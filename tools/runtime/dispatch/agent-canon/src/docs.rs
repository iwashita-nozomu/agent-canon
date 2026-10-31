// @dependency-start
// contract implementation
// responsibility Composes native Markdown providers with AgentCanon-specific documentation and bootstrap checks.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md Rust tool migration policy
// upstream design ../../../../../agents/skills/md-style-check.md Markdown style check skill contract
// upstream design ../../../../../documents/runtime/runtime-profiles-and-check-matrix.json canonical runtime profile inventory rendered by this module
// downstream implementation entrypoint_owner_map.rs owns the root entrypoint grammar subcommand
// upstream design ../../../../../documents/contracts/template-bootstrap.md default bootstrap doc contract
// upstream design ../../../../../documents/contracts/static-seed-export.md source-free static-seed contract
// upstream implementation python_cli_integer.rs shares argparse negative-number classification
// downstream implementation ../../../../bin/agent-canon invokes this command through the CLI wrapper
// downstream implementation ../../../../../tests/tools/test_check_bootstrap_docs.py validates bootstrap and static-seed checks
// downstream implementation ../../../../../tests/agent_tools/test_export_static_seed.py invokes source-free validation on exported seeds
// downstream implementation ../../../../../tests/tools/test_fix_mermaid.py tests native Mermaid syntax validation
// @dependency-end

use regex::Regex;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering as AtomicOrdering};
use std::sync::OnceLock;
use toml_edit::{DocumentMut, Item, TableLike};

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

const BOOTSTRAP_DOCS: &[&str] = &[
    "README.md",
    "QUICK_START.md",
    "docker/README.md",
    "scripts/README.md",
    "documents/contracts/template-bootstrap.md",
    "documents/contracts/linux-wsl-host-requirements.md",
];

const DEFAULT_CONSUMER_CONTRACT_DOCS: &[&str] = &[
    "agents/skills/start-repository.md",
    "documents/contracts/template-bootstrap.md",
    "templates/README.md",
];

const DEFAULT_CONSUMER_FORBIDDEN_MARKERS: &[&str] = &[
    "vendor/agent-canon",
    "tools/agent-canon",
    "agent_canon_source_root",
    "agent-canon-update",
    "agent-canon-latest-check",
    "agent-canon-ensure-latest",
    "git submodule",
    ".gitmodules",
];

const DEFAULT_BOOTSTRAP_REQUIRED_MARKERS: &[&str] = &[
    "static seed",
    "agent-canon-static-seed.json",
    "regular file",
    "one-way",
];

const STATIC_SEED_FORBIDDEN_PATHS: &[&str] = &[
    ".agent-canon",
    ".gitmodules",
    "tools/agent-canon",
    "vendor/agent-canon",
];

const STATIC_SEED_FORBIDDEN_CONTENT: &[&[u8]] = &[
    b"agent_canon_source_root",
    b"agent-canon-latest-check",
    b"agent-canon-update",
    b"check_agent_canon_latest",
    b"checkout_agent_canon_submodule",
    b"from agent_tools",
    b"git submodule",
    b"http://",
    b"https://",
    b"import agent_tools",
    b"tools/agent-canon",
    b"vendor/agent-canon",
];

const STATIC_SEED_FORBIDDEN_PREFIXES: &[&[u8]] = &[
    b"agents/skills/",
    b"agents/model_profiles.toml",
    b"tools/agent_tools/",
    b"../../agents/",
    b"../../tools/",
];

const STATIC_SEED_PROVENANCE_PATH: &str = "agent-canon-static-seed.json";
const STATIC_SEED_SOURCE_REPOSITORY: &str = "iwashita-nozomu/agent-canon";

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
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DocsCommand {
    Check,
    Format,
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
    if args
        .first()
        .is_some_and(|argument| argument.as_str() == "check-entrypoints")
    {
        return crate::entrypoint_owner_map::run(&args[1..]);
    }
    if args
        .first()
        .is_some_and(|argument| argument.as_str() == "check-bootstrap")
    {
        return run_bootstrap_command(&args[1..]);
    }
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
        DocsCommand::RenderRuntimeProfile => render_runtime_profile_command(&root),
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let command = match args.first().map(|item| item.as_str()) {
            Some("check") => DocsCommand::Check,
            Some("format") => DocsCommand::Format,
            Some("render-runtime-profile") => DocsCommand::RenderRuntimeProfile,
            Some("help") | Some("--help") | Some("-h") => DocsCommand::Help,
            Some(other) => return Err(format!("unknown docs command {other}")),
            None => return Err("missing docs command".to_string()),
        };

        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
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
                "--help" | "-h" => {
                    return Ok(Self {
                        command: DocsCommand::Help,
                        root,
                        paths,
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
        })
    }
}

