<!--
@dependency-start
contract reference
responsibility Houses the split guide section: プロジェクト内運用とサブエージェント設計.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# プロジェクト内運用とサブエージェント設計

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 1010-2637
- section sha256: `9dc5532ce0b9e0973bbbba35f153c570961fe93bd20c3f593ab1406d2933e1c7`

<!-- split-content-start -->

# 増補編：プロジェクト内運用とサブエージェント設計

addcontentsline{toc}{part}{増補編：プロジェクト内運用とサブエージェント設計}


## 増補編の位置づけ

前半では、Codex CLIの基本、コマンド、設定キー、承認、サンドボックス、MCP、Hooks、Rulesを横断的に整理した。しかし、実際にチームのリポジトリへCodexを入れるときに重要なのは、「どのファイルをどこに置くか」「個人設定とプロジェクト設定をどう分けるか」「サブエージェントに何を任せるか」「Codexが勝手に読んでよい情報と読ませたくない情報をどう分離するか」である。本増補編では、プロジェクト内に置く`.codex/`、`AGENTS.md`、`rules/`、`hooks.json`、`agents/`、`skills/`、MCP設定を、実際のディレクトリ構成とTOML例で解説する。

公式仕様上、ユーザー設定は通常`~/.codex/config.toml`に置き、プロジェクト固有の上書きはリポジトリ内の`.codex/config.toml`に置く。プロジェクトスコープの`.codex/`レイヤは、プロジェクトを信頼したときだけ読み込まれる。さらに、Codexはプロジェクトルートから現在の作業ディレクトリまで`.codex/config.toml`を探索し、同じキーが複数見つかる場合は現在ディレクトリに近いものを優先する。したがって、モノレポではroot全体の安全設定と、`packages/frontend/`や`services/api/`の局所設定を分ける設計ができる。


増補編の推奨方針は、**個人の好みはユーザー設定、チームの作業規約はリポジトリ、危険操作の制約はRulesまたは管理設定、繰り返しワークフローはSkills、大きな並列作業はSubagents**である。すべてを一つの`AGENTS.md`に詰め込むのではなく、役割ごとに置き場所を分けると保守しやすい。


## 追加50枚の図解カタログ（プロジェクト運用編）

以下の50点は、基礎編の図解を補完するプロジェクト運用向けの概念図である。


#### 図解: 51 プロジェクト内.codexの役割

`repo root` → ` .codex settings` → ` team shared behavior`

_プロジェクト設定ディレクトリ_


#### 図解: 52 単一アプリ構成

`AGENTS.md` → ` .codex/config` → ` agents/rules/hooks`

_単一リポジトリの基本_


#### 図解: 53 モノレポ構成

`root rules` → `package AGENTS` → `package .codex`

_モノレポ階層_


#### 図解: 54 サブディレクトリ起動

`current dir` → `walk to root` → `closest config wins`

_起動ディレクトリと設定_


#### 図解: 55 信頼状態

`trusted project` → `load .codex` → `load local hooks`

_信頼されたプロジェクト_


#### 図解: 56 未信頼状態

`untrusted` → `skip project layer` → `user layer only`

_未信頼プロジェクト_


#### 図解: 57 ルート検出

`markers` → `first parent hit` → `project root`

_ルート検出_


#### 図解: 58 代替指示名

`alternate route names` → `find per directory` → `one file per dir`

_AGENTS代替ファイル_


#### 図解: 59 相対パス解決

`config location` → `relative path` → `resolve from .codex`

_相対パスの基準_


#### 図解: 60 プロファイル選択

`base config` → `profile overlay` → `CLI override`

_profileの合成_


#### 図解: 61 グローバル設定

`user defaults` → `personal MCP` → `personal agents`

_個人設定_


#### 図解: 62 チーム設定

`project config` → `shared guardrails` → `shared agents`

_チーム共有設定_


#### 図解: 63 エージェント棚卸し

`built in agents` → `custom agents` → `prompt chooses`

_エージェントの一覧_


#### 図解: 64 カスタム agent TOML

`name` → `description` → `developer instructions`

_必須3項目_


#### 図解: 65 agent継承

`parent session` → `omitted fields` → `child inherits`

_継承の考え方_


#### 図解: 66 agent sandbox

`read only explorer` → `write fixer` → `approval overlay`

_役割別sandbox_


#### 図解: 67 agent threads

`spawn` → `switch with slash agent` → `collect summaries`

_agent thread管理_


#### 図解: 68 並列レビュー

`security` → `tests` → `maintainability`

_PRレビュー分担_


#### 図解: 69 調査と実装分離

`mapper` → `debugger` → `fixer`

_UIデバッグ分担_


#### 図解: 70 CSV fan out

`rows` → `workers` → `result CSV`

_大量ジョブ分散_


#### 図解: 71 reviewer設計

`evidence` → `risk` → `actionable fixes`

_reviewerの出力_


#### 図解: 72 explorer設計

`read only` → `map code paths` → `cite files`

_explorerの出力_


#### 図解: 73 docs researcher

`MCP docs` → `verify APIs` → `return sources`

_文書調査agent_


#### 図解: 74 browser debugger

`MCP browser` → `reproduce` → `capture evidence`

_ブラウザ調査agent_


#### 図解: 75 ui fixer

`small patch` → `validate changed path` → `avoid drift`

_実装修正agent_


#### 図解: 76 agent nicknames

`candidate pool` → `display label` → `type unchanged`

_表示名候補_


#### 図解: 77 max threads

`parallel cap` → `resource control` → `predictable cost`

_同時実行上限_


#### 図解: 78 max depth

`root depth zero` → `child allowed` → `avoid recursion`

_再帰深さ_


#### 図解: 79 skills local

`skill folder` → `SKILL.md` → `config path`

_プロジェクトskill_


#### 図解: 80 skill activation

`explicit mention` → `description match` → `load full file`

_skill起動_


#### 図解: 81 MCP project

`server table` → `trusted project` → `TUI slash mcp`

_プロジェクトMCP_


#### 図解: 82 MCP stdio

`command` → `args env cwd` → `tool surface`

_STDIO詳細_


#### 図解: 83 MCP http

`url` → `headers OAuth` → `tool timeout`

_HTTP詳細_


#### 図解: 84 Rules local

`rules folder` → `prefix match` → `prompt deny allow`

_rules配置_


#### 図解: 85 Hooks local

`event` → `matcher` → `command handler`

_hooks配置_


#### 図解: 86 prompt guard hook

