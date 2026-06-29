<!--
@dependency-start
contract reference
responsibility Houses the split guide section: 追加設定レシピ114-253.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# 追加設定レシピ114-253

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 8965-11747
- section sha256: `27b612a8da7bd9eb05559225bee2ad8d2e135d37871b8a6a88811eb1be89336b`

<!-- split-content-start -->

# 第VIII部 設定の書き方 追加レシピ集


## 追加レシピ集の使い方

この部では、前の設定レシピ集をさらに細分化し、`config.toml`、`requirements.toml`、`AGENTS.md`、`.codex/agents/*.toml`、`.codex/rules/*.rules`、MCP、Hooks、TUI、CI、debugの書き方を追加する。すべてを採用するのではなく、目的が一致する断片だけを選び、最小構成で検証してから広げる。


---


## 追加レシピ 114 から 133


### 追加設定レシピ 114: 初期化直後のゼロから設定

**目的**  何もない状態から最小の `config.toml` を作る。


```
#:schema https://developers.openai.com/codex/config-schema.json
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
```


**確認**  schema行を入れ、エディタ補完と `/debug-config` で読めることを確認する。

**戻し方**  このファイルを退避し、Codexを再起動する。


### 追加設定レシピ 115: profileを既定化する

**目的**  日常profileを明示的な既定にする。


```
profile = "daily"

[profiles.daily]
model = "gpt-5.5"
sandbox_mode = "workspace-write"
approval_policy = "on-request"
web_search = "cached"
```


**確認**  `codex` だけでdailyが読まれるか確認する。

**戻し方**  `profile` 行を削除し、起動時に `--profile` を使う運用へ戻す。


---


### 追加設定レシピ 116: レビュー専用profile

**目的**  PRレビューや差分確認で書き込みを止める。


```
[profiles.review]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "disabled"
model_reasoning_effort = "high"
```


**確認**  `codex --profile review` で `/review` や `/diff` を使う。

**戻し方**  profile全体を削除するか、`web_search` だけcachedへ戻す。


### 追加設定レシピ 117: 軽量lint確認profile

**目的**  限定されたlintやtypoの確認を低コストで行い、修正自体は通常の責務・検証手順に戻す。


```toml
[profiles.focused_lint_check]
service_tier = "fast"
model_reasoning_effort = "low"
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  検証用branchでlint確認を試し、出力品質と速度を比較する。

**戻し方**  `service_tier` と `model_reasoning_effort` を削除する。


---


### 追加設定レシピ 118: 深掘り設計profile

**目的**  大きな設計相談や移行計画だけ推論を強める。


```
[profiles.architect]
model_reasoning_effort = "high"
plan_mode_reasoning_effort = "high"
sandbox_mode = "read-only"
web_search = "cached"
```


**確認**  `codex --profile architect /plan ...` のように使う。

**戻し方**  日常profileから使わず、必要時だけ明示する。


### 追加設定レシピ 119: no external context profile

**目的**  外部検索やMCPを使わずrepoだけ見る。


```
[profiles.repo_only]
web_search = "disabled"
sandbox_mode = "read-only"
approval_policy = "on-request"

[profiles.repo_only.features]
apps = false
connectors = false
```


**確認**  `/debug-config` で外部contextが無効か確認する。

**戻し方**  外部仕様確認が必要ならresearch profileへ切り替える。


---


### 追加設定レシピ 120: image review profile

**目的**  スクリーンショットからUI不具合を読む。


```
[profiles.image_review]
tools_view_image = true
sandbox_mode = "read-only"
model_reasoning_effort = "medium"
```


**確認**  `codex --profile image_review -i error.png "原因を調べて"` で確認する。

**戻し方**  画像を使わない作業では通常profileへ戻す。


### 追加設定レシピ 121: memory disabled profile

**目的**  外部文脈や記憶を避けたい調査で使う。


```
[profiles.cleanroom]
web_search = "disabled"
history = { persistence = "none" }

[profiles.cleanroom.features]
memories = false
```


**確認**  履歴やmemory関連の挙動を `/debug-config` で確認する。

**戻し方**  cleanroom profileを使うのをやめ、履歴保存profileへ戻す。


---


### 追加設定レシピ 122: model catalog確認profile

**目的**  モデルcatalogを別ファイルで検証する。


```
[profiles.catalog_lab]
model_catalog_json = "/Users/me/.codex/model-catalogs/lab.json"
model = "gpt-5.5"
```


**確認**  起動時にcatalogが読まれ、model選択に反映されるか確認する。

**戻し方**  profileから `model_catalog_json` を削除する。


### 追加設定レシピ 123: review modelを分ける

**目的**  通常作業とレビューでmodelを分ける。


```
model = "gpt-5.5"
review_model = "gpt-5.5"
model_reasoning_effort = "medium"
```


**確認**  `/review` を実行し、review用設定が有効か確認する。

**戻し方**  review_model行を削除し、session modelへ戻す。


---


### 追加設定レシピ 124: OSS検証を明示する

**目的**  OSS provider検証を通常profileから分離する。


```
[profiles.ollama_lab]
oss_provider = "ollama"
model = "local-model-name"
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  `codex --profile ollama_lab --oss` で利用する。

**戻し方**  OpenAI providerのprofileへ戻す。


### 追加設定レシピ 125: API key利用profile

**目的**  ChatGPT loginではなくAPIキー運用を試す。


```
[profiles.api_key]
model_provider = "openai"
model = "gpt-5.5"
cli_auth_credentials_store = "keyring"
```


**確認**  login methodやcredential storeを確認する。

