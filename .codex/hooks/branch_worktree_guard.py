#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks unconfirmed branch and worktree creation before shell execution.
# upstream implementation ../hooks.json invokes hook dispatcher for PreToolUse.
# upstream implementation ./hook_dispatcher.py dispatches this guard as a critical child hook.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md owns branch reuse policy.
# upstream design ../../agents/skills/worktree-health.md owns worktree drift diagnostics.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates branch and worktree creation blocks.
# @dependency-end
"""Guard branch and worktree creation so tasks continue in the active checkout."""

from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from hook_dispatcher import (  # noqa: E402
    SAFE_GIT_GLOBAL_OPTION_PREFIXES,
    SAFE_GIT_GLOBAL_OPTIONS_WITH_VALUES,
    json_payload,
    tool_command,
    tool_name,
)

SHELL_TOOL_NAMES = {"Bash", "bash"}
COMMAND_SEPARATORS = {"&&", "||", ";", "|"}
SHELL_WRAPPERS = {"bash", "sh", "zsh"}
AUTHORITY_ENV = "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY"
REASON_ENV = "AGENT_CANON_BRANCH_WORKTREE_REASON"
ALLOWED_AUTHORITIES = {"user_request", "agent_canon_workflow"}
CREATE_OPTIONS = {
    "switch": (("-c", "-C"), ("--create", "--force-create")),
    "checkout": (("-b", "-B"), ("--orphan",)),
}
CREATE_EVIDENCE = {
    "switch": "git switch -c/-C",
    "checkout": "git checkout -b/-B/--orphan",
}
BRANCH_CREATE_OPTIONS = {
    "--copy",
    "--copy-force",
    "--no-track",
    "--recurse-submodules",
    "--track",
    "--force",
    "-C",
    "-c",
    "-f",
}
WORKTREE_OPTIONS = {"-v", "--verbose"}


@dataclass(frozen=True)
class CreationIntent:
    """One branch or worktree creation action visible in a shell command."""

    kind: str
    subcommand: str
    evidence: str


def load_payload() -> dict[str, object]:
    """Read one hook payload."""
    return json_payload(sys.stdin.buffer.read())


def confirmation_ready() -> bool:
    """Return whether the command carries explicit branch/worktree authority."""
    authority = os.environ.get(AUTHORITY_ENV, "").strip()
    return authority in ALLOWED_AUTHORITIES and bool(os.environ.get(REASON_ENV, "").strip())


