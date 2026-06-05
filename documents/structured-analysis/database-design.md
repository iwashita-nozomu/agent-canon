<!--
@dependency-start
responsibility Defines SQLite database design for structured prose, report, and dependency analysis.
upstream design README.md structured analysis package index
upstream design ../prose-reasoning-graph/dsl-spec.md prose graph DSL and projection contract
upstream design ../dependency-manifest-design.md dependency manifest DSL and validation model
upstream implementation ../../tools/agent_tools/prose_reasoning_graph.py current prose graph SQLite implementation
upstream implementation ../../rust/agent-canon/src/structured_analysis.rs Rust structured-analysis CLI implementation
upstream implementation ../../tools/agent_tools/check_dependency_graph.sh emits dependency manifest graph artifacts
downstream design dependency-header-analysis.md maps dependency header graph data into this DB model
downstream design code-analysis.md maps code dependency evidence into this DB model
downstream design document-canon-analysis.md maps duplicate and non-canonical document evidence into this DB model
@dependency-end
-->

# Structured Analysis Database Design

この文書は、文章解析 DSL、dependency header graph、report 構造 contract を接続する
SQLite 設計を固定する。DB は run 中の中間表現であり、正本ではない。正本は source
document、dependency manifest、DSL spec、exported evidence artifact に残す。

## Design Goal

このため、DB は次の質問へ機械的に答えるための生成 artifact である。

- report root から section、paragraph、sentence、claim、evidence まで辿れるか。
- 文中の claim は source anchor、dependency header、code dependency、実験 artifact のどれで支えられているか。
- graph diagnostic、review finding、rewrite operation はどの source span を対象にしているか。
- 文書 source は正本、runtime mirror、generated report、closed issue record、duplicate heading のどれか。
- 文書作成 skill の closure loop は、finding を修正し、同じ checker を再実行したか。
- dependency header で示される design / implementation / environment surface と、report 内の説明が対応しているか。

## Database Boundary

次は DB 配置と接続方式である。SQLite は複数 DB を `ATTACH DATABASE` で接続できる。MVP では責務ごとに DB を分け、
validation 時に attach する。DB は repo tree に置かず、既定では user home 配下の
artifact root に置く。

```text
${AGENT_CANON_STRUCTURED_ANALYSIS_HOME:-$HOME/.cache/agent-canon/structured-analysis}/
  <repo-id>/
    <run-id>/
      prose_graph.sqlite
      diagnostics.sqlite
      dependency_graph.sqlite
      report_contract.sqlite
      corpus_profile.sqlite
      exports/
```

`$HOME/.cache` を既定にする理由は、SQLite DB が再生成可能な中間 artifact だからである。
長期保存が必要な run だけ、exported Markdown/JSON/TSV evidence を repo の
`reports/agents/<run-id>/` または workflow が指定する artifact store に写す。DB 本体を
`documents/` に置いてはいけない。

DevContainer post-create は、workspace mount 後に warning-only で次を実行する。

```bash
agent-canon structured-analysis build --root <workspace> --profile devcontainer
```

この command は source file を書き換えず、git-visible file tree を `artifact` layer、
document inventory finding を `document-canon` layer として `prose_graph.sqlite` に
materialize する。その後、同じ source DB に対する解析を走らせ、warning snapshot を
`diagnostics.sqlite` に materialize する。失敗時は container setup を止めず、同じ
command を手動 rebuild command として表示する。

```sql
ATTACH DATABASE 'prose_graph.sqlite' AS prose;
ATTACH DATABASE 'diagnostics.sqlite' AS diag;
ATTACH DATABASE 'dependency_graph.sqlite' AS deps;
ATTACH DATABASE 'report_contract.sqlite' AS report;
ATTACH DATABASE 'corpus_profile.sqlite' AS corpus;
```

根拠として、SQLite は attached database 間の foreign key constraint を直接 enforce しないため、
cross-DB relation は stable id と validation query で検証する。

## Logical Databases

| DB alias | Responsibility | Owner tool |
| --- | --- | --- |
| `prose` | source anchors、lower reasoning graph、projection views、diagnostics、edit operations。 | `prose_reasoning_graph.py` |
| `deps` | dependency header manifest graph と code dependency evidence。 | dependency header tools / code dependency scanners |
| `report` | report root、section contract、claim/evidence/finding/action closure。 | report-writing / result-artifact writeout workflow |
| `corpus` | domain/corpus hints、evaluation profile、retrieval calibration metadata。 | prose graph / literature workflow |
| `artifact` | git-visible directory/file tree、README-to-directory relation、file responsibility metadata。 | `agent-canon structured-analysis build` |
| `document-canon` | duplicate heading、runtime mirror、generated report、stale document evidence。 | `agent-canon structured-analysis` |
| `diag` | current warning run、severity、rule、target path、suggested action。 | `agent-canon structured-analysis analyze` |

