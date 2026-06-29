#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs goal.md-driven repository improvement loops to completion.
# upstream design ../../goal.md top-level goal contract
# upstream design ../../agents/workflows/adaptive-improvement-workflow.md loop rules  # noqa: E501
# downstream implementation ../../tests/agent_tools/test_goal_loop.py tests this  # noqa: E501
# @dependency-end
"""Run a top-level goal.md loop until the goal contract is achieved."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

FIELD_RE = re.compile(r"^\s*-\s*([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*?)\s*$")
CHECKBOX_RE = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX])\]\s*"
    r"(?P<id>[A-Za-z0-9_.-]+):\s*(?P<text>.*)$"
)
HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
DEFAULT_MAX_PLAN_ITEMS = 12
PR_MUTATION_AUTHORITY_VALUES = (
    "inspect_and_prepare_only",
    "ready_for_review_when_green",
    "merge_when_green",
    "github_pr_automation_when_green",
)
DEFAULT_EXIT_CRITERIA = (
    (
        "G1",
        "Repository dependency review passes with "
        "`bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.",
    ),
    (
        "G2",
        "Code dependency extraction is reviewed with "
        "`bash tools/agent_tools/scan_code_dependencies.sh` for the affected surface.",
    ),
    (
        "G3",
        "OOP/readability analysis is run with "
        "`python3 tools/oop/python/readability.py` and, when C++ is in scope, "
        "`python3 tools/oop/cpp/readability.py`; findings are fixed or documented.",
    ),
    (
        "G4",
        "Hardcoded numeric literal analysis is run with "
        "`python3 tools/agent_tools/check_hardcoded_numbers.py` and findings are "
        "fixed or locally justified.",
    ),
    (
        "G5",
        "Repo-wide static analysis or CI passes with `make ci`, or the "
        "documented static-analysis route `python3 -m pyright` plus "
        "`python3 -m ruff check python tests --select D,E,F,I,UP --ignore E501`.",
    ),
    ("G6", "Objective-specific completion evidence is recorded."),
)
DEFAULT_BACKLOG = (
    (
        "B1",
        "Build the prompt-to-artifact checklist that maps objective clauses to "
        "files, commands, gates, and completion evidence.",
    ),
    (
        "B2",
        "Survey existing docs, tools, tests, and reusable surfaces before adding "
        "or deleting anything; list reuse, consolidation, and deletion candidates.",
    ),
    (
        "B3",
        "Execute one cohesive implementation slice that advances the selected "
        "related surfaces together instead of stopping after one isolated edit.",
    ),
    (
        "B4",
        "Run dependency review, code dependency scan, OOP/readability, hardcoded "
        "numeric literal analysis, and task-relevant prompt/doc/convention checks; "
        "fix any failure in the same iteration.",
    ),
    (
        "B5",
        "Refresh the goal work breakdown, close completed backlog items with evidence, "
        "and continue immediately if NEXT_ACTION still reports run_next_iteration.",
    ),
)
OPTIONAL_GOAL_ITEMS = (
    (
        "O1",
        "research",
        "External web research is required, with source links and current-date "
        "verification recorded in the run bundle.",
    ),
    (
        "O2",
        "benchmark",
        "Benchmark or experiment evidence is required, with reproducible "
        "commands, seeds, environment, and comparison artifacts.",
    ),
    (
        "O3",
        "docs",
        "Long-form documentation, slide, or user-guide review is required before "
        "closeout.",
    ),
    (
        "O4",
        "release",
        "Release, branch-integration, push, or downstream template submodule pin "
        "coordination is required.",
    ),
    (
        "O5",
        "subagents",
        "Explicit read-only specialist review or implementation handoff is "
        "required for the goal.",
    ),
)


@dataclass(frozen=True)
class CheckboxItem:
    """One goal checkbox item."""

    item_id: str
    text: str
    checked: bool
    line_number: int


@dataclass(frozen=True)
class GoalState:
    """Parsed goal.md state."""

    path: Path
    fields: dict[str, str]
    exit_criteria: tuple[CheckboxItem, ...]
    backlog: tuple[CheckboxItem, ...]
    optional_goal_items: tuple[CheckboxItem, ...]
    parse_errors: tuple[str, ...]

    @property
    def goal_status(self) -> str:
        """Return the explicit goal_status field."""
        return self.fields.get("goal_status", "active").strip().lower()

    @property
    def current_iteration(self) -> int:
        """Return current_iteration as an integer."""
        return int_field(self.fields, "current_iteration", 0)

    @property
    def run_safety_cap(self) -> int:
        """Return the optional per-run safety cap."""
        return int_field(self.fields, "run_safety_cap", 0)

    @property
    def pr_mutation_authority(self) -> str:
        """Return the PR mutation authority declared by the goal."""
        return self.fields.get(
            "pr_mutation_authority",
            "inspect_and_prepare_only",
        ).strip()

    @property
    def done_exit_criteria(self) -> int:
        """Return the number of checked exit criteria."""
        return sum(1 for item in self.exit_criteria if item.checked)

    @property
    def done_backlog_items(self) -> int:
        """Return the number of checked backlog items."""
        return sum(1 for item in self.backlog if item.checked)

    @property
    def done_optional_goal_items(self) -> int:
        """Return the number of checked optional catalog items."""
        return sum(1 for item in self.optional_goal_items if item.checked)

    @property
    def achieved(self) -> bool:
        """Return true when explicit status and all exit criteria are complete."""
        return (
            self.goal_status == "achieved"
            and bool(self.exit_criteria)
            and self.done_exit_criteria == len(self.exit_criteria)
            and self.done_backlog_items == len(self.backlog)
            and not self.parse_errors
        )

    @property
    def loop_status(self) -> str:
        """Return machine loop status."""
        if self.parse_errors:
            return "invalid"
        if self.achieved:
            return "achieved"
        if self.goal_status in {"blocked", "stopped"}:
            return self.goal_status
        return "continue"


def int_field(fields: dict[str, str], key: str, default: int) -> int:
    """Parse an integer field with a default."""
    try:
        return int(fields.get(key, str(default)).strip())
    except ValueError:
        return default


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Run or inspect a goal.md loop.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a goal.md file.")
    init_parser.add_argument("--goal-file", default="goal.md")
    init_parser.add_argument("--objective", required=True)
    init_parser.add_argument("--max-iterations", type=int, default=0)
    init_parser.add_argument(
        "--pr-mutation-authority",
        choices=PR_MUTATION_AUTHORITY_VALUES,
        default="inspect_and_prepare_only",
        help="PR mutation authority mode recorded in goal.md.",
    )
    init_parser.add_argument("--force", action="store_true")

    status_parser = subparsers.add_parser("status", help="Print goal loop status.")
    add_common_goal_args(status_parser)
    status_parser.add_argument("--require-achieved", action="store_true")

    plan_parser = subparsers.add_parser(
        "plan",
        help="Render unchecked goal items as concrete work units.",
    )
    add_common_goal_args(plan_parser)
    plan_parser.add_argument(
        "--max-items",
        type=int,
        default=DEFAULT_MAX_PLAN_ITEMS,
        help="Maximum unchecked exit/backlog items to render.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run a command until goal.md is achieved.",
    )
    add_common_goal_args(run_parser)
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        help="Optional run-local safety cap for this invocation only.",
    )
    run_parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="Command to run after --.",
    )

    mark_parser = subparsers.add_parser("mark", help="Check or uncheck one goal item.")
    mark_parser.add_argument("--goal-file", default="goal.md")
    target = mark_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--criterion")
    target.add_argument("--backlog")
    state = mark_parser.add_mutually_exclusive_group(required=True)
    state.add_argument("--done", action="store_true")
    state.add_argument("--open", action="store_true")
    mark_parser.add_argument(
        "--goal-status",
        choices=("active", "achieved", "blocked", "stopped"),
        help="Optionally update the goal_status field.",
    )
    mark_parser.add_argument(
        "--pr-mutation-authority",
        choices=PR_MUTATION_AUTHORITY_VALUES,
        help="Optionally update the goal PR mutation authority field.",
    )
    return parser


def add_common_goal_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by status and run."""
    parser.add_argument("--goal-file", default="goal.md")
    parser.add_argument("--report-out", help="Optional Markdown status report path.")


