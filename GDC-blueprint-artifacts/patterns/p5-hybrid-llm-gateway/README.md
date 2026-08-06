Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 5: Resilient Hybrid LLM Gateway [DEPRECATED]

> [!CAUTION]
> **DEPRECATED PATTERN**:
> Pattern 5 (Resilient Hybrid LLM Gateway) is **deprecated** as of Blueprint Version 1.2.
> Applications (such as Pattern 6 RAG Agent, Pattern 7 Agentic Data Analyst, Pattern 9 Sovereign Notebook, and Pattern 10 Chatbot) now natively interface directly with either the **Gemma Inference Gateway** (`gdc_gemma_gw` / vLLM / Ollama) or **GDC Gemini AI Gateway**.
> Dedicated proxy gateways (Pattern 5) are no longer required for multi-provider routing.

**Use Case:** Legacy failover for GenAI apps if the primary platform model is unreachable.

## Architecture Schematic

```text
+----------------------+
|      GenAI App       |
+----------------------+
         |
         v
+----------------------+
| LLM Gateway (GKE)    |
| (2 Replicas)         |
+----------------------+
         |
         |  (Primary Attempt)
         v
+----------------------+      +----------------------+
| Gemini API           |      | Gemma (Ollama/vLLM)  |
| (Direct Endpoint)    |<-----| (Failover Endpoint)  |
+----------------------+      +----------------------+
```

## Design & Resilience Strategy

1.  **The Gateway Service:** A new, lightweight microservice (e.g., in Python/Go) is deployed onto a **GDC GKE Cluster**. This service is deployed with multiple replicas for high availability and is exposed via a GKE Service (ClusterIP) to other applications within GDC.
2.  **Primary LLM (Gemini):** The GDC platform provides Gemini via the **Gemini API** endpoint. This is a managed, resilient service endpoint called directly by the Gateway.
3.  **Failover LLM (Gemma):** The open-source Gemma model is hosted locally using **Ollama** running on an infrastructure pod equipped with GPUs. This runs independent of Model Garden.
4.  **Resilient Failover Logic:**
    *   Agentic workloads (like Archetypes 6 & 7) send their prompts to the *Gateway Service* endpoint, not directly to the LLMs.
    *   The Gateway's internal logic first attempts to call the **Gemini API**.
    *   If this call fails (e.g., HTTP 5xx error, network timeout), the logic catches the exception, logs the error, and automatically retries the *exact same prompt* against the **Gemma (Ollama)** failover endpoint.
    *   This ensures that even if the primary Gemini service has a temporary issue, the agent's "brain" seamlessly fails over to the locally-hosted model, providing high availability for reasoning tasks.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The LLM Gateway application image must be built and pushed. More importantly, the Ollama or vLLM images must be built with the model weights (e.g., Gemma) "baked in" (as detailed in the Implementation section) and pushed to the internal GDC registry.
2.  **Helm Charts:** The Ollama or vLLM Helm charts must be downloaded and transferred.
3.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
4.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Supports 100+ concurrent requests (proxy layer). Failover capacity depends on local model size.

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LLM Gateway** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Failover Model (Ollama)** | `g2-standard-4` or `a2-highgpu-1g` | 4+ | 16Gi+ | 50Gi+ | Yes (e.g., L4, A100) |
| **Failover Model (vLLM)** | `g2-standard-8` (RAM hungry) | 8+ | 24Gi+ | 50Gi+ | Yes (A100 preferred) |

**Scaling & Upgrades:**
*   **Gateway:** Use HPA to scale the gateway service based on CPU/Memory usage.
*   **Failover Model:** Inference requires stable GPU node pools. Scale replica counts horizontally for increased concurrent capacity. Storage scaling is required for model weight persistence.
*   **Primary LLM:** Managed by the platform (Gemini). No user scaling required.

**Sizing Rationale:**
The Gateway is a lightweight proxy. The Failover Model sizing is dictated by the hardware requirements to run a 7B+ parameter LLM (Gemma) with acceptable inference latency.

## Configuration

### Model Configuration

The primary Gemini model and the local failover (Gemma) model are defined in the `gateway-conf` ConfigMap within the gateway deployment manifests.

**Changing the Default Gemini Model**

To change the default Gemini model used as the primary LLM:

1. Open `manifests/apps/llm-gateway.yaml`.
2. Locate the `gateway-conf` ConfigMap at the top of the file.
3. Modify the `GEMINI_MODEL` property to your desired model (e.g., `gemini-1.5-pro`):
   ```yaml
   data:
     # ... other variables ...
     GEMINI_MODEL: "gemini-1.5-pro"
   ```

**Choosing a Different Target for Local Failover (Gemma)**

To specify a different model for the failover endpoint (such as a different size of Gemma):

1. **Verify Local Model Availability**: Ensure the desired model (e.g., `gemma:2b`) is downloaded or baked into your Ollama/vLLM container image and deployed successfully.
2. Open `manifests/apps/llm-gateway.yaml`.
3. Locate the `gateway-conf` ConfigMap.
4. Modify the `FAILOVER_MODEL` property to match the local model tag:
   ```yaml
   data:
     # ... other variables ...
     FAILOVER_MODEL: "gemma:2b"
   ```

