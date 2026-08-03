from pathlib import Path
from unittest.mock import patch

from jutsu.backends import get_backend, vendor_dir
from jutsu.backends.realcugan import RealcuganBackend


def test_realcugan_builds_correct_command(tmp_path, monkeypatch):
    monkeypatch.setenv("JUTSU_VENDOR_DIR", "/fake/vendor")
    backend = RealcuganBackend(executable=Path("/fake/vendor/realcugan/realcugan-ncnn-vulkan"))
    frames_in = tmp_path / "in"
    frames_out = tmp_path / "out"
    frames_in.mkdir()

    with patch("subprocess.run") as mock_run:
        backend.upscale(frames_in, frames_out, scale=4, model="models-se")

    args = mock_run.call_args[0][0]
    assert args[0] == "/fake/vendor/realcugan/realcugan-ncnn-vulkan"
    assert "-i" in args and str(frames_in) in args
    assert "-o" in args and str(frames_out) in args
    assert "-s" in args and "4" in args
    assert "-m" in args and str(vendor_dir() / "realcugan" / "models-se") in args
    assert frames_out.exists()


def test_realcugan_registered_under_name():
    backend = get_backend("realcugan")
    assert isinstance(backend, RealcuganBackend)
