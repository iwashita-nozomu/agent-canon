# Skill and Tool Cooperation Sources

<!--
@dependency-start
contract reference
responsibility Records existing and external guidance considered for Skill/tool cooperation.
downstream design ../agents/skills/agent-orchestration.md owns the common cooperation procedure
@dependency-end
-->

## Existing owners

The source assessment used AgentCanon main
`eb0d3c277e4aa3c8ccada0b7bdef728a062523af` on 2026-10-25 JST.
[task-routing](../agents/skills/task-routing.md) selects owners,
[codex-task-workflow](../agents/skills/codex-task-workflow.md) composes existing
capabilities, and [agent-canon-bootstrap](../agents/skills/agent-canon-bootstrap.md)
owns the shared execution plane. [tool-finding-report](../agents/skills/tool-finding-report.md)
returns findings to their repair or reporting owner.
[Reuse feasibility support](../documents/conventions/software-engineering-principles.md#reuse-feasibility-support)
already owns composition from provider preconditions to the requested property.

The adopted procedure connects these owners through the actual tool contract,
lifecycle state, and returned evidence. Existing CLI/API argument and process
semantics remain authoritative. The retired operation/binding language and
mandatory command packet from [Issue #1233](https://github.com/iwashita-nozomu/agent-canon/issues/1233)
are not part of this procedure.

## MCP Builder design assessment, 2026-10-25

- Source: [Anthropic mcp-builder Skill](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/mcp-builder/SKILL.md).
- Revision observed: `dbd4588f9e1033efb41dad4bef2f7947c8993d44`;
  accessed 2026-10-25 JST.
- Locations: description and Overview; Phase 1.1; Phase 2.3 input/output schemas,
  descriptions, and error handling.
- Relevant guidance: tools should support the user's actual task, expose clear
  inputs and results, and provide errors useful for the next action.
- Selection: use as design context. Its workflow builds MCP servers; this task
  coordinates existing tools. Server implementation, dependencies, and its fixed
  evaluation procedure were not adopted. No external code or Skill text was copied.
- Limits: no MCP server, SDK integration, or effectiveness benchmark was run.

## Anthropic comparison, 2026-10-27

The installed `mcp-builder`, `webapp-testing` and `theme-factory` match official
commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, including their Apache-2.0
licenses and supporting files. Codex discovery returned all three enabled.
This comparison uses that snapshot and the public authoring guide below.

| Source | Comparison and adopted change |
| --- | --- |
| [Skill Creator](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/skill-creator/SKILL.md), overview, Writing Style and Improving the skill | Start from the current stage, explain reasons and remove instructions that add no useful work. The Updating Skills introduction repeated its operative cycle; keep procedure derivation in step 2. Reuse the existing empirical evaluation owner when behavior evidence is needed. |
| [MCP Builder](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/mcp-builder/SKILL.md), phases 1–4 | Pass the outcome, API references, constraints, acceptance and fixed choices to the selected design/implementation phases. Open choices return as proposals. Select phase 4 when tool-effectiveness evaluation is requested. Generic tool coordination retains its owner. |
| [Webapp Testing](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/webapp-testing/SKILL.md), decision tree and helper usage | Delegate requested interactions with an existing artifact or running URL and expected behavior; consume actual browser evidence. Static file validation and preview/serving authority remain separate. |
| [Theme Factory](https://github.com/anthropics/skills/blob/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/theme-factory/SKILL.md), usage and application | Reuse supplied theme choices and artifact constraints; otherwise follow its showcase/confirmation flow before application. Return palette/fonts to existing authoring. Keep theme assets with the provider and narrative/layout acceptance with slides. |

No universal help-first rule, extra wrapper or external catalog copy was added.
MCP Builder phase 4 specifies ten questions for tool-effectiveness evaluation;
that phase is selected for requests that include that evaluation. Generic Skill
improvement gains no fixed evaluation count/viewer. Selected providers retain
their native procedures for the selected scope. Shared reuse and native-interface
rules remain in ROOT_AGENTS and agent-orchestration; the improvement cycle
retains the required derivation.
Source consistency and discovery establish these connections, not improved
model behavior, token savings or live MCP/browser/deck acceptance.

## Using Superpowers

- Source: [Using Superpowers Skill](https://github.com/obra/superpowers/blob/2ce8aa15d05bd57213e6f746f953aafb7ded7a8b/skills/using-superpowers/SKILL.md).
- Revision observed: `2ce8aa15d05bd57213e6f746f953aafb7ded7a8b`;
  accessed 2026-10-25 JST.
- Locations: description, The Rule, and Skill Priority.
- Selection: not installed or imported. Its broad invocation threshold and
  process-first requirement conflict with AgentCanon's selected-owner reads and
  the user's preference for restrained orchestration. Existing routing remains
  the owner; no startup hook or universal Skill admission step was added.
- Limits: assessment of the source instructions, not a runtime comparison.

## Retrieval

The revision identifiers record the sources inspected; they are not installation
version pins. Source pages and raw text consulted:

- [MCP Builder main source](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/SKILL.md)
- [MCP Builder main raw text](https://raw.githubusercontent.com/anthropics/skills/main/skills/mcp-builder/SKILL.md)
- [MCP Builder inspected raw text](https://raw.githubusercontent.com/anthropics/skills/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/mcp-builder/SKILL.md)
- [Using Superpowers main source](https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md?plain=1)
- [Using Superpowers main raw text](https://raw.githubusercontent.com/obra/superpowers/main/skills/using-superpowers/SKILL.md)
- [Using Superpowers inspected raw text](https://raw.githubusercontent.com/obra/superpowers/2ce8aa15d05bd57213e6f746f953aafb7ded7a8b/skills/using-superpowers/SKILL.md)
