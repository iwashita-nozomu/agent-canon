<!--
@dependency-start
contract reference
responsibility Houses the split guide section: 設定の書き方完全増補とレシピ001-113.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# 設定の書き方完全増補とレシピ001-113

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 5634-8964
- section sha256: `f1ad25e66856eddd5526345c6c40852f3887de121399637c9d123c1f1a94eb2c`

<!-- split-content-start -->

# 第VII部 設定ファイルの書き方完全増補


## この増補で扱う設定の書き方

前回版では、設定項目の一覧と概念説明を厚くした。一方で、日常運用では「どのファイルに、どの順番で、どの断片を、どの粒度で書くか」が重要である。この増補では、`config.toml`、`requirements.toml`、`.codex/config.toml`、`.codex/agents/*.toml`、`.codex/rules/*.rules`、`AGENTS.md`、Hooks、MCP、profilesを、実際にコピーして編集できる構成例として扱う。

設定は一度に完成させるものではない。最初は最小のユーザー設定を作り、次にプロジェクト設定を追加し、最後にMCP、Hooks、Rules、Subagents、企業向けrequirementsを段階的に重ねる。特に、MCPとHooksは外部接続やコマンド実行を増やすため、目的、owner、権限、timeout、失敗時挙動、rollbackを設定断片の近くにコメントで残す。


設定ファイルを巨大な一枚にしない。個人の既定値は `~/.codex/config.toml`、repo固有の挙動は `.codex/config.toml`、agent roleは `.codex/agents/*.toml`、実行制約は `.codex/rules/*.rules`、人間向け規約は `AGENTS.md` に分ける。


#### 図解: 設定を書く順序

`最小設定` → `差分確認` → `段階追加`

_責務境界を書いて検証する。_


#### 図解: 設定ファイルの役割

`個人設定` → `プロジェクト設定` → `管理設定`

_役割分担を混ぜない。_


#### 図解: TOMLの基本

`root key` → `table` → `array table`

_TOMLの構造を先に理解する。_


#### 図解: 検証ループ

`編集` → `起動` → `debug`

_設定は実行して確かめる。_


#### 図解: rollback設計

`コメント` → `git diff` → `削除`

_戻し方も設定の一部である。_


#### 図解: MCP追加手順

`必要性` → `最小tool` → `認証`

_tool面を絞る。_


#### 図解: Hooks追加手順

`event` → `matcher` → `script`

_発火条件を限定する。_


#### 図解: Subagent追加手順

`役割` → `sandbox` → `成果物`

_親と子の責務を分ける。_


#### 図解: requirements追加手順

`許可値` → `強制hook` → `deny read`

_管理設定は弱められない前提で書く。_


#### 図解: 最新確認

`version` → `docs` → `schema`

_version差を前提に確認する。_


## TOMLを書く前の共通ルール

Codexの設定はTOMLで書く。TOMLは単純に見えるが、root key、table、array of tables、dotted keyの混在で意図しないスコープになることがある。公式サンプルにもあるように、root keyはtableより前に置くのが読みやすい。たとえば、`model`、`approval_policy`、`sandbox_mode`、`web_search` のようなroot keyを先に書き、その後に `[features]`、`[profiles.lab]`、`[mcp_servers.docs]`、`[[hooks.PreToolUse]]` などを書く。


### TOMLの最小構文


```
# root key: ファイル全体に効く
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

# table: 名前空間を作る
[features]
fast_mode = true
multi_agent = true

# nested table: 階層を作る
[profiles.readonly]
sandbox_mode = "read-only"
approval_policy = "on-request"

# array of tables: 同じ形の要素を複数並べる
[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/pre_tool_use.py"
timeout = 30
```


### よくある書き間違い


```text
L{0.32}L{0.38}}
項目  |  書き方  |  確認ポイント
項目  |  書き方  |  確認ポイント
root keyをtableの後ろへ置く  |  先にroot keyを書き、その後にtableを書く。  |  後から読んだ人がスコープを誤解しにくい。
同じtableを離れた場所で再定義する  |  関連keyを近くにまとめる。  |  merge自体は可能でも、レビューしづらくなる。
secretを直書きする  |  環境変数名だけを書く。  |  tokenの値はTOMLやGitへ入れない。
MCP toolを全許可にする  |  enabled_toolsで必要なtoolだけ許可する。  |  denylistよりallowlistを優先する。
Hooksのmatcherを広くしすぎる  |  Bashや特定toolに限定する。  |  全部のtoolに重いhookを当てない。
project設定に個人pathを書く  |  repo相対pathか環境変数を使う。  |  他の開発者の環境で壊れる。
profileを増やしすぎる  |  日常、調査、実験、CI程度に絞る。  |  profile差分を文書化する。
requirementsを過剰に縛る  |  最初はsandboxとapprovalの許可値から始める。  |  全員の作業不能を防ぐ。
```


## 設定レイヤと配置場所の実例

Codex設定の基本は、個人、プロジェクト、profile、CLI上書き、管理要求の分離である。個人設定は複数repoで共有する既定値に向く。プロジェクト設定はrepo内の規約、MCP、Hooks、Rules、Subagentsのように、そのrepoを開いたときだけ使う内容に向く。企業や管理者の制約は、ユーザーが弱められない `requirements.toml` で扱う。


```
$HOME/.codex/
  config.toml                 # 個人の既定値
  agents/
    reviewer.toml             # 個人用custom agent
  logs/                       # log_dirをここへ寄せてもよい

repo/
  AGENTS.md                   # repo全体の人間向け指示
  .codex/
    config.toml               # trusted projectで読み込むrepo設定
    agents/
      pr-reviewer.toml        # repo固有のcustom agent
      migration-worker.toml
    rules/
      shell.rules             # コマンド実行ポリシー
    hooks/
      pre_tool_use.py         # hook script
      post_tool_use.py
    skills/
      api-migration/SKILL.md  # project-local skill
  services/api/AGENTS.md      # 近い階層の追加指示
  apps/web/AGENTS.md
```


