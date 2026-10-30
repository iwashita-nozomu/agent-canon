// @dependency-start
// contract implementation
// responsibility Checks algorithm InitializeConfig/SolveConfig ownership and hidden runtime defaults.
// upstream design ../../../../../documents/design/jax_util/algorithm_module_contract.md config contract
// upstream implementation python_ast.rs shares RustPython AST and source-span helpers
// upstream implementation python_algorithm_contract.rs shares native path and glob selection
// downstream implementation main.rs exposes check-algorithm-config-partition
// downstream implementation ../../../../../tests/agent_tools/test_check_algorithm_config_partition.py checks the retired Python tool's behavior oracles through the native CLI
// @dependency-end

use crate::python_ast::{line_at_offset, normalize_python_newlines};
use rustpython_ast::{Ranged, Visitor};
use rustpython_parser::{Parse, ast};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

const DEFAULT_EXCLUDES: &[&str] = &[
    ".git",
    ".ruff_cache",
    "__pycache__",
    "build",
    "reports",
    "vendor",
    "python/jax_util.egg-info",
];
const INITIALIZE_ONLY_FIELD_NAMES: &[&str] = &[
    "run_log",
    "output_path",
    "run_label",
    "log_iterates",
    "log_intermediates",
    "log_operator_stats",
];
const RUNTIME_ONLY_FIELD_NAMES: &[&str] = &[
    "atol",
    "maxiter",
    "rtol",
    "runtime_atol",
    "runtime_rtol",
    "stopping",
];
const PROTOCOL_MODULE: &str = "jax_util.base.algorithm_module_protocol";

type ConfigKinds = BTreeMap<String, String>;
type ModuleIndex = BTreeMap<String, ConfigKinds>;

#[derive(Debug)]
struct Args {
    root: PathBuf,
    paths: Vec<String>,
    excludes: Vec<String>,
    format: OutputFormat,
    fail_on_finding: bool,
    fail_on_default: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug)]
struct Finding {
    path: String,
    line: usize,
    class_name: String,
    field: String,
    annotation: String,
    expected_owner: String,
    reason: String,
}

impl Finding {
    fn render(&self) -> String {
        format!(
            "ALGORITHM_CONFIG_PARTITION_FINDING={}:{}.{}:expected={}:reason={}",
            self.path, self.line, self.class_name, self.field, self.expected_owner, self.reason
        )
    }

    fn to_json(&self) -> Value {
        json!({
            "path": self.path,
            "line": self.line,
            "class_name": self.class_name,
            "field": self.field,
            "annotation": self.annotation,
            "expected_owner": self.expected_owner,
            "reason": self.reason,
        })
    }
}

#[derive(Debug)]
struct DefaultFinding {
    path: String,
    line: usize,
    scope: String,
    kind: String,
    name: String,
    owner: String,
    severity: String,
    reason: String,
    guidance: String,
}

impl DefaultFinding {
    fn render(&self) -> String {
        format!(
            "ALGORITHM_CONFIG_DEFAULT_FINDING={}:{}:{}:{}:{}:owner={}:severity={}:reason={}",
            self.path,
            self.line,
            self.scope,
            self.kind,
            self.name,
            self.owner,
            self.severity,
            self.reason
        )
    }

    fn to_json(&self) -> Value {
        json!({
            "path": self.path,
            "line": self.line,
            "scope": self.scope,
            "kind": self.kind,
            "name": self.name,
            "owner": self.owner,
            "severity": self.severity,
            "reason": self.reason,
            "guidance": self.guidance,
        })
    }
}

#[derive(Debug)]
struct ConfigField {
    path: String,
    line: usize,
    class_name: String,
    field: String,
    annotation: String,
    annotation_config_kinds: Vec<String>,
}

impl ConfigField {
    fn to_json(&self) -> Value {
        json!({
            "path": self.path,
            "line": self.line,
            "class_name": self.class_name,
            "field": self.field,
            "annotation": self.annotation,
            "annotation_config_kinds": self.annotation_config_kinds,
        })
    }
}

#[derive(Debug)]
struct ParsedFile {
    path: PathBuf,
    source: String,
    suite: Option<ast::Suite>,
    syntax_error_line: Option<usize>,
}

#[derive(Debug)]
struct ImportContext {
    module_aliases: BTreeMap<String, String>,
    class_aliases: BTreeMap<String, String>,
}

#[derive(Debug)]
struct ClassRecord {
    dotted_name: String,
    top_level_name: Option<String>,
    bases: Vec<String>,
}

#[derive(Debug)]
struct CheckResult {
    fields: Vec<ConfigField>,
    findings: Vec<Finding>,
    default_findings: Vec<DefaultFinding>,
}

const HELP: &str = "usage: agent-canon check-algorithm-config-partition [--root ROOT] [--exclude PATTERN]... [--format text|json] [--fail-on-finding] [--fail-on-default] [paths...]\n\nCheck InitializeConfig/SolveConfig field ownership and hidden runtime defaults.\n\nOptions:\n  --root ROOT          Repository root (default: current directory)\n  --exclude PATTERN    Exclude a path, path prefix, path part, or glob (repeatable)\n  --format FORMAT      Output format: text or json (default: text)\n  --fail-on-finding    Return non-zero when config partition findings are present\n  --fail-on-default    Return non-zero when hidden runtime default errors are present\n  -h, --help           Print this help";

