// @dependency-start
// contract implementation
// responsibility Composes native Markdown providers with AgentCanon-specific documentation checks.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust tool migration policy
// upstream design ../../../../../agents/skills/md-style-check.md Markdown style check skill contract
// upstream design ../../../../../documents/runtime/runtime-profiles-and-check-matrix.json canonical runtime profile inventory rendered by this module
// upstream implementation source_mutation.rs owns explicit capability-bound source rewrites
// downstream implementation ../../../../bin/agent-canon invokes this command through the CLI wrapper
// downstream implementation ../../../../../tests/tools/test_fix_mermaid.py tests native Mermaid syntax validation
// downstream test ../tests/source_mutation_native.rs validates source mutation capability behavior
// @dependency-end

use crate::source_mutation::SourceMutationCapability;
use regex::{Captures, Regex};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering as AtomicOrdering};
use std::sync::LazyLock;

static DOCS_TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

const DEFAULT_DOC_TARGETS: &[&str] = &[
    "README.md",
    "QUICK_START.md",
    "AGENTS.md",
    "agents",
    "docker",
    "documents",
    "scripts",
    ".github",
    ".codex/personal/skills",
    ".codex/README.md",
];

const DEFAULT_LINK_AUDIT_TARGETS: &[&str] = &[
    "README.md",
    "QUICK_START.md",
    "AGENTS.md",
    "agents",
    "documents",
    "scripts",
    ".github",
    ".codex/personal/skills",
    ".codex/README.md",
];

const LINK_SKIP_PARTS: &[&str] = &[".git", ".worktrees", "__pycache__", "Archive"];

static MARKDOWN_LINK_PATTERN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[([^\]]+)\]\(([^)]+)\)").expect("static Markdown link regex"));
static EXTERNAL_LINK_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[a-zA-Z][a-zA-Z0-9+.-]*://").expect("static external link scheme regex")
});

const BOOTSTRAP_DOCS: &[&str] = &[
    "README.md",
    "QUICK_START.md",
    "docker/README.md",
    "scripts/README.md",
    "documents/contracts/template-bootstrap.md",
    "documents/contracts/linux-wsl-host-requirements.md",
];

const DERIVED_REPO_STALE_STRINGS: &[&str] = &[
    "Project Template",
    "project-template",
    "/mnt/l/workspace/project_template/",
];

const SKIP_PARTS: &[&str] = &[".git", ".worktrees", "__pycache__", "Archive", "target"];

const RUNTIME_PROFILE_DEPENDENCY_HEADER: &str = "<!--
@dependency-start
contract reference
responsibility Defines AgentCanon runtime profiles and risk-based validation routing.
upstream design ../../ROOT_AGENTS.md root runtime entrypoint and closeout model
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
downstream design ../../agents/canonical/CODEX_WORKFLOW.md Codex execution workflow
downstream design ../agent-canon/agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream implementation ../../tools/validation/ci/runners/run_all_checks.sh repo check runner
downstream implementation ../../tools/catalog.yaml structured tool catalog
@dependency-end
-->
";

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    command: DocsCommand,
    root: PathBuf,
    paths: Vec<String>,
    apply: bool,
    check_after_apply: bool,
    mutation_capability_json: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DocsCommand {
    Check,
    Format,
    Links,
    RenderRuntimeProfile,
    Help,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Finding {
    path: Option<PathBuf>,
    line: Option<usize>,
    message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct WriteSummary {
    changed_files: usize,
    changes: usize,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => run_parsed(parsed),
        Err(message) => {
            eprintln!("docs: {message}");
            print_usage();
            2
        }
    }
}

fn run_parsed(args: Args) -> i32 {
    let root = fs::canonicalize(&args.root).unwrap_or_else(|_| args.root.clone());
    match args.command {
        DocsCommand::Help => {
            print_usage();
            0
        }
        DocsCommand::Check => render_check(&root, &args.paths),
        DocsCommand::Format => render_format(&root, &args.paths),
        DocsCommand::Links => run_link_audit(
            &root,
            &args.paths,
            args.apply,
            args.check_after_apply,
            args.mutation_capability_json.as_deref(),
        ),
        DocsCommand::RenderRuntimeProfile => render_runtime_profile_command(&root),
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let command = match args.first().map(|item| item.as_str()) {
            Some("check") => DocsCommand::Check,
            Some("format") => DocsCommand::Format,
            Some("links") => DocsCommand::Links,
            Some("render-runtime-profile") => DocsCommand::RenderRuntimeProfile,
            Some("help") | Some("--help") | Some("-h") => DocsCommand::Help,
            Some(other) => return Err(format!("unknown docs command {other}")),
            None => return Err("missing docs command".to_string()),
        };

        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
        let mut apply = false;
        let mut check_after_apply = false;
        let mut mutation_capability_json = None;
        let mut index = 1;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    let value = args
                        .get(index + 1)
                        .ok_or_else(|| "--root requires a value".to_string())?;
                    root = PathBuf::from(value);
                    index += 2;
                }
                "--apply" if command == DocsCommand::Links => {
                    apply = true;
                    index += 1;
                }
                "--check" if command == DocsCommand::Links => {
                    check_after_apply = true;
                    index += 1;
                }
                "--mutation-capability-json" if command == DocsCommand::Links => {
                    let value = args
                        .get(index + 1)
                        .ok_or_else(|| "--mutation-capability-json requires a value".to_string())?;
                    mutation_capability_json = Some(value.clone());
                    index += 2;
                }
                "--help" | "-h" => {
                    return Ok(Self {
                        command: DocsCommand::Help,
                        root,
                        paths,
                        apply,
                        check_after_apply,
                        mutation_capability_json,
                    });
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"));
                }
                value => {
                    paths.push(value.to_string());
                    index += 1;
                }
            }
        }

        Ok(Self {
            command,
            root,
            paths,
            apply,
            check_after_apply,
            mutation_capability_json,
        })
    }
}

fn usage_text() -> &'static str {
    "usage: agent-canon docs <command> [options] [paths...]\n\
\n\
commands:\n\
  check                   check Markdown lint, links, math, Mermaid, headings, and runtime-profile docs\n\
  format                  format Markdown, then run the adjacent docs check\n\
  links                   check Markdown links; --apply requires an exact source mutation capability\n\
  render-runtime-profile  render the runtime profile inventory\n\
  help, -h, --help        show this command contract\n\
\n\
options:\n\
  --root <repo-root>      repository root to evaluate; defaults to the current directory\n\
  --apply                 rewrite uniquely resolved links (links only)\n\
  --check                 run docs check after applying link rewrites (links only)\n\
  --mutation-capability-json <json>  authorize exact source paths for links --apply\n\
\n\
examples:\n\
  tools/bin/agent-canon docs -h\n\
  tools/bin/agent-canon docs check documents/tools/agent-canon.md\n\
  tools/bin/agent-canon docs links --apply --mutation-capability-json '<json>' documents/tools/agent-canon.md\n\
  tools/bin/agent-canon docs format README.md"
}

