# AgentCanon GPU admission R5 NVIDIA visibility boundary

<!--
@dependency-start
contract design
responsibility Records the strict NVIDIA process and opaque UUID visibility boundary for GPU admission R5.
upstream design ./gpu-admission-r5-source-packet.md fixed R5 packet and U-18 owner boundary
@dependency-end
-->

The primary review is the read-only artifact
`/mnt/l/workspace/agent-canon-devcontainer-runtime-boundary/reports/agents/w1-tool-env-routing-20260716/nvidia_primary_process_visibility_review.md`.
Structured NVIDIA process evidence must cover compute, graphics, MPS, and
other resource holders, with authoritative PID/start identity and GPU/GI/CI or
full GPU/MIG UUID mapping. Compute-only output cannot prove absence of other
holders. Missing or hidden namespace identity fails closed.

The accepted sources are NVIDIA System Management Interface documentation and
the CUDA Programming Guide's UUID/MIG UUID environment rules. The admission
implementation uses full opaque UUIDs only and conservatively closes physical
GPU occupancy over all MIG descendants.
