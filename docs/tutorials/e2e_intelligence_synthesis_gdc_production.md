# End-to-End Tutorial: Multi-Blueprint Intelligence Synthesis & Decision Support
## Deploying & Operating on Google Distributed Cloud Air-Gapped (GDC-ag) Production

> **Document ID:** `TUT-GDC-E2E-INTEL-SYNTHESIS`  
> **Version:** 1.1  
> **Target Environment:** Google Distributed Cloud Air-Gapped (GDC-ag) Production Rack  
> **Companion Emulation Guide:** [Testing & Demonstrating on GCP GKE Emulation Environment](./e2e_intelligence_synthesis_gcp_emulation.md)  
> **Integrated Blueprints:** P4 (Kafka Event Stream), P6 (Resilient RAG Agent), P7 (Agentic Data Analyst), P5/Gateway (`gdc_gemma_gw`), P10/Client (`gemma-client`), P12 (Keycloak OIDC)  
> **Mission Scenario:** *Operation Vanguard Shield* — Multi-Domain Operations (MDO) across Land, Air, Sea, Space, and Cyberspace.

---

## 1. Overview & GDC-ag Production Architecture

This tutorial provides the complete, step-by-step runbook for packaging, transferring across the air gap, deploying, and verifying the **Multi-Blueprint Intelligence Synthesis & Decision Support** solution on **Google Distributed Cloud air-gapped (GDC-ag)** hardware.

### Production Topology Across Shared GPU & Tenant Mission Namespaces

```text
 ┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                         GDC AIR-GAPPED (GDC-ag) PRODUCTION TOPOLOGY                               │
 └───────────────────────────────────────────────────────────────────────────────────────────────────┘

   [ Operator Browser (DoD PKI / Enterprise CA) ]
                         │
                         ▼  https://app.gdc.local  (or https://intel-console.gdc.local)
   ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
   │  TRAFFIC EXPOSURE LAYER (Choose Path A: K8s Gateway API  OR  Path B: GDC Internal LB Ingress)  │
   │  • Path A (Recommended): Gateway (gdc-platform-gateway) + HTTPRoute (gemma-unified-routes)      │
   │  • Path B (Alternative): GDC ILB Ingress (networking.gdc.goog/internal-loadbalancer: "true")   │
   └──────────────────┬───────────────────────────────┬───────────────────────────────┬──────────────┘
                      │ (/auth)                       │ (/api)                        │ (/)
                      ▼                               ▼                               ▼
            [Keycloak HA Cluster]          [gemma-client Backend] ◄──────── [gemma-client Frontend]
         (P12 OIDC + AD/LDAP Fed.)         (FastAPI Aggregator)              (React + Non-Root NGINX)
                                                      │
         ┌────────────────────────────────────────────┼────────────────────────────────────────────┐
         │                                            │                                            │
         ▼                                            ▼                                            ▼
 ┌───────────────────────────────┐    ┌───────────────────────────────┐    ┌───────────────────────────────┐
 │ [P4] Apache Kafka KRaft       │    │ [P6 & P7] GDC Managed DB      │    │ [P5] Gemma Inference Gateway  │
 │ • StatefulSet (3-Node HA)     │    │ • DBCluster (ZONAL_HA PG 14+) │    │ • Dynamic Prompt Classifier   │
 │ • Topic: multi-domain-telemetry│   │ • pgvector + Read-Only Guard  │    │ • NetworkPolicy Whitelisted   │
 │ • telemetry-consumer Daemon   │───►│ • GDC Object Storage Bucket   │    └───────────────┬───────────────┘
 └───────────────────────────────┘    └───────────────────────────────┘                    │
                                                                            ┌──────────────┴──────────────┐
                                                                            │                             │
                                                                 (Simple / Lookup)             (Complex / Tactical CoT)
                                                                            ▼                             ▼
                                                                  ┌───────────────────┐         ┌───────────────────┐
                                                                  │ vLLM Gemma 4 26B  │         │ vLLM Gemma 4 31B  │
                                                                  │ • Pool: gpu-moe   │         │ • Pool: gpu-dense │
                                                                  │ • PVC: standard-rwx│        │ • PVC: standard-rwx│
                                                                  └───────────────────┘         └───────────────────┘
```

