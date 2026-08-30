#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Owns pure secret matching, destructive Git intent classification, and redacted safety payloads.
# upstream implementation ../../.codex/hooks/hook_dispatcher.py runs these leaves in-process for active events.
# upstream implementation ../../.codex/hooks/hook_dispatcher.py is the only active caller.
# upstream design ../../documents/codex/codex-configuration-reference.md defines active hook safety semantics.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates pure safety decisions and redaction.
# @dependency-end
"""Pure safety leaves owned outside the hook directory."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"), "OpenAI-style API key"),
)

SHELL_TOOL_NAMES = {"Bash", "bash"}
COMMAND_SEPARATORS = {"&&", "||", ";", "|", "&"}
GROUPING_TOKENS = {"(", ")", "{", "}"}
SHELL_COMMENT_BOUNDARY_CHARS = frozenset(";&|()<>")
SHELL_WRAPPERS = {"bash", "sh", "zsh"}
BRANCH_AUTHORITY_ENV = "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY"
BRANCH_REASON_ENV = "AGENT_CANON_BRANCH_WORKTREE_REASON"
DESTRUCTIVE_AUTHORITY_ENV = "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY"
DESTRUCTIVE_REASON_ENV = "AGENT_CANON_DESTRUCTIVE_GIT_REASON"
ALLOWED_BRANCH_AUTHORITIES = {"user_request", "agent_canon_workflow"}
DESTRUCTIVE_AUTHORITY = "explicit_user_approval"
PRESERVATION_INVENTORY_ENV = "AGENT_CANON_CONFLICT_PRESERVATION_INVENTORY"
PRESERVATION_PLAN_ENV = "AGENT_CANON_CONFLICT_PRESERVATION_PLAN"
READ_ONLY_BRANCH_OPTIONS = {
    "--all", "--color", "--contains", "--format", "--ignore-case", "--list",
    "--merged", "--no-color", "--no-contains", "--no-merged", "--points-at",
    "--remotes", "--show-current", "--sort", "--verbose", "-a", "-r", "-v", "-vv",
}
READ_ONLY_BRANCH_VALUE_OPTIONS = {
    "--color", "--contains", "--format", "--merged", "--no-contains",
    "--no-merged", "--points-at", "--sort",
}
BENIGN_BRANCH_OPTIONS = {"--edit-description", "--unset-upstream", "-u"}
BENIGN_BRANCH_VALUE_OPTIONS = {"--set-upstream-to", "-u"}
BRANCH_NORMAL_CREATE_SHORTS = {"c"}
BRANCH_FORCE_SHORTS = {"C", "f"}
BRANCH_DESTRUCTIVE_SHORTS = {"D", "M", "d", "m"}
BRANCH_CREATION_MODIFIERS = {"--create-reflog", "--no-track", "--track"}
PROTECTED_GIT_SUBCOMMANDS = frozenset(
    {"restore", "reset", "clean", "checkout", "switch", "stash", "branch", "worktree"}
)
OPAQUE_GIT_OPTIONS_WITH_VALUES = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
)


@dataclass(frozen=True)
class GitCommand:
    """One visible Git invocation and its same-segment assignments."""

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
    requires_preservation: bool = False


def payload_tool_name(payload: dict[str, object]) -> str:
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def payload_tool_command(payload: dict[str, object]) -> str:
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("command", "cmd"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    for key in ("command", "cmd"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def payload_prompt(payload: dict[str, object]) -> str:
    value = payload.get("prompt")
    return value if isinstance(value, str) else ""


def secret_kind(prompt: str) -> str | None:
    """Return the first high-confidence secret class in prompt text."""
    for pattern, kind in SECRET_PATTERNS:
        if pattern.search(prompt):
            return kind
    return None


def secret_block_payload(secret: str) -> dict[str, object]:
    """Return a block payload without retaining the matched prompt."""
    return {
        "decision": "block",
        "reason": (
            f"Prompt appears to include a {secret}. Remove the secret or replace it "
            "with a redacted placeholder."
        ),
        "next_action": "remove_secret_or_use_redacted_placeholder_then_retry",
        "remediation": [
            "Remove the secret material from the prompt.",
            "Replace examples with redacted placeholders such as `[REDACTED_TOKEN]`.",
            "Rotate the secret if it was pasted into the session by mistake.",
        ],
    }


def command_sha256(command: str) -> str:
    """Return the only command identity allowed in a safety payload."""
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


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


def backtick_command_substitutions(command: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return complete and uncertain executable backtick bodies without shell I/O."""
    complete: list[str] = []
    active: list[str] | None = None
    single_quoted = False
    double_quoted = False
    in_comment = False
    comment_boundary = True
    active_single_quoted = False
    active_double_quoted = False
    active_in_comment = False
    active_comment_boundary = True
    index = 0
    while index < len(command):
        character = command[index]
        if active is not None:
            if active_in_comment:
                active.append(character)
                if character == "\n":
                    active_in_comment = False
                    active_comment_boundary = True
                index += 1
                continue
            if (
                character == "\\"
                and not active_single_quoted
                and index + 1 < len(command)
            ):
                escaped = command[index + 1]
                if not active_double_quoted or escaped in '$`"\\\n':
                    active.extend((character, escaped))
                    if escaped != "\n":
                        active_comment_boundary = False
                    index += 2
                    continue
                active.append(character)
                active_comment_boundary = False
                index += 1
                continue
            if character == "`":
                complete.append("".join(active))
                active = None
                comment_boundary = False
                index += 1
                continue
            active.append(character)
            if character == "'" and not active_double_quoted:
                active_single_quoted = not active_single_quoted
                active_comment_boundary = False
            elif character == '"' and not active_single_quoted:
                active_double_quoted = not active_double_quoted
                active_comment_boundary = False
            elif (
                character == "#"
                and not active_single_quoted
                and not active_double_quoted
                and active_comment_boundary
            ):
                active_in_comment = True
            elif (
                not active_single_quoted
                and not active_double_quoted
                and (
                    character.isspace()
                    or character in SHELL_COMMENT_BOUNDARY_CHARS
                )
            ):
                active_comment_boundary = True
            else:
                active_comment_boundary = False
            index += 1
            continue
        if in_comment:
            if character == "\n":
                in_comment = False
                comment_boundary = True
            index += 1
            continue
        if character == "\\" and not single_quoted and index + 1 < len(command):
            escaped = command[index + 1]
            if not double_quoted or escaped in '$`"\\\n':
                if escaped != "\n" or double_quoted:
                    comment_boundary = False
                index += 2
                continue
            comment_boundary = False
            index += 1
            continue
        if character == "'" and not double_quoted:
            single_quoted = not single_quoted
            comment_boundary = False
        elif character == '"' and not single_quoted:
            double_quoted = not double_quoted
            comment_boundary = False
        elif (
            character == "#"
            and not single_quoted
            and not double_quoted
            and comment_boundary
        ):
            in_comment = True
        elif character == "`" and not single_quoted:
            active = []
            active_single_quoted = False
            active_double_quoted = False
            active_in_comment = False
            active_comment_boundary = True
            comment_boundary = False
        elif (
            not single_quoted
            and not double_quoted
            and (
                character.isspace()
                or character in SHELL_COMMENT_BOUNDARY_CHARS
            )
        ):
            comment_boundary = True
        else:
            comment_boundary = False
        index += 1
    uncertain = ("".join(active),) if active is not None else ()
    return tuple(complete), uncertain


