// @dependency-start
// contract test
// responsibility Checks documentation CLI failures without changing source files.
// upstream implementation ../src/docs.rs dispatches Markdown checks
// @dependency-end

use std::fs;
use std::process::Command;

#[test]
fn retired_format_command_preserves_source() {
    let root = tempfile::tempdir().unwrap();
    let selected = root.path().join("selected.md");
    let source = b"# Title\r\n\r\nFirst line  \r\nNext line \r\n";
    fs::write(&selected, source).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["docs", "format", "--root"])
        .arg(root.path())
        .arg("selected.md")
        .env("PATH", "")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2), "{output:?}");
    assert!(String::from_utf8_lossy(&output.stderr).contains("unknown docs command format"));
    assert_eq!(fs::read(selected).unwrap(), source);
}

#[test]
fn explicit_check_still_reports_missing_providers() {
    let root = tempfile::tempdir().unwrap();
    let selected = root.path().join("selected.md");
    fs::write(&selected, "# Title\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["docs", "check", "--root"])
        .arg(root.path())
        .arg("selected.md")
        .env("PATH", "")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1), "{output:?}");
    assert!(String::from_utf8_lossy(&output.stderr).contains("markdownlint-cli2"));
    assert_eq!(fs::read_to_string(selected).unwrap(), "# Title\n");
}
