<!--
@dependency-start
contract reference
responsibility Documents Codex Configuration Reference for this repository.
upstream design ../ROOT_AGENTS.md template-root Codex runtime entrypoint
upstream implementation ../.codex/config.toml shared project-scoped Codex config
upstream implementation ../.codex/hooks.json hook-based runtime startup context
downstream design ./codex-configuration-slides.md slide deck derived from this reference
@dependency-end
-->

# Codex Configuration Reference

この文書は Codex CLI / Codex runtime の設定面を、host-provided
`$openai-docs` source route、ローカル `codex --help` / `codex exec --help`
/ `codex review --help` / `codex mcp --help` / `codex features list`、
およびこの template の `.codex/config.toml` から整理したものです。

目的は、agent-canon / template で Codex 設定を変更するときに、設定キー、CLI override、subagent、MCP、hooks、skills、AGENTS.md の責務境界を一か所で確認できるようにすることです。

## Reader Map

Use this reference to answer where Codex configuration lives, which source owns
each setting, and how repo-scoped `.codex/config.toml` relates to CLI overrides,
subagents, MCP servers, hooks, skills, AGENTS.md, profiles, and local state.
Read Primary Sources and Configuration Surfaces first, then use the coverage
matrix and per-key inventory for edits. The later sections group settings by
runtime surface and end with the practical change checklist and stability notes.

## Primary Sources

- `$openai-docs` is the canonical source route for Codex product docs, Codex
  manual synthesis, official Docs MCP fetches, official-domain web alternate route,
  latest-model guidance, model upgrades, and prompt-upgrade guidance.
- Do not duplicate `$openai-docs` bundled alternate route references here. When current
  Codex behavior or model guidance matters, run `$openai-docs` and record the
  resulting run artifact or decision, not a copied official URL list.
- Local evidence: `codex --help`, `codex exec --help`, `codex review --help`,
  `codex mcp --help`, `codex features list`, and `.codex/config.toml`.

## Configuration Surfaces

| Surface | Scope | Main Use |
| ------- | ----- | -------- |
| `$CODEX_HOME/config.toml` or `~/.codex/config.toml` | user / machine | Default model, approvals, sandbox, providers, MCP, hooks, skills, UI, telemetry, profiles. |
| `.codex/config.toml` | repository | Project-scoped defaults checked into the repo. In this template it is canon-owned and symlinked from `vendor/agent-canon/.codex/config.toml`. |
| CLI `-c key=value` | single invocation | Highest-friction but precise override; accepts dotted paths and TOML-parsed values. |
| CLI `--enable` / `--disable` | single invocation | Shortcut for `features.<name>=true/false`. |
| CLI direct flags | single invocation | Common overrides for model, profile, sandbox, approval policy, cwd, images, web search, and output mode. |
| `.codex/agents/*.toml` / `~/.codex/agents/*.toml` | project / user | Custom subagent roles with model, sandbox, MCP, skills, and instructions overrides. |
| `.agents/skills/**/SKILL.md` and other skill roots | directory / repo / user / system | Reusable task instructions and optional scripts/resources. |
| `AGENTS.md` and alternate route project docs | repo tree | Runtime instructions discovered from cwd to root. |
| `hooks.json` or `[hooks]` | repo / user | Lifecycle automation around session start, prompt submit, tool use, stop, and permission events. |

## Load and Override Model

Codex combines settings from persistent config, project config, profiles, custom agent config, and CLI flags. For day-to-day operations:

- Put durable repo policy in `.codex/config.toml`.
- Put human-readable task and coding rules in `AGENTS.md`, not in model/provider settings.
- Use user-level `profiles` for reusable modes such as safe review, full-access container runs, or OSS/local model usage.
- Use CLI `-c` for temporary one-off changes; do not commit temporary operator overrides.
- Treat `experimental_*` and realtime websocket overrides as unstable unless a task explicitly targets those features.

Example temporary overrides:

```bash
codex -c model='"<model-id-from-openai-docs>"' -c model_reasoning_effort='"high"'
codex --enable hooks --search
codex exec --json -c sandbox_mode='"read-only"' "review this repo"
```

## Template Baseline

The current shared template config is intentionally small:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"

review_model = "gpt-5.5"

[features]
hooks = true
goals = true

