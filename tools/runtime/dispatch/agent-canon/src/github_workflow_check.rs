// @dependency-start
// contract implementation
// responsibility Runs native providers for GitHub workflow validation.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md native tool owner policy
// upstream implementation ../../../../../tools/validation/ci/config/actionlint.yaml canonical pinned actionlint configuration
// upstream implementation python_cli_options.rs resolves unique argparse-compatible option prefixes
// downstream implementation main.rs exposes the native checker command
// downstream implementation ../../../../../tests/tools/test_check_github_workflows.py exercises the native CLI
// @dependency-end

use std::fs;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

const ACTIONLINT: &str = "/usr/local/bin/actionlint";
const SHELLCHECK: &str = "/usr/local/bin/shellcheck";
const ZIZMOR: &str = "/usr/local/bin/zizmor";
const ACTIONLINT_CONFIG: &[u8] =
    include_bytes!("../../../../../tools/validation/ci/config/actionlint.yaml");

#[derive(Clone, Debug, Eq, PartialEq)]
struct Finding {
    severity: &'static str,
    path: PathBuf,
    message: String,
}

impl Finding {
    fn line(&self, root: &Path) -> String {
        format!(
            "GITHUB_WORKFLOW_FINDING severity={} path={} message={}",
            self.severity,
            self.path
                .strip_prefix(root)
                .unwrap_or(&self.path)
                .to_string_lossy()
                .replace('\\', "/"),
            self.message
        )
    }
}

fn workflows(root: &Path) -> Vec<PathBuf> {
    let dir = root.join(".github/workflows");
    let Ok(entries) = fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut files: Vec<_> = entries
        .filter_map(Result::ok)
        .filter(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            #[cfg(windows)]
            let name = name.to_ascii_lowercase();
            crate::dependency_headers::fnmatch_case(&name, "*.y*ml")
        })
        .map(|entry| entry.path())
        .collect();
    files.sort();
    files
}

fn temp_config() -> Result<TempConfig, std::io::Error> {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let parent = std::env::temp_dir();
    for _ in 0..100 {
        let id = NEXT.fetch_add(1, Ordering::Relaxed);
        let dir = parent.join(format!(
            "agent-canon-actionlint-{}-{id}",
            std::process::id()
        ));
        match create_private_temp_dir(&dir) {
            Ok(()) => {
                let path = dir.join("actionlint.yaml");
                if let Err(error) = fs::write(&path, ACTIONLINT_CONFIG) {
                    let _ = fs::remove_dir_all(&dir);
                    return Err(error);
                }
                return Ok(TempConfig { dir, path });
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::AlreadyExists,
        "could not allocate checker temp directory",
    ))
}

fn create_private_temp_dir(path: &Path) -> Result<(), std::io::Error> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        let mut builder = fs::DirBuilder::new();
        builder.mode(0o700);
        builder.create(path)
    }
    #[cfg(not(unix))]
    {
        fs::create_dir(path)
    }
}

struct TempConfig {
    dir: PathBuf,
    path: PathBuf,
}
impl Drop for TempConfig {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.dir);
    }
}

fn flush_stdout() {
    let _flush_result = std::io::stdout().flush();
}

fn run_one(name: &str, executable: &str, args: &[String], root: &Path) -> i32 {
    match Command::new(executable)
        .args(args)
        .current_dir(root)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()
    {
        Ok(status) => {
            let code = status.code().unwrap_or(1);
            println!("GITHUB_WORKFLOW_TOOL_EXIT={name} code={code}");
            flush_stdout();
            code
        }
        Err(error) => {
            eprintln!("GITHUB_WORKFLOW_TOOL_START_ERROR tool={name} executable={executable} error={error}");
            127
        }
    }
}

fn workflow_arguments(root: &Path, files: &[PathBuf]) -> Vec<String> {
    files
        .iter()
        .map(|path| {
            path.strip_prefix(root)
                .unwrap_or(path)
                .to_string_lossy()
                .replace('\\', "/")
        })
        .collect()
}

fn run_providers(root: &Path, files: &[PathBuf]) -> Vec<i32> {
    if files.is_empty() {
        return Vec::new();
    }
    let args = workflow_arguments(root, files);
    println!("GITHUB_WORKFLOW_NATIVE_INPUTS={}", args.join(","));
    flush_stdout();
    let mut statuses = Vec::with_capacity(2);
    let config = match temp_config() {
        Ok(temp) => {
            println!("GITHUB_WORKFLOW_NATIVE_TOOL=actionlint executable={ACTIONLINT} config={} shellcheck={SHELLCHECK}", temp.path.display());
            flush_stdout();
            let mut argv = vec![
                "-no-color".into(),
                "-config-file".into(),
                temp.path.to_string_lossy().into_owned(),
                format!("-shellcheck={SHELLCHECK}"),
            ];
            argv.extend(args.iter().cloned());
            statuses.push(run_one("actionlint", ACTIONLINT, &argv, root));
            Some(temp)
        }
        Err(error) => {
            eprintln!("GITHUB_WORKFLOW_TOOL_START_ERROR tool=actionlint executable={ACTIONLINT} error={error}");
            statuses.push(127);
            None
        }
    };
    drop(config);
    println!("GITHUB_WORKFLOW_NATIVE_TOOL=zizmor executable={ZIZMOR} policy=default");
    flush_stdout();
    let mut argv = vec![
        "--strict-collection".into(),
        "--format=plain".into(),
        "--color=never".into(),
        "--no-progress".into(),
    ];
    argv.extend(args);
    statuses.push(run_one("zizmor", ZIZMOR, &argv, root));
    statuses
}

