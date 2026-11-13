// @dependency-start
// contract implementation
// responsibility Owns native Python and C++ OOP readability observations and their mechanical reports.
// upstream design ../../../../../../documents/conventions/object-oriented-design.md owns the boundary policy
// upstream implementation ../python_ast.rs shares Python source and AST operations
// downstream test ../../../../../../tests/agent_tools/test_analyze_oop_readability.py preserves public analyzer behavior
// @dependency-end

use rustpython_ast::bigint::BigInt;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
pub(crate) struct Thresholds {
    pub public_methods: BigInt,
    pub instance_attributes: BigInt,
    pub parameters: BigInt,
    pub complexity: BigInt,
    pub public_fields: BigInt,
    pub base_classes: BigInt,
    pub module_helpers: BigInt,
}
impl Default for Thresholds {
    fn default() -> Self {
        Self {
            public_methods: 12.into(),
            instance_attributes: 10.into(),
            parameters: 6.into(),
            complexity: 25.into(),
            public_fields: 8.into(),
            base_classes: 2.into(),
            module_helpers: 8.into(),
        }
    }
}
pub(crate) fn integer_value(value: &BigInt) -> Value {
    serde_json::from_str(&value.to_string()).expect("BigInt renders a valid JSON integer")
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct Finding {
    pub path: String,
    pub line: usize,
    pub language: String,
    pub severity: String,
    pub kind: String,
    pub symbol: String,
    pub evidence: Value,
    pub contract: Value,
    pub guidance: String,
}

impl Finding {
    pub(crate) fn signal(&self) -> &'static str {
        if self.severity == "error" {
            "error"
        } else if [
            "cognitive_complexity",
            "public_methods",
            "instance_attributes",
            "parameters",
            "module_helper_bucket",
        ]
        .contains(&self.kind.as_str())
        {
            "review"
        } else {
            "gate"
        }
    }

    fn identity(&self) -> (&str, &str, &str, &str, &str, &str) {
        (
            &self.path,
            &self.language,
            &self.severity,
            &self.kind,
            &self.symbol,
            &self.guidance,
        )
    }

    fn boundary(&self) -> &'static str {
        match self.kind.as_str() {
            "vague_class_name"
            | "public_methods"
            | "module_helper_name"
            | "module_helper_bucket"
            | "static_method_namespace"
            | "thin_class"
            | "method_without_self_use"
            | "stateless_callable_class" => "owner_overlap",
            "public_fields" | "state_heavy_public_surface" | "instance_attributes" => {
                "state_ownership"
            }
            "base_classes"
            | "redundant_class_boundary"
            | "mixed_morphism_effect"
            | "identity_function"
            | "pass_through_function" => "dependency_boundary",
            _ => "api_boundary",
        }
    }

    fn principles(&self) -> Vec<&'static str> {
        match self.kind.as_str() {
            "cognitive_complexity" => vec!["single responsibility", "open/closed"],
            "public_methods" | "public_fields" => {
                vec!["single responsibility", "interface segregation"]
            }
            "parameters" => vec!["interface segregation"],
            "base_classes" => vec!["liskov substitution"],
            "missing_public_annotations" => vec!["dependency inversion"],
            "optional_boundary" => vec![
                "open/closed",
                "interface segregation",
                "dependency inversion",
            ],
            "none_runtime_branch" | "null_runtime_branch" => vec!["open/closed"],
            "syntax_error" => Vec::new(),
            _ => vec!["single responsibility"],
        }
    }

    fn payload(&self) -> Value {
        let mut value = serde_json::to_value(self).unwrap();
        let (dimension, explanation, action) = facts(&self.kind);
        let object = value.as_object_mut().unwrap();
        object.insert("dimension".into(), json!(dimension));
        object.insert("explanation".into(), json!(explanation));
        object.insert("recommended_action".into(), json!(action));
        object.insert("solid_principles".into(), json!(self.principles()));
        object.insert("typed_boundary_evidence".into(),json!({"property":self.kind,"boundary":self.boundary(),
            "evidence_owner":"oop-readability-checker","source_ref":format!("{}:{}",self.path,self.line),
            "observation":display(&self.evidence),"contract":display(&self.contract)}));
        value
    }
}

