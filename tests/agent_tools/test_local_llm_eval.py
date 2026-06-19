"""Tests for local LLM responsibility eval harness."""

# @dependency-start
# contract test
# responsibility Tests local LLM single-file responsibility eval harness.
# upstream implementation ../../tools/agent_tools/local_llm_eval.py runs configured eval cases
# upstream design ../../evidence/agent-evals/local_llm_responsibility_eval.toml defines canonical eval cases
# upstream design ../../documents/local-llm-responsibility-analysis.md single-file scope policy
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "local_llm_eval.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import mounted_log_archive_root  # noqa: E402


class LocalLlmEvalTest(unittest.TestCase):
    """Exercise prompt-only local LLM evals without requiring llama.cpp."""

    def test_prompt_eval_accumulates_report(self) -> None:
        """Prompt evals should pass and write unique accumulated reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            archive_root = mounted_log_archive_root(root)
            archive_root.mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--accumulate",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            reports = list(
                (archive_root / "eval-results" / "local-llm-responsibility").glob(
                    "local-llm-eval-*-pass.md"
                )
            )
            report_text = reports[0].read_text(encoding="utf-8") if reports else ""

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LOCAL_LLM_EVAL=pass", result.stdout)
        self.assertIn("LOCAL_LLM_EVAL_ACCUMULATED_REPORT=", result.stdout)
        self.assertEqual(len(reports), 1)
        self.assertIn("LOCAL_LLM_EVAL_RUN_ID=", report_text)
        self.assertIn(
            "upstream design ../../../../evidence/agent-evals/local_llm_responsibility_eval.toml",
            report_text,
        )

    def test_duplicate_case_id_fails(self) -> None:
        """Duplicate eval case IDs must fail manifest audit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            manifest = root / "evidence" / "agent-evals" / "local_llm_responsibility_eval.toml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                + "\n".join(
                    [
                        "[[evals]]",
                        'id = "fixture-single-file"',
                        'target = "tools/agent_tools/file_responsibility_llm.py"',
                        'required_prompt_regex = ["Scope: exactly one file"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate-id", result.stdout)

    def test_missing_llm_skips_without_requirement(self) -> None:
        """Model-backed evals should skip, not fail, when llama.cpp is unavailable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tools_home = root / ".tools"
            tools_home.mkdir()
            self.write_fixture(root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--run-llm",
                    "--llama-cli",
                    str(root / "missing" / "llama-cli"),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_TOOLS_HOME": str(tools_home), "HOME": str(root), "PATH": ""},
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LOCAL_LLM_EVAL=skip", result.stdout)

    def write_fixture(self, root: Path) -> None:
        """Write a minimal local LLM eval fixture."""
        target = root / "tools" / "agent_tools" / "file_responsibility_llm.py"
        target.parent.mkdir(parents=True)
        target.write_text("# @dependency-start\n# responsibility Fixture.\n", encoding="utf-8")
        manifest = root / "evidence" / "agent-evals" / "local_llm_responsibility_eval.toml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            "\n".join(
                [
                    'catalog_kind = "agent_canon_local_llm_responsibility_eval"',
                    "version = 1",
                    "",
                    "[[evals]]",
                    'id = "fixture-single-file"',
                    'target = "tools/agent_tools/file_responsibility_llm.py"',
                    'description = "Fixture prompt scope check."',
                    'required_prompt_regex = ["Scope: exactly one file", "Do not infer repo-wide ownership"]',
                    'forbidden_prompt_regex = ["CI pass/fail authority"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
