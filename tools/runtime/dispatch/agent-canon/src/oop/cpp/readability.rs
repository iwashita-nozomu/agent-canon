// @dependency-start
// contract implementation
// responsibility Preserves C++ OOP source metrics and bounded lexical masking.
// upstream implementation ../readability.rs owns findings and thresholds
// @dependency-end

use crate::oop_readability::{integer_value, Finding, Thresholds};
use regex::Regex;
use rustpython_ast::bigint::BigInt;
use serde_json::{json, Value};
use std::sync::LazyLock;

static CLASS: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?m)(?P<kind>class|struct)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::(?P<bases>[^{]+))?\{",
    )
    .unwrap()
});
static FUNCTION: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)(?P<prefix>[A-Za-z_][A-Za-z0-9_:<>\s*&~,\[\]]+?)\s+(?P<name>[A-Za-z_~][A-Za-z0-9_:~]*)\s*\((?P<params>[^;{}()]*)\)\s*(?:const\s*)?(?:noexcept\s*)?\{").unwrap()
});
static SCALAR: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(?:bfloat|float|int|uint)\d+x\d+$").unwrap());
static CLASS_PREFIX: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?:class|struct)\s+$").unwrap());
static IDENTIFIER: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[A-Za-z_][A-Za-z0-9_]*").unwrap());
static BRANCH: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\b(if|for|while|switch|case|catch)\b").unwrap());
static RETURN_CALL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^return\s+(.+?)\((.*)\)\s*;$").unwrap());
static FORWARD: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"^(?:(?:std::)?move|(?:std::)?forward\s*<[^>]+>)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)$",
    )
    .unwrap()
});
static VALUE_RETURN: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\breturn\s+[^;\s][^;]*;").unwrap());

pub(crate) fn mask(source: &str) -> String {
    let bytes = source.as_bytes();
    let mut output = bytes.to_vec();
    let mut index = 0;
    while index < bytes.len() {
        let start = index;
        let end = if bytes[index..].starts_with(b"//") {
            source[index..]
                .find('\n')
                .map(|offset| index + offset)
                .unwrap_or(bytes.len())
        } else if bytes[index..].starts_with(b"/*") {
            let Some(close) = source[index + 2..].find("*/") else {
                index += 1;
                continue;
            };
            index + 2 + close + 2
        } else {
            let prefix = if bytes[index..].starts_with(b"u8R\"") {
                Some(4)
            } else if bytes[index..].starts_with(b"R\"") {
                Some(2)
            } else if [b"uR\"".as_slice(), b"UR\"", b"LR\""]
                .iter()
                .any(|prefix| bytes[index..].starts_with(prefix))
            {
                Some(3)
            } else {
                None
            };
            if let Some(prefix) = prefix {
                let delimiter_start = index + prefix;
                if let Some(open) = source[delimiter_start..]
                    .find('(')
                    .map(|offset| delimiter_start + offset)
                {
                    let delimiter = &source[delimiter_start..open];
                    if delimiter.chars().any(|value| "\\ \t\n\r()".contains(value)) {
                        index += 1;
                        continue;
                    }
                    let close = format!("){delimiter}\"");
                    let Some(offset) = source[open + 1..].find(&close) else {
                        index += 1;
                        continue;
                    };
                    open + 1 + offset + close.len()
                } else {
                    index += 1;
                    continue;
                }
            } else if b"'\"".contains(&bytes[index]) {
                let quote = bytes[index];
                index += 1;
                let mut closed = false;
                while index < bytes.len() {
                    if bytes[index] == b'\\' {
                        index = (index + 2).min(bytes.len());
                    } else if bytes[index] == quote {
                        index += 1;
                        closed = true;
                        break;
                    } else {
                        index += 1;
                    }
                }
                if !closed {
                    index = start + 1;
                    continue;
                }
                index
            } else {
                index += source[index..]
                    .chars()
                    .next()
                    .expect("index before source end")
                    .len_utf8();
                continue;
            }
        };
        for value in &mut output[start..end] {
            if *value != b'\n' {
                *value = b' ';
            }
        }
        index = end;
    }
    String::from_utf8(output).expect("masked UTF-8 retains unmasked source scalars")
}

