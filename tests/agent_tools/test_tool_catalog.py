"""Tests for the AgentCanon tool catalog checker."""

# @dependency-start
# responsibility Tests structured AgentCanon tool catalog validation.
# upstream implementation ../../tools/agent_tools/tool_catalog.py validates tool catalog
# upstream design ../../tools/catalog.yaml structured tool catalog fixture
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "tool_catalog.py"


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

    def test_current_repository_passes(self) -> None:
        """The canonical repository has a valid tool catalog."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TOOL_CATALOG=pass", result.stdout)

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
                    "family_values:",
                    "  - agent_tools",
                    "role_values:",
                    "  - catalog",
                    "families:",
                    "  agent_tools:",
                    "    root: tools/agent_tools",
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
