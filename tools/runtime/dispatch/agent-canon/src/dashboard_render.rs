// @dependency-start
// contract implementation
// responsibility Renders the existing full and compact runtime dashboard summaries as Markdown.
// upstream implementation agent_runtime_dashboard.rs owns evidence collection and problem/action decisions
// downstream test ../../../../../tests/agent_tools/test_generate_agent_runtime_dashboard.py preserves reader-facing report contracts
// @dependency-end

use rustpython_ast::bigint::BigInt;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

fn at<'a>(value: &'a Value, path: &str) -> &'a Value {
    path.split('.')
        .fold(value, |value, key| value.get(key).unwrap_or(&Value::Null))
}
fn text(value: &Value) -> String {
    match value {
        Value::String(value) => value.clone(),
        Value::Null => "none".into(),
        _ => value.to_string(),
    }
}
fn value(summary: &Value, path: &str) -> String {
    text(at(summary, path))
}
fn list(value: &Value) -> &[Value] {
    value.as_array().map(Vec::as_slice).unwrap_or(&[])
}
fn integer(value: &Value) -> BigInt {
    crate::python_cli_integer::parse(&text(value)).unwrap_or_default()
}
fn count(value: &Value) -> usize {
    list(value).len()
}
fn cell(value: &str) -> String {
    format!("`{}`", value.replace('|', "/"))
}
fn row(values: impl IntoIterator<Item = String>) -> String {
    format!(
        "| {} |",
        values
            .into_iter()
            .map(|value| cell(&value))
            .collect::<Vec<_>>()
            .join(" | ")
    )
}
fn metric(lines: &mut Vec<String>, name: &str, value: impl ToString) {
    lines.push(row([name.to_owned(), value.to_string()]));
}
fn heading(lines: &mut Vec<String>, title: &str) {
    lines.extend([format!("## {title}"), String::new()]);
}
fn subheading(lines: &mut Vec<String>, title: &str) {
    lines.extend([format!("### {title}"), String::new()]);
}
fn relative(path: &str, root: &str) -> String {
    Path::new(path).strip_prefix(root).map_or_else(
        |_| path.replace('\\', "/"),
        |value| value.to_string_lossy().replace('\\', "/"),
    )
}
fn rate(failed: &BigInt, total: &BigInt) -> String {
    if total <= &BigInt::from(0) {
        "unknown".into()
    } else {
        crate::python_cli_integer::true_divide(failed, total).map_or_else(
            |_| "unknown".into(),
            |value| format!("{:.1}%", value * 100.0),
        )
    }
}
fn average(values: &[Value], digits: usize) -> String {
    if values.is_empty() {
        return "unknown".into();
    }
    let sum = values.iter().filter_map(Value::as_f64).sum::<f64>() / values.len() as f64;
    format!("{sum:.digits$}")
}
fn mean(values: &[Value]) -> String {
    if values.is_empty() {
        return "unknown".into();
    }
    let sum: BigInt = values.iter().map(integer).sum();
    crate::python_cli_integer::true_divide(&sum, &BigInt::from(values.len())).map_or_else(
        |_| "unknown".into(),
        |value| format!("{:.0}", value.round_ties_even()),
    )
}
fn recent(values: &[Value]) -> Vec<Value> {
    values[values.len().saturating_sub(8)..]
        .iter()
        .map(|value| value["value"].clone())
        .collect()
}

fn counters(summary: &Value, path: &str, limit: usize) -> Vec<(String, Value)> {
    if let Some(ordered) = at(summary, "counter_rows")
        .get(path)
        .and_then(Value::as_array)
    {
        return ordered
            .iter()
            .take(limit)
            .map(|item| (text(&item[0]), item[1].clone()))
            .collect();
    }
    let mut values = at(summary, path)
        .as_object()
        .map(|object| {
            object
                .iter()
                .map(|(name, value)| (name.clone(), value.clone()))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    values.sort_by(|left, right| {
        integer(&right.1)
            .cmp(&integer(&left.1))
            .then_with(|| left.0.cmp(&right.0))
    });
    values.truncate(limit);
    values
}
fn compact_counter(summary: &Value, path: &str) -> String {
    let values = counters(summary, path, 8);
    if values.is_empty() {
        "none".into()
    } else {
        values
            .iter()
            .map(|(name, value)| format!("{name}={}", text(value)))
            .collect::<Vec<_>>()
            .join(", ")
    }
}
fn counter_table(lines: &mut Vec<String>, summary: &Value, path: &str) {
    let values = counters(summary, path, 20);
    if values.is_empty() {
        lines.push("| `_none` | `0` |".into());
    }
    for (name, value) in values {
        lines.push(row([name, text(&value)]));
    }
}
fn reset(row: &Value) -> String {
    if row["reset_path"] == "untracked-or-unknown" {
        return "untracked-or-unknown".into();
    }
    format!(
        "{} {} {}",
        text(&row["reset_at"]),
        text(&row["reset_commit"]),
        text(&row["reset_path"])
    )
}
fn selection_rows(summary: &Value) -> &[Value] {
    list(at(summary, "selection_metrics_breakdown.metrics"))
}
fn selection_total(summary: &Value, field: &str, responsibility: Option<&str>) -> BigInt {
    selection_rows(summary)
        .iter()
        .filter(|row| responsibility.is_none_or(|name| row["responsibility"] == name))
        .map(|row| integer(&row[field]))
        .sum()
}
fn family<'a>(summary: &'a Value, name: &str) -> &'a Value {
    list(&summary["result_families"])
        .iter()
        .find(|row| row["family"] == name)
        .unwrap_or(&Value::Null)
}