fn display(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}
fn facts(kind: &str) -> (&'static str, &'static str, &'static str) {
    match kind {
        "identity_function"=>("mathematical redundancy","The operation is an identity morphism that returns an input unchanged.","Remove the wrapper unless the name carries a documented domain contract."),
        "pass_through_function"=>("mathematical redundancy","The operation only delegates to another callable without changing the domain or codomain.","Inline the call or make the adapter contract explicit."),
        "stateless_callable_class"=>("mathematical redundancy","The class is equivalent to a plain function because it has no owned state.","Use a function unless object identity, protocol conformance, or lifecycle is required."),
        "trivial_format_function"=>("mathematical redundancy","The operation only formats an existing value and does not add a domain-level structure.","Inline the formatting or give the presentation boundary an explicit domain contract."),
        "vague_class_name"=>("responsibility naming","The public type name does not expose a domain responsibility.","Rename the boundary around the domain concept it owns."),
        "cognitive_complexity"=>("control-flow readability","Nested control flow makes the operation hard to compose mentally.","Review whether branch meaning can be named or flattened without adding accidental boundaries."),
        "public_methods"=>("public surface width","The public API is wide enough to suggest more than one class responsibility.","Review caller roles and refine the interface only when responsibilities are independent."),
        "public_fields"=>("state ownership","Public state is exposed directly instead of being owned by a boundary.","Hide mutable state behind a value object, accessor, or state owner."),
        "state_heavy_public_surface"=>("state ownership","The type exposes more data than behavior, so ownership and invariants are unclear.","Confirm it is a value object; otherwise move state behind a behavior boundary."),
        "instance_attributes"=>("state ownership","The object owns enough member state that lifecycle and invariants are hard to audit.","Review whether the existing state has a stable value object or state-owner boundary."),
        "static_method_namespace"=>("class necessity","The class behaves as a namespace rather than a state or contract boundary.","Use module functions or a real object with owned state and invariants."),
        "thin_class"=>("class necessity","The class has little state or behavior, so its boundary may be accidental.","Confirm it is a value object or protocol; otherwise use a function or existing type."),
        "redundant_class_boundary"=>("class necessity","Dependency sources only construct the class and never use it as a type boundary.","Inline the boundary, use a function, or document the missing lifecycle contract."),
        "method_without_self_use"=>("class cohesion","The method does not use object state, weakening the class responsibility boundary.","Move pure behavior to a function/service or make the state dependency explicit."),
        "module_helper_name"=>("helper locality","A module-level helper name hides the domain morphism it performs.","Inline it locally or rename it to a typed, domain-specific transform."),
        "module_helper_bucket"=>("helper locality","The module has many helper-shaped public operations.","Review whether helpers can stay local to callers or whether an existing domain service boundary is missing."),
        "parameters"=>("input boundary","The callable takes enough inputs that the domain shape is not explicit.","Review whether the inputs form a stable named domain shape before grouping them."),
        "base_classes"=>("composition boundary","The type depends on a wide inheritance surface.","Prefer composition unless each base is a true substitutable contract."),
        "optional_boundary"=>("typed boundary","The public boundary accepts Optional/Any-shaped inputs that blur domain variants.","Split variants into typed entrypoints, value objects, protocols, or explicit variants."),
        "missing_public_annotations"=>("typed boundary","A public Python boundary is missing type information.","Add input and return annotations so static analysis can carry the contract."),
        "none_runtime_branch"=>("typed boundary","The operation routes behavior through None checks instead of explicit types.","Replace None-driven routing with typed variants or separate entrypoints."),
        "null_runtime_branch"=>("typed boundary","The C++ operation routes behavior through null checks.","Use references, optional, variant, or explicit prevalidated handles."),
        "mixed_morphism_effect"=>("morphism/effect separation","The operation returns a value while also crossing an effect boundary.","Separate pure A -> B transforms from IO, mutation, process, or resource effects."),
        "syntax_error"=>("parseability","The source cannot be parsed, so readability analysis is incomplete.","Fix parseability before trusting readability metrics for this file."),
        _=>("readability","The static pattern increases review cost.","Inspect the local responsibility boundary."),
    }
}

pub(crate) fn new_findings(current: Vec<Finding>, baseline: &[Finding]) -> Vec<Finding> {
    current
        .into_iter()
        .filter(|finding| {
            !baseline
                .iter()
                .any(|old| old.identity() == finding.identity())
        })
        .collect()
}

