// @dependency-start
// contract implementation
// responsibility Composes the existing strict NVIDIA and lock owners for direct GPU commands.
// upstream implementation execution_resource_plan.rs owns NVIDIA observations and reservations
// upstream design ../../../../../documents/experiments/gpu-direct-command.md owns the opt-in direct command contract
// downstream test ../tests/direct_gpu_native.rs verifies public admission and execution behavior
// @dependency-end

use crate::execution_resource_plan::{Failure, NvidiaListEvidence};
#[cfg(target_os = "linux")]
use crate::execution_resource_plan::{
    GpuUnitDisposition, ProcessOccupancyEvidence, ResourceObservation,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::sync::LazyLock;

type Result<T> = std::result::Result<T, Failure>;
static UUID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(GPU|MIG)-[A-Za-z0-9-]+$").unwrap());

fn failure(code: &str, message: &str) -> Failure {
    Failure {
        code: code.into(),
        message: message.into(),
        details: BTreeMap::new(),
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CandidateAllocation {
    pub candidate_ids: Vec<String>,
    pub source: String,
    pub inventory_fingerprint: String,
    pub physical_uuids: Vec<String>,
    pub mig_uuids: Vec<String>,
    pub mig_parent_by_uuid: BTreeMap<String, String>,
}

#[derive(Clone, Debug)]
pub struct DirectGpuCommandRequest {
    pub argv: Vec<String>,
    pub cwd: PathBuf,
    pub environment: BTreeMap<String, String>,
    pub candidate_allocation: CandidateAllocation,
    pub gpu_count: usize,
    pub minimum_free_memory_bytes: u64,
    pub output_dir: PathBuf,
    pub runtime_root: PathBuf,
    pub lock_root: PathBuf,
    pub descendant_poll_seconds: f64,
}
impl DirectGpuCommandRequest {
    pub fn validate(&self) -> Result<()> {
        if self.argv.is_empty()
            || self
                .argv
                .iter()
                .any(|token| token.is_empty() || token.contains('\0'))
        {
            return Err(failure(
                "gpu_command_argv_invalid",
                "direct command argv requires non-empty NUL-free strings",
            ));
        }
        if self.gpu_count == 0 {
            return Err(failure(
                "gpu_request_cardinality_invalid",
                "direct GPU command count must be positive",
            ));
        }
        if self.gpu_count > self.candidate_allocation.candidate_ids.len() {
            return Err(failure(
                "gpu_candidate_cardinality_insufficient",
                "candidate set is smaller than requested count",
            ));
        }
        if self.descendant_poll_seconds <= 0.0 {
            return Err(failure(
                "gpu_command_request_invalid",
                "descendant poll interval must be positive",
            ));
        }
        for path in [
            &self.cwd,
            &self.output_dir,
            &self.runtime_root,
            &self.lock_root,
        ] {
            crate::execution_resource_plan::AbsolutePosixPath::parse(&path.to_string_lossy())?;
        }
        if self.runtime_root
            != std::path::Path::new(crate::execution_resource_plan::HOST_RUNTIME_ROOT)
            || self.lock_root != std::path::Path::new("/var/lib/agent-canon/runtime/locks")
        {
            return Err(failure(
                "gpu_lock_namespace_not_canonical",
                "direct commands require canonical runtime and lock root",
            ));
        }
        if self
            .environment
            .iter()
            .any(|(key, value)| key.is_empty() || key.contains(['\0', '=']) || value.contains('\0'))
        {
            return Err(failure(
                "gpu_command_environment_invalid",
                "direct command environment requires NUL-free string keys and values",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FrozenDirectGpuCommandPlan {
    pub schema_version: String,
    pub plan_id: String,
    pub plan_fingerprint: String,
    pub argv: Vec<String>,
    pub cwd: String,
    pub candidate_ids: Vec<String>,
    pub selected_ids: Vec<String>,
    pub candidate_source: String,
    pub candidate_inventory_fingerprint: String,
    pub candidate_mig_parent_by_uuid: BTreeMap<String, String>,
    pub requested_gpu_count: usize,
    pub minimum_free_memory_bytes: u64,
    pub selected_free_memory_bytes: BTreeMap<String, u64>,
    pub initial_unit_states: BTreeMap<String, String>,
    pub final_unit_states: BTreeMap<String, String>,
    pub initial_observation_fingerprint: String,
    pub final_observation_fingerprint: String,
    pub initial_event_id: String,
    pub final_event_id: String,
    pub reservation_fingerprint: String,
    pub reservation_ids: Vec<String>,
    pub lock_identities: Vec<(u64, u64)>,
    pub admission_fingerprint: String,
    pub base_environment_fingerprint: String,
    pub environment_key_witness: serde_json::Value,
    pub output_dir: String,
    pub unknown_initial_ids: Vec<String>,
    pub unknown_final_ids: Vec<String>,
}
impl FrozenDirectGpuCommandPlan {
    pub fn validate(&self) -> Result<()> {
        if self.schema_version != "agentcanon-gpu-command-plan/v1"
            || self.candidate_inventory_fingerprint.is_empty()
        {
            return Err(failure(
                "gpu_command_plan_invalid",
                "direct GPU plan schema and inventory identity are required",
            ));
        }
        if self.candidate_ids.windows(2).any(|pair| pair[0] > pair[1])
            || self.selected_ids.windows(2).any(|pair| pair[0] > pair[1])
            || self
                .selected_ids
                .iter()
                .any(|uuid| !self.candidate_ids.contains(uuid))
        {
            return Err(failure(
                "gpu_command_plan_invalid",
                "candidate and selected UUIDs require stable subset order",
            ));
        }
        if self.selected_ids.len() != self.requested_gpu_count
            || self.reservation_ids.len() != self.selected_ids.len()
            || self.lock_identities.len() != self.selected_ids.len()
        {
            return Err(failure(
                "gpu_command_plan_invalid",
                "selected, reservation and lock counts must match request",
            ));
        }
        if self.reservation_ids.iter().collect::<BTreeSet<_>>().len() != self.reservation_ids.len()
            || self.lock_identities.iter().collect::<BTreeSet<_>>().len()
                != self.lock_identities.len()
        {
            return Err(failure(
                "gpu_command_plan_invalid",
                "reservation and lock identities must be unique",
            ));
        }
        if self.initial_event_id == self.final_event_id {
            return Err(failure(
                "gpu_command_plan_invalid",
                "post-lock observation must use a fresh event ID",
            ));
        }
        if self
            .selected_free_memory_bytes
            .keys()
            .collect::<BTreeSet<_>>()
            != self.selected_ids.iter().collect::<BTreeSet<_>>()
            || self
                .selected_free_memory_bytes
                .values()
                .any(|value| *value < self.minimum_free_memory_bytes)
        {
            return Err(failure(
                "gpu_command_plan_invalid",
                "selected memory evidence must cover the exact requested UUID set",
            ));
        }
        if self.selected_ids.iter().any(|uuid| {
            self.final_unit_states.get(uuid).map(String::as_str) != Some("FREE")
                || self.unknown_initial_ids.contains(uuid)
                || self.unknown_final_ids.contains(uuid)
        }) {
            return Err(failure(
                "gpu_command_plan_invalid",
                "selected UUIDs must be FREE in post-lock observation and cannot be UNKNOWN",
            ));
        }
        let mut payload = serde_json::to_value(self)
            .map_err(|error| failure("gpu_command_plan_invalid", &error.to_string()))?;
        payload
            .as_object_mut()
            .expect("plan serializes as object")
            .remove("plan_fingerprint");
        let bytes = crate::artifacts::artifact_identity::canonical_json_ascii_bytes(&payload)
            .map_err(|error| failure("gpu_command_plan_invalid", &error.to_string()))?;
        use sha2::{Digest, Sha256};
        if self.plan_fingerprint != format!("{:x}", Sha256::digest(bytes)) {
            return Err(failure(
                "gpu_command_plan_invalid",
                "direct GPU plan fingerprint mismatch",
            ));
        }
        Ok(())
    }
}

fn visibility_restriction(environment: &BTreeMap<String, String>) -> Result<Option<Vec<String>>> {
    let mut exact = Vec::new();
    for key in ["CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"] {
        let Some(raw) = environment.get(key) else {
            continue;
        };
        let raw = crate::python_text::python_strip(raw);
        if ["all", ""].contains(&raw.to_ascii_lowercase().as_str()) {
            continue;
        }
        if ["none", "void"].contains(&raw.to_ascii_lowercase().as_str()) {
            return Err(failure(
                "gpu_scheduler_uuid_visibility_unproven",
                "direct GPU execution cannot widen explicitly empty visibility",
            ));
        }
        let mut tokens = raw
            .split(',')
            .map(crate::python_text::python_strip)
            .map(str::to_owned)
            .collect::<Vec<_>>();
        if tokens.iter().any(String::is_empty) {
            return Err(failure(
                "gpu_scheduler_uuid_visibility_unproven",
                "GPU visibility must be an exact comma-separated UUID set",
            ));
        }
        if tokens.iter().any(|uuid| !UUID.is_match(uuid)) {
            return Err(failure(
                "gpu_candidate_uuid_invalid",
                "GPU candidates must use complete opaque UUIDs",
            ));
        }
        let unique = tokens.iter().collect::<BTreeSet<_>>();
        if unique.len() != tokens.len() {
            return Err(failure(
                "gpu_scheduler_uuid_visibility_ambiguous",
                "GPU visibility must not repeat UUIDs",
            ));
        }
        tokens.sort();
        exact.push(tokens);
    }
    if exact.is_empty() {
        return Ok(None);
    }
    if exact.iter().skip(1).any(|value| *value != exact[0]) {
        return Err(failure(
            "gpu_scheduler_uuid_visibility_conflict",
            "CUDA and NVIDIA exact UUID sets disagree",
        ));
    }
    Ok(Some(exact.remove(0)))
}

pub fn candidate_allocation(
    environment: &BTreeMap<String, String>,
    explicit: &[String],
    inventory: &NvidiaListEvidence,
) -> Result<CandidateAllocation> {
    if environment
        .iter()
        .any(|(key, value)| key.is_empty() || key.contains(['\0', '=']) || value.contains('\0'))
    {
        return Err(failure(
            "gpu_command_environment_invalid",
            "direct command environment requires NUL-free string keys and values",
        ));
    }
    let parents = inventory
        .joins
        .iter()
        .map(|join| join.parent_uuid.as_str())
        .collect::<BTreeSet<_>>();
    let mut physical = inventory.physical_uuids.clone();
    physical.sort();
    let mut mig = inventory.mig_uuids.clone();
    mig.sort();
    let leaves = physical
        .iter()
        .filter(|uuid| !parents.contains(uuid.as_str()))
        .chain(&mig)
        .cloned()
        .collect::<Vec<_>>();
    let restriction = visibility_restriction(environment)?;
    let (requested, source) = if !explicit.is_empty() {
        let mut requested = explicit.to_vec();
        requested.sort();
        if requested.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err(failure(
                "gpu_candidate_uuid_duplicate",
                "explicit GPU candidates must be unique",
            ));
        }
        if requested.iter().any(|uuid| !UUID.is_match(uuid)) {
            return Err(failure(
                "gpu_candidate_uuid_invalid",
                "GPU candidates must use complete opaque UUIDs",
            ));
        }
        (requested, "cli")
    } else if let Some(restriction) = &restriction {
        (restriction.clone(), "scheduler_environment")
    } else {
        (leaves.clone(), "strict_nvidia_inventory")
    };
    if requested.iter().any(|uuid| !leaves.contains(uuid)) {
        return Err(failure(
            "gpu_candidate_uuid_not_executable_leaf",
            "candidate UUIDs must be executable leaves in strict NVIDIA topology",
        ));
    }
    if restriction
        .as_ref()
        .is_some_and(|restriction| requested.iter().any(|uuid| !restriction.contains(uuid)))
    {
        return Err(failure(
            "gpu_candidate_outside_scheduler_visibility",
            "explicit GPU candidates cannot widen caller visibility",
        ));
    }
    if requested.is_empty() {
        return Err(failure(
            "gpu_candidate_set_empty",
            "direct GPU command requires non-empty candidates",
        ));
    }
    Ok(CandidateAllocation {
        candidate_ids: requested,
        source: source.into(),
        inventory_fingerprint: inventory.evidence_fingerprint.clone(),
        physical_uuids: physical,
        mig_uuids: mig,
        mig_parent_by_uuid: inventory
            .joins
            .iter()
            .map(|join| (join.mig_uuid.clone(), join.parent_uuid.clone()))
            .collect(),
    })
}

#[cfg(target_os = "linux")]
fn eligible_ids(
    request: &DirectGpuCommandRequest,
    observation: &ResourceObservation,
    occupancy: &ProcessOccupancyEvidence,
) -> Vec<String> {
    request
        .candidate_allocation
        .candidate_ids
        .iter()
        .filter(|uuid| {
            occupancy.unit_states.get(*uuid) == Some(&GpuUnitDisposition::Free)
                && observation
                    .free_memory_bytes
                    .get(*uuid)
                    .is_some_and(|memory| *memory >= request.minimum_free_memory_bytes)
        })
        .cloned()
        .collect()
}
#[cfg(target_os = "linux")]
fn validate_candidate_topology(
    request: &DirectGpuCommandRequest,
    observation: &ResourceObservation,
) -> Result<()> {
    let inventory = observation.nvidia_inventory.as_ref().ok_or_else(|| {
        failure(
            "gpu_inventory_unproven",
            "direct GPU admission requires strict NVIDIA inventory",
        )
    })?;
    let expected = request
        .candidate_allocation
        .candidate_ids
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    if observation.caller_allocated_ids != expected {
        return Err(failure(
            "gpu_candidate_visibility_raced",
            "resource observation caller visibility differs from frozen candidates",
        ));
    }
    let parents = inventory
        .joins
        .iter()
        .map(|join| (join.mig_uuid.clone(), join.parent_uuid.clone()))
        .collect::<BTreeMap<_, _>>();
    let mut physical = inventory.physical_uuids.clone();
    physical.sort();
    let mut mig = inventory.mig_uuids.clone();
    mig.sort();
    let parent_ids = parents.values().collect::<BTreeSet<_>>();
    let leaves = physical
        .iter()
        .filter(|uuid| !parent_ids.contains(uuid))
        .chain(&mig)
        .cloned()
        .collect::<BTreeSet<_>>();
    if physical != request.candidate_allocation.physical_uuids
        || mig != request.candidate_allocation.mig_uuids
        || parents != request.candidate_allocation.mig_parent_by_uuid
        || !expected.is_subset(&leaves)
    {
        return Err(failure(
            "gpu_candidate_topology_raced",
            "candidate UUIDs no longer match strict executable-leaf topology",
        ));
    }
    Ok(())
}
#[cfg(target_os = "linux")]
fn validate_fresh_post_lock(
    request: &DirectGpuCommandRequest,
    initial: &ResourceObservation,
    final_observation: &ResourceObservation,
    occupancy: &ProcessOccupancyEvidence,
    selected: &[String],
) -> Result<()> {
    if initial.observation_event_id.is_empty()
        || final_observation.observation_event_id.is_empty()
        || initial.observation_event_id == final_observation.observation_event_id
    {
        return Err(failure(
            "gpu_run_admission_raced",
            "post-lock observation requires a distinct freshness event ID",
        ));
    }
    if request
        .candidate_allocation
        .candidate_ids
        .iter()
        .any(|uuid| !final_observation.caller_allocated_ids.contains(uuid))
    {
        return Err(failure(
            "gpu_run_admission_raced",
            "post-lock visibility no longer contains every candidate",
        ));
    }
    if selected.iter().any(|uuid| {
        occupancy.unit_states.get(uuid) != Some(&GpuUnitDisposition::Free)
            || !final_observation
                .free_memory_bytes
                .get(uuid)
                .is_some_and(|memory| *memory >= request.minimum_free_memory_bytes)
    }) {
        return Err(failure(
            "gpu_run_admission_raced",
            "selected GPU became BUSY, UNKNOWN, or memory-insufficient after lock acquisition",
        ));
    }
    Ok(())
}

#[derive(Clone, Debug)]
pub struct MaterializedDirectEnvironment {
    pub schema_version: String,
    pub plan_fingerprint: String,
    pub environment_fingerprint: String,
    pub exact_environment: BTreeMap<String, String>,
    pub selected_uuid_list: String,
    pub canonical_jax_environment: BTreeMap<String, String>,
}
fn sensitive_environment_key(key: &str) -> bool {
    [
        "API_KEY",
        "AUTH",
        "CREDENTIAL",
        "KEY",
        "PASSWORD",
        "SECRET",
        "TOKEN",
    ]
    .iter()
    .any(|part| key.to_uppercase().contains(part))
}
fn environment_contract(environment: &BTreeMap<String, String>) -> serde_json::Value {
    use sha2::{Digest, Sha256};
    let values=environment.iter().map(|(key,value)|{
        let sensitive=sensitive_environment_key(key);
        (key.clone(),if sensitive{serde_json::json!({"present":true,"redacted":true,"sha256":format!("{:x}",Sha256::digest(value.as_bytes())),"byte_count":value.len()})}else{serde_json::json!(value)})
    }).collect::<Vec<_>>();
    serde_json::json!(values)
}
pub fn materialize_direct_environment(
    plan: &FrozenDirectGpuCommandPlan,
    base: &BTreeMap<String, String>,
) -> Result<MaterializedDirectEnvironment> {
    use sha2::{Digest, Sha256};
    if base
        .iter()
        .any(|(key, value)| key.is_empty() || key.contains(['\0', '=']) || value.contains('\0'))
    {
        return Err(failure(
            "gpu_command_environment_invalid",
            "direct command environment requires NUL-free string keys and values",
        ));
    }
    let selected = plan.selected_ids.join(",");
    if selected.is_empty() || plan.selected_ids.iter().any(|uuid| !UUID.is_match(uuid)) {
        return Err(failure(
            "gpu_visibility_materialization_invalid",
            "selected visibility requires non-empty complete UUIDs",
        ));
    }
    let jax = BTreeMap::from([
        ("JAX_PLATFORMS".to_owned(), "cuda".to_owned()),
        ("XLA_PYTHON_CLIENT_PREALLOCATE".into(), "false".into()),
        ("XLA_PYTHON_CLIENT_ALLOCATOR".into(), "platform".into()),
        (
            "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR".into(),
            "false".into(),
        ),
    ]);
    let mut environment = base.clone();
    environment.insert("CUDA_VISIBLE_DEVICES".into(), selected.clone());
    environment.insert("NVIDIA_VISIBLE_DEVICES".into(), selected.clone());
    environment.extend(jax.clone());
    let payload = environment_contract(&environment);
    let bytes = crate::artifacts::artifact_identity::canonical_json_ascii_bytes(&payload)
        .map_err(|error| failure("gpu_command_environment_invalid", &error.to_string()))?;
    Ok(MaterializedDirectEnvironment {
        schema_version: "agentcanon-gpu-command-environment/v1".into(),
        plan_fingerprint: plan.plan_fingerprint.clone(),
        environment_fingerprint: format!("{:x}", Sha256::digest(bytes)),
        exact_environment: environment,
        selected_uuid_list: selected,
        canonical_jax_environment: jax,
    })
}

#[cfg(target_os = "linux")]
fn prepare_output_directory(
    request: &DirectGpuCommandRequest,
) -> Result<crate::runtime_boundary::RuntimeDirectory> {
    let directory =
        crate::runtime_boundary::RuntimeDirectory::open_nofollow(&request.output_dir, true)
            .map_err(|error| failure("gpu_command_output_unavailable", &error.to_string()))?;
    for filename in [
        "gpu_command_plan.json",
        "gpu_command_environment.json",
        "gpu_command_result.json",
        "gpu_command_failure.json",
        "stdout.log",
        "stderr.log",
    ] {
        if directory
            .entry_exists(std::path::Path::new(filename))
            .map_err(|error| failure("gpu_command_output_invalid", &error.to_string()))?
        {
            return Err(failure(
                "gpu_command_evidence_collision",
                "direct GPU command output files must not already exist",
            ));
        }
    }
    Ok(directory)
}
#[cfg(target_os = "linux")]
fn fingerprint(payload: &serde_json::Value) -> Result<String> {
    use sha2::{Digest, Sha256};
    let value = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| failure("gpu_command_evidence_invalid", &error))?;
    let bytes = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&value)
        .map_err(|error| failure("gpu_command_evidence_invalid", &error))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
#[cfg(target_os = "linux")]
fn build_admission_receipt(
    request: &DirectGpuCommandRequest,
    observations: (&ResourceObservation, &ResourceObservation),
    occupancies: (&ProcessOccupancyEvidence, &ProcessOccupancyEvidence),
    reservation: &crate::execution_resource_plan::ReservationEvidence,
) -> Result<crate::execution_resource_plan::RunGpuAdmissionReceipt> {
    use std::os::unix::fs::MetadataExt;
    let (initial, final_observation) = observations;
    let (initial_occupancy, final_occupancy) = occupancies;
    let lock = reservation.locks.first().cloned().ok_or_else(|| {
        failure(
            "gpu_lock_readback_missing",
            "acquired reservation returned no lock readback",
        )
    })?;
    let inventory = final_observation.nvidia_inventory.as_ref().ok_or_else(|| {
        failure(
            "gpu_inventory_unproven",
            "strict NVIDIA inventory is required",
        )
    })?;
    let metadata = std::fs::metadata(&request.lock_root)
        .map_err(|error| failure("gpu_runtime_identity_unproven", &error.to_string()))?;
    let namespace = std::fs::read_link("/proc/self/ns/pid")
        .map_err(|error| failure("gpu_runtime_identity_unproven", &error.to_string()))?;
    let runtime = fingerprint(
        &serde_json::json!({"schema_version":"host-direct-runtime-identity/v1","runtime_root":request.runtime_root,"lock_root":request.lock_root,"lock_device":metadata.dev(),"lock_inode":metadata.ino(),"lock_mode":format!("0o{:o}",metadata.mode()&0o7777),"pid_namespace":namespace,"boot_id":final_observation.boot_id,"caller_allocated_ids":final_observation.caller_allocated_ids}),
    )?;
    let concurrent = serde_json::json!({"initial_snapshot_fingerprint":initial.fingerprint,"admission_snapshot_fingerprint":final_observation.fingerprint,"final_snapshot_fingerprint":final_observation.fingerprint,"initial_event_id":initial.observation_event_id,"admission_event_id":final_observation.observation_event_id,"final_event_id":final_observation.observation_event_id,
        "fingerprint":fingerprint(&serde_json::json!({"initial":initial.fingerprint,"admission":final_observation.fingerprint,"initial_event_id":initial.observation_event_id,"admission_event_id":final_observation.observation_event_id}))?});
    let selected = &reservation.selected_uuids;
    let parent_by_uuid = inventory
        .joins
        .iter()
        .map(|join| (join.mig_uuid.clone(), join.parent_uuid.clone()))
        .collect::<BTreeMap<_, _>>();
    let joins = inventory
        .joins
        .iter()
        .map(|join| serde_json::json!([join.parent_uuid, join.ordinal, join.mig_uuid]))
        .collect::<Vec<_>>();
    let mig = serde_json::json!({"parent_by_uuid":parent_by_uuid,"executable_leaf_uuids":inventory.mig_uuids,"selected_physical_uuids":selected.iter().filter(|uuid|inventory.physical_uuids.contains(uuid)).collect::<Vec<_>>(),"fingerprint":fingerprint(&serde_json::json!({"joins":joins,"selected":selected}))?});
    let mut receipt = crate::execution_resource_plan::RunGpuAdmissionReceipt {
        schema_version: "gpu-admission/v1".into(),
        candidate_uuids: request.candidate_allocation.candidate_ids.clone(),
        occupied_uuids: final_occupancy.occupied_uuids.clone(),
        reserved_uuids: selected.clone(),
        selected_uuids: selected.clone(),
        inventory_fingerprint: inventory.evidence_fingerprint.clone(),
        occupancy_fingerprint: fingerprint(
            &serde_json::json!({"initial":initial_occupancy.evidence_fingerprint,"final":final_occupancy.evidence_fingerprint}),
        )?,
        reservation_fingerprint: reservation.evidence_fingerprint.clone(),
        runtime_identity_fingerprint: runtime,
        plan_fingerprint: None,
        admission_fingerprint: String::new(),
        lock_readback: Some(lock),
        effective_environment: None,
        actual_gpu_processes: Some(vec![initial_occupancy.clone(), final_occupancy.clone()]),
        concurrent_run_evidence: Some(concurrent),
        mig_evidence: Some(mig),
        container_visible_uuid_mapping: None,
        os_safe_lock_placement: None,
        descendant_retention_evidence: None,
    };
    receipt.refresh_fingerprint()?;
    Ok(receipt)
}
#[cfg(target_os = "linux")]
fn freeze_direct_plan(
    request: &DirectGpuCommandRequest,
    observations: (&ResourceObservation, &ResourceObservation),
    occupancies: (&ProcessOccupancyEvidence, &ProcessOccupancyEvidence),
    reservation: &crate::execution_resource_plan::ReservationEvidence,
    reservation_ids: Vec<String>,
    admission: &crate::execution_resource_plan::RunGpuAdmissionReceipt,
) -> Result<FrozenDirectGpuCommandPlan> {
    use sha2::{Digest, Sha256};
    let (initial, final_observation) = observations;
    let (initial_occupancy, final_occupancy) = occupancies;
    let selected = &reservation.selected_uuids;
    let identity = format!(
        "{}{}{}",
        request.argv.join("\0"),
        request.cwd.display(),
        final_observation.observation_event_id
    );
    let digest = format!("{:x}", Sha256::digest(identity));
    let key_witness = request
        .environment
        .keys()
        .map(|key| {
            (
                key.clone(),
                serde_json::json!({"present":true,"redacted":sensitive_environment_key(key)}),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let unit_states = |occupancy: &ProcessOccupancyEvidence| {
        request
            .candidate_allocation
            .candidate_ids
            .iter()
            .map(|uuid| {
                (
                    uuid.clone(),
                    match occupancy.unit_states.get(uuid) {
                        Some(GpuUnitDisposition::Free) => "FREE",
                        Some(GpuUnitDisposition::Busy) => "BUSY",
                        _ => "UNKNOWN",
                    }
                    .into(),
                )
            })
            .collect()
    };
    let mut plan = FrozenDirectGpuCommandPlan {
        schema_version: "agentcanon-gpu-command-plan/v1".into(),
        plan_id: format!("gpu-command-{}", &digest[..20]),
        plan_fingerprint: String::new(),
        argv: request.argv.clone(),
        cwd: request.cwd.to_string_lossy().into_owned(),
        candidate_ids: request.candidate_allocation.candidate_ids.clone(),
        selected_ids: selected.clone(),
        candidate_source: request.candidate_allocation.source.clone(),
        candidate_inventory_fingerprint: request.candidate_allocation.inventory_fingerprint.clone(),
        candidate_mig_parent_by_uuid: request.candidate_allocation.mig_parent_by_uuid.clone(),
        requested_gpu_count: request.gpu_count,
        minimum_free_memory_bytes: request.minimum_free_memory_bytes,
        selected_free_memory_bytes: selected
            .iter()
            .map(|uuid| {
                final_observation
                    .free_memory_bytes
                    .get(uuid)
                    .map(|memory| (uuid.clone(), *memory))
                    .ok_or_else(|| {
                        failure(
                            "gpu_command_plan_invalid",
                            "selected memory evidence is missing",
                        )
                    })
            })
            .collect::<Result<_>>()?,
        initial_unit_states: unit_states(initial_occupancy),
        final_unit_states: unit_states(final_occupancy),
        initial_observation_fingerprint: initial.fingerprint.clone(),
        final_observation_fingerprint: final_observation.fingerprint.clone(),
        initial_event_id: initial.observation_event_id.clone(),
        final_event_id: final_observation.observation_event_id.clone(),
        reservation_fingerprint: reservation.evidence_fingerprint.clone(),
        reservation_ids,
        lock_identities: reservation
            .locks
            .iter()
            .map(|lock| (lock.device, lock.inode))
            .collect(),
        admission_fingerprint: admission.admission_fingerprint.clone(),
        base_environment_fingerprint: fingerprint(&environment_contract(&request.environment))?,
        environment_key_witness: serde_json::json!(key_witness),
        output_dir: request.output_dir.to_string_lossy().into_owned(),
        unknown_initial_ids: initial_occupancy.unknown_uuids.clone(),
        unknown_final_ids: final_occupancy.unknown_uuids.clone(),
    };
    let mut payload = serde_json::to_value(&plan)
        .map_err(|error| failure("gpu_command_plan_invalid", &error.to_string()))?;
    payload
        .as_object_mut()
        .expect("plan object")
        .remove("plan_fingerprint");
    plan.plan_fingerprint = fingerprint(&payload)?;
    plan.validate()?;
    Ok(plan)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProcRecord {
    pub pid: u32,
    pub parent_pid: u32,
    pub process_group_id: u32,
    pub session_id: u32,
    pub starttime: String,
    pub state: String,
}
#[cfg(target_os = "linux")]
impl ProcRecord {
    fn identity(&self) -> (u32, String) {
        (self.pid, self.starttime.clone())
    }
}
#[cfg(target_os = "linux")]
fn scan_proc_table(root: &std::path::Path) -> Result<BTreeMap<u32, ProcRecord>> {
    let mut records = BTreeMap::new();
    let entries = std::fs::read_dir(root)
        .map_err(|error| failure("gpu_command_proc_unavailable", &error.to_string()))?;
    for entry in entries {
        let Ok(entry) = entry else {
            continue;
        };
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Ok(pid) = name.parse::<u32>() else {
            continue;
        };
        let Ok(raw) = std::fs::read_to_string(entry.path().join("stat")) else {
            continue;
        };
        let Some((_, tail)) = raw.rsplit_once(')') else {
            continue;
        };
        let fields = tail.split_whitespace().collect::<Vec<_>>();
        if fields.len() <= 19 {
            continue;
        }
        let (Ok(parent_pid), Ok(process_group_id), Ok(session_id)) =
            (fields[1].parse(), fields[2].parse(), fields[3].parse())
        else {
            continue;
        };
        records.insert(
            pid,
            ProcRecord {
                pid,
                parent_pid,
                process_group_id,
                session_id,
                starttime: fields[19].into(),
                state: fields[0].into(),
            },
        );
    }
    Ok(records)
}
#[cfg(target_os = "linux")]
fn descendant_scope(
    table: &BTreeMap<u32, ProcRecord>,
    runner_pid: u32,
    root_pid: u32,
    tracked: &BTreeMap<(u32, String), ProcRecord>,
    baseline: &BTreeSet<(u32, String)>,
) -> BTreeMap<(u32, String), ProcRecord> {
    let mut scoped = BTreeMap::new();
    let mut frontier = tracked
        .values()
        .map(|record| record.pid)
        .collect::<BTreeSet<_>>();
    frontier.insert(root_pid);
    loop {
        let before = frontier.len();
        for record in table.values() {
            if record.pid == runner_pid {
                continue;
            }
            let identity = record.identity();
            let adopted = record.parent_pid == runner_pid && !baseline.contains(&identity);
            if record.pid == root_pid
                || tracked.contains_key(&identity)
                || record.session_id == root_pid
                || record.process_group_id == root_pid
                || frontier.contains(&record.parent_pid)
                || adopted
            {
                frontier.insert(record.pid);
                scoped.insert(identity, record.clone());
            }
        }
        if frontier.len() == before {
            return scoped;
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum ProvenQuiescence {
    #[serde(rename = "PROVEN")]
    Proven,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DirectCommandLifecycle {
    pub child_pid: u32,
    pub child_starttime: Option<String>,
    pub process_group_id: u32,
    pub session_id: u32,
    pub observed_descendant_identities: Vec<(u32, String)>,
    pub descendant_quiescence: ProvenQuiescence,
    pub subreaper_enabled: bool,
    pub started_at_utc: String,
    pub finished_at_utc: String,
    pub started_at_monotonic: f64,
    pub finished_at_monotonic: f64,
}
#[cfg(target_os = "linux")]
impl DirectCommandLifecycle {
    fn record(&self) -> serde_json::Value {
        serde_json::json!({"child_pid":self.child_pid,"child_starttime":self.child_starttime,"process_group_id":self.process_group_id,"session_id":self.session_id,"observed_descendant_identities":self.observed_descendant_identities,"descendant_quiescence":self.descendant_quiescence,"subreaper_enabled":self.subreaper_enabled,"started_at":self.started_at_utc,"finished_at":self.finished_at_utc,"duration_seconds":(self.finished_at_monotonic-self.started_at_monotonic).max(0.0),"signal_or_kill_sent":false})
    }
}
#[derive(Clone, Debug)]
pub struct DirectCommandExecution {
    pub returncode: i32,
    pub lifecycle: DirectCommandLifecycle,
    pub stdout_path: PathBuf,
    pub stderr_path: PathBuf,
}
#[cfg(target_os = "linux")]
pub fn execute_direct_command(
    plan: &FrozenDirectGpuCommandPlan,
    environment: &BTreeMap<String, String>,
    poll_seconds: f64,
) -> std::result::Result<DirectCommandExecution, (Failure, Option<Box<DirectCommandExecution>>)> {
    use nix::sys::wait::{waitpid, WaitPidFlag};
    use std::os::unix::process::ExitStatusExt;
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};
    let mut completed = None;
    let operation = (|| -> Result<DirectCommandExecution> {
        plan.validate()?;
        let runner = std::process::id();
        let table = scan_proc_table(std::path::Path::new("/proc"))?;
        let baseline = table
            .values()
            .filter(|record| record.parent_pid == runner)
            .map(ProcRecord::identity)
            .collect::<BTreeSet<_>>();
        let previous = nix::sys::prctl::get_child_subreaper()
            .map_err(|error| failure("gpu_command_subreaper_unavailable", &error.to_string()))?;
        if !previous {
            nix::sys::prctl::set_child_subreaper(true).map_err(|error| {
                failure("gpu_command_subreaper_unavailable", &error.to_string())
            })?;
        }
        let operation = (|| -> Result<DirectCommandExecution> {
            let output = crate::runtime_boundary::RuntimeDirectory::open_nofollow(
                std::path::Path::new(&plan.output_dir),
                false,
            )
            .map_err(|error| failure("gpu_command_output_unavailable", &error.to_string()))?;
            let stdout_path = PathBuf::from(&plan.output_dir).join("stdout.log");
            let stderr_path = PathBuf::from(&plan.output_dir).join("stderr.log");
            let stdout = output
                .create_file_once(std::path::Path::new("stdout.log"), 0o600)
                .map_err(|error| failure("gpu_command_output_unavailable", &error.to_string()))?;
            let stderr = output
                .create_file_once(std::path::Path::new("stderr.log"), 0o600)
                .map_err(|error| failure("gpu_command_output_unavailable", &error.to_string()))?;
            let start = Instant::now();
            let started_at_utc = utc_timestamp()?;
            let started_at_monotonic = monotonic_seconds()?;
            let mut child =
                Command::new("setsid")
                    .arg("--")
                    .args(&plan.argv)
                    .current_dir(&plan.cwd)
                    .env_clear()
                    .envs(environment)
                    .stdin(Stdio::inherit())
                    .stdout(stdout.try_clone().map_err(|error| {
                        failure("gpu_command_launch_failed", &error.to_string())
                    })?)
                    .stderr(stderr.try_clone().map_err(|error| {
                        failure("gpu_command_launch_failed", &error.to_string())
                    })?)
                    .spawn()
                    .map_err(|error| failure("gpu_command_launch_failed", &error.to_string()))?;
            let root = child.id();
            let mut tracked = BTreeMap::new();
            let mut child_starttime = None;
            let mut pending = None;
            let delay = Duration::from_secs_f64(poll_seconds);
            let status = loop {
                match scan_proc_table(std::path::Path::new("/proc")) {
                    Ok(table) => {
                        tracked.extend(descendant_scope(&table, runner, root, &tracked, &baseline));
                        if child_starttime.is_none() {
                            child_starttime =
                                table.get(&root).map(|record| record.starttime.clone());
                        }
                    }
                    Err(error) => {
                        pending.get_or_insert(error);
                    }
                }
                match child.try_wait() {
                    Ok(Some(status)) => break status,
                    Ok(None) => {}
                    Err(error) => {
                        pending.get_or_insert_with(|| {
                            failure("gpu_command_wait_failed", &error.to_string())
                        });
                    }
                }
                std::thread::sleep(delay);
            };
            loop {
                match scan_proc_table(std::path::Path::new("/proc")) {
                    Ok(table) => {
                        let scoped = descendant_scope(&table, runner, root, &tracked, &baseline);
                        tracked.extend(scoped.clone());
                        for record in scoped.values().filter(|record| {
                            record.pid != root && record.parent_pid == runner && record.state == "Z"
                        }) {
                            match waitpid(
                                nix::unistd::Pid::from_raw(record.pid as i32),
                                Some(WaitPidFlag::WNOHANG),
                            ) {
                                Ok(_) | Err(nix::errno::Errno::ECHILD) => {}
                                Err(error) => {
                                    pending.get_or_insert_with(|| {
                                        failure("gpu_command_wait_failed", &error.to_string())
                                    });
                                }
                            }
                        }
                        if !scoped
                            .values()
                            .any(|record| record.pid != root && record.state != "Z")
                        {
                            break;
                        }
                    }
                    Err(error) => {
                        pending.get_or_insert(error);
                    }
                }
                std::thread::sleep(delay);
            }
            let execution = DirectCommandExecution {
                returncode: status
                    .code()
                    .unwrap_or_else(|| -status.signal().unwrap_or(1)),
                lifecycle: DirectCommandLifecycle {
                    child_pid: root,
                    child_starttime,
                    process_group_id: root,
                    session_id: root,
                    observed_descendant_identities: tracked
                        .keys()
                        .filter(|(pid, _)| *pid != root)
                        .cloned()
                        .collect(),
                    descendant_quiescence: ProvenQuiescence::Proven,
                    subreaper_enabled: true,
                    started_at_utc,
                    finished_at_utc: utc_timestamp()?,
                    started_at_monotonic,
                    finished_at_monotonic: started_at_monotonic + start.elapsed().as_secs_f64(),
                },
                stdout_path,
                stderr_path,
            };
            for file in [stdout, stderr] {
                if let Err(error) = file.sync_all() {
                    pending.get_or_insert_with(|| {
                        failure("gpu_command_output_sync_failed", &error.to_string())
                    });
                }
            }
            completed = Some(Box::new(execution.clone()));
            if let Some(error) = pending {
                return Err(error);
            }
            Ok(execution)
        })();
        if !previous {
            nix::sys::prctl::set_child_subreaper(false).map_err(|error| {
                failure("gpu_command_subreaper_unavailable", &error.to_string())
            })?;
        }
        operation
    })();
    operation.map_err(|error| (error, completed))
}
#[cfg(target_os = "linux")]
fn utc_timestamp() -> Result<String> {
    time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .map_err(|error| failure("gpu_command_clock_unavailable", &error.to_string()))
}
#[cfg(target_os = "linux")]
fn monotonic_seconds() -> Result<f64> {
    let value = rustix::time::clock_gettime(rustix::time::ClockId::Monotonic);
    Ok(value.tv_sec as f64 + value.tv_nsec as f64 / 1e9)
}

#[cfg(target_os = "linux")]
fn occupancy(observation: &ResourceObservation) -> Result<ProcessOccupancyEvidence> {
    let inventory = observation.nvidia_inventory.as_ref().ok_or_else(|| {
        failure(
            "gpu_inventory_unproven",
            "GPU admission requires strict inventory",
        )
    })?;
    let namespace = std::fs::read_link("/proc/self/ns/pid")
        .map_err(|error| failure("gpu_namespace_identity_unproven", &error.to_string()))?;
    let namespace = namespace.to_string_lossy();
    let inode = namespace
        .strip_prefix("pid:[")
        .and_then(|value| value.strip_suffix(']'))
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| {
            failure(
                "gpu_namespace_identity_unproven",
                "local PID namespace identity is invalid",
            )
        })?;
    let disposition = if observation.process_identities.is_empty() {
        "COMPLETE_EMPTY"
    } else {
        "COMPLETE"
    };
    crate::execution_resource_plan::process_occupancy(
        inventory,
        inode,
        &observation.process_identities,
        &observation.unknown_gpu_ids,
        false,
        disposition,
    )
}
#[cfg(target_os = "linux")]
pub struct DirectGpuCommandResult {
    pub record: serde_json::Value,
    pub execution: DirectCommandExecution,
}
#[cfg(target_os = "linux")]
pub fn run_direct_command(request: &DirectGpuCommandRequest) -> Result<DirectGpuCommandResult> {
    use crate::execution_resource_plan::{
        discover_resources, AbsolutePosixPath, GpuReservationTransaction,
    };
    request.validate()?;
    run_direct_command_with(
        request,
        discover_resources,
        |request| {
            Ok(Box::new(GpuReservationTransaction::new(
                &AbsolutePosixPath::parse(&request.lock_root.to_string_lossy())?,
                &AbsolutePosixPath::parse(&request.runtime_root.to_string_lossy())?,
            )?))
        },
        execute_direct_command,
    )
}
pub trait ReservationTransaction {
    fn try_reserve(
        &mut self,
        candidates: &[String],
        occupied: &BTreeSet<String>,
        count: usize,
    ) -> Result<crate::execution_resource_plan::ReservationEvidence>;
    fn reservation_ids(&self) -> Vec<String>;
    fn close(&mut self) -> Result<Vec<crate::execution_resource_plan::FdReleaseEvidence>>;
}
#[cfg(target_os = "linux")]
fn release_dispositions_complete(
    dispositions: &[crate::execution_resource_plan::FdReleaseEvidence],
) -> bool {
    !dispositions.is_empty()
        && dispositions.iter().all(|item| {
            item.error_kind.is_none()
                && ["busy_candidate", "released", "rolled_back"]
                    .contains(&item.disposition.as_str())
        })
}
#[cfg(target_os = "linux")]
impl ReservationTransaction for crate::execution_resource_plan::GpuReservationTransaction {
    fn try_reserve(
        &mut self,
        candidates: &[String],
        occupied: &BTreeSet<String>,
        count: usize,
    ) -> Result<crate::execution_resource_plan::ReservationEvidence> {
        self.try_reserve(candidates, occupied, count)
    }
    fn reservation_ids(&self) -> Vec<String> {
        self.reservation_ids()
    }
    fn close(&mut self) -> Result<Vec<crate::execution_resource_plan::FdReleaseEvidence>> {
        self.close()
    }
}
#[cfg(target_os = "linux")]
pub fn run_direct_command_with(
    request: &DirectGpuCommandRequest,
    mut observe: impl FnMut(&BTreeMap<String, String>, usize) -> Result<ResourceObservation>,
    mut reserve: impl FnMut(&DirectGpuCommandRequest) -> Result<Box<dyn ReservationTransaction>>,
    mut execute: impl FnMut(
        &FrozenDirectGpuCommandPlan,
        &BTreeMap<String, String>,
        f64,
    ) -> std::result::Result<
        DirectCommandExecution,
        (Failure, Option<Box<DirectCommandExecution>>),
    >,
) -> Result<DirectGpuCommandResult> {
    use crate::execution_resource_plan::{write_json_once, FdReleaseEvidence};
    let output = prepare_output_directory(request)?;
    let mut transaction = None::<Box<dyn ReservationTransaction>>;
    let mut dispositions = Vec::<FdReleaseEvidence>::new();
    let mut plan = None;
    let mut environment = None;
    let mut admission = None;
    let mut execution = None;
    let mut close_failure = None;
    let result = (|| -> Result<DirectGpuCommandResult> {
        let mut probe_environment = request.environment.clone();
        let candidates = request.candidate_allocation.candidate_ids.join(",");
        probe_environment.insert("CUDA_VISIBLE_DEVICES".into(), candidates.clone());
        probe_environment.insert("NVIDIA_VISIBLE_DEVICES".into(), candidates);
        let initial = observe(&probe_environment, request.gpu_count)?;
        validate_candidate_topology(request, &initial)?;
        let initial_occupancy = occupancy(&initial)?;
        let eligible = eligible_ids(request, &initial, &initial_occupancy);
        if eligible.len() < request.gpu_count {
            return Err(failure(
                "gpu_candidate_unavailable",
                "FREE, memory-qualified candidates cannot satisfy the request",
            ));
        }
        transaction = Some(reserve(request)?);
        let owned = transaction.as_mut().expect("transaction created");
        let occupied = initial_occupancy
            .occupied_uuids
            .iter()
            .chain(&initial_occupancy.unknown_uuids)
            .cloned()
            .collect();
        let reservation = owned.try_reserve(&eligible, &occupied, request.gpu_count)?;
        if reservation.disposition != "ACQUIRED"
            || reservation.selected_uuids.len() != request.gpu_count
        {
            return Err(failure(
                "gpu_candidate_unavailable",
                "UUID lock acquisition could not satisfy requested count",
            ));
        }
        let final_observation = observe(&probe_environment, request.gpu_count)?;
        validate_candidate_topology(request, &final_observation)?;
        let final_occupancy = occupancy(&final_observation)?;
        validate_fresh_post_lock(
            request,
            &initial,
            &final_observation,
            &final_occupancy,
            &reservation.selected_uuids,
        )?;
        let admitted = build_admission_receipt(
            request,
            (&initial, &final_observation),
            (&initial_occupancy, &final_occupancy),
            &reservation,
        )?;
        let frozen = freeze_direct_plan(
            request,
            (&initial, &final_observation),
            (&initial_occupancy, &final_occupancy),
            &reservation,
            owned.reservation_ids(),
            &admitted,
        )?;
        let frozen_value = serde_json::to_value(&frozen)
            .map_err(|error| failure("gpu_command_plan_invalid", &error.to_string()))?;
        write_json_once(
            &request.output_dir.join("gpu_command_plan.json"),
            &frozen_value,
            false,
        )?;
        plan = Some(frozen.clone());
        admission = Some(admitted.clone());
        let materialized = materialize_direct_environment(&frozen, &request.environment)?;
        let witness = materialized
            .exact_environment
            .keys()
            .map(|key| {
                (
                    key.clone(),
                    serde_json::json!({"present":true,"redacted":sensitive_environment_key(key)}),
                )
            })
            .collect::<BTreeMap<_, _>>();
        let record = serde_json::json!({"schema_version":materialized.schema_version,"plan_fingerprint":materialized.plan_fingerprint,"environment_fingerprint":materialized.environment_fingerprint,"selected_uuid_list":materialized.selected_uuid_list,"cuda_visible_devices":materialized.exact_environment["CUDA_VISIBLE_DEVICES"],"nvidia_visible_devices":materialized.exact_environment["NVIDIA_VISIBLE_DEVICES"],"canonical_jax_environment":materialized.canonical_jax_environment,"environment_key_witness":witness});
        write_json_once(
            &request.output_dir.join("gpu_command_environment.json"),
            &record,
            false,
        )?;
        environment = Some(materialized.clone());
        let executed = match execute(
            &frozen,
            &materialized.exact_environment,
            request.descendant_poll_seconds,
        ) {
            Ok(value) => value,
            Err((error, completed)) => {
                execution = completed.map(|value| *value);
                return Err(error);
            }
        };
        execution = Some(executed.clone());
        let mut owned = transaction.take().expect("owned transaction");
        dispositions = match owned.close() {
            Ok(values) => values,
            Err(error) => {
                close_failure = Some(error.message);
                return Err(failure(
                    "gpu_reservation_release_failed",
                    "direct command reservation release was incomplete",
                ));
            }
        };
        if !release_dispositions_complete(&dispositions) {
            return Err(failure(
                "gpu_reservation_release_failed",
                "direct command reservation release was incomplete",
            ));
        }
        let file_record = |path: &std::path::Path| -> Result<serde_json::Value> {
            use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
            use sha2::{Digest, Sha256};
            use std::io::Read;
            let parent =
                crate::source_mutation::open_root_nofollow(path.parent().ok_or_else(|| {
                    failure("gpu_command_output_invalid", "output parent required")
                })?)
                .map_err(|error| failure("gpu_command_output_unavailable", &error.to_string()))?;
            let mut options = cap_std::fs::OpenOptions::new();
            options.read(true).follow(FollowSymlinks::No);
            let mut file = parent
                .open_with(
                    path.file_name().ok_or_else(|| {
                        failure("gpu_command_output_invalid", "output filename required")
                    })?,
                    &options,
                )
                .map_err(|error| failure("gpu_command_output_unavailable", &error.to_string()))?;
            let mut digest = Sha256::new();
            let mut size = 0u64;
            let mut buffer = [0u8; 8192];
            loop {
                let count = file.read(&mut buffer).map_err(|error| {
                    failure("gpu_command_output_unavailable", &error.to_string())
                })?;
                if count == 0 {
                    break;
                }
                digest.update(&buffer[..count]);
                size += count as u64;
            }
            Ok(
                serde_json::json!({"path":path,"sha256":format!("{:x}",digest.finalize()),"bytes":size}),
            )
        };
        let lifecycle = executed.lifecycle.record();
        let selected = &frozen.selected_ids;
        let record = serde_json::json!({"schema_version":"agentcanon-gpu-command-result/v1","plan_id":frozen.plan_id,"plan_fingerprint":frozen.plan_fingerprint,"admission_fingerprint":admitted.admission_fingerprint,"environment_fingerprint":materialized.environment_fingerprint,"argv":frozen.argv,"cwd":frozen.cwd,"candidate_gpu_ids":frozen.candidate_ids,"selected_gpu_ids":selected,"selected_free_memory_bytes":frozen.selected_free_memory_bytes,"reservation_ids":frozen.reservation_ids,"lock_identities":frozen.lock_identities,"raw_returncode":executed.returncode,"process_exit_code":process_exit_code(executed.returncode),"stdout":file_record(&executed.stdout_path)?,"stderr":file_record(&executed.stderr_path)?,"lifecycle":lifecycle,
            "container_visible_uuid_mapping":{"cuda_visible_devices":materialized.selected_uuid_list,"nvidia_visible_devices":materialized.selected_uuid_list,"visible_uuids":selected,"namespace_id":format!("pid-session:{}",executed.lifecycle.session_id),"fingerprint":fingerprint(&serde_json::json!({"plan_fingerprint":frozen.plan_fingerprint,"selected_ids":selected,"session_id":executed.lifecycle.session_id}))?},
            "descendant_retention_evidence":{"child_process_ids":[executed.lifecycle.child_pid],"process_group_ids":[executed.lifecycle.process_group_id],"descendant_quiescence":"PROVEN","release_blocked":false,"fingerprint":fingerprint(&lifecycle)?},"release_dispositions":dispositions,"managed_provider_required":false,"shell":false,"signal_or_kill_sent":false});
        write_json_once(
            &request.output_dir.join("gpu_command_result.json"),
            &record,
            false,
        )?;
        Ok(DirectGpuCommandResult {
            record,
            execution: executed,
        })
    })();
    if let Err(mut error) = result {
        let mut release_failure = close_failure;
        if let Some(mut owned) = transaction.take() {
            match owned.close() {
                Ok(values) => {
                    dispositions = values;
                    if !release_dispositions_complete(&dispositions) {
                        release_failure =
                            Some("GPU reservation release evidence was incomplete".to_owned());
                    }
                }
                Err(failure) => {
                    release_failure = Some(failure.message);
                }
            }
        }
        if release_failure.is_some() {
            error = failure(
                "gpu_reservation_release_failed",
                "direct command reservation release was incomplete",
            );
        }
        let record = serde_json::json!({"schema_version":"agentcanon-gpu-command-failure/v1","failure_code":error.code,"message":error.message,"evidence":error.details,"plan_fingerprint":plan.as_ref().map(|plan|&plan.plan_fingerprint),"environment_fingerprint":environment.as_ref().map(|environment|&environment.environment_fingerprint),"admission_fingerprint":admission.as_ref().map(|admission|&admission.admission_fingerprint),"release_dispositions":dispositions,"release_close_failure":release_failure.map(|message|serde_json::json!({"type":"TypedPreflightFailure","message":message})),"managed_provider_required":false,"child_started":execution.is_some(),"descendant_quiescence_proven":execution.is_some(),"release_blocked":false,"lifecycle":execution.as_ref().map(|execution|execution.lifecycle.record())});
        if !output
            .entry_exists(std::path::Path::new("gpu_command_failure.json"))
            .map_err(|error| failure("gpu_command_output_invalid", &error.to_string()))?
        {
            write_json_once(
                &request.output_dir.join("gpu_command_failure.json"),
                &record,
                false,
            )?;
        }
        return Err(error);
    }
    result
}
pub fn process_exit_code(raw: i32) -> i32 {
    if raw < 0 {
        128 + raw.saturating_abs()
    } else {
        raw
    }
}

pub fn run(args: &[String]) -> i32 {
    let options = [
        ("--gpu-count", 0),
        ("--min-free-memory", 1),
        ("--minimum-free-memory-bytes", 1),
        ("--candidate-gpu", 2),
        ("--cwd", 3),
        ("--output-dir", 4),
    ];
    let current = match std::env::current_dir() {
        Ok(path) => path,
        Err(error) => {
            eprintln!("{error}");
            return 125;
        }
    };
    let mut count = 1i64;
    let mut memory = 0i64;
    let mut explicit = Vec::new();
    let mut cwd = current.clone();
    let mut output = None;
    let mut argv = Vec::new();
    let mut index = 0;
    while index < args.len() {
        let raw = &args[index];
        if raw == "--" {
            argv = args[index + 1..].to_vec();
            break;
        }
        if raw == "--help" || raw == "-h" {
            println!("usage: agent-canon run-gpu-command [--gpu-count N] [--min-free-memory BYTES] [--candidate-gpu FULL_UUID] [--cwd PATH] [--output-dir PATH] -- COMMAND ...");
            return 0;
        }
        if !raw.starts_with('-') {
            argv = args[index..].to_vec();
            break;
        }
        let (option, inline) = raw
            .split_once('=')
            .map_or((raw.as_str(), None), |(name, value)| (name, Some(value)));
        let key = match crate::python_cli_options::resolve_long_option_prefix(option, &options) {
            Ok(key) => key,
            Err(_) => {
                eprintln!("unrecognized or ambiguous argument: {raw}");
                return 2;
            }
        };
        let value = match inline {
            Some(value) => value.to_owned(),
            None => {
                index += 1;
                let Some(value) = args.get(index) else {
                    eprintln!("argument {option}: expected one argument");
                    return 2;
                };
                value.clone()
            }
        };
        match key {
            0 | 1 => {
                use num_traits::ToPrimitive;
                let Some(value) =
                    crate::python_cli_integer::parse(&value).and_then(|value| value.to_i64())
                else {
                    eprintln!("argument {option}: invalid int value");
                    return 2;
                };
                if key == 0 {
                    count = value;
                } else {
                    memory = value;
                }
            }
            2 => explicit.push(value),
            3 => {
                cwd = if std::path::Path::new(&value).is_absolute() {
                    value.into()
                } else {
                    current.join(value)
                }
            }
            4 => {
                if !value.is_empty() {
                    output = Some(if std::path::Path::new(&value).is_absolute() {
                        PathBuf::from(value)
                    } else {
                        current.join(value)
                    });
                }
            }
            _ => unreachable!(),
        }
        index += 1;
    }
    let output = output.unwrap_or_else(|| {
        let now = time::OffsetDateTime::now_utc();
        let stamp = format!(
            "{:04}{:02}{:02}T{:02}{:02}{:02}Z",
            now.year(),
            now.month() as u8,
            now.day(),
            now.hour(),
            now.minute(),
            now.second()
        );
        current
            .join("reports/agents")
            .join(format!("gpu-command-{stamp}-{}", std::process::id()))
            .join("runtime")
    });
    let operation = (|| -> Result<i32> {
        if argv.is_empty() {
            return Err(failure(
                "gpu_command_argv_invalid",
                "a direct command argv is required after --",
            ));
        }
        #[cfg(not(target_os = "linux"))]
        {
            let _ = (&explicit, &cwd, count, memory);
            Err(failure(
                "gpu_command_lifecycle_unsupported",
                "GPU descendant retention requires Linux procfs and subreaper support",
            ))
        }
        #[cfg(target_os = "linux")]
        {
            use crate::execution_resource_plan::{parse_nvidia_smi_list, EvidenceFd};
            let environment = std::env::vars().collect::<BTreeMap<_, _>>();
            let nvidia = crate::tool_dispatch::find_executable("nvidia-smi").ok_or_else(|| {
                failure(
                    "gpu_structured_probe_unavailable",
                    "nvidia-smi is required to resolve direct-command GPU candidates",
                )
            })?;
            let evidence = EvidenceFd::capture(
                &[nvidia.to_string_lossy().into_owned(), "-L".into()],
                "direct_nvidia_smi_list",
            )
            .map_err(|error| {
                if error.code == "gpu_evidence_capture_failed" {
                    failure("gpu_list_probe_failed", &error.message)
                } else {
                    error
                }
            })?;
            let inventory = parse_nvidia_smi_list(&evidence)?;
            let allocation = candidate_allocation(&environment, &explicit, &inventory)?;
            if count <= 0 {
                return Err(failure(
                    "gpu_request_cardinality_invalid",
                    "direct GPU command count must be positive",
                ));
            }
            if memory < 0 {
                return Err(failure(
                    "gpu_request_memory_invalid",
                    "minimum free memory must be non-negative",
                ));
            }
            let request = DirectGpuCommandRequest {
                argv,
                cwd,
                environment,
                candidate_allocation: allocation,
                gpu_count: count as usize,
                minimum_free_memory_bytes: memory as u64,
                output_dir: output.clone(),
                runtime_root: crate::execution_resource_plan::HOST_RUNTIME_ROOT.into(),
                lock_root: "/var/lib/agent-canon/runtime/locks".into(),
                descendant_poll_seconds: 0.05,
            };
            let result = run_direct_command(&request)?;
            use std::io::{Read, Write};
            for (path, is_stderr) in [
                (&result.execution.stdout_path, false),
                (&result.execution.stderr_path, true),
            ] {
                let mut file = std::fs::File::open(path).map_err(|error| {
                    failure("gpu_command_output_unavailable", &error.to_string())
                })?;
                let mut bytes = [0u8; 8192];
                loop {
                    let count = file.read(&mut bytes).map_err(|error| {
                        failure("gpu_command_output_unavailable", &error.to_string())
                    })?;
                    if count == 0 {
                        break;
                    }
                    if is_stderr {
                        std::io::stderr().write_all(&bytes[..count])
                    } else {
                        std::io::stdout().write_all(&bytes[..count])
                    }
                    .map_err(|error| {
                        failure("gpu_command_output_unavailable", &error.to_string())
                    })?;
                }
            }
            Ok(process_exit_code(result.execution.returncode))
        }
    })();
    match operation {
        Ok(code) => code,
        Err(error) => {
            eprintln!(
                "{}",
                serde_json::json!({"schema_version":"agentcanon-gpu-command-cli-error/v1","failure_code":error.code,"message":error.message,"output_dir":output})
            );
            125
        }
    }
}

#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;
    use crate::execution_resource_plan::{
        FdReleaseEvidence, GpuDevice, LockReadback, NvidiaInventory, ProcessIdentity,
        ReservationEvidence,
    };
    use std::cell::RefCell;
    use std::rc::Rc;
    const A: &str = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    const B: &str = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
    const C: &str = "GPU-cccccccc-cccc-cccc-cccc-cccccccccccc";
    #[derive(Default)]
    struct Events {
        candidates: Vec<String>,
        occupied: BTreeSet<String>,
        selected: Vec<String>,
        closes: usize,
        executed: bool,
        fail_close: bool,
    }
    struct Transaction(Rc<RefCell<Events>>);
    impl ReservationTransaction for Transaction {
        fn try_reserve(
            &mut self,
            candidates: &[String],
            occupied: &BTreeSet<String>,
            count: usize,
        ) -> Result<ReservationEvidence> {
            let mut events = self.0.borrow_mut();
            events.candidates = candidates.into();
            events.occupied = occupied.clone();
            events.selected = candidates.iter().take(count).cloned().collect();
            Ok(ReservationEvidence {
                schema_version: "gpu-reservation/v1".into(),
                selected_uuids: events.selected.clone(),
                locks: events
                    .selected
                    .iter()
                    .enumerate()
                    .map(|(index, _)| LockReadback {
                        runtime_root: crate::execution_resource_plan::HOST_RUNTIME_ROOT.into(),
                        filesystem_type: "ext4".into(),
                        device: 11,
                        inode: 22 + index as u64,
                        selected: Vec::new(),
                        fingerprint: format!("readback-{index}"),
                    })
                    .collect(),
                disposition: "ACQUIRED".into(),
                evidence_fingerprint: "reservation-evidence".into(),
            })
        }
        fn reservation_ids(&self) -> Vec<String> {
            self.0
                .borrow()
                .selected
                .iter()
                .map(|uuid| format!("reservation-{uuid}"))
                .collect()
        }
        fn close(&mut self) -> Result<Vec<FdReleaseEvidence>> {
            let mut events = self.0.borrow_mut();
            events.closes += 1;
            if events.fail_close {
                return Err(failure("fixture_close_failure", "one close attempt failed"));
            }
            Ok(events
                .selected
                .iter()
                .map(|uuid| FdReleaseEvidence {
                    component: "gpu-reservation-lock".into(),
                    uuid: Some(uuid.clone()),
                    disposition: "released".into(),
                    close_attempts: 1,
                    error_kind: None,
                    fingerprint: format!("released-{uuid}"),
                })
                .collect())
        }
    }
    fn observation(event: &str, busy: &[&str], unknown: &[&str]) -> ResourceObservation {
        let identities = [A, B, C].map(str::to_owned);
        let allocated = identities.iter().cloned().collect();
        let namespace = std::fs::read_link("/proc/self/ns/pid")
            .expect("local PID namespace")
            .to_string_lossy()
            .into_owned();
        ResourceObservation {
            caller_allocated_ids: allocated,
            process_identities: busy
                .iter()
                .enumerate()
                .map(|(index, uuid)| ProcessIdentity {
                    pid: 10000 + index as u32,
                    process_start_identity: format!("start-{index}"),
                    gpu_uuid: (*uuid).into(),
                    kind: "compute".into(),
                    parent_pid: None,
                    relationship: "external".into(),
                    observation_timestamp: String::new(),
                    observation_fingerprint: String::new(),
                    container_namespace_identity: namespace.clone(),
                    pid_namespace: namespace.clone(),
                    cgroup: "0::/test".into(),
                    process_root: None,
                    ancestry: Vec::new(),
                })
                .collect(),
            gpu_devices: identities
                .iter()
                .map(|uuid| GpuDevice {
                    uuid: uuid.clone(),
                    free_memory_bytes: 1000,
                    memory_bytes: 2000,
                    mig_parent_uuid: None,
                })
                .collect(),
            free_memory_bytes: identities.iter().map(|uuid| (uuid.clone(), 1000)).collect(),
            boot_id: "boot-test".into(),
            container_visible_ids: identities.iter().cloned().collect(),
            observed_at: event.into(),
            fingerprint: format!("observation-{event}"),
            observation_event_id: event.into(),
            cpu_available_set: vec![0],
            host_memory_bytes: 1024,
            temp_bytes: 1024,
            container_id: "container-test".into(),
            unknown_gpu_ids: unknown.iter().map(|uuid| (*uuid).into()).collect(),
            structure_tool: BTreeMap::new(),
            tool_availability: serde_json::json!({}),
            nvidia_inventory: Some(NvidiaInventory {
                schema_version: "nvidia-inventory/v1".into(),
                physical_uuids: identities.into(),
                mig_uuids: Vec::new(),
                joins: Vec::new(),
                driver_version: None,
                evidence_fingerprint: "inventory-test".into(),
            }),
            unit_states: BTreeMap::new(),
        }
    }
    fn fixture(count: usize) -> (tempfile::TempDir, DirectGpuCommandRequest) {
        let root = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("fixture directory");
        let locks = root.path().join("runtime/locks");
        std::fs::create_dir_all(&locks).expect("lock directory");
        let request = DirectGpuCommandRequest {
            argv: vec!["sh".into(), "-c".into(), "exit 7".into()],
            cwd: root.path().into(),
            environment: BTreeMap::from([
                (
                    "PATH".into(),
                    std::env::var("PATH").expect("configured PATH"),
                ),
                ("API_TOKEN".into(), "test-private-token".into()),
            ]),
            candidate_allocation: CandidateAllocation {
                candidate_ids: [A, B, C].map(str::to_owned).into(),
                source: "cli".into(),
                inventory_fingerprint: "candidate-inventory".into(),
                physical_uuids: [A, B, C].map(str::to_owned).into(),
                mig_uuids: Vec::new(),
                mig_parent_by_uuid: BTreeMap::new(),
            },
            gpu_count: count,
            minimum_free_memory_bytes: 100,
            output_dir: root.path().join("evidence"),
            runtime_root: root.path().join("runtime"),
            lock_root: locks,
            descendant_poll_seconds: 0.01,
        };
        (root, request)
    }
    fn execute_fixture(
        plan: &FrozenDirectGpuCommandPlan,
        environment: &BTreeMap<String, String>,
        events: &Rc<RefCell<Events>>,
    ) -> DirectCommandExecution {
        assert!(PathBuf::from(&plan.output_dir)
            .join("gpu_command_plan.json")
            .is_file());
        assert_eq!(
            environment["CUDA_VISIBLE_DEVICES"],
            plan.selected_ids.join(",")
        );
        assert_eq!(
            environment["NVIDIA_VISIBLE_DEVICES"],
            plan.selected_ids.join(",")
        );
        assert_eq!(environment["JAX_PLATFORMS"], "cuda");
        assert_eq!(environment["XLA_PYTHON_CLIENT_PREALLOCATE"], "false");
        assert_eq!(environment["XLA_PYTHON_CLIENT_ALLOCATOR"], "platform");
        assert_eq!(
            environment["XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR"],
            "false"
        );
        events.borrow_mut().executed = true;
        let stdout_path = PathBuf::from(&plan.output_dir).join("stdout.log");
        let stderr_path = PathBuf::from(&plan.output_dir).join("stderr.log");
        std::fs::write(&stdout_path, b"stdout-bytes\n").expect("stdout fixture");
        std::fs::write(&stderr_path, b"stderr-bytes\n").expect("stderr fixture");
        DirectCommandExecution {
            returncode: 7,
            lifecycle: DirectCommandLifecycle {
                child_pid: 1234,
                child_starttime: Some("456".into()),
                process_group_id: 1234,
                session_id: 1234,
                observed_descendant_identities: vec![(1235, "457".into())],
                descendant_quiescence: ProvenQuiescence::Proven,
                subreaper_enabled: true,
                started_at_utc: "2026-08-16T00:00:00+00:00".into(),
                finished_at_utc: "2026-08-16T00:00:01+00:00".into(),
                started_at_monotonic: 1.0,
                finished_at_monotonic: 2.0,
            },
            stdout_path,
            stderr_path,
        }
    }
    fn run_fixture(
        request: &DirectGpuCommandRequest,
        observations: Vec<ResourceObservation>,
        events: Rc<RefCell<Events>>,
        post_launch_failure: bool,
    ) -> Result<DirectGpuCommandResult> {
        let mut observations = observations.into_iter();
        let reserve_events = events.clone();
        run_direct_command_with(
            request,
            move |_, _| Ok(observations.next().expect("fresh observation required")),
            move |_| Ok(Box::new(Transaction(reserve_events.clone()))),
            move |plan, environment, _| {
                let execution = execute_fixture(plan, environment, &events);
                if post_launch_failure {
                    Err((
                        failure(
                            "fixture_diagnostic_failure",
                            "post-launch diagnostics failed",
                        ),
                        Some(Box::new(execution)),
                    ))
                } else {
                    Ok(execution)
                }
            },
        )
    }
    #[test]
    fn busy_and_unknown_exclusion_exact_environment_and_private_evidence() {
        let (_root, request) = fixture(1);
        let events = Rc::new(RefCell::new(Events::default()));
        let result = run_fixture(
            &request,
            vec![
                observation("initial", &[B], &[C]),
                observation("final", &[B], &[C]),
            ],
            events.clone(),
            false,
        )
        .expect("admitted run");
        let events = events.borrow();
        assert_eq!(events.candidates, [A]);
        assert_eq!(events.occupied, BTreeSet::from([B.into(), C.into()]));
        assert_eq!(events.closes, 1);
        assert!(events.executed);
        assert_eq!(result.execution.returncode, 7);
        assert_eq!(result.record["selected_gpu_ids"], serde_json::json!([A]));
        assert_eq!(
            result.record["lock_identities"],
            serde_json::json!([[11, 22]])
        );
        assert_eq!(
            result.record["reservation_ids"],
            serde_json::json!([format!("reservation-{A}")])
        );
        assert_eq!(result.record["shell"], false);
        assert_eq!(result.record["managed_provider_required"], false);
        for name in [
            "gpu_command_plan.json",
            "gpu_command_environment.json",
            "gpu_command_result.json",
        ] {
            let text =
                std::fs::read_to_string(request.output_dir.join(name)).expect("persisted evidence");
            assert!(!text.contains("test-private-token"));
        }
    }
    #[test]
    fn post_lock_busy_stale_memory_and_topology_changes_stop_before_execution() {
        for case in ["busy", "stale", "memory", "topology"] {
            let (_root, request) = fixture(1);
            let initial = observation("initial", &[], &[]);
            let mut final_observation = observation("final", &[], &[]);
            match case {
                "busy" => final_observation = observation("final", &[A], &[]),
                "stale" => final_observation.observation_event_id = "initial".into(),
                "memory" => {
                    final_observation.free_memory_bytes.insert(A.into(), 0);
                }
                _ => final_observation
                    .nvidia_inventory
                    .as_mut()
                    .expect("inventory")
                    .physical_uuids
                    .pop()
                    .map(|_| ())
                    .unwrap_or(()),
            }
            let events = Rc::new(RefCell::new(Events::default()));
            let error = run_fixture(
                &request,
                vec![initial, final_observation],
                events.clone(),
                false,
            )
            .err()
            .expect("preflight failure");
            assert!(["gpu_run_admission_raced", "gpu_candidate_topology_raced"]
                .contains(&error.code.as_str()));
            assert!(!events.borrow().executed);
            assert_eq!(events.borrow().closes, 1);
        }
    }
    #[test]
    fn unavailable_unknown_candidates_never_reach_reservation() {
        let (_root, request) = fixture(1);
        let events = Rc::new(RefCell::new(Events::default()));
        let error = run_fixture(
            &request,
            vec![observation("initial", &[], &[A, B, C])],
            events.clone(),
            false,
        )
        .err()
        .expect("unavailable candidates");
        assert_eq!(error.code, "gpu_candidate_unavailable");
        assert!(events.borrow().candidates.is_empty());
        assert_eq!(events.borrow().closes, 0);
    }
    #[test]
    fn multi_gpu_plan_binds_all_locks_and_visibility() {
        let (_root, request) = fixture(2);
        let events = Rc::new(RefCell::new(Events::default()));
        let result = run_fixture(
            &request,
            vec![
                observation("initial", &[], &[]),
                observation("final", &[], &[]),
            ],
            events.clone(),
            false,
        )
        .expect("two GPU run");
        assert_eq!(result.record["selected_gpu_ids"], serde_json::json!([A, B]));
        assert_eq!(
            result.record["lock_identities"],
            serde_json::json!([[11, 22], [11, 23]])
        );
        assert_eq!(events.borrow().closes, 1);
    }
    #[test]
    fn post_launch_failure_retains_quiescence_and_close_is_not_retried() {
        for fail_close in [false, true] {
            let (_root, request) = fixture(1);
            let events = Rc::new(RefCell::new(Events {
                fail_close,
                ..Events::default()
            }));
            let _ = run_fixture(
                &request,
                vec![
                    observation("initial", &[], &[]),
                    observation("final", &[], &[]),
                ],
                events.clone(),
                true,
            )
            .err()
            .expect("diagnostic failure");
            assert!(events.borrow().executed);
            assert_eq!(events.borrow().closes, 1);
            let record: serde_json::Value = serde_json::from_slice(
                &std::fs::read(request.output_dir.join("gpu_command_failure.json"))
                    .expect("failure evidence"),
            )
            .expect("failure JSON");
            assert_eq!(record["child_started"], true);
            assert_eq!(record["descendant_quiescence_proven"], true);
            if fail_close {
                assert_eq!(record["failure_code"], "gpu_reservation_release_failed");
            }
        }
    }
    #[test]
    fn completed_execution_close_exception_is_reported_once() {
        let (_root, request) = fixture(1);
        let events = Rc::new(RefCell::new(Events {
            fail_close: true,
            ..Events::default()
        }));
        let error = run_fixture(
            &request,
            vec![
                observation("initial", &[], &[]),
                observation("final", &[], &[]),
            ],
            events.clone(),
            false,
        )
        .err()
        .expect("release failure");
        assert_eq!(error.code, "gpu_reservation_release_failed");
        assert_eq!(events.borrow().closes, 1);
        let record: serde_json::Value = serde_json::from_slice(
            &std::fs::read(request.output_dir.join("gpu_command_failure.json"))
                .expect("failure evidence"),
        )
        .expect("failure JSON");
        assert!(record["release_close_failure"].is_object());
        assert_eq!(record["release_blocked"], false);
    }
    #[test]
    fn candidate_leaves_and_scheduler_visibility_keep_exact_opaque_identity() {
        let inventory = NvidiaListEvidence {
            schema_version: "nvidia-list/v1".into(),
            physical_uuids: vec![A.into(), B.into()],
            mig_uuids: vec!["MIG-cccccccc-cccc-cccc-cccc-cccccccccccc".into()],
            joins: vec![crate::execution_resource_plan::NvidiaTopologyJoin {
                parent_uuid: B.into(),
                ordinal: serde_json::json!(0),
                mig_uuid: "MIG-cccccccc-cccc-cccc-cccc-cccccccccccc".into(),
            }],
            evidence_fingerprint: "topology".into(),
        };
        let allocation = candidate_allocation(&BTreeMap::new(), &[], &inventory)
            .expect("physical and MIG leaves");
        assert_eq!(
            allocation.candidate_ids,
            vec![
                A.to_owned(),
                "MIG-cccccccc-cccc-cccc-cccc-cccccccccccc".into()
            ]
        );
        for value in ["0", "GPU-aaaa", "none", "void"] {
            assert!(candidate_allocation(
                &BTreeMap::from([("CUDA_VISIBLE_DEVICES".into(), value.into())]),
                &[],
                &inventory
            )
            .is_err());
        }
        assert!(candidate_allocation(
            &BTreeMap::from([("CUDA_VISIBLE_DEVICES".into(), A.into())]),
            &[B.into()],
            &inventory
        )
        .is_err());
    }
    #[test]
    fn busy_candidate_close_is_a_complete_release_disposition() {
        let evidence = ["busy_candidate", "released"].map(|disposition| FdReleaseEvidence {
            component: "gpu-reservation-lock".into(),
            uuid: Some(A.into()),
            disposition: disposition.into(),
            close_attempts: 1,
            error_kind: None,
            fingerprint: "fixture".into(),
        });
        assert!(release_dispositions_complete(&evidence));
        assert!(!release_dispositions_complete(&[]));
    }
}
