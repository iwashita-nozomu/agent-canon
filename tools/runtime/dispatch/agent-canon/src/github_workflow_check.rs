// @dependency-start
// contract implementation
// responsibility Checks standalone GitHub workflows and AgentCanon PR-template contracts.
// upstream design ../../../../../documents/design/rust-agent-tool-migration.md native tool owner policy
// upstream implementation ../../../../../tools/validation/ci/config/actionlint.yaml canonical pinned actionlint configuration
// downstream implementation main.rs exposes the native checker command
// downstream implementation ../../../../../tests/tools/test_check_github_workflows.py exercises the native CLI
// @dependency-end

use regex::Regex;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use yaml_rust2::YamlLoader;

const ACTIONLINT: &str = "/usr/local/bin/actionlint";
const SHELLCHECK: &str = "/usr/local/bin/shellcheck";
const ZIZMOR: &str = "/usr/local/bin/zizmor";
const ACTIONLINT_CONFIG: &[u8] =
    include_bytes!("../../../../../tools/validation/ci/config/actionlint.yaml");

const PR_REQUIRED: &[&str] = &[
    "## PR Essence",
    "Problem / user request:",
    "Canonical owner / responsibility unit:",
    "Behavior or contract delta:",
    "Evidence route:",
    "Explicit non-goals:",
    "canonical route",
    "changed surfaces:",
    "source_commit:",
    "template_pin:",
    "pr_head:",
    "identity relation (source_commit -> template_pin -> pr_head):",
    "changed-surface validation:",
    "mutation authority:",
    "risk:",
    "follow-up owner or issue:",
];
const PR_FORBIDDEN: &[&str] = &[
    "Plan Mode Evidence",
    "Agent Orchestration Evidence",
    "paused until",
    "Existing durable findings were searched",
    "Copilot Configuration Impact",
    "Candidate Commit And Publication Identity",
    "GitHub Mirror / Submodule Evidence",
    "template submodule SHA:",
];
const GUIDE_REQUIRED: &[&str] = &["generate_agent_improvement_guide.py"];
const DASHBOARD_REQUIRED: &[&str] = &[
    "pull_request:",
    "workflow_dispatch:",
    "schedule:",
    "generate_agent_runtime_dashboard.py",
];
const STATIC_GATES_REQUIRED: &[&str] = &[
    "pull_request:",
    "workflow_dispatch:",
    "github.event.pull_request.head.sha || github.sha",
    "bootstrap.sh",
    "run_standalone_static_gate_unit.sh",
];

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

fn require_text(path: &Path, required: &[&str]) -> Vec<Finding> {
    let Ok(text) = fs::read_to_string(path) else {
        return vec![Finding {
            severity: "error",
            path: path.to_path_buf(),
            message: "missing_file".into(),
        }];
    };
    let normalized = Regex::new(r"/{2,}")
        .unwrap()
        .replace_all(&text, "/")
        .into_owned();
    required
        .iter()
        .filter(|item| !text.contains(**item) && !normalized.contains(**item))
        .map(|item| Finding {
            severity: "error",
            path: path.to_path_buf(),
            message: format!("missing_text:{item}"),
        })
        .collect()
}

fn check_template_gate(path: &Path) -> Vec<Finding> {
    let Ok(text) = fs::read_to_string(path) else {
        return vec![Finding {
            severity: "error",
            path: path.to_path_buf(),
            message: "missing_file".into(),
        }];
    };
    let mut findings = Vec::new();
    for item in PR_FORBIDDEN {
        if text.contains(item) {
            findings.push(Finding {
                severity: "error",
                path: path.to_path_buf(),
                message: format!("forbidden_universal_pr_gate:{item}"),
            });
        }
    }
    for field in ["source_commit", "template_pin", "pr_head"] {
        let pattern = Regex::new(&format!(r"(?m)^\s*-\s*{}:", regex::escape(field))).unwrap();
        let count = pattern.find_iter(&text).count();
        if count != 1 {
            findings.push(Finding {
                severity: "error",
                path: path.to_path_buf(),
                message: format!("identity_field_count:{field}:{count}"),
            });
        }
    }
    let count = text
        .matches("identity relation (source_commit -> template_pin -> pr_head):")
        .count();
    if count != 1 {
        findings.push(Finding {
            severity: "error",
            path: path.to_path_buf(),
            message: format!("identity_relation_count:{count}"),
        });
    }
    findings
}

