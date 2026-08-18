<!--
@dependency-start
contract template
responsibility Owns materializable code and Docstring examples for derived repositories.
upstream design ../../documents/rule/README.md filename, placement, and Japanese human-facing language rules.
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract.
upstream design ../README.md centralized template index and canonical source boundary.
downstream implementation ./python/docstring_template.py parse-valid module/class/function example.
downstream implementation ../../tools/agent_tools/code_template_rendering.py code-template renderer/readback route.
@dependency-end
-->

# Code Templates

この directory は、派生 repo が materialize して利用する code template の唯一の source owner です。
field name、command、code identifier は機械的な安定性のため英語を保ちますが、人が読む説明と
Docstring の意味契約は日本語で記述します。

## Reader Map

- purpose: 責務境界、状態 invariant、型、Docstring、side effect、所有権を実装へ移す。
- intended reader and decision: 実装者と reviewer が、どの template をどこへ materialize するか決める。
- what this directory contains: `python/docstring_template.py` と、その source/renderer/readback 契約。
- canonical source: `templates/code/`。
- generated or local surface: 派生 repo の `python/` または指定された source directory。
- owner and responsibility boundary: code template は例示の型・Docstring・局所 invariant を所有し、
  project-specific domain logic、依存、resource allocation、artifact retention は所有しない。
- validation/readback: source copy、Python parse、D213、renderer output、生成先の byte/readback identity。
- lifecycle: materialize 後は派生 repo owner が domain adaptation、review、cleanup を管理する。

## Source Index

| source | responsibility | materialization / renderer route |
| --- | --- | --- |
| `python/docstring_template.py` | module/class/function Docstring と具体的な state/type boundary の例 | `render_code_template("python/docstring_template.py")` または source copy |

## Materialization Contract

1. source を変更せず、派生 repo の責務に合わせた新しい destination へ copy する。
1. `python -m py_compile` と D213 checker を copy 前後で実行する。
1. owner、invariant/state、Args の units/shapes、Returns、Raises、side effects、ownership を
   domain-specific な値へ置換し、例示のまま成功扱いにしない。
1. renderer を使った場合は rendered source と destination の path/sha256 を read back する。

```bash
PYTHONPATH=tools python3 - <<'PY'
from pathlib import Path

from agent_tools.code_template_rendering import render_code_template

source = render_code_template("python/docstring_template.py")
Path("python/docstring_template.py").write_text(source, encoding="utf-8")
PY
```

この例の write は destination owner の明示的な materialization route です。template source の
複製を別の canonical owner として追加せず、派生 repo 側でのみ編集します。

## Adaptation Boundary

- `ExampleState` は immutable state と非空値 invariant の具体例です。
- `build_example_state()` は units/shapes を受け取り、型境界を越えた値を検証します。
- domain algorithm、network/file/device side effect、並列 resource、test oracle は利用 repo が所有します。
- 新しい責務、reader、validation route、update cadence が発生した場合だけ別 template owner を設計します。
