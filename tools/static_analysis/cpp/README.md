# C And C++ Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents C and C++ static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/conventions/coding-conventions-cpp.md C++ coding conventions
upstream design ../../../documents/design/cpp-build-layout.md canonical native project surface
upstream implementation ../../oop/cpp/readability.py scores C and C++ readability
@dependency-end
-->

C and C++ review uses the C++ OOP/readability entrypoint and
project-native build/test commands.

Default command:

```bash
python3 tools/oop/cpp/readability.py --format markdown include src tests/cpp experiments/cpp
```

Omit optional paths that do not exist. Do not add the legacy `cpp/` tree as a
fallback. Native projects use root `CMakeLists.txt` as the source anchor and add
configure, build, CTest, install, and consumer-to-provider target evidence to
the run bundle. The readability score is a review aid, not build evidence.
