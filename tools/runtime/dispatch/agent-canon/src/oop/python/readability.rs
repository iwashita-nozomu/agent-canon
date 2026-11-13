// @dependency-start
// contract implementation
// responsibility Extracts existing Python OOP metrics from native RustPython ASTs.
// upstream implementation ../readability.rs owns thresholds and findings
// upstream implementation ../../python_ast.rs owns source positions
// @dependency-end

use crate::oop_readability::{integer_value, Finding, Thresholds};
use crate::python_ast::node_line;
use rustpython_ast::bigint::BigInt;
use rustpython_ast::Visitor;
use rustpython_parser::{ast, Parse};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

#[derive(Default, Clone)]
pub(crate) struct Usage {
    constructors: usize,
    annotations: usize,
    inheritance: usize,
    isinstance: usize,
    methods: usize,
    attrs: usize,
    files: BTreeSet<String>,
}
pub(crate) struct UsageIndex {
    values: BTreeMap<String, Usage>,
    modules: BTreeMap<String, String>,
}
impl UsageIndex {
    fn get(&self, path: &str, name: &str) -> Option<&Usage> {
        self.modules
            .get(path)
            .and_then(|module| self.values.get(&format!("{module}.{name}")))
    }
}

pub(crate) fn usage_index(sources: &[(String, String)], roots: &[PathBuf]) -> UsageIndex {
    let mut modules = BTreeMap::new();
    let mut definitions = BTreeSet::new();
    let mut simple = BTreeMap::<String, Vec<String>>::new();
    let mut trees = Vec::new();
    let mut roots = roots.to_vec();
    roots.sort_by_key(|root| std::cmp::Reverse(root.components().count()));
    struct Classes(Vec<String>);
    impl Visitor for Classes {
        fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
            self.0.push(node.name.to_string());
            self.generic_visit_stmt_class_def(node);
        }
    }
    for (path, source) in sources {
        let Ok(tree) = ast::Suite::parse(source, path) else {
            continue;
        };
        let source_path = Path::new(path);
        let relative = roots
            .iter()
            .find_map(|root| source_path.strip_prefix(root).ok())
            .unwrap_or(source_path);
        let module = crate::python_ast::module_name(relative);
        modules.insert(path.clone(), module.clone());
        let mut classes = Classes(Vec::new());
        for statement in &tree {
            classes.visit_stmt(statement.clone());
        }
        for name in classes.0 {
            let key = format!("{module}.{name}");
            definitions.insert(key.clone());
            simple.entry(name).or_default().push(key);
        }
        trees.push((path.clone(), module, tree));
    }
    let unique = simple
        .into_iter()
        .filter_map(|(name, keys)| {
            if keys.len() == 1 {
                Some((name, keys[0].clone()))
            } else {
                None
            }
        })
        .collect::<BTreeMap<_, _>>();
    let mut values = definitions
        .iter()
        .map(|key| (key.clone(), Usage::default()))
        .collect::<BTreeMap<_, _>>();
    for (path, module, tree) in trees {
        let mut aliases = BTreeMap::new();
        for statement in &tree {
            match statement {
                ast::Stmt::Import(node) => {
                    for alias in &node.names {
                        let name = alias.name.as_str();
                        if definitions
                            .iter()
                            .any(|key| key.starts_with(&format!("{name}.")))
                        {
                            aliases.insert(
                                alias
                                    .asname
                                    .as_ref()
                                    .map(|name| name.as_str())
                                    .unwrap_or_else(|| name.split('.').next().unwrap())
                                    .to_owned(),
                                name.to_owned(),
                            );
                        }
                    }
                }
                ast::Stmt::ImportFrom(node) => {
                    let level = node.level.as_ref().map_or(0, |value| value.to_usize());
                    let prefix = if level == 0 {
                        String::new()
                    } else {
                        let parts = module.split('.').collect::<Vec<_>>();
                        parts[..parts.len().saturating_sub(level)].join(".")
                    };
                    let imported = node.module.as_ref().map(|name| name.as_str()).unwrap_or("");
                    let owner = if prefix.is_empty() {
                        imported.to_owned()
                    } else if imported.is_empty() {
                        prefix
                    } else {
                        format!("{prefix}.{imported}")
                    };
                    for alias in &node.names {
                        let key = if owner.is_empty() {
                            alias.name.to_string()
                        } else {
                            format!("{owner}.{}", alias.name)
                        };
                        if definitions.contains(&key)
                            || definitions
                                .iter()
                                .any(|name| name.starts_with(&format!("{key}.")))
                        {
                            aliases.insert(
                                alias.asname.as_ref().unwrap_or(&alias.name).to_string(),
                                key,
                            );
                        }
                    }
                }
                _ => {}
            }
        }
        let mut collector = UsageCollector {
            definitions: &definitions,
            unique: &unique,
            aliases: &aliases,
            module: &module,
            path: &path,
            values: &mut values,
            variables: BTreeMap::new(),
        };
        for statement in tree {
            collector.visit_stmt(statement);
        }
    }
    UsageIndex { values, modules }
}

