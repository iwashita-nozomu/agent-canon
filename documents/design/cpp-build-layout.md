<!--
@dependency-start
contract design
responsibility Defines the derived-repository C++ source, build, test, and native-experiment ownership boundary.
upstream design ../runtime/runtime-profiles-and-check-matrix.md C++ profile and validation routing
upstream design ../conventions/coding-conventions-cpp.md native source and header conventions
upstream design ../conventions/coding-conventions-project.md project path and environment conventions
upstream design ../conventions/coding-conventions-testing.md CTest and test ownership conventions
upstream design ../conventions/coding-conventions-experiments.md experiment source and artifact conventions
upstream design ../structure/repo-structure-contract.toml positive path and ownership contract
upstream design ../../agents/skills/cpp-review.md native build, header, and CTest review
upstream design ../../agents/skills/refactor-loop.md behavior-preserving path migration contract
downstream implementation ../../tools/agent_tools/manifest_rendering.py projects C++ review candidates from changed paths
downstream implementation ../../tests/agent_tools/test_agent_team_templates.py validates the canonical path markers
@dependency-end
-->

# C++ Build Layout

## Purpose

Derived repositories own their C++ project directly at the repository root. The
canonical production surface is:

- public headers: `include/`;
- production implementation: `src/`;
- CMake project entrypoint and helpers: `CMakeLists.txt` and `cmake/`;
- product adapter and integration tests: `tests/cpp/`;
- optional native experiment target sources: `experiments/cpp/`.

The legacy `cpp/` project directory is not a compatibility surface. A derived
repository must not retain `cpp/CMakeLists.txt`, `cpp/include/`, `cpp/src/`, or a
forwarding wrapper after migration.

This is an ownership and path contract. It does not change numerical behavior,
public API semantics, dependency versions, experiment protocols, or the owner of
mathematical oracle tests.

## Engineering basis

CMake resolves source-relative include, package, install, and subdirectory paths
from its source directory. Making the repository root the single source directory
keeps the public paths (`include/`, `src/`, `cmake/`) identical in the source tree,
IDE configuration, package installation, and CI. A second `cpp/` anchor would add
one artificial prefix and create two plausible project roots.

Tests and experiments are consumers of production targets, not production source.
Their directories therefore follow their lifecycle owners:

- `tests/cpp/` is owned by the derived product test tree;
- `experiments/cpp/` is owned by the experiment tree and only contains native
  target source/wiring;
- managed run configuration, execution evidence, reports, and retention remain
  under `experiments/<topic>/`;
- numerical, mathematical, and neural-network oracle tests remain in the owning
  C++ provider repository (for example cppdev), not in the derived product tree;
- AgentCanon runtime and template tests remain in AgentCanon.

This dependency direction is acyclic: product test/experiment target → production
target. Production targets do not depend on test or experiment state.

## Target state

| Responsibility | Canonical owner/path | Required readback |
| --- | --- | --- |
| CMake source root | `CMakeLists.txt` | exactly one project entry at repository root |
| CMake helpers and package config | `cmake/` | helper paths are rooted at `${CMAKE_SOURCE_DIR}/cmake` or target-local equivalents |
| public API | `include/<project>/...` | build and install interfaces expose `include/` without a `cpp/` prefix |
| production implementation | `src/` | production translation units belong only to production targets |
| product CTest source | `tests/cpp/` | test targets consume production targets and are registered with CTest |
| optional native experiment source | `experiments/cpp/` | experiment targets consume production targets; build does not execute or publish a run |
| build tree | `build/cpp/<profile>/` | configure, build, CTest, and install use the same cache |
| install tree | `dist/cpp/<profile>/` | installed headers and package metadata contain no legacy source path |

Empty production directories may be represented by an owner README or omitted
until the project has that source kind. The build must not require a placeholder
translation unit or compatibility directory.

## Canonical commands

All commands are anchored at the repository root:

```bash
ROOT="$(git rev-parse --show-toplevel)"
cmake -S "$ROOT" -B "$ROOT/build/cpp/<profile>" \
  -DCMAKE_INSTALL_PREFIX="$ROOT/dist/cpp/<profile>"
cmake --build "$ROOT/build/cpp/<profile>" --target cpp-core
cmake --build "$ROOT/build/cpp/<profile>" --target cpp-tests
ctest --test-dir "$ROOT/build/cpp/<profile>" --output-on-failure
cmake --install "$ROOT/build/cpp/<profile>"
```

`cpp-tests` and `cpp-experiments` are aggregate build targets when their consumers
exist. They do not own execution, results, or production state.

## CMake graph contract

The root `CMakeLists.txt` owns one configure graph.

1. Define the production target and its public build/install include interfaces.
2. Add production translation units from `src/` only when the project owns them.
3. When `tests/cpp/CMakeLists.txt` exists, connect it with an explicit binary
   directory, for example:

   ```cmake
   add_subdirectory(
     "${CMAKE_SOURCE_DIR}/tests/cpp"
     "${CMAKE_BINARY_DIR}/tests/cpp"
   )
   ```

4. When `experiments/cpp/CMakeLists.txt` exists, connect it with a distinct explicit
   binary directory. Native experiment targets may build executables but must not
   execute them during configure or build.
5. Test and experiment targets link to the production target. The reverse edge is
   forbidden.
6. Package config templates and install rules are read from `cmake/` and install
   public headers from `include/`.

No root wrapper may forward to `cpp/CMakeLists.txt`, and no CMake fallback may
silently select legacy paths.

## Migration map

| Legacy path/command | Canonical replacement |
| --- | --- |
| `cpp/CMakeLists.txt` | `CMakeLists.txt` |
| `cpp/cmake/` | `cmake/` |
| `cpp/include/` | `include/` |
| `cpp/src/` | `src/` |
| `cpp/tests/` | `tests/cpp/` |
| `cpp/experiments/` | `experiments/cpp/` |
| `cmake -S "$ROOT/cpp" ...` | `cmake -S "$ROOT" ...` |

Migration is a move, not an alias period. Update all direct consumers in the same
change, then delete the legacy tree. A parent repository with behavior-sensitive
adapters validates the same target graph and test oracle before and after the move.

## Validation oracle

A layout migration is complete when all of the following hold:

- the root CMake configure succeeds using `-S "$ROOT"`;
- production, product-test, and optional native-experiment targets form the
  consumer-to-provider graph above;
- CTest discovers and runs `tests/cpp/` targets from the same build cache;
- install readback exposes the intended public headers and package metadata;
- repository structure and responsibility checks accept the root surface;
- changed-path routing selects C++ review for `CMakeLists.txt`, `cmake/`, `include/`,
  `src/`, `tests/cpp/`, and `experiments/cpp/`;
- no tracked path or command requires `cpp/CMakeLists.txt`, `cpp/include/`,
  `cpp/src/`, `cpp/tests/`, or `cpp/experiments/`.

Environment-specific build or dependency checks that cannot run are reported as
remaining verification; they are not replaced by a compatibility path or a
successful documentation-only check.
