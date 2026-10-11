# result-visualize
<!--
@dependency-start
contract skill
responsibility Defines reusable result-visualization design for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md raw/summary artifact boundary
upstream design catalog.yaml upstream registry for this public skill
upstream design report-writing.md interpretation and narrative projection
upstream design html-output.md reader-facing rendering and viewport constraints
upstream design structure-planning.md first-figure and section planning
upstream design result-artifact-writeout.md artifact placement and manifest discipline
upstream design ../../documents/experiments/experiment-report-style.md reader-facing evidence quality
downstream implementation ../../.codex/personal/skills/result-visualize/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Scope: Reusable Figure Contracts for indexed result artifacts, independent of any specific domain.
- Use When: Figure-level contracts are needed for plotting, status summaries, or visual comparison planning.
- Boundary: Raw persistence belongs to `result-artifact-writeout`, interpretation belongs to `report-writing`, rendering belongs to `html-output`, execution belongs to `experiment-lifecycle`.
- Section Path: Use `Purpose`, `Use When`, `Figure Contract`, `Coverage`, `Common Calculation Patterns`, `Workflow`, `Chart Families`, `Output Schema`.

## Purpose

Define reusable, testable result visualization contracts where each figure explicitly states calculation and visualization details together.

## Use When

- The requested visualization needs an explicit calculation and interpretation
  contract.
- Coverage, denominator, pairing, or missingness can change the claim a figure
  supports.

## Figure Contract

Give each requested figure a contract sufficient to reproduce and interpret its
calculation. Core inputs are the question, source, included population,
calculation, displayed geometry, and the reading the result supports. Add the
following details when they affect that figure; do not fill fields for unused
dimensions or invent extra figures to satisfy the list:

- `figure_id`: short stable identifier
- `question`: one-sentence question this figure answers
- `source_artifacts`: input paths and field names
- `population`: denominator definition, eligibility filters, and exclusions
- `index_levels`: present index keys used for grouping and aggregation (e.g., entity, replicate, time)
- `formula_or_transformation`: exact calculation for the figure
- `grouping`: grouping/faceting keys
- `weighting`: weight field or weight rule
- `denominator`: ratio numerator and denominator source
- `output_artifact`: output path and format for the figure data or artifact
- `missingness`: counts for `observed`, `missing`, `failed`, `not_applicable` and treatment
- `pre_imputation` (optional): provenance when source is already imputed
- `chart_geometry`: geometry and scale/axis specification
- `pairing_keys` (optional): keys used to align paired comparands
- `supported_reading`: exact statement supported by the calculation and population
- `conditioning_population`: slice and conditioning population used for this figure
- `scope_limit`: population or condition outside which the supported statement does not extend

An execution-status view is useful when run outcomes or missing cases affect the
comparison. Include it only when it answers a question the requested figures
need to establish.

## Workflow

For each requested figure, connect its source and relevant population to the
question, estimand, calculation, and geometry. State grouping, weighting,
pairing, units, or coverage when they affect the result. Resolve choices that
would otherwise make the figure ambiguous; keep alternatives separate only
when the user needs both comparisons. Check that the rendered figure does not
silently change the population or direction of the claim.

## Coverage

When the claim is about a complete expected population, make coverage explicit:
- every expected key has either `observed` or explicit status (`missing`, `failed`, `not_applicable`),
- no silent exclusion from figures.
- complete coverage is represented through density/ECDF/quantile/heatmap outputs, not by plotting every raw series.

For other claims, define the population the figure actually represents and
state material exclusions. For each figure, describe aggregation coverage only
for index levels that are present; do not require unused levels.

Define full-coverage behavior for distribution views (density, ECDF, quantiles, heatmaps): if a key is absent or not eligible, route it to missingness rather than dropping it from the contract.

## Common Calculation Patterns

Use the pattern that matches the figure. These examples are not a required set
of calculations for every visualization.

1. Status counts
   - For expected key set $K$ and status category $s$,
     $N_s=\sum_{k\in K}\mathbf 1\{\operatorname{status}(k)=s\}$.
   - $p_s=\frac{N_s}{|K|}$
2. Histogram and ECDF
   - For bin $b=[a_b,a_{b+1})$,
     $H_b=\sum_{i=1}^{n}\mathbf 1\{a_b\leq x_i<a_{b+1}\}$.
   - $h_b=\frac{H_b}{n}$
   - $f_b=\frac{H_b}{n(a_{b+1}-a_b)}$
   - $\widehat F(x)=\frac{1}{n}\sum_{i=1}^{n}\mathbf 1\{x_i\le x\}$
