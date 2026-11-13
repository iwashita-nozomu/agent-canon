// @dependency-start
// contract implementation
// responsibility Publishes source-bound wiki page sets through the existing Git and docs providers.
// upstream design ../../../../../agents/skills/wiki-publication.md owns publication and reviewer authority
// upstream implementation ./runtime_boundary.rs owns external staging and atomic output
// downstream test ../../../../../tests/agent_tools/test_wiki_publish.py verifies native CLI behavior
// @dependency-end

use crate::path_resolution::resolve_non_strict;
use crate::python_cli_options::{resolve_long_option_prefix, LongOptionError};
use crate::runtime_boundary::RuntimeArtifactBoundary;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const USAGE: &str = "usage: agent-canon wiki-publish --wiki-root PATH --source-root PATH --source-commit SHA --repo OWNER/REPO --writer NAME --reviewer NAME [--expected-page-set-digest SHA256] [--summary-out PATH]";
const MARKER: &str = "<!-- AGENT_CANON_WIKI_SOURCE_COMMIT=";

#[derive(Debug)]
struct Failure {
    message: String,
    next_action: &'static str,
}
type Result<T> = std::result::Result<T, Failure>;
fn failure(message: impl Into<String>, next_action: &'static str) -> Failure {
    Failure {
        message: message.into(),
        next_action,
    }
}
fn storage(error: impl std::fmt::Display) -> Failure {
    failure(error.to_string(), "investigate_failure")
}

