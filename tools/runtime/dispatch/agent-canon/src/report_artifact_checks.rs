// @dependency-start
// contract implementation
// responsibility Owns native report checks, status parsing, token fields, and run-bundle placement.
// upstream design ../../../../../documents/design/request-intent-and-update-relation.md run-bundle evidence contract
// upstream implementation ../../../../../tools/runtime/artifacts/report_artifact_checks.py owns shared Python report checks
// downstream implementation run_evaluation.rs scores selected run artifacts
// downstream implementation task_close.rs consumes report status and placement checks at task close
// downstream test ../tests/run_evaluation_native.rs establishes selected-file check behavior
// @dependency-end

use regex::Regex;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

const PLAN_SECTIONS: &[(&str, &str)] = &[
    ("## Stage Plan", "stage_plan"),
    ("## Clause Coverage", "clause_coverage"),
    ("## Planned Work Units", "planned_work_units"),
];

fn placeholder_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"(?s)<!--.*?-->").expect("fixed comment regex"))
}

fn approve_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?i)^(?:[-*]\s*)?(?:decision\s*:\s*)?approve\s*$")
            .expect("fixed approval regex")
    })
}

pub fn markdown_without_comments(text: &str) -> String {
    placeholder_pattern().replace_all(text, "").into_owned()
}

pub fn markdown_without_adjudicated_rejected_hypotheses(text: &str) -> String {
    let mut table_indexes: Option<(usize, usize, usize)> = None;
    let mut output = Vec::new();
    for line in text.lines() {
        let cells = pipe_cells(line);
        let normalized = cells
            .iter()
            .map(|cell| normalize_header(cell))
            .collect::<Vec<_>>();
        if let (Some(adjudication), Some(reason), Some(evidence)) = (
            normalized.iter().position(|cell| cell == "adjudication"),
            normalized.iter().position(|cell| cell == "reason_code"),
            normalized.iter().position(|cell| cell == "evidence_ref"),
        ) {
            table_indexes = Some((adjudication, reason, evidence));
            output.push(line);
            continue;
        }
        if cells.is_empty() || !line.trim_start().starts_with('|') {
            table_indexes = None;
            output.push(line);
            continue;
        }
        if let Some((adjudication_index, reason_index, evidence_index)) = table_indexes {
            let indexes = [adjudication_index, reason_index, evidence_index];
            if indexes.iter().all(|index| *index < cells.len()) {
                let adjudication = cells[adjudication_index].to_ascii_lowercase();
                let reason = cells[reason_index].to_ascii_lowercase();
                let evidence = cells[evidence_index].to_ascii_lowercase();
                if adjudication == "rejected"
                    && !is_review_placeholder(&reason)
                    && !is_review_placeholder(&evidence)
                {
                    continue;
                }
            }
        }
        output.push(line);
    }
    output.join("\n")
}

fn pipe_cells(line: &str) -> Vec<String> {
    let stripped = line.trim();
    if !stripped.starts_with('|') {
        return Vec::new();
    }
    let parts = stripped.split('|').collect::<Vec<_>>();
    if parts.len() < 3 {
        return Vec::new();
    }
    parts[1..parts.len() - 1]
        .iter()
        .map(|cell| cell.trim().to_string())
        .collect()
}

fn normalize_header(value: &str) -> String {
    let mut result = String::new();
    let mut separator = false;
    for character in value.to_ascii_lowercase().chars() {
        if character.is_ascii_alphanumeric() {
            if separator && !result.is_empty() {
                result.push('_');
            }
            separator = false;
            result.push(character);
        } else {
            separator = true;
        }
    }
    result
}

fn is_review_placeholder(value: &str) -> bool {
    matches!(
        value,
        "" | "-" | "—" | "none" | "null" | "n/a" | "na" | "missing" | "unknown" | "todo" | "tbd"
    )
}

pub fn section_has_content(text: &str, heading: &str) -> bool {
    let mut in_section = false;
    let mut body = Vec::new();
    for line in text.lines() {
        let stripped = crate::python_text::python_strip(line);
        if stripped.starts_with("## ") {
            if in_section {
                break;
            }
            in_section = stripped == heading;
            continue;
        }
        if in_section {
            body.push(line);
        }
    }
    if !in_section {
        return false;
    }
    markdown_without_comments(&body.join("\n"))
        .lines()
        .any(|line| !line.trim().is_empty())
}

pub fn bullet_rows<'a>(text: &'a str, heading: &str) -> Vec<&'a str> {
    let mut rows = Vec::new();
    let mut in_section = false;
    for line in text.lines() {
        let stripped = crate::python_text::python_strip(line);
        if stripped.starts_with("## ") {
            in_section = stripped == heading;
            continue;
        }
        if in_section && stripped.starts_with("- ") {
            rows.push(stripped);
        }
    }
    rows
}

