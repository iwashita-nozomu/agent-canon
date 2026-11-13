// @dependency-start
// contract implementation
// responsibility Owns native report checks, status parsing, token fields, run-bundle placement, and generated report rejection.
// upstream design ../../../../../documents/design/request-intent-and-update-relation.md selected report evidence contract
// upstream design ../../../../../documents/runtime/runtime-log-archive.md retains selected report placement checks
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

use regex::Regex;
use std::collections::{BTreeMap, HashMap};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

pub const GENERATED_ARTIFACT_GUARD_SELECTOR: &str = "generated-artifact-guard";

/// Authoritative path, target digest and decision projection for one review.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReviewIdentityResult {
    pub design_artifact_path: Option<String>,
    pub review_target_sha256: Option<String>,
    pub decision_approved: bool,
}

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

fn is_mechanically_regenerated_report_path_bytes(path: &[u8]) -> bool {
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
        if is_mechanically_regenerated_report_path_bytes(&path) {
            states.insert(path, GeneratedArtifactState::Tracked);
        }
    }
    for path in git_report_paths(root, &["--others", "--exclude-standard"])? {
        if is_mechanically_regenerated_report_path_bytes(&path) {
            states
                .entry(path)
                .or_insert(GeneratedArtifactState::Untracked);
        }
    }
    for path in git_report_paths(root, &["--others", "--ignored", "--exclude-standard"])? {
        if is_mechanically_regenerated_report_path_bytes(&path) {
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

fn review_target_sha_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?i)\breview_target_sha256\s*=\s*`?([0-9a-f]{64})`?")
            .expect("fixed review target digest regex")
    })
}

fn design_artifact_path_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"(?im)^\s*-\s*Design artifact path:\s*`?([^`\r\n]+?)`?\s*$")
            .expect("fixed design artifact path regex")
    })
}

pub fn markdown_without_comments(text: &str) -> String {
    placeholder_pattern().replace_all(text, "").into_owned()
}

/// Return whether one report path names a mechanically regenerated artifact.
pub fn is_mechanically_regenerated_report_path(path: &str) -> bool {
    is_mechanically_regenerated_report_path_bytes(path.as_bytes())
}

/// Return exact tracked, untracked, and ignored eval capture leftovers in path order.
pub fn generated_eval_transient_blockers(workspace: &Path) -> Vec<String> {
    let mut states = HashMap::<Vec<u8>, &'static str>::new();
    for path in git_report_paths(workspace, &[]).unwrap_or_default() {
        if eval_transient_capture_path(&path) {
            states.insert(path, "tracked");
        }
    }
    for path in git_report_paths(workspace, &["--others", "--exclude-standard"]).unwrap_or_default()
    {
        if eval_transient_capture_path(&path) {
            states.entry(path).or_insert("untracked");
        }
    }
    for path in git_report_paths(workspace, &["--others", "--ignored", "--exclude-standard"])
        .unwrap_or_default()
    {
        if eval_transient_capture_path(&path) {
            states.entry(path).or_insert("ignored");
        }
    }
    let mut paths = states.into_iter().collect::<Vec<_>>();
    paths.sort_by_cached_key(|(path, _)| python_surrogateescape_sort_key(path));
    paths
        .into_iter()
        .map(|(path, state)| {
            format!(
                "generated_report_artifact_{state}_left_in_tree:{}",
                String::from_utf8_lossy(&path)
            )
        })
        .collect()
}

