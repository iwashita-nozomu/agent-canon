#!/usr/bin/env python3
# @dependency-start
# responsibility Predicts tool and hook rejection gates before edits are handed to agents.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md defines handoff packet fields
# upstream implementation ./log_surface_inventory.py checks hook/tool/skill log-surface drift
# upstream implementation ../../.codex/hooks/oop_readability_guard.py blocks OOP readability failures
# upstream implementation ../../.codex/hooks/helper_inventory_guard.py blocks helper inventory findings
# downstream implementation ../../tools/agent_tools/agent_team.py injects preflight protocol into team manifests
# downstream implementation ../../tests/agent_tools/test_tool_rejection_preflight.py validates predicted gate routing
# @dependency-end
"""Predict edit-time tool/hook rejection gates from planned paths."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
TEXT_SUFFIXES = {
    ".bash",
    ".cfg",
    ".css",
    ".h",
    ".hpp",
    ".html",
    ".c",
    ".cc",
    ".cpp",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".zsh",
}
LOG_SURFACE_PREFIXES = (
    ".codex/hooks/",
    ".agents/skills/",
    ".claude/skills/",
    "agents/skills/",
    "tools/",
)
GITHUB_SURFACE_PREFIXES = (".github/workflows/", ".github/actions/")


@dataclass(frozen=True, order=True)
class PredictedGate:
    """One likely rejection gate for a planned edit."""

    path: str
    gate: str
    command: str
    handoff: str


@dataclass(frozen=True)
class GateTemplate:
    """Reusable gate template with path interpolation."""

    gate: str
    command_template: str
    handoff: str

    def for_path(self, path: str) -> PredictedGate:
        """Materialize this gate for one planned path."""
        return PredictedGate(
            path=path,
            gate=self.gate,
            command=self.command_template.format(path=path),
            handoff=self.handoff,
        )


PYTHON_GATE_TEMPLATES = (
    GateTemplate(
        gate="oop_readability_guard",
        command_template=(
            "python3 tools/oop/python/readability.py --root . --min-score 95 {path}"
        ),
        handoff=(
            "include OOP readability risk and repair plan before implementation edits"
        ),
    ),
    GateTemplate(
        gate="helper_inventory_guard",
        command_template=(
            "python3 tools/agent_tools/helper_function_inventory.py "
            "--root . --changed --baseline-ref HEAD"
        ),
        handoff=(
            "avoid ad hoc helper creation or state why existing helper surfaces "
            "cannot be reused"
        ),
    ),
)
CPP_GATE_TEMPLATES = (
    GateTemplate(
        gate="oop_readability_guard",
        command_template=(
            "python3 tools/oop/cpp/readability.py --root . --min-score 95 {path}"
        ),
        handoff="include C/C++ OOP readability risk before edits",
    ),
)
DEPENDENCY_GATE_TEMPLATES = (
    GateTemplate(
        gate="dependency_review",
        command_template=(
            "bash tools/agent_tools/run_repo_dependency_review.sh "
            "--root . --fail-missing --list-changed-dependencies"
        ),
        handoff=(
            "include dependency header and related edit-scope plan for created "
            "or edited text files"
        ),
    ),
)
LOG_SURFACE_GATE_TEMPLATES = (
    GateTemplate(
        gate="log_surface_inventory_guard",
        command_template=(
            "python3 tools/agent_tools/log_surface_inventory.py --root . "
            "--check --baseline documents/log-surface-inventory.json"
        ),
        handoff=(
            "state whether emitted hook/tool/skill fields changed and regenerate "
            "the inventory baseline in the same branch"
        ),
    ),
)
GITHUB_GATE_TEMPLATES = (
    GateTemplate(
        gate="github_workflow_check",
        command_template="python3 tools/ci/check_github_workflows.py",
        handoff="include workflow checkout, permissions, and artifact evidence",
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Predict tool/hook rejection gates that should be run or explained "
            "before a write-capable subagent edits planned paths."
        )
    )
    parser.add_argument("paths", nargs="*", help="Planned edit paths.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Use git changed paths when explicit paths are not supplied.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser


def changed_paths(root: Path) -> tuple[str, ...]:
    """Return changed tracked and untracked paths."""
    commands = (
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACMRT", "HEAD"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for command in commands:
        paths.update(git_output_lines(command))
    return tuple(sorted(paths))


def git_output_lines(command: list[str]) -> tuple[str, ...]:
    """Return output lines for one read-only git command."""
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line)


def planned_paths(root: Path, raw_paths: list[str], *, use_changed: bool) -> tuple[str, ...]:
    """Resolve planned paths relative to the workspace root."""
    if raw_paths:
        return tuple(dict.fromkeys(normalize_path(root, path) for path in raw_paths))
    if use_changed:
        return changed_paths(root)
    return ()


def normalize_path(root: Path, raw_path: str) -> str:
    """Return one path relative to root when possible."""
    candidate = (root / raw_path).resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return raw_path


def predict_gates(paths: tuple[str, ...]) -> tuple[PredictedGate, ...]:
    """Predict rejection gates for planned paths."""
    gates: set[PredictedGate] = set()
    for path in paths:
        gates.update(path_gates(path))
    return tuple(sorted(gates))


def path_gates(path: str) -> tuple[PredictedGate, ...]:
    """Return predicted gates for one path."""
    suffix = Path(path).suffix
    templates: list[GateTemplate] = []
    if suffix in PYTHON_SUFFIXES:
        templates.extend(PYTHON_GATE_TEMPLATES)
    if suffix in CPP_SUFFIXES:
        templates.extend(CPP_GATE_TEMPLATES)
    if suffix in TEXT_SUFFIXES:
        templates.extend(DEPENDENCY_GATE_TEMPLATES)
    if path.startswith(LOG_SURFACE_PREFIXES):
        templates.extend(LOG_SURFACE_GATE_TEMPLATES)
    if path.startswith(GITHUB_SURFACE_PREFIXES):
        templates.extend(GITHUB_GATE_TEMPLATES)
    return tuple(template.for_path(path) for template in templates)


def text_output(gates: tuple[PredictedGate, ...]) -> str:
    """Render stable text output."""
    status = "warn" if gates else "pass"
    lines = [
        f"TOOL_REJECTION_PREFLIGHT={status}",
        f"TOOL_REJECTION_PREDICTED_GATES={len(gates)}",
    ]
    for gate in gates:
        lines.append(
            "TOOL_REJECTION_PREDICTED_GATE="
            f"path:{gate.path}\tgate:{gate.gate}\tcommand:{gate.command}\thandoff:{gate.handoff}"
        )
    return "\n".join(lines)


def json_output(gates: tuple[PredictedGate, ...]) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "warn" if gates else "pass",
            "predicted_gate_count": len(gates),
            "predicted_gates": [asdict(gate) for gate in gates],
        },
        indent=2,
        sort_keys=True,
    )


def main() -> int:
    """Run the preflight CLI."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    paths = planned_paths(root, list(args.paths), use_changed=args.changed)
    gates = predict_gates(paths)
    if args.format == "json":
        print(json_output(gates))
    else:
        print(text_output(gates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
