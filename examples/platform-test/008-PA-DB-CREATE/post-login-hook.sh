#!/usr/bin/env bash
# post-login-hook.sh for 008-PA-DB-CREATE
# Day-0 elevated BackupRepository bootstrapping

# ==============================================================================
# GDC ARCHITECTURAL NOTE & DECOUPLING ACKNOWLEDGMENT
# ==============================================================================
# While declaring the BackupRepository and mock S3 Secret inside the user-facing
# declarative Helmfile orchestrator is highly desirable from a pure GitOps standpoint,
# GDC's platform security model and resource controllers enforce a strict separation
# of concerns that makes this approach impossible to install natively via Helm:
#
# 1. GDC Topological Security Boundary (RBAC Block):
#    The BackupRepository is a cluster-scoped infrastructure resource. GDC's RBAC
#    model strictly forbids namespaced logical project users (like fop-iac@example.com)
#    from creating or managing cluster-scoped backup assets. Only elevated GDC
#    Infrastructure Operators (running under cluster-admin contexts) are authorized.
#
# 2. API Webhook Deadlock:
#    When the Secret and BackupRepository are submitted together inside the same Helm
#    release, GDC's validating admission webhook intercepts the BackupRepository creation
#    and attempts to synchronously connect to the S3 endpoint using credentials from the
#    secret. Because the secret has not been fully committed to etcd yet, the webhook
#    blocks, hanging Helm's HTTP socket connection indefinitely.
#
# Concession:
#    To achieve a fully working, 100% automated GDC database cluster provisioning test
#    suite, we gracefully decouple this dependency. The physical cluster-scoped
#    BackupRepository is provisioned out-of-band during this elevated Platform Setup
#    phase (post-login hook), allowing the restricted workload Helmfile to successfully
#    deploy the namespaced database cluster on the first try.
# ==============================================================================

# Determine Admin Cluster Context
ADMIN_CONTEXT=${ADMIN_CLUSTER_CONTEXT:-"${ORG_NAME}-admin-${ZONE_NAME}-gdch_console-${ORG_NAME}-${ZONE_NAME}-${DOMAIN_SUFFIX_CONTEXT}_${ORG_NAME}-admin"}

echo "🏗️  [HOOK] Setting up GDC BackupRepository on Admin context: $ADMIN_CONTEXT"

# Create namespace and secret for mock S3 backups
kubectl --context "$ADMIN_CONTEXT" create namespace ioc-test-infra 2>/dev/null || true
kubectl --context "$ADMIN_CONTEXT" create secret generic s3-backup-secret \
  -n ioc-test-infra \
  --from-literal=access-key-id="admin" \
  --from-literal=access-key="password" \
  --dry-run=client -o yaml | kubectl --context "$ADMIN_CONTEXT" apply -f -

# Create GDC BackupRepository resource
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
# 1. Create custom namespaced Role allowing GET and LIST on Secrets inside ioc-test-infra
# (Required because standard 'view' ClusterRole explicitly excludes read access to secrets)
cat <<EOF | kubectl --context "$ADMIN_CONTEXT" apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: test-infra-secret-reader
  namespace: ioc-test-infra
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list"]
EOF

# 2. Bind OIDC User to the custom Secret Reader Role
# (Required so OIDC terminal context can successfully verify s3-backup-secret status in helmfile hook!)
echo "🔑 Granting namespaced secret-read access in ioc-test-infra to $IAC_USER_EMAIL..."
kubectl --context "$ADMIN_CONTEXT" create rolebinding test-user-008-infra-secret-reader \
  -n ioc-test-infra \
  --role=test-infra-secret-reader \
  --user="$IAC_USER_EMAIL" 2>/dev/null || true

echo "✅ [HOOK] BackupRepository and User RoleBindings registered successfully."