def command_basename(token: str) -> str:
    return Path(token).name


def assignment(token: str) -> tuple[str, str] | None:
    name, separator, value = token.partition("=")
    if not separator or not name or token.startswith("-"):
        return None
    if not (name[0].isalpha() or name[0] == "_"):
        return None
    if not all(character.isalnum() or character == "_" for character in name):
        return None
    return name, value


def command_segments(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
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
    result = list(tokens)
    while result and (result[0] in GROUPING_TOKENS or set(result[0]) <= set("(){}!")):
        result.pop(0)
    while result and (result[-1] in GROUPING_TOKENS or set(result[-1]) <= set("(){}")):
        result.pop()
    return tuple(result)


def consume_time_prefix(tokens: tuple[str, ...], index: int) -> int:
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


def consume_exec_prefix(tokens: tuple[str, ...], index: int) -> int:
    if index >= len(tokens) or command_basename(tokens[index]) != "exec":
        return index
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token == "-a":
            index += 2
            continue
        if token in {"-c", "-l"} or (
            token.startswith("-") and not token.startswith("--") and token[1:] and set(token[1:]) <= {"c", "l"}
        ):
            index += 1
            continue
        break
    return index


def consume_env_prefix(tokens: tuple[str, ...], index: int, values: dict[str, str]) -> int:
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
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}:
            index += 2
            continue
        if token in {"-p", "-P", "--paginate", "--no-pager", "--bare", "--no-replace-objects", "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs", "--exec-path"}:
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
        if token == "-c" or (token.startswith("-") and not token.startswith("--") and "c" in token[1:]):
            script_index = option_index + 1
            return tokens[script_index] if script_index < len(tokens) else ""
    return ""


