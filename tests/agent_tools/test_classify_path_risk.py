"""Tests for the native path/risk check matrix classifier."""

# @dependency-start
# contract test
# responsibility Tests representative native path-risk profiles and their stable reasons/checks.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/classify_path_risk.rs classifies changed paths.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md defines risk/check routing.
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


class ClassifyPathRiskTest(unittest.TestCase):
    """Validate representative path-risk profiles through the native CLI."""

    def run_selector(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Use the explicitly selected native executable for the public command."""
        self.assertIsNotNone(
            AGENT_CANON_CLI,
            "AGENT_CANON_CLI must select the current native executable",
        )
        return subprocess.run(
            [str(AGENT_CANON_CLI), "classify-path-risk", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def select_units(self, *paths: str) -> tuple[str, ...]:
        result = self.run_selector(
            "--format",
            "json",
            *(argument for path in paths for argument in ("--path", path)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return tuple(json.loads(result.stdout)["units"])

    def test_behavior_sources_add_eval_without_retiring_existing_units(self) -> None:
        cases = {
            "agents/skills/example.md": ("docs", "eval"),
            "agents/internal-routines/example.md": ("docs", "eval"),
            "ROOT_AGENTS.md": ("docs", "eval"),
            ".codex/agents/worker.toml": ("contracts", "eval"),
            "agents/agents_config.json": ("contracts", "eval"),
            "tools/agent/orchestration/route.py": ("contracts", "eval"),
            "documents/conventions/example.md": ("docs", "eval"),
            "bootstrap/host/manifest.toml": ("eval", "workflow-container"),
            "tools/runtime/archive/github_eval_delivery.py": ("contracts", "eval"),
            ".github/workflows/other.yml": ("eval", "workflow-container"),
            "documents/design/example.md": ("docs",),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(self.select_units(path), expected)

    def test_profiles_keep_reasons_checks_and_declaration_order(self) -> None:
        paths = (
            "documents/example.md",
            "tools/agent_tools/example.py",
            ".github/workflows/demo.yml",
            "bootstrap/runtime.py",
            "eval/definitions/example.toml",
            "tools/runtime/dispatch/agent-canon/src/example.rs",
            "tools/catalog.yaml",
        )
        result = self.run_selector(
            "--format",
            "json",
            *(argument for path in paths for argument in ("--path", path)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["paths"], list(paths))
        self.assertEqual(
            payload["risks"],
            [
                {
                    "profile": "docs-only-or-docs-impact",
                    "reason": "markdown_or_docs_checker_changed",
                    "checks": ["tools/bin/agent-canon docs check"],
                },
                {
                    "profile": "python-tooling",
                    "reason": "python_path_changed",
                    "checks": [
                        "ruff check <changed-python-paths>",
                        "basedpyright --project tools/validation/code/config/basedpyright-explicit-any.json <changed-python-paths>",
                        "python3 -m pytest -q <targeted-tests>",
                    ],
                },
                {
                    "profile": "container-runtime",
                    "reason": "container_runtime_surface_changed",
                    "checks": [
                        "python3 -m pytest -q tests/tools/test_bootstrap_container_contract.py",
                        "python3 -m pytest -q tests/bootstrap/test_bootstrap_runtime.py",
                    ],
                },
                {
                    "profile": "github-automation",
                    "reason": "github_surface_changed",
                    "checks": [
                        "python3 tools/validation/ci/checks/check_github_workflows.py"
                    ],
                },
                {
                    "profile": "agent-eval",
                    "reason": "eval_surface_changed",
                    "checks": ["python3 eval/producers/run_accumulated_agent_evals.py"],
                },
                {
                    "profile": "rust",
                    "reason": "rust_surface_changed",
                    "checks": [
                        "cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml"
                    ],
                },
                {
                    "profile": "dependency",
                    "reason": "dependency_owner_changed",
                    "checks": [
                        "bash tools/analysis/dependencies/run_repo_dependency_review.sh"
                    ],
                },
            ],
        )
        self.assertEqual(
            payload["units"],
            ["docs", "rust", "contracts", "eval", "workflow-container"],
        )

    def test_paths_file_normalization_and_stable_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths_file = Path(temporary) / "changed-paths.txt"
            paths_file.write_text(
                "./documents/example.md\ndocuments/example.md\n\n./tools/unknown.sh\n",
                encoding="utf-8",
            )
            result = self.run_selector(
                "--paths-file",
                str(paths_file),
                "--format",
                "json",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["paths"], ["documents/example.md", "tools/unknown.sh"])
        self.assertEqual(payload["units"], ["docs", "contracts"])


if __name__ == "__main__":
    unittest.main()
