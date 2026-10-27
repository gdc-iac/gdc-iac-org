#!/usr/bin/env bash
# setup-customer-sa.sh
# Case-scoped wrapper for 003 customer/tenant SA setup.

export TEST_CASE_NO="003"
export VERIFY_RBAC="get virtualmachines"

source ../../000-SETUP/setup-customer-base.sh
