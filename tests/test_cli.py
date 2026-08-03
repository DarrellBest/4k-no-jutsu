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
