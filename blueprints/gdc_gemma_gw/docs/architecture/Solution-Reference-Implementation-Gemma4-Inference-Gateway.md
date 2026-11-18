Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Gemma 4 Dedicated Inference Gateway on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Gemma 4 Dedicated Inference Gateway (`GCPS-20`)** on Google Distributed Cloud (GDC) air-gapped environments. The gateway is a high-performance, OpenAI-compatible Layer 7 (L7) routing proxy and control plane (FastAPI) that dynamically routes incoming client and agent queries to either the latency-optimized **Gemma 4 26B A4B (MoE)** or the reasoning-optimized **Gemma 4 31B (Dense)** backend serving pools. By combining context-aware prompt classification, federated Keycloak OIDC authentication, and optional KV-cache-aware pod selection across multi-replica GPU pools via Envoy AI Gateway and the Kubernetes Gateway API Inference Extension, the gateway maximizes hardware utilization across GDC-ag GPU nodes.

## **Architecture**

The architecture consists of a multi-replica **Gemma 4 Gateway Proxy (`gemma-gateway`)** deployment exposed via standard **Kubernetes Gateway API** resources (`Gateway`, `HTTPRoute`) bound to a platform-configured `GatewayClass` (`gdc-platform-gateway`). The proxy authenticates callers via **Keycloak OIDC (`GCPS-12`)** or API keys, classifies prompt complexity on the isolated user turn, normalizes payloads, and routes `/v1/chat/completions` requests either through the **Envoy AI Gateway & Gateway API Inference Extension (`gemma-envoy-inference-pool`)** for per-user token rate limiting and KV-cache-aware Endpoint Picker (`epp`) pod scoring, or directly over internal KubeDNS to the underlying **vLLM** (production) or **Ollama** (sandbox) serving engines running on NVIDIA H200, H100, or A100 GPU node pools.

```
         [ Downstream Clients & AI Blueprints: GCPS-20a, GCPS-13, GCPS-06, GCPS-07 ]
                                              │
                                              ▼
                 [ GDC PLATFORM HLB / KUBERNETES GATEWAY API ]
                   Gateway: gdc-platform-gateway | HTTPRoute: gemma-gateway-route
                   Host: gemma-gateway.shared-services.gdc.local (TLS: gdc-ca-issuer)
                                              │
                                              ▼
  ┌──────────────────────┐      ┌───────────────────────────┐      ┌──────────────────────┐
  │ Keycloak OIDC SSO    │◄────►│  Gemma 4 Gateway Proxy    │◄────►│ Shared State &       │
  │ (GCPS-12, /auth/)    │ OIDC │  (FastAPI Control Plane)  │Sync  │ Telemetry            │
  │ • PKCE & JWKS RS256  │ JWKS │  • Context-Aware Router   │State │ • Atomic File / Redis│
  │ • RBAC (admin/user)  │      │  • Payload Normalizer     │      │ • vLLM / DCGM Metrics│
  └──────────────────────┘      │  • Admin Control Plane (/)│      └──────────────────────┘
                                └─────────────┬─────────────┘
                                              │ (X-User-ID & x-ai-eg-model)
                                              ▼
                 ┌─────────────────────────────────────────────────────────┐
                 │ [Optional Scale-Out L7 Data Plane]                      │
                 │ Envoy AI Gateway & Gateway API Inference Extension      │
                 │ • AIGatewayRoute & BackendTrafficPolicy (Token Limiter) │
                 │ • InferencePool + Endpoint Picker (vllm-26b/31b-epp)    │
                 │   Scorers: Prefix-Cache (3), KV-Cache (2), Queue (2)    │
                 └──────────────┬───────────────────────────┬──────────────┘
                                │                           │
             (Conversational / Priority: 100)    (Complex / Code / Math / SQL / Priority: 50)
                                ▼                           ▼
                 ┌────────────────────────────┐ ┌────────────────────────────┐
                 │ Tier 1: Gemma 4 26B (MoE)  │ │ Tier 2: Gemma 4 31B (Dense)│
                 │ pool: gpu-moe (H200/H100)  │ │ pool: gpu-dense (H200/H100)│
                 │ vllm-26b / ollama-26b      │ │ vllm-31b / ollama-31b      │
                 │ (vllm-26b-vllm-gke-service)│ │ (vllm-31b-vllm-gke-service)│
                 └──────────────┬─────────────┘ └─────────────┬──────────────┘
                                └──────────────┬──────────────┘
                                               ▼
                 [ GDC SAN Shared Storage (standard-rwx PVCs) & Harbor Registry ]
```

### **Key Solution Capabilities**

