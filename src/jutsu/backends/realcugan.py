import subprocess
from pathlib import Path

from jutsu.backends import register_backend, vendor_dir


class RealcuganBackend:
    def __init__(self, executable: Path | None = None):
        self.executable = executable or vendor_dir() / "realcugan" / "realcugan-ncnn-vulkan"

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        models_dir = vendor_dir() / "realcugan" / model
        cmd = [
            str(self.executable),
            "-i", str(frames_in),
            "-o", str(frames_out),
            "-s", str(scale),
            "-m", str(models_dir),
            "-n", "0",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {e.stderr}") from e


register_backend("realcugan", RealcuganBackend())
