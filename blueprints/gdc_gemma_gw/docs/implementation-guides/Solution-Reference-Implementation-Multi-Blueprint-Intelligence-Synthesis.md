Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Multi-Blueprint: AI-Powered Intelligence Synthesis & Decision Support on GDC air-gapped**

> **Version:** 1.0  
> **Classification:** Air-Gapped Production Reference Architecture  
> **Integrated Patterns:** Pattern 4 (Kafka), Pattern 6 (RAG Agent), Pattern 7 (Agentic Data Analyst), Pattern 5 / Gateway (`gdc_gemma_gw`), Pattern 10 / Client (`gemma-client`), Pattern 12 (Keycloak OIDC)  
> **Target Platform:** Google Distributed Cloud air-gapped (GDC-ag)

---

## **1. Overview & Operational Problem Formulation**

In modern high-consequence defense and emergency management operations, decision superiority depends on the rapid fusion of **high-velocity sensor telemetry** and **unstructured historical intelligence**:

* **Multi-Domain Ingestion Surge:** Land, maritime, aerospace, orbital, and cyber sensor feeds arrive simultaneously. In disconnected environments without backpressure buffering, packet drops cause blind spots in situational awareness.
* **Unstructured Intelligence Latency:** Critical historical context sits trapped in textual After Action Reports (AARs) and SITREPs that human analysts cannot read fast enough during crisis events.
* **Database Opacity for Commanders:** Operational databases containing force readiness, ammunition stock, and convoy route statuses require database engineers to formulate SQL queries, creating decision latency.

This multi-blueprint solution integrates five foundational GDC patterns into an end-to-end air-gapped decision support system that continuously ingests, vectorizes, dynamically routes, and audits multi-domain operations.

---

## **2. Architecture & Data Flow Schematic**