* **Context-Aware Prompt Classification & Model Tiering**: Dynamically analyzes the latest user query turn while stripping injected RAG `<context>` blocks, system directives, and benign conversational idioms so retrieved document context does not skew routing. Standard conversational queries route to the low-latency **Gemma 4 26B A4B (MoE)** backend (`pool: gpu-moe`, `priority: 100`), while code generation, SQL synthesis, mathematical proofs, and multi-step reasoning tasks route to the reasoning-optimized **Gemma 4 31B (Dense)** backend (`pool: gpu-dense`, `priority: 50`). Supports explicit model overrides (`gemma4:26b`, `gemma4:31b`, `auto`) and routing headers (`X-Task-Complexity`, `X-Model-Tier`).
* **Telemetry-Driven GPU Pod Selection & Per-User Token Rate Limiting**: Integrates with **Envoy AI Gateway** (`AIGatewayRoute`, `BackendTrafficPolicy`) and the **Kubernetes Gateway API Inference Extension** (`InferencePool`, `InferenceObjective`, and `epp` Endpoint Picker `v1.3.0`) to score multi-replica vLLM pods using live Prometheus metrics (`prefix-cache-scorer` weight `3`, `kv-cache-utilization-scorer` weight `2`, `queue-scorer` weight `2`) and enforce per-user hourly token budgets (`llm_total_tokens` via `X-User-ID`), with automatic fail-safe fallback to direct KubeDNS service routing.
* **Federated Keycloak OIDC Authentication & RBAC**: Integrates with centralized **Keycloak (`GCPS-12`)** (`gdc-rag-realm`) for OIDC Authorization Code Flow with PKCE (`S256`), `/auth/` reverse-proxying, RS256 JWKS Bearer JWT verification, and role-based access control (`admin` and `user` roles).
* **Drop-in OpenAI Compatibility & Payload Normalization**: Exposes a standard, rootless `/v1/chat/completions` endpoint (`runAsNonRoot: true`, UID `1000`), normalizing `<thought>` reasoning blocks in SSE streams, flattening `system`-role messages when required by target backends, and preserving deterministic agent overrides (`temperature=0.0`, `X-Preserve-Client-Params`).
* **Flexible Serving Backends (vLLM & Ollama)**: Configured to support high-throughput, production-grade serving via **vLLM** (using PagedAttention, prefix caching, chunked prefill, 32K context windows, and multi-GPU tensor parallelism on NVIDIA H200 141GB or H100/A100 80GB GPUs) alongside pre-baked **Ollama** containers for developer sandboxes and staging environments.
* **GDC Air-Gapped Sovereignty & GPU Isolation**: Adheres to strict GDC-ag isolated constraints (`HF_HUB_OFFLINE=1`)—all container images are sideloaded into the local Harbor registry, model weights are persisted locally on GDC SAN StorageClasses (`standard-rwx`), and node selectors (`pool: cpu`, `pool: gpu-moe`, `pool: gpu-dense`), taints (`nvidia.com/gpu:NoSchedule`), and `ProjectNetworkPolicy` rules isolate GPU inference pools from stateless workloads.

### **Unified Admin Control Plane**

The Gemma 4 Gateway Proxy serves an interactive, OIDC RBAC-protected HTML **Admin Control Plane** (served directly at the root `/` URL path of the gateway) alongside its REST administration APIs, backed by multi-pod state synchronization (`GATEWAY_STATE_FILE` atomic file locking or Redis):

1. **Dynamic Parameter Configuration (`POST /api/config`)**:
   - Adjusts default generation parameters globally at runtime, including **Temperature**, **Top-P**, **Frequency Penalty**, and **`enforce_parameter_overrides`** (with one-click reset to auto defaults).
   - Adjusts GDC-ag specific **Vision Token Budgets** for multimodal workloads (supporting variable budget resolution selections: `70`, `140`, `280`, `560`, or `1120` tokens).
   - Hot-swaps the default model variant routing target (`26b`, `31b`, or `auto`).

2. **In-Flight Traffic Control & Session Termination (`POST /api/sessions/{session_id}/kill`)**:
   - Logs and monitors active user chat sessions and real-time generation status across gateway replicas.
   - Provides an administrative kill-switch to immediately disconnect and terminate active generation streams in-flight.

3. **User Blocklist Management (`POST /api/users/{user_id}/block`)**:
   - Allows administrators to block or unblock users by ID across all gateway pods.
   - Automatically drops active sessions and rejects subsequent API calls from blocked client IDs.

4. **Real-Time Upstream GPU & Gateway Telemetry (`GET /api/metrics`)**:
   - Scrapes live Prometheus metrics from upstream vLLM pods (`/metrics`), NVIDIA DCGM Exporter (`DCGM_METRICS_URL`), or Ollama (`/api/ps`) to report real-time GPU/VRAM utilization, KV-cache saturation, active session counts, and token throughput.

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* User cluster created with GPU-enabled node pools and sufficient GPU memory.
* Minimum of 1 NVIDIA A100 (80GB) GPU for the 26B MoE model; minimum of 2 NVIDIA A100 (80GB) GPUs for the 31B Dense model.
* Harbor container registry instance available and accessible.
* All required container images (vLLM serving, NGINX sidecar, Gateway proxy) packaged and sideloaded into your local GDC-ag registry. See **[Air-Gapped Packaging & Sideloading Guide](../operations/sideloading-guide.md)** for detailed export/import steps.
* `kubectl` and `gdcloud` CLIs configured to access the user cluster.
* Docker client installed and configured on the workstation to push to Harbor.
* Necessary IAM permissions granted (e.g., Namespace Admin, Cluster Developer).
* Hugging Face account and authentication token configured for weights download.

# Section 1: Common Setup

## 1.1 Create Image Pull Secret

To configure an image pull secret for a container workload in GDC air-gapped, you need to create a Kubernetes `docker-registry` secret containing credentials to access your private Harbor project. This secret is then referenced in your deployment specification.

You should use a Harbor robot account for programmatic access to images in private Harbor projects.

