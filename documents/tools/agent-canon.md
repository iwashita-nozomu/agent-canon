<!--
@dependency-start
contract reference
responsibility Documents the unified Rust docs formatter and checker.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs implements docs check, format, and check-bootstrap.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs implements the native exact duplicate-design route.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/entrypoint_owner_map.rs implements docs check-entrypoints.
upstream implementation ../../tools/runtime/dispatch/agent-canon/src/config.rs implements the lifecycle-only TOML context projection
downstream design ../../agents/skills/md-style-check.md routes Markdown style work to this tool.
@dependency-end
-->

# agent-canon CLI

`agent-canon` is the canonical Rust entrypoint for deterministic AgentCanon
tooling. This page covers the command families that share the wrapper, including
the read-only TaskClose terminal consumer.
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
tools/bin/agent-canon docs find-redundant-designs [--design-root <path>] [--delete] [--mutation-capability-json <json>] [--runtime-root <path>] [--output <path>]
tools/bin/agent-canon docs check-entrypoints [--root <repo-root>] [--format text|json]
tools/bin/agent-canon docs check-bootstrap [--root <path>] [--static-seed-consumer]
tools/bin/agent-canon template-bundle export --source-root <root> --source-ref <commit-ish> --profile static-seed --output <directory>
tools/bin/agent-canon template-bundle committed-tree --source-root <root> --source-ref <commit-ish>
tools/bin/agent-canon test-design check <test-paths...>
tools/bin/agent-canon waterfall-gate-check (--run-id <run-id> | --report-dir <path>) --gate <gate> [--report-root <path>]
tools/bin/agent-canon task-close (--run-id <run-id> | --report-dir <path>) [--report-root <path>] [--runtime-root <path>]
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

`docs check-bootstrap` validates bootstrap-facing documentation and can validate
an exported static seed or source-hidden consumer root with
`--static-seed-consumer`. It reads the selected root and emits the existing
bootstrap-check findings and pass/fail markers without resolving an AgentCanon
source checkout.

`template-bundle export --profile static-seed` exports the exact allowlisted
source snapshot. `template-bundle committed-tree` returns the resolved commit
and complete Git tree entries for native consumers such as the dependency graph
renderer.

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

`check-entrypoints` validates the finite root entrypoint owner-map grammar,
required owner rows and destinations, and marker ownership. It uses the same
`--root` and `--format text|json` shape as the retired checker while keeping
entrypoint grammar in its dedicated native owner.

## Link repair and source mutation

`tools/bin/agent-canon docs links` is the native link audit route and does not
create `reports/broken_links.txt`; without apply it runs the canonical docs check.
The `--apply` mode requires
`--mutation-capability-json` with exactly `allowed_paths`, `purpose`,
and `authority` fields; every changed file must be within its allowed source
paths. The optional `--check` flag runs the complete docs check after rewriting.
`docs find-redundant-designs` detects exact duplicates natively and requires an
explicit external `--runtime-root` (or the equivalent runtime environment) for
its report. Its `--delete` mode requires an explicit source mutation capability;
all deletion grants and the external report destination are admitted before
source files are removed. `docs find-similar-designs` compares design Markdown
with the native SequenceMatcher owner and writes its report to the external
runtime. `docs organize-designs` plans placements without source writes; its
`--apply` mode requires an explicit mutation capability for every target. No
documentation tool defaults output to the source checkout.