def parse_goal(path: Path) -> GoalState:
    """Parse goal.md into a machine state."""
    if not path.is_file():
        return GoalState(
            path=path,
            fields={},
            exit_criteria=(),
            backlog=(),
            optional_goal_items=(),
            parse_errors=(f"missing goal file: {path}",),
        )
    fields: dict[str, str] = {}
    exit_criteria: list[CheckboxItem] = []
    backlog: list[CheckboxItem] = []
    optional_goal_items: list[CheckboxItem] = []
    parse_errors: list[str] = []
    section = ""
    goal_lines = path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(goal_lines, 1):
        heading = HEADING_RE.match(line)
        if heading:
            section = normalize_heading(heading.group("title"))
            continue
        field = FIELD_RE.match(line)
        if field:
            fields[field.group(1).strip()] = field.group(2).strip()
        checkbox = CHECKBOX_RE.match(line)
        if not checkbox:
            continue
        item = CheckboxItem(
            item_id=checkbox.group("id"),
            text=checkbox.group("text").strip(),
            checked=checkbox.group("mark").strip().lower() == "x",
            line_number=line_number,
        )
        if section == "exit criteria":
            exit_criteria.append(item)
        elif section == "backlog":
            backlog.append(item)
        elif section == "optional goal item catalog":
            optional_goal_items.append(item)
    if not exit_criteria:
        parse_errors.append("goal.md must include at least one Exit Criteria checkbox")
    if int_field(fields, "current_iteration", 0) < 0:
        parse_errors.append("current_iteration must be >= 0")
    if int_field(fields, "run_safety_cap", 0) < 0:
        parse_errors.append("run_safety_cap must be >= 0")
    pr_authority = fields.get("pr_mutation_authority", "inspect_and_prepare_only")
    if pr_authority not in PR_MUTATION_AUTHORITY_VALUES:
        allowed = ",".join(PR_MUTATION_AUTHORITY_VALUES)
        parse_errors.append(
            f"pr_mutation_authority must be one of: {allowed}"
        )
    return GoalState(
        path=path,
        fields=fields,
        exit_criteria=tuple(exit_criteria),
        backlog=tuple(backlog),
        optional_goal_items=tuple(optional_goal_items),
        parse_errors=tuple(parse_errors),
    )


