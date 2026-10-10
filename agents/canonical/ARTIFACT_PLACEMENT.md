# Artifact Placement
<!--
@dependency-start
contract agent-runtime
responsibility Owns placement of task artifacts and routes durable document creation to its structure owner.
upstream design README.md canonical workflow index
upstream design ../../documents/rule/directory-structure.md document placement, responsibility split, and reader reachability
@dependency-end
-->

この文書は、task 実行中に増える文書や補助出力の置き場の正本です。
run ごとの一時 artifact と、repo に長く残す文書を分けて扱います。

## この文書の読み方

作成・移動する成果物の責務を決めてから、該当する保存先だけを読みます。
既存の in-scope file の編集だけでは、配置の再調査を要求しません。

| 現在の操作 | 次に読む箇所 |
| --- | --- |
| run-local artifact の作成 | [reports](#reportsagentsrun-id) と選択済み run の write policy |
| 恒久文書の追加・分割・移動・削除 | [配置と分割](../../documents/rule/directory-structure.md#配置と分割の判断軸)、[参照と到達性](../../documents/rule/directory-structure.md#参照と到達性) |
| file・symbol・artifact の命名 | [命名規約](../../documents/rule/naming.md) の該当する責務 |
| 公開可能な失敗検証の保存 | [Failed Verification Record](../../documents/operations/notes-lifecycle.md#failed-verification-record) |
| cross-run knowledge の配置・昇格 | [documents/notes](#documentsnotes) と [Notes Lifecycle](../../documents/operations/notes-lifecycle.md) |

追加・移動・分割では、新しい場所へ置くことと、実際の consumer から必要な場面に
読めることを同じ変更で確認します。索引への登録だけで適用経路の接続済みとは扱いません。
直接の参照元を更新し、path / anchor の実在を既存 docs 検証で確認します。

## 置き場ルール

恒久文書を追加・分割・移動・削除するときは、
[配置と分割](../../documents/rule/directory-structure.md#配置と分割の判断軸) と
[参照と到達性](../../documents/rule/directory-structure.md#参照と到達性) を適用します。
名前を決める場合は [命名規約](../../documents/rule/naming.md) の該当する責務を読みます。

- repo-wide の正本: agent 運用は `agents/`、一般規約と恒久手順は `documents/`、
  再利用知見は `documents/notes/`。開発環境はその repository の既存環境 owner。
- run-local artifact: 選択された coordination / resumption run の `reports/agents/<run-id>/`。
  bounded route は既存 task/Issue evidence を使い、配置のために bundle を作りません。
- cross-run agent report: `.agent-canon/log-archive/agent-reports/<stable-source-repository-id>/<run-id>/<snapshot-id>/`。
  branch と stable-source identity は `agent-canon-log` の repository policy が所有します。
- temporary runtime output: current handoff、`team_manifest.yaml`、または
  `task_authority.yaml` の許可された path。`WORKTREE_SCOPE.md` は legacy cleanup evidence
  であり、新しい write authority ではありません。

## Task 中の拡張文書

その run だけの判断・review・handoff・メモは既存 artifact へ追記します。
repo-wide 文書へ増殖させず、追加の reader-facing 説明は file/document responsibility
から保存先を選びます。writer は選択された artifact と許可 path だけを更新します。

## どこへ置くか

### `reports/agents/<run-id>/`

Selected run artifacts include `intent_brief.md`, `decision_log.md`, `design_brief.md`,
`design_review.md`, `change_review.md`, `final_review.md`, `verification.txt`, and
only the selected experiment/environment/specialist outputs. Artifact names are
available placements, not instructions to materialize every template.

`semantic_responsibility_contract.toml` is the populated run-local instance referenced
by the active design packet. Policy and empty template stay with `documents/design/`
and `templates/documents/`; a populated instance is not copied back into canon.
Roles and artifact write policy remain in `agents/agents_config.json` and the selected
run's authority. Add run-specific sections to existing artifacts rather than new
parallel reports.

Archive a selected durable agent report through the existing
`tools/runtime/archive/runtime_log_archive_git.py archive-agent-report --report-dir
reports/agents/<run-id>` operation, using the owned execution route. It owns the
immutable snapshot, append-only index, push and remote readback. Broad `sync` is for
explicitly selected cumulative runtime families, not a replacement report publisher.
Read actual placement/identity from that owner's status output rather than guessing.

When coordinated closeout is selected, `task_close.py` checks artifact placement.
Tracked durable reports are allowed by canon; untracked/ignored reports belong only
to the current run directory. Old run bundles follow archive/closeout rather than
being copied into a new run.

Mechanically regenerable report roots remain governed by `generated_artifact_guard.py`:
`reports/agent-eval-runs/`, `reports/dependency-review/`,
`reports/agent-runtime-dashboard/`, `reports/agent-improvement-guide/`, `reports/hooks/`,
`reports/.cache/`, and generated `reports/*.json`, `*.patch`, `*.txt`.
Promote reusable findings to their document/notes owner with responsibility and
reference evidence, not by retaining disposable output as a second canon.

### `documents/`

Place reusable repository-wide rules, development-environment operations, and durable
review/research/experiment procedures here when they have value beyond a single run.
Use the structure/reader-route owner before adding or splitting these documents.

### `agents/`

Place cross-agent workflow, handoff, review, escalation, Skill and subagent operating
canon here. Runtime entrypoints remain thin references rather than copied policy.

### `documents/notes/`

Place cross-run observations, experiment/research summaries, and reusable decision
support here. These are supporting records, not another permanent rule owner.
Use existing topic records and Notes Lifecycle for retrieval, retention and promotion.
Private knowledge follows its authorized private-log owner instead of public notes.

## Subagent と補助文書

Subagent policy belongs to `agents/`; a particular run's prompt fragment is not
repo-wide canon. New artifacts require the selected operation and existing write
scope, not merely a possible future stage or candidate reviewer.

## 禁止事項

Keep transient run notes and command experiments out of permanent canon. Retired
example commands are not runtime truth. Preserve unknown/user-owned data, successful
or shared evidence, and current authority while applying the existing archive and
cleanup owners; placing an artifact does not authorize deleting another owner's data.
