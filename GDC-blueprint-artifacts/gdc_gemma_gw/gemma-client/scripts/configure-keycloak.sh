#!/bin/bash
# Dynamic Staging Configuration & Hydration Script for Keycloak OIDC
# Automatically detects loopbacks and workstation subdomains, and pre-packs dynamic environments.

set -e

# Determine the directory of this script so relative paths work
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="${SCRIPT_DIR}/../.."

# Target file paths
REALM_TEMPLATE="${SCRIPT_DIR}/../manifests/gcp/keycloak-realm-import.yaml"
REALM_HYDRATED="${SCRIPT_DIR}/../manifests/gcp/keycloak-realm-import-hydrated.yaml"
FRONTEND_ENV="${SCRIPT_DIR}/../src/frontend/.env"

echo "🔐 Gemma Dedicated Ingress Identity Configurator"
echo "================================================="

# 1. Acquire current browser preview URL to isolate the workstation hash
echo "To secure dynamic browser session handshakes, Keycloak requires your active"
echo "Google Cloud Workstation secure preview subdomain coordinates."
echo ""
echo "Please look at your laptop's browser URL bar inside the GCP Workstation preview,"
echo "and copy-paste your active Web Preview URL (e.g. https://80-w-user-...cloudworkstations.dev/)"
echo ""
read -p "Enter your active Workstation Web Preview URL: " WORKSTATION_URL

if [ -z "$WORKSTATION_URL" ]; then
    echo "❌ Error: Workstation Preview URL is required." >&2
    exit 1
fi

# Clean trailing slashes
WORKSTATION_URL="${WORKSTATION_URL%/}"

# 2. Extract base cluster domain mapping
# Matches "80-w-username.cluster-hash.cloudworkstations.dev" or "w-username.cluster-hash..."
# And converts to the standard Port 8081 preview domain
if [[ "$WORKSTATION_URL" =~ http[s]?://([0-9]+-)?(w-[a-zA-Z0-9-]+)\.(.+)$ ]]; then
    VM_HOSTNAME="${BASH_REMATCH[2]}"
    BASE_DOMAIN="${BASH_REMATCH[3]}"
    DYNAMIC_FQDN="8081-${VM_HOSTNAME}.${BASE_DOMAIN}"
    echo ""
    echo "🎯 Dynamic Identity Target Coordinates Discovered:"
    echo "   - Active Workstation VM Hostname: ${VM_HOSTNAME}"
    echo "   - Base Cluster Routing Suffix  : ${BASE_DOMAIN}"
    echo "   - Exposed Port 8081 Preview FQDN: ${DYNAMIC_FQDN}"
else
    # Fallback to direct input if regex fails
    echo "⚠️ Warning: Failed to parse preview URL regex automatically."
    echo "Using raw URL target domain instead..."
    DYNAMIC_FQDN=$(echo "$WORKSTATION_URL" | sed -e 's|^[^/]*//||' -e 's|/.*$||')
fi

# 3. Hydrate Staging Keycloak Realm Import
if [ -f "$REALM_TEMPLATE" ]; then
    echo ""
    echo "🔄 Hydrating dynamic whitelisted allowed origins inside GKE manifests..."
    sed "s|WORKSTATION_FQDN_PLACEHOLDER|${DYNAMIC_FQDN}|g" "$REALM_TEMPLATE" > "$REALM_HYDRATED"
    echo "   ✅ Staged GitOps Auto-Import Manifest: manifests/gcp/keycloak-realm-import-hydrated.yaml"
else
    echo "❌ Error: Base realm-import template not found at: ${REALM_TEMPLATE}" >&2
    exit 1
fi

# 4. Bake Vite Staging Variables into Frontend .env
echo "🔄 Baking secure preview parameters into static UI compilation environment..."
cat <<EOF > "$FRONTEND_ENV"
# Staging/Sandbox Web Preview Environment variables (Bakes into Vite JS Assets)
VITE_ENABLE_OIDC=true
VITE_OIDC_AUTHORITY=https://${DYNAMIC_FQDN}/auth/realms/gdc-rag-realm
VITE_OIDC_CLIENT_ID=rag-frontend
EOF
echo "   ✅ Baked Frontend Environment: src/frontend/.env"

echo ""
echo "================================================="
echo "🎉 CONFIGURATION COMPLETED SUCCESSFULLY!"
echo ""
echo "To deploy this pre-configured identity perimeter inside GKE sandbox:"
echo "1. Run: kubectl apply -f gemma-client/manifests/gcp/keycloak-realm-import-hydrated.yaml -n gemma-inference"
echo "2. Run: kubectl apply -f gemma-client/manifests/gcp/keycloak-staging.yaml -n gemma-inference"
echo "3. Rollout restart the deployments and rebuild standard client images!"
echo ""