fn print_usage() {
    eprintln!("{}", usage_text());
}

fn render_runtime_profile_command(root: &Path) -> i32 {
    match render_runtime_profile_inventory(
        &root.join("documents/runtime/runtime-profiles-and-check-matrix.json"),
    ) {
        Ok(rendered) => {
            print!("{rendered}");
            0
        }
        Err(message) => {
            eprintln!("RUNTIME_PROFILE_INVENTORY_RENDER=fail");
            eprintln!("RUNTIME_PROFILE_INVENTORY_FINDING={message}");
            1
        }
    }
}

fn render_check(root: &Path, raw_paths: &[String]) -> i32 {
    let markdown_files = collect_markdown_files(root, raw_paths);
    let mut succeeded = run_markdownlint_cli(root, &markdown_files);
    succeeded &= run_lychee(root, &markdown_files);
    let mut findings = Vec::new();
    for path in &markdown_files {
        let text = match fs::read_to_string(path) {
            Ok(text) => text,
            Err(error) => {
                findings.push(Finding {
                    path: Some(path.clone()),
                    line: None,
                    message: format!("cannot read Markdown source: {error}"),
                });
                succeeded = false;
                continue;
            }
        };
        findings.extend(check_list_marker_consistency_by_depth(path, &text));
        match read_document_ast(root, path) {
            Ok(document) => {
                findings.extend(check_workspace_absolute_links(root, path, &document.links));
                findings.extend(check_markdown_math(path, &text, &document.math_fences));
                if document.has_mermaid {
                    succeeded &= run_mermaid_cli(root, path);
                }
            }
            Err(message) => {
                eprintln!("{}: {message}", display_path(root, path));
                succeeded = false;
            }
        }
    }
    findings.extend(check_bootstrap_docs(root));
    findings.extend(check_runtime_profile_inventory(root));
    succeeded &= render_findings(&findings, root);
    if succeeded {
        0
    } else {
        1
    }
}

fn render_format(root: &Path, raw_paths: &[String]) -> i32 {
    let summary = match format_markdown_files(root, raw_paths) {
        Ok(summary) => summary,
        Err(error) => {
            eprintln!("docs format: {error}");
            return 1;
        }
    };
    println!(
        "docs format: {} file(s), {} change(s)",
        summary.changed_files, summary.changes
    );
    render_check(root, raw_paths)
}

fn run_link_audit(
    root: &Path,
    raw_paths: &[String],
    apply: bool,
    check_after_apply: bool,
    mutation_capability_json: Option<&str>,
) -> i32 {
    let paths = if raw_paths.is_empty() {
        DEFAULT_LINK_AUDIT_TARGETS
            .iter()
            .map(|path| path.to_string())
            .collect::<Vec<_>>()
    } else {
        raw_paths.to_vec()
    };
    if !apply {
        if mutation_capability_json.is_some() {
            eprintln!("docs links: --mutation-capability-json is valid only with --apply");
            print_usage();
            return 2;
        }
        return render_check(root, &paths);
    }
    let capability = match SourceMutationCapability::from_json(root, mutation_capability_json) {
        Ok(capability) => capability,
        Err(error) => {
            eprintln!("mutation_capability_error: {error}");
            print_usage();
            return 2;
        }
    };
    let changes = match planned_link_rewrites(root, &paths) {
        Ok(changes) => changes,
        Err(error) => {
            eprintln!("docs links: {error}");
            return 1;
        }
    };
    // Validate every target before the first write, then the capability does
    // another resolution and no-follow check at the actual write boundary.
    let approved = match changes
        .into_iter()
        .map(|(path, contents)| {
            capability
                .assert_allowed(&path)
                .map(|resolved| (resolved, contents))
                .map_err(|error| format!("mutation_capability_error: {error}"))
        })
        .collect::<Result<Vec<_>, _>>()
    {
        Ok(approved) => approved,
        Err(error) => {
            eprintln!("{error}");
            return 2;
        }
    };
    for (path, contents) in &approved {
        if let Err(error) = capability.write_text(path, contents) {
            eprintln!("mutation_capability_error: {error}");
            return 1;
        }
    }
    println!("Applied link rewrites: {}", approved.len());
    if check_after_apply {
        render_check(root, &paths)
    } else {
        0
    }
}

fn planned_link_rewrites(
    root: &Path,
    raw_paths: &[String],
) -> Result<BTreeMap<PathBuf, String>, String> {
    let name_index = link_name_index(root);
    let mut changes = BTreeMap::new();
    for markdown_file in link_markdown_files(root, raw_paths) {
        let text = fs::read_to_string(&markdown_file)
            .map_err(|error| format!("cannot read {}: {error}", markdown_file.display()))?;
        let mut replacements = BTreeMap::new();
        for (_label, target) in find_markdown_links(&text) {
            let target = target.as_str();
            if is_external_link_target(target) {
                continue;
            }
            let (target_path, anchor) = split_link_anchor(target);
            if let Some(resolved) = resolve_local_link_target(root, &markdown_file, target_path) {
                if Path::new(target_path).is_absolute() && resolved.starts_with(root) {
                    if let Some(relative) = relative_link_target(&markdown_file, &resolved) {
                        replacements
                            .insert(target.to_string(), append_link_anchor(relative, anchor));
                    }
                }
                continue;
            }
            let basename = Path::new(target_path)
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default();
            let candidates = name_index
                .get(&basename)
                .into_iter()
                .flatten()
                .filter(|candidate| !candidate.to_string_lossy().ends_with(".bak"))
                .collect::<Vec<_>>();
            if candidates.len() == 1 {
                if let Some(relative) = relative_link_target(&markdown_file, candidates[0]) {
                    replacements.insert(target.to_string(), append_link_anchor(relative, anchor));
                }
            }
        }
        let rewritten = replace_link_targets(&text, &replacements);
        if rewritten != text {
            changes.insert(markdown_file, rewritten);
        }
    }
    Ok(changes)
}

fn find_markdown_links(text: &str) -> Vec<(String, String)> {
    MARKDOWN_LINK_PATTERN
        .captures_iter(text)
        .map(|captures| {
            (
                captures
                    .get(1)
                    .map_or("", |capture| capture.as_str())
                    .to_string(),
                captures
                    .get(2)
                    .map_or("", |capture| capture.as_str())
                    .to_string(),
            )
        })
        .collect()
}

