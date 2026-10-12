# cpp-review
<!--
@dependency-start
contract skill
responsibility Reviews selected C/C++ contract, build, ownership, and performance risks with point-of-use validation.
upstream design ../canonical/skills.md skill canon registry
upstream design ./catalog.yaml public skill and capability projection
upstream design ./skill-dependencies.yaml prerequisite and reviewer order
upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json C++ validation profile owner
upstream design ../../documents/conventions/DOCSTRING_GUIDE.md semantic Docstring contract and sparse C++ projection
upstream design ../../documents/design/cpp-debugging.md native debugging selection and evidence boundary
@dependency-end
-->

## Reader Map

Use this Skill when the review needs a concrete C/C++ contract or risk resolved.
A C/C++ path or reviewer candidate alone does not select every route.

| Review question | Read next |
| --- | --- |
| Native source, header, ABI, or build behavior | [Core review](#core-review) |
| Docstring or convention prose only | [Documentation review](#documentation-review) |
| Crash, hang, lifetime, initialization, or race | [Runtime debugging](#runtime-debugging) |
| Performance claim or changed workload cost | [Performance review](#performance-review) |

## Purpose

Review the changed C/C++ contract, reachable behavior, ownership, and relevant
validation. For performance claims, examine the actual workload and cost
evidence. Select only the parts that can affect the requested claim.

## Use When

Use when the selected task needs evidence about native C/C++ source, public
headers, ABI/FFI behavior, build settings, or C++ semantic documentation.
Debugging and performance details below apply only when those concerns are part
of the request or changed guarantee.

## Core review

Start with the changed interface or behavior and its governing contract. Trace
only the callers and failure paths needed to understand the effect. Check
header/implementation correspondence, linkage and ABI, type invariants,
ownership and lifetime, moves/copies and resource release, bounds/null handling,
and exception or error behavior where they affect the change. Preserve required
inputs, memory and numerical semantics, and existing regression contracts.

Use the project's selected build, test, or static-analysis route that covers the
changed guarantee. For CMake path/build changes, consult the relevant
[build-layout owner](../../documents/design/cpp-build-layout.md) and the
consumer's CMake configuration for production paths, targets, and tests. Use
existing compiler settings and analysis configuration rather than creating a
second set of flags or include paths.

Run through the project's selected environment with its permissions and
resource/retry limits. Keep diagnostic success separate from program success,
and report failed, partial, skipped, and unrun checks accurately.

## Documentation review

For a C/C++ semantic-documentation change, use the
[Docstring contract](../../documents/conventions/DOCSTRING_GUIDE.md). Check
syntax and that the prose matches the relevant interface and changed behavior.
Do not copy declarations into comments or require a fixed set of tags. A
documentation-only change does not add a native build unless its changed claim
requires one.

## Runtime debugging

For an active crash, hang, lifetime, initialization, or race question, use
[C++ debugging](../../documents/design/cpp-debugging.md) to choose relevant
diagnostic evidence. Preserve the project's runner and execution limits. A
diagnostic command completing does not by itself show that the program behavior
is correct.

## Performance review

Activate this route for a performance claim, a changed known hot path or cost
model, or an existing performance regression contract. Establish the workload,
metric, comparison conditions, and supported bottleneck hypothesis. Use the
project's existing benchmark or profiler where needed; compare equivalent work
and report variability and untested conditions. Keep analytical cost reasoning
separate from measured results, and preserve ABI, lifetime, concurrency, and
numerical semantics. Do not infer end-to-end gains from an isolated timing or
introduce a universal threshold. For numerical solvers, use
[computational-optimization](computational-optimization.md) when convergence or
solver behavior is part of the claim.

## Expected outcome

Report the relevant interface, ownership, error-path, correctness, build, and
documentation findings with the validation actually performed. For an active
performance claim, include the comparison and its limits. Identify unresolved
risks without treating missing evidence as a pass.

## Core references

- [C++ conventions](../../documents/conventions/coding-conventions-cpp.md)
- [Testing conventions](../../documents/conventions/coding-conventions-testing.md)
- [Review process](../../documents/conventions/REVIEW_PROCESS.md)
- [C++ Core Guidelines](https://isocpp.org/guidelines)
