// @dependency-start
// contract implementation
// responsibility Expands one C++ source root into a retained canonical record and Lean evidence module.
// upstream implementation cpp_source_canonical_ir.rs extracts the C++ source envelope
// upstream implementation operational_ir_to_lean.rs enforces complete coverage and renders Lean evidence
// downstream implementation main.rs exposes cpp-template-to-lean
// downstream test ../../../../../tests/agent_tools/test_cpp_template_to_lean.py preserves the full-expansion route
// @dependency-end

//! Canonical C++ source-to-Lean composition command.

use crate::cpp_source_canonical_ir::build_cpp_source_canonical_ir;
use crate::operational_ir_to_lean::{render_envelope, validate_namespace};
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

pub const SELECTOR: &str = "cpp-template-to-lean";
const USAGE: &str = "usage: agent-canon cpp-template-to-lean [--root ROOT] --cpp-symbol PATH::QUALNAME --namespace NAMESPACE [--module-name MODULE] [--out OUT] [--record-out RECORD_OUT]";

#[derive(Default)]
struct Args {
    root: Option<PathBuf>,
    cpp_symbol: Option<String>,
    namespace: Option<String>,
    module_name: Option<String>,
    out: Option<PathBuf>,
    record_out: Option<PathBuf>,
}

enum ParseResult {
    Help,
    Run(Args),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OptionName {
    Root,
    Symbol,
    Namespace,
    ModuleName,
    Out,
    RecordOut,
    Help,
}
const OPTIONS: &[(&str, OptionName)] = &[
    ("--root", OptionName::Root),
    ("--cpp-symbol", OptionName::Symbol),
    ("--namespace", OptionName::Namespace),
    ("--module-name", OptionName::ModuleName),
    ("--out", OptionName::Out),
    ("--record-out", OptionName::RecordOut),
    ("--help", OptionName::Help),
];

fn parse_args(argv: &[String]) -> Result<ParseResult, String> {
    let mut args = Args::default();
    let mut index = 0;
    while index < argv.len() {
        let token = &argv[index];
        if token == "-h" {
            return Ok(ParseResult::Help);
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
        if option == OptionName::Help {
            if inline.is_some() {
                return Err(format!(
                    "argument --help: ignored explicit argument '{token}'"
                ));
            }
            return Ok(ParseResult::Help);
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
            OptionName::Root => args.root = Some(value.into()),
            OptionName::Symbol => args.cpp_symbol = Some(value),
            OptionName::Namespace => args.namespace = Some(value),
            OptionName::ModuleName => args.module_name = Some(value),
            OptionName::Out => args.out = Some(value.into()),
            OptionName::RecordOut => args.record_out = Some(value.into()),
            OptionName::Help => unreachable!(),
        }
        index += 1;
    }
    if args.cpp_symbol.is_none() {
        return Err("the following arguments are required: --cpp-symbol".into());
    }
    if args.namespace.is_none() {
        return Err("the following arguments are required: --namespace".into());
    }
    Ok(ParseResult::Run(args))
}

fn write_text(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    }
    fs::write(path, text).map_err(|error| format!("cannot write {}: {error}", path.display()))
}
fn write_record(path: &Path, record: &Value) -> Result<(), String> {
    let text = serde_json::to_string_pretty(record).map_err(|error| error.to_string())? + "\n";
    write_text(path, &text)
}

pub fn run(argv: &[String]) -> i32 {
    let args = match parse_args(argv) {
        Ok(ParseResult::Help) => {
            println!("{USAGE}");
            return 0;
        }
        Ok(ParseResult::Run(args)) => args,
        Err(error) => {
            eprintln!("{USAGE}");
            eprintln!("agent-canon {SELECTOR}: error: {error}");
            return 2;
        }
    };
    let result = (|| -> Result<(), String> {
        let namespace = args.namespace.as_deref().expect("required namespace");
        validate_namespace(namespace)?;
        let root = args.root.as_deref().unwrap_or(Path::new("."));
        let record = build_cpp_source_canonical_ir(
            args.cpp_symbol.as_deref().expect("required symbol"),
            root,
        )?;
        if let Some(record_path) = args.record_out.as_deref() {
            write_record(record_path, &record)?;
        }
        let rendered = render_envelope(&record, namespace, args.module_name.as_deref())?;
        if let Some(output) = args.out.as_deref() {
            write_text(output, &rendered)?;
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
