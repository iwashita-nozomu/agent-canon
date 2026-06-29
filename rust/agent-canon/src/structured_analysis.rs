// @dependency-start
// contract implementation
// responsibility Implements structured prose/document analysis Rust CLI commands.
// upstream design ../../../documents/structured-analysis/README.md structured analysis package boundary
// upstream design ../../../documents/structured-analysis/database-design.md structured analysis DB contract
// upstream design ../../../documents/prose-reasoning-graph/dsl-spec.md document responsibility diagnostic boundary
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation ../../../tests/agent_tools/test_structured_document_inventory_cli.py tests the canonical CLI
// downstream implementation ../../../rust/agent-canon/src/main.rs routes structured-analysis commands
// @dependency-end

use rusqlite::{params, Connection};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

const DOC_SUFFIXES: &[&str] = &["md", "rst", "txt"];
const HEADER_SCAN_LINES: usize = 120;
const HEADER_SCAN_BYTES: usize = 64 * 1024;
const MAX_MARKDOWN_FINDINGS: usize = 200;
const DOCUMENT_RESPONSIBILITY_GAP: &str = "document_responsibility_gap";
const DIRECTORY_RESPONSIBILITY_LOW_CHILD_COVERAGE: &str =
    "directory_responsibility_low_child_coverage";
const DIRECTORY_RESPONSIBILITY_EVIDENCE_LIMIT: usize = 8;
const GRAPH_CONTRACT_VERSION: &str = "graph_storage_core.v1";
const REGISTERED_GRAPH_LAYERS: &[&str] = &[
    "source",
    "form",
    "prose",
    "concept",
    "discourse",
    "argument",
    "evidence",
    "presentation",
    "projection",
    "diagnostics",
    "edit-operation",
    "artifact",
    "document-canon",
    "deps",
    "code",
    "report",
    "algorithm",
    "proof",
];
const KNOWN_ORDER_KINDS: &[&str] = &[
    "",
    "hard",
    "hard_before",
    "adjacency_preferred",
    "preferred",
    "none",
];
const DIAGNOSTIC_SEVERITIES: &[&str] = &["blocker", "warn", "info"];

#[derive(Debug, Clone, PartialEq, Eq)]
struct DocumentRecord {
    path: String,
    title: String,
    responsibility: String,
    upstream_design_targets: Vec<String>,
    coverage_rules: Vec<CoverageRule>,
    has_dependency_manifest: bool,
    text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CoverageRule {
    id: String,
    requirement_groups: Vec<Vec<String>>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct DocumentFinding {
    path: String,
    kind: String,
    canonical_path: String,
    action: String,
    reason: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct InventoryReport {
    root: String,
    documents: Vec<DocumentRecord>,
    findings: Vec<DocumentFinding>,
    historical_records: Vec<DocumentFinding>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FileRecord {
    path: String,
    file_kind: String,
    extension: String,
    byte_len: u64,
    content_sha256: String,
    title: String,
    responsibility: String,
    has_dependency_manifest: bool,
    is_document: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct DirectoryResponsibility {
    path: String,
    responsibility: String,
    basis: String,
    readme_path: String,
    evidence_paths: Vec<String>,
    descendant_file_count: usize,
    declared_responsibility_count: usize,
    child_kind_counts: BTreeMap<String, usize>,
    missing_child_terms: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct InventoryArgs {
    root: PathBuf,
    json_out: Option<PathBuf>,
    markdown_out: Option<PathBuf>,
    fail_on_findings: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ImportArgs {
    db: PathBuf,
    json: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct AnalyzeArgs {
    db: PathBuf,
    diagnostics_db: PathBuf,
    profile: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BuildArgs {
    root: PathBuf,
    profile: String,
    out_dir: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct GraphContractArgs {
    db: Option<PathBuf>,
    format: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct BuildResult {
    cache_dir: PathBuf,
    report_dir: PathBuf,
    db: PathBuf,
    diagnostics_db: PathBuf,
    document_inventory_json: PathBuf,
    document_inventory_markdown: PathBuf,
    file_count: usize,
    directory_count: usize,
    document_count: usize,
    document_finding_count: usize,
    document_historical_record_count: usize,
    warning_count: usize,
    blocker_count: usize,
    warn_count: usize,
    info_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct WarningRow {
    id: String,
    source_layer: String,
    severity: String,
    rule: String,
    target_node_id: String,
    target_edge_id: String,
    target_path: String,
    message: String,
    suggested_action_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct WarningSummary {
    warning_count: usize,
    blocker_count: usize,
    warn_count: usize,
    info_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct GraphContractFinding {
    severity: String,
    rule: String,
    location: String,
    message: String,
}

pub fn run(args: &[String]) -> i32 {
    let Some(command) = args.first() else {
        eprintln!("STRUCTURED_ANALYSIS=fail");
        eprintln!("STRUCTURED_ANALYSIS_FINDING=missing-command");
        return 2;
    };
    match command.as_str() {
        "analyze" => run_analyze(&args[1..]),
        "build" => run_build(&args[1..]),
        "document-inventory" => run_document_inventory(&args[1..]),
        "graph-contract" => run_graph_contract(&args[1..]),
        "import-document-inventory" => run_import_document_inventory(&args[1..]),
        "help" | "--help" | "-h" => {
            print_usage();
            0
        }
        unknown => {
            eprintln!("STRUCTURED_ANALYSIS=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=unknown-command:{unknown}");
            print_usage();
            2
        }
    }
}

fn print_usage() {
    eprintln!(
        "usage: agent-canon structured-analysis build --root <repo-root> [--profile name] [--out-dir path] | analyze --db <prose_graph.sqlite> --diagnostics-db <diagnostics.sqlite> [--profile name] | graph-contract [--db <graph.sqlite>] [--format text|json] | document-inventory --root <repo-root> [--json-out path] [--markdown-out path] [--fail-on-findings] | import-document-inventory --db <graph.sqlite> --json <inventory.json>"
    );
}

fn run_analyze(args: &[String]) -> i32 {
    let parsed = match parse_analyze_args(args) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_ANALYZE=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=invalid-arguments:{message}");
            return 2;
        }
    };
    let summary =
        match analyze_structured_analysis_db(&parsed.db, &parsed.diagnostics_db, &parsed.profile) {
            Ok(value) => value,
            Err(message) => {
                eprintln!("STRUCTURED_ANALYSIS_ANALYZE=fail");
                eprintln!("STRUCTURED_ANALYSIS_FINDING=analyze-error:{message}");
                return 1;
            }
        };
    println!("STRUCTURED_ANALYSIS_ANALYZE=pass");
    println!("STRUCTURED_ANALYSIS_PROFILE={}", parsed.profile);
    println!("STRUCTURED_ANALYSIS_DB={}", parsed.db.display());
    println!(
        "STRUCTURED_ANALYSIS_DIAGNOSTICS_DB={}",
        parsed.diagnostics_db.display()
    );
    println!("STRUCTURED_ANALYSIS_WARNINGS={}", summary.warning_count);
    println!("STRUCTURED_ANALYSIS_BLOCKERS={}", summary.blocker_count);
    println!("STRUCTURED_ANALYSIS_WARNS={}", summary.warn_count);
    println!("STRUCTURED_ANALYSIS_INFOS={}", summary.info_count);
    0
}

fn run_build(args: &[String]) -> i32 {
    let parsed = match parse_build_args(args) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_BUILD=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=invalid-arguments:{message}");
            return 2;
        }
    };
    let result = match build_structured_analysis_cache(&parsed) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_BUILD=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=build-error:{message}");
            return 1;
        }
    };
    println!("STRUCTURED_ANALYSIS_BUILD=pass");
    println!("STRUCTURED_ANALYSIS_PROFILE={}", parsed.profile);
    println!(
        "STRUCTURED_ANALYSIS_CACHE_DIR={}",
        result.cache_dir.display()
    );
    println!(
        "STRUCTURED_ANALYSIS_REPORT_DIR={}",
        result.report_dir.display()
    );
    println!("STRUCTURED_ANALYSIS_DB={}", result.db.display());
    println!(
        "STRUCTURED_ANALYSIS_DIAGNOSTICS_DB={}",
        result.diagnostics_db.display()
    );
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY_JSON={}",
        result.document_inventory_json.display()
    );
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY_MARKDOWN={}",
        result.document_inventory_markdown.display()
    );
    println!("STRUCTURED_ANALYSIS_FILES={}", result.file_count);
    println!("STRUCTURED_ANALYSIS_DIRECTORIES={}", result.directory_count);
    println!("STRUCTURED_ANALYSIS_DOCUMENTS={}", result.document_count);
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_CANON_FINDINGS={}",
        result.document_finding_count
    );
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_HISTORICAL_RECORDS={}",
        result.document_historical_record_count
    );
    println!("STRUCTURED_ANALYSIS_WARNINGS={}", result.warning_count);
    println!("STRUCTURED_ANALYSIS_BLOCKERS={}", result.blocker_count);
    println!("STRUCTURED_ANALYSIS_WARNS={}", result.warn_count);
    println!("STRUCTURED_ANALYSIS_INFOS={}", result.info_count);
    0
}

fn run_graph_contract(args: &[String]) -> i32 {
    let parsed = match parse_graph_contract_args(args) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_GRAPH_CONTRACT=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=invalid-arguments:{message}");
            return 2;
        }
    };
    let findings = match &parsed.db {
        Some(path) => {
            let connection = match Connection::open(path) {
                Ok(value) => value,
                Err(error) => {
                    eprintln!("STRUCTURED_ANALYSIS_GRAPH_CONTRACT=fail");
                    eprintln!("STRUCTURED_ANALYSIS_FINDING=open-db:{error}");
                    return 1;
                }
            };
            match validate_graph_contract(&connection) {
                Ok(value) => value,
                Err(error) => {
                    eprintln!("STRUCTURED_ANALYSIS_GRAPH_CONTRACT=fail");
                    eprintln!("STRUCTURED_ANALYSIS_FINDING=validate:{error}");
                    return 1;
                }
            }
        }
        None => Vec::new(),
    };
    let failed = findings.iter().any(|finding| finding.severity == "blocker");
    if parsed.format == "json" {
        println!(
            "{}",
            render_graph_contract_json(parsed.db.as_deref(), &findings)
        );
    } else {
        print!(
            "{}",
            render_graph_contract_text(parsed.db.as_deref(), &findings)
        );
    }
    if failed {
        1
    } else {
        0
    }
}

fn run_document_inventory(args: &[String]) -> i32 {
    let parsed = match parse_inventory_args(args) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=invalid-arguments:{message}");
            return 2;
        }
    };

    let report = match build_report(&parsed.root) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=inventory-error:{message}");
            return 1;
        }
    };

    if let Some(path) = &parsed.json_out {
        if let Err(error) = write_file(path, &render_json(&report)) {
            eprintln!("STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=write-json:{error}");
            return 1;
        }
    }
    if let Some(path) = &parsed.markdown_out {
        if let Err(error) = write_file(path, &render_markdown(&report)) {
            eprintln!("STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=write-markdown:{error}");
            return 1;
        }
    }

    println!("STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=pass");
    println!("STRUCTURED_ANALYSIS_DOCUMENTS={}", report.documents.len());
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_FINDINGS={}",
        report.findings.len()
    );
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_HISTORICAL_RECORDS={}",
        report.historical_records.len()
    );
    for finding in &report.findings {
        println!(
            "STRUCTURED_ANALYSIS_DOCUMENT_FINDING={}:{}:{}:{}",
            finding.kind, finding.path, finding.canonical_path, finding.action
        );
    }
    for record in &report.historical_records {
        println!(
            "STRUCTURED_ANALYSIS_DOCUMENT_HISTORICAL_RECORD={}:{}:{}:{}",
            record.kind, record.path, record.canonical_path, record.action
        );
    }

    if parsed.fail_on_findings && !report.findings.is_empty() {
        return 1;
    }
    0
}

fn run_import_document_inventory(args: &[String]) -> i32 {
    let parsed = match parse_import_args(args) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=invalid-arguments:{message}");
            return 2;
        }
    };
    let text = match fs::read_to_string(&parsed.json) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=read-json:{error}");
            return 1;
        }
    };
    let payload: Value = match serde_json::from_str(&text) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=parse-json:{error}");
            return 1;
        }
    };
    let connection = match Connection::open(&parsed.db) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=open-db:{error}");
            return 1;
        }
    };
    if let Err(error) = initialize_graph_schema(&connection) {
        eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
        eprintln!("STRUCTURED_ANALYSIS_FINDING=schema:{error}");
        return 1;
    }
    let document_id = match analysis_document_id(&connection) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=document-id:{error}");
            return 1;
        }
    };
    let result = match import_inventory_payload(&connection, &document_id, &payload, &parsed.json) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=fail");
            eprintln!("STRUCTURED_ANALYSIS_FINDING=import:{error}");
            return 1;
        }
    };
    println!("STRUCTURED_ANALYSIS_IMPORT_DOCUMENT_INVENTORY=pass");
    println!("STRUCTURED_ANALYSIS_DB={}", parsed.db.display());
    println!(
        "STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY={}",
        parsed.json.display()
    );
    println!("STRUCTURED_ANALYSIS_DOCUMENT_CANON_RECORDS={}", result.0);
    println!("STRUCTURED_ANALYSIS_DOCUMENT_CANON_FINDINGS={}", result.1);
    0
}

fn parse_analyze_args(args: &[String]) -> Result<AnalyzeArgs, String> {
    let mut db = None;
    let mut diagnostics_db = None;
    let mut profile = "manual".to_string();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--db" => {
                db = Some(next_path(args, index, "--db")?);
                index += 2;
            }
            "--diagnostics-db" => {
                diagnostics_db = Some(next_path(args, index, "--diagnostics-db")?);
                index += 2;
            }
            "--profile" => {
                profile = args
                    .get(index + 1)
                    .cloned()
                    .ok_or_else(|| "--profile requires a value".to_string())?;
                index += 2;
            }
            unknown => return Err(format!("unknown argument {unknown}")),
        }
    }
    if profile.trim().is_empty() {
        return Err("--profile must not be empty".to_string());
    }
    Ok(AnalyzeArgs {
        db: db.ok_or_else(|| "--db is required".to_string())?,
        diagnostics_db: diagnostics_db.ok_or_else(|| "--diagnostics-db is required".to_string())?,
        profile,
    })
}

