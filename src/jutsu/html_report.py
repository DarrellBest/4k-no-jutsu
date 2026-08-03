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
