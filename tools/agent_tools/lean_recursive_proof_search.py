#!/usr/bin/env python3
"""Run recursive Lean proof-search targets and record unresolved goals.

@dependency-start
contract tool
responsibility Runs target-driven Lean tactic attempts from a JSON proof-search plan.
upstream design ../../agents/skills/formal-proof-workflow.md defines recursive target-driven proof search.
downstream design ../../documents/tools/lean_recursive_proof_search.md documents CLI usage.
@dependency-end
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class TargetResult:
    """One Lean target attempt result."""

    name: str
    role: str
    status: str
    returncode: int
    tactic: str
    stdout: str
    stderr: str
    suggested_proof: str
    unresolved_goals: tuple[str, ...]
    next_targets: tuple[str, ...]


@dataclass(frozen=True)
class TargetScript:
    """One target rendered into a Lean example."""

    target: dict[str, object]
    tactic: str
    script: str


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Proof-search target JSON.")
    parser.add_argument("--format", choices=("json", "markdown", "text"), default="text")
    parser.add_argument("--out")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run all targets in one Lean stdin process. Faster, but reports less per-target failure detail.",
    )
    return parser


def load_config(path: Path) -> dict[str, object]:
    """Load JSON config."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config must be a JSON object")
    return cast(dict[str, object], payload)


def string_list(value: object) -> list[str]:
    """Return string values from a JSON list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast(list[object], value)]


def dict_list(value: object) -> list[dict[str, object]]:
    """Return JSON object rows from a JSON list."""
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], item) for item in cast(list[object], value) if isinstance(item, dict)]


def lean_script(config: dict[str, object], target: dict[str, object], tactic: str) -> str:
    """Build a Lean stdin script for one target."""
    imports = "\n".join(f"import {item}" for item in string_list(config.get("imports")))
    opens = "\n".join(f"open {item}" for item in string_list(config.get("opens")))
    options = "\n".join(string_list(config.get("options")))
    prelude = str(config.get("prelude", ""))
    binders = str(target.get("binders", "")).strip()
    statement = str(target["statement"]).strip()
    setup = str(target.get("setup", "")).strip()
    body_lines: list[str] = []
    if setup:
        body_lines.append(setup)
    body_lines.append(tactic)
    body = "\n  ".join(body_lines)
    return f"""{imports}

{opens}

{options}

{prelude}

noncomputable section

example
    {binders} :
    {statement} := by
  {body}
"""


def lean_header(config: dict[str, object]) -> str:
    """Build the common Lean stdin header."""
    imports = "\n".join(f"import {item}" for item in string_list(config.get("imports")))
    opens = "\n".join(f"open {item}" for item in string_list(config.get("opens")))
    options = "\n".join(string_list(config.get("options")))
    prelude = str(config.get("prelude", ""))
    return f"""{imports}

{opens}

{options}

{prelude}

noncomputable section
"""


def lean_example_script(target: dict[str, object], tactic: str, index: int | None = None) -> str:
    """Build only the Lean example for one target."""
    binders = str(target.get("binders", "")).strip()
    statement = str(target["statement"]).strip()
    setup = str(target.get("setup", "")).strip()
    body_lines: list[str] = []
    if setup:
        body_lines.append(setup)
    body_lines.append(tactic)
    body = "\n  ".join(body_lines)
    marker = ""
    if index is not None:
        marker = f"/-- proof-search-target:{index}:{target['name']} -/\n"
    return f"""{marker}example
    {binders} :
    {statement} := by
  {body}
"""


def target_script(target: dict[str, object], index: int) -> TargetScript:
    """Render one target to a Lean example script."""
    tactic = str(target.get("tactic", "aesop?"))
    return TargetScript(
        target=target,
        tactic=tactic,
        script=lean_example_script(target, tactic, index=index),
    )


def run_lean(
    config_path: Path,
    config: dict[str, object],
    target: dict[str, object],
) -> TargetResult:
    """Run Lean for one target."""
    tactic = str(target.get("tactic", "aesop?"))
    cwd_value = config.get("cwd")
    cwd = Path(str(cwd_value)) if cwd_value else config_path.parent
    raw_command = config.get("command")
    command = string_list(raw_command) or ["lake", "env", "lean", "--stdin"]
    proc = subprocess.run(
        command,
        cwd=cwd,
        input=lean_script(config, target, tactic),
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    suggested = extract_suggestion(output)
    unresolved = extract_unresolved_goals(output)
    if proc.returncode == 0:
        status = "verified"
    elif unresolved:
        status = "unverified_with_next_goals"
    else:
        status = "failed_no_structured_goals"
    return TargetResult(
        name=str(target["name"]),
        role=str(target.get("role", "proof")),
        status=status,
        returncode=proc.returncode,
        tactic=tactic,
        stdout=proc.stdout,
        stderr=proc.stderr,
        suggested_proof=suggested,
        unresolved_goals=tuple(unresolved),
        next_targets=tuple(string_list(target.get("next_targets"))),
    )


def extract_suggestion(output: str) -> str:
    """Extract Lean's `Try this` suggestion when present."""
    marker = "Try this:"
    if marker not in output:
        return ""
    tail = output.split(marker, 1)[1]
    if "error:" in tail:
        return tail.split("error:", 1)[0].strip()
    return tail.strip()


