#!/usr/bin/env bash
# setup-customer-sa.sh
# Case-scoped wrapper for 006 customer SA setup.

export TEST_CASE_NO="006"
export VERIFY_RBAC="create deployments"

source ../000-SETUP/setup-customer-base.sh
