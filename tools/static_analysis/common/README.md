# Common Static Analysis
<!--
@dependency-start
responsibility Documents cross-language static analysis entrypoints.
upstream design ../README.md language-organized static analysis index
upstream design ../../../documents/dependency-manifest-design.md dependency manifest policy
upstream implementation ../../agent_tools/review_backlog_scan.sh runs integrated review scans
upstream implementation ../../agent_tools/check_hardcoded_numbers.py checks numeric literals
upstream implementation ../../agent_tools/run_repo_dependency_review.sh validates dependency headers
@dependency-end
-->

Common review gates cover repo surfaces regardless of implementation language.

Default commands:

```bash
bash tools/agent_tools/review_backlog_scan.sh --report-dir reports/agents/<run-id>
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
bash tools/agent_tools/scan_code_dependencies.sh
python3 tools/agent_tools/check_hardcoded_numbers.py --changed
```

`review_backlog_scan.sh` writes both JSON and Markdown inventory reports, then
runs dependency, code-dependency, readability, hardcoded-number, log-helper, and
convention scans for the selected scope.
