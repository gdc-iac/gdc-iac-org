#!/usr/bin/env bash
# setup-customer-base.sh
# Core driver for logical customer-scoped pipeline SA and credential compilation.
# Sourced by case-scoped setup-customer-sa.sh scripts.

set -e

if [ -z "${TEST_CASE_NO}" ] || [ -z "${VERIFY_RBAC}" ]; then
    echo "❌ Error: TEST_CASE_NO and VERIFY_RBAC must be defined before sourcing setup-customer-base.sh"
    exit 1
fi

# --- Configuration & Context Defaults ---
ORG_NAME=${ORG_NAME:-"org-1"}
IAC_PROJECT=${IAC_PROJECT:-"iac-root"}
ZONE_NAME=${ZONE_NAME:-"east1"}
HOST_SUFFIX=${HOST_SUFFIX:-"google.gdch.test"}

# Derive context-safe domain representation (dots to dashes)
DOMAIN_SUFFIX_CONTEXT=$(echo "${HOST_SUFFIX}" | tr '.' '-')

GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-${ORG_NAME}-${ZONE_NAME}-${DOMAIN_SUFFIX_CONTEXT}_global-api"}

CERT_DIR="./.certs"
KUBECONFIG_SA="./.kubeconfig-sa"

CONSOLE_HOST=${CONSOLE_HOST:-"console.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}
AIS_HOST=${AIS_HOST:-"ais-core.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}
KMS_HOST=${KMS_HOST:-"kms.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}

echo "======================================================="
echo "🛡️  GDC Customer Setup Driver (Logical Plane)"
echo "📋 Case: ${TEST_CASE_NO} | Verify: ${VERIFY_RBAC}"
echo "======================================================="

# ==============================================================================
# [STEP 1] OPTIONAL LOCAL CERTIFICATE TRUST STORE SETUP
# ==============================================================================
if [ "${UPDATE_CERTS}" = "true" ] || [ ! -f "${CERT_DIR}/gdc-console.crt" ]; then
    echo "🔒 [STEP 1] Fetching and updating certificates for local trust store..."
    ../000-SETUP/update-certs.sh
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
        ../000-SETUP/update-certs.sh
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
# [STEP 3] APPLY DECLARATIVE GDC-NATIVE RESOURCES
# ==============================================================================
echo "📦 [STEP 3] Applying GDC-Native ServiceAccounts & IAMRoleBindings to Global API Cluster..."

# Substitute placeholders in base-customer-identity.yaml and apply
sed -e "s/\${TEST_CASE_NO}/${TEST_CASE_NO}/g" \
    -e "s/\${IAC_PROJECT}/${IAC_PROJECT}/g" \
    ../000-SETUP/base-customer-identity.yaml | kubectl --context "$GLOBAL_CONTEXT" apply -f -
kubectl --context "$GLOBAL_CONTEXT" apply -f ./auth-extension.yaml

echo "⏳ Waiting for GDC secrets and roles to propagate (15s)..."
sleep 15

# ==============================================================================
# [STEP 4] EXTRACT GDC SERVICE ACCOUNT JWT TOKENS & GENERATE KUBECONFIG
# ==============================================================================
echo "💾 [STEP 4] Compiling customer-scoped Kubeconfig at '$KUBECONFIG_SA'..."
../000-SETUP/generate-kubeconfig.sh --type customer

# ==============================================================================
# [STEP 5] VERIFY PRIVILEGES & PROPAGATION
# ==============================================================================
echo ""
echo "🔍 [STEP 5] Verifying Customer Setup SA Permissions..."
echo "-------------------------------------------------------"
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=bootstrap-context auth can-i create projects.resourcemanager.global.gdc.goog -n platform >/dev/null 2>&1; then
    echo "✅ SUCCESS: test-setup-sa possesses project-creation and tenant-admin privileges."
else
    echo "⚠️  WARNING: test-setup-sa permission check failed. Role propagation may take a moment."
fi

echo ""
echo "🔍 Verifying Customer Runner SA Permissions..."
echo "-------------------------------------------------------"
# Split VERIFY_RBAC into action and resource
read -r VERIFY_VERB VERIFY_KIND <<< "${VERIFY_RBAC}"
if kubectl --kubeconfig="$KUBECONFIG_SA" --context=runner-context auth can-i "${VERIFY_VERB}" "${VERIFY_KIND}" -n "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "✅ SUCCESS: test-runner-${TEST_CASE_NO}-sa can perform '${VERIFY_RBAC}' within namespace '$IAC_PROJECT'."
else
    echo "⚠️  WARNING: test-runner-${TEST_CASE_NO}-sa permission check failed."
fi

VERSION_PREFIX=""
if [ -n "$VERSION" ]; then
    VERSION_PREFIX="VERSION=$VERSION "
else
    VERSION_PREFIX="VERSION=-v1 "
fi

echo ""
echo "🚀 READY FOR GDC-NATIVE CUSTOMER RUN!"
echo "-------------------------------------------------------"
echo "To deploy Project and Workloads via Customer-Scoped Contexts:"
echo "  KUBECONFIG=$KUBECONFIG_SA ${VERSION_PREFIX}GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile sync"
echo ""
