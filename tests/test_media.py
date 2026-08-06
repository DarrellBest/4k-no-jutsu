import subprocess
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


def test_concat_segments_batches_large_inputs(sample_clip, tmp_path):
    # Real production defect: ffmpeg's concat demuxer + `-c copy` becomes
    # unreliable (observed: hangs indefinitely, non-monotonic DTS) once it's
    # stream-copying roughly 1000+ independently-encoded segments in one
    # process. The fix batches segments into groups, re-encodes each batch
    # (which resolves the timestamp corruption -- a fresh encode generates
    # clean, consistent timestamps regardless of input quirks), then does a
    # final lightweight -c copy concat of the small number of clean batches.
    #
    # This test exercises the batching CODE PATH (correct grouping, correct
    # stitching, temp cleanup) at a small, fast scale via batch_size=3 --
    # it does NOT reproduce the real ffmpeg-level defect itself (verified
    # directly: that only manifests with ~100+ genuinely independent
    # encodes, impractical for a fast unit test). The real defect fix was
    # verified against real production content (see git history / README).
    frames_dir = tmp_path / "frames"
    extract_and_clean(sample_clip, start=0.0, duration=1.0, cleanup=CleanupSettings(), frames_dir=frames_dir)

    segments = []
    for i in range(7):
        segment = tmp_path / f"segment{i}.mp4"
        assemble_and_color(frames_dir, fps=10.0, color=ColorSettings(), output=segment)
        segments.append(segment)

    single_segment_duration = probe(segments[0]).duration

    output = tmp_path / "concatenated.mp4"
    concat_segments(segments, output, batch_size=3)

    assert output.exists()
    output_info = probe(output)
    expected_duration = single_segment_duration * len(segments)
    assert abs(output_info.duration - expected_duration) < 0.5, (
        f"expected ~{expected_duration}s (7 x {single_segment_duration}s), got {output_info.duration}s"
    )

    batch_dir = output.parent / f"{output.stem}_concat_batches"
    assert not batch_dir.exists(), "temp batch directory must be cleaned up after concat"


def test_concat_segments_small_input_unchanged(sample_clip, tmp_path):
    # Below the batch threshold, behavior must be identical to before:
    # a single direct -c copy concat, no batching overhead.
    frames_dir = tmp_path / "frames"
    extract_and_clean(sample_clip, start=0.0, duration=1.0, cleanup=CleanupSettings(), frames_dir=frames_dir)
    segment = tmp_path / "segment.mp4"
    assemble_and_color(frames_dir, fps=10.0, color=ColorSettings(), output=segment)

    output = tmp_path / "concatenated.mp4"
    concat_segments([segment], output)

    assert output.exists()
    batch_dir = output.parent / f"{output.stem}_concat_batches"
    assert not batch_dir.exists(), "small inputs must not go through the batching path"


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


def test_pad_to_resolution_preserves_duration_on_concatenated_variable_rate_input(tmp_path):
    # Motivated by a real defect found on a full-movie production run: on a
    # concatenation of many per-window segments (each assembled at a
    # slightly different real fps, computed from actual extracted frame
    # count), ffmpeg's default CFR-conforming re-encode silently
    # duplicated/dropped frames instead of preserving real timing --
    # ~90 minutes of real content shrank to ~83 minutes with no error or
    # warning. Fixed via -fps_mode passthrough.
    #
    # NOTE: this 3-segment synthetic fixture does NOT reliably reproduce
    # the defect on its own -- verified directly that this assertion passes
    # even without the fix at this small scale (the real repro needed
    # ~100+ genuinely independently-encoded segments, impractical for a
    # fast unit test). Keep this as a basic duration-preservation sanity
    # check, not proof the fps_mode fix is load-bearing; the real coverage
    # for this class of defect is the production verification recorded in
    # git history (commits around the Task 16 real-hardware run).
    segments = []
    for i, rate in enumerate([9, 10, 11]):
        segment = tmp_path / f"segment{i}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration=2:size=64x48:rate={rate}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(segment),
            ],
            check=True, capture_output=True,
        )
        segments.append(segment)

    concatenated = tmp_path / "concatenated.mp4"
    concat_segments(segments, concatenated)
    concatenated_info = probe(concatenated)

    output = tmp_path / "padded.mp4"
    pad_to_resolution(concatenated, width=128, height=128, output=output)
    output_info = probe(output)

    assert abs(output_info.duration - concatenated_info.duration) < 0.5, (
        f"expected padded output duration to match input ({concatenated_info.duration}s), "
        f"got {output_info.duration}s -- frames were likely duplicated/dropped to conform "
        f"to a declared frame rate that doesn't match the real content rate"
    )
