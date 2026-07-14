# Active Design Packet Materialization — Detailed Design

<!--
@dependency-start
contract design
responsibility Defines one typed active-design-packet value and one validate-all, render-all, atomic run-bundle materializer shared by every producer and manifest consumer.
upstream design ../../../agents/TASK_WORKFLOWS.md owns the common design-artifact shape.
upstream design ../../../agents/canonical/CLI_ENTRYPOINTS.md owns task-start and bootstrap public behavior.
upstream design ../../../agents/canonical/CODEX_WORKFLOW.md owns design integrity and run-manifest authority.
upstream design ../../../agents/workflows/implementation-waterfall-workflow.md owns Gate 5 through Gate 8 semantics.
upstream design ../../../agents/workflows/agent-canon-pr-workflow.md owns the post-merge source-PR evidence route.
upstream design ../../../agents/canonical/ARTIFACT_PLACEMENT.md owns run-local and durable report placement.
upstream design ../../../agents/templates/design_brief.md owns the four reader-facing design sections.
upstream design ../../../documents/dependency-manifest-design.md owns dependency-header and reverse-edge semantics.
upstream design ../../../documents/runtime-log-archive.md owns immutable run-bundle archiving.
upstream implementation ../../../tools/agent_tools/agent_team.py owns run-bundle construction, config resolution, templates, manifest projection, role packets, and artifact paths.
upstream implementation ../../../tools/agent_tools/task_start.py owns the task-start producer.
upstream implementation ../../../tools/agent_tools/bootstrap_agent_run.py owns the bootstrap producer.
upstream implementation ../../../tools/agent_tools/waterfall_gate_check.py owns waterfall gate CLI behavior.
upstream implementation ../../../tools/agent_tools/github_publish.py owns verified GitHub PR metadata and post-merge evidence production.
upstream implementation ../../../tools/agent_tools/report_artifact_checks.py owns review structure and decision parsing.
upstream implementation ../../../tools/agent_tools/runtime_log_archive_git.py owns immutable report snapshots and their index.
downstream design ./active_design_packet_implementation_surface_route.txt selects this unit's exclusive implementation surface.
downstream design ./active_design_packet_implementation_request.txt carries this unit's exact implementation request.
downstream implementation ../../../tests/agent_tools/test_agent_team_templates.py checks public bundle and projection behavior.
downstream implementation ../../../tests/agent_tools/test_task_start_and_close.py checks task-start and bootstrap public behavior.
downstream implementation ../../../tests/agent_tools/test_waterfall_gate_check.py checks manifest-consumer behavior.
downstream implementation ../../../tests/agent_tools/test_github_publish.py is verify-only evidence for existing public GitHub-publish behavior; this unit mandates no predecessor test.
@dependency-end
-->

## Reader Map

この文書は active design packet の parse、resolve、reference validation、
projection、run-bundle publication、waterfall consumption を一つの置換可能な
責任単位として固定します。最初に `Design Status`、`Request Clauses`、
`Abstract Design Frame`、その直後の
`Design Side-Effect Summary` を読み、要求、責任、影響を確認します。次に
branch evidence、reuse survey、normative value、reference-resolution
algorithm、public API、atomic call graph、waterfall call path を読みます。最後に
durable predecessor-integration record、historical deletion list、path
classification、Implementation Source Packet、
Side-Effect Map、Trace、targeted validation、review handoff を使って、一人の
writer が同じ単位を source-first で実装します。

この revision は prior six-generation plan を廃止します。別 schema、caller
別 packet、gate-local parser、file 別の implementation slice は作りません。
実装はこの文書に列挙した一単位だけであり、現在の design-writing turn は
product/source/config/test を変更しません。

## Design Status

| Field | Value |
| --- | --- |
| revision | `materialization-rewrite-5` |
| review_status | `pending` |
| approval_claimed | `no` |
| implementation_authorization | `pending_exact_design_review_gate` |
| source HEAD inspected | `4e5318f6483d39b15c29b49eac1af77d56ad23cf` |
| historical active-packet commit | `9ba4bba59d7cc4aa386c6066c0c1310710619175` |
| merged PR #373 commit | `0649a1d9c08ce57972bc3bce9dfaa02c1db8e884` |
| current-turn edit paths | this design plus the two unit-owned packet files named below |
| product/source/config/test edits in this turn | `none` |
| test-design activation | `inactive` |

The implementation packet uses a one-way hash chain, so no artifact hashes a
later artifact that hashes it back:

| Artifact | SHA-256 | Lines | Ownership |
| --- | --- | ---: | --- |
| `active_design_packet_implementation_surface_route.txt` | `15164e6d67da7603cd7968bf7725397d7944f7487f062b909de1d8092de18d2b` | 218 | exclusive to `active-design-packet-materialization` |
| `active_design_packet_implementation_request.txt` | `6538c0e508a38f2914c895d8fe8bce6ce8d30bfbee4b60c84f9c6d11d668676c` | 220 | exclusive to `active-design-packet-materialization`; binds the route SHA and line count |
| this design | computed after final formatting and checks | 3522 | binds both packet SHA/line-count pairs |
| detailed-design and document-flow reviews | written after design hashing | generated by each reviewer | each binds the final design SHA |

The packet metadata field is
`responsibility_unit_id=active-design-packet-materialization`; it identifies
this design responsibility and may retain the established dashed name. The
persisted record field is separately
`predecessor_record_unit_id=active_design_packet_materialization`, which must
match the lowercase-snake `unit_id` grammar. Neither field aliases or
normalizes the other.

The existing generic files are external evidence for another graph/routing
unit and remain byte-for-byte verify-only:

| External artifact | SHA-256 | Disposition |
| --- | --- | --- |
| `implementation_request.txt` | `b9c51113697103c81a61993355c1ab596e87ec01589be241d639c4bb70b1854e` | do not edit, reuse, or overwrite |
| `implementation_surface_route.txt` | `7ea128a204d78c82bf981572891b1f0088800980aee5211634876e515951c4b4` | do not edit, reuse, or overwrite |

The current run also contains files that are not active-packet authority. They
are read only to classify ownership, not before implementation and never to
derive a clause, schedule, path, or schema:

| External or historical artifact | SHA-256 | Disposition |
| --- | --- | --- |
| `user_request_contract.md` | `7d92eff70daad8c556b7491e108280debd1b9c8af34878489886ce71a8dcb5b2` | external knowledge-graph unit; verify-only; no clause binding |
| `schedule.md` | `aa1cc275f0dcfedf3dc526fde7bdafe8e44cd12c805ccd7dc19769c52a9a0866` | operational output; verify-only; no authority or read-before-edit role |
| `active_design_packet_contract_repair_design_review_v1.md` | `1c8f14e70b163a8790e3e5785ff2011a09472b5e961911ceedbe3f8101cfa7f5` | historical review; non-authoritative |
| `active_design_packet_contract_repair_design_review_v2.md` | `abbd315ad5cca93fa90964f0257e2213c3562a5dfff12fab1368a1cacd95eb0e` | historical review; non-authoritative |
| `active_design_packet_contract_repair_design_review_v3.md` | `a07b8f40545be12be532078fe13e4bc13f3f84fdd8900009d5cff9f84ab81f91` | historical review; non-authoritative |
| `active_design_packet_contract_repair_design_review_v4.md` | `b05d2c12214483361e239e5456f1716ce24166a728230f1d66473da7900fd2fa` | historical review; non-authoritative |
| `active_design_packet_contract_repair_design_review_v5.md` | `1e097e7e6f12e7ae7f3aed89eb384bacbb87a83489bd83332918b72d36806179` | historical review; non-authoritative |
| `active_design_packet_contract_repair_design_review_v6.md` | `8c053a3ec8cd509b413c987bcb4aa39969990eb8d4b23e86c726b406a4ca2412` | historical review; non-authoritative |
| `productive_wait_contract_reconciliation_v1.md` | `14e706c816d3deb76bb60d3533800429c6cfd6dcfa83f1f418d935efcbbb9e5f` | external WAIT-1 scope evidence only; no implementation authority |
| `productive_wait_contract_design.md` | `c3701aab5c86898d2990089426cb0af0c662282178bf95d10691fc2a0f5835e7` | external v17 interim candidate; blocked; no implementation authority |
| `productive_wait_contract_detailed_design_review_v14.md` | `4caaec7250bab1615d3f6cc6374e64b9d87be38f75d8bb7d513754059117a2f7` | external historical REVISE review |
| `productive_wait_contract_detailed_design_review_v16.md` | `ed25086f1181291ace326d3f73dbbbdbe32d5fbb56a50a42c8c56156fff7f3fe` | external historical ESCALATE review |
| `productive_wait_contract_review_v1.md` | `1a6fe63239749a8dba45880498f92ac2c640c7949f40617462c72bee7b598fae` | external historical REVISE review |
| `routing_llama_design_brief.md` | `ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7` | final successor design; 854 lines; consumes this unit after integration |
| `routing_llama_detailed_design_review_v15.md` | `f428cf186f2e7dacb1cf99203eee4c0f427eefc7560da7830a2fbd241e5671d2` | 160 lines; `review_status=approved`; `decision=APPROVE`; `implementation_authorized=yes`; binds the exact routing brief path, SHA, and 854 lines above |
| `graph_design_brief.md` | producer-computed after same-SHA APPROVE; no transient live SHA is copied | external `knowledge_graph` design; verify-only input to its own predecessor record |
| `graph_design_review.md` | producer-computed with the final review bytes; no replaceable review-file SHA is copied | external live review input; intake target evidence was `5febd536a44fe5d3f1e7fe5ffecc028c8e3f0e2658182790393fb20728449f87`, and final production still requires same-SHA APPROVE |
| `container_codex_home_design.md` | successor-owner current revision; no transient live SHA is copied | external successor design; verify-only here; any stale S1 schema, IDs, filenames, or manual pair comparison must rebase to this owner's final contract |

Only the unversioned detailed-design and document-flow review paths named in
the Implementation Source Packet may authorize implementation, and both must
record APPROVE against the same final design SHA. Historical review filenames
cannot satisfy that gate.

## Request Clauses

| ID | Normative requirement |
| --- | --- |
| ADP-01 | One neutral typed value carries the Abstract Design Frame, Implementation Source Packet, Design Side-Effect Map, and Design-To-Implementation Trace. |
| ADP-02 | One owner validates all references, renders all projections, and publishes one complete run bundle atomically for every producer. |
| ADP-03 | `run.active_design_packet` is current-state authority and contains exact clause, owner, source, dependency, output, and reviewer references. |
| ADP-04 | Packet authority never comes from chat, history, schedule prose, free-text tables, or inferred wording. |
| ADP-05 | The owner consumes authoritative parser, type, config, schema, dependency-graph, and build results; AgentCanon adds only owner, dependency, projection, cross-file, and public-semantics checks. |
| ADP-06 | `create_run_bundle` is the sole canonical public delegator for materialization. |
| ADP-07 | Preserve explicit active-packet behavior under one `waterfall.design_packet.v1` shape; do not create caller-specific shapes. |
| ADP-08 | Collapse the additions from `9ba4bba5`: remove local packet types, duplicate parsers/projectors/revalidators, duplicated producer branches, partial writers, and stale internal-shape tests. |
| ADP-09 | One Luna worker changes the owner-approved responsibility graph—graph predecessor intent, active source, producers, consumer, config, templates, docs, skills, generated views, reverse edges, and checker disposition—in dependency order; tests remain verify-only unless a revised design authorizes one exact stale assertion. The only routing/Llama approval binding is `routing_llama_detailed_design_review_v15.md`, SHA-256 `f428cf186f2e7dacb1cf99203eee4c0f427eefc7560da7830a2fbd241e5671d2`, 160 lines, with `review_status=approved`, `decision=APPROVE`, and `implementation_authorized=yes` for routing design SHA-256 `ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7`, 854 lines. |
| ADP-10 | Source and public behavior are established before stale tests are rewritten; public property or regression evidence is added only when the current suite lacks that oracle. |
| ADP-11 | Validation, rendering, collision, staging, or activation failure cannot expose a partial target or advance `.active_run`; rollback failure is a distinct fatal result and never reports success. |
| ADP-12 | There is no test-count target, mandatory new-test requirement, prose inference, or fixed GitHub Actions workflow assumption. |
| ADP-13 | After a source PR merges, the generic producer emits one durable record per approved `unit_id` under one schema. The successor container requires `knowledge_graph` and `active_design_packet_materialization`, verifies each independently, rejects duplicate units, and requires byte-equal merged source OIDs without `team_manifest.yaml`, chat, schedule, aggregate-record, or document-flow inference. |
| RF-01 | Every file-scope record is self-contained: exact owner, action and reason, symbols or sections, request clauses, reverse edges and consumers, trace, validation, rollback or atomicity effect, and disposition appear in that record. |
| RF-02 | The materializer owns one persistent lock-file lifecycle, identity-safe bookkeeping snapshots, compare-before-restore, and no-clobber cleanup for first acquisition, released-file reuse, crash-stale reuse, contention, foreign state, release, and process death. |
| RF-03 | `PredecessorIntegrationErrorCode` and its phase table are total for argument, record, set, Git, serialization, publication, cleanup, and retry outcomes; no phase may report partial success. |
| RF-04 | The predecessor producer, individual verifier, and set verifier have one frozen CLI grammar, one parser/serializer owner, exact canonical stdout/stderr records, exact exit codes, and no partial set output. |
| RF-05 | Product source remains first. No test file is an unconditional edit, no predecessor test is mandatory, and no line or test count is an acceptance measure; a test edit requires post-source evidence of a conflicting stale public assertion and a new test requires a revised design naming an unresolved public oracle. |
| RF-06 | The obsolete custom design-claim parser is neither invoked nor repaired by this unit. Its check is pending until a verified `knowledge_graph` predecessor record enables graph-owned `graph status` and `graph context` validation bound to the reviewed design SHA; only then is the obsolete checker `not_applicable`. |

## Abstract Design Frame

### Responsibility model

The replaceable responsibility is `ActiveDesignPacketMaterialization`. It
selects one input by fixed precedence, decodes it once into
`ActiveDesignPacketValue`, validates every reference against authoritative
current-state indexes, derives all role/prompt/manifest/artifact projections
from that value, renders every output in memory, publishes a complete target
with no-replace semantics, and exposes the same value through the persisted
manifest consumer API.

The responsibility owns three boundaries only:

1. authoritative inputs to a typed current-state value; and
2. that value to public AgentCanon projections and atomic publication; and
3. each approved design unit and merged implementation result to one durable
   predecessor-integration record, plus read-only multi-record verification
   for successor source packets.

It does not own the Python parser, JSON/YAML parser, team config, task catalog,
dependency-manifest parser, Markdown review decision parser, template source,
workflow scheduler semantics, GitHub PR state parser, or archive snapshot
format. It consumes their results.

### Concept and layer model

```text
explicit JSON | workflow-family record | agents_config record
                         |
                         v
        one strict decoder + fixed precedence resolver
                         |
                         v
              ActiveDesignPacketValue
                         |
      +------------------+-------------------+
      |                  |                   |
      v                  v                   v
reference catalog   projection plan   manifest-consumer value
      |                  |                   |
      +--------- validate-all ---------------+
                         |
                         v
        role / prompt / template / verification /
        authority / wave-ledger / manifest projectors
                         |
                         v
             in-memory artifact set
                         |
                         v
          no-replace staged publication
                         |
                         v
       pointer bookkeeping, pointer written last

merged source PR + one same-SHA APPROVE review per unit
                         |
                         v
     generic unit-named predecessor-integration records
                         |
                         v
       existing immutable run-bundle archive
                         |
                         v
   successor read-only record and set verifiers
```

`ActiveDesignPacketValue` is the only data model for the four design sections.
Projectors may expose subsets, but they receive this value and may not decode a
second shape.

### Non-goals

- No second schema version or per-entrypoint packet schema.
- No source-document prose parser that guesses responsibilities from tables or
  keywords.
- No copy of chat, historical review text, schedule rows, work logs, or branch
  narrative into packet authority.
- No generic filesystem transaction framework outside run-bundle publication.
- No replacement for JSON, YAML, Python AST, dependency-manifest, template, or
  review-decision parsers.
- No GitHub Actions job-name, workflow-file, or runner assumption.
- No file-by-file writer split and no test-only implementation path.
- No new test file and no numerical test target.

### Future extension layers

Future fields enter only by revising this one value, the one config record, the
one decoder, every projector, the manifest consumer, docs, and public evidence
in the same responsibility unit. A future reference kind must add an
authoritative index and one resolution algorithm before it can enter the
packet. A caller-local field, unvalidated prose field, or sidecar packet is not
an extension layer.

### Evaluation axes

| Axis | Pass condition |
| --- | --- |
| identity | explicit, workflow, config, and persisted-manifest inputs decode to equal value content |
| completeness | all six reference collections resolve for all four section records before rendering |
| projection | manifest, role packets, prompt packets, created-file output, and gate consumption agree exactly |
| atomicity | a failure yields no partial target and never advances the active pointer |
| ownership | only `agent_team.py` decodes/resolves/projects active-packet semantics |
| public behavior | task-start, bootstrap, doc-start, smoke, alignment, and waterfall consumers use the same owner |
| maintainability | historical private-shape assertions are removed; evidence observes public properties |
| portability | validation selects repository commands and types, not a named CI workflow |

### Canonical-surface relationships

- `agents/agents_config.json` supplies the standard raw record.
- `agents/task_catalog.yaml` supplies workflow and role/reviewer identities.
- `tools/agent_tools/agent_team.py` owns the resolved value, projections,
  materializer, and persisted-manifest consumer API.
- `task_start.py`, `bootstrap_agent_run.py`, and `doc_start.py` are producers,
  not packet owners.
- `waterfall_gate_check.py` maps canonical consumer violations to CLI blockers;
  it owns no packet model or packet semantics.
- templates define reader-facing section structure; they are projections, not
  machine authority.
- `implementation-waterfall-workflow.md`, `CODEX_WORKFLOW.md`, and
  `CLI_ENTRYPOINTS.md` define public workflow meaning.
- dependency headers define reverse edges; the canonical graph result resolves
  declared dependency references.

## Design Side-Effect Summary

| ID | Surface | Required result |
| --- | --- | --- |
| S1 | type/config | one strict value and one exact standard config record |
| S2 | producer path | every producer calls `create_run_bundle` once and performs no packet or publication work afterward |
| S3 | projection path | role, prompt, verification, authority, wave-ledger, manifest, and public output derive from one value |
| S4 | publication | in-memory render, staged no-replace target publish, pointer bookkeeping last |
| S5 | waterfall ownership | `waterfall_gate_check.py` calls the shared loader and shared manifest-consumer validator; all gate-local packet semantics are deleted; follow `S5 → T6 → V7` for implementation and oracle |
| S6 | public surface | explicit `--active-design-packet`, manifest key, output paths, and typed failure behavior remain public evidence |
| S7 | templates/docs/skills/reverse edges | exact sections state the reference model and single-owner route; headers agree in both directions |
| S8 | tests | `9ba4bba5` private-shape additions are deleted or rewritten as missing public property/regression evidence only |
| S9 | predecessor integration | one generic producer writes one immutable record per valid `unit_id`; the archive retains both required records; the successor verifies each and requires one common merged source OID without creating an aggregate artifact |
| S10 | external overlap | seven hash-bound productive-wait/routing inputs are verify-only; the two required records integrate at one source OID first and freeze exact predecessor blocks before any narrower successor edit |

## Branch, Merge, and Scope Evidence

### Historical commit collapse

`git show --numstat 9ba4bba5` establishes the following baseline:

| Surface | Git evidence |
| --- | --- |
| total commit | `+2023/-254` |
| `agent_team.py` | `+383/-42`, 425 touched lines |
| `task_start.py` | `+54/-25`, one 79-line changed branch |
| `bootstrap_agent_run.py` | `+54/-25`, a duplicated 79-line changed branch |
| `waterfall_gate_check.py` | `+352/-109`, 461 touched lines |
| three active-packet test files | `+257`, `+270`, and `+583`: exactly 1,110 added test lines |
| config and canonical workflow docs | `agents_config.json`, `CLI_ENTRYPOINTS.md`, `CODEX_WORKFLOW.md`, and waterfall workflow |

The 1,110 figure is the baseline. It is not a retention target, deletion
target, or replacement target. The implementation must minimize evidence to
the public contract after production ownership is fixed.

### PR #373 disposition

PR #373 is merged as commit
`0649a1d9c08ce57972bc3bce9dfaa02c1db8e884`. The command
`git merge-base --is-ancestor 0649a1d9c08ce57972bc3bce9dfaa02c1db8e884 HEAD`
returns exit 0 at the inspected HEAD. The pre-merge
`pr_373_diff_intake.md` is historical evidence, not a current merge blocker.
No PR #373 condition remains in this unit.

### Remaining WAIT-1 v14 boundary

The only open WAIT-1 v14 design scope is operation resolution for these four
capabilities:

- `observe_agent_state`
- `await_agent_state_change`
- `deliver_same_task_input`
- `close_terminal_instance`

That scope owns `agents/skills/subagent-bootstrap.md` section `Subagent Return
Investigation`, its runtime skill view, and the `schedule.md` source/view map.
This active-packet unit edits none of them. The route packet classifies both
subagent-bootstrap files and `schedule.md` as verify-only, while its edit rows
name no WAIT-1 section. The resulting write-section intersection is empty.

### External overlap inputs, precedence, and integration order

The seven external files and hashes in Design Status are the complete overlap
input set. They are verify-only evidence, not forbidden unknowns. Their status
is decisive: the productive-wait design is an unapproved v17 interim candidate
with historical REVISE/ESCALATE reviews, while the routing/Llama brief declares
this active-packet unit as its serial predecessor and its durable independent
v15 approval records `review_status=approved`, `decision=APPROVE`, and
`implementation_authorized=yes` for the exact brief identity. The routing pair
remains serial successor evidence and cannot authorize a concurrent edit to
this unit or waive any predecessor gate.

Precedence and source integration order are fixed, not left to a parent:

1. One Luna worker executes the approved `knowledge_graph` source/checker
   cleanup and existing dirty semantic intent first, then this active-packet
   source, inside one owner-preserving responsibility graph and one source PR.
   Active-packet implementation remains under its unversioned equal-SHA
   reviews and V1–V11. This design owns every packet type, decoder, resolver,
   context, violation renderer, projector call order, `build_manifest`
   `run.active_design_packet` and
   `run.active_design_packet_reference_projection` blocks, atomic publisher,
   producer activation sequence, and shared waterfall consumer.
2. After that source PR merges, invoke the generic producer once for
   `knowledge_graph` and once for `active_design_packet_materialization` with
   the same PR. Archive both records in one immutable snapshot, verify each,
   then run the two-unit set verifier and require byte-equal
   `integrated_source_oid` values. Those two explicit archived records are the
   only integration inputs accepted by the successor container; no aggregate
   record or one of the seven external files may substitute for either record.
3. If WAIT-1 resumes, it follows this merge and may implement only the four
   operation-resolution capabilities listed above. In
   `workflow_monitor.py` its reserved symbols are
   `mid_task_classification`, `validate_mid_task_route_fields`,
   `normalize_mid_task_user_input`, and `append_mid_task_schedule_rows`; this
   unit owns `build_run_start_monitoring_entries`,
   `render_monitoring_artifacts`, the later-event delegation inside
   `append_monitoring`, and packet-time `project_wave_ledger_artifacts`.
   WAIT-1 consumes those pure render results and may not change their packet
   inputs, artifact replacement, or publication order. Its
   `CODEX_SUBAGENTS.md`, subagent-bootstrap, and schedule Planned Work Units
   sections remain outside this unit as already delimited.
4. The routing/Llama unit follows this unit and, where it consumes WAIT-1,
   follows an approved WAIT-1 result. Its `agent_team.py` routing projection
   may remove only routing-owned thread/spark/prompt fields in
   `manifest_run_lines`, role selection, and topology helpers; it may not alter
   the active-packet value/context parameters, either persisted packet block,
   or materializer/publication order. Its task-start/bootstrap work may remove
   only routing-owned imports, skill suggestions, and retired output keys from
   the already-integrated producer result; this unit's `RunActivationSpec`,
   one `create_run_bundle` call, returned packet/files/pointer mapping, error
   mapping, and deletion of post-create monitoring mutation are frozen
   predecessor behavior. Its lifecycle work may edit only the WAIT-1 symbols/
   sections in item 3 and cannot replace the pure renderer.

On any textual collision, the earlier dependency node above wins; the
successor rebases and narrows its stale reservation. There is no merge-by-file,
finding, test, alternate packet schema, or concurrent writer. Luna verifies
the hashes and owner records before source editing, preserves graph-owned dirty
intent, and returns one integrated handoff. Only an actual concurrent write
conflict or unresolved predecessor permits a split; the two records at one OID
then precede WAIT-1 if approved and routing/Llama.

## Installed and Existing Implementation Reuse Survey

The implementation reuses current owners rather than reproducing them:

| Existing result/API | Reuse decision |
| --- | --- |
| `json.loads` and `yaml.safe_load` | parse transport once; the shared decoder checks packet fields after parser success |
| `load_team_config` / `TeamConfig` | authoritative standard config and role/artifact registry |
| `load_task_catalog` / `TaskCatalog` | authoritative workflow and reviewer-role registry |
| `resolve_report_bundle_artifact_path` | artifact containment, symlink, and regular-file behavior |
| `resolve_workspace_document_path` | repository-root path selection |
| `markdown_document_headings` / `markdown_heading_anchor` | exact structural section index; no prose-table interpretation |
| Python `ast.parse` result | exact class/function qualname membership for `#symbol:`; AgentCanon does not parse Python grammar itself |
| `check_dependency_graph.sh --graph-tsv` | authoritative normalized dependency-edge build result |
| `report_artifact_checks.section_has_content` | structural required-section result |
| `report_artifact_checks.has_approve_decision` | authoritative review decision result |
| `report_artifact_checks.parse_review_identity` | one authoritative review path/target-SHA/decision result moved out of the waterfall gate and shared by packet and predecessor checks |
| `render_template` / `expand_template_partials` | template bytes |
| `build_default_task_authority` | task-authority content |
| `workflow_monitor` normalization and section transforms | monitoring and wave-ledger content through a pure renderer |
| `run_workflow_family`, role selection, and artifact registries | workflow and output selection |
| `github_publish.verify_remote`, `gh pr view --json`, and Git object commands | authoritative repository identity, merged PR metadata, commit identity, and ancestry process results |
| `runtime_log_archive_git.py archive-agent-report` and `push` | content-addressed immutable snapshot, manifest, index, and durable push; no manual archive copy |

