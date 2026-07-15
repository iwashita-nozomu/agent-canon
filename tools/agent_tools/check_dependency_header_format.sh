#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Gates dependency-manifest syntax and required coverage through the canonical graph parser.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# upstream implementation ../../rust/agent-canon/src/dependency_manifest.rs owns complete-file parsing and static validation
# upstream implementation ./scan_dependency_headers.sh projects parsed manifest coverage
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
CHANGED=0
REQUIRE_HEADER=0
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_header_format.sh [--root DIR] [--changed] [--require-header] [--allow-frontmatter] [paths...]

The canonical graph parser owns syntax, registered kinds, spans, and target binding.
This wrapper adds only caller-selected coverage policy.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT_DIR="$2"; shift 2 ;;
    --changed) CHANGED=1; shift ;;
    --require-header) REQUIRE_HEADER=1; shift ;;
    --allow-frontmatter) shift ;;
    -h|--help) usage; exit 0 ;;
    *) INPUT_PATHS+=("$1"); shift ;;
  esac
done

ROOT_DIR="$(realpath -m "$ROOT_DIR")"
if [[ -x "$ROOT_DIR/vendor/agent-canon/tools/bin/agent-canon" ]]; then
  GRAPH_CLI="$ROOT_DIR/vendor/agent-canon/tools/bin/agent-canon"
else
  GRAPH_CLI="$ROOT_DIR/tools/bin/agent-canon"
fi

status_file="$(mktemp)"
selected_file="$(mktemp)"
context_file="$(mktemp)"
trap 'rm -f "$status_file" "$selected_file" "$context_file"' EXIT

set +e
"$GRAPH_CLI" graph status --root "$ROOT_DIR" --profile default --format json >"$status_file"
status_exit=$?
set -e
if [[ "$status_exit" -ne 0 ]] || ! jq -e '
  .status == "fresh"
  and .integration_record.verified == true
  and .integration_record.profile == "default"
  and .integration_record.source_snapshot_profile == "parent"
' "$status_file" >/dev/null 2>&1; then
  echo "DEPENDENCY_HEADER_FORMAT=fail"
  echo "canonical graph integration is not fresh and verified"
  cat "$status_file"
  exit 1
fi

if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
  printf '%s\n' "${INPUT_PATHS[@]}" | sed 's#^\./##' | sort -u >"$selected_file"
elif [[ "$CHANGED" -eq 1 ]]; then
  {
    git -C "$ROOT_DIR" diff --name-only --diff-filter=ACMRT HEAD --
    git -C "$ROOT_DIR" ls-files --others --exclude-standard
  } | sed '/^$/d' | sort -u >"$selected_file"
else
  git -C "$ROOT_DIR" ls-files | sort -u >"$selected_file"
fi

is_checkable() {
  case "$1" in
    .git/*|.pytest_cache/*|.ruff_cache/*|reports/*|LICENSE|LICENSE.*|NOTICE|NOTICE.*|COPYING|COPYING.*) return 1 ;;
    *.bash|*.cfg|*.css|*.h|*.hpp|*.html|*.c|*.cc|*.cpp|*.md|*.py|*.rst|*.sh|*.toml|*.txt|*.yaml|*.yml|*.zsh) return 0 ;;
    *) return 1 ;;
  esac
}

failures=0
checked=0
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  is_checkable "$path" || continue
  checked=$((checked + 1))
  set +e
  "$GRAPH_CLI" graph context --root "$ROOT_DIR" --profile default --format json --path "$path" >"$context_file"
  context_exit=$?
  set -e
  if [[ "$context_exit" -ne 0 || "$(jq -r '.status // "invalid"' "$context_file" 2>/dev/null)" != "fresh" ]]; then
    echo "$path: invalid graph dependency manifest evidence: graph-context-unavailable"
    failures=$((failures + 1))
    continue
  fi
  evidence_state="$(jq -r --arg path "$path" '
    def rows($kind): [
      .items[]
      | select(
          .kind == $kind
          and .source_store == "manifest"
          and .producer == "source-snapshot"
          and .source_path == $path
          and .authority == "ManifestParser"
        )
    ];
    (rows("manifest.present")) as $present
    | (rows("manifest.contract")) as $contract
    | (rows("manifest.responsibility")) as $responsibility
    | if ($present | length) != 1 then "invalid"
      elif $present[0].value == "false" and ($contract | length) == 0 and ($responsibility | length) == 0 then "missing"
      elif $present[0].value == "true" and ($contract | length) == 1 and ($responsibility | length) == 1 then "present"
      else "invalid"
      end
  ' "$context_file" 2>/dev/null || printf invalid)"
  case "$evidence_state" in
    present) ;;
    missing)
      if [[ "$REQUIRE_HEADER" -eq 1 ]]; then
        echo "$path: missing dependency manifest"
        failures=$((failures + 1))
      fi
      ;;
    *)
      echo "$path: invalid graph dependency manifest evidence: malformed-projection"
      failures=$((failures + 1))
      ;;
  esac
done <"$selected_file"

if [[ "$failures" -gt 0 ]]; then
  echo "DEPENDENCY_HEADER_FORMAT=fail checked=$checked failures=$failures"
  exit 1
fi
echo "DEPENDENCY_HEADER_FORMAT=pass authority=canonical-graph checked=$checked"
