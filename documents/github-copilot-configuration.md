# GitHub Copilot Configuration
<!--
@dependency-start
responsibility Documents GitHub Copilot configuration surfaces and AgentCanon placement rules.
upstream design ../.github/instructions/pr-processing.instructions.md Copilot PR processing instructions
upstream design ../.github/agents/pr-maintainer.md Copilot PR maintainer custom agent
upstream design ../agents/workflows/github-copilot-workflow.md Copilot workflow routing
downstream implementation ../tools/ci/check_github_workflows.py validates Copilot configuration coverage
downstream implementation ../tools/sync_agent_canon.sh exposes this document as a shared root view
downstream design ../.github/copilot-instructions.md Copilot repository instruction entrypoint consumes this catalog
@dependency-end
-->

This catalog maps GitHub Copilot configuration surfaces to AgentCanon source
paths and template / derived repository root paths. Treat it as the routing
guide before changing Copilot instructions, PR templates, custom agents, MCP
configuration, or Copilot setup workflows.

References checked on 2026-05-08:

- GitHub repository custom instructions:
  <https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions>
- Custom instruction support matrix:
  <https://docs.github.com/en/copilot/reference/custom-instructions-support>
- GitHub Copilot CLI customization overview:
  <https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/overview>
- GitHub Copilot custom agents:
  <https://docs.github.com/en/copilot/concepts/agents/copilot-cli/about-custom-agents>
- Custom agents configuration reference:
  <https://docs.github.com/en/enterprise-cloud@latest/copilot/reference/custom-agents-configuration>
- Copilot cloud agent environment setup:
  <https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/customize-the-agent-environment>
- MCP and Copilot cloud agent:
  <https://docs.github.com/en/copilot/concepts/agents/cloud-agent/mcp-and-cloud-agent>
- Copilot cloud agent MCP setup:
  <https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/extend-cloud-agent-with-mcp>

## Configuration Catalog

| GitHub Copilot item | GitHub-recognized placement | AgentCanon source | Template / derived root behavior | AgentCanon policy |
| --- | --- | --- | --- | --- |
| Repository-wide custom instructions | `.github/copilot-instructions.md` | `.github/copilot-instructions.md` | symlink view to `vendor/agent-canon/.github/copilot-instructions.md` | Keep thin. Route to `AGENTS.md`, this catalog, PR processing instructions, workflow docs, and PR templates. |
| Path-specific custom instructions | `.github/instructions/**/*.instructions.md` with `applyTo` frontmatter | `.github/instructions/pr-processing.instructions.md` | symlink view to `vendor/agent-canon/.github/instructions/` | Use for PR-wide triage and check-failure handling. Preserve `applyTo: "**"` when the instruction must cover all PR paths. |
| Agent instructions | `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md` depending on client support | `ROOT_AGENTS.md`, `CLAUDE.md` | `AGENTS.md` and `CLAUDE.md` symlink views | Put durable cross-runtime rules here. Use Plan mode before non-trivial repo-changing work when the runtime supports it. |
| GitHub-scoped agent entrypoint | `.github/AGENTS.md` | `.github/AGENTS.md` | symlink view | Keep a short index for GitHub-hosted agent contexts and PR template routing. |
| Custom agent profiles | `.github/agents/*.md` with YAML frontmatter | `.github/agents/pr-maintainer.md` | symlink view to `vendor/agent-canon/.github/agents/` | Use `description:` frontmatter and a narrow prompt. Keep PR maintenance read/triage focused unless explicitly assigned implementation work. |
| Custom agent tools | `tools:` YAML property in an agent profile | Optional in `.github/agents/*.md` | inherited through symlink view | Omit `tools` to allow default tools only when that is intentional; otherwise allowlist role-appropriate tools. |
| Custom agent MCP servers | `mcp-servers:` YAML property in an agent profile | Optional in `.github/agents/*.md` | inherited through symlink view | Allow only necessary tools. Secrets must come from each repository's Copilot environment, not from AgentCanon text. |
| Repository MCP for Copilot cloud agent | GitHub repository settings, Copilot > Cloud agent MCP JSON | documented here; no checked-in secret-bearing config | template / derived repo setting, not synced by AgentCanon | Use repository-admin configuration. Review third-party tools before enabling them because Copilot can use configured tools autonomously. |
| Project-level Copilot CLI MCP | `.mcp.json` or `.github/mcp.json` for Copilot CLI | no default shared file | repo-local unless explicitly added to AgentCanon policy | Keep repo-specific server endpoints out of shared canon unless they are generic, non-secret, and reusable. |
| Copilot cloud agent setup workflow | `.github/workflows/copilot-setup-steps.yml`, job name `copilot-setup-steps` | no default shared workflow | template / derived repo-local unless a shared setup workflow is added later | Use only for deterministic dependency/tool setup. Validate in PR and keep permissions minimal. |
| Copilot environment variables and secrets | repository environment named `copilot` | documented only | configured per GitHub repository | Never store secret values in AgentCanon. Use names such as `AGENT_CANON_REPO_TOKEN`, `AGENT_CANON_REPO_SSH_KEY`, and `COPILOT_MCP_*` in documentation/checks only. |
| Copilot CLI user settings | `~/.copilot/settings.json`, `~/.copilot/copilot-instructions.md`, `~/.copilot/instructions/`, `~/.copilot/agents/`, `~/.copilot/skills/`, `~/.copilot/hooks/` | not an AgentCanon source surface | user-local | Mention only when diagnosing CLI behavior. Do not encode user-local settings as repo policy. |
| Copilot PR templates | GitHub PR template files under `.github/` | `.github/PULL_REQUEST_TEMPLATE.md` and `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` | standalone template is not synced; template AgentCanon checklist is a synced root copy | Keep standalone AgentCanon and template / derived AgentCanon-pin PR paths separate. |

