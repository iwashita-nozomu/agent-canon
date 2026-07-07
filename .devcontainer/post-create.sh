#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Runs shared devcontainer post-create setup after workspace mount.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../CONTAINER_OPERATIONS.md container and devcontainer ownership boundary
# upstream design ../documents/rust-agent-tool-migration.md Rust toolchain and CLI install boundary
# upstream design ../documents/tools/lean_proof_env.md Lean proof environment toolchain contract
# upstream environment devcontainer.json postCreateCommand entrypoint
# upstream implementation ../tools/install_llama_cpp.sh builds llama.cpp local LLM tooling
# upstream implementation ../tools/ci/scan_secrets.sh runs dedicated secret scanners
# downstream implementation ../rust/agent-canon/src/structured_analysis.rs builds structured analysis cache DB
# @dependency-end

set -euo pipefail

workspace="${1:-/workspace}"
node_version="${NODE_VERSION:-22.14.0}"
rust_toolchain="${RUST_TOOLCHAIN:-stable}"
lean_toolchain="${AGENT_CANON_LEAN_TOOLCHAIN:-leanprover/lean4:v4.30.0}"
elan_version="${AGENT_CANON_ELAN_VERSION:-v4.2.3}"
elan_x86_64_sha256="${AGENT_CANON_ELAN_X86_64_SHA256:-df0b2b3a439961ffcbb3985214365ffe40f49bc871df04dff268c7d8e21ca8b2}"
elan_aarch64_sha256="${AGENT_CANON_ELAN_AARCH64_SHA256:-cb69af0803b04157bc30201c29c12fca882bb3ad8b43476b8d2d3064810bc3ac}"
tools_home="${AGENT_CANON_TOOLS_HOME:-${HOME}/.tools}"
llama_cpp_ref="${AGENT_CANON_LLAMA_CPP_REF:-master}"
local_llm_model="${AGENT_CANON_LOCAL_LLM_MODEL:-ggml-org/SmolLM3-3B-GGUF:Q4_K_M}"
gitleaks_version="${AGENT_CANON_GITLEAKS_VERSION:-8.30.1}"
trufflehog_version="${AGENT_CANON_TRUFFLEHOG_VERSION:-3.95.3}"
detect_secrets_version="${AGENT_CANON_DETECT_SECRETS_VERSION:-1.5.0}"
playwright_version="${AGENT_CANON_PLAYWRIGHT_VERSION:-1.61.0}"
playwright_browsers_path="${AGENT_CANON_PLAYWRIGHT_BROWSERS_PATH:-/usr/local/share/ms-playwright}"

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return
  fi
  if command -v sudo >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  echo "post-create requires root or sudo for package installation: $*" >&2
  exit 1
}

apt_install() {
  run_as_root apt-get update
  run_as_root apt-get install -y --no-install-recommends "$@"
}

publish_agent_tools_profile() {
  local profile_script

  install -d -m 755 "${tools_home}/bin"
  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export AGENT_CANON_TOOLS_HOME="${tools_home}"
export AGENT_CANON_LOCAL_LLM_MODEL="${local_llm_model}"
export AGENT_CANON_LLAMA_CLI="${tools_home}/bin/llama-cli"
export AGENT_CANON_LLAMA_CPP_CUDA="disabled"
case ":\${PATH}:" in
  *:"${tools_home}/bin":*) ;;
  *) export PATH="${tools_home}/bin:\${PATH}" ;;
esac
EOF
  run_as_root install -m 644 "$profile_script" /etc/profile.d/agent-canon-tools.sh
  rm -f "$profile_script"
  export PATH="${tools_home}/bin:${PATH}"
}

install_node_for_codex() {
  local archive
  if command -v npm >/dev/null 2>&1; then
    return
  fi
  apt_install ca-certificates curl xz-utils
  archive="$(mktemp)"
  curl -fsSL "https://nodejs.org/dist/v${node_version}/node-v${node_version}-linux-x64.tar.xz" \
    -o "$archive"
  run_as_root tar -xJ --strip-components=1 -C /usr/local -f "$archive"
  rm -f "$archive"
}

install_github_cli() {
  local keyring
  if command -v gh >/dev/null 2>&1; then
    return
  fi
  apt_install ca-certificates curl
  keyring="$(mktemp)"
  run_as_root install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o "$keyring"
  run_as_root install -m 644 "$keyring" /etc/apt/keyrings/githubcli-archive-keyring.gpg
  rm -f "$keyring"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' "$(dpkg --print-architecture)" \
    | run_as_root tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  apt_install gh
}

