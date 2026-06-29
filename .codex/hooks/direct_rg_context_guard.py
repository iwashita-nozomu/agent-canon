#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Warns on context-polluting direct rg usage before shell execution.
# upstream implementation ../hooks.json invokes hook dispatcher for PreToolUse.
# upstream implementation ./hook_dispatcher.py dispatches this guard before read-only bypass.
# upstream design ../../documents/codex-configuration-reference.md documents hook warning policy.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates direct rg context-risk warnings.
# @dependency-end
"""Warn when a Bash command is likely to dump broad `rg` output into context."""

from __future__ import annotations

import json
import shlex
import sys

COMMAND_SEPARATORS = {"&&", "||", ";", "|"}
OUTPUT_LIMIT_FLAGS = {"-c", "--count", "--count-matches", "-l", "--files-with-matches", "--files"}
OUTPUT_LIMIT_OPTIONS_WITH_VALUES = {"-m", "--max-count"}
RISKY_EXCLUDED_PATHS = (".agent-canon/log-archive", "reports", "*.jsonl")
SHELL_TOOL_NAMES = {"bash", "Bash"}
SHELL_WRAPPERS = {"bash", "sh", "zsh"}
BROAD_PATHS = {"", ".", ".."}


def load_payload() -> dict[str, object]:
    """Read one hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def tool_name(payload: dict[str, object]) -> str:
    """Return the Codex tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def command_text(payload: dict[str, object]) -> str:
    """Return the Bash command text from the hook payload."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("cmd", "command"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    for key in ("cmd", "command"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def shell_tokens(command: str) -> tuple[str, ...]:
    """Return shell tokens, preserving common command separators."""
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
    return token.rsplit("/", 1)[-1]


def is_env_assignment(token: str) -> bool:
    """Return whether a token is a simple environment assignment."""
    name, separator, _value = token.partition("=")
    return bool(separator and name and not token.startswith("-"))


def shell_wrapper_script(tokens: tuple[str, ...]) -> str:
    """Return the script passed to `sh -c` style wrappers."""
    if not tokens or command_basename(tokens[0]) not in SHELL_WRAPPERS:
        return ""
    for index, token in enumerate(tokens[1:], start=1):
        if token == "--":
            return ""
        if token == "-c" or (token.startswith("-") and "c" in token[1:]):
            script_index = index + 1
            return tokens[script_index] if script_index < len(tokens) else ""
    return ""


def command_segments(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Split shell tokens into command segments around common separators."""
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


def rg_segment_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Return an `rg` invocation from one command segment, allowing env wrappers."""
    index = 0
    while index < len(tokens) and is_env_assignment(tokens[index]):
        index += 1
    if index < len(tokens) and tokens[index] == "command":
        index += 1
    if index < len(tokens) and tokens[index] == "env":
        index += 1
        while index < len(tokens) and (
            tokens[index].startswith("-") or is_env_assignment(tokens[index])
        ):
            index += 1
    while index < len(tokens) and is_env_assignment(tokens[index]):
        index += 1
    return tokens[index:] if index < len(tokens) and command_basename(tokens[index]) == "rg" else ()


def rg_token_sequences(command: str) -> tuple[tuple[str, ...], ...]:
    """Return all direct `rg` invocations visible in a shell command."""
    tokens = shell_tokens(command)
    if not tokens:
        return ()
    script = shell_wrapper_script(tokens)
    if script:
        return rg_token_sequences(script)
    sequences: list[tuple[str, ...]] = []
    for segment in command_segments(tokens):
        rg_tokens = rg_segment_tokens(segment)
        if rg_tokens:
            sequences.append(rg_tokens)
    return tuple(sequences)


def rg_tokens(command: str) -> tuple[str, ...]:
    """Return the first `rg` token sequence for compatibility with tests."""
    sequences = rg_token_sequences(command)
    return sequences[0] if sequences else ()


def has_output_limit(tokens: tuple[str, ...]) -> bool:
    """Return whether `rg` output is already bounded or file-list only."""
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            break
        if token in OUTPUT_LIMIT_FLAGS:
            return True
        if token in OUTPUT_LIMIT_OPTIONS_WITH_VALUES:
            return True
        if token.startswith("--max-count=") or (token.startswith("-m") and len(token) > 2):
            return True
        index += 1
    return False


def has_line_numbers(tokens: tuple[str, ...]) -> bool:
    """Return whether `rg` is asked to print matching lines."""
    return "-n" in tokens or "--line-number" in tokens or "--vimgrep" in tokens


def excludes_risky_paths(tokens: tuple[str, ...]) -> bool:
    """Return whether known high-volume log/report paths are excluded."""
    joined = " ".join(tokens)
    return all(path in joined for path in RISKY_EXCLUDED_PATHS)


def bounded_path_args(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Return non-option path-like args after the pattern argument."""
    path_args: list[str] = []
    pattern_seen = False
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in OUTPUT_LIMIT_OPTIONS_WITH_VALUES or token in {"-g", "--glob", "--iglob"}:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        if not pattern_seen:
            pattern_seen = True
            continue
        path_args.append(token)
    return tuple(path_args)


def is_broad_path(path: str) -> bool:
    """Return whether a path token names the current, parent, or filesystem root."""
    return path.rstrip("/") in BROAD_PATHS or path == "/"


def risky_rg_tokens(tokens: tuple[str, ...]) -> bool:
    """Return whether one `rg` invocation can dump broad line matches."""
    if has_output_limit(tokens) or not has_line_numbers(tokens):
        return False
    paths = bounded_path_args(tokens)
    if paths and not any(is_broad_path(path) for path in paths):
        return False
    return not excludes_risky_paths(tokens)


def risky_direct_rg(command: str) -> bool:
    """Return whether a command is a context-polluting direct `rg` risk."""
    return any(risky_rg_tokens(tokens) for tokens in rg_token_sequences(command))


def warning_payload(command: str) -> dict[str, object]:
    """Return a non-blocking hook warning payload."""
    return {
        "decision": "approve",
        "reason": (
            "DIRECT_RG_CONTEXT_RISK=warn: direct `rg -n` over a broad or root scope can "
            "dump large logs/reports into context. Use `rg -l` first, bound the path, "
            "exclude `.agent-canon/log-archive/**`, `reports/**`, and `*.jsonl`, or add "
            "`--max-count` before printing matches."
        ),
        "next_action": "replace_broad_rg_with_bounded_or_compact_search",
        "remediation": [
            "`rg --files` or `rg -l '<pattern>' <bounded dirs>` for discovery.",
            "`rg -n '<pattern>' <specific files or bounded dirs>` for line details.",
            "Exclude `.agent-canon/log-archive/**`, `reports/**`, and `*.jsonl` for ordinary repo search.",
            "This warning is non-blocking; record unresolved direct-rg findings before closeout.",
        ],
        "command": command.strip(),
    }


def main() -> int:
    """Run the direct-rg context-risk guard."""
    payload = load_payload()
    if tool_name(payload) not in SHELL_TOOL_NAMES:
        return 0
    command = command_text(payload)
    if risky_direct_rg(command):
        json.dump(warning_payload(command), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
