#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs Issue #1370's live regression in its disposable Docker-host test image.
# upstream implementation ./Dockerfile.live provides Python, Git, pytest, and Docker CLI
# downstream test ./test_live_projection_authority.py validates live projection authority
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../../tools/repository/support/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"

RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT:-}"
RUNTIME_ROOT="${RUNTIME_ROOT%/}"
if [[ "${RUNTIME_ROOT}" != /* || "${RUNTIME_ROOT}" == "/" || ! -d "${RUNTIME_ROOT}" ]]; then
  echo "AGENT_CANON_RUNTIME_ROOT must name an existing absolute external runtime directory" >&2
  exit 2
fi

TEST_WORKAREA="$(mktemp -d "${RUNTIME_ROOT}/live-projection-1370.XXXXXX")"
IMAGE_TAG="agent-canon-live-projection:${TEST_WORKAREA##*/}-$$"
SOURCE_IMAGE="/opt/agent-canon/source"
TEST_NODE="${SOURCE_IMAGE}/tests/bootstrap/test_live_projection_authority.py::test_topic_registration_anchor_status_remove_share_projection"
IMAGE_BUILT=0

# Match Docker CLI precedence without forwarding its context or auth files:
# DOCKER_CONTEXT wins, then DOCKER_HOST, then the configured current context.
if [[ -n "${DOCKER_CONTEXT:-}" ]]; then
  DOCKER_ENDPOINT="$(docker context inspect --format '{{.Endpoints.docker.Host}}' "${DOCKER_CONTEXT}")"
elif [[ -n "${DOCKER_HOST:-}" ]]; then
  DOCKER_ENDPOINT="${DOCKER_HOST}"
else
  CURRENT_DOCKER_CONTEXT="$(docker context show)"
  DOCKER_ENDPOINT="$(docker context inspect --format '{{.Endpoints.docker.Host}}' "${CURRENT_DOCKER_CONTEXT}")"
fi

case "${DOCKER_ENDPOINT}" in
  unix:///*)
    DOCKER_SOCKET_PATH="${DOCKER_ENDPOINT#unix://}"
    ;;
  *)
    echo "the live Docker test requires a local Unix-socket Docker endpoint" >&2
    exit 2
    ;;
esac

cleanup() {
  local status=$?
  local cleanup_status=0
  trap - EXIT INT TERM

  if [[ "${IMAGE_BUILT}" -eq 1 ]] && ! docker image rm -- "${IMAGE_TAG}"; then
    echo "failed to remove task-owned test image ${IMAGE_TAG}" >&2
    cleanup_status=1
  fi
  if ! rm -rf -- "${TEST_WORKAREA}"; then
    echo "failed to remove task-owned test workarea ${TEST_WORKAREA}" >&2
    cleanup_status=1
  fi
  if [[ "${status}" -eq 0 && "${cleanup_status}" -ne 0 ]]; then
    status="${cleanup_status}"
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker build \
  --file "${SCRIPT_DIR}/Dockerfile.live" \
  --tag "${IMAGE_TAG}" \
  "${WORKSPACE_ROOT}"
IMAGE_BUILT=1

# The only runtime binds are the task workarea at its host-absolute path and
# the configured Docker socket. Normalize the inner CLI to the socket mount
# destination without exposing host Docker context or credential files.
docker run --rm \
  --mount "type=bind,source=${TEST_WORKAREA},target=${TEST_WORKAREA}" \
  --mount "type=bind,source=${DOCKER_SOCKET_PATH},target=/var/run/docker.sock" \
  --workdir "${TEST_WORKAREA}" \
  --env AGENT_CANON_LIVE_DOCKER=1 \
  --env "AGENT_CANON_RUNTIME_ROOT=${TEST_WORKAREA}/runtime" \
  --env DOCKER_HOST=unix:///var/run/docker.sock \
  "${IMAGE_TAG}" \
  python3 -m pytest -vv "${TEST_NODE}"