fn parse_build_args(args: &[String]) -> Result<BuildArgs, String> {
    let mut root = PathBuf::from(".");
    let mut profile = "manual".to_string();
    let mut out_dir = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                root = next_path(args, index, "--root")?;
                index += 2;
            }
            "--profile" => {
                profile = args
                    .get(index + 1)
                    .cloned()
                    .ok_or_else(|| "--profile requires a value".to_string())?;
                index += 2;
            }
            "--out-dir" => {
                out_dir = Some(next_path(args, index, "--out-dir")?);
                index += 2;
            }
            unknown => return Err(format!("unknown argument {unknown}")),
        }
    }
    if profile.trim().is_empty() {
        return Err("--profile must not be empty".to_string());
    }
    Ok(BuildArgs {
        root,
        profile,
        out_dir,
    })
}

fn parse_graph_contract_args(args: &[String]) -> Result<GraphContractArgs, String> {
    let mut db = None;
    let mut format = "text".to_string();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--db" => {
                db = Some(next_path(args, index, "--db")?);
                index += 2;
            }
            "--format" => {
                format = args
                    .get(index + 1)
                    .cloned()
                    .ok_or_else(|| "--format requires a value".to_string())?;
                if !matches!(format.as_str(), "text" | "json") {
                    return Err("--format must be text or json".to_string());
                }
                index += 2;
            }
            unknown => return Err(format!("unknown argument {unknown}")),
        }
    }
    Ok(GraphContractArgs { db, format })
}

fn parse_inventory_args(args: &[String]) -> Result<InventoryArgs, String> {
    let mut root = PathBuf::from(".");
    let mut json_out = None;
    let mut markdown_out = None;
    let mut fail_on_findings = false;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" => {
                root = next_path(args, index, "--root")?;
                index += 2;
            }
            "--json-out" => {
                json_out = Some(next_path(args, index, "--json-out")?);
                index += 2;
            }
            "--markdown-out" => {
                markdown_out = Some(next_path(args, index, "--markdown-out")?);
                index += 2;
            }
            "--fail-on-findings" => {
                fail_on_findings = true;
                index += 1;
            }
            unknown => return Err(format!("unknown argument {unknown}")),
        }
    }
    Ok(InventoryArgs {
        root,
        json_out,
        markdown_out,
        fail_on_findings,
    })
}

fn parse_import_args(args: &[String]) -> Result<ImportArgs, String> {
    let mut db = None;
    let mut json = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--db" => {
                db = Some(next_path(args, index, "--db")?);
                index += 2;
            }
            "--json" => {
                json = Some(next_path(args, index, "--json")?);
                index += 2;
            }
            unknown => return Err(format!("unknown argument {unknown}")),
        }
    }
    Ok(ImportArgs {
        db: db.ok_or_else(|| "--db is required".to_string())?,
        json: json.ok_or_else(|| "--json is required".to_string())?,
    })
}

fn next_path(args: &[String], index: usize, name: &str) -> Result<PathBuf, String> {
    args.get(index + 1)
        .map(PathBuf::from)
        .ok_or_else(|| format!("{name} requires a value"))
}

fn build_structured_analysis_cache(parsed: &BuildArgs) -> Result<BuildResult, String> {
    let root = fs::canonicalize(&parsed.root)
        .map_err(|error| format!("canonicalize {}: {error}", parsed.root.display()))?;
    let cache_dir = default_cache_dir(&root, &parsed.profile)?;
    let report_dir = parsed.out_dir.clone().unwrap_or_else(|| cache_dir.clone());
    fs::create_dir_all(&cache_dir)
        .map_err(|error| format!("create-dir {}: {error}", cache_dir.display()))?;
    fs::create_dir_all(&report_dir)
        .map_err(|error| format!("create-dir {}: {error}", report_dir.display()))?;
    let exports_dir = report_dir.join("exports");
    fs::create_dir_all(&exports_dir)
        .map_err(|error| format!("create-dir {}: {error}", exports_dir.display()))?;

    let report = build_report(&root)?;
    let inventory_json = report_dir.join("document_inventory.json");
    let inventory_markdown = exports_dir.join("document_inventory.md");
    let inventory_text = render_json(&report);
    write_file(&inventory_json, &inventory_text)?;
    write_file(&inventory_markdown, &render_markdown(&report))?;

    let files = collect_files(&root)?;
    let db = cache_dir.join("prose_graph.sqlite");
    remove_regenerated_file(&db)?;
    let connection =
        Connection::open(&db).map_err(|error| format!("open-db {}: {error}", db.display()))?;
    initialize_graph_schema(&connection).map_err(|error| format!("schema: {error}"))?;
    let document_id = ensure_analysis_document(&connection, &root)
        .map_err(|error| format!("analysis-document: {error}"))?;
    let inventory_payload: Value = serde_json::from_str(&inventory_text)
        .map_err(|error| format!("inventory-json: {error}"))?;
    let imported = import_inventory_payload(
        &connection,
        &document_id,
        &inventory_payload,
        &inventory_json,
    )
    .map_err(|error| format!("document-canon-import: {error}"))?;
    let artifact_counts = import_artifact_layer(&connection, &document_id, &files)
        .map_err(|error| format!("artifact-import: {error}"))?;
    let diagnostics_db = cache_dir.join("diagnostics.sqlite");
    remove_regenerated_file(&diagnostics_db)?;
    let warning_summary = analyze_structured_analysis_db(&db, &diagnostics_db, &parsed.profile)?;
    let result = BuildResult {
        cache_dir,
        report_dir,
        db,
        diagnostics_db,
        document_inventory_json: inventory_json,
        document_inventory_markdown: inventory_markdown,
        file_count: artifact_counts.0,
        directory_count: artifact_counts.1,
        document_count: imported.0,
        document_finding_count: imported.1,
        document_historical_record_count: imported.2,
        warning_count: warning_summary.warning_count,
        blocker_count: warning_summary.blocker_count,
        warn_count: warning_summary.warn_count,
        info_count: warning_summary.info_count,
    };
    write_build_artifacts(&result, &root, &parsed.profile)?;
    Ok(result)
}

fn remove_regenerated_file(path: &Path) -> Result<(), String> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("remove-file {}: {error}", path.display())),
    }
}

fn build_report(root: &Path) -> Result<InventoryReport, String> {
    let documents = collect_documents(root)?;
    let (findings, historical_records) = collect_findings(&documents);
    Ok(InventoryReport {
        root: root.to_string_lossy().to_string(),
        documents,
        findings,
        historical_records,
    })
}

fn collect_documents(root: &Path) -> Result<Vec<DocumentRecord>, String> {
    let mut records = Vec::new();
    for relative_path in document_paths(root)? {
        let path = root.join(&relative_path);
        if !path.is_file() || path.is_symlink() {
            continue;
        }
        let text = fs::read_to_string(&path)
            .or_else(|_| fs::read(&path).map(|bytes| String::from_utf8_lossy(&bytes).to_string()))
            .map_err(|error| format!("read {}: {error}", path.display()))?;
        let lines: Vec<&str> = text.lines().collect();
        let title = markdown_title_for_path(Path::new(&relative_path), &lines);
        records.push(DocumentRecord {
            path: relative_path,
            title,
            responsibility: dependency_responsibility(&lines),
            upstream_design_targets: dependency_manifest_values(&lines, "upstream design "),
            coverage_rules: dependency_coverage_rules(&lines),
            has_dependency_manifest: has_dependency_manifest(&lines),
            text,
        });
    }
    records.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(records)
}

fn document_paths(root: &Path) -> Result<Vec<String>, String> {
    if let Some(paths) = git_visible_paths(root) {
        return Ok(paths
            .into_iter()
            .filter(|path| is_document_path(Path::new(path)))
            .collect());
    }
    let mut paths = Vec::new();
    collect_document_paths_recursive(root, root, &mut paths)?;
    paths.sort();
    Ok(paths)
}

fn collect_files(root: &Path) -> Result<Vec<FileRecord>, String> {
    let mut records = Vec::new();
    for relative_path in file_paths(root)? {
        let path = root.join(&relative_path);
        if !path.is_file() || path.is_symlink() {
            continue;
        }
        let bytes = fs::read(&path).map_err(|error| format!("read {}: {error}", path.display()))?;
        let header_bytes = &bytes[..bytes.len().min(HEADER_SCAN_BYTES)];
        let header_text = String::from_utf8_lossy(header_bytes);
        let lines: Vec<&str> = header_text.lines().collect();
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        records.push(FileRecord {
            path: relative_path,
            file_kind: file_kind(&path),
            extension,
            byte_len: bytes.len() as u64,
            content_sha256: sha256_hex(&bytes),
            title: markdown_title_for_path(&path, &lines),
            responsibility: dependency_responsibility(&lines),
            has_dependency_manifest: has_dependency_manifest(&lines),
            is_document: is_document_path(&path),
        });
    }
    records.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(records)
}

fn file_paths(root: &Path) -> Result<Vec<String>, String> {
    if let Some(paths) = git_visible_paths(root) {
        return Ok(paths);
    }
    let mut paths = Vec::new();
    collect_file_paths_recursive(root, root, &mut paths)?;
    paths.sort();
    Ok(paths)
}

fn git_visible_paths(root: &Path) -> Option<Vec<String>> {
    let output = Command::new("git")
        .arg("-C")
        .arg(root)
        .args([
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ])
        .output();
    if let Ok(result) = output {
        if result.status.success() && !result.stdout.is_empty() {
            return Some(
                result
                    .stdout
                    .split(|byte| *byte == b'\0')
                    .filter(|raw| !raw.is_empty())
                    .map(|raw| String::from_utf8_lossy(raw).to_string())
                    .filter(|path| !is_ephemeral_path(Path::new(path)))
                    .collect(),
            );
        }
    }
    None
}

fn collect_document_paths_recursive(
    root: &Path,
    current: &Path,
    paths: &mut Vec<String>,
) -> Result<(), String> {
    for entry in
        fs::read_dir(current).map_err(|error| format!("read-dir {}: {error}", current.display()))?
    {
        let entry =
            entry.map_err(|error| format!("read-dir-entry {}: {error}", current.display()))?;
        let path = entry.path();
        if path.is_dir() {
            if skip_recursive_dir(&path) {
                continue;
            }
            collect_document_paths_recursive(root, &path, paths)?;
        } else if path.is_file() && is_document_path(&path) {
            let relative = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            paths.push(relative);
        }
    }
    Ok(())
}

fn collect_file_paths_recursive(
    root: &Path,
    current: &Path,
    paths: &mut Vec<String>,
) -> Result<(), String> {
    for entry in
        fs::read_dir(current).map_err(|error| format!("read-dir {}: {error}", current.display()))?
    {
        let entry =
            entry.map_err(|error| format!("read-dir-entry {}: {error}", current.display()))?;
        let path = entry.path();
        if path.is_dir() {
            if skip_recursive_dir(&path) {
                continue;
            }
            collect_file_paths_recursive(root, &path, paths)?;
        } else if path.is_file() {
            let relative = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            paths.push(relative);
        }
    }
    Ok(())
}

fn skip_recursive_dir(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .map(|name| {
            matches!(
                name,
                ".git"
                    | ".agent-canon"
                    | ".mypy_cache"
                    | ".pytest_cache"
                    | ".ruff_cache"
                    | ".venv"
                    | "__pycache__"
                    | "node_modules"
                    | "reports"
                    | "target"
            )
        })
        .unwrap_or(false)
}

fn is_ephemeral_path(path: &Path) -> bool {
    path.components()
        .next()
        .map(|component| component.as_os_str())
        == Some("reports".as_ref())
}

fn is_document_path(path: &Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| DOC_SUFFIXES.contains(&extension.to_ascii_lowercase().as_str()))
        .unwrap_or(false)
}

fn is_markdown_path(path: &Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| extension.eq_ignore_ascii_case("md"))
        .unwrap_or(false)
}

fn has_dependency_manifest(lines: &[&str]) -> bool {
    let header = &lines[..lines.len().min(HEADER_SCAN_LINES)];
    header.iter().any(|line| line.contains("@dependency-start"))
        && header.iter().any(|line| line.contains("@dependency-end"))
}

fn dependency_responsibility(lines: &[&str]) -> String {
    dependency_manifest_values(lines, "responsibility ")
        .into_iter()
        .next()
        .unwrap_or_default()
}

fn dependency_manifest_values(lines: &[&str], prefix: &str) -> Vec<String> {
    let mut values = Vec::new();
    for line in lines.iter().take(HEADER_SCAN_LINES) {
        let stripped = strip_comment_prefix(line.trim());
        if let Some(value) = stripped.strip_prefix(prefix) {
            values.push(value.trim().to_string());
        }
    }
    values
}

fn dependency_coverage_rules(lines: &[&str]) -> Vec<CoverageRule> {
    dependency_manifest_values(lines, "coverage ")
        .into_iter()
        .filter_map(|value| parse_coverage_rule(&value))
        .collect()
}

fn parse_coverage_rule(value: &str) -> Option<CoverageRule> {
    let (id, requirements) = value.split_once(" requires ")?;
    let id = id.trim().to_string();
    if id.is_empty() {
        return None;
    }
    let requirement_groups = requirements
        .split(';')
        .filter_map(|group| {
            let alternatives = group
                .split('|')
                .map(normalize_coverage_term)
                .filter(|term| !term.is_empty())
                .collect::<Vec<_>>();
            if alternatives.is_empty() {
                None
            } else {
                Some(alternatives)
            }
        })
        .collect::<Vec<_>>();
    if requirement_groups.is_empty() {
        None
    } else {
        Some(CoverageRule {
            id,
            requirement_groups,
        })
    }
}

fn normalize_coverage_term(value: &str) -> String {
    value
        .trim()
        .trim_matches('`')
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_ascii_lowercase()
}

fn markdown_title(lines: &[&str]) -> String {
    for line in lines.iter().take(HEADER_SCAN_LINES) {
        if let Some(value) = line.strip_prefix("# ") {
            return value.trim().to_string();
        }
    }
    String::new()
}

fn markdown_title_for_path(path: &Path, lines: &[&str]) -> String {
    if is_markdown_path(path) {
        markdown_title(lines)
    } else {
        String::new()
    }
}

fn strip_comment_prefix(line: &str) -> &str {
    let mut value = line.trim();
    loop {
        let stripped = value
            .strip_prefix('#')
            .or_else(|| value.strip_prefix("//"))
            .or_else(|| value.strip_prefix('*'))
            .or_else(|| value.strip_prefix("<!--"))
            .or_else(|| value.strip_prefix("-->"));
        let Some(next) = stripped else {
            return value.trim();
        };
        value = next.trim();
    }
}

