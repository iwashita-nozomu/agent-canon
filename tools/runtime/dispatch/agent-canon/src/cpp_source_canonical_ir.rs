// @dependency-start
// contract implementation
// responsibility Extracts source-only C++ facts and reachable call/control-flow records into thin operational IR.
// upstream design ../../../../../documents/tools/cpp_source_canonical_ir.md defines the source envelope
// downstream implementation operational_ir_to_lean.rs renders complete records as Lean evidence
// downstream implementation cpp_template_to_lean.rs owns the canonical C++ source-to-Lean route
// downstream implementation main.rs exposes cpp-source-canonical-ir
// downstream test ../../../../../tests/agent_tools/test_cpp_source_canonical_ir.py preserves source IR oracles
// @dependency-end

//! Native source-only C++ canonical IR extraction.

use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use regex::Regex;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "cpp-source-canonical-ir";
const USAGE: &str = "usage: agent-canon cpp-source-canonical-ir --root ROOT --cpp-symbol PATH::QUALNAME [--format {json,markdown,text}] [--out OUT]";
const CONTROL_CALLS: &[&str] = &["if", "for", "while", "switch", "catch", "return", "sizeof"];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Opt {
    Root,
    Symbol,
    Format,
    Out,
    Help,
}
const OPTIONS: &[(&str, Opt)] = &[
    ("--root", Opt::Root),
    ("--cpp-symbol", Opt::Symbol),
    ("--format", Opt::Format),
    ("--out", Opt::Out),
    ("--help", Opt::Help),
];
#[derive(Default)]
struct Args {
    root: Option<PathBuf>,
    symbol: Option<String>,
    format: String,
    out: Option<PathBuf>,
}
enum Parsed {
    Help,
    Run(Args),
}

#[derive(Clone, Debug)]
struct Symbol {
    name: String,
    qualname: String,
    namespace: String,
    record: Option<String>,
    start: usize,
    line_start: usize,
    line_end: usize,
    header: String,
    body: String,
    params: String,
    return_type: String,
}
#[derive(Debug)]
struct Index {
    path: PathBuf,
    relative: String,
    root: PathBuf,
    source: String,
    file_hash: String,
    records: BTreeSet<String>,
    symbols: Vec<Symbol>,
}
#[derive(Clone, Debug)]
struct Control {
    kind: String,
    opcode: String,
    line: usize,
    condition: String,
    alternatives: Vec<String>,
    offset: usize,
}
#[derive(Clone, Debug)]
struct Call {
    text: String,
    line: usize,
    assigned: Vec<String>,
    receiver: Option<String>,
    receiver_type: Option<String>,
    target: String,
    edge_kind: String,
    resolved: bool,
    offset: usize,
}
#[derive(Clone, Debug)]
struct Fact {
    id: String,
    path: String,
    symbol: String,
    span: String,
    kind: String,
    target: String,
    expression: String,
    statement: String,
    hash: String,
}

