// @dependency-start
// contract test
// responsibility Checks the native read-only Skill shim renderer against independent fixed-point and drift fixtures.
// upstream implementation ../src/catalog/skill_materialization.rs owns v3 projection reconstruction and readback
// upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md defines the fixed-point contract
// upstream test ../../../../../tests/fixtures/skill_frontmatter contains independent canonical and projection bytes
// @dependency-end

use agent_canon::catalog::skill_materialization;
use std::fs;
use std::path::{Path, PathBuf};

const FIXTURE_RELATIVE: &str = "tests/fixtures/skill_frontmatter";
const SHIM_RELATIVE: &str = ".codex/personal/skills/fixture-skill/SKILL.md";

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(4)
        .expect("crate is nested under the repository root")
        .to_path_buf()
}

fn fixture_root() -> PathBuf {
    repository_root().join(FIXTURE_RELATIVE)
}

fn copy_tree(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).expect("create fixture copy directory");
    for entry in fs::read_dir(source).expect("read fixture directory") {
        let entry = entry.expect("read fixture entry");
        let source_path = entry.path();
        let destination_path = destination.join(entry.file_name());
        if entry.file_type().expect("read fixture entry type").is_dir() {
            copy_tree(&source_path, &destination_path);
        } else {
            fs::copy(source_path, destination_path).expect("copy fixture file");
        }
    }
}

#[test]
fn v3_projection_matches_the_independent_fixture_bytes() {
    let check = skill_materialization::check(&fixture_root()).expect("check fixture projection");
    assert!(check.content_delta_paths.is_empty());
}

#[test]
fn readback_reports_only_the_changed_catalog_projection_path() {
    let temp = tempfile::tempdir().expect("create temporary fixture root");
    copy_tree(&fixture_root(), temp.path());
    let shim = temp.path().join(SHIM_RELATIVE);
    fs::write(&shim, "deliberate projection drift\n").expect("change copied projection");

    let check = skill_materialization::check(temp.path()).expect("check changed fixture");
    assert_eq!(
        check.content_delta_paths,
        [SHIM_RELATIVE.to_owned()].into_iter().collect::<Vec<_>>()
    );
}

#[test]
fn readback_reports_a_missing_catalog_projection_path() {
    let temp = tempfile::tempdir().expect("create temporary fixture root");
    copy_tree(&fixture_root(), temp.path());
    fs::remove_file(temp.path().join(SHIM_RELATIVE)).expect("remove copied projection");

    let check = skill_materialization::check(temp.path()).expect("check missing projection");
    assert_eq!(
        check.content_delta_paths,
        [SHIM_RELATIVE.to_owned()].into_iter().collect::<Vec<_>>()
    );
}

#[test]
fn owner_source_changes_invalidate_the_projection_record() {
    let temp = tempfile::tempdir().expect("create temporary fixture root");
    copy_tree(&fixture_root(), temp.path());
    fs::write(
        temp.path().join("agents/skills/fixture-skill.md"),
        "changed canonical source\n",
    )
    .expect("change copied canonical owner");

    let check = skill_materialization::check(temp.path()).expect("check changed owner");
    assert_eq!(
        check.content_delta_paths,
        [SHIM_RELATIVE.to_owned()].into_iter().collect::<Vec<_>>()
    );
}
