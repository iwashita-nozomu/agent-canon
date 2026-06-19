# AgentCanon Vendor

<!--
@dependency-start
contract reference
responsibility Documents AgentCanon internal vendor ownership policy.
upstream design ../README.md AgentCanon source tree overview
downstream design skills/README.md third-party skill vendor contract
downstream implementation ../tools/agent_tools/vendor_skill_adapters.py validates vendored skill adapters
@dependency-end
-->

`vendor/` inside AgentCanon is for external agent-facing assets that AgentCanon
wants to expose without pretending to own their upstream design.

This is different from a template or derived repository's root
`vendor/agent-canon/` submodule. The outer `vendor/agent-canon/` path is the
AgentCanon pin. This internal `vendor/` directory is part of AgentCanon itself.

## Ownership

- External skill source stays under `vendor/skills/<provider>/<skill>/`.
- For GitHub imports, `provider` is the upstream GitHub owner or
  organization, even when that repository is maintained by someone outside the
  AgentCanon project.
- A GitHub-sourced external repository must attach below
  `vendor/<asset-class>/<github-owner>/<import-id>/`. Do not clone or copy it
  directly into `.agents/`, `agents/`, `tools/`, `mcp/`, `documents/`, or a
  template parent repository root.
- Runtime exposure goes through `.agents/skills/<skill>` adapter symlinks.
- `.agents/skills/` remains the discovery surface; it is not the place to copy
  third-party source by hand.
- Every enabled third-party skill must be listed in
  `vendor/skills/manifest.toml` with provider, upstream URL, revision, and
  license metadata.
- Canonical AgentCanon skills stay in `agents/skills/` and `.agents/skills/`.
  Third-party skills must not reuse a canonical skill id.

## Validation

Use the adapter tool before committing a third-party skill import. It rejects
GitHub skill sources whose `provider`, `upstream` owner, and
`vendor/skills/<provider>/<skill>/` source path do not agree.

```bash
python3 tools/agent_tools/vendor_skill_adapters.py --sync
python3 tools/agent_tools/vendor_skill_adapters.py
python3 tools/agent_tools/check_agent_runtime_alignment.py
```

The sync command creates missing adapter symlinks only for manifest entries
marked `enabled = true`; it does not delete disabled entries or overwrite
unmanaged files.
