#!/usr/bin/env bash
# setup-tenant-sa.sh
# Case-scoped wrapper for 002 customer/tenant SA setup.

export TEST_CASE_NO="002"
export VERIFY_RBAC="get secrets"

source ../../000-SETUP/setup-customer-base.sh