**戻し方**  `codex logout` し、通常のloginへ戻す。


---


### 追加設定レシピ 126: ephemeral profile

**目的**  共有端末でcredentialを残さない。


```
[profiles.shared_terminal]
cli_auth_credentials_store = "ephemeral"
history = { persistence = "none" }
web_search = "disabled"
```


**確認**  終了後にcredentialやhistoryが残らないか確認する。

**戻し方**  個人端末では通常profileへ戻す。


### 追加設定レシピ 127: verbose出力を調整する

**目的**  出力の詳しさをprofileで変える。


```
[profiles.concise]
model_verbosity = "low"

[profiles.verbose]
model_verbosity = "high"
```


**確認**  同じ質問を両profileで実行し、説明量を比較する。

**戻し方**  使わないprofileを削除する。


---


### 追加設定レシピ 128: reasoning summaryを調整する

**目的**  推論要約の表示方針を検証する。


```
[profiles.summary_lab]
model_reasoning_summary = "auto"
model_reasoning_effort = "medium"
```


**確認**  手元のmodelとCLIが対応しているか確認する。

**戻し方**  非対応なら設定を削除する。


### 追加設定レシピ 129: history size limit

**目的**  履歴肥大化を避ける。


```
[history]
persistence = "save-all"
max_bytes = 104857600
```


**確認**  履歴fileのサイズ上限が反映されるか確認する。

**戻し方**  max_bytesを削除し既定へ戻す。


---


### 追加設定レシピ 130: feedbackを無効にする

**目的**  feedback flowを使わないprofileを作る。


```
[profiles.quiet]
feedback = { enabled = false }
analytics = { enabled = false }
```


**確認**  `/debug-config` で設定が反映されるか確認する。

**戻し方**  profileを削除する。


### 追加設定レシピ 131: manual compact設定の入口

**目的**  長いsessionのcontext管理を意識する。


```
model_auto_compact_token_limit = 64000
tool_output_token_limit = 12000
```


**確認**  長いtool出力でcontextが膨らみすぎないか確認する。

**戻し方**  model既定に戻すなら両行を削除する。


---


### 追加設定レシピ 132: background terminal timeout

**目的**  長いpollを避ける。


```
background_terminal_max_timeout = 300000
```


**確認**  background terminal利用時の待ち時間を観察する。

**戻し方**  既定へ戻すなら行を削除する。


### 追加設定レシピ 133: zsh pathを明示する

**目的**  特定のzsh実行環境を使う。


```
zsh_path = "/bin/zsh"
```


**確認**  shell実行が想定zshで動くか確認する。

**戻し方**  pathが合わない環境では行を削除する。


---


---


## 追加レシピ 134 から 153


### 追加設定レシピ 134: repo内の基本ディレクトリ

**目的**  Codex関連fileをrepo内で整理する。


```
repo/
  AGENTS.md
  .codex/
    config.toml
    agents/
    hooks/
    rules/
    mcp/
    skills/
```


**確認**  新規repoでこの構成を作り、trusted projectとして読み込む。

**戻し方**  不要なdirectoryは削除し、空のまま放置しない。


### 追加設定レシピ 135: service別AGENTS

**目的**  monorepoで近い指示を優先する。


```
repo/AGENTS.md
repo/services/api/AGENTS.md
repo/apps/web/AGENTS.md
repo/packages/ui/AGENTS.md
```


**確認**  各subdirでCodexを起動し、近いAGENTSが読まれるか確認する。

**戻し方**  重複する規約はroot AGENTSへ戻す。


---


### 追加設定レシピ 136: project doc容量調整

**目的**  AGENTSやalternate route文書を読みすぎない。


```
project_doc_max_bytes = 150000
project_doc_alternate route_filenames = ["AI_GUIDE.md", "CODING_RULES.md"]
```


**確認**  巨大文書でcontextが圧迫されないか確認する。

**戻し方**  文書を分割し、不要なalternate routeを外す。


### 追加設定レシピ 137: root markerを言語別にする

**目的**  polyglot repoのroot検出を安定させる。


```
project_root_markers = [".git", "go.work", "Cargo.toml", "pnpm-workspace.yaml"]
```


**確認**  想定rootが変わらないか `/debug-config` で見る。

**戻し方**  誤検出するmarkerを削除する。


---


### 追加設定レシピ 138: project固有MCPのみ有効

**目的**  repo外ではMCPを出さない。


```
# .codex/config.toml
[mcp_servers.repo_docs]
command = "python3"
args = [".codex/mcp/repo_docs.py"]
enabled_tools = ["search", "fetch"]
```


**確認**  他repoでこのMCPが出ないことを確認する。

**戻し方**  必要なくなったらtableを削除する。


### 追加設定レシピ 139: project hook script配置

**目的**  hook scriptをrepo内で管理する。


```
.codex/hooks/pre_tool_use.py
.codex/hooks/post_tool_use.py
.codex/hooks/session_start.py
```


**確認**  scriptに実行権限や依存があるか確認する。

**戻し方**  hook設定を無効化し、scriptを削除する。


---


### 追加設定レシピ 140: project skill配置

**目的**  repo専用作業手順をskill化する。


```
.codex/skills/api-migration/SKILL.md
.codex/skills/ui-audit/SKILL.md
.codex/skills/release-note/SKILL.md
```


**確認**  Codexがskillを発見できるか確認する。

**戻し方**  使われないskillはenabled=falseまたは削除する。


### 追加設定レシピ 141: generated files方針

**目的**  生成物を誤編集させない。


