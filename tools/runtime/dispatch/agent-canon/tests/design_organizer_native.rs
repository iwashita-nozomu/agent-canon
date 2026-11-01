// @dependency-start
// contract test
// responsibility Runs the native design organizer against the frozen CPython CLI oracle and explicit mutation contract.
// upstream implementation ../src/docs.rs owns native organizer planning, reporting, and CLI routing
// upstream implementation ../src/source_mutation.rs owns capability-bound organizer copies
// upstream evidence ../../../../../tests/fixtures/design_organizer/python_golden.json freezes old CLI outcomes and input metadata
// upstream implementation ../src/runtime_boundary.rs owns external report admission
// @dependency-end

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const PYTHON_GOLDEN: &str =
    include_str!("../../../../../tests/fixtures/design_organizer/python_golden.json");
const PYTHON_GOLDEN_SHA256: &str =
    "fbd4936a00231d5199442aee8fe6c16e05be45a722bd2bbc227d6dfd10cec5e8";

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock is after epoch")
            .as_nanos();
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "agent-canon-design-organizer-{}-{sequence}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("temporary organizer root is created");
        Self(path.canonicalize().expect("temporary root is canonical"))
    }

    fn source(&self) -> PathBuf {
        self.0.join("source")
    }

    fn support(&self) -> PathBuf {
        self.0.join("support")
    }

    fn runtime(&self) -> PathBuf {
        self.0.join("runtime")
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[derive(Debug)]
enum FixtureSetupError {
    Io(io::Error),
    SymlinkUnavailable(io::Error),
}

impl From<io::Error> for FixtureSetupError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

#[test]
fn native_organizer_cli_matches_frozen_python_oracle() {
    assert_eq!(
        format!("{:x}", Sha256::digest(PYTHON_GOLDEN.as_bytes())),
        PYTHON_GOLDEN_SHA256,
        "the actual CPython fixture bytes are immutable"
    );
    let golden: Value = serde_json::from_str(PYTHON_GOLDEN).expect("frozen oracle parses");
    let cases = golden["cases"].as_array().expect("oracle has cases");
    assert_eq!(cases.len(), 9, "the old CLI corpus has nine cases");

    let mut executed = 0;
    for case in cases {
        if run_oracle_case(case) {
            executed += 1;
        }
    }
    assert!(
        executed >= 6,
        "the host must execute the portable planner, capability, and runtime cases"
    );
}

fn run_oracle_case(case: &Value) -> bool {
    let name = case["name"].as_str().expect("case has a name");
    let temp = TempRoot::new();
    let source = temp.source();
    fs::create_dir_all(&source).expect("test source root is created");
    let old_source = case["cwd"].as_str().expect("case has source root");
    let old_case_root = old_source
        .rsplit_once('/')
        .map(|(parent, _)| parent)
        .expect("old source root has parent");

    let mut metadata_setup_complete = true;
    if let Err(error) = materialize_tree(
        &case["support_before"],
        &temp.support(),
        old_case_root,
        &temp.0,
        &mut metadata_setup_complete,
    )
    .and_then(|()| {
        materialize_tree(
            &case["source_before"],
            &source,
            old_case_root,
            &temp.0,
            &mut metadata_setup_complete,
        )
    }) {
        match error {
            FixtureSetupError::SymlinkUnavailable(error) => {
                eprintln!("{name}: symlink premise unavailable on this host: {error}");
                return false;
            }
            FixtureSetupError::Io(error) => panic!("{name}: fixture setup failed: {error}"),
        }
    }

    let before = content_snapshot(&source);
    let runtime = temp.runtime();
    let output = run_native(&source, &runtime, case);
    if output.status.success() {
        // Check copystat timestamps before the independent content oracle reads
        // the files and can itself advance their access times.
        assert_successful_copy_metadata(case, &source, metadata_setup_complete);
    }
    let actual_report_path = report_path(&output);
    if case["legacy_discrepancy_only"].as_bool().unwrap_or(false)
        || is_existing_target_symlink_case(name)
    {
        // The accepted native SourceMutationCapability rejects lexical target
        // symlinks. The old internal-target-link acceptance is recorded as a
        // discrepancy only and is not required of the native route.
        assert_eq!(output.status.code(), Some(2), "{name}: no-follow grant");
        assert!(
            output.stdout.is_empty(),
            "{name}: denied apply has no report stdout"
        );
        assert!(
            String::from_utf8_lossy(&output.stderr).contains("symlink"),
            "{name}: denial explains the native no-follow boundary"
        );
        assert!(
            actual_report_path.is_none(),
            "{name}: denied symlink target has no report path"
        );
        assert_eq!(
            content_snapshot(&source),
            before,
            "{name}: source remains unchanged"
        );
        return true;
    }

    assert_eq!(
        output.status.code(),
        Some(case["exit"].as_i64().expect("case exit code") as i32),
        "{name}: exit status\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert_source_tree_matches_oracle(case, &source, &temp);

    let mapped_stdout = map_oracle_paths(
        case,
        case["stdout_utf8"].as_str().expect("old stdout is text"),
        &temp,
        &source,
        actual_report_path.as_deref(),
    );
    let mapped_stderr = map_oracle_paths(
        case,
        case["stderr_utf8"].as_str().expect("old stderr is text"),
        &temp,
        &source,
        actual_report_path.as_deref(),
    );
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        mapped_stdout,
        "{name}: stdout"
    );
    assert_eq!(
        String::from_utf8_lossy(&output.stderr),
        mapped_stderr,
        "{name}: stderr"
    );

    match case["report"].as_object() {
        Some(old_report) => {
            let report_path = actual_report_path.expect("successful CLI reports its output");
            if case["name"] == "default-planning" {
                assert_default_report_path(&report_path, &runtime);
            } else {
                assert_eq!(
                    report_path,
                    runtime.join("report.txt"),
                    "{name}: explicit output"
                );
            }
            let expected = map_oracle_paths(
                case,
                old_report["content_utf8"]
                    .as_str()
                    .expect("old report is text"),
                &temp,
                &source,
                Some(&report_path),
            );
            assert_eq!(
                fs::read(&report_path).expect("native report is written"),
                expected.as_bytes(),
                "{name}: report bytes"
            );
        }
        None => {
            assert!(
                actual_report_path.is_none(),
                "{name}: failed CLI does not report an output path"
            );
        }
    }

    true
}

fn run_native(source: &Path, runtime: &Path, case: &Value) -> Output {
    let old_argv = case["argv"].as_array().expect("old argv is an array");
    assert!(
        old_argv.len() >= 2,
        "old argv includes interpreter and script"
    );
    let mut arguments = vec!["docs".to_string(), "organize-designs".to_string()];
    let mut index = 2;
    while index < old_argv.len() {
        let argument = old_argv[index].as_str().expect("old argv item is text");
        if argument == "--runtime-root" {
            arguments.push(argument.to_string());
            arguments.push(runtime.display().to_string());
            index += 2;
        } else {
            arguments.push(argument.to_string());
            index += 1;
        }
    }
    let mut command = Command::new(env!("CARGO_BIN_EXE_agent-canon"));
    command
        .args(arguments)
        .current_dir(source)
        .env_remove("AGENT_CANON_RUNTIME_ROOT")
        .env("PYTHONDONTWRITEBYTECODE", "1");
    command.output().expect("native organizer CLI starts")
}

fn report_path(output: &Output) -> Option<PathBuf> {
    let stdout = String::from_utf8_lossy(&output.stdout);
    let path = stdout.strip_prefix("Report written to ")?;
    Some(PathBuf::from(path.trim()))
}

fn assert_default_report_path(path: &Path, runtime: &Path) {
    let relative = path
        .strip_prefix(runtime)
        .expect("default report is beneath the external runtime");
    let components = relative.components().collect::<Vec<_>>();
    assert_eq!(
        components.len(),
        4,
        "default report has task/category/run/file path"
    );
    assert_eq!(components[0].as_os_str(), "tasks");
    assert_eq!(components[1].as_os_str(), "design-organization");
    let run_name = components[2].as_os_str().to_string_lossy().to_string();
    assert!(run_name.starts_with("run-"));
    assert_eq!(
        components[3].as_os_str().to_str(),
        Some("design_organize_report.txt")
    );
}

fn is_existing_target_symlink_case(name: &str) -> bool {
    name == "existing-target-symlink-outside-source"
        || name == "source-symlink-with-existing-target-symlink"
}

fn map_oracle_paths(
    case: &Value,
    text: &str,
    temp: &TempRoot,
    source: &Path,
    report: Option<&Path>,
) -> String {
    let old_source = case["cwd"].as_str().expect("old source root");
    let old_case_root = old_source
        .rsplit_once('/')
        .map(|(parent, _)| parent)
        .expect("case root has source directory");
    let mut replacements = Vec::<(String, String)>::new();
    add_tree_replacements(
        &mut replacements,
        &case["source_before"],
        old_source,
        source,
    );
    add_tree_replacements(&mut replacements, &case["source_after"], old_source, source);
    add_tree_replacements(
        &mut replacements,
        &case["support_before"],
        &format!("{old_case_root}/support"),
        &temp.support(),
    );
    add_tree_replacements(
        &mut replacements,
        &case["support_after"],
        &format!("{old_case_root}/support"),
        &temp.support(),
    );
    if let (Some(old_report), Some(report)) = (case["report"]["path"].as_str(), report) {
        replacements.push((old_report.to_string(), report.display().to_string()));
    }
    replacements.sort_by_key(|replacement| std::cmp::Reverse(replacement.0.len()));
    let mut mapped = text.to_owned();
    for (old, new) in replacements {
        mapped = mapped.replace(&old, &new);
    }
    mapped
}

fn add_tree_replacements(
    replacements: &mut Vec<(String, String)>,
    tree: &Value,
    old_root: &str,
    new_root: &Path,
) {
    let Some(entries) = tree["entries"].as_object() else {
        return;
    };
    for relative in entries.keys().filter(|relative| relative.as_str() != ".") {
        replacements.push((
            format!("{old_root}/{relative}"),
            new_root.join(relative).display().to_string(),
        ));
    }
}

fn content_snapshot(root: &Path) -> BTreeMap<PathBuf, String> {
    let mut entries = BTreeMap::new();
    collect_content_snapshot(root, root, &mut entries);
    entries
}

fn collect_content_snapshot(root: &Path, current: &Path, entries: &mut BTreeMap<PathBuf, String>) {
    for entry in fs::read_dir(current).expect("source tree remains readable") {
        let entry = entry.expect("source entry remains readable");
        let path = entry.path();
        let relative = path
            .strip_prefix(root)
            .expect("source entry is beneath root")
            .to_path_buf();
        let kind = entry.file_type().expect("source type remains readable");
        if kind.is_dir() {
            entries.insert(relative, "directory".to_string());
            collect_content_snapshot(root, &path, entries);
        } else if kind.is_symlink() {
            entries.insert(
                relative,
                format!(
                    "symlink:{}",
                    fs::read_link(&path).expect("link text exists").display()
                ),
            );
        } else if kind.is_file() {
            let bytes = fs::read(&path).expect("source bytes remain readable");
            entries.insert(relative, format!("file:{}", STANDARD.encode(bytes)));
        } else {
            entries.insert(relative, "other".to_string());
        }
    }
}

fn assert_source_tree_matches_oracle(case: &Value, source: &Path, temp: &TempRoot) {
    let source_after = &case["source_after"];
    let actual = content_snapshot(source);
    let mut expected = BTreeMap::new();
    let old_source = case["cwd"].as_str().expect("oracle source root");
    let old_case_root = old_source
        .rsplit_once('/')
        .map(|(parent, _)| parent)
        .expect("oracle case root");
    let entries = source_after["entries"]
        .as_object()
        .expect("source_after entries are captured");
    for (relative, entry) in entries {
        if relative == "." {
            continue;
        }
        let path = PathBuf::from(relative);
        let content = match entry["kind"].as_str().expect("entry kind") {
            "directory" => "directory".to_string(),
            "file" => {
                let bytes = STANDARD
                    .decode(
                        entry["content_base64"]
                            .as_str()
                            .expect("old file content is base64"),
                    )
                    .expect("old file content decodes");
                format!("file:{}", STANDARD.encode(bytes))
            }
            "symlink" => {
                let old_text = entry["link_text"].as_str().expect("old link text");
                let new_text = remap_case_path(old_text, old_case_root, &temp.0);
                let actual_link = fs::read_link(source.join(relative))
                    .expect("expected source symlink exists after native operation");
                assert_eq!(
                    actual_link,
                    PathBuf::from(new_text),
                    "{}: link text",
                    case["name"]
                );
                "symlink".to_string()
            }
            other => panic!("unsupported source tree entry kind {other}"),
        };
        assert!(expected.insert(path, content).is_none());
    }
    let actual_kinds_and_contents = actual
        .into_iter()
        .map(|(path, content)| {
            let content = if content.starts_with("symlink:") {
                "symlink".to_string()
            } else {
                content
            };
            (path, content)
        })
        .collect::<BTreeMap<_, _>>();
    assert_eq!(
        actual_kinds_and_contents, expected,
        "{}: source tree contents",
        case["name"]
    );
}

fn assert_successful_copy_metadata(case: &Value, source: &Path, metadata_setup_complete: bool) {
    let name = case["name"].as_str().expect("oracle case name");
    if name == "regular-target-overwrite-and-metadata" {
        let source_path = source.join("documents/design/a.md");
        let target_path = source.join("documents/design/foo/a.md");
        let source_metadata = fs::metadata(&source_path).expect("copy source metadata");
        let target_metadata = fs::metadata(&target_path).expect("copied target metadata");

        assert_eq!(
            source_metadata.modified().unwrap(),
            target_metadata.modified().unwrap(),
            "regular overwrite copies mtime"
        );
        assert_eq!(
            source_metadata.accessed().unwrap(),
            target_metadata.accessed().unwrap(),
            "regular overwrite copies atime"
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                source_metadata.permissions().mode() & 0o7777,
                target_metadata.permissions().mode() & 0o7777,
                "regular overwrite copies mode"
            );
        }
        #[cfg(windows)]
        assert_eq!(
            source_metadata.permissions().readonly(),
            target_metadata.permissions().readonly(),
            "regular overwrite copies readonly state"
        );

        if metadata_setup_complete {
            #[cfg(unix)]
            {
                let source_attrs = read_xattrs(&source_path);
                let target_attrs = read_xattrs(&target_path);
                assert_eq!(
                    source_attrs.get("user.agentcanon.organizer.shared"),
                    target_attrs.get("user.agentcanon.organizer.shared"),
                    "regular overwrite copies source xattr"
                );
                let target_only_value = b"preserve-target-only".to_vec();
                assert_eq!(
                    target_attrs.get("user.agentcanon.organizer.target-only"),
                    Some(&target_only_value),
                    "regular overwrite preserves target-only xattr"
                );
            }
        }
    } else if name == "source-file-symlink-copy" {
        let source_path = source.join("documents/design/a.md");
        let target_path = source.join("documents/design/foo/a.md");
        assert_eq!(
            fs::read_link(&source_path).expect("source link text"),
            fs::read_link(&target_path).expect("copied link text"),
            "source symlink copy preserves the link text"
        );
        let source_metadata = fs::symlink_metadata(&source_path).expect("source link metadata");
        let target_metadata = fs::symlink_metadata(&target_path).expect("target link metadata");
        assert_eq!(
            source_metadata.modified().unwrap(),
            target_metadata.modified().unwrap(),
            "source symlink copy preserves mtime"
        );
    }
}