def short_option_letters(arguments: tuple[str, ...]) -> set[str]:
    letters: set[str] = set()
    for argument in arguments:
        if argument == "--":
            break
        if argument.startswith("-") and not argument.startswith("--"):
            letters.update(argument[1:])
    return letters


def has_long_option(arguments: tuple[str, ...], *options: str) -> bool:
    return any(argument in options or any(argument.startswith(f"{option}=") for option in options) for argument in arguments)


def branch_is_read_only(arguments: tuple[str, ...]) -> bool:
    if not arguments or arguments == ("--show-current",):
        return True
    index = 0
    saw_list = False
    saw_benign_metadata = False
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
        if argument.startswith("-u") and not argument.startswith("--") and argument != "-u":
            saw_benign_metadata = True
            index += 1
            continue
        if argument in BENIGN_BRANCH_VALUE_OPTIONS:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("-"):
                return False
            saw_benign_metadata = True
            index += 2
            continue
        if any(argument.startswith(f"{option}=") for option in BENIGN_BRANCH_VALUE_OPTIONS if option.startswith("--")):
            saw_benign_metadata = True
            index += 1
            continue
        if argument in BENIGN_BRANCH_OPTIONS:
            saw_benign_metadata = True
            index += 1
            continue
        if argument in READ_ONLY_BRANCH_OPTIONS:
            index += 1
            continue
        if (saw_list or saw_benign_metadata) and not argument.startswith("-"):
            index += 1
            continue
        return False
    return True


def branch_intent(arguments: tuple[str, ...]) -> GitIntent | None:
    if branch_is_read_only(arguments):
        return None
    letters = short_option_letters(arguments)
    if letters & BRANCH_FORCE_SHORTS or has_long_option(arguments, "--force", "--copy-force"):
        return GitIntent("destructive_branch_creation", "branch", "force-create/ref-overwrite", True, True)
    if letters & BRANCH_DESTRUCTIVE_SHORTS or has_long_option(arguments, "--delete", "--move"):
        return GitIntent("destructive_git", "branch", "delete/rename", False, True)
    if letters & BRANCH_NORMAL_CREATE_SHORTS or has_long_option(arguments, "--copy"):
        return GitIntent("branch_creation", "branch", "create/copy", True, False)
    if has_long_option(arguments, *BRANCH_CREATION_MODIFIERS) and any(not argument.startswith("-") for argument in arguments):
        return GitIntent("branch_creation", "branch", "create with tracking/reflog", True, False)
    if arguments and not arguments[0].startswith("-"):
        return GitIntent("branch_creation", "branch", "branch name", True, False)
    return GitIntent("destructive_git", "branch", "metadata mutation", False, True)


def worktree_intent(arguments: tuple[str, ...]) -> GitIntent | None:
    index = 0
    while index < len(arguments) and arguments[index] in {"-v", "--verbose"}:
        index += 1
    if index >= len(arguments):
        return GitIntent("destructive_git", "worktree", "worktree mutation", False, True)
    subcommand = arguments[index]
    rest = arguments[index + 1 :]
    if subcommand == "list":
        return None
    if subcommand == "lock":
        index = 0
        saw_path = False
        while index < len(rest):
            argument = rest[index]
            if argument == "--reason":
                if index + 1 >= len(rest) or rest[index + 1].startswith("-"):
                    return GitIntent("destructive_git", "worktree", "worktree lock mutation", False, True)
                index += 2
                continue
            if argument.startswith("--reason="):
                index += 1
                continue
            if argument == "--":
                if not saw_path and len(rest[index + 1 :]) == 1:
                    return None
                return GitIntent("destructive_git", "worktree", "worktree lock mutation", False, True)
            if argument.startswith("-") or saw_path:
                return GitIntent("destructive_git", "worktree", "worktree lock mutation", False, True)
            saw_path = True
            index += 1
        if saw_path:
            return None
    if subcommand == "unlock":
        if rest and all(not argument.startswith("-") for argument in rest):
            return None
    if subcommand == "add":
        force_overwrite = bool(short_option_letters(rest) & {"B", "f"}) or has_long_option(rest, "--force")
        if force_overwrite:
            return GitIntent("destructive_worktree_creation", "worktree", "worktree force-add", True, True)
        return GitIntent("worktree_creation", "worktree", "worktree add", True, False)
    return GitIntent("destructive_git", "worktree", f"worktree {subcommand}", False, True)