```
# AGENTS.md
## Generated files
- Do not edit generated/* directly.
- Regenerate using pnpm generate.
- Review generated diffs before committing.
```


**確認**  生成物に修正依頼したとき、再生成方針を守るか見る。

**戻し方**  方針変更時はAGENTSとscriptsを同時に更新する。


---


### 追加設定レシピ 142: test commandを明文化

**目的**  Codexに正しい検証commandを教える。


```
# AGENTS.md
## Test commands
- API: pnpm test --filter=@svc/api
- Web: pnpm test --filter=@app/web
- All: pnpm turbo run test
```


**確認**  Codexが古いcommandを使わないか確認する。

**戻し方**  package変更時にAGENTSも更新する。


### 追加設定レシピ 143: branch policyをAGENTSへ書く

**目的**  commitやpushの方針を明確にする。


```
# AGENTS.md
## Git policy
- Do not commit unless the user explicitly asks.
- Never push to remote.
- Always show git diff before final summary.
```


**確認**  タスク終了時のsummaryでdiff確認が出るか見る。

**戻し方**  チーム運用変更に合わせて更新する。


---


### 追加設定レシピ 144: migration branch専用override

**目的**  一時的な移行規約をbranchに置く。


```
# AGENTS.override.md
Migration branch only:
- Use new-auth package.
- Do not call legacy-auth helpers.
- Update tests in tests/auth-v2.
```


**確認**  branch終了時にoverrideを削除する予定をissueに残す。

**戻し方**  merge前にoverrideが不要なら削除する。


### 追加設定レシピ 145: local env fileを読ませない

**目的**  repoのenv fileを保護する。


```
# AGENTS.md
## Secrets
- Do not open .env or .env.local.
- Ask the user for non-secret config values if needed.
```


**確認**  Codexがenv内容を求めた時に拒否するか確認する。

**戻し方**  必要な値はexample fileへ移す。


---


### 追加設定レシピ 146: project settings README

**目的**  設定の意図をdocument化する。


```
# .codex/README.md
- config.toml: project-scoped Codex settings.
- agents/: custom subagents.
- hooks/: local policy scripts.
- rules/: command execution policy.
- mcp/: repo-local MCP servers.
```


**確認**  新メンバーが設定を理解できるか確認する。

**戻し方**  構成変更時にREADMEを更新する。


### 追加設定レシピ 147: service別agent map

**目的**  serviceとagentの対応を明確にする。


```
# AGENTS.md
## Agent map
- API tasks: use api-reviewer or migration-worker.
- Web UI tasks: use ui-debugger then web-worker.
- Docs tasks: use docs-researcher.
```


**確認**  親agentが適切にsubagentを使えるか確認する。

**戻し方**  agent追加や削除時にmapを更新する。


---


### 追加設定レシピ 148: artifact出力先

**目的**  PDFやレポートの出力場所を固定する。


```
# AGENTS.md
## Artifacts
- Put generated reports under artifacts/codex/.
- Do not commit artifacts unless requested.
- Include source file and command in final summary.
```


**確認**  成果物がrepo rootに散らからないか確認する。

**戻し方**  不要なartifactはcleanupする。


### 追加設定レシピ 149: network falseを明記

**目的**  依存しない作業ではnetworkを閉じる。


```
sandbox_mode = "workspace-write"
[sandbox_workspace_write]
network_access = false
```


**確認**  downloadや外部APIが失敗することを確認する。

**戻し方**  必要時だけprofileでtrueにする。


---


### 追加設定レシピ 150: dependency install profile

**目的**  依存追加が必要な時だけnetworkを開く。


```
[profiles.deps]
sandbox_mode = "workspace-write"
approval_policy = "on-request"
[profiles.deps.sandbox_workspace_write]
network_access = true
```


**確認**  install前に承認が出る運用にする。

**戻し方**  作業後は通常profileへ戻す。


### 追加設定レシピ 151: read-only plus live docs

**目的**  仕様確認だけlive検索を許す。


```
[profiles.spec_check]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "live"
```


**確認**  コード編集が起きないことを確認する。

**戻し方**  実装作業ではworkspace-write profileへ切り替える。


---


### 追加設定レシピ 152: strict local review

**目的**  外部contextなしで差分だけreviewする。


```
[profiles.strict_review]
sandbox_mode = "read-only"
approval_policy = "untrusted"
web_search = "disabled"
```


**確認**  review結果がrepo証拠に基づくか見る。

**戻し方**  外部仕様が必要ならdocs-researcherへ依頼する。


### 追加設定レシピ 153: prompt on deploy

**目的**  deploy系commandを承認制にする。


```
prefix_rule(pattern=["npm", "run", "deploy"], decision="prompt", reason="Deployment requires explicit approval.")
prefix_rule(pattern=["pnpm", "deploy"], decision="prompt", reason="Deployment requires explicit approval.")
```


**確認**  `codex execpolicy check` で判定する。

**戻し方**  deploy不要の作業ではcommandを実行させない。


---


---


## 追加レシピ 154 から 173


### 追加設定レシピ 154: forbid prod env

**目的**  production env指定を防ぐ。


```
prefix_rule(pattern=["--env", "production"], decision="forbidden", reason="Production environment is not allowed from Codex.")
prefix_rule(pattern=["NODE_ENV=production"], decision="prompt", reason="Production mode needs review.")
```


**確認**  実際のshell tokenizationに合わせて調整する。

**戻し方**  必要なら人間が別手順で実行する。


### 追加設定レシピ 155: container command guard

**目的**  Docker操作をpromptにする。


