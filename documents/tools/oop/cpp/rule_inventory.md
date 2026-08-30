# C++ OOP Rule Inventory
<!--
@dependency-start
contract reference
responsibility Documents C++ OOP rule inventory behavior in Japanese.
upstream implementation ../../../../tools/validation/code/oop/cpp/rule_inventory.py C++ OOP inventory checker
upstream design ../../../conventions/object-oriented-design.md OOP policy source
downstream design ../../tool-docs.toml one-to-one tool/document manifest
@dependency-end
-->

この文書は `tools/validation/code/oop/cpp/rule_inventory.py` と一対一で対応します。
同名の `rule_inventory.py` が tool、同名の `rule_inventory.md` が説明文書です。

## 何をチェックするか

C++ OOP の規約、tool、説明文書、test が現在の canonical path に揃っているかを確認します。
AgentCanon-owned shared docs は standalone AgentCanon source checkout の正本を確認します。

- `documents/conventions/object-oriented-design.md` が存在すること。
- `documents/conventions/coding-conventions-cpp.md` が存在すること。
- `tools/validation/code/oop/cpp/readability.py` が存在すること。
- `tools/validation/code/oop/cpp/rule_inventory.py` が存在すること。
- `documents/tools/oop/cpp/readability.md` が存在すること。
- `documents/tools/oop/cpp/rule_inventory.md` が存在すること。
- `.codex/agents/oop_readability_reviewer.toml` が存在すること。
- `tests/agent_tools/test_analyze_oop_readability.py` が存在すること。
- `tests/agent_tools/test_oop_rule_inventory.py` が存在すること。

## 実行例

```bash
python3 tools/validation/code/oop/cpp/rule_inventory.py
python3 tools/validation/code/oop/cpp/rule_inventory.py --format markdown
```

この inventory は旧 `tools/legacy/` 配置を前提にしません。C++ OOP checker の説明、規約、実装、test の配置ずれを機械的に検出します。
