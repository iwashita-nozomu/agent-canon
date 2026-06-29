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
import os
import re
import subprocess
import sys
from collections import defaultdict
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
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Run only the named target. May be repeated.",
    )
    parser.add_argument(
        "--target-name-regex",
        help="Run only targets whose name matches this regular expression.",
    )
    parser.add_argument(
        "--max-targets",
        type=int,
        help="Cap the number of selected targets after filtering.",
    )
    parser.add_argument(
        "--tactic-matrix",
        help=(
            "Comma-separated tactics to try for each selected target, for example "
            "'exact?,simp?,aesop?,grind'. Matrix mode runs each target/tactic "
            "pair separately and succeeds when every selected target has at "
            "least one verified tactic."
        ),
    )
    parser.add_argument(
        "--attempt-timeout-sec",
        type=float,
        help="Optional per target/tactic timeout in seconds.",
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
    *,
    timeout_sec: float | None = None,
) -> TargetResult:
    """Run Lean for one target."""
    tactic = str(target.get("tactic", "aesop?"))
    cwd_value = config.get("cwd")
    cwd = Path(str(cwd_value)) if cwd_value else config_path.parent
    raw_command = config.get("command")
    command = string_list(raw_command) or ["lake", "env", "lean", "--stdin"]
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            input=lean_script(config, target, tactic),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        partial_output = "\n".join(
            part
            for part in (
                exc.stdout if isinstance(exc.stdout, str) else "",
                exc.stderr if isinstance(exc.stderr, str) else "",
            )
            if part
        )
        return TargetResult(
            name=str(target["name"]),
            role=str(target.get("role", "proof")),
            status="timeout",
            returncode=124,
            tactic=tactic,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            suggested_proof=extract_suggestion(partial_output),
            unresolved_goals=tuple(extract_unresolved_goals(partial_output)),
            next_targets=tuple(string_list(target.get("next_targets"))),
        )
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    suggested = extract_suggestion(output)
    unresolved = extract_unresolved_goals(output)
    uses_sorry = output_uses_sorry(output)
    if proc.returncode == 0 and not uses_sorry:
        status = "verified"
    elif uses_sorry:
        status = (
            "partial_proof_with_sorry"
            if unresolved
            else "partial_proof_with_sorry_no_structured_goals"
        )
    else:
        status = (
            "unverified_with_next_goals"
            if unresolved
            else "failed_no_structured_goals"
        )
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


def output_uses_sorry(output: str) -> bool:
    """Return whether Lean accepted a script only by using ``sorry``.

    Tactics such as ``apply?`` can print partial proof scripts containing
    ``sorry`` while Lean exits successfully because examples allow sorry by
    default.  That output is useful proof-search guidance, but it is not a
    verified proof.
    """
    markers = (
        "warning: declaration uses `sorry`",
        "warning: declaration uses 'sorry'",
        "declaration uses `sorry`",
        "declaration uses 'sorry'",
    )
    return any(marker in output for marker in markers)


def extract_remaining_subgoal_blocks(output: str) -> list[str]:
    """Extract partial-proof remaining subgoals from tactic suggestions."""
    blocks: list[str] = []
    marker = "-- Remaining subgoals:"
    for part in output.split(marker)[1:]:
        lines: list[str] = []
        for raw_line in part.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if stripped.startswith("Try this:"):
                break
            if stripped.startswith("found a partial proof"):
                break
            if stripped.startswith("<stdin>:"):
                break
            if stripped.startswith("[apply]"):
                break
            if not line:
                if lines:
                    break
                continue
            lines.append(line.removeprefix("  -- ").strip())
        if lines:
            blocks.append("\n".join(lines)[:3000])
    return blocks


def extract_unresolved_goals(output: str) -> list[str]:
    """Extract compact unresolved-goal snippets from Lean output."""
    goals: list[str] = []
    goals.extend(extract_remaining_subgoal_blocks(output))
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
    deduped: list[str] = []
    seen: set[str] = set()
    for goal in goals:
        normalized = "\n".join(line.rstrip() for line in goal.strip().splitlines())
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(goal)
    return deduped


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


def filtered_targets(
    targets: list[dict[str, object]],
    *,
    names: list[str],
    name_regex: str | None,
    max_targets: int | None,
) -> list[dict[str, object]]:
    """Return targets selected by CLI filters."""
    selected = targets
    if names:
        wanted = set(names)
        selected = [target for target in selected if str(target.get("name")) in wanted]
    if name_regex:
        pattern = re.compile(name_regex)
        selected = [
            target
            for target in selected
            if pattern.search(str(target.get("name", "")))
        ]
    if max_targets is not None:
        selected = selected[:max_targets]
    return selected


