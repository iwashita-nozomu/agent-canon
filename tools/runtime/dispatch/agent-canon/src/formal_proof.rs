// @dependency-start
// contract implementation
// responsibility Builds formal-proof scaffold plans and writes their retained runtime artifacts.
// upstream implementation python_ast.rs owns native source parsing utilities
// upstream implementation python-provider/src/proof_trace_alignment.rs owns safe CPython AST-unparse access
// upstream implementation lean_proof_env.rs owns the native Lean environment command contract
// upstream implementation runtime_boundary.rs owns external artifact writes
// downstream implementation main.rs exposes the formal-proof selector
// downstream test ../../../../../tests/agent_tools/test_formal_proof.py preserves the CLI and artifact contract
// @dependency-end

//! Native implementation of the formal-proof planning scaffold CLI.

use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::runtime_boundary::{RuntimeArtifactBoundary, RUNTIME_ROOT_ENV};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const SELECTOR: &str = "formal-proof";
const PROVIDER_ENV: &str = "AGENT_CANON_PYTHON_PROVIDER";
const TARGETS: &[(&str, &str, &str)] = &[
    ("lean", "lean", "Lean 4"),
    ("isabelle", "thy", "Isabelle/HOL"),
    ("coq", "v", "Coq/Rocq"),
    ("smt", "smt2", "SMT-LIB"),
];
const MAX_QUERY_WORDS: usize = 16;
const USAGE: &str = "usage: agent-canon formal-proof (--claim CLAIM | --claim-file CLAIM_FILE | --python-symbol PATH::QUALNAME) [--target {lean,isabelle,coq,smt}] [--domain DOMAIN] [--name NAME] [--out-dir OUT_DIR] [--runtime-root RUNTIME_ROOT] [--format {text,json,markdown}]";
const HELP: &str = "Create a formal-proof scaffold from a natural-language claim.\n\noptions:\n  -h, --help            show this help message and exit\n  --claim CLAIM         Natural-language mathematical claim.\n  --claim-file CLAIM_FILE\n                        Path to a natural-language claim file.\n  --python-symbol PATH::QUALNAME\n                        Python AST source in path.py::qualname form. The file is parsed with ast.parse and is not imported or executed.\n  --target {lean,isabelle,coq,smt}\n  --domain DOMAIN       Domain keyword. Repeatable.\n  --name NAME           Identifier for the theorem stub.\n  --out-dir OUT_DIR     Output directory, resolved below --runtime-root or AGENT_CANON_RUNTIME_ROOT.\n  --runtime-root RUNTIME_ROOT\n                        External runtime root used by checker environments.\n  --format {text,json,markdown}\n";

