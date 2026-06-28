<!--
@dependency-start
contract reference
responsibility Documents Git diff dependency summary tool usage.
upstream implementation ../../tools/agent_tools/git_dependency_diff_summary.py summarizes Git diffs with dependency expansion artifacts.
upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh extracts code dependency edges.
upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh expands dependency-header graph evidence.
downstream implementation ../../tests/agent_tools/test_git_dependency_diff_summary.py tests CLI behavior.
@dependency-end
-->

# git_dependency_diff_summary.py

Use this tool when a review needs one compact entrypoint for the current Git
diff and the dependency surfaces around that diff.

The tool owns aggregation only. Git changed-file facts come from `git diff`.
Code dependency edges come from `scan_code_dependencies.sh`. Dependency-header
graph expansion comes from `run_repo_dependency_review.sh`. This keeps pass /
fail authority in the existing dependency tools while providing one JSON or
Markdown packet for PR review, change review, or subagent handoff.

```bash
python3 tools/agent_tools/git_dependency_diff_summary.py \
  --root . \
  --report-dir reports/dependency-review/git-diff-summary \
  --format text
```

For a PR-style committed comparison:

```bash
python3 tools/agent_tools/git_dependency_diff_summary.py \
  --root . \
  --base origin/main \
  --head HEAD \
  --report-dir reports/dependency-review/git-diff-summary \
  --format markdown
```

The report directory contains:

- `changed_files.txt`: paths used as dependency expansion seeds.
- `git_stat.txt`: `git diff --stat` output.
- `code_dependencies.tsv`: code dependency edges from imports, includes, and
  shell source statements.
- `dependency-review/dependency_graph.tsv`: dependency-header graph artifact.
- `dependency-review/dependency_edit_scope.txt`: dependency-expanded edit
  scope for the changed paths.
- `summary.json`: schema `agent_canon.git_dependency_diff_summary.v1`.
- `summary.md`: reader-facing Markdown summary.

Use `--skip-code-dependencies` or `--skip-dependency-review` only when the
caller is deliberately checking Git diff summarization in isolation. Use
`--strict-dependency-review` when missing dependency manifests should fail the
same way as PR readiness.
