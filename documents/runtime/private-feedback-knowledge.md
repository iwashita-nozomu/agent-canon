<!--
@dependency-start
contract runtime
responsibility Defines the private feedback/knowledge command boundary and its external agent-canon-log storage route.
upstream external-schema git@github.com:iwashita-nozomu/agent-canon-log.git@db3722b817be8574c682949db733df0fb5c2674a docs/FEEDBACK_KNOWLEDGE_SCHEMA.md
downstream implementation ../../tools/agent_tools/private_feedback.py
downstream implementation ../../rust/agent-canon/src/private_feedback.rs
downstream implementation ../../tools/agent_tools/workflow_monitor.py structured feedback capture
@dependency-end
-->

# Private feedback and knowledge

AgentCanon records reusable private feedback outside the source checkout. The
private remote is `iwashita-nozomu/agent-canon-log`; at this revision its
schema is read from `db3722b817be8574c682949db733df0fb5c2674a`.

The operational checkout is selected by the explicit bootstrap control root:

```text
<control-parent-root>/agent-canon-log
```

For the live installation this is normally `~/agent-canon-log`. The checkout
is a private (`0700`) normal Git clone on `main`, with the exact private remote.
Runtime data is first written below the external runtime root:

```text
<runtime-root>/spool/private-feedback/
```

The host archive adapter performs fetch, non-force publication, compare/readback
and spool retention on conflict. The container has no Git credentials and does
not publish directly.

## Commands

The Rust CLI owns the public namespace. `k` and `f` are short aliases:

```bash
agent-canon k add <topic> <prose>
agent-canon k add <topic> --stdin
agent-canon k read <topic> [--show]
agent-canon k search [--query <text>]
agent-canon k status
agent-canon k sync
agent-canon k capture <structured-feedback>
agent-canon k migrate-memory --root <agent-canon-source>

agent-canon f add <topic> <prose>
agent-canon f add <topic> --stdin
agent-canon f status
agent-canon f sync
```

Direct prose is convenient but can be retained in shell history. Use
`--stdin` for sensitive-but-permitted prose. Credentials, tokens, auth
headers, private keys, raw datasets, private source files, and embedding
payloads are rejected. Bodies do not appear in ordinary receipts, dashboards,
Issues, PRs, or agent handoffs.

The published paths are used without a second schema:

```text
feedback/<topic>/<digest>.md
knowledge/topics/<topic>/candidate.md
knowledge/topics/<topic>/read-receipt.md
runtime/skills/<topic>/SKILL.md
raw/<topic>/<payload>
```

`raw/` is git-annex-only. Without a configured special remote, raw content
remains in the external spool and `sync` reports `pending`; it is not added as
an ordinary Git blob.

## Read and private promotion

`read` writes a metadata-only read receipt. A task scope is counted once even
if it is read repeatedly. When the same topic and content digest has been read
in two distinct task/run scopes, the adapter writes a private
`runtime/skills/<topic>/SKILL.md` candidate with evidence, use, and limits. A
read receipt, a single worker-written document, or a written candidate is not
approval, truth, or public promotion. No evaluator loop, approval registry,
new global ID, or public skill-catalog/shim mutation is performed.

The runtime-local Codex managed-link route may install the private candidate
for the next session. Existing sessions do not reload it. Public promotion
requires explicit user declassification and the normal `skill-creator` and
AgentCanon update route.

`agent-canon memory` remains a compatibility route during the one-cycle
migration. `knowledge migrate-memory` copies existing `memory/records` into the
private spool and never deletes the source; deletion requires live migration
readback by the owner.
