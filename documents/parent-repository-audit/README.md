# Parent Repository Audit
<!--
@dependency-start
contract design
responsibility Defines the canonical semantic-unit route for auditing an AgentCanon-consuming parent repository.
upstream design ../design/parent-repository-audit.md owns unit identity, selection, and failure semantics
upstream design ../rule/README.md owns document placement and filename rules
upstream design ../../responsibility-scope.toml owns AgentCanon path owner/class assignments
upstream implementation ../../tools/analysis/code/parent_repository_audit.py enumerates semantic units and records tracked evidence
upstream implementation ../../agents/skills/parent-repository-audit.md owns the public repair workflow
@dependency-end
-->

## Reader Map

この directory は、親 repository の監査を責務単位で進める正本です。最初に本 README で
選択と証拠の境界を固定し、次に `audit-unit/*.md` を path の昇順で読みます。各 unit は
owner responsibility、invariant、evidence、repair route、validation、close condition、
semantic change surface、legacy migration ID を自己完結して持ちます。

## Canonical Boundary

一般 path の owner/class は、監査 unit、構造 contract、runtime projection manifest ではなく、
対象 repository の `responsibility-scope.toml` だけが所有します。所有判定は tracked path
`p` ごとに owner scope がちょうど一つ存在することを要求します。glob が現在の tracked
path を一件も持たないことは、path の存在要求ではないため正常です。

責務は次のように分離します。

- `responsibility-scope.toml`: 実在する tracked path の owner/class の一意な対応。
- `repo-structure-contract.toml`: required/optional path の存在と filesystem kind。
- `audit-unit/*.md`: semantic change surface ごとの監査・修正・close 契約。

したがって audit unit は broad path glob、tracked-tree coverage、owner overlap を再判定しません。
選択された path は evidence であり、owner map でも unit selector でもありません。

## Unit Selection And Evidence

`parent_repository_audit.py` は unit file を POSIX lexicographic order で読み、
`Related Change Surfaces` にある `surface:<stable-id>` を semantic selector として使います。
`--surface` を省略すると全 unit、指定するとその surface を宣言する unit だけを選択します。
未知の surface は推測せず typed failure にします。

`--scope` は親 root 配下の tracked file/directory を evidence として絞るだけです。scope の
有無や path 名から unit、owner、class を決めません。AgentCanon source clone 内部は展開せず、親の tracked tree と明示された runtime/source clone
だけを tracked evidence とします。path escape、存在しない scope、親 Git 不在は fail closed
で返します。

```bash
python3 tools/analysis/code/parent_repository_audit.py list \
  --root <parent-root> --format text
python3 tools/analysis/code/parent_repository_audit.py list \
  --root <parent-root> --surface environment.containers --scope docker --format text
python3 tools/analysis/code/parent_repository_audit.py check \
  --root <parent-root> --unit-status pass --unit-status closed --format text
```

## Sequential Repair And Closure

public workflow は selected unit を一つずつ読み、次の遷移を完了してから次へ進みます。

```text
selected -> evidence read -> pass
                       \-> finding -> owner repair -> target readback -> closed
```

finding があっても全監査を途中で捨てません。repair が blocked または deferred の unit は
閉じず、owner、blocker、attempted repair、欠けている readback を残して次へ進みます。
failed/deferred が一件でもあれば全体を pass/closed に昇格させません。static evidence で
十分な unit に無関係な runtime build や全 suite を要求しません。

## Stable Failures

- `agent_canon_source_root_missing`: canonical source root を解決できない。
- `parent_repository_audit_unit_invalid`: required section、surface、legacy ID uniqueness が不正。
- `parent_repository_audit_path_escape`: unit または evidence scope が owner root 外へ出る。
- `parent_repository_audit_scope_missing`: 指定 evidence scope が tracked tree に存在しない。
- `parent_repository_audit_surface_unknown`: 指定 semantic surface が unit 集合に存在しない。
- `parent_repository_audit_parent_git_missing`: 親 root が Git tracked evidence を提供できない。
- `parent_repository_audit_unit_status_failed`: failed/deferred receipt が残る。

## Change And Publication Boundary

AgentCanon 共通契約の変更は AgentCanon branch/PR、親固有 tree・finding・修正・pin は親側
branch/PR が所有します。generated report、inventory、summary、run bundle は evidence または
projection であり、unit や path owner map の代わりに判定しません。契約変更時は、その
`surface:<stable-id>` を所有する unit だけを同じ PR で更新します。
