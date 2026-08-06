Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 6: Resilient RAG Agent

# Pattern 6: Resilient RAG Agent

**Use Case:** Document processing pipeline using platform AI APIs. This is a modern approach to a RAG solution using an agentic pattern.

## Architecture Schematic

```
+----------------------+      +----------------------+      +----------------------+
| GDC Storage (Object) |----->| GKE CronJob          |----->| Gemini (Multimodal)  |
| (Raw Docs)           |      | (Ingestion Pipeline) |      | (Audio/Image/Text)   |
+----------------------+      +----------------------+      +----------------------+
                                         |
                                         v
                              +----------------------+
                              | GDC Database Service |
                              | (PostgreSQL HA)      |
                              | (Vector Storage)     |
                              +----------------------+
                                         ^
                                         |
                                         | (Query)
                                         |
                              +----------------------+
                              | GKE Service          |
                              | (RAG Agent)          |
                              +----------------------+
                                         |
                     +-------------------+-------------------+
                     |                                       |
                     v                                       v
         +-----------------------+               +-----------------------+
         | Gemma Inference GW    |               | GDC AI Inference GW   |
         | (gdc_gemma_gw / vLLM) |               | (Gemini 3.5/3.1 Flash)|
         +-----------------------+               +-----------------------+
```

## Design & Resilience Strategy

This pattern describes a modern, resilient, agentic RAG solution for a GDC-ag environment, designed to answer questions about a private document corpus.

> [!IMPORTANT]
> **Document Corpus Scope & Query Handling**:
> * **Document-Centric Design**: Pattern 6 is specifically built to answer questions grounded in the user's uploaded/indexed document corpus stored in PostgreSQL (`pgvector`).
> * **Not Optimized for Generic Queries**: This pattern is **not** an open-ended general chat agent. If a user asks generic or out-of-scope questions without uploading relevant documents (or before the ingestion job runs), the agent's semantic search will return zero matching context chunks and will trigger a fallback error: `"Sorry, I encountered an error processing your request."`

> [!NOTE]
> **LLM Gateway Dependency & Migration Path**:
> * **Primary Gateway (`gdc_gemma_gw`)**: By default, this pattern depends on the self-hosted **Gemma Inference Gateway** (`../gdc_gemma_gw`), listening on HTTP port 80 (`http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`).
> * **Migration to Native GDC Gemini AI Gateway**: To migrate from Gemma Gateway to GDC Gemini AI Gateway or Vertex Gemini, update the deployment environment variables in `manifests/apps/query-service.yaml` and `manifests/apps/ingest-job.yaml`:
>   ```yaml
>   - name: LLM_PROVIDER
>     value: "gemini"
>   - name: LLM_GATEWAY_URL
>     value: "https://ai-gateway.shared-services.gdc.local/v1"
>   - name: GEMINI_MODEL
>     value: "google/gemini-3.5-flash"
>   - name: AO_PROJECT_ID
>     value: "projects/your-project-id"
>   ```

*   **Document Ingestion:** A GKE CronJob periodically scans a GDC Storage (Object) bucket. It coordinates a pre-processing pipeline:
    1.  **Source Triage:** Identifies file types.
    2.  **Multimodal Processing (Gemini):**
        *   **Audio:** Calls **Gemini 2.5 Flash** to transcribe speech to text.
        *   **Images:** Calls **Gemini 2.5 Flash** to describe images and extract visible text.
        *   **Translation:** Calls **Gemini 2.5 Flash** to translate non-English text to English.
*   **Embedding & Vector Storage:** The (now-processed) text is passed to the ingestion job's embedding service, which:
    1.  Converts text chunks to embeddings.
    2.  Stores embeddings in GDC Database Service (PostgreSQL with `pgvector`).
*   **Agent Service (Inference):** A GKE service using A2A, ADK, and MCP.
*   **Agent Logic (ReAct Loop):**
    1.  **Reasoning:** The agent receives a query and uses a "Thought -> Action -> Observation" loop to determine the best course of action.
    2.  **Tool Use:** It can use local tools like `search_knowledge_base` (semantic search) or `list_documents` (metadata query).
    3.  **Resilience (Fallback):** If the agentic loop times out or fails, the system automatically falls back to a standard RAG retrieval (Simple RAG) to ensure the user receives an answer based on vector storage content.