pub(crate) fn machine_summary_lines(summary: &Value) -> Vec<String> {
    let mut lines = vec!["AGENT_RUNTIME_DASHBOARD_STATUS=pass".into()];
    let mut add =
        |name: &str, value: String| lines.push(format!("AGENT_RUNTIME_DASHBOARD_{name}={value}"));
    add("EVIDENCE_ROOT", value(summary, "root"));
    add(
        "RECENT_DAYS",
        if summary["recent_days"].is_null() {
            "all".into()
        } else {
            text(&summary["recent_days"])
        },
    );
    add("HOOK_FILES", count(&summary["hook_files"]).to_string());
    add("HOOK_ENTRIES", value(summary, "hook_entries"));
    add(
        "WORKFLOW_SELECTION_REPORTS",
        count(&family(summary, "workflow-selection")["reports"]).to_string(),
    );
    add(
        "CODEX_AGENT_ROLE_REPORTS",
        count(&family(summary, "codex-agent-role")["reports"]).to_string(),
    );
    for (name, path) in [
        (
            "HOOK_WORKFLOW_ATTRIBUTED",
            "hook_workflow_breakdown.entries_with_workflow",
        ),
        (
            "HOOK_WORKFLOW_MISSING",
            "hook_workflow_breakdown.entries_without_workflow",
        ),
        (
            "HOOK_WORKFLOW_CONTEXT_ATTRIBUTED",
            "hook_workflow_breakdown.context_attributed_entries",
        ),
        (
            "TOKEN_COMPARISONS",
            "token_usage_breakdown.comparison_count",
        ),
        ("TOKEN_SUMMARIES", "token_usage_breakdown.summary_count"),
        (
            "TOKEN_OBJECTIVE_SELECTED",
            "token_usage_breakdown.objective_selected",
        ),
        (
            "TOKEN_SUMMARY_SESSIONS",
            "token_usage_breakdown.session_count",
        ),
        (
            "TOKEN_SUMMARY_EVENTS",
            "token_usage_breakdown.token_event_count",
        ),
        ("PROMPT_ENTRIES", "prompt_tool_breakdown.prompt_entries"),
        (
            "TOOL_SELECTION_ENTRIES",
            "prompt_tool_breakdown.tool_selection_entries",
        ),
        (
            "REFERENCE_CAPTURE_ENTRIES",
            "reference_capture_breakdown.entries",
        ),
        (
            "REFERENCE_URL_OBSERVATIONS",
            "reference_capture_breakdown.url_observations",
        ),
        (
            "REFERENCE_MISSING_URLS",
            "reference_capture_breakdown.missing_url_observations",
        ),
        (
            "REFERENCE_BLOCKED_ENTRIES",
            "reference_capture_breakdown.blocked_entries",
        ),
    ] {
        add(name, value(summary, path));
    }
    add("SELECTION_ITEMS", selection_rows(summary).len().to_string());
    for (name, field) in [
        ("SELECTED", "selected_count"),
        ("CANDIDATES", "candidate_count"),
        ("MISSES", "missed_count"),
    ] {
        add(
            &format!("SELECTION_{name}"),
            selection_total(summary, field, None).to_string(),
        );
    }
    for responsibility in ["skill", "workflow", "tool"] {
        add(
            &format!("{}_SELECTION_MISS_RATE", responsibility.to_uppercase()),
            rate(
                &selection_total(summary, "missed_count", Some(responsibility)),
                &selection_total(summary, "candidate_count", Some(responsibility)),
            ),
        );
    }
    add(
        "MARKDOWN_HOOK_SIGNALS",
        (integer(at(
            summary,
            "markdown_docs_breakdown.candidate_skill_entries",
        )) + integer(at(
            summary,
            "markdown_docs_breakdown.candidate_tool_entries",
        )))
        .to_string(),
    );
    add(
        "PROBLEM_COMPONENTS",
        count(&summary["problem_components"]).to_string(),
    );
    add("NEXT_ACTIONS", count(&summary["next_actions"]).to_string());
    add(
        "BLOCKING_NEXT_ACTIONS",
        list(&summary["next_actions"])
            .iter()
            .filter(|action| action["priority"] == "P0" || action["priority"] == "P1")
            .count()
            .to_string(),
    );
    add(
        "GITHUB_ISSUE_REFS",
        count(at(summary, "evidence.github_issue_refs")).to_string(),
    );
    add(
        "ISSUE_PUBLICATION_RECEIPTS",
        count(&summary["issue_publication_receipts"]).to_string(),
    );
    let mut actions = BTreeMap::<String, usize>::new();
    for receipt in list(&summary["issue_publication_receipts"]) {
        *actions.entry(text(&receipt["action"])).or_default() += 1;
    }
    add(
        "ISSUE_PUBLICATION_ACTIONS",
        if actions.is_empty() {
            "none".into()
        } else {
            actions
                .iter()
                .map(|(key, value)| format!("{key}={value}"))
                .collect::<Vec<_>>()
                .join(", ")
        },
    );
    for (name, status) in [
        ("QUALIFIED", "qualified"),
        ("HANDOFFS", "handoff"),
        ("NO_ACTION", "no-action"),
    ] {
        add(
            &format!("ISSUE_WORKER_{name}"),
            list(&summary["issue_worker_handoffs"])
                .iter()
                .filter(|value| value["status"] == status)
                .count()
                .to_string(),
        );
    }
    add(
        "ISSUE_WORKER_ROUTEABLE",
        list(&summary["issue_worker_handoffs"])
            .iter()
            .filter(|value| value["can_route"] == true || value["status"] == "qualified")
            .count()
            .to_string(),
    );
    lines
}

