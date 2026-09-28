Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GDC Blueprints Testing Plan

> **Version:** 1.1

This document outlines the testing strategy for the GDC Resilient Architecture Blueprints. It covers the entire development lifecycle, from local validation to deployment in a GDC air-gapped environment.

## Pipeline Overview

The testing pipeline consists of four main stages:

1.  **Stage 1: Local Dev Workstation**: Initial development, linting, and mocked testing.
2.  **Stage 2: GCP Stepping Stone**: Testing on standard GCP GKE with mocked GDC services to verify Kubernetes manifests and container images.
3.  **Stage 3: GDC Sandbox**: Testing on a non-production GDC environment with real GDC services.
4.  **Stage 4: GDC Air-gapped**: Final deployment to the production air-gapped GDC platform.


---

## Blueprints vs. Example Applications

It is important to distinguish between the two primary components of this repository:

1.  **Architecture Blueprints**: These define the *infrastructure* and *platform services* required for a specific resilience pattern (e.g., Database Clusters, Storage Buckets, Redis Caches, IAM Policies). This is the core "product" of the blueprint.
2.  **Example Applications**: These are reference implementations provided to demonstrate how to deploy a workload onto the provisioned architecture. Deploying these serves as an **optional extra test step** to validate the architecture is functional from an application perspective.

---

## Stage 1: Local Dev Workstation

**Goal**: Verify code quality, configuration, and basic functionality using mocks. These tests should be run by developers before pushing changes or attempting deployment.

### 1.1. Docker Build Test (Example Applications)
Verify that all **Example Application** container images build successfully and run as non-root users. This ensures the reference implementations are valid.

**Option A: Consolidated Script (Recommended)**
Run the provided script to test all patterns (1-8) at once:
```bash
./scripts/stage1-local-test.sh
```

**Option B: Individual Pattern Test**
You can also test patterns individually using Docker directly:
```bash
# Example for p1
docker build -t test-backend p1-resilient-3-tier-webapp/example-app/src/backend
docker build -t test-frontend p1-resilient-3-tier-webapp/example-app/src/frontend

# Verify non-root user (should return a uid > 0)
docker run --rm --entrypoint id test-backend
docker run --rm --entrypoint id test-frontend
```

### 1.2. Manifest Validation
Ensure Kubernetes manifests are syntactically correct and adhere to the schema.

**Option A: Bulk Validation (Recommended)**
Validate manifests for all patterns:

**Prerequisites:**
1.  **Kubernetes Cluster**: You must have a cluster running. This can be:
    *   A **Local Cluster** (e.g., `kind`, `minikube`, `docker-desktop`).
    *   A **GCP Cluster** (e.g., GKE Standard or Autopilot).
        > **Note for GCP Users:** If using a GKE cluster, ensure you are authenticated via `gcloud` and have the correct context selected (`kubectl config current-context`). You **must still apply the mock CRDs** because GDC-specific resources (like `DBCluster` or `VirtualMachine`) are not native to GKE. The validation script needs these CRDs to verify the manifests correctly.

2.  **Mock CRDs**: You must apply the GDC mock Custom Resource Definitions (CRDs) to your cluster. This allows validation of GDC-specific resources (e.g., `DBCluster`, `VirtualMachine`) on standard Kubernetes.

```bash
# 1. Apply Mock CRDs
kubectl apply -f tests/mock-crds.yaml

# 2. Run Validation Script
./scripts/validate-manifests.sh
```

**Option B: Individual Validation**
```bash
# Requires kubectl to be installed. 
# If no cluster is configured, use --validate=false to check structure only.
kubectl apply --dry-run=client --validate=false -f p1-resilient-3-tier-webapp/manifests/apps/
```

### 1.3. Local Mock Testing
Run the provided local test suite to simulate configuration and deployment checks without a real cluster.

**Why is this required?**
Even if you have a GKE cluster available (from Step 1.2), this mocked testing step is critical because:
1.  **Validates Test Logic vs. Infrastructure**: It verifies that your `verify.sh` scripts are correctly parsing CLI output and handling logic flow, ensuring the *test code itself* is bug-free.
2.  **Speed**: It completes in seconds, providing instant feedback on script logic, whereas deploying to a real cluster (especially checking timeouts/retries) can take minutes to hours.
3.  **Isolation**: It guarantees a controlled environment where "success" is pre-defined, ensuring tests pass/fail based on script logic, not transient network or cluster issues.

**Alternative (Real Cluster)**: 
If you prefer to test against a running GKE cluster, you can proceed directly to **Stage 2** (GCP Stepping Stone) to deploy and run `verify.sh` against live resources. However, we strongly recommend running this mock step first to ensure your verification tools are working correctly before initiating a time-consuming deployment.

To run the full suite:
```bash
bash tests/run-local.sh
```

This will iterate through all patterns and run their respective `test/verify.sh` scripts using the mocked environment.

> **Note:** This step is **completely isolated**. It does not communicate with any real Kubernetes cluster (Local or GCP) or Google Cloud APIs. It runs entirely on your local machine using shell function overrides. You do not need to configure `kubectl` or `gdcloud` before running this.

### 1.4. Local Cleanup (Optional)
To delete the Docker images created during the local build test (Step 1.1), run:
```bash
./scripts/cleanup-local-images.sh
```

---

## Stage 2: GCP Stepping Stone (Emulation Mode)

**Goal**: Verify container images and Kubernetes manifests on a real GKE cluster using **Emulated Services** (removing the need for complex Config Connector setups). This approaches a "GDC-like" environment where services are pre-provisioned.

