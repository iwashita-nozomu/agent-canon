#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Evaluates Codex subagent role configuration, routing, model settings, and runtime metrics.
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagent role inventory contract
# upstream design ../../evidence/agent-evals/README.md eval directory contract
# upstream implementation ./agent_team.py loads team and task routing metadata
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# downstream implementation ../../tests/agent_tools/test_evaluate_codex_agent_roles.py tests role eval behavior
# @dependency-end
"""Evaluate Codex custom agent role definitions and routing policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_team import (  # noqa: E402
    Role,
    default_specialists_for_task,
    load_task_catalog,
    load_team_config,
)
from runtime_log_paths import eval_results_dir  # noqa: E402

COMPACT_FINDING_SAMPLE_LIMIT = 25
DEFAULT_RESULTS_FAMILY = "codex-agent-role"
RUN_ID_DIGEST_LENGTH = 10
GIT_COMMAND_TIMEOUT_SECONDS = 5
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
SPARK_MODEL = "gpt-5.3-codex-spark"
MINI_MODEL = "gpt-5.4-mini"
FRONTIER_MODEL = "gpt-5.5"
DEPRECATED_CODEX_MODELS = {"gpt-5.2", "gpt-5.3-codex"}
SPARK_MODEL_AGENT_IDS = {"spark_worker"}
MINI_MEDIUM_AGENT_IDS = {
    "experiment_runner",
    "explorer",
}
FRONTIER_XHIGH_AGENT_IDS = {
    "diff_triage_reviewer",
    "docs_workflow_steward",
    "reviewer",
    "ship_reviewer",
    "test_designer",
}


@dataclass(frozen=True)
class Finding:
    """One role eval finding."""

    check: str
    target: str
    detail: str

    def render(self) -> str:
        """Render a machine-readable finding line."""
        return f"CODEX_AGENT_ROLE_FINDING={self.check}:{self.target}:{self.detail}"


@dataclass(frozen=True)
class RuntimeSummary:
    """Aggregated runtime metrics for one agent role."""

    calls: int
    tokens: int
    latency_ms: int
    retries: int
    parent_interventions: int
    format_violations: int
    output_used: int


@dataclass(frozen=True)
class EvalRunMetadata:
    """Metadata recorded with one role eval run."""

    created_at: str
    eval_run_id: str
    run_id: str
    argv: tuple[str, ...]
    cwd: str
    root: str
    git_branch: str
    git_commit: str
    git_dirty: str


@dataclass(frozen=True)
class EvalReport:
    """Complete role eval report."""

    metadata: EvalRunMetadata
    status: str
    findings: tuple[Finding, ...]
    model_matrix: tuple[str, ...]
    runtime_metrics_status: str
    runtime_metrics: dict[str, RuntimeSummary]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--runtime-log",
        action="append",
        default=[],
        help="Optional JSONL file with role runtime metrics.",
    )
    parser.add_argument("--report-out", type=Path)
    parser.add_argument(
        "--compact-out",
        type=Path,
        help="Optional JSON summary path. When set, stdout omits full finding and model-matrix detail.",
    )
    parser.add_argument("--accumulate", action="store_true")
    parser.add_argument(
        "--results-dir",
        default="",
        help=(
            "Directory for accumulated reports. Defaults to the mounted "
            "AgentCanon log archive eval-results/codex-agent-role path."
        ),
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run bundle id recorded in accumulated reports.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return AgentCanon root for standalone or template invocation."""
    vendored = root / "vendor" / "agent-canon"
    if (vendored / ".codex" / "agents").is_dir():
        return vendored.resolve()
    return root.resolve()


def load_agent_configs(root: Path) -> dict[str, dict[str, object]]:
    """Load all project-scoped Codex custom agent TOML files."""
    configs: dict[str, dict[str, object]] = {}
    load_toml = cast(Callable[[str], dict[str, object]], getattr(tomllib, "loads"))
    for path in sorted((root / ".codex" / "agents").glob("*.toml")):
        payload = load_toml(path.read_text(encoding="utf-8"))
        payload["__path"] = path.relative_to(root).as_posix()
        payload["__stem"] = path.stem
        configs[str(payload.get("name", path.stem))] = payload
    return configs


def validate_no_legacy_model_policy(root: Path) -> list[Finding]:
    """Check that model settings are not duplicated in project config."""
    findings: list[Finding] = []
    config_path = root / ".codex" / "config.toml"
    if not config_path.is_file():
        return [Finding("model-settings", ".codex/config.toml", "missing-config")]
    load_toml = cast(Callable[[str], dict[str, object]], getattr(tomllib, "loads"))
    payload = load_toml(config_path.read_text(encoding="utf-8"))
    if "agent_model_policy" in payload:
        findings.append(Finding("model-settings", ".codex/config.toml", "legacy-agent-model-policy"))
    return findings


