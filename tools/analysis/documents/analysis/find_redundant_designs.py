#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Finds exact duplicate design documents and emits only external consolidation evidence.
# upstream design ../README.md shared tool index
# upstream implementation ./_runtime_output.py external output and mutation capability boundary
# downstream design ../../documents/design/README.md documents design placement
# @dependency-end
"""Detect exact-duplicate design documents.

The analyzer is read-only by default. Reports are runtime artifacts and
therefore require an explicit external runtime root (or its explicitly
configured environment capability). ``--delete`` is a separate source
mutation operation and requires an exact typed ``--mutation-capability-json``.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactError  # noqa: E402
from tools.analysis.documents.formatting._runtime_output import (  # noqa: E402
    MutationCapability,
    MutationCapabilityError,
    add_runtime_output_arguments,
    external_output,
    output_value,
)


def normalize(text: str) -> str:
    """Normalize whitespace without changing document meaning."""
    return " ".join(text.split())


def sha(text: str) -> str:
    """Return the duplicate-group digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_md_files(design_dir: Path) -> list[Path]:
    """Return source design files, excluding templates and backup files."""
    if not design_dir.is_dir():
        return []
    return sorted(
        path
        for path in design_dir.rglob("*.md")
        if path.is_file()
        and "template" not in path.name.casefold()
        and not path.name.endswith(".bak")
    )


def choose_canonical(paths: list[Path], design_dir: Path) -> Path:
    """Choose a deterministic canonical document without mutating anything."""
    subs = [path for path in paths if len(path.relative_to(design_dir).parts) >= 2]
    pool = subs or paths
    return sorted(
        pool,
        key=lambda path: (len(path.relative_to(design_dir).parts), path.as_posix()),
    )[0]


def build_report(
    design_dir: Path,
    *,
    delete: bool,
    capability: MutationCapability | None,
) -> tuple[str, list[Path]]:
    """Build a report and return the exact source paths eligible for deletion."""
    groups: dict[str, list[Path]] = {}
    for path in find_md_files(design_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeArtifactError(f"cannot read design document: {path}") from exc
        groups.setdefault(sha(normalize(text)), []).append(path)

    lines: list[str] = []
    deletions: list[Path] = []
    for paths in groups.values():
        if len(paths) <= 1:
            continue
        lines.append("DUP_GROUP:")
        for path in paths:
            lines.append(f"  {path}")
        canonical = choose_canonical(paths, design_dir)
        lines.append(f"  KEEP: {canonical}")
        for path in paths:
            if path == canonical:
                continue
            lines.append(f"  DELETE: {path}")
            deletions.append(path)
        lines.append("")
    if not lines:
        lines = ["No exact-duplicate design files found."]

    if delete:
        if capability is None:
            raise MutationCapabilityError(
                "--delete requires --mutation-capability-json; analysis is read-only by default"
            )
        # Validate every target before the first unlink so a partial mutation
        # cannot be caused by a malformed or incomplete capability.  The
        # caller performs the unlink only after the external output capability
        # has also been established.
        for path in deletions:
            capability.assert_allowed(path)
        lines.extend(["", "DELETED:"])
        lines.extend(str(path) for path in deletions)
    return "\n".join(lines) + "\n", deletions


def main(argv: list[str] | None = None) -> int:
    """Run duplicate detection with explicit runtime and mutation boundaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design-root",
        default=str(Path("documents") / "design"),
        help="Read-only design root (defaults to documents/design).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete redundant source files; requires an explicit mutation capability.",
    )
    parser.add_argument(
        "--mutation-capability-json",
        help="Exact typed source mutation capability JSON.",
    )
    add_runtime_output_arguments(parser)
    args = parser.parse_args(argv)

    source_root = Path.cwd().resolve()
    design_dir = Path(args.design_root).expanduser().resolve()
    if not design_dir.is_dir():
        parser.error(f"design root is not a directory: {design_dir}")
    try:
        capability = (
            MutationCapability.from_json(source_root, args.mutation_capability_json)
            if args.delete
            else None
        )
        report, deletions = build_report(
            design_dir, delete=args.delete, capability=capability
        )
        boundary, target = external_output(
            source_root,
            args.runtime_root,
            category="redundant-designs",
            filename="redundant_designs.txt",
            output=args.output,
        )
        # Do not touch source until both the typed mutation grant and the
        # explicit external report destination have been admitted.
        if args.delete:
            for path in deletions:
                path.unlink()
        boundary.atomic_write_text(output_value(target, boundary), report)
    except (RuntimeArtifactError, MutationCapabilityError) as exc:
        parser.error(f"runtime_or_mutation_error: {exc}")
    print(f"Report written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
