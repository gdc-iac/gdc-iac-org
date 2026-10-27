Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 6: Resilient RAG Agent on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Resilient RAG Agent** on Google Distributed Cloud (GDC) air-gapped environments. This pattern constructs a secure, multi-stage Document Retrieval-Augmented Generation (RAG) agent that orchestrates ingestion pipelines (multimodal vision parsing, document translation, text extraction) via Gemma / Gemini models and stores embeddings in a PostgreSQL vector database to answer user queries with local LLM assistance.

## **Architecture**

The architecture divides operations into two distinct cycles:
1. **Document Ingestion (Batch/Cron)**: Reads documents from GDC Object Storage, extracts text and multimodal features using Gemma or Gemini models via the Inference Gateway, converts contents to embeddings, and writes to PostgreSQL with `pgvector`.
2. **Query Agent Service (Online)**: Intercepts natural language questions, vectorizes the search query, retrieves relevant document fragments from the vector database, and feeds them as context to the primary LLM (via the LLM Gateway).

```
                     [ raw-docs Object Bucket ]
                                 │
                                 ▼ (Per 15 Min)
                          [ doc-ingest ] (CronJob)
                                 │
                                 ▼ (Multimodal Vision / Translation / Parsing)
                    [ Gemma / Gemini Inference Gateway ]
                                 │
                                 ▼
                     [ postgres-db (Vector) ]
                                 ▲
                                 │ (Similarity Search)
                      [ query-service ] (API)
                                 ▲
                                 │ (Ask / Answer)
                             [ User ]
                                 │
          ┌──────────────────────┴──────────────────────┐
          │ (Option A: Gemma Gateway)                   │ (Option B: GDC Gemini Gateway)
          ▼                                             ▼
 [ Gemma Inference Gateway ]                  [ GDC AI Inference Gateway ]
  (gdc_gemma_gw / vLLM / Ollama)               (https://ai-gateway.shared-services...)
  Model: Gemma 4 26B / 31B                     Headers: x-goog-user-project
                                               Model: google/gemini-3.5-flash /
                                                      google/gemini-3.1-flash-lite
```

### **Key Solution Capabilities**

* **LLM inference**: Gemma 4 or Gemini 3.5.
* **Vector DB Co-location**: Embeds text using native embedding models and stores vectors directly inside an HA GDC database cluster.
* **Dual Inference Gateway Integration**: Flexibly routes generation prompts through either:
  * **Option A (Primary)**: Self-hosted **Gemma Inference Gateway** (`../gdc_gemma_gw`) providing offline inference for Gemma models.
  * **Option B (Alternative)**: Native **GDC Gemini AI Gateway** exposing Gemini models via an OpenAI-compatible interface authenticated with GDC STS tokens and `x-goog-user-project` headers.
* **Asynchronous Document Ingestion Lifecycle**: Uploading a document stores the raw file in Object Storage (`users/<user_id>/...` or `shared/...`). **Files are indexed into PostgreSQL (`pgvector`) only when the Ingestion CronJob (`doc-ingest`) executes.** Manual execution can be triggered for immediate testing: `kubectl create job --from=cronjob/doc-ingest manual-ingest-$(date +%s) -n <namespace>`.
* **Namespace Isolation & Blueprint Hydration**: Blueprints use `./configure-blueprints.sh -p <project-id> -n <target-namespace>` to bind workloads seamlessly to custom namespaces (such as `gemma-inference`).
* **Least-Privilege Security Policy**: Restricts container capabilities using a dedicated `ServiceAccount` and binds IAM roles explicitly via `ProjectPolicy`.

---

## **Production Deployment vs Connected Artifact Preparation**

| Dimension | **Connected Sideloading Workstation** | **GDC Air-Gapped Production** |
| :--- | :--- | :--- |
| **Object Storage** | Artifact stage / local directory (`./data/raw-docs`) for bundle prep | Native GDC Object Storage Bucket |
| **Database** | Local development container / StatefulSet (`pgvector`) for offline testing | GDC Database Service (Managed PostgreSQL HA) |
| **LLM Inference** | Container image download & model weights packaging | Gemma Gateway (`gdc_gemma_gw`) or GDC AI Inference Gateway |
| **Target Namespace** | Connected staging registry (`harbor.gdc.local`) | Organization Workload Namespace (hydrated via `-n`) |
| **Service Exposure** | Local CLI / Docker execution | GDC Gateway API (`HTTPRoute` + `theia-shared-gateway`) |

