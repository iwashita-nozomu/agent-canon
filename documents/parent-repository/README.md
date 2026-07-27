<!--
@dependency-start
contract reference
responsibility Defines the expected structure and ownership boundaries of a parent repository that vendors AgentCanon.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared surface ownership and projection policy
upstream design ../structure/repo-structure-contract.toml machine-readable expected path contract
upstream design ../rule/directory-structure.md directory documentation and responsibility rule
upstream implementation ../../tools/agent_tools/parent_repo_readiness.py parent repository structure readiness checker
upstream implementation ../../tools/agent_tools/surface_manifest.py shared surface materialization and check
downstream design ../../README.md AgentCanon source reader route
@dependency-end
-->

# 親レポ構造

この文書は、AgentCanon を `vendor/agent-canon/` に pin する template / 派生
親レポに期待する構造、各 surface の所有者、Symlink と実体 directory の意味を
定義します。AgentCanon 自体の source tree の構造説明ではありません。

## 正本の分担

- この README: 親レポ root の期待構造と、Symlink / checked copy / regular
  surface の使い分け。
- `../SHARED_RUNTIME_SURFACES.md`: shared surface の source、projection、更新
  手順の正本。
- `../repo-structure-contract.toml`: checker が読む path と mode の正本。
- 各 directory の `README.md` または owner document: その directory 内の子構造と
  個別責務の正本。この README に子構造の説明を複製しない。
- 親レポ root の `documents/README.md`: 親レポ固有文書の索引。AgentCanon の
  shared document は `vendor/agent-canon/documents/` を読む。

## Root の期待構造

```text
<parent-root>/
├── AGENTS.md -> vendor/agent-canon/ROOT_AGENTS.md
├── README.md                         # parent-owned regular file
├── .agents -> vendor/agent-canon/.agents
├── .codex/                           # parent-owned regular directory
│   ├── agents -> ../../vendor/agent-canon/.codex/agents
│   ├── config.toml -> ../../vendor/agent-canon/.codex/config.toml
│   ├── project-config.toml           # optional parent-owned file
│   └── project-skills/               # optional parent-owned directory
├── .devcontainer/                    # parent-owned regular directory
│   ├── devcontainer.json -> ../../vendor/agent-canon/.devcontainer/devcontainer.json
│   ├── bootstrap-shared-runtime.sh   # parent-owned wrapper
│   ├── finalize-shared-runtime.sh    # parent-owned wrapper
│   ├── generate-runtime-compose.sh   # parent-owned wrapper
│   ├── post-attach.sh                 # parent-owned wrapper
│   ├── post-create.sh                # parent-owned ordering wrapper
│   └── post-create-parent.sh          # optional parent-owned hook
├── .github/                          # parent-owned path-constrained surfaces
├── .vscode/                          # parent-owned regular directory
│   └── <individual AgentCanon file symlinks>
├── agents -> vendor/agent-canon/agents
├── documents/                        # parent-owned regular directory
├── docker/                           # parent-owned regular directory
├── experiments/                      # parent-owned regular directory
├── notes/                            # parent-owned regular directory
├── reports/                          # parent-owned generated/evidence directory
├── tools -> vendor/agent-canon/tools
└── vendor/
    └── agent-canon/                  # clean submodule pin
```

## Surface の意味

### Symlink

Symlink は、AgentCanon にある shared source を親レポから同じ内容として参照
するために使います。Symlink 先を親レポ固有の内容で上書きせず、変更は
AgentCanon source の topic branch と PR から行います。

- `AGENTS.md`: root runtime instruction の view。
- `.agents/`: shared skill discovery の view。
- `.codex/agents/`: shared subagent role の view。
- `.codex/config.toml`: shared Codex runtime config の view。
- `agents/`: workflow / canonical document の view。
- `tools/`: shared automation の view。
- `.vscode/` の個別ファイル: shared editor defaults の view。
- `.devcontainer/devcontainer.json`: shared devcontainer profile の view。

### Regular directory / file

Regular surface は親レポが ownership を持ち、親固有の責務や state を保持する
ために使います。AgentCanon の source を親の regular copy として二重管理する
ためのものではありません。

