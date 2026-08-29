#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Finds similar design documents and emits only external consolidation evidence.
# upstream design ../README.md shared tool index
# upstream implementation ./_runtime_output.py external output boundary
# downstream design ../../documents/design/README.md documents design placement
# @dependency-end
"""Detect similar design documents without writing into the source checkout."""

from __future__ import annotations

import argparse
import difflib
import itertools
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactError  # noqa: E402
from tools.analysis.documents.formatting._runtime_output import (  # noqa: E402
    add_runtime_output_arguments,
    external_output,
    output_value,
)


def normalize_text(text: str) -> str:
    """Normalize Markdown for conservative pairwise comparison."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"[#>*`-]", " ", text)
    return " ".join(text.split()).lower()


def read_files(design_dir: Path) -> list[Path]:
    """Return deterministic Markdown inputs."""
    return sorted(
        path
        for path in design_dir.rglob("*.md")
        if path.is_file()
        and "template" not in path.name.casefold()
        and not path.name.endswith(".bak")
    )


def similarity(a: str, b: str) -> float:
    """Return sequence similarity."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def main(argv: list[str] | None = None) -> int:
    """Run design similarity analysis and publish one external report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design-root",
        default=str(Path("documents") / "design"),
        help="Read-only design root (defaults to documents/design).",
    )
    parser.add_argument("--min", type=float, default=0.6)
    add_runtime_output_arguments(parser)
    args = parser.parse_args(argv)

    source_root = Path.cwd().resolve()
    design_dir = Path(args.design_root).expanduser().resolve()
    if not design_dir.is_dir():
        parser.error(f"design root is not a directory: {design_dir}")
    if not 0.0 <= args.min <= 1.0:
        parser.error("--min must be between 0 and 1")
    try:
        boundary, target = external_output(
            source_root,
            args.runtime_root,
            category="similar-designs",
            filename="similar_designs_report.txt",
            output=args.output,
        )
        files = read_files(design_dir)
        texts = {
            path: normalize_text(path.read_text(encoding="utf-8")) for path in files
        }
        pairs: list[tuple[float, Path, Path]] = []
        for first, second in itertools.combinations(files, 2):
            score = similarity(texts[first], texts[second])
            if score >= args.min:
                pairs.append((score, first, second))
        pairs.sort(reverse=True)
        if not pairs:
            lines = [f"No similar design files found with threshold >= {args.min}"]
        else:
            lines = [f"Similar design file pairs (threshold >= {args.min})"]
            lines.extend(
                f"{score:.3f}  {first}  {second}" for score, first, second in pairs
            )
        boundary.atomic_write_text(output_value(target, boundary), "\n".join(lines) + "\n")
    except (RuntimeArtifactError, OSError) as exc:
        parser.error(f"runtime_or_input_error: {exc}")
    print(f"Report written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
