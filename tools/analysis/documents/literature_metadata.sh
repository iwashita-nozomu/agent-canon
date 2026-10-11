#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: bash tools/analysis/documents/literature_metadata.sh DOI\n' >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

doi=$1
if [[ $doi != 10.*/* || $doi == */ || $doi == *[[:space:]]* ]]; then
  printf 'DOI must be a bare identifier beginning with 10. and containing a suffix.\n' >&2
  exit 2
fi

accept='application/vnd.citationstyles.csl+json'

url_encode_doi() {
  local input=$1
  local encoded=''
  local character
  local escaped
  local index
  local LC_ALL=C

  # Preserve DOI path separators; percent-encode reserved characters in the DOI.
  for ((index = 0; index < ${#input}; index += 1)); do
    character=${input:index:1}
    case $character in
      [a-zA-Z0-9._~/-]) encoded+=$character ;;
      "'") encoded+='%27' ;;
      *) printf -v escaped '%%%02X' "'$character"; encoded+=$escaped ;;
    esac
  done

  printf '%s' "$encoded"
}

encoded_doi=$(url_encode_doi "$doi")
source_url="https://api.crossref.org/v1/works/${encoded_doi}/transform"

# A nonzero curl exit means callers must discard any response bytes already streamed to stdout.
curl \
  --fail \
  --location \
  --silent \
  --show-error \
  --path-as-is \
  --connect-timeout 10 \
  --max-time 60 \
  --proto '=https' \
  --proto-redir '=https' \
  --header "Accept: $accept" \
  "$source_url"

retrieved_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

printf '%s\n' \
  '## Metadata' \
  '- provider: crossref' \
  '- source_kind: csl-json' \
  "- doi: $doi" \
  "- source_url: $source_url" \
  "- retrieved_at_utc: $retrieved_at_utc" >&2
