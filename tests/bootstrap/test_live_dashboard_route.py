"""Opt-in end-to-end dashboard dispatch through a resident Docker container."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))
from tools.runtime.archive.runtime_log_paths import repo_log_key  # noqa: E402
from tools.agent.orchestration.tool_calls import materialize_issue_worker_tool_call  # noqa: E402

LIVE_DOCKER = os.environ.get("AGENT_CANON_LIVE_DOCKER") == "1"


pytestmark = pytest.mark.skipif(
    not LIVE_DOCKER,
    reason="set AGENT_CANON_LIVE_DOCKER=1 to run the resident Docker integration",
)


def run_bootstrap(source: Path, control: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the source checkout's host bootstrap with one isolated control root."""
    environment = os.environ.copy()
    environment["AGENT_CANON_ALLOW_BUILD"] = "1"
    return subprocess.run(
        [
            str(source / "bootstrap.sh"),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(control / "runtime"),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
        env=environment,
    )


def git(*arguments: str, cwd: Path) -> None:
    """Run one test-owned Git setup command."""
    subprocess.run(["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True)


def test_resident_dashboard_route_uses_target_and_private_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the logical dashboard tool against a read-only target mount."""
    source = tmp_path / "agent-canon"
    target = tmp_path / "target"
    control = tmp_path / "control"
    private_log = tmp_path / "agent-canon-log"
    private_remote = tmp_path / "agent-canon-log.git"
    git_config = tmp_path / "gitconfig"
    log_remote = "https://github.com/example/agent-canon-log.git"
    subprocess.run(
        ["git", "clone", "--local", str(ROOT), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    git("remote", "set-url", "origin", "https://github.com/iwashita-nozomu/agent-canon.git", cwd=source)
    target.mkdir()
    control.mkdir()
    private_log.mkdir()
    private_log.chmod(0o700)
    subprocess.run(["git", "init", "-q", "--bare", str(private_remote)], check=True)
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(git_config),
            "url.file://" + str(private_remote) + ".insteadOf",
            log_remote,
        ],
        check=True,
    )
    monkeypatch.setenv("AGENT_CANON_PRIVATE_LOG_ROOT", str(private_log))
    monkeypatch.setenv("AGENT_CANON_LOG_REMOTE", log_remote)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    git("init", "-q", "-b", "main", cwd=private_log)
    git("remote", "add", "origin", log_remote, cwd=private_log)
    git("init", "-q", "-b", "main", cwd=target)
    (target / "KNOWN_TARGET_MARKER").write_text("target\n", encoding="utf-8")
    git("add", "KNOWN_TARGET_MARKER", cwd=target)
    git(
        "-c",
        "user.name=AgentCanon live test",
        "-c",
        "user.email=agent-canon-live@example.invalid",
        "commit",
        "-qm",
        "target marker",
        cwd=target,
    )
    git("remote", "add", "origin", "https://github.com/example/live-target.git", cwd=target)
    log_dir = private_log / "hook-runs" / repo_log_key(target) / "live"
    log_dir.mkdir(parents=True)
    (log_dir / "behavior_events.jsonl").write_text(
        json.dumps(
            {
                "schema": "agent-canon.behavior-event.v1",
                "event_id": "a" * 64,
                "hook_invocation_id": "live-dashboard",
                "event_kind": "behavior_snapshot",
                "hook_event_name": "PostToolUse",
                "hook_log_namespace": "live",
                "status": "pass",
                "timestamp": "2026-08-27T00:00:00Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    git("add", ".", cwd=private_log)
    git(
        "-c",
        "user.name=AgentCanon live test",
        "-c",
        "user.email=agent-canon-live@example.invalid",
        "commit",
        "-qm",
        "private log seed",
        cwd=private_log,
    )
    git("push", "-u", "origin", "main", cwd=private_log)
    source_status_before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    target_status_before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=target,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    try:
        installed = run_bootstrap(source, control, "install")
        assert installed.returncode == 0, installed.stdout + installed.stderr
        registered = run_bootstrap(source, control, "target", "add", "--root", str(target), "--mode", "read-only")
        assert registered.returncode == 0, registered.stdout + registered.stderr
        runtime = control / "runtime" / "container-state"
        target_head = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        checkout_identity = {
            "cwd": str(target),
            "git_root": str(target),
            "branch": "main",
            "head": target_head,
            "remote": "example/live-target",
        }
        tool_call = materialize_issue_worker_tool_call(
            handoff={
                "repository": "example/live-target",
                "owner": "issue-worker",
                "fix": "stage body-free receipt",
            },
            publisher_agent_id="publisher-live",
            checkout_repository="example/live-target",
            checkout_identity=checkout_identity,
            runtime_root=str(control / "runtime"),
            agentcanon_source_root=str(source),
            target_root=str(target),
            control_parent_root=str(control),
        )
        tool_arguments = tool_call["arguments"]
        assert tool_arguments["agentcanon_source_root"] == str(source)
        assert tool_arguments["target_root"] == str(target)
        materialized_preflight = tuple(tool_arguments["receipt_preflight_command"])
        materialized_stage = tuple(tool_arguments["receipt_stage_command"])
        assert materialized_preflight[materialized_preflight.index("--root") + 1] == str(target)
        assert materialized_stage[materialized_stage.index("--root") + 1] == str(target)
        assert "--runtime-root" not in materialized_preflight[materialized_preflight.index("--") + 1 :]
        assert "--checkout-root" not in materialized_preflight[materialized_preflight.index("--") + 1 :]
        assert "--runtime-root" not in materialized_stage[materialized_stage.index("--") + 1 :]
        assert "--checkout-root" not in materialized_stage[materialized_stage.index("--") + 1 :]
        assert str(control / "runtime") not in materialized_preflight[materialized_preflight.index("--") + 1 :]
        assert str(target) not in materialized_preflight[materialized_preflight.index("--") + 1 :]
        assert str(control / "runtime") not in materialized_stage[materialized_stage.index("--") + 1 :]
        assert str(target) not in materialized_stage[materialized_stage.index("--") + 1 :]
        command_environment = os.environ.copy()
        command_environment["AGENT_CANON_ALLOW_BUILD"] = "1"
        receipt_preflight = subprocess.run(
            list(materialized_preflight),
            cwd=source,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=command_environment,
        )
        assert receipt_preflight.returncode == 0, (
            receipt_preflight.stdout + receipt_preflight.stderr
        )
        readback_bindings = {
            "<issue-number>": "1",
            "<issue-url>": "https://github.com/example/live-target/issues/1",
            "<issue-state>": "open",
            "<issue-action>": "create",
        }
        receipt_stage_command = tuple(
            readback_bindings.get(value, value) for value in materialized_stage
        )
        receipt_stage = subprocess.run(
            list(receipt_stage_command),
            cwd=source,
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=command_environment,
        )
        assert receipt_stage.returncode == 0, receipt_stage.stdout + receipt_stage.stderr
        assert not (runtime / "spool" / "private-feedback" / "sync-request.json").exists()
        archive_receipt = (
            private_log / "feedback" / "issue-packets" / "published"
            / "example" / "live-target" / "1.json"
        )
        assert archive_receipt.is_file()
        receipt_text = archive_receipt.read_text(encoding="utf-8")
        assert "body" not in receipt_text
        assert "private" not in receipt_text
        assert subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=private_log,
            check=True,
            capture_output=True,
            text=True,
        ).stdout == ""
        dashboard = run_bootstrap(
            source,
            control,
            "tool",
            "run",
            "--root",
            str(target),
            "generate-agent-runtime-dashboard",
            "--",
            "--root",
            ".",
            "--out",
            "reports/live-dashboard/dashboard.md",
            "--compact-out",
            "reports/live-dashboard/compact.md",
            "--api-out",
            "reports/live-dashboard/api.json",
        )
        assert dashboard.returncode == 0, dashboard.stdout + dashboard.stderr
        api = json.loads((runtime / "reports/live-dashboard/api.json").read_text(encoding="utf-8"))
        assert api["root"].startswith("/targets/")
        assert api["hook_files"] == 1
        assert api["hook_entries"] == 1
        assert (runtime / "reports/live-dashboard/dashboard.md").is_file()
        assert (runtime / "reports/live-dashboard/compact.md").is_file()
        dashboard_text = (runtime / "reports/live-dashboard/dashboard.md").read_text(encoding="utf-8")
        assert "/var/lib/agent-canon/private-log" in dashboard_text
        assert not (target / "reports").exists()
        assert not (source / "reports/live-dashboard").exists()
        assert subprocess.run(
            ["git", "status", "--porcelain"], cwd=target, check=True, capture_output=True, text=True
        ).stdout == target_status_before
        assert subprocess.run(
            ["git", "status", "--porcelain"], cwd=source, check=True, capture_output=True, text=True
        ).stdout == source_status_before
    finally:
        removed = run_bootstrap(source, control, "uninstall")
        assert removed.returncode == 0, removed.stdout + removed.stderr
