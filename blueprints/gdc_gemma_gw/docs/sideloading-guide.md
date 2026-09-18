Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Air-Gapped Packaging & Sideloading Guide

> **Version:** 1.1

This guide explains how to package the Gemma 4 Inference Gateway assets from an internet-connected bastion (like a Google Cloud Workstation) and transfer them to the GDC air-gapped (GDC-ag) environment using the GDC blueprint standard format.

> For detailed instructions on provisioning multi-GPU nodes, configuring Helm parameters, and scaling vLLM workloads, refer to the [GDC Production Serving Guide: vLLM & Gemma 4](vllm-serving-guide.md).

---

## GDC Platform Prerequisites

Deploying the full **Gemma 4 Dedicated Inference Gateway** stack in production GDC air-gapped environments requires coordinating several platform resources. The gateway and its companion **Gemma Client Application** rely on these pre-requisites to enable secure multi-tenant, high-capacity serving.

> [!TIP]
> **GCP Staging & Sandbox Emulation Note:**
> If you are testing or validating this entire setup inside a GCP GKE development sandbox rather than a live air-gapped GDC production rack, refer to the **[GCP Quickstart Guide](quickstart_on_GCP.md)**. The guide contains the exact commands to provision the GKE GPU cluster, configure symmetrical node labels (`app=vllm-26b`, `app=vllm-31b`, `app=client`), and deploy PostgreSQL database emulation (`statefulset-postgres.yaml`).

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
* **Why?** To enable persistent multi-tenant workflows, dynamic PostgreSQL services must be pre-provisioned.
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

## 1. Overview of Assets to Package
To run the gateway offline, you must bundle:
1. **Complete Transfer Bundle** (`gemma-gateway-gdc-bundle.tar.gz`)
2. **Helm Charts, Manifests & Gemma Client Application**
3. **Baked Images** (Ollama or vLLM baked models and Gateway Proxy)
4. **Integrity Checksums** (`BOM.txt` and `manifest.txt`)

---

## 2. Building and Exporting the Bundle (Internet Connected)

Instead of manually tarring individual files, use the `package-for-gdc.sh` script to automatically produce a complete self-contained transfer bundle mirroring exactly the GDC blueprint structure.

### 2.1. Package for Ollama (Optimsed for testing quick validation)
```bash
export INFERENCE_ENGINE="ollama"
export REGISTRY_HOST="us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"
./scripts/package-for-gdc.sh
```

### 2.2. Package for vLLM (Production/Advanced)
```bash
export INFERENCE_ENGINE="vllm"
export REGISTRY_HOST="us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"
./scripts/package-for-gdc.sh
```

### 2.3. Package Both Simultaneously
```bash
export INFERENCE_ENGINE="all"
export REGISTRY_HOST="us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"
./scripts/package-for-gdc.sh
### 2.4. Package Client Only
```bash
export INFERENCE_ENGINE="client"
export REGISTRY_HOST="us-central1-docker.pkg.dev/your-gdc-project/gemma-repo"
./scripts/package-for-gdc.sh
```

### 2.5. Packaging Gated Model Weights (MoE 26B, Dense 31B, Multimodal 8B)
To serve the model weights offline inside GDC air-gapped rack volumes (bypassing HuggingFace network dependencies entirely), you must download and stage the unquantized model weights before perimeter transfers:

> [!IMPORTANT]
> **Engine Weight Packaging Differences (Ollama vs. vLLM):**
> - **Ollama Serving (Pre-Baked)**: Ollama container images are fully self-contained because our building scripts compile the weights **directly into the baked image filesystem layers**. If you are deploying Ollama for developers/testing, you do **not** need to execute the separate downloading or compression steps in this section!
> - **vLLM Serving (Dynamic Mounts)**: vLLM serving containers are kept lightweight and strictly rootless, meaning **they do not bundle any model weights** internally. Instead, vLLM mounts weights dynamically from dynamic SAN Persistent Volumes. 
> - **Operational Rule**: **This Section (2.5) is strictly and only required if you are deploying the production-grade vLLM serving engine!**

```bash
# 1. Authenticate against the gated HuggingFace Hub on your staging workstation
huggingface-cli login --token <YOUR_HF_TOKEN>

