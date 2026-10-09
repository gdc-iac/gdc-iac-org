# End-to-End Tutorial: Multi-Blueprint Intelligence Synthesis & Decision Support
## Testing & Demonstrating on GCP GKE Emulation Environment

> **Document ID:** `TUT-GCP-E2E-INTEL-SYNTHESIS`  
> **Version:** 1.1  
> **Target Environment:** Standard Google Kubernetes Engine (GKE) Sandbox  
> **Companion Production Guide:** [Deploying to GDC Air-Gapped (GDC-ag) Production](./e2e_intelligence_synthesis_gdc_production.md)  
> **Integrated Blueprints:** P4 (Kafka Event Stream), P6 (Resilient RAG Agent), P7 (Agentic Data Analyst), P5/Gateway (`gdc_gemma_gw`), P10/Client (`gemma-client`), P12 (Keycloak OIDC)  
> **Mission Scenario:** *Operation Vanguard Shield* — Multi-Domain Operations (MDO) across Land, Air, Sea, Space, and Cyberspace.

---

## 1. Overview & Demonstration Objectives

This tutorial demonstrates an enterprise-grade, multi-blueprint architecture deployed on a standard Google Kubernetes Engine (GKE) cluster. By orchestrating five decoupled blueprints from the `GDC-blueprints` repository, this solution solves the **Multi-Domain Intelligence Bottleneck**:

1. **Ingest:** Streams and buffers high-velocity multi-domain sensor telemetry (Land, Air, Sea, Space, Cyber) through **Apache Kafka (P4)**.
2. **Index:** Automatically indexes unstructured operational cables, SITREPs, and after-action reports (AARs) using the **Resilient RAG Agent (P6)**.
3. **Query:** Allows tactical operators to query all-source intelligence with grounded document citations in the **Joint Intelligence & Readiness Console (P10 gemma-client)**.
4. **Route:** Automatically routes simple queries to fast lightweight models (`gemma4:26b` MoE) and complex tactical fusion to advanced models (`gemma4:31b` Dense) via the **Gemma Inference Gateway (gdc_gemma_gw)**.
5. **Audit:** Enables commanders to query live force readiness, equipment, and convoy routes in plain English using the **Agentic Data Analyst (P7)**, protected by strict read-only SQL guards.

---

## 2. Prerequisites & Environment Setup

### Environment Assumption: Google Cloud Workstation
This tutorial assumes you are operating within a **Google Cloud Workstation** configured as your development and evaluation host:
* **Persistent Disk Sizing:** Your Cloud Workstation persistent home directory must have **at least 100 GB (recommended 150 GB+)** of disk space to comfortably accommodate:
  * Both containerized inference model images (`gemma4:26b` ~18 GB and `gemma4:31b` ~20 GB).
  * Docker intermediate build layers and caching.
  * Local Git repositories (`gdc_gemma_gw` and `GDC-blueprints`).
* **Cluster Access:** `kubectl` and `gcloud` authenticated with cluster-admin access to your GKE evaluation cluster.

### Design Choice: Why This Tutorial Uses In-Database RAG vs. Cloud Object Storage (GCS)
In the standalone **Pattern 6 (`p6-resilient-rag-agent`)** blueprint, document ingestion uses an Object Storage bucket (Google Cloud Storage in GCP, or MinIO / GDC Native Bucket `object.gdc.goog` in GDC): analysts upload raw PDF/DOCX files, and an ingestion daemon asynchronously chunks and vectorizes them into PostgreSQL.