AgentCanon adds only these checks: known owner/reviewer membership, declared
dependency-edge membership, cross-section joins, exact source/output
resolution, projection equality, and public gate semantics. It does not
restate parser, schema, role, dependency, template, or review rules in a
caller.

## Durable Post-Merge Predecessor Integration Record

This is a generic, repeatable post-merge contract: one independently approved
design unit produces one record, and every record has the same schema. It is
not a fifth active-design-packet section, manifest field, schedule row, special
successor aggregate, or document-flow record. A valid `unit_id` determines one
filename in the originating run. Two units therefore cannot share a target,
and no producer may reuse, truncate, or replace another unit's record.

### Exact record and canonical bytes

`tools/agent_tools/github_publish.py` owns the following frozen record. The
JSON object has exactly these fields and no extension mapping:

```python
PREDECESSOR_INTEGRATION_SCHEMA_VERSION = "agent_canon.predecessor_integration.v1"
PREDECESSOR_INTEGRATION_PRODUCER = (
    "tools/agent_tools/github_publish.py:predecessor-integration"
)
PREDECESSOR_INTEGRATION_UNIT_ID_PATTERN = r"[a-z][a-z0-9_]{0,63}"
PREDECESSOR_TARGET_REMOTE = "origin"
PREDECESSOR_TARGET_BRANCH = "main"
PREDECESSOR_TARGET_MAIN_REF = "refs/remotes/origin/main"


def predecessor_integration_filename(unit_id: str) -> str:
    if re.fullmatch(PREDECESSOR_INTEGRATION_UNIT_ID_PATTERN, unit_id) is None:
        raise PredecessorIntegrationError(
            code="invalid_unit_id",
            phase="arguments",
            unit_id=unit_id,
            path=None,
            field="unit_id",
            expected=PREDECESSOR_INTEGRATION_UNIT_ID_PATTERN,
            observed=unit_id,
            command=None,
            returncode=None,
            retryable=False,
        )
    return f"predecessor_integration.{unit_id}.json"


@dataclass(frozen=True)
class PredecessorIntegrationRecord:
    schema_version: str
    unit_id: str
    design_path: str
    design_sha256: str
    approve_review_path: str
    approve_review_sha256: str
    source_pr_url: str
    source_pr_number: int
    integrated_source_oid: str
    observed_target_main_oid: str
    produced_at: str
    producer: str
    artifact_sha256: str


PredecessorIntegrationErrorCode = Literal[
    "usage_error",
    "invalid_unit_id",
    "duplicate_unit_id",
    "unit_id_mismatch",
    "integrated_source_oid_mismatch",
    "non_ancestor",
    "malformed_json",
    "truncated_json",
    "stale_record",
    "missing_record",
    "schema_version_mismatch",
    "record_shape_mismatch",
    "path_mismatch",
    "filename_mismatch",
    "record_collision",
    "record_hash_mismatch",
    "design_hash_mismatch",
    "review_hash_mismatch",
    "same_sha_approve_mismatch",
    "archive_hash_mismatch",
    "source_pr_mismatch",
    "git_object_missing",
    "process_failure",
    "serialization_failure",
    "publication_failure",
    "cleanup_failure",
    "set_inconsistency",
]


PredecessorIntegrationPhase = Literal[
    "arguments",
    "load",
    "decode",
    "schema",
    "path",
    "review",
    "remote",
    "pr",
    "git",
    "serialize",
    "publish",
    "cleanup",
    "archive",
    "set",
]


@dataclass(frozen=True)
class PredecessorIntegrationError(Exception):
    code: PredecessorIntegrationErrorCode
    phase: PredecessorIntegrationPhase
    unit_id: str | None
    path: str | None
    field: str | None
    expected: str | None
    observed: str | None
    command: tuple[str, ...] | None
    returncode: int | None
    retryable: bool
```

The first twelve fields above, in that order, are the digest payload.
`artifact_sha256` is SHA-256 of UTF-8 JSON for those twelve fields with
`ensure_ascii=False`, `sort_keys=True`, separators `(",", ":")`, followed by
LF. The final artifact is the same canonical JSON object with
`artifact_sha256` added, again sorted with the same separators and one LF.
This explicit detached-payload rule avoids an impossible self-referential file
digest. The immutable archive manifest independently records SHA-256 of the
complete final file bytes.

`schema_version` and `producer` equal the constants above. `unit_id` must
`fullmatch` the ASCII grammar and the target basename must equal
`predecessor_integration_filename(unit_id)`; a normalized ID, alias, dash, path
separator, extension, or caller-selected filename is rejected rather than
rewritten. `design_path` and `approve_review_path` are normalized repository-
relative POSIX paths under the same `reports/agents/<run-id>/` directory. Both
hashes are lowercase SHA-256 of exact file bytes. `source_pr_number` is a
positive integer; both OIDs are the full lowercase 40-hex commit IDs returned
by Git/GitHub for this repository. `produced_at` is the producer's single UTC
RFC 3339 timestamp with `Z`. No field is accepted from chat, a schedule,
`team_manifest.yaml`, a PR body, another unit's record, or an aggregate record.

`load_predecessor_integration_record` is the only record parser. It reads one
bounded byte string, never returns a mapping, and applies this classification
before constructing the dataclass:

1. An absent path is `missing_record`. An empty file or a file without exactly
   one terminal LF is `truncated_json`.
2. UTF-8 failure with `reason == "unexpected end of data"` is
   `truncated_json`; every other UTF-8 failure is `malformed_json`.
3. JSON decoding uses one duplicate-key-rejecting `object_pairs_hook`. A
   duplicate key is `malformed_json`. A `JSONDecodeError` is
   `truncated_json` only when its position equals the payload length or its
   message begins `Unterminated string`; every other decoder failure is
   `malformed_json`.
4. A decoded non-object, missing or unknown key, wrong JSON type, noncanonical
   key order/spacing/escaping, extra LF, or byte mismatch against the canonical
   serializer is `record_shape_mismatch`. A nonmatching `schema_version` is
   `schema_version_mismatch` instead.
5. Field semantics are checked in record order. Path containment or
   design/review run-directory disagreement is `path_mismatch`; derived
   basename disagreement is `filename_mismatch`; digest, review, PR, and
   ancestry checks retain their dedicated codes. No caller reparses the bytes.

The error rendering fields are the fields of `PredecessorIntegrationError` in
the order shown above. `expected` and `observed` are bounded to 512 Unicode
scalar values; `command` is an argv tuple, never a shell string; captured
stdout and stderr never become public messages. The code-to-phase, exit,
cleanup, and retry map is total and normative:

| Phase and first failing condition | Typed code | Required message fields | Exit | State, cleanup, and retry |
| --- | --- | --- | --- | --- |
| `arguments`: parser grammar, missing/repeated/forbidden flag, invalid `UNIT_ID=PATH`, or unsupported value | `usage_error` | `field`, `expected`, `observed`; other optional fields null | `2` | No file or command work; no stdout; correct the invocation before retry. |
| `arguments`: `unit_id` fails the ASCII grammar | `invalid_unit_id` | `unit_id`, `field=unit_id`, grammar in `expected`, input in `observed` | `2` | No file or command work; retry only with a corrected ID. |
| `set`: a required, input-key, or verified unit repeats | `duplicate_unit_id` | repeated `unit_id`, `field`, first and repeated positions | `6` | No set result and no writes; correct the entire set before retry. |
| `set`: CLI key and decoded record ID differ | `unit_id_mismatch` | `unit_id`, `path`, `field=unit_id`, CLI key, decoded ID | `6` | Suppress all set stdout; no writes; correct the binding before retry. |
| `set`: verified records carry unequal integrated OIDs | `integrated_source_oid_mismatch` | `field=integrated_source_oid`, first OID, differing OID, differing unit | `6` | Suppress all set stdout; no writes; regenerate or select records from one merge before retry. |
| `set`: missing/unexpected/unpaired keys, zero required IDs, unequal archive snapshot locators, or result cardinality/order disagreement | `set_inconsistency` | `field`, exact required ordered IDs, exact observed ordered keys | `6` | Suppress all set stdout; no writes; correct the complete set before retry. |
| `load`: record path is absent or a required set record is absent | `missing_record` | `unit_id`, `path`, `field=record_path`, expected existence, observed missing | `3` for an individual operation; `6` during set composition | No writes; retryable only after the named immutable record exists. |
| `decode`: empty, missing-final-LF, EOF-position JSON, unterminated string, or incomplete UTF-8 | `truncated_json` | `unit_id`, `path`, `field=record`, canonical complete JSON+LF expectation, bounded decoder position/reason | `3` | No writes; replace from the canonical producer, never append or repair in place. |
| `decode`: other UTF-8/JSON failure or duplicate raw key | `malformed_json` | `unit_id`, `path`, `field=record`, canonical JSON expectation, bounded decoder reason | `3` | No writes; replace from the canonical producer, never normalize in the verifier. |
| `schema`: wrong schema version | `schema_version_mismatch` | `unit_id`, `path`, `field=schema_version`, fixed schema, observed value | `3` | No writes; regenerate with the integrated producer. |
| `schema`: individual `--expected-unit-id` differs from the decoded record ID | `unit_id_mismatch` | decoded `unit_id`, `path`, `field=unit_id`, expected ID, decoded ID | `3` | No stdout or writes; select the canonical unit record before retry. |
| `schema`: unknown/missing field, wrong type, noncanonical bytes, or record cardinality failure | `record_shape_mismatch` | `unit_id`, `path`, exact field or `record`, expected shape, observed shape | `3` | No writes; regenerate; the verifier never projects a partial record. |
| `path`: escape, absolute path, symlink, report-directory disagreement, archive locator mismatch, or nonregular input | `path_mismatch` | `unit_id`, offending `path`, `field`, required root/run relationship, observed normalized path/type | `3` | No writes; correct the explicit locator before retry. |
| `path`: basename is not `predecessor_integration_filename(unit_id)` | `filename_mismatch` | `unit_id`, `path`, `field=record_path`, derived basename, observed basename | `3` | No writes; move nothing; consume the canonical derived path. |
| `schema`: detached payload digest differs | `record_hash_mismatch` | `unit_id`, `path`, `field=artifact_sha256`, recomputed digest, recorded digest | `3` | No writes; replace from archive or producer. |
| `review`: design bytes differ | `design_hash_mismatch` | `unit_id`, design path, `field=design_sha256`, recomputed digest, recorded digest | `3` | Producer temp absent or removed; verifier writes nothing; retry after correct immutable inputs. |
| `review`: review bytes differ | `review_hash_mismatch` | `unit_id`, review path, `field=approve_review_sha256`, recomputed digest, recorded digest | `3` | Producer temp absent or removed; verifier writes nothing; retry after correct immutable inputs. |
| `review`: review path, target SHA, or decision is not exact APPROVE | `same_sha_approve_mismatch` | `unit_id`, review path, failing review field, required design path/SHA/APPROVE, parsed result | `3` | Producer temp absent or removed; verifier writes nothing; obtain a new authoritative review before retry. |
| `archive`: complete-file digest or sibling manifest entry differs | `archive_hash_mismatch` | `unit_id`, manifest path, exact manifest field, recomputed complete-file digest, manifest value | `3` | No writes; use one intact immutable snapshot before retry. |
| `pr`: URL, number, merged state, base, or merge OID differs | `source_pr_mismatch` | `unit_id`, `field`, record value, verified GitHub value, argv in `command`, return code | `4` | Producer temp absent or removed; verifier writes nothing; retry after remote metadata is authoritative. |
| `git`: required commit cannot be resolved locally | `git_object_missing` | `unit_id`, `field`, required OID, observed missing, literal argv and return code | `4` | No record or set output; verifier never fetches; caller may fetch fixed `origin/main` and retry. |
| `git`: required ancestor relation returns exit `1` | `non_ancestor` | `unit_id`, `field`, ancestor and descendant OIDs, literal argv, `returncode=1` | `4` | No producer or set output; no writes; retry only after selecting valid integrated evidence. |
| `git`: record's observed main was valid but is not an ancestor of current fixed `origin/main` | `stale_record` | `unit_id`, record path, `field=observed_target_main_oid`, fixed current main OID, recorded observed OID, literal argv, `returncode=1` | `3` | No writes; produce a new record only through a new approved unit integration; the verifier never rewrites it. |
| `remote`, `pr`, or `git`: process launch fails or a command returns a status not assigned above | `process_failure` | `unit_id`, phase field, expected status, observed status, literal argv and return code | `4` | Producer temp removed if created; verifier and set write nothing; retryable only for a corrected or transient external-process condition. |
| `serialize`: canonical record/result serialization fails before a temp is complete | `serialization_failure` | `unit_id`, `field=record` or `result`, canonical schema, bounded exception class | `5` | Remove an identity-owned temp if one exists; target absent; retry only after implementation repair. |
| `publish`: temp write/verify, atomic rename, or directory sync fails | `publication_failure` | `unit_id`, target path, publication step, expected durable state, errno/status | `5` | Remove an identity-owned pre-rename temp. After a successful rename with failed directory sync, emit no success and leave the complete target for idempotent verify/retry; never expose partial bytes. |
| `publish`: derived target exists but is not byte-identical and fully verified | `record_collision` | `unit_id`, target path, `field=record_path`, expected complete digest, observed type/digest | `5` | Do not overwrite, unlink, truncate, or rename the target; remove only this invocation's temp; retry only after owner collision resolution. |
| `cleanup`: identity-owned producer temp cannot be removed after a pre-publication failure | `cleanup_failure` | `unit_id`, temp path, `field=producer_temp`, recorded identity/digest, bounded errno or observed identity | `5` | Emit no success, never touch a mismatched object or target, retain the exact temp path for owner cleanup, and retry only after identity-safe cleanup or implementation repair. |

Every row emits exactly one typed error. The producer emits no success JSON
until durable publication or verified idempotent reuse completes. The
individual verifier emits no success JSON until every check completes. The set
verifier buffers all individual results, discards them on any failure, and
emits no partial array, count, common OID, or per-unit success line.

For this successor dependency, the two producer inputs are fixed as follows:

| `unit_id` | `design_path` | `approve_review_path` | Current readiness |
| --- | --- | --- | --- |
| `knowledge_graph` | `reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md` | `reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_review.md` | reject unless producer-time SHA-256 of the design equals the review target and the decision is APPROVE; intake review evidence targeted `5febd536a44fe5d3f1e7fe5ffecc028c8e3f0e2658182790393fb20728449f87`, while mutable graph-owner working bytes are deliberately not frozen here |
| `active_design_packet_materialization` | `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md` | `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_detailed_design_review.md` | pending this design's final SHA and same-SHA APPROVE |

The review path is singular in every record. It is the unit's detailed-design
APPROVE evidence; document-flow review remains a pre-implementation workflow
gate and adds no persisted field. Relative metadata such as
`graph_design_brief.md` is resolved once against the review file's report
directory, normalized to a repository-relative POSIX path, and then compared
to `design_path`; absolute paths, `..`, symlink escape, or another report
directory fail `path_mismatch`.

### Authoritative review identity result

The existing gate-local review regexes move once to the review parser owner;
they are not copied into this producer or the waterfall consumer:

```python
@dataclass(frozen=True)
class ReviewIdentityResult:
    design_artifact_path: str | None
    review_target_sha256: str | None
    decision_approved: bool


def parse_review_identity(text: str) -> ReviewIdentityResult: ...
```

`tools/agent_tools/report_artifact_checks.py#parse_review_identity` consumes
the existing structural/decision parser results and returns these fields.
Both the shared packet validator and predecessor producer consume this result.
The producer resolves `design_artifact_path` by the report-relative rule above,
requires exact normalized equality with `design_path`, requires exact
`review_target_sha256 == design_sha256`, and
`decision_approved is True`. The review file's own SHA is stored separately as
`approve_review_sha256`. This is the same-SHA APPROVE gate; filename, basename,
or prose similarity cannot satisfy it.

### Canonical producer after source PR merge

The sole producer API and CLI action are:

```python
def produce_predecessor_integration_record(
    *,
    root: Path,
    report_dir: Path,
    unit_id: str,
    design_path: PurePosixPath,
    approve_review_path: PurePosixPath,
    pr: str,
    remote: RemoteVerification,
    runner: Runner,
) -> Path: ...
```

```bash
python3 tools/agent_tools/github_publish.py predecessor-integration \
  --user-task "<current merge task>" \
  --repo <verified-owner/repository> \
  --pr <shared-merged-source-pr-number-or-url> \
  --report-dir reports/agents/20260712-090608-context-packettool-skill-routing \
  --unit-id knowledge_graph \
  --design-path reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md \
  --approve-review-path reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_review.md

python3 tools/agent_tools/github_publish.py predecessor-integration \
  --user-task "<current merge task>" \
  --repo <verified-owner/repository> \
  --pr <shared-merged-source-pr-number-or-url> \
  --report-dir reports/agents/20260712-090608-context-packettool-skill-routing \
  --unit-id active_design_packet_materialization \
  --design-path reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  --approve-review-path reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_detailed_design_review.md
```

Each action runs only after the same named source PR reports merged. The
PR-processing owner invokes the command once per unit; there is no multi-unit
producer mode. Each invocation executes this order exactly:

1. Call existing `verify_remote`; use its repository result and require its
   remote name to equal `PREDECESSOR_TARGET_REMOTE`. A different remote name
   fails before any record write because the exact record has no remote field
   and therefore cannot safely bind another ref.
2. Call `gh pr view <pr> --repo <verified-repo> --json
   number,url,state,mergedAt,mergeCommit,baseRefName`; require
   `state == "MERGED"`, non-null `mergedAt`, `baseRefName == "main"`, a positive
   number, an HTTPS URL for the verified repository, and one full
   `mergeCommit.oid`. These parser results populate the PR fields and
   `integrated_source_oid`.
3. Run `git fetch origin main`, then
   `git rev-parse refs/remotes/origin/main^{commit}`. That exact result
   populates `observed_target_main_oid`.
4. Run
   `git merge-base --is-ancestor <integrated_source_oid>
   <observed_target_main_oid>` and require exit 0. Exit 1 is a semantic failure;
   any other status is a Git-process failure. The literal argv and exit status
   are emitted as producer evidence.
5. Resolve the two declared files under `root` without symlink escape, hash
   exact bytes, decode the review through `parse_review_identity`, and enforce
   the same-SHA APPROVE checks above.
6. Validate `unit_id`, derive the target only through
   `predecessor_integration_filename`, build all record fields in memory, and
   compute `artifact_sha256`. Canonically serialize the complete bytes before
   opening a path. Create one no-follow exclusive sibling
   `.<derived-basename>.tmp.<pid>.<128-bit-nonce>` at mode `0600`, write,
   flush, fsync, close, reopen no-follow, and verify type, owner, mode, size,
   and complete-file SHA. Publish with
   `renameat2(RENAME_NOREPLACE)`, chmod the published file to `0644`, and fsync
   the report directory. A pre-existing byte-identical record that passes the
   complete loader and verifier is idempotent success; a differing, malformed,
   symlink, nonregular, filename-mismatched, or foreign-owned target is
   `record_collision`. Pre-rename failure removes only the temp whose recorded
   device/inode still matches; post-rename directory-sync failure leaves the
   complete target, emits `publication_failure`, and permits only idempotent
   verification/retry. No path is overwritten or partially exposed.

The producer fixes the unit-ID grammar, filename derivation, schema, producer,
base branch, field derivation, and output directory. `unit_id`, the two
approved artifact paths, PR identifier, and verified repository are explicit
operation inputs from the unit's Source Packet, not inferred design decisions.
For this source PR the two invocations use the exact table above and the same
`--pr`; a stale graph review causes the first invocation to fail before any
record write rather than weakening the same-SHA gate.

### Durable publication and successor locator

Immediately after production, the same PR-processing route runs the existing
archive owner without manually copying or rewriting the record:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report \
  --report-dir reports/agents/20260712-090608-context-packettool-skill-routing
python3 tools/agent_tools/runtime_log_archive_git.py push \
  --message "Archive predecessor integration records"
```

The durable records are therefore exactly:

```text
.agent-canon/log-archive/agent-reports/<repo-key>/
  20260712-090608-context-packettool-skill-routing/<snapshot-id>/
  predecessor_integration.knowledge_graph.json
  predecessor_integration.active_design_packet_materialization.json
```

The two files share one sibling `archive_manifest.json`, which gives each
complete-file SHA; the append-only `agent-reports/<repo-key>/index.jsonl` gives
the snapshot locator. Archive runs once only after both run-local producers
succeed. The PR-processing owner reports the archive command's exact
destination and declares `predecessor_integration=complete` only after archive
push, both individual verifications, and the set verification below pass. A
successor's Implementation Source Packet records both explicit archived paths,
the sibling manifest path, snapshot ID, each payload `artifact_sha256`, and
each complete-file SHA. It never searches the latest run, active pointer,
team manifest, chat, or schedule, and it never writes an aggregate record.

### Read-only verifier and ancestry evidence

The public read-only APIs and CLI are:

```python
@dataclass(frozen=True)
class PredecessorIntegrationVerification:
    record: PredecessorIntegrationRecord
    record_path: Path
    archive_manifest_path: Path
    complete_file_sha256: str
    design_sha256_verified: bool
    approve_review_sha256_verified: bool
    same_sha_approve_verified: bool
    source_pr_identity_verified: bool
    integrated_is_ancestor_of_observed_main: bool
    observed_main_is_ancestor_of_current_main: bool


@dataclass(frozen=True)
class PredecessorIntegrationInput:
    expected_unit_id: str
    record_path: Path
    archive_manifest_path: Path


@dataclass(frozen=True)
class PredecessorIntegrationSetVerification:
    verified_records: tuple[PredecessorIntegrationVerification, ...]
    common_integrated_source_oid: str


def load_predecessor_integration_record(
    record_path: Path,
) -> PredecessorIntegrationRecord: ...


def verify_predecessor_integration_record(
    *,
    root: Path,
    record_path: Path,
    archive_manifest_path: Path,
    expected_unit_id: str,
    runner: Runner,
) -> PredecessorIntegrationVerification: ...


def verify_predecessor_integration_set(
    *,
    root: Path,
    inputs: tuple[PredecessorIntegrationInput, ...],
    required_unit_ids: tuple[str, ...],
    runner: Runner,
) -> PredecessorIntegrationSetVerification: ...
```

```bash
python3 tools/agent_tools/github_publish.py verify-predecessor-integration \
  --record <explicit-archived-active-packet-record-path> \
  --archive-manifest <same-snapshot>/archive_manifest.json \
  --expected-unit-id active_design_packet_materialization

python3 tools/agent_tools/github_publish.py verify-predecessor-integration-set \
  --required-unit-id knowledge_graph \
  --required-unit-id active_design_packet_materialization \
  --record knowledge_graph=<explicit-archived-knowledge-graph-record-path> \
  --archive-manifest knowledge_graph=<same-snapshot>/archive_manifest.json \
  --record active_design_packet_materialization=<explicit-archived-active-packet-record-path> \
  --archive-manifest active_design_packet_materialization=<same-snapshot>/archive_manifest.json
```

### Frozen predecessor CLI grammar, mapping, and emission

`tools/agent_tools/github_publish.py#build_parser` remains the sole argument-
parser owner, `run` remains the sole action dispatcher, and `emit_summary`
remains the sole public serializer/emitter. The implementation adds
`add_predecessor_integration_arguments`,
`add_predecessor_verification_arguments`, and
`add_predecessor_set_verification_arguments` beneath `build_parser`; no action
or caller constructs a second parser. A private
`_canonical_json_line_bytes(mapping)` performs the module's record and CLI JSON
serialization with `ensure_ascii=False`, `sort_keys=True`,
`separators=(",", ":")`, strict finite values, UTF-8, and one LF. Record
loading remains owned by `load_predecessor_integration_record`; CLI parsing
never decodes a record.

The complete grammar is below. Global `--root ROOT` occurs zero or one time
before the action and defaults to `.`; it resolves to the verified repository
root. No action accepts `--format`, `--summary-out`, `--remote`, `--branch`,
`--base`, `--ref`, or an unlisted positional argument.

```text
github_publish.py [--root ROOT] predecessor-integration
  --user-task NONEMPTY_TEXT
  --repo OWNER/REPOSITORY
  --pr POSITIVE_DECIMAL_OR_CANONICAL_HTTPS_PR_URL
  --report-dir REPO_RELATIVE_REPORT_DIRECTORY
  --unit-id LOWERCASE_SNAKE_UNIT_ID
  --design-path REPO_RELATIVE_REPORT_FILE
  --approve-review-path REPO_RELATIVE_REPORT_FILE

github_publish.py [--root ROOT] verify-predecessor-integration
  --record REPO_RELATIVE_ARCHIVED_RECORD_FILE
  --archive-manifest REPO_RELATIVE_SIBLING_ARCHIVE_MANIFEST
  --expected-unit-id LOWERCASE_SNAKE_UNIT_ID

github_publish.py [--root ROOT] verify-predecessor-integration-set
  --required-unit-id LOWERCASE_SNAKE_UNIT_ID
  [--required-unit-id LOWERCASE_SNAKE_UNIT_ID ...]
  --record LOWERCASE_SNAKE_UNIT_ID=REPO_RELATIVE_ARCHIVED_RECORD_FILE
  [--record LOWERCASE_SNAKE_UNIT_ID=REPO_RELATIVE_ARCHIVED_RECORD_FILE ...]
  --archive-manifest LOWERCASE_SNAKE_UNIT_ID=REPO_RELATIVE_SIBLING_ARCHIVE_MANIFEST
  [--archive-manifest LOWERCASE_SNAKE_UNIT_ID=REPO_RELATIVE_SIBLING_ARCHIVE_MANIFEST ...]
```

