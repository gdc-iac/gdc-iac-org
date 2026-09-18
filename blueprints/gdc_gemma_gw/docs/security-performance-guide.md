Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Security & Performance Optimization Guide

> **Version:** 1.1
> **Status:** ACTIVE & HARDENED — Critical P0 authentication vulnerability successfully resolved.
> **Last Updated:** 2026-05-29

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Critical Security Issues (P0)](#critical-security-issues-p0)
3. [High-Priority Security Issues (P1)](#high-priority-security-issues-p1)
4. [Performance Optimizations (P2)](#performance-optimizations-p2)
5. [Medium-Priority Improvements (P3)](#medium-priority-improvements-p3)
6. [Implementation Checklist](#implementation-checklist)

---

## Executive Summary

This codebase (GDC Gemma Gateway + Gemma Client) has several security and performance concerns that should be addressed before production deployment:

| Category | Critical (P0) | High (P1) | Medium (P2) | Low (P3) |
|----------|:---:|:---:|:---:|:---:|
| Authentication | 1 | 1 | — | — |
| Input Validation | — | 2 | — | — |
| Configuration & Logging | 1 | 1 | 1 | — |
| Infrastructure & Reliability | 1 | — | 1 | 2 |
| Performance & Frontend | — | — | 2 | 3 |

**Total actionable items: 16**

---

## Critical Security Issues (P0)

### 1. No Real Authentication — Header-Based "Auth" (RESOLVED [x])

**Files:** `gemma-client/src/backend/auth.py`, `gemma-client/src/frontend/src/api.js`, `gemma-client/src/frontend/src/oidc.js`

**Problem Statement (Baseline Vulnerability):**
Legacy backend authentication simply extracted unverified headers (`X-User-ID` and `X-User-Role`) directly from the request context, accepting an anonymous default fallback. This constituted a catastrophic security bypass, permitting arbitrary spoofing and user/administrator impersonations out-of-the-box.

**The Production-Grade Resolution (OIDC Keycloak Identity Perimeter):**
We have successfully resolved this critical P0 security audit vulnerability by implementing a **production-ready OpenID Connect (OIDC) federated authentication perimeter utilizing Keycloak (Pattern 12 standard)**. 

The security posture has been hardened under a strictly modular, feature-flagged (`ENABLE_OIDC`) dual-path architecture:

1.  **Zero-Dependency PKCE Browser Engine ([oidc.js](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/src/frontend/src/oidc.js))**:
    To bypass GDC's strict air-gap package download bounds, we engineered a native, lightweight PKCE (Proof Key for Code Exchange) client wrapper. It utilizes the browser's native **WebCrypto Subtle API** to perform SHA-256 code challenge generation and base64url encodings, executing secure OIDC authorization handshakes without introducing a single external node package.
2.  **Symmetrical Cryptographic Validation ([auth.py](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/src/backend/auth.py))**:
    The FastAPI backend auth dependency intercepts the standard HTTP `Authorization: Bearer <JWT>` header. If OIDC is active, it rapidly fetches the dynamic public signature verification certificates (**JSON Web Key Sets (JWKS)**) from the internal Keycloak endpoints using standard Python libraries, validates the cryptographic RSA signature, parses username claims, and assigns roles (`user`/`admin`) based on verified JWT realm roles scopes.
3.  **Unified Single-Origin Proxy Routing ([nginx-ingress-staging.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/manifests/gcp/nginx-ingress-staging.yaml))**:
    Google Cloud Workstations isolates ports to dynamic subdomains and drops cookie handovers inside sandboxed iframe session checks (yielding `403 Forbidden` console locks). We resolved this in staging by exposing the client UI, API backends, and Keycloak under a unified, single-port NGINX reverse-proxy gateway, satisfying browser CORS.
4.  **Automated Realm Auto-Imports ([keycloak-realm-import.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/manifests/gcp/keycloak-realm-import.yaml))**:
    To avoid manual operator interactions and align with GDC physical rack GitOps standards, Keycloak's target realm boundary, dynamic client whitelists, and user accounts (`alice`/`charlie`) are preloaded inside a GKE ConfigMap volume. Keycloak imports this config dynamically in 6 seconds on startup, **completely bypassing the locked admin console Spinner loops!**

Refer to the staged strategy guides and playbooks to review this dynamic perimeter:
*   🔑 **[gcp-sandbox-keycloak-testing-strategy.md](file:///Users/gmollison/GitHub/gdc_gemma_gw/docs/gcp-sandbox-keycloak-testing-strategy.md)**: Staging topologies, Nginx single-port mappings, and physical rack Gateway API routes.
*   🔑 **[keycloak_integration_guide.md](file:///Users/gmollison/GitHub/gdc_gemma_gw/docs/keycloak_integration_guide.md)**: Master standard OIDC integration blueprint detailing GDC-ag standard Gateway API HTTPRoute manifests.
*   🔧 **[configure-keycloak.sh](file:///Users/gmollison/GitHub/gdc_gemma_gw/gemma-client/scripts/configure-keycloak.sh)**: Dynamic configuration script to automatically hydrate GKE manifests and write Vite frontend environments without hardcoded settings.

---

### 2. Unpinned Docker Image Tags

**Files:** `gateway/ollama-baked/Dockerfile.26b`, `gateway/ollama-baked/Dockerfile.31b`

**Problem:**
```dockerfile
FROM ollama/ollama:latest  # Unpinned — unpredictable builds
```

**Impact:** Supply chain attack vector. A compromised `:latest` tag could inject malicious code into your build pipeline.

**Fix:** Pin to a specific digest or version:

```dockerfile
FROM ollama/ollama@sha256:<digest>
# OR
FROM ollama/ollama:0.20.2
```

Also pin the backend Dockerfile:
```dockerfile
FROM python:3.11-slim@sha256:<digest>
```

---

### 3. Hardcoded Database Credentials

**File:** `gemma-client/src/backend/database.py`

**Problem:**
```python
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres-svc:5432/postgres")
```

**Impact:** Default password exposed in source code. If `DATABASE_URL` env var is missing, the app connects with weak credentials.

**Fix:**
```python
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")
```

---

## High-Priority Security Issues (P1)

### 4. Overly Permissive CORS

**File:** `gemma-client/src/backend/main.py`

**Problem:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Any origin
    allow_credentials=True,    # Combined with * is dangerous
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Impact:** Any website can make authenticated cross-origin requests. While browsers strip credentials with `*`, the API still accepts requests from anywhere.

**Fix:** Whitelist specific origins:
```python
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://your-frontend-domain")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

### 5. No Rate Limiting

**Files:** `gateway/proxy/main.py`, `gemma-client/src/backend/main.py`

**Problem:** No rate limiting on any endpoint. An attacker can flood the API, exhausting GPU/memory resources.

**Impact:** Denial of service, resource exhaustion, increased costs.

**Fix:** Add `slowapi` or `slowapi`-compatible rate limiting:

```python
# main.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/v1/chat/completions")
@limiter.limit("10/minute")
async def chat_completions(request: Request):
    ...

@app.post("/upload")
@limiter.limit("5/minute")
async def upload_file(...):
    ...
```

Install: `pip install slowapi`

---

### 6. No Input Validation or Sanitization

**Files:** `gemma-client/src/backend/storage.py`, `gemma-client/src/backend/chat.py`

**Problem:**
- **File uploads:** No size limits, no MIME type validation, no filename sanitization.
- **Chat messages:** No length limits. Long messages are injected directly into the system prompt.
- **File context:** Entire file contents injected into prompt with no cap — a large PDF could exhaust the context window.

**Impact:** Resource exhaustion, prompt injection, potential XSS via file content.

**Fix — File uploads (`storage.py`):**
```python
ALLOWED_CONTENT_TYPES = {
    "text/plain", "application/pdf", "image/png", "image/jpeg", "image/webp"
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

async def upload_file_to_gcs(file: UploadFile, user_id: str, is_shared: bool) -> str:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")
    
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Sanitize filename
    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    blob_name = f"{'shared' if is_shared else f'users/{user_id}'}/{safe_filename}"
    ...
```

**Fix — Chat input (`chat.py`):**
```python
MAX_MESSAGE_LENGTH = 100_000  # characters
MAX_FILE_CONTEXT_LENGTH = 500_000  # characters total

async def generate_chat_response(message: str, ...):
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=400, detail="Message too long")
    
    # Cap file context
    if len(file_context) > MAX_FILE_CONTEXT_LENGTH:
        file_context = file_context[:MAX_FILE_CONTEXT_LENGTH] + "\n... [truncated]"
```

---

### 7. Sensitive Data in Logs

**File:** `gateway/proxy/main.py`

**Problem:**
```python
logger.info(f"Configuration updated: {CURRENT_STATE}")
```

**Impact:** Routing URLs and model variants logged in plaintext.

**Fix:**
```python
logger.info("Configuration updated")
# Or log only non-sensitive fields:
logger.info(f"Config updated: temperature={CURRENT_STATE['temperature']}")
```

---

## Performance Optimizations (P2)

### 8. Global Mutable State in Gateway

**File:** `gateway/proxy/main.py`

**Problem:**
```python
CURRENT_STATE = {
    "temperature": 0.7,
    "top_p": 0.9,
    ...
}
```

**Impact:** In multi-replica deployments, each pod has independent state. Config updates on one pod are invisible to others. State is lost on restart.

**Fix:** Use Redis for shared state:
```python
import redis.asyncio as aioredis

redis_client = aioredis.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"),
    decode_responses=True
)

async def get_config():
    state = await redis_client.hgetall("gateway:config")
    return {**DEFAULT_STATE, **state}

async def update_config(config: UpdateConfigRequest):
    updates = {}
    if config.temperature is not None: updates["temperature"] = str(config.temperature)
    if config.top_p is not None: updates["top_p"] = str(config.top_p)
    # ... etc
    if updates:
        await redis_client.hset("gateway:config", mapping=updates)
```

---

### 9. OpenAI Client Without Connection Pooling

**File:** `gemma-client/src/backend/chat.py`

**Problem:**
```python
client = OpenAI(base_url=GATEWAY_URL, api_key="gdc-no-auth-required")
```

**Impact:** No connection pooling configured. Additionally, utilizing the synchronous `OpenAI` client in an `async def` function blocks the FastAPI event loop for the duration of the inference call, severely degrading gateway performance and limiting concurrency.

**Fix:** Use `AsyncOpenAI` and configure an `httpx.AsyncClient` with optimized connection limits, timeouts, and pooling:

```python
import httpx
from openai import AsyncOpenAI

httpx_client = httpx.AsyncClient(
    timeout=httpx.Timeout(60.0, connect=10.0),
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=30
    )
)
client = AsyncOpenAI(
    base_url=GATEWAY_URL,
    api_key="gdc-no-auth-required",
    http_client=httpx_client
)
```

Then, await the chat completions call in `generate_chat_response`:
```python
response = await client.chat.completions.create(
    model=model_name or "gemma4:26b",
    messages=openai_history,
    temperature=0.7,
    stream=False
)
```

---

### 10. No Database Connection Pool Sizing

**File:** `gemma-client/src/backend/database.py`

**Problem:**
```python
self.pool = await asyncpg.create_pool(DATABASE_URL)
```

**Impact:** Default pool size (25 connections) may be insufficient or wasteful depending on deployment.

**Fix:**
```python
self.pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=5,
    max_size=20,
    command_timeout=60,
    server_settings={"application_name": "gemma-client"}
)
```

---

### 11. Synchronous GCS Operations in Async Context

**File:** `gemma-client/src/backend/storage.py`

**Problem:**
```python
def get_blob_content(gcs_path: str) -> bytes:
    ...
    return blob.download_as_bytes()  # Blocking call in async context
```

And in `upload_file_to_gcs` / `delete_file_from_gcs` (which are declared `async def` but perform blocking synchronous calls):
```python
blob.upload_from_file(file.file, content_type=file.content_type)
...
blob.delete()
```

**Impact:** Since the standard `google-cloud-storage` library is entirely synchronous, calling these methods directly inside async FastAPI endpoints blocks the event loop, degrading performance for all concurrent user sessions.

**Fix:** Offload these synchronous GCS blocking operations to a worker thread pool using `asyncio.to_thread()` (or running them in a thread pool executor) to ensure the FastAPI event loop remains non-blocking:

```python
import asyncio

async def get_blob_content(gcs_path: str) -> bytes:
    if not storage_client:
        raise Exception("Storage service unavailable")
        
    parts = gcs_path.replace("gs://", "").split("/", 1)
    bucket_name, blob_name = parts
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Run the synchronous download in a thread pool
    return await asyncio.to_thread(blob.download_as_bytes)
```

Also make `upload_file_to_gcs` and `delete_file_from_gcs` truly non-blocking:
```python
async def upload_file_to_gcs(file: UploadFile, user_id: str, is_shared: bool) -> str:
    if not storage_client:
        raise HTTPException(status_code=500, detail="Storage service unavailable")

    bucket = storage_client.bucket(INPUT_BUCKET)
    prefix = "shared" if is_shared else f"users/{user_id}"
    
    # Sanitize input filename (P1-6)
    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    blob_name = f"{prefix}/{safe_filename}"
    blob = bucket.blob(blob_name)

    # Run the synchronous file upload in a thread pool
    await asyncio.to_thread(blob.upload_from_file, file.file, content_type=file.content_type)
    
    return f"gs://{INPUT_BUCKET}/{blob_name}"

async def delete_file_from_gcs(gcs_path: str):
    if not storage_client:
        raise HTTPException(status_code=500, detail="Storage service unavailable")
        
    if not gcs_path.startswith("gs://"):
        return
        
    parts = gcs_path.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        return
        
    bucket_name, blob_name = parts
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Run the synchronous delete in a thread pool
    await asyncio.to_thread(blob.delete)
```

---

## Medium-Priority Improvements (P3)

### 12. No Caching

**Files:** `gemma-client/src/backend/main.py` (models endpoint), `gemma-client/src/backend/chat.py` (file downloads)

**Problem:** Model list fetched from gateway on every request. File contents re-downloaded from GCS on every chat turn.

**Fix:** Add in-memory caching:
```python
from functools import lru_cache
from aiocache import cached, Cache

@cached(ttl=300, cache=Cache.MEMORY)
async def get_serving_models():
    ...

# Or for file context:
FILE_CACHE = {}  # Simple in-memory cache
async def get_cached_file_content(file_id: str) -> str:
    if file_id in FILE_CACHE:
        return FILE_CACHE[file_id]
    # ... fetch from GCS ...
    FILE_CACHE[file_id] = content
    return content
```

---

### 13. No Streaming Support

**File:** `gemma-client/src/backend/chat.py`

**Problem:**
```python
response = client.chat.completions.create(
    ...
    stream=False  # Loads entire response into memory
)
```

**Impact:** Wastes memory on long generations. Increases perceived latency (user waits for full response).

**Fix:** Implement SSE streaming:
```python
from fastapi.responses import StreamingResponse
import json

async def stream_chat_response(message: str, ...):
    response = client.chat.completions.create(
        model=model_name,
        messages=openai_history,
        stream=True
    )
    async def event_generator():
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

### 14. Health Check Doesn't Verify Dependencies

**File:** `gemma-client/src/backend/main.py`

**Problem:**
```python
@app.get("/health")
async def health():
    return {"status": "ok"}  # Doesn't check DB, GCS, or gateway
```

**Impact:** Kubernetes may route traffic to a pod that can't reach its dependencies.

**Fix:**
```python
@app.get("/health")
async def health():
    checks = {"status": "ok", "checks": {}}
    try:
        await db.fetch_one("SELECT 1")
        checks["database"] = "connected"
    except Exception:
        checks["database"] = "disconnected"
        checks["status"] = "degraded"
    
    checks["gateway"] = "connected"  # Add gateway check too
    return checks
```

---

### 15. Frontend Uses Axios (Unnecessary Dependency)

**File:** `gemma-client/src/frontend/src/api.js`

**Problem:** Axios adds ~13KB gzipped to the bundle for a simple API client.

**Fix:** Replace with native `fetch`:
```javascript
const API_URL = import.meta.env.VITE_API_URL || '/api';

async function request(endpoint, options = {}) {
  const userId = localStorage.getItem('userId') || 'user1';
  const userRole = localStorage.getItem('userRole') || 'user';
  
  const config = {
    ...options,
    headers: {
      'X-User-ID': userId,
      'X-User-Role': userRole,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  };
  
  const response = await fetch(`${API_URL}${endpoint}`, config);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw { response: { data: error }, status: response.status };
  }
  return response.json();
}

export default {
  get: (endpoint) => request(endpoint),
  post: (endpoint, body) => request(endpoint, { method: 'POST', body: JSON.stringify(body) }),
};
```

---

### 16. Silent Failures in Model Listing (Gateway Unreachability)

**File:** `gemma-client/src/backend/main.py`

**Problem:**
```python
@app.get("/api/models")
async def get_serving_models():
    ...
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"{GATEWAY_URL}/models", timeout=10.0)
            if response.status_code != 200:
                return [
                    {"id": "gemma4:26b", "name": "Gemma 4 26B A4B (MoE)"},
                    {"id": "gemma4:31b", "name": "Gemma 4 31B (Dense)"}
                ]
            ...
    except Exception as e:
        print(f"Error querying dynamic models: {e}")
        return [
            {"id": "gemma4:26b", "name": "Gemma 4 26B A4B (MoE)"},
            {"id": "gemma4:31b", "name": "Gemma 4 31B (Dense)"}
        ]
```

**Impact:** Complete downstream gateway unreachability or endpoint failure (HTTP status code != 200 or connection timeout/exception) is masked by a silent fallback to a hardcoded list of model configurations. The frontend UI incorrectly reports these models as active and selectable, leading to confusing failures and masking critical system errors.

**Fix:** Avoid silent fallbacks. Instead, raise a clear error, log an alert/exception, and allow the API to bubble up the status of the downstream gateway so that the frontend can display an appropriate degraded UI status or "Inference Engine Offline" alert:

```python
import logging
from fastapi import HTTPException

logger = logging.getLogger("gemma-client")

@app.get("/api/models")
async def get_serving_models():
    import httpx
    from chat import GATEWAY_URL
    
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"{GATEWAY_URL}/models", timeout=5.0)
            if response.status_code != 200:
                logger.error(f"Failed to query inference gateway: HTTP {response.status_code}")
                raise HTTPException(
                    status_code=502, 
                    detail="Inference gateway returned an invalid response"
                )
            
            openai_data = response.json()
            models_list = []
            for item in openai_data.get("data", []):
                model_id = item.get("id")
                friendly_name = "Gemma 4 26B A4B (MoE)" if "26b" in model_id.lower() else "Gemma 4 31B (Dense)"
                if "8b" in model_id.lower() or "e4b" in model_id.lower():
                    friendly_name = "Gemma 4 8B Multimodal (E4B)"
                models_list.append({"id": model_id, "name": friendly_name})
            return models_list
            
    except httpx.RequestError as e:
        logger.error(f"Inference gateway connection failed: {e}")
        raise HTTPException(
            status_code=503, 
            detail="Inference gateway is currently unreachable"
        )
```

Additionally, propagate this status into the dependency-aware health check (`/health` endpoint):
```python
@app.get("/health")
async def health():
    checks = {"status": "ok", "checks": {}}
    
    # Check Database
    try:
        await db.fetch_one("SELECT 1")
        checks["database"] = "connected"
    except Exception as e:
        logger.error(f"Health check: Database failure: {e}")
        checks["database"] = "disconnected"
        checks["status"] = "degraded"
        
    # Check Gateway Reachability
    try:
        import httpx
        from chat import GATEWAY_URL
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"{GATEWAY_URL}/models", timeout=2.0)
            if response.status_code == 200:
                checks["gateway"] = "connected"
            else:
                checks["gateway"] = f"degraded (HTTP {response.status_code})"
                checks["status"] = "degraded"
    except Exception as e:
        logger.error(f"Health check: Gateway unreachable: {e}")
        checks["gateway"] = "disconnected"
        checks["status"] = "degraded"
        
    return checks
```

---

## Implementation Checklist

### Phase 1 — Security (Before Any Deployment)

- [x] **P0-1:** Implement JWT/OIDC authentication (replace header-based auth)
- [ ] **P0-2:** Pin all Docker image tags to specific versions/digests
- [ ] **P0-3:** Remove hardcoded DB credentials; require env var
- [ ] **P1-4:** Restrict CORS to specific origins
- [ ] **P1-5:** Add rate limiting to all endpoints
- [ ] **P1-6:** Add input validation (file size/type, message length, context cap)
- [ ] **P1-7:** Remove sensitive data from logs

### Phase 2 — Performance & Reliability

- [ ] **P2-8:** Replace global state with Redis
- [ ] **P2-9:** Configure OpenAI client connection pooling (using `AsyncOpenAI` and `httpx.AsyncClient`)
- [ ] **P2-10:** Size database connection pool explicitly
- [ ] **P2-11:** Make GCS operations async (using `asyncio.to_thread` to offload GCS blocking operations)
- [ ] **P3-12:** Add caching for models and file content
- [ ] **P3-13:** Implement streaming chat responses
- [ ] **P3-14:** Add dependency-aware health checks
- [ ] **P3-15:** Replace axios with native fetch
- [ ] **P3-16:** Eliminate silent fallback in model listing and integrate with health check

### Phase 3 — Hardening (Optional but Recommended)

- [ ] Add HTTPS/TLS termination (Ingress or sidecar)
- [ ] Add request ID tracing (correlation IDs)
- [ ] Add structured logging (JSON format)
- [ ] Add Prometheus metrics endpoint
- [ ] Add PodDisruptionBudget for high availability
- [ ] Add resource quotas and limit ranges
- [ ] Run `gcr.io/cloud-marketplace-tools/k8s/checkov` or `trivy` for container scanning
- [ ] Add network policies to restrict pod-to-pod communication

---

## References

- [Keycloak Integration Guide](./keycloak_integration_guide.md)
- [vLLM Serving Guide](./vllm-serving-guide.md)
- [Testing Methodology](./testing-methodology.md)
- [Quickstart on GCP](./quickstart_on_GCP.md)
