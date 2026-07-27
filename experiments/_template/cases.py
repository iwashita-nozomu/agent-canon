# @dependency-start
# contract reference
# responsibility Holds template experiment case definitions after copying.
# upstream design ../../documents/experiments/experiment-registry.md defines managed experiment expectations.
# downstream implementation run.py consumes topic-specific cases after the template is filled in.
# @dependency-end
"""Template case-definition placeholder."""

# IMPLEMENT HERE: define domain cases for topic-owned reports only.
# The managed route does not import this module as an execution entrypoint; it
# adapts the selected topic main() into one external ExperimentRunner task.
# Worker-only dependencies belong inside run.py run_case_worker() after the
# frozen child environment has been installed.