Follow these steps to configure the image pull secret:

**Create a Harbor Robot Account:**

* Navigate to your Harbor instance UI.
* Go to your Harbor project.
* Select the "Robot Accounts" tab.
* Click "+ NEW ROBOT ACCOUNT".
* Give it a name (e.g., gemma-puller) and grant it the necessary permissions (at least "pull" access) until an expiration time.
* Securely store the robot account name (e.g., `robot$gemma-puller`) and the secret token provided.

**Authenticate Docker to Harbor:**

On your machine with Docker installed and network access to the Harbor registry, log in using the robot account credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$gemma-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-account-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```

**Create the Kubernetes Image Pull Secret:**

Use `kubectl` to create a secret of type `docker-registry` in your project namespace, using the Docker configuration file updated in the previous step:

```shell
# Login into GDC air-gapped
gdcloud auth login --login-config-cert /path/to/web-tls-cert.pem
gdcloud clusters get-credentials user-cluster-1
kubectl config set-context --current --namespace=gemma-inference

export SECRET_NAME="gemma-pull-secret" # You can select an alternative name 
export NAMESPACE="gemma-inference"
export DOCKER_CONFIG_PATH="$HOME/.docker/config.json"

kubectl create secret docker-registry ${SECRET_NAME} \
      --from-file=.dockerconfigjson=${DOCKER_CONFIG_PATH} \
      -n ${NAMESPACE}
```

## 1.2 Base Cluster CPU & GPU Resource Requirements

To successfully run both the **Gemma 4 Dedicated Inference Gateway** (including vLLM/Ollama model serving engines) and the **Gemma 4 Client Application** (including the frontend, backend, Keycloak, and database services), your GDC base cluster must be provisioned with sufficient compute and acceleration resources.

The tables below provide the detailed breakdown of CPU, RAM, and GPU requirements for all components of the stack.

### 1.2.1. Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | GPU Required (per Pod) | Storage / PVC |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **Inference Gateway Proxy** | 2 | 100m (500m) | 128Mi (512Mi) | None | None |
| **vLLM MoE (26B)** | 1 | 8 (8) | 32Gi (64Gi) | 1 x A100/H100 (80GB) | 120Gi PVC |
| **vLLM Dense (31B)** | 1 | 16 (16) | 64Gi (128Gi) | 2 x A100/H100 (80GB)* | 150Gi PVC |
| **Client Frontend** | 2 | 100m (500m) | 128Mi (256Mi) | None | None |
| **Client Backend** | 2 | 200m (1) | 256Mi (1Gi) | None | None |
| **Keycloak SSO** | 1 | 500m (1) | 1Gi (2Gi) | None | None |
| **Managed DB (PostgreSQL)** | 1 | 2 (2) | 8Gi (8Gi) | None | 50Gi PVC |

> [!NOTE]
> \* **GPU requirements for Gemma 4 31B (Dense)**: Running this model under vLLM using unquantized FP16 weights requires a minimum of **2x NVIDIA A100/H100 (80GB)** GPUs due to model size and tensor parallelism requirements. Alternatively, a single **NVIDIA H200 (141GB)** can serve the model.

### 1.2.2. Recommended Node Pool Configurations

To ensure zonal high availability (HA) and avoid resource contention, configure two separate node pools in the user cluster:

#### 1. GPU Accelerator Node Pool (Inference Serving Workloads)
* **Purpose**: Dedicated to hosting GPU-intensive model serving deployments (`vllm-26b` and `vllm-31b`).
* **Node Type**: GPU-equipped host servers (e.g., `a2-highgpu-1g` / `hgx-h100-1g` or GDC air-gapped equivalent physical nodes).
* **Recommended Capacity**:
  - **Minimum for Dual-Model Serving**: 3x NVIDIA A100/H100 (80GB) GPUs.
  - **System Memory per Node**: At least 128Gi RAM and 16 vCPUs per GPU host to prevent CPU/RAM starvation.
* **Taints & Tolerations**: Apply a taint (`nvidia.com/gpu:NoSchedule`) to prevent non-GPU workloads from scheduling on these expensive nodes.

#### 2. Standard Compute Node Pool (Stateless & Database Workloads)
* **Purpose**: Hosts the Gateway Proxy, Client Frontend, Client Backend, Keycloak, and the Managed Database.
* **Recommended Instance Type**: Minimum of 2 nodes of type **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node) or equivalent.
* **Total Resource Pool**: 16 vCPUs, 64Gi RAM, and standard SSD-backed persistent storage.
* **High Availability**: Spreading workloads across at least 2 compute nodes ensures that frontend/backend replicas are distributed across different nodes to withstand a single-node failure without downtime.

### 1.2.3. Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

In Google Distributed Cloud (GDC) air-gapped environments, GKE user clusters and node pools are provisioned by Platform Administrators (PAs) using `kubectl` against the zonal Management API server (`MANAGEMENT_API_SERVER`).

Depending on your organizational topology, select one of the following deployment paths:

#### Option A: Using an Existing Shared Cluster or Creating a New One
For multi-tenant environments, you can use an existing shared cluster or create a new one that meets the resource requirements of both the gateway and the client application. Shared clusters span multiple GDC projects. GDC projects must be explicitly bound to the cluster using a `ProjectBinding` resource before application workloads can be deployed.

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**

```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: gemma-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100 # Replace with your target GDC-ag version
  nodePools:
  # 1. Standard Node Pool for Gateway Proxy, Keycloak, Frontend, Backend, and DB workloads
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc # Sized at 8 vCPUs, 32G RAM per node
    nodeCount: 2
    labels:
      pool: cpu
  # 2. GPU Node Pool for Gemma 4 26B MoE serving workloads (1x A100 80GB)
  - name: gpu-moe-pool
    machineTypeName: a2-ultragpu-1g-gdc # Predefined GDC-ag machine type with 1x A100 80GB
    nodeCount: 1
    labels:
      pool: gpu-moe
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  # 3. GPU Node Pool for Gemma 4 31B Dense serving workloads (2x A100 80GB)
  - name: gpu-dense-pool
    machineTypeName: a2-ultragpu-2g-gdc # Predefined GDC-ag machine type with 2x A100 80GB
    nodeCount: 1
    labels:
      pool: gpu-dense
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Create the Project Binding YAML (`project-binding.yaml`):**

