<!--
@dependency-start
contract reference
responsibility Owns the complete Python-to-Rust migration scope and preservation contract for AgentCanon tools.
upstream design README.md AgentCanon documentation index
upstream design ../../CONTAINER_OPERATIONS.md consumer and shared-runtime ownership
upstream design ../../tools/catalog.yaml public commands and external provider identities
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs native command registration
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/migration_audit.rs shared source foundation checks
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/rust_migration_plan.rs discovered implementation inventory and family ordering
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/file_surface_inventory.rs native file-surface inventory owner
downstream implementation ../../tools/bin/agent-canon stable native entrypoint
@dependency-end
-->

# Rust Agent Tool Migration

## Scope and Intent

Migrate every AgentCanon-owned Python tool implementation to Rust, including
workflow orchestration, runtime lifecycle, Eval producers and checkers, and
active hooks. This replaces the earlier policy that kept frequently changing
workflow tools in Python. Stability and usage may inform implementation work;
they do not exempt an owned tool from migration.

Preserve the tool's external CLI/API, schema, exit behavior, filesystem effects,
mount and credential boundaries, and consumer functionality. Prioritize memory
safety and reuse existing native owners. Moving Python logic into Rust string
payloads, calling the old Python implementation from a Rust wrapper, or moving
that implementation into a consumer repository does not complete a port.

This document owns scope, ordering, and completion evidence. The plan and audit
are migration foundations; delivering them does not complete the actual ports.

## Inventory Boundaries

Discover source under `tools`, `eval`, and `.codex/hooks`. Inventory `tests` and
`templates` separately so file-extension totals cannot be mistaken for remaining
tool implementations. Ignore build/cache directories and do not follow source
symlinks. The plan inventories the current filesystem, including new source
files; it does not claim a Git snapshot or a complete Python import graph.

| Classification | Migration treatment |
| --- | --- |
| Owned Python implementation | Migrate, including uncatalogued helpers and active hooks |
| Package marker | Empty/comment/docstring-only `__init__.py`; an executable initializer remains an implementation |
| Test | Preserve behavior oracles; tests are not production tool ports |
| Template or fixture | Preserve consumer/example semantics; do not count as an AgentCanon implementation |
| Third-party source | Keep provider ownership distinct from AgentCanon orchestration |
| Source view | Record separately; do not count a symlink as another implementation |
| Native source, unverified | Native source presence alone establishes neither behavior preservation nor Python independence |
| External runtime | Preserve provider contracts; the AgentCanon adapter remains in migration scope |

Join discovered paths with `tools/catalog.yaml` IDs, including Rust command
selectors. Report owned implementations without a catalog row. Multiple command
IDs may refer to one source module; catalog rows are not module counts. Paths,
not basenames, distinguish owners such as the several `readability.py` files.

The planner also reports known Python delegation at these native owners when
the corresponding source evidence is present:

- `private_feedback.rs`: private feedback storage and sync Python adapter.
- `dependency_manifest.rs`: Python surface-manifest snapshot producer.
- `python_structure_hash.rs` and `python_algorithm_contract.rs`: embedded Python
  AST extraction implementations.

This is a declared set of known gaps, not an exhaustive detector for arbitrary
Python execution. An absent known marker does not establish completion. The
plan always leaves overall completion unverified; a port needs the evidence
below.

## Runtime and External Providers

The stable entrypoint is `tools/bin/agent-canon`; native source belongs under
`tools/runtime/dispatch/agent-canon/src`. Use the selected shared build and
release route. Consumer project images, runtime dependencies, and credentials
remain consumer-owned.

Host bootstrap starts in `bootstrap.sh` and delegates to
`bootstrap/host/lifecycle/entrypoint.sh`. The resident container receives its
numeric caller identity through the host adapter's `--user` argument. A
Dockerfile `USER agentcanon` declaration or host Python bootstrap entrypoint is
not the current ownership contract. The audit checks source foundation markers,
not actual container admission or runtime identity.

