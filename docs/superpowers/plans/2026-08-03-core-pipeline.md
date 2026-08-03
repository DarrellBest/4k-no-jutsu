# 4k-no-jutsu Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the config-driven video upscaling pipeline (cleanup → AI upscale → color correct → encode), a CPU-only "passthrough" backend usable today without a working GPU, real AI backends (Real-ESRGAN, RealCUGAN), normal-mode publishing, and compare mode with an HTML side-by-side report.

**Architecture:** A Python package (`jutsu`) with clearly separated modules: pure config/settings, pure ffmpeg-filter-string builders, ffmpeg subprocess operations, a pluggable upscale-backend registry, a chunked pipeline orchestrator that ties them together, and thin publish/compare/CLI layers on top. Every module except the CLI is independently unit-testable; ffmpeg-based modules are tested against tiny synthetic clips generated on the fly (no committed video fixtures).

**Tech Stack:** Python 3.12 (conda env `4k-no-jutsu`), PyYAML, Pillow, pytest, system `ffmpeg`/`ffprobe` (already installed), `realesrgan-ncnn-vulkan` / `realcugan-ncnn-vulkan` (vendored, Vulkan-based).

## Global Constraints

- Activate the project's conda env before running any command in this plan: `conda activate 4k-no-jutsu`.
- Package import name is `jutsu` (Python identifiers can't start with a digit or contain hyphens); the distribution/repo name stays `4k-no-jutsu`.
- No committed binary video/model fixtures — tests generate synthetic clips via `ffmpeg -f lavfi` at run time.
- Real AI backends require a working GPU/Vulkan stack, which is currently blocked on a pending host reboot (NVIDIA driver/library version mismatch). Every task in this plan is designed to be fully buildable and testable **without** the GPU except the final manual verification task (Task 16), which is explicitly deferred until after the reboot.
- Follow the approved spec at `docs/superpowers/specs/2026-08-03-video-upscale-pipeline-design.md` for anything not covered here.
- This plan covers **normal mode and compare mode only**. Secure mode (ramfs scratch + VeraCrypt vault) is deliberately a separate follow-up plan, built once this core pipeline is proven — it reuses `pipeline.run_pipeline` as-is.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/jutsu/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Produces: an installed, importable `jutsu` package and a working `pytest` command for every later task.

- [ ] **Step 1: Create the conda environment**

Run:
```bash
conda create -n 4k-no-jutsu python=3.12 -y
```
Expected: environment created successfully.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "4k-no-jutsu"
version = "0.1.0"
description = "Config-driven AI video upscaling pipeline"
requires-python = ">=3.11"
dependencies = [
    "pyyaml>=6.0",
    "pillow>=10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
jutsu = "jutsu.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Create package skeleton**

`src/jutsu/__init__.py`:
```python
```
(empty file — just marks the package)

`tests/__init__.py`:
```python
```
(empty file)

- [ ] **Step 4: Write the smoke test**

`tests/test_smoke.py`:
```python
import jutsu


def test_package_importable():
    assert jutsu is not None
```

- [ ] **Step 5: Install the package and run the smoke test**

Run:
```bash
conda activate 4k-no-jutsu
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/jutsu/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "Scaffold jutsu Python package"
```

---

## Task 2: Content profiles and settings dataclasses

**Files:**
- Create: `src/jutsu/profiles.py`
- Test: `tests/test_profiles.py`

**Interfaces:**
- Produces:
  - `CleanupSettings(denoise: float = 0.0, deblock: float = 0.0, deband: bool = False)`
  - `ColorSettings(brightness: float = 0.0, contrast: float = 1.0, saturation: float = 1.0, gamma: float = 1.0)`
  - `ProfileDefaults(backend: str, model: str, scale: int, cleanup: CleanupSettings, color: ColorSettings)`
  - `PROFILES: dict[str, ProfileDefaults]` with keys `"anime"` and `"live-action"`
  - `get_profile(name: str) -> ProfileDefaults` — raises `ValueError` for unknown names

- [ ] **Step 1: Write the failing tests**

`tests/test_profiles.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.profiles'`

- [ ] **Step 3: Implement `profiles.py`**

`src/jutsu/profiles.py`:
```python
from dataclasses import dataclass


@dataclass
class CleanupSettings:
    denoise: float = 0.0
    deblock: float = 0.0
    deband: bool = False


@dataclass
class ColorSettings:
    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0


@dataclass
class ProfileDefaults:
    backend: str
    model: str
    scale: int
    cleanup: CleanupSettings
    color: ColorSettings


PROFILES: dict[str, ProfileDefaults] = {
    "anime": ProfileDefaults(
        backend="realcugan",
        model="models-se",
        scale=4,
        cleanup=CleanupSettings(denoise=3.0, deblock=2.0, deband=True),
        color=ColorSettings(),
    ),
    "live-action": ProfileDefaults(
        backend="realesrgan",
        model="realesrgan-x4plus",
        scale=4,
        cleanup=CleanupSettings(denoise=1.0, deblock=0.0, deband=False),
        color=ColorSettings(),
    ),
}


def get_profile(name: str) -> ProfileDefaults:
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {sorted(PROFILES)}")
    return PROFILES[name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_profiles.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/profiles.py tests/test_profiles.py
git commit -m "Add content profiles (anime, live-action) with cleanup/color defaults"
```

---

## Task 3: Job config loading

**Files:**
- Create: `src/jutsu/config.py`
- Create: `tests/fixtures/anime_job.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `jutsu.profiles.{get_profile, CleanupSettings, ColorSettings}` (Task 2)
- Produces:
  - `JobConfig(source: str, profile: str, mode: str, backend: str, model: str, scale: int, cleanup: CleanupSettings, color: ColorSettings, output_name: str)`
  - `load_job_config(path: pathlib.Path) -> JobConfig` — raises `ValueError` on missing `source` or invalid `mode`

- [ ] **Step 1: Write the failing tests**

`tests/fixtures/anime_job.yaml`:
```yaml
source: /mnt/4tb/4k-no-jutsu-work/naruto_movie.mp4
profile: anime
```

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from jutsu.config import load_job_config

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_profile_defaults(tmp_path):
    config = load_job_config(FIXTURES / "anime_job.yaml")
    assert config.source == "/mnt/4tb/4k-no-jutsu-work/naruto_movie.mp4"
    assert config.profile == "anime"
    assert config.mode == "normal"
    assert config.backend == "realcugan"
    assert config.scale == 4
    assert config.cleanup.denoise == 3.0
    assert config.output_name == "output.mp4"


def test_missing_source_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("profile: anime\n")
    with pytest.raises(ValueError, match="source"):
        load_job_config(bad)


def test_invalid_mode_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("source: /tmp/x.mp4\nmode: not-a-mode\n")
    with pytest.raises(ValueError, match="Invalid mode"):
        load_job_config(bad)


def test_overrides_applied(tmp_path):
    override = tmp_path / "override.yaml"
    override.write_text(
        "source: /tmp/x.mp4\n"
        "profile: anime\n"
        "model:\n"
        "  backend: realesrgan\n"
        "  name: realesrgan-x4plus-anime\n"
        "  scale: 2\n"
        "cleanup:\n"
        "  denoise: 5.0\n"
        "color:\n"
        "  contrast: 1.2\n"
        "output_name: naruto_4k.mp4\n"
    )
    config = load_job_config(override)
    assert config.backend == "realesrgan"
    assert config.model == "realesrgan-x4plus-anime"
    assert config.scale == 2
    assert config.cleanup.denoise == 5.0
    assert config.cleanup.deblock == 2.0  # untouched profile default
    assert config.color.contrast == 1.2
    assert config.output_name == "naruto_4k.mp4"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.config'`

- [ ] **Step 3: Implement `config.py`**

`src/jutsu/config.py`:
```python
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from jutsu.profiles import ColorSettings, CleanupSettings, get_profile


@dataclass
class JobConfig:
    source: str
    profile: str
    mode: str
    backend: str
    model: str
    scale: int
    cleanup: CleanupSettings
    color: ColorSettings
    output_name: str


def load_job_config(path: Path) -> JobConfig:
    raw = yaml.safe_load(path.read_text())
    if "source" not in raw:
        raise ValueError("Job config missing required field: source")

    profile_name = raw.get("profile", "anime")
    defaults = get_profile(profile_name)

    mode = raw.get("mode", "normal")
    if mode not in ("normal", "secure"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'normal' or 'secure'")

    model_overrides = raw.get("model", {})
    cleanup_overrides = raw.get("cleanup", {})
    color_overrides = raw.get("color", {})

    return JobConfig(
        source=raw["source"],
        profile=profile_name,
        mode=mode,
        backend=model_overrides.get("backend", defaults.backend),
        model=model_overrides.get("name", defaults.model),
        scale=model_overrides.get("scale", defaults.scale),
        cleanup=replace(defaults.cleanup, **cleanup_overrides),
        color=replace(defaults.color, **color_overrides),
        output_name=raw.get("output_name", "output.mp4"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/config.py tests/fixtures/anime_job.yaml tests/test_config.py
git commit -m "Add job config loading with profile-aware overrides"
```

---

## Task 4: FFmpeg filter-string builders

**Files:**
- Create: `src/jutsu/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: `jutsu.profiles.{CleanupSettings, ColorSettings}` (Task 2)
- Produces:
  - `build_cleanup_filter(settings: CleanupSettings) -> str` (returns `"null"` if nothing enabled)
  - `build_color_filter(settings: ColorSettings) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_filters.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_filters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.filters'`

- [ ] **Step 3: Implement `filters.py`**

`src/jutsu/filters.py`:
```python
from jutsu.profiles import CleanupSettings, ColorSettings


def build_cleanup_filter(settings: CleanupSettings) -> str:
    parts = []
    if settings.denoise > 0:
        luma = settings.denoise * 2
        chroma = settings.denoise * 1.5
        parts.append(f"hqdn3d={luma:.1f}:{chroma:.1f}:{luma * 2:.1f}:{chroma * 2:.1f}")
    if settings.deblock > 0:
        quality = min(6, max(0, round(settings.deblock)))
        parts.append(f"spp=quality={quality}")
    if settings.deband:
        parts.append("deband")
    return ",".join(parts) if parts else "null"


def build_color_filter(settings: ColorSettings) -> str:
    return (
        f"eq=brightness={settings.brightness}:contrast={settings.contrast}"
        f":saturation={settings.saturation}:gamma={settings.gamma}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_filters.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/filters.py tests/test_filters.py
git commit -m "Add ffmpeg cleanup/color filter-string builders"
```

---

## Task 5: Media operations (ffmpeg subprocess wrappers)

**Files:**
- Create: `src/jutsu/media.py`
- Create: `tests/conftest.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: `jutsu.filters.{build_cleanup_filter, build_color_filter}` (Task 4), `jutsu.profiles.{CleanupSettings, ColorSettings}` (Task 2)
- Produces:
  - `MediaInfo(duration: float, width: int, height: int, fps: float, has_audio: bool)`
  - `probe(source: pathlib.Path) -> MediaInfo`
  - `extract_and_clean(source: Path, start: float, duration: float, cleanup: CleanupSettings, frames_dir: Path) -> None` — writes `frame_000001.png`, `frame_000002.png`, ...
  - `extract_clip(source: Path, start: float, duration: float, output: Path) -> None` — raw trim, stream copy
  - `assemble_and_color(frames_dir: Path, fps: float, color: ColorSettings, output: Path) -> None`
  - `concat_segments(segments: list[Path], output: Path) -> None`
  - `mux_audio(video: Path, source: Path, output: Path) -> None`
- Test fixture `sample_clip` (in `tests/conftest.py`) is reused by every later ffmpeg-touching test module.

- [ ] **Step 1: Write the shared test fixture**

`tests/conftest.py`:
```python
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
```

- [ ] **Step 2: Write the failing tests**

`tests/test_media.py`:
```python
from pathlib import Path

from jutsu.media import (
    assemble_and_color,
    concat_segments,
    extract_and_clean,
    extract_clip,
    mux_audio,
    probe,
)
from jutsu.profiles import CleanupSettings, ColorSettings


def test_probe_reads_duration_and_resolution(sample_clip):
    info = probe(sample_clip)
    assert 2.9 <= info.duration <= 3.1
    assert info.width == 64
    assert info.height == 48
    assert info.has_audio is True


def test_extract_and_clean_writes_frames(sample_clip, tmp_path):
    frames_dir = tmp_path / "frames"
    extract_and_clean(sample_clip, start=0.0, duration=1.0, cleanup=CleanupSettings(), frames_dir=frames_dir)
    frames = sorted(frames_dir.glob("*.png"))
    assert len(frames) > 0


def test_extract_and_clean_applies_denoise(sample_clip, tmp_path):
    frames_dir = tmp_path / "frames"
    extract_and_clean(
        sample_clip, start=0.0, duration=1.0,
        cleanup=CleanupSettings(denoise=3.0), frames_dir=frames_dir,
    )
    assert len(list(frames_dir.glob("*.png"))) > 0


def test_extract_clip_trims_without_reencode(sample_clip, tmp_path):
    output = tmp_path / "clip.mp4"
    extract_clip(sample_clip, start=0.0, duration=1.0, output=output)
    assert output.exists()
    info = probe(output)
    assert info.duration <= 1.5


def test_assemble_and_color_produces_video(sample_clip, tmp_path):
    frames_dir = tmp_path / "frames"
    extract_and_clean(sample_clip, start=0.0, duration=1.0, cleanup=CleanupSettings(), frames_dir=frames_dir)
    output = tmp_path / "assembled.mp4"
    assemble_and_color(frames_dir, fps=10.0, color=ColorSettings(), output=output)
    assert output.exists()
    info = probe(output)
    assert info.width == 64
    assert info.height == 48


def test_concat_and_mux_audio_roundtrip(sample_clip, tmp_path):
    frames_dir = tmp_path / "frames"
    extract_and_clean(sample_clip, start=0.0, duration=3.0, cleanup=CleanupSettings(), frames_dir=frames_dir)
    segment = tmp_path / "segment.mp4"
    assemble_and_color(frames_dir, fps=10.0, color=ColorSettings(), output=segment)

    concatenated = tmp_path / "concatenated.mp4"
    concat_segments([segment], concatenated)
    assert concatenated.exists()

    final = tmp_path / "final.mp4"
    mux_audio(concatenated, sample_clip, final)
    info = probe(final)
    assert info.has_audio is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_media.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.media'`

- [ ] **Step 4: Implement `media.py`**

`src/jutsu/media.py`:
```python
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jutsu.filters import build_cleanup_filter, build_color_filter
from jutsu.profiles import CleanupSettings, ColorSettings


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


def probe(source: Path) -> MediaInfo:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(source)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    num, den = video_stream["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    duration = float(data["format"]["duration"])
    return MediaInfo(
        duration=duration,
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=fps,
        has_audio=has_audio,
    )


def extract_and_clean(source: Path, start: float, duration: float, cleanup: CleanupSettings, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    filter_str = build_cleanup_filter(cleanup)
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration)]
    if filter_str != "null":
        cmd += ["-vf", filter_str]
    cmd += [str(frames_dir / "frame_%06d.png")]
    subprocess.run(cmd, check=True, capture_output=True)


def extract_clip(source: Path, start: float, duration: float, output: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration), "-c", "copy", str(output)],
        check=True, capture_output=True,
    )


def assemble_and_color(frames_dir: Path, fps: float, color: ColorSettings, output: Path) -> None:
    filter_str = build_color_filter(color)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(fps), "-i", str(frames_dir / "frame_%06d.png"),
            "-vf", filter_str,
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            str(output),
        ],
        check=True, capture_output=True,
    )


def concat_segments(segments: list[Path], output: Path) -> None:
    filelist = output.parent / "concat_list.txt"
    filelist.write_text("\n".join(f"file '{s.resolve()}'" for s in segments))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist), "-c", "copy", str(output)],
        check=True, capture_output=True,
    )


def mux_audio(video: Path, source: Path, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video), "-i", str(source),
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-shortest",
            str(output),
        ],
        check=True, capture_output=True,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_media.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/jutsu/media.py tests/conftest.py tests/test_media.py
git commit -m "Add ffmpeg media operations: probe, extract, assemble, concat, mux"
```

---

## Task 6: Job state tracking (resumability)

**Files:**
- Create: `src/jutsu/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces:
  - `JobState(path: Path, total_windows: int)` — dataclass, loads existing state from `path` if present
  - `.is_window_done(index: int) -> bool`
  - `.mark_window_done(index: int) -> None` — persists immediately

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`:
```python
from jutsu.state import JobState


def test_fresh_state_has_no_windows_done(tmp_path):
    state = JobState(tmp_path / "state.json", total_windows=5)
    assert state.is_window_done(0) is False


def test_mark_and_check_window_done(tmp_path):
    state = JobState(tmp_path / "state.json", total_windows=5)
    state.mark_window_done(2)
    assert state.is_window_done(2) is True
    assert state.is_window_done(3) is False


def test_state_persists_across_instances(tmp_path):
    path = tmp_path / "state.json"
    first = JobState(path, total_windows=5)
    first.mark_window_done(1)
    first.mark_window_done(4)

    second = JobState(path, total_windows=5)
    assert second.is_window_done(1) is True
    assert second.is_window_done(4) is True
    assert second.is_window_done(0) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.state'`

- [ ] **Step 3: Implement `state.py`**

`src/jutsu/state.py`:
```python
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JobState:
    path: Path
    total_windows: int
    _done: set[int] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._done = set(data.get("done_windows", []))

    def is_window_done(self, index: int) -> bool:
        return index in self._done

    def mark_window_done(self, index: int) -> None:
        self._done.add(index)
        self._save()

    def _save(self) -> None:
        self.path.write_text(
            json.dumps({"total_windows": self.total_windows, "done_windows": sorted(self._done)})
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/state.py tests/test_state.py
git commit -m "Add job state tracking for resumable pipeline runs"
```

---

## Task 7: Backend interface and registry

**Files:**
- Create: `src/jutsu/backends/__init__.py`
- Test: `tests/test_backends_registry.py`

**Interfaces:**
- Produces:
  - `UpscaleBackend` — `typing.Protocol` with `upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None`
  - `register_backend(name: str, backend: UpscaleBackend) -> None`
  - `get_backend(name: str) -> UpscaleBackend` — raises `ValueError` for unknown names
  - `vendor_dir() -> Path` — reads `JUTSU_VENDOR_DIR` env var, defaults to `<repo_root>/vendor`

- [ ] **Step 1: Write the failing tests**

`tests/test_backends_registry.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backends_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.backends'`

- [ ] **Step 3: Implement `backends/__init__.py`**

`src/jutsu/backends/__init__.py`:
```python
import os
from pathlib import Path
from typing import Protocol


class UpscaleBackend(Protocol):
    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None: ...


_REGISTRY: dict[str, UpscaleBackend] = {}


def register_backend(name: str, backend: UpscaleBackend) -> None:
    _REGISTRY[name] = backend


def get_backend(name: str) -> UpscaleBackend:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown backend: {name}. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def vendor_dir() -> Path:
    override = os.environ.get("JUTSU_VENDOR_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "vendor"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backends_registry.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/backends/__init__.py tests/test_backends_registry.py
git commit -m "Add pluggable upscale-backend registry"
```

---

## Task 8: Passthrough backend (no GPU required)

**Files:**
- Create: `src/jutsu/backends/passthrough.py`
- Modify: `src/jutsu/backends/__init__.py` (add self-registering import at bottom)
- Test: `tests/test_backend_passthrough.py`

**Interfaces:**
- Consumes: `jutsu.backends.register_backend` (Task 7)
- Produces: `PassthroughBackend` registered under the name `"passthrough"` — bicubic resize via Pillow, no AI model, no GPU. This is both a real usable backend today (comparison baseline / works before the host reboot) and the standard test double used by later pipeline/compare tests.

- [ ] **Step 1: Write the failing test**

`tests/test_backend_passthrough.py`:
```python
from PIL import Image

from jutsu.backends import get_backend


def test_passthrough_scales_images(tmp_path):
    frames_in = tmp_path / "in"
    frames_out = tmp_path / "out"
    frames_in.mkdir()
    Image.new("RGB", (10, 8), color="red").save(frames_in / "frame_000001.png")

    backend = get_backend("passthrough")
    backend.upscale(frames_in, frames_out, scale=4, model="unused")

    output_frames = sorted(frames_out.glob("*.png"))
    assert len(output_frames) == 1
    with Image.open(output_frames[0]) as img:
        assert img.size == (40, 32)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backend_passthrough.py -v`
Expected: FAIL with `ValueError: Unknown backend: passthrough`

- [ ] **Step 3: Implement `passthrough.py`**

`src/jutsu/backends/passthrough.py`:
```python
from pathlib import Path

from PIL import Image

from jutsu.backends import register_backend


class PassthroughBackend:
    """Bicubic upscale with no AI model. Useful for testing the pipeline without
    a GPU, and as a baseline comparison point against the real AI backends."""

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        for frame in sorted(frames_in.glob("*.png")):
            with Image.open(frame) as img:
                resized = img.resize((img.width * scale, img.height * scale), Image.BICUBIC)
                resized.save(frames_out / frame.name)


register_backend("passthrough", PassthroughBackend())
```

- [ ] **Step 4: Register it on package import**

Append to the bottom of `src/jutsu/backends/__init__.py`:
```python
from jutsu.backends import passthrough  # noqa: E402,F401  (registers "passthrough")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_backend_passthrough.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/jutsu/backends/passthrough.py src/jutsu/backends/__init__.py tests/test_backend_passthrough.py
git commit -m "Add passthrough backend (bicubic, no GPU) as baseline and test double"
```

---

## Task 9: Real-ESRGAN backend

**Files:**
- Create: `src/jutsu/backends/realesrgan.py`
- Modify: `src/jutsu/backends/__init__.py` (add self-registering import)
- Create: `scripts/install_backends.sh`
- Test: `tests/test_backend_realesrgan.py`

**Interfaces:**
- Consumes: `jutsu.backends.{register_backend, vendor_dir}` (Task 7)
- Produces: `RealesrganBackend` registered under `"realesrgan"`. Valid `model` values: `realesr-animevideov3` (default), `realesrgan-x4plus`, `realesrgan-x4plus-anime`, `realesrnet-x4plus`.

This task's command-construction tests run today with a mocked subprocess (no GPU needed). The install script downloads the real binary today too (download/unzip needs no GPU) — only *executing* it for a real upscale needs Vulkan, which is covered in Task 16 after the reboot.

- [ ] **Step 1: Write the install script**

`scripts/install_backends.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT/vendor"
mkdir -p "$VENDOR_DIR"

if [ ! -x "$VENDOR_DIR/realesrgan/realesrgan-ncnn-vulkan" ]; then
  echo "Installing realesrgan-ncnn-vulkan..."
  TMP=$(mktemp -d)
  curl -L -o "$TMP/realesrgan.zip" \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip
  mkdir -p "$VENDOR_DIR/realesrgan"
  unzip -o -q "$TMP/realesrgan.zip" -d "$VENDOR_DIR/realesrgan"
  chmod +x "$VENDOR_DIR/realesrgan/realesrgan-ncnn-vulkan"
  rm -rf "$TMP"
fi

if [ ! -x "$VENDOR_DIR/realcugan/realcugan-ncnn-vulkan" ]; then
  echo "Installing realcugan-ncnn-vulkan..."
  TMP=$(mktemp -d)
  curl -L -o "$TMP/realcugan.zip" \
    https://github.com/nihui/realcugan-ncnn-vulkan/releases/download/20220728/realcugan-ncnn-vulkan-20220728-ubuntu.zip
  unzip -o -q "$TMP/realcugan.zip" -d "$TMP/extracted"
  mkdir -p "$VENDOR_DIR/realcugan"
  mv "$TMP"/extracted/realcugan-ncnn-vulkan-20220728-ubuntu/* "$VENDOR_DIR/realcugan/"
  chmod +x "$VENDOR_DIR/realcugan/realcugan-ncnn-vulkan"
  rm -rf "$TMP"
fi

echo "Backends installed in $VENDOR_DIR"
```

Run:
```bash
chmod +x scripts/install_backends.sh
./scripts/install_backends.sh
```
Expected: `vendor/realesrgan/realesrgan-ncnn-vulkan` and `vendor/realesrgan/models/` (containing `realesrgan-x4plus.bin`/`.param` etc.) exist; `vendor/realcugan/realcugan-ncnn-vulkan` and `vendor/realcugan/models-se/` etc. exist.

- [ ] **Step 2: Verify the binary runs (help text needs no GPU)**

Run: `./vendor/realesrgan/realesrgan-ncnn-vulkan -h`
Expected: usage text printed, exit code 0.

- [ ] **Step 3: Add `vendor/` to `.gitignore`**

Append to `.gitignore`:
```
vendor/
```

- [ ] **Step 4: Write the failing test**

`tests/test_backend_realesrgan.py`:
```python
from pathlib import Path
from unittest.mock import patch

from jutsu.backends import get_backend
from jutsu.backends.realesrgan import RealesrganBackend


def test_realesrgan_builds_correct_command(tmp_path):
    backend = RealesrganBackend(
        executable=Path("/fake/realesrgan-ncnn-vulkan"),
        models_dir=Path("/fake/models"),
    )
    frames_in = tmp_path / "in"
    frames_out = tmp_path / "out"
    frames_in.mkdir()

    with patch("subprocess.run") as mock_run:
        backend.upscale(frames_in, frames_out, scale=4, model="realesr-animevideov3")

    args = mock_run.call_args[0][0]
    assert args[0] == "/fake/realesrgan-ncnn-vulkan"
    assert "-i" in args and str(frames_in) in args
    assert "-o" in args and str(frames_out) in args
    assert "-s" in args and "4" in args
    assert "-m" in args and "/fake/models" in args
    assert "-n" in args and "realesr-animevideov3" in args
    assert frames_out.exists()


def test_realesrgan_registered_under_name():
    backend = get_backend("realesrgan")
    assert isinstance(backend, RealesrganBackend)
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `pytest tests/test_backend_realesrgan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.backends.realesrgan'`

- [ ] **Step 6: Implement `realesrgan.py`**

`src/jutsu/backends/realesrgan.py`:
```python
import subprocess
from pathlib import Path

from jutsu.backends import register_backend, vendor_dir


class RealesrganBackend:
    def __init__(self, executable: Path | None = None, models_dir: Path | None = None):
        base = vendor_dir() / "realesrgan"
        self.executable = executable or base / "realesrgan-ncnn-vulkan"
        self.models_dir = models_dir or base / "models"

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                str(self.executable),
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-s", str(scale),
                "-m", str(self.models_dir),
                "-n", model,
            ],
            check=True,
        )


register_backend("realesrgan", RealesrganBackend())
```

- [ ] **Step 7: Register it on package import**

Append to the bottom of `src/jutsu/backends/__init__.py`:
```python
from jutsu.backends import realesrgan  # noqa: E402,F401  (registers "realesrgan")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_backend_realesrgan.py -v`
Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add scripts/install_backends.sh .gitignore src/jutsu/backends/realesrgan.py src/jutsu/backends/__init__.py tests/test_backend_realesrgan.py
git commit -m "Add Real-ESRGAN backend and vendored-binary install script"
```

---

## Task 10: RealCUGAN backend

**Files:**
- Create: `src/jutsu/backends/realcugan.py`
- Modify: `src/jutsu/backends/__init__.py` (add self-registering import)
- Test: `tests/test_backend_realcugan.py`

**Interfaces:**
- Consumes: `jutsu.backends.{register_backend, vendor_dir}` (Task 7)
- Produces: `RealcuganBackend` registered under `"realcugan"`. `model` selects the models subdirectory (`"models-se"`, `"models-pro"`, or `"models-nose"`).

- [ ] **Step 1: Write the failing test**

`tests/test_backend_realcugan.py`:
```python
from pathlib import Path
from unittest.mock import patch

from jutsu.backends import get_backend, vendor_dir
from jutsu.backends.realcugan import RealcuganBackend


def test_realcugan_builds_correct_command(tmp_path, monkeypatch):
    monkeypatch.setenv("JUTSU_VENDOR_DIR", "/fake/vendor")
    backend = RealcuganBackend(executable=Path("/fake/vendor/realcugan/realcugan-ncnn-vulkan"))
    frames_in = tmp_path / "in"
    frames_out = tmp_path / "out"
    frames_in.mkdir()

    with patch("subprocess.run") as mock_run:
        backend.upscale(frames_in, frames_out, scale=4, model="models-se")

    args = mock_run.call_args[0][0]
    assert args[0] == "/fake/vendor/realcugan/realcugan-ncnn-vulkan"
    assert "-i" in args and str(frames_in) in args
    assert "-o" in args and str(frames_out) in args
    assert "-s" in args and "4" in args
    assert "-m" in args and str(vendor_dir() / "realcugan" / "models-se") in args
    assert frames_out.exists()


def test_realcugan_registered_under_name():
    backend = get_backend("realcugan")
    assert isinstance(backend, RealcuganBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backend_realcugan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.backends.realcugan'`

- [ ] **Step 3: Implement `realcugan.py`**

`src/jutsu/backends/realcugan.py`:
```python
import subprocess
from pathlib import Path

from jutsu.backends import register_backend, vendor_dir


class RealcuganBackend:
    def __init__(self, executable: Path | None = None):
        self.executable = executable or vendor_dir() / "realcugan" / "realcugan-ncnn-vulkan"

    def upscale(self, frames_in: Path, frames_out: Path, scale: int, model: str) -> None:
        frames_out.mkdir(parents=True, exist_ok=True)
        models_dir = vendor_dir() / "realcugan" / model
        subprocess.run(
            [
                str(self.executable),
                "-i", str(frames_in),
                "-o", str(frames_out),
                "-s", str(scale),
                "-m", str(models_dir),
                "-n", "0",
            ],
            check=True,
        )


register_backend("realcugan", RealcuganBackend())
```

- [ ] **Step 4: Register it on package import**

Append to the bottom of `src/jutsu/backends/__init__.py`:
```python
from jutsu.backends import realcugan  # noqa: E402,F401  (registers "realcugan")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_backend_realcugan.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/jutsu/backends/realcugan.py src/jutsu/backends/__init__.py tests/test_backend_realcugan.py
git commit -m "Add RealCUGAN backend"
```

---

## Task 11: Chunked pipeline orchestrator

**Files:**
- Create: `src/jutsu/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `jutsu.config.JobConfig` (Task 3), `jutsu.state.JobState` (Task 6), `jutsu.media.{probe, extract_and_clean, assemble_and_color, concat_segments, mux_audio}` (Task 5), `jutsu.backends.get_backend` (Task 7), the `"passthrough"` backend (Task 8)
- Produces:
  - `compute_windows(duration: float, window_seconds: float = 5.0) -> list[tuple[float, float]]`
  - `run_pipeline(config: JobConfig, source: Path, workdir: Path) -> Path` — returns the final output file path. Safe to re-run on an interrupted `workdir`: already-completed windows (per `JobState`) are skipped.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:
```python
from pathlib import Path

from jutsu.config import JobConfig
from jutsu.pipeline import compute_windows, run_pipeline
from jutsu.profiles import CleanupSettings, ColorSettings
from jutsu.state import JobState


def _passthrough_config(source: str) -> JobConfig:
    return JobConfig(
        source=source,
        profile="anime",
        mode="normal",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def test_compute_windows_covers_full_duration():
    windows = compute_windows(duration=12.0, window_seconds=5.0)
    assert windows == [(0.0, 5.0), (5.0, 5.0), (10.0, 2.0)]


def test_compute_windows_exact_multiple():
    windows = compute_windows(duration=10.0, window_seconds=5.0)
    assert windows == [(0.0, 5.0), (5.0, 5.0)]


def test_run_pipeline_produces_upscaled_output(sample_clip, tmp_path):
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"

    output = run_pipeline(config, sample_clip, workdir)

    assert output.exists()
    from jutsu.media import probe
    info = probe(output)
    assert info.width == 128  # 64 * scale(2)
    assert info.height == 96  # 48 * scale(2)
    assert info.has_audio is True


def test_run_pipeline_skips_completed_windows(sample_clip, tmp_path):
    config = _passthrough_config(str(sample_clip))
    workdir = tmp_path / "work"
    workdir.mkdir(parents=True)

    from jutsu.media import probe
    info = probe(sample_clip)
    windows = compute_windows(info.duration, window_seconds=5.0)
    state = JobState(workdir / "state.json", total_windows=len(windows))
    state.mark_window_done(0)

    # Pre-create the segment for window 0 so a real re-run isn't required for it.
    (workdir / "segment_00000.mp4").write_bytes(b"not-a-real-video-but-should-be-skipped")

    output = run_pipeline(config, sample_clip, workdir)
    assert output.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.pipeline'`

- [ ] **Step 3: Implement `pipeline.py`**

`src/jutsu/pipeline.py`:
```python
from pathlib import Path

from jutsu.backends import get_backend
from jutsu.config import JobConfig
from jutsu.media import assemble_and_color, concat_segments, extract_and_clean, mux_audio, probe
from jutsu.state import JobState

WINDOW_SECONDS = 5.0


def compute_windows(duration: float, window_seconds: float = WINDOW_SECONDS) -> list[tuple[float, float]]:
    windows = []
    start = 0.0
    while start < duration - 1e-9:
        length = min(window_seconds, duration - start)
        windows.append((start, length))
        start += window_seconds
    return windows


def run_pipeline(config: JobConfig, source: Path, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    info = probe(source)
    windows = compute_windows(info.duration)
    state = JobState(workdir / "state.json", total_windows=len(windows))
    backend = get_backend(config.backend)

    segment_paths = []
    for index, (start, length) in enumerate(windows):
        segment_path = workdir / f"segment_{index:05d}.mp4"
        segment_paths.append(segment_path)
        if state.is_window_done(index):
            continue

        frames_in = workdir / f"frames_in_{index:05d}"
        frames_out = workdir / f"frames_out_{index:05d}"
        extract_and_clean(source, start, length, config.cleanup, frames_in)
        backend.upscale(frames_in, frames_out, config.scale, config.model)
        assemble_and_color(frames_out, info.fps, config.color, segment_path)
        state.mark_window_done(index)

    final_video = workdir / "final_video.mp4"
    concat_segments(segment_paths, final_video)

    final_output = workdir / config.output_name
    if info.has_audio:
        mux_audio(final_video, source, final_output)
    else:
        final_video.replace(final_output)
    return final_output
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/pipeline.py tests/test_pipeline.py
git commit -m "Add chunked pipeline orchestrator with resumable window processing"
```

---

## Task 12: Publish (pCloud + Jellyfin)

**Files:**
- Create: `src/jutsu/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `jutsu.config.JobConfig` (Task 3)
- Produces: `publish_normal(output: Path, config: JobConfig) -> None` — uploads to the `pcloud:Naruto` rclone remote and copies into the Jellyfin media library at `/mnt/4tb/JellyfinServer/media`.

- [ ] **Step 1: Write the failing tests**

`tests/test_publish.py`:
```python
from pathlib import Path
from unittest.mock import patch

from jutsu.config import JobConfig
from jutsu.profiles import CleanupSettings, ColorSettings
from jutsu.publish import publish_normal


def _config() -> JobConfig:
    return JobConfig(
        source="/tmp/source.mp4",
        profile="anime",
        mode="normal",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def test_publish_uploads_to_pcloud_and_copies_to_jellyfin(tmp_path):
    output = tmp_path / "output.mp4"
    output.write_bytes(b"fake-video-bytes")

    with patch("subprocess.run") as mock_run, patch("shutil.copy2") as mock_copy:
        publish_normal(output, _config())

    rclone_args = mock_run.call_args[0][0]
    assert rclone_args[0] == "rclone"
    assert rclone_args[1] == "copy"
    assert str(output) in rclone_args
    assert "pcloud:Naruto" in rclone_args

    copy_args = mock_copy.call_args[0]
    assert copy_args[0] == output
    assert str(copy_args[1]).endswith("output.mp4")
    assert "/mnt/4tb/JellyfinServer/media" in str(copy_args[1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.publish'`

- [ ] **Step 3: Implement `publish.py`**

`src/jutsu/publish.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_publish.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/publish.py tests/test_publish.py
git commit -m "Add normal-mode publish: rclone upload + Jellyfin library copy"
```

---

## Task 13: Compare mode

**Files:**
- Create: `src/jutsu/compare.py`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: `jutsu.config.JobConfig` (Task 3), `jutsu.media.extract_clip` (Task 5), `jutsu.pipeline.run_pipeline` (Task 11)
- Produces:
  - `Variant(label: str, backend: str, model: str, scale: int)`
  - `run_compare(config: JobConfig, source: Path, variants: list[Variant], start: float, duration: float, workdir: Path) -> dict[str, Path]` — key `"original"` maps to the raw trimmed clip; every variant label maps to its processed output.

- [ ] **Step 1: Write the failing test**

`tests/test_compare.py`:
```python
from jutsu.compare import Variant, run_compare
from jutsu.config import JobConfig
from jutsu.media import probe
from jutsu.profiles import CleanupSettings, ColorSettings


def _config(source: str) -> JobConfig:
    return JobConfig(
        source=source,
        profile="anime",
        mode="normal",
        backend="passthrough",
        model="unused",
        scale=2,
        cleanup=CleanupSettings(),
        color=ColorSettings(),
        output_name="output.mp4",
    )


def test_run_compare_produces_original_and_variant_outputs(sample_clip, tmp_path):
    variants = [
        Variant(label="fast", backend="passthrough", model="unused", scale=2),
        Variant(label="slow", backend="passthrough", model="unused", scale=3),
    ]

    results = run_compare(_config(str(sample_clip)), sample_clip, variants, start=0.0, duration=2.0, workdir=tmp_path)

    assert set(results) == {"original", "fast", "slow"}
    for path in results.values():
        assert path.exists()

    fast_info = probe(results["fast"])
    slow_info = probe(results["slow"])
    assert fast_info.width == 128  # 64 * 2
    assert slow_info.width == 192  # 64 * 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compare.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.compare'`

- [ ] **Step 3: Implement `compare.py`**

`src/jutsu/compare.py`:
```python
from dataclasses import dataclass, replace
from pathlib import Path

from jutsu.config import JobConfig
from jutsu.media import extract_clip
from jutsu.pipeline import run_pipeline


@dataclass
class Variant:
    label: str
    backend: str
    model: str
    scale: int


def run_compare(
    config: JobConfig,
    source: Path,
    variants: list[Variant],
    start: float,
    duration: float,
    workdir: Path,
) -> dict[str, Path]:
    workdir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}

    clip_source = workdir / "clip_source.mp4"
    extract_clip(source, start, duration, clip_source)
    results["original"] = clip_source

    for variant in variants:
        variant_config = replace(config, backend=variant.backend, model=variant.model, scale=variant.scale)
        variant_workdir = workdir / variant.label
        results[variant.label] = run_pipeline(variant_config, clip_source, variant_workdir)

    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_compare.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/compare.py tests/test_compare.py
git commit -m "Add compare mode: run multiple model/setting variants on a sample clip"
```

---

## Task 14: HTML comparison report

**Files:**
- Create: `src/jutsu/html_report.py`
- Test: `tests/test_html_report.py`

**Interfaces:**
- Consumes: nothing beyond `pathlib.Path` — takes the `dict[str, Path]` produced by `run_compare` (Task 13) plus a list of timestamps
- Produces:
  - `grab_frame(video: Path, timestamp: float, out_png: Path) -> None`
  - `build_comparison_html(variants: dict[str, Path], timestamps: list[float], workdir: Path) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_html_report.py`:
```python
from jutsu.html_report import build_comparison_html, grab_frame


def test_grab_frame_writes_png(sample_clip, tmp_path):
    out = tmp_path / "frame.png"
    grab_frame(sample_clip, timestamp=1.0, out_png=out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_build_comparison_html_includes_all_variants_and_timestamps(sample_clip, tmp_path):
    variants = {"original": sample_clip, "fast": sample_clip}
    html = build_comparison_html(variants, timestamps=[0.5, 1.5], workdir=tmp_path / "frames")

    assert "original" in html
    assert "fast" in html
    assert "0.5" in html
    assert "1.5" in html
    assert html.count("data:image/png;base64,") == 4  # 2 variants x 2 timestamps
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_html_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.html_report'`

- [ ] **Step 3: Implement `html_report.py`**

`src/jutsu/html_report.py`:
```python
import base64
import subprocess
from pathlib import Path


def grab_frame(video: Path, timestamp: float, out_png: Path) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1", str(out_png)],
        check=True, capture_output=True,
    )


def _data_uri(png_path: Path) -> str:
    data = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def build_comparison_html(variants: dict[str, Path], timestamps: list[float], workdir: Path) -> str:
    workdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for ts in timestamps:
        cells = []
        for label, video_path in variants.items():
            png = workdir / f"{label}_{ts:.1f}.png"
            grab_frame(video_path, ts, png)
            cells.append(
                f'<figure><img src="{_data_uri(png)}">'
                f'<figcaption>{label} @ {ts:.1f}s</figcaption></figure>'
            )
        rows.append(f'<div class="row">{"".join(cells)}</div>')
    body = "\n".join(rows)
    return f"""<!doctype html>
<html><head><title>4k-no-jutsu comparison</title>
<style>
.row {{ display: flex; gap: 8px; margin-bottom: 16px; }}
figure {{ margin: 0; }}
img {{ max-width: 300px; display: block; }}
figcaption {{ text-align: center; font-family: sans-serif; font-size: 12px; }}
</style></head>
<body>{body}</body></html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_html_report.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jutsu/html_report.py tests/test_html_report.py
git commit -m "Add HTML side-by-side comparison report generator"
```

---

## Task 15: CLI

**Files:**
- Create: `src/jutsu/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `jutsu.config.load_job_config` (Task 3), `jutsu.pipeline.run_pipeline` (Task 11), `jutsu.publish.publish_normal` (Task 12), `jutsu.compare.{Variant, run_compare}` (Task 13), `jutsu.html_report.build_comparison_html` (Task 14)
- Produces:
  - `main(argv: list[str] | None = None) -> int` — the `jutsu` console-script entry point (`jutsu run <config> <workdir> [--no-publish]`, `jutsu compare <config> <workdir> [--start N] [--duration N]`)

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import yaml

from jutsu.cli import main


def _write_config(path, source, mode="normal"):
    path.write_text(yaml.dump({"source": str(source), "profile": "anime", "mode": mode, "model": {"backend": "passthrough", "name": "unused", "scale": 2}}))


def test_cli_run_produces_output_without_publishing(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["run", str(config_path), str(workdir), "--no-publish"])

    assert exit_code == 0
    assert (workdir / "output.mp4").exists()


def test_cli_compare_produces_report(sample_clip, tmp_path):
    config_path = tmp_path / "job.yaml"
    _write_config(config_path, sample_clip)
    workdir = tmp_path / "work"

    exit_code = main(["compare", str(config_path), str(workdir), "--start", "0", "--duration", "2"])

    assert exit_code == 0
    assert (workdir / "comparison.html").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jutsu.cli'`

- [ ] **Step 3: Implement `cli.py`**

`src/jutsu/cli.py`:
```python
import argparse
from pathlib import Path

from jutsu.compare import Variant, run_compare
from jutsu.config import load_job_config
from jutsu.html_report import build_comparison_html
from jutsu.pipeline import run_pipeline
from jutsu.publish import publish_normal


def cmd_run(args: argparse.Namespace) -> int:
    config = load_job_config(Path(args.config))
    workdir = Path(args.workdir)
    source = Path(config.source)
    output = run_pipeline(config, source, workdir)
    if config.mode == "normal" and not args.no_publish:
        publish_normal(output, config)
    print(f"Done: {output}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    config = load_job_config(Path(args.config))
    workdir = Path(args.workdir)
    source = Path(config.source)

    variants = [
        Variant(label="realcugan", backend="realcugan", model=config.model, scale=config.scale),
        Variant(label="realesrgan", backend="realesrgan", model="realesrgan-x4plus", scale=config.scale),
        Variant(label="passthrough", backend="passthrough", model="unused", scale=config.scale),
    ]
    results = run_compare(config, source, variants, args.start, args.duration, workdir)

    timestamps = [args.start + 1.0, args.start + args.duration / 2, args.start + args.duration - 1.0]
    html = build_comparison_html(results, timestamps, workdir / "report_frames")
    report_path = workdir / "comparison.html"
    report_path.write_text(html)

    print(f"Sample clips: {list(results.values())}")
    print(f"Comparison report: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jutsu")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the full upscale pipeline on a job config")
    run_parser.add_argument("config")
    run_parser.add_argument("workdir")
    run_parser.add_argument("--no-publish", action="store_true")
    run_parser.set_defaults(func=cmd_run)

    compare_parser = sub.add_parser("compare", help="Compare models/settings on a short clip")
    compare_parser.add_argument("config")
    compare_parser.add_argument("workdir")
    compare_parser.add_argument("--start", type=float, default=60.0)
    compare_parser.add_argument("--duration", type=float, default=15.0)
    compare_parser.set_defaults(func=cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests across every task pass.

- [ ] **Step 6: Commit**

```bash
git add src/jutsu/cli.py tests/test_cli.py
git commit -m "Add jutsu CLI: run and compare subcommands"
```

---

## Task 16: Manual verification (post-reboot, GPU required)

Not a TDD task — this can only be exercised once the host's NVIDIA driver mismatch is resolved by a reboot, since it needs a working Vulkan/GPU stack. Do not attempt before then.

- [ ] **Step 1: Confirm GPU/Vulkan works after reboot**

Run: `nvidia-smi` and `vulkaninfo --summary`
Expected: both succeed without the "Driver/library version mismatch" error.

- [ ] **Step 2: Verify the real backends run end-to-end**

Run:
```bash
conda activate 4k-no-jutsu
./vendor/realesrgan/realesrgan-ncnn-vulkan -i <(mkdir -p /tmp/jutsu-smoke-in) # sanity only; see below
```
Concretely: create a one-frame test directory and confirm a real upscale runs:
```bash
mkdir -p /tmp/jutsu-smoke-in /tmp/jutsu-smoke-out
python -c "from PIL import Image; Image.new('RGB', (64, 48), 'blue').save('/tmp/jutsu-smoke-in/frame_000001.png')"
./vendor/realesrgan/realesrgan-ncnn-vulkan -i /tmp/jutsu-smoke-in -o /tmp/jutsu-smoke-out -n realesr-animevideov3
./vendor/realcugan/realcugan-ncnn-vulkan -i /tmp/jutsu-smoke-in -o /tmp/jutsu-smoke-out-cugan -m ./vendor/realcugan/models-se -s 4 -n 0
```
Expected: both commands exit 0 and write an upscaled PNG to their output directory.

- [ ] **Step 3: Download the real Naruto source locally**

Run:
```bash
mkdir -p /mnt/4tb/4k-no-jutsu-work
rclone copy "pcloud:Naruto" /mnt/4tb/4k-no-jutsu-work/
```
Expected: the Naruto video file(s) appear in `/mnt/4tb/4k-no-jutsu-work/`.

- [ ] **Step 4: Run compare mode on the real source**

Write a job config, e.g. `jobs/naruto_movie.yaml`:
```yaml
source: /mnt/4tb/4k-no-jutsu-work/Naruto Shipuden Movie.mp4
profile: anime
```
Run:
```bash
jutsu compare jobs/naruto_movie.yaml /mnt/4tb/4k-no-jutsu-work/compare_run --start 300 --duration 15
```
Expected: `comparison.html` and labeled sample clips (`realcugan`, `realesrgan`, `passthrough`, `original`) appear under the workdir. Open `comparison.html` in a browser and the sample clips in a media player to judge quality before committing to a full run.

- [ ] **Step 5: Note actual timing**

Record how long a single 15s compare-mode window took per backend in the plan's tracking issue/notes — this determines whether the default `WINDOW_SECONDS = 5.0` in `pipeline.py` needs adjusting for a full-length run, and gives a real estimate for how long the full movie will take.

---

## Self-review notes

- **Spec coverage:** config/profiles (Tasks 2-3), cleanup→upscale→color→encode pipeline order (Task 11), chunked processing (Task 11's `compute_windows`), compare mode + HTML report (Tasks 13-14), normal-mode publish to pCloud + Jellyfin (Task 12), pluggable backends (Tasks 7-10). Secure mode is intentionally out of scope for this plan (see Global Constraints) and will be its own follow-up plan.
- **Placeholder scan:** no TBD/TODO; Task 16 is explicitly manual (not fake-automated) because it requires hardware this plan cannot control.
- **Type consistency:** `UpscaleBackend.upscale(frames_in, frames_out, scale, model)` signature is identical across the Protocol (Task 7) and all three concrete backends (Tasks 8-10) and how `pipeline.py` calls it (Task 11). `JobConfig` fields are consistent from Task 3 through every later consumer (Tasks 11-15).
