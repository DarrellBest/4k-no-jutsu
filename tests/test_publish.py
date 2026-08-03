import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from jutsu.config import JobConfig
from jutsu.profiles import CleanupSettings, ColorSettings
from jutsu.publish import publish_normal, JELLYFIN_MEDIA_DIR


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


def test_publish_uploads_to_pcloud_and_copies_to_jellyfin(tmp_path):
    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with (
        patch("subprocess.run") as mock_run,
        patch("shutil.copy2") as mock_copy,
        patch("pathlib.Path.mkdir") as mock_mkdir,
    ):
        publish_normal(output, _config())

    rclone_args = mock_run.call_args[0][0]
    assert rclone_args[0] == "rclone"
    assert rclone_args[1] == "copy"
    assert str(output) in rclone_args
    assert "pcloud:Naruto" in rclone_args

    copy_args = mock_copy.call_args[0]
    assert copy_args[0] == output
    assert copy_args[1] == JELLYFIN_MEDIA_DIR / output.name

    mock_mkdir.assert_called_once()


def test_publish_surfaces_rclone_stderr_on_failure(tmp_path):
    # Consistent with every other subprocess call site in the codebase:
    # a bare CalledProcessError only shows the exit code, so failures must
    # be re-raised with the captured stderr included.
    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    failure = subprocess.CalledProcessError(
        returncode=1, cmd=["rclone", "copy"], stderr="rclone: remote not found"
    )
    with patch("subprocess.run", side_effect=failure):
        with pytest.raises(Exception) as exc_info:
            publish_normal(output, _config())

    assert "rclone: remote not found" in str(exc_info.value)
