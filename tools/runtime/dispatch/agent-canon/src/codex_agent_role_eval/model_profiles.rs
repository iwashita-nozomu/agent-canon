// @dependency-start
// contract implementation
// responsibility Loads the canonical role/profile registry and generates/checks executable and consumer-static role views.
// upstream design ../../../../../../agents/model_profiles.toml canonical model/profile registry and static instruction projections
// upstream design ../../../../../../agents/agents_config.json logical role mappings and consumer projection destination
// upstream design ../../../../../../.codex/config.toml registered role descriptions and context settings
// downstream implementation ./mod.rs evaluate-codex-agent-roles generation and readback CLI
// downstream test ../../../../../../tests/agent_tools/test_model_profile_registry.py native generation and drift oracle
// @dependency-end

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use serde_json::{json, Value as JsonValue};
use sha2::{Digest, Sha256};
use toml_edit::{DocumentMut, Item, TableLike};

const REGISTRY_SCHEMA_ID: &str = "model_profile_registry_v1";
const STATIC_FORBIDDEN_PREFIXES: &[&str] = &[
    "agents/skills/",
    "agents/model_profiles.toml",
    "tools/agent_tools/",
    "../../agents/",
    "../../tools/",
];

const CHECKOUT_IDENTITY_PROMPT: &str = "Carry one checkout_identity block with cwd, git_root, branch (or detached), head, and normalized remote owner/repository at bounded workflow transitions; do not repeat it for ordinary commands.";
const WRITER_TARGET_PROMPT: &str = "Write-capable handoffs must carry writer_target with an absolute checkout_root, fixed branch, normalized remote owner/repository, and allowed_paths. The checkout is prepared by repository-topic-clone before handoff; start with cwd equal to checkout_root and branch equal to the target branch. Do not use git switch, git checkout, branch rename, or git worktree operations; a target mismatch is a hard stop before mutation.";
const CANONICAL_SPAWN_PROMPT: &str = "Spawn only through the canonical AgentTeam dispatch and ToolCall route; raw spawn_agent is not an admission path.";

const WRITER_TARGET_ROLE_IDS: &[&str] = &[
    "worker",
    "spark_worker",
    "implementer",
    "integration_executor",
];
const CANONICAL_SPAWN_ROLE_IDS: &[&str] = &["sol_parent", "manager", "manager_reviewer"];

const STATIC_OBLIGATIONS: &[(&str, &str)] = &[
    (
        "validation_owner",
        "follow the selected closed validation route",
    ),
    (
        "parent_assignment",
        "act only on the assigned child packet and scope",
    ),
    (
        "parent_authority",
        "respect child-owned integration publication and final-review decisions",
    ),
    (
        "stop_handback",
        "return branch/head/check evidence or the role result and stop",
    ),
];

#[derive(Clone, Debug)]
pub(super) struct GeneratedRoleView {
    pub role_id: String,
    pub profile_id: String,
    pub name: String,
    pub description: String,
    pub nickname_candidates: Vec<String>,
    pub sandbox_mode: String,
    pub approval_policy: String,
    pub rendered_instructions: String,
    pub model: String,
    pub reasoning_effort: String,
    pub model_context_window: Option<i64>,
    pub model_auto_compact_token_limit: Option<i64>,
    pub capabilities: Vec<String>,
    pub allowed_context: Vec<String>,
    pub forbidden_context: Vec<String>,
    pub return_schema_id: String,
    pub checkpoint_policy: String,
    pub continuation_policy: String,
    pub source_canonical_digest: String,
    pub logical_role_id: String,
    pub role_contract_ref: String,
    pub capsule_schema_id: String,
}

#[derive(Clone, Debug)]
struct InstructionClause {
    id: String,
    text: String,
    priority: i64,
    consumer_static_text: Option<String>,
    static_obligations: Vec<String>,
}

#[derive(Clone, Debug)]
pub(super) struct ModelProfile {
    pub(super) id: String,
    model_alias: String,
    pub(super) model: String,
    pub(super) reasoning_effort: String,
    capabilities: Vec<String>,
    allowed_context: Vec<String>,
    forbidden_context: Vec<String>,
    return_schema_id: String,
    checkpoint_policy: String,
    continuation_policy: String,
    capsule_schema_id: String,
    role_template: String,
    role_instructions: Vec<InstructionClause>,
}

#[derive(Clone, Debug)]
struct StandaloneRoleMetadata {
    logical_role_id: String,
    role_contract_ref: String,
    sandbox_mode: String,
}

#[derive(Clone, Debug)]
struct TeamRoleMetadata {
    logical_role_id: String,
    role_contract_ref: String,
    sandbox_mode: String,
}

#[derive(Clone, Debug)]
pub(super) struct ModelProfileRegistry {
    profile_bindings: BTreeMap<String, String>,
    sandbox_bindings: BTreeMap<String, String>,
    role_instruction_templates: BTreeMap<String, Vec<InstructionClause>>,
    standalone_role_metadata: BTreeMap<String, StandaloneRoleMetadata>,
    profiles: BTreeMap<String, ModelProfile>,
}

