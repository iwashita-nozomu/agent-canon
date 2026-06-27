#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Delegates GitHub Actions AgentCanon submodule checkout to the shared CI helper.
# upstream implementation ../../tools/ci/checkout_agent_canon_submodule.sh shared checkout helper.
# downstream implementation ../../tools/ci/check_github_workflows.py enforces workflow usage.
# @dependency-end

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/../.." && pwd -P)"

exec bash "${repo_root}/tools/ci/checkout_agent_canon_submodule.sh" "$@"
