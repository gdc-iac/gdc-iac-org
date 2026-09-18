Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GDC Gemma 4 Gateway: FAQ & Operational Troubleshooting Guide

> **Version:** 1.1

This guide collates the comprehensive trouble-shooting expertise, operational lessons, and architectural nuances learned during the design, development, and validation of the **Gemma 4 Dedicated Inference Gateway** on **Google Distributed Cloud air-gapped (GDC-ag)**. 

---

## 1. Development Sandbox (GCP Emulation) vs. GDC Production

When engineering and validating the gateway, developers utilize a Google Cloud GKE GPU sandbox (running standard L4 GPUs) to emulate GDC-ag. However, significant infrastructure constraints and behaviors differ between the emulation sandbox and the disconnected production rack.

| Dimension | Development Sandbox (GCP GKE Emulation) | GDC Air-Gapped Production (Target) |
| :--- | :--- | :--- |
| **Hardware / VRAM** | Restricted VRAM (NVIDIA L4 = **24GB VRAM**). Cannot host both unquantized `26B` (MoE) and `31B` (Dense) side-by-side natively without OOM failures. | High-performance multi-GPU pools (NVIDIA H100/A100). Natively hosts both unquantized models concurrently. |
| **Model Precision** | Requires **FP8 quantization** overlays (`--set model.quantization="fp8"`) or lightweight mock variants (like `google/gemma-2b-it`) to fit memory. | Full unquantized native **BF16** precision (no quantization degradation). |
| **Storage Classes** | Dynamic cloud block storage (`standard-rwo`) enforcing **ReadWriteOnce** (RWO) access modes. | Enterprise SAN dynamic storage classes (`standard-rwx`) supporting **ReadWriteMany** (RWX) multi-writer mappings. |
| **Image Registry** | Dynamic network access to Google Artifact Registry (`us-central1-docker.pkg.dev`). | Air-gapped Harbor registry loaded via secure `gdcloud` sideloading (`gdcloud container images import`). |
| **Ingestion Strategy** | Direct pulling from registry or huggingface endpoints using cluster secrets. | Offline sideloading. Weights are tarballed, transferred over security perimeters, and extracted onto dynamic SAN volumes. |
| **Ingress & Routing** | Ephemeral tunnels (`kubectl port-forward`) mapping direct, single-pod TCP sockets. | Hardware Load Balancers (HLB) and active-active Ingress controllers with zero-downtime connection draining. |

---

## 2. How to Validate Model Hot-Swapping on GDC

The gateway features a server-side **Prompt Routing Classifier** (`gateway/proxy/main.py`) that inspects user queries and routes them dynamically to the optimal model. General conversational prompts route to **26B MoE** (optimized for low-latency stream generation), while complex coding or mathematical reasoning prompts route to **31B Dense** (optimized for precision reasoning).

Operators and platform administrators must be able to verify that this routing and VRAM allocation works as expected on GDC-ag without external telemetry tools.

```
               +---------------------------------------+
               |        Gemma 4 Gateway Proxy          |
               |    (Prompt Complexity Classifier)     |
               +-----------+-------------------+-------+
                           |                   |
         (Conversational)  |                   | (Complex Reasoning)
         Model: gemma4:26b |                   | Model: gemma4:31b
                           v                   v
               +-------------------+   +-------------------+
               |  vLLM Service A   |   |  vLLM Service B   |
               | (vllm-26b-service)|   | (vllm-31b-service)|
               +---------+---------+   +---------+---------+
```

To validate model hot-swapping end-to-end, follow these three concurrent feedback loops:

### Loop A: Payload & Classifier Verification (Gateway Logs)
Stream the gateway proxy container logs to observe prompt classification decisions in real time:
```bash
kubectl logs -f deployment/gemma-gateway -n gemma-inference
```
* **Conversational Trigger**: Send a general query (e.g., *"Hello, tell me a joke!"*). You should witness:
  ```text
  INFO:gemma-gateway:[Classifier] General conversational query detected. Routing to Gemma 4 26B MoE.
  INFO:gemma-gateway:[Classifier] Dynamic route resolved: gemma4:26b at http://vllm-26b-service.gemma-inference.svc.cluster.local:8000
  ```
* **Reasoning Trigger**: Send a coding query (e.g., *"Write a python function to compute Fibonacci"*). You should witness:
  ```text
  INFO:gemma-gateway:[Classifier] Complexity keyword detected: 'python'. Routing to Gemma 4 31B Dense.
  INFO:gemma-gateway:[Classifier] Dynamic route resolved: gemma4:31b at http://vllm-31b-service.gemma-inference.svc.cluster.local:8000
  ```

