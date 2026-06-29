// @dependency-start
// contract implementation
// responsibility Provides Rust-native local LLM CLI routing, prose IR extraction, and responsibility review.
// upstream design ../../../documents/local-llm-responsibility-analysis.md local LLM responsibility boundary
// upstream design ../../../documents/search-coordination.md coordinated search provider contract
// upstream design ../../../documents/rust-agent-tool-migration.md Rust CLI migration policy
// upstream design ../../../agents/skills/structure-refactor.md repository structure and personal runtime routing boundary
// upstream design ../../../agent-canon-environment.toml records local LLM CLI environment commands
// downstream design ../../../tools/catalog.yaml catalogs this Rust CLI surface
// downstream design ../../../tools/README.md documents root tool entrypoints
// downstream design ../../../documents/tools/README.md documents reader-facing tool entrypoints
// downstream implementation ../../../tools/agent_tools/file_responsibility_llm.py remains the Python compatibility prompt helper
// downstream implementation ../../../tools/agent_tools/search.py coordinates purpose-based search
// downstream implementation ../../../tools/agent_tools/search_index.py builds local LLM search cards
// downstream implementation ../../../tools/agent_tools/local_llm_eval.py validates local LLM eval cases
// downstream implementation ../../../tools/agent_tools/prose_reasoning_graph.py consumes local prose IR extraction
// downstream implementation ../../../tools/bin/agent-canon invokes this command through the CLI wrapper
// downstream implementation ../../../tools/ci/run_all_checks.sh runs this CLI in local CI
// downstream implementation ../../../.github/workflows/agent-canon-static-gates.yml runs this CLI in GitHub static gates
// @dependency-end

use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const DEFAULT_MODEL: &str = "ggml-org/SmolLM3-3B-GGUF:Q4_K_M";
const DEFAULT_MAX_BYTES: usize = 24_000;
const DEFAULT_PREDICT_TOKENS: usize = 768;
const DEFAULT_PROSE_IR_DOCUMENT_BATCH_SIZE: usize = 4;
const DEFAULT_PROSE_IR_TERM_BATCH_SIZE: usize = 32;
const DEFAULT_PROSE_IR_LLM_JOBS: usize = 4;
const PROMPT_DIGEST_LENGTH: usize = 12;
const LOCAL_LLM_CPU_ENV: [(&str, &str); 4] = [
    ("CUDA_VISIBLE_DEVICES", ""),
    ("NVIDIA_VISIBLE_DEVICES", "void"),
    ("HIP_VISIBLE_DEVICES", ""),
    ("ROCR_VISIBLE_DEVICES", ""),
];

