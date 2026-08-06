#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Installs and validates the fixed base capability set before declarative derived dependencies.
# upstream design ../CONTAINER_OPERATIONS.md image versus mounted devcontainer ownership boundary
# upstream design ../documents/design/devcontainer/parent-dependency-manifest-followup.md parent manifest and ordering contract
# downstream implementation ../tools/agent_tools/devcontainer_dependencies.py validates and installs derived records
# downstream implementation post-create.sh invokes this fixed bootstrap before plan validation
# @dependency-end

set -euo pipefail

readonly NODE_VERSION="22.14.0"
readonly NODE_NPM_VERSION="10.9.2"
readonly NODE_X86_64_SHA256="69b09dba5c8dcb05c4e4273a4340db1005abeafe3927efda2bc5b249e80437ec"
readonly NODE_AARCH64_SHA256="08bfbf538bad0e8cbb0269f0173cca28d705874a67a22f60b57d99dc99e30050"
readonly NODE_INSTALL_PATH="/usr/local/lib/node-v22.14.0"
readonly NODE_BOOTSTRAP_RECEIPT="/var/lib/agent-canon/bootstrap/node-22.14.0.json"

fail() {
  printf 'dependency bootstrap failed: %s\n' "$1" >&2
  exit 1
}

validate_runtime_identity() {
  local runtime_id
  local runtime_version
  local runtime_machine
  runtime_id="$(awk -F= '$1 == "ID" { gsub(/^"|"$/, "", $2); print $2; exit }' /etc/os-release)"
  runtime_version="$(awk -F= '$1 == "VERSION_ID" { gsub(/^"|"$/, "", $2); print $2; exit }' /etc/os-release)"
  case "$(uname -m)" in
    x86_64|amd64) runtime_machine="amd64" ;;
    *) runtime_machine="$(uname -m)" ;;
  esac
  [ "$runtime_id" = "ubuntu" ] || fail "runtime ID must be ubuntu, got: $runtime_id"
  [ "$runtime_version" = "22.04" ] || fail "runtime VERSION_ID must be 22.04, got: $runtime_version"
  [ "$runtime_machine" = "amd64" ] || fail "runtime platform must be linux/amd64, got: linux/$runtime_machine"
  printf 'DEVCONTAINER_RUNTIME_IDENTITY=pass:ubuntu:%s:linux/%s\n' "$runtime_version" "$runtime_machine"
}

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    fail "root or sudo is required for: $*"
  fi
}

architecture() {
  case "$(uname -m)" in
    x86_64|amd64) printf '%s\n' "x86_64" ;;
    aarch64|arm64) printf '%s\n' "aarch64" ;;
    *) fail "unsupported Linux architecture: $(uname -m)" ;;
  esac
}

node_sha256() {
  case "$(architecture)" in
    x86_64) printf '%s\n' "$NODE_X86_64_SHA256" ;;
    aarch64) printf '%s\n' "$NODE_AARCH64_SHA256" ;;
  esac
}

node_asset_architecture() {
  case "$(architecture)" in
    x86_64) printf '%s\n' "x64" ;;
    aarch64) printf '%s\n' "arm64" ;;
  esac
}

check_python_toml_capability() {
  python3 - <<'PY'
try:
    import tomllib
except ModuleNotFoundError:
    import tomli
PY
}

check_python_pip_capability() {
  python3 -m pip --version >/dev/null 2>&1
}

check_python_requirement_capability() {
  python3 - <<'PY'
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

requirement = Requirement("pyyaml[secure]>=6")
assert canonicalize_name(requirement.name) == "pyyaml"
assert requirement.extras == {"secure"}
PY
}

node_receipt_matches() {
  [ -f "$NODE_BOOTSTRAP_RECEIPT" ] || return 1
  python3 - "$NODE_BOOTSTRAP_RECEIPT" "$(node_sha256)" <<'PY'
import json
import sys

receipt_path, archive_sha256 = sys.argv[1:]
expected = {
    "schema": "agent-canon.node-bootstrap-receipt/v1",
    "status": "pass",
    "archive_sha256": archive_sha256,
    "node_version": "22.14.0",
    "npm_version": "10.9.2",
    "bundled_npm_version": "10.9.2",
    "install_path": "/usr/local/lib/node-v22.14.0",
}
with open(receipt_path, encoding="utf-8") as stream:
    payload = json.load(stream)
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
PY
}

check_node_activation() {
  command -v node >/dev/null 2>&1 || fail "node is unavailable"
  [ "$(node --version)" = "v$NODE_VERSION" ] || fail "node is not v$NODE_VERSION"
  command -v npm >/dev/null 2>&1 || fail "npm is unavailable"
  [ "$(npm --version)" = "$NODE_NPM_VERSION" ] || fail "npm is not $NODE_NPM_VERSION"
  [ "$(readlink -f "$(command -v node)")" = "$NODE_INSTALL_PATH/bin/node" ] || \
    fail "node is not activated from the verified archive install path"
  [ "$(readlink -f "$(command -v npm)")" = \
    "$NODE_INSTALL_PATH/lib/node_modules/npm/bin/npm-cli.js" ] || \
    fail "npm is not activated from the verified bundled CLI path"
}