### Key Differences from the GCP GKE Emulation Sandbox

| Component | GCP GKE Sandbox Emulation | GDC-ag Production Deployment |
| :--- | :--- | :--- |
| **Container Registry** | Google Artifact Registry (`${REGION}-docker.pkg.dev`) | Internal Harbor Registry (`harbor.gdc.local/library` & `harbor.gdc.local/blueprint-images`) |
| **Inference Engine** | Ollama (4-bit GGUF on 1x NVIDIA L4) | **vLLM Distributed Serving** (FP16/FP8 on NVIDIA H100/H200 with PagedAttention; Ollama supported for tactical edge) |
| **Model Weight Storage** | Baked into container layer for rapid PoC | **GDC SAN PersistentVolumeClaim** (`storageClassName: standard-rwx`, `ReadWriteMany`, 150Gi) |
| **Database Tier** | Single-pod `pgvector/pgvector:pg16` StatefulSet | **GDC Managed Database Service** (`postgresql.dbadmin.gdc.goog/v1` `DBCluster` with `ZONAL_HA`) |
| **Object Storage** | Google Cloud Storage (`gs://`) or In-DB seed | **GDC Native Object Storage** (`object.gdc.goog/v1` `Bucket` + `iam.gdc.goog/v1` `IAMPolicyBinding`) |
| **Traffic Exposure** | `kubectl port-forward` to `gemma-ingress-gateway` or `gdc-gateway-tunnel` | **GDC Platform Hardware Load Balancer** via Kubernetes Gateway API (`HTTPRoute`) or GDC Internal LB `Ingress` |

---

## 2. Stage 1: Connected Staging Workstation — Building & Packaging for the Air Gap

Perform this stage on an internet-connected staging workstation that has access to both `gdc_gemma_gw` and `GDC-blueprints` before crossing the air-gapped boundary.

### 2.1. Export Target GDC Coordinates

```bash
export PROJECT_ID="gdc-intel-prod"
export NAMESPACE="gemma-inference"
export REGISTRY_HOST="harbor.gdc.local/library"
export BLUEPRINT_REGISTRY="harbor.gdc.local/blueprint-images"
export TAG="latest"
```

### 2.2. Build Hardened Application & Gateway Container Images

All images enforce non-root execution (`USER 1000` / `10101`), upgraded base layers (`debian:trixie-slim` / `python:3.11-slim`), and P0 CVE-remediated dependencies:

```bash
cd ~/GitHub/gdc_gemma_gw

# 1. Build Gemma 4 Inference Gateway Proxy
docker build -t "${REGISTRY_HOST}/gemma-proxy:${TAG}" standalone/
docker tag "${REGISTRY_HOST}/gemma-proxy:${TAG}" "${REGISTRY_HOST}/gemma-gateway:${TAG}"

# 2. Configure Frontend OIDC + Intelligence Console Flags & Build gemma-client
cat << 'EOF' > gemma-client/src/frontend/.env
VITE_API_URL=/api
VITE_ENABLE_OIDC=true
VITE_OIDC_CLIENT_ID=rag-frontend
VITE_ENABLE_INTEL_CONSOLE=true
EOF

docker build -t "${REGISTRY_HOST}/gemma-client-backend:${TAG}" gemma-client/src/backend
docker build -t "${REGISTRY_HOST}/gemma-client-frontend:${TAG}" gemma-client/src/frontend

# 3. Build Pattern 4 Multi-Domain Telemetry Stream Consumer
docker build -t "${REGISTRY_HOST}/telemetry-consumer:${TAG}" glue-code/telemetry-consumer
docker tag "${REGISTRY_HOST}/telemetry-consumer:${TAG}" "${BLUEPRINT_REGISTRY}/p4-consumer:${TAG}"

# 4. Build Supporting Blueprint Microservices (P6 RAG & P7 SQL Agent)
BLUEPRINTS_DIR="${BLUEPRINTS_DIR:-../GDC-blueprints}"
if [ -d "${BLUEPRINTS_DIR}" ]; then
  docker build -t "${BLUEPRINT_REGISTRY}/rag-ingest:${TAG}" "${BLUEPRINTS_DIR}/p6-resilient-rag-agent/example-app/ingest-service"
  docker build -t "${BLUEPRINT_REGISTRY}/rag-query:${TAG}" "${BLUEPRINTS_DIR}/p6-resilient-rag-agent/example-app/query-service"
  docker build -t "${BLUEPRINT_REGISTRY}/p7-agent:${TAG}" "${BLUEPRINTS_DIR}/p7-agentic-data-analyst/example-app/agent"
fi
```

