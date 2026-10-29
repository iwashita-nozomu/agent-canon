// @dependency-start
// contract implementation
// responsibility Checks selected source files for dependency manifests, registered contract kinds, and typed edge syntax.
// upstream design ../../../../../documents/design/dependency-manifest-design.md manifest grammar and selected analysis route
// upstream design dependency_manifest.rs owns per-file dependency edge parsing and path diagnostics
// downstream implementation main.rs exposes the check-dependency-headers command
// downstream test ../../../../../tests/agent_tools/test_check_dependency_headers.py verifies native CLI behavior
// @dependency-end

use crate::dependency_manifest::{has_dependency_markers, parse_dependency_header};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use toml_edit::DocumentMut;

const REGISTRY: &str = "documents/design/dependency-contract-kinds.toml";
const CHECKABLE_SUFFIXES: &[&str] = &[
    ".bash", ".cfg", ".css", ".html", ".md", ".py", ".rst", ".sh", ".toml", ".txt", ".yaml",
    ".yml", ".zsh",
];
const SKIP_PREFIXES: &[&str] = &[".git/", ".pytest_cache/", ".ruff_cache/", "reports/"];
const RAW_NVIDIA_FIXTURE_PREFIX: &str = "tests/fixtures/nvidia/";
const NON_OWNING_PACKAGE_MARKER: &str = "\"\"\"Repository-local package namespace.\"\"\"";

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    changed: bool,
    allow_frontmatter: bool,
    help: bool,
    surfaces: Vec<String>,
    paths: Vec<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Registry {
    path: PathBuf,
    header_surfaces: Vec<String>,
    allowed_kinds: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    let args = match Args::parse(args) {
        Ok(args) => args,
        Err(message) => {
            eprintln!("agent-canon check-dependency-headers: {message}");
            eprintln!("usage: agent-canon check-dependency-headers [--root DIR] [--changed] [--allow-frontmatter] [--surface GLOB]... [paths...]");
            return 2;
        }
    };
    if args.help {
        println!("usage: agent-canon check-dependency-headers [--root DIR] [--changed] [--allow-frontmatter] [--surface GLOB]... [paths...]");
        return 0;
    }
    let _frontmatter_allowed_by_default = args.allow_frontmatter;

    let root = resolve_root(&args.root);
    let registry = match load_registry(&root) {
        Ok(registry) => registry,
        Err(message) => return fail(vec![message]),
    };
    if registry.allowed_kinds.is_empty() {
        return fail(vec![format!(
            "missing dependency contract kind registry: {}; fix: restore documents/design/dependency-contract-kinds.toml",
            registry.path.display()
        )]);
    }
    let paths = match request_paths(&root, &args, &registry.header_surfaces) {
        Ok(paths) => paths,
        Err(message) => return fail(vec![message]),
    };

    let mut findings = Vec::new();
    for requested in paths {
        let path = if requested.is_absolute() {
            requested
        } else {
            root.join(requested)
        };
        if !should_check(&root, &path) {
            continue;
        }
        let relative = repo_relative(&root, &path);
        let source = match canonical_source(&root, &path, &relative) {
            Ok(source) => source,
            Err(message) => {
                findings.push(message);
                continue;
            }
        };
        let parsed = parse_dependency_header(&relative, &source.path, &source.text);
        if !has_dependency_markers(&source.text) {
            findings.push(format!("{relative}: missing top dependency manifest block"));
            continue;
        }
        findings.extend(contract_kind_findings(
            &relative,
            &parsed.entries,
            &registry.allowed_kinds,
            &registry.path,
        ));
        findings.extend(parsed.diagnostics.into_iter().map(|diagnostic| {
            format!(
                "{}: dependency edge {} at line {}: {}",
                relative, diagnostic.code, diagnostic.source_span.start_line, diagnostic.message
            )
        }));
    }

    if findings.is_empty() {
        println!("DEPENDENCY_HEADERS=pass");
        0
    } else {
        fail(findings)
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut root = PathBuf::from(".");
        let mut changed = false;
        let mut allow_frontmatter = false;
        let mut surfaces = Vec::new();
        let mut paths = Vec::new();
        let mut index = 0;
        let mut positional_only = false;
        while index < args.len() {
            let argument = &args[index];
            if positional_only {
                paths.push(PathBuf::from(argument));
                index += 1;
                continue;
            }
            if argument == "--" {
                positional_only = true;
                index += 1;
                continue;
            }
            if argument == "-h" || argument == "--help" {
                return Ok(Self {
                    root,
                    changed,
                    allow_frontmatter,
                    help: true,
                    surfaces,
                    paths: Vec::new(),
                });
            }
            if argument == "--changed" {
                changed = true;
                index += 1;
                continue;
            }
            if argument == "--allow-frontmatter" {
                allow_frontmatter = true;
                index += 1;
                continue;
            }
            if argument == "--root" || argument == "--surface" {
                let value = args
                    .get(index + 1)
                    .ok_or_else(|| format!("{argument} requires a value"))?;
                if value.starts_with('-') {
                    return Err(format!("{argument} requires a value"));
                }
                if argument == "--root" {
                    root = PathBuf::from(value);
                } else {
                    surfaces.push(value.clone());
                }
                index += 2;
                continue;
            }
            if let Some(value) = argument.strip_prefix("--root=") {
                root = PathBuf::from(value);
                index += 1;
                continue;
            }
            if let Some(value) = argument.strip_prefix("--surface=") {
                surfaces.push(value.to_string());
                index += 1;
                continue;
            }
            if argument.starts_with('-') {
                return Err(format!("unknown argument {argument}"));
            }
            paths.push(PathBuf::from(argument));
            index += 1;
        }
        Ok(Self {
            root,
            changed,
            allow_frontmatter,
            help: false,
            surfaces,
            paths,
        })
    }
}

