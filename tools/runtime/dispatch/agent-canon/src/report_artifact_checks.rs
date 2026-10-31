// @dependency-start
// contract implementation
// responsibility Owns native report text checks and rejects generated report artifacts left in the source tree.
// upstream design ../../../../../documents/design/request-intent-and-update-relation.md run-bundle evidence contract
// upstream implementation ../../../../../tools/runtime/artifacts/report_artifact_checks.py retains task-close placement checks
// upstream design ../../../../../agents/canonical/ARTIFACT_PLACEMENT.md generated artifact placement policy
// upstream design ../../../../../templates/agents/closeout_gate.md closeout evidence template
// upstream design ../../../../../tools/README.md native tool index
// upstream design ../../../../../documents/tools/README.md public tool index
// upstream design ../../../../../tools/catalog.yaml existing generated artifact guard entry
// downstream implementation main.rs routes the generated-artifact-guard CLI
// downstream implementation ../../../../validation/ci/checks/check_agent_canon_pr.sh runs the guard for PR checks
// downstream test ../../../../../tests/agent_tools/test_generated_artifact_guard.py checks CLI and retained Python helper contracts
// downstream test ../tests/generated_artifact_guard_native.rs checks the frozen Python CLI oracle
// downstream test ../../../../../tests/agent_tools/test_tool_drift.py checks caller closure
// downstream implementation run_evaluation.rs scores selected run artifacts
// downstream test ../tests/run_evaluation_native.rs establishes selected-file check behavior
// @dependency-end

use std::collections::HashMap;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

use regex::Regex;
use std::sync::OnceLock;

pub const GENERATED_ARTIFACT_GUARD_SELECTOR: &str = "generated-artifact-guard";

const GENERATED_ARTIFACT_GUARD_DESCRIPTION: &str =
    "Fail when mechanically regenerated report artifacts remain in the tree.";
const GENERATED_ARTIFACT_GUARD_NEXT: &[u8] = b"delete_regeneratable_report_outputs_or_write_durable_evidence_to_documents_agents_notes_with_dependency_manifest";
const GENERATED_ARTIFACT_ROOTS: &[&[u8]] = &[
    b"reports/agent-eval-runs",
    b"reports/agent-improvement-guide",
    b"reports/agent-runtime-dashboard",
    b"reports/dependency-review",
    b"reports/hooks",
    b"reports/.cache",
];
const GENERATED_ARTIFACT_FILE_SUFFIXES: [&[u8]; 3] = [b".json", b".patch", b".txt"];

fn is_unambiguous_long_option_prefix(argument: &str, option: &str) -> bool {
    argument.len() > 2 && option.starts_with(argument)
}

#[derive(Clone, Copy)]
enum GeneratedArtifactState {
    Tracked,
    Untracked,
    Ignored,
}

impl GeneratedArtifactState {
    fn as_bytes(self) -> &'static [u8] {
        match self {
            Self::Tracked => b"tracked",
            Self::Untracked => b"untracked",
            Self::Ignored => b"ignored",
        }
    }
}

struct GeneratedArtifactBlocker {
    path: Vec<u8>,
    state: GeneratedArtifactState,
}

fn git_report_paths(root: &Path, options: &[&str]) -> io::Result<Vec<Vec<u8>>> {
    let output = Command::new("git")
        .arg("ls-files")
        .args(options)
        .arg("-z")
        .arg("--")
        .arg("reports")
        .current_dir(root)
        .output()?;
    if !output.status.success() {
        return Ok(Vec::new());
    }
    Ok(output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|path| !path.is_empty())
        .map(<[u8]>::to_vec)
        .collect())
}

fn normalized_git_path(path: &[u8]) -> Vec<u8> {
    let replaced = path
        .iter()
        .map(|byte| if *byte == b'\\' { b'/' } else { *byte })
        .collect::<Vec<_>>();
    let start = replaced
        .iter()
        .position(|byte| *byte != b'/')
        .unwrap_or(replaced.len());
    let end = replaced
        .iter()
        .rposition(|byte| *byte != b'/')
        .map_or(start, |index| index + 1);
    replaced[start..end].to_vec()
}

