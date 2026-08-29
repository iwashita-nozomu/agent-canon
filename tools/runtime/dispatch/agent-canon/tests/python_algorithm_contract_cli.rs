// @dependency-start
// contract test
// responsibility Verifies the public Rust CLI parity matrix for Python algorithm contracts.
// upstream design ../../../documents/design/jax_util/algorithm_module_contract.md parity matrix and CLI artifact contract
// upstream implementation ../src/python_algorithm_contract.rs canonical Rust checker
// @dependency-end

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::time::{SystemTime, UNIX_EPOCH};

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .and_then(Path::parent)
        .expect("crate lives below repository root")
        .to_path_buf()
}

fn fixture_root(name: &str) -> PathBuf {
    repository_root()
        .join("tests/fixtures/python_algorithm_contract")
        .join(name)
}

fn stored_fixture_path(relative: &str) -> PathBuf {
    let requested = fixture_root(relative);
    if requested.exists() {
        return requested;
    }
    let stored = PathBuf::from(format!("{}.fixture", requested.display()));
    assert!(
        stored.is_file(),
        "stored fixture is missing: {}",
        stored.display()
    );
    stored
}

fn materialize_fixture(relative: &str) -> PathBuf {
    let stored = stored_fixture_path(relative);
    let root = unique_temp_dir("stored-fixture");
    if stored.is_dir() {
        materialize_fixture_tree(&stored, &stored, &root);
    } else {
        materialize_fixture_file(&stored, stored.parent().unwrap(), &root);
    }
    root
}

fn materialize_fixture_tree(source_root: &Path, current: &Path, destination_root: &Path) {
    let mut entries = fs::read_dir(current)
        .expect("stored fixture directory reads")
        .flatten()
        .map(|entry| entry.path())
        .collect::<Vec<_>>();
    entries.sort();
    for path in entries {
        if path.is_dir() {
            materialize_fixture_tree(source_root, &path, destination_root);
        } else {
            materialize_fixture_file(&path, source_root, destination_root);
        }
    }
}

fn materialize_fixture_file(path: &Path, source_root: &Path, destination_root: &Path) {
    let relative = path
        .strip_prefix(source_root)
        .expect("stored fixture path is below its root");
    let name = path
        .file_name()
        .and_then(|value| value.to_str())
        .expect("stored fixture has a UTF-8 filename");
    assert!(
        name.ends_with(".py.fixture"),
        "tracked fixture source must use a non-Python extension: {}",
        path.display()
    );
    let mut destination = destination_root.join(relative);
    destination.set_file_name(name.strip_suffix(".fixture").unwrap());
    fs::create_dir_all(destination.parent().unwrap()).expect("fixture destination creates");
    fs::copy(path, &destination).expect("fixture source materializes as Python source");
}

fn run_cli(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(args)
        .output()
        .expect("agent-canon CLI runs")
}

fn unique_temp_dir(name: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock is after epoch")
        .as_nanos();
    let path = std::env::temp_dir().join(format!("agent-canon-python-contract-{name}-{nonce}"));
    fs::create_dir_all(&path).expect("temporary fixture directory creates");
    path
}

fn write_variant(name: &str, source: String) -> PathBuf {
    let root = unique_temp_dir(name);
    let path = root.join("variant.py");
    fs::write(&path, source).expect("variant fixture writes");
    path
}

fn json(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).expect("CLI JSON is parseable")
}

#[test]
fn valid_fixture_has_canonical_json_projection() {
    let root = materialize_fixture("valid.py");
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "valid.py",
    ]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = json(&output);
    assert_eq!(payload["summary"]["files"], 1);
    assert_eq!(payload["summary"]["algorithm_modules"], 1);
    assert_eq!(payload["summary"]["findings"], 0);
    assert_eq!(payload["summary"]["parse_errors"], 0);
    assert_eq!(payload["summary"]["status"], "pass");
    assert_eq!(
        payload["algorithm_modules"],
        serde_json::json!(["valid.py"])
    );
    assert_eq!(payload["modules"][0]["path"], "valid.py");
    assert_eq!(payload["modules"][0]["public_names"][0], "Algorithm");
    assert_eq!(payload["modules"][0]["all_names"][0], "InitializeConfig");
    let text = String::from_utf8_lossy(&output.stdout);
    assert!(text.find("\"summary\"").unwrap() < text.find("\"algorithm_modules\"").unwrap());
    assert!(text.find("\n  \"modules\"").unwrap() < text.find("\n  \"parse_errors\"").unwrap());
    assert!(text.find("\n  \"parse_errors\"").unwrap() < text.find("\n  \"findings\"").unwrap());
}