pub fn run(raw_args: &[String]) -> i32 {
    let args = match Args::parse(raw_args) {
        Ok(Some(args)) => args,
        Ok(None) => {
            println!("{HELP}");
            return 0;
        }
        Err(message) => {
            eprintln!("{HELP}");
            eprintln!("agent-canon: check-algorithm-config-partition: error: {message}");
            return 2;
        }
    };
    match run_check(args) {
        Ok((report, format, fail_on_finding, fail_on_default)) => {
            render_report(&report, format);
            if (fail_on_finding && !report.findings.is_empty())
                || (fail_on_default && report.runtime_default_errors > 0)
            {
                1
            } else {
                0
            }
        }
        Err(message) => {
            eprintln!("ALGORITHM_CONFIG_PARTITION=fail");
            eprintln!("ALGORITHM_CONFIG_PARTITION_ERROR={message}");
            2
        }
    }
}

impl Args {
    fn parse(raw_args: &[String]) -> Result<Option<Self>, String> {
        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
        let mut excludes = DEFAULT_EXCLUDES
            .iter()
            .map(|value| value.to_string())
            .collect::<Vec<_>>();
        let mut format = OutputFormat::Text;
        let mut fail_on_finding = false;
        let mut fail_on_default = false;
        let mut positional_only = false;
        let mut index = 0;
        while index < raw_args.len() {
            let value = raw_args[index].as_str();
            if positional_only || value == "-" || !value.starts_with('-') {
                paths.push(value.to_string());
                index += 1;
                continue;
            }
            if value == "--" {
                positional_only = true;
                index += 1;
                continue;
            }
            if matches!(value, "-h" | "--help") {
                return Ok(None);
            }
            if let Some(value) = value.strip_prefix("--root=") {
                root = PathBuf::from(value);
                index += 1;
                continue;
            }
            if let Some(value) = value.strip_prefix("--exclude=") {
                excludes.push(value.to_string());
                index += 1;
                continue;
            }
            if let Some(value) = value.strip_prefix("--format=") {
                format = parse_format(value)?;
                index += 1;
                continue;
            }
            match value {
                "--root" => {
                    root = PathBuf::from(value_after(raw_args, index, "--root")?);
                    index += 2;
                }
                "--exclude" => {
                    excludes.push(value_after(raw_args, index, "--exclude")?);
                    index += 2;
                }
                "--format" => {
                    format = parse_format(&value_after(raw_args, index, "--format")?)?;
                    index += 2;
                }
                "--fail-on-finding" => {
                    fail_on_finding = true;
                    index += 1;
                }
                "--fail-on-default" => {
                    fail_on_default = true;
                    index += 1;
                }
                _ => return Err(format!("unknown argument {value}")),
            }
        }
        Ok(Some(Self {
            root,
            paths,
            excludes,
            format,
            fail_on_finding,
            fail_on_default,
        }))
    }
}

fn parse_format(value: &str) -> Result<OutputFormat, String> {
    match value {
        "text" => Ok(OutputFormat::Text),
        "json" => Ok(OutputFormat::Json),
        _ => Err(format!(
            "argument --format: invalid choice: {value:?} (choose from 'text', 'json')"
        )),
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .filter(|value| !value.starts_with("--"))
        .cloned()
        .ok_or_else(|| format!("argument {flag}: expected one argument"))
}

fn run_check(args: Args) -> Result<(Report, OutputFormat, bool, bool), String> {
    let format = args.format;
    let fail_on_finding = args.fail_on_finding;
    let fail_on_default = args.fail_on_default;
    let root = resolve_like_cwd(&args.root);
    let root = fs::canonicalize(&root).unwrap_or(root);
    let files = crate::python_algorithm_contract::source_files_for_config_checker(
        &root,
        &args.paths,
        &args.excludes,
    );
    let parsed = parse_files(&files)?;
    let module_index = build_module_config_index(&root, &parsed);
    let mut report = Report::default();
    for parsed_file in &parsed {
        let result = scan_file(&root, parsed_file, &module_index);
        report.fields.extend(result.fields);
        report.findings.extend(result.findings);
        report.default_findings.extend(result.default_findings);
    }
    report.runtime_default_errors = report
        .default_findings
        .iter()
        .filter(|finding| finding.severity == "error")
        .count();
    report.config_default_warnings = report
        .default_findings
        .iter()
        .filter(|finding| finding.severity == "warn")
        .count();
    Ok((report, format, fail_on_finding, fail_on_default))
}

fn resolve_like_cwd(path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    }
}

#[derive(Debug, Default)]
struct Report {
    fields: Vec<ConfigField>,
    findings: Vec<Finding>,
    default_findings: Vec<DefaultFinding>,
    runtime_default_errors: usize,
    config_default_warnings: usize,
}

fn render_report(report: &Report, format: OutputFormat) {
    if format == OutputFormat::Json {
        let payload = json!({
            "summary": {
                "fields": report.fields.len(),
                "findings": report.findings.len(),
                "default_findings": report.default_findings.len(),
                "runtime_default_errors": report.runtime_default_errors,
                "config_default_warnings": report.config_default_warnings,
            },
            "fields": report.fields.iter().map(ConfigField::to_json).collect::<Vec<_>>(),
            "findings": report.findings.iter().map(Finding::to_json).collect::<Vec<_>>(),
            "default_findings": report.default_findings.iter().map(DefaultFinding::to_json).collect::<Vec<_>>(),
        });
        println!(
            "{}",
            serde_json::to_string_pretty(&payload).expect("JSON report is serializable")
        );
        return;
    }
    for finding in &report.findings {
        println!("{}", finding.render());
    }
    for finding in &report.default_findings {
        println!("{}", finding.render());
    }
    println!("ALGORITHM_CONFIG_PARTITION_FIELDS={}", report.fields.len());
    println!(
        "ALGORITHM_CONFIG_PARTITION_FINDINGS={}",
        report.findings.len()
    );
    println!(
        "ALGORITHM_CONFIG_DEFAULT_FINDINGS={}",
        report.default_findings.len()
    );
    println!(
        "ALGORITHM_CONFIG_RUNTIME_DEFAULT_ERRORS={}",
        report.runtime_default_errors
    );
    let status = if !report.findings.is_empty() || report.runtime_default_errors > 0 {
        "fail"
    } else {
        "pass"
    };
    println!("ALGORITHM_CONFIG_PARTITION={status}");
}

