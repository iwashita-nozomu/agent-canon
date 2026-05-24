<!--
@dependency-start
responsibility Documents the semantic-index candidate-generation tool and Eval harness.
upstream design search-coordination.md coordinated search provider boundary
upstream design local-llm-responsibility-analysis.md local model advisory boundary
upstream design rust-agent-tool-migration.md Rust CLI migration policy
downstream implementation ../rust/agent-canon/src/semantic_index.rs implements the Rust semantic-index CLI
downstream implementation ../rust/agent-canon/src/main.rs routes the semantic-index command
downstream design ../tools/README.md documents operator-facing tool entrypoints
downstream design tools/README.md documents reader-facing tool entrypoints
downstream design ../tools/catalog.yaml catalogs the semantic-index tool
@dependency-end
-->

# Semantic Index

`agent-canon semantic-index` builds a repo-local semantic-vector cache for
text-like files and uses that cache for advisory search, similar-item, merge
candidate, and fixture Eval reports.

The tool is candidate generation, not deletion authority. Strict structure
hashes, dependency graph analysis, AST equality, and safe removal decisions stay
in the existing strict analysis tools.

## Generated Cache

The default database is:

```text
~/.cache/agent-canon/semantic-index/<repo-key>/index.sqlite
```

The default generated cache lives under the operator home directory, not in the
repository tree. Set `AGENT_CANON_SEMANTIC_INDEX_HOME` to move all semantic
index artifacts to another home-managed directory. Rebuild it after relevant
source, tool, workflow, or document changes. Do not commit SQLite files, vector
blobs, or local model output. The legacy repo-local `.agent-canon/semantic-index/`
path remains ignored for explicit `--db` runs and older worktrees.

The MVP stores file/node metadata, hashes, and dense vectors. It does not store
the full original text as a durable truth surface.

Writes use a local temporary SQLite database, copy the completed cache to a
target-directory publish file, then atomically rename it over the requested
path. This keeps normal SQLite locking and journaling behavior during mutation
while still supporting generated cache paths on network-backed worktrees.

## Commands

Build an index:

```bash
agent-canon semantic-index build \
  --root . \
  --include documents \
  --include agents
```

Search by meaning-like vector similarity:

```bash
agent-canon semantic-index search \
  --query "AgentCanon latest submodule pin workflow" \
  --format json
```

For long natural-language task descriptions, avoid shell-quoting the whole
paragraph. Put the text in a file or pipe it on stdin:

```bash
agent-canon semantic-index search \
  --query-file reports/search_query.txt \
  --top-k 20 \
  --format text

cat reports/search_query.txt \
  | agent-canon semantic-index search --query-stdin --top-k 20 --format jsonl
```

`jsonl` emits a bounded summary line followed by one JSON object per result and
does not echo long query text, so agents can stream or filter it without reading
one full JSON array.

List semantic similarity candidates:

```bash
agent-canon semantic-index similar --min-score 0.82
```

`similar` is allowed to cross repository surfaces. A code block and a document
block can be surfaced together when the result is useful as alignment evidence.

List cross-file merge candidates:

```bash
agent-canon semantic-index merge-candidates --min-score 0.82
```

`merge-candidates` still reads the full indexed repository, but it only scores
pairs inside the same responsibility scope, surface kind, document topic, and
node kind. The responsibility scope follows the top-level ownership buckets in
`responsibility-scope.toml`, so review output can distinguish
`runtime-entrypoints`, `shared-tooling`, `shared-policy-documents`,
`eval-and-hook-evidence`, and related surfaces. Documentation, code, and config
are separated first; document buckets are further split by surface such as
skill, workflow, tool docs, issue, memory, note, and general documents. A
code/document match is alignment evidence, never merge evidence, even when the
vectors are nearly identical. Runtime mirror surfaces such as
`.agents/skills/` and `.claude/skills/`, and accumulated eval/report logs, are
also alignment or evidence surfaces rather than merge surfaces. Preserved
source/split guide pairs are excluded for the same reason. Very small
heading-only sections are below the merge-candidate floor because they do not
carry enough local content to justify a consolidation recommendation.

For review, use the same command with JSONL output so each candidate carries its
responsibility metadata:

```bash
agent-canon semantic-index merge-candidates --min-score 0.90 --top-k 20 --format jsonl
```

Each result includes `same_responsibility`, `candidate_bucket`, and per-side
`responsibility_bucket` fields. These fields are review routing evidence only:
they make duplicate-responsibility and consolidation candidates visible, but
they do not authorize deletion or merge without dependency, structure, and
human review evidence.

List thin documentation wrappers:

```bash
agent-canon semantic-index thin-docs --top-k 20 --format text
```

`thin-docs` scores document nodes from the SQLite vector DB and nearby source
files. It combines low meaningful content, high single-target similarity,
reference density, and wrapper/entrypoint language. Protected runtime
entrypoints such as root README / AGENTS surfaces are reported as
`keep_entrypoint` rather than deletion candidates. Other actions are advisory:
`inline_into_target`, `replace_with_catalog_row`, `merge_with_peer`, and
`manual_review`.

Run a fixture Eval:

```bash
agent-canon semantic-index eval \
  --fixture tests/fixtures/semantic-index/basic \
  --report reports/agents/<run-id>/semantic_index_eval.json
```

## MVP Provider

The first provider is `deterministic-dense-v1`, model `hash-token-char-v1`.
It is deterministic and offline so tests and CI can measure the tool without a
local model. A future embedding provider can add model-backed vectors under the
same table contract by writing a new provider/model pair.

## Eval Boundary

`semantic-index eval` measures candidate quality. It checks:

- indexed files and nodes
- missing embeddings
- query Recall@5 and MRR
- known similar pair scores
- must-not pair violations
- build runtime

Eval failure means the candidate generator needs tuning. It does not prove that
a document should be merged or deleted.

## Candidate Generation Boundary

Full-repo input is the normal path. The tool avoids full pairwise comparison by
using vector prefix features to propose exact-rescored candidates. Operators
should not narrow `--include` just to make `merge-candidates` finish; if full
input is too slow, fix candidate generation or responsibility bucketing instead.
