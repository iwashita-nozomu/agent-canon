# grilling
<!--
@dependency-start
contract skill
responsibility Provides an explicit, read-only design-tree interview that resolves the user's decisions before implementation.
upstream design ../../documents/design/request-intent-and-update-relation.md owns question scope, explicit write clauses, and handoff separation
upstream design ./agent-orchestration.md owns fact discovery and the existing post-interview handoff route
upstream implementation ./catalog.yaml owns public skill identity and explicit trigger metadata
upstream implementation ./skill-dependencies.yaml owns the public-skill dependency relation
downstream implementation ../../tools/agent/skills/skill_shim_materializer.py generates the runtime discovery shim
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates source/catalog/shim alignment
@dependency-end
-->

## Purpose

`grilling` is an explicit, read-only interview for stress-testing a plan,
decision, or idea before implementation. It adapts Matt Pocock's upstream
design-tree and frontier-round behavior to AgentCanon's existing request and
routing boundaries. It does not authorize implementation, review, testing,
approval, or any other write action.

## Use When

Activate this skill only when the user explicitly requests a grilling session,
for example `grill me`, `grilling`, or `$grilling`. Do not activate it for
ordinary planning, implementation, review, debugging, experiment, or
hypothesis-validation language that does not explicitly request the interview.

The interview is read-only. The user's answers settle decisions; the agent
finds environmental facts through the existing fact-discovery route. After
the interview, any resolved request clauses or remaining owner/edit/validation
branch return through the existing request-intent and Decision Sufficiency
handoff. This skill itself never grants write authority.

## Interview Contract

Interview the user relentlessly until you reach a shared understanding. Map
this as a **design tree**: every decision branches into the decisions that hang
off it.

Work the tree in **rounds**. The **frontier** is every decision whose
prerequisites are already settled: the questions you can ask _now_ without
guessing at answers you haven't heard yet. Ask the whole frontier in one round:
number each question and give your recommended answer. Then wait for the user's
answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the
frontier outward and unblock questions that depended on them. Recompute the
frontier and ask the next round. A question whose answer depends on another
question still open in this round belongs to a _later_ round, not this round.

Finding _facts_ is the agent's job, never the user's. When a frontier question
needs a fact from the environment (filesystem, tools, etc.), dispatch an
existing fact-finding sub-agent to find it; don't ask the user for anything you
could look up yourself. Don't block on it: a running exploration is an
unsettled prerequisite, so only the questions downstream of it wait for the
sub-agent to report; ask the rest of the frontier now. The _decisions_ are the
user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree
has been visited and nothing is left silently assumed. Do not act on it until
the user confirms that shared understanding has been reached. If the user
stops, stop the read-only interview without treating unanswered branches as
settled.

## Authority Boundary

- This skill may inspect facts and ask questions; it may not edit files, run
  implementation commands, approve a plan, or declare a write route ready.
- Existing AgentCanon orchestration supplies the fact-finding and handoff
  mechanics. Do not invent a new role, tool, schema, registry, or completion
  checker for grilling.
- Whole-frontier rounds, recommendations, user-owned decisions, and the
  frontier-empty termination condition are part of the upstream contract.
  Do not replace them with one-question-at-a-time interviews, a fixed question
  cap, or custom completion semantics.

## Upstream Attribution

Adapted from Matt Pocock's `grilling` skill in `mattpocock/skills`:

- source: <https://github.com/mattpocock/skills/blob/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76/skills/productivity/grilling/SKILL.md>
- source snapshot: `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`
- license: MIT; the required copyright and permission notice is recorded in
  [`references/agent-canon-technology-bibliography.md`](../../references/agent-canon-technology-bibliography.md)

Only the AgentCanon routing, read-only authority, and existing handoff boundary
are local adaptation. The upstream design-tree, dependency-frontier,
whole-frontier-round, recommendation, fact-finding, user-decision, and
frontier-empty semantics remain the behavioral source.