fn collect_findings(records: &[DocumentRecord]) -> (Vec<DocumentFinding>, Vec<DocumentFinding>) {
    let mut findings = Vec::new();
    let records_by_path = records
        .iter()
        .map(|record| (record.path.as_str(), record))
        .collect::<BTreeMap<_, _>>();
    for record in records {
        findings.extend(direct_findings(record, &records_by_path));
    }
    findings.extend(duplicate_title_findings(records));
    let mut seen = BTreeSet::new();
    let deduped = findings
        .into_iter()
        .filter(|finding| {
            let key = format!(
                "{}\t{}\t{}\t{}\t{}",
                finding.path, finding.kind, finding.canonical_path, finding.action, finding.reason
            );
            seen.insert(key)
        })
        .collect::<Vec<_>>();
    let mut active_findings = Vec::new();
    let mut historical_records = Vec::new();
    for finding in deduped {
        if is_historical_document_record(&finding) {
            historical_records.push(normalize_historical_record(finding));
        } else {
            active_findings.push(finding);
        }
    }
    (active_findings, historical_records)
}

fn is_historical_document_record(finding: &DocumentFinding) -> bool {
    let path = Path::new(&finding.path);
    path.starts_with("issues/closed")
        && path.file_name().and_then(|name| name.to_str()) != Some("README.md")
}

fn normalize_historical_record(mut finding: DocumentFinding) -> DocumentFinding {
    if finding.kind == "closed_issue_record" {
        finding.action = "retain as historical record; open a new issue for new scope".to_string();
    } else if finding.kind == "stale_name_candidate" {
        finding.action = "retain historical filename; open a new issue for new scope".to_string();
        finding.reason =
            "closed issue filenames preserve historical operational context".to_string();
    }
    finding
}

fn direct_findings(
    record: &DocumentRecord,
    records_by_path: &BTreeMap<&str, &DocumentRecord>,
) -> Vec<DocumentFinding> {
    let mut findings = Vec::new();
    let path = Path::new(&record.path);
    if is_accumulated_eval_report(path) {
        findings.push(DocumentFinding {
            path: record.path.clone(),
            kind: "accumulated_eval_result".to_string(),
            canonical_path: "evidence/agent-evals/README.md".to_string(),
            action: "retain as evidence; do not edit as policy".to_string(),
            reason: "accumulated eval reports are run evidence, not the prompt canon".to_string(),
        });
    }
    if path
        .components()
        .next()
        .map(|component| component.as_os_str())
        == Some("reports".as_ref())
    {
        findings.push(DocumentFinding {
            path: record.path.clone(),
            kind: "generated_report".to_string(),
            canonical_path: "tools/README.md".to_string(),
            action: "regenerate or cite as evidence; do not treat as source policy".to_string(),
            reason: "reports are generated run artifacts".to_string(),
        });
    }
    if path.starts_with("issues/closed")
        && path.file_name().and_then(|name| name.to_str()) != Some("README.md")
    {
        findings.push(DocumentFinding {
            path: record.path.clone(),
            kind: "closed_issue_record".to_string(),
            canonical_path: "issues/README.md".to_string(),
            action: "retain as historical record; open a new issue for new scope".to_string(),
            reason: "closed issue files are immutable operational records".to_string(),
        });
    }
    if !record.has_dependency_manifest {
        findings.push(DocumentFinding {
            path: record.path.clone(),
            kind: "missing_dependency_manifest".to_string(),
            canonical_path: nearest_canonical_anchor(path),
            action: "add a dependency manifest or move the artifact out of source docs".to_string(),
            reason: "document lacks a top dependency manifest".to_string(),
        });
    }
    if stale_name_candidate(&record.path) {
        findings.push(DocumentFinding {
            path: record.path.clone(),
            kind: "stale_name_candidate".to_string(),
            canonical_path: nearest_canonical_anchor(path),
            action: "confirm whether the document is current, then rename, merge, or remove"
                .to_string(),
            reason: "path name suggests backup, copy, legacy, snapshot, old, or stale content"
                .to_string(),
        });
    }
    findings.extend(document_responsibility_findings(record, records_by_path));
    findings
}

fn document_responsibility_findings(
    record: &DocumentRecord,
    records_by_path: &BTreeMap<&str, &DocumentRecord>,
) -> Vec<DocumentFinding> {
    let mut findings = Vec::new();
    for upstream_design in &record.upstream_design_targets {
        let Some(upstream_path) = resolve_manifest_target_path(&record.path, upstream_design)
        else {
            continue;
        };
        let Some(upstream_record) = records_by_path.get(upstream_path.as_str()) else {
            continue;
        };
        for rule in &upstream_record.coverage_rules {
            let missing_groups = missing_coverage_groups(rule, &record.text);
            if missing_groups.is_empty() {
                continue;
            }
            findings.push(DocumentFinding {
                path: record.path.clone(),
                kind: DOCUMENT_RESPONSIBILITY_GAP.to_string(),
                canonical_path: record.path.clone(),
                action: "cover the declared upstream design coverage in the document or constrain the dependency manifest responsibility".to_string(),
                reason: format!(
                    "responsibility=`{}` missing_responsibility_coverage=`{}` upstream_design=`{}` missing_terms=`{}`",
                    display_responsibility(&record.responsibility),
                    rule.id,
                    upstream_design,
                    missing_groups.join("; ")
                ),
            });
        }
    }
    findings
}

fn resolve_manifest_target_path(record_path: &str, target: &str) -> Option<String> {
    let target_path = target.split_whitespace().next()?.trim();
    if target_path.is_empty() || target_path.contains("://") {
        return None;
    }
    let base = Path::new(record_path).parent().unwrap_or(Path::new(""));
    normalize_repo_path(&base.join(target_path))
}

fn normalize_repo_path(path: &Path) -> Option<String> {
    let mut parts = Vec::new();
    for component in path.components() {
        match component {
            std::path::Component::CurDir => {}
            std::path::Component::Normal(part) => parts.push(part.to_string_lossy().to_string()),
            std::path::Component::ParentDir => {
                parts.pop()?;
            }
            std::path::Component::RootDir | std::path::Component::Prefix(_) => return None,
        }
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join("/"))
    }
}

fn missing_coverage_groups(rule: &CoverageRule, text: &str) -> Vec<String> {
    let lowered = text.to_ascii_lowercase();
    rule.requirement_groups
        .iter()
        .filter(|group| {
            !group
                .iter()
                .any(|alternative| lowered.contains(alternative))
        })
        .map(|group| group.join("|"))
        .collect()
}

fn display_responsibility(value: &str) -> &str {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        "<undeclared>"
    } else {
        trimmed
    }
}

fn is_accumulated_eval_report(path: &Path) -> bool {
    let parts: Vec<String> = path
        .iter()
        .map(|part| part.to_string_lossy().to_string())
        .collect();
    parts.len() >= 5
        && parts[0] == "agents"
        && parts[1] == "evals"
        && parts[2] == "results"
        && parts[3] == "skill-workflow-prompt"
        && path.file_name().and_then(|name| name.to_str()) != Some("README.md")
}

fn nearest_canonical_anchor(path: &Path) -> String {
    let Some(root) = path.iter().next().and_then(|part| part.to_str()) else {
        return "README.md".to_string();
    };
    if ["agents", "documents", "issues", "memory", "notes", "tools"].contains(&root) {
        return format!("{root}/README.md");
    }
    if root.starts_with('.') {
        return "AGENTS.md".to_string();
    }
    "README.md".to_string()
}

fn stale_name_candidate(path: &str) -> bool {
    path.split(|character: char| ['-', '_', '/'].contains(&character))
        .any(|part| {
            matches!(
                part.to_ascii_lowercase().as_str(),
                "backup" | "copy" | "duplicate" | "legacy" | "old" | "snapshot" | "stale"
            )
        })
}

fn duplicate_title_findings(records: &[DocumentRecord]) -> Vec<DocumentFinding> {
    let mut by_title: BTreeMap<String, Vec<&DocumentRecord>> = BTreeMap::new();
    for record in records {
        let title = normalize_heading(&record.title);
        if title.is_empty() || !participates_in_duplicate_title_check(Path::new(&record.path)) {
            continue;
        }
        by_title.entry(title).or_default().push(record);
    }
    let mut findings = Vec::new();
    for group in by_title.values() {
        if group.len() < 2 {
            continue;
        }
        let canonical = group
            .iter()
            .min_by_key(|record| canonical_priority(record))
            .expect("duplicate group is non-empty");
        for record in group {
            if record.path == canonical.path {
                continue;
            }
            findings.push(DocumentFinding {
                path: record.path.clone(),
                kind: "duplicate_heading_candidate".to_string(),
                canonical_path: canonical.path.clone(),
                action: "merge, retitle, or document why both headings are active".to_string(),
                reason: format!("shares H1 title with {}", canonical.path),
            });
        }
    }
    findings
}

fn normalize_heading(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn participates_in_duplicate_title_check(path: &Path) -> bool {
    let parts: Vec<String> = path
        .iter()
        .map(|part| part.to_string_lossy().to_string())
        .collect();
    if parts.len() >= 2
        && ((parts[0] == ".agents" && parts[1] == "skills")
            || (parts[0] == "issues" && parts[1] == "closed")
            || (parts[0] == "agents" && parts[1] == "templates"))
    {
        return false;
    }
    !(parts.len() >= 3 && parts[0] == "agents" && parts[1] == "evals" && parts[2] == "results")
}

fn canonical_priority(record: &DocumentRecord) -> (usize, String) {
    let path = &record.path;
    if path.starts_with(".agents/skills/") {
        return (0, path.clone());
    }
    if path.starts_with("agents/skills/") {
        return (1, path.clone());
    }
    if path.starts_with("agents/") || path.starts_with("documents/") {
        return (2, path.clone());
    }
    (5, path.clone())
}

fn render_json(report: &InventoryReport) -> String {
    let payload = json!({
        "status": "pass",
        "root": report.root,
        "documents": report.documents.iter().map(document_json).collect::<Vec<_>>(),
        "findings": report.findings.iter().map(finding_json).collect::<Vec<_>>(),
        "historical_records": report.historical_records.iter().map(finding_json).collect::<Vec<_>>(),
        "document_count": report.documents.len(),
        "finding_count": report.findings.len(),
        "historical_record_count": report.historical_records.len(),
    });
    serde_json::to_string_pretty(&payload).expect("inventory JSON should serialize")
}

fn document_json(record: &DocumentRecord) -> Value {
    json!({
        "path": record.path,
        "title": record.title,
        "responsibility": record.responsibility,
        "has_dependency_manifest": record.has_dependency_manifest,
    })
}

fn finding_json(finding: &DocumentFinding) -> Value {
    json!({
        "path": finding.path,
        "kind": finding.kind,
        "canonical_path": finding.canonical_path,
        "action": finding.action,
        "reason": finding.reason,
    })
}

fn render_markdown(report: &InventoryReport) -> String {
    let mut lines =
        vec![
        "# Non-Canonical Document Inventory".to_string(),
        String::new(),
        "<!--".to_string(),
        "@dependency-start".to_string(),
        "responsibility Records non-canonical document candidates for cleanup review.".to_string(),
        "upstream implementation rust/agent-canon/src/structured_analysis.rs generates this report"
            .to_string(),
        "@dependency-end".to_string(),
        "-->".to_string(),
        String::new(),
        format!("- root: `{}`", report.root),
        format!("- documents: `{}`", report.documents.len()),
        format!("- findings: `{}`", report.findings.len()),
        format!("- historical records: `{}`", report.historical_records.len()),
        String::new(),
        "## Findings".to_string(),
        String::new(),
        "| Kind | Path | Canonical Path | Action | Reason |".to_string(),
        "| ---- | ---- | -------------- | ------ | ------ |".to_string(),
    ];
    for finding in report.findings.iter().take(MAX_MARKDOWN_FINDINGS) {
        lines.push(format!(
            "| {} | `{}` | `{}` | {} | {} |",
            finding.kind, finding.path, finding.canonical_path, finding.action, finding.reason
        ));
    }
    if report.findings.len() > MAX_MARKDOWN_FINDINGS {
        lines.push(format!(
            "| truncated | ... | ... | ... | {} additional findings omitted |",
            report.findings.len() - MAX_MARKDOWN_FINDINGS
        ));
    }
    lines.extend([
        String::new(),
        "## Historical Records".to_string(),
        String::new(),
        "| Kind | Path | Canonical Path | Action | Reason |".to_string(),
        "| ---- | ---- | -------------- | ------ | ------ |".to_string(),
    ]);
    for record in report.historical_records.iter().take(MAX_MARKDOWN_FINDINGS) {
        lines.push(format!(
            "| {} | `{}` | `{}` | {} | {} |",
            record.kind, record.path, record.canonical_path, record.action, record.reason
        ));
    }
    if report.historical_records.len() > MAX_MARKDOWN_FINDINGS {
        lines.push(format!(
            "| truncated | ... | ... | ... | {} additional historical records omitted |",
            report.historical_records.len() - MAX_MARKDOWN_FINDINGS
        ));
    }
    format!("{}\n", lines.join("\n"))
}

fn write_file(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("create-dir {}: {error}", parent.display()))?;
    }
    let mut file =
        fs::File::create(path).map_err(|error| format!("create {}: {error}", path.display()))?;
    file.write_all(text.as_bytes())
        .map_err(|error| format!("write {}: {error}", path.display()))
}

fn analyze_structured_analysis_db(
    source_db: &Path,
    diagnostics_db: &Path,
    profile: &str,
) -> Result<WarningSummary, String> {
    if let Some(parent) = diagnostics_db.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("create-dir {}: {error}", parent.display()))?;
    }
    let source = Connection::open(source_db)
        .map_err(|error| format!("open-source-db {}: {error}", source_db.display()))?;
    let diagnostics = Connection::open(diagnostics_db)
        .map_err(|error| format!("open-diagnostics-db {}: {error}", diagnostics_db.display()))?;
    initialize_warning_schema(&diagnostics).map_err(|error| format!("warning-schema: {error}"))?;
    let warnings = collect_warning_rows(&source).map_err(|error| format!("collect: {error}"))?;
    write_warning_rows(&diagnostics, source_db, profile, &warnings)
        .map_err(|error| format!("write: {error}"))
}

