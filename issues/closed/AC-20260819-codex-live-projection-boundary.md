<!--
@dependency-start
contract issue
responsibility Tracks the project-scoped Codex live-projection boundary and removal of internal tree projection.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md live projection reachability model
downstream design ../../documents/runtime/shared-runtime-surfaces.toml exact root-view manifest
downstream design ../../ROOT_AGENTS.md live parent entrypoint
downstream implementation ../../tools/agent_tools/surface_manifest.py manifest parser and renderer
downstream implementation ../../tools/sync_agent_canon.sh link and bounded migration consumer
downstream implementation ../../tests/agent_tools/test_codex_projection_boundary.py focused projection regression
@dependency-end
-->

# [Codex投影境界] project-scoped .codex surface を保持し、内部 tools/tests 投影を除去する

issue_id: AC-20260819-codex-live-projection-boundary
status: resolved
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/799
source: user
severity: S2
problem: live AgentCanon integration が Codex の project-scoped discovery surface と AgentCanon internal tools/tests tree を同じ projection contract に混在させ、同時に hooks を legacy removal 扱いしている。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/796
done: live root symlink set が AGENTS.md、.codex/config.toml、.codex/agents、.codex/hooks.json、.codex/hooks に閉じ、tools/agent-canon は active projection から除かれ、parent tests は steady-state absence contractから外れる。
affected_surfaces: documents/runtime/shared-runtime-surfaces.toml, documents/runtime/SHARED_RUNTIME_SURFACES.md, ROOT_AGENTS.md, tests/agent_tools/test_codex_projection_boundary.py
edit_scope: owner-bounded
required_action: Codexが直接読むproject surfaceとhook entrypoint closureだけを投影し、generic tools/tests projectionとstale runtime aliasを除去する。
close_condition: focused manifest tests、document alignment、dependency/header/static gates、Issue mirror、PR required checksがpassし、Issueからbranch、commit、PR、validationを追跡できる。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/796

## Baseline

- AgentCanon source: `main@0ea5bb6d5d0bfc2e027698612aeb6fc5a3c8b0c2`
- project template: `main@6110ac3546a6309c59af63a01b701be4316e954c`
- work branch: `agent/796-codex-projection-boundary`
- consumer issue: `iwashita-nozomu/project_template#182`

## Confirmed state

`documents/runtime/shared-runtime-surfaces.toml` currently projects
`tools/agent-canon -> tools` as an active runtime surface, while
`.codex/hooks.json` and `.codex/hooks` are placed in `removed_legacy`. It also
keeps `tests` in the steady-state root-absence set even though parent tests are
project-owned.

AgentCanon owns actual project-scoped custom agent definitions in
`.codex/agents/*.toml`, registration and runtime settings in
`.codex/config.toml`, and lifecycle declarations in `.codex/hooks.json`.
Removing `.codex` would make those custom agents and hooks undiscoverable; the
correct repair is to retain them and remove only the unrelated tree aliases.

## Canonical reachability model

```text
D = {
  AGENTS.md,
  .codex/config.toml,
  .codex/agents,
  .codex/hooks.json
}
R(D) = { .codex/hooks }
P = D ∪ R(D)
```

The hook dispatcher is reached through `.codex/hooks` and resolves the exact
AgentCanon physical checkout as its source root. Its imports therefore use the
same reviewed pin and do not require a root `tools/agent-canon` alias.

## Scope

- add `.codex/hooks.json` and `.codex/hooks` to active symlink projection;
- retain `AGENTS.md`, `.codex/config.toml`, and `.codex/agents`;
- move `tools/agent-canon` out of active projection and keep only bounded stale-symlink cleanup;
- remove parent `tests` from the steady-state removed-legacy set;
- update the live-integration document and root command route;
- add a focused structural regression for exact active link specs and exclusions.

## Non-goals

- deleting AgentCanon custom agents, project config, hooks, tools, or tests from the source repository;
- redesigning role aliases or direct model dispatch (#775);
- deleting the static-seed exporter (#781);
- changing update transaction semantics or parent product commands;
- introducing a new manifest, registry, resolver, or compatibility wrapper.

## Acceptance criteria

- [ ] active symlink paths equal `AGENTS.md`, `.codex/config.toml`, `.codex/agents`, `.codex/hooks.json`, `.codex/hooks`;
- [ ] active link specs contain no `tools/agent-canon` or `tests` path;
- [ ] `.codex/hooks.json` and `.codex/hooks` are not legacy-removal entries;
- [ ] parent `tests` is not a steady-state AgentCanon absence requirement;
- [ ] former `tools/agent-canon` stale symlink remains safely removable without deleting regular parent content;
- [ ] ROOT_AGENTS routes tools through the exact `vendor/agent-canon` pin;
- [ ] focused tests and repository required checks pass;
- [ ] consumer implementation remains separately traceable through project_template#182.