check_bootstrap() {
  command -v python3 >/dev/null 2>&1 || fail "python3 is unavailable"
  check_python_toml_capability || fail "python3 has neither tomllib nor tomli"
  check_python_pip_capability || fail "python3-pip capability is unavailable"
  check_python_requirement_capability || fail "python3-packaging capability is unavailable"
  check_node_activation
  node_receipt_matches || fail "verified Node bootstrap receipt is unavailable or stale"
  command -v gpg >/dev/null 2>&1 || fail "gnupg capability is unavailable"
  command -v ninja >/dev/null 2>&1 || fail "ninja-build capability is unavailable"
  command -v cc >/dev/null 2>&1 || fail "build-essential capability is unavailable: cc"
  command -v gcc >/dev/null 2>&1 || fail "build-essential capability is unavailable: gcc"
  printf 'DEVCONTAINER_BASE_BOOTSTRAP=pass\n'
}

install_verified_node_archive() {
  local archive
  local asset_arch
  local work_dir
  local archive_root
  local executable
  local receipt_file
  work_dir="$(mktemp -d)"
  trap 'rm -rf "$work_dir"' RETURN
  asset_arch="$(node_asset_architecture)"
  archive="$work_dir/node-v$NODE_VERSION-linux-$asset_arch.tar.xz"
  archive_root="$work_dir/node-v$NODE_VERSION-linux-$asset_arch"
  curl --fail --location --silent --show-error \
    "https://nodejs.org/dist/v$NODE_VERSION/$(basename "$archive")" \
    --output "$archive"
  printf '%s  %s\n' "$(node_sha256)" "$archive" | sha256sum --check -
  tar --extract --xz --file "$archive" \
    --directory "$work_dir" --no-same-owner --no-same-permissions
  [ "$("$archive_root/bin/node" --version)" = "v$NODE_VERSION" ] || \
    fail "downloaded Node archive contains the wrong node version"
  [ "$(PATH="$archive_root/bin:$PATH" "$archive_root/bin/npm" --version)" = "$NODE_NPM_VERSION" ] || \
    fail "downloaded Node archive contains the wrong npm version"

  run_as_root install -d -m 0755 "$NODE_INSTALL_PATH"
  run_as_root cp -a "$archive_root/." "$NODE_INSTALL_PATH/"
  run_as_root install -d -m 0755 /usr/local/bin
  for executable in node npm npx corepack; do
    [ -e "$NODE_INSTALL_PATH/bin/$executable" ] || continue
    run_as_root ln -sfn "$NODE_INSTALL_PATH/bin/$executable" "/usr/local/bin/$executable"
  done

  receipt_file="$work_dir/node-bootstrap-receipt.json"
  python3 - "$receipt_file" "$(node_sha256)" <<'PY'
import json
import sys

receipt_path, archive_sha256 = sys.argv[1:]
payload = {
    "schema": "agent-canon.node-bootstrap-receipt/v1",
    "status": "pass",
    "archive_sha256": archive_sha256,
    "node_version": "22.14.0",
    "npm_version": "10.9.2",
    "bundled_npm_version": "10.9.2",
    "install_path": "/usr/local/lib/node-v22.14.0",
}
with open(receipt_path, "w", encoding="utf-8") as stream:
    json.dump(payload, stream, sort_keys=True, indent=2)
    stream.write("\n")
PY
  run_as_root install -D -m 0644 "$receipt_file" "$NODE_BOOTSTRAP_RECEIPT"
  trap - RETURN
  rm -rf "$work_dir"
}

install_language_runtime() {
  run_as_root apt-get update
  run_as_root apt-get install -y --no-install-recommends ninja-build

  if ! node_receipt_matches || ! check_node_activation; then
    install_verified_node_archive
  fi
  check_bootstrap
}

install_standalone_base() {
  run_as_root apt-get update
  run_as_root apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-packaging \
    ca-certificates \
    curl \
    gnupg \
    xz-utils \
    ninja-build \
    build-essential
  if ! python3 - <<'PY'
try:
    import tomllib
except ModuleNotFoundError:
    import tomli
PY
  then
    run_as_root apt-get install -y --no-install-recommends python3-tomli
  fi

  install_language_runtime
}

mode="standalone"
if [ "$#" -gt 0 ]; then
  case "$1" in
    --check)
      mode="check"
      ;;
    --install-language-runtime)
      mode="language-runtime"
      ;;
    --install)
      mode="standalone"
      ;;
    *)
      fail "unsupported mode: $1 (use --check, --install-language-runtime, or --install)"
      ;;
  esac
fi

validate_runtime_identity

case "$mode" in
  check)
    check_bootstrap
    ;;
  language-runtime)
    install_language_runtime
    ;;
  standalone)
    install_standalone_base
    ;;
esac
