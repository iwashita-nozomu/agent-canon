<!--
@dependency-start
responsibility Defines Python structural duplicate analysis and module-group dependency semantics.
upstream design ../rust-agent-tool-migration.md Rust tool migration policy for native agent tools.
upstream design ../dependency-manifest-design.md repository dependency graph principles.
downstream implementation ../../rust/agent-canon/src/python_structure_hash.rs extracts dependency-expanded structural findings.
downstream implementation ../../rust/agent-canon/src/python_structure_hash_report.rs structures findings and computes module-group priority order.
downstream implementation ../../rust/agent-canon/src/python_structure_hash_impact.rs compares before/after structured reports.
@dependency-end
-->

# Python Structure Hash Analysis

This document is the canonical design for AgentCanon's Python structural
duplicate analysis.

## Purpose

`python-structure-hash` finds structurally duplicated Python functions,
classes, and type aliases using normalized AST shape. It also reports
single-caller structural helpers when an implementation function or class is
owned by exactly one enclosing caller block. It intentionally avoids name-only
matching. Names can appear in the report as evidence, but they are not the
primary duplicate or single-caller criterion.

The tool is intended to support refactoring order, not to automatically delete
code. Its output is mechanical evidence that an agent or reviewer can inspect.

## Analysis Population

The analyzer starts from the requested paths. If no path is given, the analysis
population is the repository root after default excludes.

For each Python file in the starting population, repo-local imports are resolved
and added to the analysis population. Reverse repo-local dependents are also
added so single-caller counts can see caller-side usage instead of only imported
dependencies. Expansion is transitive over this import neighborhood. External
libraries are recorded as advisory metadata only and are not rewrite targets.

Repo-local import resolution recognizes:

- direct repository paths,
- `python/` package roots,
- `src/` package roots,
- relative imports such as `from .x import Y` and `from ..base import Scalar`.

`__init__.py` is normalized to the package module, not a synthetic
`pkg.__init__` module, so package re-export surfaces participate in dependency
and caller analysis.

## Structural Identity

The structural hash uses:

- block role: `implementation`, `protocol`, or `alias`;
- block kind: `Function`, `Class`, or `Alias`;
- non-`self` / non-`cls` parameter count for functions;
- normalized AST payload with identifier, attribute, argument, and literal names
  removed.

Import facts, decorators, bases, module, and owner are kept as context. They do
not prevent duplicate grouping by default; instead they explain whether a group
is same-module, cross-module, same-import, mixed-import, same-base, or
mixed-base.

## Single-Caller Ownership

Single-caller analysis uses call/reference facts extracted from Python AST and
resolved in Rust against the analyzed symbol table. The count is based on unique
enclosing caller blocks, not raw call site count. A helper called twice from the
same function still has `caller_count=1` and `call_site_count=2`.

The structured report preserves both counts plus caller evidence:

- `caller_count`: number of unique owning caller blocks;
- `call_site_count`: number of call expressions inside that owner;
- `caller_analysis.callers[*].call_lines`: source lines where the target is
  called.

Single-caller findings are mechanical evidence for ownership review. They are
not automatic deletion instructions. Non-production single-caller findings are
review-blocked in `repair_slice`; production findings can be prioritized with
the same module/file dependency signals used for structural duplicates.

For each single-caller finding, the analyzer also computes deterministic
similar-responsibility caller evidence. This is not based on the target or
caller names alone. Candidate caller peers must be in the same module and have
the same block kind, then satisfy at least one stronger usage-shape rule:

- same normalized caller AST structure;
- at least two shared qualified call/reference profile entries;
- same non-module parent scope plus at least one shared qualified
  call/reference profile entry.

The call/reference profile keeps qualified names and `self.` / `cls.` receiver
shape instead of collapsing everything to the leaf method name. This prevents a
single unrelated shared leaf name from creating a merge suggestion.

