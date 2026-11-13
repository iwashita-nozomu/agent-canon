//! Variant-scoped latest-result selection and locked JSON/Markdown publication.

use crate::experiment_identity::{
    identity_from_json, json_field, json_text, validate_segment, ExperimentIdentity,
};
use crate::path_resolution::resolve_non_strict;
use crate::python_json::{
    parse_json_bytes, parse_json_bytes_unique_keys, python_json_pretty_ascii_bytes,
};
use crate::source_mutation::{open_root_nofollow, SourceMutationCapability};
use cap_fs_ext::{DirExt, MetadataExt, OpenOptionsFollowExt};
use cap_primitives::fs::FollowSymlinks;
use cap_std::fs::{Dir, OpenOptions};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use time::{format_description::well_known::Iso8601, OffsetDateTime, PrimitiveDateTime};

struct LockedRoot {
    path: PathBuf,
    repository: PathBuf,
    topic: String,
    directory: Dir,
    lock: cap_std::fs::File,
}

impl LockedRoot {
    fn open(path: &Path) -> Result<Self, String> {
        let path = if path.is_absolute() {
            path.to_owned()
        } else {
            std::env::current_dir()
                .map_err(|error| error.to_string())?
                .join(path)
        };
        if path
            .components()
            .any(|part| matches!(part, Component::ParentDir))
        {
            return Err(
                "result-root must be experiments/<topic>/result without path traversal".into(),
            );
        }
        let topic_dir = path
            .parent()
            .ok_or("result-root must be experiments/<topic>/result (or its absolute path)")?;
        let experiments = topic_dir
            .parent()
            .ok_or("result-root must be experiments/<topic>/result (or its absolute path)")?;
        let repository = experiments
            .parent()
            .ok_or("result-root must be experiments/<topic>/result (or its absolute path)")?
            .to_owned();
        if path.file_name().is_none_or(|name| name != "result")
            || experiments
                .file_name()
                .is_none_or(|name| name != "experiments")
        {
            return Err(
                "result-root must be experiments/<topic>/result (or its absolute path)".into(),
            );
        }
        let topic = topic_dir
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("topic must be a non-empty string")?
            .to_owned();
        validate_segment(&topic, "topic")?;
        for ancestor in [
            &repository,
            &experiments.to_owned(),
            &topic_dir.to_owned(),
            &path,
        ] {
            let canonical = resolve_non_strict(ancestor)?;
            if canonical != *ancestor
                || fs::symlink_metadata(ancestor)
                    .is_ok_and(|metadata| metadata.file_type().is_symlink())
            {
                return Err(format!(
                    "result tree path must not use a symlinked ancestor: {}",
                    ancestor.display()
                ));
            }
        }
        let directory = open_root_nofollow(&path).map_err(|error| error.to_string())?;
        let lock = directory.open(".").map_err(|error| error.to_string())?;
        lock_directory(&lock)?;
        Ok(Self {
            path,
            repository,
            topic,
            directory,
            lock,
        })
    }

    fn relative(&self, path: &Path) -> Result<String, String> {
        let resolved = resolve_non_strict(path)?;
        resolved
            .strip_prefix(&self.repository)
            .map(|path| path.to_string_lossy().replace('\\', "/"))
            .map_err(|_| {
                format!(
                    "pointer path is outside repository root: {}",
                    path.display()
                )
            })
    }

