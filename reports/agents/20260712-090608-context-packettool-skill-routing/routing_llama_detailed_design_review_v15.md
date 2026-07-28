# Routing/Llama Detailed-Design Review v15

<!--
@dependency-start
contract review
responsibility Records the independent approved routing/Llama detailed-design decision for exact target bytes.
upstream design ./routing_llama_design_brief.md exact reviewed design target.
upstream requirements ./routing_llama_user_delta_contract.md current requirements and clause identities.
upstream review ./routing_llama_detailed_design_review_v14.md pending exact-byte review request resolved by this artifact.
upstream review ./routing_llama_detailed_design_review_v13_semantic.md mandatory prior findings evidence.
upstream evidence ./routing_llama_runtime_capability_evidence_v1.json runtime operation evidence.
downstream implementation the approved design may proceed only through its own predecessor, capability, validation, and review gates.
@dependency-end
-->

## Reader Map

- Purpose: durably materialize the independent APPROVE decision already issued
  for the exact routing/Llama design bytes below.
- Reading order: review the exact decision record, source packet, finding
  closure, no-regression disposition, dependency disposition, and residual
  implementation risk.
- Boundary: this is decision transcription, not a new review. It changes no
  design, source, configuration, test, runtime, Git, or pending v14 request
  artifact.

## Exact Decision Record

```text
review_status=approved
decision=APPROVE
implementation_authorized=yes
reviewer_role=independent_detailed_design_reviewer
reviewer_independence=independent_of_design_authorship_and_implementation
decision_origin=previously_issued_exact_byte_independent_review
re_review_performed=no
reviewed_design_path=reports/agents/20260712-090608-context-packettool-skill-routing/routing_llama_design_brief.md
reviewed_design_sha256=ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7
reviewed_design_lines=854
materialized_at=2026-07-15T01:14:35+09:00
repository_branch=codex/knowledge-graph-cli
repository_commit=4e5318f6483d39b15c29b49eac1af77d56ad23cf
```

`implementation_authorized=yes` closes the design-review gate for only the
exact path, hash, and line count above. It does not waive any predecessor,
runtime-capability, source-validation, owner-review, or ship-review gate defined
by the approved design.

## Source Packet

- Reviewed design: `routing_llama_design_brief.md`, SHA-256
  `ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7`,
  854 lines.
- Review request: `routing_llama_detailed_design_review_v14.md`, SHA-256
  `f807043764615011537fada324db5128ff4e6327ebb2567f58e5836d27d0b160`,
  76 lines.
- Current requirements: `routing_llama_user_delta_contract.md`, SHA-256
  `1259a0ac56d125bc7b6494f77e37c305e6a43ee1e2300e5c1b435df1affbaaf0`,
  58 lines.
- Runtime evidence: `routing_llama_runtime_capability_evidence_v1.json`,
  SHA-256
  `6291226c8f44fdc52ce2cc1cfd92fed9626ab4690156f2796d796f30de1e84c6`,
  one line.
- Mandatory prior review evidence:
  `routing_llama_detailed_design_review_v13_semantic.md`, SHA-256
  `44772f46e5027b0432cdf9e599e200a88428694d32c292772793ec4a3f264492`,
  224 lines, decision `ESCALATE` as finding evidence rather than approval.
- Source result: the prior independent APPROVE response for the exact reviewed
  design identity. This v15 artifact only preserves that decision.

## Finding Closure

| Finding ID | Disposition | Exact approved-design evidence |
| --- | --- | --- |
| `F2-SOURCE-UNIVERSE-OVEREXPANSION` | `closed` | Lines 450, 453, and 455 make source-universe sets membership/integrity evidence with no `Q` or `X`; initial closure is request-derived, and only row-defined `X` adds an endpoint. |
| `F10-DELTA-REF-UNRESOLVED` | `closed` | Lines 537-562 define hashed artifact refs and delta/finding bindings; lines 712-714 enforce one binding per ID, byte-hash verification, and ref-only prompt resolution before send/resume. |
| `TOKEN-OBSERVABILITY-OWNER-MISSING` | `closed` | Lines 44-45, 768, 800, 813, 826, 839, and 847 bind observations to the existing comparison, role-evaluation, and dashboard owners, preserve `unmeasured` candidate absence, and add no metric schema, threshold, or token cap. |

No finding remains open against the reviewed design identity.

## No-Regression Disposition