impl ModelProfileRegistry {
    pub(super) fn load(root: &Path) -> Result<Self, String> {
        let path = root.join("agents/model_profiles.toml");
        let document = read_toml_document(&path)?;
        validate_exact_fields(
            document.as_table(),
            &[
                "schema_id",
                "registry_id",
                "registry_version",
                "writer_isolation_policy",
                "role_profile_bindings",
                "role_sandbox_bindings",
                "role_instruction_templates",
                "standalone_role_metadata",
                "model_profiles",
            ],
            "registry",
        )?;
        let schema_id = table_string(document.as_table(), "schema_id", "registry.schema_id")?;
        if schema_id != REGISTRY_SCHEMA_ID {
            return Err("schema_id:mismatch".to_owned());
        }
        let _registry_id =
            table_string(document.as_table(), "registry_id", "registry.registry_id")?;
        let writer_policy =
            required_item(document.as_table(), "writer_isolation_policy", "registry")?
                .as_table_like()
                .ok_or_else(|| "writer_isolation_policy:must_be_mapping".to_owned())?;
        validate_exact_fields(
            writer_policy,
            &[
                "current_checkout_mode",
                "parallel_requirements",
                "collision_action",
                "isolated_worktree_mode",
            ],
            "writer_isolation_policy",
        )?;
        for field in [
            "current_checkout_mode",
            "collision_action",
            "isolated_worktree_mode",
        ] {
            let _ = table_string(
                writer_policy,
                field,
                &format!("writer_isolation_policy.{field}"),
            )?;
        }
        let _ = table_string_array(
            writer_policy,
            "parallel_requirements",
            "writer_isolation_policy.parallel_requirements",
        )?;
        let version = document
            .get("registry_version")
            .and_then(Item::as_integer)
            .filter(|value| *value > 0)
            .ok_or_else(|| "registry_version:must_be_positive_int".to_owned())?;
        let _ = version;

        let profile_bindings = string_table(
            required_item(document.as_table(), "role_profile_bindings", "registry")?,
            "role_profile_bindings",
        )?;
        if profile_bindings.is_empty() {
            return Err("role_profile_bindings:must_be_nonempty_mapping".to_owned());
        }
        let sandbox_bindings = string_table(
            required_item(document.as_table(), "role_sandbox_bindings", "registry")?,
            "role_sandbox_bindings",
        )?;
        if profile_bindings.keys().collect::<BTreeSet<_>>()
            != sandbox_bindings.keys().collect::<BTreeSet<_>>()
        {
            return Err("role_sandbox_bindings:must_exactly_match_role_bindings".to_owned());
        }
        for (role_id, sandbox) in &sandbox_bindings {
            if !matches!(sandbox.as_str(), "read-only" | "workspace-write") {
                return Err(format!("role_sandbox_bindings.{role_id}:invalid"));
            }
        }

        let role_instruction_templates = parse_role_instruction_templates(required_item(
            document.as_table(),
            "role_instruction_templates",
            "registry",
        )?)?;
        let unknown_templates = role_instruction_templates
            .keys()
            .filter(|role_id| !profile_bindings.contains_key(*role_id))
            .cloned()
            .collect::<Vec<_>>();
        if !unknown_templates.is_empty() {
            return Err(format!(
                "role_instruction_templates:unknown_roles:{}",
                unknown_templates.join(",")
            ));
        }

        let standalone_role_metadata = parse_standalone_metadata(required_item(
            document.as_table(),
            "standalone_role_metadata",
            "registry",
        )?)?;
        let profiles = parse_model_profiles(required_item(
            document.as_table(),
            "model_profiles",
            "registry",
        )?)?;
        let unknown_profiles = profile_bindings
            .values()
            .filter(|profile_id| !profiles.contains_key(*profile_id))
            .cloned()
            .collect::<BTreeSet<_>>();
        if !unknown_profiles.is_empty() {
            return Err(format!(
                "role_profile_bindings:unknown_profiles:{}",
                unknown_profiles.into_iter().collect::<Vec<_>>().join(",")
            ));
        }

        Ok(Self {
            profile_bindings,
            sandbox_bindings,
            role_instruction_templates,
            standalone_role_metadata,
            profiles,
        })
    }

    pub(super) fn by_profile(&self, profile_id: &str) -> Result<&ModelProfile, String> {
        self.profiles
            .get(profile_id)
            .ok_or_else(|| format!("model_profile:{profile_id}:not_found"))
    }

    pub(super) fn profile_for_role(&self, role_id: &str) -> Result<&ModelProfile, String> {
        let profile_id = self
            .profile_bindings
            .get(role_id)
            .ok_or_else(|| format!("role_profile:{role_id}:not_found"))?;
        self.by_profile(profile_id)
    }

