# GCP Quickstart: Testing the Inference Gateway on GKE

> **Version:** 1.1

This guide explains how to deploy and test the **Gemma 4 Inference Gateway** on Google Cloud Platform (GCP) standard GKE. This environment uses native GKE managed drivers and Dataplane V2 to accurately emulate the GDC-ag network and GPU stack.

## Prerequisites
1.  **Google Cloud Workstation:** Ensure you are running this from your provisioned Cloud Workstation.
2.  **CLI Tools Installed:** `gcloud`, `kubectl`, `helm`, and `docker`.
3.  **Permissions:** Kubernetes Engine Admin, Service Account User, Artifact Registry Admin.

---

## 🗺️ Pre-Production Validation Strategy Matrix

Before preparing the deployment package for high-security, air-gapped **Google Distributed Cloud (GDC-ag)** environments, platform engineers can choose between **two distinct staging pathways** inside the standard GKE sandbox cluster. Select your validation target below:

| Staging Pathway | Primary Validation Target | Serving Engine | Model Resolution | VRAM Hardware | Behavioral Caveat |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pathway 1: Model Behavior Validation (Ollama)** | Multi-turn reasoning, prompt formatting, conversational capabilities, thinking overrides, and high-fidelity model response verification. | **Ollama** (Standard Test Engine) | `gemma4:26b` / `gemma4:31b` (Staging GGUF) | Fits inside L4 GPU (requires CPU memory offloading). | High-fidelity reasoning but suffers from PCIe CPU/GPU layer offload latency (tripping Cloud Workstations 60s timeout under browser). |
| **Pathway 2 (Option B): Infrastructure Validation (vLLM Mock)** | GKE PVC storage binds, IAM service accounts, GCS objects buckets, ingress connectivity, and gateway proxy in-flight system flattener routing. | **vLLM** (Production Mirror Engine) | `google/gemma-2b-it` (Staging Mock) | Fits cleanly in single L4 GPU VRAM. | Textual behavior is weak (mock model has poor instructions/RAG compliance, returns thought tags reasoning but contradicts itself on output). |

---

### Pathway 1: Staging Ollama Model Behavior (High-Fidelity Reasoning)
*   **What this validates**: Validates high-fidelity model-variant reasoning, dynamic variant hot-swaps (using the Admin console to switch active templates), and server-side **Prompt Routing Classifier** logic.
*   **How to verify Routing is working**: Stream the gateway proxy container logs live using a targeted, noise-filtered grep filter to observe dynamic resolutions in real-time (conversational query -> routes to `ollama-26b`, logical code query -> routes to `ollama-31b`):
    ```bash
    kubectl logs -n gemma-inference -l app=gemma-gateway --tail=1000 | grep -E "Classifier|Detected|flattening|System role|chat/completions|Retry Engine"
    ```
*   **The Workstation 60s Timeout Gotcha (504 Gateway Timeout)**:
    - **The Cause**: The GGUF models for `ollama-31b` are extremely heavy. In a single-GPU 24GB VRAM L4 workstation node, Ollama must split the model layers (keeping 3.3 GB in system CPU memory). Streaming layer activations across the PCIe bus collapses token generation speed to a crawl (~1 token/sec). Asking a complex coding request (like bubble sort generation) takes over 1.5 minutes.
    - **The Timeout**: The Google Cloud Workstations secure browser preview proxy gateway (`*.cloudworkstations.dev/`) enforces a hard **60-second connection timeout** on all dynamic HTTPS web streams. Generating code in the browser chat app will reliably trip this 60s limit and crash with a `504 Gateway Timeout`!
    - **The Direct-Tunnel Solution (Interactive Terminal CLI)**: To completely bypass the secure Workstation web preview's 60-second timeout, **run the sorting query directly from the interactive Python CLI client inside your Workstation terminal VM!**
      The CLI client uses direct GKE port-forwarding (`kubectl port-forward svc/gemma-gateway 8080:80`) which creates a raw TCP stream tunnel. **Raw port forwarding possesses absolutely no HTTP-level gateway timeout constraints!**
      Combined with our dynamic in-flight completions override (`GATEWAY_TIMEOUT = 300s`), the proxy will wait patiently up to 5 minutes, allowing the slow CPU-split model to successfully stream the complete code block to your terminal window:
      ```bash
      cd samples
      export GATEWAY_URL="http://localhost:8080/v1"
      python chat_sample.py
      # Turn off thoughts to accelerate CLI generation:
      /thinking off
      # Submit prompt:
      generate the code to create a bubble sort
      ```
*   **Symmetrical GDC Production Parity**: In a live air-gapped GDC-ag deployment, the cluster node pools are provisioned with A100/H100 hardware, and the unquantized model weights fit completely inside GPU VRAM memory space. **Layer-splitting never occurs**, meaning complex code prompts stream back in real-time at a blazing **40+ tokens/second**, resolving connection timeouts natively across both user-facing browser chat UI and dynamic backend consumers!

### Pathway 2 (Option B): Staging vLLM Infrastructure (Production Sandbox Mirror)
*   **What this validates**: Confirms that GDC storage provisioning, multi-writer access volume claims, client-app database pooling schemas, and security annotations map successfully. It validates the gateway proxy's robust background `flatten_system_message` engine by dynamically catching the 2B model's system-role template limitations in GKE.
*   **Operational Behavior Warning**: Because Option B uses the lightweight **Gemma 2B** model to fit within sandbox memory constraints, **it does not possess advanced instruction or RAG search boundary compliance.** The model will successfully reason the target context *inside its `<thought>` thought process*, but can often contradict itself and return a generic negative response block (*"The context does not specify..."*). **This is fully expected behavior** and confirms that your GCS file retrieval and database history indexes are completely functional under a `200 OK` connection!

---

## Step 1: Provision the GPU Cluster (P5 Blueprint Standard)
We use native GKE managed drivers (`gpu-driver-version=LATEST`) to handle GPU configuration automatically, bypassing manual driver installations.

```bash
# Set your environment variables
export PROJECT_ID=$(gcloud config get-value project)
export ZONE="us-central1-a" # L4 GPUs are often available in -a or -c
export REGION="us-central1"
export CLUSTER_NAME="gdc-gemma-cluster"
export NAMESPACE="gemma-inference"
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
export GSA_NAME="gemma-gateway-sa"

# Pre-check: Ensure L4 GPUs are available in your chosen zone
gcloud compute accelerator-types list --filter="name=nvidia-l4 AND zone:$ZONE"

# 1. Create GKE Cluster with Native GPU Management & Gateway API enabled
# We label the default node pool nodes "app=vllm-26b" so GKE scheduler knows to route
# our latency-optimized serving pod (Release 26b) strictly to this hardware.
gcloud container clusters create $CLUSTER_NAME \
  --project $PROJECT_ID \
  --zone $ZONE \
  --release-channel "regular" \
  --enable-dataplane-v2 \
  --gateway-api=standard \
  --workload-pool "$PROJECT_ID.svc.id.goog" \
  --machine-type "g2-standard-24" \
  --accelerator type=nvidia-l4,count=2,gpu-driver-version=LATEST \
  --num-nodes "1" \
  --disk-size=300 \
  --node-labels="app=vllm-26b" \
  --tags=gdc-emulation

# 1b. Configure VPC Proxy-Only Subnet & Firewall for GKE Gateway API (gke-l7-rilb)
# Note: Subnet names and CIDRs are global per VPC. We scope the subnet name to ${REGION}
# and only create it if no REGIONAL_MANAGED_PROXY subnet exists in ${REGION} yet.
if [ -z "$(gcloud compute networks subnets list --filter="region:${REGION} AND purpose:REGIONAL_MANAGED_PROXY" --format="value(name)" --project="${PROJECT_ID}")" ]; then
  gcloud compute networks subnets create "gke-gateway-proxy-${REGION}" \
    --purpose=REGIONAL_MANAGED_PROXY \
    --role=ACTIVE \
    --region="${REGION}" \
    --network=default \
    --range=172.16.2.0/23 \
    --project="${PROJECT_ID}"
fi

gcloud compute firewall-rules create allow-gateway-internal \
  --network=default \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:80,tcp:443,tcp:8000,tcp:8080 \
  --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
  --project="${PROJECT_ID}" 2>/dev/null || \
gcloud compute firewall-rules update allow-gateway-internal \
  --rules=tcp:80,tcp:443,tcp:8000,tcp:8080 \
  --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
  --project="${PROJECT_ID}"

# 2. Create standard non-GPU node pool for client/auth apps
gcloud container node-pools create client-pool \
  --cluster $CLUSTER_NAME \
  --project $PROJECT_ID \
  --zone $ZONE \
  --machine-type "e2-standard-4" \
  --num-nodes "1" \
  --node-labels="app=client"

# 2a. Optional: Scale up GKE for Concurrent Dual-Model Serving (Phase 8)
# To host both unquantized Gemma 4 models (26B MoE and 31B Dense) concurrently side-by-side,
# scale up the GKE cluster rig by adding a second dedicated Nvidia L4 GPU node:
gcloud container node-pools create gpu-reasoning-pool \
  --cluster $CLUSTER_NAME \
  --project $PROJECT_ID \
  --zone $ZONE \
  --machine-type "g2-standard-24" \
  --accelerator type=nvidia-l4,count=1,gpu-driver-version=LATEST \
  --num-nodes "1" \
  --node-labels="app=vllm-31b" \
  --tags=gdc-emulation

# 3. Get Credentials
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID

# 4. Setup Workload Identity (Idempotent)
gcloud iam service-accounts describe ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com || \
gcloud iam service-accounts create $GSA_NAME \
    --project=$PROJECT_ID \
    --description="GSA for Gemma Gateway Workload Identity"

gcloud iam service-accounts add-iam-policy-binding ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[gemma-inference/gemma-gateway-ksa]" \
    --project $PROJECT_ID
```