`OWNER/REPOSITORY` is exactly the slug returned by existing `verify_remote`.
The PR value is either a positive decimal integer or
`https://github.com/<verified-owner>/<verified-repository>/pull/<positive>`;
fragments, query strings, aliases, branch selectors, and another host are
invalid. Every repository path uses `/`, is relative, contains no empty, `.`
or `..` segment, and must pass the no-symlink containment resolver. Producer
design/review paths must be regular files below `--report-dir`. The producer
target is not a flag: it is exactly
`report_dir / predecessor_integration_filename(unit_id)`. Individual
verification derives the expected basename from the decoded unit. Set values
split on the first `=`; the key is never normalized. At least one required ID
is mandatory; required-ID order is retained; record and manifest key sets must
equal that ordered ID set, with one value per key and one shared archive
snapshot directory.

For recognized predecessor actions, `build_parser` uses non-exiting argument
errors and `main` converts every grammar error to `usage_error`; legacy publish
actions retain their existing parser behavior. `run` dispatches in this exact
order:

```text
main
  -> build_parser
  -> parse one action namespace
  -> run
     -> predecessor-integration
        -> verify_remote
        -> produce_predecessor_integration_record
     -> verify-predecessor-integration
        -> verify_predecessor_integration_record
     -> verify-predecessor-integration-set
        -> construct ordered PredecessorIntegrationInput tuple
        -> verify_predecessor_integration_set
  -> construct one complete result or one PredecessorIntegrationError
  -> emit_summary once to stdout on success or stderr on failure
```

`agents/canonical/CLI_ENTRYPOINTS.md` gains one `Predecessor Integration`
section containing all three actions and this call graph. The PR workflow,
canonical/runtime PR-processing skill, and `documents/tools/github_publish.md`
reference that section; none restates a parser, serializer, schema, or exit
table.

Success writes exactly one canonical JSON line to stdout and writes nothing to
stderr. Key order is the lexicographic order produced by `sort_keys=True`;
nested mappings use that order, arrays retain the operation order, and paths
are repository-relative POSIX strings. The producer result has exactly:

```json
{"action":"predecessor-integration","artifact_sha256":"<hex64>","command_evidence":[{"argv":["<arg>"],"returncode":0}],"complete_file_sha256":"<hex64>","idempotent":false,"path":"<repo-path>","schema":"agent_canon.predecessor_integration.cli_result.v1","status":"ok","unit_id":"<unit-id>"}
```

The individual verification result has exactly:

```json
{"action":"verify-predecessor-integration","archive_manifest_path":"<repo-path>","artifact_sha256":"<hex64>","command_evidence":[{"argv":["<arg>"],"returncode":0}],"complete_file_sha256":"<hex64>","integrated_source_oid":"<hex40>","observed_target_main_oid":"<hex40>","record_path":"<repo-path>","schema":"agent_canon.predecessor_integration.cli_result.v1","status":"ok","unit_id":"<unit-id>"}
```

The set result has exactly this shape; `records` follows required-ID order and
each nested `command_evidence` is the already-consumed individual result:

```json
{"action":"verify-predecessor-integration-set","common_integrated_source_oid":"<hex40>","records":[{"artifact_sha256":"<hex64>","command_evidence":[{"argv":["<arg>"],"returncode":0}],"complete_file_sha256":"<hex64>","integrated_source_oid":"<hex40>","observed_target_main_oid":"<hex40>","record_path":"<repo-path>","unit_id":"<unit-id>"}],"required_unit_ids":["<unit-id>"],"schema":"agent_canon.predecessor_integration.cli_set_result.v1","status":"ok"}
```

`command_evidence` includes every external argv and return code in invocation
order but never command stdout/stderr. The producer's `idempotent` is `true`
only for a pre-existing, byte-identical, fully verified canonical record.

Failure writes no stdout and exactly one canonical JSON line to stderr. It has
all fields below, including explicit nulls; its `exit_code` is the total table
value above, and `main` returns that value:

```json
{"action":"<action>","code":"<typed-code>","command":null,"exit_code":3,"expected":null,"field":null,"observed":null,"path":null,"phase":"<phase>","retryable":false,"returncode":null,"schema":"agent_canon.predecessor_integration.cli_error.v1","status":"error","unit_id":null}
```

The set action constructs the complete in-memory result before invoking
`emit_summary`. On any input or individual failure it discards every verified
prefix and emits only the error line; stdout remains zero bytes. Exit `0`
means the complete action succeeded, `2` means usage/ID grammar, `3` means
record/schema/path/hash/review/archive/stale input, `4` means remote/PR/Git,
`5` means serialization/publication/collision/cleanup, and `6` means set
composition.

The single-record verifier writes nothing and never runs `git fetch`. It
requires exact fields only, validates the ID grammar, requires the record
basename to equal `predecessor_integration_filename(record.unit_id)`, requires
`record.unit_id == expected_unit_id`, recomputes the twelve-field payload
digest, and requires equality with `artifact_sha256`. That field is the
canonical record hash; it is not the complete-file hash. The verifier then
checks the archive manifest's complete-file entry, maps the two repository-
relative report paths into the same immutable snapshot, hashes them, and calls
`parse_review_identity` for the same-SHA APPROVE check. It calls the same read-
only `gh pr view <source_pr_url>` query and requires URL, number, merged state,
main base, and merge OID equality with the record. It requires all three
commits to exist locally, then runs these exact read-only commands:

```bash
git merge-base --is-ancestor \
  <integrated_source_oid> <observed_target_main_oid>
git merge-base --is-ancestor \
  <observed_target_main_oid> refs/remotes/origin/main
```

The verifier has no ref or remote option and rejects a repository whose
canonical `origin/main` ref is absent. The integrated-to-observed command's
exit `1` is `non_ancestor`; the observed-to-current command's exit `1` is
`stale_record`; any other nonzero follows the total process map. Missing
objects, hash mismatch, unknown field, path escape, non-unit filename/ID, PR
identity mismatch, review mismatch, or archive-manifest mismatch returns its
dedicated typed failure and no partial success.

`verify_predecessor_integration_set` is a generic in-memory composition of the
single-record verifier, not a persisted schema. Its algorithm is exact:

1. Validate every `required_unit_ids` entry with the unit grammar and reject a
   duplicate before reading a file.
2. Parse repeated CLI `UNIT_ID=PATH` values without normalization. Require
   exactly one `--record` and one `--archive-manifest` for each input key;
   reject duplicate keys, an unpaired key, a missing required key, or an
   unexpected key before record verification.
3. Construct one `PredecessorIntegrationInput` per required ID and call
   `verify_predecessor_integration_record` exactly once in
   `required_unit_ids` order. Do not reparse a record, review, manifest, PR, or
   Git result in the set verifier.
4. Reject duplicate verified `record.unit_id` values even if they arrived
   through distinct paths. Require the verified unit set to equal the required
   unit set exactly.
5. Compare all `integrated_source_oid` strings for byte equality to the first
   result. Zero records or a missing required key is `set_inconsistency`; any
   unequal 40-hex value is `integrated_source_oid_mismatch`. Ancestry
   equivalence does not substitute for equality.
6. Return the individual results in required-ID order and the one common OID.
   Do not persist the set result or add aggregate, container, document-flow, or
   latest-pointer fields; the CLI may serialize this in-memory result once to
   its frozen stdout shape.

For this successor container, the Source Packet passes the exact ordered pair
`knowledge_graph`, then `active_design_packet_materialization`, as
`required_unit_ids`. This tuple is request data, not a `github_publish.py`
registry or hard-coded producer restriction. Thus
both records may name the same merged source OID while retaining independent
design/review paths and record hashes. Each individual verification has proved
integrated→observed and observed→current fixed `origin/main` ancestry; the set
verifier consumes those booleans and adds only duplicate, exact-unit-set, and
same-OID semantics. These individual and set APIs are the only predecessor-
integration APIs a successor uses.

### Successor container reconciliation

The live successor design
`reports/agents/20260712-090608-context-packettool-skill-routing/container_codex_home_design.md`
is verify-only in this unit. Its transient SHA is successor-owner state, not an
active-packet Source Packet hash. If its S1 names the superseded schema, dashed
unit IDs, old filenames, two caller-level verifier calls, equal observed-main
OIDs, or a caller-level integrated-OID comparison, it is not valid successor
intake for this revision and the exact replacement below is mandatory.

There is no remaining parent choice. Before container implementation, the
container design owner replaces that S1 surface exactly as follows:

1. Replace schema
   `agent_canon.active_design_packet.predecessor_integration.v1` with
   `agent_canon.predecessor_integration.v1`.
2. Replace `knowledge-graph` and `active-design-packet-materialization` with
   `knowledge_graph` and `active_design_packet_materialization`.
3. Replace `knowledge_graph_predecessor_integration.json` and
   `active_design_packet_materialization_predecessor_integration.json` with
   `predecessor_integration.knowledge_graph.json` and
   `predecessor_integration.active_design_packet_materialization.json`.
4. Replace the caller's two-result unit/OID comparison with one call to
   `verify_predecessor_integration_set`, passing the exact ordered required IDs
   and two explicit `PredecessorIntegrationInput` values. The set API owns both
   individual calls, duplicate/exact-set rejection, and byte-equal integrated-
   OID comparison.
5. Delete the equal-`observed_target_main_oid` requirement. Records produced
   at different post-merge observation times may name different descendants;
   each individual verifier already proves integrated→observed and
   observed→fixed `origin/main` ancestry.
6. After the set result succeeds, retain exactly one container-readiness check:
   `git merge-base --is-ancestor <common_integrated_source_oid> HEAD` must exit
   0 before container source work. This consumes the in-memory result and adds
   no record, aggregate, or document-flow field.

The active-packet writer does not edit the container design. The container
owner performs this deterministic rebase after the generic owner integrates;
until then, its current S1 and V0 are stale verify-only evidence rather than a
second contract.

## Normative Typed Value

The following names and fields are final implementation choices. All records
are frozen. Tuples retain input order; the decoder rejects duplicates rather
than silently de-duplicating them.

```python
ActiveDesignSection = Literal[
    "abstract_design_frame",
    "implementation_source_packet",
    "design_side_effect_map",
    "design_to_implementation_trace",
]


@dataclass(frozen=True)
class ActiveDesignClause:
    clause_id: str
    source_ref: str


@dataclass(frozen=True)
class ActiveDesignPacketEntry:
    entry_id: str
    responsibility_id: str
    clause_refs: tuple[str, ...]
    owner_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    dependency_refs: tuple[str, ...]
    output_refs: tuple[str, ...]
    reviewer_refs: tuple[str, ...]


@dataclass(frozen=True)
class ActiveDesignPacketValue:
    schema: str
    design_artifact: str
    design_review_artifact: str
    document_flow_review_artifact: str
    document_flow_required: bool
    clause_registry: tuple[ActiveDesignClause, ...]
    abstract_design_frame: ActiveDesignPacketEntry
    implementation_source_packet: ActiveDesignPacketEntry
    design_side_effect_map: ActiveDesignPacketEntry
    design_to_implementation_trace: ActiveDesignPacketEntry
```

`ActiveDesignPacketConfig` is deleted. There is no section-specific class.
`ActiveDesignPacketEntry` is the neutral representation used exactly four
times.

### Exact decoder and resolver APIs

```python
def parse_active_design_packet_input(
    value: str | None,
) -> ActiveDesignPacketValue | None: ...


def resolve_active_design_packet(
    config: TeamConfig,
    *,
    workflow_family: Mapping[str, object] | None,
    explicit: ActiveDesignPacketValue | None,
) -> ActiveDesignPacketValue: ...
```

Both functions call one private decoder:

```python
def _decode_active_design_packet(
    raw: object,
    *,
    field_prefix: str,
) -> ActiveDesignPacketValue: ...
```

Resolution precedence is exactly `explicit > workflow_family >
agents_config`. Missing fields, unknown fields, wrong types, unknown schema,
duplicate IDs, empty reference arrays, and malformed references fail in this
decoder. No producer or consumer repeats those checks.

## Normative `agents_config.json` Record

`agents_config.json` replaces the current five-field
`artifacts.active_design_packet` value in place with the following exact JSON
content. The schema string stays `waterfall.design_packet.v1`; no sibling key
or additional schema is introduced.

```json
{
  "schema": "waterfall.design_packet.v1",
  "design_artifact": "design_brief.md",
  "design_review_artifact": "design_review.md",
  "document_flow_review_artifact": "document_flow_review.md",
  "document_flow_required": true,
  "clause_registry": [
    {
      "clause_id": "CANON-ADF",
      "source_ref": "repo:agents/canonical/CODEX_WORKFLOW.md#section:design-integrity-gate"
    },
    {
      "clause_id": "CANON-SOURCE-PACKET",
      "source_ref": "repo:agents/templates/design_brief.md#section:implementation-source-packet"
    },
    {
      "clause_id": "CANON-SIDE-EFFECT",
      "source_ref": "repo:agents/templates/design_brief.md#section:design-side-effect-map"
    },
    {
      "clause_id": "CANON-TRACE",
      "source_ref": "repo:agents/templates/design_brief.md#section:design-to-implementation-trace"
    }
  ],
  "abstract_design_frame": {
    "entry_id": "abstract-design-frame",
    "responsibility_id": "active-design-packet",
    "clause_refs": ["CANON-ADF"],
    "owner_refs": ["role:designer"],
    "source_refs": [
      "repo:agents/canonical/CODEX_WORKFLOW.md#section:design-integrity-gate",
      "repo:agents/templates/design_brief.md#section:abstract-design-frame"
    ],
    "dependency_refs": [
      "header:upstream:design:repo:agents/templates/design_brief.md->repo:documents/dependency-manifest-design.md"
    ],
    "output_refs": ["artifact:design_brief.md"],
    "reviewer_refs": [
      "role:design_reviewer",
      "role:document_flow_reviewer"
    ]
  },
  "implementation_source_packet": {
    "entry_id": "implementation-source-packet",
    "responsibility_id": "active-design-packet",
    "clause_refs": ["CANON-SOURCE-PACKET"],
    "owner_refs": ["role:designer"],
    "source_refs": [
      "repo:agents/templates/design_brief.md#section:implementation-source-packet",
      "repo:agents/workflows/implementation-waterfall-workflow.md#section:active-design-packet"
    ],
    "dependency_refs": [
      "entry:abstract-design-frame",
      "header:upstream:design:repo:agents/templates/design_brief.md->repo:documents/dependency-manifest-design.md"
    ],
    "output_refs": ["artifact:design_brief.md"],
    "reviewer_refs": ["role:design_reviewer"]
  },
  "design_side_effect_map": {
    "entry_id": "design-side-effect-map",
    "responsibility_id": "active-design-packet",
    "clause_refs": ["CANON-SIDE-EFFECT"],
    "owner_refs": ["role:designer"],
    "source_refs": [
      "repo:agents/templates/design_brief.md#section:design-side-effect-map",
      "repo:agents/workflows/implementation-waterfall-workflow.md#section:active-design-packet"
    ],
    "dependency_refs": [
      "entry:abstract-design-frame",
      "header:upstream:design:repo:agents/templates/design_brief.md->repo:documents/dependency-manifest-design.md"
    ],
    "output_refs": ["artifact:design_brief.md"],
    "reviewer_refs": [
      "role:design_reviewer",
      "role:document_flow_reviewer"
    ]
  },
  "design_to_implementation_trace": {
    "entry_id": "design-to-implementation-trace",
    "responsibility_id": "active-design-packet",
    "clause_refs": ["CANON-TRACE"],
    "owner_refs": ["role:designer"],
    "source_refs": [
      "repo:agents/templates/design_brief.md#section:design-to-implementation-trace",
      "repo:agents/canonical/CODEX_WORKFLOW.md#section:5.-implementation"
    ],
    "dependency_refs": [
      "entry:abstract-design-frame",
      "entry:implementation-source-packet",
      "entry:design-side-effect-map"
    ],
    "output_refs": [
      "artifact:design_brief.md",
      "artifact:design_review.md",
      "artifact:document_flow_review.md"
    ],
    "reviewer_refs": [
      "role:design_reviewer",
      "role:document_flow_reviewer"
    ]
  }
}
```

### Cardinality and join rules

1. The packet has exactly one object for each of the four named section keys.
2. `clause_registry` has one or more records; `clause_id` is unique and every
   registry record is referenced by at least one section.
3. Every section has exactly the seven fields shown for
   `ActiveDesignPacketEntry`; every reference tuple is non-empty and contains
   no duplicate declared value within that tuple. The same authority may be
   referenced by different sections; those cross-section repetitions must
   resolve to the same result record.
4. Section `entry_id` values are exactly `abstract-design-frame`,
   `implementation-source-packet`, `design-side-effect-map`, and
   `design-to-implementation-trace`; each appears once.
5. The same non-empty `responsibility_id` appears in all four records. A packet
   therefore describes one responsibility unit.
6. Every `clause_refs` item joins to exactly one clause registry record.
7. Every `entry:<entry_id>` joins to one of the other three section records;
   self-reference is rejected.
8. Source packet and side-effect map each depend on
   `entry:abstract-design-frame`. Trace depends on all three preceding entry
   IDs. Missing or extra join direction is rejected.
9. Every owner and reviewer resolves through the active role projection built
   from selected `TeamConfig` roles. Reviewers must own a selected review
   output through exact `Role.required_outputs` equality; suffix or prose
   heuristics are forbidden.
10. Every output joins to the exact planned artifact path and, after rendering,
    to exactly one in-memory artifact. No unreferenced alternate design packet
    is searched.
11. Collect distinct `reviewer_refs` in four-section order, preserving the
    first occurrence. Join each role to exactly one of
    `artifact:<design_review_artifact>` or
    `artifact:<document_flow_review_artifact>` by exact required-output path.
    The resulting reviewer-to-artifact mapping has exactly one distinct design
    reviewer and, when `document_flow_required=true`, exactly one distinct flow
    reviewer. Repeated section references reuse that mapping and do not change
    cardinality. A role matching zero or both review artifacts is rejected.

## Reference Grammar and Resolution Algorithms

### Source references: root, path, symbol, and section

The grammar is:

```text
repo:<relative-posix-path>
repo:<relative-posix-path>#symbol:<dotted-qualname>
repo:<relative-posix-path>#section:<canonical-anchor>
artifact:<relative-posix-path>
artifact:<relative-posix-path>#section:<canonical-anchor>
```

Resolution is deterministic:

1. Split on at most one `#`. Reject empty roots, empty paths, unknown fragment
   kinds, backslashes, absolute paths, `.`/`..` segments, NUL, and duplicate
   normalized declarations within one reference tuple. Cross-section reuse of
   the same normalized path or fragment is allowed and interns one result.
2. `repo:` resolves beneath `RunBundleSpec.workspace_root` through
   `resolve_workspace_document_path`; `artifact:` resolves beneath
   `report_dir` through `resolve_report_bundle_artifact_path`.
3. Resolve symlinks and require containment. A bare source path must be an
   existing regular file. A planned artifact may be absent before rendering
   but must be present exactly once in the planned and rendered output sets.
4. `#symbol:` is valid only for a Python source path in this unit. Parse bytes
   with Python `ast.parse`; traverse class/function bodies by exact dotted
   qualname. AgentCanon checks membership only. Syntax validity and node types
   are the Python parser's result.
5. `#section:` calls `markdown_document_headings`, computes every exact heading
   with `markdown_heading_anchor`, and requires one equal anchor. It does not
   inspect paragraph text, table cells, keywords, or heading-adjacent prose.
6. Source or clause references to `schedule.md`, `workflow_monitoring.md`,
   `work_log.md`, `decision_log.md`, chat exports, history files, or review
   narrative are rejected as authority sources. Those files may still be
   outputs when selected by the normal artifact registry.

### Dependency references

The grammar is:

```text
entry:<entry-id>
header:<upstream|downstream>:<design|implementation|environment>:repo:<source-relative-posix-path>->repo:<target-relative-posix-path>
```

`entry:` uses the four-record join rules above. A header reference must match
this anchored grammar exactly; `repo:` is mandatory on both endpoints and
fragments, artifact endpoints, extra `->`, and unregistered direction or kind
values are rejected. Parse the direction and kind, split the remainder exactly
once on `->`, and pass each complete `repo:` endpoint through the source-path
algorithm. Select the nearest canonical Git root containing both resolved
paths. A logical AgentCanon path therefore resolves through the root view,
vendored AgentCanon source, or standalone source selected by
`resolve_workspace_document_path`; a project-local path resolves beneath the
workspace root. Endpoints that resolve to different dependency roots are
rejected. Invoke the canonical dependency graph builder for the one selected
root with a private temporary TSV:

```bash
bash <agent-canon-source>/tools/agent_tools/check_dependency_graph.sh \
  --root <selected-dependency-root> \
  --cycle-report-only \
  --graph-tsv <private-temp>/dependency_graph.tsv
```

The materializer consumes the documented four-column normalized result
`direction, kind, source, target`. For each row it requires root-relative POSIX
`source` and `target` values and constructs exactly
`header:{direction}:{kind}:repo:{source}->repo:{target}`. Declared references
are normalized to that same key after their resolved paths are made relative
to the selected dependency root. Membership is exact string equality. It does
not read dependency prose, infer imports, merge code-dependency output, or
implement dependency-header parsing. The temporary graph is not a run artifact
and is deleted on success and every failure before publication.

### Owner and reviewer references

Both use `role:<role-id>`.

1. Consume the role map produced by the existing `TeamConfig` loader and the
   selected `spec.roles`; duplicate or unknown active IDs are config/selection
   errors owned by those existing results.
2. Project each active role as one `RoleOutputProjection` with its exact
   `role:<id>` and normalized `artifact:<required-output>` values. Persist that
   projection in `team_manifest.yaml`; the waterfall loader reconstructs it
   from the manifest and never re-reads live config.
3. An owner resolves when its role ref occurs in that active projection.
4. Build `ReviewerArtifactProjection` records by the cardinality/join rule
   above. Persist them beside the packet reference projection. A reviewer
   resolves only through one of those records.
5. No role-name suffix, agent type, schedule assignment, or prose statement is
   used to infer ownership.

### Clause references

`clause_refs` contain bare IDs. Build a map from `clause_registry`, reject
duplicates, resolve every `ActiveDesignClause.source_ref` with the source
algorithm, and require every section reference to hit one record. Clause text
is not copied into the packet. The source path and exact anchor remain the
authority.

### Output references

The grammar is `artifact:<relative-posix-path>`. Before rendering, each output
must occur exactly once in `iter_artifacts(...)` plus the two authority outputs
owned by `project_authority_artifacts`. After rendering, the same normalized
path must occur exactly once in the in-memory artifact set. The manifest,
role/prompt packets, `created_files`, and consumer value must expose the same
path. A basename search or sibling fallback is forbidden.

## Public Types and APIs

### Projection and result types