#[derive(Clone, Debug, Serialize)]
struct FormalProofPlan {
    status: String,
    target: String,
    target_label: String,
    claim_text: String,
    source_kind: String,
    source_path: Option<String>,
    source_symbol: Option<String>,
    source_summary: Option<String>,
    assumptions: Vec<String>,
    definitions: Vec<String>,
    theorem_target: String,
    proof_sketch: Vec<String>,
    proof_obligations: Vec<String>,
    existing_proof_queries: Vec<String>,
    literature_queries: Vec<String>,
    verification_commands: Vec<String>,
    theorem_stub_path: Option<String>,
    theorem_stub_name: Option<String>,
    library_trace_module_path: Option<String>,
    library_trace_module_name: Option<String>,
    origin_theorem_stub_path: Option<String>,
    origin_library_trace_module_path: Option<String>,
    trace_path_semantics: String,
    notes: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
struct PythonAstSource {
    path: String,
    qualname: String,
    node_kind: String,
    signature: String,
    docstring: Option<String>,
    lineno: usize,
    end_lineno: Option<usize>,
    branch_count: usize,
    return_expressions: Vec<String>,
    proof_obligations: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OptionName {
    Help,
    Claim,
    ClaimFile,
    PythonSymbol,
    Target,
    Domain,
    Name,
    OutDir,
    RuntimeRoot,
    Format,
}

#[derive(Default)]
struct Options {
    claim: Option<String>,
    claim_file: Option<PathBuf>,
    python_symbol: Option<String>,
    target: Option<String>,
    domains: Vec<String>,
    name: Option<String>,
    out_dir: Option<PathBuf>,
    runtime_root: Option<PathBuf>,
    format: Option<String>,
}

enum ParsedOptions {
    Help,
    Run(Box<Options>),
}

const CLI_OPTIONS: &[(&str, OptionName)] = &[
    ("--help", OptionName::Help),
    ("--claim", OptionName::Claim),
    ("--claim-file", OptionName::ClaimFile),
    ("--python-symbol", OptionName::PythonSymbol),
    ("--target", OptionName::Target),
    ("--domain", OptionName::Domain),
    ("--name", OptionName::Name),
    ("--out-dir", OptionName::OutDir),
    ("--runtime-root", OptionName::RuntimeRoot),
    ("--format", OptionName::Format),
];

fn parse_args(args: &[String]) -> Result<ParsedOptions, String> {
    let mut options = Options::default();
    let mut source_count = 0usize;
    let mut index = 0usize;
    while index < args.len() {
        let token = &args[index];
        if token == "-h" {
            return Ok(ParsedOptions::Help);
        }
        let (name, inline) = token
            .split_once('=')
            .map_or((token.as_str(), None), |(name, value)| (name, Some(value)));
        let option = if name == "-h" {
            OptionName::Help
        } else {
            resolve_long_option_prefix(name, CLI_OPTIONS).map_err(|error| match error {
                LongOptionError::Unrecognized => format!("unrecognized arguments: {name}"),
                LongOptionError::Ambiguous(values) => {
                    format!("ambiguous option: {name} could match {}", values.join(", "))
                }
            })?
        };
        if option == OptionName::Help {
            if inline.is_some() {
                return Err(format!(
                    "argument --help: ignored explicit argument '{token}'"
                ));
            }
            return Ok(ParsedOptions::Help);
        }
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            args.get(index)
                .filter(|value| !value.starts_with('-'))
                .cloned()
                .ok_or_else(|| format!("argument {name}: expected one argument"))?
        };
        match option {
            OptionName::Claim => {
                source_count += 1;
                options.claim = Some(value);
            }
            OptionName::ClaimFile => {
                source_count += 1;
                options.claim_file = Some(PathBuf::from(value));
            }
            OptionName::PythonSymbol => {
                source_count += 1;
                options.python_symbol = Some(value);
            }
            OptionName::Target => options.target = Some(value),
            OptionName::Domain => options.domains.push(value),
            OptionName::Name => options.name = Some(value),
            OptionName::OutDir => options.out_dir = Some(PathBuf::from(value)),
            OptionName::RuntimeRoot => options.runtime_root = Some(PathBuf::from(value)),
            OptionName::Format => options.format = Some(value),
            OptionName::Help => unreachable!(),
        }
        index += 1;
    }
    if source_count == 0 {
        return Err("one of the arguments --claim --claim-file --python-symbol is required".into());
    }
    if source_count > 1 {
        return Err("argument --claim-file: not allowed with argument --claim".into());
    }
    let target = options.target.as_deref().unwrap_or("lean");
    if !TARGETS.iter().any(|(value, _, _)| *value == target) {
        return Err(format!(
            "argument --target: invalid choice: '{target}' (choose from 'lean', 'isabelle', 'coq', 'smt')"
        ));
    }
    let format = options.format.as_deref().unwrap_or("text");
    if !["text", "json", "markdown"].contains(&format) {
        return Err(format!(
            "argument --format: invalid choice: '{format}' (choose from 'text', 'json', 'markdown')"
        ));
    }
    Ok(ParsedOptions::Run(Box::new(options)))
}

fn compact_space(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn normalize_identifier(raw: &str) -> String {
    let mut value = String::new();
    let mut underscore = false;
    for character in raw.trim().chars() {
        if character.is_ascii_alphanumeric() || character == '_' {
            value.push(character.to_ascii_lowercase());
            underscore = false;
        } else if !underscore && !value.is_empty() {
            value.push('_');
            underscore = true;
        }
    }
    let value = value.trim_matches('_').to_owned();
    if value.is_empty() {
        return "generated_claim".into();
    }
    if value.as_bytes()[0].is_ascii_digit() {
        format!("claim_{value}")
    } else {
        value
    }
}

fn read_claim(options: &Options) -> Result<String, String> {
    if let Some(path) = options.claim_file.as_ref() {
        let text =
            fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
        return Ok(crate::python_text::python_strip(&text).to_owned());
    }
    Ok(options
        .claim
        .as_deref()
        .map(crate::python_text::python_strip)
        .unwrap_or_default()
        .to_owned())
}

fn extract_python_source(reference: &str, root: &Path) -> Result<PythonAstSource, String> {
    let (raw_path, raw_qualname) = reference
        .split_once("::")
        .ok_or_else(|| "--python-symbol must use path.py::qualname syntax".to_owned())?;
    let path = raw_path.trim();
    let qualname = raw_qualname.trim();
    if path.is_empty() {
        return Err("--python-symbol path is empty".into());
    }
    if qualname.is_empty() {
        return Err("--python-symbol qualname is empty".into());
    }
    let provider =
        env::var_os(PROVIDER_ENV).unwrap_or_else(|| "agent-canon-python-provider".into());
    let output = Command::new(&provider)
        .arg("proof-source")
        .arg(path)
        .arg(qualname)
        .arg(root)
        .current_dir(root)
        .output()
        .map_err(|error| format!("Python AST provider unavailable: {error}"))?;
    let value: Value = serde_json::from_slice(&output.stdout).map_err(|error| {
        format!(
            "Python AST provider returned invalid JSON (exit {}): {error}",
            output.status.code().unwrap_or(1)
        )
    })?;
    if !output.status.success() || value.get("status").and_then(Value::as_str) == Some("fail") {
        return Err(value
            .get("error")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .unwrap_or_else(|| String::from_utf8_lossy(&output.stderr).trim().to_owned()));
    }
    serde_json::from_value(value)
        .map_err(|error| format!("Python AST provider result does not match its schema: {error}"))
}

fn build_claim_from_python_ast(source: &PythonAstSource) -> String {
    let claim = source
        .docstring
        .as_deref()
        .map(compact_space)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| {
            format!(
                "Formalize the extracted Python AST behavior of {}.",
                source.qualname
            )
        });
    let return_expressions = if source.return_expressions.is_empty() {
        "<none>".to_owned()
    } else {
        source.return_expressions.join("; ")
    };
    format!(
        "Definitions: Python AST source {}::{}\n- Node kind: {}\n- Signature: {}\n- Lines: {}-{}\n- Branch nodes: {}\n- Return expressions: {}\nClaim: {}\nProof sketch: Translate the parsed AST into target-language semantics,\nthen discharge the extracted branch and return-expression obligations.",
        source.path,
        source.qualname,
        source.node_kind,
        source.signature,
        source.lineno,
        source.end_lineno.unwrap_or(source.lineno),
        source.branch_count,
        return_expressions,
        claim
    )
}

fn parse_sections(claim_text: &str) -> BTreeMap<String, Vec<String>> {
    const ALIASES: &[(&str, &str)] = &[
        ("assumptions", "assumptions"),
        ("assumption", "assumptions"),
        ("given", "assumptions"),
        ("hypotheses", "assumptions"),
        ("definitions", "definitions"),
        ("definition", "definitions"),
        ("defs", "definitions"),
        ("claim", "target"),
        ("target", "target"),
        ("theorem", "target"),
        ("goal", "target"),
        ("proof", "proof_sketch"),
        ("proof sketch", "proof_sketch"),
        ("sketch", "proof_sketch"),
    ];
    let pattern = regex::Regex::new(r"^\s*([A-Za-z][A-Za-z _-]{0,40})\s*:\s*(.*)$")
        .expect("formal proof section regex is valid");
    let mut sections = BTreeMap::from([
        ("assumptions".to_owned(), Vec::new()),
        ("definitions".to_owned(), Vec::new()),
        ("target".to_owned(), Vec::new()),
        ("proof_sketch".to_owned(), Vec::new()),
    ]);
    let mut current = "target".to_owned();
    let mut saw_explicit_target = false;
    for raw_line in claim_text.lines() {
        let line = crate::python_text::python_strip(raw_line);
        if line.is_empty() {
            continue;
        }
        if let Some(captures) = pattern.captures(line) {
            let label = captures
                .get(1)
                .map(|value| value.as_str())
                .unwrap_or_default()
                .trim()
                .to_ascii_lowercase()
                .replace('-', " ");
            if let Some((_, section)) = ALIASES.iter().find(|(alias, _)| *alias == label) {
                current = (*section).to_owned();
                if current == "target" {
                    saw_explicit_target = true;
                }
                append_section(&mut sections, &current, captures.get(2).unwrap().as_str());
                continue;
            }
        }
        let stripped =
            line.trim_start_matches(|ch: char| matches!(ch, '-' | '*' | '.' | ' ' | '0'..='9'));
        append_section(&mut sections, &current, stripped);
    }
    if !saw_explicit_target {
        let target = sections.get_mut("target").unwrap();
        if target.len() > 1 {
            let rest = target.split_off(1);
            sections.get_mut("proof_sketch").unwrap().extend(rest);
        }
    }
    sections
}

fn append_section(sections: &mut BTreeMap<String, Vec<String>>, section: &str, value: &str) {
    let value = crate::python_text::python_strip(value);
    if !value.is_empty() {
        sections
            .entry(section.to_owned())
            .or_default()
            .push(value.to_owned());
    }
}

fn words(value: &str) -> Vec<String> {
    regex::Regex::new(r"[A-Za-z][A-Za-z0-9_'-]*")
        .expect("proof query word regex is valid")
        .find_iter(value)
        .map(|word| word.as_str().to_owned())
        .collect()
}

fn query_terms(claim_text: &str, domains: &[String]) -> String {
    const STOP_WORDS: &[&str] = &["the", "and", "for", "with", "that", "then", "from", "there"];
    let mut values = Vec::new();
    for source in domains.iter().map(String::as_str).chain([claim_text]) {
        for word in words(source) {
            let lowered = word.to_ascii_lowercase();
            if lowered.len() <= 2 || STOP_WORDS.contains(&lowered.as_str()) {
                continue;
            }
            if !values.contains(&word) {
                values.push(word);
            }
        }
    }
    if values.is_empty() {
        compact_space(claim_text).chars().take(120).collect()
    } else {
        values
            .into_iter()
            .take(MAX_QUERY_WORDS)
            .collect::<Vec<_>>()
            .join(" ")
    }
}

fn existing_proof_queries(claim_text: &str, domains: &[String], target: &str) -> Vec<String> {
    let terms = query_terms(claim_text, domains);
    let natural = compact_space(claim_text);
    let mut queries = vec![
        format!("\"{natural}\" formal proof"),
        format!("\"{natural}\" theorem proof"),
        format!("{terms} Lean mathlib"),
        format!("{terms} site:leanprover-community.github.io/mathlib4_docs"),
        format!("{terms} LeanSearch mathlib"),
        format!("{terms} Loogle mathlib"),
        format!("{terms} Isabelle AFP"),
        format!("{terms} Coq Rocq theorem"),
    ];
    let insertion = match target {
        "isabelle" => Some(format!("{terms} Isabelle Sledgehammer AFP")),
        "coq" => Some(format!("{terms} CoqHammer Coq Rocq")),
        "smt" => Some(format!("{terms} SMT-LIB Z3 cvc5")),
        _ => None,
    };
    if let Some(query) = insertion {
        queries.insert(2, query);
    }
    let mut deduped = Vec::new();
    for query in queries {
        if !query.trim().is_empty() && !deduped.contains(&query) {
            deduped.push(query);
        }
    }
    deduped
}

fn literature_queries(claim_text: &str, domains: &[String]) -> Vec<String> {
    let terms = query_terms(claim_text, domains);
    vec![
        format!("{terms} proof paper"),
        format!("{terms} theorem survey"),
        format!("{terms} formalization Lean Isabelle Coq"),
        format!("{terms} counterexample assumptions"),
    ]
}

fn build_obligations(sections: &BTreeMap<String, Vec<String>>) -> Vec<String> {
    let mut obligations = Vec::new();
    let definitions = sections
        .get("definitions")
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if definitions.is_empty() {
        obligations.push(
            "Define all mathematical objects and notation in the target proof assistant.".into(),
        );
    }
    for assumption in sections.get("assumptions").into_iter().flatten() {
        obligations.push(format!("Formalize assumption: {assumption}"));
    }
    let target = sections
        .get("target")
        .into_iter()
        .flatten()
        .cloned()
        .collect::<Vec<_>>()
        .join(" ");
    if !target.is_empty() {
        obligations.push(format!("Formalize theorem target: {target}"));
    }
    if !sections
        .get("proof_sketch")
        .map(Vec::is_empty)
        .unwrap_or(true)
    {
        obligations.push("Split the informal proof sketch into assistant-checkable lemmas.".into());
    }
    obligations.extend([
        "Search existing formal libraries before proving new lemmas.".into(),
        "Run the target proof assistant and record the checker log.".into(),
        "When a fragment is checked, register it in the package-retained proof trace and record remaining implementation-instantiation obligations as explicit proof boundaries.".into(),
    ]);
    obligations
}

fn target_info(target: &str) -> (&'static str, &'static str) {
    TARGETS
        .iter()
        .find_map(|(name, extension, label)| (*name == target).then_some((*extension, *label)))
        .expect("target was validated by argument parsing")
}

fn shell_quote(value: &str) -> String {
    crate::lean_proof_env::shell_join(&[value.to_owned()])
}

fn verification_commands(stub_path: &str, target: &str, runtime_root: Option<&str>) -> Vec<String> {
    match target {
        "lean" => {
            let env_dir = runtime_root.map_or_else(
                || "${AGENT_CANON_RUNTIME_ROOT}/tasks/formal-proof/lean-proof-env".to_owned(),
                |runtime| {
                    shell_quote(
                        &Path::new(runtime)
                            .expanduser()
                            .join("tasks/formal-proof/lean-proof-env")
                            .to_string_lossy(),
                    )
                },
            );
            vec![format!(
                "tools/bin/agent-canon lean-proof-env check-file --env-dir {env_dir} --lean-file {} --execute",
                shell_quote(stub_path)
            )]
        }
        "isabelle" => vec![format!("isabelle process -T GeneratedClaim {stub_path}")],
        "coq" => vec![format!("coqc {stub_path}")],
        _ => vec![
            format!("z3 -smt2 {stub_path}"),
            format!("cvc5 --lang smt2 {stub_path}"),
        ],
    }
}

trait ExpandUserPath {
    fn expanduser(&self) -> PathBuf;
}

impl ExpandUserPath for Path {
    fn expanduser(&self) -> PathBuf {
        let Some(value) = self.to_str() else {
            return self.to_path_buf();
        };
        if value == "~" {
            return env::var_os("HOME")
                .map(PathBuf::from)
                .unwrap_or_else(|| self.to_path_buf());
        }
        if let Some(suffix) = value.strip_prefix("~/") {
            return env::var_os("HOME")
                .map(PathBuf::from)
                .map(|home| home.join(suffix))
                .unwrap_or_else(|| self.to_path_buf());
        }
        self.to_path_buf()
    }
}

fn build_plan(
    claim_text: &str,
    target: &str,
    domains: &[String],
    name: &str,
    source: Option<&PythonAstSource>,
    runtime_root: Option<&str>,
) -> FormalProofPlan {
    let sections = parse_sections(claim_text);
    let theorem_target = sections
        .get("target")
        .into_iter()
        .flatten()
        .cloned()
        .collect::<Vec<_>>()
        .join(" ");
    let theorem_target = if theorem_target.is_empty() {
        compact_space(claim_text)
    } else {
        theorem_target
    };
    let verification_stub = format!(
        "<out-dir>/{}.{}",
        normalize_identifier(name),
        target_info(target).0
    );
    let mut obligations = source
        .map(|source| source.proof_obligations.clone())
        .unwrap_or_default();
    obligations.extend(build_obligations(&sections));
    FormalProofPlan {
        status: "scaffold_only_unverified".into(),
        target: target.into(),
        target_label: target_info(target).1.into(),
        claim_text: claim_text.into(),
        source_kind: if source.is_some() {
            "python_ast"
        } else {
            "natural_language"
        }
        .into(),
        source_path: source.map(|source| source.path.clone()),
        source_symbol: source.map(|source| source.qualname.clone()),
        source_summary: source.map(|source| source.signature.clone()),
        assumptions: sections.get("assumptions").cloned().unwrap_or_default(),
        definitions: sections.get("definitions").cloned().unwrap_or_default(),
        theorem_target,
        proof_sketch: sections.get("proof_sketch").cloned().unwrap_or_default(),
        proof_obligations: obligations,
        existing_proof_queries: existing_proof_queries(claim_text, domains, target),
        literature_queries: literature_queries(claim_text, domains),
        verification_commands: verification_commands(&verification_stub, target, runtime_root),
        theorem_stub_path: None,
        theorem_stub_name: None,
        library_trace_module_path: None,
        library_trace_module_name: None,
        origin_theorem_stub_path: None,
        origin_library_trace_module_path: None,
        trace_path_semantics:
            "No library trace module has been written. Paths are scaffold-generation context."
                .into(),
        notes: vec![
            "This scaffold is not proof evidence.".into(),
            "Use $literature-survey before new formalization when the claim may already exist."
                .into(),
            "Only a successful proof-assistant checker log can upgrade proof_status to verified."
                .into(),
        ],
    }
}

fn comment_block(prefix: &str, text: &str) -> String {
    crate::python_text::python_splitlines(text)
        .into_iter()
        .map(|line| {
            if line.is_empty() {
                prefix.to_owned()
            } else {
                format!("{prefix} {line}")
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn indent_nonempty(text: &str, prefix: &str) -> Vec<String> {
    crate::python_text::python_splitlines(text)
        .into_iter()
        .map(|line| {
            if line.trim().is_empty() {
                line.to_owned()
            } else {
                format!("{prefix}{line}")
            }
        })
        .collect()
}

fn build_stub(target: &str, name: &str, plan: &FormalProofPlan) -> String {
    let safe_name = normalize_identifier(name);
    match target {
        "lean" => {
            let mut lines = vec![
                "import Mathlib".to_owned(),
                "import Aesop".to_owned(),
                String::new(),
                "/-".to_owned(),
                "Formal proof scaffold generated by agent-canon formal-proof.".to_owned(),
                "This file is not proof evidence until <FORMAL_TARGET> is replaced".to_owned(),
                "and the checker command succeeds without sorry/admit/placeholders.".to_owned(),
                String::new(),
                "Natural-language claim:".to_owned(),
            ];
            lines.extend(indent_nonempty(&plan.claim_text, "  "));
            lines.extend([
                "-/".to_owned(),
                String::new(),
                format!("theorem {safe_name} : <FORMAL_TARGET> := by"),
                "  -- TODO: replace this scaffold with a checked proof.".to_owned(),
                "  sorry".to_owned(),
                String::new(),
            ]);
            lines.join("\n")
        }
        "isabelle" => {
            let mut lines = vec![
                "theory GeneratedClaim".to_owned(),
                "  imports Main".to_owned(),
                "begin".to_owned(),
                String::new(),
                "(*".to_owned(),
                "Formal proof scaffold generated by agent-canon formal-proof.".to_owned(),
                "This file is not proof evidence until <FORMAL_TARGET> is replaced".to_owned(),
                "and Isabelle checks a proof without sorry/placeholders.".to_owned(),
                String::new(),
                "   Natural-language claim:".to_owned(),
            ];
            lines.extend(
                crate::python_text::python_splitlines(&plan.claim_text)
                    .into_iter()
                    .map(|line| format!("   {line}")),
            );
            lines.extend([
                "*)".to_owned(),
                String::new(),
                format!("theorem {safe_name}:"),
                "  \"<FORMAL_TARGET>\"".to_owned(),
                "  sorry".to_owned(),
                String::new(),
                "end".to_owned(),
                String::new(),
            ]);
            lines.join("\n")
        }
        "coq" => {
            let mut lines = vec![
                "(*".to_owned(),
                "Formal proof scaffold generated by agent-canon formal-proof.".to_owned(),
                "This file is not proof evidence until <FORMAL_TARGET> is replaced".to_owned(),
                "and Coq/Rocq checks a proof without Admitted/placeholders.".to_owned(),
                String::new(),
                "Natural-language claim:".to_owned(),
            ];
            lines.extend(
                crate::python_text::python_splitlines(&plan.claim_text)
                    .into_iter()
                    .map(str::to_owned),
            );
            lines.extend([
                "*)".to_owned(),
                String::new(),
                format!("Theorem {safe_name} : <FORMAL_TARGET>."),
                "Proof.".to_owned(),
                "  (* TODO: replace this scaffold with a checked proof. *)".to_owned(),
                "Admitted.".to_owned(),
                String::new(),
            ]);
            lines.join("\n")
        }
        _ => {
            let mut lines = vec![
                "; Formal proof scaffold generated by agent-canon formal-proof.".to_owned(),
                "; This file is not proof evidence until assertions are formalized".to_owned(),
                "; and an SMT solver returns unsat/sat as expected for the encoded obligation."
                    .to_owned(),
            ];
            lines.extend(
                comment_block(";", &plan.claim_text)
                    .lines()
                    .map(str::to_owned),
            );
            lines.extend([
                String::new(),
                "(set-logic ALL)".to_owned(),
                "; TODO: declare symbols and assert the negated theorem.".to_owned(),
                "; (check-sat)".to_owned(),
                String::new(),
            ]);
            lines.join("\n")
        }
    }
}

fn render_markdown(plan: &FormalProofPlan) -> String {
    let mut lines = vec![
        "# Formal Proof Plan".to_owned(),
        String::new(),
        format!("- status: `{}`", plan.status),
        format!("- target: `{}`", plan.target_label),
        format!(
            "- theorem_stub_path: `{}`",
            plan.theorem_stub_path.as_deref().unwrap_or("<not-written>")
        ),
        format!(
            "- theorem_stub_name: `{}`",
            plan.theorem_stub_name.as_deref().unwrap_or("<not-written>")
        ),
        format!(
            "- library_trace_module_path: `{}`",
            plan.library_trace_module_path
                .as_deref()
                .unwrap_or("<not-written>")
        ),
        format!(
            "- library_trace_module_name: `{}`",
            plan.library_trace_module_name
                .as_deref()
                .unwrap_or("<not-written>")
        ),
        format!("- source_kind: `{}`", plan.source_kind),
        format!(
            "- source_path: `{}`",
            plan.source_path.as_deref().unwrap_or("<none>")
        ),
        format!(
            "- source_symbol: `{}`",
            plan.source_symbol.as_deref().unwrap_or("<none>")
        ),
        format!("- trace_path_semantics: `{}`", plan.trace_path_semantics),
        String::new(),
        "## Claim".to_owned(),
        String::new(),
        plan.claim_text.clone(),
        String::new(),
        "## Source Summary".to_owned(),
        String::new(),
        plan.source_summary
            .as_deref()
            .unwrap_or("<none>")
            .to_owned(),
        String::new(),
        "## Assumptions".to_owned(),
        String::new(),
    ];
    lines.extend(
        plan.assumptions
            .iter()
            .map(|item| format!("- {item}"))
            .chain((plan.assumptions.is_empty()).then(|| "- <none parsed>".to_owned())),
    );
    lines.extend([String::new(), "## Definitions".into(), String::new()]);
    lines.extend(
        plan.definitions
            .iter()
            .map(|item| format!("- {item}"))
            .chain((plan.definitions.is_empty()).then(|| "- <none parsed>".to_owned())),
    );
    for (title, values, code) in [
        ("Proof Obligations", &plan.proof_obligations, false),
        ("Existing Proof Queries", &plan.existing_proof_queries, true),
        ("Literature Queries", &plan.literature_queries, true),
        ("Verification Commands", &plan.verification_commands, true),
        ("Notes", &plan.notes, false),
    ] {
        lines.extend([String::new(), format!("## {title}"), String::new()]);
        lines.extend(values.iter().map(|value| {
            if code {
                format!("- `{value}`")
            } else {
                format!("- {value}")
            }
        }));
    }
    lines.join("\n") + "\n"
}

fn render_text(plan: &FormalProofPlan) -> String {
    let mut lines = vec![
        format!("FORMAL_PROOF_STATUS={}", plan.status),
        format!("FORMAL_PROOF_TARGET={}", plan.target),
        format!(
            "FORMAL_PROOF_STUB={}",
            plan.theorem_stub_path.as_deref().unwrap_or("<not-written>")
        ),
        format!(
            "FORMAL_PROOF_LIBRARY_TRACE_MODULE={}",
            plan.library_trace_module_path
                .as_deref()
                .unwrap_or("<not-written>")
        ),
        format!(
            "FORMAL_PROOF_LIBRARY_TRACE_MODULE_NAME={}",
            plan.library_trace_module_name
                .as_deref()
                .unwrap_or("<not-written>")
        ),
        format!("FORMAL_PROOF_SOURCE_KIND={}", plan.source_kind),
    ];
    if let Some(path) = plan.source_path.as_deref() {
        lines.push(format!("FORMAL_PROOF_SOURCE_PATH={path}"));
    }
    if let Some(symbol) = plan.source_symbol.as_deref() {
        lines.push(format!("FORMAL_PROOF_SOURCE_SYMBOL={symbol}"));
    }
    lines.extend(
        plan.existing_proof_queries
            .iter()
            .map(|value| format!("FORMAL_PROOF_EXISTING_QUERY={value}")),
    );
    lines.extend(
        plan.literature_queries
            .iter()
            .map(|value| format!("FORMAL_PROOF_LITERATURE_QUERY={value}")),
    );
    lines.extend(
        plan.verification_commands
            .iter()
            .map(|value| format!("FORMAL_PROOF_VERIFY={value}")),
    );
    lines.join("\n") + "\n"
}

fn json_ensure_ascii(value: &Value) -> Result<String, String> {
    let encoded = serde_json::to_string_pretty(value)
        .map_err(|error| format!("serialize formal proof plan: {error}"))?;
    let mut output = String::with_capacity(encoded.len());
    for character in encoded.chars() {
        if character as u32 <= 0x7f {
            output.push(character);
        } else if character as u32 <= 0xffff {
            output.push_str(&format!("\\u{:04x}", character as u32));
        } else {
            let value = character as u32 - 0x10000;
            let high = 0xd800 + (value >> 10);
            let low = 0xdc00 + (value & 0x3ff);
            output.push_str(&format!("\\u{high:04x}\\u{low:04x}"));
        }
    }
    Ok(output)
}

fn python_repr(value: &str) -> String {
    let mut output = String::from("'");
    for character in value.chars() {
        match character {
            '\\' => output.push_str("\\\\"),
            '\'' => output.push_str("\\'"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character.is_control() => {
                output.push_str(&format!("\\x{:02x}", character as u32));
            }
            character => output.push(character),
        }
    }
    output.push('\'');
    output
}

fn build_library_trace_module(plan: &FormalProofPlan) -> Result<String, String> {
    let trace_json =
        json_ensure_ascii(&serde_json::to_value(plan).map_err(|error| error.to_string())?)?;
    let literal = python_repr(&trace_json);
    Ok([
        "\"\"\"Generated formal-proof trace for Python package distribution.".to_owned(),
        String::new(),
        "This module is provenance and planning evidence only. It is not proof".to_owned(),
        "evidence until the checker command recorded in FORMAL_PROOF_TRACE succeeds".to_owned(),
        "on a completed artifact without placeholders or unchecked proof escapes.".to_owned(),
        "\"\"\"".to_owned(),
        String::new(),
        "from __future__ import annotations".to_owned(),
        String::new(),
        "import json".to_owned(),
        "from pathlib import Path".to_owned(),
        "from typing import Any".to_owned(),
        String::new(),
        format!("FORMAL_PROOF_TRACE_JSON = {literal}"),
        "FORMAL_PROOF_TRACE: dict[str, Any] = json.loads(FORMAL_PROOF_TRACE_JSON)".to_owned(),
        "_TRACE_MODULE_PATH = Path(__file__).resolve()".to_owned(),
        "_ORIGIN_LIBRARY_TRACE_MODULE_PATH = FORMAL_PROOF_TRACE.get(".to_owned(),
        "    \"library_trace_module_path\"".to_owned(),
        ")".to_owned(),
        "_ORIGIN_THEOREM_STUB_PATH = FORMAL_PROOF_TRACE.get(\"theorem_stub_path\")".to_owned(),
        "FORMAL_PROOF_TRACE[\"origin_library_trace_module_path\"] = (".to_owned(),
        "    _ORIGIN_LIBRARY_TRACE_MODULE_PATH".to_owned(),
        ")".to_owned(),
        "FORMAL_PROOF_TRACE[\"origin_theorem_stub_path\"] = _ORIGIN_THEOREM_STUB_PATH".to_owned(),
        "FORMAL_PROOF_TRACE[\"library_trace_module_path\"] = _TRACE_MODULE_PATH.as_posix()"
            .to_owned(),
        "FORMAL_PROOF_TRACE[\"library_trace_module_name\"] = _TRACE_MODULE_PATH.name".to_owned(),
        "_THEOREM_STUB_NAME = FORMAL_PROOF_TRACE.get(\"theorem_stub_name\")".to_owned(),
        "if isinstance(_THEOREM_STUB_NAME, str):".to_owned(),
        "    FORMAL_PROOF_TRACE[\"runtime_theorem_stub_candidate_path\"] = (".to_owned(),
        "        _TRACE_MODULE_PATH.parent / _THEOREM_STUB_NAME".to_owned(),
        "    ).as_posix()".to_owned(),
        "FORMAL_PROOF_TRACE[\"trace_path_semantics\"] = (".to_owned(),
        "    \"library_trace_module_path is computed from this installed module's \"".to_owned(),
        "    \"__file__; origin_* fields preserve generation-context paths.\"".to_owned(),
        ")".to_owned(),
        String::new(),
    ]
    .join("\n"))
}

fn path_relative_to(path: &Path, root: &Path) -> String {
    let resolved_path =
        crate::path_resolution::resolve_non_strict(path).unwrap_or_else(|_| path.to_path_buf());
    let resolved_root =
        crate::path_resolution::resolve_non_strict(root).unwrap_or_else(|_| root.to_path_buf());
    resolved_path
        .strip_prefix(&resolved_root)
        .map(|value| value.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().into_owned())
}

fn resolve_output_dir(
    output_dir: &Path,
    runtime_root: Option<&Path>,
    source_root: &Path,
) -> Result<(PathBuf, RuntimeArtifactBoundary), String> {
    if runtime_root.is_none()
        && env::var_os(RUNTIME_ROOT_ENV)
            .filter(|value| !value.is_empty())
            .is_none()
    {
        return Err(format!(
            "explicit runtime root required for --out-dir; pass --runtime-root or set {RUNTIME_ROOT_ENV}"
        ));
    }
    let boundary = RuntimeArtifactBoundary::for_source(source_root, runtime_root, true)?;
    let destination = boundary.resolve(output_dir)?;
    let relative = destination.strip_prefix(boundary.root()).map_err(|_| {
        format!(
            "output path escapes runtime root: {}",
            destination.display()
        )
    })?;
    boundary.ensure_directory(relative)?;
    Ok((destination, boundary))
}

fn validate_runtime_root(source_root: &Path, requested: &Path) -> Result<PathBuf, String> {
    let probe = RuntimeArtifactBoundary::resolve_read_path(
        source_root,
        Some(requested),
        Path::new(".formal-proof-runtime-root-probe"),
    )?;
    probe
        .parent()
        .map(Path::to_path_buf)
        .ok_or_else(|| format!("runtime root is unavailable: {}", requested.display()))
}

fn write_outputs(
    plan: &FormalProofPlan,
    output_dir: &Path,
    name: &str,
    runtime_root: Option<&Path>,
    source_root: &Path,
) -> Result<FormalProofPlan, String> {
    let (output_dir, boundary) = resolve_output_dir(output_dir, runtime_root, source_root)?;
    let safe_name = normalize_identifier(name);
    let extension = target_info(&plan.target).0;
    let theorem_path = output_dir.join(format!("{safe_name}.{extension}"));
    let trace_path = output_dir.join(format!("{safe_name}_proof_trace.py"));
    let theorem_relative = path_relative_to(
        &theorem_path,
        &env::current_dir().map_err(|e| e.to_string())?,
    );
    let trace_relative =
        path_relative_to(&trace_path, &env::current_dir().map_err(|e| e.to_string())?);
    let mut written = plan.clone();
    written.theorem_stub_path = Some(theorem_relative.clone());
    written.theorem_stub_name = Some(
        theorem_path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned(),
    );
    written.library_trace_module_path = Some(trace_relative.clone());
    written.library_trace_module_name = Some(
        trace_path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned(),
    );
    written.origin_theorem_stub_path = Some(theorem_relative);
    written.origin_library_trace_module_path = Some(trace_relative);
    written.trace_path_semantics = "library_trace_module_path is generation-context until the generated trace module is imported; the module rewrites that field from __file__ and keeps origin_* paths for generation provenance.".into();
    written.verification_commands = verification_commands(
        written.theorem_stub_path.as_deref().unwrap_or_default(),
        &written.target,
        runtime_root.map(|path| path.to_string_lossy()).as_deref(),
    );
    let write = |path: &Path, content: &str| -> Result<(), String> {
        let relative = path
            .strip_prefix(boundary.root())
            .map_err(|_| format!("output path escapes runtime root: {}", path.display()))?;
        boundary.atomic_write_text(relative, content, 0o600)?;
        Ok(())
    };
    write(&theorem_path, &build_stub(&plan.target, name, &written))?;
    write(&trace_path, &build_library_trace_module(&written)?)?;
    let plan_json =
        json_ensure_ascii(&serde_json::to_value(&written).map_err(|error| error.to_string())?)?
            + "\n";
    write(&output_dir.join("formal_proof_plan.json"), &plan_json)?;
    write(
        &output_dir.join("formal_proof_plan.md"),
        &render_markdown(&written),
    )?;
    write(
        &output_dir.join("existing_proof_queries.txt"),
        &(written.existing_proof_queries.join("\n") + "\n"),
    )?;
    write(
        &output_dir.join("literature_queries.txt"),
        &(written.literature_queries.join("\n") + "\n"),
    )?;
    Ok(written)
}

pub fn run(args: &[String]) -> i32 {
    let options = match parse_args(args) {
        Ok(ParsedOptions::Help) => {
            print!("{HELP}");
            return 0;
        }
        Ok(ParsedOptions::Run(options)) => options,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let current_dir = match env::current_dir() {
        Ok(path) => path,
        Err(error) => {
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let runtime_root = if let Some(requested) = options.runtime_root.as_deref() {
        match validate_runtime_root(&current_dir, requested) {
            Ok(root) => Some(root),
            Err(error) => {
                eprintln!("{USAGE}");
                eprintln!("agent-canon {SELECTOR}: error: runtime_root_error: {error}");
                return 2;
            }
        }
    } else {
        None
    };
    let domains = options
        .domains
        .iter()
        .map(|domain| compact_space(domain))
        .filter(|domain| !domain.is_empty())
        .collect::<Vec<_>>();
    let (claim_text, source) = if let Some(reference) = options.python_symbol.as_deref() {
        match extract_python_source(reference, &current_dir) {
            Ok(source) => {
                let claim = build_claim_from_python_ast(&source);
                (claim, Some(source))
            }
            Err(error) => {
                eprintln!("{USAGE}");
                eprintln!("agent-canon {SELECTOR}: error: {error}");
                return 2;
            }
        }
    } else {
        match read_claim(&options) {
            Ok(claim) => (claim, None),
            Err(error) => {
                eprintln!("{USAGE}");
                eprintln!("agent-canon {SELECTOR}: error: {error}");
                return 2;
            }
        }
    };
    let target = options.target.as_deref().unwrap_or("lean");
    let name = options
        .name
        .as_deref()
        .map(str::to_owned)
        .or_else(|| {
            source
                .as_ref()
                .map(|source| normalize_identifier(&source.qualname))
        })
        .unwrap_or_else(|| "generated_claim".into());
    let mut plan = build_plan(
        &claim_text,
        target,
        &domains,
        &name,
        source.as_ref(),
        runtime_root
            .as_deref()
            .map(|path| path.to_string_lossy())
            .as_deref(),
    );
    if let Some(output_dir) = options.out_dir.as_deref() {
        match write_outputs(
            &plan,
            output_dir,
            &name,
            runtime_root.as_deref(),
            &current_dir,
        ) {
            Ok(written) => plan = written,
            Err(error) => {
                eprintln!("{USAGE}");
                eprintln!("agent-canon {SELECTOR}: error: runtime_root_error: {error}");
                return 2;
            }
        }
    }
    match options.format.as_deref().unwrap_or("text") {
        "json" => match serde_json::to_value(&plan)
            .map_err(|error| error.to_string())
            .and_then(|value| json_ensure_ascii(&value))
        {
            Ok(value) => println!("{value}"),
            Err(error) => {
                eprintln!("agent-canon {SELECTOR}: error: {error}");
                return 1;
            }
        },
        "markdown" => print!("{}", render_markdown(&plan)),
        _ => print!("{}", render_text(&plan)),
    }
    0
}
