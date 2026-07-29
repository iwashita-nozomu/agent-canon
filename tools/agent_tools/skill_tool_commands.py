#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Maintains explicit tool-command entry sections in runtime skills.
# upstream design ../../agents/canonical/skills.md skill canon registry
# upstream design ../../agents/skills/task-routing.md deterministic skill routing contract
# upstream design ../../agents/skills/agent-orchestration.md tool-first skill execution contract
# upstream design ../../agents/skills/catalog.yaml public skill related-skill metadata
# upstream implementation ../../tools/agent_tools/route.py parses and validates the public skill catalog
# downstream implementation ../../.agents/skills/agent-orchestration/SKILL.md materialized runtime skill command entry example
# downstream implementation ../../tools/agent_tools/check_convention_compliance.py verifies command section wiring
# downstream implementation ../../tests/agent_tools/test_skill_tool_commands.py tests command extraction and sync
# @dependency-end
"""Maintain explicit tool-command packets for AgentCanon runtime skills."""

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
from route import load_skill_related_map, load_skill_required_tool_commands

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
COMMON_RESOLUTION_WORDING = (
    "論理コマンドは、実行前に AgentCanon source root を基準として解決します。"
    "各解決結果には `source_root`、`execution_cwd`、`execution_argv` を含め、"
    "fallback-only skill を含む script entry の script path は絶対 path にします。"
)
FORMAT_VALUES = ("text", "json")
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
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
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
            "remote-doc-template-path",
            "vendor/agent-canon/documents/agent-canon/agent-canon-github-remote.md",
        ),
        (
            "profile-doc-template-path",
            "vendor/agent-canon/documents/runtime/runtime-profiles-and-check-matrix.md",
        ),
    ),
    "tool-finding-report": (
        (
            "workflow-monitoring-run-local-path",
            "reports/agents/",
        ),
        (
            "workflow-monitoring-template-path",
            "agents/templates/workflow_monitoring.md",
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
    """Commands discovered for one runtime skill."""

    skill: str
    runtime_skill: str
    canonical_doc: str
    related_skills: tuple[str, ...]
    required_commands: tuple[str, ...]
    discovered_commands: tuple[str, ...]
    resolved_required_commands: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    resolved_discovered_commands: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    validation_commands: tuple[str, ...]


@dataclass(frozen=True)
class CommandPlan:
    """Typed execution plan for one packet command."""

    logical_command: str
    source_root: str
    execution_cwd: str
    execution_argv: tuple[str, ...]


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

    sync = subparsers.add_parser("sync", help="Synchronize every runtime skill section.")
    sync.add_argument("--format", choices=FORMAT_VALUES, default="text")
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
    return value.startswith(COMMAND_PREFIXES)


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
    resolved: list[str] = []
    skip_next_root = False

    for index, token in enumerate(raw_tokens):
        if token == "--root" and index + 1 < len(raw_tokens):
            resolved.append(token)
            if raw_tokens[index + 1] == ".":
                resolved.append(resolved_root)
            else:
                resolved.append(raw_tokens[index + 1])
            skip_next_root = True
            continue
        if skip_next_root:
            skip_next_root = False
            continue
        if token.startswith("--root=") and token.split("=", maxsplit=1)[1] == ".":
            resolved.append(f"--root={resolved_root}")
            continue
        if index == 0 and token in ("python3", "python"):
            resolved.append(token)
            continue
        if index == 1 and raw_tokens[0] in ("python3", "python"):
            resolved.append(
                str((source_root_as_path / token).resolve())
                if token.startswith((".", "tools/", "agents/", ".agents/", "tests/"))
                else token
            )
            continue
        if index == 0 and token == "bash":
            resolved.append(token)
            continue
        if index == 1 and raw_tokens[0] == "bash":
            resolved.append(
                str((source_root_as_path / token).resolve())
                if token.startswith((".", "tools/", "agents/", ".agents/", "tests/"))
                else token
            )
            continue
        if index == 0 and token.startswith(("./", "tools/", "agents/", ".agents/", "tests/")):
            resolved.append(str((source_root_as_path / token).resolve()))
            continue
        resolved.append(token)

    return CommandPlan(
        logical_command=normalized,
        source_root=resolved_root,
        execution_cwd=resolved_root,
        execution_argv=tuple(resolved),
    )


def packet_for_skill(root_resolution: RootResolution, skill: str) -> SkillCommandPacket:
    """Build one command packet from runtime and human-facing skill files."""
    source_root = root_resolution.source_root
    root = source_root
    runtime_path = runtime_skill_path(root, skill)
    canon_path = canonical_skill_doc(root, skill)
    texts: list[str] = []
    for path in (runtime_path, canon_path):
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    discovered = unique_preserve_order(
        command for text in texts for command in iter_command_lines(text)
    )
    required = load_skill_required_tool_commands(root).get(skill, ())
    resolved_required = tuple(
        build_command_plan(command, source_root) for command in required
    )
    conditional_commands = discovered or (FALLBACK_COMMAND,)
    resolved_discovered = tuple(
        build_command_plan(command, source_root)
        for command in conditional_commands
    )
    validation = (
        "python3 tools/agent_tools/check_skill_frontmatter.py --root .",
        "python3 tools/agent_tools/skill_tool_commands.py check",
    )
    related_skills = related_skills_for(root, skill)
    return SkillCommandPacket(
        skill=skill,
        runtime_skill=repo_relative(root, runtime_path),
        canonical_doc=repo_relative(root, canon_path),
        related_skills=related_skills,
        required_commands=required,
        discovered_commands=discovered,
        resolved_required_commands=tuple(
            (
                plan.logical_command,
                plan.source_root,
                plan.execution_cwd,
                plan.execution_argv,
            )
            for plan in resolved_required
        ),
        resolved_discovered_commands=tuple(
            (
                plan.logical_command,
                plan.source_root,
                plan.execution_cwd,
                plan.execution_argv,
            )
            for plan in resolved_discovered
        ),
        validation_commands=validation,
    )


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


def expected_section(skill: str) -> str:
    """Return the materialized Tool Commands section for one runtime skill."""
    command = COMMAND_TEMPLATE.format(skill=skill)
    return (
        f"{SECTION_HEADING}\n\n"
        f"{SECTION_START}\n"
        "この skill の workflow を適用する前に、次の command packet を使用してください。\n\n"
        "```bash\n"
        f"{command}\n"
        "```\n\n"
        f"{COMMON_RESOLUTION_WORDING}\n\n"
        "packet が出力した必須 command と、task に該当する conditional command を実行してください。\n"
        f"{SECTION_END}\n"
    )


def replace_or_insert_section(text: str, section: str) -> str:
    """Replace an existing Tool Commands section or insert one after the title."""
    marked_pattern = re.compile(
        rf"(?ms)^{re.escape(SECTION_HEADING)}\n\n"
        rf"{re.escape(SECTION_START)}\n.*?{re.escape(SECTION_END)}\n"
    )
    if marked_pattern.search(text):
        return marked_pattern.sub(section.rstrip() + "\n", text, count=1)
    legacy_pattern = re.compile(
        rf"(?ms)^{re.escape(SECTION_HEADING)}\n\n"
        r"Use the command packet before applying this skill's workflow:\n\n"
        r"```bash\n"
        r"python3 tools/agent_tools/skill_tool_commands\.py show --skill [A-Za-z0-9_-]+ --format text\n"
        r"```\n\n"
        r"Execute the required and task-matching conditional commands that the packet prints\.\n\n?"
    )
    if legacy_pattern.search(text):
        return legacy_pattern.sub(section.rstrip() + "\n\n", text, count=1)
    match = re.search(r"(?m)^# .+\n", text)
    if match:
        insert_at = match.end()
        return text[:insert_at] + "\n" + section + "\n" + text[insert_at:]
    return section + "\n" + text


def sync(root: Path) -> tuple[int, ...]:
    """Synchronize every runtime skill and return changed file indexes."""
    changed: list[int] = []
    for index, path in enumerate(runtime_skill_paths(root)):
        skill = skill_name_from_path(path)
        current = path.read_text(encoding="utf-8")
        updated = replace_or_insert_section(current, expected_section(skill))
        if updated != current:
            path.write_text(updated, encoding="utf-8")
            changed.append(index)
    return tuple(changed)


def check(root: Path) -> tuple[Finding, ...]:
    """Check every runtime skill for the materialized Tool Commands section."""
    findings: list[Finding] = []
    paths = runtime_skill_paths(root)
    if not paths:
        findings.append(Finding("skill_tool_commands", RUNTIME_SKILL_ROOT.as_posix(), "missing-skill-root"))
    for path in paths:
        skill = skill_name_from_path(path)
        relative = repo_relative(root, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        section = expected_section(skill)
        if SECTION_HEADING not in text:
            findings.append(Finding("skill_tool_commands", relative, "missing-tool-commands-section"))
            continue
        if SECTION_START not in text or SECTION_END not in text:
            findings.append(Finding("skill_tool_commands", relative, "missing-section-markers"))
        if COMMAND_TEMPLATE.format(skill=skill) not in text:
            findings.append(Finding("skill_tool_commands", relative, "missing-command-packet-entry"))
        if section not in text:
            findings.append(Finding("skill_tool_commands", relative, "stale-tool-commands-section"))
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
    for command, source_root, execution_cwd, argv in packet.resolved_required_commands:
        lines.extend(
            (
                f"- logical={command}",
                f"- source_root={source_root}",
                f"- execution_cwd={execution_cwd}",
                f"- execution_argv={json.dumps(list(argv))}",
            )
        )
    lines.append("SKILL_TOOL_COMMANDS_CONDITIONAL:")
    if packet.discovered_commands:
        lines.extend(f"- {command}" for command in packet.discovered_commands)
    else:
        lines.append(f"- {FALLBACK_COMMAND}")
    lines.append("SKILL_TOOL_COMMANDS_CONDITIONAL_RESOLUTION:")
    for command, source_root, execution_cwd, argv in packet.resolved_discovered_commands:
        lines.extend(
            (
                f"- logical={command}",
                f"- source_root={source_root}",
                f"- execution_cwd={execution_cwd}",
                f"- execution_argv={json.dumps(list(argv))}",
            )
        )
    lines.append("SKILL_TOOL_COMMANDS_MAINTENANCE_ONLY:")
    lines.append("- Run these only when editing skill command sections or checking skill-tool drift.")
    lines.extend(f"- {command}" for command in packet.validation_commands)
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
        return 0
    if args.command == "sync":
        changed = sync(root)
        findings = check(root)
        payload = {
            "status": "pass" if not findings else "fail",
            "changed_files": len(changed),
            "findings": [asdict(finding) for finding in findings],
        }
        if args.format == "json":
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"SKILL_TOOL_COMMANDS_SYNC_CHANGED={len(changed)}")
            for finding in findings:
                print(finding.render())
            print(f"SKILL_TOOL_COMMANDS_SYNC={'pass' if not findings else 'fail'}")
        return 0 if not findings else 1
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