Retain consumer Python functions, JAX execution, and explicitly contracted
external Python producer interfaces. Keep basic CLI paths independent of Python.
External runtime connections do not exempt AgentCanon-owned logic from migration;
the default surface-manifest producer must become native while explicit external
producer identity, root/foreign restrictions, and stale guards are preserved.
No substantial Python implementation belongs in Rust or bootstrap strings.

Preserve these existing provider capabilities:

- Managed experiment orchestration already exchanges typed request/result
  files with the pinned `experiment-runner-admitted` provider declared in
  `agent-canon-environment.toml`. Port admission, fingerprints, receipts,
  lifecycle checks, and artifacts while preserving that provider and consumer
  `experiments/<topic>/run.py` execution.
- JIT extraction accepts `path.py::qualname` and an input factory, dynamically
  calls Equinox/JAX lowering and shape/tree APIs, and produces StableHLO,
  public-interface, and backend evidence. The native `jit_ir_to_lean.rs` owner
  consumes downstream JSON; it does not replace this lowering contract.
  Select a reviewed safe native connection to the external CPython/JAX runtime.
  Requiring only pre-exported StableHLO would remove existing functionality.
- Preserve configured LSP servers while migrating `pylsp_jsonrpc` transport
  responsibilities. PDF extraction currently supports both `pypdf` and
  `pdftotext`; removing the pypdf-only case needs an explicit replacement
  dependency decision.

Native parser, Python runtime binding, and filesystem capability dependencies
require their own investigated design and validation. Do not weaken
Python-AST semantics or descriptor-relative writes, inode/device identity,
no-follow handling, locks, and authenticated handoffs to avoid that work.
`runtime_boundary.rs` provides useful external-artifact checks but does not yet
replace all guarantees of `parent_root_side_effects.py` and
`runtime_artifacts.py`.

## Dependency Order

The planner applies these responsibility prerequisites to the discovered
remaining owners. This is an explicit family policy, not a claim that source
imports have been fully analyzed. Resolve the selected module's actual imports,
callers, and test contracts before implementation. Keep shared CLI/catalog
registration under one integration owner while implementation modules have
disjoint write sets.

| Order | Family | Required earlier families |
| --- | --- | --- |
| 0 | Independent file-surface inventory | None |
| 10 | Catalog, surface manifests, projection identities, tool-path policy | None |
| 20 | Artifact/root capabilities, authority, source identity, shared values and support | None |
| 30 | Source/dependency/search/document analysis | Catalog foundation |
| 30 | AST inventory, readability, embedded AST extractors | Authority foundation; native parser contract |
| 40 | Container and tool dispatch, execution runners | Catalog and authority foundations |
| 50 | Archive, audit logging, private feedback, lifecycle | Authority foundation and runtime execution |
| 60 | Agent workflow, packets, teams, manifest rendering, skills and templates | Catalog and authority foundations, archive/lifecycle |
| 60 | Repository checkout, Git and publication operations | Authority foundation and archive/lifecycle |
| 60 | Experiments, HLO, numerical and proof tooling | Authority foundation and runtime execution |
| 70 | Remaining validation, Eval and hook dispatch | Agent workflow, source analysis, AST analysis, archive/lifecycle |

The family order does not authorize mutation, publication, a new dependency, or
execution of consumer code. A remaining prerequisite produces `dependency-first`;
a selected native parser/provider/capability design produces `contract-first`.
Other candidates are `port-now`, subject to their existing authority and
behavior contracts. No `keep-python` class remains.

## Native File-Surface Port and Caller Closure

File-surface inventory is implemented by
`agent-canon file-surface-inventory`; its former Python implementation is
retired. The CLI and catalog route select the Rust owner. The command retains
default `root-only`, mutually exclusive `--root-only`/`--agentcanon-only`,
explicit `--json-out` and `--markdown-out`, and `--max-markdown-entries`.
The full owned-tool migration remains open; this port does not establish
completion of other implementations or native Python delegations.