### Loop B: VRAM scheduling Verification (Model Engine Logs)
Depending on your deployed engine, track memory allocations and layer loading:
* **For Ollama (Testing)**: Stream the Ollama container logs to verify the server dynamically shifts GPU VRAM slots:
  ```bash
  kubectl logs -f deployment/ollama-26b -c ollama -n gemma-inference
  ```
  Look for logs signaling the hot allocation of layers:
  ```text
  source=runner.go ... load request="{Operation:alloc Model:gemma4:31b ...}"
  offloading 30 repeating layers to GPU
  ```
* **For vLLM (Production)**: Stream the target vLLM pod logs to verify that the connection lands on the isolated pod corresponding to the selected release:
  ```bash
  kubectl logs -f deployment/vllm-31b-vllm-gke -c vllm -n gemma-inference
  ```

### Loop C: Client Frontend Synchronization (End-to-End Browser UI)
1. Access the user chat console. The model badge chip in the top-right header initially displays: **`Gemma 4 Gateway (Auto)`**.
2. Type *"Hello, can you recommend a fun weekend itinerary?"* and submit. The badge instantly flips to **`Gemma 4 26B A4B (MoE)`**.
3. In the same chat interface, type *"Implement a Java class that represents a Graph data structure"* and submit.
4. The badge instantly refreshes to display **`Gemma 4 31B (Dense)`**, demonstrating real-time, server-driven client synchronization!

---

## 3. Copy-Paste Test Prompts (Verification Suite)

Use these exact, pre-validated prompts to force model swaps and test dynamic routing:

### Conversational Prompts (Triggers `26B MoE` - Latency Optimized)
* `"Hello! Can you suggest a fun weekend itinerary for visiting Seattle on a rainy day?"`
* `"Describe the main differences between a classical piano and an electric keyboard in two sentences."`
* `"Write a short, creative story about a lost astronaut who stumbles upon a lush green forest on a foreign moon."`

### Complex Reasoning Prompts (Triggers `31B Dense` - Reasoning Optimized)
* `"Write a python function that reads a CSV payload from a local directory, parses the rows into a dictionary, and calculates the standard deviation."` (Triggers: `python`, `function`, `calculate`)
* `"Can you explain step-by-step the mathematical derivation of the quadratic equation formula and solve for x in: 2x^2 - 7x + 3 = 0?"` (Triggers: `mathematical`, `solve`, `step-by-step`)
* `"Implement a Java class that represents a Graph data structure, and write a Dijkstra algorithm to find the shortest path between nodes."` (Triggers: `implement`, `algorithm`)

---

## 4. Infrastructure Troubleshooting & Blocker FAQ

### Q: My UI prompts fail with "502 Bad Gateway: Inference engine connection error: All connection attempts failed". Why?
* **The Cause**: In GCP Cloud Workstations, OS environment variables like `http_proxy` and `https_proxy` are injected into containers. Standard HTTP clients (like `httpx` in FastAPI) read these variables and try to route internal GKE service calls (e.g. `http://vllm-26b-service:8000`) *outside* the cluster through the Workstation proxy, causing timeouts.
* **The GDC-ag Production Fix**: Ensure that your HTTP clients initialize with `trust_env=False` to prevent reading these workstation proxies. This is already enforced in the gateway backend:
  ```python
  self.client = httpx.AsyncClient(trust_env=False, timeout=timeout)
  ```
* **The Workstation Staging Fix**: If you modified the client, rebuild and rollout-restart the proxy deployment:
  ```bash
  docker build -t $REGISTRY_HOST/gemma-proxy:latest gateway/proxy
  docker push $REGISTRY_HOST/gemma-proxy:latest
  kubectl rollout restart deployment/gemma-gateway -n gemma-inference
  ```

### Q: My vLLM pod remains in "Pending" with "0/2 nodes available: pod has unbound immediate PersistentVolumeClaims". How do I fix this?
* **The Cause**: GDC production Helm values configure dynamic SAN storage (`ReadWriteMany`, storage class `standard-rwx`). If deploying in a standard GCP emulation sandbox, standard cloud provisioners (like GCE-PD) only support `ReadWriteOnce` (`standard-rwo`).
* **The Emulation/Sandbox Fix**: Pass the emulation override settings during Helm installation:
  ```bash
  --set persistence.storageClassName="standard-rwo" \
  --set persistence.accessModes={ReadWriteOnce}
  ```
* **The GDC Production Fix**: Confirm that GDC SAN volumes are properly mounted in the physical rack and that the StorageClass `"standard-rwx"` is active.

