<!--
@dependency-start
contract workflow
responsibility Defines the target area for workflow-owned AgentCanon helper tools.
upstream design ../../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md internal tool placement policy
downstream implementation ../../agent_tools/tool_catalog.py validates workflow-helper placement
@dependency-end
-->

# Workflow Helpers

Use this directory for task-start, closeout, routing, run-bundle, and workflow
gate helpers that are primarily called by AgentCanon workflows. Keep user-facing
wrappers outside this directory.
