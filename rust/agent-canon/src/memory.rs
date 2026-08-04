// @dependency-start
// contract implementation
// responsibility Owns the searchable one-topic-per-record AgentCanon memory schema, parser, validator, and CLI operations.
// upstream design ../../../memory/README.md memory record topology and reader contract
// upstream design ../../../documents/runtime/shared-runtime-surfaces.toml shared memory surface ownership
// downstream implementation ../../../tools/bin/agent-canon exposes the memory subcommand
// downstream implementation ../../../tools/agent_tools/memory_record.py provides the thin Python adapter
// downstream implementation ../../../tests/agent_tools/test_memory_record.py validates the adapter contract
// @dependency-end

//! Searchable, self-contained problem-solving records for AgentCanon memory.

use serde::Serialize;
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

const SCHEMA: &str = "agent-canon.memory-record.v1";
const RECORDS_DIR: &str = "memory/records";
const REQUIRED_SECTIONS: &[&str] = &[
    "Problem/Symptom",
    "Context/Trigger",
    "Root Cause",
    "Effective Resolution",
    "Failed Approaches",
    "Applicability/Limits",
    "Evidence/Source",
    "Promoted Owner Refs",
    "Related Records",
];
const FILENAME_ALLOWED: &str = "lowercase ASCII letters, digits, and hyphens with one -- separator";

