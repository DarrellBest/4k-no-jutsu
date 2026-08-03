# 4k-no-jutsu: AI video upscaling pipeline

Status: approved
Date: 2026-08-03

## Purpose

A config-driven pipeline that takes a source video, cleans it up, upscales it
to 4K with an AI super-resolution model, color-corrects it, and produces
either a normal output (uploaded to pCloud + copied into the Jellyfin media
library) or a "secure mode" output (processed with no plaintext trace on
disk, final file written straight into a VeraCrypt vault).

First use case is a pair of Naruto videos currently sitting in a pCloud
`Naruto` folder, but the pipeline is not anime-specific — content-type
profiles make it usable for other video types too.

## Non-goals

- Not reimplementing super-resolution neural networks. We call existing
  pretrained, Vulkan-accelerated inference binaries (`realesrgan-ncnn-vulkan`,
  `realcugan-ncnn-vulkan`) as swappable backends. What we own is the
  orchestration around them: frame extraction/batching, temp-file lifecycle,
  model selection, cleanup/color processing, comparison generation, and
  secure-mode handling.
- Not a GUI. CLI/config-file driven.
- Not real-time/streaming playback upscaling (e.g. Anime4K-style live
  shader upscaling during playback) — this is an offline batch pipeline.

## Architecture

```
                 ┌───────────────────────────────────────────────┐
                 │                 job config (YAML)              │
                 └───────────────────────────────────────────────┘
                                      │
   source (local file or pCloud) ────┼──────────────────────────────┐
                                      ▼                              │
                              ┌───────────────┐                      │
                              │   download     │  (skipped if local) │
                              └───────┬───────┘                      │
                                      ▼                              │
                    ┌─────────────────────────────────┐              │
                    │  chunked processing loop          │             │
                    │  (window of N seconds at a time)  │             │
                    │                                    │            │
                    │  extract frames (ffmpeg)           │            │
                    │        │                           │            │
                    │        ▼                           │            │
                    │  cleanup: denoise/deblock/deband    │            │
                    │        │                           │            │
                    │        ▼                           │            │
                    │  AI upscale (realesrgan/realcugan) │            │
                    │        │                           │            │
                    │        ▼                           │            │
                    │  color correct (fixed filter chain) │           │
                    │        │                           │            │
                    │        ▼                           │            │
                    │  encode + append to output          │           │
                    └─────────────────┬─────────────────┘             │
                                      ▼                              │
                    normal mode: /mnt/4tb scratch → pCloud + Jellyfin│
                    secure mode: ramfs scratch → VeraCrypt vault  ◄──┘
```

## Components

### Job config (YAML)

One file per job. Fields:

- `source`: local path or pCloud path
- `profile`: `anime` | `live-action` (extensible) — selects default model +
  cleanup + color settings
- `model`: backend + model name + scale factor (overrides profile default)
- `cleanup`: denoise/deblock/deband filter strengths (overrides profile
  default)
- `color`: fixed correction parameters (eq/curves/colorbalance values),
  chosen once per job from representative sample frames and applied
  uniformly across the whole video — this is what guarantees frame-to-frame
  consistency, not per-frame auto-adjustment
- `mode`: `normal` | `secure`
- `output`: naming/destination overrides

### Orchestrator (Python)

Owns the chunked processing loop, calls ffmpeg and the ncnn-vulkan binaries
as subprocesses, tracks job state for resumability, and enforces the
secure-mode preflight checks below.

### Inference backends

- `realesrgan-ncnn-vulkan` — general + anime-tuned model
- `realcugan-ncnn-vulkan` — anime-specialized
- Vulkan-based, so no CUDA-version matching against the host driver;
  extensible to add more backends per profile later.

### Compare mode

Given a source and a short time range:

1. Extract the original clip for that range.
2. Run the full pipeline on that clip once per (model, settings) combination
   in the comparison matrix.
3. Output labeled sample clips (`sample_original.mp4`,
   `sample_realcugan_x4.mp4`, etc.) for playback in a normal media player.
4. Generate an HTML comparison page: a grid of frame crops from the same
   timestamps across original + each variant, embedded as data URIs,
   published as a Claude Code artifact for quick visual triage before
   committing to a full-length run.

## Pipeline order

`download → cleanup → AI upscale → color correct → encode`

