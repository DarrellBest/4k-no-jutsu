import ctypes.util
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from jutsu import joblog
from jutsu.backends import get_backend
from jutsu.config import JobConfig
from jutsu.media import assemble_and_color, concat_segments, extract_and_clean, mux_audio, pad_to_resolution, probe
from jutsu.state import JobState

WINDOW_SECONDS = 5.0
MIN_FREE_DISK_BYTES = 1 * 1024**3  # 1 GiB
MIN_FREE_RAM_BYTES = 512 * 1024**2  # 512 MiB


def _vulkan_available() -> bool:
    """Whether a Vulkan loader is present on this system. Doesn't confirm a
    working GPU (software rendering via e.g. mesa lavapipe also counts as a
    working Vulkan device) -- just that the runtime library any Vulkan-based
    backend needs to even start exists at all."""
    return ctypes.util.find_library("vulkan") is not None


def _available_ram_bytes() -> int:
    """Linux-specific (matches the rest of this codebase's assumptions:
    ffmpeg/Vulkan/ncnn subprocess tooling, no cross-platform support
    attempted). MemAvailable (not MemFree) is the kernel's own estimate of
    what could actually be handed to a new process without swapping."""
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("Could not determine available RAM from /proc/meminfo")


def compute_windows(duration: float, window_seconds: float = WINDOW_SECONDS) -> list[tuple[float, float]]:
    windows = []
    start = 0.0
    while start < duration - 1e-9:
        length = min(window_seconds, duration - start)
        windows.append((start, length))
        start += window_seconds
    return windows


def preflight(config: JobConfig, source: Path, workdir: Path | None = None) -> None:
    """Validate a job before any processing starts: mode supported, input readable,
    backend registered, backend executable present on disk, Vulkan available if
    the backend needs it, sufficient RAM, and (if workdir is given) disk space."""
    if config.mode == "secure":
        raise SystemExit(
            "Secure mode is not implemented yet, see docs/superpowers/plans for the "
            "planned secure-mode design. Refusing to run this job."
        )
    if not source.exists():
        raise FileNotFoundError(f"Source video does not exist: {source}")
    backend = get_backend(config.backend)
    executable = getattr(backend, "executable", None)
    if executable is not None:
        if not executable.exists():
            raise FileNotFoundError(
                f"{config.backend} backend executable not found at {executable}, "
                "run scripts/install_backends.sh first"
            )
        if not _vulkan_available():
            raise RuntimeError(
                f"{config.backend} backend requires Vulkan, but no Vulkan loader "
                "(libvulkan.so.1) was found on this system. Install a Vulkan "
                "runtime (e.g. `apt install libvulkan1`) or a GPU driver that "
                "provides one."
            )

    available_ram = _available_ram_bytes()
    if available_ram < MIN_FREE_RAM_BYTES:
        raise RuntimeError(
            f"Insufficient available RAM: {available_ram / 1024**2:.0f} MiB free, "
            f"need at least {MIN_FREE_RAM_BYTES / 1024**2:.0f} MiB."
        )

    if workdir is not None:
        usage = shutil.disk_usage(workdir if workdir.exists() else workdir.parent)
        if usage.free < MIN_FREE_DISK_BYTES:
            raise RuntimeError(
                f"Insufficient disk space at {workdir}: {usage.free / 1024**3:.2f} GiB "
                f"free, need at least {MIN_FREE_DISK_BYTES / 1024**3:.0f} GiB."
            )


def _process_window(
    config: JobConfig,
    source: Path,
    workdir: Path,
    backend,
    info,
    state: JobState,
    index: int,
    start: float,
    length: float,
) -> None:
    frames_in = workdir / f"frames_in_{index:05d}"
    frames_out = workdir / f"frames_out_{index:05d}"
    segment_path = workdir / f"segment_{index:05d}.mp4"
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


def run_pipeline(
    config: JobConfig,
    source: Path,
    workdir: Path,
    window_seconds: float = WINDOW_SECONDS,
    max_workers: int = 1,
    target_resolution: tuple[int, int] | None = None,
) -> Path:
    preflight(config, source, workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    joblog.set_log_path(workdir / "job.log")
    try:
        info = probe(source)
        windows = compute_windows(info.duration, window_seconds)
        state = JobState(workdir / "state.json", total_windows=len(windows))
        backend = get_backend(config.backend)

        segment_paths = [workdir / f"segment_{index:05d}.mp4" for index in range(len(windows))]
        pending = [
            (index, start, length)
            for index, (start, length) in enumerate(windows)
            if not state.is_window_done(index)
        ]

        if max_workers <= 1:
            for index, start, length in pending:
                _process_window(config, source, workdir, backend, info, state, index, start, length)
        else:
            # Windows are independent (disjoint frame/segment directories per
            # index), and the real bottleneck observed on this pipeline is a
            # near-idle GPU during single-window processing, so running several
            # windows' extract/upscale/assemble concurrently is safe and gives a
            # real throughput win. Threads (not processes) are enough here since
            # each window's work is almost entirely spent blocked in subprocess
            # calls (ffmpeg, the AI backend binary), which release the GIL.
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_process_window, config, source, workdir, backend, info, state, index, start, length)
                    for index, start, length in pending
                ]
                for future in as_completed(futures):
                    future.result()  # re-raise any worker exception in the main thread

        final_video = workdir / "final_video.mp4"
        concat_segments(segment_paths, final_video)

        if target_resolution is not None:
            # Pad on the video-only concat output, before muxing -- pad_to_resolution
            # drops audio by design (a pure spatial transform has no business
            # touching the audio stream), so this must happen before mux_audio,
            # not after, or the source's audio would need re-attaching separately.
            padded_video = workdir / "padded_video.mp4"
            pad_to_resolution(final_video, target_resolution[0], target_resolution[1], padded_video)
            final_video = padded_video

        final_output = workdir / config.output_name
        if info.has_audio:
            mux_audio(final_video, source, final_output)
        else:
            final_video.replace(final_output)
        return final_output
    finally:
        # Reset so a later, unrelated run_pipeline/media.py call in the same
        # process (e.g. the next test, or a second job) doesn't keep logging
        # to this job's now-possibly-gone workdir.
        joblog.set_log_path(None)