fn check_headers(root: &Path) -> Vec<Finding> {
    let dir = root.join(".github/workflows");
    let mut findings = Vec::new();
    for (name, required) in [
        ("agent-improvement-guide.yml", GUIDE_REQUIRED),
        ("agent-runtime-dashboard.yml", DASHBOARD_REQUIRED),
        ("agent-canon-static-gates.yml", STATIC_GATES_REQUIRED),
    ] {
        let path = dir.join(name);
        if !path.exists() {
            continue;
        }
        findings.extend(require_text(&path, required));
        if name == "agent-runtime-dashboard.yml" {
            let guard = fs::read_to_string(&path)
                .ok()
                .and_then(|text| YamlLoader::load_from_str(&text).ok())
                .and_then(|docs| docs.into_iter().next())
                .and_then(|yaml| yaml["jobs"]["dashboard"]["if"].as_str().map(str::to_owned));
            if guard.as_deref() != Some("github.event_name != 'pull_request'") {
                findings.push(Finding {
                    severity: "error",
                    path,
                    message: "missing_dashboard_pr_job_exclusion".into(),
                });
            }
        }
    }
    findings
}

fn check_owned(root: &Path) -> Vec<Finding> {
    let mut findings = check_headers(root);
    let pr = root.join(".github/PULL_REQUEST_TEMPLATE.md");
    findings.extend(require_text(&pr, PR_REQUIRED));
    for relative in [
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        "templates/documents/github/pull-request/agent_canon.md",
    ] {
        findings.extend(check_template_gate(&root.join(relative)));
    }
    findings
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
        match fs::create_dir(&dir) {
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

struct TempConfig {
    dir: PathBuf,
    path: PathBuf,
}
impl Drop for TempConfig {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.dir);
    }
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
            code
        }
        Err(error) => {
            eprintln!("GITHUB_WORKFLOW_TOOL_START_ERROR tool={name} executable={executable} error={error}");
            127
        }
    }
}

