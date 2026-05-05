#!/usr/bin/env bash
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
username="niwashita"

git config user.name "${username}"
git config user.email "${username}@users.noreply.github.com"

git config init.defaultBranch main