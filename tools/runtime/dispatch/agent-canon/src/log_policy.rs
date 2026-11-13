// @dependency-start
// contract implementation
// responsibility Reads and validates the existing fixed legacy log inventory without changing its data.
// upstream design ../../../../../documents/design/runtime-log-repository-lifecycle.md owns RL-009..RL-012 evidence
// downstream test ../../../../../tests/agent_tools/test_agent_canon_log_policy.py exercises deterministic fixtures
// @dependency-end

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::path::Path;
#[cfg(target_os = "linux")]
use std::process::Command;

const REMOTE: &str = "https://github.com/iwashita-nozomu/agent-canon-log.git";
const COMMIT: &str = "9f10130184539beaebe8991bbcfb5665d476fbe5";
const BLOB: &str = "ad96c36a281ccea58bcd38166ae78ac1a61ad57362de57fdf5e92c82a0aa9d02";
#[cfg(target_os = "linux")]
const INVENTORY: &str = "docs/migration/legacy-inventory.json";
const BLOCKERS: &[&str] = &[
    "A source-remote authority manifest is required before any legacy branch can be migrated.",
    "Migration must be a dry-run manifest, explicit authority, and exact remote readback.",
    "This inventory performs no branch deletion, merge, rewrite, or data migration.",
];
type Result<T> = std::result::Result<T, &'static str>;
fn hex(value: Option<&Value>, length: usize) -> bool {
    value.and_then(Value::as_str).is_some_and(|value| {
        value.len() == length
            && value
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
    })
}
fn require(condition: bool, code: &'static str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(code)
    }
}
fn object<'a>(value: &'a Value, code: &'static str) -> Result<&'a serde_json::Map<String, Value>> {
    value.as_object().ok_or(code)
}
fn string<'a>(value: &'a Value, code: &'static str) -> Result<&'a str> {
    value.as_str().filter(|value| !value.is_empty()).ok_or(code)
}
fn validate(raw: &[u8], expected: Option<&str>) -> Result<String> {
    let digest = format!("{:x}", Sha256::digest(raw));
    require(
        expected.is_none_or(|value| value == digest),
        "policy_inventory_blob_digest_mismatch",
    )?;
    let payload: Value =
        serde_json::from_slice(raw).map_err(|_| "policy_inventory_json_invalid")?;
    object(&payload, "policy_inventory_json_invalid")?;
    for (field, value, code) in [
        (
            "schema",
            "agent-canon-log-legacy-inventory.v1",
            "policy_inventory_schema_mismatch",
        ),
        (
            "policy_schema",
            "agent-canon-log-policy.v1",
            "policy_inventory_policy_schema_mismatch",
        ),
        ("mode", "read_only", "policy_inventory_not_read_only"),
        ("remote", REMOTE, "policy_inventory_remote_mismatch"),
    ] {
        require(payload[field] == value, code)?;
    }
    let branches = payload["legacy_branches"]
        .as_array()
        .filter(|values| values.len() == 42)
        .ok_or("policy_inventory_legacy_branch_rows")?;
    let mut names = BTreeSet::new();
    for row in branches {
        object(row, "policy_inventory_branch_row_invalid")?;
        let name = string(&row["branch"], "policy_inventory_branch_name_invalid")?;
        require(
            name.starts_with("logs/") && names.insert(name.to_owned()),
            "policy_inventory_branch_name_invalid",
        )?;
        require(
            row["count"].as_u64().is_some(),
            "policy_inventory_branch_count_invalid",
        )?;
        for (field, length, code) in [
            ("digest", 64, "policy_inventory_branch_digest_invalid"),
            ("head", 40, "policy_inventory_branch_head_invalid"),
            ("tree", 40, "policy_inventory_branch_tree_invalid"),
        ] {
            require(hex(row.get(field), length), code)?;
        }
    }
    require(
        payload["legacy_branch_count"] == 42,
        "policy_inventory_branch_count_mismatch",
    )?;
    let mappings = object(
        &payload["legacy_to_stable"],
        "policy_inventory_mapping_invalid",
    )?;
    require(
        mappings.keys().cloned().collect::<BTreeSet<_>>() == names,
        "policy_inventory_mapping_coverage",
    )?;
    for mapping in mappings.values() {
        object(mapping, "policy_inventory_mapping_row_invalid")?;
        for (field, value, code) in [
            (
                "status",
                "authority_required",
                "policy_inventory_mapping_status",
            ),
            (
                "stable_branch",
                "logs/github.com-iwashita-nozomu-agent-canon-log-b748513d5bba954b360f59d7",
                "policy_inventory_mapping_stable_branch",
            ),
            (
                "reason",
                "source remote supplied for future migration authority; no data moved",
                "policy_inventory_mapping_reason",
            ),
        ] {
            require(mapping[field] == value, code)?;
        }
    }
    let refs = object(
        &payload["remote_log_ref_heads"],
        "policy_inventory_remote_refs_invalid",
    )?;
    require(
        refs.keys().cloned().collect::<BTreeSet<_>>() == names,
        "policy_inventory_remote_ref_coverage",
    )?;
    for value in refs.values() {
        require(
            hex(Some(value), 40),
            "policy_inventory_remote_ref_head_invalid",
        )?;
    }
    require(
        payload["migration_blockers"] == json!(BLOCKERS),
        "policy_inventory_read_only_blockers",
    )?;
    let snapshot = &payload["observation_snapshot"];
    object(snapshot, "policy_inventory_observation_invalid")?;
    require(
        snapshot["remote_log_ref_count"] == 42,
        "policy_inventory_observation_count",
    )?;
    require(
        string(
            &snapshot["observed_at_utc"],
            "policy_inventory_observation_time",
        )?
        .ends_with('Z'),
        "policy_inventory_observation_time",
    )?;
    require(
        hex(snapshot.get("snapshot_id"), 64),
        "policy_inventory_snapshot_id",
    )?;
    let main = &payload["main_legacy_import"];
    object(main, "policy_inventory_main_observation")?;
    require(
        main["count"].as_u64() == Some(26),
        "policy_inventory_main_observation_count",
    )?;
    for (field, length) in [("digest", 64), ("head", 40), ("tree", 40)] {
        require(
            hex(main.get(field), length),
            "policy_inventory_main_observation",
        )?;
    }
    Ok(digest)
}