pub(crate) fn summary(
    root: &Path,
    files: &[PathBuf],
    findings: &[Finding],
    excludes: &[String],
) -> Value {
    fn counts(values: impl Iterator<Item = String>) -> BTreeMap<String, usize> {
        let mut counts = BTreeMap::new();
        for value in values {
            *counts.entry(value).or_default() += 1;
        }
        counts
    }
    let signals = counts(findings.iter().map(|finding| finding.signal().to_owned()));
    let error = signals.get("error").copied().unwrap_or(0);
    let gate = signals.get("gate").copied().unwrap_or(0);
    let review = signals.get("review").copied().unwrap_or(0);
    let (status, reason) = if error > 0 {
        ("fail", "error-signal")
    } else if gate > 0 {
        ("fail", "gate-signal")
    } else if review > 0 {
        ("review", "review-signal")
    } else {
        ("pass", "clean")
    };
    let mut solid = BTreeMap::from([
        ("single responsibility", 0),
        ("open/closed", 0),
        ("liskov substitution", 0),
        ("interface segregation", 0),
        ("dependency inversion", 0),
    ]);
    for principle in findings.iter().flat_map(Finding::principles) {
        *solid.entry(principle).or_default() += 1;
    }
    let mut top = most_common(findings.iter().map(|finding| finding.path.clone()));
    top.truncate(20);
    json!({"files":files.len(),"scanned_paths":files.iter().map(|file|file.strip_prefix(root).unwrap_or(file).to_string_lossy().into_owned()).collect::<Vec<_>>(),
        "findings":findings.len(),"excluded_patterns":excludes,"status":status,"status_reason":reason,
        "severity_counts":counts(findings.iter().map(|finding|finding.severity.clone())),
        "kind_counts":counts(findings.iter().map(|finding|finding.kind.clone())),
        "review_signal_findings":review,"gate_signal_findings":gate,"error_signal_findings":error,
        "signal_counts":signals,"typed_evidence_owner":"oop-readability-checker",
        "dimension_counts":counts(findings.iter().map(|finding|facts(&finding.kind).0.into())),
        "typed_boundary_counts":counts(findings.iter().map(|finding|finding.boundary().into())),
        "solid_counts":solid,"top_files":top.iter().map(|(path,count)|json!({"path":path,"findings":count})).collect::<Vec<_>>()})
}

fn excluded(path: &Path, patterns: &[String]) -> bool {
    let text = path.to_string_lossy().replace('\\', "/");
    patterns
        .iter()
        .map(|pattern| pattern.trim().trim_matches('/'))
        .filter(|pattern| !pattern.is_empty())
        .any(|pattern| {
            if pattern.contains(['*', '?', '[']) {
                crate::path_resolution::python_fnmatch_case(&text, pattern)
            } else {
                text == pattern
                    || text.starts_with(&format!("{pattern}/"))
                    || path.components().any(|part| part.as_os_str() == pattern)
            }
        })
}

fn files(
    root: &Path,
    targets: &[PathBuf],
    patterns: &[String],
    language: &str,
) -> Result<Vec<PathBuf>, String> {
    let mut pending = if targets.is_empty() {
        vec![(root.to_path_buf(), true)]
    } else {
        targets
            .iter()
            .map(|path| (root.join(path), false))
            .collect()
    };
    let mut selected = std::collections::BTreeSet::new();
    while let Some((path, from_directory)) = pending.pop() {
        let relative = path.strip_prefix(root).unwrap_or(&path);
        if excluded(relative, patterns) {
            continue;
        }
        let metadata = std::fs::symlink_metadata(&path)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        if metadata.is_dir() {
            for entry in std::fs::read_dir(&path).map_err(|error| error.to_string())? {
                let entry = entry.map_err(|error| error.to_string())?;
                let name = entry.file_name();
                let name = name.to_string_lossy();
                if !name.starts_with('.') && name != "__pycache__" {
                    pending.push((entry.path(), true));
                }
            }
        } else if metadata.is_file() || metadata.is_symlink() {
            let resolved = path.canonicalize().map_err(|error| error.to_string())?;
            if !resolved.is_file()
                || excluded(resolved.strip_prefix(root).unwrap_or(&resolved), patterns)
            {
                continue;
            }
            if from_directory
                && relative
                    .components()
                    .any(|part| part.as_os_str().to_string_lossy().starts_with('.'))
            {
                continue;
            }
            let suffix = path
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or("");
            if (language != "cpp" && suffix == "py")
                || (language != "python"
                    && ["c", "cc", "cpp", "cxx", "h", "hpp", "hh", "hxx"].contains(&suffix))
            {
                selected.insert(resolved);
            }
        }
    }
    Ok(selected.into_iter().collect())
}

