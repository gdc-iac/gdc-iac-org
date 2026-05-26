#!/usr/bin/env bash
# setup-operator-sa.sh
# Case-scoped wrapper for 006 operator SA setup.

export TEST_CASE_NO="006"
export VERIFY_RBAC="create deployments"
export HELM_SELECTOR="tier=workload"

source ../000-SETUP/setup-operator-base.sh
