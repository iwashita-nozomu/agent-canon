// @dependency-start
// contract test
// responsibility Checks missing Markdown providers without changing source files.
// upstream implementation ../src/docs.rs dispatches Markdown formatting and checks
// @dependency-end

use std::fs;
use std::process::Command;

#[test]
fn format_reports_missing_formatter_without_rewriting_source() {
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
    assert_eq!(output.status.code(), Some(1), "{output:?}");
    assert!(String::from_utf8_lossy(&output.stderr).contains("markdownlint-cli2"));
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