In this unified end-to-end tutorial, **we intentionally bypass external GCS buckets** in favor of pre-seeding the extracted tactical cables directly into the `intelligence_reports` PostgreSQL table (`test-data/seed_readiness_db.sql`):
1. **Zero Cloud IAM Friction:** Eliminates the need to create cloud storage buckets, bind IAM service account roles, or manage cross-project object permissions.
2. **Instant & Deterministic Scenario State:** Guarantees that the tactical SITREPs (`SITREP-2026-08-SEC9-CONVOY`, Route 9 bridge damage, and FOB Bravo fuel reserves) are immediately queryable without waiting for asynchronous background file ingestion queues to finish.
3. **Decoupled Air-Gap Parity:** Keeps the evaluation workflow self-contained inside Kubernetes. For instructions on connecting live GCS or GDC object buckets to the automated ingestion worker in production, refer to the [GDC-ag Production E2E Deployment Tutorial](./e2e_intelligence_synthesis_gdc_production.md) and the [Operational Administration & Data Ingestion Guide](../operational-guides/operational-administration-and-data-ingestion-guide.md).

---

### Environment Variable Export:
Before starting, ensure your terminal has your active GCP project and cluster coordinates exported:

```bash
export PROJECT_ID=$(gcloud config get-value project)
export NAMESPACE="gemma-inference"
export REGION="us-west4" # Match your Gemma repository region (e.g. us-west4)
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
# Optional: If storing GDC-blueprints images in a separate Artifact Registry repository:
export BLUEPRINT_REGION="${BLUEPRINT_REGION:-us-central1}"
export BLUEPRINT_REGISTRY_HOST="${BLUEPRINT_REGISTRY_HOST:-${BLUEPRINT_REGION}-docker.pkg.dev/${PROJECT_ID}/blueprint-images}"
export CLUSTER_NAME="gdc-gemma-cluster"
export ZONE="us-west4-a"
```

### Pre-Requisite Verification Checklist:
Ensure the baseline services deployed in the [GCP Quickstart Guide](../quickstart_on_GCP.md) are running:
```bash
# 1. Verify GKE node and GPU availability
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-l4

# 2. Verify Inference Gateway, Ollama Engines, Keycloak, and PostgreSQL are Running
kubectl get pods -n "${NAMESPACE}" -l app=gemma-gateway
kubectl get pods -n "${NAMESPACE}" -l app=keycloak
kubectl get pods -n "${NAMESPACE}" -l app=postgres
```
*(All three should report `1/1 Running` status).*

---

## 3. Building and Staging Container Images

### Architectural Note: Pattern 4 (Apache Kafka) Under the Hood
* **The Message Broker (`apache/kafka:3.9.0`):** The Kafka message broker is deployed directly from `blueprints/p4-kafka/statefulset-kafka.yaml` running in KRaft mode (no ZooKeeper required). Because Apache Kafka is standard off-the-shelf broker infrastructure, you do **not** run `docker build` for it; on GKE it is pulled directly from Docker Hub (`apache/kafka:3.9.0`). In an air-gapped GDC environment, it is mirrored into your private Harbor registry.
* **The Telemetry Stream Consumer (`telemetry-consumer`):** This is the custom stream processor based on the Pattern 4 consumer architecture (`p4-event-driven-kafka/example-app/consumer/app.py`). It subscribes to Kafka topic `multi-domain-telemetry`, reads incoming sensor signals, and normalizes them into the PostgreSQL `sensor_telemetry` table.
* **The Telemetry Producer:** Generated via `scripts/simulate_multidomain_telemetry.py` or the console's **"⚡ Ingest Sensor Pings"** button, emitting multi-domain events directly into Kafka.

Build and push the custom container images to your Google Artifact Registry repository:

