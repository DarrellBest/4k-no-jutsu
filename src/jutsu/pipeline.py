import shutil
from pathlib import Path

from jutsu.backends import get_backend
from jutsu.config import JobConfig
from jutsu.media import assemble_and_color, concat_segments, extract_and_clean, mux_audio, probe
from jutsu.state import JobState

WINDOW_SECONDS = 5.0


def compute_windows(duration: float, window_seconds: float = WINDOW_SECONDS) -> list[tuple[float, float]]:
    windows = []
    start = 0.0
    while start < duration - 1e-9:
        length = min(window_seconds, duration - start)
        windows.append((start, length))
        start += window_seconds
    return windows


def preflight(config: JobConfig, source: Path) -> None:
    """Validate a job before any processing starts: mode supported, input readable,
    backend registered, backend executable present on disk."""
    if config.mode == "secure":
        raise SystemExit(
            "Secure mode is not implemented yet, see docs/superpowers/plans for the "
            "planned secure-mode design. Refusing to run this job."
        )
    if not source.exists():
        raise FileNotFoundError(f"Source video does not exist: {source}")
    backend = get_backend(config.backend)
    executable = getattr(backend, "executable", None)
    if executable is not None and not executable.exists():
        raise FileNotFoundError(
            f"{config.backend} backend executable not found at {executable}, "
            "run scripts/install_backends.sh first"
        )


def run_pipeline(config: JobConfig, source: Path, workdir: Path, window_seconds: float = WINDOW_SECONDS) -> Path:
    preflight(config, source)
    workdir.mkdir(parents=True, exist_ok=True)
    info = probe(source)
    windows = compute_windows(info.duration, window_seconds)
    state = JobState(workdir / "state.json", total_windows=len(windows))
    backend = get_backend(config.backend)

    segment_paths = []
    for index, (start, length) in enumerate(windows):
        segment_path = workdir / f"segment_{index:05d}.mp4"
        segment_paths.append(segment_path)
        if state.is_window_done(index):
            continue

        frames_in = workdir / f"frames_in_{index:05d}"
        frames_out = workdir / f"frames_out_{index:05d}"
        extract_and_clean(source, start, length, config.cleanup, frames_in)
        # Assemble at the rate actually achieved during extraction for this
        # window, not the source's globally-probed nominal fps: on a
        # variable-frame-rate source, ffprobe's r_frame_rate (info.fps) can be
        # well above the real average number of frames landed per second,
        # which would reassemble the window's frames faster than real time
        # and produce a shorter-than-intended segment. Deriving fps from what
        # was really extracted is correct by construction regardless of
        # whether the source is CFR or VFR.
        frame_count = len(list(frames_in.glob("frame_*.png")))
        window_fps = frame_count / length if frame_count > 0 else info.fps
        backend.upscale(frames_in, frames_out, config.scale, config.model)
        assemble_and_color(frames_out, window_fps, config.color, segment_path)
        state.mark_window_done(index)
        shutil.rmtree(frames_in, ignore_errors=True)
        shutil.rmtree(frames_out, ignore_errors=True)

    final_video = workdir / "final_video.mp4"
    concat_segments(segment_paths, final_video)

    final_output = workdir / config.output_name
    if info.has_audio:
        mux_audio(final_video, source, final_output)
    else:
        final_video.replace(final_output)
    return final_output