fn initialize_warning_schema(connection: &Connection) -> rusqlite::Result<()> {
    connection.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS warning_runs (
            id TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            source_db TEXT NOT NULL,
            created_at TEXT NOT NULL,
            warning_count INTEGER NOT NULL,
            blocker_count INTEGER NOT NULL,
            warn_count INTEGER NOT NULL,
            info_count INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS warnings (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            source_layer TEXT NOT NULL,
            severity TEXT NOT NULL,
            rule TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            target_edge_id TEXT NOT NULL,
            target_path TEXT NOT NULL,
            message TEXT NOT NULL,
            suggested_action_json TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_warnings_severity ON warnings(severity);
        CREATE INDEX IF NOT EXISTS idx_warnings_target_path ON warnings(target_path);
        CREATE INDEX IF NOT EXISTS idx_warnings_rule ON warnings(rule);
        ",
    )
}

fn collect_warning_rows(source: &Connection) -> rusqlite::Result<Vec<WarningRow>> {
    let mut statement = source.prepare(
        "
        SELECT
            d.id,
            d.layer,
            d.severity,
            d.rule,
            d.target_node_id,
            d.target_edge_id,
            d.message,
            d.suggested_action_json,
            COALESCE(n.payload_json, '{}')
        FROM diagnostics AS d
        LEFT JOIN nodes AS n ON n.id = d.target_node_id
        ORDER BY d.layer, d.severity, d.rule, d.id
        ",
    )?;
    let rows: rusqlite::Result<Vec<WarningRow>> = statement
        .query_map([], |row| {
            let source_id: String = row.get(0)?;
            let target_payload: String = row.get(8)?;
            Ok(WarningRow {
                id: format!("warning:{}", stable_id_fragment(&source_id, 20)),
                source_layer: row.get(1)?,
                severity: row.get(2)?,
                rule: row.get(3)?,
                target_node_id: row.get(4)?,
                target_edge_id: row.get(5)?,
                target_path: warning_target_path(&target_payload),
                message: row.get(6)?,
                suggested_action_json: row.get(7)?,
            })
        })?
        .collect();
    let mut rows = rows?;
    rows.extend(graph_contract_warning_rows(source)?);
    Ok(rows)
}

fn graph_contract_warning_rows(source: &Connection) -> rusqlite::Result<Vec<WarningRow>> {
    Ok(validate_graph_contract(source)?
        .into_iter()
        .enumerate()
        .map(|(index, finding)| WarningRow {
            id: format!("warning:graph-contract:{}", index + 1),
            source_layer: "graph-contract".to_string(),
            severity: finding.severity,
            rule: finding.rule,
            target_node_id: String::new(),
            target_edge_id: String::new(),
            target_path: String::new(),
            message: finding.message,
            suggested_action_json: json!({
                "verification_route": "graph_contract_validation",
                "contract_version": GRAPH_CONTRACT_VERSION,
            })
            .to_string(),
        })
        .collect())
}

fn write_warning_rows(
    connection: &Connection,
    source_db: &Path,
    profile: &str,
    warnings: &[WarningRow],
) -> rusqlite::Result<WarningSummary> {
    let run_id = "warning-run:current";
    connection.execute("DELETE FROM warnings", [])?;
    connection.execute("DELETE FROM warning_runs", [])?;
    let summary = warning_summary(warnings);
    for warning in warnings {
        connection.execute(
            "INSERT OR REPLACE INTO warnings(id, run_id, source_layer, severity, rule, target_node_id, target_edge_id, target_path, message, suggested_action_json, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                warning.id,
                run_id,
                warning.source_layer,
                warning.severity,
                warning.rule,
                warning.target_node_id,
                warning.target_edge_id,
                warning.target_path,
                warning.message,
                warning.suggested_action_json,
                json!({
                    "source_db": source_db.to_string_lossy(),
                    "source_layer": warning.source_layer,
                    "source_rule": warning.rule,
                })
                .to_string(),
            ],
        )?;
    }
    connection.execute(
        "INSERT OR REPLACE INTO warning_runs(id, profile, source_db, created_at, warning_count, blocker_count, warn_count, info_count, payload_json) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?)",
        params![
            run_id,
            profile,
            source_db.to_string_lossy(),
            summary.warning_count,
            summary.blocker_count,
            summary.warn_count,
            summary.info_count,
            json!({"source_db": source_db.to_string_lossy(), "profile": profile}).to_string(),
        ],
    )?;
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('structured_analysis_warning_summary', ?)",
        [json!({
            "source_db": source_db.to_string_lossy(),
            "profile": profile,
            "warning_count": summary.warning_count,
            "blocker_count": summary.blocker_count,
            "warn_count": summary.warn_count,
            "info_count": summary.info_count,
        })
        .to_string()],
    )?;
    Ok(summary)
}

fn warning_summary(warnings: &[WarningRow]) -> WarningSummary {
    let mut summary = WarningSummary {
        warning_count: warnings.len(),
        blocker_count: 0,
        warn_count: 0,
        info_count: 0,
    };
    for warning in warnings {
        match warning.severity.as_str() {
            "blocker" => summary.blocker_count += 1,
            "warn" => summary.warn_count += 1,
            _ => summary.info_count += 1,
        }
    }
    summary
}

fn warning_target_path(payload_json: &str) -> String {
    let Ok(payload) = serde_json::from_str::<Value>(payload_json) else {
        return String::new();
    };
    json_string(payload.get("path"))
}

fn validate_graph_contract(connection: &Connection) -> rusqlite::Result<Vec<GraphContractFinding>> {
    let mut findings = Vec::new();
    validate_required_table(
        connection,
        "documents",
        &["id", "path", "title", "kind", "created_at"],
        &mut findings,
    )?;
    validate_required_table(
        connection,
        "nodes",
        &[
            "id",
            "document_id",
            "layer",
            "kind",
            "label",
            "text",
            "source_start",
            "source_end",
            "confidence",
            "payload_json",
        ],
        &mut findings,
    )?;
    validate_required_table(
        connection,
        "edges",
        &[
            "id",
            "layer",
            "kind",
            "from_node_id",
            "to_node_id",
            "order_kind",
            "confidence",
            "evidence_node_id",
            "payload_json",
        ],
        &mut findings,
    )?;
    validate_required_table(
        connection,
        "diagnostics",
        &[
            "id",
            "layer",
            "target_node_id",
            "target_edge_id",
            "severity",
            "rule",
            "message",
            "suggested_action_json",
        ],
        &mut findings,
    )?;
    validate_required_table(connection, "metadata", &["key", "value"], &mut findings)?;
    let node_table_ready = table_has_required_columns(
        connection,
        "nodes",
        &[
            "id",
            "document_id",
            "layer",
            "kind",
            "label",
            "text",
            "source_start",
            "source_end",
            "confidence",
            "payload_json",
        ],
    )?;
    let edge_table_ready = table_has_required_columns(
        connection,
        "edges",
        &[
            "id",
            "layer",
            "kind",
            "from_node_id",
            "to_node_id",
            "order_kind",
            "confidence",
            "evidence_node_id",
            "payload_json",
        ],
    )?;
    let diagnostic_table_ready = table_has_required_columns(
        connection,
        "diagnostics",
        &[
            "id",
            "layer",
            "target_node_id",
            "target_edge_id",
            "severity",
            "rule",
            "message",
            "suggested_action_json",
        ],
    )?;
    if node_table_ready {
        validate_node_rows(connection, &mut findings)?;
    }
    if edge_table_ready {
        validate_edge_rows(connection, &mut findings)?;
    }
    if diagnostic_table_ready {
        validate_diagnostic_rows(connection, &mut findings)?;
    }
    Ok(findings)
}

fn validate_required_table(
    connection: &Connection,
    table: &str,
    required_columns: &[&str],
    findings: &mut Vec<GraphContractFinding>,
) -> rusqlite::Result<()> {
    let Some(columns) = table_columns(connection, table)? else {
        findings.push(graph_contract_finding(
            "blocker",
            "missing_required_table",
            format!("table:{table}"),
            format!("Graph contract table `{table}` is missing."),
        ));
        return Ok(());
    };
    for column in required_columns {
        if !columns.contains(*column) {
            findings.push(graph_contract_finding(
                "blocker",
                "missing_required_column",
                format!("table:{table}.{column}"),
                format!("Graph contract table `{table}` is missing column `{column}`."),
            ));
        }
    }
    Ok(())
}

fn table_has_required_columns(
    connection: &Connection,
    table: &str,
    required_columns: &[&str],
) -> rusqlite::Result<bool> {
    let Some(columns) = table_columns(connection, table)? else {
        return Ok(false);
    };
    Ok(required_columns
        .iter()
        .all(|column| columns.contains(*column)))
}

fn table_columns(
    connection: &Connection,
    table: &str,
) -> rusqlite::Result<Option<BTreeSet<String>>> {
    let mut statement = connection.prepare(&format!("PRAGMA table_info({table})"))?;
    let columns: rusqlite::Result<BTreeSet<_>> = statement
        .query_map([], |row| row.get::<_, String>(1))?
        .collect();
    let columns = columns?;
    if columns.is_empty() {
        Ok(None)
    } else {
        Ok(Some(columns))
    }
}

fn validate_node_rows(
    connection: &Connection,
    findings: &mut Vec<GraphContractFinding>,
) -> rusqlite::Result<()> {
    let document_ids = string_set_query(connection, "SELECT id FROM documents")?;
    let mut statement =
        connection.prepare("SELECT id, document_id, layer, confidence, payload_json FROM nodes")?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, f64>(3)?,
            row.get::<_, String>(4)?,
        ))
    })?;
    for row in rows {
        let (id, document_id, layer, confidence, payload_json) = row?;
        if id.trim().is_empty() {
            findings.push(graph_contract_finding(
                "blocker",
                "empty_node_id",
                "nodes:<empty>",
                "A node row has an empty id.",
            ));
        }
        if !document_ids.contains(&document_id) {
            findings.push(graph_contract_finding(
                "blocker",
                "missing_document_reference",
                format!("nodes:{id}.document_id"),
                format!("Node `{id}` references missing document `{document_id}`."),
            ));
        }
        if !is_registered_graph_layer(&layer) {
            findings.push(graph_contract_finding(
                "warn",
                "unknown_layer",
                format!("nodes:{id}.layer"),
                format!("Node `{id}` uses unregistered layer `{layer}`."),
            ));
        }
        if !(0.0..=1.0).contains(&confidence) {
            findings.push(graph_contract_finding(
                "warn",
                "invalid_confidence",
                format!("nodes:{id}.confidence"),
                format!("Node `{id}` confidence `{confidence}` is outside [0.0, 1.0]."),
            ));
        }
        validate_payload_json("node", &id, "payload_json", &payload_json, findings);
    }
    Ok(())
}

fn validate_edge_rows(
    connection: &Connection,
    findings: &mut Vec<GraphContractFinding>,
) -> rusqlite::Result<()> {
    let node_ids = string_set_query(connection, "SELECT id FROM nodes")?;
    let mut statement = connection.prepare(
        "SELECT id, layer, from_node_id, to_node_id, order_kind, confidence, COALESCE(evidence_node_id, ''), payload_json FROM edges",
    )?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, f64>(5)?,
            row.get::<_, String>(6)?,
            row.get::<_, String>(7)?,
        ))
    })?;
    for row in rows {
        let (
            id,
            layer,
            from_node_id,
            to_node_id,
            order_kind,
            confidence,
            evidence_node_id,
            payload_json,
        ) = row?;
        if !is_registered_graph_layer(&layer) {
            findings.push(graph_contract_finding(
                "warn",
                "unknown_layer",
                format!("edges:{id}.layer"),
                format!("Edge `{id}` uses unregistered layer `{layer}`."),
            ));
        }
        if !node_ids.contains(&from_node_id) {
            findings.push(graph_contract_finding(
                "blocker",
                "broken_edge_endpoint",
                format!("edges:{id}.from_node_id"),
                format!("Edge `{id}` references missing from_node_id `{from_node_id}`."),
            ));
        }
        if !node_ids.contains(&to_node_id) {
            findings.push(graph_contract_finding(
                "blocker",
                "broken_edge_endpoint",
                format!("edges:{id}.to_node_id"),
                format!("Edge `{id}` references missing to_node_id `{to_node_id}`."),
            ));
        }
        if !evidence_node_id.is_empty() && !node_ids.contains(&evidence_node_id) {
            findings.push(graph_contract_finding(
                "blocker",
                "missing_evidence_node",
                format!("edges:{id}.evidence_node_id"),
                format!("Edge `{id}` references missing evidence_node_id `{evidence_node_id}`."),
            ));
        }
        if !KNOWN_ORDER_KINDS.contains(&order_kind.as_str()) {
            findings.push(graph_contract_finding(
                "warn",
                "unknown_order_kind",
                format!("edges:{id}.order_kind"),
                format!("Edge `{id}` uses order_kind `{order_kind}` outside the core registry."),
            ));
        }
        if !(0.0..=1.0).contains(&confidence) {
            findings.push(graph_contract_finding(
                "warn",
                "invalid_confidence",
                format!("edges:{id}.confidence"),
                format!("Edge `{id}` confidence `{confidence}` is outside [0.0, 1.0]."),
            ));
        }
        validate_payload_json("edge", &id, "payload_json", &payload_json, findings);
    }
    Ok(())
}

fn validate_diagnostic_rows(
    connection: &Connection,
    findings: &mut Vec<GraphContractFinding>,
) -> rusqlite::Result<()> {
    let node_ids = string_set_query(connection, "SELECT id FROM nodes")?;
    let edge_ids = string_set_query(connection, "SELECT id FROM edges")?;
    let mut statement = connection.prepare(
        "SELECT id, layer, target_node_id, target_edge_id, severity, suggested_action_json FROM diagnostics",
    )?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
        ))
    })?;
    for row in rows {
        let (id, layer, target_node_id, target_edge_id, severity, suggested_action_json) = row?;
        if !is_registered_graph_layer(&layer) {
            findings.push(graph_contract_finding(
                "warn",
                "unknown_layer",
                format!("diagnostics:{id}.layer"),
                format!("Diagnostic `{id}` uses unregistered layer `{layer}`."),
            ));
        }
        if !target_node_id.is_empty() && !node_ids.contains(&target_node_id) {
            findings.push(graph_contract_finding(
                "blocker",
                "invalid_diagnostic_target",
                format!("diagnostics:{id}.target_node_id"),
                format!("Diagnostic `{id}` references missing target_node_id `{target_node_id}`."),
            ));
        }
        if !target_edge_id.is_empty() && !edge_ids.contains(&target_edge_id) {
            findings.push(graph_contract_finding(
                "blocker",
                "invalid_diagnostic_target",
                format!("diagnostics:{id}.target_edge_id"),
                format!("Diagnostic `{id}` references missing target_edge_id `{target_edge_id}`."),
            ));
        }
        if !DIAGNOSTIC_SEVERITIES.contains(&severity.as_str()) {
            findings.push(graph_contract_finding(
                "blocker",
                "unknown_diagnostic_severity",
                format!("diagnostics:{id}.severity"),
                format!("Diagnostic `{id}` uses severity `{severity}`."),
            ));
        }
        validate_suggested_action_json(
            "diagnostic",
            &id,
            "suggested_action_json",
            &suggested_action_json,
            findings,
        );
    }
    Ok(())
}

fn string_set_query(connection: &Connection, sql: &str) -> rusqlite::Result<BTreeSet<String>> {
    let mut statement = connection.prepare(sql)?;
    let values: rusqlite::Result<BTreeSet<_>> = statement
        .query_map([], |row| row.get::<_, String>(0))?
        .collect();
    values
}