---

## **LLM Gateway Integration & Migration Guide**

### **Primary Gateway Topology & Cross-Cluster Deployment Nuance: `gdc_gemma_gw`**
Pattern 6 is designed to consume the **Gemma Inference Gateway** (`gdc_gemma_gw`) or **GDC Gemini AI Gateway**. Note that the inference gateway does **not** need to be co-located in the same cluster or namespace as the application workloads.

Depending on your enterprise topology, the inference gateway can reside in:
* **Co-located Namespace**: `http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`
* **Shared Services Cluster / Namespace**: `http://gemma-gateway.shared-services.svc.cluster.local:80/v1`
* **Dedicated Remote GPU Cluster**: `https://ai-gateway.shared-services.gdc.local/v1` (exposed via GDC Gateway API `HTTPRoute` or load balancer FQDN).

* **Service Deployment**: The gateway runs as a deployment (`deployment/gemma-gateway`) exposed by a Kubernetes service (`svc/gemma-gateway`) listening on **port 80** (or HTTPS gateway).
* **Backend Serving Engine**: Wraps vLLM / Ollama model replicas (`gemma-2-27b-it` or `gemma4:26b` / `gemma4:31b`) running on dedicated GPU node pools (`g2-standard-24` or GDC GPU nodes).
* **API Endpoints**: Implements standard OpenAI `/v1/chat/completions` and legacy `/generate` routes.

### **Migrating to Native GDC Gemini AI Gateway**
To migrate from the Gemma Inference Gateway to the native GDC Gemini AI Gateway (or Vertex AI Gemini), update the environment variables in `manifests/apps/query-service.yaml` and `manifests/apps/ingest-job.yaml`:

```yaml
env:
- name: LLM_PROVIDER
  value: "gemini"
- name: LLM_GATEWAY_URL
  value: "https://ai-gateway.shared-services.gdc.local/v1"
- name: GEMINI_MODEL
  value: "google/gemini-3.5-flash"
- name: AO_PROJECT_ID
  value: "projects/<YOUR_PROJECT_ID>"
```

Then re-apply the manifests and perform a rollout restart:
```bash
kubectl apply -f manifests/apps/query-service.yaml -n <target-namespace>
kubectl apply -f manifests/apps/ingest-job.yaml -n <target-namespace>
kubectl rollout restart deployment/query-service -n <target-namespace>
```

---

## **Production Security: Network Policies & Keycloak Integration**

### **1. NetworkPolicy Guidance for Air-Gapped Egress Control**
In a GDC air-gapped production cluster, strict network isolation is required. Apply the following `NetworkPolicy` to restrict egress and ingress for Pattern 6 workloads:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: p6-rag-security-policy
  namespace: <target-namespace>