3. Hierarchical expectation distinctions
   - $z_{e,r}=g(x_{e,r})$
   - $\bar z_e=\frac{1}{|R_e|}\sum_{r\in R_e}z_{e,r}$
   - Across-entity distribution:
     $\frac{1}{|E|}\sum_{e\in E}\delta_{\bar z_e}$, with one weight per entity.
   - Pooled distribution:
     $\frac{1}{\sum_e|R_e|}\sum_{e\in E}\sum_{r\in R_e}\delta_{z_{e,r}}$,
     with one weight per record.
   - Metric of the within-entity mean:
     $g(\bar x_e)=g\left(\frac{1}{|R_e|}\sum_{r\in R_e}x_{e,r}\right)$.
   - State whether the estimand is $E[g(X)]$ or $g(E[X])$; these are not
     interchangeable for nonlinear $g$.
4. Paired method comparison
   - $K=K_A\cap K_B$
   - $\Delta_k=y^A_k-y^B_k$
   - Direction: positive $\Delta_k$ indicates method $A$ exceeds method $B$ on key $k$.
5. Coordinate-value density
   - For coordinate bins $[c_u,c_{u+1})$ and value bins $[a_v,a_{v+1})$,
     $D_{u,v}=\sum_{i=1}^{n}\mathbf 1\{c_u\leq c_i<c_{u+1},
     \ a_v\leq x_i<a_{v+1}\}$.
   - State whether color encodes $D_{u,v}$, relative frequency
     $D_{u,v}/n$, or area-normalized density.
6. Entity-by-quantile
   - Entity quantile: $Q_e(\tau)=\inf\{x:F_e(x)\ge \tau\}$ for eligible records in each entity slice.
7. Event proportion
   - For eligible index set $J$,
     $r=\frac{1}{|J|}\sum_{j\in J}\mathbf 1\{\operatorname{event}_j=1\}$.
8. Relative metric
   - $m_j=\frac{n_j}{d_j}$, where $d_j>0$ is explicit per figure and same denominator convention is used across comparands.
9. Recompute consistency residual
   - Signed residual: $\mathrm{resid}=y_{\mathrm{recomputed}}-y_{\mathrm{reported}}$
   - Absolute residual: $|\mathrm{resid}|$

## Chart Families

Use question-to-geometry defaults, then lock the geometry in each figure block.

- Status reporting: table or status heatmap
- Distribution checks: histogram + ECDF
- Matrix views: heatmap over two index dimensions
- Coordinate-value distributions: 2D density, hexbin, or quantile bands
- Relation checks: scatter, paired scatter, identity-line comparison, difference overlays
- Dense relation checks: hexbin or 2D density
- Order/shape checks: quantile heatmap

Other geometries are allowed when the figure contract explicitly states axis semantics, scale assumptions, and missingness handling.
Write every formula with Markdown math delimiters. A final figure contract
contains one resolved geometry, axis mapping, scale, grouping, and facet plan.

## Relationship To Other Skills

- `report-writing`: convert figure contracts into reader-facing narrative, limitations, and interpretation.
- `html-output`: render optional static or browser-ready outputs from the same source artifacts and consume any selected first-figure/report structure.
- `experiment-review`: evaluate experiment-specific adequacy, fairness, or comparison validity.
- `experiment-lifecycle`: govern experiment execution, run metadata, and status reporting assumptions.
- `result-artifact-writeout`: persist raw results, summaries, and manifests.

## Output Schema

Produce a human-readable Markdown figure inventory by default, with one row or
section per requested figure and its relevant calculation and geometry details.

If a figure renderer consumes machine-readable input, include only the required machine-readable form in that renderer path and cite the file.

## Native Vega-Lite Rendering

When a requested figure has a selected Vega-Lite specification, pass that native
JSON file directly to the registered `vl-convert` tool. The spec is the
renderer input, not a second AgentCanon Figure Contract schema: keep population,
formula, denominator, and interpretation in their existing project and Figure
Contract owners. Claim-critical values should already be materialized by the
project that owns them; the renderer does not calculate or infer them.

Use an input path relative to the registered project, local or inline data, the
Vega-Lite version pinned by the renderer route, and an unused output path under
the shared runtime's external tool-output directory. The shared tool container
has no network; remote data fetching is not part of this route. Preserve the
native converter's stdout, stderr, and exit status. An invalid spec is a native
conversion failure; do not add a second schema validator or output wrapper.

```bash
OUTPUT=/var/lib/agent-canon/runtime/tool-output/<figure-id>.svg
"$BOOTSTRAP" "${COMMON[@]}" tool run --root "$PROJECT_ROOT" vl-convert -- \
  vl2svg --input "$SPEC" --output "$OUTPUT" --vl-version 6.4.1
```

The existing `html-output` owner may consume the resulting static SVG as an
image asset. It does not add a second chart grammar or browser renderer.

## Closeout

When an inventory is created, give its path. Include a status summary only when
the requested visualization produced one.
