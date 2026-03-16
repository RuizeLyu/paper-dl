"""Command-line interface for paper-dl."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from paper_dl import __version__
from paper_dl.downloader import download_papers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-dl",
        description=(
            "Download arxiv PDFs from pasa search results.\n"
            "Batch-download papers exported by pasa into a local PDF library."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  paper-dl results.json\n"
            "  paper-dl results.json -o ./my_papers\n"
            "  paper-dl results.json -c 5\n"
        ),
    )
    parser.add_argument("json_file", type=Path, help="pasa-format JSON file to process")
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        metavar="DIR",
        help="output directory (default: <json_file stem>/)",
    )
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=3,
        metavar="N",
        help="number of concurrent downloads (default: 3)",
    )
    parser.add_argument(
        "-r", "--retries",
        type=int,
        default=3,
        metavar="N",
        help="max retry attempts per paper (default: 3)",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"paper-dl {__version__}",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    json_path: Path = args.json_file
    if not json_path.is_file():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    if json_path.suffix.lower() != ".json":
        print(f"Warning: expected a .json file, got: {json_path.name}")

    if args.concurrency < 1:
        print("Error: concurrency must be >= 1", file=sys.stderr)
        sys.exit(1)

    if args.retries < 1:
        print("Error: retries must be >= 1", file=sys.stderr)
        sys.exit(1)

    download_papers(
        json_path=json_path,
        output_dir=args.output,
        concurrency=args.concurrency,
        retries=args.retries,
    )


if __name__ == "__main__":
    main()