```text
L{0.32}L{0.38}}
項目  |  書き方  |  確認ポイント
項目  |  書き方  |  確認ポイント
個人設定  |  `~/.codex/config.toml`  |  全repoで使うmodel、UI、既定sandbox、個人MCP。
repo設定  |  `.codex/config.toml`  |  trusted projectだけで読み込むrepo専用設定。
agent file  |  `.codex/agents/*.toml`  |  一つのcustom agentを一ファイルで定義する。
Rules  |  `.codex/rules/*.rules`  |  shell commandのallow、prompt、forbiddenを定義する。
Hooks  |  `[hooks]` または hook script  |  lifecycle eventでscriptを実行する。
AGENTS.md  |  `AGENTS.md`  |  人間向け規約、ビルド手順、禁止事項を書く。
requirements  |  `requirements.toml`  |  管理者が安全制約を固定する。
```


## 設定の検証コマンド集

設定を書いたら、起動して体感で判断するのではなく、診断コマンドを使う。特に `/debug-config` は、設定レイヤ、requirements、policy、MCP、Rules、experimental networkなどを追う入口になる。CLI側では、`codex features list`、`codex mcp list`、`codex execpolicy check`、`codex --help`、`codex exec --help` を組み合わせる。


```
# TUI内
/status
/debug-config
/mcp
/experimental

# CLI側
codex --help
codex exec --help
codex features list
codex features enable unified_exec
codex features disable shell_snapshot
codex mcp list
codex mcp get docs
codex execpolicy check --help

# 一時上書きで比較
codex -c approval_policy="on-request" -c sandbox_mode="read-only"
codex --profile lab
codex --profile readonly -c web_search="disabled"
```


## 設定レシピ集: コピーしてから削る

ここからは、設定断片を目的別に並べる。すべてを一つのファイルに入れるのではなく、必要な断片だけをコピーし、`/debug-config`、`codex features list`、`codex mcp list`、`codex execpolicy check` で確認する。


---


## 設定レシピ集 001: 基本、モデル、profile、履歴


### 設定レシピ 001: 最小の個人設定


**目的と配置**  目的: 日常の既定モデル、承認、sandbox、検索モードを固定する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
log_dir = "/Users/me/.codex/log"
```


**確認** 
起動後に `/status` と `/debug-config` で model、approval、sandbox、web searchを確認する。


**落とし穴** 
最初からMCP、Hooks、Subagentsまで入れない。基本値が効くことを確認してから足す。


### 設定レシピ 002: 調査専用read-only設定


**目的と配置**  目的: コードを読むだけの安全なprofileを作る。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.readonly]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "cached"
model_reasoning_effort = "medium"
```


**確認** 
`codex --profile readonly` で起動し、編集やshell実行がどう扱われるか確認する。


**落とし穴** 
read-onlyでも、MCPやweb searchが外部文脈を持ち込む場合がある。必要なら `web_search = "disabled"` にする。


### 設定レシピ 003: 実験用lab profile


**目的と配置**  目的: 新機能を通常作業から隔離する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.lab]
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

[profiles.lab.features]
multi_agent = true
hooks = true
fast_mode = false
goals = true
```


**確認** 
`codex --profile lab` と `codex features list` を併用して、想定した機能だけが有効か見る。


**落とし穴** 
実験機能をroot設定に入れると、普段の作業にも影響する。profileへ閉じ込める。


### 設定レシピ 004: モデル指示ファイルを分離する


**目的と配置**  目的: 長いmodel instructionsをTOMLから外に出す。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
model = "gpt-5.5"
model_instructions_file = "/Users/me/.codex/instructions/default.md"
```


**確認** 
ファイルが存在し、Codex起動時に読み込まれることを `/debug-config` で確認する。


**落とし穴** 
project固有の規約は `AGENTS.md` へ書く。個人の一般方針だけをinstructions fileへ置く。


### 設定レシピ 005: プランモードの推論を強める


**目的と配置**  目的: 設計相談だけ高めのreasoning effortにする。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
model = "gpt-5.5"
model_reasoning_effort = "medium"
plan_mode_reasoning_effort = "high"
```


**確認** 
`/plan` で設計依頼を出し、通常モードとの差を確認する。


**落とし穴** 
常時highにすると速度や利用量に影響する可能性がある。planだけ強める設計にする。


### 設定レシピ 006: コミュニケーションスタイルを固定する


**目的と配置**  目的: 説明の口調を日常作業向けに合わせる。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
personality = "pragmatic"

[features]
personality = true
```


**確認** 
`/personality` でも変更できるため、TUIで現在値を見る。


**落とし穴** 
チーム共通の強い口調指定は避ける。個人設定に留める方がよい。


### 設定レシピ 007: web searchを無効化する


**目的と配置**  目的: ローカルコードだけで作業させたい。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
web_search = "disabled"
```


**確認** 
`/debug-config` でproject layerが読み込まれ、web searchがdisabledになったか確認する。


**落とし穴** 
untrusted projectではproject設定が読まれない。trusted状態を確認する。


### 設定レシピ 008: live search用profile


**目的と配置**  目的: 最新仕様確認が必要なときだけlive searchを使う。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.research]
web_search = "live"
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認** 
`codex --profile research` で使う。通常profileへliveを固定しない。


**落とし穴** 
live検索結果は常に検証対象であり、コード変更の根拠にするなら出典を残す。


---


### 設定レシピ 009: service tierをprofileで分ける


**目的と配置**  目的: 速度重視と深い確認を切り替える。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.fast]
service_tier = "fast"
model_reasoning_effort = "low"

[profiles.deep]
service_tier = "flex"
model_reasoning_effort = "high"
```


**確認** 
`codex --profile fast` と `codex --profile deep` を用途で使い分ける。


**落とし穴** 
service tierはプランや機能フラグの影響を受ける。effective configで確認する。


### 設定レシピ 010: ログ出力先をプロジェクト外へ出す


**目的と配置**  目的: repoにログを混ぜず、調査しやすい場所へ集約する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
log_dir = "/Users/me/.codex/logs"
history = { persistence = "save-all", max_bytes = 52428800 }
```


**確認** 
起動後、指定dirにlogが出るか確認する。


**落とし穴** 
共有repo内の `.codex-log` などへ個人logを常時出すと、誤commitの原因になる。


### 設定レシピ 011: 履歴保存を止めるprofile


**目的と配置**  目的: 機微な検証時だけhistoryを残さない。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.nohistory]
history = { persistence = "none" }
sandbox_mode = "read-only"
web_search = "disabled"
```


**確認** 
`codex --profile nohistory` で起動し、history保存設定を確認する。


**落とし穴** 
履歴を止めても、shellや外部toolのlogは別に残る場合がある。


### 設定レシピ 012: 画像入力を使うprofile


**目的と配置**  目的: UIやエラー画面の読解をしやすくする。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.ui]
tools_view_image = true
model_reasoning_effort = "medium"
```


**確認** 
`codex --profile ui -i screenshot.png "このエラーを分析"` のように使う。


**落とし穴** 
画像内にsecretや個人情報が含まれていないか確認してから添付する。


### 設定レシピ 013: OpenAI providerを明示する


**目的と配置**  目的: model providerの既定を明示し、他provider設定と混同しない。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
model_provider = "openai"
model = "gpt-5.5"
```


**確認** 
`/debug-config` でproviderとmodelを確認する。


**落とし穴** 
model名は更新される可能性がある。利用可能モデルはCLIや公式docsで確認する。


### 設定レシピ 014: OSS provider用profile


**目的と配置**  目的: ローカルOSSモデル検証と通常OpenAI利用を分ける。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.oss]
oss_provider = "ollama"
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認** 
`codex --profile oss --oss` のように使い、挙動を分ける。


**落とし穴** 
OSS providerではmodel機能、tool対応、速度が違う場合がある。通常profileと混ぜない。


### 設定レシピ 015: 一時上書きの使い方


**目的と配置**  目的: 設定ファイルを編集せず、その実行だけ変える。 配置: `CLI flag`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
codex -c sandbox_mode="read-only" -c web_search="disabled"
codex -c 'sandbox_workspace_write.network_access=false'
```


**確認** 
一時実行後に設定ファイルが変わっていないことを確認する。


**落とし穴** 
shellのquote規則に注意する。複雑な値はTOMLに書いた方が安全である。


---


## 設定レシピ集 016: Sandbox、Approval、Rules、CI


### 設定レシピ 016: workspace writeの標準設定


**目的と配置**  目的: repo内は編集可能、外部書き込みは抑える。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
sandbox_mode = "workspace-write"
approval_policy = "on-request"

[sandbox_workspace_write]
writable_roots = []
network_access = false
exclude_tmpdir_env_var = false
exclude_slash_tmp = false
```


**確認** 
patch作成、test実行、外部networkの扱いをsandbox repoで確認する。


**落とし穴** 
network_accessをtrueにする前に、downloadや外部API利用の理由をAGENTS.mdへ書く。


---


### 設定レシピ 017: 追加書き込みrootを許可する


**目的と配置**  目的: monorepo外の一時成果物dirだけ書き込みたい。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
writable_roots = ["/Users/me/tmp/codex-artifacts"]
network_access = false
```


**確認** 
`/debug-config` でwritable rootに入っているか確認する。


**落とし穴** 
広いpathを許可しない。HOME全体や親dirを入れると境界が崩れる。


### 設定レシピ 018: tmp書き込みを制限する


**目的と配置**  目的: 一時dirへ予期しない出力を避ける。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
exclude_tmpdir_env_var = true
exclude_slash_tmp = true
```


**確認** 
build toolがtmpを要求する場合は失敗する。必要性を確認してから緩める。


**落とし穴** 
node、cargo、pytestなどがtmpを使う場合があるため、CIで試す。


### 設定レシピ 019: danger full accessを隔離profileへ閉じ込める


**目的と配置**  目的: 使う場合だけ明示的に選ぶ。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.danger_lab]
sandbox_mode = "danger-full-access"
approval_policy = "never"
web_search = "disabled"
```


**確認** 
`codex --profile danger_lab` と明示したときだけ使う。


**落とし穴** 
通常profileにこの設定を入れない。使い捨てcontainerやVM内で使う。


### 設定レシピ 020: untrusted approvalで保守的に始める


**目的と配置**  目的: 読み取り以外はほぼ確認したい。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
approval_policy = "untrusted"
sandbox_mode = "workspace-write"
```


**確認** 
最初の数タスクでapproval頻度を観察する。


**落とし穴** 
承認が多すぎる場合でも、いきなりneverにしない。on-requestへ段階的に変える。


### 設定レシピ 021: granular approvalの入口


**目的と配置**  目的: 承認promptの種類を個別制御する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
approval_policy = { granular = { sandbox_approval = true, rules = true, mcp_elicitations = false, request_permissions = false, skill_approval = false } }
```


**確認** 
`/debug-config` でgranular設定が解決されているか見る。


**落とし穴** 
granularは読みづらいので、コメントで意図を書く。


### 設定レシピ 022: auto reviewを試す


**目的と配置**  目的: 承認判断の補助を使う。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
approvals_reviewer = "auto_review"

[auto_review]
policy = "Prefer denying commands that touch secrets, credentials, SSH keys, or production deploy settings."
```


**確認** 
sandbox escapeやMCP approval時の挙動を低リスクrepoで確認する。


**落とし穴** 
自動reviewは人間の責任を消さない。重要操作は別途確認する。


### 設定レシピ 023: deny readでsecretを読ませない


**目的と配置**  目的: 秘密ファイルをsandboxで読めないようにする。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[sandbox_workspace_write]
writable_roots = []
network_access = false

[filesystem]
".env" = "none"
".env.*" = "none"
"secrets/**" = "none"
```


**確認** 
実際に該当pathを読ませるコマンドが拒否されるか検証する。


**落とし穴** 
この表記はschema/versionに依存する。requirementsのdeny_readとあわせて確認する。


### 設定レシピ 024: shell環境変数の継承を抑える


**目的と配置**  目的: shell実行へ渡る環境を最小化する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[shell_environment_policy]
inherit = "core"
ignore_default_excludes = false
exclude = ["AWS_*", "GITHUB_*", "*_TOKEN", "*_SECRET"]
include_only = []
set = { "CI" = "1" }
```


**確認** 
Codexが実行する `env` の出力を低リスク環境で確認する。


**落とし穴** 
必要なPATHまで落とすとtoolが起動しない。coreから始める。


---


### 設定レシピ 025: CI用の承認なしread-only


**目的と配置**  目的: CIでレポートだけ作る。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.ci_review]
sandbox_mode = "read-only"
approval_policy = "never"
web_search = "disabled"
model_reasoning_effort = "medium"
```


**確認** 
`codex exec --profile ci_review` で差分reviewを実行する。


**落とし穴** 
writeが必要な修正生成CIとは分ける。


### 設定レシピ 026: CI用のpatch生成profile


**目的と配置**  目的: CIでpatch案を成果物にする。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.ci_patch]
sandbox_mode = "workspace-write"
approval_policy = "never"
web_search = "disabled"

[sandbox_workspace_write]
network_access = false
```


**確認** 
生成patchをartifactとして保存し、人間reviewへ回す。


**落とし穴** 
自動pushやdeployとは直結しない。


### 設定レシピ 027: Windows sandbox profile


**目的と配置**  目的: Windows nativeのsandbox設定を分ける。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.windows_native]
sandbox_mode = "workspace-write"
approval_policy = "on-request"

[profiles.windows_native.windows]
sandbox = "elevated"
sandbox_private_desktop = true
```


**確認** 
Windows上で `/debug-config` と実行結果を確認する。


**落とし穴** 
macOS/Linuxの設定と混同しない。Windows専用sectionへ置く。


### 設定レシピ 028: networkを許可する検証profile


**目的と配置**  目的: 依存取得が必要なsandbox commandだけ検証する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.net_lab]
sandbox_mode = "workspace-write"
approval_policy = "on-request"

[profiles.net_lab.sandbox_workspace_write]
network_access = true
```


**確認** 
package installが必要なタスクだけこのprofileで起動する。


**落とし穴** 
通常開発profileにnetwork_access trueを入れない。MCPやweb searchとは別の概念である。


### 設定レシピ 029: permission profileの考え方


**目的と配置**  目的: filesystem/networkを名前付きで再利用する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
default_permissions = "workspace"

[permissions.workspace.filesystem]
"." = "write"
".env" = "none"

[permissions.workspace.network]
enabled = false
```


**確認** 
使っているCLI versionがこの構造に対応しているかschemaで確認する。


**落とし穴** 
permissions系は管理ポリシーやversion差が出やすい。必ずschemaとdebugで確認する。


### 設定レシピ 030: 外部proxyの管理設定


**目的と配置**  目的: network proxyを使う環境で設定を明示する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[permissions.workspace.network]
enabled = true
proxy_url = "http://127.0.0.1:43128"
admin_url = "http://127.0.0.1:43129"
allow_upstream_proxy = false
```


**確認** 
proxyがlocal loopbackであること、上流proxyを許さないことを確認する。


**落とし穴** 
non-loopback proxyを許す危険設定は避ける。


### 設定レシピ 031: secret防御のAGENTS連携


**目的と配置**  目的: 設定と人間向け規約をそろえる。 配置: `AGENTS.md and config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# .codex/config.toml
[shell_environment_policy]
exclude = ["*_TOKEN", "*_SECRET", "AWS_*", "GITHUB_*"]

# AGENTS.md
## Secrets
- Never open .env, SSH keys, or credential files.
- Ask before using any token-bearing environment variable.
```


**確認** 
`/debug-config` とAGENTS読み込みを確認する。


**落とし穴** 
TOMLだけでは、レビュー観点や禁止事項が人間に伝わりにくい。AGENTS.mdにも書く。


### 設定レシピ 032: ローカルDBへの接続を禁止する


**目的と配置**  目的: 意図しないDB操作を避ける。 配置: `.codex/rules/db.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# .codex/rules/db.rules
prefix_rule(pattern=["psql"], decision="forbidden", reason="Do not access local databases from Codex.")
prefix_rule(pattern=["mysql"], decision="forbidden", reason="Do not access local databases from Codex.")
prefix_rule(pattern=["redis-cli"], decision="prompt", reason="Redis access requires human confirmation.")
```


**確認** 
`codex execpolicy check` でコマンド判定を確認する。


**落とし穴** 
Rulesだけでなく、AGENTS.mdにもDB方針を書く。


---


### 設定レシピ 033: deployコマンドを常にpromptにする


**目的と配置**  目的: 本番影響のあるcommandを承認対象にする。 配置: `.codex/rules/deploy.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
prefix_rule(pattern=["kubectl", "apply"], decision="prompt", reason="Kubernetes changes require human approval.")
prefix_rule(pattern=["terraform", "apply"], decision="prompt", reason="Terraform apply requires human approval.")
prefix_rule(pattern=["gh", "release"], decision="prompt", reason="Release operations require review.")
```


**確認** 
代表commandをcheckし、prompt/forbiddenの判定を見る。


**落とし穴** 
patternが広すぎると通常作業も止まる。運用しながら絞る。


### 設定レシピ 034: 危険な削除をforbiddenにする


**目的と配置**  目的: 誤削除を防ぐ。 配置: `.codex/rules/delete.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
prefix_rule(pattern=["rm", "-rf", "/"], decision="forbidden", reason="Never allow recursive root deletion.")
prefix_rule(pattern=["rm", "-rf", "~"], decision="forbidden", reason="Never allow recursive HOME deletion.")
prefix_rule(pattern=["git", "clean", "-fdx"], decision="prompt", reason="Destructive workspace cleanup requires confirmation.")
```


**確認** 
コマンドのtokenizationが想定通りかcheckする。


**落とし穴** 
rulesはshell展開後の完全な安全装置ではない。sandboxと併用する。


### 設定レシピ 035: Git操作の境界を決める


**目的と配置**  目的: commitやpushを勝手にしない。 配置: `AGENTS.md and .codex/rules/git.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# .codex/rules/git.rules
prefix_rule(pattern=["git", "push"], decision="prompt", reason="Do not push without explicit user instruction.")
prefix_rule(pattern=["git", "commit"], decision="prompt", reason="Commit creation requires explicit instruction.")
```


**確認** 
`git diff` は許可し、commit/pushだけpromptにする。


**落とし穴** 
AGENTS.mdには「ユーザーが明示した場合だけcommit」と書く。


---


## 設定レシピ集 036: MCP定義と接続


### 設定レシピ 036: 承認系のrequirements制約


**目的と配置**  目的: 組織として許すapprovalだけに絞る。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
allowed_approval_policies = ["untrusted", "on-request"]
allowed_sandbox_modes = ["read-only", "workspace-write"]
allowed_web_search_modes = ["disabled", "cached"]
```


**確認** 
ユーザーが `danger-full-access` や `never` を指定したときに弱められないか確認する。


**落とし穴** 
開発速度だけを見てneverを許可しない。例外profileを作るなら管理者承認にする。


### 設定レシピ 037: MCP STDIOの最小定義


**目的と配置**  目的: ローカルMCP serverを起動する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.docs]
enabled = true
command = "docs-server"
args = ["--root", "/Users/me/work/docs"]
startup_timeout_sec = 10
tool_timeout_sec = 60
enabled_tools = ["search", "summarize"]
```


**確認** 
`codex mcp list` とTUIの `/mcp` でserver状態を確認する。


**落とし穴** 
command名がPATH依存だと他の環境で壊れる。project設定ではrepo相対scriptを使う。


### 設定レシピ 038: MCP HTTPの最小定義


**目的と配置**  目的: 共有HTTP MCP serverへ接続する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.issues]
enabled = true
url = "https://mcp.example.internal/issues/mcp"
bearer_token_env_var = "ISSUES_MCP_TOKEN"
startup_timeout_sec = 10
tool_timeout_sec = 45
enabled_tools = ["search_issues", "get_issue"]
```


**確認** 
token環境変数が存在する状態で `codex mcp get issues` を確認する。


**落とし穴** 
bearer tokenの値をTOMLへ書かない。env var名だけを書く。


### 設定レシピ 039: MCPをproject scopedにする


**目的と配置**  目的: repo固有docs serverだけprojectで有効にする。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.repo_docs]
enabled = true
command = "python3"
args = [".codex/mcp/repo_docs_server.py"]
cwd = "/absolute/path/to/repo"
enabled_tools = ["search_repo_docs"]
```


**確認** 
trusted projectでだけ読み込まれることを確認する。


**落とし穴** 
project設定に個人HOME pathを固定しない。実運用ではcwdの扱いをrepo内scriptで安定化する。


### 設定レシピ 040: MCP requiredを使う


**目的と配置**  目的: 必須serverが落ちたまま作業しない。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.design_system]
enabled = true
required = true
url = "https://mcp.example.internal/design/mcp"
bearer_token_env_var = "DESIGN_MCP_TOKEN"
enabled_tools = ["get_component", "search_tokens"]
```


**確認** 
server停止時に起動やresumeがどう失敗するか確認する。


**落とし穴** 
すべてのMCPをrequiredにしない。作業不能になる。


---


### 設定レシピ 041: MCP tool allowlist


**目的と配置**  目的: 危険toolを表示させない。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.github_readonly]
url = "https://mcp.example.internal/github/mcp"
bearer_token_env_var = "GITHUB_MCP_TOKEN"
enabled_tools = ["list_pull_requests", "get_pull_request", "list_issues", "get_issue"]
disabled_tools = ["merge_pull_request", "delete_repository", "create_deployment"]
```


**確認** 
`/mcp` でtool一覧を見て、許可toolだけが出るか確認する。


**落とし穴** 
enabled_toolsを省略すると広すぎる場合がある。read-only用途はallowlistを使う。


### 設定レシピ 042: MCP env varsを転送する


**目的と配置**  目的: secret値を設定ファイルへ書かずに渡す。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.local_search]
command = "node"
args = ["/Users/me/.codex/mcp/local-search.js"]
env_vars = ["LOCAL_SEARCH_TOKEN"]
env = { "LOG_LEVEL" = "warn" }
```


**確認** 
server側で環境変数が読めることを確認する。


**落とし穴** 
envは値を直書きするためsecretには使わない。secretはenv_varsかbearer_token_env_varへ寄せる。


### 設定レシピ 043: MCP OAuth scopes


**目的と配置**  目的: OAuth serverで必要scopeを明示する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.calendar]
url = "https://mcp.example.com/calendar/mcp"
scopes = ["calendar:read"]
oauth_resource = "https://calendar.example.com/"
enabled_tools = ["list_events", "get_event"]
```


**確認** 
`codex mcp login calendar` でOAuth flowを確認する。


**落とし穴** 
write scopeを最初から要求しない。readから始める。


### 設定レシピ 044: MCP timeoutを短くする


**目的と配置**  目的: 重いserverで待ちすぎない。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.slow_docs]
command = "slow-docs-server"
startup_timeout_sec = 5
tool_timeout_sec = 20
enabled_tools = ["search"]
```


**確認** 
検索失敗時のログを見てtimeoutを調整する。


**落とし穴** 
timeoutを短くしすぎると有用な検索も失敗する。server別に設定する。


### 設定レシピ 045: MCP HTTP headerを追加する


**目的と配置**  目的: 社内gatewayを通す。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.internal_docs]
url = "https://gateway.example.internal/mcp/docs"
http_headers = { "X-Client" = "codex-cli" }
env_http_headers = { "X-Request-Token" = "DOCS_GATEWAY_TOKEN" }
enabled_tools = ["search", "fetch"]
```


**確認** 
環境変数がないとheaderが付かないことを確認する。


**落とし穴** 
静的headerにsecretを入れない。


### 設定レシピ 046: MCPを無効化する


**目的と配置**  目的: 定義は残しつつ一時停止する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.docs]
enabled = false
command = "docs-server"
args = ["--root", "/Users/me/work/docs"]
```


**確認** 
`codex mcp list` でdisabled表示を確認する。


**落とし穴** 
削除と無効化を使い分ける。障害切り分けではenabled=falseが便利。


### 設定レシピ 047: MCP CLIで追加する


**目的と配置**  目的: 手編集せずにSTDIO serverを登録する。 配置: `CLI command`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
codex mcp add context7 -- npx -y @upstash/context7-mcp
codex mcp list
codex mcp get context7
```


**確認** 
生成された `config.toml` の該当sectionを確認する。


**落とし穴** 
CLI追加後も、tool allowlistやtimeoutは必要に応じて手で補う。


### 設定レシピ 048: MCP login logout運用


**目的と配置**  目的: OAuth tokenを明示的に管理する。 配置: `CLI command`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
codex mcp login calendar
codex mcp get calendar
codex mcp logout calendar
```


**確認** 
共有端末ではlogoutを運用手順に入れる。


**落とし穴** 
OAuth tokenの保存場所や期限はserver実装にも依存する。


---


### 設定レシピ 049: 社内docs MCPのproject定義


**目的と配置**  目的: repoの設計資料だけ検索する。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.repo_knowledge]
command = "python3"
args = [".codex/mcp/repo_knowledge.py", "--index", ".codex/index"]
enabled_tools = ["search_design_notes", "get_runbook"]
startup_timeout_sec = 15
tool_timeout_sec = 60
```


**確認** 
repoをcloneした開発者がscriptとindexを再現できるか確認する。


**落とし穴** 
index生成手順をAGENTS.mdやREADMEへ書く。


### 設定レシピ 050: issue tracker MCPをread onlyにする


**目的と配置**  目的: チケットを読むだけに限定する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.tracker]
url = "https://mcp.example.internal/tracker/mcp"
bearer_token_env_var = "TRACKER_TOKEN"
enabled_tools = ["search_tickets", "get_ticket", "list_comments"]
disabled_tools = ["create_ticket", "update_ticket", "delete_ticket"]
```


**確認** 
TUIの `/mcp` でwrite系toolが出ないか確認する。


**落とし穴** 
tool名はserver実装で変わる。実際のtool一覧を見てallowlistを更新する。


### 設定レシピ 051: observability MCPを最小化する


**目的と配置**  目的: ログ調査だけ使う。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.observability]
url = "https://mcp.example.internal/observability/mcp"
bearer_token_env_var = "OBS_TOKEN"
enabled_tools = ["search_logs", "get_trace", "list_dashboards"]
tool_timeout_sec = 30
```


**確認** 
検索queryに個人情報やsecretが含まれないようAGENTS.mdにも注意を書く。


**落とし穴** 
production logへの接続は情報管理の対象である。


### 設定レシピ 052: database MCPのread only設計


**目的と配置**  目的: DBへ直接shell接続させず、read-only MCPに限定する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.analytics_ro]
url = "https://mcp.example.internal/analytics/mcp"
bearer_token_env_var = "ANALYTICS_RO_TOKEN"
enabled_tools = ["describe_table", "run_readonly_query"]
tool_timeout_sec = 20
```


**確認** 
server側でもwrite queryを拒否する。


**落とし穴** 
client allowlistだけに依存しない。MCP server側の権限制御が本体である。


### 設定レシピ 053: MCPとsubagentを分ける


**目的と配置**  目的: 外部toolを使う役割だけMCPを持たせる。 配置: `.codex/agents/docs-researcher.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "docs-researcher"
description = "Search official and internal docs, then return citations and uncertainty."
developer_instructions = "Use MCP docs tools only when needed. Do not edit files."
sandbox_mode = "read-only"

[mcp_servers.docs]
url = "https://mcp.example.internal/docs/mcp"
bearer_token_env_var = "DOCS_MCP_TOKEN"
enabled_tools = ["search", "fetch"]
```


**確認** 
親agentから明示的にこのagentをspawnして、成果物形式を固定する。


**落とし穴** 
すべてのagentへ同じMCPを持たせない。


### 設定レシピ 054: MCP identityをrequirementsで制約する


**目的と配置**  目的: 許可されたserverだけを使わせる。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.docs.identity]
url = "https://mcp.example.internal/docs/mcp"

[mcp_servers.repo_knowledge.identity]
command = "python3"
```


**確認** 
mismatchしたURLやcommandが無効化されることを確認する。


**落とし穴** 
server名とidentityの両方が合う必要がある設計にする。


### 設定レシピ 055: MCP失敗時の代替手順を書く


**目的と配置**  目的: server停止でも作業が止まらないようにする。 配置: `AGENTS.md`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
## MCP alternate route
- If repo_knowledge MCP is unavailable, inspect docs/ and runbooks/ manually.
- If tracker MCP is unavailable, ask the user for the issue URL or summary.
- Do not guess production incidents without logs or issue context.
```


**確認** 
MCP障害時にCodexが推測で進まないかを見る。


**落とし穴** 
required=trueのserverにはalternate routeが効かない。必須か任意かを分ける。


### 設定レシピ 056: MCP tool実行をHooksで監査する


**目的と配置**  目的: MCP tool利用の記録や制限を補助する。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.PreToolUse]]
matcher = "^MCP"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/check_mcp_tool.py"
timeout = 10
statusMessage = "Checking MCP tool policy"
```


**確認** 
matcher名は実際のイベントpayloadに合わせて調整する。


**落とし穴** 
hook側でsecretをlog出力しない。


---


### 設定レシピ 057: MCP serverをremote executorで試す


**目的と配置**  目的: localではなくremote環境でSTDIO serverを動かす。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[mcp_servers.remote_docs]
command = "docs-server"
args = ["--mode", "remote"]
experimental_environment = "remote"
enabled_tools = ["search"]
```


**確認** 
対応している環境か確認し、失敗時はlocal STDIOへ戻す。


**落とし穴** 
experimental機能なのでprofileに閉じ込める。


### 設定レシピ 058: PreToolUse hookの最小形


**目的と配置**  目的: Bash実行前にpolicy scriptを走らせる。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/pre_tool_use.py"
timeout = 30
statusMessage = "Checking Bash command"
```


**確認** 
hook scriptが0/非0終了でどう扱われるか低リスクcommandで確認する。


**落とし穴** 
hook scriptをrepoに入れる場合、trusted project前提であることを理解する。


### 設定レシピ 059: PostToolUse hookでログ要約


**目的と配置**  目的: コマンド実行後に成果を記録する。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.PostToolUse]]
matcher = "^Bash$"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/post_tool_use_summary.py"
timeout = 20
statusMessage = "Summarizing command result"
```


**確認** 
失敗したhookが作業全体を妨げないようtimeoutを短くする。


**落とし穴** 
post hookはlogに機微情報を書かない。


### 設定レシピ 060: UserPromptSubmit hook


**目的と配置**  目的: ユーザーpromptを送る前に注意喚起する。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.UserPromptSubmit]]
matcher = ".*"
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "python3 .codex/hooks/check_prompt_for_secrets.py"
timeout = 10
statusMessage = "Checking prompt"
```


**確認** 
過検知しすぎないか確認する。


**落とし穴** 
prompt内容を外部送信しない。local scriptで完結させる。


---


## 設定レシピ集 061: Hooks、Rules、Subagents


### 設定レシピ 061: SessionStart hook


**目的と配置**  目的: 起動時にrepo状態を確認する。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.SessionStart]]
matcher = ".*"
[[hooks.SessionStart.hooks]]
type = "command"
command = "python3 .codex/hooks/session_start.py"
timeout = 15
statusMessage = "Checking workspace state"
```


**確認** 
未commit差分やbranch名を検査する用途に使う。


**落とし穴** 
起動のたびに重い処理を走らせない。


### 設定レシピ 062: Stop hook


**目的と配置**  目的: セッション終了時のcleanupを行う。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.Stop]]
matcher = ".*"
[[hooks.Stop.hooks]]
type = "command"
command = "python3 .codex/hooks/stop_cleanup.py"
timeout = 15
statusMessage = "Cleaning temporary files"
```


**確認** 
background process停止やtmp削除だけに限定する。


**落とし穴** 
成果物を勝手に消さない。


### 設定レシピ 063: PermissionRequest hook


**目的と配置**  目的: 承認要求時に追加チェックする。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[hooks]
[[hooks.PermissionRequest]]
matcher = ".*"
[[hooks.PermissionRequest.hooks]]
type = "command"
command = "python3 .codex/hooks/permission_request_guard.py"
timeout = 10
statusMessage = "Reviewing permission request"
```


**確認** 
承認payloadにどの情報が来るか確認してから実装する。


**落とし穴** 
hookが誤判定すると承認flowが壊れる。段階導入する。


### 設定レシピ 064: managed hooksのrequirements


**目的と配置**  目的: 組織でhookを強制する。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
hooks = true

[hooks]
managed_dir = "/enterprise/hooks"
windows_managed_dir = 'C:'

[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 /enterprise/hooks/pre_tool_use_policy.py"
timeout = 30
statusMessage = "Checking managed Bash command"
```


**確認** 
managed_dirが存在し、scriptが配布済みであることを確認する。


**落とし穴** 
requirementsはscriptを配布しない。MDMなどで別途配る必要がある。


---


### 設定レシピ 065: Hooksをfeature flagで止める


**目的と配置**  目的: 障害時にhooksを切り戻す。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
hooks = false
```


**確認** 
hooks由来の障害を切り分けるときだけ使う。


**落とし穴** 
requirementsで強制されている場合、ユーザー側で弱められない。


### 設定レシピ 066: Rulesの最小allow


**目的と配置**  目的: 安全な読み取りcommandを明示する。 配置: `.codex/rules/read.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
prefix_rule(pattern=["git", "status"], decision="allow", reason="Read-only git status is safe.")
prefix_rule(pattern=["git", "diff"], decision="allow", reason="Read-only diff inspection is safe.")
prefix_rule(pattern=["ls"], decision="allow", reason="Directory listing is safe.")
```


**確認** 
allowを書きすぎず、よく使う読み取りから始める。


**落とし穴** 
allowはrequirementsでは使えない場合がある。管理設定ではprompt/forbidden中心にする。


### 設定レシピ 067: Rulesでnpm installをprompt


**目的と配置**  目的: 依存追加やdownloadを確認する。 配置: `.codex/rules/package.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
prefix_rule(pattern=["npm", "install"], decision="prompt", reason="Dependency installation may modify lockfiles or download packages.")
prefix_rule(pattern=["pnpm", "add"], decision="prompt", reason="Dependency changes require review.")
prefix_rule(pattern=["pip", "install"], decision="prompt", reason="Python package installation requires confirmation.")
```


**確認** 
install系commandの判定をcheckする。


**落とし穴** 
test script内部でinstallする場合もある。AGENTS.mdで禁止する。


### 設定レシピ 068: Rulesでcurl pipe shを禁止


**目的と配置**  目的: 危険なinstall patternを防ぐ。 配置: `.codex/rules/network.rules`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
prefix_rule(pattern=["sh", "-c"], decision="prompt", reason="Shell string execution requires review.")
prefix_rule(pattern=["curl"], decision="prompt", reason="Network download requires review.")
prefix_rule(pattern=["wget"], decision="prompt", reason="Network download requires review.")
```


**確認** 
完全禁止ではなくpromptから始めると運用しやすい。


**落とし穴** 
shell文字列の内容まではprefixだけで完全判定できない。


### 設定レシピ 069: custom agentの最小file


**目的と配置**  目的: 一つの役割を一つのTOMLで定義する。 配置: `.codex/agents/reviewer.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "reviewer"
description = "Review code for correctness, security, and missing tests."
developer_instructions = "Do not edit files. Return findings with severity, evidence, and suggested fixes."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認** 
Codexに明示的にreviewer subagentを使うよう依頼して動作を見る。


**落とし穴** 
name、description、developer_instructionsは必須として扱う。


### 設定レシピ 070: worker agentをworkspace writeにする


**目的と配置**  目的: 実装修正用agentを定義する。 配置: `.codex/agents/worker.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "worker"
description = "Implement small, well-scoped code changes and run tests."
developer_instructions = "Modify only files relevant to the assigned task. Summarize changed files and test results."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認** 
親agentに範囲を渡してspawnさせる。


**落とし穴** 
workerへMCPやdanger権限を過剰に付けない。


### 設定レシピ 071: explorer agentをread heavyにする


**目的と配置**  目的: 大きなrepoの調査専門agentを作る。 配置: `.codex/agents/explorer.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "explorer"
description = "Explore code paths and return maps, not patches."
developer_instructions = "Read files, identify entry points, dependencies, and risks. Do not edit files."
sandbox_mode = "read-only"
web_search = "disabled"
```


**確認** 
成果物形式を「入口、関連file、未確認点」に固定する。


**落とし穴** 
調査agentが修正まで始めないよう明記する。


### 設定レシピ 072: docs researcher agent


**目的と配置**  目的: MCPでdocsを確認するagentを分離する。 配置: `.codex/agents/docs-researcher.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "docs-researcher"
description = "Use approved docs MCP tools to verify external or internal specifications."
developer_instructions = "Return citations, dates, and uncertainty. Do not change repository files."
sandbox_mode = "read-only"

[mcp_servers.docs]
url = "https://mcp.example.internal/docs/mcp"
bearer_token_env_var = "DOCS_MCP_TOKEN"
enabled_tools = ["search", "fetch"]
```


**確認** 
MCP利用をこのagentに寄せる。


**落とし穴** 
親agentが未確認情報を推測で埋めないようにする。


---


### 設定レシピ 073: agent concurrencyを抑える


**目的と配置**  目的: subagentの並列数と深さを制限する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[agents]
max_threads = 4
max_depth = 1
job_max_runtime_seconds = 1200
interrupt_message = true
```


**確認** 
複数spawn時に上限が効くか確認する。


**落とし穴** 
max_depthを増やすと統合が難しくなる。最初は1にする。


### 設定レシピ 074: agent roleをconfigから参照する


**目的と配置**  目的: role definitionを別fileへ逃がす。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[agents.reviewer]
description = "Find correctness, security, and test risks in code."
config_file = "./agents/reviewer.toml"
nickname_candidates = ["Athena", "Ada"]
```


**確認** 
relative pathがconfig.toml基準で解決されることを確認する。


**落とし穴** 
agent fileとinline定義の責務を混ぜすぎない。


### 設定レシピ 075: PR reviewer agent


**目的と配置**  目的: PRレビュー専用の出力形式を固定する。 配置: `.codex/agents/pr-reviewer.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "pr-reviewer"
description = "Review pull request diffs and report actionable findings."
developer_instructions = "Return: summary, high-risk findings, test gaps, security concerns, and suggested review comments. Do not edit files."
sandbox_mode = "read-only"
approval_policy = "on-request"
```


**確認** 
親に「pr-reviewerで差分を見て」と明示する。


**落とし穴** 
レビューcommentを実際に投稿するMCP toolは別途allowlistで制限する。


### 設定レシピ 076: migration worker agent


**目的と配置**  目的: 大規模移行の分担単位を作る。 配置: `.codex/agents/migration-worker.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "migration-worker"
description = "Perform one bounded migration slice and run local tests."
developer_instructions = "Touch only assigned directories. Return changed files, tests, and blockers."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認** 
一回のspawnで担当dirを明示する。


**落とし穴** 
複数workerが同じfileを編集しないよう親が割り振る。


### 設定レシピ 077: UI debugger agent


**目的と配置**  目的: UI再現とスクリーンショット読解を分離する。 配置: `.codex/agents/ui-debugger.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "ui-debugger"
description = "Inspect screenshots, UI errors, and browser logs."
developer_instructions = "Prefer diagnosis and reproduction steps. Do not change files unless explicitly assigned."
sandbox_mode = "read-only"
tools_view_image = true
```


**確認** 
画像入力とconsole logを渡して分析させる。


**落とし穴** 
UI修正はworker agentへ渡すと責務が明確になる。


### 設定レシピ 078: security reviewer agent


**目的と配置**  目的: セキュリティ観点を独立させる。 配置: `.codex/agents/security-reviewer.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "security-reviewer"
description = "Review changes for security regressions and secret handling risks."
developer_instructions = "Do not exploit. Report risk, evidence, impact, and safe remediation. Never read secrets."
sandbox_mode = "read-only"
web_search = "disabled"
```


**確認** 
PRや差分reviewで使う。


**落とし穴** 
脆弱性検証の範囲は安全ポリシーと社内規定に従う。


### 設定レシピ 079: agentごとのsandbox override


**目的と配置**  目的: reviewerはread-only、workerはwriteに分ける。 配置: `.codex/agents/*.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# reviewer.toml
sandbox_mode = "read-only"
approval_policy = "on-request"

# worker.toml
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認** 
各agentのeffective configを確認する。


**落とし穴** 
親sessionの設定を無条件に継承すると役割が曖昧になる。


### 設定レシピ 080: subagent成果物テンプレート


**目的と配置**  目的: 統合しやすい出力を指定する。 配置: `.codex/agents/reviewer.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
developer_instructions = """
Return exactly these sections:
1. Scope inspected
2. Findings by severity
3. Evidence with file paths
4. Test gaps
5. Unknowns and assumptions
Do not edit files.
"""
```


**確認** 
親agentが複数agentの結果を並べやすくなる。


**落とし穴** 
自由作文にすると、比較や統合が難しくなる。


---


### 設定レシピ 081: agentでweb searchを無効化する


**目的と配置**  目的: 内部コードreviewでは外部情報を入れない。 配置: `.codex/agents/reviewer.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
name = "reviewer"
description = "Internal code reviewer."
developer_instructions = "Use repository evidence only."
web_search = "disabled"
sandbox_mode = "read-only"
```


**確認** 
外部情報が必要なときはdocs-researcherへ分ける。


**落とし穴** 
reviewerが外部情報で誤った前提を持ち込まないようにする。


### 設定レシピ 082: agent runtimeを短くする


**目的と配置**  目的: 長時間agentを止める。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[agents]
job_max_runtime_seconds = 600
max_threads = 3
max_depth = 1
```


**確認** 
大きすぎるタスクは分割してspawnする。


**落とし穴** 
timeoutが短すぎると調査が中途半端になる。


### 設定レシピ 083: project root markerを設定する


**目的と配置**  目的: monorepoでroot検出を安定させる。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
project_root_markers = [".git", "pnpm-workspace.yaml", "package.json"]
```


**確認** 
`/debug-config` でproject rootが想定通りか確認する。


**落とし穴** 
markerを増やしすぎると深いsubdirがroot扱いになる可能性がある。


### 設定レシピ 084: AGENTS alternate route filename


**目的と配置**  目的: AGENTS.md以外の社内文書も読む。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
project_doc_alternate route_filenames = ["AI_GUIDE.md", "DEVELOPMENT.md"]
project_doc_max_bytes = 200000
```


**確認** 
AGENTS.mdがないdirでalternate routeが使われるか確認する。


**落とし穴** 
巨大文書を丸ごと入れない。max bytesを決める。


### 設定レシピ 085: AGENTS overrideの使い方


**目的と配置**  目的: 階層指示を明示的に上書きする。 配置: `AGENTS.override.md`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# AGENTS.override.md
For this experimental branch, prefer the new build command:
- pnpm turbo run test --filter=@app/web
Do not use the legacy npm scripts in this directory.
```


**確認** 
該当dirで指示が後勝ちになるか確認する。


**落とし穴** 
overrideを常用すると規約が見えにくくなる。期限や理由を書く。


### 設定レシピ 086: monorepoのproject設定


**目的と配置**  目的: serviceごとにagentとrulesを分ける。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
project_root_markers = ["pnpm-workspace.yaml", ".git"]

[agents.api-reviewer]
config_file = "./agents/api-reviewer.toml"

[agents.web-reviewer]
config_file = "./agents/web-reviewer.toml"
```


**確認** 
サービス別AGENTS.mdとagentを対応させる。


**落とし穴** 
rootの設定に全サービス固有の詳細を書きすぎない。


### 設定レシピ 087: statusline設定


**目的と配置**  目的: TUI下部に必要な情報を出す。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[tui]
status_line = ["model", "context", "git_branch", "tokens", "codex_version"]
```


**確認** 
TUIの `/statusline` でも変更できる。


**落とし穴** 
表示項目を増やしすぎると狭い端末で読みにくい。


### 設定レシピ 088: terminal title設定


**目的と配置**  目的: 複数タブでprojectやtaskを見分ける。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[tui]
terminal_title = ["app_name", "project", "git_branch", "model", "task_progress"]
```


**確認** 
`/title` で対話的に変更できる。


**落とし穴** 
terminal multiplexerのtitle挙動は環境差がある。


---


### 設定レシピ 089: keymapの上書き


**目的と配置**  目的: TUI shortcutをチームや個人の好みに合わせる。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[tui.keymap]
copy_latest_response = "ctrl-o"
open_command_palette = ["ctrl-p", "ctrl-k"]
```


**確認** 
`/keymap` で現在のbindingを見る。


**落とし穴** 
空配列でunbindする場合、意図をコメントに残す。


### 設定レシピ 090: alt screenを無効化する


**目的と配置**  目的: tmuxやzellijのscrollback問題を避ける。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[tui]
alt_screen = "never"
```


**確認** 
`--no-alt-screen` でも一時的に指定できる。


**落とし穴** 
fullscreen体験は変わる。端末ごとにprofile化する。


### 設定レシピ 091: vim modeを有効化する


**目的と配置**  目的: composerでVim編集を使う。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[tui]
composer_editor = "vim"
vim_default_mode = "insert"
```


**確認** 
手元のCLI versionが対応しているかchangelogとhelpで確認する。


**落とし穴** 
Vim keymapは新しめの機能のため、version差を考慮する。


### 設定レシピ 092: feature flagのprofile保存


**目的と配置**  目的: profileごとに機能を切り替える。 配置: `CLI command`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
codex --profile lab features enable goals
codex --profile lab features disable shell_snapshot
```


**確認** 
変更が `[profiles.lab.features]` へ入ったか確認する。


**落とし穴** 
rootのfeaturesとprofileのfeaturesを混同しない。


### 設定レシピ 093: goals featureを有効化する


**目的と配置**  目的: TUIの `/goal` を使う。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
goals = true
```


**確認** 
`/experimental` または `/goal` で利用可能か確認する。


**落とし穴** 
goalは実験的機能。成功条件と停止条件をprompt側で明示する。


### 設定レシピ 094: undoを有効化する


**目的と配置**  目的: turnごとのghost snapshotで戻しやすくする。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
undo = true
```


**確認** 
実際に差分作成後、undo操作の挙動を低リスクrepoで確認する。


**落とし穴** 
Git管理外の巨大fileや生成物の扱いに注意する。


### 設定レシピ 095: shell snapshotを切る


**目的と配置**  目的: 環境snapshotの影響を切り分ける。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
shell_snapshot = false
```


**確認** 
shell環境の変化が反映されるか確認する。


**落とし穴** 
通常は速度面で有効な場合がある。切り分け用途にする。


---


## 設定レシピ集 096: Project、TUI、Feature、Enterprise


### 設定レシピ 096: apps connectorを無効化する


**目的と配置**  目的: 外部connectorを使わない環境にする。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
apps = false
connectors = false

[apps._default]
enabled = false
```


**確認** 
`/debug-config` でapps関連が無効か見る。


**落とし穴** 
Appsは外部サービス権限に関わるため、必要なprofileだけで有効化する。


---


### 設定レシピ 097: apps tool承認を厳しくする


**目的と配置**  目的: connector toolの自動実行を避ける。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[apps._default]
enabled = true
destructive_enabled = false
open_world_enabled = false

[apps.github]
default_tools_approval_mode = "prompt"
default_tools_enabled = true
```


**確認** 
各appのtool一覧と承認挙動を確認する。


**落とし穴** 
destructive/open world toolは明示的に扱う。


### 設定レシピ 098: model provider追加の骨格


**目的と配置**  目的: OpenAI互換providerを定義する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[model_providers.local_gateway]
base_url = "http://127.0.0.1:8080/v1"
env_key = "LOCAL_GATEWAY_API_KEY"

[profiles.local_gateway]
model_provider = "local_gateway"
model = "gpt-compatible-model"
```


**確認** 
providerのauthやmodel対応を別profileで検証する。


**落とし穴** 
通常OpenAI profileと混ぜない。providerごとのtool対応差に注意する。


### 設定レシピ 099: auth credential storeを指定する


**目的と配置**  目的: 認証情報の保存方式を明示する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
cli_auth_credentials_store = "keyring"
```


**確認** 
keyringが使えない環境では失敗する。必要ならautoを使う。


**落とし穴** 
共有端末ではlogout運用も必要である。


### 設定レシピ 100: ephemeral認証profile


**目的と配置**  目的: 一時sessionだけcredentialを使う。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[profiles.ephemeral]
cli_auth_credentials_store = "ephemeral"
history = { persistence = "none" }
```


**確認** 
session終了後にcredentialが残らないことを確認する。


**落とし穴** 
再起動のたびに認証が必要になる。


### 設定レシピ 101: analyticsを無効化する


**目的と配置**  目的: profileごとにanalytics設定を変える。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[analytics]
enabled = false

[profiles.default.analytics]
enabled = false
```


**確認** 
`/debug-config` でanalytics設定を確認する。


**落とし穴** 
組織ポリシーがある場合はrequirementsや管理設定が優先される場合がある。


### 設定レシピ 102: debug config lockfile


**目的と配置**  目的: effective configを固定・再現する。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[debug.config_lockfile]
export_dir = "/Users/me/.codex/config-locks"
save_fields_resolved_from_model_catalog = true
allow_codex_version_mismatch = false
```


**確認** 
debug用途に限定して使う。


**落とし穴** 
lockfileは設定の検査用であり、通常運用へ乱用しない。


### 設定レシピ 103: requirementsでweb searchを制限


**目的と配置**  目的: 組織としてlive検索を禁止する。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
allowed_web_search_modes = ["disabled", "cached"]

[features]
web_search_request = false
```


**確認** 
ユーザーが `--search` を付けた場合の挙動を確認する。


**落とし穴** 
業務上liveが必要なチームには例外の運用を決める。


### 設定レシピ 104: requirementsでfeatureを固定


**目的と配置**  目的: 危険機能や未承認機能を無効化する。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[features]
browser_use = false
computer_use = false
in_app_browser = false
apps = false
```


**確認** 
`/debug-config` でrequirements由来の制約として見えるか確認する。


**落とし穴** 
機能名はcanonical keyを使う。version差があるためschema確認が必要。


---


### 設定レシピ 105: requirementsでdeny read


**目的と配置**  目的: 全ユーザーでsecret pathを読ませない。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
deny_read = ["**/.env", "**/.env.*", "**/secrets/**", "**/*_rsa", "**/*_ed25519"]
```


**確認** 
ユーザーconfigで弱められないことを検証する。


**落とし穴** 
globの効き方やplatform差を確認する。


### 設定レシピ 106: requirementsでmanaged rule


**目的と配置**  目的: 危険commandを組織でpromptまたはforbiddenにする。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[rules]
"terraform apply" = { decision = "prompt", reason = "Infrastructure changes require approval." }
"kubectl delete" = { decision = "forbidden", reason = "Do not delete Kubernetes resources through Codex." }
```


**確認** 
公式schemaと実装versionに合う形式で確認する。


**落とし穴** 
requirements rulesではallowではなくprompt/forbidden中心にする。


### 設定レシピ 107: remote sandbox config


**目的と配置**  目的: hostnameごとにsandbox許可値を変える。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
[[remote_sandbox_config]]
hostname_patterns = ["devbox-*", "ci-*" ]
allowed_sandbox_modes = ["read-only", "workspace-write"]

[[remote_sandbox_config]]
hostname_patterns = ["prod-*" ]
allowed_sandbox_modes = ["read-only"]
```


**確認** 
host名がどのentryにmatchするか確認する。


**落とし穴** 
production系hostではwriteを許さない。


### 設定レシピ 108: managed guardian policy


**目的と配置**  目的: 自動承認reviewに組織方針を入れる。 配置: `requirements.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
guardian_policy_config = """
Deny requests that may expose credentials, deploy to production, or alter infrastructure.
Prefer explicit human approval for package installation, network downloads, and database access.
"""
```


**確認** 
auto review利用時にpolicyが反映されるか確認する。


**落とし穴** 
空文字や過度に長いpolicyで読みづらくしない。


### 設定レシピ 109: status診断テンプレート


**目的と配置**  目的: 設定確認を標準手順にする。 配置: `AGENTS.md`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
## Codex config diagnostics
When config behavior is surprising:
1. Run /debug-config.
2. Check project trust state.
3. Check active profile.
4. Run codex features list.
5. Run codex mcp list if MCP is involved.
6. Run codex execpolicy check for command policy issues.
```


**確認** 
新メンバーが同じ手順で原因を切り分けられる。


**落とし穴** 
口頭手順にせず文書化する。


### 設定レシピ 110: チーム共有テンプレート


**目的と配置**  目的: 設定変更PRに説明を付ける。 配置: `docs/codex-config-change.md`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# Codex config change
- Purpose:
- Files changed:
- New permissions:
- MCP servers affected:
- Hooks or rules affected:
- Test command:
- Rollback:
- Owner:
```


**確認** 
設定変更をコード変更と同じようにreviewする。


**落とし穴** 
MCPやHooksの変更は権限変更として扱う。


### 設定レシピ 111: ロールバック手順を設定に近く書く


**目的と配置**  目的: 失敗時にすぐ戻せるようにする。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
# Experimental: docs MCP for release notes.
# Owner: docs-platform team.
# Rollback: set enabled=false or remove this table.
[mcp_servers.release_docs]
enabled = true
url = "https://mcp.example.internal/release-docs/mcp"
bearer_token_env_var = "RELEASE_DOCS_TOKEN"
enabled_tools = ["search", "fetch"]
```


**確認** 
障害時にenabled=falseで戻せることを確認する。


**落とし穴** 
コメントなしのexperimental設定は後から意図が分からなくなる。


### 設定レシピ 112: 完全な個人設定テンプレート


**目的と配置**  目的: 個人用の出発点を作る。 配置: `~/.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
#:schema https://developers.openai.com/codex/config-schema.json
model = "gpt-5.5"
model_provider = "openai"
personality = "pragmatic"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
log_dir = "/Users/me/.codex/logs"

[features]
fast_mode = true
multi_agent = true
hooks = true
shell_snapshot = true
unified_exec = true

[sandbox_workspace_write]
writable_roots = []
network_access = false

[shell_environment_policy]
inherit = "core"
exclude = ["*_TOKEN", "*_SECRET", "AWS_*", "GITHUB_*"]

[agents]
max_threads = 4
max_depth = 1
job_max_runtime_seconds = 1200
```


**確認** 
schema対応エディタで補完と診断を使う。


**落とし穴** 
このテンプレートをそのまま全員へ強制しない。個人差がある。


---


### 設定レシピ 113: 完全なproject設定テンプレート


**目的と配置**  目的: repo専用設定の出発点を作る。 配置: `.codex/config.toml`。まずこの断片だけを追加し、`/debug-config` または関連CLIで有効値を確認する。


```
project_root_markers = [".git", "pnpm-workspace.yaml"]
project_doc_alternate route_filenames = ["AI_GUIDE.md", "DEVELOPMENT.md"]
project_doc_max_bytes = 200000
web_search = "disabled"

[agents.pr-reviewer]
config_file = "./agents/pr-reviewer.toml"
description = "Review PR diffs for this repository."

[agents.migration-worker]
config_file = "./agents/migration-worker.toml"
description = "Perform bounded migration slices."

[mcp_servers.repo_docs]
enabled = true
command = "python3"
args = [".codex/mcp/repo_docs.py"]
enabled_tools = ["search", "fetch"]
startup_timeout_sec = 10
tool_timeout_sec = 45

[hooks]
[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/pre_tool_use.py"
timeout = 20
```


**確認** 
trusted projectで読み込まれること、untrustedでは読まれないことを確認する。


**落とし穴** 
project設定には個人のabsolute pathやsecretを書かない。


---


## 反例から学ぶ設定の書き方

設定は正しい値を知るだけでなく、悪い例を見ておくと事故が減る。ここでは、実務で避けたい書き方と修正版を並べる。

### 反例1: 個人pathとsecretをproject設定へ入れる


```
# 悪い例: .codex/config.toml
[mcp_servers.github]
url = "https://mcp.example.internal/github/mcp"
bearer_token = "ghp_xxx_actual_secret_xxx"
command = "/Users/alice/local/mcp-server"
```


```
# よい例: .codex/config.toml
[mcp_servers.github]
url = "https://mcp.example.internal/github/mcp"
bearer_token_env_var = "GITHUB_MCP_TOKEN"
enabled_tools = ["list_pull_requests", "get_pull_request"]
```


### 反例2: 実験機能をrootで常時ONにする


```
# 悪い例
[features]
goals = true
apps = true
browser_use = true
computer_use = true
```


```
# よい例
[profiles.lab.features]
goals = true
apps = true

[profiles.default.features]
goals = false
apps = false
```


### 反例3: Hooksのmatcherが広すぎる


```
# 悪い例: すべてのtoolに重いhookがかかる
[[hooks.PreToolUse]]
matcher = ".*"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/slow_policy.py"
timeout = 120
```


```
# よい例: Bashだけ、timeout短め、status明示
[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/bash_policy.py"
timeout = 20
statusMessage = "Checking Bash policy"
```


### 反例4: requirementsを過剰に縛る


```
# 悪い例: すべてread-onlyだけにして開発作業が止まる
allowed_sandbox_modes = ["read-only"]
allowed_approval_policies = ["untrusted"]
allowed_web_search_modes = ["disabled"]
```


```
# よい例: writeは許すがdangerとneverを抑える
allowed_sandbox_modes = ["read-only", "workspace-write"]
allowed_approval_policies = ["untrusted", "on-request"]
allowed_web_search_modes = ["disabled", "cached"]
```


---


## 完成テンプレート集

ここでは、断片ではなく、用途別の完成形を載せる。実際にはそのまま貼るのではなく、不要なMCP、Hooks、profileを削ってから使う。

### テンプレートA: 個人の安全な既定値


```
#:schema https://developers.openai.com/codex/config-schema.json
model = "gpt-5.5"
model_provider = "openai"
personality = "pragmatic"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
log_dir = "/Users/me/.codex/logs"

[features]
fast_mode = true
multi_agent = true
hooks = true
shell_snapshot = true
unified_exec = true
undo = false

[sandbox_workspace_write]
writable_roots = []
network_access = false
exclude_tmpdir_env_var = false
exclude_slash_tmp = false

[shell_environment_policy]
inherit = "core"
ignore_default_excludes = false
exclude = ["*_TOKEN", "*_SECRET", "AWS_*", "GITHUB_*", "AZURE_*"]
set = { "CI" = "1" }

[agents]
max_threads = 4
max_depth = 1
job_max_runtime_seconds = 1200
```


### テンプレートB: 研究・仕様確認profile


```
[profiles.research]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "live"
model_reasoning_effort = "high"

[profiles.research.features]
multi_agent = true

[mcp_servers.official_docs]
url = "https://mcp.example.internal/official-docs/mcp"
bearer_token_env_var = "DOCS_MCP_TOKEN"
enabled_tools = ["search", "fetch"]
startup_timeout_sec = 10
tool_timeout_sec = 60
```


### テンプレートC: repo固有の成熟構成


```
# .codex/config.toml
project_root_markers = [".git", "pnpm-workspace.yaml"]
project_doc_alternate route_filenames = ["AI_GUIDE.md", "DEVELOPMENT.md"]
project_doc_max_bytes = 200000
web_search = "disabled"

[features]
hooks = true
multi_agent = true

[agents]
max_threads = 4
max_depth = 1
job_max_runtime_seconds = 1200

[agents.pr-reviewer]
config_file = "./agents/pr-reviewer.toml"
description = "Review PR diffs."

[agents.docs-researcher]
config_file = "./agents/docs-researcher.toml"
description = "Search internal docs via MCP."

[mcp_servers.repo_docs]
enabled = true
command = "python3"
args = [".codex/mcp/repo_docs.py"]
enabled_tools = ["search", "fetch"]
startup_timeout_sec = 10
tool_timeout_sec = 60

[hooks]
[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/pre_tool_use.py"
timeout = 20
statusMessage = "Checking Bash command"
```


### テンプレートD: CI review only


```
# .codex/config.toml
[profiles.ci_review]
sandbox_mode = "read-only"
approval_policy = "never"
web_search = "disabled"
model_reasoning_effort = "medium"

[profiles.ci_review.features]
multi_agent = false
hooks = false
```


### テンプレートE: 企業requirementsの出発点


```
# requirements.toml
allowed_sandbox_modes = ["read-only", "workspace-write"]
allowed_approval_policies = ["untrusted", "on-request"]
allowed_web_search_modes = ["disabled", "cached"]
allowed_approvals_reviewers = ["user", "auto_review"]

deny_read = ["**/.env", "**/.env.*", "**/secrets/**", "**/*_rsa", "**/*_ed25519"]

[features]
browser_use = false
computer_use = false
in_app_browser = false
apps = false
hooks = true

[hooks]
managed_dir = "/enterprise/hooks"
windows_managed_dir = 'C:'

[[hooks.PreToolUse]]
matcher = "^Bash$"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "python3 /enterprise/hooks/pre_tool_use_policy.py"
timeout = 30
statusMessage = "Checking managed Bash command"

[mcp_servers.docs.identity]
url = "https://mcp.example.internal/docs/mcp"
```


---


## 設定レビュー用チェックリスト

設定変更はコード変更と同じくレビュー対象にする。特に `MCP`、`Hooks`、`Rules`、`requirements.toml`、`Subagents` は、権限や外部接続の変更である。


```text
L{0.32}L{0.38}}
観点  |  レビュー質問  |  危険シグナル
観点  |  レビュー質問  |  危険シグナル
配置  |  個人設定、project設定、requirementsのどれに置くべきか判断したか。  |  個人pathやsecretがproject設定に入っていないか。
権限  |  sandbox、approval、network、MCP tool、app toolの増加を説明したか。  |  danger、never、network trueが混ざっていないか。
MCP  |  enabled tools、timeout、auth、required、ownerを明記したか。  |  write系toolをallowlistに入れていないか。
Hooks  |  event、matcher、script path、timeout、failure behaviorを説明したか。  |  広すぎるmatcherや長すぎるtimeoutがないか。
Subagents  |  役割、sandbox、出力形式、MCP accessを明記したか。  |  親と子の責務が重複していないか。
Rules  |  prompt/forbiddenの理由が人間に伝わるか。  |  prefixが広すぎたり狭すぎたりしないか。
AGENTS  |  設定だけでなく人間向け手順も更新したか。  |  古いbuild/test commandが残っていないか。
CI  |  noninteractiveで承認待ちにならないか。  |  writeやnetworkが不要に有効ではないか。
rollback  |  enabled=false、profile切替、file削除など戻し方を書いたか。  |  失敗時に誰が戻すかownerが明記されているか。
最新性  |  Codex version、docs、schema、changelogを確認したか。  |  古いkey名やdeprecated設定が残っていないか。
```


#### 図解: 設定レビュー 01

`配置` → `権限` → `rollback`

_設定変更は配置と戻し方まで見る。_


#### 図解: 設定レビュー 02

`MCP` → `tool` → `auth`

_MCPはtool面と認証が中心。_


#### 図解: 設定レビュー 03

`Hooks` → `matcher` → `timeout`

_hookは狭く短く始める。_


#### 図解: 設定レビュー 04

`Subagents` → `role` → `sandbox`

_役割別にsandboxを変える。_


#### 図解: 設定レビュー 05

`requirements` → `allow` → `deny`

_管理設定は弱められない。_


#### 図解: 設定レビュー 06

`AGENTS` → `command` → `policy`

_人間向け規約も更新する。_


#### 図解: 設定レビュー 07

`CI` → `never` → `read-only`

_CIは承認待ちを避ける。_


#### 図解: 設定レビュー 08

`latest` → `version` → `schema`

_最新性はversionとschemaで見る。_


#### 図解: 設定レビュー 09

`secret` → `env var` → `deny read`

_secretを値として書かない。_


#### 図解: 設定レビュー 10

`team` → `owner` → `docs`

_設定にownerを持たせる。_


## 設定変更PRのひな形


```
## Codex configuration change

### Purpose
Explain the workflow this config enables.

### Scope
- Files changed:
- Profiles affected:
- MCP servers affected:
- Hooks/rules affected:
- Requirements affected:

### Permission impact
- Sandbox modes:
- Approval policies:
- Network access:
- External services:
- Secrets/env vars:

### Verification
- /debug-config:
- codex features list:
- codex mcp list:
- codex execpolicy check:
- Test command:

### Rollback
- Set enabled=false:
- Remove section:
- Revert PR:

### Owner
Team/person responsible for upkeep.
```


## この設定増補のまとめ

設定の良し悪しは、項目数ではなく、目的、配置、権限、検証、rollbackが明確かで決まる。`config.toml` はすべてを入れる場所ではなく、個人、project、profile、agent、MCP、Hooks、Rulesを接続する中心である。`requirements.toml` はユーザーを縛るためだけではなく、組織として許容するsandbox、approval、web search、MCP identity、managed hooks、deny readを明確にするためのファイルである。設定を書くときは、まず最小構成、次にprofile、次にproject、最後にMCPやHooksを足す。変更後は `/debug-config`、`codex features list`、`codex mcp list`、`codex execpolicy check` の順に確認し、設定変更PRには必ずpermission impactとrollbackを添える。


---

