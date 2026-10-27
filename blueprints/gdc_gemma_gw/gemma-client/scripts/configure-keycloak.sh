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

# Clean trailing slashes and auto-append .dev if truncated at .cloudworkstations
WORKSTATION_URL="${WORKSTATION_URL%/}"
if [[ "$WORKSTATION_URL" == *.cloudworkstations ]]; then
    WORKSTATION_URL="${WORKSTATION_URL}.dev"
    echo "ℹ️  Auto-completed truncated '.cloudworkstations' suffix to: ${WORKSTATION_URL}"
fi

# 2. Extract base cluster domain mapping
# Matches "https://8081-w-username.cluster-hash.cloudworkstations.dev" or bare "w-username.cluster-hash..."
if [[ "$WORKSTATION_URL" =~ ^(http[s]?://)?([0-9]+-)?(w-[a-zA-Z0-9-]+)\.(.+)$ ]]; then
    DETECTED_PORT_PREFIX="${BASH_REMATCH[2]:-8081-}"
    VM_HOSTNAME="${BASH_REMATCH[3]}"
    BASE_DOMAIN="${BASH_REMATCH[4]}"
    DYNAMIC_FQDN="${DETECTED_PORT_PREFIX}${VM_HOSTNAME}.${BASE_DOMAIN}"
    FQDN_8080="8080-${VM_HOSTNAME}.${BASE_DOMAIN}"
    FQDN_8081="8081-${VM_HOSTNAME}.${BASE_DOMAIN}"
    FQDN_8082="8082-${VM_HOSTNAME}.${BASE_DOMAIN}"
    echo ""
    echo "🎯 Dynamic Identity Target Coordinates Discovered:"
    echo "   - Active Workstation VM Hostname: ${VM_HOSTNAME}"
    echo "   - Base Cluster Routing Suffix  : ${BASE_DOMAIN}"
    echo "   - Whitelisted Preview FQDNs    : ${FQDN_8080}, ${FQDN_8081}, ${FQDN_8082}"
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
# Omit hardcoded VITE_OIDC_AUTHORITY so oidc.js dynamically uses window.location.origin
# (allowing seamless access via Port 8081, Port 8082, or localhost port-forwarding).
echo "🔄 Baking secure preview parameters into static UI compilation environment..."
cat <<EOF > "$FRONTEND_ENV"
# Staging/Sandbox Web Preview Environment variables (Bakes into Vite JS Assets)
VITE_API_URL=/api
VITE_ENABLE_OIDC=true
VITE_OIDC_CLIENT_ID=rag-frontend
VITE_ENABLE_INTEL_CONSOLE=true
EOF
echo "   ✅ Baked Frontend Environment: src/frontend/.env (Dynamic Origin OIDC + Intel Console enabled)"

echo ""
echo "================================================="
echo "🎉 CONFIGURATION COMPLETED SUCCESSFULLY!"
echo ""
echo "To deploy this pre-configured identity perimeter inside GKE sandbox:"
echo "1. Run: kubectl apply -f gemma-client/manifests/gcp/keycloak-realm-import-hydrated.yaml -n gemma-inference"
echo "2. Run: kubectl apply -f gemma-client/manifests/gcp/keycloak-staging.yaml -n gemma-inference"
echo "3. Build & deploy backend.yaml and frontend.yaml, then apply gemma-client/manifests/gcp/nginx-ingress-staging.yaml!"
echo ""