fn parse_files(files: &[PathBuf]) -> Result<Vec<ParsedFile>, String> {
    files
        .iter()
        .map(|path| {
            let source = fs::read_to_string(path).map_err(|error| {
                format!("failed to read Python source {}: {error}", path.display())
            })?;
            let source = normalize_python_newlines(&source);
            let filename = path.to_string_lossy();
            match ast::Suite::parse(&source, filename.as_ref()) {
                Ok(suite) => Ok(ParsedFile {
                    path: path.clone(),
                    source,
                    suite: Some(suite),
                    syntax_error_line: None,
                }),
                Err(error) => Ok(ParsedFile {
                    path: path.clone(),
                    syntax_error_line: Some(line_at_offset(&source, error.offset.to_usize())),
                    source,
                    suite: None,
                }),
            }
        })
        .collect()
}

fn build_module_config_index(root: &Path, files: &[ParsedFile]) -> ModuleIndex {
    let mut index = ModuleIndex::new();
    for file in files {
        let Some(suite) = file.suite.as_ref() else {
            continue;
        };
        let (classes, _, _) = collect_classes(suite);
        let kinds = config_class_kinds(suite, &classes);
        if kinds.is_empty() {
            continue;
        }
        for module_name in module_names_for_path(root, &file.path) {
            index.insert(module_name, kinds.clone());
        }
    }
    index
}

fn scan_file(root: &Path, file: &ParsedFile, module_index: &ModuleIndex) -> CheckResult {
    let Some(suite) = file.suite.as_ref() else {
        return CheckResult {
            fields: Vec::new(),
            findings: vec![Finding {
                path: relative_path(root, &file.path),
                line: file.syntax_error_line.unwrap_or(1),
                class_name: "<syntax-error>".to_string(),
                field: "<syntax-error>".to_string(),
                annotation: String::new(),
                expected_owner: "fix-syntax".to_string(),
                reason: "syntax error prevents config partition analysis".to_string(),
            }],
            default_findings: Vec::new(),
        };
    };
    let (classes, class_assignment_offsets, module_assignment_offsets) = collect_classes(suite);
    let config_kinds = config_class_kinds(suite, &classes);
    let imports = import_context(suite, &primary_module_name(root, &file.path), module_index);
    let fields = class_fields(root, file, suite, &config_kinds, &imports, module_index);
    let findings = fields.iter().flat_map(field_findings).collect();
    let mut visitor = DefaultVisitor {
        root,
        path: &file.path,
        source: &file.source,
        config_kinds: &config_kinds,
        imports: &imports,
        module_index,
        class_assignment_offsets: &class_assignment_offsets,
        module_assignment_offsets: &module_assignment_offsets,
        scopes: Vec::new(),
        findings: Vec::new(),
    };
    for statement in suite {
        visitor.visit_stmt(statement.clone());
    }
    CheckResult {
        fields,
        findings,
        default_findings: visitor.findings,
    }
}

fn relative_path(root: &Path, path: &Path) -> String {
    let resolved = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    resolved
        .strip_prefix(root)
        .unwrap_or(&resolved)
        .to_string_lossy()
        .replace('\\', "/")
}

