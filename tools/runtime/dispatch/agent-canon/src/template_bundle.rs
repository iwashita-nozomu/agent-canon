//! Git-bound template profile export, source-free Codex projection, and native packages.
// @dependency-start
// contract implementation
// responsibility Exports source-commit-bound template profiles and produces/verifies deterministic native CLI packages.
// upstream design ../../../../../documents/contracts/template-bundle-manifest.toml profile roots and native package layout
// upstream implementation entrypoint_composer.rs canonical guidance composition
// downstream implementation lib.rs shared native Template library
// downstream implementation main.rs template-bundle CLI route
// downstream implementation native_release.rs source-bound release package verifier
// downstream test template_tests.rs profile, Codex and native package oracles
// downstream test ../tests/native_release_native.rs source-bound native release oracles
// @dependency-end

use crate::entrypoint_composer::Composition;
use flate2::read::GzDecoder;
use flate2::{Compression, GzBuilder};
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Map as JsonMap, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;
use tar::{Archive as TarArchive, Builder as TarBuilder, EntryType, Header as TarHeader};
use toml_edit::{DocumentMut, Item};
use zip::write::SimpleFileOptions;
use zip::{CompressionMethod, DateTime, System as ZipSystem, ZipArchive, ZipWriter};

const MANIFEST: &str = "documents/contracts/template-bundle-manifest.toml";
const CODEX_USER_PROFILE: &str = "codex-user";
const CODEX_USER_SCHEMA: &str = "agent-canon.codex-user-bundle.v1";
const CODEX_USER_MANIFEST: &str = "codex-user-bundle.json";
const CODEX_MARKETPLACE: &str = ".agents/plugins/marketplace.json";
const NATIVE_CLI_PROFILE: &str = "native-cli";
const NATIVE_CLI_CARGO_MANIFEST: &str = "tools/runtime/dispatch/agent-canon/Cargo.toml";
const NATIVE_CLI_SCHEMA: &str = "agent-canon.native-cli-package.v1";
const HEX_40: usize = 40;
const HEX_64: usize = 64;

/// An invalid or unreadable template bundle operation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TemplateBundleError(pub(crate) String);

impl fmt::Display for TemplateBundleError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for TemplateBundleError {}

pub(crate) type BundleResult<T> = Result<T, TemplateBundleError>;
type Payload = BTreeMap<String, Vec<u8>>;
type PayloadModes = BTreeMap<String, String>;

fn bundle_error(message: impl Into<String>) -> TemplateBundleError {
    TemplateBundleError(message.into())
}

fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn valid_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn json_bytes(value: &Value) -> BundleResult<Vec<u8>> {
    serde_json::to_vec_pretty(value)
        .map(|mut bytes| {
            bytes.push(b'\n');
            bytes
        })
        .map_err(|_| bundle_error("JSON serialization failed"))
}

fn object() -> Value {
    Value::Object(JsonMap::new())
}

fn set(object: &mut Value, key: &str, value: Value) -> BundleResult<()> {
    object
        .as_object_mut()
        .ok_or_else(|| bundle_error("internal JSON object is invalid"))?
        .insert(key.to_owned(), value);
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TreeEntry {
    path: String,
    mode: String,
}

struct BundleIdentityWork {
    identity: Value,
    commit: String,
    entries: Vec<TreeEntry>,
    payload: Payload,
    payload_modes: PayloadModes,
    install_files: Vec<Value>,
}

struct GitSource {
    root: PathBuf,
}

impl GitSource {
    fn open(root: &Path) -> BundleResult<Self> {
        let root = fs::canonicalize(root).map_err(|error| {
            bundle_error(format!(
                "canonicalize source root {}: {error}",
                root.display()
            ))
        })?;
        let metadata = fs::symlink_metadata(&root).map_err(|error| {
            bundle_error(format!("inspect source root {}: {error}", root.display()))
        })?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(bundle_error("source root is missing or unsafe"));
        }
        Ok(Self { root })
    }

    fn git(&self, args: &[String]) -> BundleResult<Vec<u8>> {
        let output = Command::new("git")
            .arg("-C")
            .arg(&self.root)
            .args(args)
            .output()
            .map_err(|error| bundle_error(error.to_string()))?;
        if !output.status.success() {
            let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            return Err(bundle_error(if detail.is_empty() {
                "git command failed".to_owned()
            } else {
                detail
            }));
        }
        Ok(output.stdout)
    }

    fn commit(&self, reference: &str) -> BundleResult<String> {
        let value = self.git(&[
            "rev-parse".to_owned(),
            "--verify".to_owned(),
            "--end-of-options".to_owned(),
            format!("{reference}^{{commit}}"),
        ])?;
        let commit = String::from_utf8_lossy(&value).trim().to_owned();
        if !valid_hex(&commit, HEX_40) {
            return Err(bundle_error("invalid source commit"));
        }
        Ok(commit)
    }

    fn tree(&self, commit: &str) -> BundleResult<String> {
        let value = self.git(&[
            "rev-parse".to_owned(),
            "--verify".to_owned(),
            format!("{commit}^{{tree}}"),
        ])?;
        let tree = String::from_utf8_lossy(&value).trim().to_owned();
        if !valid_hex(&tree, HEX_40) {
            return Err(bundle_error("invalid source tree"));
        }
        Ok(tree)
    }

    fn blob(&self, commit: &str, path: &str) -> BundleResult<Vec<u8>> {
        self.git(&["show".to_owned(), format!("{commit}:{path}")])
    }

    fn entries(&self, commit: &str) -> BundleResult<Vec<TreeEntry>> {
        let output = self.git(&[
            "ls-tree".to_owned(),
            "-r".to_owned(),
            "-z".to_owned(),
            commit.to_owned(),
        ])?;
        let mut entries = Vec::new();
        for record in output
            .split(|byte| *byte == 0)
            .filter(|record| !record.is_empty())
        {
            let tab = record
                .iter()
                .position(|byte| *byte == b'\t')
                .ok_or_else(|| bundle_error("git tree entry is invalid"))?;
            let metadata = std::str::from_utf8(&record[..tab])
                .map_err(|_| bundle_error("git tree entry is invalid"))?;
            let mut fields = metadata.split(' ');
            let mode = fields
                .next()
                .ok_or_else(|| bundle_error("git tree entry is invalid"))?;
            let kind = fields
                .next()
                .ok_or_else(|| bundle_error("git tree entry is invalid"))?;
            if kind == "blob" {
                let path = std::str::from_utf8(&record[tab + 1..])
                    .map_err(|_| bundle_error("git tree path is not UTF-8"))?;
                entries.push(TreeEntry {
                    path: path.to_owned(),
                    mode: mode.to_owned(),
                });
            }
        }
        entries.sort_by(|left, right| left.path.cmp(&right.path));
        Ok(entries)
    }

    fn resolve_profile(&self, commit: &str) -> BundleResult<(DocumentMut, String)> {
        let raw = self.blob(commit, MANIFEST)?;
        let text = std::str::from_utf8(&raw)
            .map_err(|_| bundle_error("template bundle manifest is invalid"))?;
        let document = text
            .parse::<DocumentMut>()
            .map_err(|_| bundle_error("template bundle manifest is invalid"))?;
        if document.get("version").and_then(Item::as_integer) != Some(1) {
            return Err(bundle_error("template bundle manifest version must be 1"));
        }
        if document.get("profiles").and_then(Item::as_table).is_none() {
            return Err(bundle_error("template bundle profiles are missing"));
        }
        Ok((document, digest(&raw)))
    }

    fn roots(document: &DocumentMut, profile: &str) -> BundleResult<Vec<String>> {
        let profile_item = document
            .get("profiles")
            .and_then(Item::as_table)
            .and_then(|profiles| profiles.get(profile))
            .and_then(Item::as_table);
        let Some(roots) = profile_item
            .and_then(|profile| profile.get("roots"))
            .and_then(Item::as_array)
        else {
            return Err(bundle_error(format!("unknown template profile: {profile}")));
        };
        Ok(roots
            .iter()
            .map(|root| {
                root.as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| root.to_string())
            })
            .collect())
    }

    fn selected_entries(&self, commit: &str, roots: &[String]) -> BundleResult<Vec<TreeEntry>> {
        Ok(self
            .entries(commit)?
            .into_iter()
            .filter(|entry| {
                roots
                    .iter()
                    .any(|root| entry.path == *root || entry.path.starts_with(&format!("{root}/")))
            })
            .collect())
    }
}

fn portable_relative(value: &str) -> BundleResult<Vec<&str>> {
    let reserved = |stem: &str| {
        let upper = stem.to_ascii_uppercase();
        matches!(upper.as_str(), "CON" | "PRN" | "AUX" | "NUL")
            || ["COM", "LPT"].iter().any(|prefix| {
                upper.strip_prefix(prefix).is_some_and(|suffix| {
                    suffix.len() == 1 && matches!(suffix.as_bytes()[0], b'1'..=b'9')
                })
            })
    };
    let parts = value.split('/').collect::<Vec<_>>();
    let unsafe_value = value.is_empty()
        || value.starts_with('/')
        || value.ends_with('/')
        || value.contains("//")
        || value
            .chars()
            .any(|character| character.is_control() || "\\:<\">|?*".contains(character))
        || parts.iter().any(|part| {
            part.is_empty()
                || matches!(*part, "." | "..")
                || part.trim_end_matches([' ', '.']) != *part
                || reserved(part.split('.').next().unwrap_or(part).trim_end_matches(' '))
        });
    if unsafe_value {
        return Err(bundle_error(format!("unsafe bundle file path: {value}")));
    }
    Ok(parts)
}

fn canonicalize_allow_missing(path: &Path) -> io::Result<PathBuf> {
    let mut missing = Vec::new();
    let mut cursor = path;
    loop {
        match fs::canonicalize(cursor) {
            Ok(mut resolved) => {
                for component in missing.iter().rev() {
                    resolved.push(component);
                }
                return Ok(resolved);
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                if let Ok(metadata) = fs::symlink_metadata(cursor) {
                    if metadata.file_type().is_symlink() {
                        let link = fs::read_link(cursor)?;
                        let mut target = if link.is_absolute() {
                            link
                        } else {
                            cursor.parent().unwrap_or(Path::new(".")).join(link)
                        };
                        for component in missing.iter().rev() {
                            target.push(component);
                        }
                        return canonicalize_allow_missing(&target);
                    }
                }
                let Some(name) = cursor.file_name() else {
                    return Err(error);
                };
                missing.push(name.to_os_string());
                cursor = cursor.parent().ok_or(error)?;
            }
            Err(error) => return Err(error),
        }
    }
}

