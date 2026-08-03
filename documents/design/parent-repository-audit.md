<!--
@dependency-start
contract design
responsibility Defines the canonical parent-repository audit surface, unit boundaries, migration map, and implementation contract.
upstream design ../rule/README.md document placement and Japanese prose rules
upstream design ../structure/repo-structure-contract.toml repository structure and source/view boundary contract
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface ownership
upstream design ../../agents/COMMUNICATION_PROTOCOL.md parent orchestration and finding closure handoff contract
upstream design ../../agents/skills/agent-orchestration.md write-capable handoff validation trust boundary
upstream design ../../agents/skills/catalog.yaml public skill catalog and tool command ownership
upstream design ../../agents/skills/skill-dependencies.yaml public skill dependency graph
downstream design ../parent-repository-audit/README.md canonical audit surface reader route
downstream implementation ../../tools/agent_tools/parent_repository_audit.py deterministic unit enumeration and contract checker
downstream implementation ../../agents/skills/parent-repository-audit.md public audit-and-repair skill
downstream implementation ../../agents/skills/catalog.yaml skill routing and command metadata
downstream implementation ../../agents/skills/skill-dependencies.yaml skill prerequisites and successors
@dependency-end
-->

# 親レポ監査の設計

## Reader Map

この文書は、AgentCanon を利用する親 repository 全体を責務別 unit として監査し、`documents/parent-repository-audit/README.md` を正本入口として、
finding の修正、対象 readback、close まで完了させる canonical surface の設計正本です。
最初に「設計判断」、次に「正本 path と所有境界」、その後に「unit 分割」、
「既存 checklist 移行 map」、「実装と検証」を読みます。根拠は `documents/design/parent-repository-audit.md` です。

## 設計判断

### Evidence And Assumption Ledger

| ID | Evidence | 判断への影響 | 仮定/未確定分岐 |
| --- | --- | --- | --- |
| E1 | `tools/agent_tools/agent_canon_source_root.py` が standalone/vendored を判定し、resolved source root で command を実行する | skill/tool の実行経路は既存 resolver を再利用する | 親が非標準配置なら明示 override を使い、source root を親 path に複製しない |
| E2 | `agents/skills/catalog.yaml` が `routing.capabilities` と tool command を所有し、`skill_route_catalog.py` が capability route を読む | audit skill は keyword-only matcher ではなく capability route と dependency map を持つ | prompt の候補選択と明示 capability の確定を混同しない |
| E3 | `agents/skills/skill-dependencies.yaml` が prerequisite/successor/order/parallel relation を所有する | audit skill の前提と writer delegation の順序はこの map に追加する | unrelated public skill の relation は変更しない |
| E4 | `tools/agent_tools/skill_shim_materializer.py` が `.agents/skills/*/SKILL.md` の唯一の writer で、`check`/`readback` を提供する | new skill shim は手作業で作らず materializer の fixed point を readback する | materializer の全件出力は selected validation に含む場合だけ実行する |
| E5 | 親の `documents/repository-audit-checklist.md` は14 section、監査 metadata、section別確認 command を一つに混在させる | legacy は親側の薄い reader route へ移し、canonical invariant は unit に分解する | 親固有の command/contract は該当 unit だけの change surface とする |
| E6 | AgentCanon PR workflow は source PR/source main と親 pin PR/parent main を別 lane とする | audit worker は source PR を作成/mergeせず、parent integrator が publication を担当する | GitHub state/権限の最終判定は parent-only とする |

この ledger は設計判断の根拠 `documents/design/parent-repository-audit.md` を固定します。生成 inventory、review report、run bundle は
ledger の代わりにならず、current source snapshot を再読した evidence path としてだけ使います。

### 所有責務と置換単位

- AgentCanon は、親 repository に共通する監査責務の定義、unit の invariant、evidence `documents/parent-repository-audit/README.md`
  source、owner repair route、validation、close condition を所有します。`documents/parent-repository-audit/README.md` がその入口です。
- `documents/parent-repository-audit/audit-unit/<unit>.md` が一つの変更責務単位です。`documents/parent-repository-audit/audit-unit` が実体です。
  一つの unit file は一つの owner responsibility を持ち、必要な契約項目を自己完結して `documents/parent-repository-audit/audit-unit`
  記述します。
- 親 repository は、監査対象の実 tree、branch、tracked files、runtime state、finding
  evidence、修正差分、readback receipt を所有します。これらは AgentCanon 正本に保存
  しません。
- `README.md` は reader route と選択規則だけを持ち、audit item の二重正本になりません。`documents/parent-repository-audit/README.md` が該当します。
  generated inventory、summary、report、run bundle は `documents/parent-repository-audit/README.md` の evidence または任意 projection
  であり、canonical source ではありません。

### 監査の順序と finding closure

`parent_repository_audit.py` が対象 root から AgentCanon source root/path resolver を
経由して正本 unit file を決定論的な POSIX lexicographic 順で列挙します。public skill は
その順序で unit を一つずつ読み、次の遷移を unit ごとに完了させてから次へ進みます。

```text
unit selected -> evidence read -> pass
                         \-> finding -> owner skill/worker repair -> target readback -> closed
```

finding は監査全体を abort する理由になりません。修正可能な finding は親を orchestrator
として owner skill/worker へ routing し、writer delegation の validation trust boundary
を保持します。修正できない finding は unit の closure record に owner、evidence、blocked
理由を残し、次の unit へ進みます。最終判定では未 close finding を audit complete と扱いません。