    pub(super) fn generate_consumer_static_role_views(
        &self,
        root: &Path,
    ) -> Result<BTreeMap<String, GeneratedRoleView>, String> {
        let mut team_roles = team_role_metadata(root)?;
        if team_roles
            .keys()
            .any(|role_id| self.standalone_role_metadata.contains_key(role_id))
        {
            return Err("role_projection:standalone_metadata_overlaps_team_binding".to_owned());
        }
        for (role_id, metadata) in &self.standalone_role_metadata {
            team_roles.insert(
                role_id.clone(),
                TeamRoleMetadata {
                    logical_role_id: metadata.logical_role_id.clone(),
                    role_contract_ref: metadata.role_contract_ref.clone(),
                    sandbox_mode: metadata.sandbox_mode.clone(),
                },
            );
        }
        if team_roles.keys().collect::<BTreeSet<_>>()
            != self.sandbox_bindings.keys().collect::<BTreeSet<_>>()
        {
            return Err("role_projection:sandbox_binding_set_mismatch".to_owned());
        }

        let descriptions = registered_role_descriptions(root)?;
        let context_settings = context_settings(root)?;
        let expected_roles = team_roles
            .keys()
            .chain(descriptions.keys())
            .cloned()
            .collect::<BTreeSet<_>>();
        if team_roles.keys().collect::<BTreeSet<_>>()
            != descriptions.keys().collect::<BTreeSet<_>>()
            || self
                .profile_bindings
                .keys()
                .cloned()
                .collect::<BTreeSet<_>>()
                != expected_roles
        {
            return Err("role_projection:binding_registration_set_mismatch".to_owned());
        }
        let mut result = BTreeMap::new();
        for role_id in expected_roles {
            let profile = self.profile_for_role(&role_id)?;
            let mut clauses = profile.role_instructions.clone();
            clauses.extend(
                self.role_instruction_templates
                    .get(&role_id)
                    .cloned()
                    .unwrap_or_default(),
            );
            let mut seen = BTreeSet::new();
            for clause in &clauses {
                if !seen.insert(clause.id.clone()) {
                    return Err(format!("role_instruction:{role_id}:duplicate"));
                }
            }
            clauses
                .sort_by(|left, right| (left.priority, &left.id).cmp(&(right.priority, &right.id)));
            let mut base_prompt = clauses
                .iter()
                .map(consumer_static_clause)
                .collect::<Result<Vec<_>, _>>()?
                .join(" ");
            if !base_prompt.is_empty() {
                base_prompt.push(' ');
            }
            base_prompt.push_str(&role_boundary_prompt(&role_id));
            let rendered_instructions = format_role_template(
                &profile.role_template,
                &role_id,
                &profile.model_alias,
                &base_prompt,
            )?;
            let metadata = &team_roles[&role_id];
            let source_canonical_digest =
                role_projection_digest(&role_id, profile.id.as_str(), &clauses)?;
            let view = GeneratedRoleView {
                role_id: role_id.clone(),
                profile_id: profile.id.clone(),
                name: role_id.clone(),
                description: descriptions[&role_id].clone(),
                nickname_candidates: vec![role_id.clone()],
                sandbox_mode: self.sandbox_bindings[&role_id].clone(),
                approval_policy: "never".to_owned(),
                rendered_instructions,
                model: profile.model.clone(),
                reasoning_effort: profile.reasoning_effort.clone(),
                model_context_window: context_settings.0,
                model_auto_compact_token_limit: context_settings.1,
                capabilities: profile.capabilities.clone(),
                allowed_context: profile.allowed_context.clone(),
                forbidden_context: profile.forbidden_context.clone(),
                return_schema_id: profile.return_schema_id.clone(),
                checkpoint_policy: profile.checkpoint_policy.clone(),
                continuation_policy: profile.continuation_policy.clone(),
                source_canonical_digest,
                logical_role_id: metadata.logical_role_id.clone(),
                role_contract_ref: metadata.role_contract_ref.clone(),
                capsule_schema_id: profile.capsule_schema_id.clone(),
            };
            result.insert(role_id, view);
        }
        if result.is_empty() {
            return Err("generated_role_views:empty".to_owned());
        }
        Ok(result)
    }

    pub(super) fn generate_role_views(
        &self,
        root: &Path,
        projection: &str,
    ) -> Result<BTreeMap<String, GeneratedRoleView>, String> {
        if !matches!(projection, "live" | "consumer-static") {
            return Err(format!(
                "role_projection:unsupported_projection:{projection}"
            ));
        }
        let mut views = self.generate_consumer_static_role_views(root)?;
        if projection == "live" {
            for (role_id, view) in &mut views {
                if role_id == "skill_evaluator" {
                    continue;
                }
                let profile = self.profile_for_role(role_id)?;
                let mut clauses = profile.role_instructions.clone();
                clauses.extend(
                    self.role_instruction_templates
                        .get(role_id)
                        .cloned()
                        .unwrap_or_default(),
                );
                clauses.sort_by(|left, right| {
                    (left.priority, &left.id).cmp(&(right.priority, &right.id))
                });
                let base_prompt = clauses
                    .iter()
                    .map(|clause| clause.text.as_str())
                    .collect::<Vec<_>>()
                    .join(" ");
                let mut base_prompt = base_prompt;
                if !base_prompt.is_empty() {
                    base_prompt.push(' ');
                }
                base_prompt.push_str(&role_boundary_prompt(role_id));
                view.rendered_instructions = format_role_template(
                    &profile.role_template,
                    role_id,
                    &profile.model_alias,
                    &base_prompt,
                )?;
            }
        }
        Ok(views)
    }
}

pub(super) fn run_role_view_operation(root: &Path, projection: &str, generate: bool) -> i32 {
    let registry = match ModelProfileRegistry::load(root) {
        Ok(registry) => registry,
        Err(error) => {
            println!("MODEL_PROFILE_ROLE_VIEW_ISSUE={error}");
            return 1;
        }
    };
    let result = if generate {
        write_role_views(&registry, root, projection)
    } else {
        check_role_views(&registry, root, projection)
    };
    match result {
        Ok(count) if generate => {
            println!("MODEL_PROFILE_ROLE_VIEWS=generated:{count}");
            0
        }
        Ok(_) => {
            println!("MODEL_PROFILE_ROLE_VIEWS=pass");
            0
        }
        Err(error) => {
            println!("MODEL_PROFILE_ROLE_VIEW_ISSUE={error}");
            1
        }
    }
}