```bash
cd ~/GitHub/gdc_gemma_gw

# 1. Authenticate Docker with your regional Artifact Registries
gcloud auth configure-docker "${REGION}-docker.pkg.dev,${BLUEPRINT_REGION}-docker.pkg.dev" --quiet

# 2. Build and Push Pattern 4 Telemetry Stream Consumer
docker build -t "${REGISTRY_HOST}/telemetry-consumer:latest" glue-code/telemetry-consumer
docker push "${REGISTRY_HOST}/telemetry-consumer:latest"

# (Optional) Tag with official P4 blueprint name if desired
docker tag "${REGISTRY_HOST}/telemetry-consumer:latest" "${REGISTRY_HOST}/p4-consumer:latest"
docker push "${REGISTRY_HOST}/p4-consumer:latest"

# 3. Build and Push Pattern 7 (Agentic Data Analyst) - Optional standalone microservice
BLUEPRINTS_DIR="${BLUEPRINTS_DIR:-../GDC-blueprints}"
if [ -d "${BLUEPRINTS_DIR}/p7-agentic-data-analyst/example-app/agent" ]; then
  docker build -t "${BLUEPRINT_REGISTRY_HOST}/p7-agent:latest" "${BLUEPRINTS_DIR}/p7-agentic-data-analyst/example-app/agent"
  docker push "${BLUEPRINT_REGISTRY_HOST}/p7-agent:latest"
fi

# 4. Configure Frontend OIDC + Intelligence Console Flags & Build gemma-client
cat << 'EOF' > gemma-client/src/frontend/.env
VITE_API_URL=/api
VITE_ENABLE_OIDC=true
VITE_OIDC_CLIENT_ID=rag-frontend
VITE_ENABLE_INTEL_CONSOLE=true
EOF

chmod +x gemma-client/scripts/build.sh
./gemma-client/scripts/build.sh -p "${PROJECT_ID}" -r "${REGISTRY_HOST}"
```

---

## 4. Deploying the Solution & Selecting Your Traffic Routing Path (Ingress vs. Gateway API)

You can deploy the solution using either the **Automated One-Click Script (4.1)** or the **Step-by-Step Manual Commands (4.2)**, and expose traffic using either **Path A (NGINX Staging Ingress)** or **Path B (GKE Gateway API + L4 Tunnel)**.

### 4.1. Automated One-Click Solution Deployment
```bash
chmod +x scripts/deploy-e2e-solution.sh

# Default (deploys NGINX Staging Ingress and refreshes Gateway API if present):
./scripts/deploy-e2e-solution.sh

# Or explicitly request GKE Gateway API (Path B):
# INGRESS_MODE=gateway ./scripts/deploy-e2e-solution.sh
```

**What `scripts/deploy-e2e-solution.sh` automates:**
* **Database Migration & Seeding:** Loads `test-data/seed_readiness_db.sql` into `postgres-0` (populating military units, equipment inventories, fuel supplies, convoy routes, and tactical SITREPs).
* **Kafka & Telemetry Daemon:** Deploys the single-node Kafka KRaft broker (`kafka-0` / `kafka-svc`) and `telemetry-consumer` deployment listening on topic `multi-domain-telemetry`.
* **ServiceAccount & DB Secret Provisioning:** Ensures `serviceaccount/gemma-client-sa` and `secret/gemma-client-db-credentials` exist before deploying `backend` (preventing Kubernetes ReplicaSet pod-creation blocks).
* **Console & OIDC Rollout:** Hydrates `backend.yaml` and `frontend.yaml`, enables `ENABLE_OIDC="true"` against `keycloak-svc`, and configures your selected Ingress or Gateway API path.

---

### 4.2. Step-by-Step Manual Deployment (Core Workloads)
If you prefer to execute each deployment step manually instead of running `./scripts/deploy-e2e-solution.sh`:

