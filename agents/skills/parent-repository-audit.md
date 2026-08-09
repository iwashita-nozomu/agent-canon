# parent-repository-audit
<!--
@dependency-start
contract skill
responsibility Audits a complete parent tracked tree and routes every finding through repair, readback, and unit closure.
upstream design ../../documents/design/parent-repository-audit.md owns target state, migration, and failure semantics
upstream design ../../documents/parent-repository-audit/README.md owns canonical unit reader route
upstream design ../skills/catalog.yaml owns public capability and command metadata
upstream design ../skills/skill-dependencies.yaml owns prerequisite and routing relations
upstream implementation ../../tools/agent_tools/parent_repository_audit.py owns deterministic unit selection and coverage
downstream implementation ../../.agents/skills/parent-repository-audit/SKILL.md exposes this source skill as a runtime adapter
@dependency-end
-->

## Reader Map

- 目的: 親 repository の全 tracked tree を canonical audit unit ごとに読み、finding を owner repair、対象 readback、closed まで進める。
- 入口: `documents/parent-repository-audit/README.md`、次に catalog capability、dependency map、resolver が解決した tool command を読む。
- 順序: `parent_repository_audit.py list` が返す unit path を POSIX lexicographic order で一つずつ読む。unit closure 前に次へ進まない。
- 境界: 親が orchestrator、writer delegation が修正を実行する。worker は AgentCanon/親 PR の create、merge、close、admin override を行わない。
- 出力: unit ごとの `pass` または `finding -> repair -> readback -> closed`、blocked unit の blocker receipt、最後の全体 status。generated report は projection/evidence であり正本ではない。

## Capability And Routing

この skill は keyword trigger だけで起動しません。catalog の explicit capability
`parent_repository_audit`、skill dependency map、`agent_canon_source_root` の typed
resolution、親 root の tracked tree packet を routing authority とします。prompt の語句は
候補説明に留め、capability が不明、重複、ambiguous、source root が missing の場合は既存
typed failure を返して推測で別 route を選びません。

必要な前提は `agent-orchestration`、`codex-task-workflow`、`structure-refactor`、
`dependency-analysis`、`subagent-bootstrap` です。finding の repair candidate は owner
surface に応じて `change-review`、`document-canon-cleanup`、`tool-finding-report` へ
routing します。public skill の catalog、shim、dependency map、runtime graph は owner
tooling で更新し、この skill に別の routing schema を複製しません。

## Use When

- AgentCanon を利用する親 repository の全 tracked tree を structure、ownership/root view、
  environment/Docker/devcontainer、dependency、code/type/OOP、tests、docs/design trace、
  CI/hooks/skills、templates/generated boundary、Git/PR lifecycle の owner unit で監査するとき。
- 現在の規約違反を report に書くだけでなく、owner skill/worker へ修正を routing し、対象
  readback と finding close まで同じ監査責務で完了するとき。
- AgentCanon/shared contract、parent contract、public skill、resolver、catalog、dependency
  map、tool command が変更され、関係する audit unit を同じ PR で更新するとき。

## Source And Evidence Boundary

正本は `documents/parent-repository-audit/README.md` と `audit-unit/*.md` だけです。一つの
変更責務につき一つの unit Markdown file を使い、巨大 checklist、TOML/YAML/JSON を audit
canon にしません。parent-specific tracked tree、branch、commit、finding、repair receipt、
runtime output は親側 evidence です。generated summary/index、inventory、report、shim、
run bundle は再生成可能な projection/evidence であり、unit invariant の source ではありません。

旧親 file `documents/repository-audit-checklist.md` は設計 packet の一回限り migration
ledger（metadata、checkbox、command の stable ID）を通って各 unit へ移行済みです。旧 file
を第二 checklist として読み続けず、親側では unit reader route への薄い参照または廃止を
行います。未移行項目が見つかった場合は、意味が対応する unit のみを同じ PR で更新します。

## Deterministic Unit Selection

親 root から、既存 resolver 経由の owner command を実行します。

```bash
python3 tools/agent_tools/parent_repository_audit.py list --root <parent-root> --format text
```

tool は AgentCanon source root を `agent_canon_source_root.RootResolution` で解決し、
`documents/parent-repository-audit/audit-unit/*.md` を filename の昇順で読みます。各 file に
required section、`surface:<stable-id>`、`pattern:<parent-relative-glob>`、legacy migration
ID が一つずつ以上あることを確認します。`--scope` は親 root 配下の tracked file/directory
だけに限定でき、path escape と missing scope は failure です。`repository-structure` は
structure contract の required path kind だけを確認し、一般 path owner/class は親の
`responsibility-scope.toml` を参照します。`all-tracked` fallback や audit unit 間の二重
ownership を判定 source にしません。submodule 内部は親 tracked universe に展開しません。

