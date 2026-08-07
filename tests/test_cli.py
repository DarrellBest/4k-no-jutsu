import subprocess
from pathlib import Path

import pytest
import yaml

from jutsu.cli import main


def _write_config(path, source, mode="normal"):
    path.write_text(yaml.dump({"source": str(source), "profile": "anime", "mode": mode, "model": {"backend": "passthrough", "name": "unused", "scale": 2}}))


def test_cli_run_produces_output_without_publishing(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["run", str(config_path), str(workdir), "--no-publish"])

    assert exit_code == 0
    assert (workdir / "output.mp4").exists()


def test_cli_run_downloads_remote_source_before_running(sample_clip, tmp_path, monkeypatch):
    # A pCloud/rclone `source:` in the job config must be fetched to a local
    # file before the pipeline runs, per the architecture's "download
    # (skipped if local)" step -- simulated here via a fake rclone that
    # copies the real sample_clip bytes so the rest of the pipeline can
    # actually process it.
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, "pcloud:Naruto/sample.mp4")
    workdir = tmp_path / "work"

    real_run = subprocess.run

    def fake_subprocess_run(cmd, *args, **kwargs):
        if cmd[:2] == ["rclone", "copyto"]:
            dest = Path(cmd[3])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(sample_clip.read_bytes())
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    exit_code = main(["run", str(config_path), str(workdir), "--no-publish"])

    assert exit_code == 0
    assert (workdir / "downloaded_source" / "sample.mp4").exists()
    assert (workdir / "output.mp4").exists()


def test_cli_run_accepts_target_resolution_shorthand(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["run", str(config_path), str(workdir), "--no-publish", "--target-resolution", "4k"])

    assert exit_code == 0
    from jutsu.media import probe
    info = probe(workdir / "output.mp4")
    assert info.width == 3840
    assert info.height == 2160


def test_cli_run_accepts_target_resolution_explicit(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["run", str(config_path), str(workdir), "--no-publish", "--target-resolution", "256x256"])

    assert exit_code == 0
    from jutsu.media import probe
    info = probe(workdir / "output.mp4")
    assert info.width == 256
    assert info.height == 256


def test_cli_run_rejects_invalid_target_resolution(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    with pytest.raises(SystemExit):
        main(["run", str(config_path), str(workdir), "--no-publish", "--target-resolution", "not-a-resolution"])


def test_cli_run_accepts_max_workers(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["run", str(config_path), str(workdir), "--no-publish", "--max-workers", "4"])

    assert exit_code == 0
    assert (workdir / "output.mp4").exists()


def test_cli_run_rejects_secure_mode(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip, mode="secure")
    workdir = tmp_path / "work"

    with pytest.raises(SystemExit):
        main(["run", str(config_path), str(workdir), "--no-publish"])

    # Secure mode isn't implemented: no output should be produced, and none
    # of the pipeline's plaintext intermediates should exist on regular disk.
    assert not (workdir / "output.mp4").exists()


def test_cli_compare_produces_report(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir), "--start", "0", "--duration", "2"])

    assert exit_code == 0
    assert (workdir / "comparison.html").exists()


def test_cli_compare_with_nonzero_start_succeeds(sample_clip, tmp_path):
    # Timestamps used for frame grabs must be clip-relative, not absolute
    # source-relative, or any non-zero --start seeks past the extracted
    # clip's short duration and crashes (this is also the CLI's own default,
    # --start 60.0, against a full-length source).
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir), "--start", "1", "--duration", "2"])

    assert exit_code == 0
    assert (workdir / "comparison.html").exists()


def test_cli_compare_with_source_shorter_than_requested_duration(sample_clip, tmp_path):
    # sample_clip is ~3s. Requesting start=2, duration=15 means the real
    # extracted clip (stream copy, source ends before start+duration) is only
    # ~1s: far shorter than the requested 15s. Timestamps must be built
    # against the clip's ACTUAL probed duration, not the requested one, or
    # every frame grab seeks past the real clip and crashes.
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir), "--start", "2", "--duration", "15"])

    assert exit_code == 0
    assert (workdir / "comparison.html").exists()


def test_cli_compare_with_default_args_succeeds_against_short_source(sample_clip, tmp_path):
    # The CLI's own defaults are --start 60 --duration 15, which used to
    # crash against any source shorter than ~75s (including this ~3s fixture).
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir)])

    assert exit_code == 0
    assert (workdir / "comparison.html").exists()


def test_cli_compare_rejects_secure_mode(sample_clip, tmp_path):
    # cmd_compare has no mode check of its own and calls run_pipeline
    # (via run_compare) three times, once per variant; the guard must live
    # where no caller can miss it, so this must refuse just like cmd_run does.
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip, mode="secure")
    workdir = tmp_path / "work"

    with pytest.raises(SystemExit):
        main(["compare", str(config_path), str(workdir), "--start", "0", "--duration", "2"])

    assert not (workdir / "comparison.html").exists()
    # The guard must fire before ANY plaintext intermediate is written, not
    # just before the final report: run_compare's extract_clip writes
    # clip_source.mp4 to plaintext disk before run_pipeline (and therefore
    # preflight) is ever reached, so this must be checked earlier still.
    assert not workdir.exists() or not any(workdir.iterdir())


def test_cli_compare_report_has_distinct_timestamps_when_clip_shorter_than_requested(sample_clip, tmp_path):
    # sample_clip is ~3s. --start 2 --duration 15 means the real extracted
    # clip is only ~1s. raw_timestamps must be built from the clip's ACTUAL
    # duration, not the requested 15s, or all three candidate timestamps
    # clamp to the same value and the report silently collapses to one row
    # instead of three.
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir), "--start", "2", "--duration", "15"])

    assert exit_code == 0
    html = (workdir / "comparison.html").read_text()
    assert html.count('<div class="row">') == 3