```bash
cd ~/GitHub/gdc_gemma_gw

# 1. Seed Operational Readiness & Intelligence Database into postgres-0
kubectl exec -i postgres-0 -n "${NAMESPACE}" -- psql -U postgres -d postgres < test-data/seed_readiness_db.sql

# 2. Deploy Pattern 4 Kafka Broker (KRaft) & Telemetry Consumer
kubectl apply -f blueprints/p4-kafka/statefulset-kafka.yaml -n "${NAMESPACE}"
kubectl rollout status statefulset/kafka -n "${NAMESPACE}" --timeout=120s

sed -e "s|REGISTRY_HOST_PLACEHOLDER|${REGISTRY_HOST}|g" \
    -e "s|namespace: gemma-inference|namespace: ${NAMESPACE}|g" \
    glue-code/telemetry-consumer/manifests/consumer-deployment.yaml | kubectl apply -n "${NAMESPACE}" -f -

# 3. Create Required ServiceAccount and Database Secret for gemma-client Backend
# IMPORTANT: Without gemma-client-sa and gemma-client-db-credentials, deployment/backend
# cannot schedule pods and /api/chat will return 502 Bad Gateway.
kubectl create serviceaccount gemma-client-sa -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic gemma-client-db-credentials \
  --from-literal=connection_string="postgresql://postgres:password@postgres-svc:5432/postgres" \
  -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# 4. Hydrate and Deploy gemma-client Backend & Frontend with OIDC Enabled
sed -i "s|image: .*gemma-client-backend:.*|image: ${REGISTRY_HOST}/gemma-client-backend:latest|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|image: .*gemma-client-frontend:.*|image: ${REGISTRY_HOST}/gemma-client-frontend:latest|g" gemma-client/manifests/apps/frontend.yaml
sed -i "s|PROJECT_ID_PLACEHOLDER|${PROJECT_ID}|g" gemma-client/manifests/apps/backend.yaml
sed -i "s|INPUT_BUCKET_PLACEHOLDER|gemma-client-files-${PROJECT_ID}|g" gemma-client/manifests/apps/backend.yaml

kubectl apply -f gemma-client/manifests/apps/backend.yaml -n "${NAMESPACE}"
kubectl set env deployment/backend \
  ENABLE_OIDC="true" \
  KEYCLOAK_URL="http://keycloak-svc:8080/auth/realms/gdc-rag-realm" \
  -n "${NAMESPACE}"

kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n "${NAMESPACE}"
kubectl rollout status deployment/backend -n "${NAMESPACE}" --timeout=90s
kubectl rollout status deployment/frontend -n "${NAMESPACE}" --timeout=90s
```

---

### 4.3. Traffic Exposure Paths: Choose Path A (NGINX Ingress) OR Path B (Gateway API)

To prevent browser CORS failures and Cloud Workstation multi-port cookie conflicts during Keycloak OIDC redirects, `/auth`, `/api/`, and `/` must be served from a **single unified origin** on port `8081`. Choose **one** of the two supported routing architectures below:

| Feature | Path A: NGINX Staging Ingress (`gemma-ingress-gateway`) | Path B: Kubernetes Gateway API (`gdc-platform-gateway` + `gdc-gateway-tunnel`) |
| :--- | :--- | :--- |
| **Manifests Used** | `gemma-client/manifests/gcp/nginx-ingress-staging.yaml` | `gemma-client/manifests/gcp/gateway-api-staging.yaml` + `gemma-client/manifests/gdc/security/production-gateway-routing.yaml` |
| **Provisioning Time** | **Instant (~5 seconds)** — lightweight in-cluster NGINX pod (`nginx:1.25-alpine-slim`). | **~60–90 seconds** — provisions a GKE Regional Internal Load Balancer (`gke-l7-rilb`), `HealthCheckPolicy`, and `GCPBackendPolicy`. |
| **Port-Forward Target** | `service/gemma-ingress-gateway` | `service/gdc-gateway-tunnel` (in-cluster `socat` L4 bridge to the Gateway RILB VIP) |
| **When to Choose** | Fastest setup for functional testing, prompt routing, and UI demonstrations. | Validating full GDC-ag `gateway.networking.k8s.io/v1` (`Gateway` + `HTTPRoute`) manifests on GKE. |

#### Option A: Deploy & Port-Forward NGINX Staging Ingress (`service/gemma-ingress-gateway`)
```bash
# 1. Apply the unified NGINX staging ingress ConfigMap, Deployment, and Service
kubectl apply -f gemma-client/manifests/gcp/nginx-ingress-staging.yaml -n "${NAMESPACE}"
kubectl rollout status deployment/gemma-ingress-gateway -n "${NAMESPACE}" --timeout=60s

# 2. Port-forward gemma-ingress-gateway to localhost:8081
pkill -f "port-forward" || true
kubectl port-forward service/gemma-ingress-gateway 8081:80 -n "${NAMESPACE}"
```