このため、One-file DB export は許可するが、その場合も table prefix と responsibility boundary は
この alias と同じにする。

## Stable IDs

また、Cross-DB references は URI-like id を使う。

| Prefix | Example | Meaning |
| --- | --- | --- |
| `doc:` | `doc:design-report` | source document。 |
| `anchor:` | `anchor:design-report:s12` | source span。 |
| `node:` | `node:claim:42` | graph node。 |
| `edge:` | `edge:supports:42` | graph edge。 |
| `view:` | `view:report:7` | derived projection view。 |
| `artifact:` | `artifact:sha256:...` | dependency/code/test/report artifact。 |
| `finding:` | `finding:weak_bridge:3` | diagnostic or review finding。 |
| `check:` | `check:prose-lint:20260602T101000` | checker run。 |

このため、Stable id は source path だけに依存させない。rename 後も source locator、content
hash、tool provenance で再接続できるようにする。

## Prose Graph Tables

この DB contract では、source-truth anchor を source span の最小根拠とし、lower graph
の typed relation を edge として保存する。Projection view は node / anchor
subgraph から派生する reader-facing view である。Node record と edge record は
どちらも `payload_json` を持ち、DSL 固有 field、provenance、verification route、
rewrite hint を table schema 変更なしに保持する。

| Table | Key columns | Purpose |
| --- | --- | --- |
| `prose.documents` | `document_id`, `path`, `title`, `kind`, `created_at` | Ingested source。 |
| `prose.source_anchors` | `anchor_id`, `document_id`, `span_kind`, `source_locator`, `source_start`, `source_end`, `text`, `segmentation_basis` | sentence / EDU / paragraph / section anchors。 |
| `prose.nodes` | `node_id`, `document_id`, `layer`, `kind`, `label`, `text`, `anchor_id`, `confidence`, `payload_json` | claim、evidence、concept、phase などの graph node。 |
| `prose.edges` | `edge_id`, `layer`, `kind`, `from_node_id`, `to_node_id`, `order_kind`, `confidence`, `evidence_node_id`, `payload_json` | supports、requires、refines、generalizes、concludes などの relation。 |
| `prose.projection_views` | `view_id`, `profile`, `role`, `reader_state_before`, `reader_state_after`, `abstraction_level`, `recommended_format`, `format_reason`, `confidence`, `inference_basis_json` | upper prose / macro structure の派生 view。 |
| `prose.projection_view_members` | `view_id`, `member_id`, `member_kind`, `ordinal` | projection view と canonical anchor/node の対応。 |
| `prose.diagnostics` | `finding_id`, `layer`, `target_id`, `severity`, `rule`, `message`, `suggested_action_json` | graph-derived findings。 |
| `prose.edit_operations` | `operation_id`, `kind`, `target_ids_json`, `reason`, `payload_json` | split、merge、bridge、reorder rewrite packet source。 |

`prose.edit_operations` is required only for DBs that have run a prose
`analyze` pass capable of proposing rewrite operations. A structured-analysis
DB that materializes artifact and `document-canon` diagnostics may omit this
table. Projection, explanation, integration, and handoff commands must still
consume the shared `diagnostics` rows and report operation count `0` rather than
requiring prose rewrite operations.

## Dependency And Code Graph Tables

| Table | Key columns | Purpose |
| --- | --- | --- |
| `deps.artifacts` | `artifact_id`, `path`, `kind`, `owner`, `content_hash`, `header_hash`, `payload_json` | files、docs、tests、tools、generated artifacts。 |
| `deps.dependency_edges` | `edge_id`, `direction`, `kind`, `source_artifact_id`, `target_artifact_id`, `reason`, `payload_json` | `@dependency-start` manifest graph。 |
| `deps.code_edges` | `edge_id`, `language`, `kind`, `source_artifact_id`, `target_locator`, `symbol`, `confidence`, `payload_json` | Python、shell、C/C++、Rust などの import / include / source edges。 |
| `deps.header_checks` | `check_id`, `artifact_id`, `checker`, `status`, `finding_json`, `created_at` | missing header、format、cycle、reverse-edge findings。 |

根拠として、文書上の読むべき context と言語構文上の reference は意味が違うため、
`deps.dependency_edges` と `deps.code_edges` は別 table にし、validation で必要なときだけ join する。

## Artifact Layer Tables

MVP は全ファイルの中間表現を existing graph schema に materialize する。

