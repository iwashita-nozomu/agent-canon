#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Compares Codex session token footprints and records run-bundle evidence.
# upstream design ../../agents/templates/workflow_monitoring.md stores run evidence
# upstream design ../../agents/workflows/token-efficient-codex-workflow.md defines token comparison protocol
# upstream implementation ./workflow_monitor.py appends monitoring evidence
# downstream implementation ../../tests/agent_tools/test_compare_codex_token_footprints.py tests it
# @dependency-end
"""Compare two Codex session token footprints and emit deterministic evidence."""

from __future__ import annotations

import argparse
import glob
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from workflow_monitor import append_monitoring

TARGET_RATIO = 0.5
DEFAULT_MOVING_AVERAGE_WINDOW = 5
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60
SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class TokenFootprint:
    """One session token footprint."""

    session_file: Path
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    token_event_count: int


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Compare or summarize Codex session token footprints."
    )
    parser.add_argument(
        "--baseline-session",
        help="Baseline Codex session JSONL file.",
    )
    parser.add_argument(
        "--candidate-session",
        help="Candidate Codex session JSONL file.",
    )
    parser.add_argument(
        "--session-glob",
        action="append",
        default=[],
        help=(
            "Session JSONL glob for summary mode. May be repeated. "
            "When set, the tool emits token usage moving-average evidence."
        ),
    )
    parser.add_argument(
        "--moving-average-window",
        type=int,
        default=DEFAULT_MOVING_AVERAGE_WINDOW,
        help="Session window size for token summary moving averages.",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        help=(
            "Only include session files modified within this many days in "
            "summary mode. Uses file mtime so long-running sessions stay visible."
        ),
    )
    parser.add_argument(
        "--report-out",
        help="Optional Markdown report path for the comparison or summary.",
    )
    parser.add_argument(
        "--report-dir",
        help="Optional run bundle directory to append monitoring evidence.",
    )
    return parser


def parse_token_usage(session_file: Path) -> TokenFootprint:
    """Return the last token_count event from one Codex session JSONL file."""
    if not session_file.is_file():
        raise FileNotFoundError(session_file)
    last: dict[str, int] | None = None
    token_event_count = 0
    for raw_line in session_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        loaded: object = json.loads(line)
        event = object_mapping(loaded)
        if event is None:
            continue
        if event.get("type") != "event_msg":
            continue
        payload = object_mapping(event.get("payload"))
        if payload is None or payload.get("type") != "token_count":
            continue
        info = object_mapping(payload.get("info"))
        if info is None:
            continue
        total_usage = object_mapping(info.get("total_token_usage"))
        if total_usage is None:
            continue
        token_event_count += 1
        last = {
            "input_tokens": token_int(total_usage, "input_tokens"),
            "cached_input_tokens": token_int(total_usage, "cached_input_tokens"),
            "output_tokens": token_int(total_usage, "output_tokens"),
            "reasoning_output_tokens": int(
                token_int(total_usage, "reasoning_output_tokens")
            ),
            "total_tokens": token_int(total_usage, "total_tokens"),
        }
    if last is None:
        raise ValueError(f"no token_count event found in {session_file}")
    return TokenFootprint(
        session_file=session_file,
        token_event_count=token_event_count,
        **last,
    )


def object_mapping(value: object) -> Mapping[str, object] | None:
    """Return a string-key mapping when decoded JSON has object shape."""
    if not isinstance(value, dict):
        return None
    return cast(Mapping[str, object], value)


def token_int(mapping: Mapping[str, object], key: str) -> int:
    """Return an integer token field from a decoded JSON object."""
    value = mapping.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def ratio(candidate: TokenFootprint, baseline: TokenFootprint) -> float:
    """Return candidate / baseline token ratio."""
    if baseline.total_tokens <= 0:
        raise ValueError("baseline total_tokens must be greater than zero")
    return candidate.total_tokens / baseline.total_tokens


