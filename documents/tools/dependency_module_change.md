<!--
@dependency-start
contract reference
responsibility Documents the dependency policy adapter command.
upstream design ../rule/dependency-module-changes.md dependency identity, pin, and projection policy
upstream design ../rule/repository-topic-clone.md generic checkout lifecycle
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_module_change.rs dependency adapter
downstream implementation ../../tests/agent_tools/test_dependency_module_change.py validates command behavior
@dependency-end
-->

# dependency-module-change

`tools/bin/agent-canon dependency-module-change` は `.gitmodules` から dependency URL と
repository name を解決し、generic `repository-topic-clone` native owner を呼ぶ policy adapter です。
checkout implementation、path alias、fresh/continuation の別 route は持ちません。
public entry は AgentCanon native CLI です。

## Commands

```bash
tools/bin/agent-canon dependency-module-change --root <parent-root> status \
  --topic <topic> [--module <module-path>]

tools/bin/agent-canon dependency-module-change --root <parent-root> prepare \
  --topic <topic> --module <module-path> --branch <branch>

tools/bin/agent-canon dependency-module-change --root <parent-root> merge-main \
  --topic <topic> --module <module-path> --branch <branch>

tools/bin/agent-canon dependency-module-change --root <parent-root> cleanup \
  --topic <topic> --module <module-path> --branch <branch> \
  [--candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>]] [--apply]
```

`prepare` と `merge-main` は module/computed identity が一致する
repo-local topic workspace に対して operation-level の追加承認なしで実行できます。reuse は
`prepare` に含まれます。`status` は dependency adapter の read-only command であり、
generic repository-topic lifecycle またはその approval carve-out には含めません。exact local/remote
branch を generic owner で再利用し、不在 branch を最新
`origin/main` から作成します。`merge-main` は通常 merge と ancestor proof を返します。
`cleanup` は manifest から計算した checkout path を対象に、marker、URL、branch、
clean non-detached state、および fetch した `origin/<branch>` の commit/tree と local head/tree
の一致を検証します。publication packet を作らなくても実行でき、candidate CAS、PR lifecycle、
publication readback は任意の追加 evidence です。いずれかを指定する場合は candidate CAS と
PR lifecycle を一組で指定し、merged state では strict publication readback も検証します。
全 command は dependency 固有の module identity と generic receipt を出力し、specialized
mismatch 時も user-requested operation 自体は拒否しません。

`prepare`、`merge-main`、`cleanup` は manifest から計算した exact checkout path と current Git
identity を確認します。caller は conversation 上で task scope を確認し、Git diff を読み戻して
担当範囲からの逸脱がないことを確認します。