fn write_role_views(
    registry: &ModelProfileRegistry,
    root: &Path,
    projection: &str,
) -> Result<usize, String> {
    let views = registry.generate_role_views(root, projection)?;
    let static_views = registry.generate_role_views(root, "consumer-static")?;
    for view in views.values() {
        let path = root
            .join(".codex/agents")
            .join(format!("{}.toml", view.role_id));
        let rendered = render_role_view(
            view,
            view.role_id == "skill_evaluator" || projection == "consumer-static",
        );
        if fs::read(&path).ok().as_deref() != Some(rendered.as_bytes()) {
            fs::write(&path, rendered.as_bytes())
                .map_err(|error| format!("role_view_write:{}:{error}", path.display()))?;
        }
    }
    let (agent_views, roles) = projection_records(&static_views);
    let projection_digest = digest_json(&JsonValue::Object(
        static_views
            .iter()
            .map(|(role_id, view)| {
                (
                    role_id.clone(),
                    JsonValue::String(view.source_canonical_digest.clone()),
                )
            })
            .collect(),
    ))?;
    let projection_metadata = json!({
        "schema_id": "generated_role_profile_projection_v1",
        "materializer": "tools/bin/agent-canon evaluate-codex-agent-roles --generate-role-views",
        "registry_ref": "agents/model_profiles.toml",
        "role_count": static_views.len(),
        "projection_digest": projection_digest,
    });
    let config_path = root.join("agents/agents_config.json");
    let mut config: JsonValue = serde_json::from_slice(
        &fs::read(&config_path).map_err(|error| format!("agents_config:unreadable:{error}"))?,
    )
    .map_err(|error| format!("agents_config:unreadable:{error}"))?;
    let object = config
        .as_object_mut()
        .ok_or_else(|| "agents_config:must_be_mapping".to_owned())?;
    let current_profile = object.get("generated_profile_projection");
    let current_views = object.get("agent_views");
    let current_roles = object.get("roles");
    if current_profile != Some(&projection_metadata)
        || current_views != Some(&agent_views)
        || current_roles != Some(&roles)
    {
        object.insert(
            "generated_profile_projection".to_owned(),
            projection_metadata,
        );
        object.insert("agent_views".to_owned(), agent_views);
        object.insert("roles".to_owned(), roles);
        let mut encoded = serde_json::to_vec_pretty(&config).map_err(|error| error.to_string())?;
        encoded.push(b'\n');
        fs::write(&config_path, encoded)
            .map_err(|error| format!("agents_config_write:{}:{error}", config_path.display()))?;
    }
    Ok(views.len())
}

fn check_role_views(
    registry: &ModelProfileRegistry,
    root: &Path,
    projection: &str,
) -> Result<usize, String> {
    let views = registry.generate_role_views(root, projection)?;
    for view in views.values() {
        let path = root
            .join(".codex/agents")
            .join(format!("{}.toml", view.role_id));
        let expected = render_role_view(
            view,
            view.role_id == "skill_evaluator" || projection == "consumer-static",
        );
        let actual = fs::read_to_string(&path)
            .map_err(|_| format!("role_view.content_drift:{}", path.display()))?;
        if actual != expected {
            let relative = path
                .strip_prefix(root)
                .map_err(|_| "role_view.path_outside_root".to_owned())?;
            return Err(format!("role_view.content_drift:{}", relative.display()));
        }
    }
    let static_views = registry.generate_role_views(root, "consumer-static")?;
    let (agent_views, roles) = projection_records(&static_views);
    let projection_digest = digest_json(&JsonValue::Object(
        static_views
            .iter()
            .map(|(role_id, view)| {
                (
                    role_id.clone(),
                    JsonValue::String(view.source_canonical_digest.clone()),
                )
            })
            .collect(),
    ))?;
    let expected_profile = json!({
        "schema_id": "generated_role_profile_projection_v1",
        "materializer": "tools/bin/agent-canon evaluate-codex-agent-roles --generate-role-views",
        "registry_ref": "agents/model_profiles.toml",
        "role_count": static_views.len(),
        "projection_digest": projection_digest,
    });
    let config_path = root.join("agents/agents_config.json");
    let config: JsonValue = serde_json::from_slice(
        &fs::read(&config_path).map_err(|error| format!("agents_config:unreadable:{error}"))?,
    )
    .map_err(|error| format!("agents_config:unreadable:{error}"))?;
    let object = config
        .as_object()
        .ok_or_else(|| "agents_config:must_be_mapping".to_owned())?;
    if object.get("generated_profile_projection") != Some(&expected_profile)
        || object.get("agent_views") != Some(&agent_views)
        || object.get("roles") != Some(&roles)
    {
        return Err("role_view.config_projection_drift:agents/agents_config.json".to_owned());
    }
    Ok(views.len())
}

fn projection_records(views: &BTreeMap<String, GeneratedRoleView>) -> (JsonValue, JsonValue) {
    let agent_views = views
        .iter()
        .map(|(role_id, view)| {
            (
                role_id.clone(),
                json!({
                    "name": view.name,
                    "description": view.description,
                    "nickname_candidates": view.nickname_candidates,
                    "sandbox_mode": view.sandbox_mode,
                    "approval_policy": view.approval_policy,
                    "model": view.model,
                    "model_reasoning_effort": view.reasoning_effort,
                    "developer_instructions": view.rendered_instructions,
                    "logical_role_id": view.logical_role_id,
                    "role_contract_ref": view.role_contract_ref,
                    "profile_id": view.profile_id,
                    "capsule_schema_id": view.capsule_schema_id,
                    "capabilities": view.capabilities,
                    "allowed_context": view.allowed_context,
                    "forbidden_context": view.forbidden_context,
                    "return_schema_id": view.return_schema_id,
                    "checkpoint_policy": view.checkpoint_policy,
                    "continuation_policy": view.continuation_policy,
                    "projection_digest": view.source_canonical_digest,
                }),
            )
        })
        .collect::<serde_json::Map<_, _>>();
    let roles = views
        .values()
        .map(|view| {
            json!({
                "id": view.role_id,
                "profile_id": view.profile_id,
                "capsule_schema_id": view.capsule_schema_id,
                "capabilities": view.capabilities,
                "allowed_context": view.allowed_context,
                "forbidden_context": view.forbidden_context,
                "return_schema_id": view.return_schema_id,
                "checkpoint_policy": view.checkpoint_policy,
                "continuation_policy": view.continuation_policy,
                "projection_digest": view.source_canonical_digest,
            })
        })
        .collect::<Vec<_>>();
    (JsonValue::Object(agent_views), JsonValue::Array(roles))
}

