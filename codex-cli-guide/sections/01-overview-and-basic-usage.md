<!--
@dependency-start
contract reference
responsibility Houses the split guide section: 概要・基本操作・設定リファレンス導入.
upstream design ../source/codex_cli_guide_config_deepdive.full.md preserved generated guide body.
@dependency-end
-->

# 概要・基本操作・設定リファレンス導入

- source file: `codex_cli_guide_config_deepdive.md`
- source lines: 1-1009
- section sha256: `1f2224aa461c3680080e90aea5da5ba3d1c822e13d28a5448f2424c06f0c4e78`

<!-- split-content-start -->

---
title: "OpenAI Codex CLI 実用ガイド 設定実践完全版"
generated: "2026-05-08"
source: "TeX版から自動変換"
---

# OpenAI Codex CLI 実用ガイド 設定実践完全版

設定ファイルの書き方・構成例・MCP・Hooks・Subagents・管理設定を徹底図解

調査日: 2026-05-08（JST）

> 公式OpenAI Developersドキュメント、公式JSON schema、公式リファレンス、Codex changelogを再確認して作成。


<!-- TeX版PDFには目次があります。Markdown版では見出しナビゲーションを利用してください。 -->


---


## このPDFの前提と読み方

本書は、OpenAIが提供するCodex CLIを、ローカル端末で安全に使うための実用的な解説である。Codex CLIは、選択したディレクトリ内のコードを読み、変更し、コマンドを実行できるローカル実行型のコーディングエージェントであり、公式READMEでもnpm、Homebrew、GitHub Release経由の導入が案内されている。本文では、`codex` の対話TUI、`codex exec` の非対話実行、`mcp`、`cloud`、`app-server`、設定ファイル、承認とサンドボックス、企業向け `requirements.toml` までを扱う。


本書の「全設定項目」は、公式Configuration Referenceと公式JSON schemaを基準に、ワイルドカード表記で繰り返しキーをまとめている。たとえば `mcp_servers.<id>.args` は任意のMCPサーバIDごとに同じキー構造を持つ、という意味である。Codex CLIは更新が速いため、実運用前には `codex --help`、`codex features list`、`/debug-config`、公式schemaの確認を推奨する。


## Codex CLIとは何か

Codex CLIは、IDE拡張やWeb版Codexと同じ「コード作業を委譲する」体験を、ターミナル中心に実現するツールである。大きな特徴は、単にチャットで回答するだけではなく、ローカルのリポジトリを読んで差分を作り、テストやビルドを実行し、必要に応じてユーザーの承認を求める点にある。標準状態では、ネットワークアクセスや作業ディレクトリ外の書き込みが制限されるため、AIに作業を任せつつも、作業境界を細かく設計できる。

CLIの使い方は三層で理解すると速い。第一層は `codex` による対話TUIで、設計相談、差分確認、修正依頼を行う。第二層は `codex exec` による非対話モードで、CI、定型レビュー、JSON出力、スクリプト連携に向く。第三層はMCP、Hooks、Rules、AGENTS.md、Skills、Subagents、Pluginsなどの拡張層で、チーム標準・外部ツール・自動検査を組み込む。


## インストール、ログイン、更新

公式の基本導入は次のとおりである。


```
# npm
npm i -g @openai/codex

# Homebrew
brew install --cask codex

# 起動
codex

# npmで更新
npm i -g @openai/codex@latest
```


初回起動時には、ChatGPTアカウントまたはAPIキーで認証する。ChatGPT Plus、Pro、Business、Edu、EnterpriseのプランではCodex利用が含まれるという案内があるが、所属プラン、組織ポリシー、地域設定により挙動が異なる可能性がある。共有端末では `codex logout` を使ってローカル資格情報を削除する。認証情報の保存先は `cli_auth_credentials_store` で制御できる。


## 50枚の図解カタログ（基礎編）

以下の図は、公式仕様を理解するための概念図であり、実際のTUIスクリーンショットではない。基礎編の50点をTikZで作成している。増補編ではさらに50点を追加する。


#### 図解: 01 ローカルCodexの基本ループ

`ユーザーが依頼` → `Codexが読解・計画` → `差分とコマンドを確認`

_ローカルエージェントの基本ループ_


#### 図解: 02 インストールから初回起動

`npm/brewで導入` → `codexを実行` → `ChatGPT/APIキーで認証`

_セットアップの流れ_


#### 図解: 03 更新の考え方

`新機能/修正` → `npm i -g @openai/codex@latest` → `changelog確認`

_アップグレード手順_


#### 図解: 04 設定レイヤの優先順位

`CLI -c/flags` → `profile/project/user/system` → `built-in defaults`

_設定解決の優先順位_


#### 図解: 05 信頼済みプロジェクト

`trustedなら読み込み` → `.codex/config/hooks/rules` → `untrustedならスキップ`

_プロジェクトスコープの安全装置_


#### 図解: 06 Autoプリセット

`workspace-write` → `on-request approvals` → `外部/ネットワークは確認`

_Autoの境界_


#### 図解: 07 read-only運用

`ファイル閲覧` → `計画・説明` → `編集/実行は承認`

_安全な調査モード_


#### 図解: 08 danger-full-access

`承認なし` → `サンドボックスなし` → `外部隔離が前提`

_危険モードの位置づけ_


#### 図解: 09 対話TUI

`プロンプト入力` → `計画・差分を読む` → `承認/修正/継続`

_TUIの協働スタイル_


#### 図解: 10 非対話exec

`標準入力/引数` → `Codexが処理` → `JSON/テキスト出力`

_スクリプト化の流れ_


#### 図解: 11 resume/fork

`履歴を選択` → `再開または分岐` → `同じ文脈で継続`

_会話ライフサイクル_


#### 図解: 12 画像入力

`スクリーンショット` → `設計/エラーを読解` → `コード変更に反映`

_画像を使うタスク_


#### 図解: 13 Web検索

`cachedが既定` → `liveは--search` → `結果は不信扱い`

_Web検索モード_


#### 図解: 14 MCP STDIO

`configにcommand` → `ローカルプロセス起動` → `ツール/文脈を提供`

_STDIO MCP接続_


#### 図解: 15 MCP HTTP/OAuth

`urlを設定` → `Bearer/OAuthで認証` → `/mcpで確認`

_HTTP MCP接続_


#### 図解: 16 アプリ/コネクタ

`apps設定` → `ツール承認モード` → `破壊的操作は確認`

_Apps連携_


#### 図解: 17 プラグイン

`marketplace追加` → `pluginを導入` → `hooks/toolsを拡張`

_プラグイン拡張_


#### 図解: 18 AGENTS.md

`global指示` → `project階層指示` → `近い階層が後勝ち`

_プロジェクト指示の合成_


#### 図解: 19 Rules/execpolicy

`コマンドprefix` → `allow/prompt/deny` → `理由を提示`

_実行ポリシー_


#### 図解: 20 Hooks

`イベント発火` → `matcherで選別` → `command hook実行`

_ライフサイクル自動化_


#### 図解: 21 Subagents

`明示的に依頼` → `役割別config` → `並列に調査/実装`

_サブエージェント活用_


#### 図解: 22 Skills

`SKILL.md` → `ツール手順を読み込む` → `タスクで使い分け`

_スキル設定_


#### 図解: 23 Cloud task

`cloudで作成` → `環境で実行` → `applyで差分適用`

_Codex Cloud連携_


#### 図解: 24 app-server

`リモートで実行環境` → `WebSocketで接続` → `ローカルTUIで操作`

_リモートTUI_


#### 図解: 25 remote auth

`listen設定` → `token/JWT検証` → `TUIが安全接続`

_リモート認証_


#### 図解: 26 サンドボックス書込