To authorize client applications in your project namespace (e.g., `gemma-inference`) to access resources on the shared cluster, you must create a `ProjectBinding` resource in the `platform` namespace:

```yaml
apiVersion: resourcemanager.gdc.goog/v1
kind: ProjectBinding
metadata:
  name: gemma-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: gemma-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - gemma-inference # Name of your GDC project/namespace
```

**3. Apply the Manifests using the Zonal Management Kubeconfig:**

```shell
# Set the environment variable to your zonal management API server's kubeconfig path
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"

# Apply cluster and binding configurations
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster (Single-Tenant/Self-Contained Workload)
Standard clusters are isolated, single-tenant clusters scoped directly to a specific GDC project namespace.

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**

```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: gemma-standard-cluster
  namespace: gemma-inference # Provisioned directly inside the project namespace
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100 # Replace with your target GDC-ag version
  nodePools:
  # 1. Standard Node Pool for Gateway Proxy, Keycloak, Frontend, Backend, and DB workloads
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 2
    labels:
      pool: cpu
  # 2. GPU Node Pool for Gemma 4 26B MoE serving workloads (1x A100 80GB)
  - name: gpu-moe-pool
    machineTypeName: a2-ultragpu-1g-gdc
    nodeCount: 1
    labels:
      pool: gpu-moe
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  # 3. GPU Node Pool for Gemma 4 31B Dense serving workloads (2x A100 80GB)
  - name: gpu-dense-pool
    machineTypeName: a2-ultragpu-2g-gdc
    nodeCount: 1
    labels:
      pool: gpu-dense
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Apply the Manifest using the Zonal Management Kubeconfig:**

```shell
# Set the environment variable to your zonal management API server's kubeconfig path
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"

# Apply the cluster configuration directly in the project namespace
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.2.4. Workload Pod Assignment & Scheduling Configuration

To ensure workloads are scheduled onto the correct node pools and avoid resource contention (such as running stateless CPU containers on expensive GPU hardware), configure `nodeSelector` and `tolerations` in your Kubernetes deployment manifests:

1. **Stateless Gateway & Client Workloads** (Proxy, keycloak, frontend, backend):
   Enforce scheduling on standard compute nodes:
   ```yaml
   spec:
     template:
       spec:
         nodeSelector:
           pool: cpu
   ```

2. **Gemma 4 26B MoE Serving Workload** (`vllm-26b`):
   Schedule onto the 1-GPU node pool and tolerate the GPU node taints:
   ```yaml
   spec:
     template:
       spec:
         nodeSelector:
           pool: gpu-moe
         tolerations:
         - key: "nvidia.com/gpu"
           operator: "Exists"
           effect: "NoSchedule"
   ```

3. **Gemma 4 31B Dense Serving Workload** (`vllm-31b`):
   Schedule onto the 2-GPU node pool and tolerate the GPU node taints:
   ```yaml
   spec:
     template:
       spec:
         nodeSelector:
           pool: gpu-dense
         tolerations:
         - key: "nvidia.com/gpu"
           operator: "Exists"
           effect: "NoSchedule"
   ```

# Section 2: Deploying with vLLM

For high-throughput GDC-ag production environments, the model engines are deployed via the **vLLM** PagedAttention serving stack.

## 2.1 Get the vLLM Docker Image

On a machine with internet access, pull the vLLM Docker image and then transfer it to your Harbor project:

```shell
# Pull and Tag vLLM (v0.4.2 recommended for stability)
docker pull vllm/vllm-openai:v0.4.2
docker tag vllm/vllm-openai:v0.4.2 harbor.shared-services.gdc.local/gemma-project/vllm-openai:v0.4.2
docker push harbor.shared-services.gdc.local/gemma-project/vllm-openai:v0.4.2
```

## 2.2 Prepare Model Weights in PVCs

Create a storage configuration file for model weight persistence (`vllm-storage-claims.yaml`):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vllm-26b-weights-pvc
  namespace: gemma-inference
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 120Gi
  storageClassName: standard-rwx
  volumeMode: Filesystem
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vllm-31b-weights-pvc
  namespace: gemma-inference
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 150Gi
  storageClassName: standard-rwx
  volumeMode: Filesystem
```

Apply the PVCs:
```shell
kubectl apply -f vllm-storage-claims.yaml
```

