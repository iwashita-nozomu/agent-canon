// @dependency-start
// contract implementation
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
    if without_suffix.name == "__init__":
        without_suffix = without_suffix.parent
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


def module_all_names(tree):
    names = set()
    found = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [target for target in node.targets if isinstance(target, ast.Name)]
            if not any(target.id == "__all__" for target in targets):
                continue
            found = True
            values = []
            if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                values = node.value.elts
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    names.add(value.value)
    return names if found else None


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


class BlockCallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.calls = []

    def visit_FunctionDef(self, node):
        return

    def visit_AsyncFunctionDef(self, node):
        return

    def visit_ClassDef(self, node):
        return

    def visit_Call(self, node):
        self.calls.append(
            {
                "name": ref_name(node.func),
                "line": getattr(node, "lineno", 0),
            }
        )
        self.generic_visit(node)


def block_calls(node):
    visitor = BlockCallVisitor()
    for child in body_without_docstring(node.body):
        visitor.visit(child)
    return sorted(visitor.calls, key=lambda item: (item["line"], item["name"]))


class BlockReferenceVisitor(ast.NodeVisitor):
    def __init__(self):
        self.references = []

    def visit_FunctionDef(self, node):
        return

    def visit_AsyncFunctionDef(self, node):
        return

    def visit_ClassDef(self, node):
        return

    def visit_AnnAssign(self, node):
        self._add_annotation_refs(node.annotation)
        self.visit(node.value) if node.value is not None else None

    def _add_annotation_refs(self, node):
        if node is None:
            return
        line = getattr(node, "lineno", 0)
        for child in ast.walk(node):
            if isinstance(child, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
                name = ref_name(child)
                if name:
                    self.references.append({"name": name, "line": line})


def block_references(node):
    visitor = BlockReferenceVisitor()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs):
            visitor._add_annotation_refs(arg.annotation)
        if node.args.vararg is not None:
            visitor._add_annotation_refs(node.args.vararg.annotation)
        if node.args.kwarg is not None:
            visitor._add_annotation_refs(node.args.kwarg.annotation)
        visitor._add_annotation_refs(node.returns)
    elif isinstance(node, ast.ClassDef):
        for base in node.bases:
            visitor._add_annotation_refs(base)
    for child in body_without_docstring(node.body):
        visitor.visit(child)
    unique = {
        (item["line"], item["name"]): item
        for item in visitor.references
        if item["name"]
    }
    return [unique[key] for key in sorted(unique)]


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
        self.module_all = module_all_names(tree)
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
        if parent is None:
            public_api = (
                node.name in self.module_all
                if self.module_all is not None
                else not node.name.startswith("_")
            )
        elif parent["kind"] == "Class" and parent["public_api"]:
            public_api = not node.name.startswith("_")
        else:
            public_api = False
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
            "public_api": public_api,
            "parameter_count": parameter_count(node) if kind == "Function" else len(node.bases),
            "decorators": decorator_facts(node),
            "bases": base_facts(node),
            "imports": self.imports,
            "calls": block_calls(node),
            "references": block_references(node),
            "canonical": canonical(body_without_docstring(node.body)),
        }
        self.blocks.append(payload)
        self.stack.append(
            {
                "kind": kind,
                "name": node.name,
                "inside_protocol": class_is_protocol or inside_protocol,
                "public_api": public_api,
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
                "public_api": (
                    name in self.module_all
                    if self.module_all is not None
                    else parent is None and not name.startswith("_")
                ),
                "parameter_count": 0,
                "decorators": [],
                "bases": [],
                "imports": self.imports,
                "calls": [],
                "references": [],
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
    public_api: bool,
    calls: Vec<CallRef>,
    references: Vec<CallRef>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CallRef {
    name: String,
    line: usize,
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
    single_callers: Vec<SingleCallerFinding>,
    single_callees: Vec<SingleCalleeFinding>,
    analyzed_files: Vec<String>,
}

#[derive(Debug, PartialEq, Eq)]
struct SingleCallerFinding {
    target: Block,
    caller: CallerEvidence,
    call_site_count: usize,
    similar_callers: Vec<SimilarCallerEvidence>,
    hash: String,
}

#[derive(Debug, PartialEq, Eq)]
struct CallerEvidence {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: Vec<usize>,
}

#[derive(Debug, PartialEq, Eq)]
struct SingleCalleeFinding {
    caller: Block,
    callee: CalleeEvidence,
    call_site_count: usize,
    hash: String,
}

#[derive(Debug, PartialEq, Eq)]
struct CalleeEvidence {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: Vec<usize>,
}

#[derive(Debug, PartialEq, Eq)]
struct SimilarCallerEvidence {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    token_count: usize,
    structure_hash: String,
    parent_scope: String,
    score: usize,
    shared_call_count: usize,
    shared_profile: Vec<String>,
    reason_codes: Vec<String>,
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
    let files = expand_with_repo_import_neighborhood(&root, files, &args.excludes);
    let analyzed_files = files
        .iter()
        .map(|path| relative_path(&root, path))
        .collect::<Vec<_>>();
    let ast_blocks = extract_ast_blocks(&root, &files)?;
    let mut all_blocks = Vec::new();
    let mut buckets: BTreeMap<String, Vec<Block>> = BTreeMap::new();
    for value in ast_blocks {
        let block = block_from_ast_value(value)?;
        all_blocks.push(block.clone());
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
    let mut single_callers = single_caller_findings(&all_blocks, args.min_tokens);
    single_callers.sort_by(|left, right| {
        right
            .target
            .token_count
            .cmp(&left.target.token_count)
            .then_with(|| left.hash.cmp(&right.hash))
    });
    single_callers.truncate(args.max_findings);
    let mut single_callees = single_callee_findings(&all_blocks, args.min_tokens);
    single_callees.sort_by(|left, right| {
        right
            .caller
            .token_count
            .cmp(&left.caller.token_count)
            .then_with(|| left.hash.cmp(&right.hash))
    });
    single_callees.truncate(args.max_findings);
    Ok(Analysis {
        groups,
        single_callers,
        single_callees,
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

fn expand_with_repo_import_neighborhood(
    root: &Path,
    initial_files: Vec<PathBuf>,
    excludes: &[String],
) -> Vec<PathBuf> {
    let mut files = initial_files
        .into_iter()
        .map(|path| fs::canonicalize(&path).unwrap_or(path))
        .collect::<BTreeSet<_>>();
    let all_repo_files = source_files(root, &[], excludes);
    let import_targets = all_repo_files
        .iter()
        .map(|path| {
            (
                fs::canonicalize(path).unwrap_or_else(|_| path.clone()),
                repo_import_targets(root, path, excludes)
                    .into_iter()
                    .collect::<BTreeSet<_>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();

    loop {
        let before = files.len();
        for path in files.clone() {
            if let Some(targets) = import_targets.get(&path) {
                files.extend(targets.iter().cloned());
            }
        }
        for (path, targets) in &import_targets {
            if files.contains(path) {
                continue;
            }
            if targets.iter().any(|target| files.contains(target)) {
                files.insert(path.clone());
            }
        }
        if files.len() == before {
            break;
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
                let name = item.split_whitespace().next().unwrap_or("");
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
        let name = item.split_whitespace().next().unwrap_or("");
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
    let mut relative = path.strip_prefix(root).ok()?.with_extension("");
    if relative.file_name().and_then(|value| value.to_str()) == Some("__init__") {
        relative = relative.parent()?.to_path_buf();
    }
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
    let calls = call_refs_field(&value, "calls")?;
    let references = call_refs_field(&value, "references")?;
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
        public_api: value
            .get("public_api")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        calls,
        references,
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

fn call_refs_field(value: &Value, field: &str) -> Result<Vec<CallRef>, String> {
    let calls = value
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("AST block field {field} must be an array"))?;
    calls
        .iter()
        .map(|call| {
            Ok(CallRef {
                name: string_field(call, "name")?,
                line: usize_field(call, "line")?,
            })
        })
        .collect()
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

fn single_caller_findings(blocks: &[Block], min_tokens: usize) -> Vec<SingleCallerFinding> {
    let mut by_name = BTreeMap::<String, Vec<usize>>::new();
    let mut by_qualname = BTreeMap::<String, usize>::new();
    for (index, block) in blocks.iter().enumerate() {
        by_name.entry(block.name.clone()).or_default().push(index);
        by_qualname.insert(block.qualname.clone(), index);
    }

    let mut target_callers = BTreeMap::<String, BTreeMap<String, CallerAccumulator>>::new();
    for caller in blocks {
        for call in &caller.calls {
            if let Some(target_index) =
                resolve_call_target(blocks, &by_name, &by_qualname, caller, call)
            {
                record_single_caller_usage(
                    blocks,
                    min_tokens,
                    &mut target_callers,
                    caller,
                    target_index,
                    call.line,
                );
            }
        }
        for reference in &caller.references {
            if let Some(target_index) =
                resolve_reference_target(blocks, &by_name, &by_qualname, caller, reference)
            {
                record_single_caller_usage(
                    blocks,
                    min_tokens,
                    &mut target_callers,
                    caller,
                    target_index,
                    reference.line,
                );
            }
        }
    }

    let block_by_key = blocks
        .iter()
        .map(|block| (block_key(block), block))
        .collect::<BTreeMap<_, _>>();
    target_callers
        .into_iter()
        .filter_map(|(target_key, callers)| {
            if callers.len() != 1 {
                return None;
            }
            let target = (*block_by_key.get(&target_key)?).clone();
            let (caller_key, caller) = callers.into_iter().next()?;
            let caller_block = *block_by_key.get(&caller_key)?;
            let call_lines = caller.call_lines.into_iter().collect::<Vec<_>>();
            let similar_callers = similar_responsibility_callers(blocks, caller_block, &target_key);
            Some(SingleCallerFinding {
                hash: stable_hash(&format!(
                    "single-caller:{}:{}:{}:{}",
                    target.kind, target.role, target.structure_hash, caller.qualname
                )),
                target,
                call_site_count: call_lines.len(),
                similar_callers,
                caller: CallerEvidence {
                    path: caller.path,
                    module: caller.module,
                    qualname: caller.qualname,
                    line: caller.line,
                    end_line: caller.end_line,
                    call_lines,
                },
            })
        })
        .collect()
}

fn single_callee_findings(blocks: &[Block], min_tokens: usize) -> Vec<SingleCalleeFinding> {
    let mut by_name = BTreeMap::<String, Vec<usize>>::new();
    let mut by_qualname = BTreeMap::<String, usize>::new();
    for (index, block) in blocks.iter().enumerate() {
        by_name.entry(block.name.clone()).or_default().push(index);
        by_qualname.insert(block.qualname.clone(), index);
    }

    let block_by_key = blocks
        .iter()
        .map(|block| (block_key(block), block))
        .collect::<BTreeMap<_, _>>();
    blocks
        .iter()
        .filter_map(|caller| {
            if !single_callee_caller_eligible(caller, min_tokens) {
                return None;
            }
            let mut callees = BTreeMap::<String, CalleeAccumulator>::new();
            for call in &caller.calls {
                if let Some(target_index) =
                    resolve_call_target(blocks, &by_name, &by_qualname, caller, call)
                {
                    record_single_callee_usage(
                        blocks,
                        &mut callees,
                        caller,
                        target_index,
                        call.line,
                    );
                }
            }
            if callees.len() != 1 {
                return None;
            }
            let (callee_key, callee) = callees.into_iter().next()?;
            let target = *block_by_key.get(&callee_key)?;
            let call_lines = callee.call_lines.into_iter().collect::<Vec<_>>();
            Some(SingleCalleeFinding {
                hash: stable_hash(&format!(
                    "single-callee:{}:{}:{}:{}",
                    caller.kind, caller.role, caller.structure_hash, target.qualname
                )),
                caller: caller.clone(),
                call_site_count: call_lines.len(),
                callee: CalleeEvidence {
                    path: callee.path,
                    module: callee.module,
                    qualname: callee.qualname,
                    line: callee.line,
                    end_line: callee.end_line,
                    call_lines,
                },
            })
        })
        .collect()
}

fn record_single_caller_usage(
    blocks: &[Block],
    min_tokens: usize,
    target_callers: &mut BTreeMap<String, BTreeMap<String, CallerAccumulator>>,
    caller: &Block,
    target_index: usize,
    line: usize,
) {
    let target = &blocks[target_index];
    if !single_caller_target_eligible(target, min_tokens) {
        return;
    }
    let target_key = block_key(target);
    let caller_key = block_key(caller);
    if target_key == caller_key {
        return;
    }
    target_callers
        .entry(target_key)
        .or_default()
        .entry(caller_key)
        .or_insert_with(|| CallerAccumulator::new(caller))
        .call_lines
        .insert(line);
}

fn record_single_callee_usage(
    blocks: &[Block],
    caller_callees: &mut BTreeMap<String, CalleeAccumulator>,
    caller: &Block,
    target_index: usize,
    line: usize,
) {
    let target = &blocks[target_index];
    if !single_callee_target_eligible(target) {
        return;
    }
    let caller_key = block_key(caller);
    let target_key = block_key(target);
    if caller_key == target_key {
        return;
    }
    caller_callees
        .entry(target_key)
        .or_insert_with(|| CalleeAccumulator::new(target))
        .call_lines
        .insert(line);
}

fn similar_responsibility_callers(
    blocks: &[Block],
    caller: &Block,
    target_key: &str,
) -> Vec<SimilarCallerEvidence> {
    let caller_profile = responsibility_profile(caller);
    let caller_key = block_key(caller);
    let mut peers = blocks
        .iter()
        .filter(|candidate| {
            let candidate_key = block_key(candidate);
            candidate_key != caller_key && candidate_key != target_key
        })
        .filter(|candidate| candidate.role == "implementation")
        .filter(|candidate| candidate.kind == caller.kind)
        .filter(|candidate| candidate.module == caller.module)
        .filter_map(|candidate| similar_caller_evidence(caller, &caller_profile, candidate))
        .collect::<Vec<_>>();
    peers.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| right.shared_call_count.cmp(&left.shared_call_count))
            .then_with(|| left.path.cmp(&right.path))
            .then_with(|| left.qualname.cmp(&right.qualname))
    });
    peers.truncate(5);
    peers
}

fn similar_caller_evidence(
    caller: &Block,
    caller_profile: &BTreeSet<String>,
    candidate: &Block,
) -> Option<SimilarCallerEvidence> {
    let candidate_profile = responsibility_profile(candidate);
    let shared_profile = caller_profile
        .intersection(&candidate_profile)
        .cloned()
        .collect::<Vec<_>>();
    let shared_call_count = shared_profile.len();
    let same_structure = caller.structure_hash == candidate.structure_hash;
    let same_non_module_parent = same_non_module_parent_scope(caller, candidate);
    if !same_structure
        && shared_call_count < 2
        && !(same_non_module_parent && shared_call_count >= 1)
    {
        return None;
    }

    let mut score = 0usize;
    let mut reason_codes = Vec::new();
    if same_structure {
        score += 10;
        reason_codes.push("same_caller_structure".to_string());
    }
    if same_non_module_parent {
        score += 4;
        reason_codes.push("same_parent_scope".to_string());
    }
    if same_token_band(caller, candidate) {
        score += 1;
        reason_codes.push("similar_token_band".to_string());
    }
    if shared_call_count > 0 {
        score += shared_call_count * 2;
        reason_codes.push("shared_call_profile".to_string());
    }
    Some(SimilarCallerEvidence {
        path: candidate.path.clone(),
        module: candidate.module.clone(),
        qualname: candidate.qualname.clone(),
        line: candidate.line,
        end_line: candidate.end_line,
        token_count: candidate.token_count,
        structure_hash: candidate.structure_hash.clone(),
        parent_scope: parent_scope_value(candidate),
        score,
        shared_call_count,
        shared_profile,
        reason_codes,
    })
}

fn responsibility_profile(block: &Block) -> BTreeSet<String> {
    block
        .calls
        .iter()
        .chain(block.references.iter())
        .map(|call| normalized_reference_name(&call.name))
        .filter(|name| !name.is_empty())
        .collect()
}

fn normalized_reference_name(name: &str) -> String {
    name.strip_prefix("self.")
        .map(|value| format!("self.{value}"))
        .or_else(|| {
            name.strip_prefix("cls.")
                .map(|value| format!("cls.{value}"))
        })
        .unwrap_or_else(|| name.to_string())
}

fn same_non_module_parent_scope(left: &Block, right: &Block) -> bool {
    if left.parent_kind.is_none() || right.parent_kind.is_none() {
        return false;
    }
    left.parent_kind == right.parent_kind && left.parent_name == right.parent_name
}

fn parent_scope_value(block: &Block) -> String {
    match (&block.parent_kind, &block.parent_name) {
        (Some(kind), Some(name)) => format!("{kind}:{name}"),
        _ => "<module>".to_string(),
    }
}

fn same_token_band(left: &Block, right: &Block) -> bool {
    let min = left.token_count.min(right.token_count).max(1);
    let max = left.token_count.max(right.token_count);
    max <= min * 2
}

#[derive(Debug)]
struct CallerAccumulator {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: BTreeSet<usize>,
}

impl CallerAccumulator {
    fn new(block: &Block) -> Self {
        Self {
            path: block.path.clone(),
            module: block.module.clone(),
            qualname: block.qualname.clone(),
            line: block.line,
            end_line: block.end_line,
            call_lines: BTreeSet::new(),
        }
    }
}

#[derive(Debug)]
struct CalleeAccumulator {
    path: String,
    module: String,
    qualname: String,
    line: usize,
    end_line: usize,
    call_lines: BTreeSet<usize>,
}

impl CalleeAccumulator {
    fn new(block: &Block) -> Self {
        Self {
            path: block.path.clone(),
            module: block.module.clone(),
            qualname: block.qualname.clone(),
            line: block.line,
            end_line: block.end_line,
            call_lines: BTreeSet::new(),
        }
    }
}

fn single_caller_target_eligible(block: &Block, min_tokens: usize) -> bool {
    block.role == "implementation"
        && matches!(block.kind.as_str(), "Function" | "Class")
        && block.token_count >= min_tokens
}

fn single_callee_caller_eligible(block: &Block, min_tokens: usize) -> bool {
    block.role == "implementation"
        && block.kind == "Function"
        && block.token_count >= min_tokens
        && !block.public_api
}

fn single_callee_target_eligible(block: &Block) -> bool {
    block.role == "implementation" && matches!(block.kind.as_str(), "Function" | "Class")
}

fn resolve_call_target(
    blocks: &[Block],
    by_name: &BTreeMap<String, Vec<usize>>,
    by_qualname: &BTreeMap<String, usize>,
    caller: &Block,
    call: &CallRef,
) -> Option<usize> {
    if let Some(index) = by_qualname.get(&call.name) {
        let target = &blocks[*index];
        if target.module == caller.module {
            return Some(*index);
        }
    }
    if let Some(method_name) = call
        .name
        .strip_prefix("self.")
        .or_else(|| call.name.strip_prefix("cls."))
    {
        if method_name.contains('.') {
            return None;
        }
        let class_name = caller.parent_name.as_deref()?;
        return unique_candidate(blocks, by_name.get(method_name)?, |target| {
            target.module == caller.module
                && target.parent_kind.as_deref() == Some("Class")
                && target.parent_name.as_deref() == Some(class_name)
        });
    }
    if call.name.contains('.') {
        return None;
    }
    unique_candidate(blocks, by_name.get(&call.name)?, |target| {
        target.module == caller.module
    })
}

fn resolve_reference_target(
    blocks: &[Block],
    by_name: &BTreeMap<String, Vec<usize>>,
    by_qualname: &BTreeMap<String, usize>,
    caller: &Block,
    reference: &CallRef,
) -> Option<usize> {
    if let Some(index) = by_qualname.get(&reference.name) {
        let target = &blocks[*index];
        if target.module == caller.module && target.kind == "Class" {
            return Some(*index);
        }
    }
    if reference.name.contains('.') {
        return None;
    }
    unique_candidate(blocks, by_name.get(&reference.name)?, |target| {
        target.module == caller.module && target.kind == "Class"
    })
}

fn unique_candidate<F>(blocks: &[Block], candidates: &[usize], predicate: F) -> Option<usize>
where
    F: Fn(&Block) -> bool,
{
    let mut matching = candidates
        .iter()
        .copied()
        .filter(|index| predicate(&blocks[*index]))
        .collect::<Vec<_>>();
    matching.sort_unstable();
    matching.dedup();
    if matching.len() == 1 {
        matching.first().copied()
    } else {
        None
    }
}

fn block_key(block: &Block) -> String {
    format!("{}:{}", block.path, block.qualname)
}

fn render(analysis: Analysis, args: &Args) -> i32 {
    match args.format {
        OutputFormat::Json => render_json(&analysis),
        OutputFormat::Text => render_text(&analysis),
    }
    if analysis.groups.is_empty()
        && analysis.single_callers.is_empty()
        && analysis.single_callees.is_empty()
    {
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
    for finding in &analysis.single_callers {
        let target = &finding.target;
        println!(
            "PY_STRUCTURE_HASH_FINDING=single_caller_structural_helper:role={}:{}:params={}:tokens={}:hash={}:count=1:caller_count=1:call_site_count={}:caller={}:similar_callers={}:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:{}",
            target.role,
            target.kind,
            target.parameter_count,
            target.token_count,
            finding.hash,
            finding.call_site_count,
            caller_label(&finding.caller),
            similar_callers_label(&finding.similar_callers),
            instance_label(target)
        );
    }
    for finding in &analysis.single_callees {
        let caller = &finding.caller;
        println!(
            "PY_STRUCTURE_HASH_FINDING=single_callee_structural_wrapper:role={}:{}:params={}:tokens={}:hash={}:count=1:callee_count=1:call_site_count={}:public_api=false:callee={}:module_scope=SameModule:import_scope=SameImports:decorator_scope=SameDecorators:base_scope=SameBases:{}",
            caller.role,
            caller.kind,
            caller.parameter_count,
            caller.token_count,
            finding.hash,
            finding.call_site_count,
            callee_label(&finding.callee),
            instance_label(caller)
        );
    }
    println!(
        "PY_STRUCTURE_HASH_ANALYZED_FILES={}",
        analysis.analyzed_files.len()
    );
    for path in &analysis.analyzed_files {
        println!("PY_STRUCTURE_HASH_ANALYZED_FILE={path}");
    }
    println!(
        "PY_STRUCTURE_HASH_DUPLICATE_GROUPS={}",
        analysis.groups.len()
    );
    println!(
        "PY_STRUCTURE_HASH_SINGLE_CALLER_FINDINGS={}",
        analysis.single_callers.len()
    );
    println!(
        "PY_STRUCTURE_HASH_SINGLE_CALLEE_FINDINGS={}",
        analysis.single_callees.len()
    );
    println!(
        "PY_STRUCTURE_HASH_GROUPS={}",
        analysis.groups.len() + analysis.single_callers.len() + analysis.single_callees.len()
    );
    println!(
        "PY_STRUCTURE_HASH={}",
        if analysis.groups.is_empty()
            && analysis.single_callers.is_empty()
            && analysis.single_callees.is_empty()
        {
            "pass"
        } else {
            "fail"
        }
    );
}

fn similar_callers_label(similar_callers: &[SimilarCallerEvidence]) -> String {
    if similar_callers.is_empty() {
        return "none".to_string();
    }
    similar_callers
        .iter()
        .map(|caller| {
            format!(
                "{}@{}-{}@{}@{}@tokens={}@structure={}@parent={}@score={}@shared={}@profile={}@reasons={}",
                caller.path,
                caller.line,
                caller.end_line,
                caller.module,
                caller.qualname,
                caller.token_count,
                caller.structure_hash,
                caller.parent_scope.replace(':', "~"),
                caller.score,
                caller.shared_call_count,
                caller.shared_profile.join("|"),
                caller.reason_codes.join("|")
            )
        })
        .collect::<Vec<_>>()
        .join(";")
}

fn instance_label(block: &Block) -> String {
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
}

fn caller_label(caller: &CallerEvidence) -> String {
    format!(
        "{}@{}-{}@{}@{}@sites={}",
        caller.path,
        caller.line,
        caller.end_line,
        caller.module,
        caller.qualname,
        caller
            .call_lines
            .iter()
            .map(usize::to_string)
            .collect::<Vec<_>>()
            .join("|")
    )
}

fn callee_label(callee: &CalleeEvidence) -> String {
    format!(
        "{}@{}-{}@{}@{}@sites={}",
        callee.path,
        callee.line,
        callee.end_line,
        callee.module,
        callee.qualname,
        callee
            .call_lines
            .iter()
            .map(usize::to_string)
            .collect::<Vec<_>>()
            .join("|")
    )
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
    let duplicate_findings = analysis.groups.iter().map(|group| {
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
                    "public_api": block.public_api,
                })
            }).collect::<Vec<_>>(),
        })
    });
    let single_caller_findings = analysis.single_callers.iter().map(|finding| {
        let block = &finding.target;
        json!({
            "kind": "single_caller_structural_helper",
            "hash": finding.hash,
            "block_kind": block.kind,
            "role": block.role,
            "parameter_count": block.parameter_count,
            "token_count": block.token_count,
            "module_scope": "SameModule",
            "import_scope": "SameImports",
            "decorator_scope": "SameDecorators",
            "base_scope": "SameBases",
            "caller_count": 1,
            "call_site_count": finding.call_site_count,
            "caller": {
                "path": finding.caller.path,
                "line": finding.caller.line,
                "end_line": finding.caller.end_line,
                "module": finding.caller.module,
                "qualname": finding.caller.qualname,
                "call_lines": finding.caller.call_lines,
            },
            "similar_responsibility_callers": finding.similar_callers.iter().map(|caller| {
                json!({
                    "path": caller.path,
                    "line": caller.line,
                    "end_line": caller.end_line,
                    "module": caller.module,
                    "qualname": caller.qualname,
                    "token_count": caller.token_count,
                    "structure_hash": caller.structure_hash,
                    "parent_scope": caller.parent_scope,
                    "score": caller.score,
                    "shared_call_count": caller.shared_call_count,
                    "shared_profile": caller.shared_profile,
                    "reason_codes": caller.reason_codes,
                })
            }).collect::<Vec<_>>(),
            "caller_analysis": {
                "caller_count": 1,
                "call_site_count": finding.call_site_count,
                "callers": [json!({
                    "path": finding.caller.path,
                    "line": finding.caller.line,
                    "end_line": finding.caller.end_line,
                    "module": finding.caller.module,
                    "qualname": finding.caller.qualname,
                    "call_lines": finding.caller.call_lines,
                })],
                "similar_responsibility_callers": finding.similar_callers.iter().map(|caller| {
                    json!({
                        "path": caller.path,
                        "line": caller.line,
                        "end_line": caller.end_line,
                        "module": caller.module,
                        "qualname": caller.qualname,
                        "token_count": caller.token_count,
                        "structure_hash": caller.structure_hash,
                        "parent_scope": caller.parent_scope,
                        "score": caller.score,
                        "shared_call_count": caller.shared_call_count,
                        "shared_profile": caller.shared_profile,
                        "reason_codes": caller.reason_codes,
                    })
                }).collect::<Vec<_>>(),
                "integration_candidates": direct_integration_candidates_json(finding),
                "enrichment_note": "python-structure-hash-report adds dependency-tree features to these AST/use-graph candidates",
            },
            "instances": [json!({
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
                "public_api": block.public_api,
            })],
        })
    });
    let single_callee_findings = analysis.single_callees.iter().map(|finding| {
        let block = &finding.caller;
        json!({
            "kind": "single_callee_structural_wrapper",
            "hash": finding.hash,
            "block_kind": block.kind,
            "role": block.role,
            "parameter_count": block.parameter_count,
            "token_count": block.token_count,
            "module_scope": "SameModule",
            "import_scope": "SameImports",
            "decorator_scope": "SameDecorators",
            "base_scope": "SameBases",
            "callee_count": 1,
            "call_site_count": finding.call_site_count,
            "public_api": false,
            "callee_analysis": {
                "callee_count": 1,
                "call_site_count": finding.call_site_count,
                "callees": [json!({
                    "path": finding.callee.path,
                    "line": finding.callee.line,
                    "end_line": finding.callee.end_line,
                    "module": finding.callee.module,
                    "qualname": finding.callee.qualname,
                    "call_lines": finding.callee.call_lines,
                })],
                "candidate_schema_scope": "ast_use_graph_only",
            },
            "instances": [json!({
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
                "public_api": block.public_api,
            })],
        })
    });
    let payload = json!({
        "summary": {
            "groups": analysis.groups.len() + analysis.single_callers.len() + analysis.single_callees.len(),
            "duplicate_groups": analysis.groups.len(),
            "single_caller_findings": analysis.single_callers.len(),
            "single_callee_findings": analysis.single_callees.len(),
            "status": if analysis.groups.is_empty() && analysis.single_callers.is_empty() && analysis.single_callees.is_empty() { "pass" } else { "fail" },
            "analyzed_file_count": analysis.analyzed_files.len(),
            "analyzed_files": analysis.analyzed_files,
        },
        "findings": duplicate_findings.chain(single_caller_findings).chain(single_callee_findings).collect::<Vec<_>>(),
    });
    println!(
        "{}",
        serde_json::to_string_pretty(&payload).expect("json payload serializes")
    );
}

fn direct_integration_candidates_json(finding: &SingleCallerFinding) -> Vec<Value> {
    let target = &finding.target;
    let base_features = vec![
        json!({"code": "unique_owner", "weight": 40, "detail": "caller_count=1"}),
        json!({"code": "module_local_ownership", "weight": 20, "detail": format!("module={}", target.module)}),
        json!({"code": "usage_site_count", "weight": finding.call_site_count.min(5) * 4, "detail": format!("call_site_count={}", finding.call_site_count)}),
        json!({"code": "target_structure_size", "weight": target.token_count.min(50), "detail": format!("block_kind={},token_count={}", target.kind, target.token_count)}),
        json!({"code": "ast_block_kind", "weight": 8, "detail": target.kind}),
    ];
    let mut candidates = vec![json!({
        "candidate_kind": direct_single_owner_candidate_kind(&target.kind),
        "candidate_schema_scope": "ast_use_graph_only",
        "target": direct_block_json(target),
        "destination_caller": direct_caller_json(&finding.caller),
        "score": base_features.iter().filter_map(|feature| feature.get("weight").and_then(Value::as_u64)).sum::<u64>(),
        "reason_codes": feature_codes(&base_features),
        "features": base_features,
    })];
    candidates.extend(finding.similar_callers.iter().map(|similar| {
        let mut features = vec![
            json!({"code": "unique_owner", "weight": 40, "detail": "caller_count=1"}),
            json!({"code": "similar_responsibility_caller", "weight": 30, "detail": format!("similar={}", similar.qualname)}),
            json!({"code": "shared_call_profile_count", "weight": similar.shared_call_count * 8, "detail": format!("shared_call_count={}", similar.shared_call_count)}),
        ];
        features.extend(similar.reason_codes.iter().map(|reason| {
            json!({"code": "similarity_reason", "weight": direct_similarity_reason_weight(reason), "detail": reason})
        }));
        json!({
            "candidate_kind": "consolidate_owner_with_similar_responsibility_caller",
            "candidate_schema_scope": "ast_use_graph_only",
            "target": direct_block_json(target),
            "destination_caller": direct_caller_json(&finding.caller),
            "similar_caller": {
                "path": similar.path,
                "line": similar.line,
                "end_line": similar.end_line,
                "module": similar.module,
                "qualname": similar.qualname,
                "token_count": similar.token_count,
                "structure_hash": similar.structure_hash,
                "parent_scope": similar.parent_scope,
                "shared_profile": similar.shared_profile,
                "reason_codes": similar.reason_codes,
            },
            "score": features.iter().filter_map(|feature| feature.get("weight").and_then(Value::as_u64)).sum::<u64>(),
            "reason_codes": feature_codes(&features),
            "features": features,
        })
    }));
    candidates
}

fn feature_codes(features: &[Value]) -> Vec<String> {
    features
        .iter()
        .filter_map(|feature| feature.get("code").and_then(Value::as_str))
        .map(str::to_string)
        .collect()
}

fn direct_block_json(block: &Block) -> Value {
    json!({
        "path": block.path,
        "line": block.line,
        "end_line": block.end_line,
        "module": block.module,
        "qualname": block.qualname,
        "block_kind": block.kind,
        "token_count": block.token_count,
        "structure_hash": block.structure_hash,
        "parent_scope": parent_scope_value(block),
    })
}

fn direct_caller_json(caller: &CallerEvidence) -> Value {
    json!({
        "path": caller.path,
        "line": caller.line,
        "end_line": caller.end_line,
        "module": caller.module,
        "qualname": caller.qualname,
        "call_lines": caller.call_lines,
    })
}

fn direct_single_owner_candidate_kind(block_kind: &str) -> &'static str {
    match block_kind {
        "Class" => "move_or_nest_single_owner_type",
        "Alias" => "inline_single_owner_alias",
        _ => "inline_target_into_owner",
    }
}

fn direct_similarity_reason_weight(reason: &str) -> usize {
    match reason {
        "same_caller_structure" => 20,
        "same_parent_scope" => 12,
        "shared_call_profile" => 10,
        "similar_token_band" => 4,
        _ => 1,
    }
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
    fn source_files_expand_repo_import_neighborhood() {
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
        let expanded = expand_with_repo_import_neighborhood(&root, initial, &[]);
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
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        }
    }

    #[test]
    fn single_caller_groups_multiple_call_sites_by_enclosing_block() {
        let helper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 2,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_helper".to_string(),
            qualname: "_helper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("helper"),
            context_hash: stable_hash("sample"),
            token_count: 12,
            public_api: false,
            calls: vec![
                CallRef {
                    name: "load_config".to_string(),
                    line: 1,
                },
                CallRef {
                    name: "validate_inputs".to_string(),
                    line: 2,
                },
            ],
            references: Vec::new(),
        };
        let caller = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 4,
            end_line: 7,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "public_api".to_string(),
            qualname: "public_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("caller"),
            context_hash: stable_hash("sample"),
            token_count: 20,
            public_api: true,
            calls: vec![
                CallRef {
                    name: "_helper".to_string(),
                    line: 5,
                },
                CallRef {
                    name: "_helper".to_string(),
                    line: 6,
                },
                CallRef {
                    name: "load_config".to_string(),
                    line: 7,
                },
                CallRef {
                    name: "validate_inputs".to_string(),
                    line: 8,
                },
            ],
            references: Vec::new(),
        };
        let peer = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 9,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "other_api".to_string(),
            qualname: "other_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("peer"),
            context_hash: stable_hash("sample"),
            token_count: 18,
            public_api: true,
            calls: vec![
                CallRef {
                    name: "load_config".to_string(),
                    line: 10,
                },
                CallRef {
                    name: "validate_inputs".to_string(),
                    line: 11,
                },
            ],
            references: Vec::new(),
        };
        let findings = single_caller_findings(&[helper, caller, peer], 8);
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].target.qualname, "_helper");
        assert_eq!(findings[0].caller.qualname, "public_api");
        assert_eq!(findings[0].call_site_count, 2);
        assert_eq!(findings[0].caller.call_lines, vec![5, 6]);
        assert_eq!(findings[0].similar_callers[0].qualname, "other_api");
        assert_eq!(findings[0].similar_callers[0].shared_call_count, 2);
        assert!(!findings[0]
            .similar_callers
            .iter()
            .any(|caller| caller.qualname == "_helper"));
        let candidates = direct_integration_candidates_json(&findings[0]);
        assert_eq!(
            candidates[0]["candidate_schema_scope"],
            "ast_use_graph_only"
        );
        assert!(candidates[0]["reason_codes"]
            .as_array()
            .expect("reason codes")
            .iter()
            .any(|code| code == "unique_owner"));
    }

    #[test]
    fn one_shared_module_level_call_does_not_create_similar_caller() {
        let helper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 2,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_helper".to_string(),
            qualname: "_helper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("helper"),
            context_hash: stable_hash("sample"),
            token_count: 12,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let caller = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 4,
            end_line: 7,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "public_api".to_string(),
            qualname: "public_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("caller"),
            context_hash: stable_hash("sample"),
            token_count: 20,
            public_api: true,
            calls: vec![
                CallRef {
                    name: "_helper".to_string(),
                    line: 5,
                },
                CallRef {
                    name: "load".to_string(),
                    line: 6,
                },
            ],
            references: Vec::new(),
        };
        let peer = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 9,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "other_api".to_string(),
            qualname: "other_api".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("peer"),
            context_hash: stable_hash("sample"),
            token_count: 18,
            public_api: true,
            calls: vec![CallRef {
                name: "load".to_string(),
                line: 10,
            }],
            references: Vec::new(),
        };

        let findings = single_caller_findings(&[helper, caller, peer], 8);

        assert_eq!(findings.len(), 1);
        assert!(findings[0].similar_callers.is_empty());
    }

    #[test]
    fn single_caller_class_target_detects_annotation_owner() {
        let class_target = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 8,
            kind: "Class".to_string(),
            role: "implementation".to_string(),
            name: "Carry".to_string(),
            qualname: "Carry".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 0,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("class"),
            context_hash: stable_hash("sample"),
            token_count: 16,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let owner = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 10,
            end_line: 15,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "solve".to_string(),
            qualname: "solve".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 0,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("owner"),
            context_hash: stable_hash("sample"),
            token_count: 20,
            public_api: true,
            calls: Vec::new(),
            references: vec![CallRef {
                name: "Carry".to_string(),
                line: 11,
            }],
        };

        let findings = single_caller_findings(&[class_target, owner], 8);

        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].target.kind, "Class");
        assert_eq!(findings[0].target.qualname, "Carry");
        assert_eq!(findings[0].caller.qualname, "solve");
        assert_eq!(findings[0].call_site_count, 1);
    }

    #[test]
    fn single_callee_reports_only_non_public_wrappers() {
        let callee = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 4,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_target".to_string(),
            qualname: "_target".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("target"),
            context_hash: stable_hash("sample"),
            token_count: 16,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let wrapper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 6,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_wrapper".to_string(),
            qualname: "_wrapper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("wrapper"),
            context_hash: stable_hash("sample"),
            token_count: 24,
            public_api: false,
            calls: vec![
                CallRef {
                    name: "_target".to_string(),
                    line: 8,
                },
                CallRef {
                    name: "_target".to_string(),
                    line: 10,
                },
            ],
            references: Vec::new(),
        };
        let public_wrapper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 14,
            end_line: 20,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "public_wrapper".to_string(),
            qualname: "public_wrapper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("public_wrapper"),
            context_hash: stable_hash("sample"),
            token_count: 24,
            public_api: true,
            calls: vec![CallRef {
                name: "_target".to_string(),
                line: 16,
            }],
            references: Vec::new(),
        };

        let findings = single_callee_findings(&[callee, wrapper, public_wrapper], 8);

        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].caller.qualname, "_wrapper");
        assert_eq!(findings[0].callee.qualname, "_target");
        assert_eq!(findings[0].call_site_count, 2);
        assert_eq!(findings[0].callee.call_lines, vec![8, 10]);
    }

    #[test]
    fn single_callee_ignores_annotation_only_references() {
        let target = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 1,
            end_line: 4,
            kind: "Class".to_string(),
            role: "implementation".to_string(),
            name: "Target".to_string(),
            qualname: "Target".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("target"),
            context_hash: stable_hash("sample"),
            token_count: 16,
            public_api: false,
            calls: Vec::new(),
            references: Vec::new(),
        };
        let annotation_only_wrapper = Block {
            path: "sample.py".to_string(),
            module: "sample".to_string(),
            line: 6,
            end_line: 12,
            kind: "Function".to_string(),
            role: "implementation".to_string(),
            name: "_typed_wrapper".to_string(),
            qualname: "_typed_wrapper".to_string(),
            parent_kind: None,
            parent_name: None,
            parameter_count: 1,
            decorators_hash: stable_hash("[]"),
            bases_hash: stable_hash("[]"),
            import_hash: stable_hash("[]"),
            structure_hash: stable_hash("typed_wrapper"),
            context_hash: stable_hash("sample"),
            token_count: 24,
            public_api: false,
            calls: Vec::new(),
            references: vec![CallRef {
                name: "Target".to_string(),
                line: 8,
            }],
        };

        let findings = single_callee_findings(&[target, annotation_only_wrapper], 8);

        assert!(findings.is_empty());
    }
}