fn parse_args(argv: &[String]) -> Result<Parsed, String> {
    let mut args = Args {
        format: "text".into(),
        ..Args::default()
    };
    let mut index = 0;
    while index < argv.len() {
        let token = &argv[index];
        if token == "-h" {
            return Ok(Parsed::Help);
        }
        let (name, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
        let option = resolve_long_option_prefix(name, OPTIONS).map_err(|error| match error {
            LongOptionError::Unrecognized => format!("unrecognized arguments: {name}"),
            LongOptionError::Ambiguous(values) => {
                format!("ambiguous option: {name} could match {}", values.join(", "))
            }
        })?;
        if option == Opt::Help {
            if inline.is_some() {
                return Err(format!(
                    "argument --help: ignored explicit argument '{token}'"
                ));
            }
            return Ok(Parsed::Help);
        }
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            argv.get(index)
                .filter(|value| !value.starts_with('-'))
                .cloned()
                .ok_or_else(|| format!("argument {name}: expected one argument"))?
        };
        match option {
            Opt::Root => args.root = Some(value.into()),
            Opt::Symbol => args.symbol = Some(value),
            Opt::Format => {
                if !["json", "markdown", "text"].contains(&value.as_str()) {
                    return Err(format!("argument --format: invalid choice: '{value}' (choose from 'json', 'markdown', 'text')"));
                }
                args.format = value;
            }
            Opt::Out => args.out = Some(value.into()),
            Opt::Help => unreachable!(),
        }
        index += 1;
    }
    if args.symbol.is_none() {
        return Err("the following arguments are required: --cpp-symbol".into());
    }
    Ok(Parsed::Run(args))
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn normalize_space(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}
fn line_at(source: &str, offset: usize) -> usize {
    source
        .as_bytes()
        .iter()
        .take(offset.min(source.len()))
        .filter(|byte| **byte == b'\n')
        .count()
        + 1
}
fn relative_path(path: &Path, root: &Path) -> String {
    path.strip_prefix(root)
        .map(|path| path.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().replace('\\', "/"))
}
fn blank_comment(captures: &regex::Captures<'_>) -> String {
    captures.get(0).map_or_else(String::new, |matched| {
        let mut result = String::with_capacity(matched.as_str().len());
        for character in matched.as_str().chars() {
            if matches!(character, '\n' | '\r') {
                result.push(character);
            } else {
                result.push_str(&" ".repeat(character.len_utf8()));
            }
        }
        result
    })
}
fn clean_comments(source: &str) -> String {
    let block = Regex::new(r"(?s)/\*.*?\*/").expect("valid block comment regex");
    let line = Regex::new(r"//[^\n]*").expect("valid line comment regex");
    let without_block = block.replace_all(source, blank_comment);
    line.replace_all(&without_block, blank_comment).into_owned()
}

fn matching_delimiter(source: &str, open: usize, left: u8, right: u8) -> Option<usize> {
    let bytes = source.as_bytes();
    if bytes.get(open).copied() != Some(left) {
        return None;
    }
    let mut depth = 0usize;
    let mut quote = 0u8;
    let mut escaped = false;
    for (index, byte) in bytes.iter().enumerate().skip(open) {
        if quote != 0 {
            if escaped {
                escaped = false;
            } else if *byte == b'\\' {
                escaped = true;
            } else if *byte == quote {
                quote = 0;
            }
            continue;
        }
        if *byte == b'\'' || *byte == b'"' {
            quote = *byte;
            continue;
        }
        if *byte == left {
            depth += 1;
        } else if *byte == right {
            depth = depth.checked_sub(1)?;
            if depth == 0 {
                return Some(index);
            }
        }
    }
    None
}

fn split_csv(text: &str) -> Vec<String> {
    let mut values = Vec::new();
    let mut start = 0usize;
    let mut stack = Vec::<char>::new();
    let mut quote = None;
    let mut escaped = false;
    for (index, ch) in text.char_indices() {
        if let Some(current) = quote {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == current {
                quote = None;
            }
            continue;
        }
        if ch == '\'' || ch == '"' {
            quote = Some(ch);
            continue;
        }
        match ch {
            '<' | '(' | '[' | '{' => stack.push(ch),
            ')' => {
                if stack.last() == Some(&'(') {
                    stack.pop();
                }
            }
            ']' => {
                if stack.last() == Some(&'[') {
                    stack.pop();
                }
            }
            '}' => {
                if stack.last() == Some(&'{') {
                    stack.pop();
                }
            }
            '>' => {
                if stack.last() == Some(&'<') {
                    stack.pop();
                }
            }
            ',' if stack.is_empty() => {
                let value = text[start..index].trim();
                if !value.is_empty() {
                    values.push(value.to_owned());
                }
                start = index + ch.len_utf8();
            }
            _ => {}
        }
    }
    let tail = text[start..].trim();
    if !tail.is_empty() {
        values.push(tail.to_owned());
    }
    values
}

fn record_ranges(source: &str) -> Vec<(String, usize, usize)> {
    let regex = Regex::new(r"\b(?:class|struct)\s+(?P<name>[A-Za-z_]\w*)\s*\{")
        .expect("valid C++ record regex");
    let mut records = Vec::new();
    for captures in regex.captures_iter(source) {
        let Some(m) = captures.get(0) else { continue };
        let Some(open) = source[m.start()..m.end()]
            .rfind('{')
            .map(|offset| offset + m.start())
        else {
            continue;
        };
        if let Some(close) = matching_delimiter(source, open, b'{', b'}') {
            records.push((
                captures
                    .name("name")
                    .map_or("", |value| value.as_str())
                    .to_owned(),
                open,
                close + 1,
            ));
        }
    }
    records
}
fn namespace_ranges(source: &str) -> Vec<(String, usize, usize)> {
    let regex = Regex::new(r"\bnamespace\s+(?P<name>[A-Za-z_]\w*)\s*\{")
        .expect("valid C++ namespace regex");
    let mut values = Vec::new();
    for captures in regex.captures_iter(source) {
        let Some(m) = captures.get(0) else { continue };
        let Some(open) = source[m.start()..m.end()]
            .rfind('{')
            .map(|offset| offset + m.start())
        else {
            continue;
        };
        if let Some(close) = matching_delimiter(source, open, b'{', b'}') {
            values.push((
                captures
                    .name("name")
                    .map_or("", |value| value.as_str())
                    .to_owned(),
                open,
                close + 1,
            ));
        }
    }
    values
}
fn containing_ranges(ranges: &[(String, usize, usize)], offset: usize) -> Vec<String> {
    ranges
        .iter()
        .filter(|(_, start, end)| *start < offset && offset < *end)
        .map(|(name, _, _)| name.clone())
        .collect()
}

fn function_symbols(
    source: &str,
    path: &Path,
    relative: &str,
    root: &Path,
    records: &[(String, usize, usize)],
    namespaces: &[(String, usize, usize)],
) -> Vec<Symbol> {
    let mut symbols = Vec::new();
    let bytes = source.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i] != b'(' {
            i += 1;
            continue;
        }
        let Some(close) = matching_delimiter(source, i, b'(', b')') else {
            i += 1;
            continue;
        };
        let before = &source[..i];
        let name_end = before.trim_end().len();
        let mut name_start = name_end;
        while name_start > 0
            && (bytes[name_start - 1].is_ascii_alphanumeric()
                || matches!(bytes[name_start - 1], b'_' | b':' | b'~'))
        {
            name_start -= 1;
        }
        if name_start == name_end {
            i += 1;
            continue;
        }
        let raw_name = &source[name_start..name_end];
        let name = raw_name
            .rsplit("::")
            .next()
            .unwrap_or(raw_name)
            .trim_start_matches('~');
        if name.is_empty() || CONTROL_CALLS.contains(&name) {
            i = close + 1;
            continue;
        }
        let mut after = close + 1;
        while after < bytes.len() && bytes[after].is_ascii_whitespace() {
            after += 1;
        }
        if source[after..].starts_with("const") {
            after += 5;
            while after < bytes.len() && bytes[after].is_ascii_whitespace() {
                after += 1;
            }
        }
        if source[after..].starts_with("noexcept") {
            after += 8;
            while after < bytes.len() && bytes[after].is_ascii_whitespace() {
                after += 1;
            }
        }
        if bytes.get(after).copied() != Some(b'{') {
            i = close + 1;
            continue;
        }
        let Some(body_end) = matching_delimiter(source, after, b'{', b'}') else {
            i = close + 1;
            continue;
        };
        let mut header_start = name_start;
        while header_start > 0 && !matches!(bytes[header_start - 1], b';' | b'{' | b'}') {
            header_start -= 1;
        }
        let prefix = source[header_start..name_start].trim();
        if prefix.is_empty()
            || prefix
                .split_whitespace()
                .any(|word| CONTROL_CALLS.contains(&word))
        {
            i = body_end + 1;
            continue;
        }
        let record = records
            .iter()
            .filter(|(_, start, end)| *start < name_start && name_start < *end)
            .min_by_key(|(_, start, end)| end - start)
            .map(|(name, _, _)| name.clone());
        let namespace = containing_ranges(namespaces, name_start).join(".");
        let qualname = if let Some(record) = record.as_deref() {
            let record_qual = if namespace.is_empty() {
                record.to_owned()
            } else {
                format!("{namespace}.{record}")
            };
            format!("{record_qual}.{name}")
        } else if !namespace.is_empty() {
            format!("{namespace}.{name}")
        } else {
            raw_name.replace("::", ".")
        };
        let params = source[i + 1..close].trim().to_owned();
        let return_type = prefix
            .split_whitespace()
            .filter(|word| {
                !matches!(
                    *word,
                    "static" | "inline" | "virtual" | "constexpr" | "const" | "friend" | "extern"
                )
            })
            .collect::<Vec<_>>()
            .join(" ");
        let header = normalize_space(source[header_start..after].trim());
        symbols.push(Symbol {
            name: name.to_owned(),
            qualname,
            namespace,
            record,
            line_start: line_at(source, name_start),
            line_end: line_at(source, body_end),
            start: header_start,
            header,
            body: source[after + 1..body_end].to_owned(),
            params,
            return_type,
        });
        i = body_end + 1;
    }
    let _ = (path, relative, root);
    symbols.sort_by_key(|symbol| symbol.start);
    symbols
}

