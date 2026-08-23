# Vendored Third-Party Skills

<!--
@dependency-start
contract reference
responsibility Documents third-party skill vendor contract.
upstream design ../README.md AgentCanon internal vendor ownership policy
downstream implementation manifest.toml records imported third-party skill metadata
downstream implementation ../../tools/agent_tools/vendor_skill_adapters.py validates and syncs runtime adapters
@dependency-end
-->

This directory stores third-party agent skills that are useful across
AgentCanon-derived repositories but are not AgentCanon-authored canonical
skills.

## Layout

Use one provider directory and one skill directory. For GitHub imports,
`provider` is the upstream GitHub owner or organization, not `agent-canon` and
not the template repository that happens to consume the skill:

```text
vendor/skills/<github-owner>/<skill-id>/SKILL.md
vendor/skills/<github-owner>/<skill-id>/LICENSE
vendor/skills/<github-owner>/<skill-id>/README.md
```

The vendored `SKILL.md` must keep valid runtime frontmatter:

```yaml
---
name: third-party-skill
description: Short description shown in skill discovery.
---
```

The frontmatter `name` must match the manifest `id` and the runtime adapter
directory name. If the upstream name conflicts with an AgentCanon canonical
skill, choose a non-conflicting upstream-compatible import name before enabling
the adapter.

## Manifest

Add one entry to `manifest.toml` for each imported skill:

```toml
[[skills]]
id = "third-party-skill"
provider = "upstream-owner"
source = "vendor/skills/upstream-owner/third-party-skill"
adapter = ".agents/skills/third-party-skill"
enabled = true
license = "MIT"
upstream = "https://github.com/upstream-owner/skill-repo"
revision = "commit-sha-or-release-tag"
```

For GitHub URLs, `provider` must match the URL owner or organization. If the
upstream repository name differs from the skill id, keep the skill id as the
adapter name and record the exact repository in `upstream`; the source path
still stays under `vendor/skills/<github-owner>/<skill-id>/`.

Run:

```bash
python3 tools/agent_tools/vendor_skill_adapters.py --sync
```

Then validate:

```bash
python3 tools/agent_tools/vendor_skill_adapters.py
python3 tools/agent_tools/check_agent_runtime_alignment.py
```

## Rules

- Do not copy third-party skill source directly into canonical
  `agents/skills/`.
- Do not clone a GitHub skill repository directly into `.agents/skills/`,
  `tools/`, `documents/`, or a template parent repository. Attach it under
  AgentCanon `vendor/skills/<github-owner>/<skill-id>/` and expose it through a
  manifest-backed adapter.
- Do not create a runtime adapter without a manifest entry.
- Do not enable a skill without upstream URL, revision, and license metadata.
- Do not edit vendored source to satisfy AgentCanon house style unless the
  change is explicitly part of the import review; prefer a small AgentCanon
  wrapper skill only when the upstream skill cannot be exposed as-is.