fn module_names_for_path(root: &Path, path: &Path) -> Vec<String> {
    let resolved = fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    let relative = resolved.strip_prefix(root).unwrap_or(&resolved);
    if relative
        .extension()
        .and_then(|extension| extension.to_str())
        != Some("py")
    {
        return Vec::new();
    }
    let mut parts = relative
        .with_extension("")
        .components()
        .map(|part| part.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    if parts.last().is_some_and(|part| part == "__init__") {
        parts.pop();
    }
    let mut candidates = Vec::new();
    if !parts.is_empty() {
        candidates.push(parts.join("."));
    }
    if parts.first().is_some_and(|part| part == "python") && parts.len() > 1 {
        candidates.push(parts[1..].join("."));
    }
    candidates.dedup();
    candidates
}

fn primary_module_name(root: &Path, path: &Path) -> String {
    module_names_for_path(root, path)
        .into_iter()
        .next()
        .unwrap_or_default()
}

fn resolve_import_from_module(current_module: &str, level: usize, module: &str) -> String {
    if level == 0 {
        return module.to_string();
    }
    let mut parts = current_module
        .split('.')
        .take(current_module.split('.').count().saturating_sub(1))
        .map(str::to_string)
        .collect::<Vec<_>>();
    for _ in 1..level {
        if !parts.is_empty() {
            parts.pop();
        }
    }
    if !module.is_empty() {
        parts.extend(
            module
                .split('.')
                .filter(|part| !part.is_empty())
                .map(str::to_string),
        );
    }
    parts.join(".")
}

#[derive(Debug)]
enum ImportSpec {
    Import {
        name: String,
        alias: Option<String>,
    },
    From {
        module: String,
        level: usize,
        name: String,
        alias: Option<String>,
    },
}

#[derive(Default)]
struct ImportCollector {
    imports: Vec<ImportRecord>,
    depth: usize,
    order: usize,
}

struct ImportRecord {
    depth: usize,
    offset: usize,
    order: usize,
    spec: ImportSpec,
}

impl ImportCollector {
    fn push(&mut self, offset: usize, spec: ImportSpec) {
        self.imports.push(ImportRecord {
            depth: self.depth,
            offset,
            order: self.order,
            spec,
        });
        self.order += 1;
    }
}

impl Visitor for ImportCollector {
    fn visit_stmt(&mut self, node: ast::Stmt) {
        self.depth += 1;
        self.generic_visit_stmt(node);
        self.depth -= 1;
    }

    fn visit_excepthandler(&mut self, node: ast::ExceptHandler) {
        self.depth += 1;
        self.generic_visit_excepthandler(node);
        self.depth -= 1;
    }

    fn visit_match_case(&mut self, node: ast::MatchCase) {
        self.depth += 1;
        self.generic_visit_match_case(node);
        self.depth -= 1;
    }

    fn visit_stmt_import(&mut self, node: ast::StmtImport) {
        let offset = node.start().to_usize();
        for alias in node.names {
            self.push(
                offset,
                ImportSpec::Import {
                    name: alias.name.as_str().to_string(),
                    alias: alias.asname.map(|name| name.as_str().to_string()),
                },
            );
        }
    }

    fn visit_stmt_import_from(&mut self, node: ast::StmtImportFrom) {
        let offset = node.start().to_usize();
        let module = node
            .module
            .map(|module| module.as_str().to_string())
            .unwrap_or_default();
        let level = node.level.map(|level| level.to_usize()).unwrap_or(0);
        for alias in node.names {
            self.push(
                offset,
                ImportSpec::From {
                    module: module.clone(),
                    level,
                    name: alias.name.as_str().to_string(),
                    alias: alias.asname.map(|name| name.as_str().to_string()),
                },
            );
        }
    }
}

fn imports_in_suite(suite: &[ast::Stmt]) -> Vec<ImportSpec> {
    let mut collector = ImportCollector::default();
    for statement in suite {
        collector.visit_stmt(statement.clone());
    }
    collector
        .imports
        .sort_by_key(|record| (record.depth, record.offset, record.order));
    collector
        .imports
        .into_iter()
        .map(|record| record.spec)
        .collect()
}

fn collect_classes(suite: &[ast::Stmt]) -> (Vec<ClassRecord>, HashSet<usize>, HashSet<usize>) {
    let mut classes = Vec::new();
    let mut module_assignment_offsets = HashSet::new();
    for statement in suite {
        if matches!(statement, ast::Stmt::AnnAssign(_) | ast::Stmt::Assign(_)) {
            module_assignment_offsets.insert(statement.start().to_usize());
        }
    }
    collect_class_records(suite, &[], &mut classes);
    let class_assignment_offsets = collect_class_assignment_offsets(suite);
    (classes, class_assignment_offsets, module_assignment_offsets)
}

fn collect_class_records(body: &[ast::Stmt], prefix: &[String], classes: &mut Vec<ClassRecord>) {
    for statement in body {
        let ast::Stmt::ClassDef(class) = statement else {
            continue;
        };
        let name = class.name.as_str().to_string();
        let mut name_parts = prefix.to_vec();
        name_parts.push(name.clone());
        let dotted_name = name_parts.join(".");
        classes.push(ClassRecord {
            dotted_name,
            top_level_name: prefix.is_empty().then_some(name),
            bases: class_base_names(class),
        });
        collect_class_records(&class.body, &name_parts, classes);
    }
}

#[derive(Default)]
struct ClassAssignmentCollector {
    offsets: HashSet<usize>,
}

impl Visitor for ClassAssignmentCollector {
    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        for statement in &node.body {
            if matches!(statement, ast::Stmt::AnnAssign(_) | ast::Stmt::Assign(_)) {
                self.offsets.insert(statement.start().to_usize());
            }
        }
        self.generic_visit_stmt_class_def(node);
    }
}

fn collect_class_assignment_offsets(suite: &[ast::Stmt]) -> HashSet<usize> {
    let mut collector = ClassAssignmentCollector::default();
    for statement in suite {
        collector.visit_stmt(statement.clone());
    }
    collector.offsets
}