fn parse_symbol_reference(reference: &str) -> Result<(PathBuf, String), String> {
    let Some((path, qualname)) = reference.split_once("::") else {
        return Err(format!("argument --cpp-symbol: invalid C++ symbol reference {reference:?}; expected path.cpp::qualname"));
    };
    let path = PathBuf::from(path.trim());
    let qualname = qualname.trim().replace("::", ".");
    if path.as_os_str().is_empty() || qualname.is_empty() {
        return Err(format!("argument --cpp-symbol: invalid C++ symbol reference {reference:?}; expected path.cpp::qualname"));
    }
    Ok((path, qualname))
}

fn load_index(cpp_symbol: &str, root: &Path) -> Result<(Index, String), String> {
    let (path, qualname) = parse_symbol_reference(cpp_symbol)?;
    let root = root
        .canonicalize()
        .map_err(|error| format!("C++ source root does not exist: {error}"))?;
    let candidate = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    if !candidate.is_file() {
        return Err(format!(
            "C++ source path does not exist: {}",
            candidate.display()
        ));
    }
    let path = candidate
        .canonicalize()
        .map_err(|error| format!("C++ source path does not exist: {error}"))?;
    let source = fs::read_to_string(&path)
        .map_err(|error| format!("cannot read C++ source {}: {error}", path.display()))?;
    let scrubbed = clean_comments(&source);
    let records = record_ranges(&scrubbed);
    let namespaces = namespace_ranges(&scrubbed);
    let symbols = function_symbols(
        &scrubbed,
        &path,
        &relative_path(&path, &root),
        &root,
        &records,
        &namespaces,
    );
    let file_hash = sha256(scrubbed.as_bytes());
    let index = Index {
        path: path.clone(),
        relative: relative_path(&path, &root),
        root,
        source: scrubbed.clone(),
        file_hash,
        records: records.iter().map(|(name, _, _)| name.clone()).collect(),
        symbols,
    };
    Ok((index, qualname))
}

fn parameter_records(params: &str) -> Vec<Value> {
    split_csv(params)
        .iter()
        .enumerate()
        .filter_map(|(index, declaration)| {
            let declaration = declaration.trim();
            let words = Regex::new(r"[A-Za-z_]\w*")
                .expect("valid C++ parameter regex")
                .find_iter(declaration)
                .map(|match_| match_.as_str().to_owned())
                .collect::<Vec<_>>();
            if words.is_empty() {
                return None;
            }
            let name = words.last().cloned().unwrap_or_default();
            let type_name = clean_type_name(declaration, &name);
            Some(json!({"index":index,"name":name,"declaration":declaration,"type":type_name}))
        })
        .collect()
}
fn clean_type_name(declaration: &str, name: &str) -> String {
    let without_name = declaration.replace(name, "");
    without_name
        .split_whitespace()
        .filter(|word| {
            !matches!(
                *word,
                "const" | "volatile" | "static" | "constexpr" | "&" | "*" | "&&"
            )
        })
        .collect::<Vec<_>>()
        .join(" ")
        .replace("&", "")
        .replace("*", "")
        .trim()
        .to_owned()
}

