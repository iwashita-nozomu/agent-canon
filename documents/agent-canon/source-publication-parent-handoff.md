<!--
@dependency-start
contract reference
responsibility Defines the source-to-parent evidence handoff without granting source checkout mutation authority.
upstream design ../../documents/runtime/runtime-log-archive.md owns archive publication.
upstream design ./agent-canon-update-route.md owns source branch and parent readback.
upstream implementation ../../bootstrap.sh owns runtime lifecycle and eval collection.
@dependency-end
-->

# Source publication handoff

The AgentCanon source checkout publishes only its reviewed branch/PR and
merged `main` identity. It does not stage a parent gitlink, create a parent
projection, or write parent lifecycle records.

The handoff packet names:

- qualified repository and Issue/PR;
- source branch, merge commit, and tree digest;
- focused and runtime-profile validation results;
- external runtime root and cleanup readback;
- eval collection receipt and, when requested, archive publication receipt.

The parent reads the merged `main` commit and performs parent-owned validation
in its own repository. AgentCanon tool/eval artifacts remain under the explicit
runtime root and are sent to `iwashita-nozomu/agent-canon-log` only through the
typed archive publisher. A failed archive operation keeps its external spool
and failure receipt for retry.

No handoff may contain a vendor path, `.gitmodules` entry, root projection,
source symlink, copied policy, or source-local generated artifact.