`UserPromptSubmit` → `scan secrets` → `block or warn`

_プロンプト保護_


#### 図解: 87 command guard hook

`PreToolUse` → `inspect Bash` → `return policy`

_コマンド保護_


#### 図解: 88 stop validation

`Stop` → `run checks` → `continue or report`

_停止時検証_


#### 図解: 89 secret policy

`deny read` → `env exclude` → `approval check`

_秘密情報防御_


#### 図解: 90 CI template

`read only exec` → `schema output` → `artifact report`

_CIレビュー_


#### 図解: 91 worktree setup

`new worktree` → `setup script` → `shared .codex`

_worktree運用_


#### 図解: 92 local actions

`common commands` → `app top bar` → `integrated terminal`

_アクション定義_


#### 図解: 93 package scopes

`frontend` → `backend` → `infra`

_パッケージ別設定_


#### 図解: 94 branch review

`diff vs main` → `subagents` → `final triage`

_ブランチレビュー_


#### 図解: 95 migration plan

`scan` → `codify guidance` → `add agents`

_導入手順_


#### 図解: 96 debug config

`effective config` → `layer source` → `fix conflict`

_設定診断_


#### 図解: 97 failure modes

`too broad prompt` → `too much recursion` → `token cost`

_失敗予防_


#### 図解: 98 team onboarding

`copy template` → `trust project` → `run smoke test`

_チーム導入_


#### 図解: 99 enterprise boundary

`requirements` → `allowlist` → `managed hooks`

_企業境界_


#### 図解: 100 mature workflow

`AGENTS` → `MCP hooks skills` → `subagents`

_成熟ロードマップ_


## プロジェクト内で使う場合の推奨ディレクトリ構成


### まず作る最小構成

基本構成では、リポジトリ直下に`AGENTS.md`と`.codex/config.toml`だけを置く。`AGENTS.md`は「Codexが毎回読む作業規約」、`.codex/config.toml`は「Codexクライアントが読む設定」である。前者は自然言語で、後者はTOMLで書く。最初からHooks、Rules、MCP、Skills、Subagentsを全部入れる必要はない。最初は基本構成で始め、Codexが同じ間違いを繰り返したら`AGENTS.md`へルールを追加し、危険なコマンドが出るならRulesへ移し、繰り返しの手順が増えたらSkillsに切り出す。


```
my-repo/
  AGENTS.md                 # チーム共通の作業規約。Codexが作業前に読む。
  .codex/
    config.toml             # プロジェクト固有のCodex設定。
```


### 実運用で育てる標準構成

実運用では、次のように`.codex/`配下を用途別に分けるとよい。`agents/`はサブエージェント定義、`rules/`は外部実行に関するコマンドポリシー、`hooks.json`または`hooks/`は決定的な検査スクリプト、`skills/`は再利用する作業手順、`mcp/`はMCPサーバの補助設定やREADMEを置く場所として扱う。


```
my-repo/
  AGENTS.md
  README.md
  package.json
  .codex/
    config.toml
    agents/
      pr-explorer.toml
      reviewer.toml
      docs-researcher.toml
      code-mapper.toml
      browser-debugger.toml
      ui-fixer.toml
    rules/
      default.rules
    hooks.json
    hooks/
      pre_tool_use_policy.py
      permission_request.py
      post_tool_use_review.py
      user_prompt_submit_data_flywheel.py
      stop_validation.py
    skills/
      release-notes/
        SKILL.md
        scripts/
          collect_changes.py
      api-contract-review/
        SKILL.md
        references/
          openapi-rules.md
    mcp/
      README.md
      local-devtools.md
```


### ファイルの役割一覧


```text
L{0.29} L{0.40}}
置き場所  |  代表ファイル  |  役割
置き場所  |  代表ファイル  |  役割
ユーザー設定  |  `~/.codex/config.toml`  |  個人の既定モデル、個人MCP、個人サブエージェント、通知、履歴など。チームへ共有しない。
ユーザー指示  |  `~/.codex/AGENTS.md`  |  自分の作業スタイル、返答の好み、普段使うパッケージマネージャなど。
プロジェクト指示  |  `AGENTS.md`  |  リポジトリのビルド、テスト、レビュー基準、命名規則、触ってはいけない領域。
プロジェクト設定  |  `.codex/config.toml`  |  sandbox、approval、MCP、profiles、features、agents、skillsなどのプロジェクト既定。
サブエージェント  |  `.codex/agents/*.toml`  |  役割別のmodel、reasoning、sandbox、MCP、developer instructions。
Rules  |  `.codex/rules/default.rules`  |  外部実行時のコマンドprefixをallow、prompt、forbiddenなどへ分類。
Hooks  |  `.codex/hooks.json`  |  SessionStart、PreToolUse、PostToolUse、PermissionRequest、UserPromptSubmit、Stopなどでスクリプトを実行。
Hook scripts  |  `.codex/hooks/*.py`  |  秘密検査、コマンド検査、テスト結果整形、終了時検証などの決定的ロジック。
Skills  |  `.codex/skills/*/SKILL.md`  |  繰り返し使う手順や専門知識。`skills.config.path`でskill folderを参照する。
MCP補足  |  `.codex/mcp/README.md`  |  MCPサーバの起動条件、必要な環境変数、ローカル開発ツールの説明。
```


### 何をGitに入れるか

基本的に、`AGENTS.md`、`.codex/config.toml`、`.codex/agents/*.toml`、`.codex/rules/*.rules`、`.codex/hooks.json`、`.codex/hooks/*.py`、`.codex/skills/*/SKILL.md`はGitに入れてよい。ただし、APIキー、Bearer token、個人の認証情報、ローカルの絶対パス、社外秘URL、個人端末にしかないツールパスは入れない。MCPサーバの認証情報は`bearer_token_env_var`や環境変数で渡し、値そのものはGit管理しない。


`.codex/`をGit管理する場合、プロジェクトが信頼済みになったときにその設定、Rules、Hooksが読み込まれる。便利な一方で、悪意あるリポジトリが危険なHooksを置く可能性もある。知らないリポジトリでは、信頼前に`.codex/`の中身を確認する。


## プロジェクトルート、設定探索、信頼状態


### プロジェクトルートの考え方

Codexは、現在の作業ディレクトリから親方向へたどり、プロジェクトルートを見つける。既定では`.git`を含むディレクトリがルートとして扱われる。MercurialやSapling、独自マーカーを使うチームでは`project_root_markers`で検出条件を増やせる。ルート探索を無効化して現在ディレクトリだけをルートにしたい場合は、`project_root_markers = []`とする。


