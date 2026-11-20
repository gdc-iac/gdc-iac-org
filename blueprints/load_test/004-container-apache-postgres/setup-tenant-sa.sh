#!/bin/bash
# setup-tenant-sa.sh
#
# ==============================================================================
# 📖 TL;DR / OVERVIEW
# ==============================================================================
# This script bootstraps the GDC-native, non-interactive GitOps/IaC execution flow
# for the 004-CONTAINER-APACHE-POSTGRES test case.
#
# 🔒 TENANT BOUNDARY SCOPE (GDC-NATIVE / SINGLE-CLUSTER LITE FLOW):
#    This script is optimized for Customer GDC Administrators (Tenants) operating
#    within their standard Org sandboxes. It makes two key assumptions:
#      1. The GDC platform services (AIS identity sync, Logical Project replication)
#         are stable and fully operational.
#      2. You do NOT possess K8s-native cluster-admin access to physical Admin/User clusters.
#
#    Instead of using low-level physical cluster-admin hacks, this flow strictly
#    deploys GDC-native IAM bindings (tenant-bootstrap.yaml) on the Global API Cluster.
#    GDC's background propagation service then securely replicates these permissions 
#    down to the regional workload namespaces.
# ==============================================================================

set -e

# --- Configuration & Context Defaults ---
ORG_NAME="org-1"
IAC_PROJECT="iac-root"
GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-org-1-zone1-google-gdch-test_global-api"}

CERT_DIR="./.certs"
KUBECONFIG_SA="./.kubeconfig-sa"

CONSOLE_HOST=${CONSOLE_HOST:-"console.org-1.zone1.google.gdch.test"}
AIS_HOST=${AIS_HOST:-"ais-core.org-1.zone1.google.gdch.test"}
KMS_HOST=${KMS_HOST:-"kms.org-1.zone1.google.gdch.test"}

echo "======================================================="
echo "🛡️  GDC Tenant-Scoped Service Account Bootstrapper (Web + DB)"
echo "======================================================="

