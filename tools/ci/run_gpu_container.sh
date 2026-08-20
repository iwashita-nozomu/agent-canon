#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs one Docker GPU container through the sole --gpus all injection route.
# upstream design ../../documents/experiments/gpu-direct-command.md full UUID admission and Docker injection contract
# upstream design ../../agents/skills/gpu-execution.md operator route and JAX GPU acceptance
# downstream implementation ../../tests/tools/test_run_gpu_container.py command and failure regression tests
# @dependency-end

set -euo pipefail

readonly GPU_ENV_NAMES=(
  CUDA_VISIBLE_DEVICES
  NVIDIA_VISIBLE_DEVICES
  JAX_PLATFORMS
  XLA_PYTHON_CLIENT_PREALLOCATE
  XLA_PYTHON_CLIENT_ALLOCATOR
  XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR
)

fail() {
  printf 'GPU_CONTAINER_ERROR=%s\n' "$1" >&2
  exit 2
}

usage() {
  printf '%s\n' \
    'usage: run_gpu_container.sh --image IMAGE --gpus all [--name NAME] -- COMMAND [ARG...]'
}

image=''
gpus=''
container_name=''
while (($#)); do
  case "$1" in
    --image)
      (($# >= 2)) || fail 'image_value_missing'
      image="$2"
      shift 2
      ;;
    --gpus)
      (($# >= 2)) || fail 'gpus_value_missing'
      gpus="$2"
      shift 2
      ;;
    --name)
      (($# >= 2)) || fail 'name_value_missing'
      container_name="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown_argument:$1"
      ;;
  esac
done

[[ -n "$image" ]] || fail 'image_required'
[[ "$gpus" == 'all' ]] || fail 'gpus_must_be_all'
(($# > 0)) || fail 'command_required'
command -v docker >/dev/null 2>&1 || fail 'docker_unavailable'

for name in "${GPU_ENV_NAMES[@]}"; do
  [[ -n "${!name-}" ]] || fail "environment_missing:$name"
  [[ "${!name}" != *$'\n'* && "${!name}" != *$'\r'* ]] || \
    fail "environment_invalid:$name"
done

[[ "$CUDA_VISIBLE_DEVICES" == "$NVIDIA_VISIBLE_DEVICES" ]] || \
  fail 'visibility_mismatch'
[[ "$JAX_PLATFORMS" == 'cuda' ]] || fail 'jax_platform_must_be_cuda'
[[ "$XLA_PYTHON_CLIENT_PREALLOCATE" == 'false' ]] || \
  fail 'xla_preallocate_must_be_false'
[[ "$XLA_PYTHON_CLIENT_ALLOCATOR" == 'platform' ]] || \
  fail 'xla_allocator_must_be_platform'
[[ "$XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR" == 'false' ]] || \
  fail 'xla_host_allocator_must_be_false'

IFS=',' read -r -a selected_gpu_ids <<<"$CUDA_VISIBLE_DEVICES"
((${#selected_gpu_ids[@]} > 0)) || fail 'visibility_empty'
for gpu_id in "${selected_gpu_ids[@]}"; do
  [[ "$gpu_id" =~ ^(GPU|MIG)-[A-Za-z0-9-]+$ ]] || \
    fail "visibility_identity_invalid:$gpu_id"
done

docker_command=(docker run --rm --gpus all)
if [[ -n "$container_name" ]]; then
  docker_command+=(--name "$container_name")
fi
for name in "${GPU_ENV_NAMES[@]}"; do
  docker_command+=(-e "$name=${!name}")
done
docker_command+=("$image" "$@")

exec "${docker_command[@]}"