Inventory indexed and untracked nonignored Git paths, preserving gitlinks,
executable and symlink modes, deleted-index exclusion, dangling symlink
presence, path exclusions, classifications, and deterministic sorting. Retain
the JSON fields, Markdown structure, machine-readable stdout markers, and
success/inventory-failure/argument-error exits 0/1/2. Markdown truncation must
not truncate JSON. Reports remain explicit; stdout-only inspection creates no
report or implicit cache.

The callers use the native command: `review_backlog_scan.sh`, the retained
`file-surface-inventory` catalog ID, `agents/COMMUNICATION_PROTOCOL.md`, and the
direct CLI and backlog-scan fixture tests. The protocol example uses the
existing `--root-only` mode; its unsupported `--submodule-aware` flag has been
removed.

The catalog's current fixed `ToolSpec` cannot express optional report-output
capabilities: changing `writes` to true requires an output root even for
stdout-only use, and `explicit-target-write` asks for source-target authority.
Keep stdout-only admission free of report or source-write requirements.
Argument-sensitive artifact admission belongs to the dispatcher Rust port; a
report destination is not a source mutation capability. The native command
retains explicit report destinations. This pre-existing catalog limitation is
not proof that report-producing calls are read-only.

Document-canon inventory is already implemented by native
`structured-analysis document-inventory`. Its generic responsibility findings
remain derived from dependency declarations and upstream coverage rules.
Preserve this owner rather than restoring a Python compatibility implementation.
Other commands in the same crate may still have the delegation gaps above.

## Plan and Audit Interfaces

```bash
agent-canon rust-migration-audit --root <agent-canon-source>
agent-canon rust-migration-plan --root <agent-canon-source> --limit 12
agent-canon rust-migration-plan --root <agent-canon-source> --format json
```

The audit and planner share source foundation checks for the native crate,
entrypoint, wrapper, shell bootstrap, image, and lifecycle. They do not require
retired files or permanent Python implementation paths. The audit also retains
the source check against agent-tool Cargo/rustup provisioning in the consumer
`docker/Dockerfile`.

The read-only plan reports classifications, catalog coverage, known native
Python delegations, declared external providers, and dependency-ordered
candidates. JSON schema `agent-canon.rust-migration-plan.v2` includes the full
inventory; `--limit` bounds only candidate presentation. Missing scan roots,
missing catalog source paths, unreadable source, and invalid registry inputs
are reported rather than silently counted as empty success. Foundation status
is reported separately from inventory status and overall migration completion.

Candidate ordering no longer derives from basename matches in feedback logs.
The old planner read only a legacy log directory despite prose claiming mounted
archive coverage. This planner uses observed source and registry evidence and
does not claim to inspect those logs.

## Local Structural Integration Check

The native `agent-canon check-merge-structure` command replaces
`tools/validation/ci/checks/check_merge_structure.py` for local integration
readback. It retains the source, target, compare-commit, and repository-root
arguments and compares each source-side structural path by its complete Git
tree entry: mode, object type, and object ID. This is local integration evidence;
it does not select or require a GitHub pull-request merge method. The integration
Skill, branch-scope procedure, worktree lifecycle, and implementation-routing
example use the native command.

## Port Acceptance and Validation

A port is ready only after the native implementation preserves the selected
CLI/API, schemas, output and exit semantics, side effects, root capabilities,
and consumer/provider contracts. Retire the old own-Python implementation and
update the complete known caller closure. A native wrapper, catalog row,
successful compile, or smaller Python-file count is insufficient evidence.

Preserve existing behavior oracles. Compare old/new behavior on the same
fixtures, including failure and authority-boundary cases, before retiring the
old implementation. Add focused cases for changed guarantees without weakening
assertions. Use the shared runtime for selected Rust formatting, clippy,
tests/build, catalog and caller checks, and the existing five-host release
matrix where native distribution guarantees change. The integration owner
selects and records those runs; source-only planning is not validation.