[agents]
max_threads = 24
max_depth = 2
job_max_runtime_seconds = 3600
```

Operational interpretation:

- `approval_policy="never"` and `sandbox_mode="danger-full-access"` assume the surrounding environment already provides the safety boundary.
- `features.hooks=true` makes hook-defined startup and prompt context part of runtime behavior.
- `features.goals=true` enables the Codex session goal feature; repo-durable loop state still lives in `goal.md` and `tools/agent_tools/goal_loop.py`.
- Reusable runtime profiles such as `token-lite`, `token-standard`, and `token-deep` belong in user-level Codex config. They adjust reasoning effort, verbosity, and per-tool output history budget without weakening review, dependency, or CI gates.
- `[agents]` raises subagent capacity and runtime budget without forcing all agents to spawn.

## Current Template Coverage Matrix

The current repo intentionally configures only a small subset of the official schema.
The lists below are not recommendations to enable every key.
They are an explicit inventory of settings that Codex can accept but this template does not currently put in `.codex/config.toml`.

### Currently Configured Top-Level Keys

| Key | Current Role In This Repo |
| --- | ------------------------- |
| `approval_policy` | Non-interactive execution policy; currently `never` because this template assumes an externally controlled workspace. |
| `sandbox_mode` | Filesystem/runtime sandbox mode; currently `danger-full-access` for externally sandboxed runs. |
| `features` | `features.hooks=true` and `features.goals=true` are configured. |
| `agents` | `max_threads=24` and `job_max_runtime_seconds=3600` are configured. |
| `mcp_servers` | Not configured by the template. |

### Top-Level Keys Not Currently In `.codex/config.toml`

| Category | Absent Keys |
| -------- | ----------- |
| Model and provider selection | `model`, `review_model`, `model_provider`, `model_providers`, `openai_base_url`, `chatgpt_base_url`, `oss_provider`, `service_tier`, `model_reasoning_summary`, `model_supports_reasoning_summaries`, `model_context_window`, `model_auto_compact_token_limit`, `model_catalog_json`, `model_instructions_file` |
| Approval, permissions, and sandbox detail | `approvals_reviewer`, `default_permissions`, `permissions`, `sandbox_workspace_write`, `shell_environment_policy`, `allow_login_shell` |
| Project docs and injected context | `instructions`, `developer_instructions`, `include_apps_instructions`, `include_environment_context`, `include_permissions_instructions`, `project_doc_alternate route_filenames`, `project_doc_max_bytes`, `project_root_markers`, `projects` |
| Hooks, tools, skills, and integrations | `hooks`, `tools`, `tool_suggest`, `web_search`, `skills`, `apps`, `plugins`, `marketplaces` |
| MCP OAuth and auth storage | `mcp_oauth_callback_port`, `mcp_oauth_callback_url`, `mcp_oauth_credentials_store`, `cli_auth_credentials_store`, `forced_chatgpt_workspace_id`, `forced_login_method` |
| UI, history, logging, and local state | `tui`, `history`, `log_dir`, `sqlite_home`, `notify`, `file_opener`, `feedback`, `analytics`, `notice`, `check_for_update_on_startup`, `suppress_unstable_features_warning`, `disable_paste_burst`, `commit_attribution`, `compact_prompt`, `hide_agent_reasoning`, `show_raw_agent_reasoning`, `background_terminal_max_timeout` |
| Memory, observability, and snapshots | `memories`, `otel`, `ghost_snapshot`, `auto_review` |
| Realtime, audio, JS, and platform-specific settings | `realtime`, `audio`, `js_repl_node_module_dirs`, `js_repl_node_path`, `windows`, `windows_wsl_setup_acknowledged`, `zsh_path` |
| Experimental thread/realtime/tool overrides | `experimental_compact_prompt_file`, `experimental_realtime_start_instructions`, `experimental_realtime_ws_backend_prompt`, `experimental_realtime_ws_base_url`, `experimental_realtime_ws_model`, `experimental_realtime_ws_startup_context`, `experimental_thread_config_endpoint`, `experimental_thread_store_endpoint`, `experimental_use_freeform_apply_patch`, `experimental_use_unified_exec_tool` |
| Profile selection | `profile`, `personality` |

Interpretation for this template:

- Absent model/provider keys should usually be placed in user config or profiles unless the repo requires a shared default.
- Absent UI, history, audio, notice, Windows, credential-store, and OAuth keys are machine-local by default.
- Absent `hooks` does not mean hooks are unused here; this repo uses the sibling `.codex/hooks.json` surface rather than inline TOML hooks.
- Absent `skills` does not mean skills are unavailable; this repo provides skills through `.agents/skills/`.
- Absent experimental keys should stay absent unless a task explicitly owns the risk and rollback path.

### Feature Flags Not Currently Enabled Here

The schema currently exposes many feature flags under `[features]`.
This template enables `hooks` and `goals`.
All other schema-listed flags are currently absent from the shared repo config:

```text
apply_patch_freeform
apply_patch_streaming_events
apps
browser_use
child_agents_md
chronicle
code_mode
code_mode_only
codex_git_commit
collab
collaboration_modes
computer_use
connectors
default_mode_request_user_input
elevated_windows_sandbox
enable_experimental_windows_sandbox
enable_fanout
enable_request_compression
exec_permission_approvals
experimental_use_freeform_apply_patch
experimental_use_unified_exec_tool
experimental_windows_sandbox
external_migration
fast_mode
general_analytics
guardian_approval
image_detail_original
image_generation
in_app_browser
include_apply_patch_tool
js_repl
js_repl_tools_only
memories
memory_tool
multi_agent
multi_agent_v2
personality
plugins
prevent_idle_sleep
realtime_conversation
remote_control
remote_models
remote_plugin
request_permissions
request_permissions_tool
request_rule
responses_websockets
responses_websockets_v2
runtime_metrics
search_tool
shell_snapshot
shell_tool
shell_zsh_fork
skill_env_var_dependency_prompt
skill_mcp_dependency_install
sqlite
steer
telepathy
tool_call_mcp_elicitation
tool_search
tool_search_always_defer_mcp_tools
tool_suggest
tui_app_server
unavailable_dummy_tools
undo
unified_exec
use_legacy_landlock
use_linux_sandbox_bwrap
web_search
web_search_cached
web_search_request
workspace_dependencies
workspace_owner_usage_nudge
```

### Nested Settings Not Currently Used By The Template

| Surface | Configured Here | Schema-Available But Absent Here |
| ------- | --------------- | -------------------------------- |
| `[agents]` | `max_threads`, `max_depth`, `job_max_runtime_seconds`, and inline role entries such as `[agents.<role>]` with `config_file`, `description`, and `nickname_candidates` | task policy strings such as same-role instance rules; keep those in `agents/task_catalog.yaml` and generated `team_manifest.yaml` |
| `.codex/hooks.json` versus `[hooks]` | hooks are stored in `.codex/hooks.json` | inline `[hooks]` entries for `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, and `Stop` |
| `.agents/skills/` versus `[skills]` | skills are provided as files under `.agents/skills/` | `[skills] include_instructions`, `[skills.bundled]`, and `[[skills.config]]` name/path enablement entries |

