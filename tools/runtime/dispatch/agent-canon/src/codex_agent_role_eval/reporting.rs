use super::EvalReport;
use crate::runtime_boundary::RuntimeArtifactBoundary;
use rustpython_ast::bigint::BigInt;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

pub(super) fn text(report: &EvalReport, details: bool, compact: Option<&Path>) -> String {
    let mut lines = vec![
        format!(
            "CODEX_AGENT_ROLE_EVAL_RUN_ID={}",
            report.metadata.eval_run_id
        ),
        format!("CODEX_AGENT_ROLE_EVAL={}", report.status),
        format!("CODEX_AGENT_ROLE_FINDINGS={}", report.findings.len()),
        format!(
            "ROLE_RUNTIME_METRICS_STATUS={}",
            report.runtime_metrics_status
        ),
    ];
    if let Some(path) = compact {
        lines.push(format!("CODEX_AGENT_ROLE_COMPACT_OUT={}", path.display()));
    }
    if details {
        lines.push(format!(
            "ROLE_MODEL_MATRIX={}",
            report.model_matrix.join(";")
        ));
        for (id, summary) in &report.runtime_metrics {
            lines.push(format!("ROLE_RUNTIME_METRIC={id}:calls={}:tokens={}:latency_ms={}:retries={}:parent_interventions={}:format_violations={}:output_used={}", summary.calls, summary.tokens, summary.latency_ms, summary.retries, summary.parent_interventions, summary.format_violations, summary.output_used));
        }
        lines.extend(report.findings.iter().map(super::Finding::line));
    }
    lines.join("\n") + "\n"
}

pub(super) fn compact(report: &EvalReport) -> Value {
    let mut checks = BTreeMap::<String, usize>::new();
    let mut models = BTreeMap::<String, usize>::new();
    for finding in &report.findings {
        *checks.entry(finding.check.clone()).or_default() += 1;
    }
    for row in &report.model_matrix {
        *models
            .entry(row.split(':').nth(1).unwrap_or("").to_owned())
            .or_default() += 1;
    }
    let names = [
        "calls",
        "tokens",
        "latency_ms",
        "retries",
        "parent_interventions",
        "format_violations",
        "output_used",
    ];
    let mut totals = BTreeMap::new();
    for name in names {
        let total: BigInt = report
            .runtime_metrics
            .values()
            .map(|summary| match name {
                "calls" => &summary.calls,
                "tokens" => &summary.tokens,
                "latency_ms" => &summary.latency_ms,
                "retries" => &summary.retries,
                "parent_interventions" => &summary.parent_interventions,
                "format_violations" => &summary.format_violations,
                _ => &summary.output_used,
            })
            .cloned()
            .sum();
        let number = total
            .to_string()
            .parse::<serde_json::Number>()
            .expect("integer JSON number");
        totals.insert(name, Value::Number(number));
    }
    json!({"status": report.status, "finding_count": report.findings.len(), "findings_by_check": checks,
        "model_counts": models, "runtime_metrics_status": report.runtime_metrics_status,
        "runtime_totals": totals, "finding_samples": report.findings.iter().take(25).collect::<Vec<_>>()})
}

pub(super) fn markdown(report: &EvalReport) -> Result<String, String> {
    let mut lines = vec!["# Codex Agent Role Eval".to_owned(), "".into(), "<!--".into(), "@dependency-start".into(),
        "responsibility Records one Codex subagent role eval run.".into(),
        "upstream implementation ../../../../tools/runtime/dispatch/agent-canon/src/codex_agent_role_eval/mod.rs generates this report".into(),
        "@dependency-end".into(), "-->".into(), "".into(),
        format!("CODEX_AGENT_ROLE_EVAL_RUN_ID={}", report.metadata.eval_run_id),
        format!("CODEX_AGENT_ROLE_EVAL={}", report.status),
        format!("CODEX_AGENT_ROLE_FINDINGS={}", report.findings.len()),
        format!("ROLE_RUNTIME_METRICS_STATUS={}", report.runtime_metrics_status),
        format!("run_id: `{}`", if report.metadata.run_id.is_empty() { "-" } else { &report.metadata.run_id }),
        format!("git_branch: `{}`", report.metadata.git_branch), format!("git_commit: `{}`", report.metadata.git_commit),
        format!("git_dirty: `{}`", report.metadata.git_dirty), "".into(), "## Model Matrix".into(), "".into()];
    lines.extend(report.model_matrix.iter().map(|row| format!("- `{row}`")));
    lines.extend(["".into(), "## Runtime Metrics".into(), "".into()]);
    if report.runtime_metrics.is_empty() {
        lines.push("- `missing`: no role runtime metric JSONL was provided".into());
    } else {
        for (id, summary) in &report.runtime_metrics {
            lines.push(format!("- `{id}`: `{{'calls': {}, 'tokens': {}, 'latency_ms': {}, 'retries': {}, 'parent_interventions': {}, 'format_violations': {}, 'output_used': {}}}`", summary.calls, summary.tokens, summary.latency_ms, summary.retries, summary.parent_interventions, summary.format_violations, summary.output_used));
        }
    }
    lines.extend(["".into(), "## Findings".into(), "".into()]);
    if report.findings.is_empty() {
        lines.push("- none".into());
    } else {
        lines.extend(
            report
                .findings
                .iter()
                .map(|finding| format!("- `{}`", finding.line())),
        );
    }
    Ok(lines.join("\n") + "\n")
}

pub(super) fn write_report(
    boundary: &RuntimeArtifactBoundary,
    path: &Path,
    report: &EvalReport,
) -> Result<PathBuf, String> {
    let mut path = boundary.resolve(path)?;
    if path.exists() {
        let stem = path.file_stem().unwrap_or_default().to_string_lossy();
        let suffix = path
            .extension()
            .map(|suffix| format!(".{}", suffix.to_string_lossy()))
            .unwrap_or_default();
        path.set_file_name(format!("{stem}-{}{suffix}", report.metadata.eval_run_id));
    }
    boundary.atomic_write_text(&path, &markdown(report)?, 0o600)
}

pub(super) fn pretty(value: &Value) -> Result<String, String> {
    let serialized = serde_json::to_string(value).map_err(|error| error.to_string())?;
    let parsed = crate::python_json::parse_json(&serialized)?;
    String::from_utf8(crate::python_json::python_json_pretty_ascii_bytes(&parsed)?)
        .map_err(|error| error.to_string())
}
