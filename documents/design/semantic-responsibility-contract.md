<!--
@dependency-start
contract design
responsibility Defines the semantic responsibility contract for implementation deltas and their verification ownership.
upstream design ../rule/README.md document filename, placement, and language rules
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface policy
upstream design codex-spark-implementation-routing.md implementation owner and validation route
downstream implementation ../../templates/documents/semantic-responsibility-contract.template.toml reusable empty task instance
downstream implementation ../../tools/agent_tools/check_semantic_responsibility_contract.py schema, identity, and reference validator
downstream design ../../agents/COMMUNICATION_PROTOCOL.md active design packet reference
@dependency-end
-->

# Semantic Responsibility Contract

## 目的

この文書は、実装で変わる意味を semantic delta として記録し、各 delta の
obligation と一次検証 owner を実装前に割り当てるための設計正本です。実装者、
設計 reviewer、検証 owner は同じ task-local instance を参照し、設計の主張、
変更する mechanism、観測可能な assertion、判定可能な oracle の対応を読み返します。

この契約は責務の意味と検証の責任を扱います。repository path の所有は
`responsibility-scope.toml` が扱い、semantic grouping から class、module、file
などの構造を決めません。

## 正本と instance

- 正本はこの文書です。
- `templates/documents/semantic-responsibility-contract.template.toml` は値を持たない
  再利用可能な task instance の形です。
- 値を埋めた instance は active design packet が参照する run-local artifact として
  `reports/agents/<run-id>/` にだけ置きます。template や `documents/` に実値を戻しません。
- `check_semantic_responsibility_contract.py` は schema、identity、reference の
  fail-closed validator です。設計の妥当性、実装の正しさ、レビューの合否はこの checker
  の責務ではありません。

## Semantic delta

一つの semantic delta は、変更の意味を説明する `summary`、設計参照、そして次の
implementation action を持ちます。

| action | 意味 |
| --- | --- |
| `reuse` | 既存 mechanism を同じ契約のもとで使う |
| `extend` | 既存 mechanism に承認済みの意味を追加する |
| `replace` | 既存 mechanism を新しい mechanism に置き換える |
| `introduce` | 新しい mechanism を契約に追加する |

delta は一つ以上の obligation を持ちます。obligation は「何を満たすか」を表す
claim と、一次検証 owner、一次検証の reference を持ちます。一次検証 owner は
obligation ごとに一つだけです。supporting evidence は一次 owner の代替ではなく、
別の property または別の role を検証するときだけ記録します。同じ property/role を
別 owner で重ねません。

許可される owner kind は次のとおりです。

`compiler`、`static_checker`、`design_review`、`existing_test`、`test_extension`、
`new_test`、`experiment`、`formal_proof`

## 既存 test の証跡

`existing_test` を一次 owner にした obligation は、次の順序を一つの証跡として
記録します。

`contract_ref → changed_mechanism_ref → observable_assertion → decidable_oracle`

さらに、変更前の mechanism が不要になったことを示す `removal_witness` を記録します。
この witness は単なる test の存在ではなく、旧経路の削除、未到達化、または旧契約が
新しい mechanism によって置き換わったことを読み取れる reference です。

## 割り当ての時点と test_designer

obligation と一次 owner は実装開始前に割り当てます。実装後に新しい検証を思いついた
ことだけで owner を差し替えません。

`test_designer` は、実装 mechanism が確立または修復された後に、static checker、
既存 checker、targeted validation では閉じない、具体的な test-owned runtime risk が
残った場合だけ起動します。起動時も未解決の oracle、specification、regression、
failure-mode を明示し、契約 instance の obligation と結び付けます。

## Hard-edge closure

semantic grouping を決める前に、次の hard edge を同じ意味の境界として閉じます。

`invariant`、`atomic_transition`、`transaction`、`lifecycle`、`effect`、
`consistency`、`substitutability`

hard-edge closure の結果は意味上の grouping です。これは責務の説明と検証の関連を
保つためのものであり、class、module、file、directory、function などの実装単位を
要求しません。実装単位は別の design boundary、既存の owner surface、依存方向、
validation route から決めます。

## 完了条件

実装開始前に、active design packet から task-local instance を辿れます。instance の
各 delta は許可された action を一つ持ち、obligation は一次 owner と参照を持ち、
既存 test の obligation は上記の証跡順序と removal witness を持ちます。hard-edge
closure は全種類を明示し、semantic grouping に構造要求を含めません。これらは
checker の存在だけでなく、設計 reviewer と実装者の readback によって完了します。