fn replace_link_targets(text: &str, replacements: &BTreeMap<String, String>) -> String {
    MARKDOWN_LINK_PATTERN
        .replace_all(text, |captures: &Captures<'_>| {
            let label = captures.get(1).map_or("", |capture| capture.as_str());
            let target = captures.get(2).map_or("", |capture| capture.as_str());
            replacements.get(target).map_or_else(
                || {
                    captures
                        .get(0)
                        .map_or("", |capture| capture.as_str())
                        .to_string()
                },
                |replacement| format!("[{label}]({replacement})"),
            )
        })
        .into_owned()
}

fn link_markdown_files(root: &Path, raw_paths: &[String]) -> Vec<PathBuf> {
    let targets = if raw_paths.is_empty() {
        DEFAULT_LINK_AUDIT_TARGETS
            .iter()
            .map(|path| path.to_string())
            .collect::<Vec<_>>()
    } else {
        raw_paths.to_vec()
    };
    let mut files = BTreeSet::new();
    for target in targets {
        let path = normalize_input_path(root, &target);
        let Ok(path) = fs::canonicalize(&path) else {
            continue;
        };
        collect_link_markdown_target(&path, &mut files);
    }
    files.into_iter().collect()
}

fn collect_link_markdown_target(path: &Path, files: &mut BTreeSet<PathBuf>) {
    if link_skip_path(path) {
        return;
    }
    let Ok(lexical_metadata) = fs::symlink_metadata(path) else {
        return;
    };
    if lexical_metadata.file_type().is_symlink() {
        if fs::metadata(path).is_ok_and(|metadata| metadata.is_file())
            && path.extension().and_then(|extension| extension.to_str()) == Some("md")
        {
            files.insert(path.to_path_buf());
        }
        return;
    }
    if lexical_metadata.is_dir() {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                collect_link_markdown_target(&entry.path(), files);
            }
        }
    } else if lexical_metadata.is_file()
        && path.extension().and_then(|extension| extension.to_str()) == Some("md")
    {
        files.insert(path.to_path_buf());
    }
}

fn link_name_index(root: &Path) -> BTreeMap<String, Vec<PathBuf>> {
    let mut paths = BTreeSet::new();
    collect_link_files(root, &mut paths);
    let mut names = BTreeMap::<String, Vec<PathBuf>>::new();
    for path in paths {
        if let Some(name) = path.file_name() {
            names
                .entry(name.to_string_lossy().into_owned())
                .or_default()
                .push(path);
        }
    }
    names
}

fn collect_link_files(path: &Path, files: &mut BTreeSet<PathBuf>) {
    if link_skip_path(path) {
        return;
    }
    let Ok(lexical_metadata) = fs::symlink_metadata(path) else {
        return;
    };
    if lexical_metadata.file_type().is_symlink() {
        if fs::metadata(path).is_ok_and(|metadata| metadata.is_file()) {
            files.insert(path.to_path_buf());
        }
        return;
    }
    if lexical_metadata.is_dir() {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                collect_link_files(&entry.path(), files);
            }
        }
    } else if lexical_metadata.is_file() {
        files.insert(path.to_path_buf());
    }
}

fn link_skip_path(path: &Path) -> bool {
    path.components().any(|component| {
        let part = component.as_os_str().to_string_lossy();
        LINK_SKIP_PARTS.contains(&part.as_ref())
    })
}

fn is_external_link_target(target: &str) -> bool {
    EXTERNAL_LINK_PATTERN.is_match(target)
        || target.starts_with("mailto:")
        || target.starts_with('#')
}

fn split_link_anchor(target: &str) -> (&str, &str) {
    target.split_once('#').unwrap_or((target, ""))
}

fn resolve_local_link_target(root: &Path, source: &Path, target_path: &str) -> Option<PathBuf> {
    if target_path.is_empty() {
        return None;
    }
    let target = Path::new(target_path);
    if target.is_absolute() {
        return normalize_repo_absolute_link(root, target);
    }
    fs::canonicalize(source.parent()?.join(target_path)).ok()
}

fn normalize_repo_absolute_link(root: &Path, target: &Path) -> Option<PathBuf> {
    if !target.is_absolute() {
        return None;
    }
    if target.exists() {
        return Some(target.to_path_buf());
    }
    let root_name = root.file_name()?.to_string_lossy();
    let parts = target
        .components()
        .map(|component| component.as_os_str().to_os_string())
        .collect::<Vec<_>>();
    for index in (0..parts.len()).rev() {
        if parts[index].to_string_lossy() == root_name {
            let mut candidate = root.to_path_buf();
            for part in &parts[index + 1..] {
                candidate.push(part);
            }
            if candidate.exists() {
                return Some(candidate);
            }
        }
    }
    None
}

fn relative_link_target(source: &Path, target: &Path) -> Option<String> {
    let relative = pathdiff::diff_paths(target, source.parent()?)?;
    #[cfg(windows)]
    {
        Some(relative.to_string_lossy().replace('\\', "/"))
    }
    #[cfg(not(windows))]
    {
        Some(relative.to_string_lossy().into_owned())
    }
}

fn append_link_anchor(path: String, anchor: &str) -> String {
    if anchor.is_empty() {
        path
    } else {
        format!("{path}#{anchor}")
    }
}

fn render_findings(findings: &[Finding], root: &Path) -> bool {
    for finding in findings {
        let path = finding
            .path
            .as_ref()
            .map(|path| display_path(root, path))
            .unwrap_or_else(|| "-".to_string());
        let line = finding
            .line
            .map(|line| format!(":{line}"))
            .unwrap_or_default();
        eprintln!("{}{}: {}", path, line, finding.message);
    }
    findings.is_empty()
}

fn run_markdownlint_cli(root: &Path, files: &[PathBuf]) -> bool {
    if files.is_empty() {
        return true;
    }
    let mut command = Command::new("markdownlint-cli2");
    command
        .current_dir(root)
        .arg("--config")
        .arg(root.join(".markdownlint-cli2.jsonc"))
        .arg("--no-globs");
    for path in files {
        command.arg(format!(":{}", path.display()));
    }
    run_native_command("markdownlint-cli2", &mut command)
}

fn run_lychee(root: &Path, files: &[PathBuf]) -> bool {
    if files.is_empty() {
        return true;
    }
    let mut inputs = Vec::with_capacity(files.len());
    for path in files {
        let Some(relative) = pathdiff::diff_paths(path, root) else {
            eprintln!(
                "lychee: cannot make Markdown input relative to docs root: {}",
                path.display()
            );
            return false;
        };
        inputs.push(relative);
    }

    let mut command = Command::new("lychee");
    command
        .current_dir(root)
        .arg("--config")
        .arg(root.join("tools/validation/documentation/config/lychee.toml"))
        .args(inputs);
    run_native_command("lychee", &mut command)
}

