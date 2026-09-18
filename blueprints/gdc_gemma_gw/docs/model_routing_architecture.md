Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Model Routing & Selection Architecture
## Gemma 4 Dedicated Inference Gateway (GDC-ag)

> **Version:** 1.1

This document provides a comprehensive blueprint of the **Model Routing & Selection** layer within the Gemma 4 Dedicated Inference Gateway. It is structured specifically as a technical reference guide for architecture presentations and slide decks.

---

## 1. Architectural Big Picture

The gateway acts as an intelligent, OpenAI-compatible proxy between downstream client applications (e.g., agents, web clients, user scripts) and the underlying high-performance GKE-managed LLM serving pools (running **Ollama** or **vLLM** engines).

### Request Routing & Classification Lifecycle

Here is the architectural sequence and pipeline of requests moving through the gateway layers:

```
                  ┌──────────────────────────────────────────┐
                  │            DOWNSTREAM CLIENT             │
                  └────────────────────┬─────────────────────┘
                                       │
                         1. POST /v1/chat/completions
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │       GDC GATEWAY API (HTTPRoute)        │
                  └────────────────────┬─────────────────────┘
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │          GATEWAY PROXY (FastAPI)         │
                  └────────────────────┬─────────────────────┘
                                       │
                         [Check blocklist & metadata]
                                       │
                                       ├──────────────────────────┐
                                       │                          │
                        (Generic "gemma4" Model)       (Explicit "gemma4:31b")
                                       │                          │
                                       ▼                          │
                  ┌──────────────────────────────────────────┐    │
                  │      PROMPT CLASSIFIER HEURISTICS        │    │
                  └────────────────────┬─────────────────────┘    │
                                       │                          │
                         [Scan keywords for math/code]            │
                                       │                          │
                       ┌───────────────┴───────────────┐          │
                       ▼                               ▼          │
                 (Keywords Match)             (No Keywords Match) │
                       │                               │          │
             [Route to 31B Dense]            [Fallback to Active] │
                       │                     (e.g., MoE 26B)      │
                       ▼                               ▼          │
                  ┌─────────┐                     ┌─────────┐     │
                  │gemma4:31b│                     │gemma4:26b│     │
                  └────┬────┘                     └────┬────┘     │
                       │                               │          │
                       │       [Resolve Endpoint]      │          │
                       └───────────────┬───────────────┘          │
                                       │ <────────────────────────┘
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │    IN-MEMORY REGISTRY & ROUTING TABLE    │
                  │  (MODEL_ROUTING_CONFIG / CURRENT_STATE)  │
                  └────────────────────┬─────────────────────┘
                                       │
                      [Resolve Upstream URL & Parameters]
                                       │
                                       ▼
                  ┌──────────────────────────────────────────┐
                  │    LLM SERVING ENGINE (Ollama / vLLM)    │
                  └──────────────────────────────────────────┘
```

#### Pipeline Sequence Flow Diagram

```
  Client              Gateway Proxy               Classifier            LLM Serving
    │                       │                          │                     │
    │  1. completions request  │                          │                     │
    │──────────────────────>│                          │                     │
    │                       │──┐                       │                     │
    │                       │  │ Check Blocklist       │                     │
    │                       │<─┘                       │                     │
    │                       │                          │                     │
    │                       │─── 2. Evaluate Prompt ──>│                     │
    │                       │    (Heuristics Scan)     │                     │
    │                       │                          │──┐                  │
    │                       │                          │  │ Math/Code?       │
    │                       │                          │<─┘                  │
    │                       │<─── 3. Target Model ─────│                     │
    │                       │    (31B Dense or 26B MoE)│                     │
    │                       │                          │                     │
    │                       │──┐                       │                     │
    │                       │  │ Resolve Route & State │                     │
    │                       │<─┘                       │                     │
    │                       │                                                │
    │                       │─── 4. Downstream Proxy Request ───────────────>│
    │                       │    (Inject Custom Budgets & Headers)          │
    │                       │                                                │
    │                       │                                                │
    │                       │<─── 5. Stream Tokens / Responses ──────────────│
    │                       │    (Intercept via Kill Switch)                 │
    │<─── 6. SSE Stream ────│                                                │
    │                       │                                                │
```

---

## 2. Dynamic vs. Explicit Route Selection

The gateway's primary routing layer is located in [gateway/proxy/main.py](file:///Users/gmollison/GitHub/gdc_gemma_gw/gateway/proxy/main.py). It operates two modes: **Explicit Routing** and **Dynamic Classification**.

