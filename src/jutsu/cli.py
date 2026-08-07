import argparse
from pathlib import Path

from jutsu.compare import Variant, run_compare
from jutsu.config import load_job_config
from jutsu.download import download_source
from jutsu.html_report import build_comparison_html
from jutsu.media import probe
from jutsu.pipeline import preflight, run_pipeline
from jutsu.publish import publish_normal
from jutsu.secure import DEFAULT_RAMFS_SIZE_MB, run_secure_pipeline

RESOLUTION_SHORTHANDS = {
    "4k": (3840, 2160),
    "uhd": (3840, 2160),
    "1080p": (1920, 1080),
    "720p": (1280, 720),
}


def parse_resolution(value: str) -> tuple[int, int]:
    shorthand = RESOLUTION_SHORTHANDS.get(value.strip().lower())
    if shorthand is not None:
        return shorthand
    parts = value.lower().split("x")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        width, height = int(parts[0]), int(parts[1])
        if width > 0 and height > 0:
            return (width, height)
    raise argparse.ArgumentTypeError(
        f"invalid resolution: {value!r} (expected e.g. '3840x2160', or one of: "
        f"{', '.join(sorted(RESOLUTION_SHORTHANDS))})"
    )


def cmd_run(args: argparse.Namespace) -> int:
    config = load_job_config(Path(args.config))

    if config.mode == "secure":
        if not args.vault_device or not args.vault_mount:
            raise SystemExit(
                "Secure mode requires --vault-device and --vault-mount "
                "(an existing VeraCrypt volume file and where to mount it). "
                "The vault itself must already exist -- create it once with "
                "the veracrypt CLI/GUI and set your own passphrase, this "
                "tool never generates or stores one."
            )
        output = run_secure_pipeline(
            config, config.source,
            ramfs_mount=Path(args.workdir),
            vault_device=Path(args.vault_device),
            vault_mount=Path(args.vault_mount),
            size_cap_mb=args.ramfs_size_mb,
            max_workers=args.max_workers,
            target_resolution=args.target_resolution,
        )
        print(f"Done: {output}")
        return 0

    workdir = Path(args.workdir)
    source = download_source(config.source, workdir / "downloaded_source")
    output = run_pipeline(
        config, source, workdir,
        max_workers=args.max_workers,
        target_resolution=args.target_resolution,
    )
    if config.mode == "normal" and not args.no_publish:
        publish_normal(output, config)
    print(f"Done: {output}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    config = load_job_config(Path(args.config))
    workdir = Path(args.workdir)
    source = download_source(config.source, workdir / "downloaded_source")

    # Must run before ANY plaintext intermediate is written. run_compare's
    # extract_clip writes clip_source.mp4 to plaintext disk before
    # run_pipeline (and therefore preflight, where the secure-mode check now
    # lives) is ever reached, so cmd_compare needs its own early call to the
    # same guard rather than relying on run_pipeline to catch it downstream.
    preflight(config, source, workdir)

    variants = [
        Variant(label="realcugan", backend="realcugan", model="models-se", scale=config.scale),
        Variant(label="realesrgan", backend="realesrgan", model="realesrgan-x4plus", scale=config.scale),
        Variant(label="passthrough", backend="passthrough", model="unused", scale=config.scale),
    ]

    # --start beyond (or too close to) the end of the source is a real,
    # observed failure mode: extract_clip's stream-copy extraction from a
    # start point at/past the source's own duration produces a container
    # that reports a nonzero duration via ffprobe but contains zero decodable
    # video frames, which fails deep inside the pipeline. Clamp start against
    # the source's own probed duration up front so extraction always has at
    # least one real frame to work with. This is also what makes the CLI's
    # own defaults (--start 60, --duration 15) usable against short sources.
    source_info = probe(source)
    source_frame_period = 1.0 / source_info.fps if source_info.fps > 0 else 0.1
    min_clip_length = max(0.05, source_frame_period * 1.5)
    start = max(0.0, min(args.start, max(0.0, source_info.duration - min_clip_length)))

    results = run_compare(config, source, variants, start, args.duration, workdir)

    # Clip-relative, not absolute-source-relative: run_compare extracts a clip
    # whose own internal timeline starts at 0, and build_comparison_html seeks
    # into that clip, not the source. Clamp against the clip's ACTUAL duration,
    # not the requested args.duration: the extraction uses stream copy, so the
    # real clip is often shorter than requested (source ends early, or keyframe
    # snapping truncates it).
    original_info = probe(results["original"])
    actual_duration = original_info.duration
    # A flat epsilon is not safe: a timestamp can be less than the clip's
    # reported duration and still land after the last frame's actual
    # presentation time, which yields no frame at all (verified empirically:
    # at 10fps/1.0s duration, ts=0.90 succeeds but ts=0.91 fails, since the
    # last frame's timestamp is 0.9). The safety margin needs to be at least
    # one frame period, so derive it from the clip's own frame rate instead
    # of guessing a small constant.
    frame_period = 1.0 / original_info.fps if original_info.fps > 0 else 0.1
    epsilon = max(0.05, frame_period * 1.5)
    upper_bound = max(0.0, actual_duration - epsilon)
    # Built from the clip's ACTUAL duration, not args.duration (the
    # requested one): when the real clip is shorter than requested (the
    # common case, per Critical 2's fix), building these from args.duration
    # made all three collapse to the same clamped upper_bound, silently
    # shrinking the report to one row instead of three.
    raw_timestamps = [1.0, actual_duration / 2, actual_duration - 1.0]
    timestamps = sorted({max(0.0, min(t, upper_bound)) for t in raw_timestamps})
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
    run_parser.add_argument("--max-workers", type=int, default=1)
    run_parser.add_argument(
        "--target-resolution", type=parse_resolution, default=None,
        help="Letterbox/pad the AI-upscaled output to an exact resolution, e.g. '3840x2160' or '4k'. "
             "AI backends only support fixed integer scale factors, so this is usually needed to land "
             "on a standard target size without distortion.",
    )
    run_parser.add_argument(
        "--vault-device", default=None,
        help="[secure mode only] path to an existing VeraCrypt volume file. Must already exist -- "
             "this tool never creates a vault or generates/stores a passphrase.",
    )
    run_parser.add_argument(
        "--vault-mount", default=None,
        help="[secure mode only] where to mount the VeraCrypt volume for the duration of writing output.",
    )
    run_parser.add_argument(
        "--ramfs-size-mb", type=int, default=DEFAULT_RAMFS_SIZE_MB,
        help=f"[secure mode only] ramfs scratch size cap in MiB, self-enforced since the kernel doesn't "
             f"cap ramfs (default: {DEFAULT_RAMFS_SIZE_MB}).",
    )
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
