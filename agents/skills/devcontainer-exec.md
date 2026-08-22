# devcontainer-exec
<!--
@dependency-start
contract skill
responsibility Preserves a narrow compatibility route for an explicitly selected project Dev Container.
upstream design ../canonical/skills.md public skill registry
upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md AgentCanon tool-container boundary
upstream design ./agent-canon-bootstrap.md shared AgentCanon tool-runtime owner
downstream implementation ../../tools/agent_tools/skill_shim_materializer.py runtime discovery shim
downstream implementation ../../tools/agent_tools/route.py prompt route
@dependency-end
-->

This is a compatibility skill for a caller that explicitly selected an
already-running project Dev Container. It does not own AgentCanon's Python,
Rust, or LSP tools and it does not create, build, or restart a container.

## Routing Boundary

- For AgentCanon tools, language servers, lifecycle, target registration,
  runtime state, or eval collection, use `$agent-canon-bootstrap`. The shared
  non-root tool container is controlled by `bootstrap.sh`; do not use a
  repository `.devcontainer` as its implementation or fallback.
- For project code, use the project's own `docker/` image and
  `test/testrunner.sh`/test list. Do not mount project tests into the AgentCanon
  tool container and do not make this skill discover project test names.
- Use this skill only when the user or the project contract names an existing
  project Dev Container and its exact workspace/config selector is already
  running. A missing container is a typed stop, not permission to run
  `devcontainer up`, `docker exec`, a rebuild, or an unrequested selector.
- Keep stdout, stderr, identity, container workspace, command, and exit/signal
  status intact. A non-zero result belongs to the selected project-container
  execution plane; it is not evidence about AgentCanon or project code outside
  that command.

## Compatibility Command

```bash
devcontainer exec --workspace-folder <project-root> [--config <selector>] \
  zsh -lc '<exact-project-command>'
```

Read back `id` and `pwd` with the same workspace/config selector before the
requested command. Use `zsh -lic` only when interactive startup is part of the
request. Do not add temporary probes outside an explicitly authorized target;
if one is required, preserve unknown state and prove cleanup.

## Closeout

Report the repository-qualified Issue/PR, selector, identity, workspace,
execution plane, exact command, output, exit/signal, and any typed
`container_not_running` or cleanup evidence. This skill's success proves only
the requested command inside an existing project container; it does not prove
AgentCanon bootstrap health, tool parity, project image build, or project test
suite success.
