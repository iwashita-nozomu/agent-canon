# Failed verification owner routing
<!--
@dependency-start
contract reference
responsibility Records the missing failure-knowledge activation route and the verified source links needed for reuse.
upstream design ../../operations/notes-lifecycle.md topic recording and reuse owner
@dependency-end
-->

## Goal And Candidate

検証で失敗した直後にトピック記録へ進み、次の関連する採用・却下判断の前に検索して
再利用する。共通規則から実行手順と保存先へ、発火条件付きで到達することを確認する。

## Reproduction Conditions

Repository: `iwashita-nozomu/agent-canon`。
調査基準: `85cbe467a75185be5b9acfad23f73f10dbda0439`（PR #1328 のマージ結果）。
対象は AgentCanon source の入口、任意の検証失敗、関連候補の次回判断。

## Verification

同じ source revision で `AGENTS.md`、`ROOT_AGENTS.md`、
`agents/canonical/SOURCE_ROUTING.md` の Reader Map を読む。
失敗時と次回判断前の案内を選び、Notes Lifecycle の保存・検索節、その先の保存 owner
へリンクを辿る。実装経路は `ROOT_IMPLEMENTATION.md` からも照合する。

| Expected result | Observed result | Evidence |
| --- | --- | --- |
| 失敗時と次回判断前の入口から保存・検索 owner が選べる | ROOT に規則はあるが、source 入口と任意作業用の owner map に対応する発火条件と行が欠けていた | 基準 revision の ROOT Always-On Boundary、AGENTS Reader Map、SOURCE_ROUTING Reader Map |
| 実装経路から同じ保存・検索 owner に到達する | ROOT_IMPLEMENTATION から Notes Lifecycle の Retrieve Before Deciding へのリンクは存在した | 基準 revision の ROOT_IMPLEMENTATION / Simplest complete implementation |
| private 保存の実行手順へ進める | Notes Lifecycle の保存節は storage contract へリンクし、agent-learning の Operating Route への直接案内は検索節側に限られていた | 基準 revision の Notes Lifecycle / Failed Verification Record、Retrieve Before Deciding |

## Established Conclusion

規則と保存機能は存在する。修正対象は、任意の検証作業で条件に応じて保存・検索手順を
選ぶ入口と、private 保存の実行 owner への接続である。実装判断だけを入口にすると、
検証専用・レビュー等の作業から必要な手順を選ぶ案内が不足する。

## Verified Remedy

ROOT の規則から repository instructions の Reader Map を参照し、source AGENTS が
条件に応じて SOURCE_ROUTING の `failed verification and reuse` 行を選ぶ。
同じ行から Notes Lifecycle の保存または検索節へ進む。新規公開 topic だけ template を
開き、private 記録だけ agent-learning の Operating Route と private log owner を使う。
既知の owner と読取済みの根拠は再利用する。

参照先の実在、見出し anchor、公開・private 両経路を既存の
`tests/agent_tools/test_check_entrypoint_owner_map.py` の
`test_failed_verification_reader_route_reaches_storage_owners` で確認する。
実行経路は既存 Entrypoint Owner Map workflow の
`python3 -m unittest tests.agent_tools.test_check_entrypoint_owner_map -v`。
実行結果と exact head は追補 PR、および #1328 の追補コメントに接続する。

## Reuse And Recheck Conditions

保存規則を追加・移動するときは、適用条件から既存の owner map、操作節、保存先、
読み戻しまでを同じ source で辿る。path、見出し、発火条件、保存責務が変わった場合は
この経路を再検証する。全資料を起動時に読む方式へ展開せず、必要な操作節を選択する。

## References

- [共通規則](../../../ROOT_AGENTS.md#always-on-boundary)
- [source 入口](../../../AGENTS.md#reader-map)
- [Source Routing](../../../agents/canonical/SOURCE_ROUTING.md#reader-map)
- [Notes Lifecycle](../../operations/notes-lifecycle.md)
- [agent-learning](../../../agents/skills/agent-learning.md#operating-route)
- [PR #1328](https://github.com/iwashita-nozomu/agent-canon/pull/1328)
