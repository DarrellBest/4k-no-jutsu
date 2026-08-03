import shutil
import subprocess
from pathlib import Path

from jutsu.config import JobConfig

JELLYFIN_MEDIA_DIR = Path("/mnt/4tb/JellyfinServer/media")
PCLOUD_REMOTE = "pcloud:Naruto"


def publish_normal(output: Path, config: JobConfig) -> None:
    subprocess.run(["rclone", "copy", str(output), PCLOUD_REMOTE], check=True)
    JELLYFIN_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, JELLYFIN_MEDIA_DIR / output.name)
