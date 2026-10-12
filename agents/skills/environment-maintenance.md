# environment-maintenance
<!--
@dependency-start
contract skill
responsibility Owns the expected Dockerfile-to-image-to-test structure for repository environments.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../CONTAINER_OPERATIONS.md canonical container and devcontainer ownership boundary
upstream design ./gpu-execution.md ordinary GPU Docker execution and optional admission boundary
downstream implementation ./dependency-design.md dependency placement under the expected structure
downstream implementation ./environment-cleanup.md environment cleanup route
downstream implementation ./devcontainer-exec.md targeted running-container execution boundary
downstream implementation ../../tests/agent_tools/test_environment_skill_expected_structure.py expected-structure contract
downstream implementation ../../tests/agent_tools/test_gpu_execution_docker_all_contract.py GPU wiring documentation regression contract
@dependency-end
-->

## Reader Map

- Purpose: assess requested changes to environment construction, dependencies,
  runtime wiring, and their consumers.
- Use When: the task changes a runtime image, dependency, CI, Dev Container,
  Compose setup, or environment compatibility rule.
- Flow: identify the changed guarantee and its owner, trace affected consumers,
  and select the acceptance evidence for that change.
- Boundary: follow the caller's project environment and defaults. AgentCanon's
  shared Python/Rust/LSP tool environment is separate from a consumer project's
  product runtime.

## Purpose

Keep an environment change aligned with the repository's actual build and run
route. Determine which capability changes, where it belongs, what selects it,
and how the affected behavior is checked. This Skill does not prescribe one
container layout for every caller.

## Use When

- The requested change affects an environment definition or its consumers.
- A dependency or runtime capability must be added, changed, or removed.
- An environment requirement or setup instruction no longer matches its owner.

Routine execution of an existing project command is not an environment change.

## Method

1. Start from the requested guarantee, changed target, and its environment
   owner. Reuse the project's documented build, run, and validation route.
2. Inspect only the definitions and consumers that can be affected: for
   example, a Dockerfile/image target, dependency manifest, runtime config,
   CI job, or Dev Container. Distinguish installed dependencies from runtime
   inputs such as data, credentials, or devices.
3. Place the change where the owner expects it and update consumers whose
   actual contract changes. Preserve existing defaults and supported execution
   behavior; do not add a separate host or tool-container path as a substitute
   for the project's selected environment.
4. Select checks that establish the changed guarantee. Keep documentation,
   dependency resolution, image construction, and runtime acceptance distinct;
   report which were performed and which remain unverified.

## Conditional owner routes

- If dependency placement, provider, version, or lock semantics are in scope,
  use [dependency-design](dependency-design.md).
- For AgentCanon's shared tool image and lifecycle, follow
  [CONTAINER_OPERATIONS.md](../../CONTAINER_OPERATIONS.md). Consumer project
  images and their tests remain project-owned.
- If a project's established contract requires a canonical image and full test
  command, validate that build-and-run route for changes that can affect it.
  Do not impose it on unrelated documentation or routine command execution.
- If the affected route needs GPU runtime evidence or optional admission, use
  [gpu-execution](gpu-execution.md).
- If the task replaces or removes an existing environment, use
  [environment-cleanup](environment-cleanup.md) for that selected lifecycle.
- A command inside an already running Dev Container belongs to
  [devcontainer-exec](devcontainer-exec.md), not environment redesign.

## Validation and closeout

Use the owning project's existing command and environment to check the changed
behavior. A documentation-only change needs documentation checks; dependency,
image, runtime, or CI changes need only the acceptance checks that cover their
affected contract. Preserve the project's execution permissions and rerun
limits. Keep failures separate from skipped or unavailable checks, and report
the result with its remaining scope.
