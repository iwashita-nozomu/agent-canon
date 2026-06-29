<!--
@dependency-start
contract reference
responsibility Houses the split guide section: 最新・実験的機能の徹底解説.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# 最新・実験的機能の徹底解説

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 2638-2976
- section sha256: `efacd87ac2f3c80a0d5090d1dfa18a23ca3858d63517f85d5fa7361ea0e4f981`

<!-- split-content-start -->

# 第V部 最新・実験的機能の徹底解説


## 実験的機能を読むための前提

Codex CLIは更新速度が高く、CLI本体、TUI、設定schema、MCP、Hooks、Subagents、Apps連携、Codex Cloudとの接続が並行して進化する。したがって、実験的機能を理解するには、単に機能名を覚えるよりも、成熟度、feature flag、profile、rollback、監査、チーム共有の流れを決めることが重要である。公式ドキュメント上のFeature Maturityは、機能をStable、Beta、Experimental、Deprecatedのような状態で読むための基準になる。Experimentalは便利でも、設定名、UI、既定値、エラーメッセージ、subcommandの構造が変わる可能性を前提に扱う。

本書では、実験的機能を「開発速度を上げるための候補」と「本番作業に混ぜるとリスクが上がる候補」に分けて扱う。前者にはmulti agent、background terminal、goal追跡、Hooks、Rules、MCP連携、Apps connector、fast modeなどがある。後者には、write権限を増やすもの、外部サービスへ接続するもの、長時間実行するもの、ユーザー確認を減らすものが含まれる。実験機能の導入では、常にbounded profileで試し、`/debug-config`で有効状態を確認し、`codex features list`で手元のbinaryが認識する機能名を照合する。


実験機能は「使えるか」ではなく、「どのprofileで、誰が、どのrepositoryで、何日間、どの成功条件で試し、どう戻すか」を決めてから有効化する。


#### 図解: 成熟度の読み方

`Stable` → `Beta` → `Experimental`

_成熟度は導入判断の入口である。_


#### 図解: 実験機能の隔離

`default profile` → `lab profile` → `rollback`

_検証用profileを分けると戻しやすい。_


#### 図解: feature flagの三層

`config.toml` → `CLI flag` → `TUI toggle`

_有効化経路を混ぜず記録する。_


#### 図解: /experimentalの使い方

`TUIで確認` → `機能を切替` → `debug configで確認`

_対話で切り替えた後も設定状態を確認する。_


#### 図解: changelog確認

`日付を見る` → `CLI versionを見る` → `差分を見る`

_最新情報はversionと日付で読む。_


#### 図解: 実験の成功条件

`効果` → `安全` → `再現性`

_便利さだけでなく再現性を測る。_


#### 図解: 失敗条件

`誤動作` → `遅延` → `権限逸脱`

_失敗条件があると撤退が速い。_


#### 図解: rollback手順

`disable` → `profile変更` → `設定削除`

_戻し方を先に書く。_


#### 図解: team共有

`AGENTS更新` → `docs更新` → `owner明記`

_チームの暗黙知にしない。_


#### 図解: binary確認

`codex version` → `features list` → `help確認`

_手元のCLIで最終確認する。_


## Feature flagとprofileの実務設計

Codex CLIの設定は、ユーザー設定、プロジェクト設定、profile、CLI上書きが重なって効く。実験的機能は、通常のprofileではなく検証用profileに閉じ込めるのが安全である。たとえば、`default`は日常作業用、`lab`は実験機能の検証用、`readonly`は調査専用、`ci`は非対話実行用として分ける。profileを分けると、`--profile lab`を付けたときだけ新機能を使えるため、通常作業に意図しない影響が出にくい。


```
# ~/.codex/config.toml
[profiles.default]
sandbox_mode = "workspace-write"
approval_policy = "on-request"
web_search = "cached"

[profiles.lab]
sandbox_mode = "workspace-write"
approval_policy = "on-request"
web_search = "cached"

[profiles.lab.features]
multi_agent = true
hooks = true
fast_mode = false

[profiles.readonly]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "cached"
```


`--yolo`や`danger-full-access`のように強い権限を与える設定と、実験的機能を同時に使う場合は、必ず使い捨て環境、別branch、明確な終了条件を用意する。


```text
L{0.34}L{0.36}}
項目  |  内容  |  実務上の判断
default  |  日常開発。workspace-writeとon-requestを基本にする。  |  実験機能は原則入れない。
lab  |  新機能検証。MCP、Hooks、goal、multi agentを試す。  |  失敗してもよいrepositoryまたはbranchで使う。
readonly  |  調査、仕様確認、PRレビュー。  |  書き込みや外部変更を避ける。
ci  |  非対話の定型実行。  |  出力形式、timeout、承認なし実行の境界を固定する。
danger  |  sandbox外の強い権限。  |  ローカル本番環境ではなく隔離環境でのみ検証する。
```


## /goalと長時間追跡

`/goal`は、Codexに一定の目標を追跡させる実験的な作業スタイルである。テストwatch、長いlint修正、CI failureの調査、migrationの段階確認など、状態が変わる作業を継続的に見たいときに向く。ただし、目標が曖昧だと、いつ止まるべきか、どのファイルに触ってよいか、どのコマンドを繰り返してよいかが不明になる。よいgoalは、成功条件、停止条件、変更可能範囲、禁止事項を含む。


```
/goal Enable a follow-goal run.
Goal: keep pytest -q and npm test green while auth refactoring proceeds.
Allowed changes: src/auth, tests/auth, docs/auth only.
Stop when: both test commands pass twice, or database schema changes are needed.
Do not: change secrets, push commits, alter CI configuration, or widen MCP tools.
```


