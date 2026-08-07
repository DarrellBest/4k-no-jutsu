import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jutsu import joblog
from jutsu.filters import build_cleanup_filter, build_color_filter
from jutsu.profiles import CleanupSettings, ColorSettings


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a subprocess, surfacing captured stderr in the exception on failure."""
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        joblog.log_subprocess(cmd, e.returncode, e.stdout or "", e.stderr or "")
        raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {e.stderr}") from e
    joblog.log_subprocess(cmd, result.returncode, result.stdout, result.stderr)
    return result


def probe(source: Path) -> MediaInfo:
    # -v error (not quiet): quiet suppresses stderr entirely, which would
    # leave failures with no diagnostic text to surface.
    result = _run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(source)]
    )
    data = json.loads(result.stdout)
    video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    num, den = video_stream["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    duration = float(data["format"]["duration"])
    return MediaInfo(
        duration=duration,
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=fps,
        has_audio=has_audio,
    )


def extract_and_clean(source: Path, start: float, duration: float, cleanup: CleanupSettings, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    filter_str = build_cleanup_filter(cleanup)
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration)]
    if filter_str != "null":
        cmd += ["-vf", filter_str]
    cmd += [str(frames_dir / "frame_%06d.png")]
    _run(cmd)


def extract_clip(source: Path, start: float, duration: float, output: Path) -> None:
    _run(
        ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration), "-c", "copy", str(output)]
    )


def assemble_and_color(frames_dir: Path, fps: float, color: ColorSettings, output: Path) -> None:
    filter_str = build_color_filter(color)
    _run(
        [
            "ffmpeg", "-y",
            "-framerate", str(fps), "-i", str(frames_dir / "frame_%06d.png"),
            "-vf", filter_str,
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            str(output),
        ]
    )


CONCAT_BATCH_SIZE = 100


def _concat_copy(segments: list[Path], output: Path, filelist_name: str = "concat_list.txt") -> None:
    filelist = output.parent / filelist_name
    filelist.write_text("\n".join(f"file '{s.resolve()}'" for s in segments))
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist), "-c", "copy", str(output)]
    )


def _concat_reencode(segments: list[Path], output: Path, filelist_name: str) -> None:
    filelist = output.parent / filelist_name
    filelist.write_text("\n".join(f"file '{s.resolve()}'" for s in segments))
    _run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist),
            "-fps_mode", "passthrough",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            str(output),
        ]
    )


def concat_segments(segments: list[Path], output: Path, batch_size: int = CONCAT_BATCH_SIZE) -> None:
    # ffmpeg's concat demuxer + `-c copy` becomes unreliable (observed on
    # real production content: indefinite hangs, non-monotonic DTS) once
    # it's stream-copying roughly 1000+ independently-encoded segments in
    # one process -- each segment (from assemble_and_color) has its own
    # independent B-frame timestamp structure, and splicing that many
    # together via stream copy eventually corrupts timestamp accounting.
    # Below the threshold, do the original fast, lossless direct concat.
    if len(segments) <= batch_size:
        _concat_copy(segments, output)
        return

    # Above the threshold: batch into groups, re-encode each batch (a fresh
    # encode generates clean, consistent timestamps regardless of input
    # quirks -- this is what actually fixes the corruption, at the cost of
    # one extra encoding generation for batched content), then do a final
    # lightweight, lossless -c copy concat of the small number of now-clean
    # batches.
    batch_dir = output.parent / f"{output.stem}_concat_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    try:
        batch_outputs = []
        for batch_index, start in enumerate(range(0, len(segments), batch_size)):
            batch_segments = segments[start:start + batch_size]
            batch_output = batch_dir / f"batch_{batch_index:05d}.mp4"
            _concat_reencode(batch_segments, batch_output, filelist_name=f"batch_{batch_index:05d}_list.txt")
            batch_outputs.append(batch_output)

        _concat_copy(batch_outputs, output, filelist_name="concat_list.txt")
    finally:
        shutil.rmtree(batch_dir, ignore_errors=True)


def pad_to_resolution(source: Path, width: int, height: int, output: Path) -> None:
    """Scale to fit within width x height preserving aspect ratio (no
    distortion), then pad with black bars to hit that exact resolution."""
    _run(
        [
            "ffmpeg", "-y", "-i", str(source),
            "-vf", (
                f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
            ),
            # Never retime frames to conform to a declared/nominal rate that
            # may not match the input's real rate (observed on real pipeline
            # output: silent frame duplication/dropping that shrank duration).
            # A pure spatial transform must pass timestamps through unchanged.
            "-fps_mode", "passthrough",
            "-an",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            str(output),
        ]
    )


def mux_audio(video: Path, source: Path, output: Path) -> None:
    _run(
        [
            "ffmpeg", "-y",
            "-i", str(video), "-i", str(source),
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-shortest",
            str(output),
        ]
    )
