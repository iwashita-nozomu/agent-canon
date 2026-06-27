<!--
@dependency-start
contract skill
responsibility Documents JIT-canonical algorithm Mermaid flowcharts for proof review.
upstream design algorithm-proof-exploration.md JIT-canonical IR and theorem graph workflow.
upstream design formal-proof-workflow.md checker-backed proof workflow.
upstream implementation ../../tools/agent_tools/jit_canonical_ir.py builds StableHLO-derived JIT-canonical IR and backend traces.
upstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers JIT-canonical IR into Lean evidence modules.
downstream implementation ../../.agents/skills/algorithm-flowchart/SKILL.md exposes the skill to Codex.
@dependency-end
-->

# algorithm-flowchart

## Reader Map

- Purpose: renders implemented algorithm and proof-state evidence into Mermaid
  flowcharts from JIT-canonical IR, Lean evidence, and theorem graphs.
- Use When: a task needs a visual algorithm/proof overlay for generated Lean
  evidence, theorem graphs, or canonical IR records.
- Section path: Purpose and Use When define scope; Canonical Flow is the
  mandatory checklist; Interpretation and Guardrails define what the diagram may
  claim.
- Boundary: diagrams visualize existing evidence; they do not replace proof or
  implementation validation.

## Purpose

`algorithm-flowchart` は、JIT-canonical IR、生成済み Lean evidence module、theorem
graph overlay を重ね、実装されている反復法と証明状態を Mermaid の block chart
として機械生成する skill です。

この skill は証明そのものを与えません。証明探索の前後で、今の実装 path、
solver chain、code fact、証明済み fragment、open / external / operational
assumption の位置を一目で確認するための visualization layer です。

## Use When

- 反復法、solver chain、initialization path、certificate path を
  StableHLO 由来の JIT-canonical IR から図示したい
- 「今どんなアルゴリズムになっているか」と「どこが証明済みか」を同時に見たい
- JIT-canonical record と theorem graph artifact を人間が読みやすい
  Mermaid diagram に射影したい
- 証明 note へ入れる前に、proof frontier が実装 path のどこに載っているか確認したい

## Canonical Flow

1. Target theorem と JIT-canonical public root を固定します。
   例: `lean/<topic>/main.py::main` と `<target theorem>`。

1. まだ IR がない場合は StableHLO lowering から生成します。

   ```bash
   python3 tools/agent_tools/jit_canonical_ir.py \
     --python-symbol lean/<topic>/main.py::main \
     --input-factory lean/<topic>/main.py::example_inputs \
     --out lean/<topic>/<root>_jit_canonical_ir.json \
     --stablehlo-out lean/<topic>/<root>.stablehlo.mlir \
     --backend-trace-dir lean/<topic>/backend_trace \
     --backend-trace-out lean/<topic>/<root>_backend_trace.json
   ```

1. Lean evidence module を生成します。

   ```bash
   tools/bin/agent-canon jit-ir-to-lean \
     --jit-ir lean/<topic>/<root>_jit_canonical_ir.json \
     --namespace <LeanNamespace> \
     --module-name Generated<Root>JitCanonical \
     --out lean/<topic>/<LeanNamespace>/Generated<Root>JitCanonical.lean
   ```

1. Renderer は現在の JIT-canonical record と theorem graph overlay を入力にします。
   旧 record だけを読む renderer しかない場合は、renderer を先に更新します。

1. 図を reader-facing proof note へ貼る場合は、生成済み Markdown から
   fenced `mermaid` block を引用します。手書きで Mermaid を更新せず、
   実装や証明 overlay が変わったら再生成します。

## Interpretation

- 通常の矩形 block は JIT-canonical operational op です。
- backend / dtype block は生成された backend trace coverage です。
- theorem overlay edge は proof graph の依存です。
- 色は proof overlay から来ます。
  - `verified`: checker-backed fragment がある、または graph/overlay が verified
  - `assumption`: mathematical assumption node
  - `external_assumption`: backend / external source boundary
  - `operational_assumption`: implemented trace premise
  - `open` / `unverified_with_next_witness`: まだ証明 path 上に残る witness
  - `unprovable_under_assumptions` / `refuted`: 現仮定では閉じないことを示した箇所

## Guardrails

- 図は proof ではありません。`verified` claim は Lean / checker / analyzer の
  evidence に戻して確認します。
- 実装 path が変わった場合は、IR、LemmaGraph、proof_status overlay、flowchart を
  同じ順で再生成します。
- proof-only production field を追加して図を作りません。必要な値は IR、
  LemmaGraph、`proof_status.json`、`lean/lib` profile から読みます。
- 大きな graph では `--include-code-facts` を必要な review だけに使い、
  proof note には対象 theorem に関係する diagram を載せます。
- runtime diagram に proof-only boundary、proof obligation、手書きの分岐を
  足しません。定理に必要な equation section は JIT-canonical record、
  theorem graph overlay、または対象 domain の projection tool から生成します。