def normalize_heading(title: str) -> str:
    """Normalize a Markdown heading for section detection."""
    return re.sub(r"\s+", " ", title.strip().lower())


def render_machine_status(state: GoalState) -> str:
    """Render stable key-value status lines."""
    lines = [
        f"GOAL_FILE={state.path}",
        f"GOAL_STATUS_FIELD={state.goal_status}",
        f"GOAL_LOOP_STATUS={state.loop_status}",
        f"GOAL_CURRENT_ITERATION={state.current_iteration}",
        f"GOAL_RUN_SAFETY_CAP={state.run_safety_cap}",
        f"GOAL_PR_MUTATION_AUTHORITY={state.pr_mutation_authority}",
        f"GOAL_EXIT_CRITERIA_TOTAL={len(state.exit_criteria)}",
        f"GOAL_EXIT_CRITERIA_DONE={state.done_exit_criteria}",
        f"GOAL_BACKLOG_TOTAL={len(state.backlog)}",
        f"GOAL_BACKLOG_DONE={state.done_backlog_items}",
        f"GOAL_OPTIONAL_ITEMS_TOTAL={len(state.optional_goal_items)}",
        f"GOAL_OPTIONAL_ITEMS_DONE={state.done_optional_goal_items}",
        f"GOAL_PARSE_ERRORS={len(state.parse_errors)}",
        f"GOAL_NEXT_OPEN_ITEM={next_open_item(state)}",
        f"NEXT_ACTION={next_action(state)}",
    ]
    for error in state.parse_errors:
        lines.append(f"GOAL_PARSE_ERROR={error}")
    return "\n".join(lines) + "\n"