def shell_tokens(command: str) -> tuple[str, ...]:
    """Return shell tokens while preserving common command separators."""
    stripped = command.strip()
    if not stripped:
        return ()
    try:
        lexer = shlex.shlex(stripped, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return tuple(lexer)
    except ValueError:
        return ()


def command_basename(token: str) -> str:
    """Return a command token without a leading path."""
    return Path(token).name


def is_env_assignment(token: str) -> bool:
    """Return whether a shell token is a simple environment assignment."""
    name, separator, _value = token.partition("=")
    return bool(separator and name and not token.startswith("-"))


def command_segments(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Split shell tokens around command separators."""
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for token in tokens:
        if token in COMMAND_SEPARATORS:
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append(token)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def shell_wrapper_script(tokens: tuple[str, ...]) -> str:
    """Return the script string passed to a shell wrapper."""
    if not tokens or command_basename(tokens[0]) not in SHELL_WRAPPERS:
        return ""
    for index, token in enumerate(tokens[1:], start=1):
        if token == "--":
            return ""
        if token == "-c" or (token.startswith("-") and "c" in token[1:]):
            script_index = index + 1
            return tokens[script_index] if script_index < len(tokens) else ""
    return ""


def normalized_git_tokens(segment: tuple[str, ...]) -> tuple[str, ...]:
    """Return Git subcommand tokens from one shell segment."""
    index = 0
    while index < len(segment) and is_env_assignment(segment[index]):
        index += 1
    if index < len(segment) and segment[index] == "command":
        index += 1
    if index < len(segment) and segment[index] == "env":
        index += 1
        while index < len(segment) and (
            segment[index].startswith("-") or is_env_assignment(segment[index])
        ):
            index += 1
    while index < len(segment) and is_env_assignment(segment[index]):
        index += 1
    if index >= len(segment) or command_basename(segment[index]) != "git":
        return ()
    index += 1
    while index < len(segment):
        token = segment[index]
        if token in SAFE_GIT_GLOBAL_OPTIONS_WITH_VALUES:
            index += 2
            continue
        if any(token.startswith(prefix) for prefix in SAFE_GIT_GLOBAL_OPTION_PREFIXES):
            index += 1
            continue
        break
    return tuple(segment[index:])


def visible_git_token_sequences(command: str) -> tuple[tuple[str, ...], ...]:
    """Return every Git command segment visible in a shell command."""
    tokens = shell_tokens(command)
    if not tokens:
        return ()
    script = shell_wrapper_script(tokens)
    if script:
        return visible_git_token_sequences(script)
    sequences: list[tuple[str, ...]] = []
    for segment in command_segments(tokens):
        git_tokens = normalized_git_tokens(segment)
        if git_tokens:
            sequences.append(git_tokens)
    return tuple(sequences)


def uses_create_option(subcommand: str, arguments: tuple[str, ...]) -> bool:
    """Return whether arguments contain one of the subcommand's branch creation options."""
    short_options, long_options = CREATE_OPTIONS[subcommand]
    return any(
        argument in short_options
        or any(argument.startswith(option) and len(argument) > len(option) for option in short_options)
        or argument in long_options
        or any(argument.startswith(f"{option}=") for option in long_options)
        for argument in arguments
    )


def branch_creates_branch(arguments: tuple[str, ...]) -> bool:
    """Return whether `git branch` arguments create or copy a branch."""
    if not arguments:
        return False
    if arguments[0] == "--":
        return len(arguments) > 1
    return (
        any(argument in BRANCH_CREATE_OPTIONS for argument in arguments)
        or not arguments[0].startswith("-")
    )


def worktree_subcommand(arguments: tuple[str, ...]) -> str:
    """Return the first worktree subcommand after minimal top-level options."""
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return arguments[index + 1] if index + 1 < len(arguments) else ""
        if not argument.startswith("-"):
            return argument
        if argument not in WORKTREE_OPTIONS:
            return ""
        index += 1
    return ""


def creation_intent_from_git_tokens(tokens: tuple[str, ...]) -> CreationIntent | None:
    """Return the guarded creation intent for one Git command."""
    if not tokens:
        return None
    subcommand = tokens[0]
    arguments = tokens[1:]
    if subcommand in CREATE_OPTIONS and uses_create_option(subcommand, arguments):
        return CreationIntent("branch", subcommand, CREATE_EVIDENCE[subcommand])
    if subcommand == "branch" and branch_creates_branch(arguments):
        return CreationIntent("branch", "branch", "git branch <name>/-c/-C/-f/--force")
    if subcommand == "worktree" and worktree_subcommand(arguments) == "add":
        return CreationIntent("worktree", "worktree", "git worktree add")
    return None


def creation_intent(command: str) -> CreationIntent | None:
    """Return the first branch or worktree creation action in a shell command."""
    for git_tokens in visible_git_token_sequences(command):
        intent = creation_intent_from_git_tokens(git_tokens)
        if intent is not None:
            return intent
    return None


def block_payload(command: str, intent: CreationIntent) -> dict[str, object]:
    """Return a blocking Codex hook payload."""
    reason = (
        "BRANCH_WORKTREE_CREATION_GUARD=block: branch/worktree creation "
        "requires recorded route authority before shell execution. "
        f"kind={intent.kind} subcommand={intent.subcommand} evidence={intent.evidence}"
    )
    return {
        "decision": "block",
        "reason": reason,
        "next_action": "reuse_current_checkout_or_record_branch_worktree_reason",
        "remediation": [
            "Continue on the current branch and checkout when the task shares the same ownership surface.",
            (
                "For an authorized branch/worktree route, record "
                "`branch_creation_reason=<reason>` or `worktree_creation_reason=<reason>` "
                f"and rerun with `{AUTHORITY_ENV}=user_request|agent_canon_workflow` "
                f"and `{REASON_ENV}=<reason>`."
            ),
            "Use `git branch --show-current` and `git worktree list --porcelain` for diagnostics.",
        ],
        "command": command.strip(),
    }


def main() -> int:
    """Run the branch/worktree creation guard."""
    payload = load_payload()
    if tool_name(payload) not in SHELL_TOOL_NAMES:
        return 0
    command = tool_command(payload)
    intent = creation_intent(command)
    if intent is not None and not confirmation_ready():
        json.dump(block_payload(command, intent), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