def git_intent(command: GitCommand) -> GitIntent | None:
    if not command.tokens:
        return None
    subcommand = command.tokens[0]
    arguments = command.tokens[1:]
    if subcommand == "restore":
        return GitIntent(
            "destructive_git",
            subcommand,
            "git restore",
            requires_destructive=True,
            requires_preservation=True,
        )
    if subcommand == "reset":
        return GitIntent(
            "destructive_git",
            subcommand,
            "git reset",
            requires_destructive=True,
            requires_preservation=True,
        )
    if subcommand == "clean":
        letters = short_option_letters(arguments)
        dry_run = "n" in letters or has_long_option(arguments, "--dry-run")
        forced = "f" in letters or has_long_option(arguments, "--force")
        return (
            GitIntent(
                "destructive_git",
                "clean",
                "git clean force",
                requires_destructive=True,
                requires_preservation=True,
            )
            if forced and not dry_run
            else None
        )
    if subcommand in {"checkout", "switch"}:
        if has_long_option(arguments, "--help") or "h" in short_option_letters(arguments):
            return None
        letters = short_option_letters(arguments)
        force_create = (subcommand == "switch" and "C" in letters) or (subcommand == "checkout" and "B" in letters) or has_long_option(arguments, "--force-create")
        normal_create = (subcommand == "switch" and "c" in letters) or (subcommand == "checkout" and "b" in letters) or has_long_option(arguments, "--create", "--orphan")
        if force_create:
            return GitIntent("destructive_branch_creation", subcommand, "force-create/ref-overwrite", True, True)
        if normal_create:
            return GitIntent("branch_creation", subcommand, "create/orphan", True, False)
        preserve = subcommand == "checkout" or "--" in arguments or has_long_option(
            arguments, "--ours", "--theirs"
        )
        return GitIntent(
            "destructive_git",
            subcommand,
            "current-checkout mutation",
            requires_destructive=True,
            requires_preservation=preserve,
        )
    if subcommand == "stash":
        if arguments and arguments[0] in {"list", "show"}:
            return None
        return GitIntent("destructive_git", "stash", "stash mutation", False, True)
    if subcommand == "branch":
        return branch_intent(arguments)
    if subcommand == "worktree":
        return worktree_intent(arguments)
    return None


def assignment_map(command: GitCommand) -> dict[str, str]:
    return dict(command.assignments)


def creation_authorized(command: GitCommand) -> bool:
    values = assignment_map(command)
    return values.get(BRANCH_AUTHORITY_ENV, "").strip() in ALLOWED_BRANCH_AUTHORITIES and bool(values.get(BRANCH_REASON_ENV, "").strip())


def destructive_authorized(command: GitCommand) -> bool:
    values = assignment_map(command)
    return values.get(DESTRUCTIVE_AUTHORITY_ENV, "").strip() == DESTRUCTIVE_AUTHORITY and bool(values.get(DESTRUCTIVE_REASON_ENV, "").strip())


def intent_authorized(command: GitCommand, intent: GitIntent) -> bool:
    return (not intent.requires_creation or creation_authorized(command)) and (
        not intent.requires_destructive or destructive_authorized(command)
    )


def opaque_protected_intent(command: str) -> GitIntent | None:
    tokens = shell_tokens(command)
    for git_index, token in enumerate(tokens):
        if command_basename(token) != "git":
            continue
        index = git_index + 1
        while index < len(tokens):
            option = tokens[index]
            if option in OPAQUE_GIT_OPTIONS_WITH_VALUES:
                index += 2
                continue
            if option.startswith("-"):
                index += 1
                continue
            if option in PROTECTED_GIT_SUBCOMMANDS:
                return GitIntent("destructive_git", "opaque", "opaque protected Git mutation", False, True)
            break
    return None


def _first_block_without_backticks(command: str) -> GitIntent | None:
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
            if intent is None and git_command.tokens and git_command.tokens[0].startswith("-"):
                if opaque := opaque_protected_intent(" ".join(segment)):
                    return opaque
            continue
        if intent := opaque_protected_intent(" ".join(segment)):
            return intent
    return None


