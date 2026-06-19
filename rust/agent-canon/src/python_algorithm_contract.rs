// @dependency-start
// contract implementation
// responsibility Checks Python amp algorithm-module public surface and nested ownership from AST JSON.
// upstream design ../../../documents/design/jax_util/algorithm_module_contract.md algorithm module contract
// upstream implementation python_structure_hash.rs provides the Python-AST-to-Rust analysis pattern
// downstream implementation main.rs exposes python-algorithm-contract-check
// @dependency-end

use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const DEFAULT_EXCLUDES: &[&str] = &[
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "vendor",
    "python/jax_util.egg-info",
];

const EXPECTED_PUBLIC_NAMES: &[&str] = &[
    "InitializeConfig",
    "SolveConfig",
    "Problem",
    "State",
    "Answer",
    "Info",
    "Algorithm",
    "initialize",
];

const CONTRACT_CLASSES: &[&str] = &["InitializeConfig", "SolveConfig", "Info", "Algorithm"];

const NON_ALGORITHM_IMPORT_ALLOWLIST: &[&str] = &[
    "python/jax_util/base",
    "python/jax_util/canon",
    "python/tests",
    "tests",
];

const STOPPING_POLICY_TYPES: &[&str] = &[
    "ResidualNormConvergenceCriterion",
    "MaxRelativeRayleighResidualCriterion",
    "RuntimeToleranceConfig",
];

const STOPPING_PRIMITIVE_CALLS: &[&str] = &[
    "residual_converged",
    "residual_tolerance",
    "rayleigh_residual_tolerance",
    "forcing_tolerance",
    "reference_residual_norm",
];

const AST_EXTRACTOR: &str = r##"
import ast
import json
import pathlib
import sys


EXPECTED_PUBLIC_NAMES = {
    "InitializeConfig",
    "SolveConfig",
    "Problem",
    "State",
    "Answer",
    "Info",
    "Algorithm",
    "initialize",
}


def module_name(root, path):
    relative = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())
    without_suffix = relative.with_suffix("")
    if without_suffix.name == "__init__":
        without_suffix = without_suffix.parent
    return ".".join(without_suffix.parts)


def ref_name(node):
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = ref_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return ref_name(node.value)
    if isinstance(node, ast.Call):
        return ref_name(node.func)
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def annotation_text(node):
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ref_name(node)


def imports_algorithm_module_protocol(tree):
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.endswith("algorithm_module_protocol"):
                return True
            if any(alias.name == "algorithm_module_protocol" for alias in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name.endswith("algorithm_module_protocol") for alias in node.names):
                return True
    return False


def public_definitions(tree):
    names = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append({"name": node.name, "line": getattr(node, "lineno", 1)})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id != "__all__":
                    names.append({"name": target.id, "line": getattr(node, "lineno", 1)})
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                names.append({"name": target.id, "line": getattr(node, "lineno", 1)})
    return names


