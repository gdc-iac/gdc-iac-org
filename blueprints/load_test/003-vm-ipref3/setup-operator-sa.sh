#!/usr/bin/env bash
# setup-operator-sa.sh
# Case-scoped wrapper for 003 operator SA setup.

export TEST_CASE_NO="003"
export VERIFY_RBAC="get secrets"
export HELM_SELECTOR="tier!=vm"

source ../../000-SETUP/setup-operator-base.sh
