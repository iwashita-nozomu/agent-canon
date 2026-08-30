<!--
@dependency-start
contract reference
responsibility Documents the focused content-preservation checker for conflict and rework.
upstream design ../../agents/skills/pr-processing.md owns integration and rework order.
upstream implementation ../../tools/repository/git/conflict_preservation.py owns packet capture and readback.
downstream implementation ../../tests/agent_tools/test_conflict_preservation.py validates the focused fixture.
@dependency-end
-->

# conflict_preservation.py

`conflict_preservation.py` is the small content-level companion to the
existing `repository_topic_clone.py` lifecycle. It records the merge base,
base/ours/theirs index stages, hunk evidence, staged state, and unaffected
content before a conflict is resolved. It does not select a side or resolve
the conflict.

`capture` is invoked automatically when `merge-main` stops on a conflict.
`validate` and `validate-rework` report packet validity; they do not complete a
merge. Only `repository_topic_clone.py finalize-merge`/`resume-merge` may
commit a stopped merge, and those routes invoke the validation and readback
against the current clone.

```bash
python3 tools/repository/git/conflict_preservation.py capture \
  --repo-root <clone> --base <merge-base> --ours <head> --theirs <origin-main> \
  --output <clone>/.agent-canon/conflict-preservation.json

python3 tools/repository/git/conflict_preservation.py validate \
  --inventory <clone>/.agent-canon/conflict-preservation.json \
  --plan <preservation-plan.json> --repo-root <clone>

python3 tools/repository/git/conflict_preservation.py validate-rework \
  --packet <rework-preservation.json>
```

Every path needs an owner, disposition (`keep`, `replace`, or `manual`),
rationale, and exact edit delta. Text preservation uses `hunk_identity` with
the captured source hunk SHA-256, source/resolved unified-diff header, and
derived changed/context lines bound to the same repository path; callers may
not substitute arbitrary required lines, and matching text somewhere else is
not accepted. Whole-file checkout, reset, reclone,
overwrite, or regeneration requires a reconstruction map. Validation rejects
an unresolved index or a missing unaffected hunk; a clean path list alone does
not prove preservation.

The hook accepts a destructive command only when every normalized mutation
target is covered by the inventory/plan, the packet files exist below the
active clone's `.agent-canon/` evidence scope, and `HEAD`, `MERGE_HEAD`, and
the target stage blob references still equal the captured snapshot. Broad
reset, clean, reclone, multi-source replacement, and unbounded pathspecs are
held for explicit finalization.
