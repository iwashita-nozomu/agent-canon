#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Proposes conservative design-document organization and requires explicit capability for source changes.
# upstream design ../../../README.md shared tool index
# upstream implementation ../../../analysis/documents/formatting/_runtime_output.py external output and mutation capability boundary
# downstream design ../../../../documents/design/README.md documents design placement
# @dependency-end
"""Plan design-document organization without implicit source mutation.

The default operation only reads ``documents/design`` and writes a report to
an external runtime root. ``--apply`` is a distinct source mutation route and
requires an exact typed ``--mutation-capability-json`` covering every target.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
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


def detect_submodule(text: str) -> str | None:
    """Infer one safe top-level organization name from an explicit code path."""
    match = re.search(r"`([^`/]+/[^`]+(?:/[^`]*)?)`", text)
    if not match:
        return None
    parts = match.group(1).split("/")
    if not parts:
        return None
    candidate = parts[1] if parts[0] == "python" and len(parts) > 1 else parts[0]
    if candidate in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", candidate):
        return None
    return candidate


def plans(design_dir: Path) -> list[tuple[Path, Path, str]]:
    """Return source-to-target organization proposals without creating paths."""
    proposals: list[tuple[Path, Path, str]] = []
    for source in sorted(design_dir.rglob("*.md")):
        if not source.is_file() or "templates" in source.parts:
            continue
        relative = source.relative_to(design_dir)
        if len(relative.parts) >= 2:
            continue
        text = source.read_text(encoding="utf-8")
        submodule = detect_submodule(text)
        if submodule is None:
            proposals.append((source, source, "unresolved"))
            continue
        target = design_dir / submodule / source.name
        proposals.append((source, target, "planned"))
    return proposals


def main(argv: list[str] | None = None) -> int:
    """Produce an external organization report and optionally apply it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--design-root",
        default=str(Path("documents") / "design"),
        help="Read-only design root (defaults to documents/design).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy proposals into source; requires an explicit mutation capability.",
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
        proposal_rows = plans(design_dir)
        capability = (
            MutationCapability.from_json(source_root, args.mutation_capability_json)
            if args.apply
            else None
        )
        if args.apply and capability is None:
            raise MutationCapabilityError(
                "--apply requires --mutation-capability-json; planning is read-only by default"
            )
        actionable = [(source, target) for source, target, status in proposal_rows if status == "planned"]
        # Establish the external report capability before any source mutation.
        boundary, output_path = external_output(
            source_root,
            args.runtime_root,
            category="design-organization",
            filename="design_organize_report.txt",
            output=args.output,
        )
        if args.apply and capability is not None:
            # Validate the complete write set before the first directory or
            # file mutation. Existing target symlinks are rejected by the
            # capability boundary.
            for _source, target in actionable:
                capability.assert_allowed(target)
            for source, target in actionable:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)

        lines: list[str] = []
        for source, target, status in proposal_rows:
            if status == "unresolved":
                lines.append(f"UNRESOLVED (no explicit code path): {source}")
            elif args.apply:
                lines.append(f"COPIED {source} -> {target}")
            else:
                lines.append(f"PROPOSE {source} -> {target}")
        submodules = sorted(
            target.parent.name for _source, target, status in proposal_rows if status == "planned"
        )
        lines.extend(["", "Detected submodules:"])
        lines.extend(f" - {name}" for name in sorted(set(submodules)))
        report = "\n".join(lines) + "\n"
        boundary.atomic_write_text(output_value(output_path, boundary), report)
    except (RuntimeArtifactError, MutationCapabilityError, OSError) as exc:
        parser.error(f"runtime_or_mutation_error: {exc}")
    print(f"Report written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