| Storage | Key columns | Purpose |
| --- | --- | --- |
| `nodes` | `layer = artifact`, `kind = directory`, `payload_json.path` | repo-visible directory node。 |
| `nodes` | `layer = artifact`, `kind = document/python/rust/shell/cpp/config/build/file`, `payload_json.path` | git-visible file node。 |
| `edges` | `layer = artifact`, `kind = contains`, `order_kind = hard` | directory から child directory / file への containment。 |
| `edges` | `layer = artifact`, `kind = explains_directory` | README file から parent directory への説明 relation。 |
| `metadata` | `key = artifact_inventory` | file count と directory count。 |

`artifact` layer は source truth ではない。README 生成、directory description の改稿、
prose rewrite は別 tool / skill の責務であり、この layer は検査と projection の入力に留める。

## Document Canon Tables

MVP は document canon evidence を existing graph schema に materialize する。

| Storage | Key columns | Purpose |
| --- | --- | --- |
| `nodes` | `layer = document-canon`, `kind = document_record`, `payload_json.path` | git-visible document inventory row。 |
| `nodes` | `layer = document-canon`, `kind = finding`, `payload_json.kind` | runtime mirror、duplicate heading、generated report などの finding。 |
| `edges` | `layer = document-canon`, `kind = targets_document` | finding から対象 document record への edge。 |
| `edges` | `layer = document-canon`, `kind = references_canonical` | finding から likely canonical document record への edge。 |
| `diagnostics` | `layer = document-canon`, `rule = finding kind` | cleanup workflow へ渡す severity/action。 |
| `metadata` | `key = document_canon_inventory` | inventory artifact path と count。 |

`document_responsibility_gap` diagnostics set
`suggested_action_json.verification_route` to
`document_responsibility_verification` and include recursive steps for
coverage-rule expansion, downstream span selection, and checker rerun. The DB
stores this as metadata for the skill loop; it does not decide the rewrite or
mark the finding closed by itself.

将来 dedicated table が必要になった場合も、この field contract を維持する。

## Diagnostics Database Tables

`diagnostics.sqlite` は current analysis warning snapshot を保持する。source IR と warning
snapshot を分ける理由は、DB 構築結果と tool/reviewer が消化すべき finding queue を別々に
再生成・破棄できるようにするためである。

| Table | Key columns | Purpose |
| --- | --- | --- |
| `diag.warning_runs` | `id`, `profile`, `source_db`, `warning_count`, `blocker_count`, `warn_count`, `info_count` | 1 回の解析 snapshot。MVP は `warning-run:current` を上書きする。 |
| `diag.warnings` | `id`, `run_id`, `source_layer`, `severity`, `rule`, `target_path`, `message`, `suggested_action_json` | source DB の diagnostics を warning queue として materialize した row。 |
| `diag.metadata` | `key = structured_analysis_warning_summary` | source DB path、profile、severity counts。 |

単独再解析は次で行う。

```bash
agent-canon structured-analysis analyze \
  --db <cache-dir>/prose_graph.sqlite \
  --diagnostics-db <cache-dir>/diagnostics.sqlite \
  --profile manual
```

## Report Contract Tables

| Table | Key columns | Purpose |
| --- | --- | --- |
| `report.reports` | `report_id`, `document_id`, `profile`, `source_packet_path`, `structure_contract_path`, `created_at` | report root。 |
| `report.sections` | `section_id`, `report_id`, `anchor_id`, `role`, `ordinal`, `required`, `payload_json` | report section to source span。 |
| `report.claims` | `claim_id`, `report_id`, `anchor_id`, `text`, `strength`, `status`, `payload_json` | report 内の主張。 |
| `report.evidence_refs` | `ref_id`, `claim_id`, `evidence_kind`, `target_id`, `status`, `payload_json` | claim から source anchor / artifact / check run への根拠参照。 |
| `report.findings` | `finding_id`, `report_id`, `source`, `severity`, `rule`, `target_id`, `status`, `classification`, `payload_json` | graph/review/report-quality findings。 |
| `report.finding_closure_events` | `event_id`, `finding_id`, `iteration`, `action`, `before_hash`, `after_hash`, `checker`, `result`, `payload_json` | closure loop の履歴。 |
| `report.actions` | `action_id`, `report_id`, `source_id`, `owner`, `status`, `command_or_path`, `payload_json` | prompt repair、rewrite、test、review action。 |
| `report.check_runs` | `check_id`, `report_id`, `checker`, `command`, `exit_code`, `diagnostics_count`, `blocker_count`, `artifact_path`, `created_at` | validation evidence。 |

`report.evidence_refs.target_id` は `anchor:*`、`artifact:*`、`check:*`、`node:*` を参照できる。
cross-DB FK ではなく、validation query で存在性と種別を確認する。

Experiment planning evidence can store a `hypothesis` label through `report.claims`.
Metric evidence can be referenced through `report.evidence_refs`.
Baseline evidence can be referenced through `report.evidence_refs`.
Expected result evidence can be referenced through `report.check_runs`.

## Corpus Tables

