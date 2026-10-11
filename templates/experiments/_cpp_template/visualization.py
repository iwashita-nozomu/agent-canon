"""Render the native run's raw output without owning execution or configuration."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


def render(raw_dir: Path, output_path: Path) -> Path:
    """Write one static HTML view of the native output artifact."""
    sources = sorted(
        path
        for path in raw_dir.iterdir()
        if path.is_file()
        and (path.name == "native-output.txt" or path.name.endswith(".stdout.txt"))
    )
    if not sources:
        raise FileNotFoundError(f"native output is missing from: {raw_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sections = "\n".join(
        f"<section><h2>{escape(source.name)}</h2><pre>"
        f"{escape(source.read_text(encoding='utf-8'))}</pre></section>"
        for source in sources
    )
    output_path.write_text(
        "<!doctype html>\n"
        "<html lang=\"en\"><meta charset=\"utf-8\"><title>Native result</title>"
        f"{sections}</html>\n",
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(render(args.raw_dir, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
