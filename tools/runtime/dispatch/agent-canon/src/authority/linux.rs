use super::{
    digest_bytes, digest_hex, encode_hex, AttestationRequest, AttestedParent, AuthorityError,
    ChildHandoffReceipt, ChildHandoffRequest, ComponentIdentity, EntryKind, FileIdentity, FileMode,
    HandoffMode, HandoffStorage, HandoffTransport, LexicalEntrySnapshot, LexicalSnapshot,
    NonEmptyTrimmedString, Nonce128, OwnerRoot, ParentOwnedPathReceipt, ParentRootReject,
    PhysicalRoot, RootKind, RootPrecedence, SecretToken, Sha256Digest, TargetIdentity,
    VerifiedChildHandoff, HANDOFF_SCHEMA,
};
use base64::engine::general_purpose::URL_SAFE;
use base64::Engine;
use cap_fs_ext::{DirExt, FollowSymlinks, OpenOptionsFollowExt};
use cap_std::ambient_authority;
use cap_std::fs::{
    Dir, DirBuilder, DirBuilderExt, MetadataExt, OpenOptions, OpenOptionsExt, Permissions,
    PermissionsExt,
};
use hmac::{Hmac, Mac};
use serde::de::{MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::value::RawValue;
use serde_json::{Map, Number, Value};
use sha2::Sha256;
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::env;
use std::ffi::{OsStr, OsString};
use std::fmt;
use std::fs;
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::MetadataExt as StdMetadataExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output};

type HmacSha256 = Hmac<Sha256>;

const ALLOWED_MARKER_FIELDS: &[&str] = &[
    "schema",
    "parent_repo_id",
    "topic_slug",
    "repo_name",
    "clone_path",
    "remote_url",
    "branch",
    "owner_evidence_sha256",
    "source_commit",
    "source_tree",
    "created_at",
    "nonce",
];
const ALLOWED_OWNER_FIELDS: &[&str] = &[
    "schema",
    "parent_repo_id",
    "physical_parent",
    "module_path",
    "remote_url",
    "observed_commit",
    "observed_tree",
    "evidence_sha256",
];

pub(crate) fn attest(request: &AttestationRequest) -> Result<AttestedParent, AuthorityError> {
    let cwd = open_physical_root(&request.cwd, ParentRootReject::RootMissing)?;
    let (root, precedence) = match request.explicit_root.as_deref() {
        Some(explicit_path) => {
            let explicit = open_physical_root(explicit_path, ParentRootReject::RootMissing)?;
            if !cwd.path.starts_with(&explicit.path) {
                return Err(error(
                    ParentRootReject::RootSpoofed,
                    format!("cwd is outside explicit root: {}", cwd.path.display()),
                ));
            }
            let explicit_git = git_toplevel(&explicit.path).map_err(|value| {
                if value.reject == ParentRootReject::RootMissing {
                    error(
                        ParentRootReject::RootMismatch,
                        "explicit root is not an authenticated Git checkout",
                    )
                } else {
                    value
                }
            })?;
            if explicit_git != explicit.path {
                return Err(error(
                    ParentRootReject::RootMismatch,
                    "explicit root is not Git toplevel",
                ));
            }
            let cwd_git = git_toplevel(&cwd.path)?;
            if cwd_git != explicit.path {
                return Err(error(
                    ParentRootReject::RootMismatch,
                    "cwd Git identity differs from explicit root",
                ));
            }
            (explicit, RootPrecedence::ExplicitGit)
        }
        None => {
            let top = git_toplevel(&cwd.path)?;
            (
                open_physical_root(&top, ParentRootReject::RootMissing)?,
                RootPrecedence::Resolver,
            )
        }
    };

    let ambient_root = env::var("AGENT_CANON_ACTIVE_REPOSITORY_ROOT")
        .unwrap_or_default()
        .trim()
        .to_owned();
    if !ambient_root.is_empty() {
        let ambient = open_physical_root(Path::new(&ambient_root), ParentRootReject::RootMissing)?;
        if ambient.path != root.path {
            return Err(error(
                ParentRootReject::RootMismatch,
                "ambient active repository root is inconsistent with the selected root",
            ));
        }
    }

    let common_path = git_common_dir(&root.path)?;
    let common = open_physical_root(&common_path, ParentRootReject::RootMissing)?;
    let source = request
        .source_root
        .as_deref()
        .map(|path| open_physical_root(path, ParentRootReject::RootMissing))
        .transpose()?;
    let clone = request
        .clone_root
        .as_deref()
        .map(|path| open_physical_root(path, ParentRootReject::RootMissing))
        .transpose()?;

    for (label, child) in [("source", source.as_ref()), ("clone", clone.as_ref())] {
        let Some(child) = child else { continue };
        if !child.path.starts_with(&root.path) {
            return Err(error(
                ParentRootReject::RootMismatch,
                format!("{label} root is outside parent root"),
            ));
        }
        if git_toplevel(&child.path)? != child.path {
            return Err(error(
                ParentRootReject::RootMismatch,
                format!("{label} is not an authenticated Git checkout"),
            ));
        }
    }
    if source
        .as_ref()
        .zip(clone.as_ref())
        .is_some_and(|(source, clone)| source.path == clone.path)
    {
        return Err(error(
            ParentRootReject::RootAmbiguous,
            "source and clone roots are identical",
        ));
    }
    if clone.is_some()
        && (request.topic_marker.is_none()
            || request.gitmodules.is_none()
            || request.owner_evidence.is_none())
    {
        return Err(error(
            ParentRootReject::RootMismatch,
            "topic clone relation lacks marker/module/owner evidence",
        ));
    }

    let marker = read_bound_file(
        &root.path,
        request.topic_marker.as_deref(),
        ParentRootReject::MarkerInvalid,
    )?;
    let mut module = read_bound_file(
        &root.path,
        request.gitmodules.as_deref(),
        ParentRootReject::ModuleInvalid,
    )?;
    let owner = read_bound_file(
        &root.path,
        request.owner_evidence.as_deref(),
        ParentRootReject::OwnerEvidenceInvalid,
    )?;

    if let (Some(source), Some(manifest)) = (source.as_ref(), request.gitmodules.as_deref()) {
        module = Some(module_binding(
            &root.path,
            manifest,
            &source.path,
            ParentRootReject::ModuleInvalid,
        )?);
    }

    if let (Some(clone), Some(marker), Some(_), Some(owner)) = (
        clone.as_ref(),
        marker.as_ref(),
        module.as_ref(),
        owner.as_ref(),
    ) {
        let source = source.as_ref().ok_or_else(|| {
            error(
                ParentRootReject::RootMismatch,
                "topic relation lacks an authenticated source root",
            )
        })?;
        let _ = git_identity(&clone.path, ParentRootReject::MarkerInvalid)?;
        let (source_commit, source_tree) =
            git_identity(&source.path, ParentRootReject::ModuleInvalid)?;
        let clone_branch = git_value(
            &clone.path,
            &["symbolic-ref", "--short", "HEAD"],
            ParentRootReject::MarkerInvalid,
        )?;
        let clone_remote = git_origin(&clone.path)?;
        let manifest_path = request.gitmodules.as_deref().ok_or_else(|| {
            error(
                ParentRootReject::RootMismatch,
                "topic relation binding files disappeared",
            )
        })?;
        let owner_path = request.owner_evidence.as_deref().ok_or_else(|| {
            error(
                ParentRootReject::RootMismatch,
                "topic relation binding files disappeared",
            )
        })?;
        let actual_module = module_binding(
            &root.path,
            manifest_path,
            &source.path,
            ParentRootReject::ModuleInvalid,
        )?;
        let module_url = value_string(&actual_module, "url", ParentRootReject::ModuleInvalid)?;
        if normalize_remote(module_url) != normalize_remote(&git_origin(&source.path)?) {
            return Err(error(
                ParentRootReject::ModuleInvalid,
                "module URL does not match source Git origin",
            ));
        }
        if value_string(
            &actual_module,
            "observed_commit",
            ParentRootReject::ModuleInvalid,
        )? != source_commit
            || value_string(
                &actual_module,
                "observed_tree",
                ParentRootReject::ModuleInvalid,
            )? != source_tree
        {
            return Err(error(
                ParentRootReject::ModuleInvalid,
                "module observed commit/tree changed during attestation",
            ));
        }

        let parent_repo_id = parent_repo_id(&root.path)?;
        let marker_checks = [
            ("parent_repo_id", parent_repo_id.as_str()),
            ("clone_path", display_path(&clone.path)?),
            (
                "repo_name",
                clone
                    .path
                    .file_name()
                    .and_then(OsStr::to_str)
                    .ok_or_else(|| {
                        error(ParentRootReject::MarkerInvalid, "clone name is not UTF-8")
                    })?,
            ),
            (
                "topic_slug",
                clone
                    .path
                    .parent()
                    .and_then(Path::file_name)
                    .and_then(OsStr::to_str)
                    .ok_or_else(|| {
                        error(ParentRootReject::MarkerInvalid, "topic name is not UTF-8")
                    })?,
            ),
            ("branch", clone_branch.as_str()),
            ("remote_url", clone_remote.as_str()),
            ("source_commit", source_commit.as_str()),
            ("source_tree", source_tree.as_str()),
        ];
        for (key, expected) in marker_checks {
            let observed = value_string(marker, key, ParentRootReject::MarkerInvalid)?;
            if observed.trim_end_matches('/') != expected.trim_end_matches('/') {
                return Err(error(
                    ParentRootReject::MarkerInvalid,
                    format!("marker {key} does not match observed identity"),
                ));
            }
        }

        let owner_raw_digest = digest_hex(&read_stable_bound_file(
            &root.path,
            owner_path,
            ParentRootReject::OwnerEvidenceInvalid,
        )?);
        if value_string(
            marker,
            "owner_evidence_sha256",
            ParentRootReject::MarkerInvalid,
        )? != owner_raw_digest
        {
            return Err(error(
                ParentRootReject::OwnerEvidenceInvalid,
                "marker owner evidence digest does not match raw evidence",
            ));
        }
        let module_path = value_string(
            &actual_module,
            "module_path",
            ParentRootReject::ModuleInvalid,
        )?;
        let parent_remote = git_origin(&root.path)?;
        let owner_checks = [
            ("parent_repo_id", parent_repo_id.as_str()),
            ("physical_parent", display_path(&root.path)?),
            ("module_path", module_path),
            ("remote_url", parent_remote.as_str()),
            ("observed_commit", source_commit.as_str()),
            ("observed_tree", source_tree.as_str()),
        ];
        for (key, expected) in owner_checks {
            if value_string(owner, key, ParentRootReject::OwnerEvidenceInvalid)? != expected {
                return Err(error(
                    ParentRootReject::OwnerEvidenceInvalid,
                    format!("owner evidence {key} does not match observed identity"),
                ));
            }
        }
        let owner_map = owner.as_object().ok_or_else(|| {
            error(
                ParentRootReject::OwnerEvidenceInvalid,
                "owner evidence must be a JSON object",
            )
        })?;
        let mut evidence_body = owner_map.clone();
        let claimed = evidence_body
            .remove("evidence_sha256")
            .and_then(|value| value.as_str().map(str::to_owned))
            .ok_or_else(|| {
                error(
                    ParentRootReject::OwnerEvidenceInvalid,
                    "owner evidence digest is missing",
                )
            })?;
        if !is_digest(&claimed)
            || claimed != digest_hex(&canonical_json(&Value::Object(evidence_body)))
        {
            return Err(error(
                ParentRootReject::OwnerEvidenceInvalid,
                "owner evidence digest does not match canonical body",
            ));
        }
        module = Some(actual_module);
    }

    if let Some(expected) = request.expected_module_digest {
        let observed = module
            .as_ref()
            .and_then(|value| value.get("sha256"))
            .and_then(Value::as_str);
        let expected_hex = expected.to_hex();
        if observed != Some(expected_hex.as_str()) {
            return Err(error(
                ParentRootReject::ModuleInvalid,
                "module digest missing or mismatched",
            ));
        }
    }
    if let Some(expected_remote) = request.expected_remote.as_deref() {
        if normalize_remote(&git_origin(&root.path)?) != normalize_remote(expected_remote) {
            return Err(error(
                ParentRootReject::MarkerInvalid,
                "expected remote does not match Git origin",
            ));
        }
    }

    let handoff = request
        .child_handoff_token
        .as_ref()
        .map(|token| {
            verify_handoff(
                token,
                request,
                &root.path,
                source.as_ref().map(|value| value.path.as_path()),
                clone.as_ref().map(|value| value.path.as_path()),
            )
        })
        .transpose()?;

    let kind = if clone.is_some() {
        RootKind::Topic
    } else if source
        .as_ref()
        .and_then(|value| value.path.file_name())
        .and_then(OsStr::to_str)
        .is_some_and(|name| name == "agent-canon")
    {
        RootKind::Vendored
    } else if request.explicit_root.is_some() {
        RootKind::Direct
    } else {
        RootKind::Standalone
    };
    let attested = AttestedParent {
        parent_identity: root.identity,
        git_common_identity: common.identity,
        parent_root: root,
        git_common_dir: common,
        source_root: source,
        clone_root: clone,
        root_kind: kind,
        precedence,
        purpose: request.purpose.clone(),
        handoff,
        token_digest: request
            .child_handoff_token
            .as_ref()
            .map(SecretToken::digest),
    };
    verify_live_identity(&attested)?;
    Ok(attested)
}