### 静的 evidence の優先

構造、root view、dependency、code/type/OOP、docs/design trace、CI/hooks/skills/templates、
Git/PR lifecycle は tracked tree と既存 checker の readback を第一 evidence とします。
Docker image 間の差分 build、不要な runtime smoke、既定 full suite、全 repo の重複 rescan は
unit の invariant が静的に確定できない場合を除き選択しません。各 unit は必要条件と十分条件
を分け、必要十分な command だけを `Validation` に持ちます。

## 正本 path と source/view 境界

| Path | 所有 | 状態 | 役割 |
| --- | --- | --- | --- |
| `documents/parent-repository-audit/README.md` | AgentCanon | 新設正本 | audit surface の入口、列挙規則、証拠境界 |
| `documents/parent-repository-audit/audit-unit/*.md` | AgentCanon | 新設正本 | 一変更責務単位ごとの self-contained audit contract |
| `documents/design/parent-repository-audit.md` | AgentCanon | 新設正本 | target state、unit map、移行と実装の設計 |
| `agents/skills/parent-repository-audit.md` | AgentCanon | 新設正本 | public skill の実行 workflow と closure protocol |
| `.agents/skills/parent-repository-audit/SKILL.md` | AgentCanon | generated runtime view | catalog から materialize する discovery adapter |
| `tools/agent_tools/parent_repository_audit.py` | AgentCanon | 新設実装 | source root resolver 経由の unit enumeration/contract check |
| `agents/skills/catalog.yaml` | AgentCanon | owner registry | capability/dependency-aware public skill route |
| `agents/skills/skill-dependencies.yaml` | AgentCanon | owner registry | prerequisite/successor/parallel relation |
| `tests/agent_tools/test_parent_repository_audit.py` | AgentCanon | targeted test | enumeration、path escape、unit contract、coverage の必要条件 |
| 親の `documents/repository-audit-checklist.md` | 親 repository | 移行対象 | source canon ではなく、unit 参照へ置換する legacy surface |
| 親の `reports/`、run bundle、audit output | 親 repository | evidence | canonical unit source ではない |

AgentCanon source root と親 root の同名 view は `agent_canon_source_root.py` が判定します。
skill command は論理的な `python3 tools/agent_tools/parent_repository_audit.py ...` を使い、
source root、execution cwd、execution argv の解決を既存 command packet に委ねます。
親の root view や個人 `~/.codex` は AgentCanon source に複製しません。

public skill の確定 route は、catalog の `routing.capabilities` にある
`parent_repository_audit`、dependency map の prerequisite/successor、
`skill_tool_commands.py show --skill parent-repository-audit` の resolved
`source_root`/`execution_cwd`/`execution_argv` の三点で閉じます。skill 本文から親 root の
相対 path を直接実行する fallback は route authority になりません。`agents/skills/parent-repository-audit.md` が実行契約です。

### 既存 schema を使う route record

実装時に追加する catalog record は既存 schema の次の値で固定します。

```yaml
- id: parent-repository-audit
  canonical_doc: agents/skills/parent-repository-audit.md
  shim: .agents/skills/parent-repository-audit/SKILL.md
  routing:
    stage_policy: active
    capabilities:
      - id: parent_repository_audit
        owner: parent_repository_audit
        phase: repo_changing_audit
        activation: explicit_capability
        exclusive: true
  tool_commands:
    required:
      - python3 tools/agent_tools/parent_repository_audit.py list --root <parent-root> --format text
    conditional:
      - python3 tools/agent_tools/parent_repository_audit.py check --root <parent-root> --format text
```

`skill-dependencies.yaml` の row は次で固定します。

```yaml
parent-repository-audit:
  responsibility_group: delivery
  required_prerequisites:
    - agent-orchestration
    - codex-task-workflow
    - structure-refactor
    - dependency-analysis
    - subagent-bootstrap
  routing_candidates:
    - change-review
    - document-canon-cleanup
    - tool-finding-report
  successors: []
  order_constraints: []
  parallel_independent: []
```

route は既存 `SkillRoutingRule`/`CapabilityRoute` の parser、依存 map `agents/skills/skill-dependencies.yaml` の typed row、
`agent_canon_source_root.RootResolution` の result を再利用します。新しい capability
schema、resolver、route checker は追加しません。unknown/duplicate/ambiguous capability は `agents/skills/catalog.yaml` の既存schemaで判定します。
既存 capability failure、source root の missing/override incomplete/command missing/escape
は既存 `SourceRootFailure.code` をそのまま返します。

### audit tool の failure semantics

監査 tool と public skill は次の stable failure code を使います。`repair_blocked` は unit の
closure record を残して次の unit へ進みますが、全体を `pass` に昇格しません。

| 状態 | code | 到達状態 |
| --- | --- | --- |
| AgentCanon source root が見つからない | `agent_canon_source_root_missing` | `blocked`、編集なし |
| unit file の required section/field が不正 | `parent_repository_audit_unit_invalid` | `failed`、該当 unit を選択しない |
| unit path/scope が source root または parent root 外へ escape | `parent_repository_audit_path_escape` | `failed`、編集なし |
| tracked tree に未割当 path がある | `parent_repository_audit_uncovered_tracked_path` | `failed`、監査開始前に停止 |
| owner skill/worker の修正が blocked | `parent_repository_audit_repair_blocked` | unit を閉じず次 unit、全体 `blocked` |

