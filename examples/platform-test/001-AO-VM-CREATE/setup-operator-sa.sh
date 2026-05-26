#!/bin/bash
# setup-operator-sa.sh
#
# ==============================================================================
# 📖 TL;DR / OVERVIEW
# ==============================================================================
# This script bootstraps the headless, non-interactive GitOps/IaC execution flow
# for the 001-AO-VM-CREATE test case.
#
# GDC's split-plane architecture requires authenticating against two endpoints:
#   1. Global API Cluster (logical resources, tenancy, projects, global IAM)
#   2. Admin Cluster (regional resources, project bindings, physical VMs)
#
# To run fully automated pipelines without human OIDC web logins, we:
#   a) Provision two twin Service Accounts (platform-bootstrap-sa and test-runner-sa)
#      on both cluster planes.
#   b) Extract their secure local JWT token secrets.
#   c) Construct a consolidated, client-side 4-context Kubeconfig (.kubeconfig-sa).
#
# 💡 TIP FOR SINGLE-CLUSTER / PHYSICAL TEST ENVIRONMENTS:
#    If your environment has a single Kubernetes context serving both Global API
#    and Admin/User planes (e.g., physical staging/development clusters),
#    you can still run this script! Simply set:
#      export GLOBAL_API_CONTEXT="your-single-context"
#      export ADMIN_CLUSTER_CONTEXT="your-single-context"
#    The script will seamlessly map the 4 logical contexts to the same physical endpoint.
#
# 🛠️ MANUAL STEP-BY-STEP EXECUTION:
#    Each major block below is annotated with the exact copy-pasteable commands 
#    you can execute manually in your terminal if you prefer not to run the script.
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
echo "🛡️  Unified GDC Service Account Bootstrapper"
echo "======================================================="

# ==============================================================================
# [STEP 1] OPTIONAL LOCAL CERTIFICATE TRUST STORE SETUP
# ==============================================================================
# Purpose: Fetches target GDC cluster endpoint TLS certificates and registers 
#          them in the local operating system's certificate store. This prevents 
#          cURL / openssl / gdcloud CLI cert-trust handshake errors.
#
# Manual Command Line equivalent:
#   mkdir -p .certs
#   openssl s_client -showcerts -connect console.org-1.zone1.google.gdch.test:443 </dev/null | openssl x509 -outform PEM > .certs/gdc-console.crt
#   openssl s_client -showcerts -connect ais-core.org-1.zone1.google.gdch.test:443 </dev/null | openssl x509 -outform PEM > .certs/ais-core.crt
#   openssl s_client -showcerts -connect kms.org-1.zone1.google.gdch.test:443 </dev/null | openssl x509 -outform PEM > .certs/gdc-kms.crt
#   sudo cp .certs/* /usr/local/share/ca-certificates/
#   sudo update-ca-certificates
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
# Purpose: Validates whether your active terminal context already possesses 
#          sufficient admin authorization on GDC to configure projects and 
#          delegate roles. If not, it triggers an interactive OIDC sign-in flow.
#
# Manual Command Line equivalent:
#   kubectl --context="global-api-gdch_console-org-1-zone1-google-gdch-test_global-api" auth can-i create serviceaccounts -n iac-root
#   # If output is "no", perform authentication:
#   gdcloud auth login --login-config-cert ".certs/gdc-console.crt"
# ==============================================================================
echo "🔍 [STEP 2] Checking current context permissions..."
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
    
    # Verify again after login to guarantee execution authorization
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
# [STEP 3] APPLY DECLARATIVE KUBERNETES RESOURCES
# ==============================================================================
# Purpose: Applies declarative Kubernetes manifests to setup the SA accounts, 
#          token Secrets, GDC global IAM policies, and regional cluster RBAC.
#
# Manual Command Line equivalent:
#   # Apply Service Accounts & GDC IAM configurations to the Global API Cluster:
#   kubectl --context="global-api-gdch_console-org-1-zone1-google-gdch-test_global-api" apply -f tenant-bootstrap.yaml
#
#   # Create target namespace and apply K8s RBAC to the Admin Cluster:
#   kubectl --context="org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin" create namespace iac-root
#   kubectl --context="org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin" apply -f operator-bootstrap.yaml
# ==============================================================================
echo "📦 [STEP 3] Applying ServiceAccounts, Tokens & GDC IAMRoleBindings to Global API Cluster..."
kubectl --context "$GLOBAL_CONTEXT" apply -f tenant-bootstrap.yaml

