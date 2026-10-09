# parent-repository-audit
<!--
@dependency-start
contract skill
responsibility Audits a parent repository by semantic unit and routes every finding through repair, readback, and closure.
upstream design ../../documents/design/parent-repository-audit.md owns semantic unit selection and failure semantics
upstream design ../../documents/parent-repository-audit/README.md owns the canonical reader route
upstream design ../../responsibility-scope.toml owns the tracked-path owner/class relation
upstream design ../skills/catalog.yaml owns public capability and command metadata
upstream design ../skills/skill-dependencies.yaml owns prerequisite and routing relations
upstream implementation ../../tools/analysis/code/parent_repository_audit.py owns deterministic unit selection and evidence receipts
downstream implementation ../../.codex/personal/skills/parent-repository-audit/SKILL.md exposes this source skill as a generated runtime adapter
@dependency-end
-->

## Reader Map

- 目的: AgentCanon を利用する親 repository を semantic audit unit ごとに読み、finding を owner repair、対象 readback、closure まで進める。
- 入口: [documents/parent-repository-audit/README.md](../../documents/parent-repository-audit/README.md)、catalog capability、dependency map、resolver が解決した tool command の順に読む。
- 順序: `list` が返す selected unit とその依存・write boundary に従う。path 順は一覧表示の順であり、独立 unit の実行を直列化しない。
- 境界: path owner/class は親の `responsibility-scope.toml`、path existence/kind は structure contract、AgentCanon runtime lifecycle は standalone `bootstrap.sh` と明示 runtime root が所有する。
- 出力: selected surface/unit、tracked evidence count、unit ごとの `pass|closed|failed|deferred|blocked`、repair/readback evidence、全体 status。

## Capability And Routing

この skill は catalog の explicit capability `parent_repository_audit`、skill dependency map、
`agent_canon_source_root` の typed resolution、親 root の Git evidence を routing authority と
します。prompt の語句や directory 名から owner/unit を推測しません。capability が不明・
重複・ambiguous、または source root が解決不能なら既存 typed failure を返します。

監査や修正に必要な routing / execution owner を選びます。`agent-orchestration` と
`codex-task-workflow` は repo-changing audit execution に適用し、`structure-refactor` と
`dependency-analysis` は該当 unit の境界・依存がその判断を必要とするとき、
`subagent-bootstrap` は選択 route が child handoff を必要とするときに使います。
finding は change surface に応じて既存の owner skill/worker へ routing し、新しい
path registry、checker、runtime graph を追加しません。

## Use When

- 親 repository の structure、AgentCanon root view、environment、dependency、code/type、
  tests、docs/design、CI/hooks/skills、templates/generated boundary を横断監査するとき。
- finding report だけで停止せず、owner repair、対象 readback、closure receipt まで完了するとき。
- AgentCanon/shared contract、parent contract、public skill、catalog、dependency map、resolver、
  tool command の変更に対応する audit unit を同じ PR で更新するとき。

## Source And Evidence Boundary

正本は [documents/parent-repository-audit/README.md](../../documents/parent-repository-audit/README.md) と `audit-unit/*.md` です。各 unit は
`Owner Responsibility`、`Invariant`、`Evidence Sources`、`Repair Route`、`Validation`、
`Close Condition`、`Related Change Surfaces`、`Legacy Migration IDs` を持ちます。

unit Markdown は broad path glob や owner map を持ちません。parent-specific tracked tree、
branch、commit、finding、repair/readback receipt は親側 evidence です。generated report、
summary、inventory、runtime shim は再生成可能な projection であり unit invariant の正本では
ありません。

## Deterministic Unit Selection

親 root から resolver が返す owner command を実行します。

```bash
python3 tools/analysis/code/parent_repository_audit.py list \
  --root <parent-root> --format text
python3 tools/analysis/code/parent_repository_audit.py list \
  --root <parent-root> --surface <stable-surface> \
  --scope <tracked-evidence-path> --format text
```

- `--surface`: unit の `Related Change Surfaces` にある stable ID から unit を選択する。
- `--scope`: 親 root 内の tracked file/directory evidence を絞るだけで、owner や unit を選ばない。
- selector なし: 全 unit と全 tracked path evidence を返す。
- AgentCanon source: 親の ignored qualified clone と source PR/readback だけを evidence とし、親の tracked tree に source internals を展開しない。

unknown surface、invalid unit、source/root path escape、missing evidence scope、parent Git missing
は typed failure です。path coverage/overlap はこの tool では計算せず、親の
`responsibility_scope.py` が canonical tracked-path relation を一度だけ検証します。

check packet は unit receipt の全体状態を集約します。

```bash
python3 tools/analysis/code/parent_repository_audit.py check \
  --root <parent-root> \
  --unit-status <pass|closed|failed|deferred|blocked> \
  --format text
```

`failed|deferred` が一件でもあれば failed、blocked があれば blocked、全 receipt が
`pass|closed` の場合だけ pass とします。未実行 command を pass に昇格しません。

## Audit And Repair Loop

Read back the README, capability, dependency relation, resolved command, and
`list` result needed to establish the selected units. For each unit, use its
owner, invariant, evidence, repair, validation, and close condition. Independent
units may be investigated or repaired in parallel when their write scopes,
authorities, and dependencies permit; serialize conflicting writes. Keep each
unit receipt with its evidence, and do not close a unit whose required readback
or validation is missing. A blocked unit records its owner, blocker, attempted
repair, and missing readback; continue with independent selected work. Aggregate
only the selected unit receipts, keeping `pass|closed` distinct from
`blocked|unresolved`.

## Owner Unit Routes

| Unit | Owner route | Static-first evidence |
| --- | --- | --- |
| `repository-structure` | `structure-refactor` | required/optional path existence、filesystem kind、canonical scope check |
| `ownership-root-views` | `agent-canon-update` | source clone、PR/main readback、runtime boundary |
| `environment-containers` | `environment-maintenance` | base image、cold build、user/sudo、owner split、host driver |
| `dependency-integrity` | `dependency-analysis` | headers、dependency manifests、graph direction |
| `code-type-boundaries` | `oop-type-design`、language review | public type、state ownership、implementation trace |
| `tests-and-oracles` | `test-design`、language review | necessary/sufficient oracle、targeted test |
| `docs-design-trace` | `long-form-writing`、`md-style-check` | reader route、formatter、design correspondence |
| `ci-hooks-skills` | `agent-orchestration` と owner tooling | catalog、capability、shim、dependency graph |
| `templates-generated-boundaries` | `document-canon-cleanup`、`result-artifact-writeout` | source/evidence/generated classification |

## Validation Boundary

static structure、scope relation、dependency、type、docs、CI syntax、Git readback を第一 evidence
とします。runtime validation は unit invariant が static に確定できない場合だけ、その unit の
`Validation` にある必要最小限を実行します。重複 checker、全 repo の二重 path scan、無関係な
full suite、不要な Docker build は追加しません。

contract 変更時は変更 surface に対応する unit file だけを更新し、source→skill→catalog/
dependency→generated shim→対象 unit の順で readback します。

## Closeout Tokens

completion report には少なくとも次を残します。

- audit status、selected surfaces、selected unit list
- tracked evidence count と任意 `--scope` evidence path
- unit ごとの `pass|closed|failed|deferred|blocked`
- finding、repair、target readback、実行した validation
- 未実行/検証不能事項と次の owner action

blocked または unresolved があれば全体を pass とせず、integration_executor または
decision-owning reviewer へ typed next action を返します。