`uncovered_tracked_path` は親 Git の `git ls-files -z` と unit の `Scope Patterns` の照合で
判定し、submodule 内部 tree は parent tracked universe に含めません。overlap は failure
ではなく、unit の primary invariant/cross-reference を output する証拠です。

## Canonical audit unit map

各 unit file は、少なくとも `Owner Responsibility`、`Invariant`、`Evidence Sources`、
`Repair Route`、`Validation`、`Close Condition`、`Related Change Surfaces`、`Scope Patterns`（`documents/parent-repository-audit/audit-unit`）、
`Legacy Migration IDs`、`documents/parent-repository-audit/audit-unit` を持ちます。`documents/parent-repository-audit/audit-unit/*.md` が対象です。unit file の追加・変更は関係する責務だけに限定し、無関係
unit を同じ変更で更新しません。

| Unit file | owner responsibility | 主対象 |
| --- | --- | --- |
| `audit-unit/repository-structure.md` | tracked tree と directory responsibility | 全 tracked tree、README、AGENTS、scope |
| `audit-unit/ownership-root-views.md` | AgentCanon pin と source/view ownership | `vendor/agent-canon`、root views、`.codex`、`.agents` |
| `audit-unit/environment-containers.md` | Docker/devcontainer と環境境界 | `docker/`、`.devcontainer/`、environment manifests |
| `audit-unit/dependency-integrity.md` | dependency header/graph と import boundary | headers、manifests、dependency tools |
| `audit-unit/code-type-boundaries.md` | code API/type/runtime boundary | implementation、public APIs、static type tools |
| `audit-unit/oop-responsibility.md` | OOP responsibility と reuse boundary | class/module/helper、OOP evidence |
| `audit-unit/tests-and-oracles.md` | tests の必要十分性と oracle | tests、fixtures、test commands |
| `audit-unit/docs-design-trace.md` | docs、design、DIC trace | README、documents、design/implementation trace |
| `audit-unit/ci-hooks-skills.md` | CI execution、hooks、public skill capability routing | `.github/workflows/`、`.codex/hooks`、`agents/skills/` |
| `audit-unit/templates-generated-boundaries.md` | templates と generated/evidence boundary | `templates/`、reports、inventories、run artifacts |
| `audit-unit/git-pr-lifecycle.md` | Git remote、branch、PR authority、commit/push lifecycle | `.git` state、remote、`.github/PULL_REQUEST_TEMPLATE*` |
| `audit-unit/audit-evidence-closeout.md` | audit state、finding closure、handoff evidence | parent-specific audit records、closeout/readback |

### 全 tracked tree の coverage

`repository-structure.md` は親 Git の `git ls-files -z` の全結果を最初の evidence universe
として記録します。親が `vendor/agent-canon` submodule を持つ場合、その entry は親の
tracked gitlink として扱い、submodule 内部の file を親 tree に混ぜません。tool は全 tracked
path を unit の `Scope Patterns` に照合し、`uncovered_paths` が一つでもあれば failure を
返します。複数 unit に一致する path は許可しますが、各 unit の `Related Change Surfaces`
に primary invariant と cross-reference を書き、`overlap_paths` と owner を output します。
ignored/generated file は tracked tree の代替にせず、対象に含める場合は
`templates-generated-boundaries.md` が evidence boundary を明示します。

## 既存 checklist の移行 map

親側の `documents/repository-audit-checklist.md` は一つの checklist に複数 owner を混在させる
legacy surface です。`documents/repository-audit-checklist.md` が対象です。親 repository 側で、次の順に内容を unit へ移し、legacy file は `documents/parent-repository-audit/README.md` unit
reader route `documents/parent-repository-audit/README.md` への薄い参照または削除にします。AgentCanon source は親固有 state を直接編集
せず、移行先の canonical unit と旧 section の対応をここで固定します。

| legacy section | 移行先 unit | 判定 |
| --- | --- | --- |
| `この文書の読み方` | `README.md` | unit の列挙順、source/evidence 境界、finding closure の reader route |
| `監査メタ情報` | `audit-evidence-closeout.md` | 日付、監査者、対象 root/branch/commit、結果、block 理由を親 evidence に保持 |
| `1. Git と Remote` の各 checkbox/command | `git-pr-lifecycle.md` | remote、branch、HEAD、push の primary invariant |
| `2. AgentCanon Latest と Submodule` | `ownership-root-views.md` | source/view invariant へ移行 |
| `3. MCP と Codex Runtime` | `ownership-root-views.md` | root runtime ownership へ移行 |
| `4. Runtime Surface と Link 構成` | `ownership-root-views.md` | root-view readback へ移行 |
| `5. Dependency Header と Graph` | `dependency-integrity.md` | header/graph invariant へ移行 |
| `6. 文書と README 導線` | `docs-design-trace.md` | reader/design trace へ移行 |
| `7. Workflow、Skill、Eval、Goal` | `ci-hooks-skills.md` と `audit-evidence-closeout.md` | route と evidence lifecycle を分離 |
| `8. Tooling と静的解析` | `code-type-boundaries.md`、`tests-and-oracles.md` | code/static と test oracle を分離 |
| `9. Docker、Dev Container、Jupyter` | `environment-containers.md` | image差分buildを除外し静的契約へ移行 |
| `10. 再利用、OOP、数理と実装境界` | `oop-responsibility.md` と `code-type-boundaries.md` | owner boundary と code contract を分離 |
| `11. 結果ログ、可視化、Artifact` | `templates-generated-boundaries.md` と `audit-evidence-closeout.md` | generated と parent evidence を分離 |
| `12. 派生 Repo 監査` | `ownership-root-views.md`、`git-pr-lifecycle.md` | pin と publication lifecycle を分離 |
| `13. GitHub Actions` の各 checkbox/command | `ci-hooks-skills.md` | workflow YAML、permissions、concurrency、checkout、CI readback |
| `13. PR Checklist` の各 checkbox/command | `git-pr-lifecycle.md` | PR template、authority、review、merge/push evidence |
| `14. Push と完了判定`、`最終監査判定` | `audit-evidence-closeout.md`、`git-pr-lifecycle.md` | close condition と push evidence を分離 |

