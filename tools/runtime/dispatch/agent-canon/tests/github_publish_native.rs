// @dependency-start
// contract test
// responsibility Checks native publication help and argument rejection before any Git/GitHub or filesystem mutation.
// upstream implementation ../src/github_publish.rs owns verified publication
// @dependency-end

#[test]
fn help_and_missing_authorizing_task_need_no_external_commands_or_writes() {
    let root = tempfile::tempdir_in(
        std::env::temp_dir()
            .canonicalize()
            .expect("canonical temporary parent"),
    )
    .expect("isolated caller root");
    for (arguments, code) in [
        (vec!["github-publish", "--help"], 0),
        (vec!["github-publish", "push"], 2),
    ] {
        let output = std::process::Command::new(env!("CARGO_BIN_EXE_agent-canon"))
            .args(arguments)
            .current_dir(root.path())
            .env("PATH", "")
            .output()
            .expect("native publication CLI");
        assert_eq!(
            output.status.code(),
            Some(code),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            std::fs::read_dir(root.path()).expect("caller root").count(),
            0
        );
    }
}
