"""Public Docker image and acceptance-route contract tests."""

# @dependency-start
# contract test
# responsibility Verifies the image-only public test boundary and the explicit persisted-graph capability split.
# upstream design ../../CONTAINER_OPERATIONS.md standalone source test boundary
# upstream implementation ../../docker/Dockerfile public test image
# upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh explicit graph-analysis route
# upstream implementation ../../.github/workflows/public-docker-acceptance.yml candidate-tree Docker acceptance
# @dependency-end

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DOCKERFILE = REPO_ROOT / "docker" / "Dockerfile"
PUBLIC_ACCEPTANCE_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "public-docker-acceptance.yml"
)
DEPENDENCY_REVIEW = (
    REPO_ROOT / "tools" / "agent_tools" / "run_repo_dependency_review.sh"
)


def _workflow_run_step(name: str) -> str:
    """Return one named public-acceptance run command."""
    payload = yaml.safe_load(PUBLIC_ACCEPTANCE_WORKFLOW.read_text(encoding="utf-8"))
    jobs = payload["jobs"]
    steps = jobs["public-docker-acceptance"]["steps"]
    matching = [step for step in steps if step.get("name") == name]
    assert len(matching) == 1
    command = matching[0].get("run")
    assert isinstance(command, str)
    return command.strip()


def test_public_image_does_not_bootstrap_persisted_graph() -> None:
    """Image construction must not require its own derived graph output."""
    dockerfile = PUBLIC_DOCKERFILE.read_text(encoding="utf-8")

    assert "graph build" not in dockerfile
    assert "graph status" not in dockerfile
    assert "graph.sqlite" not in dockerfile
    assert ".agent-canon/knowledge-graph" not in dockerfile


def test_explicit_graph_analysis_capability_remains_available() -> None:
    """Persisted graph preparation remains an explicit analyzer capability."""
    dependency_review = DEPENDENCY_REVIEW.read_text(encoding="utf-8")

    assert "--ensure-graph" in dependency_review
    assert '"$GRAPH_CLI" graph status' in dependency_review
    assert '"$GRAPH_CLI" graph build' in dependency_review


def test_public_acceptance_runs_exact_image_owned_commands() -> None:
    """The candidate is accepted through the source-owned image alone."""
    assert _workflow_run_step("Build public test image") == (
        "docker build -f docker/Dockerfile -t agent-canon-current ."
    )
    assert _workflow_run_step("Run source-owned public test contract") == (
        "docker run --rm agent-canon-current testrunner.sh"
    )


def test_public_acceptance_removes_only_task_owned_docker_resources() -> None:
    """Closeout removes the exact test image and avoids shared pruning."""
    run_command = _workflow_run_step("Run source-owned public test contract")
    cleanup = _workflow_run_step("Remove task-owned Docker resources")

    assert "--mount" not in run_command
    assert " -v " not in f" {run_command} "
    assert "docker image inspect --format '{{.Id}}' agent-canon-current" in cleanup
    assert 'docker image rm "${image_id}"' in cleanup
    assert "docker image inspect agent-canon-current" in cleanup
    assert "prune" not in cleanup
