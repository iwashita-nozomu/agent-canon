#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Produces read-only catalog-backed tool-command packets and checks their runtime projections.
# upstream design ../../agents/canonical/skills.md skill canon registry
# upstream design ../../agents/skills/task-routing.md deterministic skill routing contract
# upstream design ../../agents/skills/agent-orchestration.md tool-first skill execution contract
# upstream design ../../agents/skills/catalog.yaml public skill related-skill metadata
# upstream implementation ../../tools/agent_tools/route.py parses and validates the public skill catalog
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py resolves standalone/vendored owner roots for fallback execution
# downstream implementation ../../.agents/skills/agent-orchestration/SKILL.md materialized runtime skill command entry example
# downstream implementation ../../tools/agent_tools/check_convention_compliance.py verifies command section wiring
# downstream implementation ../../tests/agent_tools/test_skill_tool_commands.py tests command extraction and read-only checks
# @dependency-end
"""Produce read-only tool-command packets for AgentCanon runtime skills."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_canon_source_root import (
    RootResolution,
    SourceRootFailure,
    resolve_agent_canon_source_root,
)
from route import (
    load_skill_related_map,
    load_skill_required_tool_commands,
    load_skill_tool_commands,
)

DEFAULT_ROOT = Path.cwd()
RUNTIME_SKILL_ROOT = Path(".agents/skills")
HUMAN_SKILL_ROOT = Path("agents/skills")
SECTION_HEADING = "## Tool Commands"
SECTION_START = "<!-- skill-tool-commands:start -->"
SECTION_END = "<!-- skill-tool-commands:end -->"
COMMAND_TEMPLATE = (
    "python3 tools/agent_tools/skill_tool_commands.py show "
    "--skill {skill} --format text"
)
PROMPT_PLACEHOLDER = "<user request>"
FALLBACK_COMMAND = (
    f'python3 tools/agent_tools/route.py --prompt "{PROMPT_PLACEHOLDER}" --format json'
)
LEGACY_MAINTENANCE_COMMANDS = (
    "python3 tools/agent_tools/check_skill_frontmatter.py --root .",
    "python3 tools/agent_tools/skill_tool_commands.py check",
)
COMMON_RESOLUTION_WORDING = (
    "論理コマンドは、実行前に AgentCanon source root を基準として解決します。"
    "各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、"
    "fallback-only skill を含む script entry の script path は絶対 path にします。"
)
FORMAT_VALUES = ("text", "json")
SCRIPT_INTERPRETERS = ("python3", "python", "bash")
SOURCE_ROOT_SCRIPT_PREFIXES = (
    ".",
    "tools/",
    "agents/",
    ".agents/",
    "tests/",
    "scripts/",
)
SOURCE_ROOT_COMMAND_PREFIXES = (
    "./",
    "tools/",
    "agents/",
    ".agents/",
    "tests/",
)
COMMAND_PREFIXES = (
    "agent-canon ",
    "bash ",
    "cargo ",
    "gh ",
    "git ",
    "lake ",
    "make ",
    "npm ",
    "python ",
    "python3 ",
    "ruff ",
    "tools/",
)
ASSIGNMENT_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
MAKEFILE_NAMES = ("GNUmakefile", "makefile", "Makefile")
OPTIONAL_AGENT_CANON_MAKE_TARGETS = {
    "agent-canon-update-plan": "plan",
    "agent-canon-latest": "latest",
    "agent-canon-ensure-latest": "latest",
}
SOURCE_ROOT_PYTHONPATH = "vendor/agent-canon/tools:tools"
SOURCE_ROOT_UPDATE_PREFIX = (
    "python3",
    "-m",
    "agent_tools.agent_canon_source_root",
    "exec",
    "tools/update_agent_canon.sh",
)


def _canonical_makefile(repository_root: Path) -> Path | None:
    """Return Make's first default file only when it remains inside the repo."""
    root = repository_root.resolve()
    for name in MAKEFILE_NAMES:
        candidate = root / name
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            return None
        return resolved
    return None