def comparison_status(candidate: TokenFootprint, baseline: TokenFootprint) -> str:
    """Return pass/fail based on the target ratio."""
    return "pass" if ratio(candidate, baseline) <= TARGET_RATIO else "fail"


def render_report(baseline: TokenFootprint, candidate: TokenFootprint) -> str:
    """Render a Markdown comparison report."""
    value = ratio(candidate, baseline)
    status = comparison_status(candidate, baseline)
    lines = [
        "# Codex Token Footprint Comparison",
        "<!--",
        "@dependency-start",
        "responsibility Records Codex token footprint comparison evidence.",
        "upstream implementation ../../tools/agent_tools/compare_codex_token_footprints.py generates this report",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
        f"- comparison_status: {status}",
        f"- baseline_total_tokens: {baseline.total_tokens}",
        f"- candidate_total_tokens: {candidate.total_tokens}",
        f"- token_ratio: {value:.3f}",
        f"- target_ratio: {TARGET_RATIO:.3f}",
        "",
        "## Sessions",
        "",
        "| Label | Session File | input | cached input | output | reasoning output | total |",
        "| ----- | ------------ | ----- | ------------ | ------ | ---------------- | ----- |",
        row("baseline", baseline),
        row("candidate", candidate),
        "",
        "## Machine Status",
        "",
        f"- TOKEN_FOOTPRINT_COMPARISON={status}",
        f"- TOKEN_FOOTPRINT_RATIO={value:.3f}",
        f"- TOKEN_FOOTPRINT_TARGET={TARGET_RATIO:.3f}",
        "",
    ]
    return "\n".join(lines)


def row(label: str, footprint: TokenFootprint) -> str:
    """Render one Markdown table row."""
    return (
        f"| {label} | {footprint.session_file} | {footprint.input_tokens} | "
        f"{footprint.cached_input_tokens} | {footprint.output_tokens} | "
        f"{footprint.reasoning_output_tokens} | {footprint.total_tokens} |"
    )


def session_glob_paths(
    patterns: Sequence[str],
    *,
    recent_days: int | None = None,
) -> tuple[Path, ...]:
    """Return deterministic session paths from one or more glob patterns."""
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(
            Path(path).resolve()
            for path in glob.glob(pattern, recursive=True)
            if Path(path).is_file()
        )
    if recent_days is not None:
        cutoff = (
            time.time()
            - max(0, recent_days) * HOURS_PER_DAY * MINUTES_PER_HOUR * SECONDS_PER_MINUTE
        )
        paths = {path for path in paths if path.stat().st_mtime >= cutoff}
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def read_session_globs(
    patterns: Sequence[str],
    *,
    recent_days: int | None = None,
) -> tuple[TokenFootprint, ...]:
    """Return token footprints for all parseable sessions in the requested globs."""
    footprints: list[TokenFootprint] = []
    for path in session_glob_paths(patterns, recent_days=recent_days):
        try:
            footprints.append(parse_token_usage(path))
        except ValueError:
            continue
    if not footprints:
        raise ValueError("no session files with token_count events matched --session-glob")
    return tuple(footprints)


def moving_average(values: Sequence[int], window: int) -> tuple[float, ...]:
    """Return rolling averages over positive-width windows."""
    width = max(1, window)
    averages: list[float] = []
    for index in range(len(values)):
        start = max(0, index - width + 1)
        segment = values[start : index + 1]
        averages.append(sum(segment) / len(segment))
    return tuple(averages)


def token_total(footprints: Sequence[TokenFootprint]) -> int:
    """Return total tokens across sessions."""
    return sum(footprint.total_tokens for footprint in footprints)


def token_event_total(footprints: Sequence[TokenFootprint]) -> int:
    """Return token_count event count across sessions."""
    return sum(footprint.token_event_count for footprint in footprints)


def tokens_per_event(footprints: Sequence[TokenFootprint]) -> float:
    """Return the average total-token footprint per token_count event."""
    events = token_event_total(footprints)
    if events <= 0:
        return 0.0
    return token_total(footprints) / events