#### Option B: Deploy & Port-Forward Kubernetes Gateway API (`service/gdc-gateway-tunnel`)
> **Note:** Ensure your GKE cluster has the Gateway API controller (`--gateway-api=standard`) and a proxy-only subnet enabled in your VPC region (`--purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE`) as described in the [GCP Quickstart Guide](../quickstart_on_GCP.md).

```bash
# 1. Apply the GKE Gateway API (gdc-platform-gateway), HealthCheckPolicies, GCPBackendPolicies, and HTTPRoute
kubectl apply -f gemma-client/manifests/gcp/gateway-api-staging.yaml -n "${NAMESPACE}"
kubectl apply -f gemma-client/manifests/gdc/security/production-gateway-routing.yaml -n "${NAMESPACE}"

# 2. Wait for GKE to allocate the Regional Internal Load Balancer VIP (~60-90s)
echo "Waiting for gdc-platform-gateway VIP allocation..."
for i in {1..30}; do
  GATEWAY_VIP=$(kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" -o jsonpath='{.status.addresses[0].value}' 2>/dev/null || true)
  if [ -n "${GATEWAY_VIP}" ]; then
    echo "Allocated GATEWAY_VIP: ${GATEWAY_VIP}"
    break
  fi
  sleep 5
done

# 3. Bind the in-cluster L4 socat bridge (gdc-gateway-tunnel) to the allocated VIP
kubectl set env deployment/gdc-gateway-tunnel GATEWAY_VIP="${GATEWAY_VIP}" -n "${NAMESPACE}"
kubectl rollout status deployment/gdc-gateway-tunnel -n "${NAMESPACE}" --timeout=60s

# 4. Port-forward gdc-gateway-tunnel to localhost:8081
pkill -f "port-forward" || true
kubectl port-forward service/gdc-gateway-tunnel 8081:80 -n "${NAMESPACE}"
```

---

## 5. Guided Demonstration: Testing the 5 Functions

With your chosen port-forward running in a dedicated terminal (`service/gemma-ingress-gateway` for **Option A** or `service/gdc-gateway-tunnel` for **Option B**), open **`http://localhost:8081`** (or your Cloud Workstation Port `8081` Web Preview URL) and sign in at the Keycloak prompt:
* **`alice`** / **`password`** — **Intelligence Analyst persona** (`role: user`; full access to Tactical Chat, Kafka Feeds, RAG Synthesis, SQL Audit, and personal file uploads; blocked with `403 Forbidden` from uploading shared files).
* **`charlie`** / **`password`** — **Joint Task Force Commander persona** (`role: admin`; full administrative access including shared intelligence document uploads).

> [!TIP]
> **Troubleshooting `502 Bad Gateway` on First Tactical Chat Query:**
> Because `/auth` routes directly to `keycloak-svc:8080` and `/` routes directly to `frontend-svc:80`, `POST /api/chat` is the first user-visible call that reaches `backend-svc:8000`.
> * If `502` occurs **immediately (<1s)**: Verify `kubectl get pods -l app=backend -n "${NAMESPACE}"` shows `1/1 Running`. If no `backend` pod exists, run Step 3 of Section 4.2 above to create `serviceaccount/gemma-client-sa` and `secret/gemma-client-db-credentials`, then run `kubectl rollout restart deployment/backend -n "${NAMESPACE}"`.
> * If `502` occurs **after ~60s**: The first inference request triggered a cold GPU load of `gemma4:26b` in Ollama. Simply retry the chat message once the model weights finish loading into VRAM.

---

### Function 1: Multi-Domain Sensor Ingestion (Kafka Feeds)
1. In the console, navigate to the **Tactical Feeds (Kafka)** tab.
2. Observe the multi-domain overview cards for **LAND**, **AIR**, **SEA**, **SPACE**, and **CYBER**.
3. Click the **"⚡ Ingest Sensor Pings"** button in the header.
4. **Observed Behavior:** Watch new sensor telemetry events stream live into the ticker buffer.
5. *(Optional Continuous Stream)*: Run the background generator in a spare terminal:
   ```bash
   python scripts/simulate_multidomain_telemetry.py --mode stream --interval 2.0
   ```