#[derive(Debug, Clone, PartialEq, Eq)]
struct MemoryRecord {
    record_id: String,
    title: String,
    sections: BTreeMap<String, String>,
    path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct SearchHit {
    record_id: String,
    path: String,
    title: String,
    matched_by: Vec<String>,
}

#[derive(Debug, Clone, Default)]
struct MemoryOptions {
    root: PathBuf,
    format: String,
    record_id: Option<String>,
    title: Option<String>,
    problem: Option<String>,
    symptom: Option<String>,
    context: Option<String>,
    root_cause: Option<String>,
    effective_resolution: Option<String>,
    failed_approaches: Option<String>,
    applicability_limits: Option<String>,
    evidence_source: Option<String>,
    owner_refs: Vec<String>,
    related_records: Vec<String>,
    section: Option<String>,
    text: Option<String>,
    reason: Option<String>,
    query: Option<String>,
    search_owner_refs: Vec<String>,
    search_paths: Vec<String>,
    failure_evidence: Vec<String>,
    recurrence_decisions: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct MemoryError(String);

impl MemoryError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl std::fmt::Display for MemoryError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

fn normalize(value: &str) -> String {
    value
        .chars()
        .flat_map(char::to_lowercase)
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn terms(value: &str) -> Vec<String> {
    normalize(value)
        .split(|character: char| !character.is_ascii_alphanumeric())
        .filter(|term| term.len() >= 2)
        .map(ToOwned::to_owned)
        .collect()
}

fn records_dir(root: &Path) -> PathBuf {
    root.join(RECORDS_DIR)
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn is_record_filename(name: &str) -> bool {
    let Some(stem) = name.strip_suffix(".md") else {
        return false;
    };
    let separators = stem.matches("--").count();
    separators == 1
        && !stem.chars().any(char::is_uppercase)
        && stem.chars().all(|character| {
            character.is_ascii_lowercase() || character.is_ascii_digit() || character == '-'
        })
        && !stem.starts_with('-')
        && !stem.ends_with('-')
        && !stem.rsplit('-').next().is_some_and(|suffix| {
            suffix.len() == 8 && suffix.chars().all(|character| character.is_ascii_digit())
        })
}

fn record_path(root: &Path, record_id: &str) -> Result<PathBuf, MemoryError> {
    let filename = format!("{record_id}.md");
    if !is_record_filename(&filename) {
        return Err(MemoryError::new(format!(
            "invalid record_id {record_id}: {FILENAME_ALLOWED}"
        )));
    }
    Ok(records_dir(root).join(filename))
}

fn parse_sections(text: &str) -> Result<(String, BTreeMap<String, String>), MemoryError> {
    let mut title = None;
    let mut sections: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut current: Option<String> = None;
    for line in text.lines() {
        if title.is_none() && line.starts_with("# ") {
            title = Some(line[2..].trim().to_owned());
            continue;
        }
        if let Some(heading) = line.strip_prefix("## ") {
            let heading = heading.trim().to_owned();
            if !REQUIRED_SECTIONS.contains(&heading.as_str()) {
                return Err(MemoryError::new(format!(
                    "unknown record section: {heading}"
                )));
            }
            if sections.contains_key(&heading) {
                return Err(MemoryError::new(format!(
                    "duplicate record section: {heading}"
                )));
            }
            sections.insert(heading.clone(), Vec::new());
            current = Some(heading);
            continue;
        }
        if let Some(section) = current.as_ref() {
            if let Some(lines) = sections.get_mut(section) {
                lines.push(line.to_owned());
            }
        }
    }
    let title = title.ok_or_else(|| MemoryError::new("record title is missing"))?;
    Ok((
        title,
        sections
            .into_iter()
            .map(|(heading, lines)| (heading, lines.join("\n").trim().to_owned()))
            .collect(),
    ))
}

fn metadata_value(text: &str, key: &str) -> Option<String> {
    text.lines().find_map(|line| {
        line.strip_prefix(key)
            .map(str::trim)
            .map(|value| value.trim_matches('`').trim().to_owned())
    })
}

fn owner_refs(record: &MemoryRecord) -> Vec<String> {
    record
        .sections
        .get("Promoted Owner Refs")
        .into_iter()
        .flat_map(|section| section.lines())
        .filter_map(|line| {
            let start = line.find('`')? + 1;
            let end = line[start..].find('`')? + start;
            Some(line[start..end].to_owned())
        })
        .collect()
}

fn related_refs(record: &MemoryRecord) -> Vec<String> {
    record
        .sections
        .get("Related Records")
        .into_iter()
        .flat_map(|section| section.lines())
        .filter_map(|line| {
            let start = line.find('`')? + 1;
            let end = line[start..].find('`')? + start;
            Some(line[start..end].to_owned())
        })
        .collect()
}

fn topic_key(record: &MemoryRecord) -> String {
    record
        .sections
        .get("Problem/Symptom")
        .and_then(|value| value.split("\n\n").next())
        .map(normalize)
        .unwrap_or_default()
}

fn validate_owner_ref(root: &Path, reference: &str) -> Result<(), MemoryError> {
    let path = reference.split('#').next().unwrap_or(reference);
    if path.is_empty() || Path::new(path).is_absolute() || path.contains("..") {
        return Err(MemoryError::new(format!("invalid owner ref: {reference}")));
    }
    if !root.join(path).exists() {
        return Err(MemoryError::new(format!(
            "owner ref does not exist: {reference}"
        )));
    }
    Ok(())
}

fn validate_record(root: &Path, path: &Path, text: &str) -> Result<MemoryRecord, MemoryError> {
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| MemoryError::new("record filename is not valid UTF-8"))?;
    if !is_record_filename(filename) {
        return Err(MemoryError::new(format!(
            "invalid record filename {filename}: {FILENAME_ALLOWED}"
        )));
    }
    let expected_id = filename.strip_suffix(".md").unwrap_or_default();
    if metadata_value(text, "record_schema:") != Some(SCHEMA.to_owned()) {
        return Err(MemoryError::new(format!(
            "{filename}: record_schema must be {SCHEMA}"
        )));
    }
    let record_id = metadata_value(text, "record_id:")
        .ok_or_else(|| MemoryError::new(format!("{filename}: record_id is missing")))?;
    if record_id != expected_id {
        return Err(MemoryError::new(format!(
            "{filename}: record_id {record_id} does not match filename {expected_id}"
        )));
    }
    let (title, sections) = parse_sections(text)?;
    for heading in REQUIRED_SECTIONS {
        let value = sections
            .get(*heading)
            .ok_or_else(|| MemoryError::new(format!("{filename}: missing section {heading}")))?;
        if value.trim().is_empty() {
            return Err(MemoryError::new(format!(
                "{filename}: empty section {heading}"
            )));
        }
    }
    let record = MemoryRecord {
        record_id,
        title,
        sections,
        path: path.to_owned(),
    };
    let refs = owner_refs(&record);
    if refs.is_empty() {
        return Err(MemoryError::new(format!(
            "{filename}: owner refs are missing"
        )));
    }
    for reference in refs {
        validate_owner_ref(root, &reference)?;
    }
    for related in related_refs(&record) {
        if !is_record_filename(&format!("{related}.md")) {
            return Err(MemoryError::new(format!(
                "{filename}: invalid related record id: {related}"
            )));
        }
    }
    Ok(record)
}

fn load_records(root: &Path) -> Result<Vec<MemoryRecord>, MemoryError> {
    let directory = records_dir(root);
    if !directory.is_dir() {
        return Err(MemoryError::new(format!("missing {RECORDS_DIR}")));
    }
    let mut paths = fs::read_dir(&directory)
        .map_err(|error| MemoryError::new(format!("read {RECORDS_DIR}: {error}")))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("md"))
        .collect::<Vec<_>>();
    paths.sort();
    let mut records = Vec::new();
    let mut ids = BTreeSet::new();
    let mut problems = BTreeSet::new();
    for path in paths {
        let text = fs::read_to_string(&path)
            .map_err(|error| MemoryError::new(format!("read {}: {error}", path.display())))?;
        let record = validate_record(root, &path, &text)?;
        if !ids.insert(record.record_id.clone()) {
            return Err(MemoryError::new(format!(
                "duplicate record_id: {}",
                record.record_id
            )));
        }
        if !problems.insert(topic_key(&record)) {
            return Err(MemoryError::new(format!(
                "duplicate problem topic: {}",
                record.record_id
            )));
        }
        records.push(record);
    }
    let ids = records
        .iter()
        .map(|record| record.record_id.as_str())
        .collect::<BTreeSet<_>>();
    for record in &records {
        for related in related_refs(record) {
            if !ids.contains(related.as_str()) {
                return Err(MemoryError::new(format!(
                    "{}: related record does not exist: {related}",
                    record.record_id
                )));
            }
        }
    }
    Ok(records)
}

fn parse_options(args: &[String]) -> Result<MemoryOptions, MemoryError> {
    let mut options = MemoryOptions {
        root: PathBuf::from("."),
        format: "text".to_owned(),
        ..MemoryOptions::default()
    };
    let mut index = 0;
    while index < args.len() {
        let flag = args[index].as_str();
        if flag == "--help" || flag == "-h" {
            return Err(MemoryError::new(usage()));
        }
        let next = |index: &mut usize| -> Result<String, MemoryError> {
            *index += 1;
            args.get(*index)
                .cloned()
                .ok_or_else(|| MemoryError::new(format!("missing value for {flag}")))
        };
        match flag {
            "--root" => options.root = PathBuf::from(next(&mut index)?),
            "--format" => {
                options.format = next(&mut index)?;
                if options.format != "text" && options.format != "json" {
                    return Err(MemoryError::new("--format must be text or json"));
                }
            }
            "--record-id" => options.record_id = Some(next(&mut index)?),
            "--title" => options.title = Some(next(&mut index)?),
            "--problem" => options.problem = Some(next(&mut index)?),
            "--symptom" => options.symptom = Some(next(&mut index)?),
            "--context" => options.context = Some(next(&mut index)?),
            "--root-cause" => options.root_cause = Some(next(&mut index)?),
            "--effective-resolution" => options.effective_resolution = Some(next(&mut index)?),
            "--failed-approaches" => options.failed_approaches = Some(next(&mut index)?),
            "--applicability-limits" => options.applicability_limits = Some(next(&mut index)?),
            "--evidence-source" => options.evidence_source = Some(next(&mut index)?),
            "--owner-ref" => options.owner_refs.push(next(&mut index)?),
            "--related-record" => options.related_records.push(next(&mut index)?),
            "--section" => options.section = Some(next(&mut index)?),
            "--text" => options.text = Some(next(&mut index)?),
            "--reason" => options.reason = Some(next(&mut index)?),
            "--query" => options.query = Some(next(&mut index)?),
            "--search-owner-ref" => options.search_owner_refs.push(next(&mut index)?),
            "--search-path" => options.search_paths.push(next(&mut index)?),
            "--failure-evidence" => options.failure_evidence.push(next(&mut index)?),
            "--recurrence-decision" => options.recurrence_decisions.push(next(&mut index)?),
            _ => return Err(MemoryError::new(format!("unknown memory option: {flag}"))),
        }
        index += 1;
    }
    Ok(options)
}

fn required(value: &Option<String>, name: &str) -> Result<String, MemoryError> {
    value
        .clone()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| MemoryError::new(format!("{name} is required")))
}

fn search_hits(records: &[MemoryRecord], options: &MemoryOptions) -> Vec<SearchHit> {
    records
        .iter()
        .filter_map(|record| {
            let body = normalize(&render_record_text(record));
            let mut matched_by = Vec::new();
            if !options.search_owner_refs.is_empty()
                && options
                    .search_owner_refs
                    .iter()
                    .all(|value| body.contains(&normalize(value)))
            {
                matched_by.push("owner_ref".to_owned());
            }
            if !options.search_paths.is_empty()
                && options
                    .search_paths
                    .iter()
                    .all(|value| body.contains(&normalize(value)))
            {
                matched_by.push("path".to_owned());
            }
            if !options.failure_evidence.is_empty()
                && options
                    .failure_evidence
                    .iter()
                    .all(|value| terms(value).iter().all(|term| body.contains(term)))
            {
                matched_by.push("failure_evidence".to_owned());
            }
            if !options.recurrence_decisions.is_empty()
                && options
                    .recurrence_decisions
                    .iter()
                    .all(|value| terms(value).iter().all(|term| body.contains(term)))
            {
                matched_by.push("recurrence_decision".to_owned());
            }
            if let Some(query) = options.query.as_ref() {
                if !terms(query).iter().all(|term| body.contains(term)) {
                    return None;
                }
                matched_by.push("query".to_owned());
            }
            if matched_by.is_empty() {
                return None;
            }
            Some(SearchHit {
                record_id: record.record_id.clone(),
                path: relative_path(options.root.as_path(), &record.path),
                title: record.title.clone(),
                matched_by,
            })
        })
        .collect()
}

fn require_search_context(options: &MemoryOptions) -> Result<(), MemoryError> {
    if options.search_owner_refs.is_empty()
        && options.search_paths.is_empty()
        && options.failure_evidence.is_empty()
        && options.recurrence_decisions.is_empty()
    {
        return Err(MemoryError::new(
            "search requires selected owner/path/failure-evidence/recurrence-decision context",
        ));
    }
    Ok(())
}

fn render_record_text(record: &MemoryRecord) -> String {
    let mut output = format!(
        "# {}\n\nrecord_id: `{}`\nrecord_schema: `{}`\n\n",
        record.title, record.record_id, SCHEMA
    );
    for heading in REQUIRED_SECTIONS {
        output.push_str(&format!(
            "## {heading}\n\n{}\n\n",
            record.sections[*heading]
        ));
    }
    output
}

fn render_new_record(options: &MemoryOptions) -> Result<String, MemoryError> {
    let record_id = required(&options.record_id, "--record-id")?;
    let title = required(&options.title, "--title")?;
    let problem = required(&options.problem, "--problem")?;
    let symptom = required(&options.symptom, "--symptom")?;
    let mut sections = BTreeMap::new();
    sections.insert(
        "Problem/Symptom".to_owned(),
        format!("{problem}\n\n{symptom}"),
    );
    sections.insert(
        "Context/Trigger".to_owned(),
        required(&options.context, "--context")?,
    );
    sections.insert(
        "Root Cause".to_owned(),
        required(&options.root_cause, "--root-cause")?,
    );
    sections.insert(
        "Effective Resolution".to_owned(),
        required(&options.effective_resolution, "--effective-resolution")?,
    );
    sections.insert(
        "Failed Approaches".to_owned(),
        required(&options.failed_approaches, "--failed-approaches")?,
    );
    sections.insert(
        "Applicability/Limits".to_owned(),
        required(&options.applicability_limits, "--applicability-limits")?,
    );
    sections.insert(
        "Evidence/Source".to_owned(),
        required(&options.evidence_source, "--evidence-source")?,
    );
    if options.owner_refs.is_empty() {
        return Err(MemoryError::new("at least one --owner-ref is required"));
    }
    sections.insert(
        "Promoted Owner Refs".to_owned(),
        options
            .owner_refs
            .iter()
            .map(|reference| format!("- `{reference}`"))
            .collect::<Vec<_>>()
            .join("\n"),
    );
    sections.insert(
        "Related Records".to_owned(),
        if options.related_records.is_empty() {
            "- なし".to_owned()
        } else {
            options
                .related_records
                .iter()
                .map(|record| format!("- `{record}`"))
                .collect::<Vec<_>>()
                .join("\n")
        },
    );
    Ok(render_record_text(&MemoryRecord {
        record_id,
        title,
        sections,
        path: PathBuf::new(),
    }))
}

fn validate_candidate(root: &Path, path: &Path, text: &str) -> Result<MemoryRecord, MemoryError> {
    validate_record(root, path, text)
}

fn run_validate(options: &MemoryOptions) -> i32 {
    match load_records(&options.root) {
        Ok(records) => {
            if options.format == "json" {
                println!(
                    "{}",
                    json!({"schema": SCHEMA, "status": "pass", "record_count": records.len()})
                );
            } else {
                println!("MEMORY_RECORD_VALIDATION=pass");
                println!("MEMORY_RECORD_COUNT={}", records.len());
            }
            0
        }
        Err(error) => {
            if options.format == "json" {
                println!(
                    "{}",
                    json!({"schema": SCHEMA, "status": "fail", "error": error.to_string()})
                );
            } else {
                println!("MEMORY_RECORD_VALIDATION=fail");
                println!("MEMORY_RECORD_ERROR={error}");
            }
            1
        }
    }
}

fn run_search(options: &MemoryOptions) -> i32 {
    if let Err(error) = require_search_context(options) {
        eprintln!("MEMORY_SEARCH=fail error={error}");
        return 2;
    }
    match load_records(&options.root) {
        Ok(records) => {
            let hits = search_hits(&records, options);
            if options.format == "json" {
                println!(
                    "{}",
                    json!({"schema": "agent-canon.memory-search.v1", "records": hits})
                );
            } else {
                println!("MEMORY_SEARCH=pass");
                println!("MEMORY_SEARCH_COUNT={}", hits.len());
                for hit in hits {
                    println!(
                        "MEMORY_SEARCH_RECORD={} PATH={} MATCHED_BY={}",
                        hit.record_id,
                        hit.path,
                        hit.matched_by.join(",")
                    );
                }
            }
            0
        }
        Err(error) => {
            eprintln!("MEMORY_SEARCH=fail error={error}");
            1
        }
    }
}

fn run_create(options: &MemoryOptions) -> i32 {
    if let Err(error) = require_search_context(options) {
        eprintln!("MEMORY_CREATE=fail error={error}");
        return 2;
    }
    let records = match load_records(&options.root) {
        Ok(records) => records,
        Err(error) => {
            eprintln!("MEMORY_CREATE=fail error={error}");
            return 1;
        }
    };
    let hits = search_hits(&records, options);
    if !hits.is_empty() {
        eprintln!(
            "MEMORY_CREATE=duplicate existing={}",
            hits.iter()
                .map(|hit| hit.record_id.as_str())
                .collect::<Vec<_>>()
                .join(",")
        );
        return 2;
    }
    let record_id = match required(&options.record_id, "--record-id") {
        Ok(value) => value,
        Err(error) => {
            eprintln!("MEMORY_CREATE=fail error={error}");
            return 2;
        }
    };
    let path = match record_path(&options.root, &record_id) {
        Ok(path) => path,
        Err(error) => {
            eprintln!("MEMORY_CREATE=fail error={error}");
            return 2;
        }
    };
    if records.iter().any(|record| record.record_id == record_id) {
        eprintln!("MEMORY_CREATE=duplicate existing={record_id}");
        return 2;
    }
    let text = match render_new_record(options) {
        Ok(text) => text,
        Err(error) => {
            eprintln!("MEMORY_CREATE=fail error={error}");
            return 2;
        }
    };
    if path.exists() {
        eprintln!("MEMORY_CREATE=duplicate existing={record_id}");
        return 2;
    }
    let candidate = match validate_candidate(&options.root, &path, &text) {
        Ok(record) => record,
        Err(error) => {
            eprintln!("MEMORY_CREATE=fail error={error}");
            return 2;
        }
    };
    let existing_ids = records
        .iter()
        .map(|record| record.record_id.as_str())
        .collect::<BTreeSet<_>>();
    for related in related_refs(&candidate) {
        if !existing_ids.contains(related.as_str()) {
            eprintln!("MEMORY_CREATE=fail error=related record does not exist: {related}");
            return 2;
        }
    }
    if let Err(error) = fs::write(&path, text) {
        eprintln!("MEMORY_CREATE=fail error=write {}: {error}", path.display());
        return 1;
    }
    println!("MEMORY_CREATE=pass");
    println!("MEMORY_RECORD_ID={record_id}");
    0
}

fn section_body(text: &str, section: &str) -> Result<String, MemoryError> {
    let (title, sections) = parse_sections(text)?;
    let _ = title;
    sections
        .get(section)
        .cloned()
        .ok_or_else(|| MemoryError::new(format!("missing record section: {section}")))
}

fn replace_section(text: &str, section: &str, replacement: &str) -> Result<String, MemoryError> {
    if !REQUIRED_SECTIONS.contains(&section) {
        return Err(MemoryError::new(format!(
            "unknown record section: {section}"
        )));
    }
    let start_marker = format!("## {section}");
    let start = text
        .find(&start_marker)
        .ok_or_else(|| MemoryError::new(format!("missing record section: {section}")))?;
    let content_start = start + start_marker.len();
    let next = text[content_start..]
        .find("\n## ")
        .map(|offset| content_start + offset)
        .unwrap_or(text.len());
    let prefix = &text[..content_start];
    let suffix = &text[next..];
    Ok(format!(
        "{}\n\n{}\n{}",
        prefix.trim_end(),
        replacement.trim(),
        suffix.trim_start()
    ))
}

fn run_update(options: &MemoryOptions) -> i32 {
    let record_id = match required(&options.record_id, "--record-id") {
        Ok(value) => value,
        Err(error) => {
            eprintln!("MEMORY_UPDATE=fail error={error}");
            return 2;
        }
    };
    let section = match required(&options.section, "--section") {
        Ok(value) => value,
        Err(error) => {
            eprintln!("MEMORY_UPDATE=fail error={error}");
            return 2;
        }
    };
    let replacement = match required(&options.text, "--text") {
        Ok(value) => value,
        Err(error) => {
            eprintln!("MEMORY_UPDATE=fail error={error}");
            return 2;
        }
    };
    let path = match record_path(&options.root, &record_id) {
        Ok(path) => path,
        Err(error) => {
            eprintln!("MEMORY_UPDATE=fail error={error}");
            return 2;
        }
    };
    let current = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(error) => {
            eprintln!("MEMORY_UPDATE=fail error=read {}: {error}", path.display());
            return 1;
        }
    };
    let updated = match replace_section(&current, &section, &replacement) {
        Ok(text) => text,
        Err(error) => {
            eprintln!("MEMORY_UPDATE=fail error={error}");
            return 2;
        }
    };
    if let Err(error) = validate_candidate(&options.root, &path, &updated) {
        eprintln!("MEMORY_UPDATE=fail error={error}");
        return 2;
    }
    if let Err(error) = fs::write(&path, updated) {
        eprintln!("MEMORY_UPDATE=fail error=write {}: {error}", path.display());
        return 1;
    }
    println!("MEMORY_UPDATE=pass");
    println!("MEMORY_RECORD_ID={record_id}");
    0
}

