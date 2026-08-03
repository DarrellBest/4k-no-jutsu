from dataclasses import dataclass


@dataclass
class CleanupSettings:
    denoise: float = 0.0
    deblock: float = 0.0
    deband: bool = False


@dataclass
class ColorSettings:
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0


@dataclass
class ProfileDefaults:
    backend: str
    model: str
    scale: int
    cleanup: CleanupSettings
    color: ColorSettings


PROFILES: dict[str, ProfileDefaults] = {
    "anime": ProfileDefaults(
        backend="realcugan",
        model="models-se",
        scale=4,
        cleanup=CleanupSettings(denoise=3.0, deblock=2.0, deband=True),
        color=ColorSettings(),
    ),
    "live-action": ProfileDefaults(
        backend="realesrgan",
        model="realesrgan-x4plus",
        scale=4,
        cleanup=CleanupSettings(denoise=1.0, deblock=0.0, deband=False),
        color=ColorSettings(),
    ),
}


def get_profile(name: str) -> ProfileDefaults:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {sorted(PROFILES)}")
    return PROFILES[name]