def role_by_id(roles: tuple[Role, ...]) -> dict[str, Role]:
    """Return roles keyed by id."""
    return {role.id: role for role in roles}


def evaluate_static_agent_configs(
    root: Path,
    configs: dict[str, dict[str, object]],
) -> list[Finding]:
    """Evaluate static role TOML schema, behavior, and executable model settings."""
    findings: list[Finding] = []
    for agent_id, config in configs.items():
        for field in ("name", "description", "developer_instructions"):
            if not str(config.get(field, "")).strip():
                findings.append(Finding("schema", agent_id, f"missing-{field}"))
        if config.get("name") != config.get("__stem"):
            findings.append(Finding("schema", agent_id, "name-file-stem-mismatch"))
        model = config.get("model")
        effort = config.get("model_reasoning_effort")
        if not isinstance(model, str) or not model:
            findings.append(Finding("model-settings", agent_id, "missing-model"))
        elif model in DEPRECATED_CODEX_MODELS:
            findings.append(Finding("model-settings", agent_id, f"deprecated-model-{model}"))
        elif model == SPARK_MODEL and agent_id not in SPARK_MODEL_AGENT_IDS:
            findings.append(Finding("model-settings", agent_id, "spark-model-reserved-for-spark-worker"))
        if not isinstance(effort, str) or effort not in VALID_REASONING_EFFORTS:
            findings.append(Finding("model-settings", agent_id, "invalid-model-reasoning-effort"))
        if agent_id in MINI_MEDIUM_AGENT_IDS:
            if model != MINI_MODEL:
                findings.append(Finding("model-settings", agent_id, f"expected-model-{MINI_MODEL}"))
            if effort != "medium":
                findings.append(Finding("model-settings", agent_id, "expected-medium-reasoning"))
        if agent_id.endswith("_reviewer") or agent_id in FRONTIER_XHIGH_AGENT_IDS:
            if model != FRONTIER_MODEL:
                findings.append(Finding("model-settings", agent_id, f"expected-model-{FRONTIER_MODEL}"))
            if effort != "xhigh":
                findings.append(Finding("model-settings", agent_id, "expected-xhigh-reasoning"))
        findings.extend(evaluate_role_behavior(root, agent_id, config))
    return findings


def evaluate_role_behavior(
    root: Path,
    agent_id: str,
    config: dict[str, object],
) -> list[Finding]:
    """Evaluate role-specific expected behavior and prohibitions."""
    findings: list[Finding] = []
    instructions = str(config.get("developer_instructions", ""))
    lower_instructions = instructions.lower()
    sandbox_mode = str(config.get("sandbox_mode", ""))
    read_only_role = (
        agent_id.endswith("_reviewer")
        or agent_id
        in {
            "diff_triage_reviewer",
            "explorer",
            "literature_researcher",
            "reviewer",
            "ship_reviewer",
            "test_designer",
        }
    )
    if read_only_role:
        if sandbox_mode != "read-only":
            findings.append(Finding("behavior", agent_id, "read-only-role-not-read-only"))
        if "do not edit" not in lower_instructions:
            findings.append(Finding("behavior", agent_id, "read-only-role-missing-do-not-edit"))
    if agent_id.endswith("_reviewer") or agent_id in {"diff_triage_reviewer", "reviewer", "ship_reviewer"}:
        if "finding" not in lower_instructions:
            findings.append(Finding("behavior", agent_id, "review-role-not-findings-first"))
    if agent_id == "explorer" and ("implementation" not in lower_instructions or "do not edit" not in lower_instructions):
        findings.append(Finding("behavior", agent_id, "explorer-must-stay-read-only"))
    if agent_id == "spark_worker":
        for phrase in ("bounded", "parent-assigned write scope", "report exactly which files changed"):
            if phrase not in lower_instructions:
                findings.append(Finding("behavior", agent_id, f"spark-worker-missing-{phrase}"))
    if agent_id == "worker" and "parent-assigned write scope" not in lower_instructions:
        findings.append(Finding("behavior", agent_id, "worker-missing-parent-managed-write-scope"))
    if agent_id == "experiment_runner" and "do not edit repository source" not in lower_instructions:
        findings.append(Finding("behavior", agent_id, "experiment-runner-may-edit-source"))
    if agent_id == "diff_triage_reviewer" and "escalate" not in lower_instructions:
        findings.append(Finding("behavior", agent_id, "diff-triage-missing-escalation-rule"))
    if Path(str(config.get("__path", ""))).suffix != ".toml":
        findings.append(Finding("schema", agent_id, "agent-path-not-toml"))
    return findings


