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

親固有の developer/agent tool がある場合だけ、親 root に
`.devcontainer/dependencies.toml` を作成し、その record だけを置きます。
親固有の依存が無い場合はファイルを作成せず、不在を parent overlay なしとして
扱います。schema は
`agent-canon.devcontainer-dependencies` version `2`、record は
`id/package/method/version/source/verification/deps/provides/failure_policy` を
必須とし、method-specific な key fingerprint、checksum、`executable_owner_packages`、
repo/commit/source_identity/locked、browser fields も型付きで記録します。
`verification` は method と一致する
closed kind と owner-specific fields を持ち、generic command 配列や
container identity を receipt の十分条件にしません。
Cargo の AgentCanon CLI record は `source_identity = "active-source"` を選択し、
SHA を manifest に複製しません。

image build は次の順で一度だけ manifest を読み、immutable image tree を作ります。

1. `<workspace>/.devcontainer/dependencies.toml`（親、存在する場合）
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
`<workspace>/.devcontainer/dependencies.toml` が存在するときだけ
`parent-overlay` とします。親 Template が親所有の derived tool を持たない
新規または派生 repo は空 manifest や sentinel を作成せず、不在で parent
overlay なしを表現します。移行中の既存 repo に残る `records = []` の
overlay は parser が互換入力として受理します。
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
`source_identity = "active-source"` の Cargo record は毎回 `cargo build
--release --locked` を実行し、mounted source tree の incremental/change detection
を Cargo に委ねます。Build input は mounted source tree であり、startup state は
Git metadata、parent gitlink、source SHA から独立しています。active-source install
は source-identity receipt を発行せず、Cargo binary の typed verification が pass
した時点で、その起動の install が完了します。
固定 `commit` を選択する Cargo record は既存の Git commit verification と source
identity receipt を保持し、選択した commit と異なる source を受け入れません。

## pin と root projection

親側で AgentCanon submodule pin を更新し、active root views がその pin と
一致することを確認します。親の `.devcontainer/` は実ディレクトリのまま保持し、
`devcontainer.json` を含む regular files の shared copy、symlink、wrapper は
追加しません。生成された
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
devcontainer developer/agent tools の差を明記します。AgentCanon image は
Node/npm、Codex、gh、LSP tools を含む manifest-selected image capability の owner
であり、`/usr/local/share/agent-canon/image-dependencies` に plan と immutable
receipts を保持します。workspace bind の Python package install は image build または
親 image の責務であり、post-create は package install、network、repair を行いません。

## order preservation

親の `postCreateCommand` は次の順を直接保持します。

```text
image build
  parent manifest -> vendor manifest merge
  full plan validation and topological image-safe execution
  immutable `/usr/local/share/agent-canon/image-dependencies/{plan.json,receipts}`
post-create
  read-only image-verify (stored plan, receipts, live package/executable state)
  container runtime readback; if the workspace projection is unusable or unwritable under
  any daemon mapping mode, no host repair is attempted and the container-local canonical
  runtime remains the fallback
parent .devcontainer/post-create-parent.sh  # final, when present
```

Standalone AgentCanon image は固定 OS/Python capability と Node/npm provider を image build
で準備し、Node 22.14.0 bullseye-slim は digest-pinned official OCI image から取り込む。
全 selector は source-root wrapper 経由の read-only image-verify から始める。

親 record の manifest order と parent-first merge order は、依存制約がない
record の安定順として保持します。親 post-create を shared script に吸収したり、
parent Python installer を post-create に残したり、workspace bind を package repair の
対象にしたりしません。
