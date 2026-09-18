# GitHub Agent Entry Point
<!--
@dependency-start
contract reference
responsibility Provides only GitHub-subtree constraints and conditional routes.
upstream design ../documents/design/entrypoint-owner-map.md automatic reading boundary
upstream design ../templates/documents/github/README.md template source and target owner
@dependency-end
-->

This `.github/` overlay adds only GitHub Actions, templates, and automation rules.
Root instructions remain in force; do not reload them or the repository indexes.
Use `/plan` or a written plan before non-trivial changes in this subtree.

For template edits, read the matching source/target mapping in
[GitHub templates](../templates/documents/github/README.md); edit canonical sources,
not generated copies directly. For AgentCanon PR delivery, use the
[PR checklist](PULL_REQUEST_TEMPLATE.md) and selected
[update Skill](../agents/skills/agent-canon-update.md), not all GitHub documentation.
