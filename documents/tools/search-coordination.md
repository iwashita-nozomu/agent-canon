<!--
@dependency-start
contract reference
responsibility Routes repository search requests to native text, semantic-index, catalog, dependency, or LSP owners without combining their results.
upstream design ../../tools/README.md shared tool command surface
upstream design ../../tools/README.md operator-facing tool guide
downstream implementation ../../tools/analysis/search/search.py routes explicit providers
downstream implementation ../../tools/analysis/dependencies/graph_client.py owns source-derived dependency context
downstream implementation ../../tools/analysis/code/lsp_code_analysis.py owns code facts and bounded LSP discovery
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/semantic_index/mod.rs owns semantic-index search
downstream implementation ../../tests/agent_tools/test_search.py validates provider routing and failure semantics
@dependency-end
-->

# Repository Search

`tools/analysis/search/search.py` is the public AgentCanon search entrypoint and
a thin router to existing owners. It runs only the selected providers and
returns their results separately. It does not build local cards, implement a
ranker, or combine provider scores.

The default provider is stateless Git text search. Select `semantic` explicitly
for the Rust `semantic-index`; select `tool`, `header-deps`, or `code-deps` only
when that structured property is the question. A semantic-index failure remains
a failure: search does not build an index or silently fall back to text.

## Native providers

| Provider | Owner and behavior |
| --- | --- |
| `text` | Git `grep` over the selected or default repository surfaces. This is exact text/regex matching, not relevance ranking. |
| `semantic` | Rust `agent-canon semantic-index search`. It reads the selected semantic-index cache and returns that owner's result and failure status. |
| `tool` | Git `grep` restricted to `tools/catalog.yaml`, the canonical tool catalog. |
| `header-deps` | `GraphClient` source-derived dependency context for the supplied source path. It does not parse dependency headers again or require a persisted graph. |
| `code-deps` | One-shot LSP facts from `lsp_code_analysis.py`, filtered by a case-insensitive literal query over native symbol/relation/candidate fields. It does not rank results or fall back to a Python AST call approximation. |

When multiple providers are explicitly selected, their result blocks remain
independent. A failure from one selected provider is reported as a failure; it
does not trigger another provider or hide successful results from the others.

## Git text and catalog queries

Git owns its native pattern semantics. An inline `--query` or `--purpose` is one
pattern. `--regex` enables Git extended-regex matching; `--word-regexp` selects
Git whole-word matching; `--case-sensitive` overrides the default
case-insensitive search. A `--query-file` is passed to Git as a native pattern
file, so separate lines are separate patterns. Search does not tokenize natural
language, infer terms, or rank paths.

`--surface` selects Git pathspecs for `text` and bounded source paths for
`code-deps`. Without a text surface, Git searches the current repository;
`--untracked --exclude-standard -I` includes nonignored worktree files while
omitting ignored and binary content. `--exclude` is passed as an excluded Git
pathspec and is also used by LSP discovery. `--top` maps to Git's native
per-file `--max-count` and to semantic-index `--top-k`; it is not a cross-file
ranking limit. Git regex and word-boundary flags affect only Git-backed text
and catalog searches; GraphClient, semantic-index, and LSP keep their own
query contracts.

Examples:

```bash
python3 tools/analysis/search/search.py \
  --query 'dependency|graph' --regex --word-regexp --providers text --format json

python3 tools/analysis/search/search.py \
  --query-file reports/search-patterns.txt --providers text --format json

python3 tools/analysis/search/search.py \
  --query 'semantic-index' --providers tool --format json
```

Git match, no-match, and execution-error outcomes remain distinct in the
provider result. JSON output is a transport envelope with the native provider
stdout or structured payload; it does not synthesize scores or candidate
evidence from those outputs.

## Semantic, dependency, and code queries

Use the semantic owner only when semantic repository retrieval is the actual
intent and its index is available for the selected source surface:

```bash
python3 tools/analysis/search/search.py \
  --purpose 'find responsibility scope tooling' \
  --providers semantic --format json
```

Building or repairing a semantic index is a separate explicit
`agent-canon semantic-index build` operation. `search.py` does not refresh an
index as a side effect. Semantic-index cache, provider, source identity, and
stale-state semantics remain owned by [Semantic Index](semantic_index.md).

Dependency context uses an exact source path rather than a natural-language
ranker:

```bash
python3 tools/analysis/search/search.py \
  --query tools/analysis/search/search.py --providers header-deps --format json
```

For code facts, select paths and use the LSP owner:

```bash
python3 tools/analysis/search/search.py \
  --query 'target_symbol' --providers code-deps \
  --surface tools/analysis/search/search.py --format json
```

Code analysis failures remain visible and typed. Exact text search, semantic
retrieval, source dependency context, tool-catalog lookup, and LSP reports are
different evidence types; none substitutes for source ownership, dependency
review, tests, or acceptance review.

## Responsibility-first use

For an implementation or review question, first use the selected workflow's
responsibility context or direct owner path. Then choose the one search property
that is still unresolved:

1. Known path, symbol spelling, literal, or error text: direct inspection or Git
   text search.
2. Broad repository meaning: semantic-index, when that owner and its cache are
   explicitly selected.
3. Tool metadata: the catalog provider or direct catalog inspection.
4. Dependency relation: source `GraphClient` context for a path.
5. Code relations: explicit LSP analysis for selected code paths.

Search results are advisory. Expand bounded source hits through the existing
dependency-analysis route before turning them into an edit scope. Do not
materialize a second index or treat provider output as a dependency proof.
