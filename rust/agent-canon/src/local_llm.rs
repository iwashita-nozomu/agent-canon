// @dependency-start
// responsibility Provides Rust-native local LLM CLI routing and single-file responsibility review.
// upstream design ../../../documents/local-llm-responsibility-analysis.md local LLM responsibility boundary
// upstream design ../../../documents/search-coordination.md coordinated search provider contract
// upstream design ../../../documents/rust-agent-tool-migration.md Rust CLI migration policy
// downstream design ../../../agent-canon-environment.toml records local LLM CLI environment commands
// downstream design ../../../tools/catalog.yaml catalogs this Rust CLI surface
// downstream design ../../../tools/README.md documents root tool entrypoints
// downstream design ../../../documents/tools/README.md documents reader-facing tool entrypoints
// downstream implementation ../../../tools/agent_tools/file_responsibility_llm.py remains the Python compatibility prompt helper
// downstream implementation ../../../tools/agent_tools/search.py coordinates purpose-based search
// downstream implementation ../../../tools/agent_tools/search_index.py builds local LLM search cards
// downstream implementation ../../../tools/agent_tools/local_llm_eval.py validates local LLM eval cases
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// downstream implementation ../../../tools/ci/run_all_checks.sh runs this CLI in local CI
// downstream implementation ../../../.github/workflows/agent-canon-static-gates.yml runs this CLI in GitHub static gates
// @dependency-end

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

const DEFAULT_MODEL: &str = "ggml-org/SmolLM3-3B-GGUF:Q4_K_M";
const DEFAULT_MAX_BYTES: usize = 24_000;
const DEFAULT_PREDICT_TOKENS: usize = 768;
const PROMPT_DIGEST_LENGTH: usize = 12;

