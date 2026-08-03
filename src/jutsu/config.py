from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from jutsu.profiles import ColorSettings, CleanupSettings, get_profile


@dataclass
class JobConfig:
    source: str
    profile: str
    mode: str
    backend: str
    model: str
    scale: int
    cleanup: CleanupSettings
    color: ColorSettings
    output_name: str


def load_job_config(path: Path) -> JobConfig:
    raw = yaml.safe_load(path.read_text())
    if "source" not in raw:
        raise ValueError("Job config missing required field: source")

    profile_name = raw.get("profile", "anime")
    defaults = get_profile(profile_name)

    mode = raw.get("mode", "normal")
    if mode not in ("normal", "secure"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'normal' or 'secure'")

    model_overrides = raw.get("model", {})
    cleanup_overrides = raw.get("cleanup", {})
    color_overrides = raw.get("color", {})

    return JobConfig(
        source=raw["source"],
        profile=profile_name,
        mode=mode,
        backend=model_overrides.get("backend", defaults.backend),
        model=model_overrides.get("name", defaults.model),
        scale=model_overrides.get("scale", defaults.scale),
        cleanup=replace(defaults.cleanup, **cleanup_overrides),
        color=replace(defaults.color, **color_overrides),
        output_name=raw.get("output_name", "output.mp4"),
    )