def first_block(command: str) -> GitIntent | None:
    """Return the first unauthorized raw Git intent."""
    complete, uncertain = backtick_command_substitutions(command)
    for substitution in (*complete, *uncertain):
        if intent := first_block(substitution):
            return intent
    return _first_block_without_backticks(command)


def _preservation_intent_without_backticks(command: str) -> GitIntent | None:
    """Return a normalized whole-file mutation, independent of authority."""
    tokens = shell_tokens(command)
    for segment in command_segments(tokens):
        script = wrapper_script(segment)
        if script:
            if intent := preservation_intent(script):
                return intent
            continue
        git_command = normalized_git_command(segment)
        if git_command is not None:
            if git_command.tokens and git_command.tokens[0] == "clone":
                return GitIntent(
                    "whole_file_replacement",
                    "clone",
                    "git clone/reclone",
                    requires_preservation=True,
                )
            if git_command.tokens and git_command.tokens[0] == "commit":
                return GitIntent(
                    "conflict_finalize",
                    "commit",
                    "direct commit during conflict",
                    requires_preservation=True,
                )
            intent = git_intent(git_command)
            if intent is not None and intent.requires_preservation:
                return intent
            continue
        normalized = strip_grouping(segment)
        values: dict[str, str] = {}
        index = 0
        while index < len(normalized):
            pair = assignment(normalized[index])
            if pair is None:
                break
            values[pair[0]] = pair[1]
            index += 1
        index = consume_time_prefix(normalized, index)
        index = consume_command_prefix(normalized, index)
        index = consume_env_prefix(normalized, index, values)
        normalized = normalized[index:]
        if not normalized:
            continue
        command_name = command_basename(normalized[0])
        arguments = normalized[1:]
        if command_name in {"cp", "mv", "rm", "tee", "truncate", "reclone"}:
            return GitIntent(
                "whole_file_replacement",
                command_name,
                f"{command_name} whole-file replacement",
                requires_preservation=True,
            )
        if command_name in {"sed", "perl"} and any(
            argument == "-i" or argument.startswith("-i") for argument in arguments
        ):
            return GitIntent(
                "whole_file_replacement",
                command_name,
                f"{command_name} in-place replacement",
                requires_preservation=True,
            )
    return None


def preservation_intent(command: str) -> GitIntent | None:
    """Return a normalized content-replacing operation regardless of authority."""
    complete, uncertain = backtick_command_substitutions(command)
    for substitution in (*complete, *uncertain):
        if intent := preservation_intent(substitution):
            return intent
    return _preservation_intent_without_backticks(command)


def _segment_assignments(segment: tuple[str, ...]) -> dict[str, str]:
    """Read assignments attached to one normalized shell command segment."""
    git_command = normalized_git_command(segment)
    if git_command is not None:
        return assignment_map(git_command)
    normalized = strip_grouping(segment)
    values: dict[str, str] = {}
    index = 0
    while index < len(normalized):
        pair = assignment(normalized[index])
        if pair is None:
            break
        values[pair[0]] = pair[1]
        index += 1
    index = consume_time_prefix(normalized, index)
    index = consume_command_prefix(normalized, index)
    consume_env_prefix(normalized, index, values)
    return values


