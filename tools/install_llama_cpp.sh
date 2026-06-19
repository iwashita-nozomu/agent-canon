#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Builds and exposes llama.cpp for AgentCanon local LLM tools.
# upstream design ../CONTAINER_OPERATIONS.md compiled tool cache and devcontainer boundary.
# upstream design ../documents/local-llm-responsibility-analysis.md local LLM single-file policy.
# downstream environment ../.devcontainer/post-create.sh installs llama.cpp after workspace mount.
# downstream implementation ./rebuild_agent_tools.sh rebuilds llama.cpp after AgentCanon updates.
# downstream implementation ../tests/tools/test_install_llama_cpp.py validates installer behavior.
# @dependency-end

set -euo pipefail

TOOLS_HOME="${AGENT_CANON_TOOLS_HOME:-${HOME}/.tools}"
LLAMA_CPP_REF="${AGENT_CANON_LLAMA_CPP_REF:-master}"
FORCE_REBUILD="${AGENT_CANON_REBUILD_LLAMA_CPP:-0}"
CUDA_MODE="${AGENT_CANON_LLAMA_CPP_CUDA:-disabled}"
CMAKE_EXTRA_ARGS="${AGENT_CANON_LLAMA_CPP_CMAKE_ARGS:-}"
BUILD_JOBS="${AGENT_CANON_LLAMA_CPP_BUILD_JOBS:-}"
ALLOW_FETCH=0
SKIP_MISSING_SOURCE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --allow-fetch)
      ALLOW_FETCH=1
      shift
      ;;
    --skip-missing-source)
      SKIP_MISSING_SOURCE=1
      shift
      ;;
    --force)
      FORCE_REBUILD=1
      shift
      ;;
    *)
      echo "AGENT_CANON_LLAMA_CPP=fail"
      echo "AGENT_CANON_LLAMA_CPP_ERROR=unknown_argument:$1"
      exit 2
      ;;
  esac
done

missing_build_tool() {
  local tool
  for tool in git cmake; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "AGENT_CANON_LLAMA_CPP=skipped_missing_dependency"
      echo "AGENT_CANON_LLAMA_CPP_MISSING=$tool"
      return 0
    fi
  done
  return 1
}

llama_sources_newer_than_binary() {
  local source_dir="$1"
  local binary="$2"
  if [ ! -x "$binary" ]; then
    return 0
  fi
  find "$source_dir" \
    \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hpp' -o -name 'CMakeLists.txt' \) \
    -newer "$binary" -print -quit
}

llama_build_config_matches() {
  local config_path="$1"
  local expected_config="$2"
  [ -f "$config_path" ] || return 1
  [ "$(cat "$config_path")" = "$expected_config" ]
}

resolve_cuda_backend() {
  case "$CUDA_MODE" in
    1 | true | TRUE | on | ON | yes | YES | cuda | CUDA)
      printf '%s\n' disabled
      return
      ;;
    0 | false | FALSE | off | OFF | no | NO | disabled | cpu | CPU)
      printf '%s\n' disabled
      return
      ;;
    auto | "")
      printf '%s\n' disabled
      return
      ;;
    *)
      echo "AGENT_CANON_LLAMA_CPP=fail"
      echo "AGENT_CANON_LLAMA_CPP_ERROR=invalid_cuda_mode:$CUDA_MODE"
      exit 2
      ;;
  esac
}

resolve_build_jobs() {
  if [ -n "$BUILD_JOBS" ]; then
    case "$BUILD_JOBS" in
      *[!0-9]* | 0)
        echo "AGENT_CANON_LLAMA_CPP=fail"
        echo "AGENT_CANON_LLAMA_CPP_ERROR=invalid_build_jobs:$BUILD_JOBS"
        exit 2
        ;;
      *)
        printf '%s\n' "$BUILD_JOBS"
        return
        ;;
    esac
  fi
  nproc 2>/dev/null || printf '%s\n' 2
}

reject_accelerator_cmake_arg() {
  local arg="$1"
  local key
  local value
  local normalized_key
  local normalized_value
  case "$arg" in
    -D*=*)
      key="${arg#-D}"
      key="${key%%=*}"
      value="${arg#*=}"
      normalized_key="${key%%:*}"
      normalized_value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
      ;;
    *)
      return
      ;;
  esac
  case "$normalized_key" in
    GGML_CUDA | GGML_CUBLAS | LLAMA_CUBLAS | LLAMA_CUDA | GGML_METAL | GGML_HIP | GGML_VULKAN | GGML_SYCL | GGML_CANN | GGML_OPENCL)
      ;;
    *)
      return
      ;;
  esac
  case "$normalized_value" in
    1 | on | true | yes)
      echo "AGENT_CANON_LLAMA_CPP=fail"
      echo "AGENT_CANON_LLAMA_CPP_ERROR=cpu_only_policy_rejects_cmake_arg:$arg"
      exit 2
      ;;
  esac
}