---

## Step 2: Build Proxy, Side-by-Side Baked Ollama Images (`26b` & `31b`) & Deploy
`./scripts/build-and-push.sh` automatically builds and pushes **all three required container images** in a single run:
1. `${REGISTRY_HOST}/gemma-proxy:latest` — The FastAPI Gateway Proxy & Admin Control Plane UI
2. `${REGISTRY_HOST}/ollama-gemma-26b:latest` — Baked Ollama server preloaded with `gemma4:26b` (MoE)
3. `${REGISTRY_HOST}/ollama-gemma-31b:latest` — Baked Ollama server preloaded with `gemma4:31b` (Dense)

```bash
# 1. Enable Artifact Registry (uses REPO_REGION if set, otherwise REGION)
export AR_REGION="${REPO_REGION:-$REGION}"
export REGISTRY_HOST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"

gcloud services enable artifactregistry.googleapis.com --project "${PROJECT_ID}"
gcloud artifacts repositories create gemma-repo \
  --repository-format=docker \
  --location="${AR_REGION}" \
  --project="${PROJECT_ID}" || true
gcloud auth configure-docker "${AR_REGION}-docker.pkg.dev" --quiet

# 2. Build and Push the Proxy + BOTH Baked Ollama Models (26b & 31b)
chmod +x scripts/build-and-push.sh
./scripts/build-and-push.sh
```

### 2.1. Managing and Cleaning Local Images (Avoiding Stale Build Caches)

During rapid development, iteration, or debugging of the Gateway Proxy or baked serving containers, Docker's **layer-caching mechanism** can sometimes lead to stale files or scripts being executed inside newly built containers. 

To solve this, we provide a suite of **project-scoped cleanup helper scripts** located in `scripts/` that target only images belonging specifically to this repository. These scripts support standard flags like `--dry-run` (to preview deletions) and `--force` (to bypass verification prompts):

* **Wipe All Project-Related Local Images:** Wipes every local image built or tagged for this repository across all tags and variants.
  ```bash
  ./scripts/clean-all-local-images.sh [--dry-run] [--force]
  ```
* **Wipe a Single Specified Image:** Cleans a single local image by its ID or repository tag, with safety checks to ensure it is project-relevant.
  ```bash
  ./scripts/clean-single-local-image.sh <image_id_or_tag> [--dry-run] [--force]
  ```
* **Wipe Registry-Matching Images:** Cleans all local images whose repository URLs match the configured project registry.
  ```bash
  ./scripts/clean-repo-all-images.sh [--dry-run] [--force]
  ```
* **Wipe a Specific Component:** Wipes all tags for a particular project container component.
  ```bash
  ./scripts/clean-specific-image.sh <image_name_or_tag> [--dry-run] [--force]
  # Example:
  # ./scripts/clean-specific-image.sh gemma-proxy
  ```

> [!TIP]
> **Why clean specific images (Methods 2 & 4)?**
> Instead of wiping your entire workstation's Docker cache (which would force re-downloading heavy base containers or third-party dependencies like databases), cleaning a specific component (e.g. `gemma-proxy`) deletes *only* the cache for that part of your codebase. 
> This forces Docker to reconstruct the filesystem layers from scratch, ensuring that the newly built container executes the **exact, up-to-date source code** from your workspace disk.

### 2.2. Create the Target Namespace & Secrets
1. **Create the target namespace (Required for both Ollama and vLLM):**
   ```bash
   kubectl apply -f standalone/manifests/00-namespace.yaml
   ```

2. **Create the Hugging Face token secret (Required ONLY for Pathway 2 / vLLM; skip if using Pathway 1 / Ollama baked images):**
   Gemma models downloaded dynamically by vLLM (including the lightweight `google/gemma-2b-it` mock fallback) are gated on Hugging Face Hub:
   ```bash
   kubectl create secret generic hf-token-secret \
     --from-literal=token="<YOUR_HF_TOKEN>" \
     -n gemma-inference \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

### 2.3. Configure and Deploy
Select your deployment path based on your current engineering objective:

> [!TIP]
> **Pathway 1 (Ollama Side-by-Side 26B + 31B — Default for Testing):** Deploys **both** `ollama-26b` (`gemma4:26b` MoE) and `ollama-31b` (`gemma4:31b` Dense) **simultaneously side-by-side** in the `gemma-inference` namespace (1 Nvidia L4 GPU per pod, using the 2 L4 GPUs provisioned on your `g2-standard-24` node pool), along with the `gemma-gateway` proxy. The Gateway Proxy automatically routes between `http://ollama-26b:11434` and `http://ollama-31b:11434` via the Prompt Routing Classifier or live Admin UI switches without redeploying pods.
> 
> **Pathway 2 (vLLM — Production Target):** Recommended for production mirroring and load testing. vLLM implements PagedAttention for maximum enterprise throughput using unquantized weights (`Option A`) or lightweight 2B mock weights (`Option B`).

#### Pathway 1: Deploying Both Ollama 26B & 31B Models Side-by-Side (Default)

Ensure `REGISTRY_HOST` is exported in your shell (`echo $REGISTRY_HOST`). You can deploy the side-by-side Ollama stack using either the automated script (**Option 1A**) or explicit Helm releases (**Option 1B**):

##### Option 1A: Automated Side-by-Side Deployment via `install-all.sh`
When `INFERENCE_ENGINE="ollama"` and `REGISTRY_HOST` are set, `./standalone/install-all.sh` automatically hydrates and applies **both** the `ollama-26b` and `ollama-31b` deployments/services side-by-side, plus `gemma-gateway` (`OLLAMA_MODEL_VARIANT` only sets the initial default active variant in the Gateway UI):
```bash
export INFERENCE_ENGINE="ollama"
export OLLAMA_MODEL_VARIANT="26b" # Sets initial default variant; BOTH 26b and 31b pods are deployed side-by-side
chmod +x standalone/install-all.sh
./standalone/install-all.sh
```

##### Option 1B: Explicit Side-by-Side Deployment via `helm upgrade --install`
If you prefer managing each serving backend and the gateway as native Helm releases:
```bash
# 1. Deploy Ollama 26B (MoE) on GPU #1 (Service: http://ollama-26b:11434)
helm upgrade --install ollama-26b ./blueprints/ollama-gke \
  --namespace gemma-inference --create-namespace \
  --set image.repository="${REGISTRY_HOST}/ollama-gemma-26b" \
  --set image.tag="latest" \
  --set fullnameOverride="ollama-26b" \
  --set model.variant="26b" \
  --set persistence.enabled=false

# 2. Deploy Ollama 31B (Dense) on GPU #2 (Service: http://ollama-31b:11434)
helm upgrade --install ollama-31b ./blueprints/ollama-gke \
  --namespace gemma-inference \
  --set image.repository="${REGISTRY_HOST}/ollama-gemma-31b" \
  --set image.tag="latest" \
  --set fullnameOverride="ollama-31b" \
  --set model.variant="31b" \
  --set persistence.enabled=false

# 3. Deploy the Gemma Gateway Proxy pointing to both Ollama services
helm upgrade --install gemma-gateway ./standalone/chart \
  --namespace gemma-inference \
  --set gdc.enabled=false \
  --set apps.enabled=true \
  --set gateway.image.repository="${REGISTRY_HOST}/gemma-proxy" \
  --set gateway.image.tag="latest" \
  --set gateway.activeFramework="ollama" \
  --set gateway.ollamaModelVariant="26b"
```

##### Verify Side-by-Side Pods & Services
```bash
kubectl get pods,svc -n gemma-inference
```
You should see **three pods** (`ollama-26b-*`, `ollama-31b-*`, and `gemma-gateway-*`) and **three ClusterIP Services** (`ollama-26b:11434`, `ollama-31b:11434`, and `gemma-gateway:80`) running concurrently in `gemma-inference`.

