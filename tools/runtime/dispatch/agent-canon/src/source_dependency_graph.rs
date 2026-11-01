// @dependency-start
// contract implementation
// responsibility Derives dependency graph projections and shares Python-compatible component matching.
// upstream design ../../../../../documents/design/dependency-manifest-design.md dependency manifest DSL and path semantics
// upstream design ../../../../../documents/design/source-owned-dependency-validation.md tracked source authority boundary
// upstream implementation skill_projection_registry.rs resolves generated skill-view owner paths
// upstream implementation dependency_manifest.rs owns dependency declaration parsing and lexical target resolution
// upstream implementation path_resolution.rs owns shared Python-compatible component matching
// downstream implementation main.rs dispatches the native source dependency review command
// downstream implementation graph_client.rs exposes typed source-derived dependency query and context
// downstream implementation tool_drift.rs consumes source-derived dependency facts
// downstream implementation agent_search.rs routes selected dependency requests through the source graph owner
// downstream implementation ../../../../../tests/agent_tools/test_graph_client_source_projection.py validates no-runtime projections
// downstream implementation ../../../../../tests/agent_tools/test_dependency_graph_cycles.py verifies snapshot and normal-path boundaries
// @dependency-end

use crate::dependency_manifest::{
    parse_dependency_header, ParsedDependencyHeader, TargetPathError,
};
use agent_canon::path_resolution::python_fnmatch_case;
use crate::skill_projection_registry::{generated_skill_projections, GeneratedProjection};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fmt;
use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};
use std::process::Command;

pub const HEADER_SCAN_LINES: usize = 80;
pub const MANIFEST_FIELD_COUNT: usize = 4;
pub const MANIFEST_REASON_MAX_SPLIT: usize = MANIFEST_FIELD_COUNT - 1;
pub const DEFAULT_CONTEXT_DEPTH: usize = 3;

pub const DEPENDENCY_KINDS: &[&str] = &["design", "implementation", "environment", "reference"];
pub const CONTEXT_KINDS: &[&str] = &["design", "implementation", "reference"];
pub const TEXT_SUFFIXES: &[&str] = &[
    "bash", "c", "cc", "cfg", "cpp", "css", "h", "hpp", "html", "json", "md", "py", "rs", "rst",
    "sh", "toml", "txt", "yaml", "yml", "zsh",
];
pub const SKIPPED_PREFIXES: &[&str] = &[
    ".agent-canon/log-archive/",
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    "reports/",
];
pub const RAW_NVIDIA_FIXTURE_PREFIX: &str = "tests/fixtures/nvidia/";
const GENERATED_SKILL_PREFIX: &str = ".codex/personal/skills/";
const GENERATED_SKILL_SUFFIX: &str = "/SKILL.md";
const SOURCE_DEPENDENCY_USAGE: &str = "usage: agent-canon source-dependency-graph --root ROOT --edges-out EDGES_OUT --manifests-out MANIFESTS_OUT";
const SOURCE_DEPENDENCY_HELP: &str = "usage: agent-canon source-dependency-graph --root ROOT --edges-out EDGES_OUT --manifests-out MANIFESTS_OUT\n\nExport source-derived dependency review inputs without graph runtime state.\n\noptions:\n  -h, --help            show this help message and exit\n  --root ROOT\n  --edges-out EDGES_OUT\n  --manifests-out MANIFESTS_OUT";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceDependencyError {
    pub message: String,
}

impl SourceDependencyError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for SourceDependencyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for SourceDependencyError {}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct SourceDependencyEdge {
    pub source: String,
    pub direction: String,
    pub kind: String,
    pub target: String,
    pub reason: String,
    pub line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct SourceDependencyDocument {
    pub path: String,
    pub manifest_present: bool,
    pub edges: Vec<SourceDependencyEdge>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SourceDependencyProjection {
    pub nodes: Vec<Value>,
    pub facts: Vec<Value>,
    pub fingerprint: String,
}

impl SourceDependencyProjection {
    pub fn payload(&self) -> Value {
        json!({
            "nodes": self.nodes,
            "facts": self.facts,
            "graph_fingerprint": self.fingerprint,
            "projection": "tracked-source"
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceContextProjection {
    pub resolved_path: String,
    pub snapshot_commit: String,
    pub content_sha256: String,
    pub evidence_paths: Vec<String>,
    pub parent_paths: Vec<String>,
    pub fingerprint: String,
}

impl SourceContextProjection {
    pub fn payload(&self) -> Value {
        json!({
            "resolved_path": self.resolved_path,
            "source_identity": {
                "snapshot_commit": self.snapshot_commit,
                "source_path": self.resolved_path,
                "content_sha256": self.content_sha256
            },
            "evidence_paths": self.evidence_paths,
            "parent_paths": self.parent_paths,
            "graph_fingerprint": self.fingerprint,
            "projection": "tracked-source"
        })
    }
}

/// Remove supported comment wrappers from one manifest line.
pub fn strip_manifest_line(line: &str) -> String {
    let mut stripped = line.trim_end_matches('\r').trim().to_string();
    for prefix in ["# ", "#", "// ", "//", "* ", "*"] {
        if let Some(rest) = stripped.strip_prefix(prefix) {
            stripped = rest.trim().to_string();
            break;
        }
    }
    if let Some(rest) = stripped.strip_suffix(',') {
        stripped = rest.trim().to_string();
    }
    if stripped.len() >= 2 && stripped.starts_with('"') && stripped.ends_with('"') {
        stripped = stripped[1..stripped.len() - 1].trim().to_string();
    }
    stripped
}

fn io_error(context: impl AsRef<str>, error: impl fmt::Display) -> SourceDependencyError {
    SourceDependencyError::new(format!("{}: {error}", context.as_ref()))
}

fn canonicalize_non_strict(path: &Path, depth: usize) -> io::Result<PathBuf> {
    if depth > 40 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "too many levels of symbolic links",
        ));
    }
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut current = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::Prefix(prefix) => current.push(prefix.as_os_str()),
            Component::RootDir => current.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                current.pop();
            }
            Component::Normal(part) => {
                let candidate = current.join(part);
                match fs::symlink_metadata(&candidate) {
                    Ok(metadata) if metadata.file_type().is_symlink() => {
                        let target = fs::read_link(&candidate)?;
                        let target = if target.is_absolute() {
                            target
                        } else {
                            current.join(target)
                        };
                        current = canonicalize_non_strict(&target, depth + 1)?;
                    }
                    Ok(_) => current = candidate,
                    Err(error)
                        if matches!(
                            error.kind(),
                            io::ErrorKind::NotFound | io::ErrorKind::NotADirectory
                        ) =>
                    {
                        current = candidate;
                    }
                    Err(error) => return Err(error),
                }
            }
        }
    }
    Ok(current)
}

