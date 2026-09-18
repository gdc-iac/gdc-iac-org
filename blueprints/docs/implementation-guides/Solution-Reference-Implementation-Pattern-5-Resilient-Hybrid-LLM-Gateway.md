Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 5: Resilient Hybrid LLM Gateway on GDC air-gapped [DEPRECATED]**

> **Version:** 1.2  
> **Status:** DEPRECATED

> [!CAUTION]
> **DEPRECATED REFERENCE IMPLEMENTATION**:
> Pattern 5 (Resilient Hybrid LLM Gateway) is **deprecated** as of Blueprint Version 1.2.
> Application blueprints (Pattern 6 RAG Agent, Pattern 7 Agentic Data Analyst, Pattern 9 Sovereign Notebook, Pattern 10 Chatbot) now natively interface directly with either the **Gemma Inference Gateway** (`gdc_gemma_gw` / vLLM / Ollama) or **GDC Gemini AI Gateway**.
> Dedicated proxy gateways (Pattern 5) are no longer required or recommended.

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Resilient Hybrid LLM Gateway** on Google Distributed Cloud (GDC) air-gapped environments. The Gateway serves as a high-availability GenAI abstraction layer. It intercepts incoming client prompts, routing them preferentially to GDC's native platform-managed Gemini API, and executing an automatic, zero-downtime failover to a locally-served Gemma endpoint (via Ollama or vLLM) if the primary service becomes unreachable.

## **Architecture**

The gateway sits between client application request flows (like downstream RAG agents) and GDC AI services, managing failover routing policies internally.

```
                    [ Downstream Client App / Agent ]
                                   │
                                   ▼ (Port 80)
                         [ GDC LLM Gateway ]
                           (Deployment: llm-gateway)
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │ (If Primary Fails)
                     ▼                           ▼
            [ GDC Vertex AI ]           [ Locally Served Gemma ]
             (Primary Gemini API)        (Ollama / vLLM Fallback)
```

### **Key Solution Capabilities**

* **Resilient Model Failover**: Intercepts primary provider errors (5xx responses, timeouts) to switch traffic transparently.
* **Dual Serving Protocol Integration**: Implements drivers for Google's native Vertex AI API alongside standard OpenAI-compatible REST formats for secondary backends.
* **Unified Interface**: Exposes a consistent completions endpoint, preventing client codebase logic adjustments.
* **ServiceAccount Isolation**: Leverages GDC's `ProjectPolicy` and `Role/ai-invoker` to bind and protect runtime keys.

---

## **LLM Gateway Integration & Cross-Cluster Topology Guidance**

> [!NOTE]
> **Cross-Cluster & Shared-Services Gateway Access**:
> The hybrid LLM gateway and its backend inference targets (Gemma Gateway or GDC Gemini AI Gateway) do **not** need to reside in the same cluster or namespace as consumer applications.
> * **Centralized Deployment**: The Gateway can be deployed in a dedicated shared-services namespace (`http://llm-gateway.shared-services.svc.cluster.local:80`) or dedicated AI cluster to serve multiple downstream applications across the organization.
> * **Configurable Target Backends**: Primary and secondary failover endpoints (`FAILOVER_URL`) can target local namespace services, cross-namespace FQDNs, or external GDC Gateway API endpoints.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* GDC Vertex AI service enabled and healthy.
* A locally served secondary model (e.g. Gemma 2B/7B served via Ollama as deployed in Pattern 3/10) deployed and reachable over internal DNS.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **IAM Admin**: `roles/iam.serviceAccountAdmin` (to manage service accounts).
  * **GKE Developer**: `roles/gke.developer` (to deploy manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the custom gateway and baked model images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p5-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom images:
```bash
docker tag llm-gateway:latest harbor.shared-services.gdc.local/my-org/llm-gateway:latest
docker push harbor.shared-services.gdc.local/my-org/llm-gateway:latest

docker tag ollama-gemma:7b harbor.shared-services.gdc.local/library/ollama-gemma:7b
docker push harbor.shared-services.gdc.local/library/ollama-gemma:7b
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p5-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry p5-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.3 Base Cluster Resource & Node Pool Requirements

### 1.3.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **LLM Gateway Proxy** | 2 | 100m (500m) | 128Mi (512Mi) | None |

### 1.3.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Dedicated to hosting the stateless LLM gateway proxy pods.
* **Instance Type**: 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node) or equivalent.
* **Total Resource Pool**: 8 vCPUs, 32Gi RAM.
* **Resilience Configuration**: Spreading workloads across at least 2 compute nodes ensures that proxy replicas are distributed to withstand a single-node failure without service degradation.

### 1.3.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p5-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-4-gdc
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
  name: p5-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p5-shared-cluster
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
  name: p5-standard-cluster
  namespace: my-gdc-project
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-4-gdc
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

Configure `nodeSelector` in the LLM Gateway Proxy manifest:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Configuring GDC IAM Permissions**

The gateway requires project-level permissions to authorize calls to GDC's Vertex AI engine. Bind the `ai-invoker` role to the gateway's dedicated `ServiceAccount`.

#### Option A: Manual (CLI)
```shell
export NAMESPACE="my-gdc-project"

# 1. Create the ServiceAccount
kubectl create sa gateway-sa -n ${NAMESPACE}

# 2. Add IAM policy binding
gdcloud iam service-accounts add-iam-policy-binding gateway-sa \
  --project=${NAMESPACE} \
  --role=Role/ai-invoker
```

#### Option B: GitOps / IaC (`manifests/iam/gateway-permissions.yaml`)
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gateway-sa
  namespace: my-gdc-project
---
apiVersion: iam.gdc.goog/v1
kind: ProjectPolicy
metadata:
  name: gateway-bindings
  namespace: my-gdc-project
spec:
  bindings:
  - role: Role/ai-invoker
    members:
    - serviceAccount:gateway-sa
```

---

## **Section 3: Deploying the LLM Gateway**

Create the configuration maps setting up endpoints and deploy the proxy containers.

#### Option A: Manual (CLI)
```shell
kubectl apply -f llm-gateway.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/llm-gateway.yaml`)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gateway-conf
  namespace: my-gdc-project