install_codex_cli() {
  if command -v codex >/dev/null 2>&1 && codex --version >/dev/null 2>&1; then
    return
  fi
  install_node_for_codex
  run_as_root env "PATH=${PATH}" npm install -g @openai/codex
  run_as_root env "PATH=${PATH}" npm cache clean --force
  codex --version >/dev/null
}

install_browser_validation_tooling() {
  local profile_script

  install_node_for_codex
  run_as_root install -d -m 755 "$playwright_browsers_path"
  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export PLAYWRIGHT_BROWSERS_PATH="${playwright_browsers_path}"
EOF
  run_as_root install -m 644 "$profile_script" /etc/profile.d/agent-canon-playwright.sh
  rm -f "$profile_script"
  export PLAYWRIGHT_BROWSERS_PATH="$playwright_browsers_path"

  if ! command -v playwright >/dev/null 2>&1 \
    || ! playwright --version | grep -F "Version ${playwright_version}" >/dev/null 2>&1; then
    run_as_root env "PATH=${PATH}" npm install -g "playwright@${playwright_version}"
  fi
  run_as_root env "PATH=${PATH}" "PLAYWRIGHT_BROWSERS_PATH=${PLAYWRIGHT_BROWSERS_PATH}" \
    playwright install --with-deps chromium
  playwright --version
}

install_json_cli_tools() {
  if command -v jq >/dev/null 2>&1; then
    return
  fi
  apt_install jq
}

install_structure_inspection_tools() {
  if command -v tree >/dev/null 2>&1; then
    return
  fi
  apt_install tree
}

install_tex_tooling() {
  if command -v latexmk >/dev/null 2>&1 \
    && command -v pdflatex >/dev/null 2>&1 \
    && command -v xelatex >/dev/null 2>&1 \
    && command -v dvisvgm >/dev/null 2>&1 \
    && command -v pdfcrop >/dev/null 2>&1; then
    return
  fi
  apt_install \
    latexmk \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-pictures \
    texlive-xetex \
    texlive-extra-utils \
    dvisvgm \
    ghostscript \
    poppler-utils
}

elan_linux_asset() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "elan-x86_64-unknown-linux-gnu.tar.gz"
      ;;
    aarch64 | arm64)
      printf '%s\n' "elan-aarch64-unknown-linux-gnu.tar.gz"
      ;;
    *)
      echo "Unsupported elan architecture: $(uname -m)" >&2
      return 1
      ;;
  esac
}

elan_linux_sha256() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "$elan_x86_64_sha256"
      ;;
    aarch64 | arm64)
      printf '%s\n' "$elan_aarch64_sha256"
      ;;
    *)
      echo "Unsupported elan architecture: $(uname -m)" >&2
      return 1
      ;;
  esac
}

install_lean_toolchain() {
  local archive
  local asset
  local checksum
  local profile_script
  local tool
  local work_dir

  export ELAN_HOME="${ELAN_HOME:-${HOME}/.elan}"
  export PATH="${ELAN_HOME}/bin:${PATH}"

  if ! command -v elan >/dev/null 2>&1; then
    apt_install ca-certificates curl
    asset="$(elan_linux_asset)"
    checksum="$(elan_linux_sha256)"
    work_dir="$(mktemp -d)"
    archive="${work_dir}/${asset}"
    curl -fsSL "https://github.com/leanprover/elan/releases/download/${elan_version}/${asset}" \
      -o "$archive"
    printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c -
    tar -xzf "$archive" -C "$work_dir" elan-init
    "${work_dir}/elan-init" -y --default-toolchain "$lean_toolchain" --no-modify-path
    rm -rf "$work_dir"
  fi

  elan toolchain install "$lean_toolchain"
  elan default "$lean_toolchain"

  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export ELAN_HOME="${ELAN_HOME}"
case ":\${PATH}:" in
  *:"${ELAN_HOME}/bin":*) ;;
  *) export PATH="${ELAN_HOME}/bin:\${PATH}" ;;
esac
EOF
  run_as_root install -m 644 "$profile_script" /etc/profile.d/agent-canon-lean.sh
  rm -f "$profile_script"

  for tool in elan lean lake; do
    if [ -x "${ELAN_HOME}/bin/${tool}" ]; then
      run_as_root ln -sf "${ELAN_HOME}/bin/${tool}" "/usr/local/bin/${tool}"
    fi
  done

  elan --version
  lean --version
  lake --version
}

linux_arch() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "amd64"
      ;;
    aarch64 | arm64)
      printf '%s\n' "arm64"
      ;;
    *)
      echo "Unsupported secret scanner architecture: $(uname -m)" >&2
      return 1
      ;;
  esac
}

