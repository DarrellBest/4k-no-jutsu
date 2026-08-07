import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from jutsu.config import JobConfig
from jutsu.profiles import CleanupSettings, ColorSettings
from jutsu.secure import (
    SecureModePreflightError,
    check_ramfs_cap,
    mount_ramfs,
    mount_veracrypt,
    ramfs_usage_bytes,
    run_secure_pipeline,
    secure_preflight,
    unmount_ramfs,
    unmount_veracrypt,
)


def _secure_config(source: str) -> JobConfig:
    return JobConfig(
        source=source,
        profile="anime",
        mode="secure",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def _fake_all_binaries_present(monkeypatch):
    monkeypatch.setattr("jutsu.secure.shutil.which", lambda name: f"/usr/bin/{name}")


# --- secure_preflight ---

def test_secure_preflight_passes_when_everything_present(sample_clip, tmp_path, monkeypatch):
    _fake_all_binaries_present(monkeypatch)
    vault = tmp_path / "vault.hc"
    vault.write_bytes(b"fake vault container")

    secure_preflight(_secure_config(str(sample_clip)), str(sample_clip), vault)  # must not raise


def test_secure_preflight_raises_for_missing_binaries(sample_clip, tmp_path, monkeypatch):
    monkeypatch.setattr("jutsu.secure.shutil.which", lambda name: None)
    vault = tmp_path / "vault.hc"
    vault.write_bytes(b"fake vault container")

    with pytest.raises(SecureModePreflightError, match="binaries"):
        secure_preflight(_secure_config(str(sample_clip)), str(sample_clip), vault)


def test_secure_preflight_raises_for_missing_vault_file(sample_clip, tmp_path, monkeypatch):
    _fake_all_binaries_present(monkeypatch)
    vault = tmp_path / "does_not_exist.hc"

    with pytest.raises(SecureModePreflightError, match="VeraCrypt"):
        secure_preflight(_secure_config(str(sample_clip)), str(sample_clip), vault)


def test_secure_preflight_raises_for_missing_local_source(tmp_path, monkeypatch):
    _fake_all_binaries_present(monkeypatch)
    vault = tmp_path / "vault.hc"
    vault.write_bytes(b"fake vault container")
    missing_source = tmp_path / "does_not_exist.mp4"

    with pytest.raises(SecureModePreflightError, match="does not exist"):
        secure_preflight(_secure_config(str(missing_source)), str(missing_source), vault)


def test_secure_preflight_does_not_existence_check_remote_source(tmp_path, monkeypatch):
    # A remote source can't be existence-checked without downloading it --
    # that's what the real mount+download step will do; preflight only
    # rejects LOCAL sources it can directly verify are missing.
    _fake_all_binaries_present(monkeypatch)
    vault = tmp_path / "vault.hc"
    vault.write_bytes(b"fake vault container")

    secure_preflight(_secure_config("pcloud:Naruto/movie.mp4"), "pcloud:Naruto/movie.mp4", vault)  # must not raise


# --- mount/unmount command construction ---

def test_mount_ramfs_builds_correct_privileged_command(tmp_path):
    mount_point = tmp_path / "ramfs_mount"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        mount_ramfs(mount_point, size_cap_mb=2048)

    args = mock_run.call_args[0][0]
    assert args[0] == "sudo"
    assert args[1] == "mount"
    assert "-t" in args and "ramfs" in args
    assert any("size=2048m" in a for a in args)
    assert str(mount_point) in args
    assert mount_point.exists()  # dir created for the mount point


def test_unmount_ramfs_builds_correct_privileged_command(tmp_path):
    mount_point = tmp_path / "ramfs_mount"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        unmount_ramfs(mount_point)

    args = mock_run.call_args[0][0]
    assert args[:3] == ["sudo", "umount", str(mount_point)]


def test_mount_veracrypt_never_passes_a_passphrase_argument(tmp_path):
    # The passphrase must only ever be entered interactively on the real
    # terminal by veracrypt itself -- never as a CLI argument, which would
    # be visible in process listings and could end up logged.
    vault_device = tmp_path / "vault.hc"
    mount_point = tmp_path / "vault_mount"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        mount_veracrypt(vault_device, mount_point)

    args = mock_run.call_args[0][0]
    assert "-p" not in args
    assert "--password" not in args
    assert str(vault_device) in args
    assert str(mount_point) in args


def test_unmount_veracrypt_builds_correct_privileged_command(tmp_path):
    mount_point = tmp_path / "vault_mount"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0)
        unmount_veracrypt(mount_point)

    args = mock_run.call_args[0][0]
    assert "--dismount" in args
    assert str(mount_point) in args


def test_privileged_command_raises_on_nonzero_exit(tmp_path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 1)
        with pytest.raises(RuntimeError):
            mount_ramfs(tmp_path / "mount")


# --- ramfs usage cap (real filesystem, no mocking needed) ---