fn run_native_command(name: &str, command: &mut Command) -> bool {
    let output = match command.output() {
        Ok(output) => output,
        Err(error) => {
            eprintln!("{name}: {error}");
            return false;
        }
    };
    let stdout_ok = io::stdout().lock().write_all(&output.stdout).is_ok();
    let stderr_ok = io::stderr().lock().write_all(&output.stderr).is_ok();
    stdout_ok && stderr_ok && output.status.success()
}

#[derive(Default)]
struct DocumentAst {
    links: Vec<String>,
    math_fences: Vec<String>,
    has_mermaid: bool,
}

fn read_document_ast(root: &Path, path: &Path) -> Result<DocumentAst, String> {
    let output = Command::new("quarto")
        .current_dir(root)
        .arg("pandoc")
        .arg(path)
        .arg("--to=json")
        .output()
        .map_err(|error| format!("quarto pandoc: {error}"))?;
    if !output.status.success() {
        let _ = io::stdout().lock().write_all(&output.stdout);
        let _ = io::stderr().lock().write_all(&output.stderr);
        return Err(format!("quarto pandoc exited with {}", output.status));
    }
    let document: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("quarto pandoc emitted invalid JSON AST: {error}"))?;
    let mut ast = DocumentAst::default();
    collect_document_ast(&document, &mut ast);
    Ok(ast)
}

fn collect_document_ast(value: &Value, document: &mut DocumentAst) {
    if let Some(kind) = value.get("t").and_then(Value::as_str) {
        match kind {
            "Link" | "Image" => {
                if let Some(target) = value
                    .get("c")
                    .and_then(Value::as_array)
                    .and_then(|content| content.get(2))
                    .and_then(Value::as_array)
                    .and_then(|target| target.first())
                    .and_then(Value::as_str)
                {
                    document.links.push(target.to_string());
                }
            }
            "CodeBlock" => {
                if let Some(classes) = value
                    .get("c")
                    .and_then(Value::as_array)
                    .and_then(|content| content.first())
                    .and_then(Value::as_array)
                    .and_then(|attributes| attributes.get(1))
                    .and_then(Value::as_array)
                {
                    for class in classes.iter().filter_map(Value::as_str) {
                        match class.to_ascii_lowercase().as_str() {
                            "mermaid" => document.has_mermaid = true,
                            "math" | "latex" | "tex" => {
                                document.math_fences.push(class.to_ascii_lowercase());
                            }
                            _ => {}
                        }
                    }
                }
            }
            _ => {}
        }
    }
    match value {
        Value::Array(items) => {
            for item in items {
                collect_document_ast(item, document);
            }
        }
        Value::Object(fields) => {
            for item in fields.values() {
                collect_document_ast(item, document);
            }
        }
        _ => {}
    }
}

fn run_mermaid_cli(root: &Path, path: &Path) -> bool {
    let directory = match DocsTemporaryDirectory::create("mermaid") {
        Ok(directory) => directory,
        Err(error) => {
            eprintln!("mmdc: cannot create temporary directory: {error}");
            return false;
        }
    };
    let config = directory.0.join("puppeteer.json");
    if let Err(error) = fs::write(&config, br#"{"args":["--no-sandbox"]}"#) {
        eprintln!("mmdc: cannot write Puppeteer configuration: {error}");
        return false;
    }
    let rendered_markdown = directory.0.join("rendered.md");
    let mut command = Command::new("mmdc");
    command
        .current_dir(root)
        .arg("--puppeteerConfigFile")
        .arg(config)
        .arg("-i")
        .arg(path)
        .arg("-o")
        .arg(rendered_markdown);
    run_native_command("mmdc", &mut command)
}

struct DocsTemporaryDirectory(PathBuf);

impl DocsTemporaryDirectory {
    fn create(purpose: &str) -> io::Result<Self> {
        for _ in 0..32 {
            let sequence = DOCS_TEMP_SEQUENCE.fetch_add(1, AtomicOrdering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "agent-canon-docs-{purpose}-{}-{sequence}",
                std::process::id()
            ));
            match fs::create_dir(&path) {
                Ok(()) => return Ok(Self(path)),
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error),
            }
        }
        Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "could not allocate a unique docs temporary directory",
        ))
    }
}

impl Drop for DocsTemporaryDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn format_markdown_files(root: &Path, raw_paths: &[String]) -> io::Result<WriteSummary> {
    rewrite_markdown_files(root, raw_paths, |text| {
        let text = text.replace("\r\n", "\n").replace('\r', "\n");
        let lines = text.split('\n').map(str::trim_end);
        let mut output = Vec::new();
        let mut blank_count = 0usize;
        for line in lines {
            if line.is_empty() {
                blank_count += 1;
            } else {
                blank_count = 0;
            }
            if blank_count <= 2 {
                output.push(line.to_string());
            }
        }
        let formatted = output.join("\n").trim_end_matches('\n').to_string() + "\n";
        let extra_changes = if formatted != text { 1 } else { 0 };
        (formatted, extra_changes)
    })
}

fn rewrite_markdown_files(
    root: &Path,
    raw_paths: &[String],
    rewrite: fn(&str) -> (String, usize),
) -> io::Result<WriteSummary> {
    let mut changed_files = 0usize;
    let mut changes = 0usize;
    for path in collect_markdown_files(root, raw_paths) {
        let original = fs::read_to_string(&path)?;
        let (updated, file_changes) = rewrite(&original);
        if updated == original {
            continue;
        }
        fs::write(&path, updated)?;
        changed_files += 1;
        changes += file_changes.max(1);
        println!("formatted {}", display_path(root, &path));
    }
    Ok(WriteSummary {
        changed_files,
        changes,
    })
}

fn collect_markdown_files(root: &Path, raw_paths: &[String]) -> Vec<PathBuf> {
    let targets: Vec<String> = if raw_paths.is_empty() {
        DEFAULT_DOC_TARGETS
            .iter()
            .map(|item| item.to_string())
            .collect()
    } else {
        raw_paths.to_vec()
    };
    let mut files = BTreeSet::new();
    for target in targets {
        let path = normalize_input_path(root, &target);
        collect_one_markdown_target(&path, &mut files);
    }
    files.into_iter().collect()
}

fn collect_one_markdown_target(path: &Path, files: &mut BTreeSet<PathBuf>) {
    if skip_path(path) {
        return;
    }
    if path.is_dir() {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                collect_one_markdown_target(&entry.path(), files);
            }
        }
        return;
    }
    if path.is_file() && path.extension().and_then(|ext| ext.to_str()) == Some("md") {
        files.insert(path.to_path_buf());
    }
}

fn normalize_input_path(root: &Path, raw: &str) -> PathBuf {
    let path = PathBuf::from(raw);
    if path.is_absolute() {
        path
    } else {
        root.join(path)
    }
}

fn skip_path(path: &Path) -> bool {
    path.components().any(|component| {
        let value = component.as_os_str().to_string_lossy();
        SKIP_PARTS.contains(&value.as_ref())
    })
}