    fn snapshot(&self, name: &str) -> Result<Option<Snapshot>, String> {
        match self.directory.symlink_metadata(name) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Ok(metadata) if metadata.is_file() && !metadata.is_symlink() => {}
            Ok(_) => {
                return Err(format!(
                    "latest pointer must be a regular file: {}",
                    self.path.join(name).display()
                ))
            }
            Err(error) => return Err(error.to_string()),
        }
        let mut options = OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No);
        let mut file = self
            .directory
            .open_with(name, &options)
            .map_err(|error| error.to_string())?;
        let metadata = file.metadata().map_err(|error| error.to_string())?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)
            .map_err(|error| error.to_string())?;
        Ok(Some(Snapshot {
            inode: MetadataExt::ino(&metadata),
            size: metadata.len(),
            digest: format!("{:x}", Sha256::digest(&bytes)),
            bytes,
        }))
    }

    fn generation(&self, names: &[String; 2]) -> Result<[Option<Snapshot>; 2], String> {
        Ok([self.snapshot(&names[0])?, self.snapshot(&names[1])?])
    }

    fn load_run(&self, path: &Path, variant: &str) -> Result<Option<Run>, String> {
        if fs::symlink_metadata(path).is_err() || path.is_symlink() || !path.is_dir() {
            return Err(format!(
                "result directory must be a real directory: {}",
                path.display()
            ));
        }
        if resolve_non_strict(path)? != path {
            return Err(format!(
                "result directory realpath differs: {}",
                path.display()
            ));
        }
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("run_name must be a non-empty string")?;
        let directory = self
            .directory
            .open_dir_nofollow(name)
            .map_err(|error| error.to_string())?;
        let candidates: Vec<_> = ["run_manifest.json", "result_manifest.json"]
            .into_iter()
            .filter(|name| directory.symlink_metadata(name).is_ok())
            .collect();
        if candidates.len() != 1 {
            return Err(format!(
                "exactly one run_manifest.json or result_manifest.json is required: {}",
                path.display()
            ));
        }
        let manifest = candidates[0];
        let metadata = directory
            .symlink_metadata(manifest)
            .map_err(|error| error.to_string())?;
        if !metadata.is_file() || metadata.is_symlink() {
            return Err(format!(
                "manifest must be a regular non-symlink file: {}",
                path.join(manifest).display()
            ));
        }
        let mut options = OpenOptions::new();
        options.read(true).follow(FollowSymlinks::No);
        let mut file = directory
            .open_with(manifest, &options)
            .map_err(|error| error.to_string())?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)
            .map_err(|error| error.to_string())?;
        let payload = parse_json_bytes_unique_keys(&bytes).map_err(|_| {
            format!(
                "manifest is not valid JSON: {}",
                path.join(manifest).display()
            )
        })?;
        let identity = identity_from_json(&payload)?;
        if identity.topic != self.topic || identity.variant != variant {
            return Ok(None);
        }
        if identity.run_name != name {
            return Err("result directory name does not match manifest run identity".into());
        }
        let value = json_field(&payload, "created_at_utc")
            .and_then(json_text)
            .ok_or_else(|| {
                format!(
                    "manifest must contain created_at_utc: {}",
                    path.join(manifest).display()
                )
            })?;
        let created = utc_timestamp(&value)?;
        Ok(Some(Run {
            identity,
            path: path.into(),
            manifest: path.join(manifest),
            created,
        }))
    }

    fn select(&self, variant: &str) -> Result<Run, String> {
        let mut selected: Option<Run> = None;
        let mut paths = fs::read_dir(&self.path)
            .map_err(|error| error.to_string())?
            .map(|entry| entry.map(|entry| entry.path()))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        paths.sort();
        for path in paths {
            let name = path
                .file_name()
                .and_then(|name| name.to_str())
                .ok_or("run_name must be a non-empty string")?;
            if name.starts_with("LATEST.") && (name.ends_with(".json") || name.ends_with(".md")) {
                continue;
            }
            if path.is_symlink() || !path.is_dir() {
                return Err(format!(
                    "result root contains a non-directory entry: {}",
                    path.display()
                ));
            }
            validate_segment(name, "run_name")?;
            if let Some(run) = self.load_run(&path, variant)? {
                if selected
                    .as_ref()
                    .is_none_or(|current| run.key() > current.key())
                {
                    selected = Some(run);
                }
            }
        }
        selected.ok_or_else(|| {
            format!(
                "no result directories for variant {variant:?} under {}",
                self.path.display()
            )
        })
    }

    fn payload(&self, run: &Run) -> Result<Value, String> {
        let summary = run.path.join("summary/summary.json");
        let visuals = [
            run.path.join("summary/visual_diagnostics/report.html"),
            run.path.join("summary/visual_diagnostics/index.html"),
            run.path.join("summary/report.html"),
        ];
        let visual = visuals.iter().find(|path| path.is_file());
        let mut payload = run.identity.to_value();
        let object = payload.as_object_mut().expect("identity object");
        object.insert("schema".into(), json!("agentcanon.experiment-latest/v2"));
        object.insert("result_root".into(), json!(self.relative(&self.path)?));
        object.insert("latest_result".into(), json!(self.relative(&run.path)?));
        object.insert("latest_result_name".into(), json!(run.identity.run_name));
        object.insert(
            "result_manifest".into(),
            json!(self.relative(&run.manifest)?),
        );
        object.insert(
            "summary_json".into(),
            if summary.is_file() {
                json!(self.relative(&summary)?)
            } else {
                Value::Null
            },
        );
        object.insert(
            "visual_report_html".into(),
            match visual {
                Some(path) => json!(self.relative(path)?),
                None => Value::Null,
            },
        );
        object.insert(
            "experiment_report".into(),
            json!(run.identity.report_relative_path().to_string_lossy()),
        );
        Ok(payload)
    }

    fn current(
        &self,
        names: &[String; 2],
        variant: &str,
    ) -> Result<Option<CurrentPointer>, String> {
        let generation = self.generation(names)?;
        let (Some(json), Some(markdown)) = (&generation[0], &generation[1]) else {
            if generation[0].is_some() || generation[1].is_some() {
                return Err(format!(
                    "{} and {} must be published together",
                    names[0], names[1]
                ));
            }
            return Ok(None);
        };
        let value = parse_json_bytes_unique_keys(&json.bytes)
            .map_err(|_| format!("{} is not valid strict JSON", names[0]))?;
        let payload = crate::python_json::to_serde_json_value(&value)?;
        if payload["schema"] != "agentcanon.experiment-latest/v2" {
            return Err(format!("{} has an unsupported schema", names[0]));
        }
        let identity = ExperimentIdentity::from_value(&payload)?;
        if identity.topic != self.topic || identity.variant != variant {
            return Err(format!(
                "{} identity does not match the selected variant",
                names[0]
            ));
        }
        let path = self.path.join(&identity.run_name);
        if payload["latest_result"] != self.relative(&path)?
            || payload["latest_result_name"] != identity.run_name
        {
            return Err(format!(
                "{} latest_result does not match its identity",
                names[0]
            ));
        }
        if markdown.bytes != latest_markdown(&payload)?.as_bytes() {
            return Err(format!(
                "{} and {} identities are inconsistent",
                names[0], names[1]
            ));
        }
        let run = self
            .load_run(&path, variant)?
            .ok_or("manifest identity does not match the selected result variant")?;
        Ok(Some(CurrentPointer { run, generation }))
    }

    fn publish(
        &self,
        names: &[String; 2],
        payload: &Value,
        generation: &[Option<Snapshot>; 2],
    ) -> Result<(), String> {
        let raw = json!({"allowed_paths":names,"purpose":"update-latest-result","authority":"explicit result-root and variant arguments"}).to_string();
        let capability = SourceMutationCapability::from_json(&self.path, Some(&raw))
            .map_err(|error| error.to_string())?;
        let parsed = parse_json_bytes(payload.to_string().as_bytes())?;
        let mut json = python_json_pretty_ascii_bytes(&parsed)?;
        json.push(b'\n');
        let text = String::from_utf8(json).expect("ASCII JSON");
        let markdown = latest_markdown(payload)?;
        self.publish_with(
            names,
            [&text, &markdown],
            generation,
            |index, text| {
                capability
                    .atomic_write_text(&self.path.join(&names[index]), text, 0o600)
                    .map_err(|error| error.to_string())
            },
            |old| {
                if let Some(old) = old {
                    capability
                        .atomic_write_text(
                            &self.path.join(&names[0]),
                            std::str::from_utf8(&old.bytes).map_err(|error| error.to_string())?,
                            0o600,
                        )
                        .map_err(|error| error.to_string())
                } else {
                    capability
                        .remove_file(&self.path.join(&names[0]))
                        .map_err(|error| error.to_string())
                }
            },
        )
    }

    fn publish_with(
        &self,
        names: &[String; 2],
        contents: [&str; 2],
        generation: &[Option<Snapshot>; 2],
        mut write: impl FnMut(usize, &str) -> Result<(), String>,
        restore: impl FnOnce(Option<&Snapshot>) -> Result<(), String>,
    ) -> Result<(), String> {
        if self.generation(names)? != *generation {
            return Err("LATEST pointer generation changed during selection".into());
        }
        write(0, contents[0])?;
        if let Err(error) = write(1, contents[1]) {
            restore(generation[0].as_ref())?;
            return Err(error);
        }
        Ok(())
    }
}