fn components(lines: &mut Vec<String>, summary: &Value, compact: bool) {
    lines.extend(if compact {
        vec![
            "| type | component | status | problem | evidence |".into(),
            "| --- | --- | --- | --- | --- |".into(),
        ]
    } else {
        vec![
            "| type | component | status | what is wrong | evidence | next action |".into(),
            "| --- | --- | --- | --- | --- | --- |".into(),
        ]
    });
    let values = list(&summary["problem_components"]);
    if values.is_empty() {
        lines.push(if compact {"| `none` | `none` | `healthy` | `no problem components detected` | `dashboard` |"}else{"| `none` | `none` | `healthy` | `no problem components detected` | `dashboard` | `none` |"}.into());
    }
    for item in values.iter().take(if compact { 8 } else { usize::MAX }) {
        let mut cells = ["component_type", "name", "status", "problem", "evidence"]
            .iter()
            .map(|key| text(&item[*key]))
            .collect::<Vec<_>>();
        if item["component_type"].is_null() {
            cells[0] = text(&item["type"]);
            cells[1] = text(&item["component"]);
        }
        if !compact {
            cells.push(text(&item["next_action"]));
        }
        lines.push(row(cells));
    }
}
fn actions(lines: &mut Vec<String>, summary: &Value, compact: bool) {
    lines.extend(if compact { vec!["| priority | action | reason | evidence | owner surface | command |".into(),"| --- | --- | --- | --- | --- | --- |".into()] } else {vec!["| priority | action | reason | evidence | owner surface | command | done condition | issue | automation |".into(),"| --- | --- | --- | --- | --- | --- | --- | --- | --- |".into()]});
    let values = list(&summary["next_actions"]);
    if values.is_empty() {
        lines.push(if compact {"| `none` | no immediate dashboard action | all observed dashboard signals are healthy | `dashboard` | `none` | `none` |"}else{"| `none` | no immediate dashboard action | all observed dashboard signals are healthy | `dashboard` | `none` | `none` | `next_action_count=0` | `none` | `none` |"}.into());
    }
    for item in values.iter().take(if compact { 8 } else { usize::MAX }) {
        let mut cells = [
            "priority",
            "action",
            "reason",
            "evidence",
            "owner_surface",
            "command",
        ]
        .iter()
        .map(|key| text(&item[*key]))
        .collect::<Vec<_>>();
        if !compact {
            for key in ["done_condition", "issue", "automation"] {
                cells.push(text(&item[key]));
            }
        }
        lines.push(row(cells));
    }
}
fn selection(lines: &mut Vec<String>, summary: &Value, compact: bool) {
    if compact {
        lines.extend([
            "| responsibility | name | selected | candidate | missed | miss rate | reset basis |"
                .into(),
            "| --- | --- | --- | --- | --- | --- | --- |".into(),
        ]);
    } else {
        lines.extend([
            "| responsibility | item | selected | candidates | missed | miss rate | reset window |"
                .into(),
            "| --- | --- | ---: | ---: | ---: | ---: | --- |".into(),
        ]);
    }
    let mut values = selection_rows(summary)
        .iter()
        .filter(|value| !compact || integer(&value["missed_count"]) > BigInt::from(0))
        .collect::<Vec<_>>();
    if compact {
        values.sort_by(|a, b| {
            integer(&b["missed_count"])
                .cmp(&integer(&a["missed_count"]))
                .then_with(|| text(&a["responsibility"]).cmp(&text(&b["responsibility"])))
                .then_with(|| text(&a["name"]).cmp(&text(&b["name"])))
        });
        values.truncate(8);
    }
    if values.is_empty() {
        lines.push(
            if compact {
                "| `none` | `none` | `0` | `0` | `0` | `0.0%` | `none` |"
            } else {
                "| `_none` | `_none` | `0` | `0` | `0` | `unknown` | `_none` |"
            }
            .into(),
        );
    }
    for item in values {
        lines.push(row([
            text(&item["responsibility"]),
            text(&item["name"]),
            text(&item["selected_count"]),
            text(&item["candidate_count"]),
            text(&item["missed_count"]),
            rate(
                &integer(&item["missed_count"]),
                &integer(&item["candidate_count"]),
            ),
            reset(item),
        ]));
    }
}

fn token_lines(lines: &mut Vec<String>, summary: &Value, compact: bool) {
    let token = &summary["token_usage_breakdown"];
    let present =
        integer(&token["comparison_count"]) + integer(&token["summary_count"]) > BigInt::from(0);
    if compact {
        lines.extend(["| metric | value |".into(), "| --- | --- |".into()]);
    } else {
        let status = if token["objective_selected"] != true {
            "not-selected"
        } else if present {
            "present"
        } else {
            "missing"
        };
        lines.push(format!("- token_comparison_status: `{status}`"));
        lines.push(format!(
            "- token_objective_status: `{}`",
            if token["objective_selected"] == true {
                "selected"
            } else {
                "not-selected"
            }
        ));
        if token["objective_selected"] != true {
            lines.push(format!(
                "- token_evidence_status: `{}`",
                if present { "present" } else { "missing" }
            ));
            lines.push("- token_comparison_reason: `token-reduction objective was not selected; no reduction claim is made`".into());
            return;
        }
        if !present {
            lines.push("- token_comparison_reason: `token-reduction objective selected but no token footprint comparison evidence found`".into());
            return;
        }
    }
    for (label, key) in [
        ("comparison_count", "comparison_count"),
        ("summary_count", "summary_count"),
        ("baseline_total_tokens", "baseline_total_tokens"),
        ("candidate_total_tokens", "candidate_total_tokens"),
        ("summary_session_count", "session_count"),
        ("summary_token_event_count", "token_event_count"),
        ("summary_total_tokens", "total_tokens"),
    ] {
        if compact {
            metric(lines, label, text(&token[key]));
        } else {
            lines.push(format!(
                "- {}: `{}`",
                match label {
                    "comparison_count" => "token_comparison_count",
                    "summary_count" => "token_summary_count",
                    "summary_session_count" => "token_summary_session_count",
                    "summary_token_event_count" => "token_summary_event_count",
                    "summary_total_tokens" => "token_summary_total_tokens",
                    other => other,
                },
                text(&token[key])
            ));
        }
    }
    let ratio = average(list(&token["token_ratios"]), 3);
    if compact {
        metric(lines, "average_token_ratio", ratio);
    } else {
        lines.push(format!("- average_token_ratio: `{ratio}`"));
    }
    for (label, key) in [
        (
            "latest_moving_average_total_tokens",
            "latest_moving_average_total",
        ),
        ("average_tokens_per_event", "average_tokens_per_event"),
    ] {
        let value = format!("{:.3}", token[key].as_f64().unwrap_or(0.0));
        if compact {
            metric(lines, label, value)
        } else {
            lines.push(format!("- {label}: `{value}`"));
        }
    }
    let files = list(&token["comparison_files"])
        .iter()
        .chain(list(&token["summary_files"]))
        .map(text)
        .collect::<BTreeSet<_>>();
    if compact {
        metric(lines, "evidence_files", files.len());
    } else {
        lines.extend([String::new(), "| evidence file |".into(), "| --- |".into()]);
        for path in files.into_iter().take(20) {
            lines.push(row([relative(&path, &value(summary, "root"))]));
        }
    }
}

fn trend(lines: &mut Vec<String>, summary: &Value) {
    let prompt = &summary["prompt_tool_breakdown"];
    let token = &summary["token_usage_breakdown"];
    let p = list(&prompt["timed_prompt_char_counts"]);
    let t = list(&token["timed_token_ratios"]);
    let joint = if p.is_empty() && t.is_empty() {
        "missing_prompt_and_token_observations"
    } else if p.is_empty() {
        "missing_prompt_observations"
    } else if t.is_empty() {
        "missing_token_observations"
    } else if p.len() < 8 || t.len() < 8 {
        "limited_joint_window"
    } else {
        "ready"
    };
    lines.extend(["| metric | value |".into(), "| --- | --- |".into()]);
    for (key, value) in [
        ("rolling_window_observations", "8".into()),
        ("prompt_calls", text(&prompt["prompt_entries"])),
        (
            "prompt_chars_per_call_all",
            mean(list(&prompt["prompt_char_counts"])),
        ),
        ("prompt_chars_per_call_recent", mean(&recent(p))),
        ("token_comparisons", text(&token["comparison_count"])),
        ("token_ratio_all", average(list(&token["token_ratios"]), 3)),
        ("token_ratio_recent", average(&recent(t), 3)),
        (
            "candidate_tokens_per_comparison_all",
            mean(list(&token["candidate_token_counts"])),
        ),
        (
            "candidate_tokens_per_comparison_recent",
            mean(&recent(list(&token["timed_candidate_token_counts"]))),
        ),
        ("prompt_timed_observations", p.len().to_string()),
        ("token_timed_observations", t.len().to_string()),
        ("joint_trend_status", joint.into()),
    ] {
        metric(lines, key, value);
    }
}

