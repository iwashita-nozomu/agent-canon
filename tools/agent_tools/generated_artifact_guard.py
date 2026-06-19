#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Rejects mechanically regenerated report artifacts left in the source tree.
# upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md canonical artifact placement policy
# upstream design ../../agents/templates/closeout_gate.md closeout evidence template
# upstream design ../../tools/README.md shared tool index
# upstream design ../../documents/tools/README.md user-facing tool index
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream implementation ./report_artifact_checks.py classifies generated report paths
# downstream implementation ../ci/check_agent_canon_pr.sh runs this guard in PR validation
# downstream implementation ../../tests/agent_tools/test_generated_artifact_guard.py verifies guard behavior
# @dependency-end
"""Fail when mechanically regenerated report artifacts remain in the tree."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_artifact_checks import (  # noqa: E402
    generated_report_artifact_blockers,
    join_artifact_blockers,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Run the generated artifact guard."""
    root = Path(str(args.root)).resolve()
    blockers = generated_report_artifact_blockers(root)
    print(f"GENERATED_ARTIFACT_GUARD={'fail' if blockers else 'pass'}")
    print(f"GENERATED_ARTIFACT_BLOCKERS={join_artifact_blockers(blockers)}")
    if blockers:
        print(
            "GENERATED_ARTIFACT_NEXT="
            "delete_regeneratable_report_outputs_or_write_durable_evidence_to_"
            "documents_agents_notes_with_dependency_manifest"
        )
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
