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


def run_pipeline(config: JobConfig, source: Path, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    info = probe(source)
    windows = compute_windows(info.duration)
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
        backend.upscale(frames_in, frames_out, config.scale, config.model)
        assemble_and_color(frames_out, info.fps, config.color, segment_path)
        state.mark_window_done(index)

    final_video = workdir / "final_video.mp4"
    concat_segments(segment_paths, final_video)

    final_output = workdir / config.output_name
    if info.has_audio:
        mux_audio(final_video, source, final_output)
    else:
        final_video.replace(final_output)
    return final_output