pub(crate) fn bundle_destination(root: &Path, relative: &str) -> BundleResult<PathBuf> {
    let parts = portable_relative(relative)?;
    let destination = parts
        .iter()
        .fold(root.to_path_buf(), |path, part| path.join(part));
    let canonical_root = canonicalize_allow_missing(root).map_err(|error| {
        bundle_error(format!("resolve bundle root {}: {error}", root.display()))
    })?;
    let resolved = canonicalize_allow_missing(&destination)
        .map_err(|error| bundle_error(format!("resolve bundle file {relative}: {error}")))?;
    if !resolved.starts_with(&canonical_root) {
        return Err(bundle_error(format!(
            "bundle file escapes output: {relative}"
        )));
    }
    Ok(destination)
}

fn entries_for_roots(
    source: &GitSource,
    commit: &str,
    roots: &[String],
) -> BundleResult<Vec<TreeEntry>> {
    source.selected_entries(commit, roots)
}

fn mode_is_regular(mode: &str) -> bool {
    matches!(mode, "100644" | "100755")
}

fn mode_number(mode: &str) -> u32 {
    if mode == "100755" {
        0o755
    } else {
        0o644
    }
}

fn is_template_asset(path: &str, template_roots: &[String]) -> bool {
    template_roots
        .iter()
        .any(|root| path == root || path.starts_with(&format!("{root}/")))
}

fn regex(pattern: &'static str) -> Regex {
    static REGEXES: OnceLock<std::sync::Mutex<BTreeMap<&'static str, Regex>>> = OnceLock::new();
    let cache = REGEXES.get_or_init(|| std::sync::Mutex::new(BTreeMap::new()));
    let mut guard = cache.lock().expect("regex cache poisoned");
    guard
        .entry(pattern)
        .or_insert_with(|| Regex::new(pattern).expect("fixed regular expression is valid"))
        .clone()
}

#[derive(Clone, Debug)]
struct MarkdownDestination {
    start: usize,
    end: usize,
    target: String,
}

fn inline_code_spans(line: &str) -> Vec<(usize, usize)> {
    let bytes = line.as_bytes();
    let mut spans = Vec::new();
    let mut cursor = 0;
    while cursor < bytes.len() {
        if bytes[cursor] != b'`' {
            cursor += 1;
            continue;
        }
        let start = cursor;
        while cursor < bytes.len() && bytes[cursor] == b'`' {
            cursor += 1;
        }
        let delimiter_len = cursor - start;
        let mut search = cursor;
        let mut closing = None;
        while search < bytes.len() {
            let Some(relative) = bytes[search..].iter().position(|byte| *byte == b'`') else {
                break;
            };
            let candidate = search + relative;
            let mut end = candidate;
            while end < bytes.len() && bytes[end] == b'`' {
                end += 1;
            }
            if end - candidate == delimiter_len {
                closing = Some(end);
                break;
            }
            search = end;
        }
        if let Some(end) = closing {
            spans.push((start, end));
            cursor = end;
        }
    }
    spans
}

fn markdown_destinations(text: &str) -> BundleResult<Vec<MarkdownDestination>> {
    let link_start = regex(r"\]\([ \t]*|^ {0,3}\[[^\]\n]+\]:[ \t]*");
    let fence_start = regex(r"^ {0,3}(`{3,}|~{3,})");
    let mut destinations = Vec::new();
    let mut offset = 0;
    let mut fence: Option<(u8, usize)> = None;
    let frontmatter = text.starts_with("---\n");
    let mut in_frontmatter = frontmatter;
    for (line_number, line_with_ending) in text.split_inclusive('\n').enumerate() {
        let line = line_with_ending;
        if in_frontmatter {
            if line_number > 0 && matches!(line.trim(), "---" | "..." | "---\r" | "...\r") {
                in_frontmatter = false;
            }
            offset += line.len();
            continue;
        }
        if let Some(marker) = fence_start.captures(line) {
            let delimiter = marker
                .get(1)
                .expect("capture is present")
                .as_str()
                .as_bytes();
            let current = (delimiter[0], delimiter.len());
            match fence {
                None => fence = Some(current),
                Some((character, length)) if current.0 == character && current.1 >= length => {
                    fence = None
                }
                _ => {}
            }
            offset += line.len();
            continue;
        }
        if fence.is_none() {
            let code_spans = inline_code_spans(line);
            for marker in link_start.find_iter(line) {
                if code_spans
                    .iter()
                    .any(|(start, end)| *start <= marker.start() && marker.start() < *end)
                {
                    continue;
                }
                let mut start = marker.end();
                let mut end = start;
                if line.as_bytes().get(start) == Some(&b'<') {
                    start += 1;
                    end = line[start..]
                        .find('>')
                        .map(|relative| start + relative)
                        .ok_or_else(|| bundle_error("unterminated Markdown resource"))?;
                } else {
                    let bytes = line.as_bytes();
                    let mut depth = 0usize;
                    while end < bytes.len() && !bytes[end].is_ascii_whitespace() {
                        match bytes[end] {
                            b'\\' => end = (end + 2).min(bytes.len()),
                            b')' if depth == 0 => break,
                            b')' => {
                                depth -= 1;
                                end += 1;
                            }
                            b'(' => {
                                depth += 1;
                                end += 1;
                            }
                            _ => end += 1,
                        }
                    }
                }
                if end > start {
                    destinations.push(MarkdownDestination {
                        start: offset + start,
                        end: offset + end,
                        target: line[start..end].to_owned(),
                    });
                }
            }
        }
        offset += line.len();
    }
    Ok(destinations)
}

struct ParsedTarget<'a> {
    path: &'a str,
    query: &'a str,
    fragment: &'a str,
    is_external: bool,
}

fn split_target(target: &str) -> ParsedTarget<'_> {
    let (without_fragment, fragment) = match target.split_once('#') {
        Some((path, fragment)) => (path, fragment),
        None => (target, ""),
    };
    let (path, query) = match without_fragment.split_once('?') {
        Some((path, query)) => (path, query),
        None => (without_fragment, ""),
    };
    let before_slash = path.split('/').next().unwrap_or(path);
    let scheme = before_slash.split_once(':').is_some_and(|(name, _)| {
        !name.is_empty()
            && name.as_bytes()[0].is_ascii_alphabetic()
            && name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'.' | b'-'))
    });
    ParsedTarget {
        path,
        query,
        fragment,
        is_external: scheme || target.starts_with("//"),
    }
}

fn percent_unquote(path: &str) -> String {
    let input = path.as_bytes();
    let mut bytes = Vec::with_capacity(input.len());
    let mut index = 0;
    while index < input.len() {
        if input[index] == b'%' && index + 2 < input.len() {
            let hex = std::str::from_utf8(&input[index + 1..index + 3]).ok();
            if let Some(value) = hex.and_then(|value| u8::from_str_radix(value, 16).ok()) {
                bytes.push(value);
                index += 3;
                continue;
            }
        }
        bytes.push(input[index]);
        index += 1;
    }
    String::from_utf8_lossy(&bytes).into_owned()
}

fn unescape_markdown_path(path: &str) -> String {
    let bytes = path.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'\\'
            && index + 1 < bytes.len()
            && matches!(bytes[index + 1], b'\\' | b'(' | b')' | b' ')
        {
            output.push(bytes[index + 1]);
            index += 2;
        } else {
            output.push(bytes[index]);
            index += 1;
        }
    }
    String::from_utf8_lossy(&output).into_owned()
}

fn normalize_posix(parts: impl IntoIterator<Item = String>) -> String {
    let mut normalized = Vec::new();
    for part in parts {
        match part.as_str() {
            "" | "." => {}
            ".." => {
                if normalized.last().is_some_and(|last| last != "..") {
                    normalized.pop();
                } else {
                    normalized.push(part);
                }
            }
            _ => normalized.push(part),
        }
    }
    if normalized.is_empty() {
        ".".to_owned()
    } else {
        normalized.join("/")
    }
}

fn local_resource(source: &str, target: &str) -> BundleResult<Option<String>> {
    let parsed = split_target(target);
    if parsed.is_external || parsed.path.is_empty() {
        return Ok(None);
    }
    let unescaped = unescape_markdown_path(parsed.path);
    let path = percent_unquote(&unescaped);
    if path.starts_with('/') {
        return Err(bundle_error(format!(
            "Markdown resource escapes source: {source}: {target}"
        )));
    }
    let mut pieces = source
        .rsplit_once('/')
        .map(|(parent, _)| parent.split('/').map(str::to_owned).collect::<Vec<_>>())
        .unwrap_or_default();
    pieces.extend(path.split('/').map(str::to_owned));
    let resolved = normalize_posix(pieces);
    if resolved == ".." || resolved.starts_with("../") {
        return Err(bundle_error(format!(
            "Markdown resource escapes source: {source}: {target}"
        )));
    }
    Ok(Some(resolved))
}

fn codex_user_entries(
    source: &GitSource,
    commit: &str,
    entries: Vec<TreeEntry>,
    manifest: &DocumentMut,
) -> BundleResult<Vec<TreeEntry>> {
    let inventory = source
        .entries(commit)?
        .into_iter()
        .map(|entry| (entry.path.clone(), entry.mode))
        .collect::<BTreeMap<_, _>>();
    let mut selected = entries
        .into_iter()
        .map(|entry| (entry.path.clone(), entry))
        .collect::<BTreeMap<_, _>>();
    let profiles = manifest
        .get("profiles")
        .and_then(Item::as_table)
        .ok_or_else(|| bundle_error("template bundle profiles are missing"))?;
    let mut template_roots = Vec::new();
    for (name, item) in profiles.iter() {
        if name == CODEX_USER_PROFILE {
            continue;
        }
        if let Some(roots) = item
            .as_table()
            .and_then(|profile| profile.get("roots"))
            .and_then(Item::as_array)
        {
            template_roots.extend(
                roots
                    .iter()
                    .filter_map(|root| root.as_str().map(str::to_owned)),
            );
        }
    }
    let mut pending = selected.keys().cloned().collect::<Vec<_>>();
    let mut visited = BTreeSet::new();
    while let Some(path) = pending.pop() {
        if visited.contains(&path)
            || !path.ends_with(".md")
            || is_template_asset(&path, &template_roots)
        {
            continue;
        }
        visited.insert(path.clone());
        let content = source.blob(commit, &path)?;
        let text = std::str::from_utf8(&content)
            .map_err(|_| bundle_error(format!("Markdown resource is not UTF-8: {path}")))?;
        for destination in markdown_destinations(text)? {
            let Some(resource) = local_resource(&path, &destination.target)? else {
                continue;
            };
            let resources = if inventory.contains_key(&resource) {
                vec![resource]
            } else {
                let prefix = if resource == "." {
                    String::new()
                } else {
                    format!("{resource}/")
                };
                let children = inventory
                    .keys()
                    .filter(|candidate| candidate.starts_with(&prefix))
                    .cloned()
                    .collect::<Vec<_>>();
                let index = format!("{prefix}README.md");
                if inventory.contains_key(&index) && !is_template_asset(&resource, &template_roots)
                {
                    vec![index]
                } else {
                    children
                }
            };
            if resources.is_empty() {
                return Err(bundle_error(format!(
                    "missing Markdown resource: {path}: {}",
                    destination.target
                )));
            }
            for resource in resources {
                let mode = inventory
                    .get(&resource)
                    .ok_or_else(|| bundle_error(format!("unsafe Markdown resource: {resource}")))?;
                if !mode_is_regular(mode) {
                    return Err(bundle_error(format!(
                        "unsafe Markdown resource: {resource}"
                    )));
                }
                if !selected.contains_key(&resource) {
                    selected.insert(
                        resource.clone(),
                        TreeEntry {
                            path: resource.clone(),
                            mode: mode.clone(),
                        },
                    );
                    pending.push(resource);
                }
            }
        }
    }
    Ok(selected.into_values().collect())
}

