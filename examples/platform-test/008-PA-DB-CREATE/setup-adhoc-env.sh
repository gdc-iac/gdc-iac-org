#!/usr/bin/env bash
# setup-adhoc-env.sh for 008-PA-DB-CREATE Database Provisioning
# Day-0 Elevated Bootstrapper to configure BackupRepository and setup Runner credentials

set -e

# Export test-specific config
export TEST_CASE_NO="008"
export VERIFY_RBAC="create dbclusters.postgresql.dbadmin.gdc.goog"
export IAC_PROJECT=${IAC_PROJECT:-"iac-root"}
export ORG_NAME=${ORG_NAME:-"org-1"}

# Determine Admin Cluster Context
ADMIN_CONTEXT=${ADMIN_CLUSTER_CONTEXT:-"${ORG_NAME}-admin-zone1-gdch_console-${ORG_NAME}-zone1-google-gdch-test_${ORG_NAME}-admin"}

echo "=============================================================================="
# Day-0 Bootstrap: Create physical GDC BackupRepository
echo "🏗️  [BOOTSTRAP] Setting up GDC BackupRepository on Admin context: $ADMIN_CONTEXT"
echo "=============================================================================="

# 1. Create namespace and secret for mock S3 backups
kubectl --context "$ADMIN_CONTEXT" create namespace ioc-test-infra 2>/dev/null || true
kubectl --context "$ADMIN_CONTEXT" create secret generic s3-backup-secret \
  -n ioc-test-infra \
  --from-literal=access-key-id="admin" \
  --from-literal=access-key="password" \
  --dry-run=client -o yaml | kubectl --context "$ADMIN_CONTEXT" apply -f -

# 2. Create GDC BackupRepository resource
cat <<EOF | kubectl --context "$ADMIN_CONTEXT" apply -f -
apiVersion: backup.gdc.goog/v1
kind: BackupRepository
metadata:
  name: dbs-backup-repository
spec:
  secretReference:
    namespace: ioc-test-infra
    name: s3-backup-secret
  endpoint: "http://s3.local"
  type: "S3"
  s3Options:
    bucket: "dbs-backups"
    region: "zone1"
    forcePathStyle: true
  importPolicy: "ReadWrite"
EOF

echo "✅ [BOOTSTRAP] BackupRepository created successfully."
echo ""

# Day-1 Setup: Launch central logical setup base to build contexts & identities
../000-SETUP/setup-customer-base.sh
