from pathlib import Path
from unittest.mock import patch

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


def test_publish_uploads_to_pcloud_and_copies_to_jellyfin(tmp_path):
    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with patch("subprocess.run") as mock_run, patch("shutil.copy2") as mock_copy:
        publish_normal(output, _config())

    rclone_args = mock_run.call_args[0][0]
    assert rclone_args[0] == "rclone"
    assert rclone_args[1] == "copy"
    assert str(output) in rclone_args
    assert "pcloud:Naruto" in rclone_args

    copy_args = mock_copy.call_args[0]
    assert copy_args[0] == output
    assert str(copy_args[1]).endswith("output.mp4")
    assert "/mnt/4tb/JellyfinServer/media" in str(copy_args[1])
