Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Envoy `InferencePool` + `epp` Endpoint Picker Blueprint (`blueprints/envoy-inference-pool`)

This optional Helm chart packages the Kubernetes **Gateway API Inference Extension (`InferencePool` + `epp` Endpoint Picker)** and **Envoy AI Gateway (`AIGatewayRoute` + `BackendTrafficPolicy`)** as an intelligent L7 backend load balancer and per-user token rate limiter behind `gdc_gemma_gw` (`gemma-gateway`).

---

## 1. Why Combine `gdc_gemma_gw` with `envoy-inference-pool`?

In a standard single-replica per model deployment (`vllm-26b` and `vllm-31b`), `gemma-gateway` routes directly to the Kubernetes `ClusterIP` services (`http://vllm-26b-vllm-service:8000` and `http://vllm-31b-vllm-service:8000`).

However, when scaling `vllm-26b` or `vllm-31b` horizontally across **multiple GPU replicas (`replicaCount > 1`)** or enforcing **strict per-user hourly token budgets**, standard Kubernetes round-robin `Service` load balancing is blind to LLM state:
1. **Prefix-Cache Misses**: Two turns of the same multi-turn RAG or coding session may land on different vLLM pods, forcing redundant prefill computation.
2. **KV-Cache Exhaustion & Queue Head-of-Line Blocking**: A round-robin `Service` may send a 32k-token prompt to a pod whose GPU KV-cache is already 95% full while another replica is idle.

By enabling `blueprints/envoy-inference-pool`, requests flow through a two-tier architecture:

```
Client / UI / IDE (Continue.dev, RAG, Data Analyst, Tactical Chat)
   │
   ▼
[gemma-gateway (gdc_gemma_gw FastAPI Control Plane)]
   ├─ 1. Verifies Keycloak OIDC JWT (`sub` / `preferred_username`)
   ├─ 2. Classifies Prompt Complexity (Gemma 4 26B MoE vs. 31B Dense)
   ├─ 3. Injects `X-Gemma-Vision-Budget`, `X-User-ID`, and `x-ai-eg-model`
   ├─ 4. Flattens unsupported `system` roles & normalizes `<thought>` / `reasoning` SSE
   │
   ▼
[gemma-envoy-inference-pool (Envoy AI Gateway + BackendTrafficPolicy)]
   ├─ 5. Enforces Per-User Token Rate Limits (`X-User-ID` + `llm_total_tokens`)
   ├─ 6. Matches `x-ai-eg-model` (`gemma4:26b` -> `vllm-26b-pool`, `gemma4:31b` -> `vllm-31b-pool`)
   │
   ▼
[Endpoint Picker (`vllm-26b-epp:9002` / `vllm-31b-epp:9002` gRPC ext_proc)]
   ├─ 7. Scrapes live Prometheus metrics (`:8000/metrics`) from all vLLM pods
   ├─ 8. Scores candidate pods via:
   │     • `prefix-cache-scorer` (weight: 3)
   │     • `kv-cache-utilization-scorer` (weight: 2)
   │     • `queue-scorer` (weight: 2)
   └─ 9. Prioritizes workloads via `InferenceObjective` (`priority: 100` for 26B interactive, `50` for 31B deep reasoning)
   │
   ▼
[Optimal vLLM Pod Replica (`vllm-26b-*` or `vllm-31b-*`)]
```

> **Automatic Fail-Safe**: If `apps.envoyInferencePool.enabled=true` is configured on `gemma-gateway` and the Envoy InferencePool service is temporarily unreachable, `gemma-gateway` automatically fails over to the direct `vllm-26b-vllm-service` / `vllm-31b-vllm-service` or `ollama-*-service` backends without dropping user requests.

---

## 2. What This Chart Deploys