6. Click on any event row to expand its raw JSON payload (e.g. Modbus SCADA port scans, seismic acoustic signatures, or ADS-B radar tracks).

#### CLI Deep-Dive: Verifying Apache Kafka (Pattern 4) Under the Hood
To directly verify that Apache Kafka is ingesting and buffering messages behind the scenes:

```bash
# 1. Tail the telemetry consumer pod logs in real time
kubectl logs -f -l app=telemetry-consumer -n $NAMESPACE

# 2. Inspect Kafka consumer group lag and partition offsets directly on the broker
kubectl exec -it kafka-0 -n $NAMESPACE -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group telemetry-processor-group \
  --describe

# 3. List active topics on the broker (confirming 'multi-domain-telemetry')
kubectl exec -it kafka-0 -n $NAMESPACE -- \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
```
*You will observe the `telemetry-processor-group` actively consuming messages from topic `multi-domain-telemetry` and committing partition offsets into Kafka.*

---

### Function 2 & 3: All-Source Intelligence Query (P6 RAG)
1. Switch to the **All-Source Intel (RAG)** tab.
2. Click the suggested query chip:
   > *"What vulnerabilities were identified for supply convoys along Route 9 in Sector 9?"*
3. Click **Synthesize**.
4. **Observed Behavior:**
   * The RAG engine retrieves relevant paragraphs from `SITREP-2026-08-SEC9-CONVOY`.
   * The synthesis notes that Route 9 is at **AMBER** status due to bridge damage at Waypoint Echo (repair underway), defile ambushes at Ridge 104, and that FOB Bravo is down to **6 Days of Supply** of JP-8 fuel.
   * Review the **Referenced All-Source Cables** cards at the bottom containing inline citations.

---

### Function 4: Dynamic Heuristic Routing (Gemma Inference Gateway)
1. Open the **Tactical Chat** tab or observe the **Engine Badge** in the top header.
2. **Simple Summary Query:**
   * Submit: *"Summarize the role of the 16th Space Surveillance Squadron."*
   * *Observed Routing:* The heuristic classifier recognizes low-complexity lookup and routes to **`Gemma 4 26B (MoE)`**, returning an immediate summary with low latency.
3. **Complex Tactical Reasoning Query:**
   * Submit: *"Correlate the latest cyber SCADA port scan telemetry at FOB Alpha with acoustic ground sensor detections on Route 9. Assess adversary intent and recommend an alternate supply routing plan."*
   * *Observed Routing:* The classifier detects cross-domain correlation, causal inference, and military planning keywords, automatically routing to **`Gemma 4 31B (Dense)`** for deep tactical CoT reasoning!

---

### Function 5: Plain-English Operational Database Audit (P7 SQL Analyst)
1. Switch to the **Operational Readiness (SQL)** tab.
2. Click the suggested commander question:
   > *"List all military units in Sector 9 with combat readiness below C2."*
3. Click **Audit**.
4. **Observed Behavior:**
   * **Generated Safe SQL Query:** The AI generates `SELECT * FROM military_units WHERE sector = 'Sector 9' AND readiness_rating IN ('C3', 'C4');` (or `readiness_rating NOT IN ('C1')`).
   * **Security Badge:** Verified with the green **`🔒 Read-Only Guard Verified`** badge (confirming AST compliance and stripping mutation keywords).
   * **Execution Latency:** Highlights **`DB Engine: < 15ms`** (PostgreSQL query speed) alongside the total AI pipeline duration (~8–10s on emulated Ollama; < 1s on GDC production vLLM).
   * **Tabular Results:** Correctly lists the degraded units in Sector 9:
     * `9th Stryker Brigade Combat Team` with **`C3 (Marginal)`** badge *(28 Stryker ICVs deadlined)*
     * `12th Cavalry Reconnaissance Squadron` with **`C3 (Marginal)`** badge *(equipment shortages)*
     * `588th Brigade Engineer Battalion` with **`C4 (Not Ready)`** badge *(heavy equipment rebuild)*
   * **Executive Summary:** Synthesizes actionable advice for the commander on equipment repair priorities and convoy escorts.