fn percent_quote(path: &str) -> String {
    let mut output = String::new();
    for byte in path.as_bytes() {
        if byte.is_ascii_alphanumeric() || b"/._-~".contains(byte) {
            output.push(*byte as char);
        } else {
            output.push_str(&format!("%{byte:02X}"));
        }
    }
    output
}

fn posix_relative(target: &str, base: &str) -> String {
    let target_parts = target
        .split('/')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    let base_parts = base
        .split('/')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    let common = target_parts
        .iter()
        .zip(&base_parts)
        .take_while(|(left, right)| left == right)
        .count();
    let mut result = vec![".."; base_parts.len() - common];
    result.extend(target_parts[common..].iter().copied());
    if result.is_empty() {
        ".".to_owned()
    } else {
        result.join("/")
    }
}

fn codex_skill_body(source: &str, destination: &str, content: &[u8]) -> BundleResult<Vec<u8>> {
    let mut text = std::str::from_utf8(content)
        .map_err(|_| bundle_error("Codex skill body is not UTF-8"))?
        .to_owned();
    let dependency = regex(r"(?ms)^<!--\s*\n@dependency-start\n.*?^@dependency-end\n-->\n?");
    text = dependency.replacen(&text, 1, "").into_owned();
    let mut destinations = markdown_destinations(&text)?;
    destinations.reverse();
    let destination_parent = destination
        .rsplit_once('/')
        .map(|(parent, _)| parent)
        .unwrap_or("");
    for reference in destinations {
        let Some(resource) = local_resource(source, &reference.target)? else {
            continue;
        };
        let parsed = split_target(&reference.target);
        let relative = percent_quote(&posix_relative(&resource, destination_parent));
        let replacement = format!(
            "{relative}{}{}",
            if parsed.query.is_empty() {
                String::new()
            } else {
                format!("?{}", parsed.query)
            },
            if parsed.fragment.is_empty() {
                String::new()
            } else {
                format!("#{}", parsed.fragment)
            }
        );
        text.replace_range(reference.start..reference.end, &replacement);
    }
    Ok(text.into_bytes())
}

fn codex_hook_configuration(source: &[u8]) -> BundleResult<Vec<u8>> {
    const EVENTS: [&str; 3] = ["UserPromptSubmit", "PreToolUse", "PostToolUse"];
    let mut value: Value = serde_json::from_slice(source)
        .map_err(|_| bundle_error("canonical hook configuration is invalid"))?;
    let hooks = value
        .as_object_mut()
        .and_then(|root| root.get_mut("hooks"))
        .and_then(Value::as_object_mut)
        .ok_or_else(|| bundle_error("canonical active hook events changed"))?;
    let keys = hooks.keys().map(String::as_str).collect::<BTreeSet<_>>();
    if keys != EVENTS.into_iter().collect() {
        return Err(bundle_error("canonical active hook events changed"));
    }
    for event in EVENTS {
        let groups = hooks
            .get_mut(event)
            .and_then(Value::as_array_mut)
            .filter(|groups| !groups.is_empty())
            .ok_or_else(|| bundle_error(format!("canonical hook groups are missing: {event}")))?;
        for group in groups {
            let hooks = group
                .as_object_mut()
                .and_then(|group| group.get_mut("hooks"))
                .and_then(Value::as_array_mut)
                .ok_or_else(|| bundle_error(format!("canonical hook group is invalid: {event}")))?;
            for hook in hooks {
                if hook.get("type").and_then(Value::as_str) != Some("command") {
                    return Err(bundle_error(format!(
                        "canonical hook command is invalid: {event}"
                    )));
                }
                let command = format!(
                    "bash \"${{PLUGIN_ROOT}}/bootstrap.sh\" --control-parent-root \"${{AGENT_CANON_CONTROL_PARENT_ROOT:-${{HOME}}}}\" codex hook {event}"
                );
                hook.as_object_mut()
                    .ok_or_else(|| {
                        bundle_error(format!("canonical hook command is invalid: {event}"))
                    })?
                    .insert("command".to_owned(), Value::String(command));
            }
        }
    }
    let projected = json!({"hooks": hooks.clone()});
    json_bytes(&projected)
}

fn codex_skill_frontmatter(content: &[u8], skill: &str) -> BundleResult<Vec<u8>> {
    let content = std::str::from_utf8(content).map_err(|_| {
        bundle_error(format!(
            "generated Codex skill frontmatter is not UTF-8: {skill}"
        ))
    })?;
    let frontmatter = regex(r"(?s)\A---\r?\n.*?\r?\n---\r?\n")
        .find(content)
        .ok_or_else(|| {
            bundle_error(format!(
                "generated Codex skill frontmatter is invalid: {skill}"
            ))
        })?
        .as_str();
    let name = format!("name: {skill}");
    if frontmatter.lines().filter(|line| *line == name).count() != 1 {
        return Err(bundle_error(format!(
            "generated Codex skill name differs: {skill}"
        )));
    }
    Ok(frontmatter.as_bytes().to_vec())
}

fn codex_user_payload(
    source: &GitSource,
    commit: &str,
    entries: &[TreeEntry],
) -> BundleResult<(Payload, PayloadModes, Vec<Value>)> {
    let mut payload = Payload::new();
    let mut payload_modes = PayloadModes::new();
    let mut install_files = Vec::new();
    let mut root_guidance = None;
    let mut skill_frontmatter = BTreeMap::<String, Vec<u8>>::new();
    let mut canonical_skills = BTreeMap::<String, Vec<u8>>::new();
    let source_paths = entries
        .iter()
        .map(|entry| entry.path.clone())
        .collect::<BTreeSet<_>>();
    if source_paths.contains(CODEX_USER_MANIFEST) {
        return Err(bundle_error(format!(
            "Codex generated path collides with source: {CODEX_USER_MANIFEST}"
        )));
    }
    let project = |path: &str,
                   content: Vec<u8>,
                   mode: &str,
                   payload: &mut Payload,
                   payload_modes: &mut PayloadModes|
     -> BundleResult<()> {
        if source_paths.contains(path) || payload.contains_key(path) {
            return Err(bundle_error(format!(
                "Codex generated path collides with source: {path}"
            )));
        }
        payload.insert(path.to_owned(), content);
        payload_modes.insert(path.to_owned(), mode.to_owned());
        Ok(())
    };

    for entry in entries {
        if !mode_is_regular(&entry.mode) {
            return Err(bundle_error(format!(
                "Codex bundle source is not a regular file: {}",
                entry.path
            )));
        }
        let content = source.blob(commit, &entry.path)?;
        payload.insert(entry.path.clone(), content.clone());
        payload_modes.insert(entry.path.clone(), entry.mode.clone());
        if entry.path == "ROOT_AGENTS.md" {
            root_guidance = Some(content);
            continue;
        }
        if entry.path == ".codex/hooks.json" {
            project(
                "hooks/hooks.json",
                codex_hook_configuration(&content)?,
                "100644",
                &mut payload,
                &mut payload_modes,
            )?;
            continue;
        }
        if entry.path.starts_with(".codex/agents/") {
            let filename = entry.path.rsplit('/').next().unwrap_or_default();
            if entry.path.matches('/').count() != 2 || !filename.ends_with(".toml") {
                return Err(bundle_error(
                    "Codex bundle agent source is not a direct TOML child",
                ));
            }
            let destination = format!("agents/agent-canon-{filename}");
            project(
                &destination,
                content,
                &entry.mode,
                &mut payload,
                &mut payload_modes,
            )?;
            install_files.push(json!({
                "component": "agent",
                "bundle_path": destination,
                "destination": format!("codex/agents/agent-canon-{filename}"),
            }));
            continue;
        }
        if entry.path.starts_with(".codex/personal/skills/") {
            let relative = entry
                .path
                .strip_prefix(".codex/personal/skills/")
                .unwrap_or_default();
            let parts = relative.split('/').collect::<Vec<_>>();
            if parts.len() != 2 || parts[1] != "SKILL.md" {
                return Err(bundle_error(
                    "Codex skill materialization is not one-file scoped",
                ));
            }
            let skill = parts[0];
            if skill_frontmatter.contains_key(skill) {
                return Err(bundle_error(format!(
                    "Codex skill view is duplicated: {skill}"
                )));
            }
            skill_frontmatter.insert(skill.to_owned(), codex_skill_frontmatter(&content, skill)?);
            continue;
        }
        if entry.path.starts_with("agents/skills/") && entry.path.ends_with(".md") {
            let skill = entry
                .path
                .rsplit('/')
                .next()
                .unwrap_or_default()
                .strip_suffix(".md")
                .unwrap_or_default();
            if skill_frontmatter.contains_key(skill) {
                canonical_skills.insert(skill.to_owned(), content);
            }
        }
    }
    if skill_frontmatter.keys().collect::<BTreeSet<_>>()
        != canonical_skills.keys().collect::<BTreeSet<_>>()
    {
        return Err(bundle_error(
            "Codex skill views and canonical owners differ",
        ));
    }
    for (skill, frontmatter) in &skill_frontmatter {
        let destination = format!("skills/{skill}/SKILL.md");
        let canonical = canonical_skills
            .get(skill)
            .ok_or_else(|| bundle_error("Codex skill views and canonical owners differ"))?;
        let body = codex_skill_body(
            &format!("agents/skills/{skill}.md"),
            &destination,
            canonical,
        )?;
        let mut output = frontmatter.clone();
        output.push(b'\n');
        output.extend_from_slice(&body);
        project(
            &destination,
            output,
            "100644",
            &mut payload,
            &mut payload_modes,
        )?;
    }
    let root_guidance =
        root_guidance.ok_or_else(|| bundle_error("portable common ROOT_AGENTS.md is missing"))?;
    let composition = Composition {
        source_commit: commit.to_owned(),
        base: root_guidance,
        specific: Vec::new(),
    };
    project(
        "guidance/AGENTS.md",
        composition.render(),
        "100644",
        &mut payload,
        &mut payload_modes,
    )?;
    install_files.push(json!({
        "component": "guidance",
        "bundle_path": "guidance/AGENTS.md",
        "destination": "codex/AGENTS.md",
    }));
    project(
        "plugin.json",
        json_bytes(&json!({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": "agent-canon",
            "version": "0.1.0",
            "description": "AgentCanon user-scoped agents, guidance, skills, and trusted-project hooks."
        }))?,
        "100644",
        &mut payload,
        &mut payload_modes,
    )?;
    project(
        CODEX_MARKETPLACE,
        json_bytes(&json!({
            "name": "agent-canon-user-bundle",
            "plugins": [{
                "name": "agent-canon",
                "source": {"source": "local", "path": "./"},
                "interface": {"displayName": "AgentCanon"}
            }]
        }))?,
        "100644",
        &mut payload,
        &mut payload_modes,
    )?;
    for path in payload.keys() {
        payload_modes
            .entry(path.clone())
            .or_insert_with(|| "100644".to_owned());
    }
    install_files.sort_by(|left, right| {
        let left_destination = left
            .get("destination")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let right_destination = right
            .get("destination")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let left_path = left
            .get("bundle_path")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let right_path = right
            .get("bundle_path")
            .and_then(Value::as_str)
            .unwrap_or_default();
        (left_destination, left_path).cmp(&(right_destination, right_path))
    });
    Ok((payload, payload_modes, install_files))
}