fn resolve_symbol<'a>(
    index: &'a Index,
    name: &str,
    current: &Symbol,
    receiver_type: Option<&str>,
) -> Option<&'a Symbol> {
    let candidate = if let Some(receiver) = receiver_type {
        let candidate = format!("{receiver}.{name}");
        index
            .symbols
            .iter()
            .find(|symbol| symbol.qualname == candidate)
    } else {
        let record_candidate = current.record.as_ref().map(|record| {
            let prefix = if current.namespace.is_empty() {
                record.clone()
            } else {
                format!("{}.{}", current.namespace, record)
            };
            format!("{prefix}.{name}")
        });
        record_candidate
            .as_ref()
            .and_then(|candidate| {
                index
                    .symbols
                    .iter()
                    .find(|symbol| symbol.qualname == *candidate)
            })
            .or_else(|| {
                let local = if current.namespace.is_empty() {
                    name.to_owned()
                } else {
                    format!("{}.{}", current.namespace, name)
                };
                index.symbols.iter().find(|symbol| symbol.qualname == local)
            })
            .or_else(|| index.symbols.iter().find(|symbol| symbol.qualname == name))
    };
    candidate
}

fn collect_calls(index: &Index, symbol: &Symbol) -> Vec<Call> {
    let direct = Regex::new(r"(?P<name>[A-Za-z_]\w*)\s*\(").expect("valid direct C++ call regex");
    let method =
        Regex::new(r"(?P<receiver>[A-Za-z_]\w*)\s*(?:\.|->)\s*(?P<name>[A-Za-z_]\w*)\s*\(")
            .expect("valid method C++ call regex");
    let mut sites = Vec::new();
    let mut receiver_types = BTreeMap::<String, String>::new();
    for row in parameter_records(&symbol.params) {
        if let (Some(name), Some(type_)) = (
            row.get("name").and_then(Value::as_str),
            row.get("type").and_then(Value::as_str),
        ) {
            receiver_types.insert(name.to_owned(), type_.to_owned());
        }
    }
    let constructor =
        Regex::new(r"\b(?P<type>[A-Za-z_]\w*)\s+(?P<name>[A-Za-z_]\w*)\s*(?:\{|=\s*[^;]+;)")
            .expect("valid C++ local constructor regex");
    for captures in constructor.captures_iter(&symbol.body) {
        if let (Some(type_), Some(name)) = (captures.name("type"), captures.name("name")) {
            if index.records.contains(type_.as_str()) {
                receiver_types.insert(name.as_str().to_owned(), type_.as_str().to_owned());
            }
        }
    }
    let mut covered = HashSet::new();
    for captures in method.captures_iter(&symbol.body) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        covered.insert(
            captures
                .name("name")
                .map(|value| value.start())
                .unwrap_or(full.start()),
        );
        let receiver = captures
            .name("receiver")
            .map_or("", |value| value.as_str())
            .to_owned();
        let name = captures
            .name("name")
            .map_or("", |value| value.as_str())
            .to_owned();
        let receiver_type = receiver_types.get(&receiver).cloned();
        let target = resolve_symbol(index, &name, symbol, receiver_type.as_deref());
        sites.push(Call {
            text: full.as_str().trim().to_owned(),
            line: line_at(&symbol.body, full.start()) + symbol.line_start - 1,
            assigned: assigned_to(&symbol.body, full.start()),
            receiver: Some(receiver),
            receiver_type,
            target: target.map_or(name.clone(), |target| target.qualname.clone()),
            edge_kind: "method_call".into(),
            resolved: target.is_some(),
            offset: full.start(),
        });
    }
    for captures in direct.captures_iter(&symbol.body) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        let Some(name_match) = captures.name("name") else {
            continue;
        };
        if covered.contains(&name_match.start()) || CONTROL_CALLS.contains(&name_match.as_str()) {
            continue;
        }
        let name = name_match.as_str();
        let target = resolve_symbol(index, name, symbol, None);
        sites.push(Call {
            text: full.as_str().trim().to_owned(),
            line: line_at(&symbol.body, full.start()) + symbol.line_start - 1,
            assigned: assigned_to(&symbol.body, full.start()),
            receiver: None,
            receiver_type: None,
            target: target.map_or_else(|| name.to_owned(), |target| target.qualname.clone()),
            edge_kind: "direct_call".into(),
            resolved: target.is_some(),
            offset: full.start(),
        });
    }
    sites.sort_by_key(|site| site.offset);
    sites.dedup_by(|a, b| a.offset == b.offset);
    sites
}

fn assigned_to(body: &str, offset: usize) -> Vec<String> {
    let line = body[..offset.min(body.len())]
        .rsplit('\n')
        .next()
        .unwrap_or_default();
    let Some((target, _)) = line.rsplit_once('=') else {
        return Vec::new();
    };
    let target = target
        .split_whitespace()
        .last()
        .unwrap_or_default()
        .trim_matches(|character: char| !character.is_ascii_alphanumeric() && character != '_');
    if target.is_empty() {
        Vec::new()
    } else {
        vec![target.to_owned()]
    }
}