# 2. Download the desired Gemma 4 variant unquantized weights locally:
# MoE 26B (Production):
huggingface-cli download google/gemma-4-26B-A4B-it --local-dir ./packages/gemma-4-26B-A4B-it-weights
# Dense 31B (Production):
huggingface-cli download google/gemma-4-31B-it --local-dir ./packages/gemma-4-31B-it-weights
# Multimodal 8B (Workstation Sandboxes):
huggingface-cli download google/gemma-4-E4B-it --local-dir ./packages/gemma-4-E4B-it-weights

# 3. Compress all downloaded weight directories into secure transfer archives
tar -czf ./packages/gemma-4-26B-A4B-it-weights.tar.gz -C ./packages gemma-4-26B-A4B-it-weights
tar -czf ./packages/gemma-4-31B-it-weights.tar.gz -C ./packages gemma-4-31B-it-weights
tar -czf ./packages/gemma-4-E4B-it-weights.tar.gz -C ./packages gemma-4-E4B-it-weights
```

---


## 3. Transfer and Ingest (GDC-ag Environment)

This section provides the absolute, step-by-step deployment instructions for new GDC operators receiving the packaged payload files inside the air-gappedRack boundaries.

### 3.1. Step 1: Loading Container Images to dynamic Harbor Registry
1. Move the generated `packages/gemma-gateway-gdc/` staging folders into your offline rack workstations.
2. Extract the container image targets:
   `docker load -i gateway/ollama/gemma-gateway-gdc-images.tar` (For Ollama serving)
   OR `docker load -i gateway/vllm/gemma-gateway-gdc-images.tar` (For vLLM serving)
3. Tag and push the loaded image slots dynamically over to your dynamic internal Harbor registry:
   ```bash
   docker tag <IMAGE_ID> harbor.gdc.local/library/gemma-proxy:latest
   docker push harbor.gdc.local/library/gemma-proxy:latest
   ```

---

### 3.2. Step 2: Provisioning Model Weights in dynamic GDC SAN Volumes

#### Pathway A: The Ollama Testing serving setup
Ollama model weights (`26B MoE` or `31B Dense`) are **pre-baked directly inside the container images** staged in Step 3.1. You do **not** need to map separate storage volume downloads! Move straight to Step 3.3.

#### Pathway B: The High-Performance vLLM Production serving setup
vLLM serves unquantized model weights directly from the cluster's Persistent Volumes. Extract the weights payloads staged under Section 2.5 based on your hardware GPU resources:

##### 1. Option 1: Dynamic GKE sandboxes (L4 GPUs, 24GB VRAM)
If validating code logic inside limited sandboxes, leverage the smaller unquantized weights package (`8B Multimodal` variant):
```bash
# Extract the 8B weights payload directly onto the dynamic storage pool
tar -xzf packages/gemma-4-E4B-it-weights.tar.gz -C /models/gemma-4-E4B-it-weights/
```

##### 2. Option 2: GDC Production racks (Multi-GPU nodes, H100/A100 pools)
If launching concurrent unquantized serving under full GDC enterprise rack hardware, leverage the unquantized weights packages (`26B MoE` / `31B Dense`):
```bash
# Extract the unquantized MoE weights payload into the dynamic SAN storage pool
tar -xzf packages/gemma-4-26B-A4B-it-weights.tar.gz -C /models/gemma-4-26B-A4B-it-weights/
```

---

### 3.3. Step 3: Deploying serving blueprints using Helm

Now, finalize your cluster serving deployment by applying the respective Helm templates:

#### Pathway A: Launching Ollama:
Extract the manifest bundles and execute your local installation scripts:
```bash
tar -xzf gateway/ollama/gemma-gateway-gdc-manifests.tar.gz
./standalone/install-all.sh
```

#### Pathway B: Launching vLLM (GDC Production Dual-Model serving):
Extract the manifests bundle, initialize the namespace, and deploy the dual serving blueprints concurrently. We enforce GDC SAN dynamic persistent volumes (`standard-rwx`) by passing the GDC-specific overrides file `-f blueprints/vllm-gke/values-gdc.yaml`:

```bash
tar -xzf gateway/vllm/gemma-gateway-gdc-manifests.tar.gz

