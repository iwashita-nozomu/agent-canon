<!--
@dependency-start
contract design
responsibility 親レポが AgentCanon の宣言的 devcontainer 依存契約を採用するための follow-up を固定する。
upstream design ../../../CONTAINER_OPERATIONS.md product image と mounted developer/agent tool の所有境界
upstream implementation ../../../.devcontainer/dependencies.toml AgentCanon shared manifest
upstream implementation ../../../.devcontainer/post-create.sh shared execution order
downstream implementation ../../../tools/agent_tools/parent_repo_readiness.py parent structure validation
downstream implementation ../../../tools/sync_agent_canon.sh pin and root projection follow-up
@dependency-end
-->

# 親レポ follow-up: devcontainer dependency manifest

この文書は AgentCanon source change と同時に親 root を変更しないための
引き継ぎ契約です。親レポの実装者は、AgentCanon の pin を更新した同じ親側
変更で次の項目を完了します。

## 親 root の依存 manifest

親 root に `.devcontainer/dependencies.toml` を作成し、親固有の
developer/agent tool record だけを置きます。schema は
`agent-canon.devcontainer-dependencies` version `2`、record は
`id/package/method/version/source/verification/deps/provides/failure_policy` を
必須とし、method-specific な key fingerprint、checksum、`executable_owner_packages`、
repo/commit/source_identity/locked、browser fields も型付きで記録します。
`verification` は method と一致する
closed kind と owner-specific fields を持ち、generic command 配列や
container identity を receipt の十分条件にしません。
Cargo の AgentCanon CLI record は `source_identity = "active-source"` を選択し、
SHA を manifest に複製しません。

共有 post-create は次の順で一度だけ読みます。

1. `<workspace>/.devcontainer/dependencies.toml`（親）
2. `<workspace>/vendor/agent-canon/.devcontainer/dependencies.toml`（vendor）

standalone AgentCanon では `.devcontainer/dependencies.toml` 自身を一度だけ
読みます。親 record の値は常に保持し、vendor は欠落値を補い、互換な
`deps/provides/components/checksums/assets` だけを union します。
`apt-package` と `apt-repository` は `executable_owner_packages` を必須とします。
`receipt` 上の executable binding に対する所有境界検証は `tools/agent_tools/devcontainer_dependencies.py` で行います。
検証対象は所有者集合を列挙する `.devcontainer/dependencies.toml` です。
`verification` は同一でなければ incompatible duplicate として fail します。
scalar の不一致、重複 provider、missing dependency、cycle は fail です。
manifest の全体 validation が pass するまで、derived install に進めません。

## Manifest source の role と cardinality

schema v2 の manifest source role は filename の推測ではなく構造から解決します。
親と vendor がある構成では
`<workspace>/.devcontainer/dependencies.toml` を `parent-overlay` とし、親
Template が親所有の derived tool を持たない場合は `records = []` を明示できます。
`vendor/agent-canon/.devcontainer/dependencies.toml` は `canonical` であり、
空にはできません。standalone AgentCanon の workspace manifest も
`canonical` であり、空にはできません。source を読み込んだ後の merge 済み plan
には 1 件以上の record が必要です。provider、missing dependency、cycle、
typed verification の不変条件は変更しません。

success receipt は plan/record fingerprint の一致だけでは再利用しません。
record owner の typed verification を毎回実行し、package-owned state、
apt repository の key/source、exact executable、toolchain/components、
browser cache executable、または source-local Cargo binary が欠落・不一致
なら receipt を削除して repair installation と再 verification を行います。
active-source の receipt は実行時に解決した source identity も記録します。
derived parent では committed `HEAD:vendor/agent-canon` gitlink と selected
vendor source-root `HEAD` が同一であることを provider identity とし、standalone
AgentCanon では checked-out source-root `HEAD` を identity とします。identity または
binary verification が一致しない場合は receipt を再利用せず fail/repair し、別の
固定 SHA、stale source、compatibility fallback は選択しません。

## pin と root projection

親側で AgentCanon submodule pin を更新し、`.devcontainer/devcontainer.json`
と shared root view がその pin を直接参照することを確認します。親の
`.devcontainer/` は実ディレクトリのまま保持し、shared file の全体コピーや
wrapper を追加しません。生成された
`.agent-canon/docker-compose.generated.yml` と dependency receipts は追跡対象にしません。

AgentCanon source update 後の親側 follow-up は request-evidence を付けた
root projection route で行います。

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
    exec tools/sync_agent_canon.sh link-root
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root \
  exec tools/sync_agent_canon.sh check
```

## docker README と ownership

親の `docker/README.md` に、Docker product image/build/runtime と mounted
devcontainer developer/agent tools の差を明記します。Product image は
project runtime と project Python dependency の owner、AgentCanon manifest は
mounted shared tools の owner、親 `docker/install_python_dependencies.sh` は
workspace Python packages の owner です。Codex、Node/npm、Rust、Lean、
Playwright を convenience-only の理由で Dockerfile に追加しません。

## order preservation

親の `postCreateCommand` は次の順を直接保持します。

```text
shared post-create
  fixed bootstrap validation
  parent manifest -> vendor manifest merge
  full plan validation
  topological derived execution and per-record receipts
  parent docker/install_python_dependencies.sh
  AgentCanon build, cache, and runtime projection
parent .devcontainer/post-create-parent.sh  # final
```

親 record の manifest order と parent-first merge order は、依存制約がない
record の安定順として保持します。親 post-create を shared script に吸収したり、
parent Python installer を Docker image build に移したりしません。
