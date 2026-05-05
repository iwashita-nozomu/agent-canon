#!/usr/bin/env bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
username="niwashita"

git config user.name "${username}"
git config user.email "${username}@users.noreply.github.com"

git config init.defaultBranch main