- `.devcontainer/`: 親固有 wrapper と hook の実体 directory。
- `.codex/`: parent config overlay と project-specific skill の容器。
- `.github/`: GitHub が root path を要求する checked copy と親 workflow の容器。
- `documents/`: 親レポ固有の design / contract と document index。
- `docker/`: 親レポの image / pack / build contract。
- `experiments/`: 実験計画と結果の親レポ固有 surface。
- `notes/`: 親レポ固有の運用・知識・失敗記録。
- `reports/`: generated report と raw evidence の置き場。
- `vendor/agent-canon/`: source を編集しない clean submodule checkout。
- `scripts/`: 親レポ固有の bootstrap と project slug 置換。
- `python/`、`src/`、`include/`、`lib/`: 親レポの production implementation。
- `goal.md`: 親レポ固有の current task state。AgentCanon view に戻さない。

## Directory owner document

この README は root の境界だけを定義します。各 directory の子構造、役割、更新
手順は次の owner document を参照し、ここへ再掲しません。

- `AGENTS.md`、`.agents/`、`.codex/`、`agents/`: `AGENTS.md`、
  `agents/README.md`、`agents/canonical/README.md`。
- `.devcontainer/`: `../design/devcontainer/parent-devcontainer-wrapper-policy.md`。
- `.github/`、`.vscode/`、`tools/`、`vendor/`: `../SHARED_RUNTIME_SURFACES.md`
  と各 directory の README。
- `documents/`: `../README.md` と `../rule/README.md`。
- `docker/`: `../CONTAINER_OPERATIONS.md` と親レポの `docker/README.md`。
- `experiments/`、`reports/`、`notes/`、project implementation directory:
  親レポ自身の README / design / experiment owner document。

directory に README がある場合、その README は child tree と責務の reader
entrypoint です。README がない場合は、owner document を追加してから child
structure を大きく変更します。構造の説明を root README、親構造 README、
directory README に重複して持たせません。

### Checked copy

GitHub が Symlink をそのまま利用できない root path は、AgentCanon source から
checked copy として投影します。checked copy は独立した正本ではなく、source
変更後に sync tool で更新します。手編集で親固有の分岐を作りません。

## Devcontainer 境界

`.devcontainer/` 全体を `vendor/agent-canon/.devcontainer` へ Symlinkする構成は
禁止します。directory 自体を親が所有することで、親固有 hook と shared runtime
の順序を同じ entrypoint で表現できます。

- `devcontainer.json` だけを AgentCanon source から Symlinkする。
- wrapper は `BASH_SOURCE[0]` から親 root を解決し、cwd に依存せず source script
  を呼ぶ。
- `post-create.sh` は AgentCanon の標準処理を先に実行し、成功した場合だけ
  `post-create-parent.sh` を実行する。
- compose generator を source path から呼ぶときは
  `AGENT_CANON_DEVCONTAINER_REPO_ROOT` に親 root を渡す。
- compose の生成物は親 `.devcontainer/` に置き、`vendor/agent-canon/` に
  混在させない。

この分離により、shared runtime の更新と親プロジェクトの hook / build 設定を
別々に review でき、親固有の変更が AgentCanon source の pin を汚染しません。

## Topic workspace

依存 module を変更するときは、親 root の下に次の形で topic workspace を作り、
親レポと依存 module の clone を同じ workspace root に置きます。

```text
<parent-root>/workspace/<topic-slug>/
├── <parent-repo>/
└── <module-basename>/
```

devcontainer は topic root を `/workspace` に一度だけ mount します。親レポと
依存 clone を個別に mount したり、別 topic の clone を runtime に混ぜたり
しません。作業完了後、再現に不要な clone は削除対象ですが、未統合 commit や
ユーザー所有差分がある clone は保持してから判断します。

## 構造確認

人間向けの構造確認は `tree` を使います。directory の詳細は各 directory の
README / owner document を読み、ここへ再掲しません。

```bash
tree -a -L <depth> -I '.git|__pycache__|.venv|node_modules|target|reports' <parent-root>
python3 vendor/agent-canon/tools/agent_tools/parent_repo_readiness.py \
  --root <parent-root> --tree-depth <depth>
```

path / mode の判定は `repo_structure_contract.py` と surface manifest checker に
委譲します。README の tree と checker の結果が異なる場合は、まず ownership と
manifest を確認し、Symlink を実体に置き換えて合わせません。
