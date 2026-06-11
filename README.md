# agent-canon
<!--
@dependency-start
responsibility Documents agent-canon for this repository.
upstream design PHILOSOPHY.md AgentCanon design-time philosophy.
upstream design AGENTS.md shared canon runtime contract
upstream design responsibility-scope.toml AgentCanon path responsibility scope map.
upstream design documents/semantic_index.md semantic-index command and result contract.
upstream implementation rust/agent-canon/src/structured_analysis.rs structured document and responsibility analysis.
upstream design LICENSE AgentCanon license text
upstream design documents/agent-canon-licensing-policy.md AgentCanon license boundary
downstream design CONTAINER_OPERATIONS.md top-level container and devcontainer operation rulebook.
@dependency-end
-->


このディレクトリは `agent-canon` 自体の source tree です。
template や派生 repo に配布する shared agent canon の正本をここに置きます。

## First Read Path

人がこの repo を読む入口は次の順で固定します。

1. `README.md`
1. `PHILOSOPHY.md`
1. `documents/README.md`
1. `agents/README.md`
1. `agents/workflows/README.md`

`PHILOSOPHY.md` は設計時哲学の正本、`documents/README.md` は root
`documents/` の索引、`agents/README.md` は workflow / skill / runtime hub、
`agents/workflows/README.md` は workflow selector です。
`agents/canonical/README.md` は layout appendix として扱い、最初の hub にはしません。

## このディレクトリの役割

- workflow canon の正本
- skill / subagent / runtime instruction の正本
- shared runtime helper と validation helper の正本
- shared canon の upstream sync と PR 運用の正本
- design-time philosophy の正本

この役割を読んだ後は、どの責務がどの path に属するかを次の構造モデルで確認する。

## 構造モデル

この repo の全体構造は、top-level directory 名だけではなく、
`responsibility-scope.toml` と各 file の dependency manifest で読む。

2026-06-07 の機械解析では、structured-analysis 対象 file は 773、directory
は 131、document inventory 対象は 396 だった。scope 定義の逸脱は 0 件で、
document inventory finding は 11 件だった。この解析結果は、責務 scope、
top-level surface、大きい directory の内部構造の順に読む。

### 責務 Scope

`responsibility-scope.toml` は broad directory scope と cross-directory scope
を同時に扱う。以前は `eval-and-hook-evidence` と broad scope が 13 file で
重なっていたため、現在は broad scope 側の `exclude_paths` で evidence
control-plane file を差し引く。2026-06-06 の再解析では、`exclude_paths`
適用後に複数 scope へ属する tracked file は 0 件である。

| Scope | 種別 | 主な path | 役割 |
| --- | --- | --- | --- |
| `runtime-entrypoints` | primary | `AGENTS.md`, `ROOT_AGENTS.md`, `.agents/**`, `.codex/**`, `.devcontainer/**`, `agents/**`, `mcp/**` | agent runtime の入口、workflow canon、skill、hook、MCP、runtime config。 |
| `shared-tooling` | primary | `tools/**`, `rust/**`, `helper_inventory_guard_policy.json` | shared automation、static gate、OOP checker、Rust CLI、tool catalog。 |
| `shared-policy-documents` | primary | `README.md`, `CONTAINER_OPERATIONS.md`, `responsibility-scope.toml`, `documents/**`, `notes/**`, `memory/**`, `references/**` | policy、convention、container、bootstrap、tool documentation、記憶と参照資料。 |
| `test-surfaces` | primary | `tests/**` | shared tools、workflow、責務 policy を検証する test surface。 |
| `github-automation` | primary | `.github/**` | GitHub Actions、Issue / PR template、GitHub-facing entrypoint。 |
| `operational-issues` | primary | `issues/**` | durable local issue files と GitHub Issue mirror metadata。 |
| `external-skill-vendor` | primary | `vendor/**` | third-party skill など、AgentCanon 内部の external dependency 置き場。 |
| `eval-and-hook-evidence` | cross-directory primary | `evidence/**`, `.codex/hooks/log_archive_mount_warning.py`, `documents/runtime-log-archive*.md`, `tools/agent_tools/runtime_log_*.py` | hook、skill、workflow、behavior eval の evidence と log archive control plane。 |