*   **Resilience:** The agent and ingestion services are stateless (replicas on GKE). All dependencies (Storage, PostgreSQL, LLM Gateway, and Gemini) are managed services on the GDC platform.
*   **Sizing:** Recommended node pool machine type for GKE workloads: `n2-standard-4-gdc`.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The Ingestion Job and RAG Agent application images must be built, scanned, and pushed to the internal GDC registry (Harbor).
2.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
3.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Supports approx. 50-100 concurrent users (heavy DB/LLM load).

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ingestion Job** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **RAG Agent** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-4-16` (Managed) | 4 | 16Gi | 100Gi | No |

**Scaling & Upgrades:**
*   **Database (Vector Search):** This is the primary bottleneck. If search latency increases (>500ms), upgrade the PostgreSQL instance to `db-custom-8-32` or higher.
*   **Agent Service:** Use HPA to scale the agent pods based on CPU usage.
*   **Ingestion:** If document processing is slow, increase the resources (CPU/RAM) for the Ingestion Job or parallelize the job (advanced configuration).

**Sizing Rationale:**
Vector search operations in PostgreSQL with `pgvector` are CPU and memory intensive. The ingestion job requires resources to handle document parsing and embedding generation in parallel.

## Production Gateway & Security Configuration

### 1. Gemma Gateway Service Topology
Pattern 6 consumes the **Gemma Inference Gateway** (`gdc_gemma_gw`) deployed as an in-cluster Kubernetes `Service` (`svc/gemma-gateway`) listening on **port 80**.
* **Target Endpoint**: `http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`
* **GPU Backend**: Serves `gemma-2-27b-it` or `gemma4:26b/31b` backends via vLLM / Ollama running on dedicated GPU node pools (`g2-standard-24` or GDC GPU nodes).

### 2. Air-Gapped NetworkPolicies
For GDC production compliance, apply NetworkPolicies to restrict ingress/egress:
* **Ingress**: Allow HTTP traffic on port 8080 from `frontend` or Gateway API to `query-service`.
* **Egress**: Allow `query-service` and `doc-ingest` egress strictly to `svc/gemma-gateway` (TCP 80), `svc/postgres` (TCP 5432), and internal DNS (UDP 53).

### 3. Keycloak OIDC Identity & Multi-Tenancy
For production single sign-on (SSO) and RBAC multi-tenancy:
* **OIDC Provider**: Deploy Keycloak using the [P12 Keycloak Blueprint](../p12-keycloak/README.md).
* **Identity Header Extraction**: Configure the GDC Gateway API / NGINX Ingress to validate JWT tokens and forward `X-User-ID` and `X-User-Role` headers to `query-service`.
* **Document Access Filtering**: PostgreSQL vector queries automatically enforce user document isolation (`owner_id = user_id OR scope = 'shared'`). Refer to [`docs/keycloak_integration_guide.md`](../docs/keycloak_integration_guide.md) for full OIDC details.

## Configuration

### Environment Variables

The following environment variables can be configured in `manifests/apps/ingest-job.yaml` and `manifests/apps/query-service.yaml`:

| Variable | Description | Default / GDC Example |
| :--- | :--- | :--- |
| `PROJECT_ID` | Your Google Cloud Project ID. | `your-project-id` |
| `INPUT_BUCKET` | GCS Bucket for raw documents. | `gs://raw-docs-${PROJECT_ID}` |
| `GEMINI_ENDPOINT` | Endpoint for Gemini API. | **GCP:** `https://us-central1-aiplatform.googleapis.com/...` <br> **GDC:** `https://<GDC_ENDPOINT>/v1/...` |
| `GEMINI_MODEL` | Gemini Model ID. | `gemini-2.5-flash` |
| `EMBEDDING_MODEL` | Vertex AI Embedding Model ID. | **GCP:** `text-embedding-004` <br> **GDC:** `text-embedding-gecko` (check local availability) |