fn config_class_kinds(suite: &[ast::Stmt], classes: &[ClassRecord]) -> ConfigKinds {
    let imports = imports_in_suite(suite);
    let mut protocol_module_aliases = BTreeSet::new();
    let mut protocol_class_aliases = BTreeMap::new();
    for import in &imports {
        match import {
            ImportSpec::Import { name, alias } => {
                if name == PROTOCOL_MODULE || name.ends_with(".algorithm_module_protocol") {
                    protocol_module_aliases.insert(alias.clone().unwrap_or_else(|| name.clone()));
                }
            }
            ImportSpec::From {
                module,
                name,
                alias,
                ..
            } => {
                let alias_name = alias.clone().unwrap_or_else(|| name.clone());
                let imports_protocol_module =
                    module == PROTOCOL_MODULE || module.ends_with(".algorithm_module_protocol");
                if imports_protocol_module {
                    if let Some(kind) = config_base_kind(name) {
                        protocol_class_aliases.insert(alias_name.clone(), kind.to_string());
                    }
                }
                if name == "algorithm_module_protocol" {
                    protocol_module_aliases.insert(alias_name);
                }
            }
        }
    }

    let mut classes_by_name = BTreeMap::<String, &ClassRecord>::new();
    let mut class_name_order = Vec::new();
    for class in classes {
        if !classes_by_name.contains_key(&class.dotted_name) {
            class_name_order.push(class.dotted_name.clone());
        }
        classes_by_name.insert(class.dotted_name.clone(), class);
        if let Some(top_level_name) = class.top_level_name.as_ref() {
            if !classes_by_name.contains_key(top_level_name) {
                class_name_order.push(top_level_name.clone());
            }
            classes_by_name.insert(top_level_name.clone(), class);
        }
    }

    let mut resolved = ConfigKinds::new();
    let mut changed = true;
    while changed {
        changed = false;
        for name in &class_name_order {
            if resolved.contains_key(name) {
                continue;
            }
            let class = classes_by_name
                .get(name)
                .expect("class names are registered with a record");
            if let Some(kind) = direct_config_class_kind(
                &class.bases,
                &protocol_module_aliases,
                &protocol_class_aliases,
            ) {
                resolved.insert(name.clone(), kind);
                changed = true;
                continue;
            }
            for base in &class.bases {
                let tail = base.rsplit('.').next().unwrap_or(base);
                let inherited_kind = resolved.get(base).cloned().or_else(|| {
                    if base.contains('.') {
                        None
                    } else {
                        resolved.get(tail).cloned()
                    }
                });
                if let Some(kind) = inherited_kind {
                    resolved.insert(name.clone(), kind);
                    changed = true;
                    break;
                }
            }
        }
    }
    resolved
}

fn config_base_kind(name: &str) -> Option<&'static str> {
    match name {
        "InitializeConfig" => Some("InitializeConfig"),
        "SolveConfig" => Some("SolveConfig"),
        _ => None,
    }
}

fn class_base_names(class: &ast::StmtClassDef) -> Vec<String> {
    class
        .bases
        .iter()
        .flat_map(|base| {
            let name = base_name(base);
            if name.is_empty() {
                return Vec::new();
            }
            let tail = name.rsplit('.').next().unwrap_or(&name).to_string();
            vec![name, tail]
        })
        .collect()
}

fn direct_config_class_kind(
    bases: &[String],
    protocol_module_aliases: &BTreeSet<String>,
    protocol_class_aliases: &BTreeMap<String, String>,
) -> Option<String> {
    let mut candidates = BTreeSet::new();
    candidates.extend(bases.iter().cloned());
    for base in candidates {
        if let Some(kind) = protocol_class_aliases.get(&base) {
            return Some(kind.clone());
        }
        let Some((owner, tail)) = base.rsplit_once('.') else {
            continue;
        };
        if protocol_module_aliases.contains(owner) {
            if let Some(kind) = config_base_kind(tail) {
                return Some(kind.to_string());
            }
        }
    }
    None
}

fn import_context(
    suite: &[ast::Stmt],
    current_module: &str,
    module_index: &ModuleIndex,
) -> ImportContext {
    let mut module_aliases = BTreeMap::new();
    let mut class_aliases = BTreeMap::new();
    for import in imports_in_suite(suite) {
        match import {
            ImportSpec::Import { name, alias } => {
                let alias_name =
                    alias.unwrap_or_else(|| name.split('.').next().unwrap_or(&name).to_string());
                if module_index.contains_key(&name) {
                    module_aliases.insert(alias_name, name);
                }
            }
            ImportSpec::From {
                module,
                level,
                name,
                alias,
            } => {
                if name == "*" {
                    continue;
                }
                let module_name = resolve_import_from_module(current_module, level, &module);
                let alias_name = alias.unwrap_or_else(|| name.clone());
                let imported_module = if module_name.is_empty() {
                    name.clone()
                } else {
                    format!("{module_name}.{name}")
                };
                if module_index.contains_key(&imported_module) {
                    module_aliases.insert(alias_name, imported_module);
                    continue;
                }
                if let Some(config_kind) = module_index
                    .get(&module_name)
                    .and_then(|kinds| kinds.get(&name))
                {
                    class_aliases.insert(alias_name, config_kind.clone());
                }
            }
        }
    }
    ImportContext {
        module_aliases,
        class_aliases,
    }
}

fn base_name(node: &ast::Expr) -> String {
    match node {
        ast::Expr::Name(name) => name.id.as_str().to_string(),
        ast::Expr::Attribute(attribute) => {
            let prefix = base_name(&attribute.value);
            if prefix.is_empty() {
                attribute.attr.as_str().to_string()
            } else {
                format!("{prefix}.{}", attribute.attr.as_str())
            }
        }
        ast::Expr::Subscript(subscript) => base_name(&subscript.value),
        ast::Expr::BinOp(binary) if matches!(&binary.op, ast::Operator::BitOr) => {
            [base_name(&binary.left), base_name(&binary.right)]
                .into_iter()
                .filter(|name| !name.is_empty())
                .collect::<Vec<_>>()
                .join("|")
        }
        ast::Expr::Constant(constant) => match &constant.value {
            ast::Constant::Str(value) => value.clone(),
            _ => String::new(),
        },
        _ => String::new(),
    }
}

fn dotted_name(node: &ast::Expr) -> String {
    match node {
        ast::Expr::Name(name) => name.id.as_str().to_string(),
        ast::Expr::Attribute(attribute) => {
            let left = dotted_name(&attribute.value);
            if left.is_empty() {
                attribute.attr.as_str().to_string()
            } else {
                format!("{left}.{}", attribute.attr.as_str())
            }
        }
        ast::Expr::Call(call) => dotted_name(&call.func),
        _ => String::new(),
    }
}

