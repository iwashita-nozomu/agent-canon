<!--
@dependency-start
contract issue
responsibility Records the completed exclusion of AgentCanon standalone Rust/Cargo source from live parent projection ownership.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md live Rust/parent artifact ownership boundary
downstream design ../../documents/runtime/shared-runtime-surfaces.toml machine-readable projection-forbidden root
downstream implementation ../../tools/agent_tools/surface_manifest.py fail-closed target/source/transition validation
downstream implementation ../../tools/sync_agent_canon.sh consumes only validated manifest renderers
downstream implementation ../../tests/agent_tools/test_rust_projection_boundary.py focused projection and cleanup regression
@dependency-end
-->

# live consumerのAgentCanon投影からRust surfaceを排除する

issue_id: AC-20260819-rust-live-projection-boundary
status: resolved
source: user
severity: S2
problem: live AgentCanon manifestにRust pathは存在しないが、standalone Rust source、parent-owned legacy regular artifact、symlink/gitlink projectionを区別する機械可読な禁止境界がなく、将来のsurface登録またはcleanup ownershipでRust/Cargo責務がconsumerへ混入できる。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/805
done: live manifestがRust standalone rootをprojection-forbiddenとして宣言し、target/source/legacy/state/update-transitionの全registrationをfail closedにし、parent regular artifactをcleanup対象へせず、standalone Rust gateとlive parent標準routeを分離した。
affected_surfaces: documents/runtime/shared-runtime-surfaces.toml, documents/runtime/SHARED_RUNTIME_SURFACES.md, tools/agent_tools/surface_manifest.py, tests/agent_tools/test_rust_projection_boundary.py
edit_scope: owner-bounded
required_action: #796のexact five-surface projectionを維持したまま、Rust/Cargo sourceとparent Rust pathをactive projectionまたはAgentCanon-owned cleanupへ登録できない単一manifest policyを追加する。
close_condition: PR #807がmainへmergeされ、focused tests、document alignment、repository-owned hosted checksが成功し、parent artifact removalが別owner routeとして再現可能に記録され、このdurable recordがissues/closedでresolvedになっている。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/805
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/807

## Resolution snapshot

- Initial AgentCanon baseline: `main@0ea5bb6d5d0bfc2e027698612aeb6fc5a3c8b0c2`.
- Dependency integration: PR #799, whose merged tree fixed the exact five live Codex surfaces.
- Implementation branch: `fix/805-rust-projection-boundary`.
- Final validated implementation base: `main@8e3296230f5d2603d0d09c1eaccfd4743616d1fb`.
- Final validated implementation head: `b17df503ee31585b6d145da0a8cf2c038973a864`.
- PR #807 was squash-merged at `2026-08-19T14:05:12Z` as
  `006fe08c7dfb262dc65a9999311167905c8092c6`.
- Durable closeout baseline: `main@0f3f534a25647c434dc4af9e6708f9c4333e75d8`.
- Durable closeout branch: `docs/805-close-durable-record`.
- The merged implementation branch is no longer present on the remote.
- Remaining verification: none.

## Root cause and resolved invariant

The active projection already contained only the five Codex-reachable views from
#796/#799, but list absence alone did not prevent a later manifest edit from
registering `rust/**` as a target, source, repository-state path, legacy cleanup
path, or update-transition candidate.

Let `F` be every path equal to or below `rust`, `T` the manifest-owned parent
targets, `S` the AgentCanon source paths materialized by those entries, and `U`
the update-transition candidates. PR #807 enforces:

```text
prefix_intersection(T ∪ S ∪ U, F) = ∅
```

The check uses canonical POSIX path components rather than textual string
prefixes. It therefore rejects both descendants of `rust/` and an over-broad
ancestor projection that would contain `rust/`. Every renderer consumed by
`sync_agent_canon.sh` loads the same manifest authority before emitting link,
copy, regular, cleanup, or transition specs; no shell-local Rust allowlist or
second classifier was introduced.

## Implemented ownership boundary

- `vendor/agent-canon/rust/**` remains AgentCanon standalone source/test
  ownership.
- Parent regular files or directories under `rust/**` remain parent-owned
  content or historical artifacts; AgentCanon sync neither infers a projection
  edge nor receives deletion ownership.
- Generated copies remain regular parent bytes unless explicit parent provenance
  says otherwise.
- A symlink resolving into AgentCanon Rust is an unmanaged projection and must
  fail the consumer structure check.
- A gitlink/submodule is an explicit parent dependency edge, not a live
  AgentCanon root view.
- An absent Rust path is the live-projection fixed point; no cleanup placeholder
  or compatibility path is introduced.