def _logical_makefile_lines(text: str) -> Iterable[str]:
    """Yield non-recipe logical lines with odd trailing backslashes joined."""
    pending = ""
    pending_is_recipe = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        is_recipe = pending_is_recipe or raw_line.startswith("\t")
        if pending:
            line = pending + line.lstrip()
        trailing_backslashes = len(line) - len(line.rstrip("\\"))
        if trailing_backslashes % 2 == 1:
            pending = line[:-1] + " "
            pending_is_recipe = is_recipe
            continue
        if not is_recipe:
            yield line
        pending = ""
        pending_is_recipe = False
    if pending and not pending_is_recipe:
        yield pending


def _strip_unescaped_comment(line: str) -> str:
    """Remove a Make comment while preserving escaped hash characters."""
    escaped = False
    result: list[str] = []
    for character in line:
        if character == "#" and not escaped:
            break
        result.append(character)
        if character == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    return "".join(result)


def explicit_make_targets(makefile: Path) -> frozenset[str]:
    """Return only unconditional top-level literal target declarations."""
    try:
        text = makefile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset()

    targets: set[str] = set()
    define_depth = 0
    conditional_depth = 0
    for logical_line in _logical_makefile_lines(text):
        line = _strip_unescaped_comment(logical_line).strip()
        if not line:
            continue

        words = line.split()
        directive_words = words
        while directive_words and directive_words[0] in {
            "export",
            "override",
            "private",
        }:
            directive_words = directive_words[1:]
        directive = directive_words[0] if directive_words else ""

        if define_depth:
            if directive == "define":
                define_depth += 1
            elif directive == "endef":
                define_depth -= 1
            continue
        if directive == "define":
            define_depth = 1
            continue
        if directive == "endef":
            return frozenset()

        if directive in {"ifeq", "ifneq", "ifdef", "ifndef"}:
            conditional_depth += 1
            continue
        if directive == "else":
            if conditional_depth == 0:
                return frozenset()
            continue
        if directive == "endif":
            if conditional_depth == 0:
                return frozenset()
            conditional_depth -= 1
            continue
        if conditional_depth or ":" not in line:
            continue

        left, right = line.split(":", maxsplit=1)
        # Reject every assignment spelling and directive-shaped line. A
        # colon in an assignment value is not evidence for a target.
        if "=" in left or right.lstrip().startswith(("=", ":=")):
            continue
        literal_targets = left.split()
        if (
            not literal_targets
            or literal_targets[0]
            in {
                "-include",
                "export",
                "include",
                "override",
                "private",
                "sinclude",
                "undefine",
                "unexport",
                "vpath",
            }
            or any(
                re.fullmatch(r"[A-Za-z0-9_.@/+,-]+", token) is None
                for token in literal_targets
            )
        ):
            continue
        targets.update(literal_targets)

    if define_depth or conditional_depth:
        return frozenset()
    return frozenset(targets)


def make_target_is_explicit(repository_root: Path, target: str) -> bool:
    """Return whether the selected parent Makefile declares one literal target."""
    makefile = _canonical_makefile(repository_root)
    return makefile is not None and target in explicit_make_targets(makefile)


