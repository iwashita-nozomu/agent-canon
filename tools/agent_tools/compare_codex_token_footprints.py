#!/usr/bin/env python3
# @dependency-start
# responsibility Compares Codex session token footprints and records run-bundle evidence.
# upstream design ../../agents/templates/workflow_monitoring.md stores run evidence
# upstream design ../../agents/workflows/token-efficient-codex-workflow.md defines token comparison protocol
# upstream implementation ./workflow_monitor.py appends monitoring evidence
# downstream implementation ../../tests/agent_tools/test_compare_codex_token_footprints.py tests it
# @dependency-end
"""Compare two Codex session token footprints and emit deterministic evidence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from workflow_monitor import append_monitoring

TARGET_RATIO = 0.5


@dataclass(frozen=True)
class TokenFootprint:
    """One session token footprint."""

    session_file: Path
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Compare two Codex session token footprints."
    )
    parser.add_argument(
        "--baseline-session",
        required=True,
        help="Baseline Codex session JSONL file.",
    )
    parser.add_argument(
        "--candidate-session",
        required=True,
        help="Candidate Codex session JSONL file.",
    )
    parser.add_argument(
        "--report-out",
        help="Optional Markdown report path for the comparison.",
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
    for raw_line in session_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        event = json.loads(line)
        if event.get("type") != "event_msg":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        if not isinstance(info, dict):
            continue
        total_usage = info.get("total_token_usage")
        if not isinstance(total_usage, dict):
            continue
        last = {
            "input_tokens": int(total_usage.get("input_tokens", 0)),
            "cached_input_tokens": int(total_usage.get("cached_input_tokens", 0)),
            "output_tokens": int(total_usage.get("output_tokens", 0)),
            "reasoning_output_tokens": int(
                total_usage.get("reasoning_output_tokens", 0)
            ),
            "total_tokens": int(total_usage.get("total_tokens", 0)),
        }
    if last is None:
        raise ValueError(f"no token_count event found in {session_file}")
    return TokenFootprint(session_file=session_file, **last)


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


def main() -> int:
    """Run the token comparison CLI."""
    args = build_parser().parse_args()
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