spec:
  podSelector:
    matchExpressions:
      - key: app
        operator: In
        values: [query-service, doc-ingest, frontend]
  policyTypes:
  - Ingress
  - Egress
  ingress:
  # Allow Frontend & Gateway API traffic to query-service
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8080
  egress:
  # 1. Allow traffic to Gemma Inference Gateway (Port 80)
  - to:
    - podSelector:
        matchLabels:
          app: gemma-gateway
    ports:
    - protocol: TCP
      port: 80
  # 2. Allow traffic to PostgreSQL Vector Database (Port 5432)
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
  # 3. Allow DNS resolution inside cluster
  - to:
    - namespaceSelector: {}
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
```

### **2. Keycloak OIDC Authentication & Multi-Tenant Access Control**
By default, Pattern 6 includes lightweight mock headers (`X-User-ID`, `X-User-Role`) for rapid testing. For production deployments requiring multi-tenant access control and single sign-on (SSO):

1. **Overlay Keycloak (P12 Blueprint)**: Deploy Keycloak as the OIDC Identity Provider (IdP) using the [P12 Keycloak Blueprint](../p12-keycloak/README.md).
2. **API Gateway JWT Validation**: Configure GDC Gateway API (`HTTPRoute`) or NGINX ingress to validate Keycloak OIDC Bearer tokens (`Authorization: Bearer <jwt_token>`).
3. **Identity Header Extraction**: Pass extracted claims (`sub` as `X-User-ID` and `realm_access.roles` as `X-User-Role`) to `query-service`.
4. **Document Access Isolation**: `query-service` filters PostgreSQL vector queries using the authenticated user identity:
   ```sql
   SELECT content, filename FROM documents 
   WHERE (owner_id = %s OR source_path LIKE 'shared/%%') 
   ORDER BY embedding <=> %s::vector LIMIT 5;
   ```
5. **Full Integration Guide**: Refer to [`docs/keycloak_integration_guide.md`](../docs/keycloak_integration_guide.md) for detailed OIDC proxy configuration.

---

## **Document-Grounded Query Scope & Error Behavior**

> [!WARNING]
> **Corpus Scope Requirement**:
> Pattern 6 is designed **strictly as a document-grounded RAG agent**. It retrieves answer context from PostgreSQL vector storage (`pgvector`) based on documents that have been ingested.
> 
> * **Supported Queries**: Questions directly related to files uploaded to the Object Storage bucket and successfully processed by the `doc-ingest` job.
> * **Out-of-Scope / Generic Queries**: Generic conversational prompts (e.g. *"Tell me a joke"*, *"What is quantum computing?"* when no quantum computing docs exist) or queries submitted **before** running ingestion will yield 0 vector context matches. When no matching context is retrieved, the agent's safety fallback returns:
>   `Sorry, I encountered an error processing your request.`

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* Gemma Inference Gateway or GDC Gemini AI Gateway accessible for document parsing and embedding generation.
* A GDC Object Storage bucket (`gs://raw-docs-<project_id>`) created.
* The LLM Gateway (Pattern 5) deployed and active.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **IAM Admin**: `roles/iam.serviceAccountAdmin` (to configure ServiceAccounts).
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL).
  * **GKE Developer**: `roles/gke.developer` (to deploy manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the custom RAG agent container images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p6-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom RAG images:
```bash
docker tag rag-ingest:v7 harbor.shared-services.gdc.local/my-org/rag-ingest:v7
docker push harbor.shared-services.gdc.local/my-org/rag-ingest:v7

docker tag rag-query:v7 harbor.shared-services.gdc.local/my-org/rag-query:v7
docker push harbor.shared-services.gdc.local/my-org/rag-query:v7
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p6-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry p6-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.3 Base Cluster Resource & Node Pool Requirements

### 1.3.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Ingestion Worker** | 1 (CronJob) | 100m (500m) | 128Mi (512Mi) | None |
| **Query Service** | 1 | 200m (1) | 256Mi (1Gi) | None |
| **PostgreSQL Vector DB** | 2 | 4 (4) | 16Gi (16Gi) | 100Gi DB Volume |

### 1.3.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Handles the CPU-intensive PostgreSQL Vector database replicas, alongside the query backend and periodic ingestion worker.
* **Instance Type**: 2 nodes of type **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node).
* **Total Resource Pool**: 16 vCPUs, 64Gi RAM.
* **Resilience Configuration**: Sizing at `n2-standard-8-gdc` is required because the vector database requests 4 vCPUs and 16Gi RAM per replica. Having 2 nodes ensures that the active/standby database components are physically isolated, preventing a single hardware failure from causing a database outage.

### 1.3.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p6-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 2
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Create the Project Binding YAML (`project-binding.yaml`):**
```yaml
apiVersion: resourcemanager.gdc.goog/v1
kind: ProjectBinding
metadata:
  name: p6-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p6-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - my-gdc-project
```

**3. Apply the Manifests:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p6-standard-cluster
  namespace: my-gdc-project
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 2
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Apply the Manifest:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.3.4 Workload Pod Assignment & Scheduling Configuration

Configure `nodeSelector` in the Ingestion, Query, and Vector DB deployment specifications:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Configuring GDC IAM Permissions**

The RAG application requires permissions to access GDC Object Storage, Database Service, and call AI Inference Gateway APIs. Bind the AI Inference developer role to the RAG service account.

#### Option A: Manual (CLI)
```shell
export NAMESPACE="my-gdc-project"

# 1. Create the ServiceAccount
kubectl create sa rag-sa -n ${NAMESPACE}

# 2. Bind GDC AI Inference developer role
gdcloud iam service-accounts add-iam-policy-binding rag-sa \
  --project=${NAMESPACE} \
  --role=Role/ai-inference-developer
```

#### Option B: GitOps / IaC (`manifests/iam/rag-permissions.yaml`)
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: rag-sa
  namespace: my-gdc-project
---
apiVersion: iam.gdc.goog/v1
kind: ProjectPolicy
metadata:
  name: rag-bindings
  namespace: my-gdc-project
spec:
  bindings:
  - role: Role/ai-inference-developer
    members:
    - serviceAccount:rag-sa
```

---

## **Section 3: Deploying the Vector Database (PostgreSQL)**

### 3.1 Provision PostgreSQL Cluster

Create the database instance to support document vector persistence.

#### Option A: Manual (CLI)
```shell
gdcloud database clusters create rag-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=4 --memory=16Gi --storage-size=100Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/db/postgres.yaml`)
```yaml
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: rag-db
  namespace: my-gdc-project
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA
  resources:
     requests: { cpu: "4", memory: "16Gi" }
  storage: { size: "100G" }
```

