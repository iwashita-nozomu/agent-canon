<!--
@dependency-start
contract reference
responsibility Documents the current GitHub remote boundary for the project template and standalone AgentCanon.
upstream design ../agent-canon/agent-canon-github-remote.md defines AgentCanon remote policy.
downstream design ./template-bootstrap.md consumes source-free parent bootstrap policy.
downstream design ../../agents/skills/agent-canon-update.md consumes AgentCanon source PR evidence.
@dependency-end
-->

# Template GitHub Remote

`iwashita-nozomu/project_template` is the canonical template repository and
`iwashita-nozomu/agent-canon` is the canonical standalone source repository.

## Canonical Defaults

- Template URL: `https://github.com/iwashita-nozomu/project_template.git`
- AgentCanon URL: `https://github.com/iwashita-nozomu/agent-canon.git`
- Canonical branch: `main`

Use `origin` for the repository being edited and qualify every Issue/PR with
its repository name. A parent clone does not initialize AgentCanon as a
submodule or vendor path. When source changes are needed, clone AgentCanon into
the parent's ignored `workspace/agent-canondevelop/<qualified-task>/agent-canon`
directory, publish its source PR, and read back merged `main` before closing
the parent task.

## Authentication and CI

Public source reads need no AgentCanon-specific token. Parent CI does not
checkout or mount AgentCanon source. Source PR and eval archive publication use
the credentials of their own host workflow; credentials are not passed into the
shared AgentCanon tool container by default.

## Branch Protection Baseline

Protect both canonical `main` branches with pull requests and required checks,
and disallow force-push/deletion. Record `missing_or_unavailable` when a
caller cannot read branch-protection settings. Source PR checks belong to
AgentCanon; project Docker/test/CI checks belong to the parent.
