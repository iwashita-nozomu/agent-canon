// @dependency-start
// contract implementation
// responsibility Routes explicit repository-search requests to native text, semantic-index, catalog, dependency, or LSP owners without combining their results.
// upstream design ../../../../../documents/tools/search-coordination.md staged search owner contract
// upstream implementation graph_client.rs owns typed source-derived dependency context
// upstream implementation semantic_index/mod.rs owns semantic-index search
// upstream implementation ../../../../../../bootstrap/container/image/dependencies.toml owns LSP server tool inputs
// upstream implementation lsp_code_analysis.rs owns bounded code facts and LSP discovery
// upstream design ../../../../../tools/catalog.yaml owns structured tool metadata
// downstream implementation ../../../../../tests/agent_tools/test_search.py validates CLI provider routing and failure semantics
// downstream test agent_search_tests.rs validates in-process owner composition with independent source and LSP fixtures
// @dependency-end

use crate::graph_client::GraphClient;
use agent_canon::lsp_code_analysis::{
    self, LanguageId, LspServerSpec, DEFAULT_TIMEOUT as LSP_DEFAULT_TIMEOUT,
};
use icu_casemap::CaseMapper;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};

pub const DEFAULT_TOP: usize = 12;
pub const PROVIDERS: &[&str] = &["text", "semantic", "tool", "header-deps", "code-deps"];
const HELP: &str = "Usage: agent-canon agent-search [options]

Route an explicit repository search to independent providers.

Options:
  --root PATH          repository root (default: current directory)
  --query TEXT         query text or Git pattern
  --query-file PATH    read query text from a file
  --query-stdin        read query text from standard input
  --purpose TEXT       search purpose; takes precedence over --query
  --providers LIST     comma-separated providers (default: text)
                       text, semantic, tool, header-deps, code-deps
  --surface PATH       selected repository surface; repeatable
  --exclude PATH       excluded path; repeatable
  --regex              use Git extended regex for text/catalog providers
  --word-regexp        use Git whole-word matching for text/catalog providers
  --case-sensitive     use case-sensitive Git matching
  --top N              per-file Git limit and semantic top-k (default: 12)
  --format FORMAT      output format: text or json (default: text)
  -h, --help           show this help message";

#[derive(Debug, Clone)]
pub(crate) struct SearchRequest {
    pub(crate) root: PathBuf,
    pub(crate) query: String,
    pub(crate) providers: Vec<String>,
    pub(crate) surfaces: Vec<String>,
    pub(crate) excludes: Vec<String>,
    pub(crate) query_file: Option<PathBuf>,
    pub(crate) query_stdin: bool,
    pub(crate) regex: bool,
    pub(crate) word_regexp: bool,
    pub(crate) case_sensitive: bool,
    pub(crate) top: usize,
}

#[derive(Debug, Clone, Serialize)]
pub(crate) struct ProviderResult {
    pub(crate) provider: String,
    pub(crate) status: String,
    pub(crate) exit_code: i32,
    pub(crate) result: Value,
    pub(crate) stderr: String,
}