struct BootstrapArgs {
    root: PathBuf,
    static_seed_consumer: bool,
}

enum BootstrapParseResult {
    Help,
    Options(BootstrapArgs),
}

fn run_bootstrap_command(raw: &[String]) -> i32 {
    let args = match parse_bootstrap_args(raw) {
        Ok(BootstrapParseResult::Help) => {
            print_bootstrap_help();
            return 0;
        }
        Ok(BootstrapParseResult::Options(args)) => args,
        Err(error) => {
            eprintln!(
                "usage: agent-canon docs check-bootstrap [--root <path>] [--static-seed-consumer]"
            );
            eprintln!("agent-canon docs check-bootstrap: error: {error}");
            return 2;
        }
    };
    let root = fs::canonicalize(&args.root).unwrap_or_else(|_| {
        if args.root.is_absolute() {
            args.root.clone()
        } else {
            std::env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(&args.root)
        }
    });
    let (title, findings) = if args.static_seed_consumer {
        (
            "Static seed consumer check",
            iter_static_seed_consumer_findings(&root),
        )
    } else {
        match iter_bootstrap_doc_findings(&root) {
            Ok(findings) => ("Bootstrap docs check", findings),
            Err(error) => {
                eprintln!("agent-canon docs check-bootstrap: {error}");
                return 1;
            }
        }
    };
    print_bootstrap_findings(title, &findings)
}

fn parse_bootstrap_args(raw: &[String]) -> Result<BootstrapParseResult, String> {
    let mut args = BootstrapArgs {
        root: PathBuf::from("."),
        static_seed_consumer: false,
    };
    let mut index = 0;
    while index < raw.len() {
        let token = &raw[index];
        if matches!(token.as_str(), "-h" | "--help") {
            return Ok(BootstrapParseResult::Help);
        }
        if token == "--root" {
            args.root = PathBuf::from(required_bootstrap_value(raw, index, token)?);
            index += 2;
            continue;
        }
        if let Some(value) = token.strip_prefix("--root=") {
            args.root = PathBuf::from(value);
        } else if token == "--static-seed-consumer" {
            args.static_seed_consumer = true;
        } else if token == "--" {
            if index + 1 < raw.len() {
                return Err(format!(
                    "unrecognized arguments: {}",
                    raw[index + 1..].join(" ")
                ));
            }
        } else {
            return Err(format!("unrecognized arguments: {token}"));
        }
        index += 1;
    }
    Ok(BootstrapParseResult::Options(args))
}

fn required_bootstrap_value<'a>(
    raw: &'a [String],
    index: usize,
    option: &str,
) -> Result<&'a str, String> {
    raw.get(index + 1)
        .filter(|value| {
            !value.starts_with('-')
                || *value == "-"
                || crate::python_cli_integer::is_argparse_negative_number(value)
                || is_argparse_negative_float(value)
        })
        .map(String::as_str)
        .ok_or_else(|| format!("argument {option}: expected one argument"))
}

fn is_argparse_negative_float(value: &str) -> bool {
    static NEGATIVE_FLOAT: OnceLock<Regex> = OnceLock::new();
    NEGATIVE_FLOAT
        .get_or_init(|| Regex::new(r"^-\d*\.\d+$").expect("static negative float expression"))
        .is_match(value)
}

fn print_bootstrap_help() {
    println!(
        "Validate bootstrap docs or a source-free static-seed consumer.\n\n\
         usage: agent-canon docs check-bootstrap [--root <path>] [--static-seed-consumer]\n\n\
         options:\n\
           -h, --help             show this help message and exit\n\
           --root <path>          Repository or exported seed root. Defaults to cwd.\n\
           --static-seed-consumer validate only the source-free static-seed consumer surface."
    );
}

fn print_bootstrap_findings(title: &str, findings: &[String]) -> i32 {
    if findings.is_empty() {
        println!("{title} passed");
        0
    } else {
        println!("{title} failed:");
        for finding in findings {
            println!("- {finding}");
        }
        1
    }
}