```python
CleanupStatus = Literal["not_required", "pass", "fail"]
MaterializationPhase = Literal[
    "decode",
    "reference_validation",
    "render",
    "stage",
    "publish",
    "activate",
    "rollback",
]
MaterializationErrorCode = Literal[
    "packet_invalid",
    "reference_invalid",
    "render_invalid",
    "artifact_set_invalid",
    "report_root_invalid",
    "materialization_lock_failed",
    "materialization_lock_busy",
    "materialization_lock_foreign",
    "materialization_lock_release_failed",
    "atomic_noreplace_unavailable",
    "atomic_exchange_unavailable",
    "staging_name_exhausted",
    "staging_write_failed",
    "staging_verify_failed",
    "run_bundle_target_exists",
    "run_bundle_cross_device",
    "run_bundle_publish_failed",
    "active_bookkeeping_nonregular",
    "bookkeeping_name_exhausted",
    "active_baseline_publish_failed",
    "active_pointer_publish_failed",
    "bookkeeping_restore_conflict",
    "run_bundle_rollback_failed",
]
ActiveDesignPacketInputErrorCode = Literal[
    "json_invalid",
    "missing_field",
    "unknown_field",
    "wrong_type",
    "unknown_schema",
    "duplicate_id",
    "empty_reference_set",
    "malformed_reference",
]
RUN_BUNDLE_FILE_MODE = 0o644
RUN_BUNDLE_DIRECTORY_MODE = 0o755
PRIVATE_STAGE_MODE = 0o700
PRIVATE_TEMP_MODE = 0o600
MATERIALIZATION_LOCK_MODE = 0o600


@dataclass(frozen=True)
class RenderedArtifact:
    relative_path: PurePosixPath
    content: bytes
    mode: int


@dataclass(frozen=True)
class ArtifactDigest:
    relative_path: PurePosixPath
    sha256: str


@dataclass(frozen=True)
class SubagentPromptPacket:
    role_id: str
    active_design_packet: ActiveDesignPacketValue
    document_packet: RoleDocumentPacket
    required_outputs: tuple[str, ...]


@dataclass(frozen=True)
class SourceReferenceResult:
    declared_ref: str
    root_key: Literal["workspace", "agent_canon", "artifact"]
    resolved_path: Path
    relative_path: PurePosixPath
    fragment_kind: Literal["none", "symbol", "section"]
    fragment_value: str | None
    sha256: str
    parser_match_count: int


@dataclass(frozen=True)
class DependencyReferenceResult:
    declared_ref: str
    dependency_root_key: Literal["workspace", "agent_canon"]
    normalized_key: str
    source_path: PurePosixPath
    target_path: PurePosixPath
    source_sha256: str
    target_sha256: str
    graph_match_count: int


@dataclass(frozen=True)
class RoleOutputProjection:
    role_ref: str
    output_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReviewerArtifactProjection:
    reviewer_ref: str
    review_artifact_ref: str


@dataclass(frozen=True)
class ClauseReferenceResult:
    clause_id: str
    source_ref: str


@dataclass(frozen=True)
class OutputReferenceResult:
    output_ref: str
    relative_path: PurePosixPath
    planned_count: int


@dataclass(frozen=True)
class ActiveDesignReferenceContext:
    workspace_root: Path
    report_dir: Path
    source_results: tuple[SourceReferenceResult, ...]
    dependency_results: tuple[DependencyReferenceResult, ...]
    role_output_projections: tuple[RoleOutputProjection, ...]
    reviewer_artifact_projections: tuple[ReviewerArtifactProjection, ...]
    clause_results: tuple[ClauseReferenceResult, ...]
    output_results: tuple[OutputReferenceResult, ...]
    planned_output_paths: frozenset[PurePosixPath]


ActiveDesignManifestField = Literal[
    "schema",
    "design_artifact",
    "design_review_artifact",
    "document_flow_review_artifact",
    "document_flow_required",
    "clause_registry",
    "abstract_design_frame",
    "implementation_source_packet",
    "design_side_effect_map",
    "design_to_implementation_trace",
    "active_design_packet_reference_projection",
]
ManifestPacketViolationKind = Literal[
    "manifest_missing",
    "manifest_invalid",
    "packet_missing",
    "field_missing",
    "field_invalid",
    "schema_unknown",
    "path_outside_bundle",
]
ActiveDesignReferenceField = Literal[
    "clause_refs",
    "owner_refs",
    "source_refs",
    "dependency_refs",
    "output_refs",
    "reviewer_refs",
]
ActiveDesignReferenceReason = Literal[
    "clause_unknown",
    "owner_unknown",
    "source_missing",
    "source_digest_mismatch",
    "source_fragment_mismatch",
    "dependency_edge_missing",
    "output_missing",
    "reviewer_output_mismatch",
    "projection_mismatch",
]
DesignArtifactViolationReason = Literal[
    "missing",
    "template_or_placeholder_remaining",
    "section_empty_or_missing",
]
ReviewArtifactViolationReason = Literal[
    "design_artifact_path_missing",
    "design_artifact_path_mismatch",
    "review_target_sha256_missing",
    "review_target_sha256_mismatch",
    "decision_not_approve",
]


@dataclass(frozen=True)
class ManifestPacketViolation:
    kind: ManifestPacketViolationKind
    field: ActiveDesignManifestField | None
    observed_schema: str | None
    order_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class ReferencePacketViolation:
    section: ActiveDesignSection
    field: ActiveDesignReferenceField
    input_index: int
    reason: ActiveDesignReferenceReason
    order_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class DesignArtifactViolation:
    artifact_path: PurePosixPath
    reason: DesignArtifactViolationReason
    section_slug: str | None
    order_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class ReviewArtifactViolation:
    artifact_path: PurePosixPath
    reason: ReviewArtifactViolationReason
    order_key: tuple[int, int, int, int]


ActiveDesignPacketViolation = (
    ManifestPacketViolation
    | ReferencePacketViolation
    | DesignArtifactViolation
    | ReviewArtifactViolation
)


def render_active_design_packet_violation(
    violation: ActiveDesignPacketViolation,
) -> str: ...


@dataclass(frozen=True)
class MaterializedActiveDesignPacketResult:
    value: ActiveDesignPacketValue | None
    context: ActiveDesignReferenceContext | None
    violations: tuple[ActiveDesignPacketViolation, ...]
```


`render_active_design_packet_violation` is the sole public-code renderer.
It exhaustively matches the four union members and the finite `Literal`
reasons; there is no caller-supplied code string. It rejects invalid manifest
kind/field/schema combinations, requires `section_slug` only for
`section_empty_or_missing`, percent-encodes every dynamic schema/path/slug
component outside `[A-Za-z0-9._/-]`, and emits only the grammar fixed under
S5/T6/V7. `order_key` is created by the loader/validator from the fixed order
and is never parsed from a manifest. Waterfall assigns the literal owner
`design`; ownership is not data in a violation.


```python
@dataclass(frozen=True)
class RollbackResult:
    staging_cleanup: CleanupStatus
    target_cleanup: CleanupStatus
    pointer_restore: CleanupStatus
    baseline_restore: CleanupStatus
    temp_cleanup: CleanupStatus
    failed_paths: tuple[str, ...]


class ActiveDesignPacketInputError(ValueError):
    code: ActiveDesignPacketInputErrorCode
    field: str

    def __init__(
        self,
        *,
        code: ActiveDesignPacketInputErrorCode,
        field: str,
    ) -> None: ...


class RunBundleMaterializationError(RuntimeError):
    phase: MaterializationPhase
    code: MaterializationErrorCode
    cause_code: MaterializationErrorCode
    target_path: Path
    staging_path: Path | None
    violations: tuple[ActiveDesignPacketViolation, ...]
    rollback: RollbackResult

    def __init__(
        self,
        *,
        phase: MaterializationPhase,
        code: MaterializationErrorCode,
        cause_code: MaterializationErrorCode,
        target_path: Path,
        staging_path: Path | None,
        violations: tuple[ActiveDesignPacketViolation, ...],
        rollback: RollbackResult,
    ) -> None: ...


@dataclass(frozen=True)
class RunActivationSpec:
    report_root: Path
    monitoring_entries: "MonitoringEntries"


@dataclass(frozen=True)
class RunBundleSpec:
    config: TeamConfig
    report_dir: Path
    run_id: str
    task: str
    owner: str
    created_at_iso: str
    roles: tuple[Role, ...]
    workspace_root: Path
    active_design_packet: ActiveDesignPacketValue | None = None
    activation: RunActivationSpec | None = None
    workflow_family_id: str = ""
    manual_specialists: tuple[str, ...] = ()
    task_default_specialists: tuple[str, ...] = ()
    auto_specialists: tuple[str, ...] = ()
    default_review_packs_enabled: bool = False
    default_review_pack_ids: tuple[str, ...] = ()
    selected_skills: tuple[str, ...] = ()
    task_catalog: TaskCatalog | None = None
    agent_type_selections: tuple[AgentTypeSelection, ...] = ()


@dataclass(frozen=True)
class RunBundleMaterialization:
    report_dir: Path
    created_files: tuple[str, ...]
    active_design_packet: ActiveDesignPacketValue
    role_document_packets: tuple[RoleDocumentPacket, ...]
    subagent_prompt_packets: tuple[SubagentPromptPacket, ...]
    artifact_digests: tuple[ArtifactDigest, ...]
    active_pointer: Path | None
```

Every current run-bundle artifact is UTF-8 text and receives
`RUN_BUNDLE_FILE_MODE`; projectors call one private
`rendered_text_artifact(relative_path, text)` constructor and cannot choose a
mode. Staging directories use `PRIVATE_STAGE_MODE` while writes are in
progress, then every directory is changed to `RUN_BUNDLE_DIRECTORY_MODE`
leaves-first before staging verification. The lock keeps
`MATERIALIZATION_LOCK_MODE`. Bookkeeping temps use `PRIVATE_TEMP_MODE` while
private and are changed to `RUN_BUNDLE_FILE_MODE` before replacement. No
packet/config/caller field controls permissions, and an in-memory artifact with
any other mode is `artifact_set_invalid`.

The shown `RunBundleSpec` is the complete replacement, including every current
field in current order and the one new `activation` field. `agent_team.py`
imports `MonitoringEntries` only under `TYPE_CHECKING`; postponed annotations
and the local runtime import of the pure renderer avoid the existing
`workflow_monitor.py -> agent_team.py` import edge. Task-start and bootstrap
provide activation; doc-start, smoke, and alignment producers provide `None`.
No caller gets a narrower spec or error type.

`ActiveDesignPacketInputError` is emitted only by the one decoder and reports
the stable input field path. `_materialize_run_bundle` catches decoder failures
from workflow/config resolution and rethrows `RunBundleMaterializationError`
with `phase="decode"`, `code="packet_invalid"`, no staging path, all cleanup
statuses `not_required`, and no filesystem mutation. Every later failure uses
the same materialization exception. For a normal failure `code` and
`cause_code` are equal. `RollbackResult` is always present, sorts
`failed_paths`, and records each attempted cleanup independently; changing the
top-level `code` to `run_bundle_rollback_failed` preserves the original
`phase` and `cause_code` in the exception.

### Shared manifest-consumer APIs

`agent_team.py` defines these APIs before their materializer and waterfall use:

```python
def load_materialized_active_design_packet(
    report_dir: Path,
) -> MaterializedActiveDesignPacketResult: ...


def validate_materialized_active_design_packet(
    value: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
    *,
    gate: Literal["materialization", "design", "document_flow", "implementation"],
) -> tuple[ActiveDesignPacketViolation, ...]: ...


def build_active_design_reference_context(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    workflow_family: Mapping[str, object] | None,
    *,
    artifact_names: tuple[str, ...],
) -> ActiveDesignReferenceContext: ...
```

`build_active_design_reference_context` is the only constructor. It receives
the already selected workflow record, uses `spec.config`, `spec.roles`,
`spec.task_catalog`, `spec.workspace_root`, and `spec.report_dir`, and consumes
authoritative results in this fixed order: active role/output projections;
normalized planned artifacts; source containment; Python AST or Markdown
heading membership; known-clause joins; and canonical dependency TSV rows. It
interns repeated declared references after equality of every result field is
confirmed. It never reads a packet again, and callers cannot construct or
extend the context.

`build_manifest` persists the same tuples under derived
`run.active_design_packet_reference_projection`; callers cannot supply or
override that projection and it is not a second packet input schema. Its record
shape is exactly:

```yaml
active_design_packet_reference_projection:
  source_results:
    - declared_ref: <string>
      root_key: <workspace|agent_canon|artifact>
      relative_path: <posix-path>
      fragment_kind: <none|symbol|section>
      fragment_value: <string-or-null>
      sha256: <lowercase-sha256>
      parser_match_count: 1
  dependency_results:
    - declared_ref: <string>
      dependency_root_key: <workspace|agent_canon>
      normalized_key: <string>
      source_path: <posix-path>
      target_path: <posix-path>
      source_sha256: <lowercase-sha256>
      target_sha256: <lowercase-sha256>
      graph_match_count: 1
  role_output_projections:
    - role_ref: <role:id>
      output_refs: [<artifact:path>, ...]
  reviewer_artifact_projections:
    - reviewer_ref: <role:id>
      review_artifact_ref: <artifact:path>
  clause_results:
    - clause_id: <string>
      source_ref: <declared-source-ref>
  output_results:
    - output_ref: <artifact:path>
      relative_path: <posix-path>
      planned_count: 1
  planned_output_paths: [<posix-path>, ...]
```

There are no additional keys. Absolute `resolved_path` is deliberately not
serialized; the loader reconstructs it from `root_key` and `relative_path`.
Tuple order is four-section order, field order
`clause,owner,source,dependency,output,reviewer`, then declared-input order;
role and planned-output records that are not tied to one field retain selected
role order and normalized path order respectively.

The loader reads `team_manifest.yaml` once with `yaml.safe_load`, obtains
`run.workspace_root`, `run.report_dir`, `run.active_design_packet`, active role
outputs, and the derived reference projection, and calls the same packet
decoder. It reconstructs the result dataclasses, resolves only the persisted
root/path pairs through the canonical containment resolvers, and verifies
persisted file digests. It never re-reads live team config or task catalog and
never reruns AST, Markdown-heading, dependency-header, or dependency-graph
parsing. A missing/malformed projection, non-unit parser/graph match count, role
projection disagreement, path containment failure, or digest mismatch becomes
an ordered load violation. The loader returns all load violations in
deterministic manifest-field order and does not search sibling files or
alternative packet names.

The validator uses the reference algorithms above. For review artifacts it
consumes `section_has_content` and `has_approve_decision`, then enforces only
cross-file identity: selected artifact path, target SHA, selected reviewer
output, and required review presence. `gate="document_flow"` checks only the
selected flow-review projection; `design` checks the design artifact and
required design reviews; `implementation` checks those reviews plus public
projection consistency; `materialization` checks every pre-render reference
and planned-output semantic. It never decodes the value again.

### Sole public delegator

```python
def create_run_bundle(spec: RunBundleSpec) -> RunBundleMaterialization:
    return _materialize_run_bundle(spec)
```

No second public materialization function exists. Producers call this function
exactly once. `run_active_design_packet`, direct pointer writes,
`write_task_authority_baselines`, and post-create monitoring appends disappear
from producers.

### Exact projector signatures

```python
def iter_artifacts(
    config: TeamConfig,
    roles: tuple[Role, ...],
    packet: ActiveDesignPacketValue,
) -> tuple[str, ...]: ...


def project_role_document_packets(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
) -> tuple[RoleDocumentPacket, ...]: ...


def project_subagent_prompt_packets(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    role_packets: tuple[RoleDocumentPacket, ...],
) -> tuple[SubagentPromptPacket, ...]: ...


def project_template_artifacts(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    *,
    artifact_names: tuple[str, ...],
    role_packets: tuple[RoleDocumentPacket, ...],
    prompt_packets: tuple[SubagentPromptPacket, ...],
) -> tuple[RenderedArtifact, ...]: ...


def project_verification_artifact(
    spec: RunBundleSpec,
) -> RenderedArtifact: ...


def project_authority_artifacts(
    spec: RunBundleSpec,
) -> tuple[RenderedArtifact, RenderedArtifact]: ...


def project_initial_wave_row(
    spec: RunBundleSpec,
) -> Mapping[str, str] | None: ...


def project_wave_ledger_artifacts(
    spec: RunBundleSpec,
    template_artifacts: tuple[RenderedArtifact, ...],
    *,
    monitoring_entries: "MonitoringEntries",
    initial_wave_row: Mapping[str, str] | None,
) -> tuple[RenderedArtifact, ...]: ...


def build_manifest(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
    *,
    artifact_names: tuple[str, ...],
    role_packets: tuple[RoleDocumentPacket, ...],
    prompt_packets: tuple[SubagentPromptPacket, ...],
) -> str: ...


def format_start_declaration(
    workflow_family_name: str,
    active_skills: tuple[str, ...],
    review_roles: tuple[str, ...],
) -> str: ...
```

`project_authority_artifacts` returns `task_authority.yaml` and
`task_authority.yaml.sha256`; the baseline is calculated from the in-memory
authority bytes. `project_initial_wave_row` calls the existing
`workflow_spawn_budget`, `recommended_initial_subagent_wave`, and
`initial_wave_gate_fields` functions exactly once. It returns `None` for no
workflow family or no recommended wave; a selected workflow family without a
`TaskCatalog` is a render error. A returned mapping has exactly these keys in
this order: `wave_id`, `parent_or_delegate`, `spawn_authority`, `trigger`,
`budget_before`, `budget_after`, `runtime_max_threads`, `runtime_max_depth`,
`spawned_roles`, `role_instances`, `skipped_roles`, `allowed_paths`,
`do_not_read`, `write_scope`, `validation_route`, `review_gate`,
`handoff_artifacts`, `delegated_policy_ref`, and `status`.

`workflow_monitor.py` owns these exact pure construction/render APIs:

```python
def build_run_start_monitoring_entries(
    *,
    command: Literal["task_start", "bootstrap_agent_run"],
    report_dir: Path,
    created_at_iso: str,
    start_declaration: str,
    role_ids: tuple[str, ...],
    preflight_status: str,
) -> MonitoringEntries: ...


def render_monitoring_artifacts(
    *,
    schedule_text: str,
    workflow_monitoring_text: str,
    entries: MonitoringEntries,
    initial_wave_row: Mapping[str, str] | None,
) -> tuple[str, str]: ...
```

`build_run_start_monitoring_entries` returns one value with
`timestamp=created_at_iso`; `signals` are the start declaration,
`stage owner routing active_roles=<comma-joined-role-ids>`,
`agent_canon_preflight=<status>`, and
`web_research_not_required: <command> does not decide external research`;
`interventions` contains
`created run bundle and workflow_monitoring.md at <report_dir>`;
`behavior_events` contains
`token_efficiency_not_required reason=<task_start_default|bootstrap_default>`;
all other fields retain `MonitoringEntries` defaults. Task-start and bootstrap
compute `active_skills` and `review_roles`, call `format_start_declaration`
once, pass that same string to this constructor and later CLI output, and put
the returned value in `RunActivationSpec`. They do not append it later.

`project_wave_ledger_artifacts` locally imports
`render_monitoring_artifacts`, passes the exact two template strings and the
two explicit structured inputs, and replaces exactly `schedule.md` and
`workflow_monitoring.md` in the returned tuple. The renderer calls the current
normalization and section-transform functions; it does not parse packet data
or open a path. `append_monitoring` delegates its existing file-lock/write
boundary to the same pure renderer for later operational events. This removes
post-publication mutation without duplicating monitoring semantics or adding an
import-time cycle.

## Validate-All, Render-All, Atomic Call Graph

`_materialize_run_bundle` executes this order exactly:

1. `run_workflow_family(spec)` returns the authoritative selected workflow
   record.
2. `resolve_active_design_packet(config, workflow_family=...,
   explicit=spec.active_design_packet)` returns one value. It does not write.
3. `iter_artifacts(config, roles, packet)` computes exact planned public paths.
4. Call
   `build_active_design_reference_context(spec, packet, workflow_family,
   artifact_names=artifact_names)` exactly once. The function consumes the
   authoritative role/config/catalog, structural heading/AST, clause,
   containment, planned-output, and canonical dependency-graph results and
   returns the complete context described above.
5. Call `validate_materialized_active_design_packet(packet, context,
   gate="materialization")`. Collect every violation in deterministic
   section/field/input order; do not stop at the first field. Any violation
   returns one typed error before a staging or target directory is created.
6. Call `project_role_document_packets`, then
   `project_subagent_prompt_packets`. Neither function resolves or validates a
   packet.
7. Call `project_template_artifacts` once with the already-planned names and
   already-projected role/prompt packets. It expands all selected templates to
   `RenderedArtifact` values in memory.
8. Call `project_verification_artifact`, then
   `project_authority_artifacts`, in memory.
9. Call `project_initial_wave_row`. Select
   `spec.activation.monitoring_entries` when activation exists or the existing
   `EMPTY_MONITORING_ENTRIES` otherwise. Pass both explicit values and the
   template tuple to `project_wave_ledger_artifacts`; replace the two returned
   template artifacts in memory without opening target paths.
10. Call `build_manifest(spec, packet, context,
    artifact_names=artifact_names, role_packets=role_packets,
    prompt_packets=prompt_packets)` once. Add its UTF-8 bytes as the one
    `team_manifest.yaml` artifact. The derived projection serialized here is
    the exact context from step 4, not a reconstructed or caller-provided
    mapping.
11. Concatenate template, verification, authority, wave-ledger replacement,
    and manifest outputs into one ordered in-memory artifact tuple. Reject
    duplicate normalized
    paths, missing planned outputs, unexpected outputs, non-UTF-8 text outputs,
    invalid modes, packet/output disagreement, and role/prompt/manifest
    disagreement. Compute `ArtifactDigest` after this check.
12. Stage the complete artifact set, publish the target, and, if activation is
    present, publish bookkeeping as specified below.
13. Return `RunBundleMaterialization` only after all required publication and
    activation operations succeed.

Steps 1-11 are side-effect free except for the canonical dependency builder's
private temporary TSV, which is removed before step 12. A decoder failure maps
to phase `decode`; collected reference violations to `reference_validation` /
`reference_invalid`; projector or authoritative parser/type/build failure to
`render` / `render_invalid`; and final set disagreement to `render` /
`artifact_set_invalid`. There is no parse/project/revalidate step in
task-start, bootstrap, doc-start, smoke, alignment, or waterfall gate code.

## Atomic Publication and Failure Contract

The private publication boundary has these exact signatures:

```python
LockReuseClass = Literal[
    "first_acquisition",
    "released_file_reuse",
    "crash_stale_reuse",
]


@dataclass(frozen=True)
class FileIdentity:
    st_dev: int
    st_ino: int
    st_uid: int
    st_gid: int
    st_mode: int
    st_nlink: int


@dataclass(frozen=True)
class BookkeepingFileState:
    name: Literal[".active_run", ".active_run.sha256"]
    existed: bool
    identity: FileIdentity | None
    permission_mode: int | None
    size: int | None
    sha256: str | None
    content: bytes | None


@dataclass(frozen=True)
class BookkeepingTempState:
    path: Path
    identity: FileIdentity
    permission_mode: int
    size: int
    sha256: str
    content: bytes


@dataclass(frozen=True)
class MaterializationLockIdentity:
    schema_version: Literal["agent_canon.run_bundle_materialization_lock.v1"]
    state: Literal["held"]
    report_root_identity: FileIdentity
    lock_file_identity: FileIdentity
    effective_uid: int
    pid: int
    process_start_ticks: int
    boot_id: str
    nonce: str
    acquired_at: str
    run_id: str
    reuse_class: LockReuseClass
    payload_sha256: str


@dataclass(frozen=True)
class MaterializationLock:
    path: Path
    descriptor: int
    identity: MaterializationLockIdentity


@dataclass(frozen=True)
class PriorBookkeepingState:
    report_root_identity: FileIdentity
    lock_file_identity: FileIdentity
    lock_nonce: str
    pointer_prior: BookkeepingFileState
    baseline_prior: BookkeepingFileState
    pointer_temp: BookkeepingTempState | None
    baseline_temp: BookkeepingTempState | None
    pointer_quarantine: BookkeepingTempState | None
    baseline_quarantine: BookkeepingTempState | None
    pointer_published: BookkeepingFileState | None
    baseline_published: BookkeepingFileState | None


@dataclass(frozen=True)
class StagedArtifactSet:
    path: Path
    identity: FileIdentity


@dataclass(frozen=True)
class PublishedTarget:
    path: Path
    identity: FileIdentity
    tree_sha256: str


def _build_in_memory_artifact_set(
    *,
    planned_paths: tuple[str, ...],
    projected_artifacts: tuple[RenderedArtifact, ...],
) -> tuple[RenderedArtifact, ...]: ...


def _acquire_materialization_lock(
    *,
    report_root: Path,
    run_id: str,
) -> MaterializationLock: ...


def _release_materialization_lock(
    lock: MaterializationLock,
) -> None: ...


def _stage_artifact_set(
    *,
    report_root: Path,
    target: Path,
    run_id: str,
    artifacts: tuple[RenderedArtifact, ...],
) -> StagedArtifactSet: ...


def _rename_directory_noreplace(
    staging: StagedArtifactSet,
    target: Path,
) -> PublishedTarget: ...


def _publish_active_bookkeeping(
    *,
    report_root: Path,
    lock: MaterializationLock,
    published_target: PublishedTarget,
) -> tuple[Path, PriorBookkeepingState]: ...


def _rollback_publication(
    *,
    report_root: Path,
    lock: MaterializationLock,
    published_target: PublishedTarget | None,
    staging: StagedArtifactSet | None,
    prior: PriorBookkeepingState | None,
) -> RollbackResult: ...
```

`_build_in_memory_artifact_set` is step 11 above and returns paths sorted by
their normalized POSIX string. `_stage_artifact_set` owns all staging creation,
write, mode, sync, and re-read checks and returns only a fully verified staging
path plus its `lstat` device/inode identity. `_rename_directory_noreplace`
returns `PublishedTarget` only after the successful rename and verifies that
the target has the staging identity and records the canonical path/mode/size/
file-SHA tree digest as `tree_sha256`. `_publish_active_bookkeeping` snapshots
both report-root bookkeeping files and every created temp/quarantine identity,
mode, size, digest, and byte string in replacement `PriorBookkeepingState`
values, publishes baseline then pointer, and returns the pointer plus the
completed state only after report-root `fsync`; on failure it calls
`_rollback_publication` with its latest replacement state before raising the
typed error.
`_rollback_publication` is the only cleanup owner and never removes a
path unless it is the resolved private staging sibling with the recorded
identity, the `PublishedTarget` whose current `lstat(st_dev, st_ino)` still
equals the recorded identity and whose current canonical tree digest equals
`PublishedTarget.tree_sha256`, one of this call's identity/hash-bound private
temp or quarantine files, or one
of the two bookkeeping paths being restored from `prior`. A target collision
passes `published_target=None`; rollback therefore has no target deletion
authority. An identity mismatch records target cleanup failure and leaves the
unknown path untouched.

### Lock-file lifecycle and ownership

The lock path is exactly
`<report_root>/.run_bundle_materialization.lock`. It is a persistent
coordination inode, not a per-run temp and not a cleanup target. The payload is
canonical JSON+LF for every `MaterializationLockIdentity` field except
`payload_sha256`; that runtime field is SHA-256 of the exact payload bytes.
Released state is an empty zero-byte file. No timestamp or age threshold makes
a lock stale.

Acquisition is one exact sequence:

1. Open the already-validated report root with `O_DIRECTORY|O_CLOEXEC|
   O_NOFOLLOW`, retain its `FileIdentity`, and address the lock through that
   directory descriptor.
2. First acquisition calls `openat` with
   `O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW` and mode `0600`. Success sets
   `reuse_class="first_acquisition"`, requires a regular file with link count
   one, effective UID ownership, exact mode `0600`, and the report-root
   device, then proceeds to `flock`.
3. `EEXIST` opens the existing path with
   `O_RDWR|O_CLOEXEC|O_NOFOLLOW`. Before mutation, `lstat`, `fstat`, and a
   second `lstat` must identify one unchanged regular inode with link count
   one, effective UID ownership, mode `0600`, and the report-root device.
   Symlink, directory, device, FIFO, socket, hard-link count above one,
   different UID, different mode, device change, inode change, or open failure
   is `materialization_lock_foreign`; the path is not chmodded, truncated,
   replaced, or unlinked.