fn check_list_marker_consistency_by_depth(path: &Path, text: &str) -> Vec<Finding> {
    let mut markers: BTreeMap<usize, BTreeSet<char>> = BTreeMap::new();
    for line in text.lines() {
        let trimmed = line.trim_start_matches(' ');
        let indent = line.len() - trimmed.len();
        if let Some(marker) = unordered_marker(trimmed) {
            markers.entry(indent / 2).or_default().insert(marker);
        }
    }
    markers
        .into_iter()
        .filter(|(_, values)| values.len() > 1)
        .map(|(depth, values)| Finding {
            path: Some(path.to_path_buf()),
            line: None,
            message: format!(
                "MD004 inconsistent unordered list markers at depth {depth}: {values:?}"
            ),
        })
        .collect()
}

fn unordered_marker(line: &str) -> Option<char> {
    let mut chars = line.chars();
    let marker = chars.next()?;
    if matches!(marker, '-' | '*' | '+') && chars.next() == Some(' ') {
        Some(marker)
    } else {
        None
    }
}

fn opening_fence_info(line: &str) -> Option<(char, usize, &str)> {
    let trimmed = line.trim_start();
    let fence_char = trimmed.chars().next()?;
    if !matches!(fence_char, '`' | '~') {
        return None;
    }
    let fence_len = trimmed.chars().take_while(|ch| *ch == fence_char).count();
    if fence_len < 3 {
        return None;
    }
    Some((fence_char, fence_len, &trimmed[fence_len..]))
}

fn is_closing_fence(line: &str, fence_char: char, fence_len: usize) -> bool {
    let trimmed = line.trim();
    let count = trimmed.chars().take_while(|ch| *ch == fence_char).count();
    count >= fence_len && trimmed[count..].trim().is_empty()
}

fn check_markdown_math(path: &Path, text: &str, math_fences: &[String]) -> Vec<Finding> {
    // Pandoc normalizes source delimiter spelling into Math nodes, so retain
    // only this spelling residual beside the shared AST parser.
    let mut findings = Vec::new();
    for language in math_fences {
        findings.push(math_finding(
            path,
            None,
            &format!(
                "mathematical notation belongs in a standalone `$$` display block, not a `{language}` code fence"
            ),
        ));
    }

    let mut fence: Option<(char, usize)> = None;
    let mut in_display_block = false;
    for (line_index, line) in text.lines().enumerate() {
        let trimmed = line.trim_start();
        if let Some((fence_char, fence_len)) = fence {
            if is_closing_fence(trimmed, fence_char, fence_len) {
                fence = None;
            }
            continue;
        }
        if let Some((fence_char, fence_len, _)) = opening_fence_info(trimmed) {
            fence = Some((fence_char, fence_len));
            continue;
        }

        let line_no = Some(line_index + 1);
        let markdown_text = remove_inline_code_spans(line);
        if markdown_text.contains("\\(") || markdown_text.contains("\\)") {
            findings.push(math_finding(
                path,
                line_no,
                "inline math must use `$...$`, not `\\(...\\)`",
            ));
        }
        if markdown_text.contains("\\[") || markdown_text.contains("\\]") {
            findings.push(math_finding(
                path,
                line_no,
                "display math must use `$$...$$`, not `\\[...\\]`",
            ));
        }

        let compact = markdown_text.trim();
        if compact == "$$" {
            in_display_block = !in_display_block;
            continue;
        }
        if compact == "$" {
            findings.push(math_finding(
                path,
                line_no,
                "display math must use `$$...$$`, not `$` block delimiters",
            ));
            continue;
        }
        if in_display_block {
            continue;
        }
        if compact.starts_with('$')
            && compact.ends_with('$')
            && !compact.starts_with("$$")
            && compact.len() > 2
        {
            findings.push(math_finding(
                path,
                line_no,
                "display math must use `$$...$$`, not `$...$` on its own line",
            ));
            continue;
        }
        if compact.starts_with("$$") && compact.ends_with("$$") {
            continue;
        }
        if markdown_text.contains("$$") {
            findings.push(math_finding(
                path,
                line_no,
                "inline math must use `$...$`, not `$$...$$`",
            ));
        }
    }
    findings
}

fn remove_inline_code_spans(line: &str) -> String {
    let bytes = line.as_bytes();
    let mut output = String::with_capacity(line.len());
    let mut cursor = 0;
    while cursor < bytes.len() {
        if bytes[cursor] != b'`' {
            let character = line[cursor..].chars().next().unwrap_or_default();
            output.push(character);
            cursor += character.len_utf8();
            continue;
        }
        let run_end = cursor
            + bytes[cursor..]
                .iter()
                .take_while(|byte| **byte == b'`')
                .count();
        let run_length = run_end - cursor;
        let mut search = run_end;
        let closing = loop {
            let Some(offset) = bytes[search..].iter().position(|byte| *byte == b'`') else {
                break None;
            };
            let candidate = search + offset;
            let candidate_end = candidate
                + bytes[candidate..]
                    .iter()
                    .take_while(|byte| **byte == b'`')
                    .count();
            if candidate_end - candidate == run_length {
                break Some(candidate_end);
            }
            search = candidate_end;
        };
        if let Some(end) = closing {
            output.push_str(&" ".repeat(end - cursor));
            cursor = end;
        } else {
            output.push_str(&line[cursor..run_end]);
            cursor = run_end;
        }
    }
    output
}

fn math_finding(path: &Path, line: Option<usize>, message: &str) -> Finding {
    Finding {
        path: Some(path.to_path_buf()),
        line,
        message: message.to_string(),
    }
}
fn check_workspace_absolute_links(root: &Path, source: &Path, targets: &[String]) -> Vec<Finding> {
    targets
        .iter()
        .filter(|target| workspace_absolute_target(root, target))
        .map(|target| Finding {
            path: Some(source.to_path_buf()),
            line: None,
            message: format!("workspace-absolute Markdown target should be relative: {target}"),
        })
        .collect()
}

fn workspace_absolute_target(root: &Path, target: &str) -> bool {
    let target_path = target.split('#').next().unwrap_or(target);
    let raw = Path::new(target_path);
    raw.is_absolute() && (raw.starts_with(root) || map_absolute_workspace_path(root, raw).is_some())
}

