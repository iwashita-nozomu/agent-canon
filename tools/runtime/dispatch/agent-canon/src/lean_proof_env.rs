// @dependency-start
// contract implementation
// responsibility Runs native Lake setup and Lean proof, interface, and counterexample checks without interpreting diagnostic text as success.
// upstream design ../../../../../agents/skills/formal-proof-workflow.md owns proof workflow selection
// upstream implementation path_resolution.rs resolves selected environment and Lean file paths
// downstream design ../../../../../documents/tools/lean_proof_env.md documents the CLI and native configuration boundary
// downstream test ../tests/lean_proof_env_native.rs validates the shared API
// downstream implementation ../../../../../tests/agent_tools/test_lean_proof_env.py validates the selected native CLI
// @dependency-end

use serde::Serialize;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};

use crate::path_resolution::resolve_non_strict;

pub const SELECTOR: &str = "lean-proof-env";
pub const DEFAULT_PACKAGE_NAME: &str = "agent_canon_lean_proof_env";

const ACTIONS: &[&str] = &[
    "init",
    "smoke",
    "agent-smoke",
    "counterexample-smoke",
    "all-smoke",
    "check-file",
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LeanProofEnvArgs {
    pub action: String,
    pub env_dir: PathBuf,
    pub lean_toolchain: Option<String>,
    pub package_name: String,
    pub lean_file: Option<PathBuf>,
    pub execute: bool,
    pub format: OutputFormat,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OutputFormat {
    Text,
    Json,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CommandResult {
    pub command: String,
    pub returncode: i32,
    pub stdout: String,
    pub stderr: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct LeanProofEnvResult {
    pub action: String,
    pub status: String,
    pub env_dir: String,
    pub created_or_updated_files: Vec<String>,
    pub commands: Vec<String>,
    pub executed: bool,
    pub command_results: Vec<CommandResult>,
    pub lean_file: Option<String>,
    pub lean_toolchain: Option<String>,
    pub lake_version: Option<String>,
    pub lean_version: Option<String>,
    pub lake_manifest: Option<String>,
    pub mathlib_revision: Option<String>,
}

#[derive(Debug, PartialEq, Eq)]
enum ParseOutcome {
    Help,
    Run(LeanProofEnvArgs),
}

/// Run the existing action-oriented Lean proof environment command.
pub fn run(args: &[String]) -> i32 {
    let parsed = match parse_args(args) {
        Ok(ParseOutcome::Help) => {
            println!("{}", help_text());
            return 0;
        }
        Ok(ParseOutcome::Run(parsed)) => parsed,
        Err(message) => {
            eprintln!("agent-canon {SELECTOR}: {message}");
            eprintln!("{}", usage());
            return 2;
        }
    };

    let result = match build_result(&parsed) {
        Ok(result) => result,
        Err(error) => {
            eprintln!("LEAN_PROOF_ENV_ERROR={error}");
            return 2;
        }
    };
    match parsed.format {
        OutputFormat::Json => println!(
            "{}",
            serde_json::to_string_pretty(&result)
                .expect("Lean proof environment result serializes to JSON")
        ),
        OutputFormat::Text => println!("{}", render_text(&result)),
    }
    result
        .command_results
        .iter()
        .find(|item| item.returncode != 0)
        .map_or(0, |item| item.returncode)
}

/// Plan or execute the selected native Lake and Lean operations.
pub fn build_result(args: &LeanProofEnvArgs) -> Result<LeanProofEnvResult, String> {
    let env_dir = resolve_non_strict(&args.env_dir)?;
    if args.action == "check-file" && args.lean_file.is_none() {
        return Err("--lean-file is required for check-file".to_owned());
    }

    let configured = ["lakefile.lean", "lakefile.toml"]
        .iter()
        .any(|name| env_dir.join(*name).is_file());
    let toolchain_file = env_dir.join("lean-toolchain");
    let declared_toolchain = if toolchain_file.is_file() {
        Some(
            read_text(&toolchain_file)
                .map_err(|error| error.to_string())?
                .trim()
                .to_owned(),
        )
        .filter(|value| !value.is_empty())
    } else {
        None
    };
    let requested_toolchain = args.lean_toolchain.as_deref().unwrap_or_default().trim();
    let requested_toolchain = (!requested_toolchain.is_empty()).then_some(requested_toolchain);

    if !configured && env_dir.exists() {
        let mut has_foreign_content = false;
        for entry in fs::read_dir(&env_dir).map_err(|error| error.to_string())? {
            let entry = entry.map_err(|error| error.to_string())?;
            if entry.file_name().to_string_lossy().as_ref() != "lean-toolchain" {
                has_foreign_content = true;
                break;
            }
        }
        if has_foreign_content {
            return Err(format!(
                "Choose an empty directory, a toolchain-only directory, or an existing Lake package: {}",
                env_dir.display()
            ));
        }
    }
    if let (Some(declared), Some(requested)) = (declared_toolchain.as_deref(), requested_toolchain)
    {
        if declared != requested {
            return Err(format!(
                "--lean-toolchain does not match the project declaration in {}",
                toolchain_file.display()
            ));
        }
    }
    let selected_toolchain = requested_toolchain.or(declared_toolchain.as_deref());
    let Some(selected_toolchain) = selected_toolchain else {
        return Err(
            "Select an exact Lean toolchain with --lean-toolchain or a project lean-toolchain file."
                .to_owned(),
        );
    };

    let mut probes: Vec<(PathBuf, String)> = Vec::new();
    if matches!(args.action.as_str(), "smoke" | "all-smoke") {
        probes.push((
            env_dir.join("AgentCanonLeanProofEnvSmoke.lean"),
            smoke_text().to_owned(),
        ));
    }
    if matches!(args.action.as_str(), "agent-smoke" | "all-smoke") {
        probes.push((
            env_dir.join("AgentCanonLeanProofEnvAgent.lean"),
            agent_smoke_text().to_owned(),
        ));
    }
    if matches!(args.action.as_str(), "counterexample-smoke" | "all-smoke") {
        probes.push((
            env_dir.join("AgentCanonLeanProofEnvCounterexample.lean"),
            counterexample_text().to_owned(),
        ));
    }
    let mut lean_files: Vec<PathBuf> = probes.iter().map(|(path, _)| path.clone()).collect();
    if args.action == "check-file" {
        let path = args
            .lean_file
            .as_deref()
            .expect("check-file path was validated above");
        lean_files.push(resolve_non_strict(path)?);
    }

    let lake = vec!["lake".to_owned(), format!("+{selected_toolchain}")];
    let mut commands: Vec<Vec<String>> = Vec::new();
    if !configured {
        commands.push(
            [
                lake.clone(),
                vec![
                    "init".to_owned(),
                    args.package_name.clone(),
                    "math".to_owned(),
                ],
            ]
            .concat(),
        );
    }
    commands.push([lake.clone(), vec!["--version".to_owned()]].concat());
    commands.push(
        [
            lake.clone(),
            vec![
                "--keep-toolchain".to_owned(),
                "env".to_owned(),
                "lean".to_owned(),
                "--version".to_owned(),
            ],
        ]
        .concat(),
    );
    if !lean_files.is_empty() {
        commands.push(
            [
                lake.clone(),
                vec!["--keep-toolchain".to_owned(), "build".to_owned()],
            ]
            .concat(),
        );
        for path in &lean_files {
            commands.push(
                [
                    lake.clone(),
                    vec![
                        "--keep-toolchain".to_owned(),
                        "env".to_owned(),
                        "lean".to_owned(),
                        path.to_string_lossy().into_owned(),
                    ],
                ]
                .concat(),
            );
        }
    }

    let mut command_results = Vec::new();
    let mut created_or_updated_files = Vec::new();
    let mut status = "dry_run";
    if args.execute {
        fs::create_dir_all(&env_dir).map_err(|error| error.to_string())?;
        for command in &commands {
            if let Some((path, text)) = probes.iter().find(|(path, _)| {
                let path_text = path.to_string_lossy();
                command
                    .last()
                    .is_some_and(|last| last.as_str() == path_text.as_ref())
            }) {
                if write_generated(path, text).map_err(|error| error.to_string())? {
                    created_or_updated_files.push(path.to_string_lossy().into_owned());
                }
            }
            let result = run_command(command, &env_dir).map_err(|error| error.to_string())?;
            let failed = result.returncode != 0;
            command_results.push(result);
            if failed {
                status = "failed";
                break;
            }
        }
        if status != "failed" {
            status = if lean_files.is_empty() {
                "initialized"
            } else {
                "checked"
            };
        }
    }

    let manifest = env_dir.join("lake-manifest.json");
    let lean_toolchain = read_text(&toolchain_file)
        .ok()
        .map(|value| value.trim().to_owned());
    let lake_version = commands
        .iter()
        .zip(&command_results)
        .find(|(command, result)| {
            command
                .last()
                .is_some_and(|last| last.as_str() == "--version")
                && command
                    .get(1)
                    .is_some_and(|value| value.strip_prefix('+') == Some(selected_toolchain))
                && result.returncode == 0
        })
        .map(|(_, result)| result.stdout.trim().to_owned());
    let lean_version = commands
        .iter()
        .zip(&command_results)
        .find(|(command, result)| {
            command.len() >= 3
                && command[command.len() - 3].as_str() == "env"
                && command[command.len() - 2].as_str() == "lean"
                && command[command.len() - 1].as_str() == "--version"
                && result.returncode == 0
        })
        .map(|(_, result)| result.stdout.trim().to_owned());

    Ok(LeanProofEnvResult {
        action: args.action.clone(),
        status: status.to_owned(),
        env_dir: env_dir.to_string_lossy().into_owned(),
        created_or_updated_files,
        commands: commands.iter().map(|command| shell_join(command)).collect(),
        executed: args.execute,
        command_results,
        lean_file: lean_files
            .last()
            .map(|path| path.to_string_lossy().into_owned()),
        lean_toolchain,
        lake_version,
        lean_version,
        lake_manifest: manifest
            .is_file()
            .then(|| manifest.to_string_lossy().into_owned()),
        mathlib_revision: manifest_mathlib_revision(&manifest),
    })
}

/// Render native command results in the stable text format used by proof workflows.
pub fn render_text(result: &LeanProofEnvResult) -> String {
    let mut lines = vec![
        format!("LEAN_PROOF_ENV_ACTION={}", result.action),
        format!("LEAN_PROOF_ENV_STATUS={}", result.status),
        format!("LEAN_PROOF_ENV_DIR={}", result.env_dir),
        format!(
            "LEAN_PROOF_ENV_EXECUTED={}",
            if result.executed { "yes" } else { "no" }
        ),
    ];
    for (key, value) in [
        ("LEAN_PROOF_ENV_TOOLCHAIN", result.lean_toolchain.as_deref()),
        (
            "LEAN_PROOF_ENV_LAKE_VERSION",
            result.lake_version.as_deref(),
        ),
        (
            "LEAN_PROOF_ENV_LEAN_VERSION",
            result.lean_version.as_deref(),
        ),
        (
            "LEAN_PROOF_ENV_LAKE_MANIFEST",
            result.lake_manifest.as_deref(),
        ),
        (
            "LEAN_PROOF_ENV_MATHLIB_REVISION",
            result.mathlib_revision.as_deref(),
        ),
    ] {
        if let Some(value) = value {
            lines.push(format!("{key}={value}"));
        }
    }
    lines.extend(result.commands.iter().map(|command| format!("  {command}")));
    for command in &result.command_results {
        lines.push(format!(
            "LEAN_PROOF_ENV_COMMAND_RESULT={} {}",
            command.returncode, command.command
        ));
        lines.push(command.stdout.clone());
        lines.push(command.stderr.clone());
    }
    lines.join("\n")
}

/// Return the fixed smoke source used to exercise proof search and Plausible.
pub fn smoke_text() -> &'static str {
    r#"import Mathlib
import Aesop
import Plausible

namespace AgentCanonLeanProofEnvSmoke

theorem aesop_relation_composition
    {P Q R S : Prop} (hP : P) (hPQ : P -> Q)
    (hQR : Q -> R) (hRS : R -> S) : S := by
  aesop

theorem mathlib_nat_order_example {a b c : Nat}
    (hab : a <= b) (hbc : b <= c) : a <= c := by
  exact Nat.le_trans hab hbc

theorem omega_index_example {i j k : Int}
    (hij : i <= j) (hjk : j <= k) : i <= k := by
  omega

theorem linarith_budget_example {a b c : Real}
    (hab : a <= b) (hbc : b <= c) : a <= c := by
  linarith

theorem grind_symmetry_example {a b : Nat} (h : a = b) : b = a := by
  grind

#eval Plausible.Testable.check (forall (xs : Array Nat), xs.size = xs.size)

end AgentCanonLeanProofEnvSmoke
"#
}

/// Return the fixed smoke source for the LeanSearchClient public import surface.
pub fn agent_smoke_text() -> &'static str {
    r#"import LeanSearchClient

namespace AgentCanonLeanProofEnvAgent

set_option leansearchclient.backend "leansearch"

#check LeanSearchClient.SearchResult
#check LeanSearchClient.SearchServer
#check LeanSearchClient.leanSearchServer

theorem leansearchclient_import_surface_ready : True := by
  trivial

end AgentCanonLeanProofEnvAgent
"#
}

/// Return the fixed counterexample source guarded by Lean's expected diagnostic.
pub fn counterexample_text() -> &'static str {
    r#"import Plausible

namespace AgentCanonLeanProofEnvCounterexample

/-- error: Found a counter-example! -/
#guard_msgs in
#eval Plausible.Testable.check (forall (n : Nat), n < n) { quiet := true }

end AgentCanonLeanProofEnvCounterexample
"#
}

fn parse_args(args: &[String]) -> Result<ParseOutcome, String> {
    if args
        .iter()
        .any(|argument| matches!(argument.as_str(), "-h" | "--help"))
    {
        return Ok(ParseOutcome::Help);
    }
    let mut action: Option<String> = None;
    let mut env_dir = None;
    let mut lean_toolchain = None;
    let mut package_name = DEFAULT_PACKAGE_NAME.to_owned();
    let mut lean_file = None;
    let mut execute = false;
    let mut format = OutputFormat::Text;
    let mut index = 0;
    while index < args.len() {
        let argument = &args[index];
        if let Some(value) = argument.strip_prefix("--env-dir=") {
            env_dir = Some(PathBuf::from(value));
        } else if let Some(value) = argument.strip_prefix("--lean-toolchain=") {
            lean_toolchain = Some(value.to_owned());
        } else if let Some(value) = argument.strip_prefix("--package-name=") {
            package_name = value.to_owned();
        } else if let Some(value) = argument.strip_prefix("--lean-file=") {
            lean_file = Some(PathBuf::from(value));
        } else if let Some(value) = argument.strip_prefix("--format=") {
            format = parse_format(value)?;
        } else if matches!(
            argument.as_str(),
            "--env-dir" | "--lean-toolchain" | "--package-name" | "--lean-file" | "--format"
        ) {
            let option = argument.as_str();
            index += 1;
            let Some(value) = args.get(index) else {
                return Err(format!("argument {option}: expected one argument"));
            };
            if value.starts_with('-') {
                return Err(format!("argument {option}: expected one argument"));
            }
            match option {
                "--env-dir" => env_dir = Some(PathBuf::from(value)),
                "--lean-toolchain" => lean_toolchain = Some(value.clone()),
                "--package-name" => package_name = value.clone(),
                "--lean-file" => lean_file = Some(PathBuf::from(value)),
                "--format" => format = parse_format(value)?,
                _ => unreachable!("option is from the recognized set"),
            }
        } else if argument == "--execute" {
            execute = true;
        } else if argument.starts_with('-') {
            return Err(format!("unrecognized arguments: {argument}"));
        } else if action.is_none() {
            if !ACTIONS.contains(&argument.as_str()) {
                return Err(format!(
                    "argument action: invalid choice: '{argument}' (choose from {})",
                    ACTIONS
                        .iter()
                        .map(|value| format!("'{value}'"))
                        .collect::<Vec<_>>()
                        .join(", ")
                ));
            }
            action = Some(argument.clone());
        } else {
            return Err(format!("unrecognized arguments: {argument}"));
        }
        index += 1;
    }
    let action = action.ok_or_else(|| "the following arguments are required: action".to_owned())?;
    let env_dir =
        env_dir.ok_or_else(|| "the following arguments are required: --env-dir".to_owned())?;
    Ok(ParseOutcome::Run(LeanProofEnvArgs {
        action,
        env_dir,
        lean_toolchain,
        package_name,
        lean_file,
        execute,
        format,
    }))
}

fn parse_format(value: &str) -> Result<OutputFormat, String> {
    match value {
        "text" => Ok(OutputFormat::Text),
        "json" => Ok(OutputFormat::Json),
        _ => Err(format!(
            "argument --format: invalid choice: '{value}' (choose from 'text', 'json')"
        )),
    }
}

fn usage() -> &'static str {
    "usage: agent-canon lean-proof-env [-h] --env-dir ENV_DIR [--lean-toolchain LEAN_TOOLCHAIN] [--package-name PACKAGE_NAME] [--lean-file LEAN_FILE] [--execute] [--format {text,json}] {init,smoke,agent-smoke,counterexample-smoke,all-smoke,check-file}"
}

