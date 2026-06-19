# C And C++ Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents C and C++ static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/coding-conventions-cpp.md C++ coding conventions
upstream implementation ../../oop/cpp/readability.py scores C and C++ readability
@dependency-end
-->

C and C++ review uses the C++ OOP/readability entrypoint and
project-native build/test commands.

Default command:

```bash
python3 tools/oop/cpp/readability.py --format markdown include src tests/cpp
```

Native projects must add their configure, build, and test command evidence to
the run bundle; the readability score is a review aid, not build evidence.
