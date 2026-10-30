#!/bin/bash
# setup-operator-sa.sh
#
# ==============================================================================
# 📖 TL;DR / OVERVIEW
# ==============================================================================
# This script bootstraps the headless, non-interactive GitOps/IaC execution flow
# for the 004-CONTAINER-APACHE-POSTGRES test case.
#
# GDC's split-plane architecture requires authenticating against two endpoints:
#   1. Global API Cluster (logical resources, tenancy, projects, global IAM)
#   2. Admin Cluster (regional resources, project bindings, physical user workloads)
#
# To run fully automated pipelines without human OIDC web logins, we:
#   a) Provision two twin Service Accounts (platform-bootstrap-sa and test-runner-sa)
#      on both cluster planes.
#   b) Extract their secure local JWT token secrets.
#   c) Construct a consolidated, client-side 4-context Kubeconfig (.kubeconfig-sa).
# ==============================================================================

set -e

# --- Configuration & Context Defaults ---
ORG_NAME="org-1"
IAC_PROJECT="iac-root"
GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-org-1-zone1-google-gdch-test_global-api"}
ADMIN_CONTEXT=${ADMIN_CLUSTER_CONTEXT:-"org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin"}

CERT_DIR="./.certs"
KUBECONFIG_SA="./.kubeconfig-sa"

CONSOLE_HOST=${CONSOLE_HOST:-"console.org-1.zone1.google.gdch.test"}
AIS_HOST=${AIS_HOST:-"ais-core.org-1.zone1.google.gdch.test"}
KMS_HOST=${KMS_HOST:-"kms.org-1.zone1.google.gdch.test"}

echo "======================================================="
echo "🛡️  Unified GDC Service Account Bootstrapper (Web + DB)"
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
# [STEP 2] PLATFORM ADMIN ACCESS VERIFICATION & CONDITIONAL LOGIN
# ==============================================================================
echo "🔍 [STEP 2] Checking current context permissions..."
CAN_CREATE_SA=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create serviceaccounts -n "$IAC_PROJECT" 2>/dev/null || echo "no")
CAN_CREATE_RB=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create iamrolebindings.iam.global.gdc.goog -n platform 2>/dev/null || echo "no")

if [ "$CAN_CREATE_SA" != "yes" ] || [ "$CAN_CREATE_RB" != "yes" ]; then
    echo "⚠️  Current context does not have sufficient GDC Platform Admin & Delegation privileges."
    echo "👤 Requesting Platform Admin authentication..."
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
    echo "✅ Authenticated successfully as Platform Admin!"
else
    echo "✅ Active context has sufficient Platform Admin and delegation privileges. Skipping OIDC login."
fi

# ==============================================================================
# [STEP 3] APPLY DECLARATIVE MANIFESTS (Split Plane Bootstrapping)
# ==============================================================================
echo "📦 [STEP 3] Deploying Service Accounts and IAM RoleBindings logically..."
kubectl --context "$GLOBAL_CONTEXT" apply -f tenant-bootstrap.yaml

echo "⚙️  Deploying Service Accounts and Native RBAC Roles physically to Admin Cluster..."
kubectl --context "$ADMIN_CONTEXT" apply -f operator-bootstrap.yaml

echo "⏳ Waiting for GDC secrets and roles to initialize (10s)..."
sleep 10

# ==============================================================================
# [STEP 4] EXTRACT GDC SERVICE ACCOUNT JWT TOKENS
# ==============================================================================
echo "🔑 [STEP 4] Retrieving logical Global API tokens..."
PLATFORM_BOOTSTRAP_GLOBAL_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_GLOBAL_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