def evaluate_routing(root: Path) -> list[Finding]:
    """Evaluate task routing and role-to-Codex-agent ordering."""
    findings: list[Finding] = []
    config = load_team_config(root / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, root=root)
    roles = role_by_id(config.always_on_roles + config.specialist_roles)

    expected_agent_order = {
        "change_reviewer": ("python_reviewer", "cpp_reviewer", "diff_triage_reviewer", "reviewer"),
        "experimenter": ("experiment_runner", "worker"),
        "final_reviewer": ("ship_reviewer", "reviewer", "project_reviewer"),
        "implementer": ("spark_worker", "worker"),
    }
    for role_id, expected in expected_agent_order.items():
        observed = roles[role_id].codex_agents[: len(expected)]
        if observed != expected:
            findings.append(Finding("routing", role_id, f"codex-agent-order-expected-{expected}"))

    for task_id in ("T1", "T2"):
        task = next(task for task in catalog.tasks if task["id"] == task_id)
        if task.get("family") != "owner_bounded_change":
            findings.append(Finding("routing", task_id, "must-use-owner-bounded-change"))
        specialists = default_specialists_for_task(config, catalog, task_id)
        forbidden = {"scheduler", "schedule_reviewer", "document_flow_reviewer"}
        active_forbidden = sorted(forbidden & set(specialists))
        if active_forbidden:
            findings.append(Finding("routing", task_id, f"lite-route-heavy-specialists-{active_forbidden}"))

    review_pack = next(pack for pack in catalog.review_packs if pack["id"] == "research_perspective_review")
    if review_pack.get("default_for_tasks"):
        findings.append(Finding("routing", "research_perspective_review", "full-pack-must-not-default"))
    triage_pack = next(pack for pack in catalog.review_packs if pack["id"] == "research_perspective_triage")
    if set(cast(list[str], triage_pack.get("specialists", []))) != {
        "reproducibility_reviewer",
        "artifact_reviewer",
    }:
        findings.append(Finding("routing", "research_perspective_triage", "unexpected-triage-specialists"))
    return findings


def runtime_log_paths(root: Path, explicit_logs: list[str]) -> tuple[Path, ...]:
    """Resolve optional runtime metric logs."""
    paths = [Path(raw).resolve() for raw in explicit_logs]
    default_dir = root / "agents" / "evals" / "results" / "subagent-role-runtime"
    if default_dir.is_dir():
        paths.extend(sorted(default_dir.glob("*.jsonl")))
    return tuple(path for path in paths if path.is_file())


def runtime_metrics(root: Path, explicit_logs: list[str]) -> tuple[str, dict[str, RuntimeSummary], list[Finding]]:
    """Aggregate optional token, latency, retry, intervention, format, and output-use metrics."""
    paths = runtime_log_paths(root, explicit_logs)
    if not paths:
        return "missing", {}, []
    raw: dict[str, Counter[str]] = defaultdict(Counter)
    findings: list[Finding] = []
    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                findings.append(Finding("runtime-log", f"{path}:{line_no}", "invalid-json"))
                continue
            if not isinstance(entry, dict):
                findings.append(Finding("runtime-log", f"{path}:{line_no}", "entry-not-object"))
                continue
            entry = cast(dict[str, object], entry)
            agent_id = str(entry.get("agent") or entry.get("codex_agent") or entry.get("role") or "")
            if not agent_id:
                findings.append(Finding("runtime-log", f"{path}:{line_no}", "missing-agent"))
                continue
            bucket = raw[agent_id]
            bucket["calls"] += 1
            for metric_name, keys in {
                "tokens": ("tokens", "total_tokens"),
                "latency_ms": ("latency_ms",),
                "retries": ("retry_count", "retries"),
            }.items():
                value, finding = int_metric(entry, *keys)
                bucket[metric_name] += value
                if finding is not None:
                    findings.append(
                        Finding(
                            "runtime-log",
                            f"{path}:{line_no}:{agent_id}:{finding}",
                            "invalid-int-metric",
                        )
                    )
            bucket["parent_interventions"] += int(bool(entry.get("parent_intervention")))
            bucket["format_violations"] += int(bool(entry.get("format_violation")))
            bucket["output_used"] += int(bool(entry.get("output_used")))
    summaries = {
        agent_id: RuntimeSummary(
            calls=counts["calls"],
            tokens=counts["tokens"],
            latency_ms=counts["latency_ms"],
            retries=counts["retries"],
            parent_interventions=counts["parent_interventions"],
            format_violations=counts["format_violations"],
            output_used=counts["output_used"],
        )
        for agent_id, counts in sorted(raw.items())
    }
    return "observed", summaries, findings


