# C And C++ Static Analysis
<!--
@dependency-start
responsibility Documents C and C++ static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/coding-conventions-cpp.md C++ coding conventions
upstream implementation ../../agent_tools/analyze_oop_readability.py scores C and C++ readability
@dependency-end
-->

C and C++ review currently uses the cross-language OOP/readability analyzer and
project-native build/test commands.

Default command:

```bash
python3 tools/agent_tools/analyze_oop_readability.py --format markdown include src tests/cpp
```

Native projects must add their configure, build, and test command evidence to
the run bundle; the readability score is a review aid, not build evidence.
