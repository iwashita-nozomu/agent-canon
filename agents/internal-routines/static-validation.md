# static-validation
<!--
@dependency-start
contract agent-runtime
responsibility Documents static-validation for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

変更内容、risk、owner surface に応じて必要な quality gate を選びます。

## Use When

- 何を検証すべきか決めたい
- docs / code / environment 変更の確認をそろえたい

## Activation

`documents/runtime/runtime-profiles-and-check-matrix.md` owns profile activation and
the check matrix. Select a profile from the changed responsibility and risk; this
entrypoint does not define a standard command set or a universal closeout gate.

The owning profile or tool documentation explains the selected check's meaning.
In particular, numeric-literal and convention findings are semantic results of
their respective tools, not reasons to activate an otherwise unrelated profile.

## Boundary

- `static-check` は Codex skill 名互換の入口です。
- profile と gate の対応は runtime profile/check matrix が正本です。
- この文書は、選択した route の目的と結果を短く記録する入口です。
