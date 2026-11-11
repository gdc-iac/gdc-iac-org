#!/usr/bin/env bash
# setup-operator-sa.sh
# Case-scoped wrapper for 002 operator SA setup.

export TEST_CASE_NO="002"
export VERIFY_RBAC="get secrets"
export HELM_SELECTOR="tier!=iperf3"

source ../../000-SETUP/setup-operator-base.sh
