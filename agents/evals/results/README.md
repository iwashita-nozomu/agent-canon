# Legacy Eval Result Notices

<!--
@dependency-start
responsibility Documents the legacy AgentCanon eval result source-tree notice surface.
upstream design ../README.md eval directory contract
upstream design ../../../documents/runtime-log-archive.md external runtime log archive contract
upstream design ../../../documents/runtime-log-archive-migration.md legacy in-tree result migration procedure
downstream design hook-runs/README.md hook result naming convention
downstream implementation ../../../tools/agent_tools/runtime_log_paths.py resolves active eval result paths
downstream implementation ../../../tools/agent_tools/runtime_log_archive_git.py imports legacy eval reports
downstream implementation ../../../tools/agent_tools/eval_accumulation_check.py validates accumulated result evidence
downstream implementation ../../../tools/agent_tools/generate_agent_runtime_dashboard.py summarizes accumulated result evidence
@dependency-end
-->

This directory is no longer the normal storage location for accumulated
AgentCanon eval reports. AgentCanon source keeps this README and the
`hook-runs/README.md` legacy schema notice only.

Normal accumulated eval reports belong in the external log archive documented
in `documents/runtime-log-archive.md`:

```text
.agent-canon/log-archive/eval-results/<family>/<eval-run-id>-<status>*.md
```

Historical in-tree reports are imported into:

```text
.agent-canon/log-archive/eval-results/legacy-import/<family>/
```

Result families currently read by the tools are `skill-workflow-prompt`,
`local-llm-responsibility`, `workflow-selection`, and `report-quality`.
Tooling reads the mounted archive first, then the legacy import path, then this
old source-tree path only as a fallback for temporary tests or unmigrated
checkouts.

If this directory grows new report files, migrate them instead of committing
them to AgentCanon source:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py import-eval-results --delete-source
python3 tools/agent_tools/runtime_log_archive_git.py push \
  --message "Import legacy AgentCanon eval results"
```

The `log_archive_mount_warning.py` hook warns, without blocking, when
`.agent-canon/log-archive/` is not mounted as a Git clone. The warning is a
signal to run `runtime_log_archive_git.py ensure` before accumulating hook or
eval logs.

Validate the accumulated evidence before using it as workflow feedback:

```bash
python3 tools/agent_tools/eval_accumulation_check.py --root .
```

The checker is structural. It accepts legacy readable reports, but namespaced
new hook logs must carry the required fields documented under `hook-runs/`.
Raw hook and eval logs stay append-only in the archive after a prompt, skill,
workflow, or tool repair. Do not delete archive history to make a new report
look green. Tools that turn accumulated evidence into routing guidance use the
latest Git commit time of the affected source paths as the analysis cutover:
pre-cutover skill routing signals are archived out of current gap math while
remaining available as raw chronology.
For a human-readable view, generate the runtime dashboard. It shows not only
aggregate counts, but also Mermaid evidence flow, per-skill eval failure rates,
workflow attribution for hook firing, prompt/tool-selection evidence, token
comparison coverage, and explicit missing-evidence signals. In GitHub Actions,
the canonical published dashboard is the standalone AgentCanon repository
workflow summary and artifact, not a template or derived repository workflow
copy:

```bash
python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
  --root . \
  --out reports/agent-runtime-dashboard/agent-runtime-dashboard.md
```