fn map_absolute_workspace_path(root: &Path, path: &Path) -> Option<PathBuf> {
    let root_name = root.file_name()?.to_string_lossy();
    let parts: Vec<String> = path
        .components()
        .map(|component| component.as_os_str().to_string_lossy().to_string())
        .collect();
    for index in (0..parts.len()).rev() {
        if parts[index] == root_name {
            let mut mapped = root.to_path_buf();
            for part in &parts[index + 1..] {
                mapped.push(part);
            }
            return Some(mapped);
        }
    }
    None
}
fn check_bootstrap_docs(root: &Path) -> Vec<Finding> {
    let mut findings = Vec::new();
    let project_name = current_project_name(root);
    let check_stale = !matches!(project_name.as_deref(), None | Some("project-template"));
    for relative in BOOTSTRAP_DOCS {
        let path = root.join(relative);
        if !path.is_file() {
            continue;
        }
        let Ok(text) = fs::read_to_string(&path) else {
            continue;
        };
        for (line_index, line) in text.lines().enumerate() {
            if !check_stale {
                continue;
            }
            for stale in DERIVED_REPO_STALE_STRINGS {
                if line.contains(stale) {
                    findings.push(Finding {
                        path: Some(path.clone()),
                        line: Some(line_index + 1),
                        message: format!("stale template bootstrap text remains: {stale}"),
                    });
                }
            }
        }
    }
    findings
}

fn current_project_name(root: &Path) -> Option<String> {
    let text = fs::read_to_string(root.join("pyproject.toml")).ok()?;
    let mut in_project = false;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            in_project = trimmed == "[project]";
            continue;
        }
        if !in_project || !trimmed.starts_with("name") {
            continue;
        }
        let (_, value) = trimmed.split_once('=')?;
        return Some(
            value
                .trim()
                .trim_matches('"')
                .trim_matches('\'')
                .to_string(),
        );
    }
    None
}

fn check_runtime_profile_inventory(root: &Path) -> Vec<Finding> {
    let inventory_path = root.join("documents/runtime/runtime-profiles-and-check-matrix.json");
    let doc_path = root.join("documents/runtime/runtime-profiles-and-check-matrix.md");
    if !inventory_path.is_file() || !doc_path.is_file() {
        return Vec::new();
    }
    let rendered = match render_runtime_profile_inventory(&inventory_path) {
        Ok(rendered) => rendered,
        Err(message) => {
            return vec![Finding {
                path: Some(inventory_path),
                line: None,
                message,
            }];
        }
    };
    let current = fs::read_to_string(&doc_path).unwrap_or_default();
    if current == rendered {
        Vec::new()
    } else {
        vec![Finding {
            path: Some(doc_path),
            line: None,
            message:
                "runtime profile inventory markdown drifts from documents/runtime/runtime-profiles-and-check-matrix.json"
                    .to_string(),
        }]
    }
}

fn render_runtime_profile_inventory(path: &Path) -> Result<String, String> {
    let raw = fs::read_to_string(path).map_err(|error| format!("read failed: {error}"))?;
    let value: Value =
        serde_json::from_str(&raw).map_err(|error| format!("invalid JSON: {error}"))?;
    let object = value
        .as_object()
        .ok_or_else(|| "inventory JSON must be an object".to_string())?;
    let title = required_string(object.get("title"), "inventory.title")?;
    let summary = required_string_array(object.get("summary"), "inventory.summary")?;
    let profile_classes =
        required_array(object.get("profile_classes"), "inventory.profile_classes")?;
    let risk_classes = required_array(object.get("risk_classes"), "inventory.risk_classes")?;
    let check_matrix = required_array(object.get("check_matrix"), "inventory.check_matrix")?;
    let compatibility_note = required_string_array(
        object.get("compatibility_note"),
        "inventory.compatibility_note",
    )?;
    let risk_note = required_string_array(object.get("risk_note"), "inventory.risk_note")?;
    let validation_failure_response = required_object(
        object.get("validation_failure_response"),
        "inventory.validation_failure_response",
    )?;
    let closeout_rule =
        required_string_array(object.get("closeout_rule"), "inventory.closeout_rule")?;

    let mut output = String::new();
    output.push_str(RUNTIME_PROFILE_DEPENDENCY_HEADER.trim_end());
    output.push_str("\n\n");
    output.push_str(&format!("# {title}\n\n"));
    output.push_str("Source of truth: [runtime-profiles-and-check-matrix.json](runtime-profiles-and-check-matrix.json).\n\n");
    output.push_str(&render_paragraph(&summary));
    output.push('\n');
    output.push_str("## Profile Classes\n\n");
    let mut profile_rows = Vec::new();
    for item in profile_classes {
        let item = item
            .as_object()
            .ok_or_else(|| "inventory.profile_classes entries must be objects".to_string())?;
        let profile_id = required_string(item.get("id"), "profile_classes.id")?;
        let profile = required_string(item.get("profile"), "profile_classes.profile")?;
        let activates = required_string_array(item.get("activates"), "profile_classes.activates")?;
        let required_when =
            required_string(item.get("required_when"), "profile_classes.required_when")?;
        profile_rows.push(vec![
            profile_id,
            profile,
            activates.join(", "),
            required_when,
        ]);
    }
    output.push_str(&render_table(
        &["Profile ID", "Profile", "Activates", "Required when"],
        &profile_rows,
    ));
    output.push('\n');
    output.push_str(&render_paragraph(&compatibility_note));
    output.push('\n');
    output.push('\n');
    output.push_str("## Risk Classes\n\n");
    let mut risk_rows = Vec::new();
    for item in risk_classes {
        let item = item
            .as_object()
            .ok_or_else(|| "inventory.risk_classes entries must be objects".to_string())?;
        risk_rows.push(vec![
            required_string(item.get("risk"), "risk_classes.risk")?,
            required_string(item.get("examples"), "risk_classes.examples")?,
            required_string(
                item.get("required_validation"),
                "risk_classes.required_validation",
            )?,
        ]);
    }
    output.push_str(&render_table(
        &["Risk", "Examples", "Required validation"],
        &risk_rows,
    ));
    output.push('\n');
    output.push_str(&render_paragraph(&risk_note));
    output.push('\n');
    output.push_str(&render_validation_failure_response(
        validation_failure_response,
    )?);
    output.push('\n');
    output.push_str("## Check Matrix\n\n");
    let mut check_rows = Vec::new();
    for item in check_matrix {
        let item = item
            .as_object()
            .ok_or_else(|| "inventory.check_matrix entries must be objects".to_string())?;
        check_rows.push(vec![
            required_string(item.get("changed_surface"), "check_matrix.changed_surface")?,
            required_string_array(item.get("required_check"), "check_matrix.required_check")?
                .join("; "),
        ]);
    }
    output.push_str(&render_table(
        &["Changed surface", "Required check"],
        &check_rows,
    ));
    output.push('\n');
    output.push_str("## Closeout Rule\n\n");
    output.push_str(&render_paragraph(&closeout_rule));
    Ok(output.trim_end().to_string() + "\n")
}

