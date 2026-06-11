<!--
@dependency-start
responsibility Documents test_design Rust CLI usage and output contract.
upstream design ../../references/test-design-flexibility.md source basis for resilient test design
upstream design ../coding-conventions-testing.md shared testing policy
upstream implementation ../../rust/agent-canon/src/test_design.rs implements the command
downstream design ../tools/tool-docs.toml one-to-one tool/document manifest
downstream design ../../agents/skills/test-design.md uses this command before test planning
@dependency-end
-->

# test_design

`agent-canon test-design check` is the Rust diagnostic entrypoint for
change-resilient test design. It scans test-like files for signals that make
tests brittle or under-specified before an agent writes or rewrites tests.

The command does not prove that a test is bad. It separates clear repair items
from review prompts:

- `fix-now`: missing path, missing oracle, unseeded randomness.
- `review`: likely coupling to private state, exact mock call sequence, exact
  error/output prose, wall-clock waiting, or complex test-body control flow.
- `design-hint`: parser, formatter, graph, router, or mapping tests that look
  example-only and may need property or metamorphic cases.

## Commands

```bash
tools/bin/agent-canon test-design -h
tools/bin/agent-canon test-design check <test-paths...>
tools/bin/agent-canon test-design check --format json tests/tools
```

When no path is supplied, the command scans `tests/` under the selected root.
Use `--root <repo-root>` when checking a parent repo from another working
directory.

## Output Contract

Text output starts with one compact status line:

```text
TEST_DESIGN_CHECK=pass scanned_files=3
TEST_DESIGN_CHECK=warn scanned_files=3 findings=2 fix_now=0 review=1 design_hint=1
TEST_DESIGN_CHECK=fail scanned_files=3 findings=1 fix_now=1 review=0 design_hint=0
```

Detailed text findings are bounded between
`TEST_DESIGN_REPORT_BEGIN` and `TEST_DESIGN_REPORT_END`.

JSON output uses schema `agent_canon.test_design_check.v1` and includes
`status`, `scanned_files`, `finding_count`, `fix_now_count`, and `findings`.

Exit code is `1` only when at least one `fix-now` finding exists. `review` and
`design-hint` findings return `0` so a skill can interpret them without turning
every smell warning into a hard block.
