from pathlib import Path
from unittest.mock import patch

from jutsu.backends import get_backend
from jutsu.backends.realesrgan import RealesrganBackend


def test_realesrgan_builds_correct_command(tmp_path):
    backend = RealesrganBackend(
        executable=Path("/fake/realesrgan-ncnn-vulkan"),
        models_dir=Path("/fake/models"),
    )
    frames_in = tmp_path / "in"
    frames_out = tmp_path / "out"
    frames_in.mkdir()

    with patch("subprocess.run") as mock_run:
        backend.upscale(frames_in, frames_out, scale=4, model="realesr-animevideov3")

    args = mock_run.call_args[0][0]
    assert args[0] == "/fake/realesrgan-ncnn-vulkan"
    assert "-i" in args and str(frames_in) in args
    assert "-o" in args and str(frames_out) in args
    assert "-s" in args and "4" in args
    assert "-m" in args and "/fake/models" in args
    assert "-n" in args and "realesr-animevideov3" in args
    assert frames_out.exists()


def test_realesrgan_registered_under_name():
    backend = get_backend("realesrgan")
    assert isinstance(backend, RealesrganBackend)