5. Try another query:
   > *"Check fuel reserves, days of supply, and resupply status at all forward operating bases."*
   * Observe the table identifying FOB Bravo's critical 42,000-gallon reserve (6 Days of Supply).

---

## 6. Performance Breakdown: GCP Sandbox Emulation vs. GDC-ag Production

During demonstration on the GCP test rig, you will observe that while the **PostgreSQL database execution is nearly instantaneous (< 15 ms)**, the overall natural language query synthesis takes **~8 to 12 seconds**. 

This section explains why sub-second end-to-end performance is not demonstrable on the evaluation test rig, and contrasts it with expected performance in GDC air-gapped production.

### Why Sub-Second AI Latency Isn't Demonstrable on the Test Rig

1. **Hardware & Quantization Constraints (Single Entry-Level GPU):**
   * The GCP sandbox test rig is engineered as a low-cost developer stepping stone, operating on a **single NVIDIA L4 GPU (24GB VRAM)** or CPU offloading.
   * To fit the dual-model architecture (`Gemma 4 26B MoE` and `Gemma 4 31B Dense`) into a single L4, the test rig runs **Ollama with 4-bit GGUF quantized weights**. 
   * Ollama processes requests sequentially per engine instance without continuous memory batching or kernel-level tensor parallelization.

2. **Two-Pass AI Execution for NL-to-SQL & RAG:**
   * An Agentic SQL Audit or RAG Synthesis is not a single inference call—it executes a **two-pass pipeline**:
     * **Pass 1 (NL-to-SQL Generation):** Gemma converts the commander's plain-English question into structured PostgreSQL syntax (~3–5s).
     * **Database Execution:** PostgreSQL executes the query against indexed tables (**5–15 ms**).
     * **Pass 2 (Executive Synthesis):** Gemma parses the resulting JSON database rows and drafts an operational commander summary (~4–6s).
   * Cumulative latency on the single-GPU test rig: `4s + 0.015s + 5s ≈ 9 seconds`.

### Performance Comparison Matrix: Test Rig vs. GDC Production

| Dimension / Metric | GCP Evaluation Sandbox (Test Rig) | GDC-ag Air-Gapped Production Rack |
| :--- | :--- | :--- |
| **Inference Engine** | Ollama (Lightweight GGUF 4-bit Quantization) | **vLLM Distributed Serving Engine** (FP16 / FP8 Unquantized) |
| **GPU Hardware** | 1x NVIDIA L4 (24 GB VRAM) | Dedicated GPU NodePools (Multi-Node NVIDIA A100 80GB / H100) |
| **Memory Management** | Basic sequential buffer allocations | **PagedAttention** (Zero KV cache memory fragmentation) |
| **Parallelism** | Single GPU execution (No Tensor Parallelism) | **Tensor Parallelism** (`TP=2` or `TP=4` across high-speed NVLink) |
| **Batching Strategy** | Sequential / single-stream inference | **Continuous Iteration-Level Batching** |
| **Time to First Token (TTFT)** | ~1.8 – 3.2 seconds | **~150 – 350 milliseconds (Sub-Second)** |
| **Token Generation Speed** | ~15 – 25 tokens/sec | **~100 – 160+ tokens/sec** |
| **End-to-End NL-to-SQL Pipeline** | ~8.0 – 12.0 seconds | **~650 – 950 milliseconds (Sub-Second End-to-End)** |
| **Concurrent Serving Capacity** | 1 – 5 concurrent users | **50 – 150+ concurrent tactical operator streams** |

---

## 7. GDC-ag Production Readiness Tasks & Expected Target Performance