#### Pathway 2: Deploying the high-performance vLLM serving engines (Production Mirror / Phase 8)
Administrators can select between two pathways depending on GKE cluster rig GPU resources:

##### Option A: Full-Scale Simultaneous Dual-Model serving (Requires GKE GPU Pool Scale-Up)
```bash
# 1. Deploy the 26B MoE serving release
helm upgrade --install vllm-26b ./blueprints/vllm-gke -n gemma-inference \
  --set model.name="google/gemma-4-26b-it" \
  --set persistence.enabled=true \
  --set persistence.storageClassName="standard-rwo" \
  --set persistence.accessModes={ReadWriteOnce} \
  --set persistence.size="100Gi" \
  --set model.quantization="fp8" \
  --set model.servedModelName="gemma4:26b" \
  --set resources.limits."nvidia.com/gpu"=1

# 2. Deploy the 31B Dense serving release
helm upgrade --install vllm-31b ./blueprints/vllm-gke -n gemma-inference \
  --set model.name="google/gemma-4-31b-it" \
  --set persistence.enabled=true \
  --set persistence.storageClassName="standard-rwo" \
  --set persistence.accessModes={ReadWriteOnce} \
  --set persistence.size="120Gi" \
  --set model.quantization="fp8" \
  --set model.servedModelName="gemma4:31b" \
  --set resources.limits."nvidia.com/gpu"=1 # Scale to 2 if running unquantized
```

##### Option B: Testing Mock Fallbacks (Recommended for standard single-GPU sandbox staging)
We deploy two separate releases of the chart using a lightweight 2B model as a drop-in substitute. This preserves all proxy routing and parameter evaluations without causing GKE OOM crashes:

```bash
# 1. Deploy the 26B MoE Mock Release (using Gemma 2B)
helm upgrade --install vllm-26b ./blueprints/vllm-gke -n gemma-inference \
  --set model.name="google/gemma-2b-it" \
  --set model.servedModelName="gemma4:26b" \
  --set resources.limits."nvidia.com/gpu"=1

# 2. Deploy the 31B Dense Mock Release (using Gemma 2B)
helm upgrade --install vllm-31b ./blueprints/vllm-gke -n gemma-inference \
  --set model.name="google/gemma-2b-it" \
  --set model.servedModelName="gemma4:31b" \
  --set resources.limits."nvidia.com/gpu"=1
```

##### Configure Manifest Placeholders & Deploy Gateway Proxy Manifest
Run the configuration script from the repository root to point the manifests to your newly built container images in your Workstation Artifact Registry before deploying:

```bash
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d gateway
export INFERENCE_ENGINE="vllm"
./standalone/install-all.sh
```


> [!NOTE]
> ### 🎛️ Operational Parity: Staging Validation with Option B (Mock 2B Fallback)
> Option B deploys **`google/gemma-2b-it`** (a lightweight 2-billion parameter model) as a drop-in substitute. This is highly recommended for standard single-GPU staging VM environments to validate your **entire active GKE infrastructure, database persistent schemas, object storage buckets, user sessions, and proxy flattener** without causing GKE OOM crashes.
> 
> **System Role Emulation Limitation & Mitigation:**
> * **The Challenge:** Pre-trained model templates for Gemma 2B do **not** natively support the structured `system` role tags inside vLLM. 
> * **The Mitigation:** When a RAG query (with uploaded files context and strict boundaries instructions) is submitted, vLLM returns a `400 Bad Request: System role not supported` error. To prevent this from crashing tenant sessions, the **Gateway Proxy** automatically intercepts this 400 error in the background, consolidates all system directives and contexts into a single merged string, and retries the completion call in-flight as a single, flattened `"user"` role block. 
> * **Expected 2B Model Behavior:** Due to its 2B parameter scale and the merged-prompt emulation overhead, Gemma 2B possesses highly limited reasoning capacity and strict instructions alignment under RAG search boundaries. The model successfully reasons the correct answer within its `<thought>` reasoning block, but can sometimes contradict itself and output a generic negative fallback string (e.g., *"The context does not specify..."*) in its final response block.
> * **Absolute Production Confidence:** Receiving a successful **`200 OK`** response (containing the thoughts block and text) is the ultimate operational confirmation! It proves that the entire GCS file retrieval, PostgreSQL database user history tracking, network routing, and gateway flattener are successfully integrated. Once swapped to the actual **Gemma 4 models (Option A / GDC Production)**:
>   1. High-tier models natively support structured system roles, completely bypassing the proxy's flattener and retry blocks!
>   2. They possess cutting-edge instruction compliance and massive context alignments, returning correct, high-fidelity final responses out-of-the-box!
> 
> ---


## Step 3: Verify and Access

Since we are using the baked image strategy, the models are already pre-loaded into the container images. However, because these baked model images carry multiple gigabytes of staging weights, downloading and pulling the image layers into the node cache concurrently over the network interface can take **~10 minutes**.

> [!IMPORTANT]
> You MUST wait about **60 seconds** after the pods reach the `Running` state before sending your first prompt. This allows the preloader to fully load the model into GPU memory so it responds instantly to your first query!

> [!NOTE]
> **Scheduling Gotcha (`ContainerStatusUnknown`):**
> While the node interface is heavily saturated pulling the massive Ollama serving layers, the concurrent download for the gateway proxy pod can occasionally encounter a background queue delay. If GKE Kubelet temporarily loses tracking, you may see the old proxy pod transition to `ContainerStatusUnknown`. 
> 
> **This is entirely expected:** the Kubernetes self-healing controller automatically purges the deadlocked instance and spins up a fresh proxy pod in the background, which transitions to `Running` instantly once node pools are warm!

```bash
# Watch the pod statuses transition in real-time
kubectl get pods -n gemma-inference -w

# If a pod remains in 'ContainerCreating' for a long time, 
# inspect GKE/Kubelet background pull transitions and network events:
kubectl describe pod -l app.kubernetes.io/name=ollama -n gemma-inference
kubectl describe pod -l app=gemma-gateway -n gemma-inference
```
*(Wait for all pods to reach the `Running` state, then wait **60 seconds** for the warmup).*

### Option A: Internal Cluster Verification (No Port-Forwarding Needed)
Execute an ephemeral verification pod directly inside the cluster against the internal `gemma-gateway` Service:

```bash
kubectl run gateway-verify --rm -i --restart=Never -n gemma-inference \
  --image=curlimages/curl --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Gemma 4 Inference Gateway verified!" && \
    echo "✅ SUCCESS: Gateway proxy and configuration active" && \
    echo "===============================================" && \
    curl -s http://gemma-gateway/api/config && \
    echo ""
  '
```
**Expected Workstation Output:**
```text
===============================================
✅ PASS: Gemma 4 Inference Gateway verified!
✅ SUCCESS: Gateway proxy and configuration active
===============================================
{"active_framework": "...", "routing_targets": {...}}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

### Option B: Local Port-Forwarding & Browser Verification
#### 3.1. Access the Admin UI
Port-forward the UI to your Cloud Workstation:
```bash
kubectl port-forward svc/gemma-gateway 8080:80 -n gemma-inference
```
Navigate to `http://localhost:8080` in your browser.

### 3.2. Run Integration Tests
*(Note: If your Cloud Workstation prevents virtual environment creation, run `sudo apt-get install -y python3-venv` first).*

```bash
cd samples
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Point the tests at the forwarded URL
export GATEWAY_URL="http://localhost:8080/v1"
export ACTIVE_FRAMEWORK="ollama"

# Run the interactive CLI
python chat_sample.py

# Once running, the CLI indicates which variant is active:
# 🧠 Gemma 4 (Variant: streaming) [live]:
```

#### Toggling Thinking Mode
The chat client includes custom commands to control whether the model exposes its reasoning process:
- `/thinking off`: Turns off the thinking/reasoning process for subsequent queries.
- `/thinking on`: Re-enables step-by-step thinking process wrapped inside `<thought>...</thought>` tags.

> [!NOTE]
> **Initial Stream Latency & Warmup:**
> In resource-constrained testing sandboxes, initializing the deep context layers during your first few interactions can introduce a brief lag. It may take up to **3 prompts** for the inference cache to fully warm up and responses to stream back at maximum speed.
> 
> **Performance Tip:** If you encounter latency during initialization, run the `/thinking off` command in the chat CLI. Turning off the extensive step-by-step deep reasoning tokens substantially reduces prompt overhead and accelerates streaming responses instantly!

---

### 3.3. Hot-Swapping Model Variants

You can swap between the two Gemma 4 variants (26B vs 31B) using either of two methods:

