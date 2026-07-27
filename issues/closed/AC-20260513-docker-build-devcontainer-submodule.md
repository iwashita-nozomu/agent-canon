# Docker Build Devcontainer Submodule Checkout

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where Docker Build CI consumed a shared devcontainer symlink without checking out AgentCanon.
upstream design ../../documents/github-first-module-and-devcontainer-policy.md defines devcontainer ownership.
upstream implementation ../../tools/ci/check_github_workflows.py validates workflow checkout policy.
downstream implementation ../../tests/tools/test_check_github_workflows.py verifies Docker workflow checkout rules.
@dependency-end
-->

issue_id: AC-20260513-docker-build-devcontainer-submodule
status: resolved
source: ci
severity: S1
evidence: https://github.com/iwashita-nozomu/project_template/actions/runs/25843396500
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/246
affected_surfaces: .github/workflows/docker-build.yml, tools/ci/check_github_workflows.py, tests/tools/test_check_github_workflows.py, documents/github-first-module-and-devcontainer-policy.md
edit_scope: .github/workflows/docker-build.yml, tools/ci/check_github_workflows.py, tests/tools/test_check_github_workflows.py, documents/SHARED_RUNTIME_SURFACES.md, documents/github-first-module-and-devcontainer-policy.md, docker/README.md
required_action: Make Docker Build workflows check out the AgentCanon submodule before consuming shared `.devcontainer/` root views.
close_condition: Template Docker Build CI passes after the workflow uses the AgentCanon checkout helper, and the GitHub workflow checker rejects Docker workflows that omit it.
resolved_by: https://github.com/iwashita-nozomu/project_template/actions/runs/25843396500, GITHUB_WORKFLOWS=pass from `python3 tools/ci/check_github_workflows.py`
resolved_at: 2026-05-14
resolution_summary: Template Docker Build now runs `.github/scripts/checkout_agent_canon_submodule.sh` before `docker/check_build.sh`; the latest Docker Build workflow passed, and the GitHub workflow checker reports `GITHUB_WORKFLOWS=pass`.

## Finding

Template PR #3 made `.devcontainer/` an AgentCanon-owned shared root view, but
`.github/workflows/docker-build.yml` still used `actions/checkout` with
`submodules: false` and no explicit AgentCanon checkout helper. The Docker
smoke then mounted the repository and executed `.devcontainer/post-create.sh`,
which was a dangling symlink in the GitHub Actions checkout.

## Required Fix

- Treat Docker Build as AgentCanon-dependent whenever it consumes the shared
  `.devcontainer/` root view.
- Add `Checkout AgentCanon submodule` before `docker/check_build.sh` in the
  template Docker workflow.
- Remove the stale checker assumption that `docker-build.yml` is independent of
  AgentCanon.