download_release_asset() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local output="$4"
  curl -fsSL "https://github.com/${repo}/releases/download/${tag}/${asset}" -o "$output"
}

verify_release_checksum() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local archive="$4"
  local checksum_file
  local checksum_asset
  local work_dir

  work_dir="$(dirname "$archive")"
  checksum_file="${work_dir}/checksums.txt"
  checksum_asset="${asset%%_linux_*}_checksums.txt"
  curl -fsSL "https://github.com/${repo}/releases/download/${tag}/${checksum_asset}" \
    -o "$checksum_file"
  if ! grep -F "  $(basename "$archive")" "$checksum_file" >/dev/null 2>&1; then
    echo "Checksum entry for $(basename "$archive") not found in ${repo} ${tag}" >&2
    return 1
  fi
  (cd "$work_dir" && grep -F "  $(basename "$archive")" checksums.txt | sha256sum -c -)
}

install_tar_binary() {
  local repo="$1"
  local tag="$2"
  local asset="$3"
  local binary="$4"
  local archive
  local work_dir

  work_dir="$(mktemp -d)"
  archive="${work_dir}/${asset}"
  download_release_asset "$repo" "$tag" "$asset" "$archive"
  verify_release_checksum "$repo" "$tag" "$asset" "$archive"
  tar -xzf "$archive" -C "$work_dir" "$binary"
  install -d -m 755 "${tools_home}/bin"
  install -m 755 "${work_dir}/${binary}" "${tools_home}/bin/${binary}"
  run_as_root ln -sf "${tools_home}/bin/${binary}" "/usr/local/bin/${binary}"
  rm -rf "$work_dir"
}

install_detect_secrets() {
  local detector

  if command -v detect-secrets >/dev/null 2>&1; then
    return
  fi
  apt_install python3-pip
  PIP_BREAK_SYSTEM_PACKAGES=1 python3 -m pip install --user --upgrade "detect-secrets==${detect_secrets_version}"
  detector="${HOME}/.local/bin/detect-secrets"
  if [ ! -x "$detector" ]; then
    echo "detect-secrets install completed but ${detector} is missing" >&2
    return 1
  fi
  install -d -m 755 "${tools_home}/bin"
  ln -sf "$detector" "${tools_home}/bin/detect-secrets"
  run_as_root ln -sf "${tools_home}/bin/detect-secrets" /usr/local/bin/detect-secrets
}

install_secret_scanners() {
  local arch
  local gitleaks_arch

  apt_install ca-certificates curl tar
  arch="$(linux_arch)"
  if [ "$arch" = "amd64" ]; then
    gitleaks_arch="x64"
  else
    gitleaks_arch="$arch"
  fi

  if ! command -v gitleaks >/dev/null 2>&1; then
    install_tar_binary \
      "gitleaks/gitleaks" \
      "v${gitleaks_version}" \
      "gitleaks_${gitleaks_version}_linux_${gitleaks_arch}.tar.gz" \
      "gitleaks"
  fi
  if ! command -v trufflehog >/dev/null 2>&1; then
    install_tar_binary \
      "trufflesecurity/trufflehog" \
      "v${trufflehog_version}" \
      "trufflehog_${trufflehog_version}_linux_${arch}.tar.gz" \
      "trufflehog"
  fi
  install_detect_secrets

  gitleaks version
  trufflehog --version
  detect-secrets --version
}

agent_canon_source_root() {
  if [ -f "${workspace%/}/vendor/agent-canon/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "${workspace%/}/vendor/agent-canon"
    return
  fi
  if [ -f "${workspace%/}/rust/agent-canon/Cargo.toml" ]; then
    printf '%s\n' "${workspace%/}"
    return
  fi
  printf '%s\n' ""
}

install_rust_toolchain() {
  local profile_script
  local tool

  export CARGO_HOME="${CARGO_HOME:-${HOME}/.cargo}"
  export RUSTUP_HOME="${RUSTUP_HOME:-${HOME}/.rustup}"
  export PATH="${CARGO_HOME}/bin:${PATH}"

  if ! command -v rustup >/dev/null 2>&1; then
    apt_install ca-certificates curl build-essential pkg-config
    curl -fsSL https://sh.rustup.rs \
      | sh -s -- -y --profile minimal --default-toolchain "${rust_toolchain}" --no-modify-path
  fi

  rustup toolchain install "${rust_toolchain}" --profile minimal
  rustup default "${rust_toolchain}"
  rustup component add rustfmt clippy rust-analyzer --toolchain "${rust_toolchain}"

  profile_script="$(mktemp)"
  cat >"$profile_script" <<EOF
export CARGO_HOME="${CARGO_HOME}"
export RUSTUP_HOME="${RUSTUP_HOME}"
case ":\${PATH}:" in
  *:"${CARGO_HOME}/bin":*) ;;
  *) export PATH="${CARGO_HOME}/bin:\${PATH}" ;;
