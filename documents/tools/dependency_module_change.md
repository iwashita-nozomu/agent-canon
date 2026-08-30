<!--
@dependency-start
contract reference
responsibility Documents the dependency policy adapter command.
upstream design ../rule/dependency-module-changes.md dependency identity, pin, and projection policy
upstream design ../rule/repository-topic-clone.md generic clone lifecycle
upstream implementation ../../tools/repository/workspace/dependency_module_change.py dependency adapter
downstream implementation ../../tests/agent_tools/test_dependency_module_change.py validates command behavior
@dependency-end
-->

# dependency_module_change.py

`tools/repository/workspace/dependency_module_change.py` は `.gitmodules` から dependency URL と
repository name を解決し、generic `repository_topic_clone.py` を呼ぶ policy adapter です。
clone implementation、path alias、fresh/continuation の別 route は持ちません。
public entry はこの direct executable だけです。同じ `agent_tools/` directory の
`repository_topic_clone.py` をlibrary ownerとして解決するため、standalone sourceと
derived `tools/agent-canon` viewのどちらでもpackage contextや`PYTHONPATH`を要求しません。

## Commands

```bash
python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> status \
  --topic <topic> [--module <module-path>]

python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> prepare \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> [--allowed-path <relative-path> ...]

python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> merge-main \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> [--allowed-path <relative-path> ...]

python3 tools/repository/workspace/dependency_module_change.py --root <parent-root> cleanup \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> [--allowed-path <relative-path> ...] \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

`prepare` と `merge-main` は owner evidence と module/computed identity が一致する
repo-local topic workspace に対して operation-level の追加承認なしで実行できます。reuse は
`prepare` に含まれます。`status` は dependency adapter の read-only command であり、
owner-evidence を要求せず、generic repository-topic lifecycle またはその approval carve-out
には含めません。exact local/remote branch を generic owner で再利用し、不在 branch を最新
`origin/main` から作成します。`merge-main` は通常 merge と ancestor proof を返します。
`cleanup` は manifest から計算した clone path を対象に、owner evidence/marker、URL、branch、
clean non-detached state、および fetch した `origin/<branch>` の commit/tree と local head/tree
の一致を検証します。publication packet を作らなくても実行でき、candidate CAS、PR lifecycle、
publication readback は任意の追加 evidence です。いずれかを指定する場合は candidate CAS と
PR lifecycle を一組で指定し、merged state では strict publication readback も検証します。
全 command は dependency 固有の module identity と generic receipt を出力し、specialized
mismatch 時も user-requested operation 自体は拒否しません。

`prepare`、`merge-main`、`cleanup` は write-capable generic lifecycle に対して
`allowed_paths` を明示的に渡します。`--allowed-path` を省略した canonical dependency
operation は dependency clone 全体を所有するため `.` を明示値として使い、狭い責務を
持つ caller はこの option を一つ以上指定してその範囲を forward します。adapter や generic
lifecycle 側で scope を暗黙補完しません。
