# [コードコメント] 非自明な実装判断をコード近傍へ残し、変更時に同期する

issue_id: AC-20260821-decision-comments
status: open
source: user
severity: S2
problem: 正しさに関係する非自明な実装判断がコード近傍へ保存・同期される条件が、コメント正本と実装・レビュー経路の間で閉じていない。
evidence: documents/conventions/common/03_comments.md; documents/conventions/python/06_comments.md; documents/conventions/coding-conventions-house-style.md; agents/skills/comprehensive-development.md; agents/skills/change-review.md
accepted evidence: https://github.com/iwashita-nozomu/agent-canon/issues/826; https://github.com/iwashita-nozomu/agent-canon/pull/827
done: material decision の有限な comment predicate、最狭 owner への配置、同一差分での更新／削除、stale comment review が既存 owner 間で接続される。
affected_surfaces: documents/conventions/common/03_comments.md; documents/conventions/python/06_comments.md; documents/conventions/coding-conventions-house-style.md; agents/skills/comprehensive-development.md; agents/skills/change-review.md; issues/open/AC-20260821-decision-comments.md
edit_scope: owner-bounded
required_action: 共通コメント正本を decision-comment contract へ整理し、Python 表記、implementation、change review を従属させる。
close_condition: AgentCanon の required PR checks が pass し、Issue コメントから branch、commit、PR、validation、remaining verification を追跡できる。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/826

## 目的

コードを読んだ将来の変更者が、Issue や PR の履歴を掘らなくても、**その実装が守る不変条件・前提・数理的／工学的理由**をコード近傍で復元できるようにします。

現行 AgentCanon には責務コメントと「逐語説明ではなく、なぜその形かを書く」規約があります。しかし、必須条件が関数単位に寄り、実装判断の保存条件、変更時の同期、レビューでの stale comment 判定が十分に接続されていません。本 Issue はコメント量を増やす規則ではなく、正しさに関係する判断を最小の局所コメントとして残す契約へ整理します。

## Baseline

- AgentCanon: `main@173489b0f3cccdc93e54d3b4d2d0d278f2aa631d`
- project template inventory: `main@07cd68a230fb69c2cd9358de076250905750750c`
- project template の inventory 時点 AgentCanon pin: `173489b0f3cccdc93e54d3b4d2d0d278f2aa631d`
- implementation branch: `fix/826-decision-comments`
- implementation commit: `c222fec129d9e13d4ff2ca5f8a19f03e6789ac21`
- review PR: https://github.com/iwashita-nozomu/agent-canon/pull/827

project template は ownership と重複有無の確認対象として参照しましたが、本 Issue の変更対象・終了条件には含めません。

## Confirmed occurrence locations

### 共通コメント正本

`documents/conventions/common/03_comments.md` は意図、前提、数式、数値安定性、関数責務を求めますが、「どの実装判断をコード近傍へ残すか」「変更時にどう同期するか」「何をコメントしないか」の判定境界を持っていません。

### Python 固有規約

`documents/conventions/python/06_comments.md` は JAX 制御、shape、dtype、数値安定化を扱いますが、一般の ordering、resource lifetime、security/authority、external protocol、compatibility 制約を共通判定へ接続していません。

### ハウススタイル

`documents/conventions/coding-conventions-house-style.md` は非自明な関数・helper の直前に `# 責務:` を要求しますが、実装内部の判断根拠、変更時の更新／削除、stale comment の欠陥扱いが分離しています。

### 実装・レビュー経路

`agents/skills/comprehensive-development.md` と `agents/skills/change-review.md` は material mechanism の owner、根拠、alternative、oracle を扱いますが、そのうち将来の保守で必要な最小理由をコード近傍へ残すこと、変更されたコメントの正確性を review することを明示していません。

## 根本原因

現在は次の三つが分離しています。

```text
Issue / PR: task の判断履歴
canonical documents: repository-wide contract
code comments: local maintenance context
```

Issue / PR は時点依存であり、コードだけを変更する将来の作業で必ず読まれるとは限りません。一方、全処理をコメントで説明すると code と comment の二重実装になり、stale surface が増えます。

したがって、局所コメントを要求する条件を次の三条件積に限定します。

```text
needs_local_comment(decision)
  := decision affects correctness, safety, numerical validity,
     ordering/lifetime, external contract, or compatibility
     and rationale is not recoverable from names, types, or structure
     and a plausible maintenance change can violate the invariant
```