pub(crate) fn issue_child_handoff(
    request: &ChildHandoffRequest,
) -> Result<ChildHandoffReceipt, AuthorityError> {
    if request.ttl.is_zero() {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff lifetime must be positive",
        ));
    }
    let root = open_physical_root(&request.parent_root, ParentRootReject::RootMissing)?;
    if git_toplevel(&root.path)? != root.path {
        return Err(error(
            ParentRootReject::RootMismatch,
            "handoff root is not Git toplevel",
        ));
    }
    let common_path = git_common_dir(&root.path)?;
    let common = open_physical_root(&common_path, ParentRootReject::RootMissing)?;
    verify_live_root(&root, &root.identity, &common, &common.identity)?;
    let source = request
        .source_root
        .as_deref()
        .map(|path| open_physical_root(path, ParentRootReject::RootMissing))
        .transpose()?;
    let clone = request
        .clone_root
        .as_deref()
        .map(|path| open_physical_root(path, ParentRootReject::RootMissing))
        .transpose()?;
    for (label, child) in [("source", source.as_ref()), ("clone", clone.as_ref())] {
        let Some(child) = child else { continue };
        if !child.path.starts_with(&root.path) {
            return Err(error(
                ParentRootReject::RootMismatch,
                format!("handoff {label} is outside parent root"),
            ));
        }
        if label == "clone" && git_toplevel(&child.path)? != child.path {
            return Err(error(
                ParentRootReject::RootMismatch,
                "handoff clone is not an authenticated Git checkout",
            ));
        }
        verify_physical_identity(child, &child.identity).map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                "handoff root binding changed",
            )
        })?;
    }

    let nonce = Nonce128::generate()?;
    let issued_at = monotonic_now();
    let expires_at = issued_at + request.ttl.as_secs_f64();
    let storage = if request.transport == HandoffTransport::ParentLocalFile {
        HandoffStorage::ParentLocalFile
    } else {
        HandoffStorage::Pipe
    };
    let mode = if request.transport == HandoffTransport::ParentLocalFile {
        HandoffMode::PrivateFile0600
    } else {
        HandoffMode::Pipe
    };
    let mut payload = Map::new();
    payload.insert("token_version".into(), Value::String(HANDOFF_SCHEMA.into()));
    payload.insert(
        "audience".into(),
        Value::String(request.audience.as_str().into()),
    );
    payload.insert(
        "parent_root".into(),
        Value::String(path_string(&root.path)?),
    );
    payload.insert(
        "source_root".into(),
        source
            .as_ref()
            .map(|value| path_string(&value.path).map(Value::String))
            .transpose()?
            .unwrap_or(Value::Null),
    );
    payload.insert(
        "clone_root".into(),
        clone
            .as_ref()
            .map(|value| path_string(&value.path).map(Value::String))
            .transpose()?
            .unwrap_or(Value::Null),
    );
    payload.insert("issued_at".into(), number_from_f64(issued_at)?);
    payload.insert("expires_at".into(), number_from_f64(expires_at)?);
    payload.insert("nonce".into(), Value::String(encode_hex(nonce.as_bytes())));
    payload.insert("storage".into(), Value::String(storage.as_str().into()));
    payload.insert("mode".into(), Value::String(mode.as_str().into()));
    payload.insert("validation".into(), Value::String("hmac-single-use".into()));
    payload.insert(
        "transport".into(),
        Value::String(request.transport.as_str().into()),
    );
    let payload_digest = digest_bytes(&canonical_json(&Value::Object(payload.clone())));
    payload.insert(
        "payload_sha256".into(),
        Value::String(payload_digest.to_hex()),
    );

    let secret = session_secret(&root, true)?;
    let signature = sign_payload(&payload, &secret)?;
    let mut envelope = Map::new();
    envelope.insert("payload".into(), Value::Object(payload.clone()));
    envelope.insert("signature".into(), Value::String(signature));
    let token = URL_SAFE.encode(canonical_json(&Value::Object(envelope)));
    let token = SecretToken::from_untrusted(token);

    verify_live_root(&root, &root.identity, &common, &common.identity)?;
    with_locked_state(&root, true, |state, file| {
        state.insert(encode_hex(nonce.as_bytes()), expires_at);
        write_locked_state(file, state)
    })?;
    verify_live_root(&root, &root.identity, &common, &common.identity)?;
    Ok(ChildHandoffReceipt {
        token_version: HANDOFF_SCHEMA.into(),
        audience: request.audience.clone(),
        parent_root: root.path,
        source_root: source.map(|value| value.path),
        clone_root: clone.map(|value| value.path),
        issued_at,
        expires_at,
        nonce,
        payload_sha256: payload_digest,
        storage,
        mode,
        validation: "hmac-single-use".into(),
        transport: request.transport,
        token,
    })
}

pub(crate) fn verify_live_identity(attested: &AttestedParent) -> Result<(), AuthorityError> {
    verify_live_root(
        &attested.parent_root,
        &attested.parent_identity,
        &attested.git_common_dir,
        &attested.git_common_identity,
    )?;
    for (label, child) in [
        ("source", attested.source_root.as_ref()),
        ("clone", attested.clone_root.as_ref()),
    ] {
        let Some(child) = child else { continue };
        verify_physical_identity(child, &child.identity)?;
        if git_toplevel(&child.path).map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                format!("attested {label} Git identity is unavailable"),
            )
        })? != child.path
        {
            return Err(error(
                ParentRootReject::RootRaceDetected,
                format!("attested {label} Git identity changed"),
            ));
        }
    }
    Ok(())
}

pub(crate) fn resolve_parent_owned_path(
    attested: &AttestedParent,
    candidate: &Path,
    purpose: NonEmptyTrimmedString,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    attested.verify_live_identity()?;
    let lexical_path = lexical_candidate(&attested.parent_root.path, candidate)?;
    let mut selected = None;
    for (owner, root) in [
        (OwnerRoot::GitCommon, &attested.git_common_dir),
        (OwnerRoot::Parent, &attested.parent_root),
    ] {
        if lexical_path.starts_with(&root.path) {
            let physical_path = resolve_physical_allow_missing(root, &lexical_path)?;
            if !physical_path.starts_with(&root.path) {
                return Err(error(
                    ParentRootReject::SymlinkEscape,
                    "path resolves outside its attested owner root",
                ));
            }
            selected = Some((owner, root, physical_path));
            break;
        }
    }
    let (owner, root, physical_path) = selected.ok_or_else(|| {
        error(
            ParentRootReject::SymlinkEscape,
            "parent-owned file is outside repository and Git admin roots",
        )
    })?;
    if physical_path == root.path {
        return Err(error(
            ParentRootReject::RootMismatch,
            "owner root is not a file target",
        ));
    }
    let physical_parts = relative_components(&root.path, &physical_path)?;
    let physical_parent_parts = &physical_parts[..physical_parts.len() - 1];
    let (physical_parent, parent_components, parent_complete) =
        open_existing_component_prefix(root, physical_parent_parts)?;
    let leaf = physical_path.file_name().ok_or_else(|| {
        error(
            ParentRootReject::RootMismatch,
            "parent-owned file name is unavailable",
        )
    })?;
    let target = if parent_complete {
        target_identity(&physical_parent, leaf)?
    } else {
        None
    };
    let lexical_snapshot = capture_lexical_snapshot(root, &lexical_path)?;
    let receipt = ParentOwnedPathReceipt {
        lexical_path,
        physical_path,
        owner,
        owner_path: root.path.clone(),
        owner_identity: root.identity,
        purpose,
        token_digest: attested.token_digest,
        parent_components,
        target,
        lexical_snapshot,
    };
    verify_lexical_snapshot(root, &receipt, false, false)?;
    attested.verify_live_identity()?;
    Ok(receipt)
}

pub(crate) fn read_parent_owned_file(
    attested: &AttestedParent,
    receipt: &ParentOwnedPathReceipt,
) -> Result<Vec<u8>, AuthorityError> {
    attested.verify_live_identity()?;
    let root = validate_receipt(attested, receipt)?;
    let target = receipt.target.ok_or_else(|| {
        error(
            ParentRootReject::RootRaceDetected,
            "parent-owned read receipt has no target identity",
        )
    })?;
    if target.kind != EntryKind::File {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "parent-owned read target is not a regular file",
        ));
    }
    let parts = relative_components(root.path(), &receipt.physical_path)?;
    let (parent_parts, leaf) = split_leaf(&parts)?;
    let (parent, opened_components) =
        open_component_chain(root, parent_parts, &receipt.parent_components, false)?;
    if opened_components != receipt.parent_components {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "parent directory identity changed before read",
        ));
    }

    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    #[cfg(unix)]
    {
        use cap_fs_ext::OpenOptionsSyncExt;
        options.nonblock(true);
    }
    let mut file = parent.open_with(leaf, &options).map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot open parent-owned file through its capability",
        )
    })?;
    let metadata = file.metadata().map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot inspect parent-owned file through its capability",
        )
    })?;
    if entry_kind(&metadata) != EntryKind::File
        || identity_from_cap_metadata(&metadata) != target.identity
    {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "file identity changed before read",
        ));
    }
    verify_lexical_snapshot(root, receipt, true, false)?;

    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes).map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot read parent-owned file",
        )
    })?;
    let after_read = file.metadata().map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot recheck parent-owned file after read",
        )
    })?;
    if identity_from_cap_metadata(&after_read) != target.identity
        || entry_kind(&after_read) != EntryKind::File
    {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "file identity changed during read",
        ));
    }
    verify_component_identities(root, parent_parts, &receipt.parent_components)?;
    verify_target_identity(&parent, leaf, Some(target), false)?;
    verify_lexical_snapshot(root, receipt, true, false)?;
    attested.verify_live_identity()?;
    Ok(bytes)
}

