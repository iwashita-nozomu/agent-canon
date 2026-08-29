// @dependency-start
// contract implementation
// responsibility Checks Python algorithm-module public surface, nested ownership, and diagnostics from AST JSON.
// upstream design ../../../../../documents/design/jax_util/algorithm_module_contract.md algorithm module contract
// upstream implementation python_structure_hash.rs provides the Python-AST-to-Rust analysis pattern
// downstream implementation main.rs exposes python-algorithm-contract-check
// @dependency-end

use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
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
const ALLOWED_EXTRA_PUBLIC_PREFIXES: &[&str] = &["STATUS_"];

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


def module_name(root, path):
    relative = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())
    without_suffix = relative.with_suffix("")
    if without_suffix.name == "__init__":
        without_suffix = without_suffix.parent
    return ".".join(without_suffix.parts)


def relative_path(root, path):
    return str(pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())).replace("\\", "/")


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
    definitions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                definitions.append({"name": node.name, "line": getattr(node, "lineno", 1), "kind": "class"})
        elif isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_"):
                definitions.append({"name": node.name, "line": getattr(node, "lineno", 1), "kind": "function"})
        elif isinstance(node, ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                definitions.append({"name": node.name, "line": getattr(node, "lineno", 1), "kind": "async_function"})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id != "__all__":
                    definitions.append({"name": target.id, "line": getattr(node, "lineno", 1), "kind": "assignment"})
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id != "__all__":
                definitions.append({"name": target.id, "line": getattr(node, "lineno", 1), "kind": "annotation"})
    return definitions


def literal_string_sequence(value):
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return None
    names = []
    for element in value.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        names.append(element.value)
    return names


def all_state(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            names = literal_string_sequence(node.value)
            if names is None:
                return {"state": "dynamic", "names": [], "line": getattr(node, "lineno", 1)}
            return {"state": "literal", "names": names, "line": getattr(node, "lineno", 1)}
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__":
            if node.value is None:
                return {"state": "dynamic", "names": [], "line": getattr(node, "lineno", 1)}
            names = literal_string_sequence(node.value)
            if names is None:
                return {"state": "dynamic", "names": [], "line": getattr(node, "lineno", 1)}
            return {"state": "literal", "names": names, "line": getattr(node, "lineno", 1)}
    return {"state": "missing", "names": [], "line": 1}


def imported_aliases(tree):
    aliases = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("algorithm_module_protocol"):
                    continue
                aliases.append({
                    "alias": alias.asname or alias.name.rsplit(".", 1)[-1],
                    "module": alias.name,
                    "from_module": "",
                    "name": "",
                    "level": 0,
                    "line": getattr(node, "lineno", 1),
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("algorithm_module_protocol"):
                continue
            for alias in node.names:
                if alias.name == "algorithm_module_protocol":
                    continue
                imported = "." * node.level + module
                if module:
                    imported = f"{imported}.{alias.name}"
                aliases.append({
                    "alias": alias.asname or alias.name,
                    "module": imported,
                    "from_module": module,
                    "name": alias.name,
                    "level": node.level,
                    "line": getattr(node, "lineno", 1),
                })
    return aliases


def top_level_aliases(tree):
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            aliases[node.target.id] = annotation_text(node.value)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            aliases[node.targets[0].id] = annotation_text(node.value)
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
                fields.append({
                    "name": ref_name(child.target),
                    "annotation": annotation_text(child.annotation),
                    "line": getattr(child, "lineno", getattr(node, "lineno", 1)),
                })
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(child.name)
        classes.append({
            "name": node.name,
            "line": getattr(node, "lineno", 1),
            "bases": base_facts(node),
            "fields": fields,
            "methods": methods,
        })
    return classes


def uses_parent_config_field(node):
    return any(
        isinstance(child, ast.Attribute)
        and isinstance(child.value, ast.Name)
        and child.value.id == "config"
        for child in ast.walk(node)
    )


def is_local_child_config(node, dependency_alias):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "InitializeConfig"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == dependency_alias
    )


class UsageVisitor(ast.NodeVisitor):
    def __init__(self, aliases):
        self.aliases = set(aliases)
        self.alias_attrs = {}
        self.calls = []
        self.references = []
        self.initialize_calls = []

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
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "initialize"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.aliases
        ):
            first_arg = node.args[0] if node.args else None
            self.initialize_calls.append({
                "alias": node.func.value.id,
                "line": getattr(node, "lineno", 1),
                "uses_parent_config": uses_parent_config_field(first_arg),
                "local_child_config": is_local_child_config(first_arg, node.func.value.id),
            })
        self.generic_visit(node)


def usage(tree, aliases):
    visitor = UsageVisitor(alias["alias"] for alias in aliases)
    visitor.visit(tree)
    return {
        "alias_attrs": {key: sorted(value) for key, value in sorted(visitor.alias_attrs.items())},
        "calls": visitor.calls,
        "references": visitor.references,
        "initialize_calls": visitor.initialize_calls,
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
        except SyntaxError as exc:
            errors.append({
                "path": relative_path(root, path),
                "line": exc.lineno or 1,
                "kind": "syntax_error",
                "detail": "parseable",
            })
            continue
        except Exception as exc:
            print(f"AST extractor failed for {path}: {exc}", file=sys.stderr)
            raise
        aliases = imported_aliases(tree)
        state = all_state(tree)
        modules.append({
            "path": relative_path(root, path),
            "module": module_name(root, path),
            "imports_amp": imports_algorithm_module_protocol(tree),
            "public_definitions": public_definitions(tree),
            "all_state": state["state"],
            "all_names": state["names"],
            "all_line": state["line"],
            "imports": aliases,
            "aliases": top_level_aliases(tree),
            "classes": class_defs(tree),
            "usage": usage(tree, aliases),
        })
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
enum AllState {
    Missing,
    Dynamic,
    Literal,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModuleAst {
    path: String,
    module: String,
    imports_amp: bool,
    public_definitions: BTreeMap<String, PublicDefinitionAst>,
    all_state: AllState,
    all_names: Vec<String>,
    all_line: usize,
    imports: BTreeMap<String, ImportAst>,
    aliases: BTreeMap<String, String>,
    classes: BTreeMap<String, ClassAst>,
    alias_attrs: BTreeMap<String, BTreeSet<String>>,
    calls: Vec<NamedLine>,
    references: Vec<NamedLine>,
    initialize_calls: Vec<InitializeCallAst>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PublicDefinitionAst {
    line: usize,
    kind: String,
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
struct InitializeCallAst {
    alias: String,
    line: usize,
    uses_parent_config: bool,
    local_child_config: bool,
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

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct ParseError {
    path: String,
    line: usize,
    kind: String,
    detail: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct DependencyReport {
    alias: String,
    module: String,
    contract_classes: Vec<String>,
    sources: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct ModuleReport {
    path: String,
    public_names: Vec<String>,
    all_names: Vec<String>,
    dependencies: Vec<DependencyReport>,
}

#[derive(Debug, PartialEq, Eq)]
struct Report {
    files: usize,
    algorithm_modules: Vec<String>,
    modules: Vec<ModuleReport>,
    findings: Vec<Finding>,
    parse_errors: Vec<ParseError>,
    format: OutputFormat,
}

#[derive(Debug, Serialize)]
struct JsonSummary {
    files: usize,
    algorithm_modules: usize,
    findings: usize,
    parse_errors: usize,
    status: &'static str,
}

#[derive(Debug, Serialize)]
struct JsonFinding<'a> {
    path: &'a str,
    line: usize,
    kind: &'a str,
    subject: &'a str,
    detail: &'a str,
}

#[derive(Debug, Serialize)]
struct JsonReport<'a> {
    summary: JsonSummary,
    algorithm_modules: &'a [String],
    modules: &'a [ModuleReport],
    parse_errors: &'a [ParseError],
    findings: Vec<JsonFinding<'a>>,
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
                    return Err(format!("unknown argument {value}"))
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
        .map(parse_parse_error)
        .collect::<Result<Vec<_>, _>>()?;
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
    let (findings, reports) = analyze_modules(&modules);
    Ok(Report {
        files: files.len(),
        algorithm_modules,
        modules: reports,
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
    if target.is_file() {
        if target.extension().and_then(|value| value.to_str()) == Some("py")
            && !excluded(root, target, excludes)
        {
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
    excludes.iter().any(|raw_pattern| {
        let pattern = raw_pattern.trim().trim_matches('/');
        if pattern.is_empty() {
            return false;
        }
        if pattern.chars().any(|character| "*?[]".contains(character)) {
            return fnmatchcase(&relative_text, pattern);
        }
        relative_text == pattern
            || relative_text.starts_with(&format!("{pattern}/"))
            || relative_text.split('/').any(|part| part == pattern)
    })
}

fn fnmatchcase(value: &str, pattern: &str) -> bool {
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
        } else if pattern[pattern_index] == '*' {
            matches(value, pattern, value_index, pattern_index + 1, cache)
                || (value_index < value.len()
                    && matches(value, pattern, value_index + 1, pattern_index, cache))
        } else if value_index == value.len() {
            false
        } else if pattern[pattern_index] == '?' {
            matches(value, pattern, value_index + 1, pattern_index + 1, cache)
        } else if pattern[pattern_index] == '[' {
            if let Some((next, matched)) =
                match_character_class(&value[value_index], pattern, pattern_index)
            {
                matched && matches(value, pattern, value_index + 1, next, cache)
            } else {
                value[value_index] == '['
                    && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
            }
        } else {
            value[value_index] == pattern[pattern_index]
                && matches(value, pattern, value_index + 1, pattern_index + 1, cache)
        };
        cache.insert((value_index, pattern_index), result);
        result
    }
    matches(&value, &pattern, 0, 0, &mut cache)
}

fn match_character_class(value: &char, pattern: &[char], start: usize) -> Option<(usize, bool)> {
    let mut index = start + 1;
    if index >= pattern.len() {
        return None;
    }
    let negated = matches!(pattern[index], '!' | '^');
    if negated {
        index += 1;
    }
    let mut matched = false;
    let mut has_member = false;
    while index < pattern.len() && pattern[index] != ']' {
        has_member = true;
        if index + 2 < pattern.len() && pattern[index + 1] == '-' && pattern[index + 2] != ']' {
            matched |= pattern[index] <= *value && *value <= pattern[index + 2];
            index += 3;
        } else {
            matched |= pattern[index] == *value;
            index += 1;
        }
    }
    if index >= pattern.len() || !has_member {
        return None;
    }
    Some((index + 1, if negated { !matched } else { matched }))
}

fn extract_ast_modules(root: &Path, files: &[PathBuf]) -> Result<Value, String> {
    let request = json!({"root": root, "files": files});
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

fn parse_parse_error(value: &Value) -> Result<ParseError, String> {
    Ok(ParseError {
        path: string_field(value, "path")?,
        line: usize_field(value, "line")?,
        kind: string_field(value, "kind")?,
        detail: string_field(value, "detail")?,
    })
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
    let public_definitions = value
        .get("public_definitions")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: public_definitions must be array"))?
        .iter()
        .map(parse_public_definition)
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .map(|item| (item.0, item.1))
        .collect::<BTreeMap<_, _>>();
    let all_state = match string_field(&value, "all_state")?.as_str() {
        "missing" => AllState::Missing,
        "dynamic" => AllState::Dynamic,
        "literal" => AllState::Literal,
        state => return Err(format!("{path}: invalid all_state {state}")),
    };
    let all_names = value
        .get("all_names")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: all_names must be array"))?
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect();
    let initialize_calls = value
        .get("usage")
        .and_then(|usage| usage.get("initialize_calls"))
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{path}: initialize_calls must be array"))?
        .iter()
        .map(parse_initialize_call)
        .collect::<Result<Vec<_>, _>>()?;
    Ok(ModuleAst {
        path,
        module: string_field(&value, "module")?,
        imports_amp: value
            .get("imports_amp")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        public_definitions,
        all_state,
        all_names,
        all_line: usize_field(&value, "all_line")?,
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
        initialize_calls,
    })
}

fn parse_public_definition(value: &Value) -> Result<(String, PublicDefinitionAst), String> {
    let name = string_field(value, "name")?;
    Ok((
        name,
        PublicDefinitionAst {
            line: usize_field(value, "line")?,
            kind: string_field(value, "kind")?,
        },
    ))
}

fn parse_initialize_call(value: &Value) -> Result<InitializeCallAst, String> {
    Ok(InitializeCallAst {
        alias: string_field(value, "alias")?,
        line: usize_field(value, "line")?,
        uses_parent_config: value
            .get("uses_parent_config")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        local_child_config: value
            .get("local_child_config")
            .and_then(Value::as_bool)
            .unwrap_or(false),
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

fn analyze_modules(modules: &[ModuleAst]) -> (Vec<Finding>, Vec<ModuleReport>) {
    let algorithm_module_names = modules
        .iter()
        .filter(|module| module_is_algorithm(module))
        .map(|module| module.module.clone())
        .collect::<BTreeSet<_>>();
    let mut findings = Vec::new();
    let mut reports = Vec::new();
    for module in modules {
        if !module.imports_amp || module_has_expected_public_name(module) {
            if module_is_algorithm(module) {
                findings.extend(analyze_algorithm_module_surface(module));
                let (nested_findings, dependencies) =
                    analyze_nested_contract(module, &algorithm_module_names);
                findings.extend(nested_findings);
                findings.extend(analyze_legacy_stopping_usage(module));
                reports.push(module_report(module, dependencies));
            }
        } else if !is_allowed_non_algorithm_import(&module.path) {
            findings.push(Finding::new(
                &module.path,
                1,
                "non_algorithm_protocol_import",
                "algorithm_module_protocol",
                "define-standard-public-surface-or-remove-import",
            ));
        }
    }
    findings.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then_with(|| left.line.cmp(&right.line))
            .then_with(|| left.kind.cmp(&right.kind))
            .then_with(|| left.subject.cmp(&right.subject))
            .then_with(|| left.detail.cmp(&right.detail))
    });
    findings.dedup_by(|right, left| {
        right.path == left.path
            && right.line == left.line
            && right.kind == left.kind
            && right.subject == left.subject
            && right.detail == left.detail
    });
    reports.sort_by(|left, right| left.path.cmp(&right.path));
    (findings, reports)
}

fn module_report(
    module: &ModuleAst,
    dependencies: BTreeMap<String, DependencyReport>,
) -> ModuleReport {
    ModuleReport {
        path: module.path.clone(),
        public_names: module.public_definitions.keys().cloned().collect(),
        all_names: module.all_names.clone(),
        dependencies: dependencies.into_values().collect(),
    }
}

fn module_has_expected_public_name(module: &ModuleAst) -> bool {
    module
        .public_definitions
        .keys()
        .any(|name| EXPECTED_PUBLIC_NAMES.contains(&name.as_str()))
}

fn is_allowed_non_algorithm_import(relative: &str) -> bool {
    NON_ALGORITHM_IMPORT_ALLOWLIST
        .iter()
        .any(|prefix| relative == *prefix || relative.starts_with(&format!("{prefix}/")))
}

fn module_is_algorithm(module: &ModuleAst) -> bool {
    module.imports_amp && module_has_expected_public_name(module)
}

fn analyze_algorithm_module_surface(module: &ModuleAst) -> Vec<Finding> {
    let mut findings = Vec::new();
    if !matches!(module.all_state, AllState::Literal) {
        let kind = if matches!(module.all_state, AllState::Dynamic) {
            "dynamic_all"
        } else {
            "missing_all"
        };
        findings.push(Finding::new(
            &module.path,
            module.all_line,
            kind,
            "__all__",
            "literal-standard-public-names-required",
        ));
    }
    let all_name_set = module.all_names.iter().cloned().collect::<BTreeSet<_>>();
    for name in all_name_set.difference(&expected_public_name_set()) {
        if !is_allowed_extra_public_name(name) {
            findings.push(Finding::new(
                &module.path,
                module.all_line,
                "extra_all",
                name,
                "remove-from-__all__",
            ));
        }
    }
    for name in expected_public_name_set().difference(&all_name_set) {
        findings.push(Finding::new(
            &module.path,
            module.all_line,
            "missing_all_name",
            name,
            "add-to-__all__",
        ));
    }
    for (name, definition) in &module.public_definitions {
        if !EXPECTED_PUBLIC_NAMES.contains(&name.as_str()) && !is_allowed_extra_public_name(name) {
            findings.push(Finding::new(
                &module.path,
                definition.line,
                "extra_public_definition",
                name,
                "make-private-or-remove",
            ));
        }
    }
    for name in
        expected_public_name_set().difference(&module.public_definitions.keys().cloned().collect())
    {
        findings.push(Finding::new(
            &module.path,
            module.all_line,
            "missing_public_definition",
            name,
            "define-standard-public-name",
        ));
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
            module
                .public_definitions
                .get("Algorithm")
                .map(|definition| definition.line)
                .unwrap_or(1),
            "missing_algorithm_function_object",
            "Algorithm",
            "define callable Algorithm",
        )),
    }
    if let Some(info) = module.public_definitions.get("Info") {
        if info.kind != "class" {
            findings.push(Finding::new(
                &module.path,
                info.line,
                "info_not_concrete",
                "Info",
                "define concrete class Info",
            ));
        }
    }
    findings
}

fn expected_public_name_set() -> BTreeSet<String> {
    EXPECTED_PUBLIC_NAMES
        .iter()
        .map(|name| (*name).to_string())
        .collect()
}

fn is_allowed_extra_public_name(name: &str) -> bool {
    ALLOWED_EXTRA_PUBLIC_PREFIXES
        .iter()
        .any(|prefix| name.starts_with(prefix))
}

fn analyze_nested_contract(
    module: &ModuleAst,
    algorithm_module_names: &BTreeSet<String>,
) -> (Vec<Finding>, BTreeMap<String, DependencyReport>) {
    let requirements = nested_requirements(module);
    let mut dependencies = BTreeMap::new();
    for ((alias, contract_class), sources) in &requirements {
        let dependency_module = dependency_module(module, alias, algorithm_module_names);
        let key = format!("{alias}\0{dependency_module}");
        let dependency = dependencies.entry(key).or_insert_with(|| DependencyReport {
            alias: alias.clone(),
            module: dependency_module,
            contract_classes: Vec::new(),
            sources: Vec::new(),
        });
        if !dependency.contract_classes.contains(contract_class) {
            dependency.contract_classes.push(contract_class.clone());
        }
        for source in sources {
            if !dependency.sources.contains(source) {
                dependency.sources.push(source.clone());
            }
        }
    }
    for dependency in dependencies.values_mut() {
        dependency.contract_classes.sort();
        dependency.sources.sort();
    }
    let mut findings = Vec::new();
    for ((alias, contract_class), _) in requirements {
        let Some(class_node) = module.classes.get(&contract_class) else {
            findings.push(Finding::new(
                &module.path,
                1,
                "missing_contract_class",
                &format!("{alias}.{contract_class}"),
                &format!("define {contract_class}"),
            ));
            continue;
        };
        if class_annotations_contain(module, class_node, &alias, &contract_class) {
            continue;
        }
        let detail = nested_field_detail(module, class_node, &alias, &contract_class);
        findings.push(Finding::new(
            &module.path,
            class_node.line,
            "missing_nested_field",
            &format!("{alias}.{contract_class}"),
            &detail,
        ));
    }
    (findings, dependencies)
}

fn nested_requirements(module: &ModuleAst) -> BTreeMap<(String, String), BTreeSet<String>> {
    let mut requirements = BTreeMap::new();
    for contract_class in CONTRACT_CLASSES {
        let Some(class_node) = module.classes.get(*contract_class) else {
            continue;
        };
        for field in &class_node.fields {
            for dependency_alias in module.imports.keys() {
                for dependency_class in CONTRACT_CLASSES {
                    if annotation_contains_dependency(
                        module,
                        &field.annotation,
                        dependency_alias,
                        dependency_class,
                    ) {
                        requirements
                            .entry((dependency_alias.clone(), (*dependency_class).to_string()))
                            .or_insert_with(BTreeSet::new)
                            .insert("annotation".to_string());
                    }
                }
            }
        }
    }
    for call in &module.initialize_calls {
        requirements
            .entry((call.alias.clone(), "Algorithm".to_string()))
            .or_insert_with(BTreeSet::new)
            .insert("initialize_call".to_string());
        if call.uses_parent_config && !call.local_child_config {
            requirements
                .entry((call.alias.clone(), "InitializeConfig".to_string()))
                .or_insert_with(BTreeSet::new)
                .insert("initialize_parent_config".to_string());
        }
    }
    requirements
}

fn dependency_module(
    module: &ModuleAst,
    alias: &str,
    algorithm_module_names: &BTreeSet<String>,
) -> String {
    let Some(import) = module.imports.get(alias) else {
        return alias.to_string();
    };
    let candidates = import_candidate_modules(&module.module, import);
    candidates
        .iter()
        .find(|candidate| algorithm_module_names.contains(*candidate))
        .cloned()
        .or_else(|| candidates.last().cloned())
        .unwrap_or_else(|| import.module.trim_start_matches('.').to_string())
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
    package.truncate(package.len() - drop_count);
    if !from_module.is_empty() {
        package.extend(from_module.split('.').map(str::to_string));
    }
    (!package.is_empty()).then(|| package.join("."))
}

fn annotation_contains_dependency(
    module: &ModuleAst,
    annotation: &str,
    dependency_alias: &str,
    dependency_class: &str,
) -> bool {
    let required = format!("{dependency_alias}.{dependency_class}");
    annotation.contains(&required)
        || expand_annotation(annotation, &module.aliases).contains(&required)
}

fn class_annotations_contain(
    module: &ModuleAst,
    class_node: &ClassAst,
    dependency_alias: &str,
    dependency_class: &str,
) -> bool {
    class_node.fields.iter().any(|field| {
        annotation_contains_dependency(
            module,
            &field.annotation,
            dependency_alias,
            dependency_class,
        )
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
    if let Some(field) = class_node.fields.iter().find(|field| {
        field.name.to_lowercase().contains(&field_hint)
            && (field.annotation == "Any"
                || field.annotation.contains(&generic)
                || expand_annotation(&field.annotation, &module.aliases).contains(&generic))
    }) {
        return format!(
            "field-{}-uses-{}; annotate as {}.{}",
            field.name, field.annotation, dependency_alias, dependency_class
        );
    }
    format!("add-field-annotated-{dependency_alias}.{dependency_class}")
}

fn analyze_legacy_stopping_usage(module: &ModuleAst) -> Vec<Finding> {
    let mut findings = Vec::new();
    if let Some(class_node) = module.classes.get("SolveConfig") {
        for field in &class_node.fields {
            if STOPPING_POLICY_TYPES.iter().any(|name| {
                annotation_mentions(module, &field.annotation, name)
                    && !module_defines_name(module, name)
            }) {
                findings.push(Finding::new(&module.path, field.line, "legacy_stopping_policy_field", &field.name, "use imported stopping.SolveConfig so the nested algorithm contract is inferred"));
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
            let payload = JsonReport {
                summary: JsonSummary {
                    files: report.files,
                    algorithm_modules: report.algorithm_modules.len(),
                    findings: report.findings.len(),
                    parse_errors: report.parse_errors.len(),
                    status: if report.findings.is_empty() && report.parse_errors.is_empty() {
                        "pass"
                    } else {
                        "fail"
                    },
                },
                algorithm_modules: &report.algorithm_modules,
                modules: &report.modules,
                parse_errors: &report.parse_errors,
                findings: report
                    .findings
                    .iter()
                    .map(|finding| JsonFinding {
                        path: &finding.path,
                        line: finding.line,
                        kind: &finding.kind,
                        subject: &finding.subject,
                        detail: &finding.detail,
                    })
                    .collect(),
            };
            println!(
                "{}",
                serde_json::to_string_pretty(&payload).expect("json payload serializes")
            );
        }
        OutputFormat::Text => {
            for error in &report.parse_errors {
                println!(
                    "PY_ALGORITHM_CONTRACT_PARSE_ERROR={}:{}:parseable",
                    error.path, error.line
                );
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
                "PY_ALGORITHM_CONTRACT_PARSE_ERRORS={}",
                report.parse_errors.len()
            );
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
        let public_definitions = EXPECTED_PUBLIC_NAMES
            .iter()
            .map(|name| {
                (
                    (*name).to_string(),
                    PublicDefinitionAst {
                        line: 1,
                        kind: if *name == "Info" || *name == "Algorithm" {
                            "class".to_string()
                        } else {
                            "function".to_string()
                        },
                    },
                )
            })
            .collect();
        ModuleAst {
            path: "python/pkg/parent.py".to_string(),
            module: "python.pkg.parent".to_string(),
            imports_amp: true,
            public_definitions,
            all_state: AllState::Literal,
            all_names: EXPECTED_PUBLIC_NAMES
                .iter()
                .map(|name| (*name).to_string())
                .collect(),
            all_line: 1,
            imports: BTreeMap::from([(
                "child".to_string(),
                ImportAst {
                    module: ".child".to_string(),
                    from_module: String::new(),
                    imported_name: "child".to_string(),
                    level: 1,
                    line: 1,
                },
            )]),
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
                    class(6, vec![field("child_solve", "child.SolveConfig")], &[]),
                ),
                ("Problem".to_string(), class(9, Vec::new(), &[])),
                ("State".to_string(), class(12, Vec::new(), &[])),
                ("Answer".to_string(), class(15, Vec::new(), &[])),
                ("Info".to_string(), class(18, Vec::new(), &[])),
                (
                    "Algorithm".to_string(),
                    class(
                        21,
                        vec![field("child_algorithm", "child.Algorithm")],
                        &["__call__"],
                    ),
                ),
            ]),
            alias_attrs: BTreeMap::new(),
            calls: Vec::new(),
            references: Vec::new(),
            initialize_calls: vec![InitializeCallAst {
                alias: "child".to_string(),
                line: 30,
                uses_parent_config: true,
                local_child_config: false,
            }],
        }
    }

    #[test]
    fn compliant_nested_contract_passes_and_records_sources() {
        let (findings, reports) = analyze_modules(&[algorithm_module()]);
        assert!(findings.is_empty());
        assert_eq!(
            reports[0].dependencies[0].contract_classes,
            vec!["Algorithm", "InitializeConfig", "SolveConfig"]
        );
        assert_eq!(
            reports[0].dependencies[0].sources,
            vec!["annotation", "initialize_call", "initialize_parent_config"]
        );
    }

    #[test]
    fn local_child_config_does_not_require_parent_initialize_config() {
        let mut module = algorithm_module();
        module
            .classes
            .get_mut("InitializeConfig")
            .unwrap()
            .fields
            .clear();
        module.initialize_calls[0].uses_parent_config = false;
        module.initialize_calls[0].local_child_config = true;
        let (findings, reports) = analyze_modules(&[module]);
        assert!(!findings
            .iter()
            .any(|finding| finding.subject == "child.InitializeConfig"));
        assert_eq!(
            reports[0].dependencies[0].contract_classes,
            vec!["Algorithm", "SolveConfig"]
        );
    }

    #[test]
    fn protocol_only_import_is_one_finding_and_not_a_module() {
        let module = ModuleAst {
            path: "helper.py".to_string(),
            module: "helper".to_string(),
            imports_amp: true,
            public_definitions: BTreeMap::new(),
            all_state: AllState::Missing,
            all_names: Vec::new(),
            all_line: 1,
            imports: BTreeMap::new(),
            aliases: BTreeMap::new(),
            classes: BTreeMap::new(),
            alias_attrs: BTreeMap::new(),
            calls: Vec::new(),
            references: Vec::new(),
            initialize_calls: Vec::new(),
        };
        let (findings, reports) = analyze_modules(&[module]);
        assert_eq!(reports.len(), 0);
        assert_eq!(findings[0].kind, "non_algorithm_protocol_import");
    }

    #[test]
    fn glob_matching_matches_fnmatchcase_shapes() {
        assert!(fnmatchcase("pkg/generated/a.py", "pkg/generated/*.py"));
        assert!(fnmatchcase("pkg/a_generated.py", "*_generated.py"));
        assert!(!fnmatchcase("pkg/keep.py", "*_generated.py"));
    }
}