```
prefix_rule(pattern=["docker", "run"], decision="prompt", reason="Container execution may mount files or use network.")
prefix_rule(pattern=["docker", "compose", "up"], decision="prompt", reason="Compose may start multiple services.")
```


**確認**  dockerを使うrepoではAGENTSに安全なcompose fileを明記する。

**戻し方**  不要ならdocker系をforbiddenにする。


---


### 追加設定レシピ 156: ssh禁止

**目的**  remote hostへの接続を避ける。


```
prefix_rule(pattern=["ssh"], decision="forbidden", reason="Do not SSH from Codex sessions.")
prefix_rule(pattern=["scp"], decision="forbidden", reason="Do not copy files to remote hosts from Codex.")
```


**確認**  MCPやlogsで代替できるか検討する。

**戻し方**  remote作業は人間が実行する。


### 追加設定レシピ 157: credential commands prompt

**目的**  secret取得commandを止める。


```
prefix_rule(pattern=["aws", "secretsmanager"], decision="prompt", reason="Secret access requires human review.")
prefix_rule(pattern=["op", "item"], decision="prompt", reason="Password manager access requires review.")
```


**確認**  secret値がtranscriptへ出ないようにする。

**戻し方**  secretが不要な設計へ変更する。


---


### 追加設定レシピ 158: shell env inherit none

**目的**  完全に近い隔離shellを試す。


```
[shell_environment_policy]
inherit = "none"
set = { "PATH" = "/bin:/usr/bin:/usr/local/bin" }
```


**確認**  必要なtoolが起動するか確認する。

**戻し方**  toolが壊れる場合はinheritをcoreへ戻す。


### 追加設定レシピ 159: shell include only

**目的**  必要な環境変数だけ渡す。


```
[shell_environment_policy]
inherit = "all"
include_only = ["PATH", "HOME", "LANG", "LC_ALL", "CI"]
```


**確認**  command実行で必要な環境が足りるか確認する。

**戻し方**  include_onlyを空に戻す。


---


### 追加設定レシピ 160: default excludesを維持

**目的**  KEYやTOKENを含む変数を渡さない。


```
[shell_environment_policy]
ignore_default_excludes = false
exclude = ["AWS_*", "GITHUB_*", "*_TOKEN", "*_SECRET"]
```


**確認**  env出力でsecret系が消えているか見る。

**戻し方**  必要な非secretだけ個別にsetする。


### 追加設定レシピ 161: writable rootsのreview

**目的**  追加rootを必要最小にする。


```
[sandbox_workspace_write]
writable_roots = ["/Users/me/work/shared-fixtures"]
network_access = false
```


**確認**  対象dir以外へ書けないか確認する。

**戻し方**  作業完了後にwritable_rootsから削除する。


---


### 追加設定レシピ 162: temporary full access with note

**目的**  やむを得ない強権限にメモを残す。


```
[profiles.full_access_lab]
# Use only inside disposable containers.
sandbox_mode = "danger-full-access"
approval_policy = "never"
web_search = "disabled"
```


**確認**  containerやVM内でのみ利用する。

**戻し方**  profileを削除する。


### 追加設定レシピ 163: approval reviewer user固定

**目的**  承認は人間に返す。


```
approvals_reviewer = "user"
approval_policy = "on-request"
```


**確認**  承認がautoに回らないことを確認する。

**戻し方**  auto_review検証profileと分ける。


---


### 追加設定レシピ 164: MCP docs_readonly server

**目的**  docs_readonly 用MCPをread-only toolに限定する。


```
[mcp_servers.docs_readonly]
url = "https://mcp.example.internal/docs_readonly/mcp"
bearer_token_env_var = "DOCS_READONLY_MCP_TOKEN"
enabled_tools = ["search_docs"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get docs_readonly` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 165: MCP runbooks server

**目的**  runbooks 用MCPをread-only toolに限定する。


```
[mcp_servers.runbooks]
url = "https://mcp.example.internal/runbooks/mcp"
bearer_token_env_var = "RUNBOOKS_MCP_TOKEN"
enabled_tools = ["get_runbook"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get runbooks` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 166: MCP ci_logs server

**目的**  ci_logs 用MCPをread-only toolに限定する。


```
[mcp_servers.ci_logs]
url = "https://mcp.example.internal/ci_logs/mcp"
bearer_token_env_var = "CI_LOGS_MCP_TOKEN"
enabled_tools = ["search_ci_logs"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get ci_logs` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 167: MCP design_tokens server

**目的**  design_tokens 用MCPをread-only toolに限定する。


```
[mcp_servers.design_tokens]
url = "https://mcp.example.internal/design_tokens/mcp"
bearer_token_env_var = "DESIGN_TOKENS_MCP_TOKEN"
enabled_tools = ["get_token"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get design_tokens` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 168: MCP component_catalog server

**目的**  component_catalog 用MCPをread-only toolに限定する。


```
[mcp_servers.component_catalog]
url = "https://mcp.example.internal/component_catalog/mcp"
bearer_token_env_var = "COMPONENT_CATALOG_MCP_TOKEN"
enabled_tools = ["search_component"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get component_catalog` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 169: MCP api_specs server

**目的**  api_specs 用MCPをread-only toolに限定する。


```
[mcp_servers.api_specs]
url = "https://mcp.example.internal/api_specs/mcp"
bearer_token_env_var = "API_SPECS_MCP_TOKEN"
enabled_tools = ["get_openapi"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get api_specs` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 170: MCP release_notes server

**目的**  release_notes 用MCPをread-only toolに限定する。


