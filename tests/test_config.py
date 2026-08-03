from pathlib import Path

import pytest

from jutsu.config import load_job_config

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_profile_defaults(tmp_path):
    config = load_job_config(FIXTURES / "anime_job.yaml")
    assert config.source == "/mnt/4tb/4k-no-jutsu-work/naruto_movie.mp4"
    assert config.profile == "anime"
    assert config.mode == "normal"
    assert config.backend == "realcugan"
    assert config.scale == 4
    assert config.cleanup.denoise == 3.0
    assert config.output_name == "output.mp4"


def test_missing_source_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("profile: anime\n")
    with pytest.raises(ValueError, match="source"):
        load_job_config(bad)


def test_invalid_mode_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("source: /tmp/x.mp4\nmode: not-a-mode\n")
    with pytest.raises(ValueError, match="Invalid mode"):
        load_job_config(bad)


def test_overrides_applied(tmp_path):
    override = tmp_path / "override.yaml"
    override.write_text(
        "source: /tmp/x.mp4\n"
        "profile: anime\n"
        "model:\n"
        "  backend: realesrgan\n"
        "  name: realesrgan-x4plus-anime\n"
        "  scale: 2\n"
        "cleanup:\n"
        "  denoise: 5.0\n"
        "color:\n"
        "  contrast: 1.2\n"
        "output_name: naruto_4k.mp4\n"
    )
    config = load_job_config(override)
    assert config.backend == "realesrgan"
    assert config.model == "realesrgan-x4plus-anime"
    assert config.scale == 2
    assert config.cleanup.denoise == 5.0
    assert config.cleanup.deblock == 2.0  # untouched profile default
    assert config.color.contrast == 1.2
    assert config.output_name == "naruto_4k.mp4"
