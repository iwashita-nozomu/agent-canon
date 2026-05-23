#!/usr/bin/env python3
# @dependency-start
# responsibility Evaluates Codex subagent role configuration, routing, cost buckets, and runtime metrics.
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagent role inventory contract
# upstream design ../../agents/evals/README.md eval directory contract
# upstream implementation ./agent_team.py loads team and task routing metadata
# downstream implementation ../../tests/agent_tools/test_evaluate_codex_agent_roles.py tests role eval behavior
# @dependency-end
"""Evaluate Codex custom agent role definitions and routing cost policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_team import (  # noqa: E402
    Role,
    default_specialists_for_task,
    load_task_catalog,
    load_team_config,
)

FRONTIER_MODEL = "gpt-5.5"
MINI_MODEL = "gpt-5.4-mini"
SPARK_MODEL = "gpt-5.3-codex-spark"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

MODEL_POLICY: dict[str, tuple[str, str, str]] = {
    "artifact_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "benchmark_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "citation_evidence_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "cpp_reviewer": ("cheap_first_review", SPARK_MODEL, LOW),
    "detailed_design_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "detailed_designer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "diff_triage_reviewer": ("cheap_first_review", SPARK_MODEL, LOW),
    "docs_workflow_steward": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "document_flow_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "execution_planner": ("frontier_required", FRONTIER_MODEL, HIGH),
    "experiment_runner": ("execution_only", SPARK_MODEL, LOW),
    "explorer": ("cheap_first_review", SPARK_MODEL, LOW),
    "fair_data_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "literature_researcher": ("frontier_required", FRONTIER_MODEL, HIGH),
    "logic_gap_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "long_form_writer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "manager_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "ml_science_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "notation_definition_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "oop_readability_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "plan_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "project_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "python_reviewer": ("cheap_first_review", SPARK_MODEL, LOW),
    "report_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "reproducibility_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "requirements_organizer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "scientific_computing_reviewer": ("conditional_frontier", MINI_MODEL, MEDIUM),
    "ship_reviewer": ("frontier_required", FRONTIER_MODEL, HIGH),
    "spark_worker": ("execution_only", SPARK_MODEL, LOW),
    "test_designer": ("cheap_first_review", SPARK_MODEL, LOW),
    "worker": ("frontier_required", FRONTIER_MODEL, HIGH),
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
class EvalReport:
    """Complete role eval report."""

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
    for path in sorted((root / ".codex" / "agents").glob("*.toml")):
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        payload["__path"] = path.relative_to(root).as_posix()
        payload["__stem"] = path.stem
        configs[str(payload.get("name", path.stem))] = payload
    return configs


def role_by_id(roles: tuple[Role, ...]) -> dict[str, Role]:
    """Return roles keyed by id."""
    return {role.id: role for role in roles}


def evaluate_static_agent_configs(
    root: Path,
    configs: dict[str, dict[str, object]],
) -> list[Finding]:
    """Evaluate static role TOML schema, behavior, and model policy."""
    findings: list[Finding] = []
    for agent_id, config in configs.items():
        for field in ("name", "description", "developer_instructions"):
            if not str(config.get(field, "")).strip():
                findings.append(Finding("schema", agent_id, f"missing-{field}"))
        if config.get("name") != config.get("__stem"):
            findings.append(Finding("schema", agent_id, "name-file-stem-mismatch"))
        if agent_id not in MODEL_POLICY:
            findings.append(Finding("model-policy", agent_id, "unclassified-agent"))
            continue
        bucket, expected_model, expected_effort = MODEL_POLICY[agent_id]
        if config.get("model") != expected_model:
            findings.append(
                Finding("model-policy", agent_id, f"{bucket}-model-expected-{expected_model}")
            )
        if config.get("model_reasoning_effort") != expected_effort:
            findings.append(
                Finding("model-policy", agent_id, f"{bucket}-effort-expected-{expected_effort}")
            )
        findings.extend(evaluate_role_behavior(root, agent_id, config))
    missing_policy = sorted(set(MODEL_POLICY) - set(configs))
    for agent_id in missing_policy:
        findings.append(Finding("model-policy", agent_id, "missing-agent-toml"))
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
        for phrase in ("narrow", "parent-assigned write scope", "report exactly which files changed"):
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
        if task.get("family") != "scoped_change_lite":
            findings.append(Finding("routing", task_id, "must-use-scoped-change-lite"))
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
    """Render agent model bucket matrix."""
    rows: list[str] = []
    for agent_id in sorted(configs):
        bucket, _, _ = MODEL_POLICY.get(agent_id, ("unclassified", "", ""))
        rows.append(
            f"{agent_id}:{bucket}:{configs[agent_id].get('model')}:{configs[agent_id].get('model_reasoning_effort')}"
        )
    return tuple(rows)


def evaluate(root: Path, runtime_logs: list[str]) -> EvalReport:
    """Run the full role eval."""
    canon_root = agent_canon_root(root)
    configs = load_agent_configs(canon_root)
    findings = [
        *evaluate_static_agent_configs(canon_root, configs),
        *evaluate_routing(canon_root),
    ]
    metrics_status, metrics, metric_findings = runtime_metrics(canon_root, runtime_logs)
    findings.extend(metric_findings)
    return EvalReport(
        status="pass" if not findings else "fail",
        findings=tuple(findings),
        model_matrix=model_matrix(configs),
        runtime_metrics_status=metrics_status,
        runtime_metrics=metrics,
    )


def render_text(report: EvalReport) -> str:
    """Render text output."""
    lines = [
        f"CODEX_AGENT_ROLE_EVAL={report.status}",
        f"CODEX_AGENT_ROLE_FINDINGS={len(report.findings)}",
        f"ROLE_RUNTIME_METRICS_STATUS={report.runtime_metrics_status}",
        f"ROLE_MODEL_MATRIX={';'.join(report.model_matrix)}",
    ]
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


def write_markdown_report(path: Path, report: EvalReport) -> None:
    """Write a Markdown role eval report."""
    lines = [
        "# Codex Agent Role Eval",
        "",
        f"CODEX_AGENT_ROLE_EVAL={report.status}",
        f"CODEX_AGENT_ROLE_FINDINGS={len(report.findings)}",
        f"ROLE_RUNTIME_METRICS_STATUS={report.runtime_metrics_status}",
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Run the role eval."""
    args = build_parser().parse_args()
    report = evaluate(args.root, cast(list[str], args.runtime_log))
    if args.report_out is not None:
        write_markdown_report(args.report_out, report)
    if args.format == "json":
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_text(report), end="")
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
