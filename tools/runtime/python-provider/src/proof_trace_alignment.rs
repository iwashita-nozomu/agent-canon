// @dependency-start
// contract implementation
// responsibility Checks retained proof claims and implementation anchors through existing CPython trace and AST APIs.
// upstream design ../../../../documents/tools/check_proof_trace_alignment.md proof trace contract
// downstream test ../../../../tests/agent_tools/test_check_proof_trace_alignment.py independent CLI oracles
// @dependency-end

use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyException, PySyntaxError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyInt, PyString};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

const CONTRACT_KEYS: &[&str] = &[
    "checked_fragment",
    "implementation_anchor",
    "implementation_anchors",
    "source_shape_anchor",
    "source_path",
    "source_symbol",
    "source_symbols",
];

#[derive(Eq, PartialEq, Ord, PartialOrd)]
struct Finding {
    contract: String,
    anchor: String,
    kind: String,
    detail: String,
}

impl Finding {
    fn new(contract: &str, anchor: &str, kind: &str, detail: impl Into<String>) -> Self {
        Self {
            contract: contract.into(),
            anchor: anchor.into(),
            kind: kind.into(),
            detail: detail.into(),
        }
    }
    fn value(&self) -> Value {
        json!({"contract":self.contract,"anchor":self.anchor,"kind":self.kind,"detail":self.detail})
    }
    fn text(&self) -> String {
        format!(
            "PROOF_TRACE_ALIGNMENT_FINDING={}:{}:{}:{}",
            self.contract, self.anchor, self.kind, self.detail
        )
    }
}

fn get<'py>(value: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    value.call_method1("get", (key,))
}

fn string(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_instance_of::<PyString>() {
        value.extract().map(Some)
    } else {
        Ok(None)
    }
}

fn field(value: &Bound<'_, PyAny>, key: &str) -> PyResult<Option<String>> {
    string(&get(value, key)?)
}

fn mapping<'py>(py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, PyAny>>> {
    if !value.is_instance(&py.import("collections.abc")?.getattr("Mapping")?)? {
        return Ok(None);
    }
    for key in value.call_method0("keys")?.try_iter()? {
        if !key?.is_instance_of::<PyString>() {
            return Ok(None);
        }
    }
    Ok(Some(value.clone()))
}

fn sequence<'py>(py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    if value.is_instance_of::<PyString>()
        || value.is_instance_of::<PyBytes>()
        || !value.is_instance(&py.import("collections.abc")?.getattr("Sequence")?)?
    {
        return Ok(Vec::new());
    }
    value.try_iter()?.collect()
}

fn strings(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    if let Some(value) = string(value)? {
        return Ok(vec![value]);
    }
    let mut values = Vec::new();
    for item in sequence(py, value)? {
        if let Some(value) = string(&item)? {
            values.push(value);
        }
    }
    Ok(values)
}

fn compact(py: Python<'_>, value: &str) -> PyResult<String> {
    Ok(PyString::new(py, value)
        .call_method0("split")?
        .extract::<Vec<String>>()?
        .join(" "))
}

fn copy_anchor<'py>(
    py: Python<'py>,
    contract: &Bound<'py, PyAny>,
    raw: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let anchor = py.import("builtins")?.getattr("dict")?.call1((raw,))?;
    for key in ["source_path", "source_symbol"] {
        if !anchor.contains(key)? {
            if let Some(value) = field(contract, key)? {
                anchor.set_item(key, value)?;
            }
        }
    }
    Ok(anchor)
}

fn anchors<'py>(py: Python<'py>, contract: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut result = Vec::new();
    for key in ["implementation_anchor", "source_shape_anchor"] {
        if let Some(value) = mapping(py, &get(contract, key)?)? {
            result.push(copy_anchor(py, contract, &value)?);
        }
    }
    for item in sequence(py, &get(contract, "implementation_anchors")?)? {
        if let Some(value) = mapping(py, &item)? {
            result.push(copy_anchor(py, contract, &value)?);
        }
    }
    if let Some(path) = field(contract, "source_path")? {
        let mut symbols = strings(py, &get(contract, "source_symbols")?)?;
        if let Some(symbol) = field(contract, "source_symbol")? {
            symbols.push(symbol);
        }
        if result.is_empty() && symbols.is_empty() {
            let value = PyDict::new(py);
            value.set_item("source_path", &path)?;
            result.push(value.into_any());
        }
        for symbol in symbols {
            let value = PyDict::new(py);
            value.set_item("source_path", &path)?;
            value.set_item("source_symbol", symbol)?;
            result.push(value.into_any());
        }
    }
    Ok(result)
}