impl Drop for LockedRoot {
    fn drop(&mut self) {
        #[cfg(not(unix))]
        let _ = &self.lock;
        #[cfg(unix)]
        {
            let _ = rustix::fs::flock(&self.lock, rustix::fs::FlockOperation::Unlock);
        }
    }
}

fn lock_directory(directory: &cap_std::fs::File) -> Result<(), String> {
    #[cfg(unix)]
    {
        rustix::fs::flock(directory, rustix::fs::FlockOperation::LockExclusive)
            .map_err(|error| error.to_string())
    }
    #[cfg(not(unix))]
    {
        let _ = directory;
        Err("result-root directory locks require a Unix execution environment".into())
    }
}

#[derive(Clone, Eq, PartialEq)]
struct Snapshot {
    inode: u64,
    size: u64,
    digest: String,
    bytes: Vec<u8>,
}
struct Run {
    identity: ExperimentIdentity,
    path: PathBuf,
    manifest: PathBuf,
    created: OffsetDateTime,
}
struct CurrentPointer {
    run: Run,
    generation: [Option<Snapshot>; 2],
}
impl Run {
    fn key(&self) -> (OffsetDateTime, &str) {
        (self.created, &self.identity.run_name)
    }
}

fn utc_timestamp(value: &str) -> Result<OffsetDateTime, String> {
    let timestamp = match OffsetDateTime::parse(value, &Iso8601::PARSING) {
        Ok(value) => value,
        Err(_) if PrimitiveDateTime::parse(value, &Iso8601::PARSING).is_ok() => {
            return Err("manifest created_at_utc must be timezone-aware UTC".into())
        }
        Err(_) => return Err("manifest created_at_utc is not parseable".into()),
    };
    if !timestamp.offset().is_utc() {
        return Err("manifest created_at_utc must use UTC (+00:00 or Z)".into());
    }
    timestamp
        .replace_nanosecond(timestamp.nanosecond() / 1000 * 1000)
        .map_err(|error| error.to_string())
}