struct UsageCollector<'a> {
    definitions: &'a BTreeSet<String>,
    unique: &'a BTreeMap<String, String>,
    aliases: &'a BTreeMap<String, String>,
    module: &'a str,
    path: &'a str,
    values: &'a mut BTreeMap<String, Usage>,
    variables: BTreeMap<String, String>,
}
impl UsageCollector<'_> {
    fn resolve(&self, expression: &ast::Expr) -> Option<String> {
        let value = dotted(expression);
        if value.is_empty() {
            return None;
        }
        if self.definitions.contains(&value) {
            return Some(value);
        }
        if let Some((head, tail)) = value.split_once('.') {
            if let Some(alias) = self.aliases.get(head) {
                let candidate = format!("{alias}.{tail}");
                if self.definitions.contains(&candidate) {
                    return Some(candidate);
                }
            }
            return None;
        }
        if let Some(alias) = self
            .aliases
            .get(&value)
            .filter(|alias| self.definitions.contains(*alias))
        {
            return Some(alias.clone());
        }
        let local = format!("{}.{}", self.module, value);
        if self.definitions.contains(&local) {
            return Some(local);
        }
        self.unique.get(&value).cloned()
    }
    fn record(&mut self, key: &str, field: u8) {
        if let Some(value) = self.values.get_mut(key) {
            match field {
                0 => value.constructors += 1,
                1 => value.annotations += 1,
                2 => value.inheritance += 1,
                3 => value.isinstance += 1,
                4 => value.methods += 1,
                _ => value.attrs += 1,
            };
            value.files.insert(self.path.into());
        }
    }
    fn annotation(&mut self, expression: &ast::Expr, field: u8) {
        struct References(Vec<ast::Expr>);
        impl Visitor for References {
            fn visit_expr(&mut self, node: ast::Expr) {
                self.0.push(node.clone());
                self.generic_visit_expr(node);
            }
        }
        let mut expressions = References(Vec::new());
        expressions.visit_expr(expression.clone());
        let keys = expressions
            .0
            .iter()
            .filter_map(|expression| self.resolve(expression))
            .collect::<BTreeSet<_>>();
        for key in keys {
            self.record(&key, field);
        }
    }
}
impl Visitor for UsageCollector<'_> {
    fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
        for base in &node.bases {
            if let Some(key) = self.resolve(base) {
                self.record(&key, 2);
            }
        }
        self.generic_visit_stmt_class_def(node);
    }
    fn visit_arg(&mut self, node: ast::Arg) {
        if let Some(annotation) = &node.annotation {
            self.annotation(annotation, 1);
        }
        self.generic_visit_arg(node);
    }
    fn visit_stmt_function_def(&mut self, node: ast::StmtFunctionDef) {
        let previous = std::mem::take(&mut self.variables);
        if let Some(annotation) = &node.returns {
            self.annotation(annotation, 1);
        }
        self.generic_visit_stmt_function_def(node);
        self.variables = previous;
    }
    fn visit_stmt_async_function_def(&mut self, node: ast::StmtAsyncFunctionDef) {
        let previous = std::mem::take(&mut self.variables);
        if let Some(annotation) = &node.returns {
            self.annotation(annotation, 1);
        }
        self.generic_visit_stmt_async_function_def(node);
        self.variables = previous;
    }
    fn visit_stmt_ann_assign(&mut self, node: ast::StmtAnnAssign) {
        self.annotation(&node.annotation, 1);
        if let (ast::Expr::Name(target), Some(ast::Expr::Call(call))) =
            (&*node.target, node.value.as_deref())
        {
            if let Some(key) = self.resolve(&call.func) {
                self.variables.insert(target.id.to_string(), key);
            }
        }
        self.generic_visit_stmt_ann_assign(node);
    }
    fn visit_stmt_assign(&mut self, node: ast::StmtAssign) {
        if let ast::Expr::Call(call) = &*node.value {
            if let Some(key) = self.resolve(&call.func) {
                for target in &node.targets {
                    if let ast::Expr::Name(target) = target {
                        self.variables.insert(target.id.to_string(), key.clone());
                    }
                }
            }
        }
        self.generic_visit_stmt_assign(node);
    }
    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        if ["isinstance", "issubclass"].contains(&dotted(&node.func).as_str())
            && node.args.len() >= 2
        {
            self.annotation(&node.args[1], 3);
        } else if let Some(key) = self.resolve(&node.func) {
            self.record(&key, 0);
        }
        if let ast::Expr::Attribute(attribute) = &*node.func {
            if let ast::Expr::Name(name) = &*attribute.value {
                if let Some(key) = self.variables.get(name.id.as_str()).cloned() {
                    self.record(&key, 4);
                }
            }
        }
        self.generic_visit_expr_call(node);
    }
    fn visit_expr_attribute(&mut self, node: ast::ExprAttribute) {
        if let ast::Expr::Name(name) = &*node.value {
            if let Some(key) = self.variables.get(name.id.as_str()).cloned() {
                self.record(&key, 5);
            }
        }
        self.generic_visit_expr_attribute(node);
    }
}