fn closing(source: &str, open: usize) -> Option<usize> {
    let mut depth = 0usize;
    for (offset, value) in source.as_bytes()[open..].iter().enumerate() {
        if *value == b'{' {
            depth += 1;
        } else if *value == b'}' {
            depth = depth.checked_sub(1)?;
            if depth == 0 {
                return Some(open + offset);
            }
        }
    }
    None
}

fn split_parameters(value: &str) -> Vec<&str> {
    let mut depths = [0usize; 4];
    let mut start = 0;
    let mut parts = Vec::new();
    for (offset, character) in value.char_indices() {
        if character == ',' && depths == [0; 4] {
            parts.push(value[start..offset].trim());
            start = offset + 1;
            continue;
        }
        if let Some(index) = "<([{ ".find(character).filter(|index| *index < 4) {
            depths[index] += 1;
        } else if let Some(index) = ">)]}".find(character) {
            depths[index] = depths[index].saturating_sub(1);
        }
    }
    parts.push(value[start..].trim());
    parts
        .into_iter()
        .filter(|value| !value.is_empty() && *value != "void")
        .collect()
}

fn public_members(kind: &str, body: &str) -> Vec<String> {
    let mut public = kind == "struct";
    let mut depth = 0isize;
    let mut pending = String::new();
    let mut result = Vec::new();
    for line in body.lines().map(str::trim) {
        if ["public:", "protected:", "private:"].contains(&line) {
            public = line == "public:";
            continue;
        }
        if !public {
            continue;
        }
        if !line.is_empty() && !line.starts_with('#') && depth == 0 {
            if !pending.is_empty() {
                pending.push(' ');
                pending.push_str(line);
            } else if !line.starts_with("using ")
                && !line.starts_with("typedef ")
                && (line.contains('(') || line.ends_with(';'))
            {
                pending = line.into();
            }
            if !pending.is_empty() && (line.contains(';') || line.contains('{')) {
                if (pending.contains('(') && pending.contains(')')) || pending.ends_with(';') {
                    result.push(std::mem::take(&mut pending));
                } else {
                    pending.clear();
                }
            }
        }
        depth = (depth + line.bytes().filter(|value| *value == b'{').count() as isize
            - line.bytes().filter(|value| *value == b'}').count() as isize)
            .max(0);
    }
    result
}

fn aggregate(name: &str) -> bool {
    [
        "Add",
        "Answer",
        "Cos",
        "Divide",
        "EvaluationContext",
        "Exp",
        "FunctionIr",
        "Literal",
        "Log",
        "LoweringOpcodeFor",
        "Multiply",
        "Negate",
        "Sin",
        "StateFunction",
        "StateFunctionResult",
        "Step",
        "Subtract",
        "operator_vector_leaf_traits",
        "two_float",
    ]
    .contains(&name)
        || [
            "Argument1D",
            "Binding",
            "Buffers",
            "Cache",
            "Comparison",
            "Config",
            "Contract",
            "Criterion",
            "Decision",
            "Descriptor",
            "DescriptorV3",
            "Eligibility",
            "Entry",
            "Functions",
            "Handle",
            "Header",
            "Identity",
            "Info",
            "Key",
            "Layout",
            "Manifest",
            "Metrics",
            "Norms",
            "Parameter",
            "Paths",
            "Point",
            "Problem",
            "Record",
            "Result",
            "Rule1D",
            "Selection",
            "Segment",
            "Set",
            "Shape",
            "Slice",
            "Snapshot",
            "Spec",
            "State",
            "Stats",
            "Storage",
            "Tape",
            "Triangle",
            "Views",
            "Workspace",
        ]
        .iter()
        .any(|suffix| name.ends_with(suffix))
}

