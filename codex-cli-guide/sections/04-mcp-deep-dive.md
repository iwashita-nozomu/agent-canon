<!--
@dependency-start
contract reference
responsibility Houses the split guide section: MCPの基礎から定義・運用・デバッグまで.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# MCPの基礎から定義・運用・デバッグまで

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 2977-3985
- section sha256: `63e637de165c7203a483c9d66d5076d873301d370db12eae35ff6777e12edda4`

<!-- split-content-start -->

# 第VI部 MCPの基礎から定義・運用・デバッグまで


## MCPとは何か

MCPはModel Context Protocolの略で、agentへ外部の文脈やtoolを提供するための接続方式である。Codex CLIでは、MCP serverを`config.toml`に登録し、Codexがそのserverのtoolを呼べるようにする。典型的には、repository内docs検索、issue tracker、browser操作、CI log、observability、社内API、design system、databaseのread-only参照などを接続する。MCPを使う価値は、agentが「知らない情報を推測する」のではなく、「許可されたtoolで確認する」ことにある。

MCPの最初の分岐はtransportである。STDIOはローカルprocessを起動して標準入出力で通信する。Streamable HTTPはURLへ接続し、Bearer tokenやOAuthなどの認証を使える。プロジェクト固有の軽量toolはSTDIO、社内で運用される共有serviceはHTTP、ユーザー個別の権限が必要なserviceはOAuthが向きやすい。ただし、最終的な判断は、secret管理、network境界、teamの再現性、server ownerの有無で決める。


#### 図解: MCPの三要素

`client Codex` → `server` → `tool`

_Codexはserver上のtoolを呼ぶ。_


#### 図解: transport選択

`STDIO` → `HTTP` → `OAuth`

_接続方式で運用が変わる。_


#### 図解: STDIOの流れ

`command起動` → `stdin stdout` → `tool result`

_ローカルprocessを使う。_


#### 図解: HTTPの流れ

`url` → `auth header` → `stream result`

_共有serverへ接続する。_


#### 図解: OAuthの流れ

`login` → `callback` → `token`

_ユーザー権限で接続する。_


#### 図解: server名設計

`短い名前` → `用途が分かる` → `衝突しない`

_名前は運用の鍵になる。_


#### 図解: tool名設計

`動詞` → `対象` → `範囲`

_tool名は誤用を防ぐ。_


#### 図解: 入力schema

`query` → `limit` → `filter`

_入力を狭く定義する。_


#### 図解: 出力schema

`summary` → `evidence` → `metadata`

_出力を要約可能にする。_


#### 図解: secret設計

`env var名` → `値は外部` → `rotation`

_secretをTOMLへ書かない。_


#### 図解: allowlist

`enabled tools` → `必要最小` → `review`

_tool面を絞る。_


#### 図解: denylist

`disabled tools` → `例外遮断` → `再確認`

_denyは補助として使う。_


#### 図解: required設計

`重要server` → `起動失敗` → `早期検知`

_必須serverだけtrueにする。_


#### 図解: timeout設計

`startup` → `tool` → `retry`

_timeoutをserver別に決める。_


#### 図解: cwd設計

`repo root` → `script dir` → `固定`

_起動directoryを安定させる。_


#### 図解: env転送

`local env` → `remote env` → `明示`

_環境変数は必要分だけ渡す。_


#### 図解: project MCP

`repo config` → `team共有` → `再現性`

_プロジェクト固有のtoolを共有する。_


#### 図解: personal MCP

`home config` → `個人tool` → `分離`

_個人の便利toolはhomeへ置く。_


#### 図解: managed MCP

`requirements` → `allowlist` → `pin`

_企業では管理設定を使う。_


#### 図解: MCPとtrust

`untrusted` → `project config` → `読み込み制限`

_trust前の読み込みに注意する。_


#### 図解: MCPとAGENTS

`使い方` → `禁止事項` → `例`

_tool使用条件を書く。_


#### 図解: MCPとHooks

`PreToolUse` → `PostToolUse` → `監査`

_tool callを検査する。_


#### 図解: MCPとRules

`shell境界` → `approval` → `block`

_command実行の境界を補う。_


#### 図解: MCPとsandbox

`workspace` → `network` → `write`

_OS境界とtool権限を合わせる。_


#### 図解: MCPとsubagent

`docs` → `browser` → `logs`

_専門agentに閉じる。_


#### 図解: MCPとCI

