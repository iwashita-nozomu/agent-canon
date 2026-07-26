<!--
@dependency-start
contract reference
responsibility Documents the gh-backed GitHub publish and PR tool.
upstream design ../agent-canon-github-remote.md defines canonical GitHub remote policy.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR workflow usage.
upstream design ../../ROOT_AGENTS.md defines PR mutation authority.
downstream implementation ../../tools/agent_tools/github_publish.py implements the tool.
downstream implementation ../../tests/agent_tools/test_github_publish.py validates the tool contract.
@dependency-end
-->

# GitHub Publish Tool

`tools/agent_tools/github_publish.py` is the canonical AgentCanon entrypoint for
GitHub branch publication, pull request creation/update, and PR check evidence.
It is `gh`-based for repository identity and PR operations, and uses `git push`
only after `gh repo view` and `git remote get-url origin` agree on the same
`owner/name`.

The standalone `push` action is reversible branch transport, not correctness,
review, or PR publication. With no packet file, it requires the verified remote
identity/permission and a named current branch, captures local `HEAD`/tree,
sends that commit with
`git push -u --force-with-lease <remote> <commit-sha>:refs/heads/<branch>`, reads exactly one
`git ls-remote <remote> refs/heads/<branch>` result, and verifies the remote SHA
and unchanged local branch/HEAD/tree. It does not generate or claim G1/G2/G3 or
PR lifecycle evidence; summaries use `publication_boundary=branch_transport_only`.
If a sealed packet is supplied, its candidate identity is additionally checked
and the summary retains the sealed publication evidence. A sealed packet may
also carry `predecessor_graph_materialization`; when present, the publisher
requires the closed materialization schema, packet SHA, predecessor source OID,
unique source/dependency reference rows, and CAS-base OID equality before push.
Any identity mismatch
is a typed `UserVisibleFailure`; there is no push API, alternate remote, or
checkout fallback.

The tool requires `--user-task` on every action. The compact stdout and optional
`--summary-out` JSON include the task, repository, branch, remote verification,
and next action. It rejects literal URL push, `.git/config` remote inference,
branch-name inference, PR-context inference, and machine-local remote inference.

## Commands

Push the current topic branch:

```bash
python3 tools/agent_tools/github_publish.py push \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon
```

Push and create or update a pull request:

```bash
python3 tools/agent_tools/github_publish.py publish-pr \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --title "<PR title>" \
  --body-file reports/agents/<run-id>/pr_body.md \
  --summary-out reports/agents/<run-id>/github_publish.json
```

Read PR checks:

```bash
python3 tools/agent_tools/github_publish.py checks \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --pr <number-or-branch>
```

## Predecessor Integration Record

After an approved source PR is merged, the same parser and serializer own one
immutable record per approved unit. The public actions are
`predecessor-integration`, `verify-predecessor-integration`, and
`verify-predecessor-integration-set`; `--root` appears at most once before the
action. The complete grammar and two-unit command sequence are fixed in
`agents/canonical/CLI_ENTRYPOINTS.md`.

The producer derives exactly
`<report-dir>/predecessor_integration.<unit_id>.json`, where `unit_id` matches
`[a-z][a-z0-9_]{0,63}`. It verifies the explicit design and APPROVE review,
GitHub PR identity, merged source OID, observed target-main OID, and both
ancestry relations. The record has the closed fields `schema_version`,
`unit_id`, `design_path`, `design_sha256`, `approve_review_path`,
`approve_review_sha256`, `source_pr_url`, `source_pr_number`,
`integrated_source_oid`, `observed_target_main_oid`, `produced_at`, `producer`,
and `artifact_sha256`. The artifact hash covers canonical JSON plus LF for the
first twelve fields. Complete bytes are rendered before an identity-owned
temporary file is published with no-replace semantics; a collision never
overwrites an existing record.

Individual verification is read-only and requires an archived record, its
sibling `archive_manifest.json`, and the expected unit ID. Set verification
requires an exact ordered key set, matching record/archive pairs, and one
common `integrated_source_oid`; it discards every verified prefix on failure
and writes no aggregate artifact. The required source set is
`knowledge_graph`, then `active_design_packet_materialization`.

Success writes one canonical JSON object plus LF to stdout and zero stderr.
Failure writes zero stdout and one canonical typed error plus LF to stderr.
Exit `2` is usage/unit grammar, `3` is record/schema/path/hash/review/archive or
stale input, `4` is GitHub/Git state, `5` is serialization/publication/collision/
cleanup, and `6` is set inconsistency. Error records expose `code`, `phase`,
`unit_id`, `path`, `field`, `expected`, `observed`, `command`, `returncode`, and
`retryable`; no compatibility flags, alternate serializer, partial result, or
manual record path exists.
The source-branch predecessor graph/materialization record is therefore checked
before the main publication transport/CAS boundary, while remote readback still
proves the exact pushed branch SHA. CI fresh-clone fixtures validate clone/bootstrap or update behavior only. They
are not ordinary publication evidence; publication evidence comes from the
sealed lifecycle identity, the exact SHA ref push, and the remote readback.
`publish-pr`, PR mutation, and merge remain packet/G1/G2/G3-bound operations;
they reject a missing sealed packet.

## Hook Boundary

GitHub publish and PR evidence are user task execution, not edit-time code
quality checks. The hook dispatcher skips child guard hooks for `GitPush`,
simple `git push`, safe `gh pr` create/edit/view/list/checks/comment commands,
and this tool. Publish safety remains in the tool's explicit `gh` remote
verification and the PR workflow gates.

Non-critical hook, style, OOP, log-surface, planning, or closeout findings are
recorded as warning or closeout evidence. They do not stop branch publication or
PR body/check updates.

## Retired Shell Route

`tools/push_origin.sh` no longer performs push work. It prints the replacement
command and exits so old shell snippets cannot become a second publish
implementation or bypass the required user-task evidence.
