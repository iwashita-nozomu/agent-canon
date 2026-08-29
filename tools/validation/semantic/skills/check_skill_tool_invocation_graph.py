#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks the generated v2 public skill/tool invocation graph and its Mermaid readback.
# upstream design ../../documents/design/skill-tool-invocation-graph.md owns checker obligations
# upstream implementation ./skill_dependency_map.py owns materialization and actual Mermaid parsing
# downstream implementation ../../tests/agent_tools/test_skill_dependency_map.py checks checker failures
# @dependency-end
"""Fail-closed checker for the generated skill/tool invocation graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skill_dependency_map import CHECK_SCHEMA, check_artifacts


def main(argv: list[str] | None = None) -> int:
    """Validate artifacts and print the typed checker envelope."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[4]
    )
    args = parser.parse_args(argv)
    try:
        graph = check_artifacts(args.root.resolve())
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {"schema": CHECK_SCHEMA, "status": "fail", "error": str(exc)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema": CHECK_SCHEMA,
                "status": "pass",
                "skill_count": graph["skill_count"],
                "command_count": len(graph["commands"]),
                "tool_count": len(graph["tools"]),
                "edge_count": len(graph["edges"]),
                "graph_digest": graph["graph_digest"],
                "json_digest": graph["json_digest"],
                "mermaid_digest": graph["mermaid_digest"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
