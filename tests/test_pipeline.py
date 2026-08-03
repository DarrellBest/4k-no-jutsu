import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from jutsu.backends import register_backend
from jutsu.config import JobConfig
from jutsu.pipeline import compute_windows, preflight, run_pipeline
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


def test_run_pipeline_refuses_secure_mode(sample_clip, tmp_path):
    # Secure mode isn't implemented; run_pipeline itself must refuse it so
    # every caller (cmd_run, cmd_compare, any future caller) is covered
    # automatically, not just whichever CLI command happens to check first.
    config = replace(_passthrough_config(str(sample_clip)), mode="secure")
    workdir = tmp_path / "work"

    with pytest.raises(SystemExit):
        run_pipeline(config, sample_clip, workdir)

    assert not (workdir / "output.mp4").exists()


def test_run_pipeline_uses_real_extracted_frame_rate_not_probed_nominal_rate(sample_clip, tmp_path, monkeypatch):
    # Regression test for the VFR fps bug: run_pipeline must assemble each
    # window at the frame rate actually achieved during extraction, not the
    # source's globally-probed nominal fps (media.probe's fps, derived from
    # ffprobe's r_frame_rate). On a real variable-frame-rate source,
    # r_frame_rate can be well above the real average extractable rate, which
    # (pre-fix) reassembled windows faster than real time and produced
    # shorter-than-intended output.
    #
    # sample_clip is genuinely encoded at 10fps (see conftest.py). We
    # simulate the VFR mismatch surgically: monkeypatch pipeline's probe() to
    # report a nominal fps far above that real rate (60, matching the
    # r_frame_rate=59.94 seen in the real-world repro in the bugfix brief)
    # while leaving extraction untouched, so it still writes real frames at
    # the real ~10fps rate. If the fix works, the assembled/concatenated/
    # muxed output's duration should still match the source's real duration;
    # pre-fix, using the fake nominal fps for assembly would shrink it by
    # roughly a factor of 6 (10fps content encoded as if it were 60fps).
    import jutsu.pipeline as pipeline_module
    from jutsu.media import probe as real_probe

    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"

    real_info = real_probe(sample_clip)
    fake_info = replace(real_info, fps=60.0)
    monkeypatch.setattr(pipeline_module, "probe", lambda source: fake_info)

    output = run_pipeline(config, sample_clip, workdir, window_seconds=1.0)

    assert output.exists()
    output_info = real_probe(output)
    assert abs(output_info.duration - real_info.duration) < 0.5, (
        f"expected output duration close to source duration "
        f"({real_info.duration}s), got {output_info.duration}s -- looks "
        f"like assembly used the probed nominal fps instead of the real "
        f"extracted frame rate"
    )


def test_run_pipeline_with_max_workers_matches_sequential_output(sample_clip, tmp_path):
    # Concurrent window processing must produce output equivalent to the
    # existing sequential path (same resolution, same real duration) and must
    # leave every window marked done with no gaps -- a real symptom of a
    # thread-safety bug in JobState would be a done_windows list missing
    # entries even though every window's segment file was actually written.
    config = _passthrough_config(str(sample_clip))
    workdir_sequential = tmp_path / "sequential"
    workdir_parallel = tmp_path / "parallel"

    output_sequential = run_pipeline(config, sample_clip, workdir_sequential, window_seconds=0.3, max_workers=1)
    output_parallel = run_pipeline(config, sample_clip, workdir_parallel, window_seconds=0.3, max_workers=8)

    from jutsu.media import probe
    info_sequential = probe(output_sequential)
    info_parallel = probe(output_parallel)
    assert info_parallel.width == info_sequential.width
    assert info_parallel.height == info_sequential.height
    assert abs(info_parallel.duration - info_sequential.duration) < 0.3

    state_data = json.loads((workdir_parallel / "state.json").read_text())
    assert sorted(state_data["done_windows"]) == list(range(state_data["total_windows"])), (
        "expected every window marked done with no gaps after concurrent processing"
    )


def test_run_pipeline_max_workers_resumes_only_pending_windows(sample_clip, tmp_path):
    # Concurrency must not re-process windows JobState already marked done --
    # same resumability contract as the sequential path, just dispatched
    # through a worker pool instead of a for-loop.
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"
    workdir.mkdir(parents=True)

    from jutsu.media import probe
    info = probe(sample_clip)
    windows = compute_windows(info.duration, window_seconds=0.3)
    assert len(windows) > 4  # sanity check: needs real multi-window concurrency
    state = JobState(workdir / "state.json", total_windows=len(windows))
    state.mark_window_done(0)

    segment_path = workdir / "segment_00000.mp4"
    shutil.copy(sample_clip, segment_path)
    pre_run_bytes = segment_path.read_bytes()

    output = run_pipeline(config, sample_clip, workdir, window_seconds=0.3, max_workers=4)

    assert output.exists()
    assert segment_path.read_bytes() == pre_run_bytes


def test_preflight_raises_for_missing_backend_executable(sample_clip, tmp_path):
    class FakeMissingExeBackend:
        executable = Path("/nonexistent/fake-upscaler-binary")

        def upscale(self, frames_in, frames_out, scale, model):
            raise AssertionError("should never be called: preflight must catch this first")

    register_backend("fake_missing_exe", FakeMissingExeBackend())
    config = replace(_passthrough_config(str(sample_clip)), backend="fake_missing_exe")

    with pytest.raises(FileNotFoundError, match="fake_missing_exe"):
        preflight(config, sample_clip)
