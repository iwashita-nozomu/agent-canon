// @dependency-start
// contract test
// responsibility Preserves the native registry command's schema, topic, variant, Git, and artifact checks.
// upstream implementation ../src/experiment_registry.rs native registry validator
// upstream implementation ../src/experiment_identity.rs shared safe topic and variant grammar
// upstream design ../../../../../documents/experiments/experiment-registry.md registry contract
// @dependency-end

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

use agent_canon::experiment_identity::validate_segment;

struct RepoFixture {
    _temp: TempDir,
    root: PathBuf,
}

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("crate is nested below repository root")
        .to_path_buf()
}

fn fixture_root() -> PathBuf {
    repository_root().join("tests/fixtures/experiment_registry")
}

fn copy_fixture_tree(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).expect("fixture destination directory creates");
    let mut entries = fs::read_dir(source)
        .expect("registry fixture directory reads")
        .map(|entry| entry.expect("fixture entry reads").path())
        .collect::<Vec<_>>();
    entries.sort();
    for path in entries {
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .expect("fixture path has a UTF-8 file name");
        if path.is_dir() {
            copy_fixture_tree(&path, &destination.join(name));
            continue;
        }
        let output_name = name.strip_suffix(".fixture").unwrap_or(name);
        let output = destination.join(output_name);
        fs::create_dir_all(output.parent().expect("fixture has a parent"))
            .expect("fixture parent creates");
        fs::copy(&path, output).expect("fixture file copies");
    }
}

fn initialize_git(root: &Path) {
    let output = Command::new("git")
        .args(["init", "--quiet"])
        .current_dir(root)
        .output()
        .expect("git initializes the controlled fixture");
    assert!(
        output.status.success(),
        "git init failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

fn build_repo() -> RepoFixture {
    let temp = tempfile::tempdir().expect("temporary registry repo creates");
    let root = fs::canonicalize(temp.path()).expect("fixture root resolves platform aliases");
    copy_fixture_tree(&fixture_root(), &root);
    let managed_owner = root.join("tools/runtime/dispatch/agent-canon/src/managed_experiment.rs");
    fs::create_dir_all(managed_owner.parent().expect("managed owner has parent"))
        .expect("managed owner fixture parent creates");
    fs::write(&managed_owner, "// registry path fixture\n").expect("managed owner fixture writes");
    fs::rename(
        root.join("registry.toml"),
        root.join("experiments/registry.toml"),
    )
    .expect("registry fixture is placed at its public path");
    initialize_git(&root);
    RepoFixture { _temp: temp, root }
}

fn registry_path(repo: &RepoFixture) -> PathBuf {
    repo.root.join("experiments/registry.toml")
}

fn registry_text(repo: &RepoFixture) -> String {
    fs::read_to_string(registry_path(repo)).expect("fixture registry reads")
}

fn replace_registry(repo: &RepoFixture, old: &str, new: &str) {
    let text = registry_text(repo);
    assert!(
        text.contains(old),
        "fixture must contain the replacement source"
    );
    fs::write(registry_path(repo), text.replace(old, new)).expect("registry variant writes");
}

fn append_registry(repo: &RepoFixture, text: &str) {
    let mut file = fs::OpenOptions::new()
        .append(true)
        .open(registry_path(repo))
        .expect("registry opens for append");
    file.write_all(text.as_bytes())
        .expect("registry entry appends");
}

fn run_cli_in(cwd: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["experiment-registry"])
        .args(args)
        .current_dir(cwd)
        .output()
        .expect("native experiment-registry command runs")
}

fn run_cli(repo: &RepoFixture, args: &[&str]) -> Output {
    let mut command_args = vec![
        "--repo-root",
        repo.root.to_str().expect("repo root is UTF-8"),
    ];
    command_args.extend_from_slice(args);
    run_cli_in(&repo.root, &command_args)
}

fn stdout(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

fn append_branch_topic(repo: &RepoFixture, name: &str, branch: &str, note: &str) {
    append_registry(
        repo,
        &format!(
            "\n[[branch_topics]]\nname = \"{name}\"\nstatus = \"active\"\nremote_branch = \"{branch}\"\nprimary_note = \"{note}\"\n"
        ),
    );
}

fn git_ok(root: &Path, args: &[&str]) {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .expect("controlled git command starts");
    assert!(
        output.status.success(),
        "git {} failed: {}",
        args.join(" "),
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn valid_registry_passes_through_the_public_cli() {
    let repo = build_repo();

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains(&format!("repo_root={}", repo.root.display())));
    assert!(stdout(&output).contains("OK: experiment registry is valid"));
}

#[test]
fn native_identity_segment_validator_preserves_the_shared_safe_grammar() {
    assert_eq!(validate_segment("topic.v1", "topic"), Ok(()));
    for (value, message) in [
        ("", "must be a non-empty string"),
        (".", "must not be . or .."),
        ("a/b", "must not contain a path separator or NUL"),
        ("a\\b", "must not contain a path separator or NUL"),
        ("a b", "must not contain whitespace"),
        ("Ａ", "must not change under normalization"),
        ("é", "must match [A-Za-z0-9][A-Za-z0-9._-]*"),
    ] {
        assert!(validate_segment(value, "topic")
            .expect_err("unsafe segment is rejected")
            .contains(message));
    }
}

#[test]
fn native_registry_command_has_a_source_independent_help_surface() {
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["experiment-registry", "--help"])
        .output()
        .expect("native registry help runs without a project registry");

    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains("agent-canon experiment-registry"));
    assert!(stdout(&output).contains("--repo-root PATH"));
    assert!(stdout(&output).contains("--registry PATH"));
}

#[test]
fn report_root_cannot_append_the_topic_name_twice() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "report_root = \"experiments/demo_topic/report\"\n",
        "report_root = \"experiments/demo_topic/report/demo_topic\"\n",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("report_root must be experiments/demo_topic/report"));
}