```
                    ┌─────────────────────────────────────────────────────────┐
                    │       MULTI-DOMAIN SENSOR TELEMETRY FEEDS               │
                    │  (Land Radar, ADS-B Flight, AIS Marine, SATCOM, Cyber)  │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
                                                 ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │  [PATTERN 4] Event-Driven Kafka Pipeline                │
                    │  • Topic: multi-domain-telemetry                        │
                    │  • Buffers signal bursts across GDC fault domains       │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        │ (Stream Processor)                              │ (Raw Telemetry)
                        ▼                                                 ▼
  ┌───────────────────────────────────────────┐     ┌───────────────────────────────────────────┐
  │ [PATTERN 6] Resilient RAG Agent           │     │ [PATTERN 7] Operational Readiness DB      │
  │ • GDC Object Storage (SITREPs & Debriefs) │     │ • GDC Managed Database Service (Postgres) │
  │ • Vector Embeddings in pgvector           │     │ • Units, Equipment, Fuel, Convoy Routes  │
  │ • Semantic Grounded Context Retrieval     │     │ • Continuous Status Synchronization       │
  └─────────────────────┬─────────────────────┘     └─────────────────────┬─────────────────────┘
                        │                                                 │
                        │                                                 │
                        ▼                                                 ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
  │ [PATTERN 5 / GATEWAY] Gemma 4 Inference Gateway (gdc_gemma_gw)                             │
  │ • Reverse Proxy with Prompt Complexity Classifier & Heuristic Routing                      │
  │ • Lightweight / Lookup Routing ──────────► Gemma 4 26B A4B (MoE)                           │
  │ • Multi-Step Tactical Reasoning ─────────► Gemma 4 31B (Dense)                             │
  │                                                                                             │
  │ [INFERENCE ENGINE CHOICE - TRANSPARENT OPENAI-COMPATIBLE API]                               │
  │ • Option A (Quick Demo / Minimal Footprint): Ollama Engine (GGUF Quantized, Single L4/CPU)  │
  │ • Option B (Full Production Target): vLLM High-Performance Engine (A100/H100, PagedAttention)│
  └──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                 │
                                                 ▼
  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
  │ [PATTERN 10 & 12] Joint Intelligence & Readiness Console (gemma-client + Keycloak)          │
  │ • GDC Kubernetes Gateway API (gdc-shared-gateway / HTTPRoute)                             │
  │ • Enterprise OIDC Authentication & RBAC (Analyst vs Commander Personas)                     │
  │ • Unified Pane: Live Kafka Feeds, All-Source RAG Synthesis, Read-Only SQL Audit             │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## **3. Inference Engine Selection: Quick Demo (Ollama) vs. Full Production (vLLM)**

The solution supports two interchangeable backend engines. Because the **Gemma Inference Gateway** abstracts the model layer behind standard OpenAI-compatible endpoints (`/v1/chat/completions`), upstream clients (`gemma-client`, `sql-agent`, `rag-query`) require zero code changes when switching engines:

| Feature / Dimension | Option A: Quick Demo (Ollama Engine) | Option B: Full Production (vLLM Engine) |
| :--- | :--- | :--- |
| **Target Use Case** | Rapid PoC, local workstation testing, training labs, minimal hardware footprints. | Enterprise air-gapped production, high concurrency, tactical C2 operations. |
| **GPU / Hardware Profile** | Single NVIDIA L4 (24GB) or CPU offloading. Runs on basic worker node pools. | NVIDIA A100 (80GB) or H100 GPU pools. Requires dedicated GDC GPU node pools. |
| **Model Weights & Optimization**| GGUF 4-bit quantized weights (`gemma4:26b`, `gemma4:31b`). | Unquantized FP16 / FP8 weights with **PagedAttention**, continuous batching, and Tensor Parallelism. |
| **Concurrency & Latency** | Sequential/limited concurrency (~5–10 req/s). Higher per-token latency. | Massive concurrent serving (~50–150+ req/s) with sub-second time-to-first-token. |
| **Packaging Command** | `INFERENCE_ENGINE=ollama ./scripts/package-for-gdc.sh` | `INFERENCE_ENGINE=vllm ./scripts/package-for-gdc.sh` |
| **Deployment Resource** | `blueprints/ollama-gke/` / `standalone/manifests/` | Helm Chart `blueprints/vllm-gke/` with `values-gdc.yaml` SAN storage. |

---

## **4. Production Deployment vs Connected Sandbox Emulation**

| Dimension | Connected Staging Workstation (GKE) | GDC Air-Gapped Production Rack |
| :--- | :--- | :--- |
| **Inference Engine** | Ollama (Demo / Testing) | **vLLM Distributed Serving Engine** (or Ollama for lightweight clusters) |
| **Ingress & Networking** | Kubernetes Gateway API (`gdc-platform-gateway` + `HTTPRoute` via `service/gdc-gateway-tunnel`) | Kubernetes Gateway API standard (`gateway.networking.k8s.io/v1`) via Envoy L7 Load Balancer with mutual TLS. |
| **Object Storage** | Google Cloud Storage (GCS) with Workload Identity | GDC Native Object Storage Bucket (S3-compatible API with internal IAM credentials). |
| **Database Tier** | Ephemeral `pgvector/pgvector:pg16` StatefulSet | GDC Database Service (Managed PostgreSQL High Availability cluster across fault domains). |
| **Identity Provider** | Keycloak staging with in-memory H2 dev database | Keycloak clustered deployment backed by GDC Managed PostgreSQL, federated with corporate Active Directory / LDAP. |
| **Inference Hardware** | 1x NVIDIA L4 GPU with CPU layer offloading | Multi-node NVIDIA A100/H100 GPU pools (`gpu-moe` and `gpu-dense` node pools). |
| **Image Distribution** | Google Artifact Registry (`${REGION}-docker.pkg.dev`) | Air-gapped Harbor Registry (`harbor.gdc.local/library/`) with image signature verification. |
| **Deployment Standard**| Direct `kubectl apply` execution | GitOps declarative management via GDC Config Sync (`RepoSync` / `RootSync`). |

---

## **5. Step-by-Step Production Deployment on GDC air-gapped**

### **Phase 1: Connected Sideloading & Air-Gapped Packaging**

On your connected staging machine, run the automated packaging script to bundle manifests, custom images, and dependency charts into transferrable tarballs:

```bash
# 1. Hydrate blueprint parameters for GDC target
./configure-blueprints.sh \
  -p mission-intelligence-prod \
  -r harbor.gdc.local/library \
  -n intel-operations

# 2. Package core application blueprints
./scripts/package-for-gdc.sh p4-event-driven-kafka
./scripts/package-for-gdc.sh p6-resilient-rag-agent
./scripts/package-for-gdc.sh p7-agentic-data-analyst
./scripts/package-for-gdc.sh gemma-client

# 3. Package Model Serving Engine (Choose based on your deployment tier):
# ----------------------------------------------------------------------
# Option A (Quick Demo / Minimal Footprint):
INFERENCE_ENGINE=ollama ./scripts/package-for-gdc.sh p5-hybrid-llm-gateway

# Option B (Full Production vLLM Engine - Recommended for GDC):
INFERENCE_ENGINE=vllm ./scripts/package-for-gdc.sh p5-hybrid-llm-gateway