fn iter_bootstrap_doc_findings(root: &Path) -> Result<Vec<String>, String> {
    let project_name = read_project_name(root)?;
    let check_derived_stale_strings = project_name
        .as_deref()
        .is_some_and(|name| name != "project-template");
    let default_consumer_docs = DEFAULT_CONSUMER_CONTRACT_DOCS
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let mut scan_paths = BOOTSTRAP_DOCS.to_vec();
    for relative in DEFAULT_CONSUMER_CONTRACT_DOCS.iter().copied() {
        if !scan_paths.contains(&relative) {
            scan_paths.push(relative);
        }
    }

    let mut findings = Vec::new();
    let mut template_bootstrap_text = None;
    for relative in scan_paths {
        let path = root.join(relative);
        if !path.exists() && !is_symlink(&path) {
            continue;
        }
        let is_default_consumer_doc = default_consumer_docs.contains(relative);
        if is_default_consumer_doc && is_symlink(&path) {
            findings.push(format!(
                "{relative}: default consumer contract must be a regular file, not a symlink"
            ));
        }
        if !path.is_file() {
            continue;
        }
        let text = fs::read_to_string(&path)
            .map_err(|error| format!("{relative}: cannot read UTF-8 document: {error}"))?;
        if relative == "documents/contracts/template-bootstrap.md" {
            template_bootstrap_text = Some(text.clone());
        }
        for (line_number, line) in python_split_lines(&text).into_iter().enumerate() {
            if absolute_workspace_link_pattern().is_match(line) {
                findings.push(format!(
                    "{relative}:{}: replace workspace-absolute markdown links with relative links",
                    line_number + 1
                ));
            }
            if check_derived_stale_strings {
                for stale in DERIVED_REPO_STALE_STRINGS {
                    if line.contains(stale) {
                        findings.push(format!(
                            "{relative}:{}: stale template bootstrap text remains: {stale}",
                            line_number + 1
                        ));
                    }
                }
            }
            if is_default_consumer_doc {
                let lowered = line.to_lowercase();
                for marker in DEFAULT_CONSUMER_FORBIDDEN_MARKERS {
                    if lowered.contains(marker) {
                        findings.push(format!(
                            "{relative}:{}: default consumer contract references live runtime marker: {marker}",
                            line_number + 1
                        ));
                    }
                }
            }
        }
    }

    if let Some(template_bootstrap_text) = template_bootstrap_text {
        let lowered = template_bootstrap_text.to_lowercase();
        for marker in DEFAULT_BOOTSTRAP_REQUIRED_MARKERS {
            if !lowered.contains(marker) {
                findings.push(format!(
                    "documents/contracts/template-bootstrap.md: missing static consumer marker: {marker}"
                ));
            }
        }
    }
    Ok(findings)
}

fn read_project_name(root: &Path) -> Result<Option<String>, String> {
    let path = root.join("pyproject.toml");
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    let document = text
        .parse::<DocumentMut>()
        .map_err(|error| format!("cannot parse {}: {error}", path.display()))?;
    let Some(project) = document.get("project").and_then(item_as_table_like) else {
        return Ok(None);
    };
    let Some(name) = project.get("name").and_then(Item::as_str) else {
        return Ok(None);
    };
    let name = name.trim();
    Ok((!name.is_empty()).then(|| name.to_owned()))
}

fn absolute_workspace_link_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| {
        Regex::new(r"\]\(/mnt/l/workspace/[^)]+\)")
            .expect("static absolute workspace link expression")
    })
}

fn python_split_lines(value: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = value.char_indices().peekable();
    while let Some((index, character)) = chars.next() {
        if !is_python_line_break(character) {
            continue;
        }
        lines.push(&value[start..index]);
        start = index + character.len_utf8();
        if character == '\r' && chars.peek().is_some_and(|(_, next)| *next == '\n') {
            let (newline_index, newline) = chars.next().expect("peeked newline exists");
            start = newline_index + newline.len_utf8();
        }
    }
    if start < value.len() {
        lines.push(&value[start..]);
    }
    lines
}

fn is_python_line_break(character: char) -> bool {
    matches!(
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
    )
}

fn is_symlink(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_symlink())
        .unwrap_or(false)
}

fn is_regular_file(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_file())
        .unwrap_or(false)
}

fn is_regular_directory(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_dir())
        .unwrap_or(false)
}

