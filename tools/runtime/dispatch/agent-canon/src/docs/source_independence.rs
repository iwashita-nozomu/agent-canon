// @dependency-start
// contract implementation
// responsibility Checks a consumer's Git index against its source independence policy.
// upstream design ../../../../../../documents/tools/agent-canon.md consumer check interfaces
// upstream implementation ../git_read.rs Git index entries and blob bytes
// downstream implementation ../docs.rs check-bootstrap policy selection
// @dependency-end

use crate::git_read::{index_entries, repository_bytes, require_repository_root};
use regex::bytes::Regex;
use serde::Deserialize;
use std::path::Path;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Policy {
    source_name_pattern: String,
    #[serde(default)]
    forbidden_paths: Vec<String>,
    #[serde(default)]
    forbidden_path_fragments: Vec<String>,
    #[serde(default)]
    references: Vec<ReferenceRule>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReferenceRule {
    paths: Vec<String>,
    #[serde(default)]
    allow_paths: Vec<String>,
    forbidden: Vec<String>,
}

pub(super) fn check(root: &Path, policy_path: &Path) -> Result<Vec<String>, String> {
    let root = root.canonicalize().map_err(|error| error.to_string())?;
    require_repository_root(&root)?;
    let policy_file = root
        .join(policy_path)
        .canonicalize()
        .map_err(|error| format!("source policy {}: {error}", policy_path.display()))?;
    if !policy_file.starts_with(&root) || !policy_file.is_file() {
        return Err("source policy must be a file within the repository".into());
    }
    let text = std::fs::read_to_string(&policy_file)
        .map_err(|error| format!("{}: {error}", policy_file.display()))?;
    let policy: Policy = toml_edit::de::from_str(&text)
        .map_err(|error| format!("invalid source policy: {error}"))?;
    policy.validate()?;
    let source_name = Regex::new(&policy.source_name_pattern)
        .map_err(|error| format!("invalid source_name_pattern: {error}"))?;
    let mut findings = Vec::new();
    for entry in index_entries(&root)? {
        let path = &entry.path;
        if policy
            .forbidden_paths
            .iter()
            .any(|prefix| includes(prefix, path))
            || policy
                .forbidden_path_fragments
                .iter()
                .any(|fragment| contains(path.as_bytes(), fragment))
        {
            findings.push(format!("forbidden-source-path: {path}"));
        }
        let name_matches = source_name.is_match(path.as_bytes());
        match entry.mode.as_str() {
            "160000" if name_matches => findings.push(format!("forbidden-source-gitlink: {path}")),
            "120000" => {
                let target = repository_bytes(&root, &["cat-file", "blob", &entry.object])?;
                if name_matches || source_name.is_match(&target) {
                    findings.push(format!("forbidden-source-symlink: {path}"));
                }
            }
            "100644" | "100755" => {
                let mut rules = policy
                    .references
                    .iter()
                    .filter(|rule| rule.applies_to(path))
                    .peekable();
                if path != ".gitmodules" && rules.peek().is_none() {
                    continue;
                }
                let content = repository_bytes(&root, &["cat-file", "blob", &entry.object])?;
                if path == ".gitmodules" && source_name.is_match(&content) {
                    findings.push(format!("forbidden-source-submodule: {path}"));
                }
                for token in rules.flat_map(|rule| &rule.forbidden) {
                    if contains(&content, token) {
                        findings.push(format!("forbidden-source-reference: {path}: {token}"));
                    }
                }
            }
            _ => {}
        }
    }
    Ok(findings)
}

impl Policy {
    fn validate(&self) -> Result<(), String> {
        if self.source_name_pattern.trim().is_empty() {
            return Err("source_name_pattern must be nonempty".into());
        }
        for path in self.forbidden_paths.iter().chain(
            self.references
                .iter()
                .flat_map(|rule| rule.paths.iter().chain(&rule.allow_paths)),
        ) {
            if path.contains('\\') || path.split('/').any(|part| matches!(part, "" | "." | "..")) {
                return Err(format!("expected a repository-relative path: {path}"));
            }
        }
        if self
            .references
            .iter()
            .any(|rule| rule.paths.is_empty() || rule.forbidden.is_empty())
            || self
                .forbidden_path_fragments
                .iter()
                .chain(self.references.iter().flat_map(|rule| &rule.forbidden))
                .any(|token| token.trim().is_empty())
        {
            return Err("source policy rules must select paths and nonempty tokens".into());
        }
        Ok(())
    }
}

impl ReferenceRule {
    fn applies_to(&self, path: &str) -> bool {
        self.paths.iter().any(|prefix| includes(prefix, path))
            && !self.allow_paths.iter().any(|allowed| allowed == path)
    }
}

fn includes(prefix: &str, path: &str) -> bool {
    path == prefix
        || path
            .strip_prefix(prefix)
            .is_some_and(|tail| tail.starts_with('/'))
}

fn contains(bytes: &[u8], token: &str) -> bool {
    bytes
        .windows(token.len())
        .any(|window| window.eq_ignore_ascii_case(token.as_bytes()))
}
