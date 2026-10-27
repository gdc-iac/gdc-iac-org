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
for i in {1..15}; do
  if kubectl exec postgres-0 -n "${NAMESPACE}" -- pg_isready -U postgres >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
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
cat << 'EOF' > gemma-client/src/frontend/.env
VITE_API_URL=/api
VITE_ENABLE_OIDC=true
VITE_OIDC_CLIENT_ID=rag-frontend
VITE_ENABLE_INTEL_CONSOLE=true
EOF
chmod +x gemma-client/scripts/build.sh
./gemma-client/scripts/build.sh -p "${PROJECT_ID}" -r "${REGISTRY_HOST}"

# Ensure Keycloak realm import ConfigMap (with wildcard Cloud Workstation preview support) is applied
kubectl apply -f gemma-client/manifests/gcp/keycloak-realm-import.yaml -n "${NAMESPACE}"
if kubectl get deployment keycloak -n "${NAMESPACE}" >/dev/null 2>&1; then
  kubectl rollout restart deployment/keycloak -n "${NAMESPACE}"
  kubectl rollout status deployment/keycloak -n "${NAMESPACE}" --timeout=90s || true
fi

# Ensure GCS Object Storage bucket exists and bind Workload Identity for gemma-client-sa
export BUCKET_NAME="gs://gemma-client-files-${PROJECT_ID}"
export GSA_NAME="gemma-client-sa"
export KSA_NAME="gemma-client-sa"

if ! gcloud storage buckets describe "${BUCKET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "[+] Creating GCS Object Storage bucket ${BUCKET_NAME} in ${REGION}..."
  gcloud storage buckets create "${BUCKET_NAME}" --project="${PROJECT_ID}" --location="${REGION}" --uniform-bucket-level-access || true
else
  echo "[+] GCS Object Storage bucket ${BUCKET_NAME} verified."
fi

if ! gcloud iam service-accounts describe "${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${GSA_NAME}" --project="${PROJECT_ID}" || true
fi

gcloud storage buckets add-iam-policy-binding "${BUCKET_NAME}" \
  --member="serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin" --quiet >/dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin" \
  --condition=None --quiet >/dev/null 2>&1 || true

gcloud iam service-accounts add-iam-policy-binding "${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]" --quiet >/dev/null 2>&1 || true

# Ensure required ServiceAccount (with Workload Identity annotation) and PostgreSQL credentials secret exist
kubectl create serviceaccount "${KSA_NAME}" -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl annotate serviceaccount "${KSA_NAME}" -n "${NAMESPACE}" \
  "iam.gke.io/gcp-service-account=${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" --overwrite

kubectl create secret generic gemma-client-db-credentials \
  --from-literal=username=postgres \
  --from-literal=password=password \
  --from-literal=db_name=postgres \
  --from-literal=connection_string="postgresql://postgres:password@postgres-svc:5432/postgres" \
  -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Hydrate and apply manifests
sed -i "s|image: .*gemma-client-backend:.*|image: ${REGISTRY_HOST}/gemma-client-backend:latest|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|image: .*gemma-client-frontend:.*|image: ${REGISTRY_HOST}/gemma-client-frontend:latest|g" gemma-client/manifests/apps/frontend.yaml
sed -i "s|PROJECT_ID_PLACEHOLDER|${PROJECT_ID}|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|INPUT_BUCKET_PLACEHOLDER|gemma-client-files-${PROJECT_ID}|g" gemma-client/manifests/apps/backend.yaml

kubectl apply -f gemma-client/manifests/apps/backend.yaml -n "${NAMESPACE}"
kubectl set env deployment/backend \
  PROJECT_ID="${PROJECT_ID}" \
  INPUT_BUCKET="${BUCKET_NAME}" \
  ENABLE_OIDC="true" \
  KEYCLOAK_URL="http://keycloak-svc:8080/auth/realms/gdc-rag-realm" \
  -n "${NAMESPACE}"

if [ "$(kubectl get svc frontend-svc -n "${NAMESPACE}" -o jsonpath='{.spec.type}' 2>/dev/null || true)" = "LoadBalancer" ]; then
  kubectl delete svc frontend-svc -n "${NAMESPACE}" --ignore-not-found
fi
kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n "${NAMESPACE}"

echo "[+] Waiting for frontend and backend rollouts..."
kubectl rollout restart deployment/backend deployment/frontend -n "${NAMESPACE}"
kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=90s
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=90s

# 7. Configure Traffic Exposure (Path A: NGINX Staging Ingress vs. Path B: GKE Gateway API + L4 Tunnel)
echo "[6/6] Verifying Ingress / Gateway API routing..."
INGRESS_MODE="${INGRESS_MODE:-auto}"

if [ "${INGRESS_MODE}" = "gateway" ] || ( [ "${INGRESS_MODE}" = "auto" ] && kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" >/dev/null 2>&1 ); then
  kubectl apply -f gemma-client/manifests/gcp/gateway-api-staging.yaml -n "${NAMESPACE}"
  kubectl apply -f gemma-client/manifests/gdc/security/production-gateway-routing.yaml -n "${NAMESPACE}"
  GATEWAY_VIP=$(kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || true)
  if [ -n "${GATEWAY_VIP}" ] && kubectl get deployment gdc-gateway-tunnel -n "${NAMESPACE}" >/dev/null 2>&1; then
    kubectl set env deployment/gdc-gateway-tunnel GATEWAY_VIP="${GATEWAY_VIP}" -n "${NAMESPACE}"
    kubectl rollout status deployment/gdc-gateway-tunnel -n "${NAMESPACE}" --timeout=60s || true
  fi
fi

if [ "${INGRESS_MODE}" = "nginx" ] || [ "${INGRESS_MODE}" = "auto" ]; then
  kubectl apply -f gemma-client/manifests/gcp/nginx-ingress-staging.yaml -n "${NAMESPACE}"
  kubectl rollout restart deployment/gemma-ingress-gateway -n "${NAMESPACE}"
  kubectl rollout status deployment/gemma-ingress-gateway -n "${NAMESPACE}" --timeout=90s || true
fi

echo "=============================================================================="
echo "✅ SOLUTION DEPLOYMENT COMPLETE!"
echo "=============================================================================="
echo ""
echo "To access the Joint Intelligence & Readiness Console, choose your routing path:"
echo ""
echo "Option A — NGINX Staging Ingress Proxy (Immediate / Default):"
echo "   pkill -f 'port-forward' || true"
echo "   kubectl port-forward service/gemma-ingress-gateway 8081:80 -n ${NAMESPACE}"
echo ""
echo "Option B — GKE Gateway API L7 RILB + L4 Tunnel (Full GDC HTTPRoute Parity):"
echo "   pkill -f 'port-forward' || true"
echo "   kubectl port-forward service/gdc-gateway-tunnel 8081:80 -n ${NAMESPACE}"
echo ""
echo "Then open in your browser: http://localhost:8081 (or Workstation Port 8081 Preview)"
echo "   • Analyst Login:   'alice' / 'password' (role: user)"
echo "   • Commander Login: 'charlie' / 'password' (role: admin)"
echo ""
echo "Run the synthetic sensor stream in the background (optional):"
echo "   python scripts/simulate_multidomain_telemetry.py --mode stream --interval 2.0"
echo "=============================================================================="