struct SourceText {
    path: PathBuf,
    text: String,
}

fn fail(findings: Vec<String>) -> i32 {
    println!("DEPENDENCY_HEADERS=fail");
    for finding in findings {
        println!("- {finding}");
    }
    1
}

fn resolve_root(root: &Path) -> PathBuf {
    let absolute = if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(root)
    };
    fs::canonicalize(&absolute).unwrap_or(absolute)
}

fn runtime_source_root() -> PathBuf {
    if let Some(root) = std::env::var_os("AGENT_CANON_SOURCE_ROOT") {
        return PathBuf::from(root);
    }
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")))
        .to_path_buf()
}

fn registry_candidates(root: &Path) -> Vec<PathBuf> {
    vec![
        root.join(REGISTRY),
        root.join("vendor/agent-canon").join(REGISTRY),
        runtime_source_root().join(REGISTRY),
    ]
}

fn load_registry(root: &Path) -> Result<Registry, String> {
    let path = registry_candidates(root)
        .into_iter()
        .find(|candidate| candidate.is_file())
        .unwrap_or_else(|| root.join(REGISTRY));
    let text = fs::read_to_string(&path).map_err(|error| {
        format!(
            "missing dependency contract kind registry: {}; fix: restore documents/design/dependency-contract-kinds.toml ({error})",
            path.display()
        )
    })?;
    let document = text.parse::<DocumentMut>().map_err(|error| {
        format!(
            "dependency contract registry is invalid: {}: {error}",
            path.display()
        )
    })?;
    if document.get("schema").and_then(|item| item.as_str())
        != Some("agent_canon.dependency_contract_kinds.v1")
    {
        return Err(format!(
            "dependency contract registry has an unsupported schema: {}",
            path.display()
        ));
    }
    let surfaces_item = document
        .get("header_surfaces")
        .and_then(|item| item.as_array())
        .ok_or_else(|| {
            format!(
                "dependency contract registry has no declared header surfaces: {}; add a non-empty header_surfaces list",
                path.display()
            )
        })?;
    if surfaces_item.is_empty() {
        return Err(format!(
            "dependency contract registry has no declared header surfaces: {}; add a non-empty header_surfaces list",
            path.display()
        ));
    }
    let mut header_surfaces = Vec::new();
    for value in surfaces_item.iter() {
        let Some(value) = value.as_str().filter(|value| !value.is_empty()) else {
            return Err(format!(
                "dependency contract registry contains an invalid header surface: {}; each header_surfaces entry must be a non-empty string",
                path.display()
            ));
        };
        header_surfaces.push(value.to_string());
    }
    let allowed_kinds = document
        .get("allowed_kinds")
        .and_then(|item| item.as_array())
        .map(|values| {
            values
                .iter()
                .filter_map(|value| value.as_str())
                .filter(|value| valid_kind_token(value))
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    Ok(Registry {
        path,
        header_surfaces,
        allowed_kinds,
    })
}

fn valid_kind_token(value: &str) -> bool {
    let mut chars = value.chars();
    chars
        .next()
        .is_some_and(|character| character.is_ascii_lowercase() || character.is_ascii_digit())
        && chars.all(|character| {
            character.is_ascii_lowercase() || character.is_ascii_digit() || character == '-'
        })
}

fn git_lines(root: &Path, args: &[&str]) -> Result<Vec<String>, String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("dependency header path selection could not run git: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "dependency header path selection git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect())
}

fn changed_paths(root: &Path) -> Result<Vec<PathBuf>, String> {
    let changed = git_lines(
        root,
        &["diff", "--name-only", "--diff-filter=ACMRT", "HEAD", "--"],
    )?;
    let untracked = git_lines(root, &["ls-files", "--others", "--exclude-standard"])?;
    Ok(changed
        .into_iter()
        .chain(untracked)
        .map(PathBuf::from)
        .collect())
}

fn request_paths(
    root: &Path,
    args: &Args,
    declared_surfaces: &[String],
) -> Result<Vec<PathBuf>, String> {
    if args.changed || args.paths.is_empty() {
        let mut patterns = declared_surfaces.to_vec();
        for surface in &args.surfaces {
            if !patterns.contains(surface) {
                patterns.push(surface.clone());
            }
        }
        return Ok(changed_paths(root)?
            .into_iter()
            .filter(|path| {
                matches_declared_surface(&repo_relative(root, &root.join(path)), &patterns)
            })
            .collect());
    }
    Ok(args.paths.clone())
}

fn repo_relative(root: &Path, path: &Path) -> String {
    let root_real = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    };
    let path_real = fs::canonicalize(&absolute).unwrap_or(absolute);
    path_real
        .strip_prefix(root_real)
        .map(|relative| relative.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path_real.to_string_lossy().replace('\\', "/"))
}

