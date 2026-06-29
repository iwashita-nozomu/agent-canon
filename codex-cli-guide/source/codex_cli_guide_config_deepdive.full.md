<!--
@dependency-start
contract reference
responsibility Preserves the complete single-file Markdown source for the split Codex CLI guide.
downstream implementation ../tools/validate_split.py validates split guide reconstruction.
@dependency-end
-->

# 完全版ソースについて

このファイルは、分割前の `codex_cli_guide_config_deepdive.md` を完全収録したものです。
`<!-- split-content-start -->` 以降が原本本文です。

- normalized runtime note: hook flag examples use current `features.hooks` / `hooks` spelling.
- source sha256: `67405e3d88280008c71e01d2cb3403d3842734bfb4ce9e27474a8a87e3988510`
- source lines: 12,386
- source bytes: 365,144

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


# 第VII部 図解カタログ: MCPと実験機能の運用パターン


## 図解で見る運用パターン

この部は、前章までの説明を現場で参照しやすいように、短い図解として再整理したものである。MCP、feature flag、subagent、hooks、rules、approval、sandboxは個別機能ではなく、一つの運用設計として組み合わせる。


#### 図解: 調査専用profile

`read only` → `docs MCP` → `要約`

_調査専用profileの基本パターン。_


#### 図解: PRレビューprofile

`diff` → `subagents` → `統合`

_PRレビューprofileの基本パターン。_


#### 図解: UI debug profile

`browser MCP` → `logs` → `修正`

_UI debug profileの基本パターン。_


#### 図解: CI調査profile

`artifact` → `log` → `原因`

_CI調査profileの基本パターン。_


#### 図解: 社内docs profile

`search` → `fetch` → `根拠`

_社内docs profileの基本パターン。_


#### 図解: issue調査profile

`issue` → `PR` → `履歴`

_issue調査profileの基本パターン。_


#### 図解: DB参照profile

`read only` → `limit` → `mask`

_DB参照profileの基本パターン。_


#### 図解: observability profile

`trace` → `metric` → `log`

_observability profileの基本パターン。_


#### 図解: release profile

`notes` → `check` → `draft`

_release profileの基本パターン。_


#### 図解: security profile

`secret scan` → `policy` → `review`

_security profileの基本パターン。_


#### 図解: MCP inventory

`server` → `tools` → `owner`

_MCP inventoryの基本パターン。_


#### 図解: MCP review

`purpose` → `auth` → `scope`

_MCP reviewの基本パターン。_


#### 図解: MCP test

`start` → `call` → `result`

_MCP testの基本パターン。_


#### 図解: MCP disable

`enabled false` → `reload` → `verify`

_MCP disableの基本パターン。_


#### 図解: MCP remove

`delete config` → `docs` → `notify`

_MCP removeの基本パターン。_


#### 図解: MCP upgrade

`version` → `diff` → `test`

_MCP upgradeの基本パターン。_


#### 図解: MCP incident

`detect` → `disable` → `alternate route`

_MCP incidentの基本パターン。_


#### 図解: MCP onboarding

`env` → `login` → `smoke`

_MCP onboardingの基本パターン。_


#### 図解: MCP audit

`call` → `approval` → `diff`

_MCP auditの基本パターン。_


#### 図解: MCP cleanup

`unused` → `disabled` → `archive`

_MCP cleanupの基本パターン。_


#### 図解: feature canary

`lab` → `sandbox repo` → `observe`

_feature canaryの基本パターン。_


#### 図解: feature promote

`docs` → `owner` → `default`

_feature promoteの基本パターン。_


#### 図解: feature rollback

`disable` → `profile` → `notify`

_feature rollbackの基本パターン。_


#### 図解: feature conflict

`flag A` → `flag B` → `isolate`

_feature conflictの基本パターン。_


#### 図解: feature drift

`binary` → `schema` → `docs`

_feature driftの基本パターン。_


#### 図解: feature policy

`requirements` → `pin` → `audit`

_feature policyの基本パターン。_


#### 図解: feature training

`example` → `FAQ` → `rules`

_feature trainingの基本パターン。_


#### 図解: feature metrics

`time` → `errors` → `rework`

_feature metricsの基本パターン。_


#### 図解: feature risk

`scope` → `privilege` → `duration`

_feature riskの基本パターン。_


#### 図解: feature sunset

`deprecated` → `remove` → `update`

_feature sunsetの基本パターン。_


#### 図解: hook safety

`input` → `decision` → `block`

_hook safetyの基本パターン。_


#### 図解: hook audit

`payload` → `log` → `review`

_hook auditの基本パターン。_


#### 図解: hook secret

`scan` → `mask` → `stop`

_hook secretの基本パターン。_


#### 図解: hook query

`length` → `scope` → `limit`

_hook queryの基本パターン。_


#### 図解: hook write

`tool name` → `approval` → `deny`

_hook writeの基本パターン。_


#### 図解: rules safe

`allow` → `prompt` → `forbid`

_rules safeの基本パターン。_


#### 図解: rules review

`prefix` → `effect` → `owner`

_rules reviewの基本パターン。_