pub(crate) fn atomic_replace_parent_owned_file(
    attested: &AttestedParent,
    receipt: &ParentOwnedPathReceipt,
    bytes: &[u8],
    mode: FileMode,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    atomic_replace_with_hooks(
        attested,
        receipt,
        bytes,
        mode,
        |file, bytes| write_all_progress(file, bytes),
        |directory, name| directory.remove_file(name),
    )
}

pub(crate) fn write_parent_owned_file(
    attested: &AttestedParent,
    candidate: &Path,
    bytes: &[u8],
    purpose: NonEmptyTrimmedString,
) -> Result<ParentOwnedPathReceipt, AuthorityError> {
    let receipt = resolve_parent_owned_path(attested, candidate, purpose)?;
    atomic_replace_parent_owned_file(attested, &receipt, bytes, FileMode::Private0600)
}

fn lexical_candidate(root: &Path, candidate: &Path) -> Result<PathBuf, AuthorityError> {
    if candidate
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(error(
            ParentRootReject::SymlinkEscape,
            "lexical parent escape in parent-owned path",
        ));
    }
    Ok(if candidate.is_absolute() {
        candidate.to_path_buf()
    } else {
        root.join(candidate)
    })
}

fn resolve_physical_allow_missing(
    root: &PhysicalRoot,
    path: &Path,
) -> Result<PathBuf, AuthorityError> {
    let parts = resolvable_components(root.path(), path)?;
    let mut remaining = VecDeque::from(parts);
    let mut resolved_parts = Vec::<OsString>::new();
    let mut directories = vec![root.directory.try_clone().map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot clone attested directory capability",
        )
    })?];
    let mut symlink_count = 0_usize;

    while let Some(component) = remaining.pop_front() {
        if component == OsStr::new(".") {
            continue;
        }
        if component == OsStr::new("..") {
            if resolved_parts.pop().is_none() {
                return Err(error(
                    ParentRootReject::SymlinkEscape,
                    "symbolic link target escapes its attested owner root",
                ));
            }
            while directories.len() > resolved_parts.len() + 1 {
                directories.pop();
            }
            continue;
        }
        validate_component(&component)?;

        // Components below a missing prefix cannot exist yet. Keep resolving
        // lexical `..` components, but never use an ambient lookup for them.
        if resolved_parts.len() >= directories.len() {
            resolved_parts.push(component);
            continue;
        }

        let parent = directories.last().expect("root capability is retained");
        let metadata = match parent.symlink_metadata(&component) {
            Ok(metadata) => metadata,
            Err(error_value) if error_value.kind() == std::io::ErrorKind::NotFound => {
                resolved_parts.push(component);
                continue;
            }
            Err(_) => {
                return Err(error(
                    ParentRootReject::SymlinkEscape,
                    "cannot inspect parent-owned path component",
                ));
            }
        };
        if entry_kind(&metadata) == EntryKind::Symlink {
            symlink_count += 1;
            if symlink_count > 40 {
                return Err(error(
                    ParentRootReject::SymlinkEscape,
                    "parent-owned path contains too many symbolic links",
                ));
            }
            let target = parent.read_link(&component).map_err(|_| {
                error(
                    ParentRootReject::SymlinkEscape,
                    "cannot read parent-owned symbolic link",
                )
            })?;
            if target.is_absolute() {
                let target_parts = symlink_target_components(root, &target)?;
                resolved_parts.clear();
                directories.truncate(1);
                for part in target_parts.into_iter().rev() {
                    remaining.push_front(part);
                }
            } else {
                let target_parts = target
                    .components()
                    .filter_map(|part| match part {
                        Component::Normal(name) => Some(name.to_os_string()),
                        Component::ParentDir => Some(OsString::from("..")),
                        Component::CurDir => None,
                        Component::RootDir | Component::Prefix(_) => None,
                    })
                    .collect::<Vec<_>>();
                for part in target_parts.into_iter().rev() {
                    remaining.push_front(part);
                }
            }
            continue;
        }

        resolved_parts.push(component.clone());
        if entry_kind(&metadata) == EntryKind::Directory {
            let child = parent.open_dir_nofollow(&component).map_err(|_| {
                error(
                    ParentRootReject::RootRaceDetected,
                    "directory changed while resolving parent-owned path",
                )
            })?;
            directories.push(child);
        }
    }

    let mut physical = root.path.clone();
    for component in resolved_parts {
        physical.push(component);
    }
    Ok(physical)
}

fn symlink_target_components(
    root: &PhysicalRoot,
    target: &Path,
) -> Result<Vec<OsString>, AuthorityError> {
    let relative = target.strip_prefix(root.path()).map_err(|_| {
        error(
            ParentRootReject::SymlinkEscape,
            "parent-owned symbolic link escapes its owner root",
        )
    })?;
    relative
        .components()
        .filter_map(|component| match component {
            Component::Normal(name) => Some(Ok(name.to_os_string())),
            Component::ParentDir => Some(Ok(OsString::from(".."))),
            Component::CurDir => None,
            Component::RootDir | Component::Prefix(_) => Some(Err(error(
                ParentRootReject::SymlinkEscape,
                "parent-owned symbolic link has an invalid target component",
            ))),
        })
        .collect()
}

fn relative_components(root: &Path, path: &Path) -> Result<Vec<OsString>, AuthorityError> {
    let relative = path.strip_prefix(root).map_err(|_| {
        error(
            ParentRootReject::SymlinkEscape,
            "parent-owned path is outside its attested owner root",
        )
    })?;
    relative
        .components()
        .map(|component| match component {
            Component::Normal(name) if name != OsStr::new("") => Ok(name.to_os_string()),
            _ => Err(error(
                ParentRootReject::SymlinkEscape,
                "parent-owned path contains a non-normal component",
            )),
        })
        .collect()
}

fn resolvable_components(root: &Path, path: &Path) -> Result<Vec<OsString>, AuthorityError> {
    let relative = path.strip_prefix(root).map_err(|_| {
        error(
            ParentRootReject::SymlinkEscape,
            "parent-owned path is outside its attested owner root",
        )
    })?;
    relative
        .components()
        .filter_map(|component| match component {
            Component::Normal(name) => Some(Ok(name.to_os_string())),
            Component::ParentDir => Some(Ok(OsString::from(".."))),
            Component::CurDir => None,
            Component::RootDir | Component::Prefix(_) => Some(Err(error(
                ParentRootReject::SymlinkEscape,
                "parent-owned path contains an invalid root component",
            ))),
        })
        .collect()
}

fn split_leaf(parts: &[OsString]) -> Result<(&[OsString], &OsStr), AuthorityError> {
    let (leaf, parent) = parts.split_last().ok_or_else(|| {
        error(
            ParentRootReject::RootMismatch,
            "owner root is not a file target",
        )
    })?;
    Ok((parent, leaf.as_os_str()))
}

fn open_existing_component_prefix(
    root: &PhysicalRoot,
    parts: &[OsString],
) -> Result<(Dir, Vec<ComponentIdentity>, bool), AuthorityError> {
    let mut directory = root.directory.try_clone().map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot clone attested directory capability",
        )
    })?;
    let mut identities = Vec::with_capacity(parts.len());
    for name in parts {
        validate_component(name)?;
        match directory.open_dir_nofollow(name) {
            Ok(child) => {
                let identity = identity_from_cap_metadata(&child.metadata(".").map_err(|_| {
                    error(
                        ParentRootReject::RootRaceDetected,
                        "cannot inspect parent directory identity",
                    )
                })?);
                identities.push(ComponentIdentity {
                    name: name.clone(),
                    identity,
                });
                directory = child;
            }
            Err(error_value) if error_value.kind() == std::io::ErrorKind::NotFound => {
                return Ok((directory, identities, false));
            }
            Err(_) => {
                return Err(error(
                    ParentRootReject::SymlinkEscape,
                    "parent-owned path contains a symlink or non-directory component",
                ));
            }
        }
    }
    Ok((directory, identities, true))
}

fn open_component_chain(
    root: &PhysicalRoot,
    parts: &[OsString],
    expected: &[ComponentIdentity],
    create_missing: bool,
) -> Result<(Dir, Vec<ComponentIdentity>), AuthorityError> {
    if expected.len() > parts.len() || (!create_missing && expected.len() != parts.len()) {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "parent component snapshot shape changed",
        ));
    }
    let mut directory = root.directory.try_clone().map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot clone attested directory capability",
        )
    })?;
    let mut identities = Vec::with_capacity(parts.len());
    for (index, name) in parts.iter().enumerate() {
        validate_component(name)?;
        if let Some(snapshot) = expected.get(index) {
            if snapshot.name.as_os_str() != name.as_os_str() {
                return Err(error(
                    ParentRootReject::RootRaceDetected,
                    "parent component name changed",
                ));
            }
        }
        let child = match directory.open_dir_nofollow(name) {
            Ok(child) => child,
            Err(error_value)
                if create_missing
                    && index >= expected.len()
                    && error_value.kind() == std::io::ErrorKind::NotFound =>
            {
                create_private_directory(&directory, name)?;
                directory.open_dir_nofollow(name).map_err(|_| {
                    error(
                        ParentRootReject::RootRaceDetected,
                        "parent-owned directory changed during creation",
                    )
                })?
            }
            Err(_) => {
                return Err(error(
                    ParentRootReject::RootRaceDetected,
                    "parent directory component changed",
                ));
            }
        };
        let identity = identity_from_cap_metadata(&child.metadata(".").map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                "cannot inspect opened parent directory",
            )
        })?);
        if let Some(snapshot) = expected.get(index) {
            if snapshot.identity != identity {
                return Err(error(
                    ParentRootReject::RootRaceDetected,
                    "parent directory identity changed",
                ));
            }
        }
        identities.push(ComponentIdentity {
            name: name.clone(),
            identity,
        });
        directory = child;
    }
    Ok((directory, identities))
}

fn validate_component(name: &OsStr) -> Result<(), AuthorityError> {
    if name.is_empty() || name == OsStr::new(".") || name == OsStr::new("..") {
        return Err(error(
            ParentRootReject::SymlinkEscape,
            "parent-owned path contains an invalid component",
        ));
    }
    Ok(())
}

fn entry_kind(metadata: &cap_std::fs::Metadata) -> EntryKind {
    let kind = metadata.file_type();
    if kind.is_file() {
        EntryKind::File
    } else if kind.is_dir() {
        EntryKind::Directory
    } else if kind.is_symlink() {
        EntryKind::Symlink
    } else {
        EntryKind::Other
    }
}