readback が必要な check packet は次です。

```bash
python3 tools/agent_tools/parent_repository_audit.py check --root <parent-root> --format text
```

`source_root_missing`、invalid unit、path escape、uncovered selected path は audit start の
typed failure です。`repair_blocked` は unit を閉じず、owner、blocker、attempted repair、
readback 欠落を closure record に残して次 unit へ進み、最終 status を blocked にします。
failed または deferred check が残る状態は `closed` や `pass` に昇格しません。

## Sequential Audit And Repair Loop

1. README、catalog capability、dependency row、resolved tool command、`list` packet を readback し、selected unit paths を固定します。
2. selected unit を一つ読み、Owner Responsibility、Invariant、Evidence Sources、Repair Route、Validation、Close Condition をその順に消費します。
3. static evidence と parent-specific readback で invariant を判定します。pass なら unit receipt を残して次 unit へ進みます。
4. finding なら primary owner skill/worker に bounded handoff し、親 orchestrator が修正の validation route と write scope を保持します。監査を abort しません。
5. 修正後に対象 path/source/config を再読し、unit の validation を必要十分な範囲で実行します。finding の解消を readback で確認して closed receipt を残します。
6. owner が修正不能、権限、auth、network、toolchain、conflict などで blocked の場合は `parent_repository_audit_repair_blocked` を記録して次 unit へ進みます。
7. 全 selected unit の receipt を集約し、closed/pass と blocked/unresolved を区別した最終 status を作ります。未実行 command を pass と記述しません。

親は worker handoff の validation trust boundary を守り、worker は割り当てられた replaceable
unit、write scope、targeted validation、commit/push の範囲だけを実行します。PR 作成、merge、
close、admin override、最終 integration decision は親 integrator の責務です。

## Owner Unit Routes

| Unit | owner route | static-first evidence |
| --- | --- | --- |
| `repository-structure` | `structure-refactor` | structure contract、scope、required path kind |
| `ownership-root-views` | `agent-canon-update` | source root、pin、root-view sync |
| `environment-containers` | `environment-maintenance` | Ubuntu/base、cold-build、user/sudo、owner split、host driver、config |
| `dependency-integrity` | `dependency-analysis` | headers、dependency graph、full-tree review |
| `code-type-boundaries` | `oop-type-design`、`oop-readability-check` | OOP inventory と reviewer judgement |
| `tests-and-oracles` | `test-design`、language review | necessary/sufficient oracle と targeted test |
| `docs-design-trace` | `long-form-writing`、`md-style-check` | reader route、formatter、design correspondence |
| `ci-hooks-skills` | `agent-orchestration` と owner tooling | catalog、capability、shim、dependency graph |
| `templates-generated-boundaries` | `document-canon-cleanup`、`result-artifact-writeout` | source/evidence classification |

各 unit の `Repair Route` が個別の owner/tool を追加で指定します。この表を新しい分類へ
拡張せず、owner responsibility の変更は該当 unit だけを更新します。

## Validation Boundary

static structure、header、catalog、dependency、type、docs、CI syntax、Git readback を第一
evidence とします。runtime validation は invariant が static に確定できない unit の
`Validation` に明記された必要最小限だけ実行します。Docker image 間の差分 build、無関係な
全 suite、重複 checker、全 repo の二重 rescan は行いません。

Markdown、math、Mermaid、link formatter は `md-style-check` の owner route を使います。
shim は `skill_shim_materializer.py` の既存 `--all` を一回実行し、second readback で no
change を確認します。catalog/skill command/dependency route は既存 owner tool の readback
で閉じ、新しい checker を作りません。

## Contract Change Closure

AgentCanon source、parent shared contract、public skill、catalog、dependency map、resolver、
tool command の変更時は、変更 surface の `surface:<stable-id>` に対応する unit file のみを
同じ PR で更新します。`repository-structure` の tracked coverage、`ci-hooks-skills` の
capability/graph、`ownership-root-views` の source root、`environment-containers` の
environment contract など、関係がない unit は触りません。変更後は source→skill→catalog/
dependency→shim/graph→対象 unit の順で readback します。

## Closeout Tokens

親側の completion report には少なくとも `audit_status`、selected unit list、各 unit の
`pass|closed|blocked`、finding/repair/readback receipt、selected-scope uncovered count、source root
resolution、実行した validation、未実行項目を記録します。blocked があれば全体を pass とせず、
次の owner action と parent-only integration decision を残します。

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill parent-repository-audit --format text`
<!-- skill-tool-commands:end -->