#### 図解: approval flow

`request` → `human` → `decision`

_approval flowの基本パターン。_


#### 図解: sandbox flow

`read` → `write` → `network`

_sandbox flowの基本パターン。_


#### 図解: network flow

`cached` → `live` → `risk`

_network flowの基本パターン。_


#### 図解: subagent docs

`query` → `source` → `summary`

_subagent docsの基本パターン。_


#### 図解: subagent browser

`repro` → `console` → `evidence`

_subagent browserの基本パターン。_


#### 図解: subagent logs

`search` → `rank` → `cause`

_subagent logsの基本パターン。_


#### 図解: subagent reviewer

`risk` → `test` → `fix`

_subagent reviewerの基本パターン。_


#### 図解: subagent implementer

`patch` → `test` → `diff`

_subagent implementerの基本パターン。_


#### 図解: subagent coordinator

`spawn` → `collect` → `decide`

_subagent coordinatorの基本パターン。_


#### 図解: subagent limit

`threads` → `depth` → `timeout`

_subagent limitの基本パターン。_


#### 図解: subagent output

`format` → `evidence` → `todo`

_subagent outputの基本パターン。_


#### 図解: subagent failure

`timeout` → `alternate route` → `merge`

_subagent failureの基本パターン。_


#### 図解: subagent cost

`parallel` → `budget` → `stop`

_subagent costの基本パターン。_


#### 図解: goal tests

`watch` → `pass` → `stop`

_goal testsの基本パターン。_


#### 図解: goal migration

`plan` → `step` → `verify`

_goal migrationの基本パターン。_


#### 図解: goal cleanup

`find` → `fix` → `review`

_goal cleanupの基本パターン。_


#### 図解: goal docs

`draft` → `check` → `publish`

_goal docsの基本パターン。_


#### 図解: goal release

`prepare` → `verify` → `finish`

_goal releaseの基本パターン。_


#### 図解: background dev

`start` → `observe` → `stop`

_background devの基本パターン。_


#### 図解: background logs

`tail` → `filter` → `summarize`

_background logsの基本パターン。_


#### 図解: background tests

`watch` → `fail` → `rerun`

_background testsの基本パターン。_


#### 図解: background server

`port` → `health` → `stop`

_background serverの基本パターン。_


#### 図解: background cleanup

`list` → `kill` → `confirm`

_background cleanupの基本パターン。_


#### 図解: enterprise MCP

`allowlist` → `requirements` → `audit`

_enterprise MCPの基本パターン。_


#### 図解: enterprise feature

`pin` → `policy` → `rollout`

_enterprise featureの基本パターン。_


#### 図解: enterprise secret

`vault` → `env` → `rotation`

_enterprise secretの基本パターン。_


#### 図解: enterprise docs

`standard` → `examples` → `review`

_enterprise docsの基本パターン。_


#### 図解: enterprise incident

`disable` → `notify` → `postmortem`

_enterprise incidentの基本パターン。_


#### 図解: team onboarding

`install` → `login` → `smoke`

_team onboardingの基本パターン。_


#### 図解: team standards

`AGENTS` → `rules` → `hooks`

_team standardsの基本パターン。_


#### 図解: team review

`config` → `MCP` → `features`

_team reviewの基本パターン。_


#### 図解: team update

`changelog` → `test` → `merge`

_team updateの基本パターン。_


#### 図解: team archive

`remove` → `docs` → `cleanup`

_team archiveの基本パターン。_


#### 図解: final pattern A

`small` → `safe` → `documented`

_final pattern Aの基本パターン。_


#### 図解: final pattern B

`scoped` → `audited` → `reversible`

_final pattern Bの基本パターン。_


#### 図解: final pattern C

`subagent` → `MCP` → `summary`

_final pattern Cの基本パターン。_


#### 図解: final pattern D

`feature` → `profile` → `rollback`

_final pattern Dの基本パターン。_


#### 図解: final pattern E

`owner` → `version` → `runbook`

_final pattern Eの基本パターン。_


## 第VII部のまとめ

図解カタログの要点は単純である。MCPは外部能力を増やすため、tool allowlist、secret管理、timeout、Hooks、subagent分離が必要である。実験的機能は挙動変更の可能性があるため、profile隔離、feature flag、changelog確認、rollbackが必要である。どちらも、AGENTS.mdとteam docsに運用ルールを書き、ownerを置き、定期的に更新確認することで、便利さと安全性を両立できる。


---


# 第VIII部 実務カード集: すぐ使うMCPと実験機能パターン


## 実務カード集の使い方

この部は、設計会議やpull request reviewでそのまま参照できる短いカード集である。各カードは、入口、判断、結果の三段階で構成している。MCPを追加する時、実験的機能を有効化する時、subagentを増やす時、HooksやRulesを調整する時に、該当カードをチェックリストとして使う。


## MCP追加カード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: MCP追加カード 01

`purpose` → `owner` → `risk`

_MCP追加カードの確認カード01。_


#### 図解: MCP追加カード 02

`transport` → `auth` → `tools`

_MCP追加カードの確認カード02。_


#### 図解: MCP追加カード 03

