#!/usr/bin/env bash
export TEST_CASE_NO="008"
export VERIFY_RBAC="create dbclusters.postgresql.dbadmin.gdc.goog"
export HELM_SELECTOR="tier=database"

source ../000-SETUP/setup-operator-base.sh
