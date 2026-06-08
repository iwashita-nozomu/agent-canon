<!--
@dependency-start
responsibility Documents the unified Rust docs formatter and checker.
upstream implementation ../../rust/agent-canon/src/docs.rs implements docs check, format, fix-math, and fix-mermaid.
downstream design ../../agents/skills/md-style-check.md routes Markdown style work to this tool.
downstream implementation ../../tools/ci/run_docs_checks.sh forwards legacy docs-check calls.
@dependency-end
-->

# agent-canon docs

`agent-canon docs` is the canonical Rust entrypoint for Markdown documentation
formatting and adjacent checks.

Use `tools/bin/agent-canon docs -h` as the option contract before opening
implementation files. The help output lists commands, shared options, and
examples in a compact text block.

## Commands

```bash
tools/bin/agent-canon docs -h
tools/bin/agent-canon docs check <paths...>
tools/bin/agent-canon docs format <paths...>
tools/bin/agent-canon docs fix-math <paths...>
tools/bin/agent-canon docs fix-mermaid <paths...>
```

`check` verifies Markdown lint, heading order, fenced-code language, math
notation, local links, bootstrap-facing docs, and runtime profile inventory
drift. When no path is supplied, it checks the repository documentation targets
used by the shared AgentCanon docs gate.

Failed text-mode checks keep the compact machine lines and also emit a
structured prose report block on stderr:

```text
DOCS_CHECK=fail
DOCS_CHECK_FINDING=<check>:<path>:<line>:<message>
DOCS_CHECK_REPORT_BEGIN
status: fail
summary: Documentation checks found <n> issue(s). Use these locations before reading broader files.
findings:
- check: <check>
  location: <path>:<line>
  problem: <message>
next_action:
- Open only the reported location and nearby lines needed for the repair.
DOCS_CHECK_REPORT_END
```

Agent and subagent prompts should use the report block as the repair packet
instead of opening implementation files or scanning whole documents. If the
command contract is unclear, run `tools/bin/agent-canon docs -h` first.

`format`, `fix-math`, and `fix-mermaid` write mechanical repairs and then run
the same adjacent `check` path. A formatter run is complete only when the final
`DOCS_CHECK=pass` evidence is present or the unavailable command is recorded as
a blocker.

## Legacy Entrypoints

These old commands are compatibility forwarders:

- `bash tools/ci/run_docs_checks.sh`
- `python3 tools/docs/format_markdown.py`
- `python3 tools/docs/fix_markdown_math.py`
- `python3 tools/docs/fix_mermaid.py`
- `python3 tools/docs/check_markdown_lint.py`
- `python3 tools/docs/check_markdown_math.py`
- `python3 tools/docs/audit_and_fix_links.py --check`

When a forwarder is called, it prints `AGENT_CANON_FORWARDER=deprecated`,
`AGENT_CANON_FORWARDER_SEVERITY=fix-now`, the caller chain, and the canonical
`tools/bin/agent-canon docs ...` command before executing the Rust entrypoint.