移行後に legacy checklist `documents/repository-audit-checklist.md` と canonical unit が同じ invariant の正本にならないよう、親側
の legacy file は unit path `documents/parent-repository-audit/README.md` の reader route だけを持ちます。親固有の未移行項目が見つかった
場合は、該当 unit `documents/parent-repository-audit/audit-unit/*.md` の `Related Change Surfaces` に限って同 PR で更新します。

### legacy command の受け皿

| legacy command family | 移行先の Validation | 親側 evidence |
| --- | --- | --- |
| `git status`、`git remote`、`git rev-parse`、`git log`、`git push` | `git-pr-lifecycle.md` | branch/HEAD/remote/push receipt |
| `git submodule status`、`ls-remote`、`sync_agent_canon.sh check` | `ownership-root-views.md` | pin/root-view readback |
| `surface_manifest.py`、root `mcp` absence | `ownership-root-views.md` | forbidden legacy path receipt |
| `run_repo_dependency_review.sh`、`check_dependency_headers.py`、graph checks | `dependency-integrity.md` | header/edge/graph receipt |
| `make docs-check`、Markdown lint/math/link checks、README grep | `docs-design-trace.md` | docs checker and link readback |
| workflow/eval/goal/convention commands | `ci-hooks-skills.md`、`audit-evidence-closeout.md` | route/lifecycle receipt |
| pyright、ruff、pytest、static/OOP tools、vector search | `code-type-boundaries.md`、`oop-responsibility.md`、`tests-and-oracles.md` | targeted tool output and oracle receipt |
| Docker dependency validator、container config、pack print-only | `environment-containers.md` | static environment receipt; image差分build is excluded |
| artifact/run-bundle/findings/visualization commands | `templates-generated-boundaries.md`、`audit-evidence-closeout.md` | parent-specific evidence path |
| GitHub workflow YAML parse、PR template/AgentCanon workflow grep | `ci-hooks-skills.md`、`git-pr-lifecycle.md` | source PR / parent PR lane evidence |

各 legacy checkbox は上表の unit file に同じ意味の invariant と close condition として移し、
unit file に移せない親固有値は parent evidence の `deferred_with_issue` として closeout
unit が owner/理由を保持します。単に section 名だけをリンクして command を失う移行は不十分です。

## One-time legacy migration ledger

この ledger は legacy checklist から canonical unit へ一回だけ移行したことを証明する trace です。
監査実行用の checklist ではなく、unit file が持つ invariant/evidence/validation/close condition の
正本を置き換えません。ID はこの migration で固定し、移行完了後に新規監査項目を追加する用途へ
再利用しません。各行は legacy の metadata、checkbox、command を一つだけ表し、target は exact
`audit-unit/*.md` path です。

### Metadata

| Stable item ID | Legacy line | Exact legacy item | Exact audit unit |
| --- | ---: | --- | --- |
| PRA-M01 | 26 | 監査日: | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-M02 | 27 | 監査者: | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-M03 | 28 | 対象 repo: | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-M04 | 29 | 対象 branch: | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-M05 | 30 | 対象 commit: | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-M06 | 31 | 比較対象 remote: | `documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md` |
| PRA-M07 | 32 | 監査結果: \\`pass\\` / \\`revise\\` / \\`blocked\\` | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-M08 | 33 | block 理由: | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |

### Checkbox items