def int_metric(entry: dict[str, object], *keys: str) -> tuple[int, str | None]:
    """Return the first integer-like metric value found in one runtime entry."""
    for key in keys:
        value = entry.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return int(value), None
        if isinstance(value, int):
            return value, None
        if isinstance(value, float):
            return int(value), key if not value.is_integer() else None
        if isinstance(value, str):
            stripped = value.strip()
            try:
                return int(stripped), None
            except ValueError:
                try:
                    return int(float(stripped)), key
                except ValueError:
                    return 0, key
        return 0, key
    return 0, None


def model_matrix(configs: dict[str, dict[str, object]]) -> tuple[str, ...]:
    """Render agent executable model settings."""
    rows: list[str] = []
    for agent_id in sorted(configs):
        rows.append(
            f"{agent_id}:{configs[agent_id].get('model')}:{configs[agent_id].get('model_reasoning_effort')}"
        )
    return tuple(rows)


def git_output(root: Path, *args: str) -> str:
    """Return one git command output, or '-' outside a usable git checkout."""
    try:
        result = subprocess.run(
            ("git", "-C", root.as_posix(), *args),
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "-"
    if result.returncode != 0:
        return "-"
    return result.stdout.strip() or "-"


def build_eval_run_metadata(root: Path, run_id: str) -> EvalRunMetadata:
    """Build metadata with a unique, filename-safe eval run id."""
    now = datetime.now(UTC)
    created_at = now.isoformat()
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    digest_source = "|".join(("codex-agent-role", run_id.strip(), created_at, root.as_posix()))
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:RUN_ID_DIGEST_LENGTH]
    return EvalRunMetadata(
        created_at=created_at,
        eval_run_id=f"codex-agent-role-eval-{timestamp}-{digest}",
        run_id=run_id.strip(),
        argv=tuple(sys.argv),
        cwd=Path.cwd().as_posix(),
        root=root.as_posix(),
        git_branch=git_output(root, "rev-parse", "--abbrev-ref", "HEAD"),
        git_commit=git_output(root, "rev-parse", "HEAD"),
        git_dirty="yes" if git_output(root, "status", "--short", "--untracked-files=all") else "no",
    )


def evaluate(root: Path, runtime_logs: list[str], run_id: str = "") -> EvalReport:
    """Run the full role eval."""
    canon_root = agent_canon_root(root)
    configs = load_agent_configs(canon_root)
    findings = [
        *validate_no_legacy_model_policy(canon_root),
        *evaluate_static_agent_configs(canon_root, configs),
        *evaluate_routing(canon_root),
    ]
    metrics_status, metrics, metric_findings = runtime_metrics(canon_root, runtime_logs)
    findings.extend(metric_findings)
    return EvalReport(
        metadata=build_eval_run_metadata(canon_root, run_id),
        status="pass" if not findings else "fail",
        findings=tuple(findings),
        model_matrix=model_matrix(configs),
        runtime_metrics_status=metrics_status,
        runtime_metrics=metrics,
    )


def render_text(report: EvalReport, *, include_details: bool = True, compact_out: Path | None = None) -> str:
    """Render text output."""
    lines = [
        f"CODEX_AGENT_ROLE_EVAL_RUN_ID={report.metadata.eval_run_id}",
        f"CODEX_AGENT_ROLE_EVAL={report.status}",
        f"CODEX_AGENT_ROLE_FINDINGS={len(report.findings)}",
        f"ROLE_RUNTIME_METRICS_STATUS={report.runtime_metrics_status}",
    ]
    if compact_out is not None:
        lines.append(f"CODEX_AGENT_ROLE_COMPACT_OUT={compact_out.as_posix()}")
    if not include_details:
        return "\n".join(lines) + "\n"
    lines.append(f"ROLE_MODEL_MATRIX={';'.join(report.model_matrix)}")
    for agent_id, summary in report.runtime_metrics.items():
        lines.append(
            "ROLE_RUNTIME_METRIC="
            f"{agent_id}:calls={summary.calls}:tokens={summary.tokens}:"
            f"latency_ms={summary.latency_ms}:retries={summary.retries}:"
            f"parent_interventions={summary.parent_interventions}:"
            f"format_violations={summary.format_violations}:output_used={summary.output_used}"
        )
    lines.extend(finding.render() for finding in report.findings)
    return "\n".join(lines) + "\n"


