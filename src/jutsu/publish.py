import shutil
import subprocess
from pathlib import Path

from jutsu.config import JobConfig

JELLYFIN_MEDIA_DIR = Path("/mnt/4tb/JellyfinServer/media")
PCLOUD_REMOTE = "pcloud:Naruto"


def publish_normal(output: Path, config: JobConfig) -> None:
    cmd = ["rclone", "copy", str(output), PCLOUD_REMOTE]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{cmd[0]} failed (exit {e.returncode}): {e.stderr}") from e
    JELLYFIN_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, JELLYFIN_MEDIA_DIR / output.name)
