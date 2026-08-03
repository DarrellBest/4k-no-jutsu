from dataclasses import dataclass, replace
from pathlib import Path

from jutsu.config import JobConfig
from jutsu.media import extract_clip
from jutsu.pipeline import run_pipeline


@dataclass
class Variant:
    label: str
    backend: str
    model: str
    scale: int


def run_compare(
    config: JobConfig,
    source: Path,
    variants: list[Variant],
    start: float,
    duration: float,
    workdir: Path,
) -> dict[str, Path]:
    workdir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}

    clip_source = workdir / "clip_source.mp4"
    extract_clip(source, start, duration, clip_source)
    results["original"] = clip_source

    for variant in variants:
        variant_config = replace(config, backend=variant.backend, model=variant.model, scale=variant.scale)
        variant_workdir = workdir / variant.label
        results[variant.label] = run_pipeline(variant_config, clip_source, variant_workdir)

    return results