| Stable item ID | Legacy line | Exact legacy item | Exact audit unit |
| --- | ---: | --- | --- |
| PRA-C001 | 37 | \\`git status --short --branch --untracked-files=all\\` を確認した | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C002 | 38 | 作業開始時点の dirty file を user 変更、生成物、今回変更に分類した | `documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md` |
| PRA-C003 | 39 | \\`origin\\` が GitHub canonical repo を向いている | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C004 | 40 | \\`main\\` が \\`origin/main\\` と意図通り一致している | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C005 | 41 | push 先が GitHub canonical であることを確認した | `documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md` |
| PRA-C006 | 42 | commit message に remote migration や AgentCanon pin 変更の理由が残っている | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C007 | 55 | \\`make agent-canon-ensure-latest\\` が pass している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C008 | 56 | \\`vendor/agent-canon\\` の pin が AgentCanon GitHub \\`main\\` と一致している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C009 | 57 | \\`.gitmodules\\` の \\`vendor/agent-canon.url\\` が GitHub canonical repo を向いている | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C010 | 58 | GitHub 操作の protocol が \\`gh auth status\\` と矛盾していない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C011 | 59 | SSH 利用時は \\`github.com\\` の host key と GitHub auth が通る | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C012 | 60 | HTTPS 利用時は非対話 fetch が credential error で止まらない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C013 | 61 | shared root surface drift がある場合は \\`bash tools/agent-canon/sync_agent_canon.sh link-root\\` で修復済み | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C014 | 77 | MCP は root \\`mcp/\\` directory ではなく \\`.codex/config.toml\\` と Codex runtime surface の責務として扱われている | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C015 | 79 | removed legacy surface \\`mcp\\` が tracked root に復活していない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C016 | 80 | MCP に関する運用判断を ad hoc local process 置換で済ませていない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C017 | 81 | MCP status と通常の \\`git status\\` の差異がある場合、原因を確認済み | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C018 | 93 | root \\`agents/\\` は \\`vendor/agent-canon/agents\\` の runtime view として整合している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C019 | 94 | root \\`.agents/\\` は \\`vendor/agent-canon/.agents\\` と整合している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C020 | 95 | root \\`tools/agent-canon/\\` は \\`vendor/agent-canon/tools\\` と整合している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C021 | 96 | removed legacy surface \\`mcp\\` は root view として扱われていない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C022 | 97 | \\`AGENTS.md\\` は thin entrypoint として保たれている | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C023 | 98 | shared surface の変更は \\`vendor/agent-canon/\\` 側を正本としている | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C024 | 99 | template 固有の説明は \\`documents/\\` に置かれ、Dockerfile に焼き込まれていない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C025 | 111 | すべての human-authored text file に \\`@dependency-start\\` / \\`@dependency-end\\` がある | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C026 | 112 | 旧形式の dependency header が残っていない | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C027 | 113 | header の \\`responsibility\\` が file の責務を説明している | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C028 | 114 | \\`upstream\\` と \\`downstream\\` が人間と agent の読み順に役立つ粒度になっている | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C029 | 115 | 自己参照がない | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C030 | 116 | 循環参照がない | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C031 | 117 | 孤立 manifest がない | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C032 | 118 | 差分限定ではなく全 repo の dependency review を実行している | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-C033 | 131 | \\`README.md\\` が現在の repo 構造、AgentCanon 構成、主要 command を説明している | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-C034 | 132 | \\`documents/README.md\\` から重要な正本文書へ辿れる | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-C035 | 133 | stale path、旧 helper 名、削除済み workflow への参照が残っていない | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-C036 | 134 | 長文文書は単体で目的、前提、手順、検証が読める | `documents/parent-repository-audit/audit-unit/docs-design-trace.md` |
| PRA-C037 | 135 | Markdown の見出し階層、list、code block、link が崩れていない | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-C038 | 136 | 新しい監査・運用文書が正本と重複していない | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-C039 | 137 | 文書変更に \\`make docs-check\\` の evidence がある | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-C040 | 150 | \\`$agent-orchestration\\` が repo task の最初に呼ばれる構成になっている | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C041 | 151 | task workflow が requirements、research、plan、design、implementation、review、closeout に分離されている | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C042 | 152 | eval は skill、workflow、subagent prompt、config、memory の改善判断を対象にしている | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C043 | 153 | eval 結果が artifacts または memory に蓄積される導線がある | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C044 | 154 | \\`/goal\\` または \\`goal.md\\` 利用時に初期目標、default criteria、repo 固有 criteria が分離されている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C045 | 155 | adaptive improvement loop が反復ごとに評価、逸脱検出、prompt 修正、再評価を残す | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C046 | 156 | subagent lifecycle が fresh task ごとに再起動され、closeout 前に close される | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C047 | 157 | 明示依頼なしの spawn を runtime 上位制約で強制しようとしていない | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C048 | 170 | \\`make agent-checks\\` が pass している | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C049 | 171 | \\`make ci\\` が pass している | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C050 | 172 | Python 変更では \\`pyright\\`、\\`ruff\\`、\\`pytest\\` が pass している | documents/parent-repository-audit/audit-unit/tests-and-oracles.md |
| PRA-C051 | 173 | C / C++ 変更では project-native configure、build、test が pass している | documents/parent-repository-audit/audit-unit/tests-and-oracles.md |
| PRA-C052 | 174 | hardcoded number、static \\`Any\\`、log helper naming、OOP readability の tool が必要範囲で pass している | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-C053 | 175 | tool の重複実装や legacy 配置が OOP check 用など責務別に整理されている | `documents/parent-repository-audit/audit-unit/oop-responsibility.md` |
| PRA-C054 | 176 | 新規 tool は既存 tool の option 追加や薄い adapter で済まない理由が記録されている | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-C055 | 177 | vector search smoke で tool discovery が機能している | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C056 | 192 | \\`gh\\` CLI は Docker image に焼かれず、\\`vendor/agent-canon/.devcontainer/post-create.sh\\` が workspace mount 後に導入している | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C057 | 193 | \\`docker/Dockerfile\\` に Codex CLI、GitHub CLI、Node/npm など agent convenience tooling が入っていない | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C058 | 194 | 初回 GitHub auth は user が実行する前提になっている | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C059 | 195 | Codex state は container-local で、host \\`~/.codex\\` を mount / seed せず、\\`OPENAI_API_KEY\\` と \\`OPENAI_BASE_URL\\` を明示 forward できる | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C060 | 196 | devcontainer attach banner が \\`codex-state\\` と \\`codex-login\\` を表示している | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C061 | 197 | \\`docker/packs/default.toml\\` の product smoke が AgentCanon の shared post-create / finalize を呼ばない | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C062 | 198 | Makefile と Docker Build workflow が \\`tools/agent-canon/ci/run_container_pack.py\\` を直接呼ぶ | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C063 | 199 | \\`~/.ssh\\` など host 側 SSH 設定の共有方針が devcontainer に反映されている | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C064 | 200 | Jupyter Notebook が container 内で起動できる | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C065 | 201 | \\`docker/register_safe_directories.sh /workspace\\` が \\`/workspace\\` と \\`vendor/*\\` 由来の \\`/workspace/vendor/<name>\\` を \\`safe.directory\\` に登録する | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C066 | 202 | \\`.devcontainer/devcontainer.json\\` の \\`postCreateCommand\\` が safe.directory 登録 helper を呼ぶ | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C067 | 203 | \\`docker/packs/default.toml\\` の smoke が vendor safe.directory 登録を検証している | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C068 | 204 | Dockerfile に Template / AgentCanon の machine-local remote path が焼き込まれていない | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C069 | 205 | \\`docker/requirements.txt\\`、\\`docker/README.md\\`、\\`.devcontainer/\\` が矛盾していない | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C070 | 206 | Docker dependency validator が pass している | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-C071 | 219 | 新規実装前に既存 helper、既存 tool、既存 workflow、既存 fixture を探索している | documents/parent-repository-audit/audit-unit/oop-responsibility.md |
| PRA-C072 | 220 | \\`Reuse Survey\\` に見た path、再利用した path、不採用候補、不足理由が残っている | documents/parent-repository-audit/audit-unit/oop-responsibility.md |
| PRA-C073 | 221 | OOP 的に不要な state、member、helper、wrapper、整形関数を増やしていない | documents/parent-repository-audit/audit-unit/oop-responsibility.md |
| PRA-C074 | 222 | \\`None\\` runtime 判定で曖昧にせず、型で静的解析へ渡している | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-C075 | 223 | \\`Any\\` が public boundary や新規 code path に増えていない | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-C076 | 224 | 数理上の object、algorithm、implementation boundary が一致している | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-C077 | 225 | hardcoded number が定数、設定、または根拠付き literal として整理されている | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-C078 | 226 | 可読性評価は tool 出力と reviewer judgement を分けて扱っている | `documents/parent-repository-audit/audit-unit/oop-responsibility.md` |
| PRA-C079 | 240 | run bundle は \\`reports/agents/<run-id>/\\` に保存されている | `documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md` |
| PRA-C080 | 241 | \\`user_request_contract.md\\` に must-do、must-not-do、completion-evidence clause がある | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C081 | 242 | \\`schedule.md\\` が空でない | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C082 | 243 | \\`work_log.md\\` が作業開始から closeout まで更新されている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C083 | 244 | \\`verification.txt\\` が \\`status=pass\\` になっている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C084 | 245 | \\`closeout_gate.md\\` が user completion unlocked になっている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C085 | 246 | eval、monitoring、feedback、改善判断の保存先が明示されている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C086 | 247 | 可視化対象の結果ログが \\`reports/\\`、\\`notes/\\`、\\`memory/\\` のどこにあるか説明できる | documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md |
| PRA-C087 | 258 | 派生 repo の \\`vendor/agent-canon\\` pin が GitHub AgentCanon \\`main\\` と一致している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C088 | 259 | 派生 repo 固有の AgentCanon 差分がある場合、dedicated GitHub branch と AgentCanon PR に分離されている | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C089 | 260 | Template 由来 repo では root surface が Template と構造的に一致している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C090 | 261 | repo 固有の差分は \\`documents/\\`、project code、config に限定され、shared canon に混入していない | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C091 | 262 | \\`make agent-canon-ensure-latest\\` と \\`bash tools/agent-canon/sync_agent_canon.sh check\\` が派生 repo でも pass している | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-C092 | 273 | \\`.github/workflows/ci.yml\\` が submodule-aware checkout を使う | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C093 | 274 | \\`.github/workflows/ci.yml\\` が最小権限 \\`permissions\\` と stale run 用 \\`concurrency\\` を持つ | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C094 | 275 | \\`.github/workflows/docker-build.yml\\` が submodule-aware checkout、最小権限、concurrency を持つ | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C095 | 276 | \\`.github/workflows/agent-coordination.yml\\` は AgentCanon 正本から root copy へ同期されている | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C096 | 277 | Agent coordination workflow の各 job が AgentCanon submodule を checkout する | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-C097 | 278 | Template default PR checklist が repo-local 変更、AgentCanon pin、Docker、GitHub workflow、validation evidence を分けている | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C098 | 279 | Template 側 AgentCanon PR checklist が shared canon source、root surface sync、GitHub evidence を要求している | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C099 | 280 | Standalone AgentCanon repo 用の独立 PR checklist が \\`vendor/agent-canon/.github/PULL_REQUEST_TEMPLATE.md\\` にある | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C100 | 281 | GitHub automation と PR checklist が Codex workflow から辿れる | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C101 | 282 | PR checklist が未実行 command を pass と書かない運用になっている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C102 | 299 | 変更を commit 済み | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C103 | 300 | GitHub canonical remote へ push 済み | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C104 | 301 | \\`git status --short --branch --untracked-files=all\\` が clean | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C105 | 302 | \\`git log --oneline --decorate -5\\` で対象 commit が確認できる | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-C106 | 303 | 未完了の planned work、review finding、validation、commit、push、follow-up 判断が残っていない | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C107 | 304 | user-facing completion report に未実行 check を pass と書いていない | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C108 | 316 | \\`pass\\`: 監査対象は現行規約、latest pin、検証、文書導線を満たしている | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C109 | 317 | \\`revise\\`: 修正すれば pass にできる項目がある | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-C110 | 318 | \\`blocked\\`: auth、network、toolchain、未解決 conflict など監査を完了できない blocker がある | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
### Command items