#[derive(Debug, Clone, PartialEq, Eq)]
enum LocalLlmCommand {
    ClassifyResponsibility,
    ExtractProseIr,
    RouteImplementationSurface,
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
            "extract-prose-ir" | "prose-ir" => LocalLlmCommand::ExtractProseIr,
            "route-implementation-surface" | "implementation-surface" => {
                LocalLlmCommand::RouteImplementationSurface
            }
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
    if args.command == LocalLlmCommand::ExtractProseIr {
        return run_extract_prose_ir(args);
    }
    if args.command == LocalLlmCommand::RouteImplementationSurface {
        return run_route_implementation_surface(args);
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

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProseIrArgs {
    root: PathBuf,
    files: Vec<String>,
    terms: Vec<String>,
    terms_files: Vec<PathBuf>,
    prompt: String,
    prompt_files: Vec<PathBuf>,
    model: String,
    llama_cli: String,
    max_bytes: usize,
    predict_tokens: usize,
    document_batch_size: usize,
    term_batch_size: usize,
    llm_jobs: usize,
    json_out: Option<PathBuf>,
    print_prompt: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProseIrDocument {
    path: PathBuf,
    relative_path: String,
    title: String,
    responsibility: String,
    kind: String,
    text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum RouteOutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RouteImplementationSurfaceArgs {
    root: PathBuf,
    request_parts: Vec<String>,
    request_files: Vec<PathBuf>,
    request_stdin: bool,
    model: String,
    llama_cli: String,
    predict_tokens: usize,
    format: RouteOutputFormat,
    print_prompt: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SurfaceCandidate {
    surface: String,
    owner: String,
    score: i64,
    rationale: Vec<String>,
    canonical_paths: Vec<String>,
    forbidden_paths: Vec<String>,
    required_checks: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SurfaceRouteDecision {
    request: String,
    prompt_digest: String,
    model: String,
    llm_status: String,
    llm_output: String,
    candidates: Vec<SurfaceCandidate>,
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

impl ProseIrArgs {
    fn parse(root: PathBuf, args: &[String]) -> Result<Self, String> {
        let mut parsed = Self {
            root,
            files: Vec::new(),
            terms: Vec::new(),
            terms_files: Vec::new(),
            prompt: String::new(),
            prompt_files: Vec::new(),
            model: env::var("AGENT_CANON_LOCAL_LLM_MODEL")
                .unwrap_or_else(|_| DEFAULT_MODEL.to_string()),
            llama_cli: env::var("AGENT_CANON_LLAMA_CLI").unwrap_or_default(),
            max_bytes: DEFAULT_MAX_BYTES,
            predict_tokens: DEFAULT_PREDICT_TOKENS,
            document_batch_size: DEFAULT_PROSE_IR_DOCUMENT_BATCH_SIZE,
            term_batch_size: DEFAULT_PROSE_IR_TERM_BATCH_SIZE,
            llm_jobs: default_prose_ir_llm_jobs(),
            json_out: None,
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
                "--document-batch-size" => {
                    parsed.document_batch_size = parse_usize(args, index, "--document-batch-size")?;
                    index += 2;
                }
                "--term-batch-size" => {
                    parsed.term_batch_size = parse_usize(args, index, "--term-batch-size")?;
                    index += 2;
                }
                "--llm-jobs" | "--jobs" => {
                    parsed.llm_jobs = parse_usize(args, index, args[index].as_str())?;
                    index += 2;
                }
                "--prompt" => {
                    parsed
                        .prompt
                        .push_str(&value_string(args, index, "--prompt")?);
                    parsed.prompt.push('\n');
                    index += 2;
                }
                "--prompt-file" => {
                    parsed
                        .prompt_files
                        .push(value_path(args, index, "--prompt-file")?);
                    index += 2;
                }
                "--term" => {
                    parsed.terms.push(value_string(args, index, "--term")?);
                    index += 2;
                }
                "--terms-file" => {
                    parsed
                        .terms_files
                        .push(value_path(args, index, "--terms-file")?);
                    index += 2;
                }
                "--json-out" => {
                    parsed.json_out = Some(value_path(args, index, "--json-out")?);
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
                    parsed.files.push(file.to_string());
                    index += 1;
                }
            }
        }
        if parsed.files.is_empty() {
            return Err("at-least-one-file-required".to_string());
        }
        Ok(parsed)
    }

    fn prompt_context(&self) -> Result<String, String> {
        let mut parts = Vec::new();
        if !self.prompt.trim().is_empty() {
            parts.push(self.prompt.trim().to_string());
        }
        for prompt_file in &self.prompt_files {
            let path = rooted_path(&self.root, prompt_file);
            if !path.is_file() {
                return Err(format!("prompt-file-not-found:{}", prompt_file.display()));
            }
            parts.push(fs::read_to_string(&path).map_err(|error| {
                format!("prompt-file-read-failed:{}:{error}", prompt_file.display())
            })?);
        }
        Ok(parts.join("\n"))
    }

    fn term_inputs(&self) -> Result<Vec<String>, String> {
        let mut terms = self.terms.clone();
        for terms_file in &self.terms_files {
            let path = rooted_path(&self.root, terms_file);
            if !path.is_file() {
                return Err(format!("terms-file-not-found:{}", terms_file.display()));
            }
            let text = fs::read_to_string(&path).map_err(|error| {
                format!("terms-file-read-failed:{}:{error}", terms_file.display())
            })?;
            for line in text.lines() {
                let term = line.trim();
                if !term.is_empty() && !term.starts_with('#') {
                    terms.push(term.to_string());
                }
            }
        }
        Ok(unique_nonempty(terms))
    }
}

impl RouteImplementationSurfaceArgs {
    fn parse(root: PathBuf, args: &[String]) -> Result<Self, String> {
        let mut parsed = Self {
            root,
            request_parts: Vec::new(),
            request_files: Vec::new(),
            request_stdin: false,
            model: env::var("AGENT_CANON_LOCAL_LLM_MODEL")
                .unwrap_or_else(|_| DEFAULT_MODEL.to_string()),
            llama_cli: env::var("AGENT_CANON_LLAMA_CLI").unwrap_or_default(),
            predict_tokens: DEFAULT_PREDICT_TOKENS,
            format: RouteOutputFormat::Text,
            print_prompt: false,
        };
        let mut index = 0;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    parsed.root = value_path(args, index, "--root")?;
                    index += 2;
                }
                "--request" | "--purpose" | "--task" => {
                    parsed
                        .request_parts
                        .push(value_string(args, index, args[index].as_str())?);
                    index += 2;
                }
                "--request-file" | "--query-file" => {
                    parsed
                        .request_files
                        .push(value_path(args, index, args[index].as_str())?);
                    index += 2;
                }
                "--request-stdin" | "--query-stdin" => {
                    parsed.request_stdin = true;
                    index += 1;
                }
                "--model" => {
                    parsed.model = value_string(args, index, "--model")?;
                    index += 2;
                }
                "--llama-cli" => {
                    parsed.llama_cli = value_string(args, index, "--llama-cli")?;
                    index += 2;
                }
                "--predict-tokens" => {
                    parsed.predict_tokens = parse_usize(args, index, "--predict-tokens")?;
                    index += 2;
                }
                "--format" => {
                    parsed.format = match value_string(args, index, "--format")?.as_str() {
                        "text" => RouteOutputFormat::Text,
                        "json" => RouteOutputFormat::Json,
                        value => return Err(format!("--format must be text or json, got {value}")),
                    };
                    index += 2;
                }
                "--print-prompt" => {
                    parsed.print_prompt = true;
                    index += 1;
                }
                unknown if unknown.starts_with('-') => {
                    return Err(format!("unknown argument {unknown}"))
                }
                text => {
                    parsed.request_parts.push(text.to_string());
                    index += 1;
                }
            }
        }
        Ok(parsed)
    }

    fn request_text(&self) -> Result<String, String> {
        let mut parts = self.request_parts.clone();
        for request_file in &self.request_files {
            let path = rooted_path(&self.root, request_file);
            if !path.is_file() {
                return Err(format!("request-file-not-found:{}", request_file.display()));
            }
            parts.push(fs::read_to_string(&path).map_err(|error| {
                format!(
                    "request-file-read-failed:{}:{error}",
                    request_file.display()
                )
            })?);
        }
        if self.request_stdin {
            let mut stdin_text = String::new();
            std::io::Read::read_to_string(&mut std::io::stdin(), &mut stdin_text)
                .map_err(|error| format!("request-stdin-read-failed:{error}"))?;
            parts.push(stdin_text);
        }
        let request = parts
            .iter()
            .map(|part| part.trim())
            .filter(|part| !part.is_empty())
            .collect::<Vec<_>>()
            .join("\n");
        if request.is_empty() {
            return Err("request-required".to_string());
        }
        Ok(request)
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

fn run_extract_prose_ir(args: &LocalLlmArgs) -> i32 {
    let parsed = match ProseIrArgs::parse(args.root.clone(), &args.passthrough) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("LOCAL_LLM_PROSE_IR_ERROR={message}");
            return 2;
        }
    };
    let prompt_context = match parsed.prompt_context() {
        Ok(prompt_context) => prompt_context,
        Err(message) => {
            eprintln!("LOCAL_LLM_PROSE_IR_ERROR={message}");
            return 2;
        }
    };
    let mut documents = Vec::new();
    for file in &parsed.files {
        match read_prose_ir_document(&parsed.root, file, parsed.max_bytes) {
            Ok(document) => documents.push(document),
            Err(message) => {
                eprintln!("LOCAL_LLM_PROSE_IR_ERROR={message}");
                return 2;
            }
        }
    }
    let raw_terms = match parsed.term_inputs() {
        Ok(terms) => terms,
        Err(message) => {
            eprintln!("LOCAL_LLM_PROSE_IR_ERROR={message}");
            return 2;
        }
    };
    let terms = if raw_terms.is_empty() {
        extract_salient_terms(&documents)
    } else {
        raw_terms
    };
    let part_prompts = prompt_parts_for_prose_ir(&documents, &terms, &prompt_context, &parsed);
    let prompt = part_prompts
        .iter()
        .map(|part| format!("## {}\n{}", part.part_id, part.prompt))
        .collect::<Vec<_>>()
        .join("\n\n---\n\n");
    let digest = prompt_digest(&prompt);
    if parsed.print_prompt {
        println!("LOCAL_LLM_PROSE_IR_SCOPE=batch_documents_terms");
        println!("LOCAL_LLM_PROSE_IR_DOCUMENTS={}", documents.len());
        println!("LOCAL_LLM_PROSE_IR_TERMS={}", terms.len());
        println!("LOCAL_LLM_PROSE_IR_PARTS={}", part_prompts.len());
        println!("LOCAL_LLM_PROSE_IR_MODEL={}", parsed.model);
        println!("LOCAL_LLM_PROSE_IR_PROMPT_SHA={digest}");
        println!("LOCAL_LLM_PROSE_IR=prompt");
        println!("{prompt}");
        return 0;
    }

    let part_llm_results = prose_ir_part_llm_results(&part_prompts, &parsed);
    let payload = prose_ir_payload(
        &parsed,
        &documents,
        &terms,
        &prompt_context,
        &digest,
        &part_llm_results,
    );
    let rendered = match serde_json::to_string_pretty(&payload) {
        Ok(rendered) => rendered + "\n",
        Err(error) => {
            eprintln!("LOCAL_LLM_PROSE_IR_ERROR=json-render-failed:{error}");
            return 1;
        }
    };
    if let Some(path) = parsed.json_out {
        if let Some(parent) = path.parent() {
            if let Err(error) = fs::create_dir_all(parent) {
                eprintln!("LOCAL_LLM_PROSE_IR_ERROR=json-out-dir-failed:{error}");
                return 1;
            }
        }
        if let Err(error) = fs::write(&path, &rendered) {
            eprintln!("LOCAL_LLM_PROSE_IR_ERROR=json-out-write-failed:{error}");
            return 1;
        }
        println!("LOCAL_LLM_PROSE_IR=pass");
        println!("LOCAL_LLM_PROSE_IR_JSON={}", path.display());
        println!("LOCAL_LLM_PROSE_IR_DOCUMENTS={}", documents.len());
        println!("LOCAL_LLM_PROSE_IR_TERMS={}", terms.len());
        println!("LOCAL_LLM_PROSE_IR_PARTS={}", part_prompts.len());
        println!("LOCAL_LLM_PROSE_IR_PROMPT_SHA={digest}");
        return 0;
    }
    println!("{rendered}");
    0
}

fn run_route_implementation_surface(args: &LocalLlmArgs) -> i32 {
    let parsed = match RouteImplementationSurfaceArgs::parse(args.root.clone(), &args.passthrough) {
        Ok(parsed) => parsed,
        Err(message) => {
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_ERROR={message}");
            return 2;
        }
    };
    let request = match parsed.request_text() {
        Ok(request) => request,
        Err(message) => {
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_ERROR={message}");
            return 2;
        }
    };
    let candidates = implementation_surface_candidates(&request);
    let prompt = prompt_for_implementation_surface_route(&request, &candidates);
    let digest = prompt_digest(&prompt);
    if parsed.print_prompt {
        println!("IMPLEMENTATION_SURFACE_ROUTER=prompt");
        println!("IMPLEMENTATION_SURFACE_ROUTER_MODEL={}", parsed.model);
        println!("IMPLEMENTATION_SURFACE_ROUTER_PROMPT_SHA={digest}");
        println!("{prompt}");
        return 0;
    }

    let executable = find_llama_cli(&parsed.llama_cli);
    if executable.is_empty() {
        let decision = SurfaceRouteDecision {
            request,
            prompt_digest: digest,
            model: parsed.model,
            llm_status: "deterministic_candidate_fallback".to_string(),
            llm_output: "llama-cli not found; using deterministic candidate ranking".to_string(),
            candidates,
        };
        match parsed.format {
            RouteOutputFormat::Json => print_implementation_surface_route_json(&decision),
            RouteOutputFormat::Text => print_implementation_surface_route_text(&decision),
        }
        return 0;
    }
    let command = LlamaCommand {
        executable,
        model: parsed.model.clone(),
        prompt: prompt.clone(),
        predict_tokens: parsed.predict_tokens,
    };
    let llm_output = match run_llama_prompt(&command) {
        Ok((raw_output, raw_stderr)) => {
            if raw_stderr.trim().is_empty() {
                raw_output
            } else {
                format!("{}\n\n[stderr]\n{}", raw_output.trim(), raw_stderr.trim())
            }
        }
        Err(message) => {
            print_implementation_surface_route_error(
                &parsed,
                &request,
                &digest,
                "local_llm_route_failed",
                &message,
            );
            return 1;
        }
    };
    let decision = SurfaceRouteDecision {
        request,
        prompt_digest: digest,
        model: parsed.model,
        llm_status: "local_llm_advisory".to_string(),
        llm_output,
        candidates,
    };
    match parsed.format {
        RouteOutputFormat::Json => print_implementation_surface_route_json(&decision),
        RouteOutputFormat::Text => print_implementation_surface_route_text(&decision),
    }
    0
}

fn implementation_surface_candidates(request: &str) -> Vec<SurfaceCandidate> {
    let lower = request.to_lowercase();
    let mut candidates = vec![
        surface_candidate(
            &lower,
            "agentcanon_local_llm_tool",
            "AgentCanon shared tool implementation",
            &[
                "rust/agent-canon/src/local_llm.rs",
                "tools/catalog.yaml",
                "documents/tools/agent-canon.md",
                "documents/local-llm-responsibility-analysis.md",
                "rust/agent-canon/src/local_llm.rs tests",
            ],
            &[
                "project-local scripts for reusable AgentCanon routing",
                "new Python helper when the Rust local-llm CLI can be extended",
            ],
            &[
                "cargo test --manifest-path rust/agent-canon/Cargo.toml local_llm",
                "tools/bin/agent-canon local-llm route-implementation-surface --request <task>",
                "python3 tools/agent_tools/tool_catalog.py",
            ],
            &[
                ("implementation surface", 7),
                ("route-implementation-surface", 7),
                ("local llm", 6),
                ("local-llm", 6),
                ("llm", 3),
                ("router", 5),
                ("ルーター", 5),
                ("実装前", 4),
                ("責務判定", 5),
                ("責務", 2),
                ("判定", 2),
                ("tool", 2),
                ("ツール", 2),
            ],
        ),
        surface_candidate(
            &lower,
            "agent_runtime_instructions",
            "AgentCanon root runtime instruction surface",
            &[
                "ROOT_AGENTS.md",
                "AGENTS.md root shared view after sync_agent_canon.sh link-root",
                "documents/SHARED_RUNTIME_SURFACES.md",
            ],
            &[
                "editing root AGENTS.md as an independent truth surface when it is a shared view",
                "duplicating tool-owned deterministic rules as prose-only guardrails",
            ],
            &[
                "bash tools/sync_agent_canon.sh link-root",
                "tools/bin/agent-canon docs check ROOT_AGENTS.md",
            ],
            &[
                ("agents.md", 6),
                ("agent.md", 6),
                ("root_agents", 5),
                ("root agents", 5),
                ("agent instruction", 4),
                ("runtime entrypoint", 4),
                ("エージェント", 3),
                ("指示", 3),
                ("agent", 1),
            ],
        ),
        surface_candidate(
            &lower,
            "skill_workflow_policy",
            "AgentCanon skill and workflow routing policy",
            &[
                ".agents/skills/agent-orchestration/SKILL.md",
                "agents/skills/agent-orchestration.md",
                ".agents/skills/codex-task-workflow/SKILL.md",
                "agents/skills/codex-task-workflow.md",
                "agents/TASK_WORKFLOWS.md",
            ],
            &[
                "subagent handoff prose that reimplements a canonical router result",
                "task-local workflow copy",
            ],
            &[
                "python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "python3 tools/agent_tools/check_convention_compliance.py",
            ],
            &[
                ("skill", 4),
                ("スキル", 4),
                ("workflow", 3),
                ("ワークフロー", 3),
                ("routing", 3),
                ("ルーティング", 3),
                ("handoff", 3),
                ("subagent", 3),
                ("サブエージェント", 3),
            ],
        ),
        surface_candidate(
            &lower,
            "contract_only_test_policy",
            "Contract-only wrapper and checker-owned test admission policy",
            &[
                "documents/coding-conventions-testing.md",
                "agents/skills/test-design.md",
                ".agents/skills/test-design/SKILL.md",
                "agents/TASK_WORKFLOWS.md",
                "agents/canonical/CODEX_WORKFLOW.md",
                "tools/agent_tools/check_convention_compliance.py",
            ],
            &[
                "pytest smoke added for static contract validation",
                "execution-only no-crash test for a thin adapter",
                "numerical smoke for non-numerical routing, metadata, docs, or wrapper changes",
            ],
            &[
                "python3 tools/agent_tools/check_convention_compliance.py",
                "tools/bin/agent-canon docs check <changed-docs>",
                "cargo test --manifest-path rust/agent-canon/Cargo.toml implementation_surface_route",
            ],
            &[
                ("contract-only wrapper", 18),
                ("contract only wrapper", 18),
                ("contract-only adapter", 16),
                ("thin adapter", 14),
                ("契約だけ", 18),
                ("契約だけの wrapper", 20),
                ("契約だけのラッパー", 20),
                ("テストを強制", 16),
                ("testを強制", 16),
                ("余計なテスト", 14),
                ("不要なテスト", 14),
                ("pytest smoke", 14),
                ("execution-only test", 14),
                ("no-crash test", 14),
                ("static-analysis duplicate", 14),
                ("static-analysis-duplicate-test", 14),
                ("static contract validation", 14),
                ("checker-owned validation", 12),
                ("canonical command evidence", 12),
                ("runtime behavior", 10),
                ("observable behavior", 10),
                ("数値テスト", 9),
                ("数値 smoke", 9),
                ("unnecessary test", 10),
                ("heavy test", 8),
            ],
        ),
        surface_candidate(
            &lower,
            "numerical_iterative_algorithm_contract",
            "Computational optimization and iterative algorithm contract",
            &[
                "agents/skills/computational-optimization.md",
                ".agents/skills/computational-optimization/SKILL.md",
                "documents/algorithm-implementation-boundary.md",
                "documents/conventions/python/15_jax_rules.md",
                "documents/coding-conventions-testing.md",
            ],
            &[
                "new solver helper before objective/residual, Step_impl, R_impl, state, and stopping policy are fixed",
                "proof-only Info fields, diagnostic gates, or runtime checks without iteration-map effect",
                "large numerical tests before static contract and smallest deterministic cases are defined",
            ],
            &[
                "tools/bin/agent-canon python-algorithm-contract-check --root . <paths>",
                "tools/bin/agent-canon test-design check <test-plan-or-doc>",
                "python3 tools/agent_tools/check_convention_compliance.py",
            ],
            &[
                ("iterative method", 9),
                ("iteration map", 9),
                ("fixed point", 7),
                ("solver", 8),
                ("convergence", 8),
                ("stopping", 7),
                ("residual", 7),
                ("preconditioner", 7),
                ("kkt", 7),
                ("newton", 6),
                ("mehrotra", 6),
                ("optimizer", 5),
                ("optimization", 5),
                ("lax.while_loop", 6),
                ("while_loop", 5),
                ("反復法", 9),
                ("反復", 6),
                ("収束", 8),
                ("停止条件", 7),
                ("残差", 7),
                ("数値", 5),
            ],
        ),
        surface_candidate(
            &lower,
            "directory_repository_responsibility",
            "Repository and directory responsibility contract",
            &[
                "responsibility-scope.toml",
                "documents/repo-structure-contract.toml",
                "documents/SHARED_RUNTIME_SURFACES.md",
                "documents/responsibility-scope-management.md",
            ],
            &[
                "moving files before ownership and root-view contracts are checked",
                "using raw rg hits as ownership authority",
            ],
            &[
                "python3 tools/agent_tools/responsibility_scope.py",
                "python3 tools/agent_tools/repo_structure_contract.py",
                "agent-canon semantic-index responsibility-tree --root . --check-directory-coverage --format text",
            ],
            &[
                ("directory", 4),
                ("ディレクトリ", 5),
                ("repository", 3),
                ("リポジトリ", 3),
                ("repo", 2),
                ("ownership", 4),
                ("owner", 2),
                ("責務", 2),
                ("responsibility-scope", 5),
                ("root view", 4),
            ],
        ),
        surface_candidate(
            &lower,
            "document_claim_grounding",
            "Canonical document claim, program-contract, proof-status, and evidence-grounding policy",
            &[
                "documents/conventions/common/05_docs.md",
                "documents/coding-conventions-project.md",
                "agents/skills/long-form-writing.md",
                ".agents/skills/long-form-writing/SKILL.md",
                "agents/skills/formal-proof-workflow.md",
                ".agents/skills/formal-proof-workflow/SKILL.md",
                "tools/agent_tools/check_convention_compliance.py",
            ],
            &[
                "run-local planning language promoted to canonical policy",
                "manual prose-only claim validation when checker or proof status is required",
                "new policy prose without convention-compliance coverage",
            ],
            &[
                "python3 tools/agent_tools/check_convention_compliance.py",
                "tools/bin/agent-canon docs check <changed-docs>",
                "cargo test --manifest-path rust/agent-canon/Cargo.toml implementation_surface_route",
            ],
            &[
                ("program contract", 12),
                ("program contracts", 12),
                ("プログラム契約", 12),
                ("プログラムの契約", 12),
                ("claim grounding", 10),
                ("canonical document", 9),
                ("canonical documents", 9),
                ("public entrypoint", 9),
                ("input schema", 9),
                ("return projection", 9),
                ("mathematical claim", 9),
                ("mathematical statement", 9),
                ("mathematical statements", 9),
                ("observable effect", 8),
                ("observable state", 8),
                ("proof obligation", 9),
                ("proof_status", 9),
                ("proof status", 8),
                ("theorem target", 8),
                ("checker evidence", 8),
                ("provisional wording", 8),
                ("validation command", 8),
                ("preconditions", 7),
                ("正本文書", 8),
                ("文書を正", 8),
                ("まずは", 8),
                ("誇張", 7),
                ("overclaim", 7),
                ("source authority", 6),
                ("evidence class", 6),
                ("assumptions", 5),
                ("definitions", 5),
                ("for now", 5),
                ("first pass", 5),
                ("first draft", 5),
                ("proof-like", 5),
                ("数理", 5),
                ("数学", 5),
                ("証明", 5),
                ("定理", 5),
                ("ad hoc", 4),
                ("adhoc", 4),
                ("checker", 4),
                ("文書", 4),
            ],
        ),
        surface_candidate(
            &lower,
            "personal_codex_runtime",
            "User-level Codex configuration, skills, rules, and hook trust state",
            &[
                "$HOME/.codex/config.toml",
                "$HOME/.codex/skills/",
                "$HOME/.codex/rules/",
                "project .codex symlink targets for comparison only",
            ],
            &[
                "repo-local mirror of personal Codex state",
                "auth, history, sessions, logs, or caches unless explicitly required",
                "shared AgentCanon policy for a user-only runtime setting",
            ],
            &[
                "inspect non-secret ~/.codex config keys and skill IDs",
                "readlink -f .codex/config.toml .agents/skills",
                "python3 tools/agent_tools/route.py --prompt <request> --format json",
            ],
            &[
                ("~/.codex", 9),
                ("$home/.codex", 9),
                ("home/.codex", 9),
                ("personal codex", 6),
                ("personal runtime", 6),
                ("user codex", 5),
                ("user-level codex", 5),
                ("個人", 4),
            ],
        ),
        surface_candidate(
            &lower,
            "documentation_canon",
            "Reader-facing canonical documentation surface",
            &[
                "documents/",
                "documents/tools/",
                "agents/skills/",
                "README.md or ROOT_AGENTS.md only when listed as the canonical shared view",
            ],
            &[
                "generated reports as source canon",
                "parallel dated design copies",
            ],
            &[
                "tools/bin/agent-canon docs check <changed-docs>",
                "bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing",
            ],
            &[
                ("document", 3),
                ("documentation", 4),
                ("docs", 3),
                ("文書", 4),
                ("設計", 3),
                ("readme", 3),
                ("正本", 4),
            ],
        ),
        surface_candidate(
            &lower,
            "deterministic_checker_or_formatter",
            "Deterministic checker, formatter, or structured-analysis tool",
            &[
                "rust/agent-canon/src/docs.rs",
                "rust/agent-canon/src/structured_analysis.rs",
                "tools/catalog.yaml",
                "documents/tools/",
            ],
            &[
                "prompt-only rule for behavior that a checker can decide",
                "manual prose review as the only validation route",
            ],
            &[
                "tools/bin/agent-canon docs -h",
                "tools/bin/agent-canon structured-analysis --help",
                "cargo test --manifest-path rust/agent-canon/Cargo.toml",
            ],
            &[
                ("deterministic", 4),
                ("決定論", 5),
                ("checker", 4),
                ("チェック", 4),
                ("formatter", 4),
                ("フォーマッタ", 5),
                ("structured", 3),
                ("構造化", 4),
                ("warning", 3),
                ("警告", 3),
            ],
        ),
        surface_candidate(
            &lower,
            "environment_or_ci_surface",
            "Environment, CI, and GitHub Actions surface",
            &[
                "docker/",
                ".github/workflows/",
                "agent-canon-environment.toml",
                "documents/runtime-profiles-and-check-matrix.md",
            ],
            &["tool or skill docs for environment behavior that CI must enforce"],
            &[
                "tools/ci/check_agent_canon_pr.sh",
                "tools/bin/agent-canon docs check docker/ .github/workflows/",
            ],
            &[
                ("docker", 4),
                ("devcontainer", 4),
                ("github action", 5),
                ("githubaction", 5),
                ("ci", 3),
                ("environment", 3),
                ("環境", 4),
            ],
        ),
        surface_candidate(
            &lower,
            "report_or_runtime_artifact",
            "Run-bundle report, evidence, or append-only runtime artifact",
            &[
                "reports/agents/<run-id>/",
                ".agent-canon/log-archive/",
                "documents/runtime-log-archive.md",
            ],
            &[
                "committing generated evidence as source canon",
                "overwriting append-only runtime logs",
            ],
            &[
                "python3 tools/agent_tools/runtime_log_archive_git.py status",
                "python3 tools/agent_tools/eval_accumulation_check.py --compact-out <path>",
            ],
            &[
                ("report", 3),
                ("reports", 3),
                ("ログ", 4),
                ("log", 2),
                ("evidence", 4),
                ("run bundle", 5),
                ("artifact", 3),
            ],
        ),
    ];
    candidates.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| left.surface.cmp(&right.surface))
    });
    candidates.retain(|candidate| candidate.score > 0);
    if candidates.is_empty() {
        candidates.push(SurfaceCandidate {
            surface: "needs_responsibility_survey".to_string(),
            owner: "Route unknown until responsibility search selects the surface".to_string(),
            score: 0,
            rationale: vec!["no_keyword_surface_match".to_string()],
            canonical_paths: vec![
                "run agent-canon local-llm search --purpose <request>".to_string(),
                "run agent-canon semantic-index context-pack --query-file <file>".to_string(),
            ],
            forbidden_paths: vec![
                "new helper/module before the responsibility survey completes".to_string(),
            ],
            required_checks: vec![
                "agent-canon local-llm search --purpose <request> --providers llm,tool,header-deps,code-deps,vector --format text".to_string(),
                "bounded rg -l only after the responsibility route selects candidate paths".to_string(),
            ],
        });
    }
    candidates
}