fn consumer_workflows(root: &Path, files: &[PathBuf]) -> (Vec<Finding>, Vec<i32>) {
    let in_repository = |path: &Path| {
        path.canonicalize()
            .is_ok_and(|resolved| resolved.starts_with(root) && resolved.is_file())
    };
    let mut findings = Vec::new();
    if files.is_empty() {
        findings.push(Finding {
            severity: "error",
            path: root.join(".github/workflows"),
            message: "no_workflows".into(),
        });
    }
    let config = [".github/actionlint.yaml", ".github/actionlint.yml"]
        .into_iter()
        .map(|relative| root.join(relative))
        .find(|path| fs::symlink_metadata(path).is_ok());
    for path in files.iter().chain(config.iter()) {
        if !in_repository(path) {
            findings.push(Finding {
                severity: "error",
                path: path.clone(),
                message: "expected_file_within_repository".into(),
            });
        }
    }
    if !findings.is_empty() {
        return (findings, Vec::new());
    }
    let executable = if Path::new(ACTIONLINT).is_file() {
        ACTIONLINT
    } else {
        "actionlint"
    };
    let mut args = vec![
        "-no-color".into(),
        "-shellcheck=".into(),
        "-pyflakes=".into(),
    ];
    if let Some(path) = config {
        args.extend(["-config-file".into(), path.to_string_lossy().into_owned()]);
    }
    args.extend(workflow_arguments(root, files));
    (
        findings,
        vec![run_one("actionlint", executable, &args, root)],
    )
}

fn report(root: &Path, findings: &[Finding], files: &[PathBuf], statuses: &[i32]) -> String {
    let mut output = String::new();
    for finding in findings {
        output.push_str(&finding.line(root));
        output.push('\n');
    }
    let errors = findings.iter().filter(|f| f.severity == "error").count();
    let warnings = findings.iter().filter(|f| f.severity == "warning").count();
    let failures = statuses.iter().filter(|status| **status != 0).count();
    output.push_str(&format!("GITHUB_WORKFLOWS_CHECKED={}\nGITHUB_WORKFLOW_ERRORS={errors}\nGITHUB_WORKFLOW_WARNINGS={warnings}\nGITHUB_WORKFLOW_NATIVE_FAILURES={failures}\nGITHUB_WORKFLOWS={}\n",
        files.len(), if errors > 0 || failures > 0 { "fail" } else { "pass" }));
    output
}

fn exit_code(findings: &[Finding], statuses: &[i32]) -> i32 {
    statuses
        .iter()
        .copied()
        .find(|status| *status != 0)
        .unwrap_or_else(|| {
            if findings.iter().any(|f| f.severity == "error") {
                1
            } else {
                0
            }
        })
}

const HELP: &str = "usage: agent-canon check-github-workflows [-h] [--root ROOT] [--consumer]\n\nRun native GitHub workflow analyzers.\n\noptions:\n  -h, --help   show this help message and exit\n  --root ROOT  repository root to check\n  --consumer  validate workflows with the target repository's actionlint configuration";

#[derive(Clone, Copy)]
enum CheckerOption {
    Help,
    Root,
    Consumer,
}

const CHECKER_OPTIONS: &[(&str, CheckerOption)] = &[
    ("--help", CheckerOption::Help),
    ("--root", CheckerOption::Root),
    ("--consumer", CheckerOption::Consumer),
];

enum ParseError {
    InvalidArguments,
}

struct CheckerArgs {
    root: PathBuf,
    consumer: bool,
}

fn parse_args(args: &[String]) -> Result<Option<CheckerArgs>, ParseError> {
    let mut root = PathBuf::from(".");
    let mut consumer = false;
    let mut index = 0;
    while index < args.len() {
        let argument = args[index].as_str();
        if argument == "-h" {
            return Ok(None);
        }
        let (option, inline_value) = argument
            .split_once('=')
            .map_or((argument, None), |(option, value)| (option, Some(value)));
        let resolved =
            crate::python_cli_options::resolve_long_option_prefix(option, CHECKER_OPTIONS)
                .map_err(|_| ParseError::InvalidArguments)?;
        match resolved {
            CheckerOption::Help if inline_value.is_none() => return Ok(None),
            CheckerOption::Help => return Err(ParseError::InvalidArguments),
            CheckerOption::Consumer if inline_value.is_none() => consumer = true,
            CheckerOption::Consumer => return Err(ParseError::InvalidArguments),
            CheckerOption::Root => {
                let value: &str = if let Some(value) = inline_value {
                    value
                } else {
                    let Some(value) = args.get(index + 1) else {
                        return Err(ParseError::InvalidArguments);
                    };
                    if value.starts_with('-')
                        && value != "-"
                        && !crate::python_cli_integer::is_argparse_negative_number(value)
                    {
                        return Err(ParseError::InvalidArguments);
                    }
                    index += 1;
                    value.as_str()
                };
                root = PathBuf::from(if value.is_empty() { "." } else { value });
            }
        }
        index += 1;
    }
    Ok(Some(CheckerArgs { root, consumer }))
}

pub fn run(args: &[String]) -> i32 {
    let CheckerArgs { root, consumer } = match parse_args(args) {
        Ok(None) => {
            println!("{HELP}");
            return 0;
        }
        Ok(Some(args)) => args,
        Err(ParseError::InvalidArguments) => {
            eprintln!("usage: agent-canon check-github-workflows [-h] [--root ROOT] [--consumer]");
            return 2;
        }
    };
    let root = root.canonicalize().unwrap_or(root);
    let files = workflows(&root);
    let (findings, statuses) = if consumer {
        consumer_workflows(&root, &files)
    } else {
        (Vec::new(), run_providers(&root, &files))
    };
    print!("{}", report(&root, &findings, &files, &statuses));
    exit_code(&findings, &statuses)
}