def compact_summary(report: EvalReport) -> dict[str, object]:
    """Return a bounded JSON-friendly role eval summary."""
    findings_by_check = Counter(finding.check for finding in report.findings)
    model_counts = Counter(row.split(":", 2)[1] for row in report.model_matrix)
    runtime_totals = {
        "calls": sum(summary.calls for summary in report.runtime_metrics.values()),
        "tokens": sum(summary.tokens for summary in report.runtime_metrics.values()),
        "latency_ms": sum(summary.latency_ms for summary in report.runtime_metrics.values()),
        "retries": sum(summary.retries for summary in report.runtime_metrics.values()),
        "parent_interventions": sum(
            summary.parent_interventions for summary in report.runtime_metrics.values()
        ),
        "format_violations": sum(summary.format_violations for summary in report.runtime_metrics.values()),
        "output_used": sum(summary.output_used for summary in report.runtime_metrics.values()),
    }
    return {
        "status": report.status,
        "finding_count": len(report.findings),
        "findings_by_check": dict(sorted(findings_by_check.items())),
        "model_counts": dict(sorted(model_counts.items())),
        "runtime_metrics_status": report.runtime_metrics_status,
        "runtime_totals": runtime_totals,
        "finding_samples": [
            asdict(finding) for finding in report.findings[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
    }


def write_compact_summary(path: Path, report: EvalReport) -> None:
    """Write a bounded JSON summary for agent consumption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(compact_summary(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown_report(path: Path, report: EvalReport) -> Path:
    """Write a Markdown role eval report."""
    lines = [
        "# Codex Agent Role Eval",
        "",
        "<!--",
        "@dependency-start",
        "responsibility Records one Codex subagent role eval run.",
        "upstream implementation ../../../../tools/agent_tools/evaluate_codex_agent_roles.py generates this report",
        "@dependency-end",
        "-->",
        "",
        f"CODEX_AGENT_ROLE_EVAL_RUN_ID={report.metadata.eval_run_id}",
        f"CODEX_AGENT_ROLE_EVAL={report.status}",
        f"CODEX_AGENT_ROLE_FINDINGS={len(report.findings)}",
        f"ROLE_RUNTIME_METRICS_STATUS={report.runtime_metrics_status}",
        f"run_id: `{report.metadata.run_id or '-'}`",
        f"git_branch: `{report.metadata.git_branch}`",
        f"git_commit: `{report.metadata.git_commit}`",
        f"git_dirty: `{report.metadata.git_dirty}`",
        "",
        "## Model Matrix",
        "",
    ]
    lines.extend(f"- `{row}`" for row in report.model_matrix)
    lines.extend(["", "## Runtime Metrics", ""])
    if report.runtime_metrics:
        for agent_id, summary in report.runtime_metrics.items():
            lines.append(f"- `{agent_id}`: `{asdict(summary)}`")
    else:
        lines.append("- `missing`: no role runtime metric JSONL was provided")
    lines.extend(["", "## Findings", ""])
    if report.findings:
        lines.extend(f"- `{finding.render()}`" for finding in report.findings)
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path = path.with_name(f"{path.stem}-{report.metadata.eval_run_id}{path.suffix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def resolve_results_dir(root: Path, value: str) -> Path:
    """Resolve the CLI results directory or the default archive location."""
    stripped = value.strip()
    if stripped:
        path = Path(stripped)
        return path if path.is_absolute() else root / path
    return eval_results_dir(agent_canon_root(root), DEFAULT_RESULTS_FAMILY)


def accumulated_report_path(results_dir: Path, report: EvalReport) -> Path:
    """Return the unique accumulated report path."""
    return results_dir / f"{report.metadata.eval_run_id}-{report.status}.md"


def main() -> int:
    """Run the role eval."""
    args = build_parser().parse_args()
    report = evaluate(args.root, cast(list[str], args.runtime_log), str(args.run_id))
    report_paths: list[Path] = []
    if args.report_out is not None:
        report_paths.append(write_markdown_report(args.report_out, report))
    if args.compact_out is not None:
        write_compact_summary(args.compact_out, report)
    if args.accumulate:
        report_paths.append(
            write_markdown_report(
                accumulated_report_path(resolve_results_dir(args.root, str(args.results_dir)), report),
                report,
            )
        )
    if args.format == "json":
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(
            render_text(
                report,
                include_details=args.compact_out is None,
                compact_out=args.compact_out,
            ),
            end="",
        )
        for path in report_paths:
            print(f"CODEX_AGENT_ROLE_EVAL_REPORT={path}")
        if args.accumulate and report_paths:
            print(f"CODEX_AGENT_ROLE_EVAL_ACCUMULATED_REPORT={report_paths[-1]}")
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
