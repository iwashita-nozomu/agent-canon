# @dependency-start
# contract test
# responsibility Tests Codex agent role eval automation.
# upstream implementation ../../tools/agent_tools/evaluate_codex_agent_roles.py helper
# upstream design ../../evidence/agent-evals/README.md role eval contract
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
FIRST_RUNTIME_TOKENS = 100
FIRST_RUNTIME_LATENCY_MS = 25
SECOND_RUNTIME_TOKENS = 50
SECOND_RUNTIME_LATENCY_MS = 15
EXPECTED_RUNTIME_TOKENS = FIRST_RUNTIME_TOKENS + SECOND_RUNTIME_TOKENS


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
        self.assertIn("diff_triage_reviewer:gpt-5.5:xhigh", result.stdout)
        self.assertIn("experiment_runner:gpt-5.4-mini:medium", result.stdout)
        self.assertIn("explorer:gpt-5.4-mini:medium", result.stdout)
        self.assertIn("manager_reviewer:gpt-5.5:xhigh", result.stdout)
        self.assertIn("plan_reviewer:gpt-5.5:xhigh", result.stdout)
        self.assertIn("spark_worker:gpt-5.3-codex-spark:low", result.stdout)
        self.assertIn("ship_reviewer:gpt-5.5:xhigh", result.stdout)

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
                                "tokens": FIRST_RUNTIME_TOKENS,
                                "latency_ms": FIRST_RUNTIME_LATENCY_MS,
                                "retry_count": 1,
                                "output_used": True,
                            }
                        ),
                        json.dumps(
                            {
                                "agent": "python_reviewer",
                                "total_tokens": SECOND_RUNTIME_TOKENS,
                                "latency_ms": SECOND_RUNTIME_LATENCY_MS,
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
            self.assertIn(
                f"ROLE_RUNTIME_METRIC=python_reviewer:calls=2:tokens={EXPECTED_RUNTIME_TOKENS}",
                result.stdout,
            )
            self.assertIn("parent_interventions=1", result.stdout)
            self.assertIn("format_violations=1", result.stdout)
            self.assertIn("output_used=1", result.stdout)

    def test_compact_out_limits_stdout_and_writes_summary(self) -> None:
        """Compact mode writes role stats to JSON and keeps stdout bounded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            compact = Path(tmp_dir) / "roles.json"

            result = run_eval("--compact-out", str(compact))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CODEX_AGENT_ROLE_EVAL=pass", result.stdout)
            self.assertIn("CODEX_AGENT_ROLE_COMPACT_OUT=", result.stdout)
            self.assertNotIn("ROLE_MODEL_MATRIX=", result.stdout)
            payload = json.loads(compact.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["finding_count"], 0)
            self.assertIn("gpt-5.5", payload["model_counts"])

    def test_accumulate_writes_role_eval_report(self) -> None:
        """Role evals should accumulate through the shared eval result contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir) / "role-results"

            result = run_eval("--accumulate", "--results-dir", str(results_dir), "--run-id", "test-run")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-", result.stdout)
            self.assertIn("CODEX_AGENT_ROLE_EVAL_ACCUMULATED_REPORT=", result.stdout)
            reports = tuple(results_dir.glob("codex-agent-role-eval-*-pass.md"))
            self.assertEqual(len(reports), 1)
            text = reports[0].read_text(encoding="utf-8")
            self.assertIn("CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-", text)
            self.assertIn("run_id: `test-run`", text)

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
                task_catalog.replace("family: owner_bounded_change", "family: scoped_change", 1),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn("CODEX_AGENT_ROLE_FINDING=routing:T1:must-use-owner-bounded-change", result.stdout)

    def test_spark_model_is_reserved_for_spark_worker(self) -> None:
        """Only spark_worker should use the Spark model."""
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
            shutil.copy2(
                PROJECT_ROOT / "agents" / "task_catalog.yaml",
                root / "agents" / "task_catalog.yaml",
            )
            explorer = root / ".codex" / "agents" / "explorer.toml"
            explorer.write_text(
                explorer.read_text(encoding="utf-8").replace(
                    'model = "gpt-5.4-mini"',
                    'model = "gpt-5.3-codex-spark"',
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:explorer:"
                "spark-model-reserved-for-spark-worker",
                result.stdout,
            )

    def test_review_roles_require_frontier_model(self) -> None:
        """Reviewer and quality-check roles should stay on the frontier route."""
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
            shutil.copy2(
                PROJECT_ROOT / "agents" / "task_catalog.yaml",
                root / "agents" / "task_catalog.yaml",
            )
            python_reviewer = root / ".codex" / "agents" / "python_reviewer.toml"
            python_reviewer.write_text(
                python_reviewer.read_text(encoding="utf-8")
                .replace('model = "gpt-5.5"', 'model = "gpt-5.4-mini"')
                .replace('model_reasoning_effort = "xhigh"', 'model_reasoning_effort = "medium"'),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:python_reviewer:expected-model-gpt-5.5",
                result.stdout,
            )
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:python_reviewer:expected-xhigh-reasoning",
                result.stdout,
            )

    def test_deprecated_codex_models_are_reported(self) -> None:
        """Deprecated Codex model slugs should stay out of role TOML."""
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
            shutil.copy2(
                PROJECT_ROOT / "agents" / "task_catalog.yaml",
                root / "agents" / "task_catalog.yaml",
            )
            worker = root / ".codex" / "agents" / "worker.toml"
            worker.write_text(
                worker.read_text(encoding="utf-8").replace(
                    'model = "gpt-5.5"',
                    'model = "gpt-5.3-codex"',
                ),
                encoding="utf-8",
            )

            result = run_eval("--root", str(root))

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "CODEX_AGENT_ROLE_FINDING=model-settings:worker:deprecated-model-gpt-5.3-codex",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
