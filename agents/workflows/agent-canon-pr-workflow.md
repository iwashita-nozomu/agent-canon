# AgentCanon Source PR Workflow

<!--
@dependency-start
contract workflow
responsibility Owns standalone AgentCanon source branch, PR, merge, and main readback.
upstream design ../../documents/runtime/bootstrap-runtime.md standalone bootstrap boundary
upstream design ../../documents/tools/visualization_contract.md canonical visualization contract for completion evidence
upstream design ../skills/agent-canon-update.md source update owner
downstream implementation ../../bootstrap.sh shared runtime validation entrypoint
@dependency-end
-->

## Scope

Use this workflow for changes to `iwashita-nozomu/agent-canon`. AgentCanon is a
standalone source repository. A parent may use an ignored qualified clone at
`workspace/agent-canondevelop/<qualified-task>/agent-canon`, but it does not
own a vendor checkout, submodule pin, root projection, or copied AgentCanon
policy.

Always qualify GitHub objects as `iwashita-nozomu/agent-canon#<number>`. Issue
`#841` owns local bootstrap/runtime/eval lifecycle; `#821` owns prebuilt
artifact distribution.

## Source transaction

1. Fetch remote `main`, inspect open AgentCanon PRs/Issues, and record branch,
   HEAD, remote, and dirty-state classification.
2. Create one Issue-qualified topic branch in the standalone source clone.
3. Read the canonical owner and dependency-expanded callers before editing.
4. Implement the contract-complete change. Runtime/cache/eval/test artifacts
   must use an explicit external runtime root and must not create source-local
   `.agent-canon`, `target`, `__pycache__`, or generated reports.
5. Run focused validation, then the runtime profile selected by the changed
   responsibility. Preserve failure evidence by execution plane: AgentCanon
   tool container, Host adapter/archive, or project execution.
6. Commit only the Issue-owned write set, push the topic branch, and open or
   update the AgentCanon PR. The body states what changed, why, validation,
   cleanup, and remaining limitations.
7. Process review and CI to green, merge the AgentCanon PR, fetch `main`, and
   read back the merge commit.

## Runtime validation

For bootstrap/runtime changes, use one explicit installation:

```bash
ROOT=<authorized-parent-root>
RUNTIME="$ROOT/workspace/agent-canon-runtime/<installation>"
COMMON=(--control-parent-root "$ROOT" --runtime-root "$RUNTIME")

./bootstrap.sh "${COMMON[@]}" install
./bootstrap.sh "${COMMON[@]}" start
./bootstrap.sh "${COMMON[@]}" target add --root <project> --mode read-only
./bootstrap.sh "${COMMON[@]}" status
./bootstrap.sh "${COMMON[@]}" tool run --root <project> <verified-id> -- <args...>
./bootstrap.sh "${COMMON[@]}" eval collect --root <project> --run-id <id>
./bootstrap.sh "${COMMON[@]}" stop
./bootstrap.sh "${COMMON[@]}" gc
./bootstrap.sh "${COMMON[@]}" uninstall
```

Use the existing archive publisher for `eval sync`. A failed collection or
publication keeps its spool and receipt. Successful publication requires
non-force push plus remote ref/tree/blob readback in
`iwashita-nozomu/agent-canon-log`.

## Closeout

- source branch/commit and AgentCanon PR are pushed and qualified;
- AgentCanon `main` contains the merge and was fetched locally;
- source status/content is unchanged by runtime/eval validation;
- exactly one shared container was used for registered targets;
- task-owned containers/images/runtime paths are absent after cleanup;
- pre-existing Docker resources and global Codex state are unchanged;
- parent repositories have no AgentCanon vendor/submodule/root projection.
