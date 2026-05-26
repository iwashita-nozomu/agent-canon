# @dependency-start
# responsibility Tests Codex agent role eval automation.
# upstream implementation ../../tools/agent_tools/evaluate_codex_agent_roles.py helper
# upstream design ../../agents/evals/README.md role eval contract
# @dependency-end
"""Tests for Codex agent role eval automation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_codex_agent_roles.py"


def run_eval(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the role eval helper."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class CodexAgentRoleEvalTest(unittest.TestCase):
    """Verify Codex custom agent role eval behavior."""

    def test_default_role_eval_passes(self) -> None:
        """The canonical role eval should pass on checked-in agent config."""
        result = run_eval()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CODEX_AGENT_ROLE_EVAL=pass", result.stdout)
        self.assertIn("CODEX_AGENT_ROLE_FINDINGS=0", result.stdout)
        self.assertIn("ROLE_RUNTIME_METRICS_STATUS=missing", result.stdout)
        self.assertIn("diff_triage_reviewer:cheap_first_review", result.stdout)
        self.assertIn("experiment_runner:execution_only", result.stdout)
        self.assertIn("ship_reviewer:frontier_required", result.stdout)

    def test_runtime_metrics_are_aggregated(self) -> None:
        """Optional JSONL runtime metrics should be summarized by agent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "roles.jsonl"
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "agent": "python_reviewer",
                                "tokens": 100,
                                "latency_ms": 25,
                                "retry_count": 1,
                                "output_used": True,
                            }
                        ),
                        json.dumps(
                            {
                                "agent": "python_reviewer",
                                "total_tokens": 50,
                                "latency_ms": 15,
                                "parent_intervention": True,
                                "format_violation": True,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--runtime-log", str(log_path))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ROLE_RUNTIME_METRICS_STATUS=observed", result.stdout)
            self.assertIn("ROLE_RUNTIME_METRIC=python_reviewer:calls=2:tokens=150", result.stdout)
            self.assertIn("parent_interventions=1", result.stdout)
            self.assertIn("format_violations=1", result.stdout)
            self.assertIn("output_used=1", result.stdout)

    def test_runtime_metrics_report_invalid_numeric_values(self) -> None:
        """Malformed metric values should produce findings instead of tracebacks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "roles.jsonl"
            log_path.write_text(
                json.dumps(
                    {
                        "agent": "python_reviewer",
                        "tokens": "100.5",
                        "latency_ms": "n/a",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_eval("--runtime-log", str(log_path))

            self.assertEqual(result.returncode, 1)
            self.assertIn("CODEX_AGENT_ROLE_FINDING=runtime-log:", result.stdout)
            self.assertIn("invalid-int-metric", result.stdout)
            self.assertNotIn("Traceback", result.stderr)

    def test_root_argument_uses_target_task_catalog(self) -> None:
        """--root should validate the target checkout's routing, not the script checkout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            shutil.copytree(PROJECT_ROOT / ".codex" / "agents", root / ".codex" / "agents")
            (root / ".codex").mkdir(exist_ok=True)
            shutil.copy2(PROJECT_ROOT / ".codex" / "config.toml", root / ".codex" / "config.toml")
            (root / "agents").mkdir()
            shutil.copy2(
                PROJECT_ROOT / "agents" / "agents_config.json",
                root / "agents" / "agents_config.json",
            )
            task_catalog = (PROJECT_ROOT / "agents" / "task_catalog.yaml").read_text(
                encoding="utf-8"
            )
            (root / "agents" / "task_catalog.yaml").write_text(
                task_catalog.replace("family: scoped_change_lite", "family: scoped_change", 1),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("CODEX_AGENT_ROLE_FINDING=routing:T1:must-use-scoped-change-lite", result.stdout)


if __name__ == "__main__":
    unittest.main()