fn render_role_view(view: &GeneratedRoleView, consumer_static: bool) -> String {
    let comments = if consumer_static {
        vec![
            "# generated role view: generated_role_view_v1".to_owned(),
            format!(
                "# source canonical digest: {}",
                view.source_canonical_digest
            ),
        ]
    } else {
        vec![
            "# @dependency-start".to_owned(),
            "# contract configuration".to_owned(),
            format!("# responsibility Projects the canonical {} model profile into executable Codex settings.", view.role_id),
            "# upstream implementation ../../agents/model_profiles.toml owns model/profile authority".to_owned(),
            "# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_agent_role_eval/model_profiles.rs materializes this view".to_owned(),
            "# downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates projection parity".to_owned(),
            "# @dependency-end".to_owned(),
            "# generated role view: generated_role_view_v1".to_owned(),
            "# generated from agents/model_profiles.toml plus canonical team/runtime role metadata".to_owned(),
            "# materializer: tools/bin/agent-canon evaluate-codex-agent-roles --generate-role-views".to_owned(),
            format!("# source canonical digest: {}", view.source_canonical_digest),
        ]
    };
    let mut rows = comments;
    rows.extend([
        String::new(),
        format!("name = {}", toml_string(&view.name)),
        format!("description = {}", toml_string(&view.description)),
        format!(
            "nickname_candidates = [{}]",
            view.nickname_candidates
                .iter()
                .map(|value| toml_string(value))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        format!("sandbox_mode = {}", toml_string(&view.sandbox_mode)),
        format!("approval_policy = {}", toml_string(&view.approval_policy)),
        format!("model = {}", toml_string(&view.model)),
        format!(
            "model_reasoning_effort = {}",
            toml_string(&view.reasoning_effort)
        ),
    ]);
    if let Some(value) = view.model_context_window {
        rows.push(format!("model_context_window = {value}"));
    }
    if let Some(value) = view.model_auto_compact_token_limit {
        rows.push(format!("model_auto_compact_token_limit = {value}"));
    }
    rows.extend([
        String::new(),
        format!(
            "developer_instructions = {}",
            toml_string(&view.rendered_instructions)
        ),
        String::new(),
    ]);
    rows.join("\n")
}

fn toml_string(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".to_owned())
}

fn digest_json(value: &JsonValue) -> Result<String, String> {
    let encoded = serde_json::to_vec(value).map_err(|error| error.to_string())?;
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

fn parse_model_profiles(item: &Item) -> Result<BTreeMap<String, ModelProfile>, String> {
    let tables = item
        .as_array_of_tables()
        .ok_or_else(|| "model_profiles:must_be_nonempty_list".to_owned())?;
    if tables.is_empty() {
        return Err("model_profiles:must_be_nonempty_list".to_owned());
    }
    let mut profiles = BTreeMap::new();
    for (index, table) in tables.iter().enumerate() {
        validate_exact_fields(
            table,
            &[
                "id",
                "model_alias",
                "model",
                "reasoning_effort",
                "owner",
                "capabilities",
                "allowed_context",
                "forbidden_context",
                "return_schema_id",
                "checkpoint_policy",
                "continuation_policy",
                "projection_digest",
                "role_template",
                "prompt_capsule_schema_id",
                "prompt_capsule_template",
                "prompt_capsule_required_context",
                "close_skill_id",
                "close_tool_id",
                "close_tool_argument_schema_id",
                "close_tool_failure_schema_id",
                "close_tool_target_binding",
                "role_instructions",
            ],
            &format!("model_profiles[{index}]"),
        )?;
        let profile = ModelProfile {
            id: table_string(table, "id", &format!("model_profiles[{index}].id"))?,
            model_alias: table_string(
                table,
                "model_alias",
                &format!("model_profiles[{index}].model_alias"),
            )?,
            model: table_string(table, "model", &format!("model_profiles[{index}].model"))?,
            reasoning_effort: table_string(
                table,
                "reasoning_effort",
                &format!("model_profiles[{index}].reasoning_effort"),
            )?,
            role_template: table_string(
                table,
                "role_template",
                &format!("model_profiles[{index}].role_template"),
            )?,
            capabilities: table_string_array(
                table,
                "capabilities",
                &format!("model_profiles[{index}].capabilities"),
            )?,
            allowed_context: table_string_array(
                table,
                "allowed_context",
                &format!("model_profiles[{index}].allowed_context"),
            )?,
            forbidden_context: table_string_array(
                table,
                "forbidden_context",
                &format!("model_profiles[{index}].forbidden_context"),
            )?,
            return_schema_id: table_string(
                table,
                "return_schema_id",
                &format!("model_profiles[{index}].return_schema_id"),
            )?,
            checkpoint_policy: table_string(
                table,
                "checkpoint_policy",
                &format!("model_profiles[{index}].checkpoint_policy"),
            )?,
            continuation_policy: table_string(
                table,
                "continuation_policy",
                &format!("model_profiles[{index}].continuation_policy"),
            )?,
            capsule_schema_id: table_string(
                table,
                "prompt_capsule_schema_id",
                &format!("model_profiles[{index}].prompt_capsule_schema_id"),
            )?,
            role_instructions: parse_clause_array(
                table.get("role_instructions").ok_or_else(|| {
                    format!(
                        "model_profile:{}:missing_role_instructions",
                        profile_id(table)
                    )
                })?,
                &format!("model_profile:{} .role_instructions", profile_id(table)),
            )?,
        };
        for field in [
            "owner",
            "prompt_capsule_template",
            "close_skill_id",
            "close_tool_id",
            "close_tool_argument_schema_id",
            "close_tool_failure_schema_id",
        ] {
            let _ = table_string(table, field, &format!("model_profiles[{index}].{field}"))?;
        }
        if profile
            .allowed_context
            .iter()
            .any(|value| profile.forbidden_context.contains(value))
        {
            return Err(format!("model_profile:{}:context_overlap", profile.id));
        }
        if profile.role_instructions.is_empty() {
            return Err(format!(
                "model_profile:{}:missing_role_instructions",
                profile.id
            ));
        }
        let prompt_required = table_string_array(
            table,
            "prompt_capsule_required_context",
            &format!("model_profiles[{index}].prompt_capsule_required_context"),
        )?;
        if !prompt_required
            .iter()
            .all(|value| profile.allowed_context.contains(value))
        {
            return Err(format!(
                "model_profile:{}:required_context_not_allowed",
                profile.id
            ));
        }
        if table_string(
            table,
            "projection_digest",
            &format!("model_profiles[{index}].projection_digest"),
        )? != "computed_sha256_v1"
        {
            return Err(format!(
                "model_profile:{}:projection_digest_policy_invalid",
                profile.id
            ));
        }
        if table_string(
            table,
            "close_tool_target_binding",
            &format!("model_profiles[{index}].close_tool_target_binding"),
        )? != "terminal_agent_id"
        {
            return Err(format!(
                "model_profile:{}:close_target_mismatch",
                profile.id
            ));
        }
        let profile_id = profile.id.clone();
        if profiles.insert(profile_id.clone(), profile).is_some() {
            return Err(format!("model_profile:{profile_id}:duplicate"));
        }
    }
    Ok(profiles)
}

fn profile_id(table: &dyn TableLike) -> String {
    table
        .get("id")
        .and_then(Item::as_str)
        .unwrap_or("unknown")
        .to_owned()
}

fn parse_role_instruction_templates(
    item: &Item,
) -> Result<BTreeMap<String, Vec<InstructionClause>>, String> {
    let table = item
        .as_table_like()
        .ok_or_else(|| "role_instruction_templates:must_be_mapping".to_owned())?;
    let mut result = BTreeMap::new();
    for (role_id, clauses) in table.iter() {
        let parsed = parse_clause_array(clauses, &format!("role_instruction_templates.{role_id}"))?;
        if parsed.is_empty() {
            return Err(format!(
                "role_instruction_templates.{role_id}:must_be_nonempty_list"
            ));
        }
        result.insert(role_id.to_owned(), parsed);
    }
    Ok(result)
}

fn parse_clause_array(item: &Item, label: &str) -> Result<Vec<InstructionClause>, String> {
    let clauses = item
        .as_array_of_tables()
        .ok_or_else(|| format!("{label}:must_be_list"))?;
    let mut result = Vec::new();
    let mut seen = BTreeSet::new();
    for (index, table) in clauses.iter().enumerate() {
        validate_exact_fields(
            table,
            &[
                "id",
                "text",
                "priority",
                "consumer_static_text",
                "static_obligations",
            ],
            &format!("{label}[{index}]"),
        )?;
        let clause_label = format!("{label}[{index}]");
        let id = table_string(table, "id", &format!("{clause_label}.id"))?;
        if !seen.insert(id.clone()) {
            return Err(format!("role_instruction:{id}:duplicate"));
        }
        let text = table_string(table, "text", &format!("{clause_label}.text"))?;
        let priority = table
            .get("priority")
            .and_then(Item::as_integer)
            .ok_or_else(|| format!("role_instruction:{id}:priority_must_be_int"))?;
        let has_projection_text = table.get("consumer_static_text").is_some();
        let has_obligations = table.get("static_obligations").is_some();
        if has_projection_text != has_obligations {
            return Err(format!(
                "{label}:{id}:consumer_static_projection_incomplete"
            ));
        }
        let (consumer_static_text, static_obligations) = if has_projection_text {
            let projected = table_string(
                table,
                "consumer_static_text",
                &format!("{clause_label}.consumer_static_text"),
            )?;
            if contains_forbidden_prefix(&projected) {
                return Err(format!(
                    "{label}:{id}:consumer_static_text_contains_forbidden_prefix"
                ));
            }
            let values = table
                .get("static_obligations")
                .and_then(Item::as_array)
                .ok_or_else(|| format!("{label}:{id}:static_obligations:must_be_string_list"))?;
            let mut obligations = Vec::with_capacity(values.len());
            for value in values.iter() {
                let obligation = value
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| {
                        format!("{label}:{id}:static_obligations:must_be_string_list")
                    })?;
                if !STATIC_OBLIGATIONS
                    .iter()
                    .any(|(known, _)| *known == obligation)
                {
                    return Err(format!(
                        "{label}:{id}:static_obligations:unknown:{obligation}"
                    ));
                }
                obligations.push(obligation.to_owned());
            }
            (Some(projected), obligations)
        } else {
            if contains_forbidden_prefix(&text) {
                return Err(format!(
                    "{clause_label}:{id}:consumer_static_projection_required"
                ));
            }
            (None, Vec::new())
        };
        result.push(InstructionClause {
            id,
            text,
            priority,
            consumer_static_text,
            static_obligations,
        });
    }
    result.sort_by(|left, right| (left.priority, &left.id).cmp(&(right.priority, &right.id)));
    Ok(result)
}

fn parse_standalone_metadata(
    item: &Item,
) -> Result<BTreeMap<String, StandaloneRoleMetadata>, String> {
    let table = item
        .as_table_like()
        .ok_or_else(|| "standalone_role_metadata:must_be_mapping".to_owned())?;
    let mut result = BTreeMap::new();
    for (role_id, value) in table.iter() {
        let metadata = value
            .as_table_like()
            .ok_or_else(|| format!("standalone_role_metadata.{role_id}:must_be_mapping"))?;
        validate_exact_fields(
            metadata,
            &["logical_role_id", "role_contract_ref", "sandbox_mode"],
            &format!("standalone_role_metadata.{role_id}"),
        )?;
        result.insert(
            role_id.to_owned(),
            StandaloneRoleMetadata {
                logical_role_id: table_string(
                    metadata,
                    "logical_role_id",
                    &format!("standalone_role_metadata.{role_id}.logical_role_id"),
                )?,
                role_contract_ref: table_string(
                    metadata,
                    "role_contract_ref",
                    &format!("standalone_role_metadata.{role_id}.role_contract_ref"),
                )?,
                sandbox_mode: table_string(
                    metadata,
                    "sandbox_mode",
                    &format!("standalone_role_metadata.{role_id}.sandbox_mode"),
                )?,
            },
        );
    }
    Ok(result)
}

fn team_role_metadata(root: &Path) -> Result<BTreeMap<String, TeamRoleMetadata>, String> {
    let path = root.join("agents/agents_config.json");
    let data: JsonValue = serde_json::from_slice(
        &fs::read(&path).map_err(|error| format!("agents_config:unreadable:{error}"))?,
    )
    .map_err(|error| format!("agents_config:unreadable:{error}"))?;
    let object = data
        .as_object()
        .ok_or_else(|| "agents_config:must_be_mapping".to_owned())?;
    let mut result: BTreeMap<String, TeamRoleMetadata> = BTreeMap::new();
    for section in ["always_on_roles", "specialist_roles"] {
        let entries = object
            .get(section)
            .and_then(JsonValue::as_array)
            .ok_or_else(|| format!("agents_config:{section}:must_be_list"))?;
        for (index, entry) in entries.iter().enumerate() {
            let entry = entry
                .as_object()
                .ok_or_else(|| format!("agents_config:{section}[{index}]:must_be_mapping"))?;
            let logical_role = entry
                .get("id")
                .and_then(JsonValue::as_str)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| format!("agents_config:{section}[{index}].id:must_be_text"))?;
            let Some(agent_ids_value) = entry.get("codex_agents") else {
                continue;
            };
            if agent_ids_value.is_null() {
                continue;
            }
            let agent_ids = agent_ids_value
                .as_array()
                .ok_or_else(|| format!("agents_config:{section}[{index}].codex_agents:invalid"))?;
            let write_policy = entry
                .get("write_policy")
                .and_then(JsonValue::as_object)
                .ok_or_else(|| format!("agents_config:{section}[{index}].write_policy:invalid"))?;
            let mode = write_policy
                .get("mode")
                .and_then(JsonValue::as_str)
                .filter(|value| !value.is_empty())
                .ok_or_else(|| {
                    format!("agents_config:{section}[{index}].write_policy.mode:must_be_text")
                })?;
            let sandbox = if mode == "read_only" {
                "read-only"
            } else {
                "workspace-write"
            };
            let role_contract_ref = format!("agents/agents_config.json#/{section}/{index}");
            for agent_id in agent_ids {
                let agent_id = agent_id
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| {
                        format!("agents_config:{section}[{index}].codex_agents:invalid")
                    })?;
                if let Some(prior) = result.get_mut(agent_id) {
                    if prior.sandbox_mode != sandbox {
                        return Err(format!(
                            "agents_config:shared_codex_agent_sandbox_conflict:{agent_id}"
                        ));
                    }
                    prior.logical_role_id = format!("{}+{logical_role}", prior.logical_role_id);
                    prior.role_contract_ref =
                        format!("{}+{role_contract_ref}", prior.role_contract_ref);
                } else {
                    result.insert(
                        agent_id.to_owned(),
                        TeamRoleMetadata {
                            logical_role_id: logical_role.to_owned(),
                            role_contract_ref: role_contract_ref.clone(),
                            sandbox_mode: sandbox.to_owned(),
                        },
                    );
                }
            }
        }
    }
    Ok(result)
}