fn counter_section(lines: &mut Vec<String>, summary: &Value, title: &str, path: &str, first: &str) {
    subheading(lines, title);
    lines.extend([format!("| {first} | entries |"), "| --- | ---: |".into()]);
    counter_table(lines, summary, path);
    lines.push(String::new());
}
fn scalar_bullets(lines: &mut Vec<String>, object: &Value, fields: &[(&str, &str)]) {
    for (label, key) in fields {
        lines.push(format!("- {label}: `{}`", text(&object[*key])));
    }
}
fn workflow(lines: &mut Vec<String>, summary: &Value) {
    scalar_bullets(
        lines,
        &summary["hook_workflow_breakdown"],
        &[
            (
                "hook_entries_with_workflow_attribution",
                "entries_with_workflow",
            ),
            (
                "hook_entries_missing_workflow_attribution",
                "entries_without_workflow",
            ),
            (
                "hook_entries_context_attributed",
                "context_attributed_entries",
            ),
        ],
    );
    lines.push(format!(
        "- workflow_attribution: `{}`",
        compact_counter(summary, "hook_workflow_breakdown.workflow_attribution")
    ));
    lines.extend([
        String::new(),
        "| workflow | hook entries |".into(),
        "| --- | ---: |".into(),
    ]);
    counter_table(lines, summary, "hook_workflow_breakdown.workflows");
    lines.push(String::new());
    counter_section(
        lines,
        summary,
        "Workflow Hook Events",
        "hook_workflow_breakdown.workflow_events",
        "workflow@event",
    );
    counter_section(
        lines,
        summary,
        "Missing Workflow Attribution By Hook File",
        "hook_workflow_breakdown.missing_workflow_by_file",
        "hook file",
    );
}

fn prompt(lines: &mut Vec<String>, summary: &Value) {
    scalar_bullets(
        lines,
        &summary["prompt_tool_breakdown"],
        &[
            ("prompt_entries", "prompt_entries"),
            ("prompt_excerpt_entries", "prompt_excerpt_entries"),
            (
                "prompt_missing_excerpt_entries",
                "prompt_missing_excerpt_entries",
            ),
            ("prompt_total_chars", "prompt_total_chars"),
            ("tool_selection_entries", "tool_selection_entries"),
        ],
    );
    lines.push(String::new());
    counter_section(
        lines,
        summary,
        "Tool Selection Counts",
        "prompt_tool_breakdown.tools",
        "tool",
    );
    counter_section(
        lines,
        summary,
        "Tool Command Verbs",
        "prompt_tool_breakdown.command_verbs",
        "command verb",
    );
    counter_section(
        lines,
        summary,
        "Selected Repo Tools",
        "prompt_tool_breakdown.selected_tools",
        "repo tool",
    );
}
fn markdown(lines: &mut Vec<String>, summary: &Value) {
    let data = &summary["markdown_docs_breakdown"];
    let present = integer(&data["candidate_skill_entries"])
        + integer(&data["candidate_tool_entries"])
        > BigInt::from(0);
    lines.push(format!(
        "- markdown_hook_signal_status: `{}`",
        if present { "present" } else { "missing" }
    ));
    lines.push(format!(
        "- markdown_hook_signal_reason: `{}`",
        if present {
            "Markdown/docs prompt or tool signals are present in hook JSONL."
        } else {
            "No Markdown/docs candidate skill or docs-tool signal is present in hook JSONL yet."
        }
    ));
    scalar_bullets(
        lines,
        data,
        &[
            (
                "markdown_candidate_skill_entries",
                "candidate_skill_entries",
            ),
            ("markdown_candidate_tool_entries", "candidate_tool_entries"),
        ],
    );
    lines.push(String::new());
    counter_section(
        lines,
        summary,
        "Markdown Docs Candidate Tools",
        "markdown_docs_breakdown.candidate_tools",
        "tool",
    );
}
fn references(lines: &mut Vec<String>, summary: &Value) {
    let data = &summary["reference_capture_breakdown"];
    let present = integer(&data["entries"]) > BigInt::from(0);
    lines.push(format!(
        "- reference_capture_status: `{}`",
        if present { "present" } else { "missing" }
    ));
    lines.push(format!("- reference_capture_reason: `{}`",if present{"Reference-capture hook entries are present in accumulated hook JSONL."}else{"No reference-capture hook entries are present yet; consulted external sources may be invisible to later prompt improvement."}));
    scalar_bullets(
        lines,
        data,
        &[
            ("reference_capture_entries", "entries"),
            ("reference_url_observations", "url_observations"),
            (
                "reference_registered_url_observations",
                "registered_url_observations",
            ),
            (
                "reference_missing_url_observations",
                "missing_url_observations",
            ),
            ("reference_blocked_entries", "blocked_entries"),
        ],
    );
    lines.push(String::new());
    counter_section(
        lines,
        summary,
        "Reference Capture Events",
        "reference_capture_breakdown.events",
        "event",
    );
    counter_section(
        lines,
        summary,
        "Reference Capture Source Fields",
        "reference_capture_breakdown.source_fields",
        "source field",
    );
    subheading(lines, "Reference Capture URL Summary");
    lines.extend([
        "| url class | bounded summary |".into(),
        "| --- | --- |".into(),
    ]);
    for key in ["missing_urls", "registered_urls"] {
        lines.push(row([
            key.into(),
            compact_counter(summary, &format!("reference_capture_breakdown.{key}")),
        ]));
    }
}