### 2.3. Create Air-Gapped Transfer Bundles & Verify Checksum BOM

Package the container tarballs, Helm charts (`blueprints/vllm-gke`, `standalone/chart`, `gemma-client/chart`), and Kubernetes manifests:

```bash
cd ~/GitHub/gdc_gemma_gw
chmod +x scripts/package-for-gdc.sh

# Package vLLM Production Serving + Gateway (or set INFERENCE_ENGINE=ollama for tactical edge racks)
INFERENCE_ENGINE=vllm REGISTRY_HOST="${REGISTRY_HOST}" TAG="${TAG}" ./scripts/package-for-gdc.sh

# Package Gemma Client Console
INFERENCE_ENGINE=client REGISTRY_HOST="${REGISTRY_HOST}" TAG="${TAG}" ./scripts/package-for-gdc.sh

# Export Kafka Broker, Telemetry Consumer, and Test Seed Data into the staging bundle
docker pull apache/kafka:3.9.0
docker tag apache/kafka:3.9.0 "${REGISTRY_HOST}/kafka:3.9.0"
docker save \
  "${REGISTRY_HOST}/kafka:3.9.0" \
  "${REGISTRY_HOST}/telemetry-consumer:${TAG}" \
  -o packages/gemma-gateway-gdc/e2e-telemetry-images.tar

tar -czf packages/gemma-gateway-gdc/e2e-intel-assets.tar.gz \
  blueprints/p4-kafka/ \
  glue-code/telemetry-consumer/ \
  test-data/ \
  scripts/simulate_multidomain_telemetry.py

# Verify SHA-256 Bill of Materials (BOM) before physical media transfer
cat packages/gemma-gateway-gdc/gemma-gateway-BOM.txt
```

Transfer the `packages/gemma-gateway-gdc/` directory and your unquantized Hugging Face model snapshots (`google/gemma-4-26b-it` and `google/gemma-4-31b-it`) across the air-gapped boundary to your GDC-ag Operator Workstation.

---

## 3. Stage 2: Disconnected GDC-ag Workstation — Registry Ingestion & SAN Weight Staging

Execute the following steps from your **GDC-ag Operator Workstation** inside the disconnected perimeter.

### 3.1. Authenticate to Internal Harbor & Push Images