pub fn table_body_rows(text: &str, heading: &str) -> Vec<String> {
    let mut rows = Vec::new();
    let mut in_section = false;
    let mut in_table = false;
    let mut first_table_row = true;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.starts_with("## ") {
            if in_section {
                break;
            }
            in_section = stripped == heading;
            in_table = false;
            first_table_row = true;
            continue;
        }
        if !in_section {
            continue;
        }
        if !stripped.starts_with('|') {
            if !stripped.is_empty() {
                in_table = false;
                first_table_row = true;
            }
            continue;
        }
        let cells = pipe_cells(stripped);
        if cells.is_empty() || cells.iter().all(String::is_empty) {
            continue;
        }
        let separator = cells.iter().all(|cell| {
            !cell.is_empty()
                && cell
                    .chars()
                    .all(|character| matches!(character, '-' | ':' | ' '))
        });
        if separator {
            in_table = true;
            continue;
        }
        if !in_table {
            in_table = true;
            first_table_row = true;
        }
        if first_table_row {
            first_table_row = false;
            continue;
        }
        rows.push(cells.join(" | "));
    }
    rows
}

pub fn check_schedule_artifact(text: &str) -> Vec<String> {
    let mut blockers = Vec::new();
    for (heading, slug) in PLAN_SECTIONS {
        if !section_has_content(text, heading) {
            blockers.push(format!("schedule.md:section_empty_or_missing:{slug}"));
        }
    }
    if table_body_rows(text, "## Planned Work Units").is_empty() {
        blockers.push("schedule.md:planned_work_units_empty".to_string());
    }
    blockers
}

pub fn check_work_log_artifact(text: &str) -> Vec<String> {
    if !section_has_content(text, "## Entries") {
        return vec!["work_log.md:section_empty_or_missing:entries".to_string()];
    }
    if bullet_rows(text, "## Entries").is_empty() {
        return vec!["work_log.md:entries_empty".to_string()];
    }
    Vec::new()
}

pub fn final_review_decision_lines(text: &str) -> Vec<String> {
    let mut lines = Vec::new();
    let mut in_decision = false;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.starts_with("## ") {
            if in_decision {
                break;
            }
            in_decision = stripped == "## Decision";
            continue;
        }
        if in_decision {
            let normalized = placeholder_pattern().replace_all(line, "");
            let normalized = normalized.trim();
            if !normalized.is_empty() {
                lines.push(normalized.to_string());
            }
        }
    }
    lines
}

pub fn has_approve_decision(text: &str) -> bool {
    final_review_decision_lines(text)
        .iter()
        .any(|line| approve_pattern().is_match(line))
}

pub fn is_placeholder_only_section(text: &str) -> bool {
    let stripped = markdown_without_comments(text);
    let remaining = stripped
        .lines()
        .map(str::trim)
        .filter(|line| {
            !line.is_empty()
                && !line.starts_with('#')
                && !line.starts_with("- Run ID:")
                && !line.starts_with("- Task:")
                && !line.starts_with("- Owner:")
                && !line.starts_with("- Created At")
                && !line.starts_with('|')
        })
        .collect::<Vec<_>>();
    remaining.is_empty()
}

pub fn check_final_review_artifact(text: &str) -> Vec<String> {
    let mut blockers = Vec::new();
    if is_placeholder_only_section(text) {
        blockers.push("final_review.md:placeholder_only".to_string());
    }
    if !section_has_content(text, "## Decision") {
        blockers.push("final_review.md:section_empty_or_missing:decision".to_string());
        return blockers;
    }
    if !has_approve_decision(text) {
        blockers.push("final_review.md:decision_not_approve".to_string());
    }
    blockers
}

/// Parse status bullets from a complete Markdown artifact, keeping the last value per key.
pub fn parse_markdown_status_lines(text: &str) -> BTreeMap<String, String> {
    let mut data = BTreeMap::new();
    for line in text.lines() {
        if let Some((key, value)) = status_line(line) {
            data.insert(key.to_owned(), value.to_owned());
        }
    }
    data
}

/// Parse status bullets under one level-two heading, rejecting duplicate keys there.
pub fn parse_markdown_status_section(
    text: &str,
    heading: &str,
) -> Result<BTreeMap<String, String>, String> {
    let target = format!("## {heading}");
    let mut data = BTreeMap::new();
    let mut in_section = false;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped == target {
            in_section = true;
            continue;
        }
        if in_section && stripped.starts_with("## ") {
            break;
        }
        if !in_section {
            continue;
        }
        if let Some((key, value)) = status_line(stripped) {
            if data.contains_key(key) {
                return Err(format!("Duplicate status key in {heading}: {key}"));
            }
            data.insert(key.to_owned(), value.to_owned());
        }
    }
    Ok(data)
}

fn status_line(line: &str) -> Option<(&str, &str)> {
    let line = crate::python_text::python_strip(line);
    let line = line.strip_prefix("- ")?;
    let (key, value) = line.split_once(": ")?;
    if value.is_empty()
        || key.is_empty()
        || !key
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    {
        return None;
    }
    Some((key, crate::python_text::python_strip(value)))
}

