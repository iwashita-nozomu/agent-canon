// @dependency-start
// contract test
// responsibility Checks standalone formatting without Docker or document providers.
// upstream implementation ../src/docs.rs owns Markdown normalization and explicit checks
// @dependency-end

use std::fs;
use std::process::Command;

#[test]
fn format_normalizes_selected_file_with_no_external_commands() {
    let root = tempfile::tempdir().unwrap();
    let selected = root.path().join("selected.md");
    let untouched = root.path().join("untouched.md");
    fs::write(&selected, "# Title  \r\n\r\n\r\n\r\n### Detail\r\n").unwrap();
    fs::write(&untouched, "# Unchanged  \r\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_agent-canon"))
        .args(["docs", "format", "--root"])
        .arg(root.path())
        .arg("selected.md")
        .env("PATH", "")
        .output()
        .unwrap();
    assert!(output.status.success(), "{output:?}");
    assert_eq!(
        fs::read_to_string(selected).unwrap(),
        "# Title\n\n\n### Detail\n"
    );
    assert_eq!(fs::read(untouched).unwrap(), b"# Unchanged  \r\n");
    assert!(output.stderr.is_empty(), "{output:?}");
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
