// @dependency-start
// contract implementation
// responsibility Owns native immutable execution-resource plans, GPU admission observations, and lifecycle evidence.
// upstream design ../../../../../documents/experiments/gpu-admission-r5-source-packet.md owns the existing transaction contract
// upstream implementation runtime_boundary.rs owns external artifact paths and stable files
// upstream implementation execution_resource_projection.rs owns the coarse Hook projection
// downstream test ../tests/direct_gpu_native.rs preserves direct admission properties
// downstream test ../tests/managed_experiment_native.rs preserves managed transaction properties
// @dependency-end

use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;

pub const PLAN_SCHEMA: &str = "execution-resource-plan/v1";
pub const HOST_RUNTIME_ROOT: &str = "/var/lib/agent-canon/runtime";
pub const CALLER_ALLOCATION_PROVENANCE: &str = "caller_scheduler_allocated_uuid_set";

#[derive(Clone, Debug, Serialize)]
pub struct Failure {
    pub code: String,
    pub message: String,
    pub details: BTreeMap<String, Value>,
}
impl std::fmt::Display for Failure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for Failure {}
impl Failure {
    pub(crate) fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            details: BTreeMap::new(),
        }
    }
}
type Result<T> = std::result::Result<T, Failure>;
pub(crate) fn canonical_fingerprint(payload: &Value) -> Result<String> {
    let value = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| Failure::new("gpu_evidence_invalid", error))?;
    let bytes = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&value)
        .map_err(|error| Failure::new("gpu_evidence_invalid", error))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