### Q: My vLLM container fails startup with "401 GatedRepoError: You are trying to access a gated repo". What is missing?
* **The Cause**: Gemma 4 models are gated. Even if a Kubernetes image pull secret is configured, Hugging Face restricts API access unless your specific developer account has explicitly agreed to the license terms on the Hugging Face model page.
* **The Fix**:
  1. Accept the model license terms on Hugging Face (e.g. for `google/gemma-4-26B-A4B-it` or `google/gemma-2b-it`).
  2. Provision a Kubernetes secret containing your Hugging Face token inside your namespace:
     ```bash
     kubectl create secret generic hf-token-secret --from-literal=token="<YOUR_HF_TOKEN>" -n gemma-inference
     ```

### Q: Helm upgrade fails with "spec.selector is immutable" or PVCs are stuck in "Terminating" during re-deployments. How do I break the deadlock?
* **The Cause**: GKE/GDC deployments have immutable selectors. Furthermore, uninstalling a Helm release triggers PVC deletion, but the PVCs get stuck in `Terminating` because of the `kubernetes.io/pvc-protection` finalizer, which holds the volumes locked while pods are cleaning up. This blocks Helm from re-creating the deployment.
* **The Unblocking Fix**: Purge the stuck resources by force-removing the finalizers on the terminating PVCs:
  ```bash
  helm uninstall vllm-26b vllm-31b -n gemma-inference
  kubectl patch pvc vllm-26b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge
  kubectl patch pvc vllm-31b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge
  ```

### Q: I updated my React frontend components, but the header badge does not update or changes are not visible. Why?
* **The Cause**: This is caused by two aggressive cache layers:
  1. **Docker Build Caching**: Docker caches filesystem layers. If it fails to recognize file changes, it pushes the cached old bundle to Artifact Registry.
  2. **Aggressive Browser Caching**: Modern browsers cache Vite/React static JS bundles aggressively to speed up page loads.
* **The Fix**:
  1. Force Docker to build without cache:
     ```bash
     docker build --no-cache -t $REGISTRY_HOST/gemma-client-frontend:latest gemma-client/src/frontend
     docker push $REGISTRY_HOST/gemma-client-frontend:latest
     ```
  2. Perform a hard browser refresh:
     - **Mac**: `Cmd + Shift + R` (or hold `Shift` and click reload).
     - **Windows/Linux**: `Ctrl + F5` or `Ctrl + Shift + R`.

### Q: Why does my "kubectl port-forward" session disconnect with "broken pipe" or "lost connection to pod" every time I rollout?
* **The Cause**: `kubectl port-forward` maps a TCP socket tunnel directly to a *single pod* instance. When you trigger a rollout restart or redeployment, that specific pod is terminated, immediately severing the socket tunnel.
* **Production Parity Note**: This tunnel breakage **will NOT occur in GDC-ag Production!** GDC-ag environments use **Hardware Load Balancers (HLB)** and native **Ingress Controllers** mapped to highly available active-active replica pools. When a rollout occurs, the Ingress/HLB performs graceful connection draining, routing subsequent user traffic seamlessly to warm replicas with **zero downtime or socket interruptions**.

---

## 5. Real-World Diagnostic Case Studies

### Case Study 1: Forgetting Environment Variables (Hydration Placeholder Failure)
* **The Scenario**: A developer runs the standalone setup script (`./standalone/install-all.sh`) or deploys manually without exporting the target environment variables (`PROJECT_ID`, `REGISTRY_HOST`) on the Cloud Workstation.
* **The Symptom**: The gateway pod enters an `ErrImagePull` or `ImagePullBackOff` state.
* **Step-by-Step Diagnosis**:
  1. **Detect Pod Failure**: Run `kubectl get pods -n gemma-inference` and notice the gateway pod is not starting:
     ```text
     NAME                             READY   STATUS             RESTARTS   AGE
     gemma-gateway-5d8895f6-abc12     0/1     ImagePullBackOff   0          2m
     ```
  2. **Inspect Pod Events**: Describe the failing pod using `kubectl describe pod <pod_name> -n gemma-inference`. Scroll to the **Events** table at the bottom and observe:
     ```text
     Warning  Failed     12s (x3 over 45s)  kubelet  Failed to pull image "gemma-gateway:latest": rpc error: code = Unknown desc = failed to resolve image "docker.io/library/gemma-gateway:latest": pull access denied...
     ```
  3. **Trace the Root Cause**: The Kubelet is attempting to pull from `docker.io/library/gemma-gateway:latest` instead of the private Harbor/Artifact Registry host! This indicates that the baseline hydration placeholder `image: gemma-gateway:latest` inside `manifests/01-gateway.yaml` was not replaced.
