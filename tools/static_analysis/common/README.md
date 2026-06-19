# Common Static Analysis
<!--
@dependency-start
contract tool
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
bash tools/agent_tools/review_backlog_scan.sh \
  --report-dir reports/agents/<run-id>/cross_repo_inspection \
  --submodule-aware
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
bash tools/agent_tools/scan_code_dependencies.sh
python3 tools/agent_tools/check_hardcoded_numbers.py --changed
```

`review_backlog_scan.sh` writes both JSON and Markdown inventory reports, then
runs dependency, code-dependency, readability, hardcoded-number, log-helper, and
convention scans for the selected scope.
Use `--submodule-aware` in template and derived repos so the parent/root surface
and `vendor/agent-canon` source are reported separately.