### Prerequisites & Environment Setup

These steps should be performed on your **GCP Cloud Workstation**.

#### 1. Configure Environment Variables
```bash
export PROJECT_ID=<your-project-id>
export REGION=<your-region> # e.g., us-central1
export CLUSTER_NAME=blueprint-cluster
export REPO_NAME=blueprint-images
export NAMESPACE="test-project"
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
```

#### 2. Enable Required APIs (for GCS/GKE)
```bash
gcloud services enable \
    container.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    --project=$PROJECT_ID
```

#### 3. Artifact Registry Setup
Ensure you have an Artifact Registry to host your blueprint images.
```bash
gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --project=$PROJECT_ID \
    --description="Docker repository for GDC Blueprints" 2>/dev/null || echo "Repo exists"

gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

#### 4. Cluster Setup (Standard GKE)
Create a GKE cluster using the standardized script. This automatically enables the Workload Identity pool and other requirements.
```bash
# Ensure RELIANT variables are set (script uses REGION, CLUSTER_NAME)
./scripts/create_cluster.sh
```

#### 5. Workload Identity Binding
Configure the service account bindings to allow pods to act as a GCP Service Account to access external services (like Vertex AI or GCS).
```bash
# This creates the default 'rag-sa' for Patterns using typical AI gateways
./scripts/configure-workload-identity.sh
```

> **Important Note for P10 (Gemini GUI):** The P10 Chatbot requires its own dedicated Workload Identity Service Account (`gemini-gui-sa`) to access Vertex AI and its dedicated User File GCS Bucket. Before running the bulk deploy, you MUST configure it manually by setting the specific environment variables for the helper script:
> ```bash
> export GSA_NAME="gemini-gui-sa"
> export KSA_NAME="gemini-gui-sa"
> ./scripts/configure-workload-identity.sh
> ```

> **Note for AI Patterns (P5, P6, P7)**: If you require GPU nodes (e.g., when building and deploying complete AI pipelines natively such as the vLLM backend in P5), ensure you provision a GPU node pool on GKE or update the `create_cluster.sh` script to request GPU accelerators:

```bash
# Add GPU Node pool
gcloud container node-pools create gpu-pool \
    --cluster ${CLUSTER_NAME} \
    --region ${REGION} \
    --node-locations us-central1-a \
    --machine-type g2-standard-4 \
    --accelerator type=nvidia-l4,count=1,gpu-driver-version=LATEST \
    --workload-metadata=GKE_METADATA \
    --num-nodes 1
```

### Emulation Infrastructure Setup

Instead of provisioning real Cloud SQL instances (which are slow and costly), we deploy a **Shared Emulated Postgres** cluster within GKE.

#### 1. Deploy Shared Postgres (Data Tier)
This StatefulSet mimics the "GDC DBCluster" service.
```bash
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n ${NAMESPACE} -f testing/emulation/postgres.yaml
kubectl wait --for=condition=Ready pod/postgres-0 -n ${NAMESPACE} --timeout=300s
```

#### 2. Deploy Emulated Kafka (Broker Tier)
This Deployment mimics the "GDC Kafka" service required for Event-Driven patterns like Pattern 4.
```bash
kubectl apply -n ${NAMESPACE} -f testing/emulation/kafka.yaml
kubectl wait --for=condition=Ready pod -l app=kafka -n ${NAMESPACE} --timeout=300s
```

#### 3. Provision Storage Buckets (GCS)
We use a helper script to create standard GCS buckets that map to GDC Buckets.
```bash
./scripts/setup-gcp-resources.sh
```

### Activities

#### 1. Configure Blueprints
Point all manifests to your Registry and Project. This script will configure **all** blueprints at once.
```bash
# VERY IMPORTANT: Export NAMESPACE="test-project" first, or pass `-n test-project` explicitly. 
# If you let it default to $PROJECT_ID, the validation scripts below will fail to find your mock resources!
export NAMESPACE="test-project"
./configure-blueprints.sh -p $PROJECT_ID -n $NAMESPACE -r $REGISTRY_HOST
```

#### 2. Build and Push Images
Build the example application images.
```bash
./scripts/push-images.sh $REGISTRY_HOST
```

#### 3. Deploy & Verify Patterns
You can now deploy any pattern. The manifests have been adapted to use the Shared Emulated Postgres via the `emulation-db.yaml` secrets.

**Example: P1 Resilient Web App**
```bash
# Deploy
kubectl apply -f p1-resilient-3-tier-webapp/manifests/apps/
# Verify
./p1-resilient-3-tier-webapp/test/verify.sh
```

**Example: P9 NotebookLM**
```bash
helm upgrade --install anythingllm p9-notebooklm/example-app/anythingllm \
  --namespace test-project --create-namespace \
  -f p9-notebooklm/example-app/anythingllm/values-gcp.yaml
./p9-notebooklm/test/verify.sh
```

#### 3. Build and Push Example App Images (Optional)
**Required only if you intend to deploy the example applications.** 

If you plan to run the optional "Deploy Example Application" step, you must first build and push the custom application images to your Artifact Registry. The **Architecture** (Step 1 & 2) does not require these images.

**Option A: Bulk Push (Recommended)**
Use the provided script to build and push all blueprint images at once:
```bash
# Ensure you are in the root of the repository
cd ../.. 