# ==============================================================================
# [STEP 1] OPTIONAL LOCAL CERTIFICATE TRUST STORE SETUP
# ==============================================================================
if [ "${UPDATE_CERTS}" = "true" ]; then
    echo "🔒 [STEP 1] Fetching and updating certificates for local trust store..."
    mkdir -p "$CERT_DIR"
    openssl s_client -showcerts -connect "${CONSOLE_HOST}:443" </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"
    openssl s_client -showcerts -connect "${AIS_HOST}:443" </dev/null | openssl x509 -outform PEM >  "${CERT_DIR}/ais-core.crt"
    openssl s_client -showcerts -connect "${KMS_HOST}:443" </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-kms.crt"
    
    echo "Adding KMS & AIS certs to trust store (requires sudo)..."
    sudo cp ${CERT_DIR}/* /usr/local/share/ca-certificates/
    sudo update-ca-certificates
    echo "✅ Trust store updated!"
fi

# ==============================================================================
# [STEP 2] TENANT ADMIN ACCESS VERIFICATION & CONDITIONAL LOGIN
# ==============================================================================
echo "🔍 [STEP 2] Checking current context permissions..."
CAN_CREATE_SA=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create serviceaccounts -n "$IAC_PROJECT" 2>/dev/null || echo "no")
CAN_CREATE_RB=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create iamrolebindings.iam.global.gdc.goog -n platform 2>/dev/null || echo "no")

if [ "$CAN_CREATE_SA" != "yes" ] || [ "$CAN_CREATE_RB" != "yes" ]; then
    echo "⚠️  Current context does not have sufficient GDC Tenant Admin & Delegation privileges."
    echo "👤 Requesting Tenant Admin authentication..."
    echo "-------------------------------------------------------"
    
    if [ ! -f "${CERT_DIR}/gdc-console.crt" ]; then
        echo "📥 Fetching console certificate for authentication..."
        mkdir -p "$CERT_DIR"
        openssl s_client -showcerts -connect "${CONSOLE_HOST}:443" </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"
    fi
    
    gdcloud auth login --login-config-cert "${CERT_DIR}/gdc-console.crt"
    
    CAN_CREATE_SA_AFTER=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create serviceaccounts -n "$IAC_PROJECT" 2>/dev/null || echo "no")
    CAN_CREATE_RB_AFTER=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create iamrolebindings.iam.global.gdc.goog -n platform 2>/dev/null || echo "no")
    
    if [ "$CAN_CREATE_SA_AFTER" != "yes" ] || [ "$CAN_CREATE_RB_AFTER" != "yes" ]; then
        echo "❌ Authentication failed or identity lacks privileges to bootstrap Service Accounts."
        exit 1
    fi
    echo "✅ Authenticated successfully as Tenant Admin!"
else
    echo "✅ Active context has sufficient Tenant Admin and delegation privileges. Skipping OIDC login."
fi

# ==============================================================================
# [STEP 3] APPLY DECLARATIVE GDC-NATIVE RESOURCES
# ==============================================================================
echo "📦 [STEP 3] Applying GDC-Native ServiceAccounts & IAMRoleBindings to Global API Cluster..."
kubectl --context "$GLOBAL_CONTEXT" apply -f tenant-bootstrap.yaml

echo "⏳ Waiting for GDC secrets and roles to initialize (10s)..."
sleep 10

# ==============================================================================
# [STEP 4] EXTRACT GDC SERVICE ACCOUNT JWT TOKENS
# ==============================================================================
echo "🔑 [STEP 4] Retrieving ServiceAccount tokens..."
PLATFORM_BOOTSTRAP_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

if [ -z "$PLATFORM_BOOTSTRAP_TOKEN" ] || [ -z "$TEST_RUNNER_TOKEN" ]; then
    echo "❌ Failed to retrieve ServiceAccount tokens from Global API. Ensure tenant-bootstrap.yaml is deployed successfully."
    exit 1
fi

echo "✅ Tokens retrieved successfully!"

# ==============================================================================
# [STEP 5] GENERATE CLIENT-SIDE 2-CONTEXT KUBECONFIG
# ==============================================================================
echo "💾 [STEP 5] Generating tenant-scoped Kubeconfig at '$KUBECONFIG_SA'..."
rm -f "$KUBECONFIG_SA"

APISERVER=$(kubectl config view --minify --context="$GLOBAL_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}')

# Map cluster endpoint
kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster tenant-gdc-cluster \
    --server="$APISERVER" \
    --insecure-skip-tls-verify=true

# Inject decrypted tokens
kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials tenant-bootstrap-sa \
    --token="$PLATFORM_BOOTSTRAP_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials tenant-runner-sa \
    --token="$TEST_RUNNER_TOKEN"

# Configure logical contexts
kubectl config --kubeconfig="$KUBECONFIG_SA" set-context bootstrap-context \
    --cluster=tenant-gdc-cluster \
    --user=tenant-bootstrap-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context runner-context \
    --cluster=tenant-gdc-cluster \
    --user=tenant-runner-sa \
    --namespace="$IAC_PROJECT"

echo "✅ Isolated Tenant Kubeconfig generated!"

# ==============================================================================
# [STEP 6] VERIFY PRIVILEGES & PROPAGATION
# ==============================================================================
echo ""
echo "🔍 [STEP 6] Verifying Tenant Bootstrap SA Permissions..."
echo "-------------------------------------------------------"
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-context auth can-i create projects.resourcemanager.global.gdc.goog -n platform >/dev/null 2>&1; then
    echo "✅ SUCCESS: tenant-bootstrap-sa possesses project-creation and tenant-admin privileges."
else
    echo "⚠️ WARNING: tenant-bootstrap-sa permission check failed. Role propagation may take a moment."
fi

echo ""
echo "🔍 Verifying Tenant Runner SA Permissions..."
echo "-------------------------------------------------------"
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=runner-context auth can-i get secrets -n "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "✅ SUCCESS: tenant-runner-sa can view secrets within namespace '$IAC_PROJECT'."
else
    echo "⚠️ WARNING: tenant-runner-sa permission check failed."
fi

VERSION_PREFIX=""
if [ -n "$VERSION" ]; then
    VERSION_PREFIX="VERSION=$VERSION "
else
    VERSION_PREFIX="VERSION=-v1 "
fi

echo ""
echo "🚀 READY FOR GDC-NATIVE RUN!"
echo "-------------------------------------------------------"
echo "To deploy Project & Container Web + DB benchmark via Tenant-Scoped Contexts:"
echo "  KUBECONFIG=$KUBECONFIG_SA ${VERSION_PREFIX}GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile sync"
echo ""
