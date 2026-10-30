// @dependency-start
// contract implementation
// responsibility Shares Python source normalization, module naming, source spans, and CPython-compatible AST dumps.
// downstream implementation python_structure_hash.rs extracts native AST structural-hash evidence
// downstream implementation python_algorithm_contract.rs extracts native algorithm-module contracts
// downstream implementation python_helper_function_inventory.rs extracts normalized helper-function signatures
// @dependency-end

use rustpython_ast::{Expr, Ranged};
use rustpython_parser::ast;
use std::collections::BTreeMap;
use std::path::Path;

pub(crate) fn normalize_python_newlines(source: &str) -> String {
    source.replace("\r\n", "\n").replace('\r', "\n")
}

pub(crate) fn module_name(relative_path: &Path) -> String {
    let mut module_path = relative_path.to_path_buf();
    module_path.set_extension("");
    if module_path
        .file_name()
        .is_some_and(|name| name.to_string_lossy() == "__init__")
    {
        module_path.pop();
    }
    module_path
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join(".")
}

pub(crate) fn line_at_offset(source: &str, offset: usize) -> usize {
    source
        .as_bytes()
        .iter()
        .take(offset.min(source.len()))
        .filter(|byte| **byte == b'\n')
        .count()
        + 1
}

pub(crate) fn node_line(source: &str, node: &impl Ranged) -> usize {
    line_at_offset(source, node.start().to_usize())
}

pub(crate) fn ast_dump_expr(expr: &Expr) -> String {
    use ast::Expr as E;
    match expr {
        E::BoolOp(node) => ast_dump_node(
            "BoolOp",
            [
                ast_dump_node(&format!("{:?}", node.op), []),
                ast_dump_expr_list(&node.values),
            ],
        ),
        E::NamedExpr(node) => ast_dump_node(
            "NamedExpr",
            [ast_dump_expr(&node.target), ast_dump_expr(&node.value)],
        ),
        E::BinOp(node) => ast_dump_node(
            "BinOp",
            [
                ast_dump_expr(&node.left),
                ast_dump_node(&format!("{:?}", node.op), []),
                ast_dump_expr(&node.right),
            ],
        ),
        E::UnaryOp(node) => ast_dump_node(
            "UnaryOp",
            [
                ast_dump_node(&format!("{:?}", node.op), []),
                ast_dump_expr(&node.operand),
            ],
        ),
        E::Lambda(node) => ast_dump_node(
            "Lambda",
            [ast_dump_arguments(&node.args), ast_dump_expr(&node.body)],
        ),
        E::IfExp(node) => ast_dump_node(
            "IfExp",
            [
                ast_dump_expr(&node.test),
                ast_dump_expr(&node.body),
                ast_dump_expr(&node.orelse),
            ],
        ),
        E::Dict(node) => ast_dump_node(
            "Dict",
            [
                ast_dump_list(node.keys.iter().map(|key| {
                    key.as_ref()
                        .map(ast_dump_expr)
                        .unwrap_or_else(|| "None".into())
                })),
                ast_dump_expr_list(&node.values),
            ],
        ),
        E::Set(node) => ast_dump_node("Set", [ast_dump_expr_list(&node.elts)]),
        E::ListComp(node) => ast_dump_node(
            "ListComp",
            [
                ast_dump_expr(&node.elt),
                ast_dump_comprehensions(&node.generators),
            ],
        ),
        E::SetComp(node) => ast_dump_node(
            "SetComp",
            [
                ast_dump_expr(&node.elt),
                ast_dump_comprehensions(&node.generators),
            ],
        ),
        E::DictComp(node) => ast_dump_node(
            "DictComp",
            [
                ast_dump_expr(&node.key),
                ast_dump_expr(&node.value),
                ast_dump_comprehensions(&node.generators),
            ],
        ),
        E::GeneratorExp(node) => ast_dump_node(
            "GeneratorExp",
            [
                ast_dump_expr(&node.elt),
                ast_dump_comprehensions(&node.generators),
            ],
        ),
        E::Await(node) => ast_dump_node("Await", [ast_dump_expr(&node.value)]),
        E::Yield(node) => ast_dump_node(
            "Yield",
            [node
                .value
                .as_ref()
                .map(|value| ast_dump_expr(value))
                .unwrap_or_else(|| "None".into())],
        ),
        E::YieldFrom(node) => ast_dump_node("YieldFrom", [ast_dump_expr(&node.value)]),
        E::Compare(node) => ast_dump_node(
            "Compare",
            [
                ast_dump_expr(&node.left),
                ast_dump_list(
                    node.ops
                        .iter()
                        .map(|op| ast_dump_node(&format!("{op:?}"), [])),
                ),
                ast_dump_expr_list(&node.comparators),
            ],
        ),
        E::Call(node) => ast_dump_node(
            "Call",
            [
                ast_dump_expr(&node.func),
                ast_dump_expr_list(&node.args),
                ast_dump_list(node.keywords.iter().map(ast_dump_keyword)),
            ],
        ),
        E::FormattedValue(node) => ast_dump_node(
            "FormattedValue",
            [
                ast_dump_expr(&node.value),
                (node.conversion as i8).to_string(),
                node.format_spec
                    .as_ref()
                    .map(|spec| ast_dump_expr(spec))
                    .unwrap_or_else(|| "None".into()),
            ],
        ),
        E::JoinedStr(node) => ast_dump_node("JoinedStr", [ast_dump_expr_list(&node.values)]),
        E::Constant(node) => ast_dump_node(
            "Constant",
            [
                node.value.to_string(),
                node.kind
                    .as_ref()
                    .map(|kind| ast_dump_string(kind))
                    .unwrap_or_else(|| "None".into()),
            ],
        ),
        E::Attribute(node) => ast_dump_node(
            "Attribute",
            [
                ast_dump_expr(&node.value),
                ast_dump_string(node.attr.as_str()),
                ast_dump_context(&node.ctx),
            ],
        ),
        E::Subscript(node) => ast_dump_node(
            "Subscript",
            [
                ast_dump_expr(&node.value),
                ast_dump_expr(&node.slice),
                ast_dump_context(&node.ctx),
            ],
        ),
        E::Starred(node) => ast_dump_node(
            "Starred",
            [ast_dump_expr(&node.value), ast_dump_context(&node.ctx)],
        ),
        E::Name(node) => ast_dump_node(
            "Name",
            [
                ast_dump_string(node.id.as_str()),
                ast_dump_context(&node.ctx),
            ],
        ),
        E::List(node) => ast_dump_node(
            "List",
            [ast_dump_expr_list(&node.elts), ast_dump_context(&node.ctx)],
        ),
        E::Tuple(node) => ast_dump_node(
            "Tuple",
            [ast_dump_expr_list(&node.elts), ast_dump_context(&node.ctx)],
        ),
        E::Slice(node) => ast_dump_node(
            "Slice",
            [
                node.lower
                    .as_ref()
                    .map(|value| ast_dump_expr(value))
                    .unwrap_or_else(|| "None".into()),
                node.upper
                    .as_ref()
                    .map(|value| ast_dump_expr(value))
                    .unwrap_or_else(|| "None".into()),
                node.step
                    .as_ref()
                    .map(|value| ast_dump_expr(value))
                    .unwrap_or_else(|| "None".into()),
            ],
        ),
    }
}