def extract_unresolved_goals(output: str) -> list[str]:
    """Extract compact unresolved-goal snippets from Lean output."""
    goals: list[str] = []
    chunks = output.split("unsolved goals")
    for chunk in chunks[1:]:
        snippet = chunk.strip()
        if not snippet:
            continue
        goals.append(snippet[:3000])
    if "Initial goal:" in output:
        goals.append(output.split("Initial goal:", 1)[1].strip()[:3000])
    if not goals and output.strip():
        goals.append(output.strip()[:3000])
    return goals


def run_lean_batch(
    config_path: Path,
    config: dict[str, object],
    targets: list[dict[str, object]],
) -> list[TargetResult]:
    """Run all targets in one Lean process."""
    cwd_value = config.get("cwd")
    cwd = Path(str(cwd_value)) if cwd_value else config_path.parent
    raw_command = config.get("command")
    command = string_list(raw_command) or ["lake", "env", "lean", "--stdin"]
    scripts = [target_script(target, index) for index, target in enumerate(targets)]
    proc = subprocess.run(
        command,
        cwd=cwd,
        input=lean_header(config) + "\n\n".join(script.script for script in scripts),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return [
            TargetResult(
                name=str(script.target["name"]),
                role=str(script.target.get("role", "proof")),
                status="verified",
                returncode=0,
                tactic=script.tactic,
                stdout="",
                stderr="",
                suggested_proof="",
                unresolved_goals=(),
                next_targets=tuple(string_list(script.target.get("next_targets"))),
            )
            for script in scripts
        ]
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    return [
        TargetResult(
            name="_batch",
            role="proof",
            status="failed_no_structured_goals",
            returncode=proc.returncode,
            tactic="batch",
            stdout=proc.stdout,
            stderr=proc.stderr,
            suggested_proof=extract_suggestion(output),
            unresolved_goals=tuple(extract_unresolved_goals(output)),
            next_targets=(),
        )
    ]


def render_text(results: list[TargetResult]) -> str:
    """Render stable text."""
    lines = [f"LEAN_RECURSIVE_PROOF_TARGETS={len(results)}"]
    for result in results:
        status = result.status if result.role == "proof" else f"{result.status}:{result.role}"
        lines.append(
            "LEAN_RECURSIVE_PROOF_TARGET="
            f"{result.name}:{status}:next={','.join(result.next_targets) or 'none'}"
        )
    return "\n".join(lines) + "\n"


def render_markdown(results: list[TargetResult], config: dict[str, object]) -> str:
    """Render Markdown report."""
    lines = [
        "# Recursive Lean Proof Search",
        "",
        f"- target theorem: `{config.get('target_theorem', 'unspecified')}`",
        f"- targets: `{len(results)}`",
        "",
        "| Target | Status | Next Targets | Suggested Proof |",
        "| --- | --- | --- | --- |",
    ]
    for result in results:
        suggestion = result.suggested_proof.replace("|", "\\|").replace("\n", "<br>")
        status = result.status if result.role == "proof" else f"{result.status}:{result.role}"
        lines.append(
            f"| `{result.name}` | `{status}` | "
            f"`{', '.join(result.next_targets) or 'none'}` | {suggestion or '`none`'} |"
        )
    for result in results:
        if not result.unresolved_goals:
            continue
        lines.extend(["", f"## `{result.name}` Unresolved Goals", ""])
        for index, goal in enumerate(result.unresolved_goals, start=1):
            lines.extend([f"### Goal {index}", "", "```text", goal, "```"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run CLI."""
    args = build_parser().parse_args(argv)
    config_path = Path(args.config)
    config = load_config(config_path)
    targets = dict_list(config.get("targets"))
    if args.batch:
        results = run_lean_batch(config_path, config, targets)
    else:
        results = [run_lean(config_path, config, target) for target in targets]
    if args.format == "json":
        rendered = json.dumps(
            {
                "status": "lean_recursive_proof_search_complete",
                "target_theorem": config.get("target_theorem", ""),
                "results": [asdict(result) for result in results],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    elif args.format == "markdown":
        rendered = render_markdown(results, config)
    else:
        rendered = render_text(results)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if all(result.returncode == 0 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
