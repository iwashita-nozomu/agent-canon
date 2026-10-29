// @dependency-start
// contract implementation
// responsibility Resolves generated skill views to catalog and internal-routine owners without Python execution.
// upstream design ../../../../../documents/design/skill-runtime-shim-materialization.md materializer path contract
// upstream design ../../../../../agents/skills/catalog.yaml public skill identity and owner paths
// downstream implementation surface_manifest.rs publishes generated projections in the native surface snapshot
// @dependency-end

use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use yaml_rust2::YamlLoader;

const SKILL_CATALOG: &str = "agents/skills/catalog.yaml";
const GENERATED_SKILL_PREFIX: &str = ".codex/personal/skills/";
const GENERATED_SKILL_SUFFIX: &str = "/SKILL.md";

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct GeneratedProjection {
    pub(crate) path: String,
    pub(crate) source: String,
    pub(crate) projection_producer: String,
    pub(crate) projection_kind: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ProjectionError {
    Invalid(String),
    Ambiguous { path: String, owners: Vec<String> },
}

impl fmt::Display for ProjectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Invalid(message) => formatter.write_str(message),
            Self::Ambiguous { path, owners } => write!(
                formatter,
                "generated_projection_ambiguous:{path}:{}",
                owners.join(",")
            ),
        }
    }
}

fn projection(path: String, source: String, kind: &str) -> GeneratedProjection {
    GeneratedProjection {
        path,
        source,
        projection_producer: "agent-canon-bootstrap".to_string(),
        projection_kind: kind.to_string(),
    }
}

fn catalog_projections(root: &Path) -> Result<Vec<GeneratedProjection>, ProjectionError> {
    let path = root.join(SKILL_CATALOG);
    if !path.is_file() {
        return Ok(Vec::new());
    }
    let text = fs::read_to_string(&path)
        .map_err(|error| ProjectionError::Invalid(format!("skill catalog unavailable: {error}")))?;
    let documents = YamlLoader::load_from_str(&text)
        .map_err(|error| ProjectionError::Invalid(format!("skill catalog unavailable: {error}")))?;
    if documents.is_empty() {
        return Err(ProjectionError::Invalid(
            "skill catalog must contain a skill_families list".to_string(),
        ));
    }
    if documents.len() > 1 {
        return Err(ProjectionError::Invalid(
            "skill catalog unavailable: expected a single YAML document".to_string(),
        ));
    }
    let families = documents[0]["skill_families"].as_vec().ok_or_else(|| {
        ProjectionError::Invalid("skill catalog must contain a skill_families list".to_string())
    })?;
    let mut projections = Vec::new();
    let mut owners = BTreeSet::new();
    for (index, item) in families.iter().enumerate() {
        if item.as_hash().is_none() {
            return Err(ProjectionError::Invalid(format!(
                "skill catalog entry {index} must be a mapping"
            )));
        }
        let identity = ["id", "canonical_doc", "shim"].map(|key| {
            item[key].as_str().filter(|value| !value.is_empty())
        });
        let [Some(skill), Some(canonical), Some(shim)] = identity else {
            return Err(ProjectionError::Invalid(format!(
                "skill catalog entry {index} has incomplete identity"
            )));
        };
        if canonical != format!("agents/skills/{skill}.md")
            || shim != format!("{GENERATED_SKILL_PREFIX}{skill}{GENERATED_SKILL_SUFFIX}")
        {
            return Err(ProjectionError::Invalid(format!(
                "skill catalog entry {skill} has non-canonical materializer paths"
            )));
        }
        if !owners.insert(shim.to_string()) {
            return Err(ProjectionError::Invalid(format!(
                "duplicate generated skill projection: {shim}"
            )));
        }
        projections.push(projection(shim.to_string(), canonical.to_string(), "skill_shim"));
    }
    Ok(projections)
}

fn markdown_paths(directory: &Path, paths: &mut Vec<PathBuf>) -> Result<(), ProjectionError> {
    let entries = fs::read_dir(directory).map_err(|error| {
        ProjectionError::Invalid(format!("internal routine unavailable: {}: {error}", directory.display()))
    })?;
    for entry in entries {
        let entry = entry.map_err(|error| {
            ProjectionError::Invalid(format!("internal routine unavailable: {}: {error}", directory.display()))
        })?;
        let path = entry.path();
        if path.extension().is_some_and(|extension| extension == "md") {
            paths.push(path.clone());
        }
        let file_type = entry.file_type().map_err(|error| {
            ProjectionError::Invalid(format!("internal routine unavailable: {}: {error}", path.display()))
        })?;
        // Match Path.rglob: read matching file views, but never recurse through
        // a directory symlink or require generated SKILL.md views to exist.
        if file_type.is_dir() {
            markdown_paths(&path, paths)?;
        }
    }
    Ok(())
}

fn reference_delimiter(character: char) -> bool {
    character.is_whitespace()
        || matches!(character, '\u{1c}'..='\u{1f}' | '`' | ')' | '>')
}

fn private_skill_references(text: &str) -> BTreeSet<String> {
    let mut result = BTreeSet::new();
    let mut tail = text;
    while let Some(start) = tail.find(GENERATED_SKILL_PREFIX) {
        let reference = &tail[start..];
        let body = &reference[GENERATED_SKILL_PREFIX.len()..];
        let end = body.find(reference_delimiter).unwrap_or(body.len());
        let token = &body[..end];
        if let Some(suffix) = token.rfind(GENERATED_SKILL_SUFFIX).filter(|offset| *offset > 0) {
            let length = GENERATED_SKILL_PREFIX.len() + suffix + GENERATED_SKILL_SUFFIX.len();
            if body.starts_with('_') {
                result.insert(reference[..length].to_string());
            }
            tail = &reference[length..];
        } else {
            tail = body;
        }
    }
    result
}