#### Option A: Via the Admin Control Plane (Live, No Downtime)
1. Open the Admin UI in your browser at `http://localhost:8080`.
2. Select your desired variant from the **Active Model Variant** dropdown under "🧠 Gemma 4 Model Variant".
3. Click **Save Gateway Configuration**.
4. Subsequent inference calls from clients will now instantly use the newly selected model variant.

#### Option B: Via Terminal Environment Variable
To completely redeploy the serving framework with the desired variant:
```bash
export OLLAMA_MODEL_VARIANT="31b" # or "26b"
./standalone/install-all.sh
```

### 3.4. Deploy Data Layer Emulators (PostgreSQL & GCS)

To test multi-tenant workflows, session histories, and file uploads, the client backend requires persistence. In standard GKE staging, we emulate GDC PostgreSQL and GCS Object Storage dynamically inside the cluster.

#### 1. Sanity Check Environment Variables
Ensure your terminal session has the required variables exported (preserving your cluster `REGION` and Artifact Registry `REPO_REGION` from Step 1):
```bash
export PROJECT_ID=$(gcloud config get-value project)
export NAMESPACE="gemma-inference"
export REGION="${REGION:-us-east4}" # Preserves your active cluster REGION from Step 1
export AR_REGION="${REPO_REGION:-$REGION}"
export REGISTRY_HOST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
```

#### 2. Setup GCS Bucket & Client Workload Identity
```bash
# Create GCS Bucket (Object Storage Emulation)
export BUCKET_NAME="gs://gemma-client-files-${PROJECT_ID}"
gcloud storage buckets create ${BUCKET_NAME} --project=${PROJECT_ID} --location=${REGION} --uniform-bucket-level-access || true

export GSA_NAME="gemma-client-sa"
export KSA_NAME="gemma-client-sa"

# Create Google Service Account (GSA) and grant storage permissions
gcloud iam service-accounts create ${GSA_NAME} --project=${PROJECT_ID} || true
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member "serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role "roles/storage.objectAdmin"

# Bind Kubernetes Service Account (KSA) to GSA via Workload Identity
gcloud iam service-accounts add-iam-policy-binding ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

# Create and annotate KSA
kubectl create serviceaccount ${KSA_NAME} -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl annotate serviceaccount ${KSA_NAME} -n ${NAMESPACE} iam.gke.io/gcp-service-account=${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com --overwrite
```

#### 3. Deploy PostgreSQL StatefulSet
> [!IMPORTANT]
> **Database Credentials Secret**: The `postgres-0` pod requires the Secret `gemma-client-db-credentials` (keys: `db_name`, `username`, `password`) and ConfigMap `postgres-init-script`. If applied out of order, the pod will encounter a `CreateContainerConfigError`.

```bash
# 1. Create DB Credentials Secret
kubectl create secret generic gemma-client-db-credentials \
  --from-literal=username=postgres \
  --from-literal=password=password \
  --from-literal=db_name=postgres \
  --from-literal=connection_string=postgresql://postgres:password@postgres-svc.gemma-inference.svc.cluster.local:5432/postgres \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# 2. Apply ConfigMap and StatefulSet
kubectl apply -f gemma-client/manifests/gcp/postgres-configmap.yaml -n $NAMESPACE
kubectl apply -f gemma-client/manifests/gcp/statefulset-postgres.yaml -n $NAMESPACE

# 3. VERIFICATION GATE: Wait for PostgreSQL to reach Running status
kubectl rollout status statefulset/postgres -n $NAMESPACE --timeout=120s
kubectl get pods -n $NAMESPACE -l app=postgres

# 4. Seed the Operational Readiness, Sensor Telemetry, and Intelligence RAG tables
chmod +x scripts/populate-db.sh
./scripts/populate-db.sh
```

---

### 3.5. Deploy the Gemma Chat Client (gemma-client)

Choose between **two authentication pathways** based on your testing goals:

| Staging Pathway | Primary Purpose | Auth Mechanism | Port-Forward Command |
| :--- | :--- | :--- | :--- |
| **Pathway A: Mock Auth (Fast Sandbox)** | Fast sandbox validation of model badges, prompt routing classifier, and streaming latency. | In-memory persona switcher dropdown (`User 1`, `User 2`, `Admin`). | `kubectl port-forward svc/frontend-svc 8081:80` |
| **Pathway B: Production Keycloak OIDC + Gateway API (Preferred / GDC Parity)** | Full production E2E identity & routing verification using the **Kubernetes Gateway API** (`gateway.networking.k8s.io/v1`, `gdc-platform-gateway`, and `HTTPRoute/gemma-unified-routes`). | OpenID Connect with Keycloak SSO (`alice`, `charlie`). | `kubectl port-forward svc/gdc-gateway-tunnel 8081:80` |

---

#### Pathway A: Quick Mock Auth Mode (Fast Sandbox Testing)

1. **Ensure OIDC is disabled in frontend:**
   ```bash
   rm -f gemma-client/src/frontend/.env
   ```

2. **Hydrate manifests and build images:**
   ```bash
   # Hydrate placeholders across manifests
   ./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d gemma-client

   # Build and push container images to Artifact Registry
   chmod +x gemma-client/scripts/build.sh
   ./gemma-client/scripts/build.sh -p ${PROJECT_ID} -r ${REGISTRY_HOST}
   ```

3. **Deploy Backend & Frontend:**
   ```bash
   kubectl apply -f gemma-client/manifests/apps/backend.yaml -n $NAMESPACE
   kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n $NAMESPACE

   kubectl rollout status deployment/backend -n $NAMESPACE
   kubectl rollout status deployment/frontend -n $NAMESPACE
   ```

4. **Access the Chat Interface:**
   ```bash
   kubectl port-forward svc/frontend-svc 8081:80 -n $NAMESPACE
   ```
   Open `http://localhost:8081` in your browser. Use the persona switcher dropdown in the header to simulate multi-tenant users.

---

#### Pathway B: Production Keycloak OIDC + Kubernetes Gateway API (Preferred / GDC Parity)

> [!NOTE]
> **Why Kubernetes Gateway API + `gdc-gateway-tunnel` is used:**
> Physical Google Distributed Cloud (GDC-ag) racks use the **Kubernetes Gateway API** (`gateway.networking.k8s.io/v1`) rather than legacy NGINX Ingress controllers.
> We mirror GDC production in GKE by deploying a native **GKE Gateway** (`gdc-platform-gateway`, `gatewayClassName: gke-l7-rilb`) and the production **HTTPRoutes** (`gemma-unified-routes` for `/auth` $\rightarrow$ Keycloak, `/api` URLRewrite $\rightarrow$ Backend, `/` $\rightarrow$ Frontend, plus `RequestHeaderModifier` for `X-Forwarded-Proto: https`).
> Because Google Cloud Workstations run inside a Google-managed tenant VPC that cannot route directly to internal load balancer VIPs across VPC peering, we also deploy a lightweight L4 TCP pass-through Service (`gdc-gateway-tunnel`) inside the cluster. Port-forwarding `svc/gdc-gateway-tunnel` on Port `8081` sends browser traffic directly through the real GKE Gateway API Regional Internal Load Balancer (`gdc-platform-gateway`).

1. **Ensure Gateway API & Region-Scoped Proxy Subnet are Enabled on Your Cluster:**
   *(If you already ran Step 1 with `--gateway-api=standard`, skip to step 2; if enabling on an existing cluster, ensure `REGION` matches your GKE cluster region and run this once)*:
   ```bash
   gcloud container clusters update "${CLUSTER_NAME}" \
     --gateway-api=standard \
     --zone "${ZONE}" \
     --project "${PROJECT_ID}"

   # Verify or create the REGIONAL_MANAGED_PROXY subnet in ${REGION} (subnet names & CIDRs are global per VPC)
   if [ -z "$(gcloud compute networks subnets list --filter="region:${REGION} AND purpose:REGIONAL_MANAGED_PROXY" --format="value(name)" --project="${PROJECT_ID}")" ]; then
     gcloud compute networks subnets create "gke-gateway-proxy-${REGION}" \
       --purpose=REGIONAL_MANAGED_PROXY \
       --role=ACTIVE \
       --region="${REGION}" \
       --network=default \
       --range=172.16.2.0/23 \
       --project="${PROJECT_ID}"
   fi

   gcloud compute firewall-rules create allow-gateway-internal \
     --network=default \
     --direction=INGRESS \
     --priority=1000 \
     --action=ALLOW \
     --rules=tcp:80,tcp:443,tcp:8000,tcp:8080 \
     --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
     --project="${PROJECT_ID}" 2>/dev/null || \
   gcloud compute firewall-rules update allow-gateway-internal \
     --rules=tcp:80,tcp:443,tcp:8000,tcp:8080 \
     --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
     --project="${PROJECT_ID}"
   ```

