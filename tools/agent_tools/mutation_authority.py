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

try:
    from .writer_target import (
        WRITER_TARGET_PACKET_RELATIVE,
        WriterTarget,
        WriterTargetError,
        read_writer_target_packet,
    )
except ImportError:
    from writer_target import (  # type: ignore[no-redef]
        WRITER_TARGET_PACKET_RELATIVE,
        WriterTarget,
        WriterTargetError,
        read_writer_target_packet,
    )

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
SHELL_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_CONTROL_TOKENS = frozenset(
    {";", "&&", "||", "|", "&", "(", ")", ";;", ";&", ";;&"}
)
SHELL_COMMAND_PREFIXES = frozenset({"env", "command", "sudo", "exec", "builtin", "time", "!"})
OPAQUE_SHELL_COMMANDS = frozenset({".", "source", "eval", "xargs"})
SHELL_ANALYSIS_MAX_DEPTH = 32
UNRESOLVED_SHELL_PATH = "/__agent_canon_unresolved_shell_path__"
GIT_NON_PATH_VALUE_OPTIONS = frozenset(
    {
        "-m",
        "--message",
        "--author",
        "--cleanup",
        "--reuse-message",
        "--reedit-message",
        "--fixup",
        "--squash",
        "--gpg-sign",
        "--format",
        "--pretty",
        "--date",
        "--output",
    }
)


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
        if token in SHELL_CONTROL_TOKENS:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return tuple(tuple(segment) for segment in segments if segment)


def _backtick_bodies(command: str) -> tuple[tuple[str, ...], bool]:
    """Extract executable backtick substitutions without treating literals as code."""
    bodies: list[str] = []
    current: list[str] | None = None
    single_quoted = False
    escaped = False
    for character in command:
        if escaped:
            if current is not None:
                current.append(character)
            escaped = False
            continue
        if character == "\\" and not single_quoted:
            escaped = True
            if current is not None:
                current.append(character)
            continue
        if character == "'" and current is None:
            single_quoted = not single_quoted
            continue
        if character == "#" and current is None and not single_quoted:
            break
        if character == "`" and not single_quoted:
            if current is None:
                current = []
            else:
                bodies.append("".join(current))
                current = None
            continue
        if current is not None:
            current.append(character)
    # An unmatched backtick is retained as ordinary shell text here.  The
    # canonical Git safety parser owns malformed/protected Git substitutions;
    # treating every unmatched non-Git backtick as a write would regress the
    # existing read-only command contract.
    return tuple(bodies), False


def _shell_dynamic_expansion(value: str) -> bool:
    """Return whether a nested shell string contains an unknown variable expansion."""
    single_quoted = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and not single_quoted:
            escaped = True
            continue
        if character == "'":
            single_quoted = not single_quoted
            continue
        if single_quoted or character != "$" or index + 1 >= len(value):
            continue
        following = value[index + 1]
        if following.isalpha() or following == "_" or following == "{":
            return True
    return False


def _shell_path(
    value: str,
    *,
    cwd: Path,
    active_root: Path | None,
) -> tuple[str, bool]:
    """Normalize a shell path and report whether it leaves the active checkout."""
    if (
        not value
        or value.startswith("~")
        or any(marker in value for marker in ("$", "`", "*", "?", "[", "]", "<(", ">("))
    ):
        # Scope resolution must never guess the result of an expansion,
        # glob, process substitution, or shell metacharacter in a path.
        return UNRESOLVED_SHELL_PATH, True
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    if active_root is None:
        return str(candidate), candidate.is_absolute()
    resolved = candidate.resolve(strict=False)
    root = active_root.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return str(resolved), True
    return (relative.as_posix() if relative.parts else "."), False


def _command_index(segment: tuple[str, ...]) -> int | None:
    """Find the executable token after assignments and shell command prefixes."""
    index = 0
    while index < len(segment):
        token = segment[index]
        if SHELL_ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if token in SHELL_COMMAND_PREFIXES:
            index += 1
            if token == "env":
                while index < len(segment) and SHELL_ASSIGNMENT_RE.match(segment[index]):
                    index += 1
            continue
        return index
    return None