/// Parse whitespace-separated `key=value` evidence tokens from one line.
pub fn token_fields(line: &str) -> BTreeMap<String, String> {
    let mut fields = BTreeMap::new();
    let stripped = crate::python_text::python_strip(line)
        .trim_matches('-')
        .trim_matches('`');
    for token in stripped.split_whitespace() {
        if let Some((key, value)) = token.split_once('=') {
            fields.insert(
                crate::python_text::python_strip(key).to_owned(),
                value
                    .trim_matches(|character| matches!(character, '`' | '\'' | '"'))
                    .to_owned(),
            );
        }
    }
    fields
}

const MECHANICALLY_REGENERATED_REPORT_ROOTS: &[&str] = &[
    "reports/agent-eval-runs",
    "reports/agent-improvement-guide",
    "reports/agent-runtime-dashboard",
    "reports/dependency-review",
    "reports/hooks",
    "reports/.cache",
];

fn normalized_git_path(path: &str) -> String {
    path.replace('\\', "/").trim_matches('/').to_owned()
}

fn is_mechanically_regenerated_report_path(path: &str) -> bool {
    let normalized = normalized_git_path(path);
    if MECHANICALLY_REGENERATED_REPORT_ROOTS.iter().any(|root| {
        normalized == *root
            || normalized
                .strip_prefix(root)
                .is_some_and(|suffix| suffix.starts_with('/'))
    }) {
        return true;
    }
    let Some(filename) = normalized.strip_prefix("reports/") else {
        return false;
    };
    if filename.contains('/') {
        return false;
    }
    [".json", ".patch", ".txt"]
        .iter()
        .any(|extension| filename.ends_with(extension) && filename.len() > extension.len())
}

fn git_report_paths(workspace: &Path, extra: &[&str]) -> Vec<String> {
    let mut command = Command::new("git");
    command
        .args(["ls-files"])
        .args(extra)
        .args(["-z", "--", "reports"])
        .current_dir(workspace);
    let Ok(output) = command.output() else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|path| !path.is_empty())
        .map(|path| String::from_utf8_lossy(path).into_owned())
        .collect()
}

fn resolve_non_strict(path: &Path) -> PathBuf {
    crate::path_resolution::resolve_non_strict(path).unwrap_or_else(|_| {
        if path.is_absolute() {
            path.to_path_buf()
        } else {
            std::env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(path)
        }
    })
}

/// Return generated report artifacts outside the selected current run bundle.
pub fn report_artifact_placement_blockers(
    workspace: &Path,
    report_dir: &Path,
) -> Result<Vec<String>, String> {
    let workspace = resolve_non_strict(workspace);
    let report_dir = resolve_non_strict(report_dir);
    if !report_dir.starts_with(&workspace) {
        return Ok(Vec::new());
    }
    let mut report_paths = BTreeMap::<String, &'static str>::new();
    for path in git_report_paths(&workspace, &["--others", "--exclude-standard"]) {
        report_paths.entry(path).or_insert("untracked");
    }
    for path in git_report_paths(&workspace, &["--others", "--ignored", "--exclude-standard"]) {
        report_paths.entry(path).or_insert("ignored");
    }
    let report_root_metadata = [
        resolve_non_strict(&report_dir.join("../.active_run")),
        resolve_non_strict(&report_dir.join("../.active_run.sha256")),
        resolve_non_strict(&report_dir.join("../.run_bundle_materialization.lock")),
    ];
    let mut blockers = Vec::new();
    for (path, state) in report_paths {
        let candidate = resolve_non_strict(&workspace.join(&path));
        if report_root_metadata.contains(&candidate) || candidate.starts_with(&report_dir) {
            continue;
        }
        if state == "ignored" && !is_mechanically_regenerated_report_path(&path) {
            continue;
        }
        blockers.push(format!(
            "report_artifact_{state}_outside_current_run:{path}"
        ));
    }
    Ok(blockers)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_planned_work_units_keep_the_waterfall_diagnostic() {
        let text = "# Schedule\n## Stage Plan\n| Stage | Owner |\n| --- | --- |\n| plan | manager |\n## Clause Coverage\n| Clause | Stage |\n| --- | --- |\n| C1 | plan |\n## Planned Work Units\n| Unit | Clause |\n| --- | --- |\n";
        assert!(check_schedule_artifact(text)
            .iter()
            .any(|blocker| blocker == "schedule.md:planned_work_units_empty"));
    }

    #[test]
    fn schedule_with_concrete_work_and_work_log_entries_pass() {
        let schedule = "# Schedule\n## Stage Plan\nplan\n## Clause Coverage\nC1\n## Planned Work Units\n| Unit | Clause |\n| --- | --- |\n| W1 | C1 |\n";
        let work_log = "## Entries\n- kickoff: contract read\n";
        assert!(check_schedule_artifact(schedule).is_empty());
        assert!(check_work_log_artifact(work_log).is_empty());
    }

    #[test]
    fn final_review_requires_exact_approval_and_decision_content() {
        assert!(has_approve_decision("## Decision\napprove\n"));
        assert!(!has_approve_decision(
            "## Decision\nrevise: do not approve\n"
        ));
        assert_eq!(
            check_final_review_artifact("## Decision\nnot approved\n"),
            vec!["final_review.md:decision_not_approve"]
        );
    }
}
