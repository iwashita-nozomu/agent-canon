# Environment And Containers Audit Unit
<!--
@dependency-start
contract design
responsibility Audits Ubuntu direct base, cold-build reproducibility, non-root operation, sudo, owner split, and host-driver boundaries.
upstream design ../README.md owns static-first audit policy
upstream design ../../runtime/runtime-profiles-and-check-matrix.md owns profile validation selection
upstream implementation ../../../agents/skills/environment-maintenance.md owns environment repair
downstream implementation ../../../tools/analysis/code/parent_repository_audit.py selects this unit by semantic change surface
@dependency-end
-->

## Reader Map

Ubuntu direct base、cold build、non-root、sudo、owner split、host driver、devcontainer、
requirements、packs、safe-directory、Codex state の順に責務境界を読みます。image 間の
差分 build は監査しません。

## Owner Responsibility

`environment-maintenance` が Docker、CI environment、runtime profile、devcontainer の
repair route を所有します。親監査は machine-local state、host driver、shared AgentCanon
setup、親固有 setup の owner split を監査します。

## Invariant

1. runtime image は Ubuntu direct base として明示され、cold build が外部の既存 image、
   host workspace、warm cache、手動 post-step に依存せず再現できる。
2. container の通常 user は non-root で、必要な privileged operation は狭い sudo route
   として明示され、root のまま処理を継続しない。
3. AgentCanon shared setup、親 repository setup、generated/runtime state の owner split
   が明示され、同じ post-create/finalize を二重に実行しない。
4. CUDA/GPU/driver は host capability として扱い、image に host driver を同梱せず、
   `CUDA_VISIBLE_DEVICES` などの serial restriction を暗黙に追加しない。
5. `.devcontainer/`、Dockerfile、requirements、pack、safe-directory、mount、secret の
   契約が相互に一致し、machine-local path/secret を tracked image layer に焼き込まない。
6. `.zshenv`、`ZDOTDIR`、その他の host shell startup file を parent environment mount の
   必須条件にせず、user customization は non-root home の `.zshrc` に限定する。host の
   `.zshrc`/zshrc が存在しなくても cold image が成立する。
7. 必須 runtime environment は Docker `ENV`、devcontainer `containerEnv`、または owner が
   明示した bootstrap のいずれかで宣言し、interactive shell startup に隠さない。
8. host file mount inventory を一件ずつ確認し、default の required mount は workspace
   source と GPU runtime passthrough だけに限定する。read-only `.zshrc` は optional かつ
   absence-safe とし、host `~/.codex`、parent environment/config/previous state、Docker
   socket を default successful create や tool availability の必須条件にしない。Docker
   socket は optional profile としてだけ許可する。

## Evidence Sources

- `docker/`、`.devcontainer/`、`docker/packs/`、`agent-canon-environment.toml`
- Dockerfile の `FROM`、user、sudo、entrypoint、mount、cache、secret 宣言
- `.devcontainer/devcontainer.json` と bootstrap/post-create scripts
- `.zshenv`、`ZDOTDIR`、`.zshrc`、shell startup の mount/source/readback
- host file mount inventory と default/optional profile の create/tool-availability readback
- `documents/runtime/runtime-profiles-and-check-matrix.md`
- `tools/validation/dependencies/docker_dependency_validator.sh` と container config parser
- host driver は `nvidia-smi` 等の host evidence、image 側は driver 非同梱の static readback

## Repair Route

owner skill は `environment-maintenance`、主 tool は `docker_dependency_validator.sh`、
bootstrap container contract checkerとproject-owned environment checker。Ubuntu base、user/sudo、
owner split、host driver の static 誤りを先に修正し、runtime command は static に確定
できない invariant だけ実行します。

## Validation

Dockerfile/dependency/devcontainer/pack の static 整合性、non-root/sudo と owner split の
設定 readback、cold-build contract の宣言を必要十分な証拠とします。実際の cold build は
宣言だけで再現性を確定できない場合に一回だけ行います。Docker image 間の差分 build、
不要な全 image build、serial GPU 制限の追加は実行しません。

## Close Condition

Ubuntu direct base、cold-build、non-root/sudo、owner split、host-driver invariant が
evidence で pass し、対象 configuration readback が意図した差分だけになる。runtime-only
検証が実行不能なら `repair_blocked` と理由を記録し、次 unit へ進む。

## Related Change Surfaces

`surface:environment.containers`、`surface:runtime.profiles`、`surface:devcontainer`、
`surface:gpu.host-driver`。Docker、devcontainer、profile、safe-directory、container
validation contract、owner split の変更時だけ本 unit を更新します。

## Legacy Migration IDs

PRA-C056 PRA-C057 PRA-C058 PRA-C059 PRA-C060 PRA-C061 PRA-C062 PRA-C063 PRA-C064 PRA-C065 PRA-C066 PRA-C067 PRA-C068 PRA-C069 PRA-C070 PRA-X036 PRA-X037 PRA-X038 PRA-X039
