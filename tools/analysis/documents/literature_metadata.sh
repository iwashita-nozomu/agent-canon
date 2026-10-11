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

sha256_stdin() {
  local digest_line
  if command -v sha256sum >/dev/null 2>&1; then
    digest_line=$(sha256sum) || return
  elif command -v shasum >/dev/null 2>&1; then
    digest_line=$(shasum -a 256) || return
  else
    printf 'literature metadata lookup requires sha256sum or shasum for provenance.\n' >&2
    return 127
  fi
  printf '%s\n' "${digest_line%% *}"
}

encoded_doi=$(url_encode_doi "$doi")
source_url="https://api.crossref.org/v1/works/${encoded_doi}/transform"
request_material=$(printf 'GET\nAccept: %s\n%s' "$accept" "$source_url")
request_sha256=$(printf '%s' "$request_material" | sha256_stdin)

response_file=''
cleanup() {
  if [[ -n $response_file ]]; then
    rm -f "$response_file"
  fi
}
trap cleanup EXIT

response_file=$(mktemp "${TMPDIR:-/tmp}/agent-canon-literature-metadata.XXXXXX")

# Buffer the provider response so a failed HTTP transfer cannot look like a complete CSL record.
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
  --output "$response_file" \
  "$source_url"

if [[ ! -s $response_file ]]; then
  printf 'Crossref returned an empty CSL response for DOI %s.\n' "$doi" >&2
  exit 1
fi

content_sha256=$(sha256_stdin < "$response_file")
retrieved_at_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

cat "$response_file"

printf '%s\n' \
  '## Metadata' \
  '- provider: crossref' \
  '- source_kind: csl-json' \
  "- doi: $doi" \
  "- source_url: $source_url" \
  "- retrieved_at_utc: $retrieved_at_utc" \
  "- request_sha256: $request_sha256" \
  "- content_sha256: $content_sha256" >&2
