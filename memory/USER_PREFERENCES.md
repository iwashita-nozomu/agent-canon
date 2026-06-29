# User Preferences
<!--
@dependency-start
contract data
responsibility Documents User Preferences for this repository.
upstream design README.md memory surface index
@dependency-end
-->

この file は、会話から抽出した user の coding philosophy、review expectation、document preference を逐次追記する append-first note です。
`AGENTS.md` へ入れる前の観測をここへ集め、十分に安定した項目だけを periodic sweep で昇格させます。

## この文書の読み方

- この note は、会話から抽出した repo-wide な user preference を蓄積し、`AGENTS.md` へ昇格する前の観測を保持します。
- `Use` で追記対象を確認し、`Stable Preferences` と `Provisional Preferences` で安定度ごとの preference を読みます。
- 昇格候補や最近の観測を確認するときは `Promotion Candidates` と `Recent Observations` を読みます。

## Use

- user が明示した repo-wide preference を観測したら追記します。
- task 固有の一時指示ではなく、今後も効く傾向だけを残します。
- `AGENTS.md` に直接書かず、まずこの note に入れます。
- periodic sweep では repeated で durable な項目だけを `AGENTS.md` へ昇格します。
- shared canon の `memory/` を正本にし、template 側では runtime view を使います。

## Stable Preferences


- 2026-04-16 | Keep only canonical design and implementation paths in the tracked tree; reject non-canonical copies, snapshots, and backup files.
  - source: chat
  - rationale: User explicitly required current tree-head state as the only durable repo state.

- 2026-04-23 | Review must always check full consistency with existing code, docs, workflows, and canonical surfaces, not only the diff.
  - source: chat

- 2026-05-05 | Do not enforce a fixed 100-character line-length limit; treat line length as a readability judgment governed by project-local formatter/lint configuration, and ignore E501 when fixed line-length failures are not desired.
  - source: chat

## Provisional Preferences

- 2026-04-10 | agent の作業哲学、知識、対話から得た学習を task / dialogue ごとに更新可能な仕組みにしたい
  - source: chat
  - rationale: 2026-04-10 の依頼: エージェントの知識・哲学・人格形成を継続更新したい

- 2026-04-10 | 要件定義では、過去ログ由来のユーザー特性と、今回の要求・repo 実態・domain 制約・未確定事項を分けて扱いたい
  - source: chat
  - rationale: 2026-04-10 request: requirements definition should be more careful; user traits can be extracted separately but should not replace task-specific requirements

- 2026-04-10 | 変数名や identifier を worker が自由裁量で決めるのではなく、既存 precedent または詳細設計に結び付けたい
  - source: chat
  - rationale: 2026-04-10 request asking whether variable names can be decided freely

- 2026-04-10 | task 開始時に agent-canon を毎回最新化してから作業したい
  - source: chat
  - rationale: 2026-04-10 request: 毎回毎回agent-canonは最新化したい

- 2026-04-10 | ウォーターフォール開発では途中 gate のエラー検出と再開先を弱くせず、各段で機械的に止めたい
  - source: chat
  - rationale: 2026-04-10 request: ウォーターフォールの開発フローが弱く、途中でエラーがある

- 2026-04-10 | Agile / adaptive improvement は、拡張 1 件ごとに独立した waterfall pass として回したい
  - source: chat
  - rationale: 2026-04-10 request: Agile を強化し、一つの拡張ごとにウォーターフォールで回すループにしたい

- 2026-04-10 | 文書や詳細設計がある状態では、実装を設計文書ベースで行い、会話や推測で上書きしない
  - source: chat
  - rationale: 2026-04-10 request: 文書がある状態で実装が文書を無視することが多い

- 2026-04-10 | レートリミットが厳しいため、Codex Sparkに移譲できる低リスク実装sliceは移譲したい
  - source: chat
  - rationale: 2026-04-10 request: codexSparkに移譲できるところはしていきたい、レートリミットが厳しい

