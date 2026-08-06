import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from jutsu.config import JobConfig
from jutsu.profiles import CleanupSettings, ColorSettings
from jutsu.publish import publish_normal


def _config() -> JobConfig:
    return JobConfig(
        source="/tmp/source.mp4",
        profile="anime",
        mode="normal",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def test_publish_uploads_to_pcloud_and_copies_to_jellyfin_when_both_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("JUTSU_PCLOUD_REMOTE", "pcloud:Naruto")
    jellyfin_dir = tmp_path / "jellyfin_media"
    monkeypatch.setenv("JUTSU_JELLYFIN_DIR", str(jellyfin_dir))

    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with patch("subprocess.run") as mock_run:
        publish_normal(output, _config())

    rclone_args = mock_run.call_args[0][0]
    assert rclone_args[0] == "rclone"
    assert rclone_args[1] == "copy"
    assert str(output) in rclone_args
    assert "pcloud:Naruto" in rclone_args

    copied = jellyfin_dir / output.name
    assert copied.exists()
    assert copied.read_bytes() == output.read_bytes()


def test_publish_is_a_noop_when_neither_destination_configured(tmp_path, monkeypatch):
    # Default behavior for anyone running jutsu without publish destinations
    # configured: the AI-upscaled file already exists locally in the workdir
    # (that's the real "output"), so publish_normal has nothing more to do
    # rather than assuming this specific machine's Jellyfin/pCloud layout.
    monkeypatch.delenv("JUTSU_PCLOUD_REMOTE", raising=False)
    monkeypatch.delenv("JUTSU_JELLYFIN_DIR", raising=False)

    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with patch("subprocess.run") as mock_run, patch("shutil.copy2") as mock_copy:
        publish_normal(output, _config())

    mock_run.assert_not_called()
    mock_copy.assert_not_called()


def test_publish_uploads_to_pcloud_only_when_only_that_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("JUTSU_PCLOUD_REMOTE", "pcloud:Naruto")
    monkeypatch.delenv("JUTSU_JELLYFIN_DIR", raising=False)

    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with patch("subprocess.run") as mock_run, patch("shutil.copy2") as mock_copy:
        publish_normal(output, _config())

    mock_run.assert_called_once()
    mock_copy.assert_not_called()


def test_publish_copies_to_jellyfin_only_when_only_that_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("JUTSU_PCLOUD_REMOTE", raising=False)
    jellyfin_dir = tmp_path / "jellyfin_media"
    monkeypatch.setenv("JUTSU_JELLYFIN_DIR", str(jellyfin_dir))

    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with patch("subprocess.run") as mock_run:
        publish_normal(output, _config())

    mock_run.assert_not_called()
    copied = jellyfin_dir / output.name
    assert copied.exists()


def test_publish_surfaces_rclone_stderr_on_failure(tmp_path, monkeypatch):
    # Consistent with every other subprocess call site in the codebase:
    # a bare CalledProcessError only shows the exit code, so failures must
    # be re-raised with the captured stderr included.
    monkeypatch.setenv("JUTSU_PCLOUD_REMOTE", "pcloud:Naruto")
    monkeypatch.delenv("JUTSU_JELLYFIN_DIR", raising=False)

    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    failure = subprocess.CalledProcessError(
        returncode=1, cmd=["rclone", "copy"], stderr="rclone: remote not found"
    )
    with patch("subprocess.run", side_effect=failure):
        with pytest.raises(Exception) as exc_info:
            publish_normal(output, _config())

    assert "rclone: remote not found" in str(exc_info.value)
