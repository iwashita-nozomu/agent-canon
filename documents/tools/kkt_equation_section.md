<!--
@dependency-start
responsibility Documents kkt_equation_section.py operator usage.
upstream implementation ../../tools/agent_tools/kkt_equation_section.py emits KKT solver-chain equation sections.
upstream implementation ../../tools/agent_tools/algorithm_expansion_ir.py emits Algorithm Expansion IR code facts.
upstream design ../../agents/skills/algorithm-proof-exploration.md defines IR-backed proof notes.
upstream design ../../agents/skills/formal-proof-workflow.md defines checker-backed proof workflow.
downstream implementation ../../tests/agent_tools/test_kkt_equation_section.py tests the generator.
@dependency-end
-->

# kkt_equation_section.py

`kkt_equation_section.py` emits a reproducible Markdown section for the
PDIPM/KKT/MINRES solver-chain equations from Algorithm Expansion IR
`code_facts`.

The tool is a projection layer. It does not prove convergence and it does not
execute the optimizer. Its job is to prevent hand-maintained KKT equation prose:
before rendering, it checks that the required reduced-KKT, regularized KKT,
preconditioner, MINRES transform, and residual-certificate facts exist in the
supplied IR files. If a required fact is missing, the command fails closed.
The displayed implementation equations are substituted from matched
`code_facts[*].expression` entries; the Markdown template must not contain a
parallel hand-maintained symbolic equation for the same runtime path.

## Typical Use

```bash
python3 tools/agent_tools/kkt_equation_section.py \
  --ir-json lean/pdipm_convergence/pdipm_solve_ir.json \
  --ir-json lean/pdipm_convergence/kkt_solve_ir.json \
  --ir-json lean/pdipm_convergence/minres_solve_ir.json \
  --out lean/pdipm_convergence/pdipm_kkt_equation_section.md
```

Use `--format json` when a checker or report needs the matched evidence list:

```bash
python3 tools/agent_tools/kkt_equation_section.py \
  --ir-json lean/pdipm_convergence/pdipm_solve_ir.json \
  --ir-json lean/pdipm_convergence/kkt_solve_ir.json \
  --ir-json lean/pdipm_convergence/minres_solve_ir.json \
  --format json
```

## Inputs

- `--ir-json`: one or more Algorithm Expansion IR JSON files. For PDIPM,
  pass the outer PDIPM IR, the nested KKT IR, and the nested MINRES IR.
- `--title`: optional H2 title for Markdown output.
- `--format`: `markdown` or `json`.
- `--out`: optional output path.

## Output

Markdown output contains IR-substituted equations for:

- implemented reduced-KKT equations at the PDIPM boundary;
- slack and inequality-multiplier back-substitution equations;
- the regularized saddle operator passed to MINRES;
- the block-diagonal preconditioner and square-root transform;
- `r_reg`, `r_unreg`, and MINRES physical `r_true` residual certificates;
- a proof-obligation subsection that is explicitly separated from the runtime
  flow;
- a source-fact evidence list with file, symbol, span, target, and expression.

JSON output contains the same `status`, `inputs`, matched `evidence`,
`missing_evidence`, and generated `markdown`.

## Guardrails

- Do not hand-write KKT equation sections in proof notes when this tool can
  generate them from current IR.
- Regenerate Algorithm Expansion IR before rerunning this tool after changes to
  `pdipm.py`, `kkt.py`, or `minres.py`.
- Treat a missing required fact as a tool or IR extraction issue, not as
  permission to manually patch the proof note.
- Keep proof obligations separate from runtime flowcharts. This tool may list
  obligations, but it must not render them as runtime branches.
