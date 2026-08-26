#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enforces runtime parent-orchestration-only mutation authority from authenticated child identity, writer-target environment, and scope receipts.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns parent orchestration and child write contracts.
# upstream implementation ./workspace_scope.py owns canonical role write-scope derivation.
# downstream implementation ../../.codex/hooks/hook_dispatcher.py applies the PreToolUse decision.
# downstream implementation ../../tests/agent_tools/test_mutation_authority.py validates parent rejection and child-scope admission.
# @dependency-end
"""Pure runtime mutation authority for the active PreToolUse hook."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

IDENTITY_SCHEMA = "agent-canon.runtime-agent-identity.v1"
MUTATION_DECISION_SCHEMA = "agent-canon.mutation-authority.v1"
RUNTIME_AGENT_ID_ENV = "AGENT_CANON_RUNTIME_AGENT_ID"
RUNTIME_ROLE_ID_ENV = "AGENT_CANON_RUNTIME_ROLE_ID"
RUNTIME_PARENT_AGENT_ID_ENV = "AGENT_CANON_RUNTIME_PARENT_AGENT_ID"
WRITER_CHECKOUT_ROOT_ENV = "AGENT_CANON_CHECKOUT_ROOT"
WRITER_BRANCH_ENV = "AGENT_CANON_CHECKOUT_BRANCH"
WRITER_ALLOWED_PATHS_ENV = "AGENT_CANON_WRITER_ALLOWED_PATHS"
IDENTITY_RECEIPT_RELATIVE = Path("runtime") / "agent_identity.json"
PARENT_ROLE_IDS = frozenset({"parent", "sol_parent", "manager", "manager_reviewer"})
MUTATING_TOOLS = frozenset({"apply_patch", "python", "python3", "Bash", "bash"})
READONLY_COMMANDS = frozenset(
    {
        "cat",
        "find",
        "git",
        "head",
        "ls",
        "pwd",
        "rg",
        "sed",
        "tail",
        "type",
        "which",
    }
)
READONLY_GIT_SUBCOMMANDS = frozenset(
    {"branch", "diff", "log", "ls-files", "remote", "rev-parse", "show", "status"}
)
MUTATING_COMMANDS = frozenset(
    {"apply_patch", "cargo", "chmod", "cp", "docker", "make", "mkdir", "mv", "perl", "pytest", "python", "python3", "rm", "sed", "tee", "touch"}
)
PATCH_PATH_RE = re.compile(r"^\*\*\*\s+(?:Update|Add|Delete) File:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class MutationAuthorityDecision:
    status: str
    reason: str
    mutation: bool
    actor_id: str = ""
    role_id: str = ""
    parent_agent_id: str = ""
    scope_digest: str = ""
    mutation_paths: tuple[str, ...] = ()
    evidence_ref: str = ""
    command_sha256: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": MUTATION_DECISION_SCHEMA,
            "status": self.status,
            "reason": self.reason,
            "mutation": self.mutation,
            "actor_id": self.actor_id,
            "role_id": self.role_id,
            "parent_agent_id": self.parent_agent_id,
            "scope_digest": self.scope_digest,
            "mutation_paths": list(self.mutation_paths),
            "evidence_ref": self.evidence_ref,
            "command_sha256": self.command_sha256,
        }


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return value if isinstance(value, str) else ""


def _relative_paths(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None
    paths = tuple(str(item) for item in value)
    if any(Path(item).is_absolute() or ".." in Path(item).parts for item in paths):
        return None
    return paths


def _scope_digest(allowed_files: tuple[str, ...], allowed_directories: tuple[str, ...]) -> str:
    return hashlib.sha256(
        _canonical({"allowed_files": list(allowed_files), "allowed_directories": list(allowed_directories)})
    ).hexdigest()


def _read_identity(report_dir: Path) -> tuple[dict[str, object] | None, str]:
    path = report_dir / IDENTITY_RECEIPT_RELATIVE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, str(path)
    if not isinstance(value, dict):
        return None, str(path)
    expected = {
        "schema",
        "run_id",
        "agent_id",
        "role_id",
        "parent_agent_id",
        "authority",
        "allowed_files",
        "allowed_directories",
        "scope_digest",
        "status",
        "receipt_sha256",
    }
    if set(value) != expected or value.get("schema") != IDENTITY_SCHEMA or value.get("status") != "active":
        return None, str(path)
    allowed_files = _relative_paths(value.get("allowed_files"))
    allowed_directories = _relative_paths(value.get("allowed_directories"))
    receipt_sha = value.get("receipt_sha256")
    if allowed_files is None or allowed_directories is None or not isinstance(receipt_sha, str):
        return None, str(path)
    if value.get("scope_digest") != _scope_digest(allowed_files, allowed_directories):
        return None, str(path)
    unsigned = dict(value)
    unsigned.pop("receipt_sha256", None)
    if hashlib.sha256(_canonical(unsigned)).hexdigest() != receipt_sha:
        return None, str(path)
    return value, str(path)


def _command_segments(command: str) -> tuple[tuple[str, ...], ...]:
    try:
        tokens = tuple(shlex.shlex(command, posix=True, punctuation_chars=";&|()<>"))
    except ValueError:
        return ()
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in {";", "&&", "||", "|", "&", "(", ")"}:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return tuple(tuple(segment) for segment in segments if segment)


def _bash_mutation(command: str) -> tuple[bool, tuple[str, ...], str]:
    segments = _command_segments(command)
    if not segments:
        return True, (), "command_unparseable"
    paths: list[str] = []
    for segment in segments:
        if any(token in {">", ">>", "<"} for token in segment):
            return True, tuple(paths), "shell_redirection"
        command_index = next((index for index, token in enumerate(segment) if "=" not in token or token.startswith("./")), None)
        if command_index is None:
            return True, tuple(paths), "command_missing"
        verb = segment[command_index]
        while verb in {"env", "command", "sudo", "exec"} and command_index + 1 < len(segment):
            command_index += 1
            while command_index < len(segment) and "=" in segment[command_index]:
                command_index += 1
            if command_index >= len(segment):
                return True, tuple(paths), "command_missing"
            verb = segment[command_index]
        if verb == "git":
            git_args = segment[command_index + 1 :]
            sub_index = next((index for index, token in enumerate(git_args) if not token.startswith("-")), None)
            subcommand = git_args[sub_index] if sub_index is not None else ""
            sub_args = git_args[sub_index + 1 :] if sub_index is not None else ()
            if subcommand in {"worktree", "stash"}:
                nested = next((token for token in sub_args if not token.startswith("-")), "")
                if (subcommand == "worktree" and nested in {"list", "lock", "unlock"}) or (subcommand == "stash" and nested in {"list", "show"}):
                    continue
            if subcommand == "clean" and any(token in {"-n", "--dry-run"} or (token.startswith("-") and "n" in token[1:]) for token in sub_args):
                continue
            if subcommand in {"switch", "checkout"} and any(token in {"-h", "--help"} for token in sub_args):
                continue
            if subcommand in READONLY_GIT_SUBCOMMANDS and subcommand not in {"branch", "worktree", "stash"}:
                continue
            if subcommand == "branch" and (not sub_args or any(token in {"--list", "-a", "-r", "-v", "-vv", "--show-current", "--edit-description", "--set-upstream-to", "--unset-upstream", "-u"} or token.startswith("--set-upstream-to=") or token.startswith("-u") for token in sub_args)):
                continue
            paths.extend(token for token in sub_args if not token.startswith("-"))
            return True, tuple(paths), f"git_{subcommand or 'unknown'}"
        if verb in {"bash", "sh", "zsh"}:
            wrapper_args = segment[command_index + 1 :]
            command_flag = next((index for index, token in enumerate(wrapper_args) if token in {"-c", "-lc", "--command"}), None)
            if command_flag is None or command_flag + 1 >= len(wrapper_args):
                return True, tuple(paths), "shell_wrapper_unresolved"
            inner = " ".join(wrapper_args[command_flag + 1 :])
            inner_mutation, inner_paths, inner_reason = _bash_mutation(inner)
            return inner_mutation, inner_paths, f"{verb}_wrapper_{inner_reason}"
        if verb in MUTATING_COMMANDS:
            operands = [
                token for token in segment[command_index + 1 :] if not token.startswith("-")
            ]
            if verb in {"cp", "mv"} and len(operands) > 1:
                paths.append(operands[-1])
            else:
                paths.extend(operands)
            return True, tuple(paths), f"command_{verb}"
        if verb not in READONLY_COMMANDS:
            continue
    return False, (), "read_only_command"


def _mutation_request(tool_name: str, tool_input: Mapping[str, object]) -> tuple[bool, tuple[str, ...], str, str]:
    if tool_name == "apply_patch":
        patch = tool_input.get("patch")
        if not isinstance(patch, str):
            return True, (), "patch_payload_missing", ""
        return True, tuple(match.group(1).strip() for match in PATCH_PATH_RE.finditer(patch)), "apply_patch", hashlib.sha256(patch.encode()).hexdigest()
    if tool_name in {"python", "python3"}:
        return True, (), "python_execution", ""
    if tool_name in {"Bash", "bash"}:
        command = tool_input.get("command", tool_input.get("cmd"))
        if not isinstance(command, str):
            return True, (), "bash_command_missing", ""
        mutation, paths, reason = _bash_mutation(command)
        return mutation, paths, reason, hashlib.sha256(command.encode()).hexdigest()
    return False, (), "not_mutating_tool", ""


def _writer_target_violation(
    environment: Mapping[str, str],
    active_root: Path,
    reason: str,
    command: str,
) -> str | None:
    """Return a target-boundary failure when the active writer target is set."""
    declared_root = environment.get(WRITER_CHECKOUT_ROOT_ENV, "").strip()
    declared_branch = environment.get(WRITER_BRANCH_ENV, "").strip()
    declared_paths = environment.get(WRITER_ALLOWED_PATHS_ENV, "").strip()
    if not declared_root and not declared_branch and not declared_paths:
        return None
    if not declared_root or not declared_branch:
        return "writer_target_required"
    if declared_paths:
        try:
            parsed_paths = json.loads(declared_paths)
        except (TypeError, json.JSONDecodeError):
            return "writer_target_allowed_paths_invalid"
        if not isinstance(parsed_paths, list) or not parsed_paths:
            return "writer_target_allowed_paths_invalid"
        if any(
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or "\\" in path
            or "//" in path
            for path in parsed_paths
        ):
            return "writer_target_allowed_paths_invalid"
    target_root = Path(declared_root).expanduser()
    if not target_root.is_absolute():
        return "writer_target_checkout_root_not_absolute"
    if target_root.resolve(strict=False) != active_root.resolve(strict=False):
        return "writer_target_checkout_root_mismatch"
    if reason in {"git_checkout", "git_switch"}:
        return "writer_target_branch_switch_forbidden"
    for segment in _command_segments(command):
        if not segment:
            continue
        if segment[0] == "cd" and len(segment) > 1:
            candidate = Path(segment[1]).expanduser()
            if not candidate.is_absolute():
                candidate = target_root / candidate
            if candidate.resolve(strict=False) != target_root.resolve(strict=False):
                return "writer_target_checkout_root_mismatch"
        if segment[0] == "git":
            for index, token in enumerate(segment[:-1]):
                if token == "-C":
                    candidate = Path(segment[index + 1]).expanduser()
                    if not candidate.is_absolute():
                        candidate = target_root / candidate
                    if candidate.resolve(strict=False) != target_root.resolve(strict=False):
                        return "writer_target_checkout_root_mismatch"
    return None


def _allowed_path(path: str, active_root: Path, allowed_files: tuple[str, ...], allowed_directories: tuple[str, ...]) -> bool:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    normalized = candidate.as_posix()
    if normalized in allowed_files:
        return True
    return any(normalized == directory or normalized.startswith(directory.rstrip("/") + "/") for directory in allowed_directories)


def evaluate_mutation_authority(
    payload: object,
    *,
    report_dir: Path | None,
    active_root: Path,
    environment: Mapping[str, str],
    hook_spool_root: Path | None = None,
) -> MutationAuthorityDecision:
    """Correlate actor identity, child scope, and one real mutation request."""
    if not isinstance(payload, dict):
        return MutationAuthorityDecision("not_applicable", "payload_not_mapping", False)
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return MutationAuthorityDecision("blocked", "tool_identity_missing", True)
    mutation, paths, reason, command_sha = _mutation_request(tool_name, tool_input)
    if not mutation:
        return MutationAuthorityDecision("not_applicable", reason, False)
    command_value = ""
    if tool_name in {"Bash", "bash"}:
        candidate = tool_input.get("command", tool_input.get("cmd"))
        if isinstance(candidate, str):
            command_value = candidate
    target_violation = _writer_target_violation(
        environment,
        active_root,
        reason,
        command_value,
    )
    if target_violation is not None:
        return MutationAuthorityDecision(
            "blocked",
            target_violation,
            True,
            mutation_paths=paths,
            command_sha256=command_sha,
        )
    if report_dir is None:
        return MutationAuthorityDecision("blocked", "blocked_authority_required", True, mutation_paths=paths, command_sha256=command_sha)
    identity, evidence_ref = _read_identity(report_dir)
    if identity is None:
        return MutationAuthorityDecision("blocked", "blocked_authority_required", True, mutation_paths=paths, evidence_ref=evidence_ref, command_sha256=command_sha)
    actor_id = _text(identity, "agent_id")
    role_id = _text(identity, "role_id")
    parent_agent_id = _text(identity, "parent_agent_id")
    if environment.get(RUNTIME_AGENT_ID_ENV) != actor_id or environment.get(RUNTIME_ROLE_ID_ENV) != role_id or environment.get(RUNTIME_PARENT_AGENT_ID_ENV) != parent_agent_id:
        return MutationAuthorityDecision("blocked", "runtime_identity_mismatch", True, actor_id, role_id, parent_agent_id, str(identity.get("scope_digest", "")), paths, evidence_ref, command_sha)
    if role_id in PARENT_ROLE_IDS or identity.get("authority") != "write_capable_child":
        return MutationAuthorityDecision("blocked", "parent_mutation_forbidden", True, actor_id, role_id, parent_agent_id, str(identity.get("scope_digest", "")), paths, evidence_ref, command_sha)
    if hook_spool_root is None or not any(
        _spawn_event_matches(path, actor_id, role_id, str(identity.get("scope_digest", "")))
        for path in hook_spool_root.glob("**/*.json")
    ):
        return MutationAuthorityDecision("blocked", "child_spawn_evidence_missing", True, actor_id, role_id, parent_agent_id, str(identity.get("scope_digest", "")), paths, evidence_ref, command_sha)
    allowed_files = _relative_paths(identity.get("allowed_files")) or ()
    allowed_directories = _relative_paths(identity.get("allowed_directories")) or ()
    explicit_allowed = environment.get(WRITER_ALLOWED_PATHS_ENV, "").strip()
    if explicit_allowed:
        try:
            parsed_allowed = json.loads(explicit_allowed)
        except (TypeError, json.JSONDecodeError):
            return MutationAuthorityDecision(
                "blocked",
                "writer_target_allowed_paths_invalid",
                True,
                actor_id,
                role_id,
                parent_agent_id,
                str(identity.get("scope_digest", "")),
                paths,
                evidence_ref,
                command_sha,
            )
        if not isinstance(parsed_allowed, list) or not all(
            isinstance(path, str) and path for path in parsed_allowed
        ):
            return MutationAuthorityDecision(
                "blocked",
                "writer_target_allowed_paths_invalid",
                True,
                actor_id,
                role_id,
                parent_agent_id,
                str(identity.get("scope_digest", "")),
                paths,
                evidence_ref,
                command_sha,
            )
        normalized_allowed = tuple(str(path) for path in parsed_allowed)
        allowed_files = tuple(
            path.rstrip("/") for path in normalized_allowed if not path.endswith("/")
        )
        allowed_directories = tuple(
            path.rstrip("/") for path in normalized_allowed if path.endswith("/")
        )
    target_metadata_only = (
        bool(environment.get(WRITER_CHECKOUT_ROOT_ENV, "").strip())
        and reason in {"git_commit", "git_merge", "git_rebase"}
    )
    if not target_metadata_only and (
        not paths
        or not all(
            _allowed_path(path, active_root, allowed_files, allowed_directories)
            for path in paths
        )
    ):
        return MutationAuthorityDecision("blocked", "mutation_scope_outside_child_receipt", True, actor_id, role_id, parent_agent_id, str(identity.get("scope_digest", "")), paths, evidence_ref, command_sha)
    return MutationAuthorityDecision("allowed", "child_scope_verified", True, actor_id, role_id, parent_agent_id, str(identity.get("scope_digest", "")), paths, evidence_ref, command_sha)


def _spawn_event_matches(path: Path, actor_id: str, role_id: str, scope_digest: str) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(value, dict):
        return False
    return (
        value.get("subagent_event_kind") == "spawn"
        and value.get("subagent_target") == actor_id
        and value.get("subagent_agent_type") in {role_id, "worker", "spark_worker"}
        and value.get("mutation_scope_digest") == scope_digest
    )


def mutation_block_payload(decision: MutationAuthorityDecision) -> dict[str, object]:
    return {
        "decision": "block",
        "reason": "Repository mutation is restricted to an authenticated write-capable child scope.",
        "next_action": "launch_or_resume_write_capable_child_with_runtime_identity_receipt",
        "mutation_authority": decision.reason,
    }
