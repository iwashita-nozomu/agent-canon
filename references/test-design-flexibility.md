<!--
@dependency-start
contract reference
responsibility Records source basis for resilient test design skill and tool policy.
upstream design README.md AgentCanon reference index
downstream design ../documents/coding-conventions-testing.md translates testing guidance into repo policy
downstream design ../agents/skills/test-design.md uses the guidance in the test-design skill
downstream implementation ../rust/agent-canon/src/test_design.rs implements deterministic diagnostic hints
@dependency-end
-->

# Test Design Flexibility Source Packet

Access date: 2026-06-09.

## Question

How should AgentCanon guide agents away from brittle tests that block harmless
code changes, while still preserving strong regression detection?

## Adopted Sources

| Source | Type | Adopted Claim | Limitation |
|---|---|---|---|
| Microsoft Learn, Unit testing best practices for .NET, <https://learn.microsoft.com/en-us/dotnet/core/testing/unit-testing-best-practices> | Official guidance | Unit tests should support regression, documentation, and design; brittle and hard-to-read tests damage the codebase. | .NET examples are not a language-neutral test taxonomy. |
| Ham Vocke, The Practical Test Pyramid, <https://martinfowler.com/articles/practical-test-pyramid.html> | Practitioner reference | Test suites need multiple granularities; high-level tests should be fewer and focused on user-visible behavior. | Pyramid shape is a heuristic, not a repo-specific adequacy metric. |
| Claessen and Hughes, QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs, <https://alastairreid.github.io/RelatedWork/papers/claessen%3Aicfp%3A2000/> | Research paper | Property-based tests encode general properties and generate examples, which can find counterexamples beyond hand-picked cases. | Generators and properties can be wrong; property tests do not replace example tests for specific regressions. |
| Hypothesis documentation, <https://hypothesis.readthedocs.io/en/latest/> | Official tool documentation | Property-based tests describe input ranges and invariants; the tool explores edge cases that authors may miss. | Python-specific tool; other languages need equivalent frameworks such as proptest or QuickCheck. |
| Segura et al., A Survey on Metamorphic Testing, IEEE TSE 2016, <https://www.isa.us.es/publications/type/article-journal/2016/survey-metamorphic-testing> | Survey paper | Metamorphic testing checks relations among multiple executions when a direct oracle is hard to state. | Relations must be valid for the target contract; invalid relations create false alarms. |
| Papadakis et al., Mutation Testing Advances: An Analysis and Survey, <https://discovery.ucl.ac.uk/id/eprint/10056704/> | Survey paper | Mutation testing evaluates test-suite adequacy by introducing artificial defects and observing whether tests catch them. | Mutation score is expensive and can be distorted by equivalent mutants or weak mutation operators. |
| Panichella et al., Test smells 20 years later, <https://link.springer.com/article/10.1007/s10664-022-10207-5> | Empirical research | Static test-smell tools can over-detect; smell warnings need context and should not be treated as automatic proof of bad tests. | The paper reassesses smell validity broadly; AgentCanon uses only conservative design hints. |

## AgentCanon Translation

- Test design starts from observable behavior, not private call sequence.
- Example-based tests remain valid for named regressions and boundary values.
- Property-based tests are preferred for broad input spaces with stable
  invariants.
- Metamorphic tests are preferred when exact expected output is hard but valid
  relations between inputs and outputs are known.
- Mutation testing is an adequacy check for whether assertions are meaningful,
  not a replacement for selecting the right behavior contract.
- Static smell detection is advisory. The tool may emit `review` or
  `design-hint` findings that a skill must interpret against the contract.
