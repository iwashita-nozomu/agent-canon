# html-output
<!--
@dependency-start
contract skill
responsibility Produces and validates browser-readable HTML artifacts; serving/publication is explicit and separate.
upstream design README.md shared skill canon index
upstream design ../../documents/design/responsibility-rationale.md HTML artifact/serving and closeout rationale
upstream design structure-planning.md optional structural-decision owner
upstream design report-writing.md reader-facing report content owner
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.agents/skills/html-output/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/agent_tools/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

`html-output` owns generation and validation of a requested browser-readable HTML artifact: markup, assets, links, layout/readability, accessibility-relevant structure, and any selected rendered visualization. It does not own report claims, experiment execution, raw evidence, or network publication.

## Activation

Use this skill when HTML/browser output is explicitly requested. Reports otherwise default to their normal text/document format. Structure planning activates only if a genuine page-topology decision exists.

## Artifact validation

Validate the produced file and the properties needed by the request: referenced assets exist, internal links/IDs resolve where applicable, required data/content is present, and selected layout/render checks succeed. Use `code-visualization` for selected graph rendering/coverage.

A listen socket is not required to prove a static artifact correct.

## Preview and serving

Starting an HTTP server, choosing a port, binding `0.0.0.0`, discovering host addresses, or exposing an external URL are separate delivery operations. Perform them **only** when the user explicitly requests preview, serving, or publication. Use the environment/runtime owner for lifecycle and network rules rather than creating a second server wrapper here.

When serving is requested, start the minimum appropriate process, verify the requested URL/readback, report how to stop it, and do not imply external reachability without evidence.

## Completion evidence

Always read back only:

- artifact identity/path;
- source/provenance needed to interpret it;
- validation actually selected and its result.

Optional operations such as server startup, URL publication, ImageGen, or special policy checks are recorded only when they actually ran. Do not emit `not_requested`, `blocked`, or placeholder fields for unused operations, and do not make fixed token count/field presence an eval oracle.