`projection_forbidden_roots = ["rust"]` is deliberately separate from
`standalone_only` and `removed_legacy`. Those modes participate in root-absence
or stale-symlink cleanup and would incorrectly grant AgentCanon lifecycle
ownership over parent regular content.

## Acceptance criteria

- [x] `projection_forbidden_roots` identifies `rust` without adding a surface
  entry or normalized-snapshot field.
- [x] Target paths under or above `rust` fail before link, copy, state, or
  cleanup specs render.
- [x] Aliases whose source lies under `rust` fail even when the parent target is
  elsewhere.
- [x] Update-transition candidates below `rust` fail closed.
- [x] The exact five live symlink paths remain unchanged.
- [x] Root-absence and stale-symlink cleanup output contains no `rust` path.
- [x] Parent regular content remains present in the focused consumer fixture.
- [x] Regular, generated-copy, symlink, and gitlink/submodule classifications
  are documented with owner-specific handling.
- [x] The standalone Rust static gate remains AgentCanon-owned and live parent
  standard checks do not invoke it.
- [x] Focused tests, document check, repository static gates, Issue Mirror,
  Agent Runtime Dashboard, and Entrypoint Owner Map passed.
- [x] jax_utils artifact removal remains traceable as a separate parent change.

## Validation evidence

The exact final base plus the five-file implementation delta passed:

```text
python -m unittest -v \
  tests.agent_tools.test_surface_manifest \
  tests.agent_tools.test_codex_projection_boundary \
  tests.agent_tools.test_rust_projection_boundary

Ran 19 tests: OK

python tools/agent_tools/surface_manifest.py --root . --prefix . check-doc
# exit 0
```

Hosted validation for head `b17df503ee31585b6d145da0a8cf2c038973a864`:

- Issue Mirror run `32255575565`: success.
- Agent Runtime Dashboard run `32255575522`: success.
- Entrypoint Owner Map run `32255575561`: success.
- AgentCanon Static Gates run `32255575524`: success.
  - `select-static-units`: success.
  - selected responsibility: `contracts-static`.
  - `contracts-static`: success.
  - aggregate `static-gates`: success.
  - `rust-static`: skipped by the responsibility selector.

The `rust-static` skip is positive boundary evidence rather than missing
verification. The change modifies a projection contract, not standalone Rust
source or its gate, so Cargo/toolchain validation does not leak into the live
consumer route. No physical-environment acceptance remains.

## Durable reopen diagnosis

PR #807 used `Closes #805`, so GitHub closed Issue #805 when the PR was merged at
`2026-08-19T14:05:12Z`. The merge also published this canonical record under
`issues/open/` with `status: in_progress`.

`tools/agent_tools/issue_sync.py` derives the expected remote state from the
record directory: `issues/open/` maps to `OPEN`, while `issues/closed/` maps to
`CLOSED`. `.github/workflows/issue-mirror.yml` runs that synchronization on each
protected `main` push. The first post-merge sync therefore restored the
canonical open state and reopened #805 at approximately
`2026-08-19T14:05:26Z`.

This reopen did not indicate that the Rust projection policy was absent or that
PR #807 was unmerged. It exposed only that implementation publication and
durable closeout were separate transitions. Moving this record to
`issues/closed/`, setting `status: resolved`, and recording `resolved_by` removes
the state drift without touching the already merged implementation.

## Durable closeout scope

This closeout owns only the Issue lifecycle record:

- move `issues/open/AC-20260819-rust-live-projection-boundary.md` to the same
  filename under `issues/closed/`;
- set `status: resolved`;
- add `resolved_by: PR #807`;
- preserve the implementation invariant, validation evidence, owner boundaries,
  and reopen diagnosis.

It does not change:

- `documents/runtime/shared-runtime-surfaces.toml`;
- `tools/agent_tools/surface_manifest.py`;
- `documents/runtime/SHARED_RUNTIME_SURFACES.md`;
- `tests/agent_tools/test_rust_projection_boundary.py`;
- #796/#799's exact five live projection;
- #795 or #781 retirement work;
- project_template #182 / PR #191 consumer implementation;
- jax_utils parent-owned regular artifact migration;
- GPU admission, runtime alignment, or standalone static-gate selection.

## Remaining owner boundaries

No remaining item is part of #805's close condition.

- A jax_utils regular `rust/agent-canon/**` artifact, if removed, remains a
  parent-owned Issue/branch/PR with filesystem and index identity readback.
- project_template #182 / PR #191 remains the consumer implementation owner.
- #795 and #781 retain their own retirement and migration acceptance.

The implementation is merged, all #805-owned verification is complete, and the
durable record is ready for closed-state publication.