### Blueprint Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL> -d p5-hybrid-llm-gateway
```

## Required IAM Permissions

To deploy the resources for this pattern, your user account will need the following roles granted in your target project:

*   **GKE Developer:** To deploy the gateway application, service, and configmap to the GKE cluster.
    *   `roles/gke.developer`
*   **AI Invoker:** To use the robust new `google-genai` SDK for direct Vertex API calls, the gateway leverages the built-in `gateway-sa` Kubernetes Service Account (KSA). In a GDC-ag environment, this KSA must be granted the appropriate GDC IAM roles (e.g., via `gdcloud iam service-accounts add-iam-policy-binding`) to access the Vertex API endpoints:
    *   `Role/ai-invoker` (or the equivalent GDC-ag role for Vertex AI access)

## Implementation

### Step 1: Air-Gapped Preparation (Connected Workstation)
For GDC Air-Gapped environments, **you MUST use the "Baked Image" strategy** for the LLM. Runtime model pulling (`ollama pull`) will fail in an air-gapped environment.

1.  **Automated Baking (Default)**:
    We have streamlined this process for you. When you run `./p5-hybrid-llm-gateway/scripts/build.sh` (or the bulk deployment script), it now **automatically** builds the `ollama-gemma:7b` image natively. It does this by pulling the base image and downloading the model weights directly into the file layers via a dedicated Dockerfile. 

2.  **Automated Packaging**:
    Because we integrated a pointer configuration file (`manifests/apps/ollama-gemma-pointer.yaml`), the default `scripts/package-for-gdc.sh` script automatically detects this newly baked massive container image, groups it alongside the gateway UI, and bundles it all into the final `p5-hybrid-llm-gateway-gdc-images.tar` payload. No manual intervention (like `mirror_images.sh`) is required to transfer the 5GB+ Gemma payload—it acts exactly like normal custom code.

3.  **Build Custom vLLM Image (Manual Alternative)**:
    If utilizing vLLM as the backend, you must also bake the model weights.
    ```dockerfile
    FROM vllm/vllm-openai:latest
    
    # Pre-download the model to the cache directory
    ENV MODEL_NAME="TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='${MODEL_NAME}')"
    
    # Set the environment variable so vLLM finds it offline
    ENV HF_HUB_OFFLINE=1
    ```
    
    Build and push:
    ```bash
    docker build -t harbor.gdc.local/library/vllm-tinyllama:1.1b .
    docker push harbor.gdc.local/library/vllm-tinyllama:1.1b
    ```

3.  **Download Helm Charts**:
    *   **Ollama:** Download the chart to `p5-hybrid-llm-gateway/charts/ollama` (using `helm pull ... --untar`).
    *   **Backend:** Ensure the `p5-hybrid-llm-gateway/charts/vllm` chart is present (if used).

### Step 2: Configure IAM (GDC Production)

You must explicitly grant the Gateway permission to use the GDC pre-trained APIs for the primary Vertex LLM calls. The `gateway-sa` ServiceAccount is automatically created by the `llm-gateway.yaml` manifest.

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>
gdcloud iam service-accounts add-iam-policy-binding gateway-sa --project=$PROJECT_ID --role=Role/ai-invoker
```

**Option B: GitOps**

Sync the `manifests/iam/gateway-permissions.yaml` file to your cluster to securely bind the `Role/ai-invoker` to the `gateway-sa` ServiceAccount.

### Step 3: Deploy Failover Model (GDC)
Deploy using the local chart and your baked image.

**Option A: Ollama + Baked Gemma (Recommended for GDC)**
```bash
# Install from local chart directory using BAKED image
# Note: We disable 'ollama.models.pull' since the model is already baked in.
helm upgrade --install ollama ./p5-hybrid-llm-gateway/charts/ollama \
  --namespace ${NAMESPACE} \
  --set ollama.gpu.enabled=true \
  --set ollama.gpu.type=nvidia \
  --set image.repository=harbor.gdc.local/library/ollama-gemma \
  --set image.tag=7b \
  --set "ollama.models.pull={}"
```

**Option B: vLLM + Baked TinyLlama**
```bash
# Install vLLM using BAKED image
# We set model.name to the huggingface ID, but with HF_HUB_OFFLINE=1 in the image, 
# it will look for the cached weights.
helm upgrade --install vllm ./p5-hybrid-llm-gateway/charts/vllm \
  --namespace ${NAMESPACE} \
  --set image.repository=harbor.gdc.local/library/vllm-tinyllama \
  --set image.tag=1.1b \
  --set model.hfToken="" \
  --set model.name="TinyLlama/TinyLlama-1.1B-Chat-v1.0" \
  --set extraEnv[0].name=HF_HUB_OFFLINE \
  --set extraEnv[0].value="1"
```

### Step 4: Deploy Gateway

The Gateway is configured to failover to Ollama by default. To use vLLM, you must update the configuration.

