// @dependency-start
// contract test
// responsibility Checks shell-facing runtime operations through the real CLI and retained filesystem boundary.
// upstream implementation ../src/runtime_paths.rs owns shell routing
// upstream implementation ../src/runtime_boundary.rs owns filesystem effects
// @dependency-end

use std::fs;
use std::path::Path;
use std::process::{Command, Output};

fn temp() -> tempfile::TempDir {
    tempfile::tempdir_in(std::env::temp_dir().canonicalize().unwrap()).unwrap()
}
fn run(source: &Path, runtime: &Path, action: &str, args: &[&str]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command
        .args(["runtime-paths", action, "--source-root"])
        .arg(source)
        .arg("--runtime-root")
        .arg(runtime)
        .args(args);
    for key in [
        "AGENT_CANON_PARENT_ROOT",
        "AGENT_CANON_CONTROL_PARENT_ROOT",
        "AGENT_CANON_TARGET_ROOT",
        "AGENT_CANON_PARENT_ROOT_CAPABILITY",
        "AGENT_CANON_TARGET_ROOT_CAPABILITY",
        "AGENT_CANON_PARENT_ROOT_DEV",
        "AGENT_CANON_PARENT_ROOT_INO",
        "AGENT_CANON_TARGET_ROOT_DEV",
        "AGENT_CANON_TARGET_ROOT_INO",
    ] {
        command.env_remove(key);
    }
    command.output().unwrap()
}
fn okay(output: Output) -> String {
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8(output.stdout).unwrap().trim().into()
}

#[test]
fn readonly_preflight_rejects_escapes_and_unknown_actions_without_creating_runtime() {
    let temp = temp();
    let source = temp.path().join("source");
    let runtime = temp.path().join("runtime");
    fs::create_dir(&source).unwrap();
    assert_eq!(
        okay(run(&source, &runtime, "root", &["--create", "false"])),
        runtime.display().to_string()
    );
    assert!(!runtime.exists());
    for (action, args) in [
        (
            "path",
            vec!["--create", "false", "--candidate", "../escape"],
        ),
        ("unknown", vec![]),
    ] {
        assert_eq!(run(&source, &runtime, action, &args).status.code(), Some(2));
        assert!(!runtime.exists());
    }
    assert_eq!(
        run(
            &source,
            &source.join("output"),
            "root",
            &["--create", "false"]
        )
        .status
        .code(),
        Some(2)
    );
    assert!(!source.join("output").exists());
}

#[test]
fn runtime_must_be_external_to_source_and_selected_target_within_control() {
    let temp = temp();
    let source = temp.path().join("canon");
    let target = temp.path().join("target");
    let runtime = temp.path().join("runtime");
    fs::create_dir(&source).unwrap();
    fs::create_dir(&target).unwrap();
    let output = run(
        &source,
        &runtime,
        "path",
        &[
            "--create",
            "false",
            "--candidate",
            "report.md",
            "--target-root",
            target.to_str().unwrap(),
            "--control-parent-root",
            source.to_str().unwrap(),
        ],
    );
    assert_eq!(output.status.code(), Some(2));
    assert!(!runtime.exists());
    let output = run(
        &source,
        &target.join("cache"),
        "root",
        &["--target-root", target.to_str().unwrap()],
    );
    assert_eq!(output.status.code(), Some(2));
    assert!(!target.join("cache").exists());
}

#[test]
fn private_temp_copy_atomic_write_and_exact_cleanup_stay_in_runtime() {
    let temp = temp();
    let source = temp.path().join("source");
    let runtime = temp.path().join("runtime");
    fs::create_dir(&source).unwrap();
    fs::write(source.join("input.txt"), b"source bytes\n").unwrap();
    let reserved = okay(run(
        &source,
        &runtime,
        "temp-dir",
        &["--candidate", "tasks/scan", "--prefix", "scan-"],
    ));
    let reserved = Path::new(&reserved);
    assert!(reserved.starts_with(&runtime));
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(reserved).unwrap().permissions().mode() & 0o777,
            0o700
        );
    }
    let copied = reserved.join("input.txt");
    okay(run(
        &source,
        &runtime,
        "copy-read-only",
        &[
            "--source",
            "input.txt",
            "--candidate",
            copied.to_str().unwrap(),
        ],
    ));
    assert_eq!(fs::read(&copied).unwrap(), b"source bytes\n");
    let written = reserved.join("copy.txt");
    okay(run(
        &source,
        &runtime,
        "write-file",
        &[
            "--input",
            copied.to_str().unwrap(),
            "--candidate",
            written.to_str().unwrap(),
        ],
    ));
    assert_eq!(fs::read(written).unwrap(), b"source bytes\n");
    okay(run(
        &source,
        &runtime,
        "remove-tree",
        &["--candidate", reserved.to_str().unwrap()],
    ));
    assert!(!reserved.exists());
    assert_eq!(
        fs::read(source.join("input.txt")).unwrap(),
        b"source bytes\n"
    );
}