fn find_symbol<'py>(
    py: Python<'py>,
    ast: &Bound<'py, PyAny>,
    module: &Bound<'py, PyAny>,
    qualname: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let mut body = sequence(py, &module.getattr("body")?)?;
    let mut selected = None;
    for part in qualname.split('.').filter(|part| !part.is_empty()) {
        selected = None;
        for node in &body {
            let mut definition = false;
            for kind in ["ClassDef", "FunctionDef", "AsyncFunctionDef"] {
                definition |= node.is_instance(&ast.getattr(kind)?)?;
            }
            if definition && node.getattr("name")?.extract::<String>()? == part {
                selected = Some(node.clone());
                break;
            }
        }
        let node = selected
            .as_ref()
            .ok_or_else(|| PyValueError::new_err(format!("AST symbol not found: {qualname}")))?;
        body = sequence(py, &node.getattr("body")?)?;
    }
    selected.ok_or_else(|| PyValueError::new_err("empty AST qualname"))
}

fn shape(
    py: Python<'_>,
    ast: &Bound<'_, PyAny>,
    node: &Bound<'_, PyAny>,
) -> PyResult<(BTreeSet<String>, usize, usize)> {
    let mut snippets = BTreeSet::new();
    let mut returns = 0;
    let mut branches = 0;
    for inner in ast.call_method1("walk", (node,))?.try_iter()? {
        let inner = inner?;
        if inner.is_instance(&ast.getattr("Return")?)? {
            returns += 1;
        }
        if inner.is_instance(&ast.getattr("If")?)? || inner.is_instance(&ast.getattr("Match")?)? {
            branches += 1;
        }
        let candidates = if inner.is_instance(&ast.getattr("Call")?)? {
            vec![inner.getattr("func")?, inner.clone()]
        } else if inner.is_instance(&ast.getattr("expr")?)?
            && !inner.is_instance(&ast.getattr("Constant")?)?
            && !inner.is_instance(&ast.getattr("Name")?)?
        {
            vec![inner]
        } else {
            Vec::new()
        };
        let mut current = Vec::new();
        for candidate in candidates {
            match ast.call_method1("unparse", (&candidate,)) {
                Ok(value) => current.push(compact(py, &value.extract::<String>()?)?),
                Err(error) if error.is_instance_of::<PyException>(py) => {
                    current.clear();
                    break;
                }
                Err(error) => return Err(error),
            }
        }
        snippets.extend(current);
    }
    Ok((snippets, returns, branches))
}

fn check_anchor(
    py: Python<'_>,
    ast: &Bound<'_, PyAny>,
    root: &Path,
    contract: &str,
    index: usize,
    anchor: &Bound<'_, PyAny>,
) -> PyResult<Vec<Finding>> {
    let id = field(anchor, "id")?.unwrap_or_else(|| format!("anchor-{index}"));
    let finding = |kind: &str, detail: String| Finding::new(contract, &id, kind, detail);
    let Some(path) = field(anchor, "source_path")? else {
        return Ok(vec![finding("missing-source-path", "-".into())]);
    };
    let source_file = root.join(&path);
    if !source_file.is_file() {
        return Ok(vec![finding("missing-source-file", path)]);
    }
    let source = std::fs::read_to_string(&source_file)
        .map_err(|error| PyValueError::new_err(error.to_string()))?
        .replace("\r\n", "\n")
        .replace('\r', "\n");
    let symbol = if anchor.contains("qualname")? {
        field(anchor, "qualname")?
    } else {
        field(anchor, "source_symbol")?
    };
    let mut segment = source.clone();
    let mut node = None;
    if let Some(symbol) = symbol {
        let parsed = ast
            .call_method1(
                "parse",
                (&source, source_file.to_string_lossy().replace('\\', "/")),
            )
            .and_then(|module| find_symbol(py, ast, &module, &symbol));
        match parsed {
            Ok(selected) => {
                let value = ast.call_method1("get_source_segment", (&source, &selected))?;
                if value.is_truthy()? {
                    segment = value.extract()?;
                }
                node = Some(selected);
            }
            Err(error)
                if error.is_instance_of::<PySyntaxError>(py)
                    || error.is_instance_of::<PyValueError>(py) =>
            {
                let message = error.value(py).str()?.extract::<String>()?;
                return Ok(vec![finding(
                    "missing-ast-symbol",
                    format!("{path}::{symbol}:{message}"),
                )]);
            }
            Err(error) => return Err(error),
        }
    }
    let (snippets, returns, branches) = match node.as_ref() {
        Some(node) => shape(py, ast, node)?,
        None => (BTreeSet::new(), 0, 0),
    };
    let mut findings = Vec::new();
    for token in strings(py, &get(anchor, "required_source_tokens")?)? {
        if !segment.contains(&token) && !snippets.contains(&compact(py, &token)?) {
            findings.push(finding("missing-required-source-token", token));
        }
    }
    for token in strings(py, &get(anchor, "forbidden_source_tokens")?)? {
        if segment.contains(&token) {
            findings.push(finding("forbidden-source-token-present", token));
        }
    }
    let patterns = strings(py, &get(anchor, "required_ast_patterns")?)?;
    let mut limits = Vec::new();
    for key in ["min_return_count", "min_branch_count", "max_branch_count"] {
        let value = get(anchor, key)?;
        limits.push(value.is_instance_of::<PyInt>().then_some(value));
    }
    if node.is_none() {
        if !patterns.is_empty() || limits.iter().any(Option::is_some) {
            findings.push(finding("missing-ast-symbol-for-ast-check", path));
        }
        return Ok(findings);
    }
    for pattern in patterns {
        if !snippets.contains(&compact(py, &pattern)?) {
            findings.push(finding("missing-required-ast-pattern", pattern));
        }
    }
    for ((limit, count), kind) in limits.iter().zip([returns, branches, branches]).zip([
        "return-count-below-minimum",
        "branch-count-below-minimum",
        "branch-count-above-maximum",
    ]) {
        if let Some(limit) = limit {
            let maximum = kind == "branch-count-above-maximum";
            if count
                .into_pyobject(py)?
                .rich_compare(
                    limit,
                    if maximum {
                        CompareOp::Gt
                    } else {
                        CompareOp::Lt
                    },
                )?
                .is_truthy()?
            {
                findings.push(finding(
                    kind,
                    format!(
                        "{count}{}{}",
                        if maximum { ">" } else { "<" },
                        limit.str()?.extract::<String>()?
                    ),
                ));
            }
        }
    }
    Ok(findings)
}

