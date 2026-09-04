"""Tests for tool proof coverage reporting."""

# @dependency-start
# contract test
# responsibility Tests Lean proof-obligation coverage reporting for cataloged tools.
# upstream implementation ../../tools/analysis/proof/tool_proof_coverage.py reports tool proof coverage
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof status policy
# upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "analysis" / "proof" / "tool_proof_coverage.py"


class ToolProofCoverageTest(unittest.TestCase):
    """Exercise proof coverage reporting."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_markdown_output_lists_next_witness(self) -> None:
        """Markdown output should show the proof frontier for each tool."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root, include_proofs=False)

            result = self.run_checker(root, "--format", "markdown")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("# Tool Proof Coverage", result.stdout)
            self.assertIn("Lean theorem binding tool-catalog behavior spec", result.stdout)

    def test_require_lean_verified_requires_explicit_selection(self) -> None:
        """Strict mode never recreates a universal proof backlog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root, include_proofs=False)

            result = self.run_checker(root, "--require-lean-verified")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("explicit-tool-selection-required", result.stdout)
            self.assertNotIn("behavior-not-lean-verified", result.stdout)

    def test_require_lean_verified_checks_selected_tool_only(self) -> None:
        """A selected tool receives strict behavior/performance proof checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root, include_proofs=True)

            result = self.run_checker(
                root,
                "--tool-id",
                "tool-catalog",
                "--require-lean-verified",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("explicit-tool-selection-required", result.stdout)
            self.assertIn("performance-not-lean-verified", result.stdout)
            payload = json.loads(
                self.run_checker(root, "--tool-id", "tool-catalog", "--format", "json").stdout
            )
            self.assertEqual(payload["selected_tool_ids"], ["tool-catalog"])
            self.assertEqual([row["tool_id"] for row in payload["rows"]], ["tool-catalog"])

    def test_declared_lean_verified_rejects_sorry(self) -> None:
        """Lean-verified claims must not point at proof files with escape hatches."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root, proof_text="theorem ToolBehavior : True := by\n  sorry\n")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("behavior-proof-artifact-has-escape", result.stdout)
            self.assertIn("TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED=0", result.stdout)

    def test_declared_lean_verified_requires_checked_flag(self) -> None:
        """Catalog proof metadata must say that the checker command actually ran."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root, checked="false")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("behavior-lean-verified-requires-checked-true", result.stdout)
            self.assertIn("TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED=0", result.stdout)

    def test_json_output_has_stable_shape(self) -> None:
        """JSON output should expose rows and findings for automation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_repo(root)

            result = self.run_checker(root, "--format", "json")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertFalse(payload["require_lean_verified"])
            self.assertEqual(payload["findings"], [])
            self.assertEqual(payload["rows"][0]["tool_id"], "tool-catalog")
            self.assertEqual(payload["rows"][0]["behavior"]["status"], "lean_verified")

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

    def write_minimal_repo(
        self,
        root: Path,
        proof_text: str = "theorem ToolBehavior : True := by\n  trivial\n",
        checked: str = "true",
        include_proofs: bool = True,
    ) -> None:
        """Create a minimal tool catalog fixture repository."""
        self.write_file(root, "README.md", self.manifest("Fixture root."))
        self.write_core_fixture_files(root, proof_text)
        self.write_fixture_docs(root)
        self.write_file(root, "documents/tools/tool-docs.toml", self.tool_docs_manifest())
        self.write_file(
            root,
            "tools/validation/ci/runners/run_all_checks.sh",
            self.manifest("Run all checks.")
            + "\npython3 tools/runtime/manifest/tool_catalog.py\n",
        )
        self.write_file(
            root,
            "tools/catalog.yaml",
            self.catalog_yaml(checked=checked, include_proofs=include_proofs),
        )

    def write_core_fixture_files(self, root: Path, proof_text: str) -> None:
        """Write fixture tool, test, and proof files."""
        self.write_file(
            root,
            "tools/runtime/manifest/tool_catalog.py",
            self.manifest("Fixture catalog checker."),
        )
        self.write_file(
            root,
            "tests/agent_tools/test_tool_catalog.py",
            self.manifest("Fixture catalog checker test."),
        )
        self.write_file(root, "proofs/tool_behavior.lean", proof_text)

    def write_fixture_docs(self, root: Path) -> None:
        """Write fixture docs referenced by the catalog checker."""
        for doc in [
            "tools/README.md",
            "documents/tools/README.md",
            "documents/tools/repo-local-tool-imports.md",
            "documents/tools/tool_catalog.md",
            "tools/validation/ci/checks/check_agent_canon_pr.sh",
            "agents/skills/agent-canon-update.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        ]:
            self.write_file(
                root,
                doc,
                self.manifest("Fixture doc.")
                + "\ntools/catalog.yaml\ntool_catalog.py\ndocuments/tools/tool-docs.toml\n",
            )

    def tool_docs_manifest(self) -> str:
        """Return fixture tool-docs TOML."""
        return "\n".join(
            [
                "# @dependency-start",
                "# responsibility Defines fixture tool-doc map.",
                "# upstream design ../../tools/catalog.yaml fixture catalog",
                "# downstream implementation ../../tools/runtime/manifest/tool_catalog.py checker",
                "# @dependency-end",
                "# tools/catalog.yaml",
                "# tool_catalog.py",
                "",
                'catalog_kind = "agent_canon_tool_docs"',
                "version = 1",
                "",
                "[[tool]]",
                'id = "tool-catalog"',
                'tool = "tools/runtime/manifest/tool_catalog.py"',
                'doc = "documents/tools/tool_catalog.md"',
                "",
            ]
        )

    def catalog_yaml(self, checked: str, include_proofs: bool) -> str:
        """Return fixture catalog YAML."""
        proof_block = (
            "\n".join(
                [
                    "    proofs:",
                    "      behavior:",
                    "        status: lean_verified",
                    "        theorem: ToolBehavior",
                    "        artifact: proofs/tool_behavior.lean",
                    "        checker: lake env lean proofs/tool_behavior.lean",
                    f"        checked: {checked}",
                ]
            )
            if include_proofs
            else ""
        )
        return "\n".join(
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
                "    path: tools/runtime/manifest/tool_catalog.py",
                "    family: agent_tools",
                "    role: catalog",
                "    status: canonical",
                "    command: python3 tools/runtime/manifest/tool_catalog.py",
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
                proof_block,
                "",
            ]
        )


if __name__ == "__main__":
    unittest.main()
