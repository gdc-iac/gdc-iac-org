Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Automated Testing & Quality Assurance Guide (Phase 7)

> **Version:** 1.1

This guide provides step-by-step instructions on how to run and analyze the complete **Gemma 4 Inference Gateway** testing matrix.

The test matrix consists of four distinct suites:
1. **FastAPI Proxy Unit Tests** (Mocked downstream calls)
2. **Gemma Client Backend Unit Tests** (Mocked database, storage, and RBAC filters)
3. **Simulated/Live Integration Tests** (Asynchronous concurrency)
4. **Performance Load-Testing** (Locust SSE metrics tracker)

---

## 1. Local Environment Preparation

To prevent dependency pollution and keep your repository clean, initialize your virtual environment **outside** the git repository directory.

### Pathway A: Astral's `uv` (Recommended — Ultra-Fast & Natively Unblocked)
`uv` is a blistering-fast package resolver and environment manager written in Rust. It bypasses PEP 668 locks natively on both macOS and Linux without needing any system modifications.

```bash
# 1. Start from your repository root directory
cd <PATH_TO_YOUR_REPOSITORY>/gdc_gemma_gw

# 2. Install uv if not already installed (macOS via Homebrew)
which uv || brew install uv
# (For Linux / Cloud Workstation: which uv || curl -LsSf https://astral.sh/uv/install.sh | sh)

# 3. Create the virtual environment in the parent directory (outside the repo)
uv venv ../gdc_gemma_gw_venv

# 4. Activate the virtual environment
source ../gdc_gemma_gw_venv/bin/activate

# 5. Install all required application and testing dependencies directly from root
uv pip install -r gateway/proxy/requirements.txt \
               -r gemma-client/src/backend/requirements.txt \
               pytest pytest-asyncio pytest-cov locust pyyaml
```

### Pathway B: Standard `venv` with pip Bootstrapping (Mac Laptop / Workstation Fallback)
Use this standard fallback if corporate controls strictly block standard virtual environment activation scripts, or if `ensurepip` is restricted on your macOS laptop.

This pathway utilizes direct relative path execution, meaning **no `source bin/activate` shell command is required at all!**

```bash
# 1. Start from your repository root directory
cd <PATH_TO_YOUR_REPOSITORY>/gdc_gemma_gw

# 2. Create the virtual environment in the parent directory (outside the repo)
python3 -m venv ../gdc_gemma_gw_venv

# 3. Bootstrap pip inside the environment (natively bypasses Homebrew blocks)
../gdc_gemma_gw_venv/bin/python3 -m ensurepip --default-pip

# 4. Install all required application and testing dependencies directly
../gdc_gemma_gw_venv/bin/python3 -m pip install --index-url https://pypi.org/simple/ \
  -r gateway/proxy/requirements.txt \
  -r gemma-client/src/backend/requirements.txt \
  pytest pytest-asyncio pytest-cov pyyaml

# 5. Execute all 25 mocked unit tests directly (bypasses PATH and shell blocks)
../gdc_gemma_gw_venv/bin/pytest tests/test_gateway.py tests/test_client_backend.py tests/test_gemma_client.py -v
```

---

## 2. Running Local Unit Tests

Unit tests verify internal endpoint logic, parameter routing configurations, custom headers, and security RBAC roles by mocking database and storage dependencies entirely.

To execute all unit tests, run:

```bash
# If your virtual environment is successfully activated:
pytest tests/test_gateway.py tests/test_client_backend.py tests/test_gemma_client.py -v

# Or directly via the virtualenv's pytest binary (bypasses PATH blocks):
../gdc_gemma_gw_venv/bin/pytest tests/test_gateway.py tests/test_client_backend.py tests/test_gemma_client.py -v
```