fn surface_candidate(
    lower_request: &str,
    surface: &str,
    owner: &str,
    canonical_paths: &[&str],
    forbidden_paths: &[&str],
    required_checks: &[&str],
    keywords: &[(&str, i64)],
) -> SurfaceCandidate {
    let mut score = 0;
    let mut rationale = Vec::new();
    for (keyword, weight) in keywords {
        if lower_request.contains(&keyword.to_lowercase()) {
            score += weight;
            rationale.push(format!("matched_keyword:{keyword}"));
        }
    }
    SurfaceCandidate {
        surface: surface.to_string(),
        owner: owner.to_string(),
        score,
        rationale,
        canonical_paths: canonical_paths
            .iter()
            .map(|value| value.to_string())
            .collect(),
        forbidden_paths: forbidden_paths
            .iter()
            .map(|value| value.to_string())
            .collect(),
        required_checks: required_checks
            .iter()
            .map(|value| value.to_string())
            .collect(),
    }
}

fn prompt_for_implementation_surface_route(
    request: &str,
    candidates: &[SurfaceCandidate],
) -> String {
    let mut lines = vec![
        "You are the AgentCanon implementation-surface router.".to_string(),
        "Decide where an implementation should live before any file edit.".to_string(),
        "Use repository responsibility, canonical shared surfaces, tool ownership, skill ownership, and root-view policy.".to_string(),
        "Prefer existing canonical surfaces. Do not invent a new helper, module, skill, or directory unless every listed candidate is inadequate.".to_string(),
        "Return JSON only with schema agent_canon.local_llm.implementation_surface_route.v1.".to_string(),
        "Required JSON keys: schema, primary_surface, canonical_paths, forbidden_paths, required_pre_edit_checks, rationale, confidence, unresolved_questions.".to_string(),
        "If the request spans several surfaces, choose the implementation owner as primary and list doc/skill/runtime updates as secondary paths.".to_string(),
        String::new(),
        "Request:".to_string(),
        request.to_string(),
        String::new(),
        "Deterministic candidate surfaces from the Rust router:".to_string(),
    ];
    for candidate in candidates.iter().take(5) {
        lines.push(format!("- surface: {}", candidate.surface));
        lines.push(format!("  owner: {}", candidate.owner));
        lines.push(format!("  score: {}", candidate.score));
        lines.push(format!(
            "  canonical_paths: {}",
            candidate.canonical_paths.join("; ")
        ));
        lines.push(format!(
            "  forbidden_paths: {}",
            candidate.forbidden_paths.join("; ")
        ));
        lines.push(format!(
            "  required_checks: {}",
            candidate.required_checks.join("; ")
        ));
        lines.push(format!("  rationale: {}", candidate.rationale.join("; ")));
    }
    lines.join("\n")
}

