# Connected-session rule-routing validation

## Scope

2026-10-03、AgentCanon Issue #1331 の読取経路修正。基準は
`85cbe467a75185be5b9acfad23f73f10dbda0439`、作業ブランチは
`fix/1331-point-of-use-rule-routing`。この記録は当該セッションの取得・検証の
制約を扱い、利用者の開発環境やAgentCanon runtime全体の障害を断定しません。

## Failure Kind and Trigger

GitHub接続はsourceの読取とGit objectの公開を利用できます。一方、ローカルの
完全checkout・正規tool runtimeを必要とする操作は次の結果でした。

| 操作 | 期待 | 実際 |
| --- | --- | --- |
| `git clone --filter=blob:none --no-checkout https://github.com/iwashita-nozomu/agent-canon.git /mnt/data/agent-canon` | 基準sourceを取得する | `Could not resolve host: github.com`、exit 128 |
| `pyright-langserver --stdio </dev/null` | 関連定義・参照をLSPで取得する | executable未検出、exit 127。LSP解析は開始していない |
| `ruff format` に変更対象Python 3ファイルを渡す | `ruff.toml`によるformat | `ruff: command not found`、exit 127 |
| 部分sourceで `tools/bin/agent-canon docs format` に変更Markdownを渡す | 正規Markdown formatterで書式を揃える | entrypointが部分sourceに存在せず、exit 127 |
| 部分sourceで `python -m unittest discover -s tests/agent_tools -p test_point_of_use_skill_routes.py -v` | production loaderによる候補投影を確認する | `ModuleNotFoundError: No module named 'tools.agent'`、exit 1。assertionは未実行 |

Python対象は `tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py`、
`tests/agent_tools/test_check_entrypoint_owner_map.py`、
`tests/agent_tools/test_point_of_use_skill_routes.py`。接続作業のsourceは
`/mnt/data/rule-routing-1331/after` に組み立てた部分コピーで、Git checkoutや
AgentCanon tool containerではありません。Markdownの正確な対象は本PRの変更した
`.md`一覧です。未実施・未検出を検証成功や対象機能の不具合に変換しません。

## Why It Matters

生成Skillは薄い参照adapterですが、`skill_shim_materializer.py::build_record` は
catalog・依存辞書・canonical Skill本文のdigestをrecordへ含めます。今回の依存辞書変更は
全70個のadapter recordを更新対象にします。本文の参照が解決することだけでは生成物の
整合性を証明できません。既存materializerとgraph ownerの生成・readbackを実施するまで、
この修正はDraftとして扱い、古いdigestを手作業で置換しません。

## Current Understanding

接続による読取・公開と、ローカルのsource取得・tool実行は別の結果です。DNS失敗の
詳細原因や利用者環境の状態は未確定です。現在の判断に必要なのは、独立した編集・公開を
接続経路で継続でき、正規format・全生成物の検証を成功扱いできないという境界です。

Python構文は `ast.parse` で確認しました。入口回帰は、変更source、合成marker manifest、
存在確認用owner stubを持つ隔離fixture上で17件成功しています。これはPython 3.13の
fixture検証であり、完全checkoutのmarker一致、全参照先内容、production候補投影、
Skill生成、実エージェントの読取行動を確認した結果ではありません。

## Safe Alternative and Recheck Conditions

公開は既存 [GitHub connected work](../../../agents/internal-routines/github-connected-work.md)
で進め、正確なbase/head、部分検証と残件をIssue/PRへ残します。別runner、独自CI、
formatter代替、手書きgeneratorを作らず、失敗した同一取得を前提変更なしに反復しません。

完全checkoutとその既存tool runtimeを利用できる担当は、このブランチに最新mainを
取り込み、既存materializerでadapterを再生成・readbackし、graph ownerで該当投影を
確認します。その後、[formatter設定](../../design/formatting.md)の操作を変更ファイルへ
実行し、入口検査・2回帰suite・Skill依存/生成物・docs/変更dependencyの正規検証を行います。
具体的なcontrol root・targetは担当の既存値を使い、新規環境構築をこのIssueの条件にしません。

同じ制約下では上の失敗を再利用できます。完全sourceの取得、executable、runtime経路、
対象headが変わった場合に関連する操作だけ再検証し、成功・反証をこのtopicへ接続します。
正確なPR/headと後続結果の正本は [Issue #1331](https://github.com/iwashita-nozomu/agent-canon/issues/1331)
です。別revisionのCI成功を今回の生成・format成功に流用しません。
