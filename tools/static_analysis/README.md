# Static Analysis Tools
<!--
@dependency-start
contract tool
responsibility Documents language-organized static analysis tool entrypoints.
upstream design ../README.md shared tool index
downstream design python/README.md Python static analysis entrypoints
downstream design cpp/README.md C and C++ static analysis entrypoints
downstream design common/README.md cross-language static analysis entrypoints
@dependency-end
-->

This directory is the index for language-specific static analysis surfaces.
Canonical implementations still live in `tools/agent_tools/` unless a language
family needs a dedicated executable package.

Use this split for routing:

- `python/`: Python type, logging, OOP/readability, and explicit `Any` checks.
- `cpp/`: C and C++ readability, include, and native boundary checks.
- `common/`: cross-language dependency, hardcoded-number, and repo review scans.

The integrated repo entrypoint is:

```bash
bash tools/agent_tools/review_backlog_scan.sh \
  --report-dir reports/agents/<run-id>/cross_repo_inspection \
  --submodule-aware
```
