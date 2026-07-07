// @dependency-start
// contract implementation
// responsibility Provides unified Rust Markdown documentation formatting and checks.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// upstream design ../../../agents/skills/md-style-check.md Markdown style check skill contract
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// downstream implementation ../../../tools/ci/run_docs_checks.sh forwards legacy docs-check calls
// @dependency-end

use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const DEFAULT_DOC_TARGETS: &[&str] = &[
    "README.md",
    "QUICK_START.md",
    "AGENTS.md",
    "agents",
    "docker",
    "documents",
    "scripts",
    ".github",
    ".agents/skills",
    ".codex/README.md",
];

const BOOTSTRAP_DOCS: &[&str] = &[
    "README.md",
    "QUICK_START.md",
    "docker/README.md",
    "scripts/README.md",
    "documents/template-bootstrap.md",
    "documents/linux-wsl-host-requirements.md",
];

const DERIVED_REPO_STALE_STRINGS: &[&str] = &[
    "Project Template",
    "project-template",
    "/mnt/l/workspace/project_template/",
];

const SKIP_PARTS: &[&str] = &[".git", ".worktrees", "__pycache__", "Archive", "target"];

const MERMAID_LANGS: &[&str] = &["mermaid", "mermeid"];
const MERMAID_RESERVED_NODE_IDS: &[&str] = &[
    "class",
    "classdef",
    "click",
    "direction",
    "end",
    "flowchart",
    "graph",
    "linkstyle",
    "style",
    "subgraph",
];
const MERMAID_DIRECTIVES: &[&str] = &[
    "flowchart",
    "graph",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "statediagram-v2",
    "erdiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
];
const FLOW_DIRECTIONS: &[&str] = &["bt", "lr", "rl", "tb", "td"];

