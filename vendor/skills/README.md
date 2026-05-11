# Vendored Third-Party Skills

<!--
@dependency-start
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

Use one provider directory and one skill directory:

```text
vendor/skills/<provider>/<skill>/SKILL.md
vendor/skills/<provider>/<skill>/LICENSE
vendor/skills/<provider>/<skill>/README.md
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

Run:

```bash
python3 tools/agent_tools/vendor_skill_adapters.py --sync
python3 tools/docs/mirror_skill_shims.py --target .claude/skills --prune
```

Then validate:

```bash
python3 tools/agent_tools/vendor_skill_adapters.py
python3 tools/agent_tools/check_agent_runtime_alignment.py
```

## Rules

- Do not copy third-party skill source directly into canonical
  `agents/skills/`.
- Do not create a runtime adapter without a manifest entry.
- Do not enable a skill without upstream URL, revision, and license metadata.
- Do not edit vendored source to satisfy AgentCanon house style unless the
  change is explicitly part of the import review; prefer a small AgentCanon
  wrapper skill only when the upstream skill cannot be exposed as-is.