fn help_text() -> String {
    format!(
        "{}\n\nCreate or check a reusable Lean package through Lake's native interface.\n\npositional arguments:\n  action                {}\n\noptions:\n  -h, --help            show this help message and exit\n  --env-dir ENV_DIR     Selected Lake package directory.\n  --lean-toolchain LEAN_TOOLCHAIN\n                        Exact Lean toolchain to select when the package has no declaration.\n  --package-name PACKAGE_NAME\n  --lean-file LEAN_FILE\n                        File to check for the check-file action.\n  --execute             Execute the printed native commands; otherwise make no changes.\n  --format {{text,json}}",
        usage(),
        ACTIONS.join(" ")
    )
}

fn write_generated(path: &Path, text: &str) -> io::Result<bool> {
    if fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_symlink())
        .unwrap_or(false)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!(
                "Refusing to write a probe through a symlink: {}",
                path.display()
            ),
        ));
    }
    if path.exists() {
        let existing = read_text(path)?;
        if existing != text {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!(
                    "Refusing to overwrite non-matching probe: {}",
                    path.display()
                ),
            ));
        }
        return Ok(false);
    }
    fs::write(path, text)?;
    Ok(true)
}

fn run_command(parts: &[String], cwd: &Path) -> io::Result<CommandResult> {
    let Some((program, arguments)) = parts.split_first() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "native command must not be empty",
        ));
    };
    let output = Command::new(program)
        .args(arguments)
        .current_dir(cwd)
        .output()?;
    Ok(CommandResult {
        command: shell_join(parts),
        returncode: process_returncode(output.status),
        stdout: normalize_text_output(
            String::from_utf8(output.stdout)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?,
        ),
        stderr: normalize_text_output(
            String::from_utf8(output.stderr)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?,
        ),
    })
}

