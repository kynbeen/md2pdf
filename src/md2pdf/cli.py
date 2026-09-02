"""
Command-line interface for md2pdf.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

from md2pdf.renderer import THEME_CHOICES, render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md2pdf",
        description="Render Markdown to high-quality PDF with refined typography and smart figure layout.",
    )
    parser.add_argument("input", help="Path to input Markdown (.md) file")
    parser.add_argument("-o", "--output", help="Path to output PDF file (default: [input].pdf)")
    parser.add_argument("--title", default="", help="Document title for header (default: auto-detected from # H1)")
    parser.add_argument(
        "--theme",
        default="custom",
        choices=THEME_CHOICES,
        help="Visual theme ('custom' with Pretendard typography, or 'github')",
    )
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="Disable automatic list indentation and block margin preprocessing",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass

    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None

    logger = (lambda *_: None) if args.quiet else print

    try:
        render(
            input_path=input_path,
            output_path=output_path,
            title=args.title,
            theme=args.theme,
            preprocess=not args.no_preprocess,
            log=logger,
        )
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
