#!/usr/bin/env bash
set -euo pipefail

issues=0

report_issue() {
  printf '   \342\235\214 %s\n' "$1"
  issues=$((issues + 1))
}

report_warning() {
  printf '   \342\232\240\357\270\217 %s\n' "$1"
  issues=$((issues + 1))
}

trim_line() {
  local line="$1"
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  printf '%s' "$line"
}

check_requirements_format() {
  local req_file="docker/requirements.txt"
  local line_num=0
  local line=""
  local trimmed=""

  printf '1. Checking requirements.txt format...\n'
  if [ ! -f "$req_file" ]; then
    report_issue "docker/requirements.txt not found"
    return
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    line_num=$((line_num + 1))
    trimmed="$(trim_line "$line")"
    [ -n "$trimmed" ] || continue
    if [[ ! "$trimmed" =~ ^[A-Za-z0-9_.-]+(\[[A-Za-z0-9_,.-]+\])?([[:space:]]*(==|>=|<=|~=|!=|>|<).+)?$ ]]; then
      report_issue "Line ${line_num}: invalid requirement syntax: ${trimmed}"
    fi
  done < "$req_file"
}

check_dockerfile_coherence() {
  local dockerfile="docker/Dockerfile"

  printf '\n2. Checking Dockerfile coherence...\n'
  if [ ! -f "$dockerfile" ]; then
    report_issue "docker/Dockerfile not found"
    return
  fi

  grep -q 'requirements.txt' "$dockerfile" \
    || report_warning "Dockerfile does not reference requirements.txt"
  grep -Eiq 'pip[[:space:]]+install.*-r[[:space:]]+[^[:space:]]*requirements\.txt' "$dockerfile" \
    || report_warning "Dockerfile does not install docker/requirements.txt through pip -r"
}

is_container_runtime() {
  [ -f "/.dockerenv" ] || [ -f "/run/.containerenv" ] || [ -n "${container:-}" ] || [ -n "${DEVCONTAINER_RUNTIME_MODE:-}" ]
}

check_repo_local_venv_policy() {
  local gitignore=".gitignore"
  local path=""
  local match_file=""
  local roots=()
  local root=""
  local pattern='python3?[[:space:]]+-m[[:space:]]+venv|virtualenv|conda[[:space:]]+create|uv[[:space:]]+venv|pipenv|poetry[[:space:]]+env'
  local canonical_tool="tools/ci/python_env_policy.py"

  printf '\n3. Checking repo-local virtual-environment policy...\n'

  for path in venv env .conda conda-env .venv-*; do
    if [ -e "$path" ]; then
      report_issue "non-canonical virtual-environment directory exists: $path"
    fi
  done

  if is_container_runtime; then
    :
  elif [ -e ".venv" ]; then
    report_issue "host runtime must not keep repo-local .venv; use the canonical container runtime instead"
  fi

  if [ -f "$gitignore" ]; then
    grep -Eq '(^|/)\.venv/|^\.venv/' "$gitignore" \
      || report_issue ".venv/ is not explicitly excluded in .gitignore"
    grep -Eq '(^|/)venv/|^venv/' "$gitignore" \
      || report_issue "venv/ is not explicitly excluded in .gitignore"
  else
    report_issue ".gitignore not found"
  fi

  if [ ! -f "$canonical_tool" ]; then
    report_issue "canonical env-policy tool missing: $canonical_tool"
  fi

  if [ -f docker/Dockerfile ] && ! grep -q 'python3-venv' docker/Dockerfile; then
    report_issue "docker/Dockerfile must install python3-venv so the canonical container can create .venv"
  fi

  for root in scripts tools Makefile .github; do
    [ -e "$root" ] && roots+=("$root")
  done
  [ "${#roots[@]}" -gt 0 ] || return

  while IFS= read -r match_file; do
    case "$match_file" in
      */__pycache__/*|*.pyc|*/docker_dependency_validator.sh|*/python_env_policy.py)
        continue
        ;;
    esac
    report_issue "non-canonical virtual-environment creation command found in ${match_file}"
  done < <(
    grep -RIlE "$pattern" "${roots[@]}" 2>/dev/null \
      | sort -u
  )
}

check_pythonpath_documentation() {
  local documented=0
  local docker_documented=0
  local file=""

  printf '\n4. Checking PYTHONPATH and Docker documentation...\n'
  for file in README.md QUICK_START.md documents/coding-conventions-project.md; do
    [ -f "$file" ] || continue
    if grep -q 'PYTHONPATH' "$file" && grep -q '=/workspace/python' "$file"; then
      documented=1
    fi
    if grep -Eiq 'docker (run|build)' "$file"; then
      docker_documented=1
    fi
  done

  [ "$documented" -eq 1 ] \
    || report_warning "PYTHONPATH=/workspace/python not documented in README/QUICK_START"
  [ "$docker_documented" -eq 1 ] \
    || report_warning "Docker execution instructions not found in README/QUICK_START"
}

printf 'Checking Docker environment consistency without Python-dependent tooling...\n\n'
check_requirements_format
check_dockerfile_coherence
check_repo_local_venv_policy
check_pythonpath_documentation

printf '\nSummary: %s issues found\n' "$issues"
[ "$issues" -eq 0 ]