#[test]
fn malformed_mixed_fixture_preserves_valid_module_and_typed_parse_error() {
    let root = materialize_fixture("mixed");
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
    ]);
    assert_eq!(output.status.code(), Some(1));
    let payload = json(&output);
    assert_eq!(
        payload["summary"],
        serde_json::json!({"files": 2, "algorithm_modules": 1, "findings": 0, "parse_errors": 1, "status": "fail"})
    );
    assert_eq!(
        payload["algorithm_modules"],
        serde_json::json!(["10_valid.py"])
    );
    assert_eq!(
        payload["parse_errors"][0],
        serde_json::json!({"path": "00_malformed.py", "line": 2, "kind": "syntax_error", "detail": "parseable"})
    );

    let text_output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
    ]);
    assert_eq!(text_output.status.code(), Some(1));
    let text = String::from_utf8_lossy(&text_output.stdout);
    assert!(text.contains("PY_ALGORITHM_CONTRACT_PARSE_ERROR=00_malformed.py:2:parseable"));
    assert!(text.contains("PY_ALGORITHM_CONTRACT_FILES=2"));
    assert!(text.contains("PY_ALGORITHM_CONTRACT_PARSE_ERRORS=1"));
}

#[test]
fn nested_dependency_rows_preserve_local_config_exemption_and_parent_config_oracle() {
    let root = materialize_fixture("");
    for file in ["parent_config.py", "parent_local.py", "problem_only.py"] {
        let path = root.join("nested").join(file);
        let relative = format!("nested/{file}");
        let output = run_cli(&[
            "python-algorithm-contract-check",
            "--root",
            root.to_str().unwrap(),
            "--format",
            "json",
            &relative,
        ]);
        assert!(
            output.status.success(),
            "{file}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let payload = json(&output);
        assert_eq!(payload["summary"]["findings"], 0);
        if file == "parent_local.py" {
            assert_eq!(
                payload["modules"][0]["dependencies"][0]["contract_classes"],
                serde_json::json!(["Algorithm"])
            );
            assert_eq!(
                payload["modules"][0]["dependencies"][0]["sources"],
                serde_json::json!(["annotation", "initialize_call"])
            );
        }
        if file == "problem_only.py" {
            assert_eq!(payload["modules"][0]["dependencies"], serde_json::json!([]));
        }
        assert!(path.exists());
    }

    let parent = fs::read_to_string(root.join("nested").join("parent_config.py"))
        .expect("parent fixture reads");
    let missing = write_variant(
        "missing-parent-config",
        parent.replace(
            "    child_initialize: child.InitializeConfig\n",
            "    pass\n",
        ),
    );
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        missing.parent().unwrap().to_str().unwrap(),
        "--format",
        "json",
        "variant.py",
    ]);
    assert_eq!(output.status.code(), Some(1));
    let payload = json(&output);
    assert!(payload["findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["subject"] == "child.InitializeConfig"));
}

#[test]
fn protocol_only_imports_have_one_non_allowlisted_finding_and_allowlisted_zero() {
    let root = materialize_fixture("protocol");
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
    ]);
    assert_eq!(output.status.code(), Some(1));
    let payload = json(&output);
    assert_eq!(payload["summary"]["algorithm_modules"], 0);
    assert_eq!(payload["summary"]["findings"], 1);
    assert_eq!(
        payload["findings"][0],
        serde_json::json!({"path": "helper.py", "line": 1, "kind": "non_algorithm_protocol_import", "subject": "algorithm_module_protocol", "detail": "define-standard-public-surface-or-remove-import"})
    );
}