Transitioning this multi-blueprint solution into a mission-ready, air-gapped GDC-ag deployment requires executing specific Day-1 platform integration and Day-2 operational hardening tasks:

```
 ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                GDC AIR-GAPPED PRODUCTION TOPOLOGY                               │
 ├────────────────────────────────┬────────────────────────────────┬──────────────────────────────┤
 │   1. DEDICATED GPU NODEPOOLS   │   2. HIGH-PERFORMANCE SAN      │   3. ENTERPRISE GATEWAY & DB │
 │   • NodePool: gpu-moe (26B)    │   • StorageClass: standard-rwx │   • K8s Gateway API (Envoy)  │
 │   • NodePool: gpu-dense (31B)  │   • ReadWriteMany SAN PV       │   • Keycloak + AD / LDAP     │
 │   • Tensor Parallelism (TP=2)  │   • Instant Pod Failover       │   • GDC Managed Postgres HA  │
 └────────────────────────────────┴────────────────────────────────┴──────────────────────────────┘
```

### Production Readiness Task Checklist

1. **Dedicated GPU NodePool Provisioning (`cluster.gdc.goog/v1`):**
   * Provision dedicated GPU hardware pools using the GDC Cluster API with appropriate taints/tolerations:
     * Pool `gpu-moe`: Dedicated to `vllm-gemma-26b` with Tensor Parallelism (`TP=2`).
     * Pool `gpu-dense`: Dedicated to `vllm-gemma-31b` with Tensor Parallelism (`TP=2` or `TP=4`).
   * *Outcome:* Eliminates GPU cold-starts and guarantees dedicated compute for mission-critical C2 fusion.

2. **SAN Storage Provisioning (`standard-rwx`):**
   * Back all vLLM model weights and vector embeddings with GDC Storage Area Network (SAN) persistent volumes (`ReadWriteMany`).
   * *Outcome:* Enables instantaneous pod restarts and rolling upgrades without re-downloading multi-gigabyte model weights across nodes.

3. **Production Gateway API & Mutual TLS (`HTTPRoute`):**
   * Replace the test rig NGINX sidecar with standard Kubernetes Gateway API (`gateway.networking.k8s.io/v1`) bound to the platform's Envoy L7 load balancer (`gdc-shared-gateway`).
   * Enforce mutual TLS (mTLS) with DoD PKI / enterprise root certificates.

4. **Enterprise Identity Federation (Keycloak + Active Directory):**
   * Connect Keycloak to the air-gapped LDAP/Active Directory forest.
   * Enable 1-hour access token lifespans with automated silent background token refresh (`refresh_token` flow in `api.js`) and least-privilege RBAC personas (`Analyst` vs `Commander`).

5. **PostgreSQL High Availability & Vector Tuning:**
   * Deploy GDC Managed Database Service (`DBCluster`) in HA mode across availability zones.
   * Build HNSW vector indexes (`m = 16, ef_construction = 64`) on `intelligence_reports` and partition `sensor_telemetry` by week.

6. **Kafka Broker Clustering & Dead-Letter Queues (Pattern 4):**
   * Deploy a 3-node clustered Kafka deployment in KRaft mode.
   * Scale the `telemetry-consumer` deployment to 5 replicas (matching partition counts) and configure `multi-domain-telemetry-dlq` for corrupt message isolation.

---

## 8. Clean Up

When you have finished testing the multi-blueprint demonstration:

```bash
# 1. Stop background telemetry stream
pkill -f "simulate_multidomain_telemetry" || true

# 2. Remove Kafka and Consumer
kubectl delete -f blueprints/p4-kafka/statefulset-kafka.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f glue-code/telemetry-consumer/manifests/consumer-deployment.yaml -n $NAMESPACE --ignore-not-found

# 3. Clean database test tables
kubectl exec -i postgres-0 -n $NAMESPACE -- psql -U postgres -d postgres -c \
  "DROP TABLE IF EXISTS sensor_telemetry, military_units, equipment_inventory, fuel_and_supplies, convoy_routes, intelligence_reports CASCADE;"
```
