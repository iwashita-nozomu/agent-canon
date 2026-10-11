<!--
@dependency-start
contract reference
responsibility Documents the unified Rust docs formatter and checker.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs implements docs check and format.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/config.rs implements the lifecycle-only TOML context projection
downstream design ../../agents/skills/md-style-check.md routes Markdown style work to this tool.
@dependency-end
-->

# agent-canon CLI

`agent-canon` is the canonical Rust entrypoint for deterministic AgentCanon
tooling. This page covers the command families that share the wrapper.
`agent-canon docs` owns Markdown documentation formatting and adjacent checks.
`agent-canon test-design` owns resilient test-design diagnostics.
The host lifecycle invokes `codex-config` after native compilation to project
the two managed context defaults into the personal Codex config. It passes the
personal TOML through stdin and receives the format-preserving result through
stdout, which the host writes to its same-directory temporary file before the
atomic replacement. This helper does not create a separate host configuration
route.
Deterministic prompt-to-skill routing is owned by
`python3 tools/agent/orchestration/route.py --prompt`.

Use `tools/bin/agent-canon docs -h` as the option contract before opening
implementation files. The help output lists commands, shared options, and
examples in a compact text block.

## Reader Map

- Owns the documented command families for the unified Rust `agent-canon`
  wrapper, especially docs checks and test-design diagnostics.
- Main path: Commands and Legacy Entrypoints.
- Read this before using `agent-canon docs` or deciding whether a legacy
  Python entrypoint should forward to the Rust wrapper.
- Boundary: prompt-to-skill routing remains owned by
  `python3 tools/agent/orchestration/route.py --prompt`.

## Commands

```bash
tools/bin/agent-canon docs -h
tools/bin/agent-canon docs check <paths...>
tools/bin/agent-canon docs format <paths...>
tools/bin/agent-canon test-design check <test-paths...>
agent-canon codex-config --source-config <read-only-source-config>
python3 tools/agent/orchestration/route.py --prompt "<request>" --mode routing-only --format json
```

`check` invokes the configured `markdownlint-cli2` and offline `lychee` commands
for the selected Markdown paths, parses each file with Quarto's embedded
Pandoc AST, and validates Mermaid fences with `mmdc`. Provider output and exit
status are passed through. AgentCanon retains only the checks the standard
providers do not own: per-depth unordered-marker consistency, the exact math
delimiter convention, workspace-absolute local targets, bootstrap-facing docs,
and runtime profile inventory drift. Mermaid validation renders to a temporary
directory; it never rewrites diagram source. When no path is supplied, the
command checks the repository documentation targets used by the shared docs
gate.

If the command contract is unclear, run `tools/bin/agent-canon docs -h` first.

`test-design check` reports missing oracle, brittle coupling, exact
mock/output/prose assertions, time coupling, unseeded randomness, and
property/metamorphic candidates. Its detailed contract lives in
[test_design.md](test_design.md).

`route.py --prompt` returns the full selected `SKILLS`, `ACTIVE_SKILLS` for the
current stage, and `DEFERRED_SKILLS` for dynamic wave triggers. Use it before
broad skill-selection prose or subagent fan-out.

`format` normalizes line endings, trailing whitespace, and repeated blank lines,
then runs the same adjacent `check` path. Math and Mermaid content is not
rewritten by the checker; edit source deliberately and validate it with `check`.

## Compatibility Entrypoints

`python3 tools/validation/documentation/checks/audit_and_fix_links.py --check` is a compatibility spelling
that forwards to the single canonical Rust route, `tools/bin/agent-canon docs
check ...`; it does not create `reports/broken_links.txt`. Its `--apply` mode
is source mutation and requires a typed `--mutation-capability-json` covering
every file to be changed. Design duplicate/similarity/organization tools also
require an explicit external `--runtime-root` (or the equivalent runtime
capability) for reports; organization and deletion apply modes require the
same explicit mutation capability. No documentation tool defaults output to
the source checkout.
