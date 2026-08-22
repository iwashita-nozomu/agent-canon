# Common Static Analysis
<!--
@dependency-start
contract tool
responsibility Documents cross-language static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/design/dependency-manifest-design.md dependency manifest policy
upstream implementation ../../agent_tools/review_backlog_scan.sh runs integrated review scans
upstream implementation ../../agent_tools/check_hardcoded_numbers.py checks numeric literals
upstream implementation ../../agent_tools/run_repo_dependency_review.sh validates dependency headers
@dependency-end
-->

Common review gates cover repo surfaces regardless of implementation language.

Default commands:

```bash
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  exec --root <target> -- bash \
  /usr/local/share/agent-canon/runtime/tools/agent_tools/review_backlog_scan.sh \
  --report-dir /var/lib/agent-canon/runtime/reports/<run-id>/cross_repo_inspection
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  exec --root <target> -- bash \
  /usr/local/share/agent-canon/runtime/tools/agent_tools/run_repo_dependency_review.sh --fail-missing
```

`review_backlog_scan.sh` writes both JSON and Markdown inventory reports, then
runs dependency, code-dependency, readability, hardcoded-number, log-helper, and
convention scans for the selected scope.
Run the scan against one explicitly selected standalone source or project
target. Cross-repository discovery is not implicit.
