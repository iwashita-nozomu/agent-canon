# Markdown math fence gap in docs check

<!--
@dependency-start
contract issue
responsibility Tracks operational finding that documents/docs checker and md-style skill diverge on math-like fenced blocks.
upstream implementation ../../agents/skills/md-style-check.md defines markdown lint policy.
upstream implementation ../../.agents/skills/md-style-check/SKILL.md provides implementation guidance for docs check.
upstream design ../../documents/conventions/common/05_docs.md defines math notation and docs conventions.
upstream implementation ../../rust/agent-canon/src/docs.rs records the Rust check executor behavior.
upstream implementation ../../tests/tools/test_check_markdown_math.py is the docs math-fence fixture and expected behavior suite.
upstream implementation ../../evidence/agent-evals/skill_workflow_prompt_eval.toml records deterministic skill checks.
upstream implementation ../../documents/structured-analysis/graph-dsl.md and ../../references/gpt-5.6-benchmark-report-ja.md are migrated math documents.
@dependency-end
-->

issue_id: AC-20260715-markdown-math-fence-lint-gap
status: in_progress
source: user
severity: S2
evidence: tests/tools/test_check_markdown_math.py, evidence/agent-evals/skill_workflow_prompt_eval.toml, documents/structured-analysis/graph-dsl.md, references/gpt-5.6-benchmark-report-ja.md
affected_surfaces: agents/skills/md-style-check.md, .agents/skills/md-style-check/SKILL.md, documents/conventions/common/05_docs.md, rust/agent-canon/src/docs.rs, tests/tools/test_check_markdown_math.py, evidence/agent-evals/skill_workflow_prompt_eval.toml, documents/structured-analysis/graph-dsl.md, references/gpt-5.6-benchmark-report-ja.md
edit_scope: agents/skills/md-style-check.md, .agents/skills/md-style-check/SKILL.md, documents/conventions/common/05_docs.md, rust/agent-canon/src/docs.rs, tests/tools/test_check_markdown_math.py, evidence/agent-evals/skill_workflow_prompt_eval.toml, documents/structured-analysis/graph-dsl.md, references/gpt-5.6-benchmark-report-ja.md, issues/open/AC-20260715-markdown-math-fence-lint-gap.md
required_action: Prohibit mathematical notation in generic text-like code fences and declared math-like fences. Recognize text/plaintext/txt/plain and math/latex/tex fence info aliases case-insensitively, report declared math-like blocks once at the opening fence, and report deterministic delimiter, numeric/function equality, and operand-checked relation syntax without fuzzy or scored classification. Exclude only literal URL, backtick, arrow, angle-placeholder, currency, and shell-variable spans or tokens rather than bypassing their whole line.
close_condition: Canonical runtime skill and convention documents state the rule; the Rust docs checker rejects representative text/plaintext/txt/plain/math/latex/tex, numeric/function equality, compact/spaced/Unicode relation, and mixed math-plus-literal-span violations; pure literal/protocol output, currency/shell-variable syntax, HTML/placeholder text, and typed source fences pass; the focused regression suite and full docs scan pass; the existing graph-dsl and benchmark math are display-math compliant; and the deterministic skill eval passes all canonical/runtime checks.

## Finding

- Existing `check_markdown_math` currently skips every fenced block, so it does not catch math-like text when it is written inside a plain text fence.
- The style skill documentation defines inline and double-dollar math style, but it does not explicitly forbid equations in untyped text/code fences.
- The user observed a gap when a battery optimization note passed DOCS_CHECK despite equations inside a `text` fence.
- The fix is being prepared in the same PR.
- Fence aliases are first info tokens, normalized case-insensitively: text-like
  `text`, `plaintext`, `txt`, and `plain`; declared math-like `math`, `latex`,
  and `tex`. Typed source fences remain outside the heuristic.
- Declared math-like fences produce one finding at the opening fence to avoid
  repeated payload noise. Text-like fences report each violating payload line
  because that line is the smallest repair location.
- Numeric literals and single-symbol function expressions are deterministic
  math atoms. ASCII and Unicode relation operators require math operands on
  both sides.
- URL, backtick, arrow, and angle-placeholder spans are removed locally before
  relation checks, so math elsewhere on the same line remains visible. Dollar
  pairs that begin a later currency or shell-variable token remain literal.
- This issue requires syntax-based fence boundaries and negative fixtures; no fuzzy or scored classification should be used for this rule.