#[test]
fn missing_required_fields_are_reported() {
    let repo = build_repo();
    replace_registry(&repo, "status = \"active\"\n", "");

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("demo_topic: missing required string field: status"));
}

#[test]
fn malformed_eval_artifact_items_keep_their_indexed_diagnostic() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "required_eval_artifacts = [\"summary/summary.json\", \"summary/cases.jsonl\"]",
        "required_eval_artifacts = [\"summary/summary.json\", \"\"]",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(
        stdout(&output).contains("defaults: required_eval_artifacts[1] must be a non-empty string")
    );
}

#[test]
fn branch_topic_with_local_ref_and_note_is_valid() {
    let repo = build_repo();
    git_ok(
        &repo.root,
        &[
            "-c",
            "user.name=Registry Test",
            "-c",
            "user.email=registry-test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        ],
    );
    git_ok(&repo.root, &["branch", "experiment/branch-only"]);
    let note_path = repo.root.join("documents/notes/branches/branch_only.md");
    fs::create_dir_all(note_path.parent().unwrap()).expect("branch note directory creates");
    fs::write(&note_path, "# Branch Only\n").expect("branch note fixture writes");
    append_branch_topic(
        &repo,
        "branch_only",
        "experiment/branch-only",
        "documents/notes/branches/branch_only.md",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains("OK: experiment registry is valid"));
}

#[test]
fn duplicate_names_are_rejected_across_topic_tables() {
    let repo = build_repo();
    let note_path = repo.root.join("documents/notes/branches/demo_topic.md");
    fs::create_dir_all(note_path.parent().unwrap()).expect("branch note directory creates");
    fs::write(&note_path, "# Demo Topic Branch\n").expect("branch note fixture writes");
    append_branch_topic(
        &repo,
        "demo_topic",
        "experiment/demo-topic",
        "documents/notes/branches/demo_topic.md",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("duplicate topic name: demo_topic"));
}

#[test]
fn default_repo_root_comes_from_the_invocation_git_checkout() {
    let repo = build_repo();

    let output = run_cli_in(&repo.root, &[]);

    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains(&format!("repo_root={}", repo.root.display())));
    assert!(stdout(&output).contains("OK: experiment registry is valid"));
}

