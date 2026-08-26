#!/usr/bin/env bash
# The sole host bootstrap entrypoint. It delegates only to the shell/Docker
# adapter; AgentCanon Python starts after the resident container is healthy.
set -euo pipefail

repository_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=bootstrap/lib/entrypoint.sh
source "$repository_root/bootstrap/lib/entrypoint.sh"
bootstrap_host_entrypoint "$repository_root" "$@"
