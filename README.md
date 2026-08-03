# 4k-no-jutsu

Config-driven pipeline for upscaling video to 4K with AI super-resolution,
cleaning up compression artifacts, and applying consistent color
correction. Supports comparing models/settings on short sample clips before
committing to a full run. A secure mode that leaves no plaintext trace on
disk is designed but not yet implemented (see Secure mode below).

Design details: [docs/superpowers/specs/2026-08-03-video-upscale-pipeline-design.md](docs/superpowers/specs/2026-08-03-video-upscale-pipeline-design.md)

## Pipeline

```mermaid
flowchart TD
    A[Source video<br/>local file or pCloud] --> B[Download / stream in]
    B --> C{Chunked processing loop<br/>one window of frames at a time}
    C --> D[Cleanup<br/>denoise / deblock / deband]
    D --> E[AI upscale<br/>realesrgan-ncnn-vulkan / realcugan-ncnn-vulkan]
    E --> F[Color correct<br/>fixed filter chain, same params every frame]
    F --> G[Encode + append]
    G --> C
    C -->|all windows done| H{Mode}
    H -->|normal| I[Upload to pCloud<br/>+ copy into Jellyfin library]
    H -->|secure| J[Write directly into<br/>mounted VeraCrypt vault]
```

Cleanup runs before upscaling so artifacts get fixed at native resolution
instead of being amplified by the upscaler. Color correction is a single
fixed set of parameters applied to the whole video, not a per-frame
auto-adjustment, so there's no flicker or drift between frames.

## Compare mode

Before committing to a full-length run, try several models/settings on a
short clip and compare them side by side:

```mermaid
flowchart LR
    A[Source video] --> B[Extract short clip]
    B --> C1[Pipeline run:<br/>model/setting A]
    B --> C2[Pipeline run:<br/>model/setting B]
    B --> C3[Pipeline run:<br/>model/setting C]
    C1 --> D[Labeled sample clips]
    C2 --> D
    C3 --> D
    B --> E[Original clip]
    E --> F[HTML comparison page<br/>frame-crop grid, same timestamps]
    C1 --> F
    C2 --> F
    C3 --> F
```

## Secure mode

For source video that should leave no plaintext trace on disk:

```mermaid
flowchart TD
    A[Source video] -->|streamed in, never written to regular disk| B[ramfs scratch space<br/>RAM-only, swap-immune]
    B --> C[Pipeline processing]
    C --> D[Mounted VeraCrypt vault]
    D -->|unmounted immediately after| E[Vault stays encrypted at rest]
```

`ramfs` (not `tmpfs`) is used for scratch space because it's never
swap-backed by the kernel, so the pipeline doesn't need system-wide swap
disabled. Mounting the vault and the `ramfs` scratch space both require an
interactive sudo prompt — secure mode is never run unattended.

**Not implemented yet.** This section describes the planned design; secure
mode is a deliberately separate follow-up plan and does not exist in this
codebase today. A job config with `mode: secure` is refused at the CLI
(non-zero exit, no processing) rather than silently falling back to normal
mode.

## Status

Normal mode, compare mode, and the CLI are implemented and tested (15
implementation tasks complete). Task 16, the manual post-reboot GPU
verification against real NVIDIA hardware, is still pending — blocked on a
pending reboot to fix an NVIDIA driver/library version mismatch on the host
machine. Secure mode is designed but not implemented (see the Secure mode
section above).

## Setup

```
conda activate 4k-no-jutsu
./scripts/install_backends.sh   # fetches the realesrgan/realcugan AI backends
```

The test suite runs the AI backends' ncnn-vulkan binaries, so it needs a
working Vulkan implementation. This works today even without a working GPU
driver, via software rendering (e.g. mesa lavapipe for CPU-only Vulkan).
