Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GDC Production Serving Guide: vLLM & Gemma 4

> **Version:** 1.1

This guide details how to provision and scale the **Gemma 4 unquantized** models (`26B A4B MoE` and `31B Dense`) within the air-gapped **Google Distributed Cloud (GDC-ag)** environment using the vLLM high-performance inference engine, contrasting the serving constraints with the smaller testing environments.

> [!NOTE]
> **Sideloading Cross-Reference:**
> For complete instructions on packaging, bundling, and transferring container images and manifests across the secure air-gap perimeter, refer to the [Air-Gapped Packaging & Sideloading Guide](sideloading-guide.md).

---

## GDC Platform Prerequisites

Deploying the full **Gemma 4 Dedicated Inference Gateway** stack in production GDC air-gapped environments requires coordinating several platform resources. The gateway and its companion **Gemma Client Application** rely on these pre-requisites to enable secure multi-tenant, high-capacity serving.

> [!TIP]
> **GCP Staging & Sandbox Emulation Note:**
> If you are testing or validating this entire serving setup inside a GCP GKE development sandbox rather than a live air-gapped GDC production rack, refer to the **[GCP Quickstart Guide](quickstart_on_GCP.md)**. The guide contains the exact commands to provision the GKE GPU cluster, configure symmetrical node labels (`app=vllm-26b`, `app=vllm-31b`, `app=client`), and deploy PostgreSQL database emulation (`statefulset-postgres.yaml`).

### 1. Target GDC Shared Platform/System Cluster
* **Why?** GPU hardware cores (NVIDIA H100/A100) are the most restricted resource inside air-gapped environments. Deploying dynamic model engines inside individual Tenant/User clusters strands valuable GPU memory and causes cold-starts.
* **Constraint**: The gateway and model backends **must** be deployed in a central **Shared Cluster** (System or Platform Namespace). It operates as a central platform utility time-sharing dynamic resources across multiple client namespaces.
* **API Configuration**: The shared cluster and its GPU-enabled node pools are provisioned in the GDC management cluster namespace using the GDC cluster API (`cluster.gdc.goog/v1`).
  
  **Example: GPU NodePool Resource (`vllm-gpu-nodepool.yaml`)**
  ```yaml
  apiVersion: cluster.gdc.goog/v1
  kind: NodePool
  metadata:
    name: vllm-gpu-nodepool
    namespace: <your-project-id>
  spec:
    clusterName: shared-platform-cluster
    nodeCount: 2
    machineType: a3-highgpu-1g-gdc  # GDC H100/A100-enabled hardware type
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  ```

### 2. GDC Database Services (PostgreSQL)
* **Why?** To enable persistent multi-tenant workflows,  dynamic PostgreSQL services must be pre-provisioned.
* **Usage**:
  - **Session Caching**: Stores multi-user chat history, token analytics, and active session states.
  - **Governance Auditing**: Logs proxy metrics, classification triggers, and admin blocklist registers.
* **API Configuration**: Create the managed database instance via the `postgresql.dbadmin.gdc.goog/v1` `DBCluster` API in your project namespace.
  
  **Example: DBCluster Resource (`gemma-db-cluster.yaml`)**
  ```yaml
  apiVersion: postgresql.dbadmin.gdc.goog/v1
  kind: DBCluster
  metadata:
    name: gemma-client-db
    namespace: <your-project-id>
  spec:
    version: POSTGRESQL_14
    availabilityType: ZONAL_HA
    resources:
      requests:
        cpu: "4"
        memory: "16Gi"
    storage:
      size: "250Gi"
  ```
* **Database Schema Application (Manual)**: Because standard application workloads lack extension installation privileges inside GDC, the database operator must manually initialize the schema before deploying the client application.
  
  1. Connect to your DBCluster instance via a `psql` prompt or a temporary staging client.
  2. Apply the following SQL schema definitions:
     ```sql
     CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

     CREATE TABLE IF NOT EXISTS chats (
         id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
         user_id VARCHAR(255) NOT NULL,
         title TEXT,
         created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
         updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
     );

     CREATE TABLE IF NOT EXISTS messages (
         id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
         chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
         role VARCHAR(50) NOT NULL,
         content TEXT NOT NULL,
         created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
     );

     CREATE TABLE IF NOT EXISTS files (
         id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
         user_id VARCHAR(255),
         filename VARCHAR(255) NOT NULL,
         gcs_path TEXT NOT NULL,
         file_size_bytes BIGINT,
         content_type VARCHAR(100),
         uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
         is_shared BOOLEAN DEFAULT FALSE
     );

     CREATE INDEX idx_chats_user_id ON chats(user_id);
     CREATE INDEX idx_messages_chat_id ON messages(chat_id);
     CREATE INDEX idx_files_user_id ON files(user_id);
     ```