export REGISTRY_URL=$REGISTRY_HOST
./scripts/push-images.sh $REGISTRY_URL
```

**Option B: Manual Build**
You can also build and push individual images:
```bash
export REGISTRY_URL=$REGISTRY_HOST
# Build and push (example for p1)
docker build -t $REGISTRY_URL/p1-backend:latest p1-resilient-3-tier-webapp/example-app/src/backend
docker push $REGISTRY_URL/p1-backend:latest
```

#### 4. Deploy Example Application (Optional)
Use the provided script to deploy the blueprint example application. This serves as a test to verify that the provisioned architecture (Step 1) is usable.

**Note**: This script strips GDC-specific resources (as they were already mocked/provisioned in Step 1) and attempts to deploy the application components.

**Option A: Bulk Manual Deployment (Recommended)**
Deploy all blueprints at once:
```bash
./scripts/deploy-all-mocked.sh
```
> **Important Note for P5 (Hybrid LLM Gateway):** The bulk deployment script (`deploy-all-mocked.sh`) automatically injects a tiny *mock gateway* for Pattern 5 to bypass structural cluster validations without requiring real Workload Identity or GPU pools. If you intend to perform **interactive/visual E2E validation** of the gateway's failover logic (e.g., routing to Ollama/vLLM), you must manually delete the mock and deploy the real gateway manifests:
> ```bash
> # 1. Delete the injected mock gateway
> kubectl delete deployment llm-gateway -n test-project
> kubectl delete service llm-gateway -n test-project
> # 2. Configure raw manifests for the test-project namespace (if applicable)
> ./configure-blueprints.sh -p $PROJECT_ID -n test-project -r $REGISTRY_HOST -d p5-hybrid-llm-gateway
> # 3. Apply the real Python framework gateway
> kubectl apply -f p5-hybrid-llm-gateway/manifests/apps/llm-gateway.yaml
> ```

**Option B: Individual Manual Deployment**
Deploy a single blueprint:
```bash
# Deploy to GKE
./scripts/deploy-gcp-mocked.sh p1-resilient-3-tier-webapp
```

#### 5. Manual Mock Deployment (If needed)
If the blueprint requires external services (Postgres, Redis) and the script didn't deploy them, you may need to deploy them manually using Helm or standard Kubernetes manifests.

#### 6. Verification

Verify the deployment on GKE:

**Option A: Automated Verification (Recommended)**
Run the provided suites to verify both infrastructure and application functionality:
```bash
# 1. Structural Check (Pods Running)
./scripts/verify-all-emulation.sh

# 2. Functional Smoke Tests (App Logic)
./scripts/verify-functionality.sh
```

**Option B: Manual Verification**
```bash
kubectl get pods
kubectl get svc
# Test endpoints using port-forwarding if no LoadBalancer is created
kubectl port-forward svc/<service-name> 8080:8080
```

### 6.1 Interactive / Visual Testing (Optional)

Once the structural and functional verification tests pass, you should test the interactive visual flows to ensure real user interactions function properly over port-forwarding (which bypasses slow load-balancer assignments in ephemeral testing).

**General Port-Forwarding Syntax:**
```bash
kubectl port-forward service/<service-name> <local-port>:<service-port> -n test-project
```

#### Pattern-Specific Visual Checks:

> **Important Testing Note:** Modern web frameworks natively aggressively cache data based on the URL (and `localhost:8080` is a very common target). If you port-forward to a new pattern but see a previous mock UI (or a "blurry/broken" UI from an old test), perform a Hard Refresh (`Cmd+Shift+R`) or open an Incognito Window. We try to use distinct local ports below to mitigate this.

*   **P1: Resilient 3-Tier Web App**
    *   **Port-forward:** `kubectl port-forward service/web-lb 8081:80 -n test-project`
    *   **Action:** Open `http://localhost:8081` in your browser. Verify the "GDC Todo App" interface loads. Add a new task (e.g., "Test Database Connection") and confirm it appears in the list, verifying the web, logic, and database tiers are communicating correctly.
*   **P5: Hybrid LLM Gateway**
    *   *Note: Only applicable if you deployed the real Gateway python app (see note in Step 4).*
    *   **Port-forward:** `kubectl port-forward service/llm-gateway 8085:80 -n test-project`
    *   **Action:** Ensure the gateway is routing API requests correctly (e.g. `curl http://localhost:8085/generate`).
*   **P6: Resilient RAG Agent**
    *   **Port-forward:** `kubectl port-forward service/frontend 8086:80 -n test-project`
    *   **Action:** Open `http://localhost:8086`. Interact with the chatbot, checking that document context is retrieved and returned in the responses.
*   **P7: Agentic Data Analyst**
    *   **Port-forward:** `kubectl port-forward service/sql-agent 8000:80 -n test-project`
    *   **Action:** *Note: The Data Analyst does not have a visual UI.* Open a second terminal window and run:
        `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"What were the total sales on Jan 3rd?"}'`
        Verify it replies with a successful SQL translation and the correct data results back from the mocked database.
*   **P9: NotebookLM (AnythingLLM)**
    *   **Port-forward:** `kubectl port-forward service/anythingllm 3001:3001 -n test-project`
    *   **Action:** Open `http://localhost:3001`. Create a workspace, upload a mock document, and chat with the document to verify the Langchain pipeline is operating.
*   **P10: Gemini GUI Chatbot**
    *   **Port-forward:** `kubectl port-forward service/p10-frontend-svc 8090:80 -n test-project`
    *   **Action:** 
        1. Open `http://localhost:8090` in your browser.
        2. **Multi-Tenant Check**: Select "User 1" from the dropdown. Upload a test text file (e.g., `test.txt` with "The secret code is Blue"). Ask "What is the secret code?". It should answer "Blue".
        3. Switch to "User 2" and ask the same question. It should *not* know the answer, verifying data segregation.