fn run_promote(options: &MemoryOptions) -> i32 {
    let record_id = match required(&options.record_id, "--record-id") {
        Ok(value) => value,
        Err(error) => {
            eprintln!("MEMORY_PROMOTE=fail error={error}");
            return 2;
        }
    };
    if options.owner_refs.len() != 1 {
        eprintln!("MEMORY_PROMOTE=fail error=exactly one --owner-ref is required");
        return 2;
    }
    let reference = &options.owner_refs[0];
    if let Err(error) = validate_owner_ref(&options.root, reference) {
        eprintln!("MEMORY_PROMOTE=fail error={error}");
        return 2;
    }
    let path = match record_path(&options.root, &record_id) {
        Ok(path) => path,
        Err(error) => {
            eprintln!("MEMORY_PROMOTE=fail error={error}");
            return 2;
        }
    };
    let current = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(error) => {
            eprintln!("MEMORY_PROMOTE=fail error=read {}: {error}", path.display());
            return 1;
        }
    };
    let section = match section_body(&current, "Promoted Owner Refs") {
        Ok(section) => section,
        Err(error) => {
            eprintln!("MEMORY_PROMOTE=fail error={error}");
            return 2;
        }
    };
    let entry = format!(
        "- `{reference}`{}",
        options
            .reason
            .as_ref()
            .map(|reason| format!(" — {}", reason.trim()))
            .unwrap_or_default()
    );
    if section
        .lines()
        .any(|line| line.contains(&format!("`{reference}`")))
    {
        eprintln!("MEMORY_PROMOTE=duplicate record={record_id} owner_ref={reference}");
        return 2;
    }
    let replacement = if section.trim() == "- なし" {
        entry
    } else {
        format!("{section}\n{entry}")
    };
    let updated = match replace_section(&current, "Promoted Owner Refs", &replacement) {
        Ok(text) => text,
        Err(error) => {
            eprintln!("MEMORY_PROMOTE=fail error={error}");
            return 2;
        }
    };
    if let Err(error) = validate_candidate(&options.root, &path, &updated) {
        eprintln!("MEMORY_PROMOTE=fail error={error}");
        return 2;
    }
    if let Err(error) = fs::write(&path, updated) {
        eprintln!(
            "MEMORY_PROMOTE=fail error=write {}: {error}",
            path.display()
        );
        return 1;
    }
    println!("MEMORY_PROMOTE=pass");
    println!("MEMORY_RECORD_ID={record_id}");
    0
}