fn target_identity(parent: &Dir, leaf: &OsStr) -> Result<Option<TargetIdentity>, AuthorityError> {
    match parent.symlink_metadata(leaf) {
        Ok(metadata) => Ok(Some(TargetIdentity {
            identity: identity_from_cap_metadata(&metadata),
            kind: entry_kind(&metadata),
        })),
        Err(error_value) if error_value.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => Err(error(
            ParentRootReject::RootRaceDetected,
            "cannot inspect parent-owned target identity",
        )),
    }
}

fn capture_lexical_snapshot(
    root: &PhysicalRoot,
    lexical_path: &Path,
) -> Result<Option<LexicalSnapshot>, AuthorityError> {
    let lexical_parent = lexical_path.parent().ok_or_else(|| {
        error(
            ParentRootReject::SymlinkEscape,
            "parent-owned lexical path has no parent",
        )
    })?;
    let parent_parts = relative_components(root.path(), lexical_parent)?;
    let (parent, parent_components, complete) =
        open_existing_component_prefix(root, &parent_parts)?;
    if !complete {
        return Ok(None);
    }
    let parent_identity = parent_components
        .last()
        .map(|component| component.identity)
        .unwrap_or(root.identity);
    let name = lexical_path.file_name().ok_or_else(|| {
        error(
            ParentRootReject::RootMismatch,
            "parent-owned lexical file name is unavailable",
        )
    })?;
    let entry = match parent.symlink_metadata(name) {
        Ok(metadata) => {
            let kind = entry_kind(&metadata);
            let symlink_target = if kind == EntryKind::Symlink {
                Some(parent.read_link(name).map_err(|_| {
                    error(
                        ParentRootReject::RootRaceDetected,
                        "cannot read parent-owned symlink target",
                    )
                })?)
            } else {
                None
            };
            Some(LexicalEntrySnapshot {
                name: name.to_os_string(),
                identity: identity_from_cap_metadata(&metadata),
                kind,
                symlink_target,
            })
        }
        Err(error_value) if error_value.kind() == std::io::ErrorKind::NotFound => None,
        Err(_) => {
            return Err(error(
                ParentRootReject::RootRaceDetected,
                "cannot inspect parent-owned lexical entry",
            ));
        }
    };
    Ok(Some(LexicalSnapshot {
        parent_path: lexical_parent.to_path_buf(),
        parent_components,
        parent_identity,
        entry,
    }))
}

fn validate_receipt<'a>(
    attested: &'a AttestedParent,
    receipt: &ParentOwnedPathReceipt,
) -> Result<&'a PhysicalRoot, AuthorityError> {
    let (root, identity) = owner_root(attested, receipt.owner);
    if root.path != receipt.owner_path
        || identity != receipt.owner_identity
        || receipt.token_digest != attested.token_digest
        || !receipt.lexical_path.starts_with(&receipt.owner_path)
        || !receipt.physical_path.starts_with(&receipt.owner_path)
    {
        return Err(error(
            ParentRootReject::RootMismatch,
            format!(
                "parent-owned path receipt for purpose {} belongs to a different attested root",
                receipt.purpose.as_str()
            ),
        ));
    }
    Ok(root)
}

fn owner_root(attested: &AttestedParent, owner: OwnerRoot) -> (&PhysicalRoot, FileIdentity) {
    match owner {
        OwnerRoot::Parent => (&attested.parent_root, attested.parent_identity),
        OwnerRoot::GitCommon => (&attested.git_common_dir, attested.git_common_identity),
    }
}

fn verify_component_identities(
    root: &PhysicalRoot,
    parts: &[OsString],
    expected: &[ComponentIdentity],
) -> Result<(), AuthorityError> {
    let _ = open_component_chain(root, parts, expected, false)?;
    Ok(())
}

fn verify_target_identity(
    parent: &Dir,
    leaf: &OsStr,
    expected: Option<TargetIdentity>,
    allow_new_entry: bool,
) -> Result<(), AuthorityError> {
    let observed = target_identity(parent, leaf)?;
    match (expected, observed) {
        (Some(expected), Some(observed)) if expected == observed => Ok(()),
        (None, None) => Ok(()),
        (None, Some(_)) if allow_new_entry => Ok(()),
        _ => Err(error(
            ParentRootReject::RootRaceDetected,
            "publication target identity changed",
        )),
    }
}

fn verify_lexical_snapshot(
    root: &PhysicalRoot,
    receipt: &ParentOwnedPathReceipt,
    require_entry: bool,
    allow_new_entry: bool,
) -> Result<(), AuthorityError> {
    let Some(snapshot) = receipt.lexical_snapshot.as_ref() else {
        if require_entry {
            return Err(error(
                ParentRootReject::RootRaceDetected,
                "path receipt has no lexical parent identity",
            ));
        }
        return Ok(());
    };
    let parts = relative_components(root.path(), &snapshot.parent_path)?;
    let (parent, components) =
        open_component_chain(root, &parts, &snapshot.parent_components, false)?;
    let parent_identity = components
        .last()
        .map(|component| component.identity)
        .unwrap_or(root.identity);
    if parent_identity != snapshot.parent_identity {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "lexical parent identity changed",
        ));
    }
    let leaf = receipt.lexical_path.file_name().ok_or_else(|| {
        error(
            ParentRootReject::RootRaceDetected,
            "lexical file name is unavailable",
        )
    })?;
    match (&snapshot.entry, target_identity(&parent, leaf)?) {
        (Some(expected), Some(observed))
            if expected.identity == observed.identity && expected.kind == observed.kind =>
        {
            if expected.name.as_os_str() != leaf {
                return Err(error(
                    ParentRootReject::RootRaceDetected,
                    "lexical entry name changed",
                ));
            }
            if expected.kind == EntryKind::Symlink {
                let expected_link = expected.symlink_target.as_ref().ok_or_else(|| {
                    error(
                        ParentRootReject::RootRaceDetected,
                        "path receipt has no lexical symlink target",
                    )
                })?;
                let observed_link = parent.read_link(leaf).map_err(|_| {
                    error(
                        ParentRootReject::RootRaceDetected,
                        "cannot recheck lexical symlink target",
                    )
                })?;
                if &observed_link != expected_link {
                    return Err(error(
                        ParentRootReject::RootRaceDetected,
                        "lexical symlink target changed",
                    ));
                }
                let linked_path = if expected_link.is_absolute() {
                    expected_link.clone()
                } else {
                    snapshot.parent_path.join(expected_link)
                };
                let resolved_link =
                    resolve_physical_allow_missing(root, &linked_path).map_err(|_| {
                        error(
                            ParentRootReject::RootRaceDetected,
                            "cannot re-resolve parent-owned lexical symlink",
                        )
                    })?;
                if resolved_link != receipt.physical_path {
                    return Err(error(
                        ParentRootReject::RootRaceDetected,
                        "lexical symlink no longer resolves to the attested target",
                    ));
                }
            } else {
                match receipt.target {
                    Some(target)
                        if target.identity == expected.identity && target.kind == expected.kind => {
                    }
                    _ => {
                        return Err(error(
                            ParentRootReject::RootRaceDetected,
                            "lexical entry and physical target identities differ",
                        ));
                    }
                }
            }
            Ok(())
        }
        (None, None) if !require_entry => Ok(()),
        (None, Some(_)) if !require_entry && allow_new_entry => Ok(()),
        _ => Err(error(
            ParentRootReject::RootRaceDetected,
            "lexical entry identity changed",
        )),
    }
}

fn atomic_replace_with_hooks<W, C>(
    attested: &AttestedParent,
    receipt: &ParentOwnedPathReceipt,
    bytes: &[u8],
    mode: FileMode,
    write: W,
    cleanup: C,
) -> Result<ParentOwnedPathReceipt, AuthorityError>
where
    W: FnOnce(&mut cap_std::fs::File, &[u8]) -> std::io::Result<()>,
    C: FnOnce(&Dir, &OsStr) -> std::io::Result<()>,
{
    attested.verify_live_identity()?;
    let root = validate_receipt(attested, receipt)?;
    let parts = relative_components(root.path(), &receipt.physical_path)?;
    let (parent_parts, leaf) = split_leaf(&parts)?;
    let (parent, parent_components) =
        open_component_chain(root, parent_parts, &receipt.parent_components, true)?;
    attested.verify_live_identity()?;
    verify_component_identities(root, parent_parts, &parent_components)?;
    verify_target_identity(&parent, leaf, receipt.target, true)?;
    verify_lexical_snapshot(root, receipt, false, true)?;

    let mut temp_name: Option<OsString> = None;
    let operation_result = (|| {
        let mut opened_temp = None;
        for _ in 0..32 {
            let mut random = [0_u8; 16];
            getrandom::getrandom(&mut random).map_err(|_| {
                error(
                    ParentRootReject::UnsupportedPlatform,
                    "operating-system temporary-name generation is unavailable",
                )
            })?;
            let mut candidate = OsString::from(".");
            candidate.push(leaf);
            candidate.push(".");
            candidate.push(encode_hex(&random));
            candidate.push(".tmp");
            let mut options = OpenOptions::new();
            options
                .write(true)
                .create_new(true)
                .follow(FollowSymlinks::No);
            options.mode(match mode {
                FileMode::Private0600 => 0o600,
            });
            match parent.open_with(&candidate, &options) {
                Ok(file) => {
                    temp_name = Some(candidate);
                    opened_temp = Some(file);
                    break;
                }
                Err(error_value) if error_value.kind() == std::io::ErrorKind::AlreadyExists => {
                    continue;
                }
                Err(_) => {
                    return Err(error(
                        ParentRootReject::RootRaceDetected,
                        "cannot create atomic parent-owned temporary file",
                    ));
                }
            }
        }
        let temp_name_ref = temp_name.as_ref().ok_or_else(|| {
            error(
                ParentRootReject::RootRaceDetected,
                "cannot allocate unique parent-owned temporary file",
            )
        })?;
        let mut file = opened_temp.ok_or_else(|| {
            error(
                ParentRootReject::RootRaceDetected,
                "temporary file was not opened",
            )
        })?;
        write(&mut file, bytes).map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                "cannot write parent-owned temporary file",
            )
        })?;
        file.sync_all().map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                "cannot sync parent-owned temporary file",
            )
        })?;
        drop(file);

        attested.verify_live_identity()?;
        verify_component_identities(root, parent_parts, &parent_components)?;
        verify_target_identity(&parent, leaf, receipt.target, true)?;
        verify_lexical_snapshot(root, receipt, false, true)?;
        parent.rename(temp_name_ref, &parent, leaf).map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                "cannot atomically replace parent-owned file",
            )
        })?;
        sync_directory(&parent)?;

        attested.verify_live_identity()?;
        verify_component_identities(root, parent_parts, &parent_components)?;
        let target = target_identity(&parent, leaf)?.ok_or_else(|| {
            error(
                ParentRootReject::RootRaceDetected,
                "published parent-owned file disappeared",
            )
        })?;
        if target.kind != EntryKind::File {
            return Err(error(
                ParentRootReject::RootRaceDetected,
                "published parent-owned target is not a regular file",
            ));
        }
        let lexical_snapshot = capture_lexical_snapshot(root, &receipt.lexical_path)?;
        if receipt
            .lexical_snapshot
            .as_ref()
            .and_then(|snapshot| snapshot.entry.as_ref())
            .is_some_and(|entry| entry.kind == EntryKind::Symlink)
            && receipt.lexical_snapshot != lexical_snapshot
        {
            return Err(error(
                ParentRootReject::RootRaceDetected,
                "lexical symlink changed during atomic replacement",
            ));
        }
        let mut refreshed = receipt.clone();
        refreshed.parent_components = parent_components.clone();
        refreshed.target = Some(target);
        refreshed.lexical_snapshot = lexical_snapshot;
        verify_lexical_snapshot(root, &refreshed, true, false)?;
        attested.verify_live_identity()?;
        Ok(refreshed)
    })();

    let cleanup_result = temp_name
        .as_ref()
        .map(|name| cleanup(&parent, name))
        .transpose();
    match (operation_result, cleanup_result) {
        (Ok(receipt), Ok(_)) => Ok(receipt),
        (Ok(_), Err(cleanup_error)) if cleanup_error.kind() != std::io::ErrorKind::NotFound => {
            Err(error(
                ParentRootReject::RootRaceDetected,
                format!("atomic replacement cleanup failed: {cleanup_error}"),
            ))
        }
        (Ok(receipt), Err(_)) => Ok(receipt),
        (Err(primary), Ok(_)) => Err(primary),
        (Err(primary), Err(cleanup_error))
            if cleanup_error.kind() != std::io::ErrorKind::NotFound =>
        {
            Err(error(
                ParentRootReject::RootRaceDetected,
                format!("{primary}; atomic replacement cleanup failed: {cleanup_error}"),
            ))
        }
        (Err(primary), Err(_)) => Err(primary),
    }
}