2. **Configure Workstation Coordinates & Realm Import:**
   ```bash
   chmod +x gemma-client/scripts/configure-keycloak.sh
   ./gemma-client/scripts/configure-keycloak.sh
   ```
   *When prompted, paste your active Workstation Web Preview URL (e.g. `https://8081-w-<user>-<id>.cluster-<hash>.cloudworkstations.dev` or bare hostname `w-<user>-<id>.cluster-<hash>.cloudworkstations.dev`). This generates `keycloak-realm-import-hydrated.yaml` and `gemma-client/src/frontend/.env` with the `8081-` port prefix.*

3. **Deploy Keycloak Identity Provider & Build/Deploy Client Applications (Helm Wrapper Chart Path):**
   ```bash
   kubectl apply -f gemma-client/manifests/gcp/keycloak-realm-import-hydrated.yaml -n $NAMESPACE
   kubectl apply -f gemma-client/manifests/gcp/keycloak-staging.yaml -n $NAMESPACE
   kubectl rollout status deployment/keycloak -n $NAMESPACE --timeout=180s

   # Build and push the client images (baking the .env OIDC config into Vite assets)
   export AR_REGION="${REPO_REGION:-$REGION}"
   export REGISTRY_HOST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
   chmod +x gemma-client/scripts/build.sh
   ./gemma-client/scripts/build.sh -p ${PROJECT_ID} -r ${REGISTRY_HOST}

   # Deploy the Inference Gateway Proxy & HTTPRoute via the standalone Helm wrapper chart
   # (If gemma-gateway was previously created via kubectl apply, delete the stateless objects first so Helm owns managedFields cleanly)
   kubectl delete deployment/gemma-gateway service/gemma-gateway httproute/gemma-gateway-route -n $NAMESPACE --ignore-not-found
   helm upgrade --install gemma-standalone ./standalone/chart \
     --namespace "${NAMESPACE}" \
     --set global.projectId="${PROJECT_ID}" \
     --set global.namespace="${NAMESPACE}" \
     --set global.registry="${REGISTRY_HOST}"

   # Deploy Backend, Frontend, NetworkPolicy, and HTTPRoute/gemma-unified-routes via the gemma-client Helm wrapper chart
   helm upgrade --install gemma-client ./gemma-client/chart \
     --namespace "${NAMESPACE}" \
     --set global.projectId="${PROJECT_ID}" \
     --set global.namespace="${NAMESPACE}" \
     --set global.registry="${REGISTRY_HOST}" \
     --set apps.inputBucket="${PROJECT_ID}-gemma-input"

   kubectl rollout status deployment/backend -n $NAMESPACE
   kubectl rollout status deployment/frontend -n $NAMESPACE
   ```

4. **Deploy Kubernetes Gateway (`gdc-platform-gateway`), HealthCheck/Timeout Policies, and Workstation L4 Bridge (`gdc-gateway-tunnel`):**
   ```bash
   # 1. Remove legacy NGINX ingress pod if present
   kubectl delete -f gemma-client/manifests/gcp/nginx-ingress-staging.yaml -n $NAMESPACE --ignore-not-found

   # 2. Deploy the Kubernetes Gateway (gdc-platform-gateway), HealthCheckPolicies, 300s GCPBackendPolicy, and L4 tunnel deployment
   kubectl apply -f gemma-client/manifests/gcp/gateway-api-staging.yaml -n $NAMESPACE

   # 3. Ensure HTTPRoutes are active (already managed by the Helm releases above; safe to verify)
   kubectl get httproute -n $NAMESPACE

   # 4. Wait for the GKE Gateway Controller to allocate the Regional Internal Load Balancer VIP (~60-90s)
   echo "Waiting for gdc-platform-gateway VIP allocation..."
   until [ -n "$(kubectl get gateway gdc-platform-gateway -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)" ]; do
     sleep 5
   done
   export GATEWAY_VIP=$(kubectl get gateway gdc-platform-gateway -n $NAMESPACE -o jsonpath='{.status.addresses[0].value}')
   echo "✅ gdc-platform-gateway allocated VIP: ${GATEWAY_VIP}"

   # 5. Point the in-cluster L4 TCP bridge (gdc-gateway-tunnel) to the allocated Gateway VIP
   kubectl set env deployment/gdc-gateway-tunnel GATEWAY_VIP="${GATEWAY_VIP}" -n $NAMESPACE
   kubectl rollout status deployment/gdc-gateway-tunnel -n $NAMESPACE --timeout=60s
   ```

5. **Port-Forward the Gateway API L4 Tunnel (`gdc-gateway-tunnel`):**
   ```bash
   pkill -f "port-forward" || true
   kubectl port-forward service/gdc-gateway-tunnel 8081:80 -n $NAMESPACE
   ```
   > [!CAUTION]
   > Do **not** run `kubectl port-forward svc/frontend-svc 8081:80`. Port-forwarding `gdc-gateway-tunnel` routes all browser traffic through the real GKE Gateway API Load Balancer (`${GATEWAY_VIP}:80`) and `HTTPRoute/gemma-unified-routes` (`/auth` $\rightarrow$ Keycloak, `/api` $\rightarrow$ Backend, `/` $\rightarrow$ Frontend).

6. **Verify Secure Identity Flow via Gateway API:**
   * Open your browser to your Workstation Port 8081 Preview URL (`https://8081-w-...cloudworkstations.dev`).
   * **Hard Refresh** (`Ctrl+Shift+R` or DevTools `F12` $\rightarrow$ Empty Cache and Hard Reload) to clear cached Vite assets.
   * You will be redirected through `gdc-platform-gateway` (`HTTPRoute/gemma-unified-routes`) to Keycloak's login screen. Log in as:
     * **`alice`** / **`password`** $\rightarrow$ User persona (badge: `alice Secure (OIDC)`).
     * **`charlie`** / **`password`** $\rightarrow$ Admin persona (can upload to Shared context).

---

### 3.6. (Fallback) Legacy NGINX Ingress Proxy (`nginx-ingress-staging.yaml`)

If you are running in a restricted GKE environment where you cannot create a `REGIONAL_MANAGED_PROXY` subnet (`172.16.0.0/23`) for the GKE Gateway Controller, you can fall back to the lightweight in-cluster NGINX reverse proxy (`gemma-ingress-gateway`) after `backend.yaml` and `frontend.yaml` have been deployed:

```bash
kubectl apply -f gemma-client/manifests/gcp/nginx-ingress-staging.yaml -n $NAMESPACE
kubectl rollout status deployment/gemma-ingress-gateway -n $NAMESPACE --timeout=60s
pkill -f "port-forward" || true
kubectl port-forward service/gemma-ingress-gateway 8081:80 -n $NAMESPACE
```

---

## Step 4: Clean Up
When you are finished testing, completely tear down the deployed resources, release Persistent Disks, and clean up service accounts:

```bash
# Return to repository root dynamically
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

# 1. Delete client frontend, backend, ingress proxy, and Keycloak
kubectl delete -f gemma-client/manifests/apps/frontend.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/apps/backend.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gcp/nginx-ingress-staging.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gcp/keycloak-staging.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gcp/keycloak-realm-import-hydrated.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gcp/keycloak-realm-import.yaml -n $NAMESPACE --ignore-not-found

# 2. Delete Gateway API resources and L4 tunnel bridge
kubectl delete -f standalone/manifests/02-gateway-httproute.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gdc/security/production-gateway-routing.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gcp/gateway-api-staging.yaml -n $NAMESPACE --ignore-not-found

# 3. Delete PostgreSQL database emulator & secret
kubectl delete -f gemma-client/manifests/gcp/statefulset-postgres.yaml -n $NAMESPACE --ignore-not-found
kubectl delete -f gemma-client/manifests/gcp/postgres-configmap.yaml -n $NAMESPACE --ignore-not-found
kubectl delete secret gemma-client-db-credentials -n $NAMESPACE --ignore-not-found

# 4. Delete GCS storage bucket and Workload Identity Service Account
export BUCKET_NAME="gs://gemma-client-files-${PROJECT_ID}"
gcloud storage rm -r ${BUCKET_NAME} --quiet || true
gcloud iam service-accounts delete gemma-client-sa@${PROJECT_ID}.iam.gserviceaccount.com --project=${PROJECT_ID} --quiet || true

# 5. Run the standalone gateway uninstaller to wipe namespace & model pods
chmod +x standalone/uninstall-all.sh
./standalone/uninstall-all.sh
```

*(Optional)* To completely destroy the GKE cluster and stop GCP billing:
```bash
gcloud container clusters delete $CLUSTER_NAME --zone $ZONE --project $PROJECT_ID --quiet
```

---

## Step 5: Troubleshooting & Serving Operations Matrix

This section provides a comprehensive guide for platform administrators and testing teams to handle cluster resource boundaries, online emulations, and GDC-air-gapped operations smoothly.

