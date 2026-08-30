# branch・PR・worktree の semantic orphan lifecycle
<!--
@dependency-start
contract workflow
responsibility Defines the canonical semantic orphan inventory, finite classification, and fail-closed cleanup admission contract.
upstream design ../design/request-intent-and-update-relation.md defines lifecycle flow and existing cleanup-executor delegation.
upstream design worktree-lifecycle.md defines stale worktree handling and user-owned state protection.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines the existing PR lifecycle and publication owner.
downstream implementation ../../tools/repository/git/orphan_lifecycle.py produces the canonical read-only inventory and cleanup admission.
downstream implementation ../../tests/agent_tools/test_orphan_lifecycle.py verifies semantic equivalence and refusal behavior.
@dependency-end
-->

この文書は、古い branch、PR head、worktree を「経過日数」ではなく、最新 `main` への
意味差分、active owner、successor trace、user-owned state の有無で分類する正本です。
削除そのものは既存の branch / PR / worktree cleanup executor が所有し、本契約は第二の
branch registry、cleanup database、Issue state machine を作りません。

## 責務境界

`tools/repository/git/orphan_lifecycle.py inventory` が canonical read-only inventory を生成し、
同じ tool の `authorize-cleanup` が explicit selection を inventory digest に束縛して認可します。
どちらも ref、PR、worktree、ファイルを削除しません。

- PR の publication と GitHub mutation は `tools/repository/github/github_publish.py` および
  `agents/skills/pr-processing.md` に残ります。
- worktree の停止・除去・prune は runtime provisioning owner または user owner に残ります。
- local/remote branch の削除は、現在その resource を所有する既存 cleanup route に残ります。
- `project_template` は本判定器を複製しません。template 固有の stale artifact が観測された場合だけ
  companion Issue で具体的 cleanup を扱います。

## 安全条件

候補 `C`、inventory が固定した最新 main commit `M`、Issue/PR trace `R`、local user state
`U` に対し、cleanup admission は次の conjunction を満たす場合だけ成立します。

```text
safe(C; M, R, U)
  := no_unique_semantic_delta(C, M)
     and no_active_owner_or_unresolved_requirement(C, R)
     and traceable_resolution(C, R)
     and no_ambiguous_owner_or_successor(C, R)
     and no_dirty_untracked_unpushed_or_user_owned_state(C, U)
     and no_resource_order_blocker(C)
```

最終更新日時、branch age、PR age はこの式に現れません。時間情報は人が候補を探す際の
ヒントにはできますが、inventory は収集せず、cleanup authorization に使用しません。
一つでも観測不能または曖昧な項があれば fail closed です。

## 意味差分の判定

SHA identity だけでは squash、rebase、cherry-pick を判定できません。inventory は次を
順に read back します。

1. `merge-base` と `rev-list --left-right --count` による reachability / ahead / behind。
2. `git cherry` の patch-id equivalence。SHA が異なっても同じ patch が `main` にある場合を拾います。
3. candidate の merge-base からの changed surface を列挙し、candidate と最新 `main` の
   tree entry を path ごとに比較します。複数 commit が一つに squash されても最終 surface が
   一致すれば `surface_equivalent` です。

`main` 側が同じ path をさらに変更して exact tree comparison が成立せず、patch-id でも包含を
証明できない場合は、意味的に含まれていると推測せず `present` または `unknown` に倒します。
Issue の required outcome が別実装で満たされたという判断は、trace の resolution / successor
として人が明示しなければ cleanup 根拠になりません。

## 有限状態

| state | 判定 | 次の操作 |
| --- | --- | --- |
| `active` | open PR、active owner、または unresolved requirement がある | owner の作業・review・verification を継続する |
| `merged_equivalent` | unique semantic delta はないが resolution trace がまだない | main/Issue/PR comment の resolution を記録して再 inventory する |
| `superseded` | successor が責務を包含するが、main 到達または resolution が未完了 | successor coverage と main 到達を確認する |
| `orphan_safe_to_remove` | 上記 `safe` の全項が成立する | exact inventory digest と candidate identity を明示選択する |
| `needs_extraction` | latest main に未到達の unique delta がある | latest main 起点・Issue 番号入り branch へ必要差分だけ救出する |
| `needs_verification` | semantic/owner/successor/user-state evidence が欠落または曖昧 | 不足 evidence を取得し、推測せず再 inventory する |
| `protected_user_state` | dirty、untracked、unpushed、primary/user-managed worktree 等がある | user owner が publish・退避・破棄を明示するまで保持する |