fn codex_user_bundle_digest(
    source_commit: &str,
    source_bundle_digest: &str,
    manifest_digest: &str,
    payload: &Payload,
    install_files: &[Value],
) -> BundleResult<String> {
    let mut digest = Sha256::new();
    digest.update(CODEX_USER_SCHEMA.as_bytes());
    digest.update([0]);
    digest.update(source_commit.as_bytes());
    digest.update([0]);
    digest.update(source_bundle_digest.as_bytes());
    digest.update([0]);
    digest.update(manifest_digest.as_bytes());
    digest.update([0]);
    for (path, content) in payload {
        digest.update(path.as_bytes());
        digest.update([0]);
        digest.update(Sha256::digest(content));
        digest.update([0]);
    }
    for record in install_files {
        // serde_json's default map is key-sorted, matching the source JSON contract.
        digest.update(
            serde_json::to_vec(record).map_err(|_| bundle_error("JSON serialization failed"))?,
        );
        digest.update([0]);
    }
    Ok(digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn bundle_identity_for(
    source: &GitSource,
    source_ref: &str,
    profile: &str,
) -> BundleResult<BundleIdentityWork> {
    let commit = source.commit(source_ref)?;
    let (manifest, manifest_digest) = source.resolve_profile(&commit)?;
    let roots = GitSource::roots(&manifest, profile)?;
    let mut entries = entries_for_roots(source, &commit, &roots)?;
    if profile == CODEX_USER_PROFILE {
        entries = codex_user_entries(source, &commit, entries, &manifest)?;
    }
    let version = manifest
        .get("version")
        .and_then(Item::as_integer)
        .ok_or_else(|| bundle_error("template bundle manifest version must be 1"))?;
    let mut hasher = Sha256::new();
    hasher.update(version.to_string().as_bytes());
    hasher.update([0]);
    hasher.update(profile.as_bytes());
    hasher.update([0]);
    hasher.update(manifest_digest.as_bytes());
    hasher.update([0]);
    for entry in &entries {
        let content = source.blob(&commit, &entry.path)?;
        hasher.update(entry.path.as_bytes());
        hasher.update([0]);
        hasher.update(entry.mode.as_bytes());
        hasher.update([0]);
        hasher.update(Sha256::digest(&content));
        hasher.update([0]);
    }
    let source_bundle_digest = hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let mut payload = Payload::new();
    let mut payload_modes = PayloadModes::new();
    let mut install_files = Vec::new();
    let mut identity = if profile == CODEX_USER_PROFILE {
        let (codex_payload, codex_modes, codex_installs) =
            codex_user_payload(source, &commit, &entries)?;
        payload = codex_payload;
        payload_modes = codex_modes;
        install_files = codex_installs;
        let tree = source.tree(&commit)?;
        let final_digest = codex_user_bundle_digest(
            &commit,
            &source_bundle_digest,
            &manifest_digest,
            &payload,
            &install_files,
        )?;
        json!({
            "schema": CODEX_USER_SCHEMA,
            "source_commit": commit,
            "source_tree": tree,
            "profile": profile,
            "manifest_digest": manifest_digest,
            "source_bundle_digest": source_bundle_digest,
            "bundle_digest": final_digest,
            "paths": payload.keys().collect::<Vec<_>>(),
        })
    } else {
        json!({
            "schema": "agent-canon.template-bundle.v1",
            "source_commit": commit,
            "profile": profile,
            "manifest_digest": manifest_digest,
            "bundle_digest": source_bundle_digest,
            "paths": entries.iter().map(|entry| entry.path.clone()).collect::<Vec<_>>(),
        })
    };
    // Force an object here so the returned shape remains a JSON object across profiles.
    if !identity.is_object() {
        identity = object();
    }
    Ok(BundleIdentityWork {
        identity,
        commit,
        entries,
        payload,
        payload_modes,
        install_files,
    })
}

/// Return the source-commit-bound identity for one declared template profile.
pub fn bundle_identity(
    source_root: &Path,
    source_ref: &str,
    profile: &str,
) -> Result<Value, TemplateBundleError> {
    let source = GitSource::open(source_root)?;
    let work = bundle_identity_for(&source, source_ref, profile)?;
    Ok(work.identity)
}

fn json_identity_with_output(identity: &Value, output: &Path) -> BundleResult<Value> {
    let mut value = identity.clone();
    set(
        &mut value,
        "output",
        Value::String(output.to_string_lossy().into_owned()),
    )?;
    Ok(value)
}

fn resolve_output(output: &Path) -> BundleResult<PathBuf> {
    if output.is_absolute() {
        Ok(output.to_path_buf())
    } else {
        std::env::current_dir()
            .map(|current| current.join(output))
            .map_err(|error| bundle_error(format!("resolve output path: {error}")))
    }
}

fn ensure_fresh_output(output: &Path, source_root: &Path, label: &str) -> BundleResult<PathBuf> {
    let output = resolve_output(output)?;
    let source = fs::canonicalize(source_root)
        .map_err(|error| bundle_error(format!("canonicalize source root: {error}")))?;
    let resolved = canonicalize_allow_missing(&output)
        .map_err(|error| bundle_error(format!("resolve {label}: {error}")))?;
    if resolved == source || resolved.starts_with(&source) {
        return Err(bundle_error(format!(
            "{label} must be outside AgentCanon source"
        )));
    }
    match fs::symlink_metadata(&output) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            return Err(bundle_error(format!("{label} must be a fresh directory")));
        }
        Ok(metadata) if !metadata.is_dir() => {
            return Err(bundle_error(format!("{label} must be a fresh directory")));
        }
        Ok(_)
            if fs::read_dir(&output)
                .map_err(|error| bundle_error(format!("inspect {label}: {error}")))?
                .next()
                .is_some() =>
        {
            return Err(bundle_error(format!("{label} must be a fresh directory")));
        }
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(bundle_error(format!("inspect {label}: {error}"))),
    }
    Ok(resolved)
}

fn authorize_runtime_output(
    source_root: &Path,
    runtime_root: &Path,
    output: &Path,
    label: &str,
) -> BundleResult<()> {
    crate::runtime_boundary::validate_external_target(source_root, runtime_root, output, label)
        .map_err(bundle_error)?;
    let runtime = fs::canonicalize(runtime_root)
        .map_err(|error| bundle_error(format!("canonicalize runtime root: {error}")))?;
    let directory = crate::runtime_boundary::RuntimeDirectory::open(&runtime, false)
        .map_err(|error| bundle_error(format!("open runtime root: {error}")))?;
    let relative = output
        .strip_prefix(&runtime)
        .map_err(|_| bundle_error(format!("{label} escapes runtime root")))?;
    if !relative.as_os_str().is_empty() && output.exists() {
        directory
            .child(relative, false)
            .map_err(|error| bundle_error(format!("{label} is missing or unsafe: {error}")))?;
    } else if let Some(parent) = relative.parent() {
        if !parent.as_os_str().is_empty() {
            match directory.child(parent, false) {
                Ok(_) => {}
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(bundle_error(format!(
                        "{label} is missing or unsafe: {error}"
                    )));
                }
            }
        }
    }
    Ok(())
}

fn prepare_runtime_output(runtime_root: &Path, output: &Path, label: &str) -> BundleResult<()> {
    let runtime = fs::canonicalize(runtime_root)
        .map_err(|error| bundle_error(format!("canonicalize runtime root: {error}")))?;
    let directory = crate::runtime_boundary::RuntimeDirectory::open(&runtime, false)
        .map_err(|error| bundle_error(format!("open runtime root: {error}")))?;
    let relative = output
        .strip_prefix(&runtime)
        .map_err(|_| bundle_error(format!("{label} escapes runtime root")))?;
    if !relative.as_os_str().is_empty() {
        directory
            .child(relative, true)
            .map_err(|error| bundle_error(format!("{label} is missing or unsafe: {error}")))?;
    }
    Ok(())
}

pub(crate) fn write_output_file(path: &Path, bytes: &[u8], _mode: u32) -> BundleResult<()> {
    let parent = path
        .parent()
        .ok_or_else(|| bundle_error(format!("output file has no parent: {}", path.display())))?;
    fs::create_dir_all(parent).map_err(|error| {
        bundle_error(format!(
            "create output directory {}: {error}",
            parent.display()
        ))
    })?;
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o666);
    }
    let mut file = options
        .open(path)
        .map_err(|error| bundle_error(format!("write output file {}: {error}", path.display())))?;
    file.write_all(bytes)
        .map_err(|error| bundle_error(format!("write output file {}: {error}", path.display())))?;
    file.flush()
        .map_err(|error| bundle_error(format!("write output file {}: {error}", path.display())))?;
    #[cfg(unix)]
    if _mode == 0o755 {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(_mode))
            .map_err(|error| {
                bundle_error(format!("set output mode {}: {error}", path.display()))
            })?;
    }
    Ok(())
}

