"""Consumer tests for the native accumulated Eval producer route."""

# @dependency-start
# contract test
# responsibility Exercises the native producer collector, external logs, and typed root propagation.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/eval_accumulation.rs runs the two registered native producers
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/runtime_boundary.rs owns external artifact writes and root capabilities
# @dependency-end

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def selected_cli() -> str:
    if AGENT_CANON_CLI is None:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return AGENT_CANON_CLI


def test_native_collector_runs_registered_families_and_captures_external_logs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    runtime = tmp_path / "runtime"
    source.mkdir()
    target.mkdir()
    runtime.mkdir()
    tool = source / "tools/bin/agent-canon"
    tool.parent.mkdir(parents=True)
    tool.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "selector=$1\n"
        "shift\n"
        "printf 'selector=%s\\n' \"$selector\"\n"
        "printf 'argument=%s\\n' \"$@\"\n"
        "printf 'parent=%s\\n' \"$AGENT_CANON_PARENT_ROOT\"\n"
        "printf 'target=%s\\n' \"$AGENT_CANON_TARGET_ROOT\"\n"
        "printf 'runtime=%s\\n' \"$AGENT_CANON_RUNTIME_ROOT\"\n"
        "printf 'parent_capability=%s\\n' \"$AGENT_CANON_PARENT_ROOT_CAPABILITY\"\n"
        "printf 'target_capability=%s\\n' \"$AGENT_CANON_TARGET_ROOT_CAPABILITY\"\n"
        "printf 'stderr for %s\\n' \"$selector\" >&2\n"
        "if [ \"$selector\" = evaluate-workflow-selection ]; then exit 4; fi\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)

    result = subprocess.run(
        [
            selected_cli(),
            "run-accumulated-agent-evals",
            "--root",
            str(source),
            "--target-root",
            str(target),
            "--runtime-root",
            str(runtime),
            "--run-id",
            "run-123",
            "--log-dir",
            "tasks/run-123/logs",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    log_dir = runtime / "tasks/run-123/logs"
    role_stdout = (log_dir / "01-codex-agent-role.stdout.txt").read_text(
        encoding="utf-8"
    )
    workflow_stdout = (log_dir / "02-workflow-selection.stdout.txt").read_text(
        encoding="utf-8"
    )
    assert result.returncode == 1
    assert "ACCUMULATED_AGENT_EVAL_PRODUCER=codex-agent-role:pass:" in result.stdout
    assert "ACCUMULATED_AGENT_EVAL_PRODUCER=workflow-selection:fail:" in result.stdout
    assert "ACCUMULATED_AGENT_EVAL_PRODUCERS=2" in result.stdout
    assert "ACCUMULATED_AGENT_EVAL_FAILED=workflow-selection" in result.stdout
    assert "ACCUMULATED_AGENT_EVAL=fail" in result.stdout
    assert "selector=evaluate-codex-agent-roles" in role_stdout
    assert "selector=evaluate-workflow-selection" in workflow_stdout
    assert "argument=--accumulate" in role_stdout
    assert "argument=--run-id" in role_stdout
    assert "argument=run-123" in role_stdout
    assert f"parent={source.resolve()}" in role_stdout
    assert f"target={target.resolve()}" in role_stdout
    assert f"runtime={runtime.resolve()}" in role_stdout
    assert '"kind":"parent-root"' in role_stdout
    assert '"kind":"target-root"' in role_stdout
    assert (log_dir / "02-workflow-selection.stderr.txt").read_text(
        encoding="utf-8"
    ) == "stderr for evaluate-workflow-selection\n"


def test_native_collector_requires_an_external_runtime_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    environment = os.environ.copy()
    environment.pop("AGENT_CANON_RUNTIME_ROOT", None)
    result = subprocess.run(
        [
            selected_cli(),
            "run-accumulated-agent-evals",
            "--root",
            str(source),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "explicit runtime root required" in result.stderr