### 3.2 Initialize DB extensions for Vector Storage

Wait for database status `READY`, connect via `psql`, and enable the pgvector extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_embeddings (
    id SERIAL PRIMARY KEY,
    document_name VARCHAR(255),
    chunk_index INT,
    text_content TEXT,
    embedding vector(768)  --Sized for standard text-embedding-004
);

CREATE INDEX IF NOT EXISTS document_embedding_cosine_idx 
ON document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## **Section 4: Deploying Ingestion & Query workloads**

Deploy the CronJob to process static bucket assets and the API query deployment.

#### Option A: Manual (CLI)
```shell
kubectl apply -f ingest-job.yaml -n my-gdc-project
kubectl apply -f query-service.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/ingest-job.yaml` & `query-service.yaml`)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: doc-ingest
  namespace: my-gdc-project
spec:
  schedule: "*/15 * * * *"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: rag-sa
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            fsGroup: 1000
          containers:
          - name: ingest
            image: harbor.shared-services.gdc.local/my-org/rag-ingest:v7
            resources:
              requests:
                cpu: "100m"
                memory: "128Mi"
            env:
            - name: INPUT_BUCKET
              value: "gs://raw-docs-my-gdc-project"
            - name: DB_NAME
              value: "postgres"
            - name: GEMINI_ENDPOINT
              value: "http://llm-gateway.my-gdc-project.svc.cluster.local:80/generate"
            - name: GEMINI_MODEL
              value: "gemini-2.5-flash"
            - name: EMBEDDING_MODEL
              value: "text-embedding-004"
            - name: PROJECT_ID
              value: "my-gdc-project"
            - name: DB_HOST
              valueFrom: { secretKeyRef: { name: rag-db-credentials, key: host } }
            - name: DB_USER
              valueFrom: { secretKeyRef: { name: rag-db-credentials, key: username } }
            - name: DB_PASS
              valueFrom: { secretKeyRef: { name: rag-db-credentials, key: password } }
          restartPolicy: OnFailure
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: query-service
  namespace: my-gdc-project
spec:
  replicas: 1
  selector:
    matchLabels:
      app: query-service
  template:
    metadata:
      labels:
        app: query-service
    spec:
      serviceAccountName: rag-sa
      containers:
      - name: query-service
        image: harbor.shared-services.gdc.local/my-org/rag-query:v7
        ports:
        - containerPort: 8080
        env:
        - name: DB_HOST
          valueFrom: { secretKeyRef: { name: rag-db-credentials, key: host } }
        - name: DB_USER
          valueFrom: { secretKeyRef: { name: rag-db-credentials, key: username } }
        - name: DB_PASS
          valueFrom: { secretKeyRef: { name: rag-db-credentials, key: password } }
        - name: DB_NAME
          value: "postgres"
        - name: GEMINI_ENDPOINT
          value: "http://llm-gateway.my-gdc-project.svc.cluster.local:80/generate"
        - name: GEMINI_MODEL
          value: "gemini-2.5-flash"
        - name: EMBEDDING_MODEL
          value: "text-embedding-004"
        - name: PROJECT_ID
          value: "my-gdc-project"
        - name: INPUT_BUCKET
          value: "raw-docs-my-gdc-project"