fn write_profile_export(
    source: &GitSource,
    output: &Path,
    work: &BundleIdentityWork,
) -> BundleResult<()> {
    fs::create_dir_all(output).map_err(|error| {
        bundle_error(format!(
            "create output directory {}: {error}",
            output.display()
        ))
    })?;
    if work.identity.get("profile").and_then(Value::as_str) == Some(CODEX_USER_PROFILE) {
        for (path, content) in &work.payload {
            let destination = bundle_destination(output, path)?;
            let mode = work
                .payload_modes
                .get(path)
                .map(String::as_str)
                .unwrap_or("100644");
            write_output_file(&destination, content, mode_number(mode))?;
        }
        let files = work
            .payload
            .iter()
            .map(|(path, content)| json!({"path": path, "sha256": digest(content)}))
            .collect::<Vec<_>>();
        let manifest = json!({
            "schema": CODEX_USER_SCHEMA,
            "version": 1,
            "source_commit": work.identity["source_commit"],
            "source_tree": work.identity["source_tree"],
            "profile": CODEX_USER_PROFILE,
            "manifest_digest": work.identity["manifest_digest"],
            "source_bundle_digest": work.identity["source_bundle_digest"],
            "bundle_digest": work.identity["bundle_digest"],
            "files": files,
            "install_files": work.install_files,
        });
        write_output_file(
            &output.join(CODEX_USER_MANIFEST),
            &json_bytes(&manifest)?,
            0o644,
        )?;
    } else {
        for entry in &work.entries {
            let destination = bundle_destination(output, &entry.path)?;
            write_output_file(
                &destination,
                &source.blob(&work.commit, &entry.path)?,
                0o644,
            )?;
        }
        let provenance = json_identity_with_output(&work.identity, output)?;
        write_output_file(
            &output.join("template-bundle-provenance.json"),
            &json_bytes(&provenance)?,
            0o644,
        )?;
    }
    Ok(())
}

pub(crate) fn export_bundle_at(
    source_root: &Path,
    source_ref: &str,
    profile: &str,
    output: &Path,
    runtime_root: &Path,
) -> BundleResult<Value> {
    let source = GitSource::open(source_root)?;
    let output = ensure_fresh_output(output, &source.root, "output")?;
    if profile == "static-seed" {
        return Err(bundle_error("static-seed uses export_static_seed.py"));
    }
    authorize_runtime_output(&source.root, runtime_root, &output, "output")?;
    let work = bundle_identity_for(&source, source_ref, profile)?;
    prepare_runtime_output(runtime_root, &output, "output")?;
    write_profile_export(&source, &output, &work)?;
    json_identity_with_output(&work.identity, &output)
}

pub(crate) fn export_bundle(
    source_root: &Path,
    source_ref: &str,
    profile: &str,
    output: &Path,
) -> BundleResult<Value> {
    let runtime_root =
        crate::runtime_boundary::resolve_runtime_root(source_root).map_err(bundle_error)?;
    export_bundle_at(source_root, source_ref, profile, output, &runtime_root)
}

fn exact_keys(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key))
    })
}

fn recursive_bundle_files(
    root: &Path,
    current: &Path,
    files: &mut BTreeSet<String>,
) -> BundleResult<()> {
    let entries = fs::read_dir(current)
        .map_err(|error| bundle_error(format!("read Codex user bundle: {error}")))?;
    for entry in entries {
        let entry =
            entry.map_err(|error| bundle_error(format!("read Codex user bundle: {error}")))?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)
            .map_err(|error| bundle_error(format!("inspect Codex user bundle: {error}")))?;
        if metadata.file_type().is_symlink() {
            return Err(bundle_error("Codex user bundle contains a symlink"));
        }
        if metadata.is_dir() {
            recursive_bundle_files(root, &path, files)?;
        } else if metadata.is_file() && path != root.join(CODEX_USER_MANIFEST) {
            let relative = path
                .strip_prefix(root)
                .map_err(|_| bundle_error("Codex user bundle path escapes root"))?
                .components()
                .map(|component| component.as_os_str().to_string_lossy())
                .collect::<Vec<_>>()
                .join("/");
            files.insert(relative);
        }
    }
    Ok(())
}

fn verify_codex_user_bundle_inner(root: &Path) -> BundleResult<Value> {
    let root_metadata = fs::symlink_metadata(root)
        .map_err(|_| bundle_error("Codex user bundle root is missing or unsafe"))?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(bundle_error("Codex user bundle root is missing or unsafe"));
    }
    let root = fs::canonicalize(root)
        .map_err(|_| bundle_error("Codex user bundle root is missing or unsafe"))?;
    let manifest_path = root.join(CODEX_USER_MANIFEST);
    let manifest_metadata = fs::symlink_metadata(&manifest_path)
        .map_err(|_| bundle_error("Codex user bundle manifest is missing or unsafe"))?;
    if manifest_metadata.file_type().is_symlink() || !manifest_metadata.is_file() {
        return Err(bundle_error(
            "Codex user bundle manifest is missing or unsafe",
        ));
    }
    let manifest_bytes = fs::read(&manifest_path)
        .map_err(|_| bundle_error("Codex user bundle manifest is invalid"))?;
    let manifest: Value = serde_json::from_slice(&manifest_bytes)
        .map_err(|_| bundle_error("Codex user bundle manifest is invalid"))?;
    if manifest.get("schema").and_then(Value::as_str) != Some(CODEX_USER_SCHEMA)
        || manifest.get("version").and_then(Value::as_i64) != Some(1)
        || manifest.get("profile").and_then(Value::as_str) != Some(CODEX_USER_PROFILE)
    {
        return Err(bundle_error(
            "Codex user bundle schema or profile is invalid",
        ));
    }
    let source_commit = manifest
        .get("source_commit")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let source_tree = manifest
        .get("source_tree")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let bundle_digest = manifest
        .get("bundle_digest")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let source_bundle_digest = manifest
        .get("source_bundle_digest")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let manifest_digest = manifest
        .get("manifest_digest")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !valid_hex(source_commit, HEX_40)
        || !valid_hex(source_tree, HEX_40)
        || !valid_hex(bundle_digest, HEX_64)
        || !valid_hex(source_bundle_digest, HEX_64)
        || !valid_hex(manifest_digest, HEX_64)
    {
        return Err(bundle_error("Codex user bundle identity is invalid"));
    }
    let rows = manifest
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| bundle_error("Codex user bundle file records are missing"))?;
    let installs = manifest
        .get("install_files")
        .and_then(Value::as_array)
        .ok_or_else(|| bundle_error("Codex user bundle file records are missing"))?;
    let mut payload = Payload::new();
    let mut previous = String::new();
    for row in rows {
        if !exact_keys(row, &["path", "sha256"]) {
            return Err(bundle_error("Codex user bundle file record is invalid"));
        }
        let path = row.get("path").and_then(Value::as_str).unwrap_or_default();
        let sha = row
            .get("sha256")
            .and_then(Value::as_str)
            .unwrap_or_default();
        portable_relative(path)
            .map_err(|_| bundle_error("Codex user bundle file path or digest is invalid"))?;
        if !valid_hex(sha, HEX_64) || path <= previous.as_str() {
            return Err(bundle_error(
                "Codex user bundle file path or digest is invalid",
            ));
        }
        previous = path.to_owned();
        let candidate = bundle_destination(&root, path)
            .map_err(|_| bundle_error("Codex user bundle contains a symlink"))?;
        let mut cursor = root.clone();
        for part in path.split('/') {
            cursor.push(part);
            let metadata = fs::symlink_metadata(&cursor)
                .map_err(|_| bundle_error(format!("Codex user bundle file is missing: {path}")))?;
            if metadata.file_type().is_symlink() {
                return Err(bundle_error("Codex user bundle contains a symlink"));
            }
        }
        let metadata = fs::symlink_metadata(&candidate)
            .map_err(|_| bundle_error(format!("Codex user bundle file is missing: {path}")))?;
        if !metadata.is_file() {
            return Err(bundle_error(format!(
                "Codex user bundle file is missing: {path}"
            )));
        }
        let content = fs::read(&candidate)
            .map_err(|_| bundle_error(format!("Codex user bundle file is missing: {path}")))?;
        if digest(&content) != sha {
            return Err(bundle_error(format!(
                "Codex user bundle file digest differs: {path}"
            )));
        }
        payload.insert(path.to_owned(), content);
    }
    let mut actual = BTreeSet::new();
    recursive_bundle_files(&root, &root, &mut actual)?;
    if actual != payload.keys().cloned().collect() {
        return Err(bundle_error(
            "Codex user bundle contains unmanifested files",
        ));
    }
    const REQUIRED: [&str; 8] = [
        "bootstrap.sh",
        "bootstrap/host/lifecycle/entrypoint.sh",
        "tools/runtime/container/bootstrap_runtime.py",
        "hooks/hooks.json",
        "plugin.json",
        CODEX_MARKETPLACE,
        "skills/agent-canon-bootstrap/SKILL.md",
        "guidance/AGENTS.md",
    ];
    if REQUIRED.iter().any(|path| !payload.contains_key(*path)) {
        return Err(bundle_error(
            "Codex user bundle is missing required runtime files",
        ));
    }
    let mut normalized_installs = Vec::new();
    let mut seen_destinations = BTreeSet::new();
    for row in installs {
        if !exact_keys(row, &["component", "bundle_path", "destination"]) {
            return Err(bundle_error("Codex user bundle install record is invalid"));
        }
        let component = row
            .get("component")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let bundle_path = row
            .get("bundle_path")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let destination = row
            .get("destination")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if !matches!(component, "agent" | "guidance")
            || !payload.contains_key(bundle_path)
            || destination
                .chars()
                .any(|character| matches!(character, '\\' | '\0' | '\t' | '\n' | '\r'))
            || !seen_destinations.insert(destination.to_owned())
        {
            return Err(bundle_error("Codex user bundle install record is invalid"));
        }
        if component == "agent"
            && !(bundle_path.starts_with("agents/agent-canon-")
                && bundle_path.matches('/').count() == 1
                && bundle_path.ends_with(".toml")
                && destination
                    == format!(
                        "codex/agents/{}",
                        bundle_path.rsplit('/').next().unwrap_or_default()
                    ))
        {
            return Err(bundle_error(
                "Codex user bundle agent destination is invalid",
            ));
        }
        if component == "guidance"
            && !(bundle_path == "guidance/AGENTS.md" && destination == "codex/AGENTS.md")
        {
            return Err(bundle_error(
                "Codex user bundle guidance destination is invalid",
            ));
        }
        normalized_installs.push(json!({
            "component": component,
            "bundle_path": bundle_path,
            "destination": destination,
        }));
    }
    normalized_installs.sort_by(|left, right| {
        (
            left.get("destination")
                .and_then(Value::as_str)
                .unwrap_or_default(),
            left.get("bundle_path")
                .and_then(Value::as_str)
                .unwrap_or_default(),
        )
            .cmp(&(
                right
                    .get("destination")
                    .and_then(Value::as_str)
                    .unwrap_or_default(),
                right
                    .get("bundle_path")
                    .and_then(Value::as_str)
                    .unwrap_or_default(),
            ))
    });
    let mut expected_installs = payload
        .keys()
        .filter(|path| path.starts_with("agents/agent-canon-") && path.ends_with(".toml"))
        .map(|path| {
            let filename = path.rsplit('/').next().unwrap_or_default();
            json!({
                "component": "agent",
                "bundle_path": path,
                "destination": format!("codex/agents/{filename}"),
            })
        })
        .collect::<Vec<_>>();
    expected_installs.push(json!({
        "component": "guidance",
        "bundle_path": "guidance/AGENTS.md",
        "destination": "codex/AGENTS.md",
    }));
    expected_installs.sort_by(|left, right| {
        (
            left.get("destination")
                .and_then(Value::as_str)
                .unwrap_or_default(),
            left.get("bundle_path")
                .and_then(Value::as_str)
                .unwrap_or_default(),
        )
            .cmp(&(
                right
                    .get("destination")
                    .and_then(Value::as_str)
                    .unwrap_or_default(),
                right
                    .get("bundle_path")
                    .and_then(Value::as_str)
                    .unwrap_or_default(),
            ))
    });
    if normalized_installs != expected_installs {
        return Err(bundle_error(
            "Codex user bundle install projection is incomplete",
        ));
    }
    let computed = codex_user_bundle_digest(
        source_commit,
        source_bundle_digest,
        manifest_digest,
        &payload,
        &normalized_installs,
    )?;
    if computed != bundle_digest {
        return Err(bundle_error("Codex user bundle aggregate digest differs"));
    }
    let mut normalized = manifest;
    set(
        &mut normalized,
        "install_files",
        Value::Array(normalized_installs),
    )?;
    Ok(normalized)
}