Download the weights from Hugging Face on your internet-connected machine:
```shell
huggingface-cli login --token <YOUR_HF_TOKEN>
huggingface-cli download google/gemma-4-26B-A4B-it --local-dir ./gemma-4-26B-A4B-it-weights
huggingface-cli download google/gemma-4-31B-it --local-dir ./gemma-4-31B-it-weights

# Compress weights for migration
tar -czf gemma-4-26B-A4B-it-weights.tar.gz ./gemma-4-26B-A4B-it-weights
tar -czf gemma-4-31B-it-weights.tar.gz ./gemma-4-31B-it-weights
```

Deploy a helper staging pod (`helper-pod.yaml`) to receive and extract the weights:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: model-uploader
  namespace: gemma-inference
spec:
  containers:
  - name: uploader
    image: harbor.shared-services.gdc.local/gemma-project/busybox:latest
    command: ["sleep", "3600"]
    volumeMounts:
    - name: model-26b
      mountPath: /mnt/vllm-26b
    - name: model-31b
      mountPath: /mnt/vllm-31b
  imagePullSecrets:
  - name: gemma-pull-secret
  volumes:
  - name: model-26b
    persistentVolumeClaim:
      claimName: vllm-26b-weights-pvc
  - name: model-31b
    persistentVolumeClaim:
      claimName: vllm-31b-weights-pvc
```

Apply the pod and copy files:
```shell
kubectl apply -f helper-pod.yaml

# Wait for pod to be running
kubectl wait --for=condition=Ready pod/model-uploader -n gemma-inference

# Copy compressed weights directly into persistent volumes
kubectl cp gemma-4-26B-A4B-it-weights.tar.gz gemma-inference/model-uploader:/mnt/vllm-26b/
kubectl cp gemma-4-31B-it-weights.tar.gz gemma-inference/model-uploader:/mnt/vllm-31b/

# Extract files inside the helper pod
kubectl exec -it model-uploader -n gemma-inference -- tar -xzf /mnt/vllm-26b/gemma-4-26B-A4B-it-weights.tar.gz -C /mnt/vllm-26b/
kubectl exec -it model-uploader -n gemma-inference -- tar -xzf /mnt/vllm-31b/gemma-4-31B-it-weights.tar.gz -C /mnt/vllm-31b/

# Clean up compressed tarballs and the helper pod
kubectl exec -it model-uploader -n gemma-inference -- rm /mnt/vllm-26b/gemma-4-26B-A4B-it-weights.tar.gz
kubectl exec -it model-uploader -n gemma-inference -- rm /mnt/vllm-31b/gemma-4-31B-it-weights.tar.gz
kubectl delete pod model-uploader
```

## 2.3 Deploy vLLM Backend

Create the deployment file `vllm-serving-deployments.yaml` containing both the MoE and Dense pools:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-26b
  namespace: gemma-inference
  labels:
    app: vllm-26b
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-26b
  template:
    metadata:
      labels:
        app: vllm-26b
    spec:
      nodeSelector:
        pool: gpu-moe
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
      volumes:
      - name: weights-volume
        persistentVolumeClaim:
          claimName: vllm-26b-weights-pvc
      containers:
      - name: vllm-container
        image: harbor.shared-services.gdc.local/gemma-project/vllm-openai:v0.4.2
        args: [
          "--model", "/models/gemma-4-26B-A4B-it-weights",
          "--served-model-name", "gemma4:26b",
          "--enforce-eager",
          "--max-model-len", "8192"
        ]
        env:
        - name: HF_HUB_OFFLINE
          value: "1"
        - name: BORINGSSL_FIPS
          value: "0"
        ports:
        - containerPort: 8000
        resources:
          limits:
            nvidia.com/gpu: 1
            cpu: "8"
            memory: "64Gi"
          requests:
            nvidia.com/gpu: 1
            cpu: "8"
            memory: "32Gi"
        volumeMounts:
        - name: weights-volume
          mountPath: /models
      imagePullSecrets:
      - name: gemma-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-26b-service
  namespace: gemma-inference
spec:
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  selector:
    app: vllm-26b
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-31b
  namespace: gemma-inference
  labels:
    app: vllm-31b
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-31b
  template:
    metadata:
      labels:
        app: vllm-31b
    spec:
      nodeSelector:
        pool: gpu-dense
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
      volumes:
      - name: weights-volume
        persistentVolumeClaim:
          claimName: vllm-31b-weights-pvc
      containers:
      - name: vllm-container
        image: harbor.shared-services.gdc.local/gemma-project/vllm-openai:v0.4.2
        args: [
          "--model", "/models/gemma-4-31B-it-weights",
          "--served-model-name", "gemma4:31b",
          "--enforce-eager",
          "--max-model-len", "8192"
        ]
        env:
        - name: HF_HUB_OFFLINE
          value: "1"
        - name: BORINGSSL_FIPS
          value: "0"
        ports:
        - containerPort: 8000
        resources:
          limits:
            nvidia.com/gpu: 2  # Needs 2 GPUs for Dense model routing
            cpu: "16"
            memory: "128Gi"
          requests:
            nvidia.com/gpu: 2
            cpu: "16"
            memory: "64Gi"
        volumeMounts:
        - name: weights-volume
          mountPath: /models
      imagePullSecrets:
      - name: gemma-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-31b-service
  namespace: gemma-inference
spec:
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  selector:
    app: vllm-31b
```