The structured report converts these facts into
`caller_analysis.integration_candidates`. Candidate generation is feature based:
single-owner usage, AST block shape, target size, dependency-tree evidence, and
similar-caller shared profile evidence are emitted as weighted feature rows.
Class targets use `move_or_nest_single_owner_type` instead of a function-style
inline candidate. The raw `python-structure-hash --format json` output marks
candidate rows with `candidate_schema_scope=ast_use_graph_only`; it does not
have the full dependency graph. `python-structure-hash-report` marks rows with
`candidate_schema_scope=dependency_enriched` and adds dependency-tree features
from the structured report.

## Module Groups

Module-group definitions are parent-repository design state. AgentCanon owns the
policy and validation tool; the parent repository owns the concrete group list.

The default parent-repo contract path is:

```text
documents/design/python-module-groups.toml
```

Each `[[module_group]]` entry declares a stable group `id`, a human label, an
optional role description, and the Python submodules covered by that group:

```toml
[[module_group]]
id = "jax_util_base"
label = "jax_util Base"
role = "Core protocols, operators, logging, and scalar/vector type surface."
submodules = ["python/jax_util/base"]
```

The contract is intentionally small. A repository should use design-level groups
that humans and agents can reason about, usually on the order of tens of groups,
not a generated group for every file.

If the contract is missing, tools may fall back to parent-directory grouping for
exploratory output, but required checks must fail until the parent repo provides
the contract.

When the contract is present, paths outside all declared submodules are grouped
as `__unassigned__` in graph output. They do not create new design groups. This
keeps the graph aligned with the parent-owned design contract instead of letting
tests, generated files, vendored tools, or temporary Python files expand the
node set.

The fallback parent-directory grouping is only a bootstrap heuristic. Examples:

- `python/jax_util/base/linearoperator.py` belongs to
  `python/jax_util/base`;
- `python/jax_util/solvers/kkt.py` belongs to
  `python/jax_util/solvers`;
- a root-level Python file belongs to `.`.

Module groups are used for prioritization and dependency interpretation. They
are not a replacement for file-level findings.

## Contract Validation

`python-module-groups-check` validates that the parent-repo contract exists and
that the contract submodule list matches the production Python package
submodules discovered under `python/`.

The checker excludes tests, type stubs, egg-info directories, cache directories,
and other non-production surfaces. It reports:

- missing contract file;
- production Python submodules missing from the contract;
- contract submodules that no longer exist;
- duplicate submodule ownership.

The checker does not decide group semantics. If a group boundary is wrong, the
parent repo updates `documents/design/python-module-groups.toml`.

## Module-Group Dependency Graph

For every analyzed file, repo-local imports create directed edges:

```text
source module group -> imported target module group
```

Self-group edges are omitted. Edge counts are accumulated across all finding
instances. The structured report emits:

- group nodes with file count, incoming dependency count, and outgoing
  dependency count;
- group edges with source group, target group, and count.

Incoming dependency count is the primary mechanical signal for "deep" code:
groups imported by many other analyzed groups are refactored earlier because
changes there can simplify or unblock higher-level surfaces.

## Priority Order

The structured report emits a deterministic `priority_order`. The priority is
mechanical and uses this order of evidence:

1. module-group incoming dependency count;
2. file-level incoming dependency count;
3. fewer module-group outgoing dependencies;
4. single-caller ownership signal;
5. production surface membership;
6. implementation role before protocol and alias;
7. cross-module duplicate scope;
8. impact size from instance count and token count;
9. structural hash as the stable tie-breaker.

This means low-level repository code is preferred over high-level callers.
External libraries never increase refactor priority except as advisory context.

## Impact Diff

`python-structure-hash-impact` compares two structured
`python-structure-hash-report` JSON artifacts. Refactor loops should save a
before report before editing and an after report after the full scan reruns.

The impact diff reports:

- duplicate groups removed by the change;
- duplicate groups added by the change;
- priority rank or score changes for surviving groups;
- before and after `repair_slice` summaries.

This makes the effect of each refactor slice mechanical instead of relying on a
chat summary. The impact report is evidence for deciding whether the slice
removed the intended duplication, introduced new structural duplication, or
changed the next repair target.