fn registered_role_descriptions(root: &Path) -> Result<BTreeMap<String, String>, String> {
    let path = root.join(".codex/config.toml");
    let document = read_toml_document(&path)?;
    let agents = document
        .get("agents")
        .and_then(Item::as_table_like)
        .ok_or_else(|| "codex_config:agents_missing".to_owned())?;
    let mut result = BTreeMap::new();
    for (role_id, value) in agents.iter() {
        let Some(value) = value.as_table_like() else {
            continue;
        };
        result.insert(
            role_id.to_owned(),
            table_string(
                value,
                "description",
                &format!("codex_config.agents.{role_id}.description"),
            )?,
        );
    }
    Ok(result)
}

fn context_settings(root: &Path) -> Result<(Option<i64>, Option<i64>), String> {
    let document = read_toml_document(&root.join(".codex/config.toml"))?;
    let mut values = Vec::with_capacity(2);
    for key in ["model_context_window", "model_auto_compact_token_limit"] {
        if let Some(value) = document.get(key) {
            let integer = value
                .as_integer()
                .filter(|integer| *integer > 0)
                .ok_or_else(|| format!("codex_config:{key}:must_be_positive_integer"))?;
            values.push(Some(integer));
        } else {
            values.push(None);
        }
    }
    Ok((values[0], values[1]))
}