```
# ~/.codex/config.toml または .codex/config.toml
# Git, Mercurial, Sapling のいずれかを含む親ディレクトリをプロジェクトルートにする。
project_root_markers = [".git", ".hg", ".sl"]

# 親方向への探索をやめ、現在ディレクトリをプロジェクトルートにする場合。
# project_root_markers = []
```


### 設定探索の実例

次のモノレポで`packages/web/src`から`codex`を起動すると、Codexはrootから現在ディレクトリまでの`.codex/config.toml`を順に読む。root設定で全体のsandboxやMCPを定め、`packages/web/.codex/config.toml`でフロントエンド固有のMCPやサブエージェントを上書きできる。


```
monorepo/
  .git/
  AGENTS.md
  .codex/config.toml
  packages/
    web/
      AGENTS.md
      .codex/config.toml
      src/
    api/
      AGENTS.md
      .codex/config.toml
```


```text
L{0.27} X}
起動場所  |  読まれやすい設定  |  運用例
`monorepo/`  |  rootの`.codex/config.toml`  |  横断レビュー、依存更新、全体方針の確認。
`packages/web/`  |  root + web局所設定  |  UI、Playwright、ブラウザMCP、frontend agentを有効化。
`packages/api/`  |  root + api局所設定  |  API契約、DB migration、backend agentを有効化。
`infra/`  |  root + infra局所設定  |  TerraformやKubernetes操作を強めのRulesで保護。
```


### 信頼済みと未信頼の境界

プロジェクトを未信頼として扱うと、Codexはプロジェクト内の`.codex/`レイヤ、プロジェクトlocal hooks、プロジェクトlocal rulesを読み込まない。個人設定とシステム設定は読み込まれる。これは、見知らぬリポジトリの`.codex/hooks.json`が意図しないスクリプトを実行するのを防ぐための設計である。初めてcloneしたリポジトリでは、まず`AGENTS.md`と`.codex/`を目視し、安全が確認できてからtrustするのがよい。

section{基本の`.codex/config.toml`テンプレート}

### 汎用テンプレート

次のテンプレートは、通常の開発用に安全側へ寄せたものである。作業ディレクトリ内の変更は許可し、ネットワークやワークスペース外の書き込みは承認対象にする。MCPは必要なものだけ有効化し、サブエージェント数は6以下から始める。


```
# .codex/config.toml
#:schema https://developers.openai.com/codex/config-schema.json

model = "gpt-5.5"
model_provider = "openai"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

# プロジェクト指示の読み込み上限と代替名。
project_doc_max_bytes = 65536
project_doc_alternate route_filenames = ["TEAM_GUIDE.md", ".agents.md"]

# workspace-write時の細かい境界。必要なものだけ許可する。
[sandbox_workspace_write]
network_access = false
exclude_slash_tmp = true
exclude_tmpdir_env_var = true
writable_roots = ["./tmp", "./.codex/work"]

# 子プロセスへ渡す環境変数。秘密を広く継承しない。
[shell_environment_policy]
inherit = "core"
include_only = ["PATH", "HOME", "LANG", "LC_ALL", "NODE_ENV"]
exclude = ["OPENAI_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"]

[features]
hooks = true
multi_agent = true
fast_mode = true

[agents]
max_threads = 6
max_depth = 1
job_max_runtime_seconds = 1800
```


### プロファイルを使い分ける

プロファイルは、同じリポジトリで「軽い調査」「深いレビュー」「CI用非対話」を切り替えるのに向く。CLIでは`codex --profile deep-review`のように選択する。プロファイルは現在の仕様では実験的であり、IDE拡張では未対応とされているため、チーム標準として使うならCLI利用者向けのREADMEを残す。


```
# .codex/config.toml の続き
[profiles.explore]
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
approval_policy = "on-request"

[profiles.deep-review]
model = "gpt-5.5"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
approval_policy = "never"

[profiles.implement]
model = "gpt-5.5"
model_reasoning_effort = "medium"
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


### 一回限りの上書き

`-c`または`--config`は、任意の設定キーを一回だけ上書きする。値はTOMLとして解釈されるため、文字列は引用符を含める必要がある場合がある。専用フラグが存在する場合は`--model`や`--sandbox`などを使い、存在しない深いキーだけ`-c`で変えると読みやすい。


```
# モデルだけ上書き
codex --model gpt-5.4

# TOML値として文字列を渡す
codex --config model='"gpt-5.4"'

# ネットワーク許可を一回だけ変更
codex -c sandbox_workspace_write.network_access=true

# MCPサーバを一回だけ無効化
codex -c mcp_servers.context7.enabled=false
```


## AGENTS.mdの階層設計


### AGENTS.mdに書くべき内容

`AGENTS.md`は、毎回Codexに守ってほしいルールを置く。長大な設計資料ではなく、作業に直結する短い規約がよい。具体的には、ビルドとテストコマンド、パッケージマネージャ、コード規約、レビュー観点、禁止事項、変更後の確認手順、よく間違えるディレクトリ案内を置く。あいまいな精神論より、「TypeScript変更後は`pnpm typecheck`を走らせる」のような行動可能な指示が強い。


```
# AGENTS.md
## Project overview
This repository contains a React frontend, Node API, and shared packages.

## Commands
- Install dependencies with `pnpm install`.
- Run frontend checks with `pnpm --filter web test` and `pnpm --filter web typecheck`.
- Run API checks with `pnpm --filter api test`.

## Working rules
- Keep changes small and scoped to the requested task.
- Do not add production dependencies without explicit approval.
- Prefer editing existing tests over adding broad snapshot tests.
- Before final response, summarize changed files and validation results.

## Review expectations
- Mention correctness, security, behavior regressions, and missing tests.
- Ignore purely stylistic issues unless they hide real bugs.
```


### 階層化の例

Codexはグローバル指示、プロジェクトルート、現在ディレクトリまでの各階層の指示を連結する。近いディレクトリの指示ほど後ろに入るので、局所ルールが強く効く。たとえばrootでは全体規約を書き、frontendではUIテスト、apiではDB migration、infraでは破壊的操作の禁止を追加する。


```
monorepo/
  AGENTS.md                     # 全体ルール
  packages/
    web/
      AGENTS.md                 # UI固有ルール
    api/
      AGENTS.md                 # API固有ルール
  infra/
    AGENTS.override.md          # infraでは明示的に上書きしたいルール