fn write_all_progress<W: Write>(writer: &mut W, bytes: &[u8]) -> std::io::Result<()> {
    writer.write_all(bytes)
}

fn sync_directory(directory: &Dir) -> Result<(), AuthorityError> {
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    let file = directory.open_with(".", &options).map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot reopen parent-owned destination directory for sync",
        )
    })?;
    if !file
        .metadata()
        .map_err(|_| {
            error(
                ParentRootReject::RootRaceDetected,
                "cannot inspect parent-owned destination directory for sync",
            )
        })?
        .is_dir()
    {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "parent-owned sync target is not a directory",
        ));
    }
    file.sync_all().map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "cannot sync parent-owned destination directory",
        )
    })
}

fn create_private_directory(parent: &Dir, name: &OsStr) -> Result<(), AuthorityError> {
    let mut builder = DirBuilder::new();
    builder.mode(0o700);
    match parent.create_dir_with(name, &builder) {
        Ok(()) => Ok(()),
        Err(error_value) if error_value.kind() == std::io::ErrorKind::AlreadyExists => Ok(()),
        Err(_) => Err(error(
            ParentRootReject::RootRaceDetected,
            "cannot create parent-owned directory component",
        )),
    }
}

fn verify_live_root(
    parent: &PhysicalRoot,
    parent_identity: &FileIdentity,
    common: &PhysicalRoot,
    common_identity: &FileIdentity,
) -> Result<(), AuthorityError> {
    verify_physical_identity(parent, parent_identity)?;
    verify_physical_identity(common, common_identity)?;
    let current_common = git_common_dir(&parent.path).map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "selected checkout no longer resolves to its attested Git common directory",
        )
    })?;
    if current_common != common.path {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "selected checkout no longer resolves to its attested Git common directory",
        ));
    }
    Ok(())
}

fn verify_physical_identity(
    root: &PhysicalRoot,
    expected: &FileIdentity,
) -> Result<(), AuthorityError> {
    let handle = root.directory.metadata(".").map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "opened root identity is unavailable",
        )
    })?;
    let current = identity_from_cap_metadata(&handle);
    let path_metadata = fs::metadata(&root.path).map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "physical root path changed",
        )
    })?;
    let path_identity = FileIdentity {
        device: path_metadata.dev(),
        inode: path_metadata.ino(),
    };
    if current != *expected || path_identity != *expected {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "physical root identity changed",
        ));
    }
    Ok(())
}

fn open_physical_root(
    path: &Path,
    missing_reject: ParentRootReject,
) -> Result<PhysicalRoot, AuthorityError> {
    let canonical = fs::canonicalize(path).map_err(|_| {
        error(
            missing_reject,
            format!("cannot resolve physical path {}", path.display()),
        )
    })?;
    let metadata = fs::metadata(&canonical).map_err(|_| {
        error(
            missing_reject,
            format!("cannot inspect physical path {}", canonical.display()),
        )
    })?;
    if !metadata.is_dir() {
        return Err(error(
            missing_reject,
            format!("physical root is not a directory: {}", canonical.display()),
        ));
    }
    let directory = Dir::open_ambient_dir(&canonical, ambient_authority()).map_err(|_| {
        error(
            missing_reject,
            format!("cannot open physical directory {}", canonical.display()),
        )
    })?;
    let identity = identity_from_cap_metadata(&directory.metadata(".").map_err(|_| {
        error(
            ParentRootReject::RootRaceDetected,
            "opened physical directory identity is unavailable",
        )
    })?);
    if identity.device != metadata.dev() || identity.inode != metadata.ino() {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "physical directory changed while it was opened",
        ));
    }
    Ok(PhysicalRoot {
        path: canonical,
        directory,
        identity,
    })
}

fn identity_from_cap_metadata(metadata: &cap_std::fs::Metadata) -> FileIdentity {
    use cap_std::fs::MetadataExt;
    FileIdentity {
        device: metadata.dev(),
        inode: metadata.ino(),
    }
}

fn git_toplevel(path: &Path) -> Result<PathBuf, AuthorityError> {
    let value = git_value(
        path,
        &["rev-parse", "--show-toplevel"],
        ParentRootReject::RootMissing,
    )?;
    fs::canonicalize(Path::new(&value)).map_err(|_| {
        error(
            ParentRootReject::RootMissing,
            "Git returned a top-level path that cannot be resolved",
        )
    })
}

fn git_common_dir(path: &Path) -> Result<PathBuf, AuthorityError> {
    let value = git_value(
        path,
        &["rev-parse", "--git-common-dir"],
        ParentRootReject::RootMismatch,
    )?;
    let candidate = PathBuf::from(value);
    let candidate = if candidate.is_absolute() {
        candidate
    } else {
        path.join(candidate)
    };
    let common = fs::canonicalize(&candidate).map_err(|_| {
        error(
            ParentRootReject::RootMismatch,
            "Git common directory is unavailable",
        )
    })?;
    if !fs::metadata(&common).is_ok_and(|metadata| metadata.is_dir()) {
        return Err(error(
            ParentRootReject::RootMismatch,
            "Git common directory is not a directory",
        ));
    }
    Ok(common)
}

fn git_origin(path: &Path) -> Result<String, AuthorityError> {
    git_value(
        path,
        &["remote", "get-url", "origin"],
        ParentRootReject::RootMismatch,
    )
}

fn git_value(
    path: &Path,
    args: &[&str],
    reject: ParentRootReject,
) -> Result<String, AuthorityError> {
    let output = git_output(path, args)?;
    if !output.status.success() {
        return Err(error(
            reject,
            format!("Git identity is unavailable at {}", path.display()),
        ));
    }
    let value = std::str::from_utf8(&output.stdout)
        .map_err(|_| error(reject, "Git returned non-UTF-8 identity output"))?
        .trim()
        .to_owned();
    if value.is_empty() {
        return Err(error(
            reject,
            format!("Git identity is empty at {}", path.display()),
        ));
    }
    Ok(value)
}

fn git_output(path: &Path, args: &[&str]) -> Result<Output, AuthorityError> {
    let mut command = Command::new("git");
    command.arg("-C").arg(path).args(args);
    for name in [
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_PREFIX",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
    ] {
        command.env_remove(name);
    }
    command.output().map_err(|_| {
        error(
            ParentRootReject::RootMissing,
            "cannot execute Git identity query",
        )
    })
}

fn git_identity(path: &Path, reject: ParentRootReject) -> Result<(String, String), AuthorityError> {
    Ok((
        git_value(path, &["rev-parse", "HEAD"], reject)?,
        git_value(path, &["rev-parse", "HEAD^{tree}"], reject)?,
    ))
}

fn parent_repo_id(root: &Path) -> Result<String, AuthorityError> {
    let remote = git_origin(root)?;
    let body = format!("{}\0{}", display_path(root)?, remote.trim_end_matches('/'));
    Ok(digest_hex(body.as_bytes()))
}

fn normalize_remote(value: &str) -> &str {
    value
        .trim_end_matches('/')
        .strip_suffix(".git")
        .unwrap_or_else(|| value.trim_end_matches('/'))
}

fn display_path(path: &Path) -> Result<&str, AuthorityError> {
    path.to_str().ok_or_else(|| {
        error(
            ParentRootReject::RootMismatch,
            "physical path is not representable as UTF-8",
        )
    })
}

fn path_string(path: &Path) -> Result<String, AuthorityError> {
    display_path(path).map(str::to_owned)
}

fn read_bound_file(
    root: &Path,
    requested: Option<&Path>,
    reject: ParentRootReject,
) -> Result<Option<Value>, AuthorityError> {
    let Some(requested) = requested else {
        return Ok(None);
    };
    let physical = canonical_bound_path(root, requested, reject)?;
    let raw = read_stable_file(&physical, reject)?;
    if physical
        .file_name()
        .and_then(OsStr::to_str)
        .is_some_and(|name| name == ".gitmodules")
    {
        if raw.is_empty() {
            return Err(error(reject, "module file is empty"));
        }
        let mut value = Map::new();
        value.insert("schema".into(), Value::String("gitmodules".into()));
        value.insert("sha256".into(), Value::String(digest_hex(&raw)));
        value.insert("path".into(), Value::String(path_string(&physical)?));
        return Ok(Some(Value::Object(value)));
    }
    if reject == ParentRootReject::MarkerInvalid {
        return Ok(Some(read_exact_schema(
            &raw,
            reject,
            ALLOWED_MARKER_FIELDS,
            "agent-canon.repository-topic.v2",
        )?));
    }
    if reject == ParentRootReject::OwnerEvidenceInvalid {
        return Ok(Some(read_exact_schema(
            &raw,
            reject,
            ALLOWED_OWNER_FIELDS,
            "agent-canon.owner-evidence.v1",
        )?));
    }
    let mut value = Map::new();
    value.insert("schema".into(), Value::String("gitmodules".into()));
    value.insert("sha256".into(), Value::String(digest_hex(&raw)));
    value.insert("path".into(), Value::String(path_string(&physical)?));
    Ok(Some(Value::Object(value)))
}

fn canonical_bound_path(
    root: &Path,
    requested: &Path,
    reject: ParentRootReject,
) -> Result<PathBuf, AuthorityError> {
    let candidate = if requested.is_absolute() {
        requested.to_path_buf()
    } else {
        root.join(requested)
    };
    let physical = fs::canonicalize(&candidate).map_err(|_| {
        error(
            reject,
            format!("cannot resolve bound file {}", candidate.display()),
        )
    })?;
    if !physical.starts_with(root) {
        return Err(error(
            ParentRootReject::SymlinkEscape,
            format!(
                "bound file escapes its parent root: {}",
                requested.display()
            ),
        ));
    }
    if !fs::metadata(&physical).is_ok_and(|metadata| metadata.is_file()) {
        return Err(error(
            reject,
            format!("bound path is not a regular file: {}", physical.display()),
        ));
    }
    Ok(physical)
}

