from pathlib import Path

import pytest
from PIL import Image

from jutsu.html_report import grab_frame
from jutsu.media import (
    assemble_and_color,
    concat_segments,
    extract_and_clean,
    extract_clip,
    mux_audio,
    pad_to_resolution,
    probe,
)
from jutsu.profiles import CleanupSettings, ColorSettings


def test_probe_reads_duration_and_resolution(sample_clip):
    info = probe(sample_clip)
    assert 2.9 <= info.duration <= 3.1
    assert info.width == 64
    assert info.height == 48
    assert info.has_audio is True


def test_probe_failure_includes_ffprobe_stderr(tmp_path):
    bad_file = tmp_path / "not_a_video.mp4"
    bad_file.write_text("this is not a video file")

    with pytest.raises(Exception) as exc_info:
        probe(bad_file)

    message = str(exc_info.value)
    # Must surface actual ffprobe diagnostic text, not just a bare exit code
    # (subprocess.CalledProcessError's default __str__ only shows the code).
    assert any(
        keyword in message.lower()
        for keyword in ("invalid data", "moov", "error", "could not")
    ), f"expected real ffprobe error text in message, got: {message!r}"


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


def test_pad_to_resolution_fits_without_distortion_and_pads_with_black(sample_clip, tmp_path):
    # sample_clip is 64x48 (4:3). Padding into a 128x128 canvas is
    # width-constrained (scale factor 2.0 on both axes since 128/64 == 2.0 <
    # 128/48 == 2.667), so the real content lands at exactly 128x96,
    # centered, with black bars filling the remaining 16px top and bottom.
    # A scale that distorted the aspect ratio instead of padding would
    # stretch content into those bars instead of leaving them black.
    output = tmp_path / "padded.mp4"
    pad_to_resolution(sample_clip, width=128, height=128, output=output)

    info = probe(output)
    assert info.width == 128
    assert info.height == 128

    frame_path = tmp_path / "frame.png"
    grab_frame(output, timestamp=0.5, out_png=frame_path)
    with Image.open(frame_path) as img:
        img = img.convert("RGB")
        top_bar = img.getpixel((64, 4))
        bottom_bar = img.getpixel((64, 123))
        content_center = img.getpixel((64, 64))

    def is_near_black(pixel):
        return all(channel < 10 for channel in pixel)

    assert is_near_black(top_bar), f"expected black padding at top, got {top_bar}"
    assert is_near_black(bottom_bar), f"expected black padding at bottom, got {bottom_bar}"
    assert not is_near_black(content_center), "expected real (non-black) content at center"