| Table | Key columns | Purpose |
| --- | --- | --- |
| `corpus.corpus_hints` | `hint_id`, `document_id`, `corpus_id`, `label`, `score`, `selected`, `basis_json` | prompt と source text から推定した corpus profile。 |
| `corpus.evaluation_profiles` | `profile_id`, `corpus_id`, `metric_contract_json`, `invalid_interpretations_json` | 抽象評価の denominator、方向、禁止解釈。 |

このため、Corpus hint は citation ではない。retrieval、example selection、evaluation norm の初期値としてだけ使う。

## Core Relations

次は relation vocabulary である。MVP の relation vocabulary は次を必ず扱う。

| Relation | Scope | Ordering |
| --- | --- | --- |
| `contains` | report -> section -> paragraph -> sentence | hard order |
| `precedes` | local reader order | hard or preferred |
| `supports` | evidence / warrant -> claim | none |
| `requires` | prerequisite -> target | hard before in projection |
| `refines` | general claim -> specific claim | preferred |
| `generalizes` | specific examples -> macro claim | preferred |
| `concludes` | premises -> conclusion | hard before |
| `references_artifact` | report claim -> dependency/code/check artifact | none |
| `derived_from` | projection view -> canonical anchors/nodes | none |
| `has_finding` | target -> finding | none |
| `closed_by` | finding -> closure event/check run | none |

このため、Graph 全体は cycle を持ちうる。topological sort は、projection profile が選ぶ ordering
subgraph にだけ適用する。

## Invariants

- Every report section has a source anchor or an explicit generated-section reason.
- Every strong claim has at least one `evidence_refs` row or is marked `limitation` / `hypothesis` / `inference`.
- Every `fix-now` finding has a closure event and a later check run showing the finding is gone.
- Persistent same-class findings become `prompt-defect`; they are not closed by iteration budget exhaustion.
- Every `prompt-defect` finding creates a prompt-repair `report.actions` row.
- Every evidence ref targeting `artifact:*` resolves in `deps.artifacts`.
- Every dependency artifact referenced by a claim has a current `header_checks` status or an explicit missing-header finding.
- Projection views are derived. They must point back to member anchors or nodes and must not become source truth.
- Recommended presentation format is advisory over a subgraph, not a source rewrite.

## Validation Queries

次は unsupported strong claims を検出する query である。

```sql
SELECT c.claim_id, c.text
FROM report.claims AS c
LEFT JOIN report.evidence_refs AS r ON r.claim_id = c.claim_id
WHERE c.strength = 'strong'
  AND c.status NOT IN ('limitation', 'hypothesis', 'inference')
  AND r.ref_id IS NULL;
```

次は open fix-now findings を検出する query である。

```sql
SELECT finding_id, rule, target_id
FROM report.findings
WHERE classification = 'fix-now'
  AND status != 'closed';
```

次は artifact evidence without dependency record を検出する query である。

```sql
SELECT r.ref_id, r.target_id
FROM report.evidence_refs AS r
LEFT JOIN deps.artifacts AS a ON a.artifact_id = r.target_id
WHERE r.target_id LIKE 'artifact:%'
  AND a.artifact_id IS NULL;
```

次は projection views without source members を検出する query である。

```sql
SELECT v.view_id, v.role
FROM prose.projection_views AS v
LEFT JOIN prose.projection_view_members AS m ON m.view_id = v.view_id
WHERE m.view_id IS NULL;
```

## Write Flow

1. Ingest source prose into `prose` and create source anchors.
2. Analyze lower graph relations and projection views.
3. Scan dependency headers into `deps.dependency_edges`.
4. Scan Python、shell、C/C++、Rust references into `deps.code_edges` without merging them with header edges.
5. Build `report.reports`, `report.sections`, `report.claims`, and evidence refs.
6. Run graph/report/dependency validators.
7. Rewrite smallest target span or action.
8. Rerun the same validator and write `finding_closure_events`.
9. Export report evidence artifacts; discard or regenerate DB as needed.

## MVP Cut

根拠として、MVP は新しい durable DB を repo に残さない。既存 tool が prose DB、
dependency graph TSV、code dependency scanner output をすでに生成するため、必要な最小実装は次である。

- `prose_reasoning_graph.py` が既に持つ SQLite table を `prose` alias 相当に整理する。
- dependency graph TSV を `deps.artifacts` / `deps.dependency_edges` へ import する adapter を作る。
- code dependency scanner output を `deps.code_edges` へ import する adapter を作る。
- report root / section / claim / finding closure を `report` DB に materialize する。
- `ATTACH` 後に validation query を走らせ、自然言語 explanation と rewrite packet を返す。

根拠として、DB は source document、manifest、scanner output から再生成できるため、
永続化が必要になった場合だけ、attached DB 群を release artifact として archive する。