fn validate_payload_json(
    row_kind: &str,
    id: &str,
    field: &str,
    text: &str,
    findings: &mut Vec<GraphContractFinding>,
) {
    match serde_json::from_str::<Value>(text) {
        Ok(Value::Object(_)) => {}
        Ok(_) => findings.push(graph_contract_finding(
            "blocker",
            "invalid_payload_json",
            format!("{row_kind}s:{id}.{field}"),
            format!("{row_kind} `{id}` field `{field}` must be a JSON object."),
        )),
        Err(error) => findings.push(graph_contract_finding(
            "blocker",
            "invalid_payload_json",
            format!("{row_kind}s:{id}.{field}"),
            format!("{row_kind} `{id}` field `{field}` is invalid JSON: {error}."),
        )),
    }
}

fn validate_suggested_action_json(
    row_kind: &str,
    id: &str,
    field: &str,
    text: &str,
    findings: &mut Vec<GraphContractFinding>,
) {
    match serde_json::from_str::<Value>(text) {
        Ok(Value::Object(_)) => {}
        Ok(_) => findings.push(graph_contract_finding(
            "blocker",
            "invalid_suggested_action_json",
            format!("{row_kind}s:{id}.{field}"),
            format!("{row_kind} `{id}` field `{field}` must be a JSON object."),
        )),
        Err(error) => findings.push(graph_contract_finding(
            "blocker",
            "invalid_suggested_action_json",
            format!("{row_kind}s:{id}.{field}"),
            format!("{row_kind} `{id}` field `{field}` is invalid JSON: {error}."),
        )),
    }
}

fn is_registered_graph_layer(layer: &str) -> bool {
    REGISTERED_GRAPH_LAYERS.contains(&layer) || layer.starts_with("adapter:")
}

fn graph_contract_finding(
    severity: &str,
    rule: &str,
    location: impl Into<String>,
    message: impl Into<String>,
) -> GraphContractFinding {
    GraphContractFinding {
        severity: severity.to_string(),
        rule: rule.to_string(),
        location: location.into(),
        message: message.into(),
    }
}

fn render_graph_contract_text(db: Option<&Path>, findings: &[GraphContractFinding]) -> String {
    let status = if findings.iter().any(|finding| finding.severity == "blocker") {
        "fail"
    } else {
        "pass"
    };
    let mut lines = vec![
        format!("STRUCTURED_ANALYSIS_GRAPH_CONTRACT={status}"),
        format!(
            "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_VERSION={GRAPH_CONTRACT_VERSION}"
        ),
        "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_NECESSARY_SUFFICIENT=yes".to_string(),
        "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_OBJECT_FAMILIES=documents,nodes,edges,diagnostics,projections,operations,metadata".to_string(),
        format!(
            "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_LAYERS={}",
            REGISTERED_GRAPH_LAYERS.join(",")
        ),
        format!(
            "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_DB={}",
            db.map(|path| path.to_string_lossy().to_string())
                .unwrap_or_else(|| "<none>".to_string())
        ),
        format!(
            "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_FINDINGS={}",
            findings.len()
        ),
    ];
    for finding in findings {
        lines.push(format!(
            "STRUCTURED_ANALYSIS_GRAPH_CONTRACT_FINDING={}:{}:{}:{}",
            finding.severity, finding.rule, finding.location, finding.message
        ));
    }
    format!("{}\n", lines.join("\n"))
}

fn render_graph_contract_json(db: Option<&Path>, findings: &[GraphContractFinding]) -> String {
    let status = if findings.iter().any(|finding| finding.severity == "blocker") {
        "fail"
    } else {
        "pass"
    };
    serde_json::to_string_pretty(&json!({
        "status": status,
        "schema": "agent_canon.structured_analysis.graph_contract.v1",
        "contract_version": GRAPH_CONTRACT_VERSION,
        "necessary_sufficient": true,
        "db": db.map(|path| path.to_string_lossy().to_string()),
        "object_families": ["documents", "nodes", "edges", "diagnostics", "projections", "operations", "metadata"],
        "layers": REGISTERED_GRAPH_LAYERS,
        "authority_boundary": "storage and projection validation only; adapter tools keep semantic pass/fail authority",
        "findings": findings.iter().map(|finding| {
            json!({
                "severity": finding.severity,
                "rule": finding.rule,
                "location": finding.location,
                "message": finding.message,
            })
        }).collect::<Vec<_>>(),
    }))
    .expect("graph contract JSON should serialize")
}

fn default_cache_dir(root: &Path, profile: &str) -> Result<PathBuf, String> {
    let base = env::var_os("AGENT_CANON_STRUCTURED_ANALYSIS_HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            env::var_os("HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("."))
                .join(".cache")
                .join("agent-canon")
                .join("structured-analysis")
        });
    let repo_name = root
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("workspace");
    let repo_id = format!(
        "{}-{}",
        sanitize_path_segment(repo_name),
        short_hash(&root.to_string_lossy(), 12)?
    );
    Ok(base
        .join(repo_id)
        .join(format!("{}-current", sanitize_path_segment(profile))))
}

fn ensure_analysis_document(connection: &Connection, root: &Path) -> rusqlite::Result<String> {
    let document_id = "doc:analysis".to_string();
    connection.execute(
        "INSERT OR REPLACE INTO documents(id, path, title, kind, created_at) VALUES (?, ?, 'Structured Analysis Cache', 'analysis', CURRENT_TIMESTAMP)",
        params![document_id, root.to_string_lossy().to_string()],
    )?;
    Ok(document_id)
}

fn import_artifact_layer(
    connection: &Connection,
    document_id: &str,
    files: &[FileRecord],
) -> rusqlite::Result<(usize, usize)> {
    connection.execute("DELETE FROM diagnostics WHERE layer = 'artifact'", [])?;
    connection.execute("DELETE FROM edges WHERE layer = 'artifact'", [])?;
    connection.execute("DELETE FROM nodes WHERE layer = 'artifact'", [])?;

    let directories = directory_paths(files);
    let mut directory_nodes = BTreeMap::new();
    for directory in &directories {
        let node_id = artifact_directory_id(directory);
        let payload_json = json!({
            "path": directory,
            "kind": "directory",
        })
        .to_string();
        connection.execute(
            "INSERT OR REPLACE INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES (?, ?, 'artifact', 'directory', ?, ?, 0, 0, 1.0, ?)",
            params![node_id, document_id, directory_label(directory), directory, payload_json],
        )?;
        directory_nodes.insert(directory.clone(), node_id);
    }

    for directory in directories
        .iter()
        .filter(|directory| directory.as_str() != ".")
    {
        let parent = parent_directory(directory);
        if let (Some(parent_node), Some(child_node)) =
            (directory_nodes.get(&parent), directory_nodes.get(directory))
        {
            insert_artifact_edge(
                connection,
                "contains",
                parent_node,
                child_node,
                "hard",
                json!({"parent": parent, "child": directory, "child_kind": "directory"}),
            )?;
        }
    }

    let mut file_nodes = BTreeMap::new();
    for file in files {
        let node_id = artifact_file_id(&file.path);
        file_nodes.insert(file.path.clone(), node_id.clone());
        let label = file_label(file);
        let text = file_text(file);
        let payload_json = json!({
            "path": file.path,
            "kind": "file",
            "file_kind": file.file_kind,
            "extension": file.extension,
            "byte_len": file.byte_len,
            "content_sha256": file.content_sha256,
            "title": file.title,
            "responsibility": file.responsibility,
            "has_dependency_manifest": file.has_dependency_manifest,
            "is_document": file.is_document,
        })
        .to_string();
        connection.execute(
            "INSERT OR REPLACE INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES (?, ?, 'artifact', ?, ?, ?, 0, 0, 1.0, ?)",
            params![node_id, document_id, file.file_kind, label, text, payload_json],
        )?;

        let parent = parent_directory(&file.path);
        if let Some(parent_node) = directory_nodes.get(&parent) {
            insert_artifact_edge(
                connection,
                "contains",
                parent_node,
                &node_id,
                "hard",
                json!({"parent": parent, "child": file.path, "child_kind": "file"}),
            )?;
        }
        if is_readme_file(&file.path) {
            if let Some(directory_node) = directory_nodes.get(&parent) {
                insert_artifact_edge(
                    connection,
                    "explains_directory",
                    &node_id,
                    directory_node,
                    "",
                    json!({"readme": file.path, "directory": parent}),
                )?;
            }
        }
    }

    import_directory_responsibilities(
        connection,
        document_id,
        files,
        &directory_nodes,
        &file_nodes,
    )?;

    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('artifact_inventory', ?)",
        [json!({
            "file_count": files.len(),
            "directory_count": directories.len(),
            "directory_responsibility_count": directories.len(),
        })
        .to_string()],
    )?;
    Ok((files.len(), directories.len()))
}

fn import_directory_responsibilities(
    connection: &Connection,
    document_id: &str,
    files: &[FileRecord],
    directory_nodes: &BTreeMap<String, String>,
    file_nodes: &BTreeMap<String, String>,
) -> rusqlite::Result<()> {
    for (directory, directory_node_id) in directory_nodes {
        let responsibility = infer_directory_responsibility(directory, files);
        let node_id = artifact_directory_responsibility_id(directory);
        let payload_json = json!({
            "path": &responsibility.path,
            "kind": "directory_responsibility",
            "responsibility": &responsibility.responsibility,
            "basis": &responsibility.basis,
            "readme_path": &responsibility.readme_path,
            "evidence_paths": &responsibility.evidence_paths,
            "descendant_file_count": responsibility.descendant_file_count,
            "declared_responsibility_count": responsibility.declared_responsibility_count,
            "child_kind_counts": &responsibility.child_kind_counts,
            "missing_child_terms": &responsibility.missing_child_terms,
            "derived_from_document_structure": true,
        })
        .to_string();
        connection.execute(
            "INSERT OR REPLACE INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES (?, ?, 'artifact', 'directory_responsibility', ?, ?, 0, 0, 0.8, ?)",
            params![
                &node_id,
                document_id,
                format!("responsibility: {}", directory_label(directory)),
                &responsibility.responsibility,
                payload_json
            ],
        )?;
        insert_artifact_edge(
            connection,
            "has_responsibility",
            directory_node_id,
            &node_id,
            "",
            json!({"directory": directory, "responsibility_node": &node_id}),
        )?;
        for evidence_path in responsibility
            .evidence_paths
            .iter()
            .take(DIRECTORY_RESPONSIBILITY_EVIDENCE_LIMIT)
        {
            if let Some(evidence_node_id) = file_nodes.get(evidence_path) {
                insert_artifact_edge(
                    connection,
                    "supports",
                    evidence_node_id,
                    &node_id,
                    "",
                    json!({
                        "directory": directory,
                        "evidence_path": evidence_path,
                        "responsibility_basis": &responsibility.basis,
                    }),
                )?;
            }
        }
        if !responsibility.missing_child_terms.is_empty() {
            insert_artifact_diagnostic(
                connection,
                DIRECTORY_RESPONSIBILITY_LOW_CHILD_COVERAGE,
                &node_id,
                "warn",
                &format!(
                    "Directory `{}` README responsibility has low coverage of child responsibilities; missing child terms: {}.",
                    directory,
                    responsibility.missing_child_terms.join(", ")
                ),
                directory_responsibility_action_json(&responsibility),
            )?;
        }
    }
    Ok(())
}

fn infer_directory_responsibility(
    directory: &str,
    files: &[FileRecord],
) -> DirectoryResponsibility {
    let descendants = files
        .iter()
        .filter(|file| file_is_under_directory(&file.path, directory))
        .collect::<Vec<_>>();
    let readme = descendants
        .iter()
        .find(|file| parent_directory(&file.path) == directory && is_readme_file(&file.path));
    let child_responsibility_files = descendants
        .iter()
        .filter(|file| !is_readme_file(&file.path) && !file.responsibility.trim().is_empty())
        .copied()
        .collect::<Vec<_>>();
    let child_responsibilities = child_responsibility_files
        .iter()
        .map(|file| file.responsibility.clone())
        .collect::<Vec<_>>();
    let child_kind_counts = directory_child_kind_counts(&descendants);
    let (responsibility, basis, readme_path, mut evidence_paths) = match readme {
        Some(file) if !file.responsibility.trim().is_empty() => (
            file.responsibility.clone(),
            "readme_manifest".to_string(),
            file.path.clone(),
            vec![file.path.clone()],
        ),
        Some(file) if !file.title.trim().is_empty() => (
            file.title.clone(),
            "readme_title".to_string(),
            file.path.clone(),
            vec![file.path.clone()],
        ),
        _ if !child_responsibilities.is_empty() => (
            aggregate_child_responsibilities(&child_responsibilities),
            "descendant_manifest_aggregate".to_string(),
            String::new(),
            Vec::new(),
        ),
        _ => (
            format!("Contains tracked artifacts under `{directory}`."),
            "path_only".to_string(),
            String::new(),
            Vec::new(),
        ),
    };
    evidence_paths.extend(
        child_responsibility_files
            .iter()
            .take(DIRECTORY_RESPONSIBILITY_EVIDENCE_LIMIT)
            .map(|file| file.path.clone()),
    );
    evidence_paths.sort();
    evidence_paths.dedup();
    let missing_child_terms = readme
        .map(|file| {
            missing_directory_child_terms(
                &format!("{} {}", file.title, file.responsibility),
                &child_responsibilities,
            )
        })
        .unwrap_or_default();
    DirectoryResponsibility {
        path: directory.to_string(),
        responsibility,
        basis,
        readme_path,
        evidence_paths,
        descendant_file_count: descendants.len(),
        declared_responsibility_count: child_responsibilities.len(),
        child_kind_counts,
        missing_child_terms,
    }
}

fn file_is_under_directory(path: &str, directory: &str) -> bool {
    if directory == "." {
        return true;
    }
    path.strip_prefix(directory)
        .is_some_and(|suffix| suffix.starts_with('/'))
}

fn directory_child_kind_counts(files: &[&FileRecord]) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for file in files {
        *counts.entry(file.file_kind.clone()).or_insert(0) += 1;
    }
    counts
}

fn aggregate_child_responsibilities(responsibilities: &[String]) -> String {
    let mut unique = Vec::new();
    for responsibility in responsibilities {
        let trimmed = responsibility.trim();
        if trimmed.is_empty() || unique.iter().any(|value: &String| value == trimmed) {
            continue;
        }
        unique.push(trimmed.to_string());
        if unique.len() >= 3 {
            break;
        }
    }
    format!(
        "Aggregates child responsibilities: {}.",
        unique.join("; ").trim_end_matches('.')
    )
}

