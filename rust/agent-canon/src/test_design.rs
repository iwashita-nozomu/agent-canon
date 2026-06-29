// @dependency-start
// contract implementation
// responsibility Provides Rust-native test design resilience diagnostics.
// upstream design ../../../documents/coding-conventions-testing.md shared testing policy
// upstream design ../../../references/test-design-flexibility.md research basis for resilient test design
// upstream design ../../../documents/rust-agent-tool-migration.md Rust tool migration policy
// downstream design ../../../agents/skills/test-design.md human-facing test design skill
// downstream design ../../../tools/catalog.yaml catalogs this Rust CLI surface
// downstream design ../../../tools/README.md documents root tool entrypoints
// downstream design ../../../documents/tools/README.md documents reader-facing tool entrypoints
// @dependency-end

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::json;

#[derive(Debug, Clone, PartialEq, Eq)]
enum TestDesignCommand {
    Check,
    Help,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum OutputFormat {
    Text,
    Json,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Args {
    command: TestDesignCommand,
    root: PathBuf,
    paths: Vec<String>,
    output_format: OutputFormat,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Finding {
    severity: &'static str,
    check: &'static str,
    path: PathBuf,
    line: Option<usize>,
    message: String,
    recommendation: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ScannedFile {
    path: PathBuf,
    text: String,
}

pub fn run(args: &[String]) -> i32 {
    match Args::parse(args) {
        Ok(parsed) => {
            if parsed.command == TestDesignCommand::Help {
                print_usage();
                return 0;
            }
            run_check(&parsed)
        }
        Err(message) => {
            eprintln!("TEST_DESIGN_CHECK=fail");
            eprintln!("TEST_DESIGN_CHECK_ERROR={message}");
            print_usage();
            2
        }
    }
}

impl Args {
    fn parse(args: &[String]) -> Result<Self, String> {
        let Some(raw_command) = args.first() else {
            return Ok(Self {
                command: TestDesignCommand::Help,
                root: PathBuf::from("."),
                paths: Vec::new(),
                output_format: OutputFormat::Text,
            });
        };
        if raw_command == "--help" || raw_command == "-h" || raw_command == "help" {
            return Ok(Self {
                command: TestDesignCommand::Help,
                root: PathBuf::from("."),
                paths: Vec::new(),
                output_format: OutputFormat::Text,
            });
        }

        let command = match raw_command.as_str() {
            "check" => TestDesignCommand::Check,
            unknown => return Err(format!("unknown test-design command {unknown}")),
        };

        let mut root = PathBuf::from(".");
        let mut paths = Vec::new();
        let mut output_format = OutputFormat::Text;
        let mut index = 1;
        while index < args.len() {
            match args[index].as_str() {
                "--root" => {
                    let Some(value) = args.get(index + 1) else {
                        return Err("--root requires a value".to_string());
                    };
                    root = PathBuf::from(value);
                    index += 2;
                }
                "--format" => {
                    let Some(value) = args.get(index + 1) else {
                        return Err("--format requires a value".to_string());
                    };
                    output_format = match value.as_str() {
                        "text" => OutputFormat::Text,
                        "json" => OutputFormat::Json,
                        other => return Err(format!("unsupported --format {other}")),
                    };
                    index += 2;
                }
                "--help" | "-h" => {
                    return Ok(Self {
                        command: TestDesignCommand::Help,
                        root,
                        paths,
                        output_format,
                    });
                }
                value if value.starts_with("--") => {
                    return Err(format!("unknown argument {value}"));
                }
                value => {
                    paths.push(value.to_string());
                    index += 1;
                }
            }
        }

        Ok(Self {
            command,
            root,
            paths,
            output_format,
        })
    }
}

fn usage_text() -> &'static str {
    "usage: agent-canon test-design <command> [options] [paths...]\n\
\n\
commands:\n\
  check                   diagnose brittle or under-specified test design signals\n\
  help, -h, --help        show this command contract\n\
\n\
options:\n\
  --root <repo-root>      repository root to evaluate; defaults to the current directory\n\
  --format text|json      output format; defaults to text\n\
\n\
examples:\n\
  tools/bin/agent-canon test-design -h\n\
  tools/bin/agent-canon test-design check tests/tools/test_example.py\n\
  tools/bin/agent-canon test-design check --root . tests rust/agent-canon/src"
}

fn print_usage() {
    eprintln!("{}", usage_text());
}

fn run_check(args: &Args) -> i32 {
    let (scanned_files, mut findings) = collect_scanned_files(&args.root, &args.paths);
    for file in &scanned_files {
        findings.extend(analyze_test_file(&args.root, file));
    }
    render_findings(
        &args.root,
        scanned_files.len(),
        &findings,
        &args.output_format,
    );
    if findings.iter().any(|finding| finding.severity == "fix-now") {
        1
    } else {
        0
    }
}

fn collect_scanned_files(root: &Path, raw_paths: &[String]) -> (Vec<ScannedFile>, Vec<Finding>) {
    let mut files = Vec::new();
    let mut findings = Vec::new();
    let path_inputs = if raw_paths.is_empty() {
        vec!["tests".to_string()]
    } else {
        raw_paths.to_vec()
    };

    for raw_path in path_inputs {
        let path = resolve_path(root, &raw_path);
        if !path.exists() {
            findings.push(Finding {
                severity: "fix-now",
                check: "missing-test-path",
                path,
                line: None,
                message: format!("test-design input path does not exist: {raw_path}"),
                recommendation: "Fix the path or pass the related test file/directory explicitly."
                    .to_string(),
            });
            continue;
        }
        collect_path(root, &path, &mut files, &mut findings);
    }

    files.sort_by(|left, right| left.path.cmp(&right.path));
    findings.sort_by(|left, right| left.path.cmp(&right.path).then(left.line.cmp(&right.line)));
    (files, findings)
}

fn collect_path(
    root: &Path,
    path: &Path,
    files: &mut Vec<ScannedFile>,
    findings: &mut Vec<Finding>,
) {
    if path.is_dir() {
        let Ok(entries) = fs::read_dir(path) else {
            findings.push(Finding {
                severity: "review",
                check: "unreadable-test-directory",
                path: path.to_path_buf(),
                line: None,
                message: "test directory could not be read".to_string(),
                recommendation: "Check permissions or pass a more specific path.".to_string(),
            });
            return;
        };
        for entry in entries.flatten() {
            let child = entry.path();
            if should_skip_path(&child) {
                continue;
            }
            collect_path(root, &child, files, findings);
        }
        return;
    }

    if !is_test_like_file(root, path) {
        return;
    }

    match fs::read_to_string(path) {
        Ok(text) => files.push(ScannedFile {
            path: path.to_path_buf(),
            text,
        }),
        Err(error) => findings.push(Finding {
            severity: "review",
            check: "unreadable-test-file",
            path: path.to_path_buf(),
            line: None,
            message: format!("test file could not be read: {error}"),
            recommendation: "Check encoding or pass a more specific path.".to_string(),
        }),
    }
}

fn should_skip_path(path: &Path) -> bool {
    path.file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| {
            matches!(
                name,
                ".git" | "target" | "__pycache__" | ".pytest_cache" | "node_modules"
            )
        })
}

fn is_test_like_file(root: &Path, path: &Path) -> bool {
    let relative = display_path(root, path).replace('\\', "/");
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let extension = path
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let test_location = relative.starts_with("tests/")
        || relative.contains("/tests/")
        || file_name.contains("test")
        || file_name.contains("spec");
    let supported_extension = matches!(
        extension.as_str(),
        "py" | "rs"
            | "sh"
            | "bash"
            | "js"
            | "jsx"
            | "ts"
            | "tsx"
            | "c"
            | "cc"
            | "cpp"
            | "cxx"
            | "h"
            | "hpp"
    );
    test_location && supported_extension
}

fn analyze_test_file(root: &Path, file: &ScannedFile) -> Vec<Finding> {
    let mut findings = Vec::new();
    let text_lower = file.text.to_ascii_lowercase();
    if !has_assertion(&text_lower) {
        findings.push(Finding {
            severity: "fix-now",
            check: "missing-oracle",
            path: file.path.clone(),
            line: first_test_line(&file.text),
            message: "test-like file has no recognizable assertion or expected-failure oracle"
                .to_string(),
            recommendation:
                "Add an explicit behavior oracle: expected value, exception, state change, or diagnostic key."
                    .to_string(),
        });
    }

    findings.extend(analyze_lines(file));
    findings.extend(analyze_python_test_functions(file));

    if is_transform_or_parser_test(root, file) && !has_property_or_metamorphic_signal(&text_lower) {
        findings.push(Finding {
            severity: "design-hint",
            check: "property-or-metamorphic-candidate",
            path: file.path.clone(),
            line: first_test_line(&file.text),
            message:
                "transform/parser-style tests appear example-only and may benefit from property or metamorphic cases"
                    .to_string(),
            recommendation:
                "Add invariants such as round-trip, idempotence, ordering, preservation, or equivalent-input relations when they match the contract."
                    .to_string(),
        });
    }

    findings.sort_by(|left, right| left.path.cmp(&right.path).then(left.line.cmp(&right.line)));
    findings
}

fn analyze_lines(file: &ScannedFile) -> Vec<Finding> {
    let mut findings = Vec::new();
    let text_lower = file.text.to_ascii_lowercase();
    let has_seed = text_lower.contains("seed(")
        || text_lower.contains("seed =")
        || text_lower.contains("rng")
        || text_lower.contains("random_state");
    let mut random_reported = false;

    for (index, line) in file.text.lines().enumerate() {
        let line_no = index + 1;
        let lower = line.to_ascii_lowercase();
        if !random_reported
            && !has_seed
            && (lower.contains("random.")
                || lower.contains("np.random")
                || lower.contains("numpy.random")
                || lower.contains("rand::")
                || lower.contains("thread_rng"))
        {
            findings.push(Finding {
                severity: "fix-now",
                check: "unseeded-random-test",
                path: file.path.clone(),
                line: Some(line_no),
                message: "randomized test input appears without an explicit seed or rng boundary"
                    .to_string(),
                recommendation:
                    "Use a fixed seed, deterministic generator, or property-test framework that records failing examples."
                        .to_string(),
            });
            random_reported = true;
        }
        if lower.contains("sleep(") || lower.contains("thread::sleep") {
            findings.push(Finding {
                severity: "review",
                check: "time-coupled-test",
                path: file.path.clone(),
                line: Some(line_no),
                message: "test depends on wall-clock waiting".to_string(),
                recommendation:
                    "Prefer controlled clocks, polling with bounded condition checks, or a lower-level contract."
                        .to_string(),
            });
        }
        if contains_private_member_access(line) {
            findings.push(Finding {
                severity: "review",
                check: "implementation-detail-coupling",
                path: file.path.clone(),
                line: Some(line_no),
                message: "test reaches a private-looking member".to_string(),
                recommendation:
                    "Prefer observable public behavior unless the private boundary is the explicit contract under test."
                        .to_string(),
            });
        }
        if lower.contains("assert_called_once")
            || lower.contains("assert_has_calls")
            || lower.contains("mock_calls")
            || lower.contains("call_args_list")
        {
            findings.push(Finding {
                severity: "review",
                check: "overspecified-mock-interaction",
                path: file.path.clone(),
                line: Some(line_no),
                message: "test pins exact collaborator call details".to_string(),
                recommendation:
                    "Assert externally visible effect or stable collaborator contract; keep exact call checks only for adapter boundaries."
                        .to_string(),
            });
        }
        if lower.contains("str(")
            && lower.contains("==")
            && (lower.contains("exc") || lower.contains("error") || lower.contains("exception"))
        {
            findings.push(Finding {
                severity: "review",
                check: "exact-exception-message",
                path: file.path.clone(),
                line: Some(line_no),
                message: "test pins an exact exception/error string".to_string(),
                recommendation:
                    "Assert a stable diagnostic code, exception type, or required substring instead of the full prose message."
                        .to_string(),
            });
        }
        if (lower.contains("stdout") || lower.contains("stderr") || lower.contains("output"))
            && lower.contains("assert")
            && lower.contains("==")
        {
            findings.push(Finding {
                severity: "review",
                check: "exact-output-coupling",
                path: file.path.clone(),
                line: Some(line_no),
                message: "test pins exact command/output text".to_string(),
                recommendation:
                    "Assert stable machine-readable keys, parsed fields, or essential substrings when prose output can evolve."
                        .to_string(),
            });
        }
    }
    findings
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TestBlock {
    name: String,
    start_line: usize,
    lines: Vec<(usize, String)>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct OpenTestBlock {
    name: String,
    start_line: usize,
    def_indent: usize,
    lines: Vec<(usize, String)>,
}

impl OpenTestBlock {
    fn close(self) -> TestBlock {
        TestBlock {
            name: self.name,
            start_line: self.start_line,
            lines: self.lines,
        }
    }
}

fn analyze_python_test_functions(file: &ScannedFile) -> Vec<Finding> {
    let mut findings = Vec::new();
    for block in python_test_blocks(&file.text) {
        let block_text = block
            .lines
            .iter()
            .map(|(_, line)| line.as_str())
            .collect::<Vec<_>>()
            .join("\n")
            .to_ascii_lowercase();
        if !has_assertion(&block_text) {
            findings.push(Finding {
                severity: "fix-now",
                check: "missing-oracle",
                path: file.path.clone(),
                line: Some(block.start_line),
                message: format!("test function `{}` has no recognizable oracle", block.name),
                recommendation:
                    "Add an explicit assert, pytest.raises block, or stable expected-result check."
                        .to_string(),
            });
        }
        if is_static_analysis_duplicate_test(&block_text) {
            findings.push(Finding {
                severity: "fix-now",
                check: "static-analysis-duplicate-test",
                path: file.path.clone(),
                line: Some(block.start_line),
                message: format!(
                    "test function `{}` only reruns static-analysis or checker success",
                    block.name
                ),
                recommendation:
                    "Delete the pytest wrapper and run the canonical checker in the validation route, or replace it with a behavior regression that observes product output, diagnostics, or state."
                        .to_string(),
            });
        }
        if is_generated_execution_placeholder(&block.name, &block_text) {
            findings.push(Finding {
                severity: "fix-now",
                check: "meaningless-generated-execution-test",
                path: file.path.clone(),
                line: Some(block.start_line),
                message: format!(
                    "test function `{}` looks like a generated execution-only placeholder",
                    block.name
                ),
                recommendation:
                    "Remove the placeholder or add a concrete behavior contract, input, expected outcome, and oracle beyond process success."
                        .to_string(),
            });
        }
        for (line_no, line) in block.lines {
            let trimmed = line.trim_start();
            if starts_with_test_logic(trimmed) {
                findings.push(Finding {
                    severity: "review",
                    check: "logic-in-test-body",
                    path: file.path.clone(),
                    line: Some(line_no),
                    message: format!("test function `{}` contains control flow", block.name),
                    recommendation:
                        "Keep the oracle simple; move generators/helpers out and test nontrivial helpers separately."
                            .to_string(),
                });
            }
        }
    }
    findings
}

fn python_test_blocks(text: &str) -> Vec<TestBlock> {
    let mut blocks = Vec::new();
    let mut current: Option<OpenTestBlock> = None;

    for (index, line) in text.lines().enumerate() {
        let line_no = index + 1;
        let trimmed = line.trim_start();
        let indent = line.len() - trimmed.len();
        if let Some(open_block) = current.take() {
            if !python_test_header_complete(&open_block.lines) {
                let mut next_block = open_block;
                next_block.lines.push((line_no, line.to_string()));
                current = Some(next_block);
                continue;
            }
            if !trimmed.is_empty() && indent <= open_block.def_indent && is_python_test_def(trimmed)
            {
                blocks.push(open_block.close());
                current = Some(OpenTestBlock {
                    name: python_test_name(trimmed).unwrap_or_else(|| "test".to_string()),
                    start_line: line_no,
                    def_indent: indent,
                    lines: vec![(line_no, line.to_string())],
                });
                continue;
            }
            if !trimmed.is_empty() && indent <= open_block.def_indent && !line.starts_with('@') {
                blocks.push(open_block.close());
                current = None;
            } else {
                let mut next_block = open_block;
                next_block.lines.push((line_no, line.to_string()));
                current = Some(next_block);
                continue;
            }
        }
        if current.is_none() && is_python_test_def(trimmed) {
            current = Some(OpenTestBlock {
                name: python_test_name(trimmed).unwrap_or_else(|| "test".to_string()),
                start_line: line_no,
                def_indent: indent,
                lines: vec![(line_no, line.to_string())],
            });
        }
    }

    if let Some(open_block) = current {
        blocks.push(open_block.close());
    }

    blocks
}

fn python_test_header_complete(lines: &[(usize, String)]) -> bool {
    lines.iter().any(|(_, line)| line.trim_end().ends_with(':'))
}

fn is_python_test_def(trimmed: &str) -> bool {
    trimmed.starts_with("def test_") || trimmed.starts_with("async def test_")
}

fn python_test_name(trimmed: &str) -> Option<String> {
    let without_async = trimmed.strip_prefix("async ").unwrap_or(trimmed);
    without_async
        .strip_prefix("def ")
        .and_then(|value| value.split('(').next())
        .map(|value| value.to_string())
}

fn starts_with_test_logic(trimmed: &str) -> bool {
    trimmed.starts_with("if ")
        || trimmed.starts_with("for ")
        || trimmed.starts_with("while ")
        || trimmed.starts_with("match ")
}

fn is_static_analysis_duplicate_test(text_lower: &str) -> bool {
    contains_static_analysis_command(text_lower)
        && has_process_success_only_oracle(text_lower)
        && !has_behavior_oracle_signal(text_lower)
}

fn is_generated_execution_placeholder(name: &str, text_lower: &str) -> bool {
    let name_lower = name.to_ascii_lowercase();
    let placeholder_name = [
        "test_generated",
        "test_smoke",
        "test_runs",
        "test_can_run",
        "test_executes",
        "test_no_crash",
    ]
    .iter()
    .any(|token| name_lower.contains(token));
    placeholder_name
        && contains_execution_command(text_lower)
        && has_process_success_only_oracle(text_lower)
        && !has_behavior_oracle_signal(text_lower)
}

fn contains_static_analysis_command(text_lower: &str) -> bool {
    [
        "py_compile",
        "compileall",
        "python -m compileall",
        "python -m py_compile",
        "ruff",
        "pyright",
        "mypy",
        "deptry",
        "shellcheck",
        "cargo check",
        "cargo clippy",
        "check_static_any.py",
        "check_dependency_headers.py",
        "scan_dependency_headers.sh",
        "check_dependency_header_format.sh",
        "check_convention_compliance.py",
        "repo_structure_contract.py",
        "responsibility_scope.py",
        "import_responsibility.py",
        "agent-canon docs check",
        "agent-canon test-design check",
    ]
    .iter()
    .any(|token| text_lower.contains(token))
}

fn contains_execution_command(text_lower: &str) -> bool {
    [
        "subprocess.run",
        "subprocess.call",
        "command::new",
        ".status()",
        "python ",
        "cargo run",
        "bash ",
        "sh ",
    ]
    .iter()
    .any(|token| text_lower.contains(token))
}

fn has_process_success_only_oracle(text_lower: &str) -> bool {
    [
        "returncode == 0",
        "returncode, 0",
        "exit_code == 0",
        "status.success",
        ".success()",
        "check=true",
        "check = true",
    ]
    .iter()
    .any(|token| text_lower.contains(token))
}

fn has_behavior_oracle_signal(text_lower: &str) -> bool {
    [
        " in result.stdout",
        " in result.stderr",
        " in stdout",
        " in stderr",
        "json.loads",
        "assert result.stdout",
        "assert result.stderr",
        "assert output",
        "assert data",
        "pytest.raises",
        "write_text",
        "fs::write",
        "tmp_path",
        "tempfile",
        "expected",
        "diagnostic",
        "finding",
        "snapshot",
        "state",
    ]
    .iter()
    .any(|token| text_lower.contains(token))
}

fn has_assertion(text_lower: &str) -> bool {
    [
        "assert ",
        "assert(",
        "assert_eq!",
        "assert_ne!",
        "assert!",
        "pytest.raises",
        "unittest",
        "self.assert",
        "expect_",
        "expect(",
        "assert_",
        "require(",
        "check(",
        "grep -q",
    ]
    .iter()
    .any(|token| text_lower.contains(token))
}

fn contains_private_member_access(line: &str) -> bool {
    let bytes = line.as_bytes();
    bytes.windows(3).any(|window| {
        window[0] == b'.'
            && window[1] == b'_'
            && window[2] != b'_'
            && (window[2] as char).is_ascii_alphanumeric()
    })
}

fn is_transform_or_parser_test(root: &Path, file: &ScannedFile) -> bool {
    let haystack = format!(
        "{}\n{}",
        display_path(root, &file.path),
        file.text.to_ascii_lowercase()
    );
    [
        "parse",
        "parser",
        "serialize",
        "deserialize",
        "roundtrip",
        "round_trip",
        "normalize",
        "format",
        "sort",
        "hash",
        "graph",
        "dsl",
        "route",
        "mapping",
    ]
    .iter()
    .any(|token| haystack.contains(token))
}

fn has_property_or_metamorphic_signal(text_lower: &str) -> bool {
    [
        "parametrize",
        "hypothesis",
        "@given",
        "given(",
        "quickcheck",
        "proptest",
        "metamorphic",
        "roundtrip",
        "round_trip",
        "idempotent",
        "invariant",
    ]
    .iter()
    .any(|token| text_lower.contains(token))
}

fn first_test_line(text: &str) -> Option<usize> {
    text.lines().enumerate().find_map(|(index, line)| {
        let trimmed = line.trim_start();
        if trimmed.contains("test_") || trimmed.contains("#[test]") || trimmed.contains("TEST(") {
            Some(index + 1)
        } else {
            None
        }
    })
}

fn render_findings(root: &Path, scanned_files: usize, findings: &[Finding], format: &OutputFormat) {
    match format {
        OutputFormat::Text => render_text(root, scanned_files, findings),
        OutputFormat::Json => render_json(root, scanned_files, findings),
    }
}

fn render_text(root: &Path, scanned_files: usize, findings: &[Finding]) {
    if findings.is_empty() {
        println!("TEST_DESIGN_CHECK=pass scanned_files={scanned_files}");
        return;
    }
    let fix_now = findings
        .iter()
        .filter(|finding| finding.severity == "fix-now")
        .count();
    let review = findings
        .iter()
        .filter(|finding| finding.severity == "review")
        .count();
    let design_hint = findings
        .iter()
        .filter(|finding| finding.severity == "design-hint")
        .count();
    let status = if fix_now > 0 { "fail" } else { "warn" };
    println!(
        "TEST_DESIGN_CHECK={status} scanned_files={scanned_files} findings={} fix_now={fix_now} review={review} design_hint={design_hint}",
        findings.len()
    );
    println!("TEST_DESIGN_REPORT_BEGIN");
    println!(
        "summary: Test design diagnostics found {} issue(s). Treat review/design-hint findings as prompts for human or skill judgment, not automatic proof of bad tests.",
        findings.len()
    );
    for finding in findings {
        let location = finding
            .line
            .map(|line| format!("{}:{line}", display_path(root, &finding.path)))
            .unwrap_or_else(|| display_path(root, &finding.path));
        println!("- severity: {}", finding.severity);
        println!("  check: {}", finding.check);
        println!("  location: {location}");
        println!("  message: {}", finding.message);
        println!("  recommendation: {}", finding.recommendation);
    }
    println!("TEST_DESIGN_REPORT_END");
}

fn render_json(root: &Path, scanned_files: usize, findings: &[Finding]) {
    let fix_now = findings
        .iter()
        .filter(|finding| finding.severity == "fix-now")
        .count();
    let status = if findings.is_empty() {
        "pass"
    } else if fix_now > 0 {
        "fail"
    } else {
        "warn"
    };
    let finding_values = findings
        .iter()
        .map(|finding| {
            json!({
                "severity": finding.severity,
                "check": finding.check,
                "path": display_path(root, &finding.path),
                "line": finding.line,
                "message": finding.message,
                "recommendation": finding.recommendation,
            })
        })
        .collect::<Vec<_>>();
    println!(
        "{}",
        json!({
            "schema": "agent_canon.test_design_check.v1",
            "status": status,
            "scanned_files": scanned_files,
            "finding_count": findings.len(),
            "fix_now_count": fix_now,
            "findings": finding_values,
        })
    );
}

fn resolve_path(root: &Path, raw_path: &str) -> PathBuf {
    let path = PathBuf::from(raw_path);
    if path.is_absolute() {
        path
    } else {
        root.join(path)
    }
}

fn display_path(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn help_text_exposes_options_and_examples() {
        let usage = usage_text();

        assert!(usage.contains("usage: agent-canon test-design <command>"));
        assert!(usage.contains("--root <repo-root>"));
        assert!(usage.contains("--format text|json"));
        assert!(usage.contains("tools/bin/agent-canon test-design -h"));
    }

    #[test]
    fn parse_check_args() {
        let args = vec![
            "check".to_string(),
            "--root".to_string(),
            "/repo".to_string(),
            "--format".to_string(),
            "json".to_string(),
            "tests".to_string(),
        ];
        let parsed = Args::parse(&args).expect("parse args");

        assert_eq!(parsed.command, TestDesignCommand::Check);
        assert_eq!(parsed.root, PathBuf::from("/repo"));
        assert_eq!(parsed.output_format, OutputFormat::Json);
        assert_eq!(parsed.paths, vec!["tests"]);
    }

    #[test]
    fn detects_missing_oracle_in_python_test_function() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_no_assert.py"),
            text: "def test_runs():\n    value = helper()\n".to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(findings
            .iter()
            .any(|finding| { finding.check == "missing-oracle" && finding.line == Some(1) }));
    }

    #[test]
    fn accepts_multiline_python_test_function_header_with_unittest_assertion() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_multiline.py"),
            text: "def test_runs(\n    self,\n) -> None:\n    self.assertEqual(result, 0)\n"
                .to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(!findings
            .iter()
            .any(|finding| finding.check == "missing-oracle"));
    }

    #[test]
    fn detects_overspecified_mock_and_private_access() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_mock.py"),
            text: "def test_call(mock_client):\n    assert obj._state == 1\n    mock_client.send.assert_called_once_with('x')\n".to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(findings
            .iter()
            .any(|finding| finding.check == "implementation-detail-coupling"));
        assert!(findings
            .iter()
            .any(|finding| finding.check == "overspecified-mock-interaction"));
    }

    #[test]
    fn emits_property_design_hint_for_parser_examples() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_parser.py"),
            text: "def test_parse_value():\n    assert parse('a=1') == {'a': 1}\n".to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(findings
            .iter()
            .any(|finding| finding.check == "property-or-metamorphic-candidate"));
    }

