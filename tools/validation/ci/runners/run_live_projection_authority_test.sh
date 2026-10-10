#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs Issue #1370's live regression in its disposable Docker-host test image.
# upstream implementation ../../../../tests/bootstrap/live-projection-test.pack.toml declares the Docker-host capability
# upstream implementation ./run_in_repo_container.py owns pack image/run composition
# downstream test ../../../../tests/bootstrap/test_live_projection_authority.py validates live projection authority
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../../../repository/support/repo_paths.sh"
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
PACK="${WORKSPACE_ROOT}/tests/bootstrap/live-projection-test.pack.toml"
DOCKERFILE="${WORKSPACE_ROOT}/tests/bootstrap/Dockerfile.live-projection-test"
TEST_NODE="${SOURCE_IMAGE}/tests/bootstrap/test_live_projection_authority.py::test_topic_registration_anchor_status_remove_share_projection"

cleanup() {
  local status=$?
  local cleanup_status=0
  trap - EXIT INT TERM

  if ! docker image rm -- "${IMAGE_TAG}"; then
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

# The workarea is both the container workspace and its host-visible scratch
# root, so Docker bind sources created by pytest resolve to the same paths on
# the host daemon. The source itself is copied into the disposable image.
unset AGENT_CANON_OPTIONAL_MOUNTS
python3 "${SCRIPT_DIR}/run_in_repo_container.py" \
  --pack "${PACK}" \
  --builder docker \
  --dockerfile "${DOCKERFILE}" \
  --context "${WORKSPACE_ROOT}" \
  --tag "${IMAGE_TAG}" \
  --workspace-root "${TEST_WORKAREA}" \
  --container-workspace "${TEST_WORKAREA}" \
  --workdir "${TEST_WORKAREA}" \
  --env "AGENT_CANON_RUNTIME_ROOT=${TEST_WORKAREA}/runtime" \
  -- \
  python3 -m pytest -vv "${TEST_NODE}"
