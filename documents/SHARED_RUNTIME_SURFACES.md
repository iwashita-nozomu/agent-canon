# Shared Runtime Surfaces

<!--
@dependency-start
responsibility Documents Shared Runtime Surfaces for this repository.
upstream design ../tools/sync_agent_canon.sh shared surface link specification
upstream design ./agent-canon-subtree-migration.md vendoring ownership model
downstream implementation ../tools/sync_agent_canon.sh enforces this surface list
downstream design ./algorithm-implementation-boundary.md listed shared algorithm boundary policy surface
downstream design ./object-oriented-design.md listed shared coding policy surface
downstream design ./github-copilot-configuration.md listed shared Copilot configuration surface
@dependency-end
-->

この文書は、`vendor/agent-canon/` submodule pin を source of truth とする runtime surface をまとめます。
template root と派生 repo root では同じ path を使い続けますが、shared canon の正本は vendor 側にあります。
legacy subtree repo は移行完了まで互換 path として扱います。通常運用、PR checklist、clone 手順では submodule pin を既定にします。
`goal.md` は repo 固有の実行状態なので shared runtime surface ではありません。
root `goal.md` を `vendor/agent-canon/goal.md` へ symlink してはいけません。
`tools/sync_agent_canon.sh link-root` は既存の shared `goal.md` symlink を repo-local placeholder に変換します。
`.gitmodules` は template-local runtime contract です。AgentCanon URL、branch、checkout behavior に関わる変更では必ず review し、shared surface には同期しません。

## Surface Types

### symlink view

root では次を symlink view として扱います。

- `AGENTS.md`
- `agents/`
- `.agents/`
- `.claude/`
- `CLAUDE.md`
- `.github/AGENTS.md`
- `.github/copilot-instructions.md`
- `.github/instructions/`
- `.github/agents/`
- `.codex/config.toml`
- `.codex/README.md`
- `.codex/agents`
- `mcp/`
- `documents/BRANCH_SCOPE.md`
- `documents/AGENTS_COORDINATION.md`
- `documents/DOCSTRING_GUIDE.md`
- `documents/FILE_CHECKLIST_OPERATIONS.md`
- `documents/README.md`
- `documents/algorithm-implementation-boundary.md`
- `documents/object-oriented-design.md`
- `documents/dependency-manifest-design.md`
- `documents/notes-lifecycle.md`
- `documents/REVIEW_PROCESS.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/SKILL_IMPLEMENTATION_GUIDE.md`
- `documents/TROUBLESHOOTING.md`
- `documents/WORKTREE_SCOPE_TEMPLATE.md`
- `documents/agent-canon-github-remote.md`
- `documents/agent-canon-subtree-migration.md`
- `documents/github-copilot-configuration.md`
- `documents/template-github-remote.md`
- `documents/coding-conventions-cpp.md`
- `documents/coding-conventions-experiments.md`
- `documents/coding-conventions-house-style.md`
- `documents/coding-conventions-logging.md`
- `documents/coding-conventions-project.md`
- `documents/coding-conventions-python.md`
- `documents/coding-conventions-reviews.md`
- `documents/coding-conventions-testing.md`
- `documents/experiment-critical-review.md`
- `documents/experiment-registry.md`
- `documents/experiment-report-style.md`
- `documents/experiment_runner.md`
- `documents/cpp-build-layout.md`
- `documents/linux-wsl-host-requirements.md`
- `documents/remote-execution-repo-contract.md`
- `documents/server-host-contract.md`
- `documents/template-bootstrap.md`
- `documents/worktree-lifecycle.md`
- `documents/conventions/README.md`
- `documents/conventions/common/01_principles.md`
- `documents/conventions/common/02_naming.md`
- `documents/conventions/common/03_comments.md`
- `documents/conventions/common/04_operators.md`
- `documents/conventions/common/05_docs.md`
- `documents/conventions/python/01_scope.md`
- `documents/conventions/python/04_type_annotations.md`
- `documents/conventions/python/06_comments.md`
- `documents/conventions/python/07_type_checker.md`
- `documents/conventions/python/09_file_roles.md`
- `documents/conventions/python/11_naming.md`
- `documents/conventions/python/15_jax_rules.md`
- `documents/conventions/python/20_benchmark_policy.md`
- `documents/conventions/python/30_experiment_directory_structure.md`
- `documents/design/README.md`
- `documents/design/protocols.md`
- `documents/templates/README.md`
- `documents/templates/remote_execution_repo.template.toml`
- `documents/templates/remote_execution_target.template.toml`
- `documents/templates/server_host_inventory.template.md`
- `documents/templates/server_runtime_layout.template.toml`
- `documents/tools/README.md`
- `documents/tools/tool-docs.toml`
- `documents/tools/oop/python/readability.md`
- `documents/tools/oop/python/rule_inventory.md`
- `documents/tools/oop/cpp/readability.md`
- `documents/tools/oop/cpp/rule_inventory.md`
- `memory/README.md`
- `memory/USER_PREFERENCES.md`
- `memory/AGENT_PHILOSOPHY.md`
- `notes/experiments/README.md`
- `notes/experiments/REPORT_TEMPLATE.md`
- `notes/experiments/results/README.md`
- `notes/branches/README.md`
- `notes/branches/BRANCH_NOTE_TEMPLATE.md`
- `notes/failures/README.md`
- `notes/failures/FAILURE_NOTE_TEMPLATE.md`
- `notes/github-mirror-procedure.md`
- `notes/guardrails/README.md`
- `notes/guardrails/engineering_avoidances.md`
- `notes/knowledge/README.md`
- `notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md`
- `notes/knowledge/benchmark_levels_analysis.md`
- `notes/knowledge/benchmark_vs_experiment.md`
- `notes/knowledge/environment_setup.md`
- `notes/knowledge/experiment_directory_planning.md`
- `notes/knowledge/experiment_operations.md`
- `notes/knowledge/git_mirroring.md`
- `notes/knowledge/literature_intake.md`
- `notes/knowledge/path_resolution.md`
- `notes/knowledge/pyright_operations.md`
- `notes/themes/README.md`
- `notes/themes/THEME_NOTE_TEMPLATE.md`
- `notes/themes/from_another_agent.md`
- `notes/worktrees/README.md`
- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- `tests/agent_tools/__init__.py`
- `tests/agent_tools/test_check_agent_runtime_alignment.py`
- `tests/agent_tools/test_analyze_refactor_surface.py`
- `tests/agent_tools/test_tool_catalog.py`
- `tests/agent_tools/test_tool_drift.py`
- `tests/agent_tools/test_oop_rule_inventory.py`
- `tests/agent_tools/test_check_mcp_inventory.py`
- `tests/agent_tools/test_work_log.py`
- `tests/agent_tools/test_smoke_test_research_perspective_pack.py`
- `tests/tools/test_check_merge_structure.py`
- `tests/tools/test_check_markdown_math.py`
- `tests/tools/test_container_config.py`
- `tests/tools/test_mirror_skill_shims.py`
- `tests/tools/test_check_github_workflows.py`
- `tests/tools/test_run_managed_experiment.py`
- `tools/`

