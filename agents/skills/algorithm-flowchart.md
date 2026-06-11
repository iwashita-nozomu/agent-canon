<!--
@dependency-start
responsibility Documents AST/IR-derived algorithm Mermaid flowcharts for proof review.
upstream design algorithm-proof-exploration.md algorithm IR and lemma graph workflow.
upstream design formal-proof-workflow.md checker-backed proof workflow.
upstream implementation ../../tools/agent_tools/algorithm_flowchart.py renders Mermaid diagrams.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py builds Algorithm Expansion IR.
upstream implementation ../../tools/agent_tools/algorithm_lemma_graph.py builds Lemma Dependency Graphs.
upstream implementation ../../tools/agent_tools/kkt_equation_section.py emits KKT solver-chain equation sections.
downstream implementation ../../.agents/skills/algorithm-flowchart/SKILL.md exposes the skill to Codex.
@dependency-end
-->

# algorithm-flowchart

## Purpose

`algorithm-flowchart` は、Python AST から作った Algorithm Expansion IR、
Lemma Dependency Graph、`proof_status.json` を重ね、実装されている反復法と
証明状態を Mermaid の block chart として機械生成する skill です。

この skill は証明そのものを与えません。証明探索の前後で、今の実装 path、
solver chain、code fact、証明済み fragment、open / external / operational
assumption の位置を一目で確認するための visualization layer です。

## Use When

- 反復法、solver chain、initialization path、certificate path を
  AST / IR から図示したい
- 「今どんなアルゴリズムになっているか」と「どこが証明済みか」を同時に見たい
- Algorithm Expansion IR や LemmaGraph の graph artifact を人間が読みやすい
  Mermaid diagram に射影したい
- 証明 note へ入れる前に、proof frontier が実装 path のどこに載っているか確認したい

## Canonical Flow

1. Target theorem と root symbol を固定します。
   例: `python/jax_util/optimizers/pdipm.py::_solve` と
   `PDIPM local convergence`。

1. まだ IR がない場合は AST から生成します。

   ```bash
   python3 tools/agent_tools/algorithm_expansion_ir.py \
     --python-symbol python/jax_util/optimizers/pdipm.py::_solve \
     --target-theorem "PDIPM local convergence" \
     --format json \
     --out lean/pdipm_convergence/pdipm_solve_ir.json
   ```

1. 必要な theorem profile の LemmaGraph を生成します。

   ```bash
   python3 tools/agent_tools/algorithm_lemma_graph.py \
     --ir-json lean/pdipm_convergence/pdipm_solve_ir.json \
     --target-profile local_convergence \
     --target-profile solver_chain \
     --format json \
     --out lean/pdipm_convergence/pdipm_solver_chain_lemma_graph.json
   ```

1. `algorithm_flowchart.py` で Mermaid diagram を生成します。

   ```bash
   python3 tools/agent_tools/algorithm_flowchart.py \
     --ir-json lean/pdipm_convergence/pdipm_solve_ir.json \
     --lemma-graph lean/pdipm_convergence/pdipm_solver_chain_lemma_graph.json \
     --proof-status lean/pdipm_convergence/proof_status.json \
     --include-code-facts \
     --format markdown \
     --out lean/pdipm_convergence/pdipm_algorithm_flowchart.md
   ```

   実装経路だけを見せる図では `--view runtime`、数理・solver 中核だけを
   見せる図では `--view core --include-code-facts` を使います。`proof`
   view 以外では proof status label を出しません。

1. 図を reader-facing proof note へ貼る場合は、生成済み Markdown から
   fenced `mermaid` block を引用します。手書きで Mermaid を更新せず、
   実装や証明 overlay が変わったら再生成します。

## Interpretation

- 通常の矩形 block は IR の algorithm node です。
- 波括弧 block は IR の `code_facts` です。
- 点線 edge は static dispatch / static check 系の edge です。
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
  足しません。KKT solver-chain の数式 section は
  `tools/agent_tools/kkt_equation_section.py` で IR code fact から生成します。
