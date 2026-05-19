// @dependency-start
// responsibility Finds duplicate Python function and class structures by normalized AST hash.
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// @dependency-end

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
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
    "python/jax_util.egg-info",
];
const DEFAULT_MIN_TOKENS: usize = 8;
const DEFAULT_MAX_FINDINGS: usize = usize::MAX;

const AST_EXTRACTOR: &str = r##"
import ast
import json
import pathlib
import sys


def module_name(root, path):
    relative = pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve())
    without_suffix = relative.with_suffix("")
    return ".".join(without_suffix.parts)


def import_facts(tree):
    facts = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts.append(("import", alias.name))
        elif isinstance(node, ast.ImportFrom):
            level = "." * node.level
            module = level + (node.module or "")
            for alias in node.names:
                facts.append(("from", module, alias.name))
    return sorted(facts)


def ref_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = ref_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return ref_name(node.value)
    if isinstance(node, ast.Call):
        return ref_name(node.func)
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def decorator_facts(node):
    return sorted(ref_name(decorator) for decorator in getattr(node, "decorator_list", []))


def base_facts(node):
    return sorted(ref_name(base) for base in getattr(node, "bases", []))


def is_direct_protocol_base(base):
    return base == "Protocol" or base.endswith(".Protocol")


def class_identities(module, qualname):
    simple = qualname.rsplit(".", 1)[-1]
    return {simple, qualname, f"{module}.{qualname}"}


def base_matches_known_protocol(base, protocol_names):
    if is_direct_protocol_base(base):
        return True
    base_tail = base.rsplit(".", 1)[-1]
    return base in protocol_names or base_tail in protocol_names


class ClassIndexVisitor(ast.NodeVisitor):
    def __init__(self, module):
        self.module = module
        self.stack = []
        self.classes = []

    def visit_ClassDef(self, node):
        qualname = ".".join(self.stack + [node.name])
        self.classes.append(
            {
                "module": self.module,
                "qualname": qualname,
                "name": node.name,
                "bases": base_facts(node),
            }
        )
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def build_protocol_names(parsed_modules):
    classes = []
    for parsed in parsed_modules:
        visitor = ClassIndexVisitor(parsed["module"])
        visitor.visit(parsed["tree"])
        classes.extend(visitor.classes)

    protocol_names = set()
    changed = True
    while changed:
        changed = False
        for item in classes:
            if any(base_matches_known_protocol(base, protocol_names) for base in item["bases"]):
                identities = class_identities(item["module"], item["qualname"])
                before = len(protocol_names)
                protocol_names.update(identities)
                changed = changed or len(protocol_names) != before
    return protocol_names


def type_alias_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotation = ref_name(node.annotation)
            if annotation == "TypeAlias" or annotation.endswith(".TypeAlias"):
                names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Subscript):
                    value_name = ref_name(node.value.value)
                    if value_name in {"TypeAlias", "typing.TypeAlias"}:
                        names.add(target.id)
    return names


def parameter_count(node):
    args = node.args
    names = []
    for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
        names.append(arg.arg)
    if args.vararg is not None:
        names.append("*" + args.vararg.arg)
    if args.kwarg is not None:
        names.append("**" + args.kwarg.arg)
    return sum(1 for name in names if name not in {"self", "cls"})


def body_without_docstring(body):
    if not body:
        return body
    first = body[0]
    if isinstance(first, ast.Expr):
        value = first.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return body[1:]
        if isinstance(value, ast.Str):
            return body[1:]
    return body


def canonical(value):
    if isinstance(value, ast.AST):
        fields = []
        for field, child in ast.iter_fields(value):
            if field in {
                "name",
                "id",
                "arg",
                "attr",
                "asname",
                "lineno",
                "col_offset",
                "end_lineno",
                "end_col_offset",
                "ctx",
                "type_comment",
            }:
                continue
            if field == "returns" or field == "annotation":
                fields.append((field, "TYPE"))
                continue
            fields.append((field, canonical(child)))
        return [value.__class__.__name__, fields]
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, tuple):
        return [canonical(item) for item in value]
    if isinstance(value, str):
        return "STR"
    if isinstance(value, (int, float, complex)):
        return "NUM"
    if isinstance(value, bytes):
        return "BYTES"
    if value is None or isinstance(value, bool):
        return value
    return value.__class__.__name__


