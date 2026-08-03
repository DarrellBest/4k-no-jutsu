import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

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
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {e.stderr}") from e


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


def concat_segments(segments: list[Path], output: Path) -> None:
    filelist = output.parent / "concat_list.txt"
    filelist.write_text("\n".join(f"file '{s.resolve()}'" for s in segments))
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist), "-c", "copy", str(output)]
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
