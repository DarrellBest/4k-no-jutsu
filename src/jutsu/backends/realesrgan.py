import subprocess
from pathlib import Path

from jutsu.backends import register_backend, vendor_dir


class RealesrganBackend:
    def __init__(self, executable: Path | None = None, models_dir: Path | None = None):
        base = vendor_dir() / "realesrgan"
        self.executable = executable or base / "realesrgan-ncnn-vulkan"
        self.models_dir = models_dir or base / "models"

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(self.executable),
            "-i", str(frames_in),
            "-o", str(frames_out),
            "-s", str(scale),
            "-m", str(self.models_dir),
            "-n", model,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {e.stderr}") from e


register_backend("realesrgan", RealesrganBackend())