fn read_stable_bound_file(
    root: &Path,
    requested: &Path,
    reject: ParentRootReject,
) -> Result<Vec<u8>, AuthorityError> {
    let physical = canonical_bound_path(root, requested, reject)?;
    read_stable_file(&physical, reject)
}

fn read_stable_file(path: &Path, reject: ParentRootReject) -> Result<Vec<u8>, AuthorityError> {
    let mut file = fs::File::open(path)
        .map_err(|_| error(reject, format!("cannot read bound file {}", path.display())))?;
    let before = file.metadata().map_err(|_| {
        error(
            reject,
            format!("cannot inspect bound file {}", path.display()),
        )
    })?;
    if !before.is_file() {
        return Err(error(
            reject,
            format!("bound path is not a regular file: {}", path.display()),
        ));
    }
    let identity = (
        before.dev(),
        before.ino(),
        before.len(),
        before.mtime(),
        before.mtime_nsec(),
    );
    let mut raw = Vec::new();
    file.read_to_end(&mut raw)
        .map_err(|_| error(reject, format!("cannot read bound file {}", path.display())))?;
    let after = file.metadata().map_err(|_| {
        error(
            reject,
            format!("cannot recheck bound file {}", path.display()),
        )
    })?;
    if identity
        != (
            after.dev(),
            after.ino(),
            after.len(),
            after.mtime(),
            after.mtime_nsec(),
        )
    {
        return Err(error(
            ParentRootReject::RootRaceDetected,
            "bound file changed while being read",
        ));
    }
    Ok(raw)
}

fn read_exact_schema(
    raw: &[u8],
    reject: ParentRootReject,
    required: &[&str],
    schema: &str,
) -> Result<Value, AuthorityError> {
    let value = strict_json(raw, reject)?;
    let object = value
        .as_object()
        .ok_or_else(|| error(reject, "bound file must be a JSON object"))?;
    let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
    let expected = required.iter().copied().collect::<BTreeSet<_>>();
    if actual != expected
        || object.get("schema").and_then(Value::as_str) != Some(schema)
        || object
            .values()
            .any(|value| value.as_str().is_none_or(|item| item.is_empty()))
    {
        return Err(error(reject, "bound file schema mismatch"));
    }
    Ok(value)
}

fn strict_json(raw: &[u8], reject: ParentRootReject) -> Result<Value, AuthorityError> {
    let mut deserializer = serde_json::Deserializer::from_slice(raw);
    let value = StrictValue::deserialize(&mut deserializer)
        .map_err(|_| error(reject, "invalid JSON or duplicate object key"))?;
    deserializer
        .end()
        .map_err(|_| error(reject, "trailing data after JSON value"))?;
    Ok(value.0)
}

struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = Box::<RawValue>::deserialize(deserializer)?;
        let token = raw.get();
        match token.trim_start().as_bytes().first().copied() {
            Some(b'{') => {
                let mut nested = serde_json::Deserializer::from_str(token);
                let value = nested
                    .deserialize_map(StrictObjectVisitor)
                    .map_err(<D::Error as serde::de::Error>::custom)?;
                nested
                    .end()
                    .map_err(<D::Error as serde::de::Error>::custom)?;
                Ok(StrictValue(Value::Object(value)))
            }
            Some(b'[') => {
                let values = serde_json::from_str::<Vec<StrictValue>>(token)
                    .map_err(<D::Error as serde::de::Error>::custom)?;
                Ok(StrictValue(Value::Array(
                    values.into_iter().map(|value| value.0).collect(),
                )))
            }
            Some(_) => {
                let value = serde_json::from_str::<Value>(token)
                    .map_err(<D::Error as serde::de::Error>::custom)?;
                Ok(StrictValue(value))
            }
            None => Err(<D::Error as serde::de::Error>::custom(
                "empty raw JSON value",
            )),
        }
    }
}

struct StrictObjectVisitor;

impl<'de> Visitor<'de> for StrictObjectVisitor {
    type Value = Map<String, Value>;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON object without duplicate keys")
    }

    fn visit_map<A>(self, mut mapping: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = Map::new();
        while let Some((key, value)) = mapping.next_entry::<String, StrictValue>()? {
            if values.insert(key, value.0).is_some() {
                return Err(serde::de::Error::custom("duplicate JSON object key"));
            }
        }
        Ok(values)
    }
}

fn module_binding(
    root: &Path,
    manifest: &Path,
    source: &Path,
    reject: ParentRootReject,
) -> Result<Value, AuthorityError> {
    let manifest = canonical_bound_path(root, manifest, reject)?;
    let manifest_path = path_string(&manifest)?;
    let output = git_output(
        root,
        &[
            "config",
            "--file",
            manifest_path.as_str(),
            "--null",
            "--list",
        ],
    )?;
    if !output.status.success() {
        return Err(error(reject, "cannot parse module manifest"));
    }
    let config = std::str::from_utf8(&output.stdout)
        .map_err(|_| error(reject, "module manifest output is not UTF-8"))?;
    let relative = source
        .strip_prefix(root)
        .map_err(|_| error(reject, "module source is outside the parent root"))?;
    let relative = relative
        .components()
        .map(|component| match component {
            Component::Normal(value) => value
                .to_str()
                .map(str::to_owned)
                .ok_or_else(|| error(reject, "module path is not UTF-8")),
            _ => Err(error(
                reject,
                "module path is not a normalized relative path",
            )),
        })
        .collect::<Result<Vec<_>, _>>()?
        .join("/");
    let mut values: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    for record in config.split('\0') {
        let Some((key, value)) = record.split_once('\n') else {
            continue;
        };
        let parts = key.split('.').collect::<Vec<_>>();
        if parts.len() == 3 && parts[0] == "submodule" && matches!(parts[2], "path" | "url") {
            values
                .entry(parts[1].to_owned())
                .or_default()
                .insert(parts[2].to_owned(), value.trim().to_owned());
        }
    }
    let matches = values
        .values()
        .filter(|value| value.get("path").is_some_and(|path| path == &relative))
        .collect::<Vec<_>>();
    if matches.len() != 1 || matches[0].get("url").is_none_or(String::is_empty) {
        return Err(error(reject, "module path is not uniquely bound"));
    }
    let (commit, tree) = git_identity(source, reject)?;
    let gitlink = git_value(root, &["ls-tree", "HEAD", "--", &relative], reject)?;
    let fields = gitlink.split_whitespace().collect::<Vec<_>>();
    if fields.len() < 3 || fields[0] != "160000" || fields[1] != "commit" || fields[2] != commit {
        return Err(error(
            reject,
            "module path is not an exact gitlink to source HEAD",
        ));
    }
    let raw = read_stable_file(&manifest, reject)?;
    let mut result = Map::new();
    result.insert("schema".into(), Value::String("gitmodules".into()));
    result.insert("sha256".into(), Value::String(digest_hex(&raw)));
    result.insert("module_path".into(), Value::String(relative));
    result.insert("url".into(), Value::String(matches[0]["url"].clone()));
    result.insert("observed_commit".into(), Value::String(commit));
    result.insert("observed_tree".into(), Value::String(tree));
    Ok(Value::Object(result))
}

fn value_string<'a>(
    value: &'a Value,
    key: &str,
    reject: ParentRootReject,
) -> Result<&'a str, AuthorityError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| error(reject, format!("bound field {key} is not a string")))
}

fn is_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn canonical_json(value: &Value) -> Vec<u8> {
    // Match parent_root_side_effects._canonical_bytes: sorted keys, compact
    // separators, UTF-8 text (ensure_ascii=False), and Python float repr.
    let mut output = Vec::new();
    write_canonical_value(value, &mut output);
    output
}

fn write_canonical_value(value: &Value, output: &mut Vec<u8>) {
    match value {
        Value::Null => output.extend_from_slice(b"null"),
        Value::Bool(value) => {
            if *value {
                output.extend_from_slice(b"true");
            } else {
                output.extend_from_slice(b"false");
            }
        }
        Value::Number(value) if value.is_f64() => {
            let number = value
                .as_f64()
                .expect("serde_json guarantees f64 for an f64 Number");
            output.extend_from_slice(
                rustpython_ast::Constant::Float(number)
                    .to_string()
                    .as_bytes(),
            );
        }
        Value::Number(value) => output.extend_from_slice(value.to_string().as_bytes()),
        Value::String(value) => write_json_string(value, output),
        Value::Array(values) => {
            output.push(b'[');
            for (index, value) in values.iter().enumerate() {
                if index != 0 {
                    output.push(b',');
                }
                write_canonical_value(value, output);
            }
            output.push(b']');
        }
        Value::Object(values) => {
            output.push(b'{');
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort_unstable();
            for (index, key) in keys.into_iter().enumerate() {
                if index != 0 {
                    output.push(b',');
                }
                write_json_string(key, output);
                output.push(b':');
                write_canonical_value(&values[key], output);
            }
            output.push(b'}');
        }
    }
}

fn write_json_string(value: &str, output: &mut Vec<u8>) {
    serde_json::to_writer(output, value)
        .expect("serializing a string into an in-memory byte vector is infallible");
}

fn monotonic_now() -> f64 {
    let time = rustix::time::clock_gettime(rustix::time::ClockId::Monotonic);
    time.tv_sec as f64 + time.tv_nsec as f64 / 1_000_000_000.0
}

fn number_from_f64(value: f64) -> Result<Value, AuthorityError> {
    Number::from_f64(value).map(Value::Number).ok_or_else(|| {
        error(
            ParentRootReject::HandoffInvalid,
            "invalid handoff timestamp",
        )
    })
}

fn nonce_from_hex(value: &str) -> Result<Nonce128, AuthorityError> {
    if value.len() != 32 {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "invalid handoff nonce",
        ));
    }
    let mut bytes = [0_u8; 16];
    let decoded = decode_hex(value)
        .filter(|decoded| decoded.len() == 16)
        .ok_or_else(|| error(ParentRootReject::HandoffInvalid, "invalid handoff nonce"))?;
    bytes.copy_from_slice(&decoded);
    Ok(Nonce128::from_bytes(bytes))
}

