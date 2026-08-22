<!--
@dependency-start
contract reference
responsibility Documents the source-free parent onboarding route for standalone AgentCanon.
upstream design ../runtime/bootstrap-runtime.md owns the explicit runtime contract.
upstream design ../agent-canon/agent-canon-update-route.md owns source publication and readback.
upstream implementation ../../bootstrap.sh owns lifecycle commands.
@dependency-end
-->

# Parent project bootstrap runbook

A normal project clone is source-free. It does not initialize an AgentCanon
vendor checkout, Git submodule, source symlink, root projection, or AgentCanon
runtime. Project code and project tests remain owned by the parent repository.

## Optional AgentCanon tool runtime

When a task needs AgentCanon Python/Rust/LSP tools, start one explicit shared
runtime from the standalone AgentCanon source checkout:

```bash
ROOT=<authorized-parent-root>
RUNTIME="$ROOT/workspace/agent-canon-runtime/<installation>"
COMMON=(--control-parent-root "$ROOT" --runtime-root "$RUNTIME")

./bootstrap.sh "${COMMON[@]}" install
./bootstrap.sh "${COMMON[@]}" start
./bootstrap.sh "${COMMON[@]}" status
./bootstrap.sh "${COMMON[@]}" target add --root <project-root> --mode read-only
./bootstrap.sh "${COMMON[@]}" stop
./bootstrap.sh "${COMMON[@]}" gc
./bootstrap.sh "${COMMON[@]}" uninstall
```

The control root must be the authorized parent checkout and the runtime must
be its descendant but outside the source checkout. The source checkout cannot
be either root. Runtime cache,
reports, eval collections, Codex home, Cargo output, and temporary files stay
under the external runtime root.

## Source and project boundaries

AgentCanon source changes are made in an ignored qualified clone under
`workspace/agent-canondevelop/<qualified-task>/agent-canon`, published through
an Issue-qualified AgentCanon PR, and read back from merged `main`. Parent
project implementation and tests are run through the parent-owned Docker/test
entrypoint. No parent command may restore a vendor checkout or submodule as a
fallback.

## Failure triage

| Symptom | First check |
| --- | --- |
| missing or invalid runtime | verify explicit control/runtime arguments and containment |
| source becomes dirty after inspection | inspect source/runtime path ownership and stop the task |
| AgentCanon change is needed | create/update the qualified standalone source PR |
| eval/archive publication fails | preserve the external spool and failure receipt for retry |
| project test fails | classify the parent project execution plane separately |
