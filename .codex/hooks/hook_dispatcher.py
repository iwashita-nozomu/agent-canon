#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Dispatches Codex lifecycle hook events to the configured guard scripts.
# upstream implementation ../hooks.json invokes this dispatcher once per active hook event.
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py owns Codex trace environment names.
# upstream design ../README.md documents dispatcher-based hook wiring.
# downstream implementation ./codex_runtime_summary_logger.py exports bounded Codex runtime summaries on Stop
# downstream implementation ./runtime_log_auto_sync.py syncs mounted runtime logs and agent reports on Stop
# downstream implementation ./branch_worktree_guard.py blocks unconfirmed branch and worktree creation.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates dispatch order and hook count.
# @dependency-end

"""Run the configured child hooks for one Codex lifecycle event."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "agent_tools"
if TOOLS_DIR.is_dir():
    sys.path.insert(0, str(TOOLS_DIR))

from runtime_log_paths import CODEX_TRACE_ENV_NAMES  # noqa: E402

DISPATCHER_DIR_ENV = "AGENT_CANON_HOOK_DISPATCHER_DIR"
GIT_ROOT_TIMEOUT_SECONDS = 5
MAX_REASON_LINES = 20
READ_ONLY_TOOL_NAMES = {"gitstatus", "read", "grep", "glob", "list", "ls"}
PUBLISH_TOOL_NAMES = {"gitpush", "githubpublish", "githubpr", "pullrequest"}
SAFE_GIT_GLOBAL_OPTIONS_WITH_VALUES = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
}
SAFE_GIT_GLOBAL_OPTION_PREFIXES = (
    "--git-dir=",
    "--work-tree=",
    "--namespace=",
)
SHELL_COMPOUND_MARKERS = ("\n", "&&", "||", ";", "|", "`", "$(", ">", "<")
READ_ONLY_COMMANDS = {"cat", "head", "tail", "wc", "ls", "pwd", "nl", "stat", "rg", "grep"}
SAFE_GH_PR_SUBCOMMANDS = {"checks", "comment", "create", "edit", "list", "view"}
STRICT_BLOCKS_ENV = "AGENT_CANON_HOOK_STRICT_BLOCKS"
STRICT_FAILURES_ENV = "AGENT_CANON_HOOK_STRICT_FAILURES"
# Most policy hooks are advisory by default so a bad guardrail cannot freeze
# ordinary shell/read/validation work. CI and hook development can opt into
# strict blocking with AGENT_CANON_HOOK_STRICT_BLOCKS=1.
CRITICAL_BLOCKING_CHILD_HOOKS = frozenset({"prompt_secret_guard.py", "branch_worktree_guard.py"})
ADDITIONAL_CONTEXT_EVENTS = frozenset({"UserPromptSubmit", "PreToolUse", "PostToolUse"})
SAFE_GIT_READ_SUBCOMMANDS = {"log", "ls-files", "rev-parse", "show", "status"}
SAFE_GIT_BRANCH_LIST_OPTIONS = {
    "--all",
    "--color",
    "--list",
    "--no-color",
    "--remotes",
    "--show-current",
    "--verbose",
    "-a",
    "-r",
    "-v",
    "-vv",
}
GIT_BRANCH_MUTATING_OPTIONS = {
    "--copy",
    "--delete",
    "--edit-description",
    "--move",
    "--set-upstream-to",
    "--unset-upstream",
    "-C",
    "-D",
    "-M",
    "-c",
    "-d",
    "-m",
}
GIT_BRANCH_MUTATING_OPTION_PREFIXES = ("--set-upstream-to=",)
GIT_WRITE_OUTPUT_OPTIONS = {"--output", "-o"}
GIT_WRITE_OUTPUT_OPTION_PREFIXES = ("--output=",)
SAFE_PYTHON_MODULE_CHECKS = {
    "json.tool",
    "pydocstyle",
    "py_compile",
    "pyright",
    "pytest",
    "ruff",
}
SAFE_MAKE_VALIDATION_TARGETS = {
    "agent-canon-pr-check",
    "agent-canon-latest-check",
    "agent-checks",
    "agent-surface-checks",
    "ci",
    "ci-quick",
    "docs-check",
    "github-workflow-check",
    "test",
}
SAFE_TOOL_SCRIPT_PREFIXES = (
    "check_",
    "evaluate_",
    "run_repo_dependency_review",
    "scan_dependency_headers",
    "tool_rejection_preflight",
)
SAFE_TOOL_SCRIPT_SUBCOMMANDS = {
    "runtime_log_archive_git.py": {"repo-key", "status", "check-clean"},
}
SAFE_SED_PRINT_SCRIPT = re.compile(r"^(?:\d+|\$)(?:,(?:\d+|\$))?p$")
FAST_HOOK_TIMEOUT_SECONDS = 10
REFERENCE_CAPTURE_TIMEOUT_SECONDS = 15
CAUSE_INVESTIGATION_TIMEOUT_SECONDS = 30
STANDARD_GUARD_TIMEOUT_SECONDS = 60
STYLE_CHECKER_TIMEOUT_SECONDS = 90
HOOK_CHILD_NOT_FOUND_RETURN_CODE = 127
HOOK_CHILD_TIMEOUT_RETURN_CODE = 124
PYTHON_MODULE_MIN_TOKENS = 3
PYTHON_MODULE_NAME_INDEX = 2
PYTHON_RUFF_CHECK_MIN_TOKENS = 4
PYTHON_RUFF_SUBCOMMAND_INDEX = 3
SCRIPT_MIN_TOKENS = 2
SCRIPT_PATH_INDEX = 1
SCRIPT_SUBCOMMAND_MIN_TOKENS = 3
SCRIPT_SUBCOMMAND_INDEX = 2
CODEX_TRACE_PAYLOAD_FIELDS = (
    "codex_trace_key",
    "codex_thread_id",
    "thread_id",
    "session_id",
    "conversation_id",
)


@dataclass(frozen=True)
class HookCommandSpec:
    """One child hook command and its legacy timeout."""

    script: str
    timeout: int


@dataclass(frozen=True)
class HookResult:
    """Captured result from one child hook command."""

    spec: HookCommandSpec
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def json_stdout(self) -> dict[str, object] | None:
        """Return parsed JSON stdout when the child emitted a hook payload."""
        text = self.stdout.strip()
        if not text:
            return None
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def blocks(self) -> bool:
        """Return whether this result is a Codex blocking hook payload."""
        payload = self.json_stdout()
        return payload is not None and payload.get("decision") == "block"

    def visible(self) -> bool:
        """Return whether this child emitted output Codex should see."""
        return bool(self.stdout.strip())

    def failed(self) -> bool:
        """Return whether the child command failed outside normal hook output."""
        return self.returncode != 0 or self.timed_out


EVENT_COMMANDS: dict[str, tuple[HookCommandSpec, ...]] = {
    "UserPromptSubmit": (
        HookCommandSpec("log_archive_mount_warning.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("prompt_secret_guard.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("skill_usage_logger.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("reference_capture_guard.py", FAST_HOOK_TIMEOUT_SECONDS),
    ),
    "PreToolUse": (
        HookCommandSpec("log_archive_mount_warning.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("branch_worktree_guard.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("direct_rg_context_guard.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("cause_investigation_guard.py", CAUSE_INVESTIGATION_TIMEOUT_SECONDS),
    ),
    "PostToolUse": (
        HookCommandSpec("skill_usage_logger.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("reference_capture_guard.py", REFERENCE_CAPTURE_TIMEOUT_SECONDS),
        HookCommandSpec("task_authority_schema_guard.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("role_write_policy_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("oop_readability_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("module_boundary_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("library_implementation_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("first_party_library_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("helper_inventory_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("helper_first_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("style_checker_guard.py", STYLE_CHECKER_TIMEOUT_SECONDS),
        HookCommandSpec("log_surface_inventory_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("notebook_quality_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
    ),
    "Stop": (
        HookCommandSpec("goal_completion_guard.py", REFERENCE_CAPTURE_TIMEOUT_SECONDS),
        HookCommandSpec("task_authority_schema_guard.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("role_write_policy_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("oop_readability_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("module_boundary_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("library_implementation_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("first_party_library_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("helper_inventory_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("helper_first_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("style_checker_guard.py", STYLE_CHECKER_TIMEOUT_SECONDS),
        HookCommandSpec("log_surface_inventory_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("notebook_quality_guard.py", STANDARD_GUARD_TIMEOUT_SECONDS),
        HookCommandSpec("reference_capture_guard.py", REFERENCE_CAPTURE_TIMEOUT_SECONDS),
        HookCommandSpec("skill_usage_logger.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("codex_runtime_summary_logger.py", FAST_HOOK_TIMEOUT_SECONDS),
        HookCommandSpec("runtime_log_auto_sync.py", STANDARD_GUARD_TIMEOUT_SECONDS),
    ),
}

EVENT_ALIASES = {
    event.casefold(): event
    for event in EVENT_COMMANDS
} | {
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
}


def load_raw_payload() -> bytes:
    """Read the hook payload once so every child receives identical stdin."""
    return sys.stdin.buffer.read()


def json_payload(raw_payload: bytes) -> dict[str, object]:
    """Return decoded hook payload JSON when available."""
    if not raw_payload.strip():
        return {}
    try:
        loaded = json.loads(raw_payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def payload_trace_key(payload: dict[str, object]) -> str:
    """Return the Codex trace key carried by one hook payload."""
    for field in CODEX_TRACE_PAYLOAD_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def child_hook_environment(payload: dict[str, object]) -> dict[str, str]:
    """Return the environment shared by child hooks."""
    env = os.environ.copy()
    canonical_trace_env = CODEX_TRACE_ENV_NAMES[0]
    if env.get(canonical_trace_env, "").strip():
        return env
    trace_key = payload_trace_key(payload) or next(
        (
            env.get(name, "").strip()
            for name in CODEX_TRACE_ENV_NAMES[1:]
            if env.get(name, "").strip()
        ),
        "",
    )
    if trace_key:
        env[canonical_trace_env] = trace_key
    return env


def tool_name(payload: dict[str, object]) -> str:
    """Return the tool name from a hook payload."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def tool_command(payload: dict[str, object]) -> str:
    """Return command text from a hook payload."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd")
        if isinstance(command, str):
            return command
    for key in ("command", "cmd"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def compact_tool_name(name: str) -> str:
    """Return a comparison key for tool names across runtime spellings."""
    return "".join(character for character in name.casefold() if character.isalnum())


def git_subcommand_tokens(command: str) -> tuple[str, ...]:
    """Return Git subcommand tokens for simple one-command invocations."""
    stripped = command.strip()
    if not stripped or any(marker in stripped for marker in SHELL_COMPOUND_MARKERS):
        return ()
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return ()
    if not tokens or tokens[0] != "git":
        return ()
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in SAFE_GIT_GLOBAL_OPTIONS_WITH_VALUES:
            index += 2
            continue
        if any(token.startswith(prefix) for prefix in SAFE_GIT_GLOBAL_OPTION_PREFIXES):
            index += 1
            continue
        break
    return tuple(tokens[index:])


def simple_shell_tokens(command: str) -> tuple[str, ...]:
    """Return tokens for a simple one-command shell payload."""
    stripped = command.strip()
    if not stripped or any(marker in stripped for marker in SHELL_COMPOUND_MARKERS):
        return ()
    try:
        return tuple(shlex.split(stripped))
    except ValueError:
        return ()


def read_only_git_command(command: str) -> bool:
    """Return whether a Bash command is only Git inspection."""
    tokens = git_subcommand_tokens(command)
    if not tokens:
        return False
    subcommand = tokens[0]
    arguments = tokens[1:]
    if any(git_write_output_argument(argument) for argument in arguments):
        return False
    if subcommand == "status":
        return True
    if subcommand == "diff":
        return "--ext-diff" not in arguments
    if subcommand == "branch":
        return read_only_git_branch_arguments(arguments)
    if subcommand == "remote":
        return read_only_git_remote_arguments(arguments)
    if len(tokens) >= 2 and tokens[:2] == ("submodule", "status"):
        return True
    return subcommand in SAFE_GIT_READ_SUBCOMMANDS


def git_write_output_argument(argument: str) -> bool:
    """Return whether a Git argument writes command output to a file."""
    return (
        argument in GIT_WRITE_OUTPUT_OPTIONS
        or argument.startswith(GIT_WRITE_OUTPUT_OPTION_PREFIXES)
        or (argument.startswith("-o") and not argument.startswith("--"))
    )


def read_only_git_branch_arguments(arguments: tuple[str, ...]) -> bool:
    """Return whether `git branch` arguments only list branch state."""
    if any(git_branch_mutating_argument(argument) for argument in arguments):
        return False
    if not arguments:
        return True
    if arguments == ("--show-current",):
        return True
    if arguments[0] == "--list":
        return all(git_branch_list_argument(argument) for argument in arguments)
    return all(argument in SAFE_GIT_BRANCH_LIST_OPTIONS or argument.startswith("--format=") for argument in arguments)


def git_branch_mutating_argument(argument: str) -> bool:
    """Return whether a `git branch` argument mutates branch metadata."""
    return argument in GIT_BRANCH_MUTATING_OPTIONS or argument.startswith(GIT_BRANCH_MUTATING_OPTION_PREFIXES)


def git_branch_list_argument(argument: str) -> bool:
    """Return whether a `git branch --list` argument is list-only."""
    return argument in SAFE_GIT_BRANCH_LIST_OPTIONS or argument.startswith("--format=") or not argument.startswith("-")


def read_only_git_remote_arguments(arguments: tuple[str, ...]) -> bool:
    """Return whether `git remote` arguments only inspect remote state."""
    if not arguments or arguments in {("-v",), ("--verbose",)}:
        return True
    return arguments[0] in {"get-url", "show"}


def read_only_shell_command(command: str) -> bool:
    """Return whether a Bash command is a simple read-only inspection."""
    if read_only_git_command(command):
        return True
    tokens = simple_shell_tokens(command)
    if not tokens:
        return False
    if tokens[0] == "sed":
        return read_only_sed_arguments(tokens[1:])
    if tokens[0] == "rg":
        return False
    return tokens[0] in READ_ONLY_COMMANDS


def publish_shell_command(command: str) -> bool:
    """Return whether a Bash command is a GitHub publish/PR operation.

    Publish operations are owned by `github_publish.py` and PR workflow gates,
    not by edit-time guard hooks. This keeps hook findings from blocking branch
    publication while preserving explicit tool-level remote verification.
    """
    git_tokens = git_subcommand_tokens(command)
    if git_tokens and git_tokens[0] == "push":
        return True
    tokens = simple_shell_tokens(command)
    if not tokens:
        return False
    if tokens[0] == "gh" and len(tokens) >= 3 and tokens[1] == "pr":
        return tokens[2] in SAFE_GH_PR_SUBCOMMANDS
    if tokens[0] in {"python", "python3"} and len(tokens) >= SCRIPT_MIN_TOKENS:
        script = Path(tokens[SCRIPT_PATH_INDEX])
        return script.as_posix() == "tools/agent_tools/github_publish.py"
    if tokens[0] == "bash" and len(tokens) >= SCRIPT_MIN_TOKENS:
        script = Path(tokens[SCRIPT_PATH_INDEX])
        return script.as_posix() == "tools/push_origin.sh"
    return False


def read_only_sed_arguments(arguments: tuple[str, ...]) -> bool:
    """Return whether `sed` arguments are limited to range printing."""
    if any(sed_in_place_argument(argument) for argument in arguments):
        return False
    script_candidates = [
        argument
        for argument in arguments
        if argument not in {"-n", "--quiet", "--silent", "--"}
    ]
    return bool(script_candidates) and bool(SAFE_SED_PRINT_SCRIPT.fullmatch(script_candidates[0]))


def sed_in_place_argument(argument: str) -> bool:
    """Return whether a sed argument enables in-place writes."""
    if argument == "--in-place" or argument.startswith("--in-place="):
        return True
    return argument.startswith("-") and not argument.startswith("--") and "i" in argument[1:]


def safe_python_validation(tokens: tuple[str, ...]) -> bool:
    """Return whether tokens invoke a Python validation command."""
    if len(tokens) >= PYTHON_MODULE_MIN_TOKENS and tokens[SCRIPT_PATH_INDEX] == "-m":
        module = tokens[PYTHON_MODULE_NAME_INDEX]
        if module == "ruff":
            return (
                len(tokens) >= PYTHON_RUFF_CHECK_MIN_TOKENS
                and tokens[PYTHON_RUFF_SUBCOMMAND_INDEX] == "check"
            )
        return module in SAFE_PYTHON_MODULE_CHECKS
    if len(tokens) >= SCRIPT_MIN_TOKENS:
        script = Path(tokens[SCRIPT_PATH_INDEX])
        if safe_tool_script_subcommand(script, tokens[SCRIPT_SUBCOMMAND_INDEX:]):
            return True
        if script.parts[:2] == ("tools", "agent_tools"):
            return script.name.startswith(SAFE_TOOL_SCRIPT_PREFIXES)
        if script.parts[:2] == ("tools", "docs") and script.name.startswith("check_"):
            return True
        if script.parts[:2] in {("tools", "validation"), ("tools", "oop")}:
            return True
    return False


def safe_bash_validation(tokens: tuple[str, ...]) -> bool:
    """Return whether tokens invoke a Bash validation script."""
    if len(tokens) < SCRIPT_MIN_TOKENS:
        return False
    script = Path(tokens[SCRIPT_PATH_INDEX])
    if script.as_posix() == "tools/sync_agent_canon.sh":
        return (
            len(tokens) >= SCRIPT_SUBCOMMAND_MIN_TOKENS
            and tokens[SCRIPT_SUBCOMMAND_INDEX] in {"check", "plan", "status"}
        )
    if script.as_posix() == "tools/update_agent_canon.sh":
        return (
            len(tokens) >= SCRIPT_SUBCOMMAND_MIN_TOKENS
            and tokens[SCRIPT_SUBCOMMAND_INDEX] in {"plan", "status"}
        )
    if safe_tool_script_subcommand(script, tokens[SCRIPT_SUBCOMMAND_INDEX:]):
        return True
    if script.parts[:2] == ("tools", "agent_tools"):
        return script.name.startswith(SAFE_TOOL_SCRIPT_PREFIXES)
    if script.parts[:2] == ("tools", "ci"):
        return script.name.startswith(("check_", "run_"))
    return False


def safe_tool_script_subcommand(script: Path, arguments: tuple[str, ...]) -> bool:
    """Return whether one repo tool subcommand is a read-only validation command."""
    allowed = SAFE_TOOL_SCRIPT_SUBCOMMANDS.get(script.name)
    if not allowed:
        return False
    if script.parts[:2] != ("tools", "agent_tools"):
        return False
    subcommand = first_non_option_argument(arguments)
    return subcommand in allowed


def first_non_option_argument(arguments: tuple[str, ...]) -> str:
    """Return the first positional token after leading CLI options."""
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            return arguments[index + 1] if index + 1 < len(arguments) else ""
        if not argument.startswith("-"):
            return argument
        if argument in {"--source-root", "--canon-root", "--remote", "--archive-root"}:
            index += 2
            continue
        index += 1
    return ""


def validation_command(command: str) -> bool:
    """Return whether a Bash command is a known validation/check command."""
    tokens = simple_shell_tokens(command)
    if not tokens:
        return False
    if tokens[0] in {"pytest", "pyright", "pydocstyle"}:
        return True
    if tokens[0] == "ruff":
        return len(tokens) >= 2 and tokens[1] == "check"
    if tokens[0] in {"python", "python3"}:
        return safe_python_validation(tokens)
    if tokens[0] == "bash":
        return safe_bash_validation(tokens)
    if tokens[0] == "make":
        return bool(tokens[1:]) and all(token in SAFE_MAKE_VALIDATION_TARGETS for token in tokens[1:])
    return False


def bypass_child_guards_payload(raw_payload: bytes) -> bool:
    """Return whether this hook payload should skip child guard execution."""
    payload = json_payload(raw_payload)
    compact_name = compact_tool_name(tool_name(payload))
    if compact_name in READ_ONLY_TOOL_NAMES or compact_name in PUBLISH_TOOL_NAMES:
        return True
    command = tool_command(payload)
    return read_only_shell_command(command) or validation_command(command) or publish_shell_command(command)


def env_truthy(name: str) -> bool:
    """Return whether an environment flag is truthy."""
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "on"}


def repo_root() -> Path:
    """Return the active repository root for child hook execution."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def hook_directory() -> Path:
    """Return the directory containing child hook scripts."""
    override = os.environ.get(DISPATCHER_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent


def normalize_event(raw_event: str) -> str:
    """Return the canonical lifecycle event name."""
    event = EVENT_ALIASES.get(raw_event.casefold())
    if event:
        return event
    choices = ", ".join(EVENT_COMMANDS)
    raise SystemExit(f"unknown hook event {raw_event!r}; expected one of: {choices}")


def run_hook_command(
    spec: HookCommandSpec,
    *,
    raw_payload: bytes,
    root: Path,
    hooks_dir: Path,
    env: dict[str, str],
) -> HookResult:
    """Run one child hook script with the original payload."""
    script = hooks_dir / spec.script
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            input=raw_payload,
            cwd=root,
            check=False,
            capture_output=True,
            env=env,
            timeout=spec.timeout,
        )
    except OSError as exc:
        return HookResult(
            spec=spec,
            returncode=HOOK_CHILD_NOT_FOUND_RETURN_CODE,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = bytes(exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = bytes(exc.stderr or b"").decode("utf-8", errors="replace")
        timeout_message = f"{spec.script} timed out after {spec.timeout} seconds"
        return HookResult(
            spec=spec,
            returncode=HOOK_CHILD_TIMEOUT_RETURN_CODE,
            stdout=stdout,
            stderr="\n".join(part for part in (stderr, timeout_message) if part),
            timed_out=True,
        )
    return HookResult(
        spec=spec,
        returncode=result.returncode,
        stdout=result.stdout.decode("utf-8", errors="replace"),
        stderr=result.stderr.decode("utf-8", errors="replace"),
    )


def failure_payload(result: HookResult) -> dict[str, object]:
    """Return a blocking payload for child process failures."""
    detail_lines = [
        line
        for text in (result.stderr, result.stdout)
        for line in text.splitlines()
        if line.strip()
    ][:MAX_REASON_LINES]
    detail = "\n".join(detail_lines)
    return {
        "decision": "block",
        "reason": (
            "Hook dispatcher child command failed. Fix the child hook or rerun "
            f"the original hook directly.\n{result.spec.script}\n{detail}"
        ).strip(),
        "next_action": "fix_child_hook_failure_then_retry",
        "remediation": [
            f"Run `.codex/hooks/{result.spec.script}` directly with the same payload.",
            "Fix the child hook failure before continuing the tool action.",
        ],
    }


def visible_context_payload(
    event: str,
    *,
    reason: str,
    remediation: Sequence[str] = (),
    child_outputs: Sequence[dict[str, str]] = (),
    next_action: str | None = None,
) -> dict[str, object]:
    """Return an official non-blocking context payload for a hook event."""
    context_parts = [reason.strip()] if reason.strip() else []
    if remediation:
        context_parts.append(
            "Remediation:\n" + "\n".join(f"- {item}" for item in remediation)
        )
    payload: dict[str, object] = {
        "systemMessage": reason.strip(),
    }
    if event in ADDITIONAL_CONTEXT_EVENTS:
        payload["hookSpecificOutput"] = {
            "hookEventName": event,
            "additionalContext": "\n\n".join(context_parts),
        }
    if next_action is not None:
        payload["next_action"] = next_action
    if remediation:
        payload["remediation"] = list(remediation)
    if child_outputs:
        payload["child_output_count"] = len(child_outputs)
        payload["child_outputs"] = list(child_outputs)
    return payload


def failure_warning_payload(event: str, result: HookResult) -> dict[str, object]:
    """Return a non-blocking warning payload for child process failures."""
    blocking = failure_payload(result)
    reason = (
        "Hook child command failed, but AgentCanon hook policy is fail-open by default. "
        "Continue the requested work and repair the hook/checker before closeout.\n"
        f"{blocking['reason']}"
    )
    remediation = [
        f"Run `.codex/hooks/{result.spec.script}` directly with the same payload.",
        "Fix the child hook failure before closeout or record a durable follow-up.",
        f"Set `{STRICT_FAILURES_ENV}=1` only in explicit hook-development validation.",
    ]
    return visible_context_payload(
        event,
        reason=reason,
        remediation=remediation,
        next_action="repair_child_hook_failure_without_blocking_current_work",
    )


def should_preserve_block(result: HookResult) -> bool:
    """Return whether a child block is critical enough to keep blocking."""
    return result.spec.script in CRITICAL_BLOCKING_CHILD_HOOKS or env_truthy(STRICT_BLOCKS_ENV)


def downgraded_block_payload(event: str, result: HookResult) -> dict[str, object]:
    """Return a non-blocking warning for a non-critical child block."""
    payload = result.json_stdout() or {}
    reason = payload.get("reason")
    reason_text = reason if isinstance(reason, str) and reason.strip() else result.stdout.strip()
    remediation_raw = payload.get("remediation")
    remediation = (
        [str(item) for item in remediation_raw]
        if isinstance(remediation_raw, list)
        else []
    )
    remediation.extend(
        [
            "Treat this as a guardrail finding, not a tool-stop condition.",
            "Run the named checker or hook directly before closeout if the finding affects the change.",
            f"Set `{STRICT_BLOCKS_ENV}=1` only for explicit hook enforcement tests.",
        ]
    )
    return visible_context_payload(
        event,
        reason=(
            "Non-critical hook requested a block, but AgentCanon hook policy "
            "downgraded it to a warning so repository work can continue.\n"
            f"child_hook={result.spec.script}\n{reason_text}"
        ).strip(),
        remediation=remediation,
        child_outputs=[{"script": result.spec.script, "stdout": result.stdout.strip()}],
        next_action="address_guardrail_finding_before_closeout",
    )


def non_block_payload(result: HookResult) -> dict[str, object] | None:
    """Return a non-blocking JSON payload emitted by a child hook."""
    payload = result.json_stdout()
    if payload is None or payload.get("decision") == "block":
        return None
    return payload


def visible_output_payload(event: str, results: list[HookResult]) -> dict[str, object] | None:
    """Combine non-blocking child outputs into one visible approve payload."""
    visible_results = [result for result in results if result.visible()]
    if not visible_results:
        return None
    payloads = [
        payload
        for result in visible_results
        if (payload := non_block_payload(result)) is not None
    ]
    text_outputs = [
        result.stdout.strip()
        for result in visible_results
        if non_block_payload(result) is None and result.stdout.strip()
    ]
    reason_parts: list[str] = []
    remediation: list[str] = []
    for payload in payloads:
        reason = payload.get("reason")
        if isinstance(reason, str) and reason.strip():
            reason_parts.append(reason.strip())
        raw_remediation = payload.get("remediation")
        if isinstance(raw_remediation, list):
            remediation.extend(str(item) for item in raw_remediation)
    reason_parts.extend(text_outputs)
    next_action = next(
        (
            payload.get("next_action")
            for payload in payloads
            if isinstance(payload.get("next_action"), str)
        ),
        None,
    )
    return visible_context_payload(
        event,
        reason="\n\n".join(reason_parts),
        remediation=remediation,
        child_outputs=[
            {
                "script": result.spec.script,
                "stdout": result.stdout.strip(),
            }
            for result in visible_results
        ],
        next_action=next_action,
    )


def emit_json_payload(payload: dict[str, object]) -> None:
    """Write one JSON hook payload."""
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def dispatch_event(event: str, raw_payload: bytes) -> int:
    """Run every child hook for one event and emit the highest-priority output."""
    if bypass_child_guards_payload(raw_payload):
        return 0
    payload = json_payload(raw_payload)
    child_env = child_hook_environment(payload)
    root = repo_root()
    hooks_dir = hook_directory()
    results = [
        run_hook_command(
            spec,
            raw_payload=raw_payload,
            root=root,
            hooks_dir=hooks_dir,
            env=child_env,
        )
        for spec in EVENT_COMMANDS[event]
    ]
    if event == "PostToolUse":
        return 0
    blocking = next((result for result in results if result.blocks()), None)
    failure = next((result for result in results if result.failed()), None)
    visible_payload = visible_output_payload(event, results)

    if blocking is not None:
        if should_preserve_block(blocking):
            sys.stdout.write(blocking.stdout)
            if not blocking.stdout.endswith("\n"):
                sys.stdout.write("\n")
        else:
            emit_json_payload(downgraded_block_payload(event, blocking))
        return 0
    if failure is not None:
        if env_truthy(STRICT_FAILURES_ENV):
            emit_json_payload(failure_payload(failure))
        else:
            emit_json_payload(failure_warning_payload(event, failure))
        return 0
    if visible_payload is not None:
        emit_json_payload(visible_payload)
    return 0


def command_list_payload(event: str | None) -> dict[str, object]:
    """Return a JSON-visible dispatch matrix for tests and reviews."""
    events = [event] if event is not None else list(EVENT_COMMANDS)
    return {
        "events": {
            name: [
                {"script": spec.script, "timeout": spec.timeout}
                for spec in EVENT_COMMANDS[name]
            ]
            for name in events
        },
        "event_count": len(events),
        "command_count": sum(len(EVENT_COMMANDS[name]) for name in events),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse dispatcher command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", nargs="?", help="Codex hook event to dispatch")
    parser.add_argument("--group", dest="group", help="Alias for the event argument")
    parser.add_argument("--list", action="store_true", help="Print the child hook matrix")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    raw_event = args.group or args.event
    if args.list:
        event = normalize_event(raw_event) if raw_event else None
        json.dump(command_list_payload(event), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if not raw_event:
        raise SystemExit("hook event is required")
    event = normalize_event(raw_event)
    return dispatch_event(event, load_raw_payload())


if __name__ == "__main__":
    raise SystemExit(main())