#[cfg(unix)]
fn read_xattrs(path: &Path) -> BTreeMap<String, Vec<u8>> {
    use rustix::fs::{fgetxattr, fgetxattr_query, flistxattr, flistxattr_query};
    use std::os::unix::ffi::OsStrExt;

    let file = fs::File::open(path).expect("fixture xattr file opens");
    let length = flistxattr_query(&file).expect("fixture xattr names are available");
    let mut names = vec![0; length];
    let written = flistxattr(&file, &mut names).expect("fixture xattr names are read");
    names.truncate(written);
    let mut values = BTreeMap::new();
    for name in names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let name = std::ffi::OsStr::from_bytes(name);
        let length = fgetxattr_query(&file, name).expect("fixture xattr length is available");
        let mut value = vec![0; length];
        let written = fgetxattr(&file, name, &mut value).expect("fixture xattr value is read");
        value.truncate(written);
        values.insert(name.to_string_lossy().into_owned(), value);
    }
    values
}

fn materialize_tree(
    tree: &Value,
    destination: &Path,
    old_case_root: &str,
    new_case_root: &Path,
    metadata_setup_complete: &mut bool,
) -> Result<(), FixtureSetupError> {
    if !tree["exists"].as_bool().unwrap_or(false) {
        return Ok(());
    }
    fs::create_dir_all(destination)?;
    let entries = tree["entries"]
        .as_object()
        .expect("frozen tree entries are an object");
    let mut paths = entries.iter().collect::<Vec<_>>();
    paths.sort_by_key(|(relative, _)| relative.matches('/').count());
    for (relative, state) in &paths {
        if *relative == "." || state["kind"] != "directory" {
            continue;
        }
        fs::create_dir_all(destination.join(relative))?;
    }
    for (relative, state) in &paths {
        if *relative == "." || state["kind"] != "file" {
            continue;
        }
        let path = destination.join(relative);
        let bytes = STANDARD
            .decode(
                state["content_base64"]
                    .as_str()
                    .expect("old regular file bytes are base64"),
            )
            .expect("old file bytes decode");
        fs::create_dir_all(path.parent().expect("fixture file has parent"))?;
        fs::write(&path, bytes)?;
        seed_file_metadata(&path, state, metadata_setup_complete)?;
    }
    for (relative, state) in &paths {
        if *relative == "." || state["kind"] != "symlink" {
            continue;
        }
        let path = destination.join(relative);
        fs::create_dir_all(path.parent().expect("fixture link has parent"))?;
        let old_link = state["link_text"]
            .as_str()
            .expect("old symlink text is text");
        let link_text = remap_case_path(old_link, old_case_root, new_case_root);
        create_fixture_symlink(&link_text, &path)?;
        seed_symlink_metadata(&path, state, metadata_setup_complete)?;
    }
    Ok(())
}