`workspace root` → `writable_roots追加` → `.git/.codex保護`

_書き込み境界_


#### 図解: 27 ネットワーク制御

`既定は子プロセスOFF` → `domain/proxy設定` → `web_searchとは別`

_ネットワークの分離_


#### 図解: 28 権限プロファイル

`default_permissions` → `filesystem/network` → `再利用可能な名前`

_named permissions_


#### 図解: 29 自動承認レビュー

`承認が必要な操作` → `auto_reviewが評価` → `通過/拒否/失敗時fail closed`

_automatic approval review_


#### 図解: 30 TUIカスタム

`theme/keymap` → `status/title` → `通知設定`

_端末体験の調整_


#### 図解: 31 履歴とログ

`history.jsonl` → `log_dir` → `sqlite_home`

_ローカル状態保存_


#### 図解: 32 モデル切替

`--modelまたは/model` → `reasoning/verbosity` → `profileに保存`

_モデル運用_


#### 図解: 33 プロファイル

`profiles.<name>` → `-pで選択` → `チーム/用途別プリセット`

_profile設計_


#### 図解: 34 シェル環境

`inheritを決める` → `include/exclude/set` → `秘密漏えいを抑える`

_環境変数ポリシー_


#### 図解: 35 OTEL

`trace/metric` → `exporter設定` → `運用観測へ送る`

_観測性_


#### 図解: 36 Windows

`PowerShell native` → `elevated sandbox` → `WSL2も選択肢`

_Windows運用_


#### 図解: 37 macOS/Linux

`OS sandbox` → `deny-read/glob` → `ネットワーク境界`

_Unix系運用_


#### 図解: 38 requirements.toml

`管理者が制約` → `ユーザー上書き不可` → `互換値へ代替経路`

_管理設定_


#### 図解: 39 MCP allowlist

`名前とidentity` → `一致時のみ有効` → `不一致は無効`

_企業MCP制御_


#### 図解: 40 managed hooks

`管理dir` → `全ユーザーで強制` → `prompt leakを検査`

_管理hook_


#### 図解: 41 feature flags

`features table` → `codex features enable` → `バージョン差を確認`

_機能フラグ運用_


#### 図解: 42 review flow

`/review実行` → `別エージェントが確認` → `コミット前に修正`

_ローカルレビュー_


#### 図解: 43 diff flow

`/diff確認` → `テスト実行` → `承認して次へ`

_差分確認_


#### 図解: 44 CI read-only

`codex exec` → `read-only/never` → `レポートだけ出力`

_CI安全モード_


#### 図解: 45 CI write mode

`workspace-write` → `出力schema指定` → `パッチを成果物化`

_CI実装モード_


#### 図解: 46 設定診断

`/status` → `/debug-config` → `effective config確認`

_トラブルシュート_


#### 図解: 47 認証運用

`login status` → `keyring/file` → `共有端末はlogout`

_資格情報管理_


#### 図解: 48 秘密ファイル防御

`deny_read none` → `*.envを遮断` → `承認でも露出最小化`

_シークレット防御_


#### 図解: 49 安全な既定

`Auto/read-only` → `cached search` → `最小権限で開始`

_推奨初期値_


#### 図解: 50 拡張順序

`AGENTS→Rules` → `Hooks→MCP` → `Skills/Subagents`

_段階的な拡張ロードマップ_


---


## 基本コマンドとグローバルフラグ

Codex CLIのコマンド体系は、対話、非対話、クラウド、MCP、プラグイン、デバッグ、サンドボックス検証に分かれる。どのサブコマンドでも、設定ファイルの値は基本的に読み込まれ、CLIフラグと `-c key=value` が最上位の優先度で上書きする。危険なのは、`--yolo` や `danger-full-access` と `-a never` の組み合わせである。これは強力だが、AIが生成したコマンドに対してサンドボックスも承認も働かない。


### グローバルフラグ

```text
L{0.32} L{0.10} L{0.30}}
分類  |  キー  |  型/値  |  役割
分類  |  キー  |  型/値  |  役割
global  |  `--add-dir path`  |    |  追加ディレクトリを書き込み可能な作業ルートとして加える。複数回指定可能。
global  |  `--ask-for-approval, -a untrusted|on-request|never`  |    |  承認を求める条件を制御する。on-failure は非推奨。
global  |  `--cd, -C path`  |    |  エージェント開始前に作業ディレクトリを切り替える。
global  |  `--config, -c key=value`  |    |  この実行だけ設定値を上書きする。JSONとして解釈できる値はJSON扱い。
global  |  `--dangerously-bypass-approvals-and-sandbox, --yolo`  |    |  承認とサンドボックスを外す危険モード。外部隔離環境でのみ使う。
global  |  `--disable feature`  |    |  機能フラグを false にする。features.<name>=false と同等。
global  |  `--enable feature`  |    |  機能フラグを true にする。features.<name>=true と同等。
global  |  `--image, -i path[,path...]`  |    |  初期プロンプトに画像を添付する。複数指定可。
global  |  `--model, -m string`  |    |  既定モデルをこの実行だけ上書きする。
global  |  `--no-alt-screen`  |    |  TUIの代替画面を無効化する。
global  |  `--oss`  |    |  ローカルOSSモデルプロバイダを使う。
global  |  `--profile, -p string`  |    |  /.codex/config.toml のプロファイルを読み込む。
global  |  `--remote ws://...|wss://...`  |    |  TUIをリモート app-server WebSocket に接続する。
global  |  `--remote-auth-token-env ENV_VAR`  |    |  リモート接続時のBearerトークンを環境変数から読む。
global  |  `--sandbox, -s read-only|workspace-write|danger-full-access`  |    |  シェルコマンドのサンドボックス境界を選ぶ。
global  |  `--search`  |    |  web_search を live にしてライブWeb検索を使う。
global  |  `PROMPT`  |    |  コマンド末尾の初期プロンプト。
```

}


### 主要サブコマンド

```text
L{0.58}}
コマンド  |  用途
コマンド  |  用途
`codex`  |  対話TUIを起動。プロンプト、画像、作業ディレクトリ、承認、サンドボックス等を指定できる。
`codex app`  |  Codexデスクトップアプリ体験を開始・取得するためのコマンド。
`codex app-server`  |  ワークスペース側でWebSocketサーバを起動し、別端末のTUIから接続する。
`codex apply TASK_ID`  |  Codex Cloudタスクの差分をローカルに適用する。
`codex cloud`  |  Cloudタスクを作成・一覧・取得し、環境や試行回数を指定する。
`codex completion SHELL`  |  bash、zsh、fish、PowerShell、elvish向け補完を出力。
`codex debug app-server send-message-v2`  |  app-serverにデバッグ用メッセージを送る。
`codex debug models`  |  利用可能モデルやバンドルモデルを調べる。
`codex exec`  |  非対話モード。標準入出力、JSON、スキーマ付き出力、CIなどに使う。
`codex exec resume`  |  execの過去セッションを再開する。
`codex execpolicy`  |  コマンドがポリシールールにどう判定されるかを確認する。
`codex features list|enable|disable`  |  機能フラグを一覧・永続化・解除する。
`codex fork`  |  既存セッションから新しい枝分かれスレッドを作る。
`codex login|logout|login status`  |  ChatGPTまたはAPIキーでログインし、状態確認・ログアウトする。
`codex mcp add|get|list|login|logout|remove`  |  MCPサーバをCLIから管理する。
`codex mcp-server`  |  CodexをMCPサーバとして起動する。
`codex plugin marketplace add|remove|upgrade`  |  プラグインマーケットプレイスを追加・削除・更新する。
`codex resume`  |  対話セッションを再開する。
`codex sandbox macos|linux|windows`  |  サンドボックス実行のデバッグ・検証用サブコマンド。
`codex update`  |  更新の確認・案内。
```

}


## 対話TUIとスラッシュコマンド

`codex` を引数なしで起動すると、フルスクリーンのTUIが立ち上がる。ここでは、プロンプトを入力し、Codexの計画、ファイル差分、コマンド実行、承認要求を逐次見ながら進める。作業途中で `Tab` により追加入力やスラッシュコマンドをキューできる。長い会話では `/compact` で要点を保持しつつコンテキストを節約し、作業後は `/diff` とテスト結果を確認してからコミットする。

```text
L{0.68}}
スラッシュコマンド  |  目的
スラッシュコマンド  |  目的
`/permissions`  |  承認・サンドボックス設定を対話中に変更する。
`/sandbox-add-read-dir`  |  Windowsで追加の読み取りディレクトリを許可する。
`/agent`  |  サブエージェントのスレッドを切り替える。
`/apps`  |  アプリ・コネクタを閲覧し、プロンプトに挿入する。
`/plugins`  |  プラグインを閲覧・導入・管理する。
`/clear`  |  画面と会話をクリアして新規に始める。
`/compact`  |  長い会話を要約し、コンテキストを節約する。
`/copy`  |  最新の完了出力をコピーする。Ctrl+O相当。
`/diff`  |  Git差分と未追跡ファイルの変更を確認する。
`/exit, /quit`  |  セッションを終了する。
`/experimental`  |  実験的機能を切り替える。
`/feedback`  |  ログや診断情報を送る。
`/init`  |  AGENTS.mdのひな型を作成する。
`/logout`  |  ローカル認証を削除する。
`/mcp`  |  有効なMCPサーバを確認する。
`/mention`  |  ファイルや参照をプロンプトへ挿入する。
`/model`  |  モデルと推論設定を切り替える。
`/fast`  |  Fast modeの状態確認・有効化・無効化。
`/plan, /goal`  |  計画・ゴールの扱いを補助する。
`/personality`  |  friendly、pragmatic、noneなど応答スタイルを選ぶ。
`/ps`  |  実行中・待機中タスクを確認する。
`/stop`  |  現在のターンを停止する。
`/fork, /side`  |  会話を分岐させる。
`/resume, /new`  |  過去セッション再開または新規会話開始。
`/review`  |  作業ツリーを別Codexにレビューさせる。
`/status`  |  モデル、承認、トークン、作業ルートなどを確認。
`/debug-config`  |  設定レイヤ、要件、ポリシーの診断を表示。
`/statusline`  |  TUIフッター項目を対話的に設定。
`/title`  |  ターミナルタイトル項目を対話的に設定。
`/keymap`  |  キーバインド設定を調整。
```

}


## 非対話モードと自動化

`codex exec` は、対話TUIを開かずに1つのタスクを実行する。CIでの静的レビュー、PR説明文の生成、スキーマ付きJSON出力、既存セッションの再開などに向く。非対話では承認プロンプトが出せない場面があるため、`--ask-for-approval never` と `--sandbox read-only` のように、実行権限を明確に絞る設計が重要である。


```
# 読み取り専用でレビューだけ行う
codex exec --sandbox read-only -a never "Review this repository and summarize risks."

