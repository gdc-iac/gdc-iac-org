Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 9: Sovereign Notebook (NotebookLM) on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Sovereign Notebook (NotebookLM)** pattern on Google Distributed Cloud (GDC) air-gapped environments. This pattern provides an air-gapped interactive research notebook interface, combining local document grounding (RAG), text summarization, audio overview generation, and notebook synthesis backed by local Gemma / Gemini models.

## **Architecture**

```
                  ┌─────────────────────────────────────────┐
                  │          [ GDC Gateway API ]            │
                  │        (gdc-shared-gateway)             │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ (Port 80/443)
                  ┌─────────────────────────────────────────┐
                  │      [ Sovereign Notebook Frontend ]    │
                  │         (Interactive Research GUI)      │
                  └────────────────────┬────────────────────┘
                                       │
                  ┌────────────────────┴────────────────────┐
                  ▼                                         ▼
   ┌──────────────────────────────┐        ┌──────────────────────────────┐
   │    [ GDC Object Storage ]     │        │  [ Gemma / Gemini Gateway ]  │
   │  (Private Research Notebooks)│        │   (Document Processing LLM)  │
   └──────────────────────────────┘        └──────────────────────────────┘
```

### **Key Solution Capabilities**

* **Air-Gapped NotebookLM Experience**: Enables researchers to organize source documents, generate summaries, and interact with private data offline.
* **Dual Gateway & Fallback Support**: Connects to the self-hosted **Gemma Inference Gateway** (`../gdc_gemma_gw`) on port 80 or native **GDC Gemini AI Gateway**.
* **Air-Gapped Document Grounding**: Integrates local PostgreSQL vector storage (`pgvector`) to ensure all citations originate strictly from private sources.
* **Least-Privilege Security Policy**: Restricts storage and notebook execution using a dedicated `notebook-sa` ServiceAccount.

---

## **LLM Gateway Integration & Cross-Cluster Topology Guidance**

Pattern 9 is designed to consume either the self-hosted **Gemma Inference Gateway** (`gdc_gemma_gw`) or the native **GDC Gemini AI Gateway**.

> [!NOTE]
> **Cross-Cluster & Shared-Services Gateway Access**:
> The inference gateway does **not** need to be co-located in the same cluster or namespace as the Sovereign Notebook application.
> Depending on enterprise infrastructure deployment, `LLM_GATEWAY_URL` can point to:
> * **Co-located Namespace**: `http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`
> * **Shared Services Cluster / Namespace**: `http://gemma-gateway.shared-services.svc.cluster.local:80/v1`
> * **Dedicated External GPU Cluster**: `https://ai-gateway.shared-services.gdc.local/v1` (exposed via GDC Gateway API `HTTPRoute` or load balancer FQDN).

---

## **Production Deployment vs Connected Artifact Preparation**

| Dimension | **Connected Sideloading Workstation** | **GDC Air-Gapped Production** |
| :--- | :--- | :--- |
| **Object Storage** | Artifact stage / local directory (`./data/notebook-docs`) for bundle prep | Native GDC Object Storage Bucket |
| **LLM Inference** | Container image download & model weights packaging | Gemma Gateway (`gdc_gemma_gw`) or GDC AI Inference Gateway |
| **Target Namespace** | Connected staging registry (`harbor.gdc.local`) | Organization Workload Namespace (hydrated via `-n`) |
| **Service Exposure** | Local CLI / Docker execution | GDC Gateway API (`HTTPRoute` + `gdc-shared-gateway`) |

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* `kubectl` and `gdcloud` CLIs configured.
* A target GDC project and namespace configured.

---

## **Section 1: Setup & Blueprint Configuration**

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>"

./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p9-sovereign-notebook
```

---

## **Section 2: Workload Deployment**

```bash
kubectl apply -f manifests/apps/sovereign-notebook.yaml -n ${NAMESPACE}
kubectl rollout status deployment/sovereign-notebook -n ${NAMESPACE}
```

---

## **Section 3: Production Security & Observability**

### 3.1 Live Operational Log Inspection
```bash
# View Sovereign Notebook service logs
kubectl logs -l app=sovereign-notebook -n ${NAMESPACE} --tail=50 -f

# View Gemma Gateway inference logs
kubectl logs -l app=gemma-gateway -n ${NAMESPACE} --tail=50 -f
```

---

## **Section 4: Operations & Troubleshooting**

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Upload Failed (403)` | Workload Identity or storage IAM permissions missing. | Ensure `notebook-sa` has Object Admin role on target research bucket. |
| `LLM Gateway Timeout` | Large document processing exceeds 60s timeout. | Ensure Gemma Gateway service port is set to `80` and timeout is configured for 180s. |