`stdio` → `cwd` → `args`

_MCP追加カードの確認カード03。_


#### 図解: MCP追加カード 04

`http` → `url` → `token`

_MCP追加カードの確認カード04。_


#### 図解: MCP追加カード 05

`oauth` → `scope` → `callback`

_MCP追加カードの確認カード05。_


#### 図解: MCP追加カード 06

`allowlist` → `tools` → `review`

_MCP追加カードの確認カード06。_


#### 図解: MCP追加カード 07

`required` → `startup` → `alternate route`

_MCP追加カードの確認カード07。_


#### 図解: MCP追加カード 08

`timeout` → `measure` → `tune`

_MCP追加カードの確認カード08。_


#### 図解: MCP追加カード 09

`secret` → `env` → `rotate`

_MCP追加カードの確認カード09。_


#### 図解: MCP追加カード 10

`docs` → `AGENTS` → `FAQ`

_MCP追加カードの確認カード10。_


#### 図解: MCP追加カード 11

`test` → `start` → `call`

_MCP追加カードの確認カード11。_


#### 図解: MCP追加カード 12

`disable` → `enabled false` → `verify`

_MCP追加カードの確認カード12。_


#### 図解: MCP追加カード 13

`upgrade` → `version` → `diff`

_MCP追加カードの確認カード13。_


#### 図解: MCP追加カード 14

`incident` → `block` → `alternate route`

_MCP追加カードの確認カード14。_


#### 図解: MCP追加カード 15

`audit` → `log` → `owner`

_MCP追加カードの確認カード15。_


#### 図解: MCP追加カード 16

`read server` → `safe` → `summary`

_MCP追加カードの確認カード16。_


#### 図解: MCP追加カード 17

`write server` → `approval` → `guard`

_MCP追加カードの確認カード17。_


#### 図解: MCP追加カード 18

`browser server` → `repro` → `evidence`

_MCP追加カードの確認カード18。_


#### 図解: MCP追加カード 19

`docs server` → `search` → `fetch`

_MCP追加カードの確認カード19。_


#### 図解: MCP追加カード 20

`logs server` → `rank` → `cause`

_MCP追加カードの確認カード20。_


#### 図解: MCP追加カード 21

`issue server` → `link` → `history`

_MCP追加カードの確認カード21。_


#### 図解: MCP追加カード 22

`db server` → `limit` → `mask`

_MCP追加カードの確認カード22。_


#### 図解: MCP追加カード 23

`obs server` → `trace` → `metric`

_MCP追加カードの確認カード23。_


#### 図解: MCP追加カード 24

`file server` → `range` → `guard`

_MCP追加カードの確認カード24。_


#### 図解: MCP追加カード 25

`team server` → `requirements` → `pin`

_MCP追加カードの確認カード25。_


## 実験機能カード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: 実験機能カード 01

`maturity` → `docs` → `version`

_実験機能カードの確認カード01。_


#### 図解: 実験機能カード 02

`flag` → `enable` → `record`

_実験機能カードの確認カード02。_


#### 図解: 実験機能カード 03

`profile` → `lab` → `default`

_実験機能カードの確認カード03。_


#### 図解: 実験機能カード 04

`rollback` → `disable` → `confirm`

_実験機能カードの確認カード04。_


#### 図解: 実験機能カード 05

`goal` → `success` → `stop`

_実験機能カードの確認カード05。_


#### 図解: 実験機能カード 06

`background` → `start` → `stop`

_実験機能カードの確認カード06。_


#### 図解: 実験機能カード 07

`fast mode` → `small diff` → `review`

_実験機能カードの確認カード07。_


#### 図解: 実験機能カード 08

`multi agent` → `threads` → `depth`

_実験機能カードの確認カード08。_


#### 図解: 実験機能カード 09

`hooks` → `feature` → `matcher`

_実験機能カードの確認カード09。_


#### 図解: 実験機能カード 10

`rules` → `prefix` → `policy`

_実験機能カードの確認カード10。_


#### 図解: 実験機能カード 11

`search live` → `source` → `risk`

_実験機能カードの確認カード11。_


#### 図解: 実験機能カード 12

`image` → `purpose` → `rights`

_実験機能カードの確認カード12。_


#### 図解: 実験機能カード 13

`apps` → `scope` → `audit`

_実験機能カードの確認カード13。_


#### 図解: 実験機能カード 14

`mcp server` → `caller` → `boundary`

_実験機能カードの確認カード14。_


#### 図解: 実験機能カード 15

`cloud` → `env` → `secret`

_実験機能カードの確認カード15。_


#### 図解: 実験機能カード 16

`canary` → `sandbox repo` → `observe`

_実験機能カードの確認カード16。_


#### 図解: 実験機能カード 17

`promote` → `docs` → `owner`

_実験機能カードの確認カード17。_


#### 図解: 実験機能カード 18

`freeze` → `requirements` → `pin`

_実験機能カードの確認カード18。_


#### 図解: 実験機能カード 19

`conflict` → `isolate` → `bisect`

_実験機能カードの確認カード19。_


#### 図解: 実験機能カード 20