- 2026-04-10 | 要件定義では、むやみに停止せず、過去ログ・notes・repo precedentで解決できる曖昧さは解決してから残差だけを確認したい
  - source: chat
  - rationale: 2026-04-10 request: エージェントのランタイムにむやみに停止するのは好みではなく、過去のログや蓄積情報を参照して解決したい

- 2026-04-10 | 作業単位・chunk・sliceの完了で止まらず、ユーザー依頼全体の完了条件まで継続してほしい
  - source: chat
  - rationale: 2026-04-10 request: 作業単位に分割して終了してしまう癖をワークフローで解決したい

- 2026-04-10 | Token efficiency: when a task has repeatable shell steps, prefer small bash scripts or batched shell commands instead of spending many turns/tokens on manual command-by-command narration.
  - source: chat

- 2026-04-10 | Token reduction target is not primarily user-facing explanation; reduce command-generation overhead and subagent prompt/context tokens by batching repeatable shell work and delegating only when material.
  - source: chat

- 2026-04-10 | Do not close tasks at minimal implementation or partial-spec coverage; require reviewer-confirmed evidence that implementation covers the full requested specification and that review findings were reflected before completion.
  - source: chat

- 2026-04-11 | Repo-changing tasks must leave a concrete TODO artifact and a chronological work log until closeout.
  - source: chat

- 2026-04-11 | Do not stop to ask for push permission when push is a natural completion step; push directly unless I explicitly stop it or an external block exists.
  - source: chat

- 2026-04-11 | サブエージェントを実際に起動し、handoff では tree 順の文書探索ではなく packet path を明示してほしい
  - source: chat

- 2026-04-19 | 既存実装の再利用を強く優先し、新規実装の前に既存実装で足りない理由を明示してほしい
  - source: chat

- 2026-04-20 | レビューでは差分だけでなく関連ファイル全体と削除影響まで確認してほしい。作成したファイルを後で消すことが多いため、削除済み・移動済み・参照切れも含めて見る。
  - source: chat

- 2026-04-22 | 最小変更に拘らず、再発源が構造にあるなら workflow・packet・参照構造まで含めて十分な大きさで直してほしい。
  - source: chat

- 2026-04-22 | 必要な subagent や MCP surface がある task では、起動確認を先に行い、未起動のまま parent 単独へ静かに downgrade しないでほしい。
  - source: chat

- 2026-04-22 | temporary alternate route や旧経路を温存せず、canonical path を 1 本に寄せてほしい。代替経路温存は実装の二重化の温床になる。
  - source: chat

- 2026-04-22 | repo に搭載されている test は単一の canonical file に文書化してほしい。追加・削除・rename 時はその file も同じ pass で更新してほしい。
  - source: chat

- 2026-04-22 | 退避 branch や backup branch を残さず、履歴は git にありつつも、運用上は最新の canonical state だけを見せてほしい。同期や置換のあとに extra branch を保険として残さないでほしい。
  - source: chat

- 2026-04-22 | コードが実行できるだけでは不十分で、本体実装が数式・仕様記述と一致していることを重視してほしい。runtime success よりも mathematical/spec alignment を主要な受け入れ基準として扱ってほしい。
  - source: chat

- 2026-04-22 | 読みやすさや reader flow の評価はツールだけでは不十分なので、文書や prompt の readability はエージェント review で確認してほしい。tool check は補助にとどめ、可読性判断は agent-side review を必須にしてほしい。
  - source: chat

- 2026-04-24 | Implementation work should start from this template repository by default; avoid treating other repositories as the primary starting point unless the user explicitly redirects.
  - source: chat

- 2026-04-24 | Do not return a user-facing completion report while any task, planned work unit, required validation, commit/push, canon sync, or closeout gate remains unfinished; return only after everything in scope is complete.
  - source: chat

- 2026-04-28 | 数式文書では『導入しない』『残さない』などの自明な否定説明を避け、式の導出と必要な定義だけで書く。
  - source: chat

- 2026-04-29 | ファイルや path の欠落を見つけたときは、再作成や欠落判定の前に template root と shared agent-canon を確認してほしい。
  - source: chat