`eval-and-hook-evidence` に移した file は、元の broad scope から除外する。

| 除外元 scope | `exclude_paths` の意味 |
| --- | --- |
| `runtime-entrypoints` | `.codex/hooks/log_archive_mount_warning.py` は runtime directory 内にあるが、primary owner は evidence scope。 |
| `shared-policy-documents` | `documents/runtime-log-archive*.md` は policy directory 内にあるが、primary owner は evidence scope。 |
| `shared-tooling` | `tools/agent_tools/runtime_log_*.py` は tooling directory 内にあるが、primary owner は evidence scope。 |

Top-level surface は次のように読む。`Tracked` は `git ls-files`、`Manifest`
は `@dependency-start` marker を持つ tracked file の数です。

| Path | Tracked | Manifest | 構造上の責務 |
| --- | ---: | ---: | --- |
| root files | 9 | 7 | `README.md`、`PHILOSOPHY.md`、`ROOT_AGENTS.md`、`responsibility-scope.toml` などの root entrypoint と root policy。 |
| `.agents/` | 42 | 42 | Codex skill discovery 用の runtime skill entrypoint。 |
| `.codex/` | 61 | 61 | Codex config、role TOML、hook runtime surface。 |
| `.devcontainer/` | 4 | 4 | shared devcontainer profile。 |
| `.github/` | 12 | 12 | GitHub workflow、Issue / PR template、GitHub agent entrypoint。 |
| `agents/` | 143 | 143 | workflow、skill canon、template、task catalog の human-facing hub。`agents/evals/` は旧 manifest path の compatibility stub。 |
| `evidence/` | 8 | 8 | tracked eval manifest source と evidence contract。run output は `.agent-canon/log-archive/` に置き、legacy `agents/evals/results/` は migration input としてだけ扱う。 |
| `codex-cli-guide/` | 14 | 14 | OpenAI Codex CLI 日本語 guide の分割 source。 |
| `completion-first-review/` | 14 | 14 | completion-first 改善 review の index と説明。 |
| `documents/` | 115 | 113 | shared policy、運用規約、tool / structured-analysis / prose graph docs。runtime log archive docs は `eval-and-hook-evidence` scope。 |
| `issues/` | 21 | 21 | AgentCanon operational finding の open / closed issue record。 |
| `memory/` | 3 | 3 | user preference と agent philosophy の durable memory。 |
| `notes/` | 30 | 30 | knowledge、guardrail、theme、failure、branch、worktree notes。 |
| `references/` | 3 | 3 | workflow、tool、research の外部参照索引。OpenAI / Codex product evidence は `$openai-docs` source route を参照する。 |
| `rust/` | 15 | 14 | `agent-canon` Rust CLI implementation。 |
| `tests/` | 97 | 96 | shared tool と responsibility policy の test suite。 |
| `tools/` | 171 | 171 | Python / shell / Rust wrapper を含む shared automation surface。runtime log archive tools は `eval-and-hook-evidence` scope。 |
| `vendor/` | 3 | 3 | third-party skill vendor contract と adapter metadata。 |

### 現在の Review Finding

structured-analysis の 2026-06-07 review では blocker は 0 件です。残る 11
件は closed issue record の historical inventory が 10 件、closed issue path
の stale-name candidate が 1 件です。README の構造説明はこれらを隠さず、
open warning と historical inventory を分けて読む。

### 大きい Directory の Child 表

| Parent | Main children |
| --- | --- |
| `agents/` | `skills/`, `templates/`, `workflows/`, `canonical/`, compatibility `evals/` |
| `evidence/` | `agent-evals/` |
| `tools/` | `agent_tools/`, `ci/`, `docs/`, `oop/`, `experiments/`, `static_analysis/`, `validation/` |
| `documents/` | `tools/`, `conventions/`, `templates/`, `structured-analysis/`, `prose-reasoning-graph/`, `design/` |
| `.codex/` | `agents/`, `hooks/`, shared `config.toml` |
| `.github/` | `workflows/`, `ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE/` |
| `tests/` | `agent_tools/`, `tools/`, `fixtures/` |
| `notes/` | `knowledge/`, `guardrails/`, `themes/`, `experiments/`, `failures/`, `branches/`, `worktrees/` |

この構造表を更新するときは、AgentCanon root から次を実行し、結果を確認してから
README を直す。