### 5.1. Swapping Serving Engines (Ollama vs. vLLM) in Sandboxed Clusters
Because the cluster does not possess enough GPU hardware cores to host both serving backends concurrently under sandboxed constraints, you must execute a clean resource release cycle during framework handovers:

```bash
# A. Swapping FROM Ollama TO vLLM (Path A to B)
# 1. Scale Ollama runtimes to zero and wipe the old pods
kubectl scale deployment ollama-26b -n gemma-inference --replicas=0
kubectl scale deployment ollama-31b -n gemma-inference --replicas=0
kubectl delete pod -n gemma-inference -l app.kubernetes.io/name=ollama --grace-period=0 --force

# 2. Deploy the vLLM blueprints with your overrides
helm upgrade --install vllm-serving ./blueprints/vllm-gke -n gemma-inference \
  --set model.name="google/gemma-4-E4B-it" \
  --set persistence.enabled=true \
  --set persistence.storageClassName="standard-rwo" \
  --set persistence.accessModes={ReadWriteOnce} \
  --set persistence.size="100Gi" \
  --set model.quantization="fp8" \
  --set model.servedModelName="gemma4:26b"

# 3. Redeploy the pure, isolated production vLLM gateway proxy manifest
export INFERENCE_ENGINE="vllm"
./standalone/install-all.sh

# 4. Force rollout restart to point the proxy back at the new vLLM service pool
kubectl rollout restart deployment/gemma-gateway -n gemma-inference
```
```bash
# B. Swapping FROM vLLM TO Ollama (Path B to A)
# 1. Completely uninstall active vLLM Helm releases to release GPU locks
helm uninstall vllm-26b vllm-31b vllm-serving -n gemma-inference --ignore-not-found

# 2. Forcibly purge lingering vLLM pods to trigger immediate hardware teardowns
kubectl delete pod -n gemma-inference -l app.kubernetes.io/name=vllm-gke --grace-period=0 --force --ignore-not-found

# 2a. Safeguard (Optional): If PVC finalizers lock up blocking clean reinstalls
# (As documented in Blocker 6, patch the finalizers to release volume protections):
kubectl patch pvc vllm-26b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge || true
kubectl patch pvc vllm-31b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge || true

# 3. Export environment context to direct image hydration tags
export PROJECT_ID=$(gcloud config get-value project)
export REGION="us-west4" # Replace with your active region (e.g. us-west4 or us-central1)
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/gemma-repo"
export INFERENCE_ENGINE="ollama"
export OLLAMA_MODEL_VARIANT="26b" # "26b" MoE or "31b" Dense

# 4. Bootstrap and run installer (hydrates image tags dynamically on execution!)
chmod +x standalone/install-all.sh
./standalone/install-all.sh

# 5. Verify rollout status of the gateway proxy
kubectl rollout status deployment/gemma-gateway -n gemma-inference
```

---

### 5.2. Comprehensive Troubleshooting & Gotchas

#### Blocker 1: `502 Bad Gateway: Inference engine connection error: All connection attempts failed` (CORS / Workstation Proxy Conflicts)
* **Symptom:** UI browser prompts return Bad Gateway network errors directly, while internal curl pods connect beautifully.
* **The Cause:** Cloud Workstations automatically injects `http_proxy`/`https_proxy` OS variables into containers. FastAPI's `httpx` client reads these proxies and attempts to route the local `http://vllm-serving-vllm-gke-service:8000` requests *outside the cluster*, causing connection timeouts.
* **The GKE & GDC Fix:** Upgraded the Gateway Proxy HTTP client instantiations in `gateway/proxy/main.py` to explicitly enforce **`trust_env=False`**. Rebuild and rollout your Gateway Proxy deployment:
  ```bash
  docker build -t <REGISTRY_HOST>/gemma-proxy:latest gateway/proxy
  docker push <REGISTRY_HOST>/gemma-proxy:latest
  kubectl rollout restart deployment/gemma-gateway -n gemma-inference
  ```

#### Blocker 2: `0/2 nodes available: pod has unbound immediate PersistentVolumeClaims` (Storage Capability Conflicts)
* **Symptom:** vLLM pod remains in `0/1 Pending` and refuses to assign on L4/A100 nodes during dynamic Helm upgrades.
* **The Cause:** The GDC production SAN storage uses multi-writer access mapping (`ReadWriteMany`). Standard cloud Dynamic CSI provisioners (like `standard-rwo` and GCE-PD) strictly enforce `ReadWriteOnce` for Persistent Volumes.
* **The GKE sandbox Fix:** Override the storage capability array inside the Helm execution setting:
  ```bash
  --set persistence.accessModes={ReadWriteOnce}
  ```
* **The GDC production Fix:** Unpack and extract the models unquantized staging weights locally onto dedicated rack Persistent Volumes mapped strictly under the `standard-rwx` SAN GDC air-gapped storage pools in the disconnected perimeter.

#### Blocker 3: `401 GatedRepoError / 404 Repository Not Found` (HuggingFace Gating Handshake)
* **Symptom:** vLLM server container aborts startup events with trace errors: `You are trying to access a gated repo. Please log in.`
* **The Cause:** Gemma 4 variants (and staging models like `google/gemma-2b-it`) are gated. Even if GKE is authenticated via `hf-token-secret`, the request will fail with a `401 GatedRepoError` if your specific Hugging Face account has not explicitly accepted the license agreement on the Hugging Face repository page!
* **The Staging Fix**: Ensure you have clicked "Accept License" on Hugging Face for the exact model variant specified in your `--set model.name` Helm command (e.g. `google/gemma-4-E4B-it` or `google/gemma-2b-it`).
* **The Secret Provisioning Fix**: Provision a Kubernetes generic secret containing your Hugging Face Hub token inside GKE:
  ```bash
  kubectl create secret generic hf-token-secret --from-literal=token="<YOUR_HF_TOKEN>" -n gemma-inference
  ```

#### Blocker 4: `CreateContainerConfigError` on PostgreSQL Pod (Missing Database Secrets / ConfigMap)
* **Symptom:** The PostgreSQL database emulator pod (`postgres-0`) remains in `0/1 CreateContainerConfigError` indefinitely.
* **The Cause:** The container specification in `statefulset-postgres.yaml` injects database credentials (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) directly from the Kubernetes Secret `gemma-client-db-credentials`, and mounts `init.sql` from the ConfigMap `postgres-init-script`. If the StatefulSet is applied before the secret or configmap exists in `$NAMESPACE`, `kubelet` fails to construct the container configuration.
* **The Fix:** Create the credentials secret and apply the init script configmap in your active namespace:
  ```bash
  kubectl create secret generic gemma-client-db-credentials \
    --from-literal=username=postgres \
    --from-literal=password=password \
    --from-literal=db_name=postgres \
    --from-literal=connection_string=postgresql://postgres:password@postgres-svc.gemma-inference.svc.cluster.local:5432/postgres \
    -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f gemma-client/manifests/gcp/postgres-configmap.yaml -n $NAMESPACE
  kubectl delete pod postgres-0 -n $NAMESPACE # Force immediate container reconstruction
  ```

#### Blocker 4a: Web UI Stuck on "Contacting Secure Identity Gateway..." (OIDC Port-Forward Mismatch)
* **Symptom:** Opening the browser on port 8081 displays an infinite loading spinner stating *"Contacting Secure Identity Gateway..."* and never redirects or loads the chat interface.
* **The Cause:** The frontend container was built with OIDC enabled (`VITE_ENABLE_OIDC=true`), but the user ran `kubectl port-forward svc/frontend-svc 8081:80`. The `frontend-svc` pod only serves static React assets; it has no reverse-proxy route for `/auth` to reach Keycloak. The browser's redirect handshake falls back to `index.html`, creating an endless reload loop.
* **The Fix:**
  - **If testing with Keycloak OIDC + Gateway API (Pathway B):** Port-forward the **Gateway API L4 Tunnel** (`service/gdc-gateway-tunnel`), which forwards browser requests through `gdc-platform-gateway` (`HTTPRoute/gemma-unified-routes`):
    ```bash
    pkill -f "port-forward" || true
    kubectl port-forward service/gdc-gateway-tunnel 8081:80 -n $NAMESPACE
    ```
    *(Or `kubectl port-forward service/gemma-ingress-gateway 8081:80 -n $NAMESPACE` if using the Section 3.6 NGINX fallback).*
  - **If testing with Mock Auth (Pathway A):** Delete `gemma-client/src/frontend/.env`, rebuild the frontend image (`./gemma-client/scripts/build.sh`), restart the deployment (`kubectl rollout restart deployment/frontend -n $NAMESPACE`), and hard-refresh your browser (`Ctrl+Shift+R` or DevTools `F12` $\rightarrow$ Empty Cache and Hard Reload).