fn control_sites(symbol: &Symbol) -> Vec<Control> {
    let regex =
        Regex::new(r"\b(?P<keyword>if|while|for|switch)\s*\(").expect("valid C++ control regex");
    let mut controls = Vec::new();
    for captures in regex.captures_iter(&symbol.body) {
        let Some(full) = captures.get(0) else {
            continue;
        };
        let Some(open) = symbol.body[full.start()..full.end()]
            .rfind('(')
            .map(|offset| offset + full.start())
        else {
            continue;
        };
        let Some(close) = matching_delimiter(&symbol.body, open, b'(', b')') else {
            continue;
        };
        let keyword = captures.name("keyword").map_or("", |value| value.as_str());
        let condition = symbol.body[open + 1..close].trim().to_owned();
        let line = line_at(&symbol.body, full.start()) + symbol.line_start - 1;
        let (kind, opcode, alternatives) = match keyword {
            "if" => ("If", "cxx.if", vec!["then".to_owned(), "else".to_owned()]),
            "while" => (
                "While",
                "cxx.while",
                vec!["skip".to_owned(), "enter".to_owned()],
            ),
            "for" => (
                "While",
                "cxx.for",
                vec!["skip".to_owned(), "enter".to_owned()],
            ),
            _ => (
                "Case",
                "cxx.switch",
                switch_alternatives(&symbol.body[close + 1..])
                    .unwrap_or_else(|| vec!["case".into()]),
            ),
        };
        controls.push(Control {
            kind: kind.into(),
            opcode: opcode.into(),
            line,
            condition,
            alternatives,
            offset: full.start(),
        });
    }
    controls
}
fn switch_alternatives(body: &str) -> Option<Vec<String>> {
    let labels = Regex::new(r"\bcase\s+(?P<label>[^:]+):|\bdefault\s*:")
        .expect("valid C++ switch label regex");
    let values = labels
        .captures_iter(body)
        .map(|captures| {
            captures
                .name("label")
                .map_or("default".into(), |value| value.as_str().trim().to_owned())
        })
        .collect::<Vec<_>>();
    (!values.is_empty()).then_some(values)
}

fn control_paths(controls: &[Control]) -> Vec<Vec<(usize, String)>> {
    let mut paths = vec![Vec::<(usize, String)>::new()];
    for control in controls {
        let mut next = Vec::new();
        for path in &paths {
            for choice in &control.alternatives {
                let mut selected = path.clone();
                selected.push((control.line, choice.clone()));
                next.push(selected);
            }
        }
        paths = next;
    }
    paths
}

fn find_symbol<'a>(index: &'a Index, qualname: &str) -> Result<&'a Symbol, String> {
    index
        .symbols
        .iter()
        .find(|symbol| symbol.qualname == qualname)
        .ok_or_else(|| format!("C++ source symbol not found: {qualname}"))
}

fn reachable_symbols(index: &Index, root: &Symbol) -> Vec<Symbol> {
    let mut selected = Vec::new();
    let mut visited = BTreeSet::new();
    let mut pending = vec![root.qualname.clone()];
    while let Some(name) = pending.pop() {
        if !visited.insert(name.clone()) {
            continue;
        }
        let Some(symbol) = index.symbols.iter().find(|symbol| symbol.qualname == name) else {
            continue;
        };
        selected.push(symbol.clone());
        for call in collect_calls(index, symbol).into_iter().rev() {
            if call.resolved && !visited.contains(&call.target) {
                pending.push(call.target);
            }
        }
    }
    selected
}

fn source_facts(index: &Index, functions: &[Symbol]) -> Vec<Fact> {
    let assignment = Regex::new(r"(?P<target>[A-Za-z_]\w*)\s*=\s*(?P<expression>[^;]+);")
        .expect("valid C++ assignment fact regex");
    let initialized=Regex::new(r"\b(?P<type>[A-Za-z_]\w*(?:::\w+)*)\s+(?P<target>[A-Za-z_]\w*)\s*\{(?P<expression>[^;{}]*)\};").expect("valid C++ initializer fact regex");
    let returned =
        Regex::new(r"\breturn\s+(?P<expression>[^;]+);").expect("valid C++ return fact regex");
    let mut facts = Vec::new();
    for symbol in functions {
        for captures in assignment.captures_iter(&symbol.body) {
            let Some(full) = captures.get(0) else {
                continue;
            };
            let target = captures.name("target").map_or("", |value| value.as_str());
            let expression = captures
                .name("expression")
                .map_or("", |value| value.as_str())
                .trim();
            let line = line_at(&symbol.body, full.start()) + symbol.line_start - 1;
            let statement = full.as_str().trim().to_owned();
            facts.push(make_fact(
                index,
                symbol,
                line,
                "assignment_equation",
                target,
                expression,
                statement,
                full.start(),
            ));
        }
        for captures in initialized.captures_iter(&symbol.body) {
            let Some(full) = captures.get(0) else {
                continue;
            };
            let target = captures.name("target").map_or("", |value| value.as_str());
            let expression = captures
                .name("expression")
                .map_or("", |value| value.as_str())
                .trim();
            let line = line_at(&symbol.body, full.start()) + symbol.line_start - 1;
            facts.push(make_fact(
                index,
                symbol,
                line,
                "assignment_equation",
                target,
                expression,
                full.as_str().trim().to_owned(),
                full.start(),
            ));
        }
        for captures in returned.captures_iter(&symbol.body) {
            let Some(full) = captures.get(0) else {
                continue;
            };
            let expression = captures
                .name("expression")
                .map_or("", |value| value.as_str())
                .trim();
            let line = line_at(&symbol.body, full.start()) + symbol.line_start - 1;
            facts.push(make_fact(
                index,
                symbol,
                line,
                "return_equation",
                "return",
                expression,
                full.as_str().trim().to_owned(),
                full.start(),
            ));
        }
    }
    facts
}

#[allow(clippy::too_many_arguments)]
fn make_fact(
    index: &Index,
    symbol: &Symbol,
    line: usize,
    kind: &str,
    target: &str,
    expression: &str,
    statement: String,
    offset: usize,
) -> Fact {
    let hash = sha256(statement.as_bytes());
    Fact {
        id: format!("fact:{}:{kind}:{line}:{:05}", symbol.qualname, offset),
        path: index.relative.clone(),
        symbol: symbol.qualname.clone(),
        span: format!("{line}:{line}"),
        kind: kind.to_owned(),
        target: target.to_owned(),
        expression: expression.to_owned(),
        statement,
        hash,
    }
}

