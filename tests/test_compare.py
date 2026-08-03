from jutsu.compare import Variant, run_compare
from jutsu.config import JobConfig
from jutsu.media import probe
from jutsu.profiles import CleanupSettings, ColorSettings


def _config(source: str) -> JobConfig:
    return JobConfig(
        source=source,
        profile="anime",
        mode="normal",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def test_run_compare_produces_original_and_variant_outputs(sample_clip, tmp_path):
    variants = [
        Variant(label="fast", backend="passthrough", model="unused", scale=2),
        Variant(label="slow", backend="passthrough", model="unused", scale=3),
    ]

    results = run_compare(_config(str(sample_clip)), sample_clip, variants, start=0.0, duration=2.0, workdir=tmp_path)

    assert set(results) == {"original", "fast", "slow"}
    for path in results.values():
        assert path.exists()

    fast_info = probe(results["fast"])
    slow_info = probe(results["slow"])
    assert fast_info.width == 128  # 64 * 2
    assert slow_info.width == 192  # 64 * 3