| Stable item ID | Legacy line | Exact legacy command | Exact audit unit |
| --- | ---: | --- | --- |
| PRA-X001 | 47 | git status --short --branch --untracked-files=all | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X002 | 48 | git remote -v | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X003 | 49 | git rev-parse HEAD | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X004 | 50 | git rev-parse origin/main | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X005 | 66 | `make agent-canon-ensure-latest` | `documents/parent-repository-audit/audit-unit/ownership-root-views.md` |
| PRA-X006 | 67 | git submodule status vendor/agent-canon | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X007 | 68 | git config -f .gitmodules submodule.vendor/agent-canon.url | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X008 | 69 | gh auth status | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X009 | 70 | gh config get git_protocol -h github.com | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X010 | 71 | git -C vendor/agent-canon rev-parse HEAD | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X011 | 72 | git -C vendor/agent-canon ls-remote origin main | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X012 | 86 | python3 tools/agent-canon/agent_tools/surface_manifest.py removed-legacy-paths | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X013 | 87 | test ! -e mcp | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X014 | 88 | git status --short --branch --untracked-files=all | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X015 | 104 | bash tools/agent-canon/sync_agent_canon.sh check | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X016 | 105 | find AGENTS.md agents .agents tools .codex -maxdepth 1 -type l -ls | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X017 | 106 | git diff -- .agents .codex AGENTS.md agents tools | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X018 | 123 | bash tools/agent-canon/agent_tools/run_repo_dependency_review.sh --fail-missing | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-X019 | 124 | python3 tools/agent-canon/agent_tools/check_dependency_headers.py | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-X020 | 125 | `bash tools/agent-canon/agent_tools/check_dependency_header_format.sh --require-header` | `documents/parent-repository-audit/audit-unit/dependency-integrity.md` |
| PRA-X021 | 126 | bash tools/agent-canon/agent_tools/check_dependency_graph.sh --print-edges | documents/parent-repository-audit/audit-unit/dependency-integrity.md |
| PRA-X022 | 142 | make docs-check | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-X023 | 143 | python3 tools/agent-canon/docs/check_markdown_lint.py --check documents/repository-audit-checklist.md | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-X024 | 144 | python3 tools/agent-canon/docs/check_markdown_math.py documents/repository-audit-checklist.md | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-X025 | 145 | git grep -n -E "TODO\|FIXME\|old\|legacy\|subtree" -- README.md documents agents tools \|\| true | documents/parent-repository-audit/audit-unit/docs-design-trace.md |
| PRA-X026 | 162 | python3 tools/agent-canon/agent_tools/evaluate_skill_workflow_prompts.py --help | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X027 | 163 | python3 tools/agent-canon/agent_tools/goal_loop.py --help | documents/parent-repository-audit/audit-unit/audit-evidence-closeout.md |
| PRA-X028 | 164 | python3 tools/agent-canon/agent_tools/check_convention_compliance.py | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X029 | 165 | git grep -n -E "agent-orchestration\|adaptive-improvement-loop\|goal\|eval\|subagent_lifecycle" -- agents documents tools AGENTS.md \|\| true | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X030 | 182 | make agent-checks | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X031 | 183 | make ci | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X032 | 184 | python3 -m pyright | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-X033 | 185 | python3 -m ruff check python tests --select D,E,F,I,UP | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-X034 | 186 | python3 -m pytest tests/ -q --tb=short | documents/parent-repository-audit/audit-unit/tests-and-oracles.md |
| PRA-X035 | 187 | python3 tools/agent-canon/agent_tools/vector_search.py --query "dependency review" --limit 5 | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X036 | 211 | bash tools/agent-canon/docker_dependency_validator.sh | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-X037 | 212 | python3 tools/agent-canon/ci/container_config.py | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-X038 | 213 | make docker-build-check | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-X039 | 214 | python3 tools/agent-canon/ci/run_container_pack.py --pack docker/packs/default.toml --print-only | documents/parent-repository-audit/audit-unit/environment-containers.md |
| PRA-X040 | 231 | python3 tools/agent-canon/agent_tools/check_static_any.py --help | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-X041 | 232 | python3 tools/agent-canon/agent_tools/check_hardcoded_numbers.py --help | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-X042 | 233 | python3 tools/agent-canon/oop/python/readability.py --help | documents/parent-repository-audit/audit-unit/oop-responsibility.md |
| PRA-X043 | 234 | python3 tools/agent-canon/agent_tools/oop_rule_inventory.py --help | documents/parent-repository-audit/audit-unit/oop-responsibility.md |
| PRA-X044 | 235 | git grep -n -E "Any\|None\|TODO\|FIXME\|_log\|hardcoded" -- python tests tools \|\| true | documents/parent-repository-audit/audit-unit/code-type-boundaries.md |
| PRA-X045 | 252 | find reports/agents -maxdepth 2 -type f \| sort \| tail -50 | documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md |
| PRA-X046 | 253 | git grep -n -E "status=pass\|user_completion_report=unlocked\|eval\|feedback\|monitoring" -- notes memory agents documents \|\| true | documents/parent-repository-audit/audit-unit/templates-generated-boundaries.md |
| PRA-X047 | 267 | git remote -v | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X048 | 268 | git submodule status vendor/agent-canon | documents/parent-repository-audit/audit-unit/ownership-root-views.md |
| PRA-X049 | 287 | python3 - <<'PY' <br> from pathlib import Path <br> import yaml <br> for path in sorted(Path('.github/workflows').glob('*.yml')): <br> yaml.safe_load(path.read_text()) <br> print(f'{path}: yaml=pass') <br> PY | documents/parent-repository-audit/audit-unit/ci-hooks-skills.md |
| PRA-X050 | 294 | git grep -n -E "submodules: false\|checkout_agent_canon_submodule\|permissions:\|concurrency:\|PULL_REQUEST_TEMPLATE\|agent-canon-pr-workflow" -- .github vendor/agent-canon/.github agents documents \|\| true | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X051 | 309 | git log --oneline --decorate -5 | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X052 | 310 | git status --short --branch --untracked-files=all | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |
| PRA-X053 | 311 | git push origin main | documents/parent-repository-audit/audit-unit/git-pr-lifecycle.md |