impl ProviderResult {
    fn new(
        provider: &str,
        status: &str,
        exit_code: i32,
        result: Value,
        stderr: impl Into<String>,
    ) -> Self {
        Self {
            provider: provider.to_string(),
            status: status.to_string(),
            exit_code,
            result,
            stderr: stderr.into(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub(crate) struct SearchReport {
    pub(crate) status: String,
    pub(crate) query: String,
    pub(crate) providers: Vec<String>,
    pub(crate) results: Vec<ProviderResult>,
}

impl SearchReport {
    fn new(query: String, providers: Vec<String>, results: Vec<ProviderResult>) -> Self {
        let status = if results.iter().any(|result| result.status == "fail") {
            "fail"
        } else {
            "pass"
        };
        Self {
            status: status.to_string(),
            query,
            providers,
            results,
        }
    }

    pub(crate) fn exit_code(&self) -> i32 {
        if self.status == "fail" {
            1
        } else {
            0
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

struct CliArgs {
    root: PathBuf,
    query: String,
    query_file: Option<PathBuf>,
    query_stdin: bool,
    purpose: String,
    providers: String,
    surfaces: Vec<String>,
    excludes: Vec<String>,
    regex: bool,
    word_regexp: bool,
    case_sensitive: bool,
    top: usize,
    format: OutputFormat,
    help: bool,
}

impl CliArgs {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut parsed = Self {
            root: std::env::current_dir().map_err(|error| error.to_string())?,
            query: String::new(),
            query_file: None,
            query_stdin: false,
            purpose: String::new(),
            providers: "text".to_string(),
            surfaces: Vec::new(),
            excludes: Vec::new(),
            regex: false,
            word_regexp: false,
            case_sensitive: false,
            top: DEFAULT_TOP,
            format: OutputFormat::Text,
            help: false,
        };
        let mut index = 0;
        while index < args.len() {
            let argument = &args[index];
            match argument.as_str() {
                "-h" | "--help" => {
                    parsed.help = true;
                    return Ok(parsed);
                }
                "--query-stdin" => {
                    parsed.query_stdin = true;
                    index += 1;
                    continue;
                }
                "--regex" => {
                    parsed.regex = true;
                    index += 1;
                    continue;
                }
                "--word-regexp" => {
                    parsed.word_regexp = true;
                    index += 1;
                    continue;
                }
                "--case-sensitive" => {
                    parsed.case_sensitive = true;
                    index += 1;
                    continue;
                }
                _ => {}
            }
            let (name, inline) = argument
                .split_once('=')
                .map_or((argument.as_str(), None), |(name, value)| {
                    (name, Some(value))
                });
            let value = match inline {
                Some(value) => value.to_string(),
                None if matches!(
                    name,
                    "--root"
                        | "--query"
                        | "--query-file"
                        | "--purpose"
                        | "--providers"
                        | "--surface"
                        | "--exclude"
                        | "--top"
                        | "--format"
                ) =>
                {
                    let Some(value) = args.get(index + 1) else {
                        return Err(format!("argument {name}: expected one argument"));
                    };
                    if value.starts_with('-')
                        && !(name == "--top"
                            && crate::python_cli_integer::is_argparse_negative_number(value))
                    {
                        return Err(format!("argument {name}: expected one argument"));
                    }
                    index += 1;
                    value.clone()
                }
                None => return Err(format!("unrecognized arguments: {argument}")),
            };
            match name {
                "--root" => parsed.root = PathBuf::from(value),
                "--query" => parsed.query = value,
                "--query-file" => parsed.query_file = Some(PathBuf::from(value)),
                "--purpose" => parsed.purpose = value,
                "--providers" => parsed.providers = value,
                "--surface" => parsed.surfaces.push(value),
                "--exclude" => parsed.excludes.push(value),
                "--top" => {
                    let parsed_top = crate::python_cli_integer::parse(&value)
                        .ok_or_else(|| format!("invalid int value: '{value}'"))?;
                    let normalized = parsed_top.to_string();
                    parsed.top = if normalized.starts_with('-') || normalized == "0" {
                        1
                    } else {
                        normalized.parse::<usize>().unwrap_or(usize::MAX)
                    };
                }
                "--format" => {
                    parsed.format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        _ => {
                            return Err(format!(
                                "invalid choice: '{value}' (choose from 'text', 'json')"
                            ))
                        }
                    }
                }
                _ => return Err(format!("unrecognized arguments: {argument}")),
            }
            index += 1;
        }
        Ok(parsed)
    }
}

fn resolve_path(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|error| error.to_string())?
            .join(path)
    };
    Ok(fs::canonicalize(&absolute).unwrap_or(absolute))
}

fn expand_user_path(path: &Path) -> PathBuf {
    let value = path.to_string_lossy();
    if value == "~" {
        return std::env::var_os("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| path.to_path_buf());
    }
    if let Some(suffix) = value.strip_prefix("~/") {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home).join(suffix);
        }
    }
    path.to_path_buf()
}

fn normalize_universal_newlines(text: &str) -> String {
    text.replace("\r\n", "\n").replace('\r', "\n")
}

fn query_text_from_args(args: &CliArgs) -> Result<(String, Option<PathBuf>, bool), String> {
    if args.query_file.is_some() && args.query_stdin {
        return Err("query-file-and-query-stdin-are-mutually-exclusive".to_string());
    }
    let inline_query = if args.purpose.is_empty() {
        &args.query
    } else {
        &args.purpose
    };
    if !inline_query.trim().is_empty() {
        return Ok((inline_query.clone(), None, false));
    }
    if let Some(path) = &args.query_file {
        let query_file = resolve_path(&expand_user_path(path))?;
        let bytes = fs::read(&query_file)
            .map_err(|_| format!("query-file-read-failed:{}", query_file.display()))?;
        let query = String::from_utf8(bytes)
            .map_err(|_| format!("query-file-decode-failed:{}", query_file.display()))?;
        let query = normalize_universal_newlines(&query);
        if query.trim().is_empty() {
            return Err("query-or-purpose-required".to_string());
        }
        return Ok((query, Some(query_file), false));
    }
    if args.query_stdin {
        let mut query = String::new();
        io::stdin()
            .read_to_string(&mut query)
            .map_err(|error| format!("query-stdin-read-failed:{error}"))?;
        let query = normalize_universal_newlines(&query);
        if query.trim().is_empty() {
            return Err("query-or-purpose-required".to_string());
        }
        return Ok((query, None, true));
    }
    Err("query-or-purpose-required".to_string())
}

fn selected_providers(raw: &str) -> Result<Vec<String>, String> {
    let mut names = Vec::new();
    for part in raw
        .split(',')
        .map(str::trim)
        .filter(|part| !part.is_empty())
    {
        if !names.iter().any(|name| name == part) {
            names.push(part.to_string());
        }
    }
    if names.is_empty() {
        return Err("providers-required".to_string());
    }
    let unknown = names
        .iter()
        .filter(|name| !PROVIDERS.contains(&name.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if !unknown.is_empty() {
        return Err(format!("unknown-provider:{}", unknown.join(",")));
    }
    Ok(names)
}

fn build_request(args: CliArgs) -> Result<SearchRequest, String> {
    let (query, query_file, query_stdin) = query_text_from_args(&args)?;
    Ok(SearchRequest {
        root: resolve_path(&args.root)?,
        query,
        providers: selected_providers(&args.providers)?,
        surfaces: args.surfaces,
        excludes: args.excludes,
        query_file,
        query_stdin,
        regex: args.regex,
        word_regexp: args.word_regexp,
        case_sensitive: args.case_sensitive,
        top: args.top.max(1),
    })
}

fn git_search_argv(request: &SearchRequest, pathspecs: &[String]) -> Vec<String> {
    let mut argv = vec![
        "git".to_string(),
        "grep".to_string(),
        "--untracked".to_string(),
        "--exclude-standard".to_string(),
        "--no-color".to_string(),
        "--full-name".to_string(),
        "--line-number".to_string(),
        "-I".to_string(),
        "--max-count".to_string(),
        request.top.to_string(),
    ];
    if !request.case_sensitive {
        argv.push("--ignore-case".to_string());
    }
    argv.push(if request.regex {
        "--extended-regexp".to_string()
    } else {
        "--fixed-strings".to_string()
    });
    if request.word_regexp {
        argv.push("--word-regexp".to_string());
    }
    if let Some(query_file) = &request.query_file {
        argv.extend(["-f".to_string(), query_file.to_string_lossy().into_owned()]);
    } else if request.query_stdin {
        argv.extend(["-f".to_string(), "-".to_string()]);
    } else {
        argv.extend(["-e".to_string(), request.query.clone()]);
    }
    argv.push("--".to_string());
    argv.extend(pathspecs.iter().cloned());
    argv.extend(
        request
            .excludes
            .iter()
            .map(|value| format!(":(exclude){value}")),
    );
    argv
}

fn process_exit_code(status: &ExitStatus) -> i32 {
    match status.code() {
        Some(code) => code,
        None => {
            #[cfg(unix)]
            {
                use std::os::unix::process::ExitStatusExt;
                status.signal().map_or(1, |signal| -signal)
            }
            #[cfg(not(unix))]
            {
                1
            }
        }
    }
}

fn git_provider_result(
    request: &SearchRequest,
    provider: &str,
    pathspecs: &[String],
) -> ProviderResult {
    let argv = git_search_argv(request, pathspecs);
    let mut command = Command::new(&argv[0]);
    command.args(argv.iter().skip(1)).current_dir(&request.root);
    let output = if request.query_stdin {
        let child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn();
        match child {
            Ok(mut child) => {
                if let Some(mut stdin) = child.stdin.take() {
                    let _ = stdin.write_all(request.query.as_bytes());
                }
                child.wait_with_output()
            }
            Err(error) => {
                return ProviderResult::new(
                    provider,
                    "fail",
                    127,
                    Value::String(String::new()),
                    error.to_string(),
                )
            }
        }
    } else {
        command.output()
    };
    let output = match output {
        Ok(output) => output,
        Err(error) => {
            return ProviderResult::new(
                provider,
                "fail",
                127,
                Value::String(String::new()),
                error.to_string(),
            )
        }
    };
    let exit_code = process_exit_code(&output.status);
    let status = match exit_code {
        0 => "pass",
        1 => "no_match",
        _ => "fail",
    };
    ProviderResult::new(
        provider,
        status,
        exit_code,
        Value::String(String::from_utf8_lossy(&output.stdout).into_owned()),
        String::from_utf8_lossy(&output.stderr).into_owned(),
    )
}

fn run_text_provider(request: &SearchRequest) -> ProviderResult {
    git_provider_result(request, "text", &request.surfaces)
}

fn run_tool_provider(request: &SearchRequest) -> ProviderResult {
    git_provider_result(request, "tool", &["tools/catalog.yaml".to_string()])
}

fn run_semantic_provider(request: &SearchRequest) -> ProviderResult {
    match crate::semantic_index::search_for_agent(&request.root, &request.query, request.top) {
        Ok(result) => match serde_json::to_string(&result) {
            Ok(mut stdout) => {
                stdout.push('\n');
                ProviderResult::new("semantic", "pass", 0, Value::String(stdout), "")
            }
            Err(error) => ProviderResult::new(
                "semantic",
                "fail",
                1,
                Value::String(String::new()),
                format!("SEMANTIC_INDEX_SEARCH=fail\nSEMANTIC_INDEX_ERROR={error}\n"),
            ),
        },
        Err(error) => ProviderResult::new(
            "semantic",
            "fail",
            1,
            Value::String(String::new()),
            format!("SEMANTIC_INDEX_SEARCH=fail\nSEMANTIC_INDEX_ERROR={error}\n"),
        ),
    }
}

fn run_dependency_provider(request: &SearchRequest) -> ProviderResult {
    let client = match GraphClient::new(&request.root) {
        Ok(client) => client,
        Err(error) => {
            return ProviderResult::new("header-deps", "fail", 1, json!([]), error.to_string())
        }
    };
    let paths = if request.surfaces.is_empty() {
        vec![request.query.as_str()]
    } else {
        request.surfaces.iter().map(String::as_str).collect()
    };
    let mut contexts = Vec::with_capacity(paths.len());
    for path in paths {
        match client.context(path, None) {
            Ok(context) => contexts.push(context.payload),
            Err(error) => {
                return ProviderResult::new("header-deps", "fail", 1, json!([]), error.to_string())
            }
        }
    }
    ProviderResult::new("header-deps", "pass", 0, Value::Array(contexts), "")
}

fn python_json_text(value: &Value) -> String {
    let serialized = serde_json::to_string(value).unwrap_or_default();
    let mut text = String::with_capacity(serialized.len() + 8);
    let mut in_string = false;
    let mut escaped = false;
    for character in serialized.chars() {
        text.push(character);
        if in_string {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_string = false;
            }
        } else if character == '"' {
            in_string = true;
        } else if matches!(character, ',' | ':') {
            text.push(' ');
        }
    }
    text
}

fn run_code_provider_with_overrides(
    request: &SearchRequest,
    overrides: &BTreeMap<LanguageId, LspServerSpec>,
) -> ProviderResult {
    let files = match lsp_code_analysis::discover_lsp_files(
        &request.root,
        &request.surfaces,
        &request.excludes,
    ) {
        Ok(files) => files,
        Err(error) => {
            return ProviderResult::new(
                "code-deps",
                "fail",
                1,
                json!({
                    "status": "failed",
                    "error": {"code": error.code, "message": error.message}
                }),
                "",
            )
        }
    };
    let report = lsp_code_analysis::analyze(&request.root, &files, overrides, LSP_DEFAULT_TIMEOUT);
    let status = if report.status == "complete" {
        "pass"
    } else {
        "fail"
    };
    let mut result = report.as_json(&request.root);
    let case_mapper = CaseMapper::new();
    let query = case_mapper.fold_string(&request.query);
    for field in ["symbols", "relations", "lexical_candidates"] {
        if let Some(items) = result.get_mut(field).and_then(Value::as_array_mut) {
            items.retain(|item| {
                case_mapper
                    .fold_string(&python_json_text(item))
                    .contains(&query)
            });
        }
    }
    ProviderResult::new(
        "code-deps",
        status,
        if status == "pass" { 0 } else { 1 },
        result,
        "",
    )
}

fn run_provider(
    request: &SearchRequest,
    provider: &str,
    lsp_overrides: &BTreeMap<LanguageId, LspServerSpec>,
) -> ProviderResult {
    match provider {
        "text" => run_text_provider(request),
        "semantic" => run_semantic_provider(request),
        "tool" => run_tool_provider(request),
        "header-deps" => run_dependency_provider(request),
        "code-deps" => run_code_provider_with_overrides(request, lsp_overrides),
        _ => ProviderResult::new(
            provider,
            "fail",
            2,
            Value::String(String::new()),
            format!("unknown-provider:{provider}"),
        ),
    }
}

fn run_search_with_overrides(
    request: &SearchRequest,
    lsp_overrides: &BTreeMap<LanguageId, LspServerSpec>,
) -> SearchReport {
    let results = request
        .providers
        .iter()
        .map(|provider| run_provider(request, provider, lsp_overrides))
        .collect();
    SearchReport::new(request.query.clone(), request.providers.clone(), results)
}

fn run_search(request: &SearchRequest) -> SearchReport {
    run_search_with_overrides(request, &BTreeMap::new())
}

#[cfg(test)]
pub(crate) fn run_search_with_lsp_overrides(
    request: &SearchRequest,
    lsp_overrides: &BTreeMap<LanguageId, LspServerSpec>,
) -> SearchReport {
    run_search_with_overrides(request, lsp_overrides)
}

fn print_text(report: &SearchReport) {
    println!("AGENT_SEARCH={}", report.status);
    println!(
        "AGENT_SEARCH_QUERY={}",
        serde_json::to_string(&report.query).unwrap_or_else(|_| "\"\"".to_string())
    );
    println!("AGENT_SEARCH_PROVIDERS={}", report.providers.join(","));
    for result in &report.results {
        println!(
            "PROVIDER_RESULT={}\tstatus={}\texit_code={}",
            result.provider, result.status, result.exit_code
        );
        if let Some(text) = result.result.as_str() {
            if !text.is_empty() {
                print!("{text}");
                if !text.ends_with('\n') {
                    println!();
                }
            }
        } else {
            println!(
                "{}",
                serde_json::to_string_pretty(&result.result).unwrap_or_else(|_| "null".to_string())
            );
        }
        if !result.stderr.is_empty() {
            eprint!("{}", result.stderr);
        }
    }
}

pub fn run(args: &[String]) -> i32 {
    let args = match CliArgs::parse(args) {
        Ok(args) => args,
        Err(error) => {
            eprintln!("AGENT_SEARCH=fail");
            eprintln!("AGENT_SEARCH_ERROR={error}");
            return 2;
        }
    };
    if args.help {
        println!("{HELP}");
        return 0;
    }
    let format = args.format;
    let request = match build_request(args) {
        Ok(request) => request,
        Err(error) => {
            eprintln!("AGENT_SEARCH=fail");
            eprintln!("AGENT_SEARCH_ERROR={error}");
            return 2;
        }
    };
    let report = run_search(&request);
    match format {
        OutputFormat::Json => println!(
            "{}",
            serde_json::to_string_pretty(&report).unwrap_or_else(|_| "{}".to_string())
        ),
        OutputFormat::Text => print_text(&report),
    }
    report.exit_code()
}