#[derive(Default)]
struct Options {
    root: PathBuf,
    paths: Vec<PathBuf>,
    excludes: Vec<String>,
    language: String,
    format: String,
    thresholds: Thresholds,
    baseline: String,
    include_snippets: bool,
    snippet_context: BigInt,
    max_findings: BigInt,
    review_prompt: Option<PathBuf>,
    usage_roots: Vec<PathBuf>,
    dependency_modules: Vec<String>,
}

fn parse(args: &[String], default_language: &str) -> Result<Option<Options>, String> {
    let mut options = Options {
        root: PathBuf::from("."),
        language: default_language.into(),
        format: "text".into(),
        snippet_context: 2.into(),
        max_findings: 80.into(),
        ..Options::default()
    };
    let mut index = 0;
    let mut positional = false;
    while index < args.len() {
        let raw = &args[index];
        if raw == "--" {
            positional = true;
            index += 1;
            continue;
        }
        if positional || !raw.starts_with('-') {
            options.paths.push(PathBuf::from(raw));
            index += 1;
            continue;
        }
        if ["-h", "--help"].contains(&raw.as_str()) {
            return Ok(None);
        }
        if raw == "--include-snippets" {
            options.include_snippets = true;
            index += 1;
            continue;
        }
        let (name, inline) = raw
            .split_once('=')
            .map_or((raw.as_str(), None), |(name, value)| (name, Some(value)));
        const NAMES: &[(&str, &str)] = &[
            ("--root", "--root"),
            ("--language", "--language"),
            ("--format", "--format"),
            ("--exclude", "--exclude"),
            ("--baseline-ref", "--baseline-ref"),
            ("--review-prompt-out", "--review-prompt-out"),
            ("--usage-root", "--usage-root"),
            ("--dependency-root", "--dependency-root"),
            ("--dependency-module", "--dependency-module"),
            ("--snippet-context", "--snippet-context"),
            ("--max-report-findings", "--max-report-findings"),
            ("--max-public-methods", "--max-public-methods"),
            ("--max-instance-attributes", "--max-instance-attributes"),
            ("--max-parameters", "--max-parameters"),
            ("--max-cognitive-complexity", "--max-cognitive-complexity"),
            ("--max-public-fields", "--max-public-fields"),
            ("--max-base-classes", "--max-base-classes"),
            ("--max-module-helpers", "--max-module-helpers"),
        ];
        let name = if NAMES.iter().any(|(option, _)| *option == name) {
            name
        } else {
            crate::python_cli_options::resolve_long_option_prefix(name, NAMES)
                .map_err(|_| format!("unrecognized or ambiguous argument: {name}"))?
        };
        let value = inline
            .or_else(|| args.get(index + 1).map(String::as_str))
            .ok_or_else(|| format!("value required: {name}"))?;
        let number = || {
            crate::python_cli_integer::parse(value)
                .ok_or_else(|| format!("invalid integer: {value}"))
        };
        match name {
            "--root" => options.root = PathBuf::from(value),
            "--language" => options.language = value.into(),
            "--format" => options.format = value.into(),
            "--exclude" => options.excludes.push(value.into()),
            "--baseline-ref" => options.baseline = value.into(),
            "--review-prompt-out" => options.review_prompt = Some(PathBuf::from(value)),
            "--usage-root" | "--dependency-root" => options.usage_roots.push(PathBuf::from(value)),
            "--dependency-module" => options.dependency_modules.push(value.into()),
            "--snippet-context" => options.snippet_context = number()?,
            "--max-report-findings" => options.max_findings = number()?,
            "--max-public-methods" => options.thresholds.public_methods = number()?,
            "--max-instance-attributes" => options.thresholds.instance_attributes = number()?,
            "--max-parameters" => options.thresholds.parameters = number()?,
            "--max-cognitive-complexity" => options.thresholds.complexity = number()?,
            "--max-public-fields" => options.thresholds.public_fields = number()?,
            "--max-base-classes" => options.thresholds.base_classes = number()?,
            "--max-module-helpers" => options.thresholds.module_helpers = number()?,
            _ => return Err(format!("unrecognized argument: {name}")),
        }
        index += if inline.is_some() { 1 } else { 2 };
    }
    if !["python", "cpp", "all"].contains(&options.language.as_str())
        || !["text", "json", "markdown"].contains(&options.format.as_str())
    {
        return Err("invalid language or format".into());
    }
    Ok(Some(options))
}