fn print_implementation_surface_route_json(decision: &SurfaceRouteDecision) {
    let payload = implementation_surface_route_payload(decision);
    match serde_json::to_string_pretty(&payload) {
        Ok(rendered) => println!("{rendered}"),
        Err(error) => {
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_ERROR=json-render-failed:{error}");
        }
    }
}

fn print_implementation_surface_route_error(
    parsed: &RouteImplementationSurfaceArgs,
    request: &str,
    prompt_digest: &str,
    code: &str,
    message: &str,
) {
    match parsed.format {
        RouteOutputFormat::Json => {
            let payload = json!({
                "schema": "agent_canon.local_llm.implementation_surface_route.error.v1",
                "status": "error",
                "error_code": code,
                "message": message,
                "required_action": "repair LocalLLM environment before running implementation-surface routing",
                "model": parsed.model.as_str(),
                "prompt_sha": prompt_digest,
                "request": request,
            });
            match serde_json::to_string_pretty(&payload) {
                Ok(rendered) => eprintln!("{rendered}"),
                Err(error) => {
                    eprintln!("IMPLEMENTATION_SURFACE_ROUTER_ERROR=json-render-failed:{error}")
                }
            }
        }
        RouteOutputFormat::Text => {
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER=error");
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_SCHEMA=agent_canon.local_llm.implementation_surface_route.error.v1");
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_ERROR_CODE={code}");
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_ERROR={message}");
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_REQUIRED_ACTION=repair LocalLLM environment before running implementation-surface routing");
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_MODEL={}", parsed.model);
            eprintln!("IMPLEMENTATION_SURFACE_ROUTER_PROMPT_SHA={prompt_digest}");
        }
    }
}

fn print_implementation_surface_route_text(decision: &SurfaceRouteDecision) {
    let primary = decision
        .candidates
        .first()
        .expect("implementation surface candidates are never empty");
    println!("IMPLEMENTATION_SURFACE_ROUTER=pass");
    println!(
        "IMPLEMENTATION_SURFACE_ROUTER_SCHEMA=agent_canon.local_llm.implementation_surface_route.v1"
    );
    println!(
        "IMPLEMENTATION_SURFACE_ROUTER_STATUS={}",
        decision.llm_status
    );
    println!("IMPLEMENTATION_SURFACE_ROUTER_MODEL={}", decision.model);
    println!(
        "IMPLEMENTATION_SURFACE_ROUTER_PROMPT_SHA={}",
        decision.prompt_digest
    );
    println!("PRIMARY_SURFACE={}", primary.surface);
    println!("PRIMARY_OWNER={}", primary.owner);
    println!("PRIMARY_SCORE={}", primary.score);
    println!("PRIMARY_PATHS={}", primary.canonical_paths.join(" | "));
    println!("FORBIDDEN_PATHS={}", primary.forbidden_paths.join(" | "));
    println!(
        "REQUIRED_PRE_EDIT_CHECKS={}",
        primary.required_checks.join(" | ")
    );
    for (index, candidate) in decision.candidates.iter().take(5).enumerate() {
        println!("CANDIDATE_{}_SURFACE={}", index + 1, candidate.surface);
        println!("CANDIDATE_{}_SCORE={}", index + 1, candidate.score);
        println!(
            "CANDIDATE_{}_RATIONALE={}",
            index + 1,
            candidate.rationale.join(" | ")
        );
    }
    if !decision.llm_output.trim().is_empty() {
        println!("LOCAL_LLM_ROUTE_ADVISORY_BEGIN");
        println!("{}", decision.llm_output.trim());
        println!("LOCAL_LLM_ROUTE_ADVISORY_END");
    }
}

fn implementation_surface_route_payload(decision: &SurfaceRouteDecision) -> Value {
    let primary = decision
        .candidates
        .first()
        .expect("implementation surface candidates are never empty");
    let candidates: Vec<Value> = decision
        .candidates
        .iter()
        .map(|candidate| {
            json!({
                "surface": candidate.surface,
                "owner": candidate.owner,
                "score": candidate.score,
                "rationale": candidate.rationale,
                "canonical_paths": candidate.canonical_paths,
                "forbidden_paths": candidate.forbidden_paths,
                "required_checks": candidate.required_checks,
            })
        })
        .collect();
    json!({
        "schema": "agent_canon.local_llm.implementation_surface_route.v1",
        "status": decision.llm_status,
        "model": decision.model,
        "prompt_sha": decision.prompt_digest,
        "request": decision.request,
        "primary_surface": primary.surface,
        "primary_owner": primary.owner,
        "primary_paths": primary.canonical_paths,
        "forbidden_paths": primary.forbidden_paths,
        "required_pre_edit_checks": primary.required_checks,
        "candidates": candidates,
        "llm_output_raw": decision.llm_output,
    })
}

fn read_prose_ir_document(
    root: &Path,
    raw_file: &str,
    max_bytes: usize,
) -> Result<ProseIrDocument, String> {
    let path = rooted_path(root, Path::new(raw_file));
    if !path.is_file() {
        return Err(format!("document target is required: {raw_file}"));
    }
    let mut data = fs::read(&path).map_err(|error| format!("read-failed:{raw_file}:{error}"))?;
    if data.len() > max_bytes {
        data.truncate(max_bytes);
    }
    let text = String::from_utf8_lossy(&data).to_string();
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let canonical_path = path.canonicalize().unwrap_or(path);
    let relative_path = relative_path(&root, &canonical_path);
    Ok(ProseIrDocument {
        title: infer_markdown_title(&text, &canonical_path),
        responsibility: infer_dependency_responsibility(&text),
        kind: prose_ir_kind(&canonical_path),
        path: canonical_path,
        relative_path,
        text,
    })
}

