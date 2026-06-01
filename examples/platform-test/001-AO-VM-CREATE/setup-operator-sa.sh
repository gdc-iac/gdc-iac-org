#!/usr/bin/env bash
export TEST_CASE_NO="001"
export VERIFY_RBAC="get secrets"
export HELM_SELECTOR="tier!=subnets"

source ../000-SETUP/setup-operator-base.sh
