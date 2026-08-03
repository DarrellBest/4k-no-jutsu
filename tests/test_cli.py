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


def test_cli_compare_produces_report(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir), "--start", "0", "--duration", "2"])

    assert exit_code == 0
    assert (workdir / "comparison.html").exists()
