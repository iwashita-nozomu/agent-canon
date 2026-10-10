#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs AgentCanon live and native proof regressions in one disposable test image.
# upstream implementation ./Dockerfile.live provides Python, Git, and Docker CLI
# downstream test ./test_live_projection_authority.py validates live projection authority
# downstream design ./lean-proof-dependencies.toml pins the native proof toolchain
# downstream implementation ../../tools/analysis/dependencies/dependency_plan.py installs the selected proof profile dependencies
# downstream implementation ../../tools/analysis/proof/lean_proof_env.py runs native Lean checks
# @dependency-end

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${SCRIPT_DIR}/../../tools/repository/support/repo_paths.sh"
WORKSPACE_ROOT="$(agent_canon_repo_root "${BASH_SOURCE[0]}")"

usage() {
  printf 'usage: %s [live-projection|lean-proof]\n' "${BASH_SOURCE[0]}" >&2
}

if [[ "$#" -gt 1 ]]; then
  usage
  exit 2
fi
TEST_PROFILE="${1:-live-projection}"
case "${TEST_PROFILE}" in
  live-projection|lean-proof) ;;
  *)
    usage
    exit 2
    ;;
esac

SOURCE_IMAGE="/opt/agent-canon/source"
TEST_NODE="${SOURCE_IMAGE}/tests/bootstrap/test_live_projection_authority.py::test_topic_registration_anchor_status_remove_share_projection"
LEAN_PROOF_COMMAND='
set -euo pipefail

tool=/opt/agent-canon/source/tools/analysis/proof/lean_proof_env.py
runtime_root="${AGENT_CANON_RUNTIME_ROOT:?}"
# The installer anchors receipts to a Git workspace; the disposable container owns it.
workspace="$(mktemp -d /tmp/agent-canon-lean-workspace.XXXXXX)"
env_dir="${runtime_root}/tasks/formal-proof/lean-proof-env"
fixtures="${runtime_root}/lean-proof-fixtures"
export HOME="${runtime_root}/home"
export ELAN_HOME="${runtime_root}/elan"
export PATH="${ELAN_HOME}/bin:${PATH}"
mkdir -p "${fixtures}" "${HOME}"
git -C "${workspace}" init --quiet
python3 -m tools.analysis.dependencies.dependency_plan install \
  --workspace "${workspace}" \
  --manifest /opt/agent-canon/source/tests/bootstrap/lean-proof-dependencies.toml \
  --format json

printf "%s\n" "import Mathlib" "" "example : True := by trivial" > "${fixtures}/positive.lean"
printf "%s\n" "import Mathlib" "" "example : False := by trivial" > "${fixtures}/negative.lean"
printf "%s\n" \
  "import Plausible" \
  "" \
  "/-- error: Found a counter-example! -/" \
  "#guard_msgs in" \
  "#eval Plausible.Testable.check (forall (n : Nat), n < n) { quiet := true }" \
  "" \
  "example : False := by trivial" \
  > "${fixtures}/counterexample-type-error.lean"

python3 "${tool}" all-smoke \
  --env-dir "${env_dir}" \
  --lean-toolchain "leanprover/lean4:v4.30.0" \
  --execute --format json
python3 "${tool}" check-file \
  --env-dir "${env_dir}" \
  --lean-file "${fixtures}/positive.lean" \
  --execute --format json

expect_lean_failure() {
  local source_file="$1"
  local result_file="$2"
  local status
  if python3 "${tool}" check-file \
    --env-dir "${env_dir}" \
    --lean-file "${source_file}" \
    --execute --format json > "${result_file}" 2>&1; then
    cat "${result_file}" >&2
    echo "expected native Lean failure for ${source_file}" >&2
    return 1
  else
    status="$?"
  fi
  if [[ "${status}" -ne 1 ]] \
    || ! grep -Fq "\"status\": \"failed\"" "${result_file}" \
    || ! grep -Fq "unsolved goals" "${result_file}"; then
    cat "${result_file}" >&2
    echo "native Lean failure did not match the expected unsolved-goal result: ${source_file}" >&2
    return 1
  fi
  cat "${result_file}"
}

expect_lean_failure "${fixtures}/negative.lean" "${fixtures}/negative-result.json"
expect_lean_failure \
  "${fixtures}/counterexample-type-error.lean" \
  "${fixtures}/counterexample-type-error-result.json"
'
IMAGE_BUILT=0
IMAGE_TAG=""

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

DOCKER_SOCKET_PATH=""
if [[ "${TEST_PROFILE}" == "live-projection" ]]; then
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
fi

TEST_WORKAREA="$(mktemp -d)"
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
IMAGE_TAG="agent-canon-live-test:${TEST_WORKAREA##*/}-$$"

docker build \
  --file "${SCRIPT_DIR}/Dockerfile.live" \
  --tag "${IMAGE_TAG}" \
  "${WORKSPACE_ROOT}"
IMAGE_BUILT=1

DOCKER_RUN_ARGS=(
  --rm
  --mount "type=bind,source=${TEST_WORKAREA},target=${TEST_WORKAREA}"
  --env "AGENT_CANON_RUNTIME_ROOT=${TEST_WORKAREA}/runtime"
)
if [[ "${TEST_PROFILE}" == "live-projection" ]]; then
  # Only the live projection regression invokes the host Docker daemon from
  # inside the test container. The Lean proof checks need only their workarea.
  DOCKER_RUN_ARGS+=(
    --mount "type=bind,source=${DOCKER_SOCKET_PATH},target=/var/run/docker.sock"
    --env AGENT_CANON_LIVE_DOCKER=1
    --env DOCKER_HOST=unix:///var/run/docker.sock
  )
  DOCKER_WORKDIR="${TEST_WORKAREA}"
  DOCKER_COMMAND=(python3 -m pytest -vv "${TEST_NODE}")
else
  DOCKER_WORKDIR="${SOURCE_IMAGE}"
  DOCKER_COMMAND=(bash -euo pipefail -c "${LEAN_PROOF_COMMAND}")
fi

docker run "${DOCKER_RUN_ARGS[@]}" \
  --workdir "${DOCKER_WORKDIR}" \
  "${IMAGE_TAG}" \
  "${DOCKER_COMMAND[@]}"
