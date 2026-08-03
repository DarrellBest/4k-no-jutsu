import os
from pathlib import Path
from typing import Protocol


class UpscaleBackend(Protocol):
    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None: ...


_REGISTRY: dict[str, UpscaleBackend] = {}


def register_backend(name: str, backend: UpscaleBackend) -> None:
    _REGISTRY[name] = backend


def get_backend(name: str) -> UpscaleBackend:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown backend: {name}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def vendor_dir() -> Path:
    override = os.environ.get("JUTSU_VENDOR_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "vendor"


from jutsu.backends import passthrough  # noqa: E402,F401  (registers "passthrough")