---
apiVersion: v1
kind: Service
metadata:
  name: query-service
  namespace: my-gdc-project
spec:
  selector:
    app: query-service
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
```

---

## **Section 5: Validation**

### 5.1 Stage Ingestion Document
1. Upload a PDF/Text document containing unique info to the target GDC bucket:
   ```shell
   gdcloud storage cp test-document.pdf gs://raw-docs-my-gdc-project/
   ```
2. Manually trigger the CronJob to run:
   ```shell
   kubectl create job --from=cronjob/doc-ingest manual-ingest-trigger-01 -n my-gdc-project
   ```
3. Watch ingestion logs to verify OCR text extraction and database commits:
   ```shell
   kubectl logs -l job-name=manual-ingest-trigger-01 -n my-gdc-project
   ```

### 5.2 Verify Query Service

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Send a prompt against the internal `query-service` querying the ingested document:

```bash
kubectl run p6-verify --rm -i --restart=Never -n my-gdc-project \
  --image=curlimages/curl --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 6 Resilient RAG Agent verified!" && \
    echo "✅ SUCCESS: Query service and vector database reached" && \
    echo "===============================================" && \
    curl -s -X POST http://query-service/ask -d "{\"question\": \"Summarize the contents of the test document.\"}" -H "Content-Type: application/json" && \
    echo ""
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 6 Resilient RAG Agent verified!
✅ SUCCESS: Query service and vector database reached
===============================================
{"answer":"..."}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: ClusterIP & Curl Verification
Determine ClusterIP and execute query manually:
```shell
export QUERY_IP=$(kubectl get service query-service -n my-gdc-project -o jsonpath='{.spec.clusterIP}')

curl -X POST http://${QUERY_IP}/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize the contents of the test document."}'
```
Ensure the model successfully returns an accurate answer based on the document text.

### 5.3 Live Operational Log Inspection
To validate live system execution and verify LLM gateway routing, inspect pod logs across key components:

```bash
# 1. Inspect RAG Query Service reasoning & vector retrieval logs
kubectl logs -l app=query-service -n my-gdc-project --tail=50 -f

# 2. Inspect Ingestion Job parsing, translation, & embedding logs
kubectl logs -l app=doc-ingest -n my-gdc-project --tail=50 -f

# 3. Inspect Gemma Inference Gateway routing & token generation logs
kubectl logs -l app=gemma-gateway -n my-gdc-project --tail=50 -f

# 4. Inspect PostgreSQL Vector Database logs
kubectl logs postgres-0 -n my-gdc-project --tail=50 -f
```

---

## **Section 6: Operations & Troubleshooting**

### 6.1 Database High Availability & Manual Failover

In GDC air-gapped, database clusters configured with `ZONAL_HA` (primary and standby replicas) do not automatically failover when the primary instance becomes unavailable. Failover must be triggered manually by an operator.

#### Option A: Manual (CLI)
To trigger a manual failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover rag-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml`)
Apply a `Failover` custom resource to trigger the failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-rag-db
  namespace: my-gdc-project
spec:
  dbclusterRef: rag-db
```

### 6.2 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `LLM Gateway Call Failed` | The `rag-sa` lacks required credentials or the Gateway endpoint is unreachable. | Verify `LLM_GATEWAY_URL` endpoint and ensure `ProjectPolicy` includes `Role/ai-inference-developer`. |
| `DB extension missing` | `pgvector` was not loaded or DB initialization script failed. | Connect to PostgreSQL as admin and re-run `CREATE EXTENSION vector;`. |
| `Out of memory (OOM)` | Large document sizes cause processing memory limits to break. | Scale container resource limits or split large PDFs into smaller text parts before uploading. |
