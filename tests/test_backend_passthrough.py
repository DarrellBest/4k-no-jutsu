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
