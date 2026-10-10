<!--
@dependency-start
contract design
responsibility Defines C++ production path ownership and the consumer-owned CMake graph profiles.
upstream design ../conventions/coding-conventions-cpp.md C++ source and header conventions
upstream design ../conventions/coding-conventions-project.md project layout ownership
upstream design ../conventions/coding-conventions-testing.md test source and execution ownership
upstream design ../experiments/experiment-registry.md managed experiment identity and execution
upstream design ../experiments/result-log-retention-and-visualization.md result and retention ownership
upstream design ../structure/repo-structure-contract.toml repository path-existence profiles, not CMake graph selection
downstream implementation ../../tools/runtime/manifest/manifest_rendering.py routes C++ reviewer candidates from changed paths
downstream design ../../agents/skills/cpp-review.md owns selected project-native C++ review
downstream design ../../agents/skills/refactor-loop.md consumes the selected path and graph boundary
@dependency-end
-->

# C++ Build Layout

この文書は、AgentCanon を利用する project の C++ production source と consumer
target の owner boundary を定義します。AgentCanon 自身へ C++ CMake project を要求したり、
すべての consumer に同一の root layout を強制したりしません。

## 文書の構造契約

```text
structure_kind=design
audience=derived C++ project owners and native reviewers
decision_context=production path ownership and consumer CMake graph shape
owner_and_source=documents/design/cpp-build-layout.md; project CMake owner selects the profile
selected_topology=owner axes -> production paths -> graph profiles -> build/test/run boundary
source_map=#797 owns O(path); #802 owns G(manifest); #852/#866 retain experiment execution/materialization
invalid_interpretations=root CMake universally required/forbidden; layout inferred from path; cpp/ as fallback; AgentCanon CMake gate
validation_route=AgentCanon docs check for this document; selected project-native CMake checks only for changed consumer build behavior
```

## Owner axes

この設計では、二つの独立した判断を分けます。

| Issue / axis | Owns | Does not own |
| --- | --- | --- |
| #797: production source path `O(path)` | public header、production source、必要時の shared CMake helper の consumer path | CMake manifest topology、CTest registration、experiment run/result |
| #802: target graph `G(manifest)` | 選択された CMake entrypoint と、その configure graph に属する consumer targets | production file relocation、experiment execution/retention |

選択された layout profile の中で `O(path)` と `G(manifest)` は接続しますが、
片方を変えただけで他方の移行や checker を要求しません。

## C++ production path

`root-aggregate` profile では、project-owned public headers は root `include/`、
production implementation は root `src/` を使います。複数の CMake manifest が同じ設定を
実際に共有する場合だけ、project-owned `cmake/` helper に重複を集約します。helper は
target registry や experiment protocol を所有しません。

この path mapping は `cpp/` という固定 subdirectory を要求しません。既存 consumer の
source path をこの文書だけで移動せず、`cpp/` tree を compatibility fallback として
追加することもしません。

## CMake graph profiles

一つの consumer project は、その既存 project/build owner がどちらか一方を選択します。
profile identity は consumer の既存 CMake/design surface に属し、この文書は新しい
profile registry、command flag、path-shape autodetection を追加しません。

| Profile | Entrypoint and graph | Consumer ownership |
| --- | --- | --- |
| `root-aggregate` | Project root の `CMakeLists.txt` が project identity と production target を所有し、存在する test/experiment consumers を同じ configure graph に登録する | Production source path と install/export は project owner が決定する。現在の root-CMake consumer が有効な layout であり、root CMake を一律に削除しません |
| `consumer-local` | 選択された test または experiment の manifest を個別に configure し、他 consumer の graph に依存しません | `tests/cpp/<test-id>/CMakeLists.txt` と `experiments/<topic>/CMakeLists.txt` が各 consumer target を所有します。root aggregate を compatibility entrypoint として併置しません |

`root-aggregate` は root CMake がある consumer で使える profile であり、すべての
consumer にその entrypoint を要求する規則ではありません。`consumer-local` は明示的に
選択された project layout であり、directory shape だけから要求したり自動選択したり
しません。profile が consumer 側で決まっていない場合、AgentCanon は別 profile を
推測・生成・強制せず、その consumer の build owner が判断します。

## Build and test ownership

Configure source directory と binary directory は選択した profile と consumer の既存
CMake command から読み取ります。target 名、build directory、install prefix、test
registration は project-owned であり、`cpp-core`、`cpp-tests`、`build/cpp/`、
`.state/cpp-install/` を universal name/path として要求しません。

- `root-aggregate` は既存 root configure command と、その project が登録する target を使います。
- `consumer-local` は選択された individual manifest を configure/build し、その graph に含まれる test だけを実行します。
- shared production source/interface を consumer graph から参照する仕組みは project-owned です。source file list や target identity を各 consumer に無制御に複製しません。
- `cmake --build` は native target の build を担います。experiment の run/config/result/report/retention は既存 experiment lifecycle owner に残し、CMake target はそれらの実行状態を作りません。

必要な validation は、変更された consumer の選択 profile と native command から決めます。
一つの consumer の変更で無関係な consumer の configure/build/test を要求しません。

## Profile selection and review

`tools/runtime/manifest/manifest_rendering.py` は changed C/C++ source、header、または CMake
manifest から native reviewer candidate を選びます。その language-review routing は path
候補を示すもので、CMake profile を選択・検証するものではありません。C++ review は
consumer の canonical CMake entrypoint、production target、選択された consumer manifest、
実際の configure/build/test command を読み戻します。

`documents/structure/repo-structure-contract.toml` は repository path の存在・kind と
repository-level path profiles を所有します。CMake graph の選択や必須 path を同 contract
へ追加せず、C++ layout のための常時 admission gate / second checker を作りません。

## Experiment boundary

CMake は選択された native experiment target を build するまでを所有します。native
executable の launch、run identity、config snapshot、raw/summary result、report、retention は
既存 experiment lifecycle と artifact owners が所有します。`#866` は C++ experiment
package と既存 materializer の境界を別途所有し、この文書は新しい template client を
追加しません。

## Scope and evidence

この C++ design correction は AgentCanon source の CMake build/test を主張しません。現在の
consumer profile と build graph の実行証拠は、その consumer project owner が記録します。
AgentCanon source で扱うのは、選択された layout の path/graph boundary を記述し、関連する
conventions と reviewer route を同じ契約へ接続することです。