/// Render a Python module body using the field-labelled form of `ast.dump`.
/// Names and argument declarations listed in `parameter_names` are rewritten
/// to their stable `argN` names before rendering.
pub(crate) fn ast_dump_normalized_module_body(
    body: &[ast::Stmt],
    parameter_names: &[String],
) -> String {
    let names = parameter_names
        .iter()
        .enumerate()
        .map(|(index, name)| (name.clone(), format!("arg{index}")))
        .collect::<BTreeMap<_, _>>();
    let body = ast_dump_list(body.iter().map(|statement| dump_stmt(statement, &names)));
    dump_node("Module", [("body", body), ("type_ignores", "[]".into())])
}

const OMIT_OPTIONAL_FIELD: &str = "\0";

fn dump_node(name: &str, fields: impl IntoIterator<Item = (&'static str, String)>) -> String {
    format!(
        "{name}({})",
        fields
            .into_iter()
            .filter(|(_, value)| value != OMIT_OPTIONAL_FIELD)
            .map(|(field, value)| format!("{field}={value}"))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn dump_list(values: impl IntoIterator<Item = String>) -> String {
    format!("[{}]", values.into_iter().collect::<Vec<_>>().join(", "))
}

fn dump_optional<T: ?Sized>(value: Option<&T>, render: impl FnOnce(&T) -> String) -> String {
    value
        .map(render)
        .unwrap_or_else(|| OMIT_OPTIONAL_FIELD.into())
}

fn dump_optional_value<T: ?Sized>(value: Option<&T>, render: impl FnOnce(&T) -> String) -> String {
    value.map(render).unwrap_or_else(|| "None".into())
}

fn dump_string(value: &str) -> String {
    ast::Constant::Str(value.to_string()).to_string()
}

fn dump_constant(value: &ast::Constant) -> String {
    if matches!(value, ast::Constant::Ellipsis) {
        "Ellipsis".into()
    } else {
        value.to_string()
    }
}

fn dump_expr(expr: &ast::Expr, names: &BTreeMap<String, String>) -> String {
    use ast::Expr as E;
    match expr {
        E::BoolOp(node) => dump_node(
            "BoolOp",
            [
                ("op", format!("{:?}()", node.op)),
                (
                    "values",
                    dump_list(node.values.iter().map(|value| dump_expr(value, names))),
                ),
            ],
        ),
        E::NamedExpr(node) => dump_node(
            "NamedExpr",
            [
                ("target", dump_expr(&node.target, names)),
                ("value", dump_expr(&node.value, names)),
            ],
        ),
        E::BinOp(node) => dump_node(
            "BinOp",
            [
                ("left", dump_expr(&node.left, names)),
                ("op", format!("{:?}()", node.op)),
                ("right", dump_expr(&node.right, names)),
            ],
        ),
        E::UnaryOp(node) => dump_node(
            "UnaryOp",
            [
                ("op", format!("{:?}()", node.op)),
                ("operand", dump_expr(&node.operand, names)),
            ],
        ),
        E::Lambda(node) => dump_node(
            "Lambda",
            [
                ("args", dump_arguments(&node.args, names)),
                ("body", dump_expr(&node.body, names)),
            ],
        ),
        E::IfExp(node) => dump_node(
            "IfExp",
            [
                ("test", dump_expr(&node.test, names)),
                ("body", dump_expr(&node.body, names)),
                ("orelse", dump_expr(&node.orelse, names)),
            ],
        ),
        E::Dict(node) => dump_node(
            "Dict",
            [
                (
                    "keys",
                    dump_list(node.keys.iter().map(|key| {
                        key.as_ref()
                            .map(|value| dump_expr(value, names))
                            .unwrap_or_else(|| "None".into())
                    })),
                ),
                (
                    "values",
                    dump_list(node.values.iter().map(|value| dump_expr(value, names))),
                ),
            ],
        ),
        E::Set(node) => dump_node(
            "Set",
            [(
                "elts",
                dump_list(node.elts.iter().map(|value| dump_expr(value, names))),
            )],
        ),
        E::ListComp(node) => dump_node(
            "ListComp",
            [
                ("elt", dump_expr(&node.elt, names)),
                (
                    "generators",
                    dump_list(
                        node.generators
                            .iter()
                            .map(|value| dump_comprehension(value, names)),
                    ),
                ),
            ],
        ),
        E::SetComp(node) => dump_node(
            "SetComp",
            [
                ("elt", dump_expr(&node.elt, names)),
                (
                    "generators",
                    dump_list(
                        node.generators
                            .iter()
                            .map(|value| dump_comprehension(value, names)),
                    ),
                ),
            ],
        ),
        E::DictComp(node) => dump_node(
            "DictComp",
            [
                ("key", dump_expr(&node.key, names)),
                ("value", dump_expr(&node.value, names)),
                (
                    "generators",
                    dump_list(
                        node.generators
                            .iter()
                            .map(|value| dump_comprehension(value, names)),
                    ),
                ),
            ],
        ),
        E::GeneratorExp(node) => dump_node(
            "GeneratorExp",
            [
                ("elt", dump_expr(&node.elt, names)),
                (
                    "generators",
                    dump_list(
                        node.generators
                            .iter()
                            .map(|value| dump_comprehension(value, names)),
                    ),
                ),
            ],
        ),
        E::Await(node) => dump_node("Await", [("value", dump_expr(&node.value, names))]),
        E::Yield(node) => dump_node(
            "Yield",
            [(
                "value",
                dump_optional(node.value.as_deref(), |value| dump_expr(value, names)),
            )],
        ),
        E::YieldFrom(node) => dump_node("YieldFrom", [("value", dump_expr(&node.value, names))]),
        E::Compare(node) => dump_node(
            "Compare",
            [
                ("left", dump_expr(&node.left, names)),
                (
                    "ops",
                    dump_list(node.ops.iter().map(|operator| format!("{operator:?}()"))),
                ),
                (
                    "comparators",
                    dump_list(node.comparators.iter().map(|value| dump_expr(value, names))),
                ),
            ],
        ),
        E::Call(node) => dump_node(
            "Call",
            [
                ("func", dump_expr(&node.func, names)),
                (
                    "args",
                    dump_list(node.args.iter().map(|value| dump_expr(value, names))),
                ),
                (
                    "keywords",
                    dump_list(node.keywords.iter().map(|value| dump_keyword(value, names))),
                ),
            ],
        ),
        E::FormattedValue(node) => dump_node(
            "FormattedValue",
            [
                ("value", dump_expr(&node.value, names)),
                ("conversion", (node.conversion as i8).to_string()),
                (
                    "format_spec",
                    dump_optional(node.format_spec.as_deref(), |value| dump_expr(value, names)),
                ),
            ],
        ),
        E::JoinedStr(node) => dump_node(
            "JoinedStr",
            [(
                "values",
                dump_list(node.values.iter().map(|value| dump_expr(value, names))),
            )],
        ),
        E::Constant(node) => dump_node(
            "Constant",
            [
                ("value", dump_constant(&node.value)),
                (
                    "kind",
                    dump_optional(node.kind.as_ref(), |value| dump_string(value)),
                ),
            ],
        ),
        E::Attribute(node) => dump_node(
            "Attribute",
            [
                ("value", dump_expr(&node.value, names)),
                ("attr", dump_string(node.attr.as_str())),
                ("ctx", format!("{:?}()", node.ctx)),
            ],
        ),
        E::Subscript(node) => dump_node(
            "Subscript",
            [
                ("value", dump_expr(&node.value, names)),
                ("slice", dump_expr(&node.slice, names)),
                ("ctx", format!("{:?}()", node.ctx)),
            ],
        ),
        E::Starred(node) => dump_node(
            "Starred",
            [
                ("value", dump_expr(&node.value, names)),
                ("ctx", format!("{:?}()", node.ctx)),
            ],
        ),
        E::Name(node) => dump_node(
            "Name",
            [
                (
                    "id",
                    dump_string(
                        names
                            .get(node.id.as_str())
                            .map(String::as_str)
                            .unwrap_or(node.id.as_str()),
                    ),
                ),
                ("ctx", format!("{:?}()", node.ctx)),
            ],
        ),
        E::List(node) => dump_node(
            "List",
            [
                (
                    "elts",
                    dump_list(node.elts.iter().map(|value| dump_expr(value, names))),
                ),
                ("ctx", format!("{:?}()", node.ctx)),
            ],
        ),
        E::Tuple(node) => dump_node(
            "Tuple",
            [
                (
                    "elts",
                    dump_list(node.elts.iter().map(|value| dump_expr(value, names))),
                ),
                ("ctx", format!("{:?}()", node.ctx)),
            ],
        ),
        E::Slice(node) => dump_node(
            "Slice",
            [
                (
                    "lower",
                    dump_optional(node.lower.as_deref(), |value| dump_expr(value, names)),
                ),
                (
                    "upper",
                    dump_optional(node.upper.as_deref(), |value| dump_expr(value, names)),
                ),
                (
                    "step",
                    dump_optional(node.step.as_deref(), |value| dump_expr(value, names)),
                ),
            ],
        ),
    }
}

fn dump_comprehension(node: &ast::Comprehension, names: &BTreeMap<String, String>) -> String {
    dump_node(
        "comprehension",
        [
            ("target", dump_expr(&node.target, names)),
            ("iter", dump_expr(&node.iter, names)),
            (
                "ifs",
                dump_list(node.ifs.iter().map(|value| dump_expr(value, names))),
            ),
            ("is_async", u8::from(node.is_async).to_string()),
        ],
    )
}

fn dump_keyword(node: &ast::Keyword, names: &BTreeMap<String, String>) -> String {
    dump_node(
        "keyword",
        [
            (
                "arg",
                dump_optional(node.arg.as_ref(), |value| dump_string(value.as_str())),
            ),
            ("value", dump_expr(&node.value, names)),
        ],
    )
}

fn dump_arg(node: &ast::Arg, names: &BTreeMap<String, String>) -> String {
    dump_node(
        "arg",
        [
            (
                "arg",
                dump_string(
                    names
                        .get(node.arg.as_str())
                        .map(String::as_str)
                        .unwrap_or(node.arg.as_str()),
                ),
            ),
            (
                "annotation",
                dump_optional(node.annotation.as_deref(), |value| dump_expr(value, names)),
            ),
            (
                "type_comment",
                dump_optional(node.type_comment.as_ref(), |value| dump_string(value)),
            ),
        ],
    )
}

fn dump_arguments(node: &ast::Arguments, names: &BTreeMap<String, String>) -> String {
    let positional_defaults = node
        .posonlyargs
        .iter()
        .chain(&node.args)
        .filter_map(|argument| {
            argument
                .default
                .as_deref()
                .map(|value| dump_expr(value, names))
        })
        .collect::<Vec<_>>();
    dump_node(
        "arguments",
        [
            (
                "posonlyargs",
                dump_list(
                    node.posonlyargs
                        .iter()
                        .map(|argument| dump_arg(&argument.def, names)),
                ),
            ),
            (
                "args",
                dump_list(
                    node.args
                        .iter()
                        .map(|argument| dump_arg(&argument.def, names)),
                ),
            ),
            (
                "vararg",
                dump_optional(node.vararg.as_deref(), |value| dump_arg(value, names)),
            ),
            (
                "kwonlyargs",
                dump_list(
                    node.kwonlyargs
                        .iter()
                        .map(|argument| dump_arg(&argument.def, names)),
                ),
            ),
            (
                "kw_defaults",
                dump_list(node.kwonlyargs.iter().map(|argument| {
                    dump_optional_value(argument.default.as_deref(), |value| {
                        dump_expr(value, names)
                    })
                })),
            ),
            (
                "kwarg",
                dump_optional(node.kwarg.as_deref(), |value| dump_arg(value, names)),
            ),
            ("defaults", dump_list(positional_defaults)),
        ],
    )
}

fn dump_type_param(node: &ast::TypeParam, names: &BTreeMap<String, String>) -> String {
    match node {
        ast::TypeParam::TypeVar(value) => dump_node(
            "TypeVar",
            [
                ("name", dump_string(value.name.as_str())),
                (
                    "bound",
                    dump_optional(value.bound.as_deref(), |bound| dump_expr(bound, names)),
                ),
            ],
        ),
        ast::TypeParam::ParamSpec(value) => {
            dump_node("ParamSpec", [("name", dump_string(value.name.as_str()))])
        }
        ast::TypeParam::TypeVarTuple(value) => {
            dump_node("TypeVarTuple", [("name", dump_string(value.name.as_str()))])
        }
    }
}

fn dump_alias(node: &ast::Alias) -> String {
    dump_node(
        "alias",
        [
            ("name", dump_string(node.name.as_str())),
            (
                "asname",
                dump_optional(node.asname.as_ref(), |value| dump_string(value.as_str())),
            ),
        ],
    )
}

fn dump_with_item(node: &ast::WithItem, names: &BTreeMap<String, String>) -> String {
    dump_node(
        "withitem",
        [
            ("context_expr", dump_expr(&node.context_expr, names)),
            (
                "optional_vars",
                dump_optional(node.optional_vars.as_deref(), |value| {
                    dump_expr(value, names)
                }),
            ),
        ],
    )
}

fn dump_except_handler(node: &ast::ExceptHandler, names: &BTreeMap<String, String>) -> String {
    match node {
        ast::ExceptHandler::ExceptHandler(value) => dump_node(
            "ExceptHandler",
            [
                (
                    "type",
                    dump_optional(value.type_.as_deref(), |value| dump_expr(value, names)),
                ),
                (
                    "name",
                    dump_optional(value.name.as_ref(), |value| dump_string(value.as_str())),
                ),
                (
                    "body",
                    dump_list(
                        value
                            .body
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
            ],
        ),
    }
}

fn dump_match_case(node: &ast::MatchCase, names: &BTreeMap<String, String>) -> String {
    dump_node(
        "match_case",
        [
            ("pattern", dump_pattern(&node.pattern, names)),
            (
                "guard",
                dump_optional(node.guard.as_deref(), |value| dump_expr(value, names)),
            ),
            (
                "body",
                dump_list(
                    node.body
                        .iter()
                        .map(|statement| dump_stmt(statement, names)),
                ),
            ),
        ],
    )
}

fn dump_pattern(node: &ast::Pattern, names: &BTreeMap<String, String>) -> String {
    use ast::Pattern as P;
    match node {
        P::MatchValue(value) => {
            dump_node("MatchValue", [("value", dump_expr(&value.value, names))])
        }
        P::MatchSingleton(value) => {
            dump_node("MatchSingleton", [("value", dump_constant(&value.value))])
        }
        P::MatchSequence(value) => dump_node(
            "MatchSequence",
            [(
                "patterns",
                dump_list(
                    value
                        .patterns
                        .iter()
                        .map(|pattern| dump_pattern(pattern, names)),
                ),
            )],
        ),
        P::MatchMapping(value) => dump_node(
            "MatchMapping",
            [
                (
                    "keys",
                    dump_list(value.keys.iter().map(|expr| dump_expr(expr, names))),
                ),
                (
                    "patterns",
                    dump_list(
                        value
                            .patterns
                            .iter()
                            .map(|pattern| dump_pattern(pattern, names)),
                    ),
                ),
                (
                    "rest",
                    dump_optional(value.rest.as_ref(), |name| dump_string(name.as_str())),
                ),
            ],
        ),
        P::MatchClass(value) => dump_node(
            "MatchClass",
            [
                ("cls", dump_expr(&value.cls, names)),
                (
                    "patterns",
                    dump_list(
                        value
                            .patterns
                            .iter()
                            .map(|pattern| dump_pattern(pattern, names)),
                    ),
                ),
                (
                    "kwd_attrs",
                    dump_list(
                        value
                            .kwd_attrs
                            .iter()
                            .map(|name| dump_string(name.as_str())),
                    ),
                ),
                (
                    "kwd_patterns",
                    dump_list(
                        value
                            .kwd_patterns
                            .iter()
                            .map(|pattern| dump_pattern(pattern, names)),
                    ),
                ),
            ],
        ),
        P::MatchStar(value) => dump_node(
            "MatchStar",
            [(
                "name",
                dump_optional(value.name.as_ref(), |name| dump_string(name.as_str())),
            )],
        ),
        P::MatchAs(value) => dump_node(
            "MatchAs",
            [
                (
                    "pattern",
                    dump_optional(value.pattern.as_deref(), |pattern| {
                        dump_pattern(pattern, names)
                    }),
                ),
                (
                    "name",
                    dump_optional(value.name.as_ref(), |name| dump_string(name.as_str())),
                ),
            ],
        ),
        P::MatchOr(value) => dump_node(
            "MatchOr",
            [(
                "patterns",
                dump_list(
                    value
                        .patterns
                        .iter()
                        .map(|pattern| dump_pattern(pattern, names)),
                ),
            )],
        ),
    }
}

fn dump_for(
    node_name: &str,
    target: &ast::Expr,
    iter: &ast::Expr,
    body: &[ast::Stmt],
    orelse: &[ast::Stmt],
    type_comment: Option<&str>,
    names: &BTreeMap<String, String>,
) -> String {
    dump_node(
        node_name,
        [
            ("target", dump_expr(target, names)),
            ("iter", dump_expr(iter, names)),
            (
                "body",
                dump_list(body.iter().map(|statement| dump_stmt(statement, names))),
            ),
            (
                "orelse",
                dump_list(orelse.iter().map(|statement| dump_stmt(statement, names))),
            ),
            ("type_comment", dump_optional(type_comment, dump_string)),
        ],
    )
}

fn dump_with(
    node_name: &str,
    items: &[ast::WithItem],
    body: &[ast::Stmt],
    type_comment: Option<&str>,
    names: &BTreeMap<String, String>,
) -> String {
    dump_node(
        node_name,
        [
            (
                "items",
                dump_list(items.iter().map(|item| dump_with_item(item, names))),
            ),
            (
                "body",
                dump_list(body.iter().map(|statement| dump_stmt(statement, names))),
            ),
            ("type_comment", dump_optional(type_comment, dump_string)),
        ],
    )
}

fn dump_try(
    node_name: &str,
    body: &[ast::Stmt],
    handlers: &[ast::ExceptHandler],
    orelse: &[ast::Stmt],
    finalbody: &[ast::Stmt],
    names: &BTreeMap<String, String>,
) -> String {
    dump_node(
        node_name,
        [
            (
                "body",
                dump_list(body.iter().map(|statement| dump_stmt(statement, names))),
            ),
            (
                "handlers",
                dump_list(
                    handlers
                        .iter()
                        .map(|handler| dump_except_handler(handler, names)),
                ),
            ),
            (
                "orelse",
                dump_list(orelse.iter().map(|statement| dump_stmt(statement, names))),
            ),
            (
                "finalbody",
                dump_list(
                    finalbody
                        .iter()
                        .map(|statement| dump_stmt(statement, names)),
                ),
            ),
        ],
    )
}

fn dump_stmt(statement: &ast::Stmt, names: &BTreeMap<String, String>) -> String {
    use ast::Stmt as S;
    match statement {
        S::FunctionDef(node) => dump_node(
            "FunctionDef",
            [
                ("name", dump_string(node.name.as_str())),
                ("args", dump_arguments(&node.args, names)),
                (
                    "body",
                    dump_list(
                        node.body
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
                (
                    "decorator_list",
                    dump_list(
                        node.decorator_list
                            .iter()
                            .map(|expr| dump_expr(expr, names)),
                    ),
                ),
                (
                    "returns",
                    dump_optional(node.returns.as_deref(), |expr| dump_expr(expr, names)),
                ),
                (
                    "type_comment",
                    dump_optional(node.type_comment.as_ref(), |text| dump_string(text)),
                ),
                (
                    "type_params",
                    dump_list(
                        node.type_params
                            .iter()
                            .map(|param| dump_type_param(param, names)),
                    ),
                ),
            ],
        ),
        S::AsyncFunctionDef(node) => dump_node(
            "AsyncFunctionDef",
            [
                ("name", dump_string(node.name.as_str())),
                ("args", dump_arguments(&node.args, names)),
                (
                    "body",
                    dump_list(
                        node.body
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
                (
                    "decorator_list",
                    dump_list(
                        node.decorator_list
                            .iter()
                            .map(|expr| dump_expr(expr, names)),
                    ),
                ),
                (
                    "returns",
                    dump_optional(node.returns.as_deref(), |expr| dump_expr(expr, names)),
                ),
                (
                    "type_comment",
                    dump_optional(node.type_comment.as_ref(), |text| dump_string(text)),
                ),
                (
                    "type_params",
                    dump_list(
                        node.type_params
                            .iter()
                            .map(|param| dump_type_param(param, names)),
                    ),
                ),
            ],
        ),
        S::ClassDef(node) => dump_node(
            "ClassDef",
            [
                ("name", dump_string(node.name.as_str())),
                (
                    "bases",
                    dump_list(node.bases.iter().map(|expr| dump_expr(expr, names))),
                ),
                (
                    "keywords",
                    dump_list(
                        node.keywords
                            .iter()
                            .map(|keyword| dump_keyword(keyword, names)),
                    ),
                ),
                (
                    "body",
                    dump_list(
                        node.body
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
                (
                    "decorator_list",
                    dump_list(
                        node.decorator_list
                            .iter()
                            .map(|expr| dump_expr(expr, names)),
                    ),
                ),
                (
                    "type_params",
                    dump_list(
                        node.type_params
                            .iter()
                            .map(|param| dump_type_param(param, names)),
                    ),
                ),
            ],
        ),
        S::Return(node) => dump_node(
            "Return",
            [(
                "value",
                dump_optional(node.value.as_deref(), |expr| dump_expr(expr, names)),
            )],
        ),
        S::Delete(node) => dump_node(
            "Delete",
            [(
                "targets",
                dump_list(node.targets.iter().map(|expr| dump_expr(expr, names))),
            )],
        ),
        S::Assign(node) => dump_node(
            "Assign",
            [
                (
                    "targets",
                    dump_list(node.targets.iter().map(|expr| dump_expr(expr, names))),
                ),
                ("value", dump_expr(&node.value, names)),
                (
                    "type_comment",
                    dump_optional(node.type_comment.as_ref(), |text| dump_string(text)),
                ),
            ],
        ),
        S::TypeAlias(node) => dump_node(
            "TypeAlias",
            [
                ("name", dump_expr(&node.name, names)),
                (
                    "type_params",
                    dump_list(
                        node.type_params
                            .iter()
                            .map(|param| dump_type_param(param, names)),
                    ),
                ),
                ("value", dump_expr(&node.value, names)),
            ],
        ),
        S::AugAssign(node) => dump_node(
            "AugAssign",
            [
                ("target", dump_expr(&node.target, names)),
                ("op", format!("{:?}()", node.op)),
                ("value", dump_expr(&node.value, names)),
            ],
        ),
        S::AnnAssign(node) => dump_node(
            "AnnAssign",
            [
                ("target", dump_expr(&node.target, names)),
                ("annotation", dump_expr(&node.annotation, names)),
                (
                    "value",
                    dump_optional(node.value.as_deref(), |expr| dump_expr(expr, names)),
                ),
                ("simple", if node.simple { "1" } else { "0" }.into()),
            ],
        ),
        S::For(node) => dump_for(
            "For",
            &node.target,
            &node.iter,
            &node.body,
            &node.orelse,
            node.type_comment.as_deref(),
            names,
        ),
        S::AsyncFor(node) => dump_for(
            "AsyncFor",
            &node.target,
            &node.iter,
            &node.body,
            &node.orelse,
            node.type_comment.as_deref(),
            names,
        ),
        S::While(node) => dump_node(
            "While",
            [
                ("test", dump_expr(&node.test, names)),
                (
                    "body",
                    dump_list(
                        node.body
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
                (
                    "orelse",
                    dump_list(
                        node.orelse
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
            ],
        ),
        S::If(node) => dump_node(
            "If",
            [
                ("test", dump_expr(&node.test, names)),
                (
                    "body",
                    dump_list(
                        node.body
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
                (
                    "orelse",
                    dump_list(
                        node.orelse
                            .iter()
                            .map(|statement| dump_stmt(statement, names)),
                    ),
                ),
            ],
        ),
        S::With(node) => dump_with(
            "With",
            &node.items,
            &node.body,
            node.type_comment.as_deref(),
            names,
        ),
        S::AsyncWith(node) => dump_with(
            "AsyncWith",
            &node.items,
            &node.body,
            node.type_comment.as_deref(),
            names,
        ),
        S::Match(node) => dump_node(
            "Match",
            [
                ("subject", dump_expr(&node.subject, names)),
                (
                    "cases",
                    dump_list(node.cases.iter().map(|case| dump_match_case(case, names))),
                ),
            ],
        ),
        S::Raise(node) => dump_node(
            "Raise",
            [
                (
                    "exc",
                    dump_optional(node.exc.as_deref(), |expr| dump_expr(expr, names)),
                ),
                (
                    "cause",
                    dump_optional(node.cause.as_deref(), |expr| dump_expr(expr, names)),
                ),
            ],
        ),
        S::Try(node) => dump_try(
            "Try",
            &node.body,
            &node.handlers,
            &node.orelse,
            &node.finalbody,
            names,
        ),
        S::TryStar(node) => dump_try(
            "TryStar",
            &node.body,
            &node.handlers,
            &node.orelse,
            &node.finalbody,
            names,
        ),
        S::Assert(node) => dump_node(
            "Assert",
            [
                ("test", dump_expr(&node.test, names)),
                (
                    "msg",
                    dump_optional(node.msg.as_deref(), |expr| dump_expr(expr, names)),
                ),
            ],
        ),
        S::Import(node) => dump_node(
            "Import",
            [("names", dump_list(node.names.iter().map(dump_alias)))],
        ),
        S::ImportFrom(node) => dump_node(
            "ImportFrom",
            [
                (
                    "module",
                    dump_optional(node.module.as_ref(), |module| dump_string(module.as_str())),
                ),
                ("names", dump_list(node.names.iter().map(dump_alias))),
                (
                    "level",
                    node.level
                        .as_ref()
                        .map(|level| level.to_usize().to_string())
                        .unwrap_or_else(|| "0".into()),
                ),
            ],
        ),
        S::Global(node) => dump_node(
            "Global",
            [(
                "names",
                dump_list(node.names.iter().map(|name| dump_string(name.as_str()))),
            )],
        ),
        S::Nonlocal(node) => dump_node(
            "Nonlocal",
            [(
                "names",
                dump_list(node.names.iter().map(|name| dump_string(name.as_str()))),
            )],
        ),
        S::Expr(node) => dump_node("Expr", [("value", dump_expr(&node.value, names))]),
        S::Pass(_) => "Pass()".into(),
        S::Break(_) => "Break()".into(),
        S::Continue(_) => "Continue()".into(),
    }
}

fn ast_dump_node<const N: usize>(name: &str, fields: [String; N]) -> String {
    format!("{name}({})", fields.join(", "))
}

fn ast_dump_list(values: impl IntoIterator<Item = String>) -> String {
    format!("[{}]", values.into_iter().collect::<Vec<_>>().join(", "))
}

fn ast_dump_expr_list(values: &[Expr]) -> String {
    ast_dump_list(values.iter().map(ast_dump_expr))
}

fn ast_dump_string(value: &str) -> String {
    ast::Constant::Str(value.to_string()).to_string()
}

fn ast_dump_context(context: &ast::ExprContext) -> String {
    ast_dump_node(&format!("{context:?}"), [])
}

fn ast_dump_keyword(keyword: &ast::Keyword) -> String {
    ast_dump_node(
        "keyword",
        [
            keyword
                .arg
                .as_ref()
                .map(|name| ast_dump_string(name.as_str()))
                .unwrap_or_else(|| "None".into()),
            ast_dump_expr(&keyword.value),
        ],
    )
}

fn ast_dump_comprehensions(values: &[ast::Comprehension]) -> String {
    ast_dump_list(values.iter().map(|value| {
        ast_dump_node(
            "comprehension",
            [
                ast_dump_expr(&value.target),
                ast_dump_expr(&value.iter),
                ast_dump_expr_list(&value.ifs),
                u8::from(value.is_async).to_string(),
            ],
        )
    }))
}

fn ast_dump_arg(argument: &ast::Arg) -> String {
    ast_dump_node(
        "arg",
        [
            ast_dump_string(argument.arg.as_str()),
            argument
                .annotation
                .as_ref()
                .map(|annotation| ast_dump_expr(annotation))
                .unwrap_or_else(|| "None".into()),
            argument
                .type_comment
                .as_ref()
                .map(|comment| ast_dump_string(comment))
                .unwrap_or_else(|| "None".into()),
        ],
    )
}

fn ast_dump_arguments(arguments: &ast::Arguments) -> String {
    ast_dump_node(
        "arguments",
        [
            ast_dump_list(
                arguments
                    .posonlyargs
                    .iter()
                    .map(|argument| ast_dump_arg(&argument.def)),
            ),
            ast_dump_list(
                arguments
                    .args
                    .iter()
                    .map(|argument| ast_dump_arg(&argument.def)),
            ),
            arguments
                .vararg
                .as_ref()
                .map(|argument| ast_dump_arg(argument))
                .unwrap_or_else(|| "None".into()),
            ast_dump_list(
                arguments
                    .kwonlyargs
                    .iter()
                    .map(|argument| ast_dump_arg(&argument.def)),
            ),
            ast_dump_list(arguments.kwonlyargs.iter().map(|argument| {
                argument
                    .default
                    .as_deref()
                    .map(ast_dump_expr)
                    .unwrap_or_else(|| "None".into())
            })),
            arguments
                .kwarg
                .as_ref()
                .map(|argument| ast_dump_arg(argument))
                .unwrap_or_else(|| "None".into()),
            ast_dump_list(
                arguments
                    .posonlyargs
                    .iter()
                    .chain(&arguments.args)
                    .filter_map(|argument| argument.default.as_deref().map(ast_dump_expr)),
            ),
        ],
    )
}