- 2026-05-01 | ファイル横断実装では自前実装を最後の手段にし、既存 helper/tool/workflow/fixture の再利用・拡張を優先する。新規追加時は Reuse Survey と既存では足りない理由を残す。
  - source: chat

- 2026-04-18 | 外部から受領した Excel などの source artifact は tracked datafiles ではなく rootdata に置き、final 成果物は code で再生成する前提にする。
  - source: chat

- 2026-05-05 | 各実装・実験パスでは OOP readability / public surface / nested contract チェッカを実行し、失敗はチェッカ不具合ではなく実装違反として扱う。
  - source: repo-local jax_solver_util AgentCanon memory diff

- 2026-05-05 | レート制約が強い task では、repo inventory、tool drift survey、static validation planning、diff-local language review、design-traced bounded implementation slice を gpt-5.3-codex-spark low の fresh subagent へ優先委譲し、parent / gpt-5.5 は統合判断と最終責任に集中させる。
  - source: chat

- 2026-05-11 | Codex should actively configure and use available runtime features such as hooks, MCP, and goals when they are stable and useful, instead of leaving them dormant.
  - source: chat

- 2026-05-11 | Within Docker or devcontainer environments, Codex may use available runtime features and install/configure development dependencies more freely, while keeping host-level changes conservative.
  - source: chat

- 2026-05-15 | Jupyter notebooks should be readable practical demos that show partial execution and runnable visualization; detailed assertions and fine-grained tests belong in tests/, and hooks should block notebook-as-test misuse.
  - source: chat

- 2026-05-18 | 当面は skill_usage.jsonl などの通常 session usage log も AgentCanon-owned hook result として毎回 AgentCanon branch / PR に commit/push して蓄積する。
  - source: chat

- 2026-05-31 | PDIPM/KKT diagnostics must not use KKT solve accuracy, residual tolerance, or direction acceptance as the fix axis; focus on the mathematical reconstruction of the full Newton update direction from the reduced KKT solution.
  - source: chat

- 2026-06-01 | Reader-facing documents, reports, workflow guides, and plans should actively use Mermaid diagrams for nontrivial process, dependency, ownership, routing, state, or review-gate structure when the diagram adds reader value.
  - source: chat

- 2026-06-12 | When improving AgentCanon workflow policy, prioritize removing stale or obsolete conventions and hard-stop assumptions over adding new style-like rules.
  - source: chat

- 2026-06-13 | コード編集では保守的すぎる最小差分に寄せず、問題の再発源が設計・構造・古い surface にある場合は、十分な大きさの cohesive edit と削除・置換まで踏み込んでほしい。
  - source: chat

- 2026-06-14 | Before starting work, declare the intended work once in chat, including the task focus and immediate action, then proceed.
  - source: chat

- 2026-06-14 | Do not add numerical tests unless the changed behavior, known regression, acceptance criterion, proof obligation, or experiment contract has a concrete numerical trigger; otherwise prefer static or lightweight deterministic non-numerical tests and record the omission reason.
  - source: chat

- 2026-06-15 | Reader-facing repository documents should use positive responsibility and contract phrasing.
  - source: chat

- 2026-06-15 | Temporary code should be explicitly marked as temporary when created, and removed before closeout once it has served its purpose.
  - source: chat

- 2026-06-15 | Use GitHub Issues as durable work tracking when appropriate, and include issue cleanup or explicit issue status confirmation in closeout.
  - source: chat

- 2026-06-18 | 証明や実装の説明では、エージェントが勝手に作った抽象名・ラベルで説明せず、実在するコード名・定理名・数式・入出力に基づいて説明する。新しい便宜名を使う場合は導入理由と非正本であることを明示する。
  - source: chat

- 2026-06-19 | Before editing python/docomo_bt_management/experiments, first preserve the current state in git because changes there can affect other experiments.
  - source: chat

## Promotion Candidates

- まだなし

## Recent Observations

- まだなし
