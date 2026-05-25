#!/usr/bin/env bash
# @dependency-start
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
CUDA_MODE="${AGENT_CANON_LLAMA_CPP_CUDA:-auto}"
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

cuda_toolkit_available() {
  command -v nvcc >/dev/null 2>&1 || [ -x /usr/local/cuda/bin/nvcc ]
}

cuda_device_visible() {
  [ -e /dev/nvidia0 ] && return 0
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

cuda_driver_library_dir() {
  if [ -n "${AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR:-}" ]; then
    if [ -e "${AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR}/libcuda.so.1" ] \
      || [ -e "${AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR}/libcuda.so" ]; then
      printf '%s\n' "$AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR"
      return 0
    fi
    return 1
  fi
  if command -v ldconfig >/dev/null 2>&1; then
    local ldconfig_path
    ldconfig_path="$(
      ldconfig -p 2>/dev/null \
        | awk '/libcuda\.so\.1/{print $NF; exit} /libcuda\.so[[:space:]]/{print $NF; exit}'
    )"
    if [ -n "$ldconfig_path" ]; then
      dirname "$ldconfig_path"
      return 0
    fi
  fi
  local candidate
  for candidate in \
    /usr/local/cuda/compat/libcuda.so.1 \
    /usr/local/cuda-*/compat/libcuda.so.1 \
    /usr/lib/wsl/lib/libcuda.so.1 \
    /usr/lib/x86_64-linux-gnu/libcuda.so.1; do
    if [ -e "$candidate" ]; then
      dirname "$candidate"
      return 0
    fi
  done
  return 1
}

cuda_driver_library_available() {
  cuda_driver_library_dir >/dev/null 2>&1
}

resolve_cuda_backend() {
  case "$CUDA_MODE" in
    1 | true | TRUE | on | ON | yes | YES | cuda | CUDA)
      if ! cuda_toolkit_available; then
        echo "AGENT_CANON_LLAMA_CPP=fail"
        echo "AGENT_CANON_LLAMA_CPP_ERROR=missing_cuda_toolkit"
        exit 2
      fi
      if ! cuda_driver_library_available; then
        echo "AGENT_CANON_LLAMA_CPP=fail"
        echo "AGENT_CANON_LLAMA_CPP_ERROR=missing_cuda_driver_library"
        exit 2
      fi
      printf '%s\n' enabled
      return
      ;;
    0 | false | FALSE | off | OFF | no | NO | disabled)
      printf '%s\n' disabled
      return
      ;;
    auto | "")
      if cuda_toolkit_available && cuda_device_visible && cuda_driver_library_available; then
        printf '%s\n' enabled
      elif cuda_device_visible; then
        if cuda_toolkit_available; then
          printf '%s\n' auto_disabled_missing_cuda_driver
        else
          printf '%s\n' auto_disabled_missing_nvcc
        fi
      else
        printf '%s\n' auto_disabled_no_gpu
      fi
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

main() {
  local source_dir
  local build_dir
  local install_dir
  local source_newer
  local jobs
  local cuda_backend
  local cuda_driver_dir
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
  if [ "$cuda_backend" = "enabled" ]; then
    cuda_driver_dir="$(cuda_driver_library_dir)"
    export LIBRARY_PATH="${cuda_driver_dir}${LIBRARY_PATH:+:${LIBRARY_PATH}}"
    export LD_LIBRARY_PATH="${cuda_driver_dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    cmake_args+=(-DGGML_CUDA=ON)
    cmake_args+=("-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,${cuda_driver_dir} -Wl,-rpath,${cuda_driver_dir}")
  else
    cuda_driver_dir=""
    cmake_args+=(-DGGML_CUDA=OFF)
  fi
  if [ -n "$CMAKE_EXTRA_ARGS" ]; then
    read -r -a extra_args <<<"$CMAKE_EXTRA_ARGS"
    cmake_args+=("${extra_args[@]}")
  fi
  jobs="$(resolve_build_jobs)"
  build_config_path="$build_dir/agent-canon-build-config.txt"
  build_config="$(
    printf 'cuda_backend=%s\n' "$cuda_backend"
    printf 'cuda_driver_dir=%s\n' "$cuda_driver_dir"
    printf 'cmake_args=%s\n' "${cmake_args[*]}"
  )"
  echo "AGENT_CANON_LLAMA_CPP_CUDA=$cuda_backend"
  if [ "$cuda_backend" = "enabled" ]; then
    echo "AGENT_CANON_LLAMA_CPP_CUDA_DRIVER_LIB_DIR=$cuda_driver_dir"
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