fn matches_declared_surface(relative: &str, patterns: &[String]) -> bool {
    patterns.iter().any(|pattern| {
        relative == pattern
            || fnmatch_case(relative, pattern)
            || (pattern.ends_with("/**")
                && relative.starts_with(&format!("{}/", pattern.trim_end_matches("/**"))))
    })
}

fn fnmatch_case(value: &str, pattern: &str) -> bool {
    let value = value.chars().collect::<Vec<_>>();
    let pattern = pattern.chars().collect::<Vec<_>>();
    let mut cache = HashMap::new();
    fn matches(
        value: &[char],
        pattern: &[char],
        value_index: usize,
        pattern_index: usize,
        cache: &mut HashMap<(usize, usize), bool>,
    ) -> bool {
        if let Some(result) = cache.get(&(value_index, pattern_index)) {
            return *result;
        }
        let result = if pattern_index == pattern.len() {
            value_index == value.len()
        } else {
            match pattern[pattern_index] {
                '*' => {
                    let mut next = pattern_index + 1;
                    while next < pattern.len() && pattern[next] == '*' {
                        next += 1;
                    }
                    matches(value, pattern, value_index, next, cache)
                        || (value_index < value.len()
                            && matches(value, pattern, value_index + 1, pattern_index, cache))
                }
                '?' => {
                    value_index < value.len()
                        && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
                }
                '[' => match class_match(pattern, pattern_index, value.get(value_index).copied()) {
                    Some((end, matched)) => {
                        matched && matches(value, pattern, value_index + 1, end + 1, cache)
                    }
                    None => {
                        value.get(value_index) == Some(&'[')
                            && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
                    }
                },
                literal => {
                    value.get(value_index) == Some(&literal)
                        && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
                }
            }
        };
        cache.insert((value_index, pattern_index), result);
        result
    }
    matches(&value, &pattern, 0, 0, &mut cache)
}

fn class_match(pattern: &[char], start: usize, value: Option<char>) -> Option<(usize, bool)> {
    let closing = (start + 1..pattern.len()).find(|index| pattern[*index] == ']')?;
    let Some(value) = value else {
        return Some((closing, false));
    };
    let mut index = start + 1;
    let negated = pattern
        .get(index)
        .is_some_and(|character| *character == '!');
    if negated {
        index += 1;
    }
    let mut matched = false;
    while index < closing {
        let low = pattern[index];
        if index + 2 < closing && pattern[index + 1] == '-' {
            let high = pattern[index + 2];
            matched |= low <= value && value <= high;
            index += 3;
        } else {
            matched |= value == low;
            index += 1;
        }
    }
    Some((closing, if negated { !matched } else { matched }))
}

