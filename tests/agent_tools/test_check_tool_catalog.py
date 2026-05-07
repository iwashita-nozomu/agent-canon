"""Tests for the AgentCanon tool catalog checker."""

# @dependency-start
# responsibility Tests structured AgentCanon tool catalog validation.
# upstream implementation ../../tools/agent_tools/check_tool_catalog.py validates tool catalog
# upstream design ../../tools/catalog.yaml structured tool catalog fixture
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_tool_catalog.py"


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
                    "tools/agent_tools/check_tool_catalog.py",
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

    def test_legacy_entry_cannot_be_default_callable(self) -> None:
        """Legacy provenance entries must not be callable default tools."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "callable_by_default: false",
                    "callable_by_default: true",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("legacy:tools/legacy/example:callable-by-default", result.stdout)

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
            "tools/agent_tools/check_tool_catalog.py",
            self.manifest("Fixture catalog checker."),
        )
        self.write_file(
            root,
            "tests/agent_tools/test_check_tool_catalog.py",
            self.manifest("Fixture catalog checker test."),
        )
        self.write_file(root, "tools/legacy/example/README.md", self.manifest("Legacy."))
        (root / "tools" / "legacy" / "example").mkdir(parents=True, exist_ok=True)
        for doc in [
            "tools/README.md",
            "documents/tools/README.md",
            "documents/repo-local-tool-imports.md",
            "tools/ci/check_agent_canon_pr.sh",
            "agents/workflows/agent-canon-pr-workflow.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        ]:
            self.write_file(
                root,
                doc,
                self.manifest("Fixture doc.")
                + "\ntools/catalog.yaml\ncheck_tool_catalog.py\n",
            )
        self.write_file(
            root,
            "tools/ci/run_all_checks.sh",
            self.manifest("Run all checks.")
            + "\npython3 tools/agent_tools/check_tool_catalog.py\n",
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
                    "  - legacy_provenance",
                    "family_values:",
                    "  - agent_tools",
                    "  - legacy",
                    "role_values:",
                    "  - catalog",
                    "  - legacy",
                    "families:",
                    "  agent_tools:",
                    "    root: tools/agent_tools",
                    "  legacy:",
                    "    root: tools/legacy",
                    "entries:",
                    "  - id: check-tool-catalog",
                    "    path: tools/agent_tools/check_tool_catalog.py",
                    "    family: agent_tools",
                    "    role: catalog",
                    "    status: canonical",
                    "    command: python3 tools/agent_tools/check_tool_catalog.py",
                    "    writes: false",
                    "    default_wiring:",
                    "      ci: true",
                    "      pr_check: false",
                    "    docs:",
                    "      - tools/README.md",
                    "      - documents/tools/README.md",
                    "    tests:",
                    "      - tests/agent_tools/test_check_tool_catalog.py",
                    "  - id: legacy-example",
                    "    path: tools/legacy/example",
                    "    family: legacy",
                    "    role: legacy",
                    "    status: legacy_provenance",
                    "    command: null",
                    "    writes: false",
                    "    callable_by_default: false",
                    "    default_wiring:",
                    "      ci: false",
                    "      pr_check: false",
                    "    docs:",
                    "      - tools/legacy/example/README.md",
                    "      - documents/repo-local-tool-imports.md",
                    "    tests: []",
                    "    test_exempt_reason: fixture legacy provenance",
                    "    legacy:",
                    "      source_repo: /tmp/source",
                    "      source_path: scripts/",
                    "      promotion_status: preserved",
                    "",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
