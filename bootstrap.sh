#!/usr/bin/env bash
# The sole host bootstrap entrypoint. It delegates to a fixed Python module.
set -euo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=bootstrap/lib/entrypoint.sh
source "$repository_root/bootstrap/lib/entrypoint.sh"
bootstrap_python_entrypoint "$repository_root" "$@"