esac
EOF
  run_as_root install -m 644 "$profile_script" /etc/profile.d/agent-canon-rust.sh
  rm -f "$profile_script"

  for tool in cargo rustc rustup rustfmt rust-analyzer cargo-clippy clippy-driver; do
    if [ -x "${CARGO_HOME}/bin/${tool}" ]; then
      run_as_root ln -sf "${CARGO_HOME}/bin/${tool}" "/usr/local/bin/${tool}"
    fi
  done

  cargo --version
  rustc --version
}

install_agent_canon_cli() {
  local canon_root
  local manifest
  local binary

  canon_root="$(agent_canon_source_root)"
  if [ -z "$canon_root" ]; then
    echo "AgentCanon Rust CLI source absent; skipping rust/agent-canon build"
    return
  fi

  install_rust_toolchain
  manifest="${canon_root}/rust/agent-canon/Cargo.toml"
  cargo build --release --manifest-path "$manifest"
  binary="${canon_root}/rust/agent-canon/target/release/agent-canon"

  install -d -m 755 "${tools_home}/agent-canon/bin" "${tools_home}/bin"
  install -m 755 "$binary" "${tools_home}/agent-canon/bin/agent-canon"
  ln -sf "${tools_home}/agent-canon/bin/agent-canon" "${tools_home}/bin/agent-canon"
  run_as_root ln -sf "${tools_home}/bin/agent-canon" /usr/local/bin/agent-canon
  /usr/local/bin/agent-canon --version
}

install_llama_cpp() {
  local canon_root
  local installer

  apt_install ca-certificates curl git cmake build-essential pkg-config libcurl4-openssl-dev libssl-dev
  canon_root="$(agent_canon_source_root)"
  installer="${canon_root}/tools/install_llama_cpp.sh"
  if [ -z "$canon_root" ] || [ ! -f "$installer" ]; then
    echo "AgentCanon llama.cpp installer absent; skipping local LLM tool install"
    return
  fi
  AGENT_CANON_TOOLS_HOME="$tools_home" \
    AGENT_CANON_LLAMA_CPP_REF="$llama_cpp_ref" \
    AGENT_CANON_LLAMA_CPP_CUDA=disabled \
    bash "$installer" --allow-fetch
}

build_structured_analysis_cache() {
  local canon_root

  canon_root="$(agent_canon_source_root)"
  if [ -z "$canon_root" ]; then
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP=warn"
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP_REASON=agent-canon-source-absent"
    return
  fi
  if ! command -v agent-canon >/dev/null 2>&1; then
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP=warn"
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP_REASON=agent-canon-cli-absent"
    return
  fi
  if ! agent-canon structured-analysis build --root "$workspace" --profile devcontainer; then
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP=warn"
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP_REASON=build-failed"
    echo "STRUCTURED_ANALYSIS_BOOTSTRAP_NEXT_COMMAND=agent-canon structured-analysis build --root \"${workspace}\" --profile devcontainer"
    return
  fi
  echo "STRUCTURED_ANALYSIS_BOOTSTRAP=pass"
}

publish_agent_tools_profile
if [ -f "${workspace%/}/docker/register_safe_directories.sh" ]; then
  bash "${workspace%/}/docker/register_safe_directories.sh" "$workspace"
else
  git config --global --add safe.directory "$workspace" || true
  if [ -d "${workspace%/}/.git" ]; then
    git config --global --add safe.directory "${workspace%/}/.git" || true
  fi
fi
if [ -f "${workspace%/}/docker/install_python_dependencies.sh" ]; then
  bash "${workspace%/}/docker/install_python_dependencies.sh" "$workspace"
else
  echo "repo-local Python dependency installer absent; skipping docker/install_python_dependencies.sh"
fi
install_github_cli
install_codex_cli
install_browser_validation_tooling
install_json_cli_tools
install_structure_inspection_tools
install_tex_tooling
install_lean_toolchain
install_secret_scanners
install_agent_canon_cli
install_llama_cpp
build_structured_analysis_cache
jq --version
tree --version
latexmk --version | sed -n '1p'
pdflatex --version | sed -n '1p'
xelatex --version | sed -n '1p'
dvisvgm --version | sed -n '1p'
pdfcrop --version | sed -n '1p'
elan --version
lean --version
lake --version
gh --version
codex --version
playwright --version