fn absolute_non_strict(path: &Path) -> Result<PathBuf, SourceDependencyError> {
    canonicalize_non_strict(path, 0).map_err(|error| io_error(path.display().to_string(), error))
}

/// Return one normalized repository-relative path, following existing symlinks.
pub fn repo_relative(root: &Path, path: &Path) -> Result<String, SourceDependencyError> {
    let canonical_root = absolute_non_strict(root)?;
    let canonical_path = absolute_non_strict(path)?;
    let relative = canonical_path.strip_prefix(&canonical_root).map_err(|_| {
        SourceDependencyError::new(format!("path escapes repository root: {}", path.display()))
    })?;
    Ok(relative_path_string(relative))
}

fn relative_path_string(path: &Path) -> String {
    let value = path.to_string_lossy();
    if cfg!(windows) {
        value.replace('\\', "/")
    } else {
        value.into_owned()
    }
}

fn git_files(root: &Path) -> Result<Vec<String>, SourceDependencyError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-files"])
        .output()
        .map_err(|error| io_error("git ls-files unavailable", error))?;
    if !output.status.success() {
        return Ok(Vec::new());
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect())
}

fn walk_files(
    root: &Path,
    current: &Path,
    paths: &mut BTreeSet<String>,
) -> Result<(), SourceDependencyError> {
    let entries = match fs::read_dir(current) {
        Ok(entries) => entries,
        Err(error) if error.kind() == io::ErrorKind::NotFound && current == root => return Ok(()),
        Err(error) => return Err(io_error(current.display().to_string(), error)),
    };
    for entry in entries {
        let entry = entry.map_err(|error| io_error(current.display().to_string(), error))?;
        let path = entry.path();
        let file_type = entry
            .file_type()
            .map_err(|error| io_error(path.display().to_string(), error))?;
        if file_type.is_dir() {
            walk_files(root, &path, paths)?;
        } else if file_type.is_file() && !file_type.is_symlink() {
            paths.insert(repo_relative(root, &path)?);
        }
    }
    Ok(())
}

/// Return deterministic indexed paths, falling back to a filesystem walk when Git has none.
pub fn source_paths(root: &Path) -> Result<Vec<String>, SourceDependencyError> {
    let root = absolute_non_strict(root)?;
    let mut paths: BTreeSet<String> = git_files(&root)?.into_iter().collect();
    if paths.is_empty() {
        walk_files(&root, &root, &mut paths)?;
    }
    Ok(paths.into_iter().collect())
}

/// Return whether a path has a supported dependency-manifest text suffix.
pub fn is_text_source(path: &str) -> bool {
    let normalized = path.replace('\\', "/");
    let normalized = normalized.strip_prefix("./").unwrap_or(&normalized);
    if SKIPPED_PREFIXES
        .iter()
        .any(|prefix| normalized.starts_with(prefix))
    {
        return false;
    }
    if normalized.starts_with(RAW_NVIDIA_FIXTURE_PREFIX)
        && Path::new(normalized)
            .extension()
            .and_then(|suffix| suffix.to_str())
            == Some("txt")
    {
        return false;
    }
    Path::new(normalized)
        .extension()
        .and_then(|suffix| suffix.to_str())
        .is_some_and(|suffix| {
            let suffix = suffix.to_ascii_lowercase();
            TEXT_SUFFIXES.contains(&suffix.as_str())
        })
}

fn projection_error(error: impl fmt::Display) -> SourceDependencyError {
    SourceDependencyError::new(error.to_string())
}