def _git_subcommand(git_args: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Find a Git subcommand while consuming global options with their values."""
    index = 0
    value_options = {"-C", "--git-dir", "--work-tree", "-c", "--config-env"}
    while index < len(git_args):
        token = git_args[index]
        if token == "--":
            index += 1
            break
        if token in value_options:
            index += 2
            continue
        if any(token.startswith(option + "=") for option in value_options):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    if index >= len(git_args):
        return "", ()
    return git_args[index], git_args[index + 1 :]


def _git_repository_redirect(
    git_args: tuple[str, ...],
    *,
    cwd: Path,
    active_root: Path | None,
) -> tuple[tuple[str, ...], str | None]:
    """Find Git options that redirect work-tree or repository metadata."""
    paths: list[str] = []
    index = 0
    for index, token in enumerate(git_args):
        option: str | None = None
        value: str | None = None
        if token in {"--git-dir", "--work-tree"}:
            option = token
            if index + 1 >= len(git_args):
                return tuple(paths), "git_repository_redirect_unresolved"
            value = git_args[index + 1]
        elif token.startswith("--git-dir="):
            option, value = "--git-dir", token.removeprefix("--git-dir=")
        elif token.startswith("--work-tree="):
            option, value = "--work-tree", token.removeprefix("--work-tree=")
        if option is None or value is None:
            continue
        if not value:
            return tuple(paths), "git_repository_redirect_unresolved"
        normalized, _outside = _shell_path(value, cwd=cwd, active_root=active_root)
        paths.append(normalized)
        return tuple(paths), "git_repository_redirect"
    return tuple(paths), None


def _git_mutation_paths(
    sub_args: tuple[str, ...],
    *,
    cwd: Path,
    active_root: Path | None,
) -> tuple[str, ...]:
    """Return Git path operands without treating option values as paths."""
    paths: list[str] = []
    skip_value = False
    after_separator = False
    for token in sub_args:
        if skip_value:
            skip_value = False
            continue
        if after_separator:
            paths.append(_shell_path(token, cwd=cwd, active_root=active_root)[0])
            continue
        if token == "--":
            after_separator = True
            continue
        if token in GIT_NON_PATH_VALUE_OPTIONS:
            skip_value = True
            continue
        if any(token.startswith(option + "=") for option in GIT_NON_PATH_VALUE_OPTIONS):
            continue
        if token.startswith("-"):
            continue
        paths.append(_shell_path(token, cwd=cwd, active_root=active_root)[0])
    return tuple(paths)


def _analysis_reason(reasons: list[str]) -> str:
    """Prefer reasons that must fail closed over ordinary command descriptions."""
    if not reasons:
        return "read_only_command"
    for marker in (
        "unparseable",
        "unresolved",
        "repository_redirect",
        "cd_outside_checkout",
        "checkout_root_mismatch",
        "shell_redirection",
        "opaque",
    ):
        for reason in reasons:
            if marker in reason:
                return reason
    return reasons[-1]


def _bash_mutation_inner(
    command: str,
    *,
    active_root: Path | None,
    cwd: Path,
    depth: int,
) -> tuple[bool, tuple[str, ...], str]:
    if depth > SHELL_ANALYSIS_MAX_DEPTH:
        return True, (), "shell_wrapper_unparseable_depth"
    segments = _command_segments(command)
    if not segments:
        return True, (), "command_unparseable"
    paths: list[str] = []
    reasons: list[str] = []
    mutation = False

    backticks, unterminated_backtick = _backtick_bodies(command)
    if unterminated_backtick:
        mutation = True
        reasons.append("shell_wrapper_unparseable_backtick")
    for body in backticks:
        nested_mutation, nested_paths, nested_reason = _bash_mutation_inner(
            body,
            active_root=active_root,
            cwd=cwd,
            depth=depth + 1,
        )
        mutation = mutation or nested_mutation
        paths.extend(nested_paths)
        if nested_mutation:
            reasons.append(f"shell_substitution_{nested_reason}")

    for segment in segments:
        if any(token in {">", ">>"} for token in segment):
            mutation = True
            reasons.append("shell_redirection")
            for index, token in enumerate(segment[:-1]):
                if token in {">", ">>"}:
                    normalized, _outside = _shell_path(
                        segment[index + 1], cwd=cwd, active_root=active_root
                    )
                    paths.append(normalized)
        elif "<" in segment:
            mutation = True
            reasons.append("shell_redirection")
        command_index = _command_index(segment)
        if command_index is None:
            if not any(token in SHELL_CONTROL_TOKENS for token in segment):
                mutation = True
                reasons.append("command_missing")
            continue
        verb = segment[command_index]
        if verb == "cd":
            operands = [token for token in segment[command_index + 1 :] if token != "--"]
            if not operands or len(operands) > 1 or operands[0].startswith("-"):
                mutation = True
                reasons.append("shell_cd_unresolved")
                continue
            normalized, outside = _shell_path(
                operands[0], cwd=cwd, active_root=active_root
            )
            if outside:
                mutation = True
                paths.append(normalized)
                reasons.append("shell_cd_outside_checkout")
            elif active_root is not None:
                cwd = (active_root.resolve(strict=False) / normalized).resolve(strict=False)
            else:
                cwd = (cwd / operands[0]).resolve(strict=False)
            continue
        if verb == "git":
            git_args = segment[command_index + 1 :]
            redirect_paths, redirect_reason = _git_repository_redirect(
                git_args, cwd=cwd, active_root=active_root
            )
            if redirect_reason is not None:
                mutation = True
                paths.extend(redirect_paths)
                reasons.append(redirect_reason)
                continue
            subcommand, sub_args = _git_subcommand(git_args)
            if subcommand in {"worktree", "stash"}:
                nested = next((token for token in sub_args if not token.startswith("-")), "")
                if (subcommand == "worktree" and nested in {"list", "lock", "unlock"}) or (
                    subcommand == "stash" and nested in {"list", "show"}
                ):
                    continue
            if subcommand == "clean" and any(
                token in {"-n", "--dry-run"}
                or (token.startswith("-") and "n" in token[1:])
                for token in sub_args
            ):
                continue
            if subcommand in {"switch", "checkout"} and any(
                token in {"-h", "--help"} for token in sub_args
            ):
                continue
            if subcommand in READONLY_GIT_SUBCOMMANDS and subcommand not in {
                "branch",
                "worktree",
                "stash",
            }:
                continue
            if subcommand == "branch" and (
                not sub_args
                or any(
                    token
                    in {
                        "--list",
                        "-a",
                        "-r",
                        "-v",
                        "-vv",
                        "--show-current",
                        "--edit-description",
                        "--set-upstream-to",
                        "--unset-upstream",
                        "-u",
                    }
                    or token.startswith("--set-upstream-to=")
                    or token.startswith("-u")
                    for token in sub_args
                )
            ):
                continue
            mutation = True
            paths.extend(
                _git_mutation_paths(
                    sub_args,
                    cwd=cwd,
                    active_root=active_root,
                )
            )
            reasons.append(f"git_{subcommand or 'unknown'}")
            continue
        if verb in {"bash", "sh", "zsh"}:
            wrapper_args = segment[command_index + 1 :]
            command_flag = next(
                (
                    index
                    for index, token in enumerate(wrapper_args)
                    if token in {"-c", "-lc", "--command"}
                ),
                None,
            )
            if command_flag is None or command_flag + 1 >= len(wrapper_args):
                mutation = True
                reasons.append("shell_wrapper_unresolved")
                continue
            inner = wrapper_args[command_flag + 1]
            if _shell_dynamic_expansion(inner):
                mutation = True
                reasons.append("shell_wrapper_unparseable_expansion")
                continue
            nested_mutation, nested_paths, nested_reason = _bash_mutation_inner(
                inner,
                active_root=active_root,
                cwd=cwd,
                depth=depth + 1,
            )
            mutation = mutation or nested_mutation
            paths.extend(nested_paths)
            if nested_mutation:
                reasons.append(f"{verb}_wrapper_{nested_reason}")
            continue
        if verb in OPAQUE_SHELL_COMMANDS:
            mutation = True
            reasons.append("shell_opaque_command")
            continue
        if verb in MUTATING_COMMANDS:
            operands = [
                token
                for token in segment[command_index + 1 :]
                if not token.startswith("-")
            ]
            if verb in {"cp", "mv"} and len(operands) > 1:
                operands = operands[-1:]
            mutation = True
            paths.extend(
                _shell_path(token, cwd=cwd, active_root=active_root)[0]
                for token in operands
            )
            reasons.append(f"command_{verb}")
            continue
        if verb not in READONLY_COMMANDS:
            continue
    return mutation, tuple(paths), _analysis_reason(reasons)


def _repository_topic_clone_operation(command: str) -> str | None:
    """Classify only the canonical conflict-preserving clone lifecycle command."""
    segments = _command_segments(command)
    for segment in segments:
        if not segment:
            continue
        try:
            interpreter = next(
                index for index, token in enumerate(segment) if token in {"python", "python3"}
            )
        except StopIteration:
            continue
        arguments = segment[interpreter + 1 :]
        script_index = next(
            (
                index
                for index, token in enumerate(arguments)
                if Path(token).name == "repository_topic_clone.py"
            ),
            None,
        )
        if script_index is None or script_index + 1 >= len(arguments):
            continue
        operation = arguments[script_index + 1]
        if operation not in {"merge-main", "resume-merge", "finalize-merge"}:
            continue
        if len(segments) != 1:
            return "repository_topic_clone_compound"
        if operation in {"resume-merge", "finalize-merge"} and not {
            "--inventory",
            "--plan",
        }.issubset(arguments):
            return "repository_topic_clone_preservation_inputs_missing"
        return f"repository_topic_clone_{operation.replace('-', '_')}"
    return None


def _bash_mutation(
    command: str,
    *,
    active_root: Path | None = None,
    initial_cwd: Path | None = None,
) -> tuple[bool, tuple[str, ...], str]:
    """Classify every shell segment, retaining the effective cwd across segments."""
    root = active_root.resolve(strict=False) if active_root is not None else None
    cwd = (initial_cwd or root or Path.cwd()).resolve(strict=False)
    return _bash_mutation_inner(
        command,
        active_root=root,
        cwd=cwd,
        depth=0,
    )


def _mutation_request(
    tool_name: str,
    tool_input: Mapping[str, object],
    *,
    active_root: Path | None = None,
) -> tuple[bool, tuple[str, ...], str, str]:
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
        mutation, paths, reason = _bash_mutation(command, active_root=active_root)
        lifecycle_operation = _repository_topic_clone_operation(command)
        if lifecycle_operation is not None and lifecycle_operation != "repository_topic_clone_compound":
            return (
                mutation,
                (),
                lifecycle_operation,
                hashlib.sha256(command.encode()).hexdigest(),
            )
        if lifecycle_operation == "repository_topic_clone_compound":
            return (
                mutation,
                paths,
                lifecycle_operation,
                hashlib.sha256(command.encode()).hexdigest(),
            )
        return mutation, paths, reason, hashlib.sha256(command.encode()).hexdigest()
    return False, (), "not_mutating_tool", ""


def _writer_target_violation(
    environment: Mapping[str, str],
    active_root: Path,
    reason: str,
    command: str,
    target_root: str = "",
    target_branch: str = "",
) -> str | None:
    """Return a target-boundary failure when the active writer target is set."""
    declared_root = environment.get(WRITER_CHECKOUT_ROOT_ENV, "").strip()
    declared_branch = environment.get(WRITER_BRANCH_ENV, "").strip()
    declared_paths = environment.get(WRITER_ALLOWED_PATHS_ENV, "").strip()
    if not declared_root and not declared_branch and not declared_paths and not target_root:
        return None
    declared_root = declared_root or target_root
    declared_branch = declared_branch or target_branch
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
    target_root_path = Path(declared_root).expanduser()
    if not target_root_path.is_absolute():
        return "writer_target_checkout_root_not_absolute"
    if target_root_path.resolve(strict=False) != active_root.resolve(strict=False):
        return "writer_target_checkout_root_mismatch"
    if reason in {"git_checkout", "git_switch", "git_worktree", "git_branch"}:
        return "writer_target_branch_switch_forbidden"
    if "git_repository_redirect" in reason:
        return "writer_target_git_repository_redirect_forbidden"
    if "cd_outside_checkout" in reason or reason == "shell_cd_unresolved":
        return "writer_target_checkout_root_mismatch"
    for segment in _command_segments(command):
        if len(segment) > 1 and segment[0] == "cd":
            candidate = Path(segment[1]).expanduser()
            if not candidate.is_absolute():
                candidate = target_root_path / candidate
            if candidate.resolve(strict=False) != target_root_path.resolve(strict=False):
                return "writer_target_checkout_root_mismatch"
        if segment and segment[0] == "git":
            for index in range(len(segment) - 1):
                token = segment[index]
                if token == "-C":
                    candidate = Path(segment[index + 1]).expanduser()
                    if not candidate.is_absolute():
                        candidate = target_root_path / candidate
                    if candidate.resolve(strict=False) != target_root_path.resolve(strict=False):
                        return "writer_target_checkout_root_mismatch"
    return None


def _read_writer_target_packet(
    active_root: Path,
    environment: Mapping[str, str],
) -> tuple[WriterTarget | None, Mapping[str, object] | None, str | None]:
    """Read and validate the ignored static target packet for this checkout."""
    try:
        target, identity = read_writer_target_packet(active_root)
    except WriterTargetError as exc:
        return None, None, str(exc)
    declared_root = environment.get(WRITER_CHECKOUT_ROOT_ENV, "").strip()
    declared_branch = environment.get(WRITER_BRANCH_ENV, "").strip()
    if declared_root and Path(declared_root).expanduser().resolve(strict=False) != Path(target.normalized_root):
        return None, None, "writer_target_packet_identity_mismatch"
    if declared_branch and declared_branch != target.branch:
        return None, None, "writer_target_packet_identity_mismatch"
    return target, identity, None


def _allowed_path(path: str, active_root: Path, allowed_files: tuple[str, ...], allowed_directories: tuple[str, ...]) -> bool:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    normalized = candidate.as_posix()
    if normalized == "." and "." in allowed_files:
        return True
    if "." in allowed_files:
        return True
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
    mutation, paths, reason, command_sha = _mutation_request(
        tool_name,
        tool_input,
        active_root=active_root,
    )
    if not mutation:
        return MutationAuthorityDecision("not_applicable", reason, False)
    command_value = ""
    if tool_name in {"Bash", "bash"}:
        candidate = tool_input.get("command", tool_input.get("cmd"))
        if isinstance(candidate, str):
            command_value = candidate
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
    writer_target, _packet_identity, packet_error = _read_writer_target_packet(
        active_root,
        environment,
    )
    if packet_error is not None:
        return MutationAuthorityDecision(
            "blocked",
            packet_error,
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    target_violation = _writer_target_violation(
        environment,
        active_root,
        reason,
        command_value,
        writer_target.normalized_root if writer_target is not None else "",
        writer_target.branch if writer_target is not None else "",
    )
    if target_violation is not None:
        return MutationAuthorityDecision(
            "blocked",
            target_violation,
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    if reason in {"git_merge", "git_rebase"}:
        return MutationAuthorityDecision(
            "blocked",
            "raw_git_merge_or_rebase_forbidden",
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    canonical_lifecycle = reason in {
        "repository_topic_clone_merge_main",
        "repository_topic_clone_resume_merge",
        "repository_topic_clone_finalize_merge",
    }
    canonical_route = canonical_lifecycle or reason == "repository_topic_clone_preservation_inputs_missing"
    if reason == "repository_topic_clone_compound":
        return MutationAuthorityDecision(
            "blocked",
            "repository_topic_clone_compound",
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    if canonical_route:
        if role_id != "integration_executor":
            return MutationAuthorityDecision(
                "blocked",
                "repository_topic_clone_lifecycle_requires_integration_executor",
                True,
                actor_id,
                role_id,
                parent_agent_id,
                str(identity.get("scope_digest", "")),
                paths,
                evidence_ref,
                command_sha,
            )
        if reason == "repository_topic_clone_preservation_inputs_missing":
            return MutationAuthorityDecision(
                "blocked",
                "repository_topic_clone_preservation_inputs_missing",
                True,
                actor_id,
                role_id,
                parent_agent_id,
                str(identity.get("scope_digest", "")),
                paths,
                evidence_ref,
                command_sha,
            )
    if hook_spool_root is None or not any(
        _spawn_event_matches(path, actor_id, role_id, str(identity.get("scope_digest", "")))
        for path in hook_spool_root.glob("**/*.json")
    ):
        return MutationAuthorityDecision("blocked", "child_spawn_evidence_missing", True, actor_id, role_id, parent_agent_id, str(identity.get("scope_digest", "")), paths, evidence_ref, command_sha)
    if writer_target is None:
        return MutationAuthorityDecision(
            "blocked",
            "writer_target_packet_missing",
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    packet_paths = writer_target.allowed_paths
    allowed_files = tuple(
        path.rstrip("/") for path in packet_paths if not path.endswith("/")
    )
    allowed_directories = tuple(
        path.rstrip("/") for path in packet_paths if path.endswith("/")
    )
    packet_path = WRITER_TARGET_PACKET_RELATIVE.as_posix()
    if packet_path in command_value.replace("\\", "/") or packet_path in {
        str(path).replace("\\", "/") for path in paths
    }:
        return MutationAuthorityDecision(
            "blocked",
            "writer_target_packet_mutation_forbidden",
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    if UNRESOLVED_SHELL_PATH in paths:
        return MutationAuthorityDecision(
            "blocked",
            "writer_target_unresolved_shell_path",
            True,
            actor_id,
            role_id,
            parent_agent_id,
            str(identity.get("scope_digest", "")),
            paths,
            evidence_ref,
            command_sha,
        )
    explicit_allowed = environment.get(WRITER_ALLOWED_PATHS_ENV, "").strip()
    if explicit_allowed:
        try:
            parsed_allowed = json.loads(explicit_allowed)
        except (TypeError, json.JSONDecodeError):
            parsed_allowed = None
        if not isinstance(parsed_allowed, list) or tuple(parsed_allowed) != packet_paths:
            return MutationAuthorityDecision(
                "blocked",
                "writer_target_allowed_paths_mismatch",
                True,
                actor_id,
                role_id,
                parent_agent_id,
                str(identity.get("scope_digest", "")),
                paths,
                evidence_ref,
                command_sha,
            )
    target_metadata_only = writer_target is not None and reason == "git_commit"
    if not canonical_lifecycle and not target_metadata_only and (
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