```
[mcp_servers.release_notes]
url = "https://mcp.example.internal/release_notes/mcp"
bearer_token_env_var = "RELEASE_NOTES_MCP_TOKEN"
enabled_tools = ["search_release_notes"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get release_notes` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 171: MCP dependency_docs server

**目的**  dependency_docs 用MCPをread-only toolに限定する。


```
[mcp_servers.dependency_docs]
url = "https://mcp.example.internal/dependency_docs/mcp"
bearer_token_env_var = "DEPENDENCY_DOCS_MCP_TOKEN"
enabled_tools = ["search_package_docs"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get dependency_docs` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 172: MCP error_catalog server

**目的**  error_catalog 用MCPをread-only toolに限定する。


```
[mcp_servers.error_catalog]
url = "https://mcp.example.internal/error_catalog/mcp"
bearer_token_env_var = "ERROR_CATALOG_MCP_TOKEN"
enabled_tools = ["lookup_error"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get error_catalog` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 173: MCP feature_flags server

**目的**  feature_flags 用MCPをread-only toolに限定する。


```
[mcp_servers.feature_flags]
url = "https://mcp.example.internal/feature_flags/mcp"
bearer_token_env_var = "FEATURE_FLAGS_MCP_TOKEN"
enabled_tools = ["get_flag"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get feature_flags` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


---


## 追加レシピ 174 から 193


### 追加設定レシピ 174: MCP observability_traces server

**目的**  observability_traces 用MCPをread-only toolに限定する。


```
[mcp_servers.observability_traces]
url = "https://mcp.example.internal/observability_traces/mcp"
bearer_token_env_var = "OBSERVABILITY_TRACES_MCP_TOKEN"
enabled_tools = ["get_trace"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get observability_traces` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 175: MCP metrics server

**目的**  metrics 用MCPをread-only toolに限定する。


```
[mcp_servers.metrics]
url = "https://mcp.example.internal/metrics/mcp"
bearer_token_env_var = "METRICS_MCP_TOKEN"
enabled_tools = ["query_metrics"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get metrics` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 176: MCP incident_notes server

**目的**  incident_notes 用MCPをread-only toolに限定する。


```
[mcp_servers.incident_notes]
url = "https://mcp.example.internal/incident_notes/mcp"
bearer_token_env_var = "INCIDENT_NOTES_MCP_TOKEN"
enabled_tools = ["search_incidents"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get incident_notes` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 177: MCP code_index server

**目的**  code_index 用MCPをread-only toolに限定する。


```
[mcp_servers.code_index]
url = "https://mcp.example.internal/code_index/mcp"
bearer_token_env_var = "CODE_INDEX_MCP_TOKEN"
enabled_tools = ["search_symbol"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get code_index` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 178: MCP architecture server

**目的**  architecture 用MCPをread-only toolに限定する。


```
[mcp_servers.architecture]
url = "https://mcp.example.internal/architecture/mcp"
bearer_token_env_var = "ARCHITECTURE_MCP_TOKEN"
enabled_tools = ["get_diagram"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get architecture` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 179: MCP test_coverage server

**目的**  test_coverage 用MCPをread-only toolに限定する。


```
[mcp_servers.test_coverage]
url = "https://mcp.example.internal/test_coverage/mcp"
bearer_token_env_var = "TEST_COVERAGE_MCP_TOKEN"
enabled_tools = ["get_coverage"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get test_coverage` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 180: MCP browser_logs server

**目的**  browser_logs 用MCPをread-only toolに限定する。


```
[mcp_servers.browser_logs]
url = "https://mcp.example.internal/browser_logs/mcp"
bearer_token_env_var = "BROWSER_LOGS_MCP_TOKEN"
enabled_tools = ["get_console_log"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get browser_logs` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 181: MCP design_files server

**目的**  design_files 用MCPをread-only toolに限定する。


```
[mcp_servers.design_files]
url = "https://mcp.example.internal/design_files/mcp"
bearer_token_env_var = "DESIGN_FILES_MCP_TOKEN"
enabled_tools = ["get_design_frame"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get design_files` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 182: MCP policy_docs server

**目的**  policy_docs 用MCPをread-only toolに限定する。


```
[mcp_servers.policy_docs]
url = "https://mcp.example.internal/policy_docs/mcp"
bearer_token_env_var = "POLICY_DOCS_MCP_TOKEN"
enabled_tools = ["search_policy"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get policy_docs` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


### 追加設定レシピ 183: MCP team_directory server

**目的**  team_directory 用MCPをread-only toolに限定する。


```
[mcp_servers.team_directory]
url = "https://mcp.example.internal/team_directory/mcp"
bearer_token_env_var = "TEAM_DIRECTORY_MCP_TOKEN"
enabled_tools = ["lookup_owner"]
startup_timeout_sec = 10
tool_timeout_sec = 45
```


**確認**  `codex mcp get team_directory` と `/mcp` でtool一覧を確認する。

**戻し方**  不要になったら `enabled = false` にする。


---


### 追加設定レシピ 184: PreToolUse hook詳細

**目的**  PreToolUse eventで Bash command を確認する。


```
[hooks]
[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/check_bash.py"
timeout = 15
statusMessage = "Checking Bash command"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


### 追加設定レシピ 185: PostToolUse hook詳細

**目的**  PostToolUse eventで Bash result を確認する。


```
[hooks]
[[hooks.PostToolUse]]
matcher = "^Bash$"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/summarize_bash.py"
timeout = 15
statusMessage = "Checking Bash result"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


---


### 追加設定レシピ 186: SessionStart hook詳細

**目的**  SessionStart eventで workspace branch を確認する。