def next_action(state: GoalState) -> str:
    """Return the next loop action."""
    if state.loop_status == "achieved":
        return "close_goal_loop"
    if state.loop_status == "invalid":
        return "repair_goal_md"
    if state.loop_status == "blocked":
        return "wait_for_unblock"
    if state.loop_status == "stopped":
        return "stop_goal_loop"
    return "run_next_iteration"


def next_open_item(state: GoalState) -> str:
    """Return the first active unchecked item for large backlog iteration."""
    for item in state.backlog:
        if not item.checked:
            return f"backlog:{item.item_id}"
    for item in state.exit_criteria:
        if not item.checked:
            return f"exit_criteria:{item.item_id}"
    return "none"


def dependency_path_for(report_path: Path) -> str:
    """Return the report-relative path to this tool for dependency headers."""
    tool_path = Path("tools/agent_tools/goal_loop.py").resolve()
    return os.path.relpath(tool_path, report_path.parent.resolve())


def render_markdown_report(state: GoalState, dependency_path: str) -> str:
    """Render a Markdown report for the goal loop status."""
    lines = [
        "# Goal Loop Status",
        "<!--",
        "@dependency-start",
        "responsibility Records machine status for a top-level goal.md loop.",
        f"upstream implementation {dependency_path} generates this report",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
        f"- goal_file: `{state.path}`",
        f"- goal_status_field: `{state.goal_status}`",
        f"- goal_loop_status: `{state.loop_status}`",
        f"- current_iteration: `{state.current_iteration}`",
        f"- run_safety_cap: `{state.run_safety_cap}`",
        f"- pr_mutation_authority: `{state.pr_mutation_authority}`",
        f"- next_open_item: `{next_open_item(state)}`",
        f"- next_action: `{next_action(state)}`",
        "",
        "## Exit Criteria",
        "",
    ]
    for item in state.exit_criteria:
        mark = "x" if item.checked else " "
        lines.append(f"- [{mark}] {item.item_id}: {item.text}")
    lines.extend(["", "## Backlog", ""])
    for item in state.backlog:
        mark = "x" if item.checked else " "
        lines.append(f"- [{mark}] {item.item_id}: {item.text}")
    if state.optional_goal_items:
        lines.extend(["", "## Optional Goal Item Catalog", ""])
        lines.append(
            "These items are non-default catalog entries and do not block closeout "
            "unless copied into `Exit Criteria` or `Backlog`."
        )
        lines.append("")
        for item in state.optional_goal_items:
            mark = "x" if item.checked else " "
            lines.append(f"- [{mark}] {item.item_id}: {item.text}")
    if state.parse_errors:
        lines.extend(["", "## Parse Errors", ""])
        for error in state.parse_errors:
            lines.append(f"- {error}")
    lines.append("")
    return "\n".join(lines)


def open_items(items: tuple[CheckboxItem, ...]) -> list[CheckboxItem]:
    """Return unchecked goal items in file order."""
    return [item for item in items if not item.checked]