fn resolve_generated_view(
    root: &Path,
    normalized: &str,
    projections: Option<&[GeneratedProjection]>,
) -> Result<String, SourceDependencyError> {
    if !(normalized.starts_with(GENERATED_SKILL_PREFIX)
        && normalized.ends_with(GENERATED_SKILL_SUFFIX))
    {
        return Ok(normalized.to_string());
    }
    let owned;
    let projections = match projections {
        Some(projections) => projections,
        None => {
            owned = generated_skill_projections(root).map_err(projection_error)?;
            &owned
        }
    };
    let Some(projection) = projections
        .iter()
        .find(|projection| projection.path == normalized)
    else {
        return Err(SourceDependencyError::new(format!(
            "unknown generated skill view: {normalized}"
        )));
    };
    if !root.join(&projection.source).is_file() {
        return Err(SourceDependencyError::new(format!(
            "generated skill canonical source is unavailable: {}",
            projection.source
        )));
    }
    Ok(projection.source.clone())
}

fn resolve_source_path_with_projections(
    root: &Path,
    relative: &str,
    projections: Option<&[GeneratedProjection]>,
) -> Result<(String, PathBuf), SourceDependencyError> {
    let root = absolute_non_strict(root)?;
    let normalized = relative.replace('\\', "/");
    let normalized = normalized.strip_prefix("./").unwrap_or(&normalized);
    let normalized = resolve_generated_view(&root, normalized, projections)?;
    let direct_path = root.join(&normalized);
    if fs::symlink_metadata(&direct_path).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err(SourceDependencyError::new(format!(
            "source path is a symbolic link: {normalized}"
        )));
    }
    let direct = absolute_non_strict(&direct_path)?;
    repo_relative(&root, &direct)?;
    if !direct.is_file() {
        return Err(SourceDependencyError::new(format!(
            "source path is unavailable: {normalized}"
        )));
    }
    Ok((normalized.to_string(), direct))
}

/// Return the canonical repository-relative and physical source paths.
pub fn resolve_source_path(
    root: &Path,
    relative: &str,
) -> Result<(String, PathBuf), SourceDependencyError> {
    resolve_source_path_with_projections(root, relative, None)
}

fn read_text(path: &Path, relative: &str) -> Result<String, SourceDependencyError> {
    fs::read_to_string(path).map_err(|error| {
        SourceDependencyError::new(format!("source text is unreadable: {relative}: {error}"))
    })
}

fn strip_legacy_line(line: &str) -> String {
    strip_manifest_line(line)
}