### Blueprint Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -n test-project -r <YOUR_REGISTRY_URL> -d p6-resilient-rag-agent
```

## Required IAM Permissions

This pattern requires permissions for both the **user** deploying the application and the **service account** the application runs as.

**1. User Permissions:**
To deploy the resources, your user account will need the following GDC IAM roles:

*   **IAM Admin:** To create a new service account (`rag-sa`) and grant it project-level roles.
    *   `roles/iam.serviceAccountAdmin`
    *   `roles/project.iamAdmin`
*   **GKE Developer:** To deploy the CronJob and ServiceAccount to the GKE cluster.
    *   `roles/gke.developer`

**2. Service Account Permissions:**
The `rag-sa` service account itself will be granted the following roles by the user during setup, which it uses at runtime to call other GDC services:

*   **Vertex AI User** (if using ADC for Gemini)
*   OR **API Key Access** (if using API Key secret)

## Implementation

### Step 1: Configure IAM

You must explicitly grant your workloads permission to use GDC pre-trained APIs.

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

kubectl create sa rag-sa -n $PROJECT_ID
gdcloud iam service-accounts add-iam-policy-binding rag-sa --project=$PROJECT_ID --role=Role/ai-ocr-developer
gdcloud iam service-accounts add-iam-policy-binding rag-sa --project=$PROJECT_ID --role=Role/ai-translation-developer
```

**Option B: GitOps**

Sync the `manifests/gdc/iam/rag-permissions.yaml` file to your cluster.

### Step 2: Deploy Database
 
 **Option A: Manual (CLI)**
 
 ```bash
 export PROJECT_ID=<YOUR_PROJECT_ID>
 
 # 1. Create Managed Database Cluster (PostgreSQL HA)
 gdcloud database clusters create rag-db \
   --project=$PROJECT_ID --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA
 
 # 2. Create Connection Secret
 # Retrieve the IP address of your new DB instance and create the secret
 # DB_HOST=$(gdcloud database clusters describe rag-db --project=$PROJECT_ID --format="value(primaryInstance.ipAddress)")
 # kubectl create secret generic rag-db-credentials \
 #   --namespace=$PROJECT_ID \
 #   --from-literal=username=postgres \
 #   --from-literal=password=<YOUR_PASSWORD> \
 #   --from-literal=host=$DB_HOST \
 #   --from-literal=db_name=postgres
 ```
 
 **Option B: GitOps**
 
 Sync the `manifests/gdc/db/postgres.yaml` file to your cluster.
 
 ### Step 3: Initialize Database Schema

The application requires a specific database schema with the `pgvector` extension enabled.

**For GDC Production (PostgreSQL):**
You must manually apply the schema to your GDC Database Service instance, as the application user may not have permissions to install extensions.

1.  Connect to your PostgreSQL instance using `psql`.
2.  Run the following SQL commands:

    ```sql
    -- 1. Enable pgvector extension (Requires Superuser)
    CREATE EXTENSION IF NOT EXISTS vector;

    -- 2. Create Documents Table
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        filename TEXT UNIQUE,
        content TEXT,
        embedding vector(768), -- Matches text-embedding-004 dimensions
        owner_id TEXT DEFAULT NULL,
        source_path TEXT
    );

    -- 3. Create Chat History Tables
    CREATE TABLE IF NOT EXISTS chats (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ```

### Step 4: Deploy Ingestion Job