fn render_validation_failure_response(
    item: &serde_json::Map<String, Value>,
) -> Result<String, String> {
    let rule = required_string_array(item.get("rule"), "validation_failure_response.rule")?;
    let cause_classes = required_string_array(
        item.get("cause_classes"),
        "validation_failure_response.cause_classes",
    )?;
    let required_fields = required_string_array(
        item.get("required_fields"),
        "validation_failure_response.required_fields",
    )?;
    let intent_preservation = required_string_array(
        item.get("intent_preservation"),
        "validation_failure_response.intent_preservation",
    )?;
    let repair_routes = required_string_array(
        item.get("repair_routes"),
        "validation_failure_response.repair_routes",
    )?;

    let mut output = String::new();
    output.push_str("## Validation Failure Response\n\n");
    output.push_str(&render_paragraph(&rule));
    output.push('\n');
    output.push_str("Required machine fields:\n\n");
    for field in required_fields {
        output.push_str(&format!("- `{field}`\n"));
    }
    output.push('\n');
    output.push_str("Valid `cause_classification` values are:\n\n");
    for cause_class in cause_classes {
        output.push_str(&format!("- `{cause_class}`\n"));
    }
    output.push_str("\nValid `intent_preservation` values are:\n\n");
    for route in intent_preservation {
        output.push_str(&format!("- `{route}`\n"));
    }
    output.push_str("\nIntent preservation routes:\n\n");
    for repair_route in repair_routes {
        output.push_str(&format!("- {repair_route}\n"));
    }
    Ok(output.trim_end().to_string() + "\n")
}

fn required_string(value: Option<&Value>, name: &str) -> Result<String, String> {
    let Some(value) = value.and_then(Value::as_str) else {
        return Err(format!("{name} must be a non-empty string"));
    };
    if value.trim().is_empty() {
        return Err(format!("{name} must be a non-empty string"));
    }
    Ok(value.to_string())
}

fn required_array<'a>(value: Option<&'a Value>, name: &str) -> Result<&'a Vec<Value>, String> {
    value
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{name} must be a list"))
}

fn required_object<'a>(
    value: Option<&'a Value>,
    name: &str,
) -> Result<&'a serde_json::Map<String, Value>, String> {
    value
        .and_then(Value::as_object)
        .ok_or_else(|| format!("{name} must be an object"))
}

fn required_string_array(value: Option<&Value>, name: &str) -> Result<Vec<String>, String> {
    required_array(value, name)?
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_string)
                .ok_or_else(|| format!("{name} must be a list of strings"))
        })
        .collect()
}

fn render_paragraph(lines: &[String]) -> String {
    lines.join("\n").trim_end().to_string() + "\n"
}

fn render_table(headers: &[&str], rows: &[Vec<String>]) -> String {
    let mut output = String::new();
    output.push_str("| ");
    output.push_str(&headers.join(" | "));
    output.push_str(" |\n| ");
    output.push_str(&vec!["---"; headers.len()].join(" | "));
    output.push_str(" |\n");
    for row in rows {
        output.push_str("| ");
        output.push_str(&row.join(" | "));
        output.push_str(" |\n");
    }
    output.trim_end().to_string() + "\n"
}