def render_work_plan(state: GoalState, max_items: int, dependency_path: str) -> str:
    """Render unchecked goal items as an implementation-ready TODO surface."""
    unchecked_criteria = open_items(state.exit_criteria)
    unchecked_backlog = open_items(state.backlog)
    selected = [*unchecked_backlog, *unchecked_criteria][: max(0, max_items)]
    lines = [
        "# Goal Work Breakdown",
        "<!--",
        "@dependency-start",
        "responsibility Records executable TODO units derived from goal.md.",
        f"upstream implementation {dependency_path} generates this plan",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
        f"- goal_file: `{state.path}`",
        f"- goal_status_field: `{state.goal_status}`",
        f"- goal_loop_status: `{state.loop_status}`",
        f"- next_action: `{next_action(state)}`",
        f"- pr_mutation_authority: `{state.pr_mutation_authority}`",
        f"- open_exit_criteria: `{len(unchecked_criteria)}`",
        f"- open_backlog_items: `{len(unchecked_backlog)}`",
        f"- optional_goal_items: `{len(state.optional_goal_items)}`",
        "",
        "## Work Units",
        "",
        "| Unit ID | Source | Work To Do | Evidence To Produce | Status |",
        "| ------- | ------ | ---------- | ------------------- | ------ |",
    ]
    if selected:
        for index, item in enumerate(selected, 1):
            source = "exit_criteria" if item in unchecked_criteria else "backlog"
            evidence = evidence_hint(item)
            lines.append(
                f"| GW{index} | {source}:{item.item_id} | {item.text} | "
                f"{evidence} | open |"
            )
    else:
        lines.append(
            "| none | none | No unchecked goal items. | "
            "closeout evidence | complete |"
        )
    lines.extend(
        [
            "",
            "## Optional Goal Item Catalog",
            "",
            "Optional catalog items are not emitted as `GW*` work units by default.",
            "Promote one by copying it into `Exit Criteria` or `Backlog` when the",
            "current objective requires it.",
            "",
            "| Item ID | Text | Status |",
            "| ------- | ---- | ------ |",
        ]
    )
    if state.optional_goal_items:
        for item in state.optional_goal_items:
            status = "selected" if item.checked else "available"
            lines.append(f"| {item.item_id} | {item.text} | {status} |")
    else:
        lines.append("| none | No optional catalog entries. | unavailable |")
    lines.extend(
        [
            "",
            "## Schedule Transfer Rule",
            "",
            "- Copy every open `GW*` row into the run bundle `schedule.md` "
            "before editing.",
            "- Do not start implementation from a bare objective without this "
            "breakdown.",
            "- If `NEXT_ACTION=run_next_iteration`, create the next iteration "
            "slice from the first open work unit.",
            "",
        ]
    )
    return "\n".join(lines)


def evidence_hint(item: CheckboxItem) -> str:
    """Return a concise evidence hint for one goal item."""
    text = item.text.lower()
    if "code dependency" in text or "scan_code_dependencies" in text:
        return "`scan_code_dependencies.sh` output"
    if "oop" in text or "readability" in text:
        return "`tools/oop/*/readability.py` report"
    if "hardcoded numeric" in text or "check_hardcoded_numbers" in text:
        return "`check_hardcoded_numbers.py` output"
    if "dependency" in text:
        return "`run_repo_dependency_review.sh` output"
    if (
        re.search(r"\bci\b", text)
        or "static analysis" in text
        or "pyright" in text
        or "ruff" in text
    ):
        return "`make ci` or documented static-analysis route"
    if "evidence" in text:
        return "run-bundle artifact with clause mapping"
    return "specific artifact path, command output, or review decision"


def write_report(path: str, state: GoalState) -> None:
    """Write a Markdown status report."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_markdown_report(state, dependency_path_for(report_path)),
        encoding="utf-8",
    )


def write_work_plan(path: str, state: GoalState, max_items: int) -> None:
    """Write a Markdown goal work breakdown."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_work_plan(state, max_items, dependency_path_for(report_path)),
        encoding="utf-8",
    )