def resolve_optional_agent_canon_make_alias(
    command: str,
    repository_root: Path,
) -> str:
    """Keep an existing explicit alias or return the canonical owner-tool route."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    command_index = 0
    while (
        command_index < len(tokens)
        and ASSIGNMENT_TOKEN_RE.fullmatch(tokens[command_index])
    ):
        command_index += 1
    body = tokens[command_index:]
    if len(body) != 2 or body[0] != "make":
        return command
    mode = OPTIONAL_AGENT_CANON_MAKE_TARGETS.get(body[1])
    if mode is None or make_target_is_explicit(repository_root, body[1]):
        return command

    environment = [
        token
        for token in tokens[:command_index]
        if not token.startswith("PYTHONPATH=")
    ]
    resolved = (
        *environment,
        f"PYTHONPATH={SOURCE_ROOT_PYTHONPATH}",
        *SOURCE_ROOT_UPDATE_PREFIX,
        mode,
    )
    return shlex.join(resolved)


def resolve_optional_agent_canon_make_aliases(
    commands: Iterable[str],
    repository_root: Path,
) -> tuple[str, ...]:
    """Resolve every optional alias in stable input order."""
    return tuple(
        resolve_optional_agent_canon_make_alias(command, repository_root)
        for command in commands
    )
ISSUE_CONTRACT_MARKERS: dict[str, tuple[tuple[str, str], ...]] = {
    "experiment-lifecycle": (
        (
            "experiment-registry-contract",
            "documents/experiments/experiment-registry.md",
        ),
        (
            "experiment-registry-template-contract-path",
            "vendor/agent-canon/documents/experiments/experiment-registry.md",
        ),
        (
            "experiment-registry-project-root",
            "project-root `experiments/registry.toml`",
        ),
    ),
    "research-workflow": (
        (
            "critical-review-template-path",
            "vendor/agent-canon/documents/experiments/experiment-critical-review.md",
        ),
    ),
    "start-repository": (
        (
            "remote-doc-project-path",
            "documents/contracts/template-github-remote.md",
        ),
        (
            "bootstrap-doc-project-path",
            "documents/contracts/template-bootstrap.md",
        ),
        (
            "static-seed-contract-path",
            "documents/contracts/static-seed-export.md",
        ),
    ),
    "tool-finding-report": (
        (
            "workflow-monitoring-run-local-path",
            "reports/agents/",
        ),
        (
            "workflow-monitoring-template-path",
            "templates/agents/workflow_monitoring.md",
        ),
    ),
}
ISSUE_CONTRACT_FORBIDDEN: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "result-artifact-writeout": (
        (
            "bare-runtime-log-archive-push",
            re.compile(r"(?<!tools/agent_tools/)runtime_log_archive_git\.py push"),
        ),
    ),
    "tool-finding-report": (
        (
            "bare-workflow-monitoring-path",
            re.compile(r"(?<!/)workflow_monitoring\.md"),
        ),
    ),
}


@dataclass(frozen=True)
class SkillCommandPacket:
    """Catalog-owned command phases resolved for one runtime skill."""

    skill: str
    runtime_skill: str
    canonical_doc: str
    related_skills: tuple[str, ...]
    required_commands: tuple[str, ...]
    discovered_commands: tuple[str, ...]
    conditional_commands: tuple[str, ...]
    maintenance_commands: tuple[str, ...]
    resolved_required_commands: tuple[
        tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...
    ]
    resolved_discovered_commands: tuple[
        tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...
    ]
    resolved_conditional_commands: tuple[
        tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...
    ]
    resolved_maintenance_commands: tuple[
        tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...
    ]
    validation_commands: tuple[str, ...]


@dataclass(frozen=True)
class CommandPlan:
    """Typed execution plan for one packet command."""

    logical_command: str
    source_root: str
    execution_cwd: str
    execution_env: tuple[tuple[str, str], ...]
    execution_argv: tuple[str, ...]


@dataclass(frozen=True)
class PublicCommandProjection:
    """Transient public-layout projection of one logical command.

    ``CommandPlan`` remains the execution authority.  This value is deliberately
    not persisted in skill packets: it only supplies the path spelling shown to
    a caller in a standalone or derived checkout.
    """

    logical_command: str
    layout: str
    public_cwd: str
    public_env: tuple[tuple[str, str], ...]
    public_argv: tuple[str, ...]


def _public_tool_prefix(root_resolution: RootResolution) -> str:
    """Return the one public tool prefix for the selected checkout layout."""
    return "tools" if root_resolution.layout == "standalone" else "vendor/agent-canon/tools"


def _project_public_path(token: str, prefix: str) -> str:
    """Map source-relative AgentCanon tool paths to one public prefix."""
    if token.startswith("tools/agent-canon/tools/"):
        raise SourceRootFailure(
            "agent_canon_public_command_invalid",
            f"Nested public tools path is not valid: {token}",
        )
    if token.startswith("vendor/agent-canon/vendor/agent-canon/"):
        raise SourceRootFailure(
            "agent_canon_public_command_invalid",
            f"Repeated vendor source prefix is not valid: {token}",
        )
    if token.startswith("vendor/agent-canon/tools/"):
        return f"{prefix}/{token.removeprefix('vendor/agent-canon/tools/')}"
    if token.startswith("tools/"):
        return f"{prefix}/{token.removeprefix('tools/')}"
    return token


def _project_contract_path(token: str, prefix: str) -> str:
    """Project a source-document operand independently of the public tool path."""
    if token.startswith("vendor/agent-canon/vendor/agent-canon/"):
        raise SourceRootFailure(
            "agent_canon_public_command_invalid",
            f"Repeated vendor contract prefix is not valid: {token}",
        )
    if token.startswith("vendor/agent-canon/"):
        relative = token.removeprefix("vendor/agent-canon/")
        return relative if prefix == "tools" else token
    if token.startswith(("documents/", "agents/", "templates/")):
        return token if prefix == "tools" else f"vendor/agent-canon/{token}"
    return token


def _public_executable_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """Return only public path tokens that are executable positions."""
    candidates: list[str] = []
    if tokens and tokens[0].startswith(("tools/", "vendor/agent-canon/tools/")):
        candidates.append(tokens[0])
    if (
        len(tokens) > 1
        and tokens[0] in SCRIPT_INTERPRETERS
        and tokens[1].startswith(("tools/", "vendor/agent-canon/tools/"))
    ):
        candidates.append(tokens[1])
    candidates.extend(
        token
        for index, token in enumerate(tokens)
        if index > 0
        and tokens[index - 1] == "exec"
        and token.startswith(("tools/", "vendor/agent-canon/tools/"))
    )
    return tuple(dict.fromkeys(candidates))


def project_public_command(
    logical_command: str,
    root_resolution: RootResolution,
) -> PublicCommandProjection:
    """Project a catalog/skill logical command without changing execution.

    The parser is shared with ``build_command_plan``; only executable, source
    tool, and PYTHONPATH tokens are rewritten.  Operands such as ``--root`` and
    ``--contract`` remain independent logical paths.
    """
    raw = shlex.split(logical_command)
    if not raw:
        raise SourceRootFailure("agent_canon_public_command_invalid", "empty command")
    prefix = _public_tool_prefix(root_resolution)
    env: list[tuple[str, str]] = []
    index = 0
    while index < len(raw) and ASSIGNMENT_TOKEN_RE.fullmatch(raw[index]):
        key, value = raw[index].split("=", maxsplit=1)
        if key == "PYTHONPATH":
            projected: list[str] = []
            for entry in value.split(":"):
                if not entry:
                    continue
                if entry in {"tools", "vendor/agent-canon/tools"}:
                    entry = prefix
                projected.append(entry)
            value = ":".join(dict.fromkeys(projected))
        env.append((key, value))
        index += 1
    tokens = raw[index:]
    projected_tokens: list[str] = []
    for token_index, token in enumerate(tokens):
        if token_index == 1 and tokens[0] in SCRIPT_INTERPRETERS:
            projected_tokens.append(_project_public_path(token, prefix))
        elif token_index == 0 and token.startswith(("tools/", "vendor/agent-canon/tools/")):
            projected_tokens.append(_project_public_path(token, prefix))
        elif token_index > 0 and tokens[token_index - 1] == "exec":
            projected_tokens.append(_project_public_path(token, prefix))
        elif token_index > 0 and tokens[token_index - 1] == "--contract":
            projected_tokens.append(_project_contract_path(token, prefix))
        elif token.startswith("--contract="):
            key, value = token.split("=", maxsplit=1)
            projected_tokens.append(f"{key}={_project_contract_path(value, prefix)}")
        else:
            projected_tokens.append(token)
    public_tokens = tuple(projected_tokens)
    if root_resolution.layout != "standalone" and root_resolution.public_tool_root is not None:
        public_root = (
            root_resolution.current_repository_root / prefix
        ).resolve()
        for token in _public_executable_tokens(public_tokens):
            candidate = (
                root_resolution.current_repository_root / token
            ).resolve()
            try:
                candidate.relative_to(public_root)
            except ValueError as exc:
                raise SourceRootFailure(
                    "agent_canon_public_command_escape",
                    f"Public command escapes the authenticated public view: {token}",
                ) from exc
            if candidate.suffix in {".py", ".sh"} and not candidate.is_file():
                raise SourceRootFailure(
                    "agent_canon_public_command_missing",
                    f"Public executable does not exist: {token}",
                )
    return PublicCommandProjection(
        logical_command=shlex.join(raw),
        layout=root_resolution.layout,
        public_cwd=".",
        public_env=tuple(env),
        public_argv=public_tokens,
    )


def project_public_command_for_layout(
    logical_command: str,
    *,
    layout: str,
) -> PublicCommandProjection:
    """Project a logical command when only the resolved layout is available."""
    if layout not in {"standalone", "vendored", "override"}:
        raise SourceRootFailure("agent_canon_public_command_invalid", f"unknown layout: {layout}")
    # The projection itself is independent of source identity.  A lightweight
    # resolution object keeps this helper on the same owner seam without
    # persisting another command schema.
    resolution = RootResolution(
        current_repository_root=Path("."),
        source_root=Path("."),
        layout=layout,
        canon_root=Path("."),
        public_tool_root=None,
    )
    return project_public_command(logical_command, resolution)


@dataclass(frozen=True)
class Finding:
    """One skill-command-section finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable text finding."""
        return f"SKILL_TOOL_COMMANDS_FINDING={self.check}:{self.path}:{self.detail}"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Repository root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser("show", help="Print one skill command packet.")
    show.add_argument("--skill", required=True, help="Runtime skill name.")
    show.add_argument("--format", choices=FORMAT_VALUES, default="text")

    check = subparsers.add_parser("check", help="Check every runtime skill section.")
    check.add_argument("--format", choices=FORMAT_VALUES, default="text")

    return parser


def runtime_skill_paths(root: Path) -> list[Path]:
    """Return runtime SKILL.md files in stable order."""
    return sorted((root / RUNTIME_SKILL_ROOT).glob("*/SKILL.md"))


def skill_name_from_path(path: Path) -> str:
    """Return the skill directory name for one runtime SKILL.md."""
    return path.parent.name


def runtime_skill_path(root: Path, skill: str) -> Path:
    """Return the runtime SKILL.md path for one skill."""
    return root / RUNTIME_SKILL_ROOT / skill / "SKILL.md"


def canonical_skill_doc(root: Path, skill: str) -> Path:
    """Return the human-facing skill canon path for one skill."""
    return root / HUMAN_SKILL_ROOT / f"{skill}.md"


def repo_relative(root: Path, path: Path) -> str:
    """Return a POSIX relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def iter_command_lines(text: str) -> Iterable[str]:
    """Yield command-looking lines from Markdown text."""
    in_fence = False
    fence_lang = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            if in_fence:
                in_fence = False
                fence_lang = ""
            else:
                in_fence = True
                fence_lang = stripped.removeprefix("```").strip().lower()
            continue
        candidate = stripped
        if not candidate:
            continue
        if in_fence and fence_lang not in ("", "bash", "sh", "shell", "text"):
            continue
        if candidate.endswith("\\"):
            candidate = candidate[:-1].rstrip()
        if candidate.startswith("$ "):
            candidate = candidate[2:].strip()
        if is_command_candidate(candidate):
            yield candidate
        for inline in INLINE_CODE_RE.findall(raw_line):
            command = inline.strip()
            is_bare_tool_reference = command.startswith("tools/") and len(command.split()) == 1
            if is_command_candidate(command) and not is_bare_tool_reference:
                yield command