Apply serving manifests:
```shell
kubectl apply -f vllm-serving-deployments.yaml
```

## 2.4 Deploying serving blueprints using Helm (Alternative Production Path)

In production GDC air-gapped racks, Helm is the preferred packaging standard. If deploying using the provided Helm charts instead of manual `kubectl` manifests, follow these instructions:

```shell
# 1. Deploy GDC Production Release A (26B MoE - Latency Optimized)
helm upgrade --install vllm-26b ./blueprints/vllm-gke -n gemma-inference \
  -f ./blueprints/vllm-gke/values-gdc.yaml \
  --set persistence.existingClaim="vllm-26b-weights-pvc" \
  --set model.name="/models/gemma-4-26B-A4B-it-weights" \
  --set model.servedModelName="gemma4:26b" \
  --set resources.limits."nvidia.com/gpu"=1

# 2. Deploy GDC Production Release B (31B Dense - Reasoning Optimized)
helm upgrade --install vllm-31b ./blueprints/vllm-gke -n gemma-inference \
  -f ./blueprints/vllm-gke/values-gdc.yaml \
  --set persistence.existingClaim="vllm-31b-weights-pvc" \
  --set model.name="/models/gemma-4-31B-it-weights" \
  --set model.servedModelName="gemma4:31b" \
  --set resources.limits."nvidia.com/gpu"=2 \
  --set nodeSelector.pool="gpu-dense"
```

> [!WARNING]
> **Service Naming Convention Discrepancy:**
> * **Helm Deployments**: The GDC Helm chart dynamically generates service names in the format `<ReleaseName>-<ChartName>-service`. Therefore, the commands above will spin up services named **`vllm-26b-vllm-gke-service`** and **`vllm-31b-vllm-gke-service`**.
> * **Manual Manifest Deployments**: The raw YAML files in Section 2.3 spin up services named exactly **`vllm-26b-service`** and **`vllm-31b-service`**.
> * **Operator Action**: When configuring the `MODEL_ROUTING_CONFIG` environment variable in the Inference Gateway Proxy (Section 4), you **must** update the target hostnames to match your chosen deployment path. If using Helm, set the routing endpoints to target the `-vllm-gke-service` DNS suffixes.

## 2.5 Configure Network Policy

Apply a `ProjectNetworkPolicy` to restrict and secure access to the vLLM backends. Create `vllm-netpol.yaml`:

```yaml
apiVersion: networking.gdc.goog/v1
kind: ProjectNetworkPolicy
metadata:
  name: allow-vllm-routing-ingress
  namespace: gemma-inference
spec:
  subject:
    subjectType: UserWorkload
  policyType: Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: gemma-gateway
    ports:
    - protocol: TCP
      port: 8000
```

Apply the policy:
```shell
kubectl apply -f vllm-netpol.yaml
```

# Section 3: Deploying with Ollama

Ollama serves as the fallback engine for dev/testing clusters where GPU capacity is constrained. To enable prompt classification and routing verification under Ollama, both the 26B and 31B model variants must be deployed to separate pods with dedicated services.

## 3.1 Pre-Baked Images Setup (Ollama-Baked)

To maintain strict network isolation or provide quick startup times for 1–10 users, model weights are fully baked directly into the container image layers. This avoids dynamic volume mounts and simplifies sideloading in GDC.

The repository includes pre-configured Dockerfiles under `gateway/ollama-baked/` to build these baked images:
*   `gateway/ollama-baked/Dockerfile.26b`: Pre-bakes the Gemma 4 26B MoE weights.
*   `gateway/ollama-baked/Dockerfile.31b`: Pre-bakes the Gemma 4 31B Dense weights.

## 3.2 Build and Push Images

On your internet-connected packaging workstation, navigate to the repository root and build the baked container images:

```shell
export REGISTRY_HOST="harbor.shared-services.gdc.local/gemma-project"

# 1. Build and Push 26B MoE baked image
docker build -t ${REGISTRY_HOST}/ollama-gemma-26b:latest \
  --build-arg MODEL_TAG="gemma4:26b" \
  -f gateway/ollama-baked/Dockerfile.26b \
  gateway/ollama-baked

docker push ${REGISTRY_HOST}/ollama-gemma-26b:latest

# 2. Build and Push 31B Dense baked image
docker build -t ${REGISTRY_HOST}/ollama-gemma-31b:latest \
  --build-arg MODEL_TAG="gemma4:31b" \
  -f gateway/ollama-baked/Dockerfile.31b \
  gateway/ollama-baked

docker push ${REGISTRY_HOST}/ollama-gemma-31b:latest
```

*(Note: If you are automating this, you can execute the `./scripts/build-and-push.sh` script to build and push the proxy and both baked images dynamically.)*

## 3.3 Deploy Ollama Backends

Create `ollama-serving.yaml` to deploy both model backends concurrently:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-26b
  namespace: gemma-inference
  labels:
    app: ollama-26b
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama-26b
  template:
    metadata:
      labels:
        app: ollama-26b
    spec:
      nodeSelector:
        pool: gpu-moe
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
      containers:
      - name: ollama
        image: harbor.shared-services.gdc.local/gemma-project/ollama-gemma-26b:latest
        env:
        - name: OLLAMA_HOST
          value: "0.0.0.0"
        ports:
        - containerPort: 11434
        resources:
          limits:
            nvidia.com/gpu: 1
            cpu: "8"
            memory: "32Gi"
          requests:
            nvidia.com/gpu: 1
            cpu: "8"
            memory: "16Gi"
      imagePullSecrets:
      - name: gemma-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: ollama-26b-service
  namespace: gemma-inference