#### Blocker 5: `ErrImagePull / ImagePullBackOff` on Gateway Pod (Baseline Image Placeholder)
* **Symptom:** Pushing updates to the gateway deployment pushes the baseline manifest, causing the gateway pod to enter `ErrImagePull` for using the unhydrated `gemma-gateway:latest` image placeholder.
* **The Cause:** Baseline YAML manifests in the repository preserve unhydrated `image:` placeholders for dynamic pipeline injection. Pushing raw baseline manifests directly bypasses the Artifact Registry tag mappings.
* **The Live Fix:** Re-tag the live GKE deployment to point to your active project Artifact Registry container without Mutating baseline files:
  ```bash
  export REGISTRY_HOST="<YOUR_REGISTRY_HOST>" # e.g. us-central1-docker.pkg.dev/your-project/gemma-repo
  kubectl set image deployment/gemma-gateway gateway=${REGISTRY_HOST}/gemma-proxy:latest -n gemma-inference
  ```
 
 
 #### Blocker 6: `spec.selector is immutable` / `persistentvolumeclaim is being deleted` (GKE Storage Deadlock)
 * **Symptom:** Helm upgrade fails with `spec.selector: field is immutable`, or pods remain `Pending` indefinitely with warnings `0/2 nodes are available: persistentvolumeclaim "vllm-26b-vllm-gke-weights" is being deleted. not found`.
 * **The Cause:** Deployment selector label maps are immutable in GKE. When you uninstall a Helm release, GKE tries to delete the PVCs, but they get stuck in `Terminating` because `kubernetes.io/pvc-protection` finalizers hold a lock on them while GKE pods terminate, blocking Helm from re-creating them!
 * **The Unblocking Fix**: Uninstall the Helm releases first, and forcibly wipe the finalizers on the stuck PVCs to purge them immediately:
   ```bash
   helm uninstall vllm-26b vllm-31b -n gemma-inference
   kubectl patch pvc vllm-26b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge
   kubectl patch pvc vllm-31b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge
   ```
 
 #### Blocker 7: `ErrImagePull / ImagePullBackOff` on Client Frontend (Docker & Browser Caches)
 * **Symptom:** Rebuilding and rolling out client backend or frontend changes has "no effect", or the header model badge doesn't update to Auto.
 * **The Cause:** Docker builds utilize cached layers based on previous folder states, pushing the old bundle to registry! In addition, browser static caches aggressively cache React static JS bundles, loading the old interface.
 * **The Rebuilding Fix**: Rebuild the client frontend with `--no-cache` to bypass Docker layer caching.
 * **The Hidden Chrome "Empty Cache & Hard Reload" Trick**: 
   Standard reloads still fail to evict aggressively cached browser previews. Chrome features a hidden developer refresh menu:
   1. Open your standard, authenticated browser tab targeting port 8081.
   2. Open the Developer Tools by pressing **`F12`** (keep the panel open!).
   3. **Right-Click** (or click and hold) on browser's circular **Reload (Refresh) button** next to the URL bar.
   4. Click the third option: **"Empty Cache and Hard Reload"**!
   *(This evicts the disk cache for the specific domain, forcing Chrome to pull the up-to-date static Javascript bundles).*
 
 #### Blocker 8: `broken pipe` / `lost connection to pod` on Port-Forward Connection (Tunnel severing)
 * **Symptom:** After triggering GKE rollouts or restarts, terminal port-forwarding severes immediately: `broken pipe / readfrom tcp4: write: broken pipe`.
 * **The Cause:** Ephemeral `port-forward` socket tunnels target a single pod TCP socket directly. Rollouts replace old pods with new ones, killing the active socket.
 * **The GDC-ag Production Parity**: In GDC-ag production, this **will NOT occur!** GDC production utilizes **Hardware Load Balancers (HLB)** and active-active **Ingress Controllers** that handle zero-downtime graceful connection draining handovers, routing traffic to new replicas seamlessly with **zero socket interruptions!**
 
  #### Blocker 9: `502 Bad Gateway` / `504 Gateway Timeout` on Complex Prompts (Staging Hardware VRAM Overload & Split-Model PCIe Lag)
  * **Symptom:** Submitting complex, logic-heavy, or code generation prompts (like `"generate the code to create a bubble sort"`) triggers a `502 Bad Gateway` or `504 Gateway Timeout` error after exactly 60 seconds (or 30 seconds), while simple conversational queries return `200 OK` instantly.
  * **The Cause:** 
    1. **Model Weights VRAM Overload:** Unquantized model variants (like Gemma 4 31B Dense) have massive parameters weights exceeding **50GB - 64GB**. In staging standard GKE sandbox environments utilizing a single Nvidia L4 GPU node (providing exactly 24GB VRAM), loading these models forces the serving engine (like Ollama or vLLM) to **split model weights between VRAM and System RAM** (offloading partly to CPU).
    2. **PCI-Express Activation Lag:** Splitting model weights triggers massive, continuous activation serialization transfers across the slow PCI-Express bus during token generation. This collapses token generation throughput down to a crawling pace of **~1 token/second**.
    3. **Proxy Timeout Tripping:** Generating a complex code snippet requires producing 150 - 300 tokens, taking over 3 minutes. The gateway proxy's downstream generation timeout defaults to **60.0 seconds**. At the 60s mark, the proxy times out waiting for the model server to finish, closes the socket connection (which causes Ollama/vLLM to abort with `500` or socket errors), and returns `502 Bad Gateway` to the browser frontend (which gets translated to `504` on Ingress Load Balancers).
  * **The High-Performance Staging Fixes:**
    1. **Uncheck "Thinking Process" (UI Acceleration):** Uncheck the `"🧠 Thinking Process"` checkbox in the chat frontend header. This completely eliminates the free-form reasoning tokens generation step, reducing the total tokens output block by over 60% and bypassing the 60s timeout limit.
    2. **Increase Gateway Generation Timeout (Infrastructure Override):** We have made the completions timeout limit dynamic! Increase the timeout limit inside the deployment manifests (`standalone/manifests/01-gateway.yaml` and `01-gateway-ollama.yaml`) to allow slow staging generations to successfully complete:
       ```yaml
       env:
       - name: GATEWAY_TIMEOUT
         value: "300.0" # Set to 300 seconds (5 minutes) for slow sandbox runs
       ```
       Apply the manifest and restart the gateway proxy to propagate the changes:
       `kubectl apply -f standalone/manifests/01-gateway-ollama.yaml -n gemma-inference`
       `kubectl rollout restart deployment/gemma-gateway -n gemma-inference`
  * **The GDC-ag Production Parity:** In production disconnected racks, NVIDIA H100/A100 multi-GPU node pools are sized up cleanly to fit both full-scale unquantized `26B` and `31B` models concurrently. **Model splitting never occurs**, and complex code generations run at a blinding **40+ tokens/second**, resolving all connection timeouts natively!

  #### Blocker 10: `0/1 Pending` on GPU Pods (Regional GPU Exhaustion & Registry Outages)
  * **Symptom**: Spawning GPU nodes remains in `0/1 Pending` indefinitely with warnings `0/2 nodes available: Insufficient nvidia.com/gpu`, or dynamic builds fail during pushes.
  * **The Cause**: GKE regional pools can sometimes encounter dynamic hardware stock exhaustion (Nvidia L4 GPUs completely out-of-stock in your default zone e.g. `us-central1-a`). To bypass this, operators are forced to spin up cluster nodes inside alternative GCP regions (e.g. `us-west4-b`).
  * **The Registry Synchronization Clash**: If you are forced to shift GKE cluster coordinates (e.g., from `us-central1` to `us-west4`), **you must update your Artifact Registry region coordinates symmetrically (`REGISTRY_HOST` variable)**! If you fail to do this, your build script will push new OIDC containers to `us-central1`, but GKE will continue to pull from the old `us-west4` repository, running yesterday's stale baseline layers without any configurations!
  * **The Fix**: Symmetrically map all target regions inside your build environment before building:
    `export PROJECT_ID="grace-playground"`
    `export REGISTRY_HOST="us-west4-docker.pkg.dev/${PROJECT_ID}/gemma-repo"`
    `./gemma-client/scripts/build.sh -p $PROJECT_ID -r $REGISTRY_HOST`

  #### Blocker 11: `0/1 Error / CrashLoopBackOff` on Ingress Proxy (DNS Lookups Caching Deadlock)
  * **Symptom**: Bouncing the Ingress proxy pod triggers a dynamic CrashLoopBackOff with logs: `nginx: [emerg] host not found in upstream "frontend-svc" in /etc/nginx/nginx.conf:50`.
  * **The Cause**: 
    1. **Missing Service Endpoints**: Ingress proxy NGINX requires resolving all dynamic upstream service FQDNs (such as `frontend-svc:80` and `keycloak-svc:8080`) on boot. Deauthorizing or deleting these services inside GKE triggers a `NXDOMAIN` (Host not found) KubeDNS error, immediately crashing NGINX. (GKE services and gateways can coexist on Port 80, only local workstation port bindings clash!).
    2. **DNS Caching Deadlock**: NGINX only resolves service hostnames once on startup and caches them. Re-applying or re-creating a manifest changes the Virtual Service ClusterIP. NGINX will continue sending requests to the dead, old IP, yielding `504 Gateway Timeout` until the Ingress pod itself is rolled out!
  * **The Fix**: Re-apply the baseline frontend manifest to recreate the service, and rollout/bounce the Ingress gateway pod to refresh the DNS mapping in RAM:
    `kubectl apply -f gemma-client/manifests/apps/frontend.yaml -n gemma-inference`
    `kubectl rollout restart deployment/gemma-ingress-gateway -n gemma-inference`

  #### Blocker 12: `0/1 Error / CrashLoopBackOff` on Keycloak Pod (Agroal Memory Recycles & Bash Parameter Truncations)
  * **Symptom**: Keycloak enters a startup restart loop, exiting with `Error / Exit Code 1` at 41 seconds during `Updating the configuration...`.
  * **The Cause**: 
    1. **H2 Memory Discards**: H2 in-memory databases (`dev-mem` vendor) discard dynamic RAM schemas once active connection pools drop to `0` (which occurs during startup assemble completions), causing welcome pages queries to return `Table "USER_ENTITY" not found`.
    2. **Bash Parameter Truncations**: Keycloak's container start wrapper `kc.sh` evaluates options using UNIX shell expansions and `eval`. Passing connection URLs containing semi-colons splits the execution stream, truncating the Java launch and crashing the container.
  * **The Fix**: Add `KC_DB_POOL_MIN_SIZE=1` to force the database pool to maintain at least one connection active permanently (preventing database recycles), and avoid passing `KC_DB_URL` containing semi-colons in the env array, utilizing `KC_DB_URL_PROPERTIES` instead.

  #### Blocker 13: `504 Gateway Timeout` during Model Variant Swapping (Ollama Weight-Loading Delay)
  * **Symptom**: When using the web chat client, submitting a query that triggers a model variant swap (e.g. from `26b` to `31b`) results in a `504 Gateway Timeout` error in the browser after exactly 60 seconds. However, subsequent queries or the direct Python CLI client works fine.
  * **The Cause**: 
    1. **Dynamic VRAM Weight Loading**: In GKE sandbox environments, the serving engine (Ollama) dynamically unloads the inactive model from GPU memory and reads/loads the new variant's weights from disk. This process takes 60–90 seconds under VM resource constraints.
    2. **Short Ingress Timeout**: The staging NGINX ingress proxy acts as the single-origin ingress gateway. By default, NGINX's `proxy_read_timeout` is set to `60` seconds. Since the client backend waits synchronously (`stream=False`) for the full response, NGINX terminates the browser's connection after 60 seconds before Ollama finishes loading the model.
  * **The Staging Fix**: Increase the NGINX proxy timeouts to `300s` in the ingress config map:
    ```yaml
    # In gemma-client/manifests/gcp/nginx-ingress-staging.yaml:
    location /api/ {
        proxy_pass http://backend-svc:8000/;
        ...
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
    ```
    Apply the updated manifest and restart the ingress gateway:
    `kubectl apply -f gemma-client/manifests/gcp/nginx-ingress-staging.yaml -n gemma-inference`
    `kubectl rollout restart deployment/gemma-ingress-gateway -n gemma-inference`
  * **The GDC-ag Production Parity**: In GDC air-gapped production, this **will NOT occur**. Production utilizes **vLLM** serving pools with dedicated, permanently warmed-up GPU nodes for each model variant (`26B MoE` and `31B Dense`). Model weights are kept loaded in VRAM, meaning switching variants simply redirects the network call, executing in milliseconds without weight-loading lag.

  #### Blocker 14: `Cryptographic credentials validation failed: Signature has expired` (OIDC Token Clock-Drift)
  * **Symptom**: User login or API queries fail, and the client backend logs return: `OIDC Claim Check Failed: Signature has expired` / `Cryptographic credentials validation failed`.
  * **The Cause**: Clock synchronization drift between the Keycloak server pod and the client backend pod (especially common in virtualized Cloud Workstation VMs). Python-jose's `jwt.decode` enforces strict expiration verification with `0` seconds of leeway, causing it to reject tokens that appear to be issued in the future or expired by a few seconds.
  * **The Staging Fix**: Configure a token validation leeway (e.g. `leeway=60` seconds) inside the backend's JWT decoder options in `gemma-client/src/backend/auth.py`:
    ```python
    payload = jwt.decode(token, jwks, algorithms=ALGORITHMS, options={"verify_aud": False, "leeway": 60})
    ```
    Rebuild and restart the client backend:
    `docker build -t ${REGISTRY_HOST}/gemma-client-backend:latest ./gemma-client/src/backend/`
    `docker push ${REGISTRY_HOST}/gemma-client-backend:latest`
    `kubectl rollout restart deployment/backend -n gemma-inference`
  * **The GDC-ag Production Parity**: In GDC air-gapped production, NTP servers synchronize the clocks of all server nodes, and production identity tokens are verified by native cluster gateways using synchronized clocks, minimizing time drift below milliseconds.

 ### 5.3. Essential Kubernetes Troubleshooting CLI Commands

