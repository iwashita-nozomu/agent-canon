# @dependency-start
# contract test
# responsibility Reproduces shared-checkout writer collisions before spawn and target-bound mutation rejection.
# upstream implementation ../../tools/agent_tools/writer_target.py owns writer-target validation.
# upstream implementation ../../tools/agent_tools/implementation_dispatch.py materializes writer waves.
# upstream implementation ../../tools/agent_tools/mutation_authority.py owns active mutation admission.
# @dependency-end
"""Focused tests for task-scoped writer targets."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from tools.agent_tools.implementation_dispatch import (
    recommended_dynamic_expansion_wave_slots,
    recommended_initial_subagent_wave,
    validate_writer_handoff_waves,
    workflow_spawn_budget,
)
from tools.agent_tools.mutation_authority import evaluate_mutation_authority
from tools.agent_tools.team_config import (
    SubagentWaveSlot,
    load_task_catalog,
    load_team_config,
    select_roles,
)
from tools.agent_tools.writer_target import (
    WriterTarget,
    WriterTargetError,
    materialize_writer_target_packet,
    validate_writer_target_allocations,
    validate_writer_target_identity,
)


def target(root: str, branch: str = "fix/942") -> WriterTarget:
    return WriterTarget(root, branch, "iwashita-nozomu/agent-canon", ("tools/",))


def write_identity(root: Path, role_id: str = "implementer") -> None:
    value: dict[str, object] = {
        "schema": "agent-canon.runtime-agent-identity.v1",
        "run_id": "run-942",
        "agent_id": "writer-942",
        "role_id": role_id,
        "parent_agent_id": "parent-942",
        "authority": "write_capable_child",
        "allowed_files": ["src/owned.py"],
        "allowed_directories": [],
        "scope_digest": "",
        "status": "active",
        "receipt_sha256": "",
    }
    value["scope_digest"] = hashlib.sha256(
        json.dumps(
            {"allowed_files": value["allowed_files"], "allowed_directories": []},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    unsigned = dict(value)
    unsigned.pop("receipt_sha256")
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    target_path = root / "runtime" / "agent_identity.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    (root / "spawn.json").write_text(
        json.dumps(
            {
                "subagent_event_kind": "spawn",
                "subagent_target": "writer-942",
                "subagent_agent_type": "worker",
                "mutation_scope_digest": value["scope_digest"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    packet = {
        "schema": "agent-canon.writer-target-packet.v1",
        "checkout_root": str(root),
        "branch": "fix/942",
        "remote": "iwashita-nozomu/agent-canon",
        "allowed_paths": ["src/owned.py"],
        "checkout_identity": {
            "cwd": str(root),
            "git_root": str(root),
            "branch": "fix/942",
            "head": "a" * 40,
            "remote": "iwashita-nozomu/agent-canon",
        },
    }
    packet_path = root / ".agent-canon" / "writer-target.json"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")


def test_shared_checkout_writer_targets_are_rejected_before_spawn() -> None:
    shared = target("/tmp/agent-canon-shared")
    with pytest.raises(WriterTargetError, match="checkout_root_collision"):
        validate_writer_target_allocations(
            (
                {"owner": "#927:worker", "write_capable": True, "writer_target": shared},
                {"owner": "#928:publisher", "write_capable": True, "writer_target": shared},
            )
        )


def test_distinct_topic_clones_and_readers_remain_admissible() -> None:
    admitted = validate_writer_target_allocations(
        (
            {"owner": "#927:worker", "write_capable": True, "writer_target": target("/tmp/a")},
            {"owner": "#928:publisher", "write_capable": True, "writer_target": target("/tmp/b")},
            {"owner": "#929:reviewer", "write_capable": False, "writer_target": None},
        )
    )
    assert [item.normalized_root for item in admitted] == ["/tmp/a", "/tmp/b"]


def test_writer_target_is_required_for_writer_and_not_for_reader() -> None:
    with pytest.raises(WriterTargetError, match="required_before_spawn"):
        validate_writer_target_allocations(
            ({"owner": "worker", "write_capable": True, "writer_target": None},)
        )
    assert validate_writer_target_allocations(
        ({"owner": "reader", "write_capable": False, "writer_target": None},)
    ) == ()


def test_wave_materializer_rejects_colliding_writer_slots() -> None:
    waves = (
        (
            SubagentWaveSlot("implementer", "worker-1", "worker", True),
            SubagentWaveSlot("integration_executor", "integration-1", "integration_executor", True),
        ),
    )
    shared = target("/tmp/one")
    with pytest.raises(WriterTargetError, match="checkout_root_collision"):
        validate_writer_handoff_waves(
            waves,
            {
                waves[0][0].executable_identity: shared,
                waves[0][1].executable_identity: shared,
            },
        )


def test_wave_materializer_allows_distinct_writer_slots() -> None:
    waves = ((SubagentWaveSlot("implementer", "worker-1", "worker", True),),)
    assert validate_writer_handoff_waves(
        waves,
        {waves[0][0].executable_identity: target("/tmp/one")},
    )[0].branch == "fix/942"


def test_normal_stage_materializer_carries_targets_into_writer_slots() -> None:
    config = load_team_config()
    catalog = load_task_catalog(config)
    roles = select_roles(
        config,
        ["implementer", "integration_executor"],
        full_team=False,
        catalog=catalog,
        workflow_family_id="comprehensive_development",
    )
    active, _ = workflow_spawn_budget(catalog, "comprehensive_development")
    initial = recommended_initial_subagent_wave(roles, active, catalog)
    writer_targets = {
        "implementer": target("/tmp/implementer"),
        "integration_executor": target("/tmp/integration"),
    }
    waves = recommended_dynamic_expansion_wave_slots(
        roles,
        active,
        initial,
        catalog,
        writer_targets=writer_targets,
    )
    writer_slots = [slot for wave in waves for slot in wave if slot.write_capable]
    assert {slot.role_id for slot in writer_slots} == {
        "implementer",
        "integration_executor",
    }
    assert all(slot.writer_target is not None for slot in writer_slots)


def test_identity_must_match_prepared_target() -> None:
    writer = target("/tmp/prepared")
    identity = {
        "cwd": "/tmp/prepared",
        "git_root": "/tmp/prepared",
        "branch": "fix/942",
        "head": "a" * 40,
        "remote": "iwashita-nozomu/agent-canon",
    }
    assert validate_writer_target_identity(writer, identity) == writer
    with pytest.raises(WriterTargetError, match="branch_identity_mismatch"):
        validate_writer_target_identity(writer, {**identity, "branch": "main"})


def test_hook_target_blocks_foreign_checkout_and_branch_switch() -> None:
    env = {
        "AGENT_CANON_CHECKOUT_ROOT": "/tmp/target",
        "AGENT_CANON_CHECKOUT_BRANCH": "fix/942",
    }
    foreign = evaluate_mutation_authority(
        {"tool_name": "Bash", "tool_input": {"command": "touch src/x.py"}},
        report_dir=None,
        active_root=Path("/tmp/foreign"),
        environment=env,
    )
    assert foreign.reason == "blocked_authority_required"
    switch = evaluate_mutation_authority(
        {"tool_name": "Bash", "tool_input": {"command": "git switch fix/942"}},
        report_dir=None,
        active_root=Path("/tmp/target"),
        environment=env,
    )
    assert switch.reason == "blocked_authority_required"


def test_writer_target_rejects_relative_root() -> None:
    with pytest.raises(WriterTargetError, match="checkout_root_must_be_absolute"):
        target("relative/path")


def test_materialized_packet_contains_validated_identity(tmp_path: Path) -> None:
    writer = WriterTarget(str(tmp_path), "fix/942", "local/repo", ("src/",))
    identity = {
        "cwd": str(tmp_path),
        "git_root": str(tmp_path),
        "branch": "fix/942",
        "head": "b" * 40,
        "remote": "local/repo",
    }
    packet_path = materialize_writer_target_packet(writer, identity)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["checkout_root"] == str(tmp_path)
    assert packet["checkout_identity"] == identity


def test_pretooluse_uses_exact_structured_allowed_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_identity(root)
        environment = {
            **WriterTarget(
                str(root),
                "fix/942",
                "iwashita-nozomu/agent-canon",
                ("src/owned.py",),
            ).environment(),
            "AGENT_CANON_RUNTIME_AGENT_ID": "writer-942",
            "AGENT_CANON_RUNTIME_ROLE_ID": "implementer",
            "AGENT_CANON_RUNTIME_PARENT_AGENT_ID": "parent-942",
        }
        allowed = evaluate_mutation_authority(
            {"tool_name": "Bash", "tool_input": {"command": "touch src/owned.py"}},
            report_dir=root,
            active_root=root,
            environment=environment,
            hook_spool_root=root,
        )
        assert allowed.status == "allowed"
        escaped = evaluate_mutation_authority(
            {"tool_name": "Bash", "tool_input": {"command": "touch README.md"}},
            report_dir=root,
            active_root=root,
            environment=environment,
            hook_spool_root=root,
        )
        assert escaped.reason == "mutation_scope_outside_child_receipt"
        commit = evaluate_mutation_authority(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -qm update"},
            },
            report_dir=root,
            active_root=root,
            environment=environment,
            hook_spool_root=root,
        )
        assert commit.status == "allowed"
        switch = evaluate_mutation_authority(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git switch fix/other"},
            },
            report_dir=root,
            active_root=root,
            environment=environment,
            hook_spool_root=root,
        )
        assert switch.reason == "writer_target_branch_switch_forbidden"
        rename = evaluate_mutation_authority(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch -m fix/renamed"},
            },
            report_dir=root,
            active_root=root,
            environment=environment,
            hook_spool_root=root,
        )
        assert rename.reason == "writer_target_branch_switch_forbidden"
        packet_mutation = evaluate_mutation_authority(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "touch .agent-canon/writer-target.json"},
            },
            report_dir=root,
            active_root=root,
            environment=environment,
            hook_spool_root=root,
        )
        assert packet_mutation.reason == "writer_target_packet_mutation_forbidden"


def test_raw_merge_and_rebase_are_rejected_even_inside_target() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_identity(root)
        environment = {
            "AGENT_CANON_RUNTIME_AGENT_ID": "writer-942",
            "AGENT_CANON_RUNTIME_ROLE_ID": "implementer",
            "AGENT_CANON_RUNTIME_PARENT_AGENT_ID": "parent-942",
        }
        for command in ("git merge origin/main", "git rebase origin/main"):
            decision = evaluate_mutation_authority(
                {"tool_name": "Bash", "tool_input": {"command": command}},
                report_dir=root,
                active_root=root,
                environment=environment,
                hook_spool_root=root,
            )
            assert decision.reason == "raw_git_merge_or_rebase_forbidden"


def test_canonical_merge_main_is_integration_only_and_preservation_gated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_identity(root, role_id="integration_executor")
        runtime_environment = {
            "AGENT_CANON_RUNTIME_AGENT_ID": "writer-942",
            "AGENT_CANON_RUNTIME_ROLE_ID": "integration_executor",
            "AGENT_CANON_RUNTIME_PARENT_AGENT_ID": "parent-942",
        }
        command = (
            "python3 tools/agent_tools/repository_topic_clone.py merge-main "
            "--url git@github.com:iwashita-nozomu/agent-canon.git "
            "--repo-name agent-canon --workspace-root /tmp --topic issue-942 "
            "--branch fix/942 --owner-evidence evidence.txt"
        )
        allowed = evaluate_mutation_authority(
            {"tool_name": "Bash", "tool_input": {"command": command}},
            report_dir=root,
            active_root=root,
            environment=runtime_environment,
            hook_spool_root=root,
        )
        assert allowed.status == "allowed"
        missing_inputs = evaluate_mutation_authority(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": command.replace("merge-main", "finalize-merge")
                },
            },
            report_dir=root,
            active_root=root,
            environment=runtime_environment,
            hook_spool_root=root,
        )
        assert missing_inputs.reason == "repository_topic_clone_preservation_inputs_missing"
        finalized = evaluate_mutation_authority(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": command.replace("merge-main", "finalize-merge")
                    + " --inventory inventory.json --plan plan.json"
                },
            },
            report_dir=root,
            active_root=root,
            environment=runtime_environment,
            hook_spool_root=root,
        )
        assert finalized.status == "allowed"
        write_identity(root, role_id="implementer")
        ordinary = evaluate_mutation_authority(
            {"tool_name": "Bash", "tool_input": {"command": command}},
            report_dir=root,
            active_root=root,
            environment={
                **runtime_environment,
                "AGENT_CANON_RUNTIME_ROLE_ID": "implementer",
            },
            hook_spool_root=root,
        )
        assert ordinary.reason == "repository_topic_clone_lifecycle_requires_integration_executor"


def test_workspace_writer_without_static_packet_is_blocked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_identity(root)
        (root / ".agent-canon" / "writer-target.json").unlink()
        decision = evaluate_mutation_authority(
            {"tool_name": "Bash", "tool_input": {"command": "touch src/owned.py"}},
            report_dir=root,
            active_root=root,
            environment={
                "AGENT_CANON_RUNTIME_AGENT_ID": "writer-942",
                "AGENT_CANON_RUNTIME_ROLE_ID": "implementer",
                "AGENT_CANON_RUNTIME_PARENT_AGENT_ID": "parent-942",
            },
            hook_spool_root=root,
        )
        assert decision.reason == "writer_target_packet_missing"


def test_bootstrap_cli_rejects_duplicate_targets_before_publishing_run() -> None:
    with tempfile.TemporaryDirectory() as runtime:
        duplicate_root = Path(runtime) / "shared"
        target_json = json.dumps(
            {
                "implementer": {
                    "checkout_root": str(duplicate_root),
                    "branch": "fix/implementer",
                    "remote": "iwashita-nozomu/agent-canon",
                    "allowed_paths": ["tools/agent_tools/"],
                },
                "integration_executor": {
                    "checkout_root": str(duplicate_root),
                    "branch": "fix/integration",
                    "remote": "iwashita-nozomu/agent-canon",
                    "allowed_paths": ["agents/"],
                },
            },
            separators=(",", ":"),
        )
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "tools/agent_tools/bootstrap_agent_run.py"),
                "--task",
                "writer target collision",
                "--owner",
                "codex",
                "--task-id",
                "T11",
                "--enable",
                "integration_executor",
                "--skip-agent-canon-preflight",
                "--no-language-review-candidates",
                "--runtime-root",
                runtime,
                "--workspace-root",
                str(Path(__file__).resolve().parents[2]),
                "--writer-targets",
                target_json,
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "AGENT_CANON_RUNTIME_ROOT": runtime},
        )
        assert result.returncode == 1
        assert "writer_target:checkout_root_collision" in result.stdout
        assert not list(Path(runtime).glob("reports/agents/*"))