# workspace-writeで修正を作るが、ネットワークは別途許可しない
codex exec --sandbox workspace-write "Fix failing unit tests."

# 最終メッセージをファイルへ保存
codex exec --output-last-message result.md "Create a migration checklist."
```


## 承認、サンドボックス、ネットワーク

Codexの安全性は、技術的境界であるサンドボックスと、ユーザー確認である承認ポリシーの組み合わせで決まる。代表的には、`read-only` は読むだけ、`workspace-write` は作業ディレクトリ内の編集を許し、`danger-full-access` は外部隔離された環境向けの強い権限である。`approval_policy = "on-request"` では、Codexが必要と判断した場合や境界を越える操作で承認を求める。


`--dangerously-bypass-approvals-and-sandbox`、別名 `--yolo` は、承認もサンドボックスも外す。外部VM、コンテナ、使い捨てワークスペースなどでOSレベルの隔離を別途確保していない限り、通常の開発機では推奨しない。


## 設定ファイルの場所と優先順位

個人設定は `~/.codex/config.toml`、プロジェクト設定はリポジトリ内の `.codex/config.toml` に置く。設定優先順位は、高い順に「CLIフラグと`-c`」「`--profile`で選ぶprofile」「信頼済みプロジェクトの`.codex/config.toml`」「ユーザー設定」「システム設定」「組み込み既定値」である。未信頼プロジェクトでは、プロジェクトローカルのconfig、hooks、rulesは読み込まれない。


```
# ~/.codex/config.toml の例
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"
default_permissions = ":workspace"

[features]
shell_snapshot = true
multi_agent = true

[sandbox_workspace_write]
network_access = false
writable_roots = ["/Users/me/.pyenv/shims"]