spec:
  ports:
  - port: 11434
    targetPort: 11434
    protocol: TCP
  selector:
    app: ollama-26b
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-31b
  namespace: gemma-inference
  labels:
    app: ollama-31b
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama-31b
  template:
    metadata:
      labels:
        app: ollama-31b
    spec:
      nodeSelector:
        pool: gpu-dense
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
      containers:
      - name: ollama
        image: harbor.shared-services.gdc.local/gemma-project/ollama-gemma-31b:latest
        env:
        - name: OLLAMA_HOST
          value: "0.0.0.0"
        ports:
        - containerPort: 11434
        resources:
          limits:
            nvidia.com/gpu: 1
            cpu: "8"
            memory: "32Gi"
          requests:
            nvidia.com/gpu: 1
            cpu: "8"
            memory: "16Gi"
      imagePullSecrets:
      - name: gemma-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: ollama-31b-service
  namespace: gemma-inference
spec:
  ports:
  - port: 11434
    targetPort: 11434
    protocol: TCP
  selector:
    app: ollama-31b
```

Apply the deployment:
```shell
kubectl apply -f ollama-serving.yaml
```

## 3.4 Configure Network Policy

Create `ollama-netpol.yaml` to authorize ingress traffic from the gateway proxy to both Ollama service backends:

```yaml
apiVersion: networking.gdc.goog/v1
kind: ProjectNetworkPolicy
metadata:
  name: allow-ollama-routing-ingress
  namespace: gemma-inference
spec:
  subject:
    subjectType: UserWorkload
  policyType: Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: gemma-gateway
    ports:
    - protocol: TCP
      port: 11434
```

Apply the policy:
```shell
kubectl apply -f ollama-netpol.yaml
```

# Section 4: Deploying the Inference Gateway Proxy

The Python FastAPI gateway proxy acts as the dynamic router intercepting client traffic and distributing queries.

## 4.1 Build and Push Gateway Image

Build the proxy container on your staging bastion and push to the local Harbor project:

```shell
docker build -t harbor.shared-services.gdc.local/gemma-project/gemma-gateway:latest ./gateway/proxy/
docker push harbor.shared-services.gdc.local/gemma-project/gemma-gateway:latest
```

## 4.2 Deploy Gateway Manifests

Create the deployment manifest `01-gateway.yaml` mapping routing coordinates via JSON environment configs and setting up a dedicated service account:

> [!NOTE]
> **Why a Dedicated ServiceAccount is Used:**
> GDC air-gapped security policies mandate the Principle of Least Privilege. Rather than running the gateway proxy pods under the namespace's `default` service account (which may inherit unwanted permissions or default token mounts), we define a dedicated, unprivileged `ServiceAccount` (`gemma-gateway-sa`). This isolates the gateway proxy's identity and prevents it from having any administrative access inside the cluster namespace.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gemma-gateway-sa
  namespace: gemma-inference
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gemma-gateway
  namespace: gemma-inference
  labels:
    app: gemma-gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gemma-gateway
  template:
    metadata:
      labels:
        app: gemma-gateway
    spec:
      nodeSelector:
        pool: cpu
      serviceAccountName: gemma-gateway-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: gateway
        image: harbor.shared-services.gdc.local/gemma-project/gemma-gateway:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
        env:
        - name: ACTIVE_FRAMEWORK
          value: "vllm"  # Switch to "ollama" if deploying the test fallback
        - name: MODEL_ROUTING_CONFIG
          value: '{"gemma4:26b": "http://vllm-26b-service.gemma-inference.svc.cluster.local:8000", "gemma4:31b": "http://vllm-31b-service.gemma-inference.svc.cluster.local:8000", "*": "http://vllm-26b-service.gemma-inference.svc.cluster.local:8000"}'
        - name: GATEWAY_TIMEOUT
          value: "300.0"
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
      imagePullSecrets:
      - name: gemma-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: gemma-gateway
  namespace: gemma-inference
spec:
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
  selector:
    app: gemma-gateway
  type: ClusterIP
```

Apply gateway proxy:
```shell
kubectl apply -f 01-gateway.yaml
```

> [!IMPORTANT]
> **DNS Suffix Verification Reminder:**
> The `MODEL_ROUTING_CONFIG` hostnames listed in the environment variables above (`vllm-26b-service` and `vllm-31b-service`) target the manual `kubectl` manifest names.
> If you deployed your vLLM backends using the Helm path (Section 2.4), you **must** edit the routing config URLs in `01-gateway.yaml` to target the dynamic Helm service suffixes:
> * `http://vllm-26b-vllm-gke-service.gemma-inference.svc.cluster.local:8000`
> * `http://vllm-31b-vllm-gke-service.gemma-inference.svc.cluster.local:8000`

# Section 5: High-Performance Exposure (Gateway API)