移行 coverage: metadata=8, checkbox=110, command=53, total=171。

## dependency edge と変更契約

AgentCanon の監査契約、public skill、resolver/tooling、または親側の shared contract `documents/design/parent-repository-audit.md` を
変更するときは、変更が関係する unit file を同じ PR で更新します。変更が無関係な unit を
追加・改訂することは完了条件にしません。次の edge を dependency header と design/skill
本文で追跡します。

- unit source の変更 → `documents/parent-repository-audit/README.md` の列挙/reader route と
  `parent-repository-audit.py` の contract checker。unit file 内の `surface:` token が
  change-surface-to-unit closure `documents/parent-repository-audit/audit-unit/*.md` の機械的入力になります。
- public skill の変更 → `agents/skills/catalog.yaml`、`skill-dependencies.yaml`、runtime `agents/skills/parent-repository-audit.md`
  shim `agents/skills/parent-repository-audit.md`、関連 unit の `Repair Route`/`Validation`。
- resolver/tool command の変更 → `agent_canon_source_root.py`、`skill_tool_commands.py`、
  skill command section、関連 unit の evidence source。
- AgentCanon/shared runtime contract の変更 → 影響を受ける unit の `Related Change
  Surfaces` と親側 root-view readback。
- 親固有 contract の変更 → その contract を参照する unit のみ。全 unit の一括改訂はしません。