* **Resolution**:
  1. Define your Workstation / GDC target variables in the terminal session:
     ```bash
     export REGISTRY_HOST="us-central1-docker.pkg.dev/your-project-id/gemma-repo"
     ```
  2. Run the setup pipeline again. The installation script will detect `REGISTRY_HOST` and automatically run the dynamic stream-editor (`sed`) to replace placeholders:
     ```bash
     ./standalone/install-all.sh
     ```
  3. For an immediate hotfix on a live GKE/GDC deployment, update the image path directly via kubectl:
     ```bash
     kubectl set image deployment/gemma-gateway gateway=${REGISTRY_HOST}/gemma-proxy:latest -n gemma-inference
     ```

---

### Case Study 2: Dual-Serving Round-Robin Cross-Talk (Traffic Leakage / Selector Collision)
* **The Scenario**: You deploy both the 26B MoE and 31B Dense vLLM serving instances side-by-side in the GKE cluster using Helm. The gateway routes queries, but you notice random completions failures or intermittent `404 Model Not Found` errors from vLLM.
* **The Symptom**: When the gateway classifier routes prompts to `gemma4:31b`, 50% of the requests succeed, while the other 50% return a vLLM `404 Not Found` error. In the gateway log, you witness:
  `Routing to http://vllm-31b-service:8000` but the downstream response is rejected with model mismatch!
* **Step-by-Step Diagnosis**:
  1. **Inspect Pod Labels**: List all pods with their assigned Kubernetes labels:
     ```bash
     kubectl get pods -n gemma-inference --show-labels
     ```
     Notice that both model pods possess identical chart metadata labels:
     - `vllm-26b` pod labels: `app.kubernetes.io/name=vllm-gke, app.kubernetes.io/instance=vllm-26b`
     - `vllm-31b` pod labels: `app.kubernetes.io/name=vllm-gke, app.kubernetes.io/instance=vllm-31b`
  2. **Inspect Service Selectors**: Look at the Service definitions binding the network endpoints:
     ```bash
     kubectl get svc vllm-31b-service -n gemma-inference -o yaml
     ```
     Inspect the `spec.selector` block:
     ```yaml
     spec:
       selector:
         app.kubernetes.io/name: vllm-gke  # Selector ONLY matches chart name!
     ```
  3. **Trace the Root Cause**: The Service selector does not isolate by Helm Release Name (`app.kubernetes.io/instance`). As a result, `kube-proxy` dynamically routes requests sent to `vllm-31b-service` round-robin to **both** the 26B and 31B pods! When a 31B (Dense) request lands on the 26B (MoE) pod, vLLM returns a `404 Not Found` because it is not hosting that model.
* **Resolution**:
  1. Edit [blueprints/vllm-gke/templates/service.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/blueprints/vllm-gke/templates/service.yaml) and ensure the `selector` block strictly enforces the release instance variable to isolate traffic:
     ```yaml
     selector:
       app.kubernetes.io/name: {{ include "vllm.name" . }}
       app.kubernetes.io/instance: {{ .Release.Name }}  # Crucial for pod affinity!
     ```
  2. Re-deploy both Helm chart instances. The updated service descriptors will bind traffic solely to their corresponding pods:
     ```bash
     helm upgrade --install vllm-26b ./blueprints/vllm-gke -n gemma-inference --set model.servedModelName="gemma4:26b"
     helm upgrade --install vllm-31b ./blueprints/vllm-gke -n gemma-inference --set model.servedModelName="gemma4:31b"
     ```

### Case Study 3: Storage Provisioner Deadlock & PVC Access Mode Mismatch
* **The Scenario**: An operator is transitioning a model serving release between a single-node testing sandbox (using GKE dynamic local block SSDs) and GDC-ag production (using central SAN disk pools). During the transition or a size adjustment, the Helm release upgrade aborts or the pods refuse to schedule.
* **The Symptoms**: 
  1. Helm upgrades crash with:
     `Error: cannot patch "vllm-26b-vllm-gke-weights" with kind PersistentVolumeClaim: spec.resources.requests.storage: field is immutable`
  2. Attempting to manually delete the PVC leaves it permanently stuck in the `Terminating` status.
  3. Re-running Helm setup produces scheduling deadlocks:
     `0/2 nodes are available: persistentvolumeclaim "vllm-26b-vllm-gke-weights" is being deleted: not found`.