fn item_as_table_like(item: &Item) -> Option<&dyn TableLike> {
    item.as_table()
        .map(|table| table as &dyn TableLike)
        .or_else(|| item.as_inline_table().map(|table| table as &dyn TableLike))
}

fn usage_text() -> &'static str {
    "usage: agent-canon docs <command> [options] [paths...]\n\
\n\
commands:\n\
  check                   check Markdown lint, links, math, Mermaid, headings, and runtime-profile docs\n\
  format                  format Markdown, then run the adjacent docs check\n\
  check-entrypoints       check the finite root entrypoint owner-map contract\n\
  check-bootstrap         check bootstrap docs or a source-free static-seed consumer\n\
  render-runtime-profile  render the runtime profile inventory\n\
  help, -h, --help        show this command contract\n\
\n\
options:\n\
  --root <repo-root>      repository root to evaluate; defaults to the current directory\n\
\n\
examples:\n\
  tools/bin/agent-canon docs -h\n\
  tools/bin/agent-canon docs check documents/tools/agent-canon.md\n\
  tools/bin/agent-canon docs check-entrypoints --root . --format json\n\
  tools/bin/agent-canon docs check-bootstrap --root .\n\
  tools/bin/agent-canon docs check-bootstrap --root <seed> --static-seed-consumer\n\
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

fn iter_static_seed_consumer_findings(root: &Path) -> Vec<String> {
    let mut findings = Vec::new();
    for relative in STATIC_SEED_FORBIDDEN_PATHS {
        let path = root.join(relative);
        if path.exists() || is_symlink(&path) {
            findings.push(format!(
                "{relative}: live AgentCanon consumer surface is forbidden"
            ));
        }
    }

    let provenance_path = root.join(STATIC_SEED_PROVENANCE_PATH);
    let provenance = if !is_regular_file(&provenance_path) {
        findings.push(format!(
            "{STATIC_SEED_PROVENANCE_PATH}: expected a regular provenance file"
        ));
        None
    } else {
        match fs::read_to_string(&provenance_path) {
            Err(error) => {
                findings.push(format!(
                    "{STATIC_SEED_PROVENANCE_PATH}: invalid JSON: {error}"
                ));
                None
            }
            Ok(text) => match serde_json::from_str::<Value>(&text) {
                Err(error) => {
                    findings.push(format!(
                        "{STATIC_SEED_PROVENANCE_PATH}: invalid JSON: {error}"
                    ));
                    None
                }
                Ok(Value::Object(object)) => Some(object),
                Ok(_) => {
                    findings.push(format!(
                        "{STATIC_SEED_PROVENANCE_PATH}: JSON root must be an object"
                    ));
                    None
                }
            },
        }
    };
    if let Some(provenance) = provenance.as_ref() {
        let expected_keys = ["schema_version", "source_commit", "source_repository"];
        let mut actual_keys = provenance.keys().cloned().collect::<Vec<_>>();
        actual_keys.sort();
        if actual_keys.iter().map(String::as_str).collect::<Vec<_>>() != expected_keys {
            findings.push(format!(
                "{STATIC_SEED_PROVENANCE_PATH}: keys must be exactly {}",
                python_list_repr(&expected_keys)
            ));
        }
        if !json_value_equals_python_integer_one(provenance.get("schema_version")) {
            findings.push(format!(
                "{STATIC_SEED_PROVENANCE_PATH}: schema_version must be 1"
            ));
        }
        if provenance.get("source_repository").and_then(Value::as_str)
            != Some(STATIC_SEED_SOURCE_REPOSITORY)
        {
            findings.push(format!(
                "{STATIC_SEED_PROVENANCE_PATH}: source_repository must be {STATIC_SEED_SOURCE_REPOSITORY}"
            ));
        }
        let source_commit = provenance.get("source_commit").and_then(Value::as_str);
        if !source_commit.is_some_and(|commit| object_id_pattern().is_match(commit)) {
            findings.push(format!(
                "{STATIC_SEED_PROVENANCE_PATH}: source_commit must be a lowercase Git object ID"
            ));
        }
    }

    let codex_root = root.join(".codex");
    let agents_root = codex_root.join("agents");
    for (relative, path) in [
        (".codex", codex_root.as_path()),
        (".codex/agents", agents_root.as_path()),
    ] {
        if !is_regular_directory(path) {
            findings.push(format!("{relative}: expected a regular directory"));
        }
    }

    let config_path = codex_root.join("config.toml");
    let config = if !is_regular_file(&config_path) {
        findings.push(".codex/config.toml: expected a regular file".to_owned());
        None
    } else {
        load_static_seed_toml(&config_path, ".codex/config.toml", &mut findings)
    };

    let mut referenced_roles = BTreeSet::new();
    if let Some(config) = config.as_ref() {
        if let Some(raw_agents) = config.get("agents").and_then(item_as_table_like) {
            for (raw_role, raw_value) in raw_agents.iter() {
                let Some(role_table) = item_as_table_like(raw_value) else {
                    continue;
                };
                let Some(config_file) = role_table.get("config_file").and_then(Item::as_str) else {
                    findings.push(format!(
                        ".codex/config.toml: agents.{raw_role}.config_file must be a string"
                    ));
                    continue;
                };
                let Some(resolved) = canonical_role_path(raw_role, config_file) else {
                    findings.push(format!(
                        ".codex/config.toml: agents.{raw_role}.config_file must be agents/{raw_role}.toml"
                    ));
                    continue;
                };
                referenced_roles.insert(resolved.clone());
                if !is_regular_file(&root.join(&resolved)) {
                    findings.push(format!(
                        "{resolved}: expected a regular referenced role file"
                    ));
                }
            }
        } else {
            findings.push(".codex/config.toml: [agents] table is required".to_owned());
        }
    }

    finish_static_seed_consumer(root, findings, config, referenced_roles, &agents_root)
}