fn issue_drilldown(lines: &mut Vec<String>, summary: &Value) {
    lines.extend(["| outcome | count |".into(), "| --- | ---: |".into()]);
    for status in ["qualified", "handoff", "no-action"] {
        metric(
            lines,
            status,
            list(&summary["issue_worker_handoffs"])
                .iter()
                .filter(|value| value["status"] == status)
                .count(),
        );
    }
    lines.extend([
        String::new(),
        "| publication metric | value |".into(),
        "| --- | --- |".into(),
    ]);
    metric(
        lines,
        "published_receipts",
        count(&summary["issue_publication_receipts"]),
    );
    let refs = list(&summary["issue_publication_receipts"])
        .iter()
        .map(|value| text(&value["url"]))
        .collect::<Vec<_>>();
    metric(
        lines,
        "github_issue_refs",
        if refs.is_empty() {
            "none".into()
        } else {
            refs.join(", ")
        },
    );
    let mut actions = BTreeMap::<String, usize>::new();
    for item in list(&summary["issue_publication_receipts"]) {
        *actions.entry(text(&item["action"])).or_default() += 1;
    }
    metric(
        lines,
        "issue_publication_action_counts",
        if actions.is_empty() {
            "none".into()
        } else {
            actions
                .iter()
                .map(|(name, count)| format!("{name}={count}"))
                .collect::<Vec<_>>()
                .join(", ")
        },
    );
}
fn mapping_summary(summary: &Value, value: &Value, path: &str, nested: bool) -> String {
    let Some(object) = value.as_object().filter(|object| !object.is_empty()) else {
        return "none".into();
    };
    let values = object
        .iter()
        .take(8)
        .map(|(name, value)| {
            if nested {
                format!(
                    "{name}:({})",
                    mapping_summary(summary, value, &format!("{path}.{name}"), false)
                )
            } else {
                let ordered = counters(summary, path, 8);
                if ordered.is_empty() {
                    format!("{name}={}", text(value))
                } else {
                    ordered
                        .iter()
                        .map(|(key, count)| format!("{key}={}", text(count)))
                        .collect::<Vec<_>>()
                        .join(", ")
                }
            }
        })
        .collect::<Vec<_>>();
    if values.is_empty() {
        "none".into()
    } else {
        values.join(", ")
    }
}
fn drilldown(lines: &mut Vec<String>, summary: &Value) {
    subheading(lines, "Hook Failure Drilldown");
    lines.extend([
        "| fingerprint | status | failed entries | top namespaces | top events | top tools |"
            .into(),
        "| --- | --- | ---: | --- | --- | --- |".into(),
    ]);
    let failure = &summary["hook_failure_drilldown"];
    if failure.is_null() || failure["fingerprint"] == "none" {
        lines.push("| `none` | `healthy` | `0` | `none` | `none` | `none` |".into());
    } else {
        lines.push(row([
            text(&failure["fingerprint"]),
            "fail".into(),
            text(&failure["count"]),
            compact_counter(summary, "hook_failure_drilldown.namespaces"),
            compact_counter(summary, "hook_failure_drilldown.events"),
            compact_counter(summary, "hook_failure_drilldown.tools"),
        ]));
    }
    lines.push(String::new());
    subheading(lines, "Workflow Attribution Drilldown");
    lines.extend(["| metric | value |".into(), "| --- | --- |".into()]);
    for (label, key) in [
        ("entries_with_workflow", "entries_with_workflow"),
        ("entries_missing_workflow", "entries_without_workflow"),
        ("entries_context_attributed", "context_attributed_entries"),
    ] {
        metric(lines, label, text(&summary["hook_workflow_breakdown"][key]));
    }
    for (label, key) in [
        ("workflow_attribution", "workflow_attribution"),
        ("missing_events", "missing_workflow_events"),
        ("missing_namespaces", "missing_workflow_namespaces"),
        ("missing_statuses", "missing_workflow_statuses"),
        ("missing_tools", "missing_workflow_tools"),
    ] {
        metric(
            lines,
            label,
            compact_counter(summary, &format!("hook_workflow_breakdown.{key}")),
        );
    }
    metric(
        lines,
        "unknown_event_count",
        text(&summary["hook_schema"]["unknown_event_count"]),
    );
    for key in [
        "namespace_debt_by_hook_family",
        "status_by_hook_family",
        "failure_by_hook_family",
        "skip_by_hook_family",
    ] {
        let path = format!("hook_schema.{key}");
        metric(
            lines,
            key,
            mapping_summary(
                summary,
                &summary["hook_schema"][key],
                &path,
                key != "namespace_debt_by_hook_family",
            ),
        );
    }
    let oop = &summary["hook_schema"]["oop_applicability"];
    metric(
        lines,
        "oop_applicability",
        format!(
            "applicable={}, not_applicable={}, missing_reason={}",
            text(&oop["applicable_count"]),
            text(&oop["not_applicable_count"]),
            text(&oop["missing_reason_count"])
        ),
    );
    lines.push(String::new());
    subheading(lines, "Selection Evidence Drilldown");
    lines.extend(["| metric | value |".into(), "| --- | ---: |".into()]);
    for (label, key) in [
        ("entries_seen", "entries_seen"),
        ("entries_with_candidates", "entries_with_candidates"),
        ("entries_with_confirmed_selection", "entries_with_selection"),
        (
            "filtered_observations_before_component_update",
            "filtered_observations",
        ),
    ] {
        metric(
            lines,
            label,
            text(&summary["selection_metrics_breakdown"][key]),
        );
    }
    for (label, key) in [
        ("total_selected", "selected_count"),
        ("total_candidates", "candidate_count"),
        ("total_misses", "missed_count"),
    ] {
        metric(lines, label, selection_total(summary, key, None));
    }
    lines.push(String::new());
    subheading(lines, "IssueWorker Routing Drilldown");
    issue_drilldown(lines, summary);
    lines.push(String::new());
    subheading(lines, "Markdown And Prompt Drilldown");
    lines.extend(["| metric | value |".into(), "| --- | --- |".into()]);
    for (label, path) in [
        (
            "markdown_candidate_skill_entries",
            "markdown_docs_breakdown.candidate_skill_entries",
        ),
        (
            "markdown_candidate_tool_entries",
            "markdown_docs_breakdown.candidate_tool_entries",
        ),
        ("prompt_entries", "prompt_tool_breakdown.prompt_entries"),
        (
            "prompt_excerpt_entries",
            "prompt_tool_breakdown.prompt_excerpt_entries",
        ),
        (
            "prompt_missing_excerpt_entries",
            "prompt_tool_breakdown.prompt_missing_excerpt_entries",
        ),
        (
            "prompt_total_chars",
            "prompt_tool_breakdown.prompt_total_chars",
        ),
        (
            "tool_selection_entries",
            "prompt_tool_breakdown.tool_selection_entries",
        ),
    ] {
        metric(lines, label, value(summary, path));
    }
    for (label, path) in [
        (
            "markdown_candidate_tools",
            "markdown_docs_breakdown.candidate_tools",
        ),
        ("top_tools", "prompt_tool_breakdown.tools"),
        ("top_command_verbs", "prompt_tool_breakdown.command_verbs"),
        (
            "top_selected_repo_tools",
            "prompt_tool_breakdown.selected_tools",
        ),
    ] {
        metric(lines, label, compact_counter(summary, path));
    }
    lines.push(String::new());
    subheading(lines, "Prompt Token Trend Drilldown");
    trend(lines, summary);
    lines.push(String::new());
    subheading(lines, "Token Consumption Drilldown");
    token_lines(lines, summary, true);
    lines.push(String::new());
    subheading(lines, "Reference Capture Drilldown");
    lines.extend(["| metric | value |".into(), "| --- | --- |".into()]);
    for key in [
        "entries",
        "url_observations",
        "registered_url_observations",
        "missing_url_observations",
        "blocked_entries",
    ] {
        metric(
            lines,
            key,
            text(&summary["reference_capture_breakdown"][key]),
        );
    }
    for key in ["events", "source_fields", "missing_urls", "registered_urls"] {
        metric(
            lines,
            key,
            compact_counter(summary, &format!("reference_capture_breakdown.{key}")),
        );
    }
}

