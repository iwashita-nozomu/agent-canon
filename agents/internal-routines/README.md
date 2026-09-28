# Internal Agent Routines

<!--
@dependency-start
contract agent-runtime
responsibility Documents internal agent routines that are workflow-routed but are not public Codex skills.
upstream design ../skills/catalog.yaml enumerates public skill families
upstream design ../skills/README.md defines the public skill surface contract
downstream design ../canonical/CODEX_WORKFLOW.md routes internal review routines through workflow stages
downstream design chatgpt-codex-routing.md owns request modality before Codex workflow admission
downstream design incremental-code-change.md connects opt-in coverage traversal and incremental repair
downstream design verification-result-structuring.md structures verification results before output
@dependency-end
-->

This directory contains workflow-routed internal review and compatibility
routines. These files are intentionally outside `agents/skills/` because they
do not have public `.codex/personal/skills/*/SKILL.md` discovery shims.

Public skill instructions live in `agents/skills/`, are listed in
`agents/skills/catalog.yaml`, and have matching `.codex/personal/skills/<skill>/SKILL.md`
shims. Internal routines are called by workflow stages, subagent roles, public
skills, or root entrypoints.

## Universal design correspondence

- [設計・実装対応ルート](design-implementation-correspondence.md)
  - repository-changing implementation の前に owning design を read し、clause fingerprint、handoff、forward/reverse review coverage、design drift block を共通化します。

Runtime-internal Codex skill shims, when a shim is needed for agent runtime
activation, use `.codex/personal/skills/_<name>/SKILL.md`. The leading underscore marks
the shim as private; its human-facing owner remains the workflow, role, public
skill, entrypoint, or routine that calls it.

## Routine Groups

| Group | Files | Public Route |
| ----- | ----- | ------------ |
| Verification result structuring | [verification-result-structuring.md](verification-result-structuring.md) | Chat/handoff delivery, `$report-writing`, `$pr-processing`, and connected work before result output |
| Request modality routing | [chatgpt-codex-routing.md](chatgpt-codex-routing.md) | root entrypoints before `$agent-orchestration` |
| GitHub-connected work | [github-connected-work.md](github-connected-work.md) | `$pr-processing` when current-session GitHub transport is available |
| Incremental code change | [incremental-code-change.md](incremental-code-change.md) | `$code-cleanup` when coverage traversal or in-task token-waste repair is requested |
| Review routines | [critical-review.md](critical-review.md), [project-review.md](project-review.md), [report-review.md](report-review.md), [comprehensive-review.md](comprehensive-review.md) | [responsibility-cleanup](../skills/responsibility-cleanup.md), research workflow validation, and the selected project review |
| Academic review routines | [citation-evidence-review.md](citation-evidence-review.md), [logic-gap-review.md](logic-gap-review.md), [notation-definition-review.md](notation-definition-review.md) | `$academic-writing`, `$paper-writing`, `$prose-reasoning-graph` |
| Docs review routines | [docs-completeness-review.md](docs-completeness-review.md), [docs-consistency-review.md](docs-consistency-review.md) | [long-form-writing](../skills/long-form-writing.md) and the selected document review |
| Research routines | [experiment-change-loop.md](experiment-change-loop.md), [research-perspective-review.md](research-perspective-review.md) | `$experiment-lifecycle`, `$adaptive-improvement-loop`, `$research-workflow` |
| Validation and project health | [static-check.md](static-check.md), [project-health.md](project-health.md) | selected validation profiles and [project-review](project-review.md) |
| GitHub status | [github-status-lifecycle.md](github-status-lifecycle.md) | [pr-processing](../skills/pr-processing.md) when Issue status reconciliation is requested |
| Subagent startup routines | [subagent-startup.md](subagent-startup.md) | `$subagent-bootstrap`, `route.py --area agents` |

Artifact placement is owned directly by [ARTIFACT_PLACEMENT.md](../canonical/ARTIFACT_PLACEMENT.md).
For Codex entry and task continuation, use [repo-onboarding](../skills/repo-onboarding.md);
its Issue/PR handoff is the task-state source, not a separate global TODO note.
Diff review uses [change-review](../skills/change-review.md), and a single experiment
uses [experiment-lifecycle](../skills/experiment-lifecycle.md).

## Contract

- Add a new public skill under `agents/skills/` only with a catalog entry and a
  matching `.codex/personal/skills/<skill>/SKILL.md` shim.
- Keep workflow-only routines in this directory.
- Keep runtime-internal shims under `.codex/personal/skills/_<name>/SKILL.md` and route
  their human-facing explanation through the owner routine, entrypoint, or
  public skill.
- Promote an internal routine to public skill by moving it into
  `agents/skills/`, adding a catalog entry, adding a shim, and updating runtime
  alignment evidence in the same change.
