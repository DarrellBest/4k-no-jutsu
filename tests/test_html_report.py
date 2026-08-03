import pytest

from jutsu.html_report import build_comparison_html, grab_frame


def test_grab_frame_writes_png(sample_clip, tmp_path):
    out = tmp_path / "frame.png"
    grab_frame(sample_clip, timestamp=1.0, out_png=out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_grab_frame_raises_for_timestamp_past_duration(sample_clip, tmp_path):
    # ffmpeg -ss past EOF exits 0 and writes no PNG, so a bare check=True
    # gives no protection; grab_frame must detect and raise explicitly.
    out = tmp_path / "frame.png"
    with pytest.raises(RuntimeError, match="no frame"):
        grab_frame(sample_clip, timestamp=999.0, out_png=out)


def test_build_comparison_html_includes_all_variants_and_timestamps(sample_clip, tmp_path):
    variants = {"original": sample_clip, "fast": sample_clip}
    html = build_comparison_html(variants, timestamps=[0.5, 1.5], workdir=tmp_path / "frames")

    assert "original" in html
    assert "fast" in html
    assert "0.5" in html
    assert "1.5" in html
    assert html.count("data:image/png;base64,") == 4  # 2 variants x 2 timestamps