#### 図解: goal文の構造

`目標` → `成功条件` → `停止条件`

_goalは完了条件まで書く。_


#### 図解: goalとwatch

`test watch` → `差分確認` → `再実行`

_継続実行はwatch系と相性がよい。_


#### 図解: goalの禁止事項

`secrets` → `push` → `CI変更`

_禁止事項を明示すると逸脱を防げる。_


#### 図解: goalの終了

`pass twice` → `human review` → `stop`

_終了条件がないgoalは危険である。_


#### 図解: goalとMCP

`docs確認` → `issue確認` → `結果要約`

_MCPは必要な文脈だけに限定する。_


## background terminalの運用

background terminalは、`npm run dev`、`pytest -f`、`cargo watch`、`tail -f`、local serverのような継続processを扱うときに便利である。注意点は、processを放置しないこと、log全体を文脈へ入れすぎないこと、portやCPUを使い続けないこと、外部公開されるserverを勝手に立てないことである。AGENTS.mdには、使ってよいwatch command、終了条件、portの制限、log要約の方針を書く。


```
# AGENTS.md
## Background terminal policy
- Use background terminals only for dev servers, test watch, or log tailing.
- Stop background processes before finishing a task.
- Do not expose ports outside localhost.
- Summarize failing test names and relevant stack traces only.
- Ask before running commands that may download dependencies or start containers.
```


#### 図解: background terminalの入口

`watch command` → `log確認` → `停止`

_継続processは終了まで管理する。_


#### 図解: log要約

`全量log` → `関連箇所` → `短い要約`

_文脈汚染を避ける。_


#### 図解: port管理

`localhost` → `衝突確認` → `終了`

_portを使うprocessは明示する。_


#### 図解: resource管理

`CPU` → `memory` → `停止`

_長時間processの資源を管理する。_


#### 図解: AGENTSへの記録

`許可command` → `禁止command` → `終了条件`

_運用規則を文書にする。_


## multi agentとサブエージェントの実験運用

multi agentは、親セッションがすべてを抱え込まず、調査、レビュー、実装、UI再現、ログ解析などを分担する設計である。実験的に導入する場合は、`max_threads`を制御し、`max_depth = 1`から始める。深いspawnや多数のagentは、費用、文脈、判断の不一致を増やす。親agentは、子agentへ明確な成果物形式を求める。たとえば「関連ファイル一覧」「リスク上位5件」「再現手順」「根拠URL」「未確認事項」を固定すると統合しやすい。


```
[agents]
max_threads = 4
max_depth = 1
job_max_runtime_seconds = 1200
```


```text
L{0.34}L{0.36}}
項目  |  内容  |  実務上の判断
`pr_explorer`  |  read-onlyで影響範囲を調べる。  |  変更しない。関連ファイルと依存関係を返す。
reviewer  |  正しさ、セキュリティ、テスト不足を見る。  |  重大度順に指摘し、推測を分ける。
`docs_researcher`  |  MCPやweb検索で公式仕様を確認する。  |  根拠、日付、未確認点を返す。
`browser_debugger`  |  UI再現、console、networkを調べる。  |  証拠を短くまとめ、実装修正は親へ委ねる。
`logs_analyst`  |  CIやobservability logを読む。  |  失敗原因候補をrank付けする。
```


#### 図解: multi agentの分担

`親` → `子agent` → `統合`

_親は統合役に集中する。_


#### 図解: max threads

`同時数` → `費用` → `文脈`

_同時数は制御して始める。_


#### 図解: max depth

`root` → `child` → `stop`

_深い再帰は避ける。_


#### 図解: 成果物形式

`観点` → `根拠` → `未確認`

_形式固定で統合しやすい。_


#### 図解: MCPの閉じ込め

`docs agent` → `browser agent` → `logs agent`

_MCPは専用agentに閉じ込める。_


## fast mode、画像生成、Apps連携、Codex MCP server

実験的または新しめの機能は、用途ごとにリスクが異なる。fast modeは作業速度を上げる方向の機能であり、承認やレビューを省きすぎると危険になる。画像生成はUI素材、図、mock、説明画像に役立つが、権利や生成物管理が必要になる。Appsやconnectorは、外部サービスとの接続権限を扱うため、個人connector、team connector、project-local設定を混同しない。Codex自身をMCP serverとして扱う構成は、Agents SDKなど外部agentからCodexの能力を呼び出す設計で使われるが、権限境界を明確にする必要がある。


```text
L{0.34}L{0.36}}
項目  |  内容  |  実務上の判断
fast mode  |  速度を優先する実験的運用。  |  低リスクbranchと強めのreviewで試す。
image generation  |  UI素材や説明画像を生成する。  |  権利、用途、保存場所を確認する。
Apps connector  |  外部サービスへ接続する。  |  scope、owner、auditを確認する。
codex mcp-server  |  CodexをMCP serverとして外部agentから呼ぶ。  |  呼び出し元agentと権限境界を明文化する。
local environment  |  Codex Cloudやlocal環境と連携する。  |  secret、network、再現性を分けて管理する。
```


#### 図解: fast modeの判断

`低リスク` → `小差分` → `review`

_速度より安全境界を優先する。_


#### 図解: 画像生成の判断

`用途` → `権利` → `保存`

_生成物にも管理方針が必要。_


#### 図解: Apps連携の判断

`connector` → `scope` → `audit`

_外部接続はscopeを確認する。_


#### 図解: Codex as MCP

`external agent` → `Codex server` → `repository`

_呼び出し元と権限を分ける。_


#### 図解: local environment

`環境` → `secret` → `再現`

_環境ごとの差を文書化する。_


---

