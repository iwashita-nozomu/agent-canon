#!/usr/bin/env bash
set -euo pipefail

# Parent-owned post-create customization point.
# If parent repositories need extra bootstrap steps, they should override
# this script in their local .devcontainer/post-create-parent.sh file.