```


`AGENTS.override.md`は同じ階層の`AGENTS.md`より優先される。緊急時やブランチ固有の一時ルールには便利だが、常用すると「なぜAGENTS.mdが効かないのか」が分かりづらくなる。運用ルールとして、overrideは理由と期限を書くとよい。


### 代替ファイル名

既存プロジェクトが`TEAM_GUIDE.md`や`CONTRIBUTING.md`に規約を持っている場合、`project_doc_alternate route_filenames`で代替名を登録できる。ただし、Codexが読むファイルが増えすぎるとコンテキストが膨らむ。まずは`AGENTS.md`へCodex向けの要点を集約し、必要な補足だけリンクする。


```
# ~/.codex/config.toml または .codex/config.toml
project_doc_alternate route_filenames = ["TEAM_GUIDE.md", ".agents.md"]
project_doc_max_bytes = 65536
```


## サブエージェントの基本


### いつ使うか

サブエージェントは、Codexが別のagent threadをspawnし、並列に調査、実装、レビュー、要約を進め、親スレッドへ結果を返す仕組みである。Codexはサブエージェントを勝手にspawnせず、ユーザーが明示的に「spawn two agents」「parallel subagents」「one agent per point」のように依頼したときに使う。各サブエージェントは独自にモデルとツールを使うため、単一agentよりトークン消費、レイテンシ、ローカルリソース消費が増える。したがって、単発修正ではなく、広い調査、PRレビュー、複数観点の監査、複数ファイル群の一括点検に向く。


```
# 典型的な依頼例
Review this branch against main using parallel subagents.
Spawn one agent for security risks, one for missing tests,
and one for maintainability. Wait for all agents, then summarize
findings by category with file references and recommended fixes.
```


### 組み込みagentとカスタムagent

Codexには組み込みagentとして、汎用の`default`、実装や修正向けの`worker`、読み取り中心の探索向け`explorer`が用意されている。独自agentを作る場合は、個人用なら`~/.codex/agents/`、プロジェクト用なら`.codex/agents/`にTOMLファイルを置く。ファイル名は分かりやすさのためagent名に合わせるのがよいが、Codexが識別に使う真の名前はファイル内の`name`フィールドである。


```
.codex/
  agents/
    pr-explorer.toml
    reviewer.toml
    docs-researcher.toml
```


### カスタムagentの必須フィールド

各agentファイルには、少なくとも`name`、`description`、`developer_instructions`を定義する。`description`はCodexが「どのagentを使うべきか」を判断するときの説明で、`developer_instructions`はそのagentの振る舞いを縛る中核指示である。


```
# .codex/agents/reviewer.toml
name = "reviewer"
description = "PR reviewer focused on correctness, security, and missing tests."
developer_instructions = """
Review code like an owner.
Prioritize correctness, security, behavior regressions, and missing test coverage.
Lead with concrete findings, include reproduction steps when possible,
and avoid style-only comments unless they hide a real bug.
"""
```


### 任意フィールドと継承

`nickname_candidates`、`model`、`model_reasoning_effort`、`sandbox_mode`、`mcp_servers`、`skills.config`などを省略すると、親セッションから継承される。たとえば調査agentは`sandbox_mode = "read-only"`に固定し、実装修正agentだけ親の`workspace-write`を継承させる、といった設計ができる。逆に、親セッションで対話中に`--yolo`や承認設定を変更している場合、childにもruntime overrideが再適用されるため、強い権限でspawnするときは注意する。


```
# 調査agentは読み取り専用に固定
sandbox_mode = "read-only"
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"

# 表示名候補。内部識別名は name のまま。
nickname_candidates = ["Atlas", "Delta", "Echo"]
```


### グローバルなサブエージェント設定

`[agents]`には、同時に開けるagent thread数、spawnの深さ、CSV fan-outジョブの既定timeoutを置く。初期値としては`max_threads = 6`、`max_depth = 1`が扱いやすい。`max_depth = 1`はroot sessionから直接childをspawnできるが、childがさらにgrandchildを増やす深い再帰は防ぐ。深さを上げると便利な場合もあるが、広い委任が連鎖し、費用と不確実性が増える。


```
# .codex/config.toml
[agents]
max_threads = 6
max_depth = 1
job_max_runtime_seconds = 1800
```


## サブエージェント設定例1：PRレビュー分担


### 構成の狙い

PRレビューでは、全員が同じ観点を広く見るより、役割を分けた方が親agentの文脈が汚れにくい。`pr_explorer`はread-onlyで影響範囲を地図化し、`reviewer`は正しさ、セキュリティ、テスト不足に集中し、`docs_researcher`はMCP経由でフレームワークやAPIの仕様確認を行う。親agentは3つの結果を統合して、重要度順に最終提案をまとめる。


```
# .codex/config.toml
[agents]
max_threads = 6
max_depth = 1
```


### pr-explorer.toml


```
# .codex/agents/pr-explorer.toml
name = "pr_explorer"
description = "Read-only codebase explorer for gathering evidence before changes are proposed."
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
developer_instructions = """
Stay in exploration mode.
Trace the real execution path, cite files and symbols, and avoid proposing fixes
unless the parent agent asks for them.
Prefer fast search and targeted file reads over broad scans.
Return a concise map: entry points, touched modules, risky assumptions, and evidence.
"""
```


### reviewer.toml


```
# .codex/agents/reviewer.toml
name = "reviewer"
description = "PR reviewer focused on correctness, security, and missing tests."
model = "gpt-5.5"
model_reasoning_effort = "high"
sandbox_mode = "read-only"
developer_instructions = """
Review code like an owner.
Prioritize correctness, security, behavior regressions, and missing test coverage.
Lead with concrete findings. Include file references and reproduction ideas.
Avoid style-only comments unless they hide a real bug.
Never edit files. Return findings grouped by severity.
"""
nickname_candidates = ["Atlas", "Delta", "Echo"]
```


### docs-researcher.toml


```
# .codex/agents/docs-researcher.toml
name = "docs_researcher"
description = "Documentation specialist that verifies APIs and framework behavior through docs MCP."
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
developer_instructions = """
Use the docs MCP server to confirm APIs, options, and version-specific behavior.
Return concise answers with links or exact references when available.
Do not make code changes.
Call out uncertainty instead of guessing.
"""

