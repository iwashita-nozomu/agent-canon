// @dependency-start
// contract implementation
// responsibility Shares Python source normalization, module naming, source spans, and CPython-style expression dumps.
// downstream implementation python_structure_hash.rs extracts native AST structural-hash evidence
// downstream implementation python_algorithm_contract.rs extracts native algorithm-module contracts
// @dependency-end

use rustpython_ast::{Expr, Ranged};
use rustpython_parser::ast;
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