fn python_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut characters = text.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        let separator = matches!(
            character,
            '\n' | '\r'
                | '\u{000b}'
                | '\u{000c}'
                | '\u{001c}'
                | '\u{001d}'
                | '\u{001e}'
                | '\u{0085}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if !separator {
            continue;
        }
        lines.push(&text[start..index]);
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            let (newline_index, newline) = characters.next().expect("peeked newline is present");
            start = newline_index + newline.len_utf8();
        } else {
            start = index + character.len_utf8();
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

fn marker_range(
    relative: &str,
    text: &str,
) -> Result<Option<(usize, usize)>, SourceDependencyError> {
    let mut in_manifest = false;
    let mut saw_start = false;
    let mut start_index = None;
    for (index, raw_line) in python_lines(text)
        .into_iter()
        .take(HEADER_SCAN_LINES)
        .enumerate()
    {
        let line_number = index + 1;
        let line = strip_legacy_line(raw_line);
        if line == "@dependency-start" {
            if in_manifest || saw_start {
                return Err(SourceDependencyError::new(format!(
                    "{relative}:{line_number}: duplicate @dependency-start"
                )));
            }
            in_manifest = true;
            saw_start = true;
            start_index = Some(index);
            continue;
        }
        if line == "@dependency-end" {
            if !in_manifest {
                return Err(SourceDependencyError::new(format!(
                    "{relative}:{line_number}: @dependency-end without start"
                )));
            }
            let start = start_index.ok_or_else(|| {
                SourceDependencyError::new(format!(
                    "{relative}: incomplete dependency manifest markers"
                ))
            })?;
            return Ok(Some((start, index)));
        }
    }
    if saw_start {
        return Err(SourceDependencyError::new(format!(
            "{relative}: incomplete dependency manifest markers"
        )));
    }
    Ok(None)
}

fn normalized_parser_text(text: &str, range: Option<(usize, usize)>) -> String {
    python_lines(text)
        .into_iter()
        .take(HEADER_SCAN_LINES)
        .enumerate()
        .map(|(index, raw_line)| {
            if range.is_some_and(|(start, end)| start <= index && index <= end) {
                let line = strip_legacy_line(raw_line);
                if matches!(
                    line.as_str(),
                    "<!--" | "-->" | "/*" | "*/" | "\"\"\"" | "'''"
                ) {
                    "# ".to_string()
                } else {
                    format!("# {line}")
                }
            } else {
                String::new()
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn legacy_fields(line: &str) -> Vec<&str> {
    let mut fields = Vec::new();
    let mut rest = line;
    for _ in 0..MANIFEST_REASON_MAX_SPLIT {
        rest = rest.trim_start();
        if rest.is_empty() {
            break;
        }
        let end = rest.find(char::is_whitespace).unwrap_or(rest.len());
        fields.push(&rest[..end]);
        rest = &rest[end..];
    }
    rest = rest.trim_start();
    if !rest.is_empty() {
        fields.push(rest);
    }
    fields
}

fn legacy_grammar_error(
    relative: &str,
    line_number: usize,
    raw_line: &str,
) -> Option<SourceDependencyError> {
    let line = strip_legacy_line(raw_line);
    if line.is_empty()
        || matches!(
            line.as_str(),
            "<!--" | "-->" | "/*" | "*/" | "\"\"\"" | "'''"
        )
        || line.starts_with("contract ")
        || line.starts_with("responsibility ")
        || line.starts_with("coverage ")
    {
        return None;
    }
    let fields = legacy_fields(&line);
    if fields.len() != MANIFEST_FIELD_COUNT {
        return Some(SourceDependencyError::new(format!(
            "{relative}:{line_number}: dependency line must be direction kind relative-path reason"
        )));
    }
    if !matches!(fields[0], "upstream" | "downstream") {
        return Some(SourceDependencyError::new(format!(
            "{relative}:{line_number}: invalid dependency direction: {}",
            fields[0]
        )));
    }
    if !DEPENDENCY_KINDS.contains(&fields[1]) {
        return Some(SourceDependencyError::new(format!(
            "{relative}:{line_number}: invalid dependency kind: {}",
            fields[1]
        )));
    }
    if fields[3].is_empty() {
        return Some(SourceDependencyError::new(format!(
            "{relative}:{line_number}: dependency reason is empty"
        )));
    }
    None
}

fn diagnostic_error(
    root: &Path,
    relative: &str,
    source: &Path,
    parsed: &ParsedDependencyHeader,
) -> Result<(), SourceDependencyError> {
    for diagnostic in &parsed.diagnostics {
        let line_number = diagnostic.source_span.start_line;
        let raw_line = parsed
            .entries
            .iter()
            .find(|(number, _)| *number == line_number)
            .map(|(_, line)| line.as_str())
            .unwrap_or("");
        if diagnostic.code == "manifest-grammar" {
            if let Some(error) = legacy_grammar_error(relative, line_number, raw_line) {
                return Err(error);
            }
            return Err(SourceDependencyError::new(format!(
                "{relative}:{line_number}: dependency line must be direction kind relative-path reason"
            )));
        }
        let normalized_line = strip_legacy_line(raw_line);
        let fields = legacy_fields(&normalized_line);
        let declared_target = fields
            .get(2)
            .copied()
            .unwrap_or(diagnostic.declaration.target.as_str());
        if diagnostic.code == "target-absolute"
            || declared_target.starts_with('/')
            || declared_target.contains("://")
        {
            return Err(SourceDependencyError::new(format!(
                "dependency path must be repository-relative: {declared_target}"
            )));
        }
        if diagnostic.code == "target-escapes-root" {
            let attempted = source.parent().unwrap_or(root).join(declared_target);
            repo_relative(root, &attempted)?;
            continue;
        }
        return Err(SourceDependencyError::new(diagnostic.message.clone()));
    }
    Ok(())
}

fn resolve_target_path(
    root: &Path,
    source: &Path,
    raw_target: &str,
    lexical_target: &Result<String, TargetPathError>,
) -> Result<String, SourceDependencyError> {
    if raw_target.starts_with('/') || raw_target.contains("://") {
        return Err(SourceDependencyError::new(format!(
            "dependency path must be repository-relative: {raw_target}"
        )));
    }
    let attempted = source.parent().unwrap_or(root).join(raw_target);
    let resolved = repo_relative(root, &attempted);
    if matches!(lexical_target, Err(TargetPathError::Absolute)) {
        return Err(SourceDependencyError::new(format!(
            "dependency path must be repository-relative: {raw_target}"
        )));
    }
    resolved
}

fn has_glob_magic(path: &str) -> bool {
    path.chars()
        .any(|character| matches!(character, '*' | '?' | '['))
}

pub(crate) fn fnmatch_case(value: &str, pattern: &str) -> bool {
    python_fnmatch_case(value, pattern)
}

#[cfg(test)]
mod fnmatch_tests {
    use super::fnmatch_case;

    #[test]
    fn character_classes_match_python_leading_close_bracket_rules() {
        assert!(fnmatch_case("]", "[]]"));
        assert!(!fnmatch_case("a", "[]]"));
        assert!(fnmatch_case("a", "[!]]"));
        assert!(!fnmatch_case("]", "[!]]"));
        assert!(fnmatch_case("[]", "[]"));
        assert!(fnmatch_case("[!]", "[!]"));
    }
}

fn resolve_dependency_targets(
    root: &Path,
    source: &Path,
    raw_target: &str,
    lexical_target: &Result<String, TargetPathError>,
    projections: Option<&[GeneratedProjection]>,
) -> Result<Vec<String>, SourceDependencyError> {
    let normalized = resolve_target_path(root, source, raw_target, lexical_target)?;
    if has_glob_magic(&normalized) {
        let owned;
        let projections = match projections {
            Some(projections) => projections,
            None => {
                owned = generated_skill_projections(root).map_err(projection_error)?;
                &owned
            }
        };
        let matches: Vec<&GeneratedProjection> = projections
            .iter()
            .filter(|projection| fnmatch_case(&projection.path, &normalized))
            .collect();
        if !matches.is_empty() {
            return matches
                .into_iter()
                .map(|projection| resolve_generated_view(root, &projection.path, Some(projections)))
                .collect();
        }
    }
    Ok(vec![resolve_generated_view(
        root,
        &normalized,
        projections,
    )?])
}

/// Resolve one dependency declaration target for the checked-in header tool.
pub fn resolve_source_dependency_targets(
    root: &Path,
    source: &Path,
    raw_target: &str,
) -> Result<Vec<String>, SourceDependencyError> {
    let root = absolute_non_strict(root)?;
    let source = if source.is_absolute() {
        source.to_path_buf()
    } else {
        root.join(source)
    };
    let source = absolute_non_strict(&source)?;
    let lexical_target = if raw_target.starts_with('/') || raw_target.contains("://") {
        Err(TargetPathError::Absolute)
    } else {
        Ok(raw_target.to_owned())
    };
    resolve_dependency_targets(&root, &source, raw_target, &lexical_target, None)
}

fn parse_manifest_document_with_projections(
    root: &Path,
    relative: &str,
    projections: Option<&[GeneratedProjection]>,
) -> Result<SourceDependencyDocument, SourceDependencyError> {
    let root = absolute_non_strict(root)?;
    let (canonical, source) = resolve_source_path_with_projections(&root, relative, projections)?;
    let text = read_text(&source, &canonical)?;
    let range = marker_range(&canonical, &text)?;
    let manifest_present = range.is_some();
    if let Some((start, end)) = range {
        for (index, raw_line) in python_lines(&text)
            .into_iter()
            .take(HEADER_SCAN_LINES)
            .enumerate()
        {
            if index < start || index > end {
                continue;
            }
            let line = strip_legacy_line(raw_line);
            let first = line.split_whitespace().next();
            if first.is_some_and(|keyword| {
                matches!(keyword, "contract" | "responsibility" | "coverage")
            }) {
                let keyword = first.unwrap_or_default();
                if !line.starts_with(&format!("{keyword} ")) {
                    return Err(legacy_grammar_error(&canonical, index + 1, &line)
                        .unwrap_or_else(|| {
                            SourceDependencyError::new(format!(
                                "{canonical}:{}: dependency line must be direction kind relative-path reason",
                                index + 1
                            ))
                        }));
                }
            }
        }
    }
    let parser_source = normalized_parser_text(&text, range);
    let parser_path = source.with_extension("py");
    let parsed = parse_dependency_header(&canonical, &parser_path, &parser_source);
    diagnostic_error(&root, &canonical, &source, &parsed)?;
    let mut edges = Vec::new();
    for declaration in parsed.declarations {
        let raw_line = parsed
            .entries
            .iter()
            .find(|(line_number, _)| *line_number == declaration.line_number)
            .map(|(_, line)| line.as_str())
            .unwrap_or(&declaration.line);
        let normalized_line = strip_legacy_line(raw_line);
        let fields = legacy_fields(&normalized_line);
        if fields.len() != MANIFEST_FIELD_COUNT {
            return Err(SourceDependencyError::new(format!(
                "{canonical}:{}: dependency line must be direction kind relative-path reason",
                declaration.line_number
            )));
        }
        let raw_target = fields[2];
        let reason = fields[3].to_string();
        let targets = resolve_dependency_targets(
            &root,
            &source,
            raw_target,
            &declaration.normalized_target,
            projections,
        )?;
        for target in targets {
            edges.push(SourceDependencyEdge {
                source: canonical.clone(),
                direction: declaration.direction.clone(),
                kind: declaration.kind.clone(),
                target,
                reason: reason.clone(),
                line: declaration.line_number,
            });
        }
    }
    Ok(SourceDependencyDocument {
        path: canonical,
        manifest_present,
        edges,
    })
}

/// Parse one source document using the shared native dependency-manifest owner.
pub fn parse_manifest_document(
    root: &Path,
    relative: &str,
) -> Result<SourceDependencyDocument, SourceDependencyError> {
    parse_manifest_document_with_projections(root, relative, None)
}

/// Return the normalized dependency edges for one source document.
pub fn parse_manifest_edges(
    root: &Path,
    relative: &str,
) -> Result<Vec<SourceDependencyEdge>, SourceDependencyError> {
    Ok(parse_manifest_document(root, relative)?.edges)
}

/// Return every unique canonical text document and its dependency-manifest projection.
pub fn dependency_documents(
    root: &Path,
) -> Result<Vec<SourceDependencyDocument>, SourceDependencyError> {
    let root = absolute_non_strict(root)?;
    let projections = generated_skill_projections(&root).map_err(projection_error)?;
    let mut documents = Vec::new();
    let mut canonical_sources = BTreeSet::new();
    for relative in source_paths(&root)? {
        if !is_text_source(&relative) || canonical_sources.contains(&relative) {
            continue;
        }
        let Ok((canonical, _)) =
            resolve_source_path_with_projections(&root, &relative, Some(&projections))
        else {
            // Git links, deleted paths, and unavailable generated views are not text sources.
            continue;
        };
        if canonical_sources.contains(&canonical) {
            continue;
        }
        canonical_sources.insert(canonical.clone());
        documents.push(parse_manifest_document_with_projections(
            &root,
            &canonical,
            Some(&projections),
        )?);
    }
    documents.sort();
    Ok(documents)
}

/// Return every unique source-declared dependency edge.
pub fn dependency_edges(root: &Path) -> Result<Vec<SourceDependencyEdge>, SourceDependencyError> {
    let edges: BTreeSet<SourceDependencyEdge> = dependency_documents(root)?
        .into_iter()
        .flat_map(|document| document.edges)
        .collect();
    Ok(edges.into_iter().collect())
}

/// Return canonical text source paths containing a complete manifest block.
pub fn dependency_manifest_paths(root: &Path) -> Result<Vec<String>, SourceDependencyError> {
    Ok(dependency_documents(root)?
        .into_iter()
        .filter(|document| document.manifest_present)
        .map(|document| document.path)
        .collect())
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn stable_id(prefix: &str, values: &[Value]) -> Result<String, SourceDependencyError> {
    let mut record = Vec::with_capacity(values.len() + 1);
    record.push(Value::String(prefix.to_string()));
    record.extend_from_slice(values);
    let bytes = serde_json::to_vec(&Value::Array(record))
        .map_err(|error| SourceDependencyError::new(error.to_string()))?;
    Ok(format!("{prefix}:{}", sha256_hex(&bytes)))
}

/// Build a graph-query-compatible projection from current tracked source bytes.
pub fn build_dependency_projection(
    root: &Path,
) -> Result<SourceDependencyProjection, SourceDependencyError> {
    let edges = dependency_edges(root)?;
    let paths: BTreeSet<String> = edges
        .iter()
        .flat_map(|edge| [edge.source.clone(), edge.target.clone()])
        .collect();
    let mut node_ids = BTreeMap::new();
    let mut nodes = Vec::new();
    for path in paths {
        let id = stable_id("node", &[Value::String(path.clone())])?;
        node_ids.insert(path.clone(), id.clone());
        nodes.push(json!({"id": id, "path": path}));
    }
    let mut facts = Vec::new();
    for edge in edges {
        let fact_id = stable_id(
            "dependency",
            &[
                Value::String(edge.source.clone()),
                Value::String(edge.direction.clone()),
                Value::String(edge.kind.clone()),
                Value::String(edge.target.clone()),
                Value::String(edge.reason.clone()),
                json!(edge.line),
            ],
        )?;
        let from = node_ids.get(&edge.source).ok_or_else(|| {
            SourceDependencyError::new(format!("missing source node: {}", edge.source))
        })?;
        let to = node_ids.get(&edge.target).ok_or_else(|| {
            SourceDependencyError::new(format!("missing target node: {}", edge.target))
        })?;
        facts.push(json!({
            "id": fact_id,
            "kind": "dependency",
            "inferred": false,
            "from": from,
            "to": to,
            "producer": "tracked-source-manifest",
            "source_path": edge.source,
            "source_span": {
                "path": edge.source,
                "start_line": edge.line,
                "start_column": 1,
                "end_line": edge.line,
                "end_column": 1
            },
            "evidence_ref": format!("{}:{}", edge.source, edge.line),
            "authority": "tracked-source",
            "dependency_detail": {
                "direction": edge.direction,
                "kind": edge.kind,
                "reason": edge.reason
            }
        }));
    }
    let fingerprint_bytes = serde_json::to_vec(&Value::Array(facts.clone()))
        .map_err(|error| SourceDependencyError::new(error.to_string()))?;
    Ok(SourceDependencyProjection {
        nodes,
        facts,
        fingerprint: sha256_hex(&fingerprint_bytes),
    })
}

fn snapshot_commit(root: &Path) -> Result<String, SourceDependencyError> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["rev-parse", "HEAD"])
        .output()
        .map_err(|error| io_error("git rev-parse HEAD unavailable", error))?;
    let candidate = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if output.status.success() && !candidate.is_empty() {
        Ok(candidate)
    } else {
        Ok("working-tree".to_string())
    }
}

fn dependency_indexes(
    edges: &[SourceDependencyEdge],
) -> (
    BTreeMap<String, Vec<SourceDependencyEdge>>,
    BTreeMap<String, Vec<SourceDependencyEdge>>,
) {
    let mut outgoing: BTreeMap<String, Vec<SourceDependencyEdge>> = BTreeMap::new();
    let mut incoming: BTreeMap<String, Vec<SourceDependencyEdge>> = BTreeMap::new();
    for edge in edges {
        outgoing
            .entry(edge.source.clone())
            .or_default()
            .push(edge.clone());
        incoming
            .entry(edge.target.clone())
            .or_default()
            .push(edge.clone());
    }
    for values in outgoing.values_mut().chain(incoming.values_mut()) {
        values.sort();
    }
    (outgoing, incoming)
}

/// Build deterministic dependency evidence context from tracked source manifests.
pub fn build_context_projection(
    root: &Path,
    path: &str,
    depth: i64,
) -> Result<SourceContextProjection, SourceDependencyError> {
    if depth < 0 {
        return Err(SourceDependencyError::new(
            "context depth must be non-negative",
        ));
    }
    let depth = usize::try_from(depth)
        .map_err(|_| SourceDependencyError::new("context depth is out of range"))?;
    let root = absolute_non_strict(root)?;
    let (resolved_path, source) = resolve_source_path(&root, path)?;
    let text = read_text(&source, &resolved_path)?;
    let edges = dependency_edges(&root)?;
    let (outgoing, incoming) = dependency_indexes(&edges);
    let mut evidence = BTreeSet::from([resolved_path.clone()]);
    let mut parents = BTreeSet::new();
    let mut visited = BTreeSet::new();
    let mut queue = VecDeque::new();
    queue.push_back((resolved_path.clone(), 0usize));
    while let Some((current, current_depth)) = queue.pop_front() {
        if visited.contains(&current) || current_depth > depth {
            continue;
        }
        visited.insert(current.clone());
        let mut related = outgoing.get(&current).cloned().unwrap_or_default();
        related.extend(incoming.get(&current).cloned().unwrap_or_default());
        related.sort();
        for edge in related {
            if !CONTEXT_KINDS.contains(&edge.kind.as_str()) {
                continue;
            }
            let next_path = if edge.source == current {
                edge.target.clone()
            } else {
                edge.source.clone()
            };
            if next_path == resolved_path {
                continue;
            }
            evidence.insert(next_path.clone());
            if edge.source == resolved_path && edge.direction == "upstream" && edge.kind == "design"
            {
                parents.insert(next_path.clone());
            }
            if current_depth < depth {
                queue.push_back((next_path, current_depth + 1));
            }
        }
    }
    let projection = build_dependency_projection(&root)?;
    Ok(SourceContextProjection {
        resolved_path,
        snapshot_commit: snapshot_commit(&root)?,
        content_sha256: sha256_hex(text.as_bytes()),
        evidence_paths: evidence.into_iter().collect(),
        parent_paths: parents.into_iter().collect(),
        fingerprint: projection.fingerprint,
    })
}

/// Build context with the source projection's default depth of three edges.
pub fn build_context_projection_default(
    root: &Path,
    path: &str,
) -> Result<SourceContextProjection, SourceDependencyError> {
    build_context_projection(root, path, DEFAULT_CONTEXT_DEPTH as i64)
}

/// Write deterministic review inputs into caller-owned scratch paths.
pub fn write_review_projection(
    root: &Path,
    edges_out: &Path,
    manifests_out: &Path,
) -> Result<(), SourceDependencyError> {
    let documents = dependency_documents(root)?;
    let edges: BTreeSet<SourceDependencyEdge> = documents
        .iter()
        .flat_map(|document| document.edges.iter().cloned())
        .collect();
    let manifests: Vec<String> = documents
        .iter()
        .filter(|document| document.manifest_present)
        .map(|document| document.path.clone())
        .collect();
    let edge_lines: Vec<String> = edges
        .iter()
        .map(|edge| {
            [
                edge.direction.as_str(),
                edge.kind.as_str(),
                edge.source.as_str(),
                edge.target.as_str(),
            ]
            .join("\t")
        })
        .collect();
    let edge_text = if edge_lines.is_empty() {
        String::new()
    } else {
        format!("{}\n", edge_lines.join("\n"))
    };
    let manifest_text = if manifests.is_empty() {
        String::new()
    } else {
        format!("{}\n", manifests.join("\n"))
    };
    for output in [edges_out, manifests_out] {
        if let Some(parent) = output
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            fs::create_dir_all(parent)
                .map_err(|error| io_error(parent.display().to_string(), error))?;
        }
    }
    fs::write(edges_out, edge_text)
        .map_err(|error| io_error(edges_out.display().to_string(), error))?;
    fs::write(manifests_out, manifest_text)
        .map_err(|error| io_error(manifests_out.display().to_string(), error))?;
    Ok(())
}

#[derive(Debug, Default)]
struct CliArgs {
    root: Option<PathBuf>,
    edges_out: Option<PathBuf>,
    manifests_out: Option<PathBuf>,
    help: bool,
}

impl CliArgs {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut parsed = Self::default();
        let mut index = 0;
        while index < args.len() {
            let argument = &args[index];
            if matches!(argument.as_str(), "-h" | "--help") {
                parsed.help = true;
                return Ok(parsed);
            }
            let (name, inline) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value))
                });
            let slot = match name {
                "--root" => &mut parsed.root,
                "--edges-out" => &mut parsed.edges_out,
                "--manifests-out" => &mut parsed.manifests_out,
                _ => return Err(format!("unrecognized arguments: {argument}")),
            };
            let value = match inline {
                Some(value) if !value.is_empty() => value.to_string(),
                Some(_) => return Err(format!("argument {name}: expected one argument")),
                None => {
                    let Some(value) = args.get(index + 1) else {
                        return Err(format!("argument {name}: expected one argument"));
                    };
                    if value.starts_with('-') {
                        return Err(format!("argument {name}: expected one argument"));
                    }
                    index += 1;
                    value.clone()
                }
            };
            *slot = Some(PathBuf::from(value));
            index += 1;
        }
        let missing: Vec<&str> = [
            ("--root", parsed.root.is_none()),
            ("--edges-out", parsed.edges_out.is_none()),
            ("--manifests-out", parsed.manifests_out.is_none()),
        ]
        .into_iter()
        .filter_map(|(name, absent)| absent.then_some(name))
        .collect();
        if !missing.is_empty() {
            return Err(format!(
                "the following arguments are required: {}",
                missing.join(", ")
            ));
        }
        Ok(parsed)
    }
}