fn run_plan(options: &MemoryOptions) -> i32 {
    if let Err(error) = require_search_context(options) {
        eprintln!("MEMORY_PLAN=fail error={error}");
        return 2;
    }
    let records = match load_records(&options.root) {
        Ok(records) => records,
        Err(error) => {
            eprintln!("MEMORY_PLAN=fail error={error}");
            return 1;
        }
    };
    let hits = search_hits(&records, options);
    let operation = match hits.as_slice() {
        [] => {
            if let Err(error) = required(&options.record_id, "--record-id")
                .and_then(|record_id| record_path(&options.root, &record_id).map(|_| record_id))
            {
                eprintln!("MEMORY_PLAN=fail error={error}");
                return 2;
            }
            "create"
        }
        [hit] => {
            if let Some(record_id) = options.record_id.as_ref() {
                if record_id != &hit.record_id {
                    eprintln!(
                        "MEMORY_PLAN=fail error=selected context resolves to {}, not {}",
                        hit.record_id, record_id
                    );
                    return 2;
                }
            }
            "update"
        }
        _ => {
            eprintln!(
                "MEMORY_PLAN=ambiguous records={}",
                hits.iter()
                    .map(|hit| hit.record_id.as_str())
                    .collect::<Vec<_>>()
                    .join(",")
            );
            return 2;
        }
    };
    if options.format == "json" {
        println!(
            "{}",
            json!({"schema": "agent-canon.memory-plan.v1", "operation": operation, "records": hits})
        );
    } else {
        println!("MEMORY_PLAN=pass");
        println!("MEMORY_OPERATION={operation}");
        println!(
            "MEMORY_RECORDS={}",
            hits.iter()
                .map(|hit| hit.record_id.as_str())
                .collect::<Vec<_>>()
                .join(",")
        );
    }
    0
}