`log取得` → `artifact` → `原因分類`

_CI調査を自動化する。_


#### 図解: MCPとBrowser

`再現` → `console` → `network`

_UI debugを支援する。_


#### 図解: MCPとDocs

`検索` → `fetch` → `根拠`

_仕様確認に向く。_


#### 図解: MCPとIssue

`search` → `read` → `link`

_開発文脈を渡せる。_


#### 図解: MCPとDB

`read only` → `limit` → `mask`

_DB接続は特に制限する。_


#### 図解: MCPとObs

`trace` → `logs` → `metrics`

_本番文脈は権限注意。_


#### 図解: MCPとFiles

`read` → `write` → `guard`

_filesystem系は危険度が高い。_


#### 図解: MCPとSecrets

`secret検知` → `mask` → `deny`

_出力にsecretを載せない。_


#### 図解: MCPとAudit

`call log` → `approval` → `diff`

_監査できる設計にする。_


#### 図解: MCPとVersion

`Codex` → `server` → `schema`

_versionを三つ記録する。_


#### 図解: MCPとDocs更新

`config` → `prompt` → `FAQ`

_運用文書を一緒に更新する。_


#### 図解: MCPとOnboarding

`env` → `login` → `test`

_初期確認手順を用意する。_


#### 図解: MCPとRollback

`enabled false` → `profile` → `env解除`

_止め方を決める。_


#### 図解: MCPとAlternate route

`server down` → `repo search` → `human ask`

_代替手段を決める。_


#### 図解: MCPと権限分離

`read` → `write` → `admin`

_権限ごとにserverを分ける。_


#### 図解: MCPとscope

`最小scope` → `期間` → `owner`

_OAuth scopeを絞る。_


#### 図解: MCPとnetwork

`offline` → `internal` → `external`

_network境界を確認する。_


#### 図解: MCPと依存関係

`package` → `version` → `lock`

_server依存を固定する。_


#### 図解: MCPとエラー

`起動` → `認証` → `tool`

_不具合を層で切る。_


#### 図解: MCPと結果サイズ

`limit` → `snippet` → `summary`

_大きすぎる結果を避ける。_


#### 図解: MCPとprompt

`目的` → `制約` → `根拠`

_tool使用の指示を書く。_


#### 図解: MCPとレビュー

`目的` → `権限` → `証跡`

_追加時に必ずレビューする。_


#### 図解: MCPと更新

`diff` → `test` → `owner`

_更新にもレビューが必要。_


#### 図解: MCPと無効化

`enabled false` → `remove` → `disable`

_停止手順を練習する。_


#### 図解: MCPと障害

`detect` → `notify` → `alternate route`

_障害時の体験を決める。_


#### 図解: MCPと費用

`呼び出し` → `文脈` → `時間`

_無駄なtool呼び出しを抑える。_


#### 図解: MCPと品質

`根拠` → `再現` → `比較`

_推測ではなく確認する。_


#### 図解: MCPと安全

`最小権限` → `承認` → `監査`

_三点を基本にする。_


#### 図解: MCPと運用

`owner` → `docs` → `check`

_運用責務を追える形に保つ。_


#### 図解: MCP成熟度

`試験` → `限定` → `標準`

_段階的に広げる。_


#### 図解: MCP最終設計

`transport` → `auth` → `tools`

_三要素を明示する。_


## MCP server定義の基本形

Codex CLIのMCP server定義は、`[mcp_servers.<server-name>]`のTOML tableで表す。server名は設定上の識別子であり、tool呼び出しの表示、hook matcher、運用文書に出てくる。名前は短く、用途が分かり、環境ごとに衝突しないものにする。たとえば`docs`より`projectDocs`、`issueTracker`、`browserDebug`の方が運用上わかりやすい。


