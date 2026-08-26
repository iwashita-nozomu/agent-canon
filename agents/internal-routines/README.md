# Internal Agent Routines

<!--
@dependency-start
contract agent-runtime
responsibility Documents internal agent routines that are workflow-routed but are not public Codex skills.
upstream design ../skills/catalog.yaml enumerates public skill families
upstream design ../skills/README.md defines the public skill surface contract
downstream design ../canonical/CODEX_WORKFLOW.md routes internal review routines through workflow stages
downstream design chatgpt-codex-routing.md owns request modality before Codex workflow admission
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
| Request modality routing | `chatgpt-codex-routing.md` | root entrypoints before `$agent-orchestration` |
| Review routines | `code-review.md`, `critical-review.md`, `project-review.md`, `report-review.md`, `comprehensive-review.md` | `$change-review`, `$research-workflow`, `$comprehensive-development`, `$report-writing` |
| Academic review routines | `citation-evidence-review.md`, `logic-gap-review.md`, `notation-definition-review.md` | `$academic-writing`, `$paper-writing`, `$prose-reasoning-graph` |
| Docs review routines | `docs-completeness-review.md`, `docs-consistency-review.md` | `$document-canon-cleanup`, `$md-style-check` |
| Research routines | `experiment-change-loop.md`, `experiment-workflow.md`, `research-perspective-review.md` | `$experiment-lifecycle`, `$adaptive-improvement-loop`, `$research-workflow` |
| Runtime and validation adapters | `artifact-placement.md`, `codex-cli.md`, `static-check.md`, `static-validation.md`, `project-health.md`, `from_another_agent.md` | workflow stages, tool checks, and project review |
| Subagent startup routines | `subagent-startup.md` | `$subagent-bootstrap`, `route.py --area agents` |

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