4. Call `fcntl.flock(descriptor, LOCK_EX|LOCK_NB)`. `EACCES` or `EAGAIN` is
   `materialization_lock_busy` for canonical, concurrent, reentrant, and
   foreign holders; acquisition does not retry and does not inspect or change
   the payload. Another flock error is `materialization_lock_failed`.
5. After the flock succeeds, repeat the identity checks and read the entire
   payload from the locked descriptor. A zero-byte payload is
   `reuse_class="released_file_reuse"`. A canonical `state="held"` payload
   whose schema, root device/inode, lock device/inode, UID, boot ID, PID,
   process-start ticks, and payload digest all validate is stale only when
   `/proc/<pid>/stat` is absent, its start ticks differ, or the current boot ID
   differs; this is `reuse_class="crash_stale_reuse"`. A held payload whose
   recorded process identity is still live, or an unreadable, malformed,
   truncated, wrong-schema, wrong-root, wrong-inode, wrong-UID, or wrong-digest
   payload is `materialization_lock_foreign`. It is not repaired or removed.
6. Construct a new `state="held"` identity using the stable root/lock
   identities, effective UID, current PID, `/proc/self/stat` start ticks,
   `/proc/sys/kernel/random/boot_id`, a fresh 128-bit lowercase hex nonce, one
   UTC RFC 3339 timestamp, exact `run_id`, and the classified reuse value.
   While holding the flock, `ftruncate(0)`, write the complete canonical
   payload, `fsync` the descriptor, rewind/read, and compare exact bytes and
   digest. Failure is `materialization_lock_failed`; the handler closes the
   descriptor, leaves any held payload for crash-stale classification, and
   performs no packet write.
7. Keep this descriptor and nonce through target publication, bookkeeping,
   rollback, temp cleanup, and report-root fsync. Every mutation helper receives
   `MaterializationLock`; no helper reopens or reacquires the lock.

Release runs once on every handled success or failure after cleanup. It
rechecks the root identity, lock pathname identity, descriptor identity,
regular-file/UID/mode/link invariants, and exact held payload digest and nonce.
Only an exact match permits `ftruncate(0)`, descriptor `fsync`,
`flock(LOCK_UN)`, and close, in that order. The empty lock inode remains for
later `released_file_reuse`; it is never unlinked. A compare failure is
`materialization_lock_release_failed`, does not clobber the pathname or
payload, closes the descriptor so the kernel releases its held flock, emits no
materialization success, and reports any already-required rollback result. A
process crash or uncatchable termination closes the descriptor in the kernel,
releases the flock, and leaves the held payload; the next caller may classify
it only by step 5. Canonical contention, foreign state, and crash reuse
therefore have disjoint outcomes, and no worker invents stale-age, PID-only,
unlink, or force-unlock semantics.

### Pre-publication

- Render and validate all bytes before creating staging state.
- Resolve `report_root` with `resolve_report_root`, open it with no-follow
  directory semantics, and require a directory whose resolved device/inode
  identity stays stable while the lock is held. Resolve `report_dir`; require
  `report_dir.parent` to equal that report root. A missing, symlinked, non-
  directory, identity-changing, or mismatched root returns
  `reference_validation/report_root_invalid` before cleanup authority exists.
- Call `_acquire_materialization_lock` exactly once and apply the complete
  lifecycle above before target collision inspection. Busy, foreign, acquire,
  and release failures retain their dedicated codes; the persistent lock inode
  is never packet cleanup authority.
- Resolve the target-publication capability before creating staging. The only
  target primitive is `_rename_directory_noreplace`. If activation is present,
  bookkeeping rollback also requires `renameat2(RENAME_EXCHANGE)` and
  `renameat2(RENAME_NOREPLACE)`. Missing target support is
  `atomic_noreplace_unavailable`; missing activation-restore support is
  `atomic_exchange_unavailable`. Capability failure precedes staging and gives
  every packet cleanup status `not_required`.
- If the target exists as any filesystem object, return
  `run_bundle_target_exists`; never merge, truncate, or replace it.
- Create a private sibling staging directory named
  `.<run-id>.stage.<pid>.<128-bit-nonce>` with mode `0700`. Retry a nonce
  collision at most eight times, then return `staging_name_exhausted`.

### Staging

1. Create every parent directory inside staging with mode `0700`.
2. Open every artifact with exclusive creation (`xb`), write exact bytes,
   `flush`, and `fsync`.
3. Apply the declared final mode only after bytes are complete.
4. `fsync` each created directory from leaves to staging root.
5. Re-read and hash every staged regular file; compare path, mode, size, and
   SHA-256 with the in-memory set.
6. On any failure, remove only the identity-matched private staging directory,
   then invoke the exact lock-release lifecycle and leave target and pointer
   state unchanged.

Creation/write/mode/sync failures map to `stage` / `staging_write_failed`;
re-read/path/mode/size/digest mismatches map to `stage` /
`staging_verify_failed`. Successful cleanup records
`staging_cleanup="pass"`; failed cleanup promotes the top-level code to
`run_bundle_rollback_failed`, retains the stage code in `cause_code`, and lists
the staging path. Other rollback fields are `not_required`.

### Target publication and collision handling

`agent_team.py` implements this exact private primitive:

```python
def _rename_directory_noreplace(
    staging: StagedArtifactSet,
    target: Path,
) -> PublishedTarget: ...
```

It loads `ctypes.CDLL(None, use_errno=True).renameat2`, sets argument types to
`(c_int, c_char_p, c_int, c_char_p, c_uint)` and result type to `c_int`, and
calls it with `AT_FDCWD=-100`, `os.fsencode(staging.path)`, `AT_FDCWD=-100`,
`os.fsencode(target)`, and `RENAME_NOREPLACE=1`. A nonzero result raises
`OSError(ctypes.get_errno(), os.strerror(errno))`. There is no alternate
directory-rename path.

While holding the canonical writer lock, check target absence again and call
that primitive once. Only a successful syscall followed by exact target
device/inode equality and equality of the canonical path/mode/size/file-SHA
tree digest with the staged artifact set creates `PublishedTarget`. The lock serializes canonical
producers; the kernel
no-replace flag also rejects a target created by an external writer between
the second check and syscall. Map `EEXIST` or `ENOTEMPTY` to
`run_bundle_target_exists`; `ENOSYS`, `EINVAL`, or `EOPNOTSUPP` to
`atomic_noreplace_unavailable`; `EXDEV` to `run_bundle_cross_device`; and every
other syscall error to `run_bundle_publish_failed`. Every failed syscall passes
`published_target=None`; remove staging only when its current identity equals
`StagedArtifactSet.identity`. A failed staging removal changes top-level `code` to
`run_bundle_rollback_failed`, preserves the mapped code in `cause_code`, and
records `staging_cleanup="fail"` and its path. After a successful rename,
`fsync` the report-root directory before activation; if that fails, remove the
new target under the lock and report publish failure or rollback failure. No
code path writes into, merges with, or replaces an existing target.

### Post-publish pointer and bookkeeping

All run-local bookkeeping is already in the target: authority baseline,
initial wave ledger, monitoring entries, verification, and manifest. Activation
has only `.active_run` and `.active_run.sha256`, and all access occurs through
the locked report-root descriptor.

Publication uses this exact sequence:

1. Compute pointer bytes as the normalized resolved target path plus LF and
   baseline bytes as lowercase SHA-256 of the pointer bytes plus LF.
2. Snapshot pointer then baseline into `BookkeepingFileState`. For an existing
   path, perform `lstat` → no-follow `openat` → `fstat` → complete bounded read
   → second `lstat`; require one unchanged regular, link-count-one,
   effective-UID-owned inode on the report-root device, with permission mode
   exactly `0600` or `0644`. Record identity, permission mode, byte length,
   SHA-256, and bytes. For absence, set `existed=False` and every other field
   null. A type, owner, mode, link, device, identity, read, or size violation is
   `active_bookkeeping_nonregular` before replacement.
3. Create baseline and pointer temps as distinct
   `.<name>.tmp.<pid>.<128-bit-nonce>` siblings with no-follow exclusive mode
   `0600`; write, flush, fsync, reopen, and verify exact identity, bytes, size,
   mode, and hash. Immediately store each verified object as
   `baseline_temp` or `pointer_temp` in a replacement
   `PriorBookkeepingState`; an absent temp remains null. Eight collisions is
   `bookkeeping_name_exhausted`.
4. Immediately before each replacement, recapture the destination and require
   exact equality with its prior snapshot, including absence or device/inode,
   mode, size, hash, and bytes. A mismatch is the corresponding baseline or
   pointer publish failure and no unknown destination is replaced.
5. Change the verified baseline temp to `0644`, `os.replace` it onto
   `.active_run.sha256`, recapture the published path, and store its exact
   `BookkeepingFileState` as `baseline_published`.
6. Change the verified pointer temp to `0644`, `os.replace` it onto
   `.active_run`, recapture it, and store its exact state as
   `pointer_published`. Pointer publication is last.
7. Fsync the report-root directory, delete only still-present identity-matched
   temps, and return the pointer plus the completed
   `PriorBookkeepingState`. The materializer releases the lock only after this
   success state is complete.

Compare-before-restore and no-clobber behavior is also fixed. Rollback restores
the pointer first, then the baseline, and removes the published target only
after both required restorations pass:

1. A bookkeeping path is restorable only when its current no-follow snapshot
   exactly equals that field's recorded `*_published` state, including
   device/inode, owner, link count, permission mode, size, SHA-256, and bytes.
   Missing state, changed state, an unknown path, or root/lock identity drift is
   `bookkeeping_restore_conflict`; leave the path untouched.
2. If the prior file existed, write its recorded bytes to a new verified temp
   with its recorded permission mode. Recompare the destination, then call
   `renameat2(RENAME_EXCHANGE)` between destination and temp. Verify that the
   exchanged-out temp is exactly the recorded writer-owned published state and
   the destination exactly matches the prior bytes/mode/hash. If either check
   fails, exchange back only when both current identities match the two
   recorded exchange identities; otherwise leave both and report conflict.
   Record the exchange temp as that side's `*_temp` before the exchange and
   after every identity-changing exchange. Delete the exchanged-out file only
   after it is proved equal to that recorded writer-owned state.
3. If the prior file was absent, move the current exact writer-owned path to a
   unique quarantine sibling with `renameat2(RENAME_NOREPLACE)`. Verify the
   quarantine identity/mode/hash/bytes against the published state, then unlink
   it. On mismatch, move it back only with `RENAME_NOREPLACE`; if the original
   name is no longer absent, retain the quarantine and report conflict. No
   Record the moved object as that side's `*_quarantine` immediately after the
   no-replace rename. No unknown object is unlinked or overwritten.
4. After each successful restoration, recapture and require the prior
   absent/present state, bytes, permission mode, size, and SHA. A restored
   present file receives a new inode; its prior inode remains provenance, not
   an impossible inode-restoration requirement. Fsync the report root after
   pointer restoration and again after baseline restoration.
5. If pointer restoration fails, baseline restoration and target deletion are
   `not_required` because preserving the published baseline/target avoids a
   dangling active pointer. If pointer passes but baseline fails, target
   deletion is `not_required` and the complete target remains for diagnosis.
   Only when both required restores pass may rollback compare the target's
   complete `PublishedTarget.identity`, remove that tree, and fsync the root.
6. Temp and quarantine cleanup requires exact generated-name, report-root,
   recorded device/inode, owner, link, type, mode, size, and hash agreement.
   Any mismatch is retained and listed; no glob, age scan, recursive sibling
   cleanup, or best-effort unlink is permitted.

An activation failure before baseline replacement restores nothing and removes
the identity-matched target. A failure after baseline replacement invokes the
algorithm above with `baseline_published`; a failure after pointer replacement
uses both published states. Any compare, exchange, quarantine, restore, target,
temp, or directory-sync failure promotes the result to
`rollback/run_bundle_rollback_failed`, preserves the activation code in
`cause_code`, records `bookkeeping_restore_conflict` in the failed-path detail
when applicable, and never returns a materialization result. Existing active
runs and unknown filesystem objects are never deleted.

Target creation occurs only after steps 1-11. The specified outcome for a
validation or rendering failure is an absent target. The pointer-last sequence
leaves the pointer unchanged on staging or target-publication failure. Success
has one complete target and, for activating producers, one pointer whose
baseline matches it.

The public failure taxonomy is closed as follows; an implementation may not
collapse these rows into a generic filesystem error:

| First failing condition | Phase/code | Cleanup authority and required result |
| --- | --- | --- |
| invalid or unstable report root / target parent mismatch | `reference_validation/report_root_invalid` | no staging or target authority; all `not_required` |
| first/open/fstat/payload-write/fsync failure not classified as busy or foreign | `stage/materialization_lock_failed` | close descriptor; persistent lock retained; no packet mutation; all packet cleanup `not_required` |
| nonblocking flock contention, including reentrant acquisition | `stage/materialization_lock_busy` | do not inspect payload; close descriptor; persistent lock retained; all packet cleanup `not_required` |
| lock type/owner/mode/link/device/identity or acquired payload violates the frozen owner model | `stage/materialization_lock_foreign` | do not chmod, truncate, replace, or unlink lock; close descriptor; all packet cleanup `not_required` |
| held-lock compare, truncate, sync, unlock, or close release contract fails | `rollback/materialization_lock_release_failed` | no success; do not clobber lock path/payload; report prior rollback statuses and close descriptor |
| no `renameat2(RENAME_NOREPLACE)` capability | `publish/atomic_noreplace_unavailable` | capability preflight precedes staging; no target authority; all packet cleanup `not_required` |
| activating call lacks `renameat2(RENAME_EXCHANGE)` | `activate/atomic_exchange_unavailable` | capability preflight precedes staging; no target/bookkeeping authority; all packet cleanup `not_required` |
| eight staging-name collisions | `stage/staging_name_exhausted` | no staging object obtained; all `not_required` |
| target exists or kernel collision | `publish/run_bundle_target_exists` | `published_target=None`; staging cleanup only |
| cross-device target publication | `publish/run_bundle_cross_device` | `published_target=None`; staging cleanup only |
| other target publication or report-root fsync failure | `publish/run_bundle_publish_failed` | staging cleanup before rename, identity-matched target cleanup after rename |
| pre-existing non-regular pointer or baseline | `activate/active_bookkeeping_nonregular` | identity-matched published-target rollback; no foreign bookkeeping removal |
| eight bookkeeping-temp collisions | `activate/bookkeeping_name_exhausted` | identity-matched published-target rollback; temp cleanup as applicable |
| baseline snapshot/temp/compare/replace failure | `activate/active_baseline_publish_failed` | restore only a recorded published baseline; remove target only after every required restore passes |
| pointer compare/replace or report-root sync failure | `activate/active_pointer_publish_failed` | restore exact writer-owned pointer first, then baseline; remove target only after both pass |
| bookkeeping compare-before-restore, exchange, quarantine, or no-clobber check fails | cause detail `bookkeeping_restore_conflict`, top-level `rollback/run_bundle_rollback_failed` | leave unknown path untouched; skip dependent restore/target deletion; report exact retained path |
| any required cleanup or restoration failure | top-level `rollback/run_bundle_rollback_failed`, original row retained in `cause_code` | every attempted status and sorted failed path reported; never success; release lock through the frozen lifecycle |

## Producer Call Paths and Public Behavior

### `task_start.py`

`main` parses the explicit JSON once through
`parse_active_design_packet_input`; resolves preflight, context, roles, agent
types, and selected skills; computes `active_skills` and `review_roles`; calls
`format_start_declaration` once; calls
`build_run_start_monitoring_entries(command="task_start", ...)` once; builds
one `RunBundleSpec(activation=RunActivationSpec(...))`; and calls
`create_run_bundle` once. `emit_task_start_output` receives the already-computed
skills, reviewers, and declaration instead of recomputing them.
`TaskStartRuntime` stores fields from the returned
`RunBundleMaterialization`; activation guarantees its `active_pointer` is not
`None`. It performs no `run_active_design_packet`, direct
`.active_run.write_text`, authority baseline write, or `append_monitoring` call.
CLI `CREATED_FILES`, document packets, active packet, and active pointer come
from the returned object.

### `bootstrap_agent_run.py`

The bootstrap route follows the identical sequence with
`command="bootstrap_agent_run"`; `emit_bootstrap_output` receives and emits the
one precomputed declaration. Producer-specific signal text remains input data
in `MonitoringEntries`; its projection and publication remain canonical
materializer work.

### Other producers

- `doc_start.py#main` changes from treating the return as a tuple to reading
  `.created_files`; activation remains `None`.
- `check_agent_runtime_alignment.py` and
  `smoke_test_research_perspective_pack.py` already call
  `create_run_bundle` and ignore its return. They are verify-only unless a
  public regression exposes a real caller mismatch.
- No producer creates a packet path, writes a manifest, mutates a wave ledger,
  or writes a pointer independently.

### Producer error and exit mapping

Task-start and bootstrap catch `ActiveDesignPacketInputError` before creating
the spec, print these exact lines, and return exit status 2:

```text
ACTIVE_DESIGN_PACKET_INPUT=fail
ACTIVE_DESIGN_PACKET_ERROR=<code>
ACTIVE_DESIGN_PACKET_FIELD=<field>
```

Task-start, bootstrap, and doc-start catch
`RunBundleMaterializationError`, print these exact lines, and return exit status
1:

```text
RUN_BUNDLE_MATERIALIZATION=fail
RUN_BUNDLE_PHASE=<phase>
RUN_BUNDLE_ERROR=<code>
RUN_BUNDLE_CAUSE=<cause_code>
RUN_BUNDLE_ROLLBACK=staging:<status>,target:<status>,pointer:<status>,baseline:<status>,temp:<status>
RUN_BUNDLE_ROLLBACK_FAILED_PATHS=<comma-separated-sorted-paths-or->
```

They print no success fields after either failure. Input failure, validation,
rendering, staging, target collision, and target publication leave the prior
pointer bytes unchanged; rollback fields expose any cleanup failure. Smoke and
alignment callers do not translate the exception: their existing top-level
checker boundary reports failure, and V4 verifies absent partial target state.
Success preserves exit status 0 and the existing public output keys, sourced
from `RunBundleMaterialization`.

## Waterfall Manifest-Consumer Ownership

The one shared loader and validator are defined normatively under `Public Types
and APIs`; this section fixes their sole waterfall call path and adds no gate-
local value or rule.

### S5 / T6 / V7 contiguous ownership, trace, and oracle

- **S5 responsibility:** `agent_team.py` owns the persisted projection loader,
  packet semantic validator, violation ordering, and packet blocker codes.
  `waterfall_gate_check.py` owns only gate selection, mapping each returned
  violation to `GateBlocker`, generic non-packet implementation checks, and
  existing CLI rendering.
- **T6 implementation:** import
  `load_materialized_active_design_packet` and
  `validate_materialized_active_design_packet`; execute the exact call path
  below; delete every gate-local packet constant, type, parser, path resolver,
  identity extractor, projector, and revalidator listed in the deletion
  section. No old helper remains as a wrapper.
- **V7 oracle:** the three packet-consuming gates emit the same ordered public
  blocker grammar and owner routing from shared violations, ignore unselected
  sibling/history/schedule prose, and contain none of the deleted local packet
  symbols. Generic implementation-artifact blockers still run afterward and
  keep implementation ownership.

The shared owner emits this closed blocker grammar. Existing public codes are
preserved exactly:

```text
team_manifest.yaml:missing
team_manifest.yaml:active_design_packet_field_invalid:manifest
team_manifest.yaml:active_design_packet_missing
team_manifest.yaml:active_design_packet_field_missing:<field>
team_manifest.yaml:active_design_packet_field_invalid:<field>
team_manifest.yaml:active_design_packet_schema_unknown:<schema>
team_manifest.yaml:active_design_packet_path_outside_bundle:<field>
<design-artifact>:missing
<design-artifact>:template_or_placeholder_remaining
<design-artifact>:section_empty_or_missing:<section-slug>
<review-artifact>:design_artifact_path_missing
<review-artifact>:design_artifact_path_mismatch
<review-artifact>:review_target_sha256_missing
<review-artifact>:review_target_sha256_mismatch
<review-artifact>:decision_not_approve
```

New reference semantics use only this parameterized code:

```text
team_manifest.yaml:active_design_packet_reference_invalid:
  <section>:<field>:<zero-based-input-index>:<reason>
```

`section` is one of the four packet keys; `field` is one of
`clause_refs`, `owner_refs`, `source_refs`, `dependency_refs`, `output_refs`,
or `reviewer_refs`; and `reason` is exactly one of `clause_unknown`,
`owner_unknown`, `source_missing`, `source_digest_mismatch`,
`source_fragment_mismatch`, `dependency_edge_missing`, `output_missing`,
`reviewer_output_mismatch`, or `projection_mismatch`. Loader shape failures
that cannot name a section retain the existing manifest codes above. No
exception text, parser message, filesystem prose, or inferred term appears in
a public blocker code.

Violation order is deterministic and externally observable:

1. manifest/packet shape fields in declaration order;
2. reference results in four-section order, field order
   `clause,owner,source,dependency,output,reviewer`, then input index;
3. selected design-artifact structural checks in declared section order;
4. design-review identity in path, target-SHA, decision order;
5. document-flow-review identity in the same order when required; and
6. generic implementation `ArtifactCheck` results in existing
   `GATE_CHECKS["implementation"]` order.

Every manifest, projection, reference, design-artifact, and selected-review
violation has `owner_gate="design"`. Generic implementation-artifact results
retain `owner_gate="implementation"`; unrelated gates retain their current
gate owner. `next_action_for_gate` is unchanged: it selects the first blocker
whose owner differs from the current gate, or the current gate when none does.
Thus shared ownership changes implementation location without changing public
CLI routing semantics.

### Exact `waterfall_gate_check.py` call path

For `design`, `document_flow`, and `implementation`, `main` becomes:

```python
loaded = load_materialized_active_design_packet(report_dir)
blockers.extend(
    GateBlocker(
        code=render_active_design_packet_violation(item),
        owner_gate="design",
    )
    for item in loaded.violations
)
if loaded.value is not None and loaded.context is not None:
    blockers.extend(
        GateBlocker(
            code=render_active_design_packet_violation(item),
            owner_gate="design",
        )
        for item in validate_materialized_active_design_packet(
            loaded.value,
            loaded.context,
            gate=gate,
        )
    )
```

The existing implementation-gate `ArtifactCheck` loop runs afterward only for
non-packet implementation artifacts. Other waterfall gates keep their generic
checks.

The following gate-local semantics are deleted: packet schema constants,
`ActiveDesignPacket`, abstract-term keyword tables, YAML packet mapping guards,
path resolution, review path/SHA extraction, packet review validation,
document-flow packet validation, and packet section validation. In particular,
`check_artifact` no longer branches on `design_brief.md` to infer Abstract
Design Frame content. This closes S5: the gate maps shared violations and owns
no packet parser, projector, or revalidator.

## Historical Additions Deleted or Replaced

This is one source-first deletion/replacement operation, not a set of
file/finding/test work units.

### `agent_team.py`

Delete or replace the `9ba4bba5` additions
`ActiveDesignPacketConfig`, `ACTIVE_DESIGN_PACKET_FIELDS`,
`normalize_active_design_packet_config`,
`resolve_active_design_packet_config`, `manifest_active_design_packet_lines`,
`active_design_packet_artifact_map`, `run_active_design_packet`, direct-writing
`write_team_manifest`, direct-writing `write_initial_wave_execution_gate`, and
all optional-packet branches in `selected_role_outputs`,
`selected_artifact_name`, `iter_artifacts`, `resolve_role_document_packet`,
`build_manifest`, role/write-policy/document-packet/artifact manifest helpers,
and `render_subagent_prompt_packet`. Retain the public name
`parse_active_design_packet_input` with the new return type and retain
`create_run_bundle` with the new result and sole-delegator contract.

### Producer additions

Delete the duplicated 79-line changed branches in `task_start.py` and
`bootstrap_agent_run.py`: separate packet resolution, separate tuple capture,
direct pointer write, `write_task_authority_baselines`, and post-create
monitoring mutation. Replace them with the one-call result mapping above.

### Waterfall additions

Delete every local item named in `Waterfall Manifest-Consumer Ownership`,
including `ActiveDesignPacket`, all `ACTIVE_DESIGN_PACKET_*` and
`ABSTRACT_DESIGN_FRAME_REQUIRED_TERMS` constants,
`check_abstract_design_frame`, `abstract_term_has_content`,
`resolve_active_design_packet_path`, `is_string_value`,
`is_string_object_mapping`, `active_design_blocker`,
`load_active_design_packet`, `review_target_sha256`,
`review_design_artifact_path`, `check_review_identity`,
`check_active_document_flow_review`, and `check_active_design_packet`.

### Historical test additions subject to post-source classification

The following 25 additions are historical inventory from `9ba4bba5`, not an
authorized test edit list and not a success count. Product source is completed
and validated first. The writer then reads an existing assertion only when a
source failure identifies it. If an assertion concretely conflicts with the
approved public contract, implementation pauses and this design is revised to
name that exact stale assertion and exact delete/rewrite action. Otherwise the
test remains untouched. A new assertion or test file requires a revised design
that records a concrete unresolved public oracle after the source mechanism
exists.