## Repository Separation

AgentCanon and the project template are separate repositories. The phrase
standalone AgentCanon repository means the upstream `agent-canon` GitHub
repository that owns the shared canon source tree.

- Standalone AgentCanon source changes land through the AgentCanon repository
  and use `.github/PULL_REQUEST_TEMPLATE.md` from the AgentCanon tree.
- Template / derived project PRs that update `vendor/agent-canon` use
  `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` from the template root.
- The template root copy of `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` is
  generated from `vendor/agent-canon/.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
  by `bash tools/sync_agent_canon.sh link-root`.
- The standalone `.github/PULL_REQUEST_TEMPLATE.md` is AgentCanon-only and must
  not be copied to the template root by AgentCanon sync.

When a template task discovers a shared AgentCanon defect, open or reference the
AgentCanon source PR first, merge or identify the AgentCanon commit, then update
the template `vendor/agent-canon` pin and root shared views.

## Plan Mode Requirement

Use Plan mode before non-trivial Copilot, GitHub Actions, PR-template,
AgentCanon-sync, or multi-file runtime-surface changes.

- Codex uses `/plan` when the runtime exposes it.
- If the current GitHub Copilot surface does not expose an explicit Plan mode,
  write the plan in the issue, PR comment, PR body, or working note before
  editing.
- A plan is not closeout evidence. After implementation, still provide command
  output, PR checklist evidence, AgentCanon SHA/pin evidence, and shared-surface
  sync evidence.

## PR Template Routing

Use this routing when building or reviewing pull request templates:

| PR context | Template file | Required evidence |
| --- | --- | --- |
| Standalone AgentCanon repository PR | `.github/PULL_REQUEST_TEMPLATE.md` in AgentCanon | validation output, shared-surface impact, Copilot Configuration Impact when relevant, Plan Mode Evidence, expected template submodule SHA when propagation is needed |
| Template / derived PR that changes `vendor/agent-canon/` or the pin | `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` in the template root | AgentCanon source PR/commit, template PR URL, `make agent-canon-ensure-latest`, `bash tools/sync_agent_canon.sh link-root`, `bash tools/sync_agent_canon.sh check`, template submodule SHA |
| Template / derived project-local PR | template root `.github/PULL_REQUEST_TEMPLATE.md` | project validation, dependency review, AgentCanon Evidence only if shared surfaces or pins changed |

PR template routing is not PR mutation authority. Agents may inspect PR state,
create/update PRs, push owned branches, and add evidence comments as part of
the workflow. Merge, close, ready-for-review, reviewer request, review
dismissal, auto-merge, branch deletion, and check bypass require explicit
current-task user authorization or a tracked maintainer policy granting that
exact action.

## Validation

Run the GitHub/Copilot convention checker after changing any surface listed in
this catalog:

```bash
python3 tools/ci/check_github_workflows.py
```

For template / derived repositories, also run:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
make agent-canon-pr-check
```
