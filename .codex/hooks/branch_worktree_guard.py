#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks unconfirmed shared-checkout Git mutations before shell execution.
# upstream implementation ../hooks.json invokes hook dispatcher for PreToolUse.
# upstream implementation ./hook_dispatcher.py dispatches this guard as a critical child hook.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md owns shared-checkout and branch reuse policy.
# upstream design ../../agents/skills/worktree-health.md owns worktree drift diagnostics.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates destructive Git and creation blocks.
# @dependency-end
"""Guard shared-checkout Git mutation such as ``git restore`` and creation."""

from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from hook_dispatcher import json_payload, tool_command, tool_name  # noqa: E402

SHELL_TOOL_NAMES = {"Bash", "bash"}
COMMAND_SEPARATORS = {"&&", "||", ";", "|", "&"}
GROUPING_TOKENS = {"(", ")", "{", "}"}
SHELL_WRAPPERS = {"bash", "sh", "zsh"}
BRANCH_AUTHORITY_ENV = "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY"
BRANCH_REASON_ENV = "AGENT_CANON_BRANCH_WORKTREE_REASON"
DESTRUCTIVE_AUTHORITY_ENV = "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY"
DESTRUCTIVE_REASON_ENV = "AGENT_CANON_DESTRUCTIVE_GIT_REASON"
ALLOWED_BRANCH_AUTHORITIES = {"user_request", "agent_canon_workflow"}
DESTRUCTIVE_AUTHORITY = "explicit_user_approval"
READ_ONLY_BRANCH_OPTIONS = {
    "--all",
    "--color",
    "--contains",
    "--format",
    "--ignore-case",
    "--list",
    "--merged",
    "--no-color",
    "--no-contains",
    "--no-merged",
    "--points-at",
    "--remotes",
    "--show-current",
    "--sort",
    "--verbose",
    "-a",
    "-r",
    "-v",
    "-vv",
}
READ_ONLY_BRANCH_VALUE_OPTIONS = {
    "--color",
    "--contains",
    "--format",
    "--merged",
    "--no-contains",
    "--no-merged",
    "--points-at",
    "--sort",
}
BRANCH_NORMAL_CREATE_SHORTS = {"c"}
BRANCH_FORCE_SHORTS = {"C", "f"}
BRANCH_DESTRUCTIVE_SHORTS = {"D", "M", "d", "m"}
BRANCH_CREATION_MODIFIERS = {
    "--create-reflog",
    "--no-track",
    "--track",
}
PROTECTED_LITERAL = re.compile(
    r"(?:^|[;&|()!\s])git(?:\s+(?:-[A-Za-z]|--[^\s]+)(?:\s+[^\s]+)?)*\s+"
    r"(?:restore|reset|clean|checkout|switch|stash|branch|worktree)(?:\s|$)"
)


@dataclass(frozen=True)
class GitCommand:
    """One visible Git invocation and its command-segment assignments."""

    tokens: tuple[str, ...]
    assignments: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class GitIntent:
    """One protected Git intent and the authority it requires."""

    kind: str
    subcommand: str
    evidence: str
    requires_creation: bool = False
    requires_destructive: bool = False


def load_payload() -> dict[str, object]:
    """Read one hook payload."""
    return json_payload(sys.stdin.buffer.read())


def shell_tokens(command: str) -> tuple[str, ...]:
    """Return shell tokens while preserving separators and grouping."""
    stripped = command.strip()
    if not stripped:
        return ()
    try:
        lexer = shlex.shlex(stripped, posix=True, punctuation_chars=";&|(){}!")
        lexer.whitespace_split = True
        return tuple(lexer)
    except ValueError:
        return ()


def command_basename(token: str) -> str:
    """Return a command token without a leading path."""
    return Path(token).name


def assignment(token: str) -> tuple[str, str] | None:
    """Return a simple shell assignment pair."""
    name, separator, value = token.partition("=")
    if not separator or not name or token.startswith("-"):
        return None
    if not (name[0].isalpha() or name[0] == "_"):
        return None
    if not all(character.isalnum() or character == "_" for character in name):
        return None
    return name, value


