<!--
@dependency-start
contract reference
responsibility Documents Codex Configuration Reference for this repository.
upstream design ../../ROOT_AGENTS.md template-root Codex runtime entrypoint
upstream implementation ../../.codex/config.toml shared project-scoped Codex config
upstream implementation ../../.codex/hooks.json hook-based runtime startup context
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
- Local evidence: `codex --version`, `codex --help`, `codex exec --help`,
  `codex review --help`, `codex mcp --help`, `codex features list`, and
  `.codex/config.toml`.

## Configuration Surfaces

| Surface | Scope | Main Use |
| ------- | ----- | -------- |
| `$CODEX_HOME/config.toml` or `~/.codex/config.toml` | user / machine | Default model, approvals, sandbox, providers, MCP, hooks, skills, UI, telemetry, profiles. |
| `.codex/config.toml` | repository | Project-scoped defaults checked into the repo. A parent owns its own file; AgentCanon runtime configuration is installed under the isolated runtime `codex-home` by `bootstrap.sh`. |
| CLI `-c key=value` | single invocation | Highest-friction but precise override; accepts dotted paths and TOML-parsed values. |
| CLI `--enable` / `--disable` | single invocation | Shortcut for `features.<name>=true/false`. |
| CLI direct flags | single invocation | Common overrides for model, profile, sandbox, approval policy, cwd, images, web search, and output mode. |
| `.codex/agents/*.toml` / `~/.codex/agents/*.toml` | project / user | Custom subagent roles with model, sandbox, MCP, skills, and instructions overrides. |
| `.codex/personal/skills/**/SKILL.md` and other skill roots | directory / repo / user / system | Reusable task instructions and optional scripts/resources read after skill selection. |
| `AGENTS.md` and fallback project docs | repo tree | Runtime instructions discovered from project root to current working directory. |
| `hooks.json` or `[hooks]` | repo / user | Lifecycle automation around session start, prompt submit, tool use, stop, and permission events. |

## Load and Override Model

Codex combines settings from persistent config, project config, profiles, custom agent config, and CLI flags. For day-to-day operations:

- Put durable repo policy in `.codex/config.toml`.
- Put human-readable task and coding rules in `AGENTS.md`, not in model/provider settings.
- Use user-level `profiles` for reusable modes such as safe review, full-access container runs, or other machine-specific defaults.
- Use CLI `-c` for temporary one-off changes; do not commit temporary operator overrides.
- Treat `experimental_*` and realtime websocket overrides as unstable unless a task explicitly targets those features.

Example temporary overrides:

```bash
codex -c model='"<model-id-from-openai-docs>"' -c model_reasoning_effort='"high"'
codex --enable hooks --search
codex exec --json -c sandbox_mode='"read-only"' "review this repo"
```

## Template Baseline

The current shared template config explicitly owns the parent model, project
tool-output boundary, skill registry, and child-agent registry. This is a
representative excerpt; `.codex/config.toml` is the complete machine-readable
source:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"

model = "gpt-5.6-sol"
model_reasoning_effort = "high"
review_model = "gpt-5.6-luna"
model_context_window = 1000000
tool_output_token_limit = 4096

[agents]
max_threads = 27
max_depth = 2
job_max_runtime_seconds = 3600