    #[test]
    fn flags_static_analysis_duplicate_success_test() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_static_wrapper.py"),
            text: "def test_py_compile_passes():\n    result = subprocess.run(['python', '-m', 'py_compile', 'src/app.py'], capture_output=True)\n    assert result.returncode == 0\n".to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(findings.iter().any(|finding| {
            finding.check == "static-analysis-duplicate-test" && finding.severity == "fix-now"
        }));
    }

    #[test]
    fn flags_generated_execution_only_placeholder() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_generated_cli.py"),
            text: "def test_generated_cli_runs():\n    result = subprocess.run(['python', 'tools/example.py'])\n    assert result.returncode == 0\n".to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(findings.iter().any(|finding| {
            finding.check == "meaningless-generated-execution-test" && finding.severity == "fix-now"
        }));
    }

    #[test]
    fn allows_static_checker_behavior_contract_tests() {
        let file = ScannedFile {
            path: PathBuf::from("/repo/tests/test_static_checker.py"),
            text: "def test_static_checker_reports_bad_input(tmp_path):\n    source = tmp_path / 'bad.py'\n    source.write_text('x: Any = 1')\n    result = subprocess.run(['python3', 'tools/agent_tools/check_static_any.py', str(source)], capture_output=True, text=True)\n    assert 'STATIC_ANY=fail' in result.stdout\n".to_string(),
        };

        let findings = analyze_test_file(Path::new("/repo"), &file);

        assert!(!findings
            .iter()
            .any(|finding| finding.check == "static-analysis-duplicate-test"));
    }

    #[test]
    fn scans_test_like_files_under_tests_directory() {
        let root = temp_root();
        let tests = root.join("tests");
        fs::create_dir_all(&tests).expect("create tests");
        fs::write(
            tests.join("test_example.py"),
            "def test_example():\n    assert value() == 1\n",
        )
        .expect("write test");

        let (files, findings) = collect_scanned_files(&root, &[]);
        fs::remove_dir_all(&root).ok();

        assert_eq!(files.len(), 1);
        assert!(findings.is_empty());
    }

    fn temp_root() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        std::env::temp_dir().join(format!("agent-canon-test-design-{suffix}"))
    }
}
