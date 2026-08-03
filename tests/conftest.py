import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def sample_clip(tmp_path) -> Path:
    """A tiny synthetic 3s clip with video + audio, generated fresh per test."""
    out = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=64x48:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
            str(out),
        ],
        check=True, capture_output=True,
    )
    return out
