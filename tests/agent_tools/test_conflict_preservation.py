#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Exercises the focused conflict/rework content-preservation checker.
# upstream implementation ../../tools/repository/git/conflict_preservation.py owns inventory and readback.
# downstream design ../../agents/skills/pr-processing.md defines conflict/rework preservation obligations.
# @dependency-end

from __future__ import annotations

import subprocess
import json
from pathlib import Path

import pytest

from tools.repository.git.conflict_preservation import (
    ConflictPreservationError,
    capture_inventory,
    validate_plan,
    validate_rework_packet,
)
from tools.runtime.authority.hook_safety import preservation_authorized, preservation_intent


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def commit(repo: Path, message: str) -> None:
    git(repo, "add", "file.txt")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", message)


def conflicted_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "file.txt").write_text(
        "zero\nconflict\none\nuser-old\ntwo\nthree\nfour\nfive\nsix\nseven\neight\n",
        encoding="utf-8",
    )
    commit(repo, "base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-c", "feature")
    (repo / "file.txt").write_text(
        "zero\nfeature-change\none\nuser-change\ntwo\nthree\nfour\nfive\nsix\nseven\nuser-change\n",
        encoding="utf-8",
    )
    commit(repo, "feature and user hunk")
    ours = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "main")
    (repo / "file.txt").write_text(
        "zero\nmain-change\none\nuser-old\ntwo\nthree\nfour\nfive\nsix\nseven\neight\n",
        encoding="utf-8",
    )
    commit(repo, "main conflict")
    theirs = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "feature")
    git(repo, "merge", "--no-edit", "main", check=False)
    assert git(repo, "status", "--porcelain")
    return repo, base, ours, theirs


def plan_for(inventory: dict[str, object], *, operation: str = "manual") -> dict[str, object]:
    entry = next(item for item in inventory["paths"] if item["path"] == "file.txt")
    source_hunk = next(
        hunk
        for hunk in entry["hunks"]["base_to_ours"]
        if "+user-change\n" in hunk["text"]
    )
    return {
        "repository": inventory["repository"],
        "base": inventory["base"]["commit"],
        "head": inventory["ours"]["commit"],
        "merge_base": inventory["merge_base"],
        "selected_cause": "conflicting changes were not separated by hunk",
        "expected_mechanism": "resolve the conflict while retaining the unrelated user hunk",
        "exact_edit_delta": "choose the feature value for line two and retain line four",
        "paths": [
            {
                "path": "file.txt",
                "owner": "integration_executor",
                "disposition": "keep",
                "operation": operation,
                "rationale": "the conflict is resolved manually from the recorded stages",
                "expected_edit_delta": "replace only line two",
                "unaffected_content": [
                    {
                        "path": "file.txt",
                        "owner": "user",
                        "hunk_identity": {
                            "source_sha256": source_hunk["sha256"],
                            "source_header": source_hunk["header"],
                            "resolved_header": source_hunk["header"],
                            "required_lines": ["+user-change\n"],
                        },
                    }
                ],
                **({"reconstruction_map": ["preserve file.txt user hunk"]} if operation != "manual" else {}),
            }
        ],
    }


def test_capture_records_three_way_stages_and_hunks(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)

    assert inventory["schema"] == "agent-canon.conflict-preservation.v1"
    assert inventory["staged_state"] == "unmerged"
    assert inventory["conflict_paths"] == ["file.txt"]
    entry = inventory["paths"][0]
    assert set(entry["stages"]) == {"base", "ours", "theirs"}
    assert entry["stages"]["base"]["oid"]
    assert entry["hunks"]["base_to_ours"]
    assert entry["hunks"]["base_to_theirs"]
    assert "<<<<<<<" in inventory["combined_diff"] or inventory["combined_diff"]