```
[hooks]
[[hooks.SessionStart]]
matcher = ".*"
[[hooks.SessionStart.hooks]]
type = "command"
command = "python3 .codex/hooks/check_branch.py"
timeout = 15
statusMessage = "Checking workspace branch"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


### 追加設定レシピ 187: UserPromptSubmit hook詳細

**目的**  UserPromptSubmit eventで prompt policy を確認する。


```
[hooks]
[[hooks.UserPromptSubmit]]
matcher = ".*"
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "python3 .codex/hooks/check_prompt.py"
timeout = 15
statusMessage = "Checking prompt policy"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


---


### 追加設定レシピ 188: PermissionRequest hook詳細

**目的**  PermissionRequest eventで permission request を確認する。


```
[hooks]
[[hooks.PermissionRequest]]
matcher = ".*"
[[hooks.PermissionRequest.hooks]]
type = "command"
command = "python3 .codex/hooks/permission_guard.py"
timeout = 15
statusMessage = "Checking permission request"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


### 追加設定レシピ 189: Stop hook詳細

**目的**  Stop eventで cleanup を確認する。


```
[hooks]
[[hooks.Stop]]
matcher = ".*"
[[hooks.Stop.hooks]]
type = "command"
command = "python3 .codex/hooks/cleanup.py"
timeout = 15
statusMessage = "Checking cleanup"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


---


### 追加設定レシピ 190: PreCompact hook詳細

**目的**  PreCompact eventで compact preparation を確認する。


