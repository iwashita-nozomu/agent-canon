# Python Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents Python static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/coding-conventions-python.md Python coding conventions
upstream implementation ../../agent_tools/check_static_any.py rejects explicit Any usage
upstream implementation ../../agent_tools/check_log_helper_names.py checks log helper names
upstream implementation ../../oop/python/readability.py scores Python OOP readability
@dependency-end
-->

Python review uses existing canonical tools rather than parallel wrappers.

Default commands:

```bash
python3 tools/agent_tools/check_static_any.py --submodule-aware
python3 tools/agent_tools/check_log_helper_names.py --changed
python3 tools/oop/python/readability.py --format markdown python tools tests
```

For template roots with `vendor/agent-canon` as a submodule, prefer
`--submodule-aware` where available. Use `--root-only` when checking only the
template product surface and `--agentcanon-only` when checking the shared canon
source.