```text
L{0.30}L{0.42}}
項目  |  内容  |  実務上の判断
`command`  |  STDIO serverを起動するcommand。  |  node、python、uvx、npxなど。絶対pathより固定cwdとlockを重視する。
`args`  |  commandへ渡す引数。  |  script path、package名、port、modeなどを置く。
`cwd`  |  server起動directory。  |  project-local scriptではrepo rootに固定する。
`env`  |  固定環境変数map。  |  secret値の直書きは避ける。
`env_vars`  |  親環境から転送する変数。  |  必要なsecret名だけ明示する。
`url`  |  HTTP MCP endpoint。  |  社内serverやhosted connectorに使う。
`bearer_token_env_var`  |  Bearer tokenを読む環境変数名。  |  token値は外部に置く。
`http_headers`  |  固定HTTP header。  |  secretを含まない固定値に使う。
`env_http_headers`  |  環境変数由来のheader map。  |  header secretの受け渡しに使う。
`scopes`  |  OAuth login時のscope候補。  |  読み取りscopeから始める。
`oauth_resource`  |  OAuth resource parameter。  |  server側の要求に合わせる。
`enabled`  |  server有効化。  |  falseで設定を残して停止できる。
`required`  |  起動失敗時にsessionを失敗させる。  |  必須serverだけtrueにする。
`enabled_tools`  |  tool allowlist。  |  最小権限の中心。
`disabled_tools`  |  tool denylist。  |  例外遮断として使う。
`startup_timeout_sec`  |  起動待ちtimeout。  |  遅いserverだけ伸ばす。
`tool_timeout_sec`  |  tool呼び出しtimeout。  |  検索や外部APIで調整する。
```


## STDIO MCPの完全テンプレート

STDIO MCPは、project-localな処理と相性がよい。たとえば、repository内のADRやdesign docsを検索するserver、生成済みOpenAPI schemaを読むserver、ローカルtest artifactを要約するserverなどである。server実装はMCP protocolを話す必要があるため、実装時はMCP SDKや既存serverを使うのが現実的である。本書ではCodex側の定義と運用に焦点を当てる。


```
# .codex/config.toml
[mcp_servers.projectDocs]
command = "node"
args = ["tools/mcp/project-docs-server.mjs"]
cwd = "."
enabled = true
required = false
startup_timeout_sec = 10
tool_timeout_sec = 30
enabled_tools = ["search_docs", "read_doc", "list_adrs"]

[mcp_servers.projectDocs.env]
PROJECT_DOCS_INDEX = ".codex/cache/docs-index.json"
```


```
# docs/codex/mcp-projectDocs.md
purpose: Repository内の設計文書を検索する。
transport: stdio
risk: read-only
owner: platform-team
allowed_agents: [docs_researcher, pr_explorer]
forbidden: secrets, production data, write operations
failure_alternate route: use ripgrep in docs/ and ask human for missing context
```


#### 図解: STDIO template

`command` → `args` → `cwd`

_起動方法を固定する。_


#### 図解: STDIO env

`env` → `env vars` → `secretなし`

_環境変数は必要最小限にする。_


#### 図解: STDIO tool制限

`enabled tools` → `read only` → `limit`

_read-only toolに絞る。_


#### 図解: STDIO alternate route

`server down` → `grep` → `human ask`

_代替方法を決める。_


#### 図解: STDIO ownership

`owner` → `docs` → `tests`

_保守担当を明記する。_


## HTTP MCPとOAuth MCPの完全テンプレート

HTTP MCPは、serverを別processまたは別hostで運用し、CodexがURLへ接続する構成である。社内docs、issue tracker、browser automation、observabilityなどに向く。Bearer token方式では、token値をTOMLに直書きせず、`bearer_token_env_var`で環境変数名を指定する。OAuth方式では、callback port、callback URL、scope、resourceを合わせて設計する。


```
# HTTP MCP: bearer token
[mcp_servers.internalDocs]
url = "https://mcp.example.internal/docs"
enabled = true
required = false
bearer_token_env_var = "INTERNAL_DOCS_MCP_TOKEN"
enabled_tools = ["search", "fetch"]
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.internalDocs.env_http_headers]
X-Team = "CODEX_TEAM_NAME"
```


```
# OAuth MCP
mcp_oauth_callback_port = 1455
mcp_oauth_callback_url = "http://localhost:1455/callback"

[mcp_servers.issueTracker]
url = "https://mcp.example.internal/issues"
enabled = true
required = false
scopes = ["issues:read", "pull_requests:read"]
oauth_resource = "https://mcp.example.internal"
enabled_tools = ["search_issues", "read_issue", "list_prs"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```


#### 図解: HTTP template

`url` → `token env` → `tools`

_token値は外部に置く。_


#### 図解: HTTP headers

`static` → `env header` → `audit`

_header secretはenv経由にする。_


#### 図解: OAuth callback

`port` → `url` → `login`

_callbackを固定して運用する。_


#### 図解: OAuth scopes

`read` → `write` → `admin`

_読み取りscopeから始める。_


#### 図解: OAuth resource

