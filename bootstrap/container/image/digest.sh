#!/usr/bin/env bash
set -euo pipefail

root=${1:-$(git rev-parse --show-toplevel)}
dockerfile=bootstrap/container/image/Dockerfile
{
  git -C "$root" ls-tree -r HEAD -- "$dockerfile"
  while IFS= read -r source; do
    source=${source#source=}
    [[ -n "$source" ]] || continue
    if [[ -d "$root/$source" ]]; then
      git -C "$root" ls-tree -r HEAD -- "$source" |
        awk -F '\t' '$2 ~ /(^|\/)Cargo\.(toml|lock)$/'
    else
      git -C "$root" ls-tree -r HEAD -- "$source"
    fi
  done < <(grep -oE 'source=[^,[:space:]\\]+' "$root/$dockerfile")
} | LC_ALL=C sort | sha256sum | awk '{print $1}'
