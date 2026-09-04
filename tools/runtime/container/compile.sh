#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Compiles every source-mounted Rust tool into the external runtime cache.
# upstream design ../../../documents/design/agent-canon-bootstrap-tool-runtime.md source-mounted tool build
# downstream implementation ../../../bootstrap/container/dispatch/tool-wrapper.sh cached tool dispatch
# @dependency-end

set -euo pipefail

source_root=${AGENT_CANON_SOURCE_ROOT:-/opt/agent-canon/source}
cache_root=${AGENT_CANON_CACHE_ROOT:-/var/lib/agent-canon/cache}
cargo_target_dir=${CARGO_TARGET_DIR:-${AGENT_CANON_CARGO_TARGET_DIR:-$cache_root/cargo-target}}
cargo_home=${CARGO_HOME:-$cache_root/cargo}
seed_cargo_home=/usr/local/share/agent-canon/toolchains/cargo

mkdir -p -- "$cache_root" "$cargo_target_dir" "$cargo_home"
if [[ -d "$seed_cargo_home" ]]; then
    cp -R --update=none -- "$seed_cargo_home/." "$cargo_home/"
fi

shopt -s globstar nullglob
manifests=("$source_root"/tools/**/Cargo.toml)
for manifest in "${manifests[@]}"; do
    cargo install \
        --path "${manifest%/Cargo.toml}" \
        --root "$cache_root" \
        --target-dir "$cargo_target_dir" \
        --locked \
        --force \
        --offline
done