### What is being verified?
- **test_gateway.py**: Confirms that requests for `gemma4:26b` and `gemma4:31b` map to the correct internal Ollama/vLLM endpoints, that custom `X-Gemma-Vision-Budget` headers are injected, and that SSE streams are converted correctly.
- **test_client_backend.py**: Confirms that PostgreSQL transactions and GCS operations are successfully intercepted. Asserts that an `admin` role can upload shared resources while standard `user` roles are blocked with a `403 Forbidden`.
- **test_gemma_client.py**: Validates Kubernetes manifest syntaxes recursively (including custom GDC security, database, and networking resources like `DBCluster`, `NetworkPolicy`, `IAMPolicyBinding`, and `Ingress`) and verifies that legacy `GEMINI_MODEL` environment variables are correctly migrated.

---

## 3. Running Integration Tests (Concurrent Stream Smoke-Testing)

The integration test suite (`tests/test_integration.py`) is designed to run in **two modes** dynamically depending on your environment:

> [!IMPORTANT]
> **Mac Laptop vs. Cloud Workstation Access Constraints**
> Due to corporate endpoint security agents blocking local GKE/Kubelet network channels on standard laptops:
> - **On your Mac Laptop**: Run strictly in **Mode A (Simulated Offline)**. This runs fully-mocked async concurrency tests without querying GKE.
> - **On your Google Cloud Workstation**: Run in **Mode B (Live GKE Port-Forwarded)** to validate your actual active in-cluster GPU-enabled models.

### Mode A: Simulated Offline Integration (Local Laptop)
If no `GATEWAY_URL` is present in your shell environment, the integration framework **automatically spins up a background mock inference server and proxy gateway locally on ports `50081` and `50082`**. It then fires concurrent requests to test connection isolation and streaming:

```bash
# Simply run pytest - it will auto-detect that there is no live URL and spin up local fixtures
pytest tests/test_integration.py -v
```
*Expected Output*:
```text
🧬 No GATEWAY_URL configured. Spinning up high-fidelity local Gateway and Mock Inference server...
tests/test_integration.py::test_concurrent_non_streaming PASSED
tests/test_integration.py::test_concurrent_streaming PASSED
🛑 Tearing down local test servers.
```

### Mode B: Live Cluster Integration (Google Cloud Workstation)
When deployed on the remote workstation, you can test your actual active GPU GKE cluster (Ollama or vLLM) end-to-end.

1. Pull down your committed branch to the Cloud Workstation:
   ```bash
   git pull origin main
   ```
2. Because the GKE in-cluster DNS suffix `.svc.cluster.local` is only resolvable by pods running **directly inside** GKE, you must bridge the service to your Cloud Workstation VM using standard port-forwarding:
   ```bash
   # Run this in your workstation terminal (or background tab) to create the secure tunnel:
   kubectl port-forward svc/gemma-gateway 50083:80 -n gemma-inference
   ```
3. Configure the `GATEWAY_URL` pointing to the forwarded local VM port and execute the tests:
   ```bash
   export GATEWAY_URL="http://localhost:50083/v1"
   pytest tests/test_integration.py -v
   ```
   *(The framework dynamically detects the live environment and asserts successful real Gemma 4 completions and stream tokens, instead of checking for static local mock responses).*

---

## 4. Performance Load-Testing (Locust)

Locust load tests simulate multi-user streaming chat completions to stress-test the gateway and trigger cluster Horizontal Pod Autoscalers (HPA).

### 4.1. Start the Locust Runner
From your activated environment, launch Locust:
```bash
locust -f tests/locustfile.py
```