`deprecate` → `remove` → `notify`

_実験機能カードの確認カード20。_


#### 図解: 実験機能カード 21

`train` → `example` → `FAQ`

_実験機能カードの確認カード21。_


#### 図解: 実験機能カード 22

`measure` → `time` → `rework`

_実験機能カードの確認カード22。_


#### 図解: 実験機能カード 23

`safety` → `sandbox` → `approval`

_実験機能カードの確認カード23。_


#### 図解: 実験機能カード 24

`review` → `diff` → `test`

_実験機能カードの確認カード24。_


#### 図解: 実験機能カード 25

`standard` → `AGENTS` → `team`

_実験機能カードの確認カード25。_


## サブエージェントカード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: サブエージェントカード 01

`role` → `bounded` → `output`

_サブエージェントカードの確認カード01。_


#### 図解: サブエージェントカード 02

`explorer` → `map` → `return`

_サブエージェントカードの確認カード02。_


#### 図解: サブエージェントカード 03

`reviewer` → `risk` → `rank`

_サブエージェントカードの確認カード03。_


#### 図解: サブエージェントカード 04

`fixer` → `patch` → `test`

_サブエージェントカードの確認カード04。_


#### 図解: サブエージェントカード 05

`docs agent` → `source` → `cite`

_サブエージェントカードの確認カード05。_


#### 図解: サブエージェントカード 06

`browser agent` → `repro` → `console`

_サブエージェントカードの確認カード06。_


#### 図解: サブエージェントカード 07

`logs agent` → `artifact` → `cause`

_サブエージェントカードの確認カード07。_


#### 図解: サブエージェントカード 08

`issue agent` → `ticket` → `context`

_サブエージェントカードの確認カード08。_


#### 図解: サブエージェントカード 09

`data agent` → `csv` → `summary`

_サブエージェントカードの確認カード09。_


#### 図解: サブエージェントカード 10

`migration agent` → `one row` → `result`

_サブエージェントカードの確認カード10。_


#### 図解: サブエージェントカード 11

`parent` → `spawn` → `merge`

_サブエージェントカードの確認カード11。_


#### 図解: サブエージェントカード 12

`threads` → `budget` → `limit`

_サブエージェントカードの確認カード12。_


#### 図解: サブエージェントカード 13

`depth` → `one` → `stop`

_サブエージェントカードの確認カード13。_


#### 図解: サブエージェントカード 14

`timeout` → `job` → `abort`

_サブエージェントカードの確認カード14。_


#### 図解: サブエージェントカード 15

`handoff` → `format` → `evidence`

_サブエージェントカードの確認カード15。_


#### 図解: サブエージェントカード 16

`failure` → `alternate route` → `human`

_サブエージェントカードの確認カード16。_


#### 図解: サブエージェントカード 17

`cost` → `parallel` → `cap`

_サブエージェントカードの確認カード17。_


#### 図解: サブエージェントカード 18

`privacy` → `mask` → `avoid`

_サブエージェントカードの確認カード18。_


#### 図解: サブエージェントカード 19

`mcp inherit` → `limit` → `override`

_サブエージェントカードの確認カード19。_


#### 図解: サブエージェントカード 20

`profile` → `readonly` → `write`

_サブエージェントカードの確認カード20。_


#### 図解: サブエージェントカード 21

`model` → `effort` → `task`

_サブエージェントカードの確認カード21。_


#### 図解: サブエージェントカード 22

`skill` → `path` → `scope`

_サブエージェントカードの確認カード22。_


#### 図解: サブエージェントカード 23

`prompt` → `clear` → `bounded`

_サブエージェントカードの確認カード23。_


#### 図解: サブエージェントカード 24

`result` → `json` → `short`

_サブエージェントカードの確認カード24。_


#### 図解: サブエージェントカード 25

`cleanup` → `close` → `summarize`

_サブエージェントカードの確認カード25。_


## HooksとRulesカード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: HooksとRulesカード 01

`PreToolUse` → `inspect` → `block`

_HooksとRulesカードの確認カード01。_


#### 図解: HooksとRulesカード 02

`PostToolUse` → `review` → `log`

_HooksとRulesカードの確認カード02。_


#### 図解: HooksとRulesカード 03

`UserPrompt` → `detect` → `warn`

_HooksとRulesカードの確認カード03。_


#### 図解: HooksとRulesカード 04

`Stop` → `validate` → `continue`

_HooksとRulesカードの確認カード04。_


#### 図解: HooksとRulesカード 05

`matcher` → `specific` → `small`

_HooksとRulesカードの確認カード05。_


#### 図解: HooksとRulesカード 06

`payload` → `schema` → `parse`

_HooksとRulesカードの確認カード06。_


#### 図解: HooksとRulesカード 07

`secret scan` → `mask` → `deny`

_HooksとRulesカードの確認カード07。_


#### 図解: HooksとRulesカード 08

`write guard` → `tool` → `approval`

_HooksとRulesカードの確認カード08。_


#### 図解: HooksとRulesカード 09

`query guard` → `length` → `limit`

_HooksとRulesカードの確認カード09。_


