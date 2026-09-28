Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 2: High-Availability ML/AI Inference on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **High-Availability ML/AI Inference** pattern on Google Distributed Cloud (GDC) air-gapped environments. This pattern constructs a resilient, scalable model serving platform on GPU-enabled GKE node pools, exposing low-latency inference endpoints backed by local serving engines (vLLM or Ollama) and protected by GDC Gateway API routes.

## **Architecture**

```
                  ┌─────────────────────────────────────────┐
                  │          [ GDC Gateway API ]            │
                  │        (gdc-shared-gateway)             │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ (Port 80/443)
                  ┌─────────────────────────────────────────┐
                  │      [ Gemma Inference Gateway ]        │
                  │       (vLLM / Ollama Proxy)             │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ (Tensor Parallelism)
                  ┌─────────────────────────────────────────┐
                  │      [ GPU Node Pool Workloads ]        │
                  │     (NVIDIA L4 / g2-standard-24)        │
                  └─────────────────────────────────────────┘
```

### **Key Solution Capabilities**

* **GPU Acceleration**: Utilizes GDC GPU node pools for high-throughput, low-latency model inference.
* **vLLM / Ollama Engine Integration**: Supports OpenAI-compatible REST endpoints (`/v1/chat/completions`) and legacy `/generate` calls.
* **Dual Gateway & Fallback Support**: Can serve downstream RAG agents (Pattern 6) and Data Analyst agents (Pattern 7) or route to GDC Gemini AI Gateway.
* **Least-Privilege Security Policy**: Isolates model serving under a dedicated `gemma-gateway-sa` Kubernetes ServiceAccount.

---

## **Gateway Deployment & Cross-Cluster Topology Guidance**

The **Gemma Inference Gateway** (`gdc_gemma_gw`) deployed by Pattern 2 acts as an enterprise inference server.

> [!NOTE]
> **Centralized vs Co-Located Gateway Topology**:
> The Gemma Inference Gateway does **not** need to be deployed inside the same cluster or namespace as consumer applications (such as Pattern 6, 7, 9, or 10).
> Depending on organization topology, this gateway can be deployed in:
> * **Dedicated GPU / Model-Serving Cluster**: Exposed via GDC Gateway API (`HTTPRoute` / load balancer FQDN `https://ai-gateway.shared-services.gdc.local/v1`) to serve multiple remote GKE workload clusters.
> * **Centralized Shared Services Namespace**: `http://gemma-gateway.shared-services.svc.cluster.local:80/v1` serving cross-namespace workloads in the same cluster.
> * **Local Workload Namespace**: `http://gemma-gateway.<namespace>.svc.cluster.local:80/v1` for tightly coupled deployments.

---

## **Production Deployment vs Connected Artifact Preparation**

| Dimension | **Connected Sideloading Workstation** | **GDC Air-Gapped Production** |
| :--- | :--- | :--- |
| **GPU Node Pool** | Sideloaded GPU container images & model weights | GDC Air-Gapped GPU Node Pool |
| **Serving Backend** | Artifact bundle verification & image mirror | Gemma Gateway (`gdc_gemma_gw` HA replicas with Tensor Parallelism) |
| **Target Namespace** | Connected staging registry (`harbor.gdc.local`) | Organization Workload Namespace (hydrated via `-n`) |
| **Service Exposure** | Local docker push / image export | GDC Gateway API (`HTTPRoute` + `gdc-shared-gateway`) |

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher with GPU node pools enabled.
* Container images (`gemma-gateway`, `vllm`, `ollama`) transferred and available in internal Harbor registry.
* `kubectl` and `gdcloud` CLIs configured.

---

## **Section 1: Setup & Blueprint Configuration**

### 1.1 Configure Blueprint Variables

Hydrate blueprint manifests with your target environment variables:

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>"

./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p2-ha-ml-ai-inference
```

### 1.2 Push Images to Harbor

```bash
export REGISTRY_HOST="harbor.gdc.local"
./scripts/unpack-for-gdc.sh p2-ha-ml-ai-inference-gdc-images.tar ${REGISTRY_HOST}/library
```

---

## **Section 2: Workload Deployment**

Apply the inference gateway service and GPU deployment manifests:

```bash
kubectl apply -f manifests/apps/gemma-gateway.yaml -n ${NAMESPACE}
kubectl rollout status deployment/gemma-gateway -n ${NAMESPACE}
```

---

## **Section 3: Production Security & Observability**

### 3.1 NetworkPolicy Guidance
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: p2-inference-security-policy
  namespace: <target-namespace>
spec:
  podSelector:
    matchLabels:
      app: gemma-gateway
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 80
```

### 3.2 Live Operational Log Inspection
```bash
# View Gemma Gateway inference logs
kubectl logs -l app=gemma-gateway -n ${NAMESPACE} --tail=50 -f
```

---

## **Section 4: Operations & Troubleshooting**

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Insufficient nvidia.com/gpu` | GPU node pool has no available capacity. | Check GPU node pool scaling or reduce per-pod GPU request. |
| `Port 8080 timeout` | Service port mismatch. | Gemma Gateway listens on port `80` (`http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`). |