fn latest_markdown(payload: &Value) -> Result<String, String> {
    let identity = crate::python_json::parse_json(&payload["identity"].to_string())?;
    let identity = String::from_utf8(crate::python_json::canonical_json_ascii_bytes(&identity)?)
        .map_err(|error| error.to_string())?;
    let show = |key: &str| payload[key].as_str().unwrap_or("None");
    Ok(format!("# Latest Experiment Result\n\n- identity: `{identity}`\n- result: `{}`\n- manifest: `{}`\n- report: `{}`\n- summary: `{}`\n- visual report: `{}`\n", show("latest_result"), show("result_manifest"), show("experiment_report"), show("summary_json"), show("visual_report_html")))
}

pub fn select(result_root: &Path, variant: &str) -> Result<PathBuf, String> {
    validate_segment(variant, "variant")?;
    let root = LockedRoot::open(result_root)?;
    Ok(root.select(variant)?.path)
}

pub fn update(
    result_root: &Path,
    result_dir: Option<&Path>,
    variant: &str,
) -> Result<PathBuf, String> {
    validate_segment(variant, "variant")?;
    if let Some(path) = result_dir {
        if result_root.is_symlink() {
            return Err(format!(
                "result root must not be a symlink: {}",
                result_root.display()
            ));
        }
        if path.is_symlink() {
            return Err(format!(
                "result directory must not be a symlink: {}",
                path.display()
            ));
        }
        if resolve_non_strict(path)?.parent() != Some(resolve_non_strict(result_root)?.as_path()) {
            return Err("explicit result directory must be directly below result root".into());
        }
    }
    let root = LockedRoot::open(result_root)?;
    let names = [
        format!("LATEST.{variant}.json"),
        format!("LATEST.{variant}.md"),
    ];
    let generation = root.generation(&names)?;
    let run = match result_dir {
        Some(path) => {
            if resolve_non_strict(path)? != path {
                return Err(format!(
                    "result directory realpath differs: {}",
                    path.display()
                ));
            }
            root.load_run(path, variant)?
                .ok_or("manifest identity does not match the selected result variant")?
        }
        None => root.select(variant)?,
    };
    if let Some(current) = root.current(&names, variant)? {
        if current.generation != generation {
            return Err("LATEST pointer generation changed during selection".into());
        }
        if run.key() <= current.run.key() {
            return Ok(current.run.path);
        }
    }
    root.publish(&names, &root.payload(&run)?, &generation)?;
    Ok(run.path)
}