data:
  PROJECT_ID: "my-gdc-project"
  REGION: "us-central1"
  GEMINI_MODEL: "gemini-2.5-flash"
  FAILOVER_URL: "http://ollama-svc.my-gdc-project.svc.cluster.local:11434/api/generate"
  FAILOVER_MODEL: "gemma:7b"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-gateway
  namespace: my-gdc-project
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      serviceAccountName: gateway-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: proxy
        image: harbor.shared-services.gdc.local/my-org/llm-gateway:latest
        imagePullPolicy: Always
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
        envFrom:
        - configMapRef:
            name: gateway-conf
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: llm-gateway
  namespace: my-gdc-project
spec:
  selector:
    app: gateway
  ports:
  - port: 80
    targetPort: 8080
```

---

## **Section 4: Validation**

### 4.1 Test Primary Route (Gemini)

#### Option A: Internal Cluster Checkmark Verification (No Port-Forwarding Needed)
Execute an ephemeral verification check directly against the internal `llm-gateway` Service:

```bash
kubectl run p5-verify --rm -i --restart=Never -n my-gdc-project \
  --image=curlimages/curl --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 5 Hybrid LLM Gateway verified!" && \
    echo "✅ SUCCESS: Primary routing and endpoint reachable" && \
    echo "===============================================" && \
    curl -s -X POST http://llm-gateway/v1/completions -d "{\"prompt\": \"Hello\", \"temperature\": 0.5}" -H "Content-Type: application/json" && \
    echo ""
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 5 Hybrid LLM Gateway verified!
✅ SUCCESS: Primary routing and endpoint reachable
===============================================
{"response":"..."}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: ClusterIP & Log Verification
Send a test request using ClusterIP:
```shell
export GATEWAY_IP=$(kubectl get service llm-gateway -n my-gdc-project -o jsonpath='{.spec.clusterIP}')

curl -X POST http://${GATEWAY_IP}/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello", "temperature": 0.5}'
```
Check gateway logs to confirm routing:
```shell
kubectl logs -l app=gateway -n my-gdc-project
# Expected log line: "Routing request to primary GDC Vertex AI endpoint"
```

### 4.2 Test Failover Route (Gemma)
To simulate primary provider outage:
1. Temporarily change the target primary URL or disable the primary endpoint config.
2. Send the same completion request.
3. Check gateway logs again:
```shell
kubectl logs -l app=gateway -n my-gdc-project
# Expected log line: "Primary provider failed. Executing failover route to http://ollama-svc..."
```

---

## **Section 5: Operations & Troubleshooting**

### 5.1 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `403 Permission Denied` | ServiceAccount lacks the `ai-invoker` project IAM role. | Verify that the `ProjectPolicy` binds `Role/ai-invoker` to the `gateway-sa` service account. |
| `Failover loop exhaustion` | The secondary fallback backend is down or unreachable. | Verify DNS resolution for the secondary host and make sure the serving container is running. |
| `504 Gateway Timeout` | Large token responses cause client timeout limits to break. | Increase timeout parameters inside your downstream calling client and gateway configuration. |