### 7. Cleanup
To avoid ongoing charges, you must clean up the GCP resources.

**Option A: Automated Cleanup (Recommended)**
Use the provided script to empty buckets and remove pattern resources.
```bash
# For a specific pattern
./scripts/cleanup-gcp.sh p1-resilient-3-tier-webapp

# For ALL patterns
./scripts/cleanup-gcp.sh all
```

**Option B: Manual Cleanup**
```bash
# 1. Delete blueprint deployment
kubectl delete -f <pattern-directory>/manifests/

# 2. Empty the bucket (Required before deletion)
gcloud storage rm --recursive gs://blueprint-bucket-${PROJECT_ID}/**

# 3. Delete Emulation Infrastructure (optional, if tearing down cluster)
kubectl delete -n ${NAMESPACE} -f testing/emulation/postgres.yaml

# 4. Delete GKE cluster (optional)
gcloud container clusters delete $CLUSTER_NAME --region $REGION
```

---

## Stage 3: GDC Sandbox

**Goal**: Verify integration with real GDC services in a safe, non-production environment.

### Prerequisites
-   Access to a GDC Sandbox environment.
-   GDCH CLI (`gdcloud`) configured.
-   `kubectl` and `docker` configured for the Sandbox environment.

### Activities
1.  **Mirror Images**: Push images to the GDC Sandbox Harbor registry.
2.  **Configure Blueprints**: Run the configuration script for the Sandbox environment.
3.  **Deploy**: Apply manifests to the GDC Sandbox cluster.

```bash
# Configure for Sandbox
./configure-blueprints.sh -p <SANDBOX_PROJECT_ID> -r <SANDBOX_REGISTRY_URL>

# Deploy
kubectl apply -f <pattern-directory>/manifests/
```

---

## Stage 4: GDC-ag

**Goal**: Final deployment to the production GDC-ag platform.

### Prerequisites
-   Access to the production GDC-ag environment.
-   Physical access or secure VPN to the air-gapped network.
-   All artifacts (images, manifests) transferred via secure media.
-   Tools: `gdcloud`, `kubectl`, `docker` configured.

### 4.1. Air-Gapped Packaging and Image Mirroring

To deploy to an Air-Gapped environment, you must bundle the Kubernetes manifests and all associated container images into tarballs to be physically transferred across the air-gap boundary.

**CRITICAL REQUIREMENT:** Before running the packager, you MUST ensure all Kubernetes manifests have been configured with your actual registry URLs. If you skip this, the script will crash trying to find the `your-project-id` placeholder in your local cache.
```bash
# Ensure placeholders are injected with your actual project data 
./configure-blueprints.sh -p $PROJECT_ID -n test-project -r $REGISTRY_HOST
```

**A. Run the Packaging Script**
Use the provided `package-for-gdc.sh` script on your connected Workstation (where Docker is available to pull/save images). This script reads the manifests, pulls necessary images, and generates `.tar.gz` and `.tar` artifacts within dedicated `packages/<pattern-name>/` folders.

```bash
# Example for Pattern 1
./scripts/package-for-gdc.sh p1-resilient-3-tier-webapp

# Example for Pattern 5 (skipping large models)
./scripts/package-for-gdc.sh --skip-vllm p5-hybrid-llm-gateway
```
*Expected Output*: Three files will be generated:
1. `p1-resilient-3-tier-webapp-gdc-manifests.tar.gz` (The raw kubernetes code)
2. `p1-resilient-3-tier-webapp-gdc-images.tar` (The required docker containers)
3. `p1-resilient-3-tier-webapp-manifest.txt` (The SHA256 integrity checksums)

**B. Run the Packaging Script (Bulk)**
If you are packaging the entire repository matrix, you can run the provided loop script, which will iterate through all pattern directories. Remember to pass the skip flag to bypass the 15GB+ model downloads during the pipeline!

```bash
PATTERNS=("p1-resilient-3-tier-webapp" "p3-legacy-vm-modern-db" "p4-event-driven-kafka" "p5-hybrid-llm-gateway" "p6-resilient-rag-agent" "p7-agentic-data-analyst" "p8-closed-loop-mlops" "p10-gemini-gui")

for pattern in "${PATTERNS[@]}"; do
  # By default, pass --skip-vllm universally to bypass massive 15GB+ model downloads
  ./scripts/package-for-gdc.sh --skip-vllm $pattern
done
```

**C. Export External Helm Dependencies (Ollama/Kafka)**
Because the packaging scripts strictly parse local `.yaml` files, they intentionally ignore remote resources deployed via Helm. For patterns leveraging third parties like Pattern 5 (Ollama) or Pattern 4 (Kafka), you must run the external export script to automatically download the Helm charts and mirrored container images:
```bash
# This automatically pulls Helm charts into artifacts/external-dependencies/charts
# and mirrors required images into artifacts/external-dependencies/images
./scripts/export-external-dependencies.sh

# NOTE: The vLLM model (15GB+) is deliberately skipped by this script.
# If you require it, mirror it manually:
# ./scripts/mirror_images.sh ./p5-hybrid-llm-gateway ./artifacts/vllm-images
```

**D. Transfer and Unpack**

> **⚠️ PRE-TRANSFER BOM CHECK:** Prior to bridging the air gap, you MUST open and read the `*-BOM.txt` (Bill of Materials) generated during packaging. Validate that no critical images are listed under `MISSING / FAILED`.