- `test_workflow_selected_packet_is_materialized_and_owned_by_roles`
- `test_generation_and_manifest_reject_selected_final_symlink`
- `test_generation_and_manifest_reject_selected_symlink_parent`
- `test_generation_rejects_existing_nonregular_packet_target`
- `test_bootstrap_generates_explicit_graph_active_packet`
- `test_task_start_generates_explicit_graph_active_packet`
- `test_entrypoints_reject_partial_or_invalid_active_packet_atomically`
- `test_document_flow_gate_is_ready_when_packet_marks_flow_inactive`
- `test_document_flow_gate_uses_declared_graph_review_and_ignores_generic`
- `test_design_gate_accepts_path_sha_decision_without_abstract_review`
- `test_design_gate_rejects_technical_review_wrong_path_with_same_sha`
- `test_design_gate_rejects_flow_review_wrong_path_with_same_sha`
- `test_design_gate_accepts_path_sha_decision_without_source_packet_metadata`
- `test_custom_packet_review_routes_implementation_to_design_owner`
- `test_graph_packet_selection_ignores_historical_design_basenames`
- `test_graph_packet_revise_review_fails_closed`
- `test_design_gate_rejects_missing_manifest`
- `test_design_gate_rejects_missing_packet_field`
- `test_design_gate_rejects_wrong_packet_field_type`
- `test_design_gate_rejects_absolute_packet_path`
- `test_design_gate_rejects_unknown_packet_schema`
- `test_design_gate_rejects_packet_path_outside_bundle`
- `test_design_gate_rejects_final_component_symlink`
- `test_design_gate_rejects_symlinked_parent`
- `test_design_gate_rejects_missing_required_flow_review`

The public behaviors remain equal explicit packet behavior across task-start
and bootstrap; validate/render failure leaves target and pointer unchanged;
published packet projections agree; waterfall consumes only the manifest-
selected packet and reports shared semantic violations. Existing tests are
read-only evidence in this packet. There is no mandatory predecessor oracle,
new test, test-file edit, assertion count, test count, or line-count acceptance
measure.

## File Scope and Individual Validation Mapping

The two unit-owned source-packet files repeat every record with all ten fields.
No record inherits a field from this design, and the records authorize one
integrated writer rather than file-level writers.

### Normative source and delete/rewrite records

Each row is complete implementation authority; no field is inherited from a
paragraph, another row, or a separate map.

| Class and path | Exact owner | Action and reason | Exact symbols or sections | Request clauses | Reverse edges and consumers | Trace | Validation | Rollback or atomicity effect | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| delete/rewrite `tools/agent_tools/agent_team.py` | `agent_team.py#ActiveDesignPacketValue,create_run_bundle` | Delete the `9ba4bba5` local packet/parser/writer branches and replace them with the neutral resolver, reference context, one materializer, one lock owner, and one manifest consumer. | `ActiveDesignClause`, `ActiveDesignPacketEntry`, `ActiveDesignPacketValue`, `_decode_active_design_packet`, `parse_active_design_packet_input`, `resolve_active_design_packet`, `SourceReferenceResult`, `DependencyReferenceResult`, `RoleOutputProjection`, `ReviewerArtifactProjection`, `ClauseReferenceResult`, `OutputReferenceResult`, `ActiveDesignReferenceContext`, four violation variants, `render_active_design_packet_violation`, `FileIdentity`, `MaterializationLockIdentity`, `MaterializationLock`, `BookkeepingFileState`, `BookkeepingTempState`, `PriorBookkeepingState`, `StagedArtifactSet`, `PublishedTarget`, `RunActivationSpec`, `RunBundleSpec`, `RunBundleMaterialization`, `iter_artifacts`, seven `project_*` functions, `build_manifest`, `_acquire_materialization_lock`, `_release_materialization_lock`, `_build_in_memory_artifact_set`, `_stage_artifact_set`, `_rename_directory_noreplace`, `_publish_active_bookkeeping`, `_rollback_publication`, loader, validator, `_materialize_run_bundle`, `create_run_bundle` | ADP-01–ADP-08, ADP-11, RF-02 | Reverse edges: `task_start.py`, `bootstrap_agent_run.py`, `doc_start.py`, `waterfall_gate_check.py`, `check_agent_runtime_alignment.py`, `smoke_test_research_perspective_pack.py`; consumers: every run-bundle producer and waterfall gate. | T1, T2, T3, T4 | V1–V7 | All validation/rendering precedes staging; one persistent lock, verified stage, no-replace target, pointer-last activation, compare-before-restore, and no-clobber rollback. | First production edit; old symbols are deleted, not wrapped or retained. |
| delete/rewrite `tools/agent_tools/task_start.py` | `task_start.py#main` | Delete duplicated packet resolution, pointer, authority-baseline, and monitoring writes; delegate one fully built spec. | `TaskStartRuntime`, `emit_task_start_output`, delete `record_task_start_monitoring`, `main` | ADP-02, ADP-06–ADP-09, ADP-11 | Reverse edges: `ROOT_AGENTS.md`, `test_task_start_and_close.py`; consumers: task-start CLI and bootstrap parity checks. | T5 | V5 | Calls `create_run_bundle` once; any materialization error leaves no producer-local output or pointer mutation. | Edit after `agent_team.py`; no local parser/projector/revalidator remains. |
| delete/rewrite `tools/agent_tools/bootstrap_agent_run.py` | `bootstrap_agent_run.py#main` | Delete the duplicated 79-line producer branch and every post-create mutation; delegate one fully built spec. | `BootstrapRuntime`, `emit_bootstrap_output`, delete `record_bootstrap_monitoring`, `main` | ADP-02, ADP-06–ADP-09, ADP-11 | Reverse edges: `ROOT_AGENTS.md`, `test_task_start_and_close.py`; consumers: bootstrap CLI and task-start parity checks. | T5 | V5 | Calls `create_run_bundle` once; no direct target, baseline, pointer, or monitoring write. | Edit after `agent_team.py`; public explicit-packet behavior is retained. |
| edit `tools/agent_tools/doc_start.py` | `doc_start.py#main` | Consume the canonical materialization result instead of tuple/private writer shape. | `main` | ADP-02, ADP-06, ADP-07 | Reverse edge: `test_doc_start.py`; consumer: doc-start CLI. | T5 | V5 | Nonactivating spec publishes only through `create_run_bundle`; `active_pointer` remains null. | Edit after the materializer; no packet semantics added. |
| delete/rewrite `tools/agent_tools/waterfall_gate_check.py` | `waterfall_gate_check.py#main` | Delete all gate-local packet type/parser/path/project/review semantics and consume the shared loaded value and validator. | Delete `ACTIVE_DESIGN_PACKET_SCHEMA`, `ACTIVE_DESIGN_PACKET_FIELDS`, `ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS`, `ABSTRACT_DESIGN_FRAME_REQUIRED_TERMS`, `ActiveDesignPacket`, `check_abstract_design_frame`, `abstract_term_has_content`, `resolve_active_design_packet_path`, `is_string_value`, `is_string_object_mapping`, `active_design_blocker`, `load_active_design_packet`, `review_target_sha256`, `review_design_artifact_path`, `check_review_identity`, `check_active_document_flow_review`, `check_active_design_packet`; retain CLI `main` with shared calls. | ADP-02–ADP-05, ADP-08, RF-03 | Reverse edges: `implementation-waterfall-workflow.md`, `test_waterfall_gate_check.py`, `references/workflow/implementation-waterfall.md`; consumers: design, document-flow, implementation gates. | T6 | V7 | Read-only consumer; no staging/publication authority and no partial gate success after any violation. | Edit after shared loader/validator; every listed local symbol is absent. |
| edit `tools/agent_tools/task_authority.py` | `task_authority.py#hash_baseline_bytes` | Retain byte hashing/validation, delete the producer-side baseline writer, and let the in-memory projector own initial bytes. | `hash_baseline_bytes`, `authority_baseline_path`, `write_hash_baseline`; delete unreferenced `write_task_authority_baselines` | ADP-02, ADP-06, ADP-11, RF-02 | Reverse edges: `agent_team.py`, `test_task_authority.py`; consumers: authority projector and public baseline verifier. | T4 | V4, V5 | Authority bytes enter the staged artifact set; no post-publication baseline write or independent rollback. | Edit with the materializer seam; retain later operational validation helpers. |
| edit `tools/agent_tools/workflow_monitor.py` | `workflow_monitor.py#render_monitoring_artifacts` | Split pure construction/rendering from later locked append behavior so initial monitoring is staged in memory. | `MonitoringEntries`, `build_run_start_monitoring_entries`, `render_monitoring_artifacts`, `append_monitoring`, `append_monitoring_sections`, `normalized_wave_rows` | ADP-02, ADP-03, ADP-06, ADP-11 | Reverse edges: `agent_team.py`, `task_start.py`, `bootstrap_agent_run.py`, `test_workflow_monitor.py`; consumers: initial wave projector and later monitor appends. | T3, T4 | V3, V5 | Initial bytes publish with the bundle; later append retains its existing lock and never mutates initial publication during creation. | Edit before producers; WAIT-1 operation-resolution symbols remain untouched. |
| edit `tools/agent_tools/report_artifact_checks.py` | `report_artifact_checks.py#parse_review_identity` | Centralize authoritative review identity parsing for waterfall and predecessor verification without copying regexes. | `ReviewIdentityResult`, `parse_review_identity`, `section_has_content`, `has_approve_decision` | ADP-05, ADP-13, RF-03 | Reverse edges: `agent_team.py`, `github_publish.py`, `waterfall_gate_check.py`; consumers: shared packet validator and predecessor producer/verifier. | T6, T9 | V7, V10 | Pure parse result; no file publication or rollback authority. | Edit after source owner; current structural and decision parsers remain authoritative. |
| edit `tools/agent_tools/github_publish.py` | `github_publish.py#build_parser,run,emit_summary` | Add the generic record type, strict loader, per-unit producer, individual/set verifier, total failures, and three parser-owned CLI actions. | Existing `build_parser`, `run`, `emit_summary`, `verify_remote`, `json_object`; new `add_predecessor_integration_arguments`, `add_predecessor_verification_arguments`, `add_predecessor_set_verification_arguments`, `_canonical_json_line_bytes`, `PredecessorIntegrationRecord`, `PredecessorIntegrationError`, `PredecessorIntegrationVerification`, `PredecessorIntegrationInput`, `PredecessorIntegrationSetVerification`, `predecessor_integration_filename`, `produce_predecessor_integration_record`, `load_predecessor_integration_record`, `verify_predecessor_integration_record`, `verify_predecessor_integration_set` | ADP-05, ADP-09, ADP-13, RF-03, RF-04 | Reverse edges: `agent-canon-pr-workflow.md`, `pr-processing.md`, runtime PR skill, `documents/tools/github_publish.md`, `ARTIFACT_PLACEMENT.md`, `runtime-log-archive.md`; consumers: PR-processing producer and successor intake. | T9 | V10 | Record serialization completes in memory; identity-owned temp and `RENAME_NOREPLACE` prevent partial/overwrite publication; verifiers are read-only and set output is all-or-nothing. | Source edit after review parser; `test_github_publish.py` is not an unconditional edit. |
| edit `agents/agents_config.json` | `agents_config.json#artifacts.active_design_packet` | Install the exact four-section record and closed reference fields consumed by the one resolver. | `artifacts.active_design_packet` | ADP-01, ADP-03, ADP-05, ADP-07 | Reverse edge: `agent_team.py`; consumers: config loader, workflow selection, manifest projection. | T1 | V1, V2 | Parsed before staging; invalid cardinality or joins fail with no filesystem mutation. | Source-first normative config edit after `agent_team.py`; strict JSON remains commentless. |
| edit `agents/TASK_WORKFLOWS.md` | `TASK_WORKFLOWS.md#Design Artifact Shape` | Route all four design records to the neutral value and one implementation unit. | `Design Artifact Shape` | ADP-01, ADP-03, ADP-09, RF-01 | Reverse edges: `agent_team.py`, `implementation-waterfall-workflow.md`; consumers: workflow readers and design templates. | T7 | V8 | Documentation has no runtime publication; it lands in the source commit and is reverted with the unit if source is reverted. | Edit after source behavior. |
| edit `agents/canonical/CLI_ENTRYPOINTS.md` | `CLI_ENTRYPOINTS.md#Run Bootstrap,Predecessor Integration` | Document sole run-bundle delegator plus all three predecessor actions and exact call graph. | `Run Bootstrap`, new `Predecessor Integration` | ADP-06, ADP-09, ADP-13, RF-04 | Reverse edges: `task_start.py`, `bootstrap_agent_run.py`, `github_publish.py`, PR-processing skills; consumers: CLI operators and run bootstrap. | T5, T7, T9 | V5, V8, V10 | Documentation-only; commands describe atomic owners and cannot authorize a caller-local writer. | Edit after all public signatures freeze. |
| edit `agents/canonical/CODEX_WORKFLOW.md` | `CODEX_WORKFLOW.md#Design Integrity Gate,Run Bootstrap,Implementation` | Replace prose inference with exact active-packet authority and source-first unit sequencing. | `Design Integrity Gate`, `Run Bootstrap`, `Implementation` | ADP-01–ADP-09, ADP-12 | Reverse edges: `TASK_WORKFLOWS.md`, orchestration skills, waterfall workflow; consumers: Codex workflow readers. | T1, T5, T7 | V5, V8 | Documentation-only; unit rollback removes the route with source. | Edit after source and templates. |
| edit `agents/workflows/implementation-waterfall-workflow.md` | `implementation-waterfall-workflow.md#Active design packet,Gate 5,Gate 6,Gate 7,Gate 8` | Close the S5 call path and require the canonical loader/validator without gate-local semantics. | `Active design packet`, `Gate 5`, `Gate 6`, `Gate 7`, `Gate 8` | ADP-02–ADP-05, ADP-09 | Reverse edges: `waterfall_gate_check.py`, `design_review.md`, `document_flow_review.md`, `change_review.md`, `final_review.md`; consumers: waterfall gates and reviewers. | T6, T7 | V7, V8 | Read-only gate contract; a failure emits one blocker set and performs no run publication. | Edit with waterfall consumer and review templates. |
| edit `agents/workflows/agent-canon-pr-workflow.md` | `agent-canon-pr-workflow.md#標準手順,PR 完了条件` | Add post-merge two-unit production, archive, individual verification, and set verification. | `標準手順`, `PR 完了条件` | ADP-09, ADP-13, RF-03, RF-04, RF-06 | Reverse edges: `github_publish.py`, `runtime_log_archive_git.py`, PR-processing skills; consumers: source PR closeout and successor intake. | T9 | V10, V12 | Archive runs only after both atomic producers; completion is withheld on any typed or graph-predecessor failure. | Edit after CLI contract freezes. |
| edit `agents/templates/README.md` | `agents/templates/README.md#Active Design Packet Projection` | Register one four-section projection and exact template ownership. | `Active Design Packet Projection` | ADP-01, ADP-03, ADP-09 | Reverse edges: five review/design templates and `agent_team.py`; consumers: template authors and renderer. | T7 | V3, V8 | Template index has no publication authority; reverted with template/source unit. | Edit with all template rows. |
| edit `agents/templates/design_brief.md` | `design_brief.md#Abstract Design Frame,Implementation Source Packet,Design Side-Effect Map,Design-To-Implementation Trace` | Make all four sections exact typed inputs rather than prose-inferred headings. | Four named sections | ADP-01, ADP-03–ADP-05, ADP-09 | Reverse edges: `agents_config.json`, `agent_team.py`, `design_review.md`; consumers: design authors, packet resolver, reviewer. | T1, T7 | V2, V8 | Rendered fully in memory and included in artifact-set validation before staging. | Edit with config and renderer. |
| edit `agents/templates/design_review.md` | `design_review.md#Design Artifact Under Review` | Review exact artifact identity and all four typed sections. | `Design Artifact Under Review`, `Abstract Design Frame Review`, `Implementation Source Packet Review`, `Design Side-Effect Map Review`, `Design-To-Implementation Trace Review` | ADP-01, ADP-03, ADP-09 | Reverse edges: `report_artifact_checks.py`, waterfall workflow; consumers: design reviewer and predecessor review identity parser. | T6, T7 | V7, V8 | Review is an authorization artifact only; no target publication; non-APPROVE blocks source. | Edit with parser owner. |
| edit `agents/templates/document_flow_review.md` | `document_flow_review.md#Term And Prerequisite Introduction,Reader-Visible Side Effects` | Bind reader flow to the exact source packet and side-effect projection. | `Term And Prerequisite Introduction`, `Reader-Visible Side Effects` | ADP-03–ADP-05, ADP-09 | Reverse edges: waterfall workflow and shared validator; consumer: document-flow reviewer. | T6, T7 | V7, V8 | Authorization-only; no product publication and no partial gate success. | Edit with design review template. |
| edit `agents/templates/change_review.md` | `change_review.md#Design-Base Implementation Review,User Request Trace Review,Repo-Wide Dependency Review` | Require one integrated diff against exact trace and graph replacement state. | Three named sections | ADP-08, ADP-09, ADP-12, RF-01, RF-05, RF-06 | Reverse edges: waterfall workflow; consumer: change reviewer. | T7 | V8–V12 | Review cannot mutate source or tests; REVISE keeps implementation unapproved. | Edit after source behavior is designed. |
| edit `agents/templates/final_review.md` | `final_review.md#Design Trace Acceptance,Design Side-Effect Trace Acceptance,Repo-Wide Dependency Review` | Require final integrated behavior, atomicity, predecessor, and replacement evidence. | Three named sections | ADP-09, ADP-11–ADP-13, RF-02–RF-06 | Reverse edges: waterfall workflow; consumer: final reviewer. | T7 | V8–V12 | Review-only; no publication and no completion on partial evidence. | Edit after validation contract freezes. |
| edit `agents/skills/agent-orchestration.md` | `agent-orchestration.md#Decision Order,Outputs,Codex Implementation Routing` | Route the approved owner-preserving responsibility graph to one Luna worker and one materializer. | `Decision Order`, `Outputs`, `Codex Implementation Routing` | ADP-06, ADP-09, ADP-12 | Reverse edge: runtime orchestration skill; consumers: routing agents and Luna handoff. | T7, T10 | V8, V11 | Instruction-only; cannot create a run outside `create_run_bundle` or split work absent conflict/predecessor evidence. | Edit with runtime view; no file/finding/test slice. |
| edit `.agents/skills/agent-orchestration/SKILL.md` | `.agents/skills/agent-orchestration/SKILL.md#Tool Commands` | Mirror canonical run-bundle and implementation-handoff route without schema prose. | `Tool Commands` items `run-bundle-materialization`, `implementation-handoff` | ADP-06, ADP-09 | Reverse edge: canonical orchestration skill; consumer: runtime skill loader. | T7 | V8 | Runtime instruction-only; revert with canonical skill. | Edit in the canonical/runtime pair. |
| edit `agents/skills/codex-task-workflow.md` | `codex-task-workflow.md#Stages,Required Output` | Require the approved typed packet and one implementation unit at execution. | `Stages`, `Required Output` | ADP-01, ADP-06, ADP-09 | Reverse edge: runtime Codex task skill; consumers: task workflow agents. | T7 | V8 | Instruction-only; no writer or publication authority. | Edit with runtime view. |
| edit `.agents/skills/codex-task-workflow/SKILL.md` | `.agents/skills/codex-task-workflow/SKILL.md#Tool Commands` | Mirror approved-packet and implementation-unit commands. | `Tool Commands` items `approved-design-packet`, `implementation-slice` | ADP-01, ADP-06, ADP-09 | Reverse edge: canonical Codex task skill; consumer: runtime skill loader. | T7 | V8 | Runtime instruction-only; revert with canonical skill. | Edit in the canonical/runtime pair. |
| edit `agents/skills/pr-processing.md` | `pr-processing.md#Procedure,AgentCanon Queue` | Make post-merge predecessor production and verification the canonical queue step. | `Procedure`, `AgentCanon Queue` | ADP-09, ADP-13, RF-03, RF-04, RF-06 | Reverse edges: runtime PR skill, PR workflow, `github_publish.py`, archive owner; consumers: PR processors. | T9 | V10, V12 | No record archive until both atomic producers succeed; any error suppresses completion. | Edit with runtime skill and PR workflow. |
| edit `.agents/skills/pr-processing/SKILL.md` | `.agents/skills/pr-processing/SKILL.md#Tool Commands` | Mirror exact produce, archive, individual-verify, set-verify, and graph replacement sequence. | `Tool Commands` items `predecessor-integration-produce`, `archive`, `verify`, `verify-set`, `graph-static-validation` | ADP-09, ADP-13, RF-03, RF-04, RF-06 | Reverse edge: canonical PR-processing skill; consumer: runtime skill loader. | T9 | V10, V12 | Runtime instruction-only; no partial record/set output is accepted. | Edit in the canonical/runtime pair. |
| edit `documents/tools/github_publish.md` | `documents/tools/github_publish.md#Commands,Predecessor Integration Record` | Document exact API/CLI/error/JSON/atomic publication contract. | `Commands`, `Predecessor Integration Record` | ADP-13, RF-03, RF-04 | Reverse edge: `github_publish.py`; consumers: operators and PR-processing docs. | T9 | V10 | Documentation-only; describes no-replace temp publication and read-only verification. | Edit after source API freezes. |
| edit `documents/runtime-log-archive.md` | `runtime-log-archive.md#Layout,Agent Report Archiving` | Retain each unit record and complete-file hash in one immutable snapshot. | `Layout`, `Agent Report Archiving` | ADP-09, ADP-13 | Reverse edges: `runtime_log_archive_git.py`, `ARTIFACT_PLACEMENT.md`; consumers: predecessor verifier and successor packet. | T9 | V10 | Archive starts after both records exist; immutable no-overwrite archive behavior remains authoritative. | Edit without changing archive source. |
| edit `agents/canonical/ARTIFACT_PLACEMENT.md` | `ARTIFACT_PLACEMENT.md#reports/agents/<run-id>/` | Reserve unit-derived run-local filenames and immutable archive locator. | `reports/agents/<run-id>/` | ADP-09, ADP-13 | Reverse edges: PR workflow, archive doc, `github_publish.py`; consumers: record producer and successor source packet. | T9 | V10 | Placement has no writer; atomic producer and append-only archive own mutation. | Edit with predecessor docs. |

Every edited Markdown, skill, workflow, template, and Python source row updates
its own dependency header and its named reverse edge in that row. Strict JSON
remains commentless. This paragraph adds no scope or omitted field.

### Generated artifact records

| Class and path | Exact owner | Action and reason | Exact symbols or sections | Request clauses | Reverse edges and consumers | Trace | Validation | Rollback or atomicity effect | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| generated `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_detailed_design_review.md` | `role:design_reviewer` | Produce the pre-implementation detailed-design decision for one final design path/SHA. | `Design Artifact Under Review`, decision marker, review target SHA | ADP-09, RF-06 | Reverse edge: this design; consumers: implementation authorization, predecessor producer. | T7, T9 | V8, V10, V12 | No source publication; non-APPROVE or unequal SHA leaves authorization pending. | Absent until reviewer writes it; other units cannot reuse or overwrite it. |
| generated `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_document_flow_review.md` | `role:document_flow_reviewer` | Produce the pre-implementation document-flow decision for the final design path/SHA. | identity fields, flow decision, required-change table | ADP-09 | Reverse edge: this design; consumers: waterfall document-flow gate. | T6, T7 | V7, V8 | No source publication; non-APPROVE leaves authorization pending. | Absent until reviewer writes it; other units cannot reuse or overwrite it. |
| generated `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_change_review.md` | `role:change_reviewer` | Review the integrated source-first diff and V1–V12 evidence. | design-base review, request trace, dependency review, decision | ADP-09, RF-05, RF-06 | Reverse edge: this design; consumer: post-implementation gate. | T7 | V8–V12 | Read-only review; REVISE produces no completion. | Generated only after implementation validation. |
| generated `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_final_review.md` | `role:final_reviewer` | Decide final acceptance of the integrated responsibility unit. | design trace, side-effect trace, dependency review, decision | ADP-09, ADP-11–ADP-13, RF-02–RF-06 | Reverse edge: this design; consumer: final gate. | T7 | V8–V12 | Read-only review; no partial evidence may produce APPROVE. | Generated only after change review and validation. |
| conditional generated `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_test_plan.md` | `role:test_designer` | Record a concrete unresolved public oracle only after source exists and this design is revised. | exact oracle, public entrypoint, failure mode, revised authorization | ADP-10, ADP-12, RF-05 | Reverse edge: revised design; consumer: conditional Gate 8.5 only. | T8 | V9 | No source/test mutation; absence is required while no revised oracle exists. | Currently absent and not required; not an implementation edit target. |
| generated `reports/agents/20260712-090608-context-packettool-skill-routing/predecessor_integration.knowledge_graph.json` | `tools/agent_tools/github_publish.py#produce_predecessor_integration_record(unit_id=knowledge_graph)` | Materialize the graph unit's approved post-merge record at its derived filename. | Thirteen exact record fields; unit ID `knowledge_graph` | ADP-13, RF-03, RF-04, RF-06 | Reverse edges: graph design/review, archive manifest; consumers: individual verifier, set verifier, successor packet, graph replacement gate. | T9 | V10, V12 | Canonical bytes are staged in an identity-owned temp and published no-replace; collision never overwrites; failure emits no success. | Absent until graph APPROVE and source merge; manual edit forbidden. |
| generated `reports/agents/20260712-090608-context-packettool-skill-routing/predecessor_integration.active_design_packet_materialization.json` | `tools/agent_tools/github_publish.py#produce_predecessor_integration_record(unit_id=active_design_packet_materialization)` | Materialize this unit's approved post-merge record at its derived filename. | Thirteen exact record fields; unit ID `active_design_packet_materialization` | ADP-13, RF-03, RF-04 | Reverse edges: this design/detailed review, archive manifest; consumers: individual verifier, set verifier, successor packet. | T9 | V10 | Canonical bytes are staged in an identity-owned temp and published no-replace; collision never overwrites; failure emits no success. | Absent until this unit merges; manual edit forbidden. |

### Test-file disposition records

