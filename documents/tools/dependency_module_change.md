<!--
@dependency-start
contract reference
responsibility Documents the dependency policy adapter command.
upstream design ../rule/dependency-module-changes.md dependency identity, pin, and projection policy
upstream design ../rule/repository-topic-clone.md generic clone lifecycle
upstream implementation ../../tools/agent_tools/dependency_module_change.py dependency adapter
downstream implementation ../../tests/agent_tools/test_dependency_module_change.py validates command behavior
@dependency-end
-->

# dependency_module_change.py

`tools/agent_tools/dependency_module_change.py` は `.gitmodules` から dependency URL と
repository name を解決し、generic `repository_topic_clone.py` を呼ぶ policy adapter です。
clone implementation、path alias、fresh/continuation の別 route は持ちません。
public entry はこの direct executable だけです。同じ `agent_tools/` directory の
`repository_topic_clone.py` をlibrary ownerとして解決するため、standalone sourceと
derived `tools/agent-canon` viewのどちらでもpackage contextや`PYTHONPATH`を要求しません。

## Commands

```bash
python3 tools/agent_tools/dependency_module_change.py --root <parent-root> status \
  --topic <topic> [--module <module-path>]

python3 tools/agent_tools/dependency_module_change.py --root <parent-root> prepare \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file>

python3 tools/agent_tools/dependency_module_change.py --root <parent-root> merge-main \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file>

python3 tools/agent_tools/dependency_module_change.py --root <parent-root> cleanup \
  --topic <topic> --module <module-path> --branch <branch> \
  --owner-evidence <file> --expected-clone <absolute-clone> \
  --candidate-cas <candidate-cas.json> --pr-lifecycle <pr-lifecycle.json> \
  [--publication-readback <publication-readback.json>] [--apply]
```

`prepare` は exact local/remote branch を generic owner で再利用し、不在 branch を最新
`origin/main` から作成します。`merge-main` は通常 merge と ancestor proof を返します。
`cleanup` は canonical PR-head または merged-publication transition が成立した場合だけ
computed clone を対象にします。全 command は dependency 固有の module identity と generic
receipt を出力し、specialized mismatch 時も user-requested operation 自体は拒否しません。
