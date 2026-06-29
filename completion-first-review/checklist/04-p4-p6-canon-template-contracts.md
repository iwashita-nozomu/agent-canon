# P4-P6 Canon, Template, And Contract Checklist
<!--
@dependency-start
contract reference
responsibility Defines surface ownership, workflow/skill contract, and template propagation checks for the completion-first review.
upstream design ../README.md completion-first review index
upstream design ../explanation/01-priority-layers.md priority layer explanation
upstream design ../../README.md AgentCanon source tree overview
upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared runtime surface policy
@dependency-end
-->

## Reader Map

Use this checklist after P-1 through P3 have established completion judgment,
mechanical evidence, MCP status, and self-growth repair. Read P4 for surface
ownership and AgentCanon sync, P5 for workflow and skill contracts, and P6 for
template bootstrap, Docker, CI, and PR evidence. The done condition defines
when shared-canon propagation and contract checks are ready for later layers.

## P4: surface ownership and AgentCanon sync

### [ ] P4-001: changed path surface classification

- Target: changed files in every repo-changing task.
- Problem: root views, synced copies, AgentCanon source, and repo-local surfaces can be confused.
- Action: produce `surface_classification.json`.
- Acceptance: `unknown` surfaces fail strict completion.

### [ ] P4-002: reject root view direct edits

- Target: root symlink views such as `agents/`, `.agents/`, `tools/`, `mcp/` in Template/derived repos.
- Problem: root view can be edited instead of source.
- Action: classify `root_symlink_view` and require source edit route.
- Acceptance: direct root view edit fails unless explicitly allowed by profile.

### [ ] P4-003: synced-copy source hash

- Target: root copied surfaces such as GitHub workflow copies.
- Problem: root copy can drift from AgentCanon source.
- Action: record source path and source hash.
- Acceptance: hash mismatch fails strict/release completion.

### [ ] P4-004: submodule dirty gate

- Target: `vendor/agent-canon` in Template/derived repos.
- Problem: shared canon edits can remain dirty inside submodule.
- Action: strict and self-growth profiles require submodule clean or committed evidence.
- Acceptance: dirty submodule without propagation plan fails.

### [ ] P4-005: remote status artifact

- Target: AgentCanon source, Template, local bare mirrors, proposal branches.
- Problem: GitHub main, local mirror, proposal branch, and submodule pin can be conflated.
- Action: generate `remote_status.md`.
- Acceptance: completion report shows canonical source SHA and pin SHA separately.

### [ ] P4-006: AgentCanon source PR evidence

- Target: shared canon changes.
- Problem: shared changes can be handled only in Template PRs.
- Action: require upstream AgentCanon PR/proposal evidence before Template pin update.
- Acceptance: shared canon change without upstream route fails release/strict completion.

## P5: workflow and skill contracts

### [ ] P5-001: workflow contract blocks

- Target: `agents/workflows/*.md`.
- Problem: workflows are mostly prose and regex presence checks.
- Action: add machine-readable `workflow_contract` blocks.
- Acceptance: required artifacts, commands, reviewers, state transitions, and forbidden shortcuts are parseable.

### [ ] P5-002: skill contract blocks

- Target: `agents/skills/*.md` and `.agents/skills/*/SKILL.md`.
- Problem: skill selection can be over-broad or cosmetic.
- Action: add `skill_contract` blocks with use, do-not-use, escalation, and artifacts.
- Acceptance: public skills without do-not-use or escalation policy fail.

### [ ] P5-003: human doc and shim coverage

- Target: human-facing skill docs and discovery shims.
- Problem: human doc can contain rules absent from shims used by runtime discovery.
- Action: check critical concept coverage between human doc and shim.
- Acceptance: critical missing concept fails skill surface validation.

### [ ] P5-004: overlay workflow classifier

- Target: routing decisions.
- Problem: required overlays such as hypothesis validation can be forgotten.
- Action: classify overlay candidates from request shape and changed paths.
- Acceptance: missing overlay requires explicit rejected reason.

### [ ] P5-005: skill invocation evidence

- Target: behavior events.
- Problem: skill invocation can be a declaration only.
- Action: require `skill_name`, `source_path`, `read_before_work`, and `used_in_artifact`.
- Acceptance: declaration-only skill event fails.

### [ ] P5-006: token-efficient non-waivable gates

- Target: token-efficient workflow and runtime profiles.
- Problem: token saving can be used to skip correctness gates.
- Action: contractually state that token profile cannot weaken closeout profile.
- Acceptance: token-lite with missing required evidence fails.

## P6: Template bootstrap, Docker, CI, and PR evidence

### [ ] P6-001: bootstrap replacement manifest

- Target: Template init scripts.
- Problem: inline replacement maps are hard to audit.
- Action: introduce bootstrap replacement manifest and unresolved token scan.
- Acceptance: unresolved template tokens fail bootstrap validation.

### [ ] P6-002: dirty preflight policy

- Target: repository start wrapper.
- Problem: dirty state can block latest check without clear route.
- Action: distinguish repo-local dirty from shared-canon dirty.
- Acceptance: dirty shared-canon state routes to AgentCanon PR/proposal, not silent pin refresh.

### [ ] P6-003: Docker profile split

- Target: Docker runtime.
- Problem: CUDA default is heavy and not universally appropriate.
- Action: split CPU default and CUDA optional profiles.
- Acceptance: CPU smoke works without GPU.

### [ ] P6-004: dynamic devcontainer secret mounts

- Target: `.devcontainer` generation.
- Problem: fixed secret mounts can fail or over-share.
- Action: mount SSH/GH/Codex state only when present and trusted.
- Acceptance: empty `SSH_AUTH_SOCK` does not break compose generation.

### [ ] P6-005: PR evidence matrix

- Target: PR templates.
- Problem: checkboxes drift from closeout requirements.
- Action: generate PR evidence matrix from closeout profile.
- Acceptance: profile-required evidence cannot be marked not affected without scope reason.

### [ ] P6-006: executable audit profiles

- Target: audit checklist.
- Problem: huge audit checklist is difficult to run consistently.
- Action: create quick, strict, self-growth, release audit profiles.
- Acceptance: audit reports are command-backed and profile-specific.

## P4-P6 done condition

- [ ] Changed paths have owners.
- [ ] Shared canon changes propagate through the correct route.
- [ ] Workflows and skills expose contracts.
- [ ] Template-derived repos can inherit completion-first checks.