pub(crate) fn dependency_findings(
    path: &str,
    source: &str,
    sources: &[(String, String)],
) -> Vec<Finding> {
    let text = mask(source);
    let mut findings = Vec::new();
    for capture in CLASS.captures_iter(&text) {
        let matched = capture.get(0).unwrap();
        let name = &capture["name"];
        if capture
            .name("bases")
            .is_some_and(|bases| !bases.as_str().trim().is_empty())
        {
            continue;
        }
        let Some(close) = closing(&text, matched.end() - 1) else {
            continue;
        };
        let members = public_members(&capture["kind"], &text[matched.end()..close]);
        let methods = members
            .iter()
            .filter(|member| member.contains('(') && member.contains(')'))
            .count();
        let fields = members.len() - methods;
        if methods > 1 || fields > 1 || (fields > 0 && aggregate(name)) || SCALAR.is_match(name) {
            continue;
        }
        let declarations = sources
            .iter()
            .map(|(_, source)| {
                CLASS
                    .captures_iter(source)
                    .filter(|capture| &capture["name"] == name)
                    .count()
            })
            .sum::<usize>();
        if declarations != 1 {
            continue;
        }
        let escaped = regex::escape(name);
        let construction = Regex::new(&format!(
            r"\b{escaped}\s*(?:\(|\{{)|\b{escaped}\s+[a-z_][A-Za-z0-9_]*\s*(?:[;={{(])"
        ))
        .unwrap();
        let mut construct = 0usize;
        let mut types = 0usize;
        let mut inherit = 0usize;
        let mut files = std::collections::BTreeSet::new();
        let type_name = Regex::new(&format!(r"\b{escaped}\b")).unwrap();
        for (source_path, source) in sources {
            for matched in construction.find_iter(source) {
                let prefix = &source[..matched.start()];
                if CLASS_PREFIX.is_match(
                    &prefix[prefix
                        .char_indices()
                        .rev()
                        .nth(15)
                        .map_or(0, |(index, _)| index)..],
                ) {
                    continue;
                }
                construct += 1;
                files.insert(source_path);
            }
            for capture in CLASS.captures_iter(source) {
                if let Some(bases) = capture.name("bases") {
                    let count = type_name.find_iter(bases.as_str()).count();
                    inherit += count;
                    if count > 0 {
                        files.insert(source_path);
                    }
                }
            }
            for capture in FUNCTION.captures_iter(source) {
                let count = type_name.find_iter(&capture["prefix"]).count()
                    + split_parameters(&capture["params"])
                        .iter()
                        .map(|parameter| type_name.find_iter(parameter).count())
                        .sum::<usize>();
                types += count;
                if count > 0 {
                    files.insert(source_path);
                }
            }
        }
        if construct > 0 && types == 0 && inherit == 0 {
            findings.push(Finding {
                path: path.into(),
                line: 1 + text[..matched.start()]
                    .bytes()
                    .filter(|value| *value == b'\n')
                    .count(),
                language: "cpp".into(),
                severity: "warn".into(),
                kind: "redundant_class_boundary".into(),
                symbol: name.into(),
                evidence: json!(format!(
                    "construct={construct},type={types},inherit={inherit},files={}",
                    files.len()
                )),
                contract: json!("type-boundary-or-owned-lifecycle"),
                guidance: "replace-with-function-or-document-class-lifecycle-contract".into(),
            });
        }
    }
    findings
}