fn eval_transient_capture_path(path: &[u8]) -> bool {
    let normalized = normalized_git_path(path);
    let Some(relative) = normalized.strip_prefix(b"reports/agent-eval-runs/") else {
        return false;
    };
    let mut parts = relative.split(|byte| *byte == b'/');
    let (Some(run), Some(filename), None) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    if run.is_empty() {
        return false;
    }
    [b".stdout.txt".as_slice(), b".stderr.txt".as_slice()]
        .iter()
        .any(|suffix| filename.len() > suffix.len() && filename.ends_with(suffix))
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

/// Parse the last declared review target/path together with the approved decision.
pub fn parse_review_identity(text: &str) -> ReviewIdentityResult {
    let design_artifact_path = design_artifact_path_pattern()
        .captures_iter(text)
        .last()
        .and_then(|capture| capture.get(1))
        .map(|value| value.as_str().trim().trim_matches(['\'', '"']).to_owned());
    let review_target_sha256 = review_target_sha_pattern()
        .captures_iter(text)
        .last()
        .and_then(|capture| capture.get(1))
        .map(|value| value.as_str().to_ascii_lowercase());
    ReviewIdentityResult {
        design_artifact_path,
        review_target_sha256,
        decision_approved: has_approve_decision(text),
    }
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
    for raw_path in
        git_report_paths(&workspace, &["--others", "--exclude-standard"]).unwrap_or_default()
    {
        let path = String::from_utf8_lossy(&raw_path).into_owned();
        report_paths.entry(path).or_insert("untracked");
    }
    for raw_path in git_report_paths(&workspace, &["--others", "--ignored", "--exclude-standard"])
        .unwrap_or_default()
    {
        if !is_mechanically_regenerated_report_path_bytes(&raw_path) {
            continue;
        }
        let path = String::from_utf8_lossy(&raw_path).into_owned();
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
        blockers.push(format!(
            "report_artifact_{state}_outside_current_run:{path}"
        ));
    }
    Ok(blockers)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::process::Command;

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

    #[test]
    fn eval_transient_classifier_orders_tracked_untracked_and_ignored_paths() {
        let workspace = tempfile::tempdir().unwrap();
        let root = workspace.path();
        Command::new("git")
            .args(["init", "-q"])
            .current_dir(root)
            .status()
            .unwrap();
        fs::write(
            root.join(".gitignore"),
            "reports/agent-eval-runs/ignored-run/\n",
        )
        .unwrap();
        let tracked = root.join("reports/agent-eval-runs/tracked-run/01-role.stdout.txt");
        fs::create_dir_all(tracked.parent().unwrap()).unwrap();
        fs::write(&tracked, "tracked\n").unwrap();
        Command::new("git")
            .args([
                "add",
                ".gitignore",
                "reports/agent-eval-runs/tracked-run/01-role.stdout.txt",
            ])
            .current_dir(root)
            .status()
            .unwrap();
        let untracked = root.join("reports/agent-eval-runs/untracked-run/02-role.stderr.txt");
        fs::create_dir_all(untracked.parent().unwrap()).unwrap();
        fs::write(&untracked, "untracked\n").unwrap();
        let ignored = root.join("reports/agent-eval-runs/ignored-run/03-role.stderr.txt");
        fs::create_dir_all(ignored.parent().unwrap()).unwrap();
        fs::write(&ignored, "ignored\n").unwrap();

        assert_eq!(
            generated_eval_transient_blockers(root),
            vec![
                "generated_report_artifact_ignored_left_in_tree:reports/agent-eval-runs/ignored-run/03-role.stderr.txt",
                "generated_report_artifact_tracked_left_in_tree:reports/agent-eval-runs/tracked-run/01-role.stdout.txt",
                "generated_report_artifact_untracked_left_in_tree:reports/agent-eval-runs/untracked-run/02-role.stderr.txt",
            ]
        );
    }

    #[test]
    fn eval_transient_classifier_excludes_non_capture_outputs() {
        let workspace = tempfile::tempdir().unwrap();
        let root = workspace.path();
        Command::new("git")
            .args(["init", "-q"])
            .current_dir(root)
            .status()
            .unwrap();
        for relative in [
            "reports/agent-eval-runs/run/summary.json",
            "reports/agent-eval-runs/run/nested/role.stdout.txt",
            "reports/agent-runtime-dashboard/role.stdout.txt",
        ] {
            let path = root.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, "generated\n").unwrap();
        }
        assert!(generated_eval_transient_blockers(root).is_empty());
    }
}
