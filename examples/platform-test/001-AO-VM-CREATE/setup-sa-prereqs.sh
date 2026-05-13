#!/bin/bash
# setup-sa-prereqs.sh
# Bootstraps ServiceAccounts, Token Secrets, and GDC-native IAMRoleBindings for unified test execution.
# Works identically across Adhoc Sandbox, Staging, and Production environments.
# Run this script using your administrative context to generate the automated execution contexts.

set -e

# --- Configuration ---
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
echo "🛡️  Unified GDC Service Account Bootstrapper"
echo "======================================================="

# 1. Optional Local Certificate trust store setup
if [ "${UPDATE_CERTS}" = "true" ]; then
    echo "🔒 Fetching and updating certificates for local trust store..."
    mkdir -p "$CERT_DIR"
    openssl s_client -showcerts -connect "${CONSOLE_HOST}:443" </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"
    openssl s_client -showcerts -connect "${AIS_HOST}:443" </dev/null | openssl x509 -outform PEM >  "${CERT_DIR}/ais-core.crt"
    openssl s_client -showcerts -connect "${KMS_HOST}:443" </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-kms.crt"
    
    echo "Adding KMS & AIS certs to trust store (requires sudo)..."
    sudo cp ${CERT_DIR}/* /usr/local/share/ca-certificates/
    sudo update-ca-certificates
    echo "✅ Trust store updated!"
fi

# 2. Administrative Permission Check & Conditional Login
echo "🔍 Checking current context permissions..."
CAN_CREATE_SA=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create serviceaccounts -n "$IAC_PROJECT" 2>/dev/null || echo "no")
CAN_CREATE_RB=$(kubectl --context "$GLOBAL_CONTEXT" auth can-i create iamrolebindings.iam.global.gdc.goog -n platform 2>/dev/null || echo "no")

if [ "$CAN_CREATE_SA" != "yes" ] || [ "$CAN_CREATE_RB" != "yes" ]; then
    echo "⚠️  Current context does not have sufficient GDC Platform Admin & Delegation privileges."
    echo "👤 Requesting Platform Admin authentication..."
    echo "-------------------------------------------------------"
    
    # Ensure cert directory and console certificate exist for login
    if [ ! -f "${CERT_DIR}/gdc-console.crt" ]; then
        echo "📥 Fetching console certificate for authentication..."
        mkdir -p "$CERT_DIR"
        openssl s_client -showcerts -connect "${CONSOLE_HOST}:443" </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"
    fi
    
    gdcloud auth login --login-config-cert "${CERT_DIR}/gdc-console.crt"
    
    # Verify again after login
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

# 3. Apply Declarative Kubernetes Resources
echo "📦 Applying ServiceAccounts, Tokens & GDC IAMRoleBindings to Global API Cluster..."
kubectl --context "$GLOBAL_CONTEXT" apply -f physical-bootstrap.yaml

echo "📦 Applying ServiceAccounts, Tokens & ClusterRoleBindings to Admin Cluster..."
kubectl --context "$ADMIN_CONTEXT" create namespace "$IAC_PROJECT" 2>/dev/null || true
kubectl --context "$ADMIN_CONTEXT" apply -f admin-bootstrap.yaml

echo "⏳ Waiting for tokens and IAM roles to propagate (20s)..."
sleep 20

# 3. Extract Token and CA Data
echo "🔑 Retrieving ServiceAccount tokens from Global API Cluster..."
PLATFORM_BOOTSTRAP_GLOBAL_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_GLOBAL_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

echo "🔑 Retrieving ServiceAccount tokens from Admin Cluster..."
PLATFORM_BOOTSTRAP_ADMIN_TOKEN=$(kubectl --context "$ADMIN_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_ADMIN_TOKEN=$(kubectl --context "$ADMIN_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

if [ -z "$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN" ] || [ -z "$TEST_RUNNER_GLOBAL_TOKEN" ] || \
   [ -z "$PLATFORM_BOOTSTRAP_ADMIN_TOKEN" ] || [ -z "$TEST_RUNNER_ADMIN_TOKEN" ]; then
    echo "❌ Failed to retrieve ServiceAccount tokens from both clusters. Ensure physical-bootstrap.yaml is successfully deployed."
    exit 1
fi

echo "✅ Tokens retrieved successfully from both clusters!"

# 4. Create Isolated Kubeconfig Configuration File
echo "💾 Generating unified ServiceAccount Kubeconfig at '$KUBECONFIG_SA'..."
rm -f "$KUBECONFIG_SA"

# Copy the current server endpoints from the active contexts
APISERVER=$(kubectl config view --minify --context="$GLOBAL_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}')
ADMIN_APISERVER=$(kubectl config view --minify --context="$ADMIN_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || echo "$APISERVER")

# Build isolated Kubeconfig clusters
kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster global-api-cluster \
    --server="$APISERVER" \
    --insecure-skip-tls-verify=true

kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster admin-cluster \
    --server="$ADMIN_APISERVER" \
    --insecure-skip-tls-verify=true

# Set Credentials
kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials platform-bootstrap-global-sa \
    --token="$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials platform-bootstrap-admin-sa \
    --token="$PLATFORM_BOOTSTRAP_ADMIN_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials test-runner-global-sa \
    --token="$TEST_RUNNER_GLOBAL_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials test-runner-admin-sa \
    --token="$TEST_RUNNER_ADMIN_TOKEN"

# Set Contexts
kubectl config --kubeconfig="$KUBECONFIG_SA" set-context bootstrap-global-context \
    --cluster=global-api-cluster \
    --user=platform-bootstrap-global-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context bootstrap-admin-context \
    --cluster=admin-cluster \
    --user=platform-bootstrap-admin-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context runner-global-context \
    --cluster=global-api-cluster \
    --user=test-runner-global-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context runner-admin-context \
    --cluster=admin-cluster \
    --user=test-runner-admin-sa \
    --namespace="$IAC_PROJECT"

echo "✅ Unified Multi-Cluster Kubeconfig generated!"

# 5. Verify Permissions and Roles
echo ""
echo "🔍 Verifying Platform Bootstrap SA Permissions..."
echo "-------------------------------------------------------"
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-global-context auth can-i create projects.resourcemanager.global.gdc.goog -n platform >/dev/null 2>&1 && \
   kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-global-context auth can-i get secrets -n "$IAC_PROJECT" >/dev/null 2>&1 && \
   kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-admin-context auth can-i create projectbindings.resourcemanager.gdc.goog -n platform >/dev/null 2>&1; then
    echo "✅ SUCCESS: platform-bootstrap-sa has complete organization admin, secret management, and cluster binding privileges."
else
    echo "⚠️ WARNING: platform-bootstrap-sa permission check failed. Propagation may take a moment."
fi

echo ""
echo "🔍 Verifying Test Runner SA Permissions..."
echo "-------------------------------------------------------"
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=runner-admin-context auth can-i get secrets -n "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "✅ SUCCESS: test-runner-sa can read secrets on the Admin Cluster namespace '$IAC_PROJECT'."
else
    echo "⚠️ WARNING: test-runner-sa permission check failed."
fi

# Determine version prefix instruction based on environment or collision safety
VERSION_PREFIX=""
if [ -n "$VERSION" ]; then
    VERSION_PREFIX="VERSION=$VERSION "
else
    VERSION_PREFIX="VERSION=-v1 "
fi

echo ""
echo "🚀 READY FOR UNIFIED RUN!"
echo "-------------------------------------------------------"
echo "To deploy Phase 1 (Project Bootstrap) via Platform Admin context:"
echo "  KUBECONFIG=$KUBECONFIG_SA ${VERSION_PREFIX}GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=vm sync"
echo ""
echo "To deploy Phase 2 (VM Provisioning) via restricted Runner context:"
echo "  KUBECONFIG=$KUBECONFIG_SA ${VERSION_PREFIX}GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=vm sync"
echo ""