fn pure_posix_path(path: &[u8]) -> Vec<u8> {
    let mut normalized = Vec::with_capacity(path.len());
    for component in path.split(|byte| *byte == b'/') {
        if component.is_empty() || component == b"." {
            continue;
        }
        if !normalized.is_empty() {
            normalized.push(b'/');
        }
        normalized.extend_from_slice(component);
    }
    normalized
}

fn is_mechanically_regenerated_report_path(path: &[u8]) -> bool {
    let normalized = normalized_git_path(path);
    let candidate = pure_posix_path(&normalized);
    if GENERATED_ARTIFACT_ROOTS.iter().any(|root| {
        candidate.as_slice() == *root
            || candidate
                .as_slice()
                .strip_prefix(*root)
                .is_some_and(|tail| tail.starts_with(b"/"))
    }) {
        return true;
    }

    let Some(filename) = normalized.strip_prefix(b"reports/") else {
        return false;
    };
    if filename.is_empty() || filename.contains(&b'/') {
        return false;
    }
    let filename = filename.strip_suffix(b"\n").unwrap_or(filename);
    GENERATED_ARTIFACT_FILE_SUFFIXES
        .iter()
        .any(|suffix| filename.len() > suffix.len() && filename.ends_with(suffix))
}

fn python_surrogateescape_sort_key(path: &[u8]) -> Vec<u32> {
    let mut key = Vec::new();
    let mut remaining = path;
    while !remaining.is_empty() {
        match std::str::from_utf8(remaining) {
            Ok(text) => {
                key.extend(text.chars().map(u32::from));
                break;
            }
            Err(error) => {
                let valid = &remaining[..error.valid_up_to()];
                key.extend(
                    std::str::from_utf8(valid)
                        .expect("valid UTF-8 prefix")
                        .chars()
                        .map(u32::from),
                );
                let invalid_length = error
                    .error_len()
                    .unwrap_or(remaining.len() - error.valid_up_to());
                let invalid = &remaining[error.valid_up_to()..error.valid_up_to() + invalid_length];
                key.extend(invalid.iter().map(|byte| {
                    if *byte >= 0x80 {
                        0xdc00 + u32::from(*byte)
                    } else {
                        u32::from(*byte)
                    }
                }));
                remaining = &remaining[error.valid_up_to() + invalid_length..];
            }
        }
    }
    key
}

fn generated_artifact_blockers(root: &Path) -> io::Result<Vec<GeneratedArtifactBlocker>> {
    let mut states = HashMap::<Vec<u8>, GeneratedArtifactState>::new();
    for path in git_report_paths(root, &[])? {
        if is_mechanically_regenerated_report_path(&path) {
            states.insert(path, GeneratedArtifactState::Tracked);
        }
    }
    for path in git_report_paths(root, &["--others", "--exclude-standard"])? {
        if is_mechanically_regenerated_report_path(&path) {
            states
                .entry(path)
                .or_insert(GeneratedArtifactState::Untracked);
        }
    }
    for path in git_report_paths(root, &["--others", "--ignored", "--exclude-standard"])? {
        if is_mechanically_regenerated_report_path(&path) {
            states
                .entry(path)
                .or_insert(GeneratedArtifactState::Ignored);
        }
    }

    let mut blockers = states
        .into_iter()
        .map(|(path, state)| GeneratedArtifactBlocker { path, state })
        .collect::<Vec<_>>();
    blockers.sort_by_cached_key(|blocker| python_surrogateescape_sort_key(&blocker.path));
    Ok(blockers)
}

fn generated_artifact_guard_usage() -> &'static [u8] {
    b"usage: agent-canon generated-artifact-guard [-h] [--root ROOT]\n"
}