fn should_check(root: &Path, path: &Path) -> bool {
    let Ok(metadata) = fs::symlink_metadata(path) else {
        return false;
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() || is_binary(path) {
        return false;
    }
    if is_non_owning_package_marker(path) {
        return false;
    }
    let relative = repo_relative(root, path);
    if SKIP_PREFIXES
        .iter()
        .any(|prefix| relative.starts_with(prefix))
    {
        return false;
    }
    if relative.starts_with(RAW_NVIDIA_FIXTURE_PREFIX)
        && path
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("txt"))
    {
        return false;
    }
    let suffix = path
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| format!(".{}", extension.to_ascii_lowercase()));
    suffix.is_some_and(|suffix| CHECKABLE_SUFFIXES.contains(&suffix.as_str()))
}

fn is_binary(path: &Path) -> bool {
    match fs::read(path) {
        Ok(bytes) => bytes.iter().take(4096).any(|byte| *byte == 0),
        Err(_) => true,
    }
}

fn is_non_owning_package_marker(path: &Path) -> bool {
    if path.file_name().and_then(|name| name.to_str()) != Some("__init__.py") {
        return false;
    }
    let Ok(text) = fs::read_to_string(path) else {
        return false;
    };
    let meaningful = text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join("\n");
    meaningful.is_empty() || meaningful == NON_OWNING_PACKAGE_MARKER
}

fn canonical_source(root: &Path, path: &Path, relative: &str) -> Result<SourceText, String> {
    let canonical_root = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let candidate = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    if !candidate.starts_with(&canonical_root) {
        return Err(format!(
            "{relative}: canonical dependency source escapes repository root"
        ));
    }
    if !candidate.is_file() {
        return Err(format!("{relative}: dependency source is missing"));
    }
    if candidate.is_symlink() || is_binary(&candidate) {
        return Err(format!(
            "{relative}: dependency source is not readable text"
        ));
    }
    let text = fs::read_to_string(&candidate)
        .map_err(|_| format!("{relative}: dependency source is not readable text"))?;
    Ok(SourceText {
        path: candidate,
        text,
    })
}

fn contract_kind_findings(
    relative: &str,
    entries: &[(usize, String)],
    allowed_kinds: &[String],
    registry_path: &Path,
) -> Vec<String> {
    let contract_lines = entries
        .iter()
        .filter(|(_, line)| line.starts_with("contract "))
        .map(|(_, line)| line.as_str())
        .collect::<Vec<_>>();
    if contract_lines.len() != 1 {
        return vec![format!(
            "{relative}: dependency manifest must contain exactly one contract line; fix: add 'contract <registered-kind>' after @dependency-start and choose the kind from {}",
            registry_path.display()
        )];
    }
    let Some(contract_kind) = contract_lines[0].strip_prefix("contract ") else {
        return vec![format!(
            "{relative}: contract line must be: contract <registered-kind>; fix: use lowercase kebab-case from {}",
            registry_path.display()
        )];
    };
    if !valid_kind_token(contract_kind) {
        return vec![format!(
            "{relative}: contract line must be: contract <registered-kind>; fix: use lowercase kebab-case from {}",
            registry_path.display()
        )];
    }
    if !allowed_kinds.iter().any(|kind| kind == contract_kind) {
        return vec![format!(
            "{relative}: unregistered dependency contract kind '{contract_kind}'; fix: use an existing allowed_kinds entry from {} or update the registry with review",
            registry_path.display()
        )];
    }
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::{fnmatch_case, matches_declared_surface};

    #[test]
    fn surface_globs_match_case_sensitively_and_preserve_recursive_surfaces() {
        assert!(fnmatch_case(
            "agents/canonical/example.md",
            "agents/canonical/*.md"
        ));
        assert!(fnmatch_case("docs/a1.md", "docs/a?.md"));
        assert!(fnmatch_case("docs/a.md", "docs/[a-z].md"));
        assert!(!fnmatch_case("docs/A.md", "docs/[a-z].md"));
        assert!(matches_declared_surface(
            "agents/canonical/nested/example.md",
            &["agents/canonical/**".to_string()]
        ));
    }

    #[test]
    fn character_classes_match_python_fnmatchcase_negation() {
        assert!(fnmatch_case("pkg/a.py", "pkg/[^a].py"));
        assert!(fnmatch_case("pkg/^.py", "pkg/[^a].py"));
        assert!(!fnmatch_case("pkg/b.py", "pkg/[^a].py"));
        assert!(fnmatch_case("pkg/b.py", "pkg/[!a].py"));
        assert!(fnmatch_case("pkg/^.py", "pkg/[!a].py"));
        assert!(!fnmatch_case("pkg/a.py", "pkg/[!a].py"));
    }
}
