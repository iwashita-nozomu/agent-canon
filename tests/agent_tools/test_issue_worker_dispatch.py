# @dependency-start
# contract test
# responsibility Tests orchestration materialization of the IssueWorker publisher route.
# upstream implementation ../../tools/repository/github/issue_worker_dispatch.py materializes route and ToolCall
# upstream implementation ../../tools/agent/orchestration/agent_team.py exposes orchestration facade
# @dependency-end
"""Focused IssueWorker orchestration tests."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from tools.repository.github import issue_worker_dispatch  # noqa: E402
from tools.runtime.lifecycle.bootstrap_agent_run import main as bootstrap_main  # noqa: E402
from tools.runtime.authority.checkout_identity import CheckoutIdentity  # noqa: E402
from tools.agent.orchestration.implementation_dispatch import (  # noqa: E402
    recommended_initial_subagent_wave,
    workflow_spawn_budget,
)
from tools.agent.orchestration.team_config import (  # noqa: E402
    load_task_catalog,
    load_team_config,
    select_roles,
)


def _candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": "iwashita-nozomu/agent-canon",
        "owner": "issue-worker",
        "fix": "connect explicit candidates to publisher",
        "decision": "route durable feedback",
    }
    value.update(overrides)
    return value


def test_same_repository_candidate_materializes_publisher_tool_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    product_root = tmp_path / "product"
    product_root.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=product_root,
        check=True,
    )
    (product_root / "README.md").write_text("product checkout\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"], cwd=product_root, check=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=AgentCanon test",
            "-c",
            "user.email=agent-canon-test@example.invalid",
            "commit",
            "-qm",
            "product fixture",
        ],
        cwd=product_root,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/iwashita-nozomu/agent-canon.git",
        ],
        cwd=product_root,
        check=True,
    )
    runtime_root = tmp_path / "runtime"
    control_parent = tmp_path / "control"
    runtime_root.mkdir()
    control_parent.mkdir()
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("AGENT_CANON_CONTROL_PARENT_ROOT", str(control_parent))
    calls: list[tuple[str, str]] = []

    def spawn(agent_type: str, prompt: str) -> str:
        calls.append((agent_type, prompt))
        return "publisher-1"

    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "publish explicit feedback",
        spawn,
        workspace_root=product_root,
        agentcanon_source_root=PROJECT_ROOT,
        request_clause_ids=("feedback-routing",),
    )

    assert result.status == "spawned"
    assert result.handoff.qualifies
    assert result.publisher_agent_id == "publisher-1"
    assert result.tool_call is not None
    assert result.tool_call["tool_id"] == "issue-worker"
    assert result.tool_call["arguments"]["publisher_agent_id"] == "publisher-1"
    assert result.tool_call["arguments"]["checkout_repository"] == "iwashita-nozomu/agent-canon"
    assert result.tool_call["arguments"]["agentcanon_source_root"] == str(PROJECT_ROOT)
    assert result.tool_call["arguments"]["target_root"] == str(product_root)
    stage_command = result.tool_call["arguments"]["receipt_stage_command"]
    assert stage_command[0] == str(PROJECT_ROOT / "bootstrap.sh")
    assert str(PROJECT_ROOT) != str(product_root)
    assert stage_command[stage_command.index("--root") + 1] == str(product_root)
    child_args = stage_command[stage_command.index("--") + 1 :]
    assert "--runtime-root" not in child_args
    assert "--checkout-root" not in child_args
    assert str(runtime_root) not in child_args
    assert str(product_root) not in child_args
    assert str(runtime_root) in stage_command
    assert str(control_parent) in stage_command
    preflight_command = result.tool_call["arguments"]["receipt_preflight_command"]
    assert preflight_command[0] == str(PROJECT_ROOT / "bootstrap.sh")
    assert "--receipt-preflight" in preflight_command
    assert "receipt_preflight_command" in calls[0][1]
    assert "receipt_stage_command" in calls[0][1]
    assert calls and calls[0][0] == "publisher"
    assert "checkout_identity" in calls[0][1]
    assert "remote" in calls[0][1]

    config = load_team_config(PROJECT_ROOT / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, PROJECT_ROOT)
    roles = select_roles(
        config,
        [],
        full_team=False,
        catalog=catalog,
        workflow_family_id="issue_worker_publication",
        issue_worker_candidate=_candidate(),
    )
    active_subagents, _ = workflow_spawn_budget(catalog, "issue_worker_publication")
    assert tuple(role.id for role in roles) == ("publisher",)
    assert recommended_initial_subagent_wave(
        roles,
        active_subagents,
        catalog,
        agent_root=PROJECT_ROOT / ".codex" / "agents",
        workflow_family_id="issue_worker_publication",
        issue_worker_candidate=_candidate(),
    ) == ("worker",)


def test_t15_without_explicit_candidate_has_no_initial_publisher() -> None:
    config = load_team_config(PROJECT_ROOT / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, PROJECT_ROOT)
    roles = select_roles(
        config,
        [],
        full_team=False,
        catalog=catalog,
        workflow_family_id="issue_worker_publication",
    )
    active_subagents, _ = workflow_spawn_budget(catalog, "issue_worker_publication")

    assert roles == ()
    assert recommended_initial_subagent_wave(
        roles,
        active_subagents,
        catalog,
        agent_root=PROJECT_ROOT / ".codex" / "agents",
        workflow_family_id="issue_worker_publication",
    ) == ()


def test_runtime_context_defaults_to_the_source_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_CANON_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("AGENT_CANON_CONTROL_PARENT_ROOT", raising=False)

    context = issue_worker_dispatch.resolve_agentcanon_runtime_context()

    assert context.source_root == PROJECT_ROOT.resolve()
    assert context.runtime_root == PROJECT_ROOT.resolve() / ".runtime"
    assert context.control_parent_root == PROJECT_ROOT.resolve().parent


def test_issue_worker_dispatch_defaults_to_source_runtime_without_explicit_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_CANON_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("AGENT_CANON_CONTROL_PARENT_ROOT", raising=False)
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "publish explicit feedback",
        lambda _agent_type, _prompt: "unexpected-publisher",
        workspace_root=PROJECT_ROOT,
        agentcanon_source_root=PROJECT_ROOT,
    )
    assert result.status == "spawned"
    assert result.tool_call is not None
    arguments = result.tool_call["arguments"]
    assert arguments["publication_mode"] == "publish"
    assert arguments["publication_reason"] == ""
    preflight = arguments["receipt_preflight_command"]
    stage = arguments["receipt_stage_command"]
    assert str(PROJECT_ROOT / ".runtime") in preflight
    assert str(PROJECT_ROOT.parent) in preflight
    assert str(PROJECT_ROOT / ".runtime") in stage
    assert str(PROJECT_ROOT.parent) in stage


def test_issue_worker_dispatch_defers_without_source_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("AGENT_CANON_CONTROL_PARENT_ROOT", str(tmp_path / "control"))
    calls: list[str] = []
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "publish explicit feedback",
        lambda agent_type, _prompt: calls.append(agent_type) or "publisher-investigate",
        workspace_root=PROJECT_ROOT,
        agentcanon_source_root=tmp_path / "missing-source",
    )
    assert result.status == "deferred"
    assert result.tool_call is None
    assert calls == []


def test_explicit_issue_worker_candidate_does_not_change_generic_intake() -> None:
    config = load_team_config(PROJECT_ROOT / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, PROJECT_ROOT)
    roles = select_roles(
        config,
        [],
        full_team=False,
        catalog=catalog,
        workflow_family_id="comprehensive_development",
        issue_worker_candidate=_candidate(),
    )
    active_subagents, _ = workflow_spawn_budget(catalog, "comprehensive_development")

    assert all(role.id != "publisher" for role in roles)
    assert recommended_initial_subagent_wave(
        roles,
        active_subagents,
        catalog,
        agent_root=PROJECT_ROOT / ".codex" / "agents",
        workflow_family_id="comprehensive_development",
        issue_worker_candidate=_candidate(),
    ) == ("requirements_organizer",)


def test_bootstrap_t15_dispatches_candidate_once_and_persists_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def spawn(agent_type: str, prompt: str) -> str:
        calls.append((agent_type, prompt))
        return "publisher-bootstrap-1"

    candidate = _candidate(durable_follow_up=True)
    with tempfile.TemporaryDirectory(prefix="issue-worker-bootstrap-") as root:
        runtime_root = Path(root) / "runtime"
        monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
        report_root = runtime_root / "reports"
        run_id = "t15-bootstrap-dispatch"
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = bootstrap_main(
                [
                    "--task",
                    "publish explicit feedback",
                    "--task-id",
                    "T15",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--runtime-root",
                    str(runtime_root),
                    "--skip-agent-canon-preflight",
                    "--issue-worker-candidate",
                    json.dumps(candidate),
                ],
                spawn=spawn,
            )

        assert return_code == 0
        assert len(calls) == 1
        assert calls[0][0] == "publisher"
        assert "ISSUE_WORKER_TOOL_CALL=" in output.getvalue()
        assert "RECOMMENDED_INITIAL_SUBAGENT_ROLES=publisher" in output.getvalue()
        manifest = yaml.safe_load(
            (report_root / run_id / "team_manifest.yaml").read_text(encoding="utf-8")
        )
        run = manifest["run"]
        assert run["spawn_wave_recommendation"]["initial_wave_agent_types"] == [
            "worker"
        ]
        dispatch = run["issue_worker_dispatch"]
        assert dispatch["status"] == "spawned"
        assert dispatch["publisher_agent_id"] == "publisher-bootstrap-1"
        assert dispatch["checkout_identity"]["remote"] == "iwashita-nozomu/agent-canon"
        assert dispatch["tool_call"]["tool_id"] == "issue-worker"
        assert dispatch["tool_call"]["arguments"]["publisher_agent_id"] == (
            "publisher-bootstrap-1"
        )


def test_bootstrap_t15_without_candidate_does_not_dispatch_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="issue-worker-bootstrap-empty-") as root:
        runtime_root = Path(root) / "runtime"
        monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
        report_root = runtime_root / "reports"
        run_id = "t15-bootstrap-no-candidate"
        output = io.StringIO()
        with redirect_stdout(output):
            return_code = bootstrap_main(
                [
                    "--task",
                    "publish explicit feedback",
                    "--task-id",
                    "T15",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--runtime-root",
                    str(runtime_root),
                    "--skip-agent-canon-preflight",
                ],
                spawn=lambda agent_type, prompt: calls.append((agent_type, prompt))
                or "unexpected-publisher",
            )

        assert return_code == 0
        assert calls == []
        assert "ISSUE_WORKER_TOOL_CALL=" not in output.getvalue()
        assert "RECOMMENDED_INITIAL_SUBAGENT_ROLES=" in output.getvalue()
        manifest = yaml.safe_load(
            (report_root / run_id / "team_manifest.yaml").read_text(encoding="utf-8")
        )
        run = manifest["run"]
        assert run["spawn_wave_recommendation"]["initial_wave_role_ids"] == []
        assert "issue_worker_dispatch" not in run


def test_bootstrap_t15_foreign_candidate_is_handoff_without_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    candidate = _candidate(repository="other/repository")

    with tempfile.TemporaryDirectory(prefix="issue-worker-bootstrap-foreign-") as root:
        runtime_root = Path(root) / "runtime"
        monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
        report_root = runtime_root / "reports"
        run_id = "t15-bootstrap-foreign"
        return_code = bootstrap_main(
            [
                "--task",
                "publish foreign feedback",
                "--task-id",
                "T15",
                "--owner",
                "codex",
                "--run-id",
                run_id,
                "--workspace-root",
                str(PROJECT_ROOT),
                "--report-root",
                str(report_root),
                "--runtime-root",
                str(runtime_root),
                "--skip-agent-canon-preflight",
                "--issue-worker-candidate",
                json.dumps(candidate),
            ],
            spawn=lambda agent_type, prompt: calls.append((agent_type, prompt))
            or "unexpected-publisher",
        )

        assert return_code == 0
        assert calls == []
        manifest = yaml.safe_load(
            (report_root / run_id / "team_manifest.yaml").read_text(encoding="utf-8")
        )
        dispatch = manifest["run"]["issue_worker_dispatch"]
        assert dispatch["status"] == "deferred"
        assert dispatch["handoff"]["reason"] == "other-repository"
        assert dispatch["tool_call"] is None


def test_bootstrap_cli_materializes_spawn_handoff_without_injected_callback() -> None:
    candidate = _candidate(durable_follow_up=True)

    with tempfile.TemporaryDirectory(prefix="issue-worker-bootstrap-cli-") as root:
        runtime_root = Path(root) / "runtime"
        report_root = runtime_root / "reports"
        run_id = "t15-bootstrap-cli"
        environment = os.environ.copy()
        environment["AGENT_CANON_RUNTIME_ROOT"] = str(runtime_root)
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "tools" / "runtime" / "lifecycle" / "bootstrap_agent_run.py"),
                "--task",
                "publish explicit feedback",
                "--task-id",
                "T15",
                "--owner",
                "codex",
                "--run-id",
                run_id,
                "--workspace-root",
                str(PROJECT_ROOT),
                "--report-root",
                str(report_root),
                "--runtime-root",
                str(runtime_root),
                "--skip-agent-canon-preflight",
                "--issue-worker-candidate",
                json.dumps(candidate),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "ISSUE_WORKER_DISPATCH_STATUS=pending" in result.stdout
        assert "ISSUE_WORKER_SPAWN_TOOL_CALL=" in result.stdout
        manifest = yaml.safe_load(
            (report_root / run_id / "team_manifest.yaml").read_text(encoding="utf-8")
        )
        dispatch = manifest["run"]["issue_worker_dispatch"]
        assert dispatch["status"] == "pending"
        spawn_tool_call = dispatch["spawn_tool_call"]
        assert spawn_tool_call["tool_id"] == "spawn_agent"
        assert spawn_tool_call["arguments"]["role"] == "publisher"
        assert spawn_tool_call["arguments"]["agent_type"] == "worker"
        assert spawn_tool_call["arguments"]["checkout_identity"]["remote"] == (
            "iwashita-nozomu/agent-canon"
        )


def test_other_repository_candidate_is_no_mutation_handoff() -> None:
    calls: list[str] = []

    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(repository="other/repository"),
        "publish explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        agentcanon_source_root=PROJECT_ROOT,
    )

    assert result.status == "deferred"
    assert result.handoff.reason == "other-repository"
    assert result.tool_call is None
    assert calls == []


def test_same_repository_evidence_gap_still_reaches_publisher_investigation() -> None:
    calls: list[str] = []
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(owner=""),
        "investigate explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        agentcanon_source_root=PROJECT_ROOT,
    )

    assert result.status == "spawned"
    assert not result.handoff.qualifies
    assert result.handoff.reason == "owner-unresolved"
    assert calls == ["publisher"]


def test_missing_checkout_identity_is_deferred_without_spawn(monkeypatch) -> None:
    monkeypatch.setattr(
        issue_worker_dispatch,
        "resolve_checkout_identity",
        lambda workspace: CheckoutIdentity(
            cwd=str(workspace),
            git_root="unknown",
            branch="detached",
            head="unknown",
            remote="unknown",
        ),
    )
    calls: list[str] = []
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "publish explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        agentcanon_source_root=PROJECT_ROOT,
    )

    assert result.status == "deferred"
    assert result.handoff.reason == "checkout-identity-unresolved"
    assert calls == []


def test_missing_target_root_routes_to_publisher_investigation(monkeypatch) -> None:
    original_resolver = issue_worker_dispatch.resolve_checkout_identity

    def resolve_target_identity(workspace: Path) -> CheckoutIdentity:
        if workspace.resolve() == PROJECT_ROOT.resolve():
            return CheckoutIdentity(
                cwd=str(workspace),
                git_root="unknown",
                branch="main",
                head="a" * 40,
                remote="iwashita-nozomu/agent-canon",
            )
        return original_resolver(workspace)

    monkeypatch.setattr(issue_worker_dispatch, "resolve_checkout_identity", resolve_target_identity)
    calls: list[str] = []
    result = issue_worker_dispatch.dispatch_issue_worker(
        _candidate(),
        "investigate explicit feedback",
        lambda agent_type, prompt: calls.append(agent_type) or "publisher-1",
        workspace_root=PROJECT_ROOT,
        agentcanon_source_root=PROJECT_ROOT,
    )

    assert result.status == "spawned"
    assert result.tool_call is not None
    assert result.tool_call["arguments"]["publication_mode"] == "investigate_only"
    assert result.tool_call["arguments"]["target_root"] == "<target-root>"
    assert "target_root" in result.tool_call["arguments"]["publication_reason"]
    assert result.tool_call["arguments"]["receipt_preflight_command"] == []
    assert result.tool_call["arguments"]["receipt_stage_command"] == []
    assert calls == ["publisher"]
