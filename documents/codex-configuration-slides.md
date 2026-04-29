<!--
@dependency-start
responsibility Documents Codex Configuration Slides for this repository.
upstream design ./codex-configuration-reference.md source reference for the slide deck
upstream implementation ../.codex/config.toml current shared template Codex config
@dependency-end
-->

# Codex Configuration Slides

このスライドは `documents/codex-configuration-reference.md` の要点から作成した Markdown deck です。

---

# Codex 設定の全体像

Codex の設定は 1 ファイルではなく、複数の runtime surface で構成されます。

- `config.toml`: runtime の機械的設定
- `AGENTS.md`: repo 内の作業規律
- hooks: セッションと tool 実行の決定的処理
- MCP: 外部 tool / repo tool 接続
- skills: 再利用可能な workflow
- subagents: role と model/sandbox の分離

---

# この資料の根拠

- 公式 OpenAI Codex docs
- 公式 `config-schema.json`
- ローカル `codex --help`
- ローカル `codex exec --help`
- ローカル `.codex/config.toml`
- agent-canon の runtime entrypoint

結論: repo に残す設定は「長期運用に必要なもの」だけに絞り、臨時操作は CLI override / profile へ逃がします。

---

# 設定の置き場所

| Surface | Scope | 役割 |
| ------- | ----- | ---- |
| `~/.codex/config.toml` | user | 個人の既定値 |
| `.codex/config.toml` | repo | project runtime policy |
| `-c key=value` | run | 一時 override |
| `.codex/agents/*.toml` | repo/user | custom subagent |
| `.agents/skills` | dir/repo/user | workflow package |
| `AGENTS.md` | repo tree | 作業規律 |
| hooks | repo/user | 起動・tool 実行時の強制処理 |

---

# 覚えるべき分担

- `AGENTS.md`: 何を必ず守るか
- `.codex/config.toml`: runtime をどう動かすか
- `.codex/agents/*.toml`: role ごとの model / sandbox / MCP / skills
- `hooks.json`: deterministic startup と tool gate
- `reports/agents/<run-id>/`: task 固有の証跡

この分担を崩すと、設定が増えるほど agent が読むべき正本を見失います。

---

# Template の現在値

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"

[features]
codex_hooks = true

[agents]
max_threads = 24
job_max_runtime_seconds = 3600

