#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Delegates AgentCanon submodule checkout to the GitHub bootstrap helper.
# upstream implementation ../../.github/scripts/checkout_agent_canon_submodule.sh bootstrap-safe checkout helper
# downstream implementation ./check_github_workflows.py enforces workflow usage.
# @dependency-end

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "${script_dir}/../.." && pwd -P)"

exec bash "${repo_root}/.github/scripts/checkout_agent_canon_submodule.sh" "$@"