| Class and path | Exact owner | Action and reason | Exact symbols or sections | Request clauses | Reverse edges and consumers | Trace | Validation | Rollback or atomicity effect | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| verify-only `tests/agent_tools/test_agent_team_templates.py` | `test_agent_team_templates.py` test owner | Observe existing public bundle behavior after source; do not edit from historical inventory alone. | `test_workflow_selected_packet_is_materialized_and_owned_by_roles`, `test_generation_and_manifest_reject_selected_final_symlink`, `test_generation_and_manifest_reject_selected_symlink_parent`, `test_generation_rejects_existing_nonregular_packet_target` | ADP-08, ADP-10, ADP-12, RF-05 | Reverse edge: `agent_team.py`; consumers: post-source regression observation. | T8 | V9 | Tests perform no publication; any edit requires a revised design naming a concrete stale public assertion. | Verify-only; not in `allowed_edit_path`. |
| verify-only `tests/agent_tools/test_task_start_and_close.py` | `test_task_start_and_close.py` test owner | Observe existing producer public behavior after source; do not edit from line/count evidence. | `test_bootstrap_generates_explicit_graph_active_packet`, `test_task_start_generates_explicit_graph_active_packet`, `test_entrypoints_reject_partial_or_invalid_active_packet_atomically` | ADP-08, ADP-10, ADP-12, RF-05 | Reverse edges: `task_start.py`, `bootstrap_agent_run.py`; consumers: producer parity observation. | T8 | V9 | Tests perform no publication; any edit requires a revised design naming a concrete stale public assertion. | Verify-only; not in `allowed_edit_path`. |
| verify-only `tests/agent_tools/test_waterfall_gate_check.py` | `test_waterfall_gate_check.py` test owner | Observe existing public gate output after source; private gate-helper shape has no authority. | `test_document_flow_gate_is_ready_when_packet_marks_flow_inactive`, `test_document_flow_gate_uses_declared_graph_review_and_ignores_generic`, `test_design_gate_accepts_path_sha_decision_without_abstract_review`, `test_design_gate_rejects_technical_review_wrong_path_with_same_sha`, `test_design_gate_rejects_flow_review_wrong_path_with_same_sha`, `test_design_gate_accepts_path_sha_decision_without_source_packet_metadata`, `test_custom_packet_review_routes_implementation_to_design_owner`, `test_graph_packet_selection_ignores_historical_design_basenames`, `test_graph_packet_revise_review_fails_closed`, `test_design_gate_rejects_missing_manifest`, `test_design_gate_rejects_missing_packet_field`, `test_design_gate_rejects_wrong_packet_field_type`, `test_design_gate_rejects_absolute_packet_path`, `test_design_gate_rejects_unknown_packet_schema`, `test_design_gate_rejects_packet_path_outside_bundle`, `test_design_gate_rejects_final_component_symlink`, `test_design_gate_rejects_symlinked_parent`, `test_design_gate_rejects_missing_required_flow_review` | ADP-08, ADP-10, ADP-12, RF-05 | Reverse edge: `waterfall_gate_check.py`; consumers: public gate regression observation. | T8 | V9 | Tests perform no publication; any edit requires a revised design naming a concrete stale public assertion. | Verify-only; not in `allowed_edit_path`. |
| verify-only `tests/agent_tools/test_github_publish.py` | `test_github_publish.py` test owner | Observe existing publish behavior; this packet creates no mandatory predecessor oracle. | Existing public `github_publish.py` tests; no new symbol is authorized | ADP-12, ADP-13, RF-05 | Reverse edge: `github_publish.py`; consumer: existing regression observation. | T8, T9 | V9, V10 | Tests write only isolated fixtures; production record atomicity is validated by direct public CLI evidence. | Verify-only; no unconditional edit or new test. |
| verify-only `tests/agent_tools/test_check_agent_runtime_alignment.py` | runtime-alignment test owner | Observe existing direct `create_run_bundle` callers. | Existing public alignment tests | ADP-06, RF-05 | Reverse edge: `check_agent_runtime_alignment.py`; consumer: V5. | T5 | V5, V9 | Fixture-only; no production publication. | Verify-only; edit requires revised evidence. |
| verify-only `tests/agent_tools/test_doc_start.py` | doc-start test owner | Observe `.created_files` public result. | Existing doc-start public tests | ADP-06, RF-05 | Reverse edge: `doc_start.py`; consumer: V5. | T5 | V5, V9 | Fixture-only; no production publication. | Verify-only; edit requires revised evidence. |
| verify-only `tests/agent_tools/test_workflow_monitor.py` | workflow-monitor test owner | Observe pure renderer/later append public behavior. | Existing monitoring public tests | ADP-02, RF-05 | Reverse edge: `workflow_monitor.py`; consumer: V3/V5. | T3, T5 | V3, V5, V9 | Fixture-only; no production publication. | Verify-only; edit requires revised evidence. |
| verify-only `tests/agent_tools/test_task_authority.py` | task-authority test owner | Observe baseline hash validation. | Existing authority public tests | ADP-11, RF-05 | Reverse edge: `task_authority.py`; consumer: V4. | T4 | V4, V9 | Fixture-only; no production publication. | Verify-only; edit requires revised evidence. |
| verify-only `tests/agent_tools/test_runtime_log_archive_git.py` | runtime-archive test owner | Observe immutable snapshot/manifest/index behavior consumed unchanged. | Existing archive public tests | ADP-13, RF-05 | Reverse edge: `runtime_log_archive_git.py`; consumer: V10. | T9 | V9, V10 | Fixture archive only; production archive remains append-only. | Verify-only; edit requires revised evidence. |

### Current packet and obsolete-checker records

| Class and path | Exact owner | Action and reason | Exact symbols or sections | Request clauses | Reverse edges and consumers | Trace | Validation | Rollback or atomicity effect | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current-turn edit `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md` | `active-design-packet-materialization` design owner | Repair F1–F6 while preserving the approved responsibility, schema, predecessor, and successor decisions. | `File Scope and Individual Validation Mapping`, `Atomic Publication and Failure Contract`, `Durable Post-Merge Predecessor Integration Record`, `One-Writer Implementation Sequence`, `Targeted Validation`, `Review and Handoff` | ADP-01–ADP-13, RF-01–RF-06 | Reverse edges: the two unit-owned packet files and four unit-owned review paths; consumers: one implementation writer and reviewers. | T1–T10 | V1–V12 plus current Markdown/dependency/convention checks | No product/runtime mutation; final bytes bind both packet hashes and reviews bind the final design SHA; revision rollback is a three-artifact revert only. | Editable in this turn; implementation remains pending. |
| current-turn edit `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_surface_route.txt` | `active-design-packet-materialization` route owner | Carry every self-contained file-scope record and the exclusive future implementation surface. | `scope_file` records, forbidden paths/behaviors, implementation order, graph replacement gate | ADP-09, ADP-12, ADP-13, RF-01–RF-06 | Reverse edge: this design; consumer: unit-owned implementation request. | T1–T10 | V8–V12 plus dependency-header/format checks | No product/runtime mutation; route is hashed before request and is never overwritten by another unit. | Editable in this turn; generic route file is external and verify-only. |
| current-turn edit `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_request.txt` | `active-design-packet-materialization` request owner | Carry exact request clauses, self-contained file records, review gates, and validation route bound to the route hash. | `request_clause`, `scope_file`, predecessor CLI/failure/graph replacement fields | ADP-01–ADP-13, RF-01–RF-06 | Reverse edges: this design and unit route; consumer: one future implementation writer. | T1–T10 | V1–V12 plus dependency-header/format checks | No product/runtime mutation; request binds route bytes, design binds request bytes, and no other unit may replace it. | Editable in this turn; generic request file is external and verify-only. |
| verify-only `tools/agent_tools/check_design_doc_claims.py` | `knowledge_graph` predecessor owner after integration; no active-packet owner | Do not invoke, repair, or make the obsolete custom parser pass; graph source deletes/replaces its parser/fact semantics. | Obsolete `parse_manifest_edges`, `dependency_closure`, filesystem evidence expansion; future graph-owned `GraphClaimConsumer` only | ADP-05, RF-06 | Reverse edges: `graph_design_brief.md#check_design_doc_claims decision`, verified `predecessor_integration.knowledge_graph.json`; consumer after integration: graph-backed claim route, not this design repair. | T10 | V12 | No current mutation. `not_applicable` is permitted only after predecessor verification plus fresh graph status/context; before that state is pending and no fallback parser runs. | `pending_graph_integration`; excluded from commands and edit scope. |

### Non-authoritative verify-only dependency index

