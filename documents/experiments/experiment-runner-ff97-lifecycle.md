# Fixed ExperimentRunner ff97 lifecycle identity

<!--
@dependency-start
contract implementation
responsibility Records the fixed generic ExperimentRunner lifecycle consumed by GPU admission R5.
upstream design ../design/experiment_runner.md generic runner ownership boundary
@dependency-end
-->

The fixed read-only ExperimentRunner source clone is
`/mnt/l/workspace/experiment_runner-w1-r4-lifecycle-design` at commit
`ff97eccd9c3044566cd50b950e9b9717eb4b77bd`.

The relevant generic owners are
`python/experiment_runner/runner.py` and
`python/experiment_runner/resource_scheduler.py`. R5 binds this lifecycle from
the composition root; it does not reimplement process groups, timeout, signal,
descendant cleanup, scheduler completion, or generic runner state transitions.