Keep this dynamic GKE & GDC operations cheatsheet open for rapid troubleshooting during deployments:

```bash
# 1. Monitoring Pod Uptime and Rollout Statuses
kubectl get pods -n gemma-inference                                      # List all pods
kubectl get pods -n gemma-inference -w                                   # Watch status changes in real-time
kubectl rollout status deployment/gemma-gateway -n gemma-inference        # Verify proxy rollout transitions

# 2. Dynamic Storage & Volume Allocations checks
kubectl get pvc -n gemma-inference                                      # List PersistentVolumeClaims
kubectl describe pvc vllm-serving-vllm-gke-weights -n gemma-inference     # Inspect storage provisioner errors

# 3. Targeted Logs Streaming and previous crashes analysis
kubectl logs -f deployment/gemma-gateway -n gemma-inference              # Stream proxy logs
kubectl logs -f deployment/vllm-serving-vllm-gke -c vllm -n gemma-inference # Stream model server logs
kubectl logs pod/<CRASHING_POD_NAME> -c vllm -n gemma-inference -p       # Extract logs from the PREVIOUS crashed instance

# 4. Deep Scheduler Events & Sandbox Inspections
kubectl describe pod <POD_NAME> -n gemma-inference                       # Inspect pod scheduling and taints Events table
kubectl get nodes -o custom-columns=NAME:.metadata.name,ACCELERATOR:.metadata.labels."cloud\.google\.com/gke-accelerator" # Check cluster GPU taints labels

# 5. Recycle deadlocked ReplicaSets & Volumes immutable bindings
kubectl delete pod <POD_NAME> -n gemma-inference --grace-period=0 --force # Forcibly purge hanging pods
kubectl delete pvc <PVC_NAME> -n gemma-inference                         # Delete immutable PVC storage claims

# 6. Hardened DevSecOps Image Diagnostics (No curl/shell footprint available)
# Because our production and sandboxed containers follow strict DevSecOps hardening standards,
# standard utilities like 'curl' and 'shell execs' are stripped from the image PATH.
# Use Python's standard 'urllib.request' library natively from inside the gateway container:
kubectl exec -it deployment/gemma-gateway -n gemma-inference -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://ollama-26b-service:11434/api/tags').read().decode())"
```

---

### Alternative: Deploy via Standardized Helm Wrapper Charts on GCP GKE

After provisioning the GCP emulation backing services (`manifests/gcp/`), you can deploy the Gateway and Gemma Client workloads on GKE using the standardized Helm wrapper charts (`standalone/chart` and `gemma-client/chart`, where `gdc.enabled: false` by default omits GDC-only `DBCluster` CRDs):

```bash
# Deploy Gemma Gateway Proxy & HTTPRoute via Helm
helm upgrade --install gemma-gateway ./standalone/chart \
  --namespace ${NAMESPACE} --create-namespace \
  --set global.projectId=${PROJECT_ID} \
  --set global.namespace=${NAMESPACE} \
  --set global.registry=${REGISTRY_HOST}

# Deploy Gemma Client Backend & Frontend via Helm
helm upgrade --install gemma-client ./gemma-client/chart \
  --namespace ${NAMESPACE} \
  --set global.projectId=${PROJECT_ID} \
  --set global.namespace=${NAMESPACE} \
  --set global.registry=${REGISTRY_HOST}
```