* **Step-by-Step Diagnosis**:
  1. **Check PVC Status**: Query the cluster storage claims in your namespace:
     ```bash
     kubectl get pvc -n gemma-inference
     ```
     Observe that the target volume claim is stuck in `Terminating`:
     ```text
     NAME                        STATUS        VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
     vllm-26b-vllm-gke-weights   Terminating   pvc-xyz  100Gi      RWO            standard-rwo   2d
     ```
  2. **Inspect PVC Description**: Run `kubectl describe pvc vllm-26b-vllm-gke-weights -n gemma-inference` and observe the **Finalizers** block:
     ```yaml
     metadata:
       finalizers:
       - kubernetes.io/pvc-protection
     ```
     And under the **Events** log:
     ```text
     Warning  ProvisioningFailed  5s  volume.kubernetes.io/provisioner  storageclass.storage.k8s.io "standard-rwx" not found
     ```
  3. **Trace the Root Cause**:
     - **Finalizer Deadlock**: Kubernetes native safety controller adds the `kubernetes.io/pvc-protection` finalizer to prevent volume data corruption while pods are using a volume. When the Helm release is uninstalled or re-rendered, the finalizer prevents volume deletion because the old pods are still gracefully terminating or the dynamic CSI driver is deadlocked. This blocks Helm from re-creating the volume under a new layout!
     - **Access Mode & Class Mismatches**: If deploying a manifest compiled for GDC production (`storageClassName: standard-rwx`, `accessModes: [ReadWriteMany]`) inside a standard GKE sandbox, the cloud dynamic provisioner aborts because the `standard-rwx` StorageClass does not exist and GKE persistent disks strictly reject `ReadWriteMany` multi-writer bonds.
* **Resolution**:
  1. **Forcibly Clear PVC Finalizers**: Force Kubernetes to release the stale PV bonds and instantly clear the terminating deadlock by wiping the finalizer block:
     ```bash
     kubectl patch pvc vllm-26b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge
     ```
     *(Repeat for the 31B volume claim if necessary)*:
     ```bash
     kubectl patch pvc vllm-31b-vllm-gke-weights -n gemma-inference -p '{"metadata":{"finalizers":null}}' --type=merge
     ```
  2. **Verify Active Storage Classes**: Query the active storage classes present in the environment:
     ```bash
     kubectl get storageclass
     ```
  3. **Align Helm Parameter Capabilities**:
     - **For Sandboxed Emulation**: Override values to enforce single-writer block allocations:
       ```bash
       --set persistence.storageClassName="standard-rwo" \
       --set persistence.accessModes={ReadWriteOnce}
       ```
     - **For GDC Production**: Enforce GDC air-gapped high-availability SAN mounts:
       ```bash
       -f ./blueprints/vllm-gke/values-gdc.yaml
       ```

---

## 6. Essential Kubernetes Operations Cheatsheet

Use these standard administrative commands to monitor and maintain the gateway stack in production:

### 1. Monitoring Pods & Rollouts
```bash
# List all pods in the namespace
kubectl get pods -n gemma-inference

# Watch pod status transitions live
kubectl get pods -n gemma-inference -w

# Verify the status of a proxy rollout
kubectl rollout status deployment/gemma-gateway -n gemma-inference
```

### 2. Dynamic Storage Checks
```bash
# List active PersistentVolumeClaims
kubectl get pvc -n gemma-inference

# Inspect detailed storage errors on a pending volume
kubectl describe pvc vllm-26b-vllm-gke-weights -n gemma-inference
```

### 3. Log Diagnostics
```bash
# Stream proxy gateway logs
kubectl logs -f deployment/gemma-gateway -n gemma-inference

# Stream model server logs
kubectl logs -f deployment/vllm-26b-vllm-gke -c vllm -n gemma-inference

# Inspect logs from a previously crashed pod instance
kubectl logs pod/<CRASHING_POD_NAME> -c vllm -n gemma-inference -p
```

### 4. Hardened DevSecOps Diagnostics
Because our production and staging containers are hardened and stripped of shells, curl, or busybox utilities for security, you cannot exec directly into a pod to run networking tests. 

To perform connection checks internally, run Python's native `urllib` library directly inside the gateway container to test backend services:
```bash
# Test connectivity and fetch active models from the Ollama backend service
kubectl exec -it deployment/gemma-gateway -n gemma-inference -- python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://ollama-26b-service:11434/api/tags').read().decode())"

# Test connectivity to the vLLM backend service
kubectl exec -it deployment/gemma-gateway -n gemma-inference -- python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://vllm-26b-service:8000/v1/models').read().decode())"
```
