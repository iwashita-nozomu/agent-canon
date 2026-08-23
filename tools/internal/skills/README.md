<!--
@dependency-start
contract tool
responsibility Defines the target area for skill-owned AgentCanon helper tools.
upstream design ../../catalog.yaml structured tool audience and placement catalog
upstream design ../README.md internal tool placement policy
downstream implementation ../../agent_tools/tool_catalog.py validates skill-helper placement
@dependency-end
-->

# Skill Helpers

Use this directory for helpers whose primary caller is a skill packet rather
than a repository user. A helper may be listed in `tools/catalog.yaml` with
`audience: skill` and `placement: skill_helper` before its file is physically
moved here.
