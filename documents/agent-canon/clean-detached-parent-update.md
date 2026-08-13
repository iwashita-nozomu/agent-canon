# Clean detached parent update boundary
<!--
@dependency-start
contract design
responsibility Defines when a detached AgentCanon submodule checkout is reconstructible parent-update state rather than conflicting local work.
upstream design agent-canon-update-route.md owns parent update publication and materialization order
downstream implementation ../../tools/agent_tools/attach_clean_detached_submodule.py attaches only clean detached-at-gitlink state
downstream implementation ../../tools/update_agent_canon.sh invokes the attachment before parent update planning
downstream implementation ../../tests/agent_tools/test_attach_clean_detached_submodule.py verifies blockers and diagnostic preservation
@dependency-end
-->

A standard recurse-submodules checkout may leave `vendor/agent-canon` detached at the exact commit recorded by the parent gitlink. That state is reconstructible when all of the following are true: the submodule worktree is clean, its `HEAD` equals the parent `HEAD:vendor/agent-canon` gitlink, and attaching the requested branch does not overwrite an existing divergent local branch.

The high-level parent update entrypoint may attach that exact state to the requested branch before planning. Detachment alone is therefore not a conflict signal. Dirty submodule state, a detached `HEAD` different from the parent pin, an existing divergent local branch, unresolved merge state, materialization collision, or divergent history remain blockers and must not be rewritten to make the update proceed.

Planning diagnostics are part of the public update contract. A nonzero `plan` result must be printed before the high-level entrypoint propagates its return code, so callers can distinguish the typed blocker rather than observing only a shell exit.
