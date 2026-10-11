<!--
@dependency-start
contract reference
responsibility Documents the native SCIP index and bounded query API.
upstream design ../../agents/skills/dependency-analysis.md selects optional repository-wide symbol/reference evidence.
upstream implementation ../../tools/analysis/dependencies/scip_index.py owns native index/read/query operations.
upstream implementation ../../tools/runtime/artifacts/runtime_artifacts.py confines index outputs to the external runtime.
downstream implementation ../../tests/agent_tools/test_scip_index.py verifies output and query behavior.
@dependency-end
-->

# scip_index.py

Use this tool only when repository-wide symbol or reference evidence can change
the edit scope. It writes the standard SCIP protobuf artifact and projects a
bounded set of definitions, references, and explicit implementation
relationships from that artifact.

The SCIP index remains the canonical source. Query output contains selected
root-relative paths, ranges, symbols, roles, and references to the source index.
It does not create a persistent JSON or database copy of the full index.
References are not call edges. The current query reports callers and callees
as `not-represented` rather than inferring them from references.

## Build a native index

Every index write requires an explicit external runtime root and an output path
beneath that root. The output file is named index.scip. The selected project
owner supplies the language inputs:

    python3 tools/analysis/dependencies/scip_index.py index \
      --root <project-root> \
      --runtime-root <external-runtime-root> \
      --language python \
      --project-name <project-name> \
      --project-version <project-version> \
      --python-environment <project-owned-environment.json> \
      --output scip/<run-id>/python/index.scip

Python indexing uses scip-python 0.6.6. Its environment file comes from the
project environment owner; this command does not probe or install a host Python
environment. Missing required inputs are reported as `input-required`, not as
an unsupported-language result.

For C and C++, select the project build owner's compile database:

    python3 tools/analysis/dependencies/scip_index.py index \
      --root <project-root> \
      --runtime-root <external-runtime-root> \
      --language cpp \
      --compile-database build/<profile>/compile_commands.json \
      --output scip/<run-id>/cpp/index.scip

The current scip-clang v0.4.0 release provides an x86_64 Linux binary. The
indexer consumes the supplied JSON compilation database; this API does not
reconstruct compiler flags or build inputs.

The generic scip 0.10.0 CLI reads and validates index artifacts. The index
command uses its stats output; query uses print --json. These are native SCIP
readbacks, not an AgentCanon graph schema.

Rust currently has no selected producer. The SCIP subcommand in the pinned
rust-analyzer is unstable and has not been qualified here; a Rust index request
is reported as unsupported rather than treated as missing Rust references.

## Query a bounded impact

Pass an index path from the same external runtime root. Paths can name a file or
a directory; symbol queries use the exact SCIP symbol string.
Repeat --index once per selected language/module artifact.

    python3 tools/analysis/dependencies/scip_index.py query \
      --root <project-root> \
      --runtime-root <external-runtime-root> \
      --index scip/<run-id>/python/index.scip \
      --path src/package/api.py

The default result limit is 200 entries per projected list. Directory targets, including
the repository root, are marked partial because query output does not prove
that every source file or supported language appears in the selected indexes.
The output records index paths and hashes, separates definitions, references,
and indexer-declared
implementations, and marks an unindexed target as a coverage gap. An empty
result for an unindexed path is not evidence that the path has no references.
The artifact hash identifies the selected index, not the current source bytes;
SCIP metadata has no source-content digest, so query output marks source
freshness as unverified. Omitted symbols and call edges are not proven absent.

Shell has no selected native SCIP producer. Requesting a shell index returns an
unsupported capability, and querying a path absent from selected indexes marks
that target unindexed. Neither result is complete shell coverage.

SCIP indexing is not a default gate for small documentation/configuration
changes, direct point-LSP queries, or tasks whose owner is already known.
Point LSP analysis and diagnostics remain with lsp_code_analysis.py. The
dependency-header graph remains a separate evidence source.

scip-python 0.6.6 currently emits unspecified SymbolInformation kinds, so
queries use SCIP symbol identity and occurrence roles rather than kind filters.
Its upstream tracker also documents a src-layout reference-resolution issue
when the project has no pyright extraPaths configuration. See the upstream
[unspecified-kind report](https://github.com/sourcegraph/scip-python/issues/212)
and [src-layout reference report](https://github.com/sourcegraph/scip-python/issues/221).
Verify representative definition/reference fixtures for the selected project
before relying on an empty reference set.

Official references: [SCIP schema and bindings](https://github.com/scip-code/scip/tree/v0.10.0),
[SCIP CLI](https://github.com/scip-code/scip/blob/v0.10.0/docs/CLI.md),
[scip-python](https://github.com/sourcegraph/scip-python),
[scip-clang](https://github.com/sourcegraph/scip-clang), and
[rust-analyzer SCIP CLI](https://rust-lang.github.io/rust-analyzer/rust_analyzer/cli/index.html).