# 1. Create target namespace
kubectl apply -f standalone/manifests/00-namespace.yaml

# 2. Deploy GDC Production Release A (26B MoE - Latency Optimized)
helm upgrade --install vllm-26b ./blueprints/vllm-gke -n gemma-inference \
  -f ./blueprints/vllm-gke/values-gdc.yaml \
  --set model.name="/models/gemma-4-26B-A4B-it-weights" \
  --set model.servedModelName="gemma4:26b" \
  --set resources.limits."nvidia.com/gpu"=1

# 3. Deploy GDC Production Release B (31B Dense - Reasoning Optimized)
helm upgrade --install vllm-31b ./blueprints/vllm-gke -n gemma-inference \
  -f ./blueprints/vllm-gke/values-gdc.yaml \
  --set model.name="/models/gemma-4-31B-it-weights" \
  --set model.servedModelName="gemma4:31b" \
  --set resources.limits."nvidia.com/gpu"=2

# 4. Deploy the corresponding production vLLM gateway proxy manifest
export INFERENCE_ENGINE="vllm"
export REGISTRY_HOST="harbor.gdc.local/library" # Map to your local Harbor registry
./standalone/install-all.sh
```

---

## 4. Air-Gapped Deployment Verification

Once deployed, verification cannot be done using normal web browsers or `port-forward`. You must test inside the cluster over internal DNS:

1. Refer to the [Testing Methodology](testing-methodology.md) to start an ephemeral test client pod inside the `gemma-inference` namespace.
2. Use `curl` to test gateway parameters and trigger inference calls directly against `http://gemma-gateway.gemma-inference.svc.cluster.local/v1/chat/completions`.

---

## 5. Cross-Project Gateway Sharing & Enterprise Authentication

In enterprise GDC air-gapped (GDC-ag) organizations, multiple distinct tenant projects often share a central, high-performance **Gemma 4 Dedicated Inference Gateway** to optimize expensive GPU allocation. 

This section explains how applications running in different project namespaces and clusters can securely consume the shared gateway.

### 5.1. Cross-Namespace Network Routing

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

#### Pathway B: Cross-Cluster/Tenant Project Sharing (Gateway API)
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
     gatewayClassName: gdc-platform-gateway # Platform hardware load balancer class
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

### 5.2. OIDC User Authentication (Keycloak Federation)

In production air-gapped environments, cross-project gateway access must be cryptographically protected to maintain secure user boundaries, auditing, and Role-Based Access Control (RBAC).

*   **Keycloak Integration**: To secure user sessions, transition client applications from "Mock User" modes to federated OpenID Connect (OIDC) authentication using Keycloak running natively on GDC.
*   **Architecture & Claims Validation**: The client frontend triggers the OIDC Authorization Code Flow (with PKCE) directly against Keycloak, obtaining a JWT (Access Token) which is dynamically attached as an `Authorization: Bearer <JWT>` header to downstream requests. The FastAPI backend cryptographically validates this signature using the Keycloak certificates (`/certs`).
*   **Detailed Implementation Guide**: Refer to the complete, step-by-step [Keycloak Integration Guide](keycloak_integration_guide.md) for instructions on provisioning Keycloak Realms, configuring clients (`rag-frontend`), updating Axios token interceptors in React, and building robust OIDC validation middleware in python/FastAPI.