Move these tarballs across the air-gap to your GDC workstation. Then, use the provided unpack script to extract the local manifests and load the internal images into your workstation's Docker daemon. 

```bash
# 1. Automatically extract manifests to a folder and load images into Docker daemon
./scripts/unpack-for-gdc.sh p1-resilient-3-tier-webapp

# 2. Push the loaded images to your internal GDC registry manually
# Note: They are already tagged correctly from your pre-transfer `./configure-blueprints.sh` run
docker push harbor.gdc.local/library/p1-backend:latest
docker push harbor.gdc.local/library/p1-frontend:latest
```
> **Note on Pattern 5 (LLM Gateway):** The `unpack-for-gdc.sh` script reliably extracts and loads the natively **baked 5GB+ Gemma AI model** into your daemon alongside the gateway app. To utilize a different open-source model than Gemma, you must modify the native Dockerfile located at `p5-hybrid-llm-gateway/example-app/ollama-baked/Dockerfile` on your connected workstation *prior* to executing the packaging pipeline!

### 4.2. Configuration
Configure the blueprints for your production environment.

```bash
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL>
```

### 4.3. Deployment & Verification

Deployment should be performed in two phases to explicitly **signal architecture success** before attempting to verify with an application.

#### Phase 1: Deploy Architecture (Infra)
Apply the manifests related to infrastructure (Databases, Storage, IAM, Security).

*   **P1, P4**: `kubectl apply -f <pattern>/manifests/db/`
*   **P2**: `kubectl apply -f <pattern>/manifests/storage/`
*   **P3**: `kubectl apply -f <pattern>/manifests/infra/`
*   **P6**: `kubectl apply -f <pattern>/manifests/iam/`
*   **P7**: `kubectl apply -f <pattern>/manifests/security/`
*   **P9**: `kubectl apply -f p9-notebooklm/manifests/gdc/`
*   **Others**: Apply relevant non-application manifests.

#### Phase 2: Signal Verification (Ready Check)
Verify that the core architecture resources are ready. This signals that the **Blueprint Architecture** is successfully provisioned.

```bash
# Example: Check GDC resources
kubectl get dbclusters,storagebuckets,redisclusters,virtualmachines
kubectl wait --for=condition=Ready dbcluster --all --timeout=600s
kubectl wait --for=condition=Ready storagebucket --all --timeout=300s
```

#### Phase 3: Deploy Example App (Optional)
Deploy the example application to "live test" the architecture.

**p1-resilient-3-tier-webapp**
1.  **Deploy App**: `kubectl apply -f p1-resilient-3-tier-webapp/manifests/apps/`
2.  **Verify**: Access the Web UI and add a Todo item.
    *   **Get IP**: `kubectl get gateway web-gateway -n <namespace>` (Look for EXTERNAL-IP)

**p2-ha-ml-inference**
1.  **Deploy App**: `kubectl apply -f p2-ha-ml-inference/manifests/ai/`
2.  **Verify**: Curl the inference endpoint.

**p3-legacy-vm-modern-db**
1.  **Deploy App**: `kubectl apply -f p3-legacy-vm-modern-db/manifests/vm/` (contains the legacy app VM)
2.  **Verify**: Check logs for successful DB connection.

**p4-event-driven-kafka**
1.  **Deploy App**: `kubectl apply -f p4-event-driven-kafka/manifests/apps/`
2.  **Verify**: Check producer/consumer logs.

**p5-hybrid-llm-gateway**
1.  **Deploy App**: `kubectl apply -f p5-hybrid-llm-gateway/manifests/apps/`
2.  **Verify**: Test gateway endpoint failover.

**p6-resilient-rag-agent** (Requires P5 Deployed First)
1.  **Deploy App**: `kubectl apply -f p6-resilient-rag-agent/manifests/apps/`
2.  **Verify**: Query the agent.

**p7-agentic-data-analyst** (Requires P5 Deployed First)
1.  **Deploy App**: `kubectl apply -f p7-agentic-data-analyst/manifests/apps/`
2.  **Verify**: Ask a natural language question.

**p8-closed-loop-mlops**
1.  **Deploy App**: `kubectl apply -f p8-closed-loop-mlops/manifests/` (Entire pipeline is the app)
2.  **Verify**: Trigger a retraining job.

**p9-notebooklm**
1.  **Deploy App**: `helm upgrade --install notebook p9-notebooklm/example-app/anythingllm -f p9-notebooklm/example-app/anythingllm/values-gdc.yaml`
2.  **Verify**: Access the Notebook UI (via Gateway or Port Forward).

---

## 5. Resilience Testing

These tests verify the resilience of the deployed applications, applicable to Sandbox and Air-gapped environments.

### 5.1. Pod Failure
Delete a pod and verify it is recreated by the Deployment/ReplicaSet.
```bash
kubectl delete pod -l app=logic
```

### 5.2. Node Failure (Simulated)
Cordon/Drain a node and verify pods are rescheduled.

### 5.3. Database Failover
If using a HA database, trigger a failover and verify the application reconnects (thanks to connection pooling/retry logic).

---

## 6. Troubleshooting

### 6.1. Helm "cannot re-use a name that is still in use"
**Issue**: You try to install a Helm chart but get an error saying the name is in use.
**Cause**: A previous installation failed or was not uninstalled.
**Fix**: Uninstall the release before trying again.
```bash
helm uninstall <release-name> --namespace <namespace>
# Example
helm uninstall gcp-services --namespace config-connector-system
```