echo "🔑 Retrieving physical Admin Cluster tokens..."
PLATFORM_BOOTSTRAP_ADMIN_TOKEN=$(kubectl --context "$ADMIN_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_ADMIN_TOKEN=$(kubectl --context "$ADMIN_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

if [ -z "$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN" ] || [ -z "$TEST_RUNNER_GLOBAL_TOKEN" ] || \
   [ -z "$PLATFORM_BOOTSTRAP_ADMIN_TOKEN" ] || [ -z "$TEST_RUNNER_ADMIN_TOKEN" ]; then
    echo "❌ Failed to retrieve ServiceAccount tokens from either Global API or Admin Cluster. Check deployment logs above."
    exit 1
fi

echo "✅ All 4 tokens extracted successfully!"

# ==============================================================================
# [STEP 5] GENERATE CLIENT-SIDE 4-CONTEXT HYBRID KUBECONFIG
# ==============================================================================
echo "💾 [STEP 5] Generating 4-context Kubeconfig at '$KUBECONFIG_SA'..."
rm -f "$KUBECONFIG_SA"

GLOBAL_APISERVER=$(kubectl config view --minify --context="$GLOBAL_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}')
ADMIN_APISERVER=$(kubectl config view --minify --context="$ADMIN_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}')

# Map Cluster Endpoints
kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster global-api-cluster \
    --server="$GLOBAL_APISERVER" \
    --insecure-skip-tls-verify=true

kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster admin-physical-cluster \
    --server="$ADMIN_APISERVER" \
    --insecure-skip-tls-verify=true

# Inject Tokens
kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials global-bootstrap-sa \
    --token="$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials admin-bootstrap-sa \
    --token="$PLATFORM_BOOTSTRAP_ADMIN_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials global-runner-sa \
    --token="$TEST_RUNNER_GLOBAL_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials admin-runner-sa \
    --token="$TEST_RUNNER_ADMIN_TOKEN"

# Configure Multi-Plane Contexts
kubectl config --kubeconfig="$KUBECONFIG_SA" set-context bootstrap-global-context \
    --cluster=global-api-cluster \
    --user=global-bootstrap-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context bootstrap-admin-context \
    --cluster=admin-physical-cluster \
    --user=admin-bootstrap-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context runner-global-context \
    --cluster=global-api-cluster \
    --user=global-runner-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context runner-admin-context \
    --cluster=admin-physical-cluster \
    --user=admin-runner-sa \
    --namespace="$IAC_PROJECT"

echo "✅ Consolidated 4-Context Kubeconfig generated!"

# ==============================================================================
# [STEP 6] VERIFY PRIVILEGES
# ==============================================================================
echo ""
echo "🔍 [STEP 6] Verifying Multi-Context Permissions..."
echo "-------------------------------------------------------"

if kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-global-context auth can-i create projects.resourcemanager.global.gdc.goog -n platform >/dev/null 2>&1; then
    echo "✅ SUCCESS: bootstrap-global-context can manage global GDC Projects."
else
    echo "⚠️ WARNING: bootstrap-global-context permission check failed."
fi

if kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-admin-context auth can-i create projectbindings.cluster.gdc.goog -n platform >/dev/null 2>&1; then
    echo "✅ SUCCESS: bootstrap-admin-context can manage physical project cluster attachments."
else
    echo "⚠️ WARNING: bootstrap-admin-context permission check failed."
fi

if kubectl --kubeconfig="$KUBECONFIG_SA" --context=runner-admin-context auth can-i get secrets -n "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "✅ SUCCESS: runner-admin-context can manage Helm secrets."
else
    echo "⚠️ WARNING: runner-admin-context permission check failed."
fi

VERSION_PREFIX=""
if [ -n "$VERSION" ]; then
    VERSION_PREFIX="VERSION=$VERSION "
else
    VERSION_PREFIX="VERSION=-v1 "
fi

echo ""
echo "🚀 READY FOR OPERATOR-SCOPED RUN!"
echo "-------------------------------------------------------"
echo "To run the Operator-Scoped pathway (out-of-band Admin RBAC):"
echo "  1) Deploy Projects & bindings (Platform Admin SA Context):"
echo "     KUBECONFIG=$KUBECONFIG_SA ${VERSION_PREFIX}GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=apache-postgres sync"
echo ""
echo "  2) Deploy Web + DB workloads (Restricted Runner SA Context):"
echo "     KUBECONFIG=$KUBECONFIG_SA ${VERSION_PREFIX}GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=apache-postgres sync"
echo ""