fn relative_posix_path(root: &Path, path: &Path) -> Result<String, ProjectionError> {
    let relative = path.strip_prefix(root).map_err(|error| {
        ProjectionError::Invalid(format!("internal routine unavailable: {}: {error}", path.display()))
    })?;
    let text = relative.to_string_lossy();
    Ok(if cfg!(windows) { text.replace('\\', "/") } else { text.into_owned() })
}

pub(crate) fn generated_skill_projections(root: &Path) -> Result<Vec<GeneratedProjection>, ProjectionError> {
    let mut projections = catalog_projections(root)?;
    let mut owners: BTreeMap<String, String> = projections.iter()
        .map(|projection| (projection.path.clone(), projection.source.clone())).collect();
    let internal_root = root.join("agents/internal-routines");
    if internal_root.is_dir() {
        let mut sources = Vec::new();
        markdown_paths(&internal_root, &mut sources)?;
        sources.sort();
        for path in sources {
            let source = relative_posix_path(root, &path)?;
            let text = fs::read_to_string(&path).map_err(|error| {
                ProjectionError::Invalid(format!("internal routine unavailable: {source}: {error}"))
            })?;
            for shim in private_skill_references(&text) {
                if let Some(previous) = owners.get(&shim) {
                    if previous != &source {
                        return Err(ProjectionError::Ambiguous {
                            path: shim,
                            owners: vec![previous.clone(), source],
                        });
                    }
                    continue;
                }
                owners.insert(shim.clone(), source.clone());
                projections.push(projection(shim, source.clone(), "internal_skill_shim"));
            }
        }
    }
    projections.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(projections)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static SEQUENCE: AtomicU64 = AtomicU64::new(0);

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
            let count = SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let root = std::env::temp_dir().join(format!("agent-canon-projections-{}-{nanos}-{count}", std::process::id()));
            fs::create_dir_all(&root).unwrap();
            Self(root)
        }

        fn write(&self, relative: &str, text: &str) {
            let path = self.0.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text).unwrap();
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); }
    }

    #[test]
    fn resolves_public_and_private_owners_without_materialized_views() {
        let fixture = Fixture::new();
        fixture.write(SKILL_CATALOG, "skill_families:\n  - id: example\n    canonical_doc: agents/skills/example.md\n    shim: .codex/personal/skills/example/SKILL.md\n");
        fixture.write("agents/internal-routines/private.md", "[view](../../.codex/personal/skills/_private/SKILL.md)\n`../.codex/personal/skills/_private/SKILL.md`\n.codex/personal/skills/public-reference/SKILL.md\n");
        let projections = generated_skill_projections(&fixture.0).unwrap();
        assert_eq!(projections.len(), 2);
        assert_eq!(projections[0], projection(".codex/personal/skills/_private/SKILL.md".into(), "agents/internal-routines/private.md".into(), "internal_skill_shim"));
        assert_eq!(projections[1], projection(".codex/personal/skills/example/SKILL.md".into(), "agents/skills/example.md".into(), "skill_shim"));
        assert!(!fixture.0.join(".codex").exists());
    }

    #[test]
    fn competing_private_owners_return_stable_ambiguity_fields() {
        let fixture = Fixture::new();
        for name in ["two.md", "one.md"] {
            fixture.write(&format!("agents/internal-routines/{name}"), ".codex/personal/skills/_duplicate/SKILL.md\n");
        }
        let error = generated_skill_projections(&fixture.0).unwrap_err();
        assert_eq!(error, ProjectionError::Ambiguous {
            path: ".codex/personal/skills/_duplicate/SKILL.md".into(),
            owners: vec!["agents/internal-routines/one.md".into(), "agents/internal-routines/two.md".into()],
        });
        assert_eq!(error.to_string(), "generated_projection_ambiguous:.codex/personal/skills/_duplicate/SKILL.md:agents/internal-routines/one.md,agents/internal-routines/two.md");
    }

    #[test]
    fn invalid_and_duplicate_catalog_identities_are_rejected() {
        let fixture = Fixture::new();
        let valid = "  - id: example\n    canonical_doc: agents/skills/example.md\n    shim: .codex/personal/skills/example/SKILL.md\n";
        for (text, expected) in [
            ("not: a catalog\n".to_string(), "skill_families list"),
            ("skill_families: [false]\n".to_string(), "entry 0 must be a mapping"),
            ("skill_families: [{id: example}]\n".to_string(), "incomplete identity"),
            (format!("skill_families:\n{}", valid.replace("agents/skills/example.md", "wrong.md")), "non-canonical materializer paths"),
            (format!("skill_families:\n{valid}{valid}"), "duplicate generated skill projection"),
        ] {
            fixture.write(SKILL_CATALOG, &text);
            assert!(generated_skill_projections(&fixture.0).unwrap_err().to_string().contains(expected), "{expected}");
        }
    }

    #[test]
    fn absent_catalog_and_internal_sources_produce_an_empty_registry() {
        let fixture = Fixture::new();
        assert!(generated_skill_projections(&fixture.0).unwrap().is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn internal_source_filename_preserves_a_literal_backslash() {
        let fixture = Fixture::new();
        let source = r"agents/internal-routines/literal\name.md";
        fixture.write(source, ".codex/personal/skills/_literal/SKILL.md\n");
        let projections = generated_skill_projections(&fixture.0).unwrap();
        assert_eq!(projections[0].source, source);
    }
}
