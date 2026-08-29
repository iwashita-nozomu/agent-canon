# C And C++ Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents C and C++ static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/conventions/coding-conventions-cpp.md C++ coding conventions
upstream implementation ../../oop/cpp/readability.py scores C and C++ readability
upstream implementation ./static_analysis.py owns compile-database selection and native checks
downstream implementation ../../../tests/tools/test_cpp_static_analysis.py focused CLI and policy tests
@dependency-end
-->

C and C++ review uses the generated CMake compilation database. CMake owns
each independent module build directory; this tool owns only the explicit
profile-level active view consumed by editors and analyzers. It never adds
include paths, compiler flags, or provider-specific diagnostics.

Select one module database for the shared editor view:

```bash
python3 tools/validation/code/static/cpp/static_analysis.py \
  select-db --workspace-root <workspace-root> --build-dir <module-build-dir>
```

The default active view is `build/cpp/dev/compile_commands.json`; pass
`--output build/cpp/<profile>/compile_commands.json` when selecting another
profile. The selected path is a symlink to the CMake-generated database, so
there is exactly one active database and no merged or hand-written flags.

Run the checks against a source and explicit build directory (or pass
`--compile-database`):

```bash
python3 tools/validation/code/static/cpp/static_analysis.py \
  clangd-check --workspace-root <workspace-root> --source <source> \
  --build-dir <module-build-dir>
python3 tools/validation/code/static/cpp/static_analysis.py \
  clang-tidy --workspace-root <workspace-root> --source <source> \
  --build-dir <module-build-dir> --config-file <clang-tidy-config>
```

When `--config-file` is omitted, an existing
`<workspace-root>/clang/clang-tidy.yaml` is selected automatically. An explicit
configuration path always takes precedence; repositories without that
conventional file keep the native clang-tidy defaults.

Both commands preserve generated compiler/include/plugin flags and native tool
stdout, stderr, and exit status. Missing source, build directory, database,
explicitly requested configuration, or executable fails with a typed diagnostic
before invocation.
The existing readability aid remains available separately:

```bash
python3 tools/validation/code/oop/cpp/readability.py --format markdown cpp/include cpp/src tests/cpp cpp/experiments
```
