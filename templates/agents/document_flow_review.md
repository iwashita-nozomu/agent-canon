# Document Flow Review
<!--
@dependency-start
contract template
responsibility Documents Document Flow Review for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}

{{>findings_area_table}}

## Top-Down Readthrough

<!-- Check whether a first reader can follow the document from top to bottom without backtracking. -->

## Term And Prerequisite Introduction

<!-- Check whether terms, assumptions, and prerequisites from the exact active-packet Implementation Source Packet are introduced before they are used. Record the design artifact path and packet entry ID; chat or schedule prose is not authority. -->

## Section Order And Reader Path

<!-- Check whether section order supports the intended reader path and whether key decisions appear before implementation detail. -->

## Reader-Visible Side Effects

<!-- Check every reader-facing item in the exact active-packet Design Side-Effect Map: docs, workflows, prompts, CLI/help text, reports, and validation output. Record the packet entry and source reference for each finding. -->

## Rewrite Targets

<!-- Record concrete rewrite points needed to make the document readable in order. -->

## Revision Loop

<!-- Record what the designer must rewrite so the top-down reader path becomes approval-ready. -->

{{>decision_approve_revise_escalate}}