fn usage() -> String {
    "usage: agent-canon memory <validate|search|plan|create|update|promote> [options]".to_owned()
}

pub fn run(args: &[String]) -> i32 {
    let Some(command) = args.first() else {
        eprintln!("MEMORY=fail error={}", usage());
        return 2;
    };
    let options = match parse_options(&args[1..]) {
        Ok(options) => options,
        Err(error) => {
            eprintln!("MEMORY=fail error={error}");
            return 2;
        }
    };
    match command.as_str() {
        "validate" => run_validate(&options),
        "search" => run_search(&options),
        "plan" => run_plan(&options),
        "create" => run_create(&options),
        "update" => run_update(&options),
        "promote" => run_promote(&options),
        _ => {
            eprintln!("MEMORY=fail error=unknown command: {command}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fixture_root() -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("agent-canon-memory-{nonce}"));
        fs::create_dir_all(root.join(RECORDS_DIR)).unwrap();
        fs::create_dir_all(root.join("agents")).unwrap();
        fs::write(root.join("agents/owner.md"), "# owner\n").unwrap();
        fs::write(root.join("agents/second-owner.md"), "# second owner\n").unwrap();
        root
    }

    fn options(root: &Path) -> MemoryOptions {
        MemoryOptions {
            root: root.to_owned(),
            search_owner_refs: vec!["agents/owner.md#contract".to_owned()],
            ..MemoryOptions::default()
        }
    }

    #[test]
    fn filename_rejects_dates_and_legacy_shapes() {
        assert!(is_record_filename("runtime--archive-readback.md"));
        assert!(!is_record_filename("runtime--archive-readback-20260804.md"));
        assert!(is_record_filename("runtime--archive-20.md"));
        assert!(!is_record_filename("legacy--Uppercase.md"));
    }

    #[test]
    fn create_requires_search_context_and_renders_all_sections() {
        let root = fixture_root();
        let mut candidate = options(&root);
        candidate.record_id = Some("runtime--archive-readback".to_owned());
        candidate.title = Some("Archive readback".to_owned());
        candidate.problem = Some("Archive publication appears complete".to_owned());
        candidate.symptom = Some("The local state is not enough".to_owned());
        candidate.context = Some("After a runtime archive push".to_owned());
        candidate.root_cause = Some("The remote readback was not checked".to_owned());
        candidate.effective_resolution = Some("Read back the exact remote identity".to_owned());
        candidate.failed_approaches = Some("Trusting the push exit code".to_owned());
        candidate.applicability_limits = Some("Only publication paths".to_owned());
        candidate.evidence_source = Some("documents/runtime/runtime-log-archive.md".to_owned());
        candidate.owner_refs = vec!["agents/owner.md#contract".to_owned()];
        assert_eq!(run_create(&candidate), 0);
        let records = load_records(&root).unwrap();
        assert_eq!(search_hits(&records, &candidate).len(), 1);
    }

    #[test]
    fn duplicate_problem_topics_are_rejected() {
        let root = fixture_root();
        let mut candidate = options(&root);
        candidate.record_id = Some("runtime--one".to_owned());
        candidate.title = Some("One".to_owned());
        candidate.problem = Some("same problem".to_owned());
        candidate.symptom = Some("symptom".to_owned());
        candidate.context = Some("context".to_owned());
        candidate.root_cause = Some("cause".to_owned());
        candidate.effective_resolution = Some("resolution".to_owned());
        candidate.failed_approaches = Some("failed".to_owned());
        candidate.applicability_limits = Some("limits".to_owned());
        candidate.evidence_source = Some("source".to_owned());
        candidate.owner_refs = vec!["agents/owner.md#contract".to_owned()];
        let first = render_new_record(&candidate).unwrap();
        fs::write(root.join(RECORDS_DIR).join("runtime--one.md"), first).unwrap();
        let mut second = candidate.clone();
        second.record_id = Some("runtime--two".to_owned());
        let second_text = render_new_record(&second).unwrap();
        let second_path = root.join(RECORDS_DIR).join("runtime--two.md");
        validate_candidate(&root, &second_path, &second_text).unwrap();
        fs::write(&second_path, second_text).unwrap();
        let result = load_records(&root);
        assert!(result.is_err());
    }

    #[test]
    fn plan_requires_context_and_selects_create_or_update() {
        let root = fixture_root();
        let mut candidate = options(&root);
        candidate.record_id = Some("runtime--archive-readback".to_owned());
        assert_eq!(run_plan(&candidate), 0);
        let mut record_options = candidate.clone();
        record_options.title = Some("Archive readback".to_owned());
        record_options.problem = Some("archive published".to_owned());
        record_options.symptom = Some("readback missing".to_owned());
        record_options.context = Some("after push".to_owned());
        record_options.root_cause = Some("remote not checked".to_owned());
        record_options.effective_resolution = Some("read remote identity".to_owned());
        record_options.failed_approaches = Some("trust local state".to_owned());
        record_options.applicability_limits = Some("publication only".to_owned());
        record_options.evidence_source =
            Some("documents/runtime/runtime-log-archive.md".to_owned());
        record_options.owner_refs = vec!["agents/owner.md#contract".to_owned()];
        let text = render_new_record(&record_options).unwrap();
        fs::write(
            root.join(RECORDS_DIR).join("runtime--archive-readback.md"),
            text,
        )
        .unwrap();
        assert_eq!(run_plan(&candidate), 0);
    }

    #[test]
    fn update_replaces_one_section_and_preserves_schema() {
        let root = fixture_root();
        let mut candidate = options(&root);
        candidate.record_id = Some("runtime--archive-readback".to_owned());
        candidate.title = Some("Archive readback".to_owned());
        candidate.problem = Some("archive published".to_owned());
        candidate.symptom = Some("readback missing".to_owned());
        candidate.context = Some("after push".to_owned());
        candidate.root_cause = Some("remote not checked".to_owned());
        candidate.effective_resolution = Some("read remote identity".to_owned());
        candidate.failed_approaches = Some("trust local state".to_owned());
        candidate.applicability_limits = Some("publication only".to_owned());
        candidate.evidence_source = Some("documents/runtime/runtime-log-archive.md".to_owned());
        candidate.owner_refs = vec!["agents/owner.md#contract".to_owned()];
        assert_eq!(run_create(&candidate), 0);
        let mut update = options(&root);
        update.record_id = candidate.record_id.clone();
        update.section = Some("Effective Resolution".to_owned());
        update.text = Some("read back remote branch and tree identity".to_owned());
        assert_eq!(run_update(&update), 0);
        let text = fs::read_to_string(root.join(RECORDS_DIR).join("runtime--archive-readback.md"))
            .unwrap();
        assert!(text.contains("read back remote branch and tree identity"));
        assert!(load_records(&root).is_ok());
    }

    #[test]
    fn promote_adds_owner_ref_and_rejects_duplicate() {
        let root = fixture_root();
        let mut candidate = options(&root);
        candidate.record_id = Some("runtime--archive-readback".to_owned());
        candidate.title = Some("Archive readback".to_owned());
        candidate.problem = Some("archive published".to_owned());
        candidate.symptom = Some("readback missing".to_owned());
        candidate.context = Some("after push".to_owned());
        candidate.root_cause = Some("remote not checked".to_owned());
        candidate.effective_resolution = Some("read remote identity".to_owned());
        candidate.failed_approaches = Some("trust local state".to_owned());
        candidate.applicability_limits = Some("publication only".to_owned());
        candidate.evidence_source = Some("documents/runtime/runtime-log-archive.md".to_owned());
        candidate.owner_refs = vec!["agents/owner.md#contract".to_owned()];
        assert_eq!(run_create(&candidate), 0);
        let mut promote = options(&root);
        promote.record_id = candidate.record_id.clone();
        promote.owner_refs = vec!["agents/second-owner.md#contract".to_owned()];
        promote.reason = Some("owner is now canonical".to_owned());
        assert_eq!(run_promote(&promote), 0);
        assert_eq!(run_promote(&promote), 2);
        let text = fs::read_to_string(root.join(RECORDS_DIR).join("runtime--archive-readback.md"))
            .unwrap();
        assert!(text.contains("agents/second-owner.md#contract"));
        assert!(load_records(&root).is_ok());
    }
}