fn compact(summary: &Value) -> String {
    let mut lines = vec!["# Agent Runtime Compact Summary".into(), String::new()];
    heading(&mut lines, "Machine Summary");
    lines.push("```text".into());
    lines.extend(machine_summary_lines(summary));
    lines.extend(["```".into(), String::new()]);
    heading(&mut lines, "Priority Problems");
    components(&mut lines, summary, true);
    lines.push(String::new());
    heading(&mut lines, "Priority Next Actions");
    actions(&mut lines, summary, true);
    lines.push(String::new());
    heading(&mut lines, "Selection Misses");
    selection(&mut lines, summary, true);
    lines.push(String::new());
    heading(&mut lines, "Evidence Drilldown");
    drilldown(&mut lines, summary);
    lines.push(String::new());
    heading(&mut lines, "Reading Rule");
    lines.extend(["- Use this compact summary as the default input for agent log analysis.","- Do not read raw JSONL during normal agent log analysis.","- If this summary lacks needed detail, extend or rerun the dashboard tool with a more specific generated summary instead of searching raw logs.","- Raw JSONL inspection is reserved for tool implementation, corruption audits, or schema debugging with an explicit rationale."].map(str::to_owned));
    lines.join("\n") + "\n"
}

fn python_counter(summary: &Value, path: &str) -> String {
    format!(
        "{{{}}}",
        counters(summary, path, usize::MAX)
            .iter()
            .map(|(name, value)| format!(
                "'{}': {}",
                name.replace('\\', "\\\\").replace('\'', "\\'"),
                text(value)
            ))
            .collect::<Vec<_>>()
            .join(", ")
    )
}
fn action_map(lines: &mut Vec<String>, summary: &Value) {
    lines.extend([
        "| signal | state | evidence | action when attention is needed |".into(),
        "| --- | --- | ---: | --- |".into(),
    ]);
    let nonzero = |path: &str| integer(at(summary, path)) > BigInt::from(0);
    let rows=[
        ("hook evidence",BigInt::from(count(&summary["hook_files"])),nonzero("evidence.hook_counts.statuses.fail"),"review failing hook namespaces first"),
        ("workflow hook attribution",integer(at(summary,"hook_workflow_breakdown.entries_with_workflow")),nonzero("hook_workflow_breakdown.entries_without_workflow"),"add workflow fields to hook logs when missing attribution is high"),
        ("token consumption",integer(at(summary,"token_usage_breakdown.comparison_count"))+integer(at(summary,"token_usage_breakdown.summary_count")),false,"record token_count comparisons or moving averages when token use drives workflow design"),
        ("prompt and tool selection",integer(at(summary,"prompt_tool_breakdown.prompt_entries"))+integer(at(summary,"prompt_tool_breakdown.tool_selection_entries")),!nonzero("prompt_tool_breakdown.prompt_entries")||!nonzero("prompt_tool_breakdown.tool_selection_entries")||nonzero("prompt_tool_breakdown.prompt_missing_excerpt_entries"),"add prompt/tool fields to hook logs if selection analysis is missing"),
        ("selection accuracy by responsibility",selection_total(summary,"candidate_count",None)+selection_total(summary,"selected_count",None),selection_total(summary,"missed_count",None)>BigInt::from(0),"repair routing or logging when candidate skills/workflows/tools are not selected"),
        ("Markdown/docs hook signals",integer(at(summary,"markdown_docs_breakdown.candidate_skill_entries"))+integer(at(summary,"markdown_docs_breakdown.candidate_tool_entries")),false,"add or inspect Markdown/docs hook measurements when markdown checks feel noisy"),
        ("reference capture",integer(at(summary,"reference_capture_breakdown.entries")),nonzero("reference_capture_breakdown.missing_url_observations"),"materialize consulted PDF/HTML sources under references/external and repair missing URL logging"),
    ];
    for (signal, evidence, attention, action) in rows {
        let status = if evidence == BigInt::from(0) {
            "missing"
        } else if attention {
            "attention"
        } else {
            "healthy"
        };
        lines.push(format!(
            "| {signal} | `{status}` | `{evidence}` | {action} |"
        ));
    }
    for (signal, name, action) in [
        (
            "workflow selection eval",
            "workflow-selection",
            "repair workflow routing examples or classifier rules",
        ),
        (
            "Codex role eval",
            "codex-agent-role",
            "repair subagent role TOML, model settings, routing, or runtime metric capture",
        ),
    ] {
        let data = family(summary, name);
        let evidence = count(&data["reports"]);
        let status = if evidence == 0 {
            "missing"
        } else if !list(&data["failed_reports"]).is_empty() {
            "attention"
        } else {
            "healthy"
        };
        lines.push(format!(
            "| {signal} | `{status}` | `{evidence}` | {action} |"
        ));
    }
    let evidence =
        count(at(summary, "evidence.github_issue_refs")) + count(&summary["issue_worker_handoffs"]);
    lines.push(format!("| durable issues | `{}` | `{evidence}` | route explicit IssueWorker candidates through the host publisher |",if evidence==0{"missing"}else if !list(&summary["issue_worker_handoffs"]).is_empty(){"attention"}else{"healthy"}));
}
fn visual(lines: &mut Vec<String>, summary: &Value) {
    lines.extend([
        "```mermaid".into(),
        "flowchart LR".into(),
        format!(
            "  Hooks[\"Hook JSONL<br/>files: {}<br/>entries: {}\"]",
            count(&summary["hook_files"]),
            value(summary, "hook_entries")
        ),
        format!(
            "  WorkflowHooks[\"Workflow hook attribution<br/>attributed: {}<br/>missing: {}\"]",
            value(summary, "hook_workflow_breakdown.entries_with_workflow"),
            value(summary, "hook_workflow_breakdown.entries_without_workflow")
        ),
        format!(
            "  Tokens[\"Token consumption<br/>comparisons: {}<br/>summaries: {}\"]",
            value(summary, "token_usage_breakdown.comparison_count"),
            value(summary, "token_usage_breakdown.summary_count")
        ),
        format!(
            "  PromptTools[\"Prompt + tool selection<br/>prompts: {}<br/>tools: {}\"]",
            value(summary, "prompt_tool_breakdown.prompt_entries"),
            value(summary, "prompt_tool_breakdown.tool_selection_entries")
        ),
        format!(
            "  Selection[\"Selection accuracy<br/>items: {}<br/>misses: {}\"]",
            selection_rows(summary).len(),
            selection_total(summary, "missed_count", None)
        ),
        format!(
            "  MarkdownDocs[\"Markdown/docs hook signals<br/>entries: {}\"]",
            integer(at(
                summary,
                "markdown_docs_breakdown.candidate_skill_entries"
            )) + integer(at(
                summary,
                "markdown_docs_breakdown.candidate_tool_entries"
            ))
        ),
        format!(
            "  ReferenceCapture[\"Reference capture<br/>urls: {}<br/>missing: {}\"]",
            value(summary, "reference_capture_breakdown.url_observations"),
            value(
                summary,
                "reference_capture_breakdown.missing_url_observations"
            )
        ),
        format!(
            "  WorkflowEval[\"Workflow selection evals<br/>reports: {}\"]",
            count(&family(summary, "workflow-selection")["reports"])
        ),
        format!(
            "  RoleEval[\"Codex role evals<br/>reports: {}\"]",
            count(&family(summary, "codex-agent-role")["reports"])
        ),
        format!(
            "  Issues[\"GitHub Issues<br/>refs: {}\"]",
            count(at(summary, "evidence.github_issue_refs"))
        ),
        "  Dashboard[\"Runtime dashboard<br/>read-only view\"]".into(),
        "  Guide[\"Improvement guide<br/>next repair targets\"]".into(),
        "  Reviewer[\"Human / PR reviewer<br/>summary + artifacts\"]".into(),
    ]);
    lines.extend(
        [
            "  Hooks --> Dashboard",
            "  Hooks --> WorkflowHooks",
            "  WorkflowHooks --> Dashboard",
            "  Tokens --> Dashboard",
            "  PromptTools --> Dashboard",
            "  Hooks --> Selection",
            "  PromptTools --> Selection",
            "  Selection --> Dashboard",
            "  PromptTools --> MarkdownDocs",
            "  MarkdownDocs --> Dashboard",
            "  Hooks --> ReferenceCapture",
            "  ReferenceCapture --> Dashboard",
            "  ReferenceCapture --> Guide",
            "  WorkflowEval --> Dashboard",
            "  RoleEval --> Dashboard",
            "  Issues --> Dashboard",
            "  Dashboard --> Reviewer",
            "  Dashboard --> Guide",
            "  Issues --> Guide",
            "```",
        ]
        .map(str::to_owned),
    );
}