[mcp_servers.openaiDeveloperDocs]
url = "https://developers.openai.com/mcp"
startup_timeout_sec = 20
tool_timeout_sec = 60
```


### 実行プロンプト


```
Review this branch against main.
Have pr_explorer map the affected code paths, reviewer find real risks,
and docs_researcher verify framework APIs that the patch relies on.
Wait for all three agents, then give me a table with:
- severity
- finding
- evidence files
- suggested fix
- whether a test is required
```


## サブエージェント設定例2：フロントエンド統合デバッグ


### 構成の狙い

UIバグは、画面の再現、ネットワーク、ブラウザコンソール、状態管理、APIレスポンス、実装差分が絡むことが多い。単一agentで全部やるとログが親文脈に入りすぎる。そこで、`browser_debugger`はブラウザMCPを使って再現と証拠収集、`code_mapper`はread-onlyで関係コードを地図化、`ui_fixer`は最小差分を作る、という分担にする。


```
# .codex/agents/code-mapper.toml
name = "code_mapper"
description = "Read-only explorer for locating frontend and backend code paths."
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
developer_instructions = """
Map the code that owns the failing UI flow.
Identify entry points, state transitions, API calls, and likely files before editing starts.
Return a concise map with exact file references.
"""
```


```
# .codex/agents/browser-debugger.toml
name = "browser_debugger"
description = "UI debugger that uses browser tooling to reproduce issues and capture evidence."
model = "gpt-5.5"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
developer_instructions = """
Reproduce the issue in the browser, capture exact steps, and report what the UI does.
Use browser tooling for screenshots, console output, and network evidence.
Do not edit application code.
If the app is not running, tell the parent what command is needed.
"""

[mcp_servers.chrome_devtools]
url = "http://localhost:3000/mcp"
startup_timeout_sec = 20
tool_timeout_sec = 120
```


```
# .codex/agents/ui-fixer.toml
name = "ui_fixer"
description = "Implementation-focused agent for targeted UI fixes after the issue is understood."
model = "gpt-5.5"
model_reasoning_effort = "medium"
developer_instructions = """
Own the fix once the issue is reproduced.
Make the smallest defensible change. Keep unrelated files untouched.
Validate only the behavior you changed, then report commands and results.
"""

[[skills.config]]
path = "./skills/api-contract-review"
enabled = false
```


### 実行プロンプト


```
Investigate why the settings modal fails to save.
Have browser_debugger reproduce it, code_mapper trace the responsible code path,
and ui_fixer implement the smallest fix only after the failure mode is clear.
Wait for all agents and summarize evidence before applying the patch.
```


## サブエージェント設定例3：CSV fan-out監査

大量のファイル、パッケージ、コンポーネント、移行候補を同じ観点で点検する場合は、CSVを作り、1行1作業としてworkerに配る。これは実験的なワークフローであり、仕様変更の可能性がある。`spawn_agents_on_csv`では、入力CSV、worker prompt template、id column、output schema、出力CSVパス、並列数、timeoutを渡す。各workerは`report_agent_job_result`を一度だけ呼び、呼ばない場合はその行がerror扱いになる。


```
# 例: components.csv を作り、コンポーネント単位で監査する依頼
Create /tmp/components.csv with columns path,owner and one row per frontend component.
Then call spawn_agents_on_csv with:
- csv_path: /tmp/components.csv
- id_column: path
- instruction: "Review {path} owned by {owner}. Return JSON with keys path, risk, summary, and follow_up via report_agent_job_result."
- output_csv_path: /tmp/components-review.csv
- output_schema: an object with required string fields path, risk, summary, and follow_up
- max_concurrency: 4
- max_runtime_seconds: 1200
```


```text
L{0.24} X}
項目  |  例  |  注意点
`csv_path`  |  `/tmp/components.csv`  |  workerに配る行を含むCSV。秘匿データを入れすぎない。
`instruction`  |  {Review {path}}  |  列名プレースホルダーを使う。出力形式を明確にする。
`id_column`  |  `path`  |  結果を追跡しやすい安定IDを選ぶ。
`output_schema`  |  JSON object  |  後処理するなら必須フィールドを固定する。
`max_concurrency`  |  4  |  `agents.max_threads`との関係を考え、過剰並列を避ける。
`max_runtime_seconds`  |  1200  |  workerが詰まったときの上限。
```


## サブエージェント設計の判断基準


### 役割を狭くする

よいcustom agentは狭く、偏っていて、終わり方が明確である。`reviewer`に調査、実装、テスト、ドキュメント作成、PR説明まで全部任せると、親agentと役割が重複し、返ってくる出力が冗長になる。`explorer`は地図だけ、`reviewer`はfindingだけ、`fixer`は差分だけ、`docs_researcher`は仕様確認だけ、というように区切る。


```text
L{0.30} L{0.43}}
agent  |  向く仕事  |  避ける仕事
agent  |  向く仕事  |  避ける仕事
`explorer`  |  影響範囲、依存関係、実行経路、既存テストの把握。  |  修正案の実装、広すぎる設計提案。
`reviewer`  |  正しさ、セキュリティ、回帰、テスト不足の指摘。  |  細かい文体修正、好みだけのリファクタ。
`docs_researcher`  |  公式仕様、API差分、version固有挙動の確認。  |  推測による実装、未確認の断言。
`browser_debugger`  |  UI再現、console、network、スクリーンショット証拠。  |  アプリコード編集。
`ui_fixer`  |  再現済み問題の最小修正と確認。  |  原因未特定の広範囲改変。
`migration_worker`  |  1ファイルまたは1パッケージ単位の機械的移行。  |  横断アーキテクチャ判断。
```


### modelとreasoningの選び方

重いレビューや曖昧な設計判断には高性能モデルと`model_reasoning_effort = "high"`が向く。一方、探索、ファイル棚卸し、ログ要約、CSVの1行処理のような軽い並列作業では、軽量モデルと`medium`または`low`が扱いやすい。大切なのは、親agentを最も重要な判断に使い、サブエージェントは証拠収集と限定タスクへ寄せることだ。


```text
L{0.20} X}
用途  |  effort  |  理由
仕様判断、セキュリティレビュー  |  high  |  複数前提を検証し、エッジケースを追う必要がある。
コード探索、影響範囲整理  |  medium  |  速度と品質のバランスがよい。
大量CSV行の要約  |  lowまたはmedium  |  1件あたりの判断が軽く、並列数の方が重要。
実装修正  |  medium  |  変更を責務境界に保ち、テストで検証する。
```


### 書き込み権限を分ける

並列agentが同時に編集すると、差分競合や方針の不整合が起きやすい。調査agentとレビューagentはread-onlyにし、実装agentだけworkspace-writeにする。複数の実装agentを使う場合は「担当ファイルを分ける」「親agentが差分統合する」「最初に計画だけを出させる」などのルールをプロンプトに含める。


## プロジェクト内Skillsの作り方


### SkillsとAGENTS.mdの違い

`AGENTS.md`は常に読ませる短い規約、Skillsは必要なときだけ読み込ませる再利用可能な作業手順である。たとえば「リリースノートを書く」「OpenAPI差分を確認する」「DB migrationをレビューする」「障害レポートを作る」のような手順はSkillに向く。Skillは`SKILL.md`を含むディレクトリで、必要に応じて`scripts/`、`references/`、`assets/`を持てる。


```
.codex/
  skills/
    release-notes/
      SKILL.md
      scripts/
        collect_changes.py
      references/
        release-style.md