#[cfg(unix)]
#[test]
fn symlinks_cannot_redirect_copy_write_or_cleanup() {
    use std::os::unix::fs::symlink;
    let temp = temp();
    let source = temp.path().join("source");
    let runtime = temp.path().join("runtime");
    let outside = temp.path().join("outside");
    for path in [&source, &runtime, &outside] {
        fs::create_dir(path).unwrap();
    }
    fs::write(outside.join("keep"), b"keep").unwrap();
    symlink(&outside, source.join("link")).unwrap();
    symlink(&outside, runtime.join("link")).unwrap();
    for (action, args) in [
        (
            "copy-read-only",
            vec!["--source", "link/keep", "--candidate", "copied"],
        ),
        ("remove-tree", vec!["--candidate", "link"]),
        ("path", vec!["--candidate", "link/escape"]),
    ] {
        assert_eq!(run(&source, &runtime, action, &args).status.code(), Some(2));
    }
    assert_eq!(fs::read(outside.join("keep")).unwrap(), b"keep");
    assert!(!runtime.join("copied").exists());
}

#[test]
fn report_and_identity_readers_preserve_success_failure_and_counts() {
    let temp = temp();
    let source = temp.path().join("source");
    let runtime = temp.path().join("runtime");
    fs::create_dir(&source).unwrap();
    let input = temp.path().join("input.json");
    fs::write(&input, r#"{"results":{"b":[{}],"a":[{},{}]}}"#).unwrap();
    let output = run(
        &source,
        &runtime,
        "detect-secrets-report",
        &["--input", input.to_str().unwrap()],
    );
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(String::from_utf8(output.stdout).unwrap(),"SECRET_SCAN_DETECT_SECRETS_FINDINGS=3\nSECRET_SCAN_DETECT_SECRETS_PATH=a findings=2\nSECRET_SCAN_DETECT_SECRETS_PATH=b findings=1\n");
    fs::write(&input, "{}").unwrap();
    assert_eq!(
        okay(run(
            &source,
            &runtime,
            "detect-secrets-report",
            &["--input", input.to_str().unwrap()]
        )),
        "SECRET_SCAN_DETECT_SECRETS_FINDINGS=0"
    );
    fs::write(&input, r#"{"source_identity":"abc"}"#).unwrap();
    okay(run(
        &source,
        &runtime,
        "receipt-identity",
        &[
            "--input",
            input.to_str().unwrap(),
            "--expected-identity",
            "abc",
        ],
    ));
    assert_eq!(
        run(
            &source,
            &runtime,
            "receipt-identity",
            &[
                "--input",
                input.to_str().unwrap(),
                "--expected-identity",
                "different"
            ]
        )
        .status
        .code(),
        Some(2)
    );
    assert!(!runtime.exists());
}

#[cfg(unix)]
#[test]
fn capture_validates_destination_before_running_the_external_command() {
    let temp = temp();
    let source = temp.path().join("source");
    let runtime = temp.path().join("runtime");
    fs::create_dir(&source).unwrap();
    let output = run(
        &source,
        &runtime,
        "capture-subprocess",
        &[
            "--candidate",
            "result.json",
            "--",
            "sh",
            "-c",
            "printf output; printf diagnostic >&2; exit 3",
        ],
    );
    assert_eq!(output.status.code(), Some(3));
    assert_eq!(output.stderr, b"diagnostic");
    assert_eq!(fs::read(runtime.join("result.json")).unwrap(), b"output");
    let marker = temp.path().join("must-not-create");
    let script = format!("touch '{}'", marker.display());
    assert_eq!(
        run(
            &source,
            &runtime,
            "capture-subprocess",
            &["--candidate", "../escape", "--", "sh", "-c", &script]
        )
        .status
        .code(),
        Some(2)
    );
    assert!(!marker.exists());
}
