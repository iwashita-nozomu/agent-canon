<!--
@dependency-start
contract reference
responsibility Documents the canonical standalone AgentCanon GitHub remote.
downstream design ../../agents/workflows/agent-canon-pr-workflow.md consumes branch/PR evidence.
downstream implementation ../../bootstrap.sh validates the source checkout locally.
@dependency-end
-->

# AgentCanon GitHub remote

`iwashita-nozomu/agent-canon` on GitHub is the canonical standalone
AgentCanon repository.

## Canonical defaults

- URL: `https://github.com/iwashita-nozomu/agent-canon.git`
- integration branch: `main`
- source work: one Issue-qualified branch and pull request

The remote is used by the source PR workflow, not by a parent vendor checkout
or Git submodule. Parent repositories do not need an AgentCanon token, source
checkout, network access, or root projection for normal project operation.

## Source clone and publication

Use an ignored qualified clone under the parent workspace when editing from a
parent task. Verify the remote explicitly before publishing:

```bash
git remote get-url origin
gh repo view iwashita-nozomu/agent-canon
```

Push the Issue-qualified branch and open/update the PR in
`iwashita-nozomu/agent-canon`. Merge through the normal PR route, then fetch
and read back `main` before any parent documentation or integration update.

## Runtime and credentials

AgentCanon tools run through `bootstrap.sh` with explicit
`--control-parent-root` and `--runtime-root`. Credentials remain in the host
GitHub client process; they are not written to source, runtime, or a global
environment file. A failed remote lookup is recorded as source/host evidence
and does not trigger a vendor, submodule, or hidden clone fallback.