#[test]
fn public_surface_and_info_findings_use_canonical_kinds() {
    let source_root = materialize_fixture("valid.py");
    let source = fs::read_to_string(source_root.join("valid.py")).expect("valid fixture reads");
    let assert_kind = |name: &str, variant: String, kind: &str, expected_status: Option<i32>| {
        let path = write_variant(name, variant);
        let output = run_cli(&[
            "python-algorithm-contract-check",
            "--root",
            path.parent().unwrap().to_str().unwrap(),
            "--format",
            "json",
            "variant.py",
        ]);
        assert_eq!(output.status.code(), expected_status);
        assert!(json(&output)["findings"]
            .as_array()
            .unwrap()
            .iter()
            .any(|finding| finding["kind"] == kind));
    };

    let extra_all = write_variant(
        "extra-all",
        source.replace(
            "    \"initialize\",\n]",
            "    \"initialize\",\n    \"solve\",\n]",
        ),
    );
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        extra_all.parent().unwrap().to_str().unwrap(),
        "--format",
        "json",
        "variant.py",
    ]);
    assert_eq!(output.status.code(), Some(1));
    assert!(json(&output)["findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "extra_all"));

    let info_alias = write_variant(
        "info-alias",
        source.replace("class Info(amp.Info):\n    pass", "Info = amp.Info"),
    );
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        info_alias.parent().unwrap().to_str().unwrap(),
        "--format",
        "json",
        "variant.py",
    ]);
    assert_eq!(output.status.code(), Some(1));
    assert!(json(&output)["findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|finding| finding["kind"] == "info_not_concrete"));

    assert_kind(
        "extra-public-definition",
        format!("{source}\ndef solve() -> None:\n    pass\n"),
        "extra_public_definition",
        Some(1),
    );
    assert_kind(
        "missing-all",
        source.split("__all__ = [").next().unwrap().to_string(),
        "missing_all",
        Some(1),
    );
    assert_kind(
        "dynamic-all",
        format!(
            "{}__all__ = REQUIRED\n",
            source.split("__all__ = [").next().unwrap()
        ),
        "dynamic_all",
        Some(1),
    );
    assert_kind(
        "missing-all-name",
        source.replace("    \"Info\",\n", ""),
        "missing_all_name",
        Some(1),
    );
    assert_kind(
        "missing-public-definition",
        source.replace("class Info(amp.Info):\n    pass\n\n", ""),
        "missing_public_definition",
        Some(1),
    );
    assert_kind(
        "algorithm-not-callable",
        source.replace(
            "    def __call__(self, problem: Problem, state: State, config: SolveConfig) -> Answer:\n        return Answer()\n",
            "    pass\n",
        ),
        "algorithm_not_callable",
        Some(1),
    );
    assert_kind(
        "missing-algorithm-function-object",
        source.replace(
            "class Algorithm(amp.Algorithm):\n    def __call__(self, problem: Problem, state: State, config: SolveConfig) -> Answer:\n        return Answer()\n",
            "Algorithm = amp.Algorithm\n",
        ),
        "missing_algorithm_function_object",
        Some(1),
    );
    let status_constant = write_variant(
        "status-constant",
        format!("{source}\nSTATUS_LOCAL_OPTIMAL = 1\n"),
    );
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        status_constant.parent().unwrap().to_str().unwrap(),
        "--format",
        "json",
        "variant.py",
    ]);
    assert!(output.status.success());
    assert_eq!(json(&output)["findings"], serde_json::json!([]));
}

#[test]
fn exclude_globs_and_repeatable_union_match_fixture_counts() {
    let root = materialize_fixture("exclude");
    let no_exclude = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
    ]);
    assert!(no_exclude.status.success());
    assert_eq!(json(&no_exclude)["summary"]["files"], 3);
    assert_eq!(json(&no_exclude)["summary"]["algorithm_modules"], 3);

    let generated = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "--exclude",
        "pkg/generated/*.py",
    ]);
    assert!(generated.status.success());
    assert_eq!(json(&generated)["summary"]["files"], 2);
    assert_eq!(json(&generated)["summary"]["algorithm_modules"], 2);
    assert_eq!(
        json(&generated)["algorithm_modules"].as_array().unwrap()[0],
        "pkg/a_generated.py"
    );

    let generated_directory = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "--exclude",
        "*/generated",
    ]);
    assert!(generated_directory.status.success());
    assert_eq!(json(&generated_directory)["summary"]["files"], 3);
    assert!(json(&generated_directory)["algorithm_modules"]
        .as_array()
        .unwrap()
        .iter()
        .any(|path| path == "pkg/generated/a.py"));

    let suffix = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "--exclude",
        "*_generated.py",
    ]);
    assert!(suffix.status.success());
    assert_eq!(json(&suffix)["summary"]["files"], 2);
    assert_eq!(json(&suffix)["summary"]["algorithm_modules"], 2);
    assert!(json(&suffix)["algorithm_modules"]
        .as_array()
        .unwrap()
        .iter()
        .any(|path| path == "pkg/generated/a.py"));

    let both = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "--exclude",
        "pkg/generated/*.py",
        "--exclude",
        "*_generated.py",
    ]);
    assert!(both.status.success());
    assert_eq!(json(&both)["summary"]["files"], 1);
    assert_eq!(json(&both)["summary"]["algorithm_modules"], 1);
    assert_eq!(json(&both)["modules"][0]["path"], "pkg/keep.py");

    let prefix = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "--exclude",
        "pkg",
    ]);
    assert!(prefix.status.success());
    assert_eq!(json(&prefix)["summary"]["files"], 0);
}

#[test]
fn legacy_stopping_policy_fixture_preserves_rust_finding() {
    let root = materialize_fixture("stopping/legacy_policy.py");
    let output = run_cli(&[
        "python-algorithm-contract-check",
        "--root",
        root.to_str().unwrap(),
        "--format",
        "json",
        "legacy_policy.py",
    ]);
    assert_eq!(output.status.code(), Some(1));
    let payload = json(&output);
    assert_eq!(
        payload["summary"],
        serde_json::json!({
            "files": 1,
            "algorithm_modules": 1,
            "findings": 1,
            "parse_errors": 0,
            "status": "fail"
        })
    );
    assert_eq!(
        payload["findings"][0],
        serde_json::json!({
            "path": "legacy_policy.py",
            "line": 7,
            "kind": "legacy_stopping_policy_field",
            "subject": "criterion",
            "detail": "use imported stopping.SolveConfig so the nested algorithm contract is inferred"
        })
    );
}