#[test]
fn inner_commands_must_not_reenter_the_managed_runner() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "default_inner_command = \"python3 experiments/demo_topic/run.py --run-dir {run_dir} --config {config_path} --mode default\"",
        "default_inner_command = \"tools/bin/agent-canon run-managed-experiment --topic demo_topic --variant default\"",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("must not call the managed runner recursively"));
}

#[test]
fn registered_commands_may_omit_the_runner_run_dir_placeholder() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "default_inner_command = \"python3 experiments/demo_topic/run.py --run-dir {run_dir} --config {config_path} --mode default\"",
        "default_inner_command = \"/usr/bin/python /workspace/experiments/demo_topic/run.py --config {config_path}\"",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains("OK: experiment registry is valid"));
}

#[test]
fn registered_commands_must_consume_the_config_snapshot() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "default_inner_command = \"python3 experiments/demo_topic/run.py --run-dir {run_dir} --config {config_path} --mode default\"",
        "default_inner_command = \"/usr/bin/python /workspace/experiments/demo_topic/run.py\"",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("must include {config_path}"));
}

#[test]
fn canonical_entrypoint_must_stay_inside_the_topic() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "experiments/demo_topic/run.py",
        "python/package/experiment.py",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("canonical_entrypoint must be the topic-local run.py"));
}

#[test]
fn reserved_managed_artifacts_cannot_be_registered_as_eval_patterns() {
    let repo = build_repo();
    replace_registry(
        &repo,
        "required_eval_artifacts = [\"summary/summary.json\", \"summary/cases.jsonl\"]",
        "required_eval_artifacts = [\"summary/summary.json\", \"summary/cases.jsonl\", \"run.log\", \"logs/stdout.log\"]",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("reserved managed artifacts"));
}

#[test]
fn topic_identity_rejects_values_changed_by_nfkc() {
    let repo = build_repo();
    replace_registry(&repo, "name = \"demo_topic\"", "name = \"Ａ\"");

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(1));
    assert!(stdout(&output).contains("topic must not change under normalization"));
}

#[test]
fn branch_refs_and_optional_source_commit_follow_warning_semantics() {
    let repo = build_repo();
    let note_path = repo.root.join("documents/notes/branches/branch_only.md");
    fs::create_dir_all(note_path.parent().unwrap()).expect("branch note directory creates");
    fs::write(&note_path, "# Branch Only\n").expect("branch note fixture writes");
    append_registry(
        &repo,
        "\n[[branch_topics]]\nname = \"branch_only\"\nstatus = \"active\"\nremote_branch = \"missing/branch\"\nprimary_note = \"documents/notes/branches/branch_only.md\"\nsource_commit = \"missing-commit\"\n",
    );

    let output = run_cli(&repo, &[]);

    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains("remote_branch does not exist"));
    assert!(stdout(&output).contains("source_commit does not exist"));
    assert!(stdout(&output).contains("OK: experiment registry is valid"));
}

#[test]
fn registry_override_and_parse_exit_codes_are_preserved() {
    let repo = build_repo();
    let alternate = repo.root.join("custom/registry.toml");
    fs::create_dir_all(alternate.parent().unwrap()).expect("custom registry directory creates");
    fs::copy(registry_path(&repo), &alternate).expect("custom registry fixture copies");
    let alternate_arg = alternate.to_str().expect("custom path is UTF-8");
    let output = run_cli(&repo, &["--registry", alternate_arg]);
    assert_eq!(output.status.code(), Some(0));
    assert!(stdout(&output).contains(&format!("registry_path={}", alternate.display())));

    fs::write(&alternate, "schema_version = [").expect("malformed TOML fixture writes");
    let output = run_cli(&repo, &["--registry", alternate_arg]);
    assert_eq!(output.status.code(), Some(2));
    assert!(!String::from_utf8_lossy(&output.stderr).is_empty());
}