#[derive(Clone)]
struct Options {
    source: PathBuf,
    wiki: PathBuf,
    commit: String,
    repo: String,
    writer: String,
    reviewer: String,
    digest: Option<String>,
    summary: Option<PathBuf>,
}
struct Output {
    code: i32,
    stdout: String,
    stderr: String,
}
trait Runner {
    fn execute(&mut self, args: &[String], cwd: &Path) -> std::io::Result<Output>;
}
struct SystemRunner;
impl Runner for SystemRunner {
    fn execute(&mut self, args: &[String], cwd: &Path) -> std::io::Result<Output> {
        let output = Command::new(&args[0])
            .args(&args[1..])
            .current_dir(cwd)
            .output()?;
        Ok(Output {
            code: output.status.code().unwrap_or(1),
            stdout: String::from_utf8_lossy(&output.stdout).into(),
            stderr: String::from_utf8_lossy(&output.stderr).into(),
        })
    }
}
fn command(
    runner: &mut impl Runner,
    args: &[String],
    cwd: &Path,
    next: &'static str,
) -> Result<String> {
    let output = runner
        .execute(args, cwd)
        .map_err(|error| failure(error.to_string(), next))?;
    if output.code != 0 {
        return Err(failure(
            format!(
                "command failed: {}\n{}",
                args.join(" "),
                output.stderr.chars().take(4000).collect::<String>()
            ),
            next,
        ));
    }
    Ok(output.stdout)
}
fn git(runner: &mut impl Runner, args: &[&str], cwd: &Path, next: &'static str) -> Result<String> {
    let mut argv = vec!["git".into()];
    argv.extend(args.iter().map(|value| (*value).into()));
    command(runner, &argv, cwd, next).map(|value| crate::python_text::python_strip(&value).into())
}
fn slug(value: &str) -> String {
    let value = crate::python_text::python_strip(value);
    let value = value
        .strip_prefix("git@github.com:")
        .or_else(|| value.strip_prefix("https://github.com/"))
        .unwrap_or(value);
    value.strip_suffix(".git").unwrap_or(value).into()
}
fn prepare(
    options: &Options,
    runtime: &RuntimeArtifactBoundary,
    runner: &mut impl Runner,
) -> Result<(String, BTreeMap<PathBuf, Vec<u8>>)> {
    let mut pages = Vec::new();
    for entry in fs::read_dir(&options.wiki).map_err(storage)? {
        let entry = entry.map_err(storage)?;
        let path = entry.path();
        if path.is_file()
            && path
                .extension()
                .is_some_and(|value| value.to_string_lossy().eq_ignore_ascii_case("md"))
        {
            pages.push(path);
        }
    }
    pages.sort();
    if pages.is_empty() {
        return Err(failure(
            "no top-level markdown pages found in wiki root",
            "inventory_wiki_markdown_pages",
        ));
    }
    let missing: Vec<_> = ["Home.md", "_Footer.md", "_Sidebar.md"]
        .iter()
        .filter(|name| {
            !pages
                .iter()
                .any(|page| page.file_name().is_some_and(|value| value == **name))
        })
        .copied()
        .collect();
    if !missing.is_empty() {
        return Err(failure(
            format!("required wiki pages are missing: {}", missing.join(", ")),
            "add_required_wiki_pages",
        ));
    }
    let staging = runtime
        .ensure_directory(Path::new("wiki-publication/tmp"))
        .map_err(storage)?;
    let mut hasher = Sha256::new();
    let mut prepared = BTreeMap::new();
    for page in pages {
        let temporary = tempfile::tempdir_in(&staging).map_err(storage)?;
        let formatted = temporary.path().join("page.md");
        let text = fs::read_to_string(&page)
            .map_err(storage)?
            .replace("\r\n", "\n")
            .replace('\r', "\n");
        runtime
            .atomic_write_bytes(&formatted, text.as_bytes(), 0o644)
            .map_err(storage)?;
        command(
            runner,
            &[
                "tools/bin/agent-canon".into(),
                "docs".into(),
                "format".into(),
                formatted.to_string_lossy().into(),
            ],
            &options.source,
            "format_source_page",
        )?;
        let bytes = fs::read(&formatted).map_err(storage)?;
        let text = std::str::from_utf8(&bytes).map_err(storage)?;
        let marker = text.lines().find_map(|line| {
            line.strip_prefix(MARKER)
                .map(|value| value.strip_suffix("-->").unwrap_or(value))
        });
        if marker != Some(options.commit.as_str()) {
            return Err(failure(
                format!(
                    "wiki source marker mismatch for {:?}: observed={marker:?}, expected={:?}",
                    page.file_name().unwrap_or_default(),
                    options.commit
                ),
                "rewrite_source_marker_before_publish",
            ));
        }
        hasher.update(
            format!(
                "{}\0{}\0",
                page.file_name().unwrap_or_default().to_string_lossy(),
                bytes.len()
            )
            .as_bytes(),
        );
        hasher.update(&bytes);
        prepared.insert(page, bytes);
    }
    Ok((format!("{:x}", hasher.finalize()), prepared))
}
fn publish(
    options: &Options,
    configured_runtime: Option<&Path>,
    runner: &mut impl Runner,
) -> Result<Value> {
    if options.writer == options.reviewer {
        return Err(failure(
            "writer and reviewer must be different identities",
            "set_an_independent_reviewer",
        ));
    }
    if options.commit.len() != 40
        || !options
            .commit
            .bytes()
            .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
    {
        return Err(failure(
            format!("invalid source commit identity: {:?}", options.commit),
            "pin_an_exact_full_sha1_source_commit",
        ));
    }
    if git(
        runner,
        &["cat-file", "-t", &options.commit],
        &options.source,
        "source_commit_not_found_in_source_repo",
    )? != "commit"
    {
        return Err(failure(
            format!(
                "source commit {:?} is not a commit in source repo",
                options.commit
            ),
            "source_commit_not_found_in_source_repo",
        ));
    }
    let repository = slug(&options.repo);
    if repository.is_empty() {
        return Err(failure(
            "invalid source repository slug",
            "pass_repo_in_owner_name_form",
        ));
    }
    let remote = format!("https://github.com/{repository}.wiki.git");
    let cwd = std::env::current_dir().map_err(storage)?;
    let heads = git(
        runner,
        &["ls-remote", "--symref", &remote, "HEAD"],
        &cwd,
        "default_branch_unavailable",
    )?;
    let branch = heads
        .lines()
        .find_map(|line| {
            let line = line.strip_prefix("ref:")?.trim_start();
            let (reference, target) = line.split_once('\t')?;
            (target == "HEAD" && !reference.chars().any(char::is_whitespace))
                .then(|| reference.strip_prefix("refs/heads/"))
                .flatten()
        })
        .ok_or_else(|| {
            failure(
                "default wiki branch is unavailable from remote symref",
                "default_branch_unavailable",
            )
        })?
        .to_owned();
    if !options.wiki.exists() {
        git(
            runner,
            &[
                "clone",
                "--depth",
                "1",
                "--branch",
                &branch,
                &remote,
                &options.wiki.to_string_lossy(),
            ],
            &options.source,
            "prepare_wiki_sidecar_clone",
        )?;
    } else {
        if git(
            runner,
            &["rev-parse", "--is-inside-work-tree"],
            &options.wiki,
            "wiki_root_not_a_git_worktree",
        )? != "true"
        {
            return Err(failure(
                format!(
                    "wiki_root is not a git repository: {}",
                    options.wiki.display()
                ),
                "wiki_root_not_a_git_worktree",
            ));
        }
        let current = git(
            runner,
            &["branch", "--show-current"],
            &options.wiki,
            "ensure_default_wiki_branch_is_active",
        )?;
        if current != branch {
            return Err(failure(
                format!("expected default branch {branch:?}, but checked out {current:?}"),
                "checkout_default_wiki_branch_before_publish",
            ));
        }
    }
    let configured = configured_runtime.ok_or_else(|| {
        failure(
            "wiki-publication: explicit runtime root is required",
            "investigate_failure",
        )
    })?;
    let runtime = RuntimeArtifactBoundary::for_source(&options.source, Some(configured), true)
        .map_err(storage)?;
    let (digest, prepared) = prepare(options, &runtime, runner)?;
    let mut summary = json!({"action":"publish","repo":repository,"wiki_root":options.wiki,"wiki_remote":remote,"default_branch":branch,"source_commit":options.commit,"page_set_digest":digest,"page_count":prepared.len(),"writer":options.writer,"reviewer":options.reviewer});
    let Some(expected) = &options.digest else {
        summary["state"] = json!("PREPARE_OK");
        summary["next_action"] = json!("obtain_independent_reviewer_approval_for_page_set_digest");
        return Ok(summary);
    };
    if expected != &digest {
        return Err(failure(
            "wiki page-set digest does not match reviewer-approved digest",
            "page_set_digest_mismatch",
        ));
    }
    for (page, bytes) in &prepared {
        runtime
            .atomic_write_bytes(page, bytes, 0o644)
            .map_err(storage)?;
    }
    git(
        runner,
        &["config", "user.name", &options.writer],
        &options.wiki,
        "set_git_user_name",
    )?;
    git(
        runner,
        &[
            "config",
            "user.email",
            &format!("{}@example.invalid", options.writer),
        ],
        &options.wiki,
        "set_git_user_email",
    )?;
    let mut add = vec!["git".into(), "add".into()];
    add.extend(prepared.keys().map(|page| {
        page.file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .into()
    }));
    command(runner, &add, &options.wiki, "stage_wiki_page_set")?;
    if !git(
        runner,
        &["status", "--porcelain"],
        &options.wiki,
        "inspect_git_status",
    )?
    .is_empty()
    {
        git(
            runner,
            &[
                "commit",
                "-m",
                &format!("Publish wiki pages for source {}", options.commit),
            ],
            &options.wiki,
            "commit_formatted_wiki_pages",
        )?;
    }
    let local = git(
        runner,
        &["rev-parse", "HEAD"],
        &options.wiki,
        "read_local_wiki_head",
    )?;
    git(
        runner,
        &["push", "origin", &format!("HEAD:{branch}")],
        &options.wiki,
        "push_default_wiki_branch",
    )?;
    let remote_head = git(
        runner,
        &["ls-remote", &remote, &format!("refs/heads/{branch}")],
        &cwd,
        "read_remote_wiki_head",
    )?;
    let remote_head = remote_head
        .split_whitespace()
        .next()
        .ok_or_else(|| failure("remote wiki head is unavailable", "read_remote_wiki_head"))?;
    if remote_head != local {
        return Err(failure(
            format!("remote readback {remote_head:?} does not match local {local:?}"),
            "retry_with_exact_default_branch_readback",
        ));
    }
    summary["state"] = json!("PUBLISHED");
    summary["local_head"] = json!(local);
    summary["remote_head"] = json!(remote_head);
    summary["next_action"] = json!("read_exact_remote_page_set_head");
    Ok(summary)
}
pub fn run(args: &[String]) -> i32 {
    let names = [
        "--wiki-root",
        "--source-root",
        "--source-commit",
        "--repo",
        "--writer",
        "--reviewer",
        "--expected-page-set-digest",
        "--summary-out",
        "--help",
    ];
    let choices: Vec<_> = names.iter().map(|&name| (name, name)).collect();
    let mut values = BTreeMap::new();
    let mut index = 0;
    while index < args.len() {
        if args[index] == "-h" {
            println!("{USAGE}");
            return 0;
        }
        let (name, inline) = args[index]
            .split_once('=')
            .map_or((args[index].as_str(), None), |(name, value)| {
                (name, Some(value))
            });
        let name = match resolve_long_option_prefix(name, &choices) {
            Ok(name) => name,
            Err(error) => {
                let detail = match error {
                    LongOptionError::Unrecognized => {
                        format!("unrecognized arguments: {}", args[index])
                    }
                    LongOptionError::Ambiguous(matches) => format!(
                        "ambiguous option: {name} could match {}",
                        matches.join(", ")
                    ),
                };
                eprintln!("{USAGE}\n{detail}");
                return 2;
            }
        };
        if name == "--help" {
            println!("{USAGE}");
            return 0;
        }
        let value = if let Some(value) = inline {
            value
        } else {
            index += 1;
            let Some(value) = args.get(index) else {
                eprintln!("{USAGE}\nargument {name}: expected one argument");
                return 2;
            };
            value
        };
        values.insert(name, value.to_owned());
        index += 1;
    }
    for name in &names[..6] {
        if !values.contains_key(name) {
            eprintln!("{USAGE}\nrequired argument: {name}");
            return 2;
        }
    }
    let result = (|| {
        let options = Options {
            source: resolve_non_strict(Path::new(&values["--source-root"])).map_err(storage)?,
            wiki: resolve_non_strict(Path::new(&values["--wiki-root"])).map_err(storage)?,
            commit: values["--source-commit"].clone(),
            repo: values["--repo"].clone(),
            writer: values["--writer"].clone(),
            reviewer: values["--reviewer"].clone(),
            digest: values.get("--expected-page-set-digest").cloned(),
            summary: values.get("--summary-out").map(PathBuf::from),
        };
        let configured = std::env::var_os("AGENT_CANON_RUNTIME_ROOT")
            .filter(|value| !value.is_empty())
            .map(PathBuf::from);
        let summary = publish(&options, configured.as_deref(), &mut SystemRunner)?;
        if let Some(path) = &options.summary {
            let configured = std::env::var("AGENT_CANON_RUNTIME_ROOT").map_err(storage)?;
            let runtime = RuntimeArtifactBoundary::for_source(
                &options.source,
                Some(Path::new(&configured)),
                true,
            )
            .map_err(storage)?;
            runtime
                .atomic_write_bytes(
                    path,
                    &serde_json::to_vec_pretty(&summary).map_err(storage)?,
                    0o644,
                )
                .map_err(storage)?;
        }
        Ok::<_, Failure>(summary)
    })();
    match result {
        Ok(summary) => {
            println!("{summary}");
            0
        }
        Err(error) => {
            println!(
                "{}",
                json!({"message":error.message,"next_action":error.next_action})
            );
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[derive(Default)]
    struct FakeRunner {
        kind: String,
        heads: String,
        local: String,
        remote: String,
        calls: Vec<Vec<String>>,
    }
    impl Runner for FakeRunner {
        fn execute(&mut self, args: &[String], _: &Path) -> std::io::Result<Output> {
            self.calls.push(args.to_vec());
            let stdout = match args.get(1).map(String::as_str) {
                Some("cat-file") => self.kind.clone(),
                Some("ls-remote") if args.get(2).is_some_and(|value| value == "--symref") => {
                    self.heads.clone()
                }
                Some("ls-remote") => self.remote.clone(),
                Some("rev-parse")
                    if args
                        .get(2)
                        .is_some_and(|value| value == "--is-inside-work-tree") =>
                {
                    "true".into()
                }
                Some("rev-parse") => self.local.clone(),
                Some("branch") => "main".into(),
                _ => String::new(),
            };
            Ok(Output {
                code: 0,
                stdout,
                stderr: String::new(),
            })
        }
    }
    fn fixture() -> (tempfile::TempDir, Options, PathBuf, FakeRunner) {
        let temporary = tempfile::tempdir().unwrap();
        let root = temporary.path().canonicalize().unwrap();
        let source = root.join("source");
        fs::create_dir(&source).unwrap();
        let runtime = root.join("runtime");
        let wiki = runtime.join("wiki");
        fs::create_dir_all(&wiki).unwrap();
        let commit = "a".repeat(40);
        for name in ["Home.md", "_Sidebar.md", "_Footer.md"] {
            fs::write(wiki.join(name), format!("# Home\n\n{MARKER}{commit}-->\n")).unwrap();
        }
        let options = Options {
            source,
            wiki,
            commit,
            repo: "iwashita-nozomu/agent-canon".into(),
            writer: "alice".into(),
            reviewer: "bob".into(),
            digest: None,
            summary: None,
        };
        let runner = FakeRunner {
            kind: "commit".into(),
            heads: "ref: refs/heads/main\tHEAD\n".into(),
            local: "c".repeat(40),
            remote: format!("{}\trefs/heads/main\n", "c".repeat(40)),
            ..Default::default()
        };
        (temporary, options, runtime, runner)
    }
    fn independent_digest(options: &Options) -> String {
        let mut digest = Sha256::new();
        for name in ["Home.md", "_Footer.md", "_Sidebar.md"] {
            let bytes = fs::read(options.wiki.join(name)).unwrap();
            digest.update(format!("{name}\0{}\0", bytes.len()));
            digest.update(bytes);
        }
        format!("{:x}", digest.finalize())
    }
    #[test]
    fn source_identity_must_resolve_to_commit() {
        let (_temporary, options, runtime, mut runner) = fixture();
        runner.kind = "tree".into();
        assert_eq!(
            publish(&options, Some(&runtime), &mut runner)
                .unwrap_err()
                .next_action,
            "source_commit_not_found_in_source_repo"
        );
        assert_eq!(runner.calls.len(), 1);
    }
    #[test]
    fn missing_remote_default_is_a_typed_failure() {
        let (_temporary, options, runtime, mut runner) = fixture();
        runner.heads.clear();
        assert_eq!(
            publish(&options, Some(&runtime), &mut runner)
                .unwrap_err()
                .next_action,
            "default_branch_unavailable"
        );
    }
    #[test]
    fn required_top_level_pages_are_enforced() {
        let (_temporary, options, runtime, mut runner) = fixture();
        fs::remove_file(options.wiki.join("_Footer.md")).unwrap();
        assert_eq!(
            publish(&options, Some(&runtime), &mut runner)
                .unwrap_err()
                .next_action,
            "add_required_wiki_pages"
        );
    }
    #[test]
    fn prepare_digest_matches_independent_byte_stream_without_writes_or_clone() {
        let (_temporary, options, runtime, mut runner) = fixture();
        fs::write(options.wiki.join("draft.txt"), "ignored").unwrap();
        let expected = independent_digest(&options);
        let summary = publish(&options, Some(&runtime), &mut runner).unwrap();
        assert_eq!(summary["state"], "PREPARE_OK");
        assert_eq!(summary["page_count"], 3);
        assert_eq!(summary["page_set_digest"], expected);
        assert!(!runner
            .calls
            .iter()
            .any(|args| ["clone", "push", "add", "commit"].contains(&args[1].as_str())));
        assert_eq!(independent_digest(&options), expected);
    }
    #[test]
    fn reviewer_digest_mismatch_stops_before_git_mutation() {
        let (_temporary, mut options, runtime, mut runner) = fixture();
        options.digest = Some("bad".into());
        assert_eq!(
            publish(&options, Some(&runtime), &mut runner)
                .unwrap_err()
                .next_action,
            "page_set_digest_mismatch"
        );
        assert!(!runner
            .calls
            .iter()
            .any(|args| ["push", "add", "commit", "config"].contains(&args[1].as_str())));
    }
    #[test]
    fn publish_pushes_only_default_branch_and_checks_exact_head() {
        let (_temporary, mut options, runtime, mut runner) = fixture();
        options.digest = Some(independent_digest(&options));
        let summary = publish(&options, Some(&runtime), &mut runner).unwrap();
        assert_eq!(summary["state"], "PUBLISHED");
        assert_eq!(summary["local_head"], "c".repeat(40));
        assert_eq!(summary["remote_head"], "c".repeat(40));
        assert!(runner.calls.contains(&vec![
            "git".into(),
            "push".into(),
            "origin".into(),
            "HEAD:main".into()
        ]));
    }
    #[test]
    fn remote_head_mismatch_is_not_published() {
        let (_temporary, mut options, runtime, mut runner) = fixture();
        options.digest = Some(independent_digest(&options));
        runner.remote = "different\trefs/heads/main".into();
        assert_eq!(
            publish(&options, Some(&runtime), &mut runner)
                .unwrap_err()
                .next_action,
            "retry_with_exact_default_branch_readback"
        );
    }
}
