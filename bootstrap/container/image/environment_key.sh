#!/usr/bin/env bash
set -euo pipefail

root=${1:-$(git rev-parse --show-toplevel)}
dockerfile=bootstrap/container/image/Dockerfile
inputs=("$dockerfile")
while IFS= read -r source; do
  [[ -n "$source" ]] && inputs+=("${source#source=}")
done < <(grep -oE 'source=[^,[:space:]\\]+' "$root/$dockerfile")

git -C "$root" ls-tree -r HEAD -- "${inputs[@]}" |
  LC_ALL=C sort |
  sha256sum |
  awk '{print $1}'