```
[hooks]
[[hooks.PreCompact]]
matcher = ".*"
[[hooks.PreCompact.hooks]]
type = "command"
command = "python3 .codex/hooks/pre_compact.py"
timeout = 15
statusMessage = "Checking compact preparation"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


### 追加設定レシピ 191: PostCompact hook詳細

**目的**  PostCompact eventで compact result を確認する。


```
[hooks]
[[hooks.PostCompact]]
matcher = ".*"
[[hooks.PostCompact.hooks]]
type = "command"
command = "python3 .codex/hooks/post_compact.py"
timeout = 15
statusMessage = "Checking compact result"
```


**確認**  低リスクsessionでeventが発火するか確認する。

**戻し方**  障害時は該当matcher groupを削除する。


---


### 追加設定レシピ 192: Rules for terraform plan

**目的**  `terraform plan` を prompt として扱う。


```
prefix_rule(pattern=["terraform", "plan"], decision="prompt", reason="Infrastructure plan requires review.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


### 追加設定レシピ 193: Rules for gh pr merge

**目的**  `gh pr merge` を prompt として扱う。


```
prefix_rule(pattern=["gh", "pr", "merge"], decision="prompt", reason="PR merge must be human approved.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


---


---


## 追加レシピ 194 から 213


### 追加設定レシピ 194: Rules for npm publish

**目的**  `npm publish` を forbidden として扱う。


```
prefix_rule(pattern=["npm", "publish"], decision="forbidden", reason="Package publishing is forbidden.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


### 追加設定レシピ 195: Rules for pnpm publish

**目的**  `pnpm publish` を forbidden として扱う。


```
prefix_rule(pattern=["pnpm", "publish"], decision="forbidden", reason="Package publishing is forbidden.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


---


### 追加設定レシピ 196: Rules for python -m pip install

**目的**  `python -m pip install` を prompt として扱う。


```
prefix_rule(pattern=["python", "-m", "pip", "install"], decision="prompt", reason="Package install requires review.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


### 追加設定レシピ 197: Rules for git reset --hard

**目的**  `git reset --hard` を prompt として扱う。


```
prefix_rule(pattern=["git", "reset", "--hard"], decision="prompt", reason="Destructive git reset requires review.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


---


### 追加設定レシピ 198: Rules for git push --force

**目的**  `git push --force` を forbidden として扱う。


```
prefix_rule(pattern=["git", "push", "--force"], decision="forbidden", reason="Force push is forbidden.")
```


**確認**  `codex execpolicy check` で判定を見る。

**戻し方**  必要になったらpromptへ弱めるのではなく、別の手順を用意する。


### 追加設定レシピ 199: Custom agent api-reviewer

**目的**  Review API changes and contract compatibility. sandboxは `read-only` にする。


```
name = "api-reviewer"
description = "Review API changes and contract compatibility."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/api-reviewer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 200: Custom agent web-worker

**目的**  Implement scoped frontend changes. sandboxは `workspace-write` にする。


```
name = "web-worker"
description = "Implement scoped frontend changes."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  `.codex/agents/web-worker.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 201: Custom agent test-writer

**目的**  Add missing tests for assigned files. sandboxは `workspace-write` にする。


```
name = "test-writer"
description = "Add missing tests for assigned files."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  `.codex/agents/test-writer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 202: Custom agent release-note-writer

**目的**  Draft release notes from diffs. sandboxは `read-only` にする。


```
name = "release-note-writer"
description = "Draft release notes from diffs."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/release-note-writer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 203: Custom agent dependency-auditor

**目的**  Inspect dependency changes and lockfile risk. sandboxは `read-only` にする。


```
name = "dependency-auditor"
description = "Inspect dependency changes and lockfile risk."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/dependency-auditor.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 204: Custom agent migration-planner

**目的**  Plan large migrations and split tasks. sandboxは `read-only` にする。


```
name = "migration-planner"
description = "Plan large migrations and split tasks."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/migration-planner.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 205: Custom agent migration-slice-worker

**目的**  Perform one migration slice. sandboxは `workspace-write` にする。


```
name = "migration-slice-worker"
description = "Perform one migration slice."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  `.codex/agents/migration-slice-worker.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 206: Custom agent docs-updater

**目的**  Update docs after verified code changes. sandboxは `workspace-write` にする。


```
name = "docs-updater"
description = "Update docs after verified code changes."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  `.codex/agents/docs-updater.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 207: Custom agent log-analyst

**目的**  Analyze logs and return likely causes. sandboxは `read-only` にする。


```
name = "log-analyst"
description = "Analyze logs and return likely causes."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/log-analyst.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 208: Custom agent security-reviewer

**目的**  Review for security and secret risks. sandboxは `read-only` にする。


```
name = "security-reviewer"
description = "Review for security and secret risks."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/security-reviewer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 209: Custom agent accessibility-reviewer

**目的**  Review UI accessibility issues. sandboxは `read-only` にする。


```
name = "accessibility-reviewer"
description = "Review UI accessibility issues."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/accessibility-reviewer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 210: Custom agent perf-reviewer

**目的**  Review performance regressions. sandboxは `read-only` にする。


```
name = "perf-reviewer"
description = "Review performance regressions."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/perf-reviewer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 211: Custom agent db-migration-reviewer

**目的**  Review schema migration risk. sandboxは `read-only` にする。


```
name = "db-migration-reviewer"
description = "Review schema migration risk."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/db-migration-reviewer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


### 追加設定レシピ 212: Custom agent build-fixer

**目的**  Fix build failures with minimal changes. sandboxは `workspace-write` にする。


```
name = "build-fixer"
description = "Fix build failures with minimal changes."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  `.codex/agents/build-fixer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


### 追加設定レシピ 213: Custom agent triage-explorer

**目的**  Map issue scope without editing files. sandboxは `read-only` にする。


```
name = "triage-explorer"
description = "Map issue scope without editing files."
developer_instructions = "Stay within the assigned scope. Return evidence, changed files if any, tests, and unknowns."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認**  `.codex/agents/triage-explorer.toml` として保存し、明示的にspawnを依頼する。

**戻し方**  agent fileを削除するか、parent configから参照を外す。


---


---


## 追加レシピ 214 から 233


### 追加設定レシピ 214: Feature unified_exec

**目的**  PTY-backed execを使う。


```
[features]
unified_exec = true
```


**確認**  `codex features list` で `unified_exec` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 215: Feature shell_tool

**目的**  shell toolを有効化する。


```
[features]
shell_tool = true
```


**確認**  `codex features list` で `shell_tool` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 216: Feature shell_snapshot

**目的**  shell snapshotで反復実行を速くする。


```
[features]
shell_snapshot = true
```


**確認**  `codex features list` で `shell_snapshot` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 217: Feature fast_mode

**目的**  fast service tier選択を許可する。


```
[features]
fast_mode = true
```


**確認**  `codex features list` で `fast_mode` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 218: Feature multi_agent

**目的**  subagent collaborationを使う。


```
[features]
multi_agent = true
```


**確認**  `codex features list` で `multi_agent` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 219: Feature hooks

**目的**  hooksを有効化する。


```
[features]
hooks = true
```


**確認**  `codex features list` で `hooks` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 220: Feature goals

**目的**  実験的goalを使う。


```
[features]
goals = true
```


**確認**  `codex features list` で `goals` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 221: Feature undo

**目的**  undo snapshotを使う。


```
[features]
undo = true
```


**確認**  `codex features list` で `undo` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 222: Feature apps

**目的**  Appsを無効化する。


```
[features]
apps = false
```


**確認**  `codex features list` で `apps` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 223: Feature connectors

**目的**  connectorsを無効化する。


```
[features]
connectors = false
```


**確認**  `codex features list` で `connectors` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 224: Feature memories

**目的**  memoriesを無効化する。


```
[features]
memories = false
```


**確認**  `codex features list` で `memories` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 225: Feature image_generation

**目的**  画像生成を無効化する。


```
[features]
image_generation = false
```


**確認**  `codex features list` で `image_generation` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 226: Feature browser_use

**目的**  Browser Useを無効化する。


```
[features]
browser_use = false
```


**確認**  `codex features list` で `browser_use` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 227: Feature computer_use

**目的**  Computer Useを無効化する。


```
[features]
computer_use = false
```


**確認**  `codex features list` で `computer_use` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


---


### 追加設定レシピ 228: Feature prevent_idle_sleep

**目的**  idle sleep抑止を使わない。


```
[features]
prevent_idle_sleep = false
```


**確認**  `codex features list` で `prevent_idle_sleep` の状態を確認する。

**戻し方**  feature行を削除し既定へ戻す。


### 追加設定レシピ 229: Requirements sandbox許可値

**目的**  管理設定で sandbox許可値 を固定する。


```
allowed_sandbox_modes = ["read-only", "workspace-write"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 230: Requirements approval許可値

**目的**  管理設定で approval許可値 を固定する。


```
allowed_approval_policies = ["untrusted", "on-request"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 231: Requirements web search許可値

**目的**  管理設定で web search許可値 を固定する。


```
allowed_web_search_modes = ["disabled", "cached"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 232: Requirements reviewer許可値

**目的**  管理設定で reviewer許可値 を固定する。


```
allowed_approvals_reviewers = ["user", "auto_review"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 233: Requirements browser無効化

**目的**  管理設定で browser無効化 を固定する。


```
[features]
browser_use = false
computer_use = false
in_app_browser = false
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


---


## 追加レシピ 234 から 253


### 追加設定レシピ 234: Requirements apps無効化

**目的**  管理設定で apps無効化 を固定する。


```
[features]
apps = false
connectors = false
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 235: Requirements managed hook directory

**目的**  管理設定で managed hook directory を固定する。


```
[hooks]
managed_dir = "/enterprise/hooks"
windows_managed_dir = 'C:'
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 236: Requirements deny read secrets

**目的**  管理設定で deny read secrets を固定する。


```
deny_read = ["**/.env", "**/.env.*", "**/secrets/**"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 237: Requirements guardian policy

**目的**  管理設定で guardian policy を固定する。


```
guardian_policy_config = "Deny production deploy, secret access, and infrastructure mutation without human approval."
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 238: Requirements MCP identity docs

**目的**  管理設定で MCP identity docs を固定する。


```
[mcp_servers.docs.identity]
url = "https://mcp.example.internal/docs/mcp"
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 239: Requirements MCP identity stdio

**目的**  管理設定で MCP identity stdio を固定する。


```
[mcp_servers.repo_docs.identity]
command = "python3"
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 240: Requirements remote sandbox dev

**目的**  管理設定で remote sandbox dev を固定する。


```
[[remote_sandbox_config]]
hostname_patterns = ["dev-*", "ci-*"]
allowed_sandbox_modes = ["read-only", "workspace-write"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 241: Requirements remote sandbox prod

**目的**  管理設定で remote sandbox prod を固定する。


```
[[remote_sandbox_config]]
hostname_patterns = ["prod-*"]
allowed_sandbox_modes = ["read-only"]
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 242: Requirements require hooks feature

**目的**  管理設定で require hooks feature を固定する。


```
[features]
hooks = true
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


### 追加設定レシピ 243: Requirements disable experimental apps

**目的**  管理設定で disable experimental apps を固定する。


```
[features]
apps = false
enable_mcp_apps = false
```


**確認**  `/debug-config` でrequirements由来の制約として確認する。

**戻し方**  管理側ファイルを更新し、配布手順で戻す。


---


### 追加設定レシピ 244: debug config first

**目的**  設定が効かない時の最初の確認を固定する。


```
# TUI
/debug-config
/status
/mcp

# CLI
codex features list
codex mcp list
```


**確認**  設定変更後に毎回同じ順番で確認する。

**戻し方**  問題が切り分けられたら不要なdebug出力を消す。


### 追加設定レシピ 245: execpolicy check batch

**目的**  rules変更をまとめて検証する。


```
codex execpolicy check "git status"
codex execpolicy check "git push"
codex execpolicy check "terraform apply"
codex execpolicy check "npm install"
```


**確認**  想定と異なる判定があればrulesを修正する。

**戻し方**  rules変更をrevertする。


---


### 追加設定レシピ 246: MCP health check

**目的**  MCP serverの状態確認手順を固定する。


```
codex mcp list
codex mcp get repo_docs
codex mcp get docs
```


**確認**  required serverの起動失敗を早めに検出する。

**戻し方**  `enabled = false` またはrequired解除で戻す。


### 追加設定レシピ 247: profile diff確認

**目的**  profile差分をCLI上書きで比較する。


```
codex --profile daily -c web_search="disabled"
codex --profile review -c model_reasoning_effort="high"
```


**確認**  一時上書きで動作を見てからTOMLへ反映する。

**戻し方**  一時上書きなので終了すれば戻る。


---


### 追加設定レシピ 248: schema validation comment

**目的**  エディタ診断を有効にする。


```
#:schema https://developers.openai.com/codex/config-schema.json
```


**確認**  TOML拡張がschemaを読むか確認する。

**戻し方**  schema行を削除する。


### 追加設定レシピ 249: version note

**目的**  設定変更時のCLI versionを記録する。


```
# Checked with:
# codex --version
# codex features list
# Date: 2026-05-08 JST
```


**確認**  設定PRやREADMEに確認日を残す。

**戻し方**  version更新時にコメントを更新する。


---


### 追加設定レシピ 250: CI config smoke

**目的**  CIでCodex設定を読めるかだけ確認する。


```
codex --profile ci_review --help
codex features list
codex mcp list || true
```


**確認**  認証不要の範囲で設定構文を確認する。

**戻し方**  CIでMCP tokenがない場合はrequiredにしない。


### 追加設定レシピ 251: local read-only planning

**目的**  危険な作業前にread-onlyで計画を確認する。


```
codex --profile readonly "Plan the migration. Do not edit files."
```


**確認**  計画の妥当性を確認してからworkerへ渡す。

**戻し方**  計画だけで実装完了としない。


---


### 追加設定レシピ 252: config rollback command

**目的**  gitで設定差分を戻す。


```
git diff -- .codex AGENTS.md
git checkout -- .codex/config.toml .codex/rules AGENTS.md
```


**確認**  戻す対象にgenerated fileが混ざっていないか確認する。

**戻し方**  revert commitを作る場合は理由を書く。


### 追加設定レシピ 253: monthly config review

**目的**  月次で設定の古さを確認する。


```
# checklist
codex --version
codex features list
codex mcp list
codex execpolicy check "git push"
# compare docs and schema before changing keys
```


**確認**  deprecated keyや不要MCPを棚卸しする。

**戻し方**  不要設定を削除し、templateを更新する。


---


## 追加レシピ集のまとめ

設定は、書いた瞬間ではなく、起動、診断、実行、rollbackまで確認して初めて運用可能になる。個人設定、project設定、managed requirements、MCP、Hooks、Rules、Subagentsを分離し、各断片に目的と戻し方を添えることで、Codex CLIの能力を広げつつ、権限の増加を管理できる。


---
