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

The first figure contract is the execution-status view. It appears exactly once
and is not repeated as a preface or inside later result sections.

## Workflow

1. Artifact schema and status: define `input artifact schema`, status counts, and quality flags from run artifacts.
2. Expected key product: map required key set to explicit expected keys and coverage denominator.
3. Question and estimand: formulate one question and one estimand per figure.
4. Formula, grouping, weighting: write exact formulas, grouping fields, and weights for each figure.
5. Geometry: choose chart geometry that matches question, scale type, and missingness policy.
6. Coverage validation: validate complete-key handling via observed/missing/failed/not_applicable reporting.
7. Choice resolution: replace every unresolved `or`, `optional`, and alternative
   encoding with one concrete design; create separate figure blocks when both
   alternatives are required.
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

Produce a human-readable Markdown figure inventory by default. Include one row/section per figure with all fields above and colocated formula+geometry.

If a figure renderer consumes machine-readable input, include only the required machine-readable form in that renderer path and cite the file.

## Closeout

Record:

`result_visualize=complete`, `result_visualize_inventory=<path>`, `result_visualize_status_summary=<path>`