def write_initial_goal(
    path: Path,
    objective: str,
    run_safety_cap: int,
    pr_mutation_authority: str,
    force: bool,
) -> None:
    """Write a starter goal.md contract."""
    if path.exists() and not force:
        raise RuntimeError(f"goal file already exists: {path}")
    text = "\n".join(
        [
            "# Goal",
            "<!--",
            "@dependency-start",
            "responsibility Defines the top-level goal loop contract for this "
            "repository.",
            "upstream design README.md repository entrypoint",
            "downstream implementation tools/agent_tools/goal_loop.py consumes "
            "this contract",
            "@dependency-end",
            "-->",
            "",
            "## Loop Contract",
            "",
            "- goal_status: active",
            f"- run_safety_cap: {run_safety_cap}",
            "- current_iteration: 0",
            f"- pr_mutation_authority: {pr_mutation_authority}",
            "- active_run_id:",
            "- stop_reason:",
            "",
            "## Objective",
            "",
            objective,
            "",
            "## Exit Criteria",
            "",
            *[f"- [ ] {item_id}: {text}" for item_id, text in DEFAULT_EXIT_CRITERIA],
            "",
            "## Backlog",
            "",
            *[f"- [ ] {item_id}: {text}" for item_id, text in DEFAULT_BACKLOG],
            "",
            "## Optional Goal Item Catalog",
            "",
            "These are non-default goal items. They are not active closeout gates "
            "and are not emitted as `GW*` work units unless copied into "
            "`Exit Criteria` or `Backlog` for this objective.",
            "",
            *[
                f"- [ ] {item_id}: ({category}) {text}"
                for item_id, category, text in OPTIONAL_GOAL_ITEMS
            ],
            "",
            "## Loop Log",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def update_field(lines: list[str], key: str, value: str) -> list[str]:
    """Update the first Markdown field line with a key."""
    field_pattern = re.compile(rf"^(\s*-\s*{re.escape(key)}:\s*).*$")
    for index, line in enumerate(lines):
        if field_pattern.match(line):
            lines[index] = f"- {key}: {value}"
            return lines
    lines.append(f"- {key}: {value}")
    return lines


def append_loop_log(lines: list[str], message: str) -> list[str]:
    """Append one loop log entry under the Loop Log section."""
    for index, line in enumerate(lines):
        heading = HEADING_RE.match(line)
        if heading and normalize_heading(heading.group("title")) == "loop log":
            insert_at = index + 1
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            lines.insert(insert_at, f"- {message}")
            return lines
    lines.extend(["", "## Loop Log", "", f"- {message}"])
    return lines


def advance_iteration(goal_file: Path, next_iteration: int, command: list[str]) -> None:
    """Update goal.md before running one iteration."""
    lines = goal_file.read_text(encoding="utf-8").splitlines()
    update_field(lines, "current_iteration", str(next_iteration))
    append_loop_log(
        lines,
        f"iteration {next_iteration}: started command `{' '.join(command)}`",
    )
    goal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_checkbox(goal_file: Path, target_id: str, checked: bool) -> None:
    """Set one checkbox by id."""
    lines = goal_file.read_text(encoding="utf-8").splitlines()
    replacement = "x" if checked else " "
    pattern = re.compile(rf"^(\s*-\s*)\[[ xX]\](\s*{re.escape(target_id)}:\s*.*)$")
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            lines[index] = f"{match.group(1)}[{replacement}]{match.group(2)}"
            goal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise RuntimeError(f"goal item not found: {target_id}")


def set_goal_status(goal_file: Path, status: str) -> None:
    """Set the goal_status field."""
    lines = goal_file.read_text(encoding="utf-8").splitlines()
    update_field(lines, "goal_status", status)
    goal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_goal_command(args: argparse.Namespace) -> int:
    """Run the command until goal.md is achieved or a run-local cap is hit."""
    goal_file = Path(str(args.goal_file)).resolve()
    command = list(args.command_args)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("goal_loop.py: run requires a command after --", file=sys.stderr)
        return 1
    configured_run_limit = args.max_iterations
    runs = 0
    while True:
        state = parse_goal(goal_file)
        run_limit = configured_run_limit
        if run_limit is None and state.run_safety_cap > 0:
            run_limit = state.run_safety_cap
        if args.report_out:
            write_report(str(args.report_out), state)
        print(render_machine_status(state), end="")
        if state.loop_status == "achieved":
            return 0
        if state.loop_status == "invalid":
            return 2
        if run_limit is not None and runs >= run_limit:
            print("GOAL_LOOP_STATUS=run_limit_reached")
            return 2
        next_iteration = state.current_iteration + 1
        advance_iteration(goal_file, next_iteration, command)
        env = os.environ.copy()
        env.update(
            {
                "GOAL_FILE": str(goal_file),
                "GOAL_LOOP_ITERATION": str(next_iteration),
                "GOAL_LOOP_STATUS": "continue",
            }
        )
        result = subprocess.run(command, check=False, env=env)
        runs += 1
        if result.returncode != 0:
            print(f"GOAL_LOOP_COMMAND_EXIT={result.returncode}")
            return result.returncode


def handle_init(args: argparse.Namespace) -> int:
    """Handle goal initialization."""
    goal_file = Path(str(args.goal_file)).resolve()
    write_initial_goal(
        goal_file,
        str(args.objective),
        int(args.max_iterations),
        str(args.pr_mutation_authority),
        bool(args.force),
    )
    print(f"GOAL_FILE={goal_file}")
    print("GOAL_LOOP_INIT=created")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    """Handle goal status reporting."""
    goal_file = Path(str(args.goal_file)).resolve()
    state = parse_goal(goal_file)
    if args.report_out:
        write_report(str(args.report_out), state)
    print(render_machine_status(state), end="")
    if args.require_achieved and state.loop_status != "achieved":
        return 2
    return 0 if state.loop_status != "invalid" else 1


def handle_plan(args: argparse.Namespace) -> int:
    """Handle goal work-breakdown rendering."""
    goal_file = Path(str(args.goal_file)).resolve()
    state = parse_goal(goal_file)
    report_path = (
        Path(str(args.report_out))
        if args.report_out
        else Path("reports/goal_work_breakdown.md")
    )
    text = render_work_plan(
        state,
        int(args.max_items),
        dependency_path_for(report_path),
    )
    if args.report_out:
        write_work_plan(str(args.report_out), state, int(args.max_items))
    print(text)
    work_units = len(open_items(state.exit_criteria)) + len(open_items(state.backlog))
    print(f"GOAL_WORK_UNITS={work_units}")
    print(f"NEXT_ACTION={next_action(state)}")
    return 0 if state.loop_status != "invalid" else 1


def handle_mark(args: argparse.Namespace) -> int:
    """Handle checkbox and status updates."""
    goal_file = Path(str(args.goal_file)).resolve()
    target = args.criterion or args.backlog
    set_checkbox(goal_file, str(target), bool(args.done))
    if args.goal_status:
        set_goal_status(goal_file, str(args.goal_status))
    if args.pr_mutation_authority:
        lines = goal_file.read_text(encoding="utf-8").splitlines()
        update_field(
            lines,
            "pr_mutation_authority",
            str(args.pr_mutation_authority),
        )
        goal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"GOAL_FILE={goal_file}")
    print(f"GOAL_MARKED={target}")
    return 0


def handle_command(args: argparse.Namespace) -> int:
    """Dispatch one parsed subcommand."""
    if args.command == "init":
        return handle_init(args)
    if args.command == "status":
        return handle_status(args)
    if args.command == "plan":
        return handle_plan(args)
    if args.command == "mark":
        return handle_mark(args)
    if args.command == "run":
        return run_goal_command(args)
    return 1


def main() -> int:
    """Run the goal loop command."""
    args = build_parser().parse_args()
    try:
        return handle_command(args)
    except RuntimeError as exc:
        print(f"goal_loop.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