Use this matrix during reviews: if a task proposes adding one of these absent keys, require a short reason for why it belongs in shared repo config rather than user config, a profile, CLI override, hook file, skill file, or machine-local state.

## CLI Commands and Config-Relevant Flags

| Command | Config-relevant behavior |
| ------- | ------------------------ |
| `codex [PROMPT]` | Interactive CLI. Accepts config override flags and starts from current or specified cwd. |
| `codex exec [PROMPT]` | Non-interactive run. Adds `--json`, `--output-schema`, `--output-last-message`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, and `--skip-git-repo-check`. |
| `codex review [PROMPT]` | Non-interactive code review. Accepts `--uncommitted`, `--base`, `--commit`, and `--title`. |
| `codex mcp` | Manage MCP server config; `add`, `list`, `get`, `remove`, `login`, `logout`. |
| `codex plugin` | Manage plugin distribution surfaces. |
| `codex mcp-server` | Start Codex itself as an MCP server over stdio. |
| `codex app-server` | Experimental app server surface. |
| `codex completion` | Generate shell completion scripts. |
| `codex sandbox` | Run commands inside a Codex-provided sandbox. |
| `codex debug` | Debugging tools. |
| `codex apply` | Apply latest agent diff with `git apply`. |
| `codex resume` / `codex fork` | Continue or fork prior sessions. |
| `codex cloud` | Experimental Codex Cloud task browser. |
| `codex exec-server` | Experimental standalone exec-server service. |
| `codex features` | Inspect feature flags. |

Common root and `exec` flags:

| Flag | Equivalent or effect |
| ---- | -------------------- |
| `-c, --config <key=value>` | Override a config key with dotted path support and TOML value parsing. |
| `--enable <FEATURE>` | Same as `-c features.<FEATURE>=true`. |
| `--disable <FEATURE>` | Same as `-c features.<FEATURE>=false`. |
| `-m, --model <MODEL>` | Overrides `model`. |
| `-p, --profile <PROFILE>` | Selects `profile`. |
| `-s, --sandbox <MODE>` | Overrides `sandbox_mode`; values are `read-only`, `workspace-write`, `danger-full-access`. |
| `-a, --ask-for-approval <POLICY>` | Overrides approval behavior; local help lists `untrusted`, deprecated `on-failure`, `on-request`, and `never`. |
| `--full-auto` | Convenience low-friction sandboxed execution mode. |
| `--dangerously-bypass-approvals-and-sandbox` | Disables prompts and sandboxing; only appropriate inside an external sandbox. |
| `-C, --cd <DIR>` | Sets working root. |
| `--add-dir <DIR>` | Adds writable directories beside the main workspace. |
| `--search` | Enables live web search for the run. |
| `-i, --image <FILE>` | Attaches initial images. |
| `--oss` / `--local-provider` | Use local open-source provider selection. |
| `--no-alt-screen` | TUI display behavior; equivalent to inline terminal mode. |

## Top-Level `config.toml` Inventory

The official schema currently exposes the following top-level keys. Some are normal operator controls; others are machine-local state, UI state, or experimental surfaces.