def is_command_candidate(value: str) -> bool:
    """Return whether a string is command-shaped enough for a packet."""
    if value.endswith("/"):
        return False
    tokens = value.split()
    token_index = 0
    while token_index < len(tokens):
        if not ASSIGNMENT_TOKEN_RE.fullmatch(tokens[token_index]):
            break
        token_index += 1
    if token_index >= len(tokens):
        return False
    normalized = " ".join(tokens[token_index:])
    return normalized.startswith(COMMAND_PREFIXES)


def unique_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    """Return unique strings in first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", value.strip())
        if "skill_tool_commands.py show" in normalized:
            continue
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def build_command_plan(logical_command: str, source_root: Path) -> CommandPlan:
    """Return a command execution plan with resolved cwd and argv."""
    normalized = shlex.join(shlex.split(logical_command)) if logical_command else ""
    resolved_root = str(source_root.resolve())
    source_root_as_path = source_root.resolve()
    raw_tokens = shlex.split(logical_command)
    token_index = 0
    env_assignments: dict[str, str] = {}
    while token_index < len(raw_tokens):
        token = raw_tokens[token_index]
        if ASSIGNMENT_TOKEN_RE.fullmatch(token):
            key, value = token.split("=", maxsplit=1)
            env_assignments[key] = value
            token_index += 1
            continue
        break
    tokens = raw_tokens[token_index:]
    resolved: list[str] = []
    skip_next_root = False

    for index, token in enumerate(tokens):
        if token == "--root" and index + 1 < len(tokens):
            resolved.append(token)
            if tokens[index + 1] == ".":
                resolved.append(resolved_root)
            else:
                resolved.append(tokens[index + 1])
            skip_next_root = True
            continue
        if skip_next_root:
            skip_next_root = False
            continue
        if token.startswith("--root=") and token.split("=", maxsplit=1)[1] == ".":
            resolved.append(f"--root={resolved_root}")
            continue
        if index == 0 and token in SCRIPT_INTERPRETERS:
            resolved.append(token)
            continue
        if index == 1 and tokens[0] in SCRIPT_INTERPRETERS:
            resolved.append(
                str((source_root_as_path / token).resolve())
                if token.startswith(SOURCE_ROOT_SCRIPT_PREFIXES)
                else token
            )
            continue
        if (
            index > 0
            and tokens[index - 1] == "exec"
            and token.startswith(SOURCE_ROOT_SCRIPT_PREFIXES)
        ):
            resolved.append(str((source_root_as_path / token).resolve()))
            continue
        if index == 0 and token.startswith(SOURCE_ROOT_COMMAND_PREFIXES):
            resolved.append(str((source_root_as_path / token).resolve()))
            continue
        resolved.append(token)

    return CommandPlan(
        logical_command=normalized,
        source_root=resolved_root,
        execution_cwd=resolved_root,
        execution_env=tuple((key, env_assignments[key]) for key in env_assignments),
        execution_argv=tuple(resolved),
    )


def packet_for_skill(root_resolution: RootResolution, skill: str) -> SkillCommandPacket:
    """Build one command packet from catalog-owned command phases."""
    source_root = root_resolution.source_root
    root = source_root
    runtime_path = runtime_skill_path(root, skill)
    canon_path = canonical_skill_doc(root, skill)
    spec = load_skill_tool_commands(root).get(skill)
    if spec is not None and spec.structured:
        required = spec.required
        conditional = spec.conditional
        maintenance = spec.maintenance
        conditional_for_resolution = conditional
    else:
        # Minimal fixture roots may still exercise the legacy readback route;
        # canonical AgentCanon entries always take the structured branch above.
        texts: list[str] = []
        for path in (runtime_path, canon_path):
            if path.is_file():
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
        conditional = unique_preserve_order(
            command for text in texts for command in iter_command_lines(text)
        )
        conditional_for_resolution = conditional or (FALLBACK_COMMAND,)
        required = load_skill_required_tool_commands(root).get(skill, ())
        maintenance = LEGACY_MAINTENANCE_COMMANDS
    parent_root = root_resolution.current_repository_root
    required = resolve_optional_agent_canon_make_aliases(required, parent_root)
    conditional = resolve_optional_agent_canon_make_aliases(conditional, parent_root)
    conditional_for_resolution = resolve_optional_agent_canon_make_aliases(
        conditional_for_resolution,
        parent_root,
    )
    maintenance = resolve_optional_agent_canon_make_aliases(maintenance, parent_root)
    resolved_required = tuple(
        build_command_plan(command, source_root) for command in required
    )
    resolved_conditional = tuple(
        build_command_plan(command, source_root)
        for command in conditional_for_resolution
    )
    resolved_maintenance = tuple(
        build_command_plan(command, source_root) for command in maintenance
    )
    related_skills = related_skills_for(root, skill)
    return SkillCommandPacket(
        skill=skill,
        runtime_skill=repo_relative(root, runtime_path),
        canonical_doc=repo_relative(root, canon_path),
        related_skills=related_skills,
        required_commands=required,
        discovered_commands=conditional,
        conditional_commands=conditional,
        maintenance_commands=maintenance,
        resolved_required_commands=tuple(
            (
                plan.logical_command,
                plan.source_root,
                plan.execution_cwd,
                plan.execution_env,
                plan.execution_argv,
            )
            for plan in resolved_required
        ),
        resolved_discovered_commands=tuple(
            (
                plan.logical_command,
                plan.source_root,
                plan.execution_cwd,
                plan.execution_env,
                plan.execution_argv,
            )
            for plan in resolved_conditional
        ),
        resolved_conditional_commands=tuple(
            (
                plan.logical_command,
                plan.source_root,
                plan.execution_cwd,
                plan.execution_env,
                plan.execution_argv,
            )
            for plan in resolved_conditional
        ),
        resolved_maintenance_commands=tuple(
            (
                plan.logical_command,
                plan.source_root,
                plan.execution_cwd,
                plan.execution_env,
                plan.execution_argv,
            )
            for plan in resolved_maintenance
        ),
        validation_commands=maintenance,
    )


def _resolved_executable_tokens(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Return executable path positions from one resolved argv."""
    candidates: list[str] = []
    if argv:
        if argv[0] in SCRIPT_INTERPRETERS and len(argv) > 1:
            candidates.append(argv[1])
        else:
            candidates.append(argv[0])
    candidates.extend(
        token
        for index, token in enumerate(argv)
        if index > 0 and argv[index - 1] == "exec"
    )
    return tuple(dict.fromkeys(candidates))


