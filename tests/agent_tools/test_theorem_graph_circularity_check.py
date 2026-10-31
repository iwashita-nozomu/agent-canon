# @dependency-start
# contract test
# responsibility Checks theorem-graph circularity, leaf-origin, and forbidden reachability reports.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/theorem_graph_circularity_check.rs owns the native checker.
# @dependency-end

"""Independent CLI oracles for theorem graph proof-frontier checks."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import cast

AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def _native_cli() -> Path:
    assert AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
    executable = Path(AGENT_CANON_CLI)
    assert executable.is_absolute() and executable.is_file() and os.access(executable, os.X_OK)
    return executable


def _graph() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "root", "kind": "theorem", "status": "open"},
            {"id": "middle", "kind": "theorem", "status": "checked"},
            {"id": "leaf", "kind": "assumption", "status": "unverified", "origin": "external"},
            {"id": "forbidden", "kind": "axiom", "status": "admitted", "origin": "human"},
            {"id": "cycle_a", "kind": "lemma"},
            {"id": "cycle_b", "kind": "lemma"},
            {"id": "equiv_a", "kind": "lemma"},
            {"id": "equiv_b", "kind": "lemma"},
            {"id": "diagnostic", "kind": "theorem"},
        ],
        "edges": [
            {"source": "root", "target": "middle", "kind": "supports"},
            {"source": "middle", "target": "leaf", "kind": "supports"},
            {"source": "middle", "target": "root", "kind": "back_edge"},
            {"source": "root", "target": "forbidden", "kind": "requires"},
            {"source": "cycle_a", "target": "cycle_b", "kind": "derived"},
            {"source": "cycle_b", "target": "cycle_a", "kind": "derived"},
            {"source": "equiv_a", "target": "equiv_b", "kind": "equivalent_to"},
            {"source": "equiv_b", "target": "equiv_a", "kind": "equivalent_to"},
            {"source": "root", "target": "diagnostic", "kind": "diagnostic_projection"},
            {"source": "root", "target": "diagnostic", "kind": "supports", "status": "projection_only"},
        ],
        "circularity_checks": [
            {
                "id": "root-exit",
                "start": "root",
                "via_edge_kinds": ["supports", "back_edge"],
                "forbidden_reachable_kinds": ["theorem"],
                "severity": "error",
                "explanation": "The configured route may not reach another theorem node.",
            }
        ],
        "leaf_origin_checks": [
            {
                "id": "leaf-provenance",
                "start": "root",
                "via_edge_kinds": ["supports"],
                "allowed_origins": ["formal"],
                "allowed_statuses": ["verified"],
                "forbidden_status_terms": ["unverified"],
            }
        ],
        "forbidden_reachability_checks": [
            {
                "id": "no-axiom-route",
                "start": "root",
                "via_edge_kinds": ["requires"],
                "forbidden_node_kinds": ["axiom"],
                "forbidden_status_terms": ["admitted"],
                "allowed_node_kinds": ["theorem"],
            }
        ],
    }


def test_native_report_preserves_proof_frontier_checks_and_exit_contract(tmp_path: Path) -> None:
    graph_path = tmp_path / "theorem-graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    result = subprocess.run(
        [
            str(_native_cli()),
            "theorem-graph-circularity-check",
            "--graph",
            str(graph_path),
            "--format",
            "json",
            "--fail-on-finding",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    report = cast(dict[str, object], json.loads(result.stdout))
    assert report["status"] == "found"
    assert report["check_count"] == 1
    assert report["findings"] == [
        {
            "check_id": "root-exit",
            "start": "root",
            "reached": "middle",
            "reached_kind": "theorem",
            "path": ["root", "middle"],
            "edge_kinds": ["supports"],
            "severity": "error",
            "explanation": "The configured route may not reach another theorem node.",
        }
    ]
    assert report["directed_cycles"] == [
        ["cycle_a", "cycle_b", "cycle_a"],
        ["middle", "root", "middle"],
    ]
    leaf_findings = cast(list[dict[str, object]], report["leaf_origin_findings"])
    assert [(finding["leaf"], finding["leaf_status"], finding["path"]) for finding in leaf_findings] == [
        ("leaf", "unverified", ["root", "middle", "leaf"])
    ]
    reach_findings = cast(list[dict[str, object]], report["forbidden_reachability_findings"])
    assert [(finding["reached"], finding["reached_kind"], finding["reached_status"]) for finding in reach_findings] == [
        ("forbidden", "axiom", "admitted")
    ]


def test_native_markdown_and_text_modes_keep_documentation_and_summary_markers(tmp_path: Path) -> None:
    graph_path = tmp_path / "theorem-graph.json"
    output_path = tmp_path / "report.md"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    markdown = subprocess.run(
        [
            str(_native_cli()),
            "theorem-graph-circularity-check",
            "--graph",
            str(graph_path),
            "--out",
            str(output_path),
            "--format",
            "markdown",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert markdown.stdout == ""
    rendered = output_path.read_text(encoding="utf-8")
    assert "# Theorem Graph Circularity Check" in rendered
    assert "theorem_graph_circularity_check.rs" in rendered
    assert "## Directed Cycles" in rendered

    text_report = subprocess.run(
        [str(_native_cli()), "theorem-graph-circularity-check", "--graph", str(graph_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "THEOREM_GRAPH_CIRCULARITY=found\n" in text_report.stdout
    assert "THEOREM_GRAPH_LEAF_ORIGIN_FINDINGS=1\n" in text_report.stdout
    assert "THEOREM_GRAPH_FORBIDDEN_REACHABILITY_FINDINGS=1\n" in text_report.stdout
