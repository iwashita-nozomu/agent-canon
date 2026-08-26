"""Opt-in end-to-end dashboard dispatch through a resident Docker container."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.agent_tools.runtime_log_paths import repo_log_key

ROOT = Path(__file__).resolve().parents[2]
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


def test_resident_dashboard_route_uses_target_and_private_archive(tmp_path: Path) -> None:
    """Run the logical dashboard tool against a read-only target mount."""
    source = tmp_path / "agent-canon"
    target = tmp_path / "target"
    control = tmp_path / "control"
    private_log = tmp_path / "agent-canon-log"
    subprocess.run(
        ["git", "clone", "--local", str(ROOT), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    target.mkdir()
    control.mkdir()
    private_log.mkdir()
    private_log.chmod(0o700)
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
        runtime = control / "runtime" / "container-state"
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
