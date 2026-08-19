#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
TEST_LIST="${AGENT_CANON_TESTLIST:-${SOURCE_ROOT}/test/testlist.toml}"
ACTIVE_ROUTE="${AGENT_CANON_ACTIVE_ROUTE:-docker}"

cd "${SOURCE_ROOT}"
exec python3 test/testrunner.py \
  --source-root "${SOURCE_ROOT}" \
  --test-list "${TEST_LIST}" \
  --require "${ACTIVE_ROUTE}"