fn dotted(expr: &ast::Expr) -> String {
    match expr {
        ast::Expr::Name(node) => node.id.to_string(),
        ast::Expr::Attribute(node) => format!("{}.{}", dotted(&node.value), node.attr),
        ast::Expr::Subscript(node) => dotted(&node.value),
        _ => String::new(),
    }
}

#[derive(Default)]
struct Facts {
    names: BTreeSet<String>,
    attrs: BTreeSet<String>,
    locals: BTreeSet<String>,
    calls: Vec<(String, Option<String>)>,
    returns: bool,
    none_checks: usize,
}
impl Visitor for Facts {
    fn visit_expr_name(&mut self, node: ast::ExprName) {
        self.names.insert(node.id.to_string());
        if node.ctx == ast::ExprContext::Store {
            self.locals.insert(node.id.to_string());
        }
    }
    fn visit_expr_attribute(&mut self, node: ast::ExprAttribute) {
        if dotted(&node.value) == "self" && node.ctx == ast::ExprContext::Store {
            self.attrs.insert(node.attr.to_string());
        }
        self.generic_visit_expr_attribute(node);
    }
    fn visit_expr_call(&mut self, node: ast::ExprCall) {
        self.calls.push(match &*node.func {
            ast::Expr::Name(name) => (name.id.to_string(), None),
            ast::Expr::Attribute(value) => (value.attr.to_string(), Some(dotted(&value.value))),
            _ => (String::new(), None),
        });
        self.generic_visit_expr_call(node);
    }
    fn visit_stmt_return(&mut self, node: ast::StmtReturn) {
        self.returns |= node.value.is_some();
        self.generic_visit_stmt_return(node);
    }
    fn visit_expr_compare(&mut self, node: ast::ExprCompare) {
        if std::iter::once(&*node.left)
            .chain(node.comparators.iter())
            .any(|expr| {
                matches!(expr,
            ast::Expr::Constant(value) if value.value==ast::Constant::None)
            })
        {
            self.none_checks += 1;
        }
        self.generic_visit_expr_compare(node);
    }
}

