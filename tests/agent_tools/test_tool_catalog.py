"""Tests for the AgentCanon tool catalog checker."""

# @dependency-start
# contract test
# responsibility Tests structured AgentCanon tool catalog validation.
# upstream implementation ../../tools/agent_tools/tool_catalog.py validates tool catalog
# upstream design ../../tools/catalog.yaml structured tool catalog fixture
# upstream implementation ../fixtures/tool_catalog/main_manual_dispatch.rs manual main dispatch fixture
# upstream implementation ../fixtures/tool_catalog/graph_manual_dispatch.rs manual graph dispatch fixture
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "tool_catalog.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import tool_catalog as catalog_tool  # noqa: E402

MAIN_DISPATCH_FIXTURE = (
    PROJECT_ROOT / "tests/fixtures/tool_catalog/main_manual_dispatch.rs"
)
GRAPH_DISPATCH_FIXTURE = (
    PROJECT_ROOT / "tests/fixtures/tool_catalog/graph_manual_dispatch.rs"
)


class CheckToolCatalogTest(unittest.TestCase):
    """Exercise structured tool catalog validation."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_public_surface_fixture(self, root: Path) -> None:
        """Write only the canonical inputs used by the public-surface extractor."""
        self.write_file(
            root,
            "rust/agent-canon/src/main.rs",
            MAIN_DISPATCH_FIXTURE.read_text(encoding="utf-8"),
        )
        self.write_file(
            root,
            "rust/agent-canon/src/graph.rs",
            GRAPH_DISPATCH_FIXTURE.read_text(encoding="utf-8"),
        )
        self.write_file(
            root,
            "agents/canonical/CLI_ENTRYPOINTS.md",
            "\n".join(
                [
                    "# CLI",
                    "",
                    "graph build",
                    "graph status",
                    "graph query",
                    "graph context",
                    "",
                ]
            ),
        )
        self.write_file(root, "tools/catalog.yaml", "version: 1\nentries: []\n")
        self.write_file(
            root,
            "agents/skills/catalog.yaml",
            "version: 1\nskill_families: []\n",
        )

    def test_manual_dispatch_fixture_emits_four_sorted_public_rows(self) -> None:
        """Primary operation spans stay in graph.rs with main/doc secondary spans."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_public_surface_fixture(root)

            report = catalog_tool.extract_public_surface(root)

        self.assertEqual(report.findings, ())
        self.assertEqual(
            [row.surface_id for row in report.rows],
            [
                "cli:graph build",
                "cli:graph context",
                "cli:graph query",
                "cli:graph status",
            ],
        )
        self.assertTrue(
            all(row.source_span.path == "rust/agent-canon/src/graph.rs" for row in report.rows)
        )
        for row in report.rows:
            self.assertEqual(
                {span.path for span in row.secondary_spans},
                {
                    "agents/canonical/CLI_ENTRYPOINTS.md",
                    "rust/agent-canon/src/main.rs",
                },
            )

    def test_manual_dispatch_negative_mutations_emit_no_partial_rows(self) -> None:
        """Invalid or ambiguous dispatch grammar suppresses every public row."""
        main_source = MAIN_DISPATCH_FIXTURE.read_text(encoding="utf-8")
        graph_source = GRAPH_DISPATCH_FIXTURE.read_text(encoding="utf-8")
        cases = {
            "comment-only": (
                "// mod graph;\n// args[1] == \"graph\"\nfn main() {}\n",
                graph_source,
                "rust_dispatch_invalid",
            ),
            "enum-derived": (
                main_source,
                "enum Operation { Build, Status, Query, Context }\nfn run(_: &[String]) -> i32 { 2 }\n",
                "rust_dispatch_invalid",
            ),
            "duplicate-main": (
                main_source + main_source,
                graph_source,
                "rust_dispatch_ambiguous",
            ),
            "duplicate-operation": (
                main_source,
                graph_source.replace(
                    '"build" => run_build(&args[1..]),',
                    '"build" => run_build(&args[1..]),\n'
                    '        "build" => run_build(&args[1..]),',
                ),
                "rust_dispatch_ambiguous",
            ),
            "missing-module": (
                main_source.replace("mod graph;\n", ""),
                graph_source,
                "rust_dispatch_invalid",
            ),
            "wrong-main-index": (
                main_source.replace("args[1]", "args[0]"),
                graph_source,
                "rust_dispatch_invalid",
            ),
            "wrong-main-slice": (
                main_source.replace("&args[2..]", "&args[1..]"),
                graph_source,
                "rust_dispatch_invalid",
            ),
            "wrong-operation-slice": (
                main_source,
                graph_source.replace("&args[1..]", "&args[2..]", 1),
                "rust_dispatch_invalid",
            ),
        }
        for name, (mutated_main, mutated_graph, expected) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                self.write_public_surface_fixture(root)
                (root / "rust/agent-canon/src/main.rs").write_text(
                    mutated_main, encoding="utf-8"
                )
                (root / "rust/agent-canon/src/graph.rs").write_text(
                    mutated_graph, encoding="utf-8"
                )

                report = catalog_tool.extract_public_surface(root)

                self.assertEqual(report.rows, ())
                self.assertTrue(
                    any(expected in finding.detail for finding in report.findings),
                    report.findings,
                )

    def test_current_repository_passes(self) -> None:
        """The canonical repository has a valid tool catalog."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TOOL_CATALOG=pass", result.stdout)
        catalog = yaml.safe_load(
            (PROJECT_ROOT / "tools" / "catalog.yaml").read_text(encoding="utf-8")
        )
        renderer = next(
            entry
            for entry in catalog["entries"]
            if entry["path"]
            == "tools/agent_tools/render_dependency_manifest_graph.py"
        )
        self.assertEqual(
            renderer["command"],
            "python3 tools/agent_tools/render_dependency_manifest_graph.py "
            "--root . --scope full --bundle-dir reports/dependency-graph --format json",
        )

    def test_stale_catalog_entry_fails(self) -> None:
        """Catalog entries must point at existing tool paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "tools/agent_tools/tool_catalog.py",
                    "tools/agent_tools/missing_tool.py",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=entry:tools/agent_tools/missing_tool.py:missing-path",
                result.stdout,
            )

    def test_legacy_entry_is_retired(self) -> None:
        """Legacy provenance entries are no longer accepted in AgentCanon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            self.write_file(root, "tools/legacy/example/README.md", self.manifest("Legacy."))
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "  - id: legacy-example",
                        "    summary: Retired fixture legacy tool.",
                        "    path: tools/legacy/example",
                        "    family: agent_tools",
                        "    role: catalog",
                        "    status: legacy_provenance",
                        "    command: null",
                        "    writes: false",
                        "    callable_by_default: false",
                        "    default_wiring:",
                        "      ci: false",
                        "      pr_check: false",
                        "    docs:",
                        "      - tools/legacy/example/README.md",
                        "    tests: []",
                        "    test_exempt_reason: retired fixture",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "legacy:tools/legacy/example:legacy-tools-are-retired",
                result.stdout,
            )

    def test_legacy_token_entry_is_retired(self) -> None:
        """Legacy-like tool names outside tools/legacy are also retired."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            self.write_file(
                root,
                "tools/search_legacy.py",
                self.manifest("Retired search implementation."),
            )
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "  - id: search-legacy",
                        "    summary: Retired fixture search implementation.",
                        "    path: ./tools/search_legacy.py",
                        "    family: agent_tools",
                        "    role: catalog",
                        "    status: canonical",
                        "    command: python3 tools/search_legacy.py",
                        "    writes: false",
                        "    default_wiring:",
                        "      ci: false",
                        "      pr_check: false",
                        "    docs:",
                        "      - tools/README.md",
                        "    tests:",
                        "      - tests/agent_tools/test_tool_catalog.py",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "legacy:./tools/search_legacy.py:legacy-tools-are-retired",
                result.stdout,
            )

    def test_joined_legacy_token_entry_is_retired(self) -> None:
        """Legacy tool names are retired even when legacy is joined to another token."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            self.write_file(
                root,
                "tools/legacysearch.py",
                self.manifest("Retired joined-name search implementation."),
            )
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "  - id: legacysearch",
                        "    summary: Retired joined-name fixture search implementation.",
                        "    path: tools/legacysearch.py",
                        "    family: agent_tools",
                        "    role: catalog",
                        "    status: canonical",
                        "    command: python3 tools/legacysearch.py",
                        "    writes: false",
                        "    default_wiring:",
                        "      ci: false",
                        "      pr_check: false",
                        "    docs:",
                        "      - tools/README.md",
                        "    tests:",
                        "      - tests/agent_tools/test_tool_catalog.py",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "legacy:tools/legacysearch.py:legacy-tools-are-retired",
                result.stdout,
            )

    def test_tool_doc_manifest_requires_same_named_doc(self) -> None:
        """Tool docs must map one tool to one same-basename Markdown file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            tool_docs = root / "documents" / "tools" / "tool-docs.toml"
            tool_docs.write_text(
                tool_docs.read_text(encoding="utf-8").replace(
                    "doc = \"documents/tools/tool_catalog.md\"",
                    "doc = \"documents/tools/catalog_checker.md\"",
                ),
                encoding="utf-8",
            )
            self.write_file(
                root,
                "documents/tools/catalog_checker.md",
                self.manifest("Wrongly named catalog checker doc."),
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("tool-doc-name-mismatch", result.stdout)

    def test_default_wired_reference_must_be_cataloged(self) -> None:
        """CI-referenced tools must be listed in the catalog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            self.write_file(
                root,
                "tools/ci/run_all_checks.sh",
                self.manifest("Run all checks.")
                + "\npython3 tools/agent_tools/uncataloged.py\n",
            )
            self.write_file(
                root,
                "tools/agent_tools/uncataloged.py",
                self.manifest("Fixture uncataloged tool."),
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "default_wiring:tools/agent_tools/uncataloged.py:uncataloged-tool-reference",
                result.stdout,
            )

    def test_entry_summary_is_required(self) -> None:
        """Catalog entries must include a reader-facing summary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    summary: Validates the fixture tool catalog.\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "entry:tools/agent_tools/tool_catalog.py:missing-summary",
                result.stdout,
            )

    def test_family_audience_is_required(self) -> None:
        """Family defaults must classify the intended caller."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    audience: agent\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=family:agent_tools:missing-audience",
                result.stdout,
            )

    def test_family_placement_is_required(self) -> None:
        """Family defaults must classify the migration placement."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    placement: workflow_helper\n",
                    "",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=family:agent_tools:missing-placement",
                result.stdout,
            )

    def test_invalid_entry_audience_fails(self) -> None:
        """Entry-level audience overrides must use the catalog enum."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                    "    audience: unclear\n"
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=entry:tools/agent_tools/tool_catalog.py:invalid-audience",
                result.stdout,
            )

    def test_non_string_entry_audience_fails(self) -> None:
        """Entry-level audience type errors must not fall back to the family default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                    "    audience: 123\n"
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=entry:tools/agent_tools/tool_catalog.py:invalid-audience",
                result.stdout,
            )

    def test_invalid_entry_placement_fails(self) -> None:
        """Entry-level placement overrides must use the catalog enum."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                    "    placement: somewhere_else\n"
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=entry:tools/agent_tools/tool_catalog.py:invalid-placement",
                result.stdout,
            )

    def test_non_string_entry_placement_fails(self) -> None:
        """Entry-level placement type errors must not fall back to the family default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                    "    placement: []\n"
                    "    command: python3 tools/agent_tools/tool_catalog.py\n",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=entry:tools/agent_tools/tool_catalog.py:invalid-placement",
                result.stdout,
            )

    def test_compatibility_wrapper_requires_compatibility_placement(self) -> None:
        """Compatibility wrapper entries must not look like normal entrypoints."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "    status: canonical\n",
                    "    status: compatibility_wrapper\n"
                    "    placement: workflow_helper\n",
                    1,
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "TOOL_CATALOG_FINDING=entry:tools/agent_tools/tool_catalog.py:"
                "compatibility-wrapper-placement-required",
                result.stdout,
            )

    def test_markdown_output_lists_tool_crosswalk(self) -> None:
        """Markdown output should expose a catalog crosswalk."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)

            result = self.run_checker(root, "--format", "markdown")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("## Tool Crosswalk", result.stdout)
            self.assertIn("`tool-catalog`", result.stdout)
            self.assertIn("Validates the fixture tool catalog.", result.stdout)

    def test_semantic_index_catalog_command_builds_index_before_reports(self) -> None:
        """The semantic-index catalog entry should be safe for fresh checkouts."""
        catalog = yaml.safe_load((PROJECT_ROOT / "tools" / "catalog.yaml").read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in catalog["entries"]}
        command = entries["semantic-index"]["command"]

        self.assertEqual(
            command,
            "tools/bin/agent-canon semantic-index build --include documents --include agents",
        )
        self.assertNotIn("responsibility-tree", command)

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def manifest(self, responsibility: str) -> str:
        """Return a small dependency manifest block."""
        return "\n".join(
            [
                "# @dependency-start",
                f"# responsibility {responsibility}",
                "# upstream design README.md fixture anchor",
                "# @dependency-end",
                "",
            ]
        )

    def write_minimal_repo(self, root: Path) -> None:
        """Create a minimal catalog fixture repository."""
        self.write_public_surface_fixture(root)
        self.write_file(root, "README.md", self.manifest("Fixture root."))
        self.write_file(
            root,
            "tools/agent_tools/tool_catalog.py",
            self.manifest("Fixture catalog checker."),
        )
        self.write_file(
            root,
            "tests/agent_tools/test_tool_catalog.py",
            self.manifest("Fixture catalog checker test."),
        )
        for doc in [
            "tools/README.md",
            "documents/tools/README.md",
            "documents/repo-local-tool-imports.md",
            "documents/tools/tool_catalog.md",
            "tools/ci/check_agent_canon_pr.sh",
            "agents/workflows/agent-canon-pr-workflow.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        ]:
            self.write_file(
                root,
                doc,
                self.manifest("Fixture doc.")
                + "\ntools/catalog.yaml\ntool_catalog.py\ndocuments/tools/tool-docs.toml\n",
            )
        self.write_file(
            root,
            "documents/tools/tool-docs.toml",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Defines fixture tool-doc map.",
                    "# upstream design ../../tools/catalog.yaml fixture catalog",
                    "# downstream implementation ../../tools/agent_tools/tool_catalog.py checker",
                    "# @dependency-end",
                    "# tools/catalog.yaml",
                    "# tool_catalog.py",
                    "",
                    'catalog_kind = "agent_canon_tool_docs"',
                    "version = 1",
                    "",
                    "[[tool]]",
                    'id = "tool-catalog"',
                    'tool = "tools/agent_tools/tool_catalog.py"',
                    'doc = "documents/tools/tool_catalog.md"',
                    "",
                ]
            ),
        )
        self.write_file(
            root,
            "tools/ci/run_all_checks.sh",
            self.manifest("Run all checks.")
            + "\npython3 tools/agent_tools/tool_catalog.py\n",
        )
        self.write_file(
            root,
            "tools/catalog.yaml",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Defines fixture tool catalog.",
                    "# upstream design README.md fixture anchor",
                    "# @dependency-end",
                    "",
                    "version: 1",
                    "catalog_kind: agent_canon_tool_catalog",
                    "status_values:",
                    "  - canonical",
                    "  - compatibility_wrapper",
                    "family_values:",
                    "  - agent_tools",
                    "role_values:",
                    "  - catalog",
                    "audience_values:",
                    "  - agent",
                    "  - user",
                    "placement_values:",
                    "  - workflow_helper",
                    "  - compatibility_wrapper",
                    "families:",
                    "  agent_tools:",
                    "    root: tools/agent_tools",
                    "    audience: agent",
                    "    placement: workflow_helper",
                    "entries:",
                    "  - id: tool-catalog",
                    "    summary: Validates the fixture tool catalog.",
                    "    path: tools/agent_tools/tool_catalog.py",
                    "    family: agent_tools",
                    "    role: catalog",
                    "    status: canonical",
                    "    command: python3 tools/agent_tools/tool_catalog.py",
                    "    writes: false",
                    "    default_wiring:",
                    "      ci: true",
                    "      pr_check: false",
                    "    docs:",
                    "      - tools/README.md",
                    "      - documents/tools/README.md",
                    "      - documents/tools/tool_catalog.md",
                    "    tests:",
                    "      - tests/agent_tools/test_tool_catalog.py",
                    "",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