#### 図解: HooksとRulesカード 10

`command guard` → `prefix` → `policy`

_HooksとRulesカードの確認カード10。_


#### 図解: HooksとRulesカード 11

`allow` → `safe` → `fast`

_HooksとRulesカードの確認カード11。_


#### 図解: HooksとRulesカード 12

`prompt` → `risky` → `human`

_HooksとRulesカードの確認カード12。_


#### 図解: HooksとRulesカード 13

`forbid` → `danger` → `stop`

_HooksとRulesカードの確認カード13。_


#### 図解: HooksとRulesカード 14

`unit test` → `match` → `not match`

_HooksとRulesカードの確認カード14。_


#### 図解: HooksとRulesカード 15

`CI mode` → `no prompt` → `safe`

_HooksとRulesカードの確認カード15。_


#### 図解: HooksとRulesカード 16

`hook logs` → `file` → `rotate`

_HooksとRulesカードの確認カード16。_


#### 図解: HooksとRulesカード 17

`hook owner` → `team` → `docs`

_HooksとRulesカードの確認カード17。_


#### 図解: HooksとRulesカード 18

`hook failure` → `message` → `exit`

_HooksとRulesカードの確認カード18。_


#### 図解: HooksとRulesカード 19

`rule review` → `diff` → `example`

_HooksとRulesカードの確認カード19。_


#### 図解: HooksとRulesカード 20

`rule update` → `test` → `merge`

_HooksとRulesカードの確認カード20。_


#### 図解: HooksとRulesカード 21

`sandbox pair` → `rule` → `approval`

_HooksとRulesカードの確認カード21。_


#### 図解: HooksとRulesカード 22

`MCP pair` → `hook` → `allowlist`

_HooksとRulesカードの確認カード22。_


#### 図解: HooksとRulesカード 23

`network pair` → `live` → `warn`

_HooksとRulesカードの確認カード23。_


#### 図解: HooksとRulesカード 24

`debug pair` → `verbose` → `log`

_HooksとRulesカードの確認カード24。_


#### 図解: HooksとRulesカード 25

`rollback pair` → `disable` → `remove`

_HooksとRulesカードの確認カード25。_


## トラブルシュートカード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: トラブルシュートカード 01

`not loaded` → `trust` → `root`

_トラブルシュートカードの確認カード01。_


#### 図解: トラブルシュートカード 02

`bad config` → `debug` → `layer`

_トラブルシュートカードの確認カード02。_


#### 図解: トラブルシュートカード 03

`server fail` → `cwd` → `command`

_トラブルシュートカードの確認カード03。_


#### 図解: トラブルシュートカード 04

`auth fail` → `env` → `scope`

_トラブルシュートカードの確認カード04。_


#### 図解: トラブルシュートカード 05

`tool missing` → `allowlist` → `schema`

_トラブルシュートカードの確認カード05。_


#### 図解: トラブルシュートカード 06

`slow start` → `timeout` → `profile`

_トラブルシュートカードの確認カード06。_


#### 図解: トラブルシュートカード 07

`slow tool` → `limit` → `server`

_トラブルシュートカードの確認カード07。_


#### 図解: トラブルシュートカード 08

`huge output` → `snippet` → `summary`

_トラブルシュートカードの確認カード08。_


#### 図解: トラブルシュートカード 09

`bad answer` → `source` → `prompt`

_トラブルシュートカードの確認カード09。_


#### 図解: トラブルシュートカード 10

`wrong file` → `root` → `AGENTS`

_トラブルシュートカードの確認カード10。_


#### 図解: トラブルシュートカード 11

`hook silent` → `feature` → `matcher`

_トラブルシュートカードの確認カード11。_


#### 図解: トラブルシュートカード 12

`rule silent` → `prefix` → `test`

_トラブルシュートカードの確認カード12。_


#### 図解: トラブルシュートカード 13

`agent edits` → `sandbox` → `readonly`

_トラブルシュートカードの確認カード13。_


#### 図解: トラブルシュートカード 14

`agent loops` → `stop` → `goal`

_トラブルシュートカードの確認カード14。_


#### 図解: トラブルシュートカード 15

`cost spike` → `threads` → `limit`

_トラブルシュートカードの確認カード15。_


#### 図解: トラブルシュートカード 16

`context bloat` → `subagent` → `summary`

_トラブルシュートカードの確認カード16。_


#### 図解: トラブルシュートカード 17

`network fail` → `mode` → `proxy`

_トラブルシュートカードの確認カード17。_


#### 図解: トラブルシュートカード 18

`oauth fail` → `callback` → `resource`

_トラブルシュートカードの確認カード18。_


#### 図解: トラブルシュートカード 19

`token leak` → `rotate` → `mask`

_トラブルシュートカードの確認カード19。_


#### 図解: トラブルシュートカード 20

`server down` → `disable` → `alternate route`

_トラブルシュートカードの確認カード20。_


#### 図解: トラブルシュートカード 21

`version drift` → `changelog` → `binary`

_トラブルシュートカードの確認カード21。_


#### 図解: トラブルシュートカード 22