fn seed_file_metadata(
    path: &Path,
    state: &Value,
    metadata_setup_complete: &mut bool,
) -> Result<(), FixtureSetupError> {
    if let Some(mode) = state["mode_octal"].as_str().and_then(parse_octal) {
        set_mode(path, mode)?;
    }
    if let (Some(atime), Some(mtime)) = (state["atime_ns"].as_i64(), state["mtime_ns"].as_i64()) {
        set_file_times(path, atime, mtime)?;
    }
    let xattrs = &state["xattrs"];
    if xattrs["status"] == "captured" {
        if let Some(values) = xattrs["values"].as_object() {
            for (name, value) in values {
                if let Some(value) = value["base64"].as_str() {
                    let bytes = STANDARD.decode(value).expect("old xattr bytes decode");
                    if let Err(error) = set_fixture_xattr(path, name, &bytes) {
                        *metadata_setup_complete = false;
                        if !is_xattr_setup_unsupported(&error) {
                            return Err(FixtureSetupError::Io(error));
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn seed_symlink_metadata(
    path: &Path,
    state: &Value,
    metadata_setup_complete: &mut bool,
) -> Result<(), FixtureSetupError> {
    if let (Some(atime), Some(mtime)) = (state["atime_ns"].as_i64(), state["mtime_ns"].as_i64()) {
        if let Err(error) = set_symlink_times(path, atime, mtime) {
            *metadata_setup_complete = false;
            if !is_link_metadata_setup_unsupported(&error) {
                return Err(FixtureSetupError::Io(error));
            }
        }
    }
    Ok(())
}

fn parse_octal(value: &str) -> Option<u32> {
    u32::from_str_radix(value.strip_prefix("0o")?, 8).ok()
}

fn file_time_from_unix_ns(nanoseconds: i64) -> Result<SystemTime, FixtureSetupError> {
    let seconds = nanoseconds.unsigned_abs() / 1_000_000_000;
    let subsecond = (nanoseconds.unsigned_abs() % 1_000_000_000) as u32;
    let duration = Duration::new(seconds, subsecond);
    let time = if nanoseconds < 0 {
        UNIX_EPOCH.checked_sub(duration)
    } else {
        UNIX_EPOCH.checked_add(duration)
    };
    time.ok_or_else(|| FixtureSetupError::Io(io::Error::other("fixture time is out of range")))
}

fn set_file_times(path: &Path, atime_ns: i64, mtime_ns: i64) -> Result<(), FixtureSetupError> {
    let file = fs::OpenOptions::new().write(true).open(path)?;
    let times = fs::FileTimes::new()
        .set_accessed(file_time_from_unix_ns(atime_ns)?)
        .set_modified(file_time_from_unix_ns(mtime_ns)?);
    file.set_times(times)?;
    Ok(())
}

fn set_mode(path: &Path, mode: u32) -> Result<(), FixtureSetupError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
    }
    #[cfg(windows)]
    {
        let mut permissions = fs::metadata(path)?.permissions();
        permissions.set_readonly(mode & 0o200 == 0);
        fs::set_permissions(path, permissions)?;
    }
    Ok(())
}

#[cfg(unix)]
fn set_fixture_xattr(path: &Path, name: &str, value: &[u8]) -> io::Result<()> {
    use rustix::fs::{fsetxattr, XattrFlags};
    let file = fs::OpenOptions::new().read(true).write(true).open(path)?;
    fsetxattr(&file, name, value, XattrFlags::empty()).map_err(io::Error::from)
}

#[cfg(windows)]
fn set_fixture_xattr(_path: &Path, _name: &str, _value: &[u8]) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "Windows has no os xattr API",
    ))
}

#[cfg(unix)]
fn is_xattr_setup_unsupported(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::Unsupported || error.kind() == io::ErrorKind::PermissionDenied
}

#[cfg(windows)]
fn is_xattr_setup_unsupported(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::Unsupported
}

#[cfg(unix)]
fn set_symlink_times(path: &Path, atime_ns: i64, mtime_ns: i64) -> io::Result<()> {
    use cap_fs_ext::DirExt;
    let directory = path.parent().expect("link has parent");
    let name = path.file_name().expect("link has name");
    let directory = cap_std::fs::Dir::open_ambient_dir(directory, cap_std::ambient_authority())?;
    directory.set_symlink_times(
        name,
        Some(cap_fs_ext::SystemTimeSpec::from(
            cap_std::time::SystemTime::from_std(file_time_from_unix_ns(atime_ns).map_err(
                |error| match error {
                    FixtureSetupError::Io(error) => error,
                    FixtureSetupError::SymlinkUnavailable(error) => error,
                },
            )?),
        )),
        Some(cap_fs_ext::SystemTimeSpec::from(
            cap_std::time::SystemTime::from_std(file_time_from_unix_ns(mtime_ns).map_err(
                |error| match error {
                    FixtureSetupError::Io(error) => error,
                    FixtureSetupError::SymlinkUnavailable(error) => error,
                },
            )?),
        )),
    )
}

#[cfg(windows)]
fn set_symlink_times(_path: &Path, _atime_ns: i64, _mtime_ns: i64) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "Windows symlink timestamps are unavailable in this fixture setup",
    ))
}

