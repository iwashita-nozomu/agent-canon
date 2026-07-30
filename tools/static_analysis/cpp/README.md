# C And C++ Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents C and C++ static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/conventions/coding-conventions-cpp.md C++ coding conventions
upstream implementation ../../oop/cpp/readability.py scores C and C++ readability
@dependency-end
-->

C and C++ review uses the C++ OOP/readability entrypoint and
project-native build/test commands.

Default command:

```bash
python3 tools/oop/cpp/readability.py --format markdown cpp/include cpp/src cpp/tests cpp/experiments
```

Native projects use `cpp/CMakeLists.txt` as the source anchor and add configure,
build, CTest, install, and consumer-to-provider target evidence to the run
bundle. The readability score is a review aid, not build evidence.