fn evaluate(
    py: Python<'_>,
    root: &Path,
    trace_path: &str,
    symbol: &str,
) -> PyResult<(Value, Vec<Finding>)> {
    let globals = py
        .import("runpy")?
        .call_method1("run_path", (trace_path,))?;
    let trace = get(&globals, symbol)?;
    let trace = mapping(py, &trace)?.ok_or_else(|| {
        PyValueError::new_err(format!("{trace_path} does not define mapping {symbol}"))
    })?;
    let mut fragments = BTreeSet::new();
    for item in sequence(py, &get(&trace, "checked_proof_fragments")?)? {
        if let Some(item) = mapping(py, &item)? {
            if let Some(name) = field(&item, "name")? {
                fragments.insert(name);
            }
        }
    }
    let ast = py.import("ast")?.into_any();
    let mut findings = Vec::new();
    let mut contracts = 0;
    let mut checked_anchors = 0;
    for item in trace.call_method0("items")?.try_iter()? {
        let item = item?;
        let key = item.get_item(0)?.extract::<String>()?;
        let value = item.get_item(1)?;
        let Some(contract) = mapping(py, &value)? else {
            continue;
        };
        let mut is_contract = false;
        for key in CONTRACT_KEYS {
            is_contract |= contract.contains(*key)?;
        }
        if !is_contract {
            continue;
        }
        contracts += 1;
        if let Some(fragment) = field(&contract, "checked_fragment")? {
            if !fragments.contains(&fragment) {
                findings.push(Finding::new(
                    &key,
                    "contract",
                    "checked-fragment-not-retained",
                    fragment,
                ));
            }
        }
        let anchors = anchors(py, &contract)?;
        let mut proposition = false;
        for field_name in ["claim", "checked_conclusion", "proof_boundary"] {
            if let Some(value) = field(&contract, field_name)? {
                proposition |= !compact(py, &value)?.is_empty();
            }
        }
        if !anchors.is_empty() && !proposition {
            findings.push(Finding::new(
                &key,
                "contract",
                "missing-proposition-text",
                "-",
            ));
        }
        for (index, anchor) in anchors.iter().enumerate() {
            checked_anchors += 1;
            findings.extend(check_anchor(py, &ast, root, &key, index + 1, anchor)?);
        }
    }
    findings.sort();
    let report = json!({"status":if findings.is_empty(){"pass"}else{"fail"},"trace_path":trace_path.replace('\\',"/"),"checked_contract_count":contracts,"checked_anchor_count":checked_anchors,"findings":findings.iter().map(Finding::value).collect::<Vec<_>>()});
    Ok((report, findings))
}

pub fn run(root: PathBuf, trace_path: &str, symbol: &str, format: &str) -> i32 {
    let result = Python::attach(|py| {
        let result = evaluate(py, &root, trace_path, symbol);
        py.import("sys")?.getattr("stdout")?.call_method0("flush")?;
        result
    });
    match result {
        Ok((report, findings)) => {
            if format == "json" {
                let encoded = Python::attach(|py| -> PyResult<String> {
                    let module = py.import("json")?;
                    let value = module.call_method1("loads", (report.to_string(),))?;
                    let options = PyDict::new(py);
                    options.set_item("sort_keys", true)?;
                    options.set_item("ensure_ascii", true)?;
                    options.set_item("indent", 2)?;
                    module
                        .call_method("dumps", (value,), Some(&options))?
                        .extract()
                });
                match encoded {
                    Ok(value) => println!("{value}"),
                    Err(error) => {
                        eprintln!("{error}");
                        return 1;
                    }
                }
            } else {
                println!("PROOF_TRACE_ALIGNMENT={}\nPROOF_TRACE_ALIGNMENT_CONTRACTS={}\nPROOF_TRACE_ALIGNMENT_ANCHORS={}\nPROOF_TRACE_ALIGNMENT_FINDINGS={}",report["status"].as_str().unwrap(),report["checked_contract_count"],report["checked_anchor_count"],findings.len());
                for finding in findings {
                    println!("{}", finding.text());
                }
            }
            i32::from(report["status"] != "pass")
        }
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}
