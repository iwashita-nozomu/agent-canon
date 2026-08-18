# C++ Review（C++ レビュー）
<!--
@dependency-start
contract template
responsibility Documents C++ Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


## Reader Map（読者 map）

この review は C/C++ の責務境界、header/implementation、ownership、build/test entrypoint、
failure path、single-project experiment/test guidance を確認します。C++ topic 内の local
project は対象にしますが、template root に top-level CMake を要求しません。

- purpose:
- intended reader and decision:
- what this review contains:
- owner / OOP and type boundary:
- design-to-implementation trace:
- dependency / side-effect map:
- algorithm contract before tests:
- necessary-and-sufficient oracle:
- cleanup and readback:

{{>review_contract}}

## Scope（対象）

- Files reviewed:
- Public headers or ABI surfaces touched:
- Build or test entrypoints checked:

## Findings（指摘）

Each finding records one of `blocking`, `non-blocking`, `question`,
`not-applicable`, or `accepted-risk`. Only unresolved `blocking` findings make
the owning review outcome `changes-required`; style observations remain
non-blocking.

### Fix Now（今直す）

-

### Follow-Up（後続対応）

-

### Delete-Ok（削除可）

-

## Native Code Checklist（native code checklist）

- ownership / lifetime / aliasing risks checked:
- header / implementation consistency checked:
- boundary and error-path coverage checked:
- build / configure / test evidence checked:
- docs or developer-command follow-through checked:

## Notes（メモ）

-