fn finish_static_seed_consumer(
    root: &Path,
    mut findings: Vec<String>,
    config: Option<DocumentMut>,
    referenced_roles: BTreeSet<String>,
    agents_root: &Path,
) -> Vec<String> {
    let mut actual_roles = BTreeSet::new();
    if is_regular_directory(agents_root) {
        collect_static_role_files(root, agents_root, &mut actual_roles, &mut findings);
    }
    if actual_roles != referenced_roles {
        let missing = referenced_roles
            .difference(&actual_roles)
            .cloned()
            .collect::<Vec<_>>();
        let extra = actual_roles
            .difference(&referenced_roles)
            .cloned()
            .collect::<Vec<_>>();
        if !missing.is_empty() {
            findings.push(format!(
                ".codex/agents: missing referenced role files: {}",
                python_list_repr(&missing.iter().map(String::as_str).collect::<Vec<_>>())
            ));
        }
        if !extra.is_empty() {
            findings.push(format!(
                ".codex/agents: unreferenced role files: {}",
                python_list_repr(&extra.iter().map(String::as_str).collect::<Vec<_>>())
            ));
        }
    }

    let mut toml_payloads = BTreeMap::<String, DocumentMut>::new();
    if let Some(config) = config {
        toml_payloads.insert(".codex/config.toml".to_owned(), config);
    }
    for relative in &actual_roles {
        let path = root.join(relative);
        if let Some(document) = load_static_seed_toml(&path, relative, &mut findings) {
            toml_payloads.insert(relative.clone(), document);
        }
    }

    let mut controlled_files = BTreeSet::from([STATIC_SEED_PROVENANCE_PATH.to_owned()]);
    controlled_files.insert(".codex/config.toml".to_owned());
    controlled_files.extend(referenced_roles);
    controlled_files.extend(actual_roles);
    for relative in controlled_files {
        let path = root.join(&relative);
        if !is_regular_file(&path) {
            continue;
        }
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(error) => {
                findings.push(format!("{relative}: cannot read file: {error}"));
                continue;
            }
        };
        let lowered = bytes.to_ascii_lowercase();
        for marker in STATIC_SEED_FORBIDDEN_CONTENT {
            if contains_bytes(&lowered, marker) {
                findings.push(format!(
                    "{relative}: static seed contains forbidden runtime marker: {}",
                    String::from_utf8_lossy(marker)
                ));
            }
        }
    }

    for (relative, document) in toml_payloads {
        let mut found_prefixes = BTreeSet::new();
        scan_toml_table(document.as_table(), &mut found_prefixes);
        for marker in found_prefixes {
            findings.push(format!(
                "{relative}: static seed contains forbidden runtime marker: {}",
                String::from_utf8_lossy(&marker)
            ));
        }
    }
    findings
}