fn verify_handoff(
    token: &SecretToken,
    request: &AttestationRequest,
    root: &Path,
    source: Option<&Path>,
    clone: Option<&Path>,
) -> Result<VerifiedChildHandoff, AuthorityError> {
    let raw = URL_SAFE
        .decode(token.expose_for_transport())
        .map_err(|_| error(ParentRootReject::HandoffInvalid, "malformed handoff token"))?;
    let envelope = strict_json(&raw, ParentRootReject::HandoffInvalid)?;
    let envelope = envelope
        .as_object()
        .ok_or_else(|| error(ParentRootReject::HandoffInvalid, "invalid handoff envelope"))?;
    if envelope.len() != 2
        || !envelope.contains_key("payload")
        || !envelope.contains_key("signature")
    {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "invalid handoff envelope",
        ));
    }
    let payload = envelope
        .get("payload")
        .and_then(Value::as_object)
        .ok_or_else(|| error(ParentRootReject::HandoffInvalid, "invalid handoff payload"))?;
    let signature = envelope
        .get("signature")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            error(
                ParentRootReject::HandoffInvalid,
                "invalid handoff signature",
            )
        })?;
    let required = [
        "token_version",
        "audience",
        "parent_root",
        "source_root",
        "clone_root",
        "issued_at",
        "expires_at",
        "nonce",
        "payload_sha256",
        "storage",
        "mode",
        "validation",
        "transport",
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    let actual = payload.keys().map(String::as_str).collect::<BTreeSet<_>>();
    if actual != required
        || payload.get("token_version").and_then(Value::as_str) != Some(HANDOFF_SCHEMA)
    {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff fields are incomplete",
        ));
    }
    let transport_value = required_string(payload, "transport")?;
    let transport = HandoffTransport::from_str(transport_value).ok_or_else(|| {
        error(
            ParentRootReject::HandoffInvalid,
            "invalid handoff transport",
        )
    })?;
    let storage = match required_string(payload, "storage")? {
        "parent-local-file" => HandoffStorage::ParentLocalFile,
        "pipe" => HandoffStorage::Pipe,
        _ => {
            return Err(error(
                ParentRootReject::HandoffInvalid,
                "invalid handoff storage",
            ))
        }
    };
    let mode = match required_string(payload, "mode")? {
        "0600" => HandoffMode::PrivateFile0600,
        "pipe" => HandoffMode::Pipe,
        _ => {
            return Err(error(
                ParentRootReject::HandoffInvalid,
                "invalid handoff mode",
            ))
        }
    };
    let expected_storage = if transport == HandoffTransport::ParentLocalFile {
        HandoffStorage::ParentLocalFile
    } else {
        HandoffStorage::Pipe
    };
    let expected_mode = if transport == HandoffTransport::ParentLocalFile {
        HandoffMode::PrivateFile0600
    } else {
        HandoffMode::Pipe
    };
    if storage != expected_storage
        || mode != expected_mode
        || required_string(payload, "validation")? != "hmac-single-use"
    {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff transport/storage/mode validation is invalid",
        ));
    }
    let audience = NonEmptyTrimmedString::new(required_string(payload, "audience")?)
        .map_err(|_| error(ParentRootReject::HandoffInvalid, "invalid handoff audience"))?;
    let token_root = required_string(payload, "parent_root")?;
    let token_source = optional_string(payload, "source_root")?;
    let token_clone = optional_string(payload, "clone_root")?;
    let issued_at = required_finite_number(payload, "issued_at")?;
    let expires_at = required_finite_number(payload, "expires_at")?;
    let nonce_text = required_string(payload, "nonce")?;
    let nonce = nonce_from_hex(nonce_text)?;
    let payload_digest = Sha256Digest::parse_hex(required_string(payload, "payload_sha256")?)
        .map_err(|_| error(ParentRootReject::HandoffInvalid, "invalid payload digest"))?;

    let secret = session_secret_path(root)?;
    let mut signed = HmacSha256::new_from_slice(&secret).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "handoff authentication failed",
        )
    })?;
    let mut signed_payload = payload.clone();
    signed_payload.remove("payload_sha256");
    // Check payload digest over the body first, then authenticate the complete
    // payload, matching the Python wire format.
    if digest_bytes(&canonical_json(&Value::Object(signed_payload))) != payload_digest {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff payload digest mismatch",
        ));
    }
    signed.update(&canonical_json(&Value::Object(payload.clone())));
    let signature_bytes = decode_hex(signature).ok_or_else(|| {
        error(
            ParentRootReject::HandoffInvalid,
            "invalid handoff signature",
        )
    })?;
    signed.verify_slice(&signature_bytes).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "handoff signature mismatch",
        )
    })?;

    let now = monotonic_now();
    if !(issued_at <= now && now <= expires_at) {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff expired or not yet valid",
        ));
    }
    if audience != request.purpose || canonical_existing(token_root)? != root {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff audience or root mismatch",
        ));
    }
    for (label, token_path, request_path) in [
        ("source_root", token_source.as_ref(), source),
        ("clone_root", token_clone.as_ref(), clone),
    ] {
        match (token_path, request_path) {
            (None, None) => {}
            (Some(_), None) | (None, Some(_)) => {
                return Err(error(
                    ParentRootReject::HandoffInvalid,
                    format!("handoff {label} binding mismatch"),
                ));
            }
            (Some(token_path), Some(request_path)) => {
                let request_path = fs::canonicalize(request_path).map_err(|_| {
                    error(
                        ParentRootReject::HandoffInvalid,
                        "handoff path is unavailable",
                    )
                })?;
                if canonical_existing(token_path)? != request_path {
                    return Err(error(
                        ParentRootReject::HandoffInvalid,
                        format!("handoff {label} binding mismatch"),
                    ));
                }
            }
        }
    }

    with_locked_state_path(root, false, |state, file| {
        let key = encode_hex(nonce.as_bytes());
        let expiry = state.get(&key).copied().ok_or_else(|| {
            error(
                ParentRootReject::HandoffInvalid,
                "unknown or replayed handoff nonce",
            )
        })?;
        if expiry < now {
            return Err(error(
                ParentRootReject::HandoffInvalid,
                "handoff nonce expired",
            ));
        }
        state.remove(&key).ok_or_else(|| {
            error(
                ParentRootReject::HandoffInvalid,
                "handoff nonce changed while locked",
            )
        })?;
        write_locked_state(file, state)?;
        Ok(())
    })?;

    Ok(VerifiedChildHandoff {
        token_version: HANDOFF_SCHEMA.into(),
        audience,
        issued_at,
        expires_at,
        nonce,
        payload_sha256: payload_digest,
        storage,
        mode,
        validation: "hmac-single-use".into(),
        transport,
        token_digest: token.digest(),
    })
}

fn required_string<'a>(
    payload: &'a Map<String, Value>,
    key: &str,
) -> Result<&'a str, AuthorityError> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| error(ParentRootReject::HandoffInvalid, "invalid handoff value"))
}

fn optional_string<'a>(
    payload: &'a Map<String, Value>,
    key: &str,
) -> Result<Option<&'a str>, AuthorityError> {
    match payload.get(key) {
        Some(Value::Null) => Ok(None),
        Some(Value::String(value)) if !value.is_empty() => Ok(Some(value)),
        _ => Err(error(
            ParentRootReject::HandoffInvalid,
            "invalid handoff path value",
        )),
    }
}

fn required_finite_number(payload: &Map<String, Value>, key: &str) -> Result<f64, AuthorityError> {
    payload
        .get(key)
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite())
        .ok_or_else(|| {
            error(
                ParentRootReject::HandoffInvalid,
                "invalid handoff timestamp",
            )
        })
}

fn canonical_existing(path: &str) -> Result<PathBuf, AuthorityError> {
    fs::canonicalize(path).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "handoff path is unavailable",
        )
    })
}

fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if value.len() % 2 != 0 {
        return None;
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let high = hex(pair[0])?;
            let low = hex(pair[1])?;
            Some((high << 4) | low)
        })
        .collect()
}

fn hex(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

fn sign_payload(payload: &Map<String, Value>, secret: &[u8]) -> Result<String, AuthorityError> {
    let mut signer = HmacSha256::new_from_slice(secret).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot initialize handoff signer",
        )
    })?;
    signer.update(&canonical_json(&Value::Object(payload.clone())));
    Ok(encode_hex(&signer.finalize().into_bytes()))
}

fn session_secret(root: &PhysicalRoot, create: bool) -> Result<Vec<u8>, AuthorityError> {
    let key = load_secret(root, create)?;
    let boot_id = fs::read_to_string("/proc/sys/kernel/random/boot_id").map_err(|_| {
        error(
            ParentRootReject::UnsupportedPlatform,
            "Linux boot identity is unavailable",
        )
    })?;
    let boot_id = boot_id.trim();
    if boot_id.is_empty() {
        return Err(error(
            ParentRootReject::UnsupportedPlatform,
            "Linux boot identity is empty",
        ));
    }
    let mut signer = HmacSha256::new_from_slice(&key).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot initialize session key",
        )
    })?;
    signer.update(boot_id.as_bytes());
    Ok(signer.finalize().into_bytes().to_vec())
}

fn session_secret_path(root: &Path) -> Result<Vec<u8>, AuthorityError> {
    let physical = open_physical_root(root, ParentRootReject::HandoffInvalid)?;
    session_secret(&physical, false)
}

fn load_secret(root: &PhysicalRoot, create: bool) -> Result<Vec<u8>, AuthorityError> {
    let directory = open_handoff_dir(root, create)?;
    if create {
        let mut secret = [0_u8; 32];
        getrandom::getrandom(&mut secret).map_err(|_| {
            error(
                ParentRootReject::UnsupportedPlatform,
                "operating-system handoff-secret generation is unavailable",
            )
        })?;
        create_private_file(&directory, "secret", &secret)?;
    }
    let mut options = OpenOptions::new();
    options.read(true).follow(FollowSymlinks::No);
    let file = directory.open_with("secret", &options).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "parent-local handoff secret is missing or unsafe",
        )
    })?;
    let metadata = file.metadata().map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot inspect handoff secret",
        )
    })?;
    if !metadata.file_type().is_file() || metadata.mode() & 0o077 != 0 {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff secret is not private",
        ));
    }
    let mut raw = Vec::new();
    file.take(4096).read_to_end(&mut raw).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot read handoff secret",
        )
    })?;
    if raw.len() < 32 {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "handoff secret is too short",
        ));
    }
    Ok(raw)
}

fn open_handoff_dir(root: &PhysicalRoot, create: bool) -> Result<Dir, AuthorityError> {
    let mut directory = root.directory.try_clone().map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot clone parent directory capability",
        )
    })?;
    for component in [".agent-canon", "handoff"] {
        match directory.open_dir_nofollow(component) {
            Ok(child) => directory = child,
            Err(error_value) if create && error_value.kind() == std::io::ErrorKind::NotFound => {
                let mut builder = DirBuilder::new();
                builder.mode(0o700);
                match directory.create_dir_with(component, &builder) {
                    Ok(()) => {}
                    Err(error_value) if error_value.kind() == std::io::ErrorKind::AlreadyExists => {
                    }
                    Err(_) => {
                        return Err(error(
                            ParentRootReject::RootRaceDetected,
                            "handoff directory changed during creation",
                        ));
                    }
                }
                directory = directory.open_dir_nofollow(component).map_err(|_| {
                    error(
                        ParentRootReject::SymlinkEscape,
                        "handoff directory is not a physical directory",
                    )
                })?;
            }
            Err(error_value) if error_value.kind() == std::io::ErrorKind::NotFound => {
                return Err(error(
                    ParentRootReject::HandoffInvalid,
                    "parent-local handoff state is missing",
                ));
            }
            Err(_) => {
                return Err(error(
                    ParentRootReject::SymlinkEscape,
                    "handoff directory contains a symlink or unsafe component",
                ));
            }
        }
    }
    Ok(directory)
}

