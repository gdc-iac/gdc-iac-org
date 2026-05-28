#!/bin/bash
# setup-adhoc-env.sh: Unified interactive flow for 003-VM-IPERF3
# Uses platform-admin role to ensure full 'bind' privileges for IaC.

set -e

# --- Configuration ---
ORG_NAME="org-1"
IAC_PROJECT="iac-root"
IAC_USER_EMAIL="fop-iac@example.com"
GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-org-1-zone1-google-gdch-test_global-api"}

CONSOLE_HOST="console.org-1.zone1.google.gdch.test"
AIS_HOST="ais-core.org-1.zone1.google.gdch.test"
KMS_HOST="kms.org-1.zone1.google.gdch.test"

CERT_DIR="./.certs"
mkdir -p "$CERT_DIR"

echo "================================================="
echo "🔐 003-VM-IPERF3: Unified Platform Setup"
echo "================================================="

# 1. Certificate Management
echo "Fetching Console Certificate..."
openssl s_client -showcerts -connect ${CONSOLE_HOST}:443 </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"

echo "Fetching AIS Certificate..."
openssl s_client -showcerts -connect ${AIS_HOST}:443 </dev/null | openssl x509 -outform PEM >  "${CERT_DIR}/ais-core.crt"

echo "Fetching KMS certificate..."
openssl s_client -showcerts -connect ${KMS_HOST}:443 </dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-kms.crt"

echo "Adding KMS & AIS certs to trust store (requires sudo)..."
sudo cp ${CERT_DIR}/* /usr/local/share/ca-certificates/
sudo update-ca-certificates

# 2. Platform Admin Login
echo ""
echo "👤 STEP 1: Please log in as a PLATFORM ADMIN (Cluster Admin)"
echo "-------------------------------------------------"
gdcloud auth login --login-config-cert "${CERT_DIR}/gdc-console.crt"

# 3. Create iac-root Project (This creates the namespace)
echo ""
echo "🏗️ Ensuring Project '$IAC_PROJECT' exists..."
if gdcloud projects describe "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "ℹ️ Project '$IAC_PROJECT' already exists."
else
    echo "🔨 Creating project '$IAC_PROJECT'..."
    gdcloud projects create "$IAC_PROJECT"
fi

# 4. Grant HIGH-LEVEL Organization Roles
echo ""
echo "🔑 Granting bootstrap roles to $IAC_USER_EMAIL..."
gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:$IAC_USER_EMAIL" \
    --role="platform-admin" >/dev/null 2>&1 || echo "⚠️ Role platform-admin might already be bound."

gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:$IAC_USER_EMAIL" \
    --role="project-creator" >/dev/null 2>&1 || echo "⚠️ Role project-creator might already be bound."

echo "🔑 Granting global admin roles to $IAC_USER_EMAIL..."
for role in organization-iam-admin project-editor user-cluster-admin; do
    echo "...granting $role"
    gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
        --member="user:$IAC_USER_EMAIL" \
        --role="$role" >/dev/null 2>&1 || echo "⚠️ Role $role might already be bound."
done

# 5. Grant Project Roles on iac-root (Required for Helm state)
echo ""
echo "🔑 Granting Project-level roles on '$IAC_PROJECT' to $IAC_USER_EMAIL..."
for role in project-editor secret-admin; do
    echo "...granting $role"
    gdcloud projects add-iam-policy-binding "$IAC_PROJECT" \
        --member="user:$IAC_USER_EMAIL" \
        --role="$role" >/dev/null 2>&1 || echo "⚠️ Role $role might already be bound."
done

echo ""
echo "⏳ Waiting for IAM propagation (30s)..."
sleep 30

# 6. IAC User Login
echo ""
echo "👤 STEP 2: Switching back to IAC USER ($IAC_USER_EMAIL)"
echo "-------------------------------------------------"
gdcloud auth login --login-config-cert "${CERT_DIR}/gdc-console.crt"

# 7. Final Verification & Execute
echo ""
echo "🚀 STEP 3: Launching VM iperf3 Workload Provisioning..."
echo "🔍 Verifying Helm permissions..."
if kubectl --context "$GLOBAL_CONTEXT" auth can-i create secrets -n "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "✅ Permissions validated. Running Helmfile Sync..."
    VERSION_PREFIX=""
    if [ -n "$VERSION" ]; then
        VERSION_PREFIX="VERSION=$VERSION "
    fi
    KUBECONFIG=~/.kube/config ${VERSION_PREFIX}helmfile sync
else
    echo "❌ ERROR: Active context does not have access to create secrets in '$IAC_PROJECT'."
    exit 1
fi