#[derive(Default)]
struct Complexity {
    nesting: usize,
    value: usize,
}
macro_rules! branch_visitor {
    ($visit:ident,$generic:ident,$node:ty) => {
        fn $visit(&mut self, node: $node) {
            self.value += 1 + self.nesting;
            self.nesting += 1;
            self.$generic(node);
            self.nesting -= 1;
        }
    };
}
impl Visitor for Complexity {
    branch_visitor!(visit_stmt_if, generic_visit_stmt_if, ast::StmtIf);
    branch_visitor!(visit_stmt_for, generic_visit_stmt_for, ast::StmtFor);
    branch_visitor!(
        visit_stmt_async_for,
        generic_visit_stmt_async_for,
        ast::StmtAsyncFor
    );
    branch_visitor!(visit_stmt_while, generic_visit_stmt_while, ast::StmtWhile);
    branch_visitor!(visit_stmt_try, generic_visit_stmt_try, ast::StmtTry);
    branch_visitor!(visit_stmt_with, generic_visit_stmt_with, ast::StmtWith);
    branch_visitor!(
        visit_stmt_async_with,
        generic_visit_stmt_async_with,
        ast::StmtAsyncWith
    );
    branch_visitor!(visit_stmt_match, generic_visit_stmt_match, ast::StmtMatch);
    branch_visitor!(
        visit_expr_bool_op,
        generic_visit_expr_bool_op,
        ast::ExprBoolOp
    );
    branch_visitor!(visit_expr_if_exp, generic_visit_expr_if_exp, ast::ExprIfExp);
    branch_visitor!(
        visit_excepthandler_except_handler,
        generic_visit_excepthandler_except_handler,
        ast::ExceptHandlerExceptHandler
    );
}

fn optional(expr: &ast::Expr) -> bool {
    match expr {
        ast::Expr::Name(node) => ["Optional", "Any"].contains(&node.id.as_str()),
        ast::Expr::Attribute(node) => ["Optional", "Any"].contains(&node.attr.as_str()),
        ast::Expr::Subscript(node) => dotted(&node.value).rsplit('.').next() == Some("Optional"),
        ast::Expr::BinOp(node) if node.op == ast::Operator::BitOr => {
            optional(&node.left) || optional(&node.right)
        }
        ast::Expr::Constant(node) => node.value == ast::Constant::None,
        _ => false,
    }
}

struct Function<'a> {
    name: &'a str,
    args: &'a ast::Arguments,
    body: &'a [ast::Stmt],
    returns: Option<&'a ast::Expr>,
    decorators: &'a [ast::Expr],
    line: usize,
}
fn function<'a>(statement: &'a ast::Stmt, source: &str) -> Option<Function<'a>> {
    match statement {
        ast::Stmt::FunctionDef(node) => Some(Function {
            name: node.name.as_str(),
            args: &node.args,
            body: &node.body,
            returns: node.returns.as_deref(),
            decorators: &node.decorator_list,
            line: node_line(source, node),
        }),
        ast::Stmt::AsyncFunctionDef(node) => Some(Function {
            name: node.name.as_str(),
            args: &node.args,
            body: &node.body,
            returns: node.returns.as_deref(),
            decorators: &node.decorator_list,
            line: node_line(source, node),
        }),
        _ => None,
    }
}

fn body_without_doc(body: &[ast::Stmt]) -> &[ast::Stmt] {
    match body.first() {
        Some(ast::Stmt::Expr(node)) if matches!(&*node.value,ast::Expr::Constant(value) if matches!(&value.value,ast::Constant::Str(_))) => {
            &body[1..]
        }
        _ => body,
    }
}