fn collect_static_role_files(
    root: &Path,
    directory: &Path,
    files: &mut BTreeSet<String>,
    findings: &mut Vec<String>,
) {
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    let mut entries = entries.flatten().collect::<Vec<_>>();
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        let path = entry.path();
        let relative = path
            .strip_prefix(root)
            .unwrap_or(&path)
            .to_string_lossy()
            .replace('\\', "/");
        let Ok(metadata) = fs::symlink_metadata(&path) else {
            continue;
        };
        if metadata.file_type().is_symlink() {
            findings.push(format!("{relative}: static seed must not contain symlinks"));
        } else if metadata.file_type().is_dir() {
            collect_static_role_files(root, &path, files, findings);
        } else if metadata.file_type().is_file() {
            files.insert(relative);
        }
    }
}

fn load_static_seed_toml(
    path: &Path,
    label: &str,
    findings: &mut Vec<String>,
) -> Option<DocumentMut> {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) => {
            findings.push(format!("{label}: invalid UTF-8 TOML: {error}"));
            return None;
        }
    };
    match text.parse::<DocumentMut>() {
        Ok(document) => Some(document),
        Err(error) => {
            findings.push(format!("{label}: invalid UTF-8 TOML: {error}"));
            None
        }
    }
}

fn canonical_role_path(role: &str, raw_path: &str) -> Option<String> {
    if raw_path.is_empty()
        || raw_path.starts_with('/')
        || raw_path
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return None;
    }
    let resolved = format!(".codex/{raw_path}");
    let expected = format!(".codex/agents/{role}.toml");
    (resolved == expected).then_some(resolved)
}

fn scan_toml_table(table: &dyn TableLike, found: &mut BTreeSet<Vec<u8>>) {
    for (key, item) in table.iter() {
        scan_toml_string(key, found);
        scan_toml_item(item, found);
    }
}

fn scan_toml_item(item: &Item, found: &mut BTreeSet<Vec<u8>>) {
    if let Some(value) = item.as_str() {
        scan_toml_string(value, found);
    } else if let Some(table) = item.as_table() {
        scan_toml_table(table, found);
    } else if let Some(tables) = item.as_array_of_tables() {
        for table in tables.iter() {
            scan_toml_table(table, found);
        }
    } else if let Some(values) = item.as_array() {
        for value in values.iter() {
            scan_toml_value(value, found);
        }
    } else if let Some(table) = item.as_inline_table() {
        scan_toml_table(table, found);
    }
}

fn scan_toml_value(value: &toml_edit::Value, found: &mut BTreeSet<Vec<u8>>) {
    if let Some(value) = value.as_str() {
        scan_toml_string(value, found);
    } else if let Some(values) = value.as_array() {
        for value in values.iter() {
            scan_toml_value(value, found);
        }
    } else if let Some(table) = value.as_inline_table() {
        scan_toml_table(table, found);
    }
}

fn scan_toml_string(value: &str, found: &mut BTreeSet<Vec<u8>>) {
    let lowered = value.to_lowercase().into_bytes();
    for marker in STATIC_SEED_FORBIDDEN_PREFIXES {
        if contains_bytes(&lowered, marker) {
            found.insert(marker.to_vec());
        }
    }
}

fn contains_bytes(source: &[u8], needle: &[u8]) -> bool {
    !needle.is_empty() && source.windows(needle.len()).any(|window| window == needle)
}

fn object_id_pattern() -> &'static Regex {
    static PATTERN: OnceLock<Regex> = OnceLock::new();
    PATTERN.get_or_init(|| Regex::new(r"^[0-9a-f]{40,64}$").expect("static object ID expression"))
}

fn json_value_equals_python_integer_one(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(true)) => true,
        Some(Value::Number(number)) => {
            number.as_i64() == Some(1) || number.as_u64() == Some(1) || number.as_f64() == Some(1.0)
        }
        _ => false,
    }
}

fn python_string_repr(value: &str) -> String {
    format!("'{}'", value.replace('\\', "\\\\").replace('\'', "\\'"))
}

fn python_list_repr(values: &[&str]) -> String {
    format!(
        "[{}]",
        values
            .iter()
            .map(|value| python_string_repr(value))
            .collect::<Vec<_>>()
            .join(", ")
    )
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
        assert!(usage.contains("docs check-entrypoints"));
        assert!(usage.contains("docs check-bootstrap"));
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
}