```


### SKILL.mdの例


```
---
name: release-notes
description: Use when preparing release notes from Git diffs, merged PRs, or changelog fragments.
---

# Release notes workflow

1. Identify the release range.
2. Group changes into Features, Fixes, Breaking Changes, and Internal.
3. Mention user-visible impact before implementation details.
4. If uncertainty remains, list missing information instead of inventing details.
5. Use scripts/collect_changes.py when a git range is available.
```


### config.tomlからSkillを参照する

`skills.config.path`は`SKILL.md`を含むskill folderへのパスである。プロジェクト内に置く場合、`.codex/config.toml`からの相対パスが分かりやすい。ただし、相対パスは設定ファイルの場所を基準に解決されるため、`.codex/config.toml`内では`./skills/release-notes`のように書く。


```
# .codex/config.toml
[[skills.config]]
path = "./skills/release-notes"
enabled = true

[[skills.config]]
path = "./skills/api-contract-review"
enabled = true
```


### サブエージェントとSkillsを組み合わせる

agentファイルにも`skills.config`を置ける。これにより、親セッションでは有効だが特定agentでは無効、または特定agentだけ有効、といった制御ができる。たとえば`docs_researcher`には文書調査Skillを有効にし、`ui_fixer`ではドキュメント編集Skillを無効にする。


```
# .codex/agents/docs-researcher.toml
name = "docs_researcher"
description = "Documentation specialist."
developer_instructions = "Use docs and return concise verified answers."

[[skills.config]]
path = "../skills/api-contract-review"
enabled = true
```


## MCPをプロジェクト内で設定する


### プロジェクトMCPの基本

MCPサーバ設定は`config.toml`の`[mcp_servers.<server-name>]`に置く。ユーザー設定にもプロジェクト設定にも置ける。チームで共有すべきMCPはプロジェクト設定に置き、個人のブラウザやローカルDBなど端末依存のMCPは個人設定に置くとよい。HTTP MCPのBearer tokenは環境変数名だけを設定し、値はGit管理しない。


```
# .codex/config.toml
[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.internal_docs]
url = "https://docs.example.com/mcp"
bearer_token_env_var = "INTERNAL_DOCS_MCP_TOKEN"
startup_timeout_sec = 20
tool_timeout_sec = 60
enabled_tools = ["search_docs", "open_doc"]
```


### STDIO MCPとHTTP MCPの使い分け

STDIO MCPはローカルコマンドとして起動する。NodeやPythonのローカルツール、ブラウザ開発ツール、社内CLIラッパーに向く。HTTP MCPはURLへ接続するため、共有されたドキュメント検索、Figma、issue trackerなどのチーム共通サービスに向く。HTTPでは`bearer_token_env_var`、`http_headers`、`env_http_headers`、OAuthログインを使える。


```text
L{0.33} X}
方式  |  代表キー  |  向く用途
STDIO  |  `command`, `args`, `env`, `cwd`  |  ローカル開発ツール、npxで起動するdocs server、ブラウザ補助。
HTTP  |  `url`, `bearer_token_env_var`, `http_headers`  |  チーム共有MCP、社内ドキュメント、SaaS連携。
共通  |  `enabled_tools`, `disabled_tools`, `tool_timeout_sec`  |  tool surfaceを絞り、失敗時の待ち時間を制御。
```


### MCPの安全運用

MCPはCodexに新しい外部ツールを渡すため、便利だが攻撃面も増える。最初は`enabled_tools`で必要なtoolだけ許可する。HTTP MCPのURLは公式・社内・信頼できるものに限定する。MCPの出力も外部コンテンツであり、プロンプトインジェクションの可能性があるため、危険なsandbox設定や自動承認と組み合わせるときは慎重にする。


## Rulesをプロジェクト内で使う


### Rulesの役割

Rulesは、Codexがsandbox外で実行しようとするコマンドを、prefixに基づいて判定する。たとえば`gh pr view`は承認ありで許可、`git push`は必ずprompt、`rm -rf`はforbidden、といった運用ができる。Rulesは実験的機能として扱われるため、仕様変更に備えて責務を追える形に保ち、定期的に確認する。


```
# .codex/rules/default.rules
# PR閲覧は承認付きで許可。
prefix_rule(
  pattern = ["gh", "pr", "view"],
  decision = "prompt",
  justification = "Viewing PRs is allowed with approval",
  match = [
    "gh pr view 123",
    "gh pr view --json title,body,comments",
  ],
  not_match = [
    "gh pr --repo owner/repo view 123",
  ],
)

# git pushは必ず人間確認。
prefix_rule(
  pattern = ["git", "push"],
  decision = "prompt",
  justification = "Pushing branches mutates remote state and requires review",
)

# 危険な削除は拒否。
prefix_rule(
  pattern = ["rm", "-rf"],
  decision = "forbidden",
  justification = "Use git clean or targeted deletion after human review",
)
```


### Rulesとapprovalの関係

`approval_policy`は「いつユーザーに聞くか」の大枠であり、Rulesは「コマンド内容に基づいてどう扱うか」の補助である。`approval_policy = "never"`の非対話CIでRulesがpromptを要求すると処理が詰まる可能性があるため、CI用profileではread-onlyにして外部実行を避ける、またはRulesの設計をCIに合わせる。


## Hooksをプロジェクト内で使う


### hooks.jsonかinline TOMLか

Hooksは、`hooks.json`または`config.toml`内のinline `[hooks]`として書ける。同じlayerに両方があると両方読まれ、警告が出るため、プロジェクトではどちらか一つに揃える。複雑なhook群は`hooks.json`、短い例や管理設定ではinline TOMLが扱いやすい。


```
# .codex/config.toml
[features]
hooks = true