echo "📦 Applying ServiceAccounts, Tokens & ClusterRoleBindings to Admin Cluster..."
kubectl --context "$ADMIN_CONTEXT" create namespace "$IAC_PROJECT" 2>/dev/null || true
kubectl --context "$ADMIN_CONTEXT" apply -f operator-bootstrap.yaml

echo "⏳ Waiting for tokens and IAM roles to propagate (20s)..."
sleep 20

# ==============================================================================
# [STEP 4] EXTRACT DECRYPTED TOKEN DATA
# ==============================================================================
# Purpose: Reads the raw, auto-generated cryptographic JWT tokens stored in the 
#          Kubernetes namespace secret tokens for both service accounts on both clusters.
#
# Manual Command Line equivalent:
#   # Extract Global API tokens:
#   kubectl --context="global-api-gdch_console-org-1-zone1-google-gdch-test_global-api" -n iac-root get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode
#   kubectl --context="global-api-gdch_console-org-1-zone1-google-gdch-test_global-api" -n iac-root get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode
#
#   # Extract Admin Cluster tokens:
#   kubectl --context="org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin" -n iac-root get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode
#   kubectl --context="org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin" -n iac-root get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode
# ==============================================================================
echo "🔑 [STEP 4] Retrieving ServiceAccount tokens from Global API Cluster..."
PLATFORM_BOOTSTRAP_GLOBAL_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_GLOBAL_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