Cleanup runs before upscaling so compression artifacts/noise are corrected
at native resolution rather than amplified by the upscaler. Color correction
runs last, as a single fixed filter chain per job.

## Chunked processing

The pipeline never materializes a full video's frames at once. It processes
in bounded windows (extract → upscale → encode → discard → next window).
This bounds memory/disk usage regardless of video length and is what makes
secure mode viable for full-length video without exceeding available RAM.

## Normal mode

- Scratch/working directory on `/mnt/4tb` (same disk as the other media
  services on this machine), not inside the git repo.
- Finished output uploaded to the pCloud `Naruto` folder (or configured
  destination) via the existing `pcloud:` rclone remote, and copied into
  the Jellyfin media library at `/mnt/4tb/JellyfinServer/media`.

## Secure mode

- Scratch space mounted as `ramfs`, not `tmpfs`. `ramfs` is never
  swap-backed by kernel design (pinned page cache with no path to disk),
  so this machine's system-wide swap does not need to be touched. Trade-off:
  the kernel enforces no size cap on `ramfs`, so the orchestrator must track
  usage against a configured cap itself and abort cleanly rather than let
  usage grow unbounded — mitigated by the chunked-processing bound (never
  more than one window of frames resident at a time).
- Source video is streamed directly into the `ramfs` mount — via `rclone`
  if it's on pCloud, via a read-only open if it's already local. It is
  never copied to regular disk at any point.
- Final encoded output is written directly into a mounted VeraCrypt volume.
  The vault mount is the encryption layer; there is no separate encrypt
  step. The vault is mounted only for the duration of writing output and
  unmounted immediately after (including on error, via try/finally).
- Job state/progress tracking (for resumability) also lives in `ramfs` in
  secure mode, never on regular disk.
- Mounting `ramfs` and the VeraCrypt volume both require root. The
  orchestrator does not use passwordless sudo for this — the user enters
  their sudo password interactively when a secure-mode job starts. This is
  intentional: secure mode is for sensitive content, and a conscious
  interactive unlock each time is preferable to unattended automation here.
- Preflight checks before a secure job is allowed to start:
  - `ramfs` mount succeeds at the configured scratch path
  - VeraCrypt volume mounts successfully with the supplied passphrase
  - required binaries (ffmpeg, realesrgan/realcugan, veracrypt) are present
  - if any check fails, the job refuses to start rather than falling back
    to a less-secure mode silently

## Error handling & resumability

- The orchestrator tracks per-window job state so a crash or interruption
  does not require reprocessing completed windows. In secure mode this
  state file lives in `ramfs` (lost on unmount/crash, which is acceptable —
  a secure job that's interrupted mid-run should not silently resume days
  later from leftover state).
- Preflight validation before any processing starts: input file exists and
  is readable by ffprobe, GPU/Vulkan is available, required binaries are
  present, sufficient disk/RAM is available for the configured window size.
- All subprocess (ffmpeg, ncnn-vulkan, mount/umount) output is logged to a
  per-job log file for debugging. Secure-mode logs avoid recording
  sensitive filenames/content in detail.
- `ramfs` and VeraCrypt unmounts happen in a `finally` block so a mid-job
  failure doesn't leave the vault open or scratch space mounted longer than
  necessary.

## Testing approach

- Config parsing, filter-chain construction, and pipeline stage logic can
  be unit tested without a GPU.
- End-to-end upscale runs require a working GPU (blocked on the pending
  driver-mismatch reboot on this machine) — noted as a known gap until
  that reboot happens.
- Compare-mode HTML generation can be tested against any short sample clip
  once the backends are installed.

## Prerequisites (setup, not code)

- Reboot the machine to resolve the current NVIDIA driver/library version
  mismatch (blocks all GPU-accelerated upscaling).
- Install `realesrgan-ncnn-vulkan` and `realcugan-ncnn-vulkan` binaries.
- Install `veracrypt-console` (official GPG-signed `.deb` from
  veracrypt.io, verified against the published key before install).
- One-time creation of the VeraCrypt vault, with the user setting the
  passphrase interactively (not generated or stored by the pipeline).

## Repository

- Local: `~/projects/4k-no-jutsu`
- GitHub: `DarrellBest/4k-no-jutsu`, private