fn rooted_path(root: &Path, path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProseIrPromptPart {
    part_id: String,
    prompt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProseIrPartLlmResult {
    part_id: String,
    prompt_sha: String,
    status: String,
    stdout: String,
    stderr: String,
}

fn prompt_parts_for_prose_ir(
    documents: &[ProseIrDocument],
    terms: &[String],
    prompt_context: &str,
    args: &ProseIrArgs,
) -> Vec<ProseIrPromptPart> {
    let document_batch_size = args.document_batch_size.max(1);
    let term_batch_size = args.term_batch_size.max(1);
    let term_chunks: Vec<&[String]> = if terms.is_empty() {
        vec![&[]]
    } else {
        terms.chunks(term_batch_size).collect()
    };
    let mut parts = Vec::new();
    for (document_batch_index, document_batch) in documents.chunks(document_batch_size).enumerate()
    {
        for (term_batch_index, term_batch) in term_chunks.iter().enumerate() {
            let part_id = format!(
                "part:d{}:t{}",
                document_batch_index + 1,
                term_batch_index + 1
            );
            parts.push(ProseIrPromptPart {
                prompt: prompt_for_prose_ir_part(
                    &part_id,
                    document_batch,
                    term_batch,
                    prompt_context,
                ),
                part_id,
            });
        }
    }
    parts
}

fn prompt_for_prose_ir_part(
    part_id: &str,
    documents: &[ProseIrDocument],
    terms: &[String],
    prompt_context: &str,
) -> String {
    let mut lines = vec![
        "You are a local LLM prose-structure extractor for AgentCanon.".to_string(),
        "Return a JSON intermediate representation, not a word list.".to_string(),
        "Handle only this supplied part. A deterministic tool will merge part IR later.".to_string(),
        "Do not infer facts from omitted documents or omitted terms; mark unresolved items instead.".to_string(),
        "Use this schema name: agent_canon.local_llm.prose_ir.v1.".to_string(),
        "Do not rewrite the prose and do not settle unsupported claims.".to_string(),
        "Ignore dependency-header boilerplate, code fences, and Markdown mechanics as domain terms unless they state responsibility, coverage, command, or result-surface contracts.".to_string(),
        String::new(),
        "Return JSON with these top-level keys for this part:".to_string(),
        "- schema: agent_canon.local_llm.prose_ir.v1".to_string(),
        format!("- part_id: {part_id}"),
        "- documents[]: path, title, declared responsibility, section roles, and tool/doc responsibility coverage cues".to_string(),
        "- corpus_hints[]: corpus_id, label, score, selected, basis.signals; basis must explain the domain calibration, not just echo words".to_string(),
        "- analysis_intents[]: intent, status, field_kinds, vocabulary_kinds, and basis; mark experiment_plan as present only for actual plan assignments, not vocabulary explanations".to_string(),
        "- term_contexts[]: term, path, snippet, and role in the document; omit boilerplate-only matches".to_string(),
        "- dsl_seed.nodes[]: source/form/concept/argument/evidence/experiment/presentation candidates anchored to document spans when possible".to_string(),
        "- dsl_seed.edges[]: typed relations such as contains, follows, supports, requires, refines, generalizes, concludes, mentions, and verifies".to_string(),
        "- diagnostic_candidates[]: unsupported_claim, weak_bridge, missing_metric, missing_artifact_contract, or unresolved_boundary with verification_route".to_string(),
        "- presentation_candidates[]: table, figure, list, or equation recommendations grounded in graph structure".to_string(),
        String::new(),
        "For tool explanation documents, explicitly extract:".to_string(),
        "- command surface: command names, flags, default paths, stats keys, and generated artifacts".to_string(),
        "- result surface: what is written to files or SQLite versus what may appear on stdout".to_string(),
        "- authority boundary: what the tool diagnoses versus what another skill or reviewer must decide".to_string(),
        "- verification route: logic, evidence, experiment, document responsibility, and connection checks".to_string(),
        "- partition boundary: which documents and terms are inside this part, and what must be left for the merge stage".to_string(),
        String::new(),
        "Prompt context:".to_string(),
        prompt_context.to_string(),
        String::new(),
        "Terms:".to_string(),
    ];
    if terms.is_empty() {
        lines.push("- <derive salient concepts from documents>".to_string());
    } else {
        for term in terms {
            lines.push(format!("- {term}"));
        }
    }
    lines.push(String::new());
    lines.push("Documents:".to_string());
    for document in documents {
        lines.push(format!("## {}", document.relative_path));
        lines.push(format!("title: {}", document.title));
        if !document.responsibility.is_empty() {
            lines.push(format!("responsibility: {}", document.responsibility));
        }
        lines.push("```".to_string());
        lines.push(document.text.clone());
        lines.push("```".to_string());
    }
    lines.join("\n")
}

fn prose_ir_part_llm_results(
    part_prompts: &[ProseIrPromptPart],
    args: &ProseIrArgs,
) -> Vec<ProseIrPartLlmResult> {
    if part_prompts.is_empty() {
        return Vec::new();
    }
    let executable = find_llama_cli(&args.llama_cli);
    if executable.is_empty() {
        return part_prompts
            .iter()
            .map(|part| ProseIrPartLlmResult {
                part_id: part.part_id.clone(),
                prompt_sha: prompt_digest(&part.prompt),
                status: "skipped_llama_cli_not_found".to_string(),
                stdout: String::new(),
                stderr: String::new(),
            })
            .collect();
    }

    let jobs = args.llm_jobs.max(1).min(part_prompts.len());
    let mut results = Vec::with_capacity(part_prompts.len());
    for chunk in part_prompts.chunks(jobs) {
        let mut handles = Vec::with_capacity(chunk.len());
        for part in chunk {
            let part_id = part.part_id.clone();
            let prompt_sha = prompt_digest(&part.prompt);
            let command = LlamaCommand {
                executable: executable.clone(),
                model: args.model.clone(),
                prompt: part.prompt.clone(),
                predict_tokens: args.predict_tokens,
            };
            let handle = thread::spawn(move || match run_llama_prompt(&command) {
                Ok((stdout, stderr)) => ProseIrPartLlmResult {
                    part_id,
                    prompt_sha,
                    status: "pass".to_string(),
                    stdout,
                    stderr,
                },
                Err(error) => ProseIrPartLlmResult {
                    part_id,
                    prompt_sha,
                    status: "fail".to_string(),
                    stdout: String::new(),
                    stderr: error,
                },
            });
            handles.push((part.part_id.clone(), prompt_digest(&part.prompt), handle));
        }
        for (part_id, prompt_sha, handle) in handles {
            match handle.join() {
                Ok(result) => results.push(result),
                Err(_) => results.push(ProseIrPartLlmResult {
                    part_id,
                    prompt_sha,
                    status: "panic".to_string(),
                    stdout: String::new(),
                    stderr: "llama-thread-panicked".to_string(),
                }),
            }
        }
    }
    results
}

fn prose_ir_payload(
    args: &ProseIrArgs,
    documents: &[ProseIrDocument],
    terms: &[String],
    prompt_context: &str,
    prompt_digest: &str,
    part_llm_results: &[ProseIrPartLlmResult],
) -> Value {
    let derived_terms = if terms.is_empty() {
        extract_salient_terms(documents)
    } else {
        terms.to_vec()
    };
    let document_payloads: Vec<Value> = documents
        .iter()
        .enumerate()
        .map(|(index, document)| {
            json!({
                "document_id": format!("local-llm:doc:{}", index + 1),
                "path": document.relative_path,
                "title": document.title,
                "kind": document.kind,
                "responsibility": document.responsibility,
                "sections": markdown_sections(document),
                "corpus_signals": corpus_signals_for_text(&format!(
                    "{}\n{}\n{}\n{}",
                    document.relative_path, document.title, document.responsibility, document.text
                )),
                "term_contexts": term_contexts_for_document(document, &derived_terms),
            })
        })
        .collect();
    let term_payloads: Vec<Value> = derived_terms
        .iter()
        .enumerate()
        .map(|(index, term)| {
            json!({
                "term_id": format!("local-llm:term:{}", index + 1),
                "text": term,
                "contexts": documents
                    .iter()
                    .flat_map(|document| {
                        term_contexts_for_document(document, std::slice::from_ref(term))
                    })
                    .collect::<Vec<Value>>(),
            })
        })
        .collect();
    let corpus_hints = corpus_hints_for_ir(documents, &derived_terms, prompt_context);
    let parts = prose_ir_part_records(documents, &derived_terms, args, part_llm_results);
    let analysis_intents = analysis_intents_for_ir(documents);
    json!({
        "schema": "agent_canon.local_llm.prose_ir.v1",
        "task_owner": "local_llm",
        "status": "extracted_intermediate_representation",
        "model": args.model,
        "prompt_sha": prompt_digest,
        "root": args.root.to_string_lossy(),
        "document_count": documents.len(),
        "term_count": derived_terms.len(),
        "part_count": parts.len(),
        "llm_execution": prose_ir_llm_execution_summary(args, part_llm_results),
        "partition": {
            "document_batch_size": args.document_batch_size.max(1),
            "term_batch_size": args.term_batch_size.max(1),
        },
        "parts": parts,
        "documents": document_payloads,
        "terms": term_payloads,
        "corpus_hints": corpus_hints,
        "analysis_intents": analysis_intents,
        "dsl_seed": dsl_seed(documents, &derived_terms),
    })
}

fn prose_ir_part_records(
    documents: &[ProseIrDocument],
    terms: &[String],
    args: &ProseIrArgs,
    part_llm_results: &[ProseIrPartLlmResult],
) -> Vec<Value> {
    let document_batch_size = args.document_batch_size.max(1);
    let term_batch_size = args.term_batch_size.max(1);
    let llm_by_part = part_llm_results
        .iter()
        .map(|result| (result.part_id.as_str(), result))
        .collect::<BTreeMap<_, _>>();
    let term_chunks: Vec<&[String]> = if terms.is_empty() {
        vec![&[]]
    } else {
        terms.chunks(term_batch_size).collect()
    };
    let mut parts = Vec::new();
    for (document_batch_index, document_batch) in documents.chunks(document_batch_size).enumerate()
    {
        for (term_batch_index, term_batch) in term_chunks.iter().enumerate() {
            let document_paths = document_batch
                .iter()
                .map(|document| document.relative_path.clone())
                .collect::<Vec<_>>();
            let part_id = format!(
                "part:d{}:t{}",
                document_batch_index + 1,
                term_batch_index + 1
            );
            let mut record = json!({
                "part_id": part_id.clone(),
                "document_paths": document_paths,
                "terms": term_batch.to_vec(),
                "status": "extracted_and_merged",
            });
            if let Some(result) = llm_by_part.get(part_id.as_str()) {
                if let Some(object) = record.as_object_mut() {
                    object.insert("llm_status".to_string(), json!(result.status));
                    object.insert("llm_prompt_sha".to_string(), json!(result.prompt_sha));
                    if let Some(output) = prose_ir_part_llm_output(result) {
                        object.insert("llm_output".to_string(), output);
                    }
                    if !result.stderr.trim().is_empty() {
                        object.insert("llm_stderr".to_string(), json!(result.stderr.trim()));
                    }
                }
            }
            parts.push(record);
        }
    }
    parts
}

fn prose_ir_part_llm_output(result: &ProseIrPartLlmResult) -> Option<Value> {
    let trimmed = result.stdout.trim();
    if trimmed.is_empty() {
        return None;
    }
    serde_json::from_str::<Value>(trimmed)
        .map(Some)
        .unwrap_or_else(|_| Some(json!({ "raw": trimmed })))
}

fn prose_ir_llm_execution_summary(args: &ProseIrArgs, results: &[ProseIrPartLlmResult]) -> Value {
    let pass_count = results
        .iter()
        .filter(|result| result.status == "pass")
        .count();
    let skipped_count = results
        .iter()
        .filter(|result| result.status == "skipped_llama_cli_not_found")
        .count();
    let failed_count = results.len().saturating_sub(pass_count + skipped_count);
    let status = if results.is_empty() {
        "not_applicable"
    } else if skipped_count == results.len() {
        "skipped_llama_cli_not_found"
    } else if pass_count == results.len() {
        "completed"
    } else if pass_count > 0 {
        "partial_failure"
    } else {
        "failed"
    };
    json!({
        "status": status,
        "strategy": "per_part_bounded_parallel",
        "jobs": args.llm_jobs.max(1).min(results.len().max(1)),
        "configured_jobs": args.llm_jobs.max(1),
        "predict_tokens": args.predict_tokens,
        "part_count": results.len(),
        "attempted": pass_count + failed_count > 0,
        "passed": pass_count,
        "failed": failed_count,
        "skipped": skipped_count,
    })
}

fn infer_markdown_title(text: &str, path: &Path) -> String {
    for line in text.lines() {
        if let Some(title) = line.strip_prefix("# ") {
            let title = title.trim();
            if !title.is_empty() {
                return title.to_string();
            }
        }
    }
    path.file_stem()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "document".to_string())
}

fn infer_dependency_responsibility(text: &str) -> String {
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("responsibility ") {
            return rest.trim().trim_end_matches('.').to_string();
        }
        if let Some(rest) = trimmed.strip_prefix("# responsibility ") {
            return rest.trim().trim_end_matches('.').to_string();
        }
        if let Some(rest) = trimmed.strip_prefix("// responsibility ") {
            return rest.trim().trim_end_matches('.').to_string();
        }
    }
    String::new()
}

fn prose_ir_kind(path: &Path) -> String {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
    {
        "md" | "markdown" => "markdown".to_string(),
        "txt" => "plain_text".to_string(),
        "py" | "rs" | "cpp" | "cc" | "c" | "h" | "hpp" | "sh" => "code_text".to_string(),
        other if !other.is_empty() => format!("text_like:{other}"),
        _ => "text_like".to_string(),
    }
}

fn markdown_sections(document: &ProseIrDocument) -> Vec<Value> {
    let mut sections = Vec::new();
    for (line_index, line) in document.text.lines().enumerate() {
        let trimmed = line.trim_start();
        if !trimmed.starts_with('#') {
            continue;
        }
        let level = trimmed
            .chars()
            .take_while(|character| *character == '#')
            .count();
        if level == 0 || level > 6 {
            continue;
        }
        let title = trimmed[level..].trim();
        if title.is_empty() {
            continue;
        }
        sections.push(json!({
            "section_id": format!("{}#{}", document.relative_path, line_index + 1),
            "level": level,
            "title": title,
            "line": line_index + 1,
            "role": section_role(title),
        }));
    }
    if sections.is_empty() {
        sections.push(json!({
            "section_id": format!("{}#body", document.relative_path),
            "level": 1,
            "title": document.title,
            "line": 1,
            "role": "body",
        }));
    }
    sections
}

fn section_role(title: &str) -> String {
    let lower = title.to_lowercase();
    if contains_any(&lower, &["purpose", "目的", "overview", "summary", "概要"]) {
        return "purpose_or_overview".to_string();
    }
    if contains_any(&lower, &["design", "設計", "contract", "仕様", "dsl"]) {
        return "design_contract".to_string();
    }
    if contains_any(&lower, &["usage", "使い", "command", "実行", "runtime"]) {
        return "runtime_usage".to_string();
    }
    if contains_any(&lower, &["validation", "test", "検証", "評価", "metric"]) {
        return "validation".to_string();
    }
    "body".to_string()
}

