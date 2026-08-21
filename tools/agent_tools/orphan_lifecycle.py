#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Inventories and classifies branch, PR, and worktree orphan lifecycle state without mutating Git or GitHub.
# upstream design ../../documents/operations/orphan-lifecycle.md defines semantic classification and cleanup admission.
# upstream design ../../documents/operations/worktree-lifecycle.md delegates stale worktree cleanup evidence to this inventory.
# downstream implementation ../../tests/agent_tools/test_orphan_lifecycle.py tests semantic inventory and fail-closed admission.
# @dependency-end
"""Build a semantic orphan inventory and authorize explicit cleanup selections."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

INVENTORY_SCHEMA = "agent_canon.orphan_inventory.v1"
TRACE_SCHEMA = "agent_canon.orphan_trace.v1"
ADMISSION_SCHEMA = "agent_canon.orphan_cleanup_admission.v1"
POLICY_OWNER = "documents/operations/orphan-lifecycle.md"
_STATES = {
    "active",
    "merged_equivalent",
    "superseded",
    "orphan_safe_to_remove",
    "needs_extraction",
    "needs_verification",
    "protected_user_state",
}
Json = dict[str, Any]


class _InventoryError(RuntimeError):
    """Raised when canonical inventory evidence cannot be read safely."""


def _digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _inventory_digest(inventory: Mapping[str, object]) -> str:
    payload = dict(inventory)
    payload.pop("inventory_digest", None)
    return _digest(payload)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise _InventoryError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _git_bytes(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], check=False, capture_output=True
    )
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise _InventoryError(detail or f"git {' '.join(args)} failed")
    return result.stdout


def _git_status(root: Path, *args: str) -> int:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


def _resolve(root: Path, ref: str) -> str:
    return _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def _branch_name(ref: str) -> str:
    if ref.startswith("refs/heads/"):
        return ref.removeprefix("refs/heads/")
    short = ref.removeprefix("refs/remotes/")
    return short.split("/", 1)[1] if "/" in short else short


def _branch_refs(root: Path) -> list[Json]:
    fmt = "%(refname)%09%(objectname)%09%(symref)%09%(upstream)"
    rows = []
    for line in _git(
        root, "for-each-ref", f"--format={fmt}", "refs/heads", "refs/remotes"
    ).splitlines():
        ref, commit, symref, upstream = (line.split("\t") + ["", "", "", ""])[:4]
        if not ref or symref or ref.endswith("/HEAD"):
            continue
        rows.append(
            {"ref": ref, "commit": commit, "upstream": upstream, "branch": _branch_name(ref)}
        )
    return sorted(rows, key=lambda row: row["ref"])


def _worktrees(root: Path) -> list[Json]:
    rows: list[Json] = []
    fields: dict[str, str] = {}
    flags: set[str] = set()

    def flush() -> None:
        if fields.get("worktree"):
            rows.append(
                {
                    "path": fields["worktree"],
                    "commit": fields.get("HEAD", ""),
                    "ref": fields.get("branch", ""),
                    "detached": "detached" in flags,
                    "bare": "bare" in flags,
                    "locked": "locked" in flags,
                    "prunable": "prunable" in flags,
                }
            )

    for token in _git_bytes(root, "worktree", "list", "--porcelain", "-z").split(b"\0"):
        if not token:
            flush()
            fields, flags = {}, set()
            continue
        key, separator, value = token.decode(errors="surrogateescape").partition(" ")
        fields[key] = value if separator else ""
        if not separator:
            flags.add(key)
    flush()
    return sorted(rows, key=lambda row: row["path"])


def _worktree_state(path: Path) -> Json:
    if not path.is_dir():
        return {
            "status": "unknown",
            "dirty": None,
            "untracked_count": None,
            "entries": [],
            "error": "worktree_path_missing",
        }
    result = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        return {
            "status": "unknown",
            "dirty": None,
            "untracked_count": None,
            "entries": [],
            "error": result.stderr.decode(errors="replace").strip() or "git_status_failed",
        }
    entries = sorted(
        value.decode(errors="surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    )
    return {
        "status": "observed",
        "dirty": bool(entries),
        "untracked_count": sum(value.startswith("??") for value in entries),
        "entries": entries,
        "error": None,
    }


def _semantic_unknown(commit: str, error: str) -> Json:
    return {
        "status": "unknown",
        "basis": "unverifiable",
        "candidate_commit": commit,
        "merge_base": None,
        "ahead_commits": None,
        "behind_commits": None,
        "patch_equivalent_commits": None,
        "unique_patch_commits": None,
        "surface_equivalent": None,
        "changed_surface": [],
        "error": error,
    }


def _semantic(root: Path, main: str, candidate: str) -> Json:
    if _git_status(root, "cat-file", "-e", f"{candidate}^{{commit}}"):
        return _semantic_unknown(candidate, "candidate_commit_missing")
    try:
        merge_base = _git(root, "merge-base", main, candidate).strip()
        behind, ahead = map(
            int,
            _git(root, "rev-list", "--left-right", "--count", f"{main}...{candidate}")
            .strip()
            .split(),
        )
        cherry = [line for line in _git(root, "cherry", main, candidate).splitlines() if line]
        equivalent_patches = sum(line.startswith("-") for line in cherry)
        unique_patches = sum(line.startswith("+") for line in cherry)
        tokens = [
            value.decode(errors="surrogateescape")
            for value in _git_bytes(
                root,
                "diff",
                "--name-status",
                "-z",
                "--no-renames",
                merge_base,
                candidate,
            ).split(b"\0")
            if value
        ]
        surface = [
            {"status": tokens[index], "path": tokens[index + 1]}
            for index in range(0, len(tokens) - 1, 2)
        ]
        same_surface = all(
            _git_bytes(root, "ls-tree", "-z", candidate, "--", row["path"])
            == _git_bytes(root, "ls-tree", "-z", main, "--", row["path"])
            for row in surface
        )
        ancestor = not _git_status(root, "merge-base", "--is-ancestor", candidate, main)
        if ancestor or not ahead:
            semantic_status, basis = "none", "reachable_from_main"
        elif not unique_patches and equivalent_patches:
            semantic_status, basis = "none", "patch_equivalent"
        elif same_surface:
            semantic_status, basis = "none", "surface_equivalent"
        else:
            semantic_status, basis = "present", "unique_patch_and_surface_delta"
        return {
            "status": semantic_status,
            "basis": basis,
            "candidate_commit": candidate,
            "merge_base": merge_base,
            "ahead_commits": ahead,
            "behind_commits": behind,
            "patch_equivalent_commits": equivalent_patches,
            "unique_patch_commits": unique_patches,
            "surface_equivalent": same_surface,
            "changed_surface": surface,
            "error": None,
        }
    except (ValueError, _InventoryError) as exc:
        return _semantic_unknown(candidate, str(exc))


def _read_json(path: Path) -> Json:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _InventoryError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise _InventoryError(f"JSON root must be an object: {path}")
    return value


def _record(raw: object) -> Json:
    if not isinstance(raw, dict):
        raise _InventoryError("trace record must be an object")
    selector = raw.get("selector")
    if not isinstance(selector, dict) or len(selector) != 1:
        raise _InventoryError("trace selector must contain exactly one field")
    key, value = next(iter(selector.items()))
    allowed = {"candidate_id", "branch", "ref", "pr_number", "worktree_path"}
    if key not in allowed:
        raise _InventoryError(f"unsupported trace selector: {key}")
    if key == "pr_number":
        if not isinstance(value, int) or value <= 0:
            raise _InventoryError("trace pr_number must be positive")
    elif not isinstance(value, str) or not value:
        raise _InventoryError(f"trace selector {key} must be non-empty")

    owners = raw.get("active_owners")
    successors = raw.get("successors")
    requirement = raw.get("requirement_state")
    resolution = raw.get("resolution")
    owner = raw.get("worktree_owner", "unknown")
    if not isinstance(owners, list) or not all(isinstance(item, str) and item for item in owners):
        raise _InventoryError("trace active_owners must be a string list")
    if not isinstance(successors, list):
        raise _InventoryError("trace successors must be a list")
    normalized = []
    for successor in successors:
        if not isinstance(successor, dict):
            raise _InventoryError("trace successor must be an object")
        successor_id, coverage = successor.get("id"), successor.get("coverage")
        if not isinstance(successor_id, str) or not successor_id:
            raise _InventoryError("trace successor id must be non-empty")
        if coverage not in {"complete", "partial", "unknown"}:
            raise _InventoryError("trace successor coverage is invalid")
        normalized.append({"id": successor_id, "coverage": coverage})
    if requirement not in {"resolved", "unresolved", "unknown"}:
        raise _InventoryError("trace requirement_state is invalid")
    if resolution is not None and (not isinstance(resolution, str) or not resolution):
        raise _InventoryError("trace resolution must be null or non-empty")
    if owner not in {"runtime", "user", "unknown"}:
        raise _InventoryError("trace worktree_owner is invalid")
    return {
        "selector": selector,
        "active_owners": sorted(set(owners)),
        "successors": sorted(normalized, key=lambda item: item["id"]),
        "requirement_state": requirement,
        "resolution": resolution,
        "worktree_owner": owner,
    }


def _pr(raw: object) -> Json:
    if not isinstance(raw, dict):
        raise _InventoryError("pull request snapshot must be an object")
    number, state = raw.get("number"), raw.get("state")
    if not isinstance(number, int) or number <= 0:
        raise _InventoryError("pull request number must be positive")
    if state not in {"open", "closed", "merged"}:
        raise _InventoryError("pull request state is invalid")
    for field in ("head_ref", "head_sha", "url"):
        if not isinstance(raw.get(field), str) or not raw[field]:
            raise _InventoryError(f"pull request {field} must be non-empty")
    return {key: raw[key] for key in ("number", "head_ref", "head_sha", "state", "url")}


def load_trace(path: Path | None) -> Json:
    """Load provider-owned Issue/PR readback without owning its state machine."""
    if path is None:
        return {"schema": TRACE_SCHEMA, "records": [], "pull_requests": []}
    raw = _read_json(path)
    if raw.get("schema") != TRACE_SCHEMA:
        raise _InventoryError(f"trace schema must be {TRACE_SCHEMA}")
    records, pull_requests = raw.get("records"), raw.get("pull_requests")
    if not isinstance(records, list) or not isinstance(pull_requests, list):
        raise _InventoryError("trace records and pull_requests must be lists")
    prs = sorted((_pr(item) for item in pull_requests), key=lambda item: item["number"])
    if len({item["number"] for item in prs}) != len(prs):
        raise _InventoryError("pull request numbers must be unique")
    return {
        "schema": TRACE_SCHEMA,
        "records": [_record(item) for item in records],
        "pull_requests": prs,
    }


def _matches(selector: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    key, value = next(iter(selector.items()))
    candidate_key = {
        "candidate_id": "candidate_id",
        "branch": "branch",
        "ref": "ref",
        "pr_number": "pr_number",
        "worktree_path": "path",
    }[key]
    return candidate.get(candidate_key) == value


def _relation(trace: Json, candidate: Json) -> Json:
    matches = [item for item in trace["records"] if _matches(item["selector"], candidate)]
    empty = {
        "active_owners": [],
        "successors": [],
        "requirement_state": "unknown",
        "resolution": None,
        "worktree_owner": "unknown",
    }
    if not matches:
        return empty | {"status": "unknown", "blockers": ["ownership_successor_trace_missing"]}
    if len(matches) > 1:
        return empty | {"status": "ambiguous", "blockers": ["ownership_successor_trace_ambiguous"]}
    relation = {key: value for key, value in matches[0].items() if key != "selector"}
    blockers = []
    if len(relation["successors"]) > 1:
        blockers.append("successor_trace_ambiguous")
    if any(item["coverage"] == "unknown" for item in relation["successors"]):
        blockers.append("successor_coverage_unknown")
    return relation | {"status": "ambiguous" if blockers else "known", "blockers": blockers}


def _unpushed(root: Path, ref: str) -> int | None:
    try:
        return int(_git(root, "rev-list", "--count", ref, "--not", "--remotes").strip())
    except (ValueError, _InventoryError):
        return None


def _complete_successor(relation: Json) -> bool:
    return (
        relation["status"] == "known"
        and len(relation["successors"]) == 1
        and relation["successors"][0]["coverage"] == "complete"
    )


def _classify(candidate: Json) -> None:
    semantic, user, relation = (
        candidate["semantic_diff"],
        candidate["user_state"],
        candidate["trace"],
    )
    owners = sorted(set(relation["active_owners"]) | set(candidate["implicit_active_owners"]))
    blockers = set(relation["blockers"])
    protections = {
        "primary_worktree": user.get("primary_worktree") is True,
        "user_managed_worktree": user.get("worktree_owner") == "user",
        "dirty_worktree": user.get("dirty") is True,
        "untracked_worktree_state": user.get("untracked_count") not in (None, 0),
        "unpushed_local_commits": user.get("unpushed_commits") not in (None, 0),
        "dirty_linked_worktree": bool(user.get("dirty_linked_worktrees")),
    }
    protected = any(protections.values())
    blockers.update(name for name, present in protections.items() if present)
    if user.get("status") == "unknown":
        blockers.add("user_state_unverifiable")
    if candidate["kind"] == "local_branch" and user.get("linked_worktrees"):
        blockers.add("linked_worktree_must_be_cleaned_first")
    if candidate["kind"] == "worktree" and relation["worktree_owner"] == "unknown":
        blockers.add("worktree_owner_unknown")

    if protected:
        state = "protected_user_state"
    elif owners or relation["requirement_state"] == "unresolved":
        blockers.update(f"active_owner:{owner}" for owner in owners)
        if relation["requirement_state"] == "unresolved":
            blockers.add("unresolved_requirement")
        state = "active"
    elif semantic["status"] == "present":
        blockers.add("unique_semantic_delta")
        state = "superseded" if _complete_successor(relation) else "needs_extraction"
    elif semantic["status"] == "unknown":
        blockers.add("semantic_delta_unverifiable")
        state = "needs_verification"
    elif relation["status"] != "known" or relation["requirement_state"] == "unknown":
        blockers.add("ownership_or_requirement_unverifiable")
        state = "needs_verification"
    elif _complete_successor(relation) and relation["resolution"] is None:
        blockers.add("missing_resolution_trace")
        state = "superseded"
    elif relation["resolution"] is None:
        blockers.add("missing_resolution_trace")
        state = "merged_equivalent"
    elif not blockers:
        state = "orphan_safe_to_remove"
    else:
        blockers.add("cleanup_preconditions_incomplete")
        state = "needs_verification"

    if state == "orphan_safe_to_remove" and blockers:
        state = "needs_verification"
    if state not in _STATES:
        raise AssertionError(f"unknown orphan classification: {state}")
    actions = {
        "active": "retain and follow the active Issue/PR or unresolved requirement",
        "merged_equivalent": "record the main/resolution trace, then re-run inventory",
        "superseded": "verify successor coverage reaches main and record resolution",
        "orphan_safe_to_remove": "select this identity for the existing cleanup executor",
        "needs_extraction": "extract only the unique delta onto a latest-main Issue branch",
        "needs_verification": "obtain missing semantic, owner, successor, or user-state evidence",
        "protected_user_state": "preserve state until its user owner publishes or removes it",
    }
    if "linked_worktree_must_be_cleaned_first" in blockers:
        actions[state] = "classify and clean the linked worktree before the local branch"
    candidate.update(
        {
            "classification": state,
            "active_owners": owners,
            "cleanup_blockers": sorted(blockers),
            "recommended_action": actions[state],
        }
    )


def _candidate(candidate_id: str, kind: str, commit: str, **identity: object) -> Json:
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "ref": identity.get("ref"),
        "branch": identity.get("branch"),
        "commit": commit,
        "path": identity.get("path"),
        "pr_number": identity.get("pr_number"),
    }


def _finish(
    candidate: Json,
    semantic: Json,
    relation: Json,
    user_state: Json,
    owners: Sequence[str] = (),
) -> Json:
    candidate.update(
        {
            "semantic_diff": semantic,
            "trace": relation,
            "user_state": user_state,
            "implicit_active_owners": sorted(set(owners)),
        }
    )
    _classify(candidate)
    return candidate


def build_inventory(root: Path, main_ref: str, trace: Json) -> Json:
    """Build the canonical read-only branch, PR, and worktree inventory."""
    root = root.resolve()
    main = _resolve(root, main_ref)
    refs, worktrees, prs = _branch_refs(root), _worktrees(root), trace["pull_requests"]
    open_prs: dict[str, list[str]] = {}
    for pr in prs:
        if pr["state"] == "open":
            open_prs.setdefault(pr["head_ref"], []).append(f"pr:{pr['number']}")
    statuses = {row["path"]: _worktree_state(Path(row["path"])) for row in worktrees}
    linked: dict[str, list[str]] = {}
    for row in worktrees:
        if row["ref"]:
            linked.setdefault(row["ref"], []).append(row["path"])

    candidates = []
    for row in refs:
        if row["branch"] == "main" or row["ref"] == main_ref:
            continue
        local = row["ref"].startswith("refs/heads/")
        remote = row["ref"].removeprefix("refs/remotes/")
        item = _candidate(
            f"branch:local:{row['branch']}" if local else f"branch:remote:{remote}",
            "local_branch" if local else "remote_branch",
            row["commit"],
            ref=row["ref"],
            branch=row["branch"],
        )
        paths = sorted(linked.get(row["ref"], []))
        user = {
            "status": "observed",
            "primary_worktree": False,
            "worktree_owner": None,
            "dirty": None,
            "untracked_count": None,
            "unpushed_commits": _unpushed(root, row["ref"]) if local else 0,
            "linked_worktrees": paths,
            "dirty_linked_worktrees": sorted(
                path for path in paths if statuses[path]["dirty"] is True
            ),
        }
        if user["unpushed_commits"] is None:
            user["status"] = "unknown"
        candidates.append(
            _finish(
                item,
                _semantic(root, main, row["commit"]),
                _relation(trace, item),
                user,
                open_prs.get(row["branch"], []),
            )
        )

    for row in worktrees:
        name = _branch_name(row["ref"]) if row["ref"] else None
        item = _candidate(
            f"worktree:{row['path']}",
            "worktree",
            row["commit"],
            ref=row["ref"] or None,
            branch=name,
            path=row["path"],
        )
        relation = _relation(trace, item)
        status = statuses[row["path"]]
        user = {
            "status": status["status"],
            "primary_worktree": Path(row["path"]).resolve() == root,
            "worktree_owner": relation["worktree_owner"],
            "dirty": status["dirty"],
            "untracked_count": status["untracked_count"],
            "unpushed_commits": _unpushed(root, row["ref"]) if row["ref"] else None,
            "linked_worktrees": [],
            "dirty_linked_worktrees": [],
            "locked": row["locked"],
            "prunable": row["prunable"],
            "detached": row["detached"],
            "bare": row["bare"],
            "status_entries": status["entries"],
            "status_error": status["error"],
        }
        candidates.append(
            _finish(
                item,
                _semantic(root, main, row["commit"]),
                relation,
                user,
                open_prs.get(name or "", []),
            )
        )

    for pr in prs:
        item = _candidate(
            f"pr:{pr['number']}",
            "pr_head",
            pr["head_sha"],
            branch=pr["head_ref"],
            pr_number=pr["number"],
        )
        item.update({"pr_state": pr["state"], "pr_url": pr["url"]})
        candidates.append(
            _finish(
                item,
                _semantic(root, main, pr["head_sha"]),
                _relation(trace, item),
                {
                    "status": "observed",
                    "primary_worktree": False,
                    "worktree_owner": None,
                    "dirty": None,
                    "untracked_count": None,
                    "unpushed_commits": 0,
                    "linked_worktrees": [],
                    "dirty_linked_worktrees": [],
                },
                (f"pr:{pr['number']}",) if pr["state"] == "open" else (),
            )
        )

    candidates.sort(key=lambda item: item["candidate_id"])
    payload: Json = {
        "schema": INVENTORY_SCHEMA,
        "policy_owner": POLICY_OWNER,
        "repository_root": root.as_posix(),
        "main": {"ref": main_ref, "commit": main},
        "trace_schema": trace["schema"],
        "candidate_count": len(candidates),
        "classification_counts": dict(
            sorted(Counter(item["classification"] for item in candidates).items())
        ),
        "candidates": candidates,
        "cleanup_contract": {
            "mutation_owner": "existing branch/PR/worktree cleanup executor",
            "inventory_is_read_only": True,
            "age_is_authorization_evidence": False,
            "explicit_selection_required": True,
            "live_inventory_recheck_required": True,
            "allowed_classification": "orphan_safe_to_remove",
            "authorization_command": "orphan_lifecycle.py authorize-cleanup",
            "required_post_cleanup_readback": [
                "candidate_identity",
                "mutation_command",
                "mutation_result",
                "post_cleanup_ref_or_path_state",
                "preserved_main_or_successor_trace",
                "related_issue_or_pr_comment",
            ],
        },
    }
    payload["inventory_digest"] = _inventory_digest(payload)
    return payload


def authorize_cleanup(
    inventory: Mapping[str, object],
    *,
    fresh_inventory: Mapping[str, object],
    expected_digest: str,
    selections: Sequence[str],
) -> Json:
    """Authorize safe selections only while the live inventory is unchanged."""
    stored = inventory.get("inventory_digest")
    fresh = fresh_inventory.get("inventory_digest")
    blockers = []
    if inventory.get("schema") != INVENTORY_SCHEMA:
        blockers.append("inventory_schema_mismatch")
    if not isinstance(stored, str) or stored != _inventory_digest(inventory):
        blockers.append("inventory_digest_invalid")
    if expected_digest != stored:
        blockers.append("selection_inventory_digest_mismatch")
    if fresh_inventory.get("schema") != INVENTORY_SCHEMA:
        blockers.append("live_inventory_schema_mismatch")
    if not isinstance(fresh, str) or fresh != _inventory_digest(fresh_inventory):
        blockers.append("live_inventory_digest_invalid")
    if fresh != stored:
        blockers.append("live_inventory_digest_mismatch")
    if not selections:
        blockers.append("explicit_selection_missing")
    if len(selections) != len(set(selections)):
        blockers.append("duplicate_selection")

    raw_candidates = inventory.get("candidates")
    candidates = (
        {
            item.get("candidate_id"): item
            for item in raw_candidates
            if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
        }
        if isinstance(raw_candidates, list)
        else {}
    )
    if not isinstance(raw_candidates, list):
        blockers.append("inventory_candidates_invalid")
    decisions = []
    for candidate_id in selections:
        reasons = list(blockers)
        candidate = candidates.get(candidate_id)
        state = candidate.get("classification") if candidate else None
        if candidate is None:
            reasons.append("candidate_not_in_inventory")
        elif state != "orphan_safe_to_remove":
            reasons.append("candidate_not_orphan_safe_to_remove")
        if candidate is not None:
            candidate_blockers = candidate.get("cleanup_blockers")
            if not isinstance(candidate_blockers, list):
                reasons.append("candidate_blockers_invalid")
            elif candidate_blockers:
                reasons.append("candidate_has_cleanup_blockers")
        decisions.append(
            {
                "candidate_id": candidate_id,
                "classification": state,
                "decision": "authorized" if not reasons else "refused",
                "blockers": sorted(set(reasons)),
            }
        )
    status = (
        "authorized"
        if decisions and all(item["decision"] == "authorized" for item in decisions)
        else "refused"
    )
    contract = inventory.get("cleanup_contract")
    payload: Json = {
        "schema": ADMISSION_SCHEMA,
        "policy_owner": POLICY_OWNER,
        "status": status,
        "inventory_digest": stored,
        "live_inventory_digest": fresh,
        "expected_inventory_digest": expected_digest,
        "explicit_selections": list(selections),
        "decisions": decisions,
        "mutation_performed": False,
        "executor_obligations": (
            contract.get("required_post_cleanup_readback", [])
            if isinstance(contract, dict)
            else []
        ),
    }
    payload["admission_digest"] = _digest(payload)
    return payload


def _write(path: Path | None, payload: Json) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory")
    inventory.add_argument("--root", type=Path, default=Path.cwd())
    inventory.add_argument("--main-ref", default="refs/remotes/origin/main")
    inventory.add_argument("--trace", type=Path)
    inventory.add_argument("--output", type=Path)
    authorize = commands.add_parser("authorize-cleanup")
    authorize.add_argument("--inventory", type=Path, required=True)
    authorize.add_argument("--inventory-digest", required=True)
    authorize.add_argument("--root", type=Path, default=Path.cwd())
    authorize.add_argument("--trace", type=Path)
    authorize.add_argument("--select", action="append", default=[], dest="selections")
    authorize.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run inventory or cleanup admission."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            _write(args.output, build_inventory(args.root, args.main_ref, load_trace(args.trace)))
            return 0
        inventory = _read_json(args.inventory)
        main = inventory.get("main")
        if not isinstance(main, dict) or not isinstance(main.get("ref"), str):
            raise _InventoryError("inventory main ref is missing")
        fresh_inventory = build_inventory(args.root, main["ref"], load_trace(args.trace))
        payload = authorize_cleanup(
            inventory,
            fresh_inventory=fresh_inventory,
            expected_digest=args.inventory_digest,
            selections=args.selections,
        )
        _write(args.output, payload)
        return 0 if payload["status"] == "authorized" else 1
    except _InventoryError as exc:
        print(f"ORPHAN_LIFECYCLE_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