def test_ramfs_usage_bytes_sums_real_file_sizes(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 1000)
    (tmp_path / "b.bin").write_bytes(b"y" * 2000)

    assert ramfs_usage_bytes(tmp_path) == 3000


def test_check_ramfs_cap_raises_when_exceeded(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"x" * 2 * 1024 * 1024)  # 2 MiB

    with pytest.raises(RuntimeError, match="cap"):
        check_ramfs_cap(tmp_path, cap_mb=1)  # 1 MiB cap, 2 MiB used -- must raise


def test_check_ramfs_cap_passes_when_under(tmp_path):
    (tmp_path / "small.bin").write_bytes(b"x" * 1000)

    check_ramfs_cap(tmp_path, cap_mb=1)  # 1 MiB cap, 1000 bytes used -- must not raise


# --- run_secure_pipeline orchestration ---

def test_run_secure_pipeline_rejects_non_secure_config(sample_clip, tmp_path):
    normal_config = replace(_secure_config(str(sample_clip)), mode="normal")
    with pytest.raises(ValueError, match="secure"):
        run_secure_pipeline(normal_config, str(sample_clip), tmp_path / "ramfs", tmp_path / "vault.hc", tmp_path / "vault_mount")


def test_run_secure_pipeline_never_mounts_when_preflight_fails(sample_clip, tmp_path, monkeypatch):
    # No vault file exists -> preflight must fail before any mount is even
    # attempted (no sudo prompt, no partial state to clean up).
    _fake_all_binaries_present(monkeypatch)
    config = _secure_config(str(sample_clip))

    with patch("jutsu.secure.mount_ramfs") as mock_mount:
        with pytest.raises(SecureModePreflightError):
            run_secure_pipeline(
                config, str(sample_clip),
                tmp_path / "ramfs", tmp_path / "does_not_exist.hc", tmp_path / "vault_mount",
            )
    mock_mount.assert_not_called()


def test_run_secure_pipeline_end_to_end_with_mocked_mounts(sample_clip, tmp_path, monkeypatch):
    _fake_all_binaries_present(monkeypatch)
    vault_device = tmp_path / "vault.hc"
    vault_device.write_bytes(b"fake vault container")
    ramfs_mount = tmp_path / "ramfs"
    vault_mount = tmp_path / "vault_mount"
    vault_mount.mkdir()

    config = _secure_config(str(sample_clip))

    with (
        patch("jutsu.secure.mount_ramfs") as mock_mount_ramfs,
        patch("jutsu.secure.unmount_ramfs") as mock_unmount_ramfs,
        patch("jutsu.secure.mount_veracrypt") as mock_mount_vc,
        patch("jutsu.secure.unmount_veracrypt") as mock_unmount_vc,
    ):
        # mount_ramfs is mocked out entirely, so create the dir ourselves --
        # run_pipeline needs it to actually exist to do real (passthrough,
        # no GPU) processing into it.
        ramfs_mount.mkdir(parents=True, exist_ok=True)

        output = run_secure_pipeline(config, str(sample_clip), ramfs_mount, vault_device, vault_mount)

    mock_mount_ramfs.assert_called_once()
    mock_unmount_ramfs.assert_called_once()
    mock_mount_vc.assert_called_once()
    mock_unmount_vc.assert_called_once()

    # The real point of secure mode: the finished output ends up in the
    # vault mount, not anywhere on regular disk.
    assert output == vault_mount / "output.mp4"
    assert output.exists()


def test_run_secure_pipeline_unmounts_ramfs_even_when_processing_fails(sample_clip, tmp_path, monkeypatch):
    _fake_all_binaries_present(monkeypatch)
    vault_device = tmp_path / "vault.hc"
    vault_device.write_bytes(b"fake vault container")
    ramfs_mount = tmp_path / "ramfs"
    ramfs_mount.mkdir()
    vault_mount = tmp_path / "vault_mount"

    # A source that will pass preflight (file exists) but fail for real
    # once run_pipeline actually tries to probe/process it.
    broken_source = tmp_path / "not_a_real_video.mp4"
    broken_source.write_text("not a real video file")
    config = _secure_config(str(broken_source))

    with (
        patch("jutsu.secure.mount_ramfs") as mock_mount_ramfs,
        patch("jutsu.secure.unmount_ramfs") as mock_unmount_ramfs,
        patch("jutsu.secure.mount_veracrypt") as mock_mount_vc,
        patch("jutsu.secure.unmount_veracrypt") as mock_unmount_vc,
    ):
        with pytest.raises(Exception):
            run_secure_pipeline(config, str(broken_source), ramfs_mount, vault_device, vault_mount)

    mock_mount_ramfs.assert_called_once()
    mock_unmount_ramfs.assert_called_once()  # cleanup must run despite the failure
    mock_mount_vc.assert_not_called()  # never got far enough to need the vault
    mock_unmount_vc.assert_not_called()
