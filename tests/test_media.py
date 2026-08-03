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