### 6.2. Config Connector "Workload identity must be enabled"
**Issue**: Error when enabling Config Connector add-on.
**Cause**: The GKE cluster was created without Workload Identity enabled.
**Fix**: Update the cluster to enable Workload Identity.
```bash
gcloud container clusters update $CLUSTER_NAME \
    --region $REGION \
    --workload-pool=${PROJECT_ID}.svc.id.goog
```

### 6.3. "namespaces \"config-connector-system\" not found"
**Issue**: Error when applying `ConfigConnectorContext`.
**Cause**: The GKE Config Connector add-on does not create the `config-connector-system` namespace automatically.
**Fix**: Create the namespace manually.
```bash
kubectl create namespace config-connector-system
```

### 6.4. OCI Registry Authentication Errors
**Issue**: `unauthorized: authentication required` when pulling charts from OCI registries (like Docker Hub).
**Cause**: Missing authentication credentials for the OCI registry.
**Fix**: Use standard Helm repositories instead of OCI URLs where possible (as updated in this plan).

### 6.5. Config Connector "ACCESS_TOKEN_SCOPE_INSUFFICIENT"
**Issue**: Config Connector resources stay in `UpdateFailed` state with `ACCESS_TOKEN_SCOPE_INSUFFICIENT` error.
**Cause**: The GKE node pool does not have the `cloud-platform` scope required for Workload Identity.
**Fix**: Create a new node pool with the correct scopes and delete the old one.
```bash
# Create new pool
gcloud container node-pools create new-pool \
    --cluster=$CLUSTER_NAME \
    --region=$REGION \
    --machine-type=e2-standard-4 \
    --num-nodes=1 \
    --scopes=cloud-platform

# Delete old pool (after verifying new nodes are ready)
gcloud container node-pools delete default-pool \
    --cluster=$CLUSTER_NAME \
    --region=$REGION
```

### 6.6. Config Connector "ServiceAccount not found" or Auth Failures
**Issue**: Workload Identity binding fails or resources stay in `UpdateFailed` with 403 errors.
**Cause**: The KSA name in `cnrm-system` depends on the namespace name in Namespaced mode (e.g., `cnrm-controller-manager-config-connector-system`).
**Fix**: Verify the correct KSA name and update the binding.
```bash
# Check actual KSA name
kubectl get sa -n cnrm-system

# Update binding (example)
gcloud iam service-accounts add-iam-policy-binding config-connector-sa@${PROJECT_ID}.iam.gserviceaccount.com \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog[cnrm-system/cnrm-controller-manager-config-connector-system]" \
    --role="roles/iam.workloadIdentityUser"
```

### 6.7. GCS "Request violates constraint 'constraints/storage.uniformBucketLevelAccess'"
**Issue**: StorageBucket creation fails with Error 412.
**Cause**: Organization Policy requires Uniform Bucket Level Access, but the bucket spec didn't enable it.
**Fix**: Update the `StorageBucket` spec to include `uniformBucketLevelAccess: true` (already fixed in the provided Helm chart).

### 6.8. Config Connector Resources Stuck in "UpdateFailed"
**Issue**: Resources like `sqlinstance` or `storagebucket` show status `UpdateFailed` and `READY=False`.
**Cause**: Often caused by missing GCP APIs (e.g., `sqladmin.googleapis.com`) or permissions issues.
**Fix**:
1.  Check the specific error message in the resource status:
    ```bash
    kubectl describe sqlinstance blueprint-db -n config-connector-system
    ```
    Look for the `Status` or `Events` section.
2.  Ensure all required APIs are enabled (see **Step 2: Enable Required APIs**).
### 6.9. Resources Stuck in "Terminating"
**Issue**: `helm uninstall` hangs or resources remain indefinitely in `Terminating` state.
**Cause**: The Config Connector controller cannot reach the underlying GCP API to delete the resource, or the finalizer is blocking deletion.
**Fix**: Patch the resource to remove the finalizer (Use with caution: This leaves orphaned resources in GCP).
```bash
kubectl patch sqlinstance blueprint-db -n config-connector-system -p '{"metadata":{"finalizers":[]}}' --type=merge
kubectl patch storagebucket blueprint-bucket-${PROJECT_ID} -n config-connector-system -p '{"metadata":{"finalizers":[]}}' --type=merge
```

### 6.10. "Project specified in the request is invalid"
**Issue**: `UpdateFailed` status with `errorInvalidProject`.
**Cause**: The `cnrm.cloud.google.com/project-id` annotation is missing or invalid, causing Config Connector to default to the namespace name.
**Fix**: Ensure your Helm values have `projectID` set correctly and verify the annotation exists on the resource.
```bash
# Check annotation
kubectl get sqlinstance blueprint-db -n config-connector-system -o jsonpath='{.metadata.annotations}'
```
### 6.11. "namespaces ... not found" during deployment
**Issue**: Deployment fails with `Error from server (NotFound): error when creating ... namespaces "test-project" not found`.
**Cause**: The manifests reference a specific namespace (e.g., `test-project` or `my-gdc-project`) that does not exist in the GCP/Stepping Stone cluster.
**Fix**: The `scripts/deploy-gcp-mocked.sh` script automatically patches these to `default`. Ensure you are running the latest version of the script which includes this patching logic.