[profiles.safe]
model = "gpt-5.5"
sandbox_mode = "read-only"
approval_policy = "on-request"
```


## 設定項目完全リファレンス（config.toml）

次の表は、公式Configuration Referenceおよび公式JSON schemaを基準にした設定キー一覧である。繰り返し要素は `<id>`、`<name>`、`<tool>`、`<index>` で表す。機能フラグはバージョン差が大きいため、`codex features list` で現在の実装状態を必ず確認する。

```text
L{0.34} L{0.18} L{0.28}}
分類  |  キー  |  型/値  |  役割
分類  |  キー  |  型/値  |  役割
基本/認証  |  `model`  |  string  |  既定モデル。gpt-5.5等、利用可能モデル名を指定。
基本/認証  |  `model_provider`  |  string  |  model_providers内または組み込みプロバイダのID。
基本/認証  |  `openai_base_url`  |  string  |  組み込みOpenAIプロバイダのAPIベースURLを上書き。
基本/認証  |  `chatgpt_base_url`  |  string  |  ChatGPT向けリクエストのベースURL。
基本/認証  |  `forced_login_method`  |  chatgpt | api  |  ログイン方式をChatGPTまたはAPIキーに制限。
基本/認証  |  `forced_chatgpt_workspace_id`  |  string  |  ChatGPTログインを特定ワークスペースに制限。
基本/認証  |  `cli_auth_credentials_store`  |  file | keyring | auto | ephemeral  |  CLI認証情報の保存先。
基本/認証  |  `check_for_update_on_startup`  |  boolean  |  起動時アップデート確認。集中管理環境ではfalseにできる。
基本/認証  |  `profile`  |  string  |  起動時に使うprofiles.<name>を指定。
基本/認証  |  `profiles.<name>.*`  |  mixed  |  プロファイル単位でモデル、サンドボックス、TUIなどを上書き。
モデル/推論  |  `model_reasoning_effort`  |  minimal | low | medium | high  |  対応モデルの推論努力量。
モデル/推論  |  `model_reasoning_summary`  |  auto | concise | detailed | none  |  推論サマリ表示の制御。
モデル/推論  |  `model_supports_reasoning_summaries`  |  boolean  |  モデルの推論サマリ対応を明示上書き。
モデル/推論  |  `model_verbosity`  |  low | medium | high  |  Responses API系モデルの応答冗長度。
モデル/推論  |  `model_context_window`  |  integer  |  モデルのコンテキスト長をトークン数で上書き。
モデル/推論  |  `model_auto_compact_token_limit`  |  integer  |  自動コンパクトを開始するトークン閾値。
モデル/推論  |  `model_catalog_json`  |  string(path)  |  起動時に読むモデルカタログJSON。
モデル/推論  |  `model_instructions_file`  |  string(path)  |  モデル用組み込み指示を置き換えるファイル。通常非推奨。
モデル/推論  |  `plan_mode_reasoning_effort`  |  minimal | low | medium | high  |  計画モード時の推論努力量。
モデル/推論  |  `review_model`  |  string  |  /reviewで使うモデルを上書き。
モデル/推論  |  `oss_provider`  |  string  |  ollama、lmstudio等のローカルOSSプロバイダ選択。
モデル/推論  |  `service_tier`  |  fast | flex | auto等  |  新規ターンのサービス階層。
プロバイダ  |  `model_providers.<id>.name`  |  string  |  プロバイダの表示名。
プロバイダ  |  `model_providers.<id>.base_url`  |  string(URL)  |  OpenAI互換APIのベースURL。
プロバイダ  |  `model_providers.<id>.env_key`  |  string  |  APIキーを読む環境変数名。
プロバイダ  |  `model_providers.<id>.env_key_instructions`  |  string  |  APIキー設定の案内文。
プロバイダ  |  `model_providers.<id>.http_headers`  |  object  |  固定HTTPヘッダ。秘密値には非推奨。
プロバイダ  |  `model_providers.<id>.env_http_headers`  |  object  |  環境変数から値を読むHTTPヘッダ。
プロバイダ  |  `model_providers.<id>.query_params`  |  object  |  ベースURLへ追加するクエリパラメータ。
プロバイダ  |  `model_providers.<id>.experimental_bearer_token`  |  string  |  Bearerトークンを直接指定。安全性上env_key推奨。
プロバイダ  |  `model_providers.<id>.requires_openai_auth`  |  boolean  |  OpenAI認証を要求するか。
プロバイダ  |  `model_providers.<id>.wire_api`  |  responses | chat  |  プロバイダが期待するワイヤAPI。
プロバイダ  |  `model_providers.<id>.supports_websockets`  |  boolean  |  Responses WebSocket対応の有無。
プロバイダ  |  `model_providers.<id>.request_max_retries`  |  integer  |  HTTPリクエスト再試行回数。
プロバイダ  |  `model_providers.<id>.stream_max_retries`  |  integer  |  ストリーム切断時の再接続試行回数。
プロバイダ  |  `model_providers.<id>.stream_idle_timeout_ms`  |  integer  |  ストリーム無通信タイムアウト。
プロバイダ  |  `model_providers.<id>.websocket_connect_timeout_ms`  |  integer  |  WebSocket接続タイムアウト。
プロバイダ  |  `model_providers.<id>.auth.command`  |  string  |  外部コマンドでBearerトークンを得る。
プロバイダ  |  `model_providers.<id>.auth.args`  |  array<string>  |  auth.commandの引数。
プロバイダ  |  `model_providers.<id>.auth.cwd`  |  string(path)  |  auth.command実行ディレクトリ。
プロバイダ  |  `model_providers.<id>.auth.refresh_interval_ms`  |  integer  |  コマンドトークンの更新間隔。
プロバイダ  |  `model_providers.<id>.auth.timeout_ms`  |  integer  |  auth.commandのタイムアウト。
プロバイダ  |  `model_providers.<id>.aws.profile`  |  string  |  Amazon Bedrock等で使うAWSプロファイル。
プロバイダ  |  `model_providers.<id>.aws.region`  |  string  |  AWSリージョン。
承認/サンドボックス  |  `approval_policy`  |  untrusted | on-request | never | granular  |  シェル実行や権限昇格前に人へ確認する条件。
承認/サンドボックス  |  `approval_policy.granular.sandbox_approval`  |  boolean  |  サンドボックス昇格承認を許可するか。
承認/サンドボックス  |  `approval_policy.granular.rules`  |  boolean  |  execpolicyルール由来の承認を許可するか。
承認/サンドボックス  |  `approval_policy.granular.mcp_elicitations`  |  boolean  |  MCPの承認促しを許可するか。
承認/サンドボックス  |  `approval_policy.granular.request_permissions`  |  boolean  |  request_permissions由来の承認を許可するか。
承認/サンドボックス  |  `approval_policy.granular.skill_approval`  |  boolean  |  スキルスクリプト実行承認を許可するか。
承認/サンドボックス  |  `approvals_reviewer`  |  user | auto_review | guardian_subagent  |  承認依頼のレビュアー。auto_reviewは自動レビュー。
承認/サンドボックス  |  `auto_review.policy`  |  string  |  自動レビューのローカルポリシー指示。管理要件が優先。
承認/サンドボックス  |  `sandbox_mode`  |  read-only | workspace-write | danger-full-access  |  コマンド実行時の技術的境界。
承認/サンドボックス  |  `sandbox_workspace_write.writable_roots`  |  array<string>  |  workspace-write時の追加書き込み可能ルート。
承認/サンドボックス  |  `sandbox_workspace_write.network_access`  |  boolean  |  workspace-write時に子プロセスネットワークを許す。
承認/サンドボックス  |  `sandbox_workspace_write.exclude_tmpdir_env_var`  |  boolean  |  TMPDIRを作業書き込みから除外。
承認/サンドボックス  |  `sandbox_workspace_write.exclude_slash_tmp`  |  boolean  |  /tmpを作業書き込みから除外。
承認/サンドボックス  |  `default_permissions`  |  string  |  :read-only、:workspace、:danger-no-sandboxまたはカスタム名。
承認/サンドボックス  |  `permissions.<name>.filesystem`  |  table  |  パスやglobごとのread/write/none設定。
承認/サンドボックス  |  `permissions.<name>.filesystem.:project_roots.<glob>`  |  read | write | none  |  プロジェクトルート相対のファイルアクセス権。
承認/サンドボックス  |  `permissions.<name>.filesystem.<path-or-glob>`  |  read | write | none | object  |  任意パス/グロブへのアクセス権。
承認/サンドボックス  |  `permissions.<name>.filesystem.glob_scan_max_depth`  |  integer  |  ** glob展開の最大深度。
承認/サンドボックス  |  `permissions.<name>.network.enabled`  |  boolean  |  カスタムネットワーク権限を有効化。
承認/サンドボックス  |  `permissions.<name>.network.mode`  |  limited | full  |  ネットワークを限定許可か全面許可か。
承認/サンドボックス  |  `permissions.<name>.network.domains`  |  object  |  ドメイン別allow/deny。
承認/サンドボックス  |  `permissions.<name>.network.allow_local_binding`  |  boolean  |  ローカルポート待受を許可。
承認/サンドボックス  |  `permissions.<name>.network.allow_upstream_proxy`  |  boolean  |  上流プロキシ利用を許可。
承認/サンドボックス  |  `permissions.<name>.network.proxy_url`  |  string(URL)  |  HTTP/HTTPSプロキシ。
承認/サンドボックス  |  `permissions.<name>.network.socks_url`  |  string(URL)  |  SOCKSプロキシ。
承認/サンドボックス  |  `permissions.<name>.network.enable_socks5`  |  boolean  |  SOCKS5利用を有効化。
承認/サンドボックス  |  `permissions.<name>.network.enable_socks5_udp`  |  boolean  |  SOCKS5 UDPを有効化。
承認/サンドボックス  |  `permissions.<name>.network.unix_sockets`  |  object  |  Unixソケット別allow/none。
承認/サンドボックス  |  `permissions.<name>.network.dangerously_allow_all_unix_sockets`  |  boolean  |  全Unixソケット許可。危険。
承認/サンドボックス  |  `permissions.<name>.network.dangerously_allow_non_loopback_proxy`  |  boolean  |  非loopbackプロキシを許可。危険。
承認/サンドボックス  |  `allow_login_shell`  |  boolean  |  モデルがlogin shellを要求できるか。
TUI/対話  |  `tui.alternate_screen`  |  auto | always | never  |  代替画面バッファの利用方法。
TUI/対話  |  `tui.animations`  |  boolean  |  TUIアニメーション。
TUI/対話  |  `tui.keymap.<context>.<action>`  |  string | array<string>  |  global/composer/editor/list/pager等のキーバインド。空配列で解除。
TUI/対話  |  `tui.model_availability_nux.<model>`  |  integer  |  モデル利用案内表示の状態。
TUI/対話  |  `tui.notification_condition`  |  unfocused | always  |  通知を未フォーカス時のみ/常時にする。
TUI/対話  |  `tui.notification_method`  |  auto | osc9 | bel  |  端末通知方式。
TUI/対話  |  `tui.notifications`  |  boolean | array<string>  |  TUI通知の有効化や対象指定。
TUI/対話  |  `tui.raw_output_mode`  |  boolean  |  コピーしやすい生スクロールバックモードで開始。
TUI/対話  |  `tui.session_picker_view`  |  string  |  resume/forkピッカーの表示方式。
TUI/対話  |  `tui.show_tooltips`  |  boolean  |  起動時ツールチップ表示。
TUI/対話  |  `tui.status_line`  |  array<string>  |  フッターに表示する項目順。
TUI/対話  |  `tui.status_line_use_colors`  |  boolean  |  テーマ色でステータスラインを描画。
TUI/対話  |  `tui.terminal_title`  |  array<string>  |  端末タイトルに表示する項目。
TUI/対話  |  `tui.terminal_resize_reflow_max_rows`  |  integer  |  リサイズ再描画に使う行数上限。
TUI/対話  |  `tui.theme`  |  string  |  シンタックスハイライトテーマ。
TUI/対話  |  `tui.vim_mode_default`  |  boolean  |  コンポーザをVim modeで開始。
TUI/対話  |  `disable_paste_burst`  |  boolean  |  高速貼り付け検出を無効化。
TUI/対話  |  `file_opener`  |  string/enum  |  モデル出力のファイル引用を開くURIスキーム。
TUI/対話  |  `personality`  |  friendly | pragmatic | none  |  既定のコミュニケーションスタイル。
features  |  `features.apply_patch_freeform`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.apply_patch_streaming_events`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.apps`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.apps_mcp_path_override`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.auth_elicitation`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.browser_use`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.browser_use_external`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.builtin_mcp`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.child_agents_md`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.chronicle`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.code_mode`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.code_mode_only`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.codex_git_commit`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.hooks`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.collab`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.collaboration_modes`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.computer_use`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.connectors`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.default_mode_request_user_input`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.elevated_windows_sandbox`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.enable_experimental_windows_sandbox`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.enable_fanout`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.enable_mcp_apps`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.enable_request_compression`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.exec_permission_approvals`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.experimental_use_freeform_apply_patch`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.experimental_use_unified_exec_tool`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.experimental_windows_sandbox`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.external_migration`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.fast_mode`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.goals`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.guardian_approval`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.hooks`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.image_detail_original`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.image_generation`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.in_app_browser`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.include_apply_patch_tool`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.js_repl`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.js_repl_tools_only`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.memories`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.memory_tool`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.multi_agent`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.multi_agent_v2`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.personality`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.plugin_hooks`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.plugins`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.prevent_idle_sleep`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.realtime_conversation`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.remote_compaction_v2`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.remote_control`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.remote_models`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.remote_plugin`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.request_permissions`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.request_permissions_tool`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.request_rule`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.responses_websocket_response_processed`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.responses_websockets`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.responses_websockets_v2`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.runtime_metrics`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.search_tool`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.shell_snapshot`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.shell_tool`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.shell_zsh_fork`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.skill_env_var_dependency_prompt`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.skill_mcp_dependency_install`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.sqlite`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.steer`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.telepathy`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.terminal_resize_reflow`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.tool_call_mcp_elicitation`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.tool_search`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.tool_search_always_defer_mcp_tools`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.tool_suggest`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.tui_app_server`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.unavailable_dummy_tools`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.undo`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.unified_exec`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.use_legacy_landlock`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.use_linux_sandbox_bwrap`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.web_search`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.web_search_cached`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.web_search_request`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.workspace_dependencies`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
features  |  `features.workspace_owner_usage_nudge`  |  boolean / object  |  機能フラグ。バージョンにより実験的・非公開・非推奨のものを含む。
Web/ツール  |  `web_search`  |  disabled | cached | live  |  Web検索ツールのモード。cachedが既定、--searchでlive。
Web/ツール  |  `tools.web_search`  |  boolean  |  Web検索ツールの有効化。旧/補助設定。
Web/ツール  |  `tools.view_image`  |  boolean  |  画像閲覧ツールの有効化。
Web/ツール  |  `tools.<name>`  |  mixed  |  ツール別の補助設定。
Web/ツール  |  `tool_output_token_limit`  |  integer  |  ツール出力を会話へ入れるトークン予算。
Web/ツール  |  `tool_suggest.discoverables`  |  array/object  |  導入候補ツールの提示設定。
Web/ツール  |  `tool_suggest.disabled_tools`  |  array<string>  |  提案対象から外すツール。
MCP/Apps/Plugins  |  `mcp_servers.<id>.command`  |  string  |  STDIO MCPサーバの起動コマンド。
MCP/Apps/Plugins  |  `mcp_servers.<id>.args`  |  array<string>  |  STDIO MCPサーバの引数。
MCP/Apps/Plugins  |  `mcp_servers.<id>.env`  |  object  |  MCPサーバへ渡す環境変数。
MCP/Apps/Plugins  |  `mcp_servers.<id>.env_vars`  |  array<string|object>  |  親環境から転送する環境変数。
MCP/Apps/Plugins  |  `mcp_servers.<id>.cwd`  |  string(path)  |  MCPサーバ起動ディレクトリ。
MCP/Apps/Plugins  |  `mcp_servers.<id>.url`  |  string(URL)  |  Streamable HTTP MCPサーバURL。
MCP/Apps/Plugins  |  `mcp_servers.<id>.bearer_token_env_var`  |  string  |  Bearerトークンを読む環境変数名。
MCP/Apps/Plugins  |  `mcp_servers.<id>.http_headers`  |  object  |  HTTP MCPの固定ヘッダ。
MCP/Apps/Plugins  |  `mcp_servers.<id>.env_http_headers`  |  object  |  HTTPヘッダを環境変数から読む。
MCP/Apps/Plugins  |  `mcp_servers.<id>.enabled`  |  boolean  |  MCPサーバを有効/無効。
MCP/Apps/Plugins  |  `mcp_servers.<id>.required`  |  boolean  |  起動失敗時に必須扱いにする。
MCP/Apps/Plugins  |  `mcp_servers.<id>.startup_timeout_ms`  |  integer  |  MCPサーバ起動待ちタイムアウト。
MCP/Apps/Plugins  |  `mcp_servers.<id>.startup_timeout_sec`  |  integer  |  旧秒単位起動タイムアウト。
MCP/Apps/Plugins  |  `mcp_servers.<id>.tool_timeout_sec`  |  integer  |  MCPツール呼び出しタイムアウト。
MCP/Apps/Plugins  |  `mcp_servers.<id>.enabled_tools`  |  array<string>  |  利用を許可するツール名。
MCP/Apps/Plugins  |  `mcp_servers.<id>.disabled_tools`  |  array<string>  |  利用を禁止するツール名。
MCP/Apps/Plugins  |  `mcp_servers.<id>.tools.<tool>.approval_mode`  |  auto | prompt | approve  |  MCPツール個別承認モード。
MCP/Apps/Plugins  |  `mcp_servers.<id>.experimental_environment`  |  local | remote等  |  リモート実行環境でSTDIOサーバを起動する実験設定。
MCP/Apps/Plugins  |  `mcp_servers.<id>.oauth_resource`  |  string  |  OAuth resource指定。
MCP/Apps/Plugins  |  `mcp_servers.<id>.scopes`  |  array<string>  |  OAuth scope。
MCP/Apps/Plugins  |  `mcp_oauth_callback_port`  |  integer  |  OAuthローカルコールバック固定ポート。
MCP/Apps/Plugins  |  `mcp_oauth_callback_url`  |  string(URL)  |  OAuthリダイレクトURI上書き。
MCP/Apps/Plugins  |  `mcp_oauth_credentials_store`  |  keyring | file | auto  |  MCP OAuth認証情報の保存先。
MCP/Apps/Plugins  |  `apps._default.enabled`  |  boolean  |  全アプリの既定有効状態。
MCP/Apps/Plugins  |  `apps._default.destructive_enabled`  |  boolean  |  destructive_hint付きツールを既定許可するか。
MCP/Apps/Plugins  |  `apps._default.open_world_enabled`  |  boolean  |  open_world_hint付きツールを既定許可するか。
MCP/Apps/Plugins  |  `apps.<id>.enabled`  |  boolean  |  特定アプリを表示・利用するか。
MCP/Apps/Plugins  |  `apps.<id>.default_tools_enabled`  |  boolean  |  アプリ内ツールを既定有効にするか。
MCP/Apps/Plugins  |  `apps.<id>.default_tools_approval_mode`  |  auto | prompt | approve  |  アプリ内ツールの既定承認モード。
MCP/Apps/Plugins  |  `apps.<id>.destructive_enabled`  |  boolean  |  特定アプリの破壊的ツール許可。
MCP/Apps/Plugins  |  `apps.<id>.open_world_enabled`  |  boolean  |  特定アプリの外部世界アクセスツール許可。
MCP/Apps/Plugins  |  `apps.<id>.tools.<tool>.enabled`  |  boolean  |  アプリツール個別有効化。
MCP/Apps/Plugins  |  `apps.<id>.tools.<tool>.approval_mode`  |  auto | prompt | approve  |  アプリツール個別承認モード。
MCP/Apps/Plugins  |  `plugins.<name>.*`  |  object  |  インストール済みプラグインの設定。
MCP/Apps/Plugins  |  `marketplaces.<name>.*`  |  object  |  プラグインマーケットプレイスのsource/ref/sparse情報。
エージェント/スキル/記憶  |  `agents.<name>.config_file`  |  string(path)  |  ロール別TOML設定レイヤ。
エージェント/スキル/記憶  |  `agents.<name>.description`  |  string  |  サブエージェント選択時のロール説明。
エージェント/スキル/記憶  |  `agents.<name>.nickname_candidates`  |  array<string>  |  生成エージェントの表示名候補。
エージェント/スキル/記憶  |  `agents.interrupt_message`  |  boolean  |  中断時にモデル可視メッセージを残すか。
エージェント/スキル/記憶  |  `agents.job_max_runtime_seconds`  |  integer  |  CSV並列ジョブの既定最大実行秒。
エージェント/スキル/記憶  |  `agents.max_depth`  |  integer  |  サブエージェントのネスト深度上限。
エージェント/スキル/記憶  |  `agents.max_threads`  |  integer  |  同時に開けるエージェントスレッド上限。
エージェント/スキル/記憶  |  `skills.config`  |  array<object>  |  スキル単位の有効化上書き。
エージェント/スキル/記憶  |  `skills.config.<index>.enabled`  |  boolean  |  対象スキルの有効/無効。
エージェント/スキル/記憶  |  `skills.config.<index>.path`  |  string(path)  |  SKILL.mdを含むスキルフォルダ。
エージェント/スキル/記憶  |  `memories.use_memories`  |  boolean  |  メモリ注入指示を使うか。
エージェント/スキル/記憶  |  `memories.generate_memories`  |  boolean  |  新規スレッドからメモリを生成するか。
エージェント/スキル/記憶  |  `memories.extract_model`  |  string  |  スレッド要約/抽出用モデル。
エージェント/スキル/記憶  |  `memories.consolidation_model`  |  string  |  メモリ統合用モデル。
エージェント/スキル/記憶  |  `memories.disable_on_external_context`  |  boolean  |  外部文脈があるスレッドでメモリを汚染扱いにする。
エージェント/スキル/記憶  |  `memories.max_raw_memories_for_consolidation`  |  integer  |  統合対象の生メモリ上限。
エージェント/スキル/記憶  |  `memories.max_rollout_age_days`  |  integer  |  メモリ候補スレッドの最大日数。
エージェント/スキル/記憶  |  `memories.max_rollouts_per_startup`  |  integer  |  起動時に処理する候補数上限。
エージェント/スキル/記憶  |  `memories.max_unused_days`  |  integer  |  未使用メモリの選択期限。
エージェント/スキル/記憶  |  `memories.min_rate_limit_remaining_percent`  |  integer  |  メモリ処理を行う残りレート制限割合。
エージェント/スキル/記憶  |  `memories.min_rollout_idle_hours`  |  integer  |  スレッド最終活動からメモリ化までの待ち時間。
AGENTS/プロジェクト/履歴  |  `instructions`  |  string  |  システム指示。
AGENTS/プロジェクト/履歴  |  `developer_instructions`  |  string  |  developerロールに入る追加指示。
AGENTS/プロジェクト/履歴  |  `compact_prompt`  |  string  |  会話圧縮時のプロンプト。
AGENTS/プロジェクト/履歴  |  `experimental_compact_prompt_file`  |  string(path)  |  圧縮プロンプトを読むファイル。
AGENTS/プロジェクト/履歴  |  `history.persistence`  |  save-all | none  |  履歴JSONLへ保存するか。
AGENTS/プロジェクト/履歴  |  `history.max_bytes`  |  integer  |  履歴ファイルの最大バイト数。
AGENTS/プロジェクト/履歴  |  `project_doc_alternate route_filenames`  |  array<string>  |  AGENTS.mdがない時に探す代替ファイル名。
AGENTS/プロジェクト/履歴  |  `project_doc_max_bytes`  |  integer  |  AGENTS.md由来指示の読み込み上限。
AGENTS/プロジェクト/履歴  |  `project_root_markers`  |  array<string>  |  プロジェクトルート検出マーカー。既定.git。
AGENTS/プロジェクト/履歴  |  `projects.<path>.trust_level`  |  trusted | untrusted  |  プロジェクトスコープ.codex層の信頼状態。
AGENTS/プロジェクト/履歴  |  `log_dir`  |  string(path)  |  codex-tui.log等のログ出力先。
AGENTS/プロジェクト/履歴  |  `sqlite_home`  |  string(path)  |  SQLite状態DBの保存先。
Hooks/Rules/環境  |  `hooks`  |  table  |  config.toml内インラインhooks。hooks.jsonと同じイベントスキーマ。
Hooks/Rules/環境  |  `hooks.SessionStart`  |  array<table>  |  セッション開始時フック。
Hooks/Rules/環境  |  `hooks.PreToolUse`  |  array<table>  |  ツール実行前フック。
Hooks/Rules/環境  |  `hooks.PostToolUse`  |  array<table>  |  ツール実行後フック。
Hooks/Rules/環境  |  `hooks.PermissionRequest`  |  array<table>  |  承認要求時フック。
Hooks/Rules/環境  |  `hooks.UserPromptSubmit`  |  array<table>  |  ユーザープロンプト送信時フック。
Hooks/Rules/環境  |  `hooks.Stop`  |  array<table>  |  ターン停止時フック。
Hooks/Rules/環境  |  `hooks.PreCompact`  |  array<table>  |  コンパクト前フック。
Hooks/Rules/環境  |  `hooks.PostCompact`  |  array<table>  |  コンパクト後フック。
Hooks/Rules/環境  |  `hooks.<Event>[].matcher`  |  string  |  対象ツールや条件のマッチャ。
Hooks/Rules/環境  |  `hooks.<Event>[].hooks`  |  array<table>  |  実行するハンドラ群。
Hooks/Rules/環境  |  `hooks.<Event>[].hooks[].type`  |  command | prompt | agent  |  ハンドラ種別。commandが実行対象。
Hooks/Rules/環境  |  `hooks.<Event>[].hooks[].command`  |  string  |  実行するコマンド。
Hooks/Rules/環境  |  `hooks.<Event>[].hooks[].timeout`  |  integer  |  ハンドラのタイムアウト。
Hooks/Rules/環境  |  `hooks.<Event>[].hooks[].async`  |  boolean  |  非同期扱い。
Hooks/Rules/環境  |  `hooks.state.<id>.enabled`  |  boolean  |  hook信頼状態/有効状態。
Hooks/Rules/環境  |  `hooks.state.<id>.trusted_hash`  |  string  |  hook信頼ハッシュ。
Hooks/Rules/環境  |  `shell_environment_policy.inherit`  |  all | core | none等  |  子プロセスへ継承する環境の範囲。
Hooks/Rules/環境  |  `shell_environment_policy.include_only`  |  array<string>  |  転送する環境変数だけを列挙。
Hooks/Rules/環境  |  `shell_environment_policy.exclude`  |  array<string>  |  除外する環境変数。
Hooks/Rules/環境  |  `shell_environment_policy.set`  |  object  |  子プロセスへ明示設定する環境変数。
Hooks/Rules/環境  |  `shell_environment_policy.ignore_default_excludes`  |  boolean  |  既定の秘密除外リストを無視。
Hooks/Rules/環境  |  `shell_environment_policy.experimental_use_profile`  |  boolean  |  プロファイルベース環境を使う実験設定。
通知/観測/その他  |  `analytics.enabled`  |  boolean  |  分析収集を有効/無効。
通知/観測/その他  |  `feedback.enabled`  |  boolean  |  フィードバックフローを有効/無効。
通知/観測/その他  |  `notify`  |  array<string>  |  通知用に起動する外部コマンド。
通知/観測/その他  |  `otel.environment`  |  string  |  OpenTelemetryのenvironment属性。
通知/観測/その他  |  `otel.exporter`  |  string  |  既定エクスポータ設定。
通知/観測/その他  |  `otel.metrics_exporter`  |  string  |  メトリクス用エクスポータ。
通知/観測/その他  |  `otel.trace_exporter`  |  string  |  トレース用エクスポータ。
通知/観測/その他  |  `otel.exporter.<id>.endpoint`  |  string(URL)  |  OTEL送信先。
通知/観測/その他  |  `otel.exporter.<id>.protocol`  |  string  |  grpc/http等のプロトコル。
通知/観測/その他  |  `otel.exporter.<id>.headers`  |  object  |  OTELヘッダ。
通知/観測/その他  |  `otel.exporter.<id>.tls.ca-certificate`  |  string(path)  |  CA証明書。
通知/観測/その他  |  `otel.exporter.<id>.tls.client-certificate`  |  string(path)  |  クライアント証明書。
通知/観測/その他  |  `otel.exporter.<id>.tls.client-private-key`  |  string(path)  |  クライアント秘密鍵。
通知/観測/その他  |  `otel.log_user_prompt`  |  boolean  |  ユーザープロンプトを観測ログに含めるか。
通知/観測/その他  |  `hide_agent_reasoning`  |  boolean  |  AgentReasoningイベントを隠す。
通知/観測/その他  |  `show_raw_agent_reasoning`  |  boolean  |  生推論コンテンツを表示。
通知/観測/その他  |  `suppress_unstable_features_warning`  |  boolean  |  不安定機能の警告を抑制。
通知/観測/その他  |  `commit_attribution`  |  string  |  Codex Git commit用のCo-authored-by等。
通知/観測/その他  |  `include_apps_instructions`  |  boolean  |  apps関連developer blockを注入するか。
通知/観測/その他  |  `include_environment_context`  |  boolean  |  環境コンテキストを注入するか。
通知/観測/その他  |  `include_permissions_instructions`  |  boolean  |  権限説明を注入するか。
通知/観測/その他  |  `background_terminal_max_timeout`  |  integer  |  バックグラウンド端末出力の最大ポーリング時間。
通知/観測/その他  |  `debug.config_lockfile.export_dir`  |  string(path)  |  実効設定ロックファイルの出力先。
通知/観測/その他  |  `debug.config_lockfile.load_path`  |  string(path)  |  再現用に読み込む設定ロック。
通知/観測/その他  |  `debug.config_lockfile.allow_codex_version_mismatch`  |  boolean  |  異なるCodex版のロック再生を許可。
通知/観測/その他  |  `debug.config_lockfile.save_fields_resolved_from_model_catalog`  |  boolean  |  モデルカタログ解決値も保存。
通知/観測/その他  |  `ghost_snapshot.*`  |  mixed  |  互換目的の旧ゴーストスナップショット設定。
通知/観測/その他  |  `notice.*`  |  mixed  |  移行案内や警告の表示済み状態。
Windows/Realtime/実験  |  `windows.sandbox`  |  unelevated | elevated  |  Windowsネイティブサンドボックス方式。
Windows/Realtime/実験  |  `windows.sandbox_private_desktop`  |  boolean  |  Windowsで子プロセスをprivate desktop上で実行。
Windows/Realtime/実験  |  `windows_wsl_setup_acknowledged`  |  boolean  |  Windows/WSLオンボーディング確認済み状態。
Windows/Realtime/実験  |  `zsh_path`  |  string(path)  |  zsh-exec-bridge用patched zshの絶対パス。
Windows/Realtime/実験  |  `audio`  |  table  |  Realtime voiceのローカル音声デバイス設定。
Windows/Realtime/実験  |  `realtime`  |  table  |  Realtime WebSocketセッション選択の実験設定。
Windows/Realtime/実験  |  `experimental_realtime_start_instructions`  |  string  |  Realtime開始指示を置換。実験/非推奨。
Windows/Realtime/実験  |  `experimental_realtime_ws_backend_prompt`  |  string  |  Realtime WSバックエンド指示を置換。実験。
Windows/Realtime/実験  |  `experimental_realtime_ws_base_url`  |  string(URL)  |  Realtime WSのベースURL上書き。実験。
Windows/Realtime/実験  |  `experimental_realtime_ws_model`  |  string  |  Realtime WSモデルを指定。実験。
Windows/Realtime/実験  |  `experimental_realtime_ws_startup_context`  |  string  |  Realtime起動文脈を置換。実験。
Windows/Realtime/実験  |  `experimental_thread_config_endpoint`  |  string(URL)  |  thread-scoped config取得先。実験。
Windows/Realtime/実験  |  `experimental_thread_store`  |  table  |  スレッドストア実装選択。実験。
Windows/Realtime/実験  |  `experimental_thread_store_endpoint`  |  string(URL)  |  リモートスレッドストアURL。実験。
Windows/Realtime/実験  |  `experimental_use_freeform_apply_patch`  |  boolean  |  freeform apply_patchの実験的利用。
Windows/Realtime/実験  |  `experimental_use_unified_exec_tool`  |  boolean  |  unified exec toolの旧実験キー。
```

}


## 管理者向け requirements.toml

`requirements.toml` は、ユーザーが上書きできない制約を管理者が適用するためのファイルである。対象は、承認ポリシー、サンドボックス、Web検索、MCP allowlist、管理hooks、rules、featuresなどである。Business/Enterpriseではクラウド管理要件、MDM、システムファイルなど複数レイヤの要件が適用されることがある。

```text
L{0.32} L{0.20} L{0.24}}
分類  |  キー  |  型/値  |  役割
分類  |  キー  |  型/値  |  役割
requirements.toml  |  `allowed_approval_policies`  |  array<string>  |  許可するapproval_policy。untrusted/on-request/never/granular等。
requirements.toml  |  `allowed_approvals_reviewers`  |  array<string>  |  許可するapprovals_reviewer。user/auto_review等。
requirements.toml  |  `allowed_sandbox_modes`  |  array<string>  |  許可するsandbox_mode。
requirements.toml  |  `allowed_web_search_modes`  |  array<string>  |  許可するweb_search。disabledは常に許可。
requirements.toml  |  `features`  |  table  |  機能フラグの固定値。
requirements.toml  |  `features.<name>`  |  boolean  |  canonical feature keyを有効/無効に固定。
requirements.toml  |  `features.browser_use`  |  boolean  |  Browser Use/Browser Agentを無効化可能。
requirements.toml  |  `features.computer_use`  |  boolean  |  Computer Use関連を無効化可能。
requirements.toml  |  `features.in_app_browser`  |  boolean  |  アプリ内ブラウザpaneを無効化可能。
requirements.toml  |  `guardian_policy_config`  |  string  |  自動レビュー用管理Markdownポリシー。ローカルauto_review.policyより優先。
requirements.toml  |  `hooks`  |  table  |  管理者強制のライフサイクルフック。
requirements.toml  |  `hooks.<Event>`  |  array<table>  |  PreToolUse等イベントごとのmatcher group。
requirements.toml  |  `hooks.<Event>[].hooks`  |  array<table>  |  管理hookハンドラ。command hookが実行対象。
requirements.toml  |  `hooks.managed_dir`  |  string(abs path)  |  macOS/Linuxの管理hookスクリプトディレクトリ。
requirements.toml  |  `hooks.windows_managed_dir`  |  string(abs path)  |  Windowsの管理hookスクリプトディレクトリ。
requirements.toml  |  `mcp_servers`  |  table  |  有効化可能なMCPサーバallowlist。
requirements.toml  |  `mcp_servers.<id>.identity`  |  table  |  許可MCPの同一性。名前とidentityが一致した場合のみ有効。
requirements.toml  |  `mcp_servers.<id>.identity.command`  |  string  |  STDIO MCP identity用コマンド。
requirements.toml  |  `mcp_servers.<id>.identity.url`  |  string(URL)  |  HTTP MCP identity用URL。
requirements.toml  |  `permissions.filesystem.deny_read`  |  array<string>  |  読み取り禁止パス/グロブ。
requirements.toml  |  `remote_sandbox_config`  |  array<table>  |  ホスト名パターン別リモートサンドボックス制約。
requirements.toml  |  `remote_sandbox_config[].hostname_patterns`  |  array<string>  |  制約対象ホスト名パターン。
requirements.toml  |  `remote_sandbox_config[].allowed_sandbox_modes`  |  array<string>  |  そのホストで許すsandbox_mode。
requirements.toml  |  `rules`  |  table  |  execpolicy/rulesの管理設定。
requirements.toml  |  `rules.prefix_rules`  |  array<table>  |  コマンド先頭トークンでprompt/deny等を判定。
requirements.toml  |  `rules.prefix_rules[].pattern`  |  array<table>  |  トークン列のマッチパターン。
requirements.toml  |  `rules.prefix_rules[].pattern[].token`  |  string  |  固定トークン。
requirements.toml  |  `rules.prefix_rules[].pattern[].any_of`  |  array<string>  |  いずれか一致するトークン。
requirements.toml  |  `rules.prefix_rules[].decision`  |  allow | prompt | deny等  |  一致時の判断。
requirements.toml  |  `rules.prefix_rules[].justification`  |  string  |  ユーザーへ示す理由。
```

}


## AGENTS.md、Rules、Hooks、MCP、Skills、Subagents


### AGENTS.md

`AGENTS.md` は、リポジトリ固有の作業規約をCodexへ渡す仕組みである。Codexは起動時に、まずCodex homeのグローバル指示を読み、次にプロジェクトルートから現在ディレクトリまでの階層をたどって `AGENTS.override.md`、`AGENTS.md`、代替ファイル名を読む。近いディレクトリの内容ほど後ろに連結されるため、局所ルールが全体ルールを上書きしやすい。


### Rules

Rulesまたはexecpolicyは、モデルが提案したコマンドをprefixやパターンで判定する。たとえば、`rm -rf`、`git push`、`curl | sh` のようなコマンドを`prompt`または`deny`にし、理由を表示できる。これは、承認ポリシーとは別の「コマンド内容ベースのガード」と考えるとよい。


### Hooks

Hooksは、`SessionStart`、`PreToolUse`、`PostToolUse`、`PermissionRequest`、`UserPromptSubmit`、`Stop` などのイベントで決定的なスクリプトを走らせる拡張機構である。プロンプトに秘密情報が含まれていないか検査する、セッション開始時にチーム規約を注入する、ターン終了時に検証スクリプトを走らせる、といった用途がある。


### MCP

MCPは、Codexへ外部ツールと外部文脈を提供するプロトコルである。STDIOサーバはローカルプロセスとして起動し、Streamable HTTPサーバはURLで接続する。HTTPではBearer tokenやOAuthが使える。MCPサーバ設定は `config.toml` の `[mcp_servers.<server-name>]` に記述でき、`codex mcp add` でも追加できる。


### SkillsとSubagents

Skillsは、`SKILL.md` を中心にした手順・ツール知識のパッケージであり、Subagentsは複雑な作業を明示的に並列化するための機構である。Subagentsはトークン消費が増えるため、調査・設計・実装・レビューを分けるような大きめのタスクで使うと効果が高い。


## 推奨プリセット


```text
L{0.30} X}
目的  |  推奨設定  |  理由
普段の開発  |  `sandbox_mode="workspace-write"`, `approval_policy="on-request"`, `web_search="cached"`  |  作業ディレクトリ内の変更は進めつつ、ネットワークや外部書き込みは確認できる。
調査だけ  |  `sandbox_mode="read-only"`, `approval_policy="on-request"`  |  変更を避けて、コード読解・説明・計画に集中できる。
CIレビュー  |  `codex exec --sandbox read-only -a never`  |  非対話環境で承認待ちを避け、読み取り専用に限定する。
使い捨てVM  |  `danger-full-access` + 外部隔離  |  強い権限を使う場合は、OS/VM/コンテナ側で被害範囲を限定する。
企業端末  |  `requirements.toml` + MCP allowlist + managed hooks  |  ユーザー上書き不可の制約で、外部連携と危険操作を統制する。
```


## トラブルシューティング

**設定が効かない**  `/debug-config` でレイヤ別の解決結果を確認する。未信頼プロジェクトでは `.codex/config.toml` が読み込まれない。`-c` や `--profile` が上位で上書きしていることも多い。

**コマンドが承認待ちになる**  サンドボックス外の書き込み、ネットワークアクセス、保護された `.git` や `.codex` への操作は承認が必要になりやすい。`/status` で作業ルートと承認設定を見る。

**MCPが出てこない**  `codex mcp list` と `/mcp` を確認する。HTTP MCPはBearer/OAuth、STDIO MCPは `command` と `args`、環境変数、起動タイムアウトを確認する。企業要件のMCP allowlistにより無効化されている場合もある。

**Web検索が期待と違う**  既定の `cached` はOpenAI管理の検索キャッシュであり、ライブ取得ではない。最新情報が必要なときは `--search` または `web_search="live"` を使う。ただし、検索結果はプロンプトインジェクション源になり得るため、権限の強いサンドボックス設定と組み合わせるときは注意する。


---