struct Analyzer<'a> {
    path: &'a str,
    source: &'a str,
    thresholds: &'a Thresholds,
    usage: Option<&'a UsageIndex>,
    absolute: &'a str,
    findings: Vec<Finding>,
}
impl Analyzer<'_> {
    fn add(
        &mut self,
        line: usize,
        kind: &str,
        symbol: &str,
        evidence: Value,
        contract: Value,
        guidance: &str,
    ) {
        self.findings.push(Finding {
            path: self.path.into(),
            line,
            language: "python".into(),
            severity: if kind == "syntax_error" {
                "error"
            } else {
                "warn"
            }
            .into(),
            kind: kind.into(),
            symbol: symbol.into(),
            evidence,
            contract,
            guidance: guidance.into(),
        });
    }

    fn analyze_function(
        &mut self,
        function: Function<'_>,
        nested: bool,
        top_level: bool,
        algorithm_factory: bool,
        public_owner: bool,
    ) {
        let positional = function
            .args
            .posonlyargs
            .iter()
            .chain(&function.args.args)
            .collect::<Vec<_>>();
        let mut boundary = positional
            .iter()
            .map(|arg| &arg.def)
            .chain(function.args.kwonlyargs.iter().map(|arg| &arg.def))
            .collect::<Vec<_>>();
        if boundary
            .first()
            .is_some_and(|arg| ["self", "cls"].contains(&arg.arg.as_str()))
        {
            boundary.remove(0);
        }
        let parameters = boundary.len()
            + usize::from(function.args.vararg.is_some())
            + usize::from(function.args.kwarg.is_some());
        let names = boundary
            .iter()
            .map(|arg| arg.arg.to_string())
            .collect::<BTreeSet<_>>();
        let mut facts = Facts::default();
        for statement in function.body {
            facts.visit_stmt(statement.clone());
        }
        let mut complexity = Complexity::default();
        for statement in function.body {
            complexity.visit_stmt(statement.clone());
        }
        if BigInt::from(complexity.value) > self.thresholds.complexity {
            self.add(
                function.line,
                "cognitive_complexity",
                function.name,
                json!(complexity.value),
                integer_value(&self.thresholds.complexity),
                "review-branch-meaning-before-extraction",
            );
        }
        let public = public_owner && !nested && !function.name.starts_with('_');
        if !nested
            && function.name != "add_finding"
            && BigInt::from(parameters) > self.thresholds.parameters
        {
            self.add(
                function.line,
                "parameters",
                function.name,
                json!(parameters),
                integer_value(&self.thresholds.parameters),
                "review-stable-input-domain-shape",
            );
        }
        if public
            && (function.returns.is_none() || boundary.iter().any(|arg| arg.annotation.is_none()))
        {
            self.add(
                function.line,
                "missing_public_annotations",
                function.name,
                json!("missing"),
                json!("complete"),
                "add-public-boundary-types",
            );
        }
        let optional_count = boundary
            .iter()
            .filter(|arg| arg.annotation.as_deref().is_some_and(optional))
            .count();
        if public && optional_count > 0 {
            if function.name != "main" || !names.contains("argv") {
                self.add(
                    function.line,
                    "optional_boundary",
                    function.name,
                    json!(optional_count),
                    json!(0),
                    "split-input-variants-so-static-analysis-knows-the-shape",
                );
            }
            if facts.none_checks > 0 {
                self.add(
                    function.line,
                    "none_runtime_branch",
                    function.name,
                    json!(facts.none_checks),
                    json!("typed-variant-boundary"),
                    "replace-none-driven-runtime-branch-with-explicit-type-boundary",
                );
            }
        }
        let body = body_without_doc(function.body);
        if top_level && facts.returns {
            let effects = [
                "write",
                "writelines",
                "write_text",
                "write_bytes",
                "mkdir",
                "unlink",
                "rename",
                "open",
                "print",
                "run",
                "call",
                "check_call",
                "check_output",
            ];
            let mutations = [
                "append", "extend", "insert", "pop", "remove", "clear", "update", "add", "discard",
            ];
            let mut locals = facts.locals.clone();
            for name in &names {
                locals.remove(name);
            }
            let effect = facts.calls.iter().any(|(name, base)| {
                effects.contains(&name.as_str())
                    || (base.is_some()
                        && mutations.contains(&name.as_str())
                        && !base.as_ref().is_some_and(|base| locals.contains(base)))
            });
            let adapter = [
                "agent_canon_update_surface_status",
                "default_log_path",
                "is_git_worktree",
                "main",
                "project_root_from_script",
                "repo_root",
                "surface_manifest_paths",
                "utc_now",
            ]
            .contains(&function.name)
                || [
                    "append_", "build_", "emit_", "git_", "load_", "parse_", "read_", "resolve_",
                    "run_", "write_",
                ]
                .iter()
                .any(|prefix| function.name.starts_with(prefix));
            if effect && !adapter {
                self.add(
                    function.line,
                    "mixed_morphism_effect",
                    function.name,
                    json!("return+effect"),
                    json!("pure-or-effect-boundary"),
                    "separate-value-transform-from-io-or-mutation",
                );
            }
        }
        if top_level
            && ["helper", "util", "misc", "tmp"]
                .iter()
                .any(|part| function.name.to_lowercase().contains(part))
        {
            self.add(
                function.line,
                "module_helper_name",
                function.name,
                json!(function.name),
                json!("domain-responsibility-name-or-local-helper"),
                "inline-local-helper-or-rename-to-explicit-morphism",
            );
        }
        if !nested && body.len() == 1 {
            if let ast::Stmt::Return(statement) = &body[0] {
                if let Some(ast::Expr::Name(name)) = statement.value.as_deref() {
                    if names.contains(name.id.as_str()) {
                        self.add(
                            function.line,
                            "identity_function",
                            function.name,
                            json!(format!("returns {}", name.id)),
                            json!("non-identity-domain-transform"),
                            "remove-wrapper-or-document-domain-contract",
                        );
                    }
                }
                if let Some(ast::Expr::Call(call)) = statement.value.as_deref() {
                    let forwarded = call
                        .args
                        .iter()
                        .chain(call.keywords.iter().map(|keyword| &keyword.value))
                        .filter_map(|expr| match expr {
                            ast::Expr::Name(name) if names.contains(name.id.as_str()) => {
                                Some(name.id.to_string())
                            }
                            _ => None,
                        })
                        .collect::<Vec<_>>();
                    if !algorithm_factory
                        && !names.is_empty()
                        && forwarded.len() == names.len()
                        && forwarded.iter().cloned().collect::<BTreeSet<_>>() == names
                    {
                        let callee = match &*call.func {
                            ast::Expr::Name(name) => name.id.as_str(),
                            ast::Expr::Attribute(attribute) => attribute.attr.as_str(),
                            _ => "call",
                        };
                        self.add(
                            function.line,
                            "pass_through_function",
                            function.name,
                            json!(format!("{callee}/{}", forwarded.len())),
                            json!("adds-domain-or-adapter-contract"),
                            "inline-call-or-document-adapter-contract",
                        );
                    }
                }
                if let Some(value) = statement.value.as_deref() {
                    if [
                        "format",
                        "render",
                        "stringify",
                        "to_string",
                        "display",
                        "label",
                    ]
                    .iter()
                    .any(|part| function.name.to_lowercase().contains(part))
                    {
                        let label = match value {
                            ast::Expr::JoinedStr(_) => Some("f-string"),
                            ast::Expr::Call(call) => match &*call.func {
                                ast::Expr::Name(name)
                                    if ["str", "repr", "format"].contains(&name.id.as_str())
                                        && !call.args.is_empty() =>
                                {
                                    Some(name.id.as_str())
                                }
                                ast::Expr::Attribute(attribute)
                                    if attribute.attr.as_str() == "format" =>
                                {
                                    Some("str.format")
                                }
                                _ => None,
                            },
                            _ => None,
                        };
                        let mut used = Facts::default();
                        used.visit_expr(value.clone());
                        if let Some(label) = label.filter(|_| {
                            !used.names.is_empty()
                                && used.names.iter().all(|name| names.contains(name))
                        }) {
                            self.add(
                                function.line,
                                "trivial_format_function",
                                function.name,
                                json!(label),
                                json!("domain-presentation-contract"),
                                "inline-formatting-or-document-presentation-contract",
                            );
                        }
                    }
                }
            }
        }
    }

    fn analyze_class(&mut self, node: &ast::StmtClassDef) {
        let methods = node
            .body
            .iter()
            .filter_map(|statement| function(statement, self.source))
            .collect::<Vec<_>>();
        let bases = node.bases.iter().map(dotted).collect::<Vec<_>>();
        let visitor = bases
            .iter()
            .any(|name| ["NodeVisitor", "ast.NodeVisitor"].contains(&name.as_str()));
        let protocol = bases
            .iter()
            .any(|name| ["Protocol", "typing.Protocol"].contains(&name.as_str()));
        let algorithm = bases.iter().any(|name| {
            [
                "amp.InitializeConfig",
                "amp.SolveConfig",
                "amp.Problem",
                "amp.State",
                "amp.Answer",
                "amp.Info",
                "amp.Algorithm",
            ]
            .contains(&name.as_str())
        });
        let dataclass = node.decorator_list.iter().any(|decorator| match decorator {
            ast::Expr::Name(name) => name.id.as_str() == "dataclass",
            ast::Expr::Call(call) => dotted(&call.func).rsplit('.').next() == Some("dataclass"),
            _ => false,
        });
        let test = (self
            .path
            .rsplit('/')
            .next()
            .is_some_and(|name| name.starts_with("test_"))
            || self.path.split('/').any(|part| part == "tests"))
            && (node.name.ends_with("Test")
                || bases
                    .iter()
                    .any(|name| ["TestCase", "unittest.TestCase"].contains(&name.as_str())));
        let public = methods
            .iter()
            .filter(|method| {
                !method.name.starts_with('_') && !(visitor && method.name.starts_with("visit_"))
            })
            .collect::<Vec<_>>();
        let mut facts = Facts::default();
        for statement in &node.body {
            facts.visit_stmt(statement.clone());
        }
        for statement in &node.body {
            if let ast::Stmt::AnnAssign(value) = statement {
                if let ast::Expr::Name(name) = &*value.target {
                    facts.attrs.insert(name.id.to_string());
                }
            }
        }
        let line = node_line(self.source, node);
        if !test {
            if ["Manager", "Helper", "Util", "Thing"]
                .iter()
                .any(|suffix| node.name.ends_with(suffix))
            {
                self.add(
                    line,
                    "vague_class_name",
                    node.name.as_str(),
                    json!(node.name.as_str()),
                    json!("responsibility-name"),
                    "rename-public-boundary-to-domain-responsibility",
                );
            }
            for (kind, count, limit, guidance) in [
                (
                    "base_classes",
                    bases.len(),
                    &self.thresholds.base_classes,
                    "prefer-composition-over-wide-inheritance",
                ),
                (
                    "public_methods",
                    public.len(),
                    &self.thresholds.public_methods,
                    "review-caller-roles-before-refining-api",
                ),
                (
                    "instance_attributes",
                    facts.attrs.len(),
                    &self.thresholds.instance_attributes,
                    "review-stable-value-object-or-state-owner-boundary",
                ),
            ] {
                if BigInt::from(count) > *limit {
                    self.add(
                        line,
                        kind,
                        node.name.as_str(),
                        json!(count),
                        integer_value(limit),
                        guidance,
                    );
                }
            }
            let static_count = methods
                .iter()
                .filter(|method| {
                    method
                        .decorators
                        .iter()
                        .any(|value| dotted(value) == "staticmethod")
                })
                .count();
            if static_count > 0 && static_count == methods.len() && !algorithm {
                self.add(
                    line,
                    "static_method_namespace",
                    node.name.as_str(),
                    json!(static_count),
                    json!(0),
                    "replace-namespace-class-with-module-functions",
                );
            }
            if public.len() <= 1 && facts.attrs.is_empty() && !dataclass && !algorithm && !protocol
            {
                self.add(
                    line,
                    "thin_class",
                    node.name.as_str(),
                    json!(public.len()),
                    json!("state-or-contract"),
                    "confirm-class-is-needed-or-use-function-value-object",
                );
            }
            if methods.len() == 1
                && methods[0].name == "__call__"
                && facts.attrs.is_empty()
                && bases.is_empty()
            {
                self.add(
                    line,
                    "stateless_callable_class",
                    node.name.as_str(),
                    json!("__call__"),
                    json!("owned-state-or-contract"),
                    "replace-with-function-or-document-required-callable-contract",
                );
            }
            if !dataclass
                && !algorithm
                && !protocol
                && bases.is_empty()
                && ((methods.len() == 1 && methods[0].name == "__call__" && facts.attrs.is_empty())
                    || (public.len() <= 1 && facts.attrs.len() <= 1))
            {
                if let Some(usage) = self
                    .usage
                    .and_then(|index| index.get(self.absolute, node.name.as_str()))
                    .filter(|usage| {
                        usage.constructors > 0
                            && usage.annotations + usage.inheritance + usage.isinstance == 0
                    })
                {
                    self.add(
                        line,
                        "redundant_class_boundary",
                        node.name.as_str(),
                        json!(format!(
                            "construct={},type={},method={},attr={},files={}",
                            usage.constructors,
                            usage.annotations + usage.inheritance + usage.isinstance,
                            usage.methods,
                            usage.attrs,
                            usage.files.len()
                        )),
                        json!("type-boundary-or-owned-lifecycle"),
                        "replace-with-function-or-document-class-lifecycle-contract",
                    );
                }
            }
            if !protocol {
                for method in &public {
                    if let Some(first) = method
                        .args
                        .args
                        .first()
                        .filter(|arg| ["self", "cls"].contains(&arg.def.arg.as_str()))
                    {
                        let mut facts = Facts::default();
                        for statement in method.body {
                            facts.visit_stmt(statement.clone());
                        }
                        if !facts.names.contains(first.def.arg.as_str()) {
                            self.add(
                                method.line,
                                "method_without_self_use",
                                &format!("{}.{}", node.name, method.name),
                                json!("no-self-use"),
                                json!("uses-state-or-contract"),
                                "move-pure-operation-to-function-or-service",
                            );
                        }
                    }
                }
            }
        }
        for method in methods {
            let factory = algorithm;
            self.analyze_function(method, false, false, factory, !node.name.starts_with('_'));
        }
    }
}