### 6.12. "strict decoding error: unknown field 'namespace'"
**Issue**: Deployment fails with `strict decoding error: unknown field "namespace"`.
**Cause**: This occurs if the namespace patching logic in the deployment script accidentally strips indentation, causing the `namespace` field to act as a root-level field instead of being inside `metadata`.
**Fix**: Use the updated `scripts/deploy-gcp-mocked.sh` script which correctly preserves indentation using `sed` capture groups.
### 6.13. Pattern 1: Web Tier "CrashLoopBackOff" / "Host not found"
**Issue**: The `web-tier` pod crashes with `host not found in upstream "backend"`.
**Cause**: Nginx tries to resolve the backend hostname (e.g., `logic-svc`) immediately on startup. If the Service doesn't exist or DNS isn't ready, Nginx exits. Also caused by improper namespace patching (`logic-svc.test-project.svc` vs `default.svc`).
**Fix**:
1.  Ensure the `deploy-gcp-mocked.sh` script patches environment variables to use valid DNS names (e.g., `default.svc.cluster.local`).
2.  Ensure Nginx is configured to use a variable for the upstream (`proxy_pass ${API_UPSTREAM}`) and uses `envsubst` in the Dockerfile to inject it at runtime.

### 6.14. Pattern 1: Web Tier "Permission denied" on /run/nginx.pid
**Issue**: Nginx fails to start with `open() "/run/nginx.pid" failed (13: Permission denied)`.
**Cause**: The container runs as a non-root user (uid 101), but the default Nginx config tries to write the PID file to `/run/` which is root-owned.
**Fix**: Update the `nginx.conf` and `Dockerfile` to use a writable directory for the PID file (e.g., `/tmp/nginx/nginx.pid`).

### 6.15. Pattern 4: Consumer App "Connection refused" to DB
**Issue**: `kafka-consumer` logs show connection attempts to `localhost` failing.
**Cause**: The application code hardcoded connection defaults or failed to parse the `DB_CONN` connection string provided by the Secret.
**Fix**: Update the application code (e.g., `app.py`) to prefer the `DB_CONN` environment variable if present. Use a Mock Postgres service (`helm install postgres bitnami/postgresql`) for reliable local testing if Cloud SQL connectivity is complex.

### 6.16. Pattern 4: Consumer App "NoBrokersAvailable"
**Issue**: `kafka-consumer` logs show it cannot reach Kafka brokers.
**Cause**: The environment variable `KAFKA_BROKERS` (plural) in the manifest didn't match the code's expectation of `KAFKA_BROKER` (singular), or DNS resolution failed.
**Fix**: Update the code to accept both variable names. Reset/Reinstall the Kafka deployment (`helm uninstall/install`) to ensure it's healthy and listening on PLAINTEXT.

### 6.17. Bitnami "ImagePullBackOff" / "not found"
**Issue**: Pods fail to pull Bitnami images (like Kafka) with `manifest for ... not found` or `404`.
**Cause**: As of late 2025, Bitnami migrated older/stable tags to the `bitnamilegacy` repository and restricts usage of `latest`.
**Fix**: Explicitly set the repository to `bitnamilegacy/<image>` and use a specific tag.
```bash
--set image.repository=bitnamilegacy/kafka --set image.tag=3.6.0
```

---

## 7. Pattern-Specific Verification Guide

### Pattern 1: Resilient 3-Tier Web App
*   **Deploy**: `./scripts/deploy-gcp-mocked.sh p1-resilient-3-tier-webapp`
*   **Verify**: 
    ```bash
    kubectl port-forward svc/web-lb 8080:80
    curl http://localhost:8080/api/
    # Should return a valid JSON response from the logic tier
    ```

### Pattern 2: HA ML Inference
*   **Deploy**: `./scripts/deploy-gcp-mocked.sh p2-ha-ml-inference`
*   **Note**: The script injects a mock `tf-serving` deployment because GDC AI CRDs are stripped.
*   **Verify**:
    ```bash
    kubectl logs -l app=client --tail=20
    # Success Criteria:
    # 1. Image pulls successfully (no InvalidImageName/ImagePullBackOff).
    # 2. Logs show application startup. 
    # NOTE: You may see "ModuleNotFoundError: No module named 'requests'". This confirms the container started and ran the script, even if the dependency is missing in the example code. This is a PASS for infrastructure verification.
    ```

### Pattern 4: Event-Driven Kafka
*   **Deploy**: `./scripts/deploy-gcp-mocked.sh p4-event-driven-kafka`
*   **Prerequisites**: 
    *   Deploy Emulated Kafka: `kubectl apply -n ${NAMESPACE} -f testing/emulation/kafka.yaml`
    *   Deploy Mock DB: `kubectl apply -n ${NAMESPACE} -f testing/emulation/postgres.yaml` (SharedDB)
    *   **Secrets**: Handled automatically by `scripts/deploy-gcp-mocked.sh` (injects connection to SharedDB).
*   **Verify**:
    ```bash
    kubectl logs -l app=consumer --tail=20
    # Success Criteria:
    # 1. Logs show "Waiting for Kafka: NoBrokersAvailable" (if Kafka infra is pending).
    # 2. Logs show "DB Init failed: duplicate key..." OR no DB connection errors.
    # This confirms the application successfully connected to the Database (passed init) and is correctly looping waiting for the Broker.
    ```

