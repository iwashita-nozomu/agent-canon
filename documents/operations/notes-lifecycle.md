# Notes Lifecycle
<!--
@dependency-start
contract reference
responsibility Owns topic-based recording, retrieval, and promotion of reusable observations and failed verification.
upstream design README.md durable document index
@dependency-end
-->

この文書は、`documents/notes/` の記録、再利用、昇格を所有します。
失敗した検証は実行中にトピックへ保存し、次の調査・設計・実装判断で参照します。

## この文書の読み方

- 検証で失敗したときは「Failed Verification Record」を使います。
- 同じ候補や問題を調べる前は「Retrieve Before Deciding」を使います。
- review / closeout では保存先と参照の整合を確認し、恒久規約を正本へ昇格します。

## Purpose

- 検証の条件・手順・結果を、次の読者が再現できる状態にする。
- 確認した失敗と原因をトピック単位で蓄積し、同じ失敗の繰り返しを減らす。
- 観測が成立する範囲を保ち、条件変更後の再検証につなげる。

## Default Flow

### 1. During Execution

- 時系列と操作の参照は `documents/notes/worktrees/` の action log に残します。
- 実験 topic の結果要約は `documents/notes/experiments/` に残します。
- branch / worktree の入口整理は `documents/notes/branches/` に残します。
- 失敗した検証は、直後に下の topic record を更新し、同じ task 内で保存内容を読み戻します。

### Failed Verification Record

公開可能な repository 固有の失敗は `documents/notes/failures/<topic>.md` に記録します。
この repository では既存の failures area をトピック別メモとして使います。consumer が
`documents/memo/` 等を既に所有する場合は、その配置規約に従います。
private な再利用知識は [private log owner](../runtime/private-feedback-knowledge.md) の
`agent-canon-log` に保存します。公開範囲に応じて一つの保存先を選びます。

既存 topic を検索してから追記し、各失敗について次を簡潔に残します。

| 項目 | 内容 |
| --- | --- |
| 目的・候補 | 満たす要求と、試した実装・利用案・設定・合成 |
| 再現条件 | source revision、入力、関連する版・環境・設定・前提 |
| 検証手順 | 正規経路の command、対象、または仕様・コードの locator と確認手順 |
| 期待と実際 | 判定基準、観測値、exit status / error / 反例、および根拠の参照 |
| 結論 | 検証が確定した事実、原因が立証された範囲、候補の採用・修正・却下理由 |
| 再利用条件 | 同じ判断を適用する条件と、再検証が必要になる変更点 |

観測した失敗を先に保存し、判断に必要な原因・代案は調査と検証を続けて同じ topic に
追記します。仮説と確定結果は見分けられる形にし、検証した条件の範囲で結論を述べます。
成功した修正や反証が得られた場合は、元の失敗から新しい結果へ参照を接続します。
Issue / PR、設計、handoff には同じ topic の locator を載せます。

失敗実験のコード・設定・生成物の破棄は実験 owner の既存規約で進めます。
その際も、要求、再現手順、観測、結論を含む短い topic 記録を残します。保存対象の
知見と、削除対象の実装・生成物は責務を分けます。秘密情報や private 本文は各保存先の
公開範囲を守り、読み戻しは今回の記録を対象にします。

### Retrieve Before Deciding

調査・設計・実装で候補を採用または却下する前に、要求、候補名、エラー、関連 owner
から既存 topic を検索します。private 知識は [agent-learning](../../agents/skills/agent-learning.md)
の `agent-canon k search` と `k read` を使います。

見つかった記録の入力、source revision、設定、保証を現在の条件と照合します。
同じ前提が維持される結論と再現 evidence は参照して再利用し、結果を変え得る前提が
変わった場合はその点を正規経路で再検証します。再利用した記録と今回の結論を既存の
設計・task 記録へ接続します。未解決の判断は必要な調査・検証を実行して確定します。

### 2. At Review / Closeout

記録済みの topic と action log / report の参照を照合し、必要な昇格を行います。

- `documents/notes/knowledge/`: 繰り返し使う短い横断知識。
- `documents/notes/themes/`: 複数 run の topic-level synthesis。
- private `agent-canon-log/knowledge/` と `feedback/`: source tree 外の private 知識。
- `documents/notes/failures/`: 再現条件と検証結果を持つ failure knowledge。
- `documents/`: repository の恒久規約を所有する正本。

### 3. Keep The Worktree Log Thin

action log は時系列と参照を担当します。長く使う知見は topic record に集約し、
action log、Issue / PR、handoff から同じ記録へ接続します。

## Promotion Rules

| 保存先 | 昇格する内容 |
| --- | --- |
| `documents/notes/knowledge/` | command、path、環境規約、tool behavior の実務知識 |
| `documents/notes/themes/` | 複数 run、実験、文献を結ぶ topic-level synthesis |
| `documents/notes/failures/` | 失敗した検証の再現条件、結果、結論、再利用・再検証条件 |
| canonical `documents/` owner | repository 全体に適用する rule、workflow、contract |

## Closeout Readback

今回の失敗検証が topic に保存され、読み戻せることを確認します。採用・却下の判断を
検証結果へ、次回の判断を topic 検索へ接続します。既存記録の更新、反証、昇格がある場合は
参照も同期します。private log の保存・同期は各操作の実際の結果を示します。

## Templates

- [documents/notes/worktrees/WORKTREE_LOG_TEMPLATE.md](../notes/worktrees/WORKTREE_LOG_TEMPLATE.md)
- [documents/notes/branches/BRANCH_NOTE_TEMPLATE.md](../notes/branches/BRANCH_NOTE_TEMPLATE.md)
- [documents/notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md](../notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md)
- [documents/notes/themes/THEME_NOTE_TEMPLATE.md](../notes/themes/THEME_NOTE_TEMPLATE.md)
- private `agent-canon-log/knowledge/topics/<topic>/candidate.md`
- [documents/notes/failures/FAILURE_NOTE_TEMPLATE.md](../notes/failures/FAILURE_NOTE_TEMPLATE.md)
