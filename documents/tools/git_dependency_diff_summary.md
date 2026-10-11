<!--
@dependency-start
contract reference
responsibility Documents Git diff summary usage with optional SCIP impact and dependency-header evidence.
upstream implementation ../../tools/analysis/dependencies/git_dependency_diff_summary.py summarizes Git diffs.
upstream implementation ../../tools/analysis/dependencies/scip_index.py projects standard SCIP facts.
upstream implementation ../../tools/analysis/dependencies/run_repo_dependency_review.sh expands dependency-header graph evidence.
downstream implementation ../../tests/agent_tools/test_git_dependency_diff_summary.py tests CLI behavior.
@dependency-end
-->

# git_dependency_diff_summary.py

Use this tool to summarize Git changes alongside dependency-header evidence and,
when selected, a bounded projection from a native SCIP index.

The summary does not build an index. Create one with the project’s native
indexer and pass its external runtime path when repository-wide symbol and
reference evidence can affect the edit scope. A missing index is reported as
not selected; it does not make every Git diff fail.

Pass --scip-index once per selected language/module index.

For a Python project, the project environment owner supplies the explicit
environment file. C/C++ indexing consumes the compile database selected by the
project build owner. Rust currently has no selected producer because the pinned
rust-analyzer SCIP command has not been qualified.

    python3 tools/analysis/dependencies/scip_index.py index \
      --root . \
      --runtime-root /external/runtime \
      --language python \
      --project-name <project-name> \
      --project-version <project-version> \
      --python-environment <project-owned-environment.json> \
      --output scip/<run-id>/python/index.scip

    python3 tools/analysis/dependencies/git_dependency_diff_summary.py \
      --root . \
      --base origin/main \
      --head HEAD \
      --runtime-root /external/runtime \
      --scip-index scip/<run-id>/rust/index.scip \
      --report-dir reports/dependency-review/git-diff-summary \
      --format markdown

The report directory contains:

- changed_files.txt: paths used as dependency expansion seeds;
- git_stat.txt: git diff --stat output;
- scip_impact.json: definitions, references, and index references for selected
  changed source paths, or an explicit not-selected / no-selected-targets
  status; this is not evidence that unsupported source files have no references;
- dependency-review/dependency_graph.tsv: dependency-header graph artifact;
- dependency-review/dependency_edit_scope.txt: dependency-expanded edit scope;
- summary.json: schema agent_canon.git_dependency_diff_summary.v2;
- summary.md: reader-facing Markdown summary.

The SCIP projection remains bounded and records the index artifact path and
hash. It does not serialize the full SCIP index into another JSON, TSV, or
database. References are not presented as callers or callees unless an
indexer-provided SCIP relationship explicitly represents that fact.
The index hash does not bind the index to current source bytes; the projection
marks source freshness unverified and must not be used to infer that omitted
symbols or call edges are absent.

Use --skip-scip-impact when checking Git and dependency-header summarization
alone.
Use --skip-dependency-review to omit dependency-header expansion, and
--strict-dependency-review when missing dependency manifests should fail.