| Key | Type | Purpose |
| --- | ---- | ------- |
| `agents` | object | Subagent thread, depth, and runtime limits. |
| `allow_login_shell` | boolean | Controls whether shell tools may request or default to login shells. |
| `analytics` | object | Product analytics enablement. |
| `approval_policy` | string or object | Default command approval policy. |
| `approvals_reviewer` | enum | Where escalated approvals are routed after escalation. |
| `apps` | object | App/connector tool enablement and approval settings. |
| `audio` | object | Machine-local realtime audio device preferences. |
| `auto_review` | object | Additional policy for guardian auto-review. |
| `background_terminal_max_timeout` | integer | Maximum background terminal poll window in milliseconds. |
| `chatgpt_base_url` | string | Base URL for ChatGPT-surface requests. |
| `check_for_update_on_startup` | boolean | Startup update prompt behavior. |
| `cli_auth_credentials_store` | enum | CLI auth credential backend: file, keyring, or auto. |
| `commit_attribution` | string | Commit message co-author attribution text; empty disables automatic attribution. |
| `compact_prompt` | string | Prompt used when compacting history. |
| `default_permissions` | string | Named permissions profile from `[permissions]`. |
| `developer_instructions` | string | Developer-role instructions injected by config. |
| `disable_paste_burst` | boolean | TUI paste burst detection behavior. |
| `experimental_compact_prompt_file` | path | Experimental external compact prompt file. |
| `experimental_realtime_start_instructions` | string | Experimental realtime instruction override. |
| `experimental_realtime_ws_backend_prompt` | string | Experimental websocket backend prompt override. |
| `experimental_realtime_ws_base_url` | string | Experimental websocket base URL override. |
| `experimental_realtime_ws_model` | string | Experimental websocket model override. |
| `experimental_realtime_ws_startup_context` | string | Experimental realtime startup context override. |
| `experimental_thread_config_endpoint` | string | Experimental remote thread config endpoint. |
| `experimental_thread_store_endpoint` | string | Experimental remote thread store endpoint. |
| `experimental_use_freeform_apply_patch` | boolean | Experimental apply-patch tool mode. |
| `experimental_use_unified_exec_tool` | boolean | Experimental unified exec tool mode. |
| `features` | object | Central feature flags; preferred over scattered individual toggles. |
| `feedback` | object | Product feedback flow enablement. |
| `file_opener` | object | URI scheme for clickable file citations. |
| `forced_chatgpt_workspace_id` | string | Restricts ChatGPT login to a workspace. |
| `forced_login_method` | enum | Restricts permitted login method. |
| `ghost_snapshot` | object | Undo snapshot warning and ignore thresholds. |
| `hide_agent_reasoning` | boolean | Hides reasoning events in UI/output. |
| `history` | object | `history.jsonl` persistence and size behavior. |
| `hooks` | object | Inline TOML lifecycle hooks. |
| `include_apps_instructions` | boolean | Injects app/connector instructions. |
| `include_environment_context` | boolean | Injects environment context block. |
| `include_permissions_instructions` | boolean | Injects permissions instruction block. |
| `instructions` | string | System instructions. |
| `js_repl_node_module_dirs` | array | Node module search dirs for JS REPL. |
| `js_repl_node_path` | path | Node runtime for JS REPL. |
| `log_dir` | path | Codex log directory. |
| `marketplaces` | object | User-level marketplace entries. |
| `mcp_oauth_callback_port` | integer | Fixed local MCP OAuth callback port. |
| `mcp_oauth_callback_url` | string | MCP OAuth redirect URI override. |
| `mcp_oauth_credentials_store` | enum | MCP OAuth credential backend. |
| `mcp_servers` | object | MCP server definitions. |
| `memories` | object | Memory extraction, consolidation, and injection settings. |
| `model` | string | Model selection. |
| `model_auto_compact_token_limit` | integer | Token threshold for auto-compaction. |
| `model_catalog_json` | path | Optional model catalog loaded on startup. |
| `model_context_window` | integer | Model context window override in tokens. |
| `model_instructions_file` | path | External model instructions override; avoid unless deliberately replacing built-ins. |
| `model_provider` | string | Key into `model_providers`. |
| `model_providers` | object | Custom provider definitions. |
| `model_reasoning_effort` | enum | Reasoning effort: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`. |
| `model_reasoning_summary` | enum or object | Reasoning summary behavior. |
| `model_supports_reasoning_summaries` | boolean | Force-enable reasoning summaries for a model. |
| `model_verbosity` | enum | GPT-5 verbosity: `low`, `medium`, `high`. |
| `notice` | object | Local acknowledgement state for product notices. |
| `notify` | array | External notification command. |
| `openai_base_url` | string | Built-in OpenAI provider base URL override. |
| `oss_provider` | string | Preferred local OSS provider, such as LM Studio or Ollama. |
| `otel` | object | OpenTelemetry logs, metrics, and trace export settings. |
| `permissions` | object | Named granular permission profiles. |
| `personality` | enum | Model personality setting, such as `none`, `friendly`, `pragmatic`. |
| `plan_mode_reasoning_effort` | enum | Reasoning effort for plan mode. |
| `plugins` | object | Plugin enablement by plugin name. |
| `profile` | string | Selected named profile. |
| `profiles` | object | Named reusable config overlays. |
| `project_doc_alternate route_filenames` | array | Alternate route filenames when `AGENTS.md` is missing. |
| `project_doc_max_bytes` | integer | Maximum bytes read from project doc files. |
| `project_root_markers` | array | Markers for detecting repo root when scanning `.codex`. |
| `projects` | object | Per-project trust settings. |
| `realtime` | object | Experimental realtime session selection. |
| `review_model` | string | Model used by `/review`. |
| `sandbox_mode` | enum | `read-only`, `workspace-write`, or `danger-full-access`. |
| `sandbox_workspace_write` | object | Writable roots, temp exclusions, and network access for workspace-write sandbox. |
| `service_tier` | enum | Service tier preference such as `fast` or `flex`. |
| `shell_environment_policy` | object | Environment inheritance, include/exclude regexes, and forced variables. |
| `show_raw_agent_reasoning` | boolean | Shows raw reasoning content events. |
| `skills` | object | Skill config entries and automatic skill instruction injection. |
| `sqlite_home` | path | SQLite state DB directory. |
| `suppress_unstable_features_warning` | boolean | Suppresses unstable feature warnings. |
| `tool_output_token_limit` | integer | Context budget for tool/function outputs. |
| `tool_suggest` | object | Discoverable tool suggestions. |
| `tools` | object | Tool feature toggles. |
| `tui` | object | Terminal UI preferences. |
| `web_search` | enum or object | Web search mode: disabled, cached, or live. |
| `windows` | object | Windows sandbox behavior. |
| `windows_wsl_setup_acknowledged` | boolean | Windows WSL onboarding acknowledgement. |
| `zsh_path` | path | Patched zsh path for zsh exec bridge. |

## Model and Provider Settings

| Key | Recommended Use |
| --- | --------------- |
| `model` | Select the model for normal turns. Keep repo defaults conservative; use profiles or CLI for experiments. |
| `review_model` | Use a separate reviewer model when review quality/cost should differ from implementation. |
| `model_reasoning_effort` | Set default reasoning budget. For current frontier models or complex repo tasks, prefer profile-specific `high` rather than forcing all runs; choose model IDs through `$openai-docs`. |
| `plan_mode_reasoning_effort` | Plan mode can use a different budget from implementation mode. |
| `model_verbosity` | Controls GPT-5 response detail; use `medium` or `high` for design docs, `low` for terse automation. |
| `model_provider` | Points to `model_providers.<id>`. |
| `openai_base_url` | Override only the built-in OpenAI provider URL. |
| `chatgpt_base_url` | Override ChatGPT-specific requests separately from API provider requests. |
| `oss_provider` | Select a local provider when `--oss` is used. |
| `service_tier` | Select fast/flex service preference where supported. |

`[model_providers.<id>]` supports:

| Field | Purpose |
| ----- | ------- |
| `name` | Human-readable provider name. |
| `base_url` | OpenAI-compatible API base URL. |
| `wire_api` | Wire protocol expected by the provider. |
| `env_key` | Environment variable containing the API key. |
| `env_key_instructions` | Help text for acquiring and setting the key. |
| `http_headers` | Literal HTTP headers. |
| `env_http_headers` | Headers whose values come from environment variables. |
| `query_params` | Query parameters appended to the provider base URL. |
| `request_max_retries` | HTTP request retry count. |
| `stream_max_retries` | Streaming reconnect retry count. |
| `stream_idle_timeout_ms` | Streaming idle timeout. |
| `supports_websockets` | Whether the provider supports Responses API WebSocket transport. |
| `websocket_connect_timeout_ms` | WebSocket connection timeout. |
| `requires_openai_auth` | Whether OpenAI login or API-key auth is required. |
| `experimental_bearer_token` | Literal bearer token; avoid for committed config. |
| `auth` / `aws` | Command-backed bearer token or AWS SigV4 auth. |

## Approval, Sandbox, and Permissions

| Setting | Use |
| ------- | --- |
| `approval_policy` | Coarse approval behavior. Local CLI help exposes `untrusted`, deprecated `on-failure`, `on-request`, and `never`. |
| `approvals_reviewer` | Routes approval requests to `user`, `auto_review`, or `guardian_subagent` where supported. |
| `sandbox_mode` | Filesystem/command sandbox: `read-only`, `workspace-write`, or `danger-full-access`. |
| `sandbox_workspace_write.writable_roots` | Extra writable roots for workspace-write mode. |
| `sandbox_workspace_write.network_access` | Network availability in workspace-write mode. |
| `sandbox_workspace_write.exclude_slash_tmp` | Exclude `/tmp` from writable sandbox assumptions. |
| `sandbox_workspace_write.exclude_tmpdir_env_var` | Exclude `$TMPDIR` from writable sandbox assumptions. |
| `permissions` | Named profiles for filesystem and network permissions. |
| `default_permissions` | Selects the default named permission profile. |

Granular approval config supports booleans for:

- `sandbox_approval`
- `request_permissions`
- `mcp_elicitations`
- `skill_approval`
- `rules`

Network permission config supports:

- `enabled`
- `mode = "limited" | "full"`
- `domains`
- `unix_sockets`
- `proxy_url`
- `socks_url`
- `allow_local_binding`
- `allow_upstream_proxy`
- `enable_socks5`
- `enable_socks5_udp`
- `dangerously_allow_all_unix_sockets`
- `dangerously_allow_non_loopback_proxy`

## Subagents and Custom Agents

`[agents]` controls runtime limits, not task policy:

| Field | Purpose |
| ----- | ------- |
| `max_threads` | Maximum concurrent agent threads. |
| `max_depth` | Maximum nested spawned-agent depth. |
| `job_max_runtime_seconds` | Default worker timeout in seconds. |

Custom agents live in `~/.codex/agents/` or `.codex/agents/` as standalone TOML. They can override many normal config keys, including model, reasoning, sandbox, MCP servers, skills, and instructions. The important policy boundary is:

- Use `.codex/agents/*.toml` to define role behavior.
- Use `AGENTS.md` and workflow docs to define when roles may be used.
- Do not rely on high `max_threads` alone to improve work quality; fan-out still needs owner, input packet, write scope, and review gate.

## MCP Servers

MCP servers are configured under `[mcp_servers.<name>]` or with `codex mcp add`.

| Field | Purpose |
| ----- | ------- |
| `command` | Stdio server command. |
| `args` | Command arguments. |
| `cwd` | Working directory for stdio server. |
| `env` | Fixed environment variables. |
| `env_vars` | Environment variables to pass through. |
| `url` | Streamable HTTP server URL. |
| `bearer_token_env_var` | Environment variable containing HTTP bearer token. |
| `http_headers` | Literal HTTP headers. |
| `env_http_headers` | Headers sourced from environment variables. |
| `enabled` | Whether the server is active. |
| `required` | Whether Codex startup should fail if the server cannot start. |
| `startup_timeout_sec` / `startup_timeout_ms` | Startup timeout. |
| `tool_timeout_sec` | Tool call timeout. |
| `enabled_tools` | Allowlist tools. |
| `disabled_tools` | Denylist tools. |
| `tools` | Per-tool settings. |
| `default_tools_approval_mode` | Approval mode for tools unless overridden. |
| `supports_parallel_tool_calls` | Whether the server can handle parallel calls. |
| `oauth_resource` / `scopes` | OAuth resource and scopes. |
| `experimental_environment` | Experimental environment selector. |
| `name` | Legacy display name. |

CLI management:

```bash
codex mcp list --json
codex mcp add docs --url https://example.invalid/mcp
codex mcp remove repo
codex mcp login repo
codex mcp logout repo
```

Template guidance for MCP:

- Keep MCP server configuration out of shared AgentCanon runtime unless a task
  explicitly needs an external connector.
- Prefer deterministic AgentCanon CLI tools for repo-local checks and goal-loop
  gates.

## Hooks

Hooks can be configured inline under `[hooks]` or in `hooks.json`. Official events include:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `PermissionRequest`
- `Stop`

Use hooks for deterministic runtime checks, not for replacing workflow policy:

- Start or verify repo-local MCP surfaces early.
- Inject stable environment/context hints.
- Record hook invocations, OOP guard results, and skill usage signals for later audit.
- Avoid long-running logic in hooks unless timeouts are explicit.
- Keep pre-tool hooks out of the shared default unless they can deterministically
  repair state or prevent high-confidence secret/destructive actions without
  interrupting normal repository work.

Hook output may include hook-specific structured results. Treat hook failures as runtime evidence to fix, not as optional noise.

### Hook Severity Policy

Runtime hooks must not become the reason normal read-only inspection, validation,
repair, or PR evidence work cannot proceed. AgentCanon therefore uses these
severity rules:

- `block` is reserved for high-confidence public-accident prevention such as
  obvious API keys or private keys in a prompt. Add new runtime blockers only
  when the finding is deterministic, mechanically fixable, and safer to stop
  immediately than to continue.
- Process, search, reuse, planning, review completeness, style, OOP,
  module-boundary, helper-first, log-surface, notebook, and closeout discipline
  findings are warning/evidence by default. They should be fixed before
  closeout, but they must not require moving hook config aside or disabling
  hooks to keep working.
- Child hook failures are fail-open by default. They surface as warning context
  with repair commands. Use `AGENT_CANON_HOOK_STRICT_FAILURES=1` only while
  explicitly developing or validating the hook itself.
- Child `decision=block` output is downgraded to official warning context unless
  the child script is listed in `CRITICAL_BLOCKING_CHILD_HOOKS` or
  `AGENT_CANON_HOOK_STRICT_BLOCKS=1` is set for explicit enforcement tests.
- GitPush, GitHub branch publish, safe `gh pr` create/edit/view/list/checks/comment
  operations, and `github_publish.py` are publish/evidence work owned by the
  GitHub publish tool and PR gate. Hook dispatcher child guards skip these
  operations so non-critical style, OOP, log-surface, planning, or closeout
  findings cannot block branch publication or PR evidence updates.
- AGENTS / ROOT_AGENTS policy prose should first ask whether a rule belongs in
  a checker, warning hook, closeout gate, role TOML, workflow eval, or PR gate
  before adding more prompt-only prohibitions.

Legacy forwarders and migration wrappers report migration evidence through
stable warning fields. A deprecated forwarder emits `*_FORWARDER=deprecated`,
`*_FORWARDER_SEVERITY=fix-now`, caller chain, and the canonical command route.
The tool implementation owns detailed fields such as `FORWARDER_CALLER`,
`FORWARDER_ACTION`, `FORWARDER_PROMPT`, and `caller_process_chain`; this
configuration reference owns the operator-facing routing policy.

Template-specific hook behavior:

- `hooks.json` wires one `hook_dispatcher.py` command per active lifecycle
  event. The dispatcher replays the original stdin payload to the child guard
  scripts in the configured order, preserves log opportunities, and normalizes
  non-critical child findings into official warning context.
- The dispatcher bypasses child guards for `GitStatus`, read-only file / Git
  inspection, and known validation commands including AgentCanon
  plan/status/latest-check inspection. Do not rename, move, or temporarily
  disable `hooks.json` to inspect hook state or run validation.
- The dispatcher also bypasses child guards for GitHub publish/PR commands.
  Publish tools must still verify the GitHub remote and user task explicitly;
  the bypass only prevents unrelated hook findings from stopping the write.
- `UserPromptSubmit` runs prompt secret scanning, skill usage logging, and
  reference capture checks.
- `PreToolUse` runs `direct_rg_context_guard.py` to emit
  `DIRECT_RG_CONTEXT_RISK=warn` when a shell command uses broad direct
  broad text-search output. It does not block the tool call; it asks the agent to replace
  broad output with bounded paths, `--max-count`, or exclusions for
  `.agent-canon/log-archive/**`, `reports/**`, and `*.jsonl`.
- `PostToolUse` runs tool/subagent logging, reference capture, OOP readability,
  module boundary, library implementation, helper inventory, helper-first,
  style, log-surface inventory, and notebook quality checks as warning/evidence
  guardrails by default.
- `Stop` runs goal completion, the post-edit guard suite, reference capture,
  and final skill usage logging as closeout repair context by default.
- The OOP hook emits warning/approve output for readability findings and keeps
  explicit OOP validation available as a closeout gate. Use
  `AGENT_CANON_OOP_HOOK_MODE=diff` only when the user explicitly requests
  baseline-only checking; `AGENT_CANON_OOP_HOOK_BASELINE_REF` overrides the
  diff baseline when needed.
- Notebook quality checks block notebook-as-test misuse: fine-grained assertions,
  pytest/unittest imports, `test_` helpers, stored error output, missing narrative,
  missing code, or missing visualization. Detailed test coverage belongs in `tests/`.
- Style checker logs record selected Python / C++ / notebook / Markdown checkers and `unchecked_files` for changed paths with no automatic checker.
- Hook logs append to the mounted runtime log archive
  `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook>.jsonl`.
  Accumulated eval reports append under
  `.agent-canon/log-archive/eval-results/<family>/`, Codex runtime summaries
  under `.agent-canon/log-archive/codex-runtime/<repo-key>/chats/<conversation-id>/summary.jsonl`
  with `.agent-canon/log-archive/codex-runtime/<repo-key>/index.jsonl`, and agent run
  reports under `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/`.
  `log_archive_mount_warning.py` warns, without blocking, when that archive is
  missing and asks the agent to run `runtime_log_archive_git.py ensure` first.
  `runtime_log_auto_sync.py` runs `runtime_log_archive_git.py sync` from Stop
  so normal accumulation does not require a separate agent action.
  The archive remote and branch policy are documented in
  `documents/runtime-log-archive.md`; source-tree `agents/evals/results/`
  paths are not normal read or write locations.
- Hook log entries include `hook_run_id`, `payload_fingerprint`, `mode`,
  `baseline_ref`, and status fields. Local log paths can be overridden with
  `AGENT_CANON_HOOK_ARCHIVE_DIR`, `AGENT_CANON_HOOK_RESULTS_DIR`,
  `AGENT_CANON_OOP_HOOK_LOG_PATH`, `AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH`,
  `AGENT_CANON_NOTEBOOK_QUALITY_HOOK_LOG_PATH`, and `AGENT_CANON_SKILL_LOG_PATH`.

## Skills

Skills are loaded from multiple roots. Official docs describe repository, user, admin/system, bundled, and plugin-distributed skill locations. For repository work, the most relevant roots are:

- `$CWD/.agents/skills`
- parent-directory `.agents/skills` up to repo root
- `$REPO_ROOT/.agents/skills`
- `$HOME/.agents/skills`
- `/etc/codex/skills`
- bundled system skills

`[skills]` supports:

| Field | Purpose |
| ----- | ------- |
| `include_instructions` | Whether automatic skills instruction block is injected. |
| `bundled.enabled` | Enables or disables bundled skills. |
| `[[skills.config]] name` | Select a skill by name. |
| `[[skills.config]] path` | Select a skill by path. |
| `[[skills.config]] enabled` | Enable or disable selected skill. |

Operational guidance:

- Keep reusable workflow logic in skills when it must be invoked repeatedly.
- Keep current project policy in `AGENTS.md` and workflow docs.
- If many skills exist, descriptions compete for initial prompt budget; names and descriptions must be concise and distinctive.

## AGENTS.md and Project Docs

Codex uses `AGENTS.md` as project instructions. Config keys affecting discovery are:

| Key | Purpose |
| --- | ------- |
| `project_doc_max_bytes` | Maximum bytes included from project doc files. |
| `project_doc_alternate route_filenames` | Alternative filenames when `AGENTS.md` is missing. |
| `project_root_markers` | Root-detection markers used while searching for `.codex` folders. |
| `include_environment_context` | Whether environment context block is injected. |
| `include_permissions_instructions` | Whether permissions instruction block is injected. |
| `include_apps_instructions` | Whether app instructions block is injected. |

Policy boundary:

- `AGENTS.md` should say what must happen.
- `config.toml` should say how the runtime is configured.
- hooks should enforce deterministic startup/tool behavior.
- run bundles should preserve task-specific evidence.

## User-Level Profiles

`[profiles.<name>]` can override many of the same keys as the root config, but
current Codex warns when project-local `.codex/config.toml` defines profiles.
Keep reusable profiles in `~/.codex/config.toml` or `$CODEX_HOME/config.toml`:

- `model`, `model_provider`, `model_reasoning_effort`, `plan_mode_reasoning_effort`, `model_verbosity`
- `approval_policy`, `approvals_reviewer`, `sandbox_mode`
- `tools`, `web_search`
- `features`
- `service_tier`
- `personality`
- `windows`
- `zsh_path`
- selected prompt/context toggles

Use user-level profiles for operator modes:

```toml
[profiles.token-lite]
model_reasoning_effort = "minimal"
plan_mode_reasoning_effort = "minimal"
model_verbosity = "low"
tool_output_token_limit = 3000

[profiles.token-standard]
model_reasoning_effort = "medium"
plan_mode_reasoning_effort = "medium"
model_verbosity = "medium"
tool_output_token_limit = 4000

[profiles.token-deep]
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "high"
model_verbosity = "medium"
tool_output_token_limit = 8000

[profiles.review]
model = "<model-id-from-openai-docs>"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
approval_policy = "never"

[profiles.container-full]
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

## Tools and Web Search

| Key | Purpose |
| --- | ------- |
| `tools.view_image` | Enables local image attachment/viewing tool. |
| `tools.web_search` | Nested web-search tool config. |
| `web_search` | Top-level web search mode; schema lists `disabled`, `cached`, and `live`. |
| `tool_output_token_limit` | Limits stored tool output tokens. |
| `tool_suggest` | Configures discoverable tool suggestions. |

For documentation and high-stakes current facts, prefer live official sources. For deterministic repo work, avoid accidental external dependency by keeping web search disabled unless the task requires it.

## UI, History, Logging, and Local State

| Area | Key fields |
| ---- | ---------- |
| TUI | `tui.alternate_screen`, `tui.animations`, `tui.notifications`, `tui.notification_method`, `tui.notification_condition`, `tui.show_tooltips`, `tui.status_line`, `tui.terminal_title`, `tui.theme`. |
| History | `history.persistence`, `history.max_bytes`. |
| Logs | `log_dir`, `sqlite_home`. |
| Notifications | `notify`. |
| File links | `file_opener`. |
| Notices | `notice.*` local acknowledgement flags. |
| Feedback and analytics | `feedback.enabled`, `analytics.enabled`. |
| Updates | `check_for_update_on_startup`, `suppress_unstable_features_warning`. |

Do not commit machine-local state unless it is intentionally shared template policy.

## Realtime, Audio, Apps, Plugins, and Marketplaces

| Area | Keys |
| ---- | ---- |
| Realtime | `realtime.version`, `realtime.type`, `realtime.transport`, `realtime.voice`, plus experimental websocket overrides. |
| Audio | `audio.microphone`, `audio.speaker`. |
| Apps | `apps._default`, `apps.<app>.enabled`, `default_tools_enabled`, destructive/open-world controls, and per-tool controls. |
| Plugins | `plugins.<name>.enabled`. |
| Marketplaces | `marketplaces.<name>.source`, `source_type`, `ref`, `sparse_paths`, `last_revision`, `last_updated`. |

These are usually user- or machine-level controls. In repo config, only commit them when the project deliberately depends on that surface.

## Shell Environment

`[shell_environment_policy]` controls inherited and forced environment:

| Field | Purpose |
| ----- | ------- |
| `inherit` | How much of the parent environment to inherit. |
| `include_only` | Regex allowlist. |
| `exclude` | Regex denylist. |
| `ignore_default_excludes` | Disable built-in excludes. |
| `set` | Fixed environment variables. |
| `experimental_use_profile` | Experimental profile shell behavior. |

Use this to make tool runs reproducible and to avoid leaking credentials into model-triggered commands.

## Observability

`[otel]` supports:

| Field | Purpose |
| ----- | ------- |
| `environment` | Marks traces as dev, staging, prod, test, etc. |
| `trace_exporter` | Trace exporter. |
| `metrics_exporter` | Metrics exporter. |
| `exporter` | Log exporter. |
| `log_user_prompt` | Whether user prompts are logged in traces. |

If prompts or repo data are sensitive, keep `log_user_prompt=false` unless the environment is explicitly approved.

## Windows

`[windows]` supports:

| Field | Purpose |
| ----- | ------- |
| `sandbox` | `elevated` or `unelevated`. |
| `sandbox_private_desktop` | Whether sandboxed child process runs on a private desktop. |

`windows_wsl_setup_acknowledged` is local onboarding state, not project policy.

## Practical Change Checklist

Before changing Codex config in this repo:

1. Identify the target surface: user config, repo config, custom agent, hook, skill, MCP, or AGENTS.md.
2. Check this reference and the official schema for the exact key name.
3. Prefer repo policy in `AGENTS.md` and runtime mechanics in `.codex/config.toml`.
4. If changing shared canon, edit `vendor/agent-canon/` and run `bash tools/sync_agent_canon.sh link-root`.
5. If adding a new document or script, add a dependency header first.
6. Run dependency header scan, dependency graph validation, docs checks, and relevant static checks before closeout.

## Field Stability Notes

- Normal operator keys: `model`, `approval_policy`, `sandbox_mode`, `model_providers`, `mcp_servers`, `tools`, `web_search`, `agents`, `skills`, `hooks`.
- User-level operator keys: `profiles`, UI preferences, local model/provider experiments, and other machine-specific defaults.
- Repo-policy keys: project doc discovery, hooks, MCP, subagent limits, skill instructions, shared defaults.
- Machine-local keys: audio, TUI, credentials stores, notifications, logs, SQLite home, notices, Windows onboarding state.
- Experimental keys: names beginning with `experimental_`, realtime websocket overrides, app-server/thread endpoints, and other fields documented as experimental.
- Sensitive keys: literal bearer tokens, headers, environment inheritance, prompt logging, provider auth, MCP OAuth settings.
