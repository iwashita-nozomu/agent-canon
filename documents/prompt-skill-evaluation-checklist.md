<!--
@dependency-start
contract reference
responsibility Defines checklist and manifest format for skill, prompt, and workflow behavior evals.
upstream design ../agents/canonical/skills.md defines skill registry.
upstream design ../agents/canonical/CODEX_SUBAGENTS.md defines subagent routing.
downstream implementation ../evidence/agent-evals/issue_eval_manifest.toml registers issue-derived eval cases.
downstream implementation ../.github/ISSUE_TEMPLATE/eval-capture.yml captures new eval candidates.
downstream implementation ../.github/PULL_REQUEST_TEMPLATE.md requires eval evidence.
@dependency-end
-->

# Prompt And Skill Evaluation Checklist

Use this checklist when changing skills, subagent prompts, workflow prose, hook
messages, task routing, or closeout rules.

## Required Checks

1. Activation
   - The skill/subagent/tool activates for tasks that need it.
   - It stays quiet for tasks that do not need it.
1. Responsibility boundary
   - The role does not implement while acting as reviewer/designer/researcher.
   - Helper, public API, first-party library, workflow, and shared-canon changes
     require task authority.
1. Evidence and closeout
   - Required tool/check evidence is named.
   - Missing evidence is marked not applicable only with a reason.
1. Regression capture
   - The PR adds or updates an eval case, or states why the change is not evalable.

## Failure Taxonomy

- `scope-creep`: work expands beyond the user request.
- `helper-sprawl`: helper or wrapper code is added before owner/API evidence.
- `upstream-mutation`: vendor, external, or shared library is changed without authority.
- `api-surface-miss`: public API, exports, config, or examples were not traversed.
- `responsibility-boundary`: repo/module/document ownership was misread.
- `workflow-bypass`: defined skill, workflow, or tool route was skipped.
- `doc-drift`: stale, duplicate, or conflicting docs were left visible.
- `insufficient-evidence`: conclusion is not backed by required evidence.
- `wrong-artifact`: output format/path does not match the request.
- `non-reproducible-review`: review finding was not turned into a test or eval.

## Manifest Format

Issue-derived evals are registered in
`evidence/agent-evals/issue_eval_manifest.toml`. Each row records category, source
issue, protected behavior, expected route, forbidden route, oracle type, and
linked rule/tool/workflow.

Close an agent-behavior issue only after the eval is added, or after the issue
body/PR body records why an eval would not be meaningful.
