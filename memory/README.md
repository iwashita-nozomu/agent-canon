# Memory

`memory/` は、shared canon が責務を持つ durable memory の置き場です。
今回から flat な 2 file 構成ではなく、`global / methods / candidates / run-local` の層に分けます。

## Layout

- [global/USER_PREFERENCES.md](/mnt/l/workspace/project_template/memory/global/USER_PREFERENCES.md)
  - repo-wide durable user preference の正本
- [global/AGENT_PHILOSOPHY.md](/mnt/l/workspace/project_template/memory/global/AGENT_PHILOSOPHY.md)
  - repo-wide durable agent philosophy の正本
- [methods/README.md](/mnt/l/workspace/project_template/memory/methods/README.md)
  - 方法ベース memory の説明
- [candidates/README.md](/mnt/l/workspace/project_template/memory/candidates/README.md)
  - role / cluster ごとの未昇格 candidate
- [subagent_loadouts.yaml](/mnt/l/workspace/project_template/memory/subagent_loadouts.yaml)
  - role ごとの固定 read surface と write route

## Memory Layers

### `global/`

- 全 role が読む durable memory
- `AGENTS.md` や workflow へ昇格する前の repo-wide 正本

### `methods/`

- role 固有ではなく方法ベースの memory
- requirements、planning、design、implementation、review のような execution method を置く
- 複数 role が同じ file を読む

### `candidates/`

- run-local から昇格したが、まだ method/global に上げない観測
- reviewer 系は原則ここまでで止める

### run-local

- `reports/agents/<run-id>/`
- task 専用 scratch、TODO、decision、work log
- closeout でだけ上位層へ昇格を判断する

## Fixed Routing

反映経路は固定します。

1. run-local -> candidate
1. candidate -> method
1. method -> global
1. global -> workflow / `AGENTS.md`

禁止:

- run-local -> workflow / `AGENTS.md` の直行
- reviewer role の method / global 直書き

## No Compatibility Layer

- `memory/global/` を唯一の durable memory 正本にします。
- 旧 top-level note と `notes/themes` alias は残しません。
- root runtime も canonical path をそのまま読みます。