/// Run the native source-dependency review export and target-resolution commands.
pub fn run(args: &[String]) -> i32 {
    if args
        .first()
        .is_some_and(|argument| argument == "resolve-targets")
    {
        return run_resolve_targets(&args[1..]);
    }
    let args = match CliArgs::parse(args) {
        Ok(args) => args,
        Err(message) => {
            eprintln!("{SOURCE_DEPENDENCY_USAGE}");
            eprintln!("source-dependency-graph: error: {message}");
            return 2;
        }
    };
    if args.help {
        println!("{SOURCE_DEPENDENCY_HELP}");
        return 0;
    }
    let (Some(root), Some(edges_out), Some(manifests_out)) =
        (args.root, args.edges_out, args.manifests_out)
    else {
        eprintln!("{SOURCE_DEPENDENCY_USAGE}");
        eprintln!("source-dependency-graph: error: required arguments are missing");
        return 2;
    };
    let result = (|| {
        let root = absolute_non_strict(&root)?;
        let edges_out = absolute_non_strict(&edges_out)?;
        let manifests_out = absolute_non_strict(&manifests_out)?;
        write_review_projection(&root, &edges_out, &manifests_out)
    })();
    if let Err(error) = result {
        eprintln!("SOURCE_DEPENDENCY_EXPORT=fail reason={error}");
        return 1;
    }
    println!("SOURCE_DEPENDENCY_EXPORT=pass authority=tracked-source");
    0
}