`superseded` は cleanup-safe の同義ではありません。successor が存在しても、candidate の unique
semantic delta が最新 `main` に残る間は削除を認可しません。また successor Issue の終了条件へ
古い Issue の要求を暗黙に追加しません。

## Canonical read-only inventory

caller は先に remote を通常の Git owner で更新し、どの commit を「最新 main」として使ったかを
固定します。inventory 自身は fetch せず、ref を更新しません。

```bash
git fetch --prune origin main
python3 tools/repository/git/orphan_lifecycle.py inventory \
  --root . \
  --main-ref refs/remotes/origin/main \
  --trace reports/orphan-trace.json \
  --output reports/orphan-inventory.json
```

inventory は local branches、remote-tracking branches、linked/detached worktrees、および trace に
含まれる open/closed/merged PR heads を同じ schema へ投影します。各 candidate は identity、commit、
active owner、successor、semantic diff summary、user-state evidence、classification、cleanup blockers、
recommended action を持ちます。canonical report は JSON です。

`--trace` は既存 Issue/PR owner の readback を provider-neutral に運ぶだけです。最小 schema は次です。

```json
{
  "schema": "agent_canon.orphan_trace.v1",
  "records": [
    {
      "selector": {"branch": "fix/808-semantic-orphan-lifecycle"},
      "active_owners": ["issue:#808"],
      "successors": [],
      "requirement_state": "unresolved",
      "resolution": null,
      "worktree_owner": "runtime"
    }
  ],
  "pull_requests": [
    {
      "number": 42,
      "head_ref": "fix/808-semantic-orphan-lifecycle",
      "head_sha": "<full-sha>",
      "state": "open",
      "url": "<provider-readback-url>"
    }
  ]
}
```

selector は `candidate_id`、`branch`、`ref`、`pr_number`、`worktree_path` のいずれか一つです。
同じ candidate に複数 record が一致した場合、どちらかを採用せず `needs_verification` にします。
PR head commit が local object database にない場合も semantic comparison を推測しません。

## Fail-closed cleanup admission

cleanup 前に、inventory が出した exact digest と candidate identity を明示します。

```bash
python3 tools/repository/git/orphan_lifecycle.py authorize-cleanup \
  --inventory reports/orphan-inventory.json \
  --inventory-digest 'sha256:<inventory-digest>' \
  --root . \
  --trace reports/orphan-trace.json \
  --select 'branch:remote:origin/example'
```

認可時にも同じ root、inventory が固定した main ref、fresh Issue/PR trace から live inventory を
再生成します。保存済み inventory と live inventory の digest が一致し、selection が重複せず、candidate が
exact `orphan_safe_to_remove` で、`cleanup_blockers` が空の場合だけ認可します。出力は admission receipt
であり、`mutation_performed` は常に `false` です。ref、worktree、trace のいずれかが変わった old report、
stale digest、unknown candidate、他 state、欠損 schema は拒否します。

認可後の既存 executor は、少なくとも次を同じ Issue または PR comment から辿れる receipt に残します。

- candidate identity と inventory digest
- 実行した exact mutation command と result
- cleanup 後の ref/path absence または reachability readback
- 意味を保存した main commit または successor
- 関連 Issue/PR comment の locator

local branch に linked worktree がある場合、worktree を独立 candidate として先に分類・cleanup し、再 inventory
するまで local branch は認可しません。dirty/untracked worktree、unpushed local commit、primary worktree、
user-managed worktree は自動 cleanup 対象になりません。

## `needs_extraction` の閉じ方

unique delta を救出する場合だけ、latest main 起点の Issue 番号入り branch を作成し、inventory の
changed surface と required outcome に必要な差分だけを移します。focused validation、main/successor
readback、Issue/PR trace を残した後に元 candidate を再 inventory します。元 branch の全要求や無関係な
差分を successor の終了条件へ追加してはなりません。

## Focused verification

```bash
python3 -m unittest tests.agent_tools.test_orphan_lifecycle -v
python3 -m py_compile \
  tools/repository/git/orphan_lifecycle.py \
  tests/agent_tools/test_orphan_lifecycle.py
```

regression は squash/tree equivalence、cherry-pick/patch equivalence、superseded、unique delta、dirty
worktree、unpushed local branch、ambiguous trace、open PR、digest-bound cleanup admission、live inventory drift refusal、age 非依存を
個別に確認します。
