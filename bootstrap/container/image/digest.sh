#!/usr/bin/env bash
set -euo pipefail

root=${1:-$(git rev-parse --show-toplevel)}
dockerfile=bootstrap/container/image/Dockerfile
{
  git -C "$root" ls-tree -r HEAD -- "$dockerfile" .dockerignore
  while IFS= read -r source; do
    source=${source#source=}
    [[ -n "$source" ]] || continue
    git -C "$root" ls-tree -r HEAD -- "$source"
  done < <(grep -oE 'source=[^,[:space:]\\]+' "$root/$dockerfile")
} | LC_ALL=C sort -u | sha256sum | awk '{print $1}'
