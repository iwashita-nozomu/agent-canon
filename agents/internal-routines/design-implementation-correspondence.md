# 設計・実装の対応

<!--
@dependency-start
contract agent-runtime
responsibility Gives concise guidance for comparing an explicitly selected design with repository changes.
upstream design ../canonical/CODEX_IMPLEMENTATION.md implementation and retirement sequence
upstream design ../../ROOT_AGENTS.md user authority, scope, and validation boundaries
downstream design ../skills/change-review.md reviews the current diff and selected evidence
downstream design ../../documents/design/semantic-responsibility-contract.md owns mathematical and semantic obligations when selected
@dependency-end
-->

## 目的

この routine は、必要なときに選択済み design と実装差分を読み合わせるための案内です。
独立した実行 owner、validation gate、handoff schema、または task record ではありません。

## 選択

user request、既存 workflow、または変更する product contract が design artifact を選んだ場合に
参照します。design へのリンク、設計文書の存在、複数 file の変更だけでは追加の review、
clause packet、fingerprint、closure receipt を要求しません。通常の owner-bounded change は
その owner と選択済み validation route に従います。

## Owner boundary

| 内容 | Owner |
| --- | --- |
| user request、scope、受け入れ条件 | current conversation と request owner |
| design contract、数理・証明上の条件 | 選択された design と domain owner |
| 実際の behavior | product source とその API |
| 独立した expected result | owning tests / oracle |
| 差分と選択済み evidence の review | selected review owner |
| branch、PR、integration、remote readback | Git lifecycle owner |

## 使用方法

1. current request と選択済み design の該当箇所を読む。
2. 実装の変更を product owner に置き、必要な test oracle と selected validation を使う。
3. design assumption または public contract が変わった場合は、その design owner と current user authority に従って変更する。
4. closeout では必要な source path、diff、validation result を conversation または既存の Issue/PR に報告する。

関連文書を読む量は、decision を変え得る owner boundary と unresolved claim で決めます。
repository 全体を traverse したり、設計節、変更 path、command、result を重複した task-local
record に保存したりしません。要求された mathematical intent、proof, experiment, hook log,
Eval artifacts はそれぞれの既存 domain owner に残します。

## Related Document Closure

選択した design から通常のリンクと実装 owner をたどり、現在の変更判断に必要な参照だけを
確認します。この読み合わせは handoff/readiness gate を生成せず、成功や authorization の証拠を
代替しません。

Implementation は [Codex Implementation](../canonical/CODEX_IMPLEMENTATION.md) と
[Change Review](../skills/change-review.md) に従います。数学・証明・実験の追加条件は
それぞれの domain skill と contract が所有します。