fn run_resolve_targets(args: &[String]) -> i32 {
    let mut root = None;
    let mut source = None;
    let mut target = None;
    let mut help = false;
    let mut index = 0;
    while index < args.len() {
        let option = args[index].as_str();
        if matches!(option, "-h" | "--help") {
            help = true;
            break;
        }
        let Some(value) = args.get(index + 1) else {
            eprintln!("usage: agent-canon source-dependency-graph resolve-targets --root ROOT --source FILE --target PATH");
            eprintln!("source-dependency-graph: error: {option}: expected one argument");
            return 2;
        };
        match option {
            "--root" => root = Some(PathBuf::from(value)),
            "--source" => source = Some(PathBuf::from(value)),
            "--target" => target = Some(value.clone()),
            _ => {
                eprintln!("usage: agent-canon source-dependency-graph resolve-targets --root ROOT --source FILE --target PATH");
                eprintln!("source-dependency-graph: error: unrecognized argument: {option}");
                return 2;
            }
        }
        index += 2;
    }
    if help {
        println!("Resolve one tracked-source dependency target, including generated skill views.\nusage: agent-canon source-dependency-graph resolve-targets --root ROOT --source FILE --target PATH");
        return 0;
    }
    let (Some(root), Some(source), Some(target)) = (root, source, target) else {
        eprintln!("usage: agent-canon source-dependency-graph resolve-targets --root ROOT --source FILE --target PATH");
        eprintln!("source-dependency-graph: error: --root, --source, and --target are required");
        return 2;
    };
    match resolve_source_dependency_targets(&root, &source, &target) {
        Ok(paths) => {
            for path in paths {
                println!("{path}");
            }
            0
        }
        Err(error) => {
            let message = error.to_string();
            if let Some(unmatched) = message.strip_prefix("unknown generated skill view: ") {
                println!("{unmatched}");
                return 0;
            }
            eprintln!("{message}");
            1
        }
    }
}

