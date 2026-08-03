import subprocess
from pathlib import Path

from jutsu.backends import register_backend, vendor_dir


class RealcuganBackend:
    def __init__(self, executable: Path | None = None):
        self.executable = executable or vendor_dir() / "realcugan" / "realcugan-ncnn-vulkan"

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        models_dir = vendor_dir() / "realcugan" / model
        subprocess.run(
            [
                str(self.executable),
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-s", str(scale),
                "-m", str(models_dir),
                "-n", "0",
            ],
            check=True,
        )


register_backend("realcugan", RealcuganBackend())
