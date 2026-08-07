import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from jutsu.download import download_source, is_remote_source


def test_is_remote_source_detects_rclone_remote():
    assert is_remote_source("pcloud:Naruto/movie.mp4") is True


def test_is_remote_source_rejects_absolute_local_path():
    assert is_remote_source("/mnt/4tb/movie.mp4") is False


def test_is_remote_source_rejects_relative_local_path():
    assert is_remote_source("./movie.mp4") is False
    assert is_remote_source("relative/movie.mp4") is False


def test_download_source_passes_through_local_path_unchanged(tmp_path):
    local = tmp_path / "movie.mp4"
    with patch("subprocess.run") as mock_run:
        result = download_source(str(local), tmp_path / "downloaded")

    assert result == local
    mock_run.assert_not_called()


def test_download_source_fetches_remote_source(tmp_path):
    dest_dir = tmp_path / "downloaded"
    with patch("subprocess.run") as mock_run:
        result = download_source("pcloud:Naruto/movie.mp4", dest_dir)

    args = mock_run.call_args[0][0]
    assert args[0] == "rclone"
    assert args[1] == "copyto"
    assert "pcloud:Naruto/movie.mp4" in args
    assert result == dest_dir / "movie.mp4"
    assert str(dest_dir / "movie.mp4") in args


def test_download_source_surfaces_rclone_stderr_on_failure(tmp_path):
    failure = subprocess.CalledProcessError(
        returncode=1, cmd=["rclone", "copyto"], stderr="rclone: directory not found"
    )
    with patch("subprocess.run", side_effect=failure):
        with pytest.raises(RuntimeError, match="directory not found"):
            download_source("pcloud:Naruto/missing.mp4", tmp_path / "downloaded")