def imported_aliases(tree):
    aliases = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("algorithm_module_protocol"):
                    continue
                aliases.append(
                    {
                        "alias": alias.asname or alias.name.rsplit(".", 1)[-1],
                        "module": alias.name,
                        "line": getattr(node, "lineno", 1),
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("algorithm_module_protocol"):
                continue
            for alias in node.names:
                if alias.name == "algorithm_module_protocol":
                    continue
                if node.level:
                    imported = "." * node.level + module
                    imported = f"{imported}.{alias.name}" if module else imported
                else:
                    imported = f"{module}.{alias.name}" if module else alias.name
                aliases.append(
                    {
                        "alias": alias.asname or alias.name,
                        "module": imported,
                        "from_module": module,
                        "name": alias.name,
                        "level": node.level,
                        "line": getattr(node, "lineno", 1),
                    }
                )
    return aliases


def top_level_aliases(tree):
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = node.value
            if value is not None:
                aliases[node.target.id] = annotation_text(value)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                aliases[target.id] = annotation_text(node.value)
    return aliases


def base_facts(node):
    return [ref_name(base) for base in node.bases]


def class_defs(tree):
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields = []
        methods = []
        for child in node.body:
            if isinstance(child, ast.AnnAssign):
                target = ref_name(child.target)
                fields.append(
                    {
                        "name": target,
                        "annotation": annotation_text(child.annotation),
                        "line": getattr(child, "lineno", getattr(node, "lineno", 1)),
                    }
                )
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(child.name)
        classes.append(
            {
                "name": node.name,
                "line": getattr(node, "lineno", 1),
                "bases": base_facts(node),
                "fields": fields,
                "methods": methods,
            }
        )
    return classes


class UsageVisitor(ast.NodeVisitor):
    def __init__(self, aliases):
        self.aliases = set(aliases)
        self.alias_attrs = {}
        self.calls = []
        self.references = []

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id in self.aliases:
            self.alias_attrs.setdefault(node.value.id, set()).add(node.attr)
        name = ref_name(node)
        if name:
            self.references.append({"name": name, "line": getattr(node, "lineno", 1)})
        self.generic_visit(node)

    def visit_Name(self, node):
        self.references.append({"name": node.id, "line": getattr(node, "lineno", 1)})

    def visit_Call(self, node):
        name = ref_name(node.func)
        if name:
            self.calls.append({"name": name, "line": getattr(node, "lineno", 1)})
        self.generic_visit(node)


def usage(tree, aliases):
    visitor = UsageVisitor(alias["alias"] for alias in aliases)
    visitor.visit(tree)
    return {
        "alias_attrs": {
            key: sorted(value) for key, value in sorted(visitor.alias_attrs.items())
        },
        "calls": visitor.calls,
        "references": visitor.references,
    }


def main():
    request = json.load(sys.stdin)
    root = request["root"]
    modules = []
    errors = []
    for path in request["files"]:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8")
            tree = ast.parse(text, filename=path)
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        aliases = imported_aliases(tree)
        modules.append(
            {
                "path": str(pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())).replace("\\", "/"),
                "module": module_name(root, path),
                "imports_amp": imports_algorithm_module_protocol(tree),
                "public_definitions": public_definitions(tree),
                "imports": aliases,
                "aliases": top_level_aliases(tree),
                "classes": class_defs(tree),
                "usage": usage(tree, aliases),
            }
        )
    print(json.dumps({"modules": modules, "errors": errors}, sort_keys=True))


if __name__ == "__main__":
    main()
"##;

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    paths: Vec<String>,
    excludes: Vec<String>,
    format: OutputFormat,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModuleAst {
    path: String,
    module: String,
    imports_amp: bool,
    public_definitions: BTreeMap<String, usize>,
    imports: BTreeMap<String, ImportAst>,
    aliases: BTreeMap<String, String>,
    classes: BTreeMap<String, ClassAst>,
    alias_attrs: BTreeMap<String, BTreeSet<String>>,
    calls: Vec<NamedLine>,
    references: Vec<NamedLine>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ImportAst {
    module: String,
    from_module: String,
    imported_name: String,
    level: usize,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ClassAst {
    line: usize,
    bases: Vec<String>,
    fields: Vec<FieldAst>,
    methods: BTreeSet<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FieldAst {
    name: String,
    annotation: String,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NamedLine {
    name: String,
    line: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Finding {
    path: String,
    line: usize,
    kind: String,
    subject: String,
    detail: String,
}

impl Finding {
    fn new(path: &str, line: usize, kind: &str, subject: &str, detail: &str) -> Self {
        Self {
            path: path.to_string(),
            line,
            kind: kind.to_string(),
            subject: subject.to_string(),
            detail: detail.to_string(),
        }
    }

    fn render(&self) -> String {
        format!(
            "PY_ALGORITHM_CONTRACT_FINDING={}:{}:{}:{}:{}",
            self.path, self.line, self.kind, self.subject, self.detail
        )
    }
}

#[derive(Debug, PartialEq, Eq)]
struct Report {
    files: usize,
    algorithm_modules: Vec<String>,
    findings: Vec<Finding>,
    parse_errors: Vec<String>,
    format: OutputFormat,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args).and_then(run_check) {
        Ok(report) => {
            render_report(&report);
            if report.findings.is_empty() && report.parse_errors.is_empty() {
                0
            } else {
                1
            }
        }
        Err(message) => {
            eprintln!("PY_ALGORITHM_CONTRACT=fail");
            eprintln!("PY_ALGORITHM_CONTRACT_FINDING=tool:1:tool_error:arguments:{message}");
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
        let mut excludes = DEFAULT_EXCLUDES
            .iter()
            .map(|value| value.to_string())
            .collect::<Vec<_>>();
        let mut format = OutputFormat::Text;
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    root = PathBuf::from(value_after(args, index, "--root")?);
                    index += 2;
                }
                "--exclude" => {
                    excludes.push(value_after(args, index, "--exclude")?);
                    index += 2;
                }
                "--format" => {
                    format = match value_after(args, index, "--format")?.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        value => return Err(format!("--format must be text or json, got {value}")),
                    };
                    index += 2;
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
            root,
            paths,
            excludes,
            format,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn run_check(args: Args) -> Result<Report, String> {
    let root = resolve_like_cwd(&args.root);
    let files = source_files(&root, &args.paths, &args.excludes);
    let payload = extract_ast_modules(&root, &files)?;
    let parse_errors = payload
        .get("errors")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|error| {
            format!(
                "{}:{}",
                error
                    .get("path")
                    .and_then(Value::as_str)
                    .unwrap_or("<unknown>"),
                error
                    .get("error")
                    .and_then(Value::as_str)
                    .unwrap_or("parse-error")
            )
        })
        .collect::<Vec<_>>();
    let modules = payload
        .get("modules")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .map(parse_module_ast)
        .collect::<Result<Vec<_>, _>>()?;
    let algorithm_modules = modules
        .iter()
        .filter(|module| module_is_algorithm(module))
        .map(|module| module.path.clone())
        .collect::<Vec<_>>();
    let findings = analyze_modules(&modules);
    Ok(Report {
        files: files.len(),
        algorithm_modules,
        findings,
        parse_errors,
        format: args.format,
    })
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

fn source_files(root: &Path, raw_paths: &[String], excludes: &[String]) -> Vec<PathBuf> {
    let targets = if raw_paths.is_empty() {
        vec![root.to_path_buf()]
    } else {
        raw_paths.iter().map(|path| root.join(path)).collect()
    };
    let mut files = BTreeSet::new();
    for target in targets {
        collect_python_files(root, &target, excludes, &mut files);
    }
    files.into_iter().collect()
}

fn collect_python_files(
    root: &Path,
    target: &Path,
    excludes: &[String],
    files: &mut BTreeSet<PathBuf>,
) {
    if excluded(root, target, excludes) {
        return;
    }
    if target.is_file() {
        if target.extension().and_then(|value| value.to_str()) == Some("py") {
            files.insert(fs::canonicalize(target).unwrap_or_else(|_| target.to_path_buf()));
        }
        return;
    }
    let Ok(entries) = fs::read_dir(target) else {
        return;
    };
    for entry in entries.flatten() {
        collect_python_files(root, &entry.path(), excludes, files);
    }
}

fn excluded(root: &Path, path: &Path, excludes: &[String]) -> bool {
    let relative = path.strip_prefix(root).unwrap_or(path);
    if relative
        .components()
        .any(|component| component.as_os_str().to_string_lossy().starts_with('.'))
    {
        return true;
    }
    let relative_text = relative.to_string_lossy().replace('\\', "/");
    excludes.iter().any(|pattern| {
        let pattern = pattern.trim().trim_matches('/');
        !pattern.is_empty()
            && (relative_text == pattern
                || relative_text.starts_with(&format!("{pattern}/"))
                || relative_text.split('/').any(|part| part == pattern))
    })
}

fn extract_ast_modules(root: &Path, files: &[PathBuf]) -> Result<Value, String> {
    let request = json!({
        "root": root,
        "files": files,
    });
    let mut child = Command::new("python3")
        .arg("-c")
        .arg(AST_EXTRACTOR)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("failed to start python3 AST extractor: {error}"))?;
    {
        let stdin = child
            .stdin
            .as_mut()
            .ok_or_else(|| "failed to open python3 stdin".to_string())?;
        stdin
            .write_all(request.to_string().as_bytes())
            .map_err(|error| format!("failed to write AST request: {error}"))?;
    }
    let output = child
        .wait_with_output()
        .map_err(|error| format!("failed to wait for python3 AST extractor: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "python3 AST extractor failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("failed to parse AST extractor JSON: {error}"))
}

fn parse_module_ast(value: Value) -> Result<ModuleAst, String> {
    let path = string_field(&value, "path")?;
    let imports = value
        .get("imports")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: imports must be array"))?
        .iter()
        .map(parse_import_ast)
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|item| (item.0, item.1))
        .collect::<BTreeMap<_, _>>();
    let classes = value
        .get("classes")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: classes must be array"))?
        .iter()
        .map(parse_class_ast)
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|item| (item.0, item.1))
        .collect::<BTreeMap<_, _>>();
    Ok(ModuleAst {
        path,
        module: string_field(&value, "module")?,
        imports_amp: value
            .get("imports_amp")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        public_definitions: parse_public_definitions(&value)?,
        imports,
        aliases: parse_string_map(value.get("aliases"))?,
        classes,
        alias_attrs: parse_alias_attrs(&value)?,
        calls: parse_named_lines(
            value
                .get("usage")
                .and_then(|usage| usage.get("calls"))
                .unwrap_or(&Value::Null),
        )?,
        references: parse_named_lines(
            value
                .get("usage")
                .and_then(|usage| usage.get("references"))
                .unwrap_or(&Value::Null),
        )?,
    })
}

fn parse_import_ast(value: &Value) -> Result<(String, ImportAst), String> {
    let alias = string_field(value, "alias")?;
    Ok((
        alias,
        ImportAst {
            module: string_field(value, "module")?,
            from_module: value
                .get("from_module")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            imported_name: value
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            level: value
                .get("level")
                .and_then(Value::as_u64)
                .and_then(|number| usize::try_from(number).ok())
                .unwrap_or(0),
            line: usize_field(value, "line")?,
        },
    ))
}

fn parse_class_ast(value: &Value) -> Result<(String, ClassAst), String> {
    let name = string_field(value, "name")?;
    let fields = value
        .get("fields")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|field| {
            Ok(FieldAst {
                name: string_field(field, "name")?,
                annotation: string_field(field, "annotation")?,
                line: usize_field(field, "line")?,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let methods = value
        .get("methods")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect::<BTreeSet<_>>();
    let bases = value
        .get("bases")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect::<Vec<_>>();
    Ok((
        name,
        ClassAst {
            line: usize_field(value, "line")?,
            bases,
            fields,
            methods,
        },
    ))
}

fn parse_public_definitions(value: &Value) -> Result<BTreeMap<String, usize>, String> {
    value
        .get("public_definitions")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|item| Ok((string_field(item, "name")?, usize_field(item, "line")?)))
        .collect::<Result<BTreeMap<_, _>, String>>()
}

fn parse_string_map(value: Option<&Value>) -> Result<BTreeMap<String, String>, String> {
    let Some(Value::Object(entries)) = value else {
        return Ok(BTreeMap::new());
    };
    Ok(entries
        .iter()
        .filter_map(|(key, value)| value.as_str().map(|text| (key.clone(), text.to_string())))
        .collect())
}

fn parse_alias_attrs(value: &Value) -> Result<BTreeMap<String, BTreeSet<String>>, String> {
    let Some(Value::Object(entries)) = value
        .get("usage")
        .and_then(|usage| usage.get("alias_attrs"))
    else {
        return Ok(BTreeMap::new());
    };
    Ok(entries
        .iter()
        .map(|(key, value)| {
            let attrs = value
                .as_array()
                .cloned()
                .unwrap_or_default()
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<BTreeSet<_>>();
            (key.clone(), attrs)
        })
        .collect())
}

fn parse_named_lines(value: &Value) -> Result<Vec<NamedLine>, String> {
    Ok(value
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(|item| {
            Some(NamedLine {
                name: item.get("name")?.as_str()?.to_string(),
                line: item
                    .get("line")
                    .and_then(Value::as_u64)
                    .and_then(|number| usize::try_from(number).ok())
                    .unwrap_or(1),
            })
        })
        .collect())
}

fn string_field(value: &Value, field: &str) -> Result<String, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| format!("field {field} must be a string"))
}

fn usize_field(value: &Value, field: &str) -> Result<usize, String> {
    value
        .get(field)
        .and_then(Value::as_u64)
        .and_then(|number| usize::try_from(number).ok())
        .ok_or_else(|| format!("field {field} must be a positive integer"))
}

fn analyze_modules(modules: &[ModuleAst]) -> Vec<Finding> {
    let mut findings = Vec::new();
    let algorithm_modules = modules
        .iter()
        .filter(|module| module_is_algorithm(module))
        .map(|module| module.module.clone())
        .collect::<BTreeSet<_>>();
    for module in modules {
        if !module_is_algorithm(module) {
            continue;
        }
        findings.extend(analyze_algorithm_module_surface(module));
        let algorithm_aliases = algorithm_aliases(module, &algorithm_modules);
        findings.extend(analyze_nested_contract(module, &algorithm_aliases));
        findings.extend(analyze_legacy_stopping_usage(module));
    }
    findings.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.line.cmp(&right.line))
            .then_with(|| left.kind.cmp(&right.kind))
            .then_with(|| left.subject.cmp(&right.subject))
    });
    findings
}

fn algorithm_aliases(module: &ModuleAst, algorithm_modules: &BTreeSet<String>) -> BTreeSet<String> {
    module
        .imports
        .iter()
        .filter_map(|(alias, import)| {
            let candidates = import_candidate_modules(&module.module, import);
            if candidates
                .iter()
                .any(|candidate| module_name_matches(candidate, algorithm_modules))
            {
                return Some(alias.clone());
            }
            module.alias_attrs.get(alias).and_then(|attrs| {
                (!required_contract_classes(attrs).is_empty()).then(|| alias.clone())
            })
        })
        .collect()
}

fn import_candidate_modules(current_module: &str, import: &ImportAst) -> Vec<String> {
    if import.level > 0 {
        let base = resolve_relative_import(current_module, import.level, &import.from_module);
        if let Some(base) = base {
            let mut candidates = vec![base.clone()];
            if !import.imported_name.is_empty() && import.imported_name != "*" {
                candidates.push(format!("{base}.{}", import.imported_name));
            }
            return candidates;
        }
        return Vec::new();
    }
    if !import.from_module.is_empty() {
        let mut candidates = vec![import.from_module.clone()];
        if !import.imported_name.is_empty() && import.imported_name != "*" {
            candidates.push(format!("{}.{}", import.from_module, import.imported_name));
        }
        return candidates;
    }
    vec![import.module.clone()]
}

fn resolve_relative_import(
    current_module: &str,
    level: usize,
    from_module: &str,
) -> Option<String> {
    let mut package = current_module
        .split('.')
        .map(str::to_string)
        .collect::<Vec<_>>();
    package.pop();
    let drop_count = level.saturating_sub(1);
    if drop_count > package.len() {
        return None;
    }
    let keep = package.len() - drop_count;
    package.truncate(keep);
    if !from_module.is_empty() {
        package.extend(from_module.split('.').map(str::to_string));
    }
    (!package.is_empty()).then(|| package.join("."))
}

fn module_name_matches(candidate: &str, algorithm_modules: &BTreeSet<String>) -> bool {
    let normalized = candidate.trim_start_matches('.');
    algorithm_modules.iter().any(|module| {
        module == normalized
            || module
                .strip_prefix("python.")
                .map(|tail| tail == normalized)
                .unwrap_or(false)
            || normalized
                .strip_prefix("python.")
                .map(|tail| tail == module)
                .unwrap_or(false)
            || module.ends_with(&format!(".{normalized}"))
    })
}

fn module_is_algorithm(module: &ModuleAst) -> bool {
    if !module.imports_amp {
        return false;
    }
    if module
        .public_definitions
        .keys()
        .any(|name| EXPECTED_PUBLIC_NAMES.contains(&name.as_str()))
    {
        return true;
    }
    !NON_ALGORITHM_IMPORT_ALLOWLIST
        .iter()
        .any(|prefix| module.path == *prefix || module.path.starts_with(&format!("{prefix}/")))
}

fn analyze_algorithm_module_surface(module: &ModuleAst) -> Vec<Finding> {
    let mut findings = Vec::new();
    for name in EXPECTED_PUBLIC_NAMES {
        if !module.public_definitions.contains_key(*name) {
            findings.push(Finding::new(
                &module.path,
                1,
                "missing_algorithm_public_surface",
                name,
                "define standard amp algorithm module public surface",
            ));
        }
    }
    match module.classes.get("Algorithm") {
        Some(class_node) if class_node.methods.contains("__call__") => {}
        Some(class_node) => findings.push(Finding::new(
            &module.path,
            class_node.line,
            "algorithm_not_callable",
            "Algorithm",
            "define __call__(Problem, State, SolveConfig) returning Answer, State, Info",
        )),
        None => findings.push(Finding::new(
            &module.path,
            1,
            "missing_algorithm_function_object",
            "Algorithm",
            "define callable Algorithm",
        )),
    }
    findings
}

fn analyze_nested_contract(
    module: &ModuleAst,
    algorithm_aliases: &BTreeSet<String>,
) -> Vec<Finding> {
    let mut findings = Vec::new();
    for (dependency_alias, attrs) in &module.alias_attrs {
        if !algorithm_aliases.contains(dependency_alias) {
            continue;
        }
        let required = required_contract_classes(attrs);
        if required.is_empty() {
            continue;
        }
        for contract_class in required {
            let Some(class_node) = module.classes.get(&contract_class) else {
                findings.push(Finding::new(
                    &module.path,
                    1,
                    "missing_contract_class",
                    &format!("{dependency_alias}.{contract_class}"),
                    &format!("define {contract_class}"),
                ));
                continue;
            };
            if class_annotations_contain(module, class_node, dependency_alias, &contract_class) {
                continue;
            }
            let detail = nested_field_detail(module, class_node, dependency_alias, &contract_class);
            findings.push(Finding::new(
                &module.path,
                class_node.line,
                "missing_nested_field",
                &format!("{dependency_alias}.{contract_class}"),
                &detail,
            ));
        }
    }
    findings
}

fn required_contract_classes(attrs: &BTreeSet<String>) -> Vec<String> {
    let mut required = BTreeSet::new();
    for attr in attrs {
        if CONTRACT_CLASSES.contains(&attr.as_str()) {
            required.insert(attr.clone());
        }
    }
    if attrs.contains("initialize") {
        for class_name in CONTRACT_CLASSES {
            required.insert((*class_name).to_string());
        }
    }
    if required.is_empty() && attrs.len() == 1 && attrs.contains("Problem") {
        return Vec::new();
    }
    required.into_iter().collect()
}

fn class_annotations_contain(
    module: &ModuleAst,
    class_node: &ClassAst,
    dependency_alias: &str,
    dependency_class: &str,
) -> bool {
    let required = format!("{dependency_alias}.{dependency_class}");
    class_node.fields.iter().any(|field| {
        field.annotation.contains(&required)
            || expand_annotation(&field.annotation, &module.aliases).contains(&required)
    })
}

fn expand_annotation(annotation: &str, aliases: &BTreeMap<String, String>) -> String {
    let mut current = annotation.to_string();
    let mut seen = BTreeSet::new();
    while let Some(next) = aliases.get(&current) {
        if !seen.insert(current.clone()) {
            break;
        }
        current = next.clone();
    }
    current
}

fn nested_field_detail(
    module: &ModuleAst,
    class_node: &ClassAst,
    dependency_alias: &str,
    dependency_class: &str,
) -> String {
    let field_hint = dependency_alias.to_lowercase();
    let generic = format!("amp.{dependency_class}");
    let untyped = class_node.fields.iter().find(|field| {
        field.name.to_lowercase().contains(&field_hint)
            && (field.annotation == "Any"
                || field.annotation.contains(&generic)
                || expand_annotation(&field.annotation, &module.aliases).contains(&generic))
    });
    if let Some(field) = untyped {
        return format!(
            "field-{}-uses-{}; annotate as {}.{}",
            field.name, field.annotation, dependency_alias, dependency_class
        );
    }
    format!("add-field-annotated-{dependency_alias}.{dependency_class}")
}

fn analyze_legacy_stopping_usage(module: &ModuleAst) -> Vec<Finding> {
    let mut findings = Vec::new();
    let solve_config = module.classes.get("SolveConfig");
    if let Some(class_node) = solve_config {
        for field in &class_node.fields {
            if STOPPING_POLICY_TYPES.iter().any(|name| {
                annotation_mentions(module, &field.annotation, name)
                    && !module_defines_name(module, name)
            }) {
                findings.push(Finding::new(
                    &module.path,
                    field.line,
                    "legacy_stopping_policy_field",
                    &field.name,
                    "use imported stopping.SolveConfig so the nested algorithm contract is inferred",
                ));
            }
        }
    }
    for call in &module.calls {
        if STOPPING_PRIMITIVE_CALLS.iter().any(|name| {
            call.name.ends_with(&format!(".{name}"))
                || (call.name == *name && !module_defines_name(module, name))
        }) {
            findings.push(Finding::new(
                &module.path,
                call.line,
                "stopping_primitive_direct_call",
                &call.name,
                "call the configured stopping object and record stopping.Info",
            ));
        }
    }
    findings
}

fn module_defines_name(module: &ModuleAst, name: &str) -> bool {
    module.public_definitions.contains_key(name) || module.classes.contains_key(name)
}

fn annotation_mentions(module: &ModuleAst, annotation: &str, needle: &str) -> bool {
    annotation.contains(needle) || expand_annotation(annotation, &module.aliases).contains(needle)
}

fn render_report(report: &Report) {
    match report.format {
        OutputFormat::Json => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "summary": {
                        "files": report.files,
                        "algorithm_modules": report.algorithm_modules.len(),
                        "findings": report.findings.len(),
                        "parse_errors": report.parse_errors.len(),
                        "status": if report.findings.is_empty() && report.parse_errors.is_empty() { "pass" } else { "fail" },
                    },
                    "algorithm_modules": report.algorithm_modules,
                    "parse_errors": report.parse_errors,
                    "findings": report.findings.iter().map(|finding| json!({
                        "path": finding.path,
                        "line": finding.line,
                        "kind": finding.kind,
                        "subject": finding.subject,
                        "detail": finding.detail,
                    })).collect::<Vec<_>>(),
                }))
                .expect("json payload serializes")
            );
        }
        OutputFormat::Text => {
            for error in &report.parse_errors {
                println!("PY_ALGORITHM_CONTRACT_PARSE_ERROR={error}");
            }
            for finding in &report.findings {
                println!("{}", finding.render());
            }
            println!("PY_ALGORITHM_CONTRACT_FILES={}", report.files);
            println!(
                "PY_ALGORITHM_CONTRACT_MODULES={}",
                report.algorithm_modules.len()
            );
            println!("PY_ALGORITHM_CONTRACT_FINDINGS={}", report.findings.len());
            println!(
                "PY_ALGORITHM_CONTRACT={}",
                if report.findings.is_empty() && report.parse_errors.is_empty() {
                    "pass"
                } else {
                    "fail"
                }
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn field(name: &str, annotation: &str) -> FieldAst {
        FieldAst {
            name: name.to_string(),
            annotation: annotation.to_string(),
            line: 10,
        }
    }

    fn class(line: usize, fields: Vec<FieldAst>, methods: &[&str]) -> ClassAst {
        ClassAst {
            line,
            bases: Vec::new(),
            fields,
            methods: methods.iter().map(|name| (*name).to_string()).collect(),
        }
    }

    fn algorithm_module() -> ModuleAst {
        let mut public_definitions = BTreeMap::new();
        for name in EXPECTED_PUBLIC_NAMES {
            public_definitions.insert((*name).to_string(), 1);
        }
        ModuleAst {
            path: "python/pkg/parent.py".to_string(),
            module: "python.pkg.parent".to_string(),
            imports_amp: true,
            public_definitions,
            imports: BTreeMap::from([
                (
                    "child".to_string(),
                    ImportAst {
                        module: ".child".to_string(),
                        from_module: String::new(),
                        imported_name: "child".to_string(),
                        level: 1,
                        line: 1,
                    },
                ),
                (
                    "stopping".to_string(),
                    ImportAst {
                        module: "python.jax_util.base.stopping".to_string(),
                        from_module: String::new(),
                        imported_name: String::new(),
                        level: 0,
                        line: 2,
                    },
                ),
            ]),
            aliases: BTreeMap::new(),
            classes: BTreeMap::from([
                (
                    "InitializeConfig".to_string(),
                    class(
                        3,
                        vec![field("child_initialize", "child.InitializeConfig")],
                        &[],
                    ),
                ),
                (
                    "SolveConfig".to_string(),
                    class(
                        6,
                        vec![
                            field("child_solve", "child.SolveConfig"),
                            field("stopping", "stopping.SolveConfig"),
                        ],
                        &[],
                    ),
                ),
                (
                    "Info".to_string(),
                    class(
                        9,
                        vec![
                            field("child_info", "child.Info"),
                            field("stopping_info", "stopping.Info"),
                        ],
                        &[],
                    ),
                ),
                (
                    "Algorithm".to_string(),
                    class(
                        12,
                        vec![
                            field("child_algorithm", "child.Algorithm"),
                            field("stopping_algorithm", "stopping.Algorithm"),
                        ],
                        &["__call__"],
                    ),
                ),
            ]),
            alias_attrs: BTreeMap::from([
                (
                    "child".to_string(),
                    ["initialize".to_string()].into_iter().collect(),
                ),
                (
                    "stopping".to_string(),
                    [
                        "Algorithm".to_string(),
                        "Info".to_string(),
                        "SolveConfig".to_string(),
                    ]
                    .into_iter()
                    .collect(),
                ),
            ]),
            calls: Vec::new(),
            references: vec![NamedLine {
                name: "stopping.SolveConfig".to_string(),
                line: 6,
            }],
        }
    }

    #[test]
    fn compliant_nested_and_stopping_contract_passes() {
        let modules = vec![algorithm_module()];
        assert_eq!(analyze_modules(&modules), Vec::new());
    }

    #[test]
    fn missing_child_info_is_reported() {
        let mut module = algorithm_module();
        module
            .classes
            .get_mut("Info")
            .expect("Info fixture")
            .fields
            .retain(|field| field.name != "child_info");
        let findings = analyze_modules(&[module]);
        assert!(findings.iter().any(|finding| {
            finding.kind == "missing_nested_field" && finding.subject == "child.Info"
        }));
    }

    #[test]
    fn direct_base_stopping_policy_is_reported() {
        let mut module = algorithm_module();
        module.classes.insert(
            "SolveConfig".to_string(),
            class(
                6,
                vec![field("stopping", "ResidualNormConvergenceCriterion")],
                &[],
            ),
        );
        module.calls.push(NamedLine {
            name: "residual_converged".to_string(),
            line: 44,
        });
        let findings = analyze_modules(&[module]);
        assert!(findings
            .iter()
            .any(|finding| finding.kind == "legacy_stopping_policy_field"));
        assert!(findings
            .iter()
            .any(|finding| finding.kind == "stopping_primitive_direct_call"));
    }

    #[test]
    fn stopping_primitive_definition_module_is_not_legacy_usage() {
        let mut module = algorithm_module();
        module
            .public_definitions
            .insert("RuntimeToleranceConfig".to_string(), 20);
        module
            .public_definitions
            .insert("residual_tolerance".to_string(), 40);
        module.classes.insert(
            "RuntimeToleranceConfig".to_string(),
            class(20, Vec::new(), &[]),
        );
        module.classes.insert(
            "SolveConfig".to_string(),
            class(
                6,
                vec![field("runtime_tolerance", "RuntimeToleranceConfig")],
                &[],
            ),
        );
        module.calls.push(NamedLine {
            name: "residual_tolerance".to_string(),
            line: 44,
        });
        let findings = analyze_modules(&[module]);
        assert!(!findings
            .iter()
            .any(|finding| finding.kind == "legacy_stopping_policy_field"));
        assert!(!findings
            .iter()
            .any(|finding| finding.kind == "stopping_primitive_direct_call"));
    }

    #[test]
    fn amp_algorithm_module_requires_standard_surface_and_callable_algorithm() {
        let mut public_definitions = BTreeMap::new();
        public_definitions.insert("Algorithm".to_string(), 20);
        let module = ModuleAst {
            path: "python/pkg/thin_algorithm.py".to_string(),
            module: "python.pkg.thin_algorithm".to_string(),
            imports_amp: true,
            public_definitions,
            imports: BTreeMap::new(),
            aliases: BTreeMap::new(),
            classes: BTreeMap::from([("Stopping".to_string(), class(20, Vec::new(), &[]))]),
            alias_attrs: BTreeMap::new(),
            calls: Vec::new(),
            references: Vec::new(),
        };
        let findings = analyze_modules(&[module]);
        assert!(findings
            .iter()
            .any(|finding| finding.kind == "missing_algorithm_public_surface"
                && finding.subject == "Info"));
        assert!(findings
            .iter()
            .any(|finding| finding.kind == "missing_algorithm_function_object"));
    }
}
