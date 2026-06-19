"""Tests for accumulated agent eval producer runner."""

# @dependency-start
# contract test
# responsibility Tests accumulated agent eval producer routing and bounded output capture.
# upstream implementation ../../tools/agent_tools/run_accumulated_agent_evals.py runs eval producers in accumulation mode
# upstream design ../../evidence/agent-evals/README.md eval accumulation contract
# upstream design ../../documents/runtime-log-archive.md external eval archive contract
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from run_accumulated_agent_evals import (  # noqa: E402
    EvalProducer,
    build_producers,
    render_results,
    run_producers,
)


class RunAccumulatedAgentEvalsTest(unittest.TestCase):
    """Validate command construction and output bounding."""

    def test_build_producers_uses_accumulation_for_every_eval_family(self) -> None:
        """Every registered eval producer should run with append-only accumulation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            producers = build_producers(
                root=root,
                run_id="run-123",
                skill_used=("agent-orchestration", "result-artifact-writeout"),
                report_dir=root / "reports" / "agents" / "run-123",
                prompt_eval_manifest=root / "evidence" / "agent-evals" / "skill_workflow_prompt_eval.toml",
                python_bin=sys.executable,
            )

        names = {producer.name for producer in producers}
        self.assertEqual(
            names,
            {
                "codex-agent-role",
                "skill-workflow-prompt",
                "local-llm-responsibility",
                "workflow-selection",
                "report-quality",
            },
        )
        for producer in producers:
            self.assertIn("--accumulate", producer.command)
        prompt = next(producer for producer in producers if producer.name == "skill-workflow-prompt")
        workflow = next(producer for producer in producers if producer.name == "workflow-selection")
        self.assertIn("--run-id", prompt.command)
        self.assertIn("run-123", prompt.command)
        self.assertIn("--run-id", workflow.command)
        self.assertIn("run-123", workflow.command)
        self.assertIn("--skill-used", prompt.command)
        self.assertIn("agent-orchestration", prompt.command)
        self.assertIn("result-artifact-writeout", prompt.command)
        self.assertIn("--report-dir", prompt.command)

    def test_run_producers_writes_logs_and_renders_bounded_status(self) -> None:
        """Producer stdout/stderr should be stored in files, with compact status on stdout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_dir = root / "reports" / "agent-eval-runs" / "run"
            producers = (
                EvalProducer("ok-family", ("ok",)),
                EvalProducer("bad-family", ("bad",)),
            )

            def fake_runner(
                command: Sequence[str],
                cwd: Path,
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cwd, root)
                return subprocess.CompletedProcess(
                    args=tuple(command),
                    returncode=1 if command[0] == "bad" else 0,
                    stdout=f"stdout for {command[0]}\n",
                    stderr=f"stderr for {command[0]}\n",
                )

            results = run_producers(
                root=root,
                producers=producers,
                log_dir=log_dir,
                runner=fake_runner,
            )
            rendered = render_results(root, results)

            self.assertEqual(len(results), 2)
            self.assertTrue((log_dir / "01-ok-family.stdout.txt").exists())
            self.assertTrue((log_dir / "02-bad-family.stderr.txt").exists())
            self.assertIn("ACCUMULATED_AGENT_EVAL_PRODUCER=ok-family:pass:", rendered)
            self.assertIn("ACCUMULATED_AGENT_EVAL_PRODUCER=bad-family:fail:", rendered)
            self.assertIn("ACCUMULATED_AGENT_EVAL_FAILED=bad-family", rendered)
            self.assertIn("ACCUMULATED_AGENT_EVAL=fail", rendered)


if __name__ == "__main__":
    unittest.main()
