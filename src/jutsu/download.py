import subprocess
from pathlib import Path

from jutsu import joblog


def is_remote_source(source: str) -> bool:
    """A pCloud/rclone remote path looks like 'remote:path/to/file'. A real
    local path (this project targets Linux only) always starts with '/'
    (absolute) or './'/'../' (explicit relative) -- never a bare
    'word:' prefix."""
    if ":" not in source:
        return False
    if source.startswith("/") or source.startswith("."):
        return False
    prefix = source.split(":", 1)[0]
    return "/" not in prefix


def download_source(source: str, dest_dir: Path) -> Path:
    """Resolve a job's `source` to a local Path, downloading it first via
    rclone if it's a remote (pCloud) path. A no-op passthrough for sources
    that are already local."""
    if not is_remote_source(source):
        return Path(source)

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = source.rsplit("/", 1)[-1]
    dest_path = dest_dir / filename
    cmd = ["rclone", "copyto", source, str(dest_path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        joblog.log_subprocess(cmd, e.returncode, e.stdout or "", e.stderr or "")
        raise RuntimeError(f"Failed to download {source}: {e.stderr}") from e
    joblog.log_subprocess(cmd, result.returncode, result.stdout, result.stderr)
    return dest_path