pub(crate) fn verify_codex_user_bundle(root: &Path) -> BundleResult<Value> {
    verify_codex_user_bundle_inner(root)
}

fn package_component(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes
        .next()
        .is_some_and(|first| first.is_ascii_alphanumeric())
        && bytes
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'+' | b'-'))
}

fn native_cargo_version(source: &GitSource, commit: &str) -> BundleResult<String> {
    let raw = source.blob(commit, NATIVE_CLI_CARGO_MANIFEST)?;
    let text = std::str::from_utf8(&raw)
        .map_err(|_| bundle_error("native CLI Cargo package version is invalid"))?;
    let cargo = text
        .parse::<DocumentMut>()
        .map_err(|_| bundle_error("native CLI Cargo package version is invalid"))?;
    let version = cargo
        .get("package")
        .and_then(Item::as_table)
        .and_then(|package| package.get("version"))
        .and_then(Item::as_str)
        .filter(|version| package_component(version))
        .ok_or_else(|| bundle_error("native CLI Cargo package version is invalid"))?;
    Ok(version.to_owned())
}

pub(crate) fn native_release_version(source_root: &Path, source_ref: &str) -> BundleResult<String> {
    let source = GitSource::open(source_root)?;
    let commit = source.commit(source_ref)?;
    let base = native_cargo_version(&source, &commit)?;
    let version = regex(r"^(\d+)\.(\d+)\.(\d+)$");
    let captured = version
        .captures(&base)
        .ok_or_else(|| bundle_error("native release baseline must be a stable Cargo version"))?;
    let major = captured
        .get(1)
        .and_then(|value| value.as_str().parse::<u64>().ok())
        .ok_or_else(|| bundle_error("native release baseline must be a stable Cargo version"))?;
    let minor = captured
        .get(2)
        .and_then(|value| value.as_str().parse::<u64>().ok())
        .ok_or_else(|| bundle_error("native release baseline must be a stable Cargo version"))?;
    let patch = captured
        .get(3)
        .and_then(|value| value.as_str().parse::<u64>().ok())
        .ok_or_else(|| bundle_error("native release baseline must be a stable Cargo version"))?;
    let history = String::from_utf8(source.git(&[
        "rev-list".to_owned(),
        "--first-parent".to_owned(),
        commit.clone(),
    ])?)
    .map_err(|_| bundle_error("native release baseline is not on the source mainline"))?
    .lines()
    .map(str::to_owned)
    .collect::<Vec<_>>();
    let tag = format!("v{base}");
    let tags = source.git(&["tag".to_owned(), "--list".to_owned(), tag.clone()])?;
    let mut anchor = None;
    if String::from_utf8_lossy(&tags).trim() == tag {
        let tagged = source.commit(&format!("refs/tags/{tag}"))?;
        if history.contains(&tagged) {
            anchor = Some(tagged);
        }
    }
    if anchor.is_none() {
        let shallow =
            source.git(&["rev-parse".to_owned(), "--is-shallow-repository".to_owned()])?;
        if shallow.trim_ascii() == b"true" {
            return Err(bundle_error(
                "native release baseline needs complete source history",
            ));
        }
        let changes = String::from_utf8(source.git(&[
            "log".to_owned(),
            "--first-parent".to_owned(),
            "--format=%H".to_owned(),
            commit.clone(),
            "--".to_owned(),
            NATIVE_CLI_CARGO_MANIFEST.to_owned(),
        ])?)
        .map_err(|_| bundle_error("native release baseline is not on the source mainline"))?;
        for candidate in changes.lines() {
            let Ok(candidate_version) = native_cargo_version(&source, candidate) else {
                break;
            };
            if candidate_version != base {
                break;
            }
            anchor = Some(candidate.to_owned());
        }
    }
    let anchor = anchor
        .ok_or_else(|| bundle_error("native release baseline is not on the source mainline"))?;
    let index = history
        .iter()
        .position(|candidate| candidate == &anchor)
        .ok_or_else(|| bundle_error("native release baseline is not on the source mainline"))?
        as u64;
    let patch = patch
        .checked_add(index)
        .ok_or_else(|| bundle_error("native release baseline is not on the source mainline"))?;
    Ok(format!("{major}.{minor}.{patch}"))
}

fn native_layout(
    source: &GitSource,
    commit: &str,
    manifest: &DocumentMut,
) -> BundleResult<BTreeMap<String, String>> {
    let profile = manifest
        .get("profiles")
        .and_then(Item::as_table)
        .and_then(|profiles| profiles.get(NATIVE_CLI_PROFILE))
        .and_then(Item::as_table)
        .ok_or_else(|| bundle_error("native CLI package profile is missing"))?;
    let roots = GitSource::roots(manifest, NATIVE_CLI_PROFILE)?;
    let entries = entries_for_roots(source, commit, &roots)?;
    if entries.iter().any(|entry| !mode_is_regular(&entry.mode)) {
        return Err(bundle_error("native CLI resources must be regular files"));
    }
    let layout = profile
        .get("layout")
        .and_then(Item::as_table)
        .ok_or_else(|| {
            bundle_error("native CLI package layout must cover its declared resources")
        })?;
    let declared = entries
        .iter()
        .map(|entry| entry.path.clone())
        .collect::<BTreeSet<_>>();
    if layout.len() != declared.len() || layout.iter().any(|(path, _)| !declared.contains(path)) {
        return Err(bundle_error(
            "native CLI package layout must cover its declared resources",
        ));
    }
    let mut destinations = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for (source_path, item) in layout.iter() {
        let destination = item
            .as_str()
            .ok_or_else(|| bundle_error("native CLI package layout contains an unsafe path"))?;
        let parts = portable_relative(destination)
            .map_err(|_| bundle_error("native CLI package layout contains an unsafe path"))?;
        let relative = parts.join("/");
        if !seen.insert(relative.clone()) {
            return Err(bundle_error(
                "native CLI package layout contains duplicate destinations",
            ));
        }
        destinations.insert(source_path.to_owned(), relative);
    }
    Ok(destinations)
}

fn native_package_output(output: &Path, source_root: &Path) -> BundleResult<PathBuf> {
    ensure_fresh_output(output, source_root, "native package output")
}

fn native_tar_bytes(
    root_name: &str,
    payload: &BTreeMap<String, (Vec<u8>, u32)>,
) -> BundleResult<Vec<u8>> {
    let encoder = GzBuilder::new()
        .mtime(0)
        .write(Vec::new(), Compression::best());
    let mut archive = TarBuilder::new(encoder);
    for (relative, (content, mode)) in payload {
        let mut header = TarHeader::new_ustar();
        header.set_entry_type(EntryType::Regular);
        header.set_size(content.len() as u64);
        header.set_mode(*mode);
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(0);
        header
            .set_username("")
            .map_err(|error| bundle_error(format!("write native tar header: {error}")))?;
        header
            .set_groupname("")
            .map_err(|error| bundle_error(format!("write native tar header: {error}")))?;
        let name = format!("{root_name}/{relative}");
        archive
            .append_data(&mut header, name, Cursor::new(content))
            .map_err(|error| bundle_error(format!("write native tar archive: {error}")))?;
    }
    let encoder = archive
        .into_inner()
        .map_err(|error| bundle_error(format!("finish native tar archive: {error}")))?;
    encoder
        .finish()
        .map_err(|error| bundle_error(format!("finish native gzip stream: {error}")))
}

fn native_zip_bytes(
    root_name: &str,
    payload: &BTreeMap<String, (Vec<u8>, u32)>,
) -> BundleResult<Vec<u8>> {
    let mut archive = ZipWriter::new(Cursor::new(Vec::new()));
    for (relative, (content, mode)) in payload {
        let options = SimpleFileOptions::default()
            .compression_method(CompressionMethod::Deflated)
            .compression_level(Some(9))
            .last_modified_time(DateTime::default())
            .system(ZipSystem::Unix)
            .external_attributes((0o100000 | *mode) << 16);
        archive
            .start_file(format!("{root_name}/{relative}"), options)
            .map_err(|error| bundle_error(format!("write native ZIP archive: {error}")))?;
        archive
            .write_all(content)
            .map_err(|error| bundle_error(format!("write native ZIP archive: {error}")))?;
    }
    archive
        .finish()
        .map(|cursor| cursor.into_inner())
        .map_err(|error| bundle_error(format!("finish native ZIP archive: {error}")))
}

fn write_fresh_file(path: &Path, bytes: &[u8]) -> BundleResult<()> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|error| bundle_error(format!("write {}: {error}", path.display())))?;
    file.write_all(bytes)
        .and_then(|()| file.flush())
        .map_err(|error| bundle_error(format!("write {}: {error}", path.display())))
}