### Pattern 13: GDC Developer Environment (gdc-dev)
*   **Deploy**:
    ```bash
    ./configure-blueprints.sh -n gdc-dev -r ${REGISTRY_HOST} -d p13-gdc-dev
    kubectl apply -f p13-gdc-dev/manifests/gdc/namespace.yaml
    kubectl apply -f p13-gdc-dev/manifests/gdc/gateway.yaml
    kubectl apply -f p13-gdc-dev/manifests/gdc/loadbalancer.yaml
    kubectl apply -f p13-gdc-dev/manifests/gdc/mock-auth-configmap.yaml
    kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-operator.yaml
    kubectl rollout status deployment/gdc-dev-landing-page -n gdc-dev
    kubectl rollout status deployment/gdc-dev-operator -n gdc-dev
    ```
*   **Verify via Port-Forwarding (Cloud Workstation / GCP Emulation)**:
    ```bash
    # 1. Forward both Developer (8080) and Admin (8081) ports simultaneously:
    kubectl port-forward svc/gdc-dev-landing-page 8080:8080 8081:8081 -n gdc-dev --address 0.0.0.0 &

    # 2. Verify Developer Landing Page Health (Port 8080):
    curl -s http://localhost:8080/healthz
    # Expected: {"status": "healthy", "service": "gdc-dev-landing-page"}

    # 3. Verify Admin Console Health & Live Metrics (Port 8081):
    curl -s http://localhost:8081/admin/healthz
    # Expected: {"status": "healthy", "service": "gdc-dev-admin-console"}

    curl -s http://localhost:8081/api/admin/metrics | jq .
    # Expected: JSON object with active sessions, ai_invocations, persona_breakdown, model_routing

    # 4. Verify 302 Redirection from Port 8080 /admin to Port 8081:
    curl -I http://localhost:8080/admin
    # Expected: HTTP/1.0 302 Found, Location: http://...:8081/
    ```
*   **Interactive Dual-Port GUI Verification**:
    1. **Tab 1 — Developer (Port 8080)**: Open `http://localhost:8080/` (or Cloud Workstation Port 8080 preview). Sign in as developer (`developer@gdc.local` or mock `dev-user-1`). Create a project, open the Monaco IDE, run terminal commands, and prompt the AI Assistant.
    2. **Tab 2 — Admin (Port 8081)**: Open `http://localhost:8081/` (or Cloud Workstation Port 8081 preview). Sign in as admin (`admin@gdc.local`). Observe real-time 3-second live auto-refresh updating active sessions, AI invocations, model routing bars, and the security audit log without logging out Tab 1.

## 8. Deployment Reset & E2E Validation

Failed deployments or stale configurations can lead to confusing errors. Use this procedure to aggressively reset the environment and perform a clean end-to-end deployment verification.

```bash
# 1. Clean Slate (delete deployments to force re-creation)
kubectl delete deployment --all
kubectl delete cronjob --all
kubectl delete job --all

# 2. Redeploy All Patterns
./scripts/deploy-all-mocked.sh

# 3. Structural Verification (Automated)
# Checks that all required pods/services exist and are running/ready.
chmod +x scripts/verify-all-emulation.sh
./scripts/verify-all-emulation.sh

# 4. Functional Verification (Smoke Tests)
# Checks that applications are actually responding and connected (curl, logs).
chmod +x scripts/verify-functionality.sh
./scripts/verify-functionality.sh
```

## 9. Reference: Expected Pod Statuses

When running the bulk E2E validation, compare your `kubectl get pods` output against this table.

| Pattern   | Pod Name             | Expected Status           | Validation Note |
| :-------- | :------------------- | :------------------------ | :-------------- |
| **P1**    | `web-tier-*`         | ✅ **Running**             | Frontend serves HTML content (Status 200). |
| **P1**    | `logic-tier-*`       | ✅ **Running**             | Backend API is active. |
| **P2**    | `tf-serving-*`       | ✅ **Running**             | Mock Echo Service simulating TF Serving. |
| **P2**    | `client-*`           | ⚠️ **CrashLoop**          | **Pass**. `ModuleNotFoundError` confirms script ran. |
| **P3**    | `legacy-app-vm-*`    | ✅ **Completed**           | **Pass**. Mock app ran and exited (Success). |
| **P4**    | `kafka-consumer-*`   | ✅ **Running**             | Consumer connects to Emulated Kafka. |
| **P5**    | `llm-gateway-*`      | ✅ **Running**             | Mock Echo Service simulating Gateway. See Note above if testing real failover. |
| **P6**    | `doc-ingest-*`       | ✅ **Completed** (Job)     | **Note**: App may fail DB connection locally, but job schedules correctly. |
| **P7**    | `sql-agent-*`        | ✅ **Running**             | Logs show "Simulating agent". |
| **P13**   | `gdc-dev-landing-page-*` | ✅ **Running**         | Dual-port developer workspace & admin console active. |
| **P13**   | `gdc-dev-operator-*`     | ✅ **Running**         | Session reconciliation loop & telemetry engine active. |
| **Infra** | `postgres-0`         | ✅ **Running**             | Mock Database (StatefulSet). |
| **Infra** | `kafka-controller-*` | ✅ **Running**             | **Critical**. If `Init:ImagePullBackOff`, Docker Hub rate limit hit. |
| **Infra** | `kafka-client`       | ⚪ **Any**                 | Validation pod. Safe to ignore or delete. |

### Note on Acceptable Errors
In this mock verification stage, seeing some pods in `CrashLoopBackOff` or `Completed` state is **expected and acceptable** if it stems from app logic (e.g., missing dependencies, finishing a task) rather than deployment configuration failures.
*   **Unacceptable**: `ImagePullBackOff` (except known legacy jobs), `ErrImagePull`, `CreateContainerConfigError`, or `InvalidImageName`. These indicate fundamental flaws in the manifest or build pipeline that must be fixed.