fn run_providers(root: &Path, files: &[PathBuf]) -> Vec<i32> {
    if files.is_empty() {
        return Vec::new();
    }
    let args: Vec<String> = files
        .iter()
        .map(|path| {
            path.strip_prefix(root)
                .unwrap_or(path)
                .to_string_lossy()
                .replace('\\', "/")
        })
        .collect();
    println!("GITHUB_WORKFLOW_NATIVE_INPUTS={}", args.join(","));
    let mut statuses = Vec::with_capacity(2);
    let config = match temp_config() {
        Ok(temp) => {
            println!("GITHUB_WORKFLOW_NATIVE_TOOL=actionlint executable={ACTIONLINT} config={} shellcheck={SHELLCHECK}", temp.path.display());
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

#[cfg(test)]
fn run_with_statuses(root: &Path, statuses: &[i32]) -> (String, i32) {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let files = workflows(&root);
    let findings = check_owned(&root);
    (
        report(&root, &findings, &files, statuses),
        exit_code(&findings, statuses),
    )
}

pub fn run(args: &[String]) -> i32 {
    let mut root = PathBuf::from(".");
    let mut index = 0;
    while index < args.len() {
        if args[index] == "--root" && index + 1 < args.len() {
            root = PathBuf::from(&args[index + 1]);
            index += 2;
        } else {
            eprintln!("usage: agent-canon check-github-workflows [--root <repo-root>]");
            return 2;
        }
    }
    let root = root.canonicalize().unwrap_or(root);
    let files = workflows(&root);
    let findings = check_owned(&root);
    let statuses = run_providers(&root, &files);
    print!("{}", report(&root, &findings, &files, &statuses));
    exit_code(&findings, &statuses)
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::engine::general_purpose::STANDARD;
    use base64::Engine;
    use serde_json::Value;
    use sha2::{Digest, Sha256};

    struct TestRoot(PathBuf);
    impl TestRoot {
        fn new(label: &str) -> Self {
            static NEXT: AtomicU64 = AtomicU64::new(0);
            let id = NEXT.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "agent-canon-workflow-test-{}-{label}-{id}",
                std::process::id()
            ));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn write_corpus_file(root: &Path, relative: &str, content: &[u8]) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, content).unwrap();
    }

    fn corpus() -> Value {
        serde_json::from_str(include_str!(
            "../../../../../tests/fixtures/github_workflow_check/python_golden.json"
        ))
        .unwrap()
    }

    #[test]
    fn embedded_actionlint_config_matches_canonical_bytes() {
        let digest = format!("{:x}", Sha256::digest(ACTIONLINT_CONFIG));
        assert_eq!(
            digest,
            "8842e14b6daec1470b1b38b22524cea4c95d98cab66a992347eb94002d738e5d"
        );
    }

    #[test]
    fn captured_legacy_cli_corpus_matches_native_owned_api() {
        for case in corpus()["cli_cases"].as_array().unwrap() {
            let root = TestRoot::new(case["name"].as_str().unwrap());
            for (relative, encoded) in corpus()["shared_files"].as_object().unwrap() {
                write_corpus_file(
                    &root.0,
                    relative,
                    &STANDARD.decode(encoded.as_str().unwrap()).unwrap(),
                );
            }
            for (relative, encoded) in case["files_delta"].as_object().unwrap() {
                let path = root.0.join(relative);
                if encoded.is_null() {
                    let _ = fs::remove_file(path);
                } else {
                    write_corpus_file(
                        &root.0,
                        relative,
                        &STANDARD.decode(encoded.as_str().unwrap()).unwrap(),
                    );
                }
            }
            let statuses: Vec<i32> = case["native_statuses"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_i64().unwrap() as i32)
                .collect();
            let (actual, exit) = run_with_statuses(&root.0, &statuses);
            assert_eq!(
                actual,
                case["owned_report"].as_str().unwrap(),
                "{}",
                case["name"]
            );
            assert_eq!(
                exit,
                case["exit"].as_i64().unwrap() as i32,
                "{}",
                case["name"]
            );
        }
    }

    #[test]
    fn captured_dashboard_header_oracles_match_native_checker() {
        for case in corpus()["header_cases"].as_array().unwrap() {
            let root = TestRoot::new(case["name"].as_str().unwrap());
            for (relative, encoded) in case["files"].as_object().unwrap() {
                write_corpus_file(
                    &root.0,
                    relative,
                    &STANDARD.decode(encoded.as_str().unwrap()).unwrap(),
                );
            }
            let actual = check_headers(&root.0);
            let expected: Vec<Value> = case["findings"].as_array().unwrap().to_vec();
            assert_eq!(actual.len(), expected.len(), "{}", case["name"]);
            for (finding, expected) in actual.iter().zip(expected) {
                assert_eq!(finding.severity, expected["severity"].as_str().unwrap());
                assert_eq!(
                    finding.path.to_string_lossy(),
                    expected["path"].as_str().unwrap()
                );
                assert_eq!(finding.message, expected["message"].as_str().unwrap());
            }
        }
    }

    #[test]
    fn captured_legacy_exit_precedence_is_preserved() {
        for case in corpus()["exit_cases"].as_array().unwrap() {
            let statuses: Vec<i32> = case["native_statuses"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_i64().unwrap() as i32)
                .collect();
            let findings = if case["has_error"].as_bool().unwrap() {
                vec![Finding {
                    severity: "error",
                    path: PathBuf::from(".github/PULL_REQUEST_TEMPLATE.md"),
                    message: "captured".into(),
                }]
            } else {
                Vec::new()
            };
            assert_eq!(
                exit_code(&findings, &statuses),
                case["exit"].as_i64().unwrap() as i32
            );
        }
    }
}
