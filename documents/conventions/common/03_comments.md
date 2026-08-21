<!--
@dependency-start
contract policy
responsibility Documents コメント for this repository.
upstream design ../../runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
downstream design ../coding-conventions-house-style.md projects Python responsibility-comment syntax
downstream design ../../../agents/skills/comprehensive-development.md applies material decision comments during implementation
downstream design ../../../agents/skills/change-review.md reviews decision-comment lifecycle
@dependency-end
-->

# コメント

この章は、コード上のコメントが保存する情報と、その更新条件を定めます。
コメント量を増やすことではなく、コードだけでは復元できない実装判断を、将来の変更者が誤って壊さない形で残すことを目的にします。

## 要約

- 正しさに関係する非自明な判断は、最も狭い安定したコード所有箇所の近傍へ残します。
- コメントは処理の逐語説明ではなく、守る不変条件、前提、理由、失敗条件を優先します。
- コメントが説明する処理を変えた差分では、同じ差分でコメントを更新または削除します。
- 名前、型、構造から自明な処理にはコメントを要求せず、コメント数や行密度を品質尺度にしません。

## 規約

### 責務コメント

- 名前、型、配置だけでは責務を安全に復元できない関数、メソッド、内部補助関数には、その定義直前へ 1 行程度の責務コメントを置くことを必須にします。
- 責務コメントは「何を実行するか」の逐語説明ではなく、「どの判断、変換、状態遷移、境界を担当するか」を書かなければなりません。
- 単純な property、stub、型宣言、名前から責務が一意に読める小さな関数には、責務コメントを要求しません。

### 判断コメント

コード近傍の判断コメントは、次の三条件をすべて満たす実装判断に必須とします。

```text
needs_local_comment(decision)
  := material_constraint(decision)
     and rationale_not_recoverable_from_names_types_or_structure(decision)
     and plausible_change_can_violate_the_invariant(decision)
```

`material_constraint` には、少なくとも次を含みます。

- 仕様上の invariant、precondition、postcondition、failure semantics
- 数式の導出、停止条件、誤差境界、tolerance、conditioning、数値安定化
- concurrency、ordering、atomicity、resource lifetime、cleanup、rollback
- security、authority、data exposure、external protocol、runtime constraint
- compatibility を維持する理由、または実装上魅力的だが禁止する alternative

判断コメントには、該当する範囲で次の情報を最小限に書かなければなりません。

- 何が常に真でなければならないか、またはどの前提に依存するか
- なぜ現在の algorithm、分岐、順序、定数、変換を採用するか
- 変更すると起きる failure、または採用してはならない alternative

### 配置と参照

- コメントは、その判断を所有する最も狭い安定した箇所へ置くことを必須にします。離れた総論コメントだけで局所判断を代替してはなりません。
- repository-wide の契約を参照する必要がある場合は、stable な canonical document の path と必要な clause を示します。
- Issue や PR は task の判断履歴として参照できますが、将来の安全な変更に必要な局所理由を Issue 番号だけへ退避してはなりません。
- 長い説明が必要になる場合は、まず名前、型、責務分割、API 境界を単純化し、それでも残る非自明な制約だけをコメントにします。

### 変更時の同期

- コメントが説明する logic、式、順序、境界、failure semantics を変更した場合は、同じ差分でコメントを更新または削除することを必須にします。
- 現在の実装と異なる stale comment、誤った前提を示す misleading comment は欠陥として扱います。
- コメントを削除すると判断根拠が失われる場合は、削除前に名前、型、構造、canonical document、または新しい局所コメントへ根拠を移さなければなりません。

## 禁止事項

- 代入、分岐、loop、関数呼び出しをそのまま言い換えるコメントを禁止します。
- comment quota、行密度、関数数を満たすためだけのコメントを禁止します。
- Issue、PR、設計文書の長文をコードへ貼り付けることを禁止します。
- コメントを複雑な実装、重複責務、曖昧な名前の代替にすることを禁止します。
- 変更された処理と矛盾するコメントを残すことを禁止します。