def tactic_list(value: str | None) -> list[str]:
    """Parse a comma-separated tactic matrix."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def with_tactic(target: dict[str, object], tactic: str) -> dict[str, object]:
    """Return a target copy with a temporary tactic."""
    clone = dict(target)
    clone["tactic"] = tactic
    return clone


def run_tactic_matrix(
    config_path: Path,
    config: dict[str, object],
    targets: list[dict[str, object]],
    tactics: list[str],
    *,
    timeout_sec: float | None = None,
) -> list[TargetResult]:
    """Run each target against every tactic in the matrix."""
    results: list[TargetResult] = []
    for target in targets:
        for tactic in tactics:
            results.append(
                run_lean(
                    config_path,
                    config,
                    with_tactic(target, tactic),
                    timeout_sec=timeout_sec,
                )
            )
    return results


def matrix_groups(results: list[TargetResult]) -> dict[str, list[TargetResult]]:
    """Group matrix attempts by target name."""
    grouped: dict[str, list[TargetResult]] = defaultdict(list)
    for result in results:
        grouped[result.name].append(result)
    return dict(grouped)


def matrix_target_statuses(results: list[TargetResult]) -> dict[str, str]:
    """Summarize whether each target has any successful tactic."""
    statuses: dict[str, str] = {}
    for name, group in matrix_groups(results).items():
        statuses[name] = (
            "verified_by_some_tactic"
            if any(result.status == "verified" for result in group)
            else "unverified_by_all_tactics"
        )
    return statuses


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


def dependency_path_from_output(output_path: str | None) -> str:
    """Return this tool path relative to the rendered output file."""
    if output_path is None:
        return Path(__file__).resolve().as_posix()
    return Path(
        os.path.relpath(
            Path(__file__).resolve(),
            Path(output_path).resolve().parent,
        )
    ).as_posix()


def render_markdown(
    results: list[TargetResult],
    config: dict[str, object],
    *,
    dependency_path: str,
) -> str:
    """Render Markdown report."""
    grouped = matrix_groups(results)
    matrix_mode = any(len(group) > 1 for group in grouped.values())
    lines = [
        "<!--",
        "@dependency-start",
        "responsibility Records recursive Lean proof-search results for a configured theorem target.",
        f"upstream implementation {dependency_path} generates this report from the configured Lean target file.",
        "downstream design check_finite_stop_goal.py consumes target status rows and unresolved goals.",
        "@dependency-end",
        "-->",
        "",
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
    if matrix_mode:
        lines.extend(["", "## Tactic Matrix Summary", ""])
        lines.extend(["| Target | Matrix Status | Verified Tactics |", "| --- | --- | --- |"])
        for name, group in sorted(grouped.items()):
            verified = [result.tactic for result in group if result.status == "verified"]
            status = (
                "verified_by_some_tactic"
                if verified
                else "unverified_by_all_tactics"
            )
            lines.append(
                f"| `{name}` | `{status}` | `{', '.join(verified) or 'none'}` |"
            )
    for result in results:
        if not result.unresolved_goals:
            continue
        lines.extend(["", f"## `{result.name}` / `{result.tactic}` Unresolved Goals", ""])
        for index, goal in enumerate(result.unresolved_goals, start=1):
            lines.extend([f"### Goal {index}", "", "```text", goal, "```"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run CLI."""
    args = build_parser().parse_args(argv)
    config_path = Path(args.config)
    config = load_config(config_path)
    targets = filtered_targets(
        dict_list(config.get("targets")),
        names=args.target,
        name_regex=args.target_name_regex,
        max_targets=args.max_targets,
    )
    tactics = tactic_list(args.tactic_matrix)
    if tactics:
        results = run_tactic_matrix(
            config_path,
            config,
            targets,
            tactics,
            timeout_sec=args.attempt_timeout_sec,
        )
    elif args.batch:
        results = run_lean_batch(config_path, config, targets)
    else:
        results = [
            run_lean(
                config_path,
                config,
                target,
                timeout_sec=args.attempt_timeout_sec,
            )
            for target in targets
        ]
    if args.format == "json":
        rendered = json.dumps(
            {
                "status": "lean_recursive_proof_search_complete",
                "target_theorem": config.get("target_theorem", ""),
                "matrix_target_statuses": matrix_target_statuses(results)
                if tactics
                else {},
                "results": [asdict(result) for result in results],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    elif args.format == "markdown":
        rendered = render_markdown(
            results,
            config,
            dependency_path=dependency_path_from_output(args.out),
        )
    else:
        rendered = render_text(results)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    if tactics:
        return 0 if all(
            status == "verified_by_some_tactic"
            for status in matrix_target_statuses(results).values()
        ) else 1
    return 0 if all(result.returncode == 0 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