def latest_moving_average(footprints: Sequence[TokenFootprint], window: int) -> float:
    """Return the latest rolling average for session total tokens."""
    values = [footprint.total_tokens for footprint in footprints]
    return moving_average(values, window)[-1]


def render_summary_report(
    footprints: Sequence[TokenFootprint],
    window: int,
    *,
    recent_days: int | None = None,
) -> str:
    """Render a Markdown token usage summary with moving averages."""
    averages = moving_average([footprint.total_tokens for footprint in footprints], window)
    lines = [
        "# Codex Token Usage Summary",
        "<!--",
        "@dependency-start",
        "responsibility Records Codex token usage moving-average evidence.",
        "upstream implementation ../../tools/agent_tools/compare_codex_token_footprints.py generates this report",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
        "- token_usage_summary_status: present",
        f"- token_session_count: {len(footprints)}",
        f"- token_event_count: {token_event_total(footprints)}",
        f"- total_tokens: {token_total(footprints)}",
        f"- recent_days: {recent_days if recent_days is not None else 'all'}",
        f"- average_tokens_per_event: {tokens_per_event(footprints):.3f}",
        f"- moving_average_window: {max(1, window)}",
        f"- latest_moving_average_total_tokens: {latest_moving_average(footprints, window):.3f}",
        "",
        "## Sessions",
        "",
        "| Session File | token events | input | cached input | output | reasoning output | total | moving average total |",
        "| ------------ | ------------ | ----- | ------------ | ------ | ---------------- | ----- | -------------------- |",
    ]
    for footprint, average in zip(footprints, averages, strict=True):
        lines.append(
            f"| {footprint.session_file} | {footprint.token_event_count} | "
            f"{footprint.input_tokens} | {footprint.cached_input_tokens} | "
            f"{footprint.output_tokens} | {footprint.reasoning_output_tokens} | "
            f"{footprint.total_tokens} | {average:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Machine Status",
            "",
            "- TOKEN_USAGE_SUMMARY=pass",
            f"- TOKEN_USAGE_SESSION_COUNT={len(footprints)}",
            f"- TOKEN_USAGE_TOKEN_EVENT_COUNT={token_event_total(footprints)}",
            f"- TOKEN_USAGE_TOTAL_TOKENS={token_total(footprints)}",
            f"- TOKEN_USAGE_RECENT_DAYS={recent_days if recent_days is not None else 'all'}",
            f"- TOKEN_USAGE_AVERAGE_TOKENS_PER_EVENT={tokens_per_event(footprints):.3f}",
            f"- TOKEN_USAGE_MOVING_AVERAGE_WINDOW={max(1, window)}",
            f"- TOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL={latest_moving_average(footprints, window):.3f}",
            "",
        ]
    )
    return "\n".join(lines)


def print_machine_status(baseline: TokenFootprint, candidate: TokenFootprint) -> None:
    """Print grep-friendly status lines."""
    value = ratio(candidate, baseline)
    status = comparison_status(candidate, baseline)
    print(f"TOKEN_FOOTPRINT_COMPARISON={status}")
    print(f"TOKEN_FOOTPRINT_BASELINE_TOTAL={baseline.total_tokens}")
    print(f"TOKEN_FOOTPRINT_CANDIDATE_TOTAL={candidate.total_tokens}")
    print(f"TOKEN_FOOTPRINT_RATIO={value:.3f}")
    print(f"TOKEN_FOOTPRINT_TARGET={TARGET_RATIO:.3f}")
    print(f"TOKEN_FOOTPRINT_BELOW_TARGET={'yes' if value <= TARGET_RATIO else 'no'}")
    print(
        "NEXT_ACTION="
        + (
            "record_token_efficiency_evidence"
            if status == "pass"
            else "reduce_token_footprint"
        )
    )