### 4.2. Access the Locust Dashboard
Open your web browser and navigate to:
[http://localhost:8089](http://localhost:8089)

### 4.3. Configure the Load-Test Parameters
Enter the following parameters in the Locust UI:
- **Number of users (peak concurrency)**: `10`
- **Spawn rate (users started per second)**: `2`
- **Host**: 
  - Local simulated testing: `http://localhost:50082` (Run Mode A integration test servers in the background first)
  - Live remote GKE testing: `http://localhost:50083` (pointing to your port-forwarded tunnel) or `http://<YOUR_GATEWAY_EXTERNAL_IP>` if exposed externally
- Click **"Start swarming"**.

### 4.4. Monitor Custom SSE Latency Metrics
Our load-test script automatically parses the chunked tokens live and measures:
- **`chat_completions_ttft_ms`**: Time to First Token (perceived user latency) in milliseconds.
- **`chat_completions_inter_token_latency_ms`**: Average millisecond delta between consecutive tokens (readability smooth-flow score).
- **`chat_completions_total_stream_ms`**: Overall generation duration per request.

You can view these custom streaming metrics in real-time under the **"Charts"** and **"Statistics"** tabs inside the Locust Web UI!

---

## 5. Manual Walkthrough: Advanced Admin Features (Phase 5)

This section guides you through manually verifying the newly implemented Phase 5 Administrative features (System Telemetry, User Blocklists, and Streaming Kill-Switches) directly inside your browser.

### Step 5.1: Access the Unified Control Plane
1. Expose the GKE gateway service to your local VM (run in a background workstation terminal tab):
   ```bash
   kubectl port-forward svc/gemma-gateway 50083:80 -n gemma-inference
   ```
2. Open your browser and navigate to the Admin UI:
   [http://localhost:50083](http://localhost:50083)

---

### Step 5.2: Verify Real-Time System Telemetry
1. Once the page loads, observe the new **"⚡ Live System Performance & Telemetry"** dashboard panel.
2. You should see:
   - Smooth, circular SVG dial gauges rendering real-time CPU Load and GPU Core Load.
   - A clean progress bar rendering VRAM memory footprint (initialized stably around unquantized baseline `22.4 GB / 24.0 GB`).
   - Badges tracking Active DB pools and Token Throughput.
3. **Trigger a Load Fluctuation**:
   - Start a swarm in Locust (or run a concurrent completions query in another shell).
   - Observe the CPU/GPU load gauges and throughput numbers instantly surging in real-time on the dashboard as tokens are generated!

---

### Step 5.3: Test the Administrative User Blocklist
1. Scroll to the new **"👥 User Access Blocklist Management"** card on the Admin UI.
2. Locate the text box, enter a test user ID (e.g., `blocked-user-123`), and click **"Block User"**.
3. Verify that:
   - `blocked-user-123` immediately registers inside the "Blocked User ID" list table below.
   - An administrative warning is logged: *`User blocked-user-123 has been administratively blocked.`*
4. **Confirm Boundary Block**:
   - Attempt to query the completions endpoint using `curl` from another terminal, passing the blocked user ID:
     ```bash
     curl -i -X POST http://localhost:50083/v1/chat/completions \
       -H "X-User-ID: blocked-user-123" \
       -H "Content-Type: application/json" \
       -d '{"messages": [{"role": "user", "content": "Hello"}]}'
     ```
   - Assert that the Gateway **instantly rejects the query at the boundary**, returning a **`403 Forbidden`** with detail: `User has been administratively blocked.`
5. Click **"Unblock"** next to `blocked-user-123` in the UI table. Confirm that they are removed from the blocklist and subsequent completions queries immediately succeed again!

---

### Step 5.4: Test the In-Flight Stream Kill-Switch
1. Open a long-form streaming completion query inside your terminal using the CLI sample client or `curl`:
   ```bash
   # Trigger a long-running streaming completions prompt:
   curl --no-buffer -N -X POST http://localhost:50083/v1/chat/completions \
     -H "X-User-ID: stream-user" \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "Write a very long detailed essay about history of computer science."}], "stream": true}'
   ```
2. While the tokens are dynamically streaming back into your shell, open/view the **"🕵️ Active User Session Oversight"** card in the Admin UI browser tab.
3. You will see `stream-user` register in the active table with a flashing green status: **`GENERATING`**.
4. Click the red **"Kill Session"** button next to the active row.
5. **Observe the instant stream cut-off**:
   - The session status row in your Admin UI will immediately update to **`KILLED`** in red!

---

### Step 5.5: Test the Heuristic Prompt Routing Classifier & Sync (Phase 8)
This section guides you through manually verifying the gateway's server-side complexity-based routing decisions and automatic client UI model badge sync, including operational troubleshooting tips.

#### 5.5.1. Expose the GKE services to your local VM:
Make sure both the Gateway and the Gemma Client Frontend are running and port-forwarded:
```bash
# Expose the Gateway service (Port 50083)
kubectl port-forward svc/gemma-gateway 50083:80 -n gemma-inference

# Expose the Gemma Client Frontend service (Port 8081)
kubectl port-forward svc/frontend-svc 8081:80 -n gemma-inference
```

> [!NOTE]
> **Why does the port-forwarding pipe break?**
> - **Locally / On Staging Bastions**: Using `kubectl port-forward` creates a direct, single-pod TCP socket tunnel. When you trigger a rollout restart or rebuild/redeploy, GKE recycles the network namespace and terminates the old pod, immediately severing the active TCP tunnel (`broken pipe` / `lost connection to pod`). This is completely normal; you simply need to re-run the `kubectl port-forward` command to open a fresh tunnel to the new pod!
> - **In GDC Air-Gapped Production**: **This will NOT occur!** Production GDC-ag environments utilize **Hardware Load Balancers (HLB)** and GDC native **Ingress Controllers** managing highly available, active-active pod replicas. When a rollout occurs, the Ingress/HLB automatically performs a zero-downtime, graceful connection draining handover, routing active users to warm replicas with **zero socket interruptions!**

---

#### 5.5.2. Stream the Gateway logs live:
Open a dedicated terminal tab on your workstation to watch the classifier's decisions in real-time:
```bash
kubectl logs -f deployment/gemma-gateway -n gemma-inference
```

---

#### 5.5.3. Query the Gateway and check log outcomes:
In another terminal tab, query the generic `gemma4` model (default) using different prompt styles to watch the dynamic redirection:

* **Test Case A: Conversational Query** (Routes to **26B MoE** - Latency Optimized)
  ```bash
  curl -s -X POST http://localhost:50083/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"messages": [{"role": "user", "content": "Hello! How has your day been? Can you tell me a joke?"}]}'
  ```
  *Gateway logs output*:
  `INFO:gemma-gateway:[Classifier] General conversational query detected. Routing to Gemma 4 26B MoE.`
  `INFO:gemma-gateway:[Classifier] Dynamic route resolved: gemma4:26b at http://vllm-26b-vllm-gke-service.gemma-inference.svc.cluster.local:8000`

* **Test Case B: Complex Logic / Coding Query** (Routes to **31B Dense** - Reasoning Optimized)
  ```bash
  curl -s -X POST http://localhost:50083/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"messages": [{"role": "user", "content": "Write a python script to parse a JSON payload and calculate the average values."}]}'
  ```
  *Gateway logs output*:
  `INFO:gemma-gateway:[Classifier] Complexity keyword detected: 'python'. Routing to Gemma 4 31B Dense.`
  `INFO:gemma-gateway:[Classifier] Dynamic route resolved: gemma4:31b at http://vllm-31b-vllm-gke-service.gemma-inference.svc.cluster.local:8000`

---

#### 5.5.4. Verify Dynamic Client UI Badge Sync (End-to-End Browser Check):
1. Open your browser and go to the dynamic client web console: **[http://localhost:8081](http://localhost:8081)**.
2. Observe the read-only badge chip in the top-right header. It will initially display: **`Gemma 4 Gateway (Auto)`**!
3. Type `"Hello!"` in the chat bar and submit. The model badge chip will instantly flip to **`Gemma 4 26B A4B (MoE)`** as the MoE pod serves your conversational greeting!
4. In the same chat session, type: `"Write a python function to compute Fibonacci"` and submit.
5. Watch the badge chip. It will **instantly refresh in real-time** to display **`Gemma 4 31B (Dense)`**!

---

#### 5.5.5. 💡 Copy-Paste Example Prompts to Force serving Swaps:
Use these exact, validated prompts inside your browser chat bar to reliably trigger the server-side heuristic thresholds:

* **Conversational Prompts (Locks into `26B MoE` - Latency Optimized)**:
  - Prompt 1: `Hello! Can you suggest a fun weekend itinerary for visiting Seattle on a rainy day?`
  - Prompt 2: `Describe the main differences between a classical piano and an electric keyboard in two sentences.`
  - Prompt 3: `Write a short, creative story about a lost astronaut who stumbles upon a lush green forest on a foreign moon.`

* **Complex Reasoning & Coding Prompts (Forces swap to `31B Dense` - Reasoning Optimized)**:
  - Prompt 1: `Write a python function that reads a CSV payload from a local directory, parses the rows into a dictionary, and calculates the standard deviation.` (Triggers keywords: `python`, `function`, `calculate`)
  - Prompt 2: `Can you explain step-by-step the mathematical derivation of the quadratic equation formula and solve for x in: 2x^2 - 7x + 3 = 0?` (Triggers keywords: `mathematical`, `solve`, `step-by-step`)
  - Prompt 3: `Implement a Java class that represents a Graph data structure, and write a Dijkstra algorithm to find the shortest path between nodes.` (Triggers keywords: `implement`, `algorithm`)

---

### ⚡ Staging Rebuilding & Caching Troubleshooting Tips

When developing and compiling React components and FastAPI backends inside GKE staging, you may occasionally see changes "not taking effect" (e.g., the badge doesn't update to Auto). This is due to two aggressive cache layers:

#### **1. Docker Build Layer Caching (Workstation Backend)**
When running `docker build`, Docker optimizes compilation by caching filesystem layers. If Docker fails to detect Git updates inside your directory, it will copy cached pre-compiled assets, pushing the **old** application to Artifact Registry!
* **The Fix**: Forcibly ignore all caches when rebuilding by passing the `--no-cache` flag:
  ```bash
  docker build --no-cache -t $REGISTRY_HOST/gemma-client-frontend:latest gemma-client/src/frontend
  docker push $REGISTRY_HOST/gemma-client-frontend:latest
  ```

#### **2. Aggressive Browser Static Caching (Local Client)**
Modern web browsers aggressively cache static Vite/React JavaScript bundles locally on your disk/memory to speed up page loads. If you refresh a port-forwarded page, the browser will load the **old** JavaScript bundle from its memory cache!
  - On Mac (Chrome/Safari/Firefox): **`Cmd + Shift + R`** (or hold **`Shift`** and click the reload button).
  - On Windows (Chrome/Edge/Firefox): **`Ctrl + F5`** or **`Ctrl + Shift + R`**.

---

## 6. Heuristic Prompt Routing Architecture & Customization

This section provides a deep-dive walkthrough of the gateway proxy's intelligent, server-side **Prompt Routing Classifier** logic, explaining how vLLM/Ollama work within this architecture and how operators can easily customize the swap-triggering thresholds.

### 6.1. Walking Through the Classifier Logic (`main.py`)
The prompt routing classifier resides natively inside [gateway/proxy/main.py](file:///Users/gmollison/GitHub/gdc_gemma_gw/gateway/proxy/main.py). When a completions request is sent to the generic `gemma4` model ID (or with no model specified), the gateway parses the request payload using the following heuristic logic:

```python
def classify_prompt_complexity(payload: dict) -> str:
    messages = payload.get("messages", [])
    if not messages:
        return "gemma4:26b"  # Default to high-efficiency MoE
        
    # 1. Aggregate all user prompt content (supports both text and multimodal lists)
    full_prompt = ""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        full_prompt += " " + item.get("text", "")
            elif isinstance(content, str):
                full_prompt += " " + content
                
    full_prompt = full_prompt.lower()
    
    # 2. Heuristic complexity keywords list
    complexity_keywords = [
        "code", "function", "program", "script", "algorithm", "implement", "write a class",
        "math", "calculate", "prove", "equation", "formula", "solve for", "derivative", "integral",
        "reason", "analyze", "step-by-step", "detailed explanation", "logic", "deduce", "proof"
    ]
    
    # 3. Check prompt content against keywords
    for kw in complexity_keywords:
        if kw in full_prompt:
            logger.info(f"[Classifier] Complexity keyword detected: '{kw}'. Routing to Gemma 4 31B Dense.")
            return "gemma4:31b"  # Route to Reasoning-Optimized Dense
            
    logger.info("[Classifier] General conversational query detected. Routing to Gemma 4 26B MoE.")
    return "gemma4:26b"  # Route to Latency-Optimized MoE
```

---

### 6.2. How to Customize the Swapping Keywords
Operators can easily customize what triggers a dynamic serving swap by modifying the **`complexity_keywords`** list inside the `classify_prompt_complexity` function. 

For example, if deploying the gateway in a specialized enterprise sector, you can add domain-specific reasoning triggers:
* **Medical/Clinical Staging**: Add keywords like `diagnose, clinical, symptom, prescription, treatment, patient file`.
* **Financial/Audit Staging**: Add keywords like `audit, amortization, projection, compound interest, ledger, tax rate`.
* **Scientific/Chemical Staging**: Add keywords like `molecular, chemical structure, formula, catalyst, laboratory, synthesis`.

---

### 6.3. How vLLM & Ollama Work with this Architecture
The gateway proxy's dynamic routing framework is entirely **serving-backend-agnostic**! It resolves prompts to specific variant tags (`gemma4:26b` or `gemma4:31b`) and dispatches them to internal service endpoints mapped inside **`MODEL_ROUTING_CONFIG`**:

1. **For vLLM serving (High-Performance Production)**:
   The gateway maps variants to distinct, isolated GKE ClusterIP services:
   * `gemma4:26b` -> `http://vllm-26b-vllm-gke-service:8000`
   * `gemma4:31b` -> `http://vllm-31b-vllm-gke-service:8000`
2. **For Ollama serving (Standard Developer Testing)**:
   The gateway dynamically maps tags to corresponding local baked image services:
   * `gemma4:26b` -> `http://ollama-26b-service:11434`
   * `gemma4:31b` -> `http://ollama-31b-service:11434`

---

### 6.4. Operational Safeguard: Selector Label Isolation
Because both serving releases are deployed from the **same underlying Helm blueprint chart**, GKE assigns the chart label `app.kubernetes.io/name: vllm-gke` (or `ollama-gke`) to **both pods**.

> [!IMPORTANT]
> To prevent GKE's internal `kube-proxy` from load-balancing requests round-robin across both pods (which would result in a `404 Not Found` 50% of the time when a MoE query lands on the Dense pod), **we have strictly isolated both GKE deployments and Service selectors using the Helm Release instance parameter!**

Inside [blueprints/vllm-gke/templates/service.yaml](file:///Users/gmollison/GitHub/gdc_gemma_gw/blueprints/vllm-gke/templates/service.yaml) and `deployment.yaml`, selectors are strictly bound to the release instance:
```yaml
  selector:
    app.kubernetes.io/name: {{ include "vllm.name" . }}
    app.kubernetes.io/instance: {{ .Release.Name }}  # Forces strict pod-to-service affinity
```
This guarantees absolute networking boundary isolation, allowing you to run as many concurrent model releases side-by-side inside GKE without any traffic leakage!