[[hooks.PreToolUse]]
matcher = "^Bash$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = '/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/pre_tool_use_policy.py"'
timeout = 30
statusMessage = "Checking Bash command"
```


### hooks.jsonの例


```
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/user_prompt_submit_data_flywheel.py"",
            "statusMessage": "Checking prompt for accidental secrets"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/pre_tool_use_policy.py"",
            "timeout": 30,
            "statusMessage": "Checking Bash command"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 "$(git rev-parse --show-toplevel)/.codex/hooks/stop_validation.py"",
            "timeout": 30,
            "statusMessage": "Running final validation"
          }
        ]
      }
    ]
  }
}
```


### Hook scriptの実装方針

Hook scriptは、できるだけ決定的で短くする。LLMの判断をhook内で再現するのではなく、正規表現、allowlist、denylist、JSON schema、静的検査などの機械的ルールに寄せる。たとえば`UserPromptSubmit`で秘密っぽい文字列を検査し、`PreToolUse`で`curl | sh`や`sudo`を検知し、`Stop`で変更ファイルに応じたテストコマンドを提案する。


```
# .codex/hooks/pre_tool_use_policy.py の擬似例
import json
import re
import sys

payload = json.load(sys.stdin)
command = json.dumps(payload)

forbidden = [r"curl+.*|sh", r"rm+-rf+/"]
for pattern in forbidden:
    if re.search(pattern, command):
        print(json.dumps({
            "decision": "deny",
            "reason": f"Forbidden command pattern: {pattern}"
        }))
        sys.exit(0)

print(json.dumps({"decision": "allow"}))
```


## モノレポ向け設定パターン


### rootで守ること、packageで変えること

モノレポでは、rootの`AGENTS.md`と`.codex/config.toml`で横断ルールを決める。たとえば「依存追加は承認」「git pushは禁止」「ネットワークは既定OFF」「最大サブエージェント数は6」「MCPは社内docsだけ」というルールはrootに置く。package側では、テストコマンド、対象MCP、agent、Skillを変える。


```
monorepo/
  AGENTS.md
  .codex/config.toml
  .codex/rules/default.rules
  packages/
    web/
      AGENTS.md
      .codex/config.toml
      .codex/agents/browser-debugger.toml
    api/
      AGENTS.md
      .codex/config.toml
      .codex/agents/api-reviewer.toml
    infra/
      AGENTS.md
      .codex/config.toml
      .codex/rules/infra.rules
```


### frontend packageの例


```
# packages/web/AGENTS.md
## Frontend package rules
- Use `pnpm --filter web test` for unit tests.
- Use `pnpm --filter web e2e` for browser flows when UI behavior changes.
- Keep component changes local. Do not modify shared design tokens without approval.
- Prefer accessible queries in tests.
```


```
# packages/web/.codex/config.toml
[agents]
max_threads = 4
max_depth = 1

[mcp_servers.chrome_devtools]
url = "http://localhost:3000/mcp"
startup_timeout_sec = 20
tool_timeout_sec = 120

[[skills.config]]
path = "./skills/ui-regression"
enabled = true
```


### backend packageの例


```
# packages/api/AGENTS.md
## API package rules
- Run `pnpm --filter api test` after changing API logic.
- Migration files require a rollback explanation.
- Do not change public API response shapes without updating contract tests.
- Security-sensitive changes must include negative tests.
```


```
# packages/api/.codex/config.toml
[mcp_servers.openapi_docs]
command = "node"
args = ["scripts/openapi-mcp.js"]
startup_timeout_sec = 20

[[skills.config]]
path = "./skills/api-contract-review"
enabled = true
```


### infra packageの例


```
# infra/.codex/rules/infra.rules
prefix_rule(
  pattern = ["terraform", "apply"],
  decision = "prompt",
  justification = "Terraform apply changes cloud resources and requires explicit approval",
)

prefix_rule(
  pattern = ["kubectl", "delete"],
  decision = "prompt",
  justification = "Deleting Kubernetes resources requires explicit approval",
)

prefix_rule(
  pattern = ["aws"],
  decision = "prompt",
  justification = "AWS CLI may mutate cloud resources or access sensitive data",
)
```


## プロジェクト導入手順：基本構成から育てる


### Step 1: 現状の作業規約を集約する

最初に、既存のREADME、CONTRIBUTING、CI設定、package scripts、テストコマンドを棚卸しし、Codex向けに`AGENTS.md`へ短くまとめる。重要なのは「人間が知っている暗黙知」を明文化することである。たとえば「このリポジトリはpnpmしか使わない」「snapshot testは最後の手段」「DB migrationはdownを必ず書く」など、レビューで繰り返し指摘していることを入れる。


### Step 2: 最小のconfig.tomlを入れる

次に`.codex/config.toml`を作り、sandbox、approval、web search、features、agentsだけを設定する。MCPやHooksは後でよい。最初から強い自動化を入れると、トラブル時の原因分離が難しくなる。


```
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

[features]
multi_agent = true
hooks = false

[agents]
max_threads = 4
max_depth = 1
```


### Step 3: Smoke testを決める

Codex導入時は、簡単な読み取りタスク、差分なしのレビュー、1ファイルの小修正、テスト実行を順に試す。結果を見て、`AGENTS.md`に不足ルールを追加する。いきなり大規模migrationを任せるより、短い改善ループで設定を育てた方が成功しやすい。


```
# 読み取りだけ
codex --sandbox read-only "Summarize the repository structure and test commands."

# 差分レビュー
codex --sandbox read-only "Review this branch against main for correctness risks."