pub(crate) fn analyze_with_usage<'a>(
    path: &'a str,
    source: &'a str,
    thresholds: &'a Thresholds,
    usage: Option<&'a UsageIndex>,
    absolute: &'a str,
) -> Vec<Finding> {
    let mut analyzer = Analyzer {
        path,
        source,
        thresholds,
        usage,
        absolute,
        findings: Vec::new(),
    };
    let tree = match ast::Suite::parse(source, path) {
        Ok(tree) => tree,
        Err(_) => {
            analyzer.add(
                1,
                "syntax_error",
                path.rsplit('/').next().unwrap_or(path),
                json!("syntax-error"),
                json!("parseable"),
                "fix-syntax-before-readability-analysis",
            );
            return analyzer.findings;
        }
    };
    for statement in &tree {
        if let Some(function) = function(statement, source) {
            analyzer.analyze_function(function, false, true, false, true);
        }
        if let ast::Stmt::ClassDef(node) = statement {
            analyzer.analyze_class(node);
        }
    }
    struct Nested {
        depth: usize,
        functions: Vec<ast::Stmt>,
        classes: Vec<ast::StmtClassDef>,
    }
    impl Visitor for Nested {
        fn visit_stmt_function_def(&mut self, node: ast::StmtFunctionDef) {
            if self.depth > 0 {
                self.functions.push(ast::Stmt::FunctionDef(node.clone()));
            }
            self.depth += 1;
            self.generic_visit_stmt_function_def(node);
            self.depth -= 1;
        }
        fn visit_stmt_async_function_def(&mut self, node: ast::StmtAsyncFunctionDef) {
            if self.depth > 0 {
                self.functions
                    .push(ast::Stmt::AsyncFunctionDef(node.clone()));
            }
            self.depth += 1;
            self.generic_visit_stmt_async_function_def(node);
            self.depth -= 1;
        }
        fn visit_stmt_class_def(&mut self, node: ast::StmtClassDef) {
            if self.depth > 0 {
                self.classes.push(node.clone());
            }
            let previous = self.depth;
            self.depth = 0;
            self.generic_visit_stmt_class_def(node);
            self.depth = previous;
        }
    }
    let mut nested = Nested {
        depth: 0,
        functions: Vec::new(),
        classes: Vec::new(),
    };
    for statement in &tree {
        nested.visit_stmt(statement.clone());
    }
    for statement in &nested.functions {
        if let Some(function) = function(statement, source) {
            analyzer.analyze_function(function, true, false, false, false);
        }
    }
    for class in &nested.classes {
        analyzer.analyze_class(class);
    }
    let helpers = analyzer
        .findings
        .iter()
        .filter(|finding| finding.kind == "module_helper_name")
        .count();
    if BigInt::from(helpers) > thresholds.module_helpers {
        analyzer.add(
            1,
            "module_helper_bucket",
            path.rsplit('/').next().unwrap_or(path),
            json!(helpers),
            integer_value(&thresholds.module_helpers),
            "review-helper-locality-or-existing-domain-service",
        );
    }
    analyzer.findings
}