**Configure for vLLM (if using Option B above):**
Update the ConfigMap or Environment Variables:
- `FAILOVER_BACKEND`: `vllm`
- `FAILOVER_URL`: `http://vllm:8000/v1/completions` (or similar endpoint)
- `FAILOVER_MODEL`: `TinyLlama/TinyLlama-1.1B-Chat-v1.0` (must match the model loaded in vLLM)

Then deploy the gateway:

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/apps/llm-gateway.yaml
```

**Option B: GitOps**

Sync the `manifests/apps/llm-gateway.yaml` file to your cluster.

## Testing


### Standard Testing
This pattern includes scripts to help validate the artifacts and verify a successful deployment. The scripts are located in the `test/` directory.

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

#### Verifying Primary LLM (Gemini) on GDC

After deploying to your GDC environment, you should verify the primary Gemini mechanism manually to ensure the gateway successfully connects to the direct Gemini API endpoint:

1.  **Test the Gateway**:
    Shell into a pod or use a localized curl instance to hit the gateway's service endpoint.
    ```bash
    curl -X POST http://llm-gateway.<YOUR_NAMESPACE>.svc.cluster.local:80/generate \
      -d '{"prompt": "Hello, how are you?"}' \
      -H 'Content-Type: application/json'
    ```
    *Expected Result*: The response JSON should contain an answer from the model and indicate `"source": "primary"`.

2.  **Check Logs**:
    Inspect the gateway logs to confirm it successfully called the primary Gemini endpoint and did not attempt to fail over.
    ```bash
    kubectl logs -l app=gateway -n <YOUR_NAMESPACE>
    ```

#### Verifying Failover in Air-Gapped Environments

After deploying to your air-gapped GDC environment, you can verify the failover mechanism manually by temporarily forcing the gateway to use an invalid upstream endpoint:

1.  **Force Failover**:
    Update the `GEMINI_ENDPOINT` environment variable in the gateway deployment to an unreachable URL.
    ```bash
    kubectl set env deployment/llm-gateway GEMINI_ENDPOINT="https://invalid.endpoint" -n <YOUR_NAMESPACE>
    ```

2.  **Test the Gateway**:
    Shell into a pod or use a localized curl instance to hit the gateway's service endpoint.
    ```bash
    curl -X POST http://llm-gateway.<YOUR_NAMESPACE>.svc.cluster.local:80/generate \
      -d '{"prompt": "Test failover"}' \
      -H 'Content-Type: application/json'
    ```
    *Expected Result*: The response JSON should contain `"source": "failover"`.

3.  **Check Logs**:
    Inspect the gateway logs to confirm it attempted the primary endpoint, failed, and switched to the secondary.
    ```bash
    kubectl logs -l app=gateway -n <YOUR_NAMESPACE>
    ```

4.  **Restore Primary**:
    Remove the environment variable override to revert to the primary Gemini API.
    ```bash
    kubectl set env deployment/llm-gateway GEMINI_ENDPOINT- -n <YOUR_NAMESPACE>
    ```

### Local Testing

You can run the validation and verification scripts locally using the provided test runner, which mocks the GDC and Kubernetes CLI commands.

```bash
# Run from the root of the repository
bash tests/run-local.sh
```

This will run the configuration tests and the verification logic for all patterns.
## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p5-hybrid-llm-gateway
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p5-hybrid-llm-gateway
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p5-hybrid-llm-gateway-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p5-hybrid-llm-gateway-gdc-images.tar` (The bundled local Gateway container images and your heavily baked LLM payload)
    *   `p5-hybrid-llm-gateway-BOM.txt` and `p5-hybrid-llm-gateway-manifest.txt` (Integrity checksums)
    *   `p5-hybrid-llm-gateway-README.md` (Standalone deployment instructions)
*   **Global Dependencies (Generated in the `artifacts/` directory):**
    *   `artifacts/external-dependencies/charts/ollama-*.tgz` (The Ollama external Helm chart suite)
    *   `artifacts/external-dependencies/images/` (Standard infrastructure images tracked by the pattern, if applicable)
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

2. **Load and Push Gateway Images:** Extrapolate the locally-built Gateway images (and if utilizing the auto-baking script, your raw local Model weight images!):
   ```bash
   ./scripts/unpack-for-gdc.sh p5-hybrid-llm-gateway-gdc-images.tar harbor.gdc.local/library
   ```

3. **Extract Kubernetes Manifests:** Extract the tailored blueprint YAMLs:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf p5-hybrid-llm-gateway-gdc-manifests.tar.gz -C ./gdc-manifests/
   ```

4. **Deploy Failover Backend Helm Chart:** Unpack the Ollama Suite from `artifacts/` and cleanly install it to host your baked LLM instances securely via `--set`:
   ```bash
   tar -xzf artifacts/external-dependencies/charts/ollama-*.tgz -C ./
   helm upgrade --install ollama ./ollama \
     --namespace ${NAMESPACE} \
     --set ollama.gpu.enabled=true \
     --set image.repository=harbor.gdc.local/library/ollama-gemma \
     --set "ollama.models.pull={}"
   ```

5. **Apply Localized Gateway Manifests:** Execute the routing fabric YAMLs:
   ```bash
   kubectl apply -f ./gdc-manifests/manifests/apps/llm-gateway.yaml
   ```