pub(crate) fn analyze(path: &str, source: &str, thresholds: &Thresholds) -> Vec<Finding> {
    let text = mask(source);
    let mut findings = Vec::new();
    let mut add = |offset: usize,
                   kind: &str,
                   symbol: &str,
                   evidence: Value,
                   contract: Value,
                   guidance: &str| {
        findings.push(Finding {
            path: path.into(),
            line: 1 + text[..offset]
                .bytes()
                .filter(|value| *value == b'\n')
                .count(),
            language: "cpp".into(),
            severity: if kind == "syntax_error" {
                "error"
            } else if kind == "state_heavy_public_surface" {
                "info"
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
    };
    for capture in CLASS.captures_iter(&text) {
        let matched = capture.get(0).unwrap();
        let name = &capture["name"];
        let Some(close) = closing(&text, matched.end() - 1) else {
            add(
                matched.start(),
                "syntax_error",
                name,
                json!("unmatched-brace"),
                json!("parseable-cpp"),
                "fix-cpp-brace-structure-before-readability-analysis",
            );
            continue;
        };
        if ["Manager", "Helper", "Util", "Thing"]
            .iter()
            .any(|suffix| name.ends_with(suffix))
        {
            add(
                matched.start(),
                "vague_class_name",
                name,
                json!(name),
                json!("responsibility-name"),
                "rename-public-boundary-to-domain-responsibility",
            );
        }
        let bases = capture
            .name("bases")
            .map_or(0, |value| split_parameters(value.as_str()).len());
        if BigInt::from(bases) > thresholds.base_classes {
            add(
                matched.start(),
                "base_classes",
                name,
                json!(bases),
                integer_value(&thresholds.base_classes),
                "prefer-composition-over-wide-inheritance",
            );
        }
        let members = public_members(&capture["kind"], &text[matched.end()..close]);
        let methods = members
            .iter()
            .filter(|member| member.contains('(') && member.contains(')'))
            .count();
        let fields = members.len() - methods;
        let aggregate = fields > 0 && aggregate(name);
        let scalar = SCALAR.is_match(name);
        if !scalar && BigInt::from(methods) > thresholds.public_methods {
            add(
                matched.start(),
                "public_methods",
                name,
                json!(methods),
                integer_value(&thresholds.public_methods),
                "review-caller-roles-before-refining-api",
            );
        }
        if !aggregate && BigInt::from(fields) > thresholds.public_fields {
            add(
                matched.start(),
                "public_fields",
                name,
                json!(fields),
                integer_value(&thresholds.public_fields),
                "hide-mutable-state-behind-explicit-boundary",
            );
        }
        if !aggregate && fields > methods && fields > 0 {
            add(
                matched.start(),
                "state_heavy_public_surface",
                name,
                json!(fields),
                json!("public-behavior-boundary"),
                "avoid-carrying-members-that-can-be-owned-by-value-object-or-private-state",
            );
        }
    }
    for capture in FUNCTION.captures_iter(&text) {
        let matched = capture.get(0).unwrap();
        let name = &capture["name"];
        let Some(close) = closing(&text, matched.end() - 1) else {
            add(
                matched.start(),
                "syntax_error",
                name,
                json!("unmatched-brace"),
                json!("parseable-cpp"),
                "fix-cpp-brace-structure-before-readability-analysis",
            );
            continue;
        };
        let body = &text[matched.end()..close];
        let parameters = split_parameters(&capture["params"]);
        let names = parameters
            .iter()
            .filter_map(|parameter| {
                let parameter = parameter.split('=').next().unwrap_or(parameter).trim();
                let identifiers = IDENTIFIER.find_iter(parameter).collect::<Vec<_>>();
                if identifiers.len() < 2 {
                    return None;
                }
                let last = identifiers.last().unwrap();
                if !parameter[last.end()..].trim().is_empty()
                    || parameter[..last.start()].trim_end().ends_with("::")
                {
                    return None;
                }
                Some(last.as_str().to_owned())
            })
            .collect::<Vec<_>>();
        let nulls = ["==", "!="]
            .iter()
            .flat_map(|operator| {
                ["nullptr", "NULL"]
                    .iter()
                    .map(move |null| format!("{}\\s*{null}", regex::escape(operator)))
            })
            .map(|pattern| Regex::new(&pattern).unwrap().find_iter(body).count())
            .sum::<usize>();
        if nulls > 0 {
            add(
                matched.start(),
                "null_runtime_branch",
                name,
                json!(nulls),
                json!("typed-reference-or-variant-boundary"),
                "prefer-reference-optional-or-variant-boundary-over-null-driven-routing",
            );
        }
        let preceding = text[..matched.start()]
            .lines()
            .rev()
            .take(4)
            .collect::<Vec<_>>()
            .join("\n");
        let abi = name.starts_with("__nad_")
            || [
                "NATIVE_AD_AUGMENT",
                "NATIVE_AD_JVP",
                "NATIVE_AD_PRIMAL",
                "NATIVE_AD_VJP",
            ]
            .iter()
            .any(|marker| preceding.contains(marker));
        if BigInt::from(parameters.len()) > thresholds.parameters && !abi {
            add(
                matched.start(),
                "parameters",
                name,
                json!(parameters.len()),
                integer_value(&thresholds.parameters),
                "review-stable-input-domain-shape",
            );
        }
        let mut complexity = 0usize;
        let mut nesting = 0usize;
        for line in body.lines() {
            if BRANCH.is_match(line) {
                complexity += 1 + nesting;
            }
            complexity +=
                line.matches("&&").count() + line.matches("||").count() + line.matches('?').count();
            nesting += line.matches('{').count();
            nesting = nesting.saturating_sub(line.matches('}').count());
        }
        if BigInt::from(complexity) > thresholds.complexity {
            add(
                matched.start(),
                "cognitive_complexity",
                name,
                json!(complexity),
                integer_value(&thresholds.complexity),
                "review-branch-meaning-before-extraction",
            );
        }
        let statements = body
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
            .collect::<Vec<_>>();
        if statements.len() == 1 && statements[0].starts_with("return ") {
            let expression = statements[0]
                .trim_start_matches("return ")
                .trim()
                .trim_end_matches(';')
                .trim()
                .trim_start_matches('(')
                .trim_end_matches(')')
                .trim();
            if names.iter().any(|parameter| parameter == expression)
                && name != "apply_compile_bindings"
            {
                add(
                    matched.start(),
                    "identity_function",
                    name,
                    json!(format!("returns {expression}")),
                    json!("non-identity-domain-transform"),
                    "remove-wrapper-or-document-domain-contract",
                );
            }
            if !names.is_empty() {
                if let Some(call) = RETURN_CALL.captures(statements[0]) {
                    let callee = call[1].trim();
                    if !callee.chars().any(char::is_whitespace)
                        && ![
                            "static_cast",
                            "dynamic_cast",
                            "reinterpret_cast",
                            "const_cast",
                        ]
                        .iter()
                        .any(|prefix| callee.starts_with(prefix))
                    {
                        let forwarded = split_parameters(&call[2])
                            .into_iter()
                            .filter_map(|argument| {
                                let argument = argument.trim();
                                if names.iter().any(|name| name == argument) {
                                    return Some(argument.to_owned());
                                }
                                let wrapped = FORWARD.captures(argument)?;
                                names
                                    .iter()
                                    .find(|name| name.as_str() == &wrapped[1])
                                    .cloned()
                            })
                            .collect::<Vec<_>>();
                        if forwarded.len() == names.len()
                            && forwarded.iter().collect::<std::collections::BTreeSet<_>>()
                                == names.iter().collect()
                        {
                            add(
                                matched.start(),
                                "pass_through_function",
                                name,
                                json!(format!("{callee}/{}", forwarded.len())),
                                json!("adds-domain-or-adapter-contract"),
                                "inline-call-or-document-adapter-contract",
                            );
                        }
                    }
                }
            }
            if [
                "format",
                "render",
                "stringify",
                "to_string",
                "display",
                "label",
            ]
            .iter()
            .any(|part| name.to_lowercase().contains(part))
            {
                for marker in ["std::to_string", "std::format", "fmt::format"] {
                    if statements[0].contains(marker) {
                        add(
                            matched.start(),
                            "trivial_format_function",
                            name,
                            json!(marker),
                            json!("domain-presentation-contract"),
                            "inline-formatting-or-document-presentation-contract",
                        );
                        break;
                    }
                }
            }
        }
        let returns = VALUE_RETURN.is_match(body);
        let effects=[r"\bstd::(?:cout|cerr|clog)\s*<<",r"\b(?:printf|fprintf|system|popen|remove|rename)\s*\(",
            r"\b(?:std::print|fmt::print)\s*\(",r"\.\s*(?:open|close|flush|write)\s*\(",
            r"\bstd::filesystem::(?:copy|copy_file|create_directories|remove|remove_all|rename)\s*\(",r"\bstd::(?:ofstream|ifstream|fstream)\b"]
            .iter().any(|pattern|Regex::new(pattern).unwrap().is_match(body));
        let mutation=names.iter().any(|parameter|Regex::new(&format!(r"\b{}\s*(?:\.|->)\s*(?:append|assign|clear|emplace|emplace_back|emplace_front|erase|insert|pop|pop_back|pop_front|push|push_back|push_front|remove|resize|swap)\s*\(|\*\s*{}\s*=",regex::escape(parameter),regex::escape(parameter))).unwrap().is_match(body));
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
        .contains(&name)
            || [
                "append_", "build_", "emit_", "git_", "load_", "parse_", "read_", "resolve_",
                "run_", "write_",
            ]
            .iter()
            .any(|prefix| name.starts_with(prefix));
        if returns && (effects || mutation) && !adapter {
            add(
                matched.start(),
                "mixed_morphism_effect",
                name,
                json!("return+effect"),
                json!("pure-or-effect-boundary"),
                "separate-value-transform-from-io-or-mutation",
            );
        }
    }
    findings
}