### synced root copy

次は root 側に regular file を残しますが、正本は vendor 側です。

- `.github/workflows/agent-coordination.yml`
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`
- `.github/scripts/checkout_agent_canon_submodule.sh`

| root path | AgentCanon source | verification |
| --- | --- | --- |
| `.github/workflows/agent-coordination.yml` | `vendor/agent-canon/.github/workflows/agent-coordination.yml` | `bash tools/sync_agent_canon.sh check` |
| `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` | `vendor/agent-canon/.github/PULL_REQUEST_TEMPLATE/agent_canon.md` | `bash tools/sync_agent_canon.sh check` |
| `.github/scripts/checkout_agent_canon_submodule.sh` | `vendor/agent-canon/tools/ci/checkout_agent_canon_submodule.sh` | `bash tools/sync_agent_canon.sh check` |

### GitHub symlink root views

次は root 側では symlink view です。regular file として編集しません。

| root path | AgentCanon source | verification |
| --- | --- | --- |
| `.github/AGENTS.md` | `vendor/agent-canon/.github/AGENTS.md` | `bash tools/sync_agent_canon.sh check` |
| `.github/copilot-instructions.md` | `vendor/agent-canon/.github/copilot-instructions.md` | `bash tools/sync_agent_canon.sh check` |
| `.github/instructions/` | `vendor/agent-canon/.github/instructions/` | `bash tools/sync_agent_canon.sh check` |
| `.github/agents/` | `vendor/agent-canon/.github/agents/` | `bash tools/sync_agent_canon.sh check` |

### AgentCanon standalone-only surface

次は standalone `agent-canon` GitHub repository 用の正本であり、template root へ同期しません。

- `vendor/agent-canon/.github/PULL_REQUEST_TEMPLATE.md`

| AgentCanon path | root behavior |
| --- | --- |
| `vendor/agent-canon/.github/PULL_REQUEST_TEMPLATE.md` | standalone AgentCanon repo 専用。template root へ同期しません。 |

### Template-local surfaces

次は template / derived repo 側の runtime contract であり、AgentCanon から同期しません。

| root path | owner | review trigger |
| --- | --- | --- |
| `.gitmodules` | template / derived repo | AgentCanon URL、branch、submodule checkout behavior が変わる PR |

## Editing Rule

- shared runtime surface を直すときは `vendor/agent-canon/` 側を編集します
- root 側の symlink view や copy surface を直接編集しません
- root copy が drift したら `bash tools/sync_agent_canon.sh link-root` で復元します
- drift を確認したいときは `bash tools/sync_agent_canon.sh check` を使います
- shared surface audit は `bash tools/sync_agent_canon.sh check` を正本にします
- root copy surface の dependency header は AgentCanon source path を名前で示します
- root copy surface の変更は、source-side diff があるか、template-local override として PR / closeout evidence に理由を残した場合だけ認めます
- root 側で shared surface の file / directory 欠落を見つけたときは、再作成前に template root、`vendor/agent-canon/`、standalone `agent-canon`、この surface list、`tools/sync_agent_canon.sh` の順で確認します
- 欠落が broken symlink、root copy drift、surface list 漏れ、canon 側 rename、意図的削除のどれかを分類してから、`link-root`、vendor update、surface list update、または削除 follow-up に進みます
- template と canon の両方で欠落している path だけを repo-local 新規 file 候補にします

## Validation

```bash
bash tools/sync_agent_canon.sh check
make agent-checks
make agent-canon-pr-check
```

shared surface audit:

```bash
bash tools/sync_agent_canon.sh check
```

## Root-Side Interpretation

- `scripts/README.md` と `documents/tools/README.md` は root 側の実行入口です
- workflow canon は `agents/workflows/` にあり、root では `agents/` symlink view 経由で参照します
- `experiments/README.md`、`experiments/_template/`、`experiments/report/README.md`、`experiments/registry.toml`、topic 固有の `experiments/<topic>/`、`reports/`、repo-local note は root 側の正本に残します
- shared surface の ownership や upstream sync は、この文書と `documents/agent-canon-subtree-migration.md` を正本にします