| Prior finding scope | Disposition | Exact approved-design evidence |
| --- | --- | --- |
| `1` public primitives, types, defaults, nulls, JSON, errors, and exits | `resolved_no_regression` | Lines 63-415 retain the exact frozen public and CLI contracts. |
| `2` complete `NormalizedRecordSetV1` participation | `resolved_no_regression` | Lines 425-457 retain every family, relevance/classification rule, precedence, exclusion dominance, and finite termination proof; the source-universe repair above closes its remaining delta. |
| `3` Wiki profile/predecessor identity and state binding | `resolved_no_regression` | Lines 459-469 retain the exact relation, OID-qualified loader, provenance checks, and READY/PENDING/BLOCKED behavior. |
| `4` stale lifecycle literal replacement | `resolved_no_regression` | Lines 742-761 retain the five actual operations, legal maximum wait, timeout frontier, same-lineage resume, and terminal close. |
| `5` v13 productive-wait objection | `resolved_no_regression` | Lines 46 and 757-761 retain newest-authority resolution with zero `productive_wait` or `parent_sidecar` contract. |
| `6` one-to-one clause traces including `IDLE-CLOSE-1` | `resolved_no_regression` | Lines 31 and 820-842 retain one primary trace for every current clause; line 838 retains `IDLE-CLOSE-1`. |
| `7` historical `MINI-1` supersession | `resolved_no_regression` | Lines 31, 736-738, and 828 keep mini non-executable except the explicit read-only T14 evaluator; deterministic work remains owner-routed. |
| `8` side-effect and implementation trace joins | `resolved_no_regression` | Lines 806-842 retain complete clause, reuse, owner, effect, validation, rollback, design-section, and handoff joins without ellipsis. |
| `9` complete source packet and validation disposition | `resolved_no_regression` | Lines 779-804 and 844-852 retain exact artifacts, hashes, predecessor admission, concrete static validation, report-only honesty, and source-first test disposition. |
| `10` deterministic one-Luna-writer materialization and context reuse | `resolved_no_regression` | Lines 471-733 retain component identity, edges, conflicts, topological ordering, one writer/owner-reviewer pair, fixed fresh-context causes, and one final ship review; the hashed delta/finding repair above closes its remaining delta. |
| Token-use contract | `resolved_no_regression` | Lines 44-45, 537-562, 712-740, 768, 800, 813, 818, 826, 839, and 847 retain one reusable context per responsibility unit, delta packets, fixed fresh-generation causes, reference-only manifest normalization, continuation capsule, and existing-owner observability. |

The prior independent review found no regression in Sol/Luna/no-Llama/no-spark
policy, fixed-point scope formation, metadata routing, Wiki routing,
`RouteCatalog`, predecessor/reservation handling, formatter/dependency
dispositions, or report-only claim boundaries.

## Dependency-Review Disposition

- Full-repository command:
  `bash tools/agent_tools/run_repo_dependency_review.sh --cycle-report-only`.
- Full-repository result: `DEPENDENCY_HEADER_SCAN=pass`,
  `DEPENDENCY_HEADER_FORMAT=pass`, `DEPENDENCY_GRAPH=pass`, and
  `REPO_DEPENDENCY_REVIEW=pass`.
- Direct graph command:
  `bash tools/agent_tools/check_dependency_graph.sh --cycle-report-only`.
- Direct graph result: the downstream cycle
  `rust/agent-canon/src/dependency_manifest.rs -> rust/agent-canon/src/main.rs`
  remains visible as `DEPENDENCY_GRAPH_DOWNSTREAM_CYCLES=report_only`, while
  `DEPENDENCY_GRAPH=pass`.
- Disposition: the known cycle is retained as report-only debt and is neither
  hidden nor represented as repaired. It does not block this exact design
  approval.

## Residual Implementation Risk

- This decision approves design completeness; it is not evidence that the
  implementation exists or passes its source, config, test, owner-review, and
  ship-review gates.
- The design's four predecessor integration records and complete runtime
  capability evidence must satisfy their fail-closed gates before the relevant
  source work or runtime launch proceeds.
- The report-only `dependency_manifest.rs -> main.rs` cycle remains an explicit
  implementation dependency debt.
- Any byte change to the reviewed design invalidates this approval identity and
  requires a fresh review artifact.

## Handoff and Artifact Record

The implementation owner may consume this approval only with the exact design
identity above and the approved design's prerequisite gates. This artifact adds
no policy and does not replace the design, requirements contract, runtime
evidence, or implementation reviews.

```text
destination_class=run-local
artifact_id=routing_llama_detailed_design_review_v15
result_writeout=complete
result_source=prior_independent_review_decision_for_design_sha256_ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7
result_raw_artifact=inline_exact_decision_record
result_summary_artifact=reports/agents/20260712-090608-context-packettool-skill-routing/routing_llama_detailed_design_review_v15.md
result_manifest=inline_source_packet_and_exact_decision_record
result_overwrite_policy=unique-file
report_writing=complete
report_output_format=markdown
report_quality_checklist=pass
report_source_packet=inline
presentation_asset_packet=not_required
structure_contract=not_required_fixed_review_record
report_reviewer=not_required_materialization_only
report_rule_drift=none
document_split_decision=keep:new_versioned_review_artifact_preserves_prior_versions
PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes
PARENT_DIRECT_WRITE_EXCEPTION=explicit_user_approval
```