```bash
export PROJECT_ID="gdc-intel-prod"
export NAMESPACE="gemma-inference"
export REGISTRY_HOST="harbor.gdc.local/library"
export TAG="latest"

# 1. Verify SHA-256 integrity after transfer
cd packages/gemma-gateway-gdc
shasum -a 256 -c gemma-gateway-BOM.txt
cd ../..

# 2. Authenticate Docker to the internal Harbor registry
docker login harbor.gdc.local

# 3. Load and push Gateway, Serving, Client, and Telemetry images
for archive in \
  packages/gemma-gateway-gdc/gateway/vllm/gemma-gateway-gdc-images.tar \
  packages/gemma-gateway-gdc/client/gemma-gateway-gdc-images.tar \
  packages/gemma-gateway-gdc/e2e-telemetry-images.tar; do
  if [ -f "${archive}" ]; then
    docker load -i "${archive}"
  fi
done

docker push "${REGISTRY_HOST}/gemma-proxy:${TAG}"
docker push "${REGISTRY_HOST}/vllm-gemma-26b:${TAG}"
docker push "${REGISTRY_HOST}/vllm-gemma-31b:${TAG}"
docker push "${REGISTRY_HOST}/gemma-client-backend:${TAG}"
docker push "${REGISTRY_HOST}/gemma-client-frontend:${TAG}"
docker push "${REGISTRY_HOST}/telemetry-consumer:${TAG}"
docker push "${REGISTRY_HOST}/kafka:3.9.0"

# 4. Extract manifests and Helm charts
tar -xzf packages/gemma-gateway-gdc/gateway/vllm/gemma-gateway-gdc-manifests.tar.gz
tar -xzf packages/gemma-gateway-gdc/client/gemma-client-manifests.tar.gz
tar -xzf packages/gemma-gateway-gdc/e2e-intel-assets.tar.gz
```

---

## 4. Stage 3: Provisioning GDC-ag Native Managed Infrastructure

### 4.1. Create Target Namespace & Dedicated GPU NodePools

Ensure the target namespace exists and dedicated GPU pools (`gpu-moe` for Gemma 4 26B MoE and `gpu-dense` for Gemma 4 31B Dense) are provisioned on your GDC cluster:

```bash
kubectl apply -f standalone/manifests/00-namespace.yaml
```

If GPU node pools are not yet provisioned on the cluster, apply the GDC Cluster API `NodePool` definitions against the management plane:

```yaml
# gdc-gpu-nodepools.yaml
apiVersion: cluster.gdc.goog/v1
kind: NodePool
metadata:
  name: gpu-moe
  namespace: platform
spec:
  clusterName: shared-gpu-cluster
  nodeCount: 1
  machineType: hgx-h100-1g
  labels:
    pool: gpu-moe
  taints:
  - key: nvidia.com/gpu
    value: "present"
    effect: NoSchedule
---
apiVersion: cluster.gdc.goog/v1
kind: NodePool
metadata:
  name: gpu-dense
  namespace: platform
spec:
  clusterName: shared-gpu-cluster
  nodeCount: 1
  machineType: hgx-h100-1g
  labels:
    pool: gpu-dense
  taints:
  - key: nvidia.com/gpu
    value: "present"
    effect: NoSchedule
```

### 4.2. Provision GDC Managed PostgreSQL HA (`DBCluster`) & Seed Operational Schema

In GDC-ag production, PostgreSQL is provisioned via the GDC Database Operator (`postgresql.dbadmin.gdc.goog/v1` `DBCluster`) using `gemma-client/manifests/gdc/db/postgres.yaml`:

```bash
# 1. Hydrate namespace and apply GDC Managed PostgreSQL HA cluster
sed "s|namespace: test-project|namespace: ${NAMESPACE}|g" \
  gemma-client/manifests/gdc/db/postgres.yaml | kubectl apply -f -

# 2. Wait for the GDC Database Operator to mark gemini-db Ready
kubectl wait --for=condition=Ready dbcluster/gemini-db -n "${NAMESPACE}" --timeout=600s

# 3. Retrieve the GDC Database Operator endpoint & credentials and create the backend secret
# (Adjust DB_HOST and DB_PASSWORD to match the secret generated by the DBCluster operator in your environment)
export DB_HOST="${DB_HOST:-gemini-db.${NAMESPACE}.svc.cluster.local}"
export DB_PASSWORD="${DB_PASSWORD:?Set DB_PASSWORD from your DBCluster operator secret}"

kubectl create serviceaccount gemma-client-sa -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create serviceaccount gemini-gui-sa -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

for secret_name in gemma-client-db-credentials gemini-gui-db-credentials; do
  kubectl create secret generic "${secret_name}" \
    --from-literal=connection_string="postgresql://postgres:${DB_PASSWORD}@${DB_HOST}:5432/postgres" \
    -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
done

# 4. Seed the Operation Vanguard Shield readiness & intelligence tables and create the read-only SQL audit role
kubectl run pg-seed-job --rm -i --restart=Never \
  --image="${REGISTRY_HOST}/gemma-client-backend:${TAG}" \
  -n "${NAMESPACE}" \
  --env="DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@${DB_HOST}:5432/postgres" \
  --command -- python3 -c "
import asyncio, asyncpg
with open('/dev/stdin') as f:
    sql = f.read()
async def main():
    conn = await asyncpg.connect('postgresql://postgres:${DB_PASSWORD}@${DB_HOST}:5432/postgres')
    await conn.execute(sql)
    await conn.close()
    print('Seeded GDC Managed PostgreSQL successfully.')
asyncio.run(main())
" < test-data/seed_readiness_db.sql
```