def _non_git_segment(segment: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Return one shell command name and argv after prefixes are removed."""
    normalized = strip_grouping(segment)
    values: dict[str, str] = {}
    index = 0
    while index < len(normalized):
        pair = assignment(normalized[index])
        if pair is None:
            break
        values[pair[0]] = pair[1]
        index += 1
    index = consume_time_prefix(normalized, index)
    index = consume_command_prefix(normalized, index)
    index = consume_env_prefix(normalized, index, values)
    if index >= len(normalized):
        return "", ()
    return command_basename(normalized[index]), normalized[index + 1 :]


def _git_target_operands(command: GitCommand) -> tuple[str, ...] | None:
    """Return bounded path operands for a content-changing Git command."""
    if not command.tokens:
        return None
    subcommand = command.tokens[0]
    arguments = list(command.tokens[1:])
    if subcommand in {"checkout", "restore"}:
        option_values = {"-c", "--conflict", "--pathspec-from-file", "--source", "-s"}
        filtered: list[str] = []
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument in option_values:
                index += 2
                continue
            if any(argument.startswith(f"{option}=") for option in option_values if option.startswith("--")):
                index += 1
                continue
            filtered.append(argument)
            index += 1
        arguments = filtered
        if "--" in arguments:
            return tuple(arguments[arguments.index("--") + 1 :]) or None
        return tuple(
            argument
            for argument in arguments
            if not argument.startswith("-")
        ) or None
    if subcommand == "reset":
        if "--" not in arguments:
            return None
        return tuple(arguments[arguments.index("--") + 1 :]) or None
    if subcommand == "clean":
        if "--" not in arguments:
            return None
        return tuple(arguments[arguments.index("--") + 1 :]) or None
    return None


def _non_git_target_operands(
    command_name: str, arguments: tuple[str, ...]
) -> tuple[str, ...] | None:
    """Return bounded mutation targets for copy/remove/in-place commands."""
    if command_name in {"rm", "tee", "truncate"}:
        operands = tuple(
            argument
            for argument in arguments[arguments.index("--") + 1 :]
            if argument
        ) if "--" in arguments else tuple(
            argument for argument in arguments if not argument.startswith("-")
        )
        return operands or None
    if command_name in {"cp", "mv"}:
        operands = tuple(
            argument
            for argument in arguments[arguments.index("--") + 1 :]
        ) if "--" in arguments else tuple(
            argument for argument in arguments if not argument.startswith("-")
        )
        if len(operands) != 2:
            return None
        return (operands[-1],)
    if command_name in {"sed", "perl"}:
        operands = [argument for argument in arguments if not argument.startswith("-")]
        if len(operands) < 2:
            return None
        return tuple(operands[1:])
    return None


def preservation_target_operands(segment: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return path operands for one normalized preservation mutation segment."""
    git_command = normalized_git_command(segment)
    if git_command is not None:
        if git_command.tokens and git_command.tokens[0] == "clone":
            return None
        if git_command.tokens and git_command.tokens[0] == "commit":
            return ()
        return _git_target_operands(git_command)
    command_name, arguments = _non_git_segment(segment)
    return _non_git_target_operands(command_name, arguments)


def _under(path: Path, root: Path) -> bool:
    try:
        return path == root or root in path.parents
    except (OSError, RuntimeError):
        return False


def _packet_path(value: str, roots: tuple[Path, ...]) -> Path | None:
    raw = Path(value)
    candidates = (raw,) if raw.is_absolute() else tuple(root / raw for root in roots)
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _load_packet(path: Path) -> Mapping[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _target_paths(
    operands: tuple[str, ...], clone: Path, *, relative_root: Path
) -> tuple[str, ...] | None:
    """Resolve every bounded mutation operand against the active clone."""
    if not operands:
        return None
    paths: list[str] = []
    for operand in operands:
        if not operand or operand in {".", ".."} or any(mark in operand for mark in "*?["):
            return None
        candidate = Path(operand)
        if not candidate.is_absolute():
            candidate = relative_root / candidate
        try:
            resolved = candidate.resolve(strict=False)
            relative = resolved.relative_to(clone.resolve())
        except (OSError, RuntimeError, ValueError):
            return None
        if not relative.parts or resolved.is_dir() or operand.endswith("/"):
            return None
        paths.append(relative.as_posix())
    return tuple(dict.fromkeys(paths))


def _inventory_paths(inventory: Mapping[str, object]) -> set[str]:
    entries = inventory.get("paths")
    if not isinstance(entries, list):
        return set()
    return {
        str(entry["path"])
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }


def preservation_authorized(
    command: str, *, active_root: Path | None = None
) -> bool:
    """Validate packets attached to the same destructive command segment."""
    tokens = shell_tokens(command)
    for segment in command_segments(tokens):
        segment_text = " ".join(segment)
        intent = preservation_intent(segment_text)
        if intent is None:
            continue
        assignments = _segment_assignments(segment)
        inventory_value = assignments.get(PRESERVATION_INVENTORY_ENV, "").strip()
        plan_value = assignments.get(PRESERVATION_PLAN_ENV, "").strip()
        if not inventory_value or not plan_value:
            continue
        explicit_roots = preservation_command_roots(segment_text)
        roots = tuple(
            path.resolve() for path in explicit_roots
        ) or (Path.cwd().resolve(), *( (active_root.resolve(),) if active_root else ()))
        inventory_path = _packet_path(inventory_value, roots)
        plan_path = _packet_path(plan_value, roots)
        if inventory_path is None or plan_path is None:
            continue
        for root in roots:
            try:
                clone = root.resolve(strict=True)
                scope = (clone / ".agent-canon").resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if not (clone / ".git").exists() or not _under(inventory_path, scope) or not _under(plan_path, scope):
                continue
            inventory = _load_packet(inventory_path)
            plan = _load_packet(plan_path)
            if inventory is None or plan is None:
                continue
            operands = preservation_target_operands(segment)
            if operands is None:
                continue
            relative_root = clone if normalized_git_command(segment) is not None else Path.cwd().resolve()
            target_paths = _target_paths(
                operands, clone, relative_root=relative_root
            )
            if target_paths is None:
                continue
            covered = _inventory_paths(inventory)
            if not covered or not set(target_paths).issubset(covered):
                continue
            try:
                try:
                    from tools.repository.git.conflict_preservation import validate_plan, validate_snapshot
                except ImportError:
                    from tools.repository.git.conflict_preservation import validate_plan, validate_snapshot
                validate_plan(inventory, plan, repo=clone, readback=False)
                validate_snapshot(clone, inventory, target_paths)
            except (OSError, TypeError, ValueError, RuntimeError):
                continue
            return True
    return False


def preservation_command_roots(command: str) -> tuple[Path, ...]:
    """Return explicit Git ``-C`` roots so hooks can find a clone inventory."""
    roots: list[Path] = []
    for segment in command_segments(shell_tokens(command)):
        for index, token in enumerate(segment):
            if token == "-C" and index + 1 < len(segment):
                roots.append(Path(segment[index + 1]))
            elif token.startswith("-C") and len(token) > 2:
                roots.append(Path(token[2:]))
    return tuple(roots)


def branch_block_payload(command: str, intent: GitIntent) -> dict[str, object]:
    """Return a redacted block payload; command text never crosses the leaf boundary."""
    markers = []
    if intent.requires_destructive:
        markers.append("DESTRUCTIVE_GIT_GUARD=block")
    if intent.requires_creation:
        markers.append("BRANCH_WORKTREE_CREATION_GUARD=block")
    requirements: list[str] = []
    if intent.requires_creation:
        requirements.append(
            f"same-segment {BRANCH_AUTHORITY_ENV}=user_request|agent_canon_workflow and nonempty {BRANCH_REASON_ENV}"
        )
    if intent.requires_destructive:
        requirements.append(f"same-segment {DESTRUCTIVE_AUTHORITY_ENV}=explicit_user_approval and nonempty {DESTRUCTIVE_REASON_ENV}")
    if intent.requires_preservation:
        requirements.append(
            f"same-segment {PRESERVATION_INVENTORY_ENV} and {PRESERVATION_PLAN_ENV}"
        )
    if intent.requires_creation and intent.requires_destructive:
        next_action = "request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason"
    elif intent.requires_creation:
        next_action = "request_branch_or_worktree_creation_authority_then_rerun_same_command_with_inline_git_authority_and_reason"
    else:
        next_action = "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval"
    return {
        "decision": "block",
        "reason": (
            f"{'; '.join(markers)}: protected shared-checkout Git intent lacks required authority. "
            f"operation={intent.kind}:{intent.subcommand}; requires={'; '.join(requirements)}"
        ),
        "next_action": next_action,
        "remediation": [
            "Inspect status and preserve changes owned by the user or another concurrent chat.",
            "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
            "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git.",
        ],
        "operation": f"{intent.kind}:{intent.subcommand}",
        "command_sha256": command_sha256(command),
    }


def preservation_block_payload(command: str, intent: GitIntent) -> dict[str, object]:
    """Return a redacted block payload for an unbound whole-file mutation."""
    if intent.subcommand == "commit":
        next_action = "use_repository_topic_clone_finalize_merge_after_preservation_readback"
    else:
        next_action = (
            "capture_conflict_inventory_then_attach_same-segment_"
            f"{PRESERVATION_INVENTORY_ENV}_and_{PRESERVATION_PLAN_ENV}"
        )
    return {
        "decision": "block",
        "reason": (
            "CONFLICT_PRESERVATION_GUARD=block: whole-file or conflict mutation "
            "requires an inventory and reconstruction/preservation plan; "
            f"operation={intent.kind}:{intent.subcommand}"
        ),
        "next_action": next_action,
        "operation": f"{intent.kind}:{intent.subcommand}",
        "command_sha256": command_sha256(command),
    }
