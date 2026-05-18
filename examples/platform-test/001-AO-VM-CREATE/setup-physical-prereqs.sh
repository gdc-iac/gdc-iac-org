#!/bin/bash
# setup-physical-prereqs.sh
# Bootstraps ServiceAccounts and IAMRoleBindings for GDC Physical Clusters (Gonzo, Bunsen, etc.)
# Run this script as PLATFORM ADMIN / CLUSTER ADMIN to generate automated, restricted execution contexts.

set -e

# --- Configuration ---
ORG_NAME="org-1"
IAC_PROJECT="iac-root"
GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-org-1-zone1-google-gdch-test_global-api"}

CERT_DIR="./.certs"
mkdir -p "$CERT_DIR"

echo "======================================================="
echo "🛡️  GDC Physical Environment Bootstrapper (AD / SA Model)"
echo "======================================================="

# 1. Apply Declarative Kubernetes Resources
echo "📦 Applying ServiceAccounts, Tokens & GDC IAMRoleBindings..."
kubectl --context "$GLOBAL_CONTEXT" apply -f physical-bootstrap.yaml

echo "⏳ Waiting for secrets and tokens to generate..."
sleep 5

# 2. Extract Token and CA Data
echo "🔑 Retrieving ServiceAccount tokens..."
PLATFORM_BOOTSTRAP_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret platform-bootstrap-sa-token -o jsonpath='{.data.token}' | base64 --decode)
TEST_RUNNER_TOKEN=$(kubectl --context "$GLOBAL_CONTEXT" -n "$IAC_PROJECT" get secret test-runner-sa-token -o jsonpath='{.data.token}' | base64 --decode)

if [ -z "$PLATFORM_BOOTSTRAP_TOKEN" ] || [ -z "$TEST_RUNNER_TOKEN" ]; then
    echo "❌ Failed to retrieve ServiceAccount tokens. Ensure kubernetes.io/service-account-token secrets are active."
    exit 1
fi

echo "✅ Tokens retrieved successfully!"

# 3. Create Isolated Kubeconfig Configuration File for Verification
KUBECONFIG_SA="./.kubeconfig-sa"
echo "💾 Generating service account Kubeconfig at '$KUBECONFIG_SA'..."

# Copy the current server endpoint from global context
APISERVER=$(kubectl --context "$GLOBAL_CONTEXT" config view -o jsonpath="{.clusters[?(@.name=='$GLOBAL_CONTEXT')].cluster.server}")

# Build isolated Kubeconfig
kubectl config --kubeconfig="$KUBECONFIG_SA" set-cluster physical-gdc \
    --server="$APISERVER" \
    --insecure-skip-tls-verify=true

# Set Credentials
kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials platform-bootstrap-sa \
    --token="$PLATFORM_BOOTSTRAP_TOKEN"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-credentials test-runner-sa \
    --token="$TEST_RUNNER_TOKEN"

# Set Contexts
kubectl config --kubeconfig="$KUBECONFIG_SA" set-context bootstrap-context \
    --cluster=physical-gdc \
    --user=platform-bootstrap-sa \
    --namespace="$IAC_PROJECT"

kubectl config --kubeconfig="$KUBECONFIG_SA" set-context runner-context \
    --cluster=physical-gdc \
    --user=test-runner-sa \
    --namespace="$IAC_PROJECT"

echo "✅ Isolated Kubeconfig generated!"

# 4. Verify Permissions and Roles
echo ""
echo "🔍 Verifying Platform Bootstrap SA Permissions..."
echo "-------------------------------------------------------"
# Bootstrap SA must be able to create projects in platform namespace
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-context auth can-i create projects.resourcemanager.global.gdc.goog -n platform >/dev/null 2>&1; then
    echo "✅ SUCCESS: platform-bootstrap-sa can create Project resources in 'platform'."
else
    echo "⚠️ WARNING: platform-bootstrap-sa permission check failed. IAM Role propagation may take a few minutes."
fi

echo ""
echo "🔍 Verifying Test Runner SA Permissions..."
echo "-------------------------------------------------------"
# Runner SA must be able to get secrets inside iac-root
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=runner-context auth can-i get secrets -n "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "✅ SUCCESS: test-runner-sa can read secrets in '$IAC_PROJECT'."
else
    echo "⚠️ WARNING: test-runner-sa permission check failed."
fi

echo ""
echo "🚀 READY FOR ISOLATED RUN!"
echo "-------------------------------------------------------"
echo "To run the Helmfile sync using the automated test-runner service account, execute:"
echo ""
echo "  KUBECONFIG=$KUBECONFIG_SA helmfile --kube-context runner-context sync"
echo ""