fn consumer_static_clause(clause: &InstructionClause) -> Result<String, String> {
    let Some(text) = &clause.consumer_static_text else {
        return Ok(clause.text.clone());
    };
    let mut parts = vec![text.clone()];
    for obligation_id in &clause.static_obligations {
        let fragment = STATIC_OBLIGATIONS
            .iter()
            .find_map(|(id, fragment)| (*id == obligation_id).then_some(*fragment))
            .ok_or_else(|| format!("static_obligation:{obligation_id}:not_found"))?;
        parts.push(fragment.to_owned());
    }
    Ok(parts.join(" "))
}

fn role_projection_digest(
    role_id: &str,
    profile_id: &str,
    clauses: &[InstructionClause],
) -> Result<String, String> {
    let payload = json!({
        "profile_id": profile_id,
        "role_id": role_id,
        "clauses": clauses.iter().map(|clause| json!({
            "id": clause.id,
            "priority": clause.priority,
            "live_text": clause.text,
            "consumer_static_text": clause.consumer_static_text.as_deref().unwrap_or(&clause.text),
            "static_obligations": clause.static_obligations,
        })).collect::<Vec<_>>(),
    });
    let bytes = serde_json::to_vec(&payload).map_err(|error| error.to_string())?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn role_boundary_prompt(role_id: &str) -> String {
    if WRITER_TARGET_ROLE_IDS.contains(&role_id) {
        format!("{CHECKOUT_IDENTITY_PROMPT} {WRITER_TARGET_PROMPT} {CANONICAL_SPAWN_PROMPT}")
    } else if CANONICAL_SPAWN_ROLE_IDS.contains(&role_id) {
        format!("{CHECKOUT_IDENTITY_PROMPT} {CANONICAL_SPAWN_PROMPT}")
    } else {
        CHECKOUT_IDENTITY_PROMPT.to_owned()
    }
}

fn format_role_template(
    template: &str,
    role_id: &str,
    model_alias: &str,
    base_prompt: &str,
) -> Result<String, String> {
    let mut output = String::with_capacity(template.len() + base_prompt.len());
    let mut characters = template.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if character == '{' {
            if characters.peek().is_some_and(|(_, next)| *next == '{') {
                characters.next();
                output.push('{');
                continue;
            }
            let field_start = index + character.len_utf8();
            let rest = &template[field_start..];
            let Some(end_offset) = rest.find('}') else {
                return Err("role_template:unmatched_open_brace".to_owned());
            };
            let field = &rest[..end_offset];
            let replacement = match field {
                "role_id" => role_id,
                "model_alias" => model_alias,
                "base_prompt" => base_prompt,
                _ => return Err(format!("role_template:unknown_field:{field}")),
            };
            output.push_str(replacement);
            let consumed = field_start + end_offset + 1;
            while characters
                .peek()
                .is_some_and(|(next_index, _)| *next_index < consumed)
            {
                characters.next();
            }
        } else if character == '}' {
            if characters.peek().is_some_and(|(_, next)| *next == '}') {
                characters.next();
                output.push('}');
            } else {
                return Err("role_template:unmatched_close_brace".to_owned());
            }
        } else {
            output.push(character);
        }
    }
    Ok(output.trim().to_owned())
}