fn config_kind_for_expr(
    node: &ast::Expr,
    local_config_kinds: &ConfigKinds,
    imports: &ImportContext,
    module_index: &ModuleIndex,
) -> Option<String> {
    match node {
        ast::Expr::Name(name) => local_config_kinds
            .get(name.id.as_str())
            .or_else(|| imports.class_aliases.get(name.id.as_str()))
            .cloned(),
        ast::Expr::Attribute(_) => {
            let expression_name = dotted_name(node);
            if let Some(kind) = local_config_kinds.get(&expression_name) {
                return Some(kind.clone());
            }
            let parts = expression_name.split('.').collect::<Vec<_>>();
            if parts.len() < 2 {
                return None;
            }
            if let Some(alias_module) = imports.module_aliases.get(parts[0]) {
                let mut module_parts = alias_module
                    .split('.')
                    .map(str::to_string)
                    .collect::<Vec<_>>();
                module_parts.extend(
                    parts[1..parts.len() - 1]
                        .iter()
                        .map(|part| part.to_string()),
                );
                if let Some(kind) = module_index
                    .get(&module_parts.join("."))
                    .and_then(|kinds| kinds.get(parts[parts.len() - 1]))
                {
                    return Some(kind.clone());
                }
            }
            module_index
                .get(&parts[..parts.len() - 1].join("."))
                .and_then(|kinds| kinds.get(parts[parts.len() - 1]))
                .cloned()
        }
        ast::Expr::Subscript(subscript) => {
            config_kind_for_expr(&subscript.value, local_config_kinds, imports, module_index)
        }
        _ => None,
    }
}

struct ConfigKindCollector<'a> {
    local_config_kinds: &'a ConfigKinds,
    imports: &'a ImportContext,
    module_index: &'a ModuleIndex,
    kinds: BTreeSet<String>,
}

impl Visitor for ConfigKindCollector<'_> {
    fn visit_expr(&mut self, node: ast::Expr) {
        if let Some(kind) = config_kind_for_expr(
            &node,
            self.local_config_kinds,
            self.imports,
            self.module_index,
        ) {
            self.kinds.insert(kind);
        }
        self.generic_visit_expr(node);
    }
}

fn config_kinds_in_expr(
    node: &ast::Expr,
    local_config_kinds: &ConfigKinds,
    imports: &ImportContext,
    module_index: &ModuleIndex,
) -> Vec<String> {
    let mut collector = ConfigKindCollector {
        local_config_kinds,
        imports,
        module_index,
        kinds: BTreeSet::new(),
    };
    collector.visit_expr(node.clone());
    collector.kinds.into_iter().collect()
}

fn is_literalish_default(
    node: &ast::Expr,
    local_config_kinds: &ConfigKinds,
    imports: &ImportContext,
    module_index: &ModuleIndex,
) -> bool {
    match node {
        ast::Expr::Constant(constant) => !matches!(&constant.value, ast::Constant::Ellipsis),
        ast::Expr::List(_) | ast::Expr::Tuple(_) | ast::Expr::Set(_) | ast::Expr::Dict(_) => true,
        ast::Expr::UnaryOp(unary)
            if matches!(&unary.op, ast::UnaryOp::USub | ast::UnaryOp::UAdd) =>
        {
            is_literalish_default(&unary.operand, local_config_kinds, imports, module_index)
        }
        ast::Expr::Call(call) => {
            let name = dotted_name(&call.func);
            if matches!(name.as_str(), "dict" | "list" | "set" | "tuple") {
                return true;
            }
            config_kind_for_expr(&call.func, local_config_kinds, imports, module_index).is_some()
        }
        _ => false,
    }
}

fn field_default_kind(
    node: &ast::Stmt,
    local_config_kinds: &ConfigKinds,
    imports: &ImportContext,
    module_index: &ModuleIndex,
) -> Option<(String, ast::Expr)> {
    let value = match node {
        ast::Stmt::AnnAssign(assignment) => assignment.value.as_deref(),
        ast::Stmt::Assign(assignment) => Some(assignment.value.as_ref()),
        _ => None,
    }?;
    if let ast::Expr::Call(call) = value {
        if dotted_name(&call.func).ends_with("field") {
            for keyword in &call.keywords {
                let Some(name) = keyword.arg.as_ref().map(|name| name.as_str()) else {
                    continue;
                };
                if matches!(name, "default" | "default_factory") {
                    return Some((format!("field-{name}"), keyword.value.clone()));
                }
            }
            return None;
        }
    }
    if is_literalish_default(value, local_config_kinds, imports, module_index) {
        return Some(("assigned-default".to_string(), value.clone()));
    }
    None
}

fn target_name(node: &ast::Stmt) -> String {
    match node {
        ast::Stmt::AnnAssign(assignment) => match assignment.target.as_ref() {
            ast::Expr::Name(name) => name.id.as_str().to_string(),
            _ => "<assignment>".to_string(),
        },
        ast::Stmt::Assign(assignment) => {
            let names = assignment
                .targets
                .iter()
                .filter_map(|target| match target {
                    ast::Expr::Name(name) => Some(name.id.as_str()),
                    _ => None,
                })
                .collect::<Vec<_>>();
            if names.is_empty() {
                "<assignment>".to_string()
            } else {
                names.join(",")
            }
        }
        _ => "<assignment>".to_string(),
    }
}