fn display_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_unordered_marker_consistency_scoped_to_each_depth() {
        let path = Path::new("list.md");
        assert!(check_list_marker_consistency_by_depth(path, "- parent\n  - child\n").is_empty());

        let findings = check_list_marker_consistency_by_depth(path, "- first\n+ second\n");
        assert_eq!(findings.len(), 1);
        assert!(findings[0].message.contains("at depth 0"));
    }

    #[test]
    fn keeps_exact_math_delimiter_policy_without_scanning_code_fences() {
        let path = Path::new("doc.md");
        let findings = check_markdown_math(
            path,
            "Inline `\\(literal\\)` and \\(x\\); display \\[y\\].\n\n$$z$$ inline.\n\n```text\n\\(code\\)\n```\n",
            &[],
        );

        assert_eq!(findings.len(), 3);
        assert!(findings[0].message.contains("inline math must use"));
        assert!(findings[1].message.contains("display math must use"));
        assert!(findings[2].message.contains("inline math must use"));
    }

    #[test]
    fn rejects_math_code_fences_reported_by_the_markdown_ast() {
        let findings = check_markdown_math(
            Path::new("doc.md"),
            "```math\nx + y\n```\n",
            &["math".to_string()],
        );

        assert_eq!(findings.len(), 1);
        assert!(findings[0].message.contains("not a `math` code fence"));
    }

    #[test]
    fn reads_links_and_validation_fences_from_pandoc_ast_shape() {
        let ast = serde_json::json!({
            "blocks": [
                {
                    "t": "Para",
                    "c": [{
                        "t": "Link",
                        "c": [
                            [{"t": "Str", "c": "label"}],
                            [{"t": "Str", "c": "target"}],
                            ["/repo/docs/guide.md", ""]
                        ]
                    }]
                },
                {
                    "t": "CodeBlock",
                    "c": [
                        ["", ["mermaid"], []],
                        "flowchart LR\n  a --> b"
                    ]
                },
                {
                    "t": "CodeBlock",
                    "c": [["", ["tex"], []], "x + y"]
                }
            ]
        });
        let mut document = DocumentAst::default();

        collect_document_ast(&ast, &mut document);

        assert_eq!(document.links, vec!["/repo/docs/guide.md"]);
        assert!(document.has_mermaid);
        assert_eq!(document.math_fences, vec!["tex"]);
    }

    #[test]
    fn workspace_absolute_link_policy_uses_ast_targets() {
        let root = std::env::temp_dir().join("agent-canon-docs-workspace");
        let inside = format!("{}#section", root.join("docs/guide.md").display());
        let outside = std::env::temp_dir().join("agent-canon-docs-other/guide.md");
        assert!(workspace_absolute_target(&root, &inside));
        assert!(!workspace_absolute_target(&root, "docs/guide.md"));
        assert!(!workspace_absolute_target(
            &root,
            &outside.to_string_lossy()
        ));
    }

    #[test]
    fn help_exposes_check_and_format_commands() {
        let usage = usage_text();

        assert!(usage.contains("docs check"));
        assert!(usage.contains("docs format"));
        assert!(usage.contains("docs links"));
        assert!(usage.contains("--mutation-capability-json"));
    }

    #[test]
    fn parses_formatter_command_arguments() {
        let args = vec![
            "format".to_string(),
            "--root".to_string(),
            "/repo".to_string(),
            "README.md".to_string(),
        ];
        let parsed = Args::parse(&args).expect("args should parse");

        assert_eq!(parsed.command, DocsCommand::Format);
        assert_eq!(parsed.root, PathBuf::from("/repo"));
        assert_eq!(parsed.paths, vec!["README.md"]);
    }

    #[test]
    fn parses_link_apply_arguments_without_weakening_other_docs_commands() {
        let args = vec![
            "links".to_string(),
            "--root".to_string(),
            "/repo".to_string(),
            "--apply".to_string(),
            "--check".to_string(),
            "--mutation-capability-json".to_string(),
            "{\"allowed_paths\":[\"README.md\"],\"purpose\":\"test\",\"authority\":\"issue-1630\"}"
                .to_string(),
            "README.md".to_string(),
        ];
        let parsed = Args::parse(&args).expect("native link arguments parse");
        assert_eq!(parsed.command, DocsCommand::Links);
        assert_eq!(parsed.root, PathBuf::from("/repo"));
        assert_eq!(parsed.paths, vec!["README.md"]);
        assert!(parsed.apply);
        assert!(parsed.check_after_apply);
        assert!(parsed.mutation_capability_json.is_some());
        assert!(Args::parse(&["check".to_string(), "--apply".to_string()]).is_err());
    }

    fn write_link_fixture(root: &Path, relative: &str, contents: &str) -> PathBuf {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().expect("link fixture has a parent"))
            .expect("link fixture parent is created");
        fs::write(&path, contents).expect("link fixture is written");
        path
    }

    #[test]
    fn links_read_only_route_runs_docs_check_without_source_report() {
        let temporary = DocsTemporaryDirectory::create("links-read-only")
            .expect("temporary docs root is created");
        let root = temporary
            .0
            .canonicalize()
            .expect("temporary docs root is canonical");

        assert_eq!(
            run_link_audit(&root, &["missing.md".to_string()], false, false, None),
            0
        );
        assert!(!root.join("reports").exists());
    }

    #[test]
    fn links_apply_requires_capability_before_source_write() {
        let temporary = DocsTemporaryDirectory::create("links-missing-capability")
            .expect("temporary docs root is created");
        let root = temporary
            .0
            .canonicalize()
            .expect("temporary docs root is canonical");
        write_link_fixture(&root, "README.md", "# Root\n");
        let guide = write_link_fixture(&root, "docs/guide.md", "[root](README.md)\n");
        let before = fs::read(&guide).expect("guide bytes are captured");

        assert_eq!(
            run_link_audit(&root, &["docs/guide.md".to_string()], true, false, None),
            2
        );
        assert_eq!(fs::read(guide).expect("guide remains readable"), before);
        assert!(!root.join("reports").exists());
    }

    #[test]
    fn links_apply_writes_only_exact_allowlisted_source_paths() {
        let temporary =
            DocsTemporaryDirectory::create("links-apply").expect("temporary docs root is created");
        let root = temporary
            .0
            .canonicalize()
            .expect("temporary docs root is canonical");
        write_link_fixture(&root, "README.md", "# Root\n");
        let guide = write_link_fixture(&root, "docs/guide.md", "[root](README.md#top)\n");
        let untouched = write_link_fixture(&root, "docs/untouched.md", "# Untouched\n");
        let capability = r#"{"allowed_paths":["docs/guide.md"],"purpose":"link-repair","authority":"issue-1630"}"#;

        assert_eq!(
            run_link_audit(
                &root,
                &["docs/guide.md".to_string()],
                true,
                false,
                Some(capability)
            ),
            0
        );
        assert_eq!(
            fs::read_to_string(&guide).expect("guide is readable"),
            "[root](../README.md#top)\n"
        );
        assert_eq!(
            fs::read_to_string(&untouched).expect("untouched source is readable"),
            "# Untouched\n"
        );
        assert!(!root.join("reports").exists());
    }

    #[test]
    fn links_apply_preflights_all_rewrites_before_writing_any_source() {
        let temporary = DocsTemporaryDirectory::create("links-preflight")
            .expect("temporary docs root is created");
        let root = temporary
            .0
            .canonicalize()
            .expect("temporary docs root is canonical");
        write_link_fixture(&root, "README.md", "# Root\n");
        let allowed = write_link_fixture(&root, "docs/guide.md", "[root](README.md)\n");
        let denied = write_link_fixture(&root, "docs/other.md", "[root](README.md)\n");
        let before_allowed = fs::read(&allowed).expect("allowed file bytes are captured");
        let before_denied = fs::read(&denied).expect("denied file bytes are captured");
        let capability = r#"{"allowed_paths":["docs/guide.md"],"purpose":"link-repair","authority":"issue-1630"}"#;

        assert_eq!(
            run_link_audit(&root, &["docs".to_string()], true, false, Some(capability)),
            2
        );
        assert_eq!(
            fs::read(&allowed).expect("allowed file remains readable"),
            before_allowed
        );
        assert_eq!(
            fs::read(&denied).expect("denied file remains readable"),
            before_denied
        );
    }

    #[test]
    fn link_rewrite_plans_unique_filename_targets_and_preserves_ambiguous_or_external_links() {
        let temporary = DocsTemporaryDirectory::create("links-name-index")
            .expect("temporary docs root is created");
        let root = temporary
            .0
            .canonicalize()
            .expect("temporary docs root is canonical");
        let source = write_link_fixture(
            &root,
            "docs/guide.md",
            "[unique](topic.md#part)\n[ambiguous](same.md)\n[external](https://example.test/x)\n",
        );
        write_link_fixture(&root, "one/topic.md", "# Topic\n");
        write_link_fixture(&root, "one/same.md", "# One\n");
        write_link_fixture(&root, "two/same.md", "# Two\n");
        let expected = "[unique](../one/topic.md#part)\n[ambiguous](same.md)\n[external](https://example.test/x)\n";

        let planned = planned_link_rewrites(&root, &["docs/guide.md".to_string()])
            .expect("link rewrite plan is read-only");

        assert_eq!(planned.get(&source), Some(&expected.to_string()));
        assert_eq!(
            fs::read_to_string(&source).expect("source remains unchanged during planning"),
            "[unique](topic.md#part)\n[ambiguous](same.md)\n[external](https://example.test/x)\n"
        );
    }

    #[cfg(unix)]
    #[test]
    fn link_rewrite_preserves_literal_backslash_path_components() {
        let temporary = DocsTemporaryDirectory::create("links-backslash-component")
            .expect("temporary docs root is created");
        let root = temporary
            .0
            .canonicalize()
            .expect("temporary docs root is canonical");
        let target = root.join("docs\\x/guide.md");
        fs::create_dir_all(target.parent().expect("target has a parent"))
            .expect("literal-backslash directory is created");
        fs::write(&target, "# Guide\n").expect("target is written");
        let source = write_link_fixture(
            &root,
            "index.md",
            &format!("[guide]({})\n", target.display()),
        );

        let planned = planned_link_rewrites(&root, &["index.md".to_string()])
            .expect("link rewrite planning succeeds");

        assert_eq!(
            planned.get(&source).map(String::as_str),
            Some("[guide](docs\\x/guide.md)\n")
        );
        assert_eq!(
            fs::read_to_string(&source).expect("planning does not mutate source"),
            format!("[guide]({})\n", target.display())
        );
    }
}
