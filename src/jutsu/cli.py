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
        Variant(label="realcugan", backend="realcugan", model="models-se", scale=config.scale),
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