`server要求` → `resource` → `確認`

_resource parameterを明示する。_


## MCP toolを定義する時の設計原則

MCP toolは、agentが呼び出す関数のようなものである。toolが大きすぎると、agentは必要以上の情報や権限を持つ。toolが曖昧だと、agentは誤った引数を作りやすい。toolが巨大な結果を返すと、文脈が汚れ、重要情報が埋もれる。よいtoolは、名前が具体的で、入力が狭く、出力が短く、失敗時の理由が明確で、権限が最小である。


```text
L{0.32}L{0.44}}
項目  |  内容  |  実務上の判断
名前  |  動詞と対象を含める。  |  `search_docs`、`read_issue`のように用途が分かる名前にする。
入力  |  query、limit、filterを明確化する。  |  自由文字列だけにせず、limitやscopeを持たせる。
出力  |  summary、evidence、metadataに分ける。  |  全文よりsnippetとpathを返す。
失敗  |  not found、auth、timeoutを分ける。  |  agentが次に何をすべきか分かるmessageにする。
権限  |  readとwriteを分ける。  |  write toolは別server、別profile、別approvalにする。
監査  |  tool callを記録する。  |  誰がいつ何を読んだか、必要に応じて追えるようにする。
```


#### 図解: tool名

`動詞` → `対象` → `範囲`

_名前は仕様である。_


#### 図解: 入力制限

`limit` → `filter` → `scope`

_広すぎる入力を避ける。_


#### 図解: 出力制限

`snippet` → `summary` → `metadata`

_巨大出力を避ける。_


#### 図解: 失敗表現

`auth` → `not found` → `timeout`

_原因別に返す。_


#### 図解: write分離

`read server` → `write server` → `approval`

_write toolは別扱いにする。_


## MCPとサブエージェント: 親文脈を汚さない設計

MCPは情報量を増やすため、親セッションにすべてのserverを持たせると、文脈が散らばる。そこで、MCPは用途別のサブエージェントへ閉じ込める。`docs_researcher`は公式文書や社内docs、`browser_debugger`はUI再現、`logs_analyst`はCIやobservability、`issue_mapper`はticketとPRの関連付けに集中する。親agentは、各agentに短い成果物形式を要求する。


```
# .codex/agents/logs-analyst.toml
name = "logs_analyst"
description = "CI logやobservability MCPを使い、失敗原因を短く分類する。"
sandbox_mode = "read-only"
model_reasoning_effort = "medium"
developer_instructions = """
ログ全体を貼らない。失敗原因候補、根拠行、再現コマンド、未確認事項を返す。
本番データやsecretらしき値は引用しない。
"""

[mcp_servers.ciLogs]
enabled = true
enabled_tools = ["search_runs", "read_log", "list_artifacts"]
```


#### 図解: 親文脈の保護

`MCP結果` → `子agent` → `要約`

_重い結果は子に閉じる。_


#### 図解: docs researcher

`検索` → `fetch` → `根拠`

_仕様確認を担当する。_


#### 図解: browser debugger

`再現` → `console` → `network`

_UI証拠を集める。_


#### 図解: logs analyst

`log` → `artifact` → `原因`

_CI failureを分類する。_


#### 図解: issue mapper

`issue` → `PR` → `history`

_開発文脈を整理する。_


## MCPとHooks: tool callを検査する

Hooksは、Codexのtool使用前後にscriptを走らせる仕組みである。MCP tool callを検査すると、危険なtool名、広すぎるquery、write系操作、secretらしき出力、巨大resultを早期に止められる。特に`PreToolUse`は、実行前に止めるための安全網として重要である。


```
# .codex/hooks.json
{
  "PreToolUse": [
    {
      "matcher": "mcp__issueTracker__*",
      "hooks": [
        {"type": "command", "command": "python3 .codex/hooks/mcp_guard.py"}
      ]
    }
  ]
}
```


```
# .codex/hooks/mcp_guard.py
import json, sys
payload = json.load(sys.stdin)
name = payload.get("tool_name", "")
args = payload.get("arguments", {})
if any(x in name.lower() for x in ["delete", "write", "update", "create"]):
    print("write-like MCP tool requires manual approval", file=sys.stderr)
    sys.exit(2)
if len(str(args.get("query", ""))) > 2000:
    print("MCP query too large", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
```


#### 図解: PreToolUse

`tool名` → `引数` → `block`

_実行前に検査する。_


