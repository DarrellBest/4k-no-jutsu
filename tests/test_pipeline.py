import shutil
from pathlib import Path

import pytest

from jutsu.config import JobConfig
from jutsu.pipeline import compute_windows, run_pipeline
from jutsu.profiles import CleanupSettings, ColorSettings
from jutsu.state import JobState


def _passthrough_config(source: str) -> JobConfig:
    return JobConfig(
        source=source,
        profile="anime",
        mode="normal",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def test_compute_windows_covers_full_duration():
    windows = compute_windows(duration=12.0, window_seconds=5.0)
    assert windows == [(0.0, 5.0), (5.0, 5.0), (10.0, 2.0)]


def test_compute_windows_exact_multiple():
    windows = compute_windows(duration=10.0, window_seconds=5.0)
    assert windows == [(0.0, 5.0), (5.0, 5.0)]


def test_run_pipeline_produces_upscaled_output(sample_clip, tmp_path):
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"

    output = run_pipeline(config, sample_clip, workdir)

    assert output.exists()
    from jutsu.media import probe
    info = probe(output)
    assert info.width == 128  # 64 * scale(2)
    assert info.height == 96  # 48 * scale(2)
    assert info.has_audio is True

    # Frames must be discarded per window (extract -> upscale -> encode ->
    # discard -> next window), not left to accumulate unbounded disk usage.
    assert not (workdir / "frames_in_00000").exists()
    assert not (workdir / "frames_out_00000").exists()


def test_run_pipeline_skips_completed_windows(sample_clip, tmp_path):
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"
    workdir.mkdir(parents=True)

    from jutsu.media import probe
    info = probe(sample_clip)
    windows = compute_windows(info.duration, window_seconds=5.0)
    state = JobState(workdir / "state.json", total_windows=len(windows))
    state.mark_window_done(0)

    # Pre-create the segment for window 0 so a real re-run isn't required for it.
    # It must be a real, ffmpeg-readable file (not arbitrary bytes): the final
    # concat + mux steps run for real against whatever segments are on disk,
    # completed or not, so a garbage placeholder would break the real ffmpeg
    # concat demuxer regardless of whether window 0 is actually skipped.
    # Reusing sample_clip's own bytes keeps this a valid file without needing a
    # second real encode.
    segment_path = workdir / "segment_00000.mp4"
    shutil.copy(sample_clip, segment_path)
    pre_run_bytes = segment_path.read_bytes()

    output = run_pipeline(config, sample_clip, workdir)
    assert output.exists()

    # Genuinely prove window 0 was skipped, not just that the pipeline ran:
    # if extract_and_clean / upscale / assemble_and_color had executed for
    # window 0, this file would have been overwritten with freshly assembled
    # (upscaled) content instead of staying byte-identical.
    assert segment_path.read_bytes() == pre_run_bytes


def test_run_pipeline_with_small_window_seconds_produces_multiple_windows(sample_clip, tmp_path):
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"

    output = run_pipeline(config, sample_clip, workdir, window_seconds=1.0)

    assert output.exists()
    # ~3s clip with 1.0s windows must produce more than one segment/window.
    assert (workdir / "segment_00001.mp4").exists()

    from jutsu.media import probe
    source_info = probe(sample_clip)
    output_info = probe(output)
    # Multi-segment concat + audio mux must reproduce the source's duration.
    assert abs(output_info.duration - source_info.duration) < 0.5


def test_run_pipeline_resumes_with_mixed_done_and_pending_windows(sample_clip, tmp_path):
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"
    workdir.mkdir(parents=True)

    from jutsu.media import probe
    info = probe(sample_clip)
    windows = compute_windows(info.duration, window_seconds=1.0)
    assert len(windows) > 1  # sanity check: this test needs a genuine multi-window mix
    state = JobState(workdir / "state.json", total_windows=len(windows))
    state.mark_window_done(0)

    segment_path = workdir / "segment_00000.mp4"
    shutil.copy(sample_clip, segment_path)
    pre_run_bytes = segment_path.read_bytes()

    output = run_pipeline(config, sample_clip, workdir, window_seconds=1.0)

    assert output.exists()
    assert segment_path.read_bytes() == pre_run_bytes


def test_run_pipeline_raises_clear_error_for_missing_source(tmp_path):
    missing_source = tmp_path / "does_not_exist.mp4"
    config = _passthrough_config(str(missing_source))
    workdir = tmp_path / "work"

    with pytest.raises(FileNotFoundError, match="does not exist"):
        run_pipeline(config, missing_source, workdir)
