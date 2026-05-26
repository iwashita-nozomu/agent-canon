"""Tests for tool/convention drift checker."""

# @dependency-start
# responsibility Tests tool/convention drift checker behavior.
# upstream implementation ../../tools/agent_tools/tool_drift.py checker
# upstream design ../../documents/dependency-manifest-design.md manifest trace map
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "tool_drift.py"


class CheckToolConventionDriftTest(unittest.TestCase):
    """Exercise the tool/convention drift checker."""

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
        """The canonical repository satisfies the drift gate."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TOOL_CONVENTION_DRIFT=pass", result.stdout)

    def test_missing_manifest_link_fails(self) -> None:
        """A required tool/document relationship must be in a manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_convention_contract(root)
            tool = root / "tools" / "agent_tools" / "check_convention_compliance.py"
            tool.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# responsibility Checks convention compliance.",
                        "# upstream design ../../documents/conventions/README.md conventions",
                        "# upstream design ../../agents/evals/skill_workflow_prompt_eval.toml evals",
                        "# upstream design ../../agents/templates/closeout_gate.md closeout",
                        "# upstream implementation ../ci/run_all_checks.sh ci",
                        "# upstream implementation ./tool_drift.py drift gate",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "convention_compliance")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("TOOL_CONVENTION_DRIFT=fail", result.stdout)
            self.assertIn(
                "missing-manifest-link:convention_compliance:"
                "tools/agent_tools/check_convention_compliance.py:"
                "agents/canonical/CODEX_WORKFLOW.md",
                result.stdout,
            )

    def test_kind_mismatch_is_reported(self) -> None:
        """Reverse manifest edges must not contradict the direct edge kind."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_convention_contract(root)
            target = root / "documents" / "conventions" / "README.md"
            target.write_text(
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "responsibility Defines convention index.",
                        "downstream environment ../../tools/agent_tools/check_convention_compliance.py checker",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "convention_compliance")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("kind-mismatch:convention_compliance", result.stdout)
            self.assertIn("upstream design != downstream environment", result.stdout)

    def test_reverse_required_link_fails_when_only_direct_edge_exists(self) -> None:
        """A bidirectional contract reports a missing reverse manifest edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# responsibility Defines fixture tool catalog.",
                        "# upstream design README.md fixture anchor",
                        "# @dependency-end",
                        "",
                        "version: 1",
                        "entries: []",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-reverse-manifest-link:tool_catalog:"
                "tools/agent_tools/tool_catalog.py:tools/catalog.yaml",
                result.stdout,
            )

    def test_pr_check_must_run_strict_dependency_review(self) -> None:
        """The AgentCanon PR check must include strict dependency review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_agent_canon_pr_contract(root)
            script = root / "tools" / "ci" / "check_agent_canon_pr.sh"
            text = script.read_text(encoding="utf-8").replace(
                "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing\n",
                "",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_checker(root, "--contract", "agent_canon_pr_check")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing-required-text:agent_canon_pr_check:"
                "tools/ci/check_agent_canon_pr.sh:"
                "missing-strict-dependency-review",
                result.stdout,
            )

    def test_catalog_stale_entry_fails(self) -> None:
        """The drift checker catches stale structured catalog entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    "tools/agent_tools/tool_catalog.py",
                    "tools/agent_tools/missing_tool.py",
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "stale-catalog-entry:tool_catalog:"
                "tools/agent_tools/missing_tool.py:missing-path",
                result.stdout,
            )

    def test_catalog_retired_legacy_fails(self) -> None:
        """Legacy provenance entries and directories are rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_tool_catalog_contract(root)
            self.write_file(root, "tools/legacy/example/README.md", "legacy\n")
            catalog = root / "tools" / "catalog.yaml"
            catalog.write_text(
                catalog.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "  - id: legacy-example",
                        "    path: tools/legacy/example",
                        "    status: legacy_provenance",
                        "    callable_by_default: false",
                        "    default_wiring:",
                        "      ci: false",
                        "      pr_check: false",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--contract", "tool_catalog")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "retired-legacy-tool:tool_catalog:"
                "tools/legacy/example:legacy-tools-are-retired",
                result.stdout,
            )
            self.assertIn(
                "retired-legacy-tool:tool_catalog:tools/legacy:legacy-directory-present",
                result.stdout,
            )

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_plain_manifest(self, root: Path, relative: str) -> None:
        """Write one non-isolated placeholder manifest."""
        self.write_file(
            root,
            relative,
            "\n".join(
                [
                    "<!--",
                    "@dependency-start",
                    "responsibility Provides a fixture target.",
                    "upstream design README.md fixture anchor",
                    "@dependency-end",
                    "-->",
                    "",
                ]
            ),
        )

    def write_convention_contract(self, root: Path) -> None:
        """Write fixtures for the convention-compliance contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/agent_tools/check_convention_compliance.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Checks convention compliance.",
                    "# upstream design ../../documents/conventions/README.md conventions",
                    "# upstream design ../../agents/canonical/CODEX_WORKFLOW.md workflow",
                    "# upstream design ../../agents/evals/skill_workflow_prompt_eval.toml evals",
                    "# upstream design ../../agents/templates/closeout_gate.md closeout",
                    "# upstream implementation ../ci/run_all_checks.sh ci",
                    "# upstream implementation ./tool_drift.py drift gate",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        for relative in [
            "documents/conventions/README.md",
            "agents/canonical/CODEX_WORKFLOW.md",
            "agents/evals/skill_workflow_prompt_eval.toml",
            "agents/templates/closeout_gate.md",
            "tools/ci/run_all_checks.sh",
            "tools/agent_tools/tool_drift.py",
        ]:
            self.write_plain_manifest(root, relative)

    def write_agent_canon_pr_contract(self, root: Path) -> None:
        """Write fixtures for the AgentCanon PR check contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/ci/check_agent_canon_pr.sh",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Checks AgentCanon PR readiness.",
                    "# upstream design ../../agents/workflows/agent-canon-pr-workflow.md workflow",
                    "# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone template",
                    "# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template checklist",
                    "# upstream implementation ../agent_tools/run_repo_dependency_review.sh dependency review",
                    "# upstream implementation ./check_github_workflows.py github checks",
                    "# upstream implementation ./run_all_checks.sh quick ci",
                    "# @dependency-end",
                    "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing",
                    "",
                ]
            ),
        )
        for relative in [
            "agents/workflows/agent-canon-pr-workflow.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
            "tools/agent_tools/run_repo_dependency_review.sh",
            "tools/ci/check_github_workflows.py",
            "tools/ci/run_all_checks.sh",
        ]:
            self.write_plain_manifest(root, relative)

    def write_tool_catalog_contract(self, root: Path) -> None:
        """Write fixtures for the tool catalog contract."""
        self.write_file(root, "README.md", "# Fixture\n")
        self.write_file(
            root,
            "tools/agent_tools/tool_catalog.py",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Validates tool catalog.",
                    "# upstream design ../../tools/catalog.yaml catalog",
                    "# upstream design ../../tools/README.md tool docs",
                    "# upstream design ../../documents/tools/README.md root docs",
                    "# upstream design ../../documents/tools/tool-docs.toml docs map",
                    "# upstream design ../../documents/repo-local-tool-imports.md imports",
                    "# downstream implementation ../../tools/ci/run_all_checks.sh ci",
                    "# downstream implementation ../../tests/agent_tools/test_tool_catalog.py tests",
                    "# @dependency-end",
                    "",
                ]
            ),
        )
        self.write_file(
            root,
            "tools/catalog.yaml",
            "\n".join(
                [
                    "# @dependency-start",
                    "# responsibility Defines fixture tool catalog.",
                    "# downstream implementation agent_tools/tool_catalog.py checker",
                    "# @dependency-end",
                    "",
                    "version: 1",
                    "entries:",
                    "  - id: tool-catalog",
                    "    path: tools/agent_tools/tool_catalog.py",
                    "    status: canonical",
                    "",
                ]
            ),
        )
        for relative in [
            "tools/README.md",
            "documents/tools/README.md",
            "documents/tools/tool-docs.toml",
            "documents/repo-local-tool-imports.md",
            "tools/ci/run_all_checks.sh",
            "tests/agent_tools/test_tool_catalog.py",
        ]:
            self.write_file(
                root,
                relative,
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "responsibility Provides tool catalog fixture.",
                        "upstream design README.md fixture anchor",
                        "downstream implementation tools/agent_tools/tool_catalog.py checker",
                        "@dependency-end",
                        "-->",
                        "tools/catalog.yaml",
                        "tool_catalog.py",
                        "documents/tools/tool-docs.toml",
                        "",
                    ]
                ),
            )


if __name__ == "__main__":
    unittest.main()