pub fn run(args: &[String], default_language: &str) -> i32 {
    let options = match parse(args, default_language) {
        Ok(Some(options)) => options,
        Ok(None) => {
            println!("usage: agent-canon oop-{default_language}-readability [paths...] [--root ROOT] [--format text|json|markdown]");
            return 0;
        }
        Err(error) => {
            eprintln!("{error}");
            return 2;
        }
    };
    match execute(options) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}

fn execute(options: Options) -> Result<i32, String> {
    let root = options
        .root
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let selected = files(&root, &options.paths, &options.excludes, &options.language)?;
    let mut usage = files(&root, &[], &options.excludes, &options.language)?
        .into_iter()
        .collect::<std::collections::BTreeSet<_>>();
    usage.extend(selected.iter().cloned());
    let mut source_roots = vec![root.clone()];
    for extra in &options.usage_roots {
        let extra = if extra.is_absolute() {
            extra.clone()
        } else {
            root.join(extra)
        };
        if !extra.exists() {
            continue;
        }
        let extra = extra.canonicalize().map_err(|error| error.to_string())?;
        let base = if extra.is_dir() {
            extra.clone()
        } else {
            extra
                .parent()
                .ok_or("usage source parent missing")?
                .to_path_buf()
        };
        usage.extend(files(
            &base,
            &[extra],
            &options.excludes,
            &options.language,
        )?);
        source_roots.push(base);
    }
    for module in &options.dependency_modules {
        let output = std::process::Command::new(
            std::env::var_os("AGENT_CANON_PYTHON_PROVIDER")
                .unwrap_or_else(|| "agent-canon-python-provider".into()),
        )
        .args(["module-location", module])
        .output()
        .map_err(|error| error.to_string())?;
        if !output.status.success() {
            return Err(String::from_utf8_lossy(&output.stderr).into_owned());
        }
        let value: Value =
            serde_json::from_slice(&output.stdout).map_err(|error| error.to_string())?;
        let locations = value["submodule_search_locations"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .collect::<Vec<_>>();
        for location in locations {
            let location = PathBuf::from(location);
            let mut source_root = location.clone();
            for _ in module.split('.') {
                source_root.pop();
            }
            usage.extend(files(&location, &[], &options.excludes, "python")?);
            source_roots.push(source_root);
        }
        if let Some(origin) = value["origin"].as_str().map(PathBuf::from).filter(|path| {
            path.extension().is_some_and(|extension| extension == "py") && path.is_file()
        }) {
            let mut source_root = origin
                .parent()
                .ok_or("module source parent missing")?
                .to_path_buf();
            for _ in module.split('.').skip(1) {
                source_root.pop();
            }
            usage.insert(origin);
            source_roots.push(source_root);
        }
    }
    let cpp_sources = usage
        .iter()
        .filter(|path| !path.extension().is_some_and(|suffix| suffix == "py"))
        .map(|path| {
            cpp_source(path).map(|source| {
                (
                    path.to_string_lossy().into_owned(),
                    crate::oop_cpp::mask(&source),
                )
            })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let python_sources = usage
        .iter()
        .filter(|path| path.extension().is_some_and(|suffix| suffix == "py"))
        .map(|path| {
            std::fs::read_to_string(path)
                .map(|source| (path.to_string_lossy().into_owned(), source))
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let python_usage = crate::oop_python::usage_index(&python_sources, &source_roots);
    let mut findings = Vec::new();
    for path in &selected {
        let source = if path.extension().is_some_and(|suffix| suffix == "py") {
            std::fs::read_to_string(path).map_err(|error| error.to_string())?
        } else {
            cpp_source(path)?
        };
        let relative = path.strip_prefix(&root).unwrap_or(path).to_string_lossy();
        if path.extension().is_some_and(|suffix| suffix == "py") {
            findings.extend(crate::oop_python::analyze_with_usage(
                &relative,
                &source,
                &options.thresholds,
                Some(&python_usage),
                &path.to_string_lossy(),
            ));
        } else {
            findings.extend(crate::oop_cpp::analyze(
                &relative,
                &source,
                &options.thresholds,
            ));
            findings.extend(crate::oop_cpp::dependency_findings(
                &relative,
                &source,
                &cpp_sources,
            ));
        }
    }
    if !options.baseline.is_empty() {
        let baseline = baseline_findings(&root, &selected, &options)?;
        findings = new_findings(findings, &baseline);
    }
    let summary = summary(&root, &selected, &findings, &options.excludes);
    match options.format.as_str() {
        "json" => {
            let mut payloads = findings.iter().map(Finding::payload).collect::<Vec<_>>();
            if options.include_snippets {
                for (payload, finding) in payloads.iter_mut().zip(&findings) {
                    payload["snippet"] = json!(snippet(&root, finding, &options.snippet_context));
                }
            }
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({"summary":summary,"findings":payloads}))
                    .map_err(|error| error.to_string())?
            );
        }
        "markdown" => print!("{}", markdown(&root, &summary, &findings, &options)),
        _ => {
            let mut sorted = findings.iter().collect::<Vec<_>>();
            sorted.sort_by_key(|finding| (&finding.path, finding.line, &finding.kind));
            for finding in sorted {
                println!(
                    "OOP_READABILITY_FINDING={}:{}:{}:{}:{}:{}:evidence={}:contract={}:{}",
                    finding.path,
                    finding.line,
                    finding.language,
                    finding.severity,
                    finding.kind,
                    finding.symbol,
                    display(&finding.evidence),
                    display(&finding.contract),
                    finding.guidance
                );
            }
            for (key, field) in [
                ("FILES", "files"),
                ("FINDINGS", "findings"),
                ("STATUS_REASON", "status_reason"),
                ("ERROR_SIGNAL_FINDINGS", "error_signal_findings"),
                ("GATE_SIGNAL_FINDINGS", "gate_signal_findings"),
                ("REVIEW_SIGNAL_FINDINGS", "review_signal_findings"),
                ("TYPED_BOUNDARY_COUNTS", "typed_boundary_counts"),
            ] {
                println!("OOP_READABILITY_{key}={}", display(&summary[field]));
            }
            println!("OOP_READABILITY={}", display(&summary["status"]));
        }
    }
    if let Some(path) = options.review_prompt {
        write_prompt(&path)?;
    }
    Ok(i32::from(summary["status"] == "fail"))
}

fn cpp_source(path: &Path) -> Result<String, String> {
    let bytes = std::fs::read(path).map_err(|error| error.to_string())?;
    let mut remaining = bytes.as_slice();
    let mut text = String::new();
    loop {
        match std::str::from_utf8(remaining) {
            Ok(value) => {
                text.push_str(value);
                break;
            }
            Err(error) => {
                let valid = error.valid_up_to();
                text.push_str(
                    std::str::from_utf8(&remaining[..valid]).expect("validated UTF-8 prefix"),
                );
                let Some(skip) = error.error_len() else {
                    break;
                };
                remaining = &remaining[valid + skip..];
            }
        }
    }
    Ok(text)
}

fn snippet(root: &Path, finding: &Finding, context: &BigInt) -> String {
    let text = std::fs::read_to_string(root.join(&finding.path)).unwrap_or_default();
    let lines = text.lines().collect::<Vec<_>>();
    let start = (&BigInt::from(finding.line) - context - BigInt::from(1)).max(BigInt::from(0));
    let end = (&BigInt::from(finding.line) + context).min(BigInt::from(lines.len()));
    if end < BigInt::from(0) || start >= end {
        return String::new();
    }
    let start = start.to_string().parse::<usize>().unwrap_or(lines.len());
    let end = end.to_string().parse::<usize>().unwrap_or(lines.len());
    if start >= end {
        return String::new();
    }
    lines[start..end]
        .iter()
        .enumerate()
        .map(|(offset, line)| {
            let number = start + offset + 1;
            let marker = if number == finding.line { '>' } else { ' ' };
            format!("{marker}{number:5}: {line}")
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn baseline_findings(
    root: &Path,
    selected: &[PathBuf],
    options: &Options,
) -> Result<Vec<Finding>, String> {
    let temporary = tempfile::tempdir().map_err(|error| error.to_string())?;
    let output = std::process::Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["ls-tree", "-r", "--name-only", &options.baseline])
        .output()
        .map_err(|error| error.to_string())?;
    if !output.status.success() {
        return Ok(Vec::new());
    }
    for relative in String::from_utf8_lossy(&output.stdout).lines() {
        let relative = Path::new(relative);
        if !relative
            .components()
            .all(|part| matches!(part, std::path::Component::Normal(_)))
        {
            continue;
        }
        if !relative.extension().is_some_and(|suffix| {
            ["py", "c", "cc", "cpp", "cxx", "h", "hpp", "hh", "hxx"]
                .iter()
                .any(|value| suffix == *value)
        }) {
            continue;
        }
        let output = std::process::Command::new("git")
            .arg("-C")
            .arg(root)
            .args([
                "show",
                &format!("{}:{}", options.baseline, relative.to_string_lossy()),
            ])
            .output()
            .map_err(|error| error.to_string())?;
        if !output.status.success() {
            continue;
        }
        let path = temporary.path().join(relative);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        std::fs::write(path, output.stdout).map_err(|error| error.to_string())?;
    }
    let baseline_files = selected
        .iter()
        .filter_map(|path| path.strip_prefix(root).ok())
        .map(|relative| temporary.path().join(relative))
        .filter(|path| path.is_file())
        .collect::<Vec<_>>();
    let usage_files = files(temporary.path(), &[], &options.excludes, &options.language)?;
    let python_sources = usage_files
        .iter()
        .filter(|path| path.extension().is_some_and(|suffix| suffix == "py"))
        .map(|path| {
            std::fs::read_to_string(path)
                .map(|source| (path.to_string_lossy().into_owned(), source))
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let python_usage =
        crate::oop_python::usage_index(&python_sources, &[temporary.path().to_path_buf()]);
    let cpp_sources = usage_files
        .iter()
        .filter(|path| !path.extension().is_some_and(|suffix| suffix == "py"))
        .map(|path| {
            std::fs::read_to_string(path)
                .map(|source| {
                    (
                        path.to_string_lossy().into_owned(),
                        crate::oop_cpp::mask(&source),
                    )
                })
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let mut findings = Vec::new();
    for baseline in baseline_files {
        let relative = baseline
            .strip_prefix(temporary.path())
            .map_err(|error| error.to_string())?;
        let Ok(source) = std::fs::read_to_string(&baseline) else {
            continue;
        };
        if baseline.extension().is_some_and(|suffix| suffix == "py") {
            findings.extend(crate::oop_python::analyze_with_usage(
                &relative.to_string_lossy(),
                &source,
                &options.thresholds,
                Some(&python_usage),
                &baseline.to_string_lossy(),
            ));
        } else {
            findings.extend(crate::oop_cpp::analyze(
                &relative.to_string_lossy(),
                &source,
                &options.thresholds,
            ));
            findings.extend(crate::oop_cpp::dependency_findings(
                &relative.to_string_lossy(),
                &source,
                &cpp_sources,
            ));
        }
    }
    Ok(findings)
}

fn write_prompt(path: &Path) -> Result<(), String> {
    let path = crate::path_resolution::resolve_non_strict(path)?;
    let parent = crate::source_mutation::ensure_file_parent_nofollow(&path)
        .map_err(|error| error.to_string())?;
    let directory = crate::runtime_boundary::RuntimeDirectory::open_nofollow(&parent, false)
        .map_err(|error| error.to_string())?;
    let name = path.file_name().ok_or("review prompt filename missing")?;
    directory.atomic_write_bytes(Path::new(name),concat!("# OOP Readability Reviewer Prompt\n\n",
        "You are a read-only OOP readability documentation reviewer.\n\nInput:\n- Mechanical report: `<path-to-mechanical-report>`\n\nRules:\n",
        "- Do not invent new findings that are not present in the mechanical report.\n- Do not change the checker status, thresholds, or counts.\n",
        "- Treat mechanical findings as reported signals; preserve tool facts separately from reviewer judgment.\n",
        "- Size, public-surface, parameter-count, and complexity findings are boundary review signals, not accepted design defects or split/extract instructions.\n",
        "- Separate false-positive candidates from accepted design risks.\n- Group comments by the report's SOLID Principle Signals section first.\n",
        "- Then cite the OOP dimension for each accepted mechanical finding.\n- For each hotspot, cite `path:line`, `kind`, and the mechanical explanation.\n",
        "- Do not request code edits unless the report identifies a concrete risk.\n\nExpected output:\n- One short executive summary.\n",
        "- A ranked list of mechanical risk clusters.\n- False-positive or intentional-exception candidates.\n- Suggested documentation wording for the run report.\n").as_bytes(),0o644)
        .map_err(|error|error.to_string())
}

fn markdown(root: &Path, summary: &Value, findings: &[Finding], options: &Options) -> String {
    let mut lines=vec!["# OOP Readability Mechanical Report".into(),String::new(),"This report is generated by static boundary observations. Findings are evidence for owner review, not automatic design decisions.".into(),String::new(),"## Summary".into(),String::new()];
    for key in [
        "status",
        "status_reason",
        "files",
        "scanned_paths",
        "findings",
        "error_signal_findings",
        "gate_signal_findings",
        "review_signal_findings",
        "typed_evidence_owner",
        "excluded_patterns",
    ] {
        let value = if ["scanned_paths", "excluded_patterns"].contains(&key) {
            let value = summary[key]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join(", ");
            if value.is_empty() {
                "none".to_owned()
            } else {
                value
            }
        } else {
            display(&summary[key])
        };
        lines.push(format!("- {key}: `{value}`"));
    }
    let mut solid = vec![
        "single responsibility",
        "open/closed",
        "liskov substitution",
        "interface segregation",
        "dependency inversion",
    ];
    solid.sort_by_key(|name| {
        std::cmp::Reverse(summary["solid_counts"][*name].as_u64().unwrap_or(0))
    });
    lines.extend([
        String::new(),
        "## SOLID Principle Signals".into(),
        String::new(),
    ]);
    for name in solid {
        lines.push(format!("- `{name}`: {}", summary["solid_counts"][name]));
    }
    lines.extend([
        String::new(),
        "## Dimensions".into(),
        String::new(),
        "### Typed Boundary Evidence".into(),
        String::new(),
    ]);
    for (name, count) in most_common(findings.iter().map(|finding| finding.boundary().to_owned())) {
        lines.push(format!("- `{name}`: {count}"));
    }
    lines.push(String::new());
    for (name, count) in most_common(
        findings
            .iter()
            .map(|finding| facts(&finding.kind).0.to_owned()),
    ) {
        lines.push(format!("- `{name}`: {count}"));
    }
    lines.extend([String::new(), "## Finding Kinds".into(), String::new()]);
    for (name, count) in most_common(findings.iter().map(|finding| finding.kind.clone())) {
        lines.push(format!("- `{name}`: {count} - {}", facts(&name).1));
    }
    lines.extend([String::new(), "## Hotspot Files".into(), String::new()]);
    for (path, count) in most_common(findings.iter().map(|finding| finding.path.clone()))
        .into_iter()
        .take(20)
    {
        lines.push(format!("- `{path}`: {count}"));
    }
    lines.extend([String::new(), "## Finding Details".into(), String::new()]);
    let mut sorted = findings.iter().collect::<Vec<_>>();
    sorted.sort_by_key(|finding| {
        (
            match finding.severity.as_str() {
                "error" => 0,
                "warn" => 1,
                "info" => 2,
                _ => 9,
            },
            &finding.path,
            finding.line,
            &finding.kind,
        )
    });
    let length = BigInt::from(sorted.len());
    let limit = if options.max_findings < BigInt::from(0) {
        (&length + &options.max_findings).max(BigInt::from(0))
    } else {
        options.max_findings.clone().min(length)
    };
    let limit = limit
        .to_string()
        .parse::<usize>()
        .expect("slice limit is bounded by allocated findings");
    for finding in sorted.iter().take(limit) {
        let (dimension, explanation, action) = facts(&finding.kind);
        lines.extend([
            format!(
                "### `{}:{}` `{}` `{}`",
                finding.path, finding.line, finding.kind, finding.severity
            ),
            String::new(),
            format!("- symbol: `{}`", finding.symbol),
            format!("- dimension: `{dimension}`"),
            format!("- typed_boundary: `{}`", finding.boundary()),
            "- evidence_owner: `oop-readability-checker`".into(),
            format!("- solid_principles: `{}`", finding.principles().join(", ")),
            format!("- observation: `{}`", display(&finding.evidence)),
            format!("- boundary_contract: `{}`", display(&finding.contract)),
            format!("- mechanical_explanation: {explanation}"),
            format!("- reported_action_signal: {action}"),
        ]);
        if options.include_snippets {
            let excerpt = snippet(root, finding, &options.snippet_context);
            if !excerpt.is_empty() {
                lines.extend([String::new(), "```text".into(), excerpt, "```".into()]);
            }
        }
        lines.push(String::new());
    }
    if BigInt::from(findings.len()) > options.max_findings {
        lines.extend([
            format!(
                "_Omitted {} lower-priority findings from this report._",
                BigInt::from(findings.len()) - &options.max_findings
            ),
            String::new(),
        ]);
    }
    lines.join("\n").trim_end().to_owned() + "\n"
}

fn most_common(values: impl Iterator<Item = String>) -> Vec<(String, usize)> {
    let mut values = values.fold(Vec::<(String, usize)>::new(), |mut counts, value| {
        if let Some((_, count)) = counts.iter_mut().find(|(name, _)| *name == value) {
            *count += 1;
        } else {
            counts.push((value, 1));
        }
        counts
    });
    values.sort_by_key(|(_, count)| std::cmp::Reverse(*count));
    values
}