checker は各 Markdown の `surface:<stable-id>` 行を読み、explicit contract-change surface `tools/agent_tools/parent_repository_audit.py`
に対する required unit `tools/agent_tools/parent_repository_audit.py` を出力します。変更する unit は required unit を満たし、無関係な
unit を同時に変更しないことを `change-review` で確認します。implementation-only の変更で invariant
が変わらない場合は unit file を機械的に更新せず、surface closure の判定を `not_applicable`
として parent packet に残します。

## 実装・検証 packet

実装単位は audit surface、public skill/routing、deterministic tool `tools/agent_tools/parent_repository_audit.py`、targeted tests の
責務 closure `tests/agent_tools/test_parent_repository_audit.py` とします。nested design review はこの文書と path mapping のみを read-only
review し、実装を行いません。

初回の targeted validation は次です。

1. `python3 tools/agent_tools/parent_repository_audit.py check --root <parent-root>` で unit
   path、required sections、scope patterns、tracked path coverage、overlap、source-root
   resolution `tools/agent_tools/parent_repository_audit.py` を確認する。
2. `python3 -m pytest tests/agent_tools/test_parent_repository_audit.py -q` で enumeration と
   contract failure semantics `tests/agent_tools/test_parent_repository_audit.py` を確認する。
3. `python3 tools/agent_tools/check_dependency_headers.py --changed` と
   `bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing` で変更した
   source/header `tools/agent_tools/check_dependency_headers.py` の closure を確認する。
4. `tools/bin/agent-canon docs check <changed-docs>` で Markdown、link、math、Mermaid、heading
   `tools/bin/agent-canon` を確認する。
5. 既存 materializer を一回だけ `python3 tools/agent_tools/skill_shim_materializer.py
   materialize --all --root . --format json` で実行し、`content_delta_count` と
   `readback_digest` を記録する。続けて `python3 tools/agent_tools/skill_shim_materializer.py
   readback --all --root . --format json` を実行し、catalog-sized record/projection/readback
   digest `tools/agent_tools/skill_shim_materializer.py` が一致し、second readback が `status=pass` になることを確認する。新しい shim
   checker は追加せず、既存 materializer `tools/agent_tools/skill_shim_materializer.py` の結果を受入 evidence とする。
6. `python3 tools/agent_tools/skill_tool_commands.py show --skill parent-repository-audit
   --format json` で resolved `source_root`、`execution_cwd`、`execution_argv` を readback
   し、`python3 tools/agent_tools/skill_dependency_map.py check --root .` と
   `python3 tools/agent_tools/route.py --capability parent_repository_audit --mode repo-changing --format json` で `agents/skills/catalog.yaml` の catalog/dependency/capability を readback する。
   その後 `python3 tools/agent_tools/check_skill_frontmatter.py --root .`、
   `python3 tools/agent_tools/skill_tool_commands.py check`、
   `python3 tools/agent_tools/check_convention_compliance.py` で skill projection と規約を
   確認する `tools/agent_tools/skill_tool_commands.py`。

source PR/source main の review、CI、merge は AgentCanon source owner が行い、accepted
source frontier の readback 後に parent integrator が親 PR/parent main merge と pin/root
projection を行います。audit worker/tool は PR creation/merge を行いません。Docker image
差分 build、未選択の全 test、全 repo rescan `documents/parent-repository-audit/README.md` はこの worker packet の validation route に
含めません。
