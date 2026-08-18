---
name: _chatgpt-codex-routing
description: "Runtime-internal skill that decides whether a request closes in ChatGPT or requires Codex workspace execution, using explicit monotone execution facts rather than task complexity."
---

<!--
@dependency-start
contract skill
responsibility Exposes deterministic ChatGPT-versus-Codex request routing as a private runtime skill.
upstream design ../../../agents/internal-routines/chatgpt-codex-routing.md canonical fact model, decision relation, conflict policy, and handoff owner
upstream implementation ../../../tools/agent_tools/chatgpt_codex_routing.py deterministic packet generator
@dependency-end
-->

# _chatgpt-codex-routing

## Canonical Routine

Canonical routing and policy:
`agents/internal-routines/chatgpt-codex-routing.md`.

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill _chatgpt-codex-routing --format text`
<!-- skill-tool-commands:end -->

## Invocation Boundary

1. Invoke before public Codex workflow or skill selection.
2. Extract only the canonical boolean execution facts and explicit chat-only constraint.
3. Do not use complexity, estimated effort, task length, file count, or agent count.
4. Close `route=chatgpt` in conversation without repository execution.
5. Hand only `route=codex` packets to `agent-orchestration` with concrete
   `codex_scope` and `validation_oracle`.
6. Treat `explicit_chat_only_conflict` as advisory-only; do not mutate the
   workspace or claim execution verification.

This private skill does not select a Codex workflow, implementation owner,
public skill, review role, subagent, branch strategy, or validation profile.
