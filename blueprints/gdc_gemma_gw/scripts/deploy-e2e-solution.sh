#!/bin/bash
# ==============================================================================
# deploy-e2e-solution.sh
# End-to-End Automated Deployment Script for:
# AI-Powered Intelligence Synthesis & Decision Support System (Operation Vanguard Shield)
# ==============================================================================
set -e

# Repository Root
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
cd "${REPO_ROOT}"

# 1. Sanity Check Environment Variables
export PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
export NAMESPACE="${NAMESPACE:-gemma-inference}"
export REGION="${REGION:-us-west4}"
export REGISTRY_HOST="${REGISTRY_HOST:-${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo}"

if [ -z "${PROJECT_ID}" ]; then
  echo "[-] ERROR: PROJECT_ID is not set. Run: gcloud config set project <PROJECT_ID>"
  exit 1
fi

echo "=============================================================================="
echo "🚀 Deploying End-to-End Multi-Blueprint Intelligence Synthesis Solution"
echo "   Project ID:    ${PROJECT_ID}"
echo "   Namespace:     ${NAMESPACE}"
echo "   Registry:      ${REGISTRY_HOST}"
echo "=============================================================================="

# 2. Verify Pre-Requisites (Inference Gateway & Database Pod)
echo "[1/6] Verifying pre-requisite GKE infrastructure..."
if ! kubectl get pod postgres-0 -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "[-] ERROR: postgres-0 not found in namespace ${NAMESPACE}. Please complete Step 3.4 of quickstart_on_GCP.md first."
  exit 1
fi
echo "[+] PostgreSQL pod (postgres-0) verified."

if ! kubectl get service gemma-gateway -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "[!] WARNING: gemma-gateway service not found. Inference calls will fallback."
else
  echo "[+] Inference Gateway (gemma-gateway) verified."
fi

# 3. Seed Operational Readiness Database
echo "[2/6] Seeding operational readiness schema and intelligence data into PostgreSQL..."
kubectl exec -i postgres-0 -n "${NAMESPACE}" -- psql -U postgres -d postgres < test-data/seed_readiness_db.sql
echo "[+] Operational database seeded successfully (Units, Equipment, Fuel, Routes, Telemetry, Cables)."

# 4. Deploy Kafka Event Broker (P4)
echo "[3/6] Deploying Kafka Event Broker (KRaft mode)..."
sed -i "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" blueprints/p4-kafka/statefulset-kafka.yaml 2>/dev/null || true
kubectl apply -f blueprints/p4-kafka/statefulset-kafka.yaml -n "${NAMESPACE}"
echo "[+] Waiting for Kafka broker to start..."
kubectl rollout status statefulset/kafka -n "${NAMESPACE}" --timeout=120s || true

# 5. Deploy Telemetry Stream Consumer Daemon
echo "[4/6] Deploying Multi-Domain Telemetry Consumer..."
sed -e "s|REGISTRY_HOST_PLACEHOLDER|${REGISTRY_HOST}|g" \
    -e "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" \
    glue-code/telemetry-consumer/manifests/consumer-deployment.yaml | kubectl apply -n "${NAMESPACE}" -f - || true

# 6. Build and Deploy Joint Intelligence & Readiness Console (gemma-client)
echo "[5/6] Deploying updated Joint Intelligence & Readiness Console..."
grep -q "VITE_ENABLE_INTEL_CONSOLE" gemma-client/src/frontend/.env 2>/dev/null || echo "VITE_ENABLE_INTEL_CONSOLE=true" >> gemma-client/src/frontend/.env
chmod +x gemma-client/scripts/build.sh
./gemma-client/scripts/build.sh -p "${PROJECT_ID}" -r "${REGISTRY_HOST}"

# Hydrate and apply manifests
sed -i "s|image: .*gemma-client-backend:.*|image: ${REGISTRY_HOST}/gemma-client-backend:latest|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|image: .*gemma-client-frontend:.*|image: ${REGISTRY_HOST}/gemma-client-frontend:latest|g" gemma-client/manifests/apps/frontend.yaml

kubectl apply -f gemma-client/manifests/apps/backend.yaml -n "${NAMESPACE}"
kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n "${NAMESPACE}"

echo "[+] Waiting for frontend and backend rollouts..."
kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=90s
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=90s

# Ensure Gateway API L4 tunnel or fallback Ingress Gateway is refreshed
if kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" >/dev/null 2>&1; then
  GATEWAY_VIP=$(kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || true)
  if [ -n "${GATEWAY_VIP}" ] && kubectl get deployment gdc-gateway-tunnel -n "${NAMESPACE}" >/dev/null 2>&1; then
    kubectl set env deployment/gdc-gateway-tunnel GATEWAY_VIP="${GATEWAY_VIP}" -n "${NAMESPACE}"
    kubectl rollout status deployment/gdc-gateway-tunnel -n "${NAMESPACE}" --timeout=60s || true
  fi
elif kubectl get deployment gemma-ingress-gateway -n "${NAMESPACE}" >/dev/null 2>&1; then
  kubectl rollout restart deployment/gemma-ingress-gateway -n "${NAMESPACE}"
fi

echo "=============================================================================="
echo "✅ SOLUTION DEPLOYMENT COMPLETE!"
echo "=============================================================================="
echo ""
echo "To access the Joint Intelligence & Readiness Console:"
echo ""
echo "1. Forward the Gateway API L4 Tunnel (Port 8081):"
echo "   pkill -f 'port-forward' || true"
echo "   kubectl port-forward service/gdc-gateway-tunnel 8081:80 -n ${NAMESPACE}"
echo ""
echo "2. Open in your browser: http://localhost:8081"
echo "   (Log in with Keycloak user: 'alice' / 'password' or 'charlie' / 'password')"
echo ""
echo "3. Run the synthetic sensor stream in the background (optional):"
echo "   python scripts/simulate_multidomain_telemetry.py --mode stream --interval 2.0"
echo "=============================================================================="
