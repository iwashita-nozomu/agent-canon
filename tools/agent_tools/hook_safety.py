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
import re
import shlex
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
SHELL_OPTIONS_WITH_VALUES = {"-O", "+O", "-o", "--init-file", "--rcfile"}
BRANCH_AUTHORITY_ENV = "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY"
BRANCH_REASON_ENV = "AGENT_CANON_BRANCH_WORKTREE_REASON"
DESTRUCTIVE_AUTHORITY_ENV = "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY"
DESTRUCTIVE_REASON_ENV = "AGENT_CANON_DESTRUCTIVE_GIT_REASON"
ALLOWED_BRANCH_AUTHORITIES = {"user_request", "agent_canon_workflow"}
DESTRUCTIVE_AUTHORITY = "explicit_user_approval"
READ_ONLY_BRANCH_OPTIONS = {
    "--all", "--color", "--contains", "--format", "--ignore-case", "--list",
    "--merged", "--no-color", "--no-contains", "--no-merged", "--points-at",
    "--remotes", "--show-current", "--sort", "--verbose", "-a", "-r", "-v", "-vv",
}
READ_ONLY_BRANCH_VALUE_OPTIONS = {
    "--color", "--contains", "--format", "--merged", "--no-contains",
    "--no-merged", "--points-at", "--sort",
}
BRANCH_NORMAL_CREATE_SHORTS = {"c"}
BRANCH_FORCE_SHORTS = {"C", "f"}
BRANCH_DESTRUCTIVE_SHORTS = {"D", "M", "d", "m"}
BRANCH_CREATION_MODIFIERS = {"--create-reflog", "--no-track", "--track"}
PROTECTED_GIT_SUBCOMMANDS = frozenset(
    {"restore", "reset", "clean", "checkout", "switch", "stash", "branch", "worktree"}
)
PROTECTED_UPDATE_MODES = frozenset(
    {"latest", "apply", "merge-main-into-current", "merge-main-into-current-preserve-dirty"}
)
PROTECTED_MAKE_TARGETS = frozenset(
    {"agent-canon-ensure-latest", "agent-canon-latest", "agent-canon-update"}
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


def normalized_shell_command(segment: tuple[str, ...]) -> GitCommand | None:
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
    index = consume_exec_prefix(tokens, index)
    index = consume_env_prefix(tokens, index, values)
    while index < len(tokens):
        pair = assignment(tokens[index])
        if pair is None:
            break
        values[pair[0]] = pair[1]
        index += 1
    index = consume_command_prefix(tokens, index)
    if index >= len(tokens):
        return None
    return GitCommand(tuple(tokens[index:]), tuple(values.items()))


def protected_update_intent(command: GitCommand) -> GitIntent | None:
    if not command.tokens:
        return None
    executable_token = command.tokens[0].replace("\\", "/")
    executable = command_basename(executable_token)
    arguments = command.tokens[1:]
    script = executable_token
    script_arguments = arguments
    if executable in SHELL_WRAPPERS and arguments:
        script_index = 0
        while script_index < len(arguments) and arguments[script_index].startswith("-"):
            if arguments[script_index] == "--":
                script_index += 1
                break
            if arguments[script_index] in SHELL_OPTIONS_WITH_VALUES:
                script_index += 2
                continue
            if arguments[script_index].startswith(("--init-file=", "--rcfile=")):
                script_index += 1
                continue
            script_index += 1
        if script_index >= len(arguments):
            return None
        script = arguments[script_index].replace("\\", "/")
        script_arguments = arguments[script_index + 1 :]
    if script.endswith("tools/update_agent_canon.sh") and script_arguments:
        mode = script_arguments[0]
        if mode in PROTECTED_UPDATE_MODES:
            return GitIntent("protected_agent_canon_update", mode, "protected update wrapper", True, True)
    if script.endswith("tools/sync_agent_canon.sh") and script_arguments and script_arguments[0] == "ensure-latest":
        return GitIntent("protected_agent_canon_update", "ensure-latest", "protected sync wrapper", True, True)
    if executable in {"make", "gmake"}:
        targets = PROTECTED_MAKE_TARGETS.intersection(arguments)
        if targets:
            target = sorted(targets)[0]
            return GitIntent("protected_agent_canon_update", target, "protected make target", True, True)
    return None


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
            return GitIntent("destructive_branch_creation", subcommand, "force-create/ref-overwrite", True, True)
        if normal_create:
            return GitIntent("branch_creation", subcommand, "create/orphan", True, False)
        return GitIntent("destructive_git", subcommand, "current-checkout mutation", False, True)
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
    return (not intent.requires_creation or (creation_authorized(command) and destructive_authorized(command))) and (not intent.requires_destructive or destructive_authorized(command))


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
        shell_command = normalized_shell_command(segment)
        if shell_command is not None:
            intent = protected_update_intent(shell_command)
            if intent is not None and not intent_authorized(shell_command, intent):
                return intent
        if intent := opaque_protected_intent(" ".join(segment)):
            return intent
    return None


def first_block(command: str) -> GitIntent | None:
    """Return the first unauthorized direct or backtick-substituted Git intent."""
    complete, uncertain = backtick_command_substitutions(command)
    for substitution in (*complete, *uncertain):
        if intent := first_block(substitution):
            return intent
    return _first_block_without_backticks(command)


def branch_block_payload(command: str, intent: GitIntent) -> dict[str, object]:
    """Return a redacted block payload; command text never crosses the leaf boundary."""
    markers = []
    if intent.requires_destructive:
        markers.append("DESTRUCTIVE_GIT_GUARD=block")
    if intent.requires_creation:
        markers.append("BRANCH_WORKTREE_CREATION_GUARD=block")
    requirements: list[str] = []
    if intent.requires_creation:
        requirements.extend(
            [
                f"same-segment {BRANCH_AUTHORITY_ENV}=user_request|agent_canon_workflow and nonempty {BRANCH_REASON_ENV}",
                f"same-segment {DESTRUCTIVE_AUTHORITY_ENV}=explicit_user_approval and nonempty {DESTRUCTIVE_REASON_ENV}",
            ]
        )
    elif intent.requires_destructive:
        requirements.append(f"same-segment {DESTRUCTIVE_AUTHORITY_ENV}=explicit_user_approval and nonempty {DESTRUCTIVE_REASON_ENV}")
    return {
        "decision": "block",
        "reason": (
            f"{'; '.join(markers)}: protected shared-checkout Git intent lacks required authority. "
            f"operation={intent.kind}:{intent.subcommand}; requires={'; '.join(requirements)}"
        ),
        "next_action": (
            "request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason"
            if intent.requires_creation
            else "inspect_status_preserve_other_task_changes_or_record_explicit_user_approval"
        ),
        "remediation": [
            "Inspect status and preserve changes owned by the user or another concurrent chat.",
            "Continue only on proven task-owned exact paths; that evidence bounds an approval request and never bypasses explicit destructive approval.",
            "If the user explicitly approves the protected action, place every required authority and reason assignment in the same shell segment immediately before Git.",
        ],
        "operation": f"{intent.kind}:{intent.subcommand}",
        "command_sha256": command_sha256(command),
    }
