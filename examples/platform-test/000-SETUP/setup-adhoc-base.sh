#!/usr/bin/env bash
# setup-adhoc-base.sh
# Core driver for interactive developer sandbox authentication and OIDC setup.
# Sourced by case-scoped setup-adhoc-env.sh scripts.

set -e
SETUP_DIR=$(dirname "${BASH_SOURCE[0]}")

if [ -z "${TEST_CASE_NO}" ] || [ -z "${VERIFY_RESOURCE}" ]; then
    echo "❌ Error: TEST_CASE_NO and VERIFY_RESOURCE must be defined before sourcing setup-adhoc-base.sh"
    exit 1
fi

# Attempt to auto-discover USER_CLUSTER_CONTEXT if not exported
if [ -z "${USER_CLUSTER_CONTEXT}" ]; then
    AUTO_CONTEXT=$(kubectl config get-contexts -o name | grep "^user-vm-" | head -n 1 || true)
    if [ -n "$AUTO_CONTEXT" ]; then
        echo "🔍 Automatically discovered USER_CLUSTER_CONTEXT: ${AUTO_CONTEXT}"
        export USER_CLUSTER_CONTEXT="${AUTO_CONTEXT}"
    fi
fi

if [ "$VERIFY_RESOURCE" = "deployments" ] && [ -z "${USER_CLUSTER_CONTEXT}" ]; then
    echo "❌ Error: USER_CLUSTER_CONTEXT environment variable must be exported before running setup-adhoc-env.sh for workload deployments."
    echo "👉 Run 'kubectl config get-contexts' to locate your user cluster context."
    echo "👉 Then run: export USER_CLUSTER_CONTEXT=\"<your-user-cluster-context>\""
    exit 1
fi

# --- Configuration ---
export ORG_NAME=${ORG_NAME:-"org-1"}
export IAC_PROJECT=${IAC_PROJECT:-"iac-root"}
export ZONE_NAME=${ZONE_NAME:-"zone1"}
export HOST_SUFFIX=${HOST_SUFFIX:-"google.gdch.test"}
IAC_USER_EMAIL="fop-iac@example.com"

# Derive context-safe domain representation (dots to dashes)
DOMAIN_SUFFIX_CONTEXT=$(echo "${HOST_SUFFIX}" | tr '.' '-')

GLOBAL_CONTEXT=${GLOBAL_API_CONTEXT:-"global-api-gdch_console-${ORG_NAME}-${ZONE_NAME}-${DOMAIN_SUFFIX_CONTEXT}_global-api"}

CONSOLE_HOST=${CONSOLE_HOST:-"console.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}
AIS_HOST=${AIS_HOST:-"ais-core.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}
KMS_HOST=${KMS_HOST:-"kms.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}

CERT_DIR="./.certs"
mkdir -p "$CERT_DIR"

echo "=========================================================="
echo "🔐 GDC Interactive Adhoc Setup Driver"
echo "📋 Case: ${TEST_CASE_NO} | Resource: ${VERIFY_RESOURCE}"
echo "=========================================================="

# 1. Certificate Management & Trust Store Setup
echo "📥 Ensuring GDC CA certificates are updated and trusted..."
UPDATE_SYSTEM_TRUST=false ${SETUP_DIR}/update-certs.sh


# 2. Platform Admin Login
echo ""
echo "👤 STEP 1: Please log in as a PLATFORM ADMIN (Cluster Admin)"
echo "--------------------------------------------------------"
gdcloud auth login --login-config-cert "${CERT_DIR}/gdc-root-ca.crt"

# 3. Create iac-root Project (This creates the namespace)
echo ""
echo "🏗️  Ensuring Project '$IAC_PROJECT' exists..."
if gdcloud projects describe "$IAC_PROJECT" >/dev/null 2>&1; then
    echo "ℹ️  Project '$IAC_PROJECT' already exists."
else
    echo "🔨 Creating project '$IAC_PROJECT'..."
    gdcloud projects create "$IAC_PROJECT"
fi

# 4. Grant HIGH-LEVEL Organization Roles
echo ""
echo "🔑 Granting bootstrap roles to $IAC_USER_EMAIL..."
# platform-admin includes the 'bind' privilege for standard project roles
gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:$IAC_USER_EMAIL" \
    --role="platform-admin" >/dev/null 2>&1 || echo "⚠️  Role platform-admin might already be bound."

# Also ensure project-creator is there (redundant but safe)
gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:$IAC_USER_EMAIL" \
    --role="project-creator" >/dev/null 2>&1 || echo "⚠️  Role project-creator might already be bound."

# Grant Org-level roles required to provision projects, rolebindings, and cluster bindings
echo "🔑 Granting global admin roles to $IAC_USER_EMAIL..."
for role in organization-iam-admin project-editor user-cluster-admin; do
    echo "...granting $role"
    gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
        --member="user:$IAC_USER_EMAIL" \
        --role="$role" >/dev/null 2>&1 || echo "⚠️  Role $role might already be bound."
done

# 5. Grant Project Roles on $IAC_PROJECT (Required for Helm state)
echo ""
echo "🔑 Granting Project-level roles on '$IAC_PROJECT' to $IAC_USER_EMAIL..."
for role in project-editor secret-admin; do
    echo "...granting $role"
    gdcloud projects add-iam-policy-binding "$IAC_PROJECT" \
        --member="user:$IAC_USER_EMAIL" \
        --role="$role" >/dev/null 2>&1 || echo "⚠️  Role $role might already be bound."
done

# 5b. Apply Case-Specific Administrative Auth Extension (if any)
if [ -f "./auth-extension.yaml" ]; then
    echo ""
    echo "🛡️  Applying auth-extension.yaml for administrative roles..."
    kubectl --context "$GLOBAL_CONTEXT" apply -f ./auth-extension.yaml
fi

echo ""
echo "⏳ Waiting for IAM propagation (30s)..."
sleep 30

# 6. IAC User Login
echo ""
echo "👤 STEP 2: Switching back to IAC USER ($IAC_USER_EMAIL)"
echo "--------------------------------------------------------"
gdcloud auth login --login-config-cert "${CERT_DIR}/gdc-root-ca.crt"

# 6b. Auto-configure Kubeconfig TLS Verification for Sandbox Clusters
echo ""
echo "🔧 Automatically configuring sandbox clusters to skip TLS verification..."
for ctx in "$GLOBAL_CONTEXT" "$ADMIN_CLUSTER_CONTEXT" "$USER_CLUSTER_CONTEXT"; do
    if [ -n "$ctx" ]; then
        CLUSTER_NAME=$(kubectl config view -o jsonpath="{.contexts[?(@.name=='$ctx')].context.cluster}" 2>/dev/null || true)
        if [ -n "$CLUSTER_NAME" ]; then
            echo "👉 Disabling TLS verification for cluster: $CLUSTER_NAME ($ctx)"
            kubectl config set-cluster "$CLUSTER_NAME" --insecure-skip-tls-verify=true >/dev/null
        fi
    fi
done

# 7. Final Verification & Execute
echo ""
echo "🚀 STEP 3: Launching Helm Workload Sync..."
# Verify list secrets permission before syncing
echo "🔍 Verifying Helm permissions..."
until kubectl --context "$GLOBAL_CONTEXT" get secrets -n "$IAC_PROJECT" >/dev/null 2>&1; do
    echo "...still waiting for secret permissions to propagate..."
    sleep 10
done

VERSION=${VERSION:-"-v1"} helmfile sync
