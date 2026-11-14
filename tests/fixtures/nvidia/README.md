# NVIDIA parser fixtures

<!--
@dependency-start
contract test
responsibility Provides immutable raw NVIDIA evidence for the R5 parser selectors.
upstream design ../../../documents/experiments/gpu-admission-r5-source-packet.md R5-N-04 and U-11 named fixture manifest
downstream implementation ../../../tools/runtime/dispatch/agent-canon/src/execution_resource_plan.rs NVIDIA inventory and process occupancy parser family
downstream implementation ../../../tools/runtime/dispatch/agent-canon/src/execution_resource_plan.rs captured parser unit selector
@dependency-end
-->

These files are byte fixtures for the strict fd-bound NVIDIA driver, list, and
XML parser family. Their hashes and expected outcomes are recorded in
`manifest.json`; the raw evidence files intentionally contain no normalization
or compatibility metadata.