#[cfg(unix)]
fn is_link_metadata_setup_unsupported(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::Unsupported
}

#[cfg(windows)]
fn is_link_metadata_setup_unsupported(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::Unsupported || error.kind() == io::ErrorKind::PermissionDenied
}

fn create_fixture_symlink(target: &str, link: &Path) -> Result<(), FixtureSetupError> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;
        symlink(target, link).map_err(|error| {
            if is_link_setup_unsupported(&error) {
                FixtureSetupError::SymlinkUnavailable(error)
            } else {
                FixtureSetupError::Io(error)
            }
        })
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::symlink_file;
        symlink_file(target, link).map_err(|error| {
            if is_link_setup_unsupported(&error) {
                FixtureSetupError::SymlinkUnavailable(error)
            } else {
                FixtureSetupError::Io(error)
            }
        })
    }
}

#[cfg(unix)]
fn is_link_setup_unsupported(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::Unsupported || error.kind() == io::ErrorKind::PermissionDenied
}

#[cfg(windows)]
fn is_link_setup_unsupported(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::Unsupported || error.kind() == io::ErrorKind::PermissionDenied
}

fn remap_case_path(value: &str, old_case_root: &str, new_case_root: &Path) -> String {
    let old_prefix = format!("{old_case_root}/");
    value
        .strip_prefix(&old_prefix)
        .map(|suffix| new_case_root.join(suffix).display().to_string())
        .unwrap_or_else(|| value.to_string())
}
