from jutsu.filters import build_cleanup_filter, build_color_filter
from jutsu.profiles import CleanupSettings, ColorSettings


def test_cleanup_filter_all_disabled():
    assert build_cleanup_filter(CleanupSettings()) == "null"


def test_cleanup_filter_denoise_only():
    result = build_cleanup_filter(CleanupSettings(denoise=3.0))
    assert result.startswith("hqdn3d=")
    assert "spp" not in result
    assert "deband" not in result


def test_cleanup_filter_all_enabled():
    result = build_cleanup_filter(CleanupSettings(denoise=2.0, deblock=3.0, deband=True))
    assert "hqdn3d=" in result
    assert "spp=quality=3" in result
    assert "deband" in result
    assert result.count(",") == 2


def test_color_filter_defaults():
    result = build_color_filter(ColorSettings())
    assert result == "eq=brightness=0.0:contrast=1.0:saturation=1.0:gamma=1.0"


def test_color_filter_custom_values():
    result = build_color_filter(ColorSettings(brightness=0.1, contrast=1.2, saturation=0.9, gamma=1.1))
    assert result == "eq=brightness=0.1:contrast=1.2:saturation=0.9:gamma=1.1"