pub(crate) fn package_native_cli_at(
    source_root: &Path,
    source_ref: &str,
    binary: &Path,
    target: &str,
    output: &Path,
    toolchain: &str,
    runtime_root: &Path,
) -> BundleResult<Value> {
    let source = GitSource::open(source_root)?;
    let binary_metadata = fs::symlink_metadata(binary)
        .map_err(|_| bundle_error("native executable must be a regular file"))?;
    if binary_metadata.file_type().is_symlink() || !binary_metadata.is_file() {
        return Err(bundle_error("native executable must be a regular file"));
    }
    if !package_component(target) {
        return Err(bundle_error("native target is invalid"));
    }
    let binary = fs::canonicalize(binary)
        .map_err(|_| bundle_error("native executable must be a regular file"))?;
    let commit = source.commit(source_ref)?;
    let (manifest, manifest_digest) = source.resolve_profile(&commit)?;
    let layout = native_layout(&source, &commit, &manifest)?;
    let mut payload = BTreeMap::<String, (Vec<u8>, u32)>::new();
    for (source_path, destination) in &layout {
        payload.insert(
            destination.clone(),
            (source.blob(&commit, source_path)?, 0o644),
        );
    }
    let version = native_release_version(&source.root, &commit)?;
    let binary_name = if target.ends_with("-windows-msvc") {
        "agent-canon.exe"
    } else {
        "agent-canon"
    };
    let binary_path = format!("bin/{binary_name}");
    payload.insert(
        binary_path.clone(),
        (
            fs::read(&binary).map_err(|error| bundle_error(error.to_string()))?,
            0o755,
        ),
    );
    let mut provenance_files = payload
        .iter()
        .map(|(path, (content, _))| json!({"path": path, "sha256": digest(content)}))
        .collect::<Vec<_>>();
    provenance_files.sort_by(|left, right| {
        left.get("path")
            .and_then(Value::as_str)
            .cmp(&right.get("path").and_then(Value::as_str))
    });
    let provenance = json!({
        "schema": NATIVE_CLI_SCHEMA,
        "version": version,
        "target": target,
        "source_commit": commit,
        "source_tree": source.tree(&commit)?,
        "manifest_digest": manifest_digest,
        "toolchain": toolchain,
        "files": provenance_files,
    });
    let provenance_path = "share/agent-canon/provenance.json";
    payload.insert(
        provenance_path.to_owned(),
        (json_bytes(&provenance)?, 0o644),
    );
    let sums = payload
        .iter()
        .map(|(path, (content, _))| format!("{}  {path}\n", digest(content)))
        .collect::<String>();
    payload.insert(
        "share/agent-canon/SHA256SUMS".to_owned(),
        (sums.into_bytes(), 0o644),
    );
    let output = native_package_output(output, &source.root)?;
    authorize_runtime_output(&source.root, runtime_root, &output, "native package output")?;
    prepare_runtime_output(runtime_root, &output, "native package output")?;
    fs::create_dir_all(&output)
        .map_err(|error| bundle_error(format!("create native package output: {error}")))?;
    let archive_payload = payload.clone();
    let root_name = format!("agent-canon-{version}-{target}");
    let archives = [
        ("tar.gz", native_tar_bytes(&root_name, &archive_payload)?),
        ("zip", native_zip_bytes(&root_name, &archive_payload)?),
    ];
    let mut archive_records = Vec::new();
    for (suffix, bytes) in archives {
        let filename = format!("{root_name}.{suffix}");
        let path = output.join(&filename);
        write_fresh_file(&path, &bytes)?;
        let sha = digest(&bytes);
        let sidecar_name = format!("{filename}.sha256");
        write_fresh_file(
            &output.join(&sidecar_name),
            format!("{sha}  {filename}\n").as_bytes(),
        )?;
        archive_records.push(json!({"path": path.to_string_lossy(), "sha256": sha}));
    }
    let mut result = provenance;
    set(
        &mut result,
        "output",
        Value::String(output.to_string_lossy().into_owned()),
    )?;
    set(&mut result, "archives", Value::Array(archive_records))?;
    Ok(result)
}

pub(crate) fn package_native_cli(
    source_root: &Path,
    source_ref: &str,
    binary: &Path,
    target: &str,
    output: &Path,
    toolchain: &str,
) -> BundleResult<Value> {
    let runtime_root =
        crate::runtime_boundary::resolve_runtime_root(source_root).map_err(bundle_error)?;
    package_native_cli_at(
        source_root,
        source_ref,
        binary,
        target,
        output,
        toolchain,
        &runtime_root,
    )
}

fn native_archive_payload(path: &Path, prefix: &str) -> BundleResult<Payload> {
    let mut payload = Payload::new();
    let mut add = |name: &str, content: Vec<u8>| -> BundleResult<()> {
        let prefix_slash = format!("{prefix}/");
        let Some(relative) = name.strip_prefix(&prefix_slash) else {
            return Err(bundle_error("native archive root differs"));
        };
        portable_relative(relative)?;
        if payload.insert(relative.to_owned(), content).is_some() {
            return Err(bundle_error("native archive contains duplicate members"));
        }
        Ok(())
    };
    if path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .ends_with(".tar.gz")
    {
        let file = File::open(path).map_err(|_| {
            bundle_error(format!("native archive is unreadable: {}", path.display()))
        })?;
        let decoder = GzDecoder::new(file);
        let mut archive = TarArchive::new(decoder);
        let entries = archive.entries().map_err(|_| {
            bundle_error(format!("native archive is unreadable: {}", path.display()))
        })?;
        for entry in entries {
            let mut entry = entry.map_err(|_| {
                bundle_error(format!("native archive is unreadable: {}", path.display()))
            })?;
            if !entry.header().entry_type().is_file() {
                return Err(bundle_error("native archive member is not regular"));
            }
            let name = entry.path().map_err(|_| {
                bundle_error(format!("native archive is unreadable: {}", path.display()))
            })?;
            let name = name
                .to_str()
                .ok_or_else(|| {
                    bundle_error(format!("native archive is unreadable: {}", path.display()))
                })?
                .to_owned();
            let mut content = Vec::new();
            entry.read_to_end(&mut content).map_err(|_| {
                bundle_error(format!("native archive is unreadable: {}", path.display()))
            })?;
            add(&name, content)?;
        }
    } else {
        let file = File::open(path).map_err(|_| {
            bundle_error(format!("native archive is unreadable: {}", path.display()))
        })?;
        let mut archive = ZipArchive::new(file).map_err(|_| {
            bundle_error(format!("native archive is unreadable: {}", path.display()))
        })?;
        for index in 0..archive.len() {
            let mut member = archive.by_index(index).map_err(|_| {
                bundle_error(format!("native archive is unreadable: {}", path.display()))
            })?;
            let file_type = (member.external_attributes() >> 16) & 0o170000;
            if file_type != 0o100000 {
                return Err(bundle_error("native archive member is not regular"));
            }
            let name = member
                .name()
                .map_err(|_| {
                    bundle_error(format!("native archive is unreadable: {}", path.display()))
                })?
                .into_owned();
            let mut content = Vec::new();
            member.read_to_end(&mut content).map_err(|_| {
                bundle_error(format!("native archive is unreadable: {}", path.display()))
            })?;
            add(&name, content)?;
        }
    }
    Ok(payload)
}

pub(crate) fn verify_native_packages(
    source_root: &Path,
    source_ref: &str,
    root: &Path,
    targets: &[String],
) -> BundleResult<Value> {
    let source = GitSource::open(source_root)?;
    let commit = source.commit(source_ref)?;
    let tree = source.tree(&commit)?;
    let (manifest, manifest_digest) = source.resolve_profile(&commit)?;
    let version = native_release_version(&source.root, &commit)?;
    if targets.is_empty()
        || targets.iter().collect::<BTreeSet<_>>().len() != targets.len()
        || targets.iter().any(|target| !package_component(target))
    {
        return Err(bundle_error("native release targets are invalid"));
    }
    let mut expected_files = BTreeSet::new();
    for target in targets {
        for suffix in ["tar.gz", "tar.gz.sha256", "zip", "zip.sha256"] {
            expected_files.insert(format!("agent-canon-{version}-{target}.{suffix}"));
        }
    }
    let root_metadata = fs::symlink_metadata(root)
        .map_err(|_| bundle_error("native package directory is missing or unsafe"))?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(bundle_error(
            "native package directory is missing or unsafe",
        ));
    }
    let mut actual_files = BTreeMap::new();
    for entry in fs::read_dir(root)
        .map_err(|_| bundle_error("native package directory is missing or unsafe"))?
    {
        let entry =
            entry.map_err(|_| bundle_error("native package directory is missing or unsafe"))?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)
            .map_err(|_| bundle_error("native package directory is missing or unsafe"))?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(bundle_error("native release file set differs"));
        }
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| bundle_error("native release file set differs"))?;
        actual_files.insert(name, path);
    }
    if actual_files.keys().cloned().collect::<BTreeSet<_>>() != expected_files {
        return Err(bundle_error("native release file set differs"));
    }
    let layout = native_layout(&source, &commit, &manifest)?;
    let resources = layout
        .iter()
        .map(|(source_path, destination)| {
            Ok((destination.clone(), source.blob(&commit, source_path)?))
        })
        .collect::<BundleResult<BTreeMap<_, _>>>()?;
    const PROVENANCE_PATH: &str = "share/agent-canon/provenance.json";
    const SUMS_PATH: &str = "share/agent-canon/SHA256SUMS";
    let mut records = Vec::new();
    let mut sorted_targets = targets.to_vec();
    sorted_targets.sort();
    for target in &sorted_targets {
        let prefix = format!("agent-canon-{version}-{target}");
        let binary = if target.ends_with("-windows-msvc") {
            "bin/agent-canon.exe"
        } else {
            "bin/agent-canon"
        };
        let mut previous: Option<Payload> = None;
        for suffix in ["tar.gz", "zip"] {
            let filename = format!("{prefix}.{suffix}");
            let path = actual_files
                .get(&filename)
                .ok_or_else(|| bundle_error("native release file set differs"))?;
            let archive_bytes = fs::read(path)
                .map_err(|_| bundle_error("native release metadata is unreadable"))?;
            let archive_digest = digest(&archive_bytes);
            let sidecar_name = format!("{filename}.sha256");
            let sidecar = actual_files
                .get(&sidecar_name)
                .ok_or_else(|| bundle_error("native release file set differs"))?;
            let sidecar_bytes = fs::read(sidecar)
                .map_err(|_| bundle_error("native release metadata is unreadable"))?;
            let expected_sidecar = format!("{archive_digest}  {filename}\n");
            if sidecar_bytes != expected_sidecar.as_bytes() {
                return Err(bundle_error("native archive checksum differs"));
            }
            let payload = native_archive_payload(path, &prefix)?;
            let mut expected_payload = resources.keys().cloned().collect::<BTreeSet<_>>();
            expected_payload.insert(binary.to_owned());
            expected_payload.insert(PROVENANCE_PATH.to_owned());
            expected_payload.insert(SUMS_PATH.to_owned());
            if payload.keys().cloned().collect::<BTreeSet<_>>() != expected_payload {
                return Err(bundle_error("native archive resource set differs"));
            }
            if resources
                .iter()
                .any(|(name, expected)| payload.get(name) != Some(expected))
            {
                return Err(bundle_error("native archive resource differs from source"));
            }
            let provenance: Value = serde_json::from_slice(
                payload
                    .get(PROVENANCE_PATH)
                    .ok_or_else(|| bundle_error("native archive source identity differs"))?,
            )
            .map_err(|_| bundle_error("native release metadata is unreadable"))?;
            let source_identity = [
                ("schema", Value::String(NATIVE_CLI_SCHEMA.to_owned())),
                ("version", Value::String(version.clone())),
                ("target", Value::String(target.clone())),
                ("source_commit", Value::String(commit.clone())),
                ("source_tree", Value::String(tree.clone())),
                ("manifest_digest", Value::String(manifest_digest.clone())),
            ];
            if !provenance.is_object()
                || source_identity
                    .iter()
                    .any(|(key, expected)| provenance.get(*key) != Some(expected))
            {
                return Err(bundle_error("native archive source identity differs"));
            }
            let hashes = payload
                .iter()
                .map(|(name, content)| (name.clone(), digest(content)))
                .collect::<BTreeMap<_, _>>();
            let expected_sums = hashes
                .iter()
                .filter(|(name, _)| name.as_str() != SUMS_PATH)
                .map(|(name, sha)| format!("{sha}  {name}\n"))
                .collect::<String>();
            let sums = payload
                .get(SUMS_PATH)
                .ok_or_else(|| bundle_error("native resource checksum differs"))?;
            if sums != expected_sums.as_bytes() {
                return Err(bundle_error("native resource checksum differs"));
            }
            let expected_provenance_files = hashes
                .iter()
                .filter(|(name, _)| name.as_str() != PROVENANCE_PATH && name.as_str() != SUMS_PATH)
                .map(|(name, sha)| json!({"path": name, "sha256": sha}))
                .collect::<Vec<_>>();
            if provenance.get("files") != Some(&Value::Array(expected_provenance_files)) {
                return Err(bundle_error("native provenance file digests differ"));
            }
            if previous.as_ref().is_some_and(|before| before != &payload) {
                return Err(bundle_error(
                    "native archive formats contain different payloads",
                ));
            }
            previous = Some(payload);
            for artifact in [path, sidecar] {
                let bytes = fs::read(artifact)
                    .map_err(|_| bundle_error("native release metadata is unreadable"))?;
                let metadata = fs::metadata(artifact)
                    .map_err(|_| bundle_error("native release metadata is unreadable"))?;
                records.push(json!({
                    "path": artifact.file_name().and_then(|name| name.to_str()).unwrap_or_default(),
                    "sha256": digest(&bytes),
                    "size": metadata.len(),
                }));
            }
        }
    }
    records.sort_by(|left, right| {
        left.get("path")
            .and_then(Value::as_str)
            .cmp(&right.get("path").and_then(Value::as_str))
    });
    Ok(json!({
        "schema": "agent-canon.native-release.v1",
        "source_commit": commit,
        "source_tree": tree,
        "version": version,
        "targets": sorted_targets,
        "files": records,
    }))
}