fn process_returncode(status: ExitStatus) -> i32 {
    if let Some(code) = status.code() {
        return code;
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        return status.signal().map_or(1, |signal| -signal);
    }
    #[cfg(not(unix))]
    {
        1
    }
}

fn normalize_text_output(text: String) -> String {
    text.replace("\r\n", "\n").replace('\r', "\n")
}

fn manifest_mathlib_revision(path: &Path) -> Option<String> {
    if !path.is_file() {
        return None;
    }
    let manifest: serde_json::Value = serde_json::from_str(&read_text(path).ok()?).ok()?;
    let packages = manifest.as_object()?.get("packages")?.as_array()?;
    for package in packages {
        let Some(package) = package.as_object() else {
            continue;
        };
        if package.get("name").and_then(serde_json::Value::as_str) == Some("mathlib") {
            return package
                .get("rev")
                .and_then(serde_json::Value::as_str)
                .map(str::to_owned);
        }
    }
    None
}

fn read_text(path: &Path) -> io::Result<String> {
    fs::read_to_string(path)
}

fn shell_join(parts: &[String]) -> String {
    parts
        .iter()
        .map(|part| shell_quote(part))
        .collect::<Vec<_>>()
        .join(" ")
}

fn shell_quote(value: &str) -> String {
    if !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_@%+=:,./-".contains(&byte))
    {
        return value.to_owned();
    }
    if value.is_empty() {
        return "''".to_owned();
    }
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

#[cfg(test)]
mod tests {
    use super::{counterexample_text, run_command, shell_join, write_generated};
    use std::fs;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    struct TempRoot(PathBuf);

    impl TempRoot {
        fn new() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock after epoch")
                .as_nanos();
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!(
                "agent-canon-lean-proof-env-{}-{sequence}-{nonce}",
                std::process::id()
            ));
            fs::create_dir_all(&root).expect("temporary test root is created");
            Self(root)
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn counterexample_probe_contains_the_independent_guarded_property() {
        let source = counterexample_text();
        assert!(source.contains("/-- error: Found a counter-example! -/\n#guard_msgs in\n#eval"));
        assert!(source.contains("forall (n : Nat), n < n"));
        assert!(source.contains("quiet := true"));
        assert!(source.contains("import Plausible"));
    }

    #[test]
    fn probe_writes_preserve_content_and_refuse_replacement_or_symlinks() {
        let root = TempRoot::new();
        let source = root.0.join("probe.lean");
        fs::write(&source, "user-owned\n").expect("fixture source written");
        assert!(write_generated(&source, "replacement\n")
            .unwrap_err()
            .to_string()
            .contains("non-matching"));
        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            let link = root.0.join("link.lean");
            symlink(&source, &link).expect("fixture symlink created");
            assert!(write_generated(&link, "replacement\n")
                .unwrap_err()
                .to_string()
                .contains("symlink"));
        }
        assert_eq!(fs::read_to_string(&source).unwrap(), "user-owned\n");
        assert!(!write_generated(&source, "user-owned\n").unwrap());
    }

    #[test]
    fn shell_command_rendering_keeps_paths_as_single_quoted_arguments() {
        assert_eq!(
            shell_join(&[
                "lake".to_owned(),
                "--keep-toolchain".to_owned(),
                "env".to_owned(),
                "lean".to_owned(),
                "/tmp/proof with spaces.lean".to_owned(),
            ]),
            "lake --keep-toolchain env lean '/tmp/proof with spaces.lean'"
        );
        assert_eq!(
            shell_join(&["lake".to_owned(), "don't".to_owned()]),
            "lake 'don'\"'\"'t'"
        );
    }

    #[cfg(unix)]
    #[test]
    fn native_command_status_wins_over_counterexample_diagnostic_text() {
        let root = TempRoot::new();
        for returncode in [0, 1, 17, -9] {
            let script = if returncode == -9 {
                "printf '%s\\n' 'Found a counter-example!'; printf '%s\\n' 'unrelated type error' >&2; kill -9 $$"
            } else {
                "printf '%s\\n' 'Found a counter-example!'; printf '%s\\n' 'unrelated type error' >&2; exit $1"
            };
            let mut command = vec!["sh".to_owned(), "-c".to_owned(), script.to_owned()];
            if returncode != -9 {
                command.extend(["sh".to_owned(), returncode.to_string()]);
            }
            let result = run_command(&command, &root.0).expect("native shell provider exits");
            assert_eq!(result.returncode, returncode);
            assert_eq!(result.stdout, "Found a counter-example!\n");
            assert_eq!(result.stderr, "unrelated type error\n");
        }
    }
}
