<!--
@dependency-start
contract reference
responsibility Documents the default source-free template bootstrap path.
upstream design ./static-seed-export.md static seed ownership, provenance, and exclusion contract
upstream design ./template-github-remote.md template GitHub canonical remote policy
downstream implementation ../../tools/docs/check_bootstrap_docs.py rejects live runtime requirements in the default path
downstream design ../../agents/skills/start-repository.md default repository-start workflow
@dependency-end
-->

# Template Bootstrap

この文書は、`git clone <template>` 直後に新しい repository を使い始めるための
**default bootstrap** を定義します。default は source-free です。template が直接所有する
static seed と project-owned script だけを使い、外部の AgentCanon checkout、runtime tool、
更新処理、同期状態、checkout credential、network access を必要としません。

## Reader Map

- Clone 直後: 通常 clone した tracked tree をそのまま使います。
- 初期化: project slug、表示名、destination remote だけを設定します。
- Static seed: template 内の regular file を読み、bootstrap 中には再生成しません。
- 受け入れ確認: project-owned validation を実行します。
- Live integration: default とは別の明示選択です。

## 1. Clone 直後

```bash
git clone <template-repo> <your-project>
cd <your-project>
```

追加の source checkout や recursive option は不要です。clone 後の全 tracked file は、
通常の Git tree だけで読めなければなりません。

## 2. 初期化

repository 名、表示名、destination remote 名を変える場合は次を使います。agent に任せる場合は
`$start-repository` を指定し、この project-owned entrypoint を呼ばせます。

```bash
bash scripts/start_repository.sh \
  --project-slug your-project \
  --display-name "Your Project"
```

この処理は repository identity と project config だけを変換します。static seed の取得、
上流最新版の探索、runtime projection、background update は行いません。GitHub access が必要な
場合も destination repository の作成・push に限定します。

## 3. Static Seed Ownership

[Static Seed Export Contract](static-seed-export.md) に従って template maintainer が生成した
次の surface を、template/consumer が regular file として直接所有します。

- `.codex/config.toml`
- `.codex/agents/<role>.toml`
- `agent-canon-static-seed.json`

provenance は source repository identity、source commit、schema version だけを保持します。
consumer 側の latest 状態、同期履歴、時刻、branch、remote URL は持ちません。seed maintenance は
maintainer が明示的に行う **one-way export** であり、clone、bootstrap、通常 CI、product runtime
から自動実行しません。

project 固有の instruction、script、workflow、Docker/Dev Container、editor config は project が
通常 file として所有します。static seed を上流 source への link、runtime import、代替 package、
別 checkout に置き換えません。

## 4. 受け入れ確認

初期化変更を commit したあと、project-owned validation を実行します。

```bash
bash scripts/start_repository.sh --validate-only
```

最低限、次を確認します。

- static seed と provenance が regular file である。
- Codex role reference が同じ repository 内の role file へ閉じている。
- 外部 source、更新状態、runtime tool が無くても bootstrap validation が成功する。
- destination remote 以外の network や credential を要求しない。

## 5. 開発環境

- host 前提: `documents/contracts/linux-wsl-host-requirements.md`
- container: `docker/README.md`
- VS Code Dev Container: `.devcontainer/`
- workspace defaults: `.vscode/`

これらはすべて project-owned regular content です。

## 6. Live Integration Is Separate

明示的に採用する repository だけの別契約です。default template/bootstrap はその manifest、
投影、更新 lifecycle、source-root discovery を選択しません。採用する場合は通常経路の延長ではなく、
repository architecture の独立した opt-in 変更として review します。

## 7. 作業開始

project の README、workflow、test、docs、Docker command を正本として作業を開始します。
新規作業が AgentCanon source の存在を暗黙に仮定してはなりません。