### 4.3. Bind GDC Native Object Storage IAM Policy

Grant the client service account access to the GDC native object storage bucket (`roles/storage.objectAdmin`):

```bash
sed "s|namespace: test-project|namespace: ${NAMESPACE}|g" \
  gemma-client/manifests/gdc/security/iam-policy-binding.yaml | kubectl apply -f -
```

---

## 5. Stage 4: Deploying Inference Serving Pools & Gemma Gateway

You can deploy the inference tier using either **Method A (Direct Helm & Manifests)** or **Method B (`gdc-iac-org` Layered Helmfile / ArgoCD Factory)**.

### Method A: Direct Helm & Manifest Deployment

#### 1. Deploy vLLM Serving Pools Backed by GDC SAN (`standard-rwx`)
`blueprints/vllm-gke/values-gdc.yaml` enforces `storageClassName: "standard-rwx"` (`ReadWriteMany`, `150Gi`) and GPU node pool affinity:

```bash
# 1. Deploy Gemma 4 26B A4B (MoE) on gpu-moe pool
helm upgrade --install vllm-26b ./blueprints/vllm-gke \
  --namespace "${NAMESPACE}" \
  -f ./blueprints/vllm-gke/values-gdc.yaml \
  --set image.repository="${REGISTRY_HOST}/vllm-gemma-26b" \
  --set image.tag="${TAG}" \
  --set nodeSelector.pool="gpu-moe"

# 2. Deploy Gemma 4 31B (Dense) on gpu-dense pool
helm upgrade --install vllm-31b ./blueprints/vllm-gke \
  --namespace "${NAMESPACE}" \
  -f ./blueprints/vllm-gke/values-gdc.yaml \
  --set image.repository="${REGISTRY_HOST}/vllm-gemma-31b" \
  --set image.tag="${TAG}" \
  --set nodeSelector.pool="gpu-dense"
```

> **Note on Model Weights Staging:** If your `vllm-gemma-*` images do not have weights pre-baked, copy the Hugging Face model snapshots into the provisioned `standard-rwx` PVCs (`vllm-26b-vllm-gke-weights` and `vllm-31b-vllm-gke-weights`) using the helper pod procedure in the [GDC Production Serving Guide: vLLM & Gemma 4](../vllm-serving-guide.md).

#### 2. Deploy the Gemma 4 Inference Gateway Proxy (`standalone/manifests/01-gateway.yaml`)

```bash
sed "s|image: gemma-gateway:latest|image: ${REGISTRY_HOST}/gemma-proxy:${TAG}|g" \
  standalone/manifests/01-gateway.yaml | kubectl apply -n "${NAMESPACE}" -f -

kubectl rollout status deployment/gemma-gateway -n "${NAMESPACE}" --timeout=120s
```

---

### Method B: Orchestrated Deployment via Standardized Helm Wrapper Charts (`gdc-iac-org` Compatible)

Both `standalone/chart` and `gemma-client/chart` implement the standard `gdc.enabled` (Stage 2 Zonal CRDs) and `apps.enabled` (Stage 5 User Cluster Workloads) gates used by `gdc-iac-org`:

```bash
# 1. Deploy Gemma Gateway Proxy & HTTPRoute via Helm Wrapper Chart
helm upgrade --install gemma-gateway ./standalone/chart \
  --namespace "${NAMESPACE}" --create-namespace \
  --set global.projectId="${PROJECT_ID}" \
  --set global.namespace="${NAMESPACE}" \
  --set global.registry="${REGISTRY_HOST}" \
  --set apps.enabled=true

# 2. Deploy Gemma Client Backend, Frontend & HTTPRoute via Helm Wrapper Chart
helm upgrade --install gemma-client ./gemma-client/chart \
  --namespace "${NAMESPACE}" \
  --set global.projectId="${PROJECT_ID}" \
  --set global.namespace="${NAMESPACE}" \
  --set global.registry="${REGISTRY_HOST}" \
  --set gdc.enabled=false \
  --set apps.enabled=true \
  --set apps.enableOidc="true" \
  --set apps.keycloakUrl="http://keycloak-svc:8080/auth/realms/gdc-rag-realm" \
  --set apps.gatewayUrl="http://gemma-gateway/v1"
```

---

## 6. Stage 5: Deploying Mission Workloads & Configuring Traffic Exposure (Gateway API vs. Ingress)

### 6.1. Deploy Pattern 4 Kafka Broker & Multi-Domain Telemetry Consumer

```bash
# 1. Update Kafka image reference to internal Harbor registry and deploy StatefulSet
sed -e "s|apache/kafka:3.9.0|${REGISTRY_HOST}/kafka:3.9.0|g" \
    -e "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" \
    blueprints/p4-kafka/statefulset-kafka.yaml | kubectl apply -n "${NAMESPACE}" -f -

kubectl rollout status statefulset/kafka -n "${NAMESPACE}" --timeout=120s

# 2. Deploy Telemetry Consumer Daemon (pointing to GDC Managed PostgreSQL)
sed -e "s|REGISTRY_HOST_PLACEHOLDER|${REGISTRY_HOST}|g" \
    -e "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" \
    -e "s|postgresql://postgres:password@postgres-svc:5432/postgres|postgresql://postgres:${DB_PASSWORD}@${DB_HOST}:5432/postgres|g" \
    glue-code/telemetry-consumer/manifests/consumer-deployment.yaml | kubectl apply -n "${NAMESPACE}" -f -

kubectl rollout status deployment/telemetry-consumer -n "${NAMESPACE}" --timeout=90s
```

### 6.2. Deploy Joint Intelligence Console (`gemma-client` GDC Manifests)

If you did not already deploy `gemma-client` via Helm in Section 5 (Method B), apply the GDC workload manifests directly:

```bash
sed -e "s|us-central1-docker.pkg.dev/test-project/blueprint-images/p10-backend:latest|${REGISTRY_HOST}/gemma-client-backend:${TAG}|g" \
    -e "s|namespace: test-project|namespace: ${NAMESPACE}|g" \
    -e "s|value: \"test-project\"|value: \"${PROJECT_ID}\"|g" \
    gemma-client/manifests/gdc/apps/backend.yaml | kubectl apply -n "${NAMESPACE}" -f -

sed -e "s|us-central1-docker.pkg.dev/test-project/blueprint-images/p10-frontend:latest|${REGISTRY_HOST}/gemma-client-frontend:${TAG}|g" \
    -e "s|namespace: test-project|namespace: ${NAMESPACE}|g" \
    gemma-client/manifests/gdc/apps/frontend.yaml | kubectl apply -n "${NAMESPACE}" -f -

kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=90s
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=90s
```

### 6.3. Apply Zero-Trust NetworkPolicy for the Inference Gateway

Whitelist ingress to `gemma-gateway` port `8080` exclusively from authorized mission namespaces and platform load balancer CIDRs:

```bash
sed "s|kubernetes.io/metadata.name: test-project|kubernetes.io/metadata.name: ${NAMESPACE}|g" \
  gemma-client/manifests/gdc/security/gateway-network-policy.yaml | kubectl apply -n "${NAMESPACE}" -f -
```

---

### 6.4. Expose Unified Services: Choose Path A (Kubernetes Gateway API) OR Path B (GDC Internal LB Ingress)

GDC-ag supports two production traffic exposure patterns. Both patterns preserve a unified origin for `/auth`, `/api`, and `/` so Keycloak OIDC tokens and browser sessions operate without cross-origin errors.

| Dimension | Path A: Kubernetes Gateway API (`Gateway` + `HTTPRoute`) — Recommended | Path B: GDC Internal Load Balancer (`Ingress`) |
| :--- | :--- | :--- |
| **API Group** | `gateway.networking.k8s.io/v1` (`HTTPRoute`) | `networking.k8s.io/v1` (`Ingress` with `networking.gdc.goog/internal-loadbalancer: "true"`) |
| **Manifests** | `gemma-client/manifests/gdc/security/production-gateway-routing.yaml` & `standalone/manifests/02-gateway-httproute.yaml` | `gemma-client/manifests/gdc/security/cross-cluster-gateway-ingress.yaml` (+ unified client Ingress) |
| **Header & Path Rewriting** | Native `RequestHeaderModifier` (`X-Forwarded-Proto: https`) & `URLRewrite` (`ReplacePrefixMatch: /` on `/api`) | Standard NGINX / GDC Ingress controller annotations |
| **When to Choose** | Standard GDC-ag 1.14+ clusters using the platform Envoy Gateway (`gdc-platform-gateway`). | Legacy Ingress-based GDC-ag environments or cross-cluster ILB peering (`gemma-gateway.shared-services.gdc.local`). |

#### Path A: Expose via Kubernetes Gateway API (`HTTPRoute` — Primary Production Path)

```bash
# 1. Apply the unified client HTTPRoute (/auth -> keycloak-svc, /api -> backend-svc, / -> frontend-svc)
sed "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" \
  gemma-client/manifests/gdc/security/production-gateway-routing.yaml | kubectl apply -n "${NAMESPACE}" -f -

# 2. (Optional) Expose gemma-gateway directly for external/cross-cluster API consumers
sed "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" \
  standalone/manifests/02-gateway-httproute.yaml | kubectl apply -n "${NAMESPACE}" -f -

# 3. Verify HTTPRoute acceptance and retrieve the GDC Platform Gateway VIP
kubectl get httproute gemma-unified-routes -n "${NAMESPACE}" -o yaml
kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}"
```

#### Path B: Expose via GDC Internal Load Balancer (`Ingress` — Alternative Path)

1. Expose `gemma-gateway` across clusters using `gemma-client/manifests/gdc/security/cross-cluster-gateway-ingress.yaml`:
   ```bash
   sed "s|namespace: test-project|namespace: ${NAMESPACE}|g" \
     gemma-client/manifests/gdc/security/cross-cluster-gateway-ingress.yaml | kubectl apply -n "${NAMESPACE}" -f -
   ```
2. Expose the unified console (`/auth`, `/api`, `/`) via a GDC Internal Load Balancer `Ingress`:
   ```bash
   cat <<EOF | kubectl apply -n "${NAMESPACE}" -f -
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: gemma-unified-ingress
     namespace: ${NAMESPACE}
     annotations:
       networking.gdc.goog/internal-loadbalancer: "true"
       nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
       nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
   spec:
     rules:
     - host: app.gdc.local
       http:
         paths:
         - path: /auth
           pathType: Prefix
           backend:
             service:
               name: keycloak-svc
               port:
                 number: 8080
         - path: /api
           pathType: Prefix
           backend:
             service:
               name: backend-svc
               port:
                 number: 8000
         - path: /
           pathType: Prefix
           backend:
             service:
               name: frontend-svc
               port:
                 number: 80
   EOF
   kubectl get ingress -n "${NAMESPACE}"
   ```