[mcp_servers.repo_mcp_server]
command = "bash"
args = ["mcp/repo_mcp_server.sh"]
enabled = true
required = false
startup_timeout_sec = 20
tool_timeout_sec = 300
```

---

# Template 設定の意味

- 外部 sandbox 前提なので approval は `never`
- filesystem sandbox は `danger-full-access`
- hooks を有効化し、MCP 起動や context 注入を runtime に組み込む
- subagent は最大 24 thread、job timeout 3600 秒
- repo MCP は optional startup にして、失敗時も起動後に検出・報告する

---

# Template に入っていないもの

現在の `.codex/config.toml` に入っている top-level key は 5 つだけです。

- `approval_policy`
- `sandbox_mode`
- `features`
- `agents`
- `mcp_servers`

それ以外の official schema key は「Codex が受け付けるが、この template には未設定」です。

---

# 未設定 top-level の代表カテゴリ

- model / provider / reasoning
- approvals reviewer / permissions / sandbox detail
- project doc discovery / injected context
- inline hooks / tools / skills / apps / plugins
- MCP OAuth / credential stores
- UI / history / logs / notifications
- memory / OTEL / ghost snapshots
- realtime / audio / JS REPL / Windows
- experimental overrides
- profiles / personality

---

# 未設定は不足とは限らない

未設定の理由を分類します。

- user config に置くべきもの: model、provider、profile
- machine-local なもの: TUI、history、audio、notice、Windows onboarding
- secret を含み得るもの: provider auth、headers、OAuth、credential stores
- repo では別 surface のもの: hooks は `hooks.json`、skills は `.agents/skills`
- 危険・不安定なもの: `experimental_*`

---

# Feature flags

この template で有効なのは `codex_hooks` のみです。

schema には他にも多くの flag があります。
例:

- `multi_agent`, `multi_agent_v2`
- `web_search`, `web_search_cached`, `search_tool`
- `image_generation`, `apps`, `plugins`
- `tool_search`, `tool_suggest`
- `memories`, `memory_tool`
- `unified_exec`, `shell_tool`
- `experimental_use_freeform_apply_patch`

---

# Nested で未設定のもの

`[agents]`:

- 未設定: `max_depth`
- 未設定: inline role entries

`[mcp_servers.repo_mcp_server]`:

- 未設定: `url`, `cwd`, `env`, `env_vars`
- 未設定: `enabled_tools`, `disabled_tools`, `tools`
- 未設定: HTTP headers / bearer token / OAuth
- 未設定: `supports_parallel_tool_calls`

---

# CLI override

```bash
codex -c model='"gpt-5.5"'
codex -c model_reasoning_effort='"high"'
codex --enable codex_hooks
codex --disable some_feature
codex --search
codex exec --json "run review"
```

CLI override は一時操作に使います。repo の正本へ残すのは、全員が再現すべき設定だけです。

---

# CLI command map

| Command | 用途 |
| ------- | ---- |
| `codex` | interactive session |
| `codex exec` | non-interactive run |
| `codex review` | non-interactive code review |
| `codex mcp` | MCP server 管理 |
| `codex plugin` | plugin 管理 |
| `codex apply` | latest diff の適用 |
| `codex resume` / `fork` | session 継続・分岐 |
| `codex features` | feature flags 確認 |

---

# 最重要 top-level keys

- `model`
- `model_provider`
- `model_reasoning_effort`
- `model_verbosity`
- `approval_policy`
- `sandbox_mode`
- `profiles`
- `mcp_servers`
- `agents`
- `skills`
- `hooks`
- `tools`
- `web_search`
- `project_doc_*`

---

# Model / Provider

| Key | 使い方 |
| --- | ------ |
| `model` | 通常 turn の model |
| `review_model` | review 専用 model |
| `model_reasoning_effort` | reasoning budget |
| `plan_mode_reasoning_effort` | plan mode 専用 budget |
| `model_verbosity` | GPT-5 output detail |
| `model_provider` | provider key |
| `model_providers` | custom provider map |

---

# GPT-5.5 時代の実務

GPT-5.5 を使える環境では、repo default を一律に重くするより profile / custom agent へ寄せます。

- design / review: `model="gpt-5.5"`, `reasoning_effort="high"`
- bounded implementation: task sizeに応じて medium/high
- trivial run: default profile
- plan mode: `plan_mode_reasoning_effort` を別管理

---

# Approval / Sandbox

| Key | 目的 |
| --- | ---- |
| `approval_policy` | command approval の基本方針 |
| `approvals_reviewer` | approval の宛先 |
| `sandbox_mode` | filesystem / command sandbox |
| `sandbox_workspace_write` | workspace-write の詳細 |
| `permissions` | granular permission profile |
| `default_permissions` | 既定 profile |

---

# Sandbox modes

- `read-only`: review / exploration に向く
- `workspace-write`: repo 編集に向く
- `danger-full-access`: 外部 sandbox がある container / CI に限定

この template は外部環境で安全境界を持つ前提で `danger-full-access` を使います。

---

# Subagents

`[agents]` は capacity 設定です。

| Field | 意味 |
| ----- | ---- |
| `max_threads` | 同時 agent thread 上限 |
| `max_depth` | nested spawn depth |
| `job_max_runtime_seconds` | worker timeout |

品質を決めるのは thread 数ではなく、owner、input packet、write scope、review gate です。

---

# Custom agents

Custom agents は次に置けます。

- `~/.codex/agents/`
- `.codex/agents/`

各 role で上書きできる代表例:

- `model`
- `model_reasoning_effort`
- `sandbox_mode`
- `mcp_servers`
- `skills.config`
- instructions

---

# MCP

MCP は Codex が外部 tool を呼ぶ接続面です。

```toml
[mcp_servers.repo_mcp_server]
command = "bash"
args = ["mcp/repo_mcp_server.sh"]
enabled = true
required = false
startup_timeout_sec = 20
tool_timeout_sec = 300
```

repo-local tool は `required=false` にして、boot 不能より「起動後に失敗を検知して直す」設計にします。

---

# MCP field map

- `command`, `args`, `cwd`
- `url`
- `env`, `env_vars`
- `http_headers`, `env_http_headers`
- `bearer_token_env_var`
- `enabled`, `required`
- `startup_timeout_sec`, `tool_timeout_sec`
- `enabled_tools`, `disabled_tools`, `tools`
- `default_tools_approval_mode`
- `supports_parallel_tool_calls`

---

# Hooks

Hook events:

- `SessionStart`
- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `PermissionRequest`
- `Stop`

Hook には「毎回確実に動いてほしい deterministic 処理」を置きます。

---

# Hooks の使いどころ

- MCP inventory の boot / check
- repo runtime context の注入
- 禁止 tool の事前 block
- tool 結果の監査ログ化
- permission request の追加 review

長時間処理や曖昧な判断は hook に押し込まず、workflow / agent に持たせます。

---

# Skills

Skills は reusable workflow package です。

Codex は `SKILL.md` を発見し、必要な skill を読んで実行します。

重要:

- description は短く明確にする
- frontmatter を壊すと skill が load されない
- workflow は skill、repo policy は `AGENTS.md`
- plugin は配布単位、skill は実行単位

---

# Skills config

```toml
[skills]
include_instructions = true