fn parse_cli_options(
    args: &[String],
    allowed: &[&str],
    repeatable: &[&str],
) -> BundleResult<BTreeMap<String, Vec<String>>> {
    let mut options = BTreeMap::<String, Vec<String>>::new();
    let mut index = 0;
    while index < args.len() {
        let name = args[index].as_str();
        if !name.starts_with("--") {
            return Err(bundle_error(format!("unexpected argument: {name}")));
        }
        if !allowed.contains(&name) {
            return Err(bundle_error(format!("unknown option: {name}")));
        }
        let value = args
            .get(index + 1)
            .ok_or_else(|| bundle_error(format!("missing value for {name}")))?;
        let values = options.entry(name.to_owned()).or_default();
        if !values.is_empty() && !repeatable.contains(&name) {
            return Err(bundle_error(format!("duplicate option: {name}")));
        }
        values.push(value.clone());
        index += 2;
    }
    Ok(options)
}

fn required<'a>(options: &'a BTreeMap<String, Vec<String>>, name: &str) -> BundleResult<&'a str> {
    options
        .get(name)
        .and_then(|values| values.first())
        .map(String::as_str)
        .ok_or_else(|| bundle_error(format!("missing required option {name}")))
}

#[derive(Default)]
struct SpaceJsonFormatter;

impl serde_json::ser::Formatter for SpaceJsonFormatter {
    fn begin_array_value<W>(&mut self, writer: &mut W, first: bool) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        if first {
            Ok(())
        } else {
            writer.write_all(b", ")
        }
    }

    fn begin_object_key<W>(&mut self, writer: &mut W, first: bool) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        if first {
            Ok(())
        } else {
            writer.write_all(b", ")
        }
    }

    fn begin_object_value<W>(&mut self, writer: &mut W) -> io::Result<()>
    where
        W: ?Sized + Write,
    {
        writer.write_all(b": ")
    }
}

fn cli_json_bytes(value: &Value) -> BundleResult<Vec<u8>> {
    let mut bytes = Vec::new();
    let mut serializer = serde_json::Serializer::with_formatter(&mut bytes, SpaceJsonFormatter);
    value
        .serialize(&mut serializer)
        .map_err(|_| bundle_error("JSON serialization failed"))?;
    Ok(bytes)
}

fn print_json(value: &Value) -> BundleResult<()> {
    let bytes = cli_json_bytes(value)?;
    println!("{}", String::from_utf8_lossy(&bytes));
    Ok(())
}

/// Native implementation for the existing `template-bundle` command selector.
pub fn run(args: &[String]) -> i32 {
    let result = (|| -> BundleResult<(Value, Option<String>)> {
        let operation = args
            .first()
            .ok_or_else(|| bundle_error("template-bundle operation is required"))?;
        let rest = &args[1..];
        let options = match operation.as_str() {
            "export" => parse_cli_options(
                rest,
                &["--source-root", "--source-ref", "--profile", "--output"],
                &[],
            )?,
            "verify" => parse_cli_options(rest, &["--root", "--format"], &[])?,
            "native-package" => parse_cli_options(
                rest,
                &[
                    "--source-root",
                    "--source-ref",
                    "--binary",
                    "--target",
                    "--output",
                    "--toolchain",
                ],
                &[],
            )?,
            "native-verify" => parse_cli_options(
                rest,
                &["--source-root", "--source-ref", "--root", "--target"],
                &["--target"],
            )?,
            "native-version" => parse_cli_options(rest, &["--source-root", "--source-ref"], &[])?,
            "-h" | "--help" | "help" => {
                println!("Usage: agent-canon template-bundle <export|verify|native-package|native-verify|native-version> [options]");
                return Ok((Value::Null, None));
            }
            _ => return Err(bundle_error("template-bundle operation is invalid")),
        };
        let value = match operation.as_str() {
            "export" => export_bundle(
                Path::new(required(&options, "--source-root")?),
                required(&options, "--source-ref")?,
                required(&options, "--profile")?,
                Path::new(required(&options, "--output")?),
            )?,
            "verify" => {
                if let Some(format) = options.get("--format").and_then(|values| values.first()) {
                    if format != "json" && format != "install-tsv" {
                        return Err(bundle_error("verify format must be json or install-tsv"));
                    }
                }
                let result = verify_codex_user_bundle(Path::new(required(&options, "--root")?))?;
                let format = options
                    .get("--format")
                    .and_then(|values| values.first())
                    .map(String::as_str)
                    .unwrap_or("json");
                if format == "install-tsv" {
                    let digest = result
                        .get("bundle_digest")
                        .and_then(Value::as_str)
                        .unwrap_or_default();
                    let commit = result
                        .get("source_commit")
                        .and_then(Value::as_str)
                        .unwrap_or_default();
                    let mut tsv = format!("bundle\t{digest}\t{commit}\n");
                    let hashes = result
                        .get("files")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                        .filter_map(|row| {
                            Some((row.get("path")?.as_str()?, row.get("sha256")?.as_str()?))
                        })
                        .collect::<BTreeMap<_, _>>();
                    for row in result
                        .get("install_files")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                    {
                        let component = row
                            .get("component")
                            .and_then(Value::as_str)
                            .unwrap_or_default();
                        let bundle_path = row
                            .get("bundle_path")
                            .and_then(Value::as_str)
                            .unwrap_or_default();
                        let destination = row
                            .get("destination")
                            .and_then(Value::as_str)
                            .unwrap_or_default();
                        let file_hash = hashes.get(bundle_path).copied().unwrap_or_default();
                        tsv.push_str(&format!(
                            "install\t{component}\t{bundle_path}\t{destination}\t{file_hash}\n"
                        ));
                    }
                    return Ok((result, Some(tsv)));
                }
                result
            }
            "native-package" => package_native_cli(
                Path::new(required(&options, "--source-root")?),
                required(&options, "--source-ref")?,
                Path::new(required(&options, "--binary")?),
                required(&options, "--target")?,
                Path::new(required(&options, "--output")?),
                options
                    .get("--toolchain")
                    .and_then(|values| values.first())
                    .map(String::as_str)
                    .unwrap_or(""),
            )?,
            "native-verify" => {
                let targets = options
                    .get("--target")
                    .ok_or_else(|| bundle_error("native-verify requires --target"))?;
                verify_native_packages(
                    Path::new(required(&options, "--source-root")?),
                    required(&options, "--source-ref")?,
                    Path::new(required(&options, "--root")?),
                    targets,
                )?
            }
            "native-version" => json!({
                "version": native_release_version(
                    Path::new(required(&options, "--source-root")?),
                    required(&options, "--source-ref")?,
                )?
            }),
            _ => Value::Null,
        };
        Ok((value, None))
    })();
    match result {
        Ok((_, Some(tsv))) => {
            print!("{tsv}");
            0
        }
        Ok((value, None)) if value.is_null() => 0,
        Ok((value, None)) => match print_json(&value) {
            Ok(()) => 0,
            Err(error) => {
                print_cli_error(&error.to_string());
                2
            }
        },
        Err(error) => {
            print_cli_error(&error.to_string());
            2
        }
    }
}

fn print_cli_error(message: &str) {
    let value = json!({"status": "error", "error": message});
    let bytes = cli_json_bytes(&value).unwrap_or_else(|_| {
        b"{\"error\": \"serialization error\", \"status\": \"error\"}".to_vec()
    });
    eprintln!("{}", String::from_utf8_lossy(&bytes));
}