#[cfg(test)]
mod snapshot_tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn supplied_snapshot_survives_catalog_changes_and_empty_snapshot_stays_empty() {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "source-projection-snapshot-{}-{nonce}",
            std::process::id()
        ));
        let catalog = root.join("agents/skills/catalog.yaml");
        fs::create_dir_all(catalog.parent().unwrap()).unwrap();
        fs::write(&catalog, "skill_families:\n  - id: example\n    canonical_doc: agents/skills/example.md\n    shim: .codex/personal/skills/example/SKILL.md\n").unwrap();
        fs::write(root.join("agents/skills/example.md"), "# Example\n").unwrap();
        fs::write(root.join("a.py"), "# @dependency-start\n# contract test\n# responsibility Declares an ordinary dependency.\n# downstream implementation b.py ordinary target\n# @dependency-end\n").unwrap();
        fs::write(root.join("b.py"), "# Ordinary target\n").unwrap();
        let snapshot = generated_skill_projections(&root).unwrap();
        fs::write(&catalog, "invalid catalog\n").unwrap();

        let generated = ".codex/personal/skills/example/SKILL.md";
        let document =
            parse_manifest_document_with_projections(&root, generated, Some(&snapshot)).unwrap();
        assert_eq!(document.path, "agents/skills/example.md");
        let error =
            parse_manifest_document_with_projections(&root, generated, Some(&[])).unwrap_err();
        assert!(
            error.to_string().contains("unknown generated skill"),
            "{error}"
        );
        assert!(parse_manifest_document(&root, generated)
            .unwrap_err()
            .to_string()
            .contains("skill catalog"));

        assert_eq!(resolve_source_path(&root, "a.py").unwrap().0, "a.py");
        let ordinary = parse_manifest_document(&root, "a.py").unwrap();
        assert_eq!(ordinary.edges[0].target, "b.py");
        assert_eq!(
            resolve_source_dependency_targets(&root, &root.join("a.py"), "b.py").unwrap(),
            vec!["b.py"]
        );
        fs::remove_dir_all(&root).unwrap();
    }
}