fn term_contexts_for_document(document: &ProseIrDocument, terms: &[String]) -> Vec<Value> {
    let lower_text = document.text.to_lowercase();
    let mut contexts = Vec::new();
    for term in terms {
        let lower_term = term.to_lowercase();
        if lower_term.is_empty() {
            continue;
        }
        if let Some(byte_index) = lower_text.find(&lower_term) {
            contexts.push(json!({
                "term": term,
                "path": document.relative_path,
                "snippet": snippet_at(&document.text, byte_index, term.len()),
            }));
        }
    }
    contexts
}

fn snippet_at(text: &str, byte_index: usize, term_len: usize) -> String {
    let start = text[..byte_index]
        .char_indices()
        .rev()
        .nth(80)
        .map(|(index, _)| index)
        .unwrap_or(0);
    let end_seed = byte_index.saturating_add(term_len);
    let end = text[end_seed..]
        .char_indices()
        .nth(80)
        .map(|(index, _)| end_seed + index)
        .unwrap_or_else(|| text.len());
    text[start..end].replace('\n', " ").trim().to_string()
}

fn extract_salient_terms(documents: &[ProseIrDocument]) -> Vec<String> {
    let mut terms = Vec::new();
    for document in documents {
        for token in document.text.split(|character: char| {
            !character.is_alphanumeric() && character != '_' && character != '-'
        }) {
            let token = token.trim_matches('-');
            if token.len() < 4 || token.chars().all(|character| character.is_numeric()) {
                continue;
            }
            let lower = token.to_lowercase();
            if prose_ir_stopword(&lower) {
                continue;
            }
            terms.push(token.to_string());
            if terms.len() >= 16 {
                return unique_nonempty(terms);
            }
        }
    }
    unique_nonempty(terms)
}

fn prose_ir_stopword(value: &str) -> bool {
    matches!(
        value,
        "that"
            | "this"
            | "with"
            | "from"
            | "into"
            | "should"
            | "must"
            | "because"
            | "document"
            | "source"
            | "graph"
            | "prose"
    )
}

fn corpus_hints_for_ir(
    documents: &[ProseIrDocument],
    terms: &[String],
    prompt_context: &str,
) -> Vec<Value> {
    let mut basis = String::new();
    basis.push_str(prompt_context);
    for document in documents {
        basis.push('\n');
        basis.push_str(&document.relative_path);
        basis.push('\n');
        basis.push_str(&document.title);
        basis.push('\n');
        basis.push_str(&document.responsibility);
        basis.push('\n');
        basis.push_str(&document.text);
    }
    for term in terms {
        basis.push('\n');
        basis.push_str(term);
    }
    let mut hints = Vec::new();
    for (corpus_id, label, score, signals) in corpus_hint_scores(&basis) {
        if score > 0 {
            hints.push(json!({
                "corpus_id": corpus_id,
                "label": label,
                "score": score,
                "basis": {
                    "source": "local_llm_prose_ir",
                    "signals": signals,
                },
            }));
        }
    }
    if hints.is_empty() {
        hints.push(json!({
            "corpus_id": "general_prose",
            "label": "General prose and document-structure corpus",
            "score": 0,
            "basis": {
                "source": "local_llm_prose_ir",
                "signals": [],
            },
        }));
    }
    hints.sort_by(|left, right| {
        let left_score = left.get("score").and_then(Value::as_i64).unwrap_or(0);
        let right_score = right.get("score").and_then(Value::as_i64).unwrap_or(0);
        right_score.cmp(&left_score).then_with(|| {
            left.get("corpus_id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .cmp(
                    right
                        .get("corpus_id")
                        .and_then(Value::as_str)
                        .unwrap_or_default(),
                )
        })
    });
    for (index, hint) in hints.iter_mut().enumerate() {
        if let Some(object) = hint.as_object_mut() {
            object.insert("selected".to_string(), json!(index == 0));
        }
    }
    hints
}

fn corpus_hint_scores(text: &str) -> Vec<(&'static str, &'static str, i64, Vec<String>)> {
    let lower = text.to_lowercase();
    vec![
        corpus_hint_score(
            &lower,
            "academic_writing",
            "Academic writing and discourse-structure corpus",
            &[
                "academic",
                "paper",
                "citation",
                "rst",
                "pdtb",
                "学術",
                "論文",
                "文献",
                "文章構造",
                "コーパス",
            ],
        ),
        corpus_hint_score(
            &lower,
            "software_engineering",
            "Software engineering documents and code corpus",
            &[
                "python",
                "rust",
                "cpp",
                "c++",
                "shell",
                "code",
                "implementation",
                "agentcanon",
                "dsl",
                "コード",
                "実装",
                "依存",
            ],
        ),
        corpus_hint_score(
            &lower,
            "experimental_report",
            "Experimental planning and evaluation report corpus",
            &[
                "experiment",
                "hypothesis",
                "metric",
                "baseline",
                "expected",
                "実験",
                "仮説",
                "指標",
                "ベースライン",
                "評価",
            ],
        ),
        corpus_hint_score(
            &lower,
            "formal_reasoning",
            "Formal reasoning, mathematics, and equation-heavy corpus",
            &[
                "theorem", "proof", "lemma", "equation", "formula", "定理", "証明", "数式", "数学",
            ],
        ),
    ]
}

fn corpus_hint_score(
    lower: &str,
    corpus_id: &'static str,
    label: &'static str,
    signals: &[&str],
) -> (&'static str, &'static str, i64, Vec<String>) {
    let hits: Vec<String> = signals
        .iter()
        .filter(|signal| lower.contains(**signal))
        .map(|signal| signal.to_string())
        .collect();
    (corpus_id, label, hits.len() as i64, hits)
}

fn corpus_signals_for_text(text: &str) -> Vec<String> {
    corpus_hint_scores(text)
        .into_iter()
        .flat_map(|(_, _, _, signals)| signals)
        .collect()
}

fn dsl_seed(documents: &[ProseIrDocument], terms: &[String]) -> Value {
    let mut nodes = Vec::new();
    let mut edges = Vec::new();
    for (document_index, document) in documents.iter().enumerate() {
        let doc_id = format!("local-llm:doc:{}", document_index + 1);
        nodes.push(json!({
            "id": doc_id,
            "layer": "source",
            "kind": "document",
            "label": document.title,
            "path": document.relative_path,
        }));
        for (section_index, section) in markdown_sections(document).into_iter().enumerate() {
            let section_id = format!(
                "local-llm:section:{}:{}",
                document_index + 1,
                section_index + 1
            );
            nodes.push(json!({
                "id": section_id,
                "layer": "form",
                "kind": "section",
                "label": section.get("title").and_then(Value::as_str).unwrap_or("section"),
                "path": document.relative_path,
                "payload": section,
            }));
            edges.push(json!({
                "id": format!("local-llm:edge:contains:{}:{}", document_index + 1, section_index + 1),
                "layer": "form",
                "kind": "contains",
                "from": doc_id,
                "to": section_id,
            }));
            if section_index > 0 {
                edges.push(json!({
                    "id": format!("local-llm:edge:follows:{}:{}", document_index + 1, section_index + 1),
                    "layer": "form",
                    "kind": "follows",
                    "from": format!("local-llm:section:{}:{}", document_index + 1, section_index),
                    "to": section_id,
                }));
            }
        }
    }
    for (term_index, term) in terms.iter().enumerate() {
        let term_id = format!("local-llm:term:{}", term_index + 1);
        nodes.push(json!({
            "id": term_id,
            "layer": "concept",
            "kind": "term",
            "label": term,
        }));
        for (document_index, document) in documents.iter().enumerate() {
            if document.text.to_lowercase().contains(&term.to_lowercase()) {
                edges.push(json!({
                    "id": format!("local-llm:edge:mentions:{}:{}", document_index + 1, term_index + 1),
                    "layer": "concept",
                    "kind": "mentions",
                    "from": format!("local-llm:doc:{}", document_index + 1),
                    "to": term_id,
                    "path": document.relative_path,
                }));
            }
        }
    }
    json!({
        "nodes": nodes,
        "edges": edges,
    })
}

fn analysis_intents_for_ir(documents: &[ProseIrDocument]) -> Vec<Value> {
    documents.iter().map(experiment_plan_intent).collect()
}

fn experiment_plan_intent(document: &ProseIrDocument) -> Value {
    let assignment_kinds = experiment_assignment_kinds(&document.text);
    let vocabulary_kinds = experiment_vocabulary_kinds(&document.text);
    let has_activity = contains_experiment_activity_cue(&document.text);
    let status = if assignment_kinds.len() >= 2 || (!assignment_kinds.is_empty() && has_activity) {
        "present"
    } else if !vocabulary_kinds.is_empty() {
        "vocabulary_only"
    } else {
        "absent"
    };
    json!({
        "intent": "experiment_plan",
        "path": document.relative_path,
        "status": status,
        "field_kinds": assignment_kinds,
        "vocabulary_kinds": vocabulary_kinds,
        "basis": "local_llm_prose_ir",
    })
}

fn contains_experiment_activity_cue(text: &str) -> bool {
    let lowered = text.to_lowercase();
    contains_standalone_ascii_cue(&lowered, "experiment")
        || contains_standalone_ascii_cue(&lowered, "protocol")
        || text.contains("実験")
}

fn contains_standalone_ascii_cue(lowered_text: &str, cue: &str) -> bool {
    lowered_text.match_indices(cue).any(|(index, _)| {
        let before = lowered_text[..index].chars().next_back();
        let after = lowered_text[index + cue.len()..].chars().next();
        !is_ascii_wordish(before) && !is_ascii_wordish(after)
    })
}

fn is_ascii_wordish(value: Option<char>) -> bool {
    matches!(value, Some(character) if character.is_ascii_alphanumeric() || character == '_' || character == '-')
}

fn experiment_assignment_kinds(text: &str) -> Vec<String> {
    let lowered = text.to_lowercase();
    let mut kinds = Vec::new();
    if has_assignment(&lowered, "hypothesis") || text.contains("仮説は") {
        kinds.push("hypothesis".to_string());
    }
    if has_assignment(&lowered, "metric") || text.contains("指標は") {
        kinds.push("metric".to_string());
    }
    if has_assignment(&lowered, "baseline") || text.contains("ベースラインは") {
        kinds.push("baseline".to_string());
    }
    if has_assignment(&lowered, "expected")
        || has_assignment(&lowered, "expected result")
        || text.contains("期待結果は")
        || text.contains("期待は")
    {
        kinds.push("expected_result".to_string());
    }
    kinds
}

fn has_assignment(lowered_text: &str, field: &str) -> bool {
    lowered_text.contains(&format!("{field} is"))
        || lowered_text.contains(&format!("{field} ="))
        || lowered_text.contains(&format!("{field}:"))
}

fn experiment_vocabulary_kinds(text: &str) -> Vec<String> {
    let lowered = text.to_lowercase();
    let mut kinds = Vec::new();
    for (kind, cues) in [
        ("hypothesis", &["hypothesis", "仮説"][..]),
        ("metric", &["metric", "指標"][..]),
        ("baseline", &["baseline", "ベースライン"][..]),
        ("expected_result", &["expected", "期待"][..]),
    ] {
        if cues.iter().any(|cue| lowered.contains(&cue.to_lowercase())) {
            kinds.push(kind.to_string());
        }
    }
    kinds
}

fn unique_nonempty(values: Vec<String>) -> Vec<String> {
    let mut unique = Vec::new();
    for value in values {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            continue;
        }
        if !unique
            .iter()
            .any(|item: &String| item.eq_ignore_ascii_case(trimmed))
        {
            unique.push(trimmed.to_string());
        }
    }
    unique
}