[agents.worker]
description = "Implementation agent for bounded code, docs, or test changes."
config_file = "agents/worker.toml"
```

Operational interpretation:

- `approval_policy="on-request"` and `sandbox_mode="workspace-write"` keep the project default within Codex's standard approval and workspace boundary.
- `model="gpt-5.6-sol"` with `model_reasoning_effort="high"` is the parent
  orchestrator projection. `agents/model_profiles.toml` owns child model,
  reasoning, capability, context, return-schema, checkpoint, continuation, and
  digest policy; `.codex/agents/*.toml` and `agents/agents_config.json` are
  generated projections rather than manual model-authority surfaces.
- `tool_output_token_limit=4096` bounds individual tool output admitted to
  context; it is not a task token cap or a reason to omit decision-relevant
  evidence.
- Stable runtime features use Codex defaults instead of project-level feature overrides.
- Codex discovers repo-owned skills automatically from `.codex/personal/skills/`;
  `agents.<role>` registers child roles. Skill workflow authority remains in
  `SKILL.md`, and role behavior and
  model selection remain in each role TOML.
- Reusable runtime profiles belong to machine-local user config. This repository
  does not prescribe profile names or values, and workflow routing does not
  classify a task into a profile before runtime evidence exists.
- `[agents]` sets capacity and registry entries without forcing all agents to spawn.

## Current Template Coverage Matrix

The current repo intentionally configures the shared runtime keys and registries
that require repository-wide agreement.
The lists below are not recommendations to enable every key.
They are an AgentCanon/template-relevant subset of settings that Codex can
accept but this template does not currently put in `.codex/config.toml`; they
are not a complete official schema inventory. Upstream-only API facts are
listed in [上流限定の Codex CLI API 事実](#上流限定の-codex-cli-api-事実).

### Currently Configured Top-Level Keys

| Key | Current Role In This Repo |
| --- | ------------------------- |
| `approval_policy` | Command approval policy; `on-request` is the shared project default. |
| `sandbox_mode` | Filesystem/runtime sandbox mode; `workspace-write` is the shared project default. |
| `model`, `model_reasoning_effort` | Parent orchestrator default: `gpt-5.6-sol/high`. |
| `review_model` | Parent review projection; named child role settings are generated from `agents/model_profiles.toml`. |
| `model_context_window` | Explicit parent context-window declaration. |
| `tool_output_token_limit` | Per-tool output context boundary. |
| `agents` | Capacity limits plus named child-agent registry; role TOMLs own child model and behavior. |

### Top-Level Keys Not Currently In `.codex/config.toml`

| Category | Absent Keys |
| -------- | ----------- |
| Additional model and provider selection | `model_provider`, `model_providers`, `openai_base_url`, `chatgpt_base_url`, `service_tier`, `model_reasoning_summary`, `model_supports_reasoning_summaries`, `model_auto_compact_token_limit`, `model_catalog_json`, `model_instructions_file` |
| Approval, permissions, and sandbox detail | `approvals_reviewer`, `default_permissions`, `permissions`, `sandbox_workspace_write`, `shell_environment_policy`, `allow_login_shell` |
| Project docs and injected context | `instructions`, `developer_instructions`, `include_apps_instructions`, `include_environment_context`, `include_permissions_instructions`, `project_doc_fallback_filenames`, `project_doc_max_bytes`, `project_root_markers`, `projects` |
| Hooks, tools, and integrations | `hooks`, `tools`, `tool_suggest`, `web_search`, `apps`, `plugins`, `marketplaces` |
| MCP OAuth and auth storage | `mcp_oauth_callback_port`, `mcp_oauth_callback_url`, `mcp_oauth_credentials_store`, `cli_auth_credentials_store`, `forced_chatgpt_workspace_id`, `forced_login_method` |
| UI, history, logging, and local state | `tui`, `history`, `log_dir`, `sqlite_home`, `notify`, `file_opener`, `feedback`, `analytics`, `notice`, `check_for_update_on_startup`, `suppress_unstable_features_warning`, `disable_paste_burst`, `commit_attribution`, `compact_prompt`, `hide_agent_reasoning`, `show_raw_agent_reasoning`, `background_terminal_max_timeout` |
| Memory, observability, and snapshots | `memories`, `otel`, `ghost_snapshot`, `auto_review` |
| Realtime, audio, JS, and platform-specific settings | `realtime`, `audio`, `js_repl_node_module_dirs`, `js_repl_node_path`, `windows`, `windows_wsl_setup_acknowledged`, `zsh_path` |
| Experimental thread/realtime/tool overrides | `experimental_compact_prompt_file`, `experimental_realtime_start_instructions`, `experimental_realtime_ws_backend_prompt`, `experimental_realtime_ws_base_url`, `experimental_realtime_ws_model`, `experimental_realtime_ws_startup_context`, `experimental_thread_config_endpoint`, `experimental_thread_store_endpoint`, `experimental_use_freeform_apply_patch`, `experimental_use_unified_exec_tool` |
| Profile selection | `profile`, `personality` |

Interpretation for this template:

- Additional model/provider keys should usually be placed in user config or profiles unless the repo requires a shared default.
- Absent UI, history, audio, notice, Windows, credential-store, and OAuth keys are machine-local by default.
- Absent `hooks` does not mean hooks are unused here; this repo uses the sibling `.codex/hooks.json` surface rather than inline TOML hooks.
- Codex automatically discovers repo-owned `.codex/personal/skills/` packages;
  selecting a skill still precedes reading its `SKILL.md`.
- Absent experimental keys should stay absent unless a task explicitly owns the risk and rollback path.

### 上流限定の Codex CLI API 事実

この節は、上流 Codex CLI の API 事実を参照用に保存する境界です。
AgentCanon / template はこの機能を提供せず、推奨せず、設定の既定値として
所有せず、alias・wrapper・fallback・compatibility route として公開せず、
runtime/config/routing surface として経路化しません。`codex-cli-guide/` に
残る上流例も、template の設定 guidance ではありません。

根拠は次の三つの evidence route に固定します。

- Primary-source route: この文書の [Primary Sources](#primary-sources) にある
  `$openai-docs` route、公式 CLI / Configuration Reference / schema の案内、
  および `codex --version`、`codex --help`、`codex exec --help`、
  `codex features list` の reviewed local evidence。
- Official Codex source/help evidence: upstream `openai/codex` の
  [`codex-rs/exec/src/lib.rs`](https://github.com/openai/codex/blob/main/codex-rs/exec/src/lib.rs)
  にある OSS provider resolution と、公式 CLI reference の
  `--local-provider` / `--oss` の定義。既存 guide の
  `codex-cli-guide/source/codex_cli_guide_config_deepdive.full.md` も、
  `--oss`（source line 459）と `oss_provider`（source line 626）を記録する
  upstream-only reference です。
- Reviewed version evidence: `codex-cli-guide/README.md` の Runtime
  compatibility note が記録する `codex-cli 0.130.0` と、上記 version/help
  route の組合せ。この version evidence は AgentCanon の runtime version
  pin や local-provider support claim ではありません。

| API | 上流 API の事実 |
| --- | --- |
| `--oss` | 上流 Codex CLI の OSS provider mode を選択する。 |
| `--local-provider` | `--oss` と組み合わせる上流の provider 選択 flag である。 |
| `oss_provider` | `--oss` 実行時の上流 provider 選択設定キーである。 |

### Runtime Feature Defaults

Stable runtime features use Codex defaults. Add a project-level feature override only when an owning workflow requires a non-default value and names its validation and rollback evidence.

### Nested Settings Not Currently Used By The Template

| Surface | Configured Here | Schema-Available But Absent Here |
| ------- | --------------- | -------------------------------- |
| `[agents]` | `max_threads`, `max_depth`, `job_max_runtime_seconds`, and inline role entries such as `[agents.<role>]` with `config_file`, `description`, and `nickname_candidates` | task policy strings such as same-role instance rules; keep those in `agents/task_catalog.yaml` and generated `team_manifest.yaml` |
| `.codex/hooks.json` versus `[hooks]` | hooks are stored in `.codex/hooks.json` | inline `[hooks]` entries for `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, and `Stop` |
| `.codex/personal/skills/` | skills are provided as files under `.codex/personal/skills/` and discovered automatically | a project-level skill registry that duplicates the filesystem inventory |

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
| `--no-alt-screen` | TUI display behavior; equivalent to inline terminal mode. |

## AgentCanon/template-relevant `config.toml` subset

The table below is an AgentCanon/template-relevant subset for configuration
ownership and review. It is not a complete transcription of the official
Codex schema. The upstream-only `--oss`, `--local-provider`, and
`oss_provider` API facts are recorded in [上流限定の Codex CLI API 事実](#上流限定の-codex-cli-api-事実)
and are not AgentCanon configuration surfaces.

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
| `otel` | object | OpenTelemetry logs, metrics, and trace export settings. |
| `permissions` | object | Named granular permission profiles. |
| `personality` | enum | Model personality setting, such as `none`, `friendly`, `pragmatic`. |
| `plan_mode_reasoning_effort` | enum | Reasoning effort for plan mode. |
| `plugins` | object | Plugin enablement by plugin name. |
| `profile` | string | Selected named profile. |
| `profiles` | object | Named reusable config overlays. |
| `project_doc_fallback_filenames` | array | Fallback filenames checked after `AGENTS.override.md` and `AGENTS.md`. |
| `project_doc_max_bytes` | integer | Maximum bytes read from project doc files. |
| `project_root_markers` | array | Markers for detecting repo root when scanning `.codex`. |
| `projects` | object | Per-project trust settings. |
| `realtime` | object | Experimental realtime session selection. |
| `review_model` | string | Model used by `/review`. |
| `sandbox_mode` | enum | `read-only`, `workspace-write`, or `danger-full-access`. |
| `sandbox_workspace_write` | object | Writable roots, temp exclusions, and network access for workspace-write sandbox. |
| `service_tier` | enum | Provider- and model-dependent service preference; do not configure a value that the selected model does not advertise. |
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
| `service_tier` | Set only after the selected model advertises the requested tier; otherwise leave it absent. |

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
| `approval_policy` | Coarse approval behavior. Use `on-request` as the shared project default; broader non-interactive authority belongs to an explicit invocation boundary. |
| `approvals_reviewer` | Routes approval requests to `user`, `auto_review`, or `guardian_subagent` where supported. |
| `sandbox_mode` | Filesystem/command sandbox. Use `workspace-write` for repository work and `read-only` for review; broader authority is an explicit invocation decision. |
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
| `max_threads` | Topology-derived requested/configured readback (`20 + 6 = 26` currently); platform-effective and current-available capacity may be lower and cause queueing. |
| `max_depth` | Maximum nested spawned-agent depth. |
| `job_max_runtime_seconds` | Default worker timeout in seconds. |

Custom agents live in `~/.codex/agents/` or `.codex/agents/` as standalone TOML. They can override many normal config keys, including model, reasoning, sandbox, MCP servers, skills, and instructions. The important policy boundary is:

- Use `agents/model_profiles.toml` as profile authority and regenerate `.codex/agents/*.toml` role views.
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
- `Stop` is a legacy event accepted by the dispatcher as an inactive no-op; it
  is not registered in this repository's `hooks.json`.

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
- Active dispatcher failures are fail-open except for the high-confidence
  secret and unauthorized destructive-Git decisions. Local spool failure never
  changes either safety decision. Retired analyzer findings are produced by
  their explicit owner command or skill, not downgraded child-hook output.
- GitHub publication, review, planning, style, OOP, log-surface, notebook, and
  closeout evidence remain owned by their explicit tools and workflow gates;
  they are not active hook work.
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

- `hooks.json` registers one relative `hook_dispatcher.py` command for each of
  `UserPromptSubmit`, `PreToolUse`, and `PostToolUse`. The dispatcher performs
  one bounded parse and stays in-process: it does not spawn children, invoke
  Git, inspect a repository root, or use a network.
- `HOOK_EVENT_CONTRACTS` is the canonical typed table for active/inactive
  events, matchers, failure semantics, and telemetry. Read it with
  `python3 .codex/hooks/hook_dispatcher.py --contract`.
- `UserPromptSubmit` uses the pure `hook_safety.py` leaf for high-confidence
  secret matching. `PreToolUse` uses the same leaf for destructive Git intent;
  a blocked payload exposes only `operation` and `command_sha256` as command
  information.
- `PostToolUse` forwards only a validator-approved exact execution-resource
  projection from the managed producer. Invalid or malformed input is quiet
  and fail-open. The producer uses only the coarse error constants
  `managed_gpu_failure`, `managed_gpu_execution`, and
  `see_execution_resource_plan`, plus the exact admission guarantee and
  bounded opaque namespace required by the validator.
- Each active event creates one `HookLogContext` and writes one bounded,
  fingerprint-only local spool record. Prompt, command, stdout, and stderr
  are not stored; spool failure is independent of the safety decision.
- Former active child routes remain available as standalone analyzers or
  wrappers. `RETIRED_HOOK_ROUTES` maps each one exactly once to its owner,
  explicit command or skill, profile trigger, decision semantics, and artifact.
- Former OOP, notebook, style, log-archive, summary, and auto-sync behavior is
  still available through the explicit owner routes recorded in
  `RETIRED_HOOK_ROUTES`; it is not part of active hook telemetry or blocking.

## Skills

Skills are loaded from multiple roots. Official docs describe repository, user, admin/system, bundled, and plugin-distributed skill locations. For repository work, the most relevant roots are:

- `$CWD/.codex/personal/skills`
- parent-directory `.codex/personal/skills` up to repo root
- `$REPO_ROOT/.codex/personal/skills`
- `$HOME/.codex/personal/skills`
- `/etc/codex/skills`
- bundled system skills

`[skills]` supports:

| Field | Purpose |
| ----- | ------- |
| `include_instructions` | Whether automatic skills instruction block is injected. |
| `bundled.enabled` | Enables or disables bundled skills. |
Operational guidance:

- Keep reusable workflow logic in skills when it must be invoked repeatedly.
- Keep current project policy in `AGENTS.md` and workflow docs.
- Put repository skills in `.codex/personal/skills/<skill>/SKILL.md`; rely on automatic
  discovery instead of enumerating enabled entries in project config.
- If many skills exist, descriptions compete for initial prompt budget; names and descriptions must be concise and distinctive.

## AGENTS.md and Project Docs

Codex uses `AGENTS.md` as project instructions. Config keys affecting discovery are:

| Key | Purpose |
| --- | ------- |
| `project_doc_max_bytes` | Maximum bytes included from project doc files. |
| `project_doc_fallback_filenames` | Fallback filenames checked after `AGENTS.override.md` and `AGENTS.md`. |
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

Profiles are an operator-owned runtime surface. AgentCanon does not duplicate
machine-local profile values or map task labels to profiles. Change a profile
only after observed token, latency, model-effort, or tool-output evidence
identifies that surface, and apply the change in a fresh session. Verify current
keys and model support through `$openai-docs` before editing user config.

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
4. If changing shared canon, read `documents/rule/dependency-module-changes.md`,
   edit the managed topic-workspace source clone, and use the request-evidence-authorized
   `bash bootstrap.sh` の standalone source/runtime route. Parent repository へ
   pin や root projection を戻す操作は行わない。
5. If adding a new document or script, add a dependency header first.
6. Run dependency header scan, dependency graph validation, docs checks, and relevant static checks before closeout.

## Field Stability Notes

- Normal operator keys: `model`, `approval_policy`, `sandbox_mode`, `model_providers`, `mcp_servers`, `tools`, `web_search`, `agents`, `skills`, `hooks`.
- User-level operator keys: `profiles`, UI preferences, and other machine-specific defaults.
- Repo-policy keys: project doc discovery, hooks, MCP, subagent limits, skill instructions, shared defaults.
- Machine-local keys: audio, TUI, credentials stores, notifications, logs, SQLite home, notices, Windows onboarding state.
- Experimental keys: names beginning with `experimental_`, realtime websocket overrides, app-server/thread endpoints, and other fields documented as experimental.
- Sensitive keys: literal bearer tokens, headers, environment inheritance, prompt logging, provider auth, MCP OAuth settings.