### 3. GDC Object Storage Buckets
* **Why?** Vision/Video multimodal workloads dynamically store media uploads and vision token payload files.
* **Usage**: S3/GCS-compatible buckets must be provisioned within the GDC project namespace.
* **CLI Configuration**: Create the storage bucket using the `gdcloud` CLI tool:
  ```bash
  gdcloud storage buckets create gs://gemma-client-files-<your-project-id> \
    --project=<your-project-id> \
    --location=<gdc-location>
  ```
* **Integration**: The client frontend and proxy gateway leverage this bucket for dynamic file caching, bypassing local disk limitations.

### 4. Gemma Client Application (Core Gateway Consumer)
* **Why?** The gateway itself is a middle-tier routing proxy. The user-facing UI and session backend reside inside **`gemma-client/`**, which is a key component of the architecture.
* **Prerequisites**:
  - **GDC IAM Permission Bindings**: GDC air-gapped environments do **not** support GCP Workload Identity. Instead, all service accounts are native GKE/GDC accounts. Access control to platform resources is authorized by binding local GDC IAM roles to the application `ServiceAccount` (`gemma-client-sa` or `gemini-gui-sa`).
    
    **CLI Method:**
    ```bash
    gdcloud iam service-accounts add-iam-policy-binding gemma-client-sa \
      --project=<your-project-id> \
      --role=roles/storage.objectAdmin
    ```
    
    **GitOps Method (`iam-policy-binding.yaml`):**
    ```yaml
    apiVersion: iam.gdc.goog/v1
    kind: IAMPolicyBinding
    metadata:
      name: gemma-client-storage-admin
      namespace: <your-project-id>
    spec:
      subjects:
      - kind: ServiceAccount
        name: gemma-client-sa
        namespace: <your-project-id>
      roleRef:
        kind: IAMRole
        name: roles/storage.objectAdmin
    ```
  - **Ingress Connectivity**: A dynamic Ingress controller and GDC LoadBalancer IP must expose the client interface to GDC internal user networks.

---

## 1. Testing Environment Constraints vs. Production Parity

When validating your architecture locally or inside an online **GKE Cloud Workstation (L4 GPU)** sandbox:
* **Hardware Limits:** A single NVIDIA L4 GPU offers **24GB VRAM**.
* **Gemma 4 26B/31B VRAM Requirements**: Loading the unquantized weights inside vLLM in native `BF16` format consumes over **52GB VRAM** (26B MoE) to **64GB VRAM** (31B Dense).
* **Staging/Sandbox Strategy**: To host and validate the GKE serving logic successfully inside the 24GB VRAM limits concurrently side-by-side:
  1. Deploy two separate releases of the vLLM Helm chart (`vllm-26b` and `vllm-31b`).
  2. Map overrides to the smaller 8B variant: **`google/gemma-4-E4B-it`** (16GB BF16 footprint).
  3. Apply dynamic **FP8 weight quantization** on-the-fly by overriding values: `--set model.quantization="fp8"`. This fits both models cleanly inside the L4 GPU.
* **GDC Production Staging**: In production air-gapped racks, NVIDIA H100/A100 multi-GPU node pools are scaled up using dedicated node pools to host both full-scale unquantized `26B` and `31B` models concurrently.
* **Option B Fallback Staging**: If validating inside a low-spec standard sandbox cluster using the **lightweight 2B model** (`google/gemma-2b-it`) drop-in substitute, refer to the subsection below for crucial operational parity insights.

### 1.1. Operational Parity: Staging Validation with Option B (Mock 2B Fallback)

Option B deploys **`google/gemma-2b-it`** (a lightweight 2-billion parameter model) as a drop-in substitute. This is highly recommended for low-spec sandbox environments to validate the entire dynamic GKE serving framework without causing memory crashes.