def append_report_dir(report_dir: Path, baseline: TokenFootprint, candidate: TokenFootprint) -> None:
    """Append monitoring evidence to one run bundle."""
    value = ratio(candidate, baseline)
    status = comparison_status(candidate, baseline)
    append_monitoring(
        report_dir,
        behavior_events=[
            (
                "token_efficiency_protocol=active "
                "token_footprint_comparison="
                f"{status} baseline_total={baseline.total_tokens} "
                f"candidate_total={candidate.total_tokens} "
                f"token_ratio={value:.3f} target_ratio={TARGET_RATIO:.3f}"
            ),
        ],
        interventions=[
            (
                "token footprint measured from Codex session logs "
                f"baseline={baseline.session_file.name} "
                f"candidate={candidate.session_file.name}"
            ),
        ],
    )


def append_summary_report_dir(
    report_dir: Path,
    footprints: Sequence[TokenFootprint],
    window: int,
    *,
    recent_days: int | None = None,
) -> None:
    """Append token moving-average evidence to one run bundle."""
    append_monitoring(
        report_dir,
        behavior_events=[
            (
                "token_usage_summary=present "
                f"session_count={len(footprints)} "
                f"token_event_count={token_event_total(footprints)} "
                f"total_tokens={token_total(footprints)} "
                f"recent_days={recent_days if recent_days is not None else 'all'} "
                f"moving_average_window={max(1, window)} "
                f"latest_moving_average_total={latest_moving_average(footprints, window):.3f} "
                f"average_tokens_per_event={tokens_per_event(footprints):.3f}"
            ),
        ],
        interventions=[
            "token usage moving average measured from Codex session logs",
        ],
    )


def print_summary_status(
    footprints: Sequence[TokenFootprint],
    window: int,
    *,
    recent_days: int | None = None,
) -> None:
    """Print grep-friendly token summary status lines."""
    print("TOKEN_USAGE_SUMMARY=pass")
    print(f"TOKEN_USAGE_SESSION_COUNT={len(footprints)}")
    print(f"TOKEN_USAGE_TOKEN_EVENT_COUNT={token_event_total(footprints)}")
    print(f"TOKEN_USAGE_TOTAL_TOKENS={token_total(footprints)}")
    print(f"TOKEN_USAGE_RECENT_DAYS={recent_days if recent_days is not None else 'all'}")
    print(f"TOKEN_USAGE_AVERAGE_TOKENS_PER_EVENT={tokens_per_event(footprints):.3f}")
    print(f"TOKEN_USAGE_MOVING_AVERAGE_WINDOW={max(1, window)}")
    print(f"TOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL={latest_moving_average(footprints, window):.3f}")
    print("NEXT_ACTION=record_token_usage_summary")


def main() -> int:
    """Run the token comparison CLI."""
    args = build_parser().parse_args()
    if args.session_glob:
        footprints = read_session_globs(
            tuple(str(pattern) for pattern in args.session_glob),
            recent_days=args.recent_days,
        )
        if args.report_out:
            report_path = Path(str(args.report_out))
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                render_summary_report(
                    footprints,
                    args.moving_average_window,
                    recent_days=args.recent_days,
                ),
                encoding="utf-8",
            )
        if args.report_dir:
            append_summary_report_dir(
                Path(str(args.report_dir)).resolve(),
                footprints,
                args.moving_average_window,
                recent_days=args.recent_days,
            )
        print_summary_status(
            footprints,
            args.moving_average_window,
            recent_days=args.recent_days,
        )
        return 0
    if not args.baseline_session or not args.candidate_session:
        raise SystemExit("--baseline-session and --candidate-session are required unless --session-glob is set")
    baseline = parse_token_usage(Path(str(args.baseline_session)).resolve())
    candidate = parse_token_usage(Path(str(args.candidate_session)).resolve())
    if args.report_out:
        report_path = Path(str(args.report_out))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(baseline, candidate), encoding="utf-8")
    if args.report_dir:
        append_report_dir(Path(str(args.report_dir)).resolve(), baseline, candidate)
    print_machine_status(baseline, candidate)
    return 1 if comparison_status(candidate, baseline) == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
