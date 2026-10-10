# Static Analysis Tools
<!--
@dependency-start
contract tool
responsibility Documents language-organized static analysis tool entrypoints.
upstream design ../../../README.md shared tool index
downstream design python/README.md Python static analysis entrypoints
downstream design ../../../../documents/tools/oop/cpp/readability.md C++ OOP readability checker and documentation
downstream design common/README.md cross-language static analysis entrypoints
@dependency-end
-->

This directory is the index for language-specific static analysis surfaces.
Canonical implementations live in their owner packages under `tools/analysis/`
and `tools/validation/`; language-specific directories group only the relevant
static-analysis entrypoints.

Use this split for routing:

- [python/](python/README.md): Python type, logging, OOP/readability, Ruff, and BasedPyright checks.
- [C++ OOP readability](../../../../documents/tools/oop/cpp/readability.md): C and C++ object-oriented design/readability review signals.
- [common/](common/README.md): cross-language dependency, native magic-value, and repo review scans.

The integrated repo entrypoint is:

```bash
./bootstrap.sh --control-parent-root <root> --runtime-root <runtime> \
  exec --root <target> -- bash \
  /usr/local/share/agent-canon/runtime/tools/repository/github/review_backlog_scan.sh \
  --report-dir /var/lib/agent-canon/runtime/reports/<run-id>/cross_repo_inspection
```