### 2.1 Explicit Model Tag Routing
If the client explicitly requests a specific model identifier mapping in `MODEL_ROUTING_CONFIG` (e.g., `model="gemma4:26b"` or `model="gemma4:31b"`), the routing layer bypasses dynamic text analysis and forwards directly to the target serving instance:
* Reference: [main.py:L305-L311](file:///Users/gmollison/GitHub/gdc_gemma_gw/gateway/proxy/main.py#L305-L311)

```python
# 1. If client explicitly requests a specific valid variant
if requested_model in MODEL_ROUTING_CONFIG and requested_model != "*":
    base_url = MODEL_ROUTING_CONFIG[requested_model]
    payload["model"] = requested_model
    determined_tag = requested_model
    logger.info(f"Routing to explicitly requested variant: {requested_model} at {base_url}")
```

### 2.2 Dynamic Classification (Heuristics-Based)
If the prompt specifies a generic model name like `"gemma4"` or skips it, the gateway invokes the prompt complexity engine to route requests to the most appropriate variant:
* Reference: [main.py:L312-L318](file:///Users/gmollison/GitHub/gdc_gemma_gw/gateway/proxy/main.py#L312-L318)

```python
else:
    # 2. Dynamic Prompt Routing Classifier (Generic / Default model)
    determined_tag = classify_prompt_complexity(payload)
    base_url = MODEL_ROUTING_CONFIG.get(determined_tag)
    if not base_url:
        base_url = MODEL_ROUTING_CONFIG.get("*")
    payload["model"] = determined_tag
    logger.info(f"[Classifier] Dynamic route resolved: {determined_tag} at {base_url}")
```

---

## 3. Inside the Complexity Classifier

The `classify_prompt_complexity` function analyzes user queries in real-time to match them against specific complexity markers:
* Reference: [main.py:L231-L271](file:///Users/gmollison/GitHub/gdc_gemma_gw/gateway/proxy/main.py#L231-L271)

```python
def classify_prompt_complexity(payload: dict) -> str:
    """
    Heuristically parses the request messages prompt.
    Returns 'gemma4:31b' (Dense) if complex logic, code, or math is detected.
    Returns the dynamic override variant (hot-swapped from Admin Control Plane) for general conversational queries.
    """
    messages = payload.get("messages", [])
    if not messages:
        fallback_variant = CURRENT_STATE.get("model_variant", "26b")
        return f"gemma4:{fallback_variant}"
        
    # Aggregate all user prompt content
    full_prompt = ""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                # Multimodal block content
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        full_prompt += " " + item.get("text", "")
            elif isinstance(content, str):
                full_prompt += " " + content
                
    full_prompt = full_prompt.lower()
    
    # Heuristic logic, coding, and math keywords list
    complexity_keywords = [
        "code", "function", "program", "script", "algorithm", "implement", "write a class",
        "math", "calculate", "prove", "equation", "formula", "solve for", "derivative", "integral",
        "reason", "analyze", "step-by-step", "detailed explanation", "logic", "deduce", "proof"
    ]
    
    for kw in complexity_keywords:
        if kw in full_prompt:
            logger.info(f"[Classifier] Complexity keyword detected: '{kw}'. Routing to Gemma 4 31B Dense.")
            return "gemma4:31b"
            
    fallback_variant = CURRENT_STATE.get("model_variant", "26b")
    logger.info(f"[Classifier] General conversational query detected. Routing to dynamic override: gemma4:{fallback_variant}")
    return f"gemma4:{fallback_variant}"
```

### Classification Outcomes

| Prompt Characteristics | Routed Model | Description & Architectural Purpose |
| :--- | :--- | :--- |
| Contains math, coding, algorithm, step-by-step, or logic keywords | **Gemma 4 31B (Dense)** | Employs high-reasoning capabilities of the full dense model to ensure correctness, code styling, and precision. |
| General chat, greeting, metadata lookup, plain text query | **Gemma 4 26B (MoE)** (Default) | Leverages target-routed Mixture-of-Experts routing logic for fast time-to-first-token (TTFT) and optimized resource cost. |
| Admin Hot-Swap Active Variant Override | **User's Selection (26b / 31b)** | Administrators can change `CURRENT_STATE["model_variant"]` using the web UI Dashboard to route all conversational traffic manually. |

---

## 4. Serving Infrastructure Configuration (YAML)

Under air-gapped deployment constraints (GDC-ag), the underlying routing endpoints are determined at startup by parsing cluster internal Service endpoints injected via environment variables in [standalone/manifests/01-gateway.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/standalone/manifests/01-gateway.yaml).

### Environmental Mapping Example

In production GKE contexts, the `MODEL_ROUTING_CONFIG` maps specific variants directly to kubernetes headless or ClusterIP services exposed by the backend GPU serving pools:
* Reference: [01-gateway.yaml:L33-L34](file:///Users/gmollison/GitHub/gdc_gemma_gw/standalone/manifests/01-gateway.yaml#L33-L34)

```yaml
- name: MODEL_ROUTING_CONFIG
  value: '{"gemma4:26b": "http://vllm-26b-vllm-gke-service.gemma-inference.svc.cluster.local:8000", "gemma4:31b": "http://vllm-31b-vllm-gke-service.gemma-inference.svc.cluster.local:8000", "*": "http://vllm-26b-vllm-gke-service.gemma-inference.svc.cluster.local:8000"}'
```

The gateway parses this configuration to hydrate dynamic route dictionaries:
* Reference: [main.py:L34-L35](file:///Users/gmollison/GitHub/gdc_gemma_gw/gateway/proxy/main.py#L34-L35)

```python
DEFAULT_ROUTING = '{"gemma4:26b": "http://ollama-26b-service:11434", "gemma4:31b": "http://ollama-31b-service:11434", "*": "http://ollama-26b-service:11434"}' if ACTIVE_FRAMEWORK == "ollama" else '{"gemma4:26b": "http://vllm-26b-vllm-gke-service:8000", "gemma4:31b": "http://vllm-31b-vllm-gke-service:8000", "*": "http://vllm-26b-vllm-gke-service:8000"}'
MODEL_ROUTING_CONFIG = json.loads(os.getenv("MODEL_ROUTING_CONFIG", DEFAULT_ROUTING))
```

---

## 5. Validating Routing Logic via Pytest

A robust set of automated testing patterns maintains zero-regression compliance for routing logic when integrating changes.

The tests are located in [tests/test_gateway.py](file:///Users/gmollison/GitHub/gdc_gemma_gw/tests/test_gateway.py):

1. **Routing and Header Verification Test:** `test_chat_completions_routing` runs mock completions and validates standard headers, routing matching, and backend endpoint targeting ([test_gateway.py:L45-L117](file:///Users/gmollison/GitHub/gdc_gemma_gw/tests/test_gateway.py#L45-L117)).
2. **Complexity Logic Check:** `test_prompt_routing_classifier_complex` ensures that code, programming, and mathematical reasoning prompts are automatically captured and routed to the 31B Dense model variant:
   * Reference: [test_gateway.py:L312-L346](file:///Users/gmollison/GitHub/gdc_gemma_gw/tests/test_gateway.py#L312-L346)
3. **Conversational Direct Check:** `test_prompt_routing_classifier_conversational` validates general greeting prompts stay routed to MoE 26B:
   * Reference: [test_gateway.py:L348-L383](file:///Users/gmollison/GitHub/gdc_gemma_gw/tests/test_gateway.py#L348-L383)
4. **Explicit Overriding Check:** `test_prompt_routing_classifier_explicit_override` tests that the client's direct request is preserved, bypassing the heuristic classifier entirely:
   * Reference: [test_gateway.py:L385-L420](file:///Users/gmollison/GitHub/gdc_gemma_gw/tests/test_gateway.py#L385-L420)
5. **Runtime Fallback & Dashboard Integration Check:** `test_prompt_routing_classifier_dynamic_fallback` verifies that when an administrator hot-swaps the active variant override, general queries immediately route to the new target variant:
   * Reference: [test_gateway.py:L442-L454](file:///Users/gmollison/GitHub/gdc_gemma_gw/tests/test_gateway.py#L442-L454)

---

## Summary Cheat-Sheet for Presenting

* **Gateway Routing Core:** A FastAPI proxy implementing OpenAI-compliant `/v1/chat/completions`.
* **Standard Framework Integration:** Interoperable with **Ollama** (development and sandbox pods) and **vLLM** (high-throughput paged-attention GKE node architecture).
* **The Smart Layer:** In-flight request classifiers parsing prompts for logic/math/code keywords, routing complex requests to **Gemma 4 31B (Dense)** and standard queries to resource-optimized **Gemma 4 26B (MoE)**.
* **Control Override:** Full dynamic admin hot-swap capability available via simple API endpoints (`/api/config`).
* **Clean Network Boundary:** Decouples internal GPU server instances using cluster DNS and environment mappings injected at deployment time.