fn missing_directory_child_terms(
    readme_responsibility_text: &str,
    child_responsibilities: &[String],
) -> Vec<String> {
    if child_responsibilities.len() < 2 {
        return Vec::new();
    }
    let readme_tokens = responsibility_tokens(readme_responsibility_text);
    let child_tokens = child_responsibilities
        .iter()
        .flat_map(|responsibility| responsibility_tokens(responsibility))
        .collect::<BTreeSet<_>>();
    if child_tokens.is_empty()
        || child_tokens
            .iter()
            .any(|token| readme_tokens.contains(token))
    {
        return Vec::new();
    }
    child_tokens
        .into_iter()
        .take(DIRECTORY_RESPONSIBILITY_EVIDENCE_LIMIT)
        .collect()
}

fn responsibility_tokens(text: &str) -> BTreeSet<String> {
    text.split(|character: char| !character.is_ascii_alphanumeric())
        .map(|token| token.to_ascii_lowercase())
        .filter(|token| token.len() >= 4 && !directory_responsibility_stopword(token))
        .collect()
}

fn directory_responsibility_stopword(token: &str) -> bool {
    matches!(
        token,
        "agent"
            | "agentcanon"
            | "canon"
            | "code"
            | "contract"
            | "defines"
            | "directory"
            | "documents"
            | "file"
            | "files"
            | "implements"
            | "records"
            | "repository"
            | "responsibility"
            | "runtime"
            | "shared"
            | "source"
            | "tool"
            | "tools"
            | "usage"
            | "validates"
    )
}

fn insert_artifact_diagnostic(
    connection: &Connection,
    rule: &str,
    target_node_id: &str,
    severity: &str,
    message: &str,
    action: String,
) -> rusqlite::Result<()> {
    connection.execute(
        "INSERT OR REPLACE INTO diagnostics(id, layer, target_node_id, target_edge_id, severity, rule, message, suggested_action_json) VALUES (?, 'artifact', ?, '', ?, ?, ?, ?)",
        params![
            format!("diag:artifact:{}:{}", rule, stable_id_fragment(target_node_id, 20)),
            target_node_id,
            severity,
            rule,
            message,
            action
        ],
    )?;
    Ok(())
}

fn directory_responsibility_action_json(responsibility: &DirectoryResponsibility) -> String {
    json!({
        "action": "align README responsibility with child artifact responsibilities or document why the child scope is intentionally separate",
        "path": responsibility.path,
        "readme_path": responsibility.readme_path,
        "missing_child_terms": responsibility.missing_child_terms,
        "verification_route": "directory_responsibility_verification",
        "verification_question": "Does the directory-level responsibility cover the responsibilities of child documents and code artifacts?",
        "verification_targets": [
            responsibility.path,
            responsibility.readme_path
        ],
        "evidence_required": [
            "directory responsibility node",
            "README dependency manifest or title",
            "child artifact responsibility nodes",
            "structured-analysis rerun"
        ],
        "recursive_verification": {
            "max_depth": 3,
            "closure_condition": "directory responsibility covers child responsibilities, the child scope is explicitly separated, or the warning remains as an accepted unresolved finding",
            "unresolved_leaf_policy": "keep directory_responsibility_low_child_coverage active and route it to the owning directory document",
            "steps": [
                {
                    "id": "derive_child_responsibilities",
                    "route": "structured-analysis",
                    "question": "Which child artifact responsibilities are not represented in the directory responsibility projection?",
                    "if_unresolved": "preserve the artifact diagnostic"
                },
                {
                    "id": "trace_directory_document",
                    "route": "prose-reasoning-graph",
                    "question": "Which README paragraph or dependency manifest line should carry the directory responsibility?",
                    "if_unresolved": "create a document responsibility child finding"
                },
                {
                    "id": "verify_directory_projection",
                    "route": "structured-analysis",
                    "question": "Does rerunning structured-analysis close the directory responsibility warning?",
                    "if_unresolved": "record the remaining gap as warn"
                }
            ]
        }
    })
    .to_string()
}

fn insert_artifact_edge(
    connection: &Connection,
    kind: &str,
    from_node_id: &str,
    to_node_id: &str,
    order_kind: &str,
    payload: Value,
) -> rusqlite::Result<()> {
    connection.execute(
        "INSERT OR REPLACE INTO edges(id, layer, kind, from_node_id, to_node_id, order_kind, confidence, evidence_node_id, payload_json) VALUES (?, 'artifact', ?, ?, ?, ?, 1.0, NULL, ?)",
        params![
            artifact_edge_id(kind, from_node_id, to_node_id),
            kind,
            from_node_id,
            to_node_id,
            order_kind,
            payload.to_string()
        ],
    )?;
    Ok(())
}

fn write_build_artifacts(result: &BuildResult, root: &Path, profile: &str) -> Result<(), String> {
    let payload = json!({
        "status": "pass",
        "root": root.to_string_lossy(),
        "profile": profile,
        "cache_dir": result.cache_dir.to_string_lossy(),
        "report_dir": result.report_dir.to_string_lossy(),
        "db": result.db.to_string_lossy(),
        "diagnostics_db": result.diagnostics_db.to_string_lossy(),
        "document_inventory_json": result.document_inventory_json.to_string_lossy(),
        "document_inventory_markdown": result.document_inventory_markdown.to_string_lossy(),
        "file_count": result.file_count,
        "directory_count": result.directory_count,
        "document_count": result.document_count,
        "document_finding_count": result.document_finding_count,
        "document_historical_record_count": result.document_historical_record_count,
        "warning_count": result.warning_count,
        "blocker_count": result.blocker_count,
        "warn_count": result.warn_count,
        "info_count": result.info_count,
    });
    write_file(
        &result.report_dir.join("structured_analysis_build.json"),
        &serde_json::to_string_pretty(&payload).expect("build JSON should serialize"),
    )?;
    write_file(
        &result
            .report_dir
            .join("exports/structured_analysis_summary.md"),
        &render_build_summary(result, root, profile),
    )
}

fn render_build_summary(result: &BuildResult, root: &Path, profile: &str) -> String {
    format!(
        "# Structured Analysis Build\n\n- root: `{}`\n- profile: `{}`\n- source database: `{}`\n- diagnostics database: `{}`\n- files: `{}`\n- directories: `{}`\n- documents: `{}`\n- document canon findings: `{}`\n- document historical records: `{}`\n- warnings: `{}`\n- blockers: `{}`\n- warns: `{}`\n- infos: `{}`\n",
        root.display(),
        profile,
        result.db.display(),
        result.diagnostics_db.display(),
        result.file_count,
        result.directory_count,
        result.document_count,
        result.document_finding_count,
        result.document_historical_record_count,
        result.warning_count,
        result.blocker_count,
        result.warn_count,
        result.info_count
    )
}

fn initialize_graph_schema(connection: &Connection) -> rusqlite::Result<()> {
    connection.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            layer TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            text TEXT NOT NULL,
            source_start INTEGER NOT NULL,
            source_end INTEGER NOT NULL,
            confidence REAL NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edges (
            id TEXT PRIMARY KEY,
            layer TEXT NOT NULL,
            kind TEXT NOT NULL,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            order_kind TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_node_id TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS diagnostics (
            id TEXT PRIMARY KEY,
            layer TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            target_edge_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            rule TEXT NOT NULL,
            message TEXT NOT NULL,
            suggested_action_json TEXT NOT NULL
        );
        ",
    )
}

fn analysis_document_id(connection: &Connection) -> rusqlite::Result<String> {
    let mut statement =
        connection.prepare("SELECT id FROM documents WHERE id = 'doc:analysis' LIMIT 1")?;
    statement.query_row([], |row| row.get::<_, String>(0))
}

fn import_inventory_payload(
    connection: &Connection,
    document_id: &str,
    payload: &Value,
    inventory_path: &Path,
) -> rusqlite::Result<(usize, usize, usize)> {
    let documents = payload
        .get("documents")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let findings = payload
        .get("findings")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let historical_records = payload
        .get("historical_records")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    connection.execute("DELETE FROM diagnostics WHERE layer = 'document-canon'", [])?;
    connection.execute("DELETE FROM edges WHERE layer = 'document-canon'", [])?;
    connection.execute("DELETE FROM nodes WHERE layer = 'document-canon'", [])?;

    let mut path_to_node = BTreeMap::new();
    let mut document_count = 0;
    for (index, item) in documents.iter().enumerate() {
        let Some(record) = item.as_object() else {
            continue;
        };
        let path = json_string(record.get("path"));
        if path.is_empty() {
            continue;
        }
        let title = json_string(record.get("title"));
        let responsibility = json_string(record.get("responsibility"));
        let node_id = format!("doccanon:document:{}", index + 1);
        let payload_json = json!({
            "path": path,
            "title": title,
            "responsibility": responsibility,
            "has_dependency_manifest": record.get("has_dependency_manifest").and_then(Value::as_bool).unwrap_or(false),
            "inventory_path": inventory_path.to_string_lossy(),
        })
        .to_string();
        connection.execute(
            "INSERT OR REPLACE INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES (?, ?, 'document-canon', 'document_record', ?, ?, 0, 0, 1.0, ?)",
            params![node_id, document_id, if title.is_empty() { &path } else { &title }, if responsibility.is_empty() { &path } else { &responsibility }, payload_json],
        )?;
        path_to_node.insert(path, node_id);
        document_count += 1;
    }

    let finding_count = import_document_canon_records(
        connection,
        document_id,
        inventory_path,
        &path_to_node,
        &findings,
        DocumentCanonRecordImport {
            node_kind: "finding",
            node_id_prefix: "doccanon:finding",
            target_edge_prefix: "doccanon:target",
            canonical_edge_prefix: "doccanon:canonical",
            emit_diagnostics: true,
        },
    )?;
    let historical_record_count = import_document_canon_records(
        connection,
        document_id,
        inventory_path,
        &path_to_node,
        &historical_records,
        DocumentCanonRecordImport {
            node_kind: "historical_record",
            node_id_prefix: "doccanon:historical",
            target_edge_prefix: "doccanon:historical-target",
            canonical_edge_prefix: "doccanon:historical-canonical",
            emit_diagnostics: false,
        },
    )?;
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES ('document_canon_inventory', ?)",
        [json!({
            "inventory_path": inventory_path.to_string_lossy(),
            "document_count": document_count,
            "finding_count": finding_count,
            "historical_record_count": historical_record_count,
        })
        .to_string()],
    )?;
    Ok((document_count, finding_count, historical_record_count))
}

struct DocumentCanonRecordImport<'a> {
    node_kind: &'a str,
    node_id_prefix: &'a str,
    target_edge_prefix: &'a str,
    canonical_edge_prefix: &'a str,
    emit_diagnostics: bool,
}

fn import_document_canon_records(
    connection: &Connection,
    document_id: &str,
    inventory_path: &Path,
    path_to_node: &BTreeMap<String, String>,
    items: &[Value],
    config: DocumentCanonRecordImport<'_>,
) -> rusqlite::Result<usize> {
    let mut imported_count = 0;
    for (index, item) in items.iter().enumerate() {
        let Some(finding) = item.as_object() else {
            continue;
        };
        let path = json_string(finding.get("path"));
        let kind = json_string(finding.get("kind"));
        let canonical_path = json_string(finding.get("canonical_path"));
        let action = json_string(finding.get("action"));
        let reason = json_string(finding.get("reason"));
        let node_id = format!("{}:{}", config.node_id_prefix, index + 1);
        let message = format!("{kind}: `{path}` -> `{canonical_path}`. {reason}");
        let payload_json = json!({
            "path": path,
            "kind": kind,
            "canonical_path": canonical_path,
            "action": action,
            "reason": reason,
            "inventory_path": inventory_path.to_string_lossy(),
        })
        .to_string();
        connection.execute(
            "INSERT OR REPLACE INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES (?, ?, 'document-canon', ?, ?, ?, 0, 0, 0.8, ?)",
            params![node_id, document_id, config.node_kind, kind, message, payload_json],
        )?;
        if let Some(target_node) = path_to_node.get(&path) {
            connection.execute(
                "INSERT OR REPLACE INTO edges(id, layer, kind, from_node_id, to_node_id, order_kind, confidence, evidence_node_id, payload_json) VALUES (?, 'document-canon', 'targets_document', ?, ?, '', 1.0, NULL, ?)",
                params![format!("{}:{}", config.target_edge_prefix, index + 1), node_id, target_node, json!({"path": path}).to_string()],
            )?;
        }
        if let Some(canonical_node) = path_to_node.get(&canonical_path) {
            connection.execute(
                "INSERT OR REPLACE INTO edges(id, layer, kind, from_node_id, to_node_id, order_kind, confidence, evidence_node_id, payload_json) VALUES (?, 'document-canon', 'references_canonical', ?, ?, '', 1.0, NULL, ?)",
                params![format!("{}:{}", config.canonical_edge_prefix, index + 1), node_id, canonical_node, json!({"canonical_path": canonical_path}).to_string()],
            )?;
        }
        if config.emit_diagnostics {
            connection.execute(
                "INSERT OR REPLACE INTO diagnostics(id, layer, target_node_id, target_edge_id, severity, rule, message, suggested_action_json) VALUES (?, 'document-canon', ?, '', ?, ?, ?, ?)",
                params![
                    format!("diag:document-canon:{}", index + 1),
                    node_id,
                    document_canon_severity(&kind),
                    kind,
                    message,
                    document_canon_suggested_action_json(&kind, &action, &path, &canonical_path, &reason)
                ],
            )?;
        }
        imported_count += 1;
    }
    Ok(imported_count)
}

fn json_string(value: Option<&Value>) -> String {
    value.and_then(Value::as_str).unwrap_or("").to_string()
}

fn document_canon_severity(kind: &str) -> &'static str {
    match kind {
        "missing_dependency_manifest" | "broken_dependency_target" => "blocker",
        "duplicate_heading_candidate"
        | "stale_name_candidate"
        | "missing_reverse_edge"
        | DOCUMENT_RESPONSIBILITY_GAP => "warn",
        _ => "info",
    }
}