| Resource Kind | API Group | Name(s) | Purpose |
| :--- | :--- | :--- | :--- |
| `InferencePool` | `inference.networking.k8s.io/v1` | `vllm-26b-pool`, `vllm-31b-pool` | Groups `vllm-26b` and `vllm-31b` pods (`port: 8000`) and delegates pod selection to `epp` (`failureMode: FailOpen`). |
| `InferenceObjective` | `inference.networking.x-k8s.io/v1alpha2` | `gemma4-26b-interactive`, `gemma4-31b-reasoning` | Assigns scheduling priority (`100` vs `50`) for queue shedding under saturation. |
| `Deployment` & `Service` | `apps/v1`, `v1` | `vllm-26b-epp`, `vllm-31b-epp` | Runs `registry.k8s.io/gateway-api-inference-extension/epp:v1.3.0` (mirrored to Harbor in air-gapped environments) with `runAsNonRoot: true` and native `global.imagePullSecrets`. |
| `ConfigMap` | `v1` | `vllm-26b-epp-config`, `vllm-31b-epp-config` | Configures `EndpointPickerConfig` weights (`prefix-cache-scorer: 3`, `kv-cache-utilization-scorer: 2`, `queue-scorer: 2`). |
| `Gateway` | `gateway.networking.k8s.io/v1` | `gemma-envoy-inference-pool` | Internal Envoy Gateway listener on port `80` (`gatewayClassName: envoy-ai-gateway`). |
| `ClientTrafficPolicy` | `gateway.envoyproxy.io/v1alpha1` | `gemma-envoy-inference-pool-buffer-policy` | Sets `bufferLimit: 50Mi` for multimodal images and large RAG payloads. |
| `AIGatewayRoute` | `aigateway.envoyproxy.io/v1beta1` | `gemma-envoy-inference-pool-route` | Routes `x-ai-eg-model: gemma4:26b` $\rightarrow$ `vllm-26b-pool` and `gemma4:31b` $\rightarrow$ `vllm-31b-pool`; extracts `llm_input_token`, `llm_output_token`, and `llm_total_tokens`. |
| `BackendTrafficPolicy` | `gateway.envoyproxy.io/v1alpha1` | `gemma-envoy-inference-pool-token-ratelimit` | Enforces per-user (`X-User-ID`) token budgets (`default: 50000 tokens / Hour`) charged dynamically from `io.envoy.ai_gateway.llm_total_tokens`. |

---

## 3. Prerequisites on the Cluster

Before enabling `envoy-inference-pool`, ensure the following CRDs and controllers are installed on your cluster (pre-packaged in GDC-ag AI Gateway environments):
1. **Gateway API Inference Extension CRDs (`v1.3.0`)**:
   - `inferencepools.inference.networking.k8s.io`
   - `inferenceobjectives.inference.networking.x-k8s.io`
2. **Envoy Gateway (`v1.7.0`) & Envoy AI Gateway (`v0.5.0`)**:
   - `GatewayClass` named `envoy-ai-gateway`
   - `aigatewayroutes.aigateway.envoyproxy.io`

---

## 4. Deployment Options

### Option A: Declarative GitOps via `gdc-iac-org` (Stage 5 `5-workload-factory`)

In your tenant environment file (e.g., `foundations/environments/dev/zone1.yaml`), add `envoy-inference-pool` to your project's `resources.patterns` list and set `apps.envoyInferencePool.enabled: true` on `gemma-gateway`:

```yaml
resources:
  patterns:
    # 1. vLLM 26B MoE Backend Pool (scaled to 2+ replicas for KV-cache routing)
    - name: vllm-26b
      pattern: gdc-gemma-vllm
      chart_path: "{{ .Values.gdc_gemma_vllm_chart_path }}"
      namespace: gemma-inference
      values:
        replicaCount: 2
        model:
          name: "google/gemma-4-26b-it"
          servedModelName: "gemma4:26b"

    # 2. vLLM 31B Dense Backend Pool
    - name: vllm-31b
      pattern: gdc-gemma-vllm
      chart_path: "{{ .Values.gdc_gemma_vllm_chart_path }}"
      namespace: gemma-inference
      values:
        replicaCount: 2
        model:
          name: "google/gemma-4-31b-it"
          servedModelName: "gemma4:31b"

    # 3. Optional Envoy InferencePool + epp Endpoint Picker + Token Rate Limiter
    - name: gemma-envoy-pool
      pattern: gdc-gemma-envoy-inference-pool
      chart_path: "{{ .Values.gdc_gemma_envoy_inference_pool_chart_path }}"
      namespace: gemma-inference
      values:
        tokenRateLimit:
          enabled: true
          limit: 50000
          unit: "Hour"

    # 4. Gemma 4 Smart Routing Gateway (wired to Envoy InferencePool)
    - name: gemma-gateway
      pattern: gdc-gemma-gateway
      chart_path: "{{ .Values.gdc_gemma_gateway_chart_path }}"
      namespace: gemma-inference
      values:
        apps:
          activeFramework: "vllm"
          enableOidc: true
          envoyInferencePool:
            enabled: true
            serviceUrl: "http://gemma-envoy-inference-pool:80"
```

### Option B: Standalone Helm Installation

```bash
# 1. Install the Envoy InferencePool + epp Endpoint Picker chart
helm upgrade --install gemma-envoy-pool ./blueprints/envoy-inference-pool \
  --namespace default \
  --set global.namespace=default \
  --set tokenRateLimit.enabled=true \
  --set tokenRateLimit.limit=50000

# 2. Upgrade gemma-gateway with apps.envoyInferencePool.enabled=true
helm upgrade --install gemma-gateway ./standalone/chart \
  --namespace default \
  --set global.namespace=default \
  --set apps.activeFramework=vllm \
  --set apps.enableOidc=true \
  --set apps.envoyInferencePool.enabled=true \
  --set apps.envoyInferencePool.serviceUrl="http://gemma-envoy-inference-pool:80"
```
