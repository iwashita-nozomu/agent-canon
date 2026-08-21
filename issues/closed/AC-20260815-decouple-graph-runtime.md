<!--
@dependency-start
contract issue
responsibility Records the completed separation of source dependency correctness from persisted graph runtime state.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
upstream design ../../documents/design/source-owned-dependency-validation.md source and runtime authority boundary
downstream implementation ../../tools/agent_tools/source_dependency_graph.py source-derived dependency projection
downstream implementation ../../tools/agent_tools/graph_client.py compatibility and explicit graph runtime boundary
downstream implementation ../../tools/agent_tools/check_dependency_headers.py canonical source validation
downstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh source-owned repository review
downstream implementation ../../tools/ci/run_pr_dependency_source_gate.sh source-owned PR dependency gate
downstream implementation ../../tools/ci/check_agent_canon_pr.sh PR routing consumer
downstream implementation ../../tests/agent_tools/test_graph_client_source_projection.py source projection regression
downstream implementation ../../tests/tools/test_agent_canon_pr_dependency_source_gate.py no-runtime PR fixture
downstream implementation ../../tests/tools/test_agent_canon_pr_graph_gate_integration.py persisted orchestration boundary regression
@dependency-end
-->

# [Runtime簡素化] dependency検証を永続graph snapshotから分離する

issue_id: AC-20260815-decouple-graph-runtime
status: resolved
source: user
severity: S2
problem: tracked sourceから決定論的に導出できるdependency correctnessが、Rust graph executable、persisted database、producer/profile identity、runtime evidence、snapshot freshnessへ依存していた。
evidence: https://github.com/iwashita-nozomu/agent-canon/pull/725
done: dependency query/context、header/design/tool/search consumer、repository review、PR gateはpersisted graph stateなしでsource correctnessを検証し、graph runtimeは明示的analysis capabilityだけに限定された。
affected_surfaces: documents/design/, agents/canonical/CLI_ENTRYPOINTS.md, tools/agent_tools/, tools/ci/, tests/agent_tools/, tests/tools/
edit_scope: owner-bounded
required_action: none; Runtime全体の削除や別consumerの移行はそれぞれのrepository-qualified Issueが所有する。
close_condition: PR #725 のfocused no-runtime tests、repository-owned required checks、main統合、Issue上のbranch/PR/validation追跡が完了している。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/723
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/725 (merge d6ca10d2f90514fe90d84f8e2a64662a369fc194)
resolved_at: 2026-08-16

## Resolution

Tracked source stateを $S$、source-derived dependency projectionを $P(S)$、persisted runtime stateを $R$ とする。dependency correctnessは $S$ から決定論的に導出できるため、通常validationのauthorityを `V(P(S), R)` から `V(S)` へ縮約した。これによりCargo、graph executable、SQLite snapshot、freshness、runtime profile identityは通常のdependency gateの前提ではなくなった。

現行の責務境界は次のとおり。

- tracked sourceとcanonical parent-view bindingがdependency factを所有する。
- malformed source、root escape、unresolved targetはcache fallbackせずfail closedする。
- repository reviewとPR gateはsource-derived projectionを直接消費する。
- persisted graph build/status/queryとtoken contextは明示的analysis capabilityとして残す。
- `source|skipped` receiptのwriter/parser/consumer lifecycleは一つのownerに集約し、旧`prepared|scoped` graph stateを通常PR経路から除外する。

## Implemented change

PR #725 は次を実装した。

- `source_dependency_graph.py`によるpure source projection。
- `graph_client.py`を介したsource-owned query/context compatibility route。
- changed-file header、design claim、tool drift、vector search、repository reviewのsource-direct化。
- persisted graph build/status/queryを通常PR dependency gateから除外。
- production shell producer→parser→consumerのlive receipt lifecycleとcleanup/readback。
- relation kindを`design|implementation|environment`へ統一し、design/document/evidence ledgerを同期。
- explicit `--ensure-graph`だけをpersisted graph preparationとして維持。

## Validation evidence

PR head `5cffa5e3d47115a7f8b54cd6a47c6aad1a69d050` はlatest main driftを取り込み、merge commit `d6ca10d2f90514fe90d84f8e2a64662a369fc194`としてmainへ統合された。

- receipt live shell E2E: 3 passed
- focused source/receipt suites: 68 passed; final non-E2E: 39 passed
- source dependency export / dependency headers / graph cycle-report-only: pass
- Pyright: 0 errors
- Ruff D102、Bash syntax、tool drift、diff check: pass
- Python review: ACCEPT
- diff review: PASS
- AgentCanon Static Gates、Agent Runtime Dashboard、Issue Mirror: success
- unresolved review threads: 0

## Boundary after closeout

このrecordはsource dependency authorityの完了だけを閉じる。Rust graph implementation、SQLite schema、visualization、Runtime全体の削除、GPU/runtime/devcontainer移行、別repositoryのconsumer routingは非目標であり、関連Issueへ吸収しない。後続変更は本recordをupstream design evidenceとして参照し、それぞれのowner・依存辺・終了条件を独立して定義する。