#[cfg(target_os = "linux")]
fn retrieve(remote: &str, commit: &str) -> Result<Vec<u8>> {
    use crate::authority::{
        AttestationRequest, NonEmptyTrimmedString, Nonce128, ParentRootAttestor,
    };
    use crate::source_mutation::open_root_nofollow;
    use cap_fs_ext::{DirExt, MetadataExt};
    use std::os::fd::AsRawFd;
    use std::path::PathBuf;
    let parent = std::env::var_os("AGENT_CANON_PARENT_ROOT")
        .filter(|value| !value.is_empty())
        .ok_or("policy_inventory_parent_root_required")?;
    let parent = PathBuf::from(parent);
    let attested = ParentRootAttestor::new()
        .attest(&AttestationRequest {
            cwd: parent.clone(),
            explicit_root: Some(parent),
            source_root: None,
            clone_root: None,
            topic_marker: None,
            gitmodules: None,
            owner_evidence: None,
            expected_remote: None,
            expected_module_digest: None,
            child_handoff_token: None,
            purpose: NonEmptyTrimmedString::new("policy-inventory")
                .map_err(|_| "policy_inventory_parent_root_invalid")?,
            nonce: Nonce128::generate().map_err(|_| "policy_inventory_parent_root_invalid")?,
        })
        .map_err(|_| "policy_inventory_parent_root_invalid")?;
    let root = open_root_nofollow(attested.parent_root().path())
        .map_err(|_| "policy_inventory_parent_root_invalid")?;
    let mut directory = root;
    for component in [".agent-canon", "tmp", "policy-inventory"] {
        match directory.create_dir(component) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(_) => return Err("policy_inventory_temp_unavailable"),
        };
        directory = directory
            .open_dir_nofollow(component)
            .map_err(|_| "policy_inventory_temp_unavailable")?;
    }
    let nonce = Nonce128::generate().map_err(|_| "policy_inventory_temp_unavailable")?;
    let name = format!("policy-{}", crate::authority::encode_hex(nonce.as_bytes()));
    directory
        .create_dir(&name)
        .map_err(|_| "policy_inventory_temp_unavailable")?;
    let handle = directory
        .open_dir_nofollow(&name)
        .map_err(|_| "policy_inventory_temp_unavailable")?;
    let identity = handle
        .dir_metadata()
        .map_err(|_| "policy_inventory_temp_unavailable")?;
    let descriptor = PathBuf::from(format!(
        "/proc/{}/fd/{}",
        std::process::id(),
        handle.as_raw_fd()
    ));
    let result = (|| {
        for (args, code) in [
            (vec!["init", "-q"], "policy_inventory_fetch_init_failed"),
            (
                vec!["remote", "add", "origin", remote],
                "policy_inventory_remote_invalid",
            ),
            (
                vec!["fetch", "--no-tags", "--quiet", "origin", commit],
                "policy_inventory_fetch_failed",
            ),
        ] {
            let result = Command::new("git")
                .args(args)
                .current_dir(&descriptor)
                .output()
                .map_err(|_| code)?;
            require(result.status.success(), code)?;
        }
        let result = Command::new("git")
            .args(["show", &format!("{commit}:{INVENTORY}")])
            .current_dir(&descriptor)
            .output()
            .map_err(|_| "policy_inventory_blob_missing")?;
        require(result.status.success(), "policy_inventory_blob_missing")?;
        Ok(result.stdout)
    })();
    attested
        .verify_live_identity()
        .map_err(|_| "policy_inventory_target_identity_changed")?;
    let observed = directory
        .symlink_metadata(&name)
        .map_err(|_| "policy_inventory_target_identity_changed")?;
    require(
        observed.is_dir() && observed.dev() == identity.dev() && observed.ino() == identity.ino(),
        "policy_inventory_target_identity_changed",
    )?;
    directory
        .remove_dir_all(&name)
        .map_err(|_| "policy_inventory_cleanup_failed")?;
    result
}
#[cfg(not(target_os = "linux"))]
fn retrieve(_: &str, _: &str) -> Result<Vec<u8>> {
    Err("policy_inventory_parent_root_unsupported")
}