**System Role Emulation & Mediation Nuance:**
* **The Challenge:** Pre-trained model templates for Gemma 2B do **not** natively support the structured `system` role tags inside vLLM. 
* **The Mitigation:** When a RAG query (with uploaded files context and strict boundaries instructions) is submitted, vLLM returns a `400 Bad Request: System role not supported` error. To prevent this from crashing tenant sessions, the **Gateway Proxy** automatically intercepts this 400 error in the background, consolidates all system directives and contexts into a single merged string, and retries the completion call in-flight as a single, flattened `"user"` role block.
* **Expected 2B Model Behavior:** Due to its 2B parameter scale and the merged-prompt emulation overhead, Gemma 2B possesses highly limited reasoning capacity and strict instructions alignment under RAG search boundaries. The model successfully reasons the correct answer within its `<thought>` reasoning block, but can sometimes contradict itself and output a generic negative fallback string (e.g., *"The context does not specify..."*) in its final response block.
* **Absolute Production Confidence:** Receiving a successful **`200 OK`** response (containing the thoughts block and text) is the ultimate operational confirmation! It proves that the entire GCS file retrieval, PostgreSQL database user history tracking, network routing, and gateway flattener are successfully integrated. Once swapped to the actual **Gemma 4 models (Option A / GDC Production)**:
  1. High-tier models natively support structured system roles, completely bypassing the proxy's flattener and retry blocks!
  2. They possess cutting-edge instruction compliance and massive context alignments, returning correct, high-fidelity final responses out-of-the-box!

---

## 2. vLLM Dual-Serving Concurrent Architecture

The gateway proxy implements a server-side **Prompt Routing Classifier** that dynamically routes prompts side-by-side to the correct serving node over GKE internal services, completely isolated using Release-specific selectors:

```text
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
                         |                       |
              (Port 8000)|            (Port 8000)|
                         v                       v
               +-------------------+   +-------------------+
               |    vLLM Pod A     |   |    vLLM Pod B     |
               | (Gemma 4 26B MoE) |   | (Gemma 4 31B Dense)
               +---------+---------+   +---------+---------+
                         |                       |
         (standard-rwo)  |                       | (standard-rwo)
         ReadWriteOnce   v                       v ReadWriteOnce
               +-------------------+   +-------------------+
               | Persistent Volume |   | Persistent Volume |
               |    (SSD Cache)    |   |    (SSD Cache)    |
               +-------------------+   +-------------------+
```

---

## 3. GDC Air-Gapped Sideloading & Storage Bootstrap for 26B/31B Models

In GDC air-gapped cluster racks, unquantized model weights must be sideloaded into dynamic GDC SAN Persistent Volumes before Helm serving charts can be applied.

### 3.1. Sideloading weights into your Disconnected PV Staging Directory