# 4. MANDATORY: Verify Bill of Materials (BOM)
cat packages/p4-event-driven-kafka/*-BOM.txt
cat packages/p6-resilient-rag-agent/*-BOM.txt
cat packages/p7-agentic-data-analyst/*-BOM.txt
```
*(Confirm there are zero entries listed under `MISSING / FAILED`).*

---

### **Phase 2: In-Boundary Image Ingestion (Harbor Registry)**

Transfer the generated `packages/` archives across the air gap into your secure GDC environment, then unpack and push images to your internal Harbor registry:

```bash
# Extract and load Docker images
./packages/p4-event-driven-kafka/helper-scripts/unpack-for-gdc.sh packages/p4-event-driven-kafka
./packages/p6-resilient-rag-agent/helper-scripts/unpack-for-gdc.sh packages/p6-resilient-rag-agent
./packages/p7-agentic-data-analyst/helper-scripts/unpack-for-gdc.sh packages/p7-agentic-data-analyst
./packages/gemma-client/helper-scripts/unpack-for-gdc.sh packages/gemma-client

# Push application images to internal Harbor registry
docker push harbor.gdc.local/library/p4-consumer:latest
docker push harbor.gdc.local/library/rag-query:v7
docker push harbor.gdc.local/library/rag-ingest:v7
docker push harbor.gdc.local/library/p7-agent:v1
docker push harbor.gdc.local/library/gemma-client-backend:latest
docker push harbor.gdc.local/library/gemma-client-frontend:latest

# Push Model Serving Images:
# For Option A (Ollama Demo):
# docker push harbor.gdc.local/library/ollama-gemma-26b:latest
# docker push harbor.gdc.local/library/ollama-gemma-31b:latest

# For Option B (vLLM Production):
docker push harbor.gdc.local/library/vllm-gemma-26b:latest
docker push harbor.gdc.local/library/vllm-gemma-31b:latest
docker push harbor.gdc.local/library/gemma-proxy:latest
```

---

### **Phase 3: Provision GDC Managed Platform Services**

#### 1. Provision GDC Managed PostgreSQL Cluster
Deploy a managed high-availability database cluster supporting both standard relational tables and the `pgvector` extension:

```yaml
apiVersion: database.gdc.goog/v1alpha1
kind: DatabaseInstance
metadata:
  name: operational-readiness-db
  namespace: intel-operations
spec:
  databaseVersion: POSTGRES_16
  tier: db-custom-8-32768
  storage:
    sizeGb: 200
  highAvailability:
    enabled: true
    faultDomains: ["zone-a", "zone-b"]
  extensions:
    - name: vector
    - name: "uuid-ossp"
```

#### 2. Provision GDC Native Object Storage Bucket
```yaml
apiVersion: storage.gdc.goog/v1alpha1
kind: Bucket
metadata:
  name: intelligence-debriefs-bucket
  namespace: intel-operations
spec:
  storageClass: Standard
  encryption:
    kmsKeyRef: "projects/mission-intelligence-prod/locations/global/keyRings/intel-ring/cryptoKeys/intel-key"
```

#### 3. Provision GDC Dedicated GPU NodePools (Required for Option B: vLLM)
In production GDC air-gapped environments, NVIDIA A100/H100 GPU pools are provisioned in the shared platform cluster:

```yaml
apiVersion: cluster.gdc.goog/v1
kind: NodePool
metadata:
  name: vllm-gpu-nodepool
  namespace: intel-operations
spec:
  clusterName: shared-platform-cluster
  nodeCount: 2
  machineType: a3-highgpu-1g-gdc  # GDC A100/H100 hardware type
  taints:
  - key: nvidia.com/gpu
    value: "present"
    effect: NoSchedule
```

---

### **Phase 4: Expose Unified Services via Kubernetes Gateway API**

In GDC production, the NGINX staging proxy is replaced by the standard **Kubernetes Gateway API** (`HTTPRoute`) bound to the platform's Envoy Gateway:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: intelligence-console-routes
  namespace: intel-operations
spec:
  parentRefs:
  - name: gdc-shared-gateway
    namespace: gdc-system
  hostnames:
  - "intel-console.gdc.local"
  rules:
  # 1. Route /auth/* to Clustered Keycloak
  - matches:
    - path:
        type: PathPrefix
        value: /auth/
    backendRefs:
    - name: keycloak-svc
      port: 8080

  # 2. Route /api/* to FastAPI Aggregator Backend
  - matches:
    - path:
        type: PathPrefix
        value: /api/
    backendRefs:
    - name: backend-svc
      port: 8000

  # 3. Route /* to React Static Console Frontend
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: frontend-svc
      port: 80
```

---

### **Phase 5: Deploy Model Serving & Mission Workloads**

#### 1. Deploy Model Serving Tier (Choose Option A or Option B)

##### Option A: Quick Demo / Minimal Footprint (Ollama Engine)
```bash
# Deploys lightweight GGUF models on single L4 GPU or CPU offloading
kubectl apply -f blueprints/ollama-gke/ -n intel-operations
```

##### Option B: Full Production Target (vLLM High-Performance Engine)
Deploy the unquantized Gemma 4 models using the production Helm chart bound to GDC SAN storage (`standard-rwx`):

```bash
# 1. Deploy Gemma 4 26B A4B (MoE) on GPU Pool 1
helm upgrade --install vllm-gemma-26b blueprints/vllm-gke \
  --namespace intel-operations \
  -f blueprints/vllm-gke/values-gdc.yaml \
  --set model.name="google/gemma-4-26b-it" \
  --set nodeSelector.pool="gpu-moe"

# 2. Deploy Gemma 4 31B (Dense) on GPU Pool 2
helm upgrade --install vllm-gemma-31b blueprints/vllm-gke \
  --namespace intel-operations \
  -f blueprints/vllm-gke/values-gdc.yaml \
  --set model.name="google/gemma-4-31b-it" \
  --set nodeSelector.pool="gpu-dense"
```

#### 2. Configure Gemma Inference Gateway Backend Targets
The Gateway routes dynamically based on prompt complexity. Point the gateway environment variables to your selected serving engine:

```yaml
# standalone/manifests/01-gateway.yaml
env:
  # For Option A (Ollama Demo):
  # - name: BACKEND_26B_URL
  #   value: "http://ollama-26b-service:11434"
  # - name: BACKEND_31B_URL
  #   value: "http://ollama-31b-service:11434"

  # For Option B (vLLM Production):
  - name: BACKEND_26B_URL
    value: "http://vllm-gemma-26b:8000/v1"
  - name: BACKEND_31B_URL
    value: "http://vllm-gemma-31b:8000/v1"
```

#### 3. Deploy Multi-Blueprint Workloads via GitOps (Config Sync)
Declare the multi-blueprint deployment in your internal GitLab repository under `manifests/intel-operations/`. Config Sync's `RepoSync` controller will continuously reconcile the desired cluster state:

```yaml
apiVersion: configsync.gke.io/v1beta1
kind: RepoSync
metadata:
  name: intel-operations-sync
  namespace: intel-operations
spec:
  sourceType: git
  git:
    repo: "https://gitlab.gdc.local/mission-ops/gdc-blueprints.git"
    branch: "main"
    dir: "manifests/intel-operations"
    auth: token
    secretRef:
      name: git-creds
```

---

## **5. Day-2 Operational Verification Runbook**

Execute these CLI health checks inside the GDC environment to verify end-to-end integration:

### 1. Verify Multi-Domain Sensor Telemetry (Kafka)
```bash
# Check Kafka topic offsets
kubectl exec -it kafka-0 -n intel-operations -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group telemetry-processor-group \
  --describe
```

### 2. Verify Operational Readiness Database Connection
```bash
# Confirm tables and seed records are active in GDC Database Service
kubectl exec -i deployment/backend -n intel-operations -- \
  python -c "import psycopg2; conn = psycopg2.connect('host=operational-readiness-db user=postgres password=password dbname=postgres'); print('DB Status: ONLINE')"
```

### 3. Verify Model Routing Latency on Inference Gateway
```bash
# Query the gateway directly to verify response headers and model tag
curl -s -X POST http://gemma-gateway.intel-operations.svc.cluster.local:80/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4",
    "messages": [{"role": "user", "content": "What is the status of Route 9?"}]
  }' | jq '{model_selected: .model, response: .choices[0].message.content}'
```

---

## **6. Security, Hardening & Compliance Safeguards**

1. **Strict Read-Only SQL Guard:** The Agentic Data Analyst executes SQL queries using an unprivileged database role (`db_ro_user`) granted exclusively `SELECT` permissions on schema tables. All queries pass through an application-level regex validator that rejects statements containing data definition or data modification language (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`).
2. **Non-Root Pod Execution:** All containers (`p4-consumer`, `backend`, `frontend`, `query-service`) enforce:
   ```yaml
   securityContext:
     runAsNonRoot: true
     runAsUser: 1000
     allowPrivilegeEscalation: false
     capabilities:
       drop: ["ALL"]
   ```
3. **Mutual TLS (mTLS):** All inter-service traffic between the `gemma-client` backend, `query-service`, `sql-agent`, and `gemma-gateway` is encrypted using Istio/Anthos Service Mesh ambient mTLS policies.
