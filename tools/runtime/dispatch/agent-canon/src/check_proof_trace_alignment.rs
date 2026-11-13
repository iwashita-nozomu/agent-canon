// @dependency-start
// contract implementation
// responsibility Selects the retained dynamic trace and AST provider for the native proof alignment CLI.
// upstream implementation ../../../python-provider/src/proof_trace_alignment.rs owns proof contract and anchor checks
// downstream design ../../../../../documents/tools/check_proof_trace_alignment.md CLI contract
// @dependency-end

use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::resolve_long_option_prefix;
use std::path::Path;
use std::process::Command;

pub fn run(args: &[String]) -> i32 {
    const OPTIONS: &[(&str, usize)] = &[
        ("--root", 0),
        ("--trace-module", 1),
        ("--trace-symbol", 2),
        ("--format", 3),
        ("--help", 4),
    ];
    let mut values = [
        ".".to_owned(),
        String::new(),
        "FORMAL_PROOF_TRACE".to_owned(),
        "text".to_owned(),
    ];
    let mut trace_supplied = false;
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--" && index + 1 == args.len() {
            break;
        }
        let (key, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(key, value)| {
                (key, Some(value))
            });
        let field = if key == "-h" {
            4
        } else {
            match resolve_long_option_prefix(key, OPTIONS) {
                Ok(value) => value,
                Err(_) => {
                    eprintln!("unrecognized or ambiguous option: {key}");
                    return 2;
                }
            }
        };
        if field == 4 {
            println!("usage: agent-canon check-proof-trace-alignment --trace-module PATH [--root ROOT] [--trace-symbol NAME] [--format text|json]");
            return 0;
        }
        let value = if let Some(value) = inline {
            value.to_owned()
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                eprintln!("{key} requires a value");
                return 2;
            };
            value.clone()
        };
        values[field] = value;
        trace_supplied |= field == 1;
        index += 1;
    }
    if !trace_supplied || !["text", "json"].contains(&values[3].as_str()) {
        eprintln!("--trace-module is required and --format must be text or json");
        return 2;
    }
    let root = match resolve_non_strict(Path::new(&values[0])) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("{error}");
            return 1;
        }
    };
    let trace = match resolve_non_strict(Path::new(&values[1])) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("{error}");
            return 1;
        }
    };
    let provider = std::env::var_os("AGENT_CANON_PYTHON_PROVIDER")
        .unwrap_or_else(|| "agent-canon-python-provider".into());
    let mut command = Command::new(provider);
    command
        .arg("proof-trace-alignment")
        .arg(root)
        .arg(trace)
        .arg(&values[2])
        .arg(&values[3]);
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        eprintln!("proof trace provider unavailable: {}", command.exec());
        1
    }
    #[cfg(not(unix))]
    match command.status() {
        Ok(status) => status.code().unwrap_or(1),
        Err(error) => {
            eprintln!("proof trace provider unavailable: {error}");
            1
        }
    }
}
