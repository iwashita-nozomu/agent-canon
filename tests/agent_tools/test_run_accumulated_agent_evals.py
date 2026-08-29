"""Tests for accumulated agent eval producer runner."""

# @dependency-start
# contract test
# responsibility Tests accumulated agent eval producer routing and bounded output capture.
# upstream implementation ../../eval/producers/run_accumulated_agent_evals.py runs eval producers in accumulation mode
# upstream design ../../eval/definitions/README.md eval accumulation contract
# upstream design ../../documents/runtime/runtime-log-archive.md external eval archive contract
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from eval.producers.run_accumulated_agent_evals import (  # noqa: E402
    EvalProducer,
    build_producers,
    render_results,
    run_producers,
)

_PARENT_BOUNDARY_PATH_KEYS = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_TASK_ID",
    "AGENT_CANON_REPOSITORY_ID",
    "AGENT_CANON_TASK_REPOSITORY",
    "AGENT_CANON_LIFECYCLE_ID",
    "AGENT_CANON_EXPECTED_IMAGE_TAG",
    "AGENT_CANON_CONTAINER_LIFECYCLE_RECEIPT",
)
def parent_bound_environment(root: Path) -> dict[str, str]:
    """Return a clean environment for one real eval fixture repository."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(root)],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "https://example.invalid/parent.git",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    environment = os.environ.copy()
    for key in _PARENT_BOUNDARY_PATH_KEYS:
        environment.pop(key, None)
    fixture_root = str(root.resolve())
    environment["AGENT_CANON_PARENT_ROOT"] = fixture_root
    environment["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] = fixture_root
    return environment


class RunAccumulatedAgentEvalsTest(unittest.TestCase):
    """Validate command construction and output bounding."""

    def test_build_producers_uses_accumulation_for_every_eval_family(self) -> None:
        """Every registered eval producer should run with append-only accumulation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "source"
            root.mkdir()
            runtime_root = root.parent / "runtime"
            runtime_root.mkdir()
            producers = build_producers(
                root=root,
                run_id="run-123",
                skill_used=("agent-orchestration", "result-artifact-writeout"),
                report_dir=root.parent / "runtime" / "tasks" / "run-123" / "reports",
                prompt_eval_manifest=root / "eval" / "definitions" / "skill_workflow_prompt_eval.toml",
                python_bin=sys.executable,
                runtime_root=runtime_root,
            )

        names = {producer.name for producer in producers}
        self.assertEqual(
            names,
            {
                "codex-agent-role",
                "skill-workflow-prompt",
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
            root = Path(temp_dir) / "source"
            root.mkdir()
            environment = parent_bound_environment(root)
            runtime_root = root.parent / "runtime"
            runtime_root.mkdir()
            log_dir = runtime_root / "tasks" / "run" / "logs"
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

            with patch.dict(os.environ, environment, clear=True):
                results = run_producers(
                    root=root,
                    producers=producers,
                    log_dir=log_dir,
                    runtime_root=runtime_root,
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