pub fn run(args: &[String]) -> i32 {
    let mut root = None;
    let mut result = None;
    let mut variant = None;
    let mut select_only = false;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--help" | "-h" => {
                println!("usage: agent-canon update-latest-result RESULT_ROOT --variant VARIANT [--result-dir PATH] [--select-only]");
                return 0;
            }
            "--select-only" => select_only = true,
            "--variant" | "--result-dir" => {
                let key = &args[index];
                index += 1;
                let Some(value) = args.get(index) else {
                    eprintln!("{key} requires a value");
                    return 2;
                };
                if key == "--variant" {
                    variant = Some(value.clone());
                } else {
                    result = Some(PathBuf::from(value));
                }
            }
            value if !value.starts_with('-') && root.is_none() => root = Some(PathBuf::from(value)),
            value => {
                eprintln!("unrecognized argument: {value}");
                return 2;
            }
        }
        index += 1;
    }
    let (Some(root), Some(variant)) = (root, variant) else {
        eprintln!("RESULT_ROOT and --variant are required");
        return 2;
    };
    match if select_only {
        select(&root, &variant)
    } else {
        update(&root, result.as_deref(), &variant)
    } {
        Ok(path) => {
            println!("latest_result_dir={}", path.display());
            0
        }
        Err(error) => {
            eprintln!("{error}");
            2
        }
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    #[test]
    fn second_pointer_failure_restores_first_and_leaves_no_temporary() {
        let temporary = tempfile::tempdir().expect("temporary root");
        let path = temporary.path().canonicalize().expect("canonical fixture root").join("experiments/demo/result");
        fs::create_dir_all(&path).expect("result root");
        let root = LockedRoot::open(&path).expect("locked root");
        let names = ["LATEST.smoke.json".to_owned(), "LATEST.smoke.md".to_owned()];
        let generation = root.generation(&names).expect("empty generation");
        let capability = SourceMutationCapability::from_json(
            &path,
            Some(
                &json!({"allowed_paths":names,"purpose":"regression","authority":"test"})
                    .to_string(),
            ),
        )
        .expect("exact capability");
        let error = root
            .publish_with(
                &names,
                ["{}", "markdown"],
                &generation,
                |index, text| {
                    if index == 1 {
                        Err("injected markdown publication failure".into())
                    } else {
                        capability
                            .atomic_write_text(&path.join(&names[0]), text, 0o600)
                            .map_err(|error| error.to_string())
                    }
                },
                |_| {
                    capability
                        .remove_file(&path.join(&names[0]))
                        .map_err(|error| error.to_string())
                },
            )
            .expect_err("second write fails");
        assert!(error.contains("injected markdown"));
        assert_eq!(fs::read_dir(&path).expect("result entries").count(), 0);
    }
}