pub fn run(args: &[String]) -> i32 {
    const USAGE:&str="usage: agent-canon check-agent-canon-log-policy [--input PATH|--remote URL] [--commit SHA]";
    let mut input = None;
    let mut remote = REMOTE;
    let mut commit = COMMIT;
    let mut explicit_remote = false;
    let mut index = 0;
    while index < args.len() {
        let name = args[index].as_str();
        if ["-h", "--help"].contains(&name) {
            println!("{USAGE}");
            return 0;
        }
        if index + 1 == args.len() {
            eprintln!("{USAGE}");
            return 2;
        }
        match name {
            "--input" => input = Some(Path::new(&args[index + 1])),
            "--remote" => {
                remote = &args[index + 1];
                explicit_remote = true;
            }
            "--commit" => commit = &args[index + 1],
            _ => {
                eprintln!("{USAGE}");
                return 2;
            }
        }
        index += 2;
    }
    if input.is_some() && explicit_remote {
        eprintln!("{USAGE}");
        return 2;
    }
    let result = (|| {
        let bytes = if let Some(input) = input {
            std::fs::read(input).map_err(|_| "policy_inventory_input_unavailable")?
        } else {
            retrieve(remote, commit)?
        };
        validate(
            &bytes,
            if input.is_none() && commit == COMMIT {
                Some(BLOB)
            } else {
                None
            },
        )
    })();
    match result {
        Ok(digest) => {
            println!("AGENT_CANON_LOG_POLICY_COMMIT={}\nAGENT_CANON_LOG_POLICY_BLOB_SHA256={digest}\nAGENT_CANON_LOG_POLICY_LEGACY_BRANCH_ROWS=42\nAGENT_CANON_LOG_POLICY_MAPPINGS=42\nAGENT_CANON_LOG_POLICY_REMOTE_LOG_REFS=42\nAGENT_CANON_LOG_POLICY_READ_ONLY_BLOCKERS=3\nAGENT_CANON_LOG_POLICY_MAIN_OBSERVATION_COUNT=26\nAGENT_CANON_LOG_POLICY_VALIDATION=pass",if input.is_some(){"deterministic-fixture"}else{commit});
            0
        }
        Err(code) => {
            println!(
                "AGENT_CANON_LOG_POLICY_ERROR_CODE={code}\nAGENT_CANON_LOG_POLICY_VALIDATION=fail"
            );
            1
        }
    }
}