fn document_canon_suggested_action_json(
    kind: &str,
    action: &str,
    path: &str,
    canonical_path: &str,
    reason: &str,
) -> String {
    if kind == DOCUMENT_RESPONSIBILITY_GAP {
        return json!({
            "action": action,
            "path": path,
            "canonical_path": canonical_path,
            "reason": reason,
            "verification_route": "document_responsibility_verification",
            "verification_question": "Does the downstream document cover the upstream design responsibility declared by its dependency manifest?",
            "verification_targets": [path, canonical_path],
            "evidence_required": [
                "upstream coverage rule",
                "downstream document wording",
                "dependency header edge"
            ],
            "recursive_verification": {
                "max_depth": 3,
                "closure_condition": "every declared coverage group is covered, explicitly out of scope, or recorded as an unresolved document-canon finding",
                "unresolved_leaf_policy": "keep document_responsibility_gap active and route the leaf to the owning document",
                "steps": [
                    {
                        "id": "expand_coverage_rule",
                        "route": "document-canon",
                        "question": "Which upstream coverage groups are missing from the downstream document?",
                        "if_unresolved": "preserve the responsibility gap finding"
                    },
                    {
                        "id": "trace_downstream_claim",
                        "route": "prose-reasoning-graph",
                        "question": "Which downstream paragraph, sentence, or graph node should carry the missing responsibility?",
                        "if_unresolved": "create a child document-canon finding for the target document"
                    },
                    {
                        "id": "verify_rewritten_contract",
                        "route": "structured-analysis",
                        "question": "Does rerunning structured-analysis close the coverage gap without introducing a new graph or document responsibility gap?",
                        "if_unresolved": "record the remaining gap as blocker or warn"
                    }
                ]
            }
        })
        .to_string();
    }
    json!({
        "action": action,
        "path": path,
        "canonical_path": canonical_path,
        "reason": reason
    })
    .to_string()
}

fn file_kind(path: &Path) -> String {
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match extension.as_str() {
        "md" | "rst" | "txt" => "document",
        "py" => "python",
        "rs" => "rust",
        "sh" | "bash" | "zsh" => "shell",
        "c" | "cc" | "cpp" | "cxx" | "h" | "hh" | "hpp" | "hxx" => "cpp",
        "toml" | "yaml" | "yml" | "json" | "jsonl" => "config",
        "cmake" | "mk" => "build",
        _ => match path.file_name().and_then(|name| name.to_str()) {
            Some("CMakeLists.txt" | "Makefile") => "build",
            Some("Dockerfile") => "environment",
            _ => "file",
        },
    }
    .to_string()
}

fn directory_paths(files: &[FileRecord]) -> Vec<String> {
    let mut directories = BTreeSet::new();
    directories.insert(".".to_string());
    for file in files {
        let mut current = Path::new(&file.path).parent();
        while let Some(directory) = current {
            let relative = relative_path_string(directory);
            if relative == "." {
                break;
            }
            directories.insert(relative);
            current = directory.parent();
        }
    }
    directories.into_iter().collect()
}

fn parent_directory(relative_path: &str) -> String {
    Path::new(relative_path)
        .parent()
        .map(relative_path_string)
        .unwrap_or_else(|| ".".to_string())
}

fn relative_path_string(path: &Path) -> String {
    let value = path.to_string_lossy().replace('\\', "/");
    if value.is_empty() {
        ".".to_string()
    } else {
        value
    }
}

fn directory_label(path: &str) -> String {
    if path == "." {
        return "/".to_string();
    }
    Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or(path)
        .to_string()
}

fn file_label(file: &FileRecord) -> String {
    if file.title.is_empty() {
        file.path.clone()
    } else {
        format!("{} ({})", file.title, file.path)
    }
}

fn file_text(file: &FileRecord) -> String {
    if !file.responsibility.is_empty() {
        return file.responsibility.clone();
    }
    if !file.title.is_empty() {
        return file.title.clone();
    }
    file.path.clone()
}

fn is_readme_file(path: &str) -> bool {
    Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .map(|name| name.eq_ignore_ascii_case("README.md"))
        .unwrap_or(false)
}

fn artifact_directory_id(path: &str) -> String {
    if path == "." {
        return "artifact:directory:root".to_string();
    }
    format!("artifact:directory:{}", stable_id_fragment(path, 20))
}

fn artifact_directory_responsibility_id(path: &str) -> String {
    if path == "." {
        return "artifact:directory-responsibility:root".to_string();
    }
    format!(
        "artifact:directory-responsibility:{}",
        stable_id_fragment(path, 20)
    )
}

fn artifact_file_id(path: &str) -> String {
    format!("artifact:file:{}", stable_id_fragment(path, 20))
}

fn artifact_edge_id(kind: &str, from_node_id: &str, to_node_id: &str) -> String {
    format!(
        "artifact:edge:{}:{}",
        kind,
        stable_id_fragment(&format!("{from_node_id}\t{to_node_id}"), 20)
    )
}