fn contains_any(text: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| text.contains(needle))
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
    let mut process = Command::new(&command.executable);
    apply_local_llm_cpu_env(&mut process);
    let output = process.args(command.args()).output();
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

fn run_llama_prompt(command: &LlamaCommand) -> Result<(String, String), String> {
    let mut process = Command::new(&command.executable);
    apply_local_llm_cpu_env(&mut process);
    let output = process
        .args(command.args())
        .output()
        .map_err(|error| format!("llama-launch-failed:{error}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    if output.status.success() {
        Ok((stdout, stderr))
    } else {
        Err(format!(
            "llama-exit-status:{}:{}",
            output.status.code().unwrap_or(1),
            stderr.trim()
        ))
    }
}

fn apply_local_llm_cpu_env(command: &mut Command) {
    for (key, value) in LOCAL_LLM_CPU_ENV {
        command.env(key, value);
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

fn default_prose_ir_llm_jobs() -> usize {
    env::var("AGENT_CANON_LOCAL_LLM_PROSE_IR_JOBS")
        .or_else(|_| env::var("AGENT_CANON_LOCAL_LLM_JOBS"))
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_PROSE_IR_LLM_JOBS)
}

fn build_invocation(args: &LocalLlmArgs) -> Result<PythonInvocation, String> {
    let source_root = source_root_for(&args.root)?;
    let (script, prefix_args) = match args.command {
        LocalLlmCommand::ClassifyResponsibility => return Err("native-rust-command".to_string()),
        LocalLlmCommand::ExtractProseIr => return Err("native-rust-command".to_string()),
        LocalLlmCommand::RouteImplementationSurface => {
            return Err("native-rust-command".to_string())
        }
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
        "usage: agent-canon local-llm <classify-responsibility|review-file|extract-prose-ir|prose-ir|route-implementation-surface|search|build-index|eval> [--root <repo-root>] [tool args...]"
    );
    eprintln!(
        "examples: agent-canon local-llm classify-responsibility --print-prompt tools/agent_tools/search.py"
    );
    eprintln!(
        "          agent-canon local-llm extract-prose-ir --json-out /tmp/prose-ir.json --term DSL docs/spec.md docs/tool.md"
    );
    eprintln!(
        "          agent-canon local-llm search --purpose \"find responsibility scope tooling\""
    );
    eprintln!(
        "          agent-canon local-llm route-implementation-surface --request-file reports/task.txt --format text"
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
    fn local_llm_command_envelope_hides_accelerator_devices() {
        let mut command = Command::new("llama-cli");
        apply_local_llm_cpu_env(&mut command);

        let envs = command
            .get_envs()
            .map(|(key, value)| {
                (
                    key.to_string_lossy().to_string(),
                    value.map(|item| item.to_string_lossy().to_string()),
                )
            })
            .collect::<BTreeMap<_, _>>();

        assert_eq!(envs.get("CUDA_VISIBLE_DEVICES"), Some(&Some(String::new())));
        assert_eq!(
            envs.get("NVIDIA_VISIBLE_DEVICES"),
            Some(&Some("void".to_string()))
        );
        assert_eq!(envs.get("HIP_VISIBLE_DEVICES"), Some(&Some(String::new())));
        assert_eq!(envs.get("ROCR_VISIBLE_DEVICES"), Some(&Some(String::new())));
    }

    #[test]
    fn parses_implementation_surface_route_request_file() {
        let args = vec![
            "route-implementation-surface".to_string(),
            "--root".to_string(),
            "fixture".to_string(),
            "--request-file".to_string(),
            "reports/task.txt".to_string(),
            "--format".to_string(),
            "json".to_string(),
        ];
        let parsed = LocalLlmArgs::parse(&args).expect("parse local llm args");

        assert_eq!(parsed.command, LocalLlmCommand::RouteImplementationSurface);
        assert_eq!(parsed.root, PathBuf::from("fixture"));
        let route_args =
            RouteImplementationSurfaceArgs::parse(parsed.root.clone(), &parsed.passthrough)
                .expect("parse route args");
        assert_eq!(
            route_args.request_files,
            vec![PathBuf::from("reports/task.txt")]
        );
        assert_eq!(route_args.format, RouteOutputFormat::Json);
    }

    #[test]
    fn implementation_surface_route_prioritizes_local_llm_tool() {
        let request = "実装前に責務判定するルーターを local LLM で作り、AGENTS.md にも書く";
        let candidates = implementation_surface_candidates(request);

        assert_eq!(candidates[0].surface, "agentcanon_local_llm_tool");
        assert!(candidates
            .iter()
            .any(|candidate| candidate.surface == "agent_runtime_instructions"));
        let prompt = prompt_for_implementation_surface_route(request, &candidates);
        assert!(prompt.contains("implementation-surface router"));
        assert!(prompt.contains("Return JSON only"));
    }

    #[test]
    fn implementation_surface_route_detects_personal_codex_runtime() {
        let request =
            "~/.codex の config と user skill が repo routing と衝突していないか見て修正する";
        let candidates = implementation_surface_candidates(request);

        assert_eq!(candidates[0].surface, "personal_codex_runtime");
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("$HOME/.codex/config.toml")));
        assert!(candidates[0]
            .forbidden_paths
            .iter()
            .any(|path| path.contains("auth")));
    }

    #[test]
    fn implementation_surface_route_detects_iterative_algorithm_contract() {
        let request =
            "反復法の solver 実装で convergence と residual の stopping policy を直したい";
        let candidates = implementation_surface_candidates(request);

        assert_eq!(
            candidates[0].surface,
            "numerical_iterative_algorithm_contract"
        );
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("computational-optimization")));
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("algorithm-implementation-boundary")));
        assert!(candidates[0]
            .required_checks
            .iter()
            .any(|command| command.contains("python-algorithm-contract-check")));
    }

    #[test]
    fn implementation_surface_route_detects_contract_only_test_policy() {
        let request = "契約だけの wrapper で runtime behavior を増やしていないので pytest smoke, execution-only test, no-crash test, 数値テストを足さず static contract validation と canonical command evidence に戻したい";
        let candidates = implementation_surface_candidates(request);

        assert_eq!(candidates[0].surface, "contract_only_test_policy");
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("coding-conventions-testing")));
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("test-design")));
        assert!(candidates[0]
            .required_checks
            .iter()
            .any(|command| command.contains("check_convention_compliance.py")));
    }

    #[test]
    fn implementation_surface_route_detects_document_claim_grounding() {
        let request = "Canonical documents are treated as source authority, but mathematical statements and provisional wording such as まずは become ad hoc policy; route to checker evidence and proof obligation.";
        let candidates = implementation_surface_candidates(request);

        assert_eq!(candidates[0].surface, "document_claim_grounding");
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("05_docs.md")));
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("formal-proof-workflow")));
        assert!(candidates[0]
            .required_checks
            .iter()
            .any(|command| command.contains("check_convention_compliance.py")));
    }

    #[test]
    fn implementation_surface_route_detects_program_contract() {
        let request = "プログラムの契約を public entrypoint, input schema, return projection, observable effect, preconditions, validation command として明示したい。";
        let candidates = implementation_surface_candidates(request);

        assert_eq!(candidates[0].surface, "document_claim_grounding");
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("formal-proof-workflow")));
        assert!(candidates[0]
            .canonical_paths
            .iter()
            .any(|path| path.contains("long-form-writing")));
        assert!(candidates[0].rationale.iter().any(
            |reason| reason.contains("program contract") || reason.contains("プログラムの契約")
        ));
    }

    #[test]
    fn implementation_surface_route_payload_is_structured() {
        let request = "Skill routing should choose where to edit before implementation.";
        let candidates = implementation_surface_candidates(request);
        let decision = SurfaceRouteDecision {
            request: request.to_string(),
            prompt_digest: "abc123".to_string(),
            model: DEFAULT_MODEL.to_string(),
            llm_status: "local_llm_advisory".to_string(),
            llm_output: String::new(),
            candidates,
        };

        let payload = implementation_surface_route_payload(&decision);

        assert_eq!(
            payload["schema"],
            "agent_canon.local_llm.implementation_surface_route.v1"
        );
        assert!(payload["primary_surface"].as_str().is_some());
        assert!(!payload["required_pre_edit_checks"]
            .as_array()
            .expect("required checks")
            .is_empty());
        assert!(!payload["candidates"]
            .as_array()
            .expect("candidates")
            .is_empty());
    }

    #[test]
    fn implementation_surface_route_fallback_is_structured_without_llm() {
        let request = "Agents are writing implementation into the wrong directory.";
        let candidates = implementation_surface_candidates(request);
        let decision = SurfaceRouteDecision {
            request: request.to_string(),
            prompt_digest: "fallback123".to_string(),
            model: DEFAULT_MODEL.to_string(),
            llm_status: "deterministic_candidate_fallback".to_string(),
            llm_output: "llama-cli not found; using deterministic candidate ranking".to_string(),
            candidates,
        };

        let payload = implementation_surface_route_payload(&decision);

        assert_eq!(payload["status"], "deterministic_candidate_fallback");
        assert!(payload["primary_paths"]
            .as_array()
            .expect("primary paths")
            .iter()
            .any(|path| path.as_str().expect("path").contains("responsibility")));
        assert!(!payload["forbidden_paths"]
            .as_array()
            .expect("forbidden paths")
            .is_empty());
    }

    #[test]
    fn parses_batch_prose_ir_inputs() {
        let args = vec![
            "extract-prose-ir".to_string(),
            "--root".to_string(),
            "fixture".to_string(),
            "--term".to_string(),
            "DSL".to_string(),
            "--llama-cli".to_string(),
            "fake-llama-cli".to_string(),
            "--predict-tokens".to_string(),
            "64".to_string(),
            "--llm-jobs".to_string(),
            "3".to_string(),
            "--json-out".to_string(),
            "out.json".to_string(),
            "docs/one.md".to_string(),
            "docs/two.md".to_string(),
        ];
        let parsed = LocalLlmArgs::parse(&args).expect("parse local llm args");

        assert_eq!(parsed.command, LocalLlmCommand::ExtractProseIr);
        assert_eq!(parsed.root, PathBuf::from("fixture"));
        assert!(parsed.has_root_argument());
        let prose_args =
            ProseIrArgs::parse(parsed.root, &parsed.passthrough).expect("parse prose ir args");
        assert_eq!(prose_args.files, vec!["docs/one.md", "docs/two.md"]);
        assert_eq!(prose_args.terms, vec!["DSL"]);
        assert_eq!(prose_args.llama_cli, "fake-llama-cli");
        assert_eq!(prose_args.predict_tokens, 64);
        assert_eq!(prose_args.llm_jobs, 3);
        assert_eq!(prose_args.json_out, Some(PathBuf::from("out.json")));
    }

    #[test]
    fn prose_ir_payload_returns_intermediate_representation() {
        let root = make_fixture_root();
        let first = root.join("docs/one.md");
        let second = root.join("docs/two.md");
        fs::create_dir_all(first.parent().expect("docs parent")).expect("mkdir docs");
        fs::write(
            &first,
            "# One\n\n<!--\n@dependency-start\nresponsibility Documents academic DSL usage.\n@dependency-end\n-->\n\nThe DSL connects graph evidence.",
        )
        .expect("write first");
        fs::write(&second, "# Two\n\nRust code documentation mentions DSL.").expect("write second");
        let args = ProseIrArgs {
            root: root.clone(),
            files: vec!["docs/one.md".to_string(), "docs/two.md".to_string()],
            terms: vec!["DSL".to_string()],
            terms_files: Vec::new(),
            prompt: "academic Python/Rust paper".to_string(),
            prompt_files: Vec::new(),
            model: DEFAULT_MODEL.to_string(),
            llama_cli: String::new(),
            max_bytes: DEFAULT_MAX_BYTES,
            predict_tokens: DEFAULT_PREDICT_TOKENS,
            document_batch_size: 1,
            term_batch_size: 1,
            llm_jobs: 2,
            json_out: None,
            print_prompt: false,
        };
        let documents = args
            .files
            .iter()
            .map(|file| read_prose_ir_document(&args.root, file, args.max_bytes).expect("read doc"))
            .collect::<Vec<_>>();
        let prompt_parts = prompt_parts_for_prose_ir(&documents, &args.terms, &args.prompt, &args);
        let part_llm_results = vec![
            ProseIrPartLlmResult {
                part_id: "part:d2:t1".to_string(),
                prompt_sha: "second".to_string(),
                status: "pass".to_string(),
                stdout: "{\"part\":\"second\"}".to_string(),
                stderr: String::new(),
            },
            ProseIrPartLlmResult {
                part_id: "part:d1:t1".to_string(),
                prompt_sha: "first".to_string(),
                status: "pass".to_string(),
                stdout: "{\"part\":\"first\"}".to_string(),
                stderr: String::new(),
            },
        ];
        assert_eq!(prompt_parts.len(), 2);
        let payload = prose_ir_payload(
            &args,
            &documents,
            &args.terms,
            &args.prompt,
            "abc123",
            &part_llm_results,
        );

        assert_eq!(payload["schema"], "agent_canon.local_llm.prose_ir.v1");
        assert_eq!(payload["document_count"], 2);
        assert_eq!(payload["term_count"], 1);
        assert_eq!(payload["part_count"], 2);
        assert_eq!(payload["llm_execution"]["status"], "completed");
        assert_eq!(payload["llm_execution"]["jobs"], 2);
        let parts = payload["parts"].as_array().expect("parts");
        assert_eq!(parts[0]["part_id"], "part:d1:t1");
        assert_eq!(parts[0]["llm_prompt_sha"], "first");
        assert_eq!(parts[0]["llm_output"]["part"], "first");
        assert_eq!(parts[1]["part_id"], "part:d2:t1");
        assert_eq!(parts[1]["llm_prompt_sha"], "second");
        assert!(payload["documents"].as_array().expect("documents").len() == 2);
        assert!(
            payload["dsl_seed"]["nodes"]
                .as_array()
                .expect("nodes")
                .len()
                >= 3
        );
        let corpus_hints = payload["corpus_hints"].as_array().expect("corpus hints");
        assert!(corpus_hints
            .iter()
            .any(|item| item["corpus_id"].as_str() == Some("academic_writing")));
        assert!(corpus_hints
            .iter()
            .any(|item| item["corpus_id"].as_str() == Some("software_engineering")));
        let analysis_intents = payload["analysis_intents"]
            .as_array()
            .expect("analysis intents");
        assert_eq!(analysis_intents.len(), 2);
        assert!(analysis_intents
            .iter()
            .all(|item| item["intent"].as_str() == Some("experiment_plan")));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prose_ir_part_llm_results_skip_when_llama_cli_is_missing() {
        let root = make_fixture_root();
        let args = ProseIrArgs {
            root: root.clone(),
            files: vec!["docs/one.md".to_string()],
            terms: Vec::new(),
            terms_files: Vec::new(),
            prompt: String::new(),
            prompt_files: Vec::new(),
            model: DEFAULT_MODEL.to_string(),
            llama_cli: root.join("missing-llama-cli").to_string_lossy().to_string(),
            max_bytes: DEFAULT_MAX_BYTES,
            predict_tokens: 16,
            document_batch_size: 1,
            term_batch_size: 1,
            llm_jobs: 2,
            json_out: None,
            print_prompt: false,
        };
        let parts = vec![
            ProseIrPromptPart {
                part_id: "part:d1:t1".to_string(),
                prompt: "first".to_string(),
            },
            ProseIrPromptPart {
                part_id: "part:d2:t1".to_string(),
                prompt: "second".to_string(),
            },
        ];

        let results = prose_ir_part_llm_results(&parts, &args);

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].part_id, "part:d1:t1");
        assert_eq!(results[1].part_id, "part:d2:t1");
        assert!(results
            .iter()
            .all(|result| result.status == "skipped_llama_cli_not_found"));
        assert!(results.iter().all(|result| !result.prompt_sha.is_empty()));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prose_ir_part_llm_results_run_fake_llama_per_part_in_input_order() {
        #[cfg(unix)]
        use std::os::unix::fs::PermissionsExt;

        let root = make_fixture_root();
        fs::create_dir_all(&root).expect("mkdir root");
        let fake_llama = root.join("llama-cli");
        fs::write(
            &fake_llama,
            "#!/bin/sh\nprintf '{\"schema\":\"agent_canon.local_llm.prose_ir.v1\",\"ok\":true}\\n'\n",
        )
        .expect("write fake llama");
        #[cfg(unix)]
        {
            let mut permissions = fs::metadata(&fake_llama)
                .expect("fake llama metadata")
                .permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(&fake_llama, permissions).expect("chmod fake llama");
        }
        let args = ProseIrArgs {
            root: root.clone(),
            files: vec!["docs/one.md".to_string()],
            terms: Vec::new(),
            terms_files: Vec::new(),
            prompt: String::new(),
            prompt_files: Vec::new(),
            model: DEFAULT_MODEL.to_string(),
            llama_cli: fake_llama.to_string_lossy().to_string(),
            max_bytes: DEFAULT_MAX_BYTES,
            predict_tokens: 16,
            document_batch_size: 1,
            term_batch_size: 1,
            llm_jobs: 2,
            json_out: None,
            print_prompt: false,
        };
        let parts = vec![
            ProseIrPromptPart {
                part_id: "part:d1:t1".to_string(),
                prompt: "first".to_string(),
            },
            ProseIrPromptPart {
                part_id: "part:d2:t1".to_string(),
                prompt: "second".to_string(),
            },
        ];

        let results = prose_ir_part_llm_results(&parts, &args);

        assert_eq!(results.len(), 2);
        assert_eq!(results[0].part_id, "part:d1:t1");
        assert_eq!(results[1].part_id, "part:d2:t1");
        assert!(results.iter().all(|result| result.status == "pass"));
        assert!(results
            .iter()
            .all(|result| result.stdout.contains("\"ok\":true")));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prose_ir_marks_experiment_vocabulary_as_vocabulary_only() {
        let document = ProseIrDocument {
            path: PathBuf::from("docs/tool.md"),
            relative_path: "docs/tool.md".to_string(),
            title: "Tool".to_string(),
            responsibility: "Documents profile vocabulary.".to_string(),
            kind: "markdown".to_string(),
            text: "The experiment profile names hypothesis, metric, baseline, and expected result fields.".to_string(),
        };

        let intents = analysis_intents_for_ir(&[document]);

        assert_eq!(intents[0]["intent"].as_str(), Some("experiment_plan"));
        assert_eq!(intents[0]["status"].as_str(), Some("vocabulary_only"));
    }

    #[test]
    fn prose_ir_does_not_mark_experimental_identifier_as_experiment_plan() {
        let document = ProseIrDocument {
            path: PathBuf::from("docs/corpus.md"),
            relative_path: "docs/corpus.md".to_string(),
            title: "Corpus".to_string(),
            responsibility: "Documents corpus metadata.".to_string(),
            kind: "markdown".to_string(),
            text: "The selected corpus id is `experimental_report`, used only as metadata."
                .to_string(),
        };

        let intents = analysis_intents_for_ir(&[document]);

        assert_eq!(intents[0]["intent"].as_str(), Some("experiment_plan"));
        assert_eq!(intents[0]["status"].as_str(), Some("absent"));
    }

    #[test]
    fn prose_ir_does_not_mark_activity_word_only_as_experiment_plan() {
        let document = ProseIrDocument {
            path: PathBuf::from("docs/structure.md"),
            relative_path: "docs/structure.md".to_string(),
            title: "Structure".to_string(),
            responsibility: "Reports directory structure.".to_string(),
            kind: "markdown".to_string(),
            text: "The `experiments` directory warning includes the child term `experiment`."
                .to_string(),
        };

        let intents = analysis_intents_for_ir(&[document]);

        assert_eq!(intents[0]["intent"].as_str(), Some("experiment_plan"));
        assert_eq!(intents[0]["status"].as_str(), Some("absent"));
    }

    #[test]
    fn prose_ir_marks_assigned_experiment_fields_as_present() {
        let document = ProseIrDocument {
            path: PathBuf::from("docs/plan.md"),
            relative_path: "docs/plan.md".to_string(),
            title: "Plan".to_string(),
            responsibility: "Documents experiment plan.".to_string(),
            kind: "markdown".to_string(),
            text: "The hypothesis is that graph checks improve drafts. The metric is finding count and the baseline is the first draft.".to_string(),
        };

        let intents = analysis_intents_for_ir(&[document]);

        assert_eq!(intents[0]["intent"].as_str(), Some("experiment_plan"));
        assert_eq!(intents[0]["status"].as_str(), Some("present"));
        let field_kinds = intents[0]["field_kinds"].as_array().expect("field kinds");
        assert!(field_kinds
            .iter()
            .any(|item| item.as_str() == Some("hypothesis")));
        assert!(field_kinds
            .iter()
            .any(|item| item.as_str() == Some("metric")));
        assert!(field_kinds
            .iter()
            .any(|item| item.as_str() == Some("baseline")));
    }

    #[test]
    fn prose_ir_prompt_names_tool_document_extraction_contracts() {
        let document = ProseIrDocument {
            path: PathBuf::from("documents/tools/prose_reasoning_graph.md"),
            relative_path: "documents/tools/prose_reasoning_graph.md".to_string(),
            title: "prose_reasoning_graph.py".to_string(),
            responsibility: "Documents prose graph usage and contract".to_string(),
            kind: "markdown".to_string(),
            text: "# Tool Design\n\nThe command writes stats and diagnostics artifacts."
                .to_string(),
        };
        let prompt = prompt_for_prose_ir_part(
            "part:d1:t1",
            &[document],
            &["DSL".to_string(), "corpus".to_string()],
            "tool explanation document analysis",
        );

        assert!(prompt.contains("- part_id: part:d1:t1"));
        assert!(prompt.contains("command surface"));
        assert!(prompt.contains("result surface"));
        assert!(prompt.contains("authority boundary"));
        assert!(prompt.contains("verification route"));
        assert!(prompt.contains("partition boundary"));
        assert!(prompt.contains("analysis_intents[]"));
        assert!(prompt.contains("not vocabulary explanations"));
        assert!(prompt.contains("diagnostic_candidates[]"));
        assert!(prompt.contains("Ignore dependency-header boilerplate"));
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
