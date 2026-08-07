import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from jutsu import joblog
from jutsu.backends import get_backend
from jutsu.config import JobConfig
from jutsu.download import download_source, is_remote_source
from jutsu.pipeline import run_pipeline

REQUIRED_SECURE_BINARIES = ["ffmpeg", "ffprobe", "veracrypt", "mount", "umount"]
DEFAULT_RAMFS_SIZE_MB = 4096


class SecureModePreflightError(RuntimeError):
    """Raised when a secure-mode job's preflight checks fail. The job must
    refuse to start rather than fall back to a less-secure mode silently."""


def secure_preflight(config: JobConfig, source: str, vault_device: Path) -> None:
    """Verify everything a secure job needs BEFORE any mount is attempted or
    any processing starts: required binaries present, the backend's own
    executable present, the vault file exists, and the source is reachable
    (a remote source can't be existence-checked here without downloading it,
    so only local sources get a real existence check)."""
    missing = [b for b in REQUIRED_SECURE_BINARIES if shutil.which(b) is None]
    if missing:
        raise SecureModePreflightError(
            f"Missing required binaries for secure mode: {', '.join(missing)}"
        )

    backend = get_backend(config.backend)
    backend_exe = getattr(backend, "executable", None)
    if backend_exe is not None and not backend_exe.exists():
        raise SecureModePreflightError(
            f"{config.backend} backend executable not found at {backend_exe}, "
            "run scripts/install_backends.sh first"
        )

    if not vault_device.exists():
        raise SecureModePreflightError(f"VeraCrypt volume file not found: {vault_device}")

    if not is_remote_source(source) and not Path(source).exists():
        raise SecureModePreflightError(f"Source video does not exist: {source}")


def _run_privileged(cmd: list[str]) -> None:
    """Run a command that needs root via interactive sudo -- never
    passwordless (the spec is explicit: a conscious interactive unlock each
    time is preferable to unattended automation for secure mode). stdin/
    stdout/stderr are left connected to the real terminal (not captured) so
    the sudo password prompt -- and, for veracrypt, the volume passphrase
    prompt -- can actually be seen and answered interactively."""
    full_cmd = ["sudo"] + cmd
    result = subprocess.run(full_cmd)
    joblog.log_subprocess(full_cmd, result.returncode, "", "")
    if result.returncode != 0:
        raise RuntimeError(f"{full_cmd[0]} {full_cmd[1]} failed (exit {result.returncode})")


def mount_ramfs(mount_point: Path, size_cap_mb: int = DEFAULT_RAMFS_SIZE_MB) -> None:
    mount_point.mkdir(parents=True, exist_ok=True)
    _run_privileged(["mount", "-t", "ramfs", "-o", f"size={size_cap_mb}m", "ramfs", str(mount_point)])


def unmount_ramfs(mount_point: Path) -> None:
    _run_privileged(["umount", str(mount_point)])


def mount_veracrypt(vault_device: Path, mount_point: Path) -> None:
    mount_point.mkdir(parents=True, exist_ok=True)
    # No passphrase argument: veracrypt itself prompts interactively on the
    # real terminal, so the passphrase is never captured, logged, or held by
    # this process at all.
    _run_privileged(["veracrypt", "--text", "--mount", str(vault_device), str(mount_point)])


def unmount_veracrypt(mount_point: Path) -> None:
    _run_privileged(["veracrypt", "--text", "--dismount", str(mount_point)])


def ramfs_usage_bytes(mount_point: Path) -> int:
    """ramfs accepts a `size=` mount option but the kernel does not actually
    enforce it (unlike tmpfs) -- ramfs grows unbounded by design. The
    orchestrator has to police its own cap by checking real usage."""
    total = 0
    for path in mount_point.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def check_ramfs_cap(mount_point: Path, cap_mb: int) -> None:
    usage = ramfs_usage_bytes(mount_point)
    cap_bytes = cap_mb * 1024 * 1024
    if usage > cap_bytes:
        raise RuntimeError(
            f"ramfs scratch at {mount_point} exceeded its configured cap: "
            f"{usage / 1024**2:.0f} MiB used, cap is {cap_mb} MiB. Aborting "
            "rather than let usage grow unbounded (ramfs has no kernel-enforced limit)."
        )


def run_secure_pipeline(
    config: JobConfig,
    source: str,
    ramfs_mount: Path,
    vault_device: Path,
    vault_mount: Path,
    size_cap_mb: int = DEFAULT_RAMFS_SIZE_MB,
    max_workers: int = 1,
    target_resolution: tuple[int, int] | None = None,
) -> Path:
    """Secure mode: source streamed into a ramfs mount (never regular disk),
    processed there with run_pipeline as-is, then the finished output is
    written into a mounted VeraCrypt vault -- the vault mount IS the
    encryption step, there's no separate encrypt. ramfs and the vault are
    both unmounted in a finally block, so a mid-job failure never leaves the
    vault open or scratch space mounted longer than necessary."""
    if config.mode != "secure":
        raise ValueError("run_secure_pipeline requires a job config with mode: secure")

    secure_preflight(config, source, vault_device)

    mount_ramfs(ramfs_mount, size_cap_mb)
    try:
        # Local sources are read directly from where they already are (they
        # were never going to touch regular disk any more than they already
        # do by existing) -- only a remote source gets streamed into ramfs,
        # so it's never staged on regular disk at any point.
        local_source = download_source(source, ramfs_mount / "source") if is_remote_source(source) else Path(source)
        check_ramfs_cap(ramfs_mount, size_cap_mb)

        # Secure-mode logging never writes to regular disk either: the log
        # itself lives inside the ramfs mount (gone on unmount, same as job
        # state) and is redacted -- command names and exit codes only, never
        # full argument lists or captured output, which could contain
        # sensitive filenames or content.
        joblog.set_log_path(ramfs_mount / "job.log", redact=True)

        # run_pipeline itself refuses mode="secure" (that check protects the
        # public run_pipeline API from being called with secure semantics it
        # doesn't implement) -- here that's fine to bypass, because THIS
        # function is the secure orchestrator: the actual security guarantee
        # comes from workdir being inside the ramfs mount, not from any
        # check inside run_pipeline itself.
        normal_config = replace(config, mode="normal")
        output_in_ramfs = run_pipeline(
            normal_config, local_source, ramfs_mount / "work",
            max_workers=max_workers, target_resolution=target_resolution,
        )
        check_ramfs_cap(ramfs_mount, size_cap_mb)

        mount_veracrypt(vault_device, vault_mount)
        try:
            final_output = vault_mount / config.output_name
            shutil.move(str(output_in_ramfs), str(final_output))
            return final_output
        finally:
            unmount_veracrypt(vault_mount)
    finally:
        joblog.set_log_path(None)
        unmount_ramfs(ramfs_mount)
