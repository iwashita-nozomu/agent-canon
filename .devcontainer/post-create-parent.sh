#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Parent-owned container bootstrap customization point.
# upstream design ../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# downstream implementation ../tools/sync_agent_canon.sh keeps parent-owned regular .devcontainer artifacts
# downstream implementation ../tools/docker_dependency_validator.sh validates parent-postcreate customizations
# @dependency-end
set -euo pipefail

# Parent-owned post-create customization point.
# If parent repositories need extra bootstrap steps, they should override
# this script in their local .devcontainer/post-create-parent.sh file.
