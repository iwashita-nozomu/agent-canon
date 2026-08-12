# result-visualize
<!--
@dependency-start
contract skill
responsibility Defines reusable result-visualization design for this repository.
upstream design ../canonical/ARTIFACT_PLACEMENT.md raw/summary artifact boundary
upstream design catalog.yaml upstream registry for this public skill
upstream design report-writing.md interpretation and narrative projection
upstream design html-output.md reader-facing rendering and viewport constraints
upstream design structure-planning.md figure and section planning when topology is genuinely unresolved
upstream design result-artifact-writeout.md artifact placement and manifest discipline
upstream design ../../documents/experiments/experiment-report-style.md reader-facing evidence quality
downstream implementation ../../.agents/skills/result-visualize/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Scope: Reusable Figure Contracts for indexed result artifacts, independent of any specific domain.
- Use When: Figure-level contracts are needed for plotting, status summaries, or visual comparison planning.
- Boundary: Raw persistence belongs to `result-artifact-writeout`, interpretation belongs to `report-writing`, rendering belongs to `html-output`, execution belongs to `experiment-lifecycle`.
- Section Path: Use `Purpose`, `Use When`, `Figure Contract`, `Coverage`, `Required Calculation Patterns`, `Workflow`, `Chart Families`, `Output Schema`.

## Purpose

Define reusable, testable result visualization contracts where each figure explicitly states calculation and visualization details together.

## Use When

- You need standardized figure design for one or more result artifacts.
- You need explicit coverage and denominator logic with no silent filtering.
- You need complete-key coverage planning rather than representative slicing.
- You need a per-result-view status summary before figure-level content.

## Figure Contract

Each figure must be defined as one contract block with all required fields:

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

The first figure contract is the execution-status view. It appears exactly once and is not repeated as a preface or inside later result sections.

## Workflow

1. Artifact schema and status: define `input artifact schema`, status counts, and quality flags from run artifacts.
2. Expected key product: map required key set to explicit expected keys and coverage denominator.
3. Question and estimand: formulate one question and one estimand per figure.
4. Formula, grouping, weighting: write exact formulas, grouping fields, and weights for each figure.
5. Geometry: choose chart geometry that matches question, scale type, and missingness policy.
6. Coverage validation: validate complete-key handling via observed/missing/failed/not_applicable reporting.
7. Choice resolution: replace every unresolved `or`, `optional`, and alternative encoding with one concrete design; create separate figure blocks when both alternatives are required.
8. Figure inventory: emit one figure block for each required figure.

## Coverage

Default is complete-population coverage over expected keys:
- every expected key has either `observed` or explicit status (`missing`, `failed`, `not_applicable`),
- no silent exclusion from figures.
- complete coverage is represented through density/ECDF/quantile/heatmap outputs, not by plotting every raw series.

For each figure, state explicit aggregation coverage for the index levels actually present. Do not require unused levels.

Define full-coverage behavior for distribution views (density, ECDF, quantiles, heatmaps): if a key is absent or not eligible, route it to missingness rather than dropping it from the contract.

## Required Calculation Patterns

1. Status counts
   - For expected key set $K$ and status category $s$, $N_s=\sum_{k\in K}\mathbf 1\{\operatorname{status}(k)=s\}$ and $p_s=N_s/|K|$.
2. Histogram and ECDF
   - For bin $b=[a_b,a_{b+1})$, $H_b=\sum_i\mathbf 1\{a_b\leq x_i<a_{b+1}\}$, $h_b=H_b/n$, and $\widehat F(x)=n^{-1}\sum_i\mathbf 1\{x_i\le x\}$.
3. Hierarchical expectation distinctions
   - State whether the estimand is $E[g(X)]$ or $g(E[X])$; these are not interchangeable for nonlinear $g$.
   - Across-entity and pooled distributions must state their weighting unit explicitly.
4. Paired method comparison
   - $K=K_A\cap K_B$ and $\Delta_k=y^A_k-y^B_k$; state the sign convention.
5. Coordinate-value density
   - State whether color represents counts, relative frequency, or area-normalized density.
6. Entity-by-quantile
   - $Q_e(\tau)=\inf\{x:F_e(x)\ge \tau\}$ over eligible records.
7. Event proportion
   - $r=|J|^{-1}\sum_{j\in J}\mathbf 1\{\operatorname{event}_j=1\}$ for an explicit eligible set $J$.
8. Relative metric
   - $m_j=n_j/d_j$ with explicit $d_j>0$ and a consistent denominator convention.
9. Recompute consistency residual
   - $\mathrm{resid}=y_{\mathrm{recomputed}}-y_{\mathrm{reported}}$; report signed or absolute residual intentionally.

## Chart Families

Use question-to-geometry defaults, then lock the geometry in each figure block.

- Status reporting: table or status heatmap
- Distribution checks: histogram + ECDF
- Matrix views: heatmap over two index dimensions
- Coordinate-value distributions: 2D density, hexbin, or quantile bands
- Relation checks: scatter, paired scatter, identity-line comparison, difference overlays
- Dense relation checks: hexbin or 2D density
- Order/shape checks: quantile heatmap

Other geometries are allowed when the figure contract explicitly states axis semantics, scale assumptions, and missingness handling. A final figure contract contains one resolved geometry, axis mapping, scale, grouping, and facet plan.

## Relationship To Other Skills

- `report-writing`: convert figure contracts into reader-facing narrative, limitations, and interpretation when requested.
- `html-output`: render existing artifacts or report content when HTML/browser output is explicitly requested; no intermediate experiment-report wrapper is required.
- `experiment-review`: evaluate experiment-specific adequacy, fairness, or comparison validity.
- `experiment-lifecycle`: govern run identity, execution, provenance, terminal status, rerun, and explicit publication decisions.
- `result-artifact-writeout`: persist only the concrete generated artifacts with role/checksum/readback.
- `structure-planning`: add only when owner/source/reader topology is genuinely being chosen rather than for a bounded existing-artifact render.

## Output Schema

Produce a human-readable Markdown figure inventory by default. Include one row/section per figure with all fields above and colocated formula+geometry.

If a figure renderer consumes machine-readable input, include only the required machine-readable form in that renderer path and cite the file.

## Closeout

Record the selected inventory/status outputs that were actually produced; do not create negative receipts for renderers or publication operations that did not run.