fn assignment_names(node: &ast::Stmt) -> Vec<String> {
    match node {
        ast::Stmt::AnnAssign(assignment) => match assignment.target.as_ref() {
            ast::Expr::Name(name) => vec![name.id.as_str().to_string()],
            _ => Vec::new(),
        },
        ast::Stmt::Assign(assignment) => assignment
            .targets
            .iter()
            .filter_map(|target| match target {
                ast::Expr::Name(name) => Some(name.id.as_str().to_string()),
                _ => None,
            })
            .collect(),
        _ => Vec::new(),
    }
}

fn is_module_constant_assignment(
    node: &ast::Stmt,
    module_assignment_offsets: &HashSet<usize>,
) -> bool {
    if !module_assignment_offsets.contains(&node.start().to_usize()) {
        return false;
    }
    let names = assignment_names(node);
    !names.is_empty()
        && names
            .iter()
            .all(|name| name.starts_with("__") || is_python_uppercase(name))
}

fn is_python_uppercase(value: &str) -> bool {
    let mut has_cased_character = false;
    for character in value.chars() {
        if character.is_lowercase() {
            return false;
        }
        has_cased_character |= character.is_uppercase();
    }
    has_cased_character
}

fn class_fields(
    root: &Path,
    file: &ParsedFile,
    suite: &[ast::Stmt],
    config_kinds: &ConfigKinds,
    imports: &ImportContext,
    module_index: &ModuleIndex,
) -> Vec<ConfigField> {
    let mut fields = Vec::new();
    let path = relative_path(root, &file.path);
    for statement in suite {
        let ast::Stmt::ClassDef(class) = statement else {
            continue;
        };
        let Some(kind) = config_kinds.get(class.name.as_str()) else {
            continue;
        };
        for item in &class.body {
            let ast::Stmt::AnnAssign(assignment) = item else {
                continue;
            };
            let ast::Expr::Name(field_name) = assignment.target.as_ref() else {
                continue;
            };
            fields.push(ConfigField {
                path: path.clone(),
                line: line_at_offset(&file.source, item.start().to_usize()),
                class_name: kind.clone(),
                field: field_name.id.as_str().to_string(),
                annotation: assignment.annotation.to_string(),
                annotation_config_kinds: config_kinds_in_expr(
                    &assignment.annotation,
                    config_kinds,
                    imports,
                    module_index,
                ),
            });
        }
    }
    fields
}

fn field_findings(field: &ConfigField) -> Vec<Finding> {
    let (expected_owner, reason) = if field.class_name == "SolveConfig" {
        if INITIALIZE_ONLY_FIELD_NAMES.contains(&field.field.as_str()) {
            (
                "InitializeConfig",
                "initialization-only field name in SolveConfig",
            )
        } else if field
            .annotation_config_kinds
            .iter()
            .any(|kind| kind == "InitializeConfig")
        {
            (
                "InitializeConfig",
                "initialization-only config type in SolveConfig",
            )
        } else {
            return Vec::new();
        }
    } else if field.class_name == "InitializeConfig" {
        if RUNTIME_ONLY_FIELD_NAMES.contains(&field.field.as_str()) {
            ("SolveConfig", "runtime-only field name in InitializeConfig")
        } else if field
            .annotation_config_kinds
            .iter()
            .any(|kind| kind == "SolveConfig")
        {
            (
                "SolveConfig",
                "runtime-only config type in InitializeConfig",
            )
        } else {
            return Vec::new();
        }
    } else {
        return Vec::new();
    };
    vec![Finding {
        path: field.path.clone(),
        line: field.line,
        class_name: field.class_name.clone(),
        field: field.field.clone(),
        annotation: field.annotation.clone(),
        expected_owner: expected_owner.to_string(),
        reason: reason.to_string(),
    }]
}

#[derive(Debug)]
struct Scope {
    name: String,
    is_class: bool,
}

struct DefaultVisitor<'a> {
    root: &'a Path,
    path: &'a Path,
    source: &'a str,
    config_kinds: &'a ConfigKinds,
    imports: &'a ImportContext,
    module_index: &'a ModuleIndex,
    class_assignment_offsets: &'a HashSet<usize>,
    module_assignment_offsets: &'a HashSet<usize>,
    scopes: Vec<Scope>,
    findings: Vec<DefaultFinding>,
}