[skills.bundled]
enabled = true

[[skills.config]]
name = "dependency-analysis"
enabled = true
```

大量 skill 環境では初期 context budget を圧迫するため、命名と説明が重要です。

---

# AGENTS.md discovery

関連 key:

- `project_doc_max_bytes`
- `project_doc_fallback_filenames`
- `project_root_markers`
- `include_environment_context`
- `include_permissions_instructions`
- `include_apps_instructions`

`AGENTS.md` は agent が読む作業規律の正本です。設定値の一覧表を置く場所ではありません。

---

# Profiles

Profiles は operator mode を切り替えるための機構です。

```toml
[profiles.review]
model = "gpt-5.5"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
approval_policy = "never"
```

使い方:

```bash
codex --profile review
```

---

# Tools / Web Search

| Key | 目的 |
| --- | ---- |
| `tools.view_image` | local image inspection |
| `tools.web_search` | web search tool config |
| `web_search` | disabled / cached / live |
| `tool_output_token_limit` | tool output context budget |
| `tool_suggest` | discoverable tool suggestions |

current facts や公式 docs 確認では live search を使い、通常の repo 作業では不要に外部依存させません。

---

# UI / History / Local State

Machine-local に寄せるべきもの:

- `tui.*`
- `history.*`
- `log_dir`
- `sqlite_home`
- `notify`
- `file_opener`
- `notice.*`
- `audio.*`
- `windows_wsl_setup_acknowledged`

これらは原則として shared repo policy ではありません。

---

# Observability

`[otel]`:

- `environment`
- `trace_exporter`
- `metrics_exporter`
- `exporter`
- `log_user_prompt`

prompt / repo data を trace に載せるかは security decision です。既定で広く有効化しない方が安全です。

---

# Sensitive settings

特に注意:

- `experimental_bearer_token`
- literal `http_headers`
- `env_http_headers`
- `shell_environment_policy`
- `mcp_oauth_*`
- provider auth
- `otel.log_user_prompt`
- `sandbox_mode="danger-full-access"`

credential は committed config に直書きしません。

---

# Experimental settings

次は通常運用では避けます。

- `experimental_*`
- realtime websocket override
- thread config/store endpoint
- app-server related settings
- schema description が空の unstable field

必要な場合は task scope と rollback plan を明記します。

---

# 設定変更 checklist

1. 変更 surface を決める
2. 公式 schema で key 名を確認する
3. repo policy と runtime mechanics を分離する
4. canon 変更なら `vendor/agent-canon/` を編集する
5. root view は `sync_agent_canon.sh link-root`
6. dependency header を追加する
7. dependency / docs / static checks を通す

---

# Agent-canon での推奨設計

- `.codex/config.toml`: 小さく保つ
- `AGENTS.md`: workflow gate と closeout policy
- `.codex/agents/*.toml`: role behavior
- `.agents/skills`: reusable workflow
- hooks: deterministic startup
- MCP: repo tool inventory
- `reports/agents`: task evidence

---

# まとめ

Codex 設定は「便利な knobs の集合」ではなく、agent が確実に同じ作業境界で動くための runtime contract です。

最小原則:

- durable policy は repo に残す
- temporary override は CLI / profile
- tool startup は hooks / MCP
- workflow は skills / AGENTS.md
- evidence は run bundle