#### 図解: PostToolUse

`結果` → `secret` → `log`

_結果側の監査に使う。_


#### 図解: hook matcher

`mcp server` → `tool pattern` → `script`

_対象を絞る。_


#### 図解: write guard

`create` → `update` → `delete`

_write系を別扱いにする。_


#### 図解: query guard

`長さ` → `scope` → `limit`

_広すぎるqueryを止める。_


## MCPとRules、sandbox、approvalの重ね方

MCPは外部toolの面を増やす。Rulesはshell commandの実行可否をprefixで制御する。sandboxはOSレベルの境界を作る。approvalは人間の確認を挟む。これらは役割が違うため、どれか一つだけで安全になるとは考えない。MCPのtool allowlistで外部tool面を絞り、sandboxでファイルとnetwork境界を絞り、approvalで高リスク操作を確認し、HooksでMCP callを検査する。


```text
L{0.34}L{0.36}}
項目  |  内容  |  実務上の判断
MCP allowlist  |  server toolの範囲を絞る。  |  外部能力の入口を制御する。
sandbox  |  OS上の読み書きやnetworkを制限する。  |  tool外のshell実行にも効く境界。
approval  |  人間の確認を挟む。  |  境界越えや高リスク操作に使う。
Rules  |  command prefixで許可、確認、禁止を決める。  |  shell実行の予防線。
Hooks  |  tool使用やprompt提出をscriptで検査する。  |  動的な条件判定と監査。
```


#### 図解: 安全の重ね方

`MCP` → `sandbox` → `approval`

_複数層で守る。_


#### 図解: Rulesの役割

`command` → `prefix` → `policy`

_shell境界を制御する。_


#### 図解: sandboxの役割

`files` → `network` → `process`

_OS境界を作る。_


#### 図解: approvalの役割

`確認` → `記録` → `停止`

_人間判断を入れる。_


#### 図解: Hooksの役割

`検査` → `監査` → `block`

_動的に止める。_


## MCPデバッグの順番

MCPの障害は、起動、認証、transport、tool schema、timeout、出力サイズ、agentの使い方に分解して確認する。まず`/mcp`でserverが見えているかを確認する。次に、`/debug-config`で設定layerと有効状態を確認する。STDIOならcommandを人間が同じcwdで実行する。HTTPならURL、header、token、scopeを確認する。toolが呼べても結果がおかしい場合は、tool単体で入力と出力を再現し、server側のlogを見る。


```text
L{0.34}L{0.36}}
項目  |  内容  |  実務上の判断
serverが表示されない  |  設定layer、project trust、root検出。  |  `/debug-config`とproject rootを確認する。
起動しない  |  command、args、cwd、依存package。  |  同じcwdでserverを単体起動する。
401または403  |  token、scope、OAuth resource。  |  環境変数名とscopeを確認する。
toolが見えない  |  `enabled_tools`、`disabled_tools`、server schema。  |  allowlistとserver側tool定義を確認する。
timeout  |  起動遅延、外部API遅延、巨大query。  |  timeout調整より先にserver速度を確認する。
結果が巨大  |  limitなし、全文返却。  |  snippet化、limit、summaryをserver側で実装する。
agentが誤用  |  tool説明やAGENTSが曖昧。  |  使用条件とprompt例を追加する。
```


#### 図解: debug step 1

`/mcp` → `status` → `server`

_まず見えているか確認する。_


#### 図解: debug step 2

`/debug-config` → `layers` → `enabled`

_設定layerを確認する。_


#### 図解: debug step 3

`cwd` → `command` → `args`

_STDIO起動を再現する。_


#### 図解: debug step 4

`url` → `token` → `scope`

_HTTP認証を確認する。_


#### 図解: debug step 5

`tool input` → `tool output` → `log`

_tool単体で再現する。_


## MCP追加時のレビューシート

MCPを追加するpull requestには、設定diffだけでなく、目的、owner、server実装場所、認証方式、許可tool、禁止tool、timeout、alternate route、AGENTS更新、Hook有無を含める。特にwrite系toolを含む場合は、read系serverと分けるか、初期状態では`enabled = false`にする。