def test_whole_file_discard_requires_reconstruction_mapping(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    plan = plan_for(inventory, operation="checkout-ours")
    plan["paths"][0].pop("reconstruction_map")

    with pytest.raises(ConflictPreservationError, match="reconstruction_map"):
        validate_plan(inventory, plan)


def test_valid_small_hunk_repair_preserves_unrelated_user_hunk(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    (repo / "file.txt").write_text(
        "zero\nfeature-change\none\nuser-change\ntwo\nthree\nfour\nfive\nsix\nseven\nuser-change\n",
        encoding="utf-8",
    )
    git(repo, "add", "file.txt")
    plan = plan_for(inventory)

    validate_plan(inventory, plan, repo=repo)


def test_whole_file_reconstruction_is_allowed_only_with_preservation_map(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    (repo / "file.txt").write_text(
        "zero\nfeature-change\none\nuser-change\ntwo\nthree\nfour\nfive\nsix\nseven\nuser-change\n",
        encoding="utf-8",
    )
    git(repo, "add", "file.txt")
    plan = plan_for(inventory, operation="whole-file-overwrite")

    validate_plan(inventory, plan, repo=repo)


def test_preservation_readback_rejects_lost_user_hunk(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    (repo / "file.txt").write_text(
        "zero\nfeature-change\none\nuser-old\ntwo\nthree\nfour\nfive\nsix\nseven\nuser-change\n",
        encoding="utf-8",
    )
    git(repo, "add", "file.txt")
    plan = plan_for(inventory)

    with pytest.raises(ConflictPreservationError, match="resolved hunk (range/header|context) is missing"):
        validate_plan(inventory, plan, repo=repo)


def test_duplicate_text_in_another_hunk_does_not_satisfy_readback(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    (repo / "file.txt").write_text(
        "zero\nfeature-change\none\nuser-old\ntwo\nthree\nfour\nfive\nsix\nseven\nuser-change\n",
        encoding="utf-8",
    )
    git(repo, "add", "file.txt")
    plan = plan_for(inventory)

    with pytest.raises(ConflictPreservationError, match="resolved hunk (range/header|context) is missing"):
        validate_plan(inventory, plan, repo=repo)


def test_hunk_identity_rejects_arbitrary_required_lines(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    plan = plan_for(inventory)
    plan["paths"][0]["unaffected_content"][0]["hunk_identity"]["required_lines"] = [
        "+arbitrary-line\n"
    ]

    with pytest.raises(ConflictPreservationError, match="required_lines"):
        validate_plan(inventory, plan)


def test_rework_packet_requires_cause_mechanism_and_exact_delta() -> None:
    packet = {
        "schema": "agent-canon.rework-preservation.v1",
        "observed_finding": "the repair replaced an entire file",
        "stable_finding_id": "finding-conflict-1",
        "selected_cause": "the repair owner was not bounded to its hunk",
        "expected_mechanism": "edit only the owning hunk",
        "expected_behavior": "unrelated content remains byte-for-byte present",
        "exact_edit_delta": "change one line",
        "unaffected_content": [
            {
                "path": "file.txt",
                "expected_blob": {"oid": "a" * 40},
            }
        ],
    }
    validate_rework_packet(packet)
    packet.pop("expected_mechanism")
    with pytest.raises(ConflictPreservationError, match="expected_mechanism"):
        validate_rework_packet(packet)
    packet["expected_mechanism"] = "edit only the owning hunk"
    packet.pop("selected_cause")
    with pytest.raises(ConflictPreservationError, match="selected_cause"):
        validate_rework_packet(packet)


@pytest.mark.parametrize(
    "command",
    (
        "git -C /tmp/repo checkout --ours -- file.txt",
        "git -C /tmp/repo checkout file.txt",
        "git --no-pager restore --theirs file.txt",
        "git reset --hard HEAD",
        "git clean -fd",
        "git clone remote existing",
        "cp generated.txt target.txt",
        "mv replacement.txt target.txt",
        "rm -f target.txt",
        "sed -i s/old/new/ target.txt",
    ),
)
def test_preservation_guard_normalizes_arbitrary_argv_forms(command: str) -> None:
    intent = preservation_intent(command)
    assert intent is not None
    assert intent.requires_preservation


def test_preservation_guard_requires_existing_packets_in_same_segment(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    inventory_path = repo / ".agent-canon" / "conflict-preservation.json"
    inventory_path.parent.mkdir()
    inventory_path.write_text(json.dumps(inventory) + "\n", encoding="utf-8")
    plan = plan_for(inventory)
    plan_path = repo / ".agent-canon" / "conflict-preservation-plan.json"
    plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
    command = (
        f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
        f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} "
        f"git -C {repo} --no-pager restore --theirs file.txt"
    )
    assert preservation_authorized(command, active_root=repo)
    assert not preservation_authorized("git --no-pager restore --theirs file.txt")
    (repo / "file-b").write_text("uncovered\n", encoding="utf-8")
    assert not preservation_authorized(
        f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
        f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} "
        f"git -C {repo} restore --theirs file-b",
        active_root=repo,
    )
    assert not preservation_authorized(
        f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
        f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} "
        f"git -C {repo} restore --theirs file.txt file-b",
        active_root=repo,
    )
    for broad_command in (
        "git -C " + str(repo) + " reset --hard HEAD",
        "git -C " + str(repo) + " clean -fd",
        "git clone remote " + str(repo),
        "cp source-a source-b " + str(repo / "file.txt"),
    ):
        assert not preservation_authorized(
            f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
            f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} {broad_command}",
            active_root=repo,
        )


def test_preservation_guard_rejects_nonexistent_or_wrong_scope_packets(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    inventory_path = repo / ".agent-canon" / "conflict-preservation.json"
    inventory_path.parent.mkdir()
    inventory_path.write_text(json.dumps(inventory) + "\n", encoding="utf-8")
    plan_path = repo / ".agent-canon" / "conflict-preservation-plan.json"
    plan_path.write_text(json.dumps(plan_for(inventory)) + "\n", encoding="utf-8")
    prefix = (
        "AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY="
        f"{inventory_path} AGENT_CANON_CONFLICT_PRESERVATION_PLAN="
    )
    assert not preservation_authorized(
        prefix + str(repo / ".agent-canon" / "missing.json") + f" git -C {repo} restore --theirs file.txt",
        active_root=repo,
    )
    assert not preservation_authorized(
        f"{prefix}{plan_path} true; git -C {repo} restore --theirs file.txt",
        active_root=repo,
    )
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-b", "main")
    assert not preservation_authorized(
        f"{prefix}{plan_path} git -C {other} restore --theirs file.txt",
        active_root=repo,
    )


def test_preservation_guard_rejects_invalid_plan_before_allow(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    inventory_path = repo / ".agent-canon" / "conflict-preservation.json"
    inventory_path.parent.mkdir()
    inventory_path.write_text(json.dumps(inventory) + "\n", encoding="utf-8")
    plan_path = repo / ".agent-canon" / "conflict-preservation-plan.json"
    plan_path.write_text("{}\n", encoding="utf-8")
    command = (
        f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
        f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} "
        f"git -C {repo} restore --theirs file.txt"
    )
    assert not preservation_authorized(command, active_root=repo)


def test_preservation_guard_rejects_head_and_stage_snapshot_drift(tmp_path: Path) -> None:
    repo, base, ours, theirs = conflicted_repo(tmp_path)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    inventory_path = repo / ".agent-canon" / "conflict-preservation.json"
    inventory_path.parent.mkdir()
    inventory_path.write_text(json.dumps(inventory) + "\n", encoding="utf-8")
    plan_path = repo / ".agent-canon" / "conflict-preservation-plan.json"
    plan_path.write_text(json.dumps(plan_for(inventory)) + "\n", encoding="utf-8")
    command = (
        f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
        f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} "
        f"git -C {repo} restore --theirs file.txt"
    )
    git(repo, "update-ref", "HEAD", base)
    assert not preservation_authorized(command, active_root=repo)

    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    repo, base, ours, theirs = conflicted_repo(stage_root)
    inventory = capture_inventory(repo, base=base, ours=ours, theirs=theirs)
    inventory_path = repo / ".agent-canon" / "conflict-preservation.json"
    inventory_path.parent.mkdir()
    inventory_path.write_text(json.dumps(inventory) + "\n", encoding="utf-8")
    plan_path = repo / ".agent-canon" / "conflict-preservation-plan.json"
    plan_path.write_text(json.dumps(plan_for(inventory)) + "\n", encoding="utf-8")
    command = (
        f"AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY={inventory_path} "
        f"AGENT_CANON_CONFLICT_PRESERVATION_PLAN={plan_path} "
        f"git -C {repo} restore --theirs file.txt"
    )
    drift = repo / "drift.txt"
    drift.write_text("drift\n", encoding="utf-8")
    drift_oid = git(repo, "hash-object", "-w", str(drift))
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--index-info"],
        input=f"100644 {drift_oid} 2\tfile.txt\n",
        text=True,
        check=True,
    )
    assert not preservation_authorized(command, active_root=repo)


def test_integration_executor_prompt_and_conditional_outputs_are_materialized() -> None:
    root = Path(__file__).resolve().parents[2]
    prompt = (root / ".codex" / "agents" / "integration_executor.toml").read_text(
        encoding="utf-8"
    )
    assert "capture merge-base, base/ours/theirs stages and hunks" in prompt
    config = json.loads((root / "agents" / "agents_config.json").read_text(encoding="utf-8"))
    role = next(
        role
        for role in config["specialist_roles"]
        if role["id"] == "integration_executor"
    )
    assert role["required_outputs"] == ["decision_log.md"]
    assert role["write_policy"]["conditional_artifacts"]["conflict_or_rework"] == [
        "conflict_preservation_inventory",
        "preservation_readback",
    ]