Ensure `app.gdc.local` (and `gemma-gateway.shared-services.gdc.local` if using cross-cluster routing) resolves in your air-gapped DNS (or `/etc/hosts` on operator workstations) to the VIP assigned to `gdc-platform-gateway` (Path A) or `gemma-unified-ingress` (Path B).

---

## 7. Stage 6: Guided Production Verification & Mission Walkthrough

### 7.1. Terminal-Only Pre-Flight Health Checks (Hardened Non-Root Containers)

Because production containers strip `curl` and shell utilities to minimize CVE surface area, verify internal service connectivity using Python's built-in `urllib.request`:

```bash
# 1. Verify Gemma Gateway health and discovered vLLM models
kubectl exec -i deployment/gemma-gateway -n "${NAMESPACE}" -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/v1/models', timeout=10).read().decode())"

# 2. Verify Backend API health and database connectivity
kubectl exec -i deployment/backend -n "${NAMESPACE}" -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health', timeout=10).read().decode())"

# 3. Verify Kafka consumer group offset lag on kafka-0
kubectl exec -i kafka-0 -n "${NAMESPACE}" -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group telemetry-processor-group \
  --describe
```

### 7.2. Validating the 5 Mission Functions in the Console (`https://app.gdc.local`)

Navigate to **`https://app.gdc.local`** in your operator browser and authenticate via Keycloak OIDC:
* **Analyst Persona (`alice` / `password` or AD group `gdc-intel-analysts`)**: Maps to `role: user`.
* **Commander Persona (`charlie` / `password` or AD group `gdc-intel-commanders`)**: Maps to `role: admin`.

1. **Function 1 — Multi-Domain Sensor Ingestion (P4 Kafka Feeds):**
   * Open the **Tactical Feeds (Kafka)** tab and click **"⚡ Ingest Sensor Pings"** (or run `python3 scripts/simulate_multidomain_telemetry.py --mode stream --interval 2.0`).
   * Confirm live LAND, AIR, SEA, SPACE, and CYBER telemetry rows populate with sub-second ingestion latency.
2. **Function 2 & 3 — All-Source Intelligence Synthesis (P6 RAG):**
   * Switch to the **All-Source Intel (RAG)** tab and submit:
     > *"What vulnerabilities were identified for supply convoys along Route 9 in Sector 9?"*
   * Verify the grounded synthesis cites `[SITREP-2026-08-SEC9-CONVOY]`, identifying Route 9's **AMBER** status at Waypoint Echo and FOB Bravo's critical **6 Days of Supply** of JP-8 fuel.
3. **Function 4 — Sub-Second Dynamic Heuristic Routing (Gemma Gateway + vLLM):**
   * Open **Tactical Chat**:
     * Submit a low-complexity lookup (*"Summarize the role of the 16th Space Surveillance Squadron."*) $\rightarrow$ verify the header badge updates to **`Gemma 4 26B (MoE)`** (`vllm-26b` pool).
     * Submit a multi-domain reasoning prompt (*"Correlate the latest cyber SCADA port scan telemetry at FOB Alpha with acoustic ground sensor detections on Route 9. Assess adversary intent and recommend an alternate supply routing plan."*) $\rightarrow$ verify automatic routing to **`Gemma 4 31B (Dense)`** (`vllm-31b` pool) with zero weight-swapping delay because both vLLM pools remain permanently resident in dedicated GPU VRAM.
4. **Function 5 — Plain-English Operational Database Audit (P7 Read-Only SQL Analyst):**
   * Switch to the **Operational Readiness (SQL)** tab and submit:
     > *"List all military units in Sector 9 with combat readiness below C2."*
   * Verify the **`🔒 Read-Only Guard Verified`** badge, sub-second vLLM NL-to-SQL generation, and the resulting readiness table (`9th Stryker Brigade Combat Team` at `C3`, `12th Cavalry Reconnaissance Squadron` at `C3`, and `588th Brigade Engineer Battalion` at `C4`).
