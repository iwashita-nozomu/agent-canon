// @dependency-start
// contract implementation
// responsibility Resolves canonical eval manifests and legacy aliases for native Eval producers.
// upstream design ../../../../../eval/README.md owns evidence-directory placement
// upstream design ../../../../../eval/definitions/README.md owns canonical manifest sources
// downstream implementation run_evaluation.rs resolves behavior evaluation manifests
// @dependency-end

use std::panic::Location;
use std::path::{Path, PathBuf};

const CANONICAL_ROOT: &str = "eval/definitions";
const LEGACY_ROOT: &str = "agents/evals";
const LEGACY_RESULTS_ROOT: &str = "agents/evals/results";

pub fn eval_manifest_path(filename: &str) -> PathBuf {
    Path::new(CANONICAL_ROOT).join(filename)
}

pub fn is_legacy_manifest_path(path: &Path) -> bool {
    if path.is_absolute() {
        return false;
    }
    let normalized = PathBuf::from(path.as_os_str());
    normalized.starts_with(LEGACY_ROOT) && !normalized.starts_with(LEGACY_RESULTS_ROOT)
}

pub fn legacy_to_canonical_manifest(path: &Path) -> Option<PathBuf> {
    if !is_legacy_manifest_path(path) {
        return None;
    }
    let tail = path.strip_prefix(LEGACY_ROOT).ok()?;
    Some(Path::new(CANONICAL_ROOT).join(tail))
}

#[track_caller]
fn warn_legacy_manifest_path(old_path: &Path, new_path: &Path) {
    let location = Location::caller();
    let file = Path::new(location.file())
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or(location.file());
    eprintln!(
        "EVAL_MANIFEST_FORWARDER=deprecated EVAL_MANIFEST_FORWARDER_SEVERITY=fix-now old={} new={} caller_site={file}:{}",
        old_path.display(),
        new_path.display(),
        location.line()
    );
}

#[track_caller]
pub fn resolve_eval_manifest(root: &Path, value: impl AsRef<Path>) -> PathBuf {
    let raw = value.as_ref();
    if raw.is_absolute() {
        let Ok(relative) = raw.strip_prefix(root) else {
            return raw.to_path_buf();
        };
        if let Some(canonical) = legacy_to_canonical_manifest(relative) {
            warn_legacy_manifest_path(relative, &canonical);
            return root.join(canonical);
        }
        return raw.to_path_buf();
    }
    if let Some(canonical) = legacy_to_canonical_manifest(raw) {
        warn_legacy_manifest_path(raw, &canonical);
        return root.join(canonical);
    }
    root.join(raw)
}

pub fn relative_manifest_path(root: &Path, path: &Path) -> PathBuf {
    path.strip_prefix(root)
        .map(Path::to_path_buf)
        .unwrap_or_else(|_| path.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_path_is_repo_relative() {
        assert_eq!(
            eval_manifest_path("agent_behavior_eval.toml"),
            PathBuf::from("eval/definitions/agent_behavior_eval.toml")
        );
    }

    #[test]
    fn legacy_sources_resolve_but_result_history_does_not() {
        assert!(is_legacy_manifest_path(Path::new("agents/evals/old.toml")));
        assert!(!is_legacy_manifest_path(Path::new(
            "agents/evals/results/old.json"
        )));
        assert!(!is_legacy_manifest_path(Path::new(
            "/tmp/agents/evals/old.toml"
        )));
        assert_eq!(
            legacy_to_canonical_manifest(Path::new("agents/evals/old.toml")),
            Some(PathBuf::from("eval/definitions/old.toml"))
        );
        assert_eq!(
            resolve_eval_manifest(Path::new("/repo"), "eval/definitions/old.toml"),
            PathBuf::from("/repo/eval/definitions/old.toml")
        );
    }
}
