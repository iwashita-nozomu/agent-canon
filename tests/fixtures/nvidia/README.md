# NVIDIA parser fixtures

<!--
@dependency-start
contract test
responsibility Provides immutable raw NVIDIA evidence for the R5 parser selectors.
upstream design ../../../documents/gpu-admission-r5-source-packet.md R5-N-04 and U-11 named fixture manifest
downstream implementation ../../../tools/experiments/execution_resource_plan.py NvidiaInventoryProbe parser family
downstream implementation ../../../tests/tools/test_execution_resource_plan.py W1 parser selectors
@dependency-end
-->

These files are byte fixtures for the strict fd-bound NVIDIA driver, list, and
XML parser family. Their hashes and expected outcomes are recorded in
`manifest.json`; the raw evidence files intentionally contain no normalization
or compatibility metadata.