fn generated_artifact_guard_help() -> Vec<u8> {
    let mut output = generated_artifact_guard_usage().to_vec();
    output.extend_from_slice(
        format!(
            "\n{}\n\noptions:\n  -h, --help   show this help message and exit\n  --root ROOT  Repository root to inspect. Defaults to the current directory.\n",
            GENERATED_ARTIFACT_GUARD_DESCRIPTION
        )
        .as_bytes(),
    );
    output
}

fn write_generated_artifact_argument_error(detail: &str) -> i32 {
    let mut stderr = io::stderr().lock();
    let _ = stderr.write_all(generated_artifact_guard_usage());
    let _ = writeln!(
        stderr,
        "agent-canon generated-artifact-guard: error: {detail}"
    );
    2
}

fn write_generated_artifact_guard(blockers: &[GeneratedArtifactBlocker]) -> io::Result<()> {
    let mut output = io::stdout().lock();
    output.write_all(if blockers.is_empty() {
        b"GENERATED_ARTIFACT_GUARD=pass\n"
    } else {
        b"GENERATED_ARTIFACT_GUARD=fail\n"
    })?;
    output.write_all(b"GENERATED_ARTIFACT_BLOCKERS=")?;
    if blockers.is_empty() {
        output.write_all(b"none")?;
    } else {
        for (index, blocker) in blockers.iter().enumerate() {
            if index > 0 {
                output.write_all(b"|")?;
            }
            output.write_all(b"generated_report_artifact_")?;
            output.write_all(blocker.state.as_bytes())?;
            output.write_all(b"_left_in_tree:")?;
            output.write_all(&blocker.path)?;
        }
    }
    output.write_all(b"\n")?;
    if !blockers.is_empty() {
        output.write_all(b"GENERATED_ARTIFACT_NEXT=")?;
        output.write_all(GENERATED_ARTIFACT_GUARD_NEXT)?;
        output.write_all(b"\n")?;
    }
    output.flush()
}

pub fn run_generated_artifact_guard(args: &[String]) -> i32 {
    let mut root = None;
    let mut unrecognized = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        if argument == "-h"
            || (inline_value.is_none() && is_unambiguous_long_option_prefix(option, "--help"))
        {
            let _ = io::stdout()
                .lock()
                .write_all(&generated_artifact_guard_help());
            return 0;
        }
        if is_unambiguous_long_option_prefix(option, "--root") {
            if let Some(value) = inline_value {
                root = Some(PathBuf::from(if value.is_empty() { "." } else { value }));
                index += 1;
                continue;
            }
            let Some(value) = args.get(index + 1) else {
                return write_generated_artifact_argument_error(
                    "argument --root: expected one argument",
                );
            };
            if value.starts_with('-') && value != "-" {
                return write_generated_artifact_argument_error(
                    "argument --root: expected one argument",
                );
            }
            root = Some(PathBuf::from(if value.is_empty() {
                "."
            } else {
                value.as_str()
            }));
            index += 2;
            continue;
        }
        unrecognized.push(argument);
        index += 1;
    }
    if !unrecognized.is_empty() {
        return write_generated_artifact_argument_error(&format!(
            "unrecognized arguments: {}",
            unrecognized.join(" ")
        ));
    }

    let root = match root {
        Some(root) => root,
        None => match std::env::current_dir() {
            Ok(root) => root,
            Err(error) => {
                eprintln!("agent-canon generated-artifact-guard: {error}");
                return 1;
            }
        },
    };
    let blockers = match generated_artifact_blockers(&root) {
        Ok(blockers) => blockers,
        Err(error) => {
            eprintln!("agent-canon generated-artifact-guard: failed to run git ls-files: {error}");
            return 1;
        }
    };
    if let Err(error) = write_generated_artifact_guard(&blockers) {
        eprintln!("agent-canon generated-artifact-guard: failed to write output: {error}");
        return 1;
    }
    if blockers.is_empty() {
        0
    } else {
        1
    }
}

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