```text
L{0.36}L{0.40}}
項目  |  内容  |  実務上の判断
目的  |  何を解決するMCPか。  |  人間が頻繁に行う確認を減らす。
owner  |  誰がserverを保守するか。  |  ownerなしは追加しない。
transport  |  STDIO、HTTP、OAuthのどれか。  |  理由をPRに書く。
auth  |  secret、token、scopeの扱い。  |  値をTOMLに書かない。
tools  |  `enabled_tools`で絞っているか。  |  必要最小限から始める。
timeout  |  startupとtool timeout。  |  server別に設定する。
hooks  |  危険toolを検査するか。  |  write系にはhookを付ける。
docs  |  AGENTS.mdやdocs更新。  |  使い方と禁止事項を書く。
alternate route  |  server停止時の代替手段。  |  人間が困らない状態にする。
rollback  |  enabled falseや設定削除。  |  戻し方をPRに書く。
```


## 成熟したプロジェクト構成サンプル

成熟したプロジェクトでは、Codex向けの設定が散らばらないように配置を決める。rootには全体方針、AGENTS.md、共通MCP、Hooks、Rulesを置く。packageやserviceごとに追加指示が必要なら、そのdirectoryにAGENTS.mdや.codex/config.tomlを置く。ただし、project-local設定はtrust前に確認されるべきであり、secret値や個人pathは入れない。


```
repo/
  AGENTS.md
  .codex/
    config.toml
    hooks.json
    hooks/
      mcp_guard.py
      command_guard.py
    agents/
      docs-researcher.toml
      browser-debugger.toml
      logs-analyst.toml
    rules/
      safe-shell.rules
    skills/
      release-notes/SKILL.md
    mcp/
      projectDocs.md
  tools/
    mcp/
      project-docs-server.mjs
  docs/
    codex/
      mcp-inventory.md
      experimental-runbook.md
```


```
# .codex/config.toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

[features]
hooks = true
multi_agent = true
fast_mode = false

[agents]
max_threads = 4
max_depth = 1
job_max_runtime_seconds = 1200

[mcp_servers.projectDocs]
command = "node"
args = ["tools/mcp/project-docs-server.mjs"]
cwd = "."
enabled = true
required = false
enabled_tools = ["search_docs", "read_doc", "list_adrs"]
startup_timeout_sec = 10
tool_timeout_sec = 30

[mcp_servers.issueTracker]
url = "https://mcp.example.internal/issues"
enabled = false
required = false
bearer_token_env_var = "ISSUE_TRACKER_MCP_TOKEN"
enabled_tools = ["search_issues", "read_issue"]
startup_timeout_sec = 20
tool_timeout_sec = 60
```


#### 図解: 成熟構成 root

`AGENTS` → `config` → `hooks`

_rootに全体方針を置く。_


#### 図解: 成熟構成 agents

`docs` → `browser` → `logs`

_agentごとにMCPを分ける。_


#### 図解: 成熟構成 rules

`safe shell` → `prompt` → `forbid`

_shell境界を明示する。_


#### 図解: 成熟構成 docs

`inventory` → `runbook` → `FAQ`

_運用文書を残す。_


#### 図解: 成熟構成 tools

`mcp server` → `tests` → `owner`

_server実装を管理する。_


## 実験的機能とMCPの統合チェックリスト

最後に、実験的機能とMCPを同時に使う場合のチェックリストを示す。MCPは外部tool面を増やし、実験機能は挙動変更の可能性を増やす。したがって、同時導入では「実験機能のrollback」と「MCPのdisable」を両方用意する。


```text
L{0.42}L{0.34}}
項目  |  内容  |  実務上の判断
version  |  Codex CLI versionとchangelog日付を記録した。  |  更新後に挙動差分を確認できる。
feature  |  有効化したfeature flag名を記録した。  |  disable手順が分かる。
profile  |  lab profileで検証した。  |  default profileに混ぜない。
MCP auth  |  token値をTOMLに書いていない。  |  secret管理を分離する。
MCP tools  |  `enabled_tools`で絞っている。  |  最小権限から始める。
sandbox  |  workspace-writeまたはread-onlyで検証した。  |  dangerは隔離環境だけ。
approval  |  on-requestなど確認を残した。  |  承認なし運用を避ける。
hooks  |  write系や巨大queryを検査する。  |  動的な安全網を置く。
subagents  |  重いMCPは専用agentへ閉じた。  |  親文脈を守る。
docs  |  AGENTS.mdまたはdocsに使い方を書いた。  |  チームで再現できる。
rollback  |  features disableとenabled falseを確認した。  |  戻せる状態で始める。
owner  |  MCP serverと実験機能のownerを決めた。  |  放置を防ぐ。
```


---
