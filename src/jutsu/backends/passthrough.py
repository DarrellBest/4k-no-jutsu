from pathlib import Path

from PIL import Image

from jutsu.backends import register_backend


class PassthroughBackend:
    """Bicubic upscale with no AI model. Useful for testing the pipeline without
    a GPU, and as a baseline comparison point against the real AI backends."""

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        for frame in sorted(frames_in.glob("*.png")):
            with Image.open(frame) as img:
                resized = img.resize((img.width * scale, img.height * scale), Image.BICUBIC)
                resized.save(frames_out / frame.name)


register_backend("passthrough", PassthroughBackend())