def validate_command_plan_executables(
    root_resolution: RootResolution,
    packet: SkillCommandPacket,
) -> None:
    """Validate every resolved script executable before report publication."""
    command_groups = (
        packet.resolved_required_commands,
        packet.resolved_conditional_commands,
        packet.resolved_maintenance_commands,
    )
    for group in command_groups:
        for _logical, _source, _cwd, _env, argv in group:
            if not argv:
                raise SourceRootFailure(
                    "agent_canon_command_preflight_invalid",
                    f"empty command for skill {packet.skill}",
                )
            for executable in _resolved_executable_tokens(argv):
                if not executable.startswith("/"):
                    continue
                declared = Path(executable)
                candidate = declared.resolve()
                if declared.is_symlink() or not candidate.is_file():
                    raise SourceRootFailure(
                        "agent_canon_command_preflight_missing",
                        f"command executable is missing: {executable}",
                    )
                try:
                    candidate.relative_to(root_resolution.source_root.resolve())
                except ValueError as exc:
                    raise SourceRootFailure(
                        "agent_canon_command_preflight_escape",
                        f"command executable escapes source root: {executable}",
                    ) from exc


def related_skills_for(root: Path, skill: str) -> tuple[str, ...]:
    """Return related skills from the public catalog when that catalog exists."""
    catalog_path = root / HUMAN_SKILL_ROOT / "catalog.yaml"
    if not catalog_path.is_file():
        return ()
    return load_skill_related_map(root).get(skill, ())