`schema drift` → `docs` → `test`

_トラブルシュートカードの確認カード22。_


#### 図解: トラブルシュートカード 23

`team confusion` → `FAQ` → `owner`

_トラブルシュートカードの確認カード23。_


#### 図解: トラブルシュートカード 24

`unsafe diff` → `review` → `revert`

_トラブルシュートカードの確認カード24。_


#### 図解: トラブルシュートカード 25

`final check` → `pdf` → `render`

_トラブルシュートカードの確認カード25。_


## チーム運用カード


この節のカードは、短時間のreviewで見るためのものである。左から入口、判断、結果の順に読む。必要ならAGENTS.mdやdocs/codexへ転記してチーム標準にする。


#### 図解: チーム運用カード 01

`onboarding` → `install` → `login`

_チーム運用カードの確認カード01。_


#### 図解: チーム運用カード 02

`smoke test` → `codex` → `debug`

_チーム運用カードの確認カード02。_


#### 図解: チーム運用カード 03

`standard config` → `root` → `profile`

_チーム運用カードの確認カード03。_


#### 図解: チーム運用カード 04

`AGENTS` → `rules` → `style`

_チーム運用カードの確認カード04。_


#### 図解: チーム運用カード 05

`MCP inventory` → `server` → `owner`

_チーム運用カードの確認カード05。_


#### 図解: チーム運用カード 06

`feature policy` → `lab` → `promote`

_チーム運用カードの確認カード06。_


#### 図解: チーム運用カード 07

`review policy` → `PR` → `check`

_チーム運用カードの確認カード07。_


#### 図解: チーム運用カード 08

`secret policy` → `env` → `vault`

_チーム運用カードの確認カード08。_


#### 図解: チーム運用カード 09

`docs policy` → `update` → `link`

_チーム運用カードの確認カード09。_


#### 図解: チーム運用カード 10

`incident policy` → `disable` → `notify`

_チーム運用カードの確認カード10。_


#### 図解: チーム運用カード 11

`monthly review` → `version` → `schema`

_チーム運用カードの確認カード11。_


#### 図解: チーム運用カード 12

`training` → `examples` → `demo`

_チーム運用カードの確認カード12。_


#### 図解: チーム運用カード 13

`templates` → `copy` → `adapt`

_チーム運用カードの確認カード13。_


#### 図解: チーム運用カード 14

`enterprise` → `requirements` → `pin`

_チーム運用カードの確認カード14。_


#### 図解: チーム運用カード 15

`local env` → `repro` → `secret`

_チーム運用カードの確認カード15。_


#### 図解: チーム運用カード 16

`CI` → `readonly` → `json`

_チーム運用カードの確認カード16。_


#### 図解: チーム運用カード 17

`release` → `notes` → `verify`

_チーム運用カードの確認カード17。_


#### 図解: チーム運用カード 18

`security` → `audit` → `hook`

_チーム運用カードの確認カード18。_


#### 図解: チーム運用カード 19

`privacy` → `mask` → `minimize`

_チーム運用カードの確認カード19。_


#### 図解: チーム運用カード 20

`access` → `scope` → `expire`

_チーム運用カードの確認カード20。_


#### 図解: チーム運用カード 21

`archive` → `remove` → `cleanup`

_チーム運用カードの確認カード21。_


#### 図解: チーム運用カード 22

`metrics` → `usage` → `errors`

_チーム運用カードの確認カード22。_


#### 図解: チーム運用カード 23

`owner` → `rotation` → `handoff`

_チーム運用カードの確認カード23。_


#### 図解: チーム運用カード 24

`roadmap` → `feature` → `risk`

_チーム運用カードの確認カード24。_


#### 図解: チーム運用カード 25

`governance` → `standard` → `exception`

_チーム運用カードの確認カード25。_


## 実務カード集のまとめ

カード化すると、Codex CLIの運用は属人的な勘ではなく、繰り返し使える判断手順になる。特に、MCP追加、実験機能導入、subagent増設、HooksとRulesの変更は、設定diffだけでなく、目的、owner、失敗時挙動、rollback、文書更新までを一つの変更として扱うと安定する。


## 今回の徹底増補で追加した一次情報メモ

この徹底増補では、OpenAI DevelopersのCodex CLI、CLI features、Slash commands、Configuration Reference、MCP、Subagents、Hooks、Rules、Feature Maturity、Managed configuration、Best practices、Follow a goal、Codex changelog、Agents SDK関連ページを参照した。特に、MCPについてはSTDIO、Streamable HTTP、Bearer token、OAuth、tool allowlist、timeout、required、環境変数転送、OAuth callbackの観点で再整理した。実験的機能については、feature flag、`/experimental`、`/goal`、multi agent、background terminal、fast mode、Codex MCP server、Apps connectorを、導入手順とrollback手順の観点で説明した。


---


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
# 第IX部 最終追加テンプレート集


## 設定を運用へ落とし込むテンプレート

この部では、設定ファイルそのものに加えて、PR、月次棚卸し、障害時rollback、CI実行に使う短いテンプレートを追加する。


### 最終追加レシピ 254: repo監査用profile