def command_segments(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Split tokens at shell command boundaries."""
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for token in tokens:
        if token in COMMAND_SEPARATORS or set(token) <= {";", "&", "|"}:
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append(token)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def strip_grouping(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Remove shell grouping and negation tokens around one command."""
    result = list(tokens)
    while result and (result[0] in GROUPING_TOKENS or set(result[0]) <= set("(){}!")):
        result.pop(0)
    while result and (result[-1] in GROUPING_TOKENS or set(result[-1]) <= set("(){}")):
        result.pop()
    return tuple(result)


def consume_time_prefix(tokens: tuple[str, ...], index: int) -> int:
    """Skip a POSIX/GNU `time` prefix."""
    if index >= len(tokens) or command_basename(tokens[index]) != "time":
        return index
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token in {"-f", "--format", "-o", "--output"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return index


def consume_command_prefix(tokens: tuple[str, ...], index: int) -> int:
    """Skip `command` and its options."""
    if index >= len(tokens) or command_basename(tokens[index]) != "command":
        return index
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token in {"-p", "-v", "-V"}:
            index += 1
            continue
        break
    return index


def consume_env_prefix(
    tokens: tuple[str, ...], index: int, values: dict[str, str]
) -> int:
    """Skip `env` options and collect only assignments visible in this segment."""
    if index >= len(tokens) or command_basename(tokens[index]) != "env":
        return index
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token in {"-u", "--unset"}:
            if index + 1 < len(tokens):
                values.pop(tokens[index + 1], None)
            index += 2
            continue
        if token.startswith("--unset="):
            values.pop(token.partition("=")[2], None)
            index += 1
            continue
        if token in {"-i", "--ignore-environment", "-0", "--null"}:
            index += 1
            continue
        pair = assignment(token)
        if pair is not None:
            values[pair[0]] = pair[1]
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return index


def git_subcommand_index(tokens: tuple[str, ...], index: int) -> int:
    """Skip Git global options and return the subcommand index."""
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}:
            index += 2
            continue
        if token in {"-p", "-P", "--paginate", "--no-pager", "--bare", "--no-replace-objects", "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs"}:
            index += 1
            continue
        if token == "--exec-path":
            index += 1
            continue
        if token.startswith(("-C", "-c")) and len(token) > 2:
            index += 1
            continue
        if token.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--exec-path=", "--config-env=")):
            index += 1
            continue
        break
    return index


def normalized_git_command(segment: tuple[str, ...]) -> GitCommand | None:
    """Return one direct Git command from a shell segment."""
    tokens = strip_grouping(segment)
    values: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        pair = assignment(tokens[index])
        if pair is None:
            break
        values[pair[0]] = pair[1]
        index += 1
    index = consume_time_prefix(tokens, index)
    index = consume_command_prefix(tokens, index)
    index = consume_env_prefix(tokens, index, values)
    while index < len(tokens):
        pair = assignment(tokens[index])
        if pair is None:
            break
        values[pair[0]] = pair[1]
        index += 1
    index = consume_command_prefix(tokens, index)
    if index >= len(tokens) or command_basename(tokens[index]) != "git":
        return None
    subcommand_index = git_subcommand_index(tokens, index)
    return GitCommand(tuple(tokens[subcommand_index:]), tuple(values.items()))


def wrapper_script(segment: tuple[str, ...]) -> str:
    """Return a shell/eval script string visible in one segment."""
    tokens = strip_grouping(segment)
    index = consume_time_prefix(tokens, 0)
    index = consume_command_prefix(tokens, index)
    if index < len(tokens) and command_basename(tokens[index]) == "eval":
        return " ".join(tokens[index + 1 :])
    if index >= len(tokens) or command_basename(tokens[index]) not in SHELL_WRAPPERS:
        return ""
    for option_index, token in enumerate(tokens[index + 1 :], start=index + 1):
        if token == "--":
            return ""
        if token == "-c" or (token.startswith("-") and "c" in token[1:]):
            script_index = option_index + 1
            return tokens[script_index] if script_index < len(tokens) else ""
    return ""


def short_option_letters(arguments: tuple[str, ...]) -> set[str]:
    """Return letters from combined short options before `--`."""
    letters: set[str] = set()
    for argument in arguments:
        if argument == "--":
            break
        if argument.startswith("-") and not argument.startswith("--"):
            letters.update(argument[1:])
    return letters


def has_long_option(arguments: tuple[str, ...], *options: str) -> bool:
    """Return whether a long option is present in plain or assigned form."""
    return any(
        argument in options or any(argument.startswith(f"{option}=") for option in options)
        for argument in arguments
    )


def branch_is_read_only(arguments: tuple[str, ...]) -> bool:
    """Return whether branch arguments are an explicit list/show form."""
    if not arguments:
        return True
    if arguments == ("--show-current",):
        return True
    index = 0
    saw_list = False
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return False
        if argument == "--list":
            saw_list = True
            index += 1
            continue
        if argument in READ_ONLY_BRANCH_VALUE_OPTIONS:
            index += 2
            continue
        if any(argument.startswith(f"{option}=") for option in READ_ONLY_BRANCH_VALUE_OPTIONS):
            index += 1
            continue
        if argument in READ_ONLY_BRANCH_OPTIONS:
            index += 1
            continue
        if saw_list and not argument.startswith("-"):
            index += 1
            continue
        return False
    return True


def branch_intent(arguments: tuple[str, ...]) -> GitIntent | None:
    """Classify branch creation, overwrite, and metadata mutation."""
    if branch_is_read_only(arguments):
        return None
    letters = short_option_letters(arguments)
    if letters & BRANCH_FORCE_SHORTS or has_long_option(arguments, "--force", "--copy-force"):
        return GitIntent("destructive_branch_creation", "branch", "git branch force-create/ref-overwrite", True, True)
    if letters & BRANCH_DESTRUCTIVE_SHORTS or has_long_option(arguments, "--delete", "--move"):
        return GitIntent("destructive_git", "branch", "git branch delete/rename", False, True)
    if letters & BRANCH_NORMAL_CREATE_SHORTS or has_long_option(arguments, "--copy"):
        return GitIntent("branch_creation", "branch", "git branch create/copy", True, False)
    if (
        has_long_option(arguments, *BRANCH_CREATION_MODIFIERS)
        and any(not argument.startswith("-") for argument in arguments)
    ):
        return GitIntent("branch_creation", "branch", "git branch create with tracking/reflog", True, False)
    if arguments and not arguments[0].startswith("-"):
        return GitIntent("branch_creation", "branch", "git branch <name>", True, False)
    return GitIntent("destructive_git", "branch", "git branch metadata mutation", False, True)


def worktree_intent(arguments: tuple[str, ...]) -> GitIntent | None:
    """Classify worktree inspection, creation, and mutation."""
    index = 0
    while index < len(arguments) and arguments[index] in {"-v", "--verbose"}:
        index += 1
    if index >= len(arguments):
        return GitIntent("destructive_git", "worktree", "git worktree mutation", False, True)
    subcommand = arguments[index]
    rest = arguments[index + 1 :]
    if subcommand == "list":
        return None
    if subcommand == "add":
        force_overwrite = bool(short_option_letters(rest) & {"B", "f"}) or has_long_option(rest, "--force")
        if force_overwrite:
            return GitIntent("destructive_worktree_creation", "worktree", "git worktree add -B/-f/--force", True, True)
        return GitIntent("worktree_creation", "worktree", "git worktree add/create/orphan", True, False)
    return GitIntent("destructive_git", "worktree", f"git worktree {subcommand}", False, True)


def git_intent(command: GitCommand) -> GitIntent | None:
    """Classify one normalized Git command."""
    if not command.tokens:
        return None
    subcommand = command.tokens[0]
    arguments = command.tokens[1:]
    if subcommand in {"restore", "reset"}:
        return GitIntent("destructive_git", subcommand, f"git {subcommand}", False, True)
    if subcommand == "clean":
        letters = short_option_letters(arguments)
        dry_run = "n" in letters or has_long_option(arguments, "--dry-run")
        forced = "f" in letters or has_long_option(arguments, "--force")
        return GitIntent("destructive_git", "clean", "git clean force", False, True) if forced and not dry_run else None
    if subcommand in {"checkout", "switch"}:
        if has_long_option(arguments, "--help") or "h" in short_option_letters(arguments):
            return None
        letters = short_option_letters(arguments)
        force_create = (subcommand == "switch" and "C" in letters) or (subcommand == "checkout" and "B" in letters) or has_long_option(arguments, "--force-create")
        normal_create = (subcommand == "switch" and "c" in letters) or (subcommand == "checkout" and "b" in letters) or has_long_option(arguments, "--create", "--orphan")
        if force_create:
            return GitIntent("destructive_branch_creation", subcommand, f"git {subcommand} force-create/ref-overwrite", True, True)
        if normal_create:
            return GitIntent("branch_creation", subcommand, f"git {subcommand} create/orphan", True, False)
        return GitIntent("destructive_git", subcommand, f"git {subcommand} current-checkout mutation", False, True)
    if subcommand == "stash":
        if arguments and arguments[0] in {"list", "show"}:
            return None
        return GitIntent("destructive_git", "stash", "git stash mutation", False, True)
    if subcommand == "branch":
        return branch_intent(arguments)
    if subcommand == "worktree":
        return worktree_intent(arguments)
    return None


def assignment_map(command: GitCommand) -> dict[str, str]:
    """Return command-segment assignments."""
    return dict(command.assignments)


def creation_authorized(command: GitCommand) -> bool:
    """Return whether same-segment branch/worktree creation evidence is complete."""
    values = assignment_map(command)
    return values.get(BRANCH_AUTHORITY_ENV, "").strip() in ALLOWED_BRANCH_AUTHORITIES and bool(values.get(BRANCH_REASON_ENV, "").strip())


def destructive_authorized(command: GitCommand) -> bool:
    """Return whether same-segment explicit destructive authority is complete."""
    values = assignment_map(command)
    return values.get(DESTRUCTIVE_AUTHORITY_ENV, "").strip() == DESTRUCTIVE_AUTHORITY and bool(values.get(DESTRUCTIVE_REASON_ENV, "").strip())


def intent_authorized(command: GitCommand, intent: GitIntent) -> bool:
    """Return whether every authority required by an intent is present."""
    return (
        not intent.requires_creation
        or (creation_authorized(command) and destructive_authorized(command))
    ) and (
        not intent.requires_destructive or destructive_authorized(command)
    )


def opaque_protected_intent(command: str) -> GitIntent | None:
    """Fail closed when literal protected Git remains opaque to the parser."""
    if PROTECTED_LITERAL.search(command):
        return GitIntent("destructive_git", "opaque", "opaque protected Git mutation", False, True)
    return None


def block_payload(command: str, intent: GitIntent) -> dict[str, object]:
    """Return a blocking Codex hook payload."""
    destructive = intent.requires_destructive
    marker = "DESTRUCTIVE_GIT_GUARD=block" if destructive else "BRANCH_WORKTREE_CREATION_GUARD=block"
    next_action = (
        "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval"
        if destructive
        else "reuse_current_checkout_or_record_branch_worktree_reason"
    )
    requirements: list[str] = []
    if intent.requires_creation:
        requirements.append(f"same-segment {BRANCH_AUTHORITY_ENV}=user_request|agent_canon_workflow and nonempty {BRANCH_REASON_ENV}")
        requirements.append(f"same-segment {DESTRUCTIVE_AUTHORITY_ENV}=explicit_user_approval and nonempty {DESTRUCTIVE_REASON_ENV}")
    elif intent.requires_destructive:
        requirements.append(f"same-segment {DESTRUCTIVE_AUTHORITY_ENV}=explicit_user_approval and nonempty {DESTRUCTIVE_REASON_ENV}")
    return {
        "decision": "block",
        "reason": f"{marker}: protected shared-checkout Git intent lacks required authority. kind={intent.kind} subcommand={intent.subcommand} evidence={intent.evidence}; requires={'; '.join(requirements)}",
        "next_action": next_action,
        "remediation": [
            "Inspect status and preserve changes owned by the user or another concurrent chat.",
            "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
            "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git.",
        ],
        "command": command.strip(),
    }


def first_block(command: str) -> GitIntent | None:
    """Return the first unauthorized protected intent."""
    tokens = shell_tokens(command)
    if not tokens:
        return opaque_protected_intent(command)
    for segment in command_segments(tokens):
        script = wrapper_script(segment)
        if script:
            if intent := first_block(script):
                return intent
            continue
        git_command = normalized_git_command(segment)
        if git_command is not None:
            intent = git_intent(git_command)
            if intent is not None and not intent_authorized(git_command, intent):
                return intent
            if (
                intent is None
                and git_command.tokens
                and git_command.tokens[0].startswith("-")
                and (opaque := opaque_protected_intent(" ".join(segment)))
            ):
                return opaque
            continue
        if intent := opaque_protected_intent(" ".join(segment)):
            return intent
    return None


def main() -> int:
    """Run the shared-checkout Git mutation guard."""
    payload = load_payload()
    if tool_name(payload) not in SHELL_TOOL_NAMES:
        return 0
    command = tool_command(payload)
    intent = first_block(command)
    if intent is not None:
        json.dump(block_payload(command, intent), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