fn sanitize_path_segment(value: &str) -> String {
    let sanitized: String = value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '_') {
                character
            } else {
                '_'
            }
        })
        .collect();
    let trimmed = sanitized.trim_matches('_');
    if trimmed.is_empty() {
        "workspace".to_string()
    } else {
        trimmed.to_string()
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn short_hash(value: &str, length: usize) -> Result<String, String> {
    let hash = sha256_hex(value.as_bytes());
    if length > hash.len() {
        return Err(format!("hash length {length} exceeds sha256 length"));
    }
    Ok(hash[..length].to_string())
}

fn stable_id_fragment(value: &str, length: usize) -> String {
    short_hash(value, length).unwrap_or_else(|_| value.replace(['/', '\\', ':', '\t'], "_"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn duplicate_titles_are_reported() {
        let root = test_root("structured-analysis-duplicate");
        write_fixture(&root, "documents/a.md", "# Duplicate\n\nBody.");
        write_fixture(&root, "documents/b.md", "# Duplicate\n\nBody.");
        let report = build_report(&root).expect("report");
        assert!(report
            .findings
            .iter()
            .any(|finding| finding.kind == "duplicate_heading_candidate"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn generated_reports_are_excluded_from_default_document_inventory() {
        let root = test_root("structured-analysis-skip-reports");
        write_fixture(&root, "documents/missing.md", "# Missing\n\nBody.");
        write_fixture(&root, "reports/run-output.md", "# Generated\n\nBody.");

        let report = build_report(&root).expect("report");
        let paths = report
            .documents
            .iter()
            .map(|record| record.path.as_str())
            .collect::<BTreeSet<_>>();

        assert!(paths.contains("documents/missing.md"));
        assert!(!paths.contains("reports/run-output.md"));
        assert!(!report
            .findings
            .iter()
            .any(|finding| finding.kind == "generated_report"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn closed_issue_records_are_historical_not_active_findings() {
        let root = test_root("structured-analysis-closed-issue-history");
        write_fixture(
            &root,
            "issues/README.md",
            "<!--\n@dependency-start\nresponsibility Documents local issue storage.\nupstream design ../README.md repo root\n@dependency-end\n-->\n\n# Issues\n",
        );
        write_fixture(
            &root,
            "issues/closed/AC-20260517-legacy-tool-directory-regression.md",
            "<!--\n@dependency-start\nresponsibility Records a closed legacy tool directory issue.\nupstream design ../README.md issue storage\n@dependency-end\n-->\n\n# Closed Issue\n",
        );

        let report = build_report(&root).expect("report");

        assert!(!report.findings.iter().any(|finding| {
            finding.path == "issues/closed/AC-20260517-legacy-tool-directory-regression.md"
        }));
        assert!(report.historical_records.iter().any(|record| {
            record.kind == "closed_issue_record"
                && record.path == "issues/closed/AC-20260517-legacy-tool-directory-regression.md"
        }));
        assert!(report.historical_records.iter().any(|record| {
            record.kind == "stale_name_candidate"
                && record.path == "issues/closed/AC-20260517-legacy-tool-directory-regression.md"
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn dsl_upstream_without_design_trace_is_responsibility_gap() {
        let root = test_root("structured-analysis-dsl-trace-missing");
        write_fixture(
            &root,
            "documents/prose-reasoning-graph/dsl-spec.md",
            "<!--\n@dependency-start\nresponsibility Defines fixture DSL.\ncoverage dsl_design_trace requires source-truth anchor|source truth|source span; lower graph|lower text unit; typed relation; projection view|derived projection|reader-state|macro-claim\n@dependency-end\n-->\n\n# DSL Spec\n",
        );
        write_fixture(
            &root,
            "documents/tools/sample_tool.md",
            "<!--\n@dependency-start\nresponsibility Documents sample_tool.py usage and contract.\nupstream design ../prose-reasoning-graph/dsl-spec.md normative graph and DSL contract\nupstream implementation ../../tools/sample_tool.py implements the tool.\n@dependency-end\n-->\n\n# sample_tool.py\n\n## Tool Design\n\nThe graph pipeline connects ingest, analyze, project, and handoff stages.\n",
        );

        let report = build_report(&root).expect("report");
        let reasons = finding_reasons(&report, DOCUMENT_RESPONSIBILITY_GAP);
        assert!(reasons.iter().any(|reason| {
            reason.contains("missing_responsibility_coverage=`dsl_design_trace`")
                && reason.contains("upstream_design=`../prose-reasoning-graph/dsl-spec.md normative graph and DSL contract`")
        }));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn dsl_trace_can_be_satisfied_by_responsibility_coverage() {
        let root = test_root("structured-analysis-dsl-trace-satisfied");
        write_fixture(
            &root,
            "documents/prose-reasoning-graph/dsl-spec.md",
            "<!--\n@dependency-start\nresponsibility Defines fixture DSL.\ncoverage dsl_design_trace requires source-truth anchor|source truth|source span; lower graph|lower text unit; typed relation; projection view|derived projection|reader-state|macro-claim\ncoverage graph_format_trace requires node record|nodes table; edge record|edges table; payload_json|payload json\n@dependency-end\n-->\n\n# DSL Spec\n",
        );
        write_fixture(
            &root,
            "documents/tools/sample_tool.md",
            "<!--\n@dependency-start\nresponsibility Documents sample_tool.py usage and contract.\nupstream design ../prose-reasoning-graph/dsl-spec.md normative graph and DSL contract\nupstream implementation ../../tools/sample_tool.py implements the tool.\n@dependency-end\n-->\n\n# sample_tool.py\n\nThe contract keeps source-truth anchors in lower text units, records typed relations in the lower graph, and derives projection views for macro claims and reader state. The graph format uses a node record, an edge record, and payload_json for structured fields.\n",
        );

        let report = build_report(&root).expect("report");
        let reasons = finding_reasons(&report, DOCUMENT_RESPONSIBILITY_GAP);
        assert!(!reasons
            .iter()
            .any(|reason| reason.contains("missing_responsibility_coverage=`dsl_design_trace`")));
        assert!(!reasons
            .iter()
            .any(|reason| reason.contains("missing_responsibility_coverage=`graph_format_trace`")));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn upstream_coverage_rule_reports_graph_format_gap() {
        let root = test_root("structured-analysis-graph-format-missing");
        write_fixture(
            &root,
            "documents/prose-reasoning-graph/dsl-spec.md",
            "<!--\n@dependency-start\nresponsibility Defines fixture DSL.\ncoverage graph_format_trace requires node record|nodes table; edge record|edges table; payload_json|payload json\n@dependency-end\n-->\n\n# DSL Spec\n",
        );
        write_fixture(
            &root,
            "documents/tools/sample_tool.md",
            "<!--\n@dependency-start\nresponsibility Documents sample_tool.py usage and contract.\nupstream design ../prose-reasoning-graph/dsl-spec.md normative graph and DSL contract\n@dependency-end\n-->\n\n# sample_tool.py\n\nThe contract explains source-truth anchors and typed relations, but it does not define the storage shape.\n",
        );

        let report = build_report(&root).expect("report");
        let reasons = finding_reasons(&report, DOCUMENT_RESPONSIBILITY_GAP);
        assert!(reasons.iter().any(|reason| {
            reason.contains("missing_responsibility_coverage=`graph_format_trace`")
                && reason.contains("missing_terms=`node record|nodes table; edge record|edges table; payload_json|payload json`")
        }));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn tool_document_path_alone_does_not_create_design_gap() {
        let root = test_root("structured-analysis-tool-path-alone");
        write_fixture(
            &root,
            "documents/tools/sample_tool.md",
            "<!--\n@dependency-start\nresponsibility Documents sample_tool.py operator usage.\nupstream implementation ../../tools/sample_tool.py implements the tool.\n@dependency-end\n-->\n\n# sample_tool.py\n\nThis document explains command usage.\n",
        );

        let report = build_report(&root).expect("report");
        let reasons = finding_reasons(&report, DOCUMENT_RESPONSIBILITY_GAP);
        assert!(reasons.is_empty());

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn inventory_import_materializes_document_canon_diagnostics() {
        let root = test_root("structured-analysis-import");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let inventory = json!({
            "documents": [
                {"path": "documents/a.md", "title": "A", "responsibility": "Documents A.", "has_dependency_manifest": true},
                {"path": "documents/b.md", "title": "A", "responsibility": "Documents B.", "has_dependency_manifest": true}
            ],
            "findings": [
                {"path": "documents/b.md", "kind": "duplicate_heading_candidate", "canonical_path": "documents/a.md", "action": "merge", "reason": "shares H1 title"}
            ]
        });
        let connection = Connection::open(&db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        let imported = import_inventory_payload(
            &connection,
            "doc:analysis",
            &inventory,
            &root.join("inventory.json"),
        )
        .expect("import");
        assert_eq!(imported, (2, 1, 0));
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM diagnostics WHERE layer = 'document-canon'",
                [],
                |row| row.get(0),
            )
            .expect("count");
        assert_eq!(count, 1);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn responsibility_gap_diagnostic_includes_recursive_verification_route() {
        let root = test_root("structured-analysis-responsibility-route");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let inventory = json!({
            "documents": [
                {"path": "documents/design.md", "title": "Design", "responsibility": "Defines graph format.", "has_dependency_manifest": true},
                {"path": "documents/tool.md", "title": "Tool", "responsibility": "Documents tool usage.", "has_dependency_manifest": true}
            ],
            "findings": [
                {
                    "path": "documents/tool.md",
                    "kind": DOCUMENT_RESPONSIBILITY_GAP,
                    "canonical_path": "documents/design.md",
                    "action": "cover_upstream_design_rule",
                    "reason": "missing_responsibility_coverage=`graph_format_trace`"
                }
            ]
        });
        let connection = Connection::open(&db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        import_inventory_payload(
            &connection,
            "doc:analysis",
            &inventory,
            &root.join("inventory.json"),
        )
        .expect("import");

        let action_json: String = connection
            .query_row(
                "SELECT suggested_action_json FROM diagnostics WHERE rule = ?",
                [DOCUMENT_RESPONSIBILITY_GAP],
                |row| row.get(0),
            )
            .expect("suggested action");
        let payload: Value = serde_json::from_str(&action_json).expect("action json");
        assert_eq!(
            payload
                .get("verification_route")
                .and_then(Value::as_str)
                .unwrap_or(""),
            "document_responsibility_verification"
        );
        let steps = payload
            .get("recursive_verification")
            .and_then(|value| value.get("steps"))
            .and_then(Value::as_array)
            .expect("recursive steps");
        assert!(steps.iter().any(|step| {
            step.get("id")
                .and_then(Value::as_str)
                .is_some_and(|id| id == "expand_coverage_rule")
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn analyze_writes_separate_warning_database() {
        let root = test_root("structured-analysis-analyze");
        fs::create_dir_all(&root).expect("mkdir");
        let source_db = root.join("prose_graph.sqlite");
        let diagnostics_db = root.join("diagnostics.sqlite");
        let inventory = json!({
            "documents": [
                {"path": "documents/a.md", "title": "A", "responsibility": "Documents A.", "has_dependency_manifest": true},
                {"path": "documents/b.md", "title": "A", "responsibility": "Documents B.", "has_dependency_manifest": true}
            ],
            "findings": [
                {"path": "documents/b.md", "kind": "duplicate_heading_candidate", "canonical_path": "documents/a.md", "action": "merge", "reason": "shares H1 title"}
            ]
        });
        let connection = Connection::open(&source_db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        let document_id = ensure_analysis_document(&connection, &root).expect("analysis document");
        import_inventory_payload(
            &connection,
            &document_id,
            &inventory,
            &root.join("inventory.json"),
        )
        .expect("import");

        let summary =
            analyze_structured_analysis_db(&source_db, &diagnostics_db, "test").expect("analyze");
        assert_eq!(summary.warning_count, 1);
        assert_eq!(summary.warn_count, 1);
        let diagnostics = Connection::open(&diagnostics_db).expect("diagnostics db");
        let target_path: String = diagnostics
            .query_row(
                "SELECT target_path FROM warnings WHERE rule = 'duplicate_heading_candidate'",
                [],
                |row| row.get(0),
            )
            .expect("warning target path");
        assert_eq!(target_path, "documents/b.md");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn build_cache_materializes_artifact_layer() {
        let root = test_root("structured-analysis-build-root");
        let out_dir = test_root("structured-analysis-build-out");
        write_fixture(
            &root,
            "documents/README.md",
            "# Fixture Documents\n\n<!--\n@dependency-start\nresponsibility Documents fixture files.\nupstream design ../README.md fixture root\n@dependency-end\n-->\n",
        );
        write_fixture(
            &root,
            "src/main.rs",
            "// @dependency-start\n// responsibility Implements fixture Rust code.\n// upstream design ../documents/README.md fixture docs\n// @dependency-end\nfn main() {}\n",
        );

        let result = build_structured_analysis_cache(&BuildArgs {
            root: root.clone(),
            profile: "test".to_string(),
            out_dir: Some(out_dir.clone()),
        })
        .expect("build cache");
        assert_eq!(result.file_count, 2);
        assert!(result.directory_count >= 3);
        assert!(result.db.is_file());
        assert!(result.diagnostics_db.is_file());
        assert!(result.document_inventory_json.is_file());
        assert_eq!(result.report_dir, out_dir);
        assert!(result.document_inventory_json.starts_with(&out_dir));
        assert!(!result.db.starts_with(&out_dir));
        assert!(out_dir.join("structured_analysis_build.json").is_file());
        assert_eq!(result.warning_count, result.document_finding_count);

        let connection = Connection::open(&result.db).expect("db");
        let rust_text: String = connection
            .query_row(
                "SELECT text FROM nodes WHERE layer = 'artifact' AND kind = 'rust' AND label = 'src/main.rs'",
                [],
                |row| row.get(0),
            )
            .expect("rust artifact");
        assert_eq!(rust_text, "Implements fixture Rust code.");
        let readme_edges: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM edges WHERE layer = 'artifact' AND kind = 'explains_directory'",
                [],
                |row| row.get(0),
            )
            .expect("readme edge count");
        assert_eq!(readme_edges, 1);
        let directory_responsibility: String = connection
            .query_row(
                "SELECT text FROM nodes WHERE layer = 'artifact' AND kind = 'directory_responsibility' AND json_extract(payload_json, '$.path') = 'documents'",
                [],
                |row| row.get(0),
            )
            .expect("documents directory responsibility");
        assert_eq!(directory_responsibility, "Documents fixture files.");
        let responsibility_edges: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM edges WHERE layer = 'artifact' AND kind = 'has_responsibility'",
                [],
                |row| row.get(0),
            )
            .expect("responsibility edge count");
        assert!(responsibility_edges >= result.directory_count as i64);

        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(out_dir);
        let _ = fs::remove_dir_all(result.cache_dir);
    }

    #[test]
    fn directory_responsibility_gap_is_reported_from_child_artifacts() {
        let root = test_root("structured-analysis-directory-responsibility-gap");
        let out_dir = test_root("structured-analysis-directory-responsibility-out");
        write_fixture(
            &root,
            "docs/README.md",
            "# Docs\n\n<!--\n@dependency-start\nresponsibility Documents the docs index.\n@dependency-end\n-->\n",
        );
        write_fixture(
            &root,
            "docs/solver.md",
            "# Solver\n\n<!--\n@dependency-start\nresponsibility Defines solver API and convergence contracts.\n@dependency-end\n-->\n",
        );
        write_fixture(
            &root,
            "docs/runtime.md",
            "# Runtime\n\n<!--\n@dependency-start\nresponsibility Documents runtime cache and bootstrap behavior.\n@dependency-end\n-->\n",
        );

        let result = build_structured_analysis_cache(&BuildArgs {
            root: root.clone(),
            profile: "test".to_string(),
            out_dir: Some(out_dir.clone()),
        })
        .expect("build cache");

        let connection = Connection::open(&result.db).expect("db");
        let action_json: String = connection
            .query_row(
                "SELECT suggested_action_json FROM diagnostics WHERE layer = 'artifact' AND rule = ?",
                [DIRECTORY_RESPONSIBILITY_LOW_CHILD_COVERAGE],
                |row| row.get(0),
            )
            .expect("directory responsibility diagnostic");
        let action: Value = serde_json::from_str(&action_json).expect("action json");
        assert_eq!(
            action
                .get("verification_route")
                .and_then(Value::as_str)
                .unwrap_or(""),
            "directory_responsibility_verification"
        );
        let warning_summary =
            analyze_structured_analysis_db(&result.db, &result.diagnostics_db, "test")
                .expect("analyze");
        assert!(warning_summary.warn_count >= 1);

        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(out_dir);
        let _ = fs::remove_dir_all(result.cache_dir);
    }

    #[test]
    fn graph_contract_text_exposes_core_contract() {
        let text = render_graph_contract_text(None, &[]);
        assert!(text.contains("STRUCTURED_ANALYSIS_GRAPH_CONTRACT=pass"));
        assert!(text.contains("STRUCTURED_ANALYSIS_GRAPH_CONTRACT_NECESSARY_SUFFICIENT=yes"));
        assert!(text.contains("documents,nodes,edges,diagnostics,projections,operations,metadata"));
    }

    #[test]
    fn graph_contract_accepts_build_cache_schema() {
        let root = test_root("structured-analysis-graph-contract-root");
        let out_dir = test_root("structured-analysis-graph-contract-out");
        write_fixture(
            &root,
            "README.md",
            "# Fixture\n\n<!--\n@dependency-start\nresponsibility Documents fixture root.\n@dependency-end\n-->\n",
        );
        write_fixture(
            &root,
            "src/main.rs",
            "// @dependency-start\n// responsibility Implements fixture Rust code.\n// upstream design ../README.md fixture root\n// @dependency-end\nfn main() {}\n",
        );

        let result = build_structured_analysis_cache(&BuildArgs {
            root: root.clone(),
            profile: "test".to_string(),
            out_dir: Some(out_dir.clone()),
        })
        .expect("build cache");
        let connection = Connection::open(&result.db).expect("db");
        let findings = validate_graph_contract(&connection).expect("contract validation");
        assert!(findings.iter().all(|finding| finding.severity != "blocker"));

        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(out_dir);
        let _ = fs::remove_dir_all(result.cache_dir);
    }

    #[test]
    fn graph_contract_reports_broken_edge_endpoint() {
        let root = test_root("structured-analysis-broken-edge");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let connection = Connection::open(&db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        let document_id = ensure_analysis_document(&connection, &root).expect("analysis document");
        connection
            .execute(
                "INSERT INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES ('node:a', ?, 'artifact', 'file', 'a', 'a', 0, 0, 1.0, '{}')",
                [document_id],
            )
            .expect("node");
        connection
            .execute(
                "INSERT INTO edges(id, layer, kind, from_node_id, to_node_id, order_kind, confidence, evidence_node_id, payload_json) VALUES ('edge:broken', 'artifact', 'contains', 'node:a', 'node:missing', 'hard_before', 1.0, NULL, '{}')",
                [],
            )
            .expect("edge");

        let findings = validate_graph_contract(&connection).expect("contract validation");
        assert!(findings.iter().any(|finding| {
            finding.severity == "blocker" && finding.rule == "broken_edge_endpoint"
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn graph_contract_reports_invalid_payload_json() {
        let root = test_root("structured-analysis-invalid-payload");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let connection = Connection::open(&db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        let document_id = ensure_analysis_document(&connection, &root).expect("analysis document");
        connection
            .execute(
                "INSERT INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES ('node:a', ?, 'artifact', 'file', 'a', 'a', 0, 0, 1.0, '{')",
                [document_id],
            )
            .expect("node");

        let findings = validate_graph_contract(&connection).expect("contract validation");
        assert!(findings.iter().any(|finding| {
            finding.severity == "blocker" && finding.rule == "invalid_payload_json"
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn graph_contract_reports_missing_required_table() {
        let root = test_root("structured-analysis-missing-table");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let connection = Connection::open(&db).expect("db");

        let findings = validate_graph_contract(&connection).expect("contract validation");
        assert!(findings.iter().any(|finding| {
            finding.severity == "blocker" && finding.rule == "missing_required_table"
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn graph_contract_reports_missing_required_column() {
        let root = test_root("structured-analysis-missing-column");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let connection = Connection::open(&db).expect("db");
        connection
            .execute_batch(
                "
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE nodes (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    layer TEXT NOT NULL
                );
                CREATE TABLE edges (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    order_kind TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_node_id TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE diagnostics (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    target_edge_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    rule TEXT NOT NULL,
                    message TEXT NOT NULL,
                    suggested_action_json TEXT NOT NULL
                );
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                ",
            )
            .expect("partial schema");

        let findings = validate_graph_contract(&connection).expect("contract validation");
        assert!(findings.iter().any(|finding| {
            finding.severity == "blocker"
                && finding.rule == "missing_required_column"
                && finding.message.contains("payload_json")
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn graph_contract_reports_non_blocker_rules() {
        let root = test_root("structured-analysis-non-blocker-rules");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let connection = Connection::open(&db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        let document_id = ensure_analysis_document(&connection, &root).expect("analysis document");
        connection
            .execute(
                "INSERT INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES ('node:a', ?, 'adapter:fixture', 'file', 'a', 'a', 0, 0, 1.2, '{}')",
                [document_id],
            )
            .expect("node");
        connection
            .execute(
                "INSERT INTO edges(id, layer, kind, from_node_id, to_node_id, order_kind, confidence, evidence_node_id, payload_json) VALUES ('edge:a', 'artifact', 'contains', 'node:a', 'node:a', 'weird', 1.0, NULL, '{}')",
                [],
            )
            .expect("edge");
        connection
            .execute(
                "INSERT INTO diagnostics(id, layer, target_node_id, target_edge_id, severity, rule, message, suggested_action_json) VALUES ('diag:a', 'artifact', 'node:a', '', 'debug', 'fixture', 'fixture', '{}')",
                [],
            )
            .expect("diagnostic");

        let findings = validate_graph_contract(&connection).expect("contract validation");
        assert!(findings
            .iter()
            .any(|finding| finding.rule == "invalid_confidence"));
        assert!(findings
            .iter()
            .any(|finding| finding.rule == "unknown_order_kind"));
        assert!(findings.iter().any(|finding| {
            finding.severity == "blocker" && finding.rule == "unknown_diagnostic_severity"
        }));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn graph_contract_json_output_is_parseable() {
        let finding = graph_contract_finding(
            "blocker",
            "missing_required_table",
            "table:nodes",
            "Graph contract table `nodes` is missing.",
        );
        let json_text = render_graph_contract_json(None, &[finding]);
        let payload: Value = serde_json::from_str(&json_text).expect("json output");
        assert_eq!(
            payload.get("contract_version").and_then(Value::as_str),
            Some(GRAPH_CONTRACT_VERSION)
        );
        let findings = payload
            .get("findings")
            .and_then(Value::as_array)
            .expect("findings");
        assert_eq!(findings.len(), 1);
        assert_eq!(
            findings[0].get("location").and_then(Value::as_str),
            Some("table:nodes")
        );
    }

    #[test]
    fn graph_contract_cli_rejects_invalid_format_argument() {
        let args = vec!["--format".to_string(), "yaml".to_string()];
        assert_eq!(run_graph_contract(&args), 2);
    }

    #[test]
    fn graph_contract_cli_returns_failure_on_blocker() {
        let root = test_root("structured-analysis-cli-blocker");
        fs::create_dir_all(&root).expect("mkdir");
        let db = root.join("graph.sqlite");
        let connection = Connection::open(&db).expect("db");
        initialize_graph_schema(&connection).expect("schema");
        let document_id = ensure_analysis_document(&connection, &root).expect("analysis document");
        connection
            .execute(
                "INSERT INTO nodes(id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json) VALUES ('node:a', ?, 'artifact', 'file', 'a', 'a', 0, 0, 1.0, '{}')",
                [document_id],
            )
            .expect("node");
        connection
            .execute(
                "INSERT INTO edges(id, layer, kind, from_node_id, to_node_id, order_kind, confidence, evidence_node_id, payload_json) VALUES ('edge:broken', 'artifact', 'contains', 'node:a', 'node:missing', 'hard_before', 1.0, NULL, '{}')",
                [],
            )
            .expect("edge");
        let args = vec![
            "--db".to_string(),
            db.to_string_lossy().to_string(),
            "--format".to_string(),
            "text".to_string(),
        ];
        assert_eq!(run_graph_contract(&args), 1);
        let _ = fs::remove_dir_all(root);
    }

    fn test_root(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        std::env::temp_dir().join(format!("{name}-{suffix}"))
    }

    fn write_fixture(root: &Path, relative: &str, text: &str) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().expect("parent")).expect("mkdir");
        fs::write(path, text).expect("write");
    }

    fn finding_reasons(report: &InventoryReport, kind: &str) -> Vec<String> {
        report
            .findings
            .iter()
            .filter(|finding| finding.kind == kind)
            .map(|finding| finding.reason.clone())
            .collect()
    }
}