main() {
  local source_dir
  local build_dir
  local install_dir
  local source_newer
  local jobs
  local cuda_backend
  local build_config
  local build_config_path
  local -a cmake_args
  local -a extra_args

  echo "AGENT_CANON_LLAMA_CPP_TOOLS_HOME=$TOOLS_HOME"
  echo "AGENT_CANON_LLAMA_CPP_REF=$LLAMA_CPP_REF"
  if missing_build_tool; then
    return 0
  fi

  source_dir="${TOOLS_HOME}/src/llama.cpp"
  build_dir="${TOOLS_HOME}/build/llama.cpp"
  install_dir="${TOOLS_HOME}/bin"
  install -d -m 755 "${TOOLS_HOME}/src" "${TOOLS_HOME}/build" "$install_dir"

  if [ ! -d "${source_dir}/.git" ]; then
    if [ "$ALLOW_FETCH" != "1" ] || [ "$SKIP_MISSING_SOURCE" = "1" ]; then
      echo "AGENT_CANON_LLAMA_CPP=skipped_missing_source"
      echo "AGENT_CANON_LLAMA_CPP_NEXT=run_devcontainer_post_create_or_set_AGENT_CANON_LLAMA_CPP_ALLOW_FETCH"
      return 0
    fi
    git clone --depth 1 --branch "$LLAMA_CPP_REF" https://github.com/ggml-org/llama.cpp.git "$source_dir"
  elif [ "$ALLOW_FETCH" = "1" ]; then
    git -C "$source_dir" fetch --depth 1 origin "$LLAMA_CPP_REF"
    git -C "$source_dir" checkout --detach FETCH_HEAD
  fi

  cmake_args=(-DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=ON)
  cuda_backend="$(resolve_cuda_backend)"
  cmake_args+=(-DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_HIP=OFF -DGGML_VULKAN=OFF -DGGML_SYCL=OFF)
  if [ -n "$CMAKE_EXTRA_ARGS" ]; then
    read -r -a extra_args <<<"$CMAKE_EXTRA_ARGS"
    for arg in "${extra_args[@]}"; do
      reject_accelerator_cmake_arg "$arg"
    done
    cmake_args+=("${extra_args[@]}")
  fi
  jobs="$(resolve_build_jobs)"
  build_config_path="$build_dir/agent-canon-build-config.txt"
  build_config="$(
    printf 'cuda_backend=%s\n' "$cuda_backend"
    printf 'cmake_args=%s\n' "${cmake_args[*]}"
  )"
  echo "AGENT_CANON_LLAMA_CPP_CUDA=$cuda_backend"
  echo "AGENT_CANON_LLAMA_CPP_ACCELERATOR_POLICY=cpu_only"
  if [ "$CUDA_MODE" != "disabled" ] && [ "$CUDA_MODE" != "0" ] && [ "$CUDA_MODE" != "false" ] && [ "$CUDA_MODE" != "FALSE" ] && [ "$CUDA_MODE" != "off" ] && [ "$CUDA_MODE" != "OFF" ] && [ "$CUDA_MODE" != "no" ] && [ "$CUDA_MODE" != "NO" ] && [ "$CUDA_MODE" != "cpu" ] && [ "$CUDA_MODE" != "CPU" ]; then
    echo "AGENT_CANON_LLAMA_CPP_CUDA_REQUESTED=$CUDA_MODE"
    echo "AGENT_CANON_LLAMA_CPP_CUDA_REQUEST_POLICY=ignored_cpu_only"
  fi
  echo "AGENT_CANON_LLAMA_CPP_CMAKE_ARGS=${cmake_args[*]}"
  echo "AGENT_CANON_LLAMA_CPP_BUILD_JOBS=$jobs"

  source_newer="$(llama_sources_newer_than_binary "$source_dir" "${install_dir}/llama-cli")"
  if [ "$FORCE_REBUILD" != "1" ] \
    && [ -x "${install_dir}/llama-cli" ] \
    && [ -x "${install_dir}/llama-server" ] \
    && [ -z "$source_newer" ] \
    && llama_build_config_matches "$build_config_path" "$build_config"; then
    "${install_dir}/llama-cli" --help >/dev/null
    echo "AGENT_CANON_LLAMA_CPP=already_current"
    return 0
  fi

  cmake -S "$source_dir" -B "$build_dir" "${cmake_args[@]}"
  cmake --build "$build_dir" --config Release -j "$jobs" --target llama-cli llama-server
  printf '%s\n' "$build_config" >"$build_config_path"
  ln -sf "${build_dir}/bin/llama-cli" "${install_dir}/llama-cli"
  ln -sf "${build_dir}/bin/llama-server" "${install_dir}/llama-server"
  "${install_dir}/llama-cli" --help >/dev/null
  echo "AGENT_CANON_LLAMA_CPP=rebuilt"
}

main "$@"