fn create_private_file(directory: &Dir, name: &str, bytes: &[u8]) -> Result<(), AuthorityError> {
    let mut options = OpenOptions::new();
    options
        .write(true)
        .create_new(true)
        .mode(0o600)
        .follow(FollowSymlinks::No);
    match directory.open_with(name, &options) {
        Ok(mut file) => {
            file.set_permissions(Permissions::from_mode(0o600))
                .map_err(|_| {
                    error(
                        ParentRootReject::HandoffInvalid,
                        "cannot secure handoff state file",
                    )
                })?;
            file.write_all(bytes).map_err(|_| {
                error(
                    ParentRootReject::HandoffInvalid,
                    "cannot write handoff state file",
                )
            })?;
            file.sync_all().map_err(|_| {
                error(
                    ParentRootReject::HandoffInvalid,
                    "cannot sync handoff state file",
                )
            })?;
            Ok(())
        }
        Err(error_value) if error_value.kind() == std::io::ErrorKind::AlreadyExists => Ok(()),
        Err(_) => Err(error(
            ParentRootReject::HandoffInvalid,
            "cannot create private handoff state file",
        )),
    }
}

fn with_locked_state<R>(
    root: &PhysicalRoot,
    create: bool,
    operation: impl FnOnce(
        &mut BTreeMap<String, f64>,
        &mut cap_std::fs::File,
    ) -> Result<R, AuthorityError>,
) -> Result<R, AuthorityError> {
    let directory = open_handoff_dir(root, create)?;
    if create {
        create_private_file(&directory, "nonces.json", b"{}")?;
    }
    with_locked_state_file(&directory, operation)
}

fn with_locked_state_path<R>(
    root: &Path,
    create: bool,
    operation: impl FnOnce(
        &mut BTreeMap<String, f64>,
        &mut cap_std::fs::File,
    ) -> Result<R, AuthorityError>,
) -> Result<R, AuthorityError> {
    let physical = open_physical_root(root, ParentRootReject::HandoffInvalid)?;
    with_locked_state(&physical, create, operation)
}

fn with_locked_state_file<R>(
    directory: &Dir,
    operation: impl FnOnce(
        &mut BTreeMap<String, f64>,
        &mut cap_std::fs::File,
    ) -> Result<R, AuthorityError>,
) -> Result<R, AuthorityError> {
    let mut options = OpenOptions::new();
    options.read(true).write(true).follow(FollowSymlinks::No);
    let mut file = directory.open_with("nonces.json", &options).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot open nonce receipt",
        )
    })?;
    if !file
        .metadata()
        .map_err(|_| {
            error(
                ParentRootReject::HandoffInvalid,
                "cannot inspect nonce receipt",
            )
        })?
        .file_type()
        .is_file()
    {
        return Err(error(
            ParentRootReject::HandoffInvalid,
            "nonce receipt is not a regular file",
        ));
    }
    file.set_permissions(Permissions::from_mode(0o600))
        .map_err(|_| {
            error(
                ParentRootReject::HandoffInvalid,
                "cannot secure nonce receipt",
            )
        })?;
    rustix::fs::flock(&file, rustix::fs::FlockOperation::LockExclusive).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot lock nonce receipt",
        )
    })?;

    let operation_result = (|| {
        file.seek(SeekFrom::Start(0)).map_err(|_| {
            error(
                ParentRootReject::HandoffInvalid,
                "cannot seek nonce receipt",
            )
        })?;
        let mut raw = Vec::new();
        (&mut file)
            .take(1 << 20)
            .read_to_end(&mut raw)
            .map_err(|_| {
                error(
                    ParentRootReject::HandoffInvalid,
                    "cannot read nonce receipt",
                )
            })?;
        let parsed = strict_json(&raw, ParentRootReject::HandoffInvalid)?;
        let object = parsed.as_object().ok_or_else(|| {
            error(
                ParentRootReject::HandoffInvalid,
                "invalid nonce receipt state",
            )
        })?;
        let mut state = BTreeMap::new();
        for (nonce, expiration) in object {
            let expiration = expiration
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    error(
                        ParentRootReject::HandoffInvalid,
                        "invalid nonce receipt timestamp",
                    )
                })?;
            state.insert(nonce.clone(), expiration);
        }
        let result = operation(&mut state, &mut file)?;
        Ok(result)
    })();

    let unlock_result = rustix::fs::flock(&file, rustix::fs::FlockOperation::Unlock);
    match (operation_result, unlock_result) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error_value), _) => Err(error_value),
        (Ok(_), Err(_)) => Err(error(
            ParentRootReject::HandoffInvalid,
            "cannot unlock nonce receipt",
        )),
    }
}

fn write_locked_state(
    file: &mut cap_std::fs::File,
    state: &BTreeMap<String, f64>,
) -> Result<(), AuthorityError> {
    let mut value = Map::new();
    for (nonce, expires) in state {
        value.insert(nonce.clone(), number_from_f64(*expires)?);
    }
    let bytes = canonical_json(&Value::Object(value));
    file.seek(SeekFrom::Start(0)).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot seek nonce receipt",
        )
    })?;
    file.set_len(0).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot truncate nonce receipt",
        )
    })?;
    file.write_all(&bytes).map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot write nonce receipt",
        )
    })?;
    file.sync_all().map_err(|_| {
        error(
            ParentRootReject::HandoffInvalid,
            "cannot sync nonce receipt",
        )
    })?;
    Ok(())
}

fn error(reject: ParentRootReject, detail: impl Into<String>) -> AuthorityError {
    AuthorityError::new(reject, detail)
}

#[cfg(test)]
mod parent_file_tests {
    use super::*;
    use crate::authority::{
        AttestationRequest, AttestedParent, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
    };
    use std::io::{self, Write};
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ROOT: AtomicUsize = AtomicUsize::new(0);

    struct GitTempRoot(PathBuf);

    impl GitTempRoot {
        fn new() -> Self {
            let id = NEXT_ROOT.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "agent-canon-authority-effects-{}-{id}",
                std::process::id()
            ));
            fs::create_dir_all(&path).expect("create temporary Git root");
            let path = fs::canonicalize(path).expect("canonicalize temporary Git root");
            let init = Command::new("git")
                .args(["init", "-q", "-b", "main"])
                .arg(&path)
                .status()
                .expect("initialize temporary Git root");
            assert!(init.success());
            let root = path.to_str().expect("temporary root is UTF-8");
            let remote = Command::new("git")
                .args([
                    "-C",
                    root,
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/authority-effects.git",
                ])
                .status()
                .expect("set fixture Git remote");
            assert!(remote.success());
            let commit = Command::new("git")
                .args([
                    "-C",
                    root,
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "fixture",
                ])
                .status()
                .expect("commit fixture Git root");
            assert!(commit.success());
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for GitTempRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn attested_fixture() -> (GitTempRoot, AttestedParent) {
        let root = GitTempRoot::new();
        let request = AttestationRequest {
            cwd: root.path().to_path_buf(),
            explicit_root: Some(root.path().to_path_buf()),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new("parent-file-unit").unwrap(),
            nonce: Nonce128::generate().unwrap(),
        };
        let attested = ParentRootAttestor::new()
            .attest(&request)
            .expect("attest temporary Git root");
        (root, attested)
    }

    struct ShortFileWriter<'a> {
        file: &'a mut cap_std::fs::File,
        max_write: usize,
    }

    impl Write for ShortFileWriter<'_> {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.file.write(&bytes[..bytes.len().min(self.max_write)])
        }

        fn flush(&mut self) -> io::Result<()> {
            self.file.flush()
        }
    }

    struct NoProgressWriter;

    impl Write for NoProgressWriter {
        fn write(&mut self, _: &[u8]) -> io::Result<usize> {
            Ok(0)
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn atomic_replace_handles_short_writes_and_cleans_zero_progress() {
        let (root, attested) = attested_fixture();
        let purpose = NonEmptyTrimmedString::new("short-write").unwrap();
        let receipt = attested
            .resolve_parent_owned_path(Path::new("short/result.txt"), purpose.clone())
            .unwrap();
        let payload = b"short-write-payload";
        let published = atomic_replace_with_hooks(
            &attested,
            &receipt,
            payload,
            FileMode::Private0600,
            |file, bytes| {
                let mut writer = ShortFileWriter { file, max_write: 2 };
                write_all_progress(&mut writer, bytes)
            },
            |directory, name| directory.remove_file(name),
        )
        .expect("short writes complete through write_all");
        assert_eq!(
            attested.read_parent_owned_file(&published).unwrap(),
            payload
        );

        let zero_receipt = attested
            .resolve_parent_owned_path(Path::new("zero/result.txt"), purpose)
            .unwrap();
        let rejected = atomic_replace_with_hooks(
            &attested,
            &zero_receipt,
            b"no progress",
            FileMode::Private0600,
            |_file, bytes| {
                let mut writer = NoProgressWriter;
                write_all_progress(&mut writer, bytes)
            },
            |directory, name| directory.remove_file(name),
        )
        .expect_err("zero-progress write fails closed");
        assert_eq!(rejected.reject, ParentRootReject::RootRaceDetected);
        assert_eq!(fs::read_dir(root.path().join("zero")).unwrap().count(), 0);
    }

    #[test]
    fn atomic_replace_surfaces_cleanup_failure_after_publication() {
        let (root, attested) = attested_fixture();
        let purpose = NonEmptyTrimmedString::new("cleanup-failure").unwrap();
        let receipt = attested
            .resolve_parent_owned_path(Path::new("cleanup/result.txt"), purpose.clone())
            .unwrap();
        let rejected = atomic_replace_with_hooks(
            &attested,
            &receipt,
            b"published-before-cleanup-error",
            FileMode::Private0600,
            |file, bytes| write_all_progress(file, bytes),
            |_directory, _name| {
                Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "injected cleanup failure",
                ))
            },
        )
        .expect_err("cleanup failure remains observable after rename");
        assert_eq!(rejected.reject, ParentRootReject::RootRaceDetected);
        assert!(rejected.detail().contains("cleanup failed"));
        assert_eq!(
            fs::read(root.path().join("cleanup/result.txt")).unwrap(),
            b"published-before-cleanup-error"
        );

        let published = attested
            .resolve_parent_owned_path(Path::new("cleanup/result.txt"), purpose)
            .unwrap();
        assert_eq!(
            attested.read_parent_owned_file(&published).unwrap(),
            b"published-before-cleanup-error"
        );
        assert_eq!(
            fs::read_dir(root.path().join("cleanup")).unwrap().count(),
            1,
            "rename consumes the temporary entry even when cleanup reports failure"
        );
    }
}

#[cfg(test)]
mod strict_json_tests {
    use super::*;

    #[test]
    fn raw_number_tokens_and_private_number_looking_objects_keep_their_json_kinds() {
        let numeric = strict_json(br#"{"issued_at":1.25}"#, ParentRootReject::HandoffInvalid)
            .expect("parse numeric timestamp");
        assert_eq!(numeric["issued_at"].as_f64(), Some(1.25));

        let literal_object = strict_json(
            br#"{"$serde_json::private::Number":"1"}"#,
            ParentRootReject::HandoffInvalid,
        )
        .expect("preserve literal private-number-looking object");
        assert_eq!(
            literal_object,
            serde_json::json!({"$serde_json::private::Number": "1"})
        );
    }

    #[test]
    fn raw_object_parser_rejects_nested_duplicate_keys() {
        assert!(strict_json(
            br#"{"outer":{"value":1,"value":2}}"#,
            ParentRootReject::HandoffInvalid,
        )
        .is_err());
    }
}