class Collector(ast.NodeVisitor):
    def __init__(self, root, path, tree, protocol_names):
        self.root = root
        self.path = path
        self.module = module_name(root, path)
        self.imports = import_facts(tree)
        self.protocol_names = protocol_names
        self.type_aliases = type_alias_names(tree)
        self.stack = []
        self.blocks = []

    def visit_FunctionDef(self, node):
        self._visit_block("Function", node)

    def visit_AsyncFunctionDef(self, node):
        self._visit_block("Function", node)

    def visit_ClassDef(self, node):
        self._visit_block("Class", node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            annotation = ref_name(node.annotation)
            if annotation == "TypeAlias" or annotation.endswith(".TypeAlias"):
                self._record_alias(node.target.id, node, node.value or node.annotation)
                return
        self.generic_visit(node)

    def visit_Assign(self, node):
        value_name = ref_name(node.value.value) if isinstance(node.value, ast.Subscript) else ""
        if value_name in {"TypeAlias", "typing.TypeAlias"}:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._record_alias(target.id, node, node.value)
            return
        self.generic_visit(node)

    def _visit_block(self, kind, node):
        parent = self.stack[-1] if self.stack else None
        qualname = ".".join([entry["name"] for entry in self.stack] + [node.name])
        class_is_protocol = kind == "Class" and any(
            identity in self.protocol_names
            for identity in class_identities(self.module, qualname)
        )
        inside_protocol = parent["inside_protocol"] if parent else False
        role = "protocol" if class_is_protocol or inside_protocol else "implementation"
        payload = {
            "path": str(pathlib.Path(self.path).resolve().relative_to(pathlib.Path(self.root).resolve())).replace("\\", "/"),
            "module": self.module,
            "line": getattr(node, "lineno", 0),
            "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
            "kind": kind,
            "name": node.name,
            "qualname": qualname,
            "parent_kind": parent["kind"] if parent else None,
            "parent_name": parent["name"] if parent else None,
            "role": role,
            "parameter_count": parameter_count(node) if kind == "Function" else len(node.bases),
            "decorators": decorator_facts(node),
            "bases": base_facts(node),
            "imports": self.imports,
            "canonical": canonical(body_without_docstring(node.body)),
        }
        self.blocks.append(payload)
        self.stack.append(
            {
                "kind": kind,
                "name": node.name,
                "inside_protocol": class_is_protocol or inside_protocol,
            }
        )
        self.generic_visit(node)
        self.stack.pop()

    def _record_alias(self, name, node, canonical_node):
        parent = self.stack[-1] if self.stack else None
        qualname = ".".join([entry["name"] for entry in self.stack] + [name])
        self.blocks.append(
            {
                "path": str(pathlib.Path(self.path).resolve().relative_to(pathlib.Path(self.root).resolve())).replace("\\", "/"),
                "module": self.module,
                "line": getattr(node, "lineno", 0),
                "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
                "kind": "Alias",
                "name": name,
                "qualname": qualname,
                "parent_kind": parent["kind"] if parent else None,
                "parent_name": parent["name"] if parent else None,
                "role": "alias",
                "parameter_count": 0,
                "decorators": [],
                "bases": [],
                "imports": self.imports,
                "canonical": canonical(canonical_node),
            }
        )


def main():
    request = json.load(sys.stdin)
    root = request["root"]
    blocks = []
    errors = []
    parsed_modules = []
    for path in request["files"]:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8")
            tree = ast.parse(text, filename=path)
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        parsed_modules.append(
            {
                "path": path,
                "tree": tree,
                "module": module_name(root, path),
            }
        )
    protocol_names = build_protocol_names(parsed_modules)
    for parsed in parsed_modules:
        path = parsed["path"]
        tree = parsed["tree"]
        collector = Collector(root, path, tree, protocol_names)
        collector.visit(tree)
        blocks.extend(collector.blocks)
    print(
        json.dumps(
            {
                "blocks": blocks,
                "errors": errors,
                "summary": {
                    "protocol_symbols": len(protocol_names),
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
"##;

#[derive(Debug, PartialEq, Eq)]
struct Args {
    root: PathBuf,
    paths: Vec<String>,
    excludes: Vec<String>,
    min_tokens: usize,
    max_findings: usize,
    format: OutputFormat,
}

#[derive(Debug, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Block {
    path: String,
    module: String,
    line: usize,
    end_line: usize,
    kind: String,
    role: String,
    name: String,
    qualname: String,
    parent_kind: Option<String>,
    parent_name: Option<String>,
    parameter_count: usize,
    decorators_hash: String,
    bases_hash: String,
    import_hash: String,
    structure_hash: String,
    context_hash: String,
    token_count: usize,
}

#[derive(Debug, PartialEq, Eq)]
struct DuplicateGroup {
    structure_hash: String,
    role: String,
    kind: String,
    parameter_count: usize,
    token_count: usize,
    module_scope: ModuleScope,
    import_scope: ImportScope,
    decorator_scope: DecoratorScope,
    base_scope: BaseScope,
    blocks: Vec<Block>,
}

#[derive(Debug, PartialEq, Eq)]
struct Analysis {
    groups: Vec<DuplicateGroup>,
    analyzed_files: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
enum ModuleScope {
    SameModule,
    CrossModule,
}

#[derive(Debug, PartialEq, Eq)]
enum ImportScope {
    SameImports,
    MixedImports,
}

#[derive(Debug, PartialEq, Eq)]
enum DecoratorScope {
    SameDecorators,
    MixedDecorators,
}

#[derive(Debug, PartialEq, Eq)]
enum BaseScope {
    SameBases,
    MixedBases,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => match analyze(&parsed) {
            Ok(analysis) => render(analysis, &parsed),
            Err(message) => {
                eprintln!("PY_STRUCTURE_HASH=fail");
                eprintln!("PY_STRUCTURE_HASH_FINDING=analysis-error:{message}");
                2
            }
        },
        Err(message) => {
            eprintln!("PY_STRUCTURE_HASH=fail");
            eprintln!("PY_STRUCTURE_HASH_FINDING=invalid-arguments:{message}");
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
        let mut min_tokens = DEFAULT_MIN_TOKENS;
        let mut max_findings = DEFAULT_MAX_FINDINGS;
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
                "--min-tokens" => {
                    min_tokens = positive_usize(&value_after(args, index, "--min-tokens")?)?;
                    index += 2;
                }
                "--max-findings" => {
                    max_findings = positive_usize(&value_after(args, index, "--max-findings")?)?;
                    index += 2;
                }
                "--format" => {
                    let value = value_after(args, index, "--format")?;
                    format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => return Err(format!("--format must be text or json, got {value}")),
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
            min_tokens,
            max_findings,
            format,
        })
    }
}

fn value_after(args: &[String], index: usize, flag: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{flag} requires a value"))
}

fn positive_usize(value: &str) -> Result<usize, String> {
    let parsed = value
        .parse::<usize>()
        .map_err(|_| format!("expected positive integer, got {value}"))?;
    if parsed == 0 {
        return Err("expected positive integer greater than zero".to_string());
    }
    Ok(parsed)
}

fn analyze(args: &Args) -> Result<Analysis, String> {
    let root = resolve_like_cwd(&args.root);
    let files = source_files(&root, &args.paths, &args.excludes);
    let files = expand_with_repo_import_dependencies(&root, files, &args.excludes);
    let analyzed_files = files
        .iter()
        .map(|path| relative_path(&root, path))
        .collect::<Vec<_>>();
    let ast_blocks = extract_ast_blocks(&root, &files)?;
    let mut buckets: BTreeMap<String, Vec<Block>> = BTreeMap::new();
    for value in ast_blocks {
        let block = block_from_ast_value(value)?;
        if block.token_count < args.min_tokens {
            continue;
        }
        buckets
            .entry(block.structure_hash.clone())
            .or_default()
            .push(block);
    }

    let mut groups = buckets
        .into_iter()
        .filter_map(|(structure_hash, blocks)| {
            if blocks.len() < 2 {
                return None;
            }
            let first = blocks.first()?;
            Some(DuplicateGroup {
                structure_hash,
                role: first.role.clone(),
                kind: first.kind.clone(),
                parameter_count: first.parameter_count,
                token_count: first.token_count,
                module_scope: module_scope(&blocks),
                import_scope: import_scope(&blocks),
                decorator_scope: decorator_scope(&blocks),
                base_scope: base_scope(&blocks),
                blocks,
            })
        })
        .collect::<Vec<_>>();
    groups.sort_by(|left, right| {
        right
            .blocks
            .len()
            .cmp(&left.blocks.len())
            .then_with(|| right.token_count.cmp(&left.token_count))
            .then_with(|| left.structure_hash.cmp(&right.structure_hash))
    });
    groups.truncate(args.max_findings);
    Ok(Analysis {
        groups,
        analyzed_files,
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

fn expand_with_repo_import_dependencies(
    root: &Path,
    initial_files: Vec<PathBuf>,
    excludes: &[String],
) -> Vec<PathBuf> {
    let mut files = initial_files
        .into_iter()
        .map(|path| fs::canonicalize(&path).unwrap_or(path))
        .collect::<BTreeSet<_>>();
    let mut scanned = BTreeSet::new();
    loop {
        let pending = files
            .iter()
            .filter(|path| !scanned.contains(*path))
            .cloned()
            .collect::<Vec<_>>();
        if pending.is_empty() {
            break;
        }
        for path in pending {
            scanned.insert(path.clone());
            for target in repo_import_targets(root, &path, excludes) {
                files.insert(target);
            }
        }
    }
    files.into_iter().collect()
}

fn repo_import_targets(root: &Path, path: &Path, excludes: &[String]) -> Vec<PathBuf> {
    let Ok(text) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let Some(current_module) = module_name_from_path(root, path) else {
        return Vec::new();
    };
    let mut targets = BTreeSet::new();
    for fact in collect_import_facts(&text) {
        for module in imported_modules(&current_module, &fact) {
            for candidate in module_file_candidates(root, &module) {
                if !excluded(root, &candidate, excludes) {
                    targets.insert(fs::canonicalize(&candidate).unwrap_or(candidate));
                }
            }
        }
    }
    targets.into_iter().collect()
}

fn collect_import_facts(text: &str) -> Vec<String> {
    let mut facts = Vec::new();
    let mut pending_from_module: Option<String> = None;
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(module) = pending_from_module.clone() {
            add_from_import_names(&mut facts, &module, trimmed);
            if trimmed.contains(')') {
                pending_from_module = None;
            }
            continue;
        }
        if trimmed.starts_with("import ") {
            let rest = trimmed
                .trim_start_matches("import ")
                .split('#')
                .next()
                .unwrap_or("");
            for item in rest.split(',') {
                let name = item.trim().split_whitespace().next().unwrap_or("");
                if !name.is_empty() {
                    facts.push(format!("import:{name}"));
                }
            }
        } else if trimmed.starts_with("from ") {
            let rest = trimmed.trim_start_matches("from ");
            if let Some((module, names)) = rest.split_once(" import ") {
                let module = module.trim();
                if names.trim().starts_with('(') && !names.contains(')') {
                    pending_from_module = Some(module.to_string());
                } else {
                    add_from_import_names(&mut facts, module, names);
                }
            }
        }
    }
    facts.sort();
    facts.dedup();
    facts
}

fn add_from_import_names(facts: &mut Vec<String>, module: &str, names: &str) {
    let cleaned = names
        .split('#')
        .next()
        .unwrap_or("")
        .trim()
        .trim_start_matches('(')
        .trim_end_matches(')')
        .trim();
    for item in cleaned.split(',') {
        let name = item.trim().split_whitespace().next().unwrap_or("");
        if !module.is_empty() && !name.is_empty() && name != "(" && name != ")" {
            facts.push(format!("from:{module}:{name}"));
        }
    }
}

fn imported_modules(current_module: &str, fact: &str) -> Vec<String> {
    if let Some(module) = fact.strip_prefix("import:") {
        return vec![module.to_string()];
    }
    let Some(rest) = fact.strip_prefix("from:") else {
        return Vec::new();
    };
    let Some((module, name)) = rest.split_once(':') else {
        return Vec::new();
    };
    let Some(resolved) = resolve_import_module(current_module, module) else {
        return Vec::new();
    };
    let mut modules = vec![resolved.clone()];
    if !name.is_empty() && name != "*" {
        modules.push(format!("{resolved}.{name}"));
    }
    modules
}

fn resolve_import_module(current_module: &str, module: &str) -> Option<String> {
    if !module.starts_with('.') {
        return Some(module.to_string());
    }
    let dots = module.chars().take_while(|value| *value == '.').count();
    let suffix = module.trim_start_matches('.');
    let mut package = current_module
        .split('.')
        .map(str::to_string)
        .collect::<Vec<_>>();
    package.pop();
    let drop_count = dots.saturating_sub(1);
    if drop_count > package.len() {
        return None;
    }
    let keep = package.len() - drop_count;
    package.truncate(keep);
    if !suffix.is_empty() {
        package.extend(suffix.split('.').map(str::to_string));
    }
    if package.is_empty() {
        None
    } else {
        Some(package.join("."))
    }
}

fn module_name_from_path(root: &Path, path: &Path) -> Option<String> {
    let relative = path.strip_prefix(root).ok()?.with_extension("");
    Some(
        relative
            .components()
            .map(|component| component.as_os_str().to_string_lossy())
            .collect::<Vec<_>>()
            .join("."),
    )
}

fn module_file_candidates(root: &Path, module: &str) -> Vec<PathBuf> {
    let relative = module.replace('.', "/");
    let mut candidates = Vec::new();
    for source_root in ["", "python", "src"] {
        let base = if source_root.is_empty() {
            root.to_path_buf()
        } else {
            root.join(source_root)
        };
        candidates.push(base.join(format!("{relative}.py")));
        candidates.push(base.join(&relative).join("__init__.py"));
    }
    candidates
        .into_iter()
        .filter(|path| exact_file_exists(path))
        .collect()
}

fn exact_file_exists(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(parent) = path.parent() else {
        return false;
    };
    let Some(file_name) = path.file_name() else {
        return false;
    };
    let Ok(entries) = fs::read_dir(parent) else {
        return false;
    };
    entries
        .flatten()
        .any(|entry| entry.file_name() == file_name)
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
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

fn extract_ast_blocks(root: &Path, files: &[PathBuf]) -> Result<Vec<Value>, String> {
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
    let payload: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("failed to parse AST extractor JSON: {error}"))?;
    let errors = payload
        .get("errors")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if !errors.is_empty() {
        eprintln!("PY_STRUCTURE_HASH_PARSE_ERRORS={}", errors.len());
    }
    Ok(payload
        .get("blocks")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default())
}

fn block_from_ast_value(value: Value) -> Result<Block, String> {
    let canonical = value
        .get("canonical")
        .ok_or_else(|| "AST block missing canonical payload".to_string())?;
    let imports = value
        .get("imports")
        .ok_or_else(|| "AST block missing imports payload".to_string())?;
    let decorators = value
        .get("decorators")
        .ok_or_else(|| "AST block missing decorators payload".to_string())?;
    let bases = value
        .get("bases")
        .ok_or_else(|| "AST block missing bases payload".to_string())?;
    let kind = string_field(&value, "kind")?;
    let role = string_field(&value, "role")?;
    let parameter_count = usize_field(&value, "parameter_count")?;
    let canonical_text = serde_json::to_string(canonical)
        .map_err(|error| format!("failed to serialize canonical AST: {error}"))?;
    let imports_text = serde_json::to_string(imports)
        .map_err(|error| format!("failed to serialize import facts: {error}"))?;
    let decorators_text = serde_json::to_string(decorators)
        .map_err(|error| format!("failed to serialize decorator facts: {error}"))?;
    let bases_text = serde_json::to_string(bases)
        .map_err(|error| format!("failed to serialize base facts: {error}"))?;
    let module = string_field(&value, "module")?;
    let owner_text = format!(
        "{}:{}",
        optional_string_field(&value, "parent_kind").unwrap_or_else(|| "<module>".to_string()),
        optional_string_field(&value, "parent_name").unwrap_or_else(|| "<module>".to_string())
    );
    let context_text =
        format!("{module}:{imports_text}:{decorators_text}:{bases_text}:{owner_text}");
    Ok(Block {
        path: string_field(&value, "path")?,
        module,
        line: usize_field(&value, "line")?,
        end_line: usize_field(&value, "end_line")?,
        kind: kind.clone(),
        role: role.clone(),
        name: string_field(&value, "name")?,
        qualname: string_field(&value, "qualname")?,
        parent_kind: optional_string_field(&value, "parent_kind"),
        parent_name: optional_string_field(&value, "parent_name"),
        parameter_count,
        decorators_hash: stable_hash(&decorators_text),
        bases_hash: stable_hash(&bases_text),
        import_hash: stable_hash(&imports_text),
        structure_hash: stable_hash(&format!("{role}:{kind}:{parameter_count}:{canonical_text}")),
        context_hash: stable_hash(&context_text),
        token_count: ast_token_count(canonical),
    })
}

fn string_field(value: &Value, field: &str) -> Result<String, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| format!("AST block field {field} must be a string"))
}

fn optional_string_field(value: &Value, field: &str) -> Option<String> {
    value.get(field).and_then(Value::as_str).map(str::to_string)
}

fn usize_field(value: &Value, field: &str) -> Result<usize, String> {
    value
        .get(field)
        .and_then(Value::as_u64)
        .and_then(|number| usize::try_from(number).ok())
        .ok_or_else(|| format!("AST block field {field} must be a positive integer"))
}

fn ast_token_count(value: &Value) -> usize {
    match value {
        Value::Array(items) => 1 + items.iter().map(ast_token_count).sum::<usize>(),
        Value::Object(entries) => 1 + entries.values().map(ast_token_count).sum::<usize>(),
        Value::String(_) | Value::Number(_) | Value::Bool(_) | Value::Null => 1,
    }
}

fn stable_hash(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    format!("{:x}", hasher.finalize())[..16].to_string()
}

fn module_scope(blocks: &[Block]) -> ModuleScope {
    let modules = blocks
        .iter()
        .map(|block| block.module.as_str())
        .collect::<BTreeSet<_>>();
    if modules.len() == 1 {
        ModuleScope::SameModule
    } else {
        ModuleScope::CrossModule
    }
}

fn import_scope(blocks: &[Block]) -> ImportScope {
    let imports = blocks
        .iter()
        .map(|block| block.import_hash.as_str())
        .collect::<BTreeSet<_>>();
    if imports.len() == 1 {
        ImportScope::SameImports
    } else {
        ImportScope::MixedImports
    }
}

fn decorator_scope(blocks: &[Block]) -> DecoratorScope {
    let decorators = blocks
        .iter()
        .map(|block| block.decorators_hash.as_str())
        .collect::<BTreeSet<_>>();
    if decorators.len() == 1 {
        DecoratorScope::SameDecorators
    } else {
        DecoratorScope::MixedDecorators
    }
}

fn base_scope(blocks: &[Block]) -> BaseScope {
    let bases = blocks
        .iter()
        .map(|block| block.bases_hash.as_str())
        .collect::<BTreeSet<_>>();
    if bases.len() == 1 {
        BaseScope::SameBases
    } else {
        BaseScope::MixedBases
    }
}

fn render(analysis: Analysis, args: &Args) -> i32 {
    match args.format {
        OutputFormat::Json => render_json(&analysis),
        OutputFormat::Text => render_text(&analysis),
    }
    if analysis.groups.is_empty() {
        0
    } else {
        1
    }
}

fn render_text(analysis: &Analysis) {
    for group in &analysis.groups {
        let symbols = group
            .blocks
            .iter()
            .map(|block| {
                format!(
                    "{}:{}-{}:{}:{}:{}:context={}",
                    block.path,
                    block.line,
                    block.end_line,
                    block.module,
                    block.qualname,
                    compatibility_label(block),
                    block.context_hash
                )
            })
            .collect::<Vec<_>>()
            .join(",");
        println!(
            "PY_STRUCTURE_HASH_FINDING=duplicate_structural_hash:role={}:{}:params={}:tokens={}:hash={}:count={}:module_scope={:?}:import_scope={:?}:decorator_scope={:?}:base_scope={:?}:{}",
            group.role,
            group.kind,
            group.parameter_count,
            group.token_count,
            group.structure_hash,
            group.blocks.len(),
            group.module_scope,
            group.import_scope,
            group.decorator_scope,
            group.base_scope,
            symbols
        );
    }
    println!(
        "PY_STRUCTURE_HASH_ANALYZED_FILES={}",
        analysis.analyzed_files.len()
    );
    for path in &analysis.analyzed_files {
        println!("PY_STRUCTURE_HASH_ANALYZED_FILE={path}");
    }
    println!("PY_STRUCTURE_HASH_GROUPS={}", analysis.groups.len());
    println!(
        "PY_STRUCTURE_HASH={}",
        if analysis.groups.is_empty() {
            "pass"
        } else {
            "fail"
        }
    );
}

fn parent_label(block: &Block) -> String {
    match (&block.parent_kind, &block.parent_name) {
        (Some(kind), Some(name)) => format!("parent={kind}:{name}"),
        _ => "parent=<module>".to_string(),
    }
}

fn compatibility_label(block: &Block) -> String {
    format!(
        "{}:imports={}:decorators={}:bases={}",
        parent_label(block),
        block.import_hash,
        block.decorators_hash,
        block.bases_hash
    )
}

fn render_json(analysis: &Analysis) {
    let payload = json!({
        "summary": {
            "groups": analysis.groups.len(),
            "status": if analysis.groups.is_empty() { "pass" } else { "fail" },
            "analyzed_file_count": analysis.analyzed_files.len(),
            "analyzed_files": analysis.analyzed_files,
        },
        "findings": analysis.groups.iter().map(|group| {
            json!({
                "kind": "duplicate_structural_hash",
                "hash": group.structure_hash,
                "block_kind": group.kind,
                "role": group.role,
                "parameter_count": group.parameter_count,
                "token_count": group.token_count,
                "module_scope": format!("{:?}", group.module_scope),
                "import_scope": format!("{:?}", group.import_scope),
                "decorator_scope": format!("{:?}", group.decorator_scope),
                "base_scope": format!("{:?}", group.base_scope),
                "instances": group.blocks.iter().map(|block| {
                    json!({
                        "path": block.path,
                        "line": block.line,
                        "end_line": block.end_line,
                        "module": block.module,
                        "name": block.name,
                        "qualname": block.qualname,
                        "parent_kind": block.parent_kind,
                        "parent_name": block.parent_name,
                        "import_hash": block.import_hash,
                        "decorators_hash": block.decorators_hash,
                        "bases_hash": block.bases_hash,
                        "context_hash": block.context_hash,
                    })
                }).collect::<Vec<_>>(),
            })
        }).collect::<Vec<_>>(),
    });
    println!(
        "{}",
        serde_json::to_string_pretty(&payload).expect("json payload serializes")
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stable_hash_ignores_names_when_canonical_payload_is_equal() {
        let canonical = json!(["Return", [["value", ["Name", []]]]]);
        let left = stable_hash(&format!("Function:2:{canonical}"));
        let right = stable_hash(&format!("Function:2:{canonical}"));
        assert_eq!(left, right);
    }

    #[test]
    fn import_hash_tracks_import_surface_separately() {
        let left = stable_hash(r#"[["import","jax.numpy"]]"#);
        let right = stable_hash(r#"[["import","numpy"]]"#);
        assert_ne!(left, right);
    }

    #[test]
    fn module_scope_detects_cross_module_groups() {
        let blocks = vec![block_for_test("a.b"), block_for_test("a.c")];
        assert_eq!(module_scope(&blocks), ModuleScope::CrossModule);
    }

    #[test]
    fn source_files_expand_repo_import_dependencies() {
        let root = std::env::temp_dir().join(format!(
            "agent-canon-python-structure-hash-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        let pkg = root.join("pkg");
        let python_pkg = root.join("python").join("pkg");
        fs::create_dir_all(&pkg).expect("pkg dir");
        fs::create_dir_all(&python_pkg).expect("python pkg dir");
        fs::write(pkg.join("a.py"), "from .b import B\n").expect("a.py");
        fs::write(
            pkg.join("b.py"),
            "from .c import C\nimport pkg.d\nclass B: pass\n",
        )
        .expect("b.py");
        fs::write(pkg.join("c.py"), "class C: pass\n").expect("c.py");
        fs::write(python_pkg.join("d.py"), "class D: pass\n").expect("d.py");

        let initial = source_files(&root, &["pkg/a.py".to_string()], &[]);
        let expanded = expand_with_repo_import_dependencies(&root, initial, &[]);
        let relative = expanded
            .iter()
            .map(|path| {
                path.strip_prefix(&root)
                    .unwrap_or(path)
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .collect::<BTreeSet<_>>();

        assert_eq!(
            relative,
            BTreeSet::from([
                "pkg/a.py".to_string(),
                "pkg/b.py".to_string(),
                "pkg/c.py".to_string(),
                "python/pkg/d.py".to_string()
            ])
        );
        fs::remove_dir_all(root).expect("cleanup temp tree");
    }

    fn block_for_test(module: &str) -> Block {
        Block {
            path: format!("{}.py", module.replace('.', "/")),
            module: module.to_string(),
            line: 1,
            end_line: 2,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "f".to_string(),
            qualname: "f".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 0,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("Function:0:[]"),
            context_hash: stable_hash(module),
            token_count: 8,
        }
    }
}