fn full(summary: &Value) -> String {
    let root = value(summary, "root");
    let mut lines=vec!["# Agent Runtime Dashboard".into(),String::new(),"<!--".into(),"@dependency-start".into(),"responsibility Records generated read-only AgentCanon runtime evidence dashboard.".into(),"upstream implementation tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs generates this report".into(),"@dependency-end".into(),"-->".into(),String::new(),"This report is a read-only view over accumulated AgentCanon evidence.".into(),"It tells humans and PR reviewers where logs live and what signals have".into(),"been collected; it does not create GitHub Issues or rewrite skills,".into(),"workflows, tools, hooks, or private knowledge/feedback.".into(),String::new()];
    heading(&mut lines, "Machine Summary");
    lines.extend(machine_summary_lines(summary));
    lines.push(String::new());
    heading(&mut lines, "Problem Components");
    components(&mut lines, summary, false);
    lines.push(String::new());
    heading(&mut lines, "Next Actions");
    actions(&mut lines, summary, false);
    lines.push(String::new());
    heading(&mut lines, "Visual Evidence Map");
    visual(&mut lines, summary);
    lines.push(String::new());
    heading(&mut lines, "Action Map");
    action_map(&mut lines, summary);
    lines.push(String::new());
    heading(&mut lines, "Issue Routing");
    lines.extend([
        "| signal | durable issue | route reason |".into(),
        "| --- | --- | --- |".into(),
    ]);
    for (signal,slug,reason) in [("mcp preflight scope","mcp-inventory-preflight-cache","use Rust policy/cache commands for GitHub-only read versus local repo task boundaries"),("eval evidence gaps","eval-accumulation-gaps","repair missing workflow attribution, prompt capture, or token comparison evidence"),("GitHub Issue authority","github-issue-authority","resolve repository-qualified GitHub Issues through the host adapter; never mirror local issue files")] {
        if signal=="eval evidence gaps"&&list(&summary["problem_components"]).is_empty(){continue;}
        let issue=list(at(summary,"evidence.github_issue_refs")).iter().filter_map(Value::as_str).find(|value|value.contains(slug)).unwrap_or("missing-local-issue");lines.push(format!("| `{signal}` | `{issue}` | {reason} |"));
    }
    lines.push(String::new());
    heading(&mut lines, "Where Logs Accumulate");
    lines.push(format!("- evidence_root: `{root}`"));
    lines.extend([
        "- hook_jsonl_archive_mount: `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl`",
        "- hook_jsonl_archive_remote: `git@github.com:iwashita-nozomu/agent-canon-log.git`",
        "- agent_report_archive_index: `.agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl`",
        "- agent_report_archive_command: `python3 tools/runtime/archive/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>`",
        "- workflow_selection_eval_reports: `.agent-canon/log-archive/eval-results/workflow-selection/<eval-run-id>-<status>.md`",
        "- github_issue_refs: repository-qualified URLs from private run-local packets; otherwise `github_issue_lookup_required`",
        "- private_knowledge: `agent-canon-log/knowledge/topics/*/candidate.md` (on-demand; locator/count only)",
        "- token_comparison_reports: `reports/agents/**/workflow_monitoring.md` or `reports/agents/**/*token*.md`",
        "- reference_capture_hook: `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/reference_capture_guard.jsonl`",
        "- materialized_references: `references/external/*.md` in the parent repository that consulted the source",
        "- github_actions_dashboard: AgentCanon repository Step Summary plus uploaded artifact under `reports/agent-runtime-dashboard/` during the run"].map(str::to_owned));
    lines.push(String::new());
    heading(&mut lines, "Accumulated Result Families");
    lines.extend([
        "| family | path | reports | failed | status counts |".into(),
        "| --- | --- | ---: | ---: | --- |".into(),
    ]);
    for item in list(&summary["result_families"]) {
        let counter_path = format!("result_families.{}.status_counts", text(&item["family"]));
        let statuses = format!(
            "{{{}}}",
            counters(summary, &counter_path, usize::MAX)
                .iter()
                .map(|(name, value)| format!("'{name}': {}", text(value)))
                .collect::<Vec<_>>()
                .join(", ")
        );
        lines.push(row([
            text(&item["family"]),
            relative(&text(&item["directory"]), &root),
            count(&item["reports"]).to_string(),
            count(&item["failed_reports"]).to_string(),
            statuses,
        ]));
    }
    lines.push(String::new());
    heading(&mut lines, "Source Sync State");
    if summary["source_sync_state"].is_null() {
        lines.extend(["| status | unavailable |".into(), "| --- | --- |".into()]);
    } else {
        lines.extend(["| field | value |".into(), "| --- | --- |".into()]);
        for key in [
            "status",
            "code",
            "source_head",
            "source_tree",
            "failure",
            "updated_at",
        ] {
            lines.push(row([key.into(), text(&summary["source_sync_state"][key])]));
        }
    }
    lines.push(String::new());
    heading(&mut lines, "Hook Workflow Attribution");
    lines.extend(["This section attributes hook entries to workflow fields present in hook JSONL.".into(),"Missing attribution means the hook log did not carry enough workflow context for mechanical analysis.".into(),String::new()]);
    workflow(&mut lines, summary);
    heading(&mut lines, "Token Consumption Evidence");
    token_lines(&mut lines, summary, false);
    lines.push(String::new());
    heading(&mut lines, "Selection Accuracy By Responsibility");
    lines.extend(["This section compares candidate skills, workflows, and tools against the same-entry selections recorded in hook JSONL.".into(),"Counts are filtered to hook entries after the component source path's latest Git commit when a source path can be resolved.".into(),"A tool miss means a candidate repo tool was not confirmed by `tool_name` or `tool_command_verb`; coarse Bash-only logs can therefore identify missing evidence rather than definite misuse.".into(),String::new()]);
    scalar_bullets(
        &mut lines,
        &summary["selection_metrics_breakdown"],
        &[
            ("selection_entries_seen", "entries_seen"),
            (
                "selection_entries_with_candidates",
                "entries_with_candidates",
            ),
            (
                "selection_entries_with_confirmed_selection",
                "entries_with_selection",
            ),
            (
                "selection_filtered_observations_before_component_update",
                "filtered_observations",
            ),
        ],
    );
    lines.push(String::new());
    selection(&mut lines, summary, false);
    lines.push(String::new());
    subheading(&mut lines, "Responsibility Totals");
    lines.extend([
        "| responsibility | selected | candidates | missed | miss rate |".into(),
        "| --- | ---: | ---: | ---: | ---: |".into(),
    ]);
    for responsibility in ["skill", "workflow", "tool"] {
        let selected = selection_total(summary, "selected_count", Some(responsibility));
        let candidates = selection_total(summary, "candidate_count", Some(responsibility));
        let missed = selection_total(summary, "missed_count", Some(responsibility));
        lines.push(row([
            responsibility.into(),
            selected.to_string(),
            candidates.to_string(),
            missed.to_string(),
            rate(&missed, &candidates),
        ]));
    }
    lines.push(String::new());
    heading(&mut lines, "Prompt And Tool Selection Evidence");
    prompt(&mut lines, summary);
    heading(&mut lines, "Markdown Docs Hook Signals");
    markdown(&mut lines, summary);
    heading(&mut lines, "Reference Capture Signals");
    references(&mut lines, summary);
    lines.push(String::new());
    heading(&mut lines, "Hook Summary");
    lines.extend([
        format!("- hook_jsonl_files: `{}`", count(&summary["hook_files"])),
        format!("- hook_jsonl_entries: `{}`", value(summary, "hook_entries")),
        format!(
            "- status_counts: `{}`",
            python_counter(summary, "evidence.hook_counts.statuses")
        ),
        format!(
            "- event_counts: `{}`",
            python_counter(summary, "evidence.hook_counts.events")
        ),
        String::new(),
    ]);
    for (title, path) in [
        ("Hook Runtime Namespaces", "namespaces"),
        ("Skill Usage", "skills"),
        ("Prompt Candidate Workflows", "candidate_workflows"),
        ("Prompt Candidate Tools", "candidate_tools"),
        ("Human Feedback Signals", "feedback_labels"),
        ("Hook Quality Counters", "quality"),
    ] {
        heading(&mut lines, title);
        let values = counters(summary, &format!("evidence.hook_counts.{path}"), 20);
        if values.is_empty() {
            lines.push("- none".into());
        }
        for (name, value) in values {
            lines.push(format!("- `{name}`: `{}`", text(&value)));
        }
        lines.push(String::new());
    }
    heading(&mut lines, "Failed Eval Reports");
    let failed = list(&summary["result_families"])
        .iter()
        .flat_map(|item| list(&item["failed_reports"]))
        .map(text)
        .collect::<BTreeSet<_>>();
    if failed.is_empty() {
        lines.push("- none".into());
    }
    for path in failed.into_iter().take(20) {
        lines.push(format!("- `{}`", relative(&path, &root)));
    }
    lines.join("\n") + "\n"
}

pub(crate) fn render(summary: &Value) -> Result<(String, String), String> {
    for key in [
        "root",
        "evidence",
        "hook_files",
        "hook_entries",
        "result_families",
        "hook_workflow_breakdown",
        "token_usage_breakdown",
        "prompt_tool_breakdown",
        "markdown_docs_breakdown",
        "reference_capture_breakdown",
        "selection_metrics_breakdown",
        "problem_components",
        "next_actions",
    ] {
        if summary.get(key).is_none() {
            return Err(format!("dashboard summary is missing {key}"));
        }
    }
    Ok((full(summary), compact(summary)))
}