const RUNTIME_PROFILE_DEPENDENCY_HEADER: &str = "<!--
@dependency-start
contract reference
responsibility Defines AgentCanon runtime profiles and risk-based validation routing.
upstream design ../ROOT_AGENTS.md root runtime entrypoint and closeout model
upstream design ./SHARED_RUNTIME_SURFACES.md shared runtime surface ownership policy
downstream design ../agents/canonical/CODEX_WORKFLOW.md Codex execution workflow
downstream design ./agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
downstream implementation ../tools/ci/run_all_checks.sh repo check runner
downstream implementation ../tools/catalog.yaml structured tool catalog
@dependency-end
-->
";

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    command: DocsCommand,
    root: PathBuf,
    paths: Vec<String>,
    output_format: OutputFormat,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DocsCommand {
    Check,
    Format,
    FixMath,
    FixMermaid,
    RenderRuntimeProfile,
    Help,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Finding {
    check: &'static str,
    path: Option<PathBuf>,
    line: Option<usize>,
    message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct WriteSummary {
    action: &'static str,
    changed_files: usize,
    changes: usize,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => run_parsed(parsed),
        Err(message) => {
            render_tool_error("DOCS_TOOL", "invalid-arguments", &message);
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
        DocsCommand::Check => render_check(&root, &args.paths, &args.output_format),
        DocsCommand::Format => render_write_then_check(
            &root,
            &args.paths,
            &args.output_format,
            "format",
            format_markdown_files,
        ),
        DocsCommand::FixMath => render_write_then_check(
            &root,
            &args.paths,
            &args.output_format,
            "fix-math",
            fix_math_files,
        ),
        DocsCommand::FixMermaid => render_write_then_check(
            &root,
            &args.paths,
            &args.output_format,
            "fix-mermaid",
            fix_mermaid_files,
        ),
        DocsCommand::RenderRuntimeProfile => render_runtime_profile_command(&root),
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let command = match args.first().map(|item| item.as_str()) {
            Some("check") => DocsCommand::Check,
            Some("format") => DocsCommand::Format,
            Some("fix-math") => DocsCommand::FixMath,
            Some("fix-mermaid") => DocsCommand::FixMermaid,
            Some("render-runtime-profile") => DocsCommand::RenderRuntimeProfile,
            Some("help") | Some("--help") | Some("-h") => DocsCommand::Help,
            Some(other) => return Err(format!("unknown docs command {other}")),
            None => return Err("missing docs command".to_string()),
        };

        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
        let mut output_format = OutputFormat::Text;
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
                "--format" => {
                    let value = args
                        .get(index + 1)
                        .ok_or_else(|| "--format requires a value".to_string())?;
                    output_format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => return Err(format!("unknown --format value {value}")),
                    };
                    index += 2;
                }
                "--help" | "-h" => {
                    return Ok(Self {
                        command: DocsCommand::Help,
                        root,
                        paths,
                        output_format,
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
            output_format,
        })
    }
}

fn usage_text() -> &'static str {
    "usage: agent-canon docs <command> [options] [paths...]\n\
\n\
commands:\n\
  check                   check Markdown lint, links, math, Mermaid, headings, and runtime-profile docs\n\
  format                  format Markdown, then run the adjacent docs check\n\
  fix-math                normalize Markdown math notation, then run the adjacent docs check\n\
  fix-mermaid             normalize Mermaid fenced blocks and node labels, then run the adjacent docs check\n\
  render-runtime-profile  render the runtime profile inventory\n\
  help, -h, --help        show this command contract\n\
\n\
options:\n\
  --root <repo-root>      repository root to evaluate; defaults to the current directory\n\
  --format text|json      output format for check results; defaults to text\n\
\n\
examples:\n\
  tools/bin/agent-canon docs -h\n\
  tools/bin/agent-canon docs check documents/tools/agent-canon.md\n\
  tools/bin/agent-canon docs format README.md"
}

fn print_usage() {
    eprintln!("{}", usage_text());
}

fn render_runtime_profile_command(root: &Path) -> i32 {
    match render_runtime_profile_inventory(
        &root.join("documents/runtime-profiles-and-check-matrix.json"),
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

fn render_check(root: &Path, raw_paths: &[String], output_format: &OutputFormat) -> i32 {
    let findings = collect_check_findings(root, raw_paths);
    render_findings(&findings, root, output_format)
}

fn render_write_then_check(
    root: &Path,
    raw_paths: &[String],
    output_format: &OutputFormat,
    action: &'static str,
    writer: fn(&Path, &[String]) -> io::Result<WriteSummary>,
) -> i32 {
    let summary = match writer(root, raw_paths) {
        Ok(summary) => summary,
        Err(error) => {
            let report_name = format!("DOCS_{}", action.to_ascii_uppercase().replace('-', "_"));
            render_tool_error(&report_name, "write-error", &error.to_string());
            return 1;
        }
    };
    match output_format {
        OutputFormat::Text => {
            println!(
                "DOCS_{}=wrote changed_files={} changes={}",
                summary.action.to_ascii_uppercase().replace('-', "_"),
                summary.changed_files,
                summary.changes
            );
        }
        OutputFormat::Json => {
            println!(
                "{{\"action\":\"{}\",\"changed_files\":{},\"changes\":{}}}",
                json_escape(summary.action),
                summary.changed_files,
                summary.changes
            );
        }
    }
    let findings = collect_check_findings(root, raw_paths);
    render_findings(&findings, root, output_format)
}

fn render_findings(findings: &[Finding], root: &Path, output_format: &OutputFormat) -> i32 {
    match output_format {
        OutputFormat::Text => {
            if findings.is_empty() {
                println!("DOCS_CHECK=pass");
                return 0;
            }
            eprintln!("DOCS_CHECK=fail");
            for finding in findings {
                let path = finding
                    .path
                    .as_ref()
                    .map(|path| display_path(root, path))
                    .unwrap_or_else(|| "-".to_string());
                let line = finding
                    .line
                    .map(|line| line.to_string())
                    .unwrap_or_else(|| "-".to_string());
                eprintln!(
                    "DOCS_CHECK_FINDING={}:{}:{}:{}",
                    finding.check, path, line, finding.message
                );
            }
            eprint!("{}", structured_findings_report(findings, root));
        }
        OutputFormat::Json => {
            let mut output = String::from("{\"status\":\"");
            output.push_str(if findings.is_empty() { "pass" } else { "fail" });
            output.push_str("\",\"findings\":[");
            for (index, finding) in findings.iter().enumerate() {
                if index > 0 {
                    output.push(',');
                }
                output.push_str("{\"check\":\"");
                output.push_str(&json_escape(finding.check));
                output.push_str("\",\"path\":");
                if let Some(path) = &finding.path {
                    output.push('"');
                    output.push_str(&json_escape(&display_path(root, path)));
                    output.push('"');
                } else {
                    output.push_str("null");
                }
                output.push_str(",\"line\":");
                if let Some(line) = finding.line {
                    output.push_str(&line.to_string());
                } else {
                    output.push_str("null");
                }
                output.push_str(",\"message\":\"");
                output.push_str(&json_escape(&finding.message));
                output.push_str("\"}");
            }
            output.push_str("]}");
            println!("{output}");
        }
    }
    if findings.is_empty() {
        0
    } else {
        1
    }
}

fn render_tool_error(report_name: &str, kind: &str, detail: &str) {
    eprintln!("{report_name}=fail");
    eprintln!("DOCS_TOOL_FINDING={kind}:{detail}");
    eprintln!("DOCS_TOOL_REPORT_BEGIN");
    eprintln!("status: fail");
    eprintln!("summary: AgentCanon docs tool failed before completing the requested operation.");
    eprintln!("findings:");
    eprintln!("- kind: {kind}");
    eprintln!("  detail: {detail}");
    eprintln!("next_action:");
    eprintln!("- Use the machine-readable finding above as the repair target.");
    eprintln!("- Run `tools/bin/agent-canon docs -h` for the command contract and option list.");
    eprintln!("- Do not inspect implementation files unless this report lacks the needed contract detail.");
    eprintln!("DOCS_TOOL_REPORT_END");
}

fn structured_findings_report(findings: &[Finding], root: &Path) -> String {
    let mut report = String::new();
    report.push_str("DOCS_CHECK_REPORT_BEGIN\n");
    report.push_str("status: fail\n");
    report.push_str(&format!(
        "summary: Documentation checks found {} issue(s). Use these locations before reading broader files.\n",
        findings.len()
    ));
    report.push_str("findings:\n");
    for finding in findings {
        let path = finding
            .path
            .as_ref()
            .map(|path| display_path(root, path))
            .unwrap_or_else(|| "-".to_string());
        let line = finding
            .line
            .map(|line| line.to_string())
            .unwrap_or_else(|| "-".to_string());
        report.push_str(&format!("- check: {}\n", finding.check));
        report.push_str(&format!("  location: {path}:{line}\n"));
        report.push_str(&format!("  problem: {}\n", finding.message));
    }
    report.push_str("next_action:\n");
    report.push_str("- Open only the reported location and nearby lines needed for the repair.\n");
    report.push_str("- Prefer `tools/bin/agent-canon docs format`, `fix-math`, or `fix-mermaid` when the finding is mechanical.\n");
    report.push_str("- Rerun `tools/bin/agent-canon docs check <paths...>` after the repair.\n");
    report.push_str("DOCS_CHECK_REPORT_END\n");
    report
}

fn collect_check_findings(root: &Path, raw_paths: &[String]) -> Vec<Finding> {
    let mut findings = Vec::new();
    let markdown_files = collect_markdown_files(root, raw_paths);
    findings.extend(check_markdown_lint(&markdown_files));
    findings.extend(check_markdown_math(&markdown_files));
    findings.extend(check_markdown_links(root, &markdown_files));
    findings.extend(check_bootstrap_docs(root));
    findings.extend(check_runtime_profile_inventory(root));
    findings
}

fn format_markdown_files(root: &Path, raw_paths: &[String]) -> io::Result<WriteSummary> {
    rewrite_markdown_files(root, raw_paths, "format", |text| {
        let text = text.replace("\r\n", "\n").replace('\r', "\n");
        let (text, mermaid_changes) = fix_mermaid_markdown(&text);
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
        (formatted, mermaid_changes + extra_changes)
    })
}

fn fix_math_files(root: &Path, raw_paths: &[String]) -> io::Result<WriteSummary> {
    rewrite_markdown_files(root, raw_paths, "fix-math", fix_markdown_math)
}

fn fix_mermaid_files(root: &Path, raw_paths: &[String]) -> io::Result<WriteSummary> {
    rewrite_markdown_files(root, raw_paths, "fix-mermaid", fix_mermaid_markdown)
}

fn rewrite_markdown_files(
    root: &Path,
    raw_paths: &[String],
    action: &'static str,
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
        println!("DOCS_WRITE_FILE={}", display_path(root, &path));
    }
    Ok(WriteSummary {
        action,
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

fn check_markdown_lint(files: &[PathBuf]) -> Vec<Finding> {
    let mut findings = Vec::new();
    for path in files {
        let Ok(text) = fs::read_to_string(path) else {
            findings.push(Finding {
                check: "markdown-lint",
                path: Some(path.clone()),
                line: None,
                message: "file is not readable as UTF-8".to_string(),
            });
            continue;
        };
        findings.extend(check_heading_increment(path, &text));
        findings.extend(check_trailing_spaces(path, &text));
        findings.extend(check_hard_tabs(path, &text));
        findings.extend(check_list_spacing(path, &text));
        findings.extend(check_list_marker_consistency(path, &text));
        findings.extend(check_fenced_code_language(path, &text));
    }
    findings
}

fn check_heading_increment(path: &Path, text: &str) -> Vec<Finding> {
    let mut findings = Vec::new();
    let mut previous = 0usize;
    for (line_index, line) in text.lines().enumerate() {
        let Some(level) = heading_level(line) else {
            continue;
        };
        if previous != 0 && level > previous + 1 {
            findings.push(Finding {
                check: "markdown-lint",
                path: Some(path.to_path_buf()),
                line: Some(line_index + 1),
                message: format!("MD001 header jump from H{previous} to H{level}"),
            });
        }
        previous = level;
    }
    findings
}

fn heading_level(line: &str) -> Option<usize> {
    let bytes = line.as_bytes();
    let mut count = 0usize;
    while count < bytes.len() && bytes[count] == b'#' {
        count += 1;
    }
    if count > 0 && bytes.get(count) == Some(&b' ') {
        Some(count)
    } else {
        None
    }
}

fn check_trailing_spaces(path: &Path, text: &str) -> Vec<Finding> {
    text.lines()
        .enumerate()
        .filter(|(_, line)| line.trim_end() != *line)
        .map(|(index, _)| Finding {
            check: "markdown-lint",
            path: Some(path.to_path_buf()),
            line: Some(index + 1),
            message: "MD009 trailing spaces".to_string(),
        })
        .collect()
}

fn check_hard_tabs(path: &Path, text: &str) -> Vec<Finding> {
    text.lines()
        .enumerate()
        .filter(|(_, line)| line.contains('\t'))
        .map(|(index, _)| Finding {
            check: "markdown-lint",
            path: Some(path.to_path_buf()),
            line: Some(index + 1),
            message: "MD010 hard tab".to_string(),
        })
        .collect()
}

fn check_list_spacing(path: &Path, text: &str) -> Vec<Finding> {
    let mut findings = Vec::new();
    for (line_index, line) in text.lines().enumerate() {
        let trimmed = line.trim_start_matches(' ');
        let indent = line.len() - trimmed.len();
        let Some(marker_len) =
            unordered_marker_len(trimmed).or_else(|| ordered_marker_len(trimmed))
        else {
            continue;
        };
        let after_marker = &trimmed[marker_len..];
        let spaces = after_marker.chars().take_while(|ch| *ch == ' ').count();
        if spaces != 1 && after_marker.chars().any(|ch| !ch.is_whitespace()) {
            findings.push(Finding {
                check: "markdown-lint",
                path: Some(path.to_path_buf()),
                line: Some(line_index + 1),
                message: format!(
                    "MD030 list marker spacing at indent {indent}: expected 1, got {spaces}"
                ),
            });
        }
    }
    findings
}

fn check_list_marker_consistency(path: &Path, text: &str) -> Vec<Finding> {
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
            check: "markdown-lint",
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

fn unordered_marker_len(line: &str) -> Option<usize> {
    unordered_marker(line).map(|marker| marker.len_utf8())
}

fn ordered_marker_len(line: &str) -> Option<usize> {
    let mut dot_index = None;
    for (index, ch) in line.char_indices() {
        if ch == '.' {
            dot_index = Some(index);
            break;
        }
        if !ch.is_ascii_digit() {
            return None;
        }
    }
    let dot_index = dot_index?;
    if dot_index == 0 {
        return None;
    }
    if line.as_bytes().get(dot_index + 1) == Some(&b' ') {
        Some(dot_index + 1)
    } else {
        None
    }
}

fn check_fenced_code_language(path: &Path, text: &str) -> Vec<Finding> {
    let mut findings = Vec::new();
    let mut fence: Option<(char, usize)> = None;
    for (line_index, line) in text.lines().enumerate() {
        let stripped = line.trim_end();
        if let Some((fence_char, fence_len)) = fence {
            if is_closing_fence(stripped, fence_char, fence_len) {
                fence = None;
            }
            continue;
        }
        let Some((fence_char, fence_len, info)) = opening_fence_info(stripped) else {
            continue;
        };
        if info.trim().is_empty() {
            findings.push(Finding {
                check: "markdown-lint",
                path: Some(path.to_path_buf()),
                line: Some(line_index + 1),
                message: "MD040 fenced code block should specify language".to_string(),
            });
        }
        fence = Some((fence_char, fence_len));
    }
    findings
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

fn check_markdown_math(files: &[PathBuf]) -> Vec<Finding> {
    let mut findings = Vec::new();
    for path in files {
        let Ok(text) = fs::read_to_string(path) else {
            continue;
        };
        let mut in_fence = false;
        let mut in_display_block = false;
        for (line_index, line) in text.lines().enumerate() {
            if line.trim_start().starts_with("```") {
                in_fence = !in_fence;
                continue;
            }
            if in_fence {
                continue;
            }
            let line_no = line_index + 1;
            if line.contains("\\(") || line.contains("\\)") {
                findings.push(math_finding(
                    path,
                    line_no,
                    "inline math must use `$...$`, not `\\(...\\)`",
                ));
            }
            if line.contains("\\[") || line.contains("\\]") {
                findings.push(math_finding(
                    path,
                    line_no,
                    "display math must use `$$...$$`, not `\\[...\\]`",
                ));
            }
            let compact = line.trim();
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
            if line.contains("$$") {
                findings.push(math_finding(
                    path,
                    line_no,
                    "inline math must use `$...$`, not `$$...$$`",
                ));
            }
        }
    }
    findings
}

fn math_finding(path: &Path, line_no: usize, message: &str) -> Finding {
    Finding {
        check: "markdown-math",
        path: Some(path.to_path_buf()),
        line: Some(line_no),
        message: message.to_string(),
    }
}

fn check_markdown_links(root: &Path, files: &[PathBuf]) -> Vec<Finding> {
    let mut findings = Vec::new();
    let name_index = build_name_index(root);
    for path in files {
        let Ok(text) = fs::read_to_string(path) else {
            continue;
        };
        for (target, line_no) in markdown_link_targets(&text) {
            if is_external_target(&target) {
                continue;
            }
            let (target_path, _) = split_anchor(&target);
            if target_path.is_empty() {
                continue;
            }
            if let Some(resolved) = resolve_local_target(path, root, target_path) {
                if workspace_absolute_target(root, target_path, &resolved) {
                    findings.push(Finding {
                        check: "markdown-links",
                        path: Some(path.to_path_buf()),
                        line: Some(line_no),
                        message: format!(
                            "workspace-absolute markdown link should be relative: {target}"
                        ),
                    });
                }
                continue;
            }
            let candidates = Path::new(target_path)
                .file_name()
                .and_then(|name| name.to_str())
                .and_then(|name| name_index.get(name))
                .cloned()
                .unwrap_or_default();
            let message = if candidates.len() == 1 {
                format!(
                    "local markdown link target is missing; unique candidate exists: {}",
                    display_path(root, &candidates[0])
                )
            } else if candidates.is_empty() {
                format!("local markdown link target is missing: {target}")
            } else {
                format!(
                    "local markdown link target is missing with {} filename candidates: {target}",
                    candidates.len()
                )
            };
            findings.push(Finding {
                check: "markdown-links",
                path: Some(path.to_path_buf()),
                line: Some(line_no),
                message,
            });
        }
    }
    findings
}

fn workspace_absolute_target(root: &Path, target_path: &str, resolved: &Path) -> bool {
    let raw = Path::new(target_path);
    if !raw.is_absolute() {
        return false;
    }
    resolved.starts_with(root) || map_absolute_workspace_path(root, raw).is_some()
}

fn markdown_link_targets(text: &str) -> Vec<(String, usize)> {
    let mut result = Vec::new();
    for (line_index, line) in text.lines().enumerate() {
        let bytes = line.as_bytes();
        let mut index = 0usize;
        while index < bytes.len() {
            if bytes[index] != b'[' {
                index += 1;
                continue;
            }
            let Some(label_end) = line[index + 1..].find(']').map(|offset| index + 1 + offset)
            else {
                index += 1;
                continue;
            };
            if bytes.get(label_end + 1) != Some(&b'(') {
                index = label_end + 1;
                continue;
            }
            let target_start = label_end + 2;
            let Some(target_end) = line[target_start..]
                .find(')')
                .map(|offset| target_start + offset)
            else {
                index = target_start;
                continue;
            };
            result.push((line[target_start..target_end].to_string(), line_index + 1));
            index = target_end + 1;
        }
    }
    result
}

fn is_external_target(target: &str) -> bool {
    let lowercase = target.to_ascii_lowercase();
    lowercase.starts_with("mailto:")
        || target.starts_with('#')
        || lowercase.starts_with("http://")
        || lowercase.starts_with("https://")
        || lowercase.starts_with("file://")
}

fn split_anchor(target: &str) -> (&str, &str) {
    target.split_once('#').unwrap_or((target, ""))
}

fn resolve_local_target(source_path: &Path, root: &Path, target_path: &str) -> Option<PathBuf> {
    let raw = PathBuf::from(target_path);
    if raw.is_absolute() {
        if raw.exists() {
            return Some(raw);
        }
        if let Some(mapped) = map_absolute_workspace_path(root, &raw) {
            if mapped.exists() {
                return Some(mapped);
            }
        }
        return None;
    }
    let candidate = source_path.parent()?.join(raw);
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
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

fn build_name_index(root: &Path) -> BTreeMap<String, Vec<PathBuf>> {
    let mut index = BTreeMap::new();
    collect_name_index(root, &mut index);
    index
}

fn collect_name_index(path: &Path, index: &mut BTreeMap<String, Vec<PathBuf>>) {
    if skip_path(path) {
        return;
    }
    if path.is_dir() {
        if let Ok(entries) = fs::read_dir(path) {
            for entry in entries.flatten() {
                collect_name_index(&entry.path(), index);
            }
        }
        return;
    }
    if path.is_file() {
        if let Some(name) = path.file_name().and_then(|name| name.to_str()) {
            index
                .entry(name.to_string())
                .or_default()
                .push(path.to_path_buf());
        }
    }
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
        let skip_stale = *relative == "documents/template-bootstrap.md"
            && path.is_symlink()
            && path
                .canonicalize()
                .map(|resolved| {
                    let text = resolved.to_string_lossy();
                    text.contains("/vendor/") && text.contains("/agent-canon/")
                })
                .unwrap_or(false);
        let Ok(text) = fs::read_to_string(&path) else {
            continue;
        };
        for (line_index, line) in text.lines().enumerate() {
            if line.contains("](/mnt/l/workspace/") {
                findings.push(Finding {
                    check: "bootstrap-docs",
                    path: Some(path.clone()),
                    line: Some(line_index + 1),
                    message: "replace workspace-absolute markdown links with relative links"
                        .to_string(),
                });
            }
            if !check_stale || skip_stale {
                continue;
            }
            for stale in DERIVED_REPO_STALE_STRINGS {
                if line.contains(stale) {
                    findings.push(Finding {
                        check: "bootstrap-docs",
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
    let inventory_path = root.join("documents/runtime-profiles-and-check-matrix.json");
    let doc_path = root.join("documents/runtime-profiles-and-check-matrix.md");
    if !inventory_path.is_file() || !doc_path.is_file() {
        return Vec::new();
    }
    let rendered = match render_runtime_profile_inventory(&inventory_path) {
        Ok(rendered) => rendered,
        Err(message) => {
            return vec![Finding {
                check: "runtime-profile-inventory",
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
            check: "runtime-profile-inventory",
            path: Some(doc_path),
            line: None,
            message:
                "runtime profile inventory markdown drifts from documents/runtime-profiles-and-check-matrix.json"
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
        let profile = required_string(item.get("profile"), "profile_classes.profile")?;
        let activates = required_string_array(item.get("activates"), "profile_classes.activates")?;
        let required_when =
            required_string(item.get("required_when"), "profile_classes.required_when")?;
        profile_rows.push(vec![profile, activates.join(", "), required_when]);
    }
    output.push_str(&render_table(
        &["Profile", "Activates", "Required when"],
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

fn fix_mermaid_markdown(content: &str) -> (String, usize) {
    let lines: Vec<&str> = content.lines().collect();
    let mut output = Vec::new();
    let mut changes = 0usize;
    let mut index = 0usize;
    while index < lines.len() {
        let line = lines[index];
        let Some((indent, fence_marker, language, suffix)) = opening_mermaid_fence(line) else {
            output.push(line.to_string());
            index += 1;
            continue;
        };
        if language != "mermaid" {
            changes += 1;
        }
        output.push(format!("{indent}{fence_marker}mermaid{suffix}"));
        index += 1;
        let block_start = output.len();
        while index < lines.len() && !closing_mermaid_fence(lines[index], &fence_marker) {
            output.push(lines[index].to_string());
            index += 1;
        }
        let block = output.split_off(block_start);
        let (fixed_block, block_changes) = fix_mermaid_block(&block);
        changes += block_changes;
        output.extend(fixed_block);
        if index < lines.len() {
            output.push(lines[index].to_string());
            index += 1;
        }
    }
    let mut fixed = output.join("\n");
    if content.ends_with('\n') {
        fixed.push('\n');
    }
    (fixed, changes)
}

fn opening_mermaid_fence(line: &str) -> Option<(String, String, String, String)> {
    let indent_len = line.len() - line.trim_start().len();
    let indent = line[..indent_len].to_string();
    let trimmed = line.trim_start();
    let fence_char = trimmed.chars().next()?;
    if !matches!(fence_char, '`' | '~') {
        return None;
    }
    let fence_len = trimmed.chars().take_while(|ch| *ch == fence_char).count();
    if fence_len < 3 {
        return None;
    }
    let info = trimmed[fence_len..].trim();
    let mut parts = info.splitn(2, char::is_whitespace);
    let language = parts.next()?.to_ascii_lowercase();
    if !MERMAID_LANGS.contains(&language.as_str()) {
        return None;
    }
    let suffix = parts
        .next()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| format!(" {value}"))
        .unwrap_or_default();
    Some((
        indent,
        fence_char.to_string().repeat(fence_len),
        language,
        suffix,
    ))
}

fn closing_mermaid_fence(line: &str, opening_marker: &str) -> bool {
    is_closing_fence(
        line,
        opening_marker.chars().next().unwrap_or('`'),
        opening_marker.len(),
    )
}

fn fix_mermaid_block(lines: &[String]) -> (Vec<String>, usize) {
    let rename_map = reserved_node_rename_map(lines);
    if rename_map.is_empty() {
        return (lines.to_vec(), 0);
    }
    let mut changes = 0usize;
    let fixed = lines
        .iter()
        .map(|line| {
            let updated = rewrite_mermaid_line(line, &rename_map);
            if updated != *line {
                changes += 1;
            }
            updated
        })
        .collect();
    (fixed, changes)
}

fn reserved_node_rename_map(lines: &[String]) -> BTreeMap<String, String> {
    let mut result = BTreeMap::new();
    for line in lines {
        for reserved in MERMAID_RESERVED_NODE_IDS {
            if mermaid_node_id_used(line, reserved) {
                let replacement = if *reserved == "graph" {
                    "graph_node".to_string()
                } else {
                    format!("{reserved}_node")
                };
                result.insert((*reserved).to_string(), replacement);
            }
        }
    }
    result
}

fn mermaid_node_id_used(line: &str, node_id: &str) -> bool {
    let stripped = line.trim();
    if stripped.is_empty() || stripped.starts_with("%%") {
        return false;
    }
    let first = stripped
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    if MERMAID_DIRECTIVES.contains(&first.as_str()) {
        if matches!(first.as_str(), "flowchart" | "graph") {
            let remainder = stripped[first.len()..].trim();
            if remainder
                .split_whitespace()
                .next()
                .map(|value| FLOW_DIRECTIONS.contains(&value.to_ascii_lowercase().as_str()))
                .unwrap_or(false)
            {
                return false;
            }
        }
        if first == node_id {
            return false;
        }
    }
    contains_node_before_shape(line, node_id) || contains_node_after_edge(line, node_id)
}

fn contains_node_before_shape(line: &str, node_id: &str) -> bool {
    for marker in ["[", "(", "{"] {
        if line.contains(&format!("{node_id}{marker}")) {
            return true;
        }
    }
    false
}

fn contains_node_after_edge(line: &str, node_id: &str) -> bool {
    let edges = [
        "-->", "---", "==>", "~~~", "~~", "o--", "x--", "-.->", "-.-",
    ];
    edges.iter().any(|edge| {
        line.contains(&format!("{edge} {node_id}"))
            || line.contains(&format!("{edge}|"))
                && line
                    .split('|')
                    .next_back()
                    .map(|tail| tail.trim_start().starts_with(node_id))
                    .unwrap_or(false)
    })
}

fn rewrite_mermaid_line(line: &str, rename_map: &BTreeMap<String, String>) -> String {
    let mut output = line.to_string();
    for (old, new) in rename_map.iter().rev() {
        output = replace_mermaid_token(&output, old, new);
    }
    output
}

fn replace_mermaid_token(line: &str, old: &str, new: &str) -> String {
    let mut output = String::new();
    let mut index = 0usize;
    while index < line.len() {
        let rest = &line[index..];
        if rest.starts_with(old)
            && is_token_boundary(line, index, index + old.len())
            && mermaid_token_is_node_position(line, index, index + old.len())
        {
            output.push_str(new);
            index += old.len();
            continue;
        }
        let ch = rest.chars().next().expect("non-empty rest has char");
        output.push(ch);
        index += ch.len_utf8();
    }
    output
}

fn is_token_boundary(line: &str, start: usize, end: usize) -> bool {
    let before = line[..start].chars().next_back();
    let after = line[end..].chars().next();
    !before.map(is_token_char).unwrap_or(false) && !after.map(is_token_char).unwrap_or(false)
}

fn is_token_char(ch: char) -> bool {
    ch.is_ascii_alphanumeric() || ch == '_' || ch == '-'
}

fn mermaid_token_is_node_position(line: &str, start: usize, end: usize) -> bool {
    let after = line[end..].trim_start();
    if after.starts_with('[')
        || after.starts_with('(')
        || after.starts_with('{')
        || starts_mermaid_edge(after)
    {
        return true;
    }
    let before = line[..start].trim_end();
    if ends_with_mermaid_edge(before) {
        return true;
    }
    if let Some(pipe_index) = before.rfind('|') {
        return ends_with_mermaid_edge(before[..pipe_index].trim_end());
    }
    false
}

fn starts_mermaid_edge(value: &str) -> bool {
    [
        "-->", "---", "==>", "===", "-.->", "-.-", "~~~", "~~", "o--", "x--",
    ]
    .iter()
    .any(|edge| value.starts_with(edge))
}

fn ends_with_mermaid_edge(value: &str) -> bool {
    [
        "-->", "---", "==>", "===", "-.->", "-.-", "~~~", "~~", "o--", "x--",
    ]
    .iter()
    .any(|edge| value.ends_with(edge))
}

fn fix_markdown_math(content: &str) -> (String, usize) {
    let mut output = Vec::new();
    let mut changes = 0usize;
    let mut in_fence = false;
    let mut in_legacy_display = false;
    for line in content.lines() {
        let stripped = line.trim_start();
        if stripped.starts_with("```") {
            in_fence = !in_fence;
            output.push(line.to_string());
            continue;
        }
        if in_fence {
            output.push(line.to_string());
            continue;
        }
        if in_legacy_display {
            if line.trim() == "\\]" {
                output.push("$$".to_string());
                changes += 1;
                in_legacy_display = false;
            } else {
                output.push(line.to_string());
            }
            continue;
        }
        if line.trim() == "\\[" {
            output.push("$$".to_string());
            changes += 1;
            in_legacy_display = true;
            continue;
        }
        if line.trim().starts_with("\\[") && line.trim().ends_with("\\]") {
            let inner = line
                .trim()
                .trim_start_matches("\\[")
                .trim_end_matches("\\]")
                .trim();
            output.push(format!("$${inner}$$"));
            changes += 1;
            continue;
        }
        if line.trim() == "$" {
            output.push("$$".to_string());
            changes += 1;
            continue;
        }
        if line.trim().starts_with('$')
            && line.trim().ends_with('$')
            && !line.trim().starts_with("$$")
            && line.trim().len() > 2
        {
            let inner = line.trim().trim_matches('$').trim();
            output.push(format!("$${inner}$$"));
            changes += 1;
            continue;
        }
        let updated = replace_legacy_inline_math(line);
        if updated != line {
            changes += 1;
        }
        output.push(updated);
    }
    let mut fixed = output.join("\n");
    if content.ends_with('\n') {
        fixed.push('\n');
    }
    (fixed, changes)
}

fn replace_legacy_inline_math(line: &str) -> String {
    let mut output = String::new();
    let mut rest = line;
    while let Some(start) = rest.find("\\(") {
        output.push_str(&rest[..start]);
        let after_start = &rest[start + 2..];
        let Some(end) = after_start.find("\\)") else {
            output.push_str(&rest[start..]);
            return output;
        };
        output.push('$');
        output.push_str(&after_start[..end]);
        output.push('$');
        rest = &after_start[end + 2..];
    }
    output.push_str(rest);
    output
}

fn display_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

fn json_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_mermeid_fence_and_reserved_graph_node() {
        let source = "```mermeid\ngraph[SQLite graph]\ngraph --> class\n```\n";
        let (fixed, changes) = fix_mermaid_markdown(source);

        assert!(changes >= 2);
        assert!(fixed.contains("```mermaid"));
        assert!(fixed.contains("graph_node[SQLite graph]"));
        assert!(fixed.contains("graph_node --> class_node"));
    }

    #[test]
    fn fixes_legacy_math_notation() {
        let source = "\\(x\\)\n\\[\ny\n\\]\n$z$\n";
        let (fixed, changes) = fix_markdown_math(source);

        assert_eq!(changes, 4);
        assert_eq!(fixed, "$x$\n$$\ny\n$$\n$$z$$\n");
    }

    #[test]
    fn flags_workspace_absolute_markdown_links_even_when_target_exists() {
        let root =
            std::env::temp_dir().join(format!("agent-canon-docs-test-{}", std::process::id()));
        let docs = root.join("docs");
        fs::create_dir_all(&docs).expect("create docs dir");
        let target = docs.join("target.md");
        let source = docs.join("source.md");
        fs::write(&target, "# Target\n").expect("write target");
        fs::write(&source, format!("[Target]({})\n", target.display())).expect("write source");

        let findings = check_markdown_links(&root, std::slice::from_ref(&source));
        fs::remove_dir_all(&root).ok();

        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].check, "markdown-links");
        assert_eq!(findings[0].path.as_ref(), Some(&source));
        assert!(findings[0]
            .message
            .contains("workspace-absolute markdown link should be relative"));
    }

    #[test]
    fn structured_report_tells_agents_to_use_reported_location() {
        let root = PathBuf::from("/repo");
        let finding = Finding {
            check: "markdown-links",
            path: Some(root.join("docs/bad.md")),
            line: Some(3),
            message: "local markdown link target is missing: ./missing.md".to_string(),
        };

        let report = structured_findings_report(&[finding], &root);

        assert!(report.contains("DOCS_CHECK_REPORT_BEGIN"));
        assert!(report.contains("summary: Documentation checks found 1 issue(s)."));
        assert!(report.contains("location: docs/bad.md:3"));
        assert!(report.contains("Open only the reported location"));
        assert!(report.contains("DOCS_CHECK_REPORT_END"));
    }

    #[test]
    fn help_text_exposes_options_and_examples() {
        let usage = usage_text();

        assert!(usage.contains("usage: agent-canon docs <command> [options] [paths...]"));
        assert!(usage.contains("help, -h, --help"));
        assert!(usage.contains("--root <repo-root>"));
        assert!(usage.contains("--format text|json"));
        assert!(usage.contains("tools/bin/agent-canon docs -h"));
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
    fn renders_validation_failure_response_from_inventory() {
        let root = std::env::temp_dir().join(format!(
            "agent-canon-runtime-profile-test-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).expect("create temp dir");
        let inventory = root.join("inventory.json");
        fs::write(
            &inventory,
            r##"{
  "version": 1,
  "title": "Runtime Profiles And Check Matrix",
  "summary": ["summary"],
  "profile_classes": [
    {"profile": "Base project", "activates": ["`README.md`"], "required_when": "Every repo"}
  ],
  "compatibility_note": ["compat note"],
  "risk_classes": [
    {"risk": "Routine docs", "examples": "examples", "required_validation": "validation"}
  ],
  "risk_note": ["risk note"],
    "validation_failure_response": {
    "rule": [
      "After any validation test/check failure, preserve intended behavior.",
      "Record `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`."
    ],
    "required_fields": [
      "failing_contract",
      "observation_level",
      "cause_classification",
      "intent_preservation",
      "evidence"
    ],
    "cause_classes": [
      "implementation_bug",
      "stale_generated_artifact"
    ],
    "intent_preservation": [
      "repair_same_intent",
      "redesign_same_intent",
      "escalate_design_conflict"
    ],
    "repair_routes": [
      "repair_same_intent: repair implementation while preserving approved intent",
      "redesign_same_intent: return to design while preserving approved intent",
      "escalate_design_conflict: escalate before any intent change"
    ]
  },
  "check_matrix": [
    {"changed_surface": "Markdown docs only", "required_check": ["`tools/bin/agent-canon docs check`"]}
  ],
  "closeout_rule": ["closeout"]
}
"##,
        )
        .expect("write inventory");

        let rendered = render_runtime_profile_inventory(&inventory).expect("render inventory");
        fs::remove_dir_all(&root).ok();

        assert!(rendered.contains("## Validation Failure Response"));
        assert!(rendered.contains("`intent_preservation`"));
        assert!(rendered.contains("`stale_generated_artifact`"));
        assert!(rendered.contains(
            "repair_same_intent: repair implementation while preserving approved intent"
        ));
        assert!(rendered.find("## Risk Classes") < rendered.find("## Check Matrix"));
    }
}