# 小修正
codex "Fix the failing unit test in packages/web, keep the change minimal, and run the relevant test."
```


### Step 4: サブエージェントを追加する

単一agentの作業ログが長くなり、親文脈に調査ノイズが入りすぎるようになったらサブエージェントを導入する。最初は`explorer`、`reviewer`、`fixer`の3種類だけでよい。用途が増えたら`docs_researcher`、`browser_debugger`、`migration_worker`を追加する。


## 安全なプロンプトテンプレート集


### PRレビュー


```
Review this branch against main with subagents.
Use pr_explorer to map affected files and runtime paths.
Use reviewer to identify correctness, security, behavior regression, and missing-test risks.
Use docs_researcher only when an external API or framework behavior must be verified.
Wait for all agents. Return findings sorted by severity with file references.
Do not edit files unless I explicitly ask for fixes.
```


### 実装修正


```
Implement the smallest fix for the described bug.
Before editing, ask code_mapper to identify the responsible files.
If browser behavior is relevant, ask browser_debugger to reproduce the issue first.
Only after evidence is gathered, use ui_fixer to change files.
Run the most relevant tests and summarize changed files and validation results.
```


### 大規模移行


```
Plan a migration from old API usage to the new API.
First, spawn explorer agents by package to map usage and edge cases.
Do not edit yet. Return a migration plan with:
- files grouped by package
- safe mechanical changes
- risky manual changes
- required tests
After I approve the plan, process packages one at a time.
```


### CI用読み取りレビュー


```
codex exec 
  --sandbox read-only 
  --ask-for-approval never 
  --output-schema review-schema.json 
  "Review the diff against main. Return JSON findings only. Do not edit files."
```


## 設定診断とトラブルシュート増補


### 設定が効かないときの順序

設定が効かない場合は、まずレイヤの優先順位を疑う。CLI flagと`-c`が最上位、次にprofile、次にプロジェクト設定、ユーザー設定、システム設定、built-in defaultsである。プロジェクトが未信頼なら`.codex/`は読まれない。現在ディレクトリが想定と違うと、近い`.codex/config.toml`が読み込まれない。相対パスはconfigを置いた`.codex/`基準で解決される。


```text
L{0.34} X}
症状  |  よくある原因  |  確認方法
`.codex/config.toml`が効かない  |  プロジェクト未信頼、起動場所違い、root検出違い。  |  `/debug-config`、`/status`、プロジェクトtrust状態。
MCPが出ない  |  serverがdisabled、認証環境変数がない、allowlistにない。  |  `codex mcp list`、TUIの`/mcp`。
agentが選ばれない  |  `description`が曖昧、promptで明示していない。  |  agent名をプロンプトで直接指定する。
agentが編集してしまう  |  `sandbox_mode`未指定で親を継承。  |  調査agentに`sandbox_mode = "read-only"`を固定。
Hooksが走らない  |  feature flag無効、未信頼プロジェクト、matcher不一致。  |  `features.hooks`、trust、hookログ。
Rulesが効かない  |  rulesフォルダの場所違い、prefixが一致しない。  |  inline unit testの`match`と`not_match`を追加。
```


### サブエージェントが増えすぎる

`max_depth`を上げると、childがさらにchildをspawnできる。大規模探索では魅力的だが、曖昧なプロンプトと組み合わさるとfan-outが連鎖する。通常は`max_depth = 1`にし、親プロンプトで「spawn exactly three agents」「wait for all three」「do not spawn additional agents」と明記する。


```
Use exactly three subagents: pr_explorer, reviewer, docs_researcher.
Do not spawn additional agents unless I ask.
Wait for all three agents before summarizing.
Each agent should return at most 10 bullet points.
```


### agent outputが散らかる

親agentに返す形式を固定する。特に並列レビューでは、各agentが自由に長文を書くと統合が難しくなる。`finding`、`severity`、`evidence`、`recommended action`のような共通スキーマを指定すると、親agentが統合しやすい。


```
Each subagent must return:
- summary: max 5 sentences
- findings: list of {severity, file, evidence, recommendation}
- uncertainty: what could not be verified
- validation: commands run or why none were run
```


## 完成形のサンプル：チーム用Codexセットアップ

最後に、チームにそのまま配れる構成をまとめる。これは万能ではないが、フロントエンドとAPIを持つ一般的なTypeScriptモノレポの出発点として使いやすい。


```
team-repo/
  AGENTS.md
  .codex/
    config.toml
    agents/
      pr-explorer.toml
      reviewer.toml
      docs-researcher.toml
      browser-debugger.toml
      ui-fixer.toml
    rules/
      default.rules
    hooks.json
    hooks/
      pre_tool_use_policy.py
      stop_validation.py
    skills/
      release-notes/
        SKILL.md
      api-contract-review/
        SKILL.md
  packages/
    web/
      AGENTS.md
    api/
      AGENTS.md
```


```
# .codex/config.toml
#:schema https://developers.openai.com/codex/config-schema.json
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
project_doc_max_bytes = 65536

[sandbox_workspace_write]
network_access = false
exclude_slash_tmp = true
exclude_tmpdir_env_var = true

[features]
multi_agent = true
hooks = true

[agents]
max_threads = 6
max_depth = 1
job_max_runtime_seconds = 1800

[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
startup_timeout_sec = 20

[[skills.config]]
path = "./skills/release-notes"
enabled = true

[[skills.config]]
path = "./skills/api-contract-review"
enabled = true
```


```
# .codex/rules/default.rules
prefix_rule(
  pattern = ["git", "push"],
  decision = "prompt",
  justification = "Pushing to remotes requires human confirmation",
)

prefix_rule(
  pattern = ["gh", "pr", "merge"],
  decision = "prompt",
  justification = "Merging PRs changes shared state",
)

prefix_rule(
  pattern = ["rm", "-rf"],
  decision = "forbidden",
  justification = "Use targeted deletion and human review",
)
```


## プロジェクト運用チェックリスト


```text
L{0.35} L{0.50}}
段階  |  チェック  |  合格条件
段階  |  チェック  |  合格条件
1  |  `AGENTS.md`が短く具体的か  |  ビルド、テスト、禁止事項、レビュー観点が1画面程度で分かる。
2  |  `.codex/config.toml`が最小権限か  |  workspace-write + on-request、networkは原則OFF。
3  |  プロジェクトtrust前に`.codex/`を確認したか  |  hooks、rules、MCP、agentに不審なコマンドやURLがない。
4  |  サブエージェントの役割が狭いか  |  explorer、reviewer、fixerなどの境界が明確。
5  |  調査agentがread-onlyか  |  書き込み権限を持つagentは実装担当に限定。
6  |  MCPのtool surfaceを絞ったか  |  `enabled_tools`または`disabled_tools`で不要toolを減らす。
7  |  Rulesが危険操作を止めるか  |  `git push`、`rm -rf`、cloud CLIなどにpromptまたはforbiddenがある。
8  |  Hooksが決定的か  |  秘密検査やコマンド検査など、機械的で再現性がある。
9  |  CI用profileがあるか  |  非対話ではread-only、approval never、構造化出力を使う。
10  |  更新確認の運用があるか  |  Codex CLIの更新と設定schemaの変化を定期確認する。
```


---