**目的**  設定断片を運用テンプレートとして追加する。


```
[profiles.audit]
sandbox_mode = "read-only"
approval_policy = "on-request"
web_search = "disabled"
model_reasoning_effort = "high"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 255: 依存更新レビューprofile

**目的**  設定断片を運用テンプレートとして追加する。


```
[profiles.dependency_review]
sandbox_mode = "read-only"
web_search = "cached"
model_reasoning_effort = "high"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 256: docs更新worker

**目的**  設定断片を運用テンプレートとして追加する。


```
name = "docs-update-worker"
description = "Update docs after verified code changes."
developer_instructions = "Only edit docs and examples. Include verification notes."
sandbox_mode = "workspace-write"
approval_policy = "on-request"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 257: release manager agent

**目的**  設定断片を運用テンプレートとして追加する。


```
name = "release-manager"
description = "Prepare release notes and checklist from diffs."
developer_instructions = "Do not publish. Draft notes, risk list, and verification checklist."
sandbox_mode = "read-only"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 258: MCP read only owner lookup

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.owner_lookup]
url = "https://mcp.example.internal/owners/mcp"
bearer_token_env_var = "OWNER_LOOKUP_TOKEN"
enabled_tools = ["lookup_owner", "list_team_services"]
tool_timeout_sec = 30
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 259: MCP contract docs

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.contract_docs]
url = "https://mcp.example.internal/contracts/mcp"
bearer_token_env_var = "CONTRACT_DOCS_TOKEN"
enabled_tools = ["search_contracts", "get_contract"]
startup_timeout_sec = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 260: MCP disable write tools

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.tracker]
url = "https://mcp.example.internal/tracker/mcp"
bearer_token_env_var = "TRACKER_TOKEN"
enabled_tools = ["search_tickets", "get_ticket"]
disabled_tools = ["update_ticket", "delete_ticket", "assign_ticket"]
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 261: hookでlockfile変更を検知

**目的**  設定断片を運用テンプレートとして追加する。


```
[hooks]
[[hooks.PostToolUse]]
matcher = "^Bash$"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/check_lockfile_changes.py"
timeout = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 262: hookで生成物を警告

**目的**  設定断片を運用テンプレートとして追加する。


```
[hooks]
[[hooks.PostToolUse]]
matcher = "^Bash$"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "python3 .codex/hooks/warn_generated_diff.py"
timeout = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 263: hookでbranch保護

**目的**  設定断片を運用テンプレートとして追加する。


```
[hooks]
[[hooks.SessionStart]]
matcher = ".*"
[[hooks.SessionStart.hooks]]
type = "command"
command = "python3 .codex/hooks/check_not_main_branch.py"
timeout = 10
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 264: rulesでpublish禁止

**目的**  設定断片を運用テンプレートとして追加する。


```
prefix_rule(pattern=["npm", "publish"], decision="forbidden", reason="Publishing packages from Codex is not allowed.")
prefix_rule(pattern=["pnpm", "publish"], decision="forbidden", reason="Publishing packages from Codex is not allowed.")
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 265: rulesでcloud操作確認

**目的**  設定断片を運用テンプレートとして追加する。


```
prefix_rule(pattern=["aws"], decision="prompt", reason="Cloud provider commands require human review.")
prefix_rule(pattern=["gcloud"], decision="prompt", reason="Cloud provider commands require human review.")
prefix_rule(pattern=["az"], decision="prompt", reason="Cloud provider commands require human review.")
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 266: rulesでmigration確認

**目的**  設定断片を運用テンプレートとして追加する。


```
prefix_rule(pattern=["rails", "db:migrate"], decision="prompt", reason="Database migration requires review.")
prefix_rule(pattern=["prisma", "migrate", "deploy"], decision="prompt", reason="Database migration requires review.")
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 267: requirementsでCI host制御

**目的**  設定断片を運用テンプレートとして追加する。


```
[[remote_sandbox_config]]
hostname_patterns = ["ci-runner-*" ]
allowed_sandbox_modes = ["read-only", "workspace-write"]
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 268: requirementsでprod host制御

**目的**  設定断片を運用テンプレートとして追加する。


```
[[remote_sandbox_config]]
hostname_patterns = ["prod-*", "bastion-*" ]
allowed_sandbox_modes = ["read-only"]
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 269: requirementsでMCP docs固定

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.docs.identity]
url = "https://mcp.example.internal/docs/mcp"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 270: requirementsでMCP tracker固定

**目的**  設定断片を運用テンプレートとして追加する。


```
[mcp_servers.tracker.identity]
url = "https://mcp.example.internal/tracker/mcp"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 271: project READMEテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# .codex/README.md
This directory contains Codex project configuration.
- config.toml: trusted project settings.
- agents: role-specific agents.
- hooks: local policy scripts.
- rules: command policy.
- mcp: repo-local MCP servers.
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 272: AGENTSの最小安全項目

**目的**  設定断片を運用テンプレートとして追加する。


```
# AGENTS.md
## Safety
- Do not read secrets.
- Do not commit unless asked.
- Do not push.
- Show test results and git diff summary.
- Ask before installing dependencies.
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 273: AGENTSの検証項目