コメントは実装の逐語説明ではなく、最小限の
`invariant / assumption + why + forbidden alternative or failure semantics`
を保存します。

## Target contract

### Canonical owner

- 一般判定の正本: `documents/conventions/common/03_comments.md`
- Python 固有差分: `documents/conventions/python/06_comments.md`
- Python 表記・`# 責務:` 入口: `documents/conventions/coding-conventions-house-style.md`
- 実装時の適用: `agents/skills/comprehensive-development.md`
- review 時の同期確認: `agents/skills/change-review.md`

### コメントを残す代表条件

- 仕様上の invariant、precondition、postcondition、failure semantics
- 数式の導出、停止条件、誤差境界、tolerance、数値安定化
- concurrency、ordering、atomicity、resource lifetime、cleanup
- security、authority、data exposure、external protocol／runtime constraint
- compatibility を維持する理由、または実装上魅力的だが禁止する alternative

### コメントを残さない条件

- 代入、分岐、loop 等の逐語説明
- 名前・型・構造から自明な処理
- comment quota を満たすためだけの説明
- Issue / PR 本文の貼り付け
- 複雑な実装を温存するための長文解説

### Lifecycle

- コメントが説明する logic を変更した差分では、同じ差分でコメントを更新または削除します。
- 誤った／古いコメントは「コメント不足」より強い欠陥として扱います。
- repository-wide contract を参照する場合は stable canonical path/clause を使い、Issue 番号だけを唯一の根拠にしません。

## 変更範囲

- 共通コメント規約を decision-comment contract へ整理します。
- Python 固有規約とハウススタイルを共通正本へ従属させます。
- implementation skill に、material かつ code から復元不能な判断を最狭 owner へ残す手順を追加します。
- change review に、変更された comment の正確性と必要な局所理由の欠落を判定する有限ルールを追加します。
- 規範文の wiring は既存 `check_convention_compliance.py`、差分ごとの意味判定は既存 `change-review.md` へ接続します。
- コメント数や行密度を数える checker は追加しません。

## Downstream boundary

project template の exact AgentCanon pin 更新は、companion Issue https://github.com/iwashita-nozomu/project_template/issues/199 が所有します。

- AgentCanon の policy / skill / checker を template へ複製しません。
- pin 更新は upstream publication 後に行います。
- companion Issue #199 は downstream consumer work であり、本 Issue #826 の review、merge、close を block しません。
- #826 の終了条件へ template 側の branch、pin、validation を含めません。

## Non-goals

- 既存コード全体へ一括でコメントを追加しません。
- 全関数・全 block・全行への機械的コメントを要求しません。
- docstring 規約、API documentation、dependency header を全面再設計しません。
- comment coverage metric、AST comment counter、lint quota を追加しません。
- Issue / PR の履歴をコードへ複製しません。
- project template の gitlink、AGENTS、Codex surface、production code を変更しません。
- 今回触れない production code の cleanup や style 修正を終了条件に含めません。

## Acceptance criteria

- [x] 共通正本に `needs_local_comment` と同等の有限な意味判定が記載される。
- [x] correctness / safety / 数理 / ordering-lifetime / external contract / compatibility の代表条件が扱われる。
- [x] comment が `why / invariant / assumption / failure` を優先し、逐語説明・quota・長文複製を禁止する。
- [x] logic 変更時に comment を同じ差分で更新／削除し、stale comment を defect として扱う。
- [x] Python 固有規約とハウススタイルが共通正本を再実装せず参照する。
- [x] implementation skill が material decision の局所保存を明示する。
- [x] change review が missing/stale/misleading comment を concrete correctness/maintenance impact に基づいて判定し、comment density を blocking condition にしない。
- [x] 新しい comment-count checker、wrapper、registry を追加しない。
- [x] 規範文が既存 convention verification route へ接続される。
- [ ] AgentCanon required PR checks が final head で pass する。
- [x] latest main 起点・Issue 番号入り branch で作業し、Issue コメントから branch、commit、PR、validation、remaining verification を追跡できる。
- [x] downstream template pin を companion Issue へ分離し、#826 の終了条件に含めない。

## Current state

- implementation: ready for review
- review PR: https://github.com/iwashita-nozomu/agent-canon/pull/827
- validation and final head: latest Issue comment を正本とする
- downstream companion (non-blocking): https://github.com/iwashita-nozomu/project_template/issues/199