pub fn write_json_once(path: &Path, payload: &Value, allow_identical: bool) -> Result<Value> {
    let parent = crate::source_mutation::ensure_file_parent_nofollow(path)
        .map_err(|error| Failure::new("immutable_evidence_write_failed", error.to_string()))?;
    let directory = crate::runtime_boundary::RuntimeDirectory::open_nofollow(&parent, false)
        .map_err(|error| Failure::new("immutable_evidence_write_failed", error.to_string()))?;
    let name = Path::new(path.file_name().ok_or_else(|| {
        Failure::new(
            "immutable_evidence_write_failed",
            "evidence filename required",
        )
    })?);
    let value = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| Failure::new("immutable_evidence_write_failed", error))?;
    let mut bytes = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&value)
        .map_err(|error| Failure::new("immutable_evidence_write_failed", error))?;
    bytes.push(b'\n');
    let disposition = match directory
        .create_file_once(name, 0o600)
        .and_then(|mut file| {
            use std::io::Write;
            file.write_all(&bytes)?;
            file.sync_all()?;
            directory.sync_directory()
        }) {
        Ok(()) => "created",
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            let old = directory.read(name).map_err(|error| {
                Failure::new("immutable_evidence_write_failed", error.to_string())
            })?;
            if !allow_identical || old.as_deref() != Some(bytes.as_slice()) {
                return Err(Failure::new(
                    "immutable_evidence_collision",
                    format!("immutable evidence collision: {}", path.display()),
                ));
            }
            "existing_identical"
        }
        Err(error) => {
            return Err(Failure::new(
                "immutable_evidence_write_failed",
                error.to_string(),
            ))
        }
    };
    Ok(
        serde_json::json!({"path":path,"sha256":format!("{:x}",Sha256::digest(&bytes)),"bytes":bytes.len(),"disposition":disposition}),
    )
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct AbsolutePosixPath(PathBuf);
impl AbsolutePosixPath {
    pub fn parse(value: &str) -> Result<Self> {
        let path = Path::new(value);
        if !value.starts_with('/')
            || value == "/"
            || value.contains('\0')
            || value
                .split('/')
                .skip(1)
                .any(|part| ["", ".", ".."].contains(&part))
        {
            return Err(Failure::new(
                "runtime_path_invalid",
                format!("absolute normalized POSIX path required: {value}"),
            ));
        }
        let mut current = PathBuf::from("/");
        for component in path.components().filter_map(|part| {
            if let Component::Normal(name) = part {
                Some(name)
            } else {
                None
            }
        }) {
            current.push(component);
            match std::fs::symlink_metadata(&current) {
                Ok(metadata) if metadata.is_symlink() => {
                    return Err(Failure::new(
                        "runtime_path_symlink",
                        format!("runtime path contains symlink: {}", current.display()),
                    ))
                }
                Ok(_) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
                Err(error) => {
                    return Err(Failure::new("runtime_path_unreadable", error.to_string()))
                }
            }
        }
        Ok(Self(path.to_path_buf()))
    }
    pub fn path(&self) -> &Path {
        &self.0
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GpuDevice {
    pub uuid: String,
    pub free_memory_bytes: u64,
    pub memory_bytes: u64,
    pub mig_parent_uuid: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SourceFileRecord {
    pub relative_path: String,
    pub source_kind: String,
    pub st_dev: u64,
    pub st_ino: u64,
    pub st_mode: u32,
    pub st_size: u64,
    pub st_mtime_ns: i128,
    pub st_ctime_ns: i128,
    pub sha256: String,
    pub byte_count: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SourceSnapshotRecord {
    pub relative_path: String,
    pub source_dev: u64,
    pub source_ino: u64,
    pub source_byte_count: u64,
    pub source_sha256: String,
    pub snapshot_relative_path: String,
    pub snapshot_dev: u64,
    pub snapshot_ino: u64,
    pub snapshot_byte_count: u64,
    pub snapshot_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SourceSnapshotManifest {
    pub schema_version: String,
    pub source_root_dev: u64,
    pub source_root_ino: u64,
    pub source_commit: String,
    pub source_tree: String,
    pub records: Vec<SourceSnapshotRecord>,
    pub manifest_fingerprint: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SourceFreezeReceipt {
    pub schema_version: String,
    pub runtime_route: String,
    pub source_root_path: AbsolutePosixPath,
    pub source_root_dev: u64,
    pub source_root_ino: u64,
    pub source_commit: String,
    pub source_tree: String,
    pub files: Vec<SourceFileRecord>,
    pub source_paths: Vec<String>,
    pub snapshot_root_relative_path: String,
    pub snapshot_relative_path: String,
    pub snapshot_manifest_fingerprint: String,
    pub receipt_fingerprint: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GpuRunRequest {
    pub gpu_count: usize,
    pub minimum_memory_bytes_per_unit: u64,
    pub max_workers: usize,
    pub host_memory_bytes: u64,
    pub cuda_runtime_library_path: Option<String>,
    pub environment: BTreeMap<String, String>,
    pub source_root: AbsolutePosixPath,
    pub runtime_route: String,
    pub source_paths: Vec<String>,
    pub planned_chunk_ids: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResourceRequest {
    pub integration_contract: Value,
    pub xla_jax_preallocation_values: BTreeMap<String, String>,
    pub owner_id: String,
    pub parent_id: String,
    pub context_id: String,
    pub maximum_timeout_seconds: f64,
    pub argv: Vec<String>,
    pub cwd: PathBuf,
    pub environment: BTreeMap<String, String>,
    pub plan_id: String,
    pub cpu_requested_set: Vec<u32>,
    pub gpu_requested_count: usize,
    pub gpu_requested_memory_bytes: u64,
    pub gpu_allocation_provenance: String,
    pub host_memory_bytes: u64,
    pub temp_bytes: u64,
    pub ports: Vec<Value>,
    pub runtime_root: PathBuf,
    pub source_projection_root: Option<PathBuf>,
    pub run_id: String,
    pub requested_chunks: Vec<String>,
    pub lock_root: PathBuf,
    pub lock_namespace_shared_across_schedulers: bool,
    pub lock_namespace_host_safe: bool,
    pub lock_namespace_visibility_witness: String,
    pub owner_process_start_identity: String,
}
impl ResourceRequest {
    pub fn validate(&self) -> Result<()> {
        if self.owner_id.is_empty()
            || self.parent_id.is_empty()
            || self.context_id.is_empty()
            || self.maximum_timeout_seconds <= 0.0
            || self.argv.is_empty()
            || !self.cwd.is_absolute()
        {
            return Err(Failure::new(
                "resource_request_invalid",
                "resource request owner, timeout, argv and cwd are required",
            ));
        }
        if self.gpu_requested_count > 0
            && self.gpu_allocation_provenance != CALLER_ALLOCATION_PROVENANCE
        {
            return Err(Failure::new(
                "gpu_allocation_provenance_missing",
                "GPU planning requires caller/scheduler UUID-set provenance",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProcessRoot {
    pub pid: u32,
    pub starttime: String,
    pub pid_namespace: String,
    pub cgroup: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProcessIdentity {
    pub pid: u32,
    pub process_start_identity: String,
    pub gpu_uuid: String,
    pub kind: String,
    pub parent_pid: Option<u32>,
    pub relationship: String,
    pub observation_timestamp: String,
    pub observation_fingerprint: String,
    pub container_namespace_identity: String,
    pub pid_namespace: String,
    pub cgroup: String,
    pub process_root: Option<ProcessRoot>,
    pub ancestry: Vec<ProcessRoot>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResourceObservation {
    pub caller_allocated_ids: BTreeSet<String>,
    pub process_identities: Vec<ProcessIdentity>,
    pub gpu_devices: Vec<GpuDevice>,
    pub free_memory_bytes: BTreeMap<String, u64>,
    pub boot_id: String,
    pub container_visible_ids: BTreeSet<String>,
    pub observed_at: String,
    pub fingerprint: String,
    pub observation_event_id: String,
    pub cpu_available_set: Vec<u32>,
    pub host_memory_bytes: u64,
    pub temp_bytes: u64,
    pub container_id: String,
    pub unknown_gpu_ids: BTreeSet<String>,
    pub structure_tool: BTreeMap<String, String>,
    pub tool_availability: Value,
    pub nvidia_inventory: Option<NvidiaInventory>,
    pub unit_states: BTreeMap<String, GpuUnitDisposition>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum GpuUnitDisposition {
    #[serde(rename = "UNKNOWN")]
    Unknown,
    #[serde(rename = "BUSY")]
    Busy,
    #[serde(rename = "FREE")]
    Free,
}

pub fn classify_gpu_unit_states(
    devices: &[GpuDevice],
    processes: &[ProcessIdentity],
    allocated: &BTreeSet<String>,
    unknown: &BTreeSet<String>,
    xml_binding_unknown: bool,
) -> BTreeMap<String, GpuUnitDisposition> {
    let parents = devices
        .iter()
        .filter_map(|device| {
            device
                .mig_parent_uuid
                .as_ref()
                .map(|parent| (device.uuid.clone(), parent.clone()))
        })
        .collect::<BTreeMap<_, _>>();
    let mut children = BTreeMap::<String, BTreeSet<String>>::new();
    for (child, parent) in &parents {
        children
            .entry(parent.clone())
            .or_default()
            .insert(child.clone());
    }
    let busy = occupied_gpu_units(processes, devices, allocated)
        .into_iter()
        .collect::<BTreeSet<_>>();
    let mut closed = if xml_binding_unknown {
        allocated.clone()
    } else {
        BTreeSet::new()
    };
    if !xml_binding_unknown {
        for identity in unknown {
            closed.insert(identity.clone());
            if let Some(parent) = parents.get(identity) {
                closed.insert(parent.clone());
            } else if let Some(children) = children.get(identity) {
                closed.extend(children.iter().cloned());
            }
        }
        closed = closed.intersection(allocated).cloned().collect();
    }
    devices
        .iter()
        .filter(|device| allocated.contains(&device.uuid))
        .map(|device| {
            (
                device.uuid.clone(),
                if closed.contains(&device.uuid) {
                    GpuUnitDisposition::Unknown
                } else if busy.contains(&device.uuid) {
                    GpuUnitDisposition::Busy
                } else {
                    GpuUnitDisposition::Free
                },
            )
        })
        .collect()
}

pub fn scheduler_uuid_set(environment: &BTreeMap<String, String>) -> Result<BTreeSet<String>> {
    let mut observed = Vec::new();
    for key in ["CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"] {
        let Some(raw) = environment.get(key) else {
            continue;
        };
        let values = raw
            .split(',')
            .map(crate::python_text::python_strip)
            .filter(|token| !token.is_empty())
            .map(str::to_owned)
            .collect::<Vec<_>>();
        if values.is_empty()
            || values.iter().any(|token| {
                ["all", "none", "void"].contains(&token.to_ascii_lowercase().as_str())
                    || token.chars().all(|character| {
                        crate::python_cli_integer::decimal_digit_value(character).is_some()
                    })
            })
        {
            return Err(Failure::new(
                "gpu_scheduler_uuid_visibility_unproven",
                "GPU scheduler visibility must be a non-empty UUID/MIG UUID set",
            ));
        }
        observed.push(values);
    }
    if observed.is_empty() {
        return Err(Failure::new(
            "gpu_scheduler_uuid_visibility_unproven",
            "GPU request has no caller/scheduler UUID visibility",
        ));
    }
    if observed.len() == 2 && observed[0] != observed[1] {
        return Err(Failure::new(
            "gpu_scheduler_uuid_visibility_conflict",
            "CUDA and NVIDIA scheduler UUID sets disagree",
        ));
    }
    Ok(observed.remove(0).into_iter().collect())
}

pub fn occupied_gpu_units(
    processes: &[ProcessIdentity],
    devices: &[GpuDevice],
    candidates: &BTreeSet<String>,
) -> Vec<String> {
    let mut occupied = BTreeSet::new();
    for process in processes {
        occupied.insert(process.gpu_uuid.clone());
        for device in devices {
            if device.uuid == process.gpu_uuid {
                if let Some(parent) = &device.mig_parent_uuid {
                    occupied.insert(parent.clone());
                }
            }
            if device.mig_parent_uuid.as_ref() == Some(&process.gpu_uuid) {
                occupied.insert(device.uuid.clone());
            }
        }
    }
    occupied.intersection(candidates).cloned().collect()
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GpuAllocation {
    pub plan_fingerprint: String,
    pub caller_allocated_ids: Vec<String>,
    pub candidate_ids: Vec<String>,
    pub occupied_ids: Vec<String>,
    pub reserved_ids: Vec<String>,
    pub eligible_ids: Vec<String>,
    pub selected_ids: Vec<String>,
    pub reservation_ids: Vec<String>,
    pub free_memory_bytes: BTreeMap<String, u64>,
    pub occupied_process_identities: Vec<ProcessIdentity>,
    pub process_identities: Vec<ProcessIdentity>,
    pub allocation_id: String,
    pub lock_root: PathBuf,
    pub selection_order: Vec<String>,
    pub memory_bytes: BTreeMap<String, u64>,
    pub slot_id: Option<String>,
    pub requested_count: usize,
    pub requested_memory_bytes: u64,
    pub readback_fingerprint: String,
    pub lock_readback: Value,
    pub allocation_provenance: String,
    pub admission_fingerprint: Option<String>,
}
impl GpuAllocation {
    fn validate_order(&self) -> Result<()> {
        if self.selected_ids.windows(2).any(|pair| pair[0] > pair[1]) {
            return Err(Failure::new(
                "plan_state_invalid",
                "selected GPU UUIDs must use stable UUID order",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecutionResourcePlan {
    schema_version: String,
    plan_id: String,
    owner: Value,
    resources: Value,
    execution: Value,
    container: Value,
    side_effect_inventory: Value,
    plan_fingerprint: String,
    gpu_allocation: GpuAllocation,
}
impl ExecutionResourcePlan {
    pub fn plan_id(&self) -> &str {
        &self.plan_id
    }
    pub fn plan_fingerprint(&self) -> &str {
        &self.plan_fingerprint
    }
    pub fn gpu_allocation(&self) -> &GpuAllocation {
        &self.gpu_allocation
    }
    pub fn execution(&self) -> &Value {
        &self.execution
    }
    pub fn resources(&self) -> &Value {
        &self.resources
    }
    pub fn json_spec(&self) -> Value {
        serde_json::json!({"schema_version":self.schema_version,"plan_id":self.plan_id,"owner":self.owner,"resources":self.resources,"execution":self.execution,"container":self.container,"side_effect_inventory":self.side_effect_inventory})
    }
    pub fn freeze(
        request: &ResourceRequest,
        observation: &ResourceObservation,
        mut allocation: GpuAllocation,
    ) -> Result<Self> {
        request.validate()?;
        allocation.validate_order()?;
        if !["", "pending"].contains(&allocation.plan_fingerprint.as_str()) {
            return Err(Failure::new(
                "plan_state_invalid",
                "GPU allocation is already bound to another plan",
            ));
        }
        if allocation.requested_count != request.gpu_requested_count
            || allocation.requested_memory_bytes != request.gpu_requested_memory_bytes
        {
            return Err(Failure::new(
                "gpu_request_provenance_mismatch",
                "GPUAllocation request provenance differs from ResourceRequest",
            ));
        }
        if request
            .cpu_requested_set
            .iter()
            .any(|cpu| !observation.cpu_available_set.contains(cpu))
        {
            return Err(Failure::new(
                "cpu_cardinality_unavailable",
                "requested CPU set is not contained in discovered allocation",
            ));
        }
        if allocation
            .lock_readback
            .get("reservation_owner")
            .and_then(Value::as_str)
            != Some("GpuReservationTransaction")
        {
            return Err(Failure::new(
                "gpu_planner_provenance_invalid",
                "GPUAllocation was not produced by canonical admission owner",
            ));
        }
        if request.gpu_requested_count > 0 {
            if allocation.allocation_provenance != CALLER_ALLOCATION_PROVENANCE {
                return Err(Failure::new(
                    "gpu_caller_allocation_provenance_invalid",
                    "GPUAllocation is not bound to caller/scheduler UUID set",
                ));
            }
            if allocation.selected_ids.len() != request.gpu_requested_count
                || allocation.reservation_ids.len() != request.gpu_requested_count
                || allocation.selected_ids.iter().any(|uuid| {
                    !allocation.caller_allocated_ids.contains(uuid)
                        || !allocation.eligible_ids.contains(uuid)
                        || allocation.occupied_ids.contains(uuid)
                        || allocation.reserved_ids.contains(uuid)
                        || allocation.free_memory_bytes.get(uuid).copied().unwrap_or(0)
                            < request.gpu_requested_memory_bytes
                        || uuid.chars().all(|character| {
                            crate::python_cli_integer::decimal_digit_value(character).is_some()
                        })
                })
                || allocation.readback_fingerprint.is_empty()
            {
                return Err(Failure::new(
                    "gpu_allocation_contract_invalid",
                    "GPUAllocation does not prove cardinality, memory, UUID, or lease invariants",
                ));
            }
        } else if !allocation.selected_ids.is_empty() || !allocation.reservation_ids.is_empty() {
            return Err(Failure::new(
                "gpu_allocation_without_request",
                "GPU-unrequested plan cannot carry allocation or reservation state",
            ));
        }
        let plan_id = if !request.plan_id.is_empty() {
            request.plan_id.clone()
        } else if !request.run_id.is_empty() {
            request.run_id.clone()
        } else {
            let mut random = [0u8; 12];
            getrandom::getrandom(&mut random)
                .map_err(|error| Failure::new("plan_state_invalid", error.to_string()))?;
            format!(
                "plan-{}",
                random
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect::<String>()
            )
        };
        let mut environment = request.environment.clone();
        let gpu_keys = [
            "CUDA_VISIBLE_DEVICES",
            "NVIDIA_VISIBLE_DEVICES",
            "JAX_PLATFORMS",
            "XLA_PYTHON_CLIENT_PREALLOCATE",
            "XLA_PYTHON_CLIENT_ALLOCATOR",
            "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR",
            "XLA_PYTHON_CLIENT_MEM_FRACTION",
            "XLA_FLAGS",
        ];
        if request.gpu_requested_count > 0
            && ["CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"]
                .iter()
                .any(|key| environment.contains_key(*key))
        {
            return Err(Failure::new(
                "gpu_visibility_before_plan_freeze",
                "selected GPU visibility must be materialized only after plan freeze",
            ));
        }
        if request.gpu_requested_count == 0
            && (gpu_keys.iter().any(|key| environment.contains_key(*key))
                || !request.xla_jax_preallocation_values.is_empty())
        {
            return Err(Failure::new(
                "gpu_environment_without_request",
                "GPU environment cannot be injected for a GPU-unrequested plan",
            ));
        }
        environment.extend(request.xla_jax_preallocation_values.clone());
        if request.gpu_requested_count > 0 {
            if environment
                .get("XLA_PYTHON_CLIENT_PREALLOCATE")
                .is_some_and(|value| value.to_lowercase() != "false")
            {
                return Err(Failure::new(
                    "xla_preallocation_must_be_disabled",
                    "GPU execution requires canonical preallocation-disabled XLA environment",
                ));
            }
            environment.insert("XLA_PYTHON_CLIENT_PREALLOCATE".into(), "false".into());
            environment
                .entry("XLA_PYTHON_CLIENT_ALLOCATOR".to_owned())
                .or_insert_with(|| "platform".into());
            environment
                .entry("XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR".to_owned())
                .or_insert_with(|| "false".into());
        }
        let run_root = request.runtime_root.join("runs").join(&plan_id);
        let log_root = run_root.join("logs");
        let projection = request.source_projection_root.clone().unwrap_or_else(|| {
            PathBuf::from(format!("/workspace/reports/agents/{plan_id}/runtime"))
        });
        let mig_mapping = observation
            .gpu_devices
            .iter()
            .filter(|device| allocation.candidate_ids.contains(&device.uuid))
            .map(|device| (device.uuid.clone(), device.mig_parent_uuid.clone()))
            .collect::<BTreeMap<_, _>>();
        let parents = observation
            .gpu_devices
            .iter()
            .filter_map(|device| {
                device
                    .mig_parent_uuid
                    .as_ref()
                    .map(|parent| (device.uuid.clone(), parent.clone()))
            })
            .collect::<BTreeMap<_, _>>();
        let resources = serde_json::json!({"cpu":{"requested_set":request.cpu_requested_set,"allocated_set":observation.cpu_available_set,"affinity_id":null},"gpu":{"requested_count":request.gpu_requested_count,"requested_memory_bytes":request.gpu_requested_memory_bytes,"caller_allocated_ids":allocation.caller_allocated_ids,"candidate_ids":allocation.candidate_ids,"occupied_ids":allocation.occupied_ids,"reserved_ids":allocation.reserved_ids,"eligible_ids":allocation.eligible_ids,"selected_ids":allocation.selected_ids,"visible_ids":allocation.selected_ids,"allocation_id":allocation.allocation_id,"reservation_ids":allocation.reservation_ids,"admission_fingerprint":allocation.admission_fingerprint,"free_memory_bytes":allocation.free_memory_bytes,"occupied_process_identities":allocation.occupied_process_identities,"process_identities":allocation.process_identities,"lock_root":allocation.lock_root,"selection_order":allocation.selection_order,"memory_bytes":allocation.memory_bytes,"mig_mapping":mig_mapping,"slot_id":allocation.slot_id,"readback_fingerprint":allocation.readback_fingerprint,"allocation_provenance":request.gpu_allocation_provenance,"lock_readback":allocation.lock_readback,"planner_provenance":"canonical_plan_gpu_allocation","observation_timestamp":observation.observed_at,"observation_fingerprint":observation.fingerprint,"mig_parent_by_uuid":parents},"memory":{"host_bytes":observation.host_memory_bytes,"gpu_bytes":allocation.memory_bytes,"temp_bytes":observation.temp_bytes,"enforcement_mode":"hard_preflight"},"temp":{"runtime_root":request.runtime_root,"run_root":run_root,"log_root":log_root,"quota_bytes":request.temp_bytes,"disposal_policy":"record_every_side_effect"},"ports":request.ports});
        let owner = serde_json::json!({"owner_id":request.owner_id,"parent_id":request.parent_id,"context_id":request.context_id,"maximum_timeout_seconds":request.maximum_timeout_seconds,"managed_run_integration":request.integration_contract});
        let execution = serde_json::json!({"cwd":request.cwd,"argv":request.argv,"env":environment,"admission_fingerprint":allocation.admission_fingerprint,"owner_maximum_timeout_seconds":request.maximum_timeout_seconds,"idle_policy":"observe_and_wait","force_stop_policy":"no_idle_force_stop; runner_deadline_owner_only","gpu_force_kill_policy":"never","requested_chunks":request.requested_chunks});
        let structure_ref = "documents/structure/repo-structure-contract.toml";
        let mut tree = observation.structure_tool.clone();
        if tree
            .get("structure_contract_ref")
            .is_some_and(|value| value != structure_ref)
        {
            return Err(Failure::new(
                "structure_contract_authority_mismatch",
                "tree capability cannot override canonical structure contract",
            ));
        }
        tree.insert("structure_contract_ref".into(), structure_ref.into());
        let container = serde_json::json!({"runtime_root":request.runtime_root,"source_projection_root":projection,"structure_tool":"tree","tree_version":observation.structure_tool.get("version").map(String::as_str).unwrap_or("unknown"),"tree_capability":tree,"structure_contract_ref":structure_ref,"tool_availability":observation.tool_availability,"container_id":observation.container_id,"boot_id":observation.boot_id});
        let mut effects = vec![
            serde_json::json!({"id":"workspace-bind","owner":"container-runtime","target":"/workspace","policy":"allowed_source_bound_readback","disposal":"record_only"}),
            serde_json::json!({"id":"runtime-root","owner":"ExecutionResourcePlan","target":request.runtime_root,"policy":"container-local","disposal":"record_only"}),
            serde_json::json!({"id":"run-root","owner":"ExecutionResourcePlan","target":run_root,"policy":"container-local","disposal":"record_only"}),
            serde_json::json!({"id":"log-root","owner":"ExecutionResourcePlan","target":log_root,"policy":"container-local","disposal":"record_only"}),
            serde_json::json!({"id":"source-projection","owner":"ExecutionResourcePlan","target":projection,"policy":"controlled_source_bound","disposal":"record_only"}),
            serde_json::json!({"id":"runner-process-tree","owner":"ExperimentRunner","target":plan_id,"policy":"runner_owned_descendant_lifecycle","disposal":"dispose_after_terminal"}),
            serde_json::json!({"id":"gpu-leases","owner":"GpuReservationTransaction","target":request.lock_root,"policy":"shared_scheduler_visibility","disposal":"owner_callback_after_runner_join"}),
            serde_json::json!({"id":"cpu-affinity","owner":"ExperimentRunner","target":request.cpu_requested_set,"policy":"runner_owned","disposal":"dispose_if_applied"}),
            serde_json::json!({"id":"gpu-slot","owner":"ExperimentRunner","target":allocation.slot_id,"policy":"runner_owned","disposal":"dispose_if_allocated"}),
            serde_json::json!({"id":"temp-handle","owner":"ExperimentRunner","target":run_root,"policy":"retain_evidence_remove_transient","disposal":"owner_callback"}),
        ];
        effects.extend(request.ports.iter().enumerate().map(|(index,port)|serde_json::json!({"id":format!("port:{}",port.get("name").map(Value::to_string).unwrap_or_else(||index.to_string())),"owner":"ExperimentRunner","target":port,"policy":"runner_owned","disposal":"release_if_allocated"})));
        let side_effect_inventory = Value::Array(effects);
        let spec = serde_json::json!({"schema_version":PLAN_SCHEMA,"plan_id":plan_id,"owner":owner,"resources":resources,"execution":execution,"container":container,"side_effect_inventory":side_effect_inventory});
        let plan_fingerprint = canonical_fingerprint(&spec)?;
        allocation.plan_fingerprint = plan_fingerprint.clone();
        Ok(Self {
            schema_version: PLAN_SCHEMA.into(),
            plan_id,
            owner,
            resources,
            execution,
            container,
            side_effect_inventory,
            plan_fingerprint,
            gpu_allocation: allocation,
        })
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AdmittedEnvironment {
    pub schema_version: String,
    pub exact_env_map: Vec<(String, String)>,
    pub cuda_visible_devices: String,
    pub nvidia_visible_devices: String,
    pub environment_fingerprint: String,
    pub admission_fingerprint: Option<String>,
}
pub fn build_admitted_environment(
    plan: &ExecutionResourcePlan,
    runtime_route: Option<&str>,
    admission_fingerprint: Option<&str>,
) -> Result<AdmittedEnvironment> {
    let selected = &plan.gpu_allocation.selected_ids;
    if !selected.is_empty() && runtime_route != Some("MANAGED_CONTAINER") {
        return Err(Failure::new(
            "runtime_identity_route_invalid",
            "managed GPU admission requires selected managed-container route",
        ));
    }
    if !selected.is_empty() && admission_fingerprint.is_none_or(str::is_empty) {
        return Err(Failure::new(
            "admission_fingerprint_missing",
            "admitted environment requires lock-held composite admission fingerprint",
        ));
    }
    if !selected.is_empty()
        && (plan.gpu_allocation.admission_fingerprint.as_deref() != admission_fingerprint
            || plan.resources["gpu"]["admission_fingerprint"].as_str() != admission_fingerprint)
    {
        return Err(Failure::new(
            "admission_fingerprint_mismatch",
            "plan and admitted environment must reference same admission fingerprint",
        ));
    }
    let environment = plan.execution["env"].as_object().ok_or_else(|| {
        Failure::new(
            "admitted_environment_invalid",
            "frozen environment must be a string mapping",
        )
    })?;
    let mut environment = environment
        .iter()
        .map(|(key, value)| {
            value
                .as_str()
                .map(|value| (key.clone(), value.to_owned()))
                .ok_or_else(|| {
                    Failure::new(
                        "admitted_environment_invalid",
                        "frozen environment must be a string mapping",
                    )
                })
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let expected = selected.join(",");
    if !selected.is_empty() {
        if ["CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"]
            .iter()
            .any(|key| environment.contains_key(*key))
        {
            return Err(Failure::new(
                "gpu_visibility_before_plan_freeze",
                "GPU visibility must be absent before plan freeze",
            ));
        }
        environment.insert("CUDA_VISIBLE_DEVICES".into(), expected.clone());
        environment.insert("NVIDIA_VISIBLE_DEVICES".into(), expected.clone());
    }
    for name in ["CUDA_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"] {
        if environment.get(name).is_some_and(|value| {
            value.split(',').any(|token| {
                !token.is_empty()
                    && token.chars().all(|character| {
                        crate::python_cli_integer::decimal_digit_value(character).is_some()
                    })
            })
        }) {
            return Err(Failure::new(
                "admitted_environment_integer_route_forbidden",
                "GPU environment must contain opaque UUIDs, not indices",
            ));
        }
    }
    let exact = environment.into_iter().collect::<Vec<_>>();
    let payload = serde_json::json!({"schema_version":"admitted-environment/v1","exact_env_map":exact,"cuda_visible_devices":expected,"nvidia_visible_devices":expected,"admission_fingerprint":admission_fingerprint});
    let value = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| Failure::new("admitted_environment_invalid", error))?;
    let bytes = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&value)
        .map_err(|error| Failure::new("admitted_environment_invalid", error))?;
    Ok(AdmittedEnvironment {
        schema_version: "admitted-environment/v1".into(),
        exact_env_map: exact,
        cuda_visible_devices: expected.clone(),
        nvidia_visible_devices: expected,
        environment_fingerprint: format!("{:x}", Sha256::digest(bytes)),
        admission_fingerprint: admission_fingerprint.map(str::to_owned),
    })
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct NvidiaTopologyJoin {
    pub parent_uuid: String,
    pub ordinal: Value,
    pub mig_uuid: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NvidiaListEvidence {
    pub schema_version: String,
    pub physical_uuids: Vec<String>,
    pub mig_uuids: Vec<String>,
    pub joins: Vec<NvidiaTopologyJoin>,
    pub evidence_fingerprint: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NvidiaInventory {
    pub schema_version: String,
    pub physical_uuids: Vec<String>,
    pub mig_uuids: Vec<String>,
    pub joins: Vec<NvidiaTopologyJoin>,
    pub driver_version: Option<NvidiaDriverVersion>,
    pub evidence_fingerprint: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProcessOccupancyEvidence {
    pub schema_version: String,
    pub namespace_inode: u64,
    pub processes: Vec<ProcessIdentity>,
    pub occupied_uuids: Vec<String>,
    pub inventory_scope: String,
    pub evidence_fingerprint: String,
    pub unknown_uuids: Vec<String>,
    pub unit_states: BTreeMap<String, GpuUnitDisposition>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FdReleaseEvidence {
    pub component: String,
    pub uuid: Option<String>,
    pub disposition: String,
    pub close_attempts: u8,
    pub error_kind: Option<String>,
    pub fingerprint: String,
}
impl FdReleaseEvidence {
    #[cfg(target_os = "linux")]
    fn refresh_fingerprint(&mut self) -> Result<()> {
        let payload = serde_json::json!({"component":self.component,"uuid":self.uuid,"disposition":self.disposition,"close_attempts":self.close_attempts,"error_kind":self.error_kind});
        let bytes = crate::artifacts::artifact_identity::canonical_json_ascii_bytes(&payload)
            .map_err(|error| Failure::new("gpu_lock_release_record_failed", error.to_string()))?;
        self.fingerprint = format!("{:x}", Sha256::digest(bytes));
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LockReadback {
    pub runtime_root: String,
    pub filesystem_type: String,
    pub device: u64,
    pub inode: u64,
    pub selected: Vec<Value>,
    pub fingerprint: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReservationEvidence {
    pub schema_version: String,
    pub selected_uuids: Vec<String>,
    pub locks: Vec<LockReadback>,
    pub disposition: String,
    pub evidence_fingerprint: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunGpuAdmissionReceipt {
    pub schema_version: String,
    pub candidate_uuids: Vec<String>,
    pub occupied_uuids: Vec<String>,
    pub reserved_uuids: Vec<String>,
    pub selected_uuids: Vec<String>,
    pub inventory_fingerprint: String,
    pub occupancy_fingerprint: String,
    pub reservation_fingerprint: String,
    pub runtime_identity_fingerprint: String,
    pub plan_fingerprint: Option<String>,
    pub admission_fingerprint: String,
    pub lock_readback: Option<LockReadback>,
    pub effective_environment: Option<BTreeMap<String, String>>,
    pub actual_gpu_processes: Option<Vec<ProcessOccupancyEvidence>>,
    pub concurrent_run_evidence: Option<Value>,
    pub mig_evidence: Option<Value>,
    pub container_visible_uuid_mapping: Option<Value>,
    pub os_safe_lock_placement: Option<Value>,
    pub descendant_retention_evidence: Option<Value>,
}
impl RunGpuAdmissionReceipt {
    pub fn refresh_fingerprint(&mut self) -> Result<()> {
        let content = canonical_fingerprint(
            &serde_json::json!({"schema_version":self.schema_version,"candidate_uuids":self.candidate_uuids,"occupied_uuids":self.occupied_uuids,"selected_uuids":self.selected_uuids,"inventory_fingerprint":self.inventory_fingerprint,"occupancy_fingerprint":self.occupancy_fingerprint}),
        )?;
        let locks = self
            .lock_readback
            .iter()
            .map(|lock| serde_json::json!({"device":lock.device,"inode":lock.inode}))
            .collect::<Vec<_>>();
        self.admission_fingerprint = canonical_fingerprint(
            &serde_json::json!({"content_hash":content,"reservation_receipt":self.reservation_fingerprint,"lock_identity":locks,"selected_uuids":self.selected_uuids}),
        )?;
        Ok(())
    }
}

#[cfg(target_os = "linux")]
struct HeldLock {
    uuid: String,
    file: cap_std::fs::File,
    device: u64,
    inode: u64,
    reservation_id: String,
}
#[cfg(target_os = "linux")]
pub struct GpuReservationTransaction {
    root: Option<cap_std::fs::Dir>,
    root_path: PathBuf,
    device: u64,
    uid: u32,
    gid: u32,
    filesystem_type: String,
    held: Vec<HeldLock>,
    release_dispositions: Vec<FdReleaseEvidence>,
    state: String,
}
#[cfg(target_os = "linux")]
impl GpuReservationTransaction {
    pub fn new(lock_root: &AbsolutePosixPath, runtime_root: &AbsolutePosixPath) -> Result<Self> {
        use cap_std::fs::MetadataExt;
        if runtime_root.path() != Path::new(HOST_RUNTIME_ROOT) {
            return Err(Failure::new(
                "gpu_lock_namespace_not_canonical",
                "GPU reservations require canonical shared runtime root",
            ));
        }
        let path = AbsolutePosixPath::parse(&lock_root.path().to_string_lossy())?;
        let root = crate::source_mutation::open_root_nofollow(path.path())
            .map_err(|error| Failure::new("gpu_lock_namespace_unavailable", error.to_string()))?;
        let metadata = root
            .dir_metadata()
            .map_err(|error| Failure::new("gpu_lock_namespace_invalid", error.to_string()))?;
        let evidence = EvidenceFd::capture_with_timeout(
            &[
                "stat".into(),
                "-f".into(),
                "-c".into(),
                "%T".into(),
                path.path().to_string_lossy().into_owned(),
            ],
            "lock-filesystem",
            std::time::Duration::from_secs(5),
        )?;
        let bytes = evidence.read()?;
        let filesystem_type = String::from_utf8(bytes)
            .map_err(|error| Failure::new("gpu_lock_filesystem_unavailable", error.to_string()))?
            .trim()
            .to_owned();
        if !["btrfs", "ext4", "xfs"].contains(&filesystem_type.as_str()) {
            return Err(Failure::new(
                "gpu_lock_filesystem_unproved",
                "GPU lock filesystem must be btrfs, ext4, or xfs",
            ));
        }
        Ok(Self {
            root: Some(root),
            root_path: path.0,
            device: metadata.dev(),
            uid: metadata.uid(),
            gid: metadata.gid(),
            filesystem_type,
            held: Vec::new(),
            release_dispositions: Vec::new(),
            state: "CREATED".into(),
        })
    }
    fn open_candidate(&self, uuid: &str) -> Result<(cap_std::fs::File, cap_std::fs::Metadata)> {
        use cap_fs_ext::{FollowSymlinks, OpenOptionsFollowExt};
        use cap_std::fs::{MetadataExt, OpenOptionsExt};
        let name = format!("gpu-{uuid}.lock");
        let mut options = cap_std::fs::OpenOptions::new();
        options
            .read(true)
            .write(true)
            .create(true)
            .mode(0o660)
            .follow(FollowSymlinks::No);
        let root = self.root.as_ref().ok_or_else(|| {
            Failure::new(
                "gpu_reservation_transaction_repeated",
                "GPU reservation namespace is closed",
            )
        })?;
        let file = root
            .open_with(&name, &options)
            .map_err(|error| Failure::new("gpu_lock_open_failed", error.to_string()))?;
        let metadata = file
            .metadata()
            .map_err(|error| Failure::new("gpu_lock_open_failed", error.to_string()))?;
        let observed = root
            .symlink_metadata(&name)
            .map_err(|error| Failure::new("gpu_lock_open_failed", error.to_string()))?;
        if !metadata.is_file() || !observed.is_file() {
            return Err(Failure::new(
                "gpu_lock_not_regular",
                "GPU candidate lock must be regular",
            ));
        }
        if metadata.dev() != observed.dev() || metadata.ino() != observed.ino() {
            return Err(Failure::new(
                "gpu_lock_identity_changed",
                "GPU lock path identity differs from fd",
            ));
        }
        if metadata.dev() != self.device {
            return Err(Failure::new(
                "gpu_lock_device_changed",
                "GPU lock is outside shared lock filesystem",
            ));
        }
        Ok((file, metadata))
    }
    fn verify_candidate(
        &self,
        uuid: &str,
        file: &cap_std::fs::File,
        initial: &cap_std::fs::Metadata,
    ) -> Result<()> {
        use cap_std::fs::{MetadataExt, PermissionsExt};
        let final_metadata = file
            .metadata()
            .map_err(|error| Failure::new("gpu_lock_readback_tampered", error.to_string()))?;
        let root = self.root.as_ref().ok_or_else(|| {
            Failure::new(
                "gpu_reservation_transaction_repeated",
                "GPU reservation namespace is closed",
            )
        })?;
        let observed = root
            .symlink_metadata(format!("gpu-{uuid}.lock"))
            .map_err(|error| Failure::new("gpu_lock_readback_tampered", error.to_string()))?;
        if initial.dev() != final_metadata.dev()
            || initial.ino() != final_metadata.ino()
            || final_metadata.dev() != observed.dev()
            || final_metadata.ino() != observed.ino()
        {
            return Err(Failure::new(
                "gpu_lock_readback_tampered",
                "GPU candidate lock identity changed during admission",
            ));
        }
        if !final_metadata.is_file()
            || final_metadata.permissions().mode() & 0o7777 != 0o660
            || final_metadata.uid() != self.uid
            || final_metadata.gid() != self.gid
            || observed.uid() != self.uid
            || observed.gid() != self.gid
        {
            return Err(Failure::new(
                "gpu_lock_readback_invalid",
                "GPU lock type, mode or ownership is invalid",
            ));
        }
        Ok(())
    }
    fn write_record(file: &mut cap_std::fs::File, payload: &Value) -> Result<()> {
        use std::io::{Seek, SeekFrom, Write};
        let value = crate::python_json::parse_json(&payload.to_string())
            .map_err(|error| Failure::new("gpu_lock_record_write_failed", error))?;
        let mut bytes = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&value)
            .map_err(|error| Failure::new("gpu_lock_record_write_failed", error))?;
        bytes.push(b'\n');
        file.set_len(0)
            .and_then(|_| file.seek(SeekFrom::Start(0)))
            .and_then(|_| file.write_all(&bytes))
            .and_then(|_| file.sync_all())
            .map_err(|error| Failure::new("gpu_lock_record_write_failed", error.to_string()))
    }
    fn record_close(
        &mut self,
        file: cap_std::fs::File,
        uuid: Option<&str>,
        disposition: &str,
    ) -> Result<()> {
        let error = nix::unistd::close(file.into_std()).err();
        let mut evidence = FdReleaseEvidence {
            component: "gpu-reservation-lock".into(),
            uuid: uuid.map(str::to_owned),
            disposition: if error.is_some() {
                "close_ambiguous"
            } else {
                disposition
            }
            .into(),
            close_attempts: 1,
            error_kind: error.map(|_| "close_ambiguous".into()),
            fingerprint: String::new(),
        };
        evidence.refresh_fingerprint()?;
        self.release_dispositions.push(evidence);
        Ok(())
    }
    pub fn reservation_ids(&self) -> Vec<String> {
        self.held
            .iter()
            .map(|lock| lock.reservation_id.clone())
            .collect()
    }
    fn evidence(&self, disposition: &str) -> Result<ReservationEvidence> {
        let mut locks = Vec::new();
        for held in &self.held {
            let mut readback = LockReadback {
                runtime_root: HOST_RUNTIME_ROOT.into(),
                filesystem_type: self.filesystem_type.clone(),
                device: held.device,
                inode: held.inode,
                selected: Vec::new(),
                fingerprint: String::new(),
            };
            let payload = serde_json::json!({"runtime_root":readback.runtime_root,"filesystem_type":readback.filesystem_type,"device":readback.device,"inode":readback.inode,"selected":readback.selected});
            readback.fingerprint = canonical_fingerprint(&payload)?;
            locks.push(readback);
        }
        let mut evidence = ReservationEvidence {
            schema_version: "gpu-reservation/v1".into(),
            selected_uuids: self.held.iter().map(|held| held.uuid.clone()).collect(),
            locks,
            disposition: disposition.into(),
            evidence_fingerprint: String::new(),
        };
        let locks=evidence.locks.iter().map(|lock|serde_json::json!({"runtime_root":lock.runtime_root,"filesystem_type":lock.filesystem_type,"device":lock.device,"inode":lock.inode,"selected":lock.selected})).collect::<Vec<_>>();
        let payload = serde_json::json!({"schema_version":evidence.schema_version,"selected_uuids":evidence.selected_uuids,"locks":locks,"disposition":evidence.disposition});
        evidence.evidence_fingerprint = canonical_fingerprint(&payload)?;
        Ok(evidence)
    }
    pub fn try_reserve(
        &mut self,
        candidates: &[String],
        occupied: &BTreeSet<String>,
        requested_count: usize,
    ) -> Result<ReservationEvidence> {
        if self.state != "CREATED" {
            return Err(Failure::new(
                "gpu_reservation_transaction_repeated",
                "GPU reservation transaction is one-shot",
            ));
        }
        if requested_count == 0 {
            return Err(Failure::new(
                "gpu_reservation_cardinality_invalid",
                "GPU reservation requested count must be positive",
            ));
        }
        if candidates.iter().collect::<BTreeSet<_>>().len() != candidates.len() {
            return Err(Failure::new(
                "gpu_reservation_candidate_ambiguous",
                "GPU reservation candidates must be unique",
            ));
        }
        let pattern = Regex::new(r"^(GPU|MIG)-[A-Za-z0-9-]+$").unwrap();
        if candidates.iter().any(|uuid| !pattern.is_match(uuid)) {
            return Err(Failure::new(
                "gpu_reservation_uuid_unproven",
                "GPU reservation requires complete opaque UUIDs",
            ));
        }
        self.state = "ACQUIRING".into();
        let result = (|| {
            use cap_std::fs::MetadataExt;
            use std::os::fd::AsRawFd;
            use std::os::unix::fs::FileExt;
            for uuid in candidates {
                if occupied.contains(uuid) {
                    continue;
                }
                let (mut file, metadata) = self.open_candidate(uuid)?;
                #[allow(deprecated)]
                let lock = nix::fcntl::flock(
                    file.as_raw_fd(),
                    nix::fcntl::FlockArg::LockExclusiveNonblock,
                );
                if let Err(error) = lock {
                    self.record_close(
                        file,
                        Some(uuid),
                        if error == nix::errno::Errno::EAGAIN || error == nix::errno::Errno::EACCES
                        {
                            "busy_candidate"
                        } else {
                            "rolled_back"
                        },
                    )?;
                    if self
                        .release_dispositions
                        .last()
                        .is_some_and(|evidence| evidence.error_kind.is_some())
                    {
                        return Err(Failure::new(
                            "gpu_busy_candidate_close_ambiguous",
                            "busy GPU candidate close was ambiguous",
                        ));
                    }
                    if error == nix::errno::Errno::EAGAIN || error == nix::errno::Errno::EACCES {
                        continue;
                    }
                    return Err(Failure::new("gpu_lock_acquire_failed", error.to_string()));
                }
                let prepared = (|| {
                    self.verify_candidate(uuid, &file, &metadata)?;
                    let mut previous = vec![0; 65536];
                    let view = file
                        .try_clone()
                        .map_err(|error| {
                            Failure::new("gpu_lock_record_tampered", error.to_string())
                        })?
                        .into_std();
                    let count = view.read_at(&mut previous, 0).map_err(|error| {
                        Failure::new("gpu_lock_record_tampered", error.to_string())
                    })?;
                    previous.truncate(count);
                    if !previous.is_empty() {
                        let record: Value = serde_json::from_slice(&previous).map_err(|error| {
                            Failure::new("gpu_lock_record_tampered", error.to_string())
                        })?;
                        if ![
                            Some("gpu-reservation-released/v1"),
                            Some("gpu-reservation-reclaimed/v1"),
                        ]
                        .contains(&record.get("schema_version").and_then(Value::as_str))
                        {
                            return Err(Failure::new(
                                "gpu_lock_record_tampered",
                                "an acquired lock contains a non-released record",
                            ));
                        }
                    }
                    let mut random = [0u8; 12];
                    getrandom::getrandom(&mut random).map_err(|error| {
                        Failure::new("gpu_lock_record_write_failed", error.to_string())
                    })?;
                    let reservation_id = format!(
                        "reservation-{}",
                        random
                            .iter()
                            .map(|byte| format!("{byte:02x}"))
                            .collect::<String>()
                    );
                    let pid = std::process::id();
                    let stat =
                        std::fs::read_to_string(format!("/proc/{pid}/stat")).map_err(|error| {
                            Failure::new("gpu_lock_record_write_failed", error.to_string())
                        })?;
                    let start = stat
                        .rsplit_once(')')
                        .and_then(|(_, tail)| tail.split_whitespace().nth(19))
                        .ok_or_else(|| {
                            Failure::new(
                                "gpu_lock_record_write_failed",
                                "process start identity is unavailable",
                            )
                        })?;
                    let boot = std::fs::read_to_string("/proc/sys/kernel/random/boot_id").map_err(
                        |error| Failure::new("gpu_lock_record_write_failed", error.to_string()),
                    )?;
                    let payload = serde_json::json!({"schema_version":"gpu-reservation/v1","reservation_id":reservation_id,"uuid":uuid,"owner_pid":pid,"owner_process_start_identity":start,"boot_id":boot.trim(),"lock_namespace":self.root_path});
                    Self::write_record(&mut file, &payload)?;
                    Ok(reservation_id)
                })();
                match prepared {
                    Ok(reservation_id) => self.held.push(HeldLock {
                        uuid: uuid.clone(),
                        file,
                        device: metadata.dev(),
                        inode: metadata.ino(),
                        reservation_id,
                    }),
                    Err(error) => {
                        self.record_close(file, Some(uuid), "rolled_back")?;
                        return Err(error);
                    }
                }
                if self.held.len() >= requested_count {
                    self.state = "HELD".into();
                    return self.evidence("ACQUIRED");
                }
            }
            self.close()?;
            self.evidence("BUSY_CANDIDATE")
        })();
        if result.is_err() {
            self.close()?;
        }
        if self
            .release_dispositions
            .iter()
            .any(|item| item.disposition == "close_ambiguous")
        {
            return Err(Failure::new(
                "gpu_reservation_rollback_ambiguous",
                "GPU reservation rollback had an ambiguous close",
            ));
        }
        if self
            .release_dispositions
            .iter()
            .any(|item| item.error_kind.is_some())
        {
            return Err(Failure::new(
                "gpu_reservation_rollback_failed",
                "GPU reservation rollback recorded a release failure",
            ));
        }
        result
    }
    pub fn close(&mut self) -> Result<Vec<FdReleaseEvidence>> {
        if self.state == "CLOSED" {
            return Ok(self.release_dispositions.clone());
        }
        self.state = "ROLLING_BACK".into();
        while let Some(mut held) = self.held.pop() {
            let payload = serde_json::json!({"schema_version":"gpu-reservation-released/v1","uuid":held.uuid,"released_at":time::OffsetDateTime::now_utc().format(&time::format_description::well_known::Rfc3339).map_err(|error|Failure::new("gpu_lock_release_record_failed",error.to_string()))?});
            let failure = Self::write_record(&mut held.file, &payload).err();
            self.record_close(held.file, Some(&held.uuid), "released")?;
            if let Some(failure) = failure {
                if let Some(evidence) = self.release_dispositions.last_mut() {
                    if evidence.error_kind.is_none() {
                        evidence.error_kind = Some(failure.code);
                    }
                    evidence.refresh_fingerprint()?;
                }
            }
        }
        if let Some(root) = self.root.take() {
            nix::unistd::close(root.into_std_file()).map_err(|error| {
                Failure::new("gpu_lock_root_close_ambiguous", error.to_string())
            })?;
        }
        self.state = "CLOSED".into();
        Ok(self.release_dispositions.clone())
    }
}
pub fn process_occupancy(
    inventory: &NvidiaInventory,
    namespace_inode: u64,
    processes: &[ProcessIdentity],
    unknown: &BTreeSet<String>,
    binding_unknown: bool,
    inventory_disposition: &str,
) -> Result<ProcessOccupancyEvidence> {
    if namespace_inode == 0 {
        return Err(Failure::new(
            "gpu_namespace_identity_unproven",
            "GPU occupancy requires a positive local namespace inode",
        ));
    }
    if !["COMPLETE", "COMPLETE_EMPTY"].contains(&inventory_disposition) {
        return Err(Failure::new(
            "gpu_process_inventory_unproven",
            "GPU process inventory is not proven complete",
        ));
    }
    if inventory_disposition == "COMPLETE_EMPTY" && !processes.is_empty() {
        return Err(Failure::new(
            "gpu_process_inventory_conflict",
            "complete-empty process evidence contains process identities",
        ));
    }
    let known = inventory
        .physical_uuids
        .iter()
        .chain(&inventory.mig_uuids)
        .cloned()
        .collect::<BTreeSet<_>>();
    let valid_uuid = Regex::new(r"^(GPU|MIG)-[A-Za-z0-9-]+$").unwrap();
    if known.len() != inventory.physical_uuids.len() + inventory.mig_uuids.len()
        || inventory
            .physical_uuids
            .iter()
            .any(|uuid| !uuid.starts_with("GPU-") || !valid_uuid.is_match(uuid))
        || inventory
            .mig_uuids
            .iter()
            .any(|uuid| !uuid.starts_with("MIG-") || !valid_uuid.is_match(uuid))
    {
        return Err(Failure::new(
            "gpu_process_topology_unproven",
            "GPU topology UUIDs are not unique and opaque",
        ));
    }
    let mut join_keys = BTreeSet::new();
    let mut joined = BTreeSet::new();
    for join in &inventory.joins {
        let ordinal = join.ordinal.to_string();
        if !inventory.physical_uuids.contains(&join.parent_uuid)
            || !inventory.mig_uuids.contains(&join.mig_uuid)
            || ordinal.is_empty()
            || !ordinal.bytes().all(|value| value.is_ascii_digit())
            || !join_keys.insert((join.parent_uuid.clone(), ordinal))
            || !joined.insert(join.mig_uuid.clone())
        {
            return Err(Failure::new(
                "gpu_process_topology_unproven",
                "GPU topology join is outside inventory",
            ));
        }
    }
    let parents = inventory
        .joins
        .iter()
        .map(|join| (join.mig_uuid.clone(), join.parent_uuid.clone()))
        .collect::<BTreeMap<_, _>>();
    let devices = known
        .iter()
        .map(|uuid| GpuDevice {
            uuid: uuid.clone(),
            free_memory_bytes: 0,
            memory_bytes: 0,
            mig_parent_uuid: parents.get(uuid).cloned(),
        })
        .collect::<Vec<_>>();
    let mut ordered = processes.to_vec();
    ordered.sort_by(|left, right| {
        (
            &left.gpu_uuid,
            &left.kind,
            left.pid,
            &left.process_start_identity,
        )
            .cmp(&(
                &right.gpu_uuid,
                &right.kind,
                right.pid,
                &right.process_start_identity,
            ))
    });
    let mut seen = BTreeSet::new();
    let mut starts = BTreeMap::new();
    let namespace = format!("pid:[{namespace_inode}]");
    for process in &ordered {
        if !seen.insert((
            process.pid,
            process.process_start_identity.clone(),
            process.gpu_uuid.clone(),
            process.kind.clone(),
        )) {
            return Err(Failure::new(
                "gpu_process_identity_ambiguous",
                "GPU inventory repeats a process identity",
            ));
        }
        if starts
            .insert(process.pid, process.process_start_identity.clone())
            .is_some_and(|old| old != process.process_start_identity)
        {
            return Err(Failure::new(
                "gpu_process_identity_ambiguous",
                "GPU process PID has conflicting start identities",
            ));
        }
        if process.container_namespace_identity != namespace {
            return Err(Failure::new(
                "gpu_process_namespace_mismatch",
                "GPU identity is not proven in local namespace",
            ));
        }
        if !known.contains(&process.gpu_uuid) {
            return Err(Failure::new(
                "gpu_process_uuid_visibility_unproven",
                "GPU identity is not bound to an observed UUID",
            ));
        }
    }
    let states = classify_gpu_unit_states(&devices, &ordered, &known, unknown, binding_unknown);
    let closed = states
        .iter()
        .filter(|(_, state)| **state == GpuUnitDisposition::Unknown)
        .map(|(uuid, _)| uuid.clone())
        .collect::<Vec<_>>();
    let occupied = occupied_gpu_units(&ordered, &devices, &known);
    let payload = serde_json::json!({"schema_version":"gpu-process-occupancy/v1","namespace_inode":namespace_inode,"processes":ordered,"occupied_uuids":occupied,"unknown_uuids":closed,"unit_states":states,"inventory_scope":"local-namespace-complete"});
    let value = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| Failure::new("gpu_process_topology_unproven", error))?;
    let canonical = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&value)
        .map_err(|error| Failure::new("gpu_process_topology_unproven", error))?;
    Ok(ProcessOccupancyEvidence {
        schema_version: "gpu-process-occupancy/v1".into(),
        namespace_inode,
        processes: ordered,
        occupied_uuids: occupied,
        inventory_scope: "local-namespace-complete".into(),
        evidence_fingerprint: format!("{:x}", Sha256::digest(canonical)),
        unknown_uuids: closed,
        unit_states: states,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(target_os = "linux")]
    fn transaction_fixture(path: &Path) -> GpuReservationTransaction {
        use cap_std::fs::MetadataExt;
        let root =
            crate::source_mutation::open_root_nofollow(path).expect("fixture directory handle");
        let metadata = root.dir_metadata().expect("root metadata");
        GpuReservationTransaction {
            root: Some(root),
            root_path: path.into(),
            device: metadata.dev(),
            uid: metadata.uid(),
            gid: metadata.gid(),
            filesystem_type: "test-local-flock".into(),
            held: Vec::new(),
            release_dispositions: Vec::new(),
            state: "CREATED".into(),
        }
    }
    #[cfg(target_os = "linux")]
    #[test]
    fn actual_flock_excludes_busy_candidate_and_releases_every_owned_descriptor_once() {
        use std::os::unix::fs::PermissionsExt;
        const ISOLATED: &str = "AGENT_CANON_TEST_ISOLATED_FLOCK";
        if std::env::var_os(ISOLATED).is_none() {
            let output = std::process::Command::new(std::env::current_exe().expect("test executable"))
                .args(["--exact", "execution_resource_plan::tests::actual_flock_excludes_busy_candidate_and_releases_every_owned_descriptor_once", "--nocapture"])
                .env(ISOLATED, "1")
                .output()
                .expect("isolated lock fixture process");
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            return;
        }
        let root = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("lock fixture");
        let candidates = ["GPU-fixture-a".to_owned(), "GPU-fixture-b".to_owned()];
        for uuid in &candidates {
            let path = root.path().join(format!("gpu-{uuid}.lock"));
            std::fs::write(&path, b"").expect("empty lock input");
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o660))
                .expect("shared lock permissions");
        }
        let mut first = transaction_fixture(root.path());
        let first_receipt = first
            .try_reserve(&candidates[..1], &BTreeSet::new(), 1)
            .expect("first reservation");
        for held in &first.held {
            let flags = nix::fcntl::fcntl(&held.file, nix::fcntl::FcntlArg::F_GETFD)
                .expect("lock descriptor flags");
            assert_ne!(flags & nix::fcntl::FdFlag::FD_CLOEXEC.bits(), 0);
        }
        assert_eq!(first_receipt.selected_uuids, &candidates[..1]);
        let mut second = transaction_fixture(root.path());
        let second_receipt = second
            .try_reserve(&candidates, &BTreeSet::new(), 1)
            .expect("skip occupied flock");
        assert_eq!(second_receipt.selected_uuids, &candidates[1..]);
        assert_eq!(second.reservation_ids().len(), 1);
        let released = second.close().expect("second close");
        assert_eq!(released.len(), 2);
        assert_eq!(released[0].disposition, "busy_candidate");
        assert_eq!(released[1].disposition, "released");
        assert!(released
            .iter()
            .all(|item| item.close_attempts == 1 && item.error_kind.is_none()));
        assert_eq!(
            serde_json::to_value(second.close().expect("idempotent readback"))
                .expect("release JSON"),
            serde_json::to_value(&released).expect("release JSON")
        );
        first.close().expect("first close");
        let mut third = transaction_fixture(root.path());
        assert_eq!(
            third
                .try_reserve(&candidates, &BTreeSet::new(), 2)
                .expect("both locks released")
                .selected_uuids,
            candidates
        );
        third.close().expect("final release");
    }
    #[cfg(target_os = "linux")]
    #[test]
    fn dropped_unproven_reservation_keeps_active_record_and_cannot_be_reacquired() {
        use std::os::unix::fs::PermissionsExt;
        const ISOLATED: &str = "AGENT_CANON_TEST_ISOLATED_FLOCK";
        if std::env::var_os(ISOLATED).is_none() {
            let output = std::process::Command::new(std::env::current_exe().expect("test executable"))
                .args(["--exact", "execution_resource_plan::tests::dropped_unproven_reservation_keeps_active_record_and_cannot_be_reacquired", "--nocapture"])
                .env(ISOLATED, "1")
                .output()
                .expect("isolated reservation-drop fixture process");
            assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
            return;
        }
        let root = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("lock fixture");
        let uuid = "GPU-unproven-lifecycle";
        let path = root.path().join(format!("gpu-{uuid}.lock"));
        std::fs::write(&path, b"").expect("empty lock input");
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o660))
            .expect("shared lock permissions");

        let mut unproven = transaction_fixture(root.path());
        let receipt = unproven
            .try_reserve(&[uuid.into()], &BTreeSet::new(), 1)
            .expect("initial lock acquired");
        assert_eq!(receipt.disposition, "ACQUIRED");
        let active_record = std::fs::read(&path).expect("active record reads");
        assert_eq!(
            serde_json::from_slice::<Value>(&active_record).unwrap()["schema_version"],
            "gpu-reservation/v1"
        );

        drop(unproven);

        assert_eq!(
            std::fs::read(&path).expect("record remains active"),
            active_record
        );
        let mut retry = transaction_fixture(root.path());
        let rejected = retry
            .try_reserve(&[uuid.into()], &BTreeSet::new(), 1)
            .expect_err("unproven active record cannot be reacquired");
        assert_eq!(rejected.code, "gpu_lock_record_tampered");
        assert_eq!(
            std::fs::read(&path).expect("record remains active"),
            active_record
        );
    }
    #[cfg(target_os = "linux")]
    #[test]
    fn symlink_lock_preserves_referent_and_reservation_is_one_shot() {
        use std::os::unix::fs::symlink;
        let root = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("lock fixture");
        let referent = root.path().join("user-file");
        std::fs::write(&referent, b"preserve").expect("user fixture");
        symlink(&referent, root.path().join("gpu-GPU-symlink.lock")).expect("symlink fixture");
        let mut transaction = transaction_fixture(root.path());
        assert_eq!(
            transaction
                .try_reserve(&["GPU-symlink".into()], &BTreeSet::new(), 1)
                .expect_err("symlink lock rejected")
                .code,
            "gpu_lock_open_failed"
        );
        assert_eq!(
            std::fs::read(&referent).expect("referent bytes"),
            b"preserve"
        );
        assert_eq!(
            transaction
                .try_reserve(&[], &BTreeSet::new(), 1)
                .expect_err("one-shot transaction")
                .code,
            "gpu_reservation_transaction_repeated"
        );
    }
    fn fixture_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../../tests/fixtures/nvidia")
    }
    fn fixture(name: &str) -> EvidenceFd {
        let path = fixture_root().join(name);
        EvidenceFd::from_file(
            std::fs::File::open(path).expect("raw NVIDIA fixture"),
            name.into(),
        )
        .expect("retained evidence")
    }
    #[test]
    fn captured_nvidia_parser_contracts_keep_bytes_topology_and_failure_codes() {
        let manifest: Value = serde_json::from_slice(
            &std::fs::read(fixture_root().join("manifest.json")).expect("fixture manifest"),
        )
        .expect("manifest JSON");
        let mut count = 0;
        for record in manifest["records"].as_array().expect("records") {
            let parser = record["parser"].as_str().expect("parser");
            if parser == "serializer_only" {
                continue;
            }
            let name = record["raw_file"].as_str().expect("raw filename");
            let evidence = fixture(name);
            assert_eq!(
                evidence.sha256,
                record["raw_sha256"].as_str().expect("captured hash")
            );
            let actual = match parser {
                "nvidia_smi_list" => parse_nvidia_smi_list(&evidence)
                    .map(|value| serde_json::to_value(value).expect("list record")),
                "nvidia_smi_xml" => parse_nvidia_smi_xml(&evidence)
                    .map(|value| serde_json::to_value(value).expect("XML record")),
                "nvidia_driver_version" => parse_nvidia_driver_version(&evidence)
                    .map(|value| serde_json::to_value(value).expect("driver record")),
                _ => panic!("unselected parser {parser}"),
            };
            let expected = &record["expected"];
            if expected["accepted"] == true {
                let actual = actual.unwrap_or_else(|error| panic!("{name}: {}", error.code));
                for key in [
                    "physical_uuids",
                    "mig_uuids",
                    "joins",
                    "major",
                    "minor",
                    "patch",
                    "raw",
                ] {
                    if let Some(value) = expected.get(key) {
                        assert_eq!(&actual[key], value, "{name}: {key}");
                    }
                }
                if let Some(disposition) = expected.get("disposition") {
                    assert_eq!(
                        &actual["process_inventory_disposition"], disposition,
                        "{name}"
                    );
                }
                if name == "nvidia_smi_query.xml" {
                    assert_eq!(
                        actual["processing_instructions"],
                        serde_json::json!(["fixture nvidia-smi"])
                    );
                    assert_eq!(
                        actual["comments"],
                        serde_json::json!([" fixture topology "])
                    );
                }
            } else {
                assert_eq!(
                    actual.expect_err("invalid fixture must fail").code,
                    expected["failure_code"].as_str().expect("expected failure"),
                    "{name}"
                );
            }
            count += 1;
        }
        assert_eq!(count, 18);
    }
    #[test]
    fn historical_accounting_is_excluded_from_live_occupancy() {
        let list = fixture("nvidia_smi_list.txt");
        let xml = fixture("nvidia_smi_query_accounted_processes.xml");
        let allocated = BTreeSet::from(["GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".to_owned()]);
        let observation = observe_structured_nvidia(&list, &xml, None, &allocated)
            .expect("complete live process inventory");
        assert!(observation.processes.is_empty());
        assert!(observation.unknown_gpu_ids.is_empty());
        assert_eq!(
            observation.unit_states["GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            GpuUnitDisposition::Free
        );
        assert_eq!(
            observation.process_inventory_visibility["units"]
                ["GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["process_count"],
            0
        );
    }
    #[test]
    fn unresolved_unselected_inventory_remains_unknown_not_free() {
        let allocated = "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".to_owned();
        let unresolved = "GPU-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".to_owned();
        let inventory = NvidiaInventory {
            schema_version: "nvidia-inventory/v1".into(),
            physical_uuids: vec![allocated.clone(), unresolved.clone()],
            mig_uuids: Vec::new(),
            joins: Vec::new(),
            driver_version: None,
            evidence_fingerprint: "fixture-inventory".into(),
        };
        let occupancy = process_occupancy(
            &inventory,
            42,
            &[],
            &BTreeSet::from([unresolved.clone()]),
            false,
            "COMPLETE_EMPTY",
        )
        .expect("complete process inventory with an unresolved holder");
        assert_eq!(occupancy.occupied_uuids, Vec::<String>::new());
        assert_eq!(occupancy.unknown_uuids, vec![unresolved.clone()]);
        assert_eq!(occupancy.unit_states[&allocated], GpuUnitDisposition::Free);
        assert_eq!(
            occupancy.unit_states[&unresolved],
            GpuUnitDisposition::Unknown
        );
    }
    #[test]
    fn retained_evidence_detects_mutation_and_immutable_outputs_collide() {
        use std::io::Write;
        let mut file = tempfile::tempfile().expect("evidence fixture");
        file.write_all(b"570.124.06\n").expect("driver bytes");
        let mut other = file.try_clone().expect("fixture mutator");
        let evidence = EvidenceFd::from_file(file, "driver".into()).expect("capture");
        other.set_len(0).expect("truncate");
        other.write_all(b"changed\n").expect("mutation");
        assert_eq!(
            parse_nvidia_driver_version(&evidence)
                .expect_err("mutated evidence rejected")
                .code,
            "gpu_evidence_raced"
        );
        let root = tempfile::tempdir_in(
            std::env::temp_dir()
                .canonicalize()
                .expect("canonical temporary parent"),
        )
        .expect("fixture root");
        let path = root.path().join("once.json");
        let payload = serde_json::json!({"result":1});
        assert_eq!(
            write_json_once(&path, &payload, false).expect("first write")["disposition"],
            "created"
        );
        assert_eq!(
            write_json_once(&path, &payload, false)
                .expect_err("collision")
                .code,
            "immutable_evidence_collision"
        );
        assert_eq!(
            write_json_once(&path, &payload, true).expect("explicit identical acceptance")
                ["disposition"],
            "existing_identical"
        );
        assert_eq!(
            std::fs::read(path).expect("original bytes"),
            b"{\"result\":1}\n"
        );
    }
}
pub struct EvidenceFd {
    file: std::fs::File,
    pub source_name: String,
    pub st_dev: u64,
    pub st_ino: u64,
    pub byte_count: u64,
    pub sha256: String,
}
impl EvidenceFd {
    #[cfg(target_os = "linux")]
    pub fn capture(command: &[String], source_name: &str) -> Result<Self> {
        Self::capture_with_timeout(command, source_name, std::time::Duration::from_secs(30))
    }
    #[cfg(target_os = "linux")]
    fn capture_with_timeout(
        command: &[String],
        source_name: &str,
        timeout: std::time::Duration,
    ) -> Result<Self> {
        use std::io::{Read, Write};
        use std::process::{Command, Stdio};
        use std::time::{Duration, Instant};
        if command.is_empty() || source_name.is_empty() || command.iter().any(String::is_empty) {
            return Err(Failure::new(
                "gpu_evidence_command_invalid",
                "structured evidence capture requires a non-empty string command",
            ));
        }
        let mut child = Command::new(&command[0])
            .args(&command[1..])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| Failure::new("gpu_evidence_capture_failed", error.to_string()))?;
        let stdout = child.stdout.take().ok_or_else(|| {
            Failure::new("gpu_evidence_capture_failed", "stdout capture unavailable")
        })?;
        let stderr = child.stderr.take().ok_or_else(|| {
            Failure::new("gpu_evidence_capture_failed", "stderr capture unavailable")
        })?;
        let reader = |mut pipe: Box<dyn Read + Send>| {
            std::thread::spawn(move || {
                let mut bytes = Vec::new();
                pipe.read_to_end(&mut bytes).map(|_| bytes)
            })
        };
        let output = reader(Box::new(stdout));
        let error_output = reader(Box::new(stderr));
        let started = Instant::now();
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break Ok(status),
                Ok(None) if started.elapsed() < timeout => {
                    std::thread::sleep(Duration::from_millis(10))
                }
                _ => {
                    let _ = child.kill();
                    let _ = child.wait();
                    break Err(Failure::new(
                        "gpu_evidence_capture_failed",
                        "structured evidence producer timed out",
                    ));
                }
            }
        };
        let bytes = output
            .join()
            .map_err(|_| Failure::new("gpu_evidence_capture_failed", "output reader failed"))?
            .map_err(|error| Failure::new("gpu_evidence_capture_failed", error.to_string()))?;
        let _ = error_output
            .join()
            .map_err(|_| Failure::new("gpu_evidence_capture_failed", "stderr reader failed"))?
            .map_err(|error| Failure::new("gpu_evidence_capture_failed", error.to_string()))?;
        if !status?.success() {
            return Err(Failure::new(
                "gpu_evidence_capture_failed",
                "structured evidence producer returned a failure",
            ));
        }
        let descriptor = rustix::fs::memfd_create(
            format!("agent-canon-{source_name}"),
            rustix::fs::MemfdFlags::CLOEXEC,
        )
        .map_err(|error| Failure::new("gpu_evidence_fd_unavailable", error.to_string()))?;
        let mut file = std::fs::File::from(descriptor);
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|error| Failure::new("gpu_evidence_fd_unavailable", error.to_string()))?;
        Self::from_file(file, source_name.into())
    }
    pub fn from_file(file: std::fs::File, source_name: String) -> Result<Self> {
        let metadata = file
            .metadata()
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        if !metadata.is_file() {
            return Err(Failure::new(
                "gpu_evidence_not_regular",
                "NVIDIA evidence fd must reference a regular file",
            ));
        }
        #[cfg(unix)]
        let (device, inode) = {
            use std::os::unix::fs::MetadataExt;
            (metadata.dev(), metadata.ino())
        };
        #[cfg(not(unix))]
        let (device, inode) = (0, 0);
        let length = usize::try_from(metadata.len())
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(length)
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        bytes.resize(length, 0);
        let mut offset = 0;
        while offset < bytes.len() {
            #[cfg(unix)]
            let count = {
                use std::os::unix::fs::FileExt;
                file.read_at(&mut bytes[offset..], offset as u64)
            };
            #[cfg(windows)]
            let count = {
                use std::os::windows::fs::FileExt;
                file.seek_read(&mut bytes[offset..], offset as u64)
            };
            let count = count
                .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
            if count == 0 {
                return Err(Failure::new(
                    "gpu_evidence_raced",
                    "NVIDIA evidence ended before captured length",
                ));
            }
            offset += count;
        }
        Ok(Self {
            file,
            source_name,
            st_dev: device,
            st_ino: inode,
            byte_count: metadata.len(),
            sha256: format!("{:x}", Sha256::digest(bytes)),
        })
    }
    fn read(&self) -> Result<Vec<u8>> {
        let stream = &self.file;
        let before = stream
            .metadata()
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        if !before.is_file() || before.len() != self.byte_count {
            return Err(Failure::new(
                "gpu_evidence_raced",
                "NVIDIA evidence identity changed",
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if before.dev() != self.st_dev || before.ino() != self.st_ino {
                return Err(Failure::new(
                    "gpu_evidence_raced",
                    "NVIDIA evidence fd identity changed",
                ));
            }
        }
        let length = usize::try_from(before.len())
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        let mut bytes = Vec::new();
        bytes
            .try_reserve_exact(length)
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        bytes.resize(length, 0);
        let mut offset = 0;
        while offset < bytes.len() {
            #[cfg(unix)]
            let count = {
                use std::os::unix::fs::FileExt;
                stream.read_at(&mut bytes[offset..], offset as u64)
            };
            #[cfg(windows)]
            let count = {
                use std::os::windows::fs::FileExt;
                stream.seek_read(&mut bytes[offset..], offset as u64)
            };
            let count = count
                .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
            if count == 0 {
                return Err(Failure::new(
                    "gpu_evidence_raced",
                    "NVIDIA evidence ended before captured length",
                ));
            }
            offset += count;
        }
        let after = stream
            .metadata()
            .map_err(|error| Failure::new("gpu_evidence_unreadable", error.to_string()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::MetadataExt;
            if after.dev() != before.dev()
                || after.ino() != before.ino()
                || after.mode() != before.mode()
            {
                return Err(Failure::new(
                    "gpu_evidence_raced",
                    "NVIDIA evidence mode or identity changed during parsing",
                ));
            }
        }
        if !after.is_file()
            || after.len() != self.byte_count
            || bytes.len() as u64 != after.len()
            || format!("{:x}", Sha256::digest(&bytes)) != self.sha256
        {
            return Err(Failure::new(
                "gpu_evidence_raced",
                "NVIDIA evidence changed during parsing",
            ));
        }
        Ok(bytes)
    }
}

static PHYSICAL: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^GPU ([0-9]+): ([^\n]+) \(UUID: (GPU-[A-Za-z0-9-]+)\)$").unwrap()
});
static MIG: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[ ]{2,}MIG ([0-9]+c\.)?[0-9]+g\.[0-9]+gb[ ]{2,}Device[ ]{2}([0-9]+): \(UUID: (MIG-[A-Za-z0-9-]+)\)$").unwrap()
});
static DRIVER: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(0|[1-9][0-9]*)\.([0-9]+)(?:\.([0-9]+))?$").unwrap());
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NvidiaDriverVersion {
    pub major: Value,
    pub minor: Value,
    pub patch: Option<Value>,
    pub raw: String,
}
pub fn parse_nvidia_driver_version(evidence: &EvidenceFd) -> Result<NvidiaDriverVersion> {
    let bytes = evidence.read()?;
    let text = std::str::from_utf8(&bytes)
        .map_err(|error| Failure::new("gpu_driver_version_malformed", error.to_string()))?;
    if !text.ends_with('\n') || text.matches('\n').count() != 1 {
        return Err(Failure::new(
            "gpu_driver_version_malformed",
            "driver evidence must contain one LF-terminated value",
        ));
    }
    let raw = &text[..text.len() - 1];
    let capture = DRIVER.captures(raw).ok_or_else(|| {
        Failure::new(
            "gpu_driver_version_malformed",
            "driver version does not match approved grammar",
        )
    })?;
    let integer = |value: &str| -> Result<Value> {
        let value = crate::python_cli_integer::parse(value).ok_or_else(|| {
            Failure::new(
                "gpu_driver_version_malformed",
                "invalid driver version integer",
            )
        })?;
        serde_json::from_str(&value.to_string())
            .map_err(|error| Failure::new("gpu_driver_version_malformed", error.to_string()))
    };
    Ok(NvidiaDriverVersion {
        major: integer(&capture[1])?,
        minor: integer(&capture[2])?,
        patch: capture
            .get(3)
            .map(|value| integer(value.as_str()))
            .transpose()?,
        raw: raw.into(),
    })
}

pub fn parse_nvidia_smi_list(evidence: &EvidenceFd) -> Result<NvidiaListEvidence> {
    let bytes = evidence.read()?;
    if bytes.starts_with(&[0xef, 0xbb, 0xbf]) || bytes.contains(&0) {
        return Err(Failure::new(
            "gpu_structured_probe_malformed",
            "NVIDIA evidence must be UTF-8 without BOM or NUL bytes",
        ));
    }
    let text = std::str::from_utf8(&bytes)
        .map_err(|error| Failure::new("gpu_structured_probe_malformed", error.to_string()))?;
    if !text.ends_with('\n') || text.contains(['\r', '\t']) {
        return Err(Failure::new(
            "gpu_list_probe_malformed",
            "nvidia-smi -L evidence must be strict LF output",
        ));
    }
    let mut physical = Vec::new();
    let mut mig = Vec::new();
    let mut joins = Vec::new();
    let mut parent = None::<String>;
    let mut ordinals = BTreeSet::new();
    for line in text[..text.len() - 1].split('\n') {
        if line.is_empty() || line.ends_with(' ') {
            return Err(Failure::new(
                "gpu_list_probe_malformed",
                "nvidia-smi -L evidence contains empty lines or trailing spaces",
            ));
        }
        if let Some(capture) = PHYSICAL.captures(line) {
            let uuid = capture[3].to_owned();
            if physical.contains(&uuid) {
                return Err(Failure::new(
                    "gpu_uuid_duplicate",
                    "nvidia-smi -L evidence repeats a physical UUID",
                ));
            }
            parent = Some(uuid.clone());
            physical.push(uuid);
            continue;
        }
        let capture = MIG.captures(line).ok_or_else(|| {
            Failure::new(
                "gpu_list_probe_malformed",
                "nvidia-smi -L evidence contains an unmatched line",
            )
        })?;
        let parent = parent.as_ref().ok_or_else(|| {
            Failure::new(
                "gpu_mig_parent_missing",
                "MIG evidence has no immediately preceding physical parent",
            )
        })?;
        let integer = crate::python_cli_integer::parse(&capture[2])
            .ok_or_else(|| Failure::new("gpu_list_probe_malformed", "invalid MIG ordinal"))?;
        let ordinal: Value = serde_json::from_str(&integer.to_string())
            .map_err(|error| Failure::new("gpu_list_probe_malformed", error.to_string()))?;
        let uuid = capture[3].to_owned();
        if mig.contains(&uuid) {
            return Err(Failure::new(
                "gpu_uuid_duplicate",
                "nvidia-smi -L evidence repeats a MIG UUID",
            ));
        }
        if !ordinals.insert((parent.clone(), ordinal.to_string())) {
            return Err(Failure::new(
                "gpu_mig_parent_ordinal_duplicate",
                "nvidia-smi -L repeats a parent/ordinal join",
            ));
        }
        mig.push(uuid.clone());
        joins.push(NvidiaTopologyJoin {
            parent_uuid: parent.clone(),
            ordinal,
            mig_uuid: uuid,
        });
    }
    let payload = serde_json::json!({"source_name":evidence.source_name,"st_dev":evidence.st_dev,"st_ino":evidence.st_ino,"byte_count":evidence.byte_count,"sha256":evidence.sha256,
        "payload":{"physical_uuids":physical,"mig_uuids":mig,"joins":joins}});
    let parsed = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| Failure::new("gpu_list_probe_malformed", error))?;
    let canonical = crate::python_json::canonical_json_ascii_bytes(&parsed)
        .map_err(|error| Failure::new("gpu_list_probe_malformed", error))?;
    Ok(NvidiaListEvidence {
        schema_version: "nvidia-list/v1".into(),
        physical_uuids: physical,
        mig_uuids: mig,
        joins,
        evidence_fingerprint: format!("{:x}", Sha256::digest(canonical)),
    })
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParsedNvidiaXml {
    pub schema_version: String,
    pub physical_uuids: Vec<String>,
    pub mig_uuids: Vec<String>,
    pub joins: Vec<NvidiaTopologyJoin>,
    pub processing_instructions: Vec<String>,
    pub comments: Vec<String>,
    pub process_inventory_disposition: String,
    pub evidence_fingerprint: String,
}
#[derive(Default)]
struct XmlNode {
    name: String,
    text: String,
    children: Vec<usize>,
    parent: Option<usize>,
}
#[derive(Default)]
struct XmlTree {
    nodes: Vec<XmlNode>,
    stack: Vec<usize>,
    comments: Vec<String>,
    instructions: Vec<String>,
}
impl expat::internal::parse::Handler for XmlTree {
    fn start_element(&mut self, name: &[u8], _: &[(&[u8], &[u8])], _: i32) {
        let index = self.nodes.len();
        let name = String::from_utf8_lossy(name)
            .rsplit('\u{1f}')
            .next()
            .unwrap_or("")
            .to_owned();
        self.nodes.push(XmlNode {
            name,
            parent: self.stack.last().copied(),
            ..XmlNode::default()
        });
        if let Some(parent) = self.stack.last() {
            self.nodes[*parent].children.push(index);
        }
        self.stack.push(index);
    }
    fn end_element(&mut self, _: &[u8]) {
        self.stack.pop();
    }
    fn character_data(&mut self, text: &[u8]) {
        if let Some(index) = self.stack.last() {
            self.nodes[*index]
                .text
                .push_str(&String::from_utf8_lossy(text));
        }
    }
    fn comment(&mut self, text: &[u8]) {
        self.comments
            .push(String::from_utf8_lossy(text).into_owned());
    }
    fn processing_instruction(&mut self, target: &[u8], text: &[u8]) {
        let target = String::from_utf8_lossy(target);
        let text = String::from_utf8_lossy(text);
        self.instructions.push(if text.is_empty() {
            target.into_owned()
        } else {
            format!("{target} {text}")
        });
    }
}
impl XmlTree {
    fn child(&self, index: usize, name: &str) -> Option<usize> {
        self.nodes[index]
            .children
            .iter()
            .find(|child| self.nodes[**child].name == name)
            .copied()
    }
    fn ancestor(&self, index: usize, names: &[&str]) -> Option<usize> {
        let mut current = Some(index);
        while let Some(index) = current {
            if names.contains(&self.nodes[index].name.as_str()) {
                return Some(index);
            }
            current = self.nodes[index].parent;
        }
        None
    }
    fn unit_uuid(&self, index: usize) -> String {
        if let Some(uuid) = self.child(index, "uuid") {
            if !self.nodes[uuid].text.trim().is_empty() {
                return self.nodes[uuid].text.trim().into();
            }
        }
        let Some(unit) = self.ancestor(
            index,
            &[
                "mig_device",
                "mig_instance",
                "compute_instance",
                "gpu_instance",
                "gpu",
            ],
        ) else {
            return String::new();
        };
        if self.nodes[unit].name != "gpu" {
            if let Some(uuid) = self.child(unit, "uuid") {
                if !self.nodes[uuid].text.trim().is_empty() {
                    return self.nodes[uuid].text.trim().into();
                }
            }
        }
        let Some(physical) = self.ancestor(index, &["gpu"]) else {
            return String::new();
        };
        let Some(uuid) = self.child(physical, "uuid") else {
            return String::new();
        };
        let parent = self.nodes[uuid].text.trim();
        let mut identifiers = Vec::new();
        let mut current = Some(index);
        for _ in 0..3 {
            if let Some(index) = current {
                for tag in ["gpu_instance_id", "compute_instance_id"] {
                    if let Some(value) = self.child(index, tag) {
                        let value = self.nodes[value].text.trim();
                        if !value.is_empty() {
                            identifiers.push(value);
                        }
                    }
                }
                current = self.nodes[index].parent;
            }
        }
        if identifiers.is_empty() {
            parent.into()
        } else {
            format!("MIG-{parent}/{}", identifiers.join("/"))
        }
    }
    fn descendants(&self, index: usize) -> Vec<usize> {
        let mut result = Vec::new();
        let mut pending = vec![index];
        while let Some(index) = pending.pop() {
            result.push(index);
            pending.extend(self.nodes[index].children.iter().rev().copied());
        }
        result
    }
    fn child_text(&self, index: usize, name: &str) -> Result<String> {
        self.nodes[index]
            .children
            .iter()
            .find(|child| self.nodes[**child].name == name)
            .map(|child| self.nodes[*child].text.trim().to_owned())
            .filter(|text| !text.is_empty())
            .ok_or_else(|| {
                Failure::new(
                    "gpu_structured_probe_malformed",
                    format!("NVIDIA XML omitted required topology field: {name}"),
                )
            })
    }
}
pub fn parse_nvidia_smi_xml(evidence: &EvidenceFd) -> Result<ParsedNvidiaXml> {
    parse_nvidia_xml_document(evidence).map(|(_, parsed)| parsed)
}
fn parse_nvidia_xml_document(evidence: &EvidenceFd) -> Result<(XmlTree, ParsedNvidiaXml)> {
    use expat::internal::parse::{HandlerSet, Parser, Status};
    let bytes = evidence.read()?;
    let text = std::str::from_utf8(&bytes)
        .map_err(|error| Failure::new("gpu_structured_probe_malformed", error.to_string()))?;
    if bytes.starts_with(&[0xef, 0xbb, 0xbf]) || bytes.contains(&0) {
        return Err(Failure::new(
            "gpu_structured_probe_malformed",
            "NVIDIA XML must be UTF-8 without BOM or NUL",
        ));
    }
    if Regex::new(r"(?i)<!\s*ENTITY\b").unwrap().is_match(text) {
        return Err(Failure::new(
            "gpu_structured_probe_unsafe_xml",
            "NVIDIA XML must not contain entity declarations",
        ));
    }
    let mut salt = [0u8; 16];
    getrandom::getrandom(&mut salt)
        .map_err(|error| Failure::new("gpu_structured_probe_malformed", error.to_string()))?;
    let mut parser = Parser::new(None, Some(b'\x1f'), salt);
    parser.set_handlers(HandlerSet {
        start_element: true,
        end_element: true,
        character_data: true,
        external_entity_ref: true,
        comment: true,
        processing_instruction: true,
        ..HandlerSet::default()
    });
    let mut tree = XmlTree::default();
    if !matches!(parser.parse(&mut tree, &bytes, true), Status::Ok) || tree.nodes.is_empty() {
        return Err(Failure::new(
            "gpu_structured_probe_malformed",
            "NVIDIA XML could not be parsed",
        ));
    }
    let uuid = Regex::new(r"^(GPU|MIG)-[A-Za-z0-9-]+$").unwrap();
    let mut physical = Vec::new();
    let mut mig = Vec::new();
    let mut joins = Vec::new();
    let mut seen = BTreeSet::new();
    for (index, node) in tree
        .nodes
        .iter()
        .enumerate()
        .filter(|(_, node)| node.name == "gpu")
    {
        let _ = node;
        let parent = tree.child_text(index, "uuid")?;
        if !uuid.is_match(&parent) || !parent.starts_with("GPU-") {
            return Err(Failure::new(
                "gpu_structured_probe_malformed",
                "NVIDIA XML physical UUID is not full and opaque",
            ));
        }
        if physical.contains(&parent) {
            return Err(Failure::new(
                "gpu_uuid_duplicate",
                "NVIDIA XML repeats a physical UUID",
            ));
        }
        physical.push(parent.clone());
        for child in tree.descendants(index).into_iter().filter(|child| {
            *child != index
                && ["mig_device", "mig_instance"].contains(&tree.nodes[*child].name.as_str())
        }) {
            let identity = tree.child_text(child, "uuid")?;
            if !uuid.is_match(&identity) || !identity.starts_with("MIG-") {
                return Err(Failure::new(
                    "gpu_structured_probe_malformed",
                    "NVIDIA XML MIG UUID is not full and opaque",
                ));
            }
            let ordinal = tree.child_text(child, "device_ordinal")?;
            if !ordinal.chars().all(|character| {
                crate::python_cli_integer::decimal_digit_value(character).is_some()
            }) {
                return Err(Failure::new(
                    "gpu_mig_join_conflict",
                    "NVIDIA XML MIG ordinal is not decimal",
                ));
            }
            let integer = crate::python_cli_integer::parse(&ordinal)
                .ok_or_else(|| Failure::new("gpu_mig_join_conflict", "invalid MIG ordinal"))?;
            let ordinal: Value = serde_json::from_str(&integer.to_string())
                .map_err(|error| Failure::new("gpu_mig_join_conflict", error.to_string()))?;
            let declared = tree.nodes[child]
                .children
                .iter()
                .find(|node| {
                    tree.nodes[**node].name == "parent_uuid" && !tree.nodes[**node].text.is_empty()
                })
                .map(|node| tree.nodes[*node].text.trim())
                .unwrap_or(&parent);
            if declared != parent
                || mig.contains(&identity)
                || !seen.insert((parent.clone(), ordinal.to_string()))
            {
                return Err(Failure::new(
                    "gpu_mig_join_conflict",
                    "NVIDIA XML MIG topology join conflicts",
                ));
            }
            mig.push(identity.clone());
            joins.push(NvidiaTopologyJoin {
                parent_uuid: parent.clone(),
                ordinal,
                mig_uuid: identity,
            });
        }
    }
    if physical.is_empty() {
        return Err(Failure::new(
            "gpu_structured_probe_malformed",
            "NVIDIA XML contains no physical GPU topology",
        ));
    }
    let containers = tree
        .nodes
        .iter()
        .enumerate()
        .filter(|(_, node)| {
            ["processes", "compute_processes", "graphics_processes"].contains(&node.name.as_str())
        })
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    if containers.is_empty() {
        return Err(Failure::new(
            "gpu_process_inventory_unproven",
            "NVIDIA XML omitted process inventory containers",
        ));
    }
    for node in &tree.nodes {
        if node.name.contains("process")
            && ![
                "processes",
                "compute_processes",
                "graphics_processes",
                "accounted_processes",
                "process_info",
                "pid",
                "process_name",
                "used_memory",
                "type",
            ]
            .contains(&node.name.as_str())
        {
            return Err(Failure::new(
                "gpu_process_scope_unproven",
                "NVIDIA XML contains unsupported process scope",
            ));
        }
    }
    let records = containers
        .iter()
        .flat_map(|index| tree.descendants(*index))
        .collect::<Vec<_>>();
    let inventory_text = records
        .iter()
        .map(|index| tree.nodes[*index].text.trim().to_lowercase())
        .collect::<Vec<_>>()
        .join(" ");
    if [
        "permission denied",
        "insufficient permission",
        "not supported",
        "unknown error",
    ]
    .iter()
    .any(|marker| inventory_text.contains(marker))
    {
        return Err(Failure::new(
            "gpu_process_inventory_unproven",
            "NVIDIA XML process inventory is hidden or unsupported",
        ));
    }
    let disposition = if records
        .iter()
        .any(|index| tree.nodes[*index].name == "process_info")
    {
        "COMPLETE"
    } else {
        "COMPLETE_EMPTY"
    };
    let payload = serde_json::json!({"source_name":evidence.source_name,"st_dev":evidence.st_dev,"st_ino":evidence.st_ino,"byte_count":evidence.byte_count,"sha256":evidence.sha256,"payload":{"physical_uuids":physical,"mig_uuids":mig,"joins":joins,"processing_instructions":tree.instructions,"comments":tree.comments,"process_inventory_disposition":disposition}});
    let parsed = crate::python_json::parse_json(&payload.to_string())
        .map_err(|error| Failure::new("gpu_structured_probe_malformed", error))?;
    let canonical = crate::python_json::canonical_json_ascii_bytes_reject_nonfinite(&parsed)
        .map_err(|error| Failure::new("gpu_structured_probe_malformed", error))?;
    let parsed = ParsedNvidiaXml {
        schema_version: "nvidia-xml/v1".into(),
        physical_uuids: physical,
        mig_uuids: mig,
        joins,
        processing_instructions: tree.instructions.clone(),
        comments: tree.comments.clone(),
        process_inventory_disposition: disposition.into(),
        evidence_fingerprint: format!("{:x}", Sha256::digest(canonical)),
    };
    Ok((tree, parsed))
}

#[derive(Clone, Debug)]
pub struct NvidiaStructuredObservation {
    pub inventory: NvidiaInventory,
    pub devices: Vec<GpuDevice>,
    pub processes: Vec<ProcessIdentity>,
    pub process_inventory_visibility: Value,
    pub unknown_gpu_ids: BTreeSet<String>,
    pub xml_binding_unknown: bool,
    pub unit_states: BTreeMap<String, GpuUnitDisposition>,
}
fn xml_memory_bytes(tree: &XmlTree, index: usize) -> Result<u64> {
    let raw = tree.nodes[index].text.trim();
    let parts = raw.split_whitespace().collect::<Vec<_>>();
    if parts.len() != 2 {
        return Err(Failure::new(
            "gpu_structured_observation_malformed",
            "NVIDIA XML memory field requires a value/unit pair",
        ));
    }
    let multiplier = match parts[1] {
        "B" => 1f64,
        "KiB" => 1024f64,
        "MiB" => 1048576f64,
        "GiB" => 1073741824f64,
        _ => {
            return Err(Failure::new(
                "gpu_structured_observation_malformed",
                "NVIDIA XML memory unit is unsupported",
            ))
        }
    };
    let value = parts[0]
        .parse::<f64>()
        .map_err(|error| Failure::new("gpu_structured_observation_malformed", error.to_string()))?
        * multiplier;
    if !value.is_finite() || value < 0.0 || value >= u64::MAX as f64 {
        return Err(Failure::new(
            "gpu_structured_observation_malformed",
            "NVIDIA XML memory value is outside supported byte range",
        ));
    }
    Ok(value as u64)
}
fn observe_process_ancestry(pid: u32) -> Result<Vec<ProcessRoot>> {
    fn record(pid: u32) -> Result<(ProcessRoot, u32)> {
        let dir = PathBuf::from(format!("/proc/{pid}"));
        let read = || {
            std::fs::read_to_string(dir.join("stat"))
                .map_err(|error| Failure::new("gpu_process_identity_unproven", error.to_string()))
        };
        let before = read()?;
        let (_, tail) = before.rsplit_once(')').ok_or_else(|| {
            Failure::new(
                "gpu_process_identity_unproven",
                "proc stat format is invalid",
            )
        })?;
        let fields = tail.split_whitespace().collect::<Vec<_>>();
        if fields.len() <= 19 {
            return Err(Failure::new(
                "gpu_process_identity_unproven",
                "proc stat omits start identity",
            ));
        }
        let parent = fields[1]
            .parse::<u32>()
            .map_err(|error| Failure::new("gpu_process_identity_unproven", error.to_string()))?;
        let status = std::fs::read_to_string(dir.join("status"))
            .map_err(|error| Failure::new("gpu_process_identity_unproven", error.to_string()))?;
        let status_parent = status
            .lines()
            .find_map(|line| line.strip_prefix("PPid:"))
            .map(str::trim)
            .and_then(|value| value.parse::<u32>().ok());
        if status_parent != Some(parent) {
            return Err(Failure::new(
                "gpu_process_parent_mismatch",
                "proc status and stat parent disagree",
            ));
        }
        let namespace = std::fs::read_link(dir.join("ns/pid"))
            .map_err(|error| Failure::new("gpu_process_identity_unproven", error.to_string()))?;
        let cgroup = std::fs::read_to_string(dir.join("cgroup"))
            .map_err(|error| Failure::new("gpu_process_identity_unproven", error.to_string()))?;
        let records = cgroup
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty())
            .collect::<Vec<_>>();
        let unified = records
            .iter()
            .filter(|line| line.contains("::"))
            .copied()
            .collect::<Vec<_>>();
        let cgroup = if unified.is_empty() { records } else { unified }.join("|");
        let after = read()?;
        let (_, after_tail) = after.rsplit_once(')').ok_or_else(|| {
            Failure::new(
                "gpu_process_identity_unproven",
                "proc stat format is invalid",
            )
        })?;
        let after_fields = after_tail.split_whitespace().collect::<Vec<_>>();
        if after_fields.len() <= 19
            || fields[1] != after_fields[1]
            || fields[19] != after_fields[19]
        {
            return Err(Failure::new(
                "gpu_process_identity_raced",
                "proc process identity changed during observation",
            ));
        }
        if cgroup.is_empty() {
            return Err(Failure::new(
                "gpu_process_identity_unproven",
                "proc cgroup identity is empty",
            ));
        }
        Ok((
            ProcessRoot {
                pid,
                starttime: fields[19].into(),
                pid_namespace: namespace.to_string_lossy().into_owned(),
                cgroup,
            },
            parent,
        ))
    }
    let mut chain = Vec::<ProcessRoot>::new();
    let mut current = pid;
    let mut seen = BTreeSet::new();
    for _ in 0..64 {
        if !seen.insert(current) {
            return Err(Failure::new(
                "gpu_process_ancestry_cycle",
                "process ancestry contains a PID cycle",
            ));
        }
        let (root, parent) = record(current)?;
        if let Some(holder) = chain.first() {
            if root.pid_namespace != holder.pid_namespace {
                return Err(Failure::new(
                    "gpu_process_namespace_mismatch",
                    "process ancestry crosses PID namespaces",
                ));
            }
            if root.cgroup != holder.cgroup {
                return Err(Failure::new(
                    "gpu_process_cgroup_mismatch",
                    "process ancestry crosses cgroups",
                ));
            }
        }
        chain.push(root);
        if parent <= 1 {
            return Ok(chain);
        }
        current = parent;
    }
    Err(Failure::new(
        "gpu_process_ancestry_depth_exceeded",
        "process ancestry exceeded bounded depth",
    ))
}
pub fn observe_structured_nvidia(
    list: &EvidenceFd,
    xml: &EvidenceFd,
    driver: Option<&EvidenceFd>,
    allocated: &BTreeSet<String>,
) -> Result<NvidiaStructuredObservation> {
    let list_parsed = parse_nvidia_smi_list(list)?;
    let (tree, xml_parsed) = parse_nvidia_xml_document(xml)?;
    if list_parsed.physical_uuids != xml_parsed.physical_uuids
        || list_parsed.mig_uuids != xml_parsed.mig_uuids
        || list_parsed.joins != xml_parsed.joins
    {
        return Err(Failure::new(
            "gpu_mig_join_conflict",
            "NVIDIA list and XML topology evidence disagree",
        ));
    }
    let driver = driver.map(parse_nvidia_driver_version).transpose()?;
    let inventory = NvidiaInventory {
        schema_version: "nvidia-inventory/v1".into(),
        physical_uuids: list_parsed.physical_uuids,
        mig_uuids: list_parsed.mig_uuids,
        joins: list_parsed.joins,
        driver_version: driver.clone(),
        evidence_fingerprint: canonical_fingerprint(
            &serde_json::json!({"list":list_parsed.evidence_fingerprint,"xml":xml_parsed.evidence_fingerprint,"driver":driver}),
        )?,
    };
    let mut devices = BTreeMap::new();
    let mut unit_by_uuid = BTreeMap::new();
    for (index, node) in tree.nodes.iter().enumerate() {
        if !["gpu", "mig_device", "gpu_instance", "compute_instance"].contains(&node.name.as_str())
        {
            continue;
        }
        let uuid = tree.unit_uuid(index);
        if uuid.is_empty() {
            continue;
        }
        unit_by_uuid.insert(uuid.clone(), index);
        let Some(memory) = tree.child(index, "fb_memory_usage") else {
            continue;
        };
        if devices.contains_key(&uuid) {
            continue;
        }
        let free = tree.child(memory, "free").ok_or_else(|| {
            Failure::new(
                "gpu_structured_observation_incomplete",
                "NVIDIA XML omitted free memory",
            )
        })?;
        let total = tree.child(memory, "total").ok_or_else(|| {
            Failure::new(
                "gpu_structured_observation_incomplete",
                "NVIDIA XML omitted total memory",
            )
        })?;
        let parent = if node.name == "gpu" {
            None
        } else {
            tree.ancestor(index, &["gpu"])
                .map(|parent| tree.unit_uuid(parent))
        };
        devices.insert(
            uuid.clone(),
            GpuDevice {
                uuid,
                free_memory_bytes: xml_memory_bytes(&tree, free)?,
                memory_bytes: xml_memory_bytes(&tree, total)?,
                mig_parent_uuid: parent,
            },
        );
    }
    if devices.is_empty()
        || allocated
            .iter()
            .chain(&inventory.physical_uuids)
            .chain(&inventory.mig_uuids)
            .any(|uuid| !devices.contains_key(uuid))
    {
        return Err(Failure::new(
            "gpu_structured_discovery_cardinality_incomplete",
            "NVIDIA topology and memory evidence do not cover allocated units",
        ));
    }
    let inventory_tags = ["processes", "compute_processes", "graphics_processes"];
    let mut witnesses = BTreeMap::new();
    for uuid in allocated {
        let index = *unit_by_uuid.get(uuid).ok_or_else(|| {
            Failure::new(
                "gpu_process_identity_unproven",
                "allocated GPU has no structured process inventory scope",
            )
        })?;
        let mut containers = tree
            .descendants(index)
            .into_iter()
            .filter(|index| inventory_tags.contains(&tree.nodes[*index].name.as_str()))
            .collect::<Vec<_>>();
        let mut coverage = "allocated_unit_process_table";
        if containers.is_empty() {
            if let Some(parent) = tree.ancestor(index, &["gpu"]) {
                containers = tree
                    .descendants(parent)
                    .into_iter()
                    .filter(|index| inventory_tags.contains(&tree.nodes[*index].name.as_str()))
                    .collect();
                coverage = "physical_parent_process_table";
            }
        }
        if containers.is_empty() {
            return Err(Failure::new(
                "gpu_process_identity_unproven",
                "structured XML omitted process inventory for allocated unit",
            ));
        }
        let count = containers
            .iter()
            .flat_map(|index| tree.descendants(*index))
            .filter(|index| tree.nodes[*index].name == "process_info")
            .count();
        let tags = containers
            .iter()
            .map(|index| tree.nodes[*index].name.clone())
            .collect::<BTreeSet<_>>();
        witnesses.insert(uuid.clone(),serde_json::json!({"visible":true,"coverage_source":coverage,"container_tags":tags,"process_count":count,"explicit_empty":count==0}));
    }
    let process_inventory_visibility = serde_json::json!({"schema_version":"gpu-process-inventory-visibility/v1","allocated_ids":allocated,"all_allocated_units_visible":true,"units":witnesses});
    let mut processes = Vec::new();
    let mut unknown = BTreeSet::new();
    let mut binding_unknown = false;
    for (index, node) in tree
        .nodes
        .iter()
        .enumerate()
        .filter(|(_, node)| node.name == "process_info")
    {
        let _ = node;
        if tree.ancestor(index, &inventory_tags).is_none() {
            continue;
        }
        let pid = tree
            .child_text(index, "pid")?
            .parse::<u32>()
            .map_err(|error| Failure::new("gpu_process_identity_unproven", error.to_string()))?;
        if pid == 0 {
            return Err(Failure::new(
                "gpu_process_identity_unproven",
                "NVIDIA XML process PID must be positive",
            ));
        }
        let mut uuid = tree.unit_uuid(index);
        let mut ancestor = Some(index);
        let mut graphics = false;
        while let Some(current) = ancestor {
            if tree.nodes[current].name == "graphics_processes" {
                graphics = true;
            }
            if devices.contains_key(&uuid) {
                break;
            }
            if ["compute_instance", "gpu_instance", "mig_device", "gpu"]
                .contains(&tree.nodes[current].name.as_str())
            {
                uuid = tree.unit_uuid(current);
                if devices.contains_key(&uuid) {
                    break;
                }
            }
            ancestor = tree.nodes[current].parent;
        }
        if !devices.contains_key(&uuid) {
            binding_unknown = true;
            continue;
        }
        let chain = match observe_process_ancestry(pid) {
            Ok(chain) => chain,
            Err(_) => {
                unknown.insert(uuid);
                continue;
            }
        };
        let raw = tree
            .child(index, "type")
            .map(|index| tree.nodes[index].text.trim().to_uppercase())
            .unwrap_or_default();
        let tokens = raw
            .split('+')
            .map(str::trim)
            .filter(|token| !token.is_empty())
            .collect::<BTreeSet<_>>();
        let kind = if graphics {
            "graphics"
        } else if tokens.is_empty()
            || tokens
                .iter()
                .any(|token| !["C", "G", "M", "O"].contains(token))
        {
            "other_gpu_context"
        } else if tokens.contains("C") && tokens.contains("G") {
            "compute_graphics"
        } else if tokens.contains("G") {
            "graphics"
        } else if tokens.contains("M") {
            "mps_compute"
        } else if tokens.contains("O") {
            "other_gpu_context"
        } else {
            "compute"
        };
        let holder = &chain[0];
        let parent = chain.get(1).map(|root| root.pid);
        let relationship = if pid == std::process::id() {
            "planner_process"
        } else if parent == Some(std::process::id()) {
            "child"
        } else {
            "external"
        };
        processes.push(ProcessIdentity {
            pid,
            process_start_identity: holder.starttime.clone(),
            gpu_uuid: uuid,
            kind: kind.into(),
            parent_pid: parent,
            relationship: relationship.into(),
            observation_timestamp: String::new(),
            observation_fingerprint: String::new(),
            container_namespace_identity: holder.pid_namespace.clone(),
            pid_namespace: holder.pid_namespace.clone(),
            cgroup: holder.cgroup.clone(),
            process_root: chain.last().cloned(),
            ancestry: chain,
        });
    }
    processes.sort_by(|left, right| {
        (
            &left.gpu_uuid,
            &left.kind,
            left.pid,
            &left.process_start_identity,
        )
            .cmp(&(
                &right.gpu_uuid,
                &right.kind,
                right.pid,
                &right.process_start_identity,
            ))
    });
    let devices = devices.into_values().collect::<Vec<_>>();
    let known = devices
        .iter()
        .map(|device| device.uuid.clone())
        .collect::<BTreeSet<_>>();
    let states = classify_gpu_unit_states(&devices, &processes, &known, &unknown, binding_unknown);
    let unknown = states
        .iter()
        .filter(|(_, state)| **state == GpuUnitDisposition::Unknown)
        .map(|(uuid, _)| uuid.clone())
        .collect();
    let unit_states =
        classify_gpu_unit_states(&devices, &processes, allocated, &unknown, binding_unknown);
    Ok(NvidiaStructuredObservation {
        inventory,
        devices,
        processes,
        process_inventory_visibility,
        unknown_gpu_ids: unknown,
        xml_binding_unknown: binding_unknown,
        unit_states,
    })
}

#[cfg(target_os = "linux")]
pub fn discover_resources(
    environment: &BTreeMap<String, String>,
    gpu_requested_count: usize,
) -> Result<ResourceObservation> {
    let observed_at = time::OffsetDateTime::now_utc()
        .format(&time::format_description::well_known::Rfc3339)
        .map_err(|error| {
            Failure::new("host_capability_discovery_unavailable", error.to_string())
        })?;
    let status = std::fs::read_to_string("/proc/self/status")
        .map_err(|error| Failure::new("cpu_capability_discovery_unavailable", error.to_string()))?;
    let allowed = status
        .lines()
        .find_map(|line| line.strip_prefix("Cpus_allowed_list:"))
        .ok_or_else(|| {
            Failure::new(
                "cpu_capability_discovery_unavailable",
                "CPU affinity is unavailable",
            )
        })?;
    let mut cpu = Vec::new();
    for token in allowed.trim().split(',') {
        let (start, end) = token.split_once('-').unwrap_or((token, token));
        let start = start.parse::<u32>().map_err(|error| {
            Failure::new("cpu_capability_discovery_unavailable", error.to_string())
        })?;
        let end = end.parse::<u32>().map_err(|error| {
            Failure::new("cpu_capability_discovery_unavailable", error.to_string())
        })?;
        cpu.extend(start..=end);
    }
    let boot = std::fs::read_to_string("/proc/sys/kernel/random/boot_id")
        .map_err(|error| Failure::new("boot_identity_unavailable", error.to_string()))?
        .trim()
        .to_owned();
    if boot.is_empty() {
        return Err(Failure::new(
            "boot_identity_unavailable",
            "boot identity is empty",
        ));
    }
    let command = |name: &str| crate::tool_dispatch::find_executable(name);
    let tree = command("tree");
    let nvidia = command("nvidia-smi");
    let mut tools = serde_json::json!({"tree":{"available":tree.is_some(),"path":tree.as_ref().map(|path|path.to_string_lossy().into_owned()).unwrap_or_default()}});
    let mut allocated = BTreeSet::new();
    let mut devices = Vec::new();
    let mut processes = Vec::new();
    let mut inventory = None;
    let mut unknown = BTreeSet::new();
    let mut binding_unknown = false;
    let mut states = BTreeMap::new();
    if gpu_requested_count > 0 {
        allocated = scheduler_uuid_set(environment)?;
        let nvidia = nvidia
            .as_ref()
            .ok_or_else(|| {
                Failure::new(
                    "gpu_structured_probe_unavailable",
                    "GPU request requires structured nvidia-smi XML probe",
                )
            })?
            .to_string_lossy()
            .into_owned();
        let list = EvidenceFd::capture(&[nvidia.clone(), "-L".into()], "nvidia_smi_list")?;
        let xml = EvidenceFd::capture(
            &[nvidia.clone(), "-q".into(), "-x".into()],
            "nvidia_smi_xml",
        )?;
        let driver = EvidenceFd::capture(
            &[
                nvidia.clone(),
                "--id=0".into(),
                "--query-gpu=driver_version".into(),
                "--format=csv,noheader,nounits".into(),
            ],
            "nvidia_driver_version",
        )?;
        let structured = observe_structured_nvidia(&list, &xml, Some(&driver), &allocated)?;
        devices = structured.devices;
        processes = structured.processes;
        inventory = Some(structured.inventory);
        unknown = structured.unknown_gpu_ids;
        binding_unknown = structured.xml_binding_unknown;
        states = structured.unit_states;
        tools["nvidia-smi"] = serde_json::json!({"available":true,"path":nvidia,"query":"-q -x","structured":true,"process_type_taxonomy":["C","G","M","O","C+G","M+C"],"pid_identity":"authoritative_proc_pid_stat_and_pid_namespace","uuid_identity":"full_gpu_or_mig_uuid","narrower_sources_rejected":["pmon"],"query_compute_apps":"auxiliary_unique_xml_pid_join_only","process_inventory_visibility":structured.process_inventory_visibility});
    } else {
        tools["nvidia-smi"] = serde_json::json!({"available":nvidia.is_some(),"path":nvidia.map(|path|path.to_string_lossy().into_owned()).unwrap_or_default(),"structured":true,"required":false});
    }
    let memory = std::fs::read_to_string("/proc/meminfo").map_err(|error| {
        Failure::new("host_capability_discovery_unavailable", error.to_string())
    })?;
    let mut host_memory = 0u64;
    for line in memory.lines().filter(|line| line.starts_with("MemTotal:")) {
        let value = line
            .split_whitespace()
            .nth(1)
            .and_then(|value| value.parse::<u64>().ok())
            .ok_or_else(|| {
                Failure::new(
                    "host_capability_discovery_unavailable",
                    "host memory is unavailable",
                )
            })?;
        host_memory = host_memory
            .checked_add(value.checked_mul(1024).ok_or_else(|| {
                Failure::new(
                    "host_capability_discovery_unavailable",
                    "host memory exceeds byte range",
                )
            })?)
            .ok_or_else(|| {
                Failure::new(
                    "host_capability_discovery_unavailable",
                    "host memory exceeds byte range",
                )
            })?;
    }
    let filesystem = rustix::fs::statvfs("/").map_err(|error| {
        Failure::new("host_capability_discovery_unavailable", error.to_string())
    })?;
    let temp_bytes = filesystem
        .f_bavail
        .checked_mul(filesystem.f_frsize)
        .ok_or_else(|| {
            Failure::new(
                "host_capability_discovery_unavailable",
                "temporary capacity exceeds byte range",
            )
        })?;
    let container_id = std::fs::read_to_string("/etc/hostname")
        .map_err(|error| Failure::new("container_identity_unavailable", error.to_string()))?
        .trim()
        .to_owned();
    let mut random = [0u8; 12];
    getrandom::getrandom(&mut random).map_err(|error| {
        Failure::new("host_capability_discovery_unavailable", error.to_string())
    })?;
    let event = format!(
        "nvidia-smi-{}",
        random
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>()
    );
    let fingerprint = canonical_fingerprint(
        &serde_json::json!({"allocated":allocated,"devices":devices,"processes":processes,"unknown_gpu_ids":unknown,"xml_binding_unknown":binding_unknown,"unit_states":states,"boot_id":boot,"visible":allocated}),
    )?;
    for process in &mut processes {
        process.observation_timestamp = observed_at.clone();
        process.observation_fingerprint = fingerprint.clone();
    }
    let free_memory_bytes = devices
        .iter()
        .map(|device| (device.uuid.clone(), device.free_memory_bytes))
        .collect();
    let structure_tool = BTreeMap::from([
        (
            "available".into(),
            if tree.is_some() { "true" } else { "false" }.into(),
        ),
        ("command".into(), "tree".into()),
        (
            "structure_contract_ref".into(),
            "documents/structure/repo-structure-contract.toml".into(),
        ),
    ]);
    Ok(ResourceObservation {
        caller_allocated_ids: allocated.clone(),
        process_identities: processes,
        gpu_devices: devices,
        free_memory_bytes,
        boot_id: boot,
        container_visible_ids: allocated,
        observed_at,
        fingerprint,
        observation_event_id: event,
        cpu_available_set: cpu,
        host_memory_bytes: host_memory,
        temp_bytes,
        container_id,
        unknown_gpu_ids: unknown,
        structure_tool,
        tool_availability: tools,
        nvidia_inventory: inventory,
        unit_states: states,
    })
}
