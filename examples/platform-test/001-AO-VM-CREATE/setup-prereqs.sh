#!/bin/bash
# setup-prereqs.sh: Unified interactive flow for 001-AO-VM-CREATE
# Uses platform-admin role to ensure full 'bind' privileges for IaC.

set -e

# --- Configuration ---
ORG_NAME="org-1"
IAC_PROJECT="iac-root"
IAC_USER_EMAIL="fop-iac@example.com"
GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-org-1-zone1-google-gdch-test_global-api"}

CONSOLE_HOST="console.org-1.zone1.google.gdch.test"
CERT_DIR="./.certs"
mkdir -p "$CERT_DIR"

echo "================================================="
echo "🔐 001-AO-VM-CREATE: Unified Platform Setup"
echo "================================================="

# 1. Certificate Management
echo "📡 Fetching GDC Certificates..."
openssl s_client -showcerts -connect ${CONSOLE_HOST}:443 </dev/null 2>/dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"

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
echo "🔑 Granting 'platform-admin' to $IAC_USER_EMAIL..."
# platform-admin includes the 'bind' privilege for standard project roles
gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:$IAC_USER_EMAIL" \
    --role="platform-admin" >/dev/null 2>&1 || echo "⚠️ Role might already be bound."

# Also ensure project-creator is there (redundant but safe)
gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:$IAC_USER_EMAIL" \
    --role="project-creator" >/dev/null 2>&1 || echo "⚠️ Role might already be bound."

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
echo "🚀 STEP 3: Launching VM Provisioning..."
# Verify list secrets permission before syncing
echo "🔍 Verifying Helm permissions..."
until kubectl --context "$GLOBAL_CONTEXT" get secrets -n "$IAC_PROJECT" >/dev/null 2>&1; do
    echo "...still waiting for secret permissions to propagate..."
    sleep 10
done

VERSION=${VERSION:-"-v1"} helmfile sync
