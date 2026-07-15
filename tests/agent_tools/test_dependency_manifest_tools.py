# @dependency-start
# contract test
# responsibility Verifies graph-backed dependency shell consumers and code-relation producer input.
# upstream design ../../documents/dependency-manifest-design.md defines canonical graph consumer boundaries
# upstream implementation ../../tools/agent_tools/scan_dependency_headers.sh reports parser-owned manifest coverage
# upstream implementation ../../tools/agent_tools/check_dependency_header_format.sh validates graph context projections
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh validates canonical dependency facts
# upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh owns code relation extraction
# upstream implementation ../fixtures/knowledge_graph/graph_contract.jsonl canonical response fixture
# upstream implementation ../fixtures/knowledge_graph/context_evidence.jsonl canonical context fixture
# @dependency-end

"""Tests for dependency graph shell consumers and the code producer."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN_HEADERS = PROJECT_ROOT / "tools/agent_tools/scan_dependency_headers.sh"
FORMAT_HEADERS = PROJECT_ROOT / "tools/agent_tools/check_dependency_header_format.sh"
CHECK_GRAPH = PROJECT_ROOT / "tools/agent_tools/check_dependency_graph.sh"
SCAN_CODE = PROJECT_ROOT / "tools/agent_tools/scan_code_dependencies.sh"
GRAPH_CONTRACT_FIXTURE = (
    PROJECT_ROOT / "tests/fixtures/knowledge_graph/graph_contract.jsonl"
)
CONTEXT_EVIDENCE_FIXTURE = (
    PROJECT_ROOT / "tests/fixtures/knowledge_graph/context_evidence.jsonl"
)


def install_graph_fixture(root: Path) -> Path:
    """Install a deterministic graph CLI that records each exact operation."""
    executable = root / "tools/bin/agent-canon"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >>"${FAKE_GRAPH_CALLS:?}"
            operation="${2:-}"
            case "$operation" in
              status)
                cat <<'JSON'
            {"schema":"agent-canon.graph.status.v1","command":"status","status":"fresh","exit_code":0,"integration_record":{"verified":true,"profile":"default","source_snapshot_profile":"parent"}}
            JSON
                ;;
              query)
                cat <<'JSON'
            {"schema":"agent-canon.graph.query.v1","command":"query","status":"fresh","exit_code":0,"nodes":[{"id":"node-a","layer":"source","path":"docs/a.md","payload":{"manifest_present":true,"manifest_responsibility":"fixture"}},{"id":"node-b","layer":"source","path":"README.md","payload":{"manifest_present":true,"manifest_responsibility":"entrypoint"}}],"facts":[{"id":"fact-a","kind":"dependency","inferred":false,"from":"node-a","to":"node-b","payload":{"from_selector":"docs/a.md","to_selector":"README.md"},"dependency_detail":{"direction":"upstream","kind":"design","reason":"entrypoint"}}]}
            JSON
                ;;
              context)
                present="${FAKE_MANIFEST_PRESENT:-true}"
                if [[ "$present" == "true" ]]; then
                  items='[{"kind":"manifest.present","value":"true","source_store":"manifest","producer":"source-snapshot","source_path":"docs/a.md","authority":"ManifestParser"},{"kind":"manifest.contract","value":"design","source_store":"manifest","producer":"source-snapshot","source_path":"docs/a.md","authority":"ManifestParser"},{"kind":"manifest.responsibility","value":"fixture","source_store":"manifest","producer":"source-snapshot","source_path":"docs/a.md","authority":"ManifestParser"}]'
                else
                  items='[{"kind":"manifest.present","value":"false","source_store":"manifest","producer":"source-snapshot","source_path":"docs/a.md","authority":"ManifestParser"}]'
                fi
                printf '{"schema":"agent-canon.graph.context.v1","command":"context","status":"fresh","exit_code":0,"items":%s}\\n' "$items"
                ;;
              *) exit 2 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def run_shell(
    script: Path,
    *arguments: str,
    root: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one shell surface against the fixture root."""
    env = dict(os.environ)
    if environment:
        env.update(environment)
    return subprocess.run(
        ["bash", str(script), "--root", str(root), *arguments],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


class DependencyGraphConsumerTest(unittest.TestCase):
    """Verify fixed graph operations and source-owned scanner behavior."""

    def graph_root(self, temporary: str) -> tuple[Path, Path]:
        """Create one shell-consumer root and its graph-call ledger path."""
        root = Path(temporary)
        (root / "docs").mkdir()
        (root / "docs/a.md").write_text("# A\n", encoding="utf-8")
        (root / "README.md").write_text("# Root\n", encoding="utf-8")
        install_graph_fixture(root)
        calls = root / "graph-calls.txt"
        return root, calls

    def test_graph_contract_fixture_uses_only_public_response_schemas(self) -> None:
        """The compact fixture covers freshness, closure, diagnostics, and failure."""
        records = [
            json.loads(line)
            for line in GRAPH_CONTRACT_FIXTURE.read_text(encoding="utf-8").splitlines()
        ]

        self.assertEqual(
            [record["schema"] for record in records],
            [
                "agent-canon.graph.status.v1",
                "agent-canon.graph.query.v1",
                "agent-canon.graph.build.v1",
                "agent-canon.graph.build.v1",
            ],
        )
        self.assertEqual(records[0]["status"], "fresh")
        self.assertTrue(records[0]["integration_record"]["verified"])
        query_facts = records[1]["facts"]
        explicit = next(fact for fact in query_facts if not fact["inferred"])
        reverse = next(fact for fact in query_facts if fact["inferred"])
        self.assertEqual(reverse["id"], f"reverse:{explicit['id']}")
        self.assertEqual((reverse["from"], reverse["to"]), (explicit["to"], explicit["from"]))
        self.assertEqual(explicit["producer"], "source-snapshot")
        self.assertEqual(
            (records[2]["unresolved_count"], records[2]["ambiguous_count"]),
            (1, 1),
        )
        self.assertEqual(records[3]["publication"], "not-published")
        self.assertEqual(records[3]["durability"], "not-durable")

    def test_context_fixture_closes_owner_source_and_dependency_evidence(self) -> None:
        """Context evidence remains one canonical context response, not a side schema."""
        lines = CONTEXT_EVIDENCE_FIXTURE.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])

        self.assertEqual(record["schema"], "agent-canon.graph.context.v1")
        self.assertEqual(record["claim_path"], "docs/a.md")
        self.assertEqual(record["owner"], "role:designer")
        self.assertEqual(
            {item["kind"] for item in record["items"]},
            {
                "manifest.present",
                "manifest.contract",
                "manifest.responsibility",
                "owner",
            },
        )
        self.assertEqual(
            record["dependency_witnesses"][0]["authority"], "ManifestParser"
        )

    def test_header_scan_uses_status_then_dependency_query(self) -> None:
        """Coverage is projected from one fixed dependency query."""
        with tempfile.TemporaryDirectory() as temporary:
            root, calls = self.graph_root(temporary)
            result = run_shell(
                SCAN_HEADERS,
                "docs/a.md",
                root=root,
                environment={"FAKE_GRAPH_CALLS": str(calls)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)
            rows = calls.read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows[0].split()[:2], ["graph", "status"])
            self.assertIn(
                "--all --relation dependency --direction both --depth 0",
                rows[1],
            )

    def test_format_check_uses_manifest_context_and_fails_missing(self) -> None:
        """Required coverage is decided only by typed manifest context items."""
        with tempfile.TemporaryDirectory() as temporary:
            root, calls = self.graph_root(temporary)
            result = run_shell(
                FORMAT_HEADERS,
                "--require-header",
                "docs/a.md",
                root=root,
                environment={
                    "FAKE_GRAPH_CALLS": str(calls),
                    "FAKE_MANIFEST_PRESENT": "false",
                },
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("docs/a.md: missing dependency manifest", result.stdout)
            rows = calls.read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows[0].split()[:2], ["graph", "status"])
            self.assertIn("graph context", rows[1])
            self.assertIn("--path docs/a.md", rows[1])

    def test_dependency_graph_uses_all_relation_query_and_projects_tsv(self) -> None:
        """Graph validation filters dependency facts from the all-relation query."""
        with tempfile.TemporaryDirectory() as temporary:
            root, calls = self.graph_root(temporary)
            output = root / "dependency_graph.tsv"
            result = run_shell(
                CHECK_GRAPH,
                "--cycle-report-only",
                "--graph-tsv",
                str(output),
                root=root,
                environment={"FAKE_GRAPH_CALLS": str(calls)},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH=pass", result.stdout)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "direction\tkind\tsource\ttarget\n"
                "upstream\tdesign\tdocs/a.md\tREADME.md\n",
            )
            rows = calls.read_text(encoding="utf-8").splitlines()
            self.assertIn("--all --relation all --direction both --depth 0", rows[1])

    def test_code_scanner_paths_file_contract(self) -> None:
        """The graph producer accepts exact nonempty/empty input and rejects bad paths."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text("import json\n", encoding="utf-8")
            paths = root / "paths.txt"
            paths.write_text("a.py\n", encoding="utf-8")
            result = run_shell(
                SCAN_CODE,
                "--print-unresolved",
                "--paths-file",
                str(paths),
                root=root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("CODE_DEPENDENCY_SCAN=pass"), 1)
            self.assertIn("files=1", result.stdout)

            paths.write_text("", encoding="utf-8")
            empty = run_shell(
                SCAN_CODE,
                "--paths-file",
                str(paths),
                root=root,
            )
            self.assertEqual(empty.returncode, 0, empty.stderr)
            self.assertIn("CODE_DEPENDENCY_SCAN=pass files=0", empty.stdout)

            missing = run_shell(
                SCAN_CODE,
                "--paths-file",
                str(root / "missing.txt"),
                root=root,
            )
            self.assertEqual(missing.returncode, 2)

            paths.write_text("../escape.py\n", encoding="utf-8")
            malformed = run_shell(
                SCAN_CODE,
                "--paths-file",
                str(paths),
                root=root,
            )
            self.assertEqual(malformed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
