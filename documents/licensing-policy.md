# Parent Repository Licensing Policy
<!--
@dependency-start
responsibility Documents the default parent-repository licensing surface seeded from AgentCanon.
upstream design ../LICENSE provides the default license text seed.
upstream design ./README.md documents parent-owned active-contract document surfaces.
downstream implementation ../tools/sync_agent_canon.sh seeds and checks parent-repository shared surface copies.
@dependency-end
-->

This file is the default licensing-policy seed for template or derived
repositories that consume AgentCanon.

The parent repository owns its root license and project-specific licensing
policy. Template and derived repositories may replace this file with a local
policy when they intentionally choose a different project license or need
project-specific licensing terms.

AgentCanon itself remains licensed under the Apache License 2.0 through
`vendor/agent-canon/LICENSE`. Root symlink views into AgentCanon retain that
AgentCanon license. Parent-owned code, experiments, project documents, Docker
runtime files, and local data remain under the parent repository license unless
they are explicitly AgentCanon shared views.

When changing this policy in a parent repository, keep the AgentCanon license
text available in `vendor/agent-canon/LICENSE` and avoid presenting
AgentCanon-owned shared surfaces as parent-owned code.