#[derive(Debug, Clone, PartialEq, Eq)]
enum LocalLlmCommand {
    ClassifyResponsibility,
    Search,
    BuildIndex,
    Eval,
    Help,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct LocalLlmArgs {
    command: LocalLlmCommand,
    root: PathBuf,
    passthrough: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PythonInvocation {
    script: PathBuf,
    args: Vec<String>,
}

pub fn run(args: &[String]) -> i32 {
    match LocalLlmArgs::parse(args) {
        Ok(parsed) => {
            if parsed.command == LocalLlmCommand::Help {
                print_usage();
                return 0;
            }
            run_invocation(&parsed)
        }
        Err(message) => {
            eprintln!("LOCAL_LLM_CLI=fail");
            eprintln!("LOCAL_LLM_CLI_ERROR={message}");
            print_usage();
            2
        }
    }
}

impl LocalLlmArgs {
    fn parse(args: &[String]) -> Result<Self, String> {
        let Some(raw_command) = args.first() else {
            return Ok(Self {
                command: LocalLlmCommand::Help,
                root: PathBuf::from("."),
                passthrough: Vec::new(),
            });
        };
        if raw_command == "--help" || raw_command == "-h" || raw_command == "help" {
            return Ok(Self {
                command: LocalLlmCommand::Help,
                root: PathBuf::from("."),
                passthrough: Vec::new(),
            });
        }
        let command = match raw_command.as_str() {
            "classify-responsibility" | "review-file" => LocalLlmCommand::ClassifyResponsibility,
            "search" => LocalLlmCommand::Search,
            "build-index" | "index" => LocalLlmCommand::BuildIndex,
            "eval" => LocalLlmCommand::Eval,
            unknown => return Err(format!("unknown local-llm command {unknown}")),
        };
        let passthrough = args[1..].to_vec();
        let root = extract_root(&passthrough).unwrap_or_else(|| PathBuf::from("."));
        Ok(Self {
            command,
            root,
            passthrough,
        })
    }

    fn has_root_argument(&self) -> bool {
        has_option_value(&self.passthrough, "--root")
    }
}

fn run_invocation(args: &LocalLlmArgs) -> i32 {
    if args.command == LocalLlmCommand::ClassifyResponsibility {
        return run_classify_responsibility(args);
    }
    let Ok(invocation) = build_invocation(args) else {
        eprintln!("LOCAL_LLM_CLI=fail");
        eprintln!("LOCAL_LLM_CLI_ERROR=python-engine-not-found");
        return 1;
    };
    let python = env::var("AGENT_CANON_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let status = Command::new(python)
        .arg(invocation.script)
        .args(invocation.args)
        .status();
    match status {
        Ok(code) => code.code().unwrap_or(1),
        Err(error) => {
            eprintln!("LOCAL_LLM_CLI=fail");
            eprintln!("LOCAL_LLM_CLI_ERROR=python-launch-failed:{error}");
            1
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ClassifyArgs {
    root: PathBuf,
    file: String,
    model: String,
    llama_cli: String,
    max_bytes: usize,
    predict_tokens: usize,
    print_prompt: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ReviewTarget {
    root: PathBuf,
    path: PathBuf,
    relative_path: String,
    text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct LlamaCommand {
    executable: String,
    model: String,
    prompt: String,
    predict_tokens: usize,
}

impl ClassifyArgs {
    fn parse(root: PathBuf, args: &[String]) -> Result<Self, String> {
        let mut parsed = Self {
            root,
            file: String::new(),
            model: env::var("AGENT_CANON_LOCAL_LLM_MODEL")
                .unwrap_or_else(|_| DEFAULT_MODEL.to_string()),
            llama_cli: env::var("AGENT_CANON_LLAMA_CLI").unwrap_or_default(),
            max_bytes: DEFAULT_MAX_BYTES,
            predict_tokens: DEFAULT_PREDICT_TOKENS,
            print_prompt: false,
        };
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    parsed.root = value_path(args, index, "--root")?;
                    index += 2;
                }
                "--model" => {
                    parsed.model = value_string(args, index, "--model")?;
                    index += 2;
                }
                "--llama-cli" => {
                    parsed.llama_cli = value_string(args, index, "--llama-cli")?;
                    index += 2;
                }
                "--max-bytes" => {
                    parsed.max_bytes = parse_usize(args, index, "--max-bytes")?;
                    index += 2;
                }
                "--predict-tokens" => {
                    parsed.predict_tokens = parse_usize(args, index, "--predict-tokens")?;
                    index += 2;
                }
                "--print-prompt" => {
                    parsed.print_prompt = true;
                    index += 1;
                }
                unknown if unknown.starts_with('-') => {
                    return Err(format!("unknown argument {unknown}"))
                }
                file => {
                    if !parsed.file.is_empty() {
                        return Err("exactly-one-file-required".to_string());
                    }
                    parsed.file = file.to_string();
                    index += 1;
                }
            }
        }
        if parsed.file.is_empty() {
            return Err("file-required".to_string());
        }
        Ok(parsed)
    }
}

impl LlamaCommand {
    fn args(&self) -> Vec<String> {
        vec![
            "-hf".to_string(),
            self.model.clone(),
            "-p".to_string(),
            self.prompt.clone(),
            "-n".to_string(),
            self.predict_tokens.to_string(),
            "--temp".to_string(),
            "0.1".to_string(),
        ]
    }
}

fn run_classify_responsibility(args: &LocalLlmArgs) -> i32 {
    let parsed = match ClassifyArgs::parse(args.root.clone(), &args.passthrough) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("FILE_RESP_LLM_ERROR={message}");
            return 2;
        }
    };
    let target = match read_target(&parsed.root, &parsed.file, parsed.max_bytes) {
        Ok(target) => target,
        Err(message) => {
            eprintln!("FILE_RESP_LLM_ERROR={message}");
            return 2;
        }
    };
    let prompt = prompt_for_target(&target);
    let digest = prompt_digest(&prompt);
    if parsed.print_prompt {
        print_file_status(&target, &parsed.model, &digest, "prompt");
        println!("{prompt}");
        return 0;
    }
    let executable = find_llama_cli(&parsed.llama_cli);
    if executable.is_empty() {
        print_file_status(&target, &parsed.model, &digest, "unavailable");
        eprintln!("FILE_RESP_LLM_ERROR=llama-cli-not-found");
        return 2;
    }
    let command = LlamaCommand {
        executable,
        model: parsed.model.clone(),
        prompt,
        predict_tokens: parsed.predict_tokens,
    };
    run_llama(&target, &parsed.model, &digest, &command)
}

fn read_target(root: &Path, raw_file: &str, max_bytes: usize) -> Result<ReviewTarget, String> {
    let root = root.to_path_buf();
    let path = if Path::new(raw_file).is_absolute() {
        PathBuf::from(raw_file)
    } else {
        root.join(raw_file)
    };
    if !path.is_file() {
        return Err(format!("single-file target is required: {raw_file}"));
    }
    let mut data = fs::read(&path).map_err(|error| format!("read-failed:{error}"))?;
    if data.len() > max_bytes {
        data.truncate(max_bytes);
    }
    let text = String::from_utf8_lossy(&data).to_string();
    let root = root.canonicalize().unwrap_or(root);
    let path = path.canonicalize().unwrap_or(path);
    let relative_path = relative_path(&root, &path);
    Ok(ReviewTarget {
        root,
        path,
        relative_path,
        text,
    })
}

fn prompt_for_target(target: &ReviewTarget) -> String {
    [
        "You are an advisory code/document responsibility reviewer.",
        "Scope: exactly one file. Do not infer repo-wide ownership.",
        "Primary authority remains dependency headers, tool catalog, and responsibility manifests.",
        "Return concise Markdown with these headings only:",
        "1. Responsibility Summary",
        "2. Possible Ownership Mismatch",
        "3. Missing Protecting Tool Or Issue Evidence",
        "4. Deterministic Follow-Up Checks",
        "",
        &format!("File: {}", target.relative_path),
        "",
        "Content:",
        "```",
        &target.text,
        "```",
    ]
    .join("\n")
}

fn prompt_digest(prompt: &str) -> String {
    let digest = stable_sha256_hex(prompt.as_bytes());
    digest[..PROMPT_DIGEST_LENGTH].to_string()
}

fn stable_sha256_hex(data: &[u8]) -> String {
    let output = Sha256::digest(data);
    output.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn print_file_status(target: &ReviewTarget, model: &str, digest: &str, status: &str) {
    println!("FILE_RESP_LLM_SCOPE=single_file");
    println!("FILE_RESP_LLM_FILE={}", target.relative_path);
    println!("FILE_RESP_LLM_MODEL={model}");
    println!("FILE_RESP_LLM_PROMPT_SHA={digest}");
    println!("FILE_RESP_LLM={status}");
}

fn find_llama_cli(explicit: &str) -> String {
    let tools_home = env::var("AGENT_CANON_TOOLS_HOME").unwrap_or_else(|_| {
        let home = env::var("HOME").unwrap_or_else(|_| ".".to_string());
        format!("{home}/.tools")
    });
    let candidates = [
        explicit.to_string(),
        format!("{tools_home}/bin/llama-cli"),
        env::var("HOME")
            .map(|home| format!("{home}/.tools/bin/llama-cli"))
            .unwrap_or_default(),
        find_on_path("llama-cli"),
    ];
    candidates
        .into_iter()
        .find(|candidate| !candidate.is_empty() && Path::new(candidate).exists())
        .unwrap_or_default()
}

fn find_on_path(name: &str) -> String {
    let Some(paths) = env::var_os("PATH") else {
        return String::new();
    };
    for directory in env::split_paths(&paths) {
        let candidate = directory.join(name);
        if candidate.exists() {
            return candidate.to_string_lossy().to_string();
        }
    }
    String::new()
}

fn run_llama(target: &ReviewTarget, model: &str, digest: &str, command: &LlamaCommand) -> i32 {
    let output = Command::new(&command.executable)
        .args(command.args())
        .output();
    match output {
        Ok(result) => {
            let status = if result.status.success() {
                "pass"
            } else {
                "fail"
            };
            print_file_status(target, model, digest, status);
            if !result.stdout.is_empty() {
                print!("{}", String::from_utf8_lossy(&result.stdout));
            }
            if !result.stderr.is_empty() {
                eprint!("{}", String::from_utf8_lossy(&result.stderr));
            }
            result.status.code().unwrap_or(1)
        }
        Err(error) => {
            print_file_status(target, model, digest, "fail");
            eprintln!("FILE_RESP_LLM_ERROR=llama-launch-failed:{error}");
            1
        }
    }
}

fn relative_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(|relative| relative.to_string_lossy().to_string())
        .unwrap_or_else(|_| path.to_string_lossy().to_string())
        .replace('\\', "/")
}

fn value_string(args: &[String], index: usize, name: &str) -> Result<String, String> {
    args.get(index + 1)
        .cloned()
        .ok_or_else(|| format!("{name} requires a value"))
}

fn value_path(args: &[String], index: usize, name: &str) -> Result<PathBuf, String> {
    Ok(PathBuf::from(value_string(args, index, name)?))
}

fn parse_usize(args: &[String], index: usize, name: &str) -> Result<usize, String> {
    let value = value_string(args, index, name)?;
    value
        .parse::<usize>()
        .map_err(|_| format!("{name} must be a positive integer, got {value}"))
}

fn build_invocation(args: &LocalLlmArgs) -> Result<PythonInvocation, String> {
    let source_root = source_root_for(&args.root)?;
    let (script, prefix_args) = match args.command {
        LocalLlmCommand::ClassifyResponsibility => return Err("native-rust-command".to_string()),
        LocalLlmCommand::Search => (source_root.join("tools/agent_tools/search.py"), Vec::new()),
        LocalLlmCommand::BuildIndex => (
            source_root.join("tools/agent_tools/search_index.py"),
            vec!["build".to_string()],
        ),
        LocalLlmCommand::Eval => (
            source_root.join("tools/agent_tools/local_llm_eval.py"),
            Vec::new(),
        ),
        LocalLlmCommand::Help => return Err("help-has-no-python-engine".to_string()),
    };
    if !script.is_file() {
        return Err(format!("missing-script:{}", script.display()));
    }
    let mut invocation_args = prefix_args;
    if !args.has_root_argument() {
        invocation_args.push("--root".to_string());
        invocation_args.push(args.root.to_string_lossy().to_string());
    }
    invocation_args.extend(args.passthrough.clone());
    Ok(PythonInvocation {
        script,
        args: invocation_args,
    })
}

fn source_root_for(root: &Path) -> Result<PathBuf, String> {
    let root = root.to_path_buf();
    let mut candidates = Vec::new();
    if let Ok(env_root) = env::var("AGENT_CANON_SOURCE_ROOT") {
        candidates.push(PathBuf::from(env_root));
    }
    candidates.push(root.join("vendor/agent-canon"));
    candidates.push(root.clone());
    if let Ok(current_dir) = env::current_dir() {
        candidates.push(current_dir.join("vendor/agent-canon"));
        candidates.push(current_dir);
    }
    for candidate in candidates {
        if candidate.join("rust/agent-canon/Cargo.toml").is_file()
            || candidate.join("tools/catalog.yaml").is_file()
        {
            return Ok(candidate);
        }
    }
    Err(format!("agent-canon-source-not-found:{}", root.display()))
}

fn extract_root(args: &[String]) -> Option<PathBuf> {
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--root" {
            return args.get(index + 1).map(PathBuf::from);
        }
        index += 1;
    }
    None
}

fn has_option_value(args: &[String], name: &str) -> bool {
    let mut index = 0;
    while index < args.len() {
        if args[index] == name && args.get(index + 1).is_some() {
            return true;
        }
        index += 1;
    }
    false
}

fn print_usage() {
    eprintln!(
        "usage: agent-canon local-llm <classify-responsibility|review-file|search|build-index|eval> [--root <repo-root>] [tool args...]"
    );
    eprintln!(
        "examples: agent-canon local-llm classify-responsibility --print-prompt tools/agent_tools/search.py"
    );
    eprintln!(
        "          agent-canon local-llm search --purpose \"find responsibility scope tooling\""
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn parses_classify_alias_and_root() {
        let args = vec![
            "review-file".to_string(),
            "--root".to_string(),
            "fixture".to_string(),
            "--print-prompt".to_string(),
            "tools/example.py".to_string(),
        ];
        let parsed = LocalLlmArgs::parse(&args).expect("parse local llm args");

        assert_eq!(parsed.command, LocalLlmCommand::ClassifyResponsibility);
        assert_eq!(parsed.root, PathBuf::from("fixture"));
        assert!(parsed.has_root_argument());
    }

    #[test]
    fn build_index_adds_python_build_subcommand() {
        let root = make_fixture_root();
        write_engine_fixture(&root);
        let args = LocalLlmArgs {
            command: LocalLlmCommand::BuildIndex,
            root: root.clone(),
            passthrough: vec!["--surface".to_string(), "tools".to_string()],
        };

        let invocation = build_invocation(&args).expect("build invocation");

        assert!(invocation
            .script
            .ends_with("tools/agent_tools/search_index.py"));
        assert_eq!(invocation.args[0], "build");
        assert_eq!(invocation.args[1], "--root");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn classify_prompt_is_native_rust_and_single_file() {
        let root = make_fixture_root();
        let target = root.join("tools/example.py");
        fs::create_dir_all(target.parent().expect("target parent")).expect("mkdir target");
        fs::write(&target, "# @dependency-start\n# responsibility Example.\n")
            .expect("write target");
        let args = vec![
            "--root".to_string(),
            root.to_string_lossy().to_string(),
            "--print-prompt".to_string(),
            "tools/example.py".to_string(),
        ];
        let parsed = ClassifyArgs::parse(root.clone(), &args).expect("parse classify args");
        let review_target =
            read_target(&parsed.root, &parsed.file, parsed.max_bytes).expect("read target");
        let prompt = prompt_for_target(&review_target);

        assert!(prompt.contains("Scope: exactly one file"));
        assert!(prompt.contains("Do not infer repo-wide ownership."));
        assert_eq!(review_target.relative_path, "tools/example.py");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn parent_repo_root_uses_vendored_agent_canon_source() {
        let root = make_fixture_root();
        write_engine_fixture(&root.join("vendor/agent-canon"));

        let source = source_root_for(&root).expect("source root");

        assert!(source.ends_with("vendor/agent-canon"));
        let _ = fs::remove_dir_all(root);
    }

    fn make_fixture_root() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        env::temp_dir().join(format!("agent-canon-local-llm-{suffix}"))
    }

    fn write_engine_fixture(root: &Path) {
        let tool_dir = root.join("tools/agent_tools");
        fs::create_dir_all(&tool_dir).expect("mkdir tools");
        fs::write(root.join("tools/catalog.yaml"), "fixture\n").expect("write catalog");
        for script in [
            "file_responsibility_llm.py",
            "search.py",
            "search_index.py",
            "local_llm_eval.py",
        ] {
            fs::write(tool_dir.join(script), "fixture\n").expect("write script");
        }
    }
}