#[allow(clippy::too_many_arguments)]
fn append_operation(
    ops: &mut Vec<Value>,
    region: &mut Value,
    function: &str,
    line: usize,
    kind: &str,
    opcode: &str,
    text: &str,
    call_target: &str,
    extra: Map<String, Value>,
) -> String {
    let id = format!("op_{:05}", ops.len());
    let region_id = region["region_id"].as_str().unwrap_or_default().to_owned();
    let mut row = json!({"op_id":id,"kind":kind,"opcode":opcode,"line":line,"text":text,"text_sha256":sha256(text.as_bytes()),"tensor_types":[],"dtypes":[],"function":function,"region_id":region_id,"region_path":[region_id],"parent_op_id":region.get("parent_op_id").and_then(Value::as_str).unwrap_or_default(),"call_target":call_target});
    if let Some(object) = row.as_object_mut() {
        object.extend(extra);
    }
    ops.push(row);
    if let Some(ids) = region.get_mut("op_ids").and_then(Value::as_array_mut) {
        ids.push(json!(id));
    }
    id
}

fn build_operational_ir(
    index: &Index,
    functions: &[Symbol],
    _root_symbol: &str,
    source_facts: &[Fact],
) -> Value {
    let mut ops = Vec::<Value>::new();
    let mut function_rows = Vec::<Value>::new();
    let mut regions = Vec::<Value>::new();
    let mut edges = Vec::<Value>::new();
    let mut code_paths = Vec::<Value>::new();
    let module_region = json!({"region_id":"region_00000","kind":"module","parent_function":"","parent_op_id":"","depth":0,"line_start":1,"line_end":index.source.lines().count(),"op_ids":[]});
    regions.push(module_region.clone());
    let mut signatures = Vec::new();
    let mut unresolved = BTreeSet::new();
    let mut call_edges = BTreeSet::new();
    edges.push(
        json!({"edge_id":"edge_00000","kind":"program_root","from":"program","to":"region_00000"}),
    );
    let mut control_coverage = BTreeMap::<String, usize>::new();
    let mut code_decision_count = 0usize;
    let mut max_decisions = 0usize;
    let all_facts_by_symbol =
        source_facts
            .iter()
            .fold(BTreeMap::<String, Vec<&Fact>>::new(), |mut map, fact| {
                map.entry(fact.symbol.clone()).or_default().push(fact);
                map
            });
    let constructor = Regex::new(r"\b(?P<type>[A-Z][A-Za-z_\w]*)\s+(?P<name>[A-Za-z_]\w*)\s*\{")
        .expect("valid C++ construction regex");
    for symbol in functions {
        let function_id = format!("function:{}", symbol.qualname);
        let function_op_id = format!("op_{:05}", ops.len());
        let body_region_id = format!("region_{:05}", regions.len());
        signatures.push(format!(
            "{} {}({})",
            symbol.return_type, symbol.qualname, symbol.params
        ));
        function_rows.push(json!({"function_id":function_id,"name":symbol.qualname,"signature":signatures.last().cloned().unwrap_or_default(),"line_start":symbol.line_start,"line_end":symbol.line_end,"body_region_id":body_region_id,"argument_names":parameter_records(&symbol.params).iter().filter_map(|row|row.get("name").cloned()).collect::<Vec<_>>() }));
        let mut module_region = regions[0].clone();
        append_operation(
            &mut ops,
            &mut module_region,
            &symbol.qualname,
            symbol.line_start,
            "Function",
            "cxx.function",
            &symbol.header,
            "",
            Map::new(),
        );
        regions[0] = module_region;
        let mut body_region = json!({"region_id":body_region_id,"kind":"function_body","parent_function":symbol.qualname,"parent_op_id":function_op_id,"depth":1,"line_start":symbol.line_start,"line_end":symbol.line_end,"op_ids":[]});
        edges.push(json!({"edge_id":format!("edge_{:05}",edges.len()),"kind":"function_body","from":function_id,"to":body_region_id}));
        let calls = collect_calls(index, symbol);
        let controls = control_sites(symbol);
        let facts = all_facts_by_symbol
            .get(&symbol.qualname)
            .cloned()
            .unwrap_or_default();
        let mut events = Vec::<(usize, usize, Value)>::new();
        for call in &calls {
            let extra = json!({"edge_kind":call.edge_kind,"receiver_name":call.receiver,"receiver_type":call.receiver_type,"target_symbol":call.target,"resolved":call.resolved,"assigned_to":call.assigned});
            events.push((call.offset,3,json!({"kind":"Call","opcode":"cxx.call","line":call.line,"text":call.text,"call_target":if call.resolved{call.target.as_str()}else{""},"extra":extra})));
            if !call.resolved {
                unresolved.insert(call.target.clone());
            }
        }
        for control in &controls {
            *control_coverage.entry(control.kind.clone()).or_default() += 1;
            let extra = json!({"condition":control.condition,"alternatives":control.alternatives});
            events.push((control.offset,2,json!({"kind":control.kind,"opcode":control.opcode,"line":control.line,"text":control.condition,"call_target":"","extra":extra})));
        }
        for captures in constructor.captures_iter(&symbol.body) {
            let Some(full) = captures.get(0) else {
                continue;
            };
            let type_ = captures.name("type").map_or("", |value| value.as_str());
            let name = captures.name("name").map_or("", |value| value.as_str());
            if !index.records.contains(type_) {
                continue;
            }
            let line = line_at(&symbol.body, full.start()) + symbol.line_start - 1;
            let extra = json!({"edge_kind":"constructs","target_symbol":type_,"assigned_to":[name],"resolved":true});
            events.push((full.start(),1,json!({"kind":"Primitive","opcode":"cxx.construct","line":line,"text":full.as_str().trim(),"call_target":"","extra":extra})));
        }
        for fact in facts {
            let code = if fact.kind == "return_equation" {
                "Return"
            } else {
                "Let"
            };
            let opcode = if code == "Return" {
                "cxx.return"
            } else {
                "cxx.assignment"
            };
            events.push((fact_offset(&symbol.body,&fact.statement),0,json!({"kind":code,"opcode":opcode,"line":fact.span.split(':').next().unwrap_or("0").parse::<usize>().unwrap_or_default(),"text":fact.statement,"call_target":"","extra":{"fact_id":fact.id,"fact_kind":fact.kind,"target":fact.target,"expression":fact.expression}})));
        }
        events.sort_by_key(|event| (event.0, event.1));
        let mut control_op_ids = BTreeMap::<usize, String>::new();
        for (offset, _, event) in events {
            let kind = event
                .get("kind")
                .and_then(Value::as_str)
                .unwrap_or("Primitive");
            let opcode = event
                .get("opcode")
                .and_then(Value::as_str)
                .unwrap_or("cxx.primitive");
            let line = event
                .get("line")
                .and_then(Value::as_u64)
                .unwrap_or_default() as usize;
            let text = event
                .get("text")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let call_target = event
                .get("call_target")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let extra = event
                .get("extra")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            let op_id = append_operation(
                &mut ops,
                &mut body_region,
                &symbol.qualname,
                line,
                kind,
                opcode,
                text,
                call_target,
                extra,
            );
            if controls.iter().any(|control| control.offset == offset) {
                control_op_ids.insert(offset, op_id);
            }
        }
        let body_op_ids = body_region
            .get("op_ids")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let control_ids = controls
            .iter()
            .map(|control| {
                let op_id = control_op_ids
                    .get(&control.offset)
                    .cloned()
                    .unwrap_or_default();
                (control, op_id)
            })
            .collect::<Vec<_>>();
        let paths = control_paths(&controls);
        for (path_index, path) in paths.iter().enumerate() {
            let mut decisions = Vec::new();
            let mut summary = Vec::new();
            for (control, (line, choice)) in controls.iter().zip(path) {
                let op_id = control_ids
                    .iter()
                    .find(|(candidate, _)| candidate.offset == control.offset)
                    .map_or("", |(_, id)| id.as_str());
                let kind = control.opcode.trim_start_matches("cxx.");
                decisions.push(json!({"op_id":op_id,"kind":kind,"choice":choice,"condition":control.condition,"line":line}));
                summary.push(format!("{kind}@{line}:{choice}"));
            }
            let count = decisions.len();
            code_decision_count += count;
            max_decisions = max_decisions.max(count);
            let summary = if summary.is_empty() {
                "straight_line".to_owned()
            } else {
                summary.join(" -> ")
            };
            code_paths.push(json!({"path_id":format!("path:{}:{path_index:05}",symbol.qualname),"function":symbol.qualname,"region_id":body_region_id,"op_ids":body_op_ids.iter().filter_map(Value::as_str).collect::<Vec<_>>(),"decisions":decisions,"decision_count":count,"summary":summary}));
        }
        regions.push(body_region);
        for target in calls
            .iter()
            .filter(|call| call.resolved)
            .map(|call| call.target.as_str())
            .collect::<BTreeSet<_>>()
        {
            if call_edges.insert(target.to_owned()) {
                edges.push(json!({"edge_id":format!("edge_{:05}",edges.len()),"kind":"call_target","from":format!("function:{}",symbol.qualname),"to":format!("function:{target}")}));
            }
        }
    }
    let assigned_region_ids = ops
        .iter()
        .filter_map(|op| op.get("region_id").and_then(Value::as_str))
        .collect::<BTreeSet<_>>();
    let count_kind = |kind: &str| {
        ops.iter()
            .filter(|op| op.get("kind").and_then(Value::as_str) == Some(kind))
            .count()
    };
    let unresolved = unresolved.into_iter().collect::<Vec<_>>();
    let unmapped = Vec::<String>::new();
    let coverage = json!({"function_count":function_rows.len(),"region_count":regions.len(),"expansion_edge_count":edges.len(),"op_count":ops.len(),"assigned_region_count":assigned_region_ids.len(),"unassigned_op_count":0,"unassigned_op_ids":[],"unresolved_call_targets":unresolved,"max_region_depth":1,"while_count":control_coverage.get("While").copied().unwrap_or_default(),"case_count":control_coverage.get("Case").copied().unwrap_or_default(),"if_count":control_coverage.get("If").copied().unwrap_or_default(),"call_count":count_kind("Call"),"code_path_count":code_paths.len(),"code_path_decision_count":code_decision_count,"max_code_path_decisions":max_decisions,"unmapped_code_path_functions":unmapped});
    json!({"schema":"agent-canon.thin-operational-ir.v2","allowed_kinds":["Function","Let","Call","If","While","Case","Tuple","Projection","Primitive","Return"],"function_signatures":signatures,"functions":function_rows,"regions":regions,"expansion_edges":edges,"code_paths":code_paths,"ops":ops,"coverage":coverage})
}

