# Parent Repository Audit
<!--
@dependency-start
contract design
responsibility Defines the canonical surface and execution boundary for auditing a parent repository.
upstream design ../design/parent-repository-audit.md owns the target state, migration ledger, and failure semantics
upstream design ../rule/README.md owns document placement and filename rules
upstream implementation ../../tools/agent_tools/parent_repository_audit.py enumerates and checks audit units
upstream implementation ../../agents/skills/parent-repository-audit.md owns the public repair workflow
downstream implementation ../../.agents/skills/parent-repository-audit/SKILL.md exposes the runtime adapter
downstream implementation ../../agents/skills/catalog.yaml and ../../agents/skills/skill-dependencies.yaml route the capability
@dependency-end
-->

## Reader Map

- 目的: 親 repository の tracked tree を owner responsibility 単位で監査し、finding を修正、readback、close まで進める。
- 正本: この README と `audit-unit/*.md` の Markdown 集合だけが監査契約である。
- 実行順: `parent_repository_audit.py list` で対象 unit を決定論的に列挙し、skill が unit path の昇順で一つずつ読む。
- 修正境界: 各 unit の owner skill、repair tool、validation、close condition を消費する。generated report と inventory は evidence または projection であり正本ではない。
- 移行: 旧 `documents/repository-audit-checklist.md` の全 metadata、checkbox、command は設計 packet の一回限り ledger から各 unit に全射され、旧 checklist は二重正本にしない。

## Canonical Boundary

この directory は親 repository audit の canonical source です。`README.md` は
全体の reader route と境界だけを持ち、各変更責務は `audit-unit/` の一 Markdown
file に分けます。巨大 checklist、TOML、YAML、JSON を監査正本として追加しません。
集計表、finding report、run bundle、generated index は必要な場合だけ作り、source
unit の代わりに判定を行いません。

各 unit は owner responsibility、invariant、evidence source、repair skill と tool、
validation、close condition、related change surface、scope pattern、legacy migration
ID を自己完結して持ちます。unit の変更責務が変わったときは、その unit だけを
同じ変更責務の PR で更新します。AgentCanon または親側の契約変更が unit の
`Related Change Surfaces` に関係する場合は、契約変更と該当 unit を同じ PR に含めます。
無関係な unit は更新しません。

## Parent Scope And Selection

監査対象は親 root の `git ls-files -z` が返す tracked path 集合です。submodule 内部の
tree は親の tracked tree に展開せず、親側の gitlink として扱います。`--scope` が
指定されなければ全 tracked path を使い、指定時は親 root 配下の tracked file または
directory に限定します。path escape、存在しない scope、親 Git 不在は typed failure
として返し、暗黙に別 root へ切り替えません。

`repository-structure` unit は `all-tracked` を所有し、全 tracked path に少なくとも
一つの owner view を与えます。他の unit は責務別 pattern を重ねてよく、重複は
primary owner と cross-reference を evidence に残します。uncovered path は audit
failure であり、pattern を勝手に広げずに該当 owner unit を更新します。

## Execution And Closure

親 root から AgentCanon source-root/path resolver を経由して次を実行します。

```bash
python3 tools/agent_tools/parent_repository_audit.py list --root <parent-root> --format text
python3 tools/agent_tools/parent_repository_audit.py check --root <parent-root> --format text
```

public skill は最初にこの README と list packet を読み、返された unit file を昇順で
一つずつ read します。各 unit は `pass`、または finding を owner skill/worker へ
routing して修正、対象 readback、close receipt まで完了してから次へ進みます。
finding が一つ出ても全監査を abort しません。repair が blocked の unit は
`repair_blocked` と blocker evidence を記録して未完了のまま次へ進み、最終 status は
blocked とします。source-root missing、invalid unit、path escape、uncovered tracked
path も packet に固定された failure code として扱います。

静的 structure/readback で invariant が確定できる unit は runtime build や全 suite を
実行しません。runtime validation は unit が静的に判定できない場合だけ、その unit が
指定する必要十分な command を使います。Docker image 間の差分 build はこの surface
の監査対象外です。

## Change And Publication Boundary

この source tree の canonical change は AgentCanon branch/PR で完了します。親 repository
側はこの surface、runtime view、pin、親固有 evidence を別の change surface として扱い、
source PR と親 PR の authority を混ぜません。audit skill は親を orchestrator として
writer delegation 契約に従い、worker は PR の作成、merge、close、admin override を行いません。
