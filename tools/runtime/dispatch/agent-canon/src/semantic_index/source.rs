// @dependency-start
// contract implementation
// responsibility Owns semantic-index filesystem discovery and node segmentation.
// upstream design ../../../../../../documents/design/semantic-index-module-boundaries.md approved semantic-index owner boundary
// upstream implementation ../main.rs canonical Rust CLI dispatch caller
// downstream implementation ../../../../../catalog.yaml command catalog and public command source
// downstream implementation ../../../../../repository/github/review_backlog_scan.sh process-level semantic-index behavior oracle
// @dependency-end

use super::model::{count_lines, relative_path, IndexedNode, TextNode};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

pub(super) fn path_metadata_size(path: &Path) -> Result<u64, String> {
    Ok(fs::metadata(path)
        .map_err(|error| format!("failed to stat {}: {error}", path.display()))?
        .len())
}

pub(super) fn discover_files(
    root: &Path,
    includes: &[PathBuf],
    excludes: &[String],
    max_file_bytes: u64,
) -> Result<Vec<PathBuf>, String> {
    let mut files = Vec::new();
    let mut seen = HashSet::new();
    let root_canonical = fs::canonicalize(root)
        .map_err(|error| format!("failed to canonicalize root {}: {error}", root.display()))?;
    for include in includes {
        let requested = if include.is_absolute() {
            if !include.starts_with(root) && !include.starts_with(&root_canonical) {
                return Err(format!(
                    "--include path {} is outside --root {}",
                    include.display(),
                    root.display()
                ));
            }
            include.clone()
        } else {
            root.join(include)
        };
        let start = fs::canonicalize(&requested).map_err(|error| {
            format!(
                "failed to canonicalize include path {}: {error}",
                requested.display()
            )
        })?;
        if !start.starts_with(&root_canonical) {
            return Err(format!(
                "--include path {} resolves outside --root {}",
                requested.display(),
                root.display()
            ));
        }
        collect_files(
            &root_canonical,
            &start,
            excludes,
            max_file_bytes,
            &mut seen,
            &mut files,
        )?;
    }
    files.sort();
    Ok(files)
}

fn collect_files(
    root: &Path,
    path: &Path,
    excludes: &[String],
    max_file_bytes: u64,
    seen: &mut HashSet<PathBuf>,
    files: &mut Vec<PathBuf>,
) -> Result<(), String> {
    if should_exclude(root, path, excludes) {
        return Ok(());
    }
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(_) => return Ok(()),
    };
    if metadata.file_type().is_symlink() {
        return Ok(());
    }
    if metadata.is_dir() {
        let entries = fs::read_dir(path)
            .map_err(|error| format!("failed to read directory {}: {error}", path.display()))?;
        for entry in entries {
            let entry = entry.map_err(|error| error.to_string())?;
            collect_files(root, &entry.path(), excludes, max_file_bytes, seen, files)?;
        }
        return Ok(());
    }
    if !metadata.is_file() || metadata.len() > max_file_bytes || !is_indexable(path) {
        return Ok(());
    }
    let canonical = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    if !canonical.starts_with(root) {
        return Ok(());
    }
    if seen.insert(canonical) {
        files.push(path.to_path_buf());
    }
    Ok(())
}

fn should_exclude(root: &Path, path: &Path, excludes: &[String]) -> bool {
    let relative = relative_path(root, path);
    let name = path
        .file_name()
        .and_then(|part| part.to_str())
        .unwrap_or("");
    excludes
        .iter()
        .any(|exclude| relative.contains(exclude) || name == exclude)
}

fn is_indexable(path: &Path) -> bool {
    let Some(extension) = path.extension().and_then(|part| part.to_str()) else {
        return false;
    };
    matches!(
        extension,
        "md" | "txt"
            | "rst"
            | "rs"
            | "py"
            | "toml"
            | "yaml"
            | "yml"
            | "json"
            | "jsonl"
            | "sh"
            | "sql"
    )
}

pub(super) fn segment_text(path: &str, text: &str) -> Vec<TextNode> {
    let total_lines = count_lines(text).max(1);
    let mut nodes = vec![TextNode {
        kind: "document".to_string(),
        line_start: 1,
        line_end: total_lines,
        text: format!("{path}\n{text}"),
        parent_index: None,
    }];
    if path.ends_with(".md") || path.ends_with(".markdown") {
        nodes.extend(markdown_sections(text));
    }
    nodes.extend(block_nodes(text));
    nodes
}

fn markdown_sections(text: &str) -> Vec<TextNode> {
    let lines: Vec<&str> = text.lines().collect();
    let mut heading_starts = Vec::new();
    for (index, line) in lines.iter().enumerate() {
        if line.trim_start().starts_with('#') {
            heading_starts.push(index);
        }
    }
    let mut nodes = Vec::new();
    for (position, start) in heading_starts.iter().enumerate() {
        let end = heading_starts
            .get(position + 1)
            .copied()
            .unwrap_or(lines.len());
        let section_text = lines[*start..end].join("\n");
        nodes.push(TextNode {
            kind: "section".to_string(),
            line_start: start + 1,
            line_end: end.max(start + 1),
            text: section_text,
            parent_index: Some(0),
        });
    }
    nodes
}

fn block_nodes(text: &str) -> Vec<TextNode> {
    let mut nodes = Vec::new();
    let mut start_line: Option<usize> = None;
    let mut buffer = Vec::new();
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            if let Some(start) = start_line.take() {
                nodes.push(TextNode {
                    kind: "block".to_string(),
                    line_start: start,
                    line_end: index,
                    text: buffer.join("\n"),
                    parent_index: Some(0),
                });
                buffer.clear();
            }
        } else {
            if start_line.is_none() {
                start_line = Some(index + 1);
            }
            buffer.push(line);
        }
    }
    if let Some(start) = start_line {
        nodes.push(TextNode {
            kind: "block".to_string(),
            line_start: start,
            line_end: count_lines(text).max(start),
            text: buffer.join("\n"),
            parent_index: Some(0),
        });
    }
    nodes
}

pub(super) fn context_excerpt(
    root: &Path,
    node: &IndexedNode,
    max_chars: usize,
) -> Result<String, String> {
    let path = root.join(&node.path);
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("failed to read context file {}: {error}", path.display()))?;
    let excerpt = text
        .lines()
        .enumerate()
        .filter_map(|(index, line)| {
            let line_number = index as i64 + 1;
            if line_number >= node.line_start && line_number <= node.line_end {
                Some(line)
            } else {
                None
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    Ok(bound_excerpt(&excerpt, max_chars))
}

fn bound_excerpt(text: &str, max_chars: usize) -> String {
    let trimmed = text.trim();
    if trimmed.chars().count() <= max_chars {
        return trimmed.to_string();
    }
    trimmed.chars().take(max_chars).collect::<String>()
}