fn fact_offset(body: &str, statement: &str) -> usize {
    body.find(statement).unwrap_or_default()
}

fn make_source_facts(index: &Index, functions: &[Symbol]) -> Vec<Value> {
    source_facts(index,functions).iter().map(|fact|json!({"fact_id":fact.id,"source_path":fact.path,"source_symbol":fact.symbol,"source_span":fact.span,"fact_kind":fact.kind,"target":fact.target,"expression":fact.expression,"statement":fact.statement,"text_sha256":fact.hash})).collect()
}

pub fn build_cpp_source_canonical_ir(cpp_symbol: &str, root: &Path) -> Result<Value, String> {
    let (index, qualname) = load_index(cpp_symbol, root)?;
    let root_symbol = find_symbol(&index, &qualname)?;
    let functions = reachable_symbols(&index, root_symbol);
    let facts = source_facts(&index, &functions);
    let operational_ir = build_operational_ir(&index, &functions, &qualname, &facts);
    let parameters = parameter_records(&root_symbol.params);
    let mut source_facts = make_source_facts(&index, &functions);
    source_facts.sort_by_key(|fact| {
        fact.get("fact_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned()
    });
    let assignment_count = facts
        .iter()
        .filter(|fact| fact.kind == "assignment_equation")
        .count();
    let return_count = facts
        .iter()
        .filter(|fact| fact.kind == "return_equation")
        .count();
    let public_coverage = json!({"parameter_count":parameters.len(),"has_return_type":!root_symbol.return_type.is_empty(),"stablehlo_specific_fields":0});
    let source_span = format!("{}:{}", root_symbol.line_start, root_symbol.line_end);
    let source_segment = format!("{}\n{}", root_symbol.header, root_symbol.body);
    let root_record = json!({
        "schema":"agent-canon.cpp-source-root-ref.v1",
        "cpp_symbol":cpp_symbol,
        "repo_root":index.root,
        "source_kind":"cxx_source",
        "source_path":index.relative,
        "qualname":qualname
    });
    let source_root = json!({
        "schema":"agent-canon.cpp-source-root.v1",
        "status":"ok",
        "cpp_symbol":cpp_symbol,
        "path":index.path,
        "relative_path":index.relative,
        "qualname":qualname,
        "name":qualname.rsplit('.').next().unwrap_or(&root_symbol.name),
        "node_kind":if root_symbol.record.is_some(){"CxxMethodDecl"}else{"CxxFunctionDecl"},
        "parameters":parameters.iter().filter_map(|row|row.get("name").cloned()).collect::<Vec<_>>(),
        "return_type":root_symbol.return_type,
        "source_sha256":sha256(source_segment.as_bytes()),
        "file_sha256":index.file_hash,
        "source_span":source_span,
        "parse_warnings":[]
    });
    let public_interface = json!({
        "schema":"agent-canon.cpp-public-interface.v1",
        "status":"ok",
        "cpp_symbol":cpp_symbol,
        "qualname":qualname,
        "name":root_symbol.name,
        "parameters":parameters,
        "return_type":root_symbol.return_type,
        "coverage":public_coverage
    });
    let coverage = json!({
        "record_count":index.records.len(),
        "indexed_symbol_count":index.symbols.len(),
        "reachable_function_count":functions.len(),
        "parse_warning_count":0,
        "source_only":true
    });
    Ok(json!({
        "schema":"agent-canon.cpp-source-canonical-ir.v1",
        "root":root_record,
        "source_root":source_root,
        "public_interface":public_interface,
        "source_facts":{"schema":"agent-canon.cpp-source-facts.v1","facts":source_facts,"coverage":{"fact_count":facts.len(),"assignment_equation_count":assignment_count,"return_equation_count":return_count}},
        "operational_ir":operational_ir,
        "coverage":coverage
    }))
}

fn render_markdown(record: &Value) -> String {
    let coverage = &record["operational_ir"]["coverage"];
    format!("# C++ Source Canonical IR\n\n- source: `{}`\n- root: `{}`\n\n## Operational IR Coverage\n\n| Metric | Count |\n| --- | ---: |\n| Functions | {} |\n| Operations | {} |\n| Call edges | {} |\n| Code paths | {} |\n| Unresolved calls | {} |\n",record["source_root"]["relative_path"].as_str().unwrap_or(""),record["source_root"]["qualname"].as_str().unwrap_or(""),coverage["function_count"],coverage["op_count"],coverage["expansion_edge_count"],coverage["code_path_count"],coverage["unresolved_call_targets"].as_array().map_or(0,Vec::len))
}
fn render_record(record: &Value, format: &str) -> Result<String, String> {
    match format{"json"=>Ok(serde_json::to_string_pretty(record).map_err(|error|error.to_string())?+"\n"),"markdown"=>Ok(render_markdown(record)),_=>Ok(format!("CPP_SOURCE_CANONICAL_IR_STATUS=pass\nCPP_SOURCE_CANONICAL_IR_FUNCTIONS={}\nCPP_SOURCE_CANONICAL_IR_OPS={}\n",record["operational_ir"]["coverage"]["function_count"],record["operational_ir"]["coverage"]["op_count"]))}
}

pub fn run(argv: &[String]) -> i32 {
    let args = match parse_args(argv) {
        Ok(Parsed::Help) => {
            println!("{USAGE}");
            return 0;
        }
        Ok(Parsed::Run(args)) => args,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let result = (|| -> Result<(), String> {
        let root = args.root.as_deref().unwrap_or(Path::new("."));
        let symbol = args.symbol.as_deref().expect("required symbol");
        let record = build_cpp_source_canonical_ir(symbol, root)?;
        let rendered = render_record(&record, &args.format)?;
        if let Some(path) = args.out.as_deref() {
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)
                    .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
            }
            fs::write(path, rendered)
                .map_err(|error| format!("cannot write {}: {error}", path.display()))?;
        } else {
            print!("{rendered}");
        }
        Ok(())
    })();
    match result {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            1
        }
    }
}