def skill_pair_text(root: Path, skill: str) -> str:
    """Return combined runtime and human-facing skill text."""
    parts: list[str] = []
    for path in (runtime_skill_path(root, skill), canonical_skill_doc(root, skill)):
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def check_issue_contract_rules(root: Path, skill: str) -> tuple[Finding, ...]:
    """Check issue-backed skill contract drift markers."""
    text = skill_pair_text(root, skill)
    if not text:
        return ()
    path = f"{RUNTIME_SKILL_ROOT.as_posix()}/{skill}/SKILL.md+{HUMAN_SKILL_ROOT.as_posix()}/{skill}.md"
    findings: list[Finding] = []
    for marker_name, marker in ISSUE_CONTRACT_MARKERS.get(skill, ()):
        if marker not in text:
            findings.append(Finding("skill_issue_contract", path, f"{marker_name}:missing"))
    for marker_name, pattern in ISSUE_CONTRACT_FORBIDDEN.get(skill, ()):
        if pattern.search(text):
            findings.append(Finding("skill_issue_contract", path, f"{marker_name}:present"))
    return tuple(findings)


def check(root: Path) -> tuple[Finding, ...]:
    """Check every runtime skill for the materializer-owned packet projection."""
    findings: list[Finding] = []
    paths = runtime_skill_paths(root)
    if not paths:
        findings.append(Finding("skill_tool_commands", RUNTIME_SKILL_ROOT.as_posix(), "missing-skill-root"))
    for path in paths:
        skill = skill_name_from_path(path)
        relative = repo_relative(root, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECTION_HEADING not in text:
            findings.append(Finding("skill_tool_commands", relative, "missing-tool-commands-section"))
        else:
            if SECTION_START not in text or SECTION_END not in text:
                findings.append(Finding("skill_tool_commands", relative, "missing-section-markers"))
            command = COMMAND_TEMPLATE.format(skill=skill)
            if text.count(command) != 1:
                findings.append(Finding("skill_tool_commands", relative, "missing-command-packet-entry"))
        findings.extend(check_issue_contract_rules(root, skill))
    return tuple(findings)


def render_packet_text(packet: SkillCommandPacket) -> str:
    """Render one skill command packet."""
    lines = [
        f"SKILL_TOOL_COMMANDS_SKILL={packet.skill}",
        f"SKILL_TOOL_COMMANDS_RUNTIME_SKILL={packet.runtime_skill}",
        f"SKILL_TOOL_COMMANDS_CANONICAL_DOC={packet.canonical_doc}",
        "SKILL_TOOL_COMMANDS_RELATED_SKILLS="
        + (
            ",".join(f"${skill}" for skill in packet.related_skills)
            if packet.related_skills
            else "-"
        ),
        "SKILL_TOOL_COMMANDS_REQUIRED:",
    ]
    lines.extend(f"- {command}" for command in packet.required_commands)
    lines.append("SKILL_TOOL_COMMANDS_REQUIRED_RESOLUTION:")
    for command, source_root, execution_cwd, env, argv in (
        packet.resolved_required_commands
    ):
        lines.extend(
            (
                f"- logical={command}",
                f"- source_root={source_root}",
                f"- execution_cwd={execution_cwd}",
                f"- execution_env={json.dumps(list(env))}",
                f"- execution_argv={json.dumps(list(argv))}",
            )
        )
    lines.append("SKILL_TOOL_COMMANDS_CONDITIONAL:")
    lines.extend(f"- {command}" for command in packet.conditional_commands)
    lines.append("SKILL_TOOL_COMMANDS_CONDITIONAL_RESOLUTION:")
    for command, source_root, execution_cwd, env, argv in (
        packet.resolved_discovered_commands
    ):
        lines.extend(
            (
                f"- logical={command}",
                f"- source_root={source_root}",
                f"- execution_cwd={execution_cwd}",
                f"- execution_env={json.dumps(list(env))}",
                f"- execution_argv={json.dumps(list(argv))}",
            )
        )
    lines.append("SKILL_TOOL_COMMANDS_MAINTENANCE_ONLY:")
    lines.append("- Run these only when editing skill command sections or checking skill-tool drift.")
    lines.extend(f"- {command}" for command in packet.maintenance_commands)
    return "\n".join(lines)


def render_public_projection_text(
    packet: SkillCommandPacket,
    root_resolution: RootResolution,
) -> str:
    """Render transient public argv projections without changing packet schema."""
    lines = [
        f"SKILL_TOOL_COMMANDS_PUBLIC_LAYOUT={root_resolution.layout}",
        "SKILL_TOOL_COMMANDS_PUBLIC_REQUIRED:",
    ]
    for command in packet.required_commands:
        projection = project_public_command(command, root_resolution)
        lines.extend(
            (
                f"- logical={projection.logical_command}",
                f"- public_cwd={projection.public_cwd}",
                f"- public_env={json.dumps(list(projection.public_env))}",
                f"- public_argv={json.dumps(list(projection.public_argv))}",
            )
        )
    lines.append("SKILL_TOOL_COMMANDS_PUBLIC_CONDITIONAL:")
    for command in packet.conditional_commands:
        projection = project_public_command(command, root_resolution)
        lines.extend(
            (
                f"- logical={projection.logical_command}",
                f"- public_cwd={projection.public_cwd}",
                f"- public_env={json.dumps(list(projection.public_env))}",
                f"- public_argv={json.dumps(list(projection.public_argv))}",
            )
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root_resolution = resolve_agent_canon_source_root(Path(args.root))
    except SourceRootFailure as exc:
        print(f"SKILL_TOOL_COMMANDS_SOURCE_ROOT_FAILURE={exc.code}:{exc.detail}")
        return 2

    root = root_resolution.source_root
    if args.command == "show":
        packet = packet_for_skill(root_resolution, args.skill)
        if args.format == "json":
            print(json.dumps(asdict(packet), indent=2, sort_keys=True))
        else:
            print(render_packet_text(packet))
            print(render_public_projection_text(packet, root_resolution))
        return 0
    findings = check(root)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "status": "pass" if not findings else "fail",
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in findings:
            print(finding.render())
        print(f"SKILL_TOOL_COMMANDS_FINDINGS={len(findings)}")
        print(f"SKILL_TOOL_COMMANDS={'pass' if not findings else 'fail'}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