Authority classification for this entire table is
`non_authoritative_verify_only_index`. Every row and every cell, including an
owner, reason, trace, validation, disposition, or use of the word
"authoritative," is only a read-only dependency locator and carries no edit,
clause, reservation, precedence, validation, publication, or implementation
authority. The canonical active-packet owner reference is
[Implementation Source Packet](#implementation-source-packet), together with
the normative four-section reference model and the self-contained records in
File Scope and Individual Validation Mapping. An external surface's canonical
owner is resolved only from its dependency header, typed registry/config, or
normalized graph result named by that Source Packet. On any disagreement, the
canonical source owner wins and this design returns to review. Generated
artifacts, tests, current packet files, and the obsolete checker are already
covered by their complete authoritative records above.

| Exact verify-only path | Exact owner and reason | Trace and validation | Atomicity effect and disposition |
| --- | --- | --- | --- |
| `reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md` | `knowledge_graph` design owner; producer-time design input only | T9, T10; V10–V12 | Read-only; no copied transient SHA and no active-packet edit. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_review.md` | `knowledge_graph` review owner; same-SHA APPROVE input only | T9, T10; V10–V12 | Read-only; stale review fails before record publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/container_codex_home_design.md` | successor-container design owner; consumes the verified two-record set | T9; V10 | Read-only here; successor owner rebases stale S1/V0 values. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design_review_v1.md` | historical review owner; non-authoritative evidence | T10; V11 | Read-only hash evidence; cannot authorize source or publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design_review_v2.md` | historical review owner; non-authoritative evidence | T10; V11 | Read-only hash evidence; cannot authorize source or publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design_review_v3.md` | historical review owner; non-authoritative evidence | T10; V11 | Read-only hash evidence; cannot authorize source or publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design_review_v4.md` | historical review owner; non-authoritative evidence | T10; V11 | Read-only hash evidence; cannot authorize source or publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design_review_v5.md` | historical review owner; non-authoritative evidence | T10; V11 | Read-only hash evidence; cannot authorize source or publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design_review_v6.md` | historical review owner; non-authoritative evidence | T10; V11 | Read-only hash evidence; cannot authorize source or publication. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/user_request_contract.md` | external graph/routing unit; not active-packet clause authority | T10; V11 | Read-only recorded hash; excluded from read-before-edit and packet projection. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/schedule.md` | runtime schedule owner; operational output only | T10; V11 | Read-only recorded hash; excluded from authority and packet projection. |
| `ROOT_AGENTS.md` | root runtime owner; producer reverse-edge evidence | T5, T7; V5, V8 | Read-only; no runtime-root mutation in this unit. |
| `agents/README.md` | agent-runtime index owner; owner-location evidence | T7; V8 | Read-only; no publication effect. |
| `agents/COMMUNICATION_PROTOCOL.md` | context/source-packet protocol owner; packet boundary evidence | T1, T7; V2, V8 | Read-only; no active-packet schema inference. |
| `agents/canonical/CODEX_SUBAGENTS.md` | wave-plan owner; subagent lifecycle evidence | T3, T7; V3, V8 | Read-only; no operation-resolution edit. |
| `agents/task_catalog.yaml` | workflow/reviewer registry owner; authoritative typed registry | T1, T6; V1, V7 | Read-only parser input; invalid registry fails before staging. |
| `agents/templates/_partials/decision_approve_revise_escalate.md` | review-template partial owner; decision syntax evidence | T6, T7; V7, V8 | Read-only; authoritative parser consumes it without local duplication. |
| `agents/templates/_partials/findings_area_table.md` | review-template partial owner; findings layout evidence | T7; V8 | Read-only; no runtime publication. |
| `agents/templates/_partials/findings_required_change_table.md` | review-template partial owner; findings layout evidence | T7; V8 | Read-only; no runtime publication. |
| `agents/templates/closeout_gate.md` | closeout-template owner; waterfall downstream evidence | T6, T7; V7, V8 | Read-only; no active-packet implementation authority. |
| `agents/templates/schedule.md` | schedule-template owner; WAIT-1 ledger boundary | T10; V11 | Read-only; `Agent Wave Ledger` remains outside active-packet operation resolution. |
| `agents/skills/subagent-bootstrap.md` | canonical bootstrap-skill owner; verify `Standard Command` only | T7, T10; V8, V11 | Read-only; `Subagent Return Investigation` remains WAIT-1 v14-owned. |
| `.agents/skills/subagent-bootstrap/SKILL.md` | runtime bootstrap-skill owner; verify `Tool Commands` packet references only | T7, T10; V8, V11 | Read-only; `wait_agent`, `list_agents`, `send_message`, `interrupt_agent`, and close-operation instructions remain WAIT-1 v14-owned. |
| `documents/dependency-manifest-design.md` | dependency graph owner; authoritative normalized graph semantics | T2, T7; V2, V8 | Read-only result owner; no parser copied into AgentCanon packet logic. |
| `references/workflow/implementation-waterfall.md` | waterfall reference owner; reverse-edge evidence | T6, T7; V7, V8 | Read-only; no gate-local semantics. |
| `tools/README.md` | tool-index owner; source owner-location evidence | T7; V8 | Read-only; no publication effect. |
| `tools/bin/agent-canon` | command-wrapper owner; Markdown and graph command route | T7, T10; V8, V12 | Read-only executable; mandatory docs commands and pending graph commands only. |
| `tools/agent_tools/check_dependency_headers.py` | dependency-header checker owner | T7; V8 | Read-only validation command; no source rewrite. |
| `tools/agent_tools/check_dependency_header_format.sh` | dependency-header format checker owner | T7; V8 | Read-only validation command; no source rewrite. |
| `tools/agent_tools/check_dependency_graph.sh` | dependency graph build/check owner | T2, T7; V2, V8 | Read-only authoritative graph result; no local graph reconstruction. |
| `tools/agent_tools/check_convention_compliance.py` | convention checker owner | T7; V8 | Read-only validation command; no source rewrite. |
| `tools/agent_tools/dependency_manifest_records.py` | normalized dependency-record owner | T2; V2 | Read-only typed result; no active-packet schema edit. |
| `tools/agent_tools/runtime_log_archive_git.py` | immutable archive owner; snapshot/manifest/index/push implementation | T9; V10 | Read-only source; producer consumes its result and never reimplements archive writes. |
| `tools/agent_tools/check_agent_runtime_alignment.py` | runtime-alignment owner; direct public delegator consumer | T5; V5 | Read-only consumer; validates `create_run_bundle` behavior. |
| `tools/agent_tools/smoke_test_research_perspective_pack.py` | research-pack smoke owner; direct public delegator consumer | T5; V5 | Read-only consumer; validates public result only. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/implementation_request.txt` | external graph/routing unit owner | T10; V11 | Read-only hash-bound external file; never reused or overwritten. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/implementation_surface_route.txt` | external graph/routing unit owner | T10; V11 | Read-only hash-bound external file; never reused or overwritten. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_reconciliation_v1.md` | WAIT-1 owner; operation-resolution scope evidence | T10; V11 | Read-only hash-bound input; no active-packet authority. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_design.md` | WAIT-1 owner; blocked v17 candidate evidence | T10; V11 | Read-only hash-bound input; no implementation authority. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_detailed_design_review_v14.md` | WAIT-1 review owner; historical REVISE evidence | T10; V11 | Read-only hash-bound input; no implementation authority. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_detailed_design_review_v16.md` | WAIT-1 review owner; historical ESCALATE evidence | T10; V11 | Read-only hash-bound input; no implementation authority. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_review_v1.md` | WAIT-1 review owner; historical REVISE evidence | T10; V11 | Read-only hash-bound input; no implementation authority. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/routing_llama_design_brief.md` | routing/Llama successor owner; post-integration reservation evidence | T10; V11 | Read-only hash-bound input; activates only after required predecessors. |
| `reports/agents/20260712-090608-context-packettool-skill-routing/routing_llama_detailed_design_review_v15.md` | routing/Llama review owner; durable independent approval identity for the final successor design | T10; V11 | Read-only hash-bound input; SHA-256 `f428cf186f2e7dacb1cf99203eee4c0f427eefc7560da7830a2fbd241e5671d2`; 160 lines; `review_status=approved`; `decision=APPROVE`; `implementation_authorized=yes`; approves brief SHA `ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7` at 854 lines and cannot authorize active-packet publication or waive predecessor gates. |

Forbidden scope is `.github/workflows/**`, all edits to the seven hash-bound
external overlap artifacts, all unlisted source/config/test/template/doc/skill
paths, and all edits to the two generic packet files. No fixed workflow
assumption may be introduced through docs or validation.

## Implementation Source Packet

The current implementation source packet consists of these exact artifacts:

1. this design;
2. `active_design_packet_implementation_surface_route.txt`, SHA-256
   `15164e6d67da7603cd7968bf7725397d7944f7487f062b909de1d8092de18d2b`,
   218 lines;
3. `active_design_packet_implementation_request.txt`, SHA-256
   `6538c0e508a38f2914c895d8fe8bce6ce8d30bfbee4b60c84f9c6d11d668676c`,
   220 lines; its header and metadata bind the route SHA and line count;
4. pre-implementation
   `active_design_packet_contract_repair_detailed_design_review.md`, owned by
   `role:design_reviewer`, and
   `active_design_packet_contract_repair_document_flow_review.md`, owned by
   `role:document_flow_reviewer`; each must record `approve`, this exact design
   path, and the same final design SHA before implementation authorization;
5. post-implementation
   `active_design_packet_contract_repair_change_review.md`, owned by
   `role:change_reviewer`, and
   `active_design_packet_contract_repair_final_review.md`, owned by
   `role:final_reviewer`; each records `approve` against the integrated diff
   and V1-V12 evidence;
6. conditional `active_design_packet_contract_repair_test_plan.md`, which is
   absent and not required. It may enter only after the complete source
   mechanism exists, concrete validation evidence identifies one unresolved
   public oracle, and this design is revised to name that evidence, oracle,
   owner, path, and validation. File counts, line counts, internal-helper
   changes, and planned predecessor coverage cannot activate it;
7. public-oracle source evidence in
   `tests/agent_tools/test_agent_team_templates.py`,
   `tests/agent_tools/test_task_start_and_close.py`, and
   `tests/agent_tools/test_waterfall_gate_check.py`; these are evidence paths,
   not mandatory new-test targets;
8. the exact current symbols and sections listed in `File Scope`;
9. the dependency graph related-surface result and targeted validation commands
   listed below;
10. post-merge outputs
    `predecessor_integration.knowledge_graph.json` and
    `predecessor_integration.active_design_packet_materialization.json`, each
    owned by its `unit_id` and generated by a separate invocation of the same
    generic GitHub-publish action against the same merged source PR; their one
    archive snapshot, sibling manifest, snapshot ID, individual payload hashes,
    complete-file hashes, and common integrated source OID become two explicit
    predecessor entries in the successor container's Source Packet.
11. downstream live verify-only consumer `container_codex_home_design.md`;
    its owner applies the exact schema/ID/filename/set-API/observed-OID/HEAD-
    ancestry replacements in `Successor container reconciliation` whenever
    stale S1 values remain, and this unit never copies its transient SHA,
    edits it, or treats its S1 as authority.

The two pre-implementation review artifacts are currently unmaterialized
because `review_status=pending`; their paths and owners are nevertheless closed
here and in the request packet. Approval is the mechanical same-SHA result, not
a future scope or routing choice. The post-implementation and conditional test-
plan names are likewise exclusive to this responsibility unit and cannot be
reused or overwritten by another design unit.

Both predecessor records are currently absent because this responsibility has
not been implemented or merged. Absence is expected pre-implementation state,
not a future scope decision or blocker. In addition, intake graph-review
evidence targeted
`5febd536a44fe5d3f1e7fe5ffecc028c8e3f0e2658182790393fb20728449f87`;
the graph owner must provide a review whose target equals the producer-time
design hash before its generic invocation can succeed. Mutable graph-owner
working bytes are not copied as packet authority. That required evidence
replacement is external to this three-file repair and introduces no schema
choice. The exact unit-ID
grammar, filename derivation, fields, hashes, archive route, individual
verifier, set verifier, and common-OID rule are fixed here. After merge, the
successor proceeds only from both explicit archived locators and successful
read-only V10 result; it may not substitute one record, an aggregate record,
the current run manifest, an active pointer, PR prose, chat, or schedule.

The following current-run artifacts are explicitly outside this Source Packet:
`user_request_contract.md`, `schedule.md`, the two generic
`implementation_*.txt` files, the six versioned active-packet design reviews,
and the seven productive-wait/routing overlap files. Their hashes and
dispositions are in Design Status. The overlap files are read only at the
explicit precedence step below; all others are not read-before-edit inputs.
None binds an active-packet request clause, owner, dependency, output,
reviewer, or implementation route.

The read-before-edit order is:

1. request clauses and Abstract Design Frame in this document;
2. the route packet and request packet, verifying both hashes;
3. the seven external overlap files, verifying their hashes, status, exact
   reservations, and fixed predecessor order only;
4. both approving pre-implementation review artifacts, verifying the same
   design path and SHA;
5. `agent_team.py` exact current symbols and its direct config/template owners;
6. producer and waterfall call sites;
7. canonical workflow/docs/skills/templates named in the edit table;
8. the historical test symbols only as read-only public-behavior evidence;
   no test path is editable unless post-source validation exposes a concrete
   conflicting assertion and a revised design authorizes that exact edit;
9. the GitHub-publish, PR-processing, placement, and archive owner surfaces for
   the fixed generic per-unit producer and two-unit verifier route;
10. at post-merge production only, the exact graph design/review paths;
    compute both hashes then and require same-path/same-SHA APPROVE without a
    copied pre-implementation graph hash;
11. the container design path, owner boundary, and exact successor rebase
    contract only; no container hash or edit is authorized;
12. verify-only reverse edges required by the changed path.

The packet's `allowed_edit_path`, `allowed_verify_path`, `forbidden_path`,
dependency expansion, implementation order, review gate, and validation route
are closed values. There is no unresolved parent choice. Design approval is a
mechanical gate on one design SHA, not permission to select another scope.
No other design unit may reuse, truncate, or overwrite either active-packet-
specific source-packet filename.

The implementation handoff selects one Luna worker for the complete
owner-preserving responsibility graph. The graph predecessor, current graph-
owned dirty semantic intent, active-packet materialization, affected
source/config, skills/docs, generated views, and checker disposition are
ordered nodes inside Luna's work, not file/finding/test slices. Luna uses each
node's approved path authority and returns one integrated validation packet.
Only an actual concurrent write conflict or unresolved predecessor permits a
split; an unresolved predecessor pauses the complete graph and does not
authorize a smaller substitute.

## Detailed Design Side-Effect Map

| ID | Request clauses | Decision | Reuse precedent | Downstream surfaces | Owner stage | Explicit review gate | Validation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | ADP-01, ADP-03, ADP-05, ADP-07 | one value, one strict decoder, one precedence resolver | `json.loads`, `load_team_config`, `_as_object_mapping`, current workflow/config selection | config, CLI input, workflow record, persisted manifest | Gate 5 designer fixes schema; Gate 8 `agent_team.py` writer implements | detailed-design approval, then change review | V1, V2 |
| S2 | ADP-02, ADP-06, ADP-07, ADP-11 | `create_run_bundle` is the sole producer delegator | current direct `create_run_bundle` callers and `resolve_report_root` | task-start, bootstrap, doc-start, smoke, alignment | Gate 8 `agent_team.py` writer integrates every caller | change review and final review | V5 |
| S3 | ADP-01, ADP-02, ADP-03, ADP-05 | every projector consumes the same resolved value and prior projection | current `iter_artifacts`, `render_template`, `expand_template_partials`, role/output registries | role packets, prompt packets, templates, verification, authority, wave ledger, manifest | Gate 5 defines projection equality; Gate 8 source owner implements | detailed-design approval and change review | V3, V6 |
| S4 | ADP-02, ADP-11 | render all, verify staging, kernel no-replace publish, pointer-last activation | `resolve_report_bundle_artifact_path`, `write_hash_baseline` naming, current monitoring transforms, POSIX `flock`/`renameat2` results | report directory, authority baseline, monitoring, `.active_run`, `.active_run.sha256` | Gate 8 materializer and task-authority/monitor seams | detailed-design approval, change review, final review | V4 |
| S5 | ADP-02, ADP-03, ADP-04, ADP-05 | one manifest loader and one semantic validator; gate-local packet semantics are deleted | `yaml.safe_load`, `section_has_content`, `has_approve_decision`, artifact containment resolver | `waterfall_gate_check.py`; design, document-flow, implementation gates | Gate 6/7 review semantics and Gate 8 consumer source; follow S5 → T6 → V7 | detailed-design and document-flow approval before source; change review after source | V7 |
| S6 | ADP-03, ADP-06, ADP-07 | explicit packet intent and typed failures stay public | current argparse option, run-manifest output, CLI machine-readable output helpers | `--active-design-packet`, `run.active_design_packet`, CLI outputs and exit codes | Gate 0 bootstrap producers and Gate 8 consumer | change review and final review | V5, V7 |
| S7 | ADP-03, ADP-08, ADP-09, ADP-12 | structural instructions and reverse edges state the one owner and reference model | current dependency headers, template renderer, Markdown heading index, canonical workflow sections | five templates, template README, canonical docs/workflow, six skill surfaces, paired headers | Gate 5-7 doc/skill owners updated in the same Gate 8 unit | document-flow and detailed-design approval, then final review | V8 |
| S8 | ADP-08, ADP-09, ADP-10, ADP-12, RF-05 | test files are verify-only at authorization; source is completed first, a conflicting stale public assertion requires a design revision before its exact test edit, and a new test requires a revised design naming a concrete unresolved public oracle | historical `git show 9ba4bba5` inventory and existing public CLI/bundle/gate evidence | verify-only historical and public test paths; no currently authorized test edit | Gate 8 source first; stop and revise this design only if post-source evidence meets the exact stale-assertion or unresolved-oracle rule | change review verifies source-first evidence and the absence of count-based or unconditional test work | V9 |
| S9 | ADP-05, ADP-09, ADP-13 | one generic schema and filename function produce independent `knowledge_graph` and `active_design_packet_materialization` records; individual verification proves record/review/PR/ancestry, while the in-memory set verifier rejects duplicate/missing/unexpected units and requires one byte-equal merged source OID without an aggregate artifact; the container owner deterministically replaces its stale schema/IDs/filenames/manual comparison and retains only common-integrated-OID→HEAD readiness | `verify_remote`, `parse_review_identity`, `gh pr view` result, Git process results, `archive-agent-report` snapshot/manifest/index | GitHub publish tool/docs/test, PR workflow and canonical/runtime skill, placement/archive docs, both unit inputs, current Source Packet, successor Source Packets, verify-only `container_codex_home_design.md` | source first in Gate 8; graph owner supplies its same-SHA review; canonical PR-processing producer runs twice after the shared merge; container owner rebases its S1/V0 after integration; successor intake is read-only | each unit's same-SHA detailed-design gate plus change/final review before merge; V10 after merge; container review consumes the final contract | V10 |
| S10 | ADP-04, ADP-09, ADP-13 | seven hash-bound external overlap inputs are verify-only; one Luna worker executes the graph-owned dirty semantic intent, active packet, affected source/config, skills/docs, generated views, and checker cleanup as one owner-preserving responsibility graph in dependency order; both required predecessor records for the merged source OID integrate first, optional approved WAIT-1 second, routing/Llama last; split occurs only for an actual concurrent write conflict or unresolved predecessor | current graph-owned dirty paths, productive-wait reconciliation/design/reviews, and routing/Llama predecessor table | graph predecessor paths under graph authority, `agent_team.py`, workflow monitor, task-start/bootstrap, manifest/docs/skill/generated-view sections, and post-merge record/graph evidence | one Luna writer preserves each node's path authority, lands the integrated source PR, and hands off one V1–V12 evidence set; later units consume both archived records and narrower reservations | equal-SHA reviews plus change/final review check owner boundaries, hashes, reservations, and one-worker handoff; successor verifies both records and common OID | V11, V12 |

No item delegates schema interpretation, path selection, or test count to a
worker. A finding against any side effect returns to this same responsibility
unit.

## Design-To-Implementation Trace

| Trace | Clauses | Design decision | Reuse precedent | Implementation projection | Side effects | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | ADP-01, ADP-03, ADP-05, ADP-07 | normative type, config record, cardinality, join algorithms | current team-config JSON loader and workflow-family selection | `agent_team.py` decoder/resolver and `agents_config.json` | S1 | V1, V2 |
| T2 | ADP-03, ADP-04, ADP-05 | exact root/symbol/section/dependency/owner/reviewer/clause/output resolution | `resolve_workspace_document_path`, artifact resolver, Python AST, Markdown heading index, dependency TSV | shared reference context and validator | S1, S3 | V2, V6 |
| T3 | ADP-02, ADP-03, ADP-06 | exact projector signatures and build order | current artifact registry, role packet, template, authority, and workflow-monitor functions | role/prompt/template/verification/authority/wave/manifest projections | S3 | V3, V6 |
| T4 | ADP-02, ADP-11 | in-memory set, staging verification, no-replace target publish, pointer-last rollback | current path containment/baseline naming plus kernel and filesystem results | materializer, task authority, workflow monitor | S4 | V4 |
| T5 | ADP-02, ADP-06, ADP-07, ADP-11 | one-call producer result and typed error mapping | current five direct caller paths and machine-readable CLI output keys | task-start, bootstrap, doc-start; smoke/alignment verification | S2, S6 | V5 |
| T6 | ADP-02, ADP-03, ADP-04, ADP-05 | exact shared loader/validator call path; delete gate-local semantics | `yaml.safe_load` and current report-artifact structural/review-decision results | waterfall source and review templates | S5, S6 | V7 |
| T7 | ADP-03, ADP-08, ADP-09, ADP-12 | exact reader-facing sections and paired owner edges | existing dependency headers, canonical sections, template/runtime skill views | each doc/template/skill row in File Scope | S7 | V8 |
| T8 | ADP-08, ADP-09, ADP-10, ADP-12, RF-05 | keep every test path verify-only until source-complete validation identifies a concrete stale public assertion; authorize a new oracle only through a revised design with evidence | historical `git show` inventory and current public property observations | verify-only test paths and a design-revision gate; no current test edit | S8 | V9 |
| T9 | ADP-05, ADP-09, ADP-13 | generic exact record fields and payload hash, unit-ID grammar and filename derivation, per-unit merged-PR producer, immutable two-record archive path, individual verifier, duplicate/exact-set/common-OID verifier, two ancestry checks per record, and exact stale-container S1/V0 replacement with common-OID→HEAD readiness | verified GitHub metadata, authoritative review identity result, Git object/process results, existing run archive, container design's explicit owner-deference | `github_publish.py`, report parser, PR workflow/skills/docs, archive/placement docs, graph and active design/review inputs, public regression, verify-only container successor design; no manifest consumer or aggregate schema | S9 | V10 |
| T10 | ADP-04, ADP-09, ADP-13 | exact external hashes, statuses, shared-symbol reservations, two-record predecessor requirement, and one-Luna owner-preserving dependency order; no file/finding/test/review slice is valid | current graph-owned dirty state, seven external overlap artifacts, routing brief's active-packet predecessor declaration, and durable v15 identity `review_status=approved`, `decision=APPROVE`, `implementation_authorized=yes` | one responsibility-graph handoff, graph paths under graph authority, frozen active-packet blocks, explicit predecessor set, and post-merge graph validation | S10 | V11, V12 |

Every edit row cites at least one trace and validation ID. The trace is by
responsibility decision, so the implementation remains one unit rather than a
file or test partition.

## One-Writer Implementation Sequence

The selected implementation worker is one Luna worker. Luna receives the
`knowledge_graph` predecessor node, its existing dirty semantic intent, this
active-design-packet node, affected source/config, skills/docs, generated
views, and graph-owned obsolete-checker cleanup as one responsibility graph.
Each path retains the owner and approved packet recorded in File Scope; this
orchestration rule does not transfer graph path authority into the active-
packet design. Luna executes the graph internally in dependency order and
returns one integrated diff and one validation handoff. File size, finding
count, test location, review area, and a generic safety preference never create
a slice or another writer. A split is permitted only for an actual concurrent
write conflict or an unresolved predecessor; either condition pauses the
affected responsibility graph for coordination rather than creating a file-
sized substitute.

Luna performs this sequence without handing independent files to other
writers:

1. Verify both unit packet hashes and the owner/path records, preserve every
   graph-owned dirty path named in the route, and establish the graph-before-
   active dependency order. Execute approved graph-owned source/checker cleanup
   first, then the active-packet source below, in one worker and one source PR.
   If the graph predecessor is unresolved, stop the complete graph without
   starting a narrower active-packet or documentation slice. Its integration
   record remains post-merge evidence and therefore does not become a pre-
   source gate.
2. Complete the active-packet production-source mechanism. Within this source
   step, update `agent_team.py` before its dependents: types, decoder/resolver,
   reference context, shared validation, projectors, result, call graph,
   staging/publication, and persisted-manifest consumer. Then update the task-
   authority and workflow-monitor pure seams, task-start, bootstrap, doc-start,
   waterfall consumer, authoritative review-identity parser, generic GitHub
   post-merge per-unit producer plus individual/set verifiers, and the exact
   normative `agents_config.json` record;
   verify smoke and alignment callers. Production source and normative config
   are one first step. Do not enter a test file before this complete path
   exists.
3. Run the source-targeted validation before opening any test for mutation.
   Every test path in this packet is verify-only. If one existing assertion
   demonstrably conflicts with the approved public contract, stop, record the
   exact failing assertion and public semantic, and revise this design before
   authorizing that one stale assertion edit. If a concrete public oracle
   remains unresolved after static checks and direct public behavior evidence,
   stop and revise this design before activating test design or naming a new
   test. The absence of predecessor tests is not itself an oracle gap.
4. Update templates, template README, canonical docs/workflows, archive and
   GitHub-publish docs, canonical skills, runtime skill views, and every paired
   dependency header together.
5. Run V1 through V11 before merge, merge the one source PR, produce and verify
   both predecessor records at the merged source OID, then run V12. Change and
   final review receive the one Luna diff, one responsibility-graph trace, and
   one V1–V12 handoff; generated views and checker disposition are not separate
   review slices.

The writer may not preserve an old packet owner beside the new owner, add a
temporary caller parser, publish one artifact at a time, or weaken a public
oracle to make the refactor pass.

## Targeted Validation

### Validation map

| ID | Contract | Exact observable result |
| --- | --- | --- |
| V1 | decoder and precedence | explicit, workflow, and config records decode to equal value content; precedence is explicit > workflow > config; unknown/duplicate/partial input is rejected once |
| V2 | reference model | all four records satisfy cardinality/join rules; every clause/owner/source/dependency/output/reviewer ref resolves through its authoritative index; forbidden prose authority is rejected |
| V3 | projector parity | role packets, prompt packets, wave/monitor bytes, authority, verification, artifact list, and manifest all derive from the same value and exact paths |
| V4 | atomic publication | first lock acquisition, released-lock reuse, proven crash-stale reuse, live contention, foreign identity/payload rejection, process crash, identity-safe release, and cleanup follow the one persistent-lock lifecycle; validate/render/stage/collision/pointer failures expose no partial target or pointer advance; bookkeeping rollback compares the exact published identity/mode/size/hash before restore, never clobbers a changed path, preserves unknown state, and reports restore/release failure distinctly |
| V5 | producer public parity | task-start and bootstrap accept the same explicit packet and return equivalent public packet/output properties; doc-start uses `.created_files`; smoke/alignment remain valid |
| V6 | manifest projection | persisted `run.active_design_packet`, role outputs, prompt packet, and created-file paths equal the in-memory value and output set |
| V7 | waterfall shared-consumer path | design/document-flow/implementation gates call `load_materialized_active_design_packet` then `validate_materialized_active_design_packet`; local packet symbols are absent; sibling/history prose is ignored; shared violations map unchanged to CLI blocker ownership |
| V8 | docs/templates/skills/reverse edges | every individually mapped section states the single owner/reference model; canonical/runtime skills agree; dependency headers and related surfaces are paired |
| V9 | source-first test policy | no test path is an unconditional edit and no test or line count is an acceptance measure; source completes before test inspection; an existing test changes only after a concrete conflicting public assertion is recorded and this design is revised for that exact edit; a new test enters only after evidence of an unresolved public oracle and a design revision naming it |
| V10 | predecessor integration | after the shared merge, generic production yields exactly `predecessor_integration.knowledge_graph.json` and `predecessor_integration.active_design_packet_materialization.json`, each with the same thirteen-field schema, valid twelve-field payload `artifact_sha256`, valid archive complete-file SHA, exact unit-derived filename, matching design/review bytes, and same-path/same-SHA detailed-design APPROVE; both PR identities are merged/main-bound and `integrated_source_oid` strings are byte-equal; each record passes integrated→observed and observed→fixed `refs/remotes/origin/main` `git merge-base --is-ancestor`; collision never overwrites; duplicate, missing, unexpected, or unequal-OID sets fail atomically; successor verification exposes no remote/ref option, performs no write/fetch, creates no aggregate, and uses no manifest/chat/schedule/document-flow input; the live container path and owner boundary are verify-only here, and its next owner revision replaces any stale S1/V0 values with the set API, drops observed-OID equality/manual pair comparison, and requires only common-integrated-OID→HEAD after successful set verification |
| V11 | external overlap closure | all seven external hashes and line identities match; productive-wait remains non-authoritative until separately approved; routing/Llama brief SHA `ba97d93524b70982590c27ada977e38f491a4e93089f063c396e5ff1d903d4d7` has 854 lines and its durable v15 review SHA `f428cf186f2e7dacb1cf99203eee4c0f427eefc7560da7830a2fbd241e5671d2` has 160 lines with `review_status=approved`, `decision=APPROVE`, and `implementation_authorized=yes`; the brief observes this unit as predecessor; static symbol/section comparison shows active packet owns packet blocks/pure renderer/producer activation while WAIT/routing own only the later reservations listed in the precedence section; integration order is verified `knowledge_graph` plus `active_design_packet_materialization` records at one OID → approved WAIT-1 if any → routing/Llama, with no concurrent edit, aggregate, or schema bridge |
| V12 | graph-owned static replacement | while the `knowledge_graph` predecessor record is absent or unverified, state is `pending_graph_integration` and the obsolete custom checker is neither invoked nor repaired; after individual predecessor verification succeeds, graph `status` and graph `context` both return fresh evidence for this exact reviewed design path/SHA and the evidence binding below is complete, at which point the obsolete checker alone becomes `not_applicable` |

### Current design-artifact commands

Run in this order on the three design-owned files:

```bash
tools/bin/agent-canon docs format \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md

tools/bin/agent-canon docs check \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md

python3 tools/agent_tools/check_dependency_headers.py \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_request.txt \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_surface_route.txt

bash tools/agent_tools/check_dependency_header_format.sh --require-header \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_request.txt \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_surface_route.txt

bash tools/agent_tools/check_dependency_graph.sh --root . \
  --cycle-report-only --list-related \
  --focus reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  --focus reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_request.txt \
  --focus reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_surface_route.txt

python3 tools/agent_tools/check_convention_compliance.py

python3 tools/agent_tools/prose_reasoning_graph.py check-document \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  --out-dir <task-local-artifact-dir> --profile writing \
  --stats-out <task-local-stats.json>

git diff --check -- \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_request.txt \
  reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_implementation_surface_route.txt
```

After formatting, compute SHA-256 and line count once. Both design reviewers
receive those exact bytes. A revision repeats the full command order and
creates a new SHA.

### Graph-predecessor replacement static validation

`check_design_doc_claims_state=pending_graph_integration` is the current and
only valid state. This unit does not invoke, patch, wrap, emulate, or require a
pass from `tools/agent_tools/check_design_doc_claims.py`. The `knowledge_graph`
predecessor deletes/replaces that custom parser with its graph-owned
`GraphClaimConsumer`; no active-packet fallback parser exists.

V12 changes the obsolete checker's disposition to `not_applicable` only after
all three read-only commands below succeed in this order:

```bash
python3 tools/agent_tools/github_publish.py verify-predecessor-integration \
  --record reports/agents/20260712-090608-context-packettool-skill-routing/predecessor_integration.knowledge_graph.json \
  --archive-manifest <same-snapshot>/archive_manifest.json \
  --expected-unit-id knowledge_graph

tools/bin/agent-canon graph status \
  --root <parent-root> \
  --profile default \
  --format json

tools/bin/agent-canon graph context \
  --root <parent-root> \
  --path reports/agents/20260712-090608-context-packettool-skill-routing/active_design_packet_contract_repair_design.md \
  --profile default \
  --format json
```

The individual predecessor result must be `verified=true` for
`unit_id=knowledge_graph`. The graph status result must report `status=fresh`
and a verified `GraphIntegrationRecord`. The graph context result must report
`status=fresh`, the exact repository-relative design path above, and the
reviewed design SHA. The V12 evidence object is exact and closed:

```text
reviewed_design_path
reviewed_design_sha256
knowledge_graph_record_path
knowledge_graph_record_artifact_sha256
knowledge_graph_archive_manifest_path
knowledge_graph_archive_complete_file_sha256
knowledge_graph_integrated_source_oid
graph_integration_record
graph_fingerprint
graph_status_response_sha256
graph_context_response_sha256
command_argv
command_exit_status
```

`reviewed_design_sha256` must equal the SHA in both unversioned APPROVE reviews;
the predecessor record and graph integration record must identify the reviewed
source OID; response hashes cover each command's canonical JSON stdout plus LF;
and every recorded exit status is zero. A missing/unverified record, stale
status/context, SHA/OID/path disagreement, or incomplete evidence keeps
`pending_graph_integration`, emits no partial V12 success, and cannot be
replaced by the obsolete checker. The mandatory Markdown formatter/checker and
applicable dependency/convention checks remain required independently of this
pending graph gate.

### Targeted implementation commands

The implementation writer runs repository-supported equivalents of these
targeted commands; no named CI workflow is assumed:

```bash
python3 -m pyright \
  tools/agent_tools/agent_team.py \
  tools/agent_tools/task_start.py \
  tools/agent_tools/bootstrap_agent_run.py \
  tools/agent_tools/doc_start.py \
  tools/agent_tools/waterfall_gate_check.py \
  tools/agent_tools/task_authority.py \
  tools/agent_tools/workflow_monitor.py \
  tools/agent_tools/report_artifact_checks.py \
  tools/agent_tools/github_publish.py

python3 -m ruff check \
  tools/agent_tools/agent_team.py \
  tools/agent_tools/task_start.py \
  tools/agent_tools/bootstrap_agent_run.py \
  tools/agent_tools/doc_start.py \
  tools/agent_tools/waterfall_gate_check.py \
  tools/agent_tools/task_authority.py \
  tools/agent_tools/workflow_monitor.py \
  tools/agent_tools/report_artifact_checks.py \
  tools/agent_tools/github_publish.py

python3 -m pytest -q \
  tests/agent_tools/test_agent_team_templates.py \
  tests/agent_tools/test_task_start_and_close.py \
  tests/agent_tools/test_waterfall_gate_check.py \
  tests/agent_tools/test_doc_start.py \
  tests/agent_tools/test_workflow_monitor.py \
  tests/agent_tools/test_task_authority.py \
  tests/agent_tools/test_check_agent_runtime_alignment.py \
  tests/agent_tools/test_github_publish.py \
  tests/agent_tools/test_runtime_log_archive_git.py

python3 tools/agent_tools/check_agent_runtime_alignment.py

python3 tools/agent_tools/check_dependency_headers.py --changed
bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header
bash tools/agent_tools/check_dependency_graph.sh --changed --list-related
tools/bin/agent-canon docs format
tools/bin/agent-canon docs check
git diff --check
```

If the repository wrapper selects different installed commands for pyright,
ruff, or tests, the wrapper command is authoritative while the source file set
and V1-V12 public/static oracles remain fixed. The pytest command observes the
existing suite after source completion; it authorizes no test edit, new test,
predecessor-oracle requirement, or count target. Any concrete stale assertion
or unresolved public oracle returns to the design-revision rule in V9.

After the shared source PR merge, the PR-processing owner runs the exact two
producer commands, one archive/push, two individual verifiers, and one set
verifier from `Durable Post-Merge Predecessor Integration Record`. V10 records
both pairs of literal `git merge-base --is-ancestor` argv vectors and exit
statuses, the archive destination/snapshot ID, both payload
`artifact_sha256` values, both archive-manifest complete-file SHAs, the common
`integrated_source_oid`, and `predecessor_integration=complete`. The set result
is not serialized. This post-merge operation is not replaced by a pre-merge
fixture result.

The later container V0 consumes that common OID and requires exit 0 from this
one additional literal argv:

```bash
git merge-base --is-ancestor <common_integrated_source_oid> HEAD
```

It does not compare the two observed-main OIDs or rerun record parsing.

V11 runs before source editing and again in change review:

```bash
sha256sum \
  reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_reconciliation_v1.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_design.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_detailed_design_review_v14.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_detailed_design_review_v16.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/productive_wait_contract_review_v1.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/routing_llama_design_brief.md \
  reports/agents/20260712-090608-context-packettool-skill-routing/routing_llama_detailed_design_review_v15.md

git grep -n \
  -e 'run.active_design_packet' \
  -e 'active_design_packet_reference_projection' \
  -e 'build_run_start_monitoring_entries' \
  -e 'render_monitoring_artifacts' \
  -e 'mid_task_classification' \
  -e 'validate_mid_task_route_fields' \
  -e 'normalize_mid_task_user_input' \
  -e 'append_mid_task_schedule_rows' \
  -- tools/agent_tools/agent_team.py \
     tools/agent_tools/workflow_monitor.py \
     tools/agent_tools/task_start.py \
     tools/agent_tools/bootstrap_agent_run.py
```

The expected hashes are the six Design Status values. Review maps every hit to
the reservations in `External overlap inputs, precedence, and integration
order`; an unclassified or cross-owned hit fails V11. This is a symbol/section
ownership check, not a file-level split.

## Evidence And Assumption Ledger

- Evidence sources: `tools/agent_tools/agent_team.py`,
  `tools/agent_tools/task_start.py`,
  `tools/agent_tools/bootstrap_agent_run.py`,
  `tools/agent_tools/doc_start.py`,
  `tools/agent_tools/waterfall_gate_check.py`,
  `tools/agent_tools/task_authority.py`,
  `tools/agent_tools/workflow_monitor.py`,
  `tools/agent_tools/report_artifact_checks.py`,
  `tools/agent_tools/github_publish.py`,
  `tools/agent_tools/runtime_log_archive_git.py`,
  `agents/agents_config.json`,
  `agents/task_catalog.yaml`, `agents/canonical/CLI_ENTRYPOINTS.md`,
  `agents/canonical/CODEX_WORKFLOW.md`,
  `agents/workflows/implementation-waterfall-workflow.md`,
  `agents/workflows/agent-canon-pr-workflow.md`,
  `documents/dependency-manifest-design.md`,
  `documents/runtime-log-archive.md`, and the two unit-owned packet paths
  recorded in Design Status.
- Assumptions: normalization means only exact path/ID canonicalization defined
  in `Reference Grammar and Resolution Algorithms`; target publication uses
  the capability-checked kernel no-replace result while the canonical writer
  lock serializes canonical producers; no prose normalization or inferred
  standard form is permitted.
- Parent-doc alignment: `agents/canonical/CODEX_WORKFLOW.md` owns design
  integrity, `agents/workflows/implementation-waterfall-workflow.md` owns gate
  order, and `documents/dependency-manifest-design.md` owns graph evidence.
- Refactor handoff: one Luna worker receives both exclusive packet artifacts,
  the graph-owned dirty-intent records, and the `File Scope and Individual
  Validation Mapping`; no file/finding/test/review partition is authorized
  absent an actual concurrent write conflict or unresolved predecessor.

| Claim/decision | Evidence or governing source | Assumption status |
| --- | --- | --- |
| current source has two packet types and duplicated gate parsing | exact symbols in `agent_team.py` and `waterfall_gate_check.py` | observed |
| producers separately resolve, create, write pointer/baseline, and append monitoring | current `task_start.py#main` and `bootstrap_agent_run.py#main` | observed |
| all direct `create_run_bundle` callers are bounded | `git grep` hits in agent_team tests, task-start, bootstrap, doc-start, smoke, alignment | observed |
| historical tests added 1,110 lines | `git show --numstat 9ba4bba5` | observed |
| PR #373 is merged and ancestral | merge commit metadata and successful `merge-base --is-ancestor` | observed |
| generic packet files belong to another unit | their current content, hashes, and user collision clarification | governing request evidence |
| WAIT-1 v14 owns only four operation-resolution capabilities | `productive_wait_contract_reconciliation_v1.md` plus user repair packet | governing external scope |
| one standard record and one value are sufficient | this Abstract Design Frame and one-unit requirement | design decision |
| kernel `renameat2(RENAME_NOREPLACE)` is the sole target publication primitive | libc/kernel capability result and the no-overwrite public contract | explicit design decision; unavailable or cross-device capability is typed failure |
| review decision parsing remains externally owned | `report_artifact_checks.has_approve_decision` | reuse decision |
| dependency membership consumes graph TSV | `dependency-manifest-design.md` machine-readable graph contract | reuse decision |
| durable predecessor placement is run-local then immutable archive snapshot | `ARTIFACT_PLACEMENT.md`, `runtime-log-archive.md`, and `result-artifact-writeout` output contract | reuse decision |
| source PR integration requires two explicit ancestry relations | merged PR metadata plus exact `git merge-base --is-ancestor` process results | explicit design decision |
| current `user_request_contract.md`, `schedule.md`, generic packets, and six versioned reviews are not authority | recorded hashes, file ownership/content, and current repair clauses | observed and governing request evidence |
| productive-wait and routing/Llama overlap cannot run concurrently with this unit | seven recorded hashes/statuses, routing brief `P0-active-packet` predecessor declaration, durable v15 `review_status=approved` / `decision=APPROVE` / `implementation_authorized=yes` identity, and exact shared-symbol reservations | observed external evidence plus fixed integration decision |

No unsupported parser or workflow claim is inferred from prose. If an
authoritative tool changes its result contract, this unit returns to design
instead of copying the old result shape locally.

## Review and Handoff

`review_status=pending`. After the formatter and static checks pass, compute
the final SHA and hand the exact bytes independently to
`detailed_design_reviewer` and `document_flow_reviewer`. The detailed-design
review covers implementability of the exact types, JSON record,
reference algorithms, projector signatures, call order, waterfall API, atomic
failure behavior, deletion list, scope classification, predecessor producer /
verifier/archive contract, external-overlap order, graph replacement state,
and V1-V12 mapping. The document-flow review covers
definition before use, contiguous S5/T6/V7 clarity, the one-writer reading of
the scope tables, predecessor-record placement, and readability of the current
packet hashes.

An approving review does not alter the allowed paths or introduce another
packet. A revise decision edits these same three design-owned files, reruns the
same checks, records new packet/design hashes in one-way order, and returns the
new design bytes to both reviews. Implementation begins only after both reviews
approve one design SHA; no stale PR or packet evidence is a blocker because it
has been replaced or classified here.