fn contains_forbidden_prefix(text: &str) -> bool {
    let lowered = text.to_lowercase();
    STATIC_FORBIDDEN_PREFIXES
        .iter()
        .any(|prefix| lowered.contains(prefix))
}

fn required_item<'a>(table: &'a dyn TableLike, key: &str, label: &str) -> Result<&'a Item, String> {
    table
        .get(key)
        .ok_or_else(|| format!("{label}:{key}:missing"))
}

fn table_string(table: &dyn TableLike, key: &str, label: &str) -> Result<String, String> {
    table
        .get(key)
        .and_then(Item::as_str)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| format!("{label}:must_be_text"))
}

fn validate_exact_fields(
    table: &dyn TableLike,
    allowed: &[&str],
    label: &str,
) -> Result<(), String> {
    let allowed = allowed.iter().copied().collect::<BTreeSet<_>>();
    let unknown = table
        .iter()
        .map(|(key, _)| key)
        .filter(|key| !allowed.contains(key))
        .collect::<Vec<_>>();
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(format!("{label}:unknown_fields:{}", unknown.join(",")))
    }
}

fn table_string_array(
    table: &dyn TableLike,
    key: &str,
    label: &str,
) -> Result<Vec<String>, String> {
    let values = table
        .get(key)
        .and_then(Item::as_array)
        .ok_or_else(|| format!("{label}:must_be_string_list"))?;
    let result = values
        .iter()
        .map(|value| {
            value
                .as_str()
                .filter(|value| !value.is_empty())
                .map(str::to_owned)
                .ok_or_else(|| format!("{label}:must_be_string_list"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if result.iter().collect::<BTreeSet<_>>().len() != result.len() {
        return Err(format!("{label}:duplicate"));
    }
    Ok(result)
}

fn string_table(item: &Item, label: &str) -> Result<BTreeMap<String, String>, String> {
    let table = item
        .as_table_like()
        .ok_or_else(|| format!("{label}:must_be_mapping"))?;
    let mut result = BTreeMap::new();
    for (key, value) in table.iter() {
        let value = value
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| format!("{label}.{key}:must_be_text"))?;
        result.insert(key.to_owned(), value.to_owned());
    }
    Ok(result)
}

fn read_toml_document(path: &Path) -> Result<DocumentMut, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    text.parse::<DocumentMut>()
        .map_err(|error| format!("{}: {error}", path.display()))
}