echo "🔑 Retrieving ServiceAccount tokens from Admin Cluster..."
PLATFORM_BOOTSTRAP_ADMIN_TOKEN=$(kubectl --context "$ADMIN_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_ADMIN_TOKEN=$(kubectl --context "$ADMIN_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

if [ -z "$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN" ] || [ -z "$TEST_RUNNER_GLOBAL_TOKEN" ] || \
   [ -z "$PLATFORM_BOOTSTRAP_ADMIN_TOKEN" ] || [ -z "$TEST_RUNNER_ADMIN_TOKEN" ]; then
    echo "❌ Failed to retrieve ServiceAccount tokens from both clusters. Ensure tenant-bootstrap.yaml and operator-bootstrap.yaml are successfully deployed."
    exit 1
fi

echo "✅ Tokens retrieved successfully from both clusters!"

# ==============================================================================
# [STEP 5] CREATE CLIENT-SIDE ISOLATED MULTI-CONTEXT KUBECONFIG
# ==============================================================================
# Purpose: Creates an isolated .kubeconfig-sa file featuring four distinct contexts:
#            * bootstrap-global-context: High-privilege SA bound to Global API
#            * bootstrap-admin-context: High-privilege SA bound to Admin Cluster
#            * runner-global-context: Restricted runner SA bound to Global API
#            * runner-admin-context: Restricted runner SA bound to Admin Cluster
#          This decouples our automated tools from AIS OIDC logins.
#
# Manual Command Line equivalent:
#   rm -f .kubeconfig-sa
#   APISERVER=$(kubectl config view --minify --context="global-api-gdch_console-org-1-zone1-google-gdch-test_global-api" -o jsonpath='{.clusters[0].cluster.server}')
#   ADMIN_APISERVER=$(kubectl config view --minify --context="org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin" -o jsonpath='{.clusters[0].cluster.server}')
#
#   # Run these config mapping commands to register endpoints, users and contexts:
#   kubectl config --kubeconfig=.kubeconfig-sa set-cluster global-api-cluster --server="$APISERVER" --insecure-skip-tls-verify=true
#   kubectl config --kubeconfig=.kubeconfig-sa set-cluster admin-cluster --server="$ADMIN_APISERVER" --insecure-skip-tls-verify=true
#   kubectl config --kubeconfig=.kubeconfig-sa set-credentials platform-bootstrap-global-sa --token="$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN"
#   kubectl config --kubeconfig=.kubeconfig-sa set-credentials platform-bootstrap-admin-sa --token="$PLATFORM_BOOTSTRAP_ADMIN_TOKEN"
#   kubectl config --kubeconfig=.kubeconfig-sa set-credentials test-runner-global-sa --token="$TEST_RUNNER_GLOBAL_TOKEN"
#   kubectl config --kubeconfig=.kubeconfig-sa set-credentials test-runner-admin-sa --token="$TEST_RUNNER_ADMIN_TOKEN"
#   kubectl config --kubeconfig=.kubeconfig-sa set-context bootstrap-global-context --cluster=global-api-cluster --user=platform-bootstrap-global-sa --namespace=iac-root
#   kubectl config --kubeconfig=.kubeconfig-sa set-context bootstrap-admin-context --cluster=admin-cluster --user=platform-bootstrap-admin-sa --namespace=iac-root
#   kubectl config --kubeconfig=.kubeconfig-sa set-context runner-global-context --cluster=global-api-cluster --user=test-runner-global-sa --namespace=iac-root
#   kubectl config --kubeconfig=.kubeconfig-sa set-context runner-admin-context --cluster=admin-cluster --user=test-runner-admin-sa --namespace=iac-root
# ==============================================================================
echo "💾 [STEP 5] Generating unified ServiceAccount Kubeconfig at '$KUBECONFIG_SA'..."
rm -f "$KUBECONFIG_SA"

# Extract active connection string endpoints from original admin context
APISERVER=$(kubectl config view --minify --context="$GLOBAL_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}')
ADMIN_APISERVER=$(kubectl config view --minify --context="$ADMIN_CONTEXT" -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || echo "$APISERVER")

# Map cluster endpoints into target file
kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster global-api-cluster \
    --server="$APISERVER" \
    --insecure-skip-tls-verify=true

kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster admin-cluster \
    --server="$ADMIN_APISERVER" \
    --insecure-skip-tls-verify=true

# Inject decrypted SA authentication tokens
kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials platform-bootstrap-global-sa \
    --token="$PLATFORM_BOOTSTRAP_GLOBAL_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials platform-bootstrap-admin-sa \
    --token="$PLATFORM_BOOTSTRAP_ADMIN_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials test-runner-global-sa \
    --token="$TEST_RUNNER_GLOBAL_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials test-runner-admin-sa \
    --token="$TEST_RUNNER_ADMIN_TOKEN"

# Link users, cluster endpoints, and target workspaces into logical environments
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

# ==============================================================================
# [STEP 6] VERIFY PRIVILEGES AND ROLE ASSIGNMENTS
# ==============================================================================
# Purpose: Simulates active access checks using the generated Kubeconfig's 
#          isolated contexts to verify the new Service Accounts can perform their tasks.
#
# Manual Command Line equivalent:
#   kubectl --kubeconfig=.kubeconfig-sa --context=bootstrap-global-context auth can-i create projects.resourcemanager.global.gdc.goog -n platform
#   kubectl --kubeconfig=.kubeconfig-sa --context=bootstrap-admin-context auth can-i create projectbindings.resourcemanager.gdc.goog -n platform
#   kubectl --kubeconfig=.kubeconfig-sa --context=runner-admin-context auth can-i get secrets -n iac-root
# ==============================================================================
echo ""
echo "🔍 [STEP 6] Verifying Platform Bootstrap SA Permissions..."
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