```bash
agent-canon structured-analysis document-inventory --root . \
  --json-out reports/agentcanon-structure/document_inventory.json \
  --markdown-out reports/agentcanon-structure/document_inventory.md
python3 tools/agent_tools/responsibility_scope.py --root . --format json \
  > reports/agentcanon-structure/responsibility_scope.json
```

## 主な入口

- `documents/README.md`
  - root `documents/` の索引
- `PHILOSOPHY.md`
  - 設計時哲学と安定原則の正本
- `agents/README.md`
  - workflow / skill / runtime hub
- `agents/workflows/README.md`
  - workflow catalog と routing guide の入口
- `ROOT_AGENTS.md`
- `agents/`
- `.agents/skills/`
- `.codex/agents/`
- `tools/`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `CONTAINER_OPERATIONS.md`
- `documents/github-first-module-and-devcontainer-policy.md`
- `documents/agent-canon-github-remote.md`
- `documents/agent-canon-update-route.md`
- `documents/agent-canon-submodule-rollback.md`
- `documents/derived-repo-bootstrap-runbook.md`
- `documents/mcp-preflight-and-alternate route-policy.md`
- `documents/issue-label-taxonomy.md`
- `documents/prompt-skill-evaluation-checklist.md`
- `documents/template-github-remote.md`
- `documents/runtime-profiles-and-check-matrix.md`
- `documents/template-agent-canon-audit-resolution.md`
- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`
  - legacy vendoring compatibility appendix

## OpenAI / Codex Source Route

OpenAI / Codex の current product evidence、API reference、model selection、
model upgrade、prompt-upgrade guidance、Codex manual、official-domain web
alternate route は AgentCanon 内で個別 URL や alternate route 文書として二重管理しない。
host-provided `$openai-docs` skill を正本 route とし、AgentCanon 側には local
decision artifact だけを残す。

- workflow / bibliography policy:
  `agents/workflows/workflow-references.md`
- Codex runtime configuration:
  `documents/codex-configuration-reference.md`
- implementation / runtime source record:
  `references/agent-canon-technology-bibliography.md`
- skill discovery rule:
  `agents/skills/README.md`

role TOML の model 値や checked-in config の実値は runtime source ですが、
それらの変更根拠は `$openai-docs` で確認します。README、workflow docs、
bibliography、configuration guide に OpenAI docs の alternate route copy を増やしては
いけません。

## Runtime Profiles

AgentCanon exposes shared runtime surfaces so template and derived repositories
can opt into them without copying implementation. Exposed does not mean always
active. The activation and validation policy is
[Runtime Profiles And Check Matrix](documents/runtime-profiles-and-check-matrix.md).

- Agent runtime surfaces are active when an agent performs or reviews work.
- GitHub automation, devcontainer, Docker, experiment, C++, memory, and
  maintenance surfaces are profile-specific.
- Full repo validation is still available, but day-to-day checks should be
  selected by changed path and risk class.
- The 2026-05-16 500-item audit is resolved in
  [Template / AgentCanon Audit Resolution](documents/template-agent-canon-audit-resolution.md).

## 利用時のディレクトリ / リンク構成

AgentCanon 単体 repo では、この tree 自体を source of truth として扱います。
Template や派生 repo では `vendor/agent-canon/` を source of truth にし、repo
root の入口は symlink view または明示的な synced copy にします。Template /
derived repo に露出する root view は次です。

- `vendor/agent-canon/`: AgentCanon submodule pin。shared workflow、skills、tools、docs の正本。
- `AGENTS.md -> vendor/agent-canon/ROOT_AGENTS.md`: Codex 向けの薄い root entrypoint。
- `agents -> vendor/agent-canon/agents`: workflow、canonical docs、task catalog の root view。
- `.agents -> vendor/agent-canon/.agents`: Codex skill discovery 用の root view。
- `.codex/config.toml -> vendor/agent-canon/.codex/config.toml`: Codex runtime config の共有 view。
- `.codex/agents -> vendor/agent-canon/.codex/agents`: Codex subagent role TOML の共有 view。
- `.devcontainer -> vendor/agent-canon/.devcontainer`: devcontainer profile の共有 view。
- `tools -> vendor/agent-canon/tools`: shared automation の共有 view。
- `documents/*`: template / derived repo root では active contract だけを regular file として残し、AgentCanon-owned shared policy docs は `vendor/agent-canon/documents/` から読みます。
- `memory/*`、`notes/*`、`tests/*`: `vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md` に従って shared surface だけを root view にします。
- `.github/AGENTS.md`: root `.github/AGENTS.md` から symlink される GitHub agent entrypoint。
- `.github/workflows/agent-coordination.yml`: root `.github/workflows/agent-coordination.yml` へ同期される workflow source。
- `.github/workflows/agent-canon-static-gates.yml`: standalone AgentCanon PR / push で tool catalog、tool drift、dependency review、workflow convention、container config の軽量 gate を走らせる workflow。
- `.github/PULL_REQUEST_TEMPLATE.md`: standalone AgentCanon repository 用の独立 PR checklist。template root へ同期しません。
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`: template 側で `vendor/agent-canon/` を変える PR 用 checklist。root `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` へ同期されます。

repo-local の正本として残すもの:

- `docker/`: Template / project の Docker runtime profile と dependency pack。Codex、agent 用 npm / Node、GitHub CLI / `gh`、auth、mount 方針は Dockerfile に焼かず、shared `.devcontainer/` の post-create と host mount convention で管理します。
- `scripts/`: Template / project 固有の bootstrap と slug 置換。
- `python/`、`src/`、`include/`、`lib/`: project implementation。
- `experiments/`、`reports/`、`goal.md`: repo-local state。shared symlink には戻しません。

root view の修復と検証:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
```

remote の正本:

- AgentCanon canonical remote は `documents/agent-canon-github-remote.md` を見ます。
- Template canonical remote は `documents/template-github-remote.md` を見ます。
- reusable module distribution は GitHub PR / main SHA を正本にします。repo-specific local Git repair は shared module architecture から分離します。

## 検索導線

正確な symbol、path、error message だけはまず `rg` で探します。それ以外の
広い概念、長い query、近い tool、既存 helper の再利用候補、編集 surface
選定では、`rg` より先に responsibility-based search を走らせます。
この導線は `ROOT_AGENTS.md` の Default Search And Routing と
`documents/semantic_index.md` の command / result contract に従う。

```bash
tools/bin/agent-canon semantic-index context-pack --root . \
  --query-file /tmp/query.txt --max-cells 12 --format text
tools/bin/agent-canon local-llm search \
  --purpose "find owning responsibility and existing surface" \
  --providers llm,tool,header-deps,code-deps,vector --format json
tools/bin/agent-canon semantic-index thin-docs --root . --top-k 10 --format text
```

semantic-index の DB が無い場合は先に build します:

```bash
tools/bin/agent-canon semantic-index build --root .
```

JSON 出力や旧 `vector_search.py` 互換 helper の扱いは、`ROOT_AGENTS.md` と
`documents/semantic_index.md` を正本にします。検索で対象 path と source
packet を絞ったら、以後の保守では正本 surface を直接編集し、root view や
生成物を別の truth surface にしない。

## 保守ルール

- template root の symlink view や synced copy を直接編集しません。
- shared canon を直すときはこの directory を source of truth にします。
- root surface を戻すときは次を使います。

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

## upstream sync

template 側で shared canon を直した変更を upstream `agent-canon` repo に戻すときは次を使います。

```bash
bash tools/update_agent_canon.sh merge-main-into-current
git -C vendor/agent-canon push origin HEAD
```

update / branch / PR の詳細は `agents/workflows/agent-canon-pr-workflow.md` を見ます。
canonical remote の詳細は `documents/agent-canon-github-remote.md` を見ます。

## License

AgentCanon is licensed under Apache License 2.0. See [LICENSE](LICENSE) and
[documents/agent-canon-licensing-policy.md](documents/agent-canon-licensing-policy.md).

Parent repositories may use a different root project license, but AgentCanon
submodule content and root views into AgentCanon retain the AgentCanon license.
Third-party skills or assets under `vendor/` must keep upstream URL, revision,
and license metadata before they are enabled. GitHub-sourced third-party
repositories attach under `vendor/<asset-class>/<github-owner>/<import-id>/`
with a manifest-backed adapter instead of being copied into canonical runtime
paths.
