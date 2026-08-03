import os
from pathlib import Path

import pytest

from jutsu.backends import get_backend, register_backend, vendor_dir


class _FakeBackend:
    def upscale(self, frames_in, frames_out, scale, model):
        pass


def test_register_and_get_backend():
    register_backend("fake-for-test", _FakeBackend())
    backend = get_backend("fake-for-test")
    assert isinstance(backend, _FakeBackend)


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown backend"):
        get_backend("does-not-exist")


def test_vendor_dir_default():
    os.environ.pop("JUTSU_VENDOR_DIR", None)
    result = vendor_dir()
    assert result.name == "vendor"


def test_vendor_dir_env_override(monkeypatch):
    monkeypatch.setenv("JUTSU_VENDOR_DIR", "/custom/path")
    assert vendor_dir() == Path("/custom/path")
