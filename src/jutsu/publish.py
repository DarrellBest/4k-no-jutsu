import os
import shutil
import subprocess
from pathlib import Path

from jutsu.config import JobConfig


def publish_normal(output: Path, config: JobConfig) -> None:
    """Upload to pCloud and/or copy into a Jellyfin library, if configured.

    Both destinations are opt-in via environment variables
    (JUTSU_PCLOUD_REMOTE, JUTSU_JELLYFIN_DIR) -- with neither set, this is a
    no-op: the pipeline's real output already exists locally at `output`.
    """
    pcloud_remote = os.environ.get("JUTSU_PCLOUD_REMOTE")
    if pcloud_remote:
        cmd = ["rclone", "copy", str(output), pcloud_remote]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {e.stderr}") from e

    jellyfin_dir = os.environ.get("JUTSU_JELLYFIN_DIR")
    if jellyfin_dir:
        jellyfin_path = Path(jellyfin_dir)
        jellyfin_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, jellyfin_path / output.name)