Execute these steps to download and bundle **both** unquantized Gemma 4 variants on your internet-connected bastion before shipping them over the air-gap perimeter (as detailed in the [Sideloading Guide](sideloading-guide.md#25-packaging-gated-model-weights-moe-26b-dense-31b-multimodal-8b)):

```bash
# 1. Authenticate against Hugging Face Hub
huggingface-cli login --token <YOUR_HF_TOKEN>

# 2. Download the Latency-Optimized 26B MoE variant
huggingface-cli download google/gemma-4-26B-A4B-it \
  --local-dir ./gemma-4-26B-A4B-it-weights

# 3. Download the Reasoning-Optimized 31B Dense variant
huggingface-cli download google/gemma-4-31B-it \
  --local-dir ./gemma-4-31B-it-weights

# 4. Compress both weight staging folders into secure transfer payloads
tar -czf gemma-4-26B-A4B-it-weights.tar.gz ./gemma-4-26B-A4B-it-weights/
tar -czf gemma-4-31B-it-weights.tar.gz ./gemma-4-31B-it-weights/
```

---

### 3.2. Bootstrapping Storage & Extracting Weights inside GDC-ag

Before copying the model weights, the target PersistentVolumes must be created in the GDC-ag cluster namespace. We bootstrap this dynamically using Kubernetes **PersistentVolumeClaims** and a temporary **Staging Helper Pod**:

#### Step A: Define the Storage Claims Manifest
Create `vllm-storage-claims.yaml` to request dynamic GDC SAN SAN storage allocations (`standard-rwx` supporting multi-writer mounting):

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vllm-26b-weights-pvc
  namespace: gemma-inference
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: "standard-rwx" # Mandatory GDC SAN StorageClass
  resources:
    requests:
      storage: 120Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: vllm-31b-weights-pvc
  namespace: gemma-inference
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: "standard-rwx" # Mandatory GDC SAN StorageClass
  resources:
    requests:
      storage: 120Gi
```

#### Step B: Define the Staging Helper Pod
Create `vllm-staging-helper.yaml` to mount both volumes securely, allowing you to copy and extract weights directly onto the SAN dynamic directories:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: vllm-staging-helper
  namespace: gemma-inference
spec:
  volumes:
    - name: storage-26b
      persistentVolumeClaim:
        claimName: vllm-26b-weights-pvc
    - name: storage-31b
      persistentVolumeClaim:
        claimName: vllm-31b-weights-pvc
  containers:
    - name: staging-helper
      image: debian:bookworm-slim
      command: ["/bin/sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: storage-26b
          mountPath: /mnt/vllm-26b
        - name: storage-31b
          mountPath: /mnt/vllm-31b
```

#### Step C: Apply Manifests and Upload Weights
Execute these administrative commands on your offline GDC operator workstation:

```bash
# 1. Create the Namespace and apply the storage descriptors
kubectl create namespace gemma-inference || true
kubectl apply -f vllm-storage-claims.yaml
kubectl apply -f vllm-staging-helper.yaml

# 2. Watch and wait for the helper pod to reach 'Running' status
kubectl get pods -n gemma-inference -l app.kubernetes.io/name=vllm-staging-helper -w
# (Alternatively wait using: kubectl wait --for=condition=Ready pod/vllm-staging-helper -n gemma-inference --timeout=300s)

# 3. Copy the compressed weights payloads directly into the mounted PVC folders
kubectl cp gemma-4-26B-A4B-it-weights.tar.gz gemma-inference/vllm-staging-helper:/mnt/vllm-26b/
kubectl cp gemma-4-31B-it-weights.tar.gz gemma-inference/vllm-staging-helper:/mnt/vllm-31b/

# 4. Execute extraction directly inside the volume mounts to populate directories
echo "Extracting Gemma 4 26B MoE weights..."
kubectl exec -it vllm-staging-helper -n gemma-inference -- /bin/sh -c \
  "tar -xzf /mnt/vllm-26b/gemma-4-26B-A4B-it-weights.tar.gz -C /mnt/vllm-26b/ && rm /mnt/vllm-26b/gemma-4-26B-A4B-it-weights.tar.gz"

echo "Extracting Gemma 4 31B Dense weights..."
kubectl exec -it vllm-staging-helper -n gemma-inference -- /bin/sh -c \
  "tar -xzf /mnt/vllm-31b/gemma-4-31B-it-weights.tar.gz -C /mnt/vllm-31b/ && rm /mnt/vllm-31b/gemma-4-31B-it-weights.tar.gz"

# 5. Verify directories are warm and populated
kubectl exec -it vllm-staging-helper -n gemma-inference -- ls -lh /mnt/vllm-26b/
kubectl exec -it vllm-staging-helper -n gemma-inference -- ls -lh /mnt/vllm-31b/

# 6. Delete the temporary helper pod (volumes persist cleanly in GDC SAN)
kubectl delete pod vllm-staging-helper -n gemma-inference
```

Now, your dynamic PersistentVolumes are pre-loaded with model weights and mapped cleanly under GDC paths:
- 26B Weights path: `/mnt/vllm-26b` (referenced in Helm values as mounting to `/models/gemma-4-26B-A4B-it-weights`)
- 31B Weights path: `/mnt/vllm-31b` (referenced in Helm values as mounting to `/models/gemma-4-31B-it-weights`)

---

### 3.3. Deploying serving blueprints using Helm

Pass the dynamic volume claims created in Step 3.2 to your Helms serving upgrades:

```bash
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
  --set resources.limits."nvidia.com/gpu"=2
```

# 3. Deploy the corresponding production vLLM gateway proxy manifest
export INFERENCE_ENGINE="vllm"
export REGISTRY_HOST="harbor.gdc.local/library" # Map to your local Harbor registry
./standalone/install-all.sh

> [!IMPORTANT]
> **Operational Note on Large Weights Pulling Time:**
> Because production-level unquantized baked model images exceed **45GB+**, GKE nodes pulling container layers internally over isolated networks dynamically stream massive chunks from the Harbor registry. **Planners and operators must allocate at least 10-15 minutes for image extraction and startup BEFORE triggering troubleshooting procedures.**

---

## 4. Cross-Project Gateway Sharing & Enterprise Authentication

In enterprise GDC air-gapped (GDC-ag) organizations, multiple distinct tenant projects often share a central, high-performance **Gemma 4 Dedicated Inference Gateway** to optimize expensive GPU allocation. 

This section explains how applications running in different project namespaces and clusters can securely consume the shared gateway.

### 4.1. Cross-Namespace Network Routing

Depending on whether the client application is deployed in the **same GKE cluster** (different project namespaces) or an **entirely different GKE user cluster** within the GDC organization, configure network connectivity accordingly:

#### Pathway A: Same-Cluster Service Sharing (KubeDNS)
Workloads running in different namespaces within the same GKE cluster can directly address the Inference Gateway via its internal Kubernetes cluster-DNS domain:
`http://gemma-gateway.gemma-inference.svc.cluster.local/v1`

Because GDC namespaces are isolated by default, the operator must apply a `NetworkPolicy` inside the serving namespace (`gemma-inference`) to explicitly authorize incoming traffic from your tenant projects.

**Example: Cross-Project NetworkPolicy (`gateway-allow-ingress.yaml`)**
```yaml
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
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: <your-tenant-project-namespace>
    ports:
    - protocol: TCP
      port: 80
```

##### Pathway B: Cross-Cluster/Tenant Project Sharing (Gateway API)
If the client application resides in a completely separate GKE cluster or tenant project, it cannot use cluster-local DNS. Instead, the gateway must be exposed via standard Kubernetes Gateway API resources (`Gateway`, `HTTPRoute`).

1. **Deploy the GDC Platform Gateway (Load Balancer):**
   If not already provisioned by platform operators, deploy the `Gateway` resource bound to the platform `GatewayClass` representing the hardware load balancer:

   ```yaml
   # 02-gateway-loadbalancer.yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: Gateway
   metadata:
     name: gdc-platform-gateway
     namespace: gemma-inference
   spec:
     gatewayClassName: gdc-platform-gateway # Native GDC hardware load balancer class
     listeners:
     - name: http
       protocol: HTTP
       port: 80
       allowedRoutes:
         namespaces:
           from: All
   ```

2. **Deploy the HTTPRoute (`02-gateway-httproute.yaml`):**
   Expose the gateway by binding an `HTTPRoute` mapping rule to the programmed gateway:

   ```yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: HTTPRoute
   metadata:
     name: gemma-gateway-route
     namespace: gemma-inference
   spec:
     parentRefs:
     - group: gateway.networking.k8s.io
       kind: Gateway
       name: gdc-platform-gateway
       namespace: gemma-inference # References shared platform gateway
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
Once applied, external projects can resolve the FQDN `http://gemma-gateway.shared-services.gdc.local/v1` inside the private GDC network.

---

### 4.2. OIDC User Authentication (Keycloak Federation)

In production air-gapped environments, cross-project gateway access must be cryptographically protected to maintain secure user boundaries, auditing, and Role-Based Access Control (RBAC).

*   **Keycloak Integration**: To secure user sessions, transition client applications from "Mock User" modes to federated OpenID Connect (OIDC) authentication using Keycloak running natively on GDC.
*   **Architecture & Claims Validation**: The client frontend triggers the OIDC Authorization Code Flow (with PKCE) directly against Keycloak, obtaining a JWT (Access Token) which is dynamically attached as an `Authorization: Bearer <JWT>` header to downstream requests. The FastAPI backend cryptographically validates this signature using the Keycloak certificates (`/certs`).
*   **Detailed Implementation Guide**: Refer to the complete, step-by-step [Keycloak Integration Guide](keycloak_integration_guide.md) for instructions on provisioning Keycloak Realms, configuring clients (`rag-frontend`), updating Axios token interceptors in React, and building robust OIDC validation middleware in python/FastAPI.