> **Note on Cloud Storage:** The GDC Object Storage (S3-compatible) bucket required for raw documents is automatically configured via the `ingest.yaml` manifest. If you are not using the provided manifest, you must manually create the bucket (e.g., `gs://raw-docs-${PROJECT_ID}`) before running the ingestion job.

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/apps/ingest-job.yaml
```

**Option B: GitOps**

Sync the `manifests/apps/ingest-job.yaml` file to your cluster.

## Testing

### Validation (Pre-deployment)

The `validate.sh` script performs a client-side dry run of all Kubernetes manifests to check for syntactical errors.

To run the validation:
```bash
cd test/
chmod +x validate.sh
./validate.sh
```

### Verification (Post-deployment)

The `verify.sh` script checks the status of the deployed GKE resources.

To run the verification:
```bash
cd test/
chmod +x verify.sh
./verify.sh
```

### Local Testing

You can run the validation and verification scripts locally using the provided test runner, which mocks the GDC and Kubernetes CLI commands.

```bash
# Run from the root of the repository
bash tests/run-local.sh
```

This will run the configuration tests and the verification logic for all patterns.

## Troubleshooting

### Ingestion Job Issues

If the ingestion job appears stuck or is creating too many pods, it may be due to an older version of the script that contained an infinite loop.

**Symptoms:**
*   Multiple `doc-ingest` pods in `Running` state.
*   New jobs are spawned but old ones never complete.

**Resolution:**
Run the following command to clean up all stuck ingestion jobs and pods:

```bash
kubectl get jobs -n test-project -o name | grep "doc-ingest" | xargs -r kubectl delete -n test-project
```

This will delete the jobs, which in turn deletes the associated pods. The CronJob will spawn a fresh (and hopefully fixed) job at the next scheduled interval.

### Resetting the Environment

If you need to wipe all data and start fresh (e.g., to clear old non-RBAC documents or reset chat history), run the following commands:

```bash
# 1. Clear GCS Bucket (WARNING: Deletes all uploaded documents)
# Ensure BUCKET_NAME is set
gcloud storage rm -r ${BUCKET_NAME}/**

# 2. Clear Database Tables (WARNING: Deletes all metadata and chat history)
kubectl exec -n test-project postgres-0 -- psql -U user -d ragdb -c "TRUNCATE documents, chats, messages;"

# 3. Restart Ingestion Job (to reset its processed cache)
kubectl delete job -n test-project -l app=ingest-job
kubectl create job --from=cronjob/doc-ingest manual-reset -n test-project
```
## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p6-resilient-rag-agent
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p6-resilient-rag-agent
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p6-resilient-rag-agent-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p6-resilient-rag-agent-gdc-images.tar` (The bundled container images)
    *   `p6-resilient-rag-agent-BOM.txt` and `p6-resilient-rag-agent-manifest.txt` (Integrity checksums)
    *   `p6-resilient-rag-agent-README.md` (Standalone deployment instructions)

*(Note: Unlike the infrastructure-heavy patterns, this robust pattern does not strictly require complex 3rd-party external Helm charts or images dropped into the `artifacts/` pool via the dependencies script—it is cleanly self-contained in the 3 standard `.tar` / `.txt` files above).*
### 4. Unpack and Deploy
Once transferred to your secure GDC environment, you must unpack and deploy the assets logically:

> **Optional: Hot-Patching Manifests Offline**
> If you need to deploy this pattern to a *different* namespace, project ID, or registry host than the one you originally injected during the pre-packaging step, you do not need to resend the payload across the air-gap. You can dynamically hot-patch the extracted manifests locally:
> ```bash
> # Define your old (packaged) and new (target) variables
> OLD_PROJECT="<PACKAGED_PROJECT_ID>"
> NEW_PROJECT="<NEW_PROJECT_ID>"
> OLD_NAMESPACE="<PACKAGED_NAMESPACE>"
> NEW_NAMESPACE="<NEW_NAMESPACE>"
> OLD_REGISTRY="<PACKAGED_REGISTRY_HOST>"
> NEW_REGISTRY="<NEW_REGISTRY_HOST>"
> 
> # Recursively execute string replacement across all extracted YAML files
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_PROJECT}|${NEW_PROJECT}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_NAMESPACE}|${NEW_NAMESPACE}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_REGISTRY}|${NEW_REGISTRY}|g" {} +
> ```


1. **Authenticate Docker with Harbor:** Log in to your target GDC environment's Harbor registry:
   ```bash
   export REGISTRY_HOST="harbor.gdc.local"
   export ROBOT_NAME="robot\$puller"  # Escape the $ character
   export ROBOT_SECRET="your-robot-secret"

   docker login ${REGISTRY_HOST} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
   ```

2. **Load and Push Local Container Images:** Extrapolate the locally-built images into your secure internal registry:
   ```bash
   ./scripts/unpack-for-gdc.sh p6-resilient-rag-agent-gdc-images.tar harbor.gdc.local/library
   ```

3. **Load and Push Global Container Images (If Applicable):** For blueprints bridging global components (e.g. Hashicorp Vault, external pipelines), manually load and tag the artifacts using standard Docker commands:
   ```bash
   docker load -i artifacts/external-dependencies/images/...
   docker tag ... harbor.gdc.local/library/...
   docker push ...
   ```

4. **Extract and Apply Kubernetes Manifests:** Extract the exact blueprints generated during the `-d` inject step and apply them to your cluster:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf p6-resilient-rag-agent-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

5. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.

---

## Advanced Configuration: Identity Management

By default, Pattern 6 utilizes a lightweight "Mock Auth" system intended strictly for feature validation and testing. The architecture itself is completely decoupled from any single Identity Provider (IdP). 

If you wish to advance this architecture to a state of production-readiness or require multi-tenant access control for "multiple users", you can seamlessly overlay Keycloak via standard OIDC.

For step-by-step instructions on integrating this pattern with the **P12-Keycloak** blueprint, please refer to the dedicated [Keycloak Integration Guide](../docs/keycloak_integration_guide.md).