To satisfy GDC air-gapped production networking requirements, legacy Kubernetes Ingress resources and raw Services of `type: LoadBalancer` are retired. Expose the `gemma-gateway` service using standard Kubernetes Gateway API resources (`Gateway`, `HTTPRoute`).

## 5.1. Provision the GDC Platform Gateway (Load Balancer)
First, ensure the `Gateway` resource bound to the platform `GatewayClass` (which provisions the platform's hardware load balancer) is created inside the namespace:

```yaml
# 02-gateway-loadbalancer.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: gdc-platform-gateway
  namespace: gemma-inference
spec:
  gatewayClassName: gdc-platform-gateway # Platform hardware load balancer class
  listeners:
  - name: http
    protocol: HTTP
    port: 80
    allowedRoutes:
      namespaces:
        from: All
```

Apply the Gateway resource:
```shell
kubectl apply -f 02-gateway-loadbalancer.yaml -n gemma-inference
```

## 5.2. Deploy the HTTPRoute
Expose the `gemma-gateway` service by binding an `HTTPRoute` mapping rule to the programmed gateway:

```yaml
# 02-gateway-httproute.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gemma-gateway-route
  namespace: gemma-inference
  labels:
    app.kubernetes.io/part-of: gemma-gateway
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: gemma-inference
  hostnames:
  - "gemma-gateway.shared-services.gdc.local"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: gemma-gateway
      port: 80
```

Apply the routing manifest:
```shell
kubectl apply -f 02-gateway-httproute.yaml -n gemma-inference
```

# Section 6: Network Isolation Security Policies

GDC namespaces restrict cross-project traffic by default. Apply a custom ingress policy allowing tenant applications (e.g. `gemma-client`) in project namespaces to access the gateway:

```yaml
# gateway-network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-tenant-ingress-to-gateway
  namespace: gemma-inference
spec:
  podSelector:
    matchLabels:
      app: gemma-gateway
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector: {}  # Opens ingress access to other GDC user namespaces
    ports:
    - protocol: TCP
      port: 8080
```

Apply policy:
```shell
kubectl apply -f gateway-network-policy.yaml
```

# Section 7: Validation

Verify endpoints, proxy logic, and dynamic backend routing.

### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute verification pod directly inside the cluster to check configuration status and API responsiveness:

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
**Expected Production Output:**
```text
===============================================
✅ PASS: Gemma 4 Inference Gateway verified!
✅ SUCCESS: Gateway proxy and configuration active
===============================================
{"active_framework": "...", "routing_targets": {...}}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

### Option B: Manual ClusterIP & Curl Verification
**1. Query Configuration Endpoint:**
```shell
export GATEWAY_IP=$(kubectl get service gemma-gateway -n gemma-inference -o jsonpath='{.spec.clusterIP}')

curl http://${GATEWAY_IP}/api/config
# Expected return:
# {"active_framework": "vllm", "routing_targets": {...}}
```

**2. Test Conversational Routing (26B MoE Target):**
```shell
curl -X POST http://${GATEWAY_IP}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4",
    "messages": [
      {"role": "user", "content": "How was your day today?"}
    ],
    "temperature": 0.7
  }'
```
Check gateway logs (`kubectl logs -l app=gemma-gateway -n gemma-inference`):
`Dynamic route resolved: gemma4:26b (Conversational threshold)`

**3. Test Complex Routing (31B Dense Target):**
```shell
curl -X POST http://${GATEWAY_IP}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4",
    "messages": [
      {"role": "user", "content": "Write a python function to execute quicksort recursively."}
    ],
    "temperature": 0.1
  }'
```
Check gateway logs:
`Complexity keyword detected in prompt. Routing to Gemma 4 31B Dense.`

# Section 8: Operations & Troubleshooting

## 8.1 Scaling

**Vertical Scaling (Hardware Optimization):**
* If generation token-lag begins to throttle under multiple streams, migrate the `vllm-31b` deployment to an NVIDIA H100 GPU node-pool.
* Ensure `gpu-memory-utilization` is configured properly (e.g., `0.90`) to reserve sufficient host RAM for serving context size extensions (256K window).

**Horizontal Scaling (Throughput):**
* Scale gateway replicas to distribute connection requests:
  `kubectl scale deployment/gemma-gateway --replicas=4 -n gemma-inference`
* Add replicas to backend serving deployments. GDC platforms automatically load-balance incoming HTTP connections across Pod endpoints.

## 8.2 Troubleshooting

| Error | Root Cause | Mitigation |
| :--- | :--- | :--- |
| `FIPS SELFTEST FAILURE` | Official vLLM images compile BoringSSL, which fails runtime FIPS checks on hardened GDC nodes. | Set `BORINGSSL_FIPS=0` and `OPENSSL_CONF=/dev/null` in container environment variables. |
| `504 Gateway Timeout` | During initial generation, context processing delays can cause downstream sockets to drop. | Set `GATEWAY_TIMEOUT="300.0"` in gateway proxy configuration env. |
| `Connection Refused` | GDC internal firewalls blocking service target ports. | Ensure `ProjectNetworkPolicy` is active in `gemma-inference` namespace to whitelist cross-namespace client calls. |
| `400 Bad Request: system role unsupported` | GKE/GDC local mock engines (e.g., Gemma 2B) do not support the system role. | The gateway proxy includes a custom interceptor that merges system instructions into user prompts and retries the call automatically. |
