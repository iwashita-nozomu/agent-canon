// @dependency-start
// contract implementation
// responsibility Owns the pure native checks for report schedule, work log, and final-review artifacts.
// upstream design ../../../../../documents/design/request-intent-and-update-relation.md run-bundle evidence contract
// upstream implementation ../../../../../tools/runtime/artifacts/report_artifact_checks.py owns shared Python report checks
// downstream implementation run_evaluation.rs scores selected run artifacts
// downstream test ../tests/run_evaluation_native.rs establishes selected-file check behavior
// @dependency-end

use regex::Regex;
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
        let stripped = line.trim();
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
        let stripped = line.trim();
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