**目的**  設定断片を運用テンプレートとして追加する。


```
# AGENTS.md
## Verification
- Run the smallest relevant test first.
- If tests are skipped, explain why.
- Include command output summary in final response.
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 274: CI review command

**目的**  設定断片を運用テンプレートとして追加する。


```
codex exec --profile ci_review "Review this diff for correctness, security, and missing tests. Output JSON."
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 275: CI patch command

**目的**  設定断片を運用テンプレートとして追加する。


```
codex exec --profile ci_patch "Fix the failing tests with minimal changes. Do not use network."
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 276: MCP health workflow

**目的**  設定断片を運用テンプレートとして追加する。


```
codex mcp list
codex mcp get docs
codex mcp get tracker
# In TUI: /mcp
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 277: feature review workflow

**目的**  設定断片を運用テンプレートとして追加する。


```
codex features list
codex --profile lab features enable goals
codex --profile lab features disable apps
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 278: debug config workflow

**目的**  設定断片を運用テンプレートとして追加する。


```
# In TUI
/debug-config
/status
/mcp
/experimental
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 279: schema付き設定開始

**目的**  設定断片を運用テンプレートとして追加する。


```
#:schema https://developers.openai.com/codex/config-schema.json
model = "gpt-5.5"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 280: 設定変更PRテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# Codex config PR
Purpose:
Permission impact:
MCP impact:
Hooks and rules:
Validation:
Rollback:
Owner:
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 281: 月次棚卸しテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# Monthly Codex config review
- codex version:
- deprecated keys:
- MCP servers still needed:
- hooks still passing:
- rules false positives:
- requirements exceptions:
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


### 最終追加レシピ 282: 障害時disableテンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
# Emergency rollback
# 1. Disable project MCP
# enabled = false
# 2. Disable hooks
# [features]
# hooks = false
# 3. Revert .codex config PR
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


### 最終追加レシピ 283: 最終確認テンプレ

**目的**  設定断片を運用テンプレートとして追加する。


```
codex --version
codex features list
codex mcp list
codex execpolicy check "git push"
# TUI: /debug-config
```


**確認**  関連する `/debug-config`、`codex features list`、`codex mcp list`、または `codex execpolicy check` で確認する。

**戻し方**  該当sectionを削除するか、`enabled = false` にして戻す。


---


## 参考文献・一次情報


- OpenAI Developers, Codex CLI: <https://developers.openai.com/codex/cli>
- OpenAI Developers, Command line options: <https://developers.openai.com/codex/cli/reference>
- OpenAI Developers, Codex CLI features: <https://developers.openai.com/codex/cli/features>
- OpenAI Developers, Slash commands in Codex CLI: <https://developers.openai.com/codex/cli/slash-commands>
- OpenAI Developers, Config basics: <https://developers.openai.com/codex/config-basic>
- OpenAI Developers, Advanced Configuration: <https://developers.openai.com/codex/config-advanced>
- OpenAI Developers, Configuration Reference: <https://developers.openai.com/codex/config-reference>
- OpenAI Developers, Config JSON schema: <https://developers.openai.com/codex/config-schema.json>
- OpenAI Developers, Agent approvals & security: <https://developers.openai.com/codex/agent-approvals-security>
- OpenAI Developers, Hooks: <https://developers.openai.com/codex/hooks>
- OpenAI Developers, AGENTS.md guide: <https://developers.openai.com/codex/guides/agents-md>
- OpenAI Developers, Model Context Protocol: <https://developers.openai.com/codex/mcp>
- OpenAI GitHub, openai/codex README: <https://github.com/openai/codex/blob/main/README.md>

- OpenAI Developers, Subagents: <https://developers.openai.com/codex/subagents>
- OpenAI Developers, Subagent concepts: <https://developers.openai.com/codex/concepts/subagents>
- OpenAI Developers, Customization: <https://developers.openai.com/codex/concepts/customization>
- OpenAI Developers, Sample Configuration: <https://developers.openai.com/codex/config-sample>
- OpenAI Developers, Rules: <https://developers.openai.com/codex/rules>
- OpenAI Developers, Agent Skills: <https://developers.openai.com/codex/skills>
- OpenAI Developers, Managed configuration: <https://developers.openai.com/codex/enterprise/managed-configuration>
- OpenAI Developers, Local environments: <https://developers.openai.com/codex/app/local-environments>
- OpenAI Developers, Feature Maturity: <https://developers.openai.com/codex/feature-maturity>
- OpenAI Developers, Codex changelog: <https://developers.openai.com/codex/changelog?type=codex-cli>
- OpenAI Developers, Follow a goal: <https://developers.openai.com/codex/use-cases/follow-goals>
- OpenAI Developers, Best practices: <https://developers.openai.com/codex/learn/best-practices>
- OpenAI Developers, Use Codex with the Agents SDK: <https://developers.openai.com/codex/guides/agents-sdk>
- OpenAI Developers, Codex MCP server command: <https://developers.openai.com/codex/cli/reference#codex-mcp-server>