impl DefaultVisitor<'_> {
    fn current_scope(&self) -> String {
        let names = self
            .scopes
            .iter()
            .map(|scope| scope.name.as_str())
            .collect::<Vec<_>>();
        if names.is_empty() {
            "<module>".to_string()
        } else {
            names.join(".")
        }
    }

    fn current_owner(&self) -> Option<String> {
        self.scopes.iter().rev().find_map(|scope| {
            scope
                .is_class
                .then(|| self.config_kinds.get(&scope.name))
                .flatten()
                .cloned()
        })
    }

    fn record_function_defaults(&mut self, args: &ast::Arguments) {
        let owner = self
            .current_owner()
            .unwrap_or_else(|| "runtime".to_string());
        let scope = self.current_scope();
        for argument in args.posonlyargs.iter().chain(&args.args) {
            let Some(default) = argument.default.as_deref() else {
                continue;
            };
            self.findings.push(DefaultFinding {
                path: relative_path(self.root, self.path),
                line: line_at_offset(self.source, default.start().to_usize()),
                scope: scope.clone(),
                kind: "parameter-default".to_string(),
                name: argument.def.arg.as_str().to_string(),
                owner: owner.clone(),
                severity: "error".to_string(),
                reason: "callable parameter supplies a code default outside config ownership"
                    .to_string(),
                guidance:
                    "move the value into InitializeConfig/SolveConfig or require the caller to pass it explicitly"
                        .to_string(),
            });
        }
        for argument in &args.kwonlyargs {
            let Some(default) = argument.default.as_deref() else {
                continue;
            };
            self.findings.push(DefaultFinding {
                path: relative_path(self.root, self.path),
                line: line_at_offset(self.source, default.start().to_usize()),
                scope: scope.clone(),
                kind: "keyword-parameter-default".to_string(),
                name: argument.def.arg.as_str().to_string(),
                owner: owner.clone(),
                severity: "error".to_string(),
                reason:
                    "keyword-only parameter supplies a code default outside config ownership"
                        .to_string(),
                guidance:
                    "move the value into InitializeConfig/SolveConfig or require the caller to pass it explicitly"
                        .to_string(),
            });
        }
    }

    fn record_assignment_default(&mut self, statement: &ast::Stmt) {
        if !self
            .class_assignment_offsets
            .contains(&statement.start().to_usize())
        {
            return;
        }
        let Some(owner) = self.current_owner() else {
            return;
        };
        if is_module_constant_assignment(statement, self.module_assignment_offsets) {
            return;
        }
        let Some((kind, value)) = field_default_kind(
            statement,
            self.config_kinds,
            self.imports,
            self.module_index,
        ) else {
            return;
        };
        self.findings.push(DefaultFinding {
            path: relative_path(self.root, self.path),
            line: line_at_offset(self.source, value.start().to_usize()),
            scope: self.current_scope(),
            kind,
            name: target_name(statement),
            owner,
            severity: "warn".to_string(),
            reason: "config class owns this default value".to_string(),
            guidance: "make this field required if caller-specific configuration must be explicit"
                .to_string(),
        });
    }

    fn record_implicit_default(
        &mut self,
        line_node: &impl Ranged,
        kind: &str,
        name: String,
        reason: &str,
    ) {
        self.findings.push(DefaultFinding {
            path: relative_path(self.root, self.path),
            line: line_at_offset(self.source, line_node.start().to_usize()),
            scope: self.current_scope(),
            kind: kind.to_string(),
            name,
            owner: self
                .current_owner()
                .unwrap_or_else(|| "runtime".to_string()),
            severity: "error".to_string(),
            reason: reason.to_string(),
            guidance: "thread the value through InitializeConfig/SolveConfig or fail when absent"
                .to_string(),
        });
    }
}

impl Visitor for DefaultVisitor<'_> {
    fn visit_stmt_function_def(&mut self, node: ast::StmtFunctionDef) {
        self.record_function_defaults(&node.args);
        self.scopes.push(Scope {
            name: node.name.as_str().to_string(),
            is_class: false,
        });
        self.generic_visit_stmt_function_def(node);
        self.scopes.pop();
    }

    fn visit_stmt_async_function_def(&mut self, node: ast::StmtAsyncFunctionDef) {
        self.record_function_defaults(&node.args);
        self.scopes.push(Scope {
            name: node.name.as_str().to_string(),
            is_class: false,
        });
        self.generic_visit_stmt_async_function_def(node);
        self.scopes.pop();
    }

    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        self.scopes.push(Scope {
            name: node.name.as_str().to_string(),
            is_class: true,
        });
        self.generic_visit_stmt_class_def(node);
        self.scopes.pop();
    }

    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        self.record_assignment_default(&ast::Stmt::AnnAssign(node.clone()));
        self.generic_visit_stmt_ann_assign(node);
    }

    fn visit_stmt_assign(&mut self, node: ast::StmtAssign) {
        self.record_assignment_default(&ast::Stmt::Assign(node.clone()));
        self.generic_visit_stmt_assign(node);
    }

    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        let name = dotted_name(&node.func);
        if name.ends_with(".get") && node.args.len() >= 2 {
            self.record_implicit_default(
                &node.args[1],
                "mapping-get-default",
                name.clone(),
                "mapping get supplies an implicit value outside config ownership",
            );
        } else if name == "getattr" && node.args.len() >= 3 {
            self.record_implicit_default(
                &node.args[2],
                "getattr-default",
                name.clone(),
                "getattr supplies an implicit value outside config ownership",
            );
        } else if name.ends_with(".setdefault") && node.args.len() >= 2 {
            self.record_implicit_default(
                &node.args[1],
                "setdefault-default",
                name.clone(),
                "setdefault creates an implicit value outside config ownership",
            );
        } else if config_kind_for_expr(
            &node.func,
            self.config_kinds,
            self.imports,
            self.module_index,
        )
        .is_some()
            && node.args.is_empty()
            && node.keywords.is_empty()
        {
            self.record_implicit_default(
                &node,
                "empty-config-constructor",
                name,
                "config constructor is called without explicit fields",
            );
        }
        self.generic_visit_expr_call(node);
    }

    fn visit_expr_bool_op(&mut self, node: ast::ExprBoolOp) {
        if matches!(&node.op, ast::BoolOp::Or) && node.values.len() >= 2 {
            if let Some(implicit_default) = node.values.last() {
                if is_literalish_default(
                    implicit_default,
                    self.config_kinds,
                    self.imports,
                    self.module_index,
                ) {
                    self.record_implicit_default(
                        implicit_default,
                        "or-implicit-default",
                        "<or>".to_string(),
                        "boolean or supplies an implicit value outside config ownership",
                    );
                }
            }
        }
        self.generic_visit_expr_bool_op(node);
    }
}
