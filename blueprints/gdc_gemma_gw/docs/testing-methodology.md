Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GDC Air-Gapped Testing Methodology

> **Version:** 1.1

This guide details how to verify the **Gemma 4 Inference Gateway** in disconnected GDC air-gapped environments where external network access and `kubectl port-forward` are prohibited.

---

## 1. Ephemeral Test Pod Pattern

Since you cannot reach the gateway from outside the cluster, you must run a temporary test client pod directly inside the same GKE namespace (`gemma-inference`) and interact with the service over the internal DNS.

### 1.1. Start the Ephemeral Test Pod

Run a temporary Linux client pod in your cluster:
```bash
kubectl run gemma-test-client --rm -i --tty \
  --image=debian:bookworm-slim \
  --namespace gemma-inference \
  -- /bin/sh
```
*(Wait for the prompt).*

> [!CAUTION]
> **Ollama Baked Model Image Pulling Time:**
> The `ollama-gemma-26b` (MoE) and `ollama-gemma-31b` (Dense) container images contain the complete baked VRAM weights and exceed **45GB - 50GB+** each! When deploying or switching variants inside GKE sandboxes, GKE requires **at least 10-15 minutes** to successfully download and unpack the heavy image layers. **Do not execute validation commands until the serving pod transitions securely into a healthy `Running` status.**


### 1.2. Install Test Tooling (Inside the Pod)
Once inside the prompt, install `curl`:
```bash
apt-get update && apt-get install -y curl
```

---

## 2. Testing the Inference Gateway

Run these commands from inside the test pod to verify the gateway:

### 2.1. Validate Gateway Health
```bash
curl -X GET http://gemma-gateway.gemma-inference.svc.cluster.local/api/config
```
*Expected Result*: A valid JSON document containing the current model parameters and the active variant:
```json
{
  "temperature": 0.7,
  "top_p": 0.9,
  "frequency_penalty": 0.0,
  "vision_token_budget": 280,
  "model_variant": "26b"
}
```

### 2.2. Test Basic Inference
Invoke the OpenAI-compatible chat endpoint via the internal URL:
```bash
curl -X POST http://gemma-gateway.gemma-inference.svc.cluster.local/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:26b",
    "messages": [
      {"role": "user", "content": "What are three primary colors?"}
    ]
  }'
```
*Expected Result*: The JSON output containing the response tokens from the active backend model.

---

## 3. Testing Both Model Variants (Hot-Swapping)

When running both Gemma 4 variants (`26b` MoE and `31b` Dense) concurrently inside the cluster sandbox (Option A: Unified Pod serving) under hardware constraints, the model weights sharing is handled dynamically on the VRAM. Operators can validate that model hot-swapping is successfully taking place in the background by tracking two console feedback loops simultaneously:

### 3.1. Payload Validation: Gateway Proxy logging
Stream the core Gateway logs to confirm your client requests are actively changing the routing payload target:

```bash
kubectl logs -f deployment/gemma-gateway -n gemma-inference
```

As you select different models and enter queries, the Gateway output logs stream:
* `Routing request (Model: gemma4:26b) to: ...` when executing MoE variant.
* `Routing request (Model: gemma4:31b) to: ...` when executing Dense variant.

### 3.2. Memory Validation: Ollama Server VRAM scheduling
Stream the Ollama container logs to verify that the model server is dynamically shifting hardware VRAM slices on the GPU card:

```bash
kubectl logs -f deployment/ollama-26b -c ollama -n gemma-inference
```

When the dropdown swaps and requests different models, you will witness the Ollama server output:
* `source=runner.go ... load request="{Operation:alloc Model:gemma4:31b ...}"`
* `offloading 30 repeating layers to GPU` and re-loading weights dynamically in VRAM!

---

## 4. Verifying the Gemma Client Integration

The **Gemma Client Application** (`gemma-client/`) is the core user-facing interface that queries the Inference Gateway. In GDC air-gapped clusters, operators must verify that the client frontend and backend pods are healthy, connected to internal dynamic databases and object storage buckets, and communicating correctly with the gateway proxy.

### 4.1. Verify Client Pod Statuses
Verify that both the client backend and frontend pods are running securely inside the cluster namespace:
```bash
kubectl get pods -n gemma-inference -l app.kubernetes.io/part-of=gemma-client
```
*Expected Result*: Both pods should render a `Running` status with ready signals (`1/1 READY`).

---

### 4.2. Verify Database & Object Storage Connections (Workload Identity)
The client backend requires active connections to your dynamic in-cluster database (PostgreSQL) and GCS/S3 storage bucket. Stream the client backend container logs to assert successful handshakes:
```bash
kubectl logs -f deployment/gemma-client-backend -n gemma-inference
```
Confirm the output streams verify the Workload Identity credentials:
* `INFO:gemma-client:[Database] Successfully pooled connection to PostgreSQL instance at ...`
* `INFO:gemma-client:[Storage] Secure handshake established with bucket: gemma-client-files-...`

---

### 4.3. Hardened Connectivity Diagnostics (Exec-less Workaround)
Because production GDC-ag containers follow strict DevSecOps hardening standards, tools like `curl` and terminal shells are stripped from the client image. 

To verify that the client backend pod can reach the gateway proxy internally over GKE service DNS without a shell, execute a native Python `urllib` call directly inside the running container:
```bash
kubectl exec -it deployment/gemma-client-backend -n gemma-inference -- python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://gemma-gateway/api/config').read().decode())"
```
*Expected Result*: A successful JSON print containing the gateway's parameter configurations:
`{"temperature": 0.7, "top_p": 0.9, "model_variant": "26b"}`

---

### 4.4. End-to-End Client UI Badge Sync (Dynamic Hot-Swapping Verification)
1. Expose the Client Frontend service to your network workstation (or fetch the allocated GDC external LoadBalancer Ingress IP):
   ```bash
   # For local bastion port-forwarding
   kubectl port-forward svc/frontend-svc 8081:80 -n gemma-inference
   ```
2. Load the interface in your web browser at `http://localhost:8081` (or using your GDC Ingress URL).
3. **Initial State**: Confirm that the model badge chip rendered in the top-right header displays: **`Gemma 4 Gateway (Auto)`**.
4. **Test Conversational Routing (26B MoE)**:
   - In the chat input bar, type: `"Hello! How is your day going?"` and submit.
   - **Verify Badge Swap**: The header badge must instantly flip to **`Gemma 4 26B A4B (MoE)`** to reflect that the gateway classifier routed your conversational greeting to the latency-optimized MoE pod.
5. **Test Complex Reasoning Routing (31B Dense)**:
   - In the same session, type a coding trigger: `"Write a python function to calculate standard deviation"` and submit.
   - **Verify Badge Swap**: The header badge must instantly flip to **`Gemma 4 31B (Dense)`** to reflect that the classifier recognized the coding complexity keyword and dynamically redirected the prompt to the reasoning-optimized Dense pod!

