import pytest

from jutsu.profiles import get_profile, PROFILES, CleanupSettings, ColorSettings


def test_anime_profile_defaults():
    profile = get_profile("anime")
    assert profile.backend == "realcugan"
    assert profile.model == "models-se"
    assert profile.scale == 4
    assert isinstance(profile.cleanup, CleanupSettings)
    assert isinstance(profile.color, ColorSettings)


def test_live_action_profile_defaults():
    profile = get_profile("live-action")
    assert profile.backend == "realesrgan"
    assert profile.model == "realesrgan-x4plus"


def test_unknown_profile_raises():
    with pytest.raises(ValueError, match="Unknown profile"):
        get_profile("does-not-exist")


def test_all_profiles_registered():
    assert set(PROFILES) == {"anime", "live-action"}
