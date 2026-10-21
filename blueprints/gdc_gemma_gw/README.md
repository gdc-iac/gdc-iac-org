Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Gemma 4 Dedicated Inference Gateway (GDC-ag)

This repository contains the infrastructure and code for running a secure, high-performance Large Language Model gateway designed specifically for **Google Distributed Cloud air-gapped (GDC-ag)** environments.

---

## 📖 Documentation Hub & Reading Trails

All documentation is consolidated in the **[`docs/` Documentation Hub](docs/README.md)**, organized into four subfolders:
- **[`docs/tutorials/`](docs/README.md#1-tutorials--interactive-walkthroughs-docstutorials)**: Step-by-step end-to-end deployment guides, interactive GUI walkthroughs, and automated verification runbooks.
- **[`docs/architecture/`](docs/README.md#2-architecture--design-references-docsarchitecture)**: Reference architectures, prompt complexity routing design, GPU/VRAM T-shirt sizing, and security hardening.
- **[`docs/operations/`](docs/README.md#3-operations-packaging--troubleshooting-docsoperations)**: Air-gapped OCI/weight sideloading, production vLLM + Envoy `InferencePool` serving, Keycloak OIDC federation, Day-2 administration, and troubleshooting.
- **[`docs/testing/`](docs/README.md#4-testing--quality-assurance-docstesting)**: Automated unit/integration/load testing (`pytest` & `Locust`), GDC air-gapped smoke tests, and Keycloak sandbox strategies.

### Pathway 1: Testing and Developing on GCP (Staging Emulation)
If you are a developer validating features, testing prompt classifiers, or running the full AI-enabled blueprint stack on GKE:
1. 🎯 **[AI-Enabled Blueprint E2E Deployment Guide (GCP Staging)](docs/tutorials/ai_enabled_e2e_gcp_staging_guide.md)**: Complete end-to-end runbook deploying the Gemma Gateway (`8080`), Joint Intelligence & Chat Client (`8081`/`8082`), Kafka (`P4`), RAG (`P6`), SQL Analyst (`P7`), Keycloak (`P12`), and `gdc-dev` (`8083`/`8084`).
2. 🖥️ **[GUI Functional Walkthrough & Live Demo Playbook](docs/tutorials/gui_demo_walkthrough_and_prompts.md)**: Interactive browser walkthrough across all 5 ports (`8080`–`8084`) with copy-pasteable prompts to trigger `26B MoE` vs. `31B Dense` routing, RAG citations, Text-to-SQL, and `gdc-dev` IDE Swarm.
3. ✅ **[Zero-Tweak Automated E2E & IO/AO Verification Suite](docs/tutorials/e2e_zero_tweak_validation_runbook.md)**: Automated 17-check (`verify-e2e-gcp-staging.py`) and 20-check (`verify-e2e-gdc-ag.py`) CLI verification suites.
4. 📂 **[Standalone Gateway & Client GCP Quickstart](docs/tutorials/quickstart_on_GCP.md)**: Focused quickstart for provisioning GKE GPU node pools and deploying only the standalone Gateway and Chat Client.
5. 🔐 **[Keycloak OIDC Staging Strategy](docs/testing/gcp-sandbox-keycloak-testing-strategy.md)** & 🧪 **[Automated Testing & QA Guide](docs/testing/automated-testing-guide.md)**.
6. 🧠 **[FAQ & Operational Troubleshooting](docs/operations/faq-troubleshooting.md)**: Solutions for Cloud Workstation proxy cookies, dynamic storage claims, and regional GPU stock exhaustion.

---

### Pathway 2: Preparing and Deploying to GDC Air-Gapped (Production Target)
If you are an Infrastructure Operator (IO) or Application Operator (AO) packaging cluster assets or deploying to disconnected GDC air-gapped production racks:
1. 🎯 **[AI-Enabled Blueprint E2E Deployment Guide (GDC-ag Production IaC)](docs/tutorials/ai_enabled_e2e_gdc_production_iac_guide.md)**: Declarative multi-stage `gdc-iac-org` Helmfile (`0-bootstrap` $\rightarrow$ `5-workload-factory`) production deployment and IO/AO upgrade verification.
2. 📂 **[Gemma 4 Dedicated Inference Gateway Reference Manual](docs/architecture/Solution-Reference-Implementation-Gemma4-Inference-Gateway.md)**: Master blueprint detailing architecture, proxy classifier setup, serving engine pools (vLLM/Ollama), and `HTTPRoute` configuration on GDC-ag clusters.
3. 📂 **[Gemma 4 Client Application Reference Manual](docs/architecture/Solution-Reference-Implementation-Gemma4-Client-Application.md)**: Master blueprint for deploying the three-tier client web application, whitelisting cross-namespace ingress, database and object storage integration, and configuring native Keycloak OIDC.
4. 📦 **[Air-Gapped Packaging & Sideloading Guide](docs/operations/sideloading-guide.md)**: Package container image archives, stage gated Hugging Face model weights, and ingest assets into GDC Managed Harbor offline.
5. 🔐 **[Keycloak OIDC Integration Guide](docs/operations/keycloak_integration_guide.md)**: Establish Keycloak boundaries, lock down Web Origins, deploy GDC standard Gateway API `HTTPRoute` resources, and optimize internal KubeDNS resolution.
6. 💾 **[GDC Production Serving Guide: vLLM & Gemma 4](docs/operations/vllm-serving-guide.md)**: Dynamically provision `standard-rwx` PersistentVolumeClaims, mount unquantized weights, and configure concurrent dual-model vLLM serving with Envoy `InferencePool` (`epp`).
7. 🔌 **[GDC Air-Gapped Testing Methodology](docs/testing/testing-methodology.md)** & 🧠 **[FAQ & Operational Troubleshooting](docs/operations/faq-troubleshooting.md)**.

---

## Architecture

```text
                    [ User Browser / Client App User ]
                                   │
                                   ▼
                     [ GDC PLATFORM HLB / GATEWAY ] (app.gdc.local)
                                   │
             ┌─────────────────────┼─────────────────────┐
             │ (/auth)             │ (/api)              │ (/)
             ▼                     ▼                     ▼
         [Keycloak]        [gemma-client Backend] ◄─── [gemma-client Frontend]
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         │                                                   │
         │ (Option A: Same-Cluster)                          │ (Option B: Cross-Cluster)
         │ Connects directly via KubeDNS                     │ Connects via external LB host:
         │ http://gemma-gateway.gemma-inference              │ gemma-gateway.gdc.local
         │                                                   │
         ▼                                                   ▼
  [gemma-gateway Service]                             [ GDC PLATFORM HLB / GATEWAY ]
         │                                                   │
         └─────────────────────────┬─────────────────────────┘
                                   │
                                   ▼
                        [Gemma 4 Gateway Proxy]
                      (FastAPI Routing Classifier)
                                   │
                     ┌─────────────┴─────────────┐
           (Conversational)              (Complex/Math/Code)
                     ▼                           ▼
             [vLLM Serving Pod]          [vLLM Serving Pod]
             Gemma 4 26B (MoE)           Gemma 4 31B (Dense)
                     │                           │
                     └─────────────┬─────────────┘
                                   ▼
                             [GDC Storage]
```

## Quickstart (Local Testing)

**1. Set up Python Environment**
```bash
cd gateway/proxy
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Run the Proxy locally**
```bash
uvicorn main:app --reload --port 8080
```
Access the Admin UI at: [http://localhost:8080](http://localhost:8080)

## Testing the Gateway

Use the sample applications to test integration:
```bash
cd samples
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run a chat completion test
python chat_sample.py
```

For complete, step-by-step instructions on automated and manual testing across local development and GKE workstation environments, see the [Automated Testing & Quality Assurance Guide](docs/testing/automated-testing-guide.md) and the [GDC Testing Methodology](docs/testing/testing-methodology.md).

### Troubleshooting & FAQ

A dedicated, highly detailed operational manual is available in the [FAQ & Operational Troubleshooting Guide](docs/operations/faq-troubleshooting.md). This guide details:
- Differences between GCP GKE emulation environments and physical air-gapped GDC production racks.
- End-to-end dynamic model hot-swapping validation procedures across proxy payloads, serving logs, and client badge sync.
- Infrastructure blockers (CORS proxy failures, gated repos, immutable selector deadlocks, aggressive caching).
- Hardened DevSecOps diagnostic workarounds (exec-less Python connectivity checks).

---

* **Security First:** Strictly follows DevSecOps principles and GDC-ag hardening guidelines.  
* **Architectural Flexibility (Dual Serving Engines):**
  * **Ollama Engine (Rapid Model Testing & Sandboxing):** Ideal for rapid developers, quick application integration, and validation tests. It leverages quantized weights (e.g., GQUF) and features a significantly lighter resource footprint, making it simple to provision and hot-swap variants quickly on limited GPU setups without external gating issues.
  * **vLLM Engine (Production-Grade Inference Target):** The mandatory target for high-throughput, multi-tenant production environments on GDC-ag. It implements PagedAttention and continuous batching to maximize unquantized weight performance, drastically reduces VRAM fragmentation, and provides the enterprise scale required for production workloads.
* **Dual-Path Deployment:** Supports **GitOps** (GitLab \+ ConfigSync) or **Direct-to-Cluster** (Manual `kubectl` \+ Helm fallback).

## 2\. Production Architecture: Shared GDC Clusters

On GDC hardware, this Inference Gateway must be deployed to a **Shared Cluster** (System/Platform Cluster) rather than individual Standard User Clusters. 

**Why?**
1. **GPU Scarcity & Cost Efficiency**: H100/H200 GPUs are constrained resources on GDC. Deploying an LLM runtime inside every tenant's cluster requires significant amounts of VRAM. A shared cluster allows multi-tenant time-sharing on a central GPU pool.
3. **Centralized Governance**: This gateway handles API-Key validation, tenant mapping, and Request/Vision-Token budgeting. Operating as a core Platform Service ensures uniform policy enforcement across the air-gapped perimeter.

## 3. Resource Requirements (Production H100/H200 T-Shirt Sizes)

The tables below outline the GDC cluster resource requirements to support varying levels of enterprise query traffic and token workloads for both the **Ollama** (standard/testing) and **vLLM** (high-performance production) backend options, utilizing NVIDIA's **H100 (80GB)** and **H200 (141GB)** GPUs.

### Standard Enterprise Payload Benchmark:
- **Average Prompt Context**: **4,000 Input Tokens** (conversational prompts or large code chunks)
- **Average Completion Tokens**: **1,024 Output Tokens** (detailed analytical logic or derivation)
- **Total Session Context**: **5,024 Tokens**

---

### 3.1. Small Scale: Up to 600 Requests Per Minute (RPM)
- **Peak Load**: ~10 requests per second (RPS)
- **Target Total Throughput**: ~3,000,000 tokens per minute
- **Simultaneous Capacity**: **~200 - 300 active users** (assuming ~2 queries/min per user during active sessions)

| Backend | Recommended GDC Machine Type | vCPU | RAM | GPU Required | Storage (PVC) | Anticipated TTFT |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Ollama** | `hgx-h100-1g` | 16 | 96Gi | **1 x NVIDIA H100 (80GB)** | 150Gi | **~110ms** |
| **vLLM** | `hgx-h100-1g` | 16 | 120Gi | **1 x NVIDIA H100 (80GB)** | 150Gi | **~80ms** |

---

### 3.2. Medium Scale: Up to 3,000 Requests Per Minute (RPM)
- **Peak Load**: ~50 requests per second (RPS)
- **Target Total Throughput**: ~15,000,000 tokens per minute
- **Simultaneous Capacity**: **~1,000 - 1,500 active users** (assuming ~2 queries/min per user during active sessions)

| Backend | Recommended GDC Machine Type | vCPU | RAM | GPU Required | Storage (PVC) | Anticipated TTFT |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Ollama** | `hgx-h100-4g` | 64 | 384Gi | **4 x NVIDIA H100 (80GB)** | 150Gi/pod | **~100ms** |
| **vLLM** | `hgx-h200-1g` | 32 | 240Gi | **1 x NVIDIA H200 (141GB)** | 150Gi | **~70ms** |

---

### 3.3. Large Scale: Up to 6,000 Requests Per Minute (RPM)
- **Peak Load**: ~100 requests per second (RPS)
- **Target Total Throughput**: ~30,000,000 tokens per minute
- **Simultaneous Capacity**: **~2,000 - 3,000 active users** (assuming ~2 queries/min per user during active sessions)

| Backend | Recommended GDC Machine Type | vCPU | RAM | GPU Required | Storage (PVC) | Anticipated TTFT |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Ollama** | `hgx-h100-8g` | 128 | 768Gi | **8 x NVIDIA H100 (80GB)** | 150Gi/pod | **~90ms** |
| **vLLM** | `hgx-h200-2g` | 64 | 480Gi | **2 x NVIDIA H200 (141GB)** | 150Gi | **~60ms** |

---

### 3.4 Sizing & Architecture Sizing Methodology

> [!TIP]
> **ARCHITECTURAL COMPLIANCE REPORT:**
> The entire sizing matrix has been physically audited, verified, and signed off under detailed mathematical token flow derivations, VRAM KV cache pools calculations, and GDC-ag standard machine mappings! Proceed deeply into the master engineering report: **[docs/architecture/resource-sizing-validation.md](docs/architecture/resource-sizing-validation.md)**.

Our resource t-shirt sizing recommendations are formulated using dynamic token throughput calculations, standard GDC-ag architecture benchmarks, and three core engineering pillars:

1. **Dynamic KV Cache & GPU Memory Capacity (H100 vs. H200)**:
   While the static model weights for the unquantized Gemma 4 26B MoE (~52GB) and 31B Dense (~64GB) fit in a single 80GB H100, concurrent query processing causes rapid **Key-Value (KV) Cache** expansion. 
   - **NVIDIA H100 (80GB)**: Offers HBM3 memory bus speeds, accommodating ~600 RPM before caching saturates.
   - **NVIDIA H200 (141GB)**: Employs ultra-fast HBM3e memory. The larger VRAM cushion allows vLLM to expand the dynamic KV cache allocation, doubling overall concurrency capacity on a single GPU, making H200 the optimal choice for high-density multi-tenant workloads.
2. **Continuous Batching & Time to First Token (TTFT) Optimizations**:
   vLLM's paged memory allocations and continuous batching schedule overlapping token generations in real time. By dynamically interleaving the prefill phase (first token calculation) with active generation steps, the gateway delivers an extremely low anticipated TTFT (**~60ms - 80ms** on H200), maintaining smooth interactive generation speeds under massive transactional queues.
3. **Ollama Horizontal Pod Scaling vs. vLLM Consolidations**:
   Ollama relies on traditional runtime wrappers, meaning scaling to higher RPM thresholds requires deploying multi-pod replicas (e.g., 4-8 pods) mapped to isolated physical H100 GPUs. vLLM consolidates this footprint: by utilizing tensor parallel routing and massive HBM3e bus widths, a single H200 pod easily handles workloads that would otherwise require up to 8 individual Ollama containers, drastically reducing cluster resource overhead.

---

## 4. Docker Image Management & Cleanup

To support development and operational workflows on sandbox workstations, this repository provides a suite of helper scripts to clean up local Docker images. 

> [!IMPORTANT]
> **Project-Scope Safety Guardrails:**
> To prevent accidental data loss, these scripts will **only** target images belonging to this project. They identify relevant images based on known names (`gemma-proxy`, `ollama-gemma-*`, `vllm-gemma-*`, `gemma-client-*`) or tags matching the project's `REGISTRY_HOST`. Unrelated third-party images (such as base Postgres, system tools, or other projects) are protected.

### Available Cleanup Scripts

All scripts are located in the `scripts/` directory and support `--dry-run` (to preview deletions without modifying files) and `--force` (to bypass confirmation prompts):

1. **Clean All Project Local Images**
   ```bash
   ./scripts/clean-all-local-images.sh [--dry-run] [--force]
   ```
   Removes *every* local image built or tagged for this project across all tags and variants.

2. **Clean a Single Local Image**
   ```bash
   ./scripts/clean-single-local-image.sh <image_id_or_name> [--dry-run] [--force]
   ```
   Removes a single specified local image by ID or name/tag. If you attempt to delete an image not relevant to this project, a safety guardrail warning is displayed, requiring a confirmation bypass.

3. **Clean All Repo-Matching Images**
   ```bash
   ./scripts/clean-repo-all-images.sh [--dry-run] [--force]
   ```
   Cleans out all local images whose repository URLs match the configured project `REGISTRY_HOST`.

4. **Clean a Specific Project Image Component**
   ```bash
   ./scripts/clean-specific-image.sh <image_name_or_tag> [--dry-run] [--force]
   ```
   Removes all tags or a specific tag of a particular project component (e.g., `./scripts/clean-specific-image.sh gemma-proxy`).

---

### 🧠 Educational Note: Docker Layer Caching & Clean Starts

During rapid iteration, building, and debugging of local images (like the FastAPI Gateway Proxy or Ollama baked models), Docker's **layer-caching mechanism** can lead to subtle, hard-to-debug issues:
- **Stale Cache Retention**: If files change inside the Docker context but do not trigger a cache-busting instruction in the Dockerfile, Docker may reuse cached layers. This can result in a newly built image running *stale* source code or using outdated dependencies.
- **Gemma Weights Caching**: Large weights layers in baked models are heavily cached. When debugging model-prep or loading scripts, Docker's cache can bypass execution of these script blocks entirely.

#### Why Use Scenarios 2 & 4?
Using `./scripts/clean-single-local-image.sh` or `./scripts/clean-specific-image.sh` targets and wipes the cache of a **single specific image/component** without having to wipe your entire Docker environment. 
- It forces Docker to **reconstruct the filesystem layers** for that component from scratch.
- It guarantees that the newly built container runs the **exact, up-to-date source code** located on your workspace disk.
- It establishes a **100% deterministic and clean sandbox environment** to begin troubleshooting from.

---

## 5. Air-Gapped Packaging and Deployment (GDC-ag)

For instructions on how to build, package, and securely transfer the deployment assets to GDC production environments, refer to the [Air-Gapped Packaging & Sideloading Guide](docs/operations/sideloading-guide.md).

### Target Variables Configuration
Ensure you have configured the appropriate target destination variables before starting the pipeline:
```bash
export PROJECT_ID="your-gdc-project"
export NAMESPACE="gemma-inference"
export REGISTRY_HOST="harbor.gdc.local/library"
```

## 5. Smart Prompt Routing Classifier & Dual-Serving
This gateway implements a server-side **Smart Prompt Routing Classifier** that dynamically analyzes user prompts in real-time to direct queries to the optimal GKE serving backend, achieving a perfect balance between high-capacity reasoning and ultra-low latency:

- **💬 Conversational Heuristics (MoE 26B)**: Simple greetings, standard Q&A, and creative writing are automatically routed to the highly efficient **Gemma 4 26B A4B (MoE)** backend pod (`vllm-26b-service`), delivering peak speed and minimizing resource cost.
- **💻 Complexity Heuristics (Dense 31B)**: Prompts containing logic, coding, or math indicators (*code, python, math, solve, step-by-step*) are dynamically routed to the high-performance **Gemma 4 31B (Dense)** backend pod (`vllm-31b-service`) to leverage peak reasoning capabilities.
- **🔄 Dynamic Client UI Sync**: The React client application dynamically parses the served model tag returned in the API completions response and refreshes its read-only header badge dynamically in real-time (e.g., flipping between **`MoE`** and **`Dense`**), providing elegant user feedback of the gateway's server-side routing decisions.
- **⚡ GDC Production High-Availability**: In GDC-ag production, serving releases are connected to **Hardware Load Balancers (HLBs)** and active-active **Ingress Controllers**. Rollout restarts and upgrades perform graceful zero-downtime connection draining handovers, preserving active user socket connections perfectly without any port-forward severing.

## 6. Operations & UI
The Gateway includes a zero-dependency Vanilla HTML/CSS Admin Dashboard. It allows operators to view system metrics, CPU/GPU SVG gauges, VRAM progress, active session lists, and access blocklists.

## 7. Multi-User Client Application (gemma-client)
Located in the `gemma-client/` directory, this client serves as the user-facing interface for end users and agents querying the Inference Gateway inside the air-gapped perimeter:
- **Modern Web UI & FastAPI Backend**: Provides users with active multi-user session tracking, a visual toggle for model "thinking", dynamic model badge sync, and historical query caches.
- **Workload Identity Auth & Storage Emulation**: Interrogates the isolated database and storage service accounts, simulating production-grade air-gapped cloud resource provisioning exactly as mapped in `../GDC-blueprints/`.

### Air-Gapped Verification
Refer to the [GDC Testing Methodology](docs/testing/testing-methodology.md) for complete, terminal-only, disconnected test instructions using ephemeral test pods inside the cluster.

---

## Helm & IaC Orchestrated Deployment (`gdc-iac-org` Integration)

All Gemma Gateway and Gemma Client components include standardized Helm charts (`blueprints/ollama-gke`, `blueprints/vllm-gke`, `blueprints/envoy-inference-pool`, `standalone/chart`, and `gemma-client/chart`) compatible with the `gdc-iac-org` layered Helmfile orchestration (`foundations/releases/5-workload-factory`).
- **Zonal Managed Databases (`Stage 2: 2-resources`)**: Provisioned via core `charts/gdc-dbs` (`gdc.enabled: false` by default in `gemma-client/chart`).
- **Shared/User Cluster GPU Node Pools (`Stage 3: 3-clusters`)**: Provisioned via `charts/gdc-clusters` with `hgx-h200-1g` (NVIDIA H200 141GB) node pools (`pool: gpu-moe` and `pool: gpu-dense`).
- **Optional Envoy `InferencePool` + `epp` Endpoint Picker (`blueprints/envoy-inference-pool`)**: When scaling `vllm-26b` or `vllm-31b` across multiple GPU replicas (`replicaCount > 1`) or enforcing strict per-user hourly token budgets, enable [`blueprints/envoy-inference-pool`](blueprints/envoy-inference-pool/README.md). `gemma-gateway` acts as the L7 Gemma-aware Control Plane (verifying Keycloak OIDC JWTs, classifying prompt complexity, injecting `X-User-ID` and `x-ai-eg-model`) and forwards traffic to `gemma-envoy-inference-pool`, which enforces per-user token rate limits (`BackendTrafficPolicy` + `llmRequestCosts`) and delegates pod selection to the Gateway API Inference Extension `epp` Endpoint Picker (`prefix-cache-scorer`, `kv-cache-utilization-scorer`, and `queue-scorer`).
- **Cluster Workloads (`Stage 5: 5-workload-factory`)**: Declared under `projects[].resources.patterns[]` in `foundations/bases/environments/<env>/zone1/tenant-1.yaml` using `values_files` to load `values-gdc.yaml`:

```yaml
              patterns:
                - name: "vllm-26b"
                  pattern: "gdc-gemma-vllm-26b"
                  chart_path: "../../../blueprints/gdc_gemma_gw/blueprints/vllm-gke"
                  namespace: "gemma-inference"
                  registry: "harbor.gdc.local/gemma-repo"
                  deploy_gdc_resources: false
                  deploy_apps: true
                  values_files:
                    - "../../../blueprints/gdc_gemma_gw/blueprints/vllm-gke/values-gdc.yaml"
                  values:
                    replicaCount: 2
                    model:
                      name: "/models/gemma-4-26B-A4B-it-weights"
                      servedModelName: "gemma4:26b"
                    nodeSelector:
                      pool: "gpu-moe"

                - name: "vllm-31b"
                  pattern: "gdc-gemma-vllm-31b"
                  chart_path: "../../../blueprints/gdc_gemma_gw/blueprints/vllm-gke"
                  namespace: "gemma-inference"
                  registry: "harbor.gdc.local/gemma-repo"
                  deploy_gdc_resources: false
                  deploy_apps: true
                  values_files:
                    - "../../../blueprints/gdc_gemma_gw/blueprints/vllm-gke/values-gdc.yaml"
                  values:
                    replicaCount: 2
                    model:
                      name: "/models/gemma-4-31B-it-weights"
                      servedModelName: "gemma4:31b"
                    persistence:
                      existingClaim: "vllm-26b-vllm-weights"
                    nodeSelector:
                      pool: "gpu-dense"

                # Optional: Envoy InferencePool + epp Endpoint Picker & Per-User Token Rate Limiter
                - name: "gemma-envoy-pool"
                  pattern: "gdc-gemma-envoy-inference-pool"
                  chart_path: "../../../blueprints/gdc_gemma_gw/blueprints/envoy-inference-pool"
                  namespace: "gemma-inference"
                  registry: "harbor.gdc.local/gemma-repo"
                  deploy_gdc_resources: false
                  deploy_apps: true
                  values:
                    tokenRateLimit:
                      enabled: true
                      limit: 50000
                      unit: "Hour"

                - name: "gemma-gateway"
                  pattern: "gdc-gemma-gateway"
                  chart_path: "../../../blueprints/gdc_gemma_gw/standalone/chart"
                  namespace: "gemma-inference"
                  registry: "harbor.gdc.local/gemma-repo"
                  deploy_gdc_resources: false
                  deploy_apps: true
                  values:
                    apps:
                      activeFramework: "vllm"
                      envoyInferencePool:
                        enabled: false # Set to true when gemma-envoy-pool is deployed
                        serviceUrl: "http://gemma-envoy-inference-pool:80"

                - name: "gemma-client"
                  pattern: "gdc-gemma-client"
                  chart_path: "../../../blueprints/gdc_gemma_gw/gemma-client/chart"
                  namespace: "mellons-prj"
                  registry: "harbor.gdc.local/gemma-repo"
                  deploy_gdc_resources: false
                  deploy_apps: true
                  values:
                    apps:
                      gatewayUrl: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
                      hostnames: ["app.gdc.local"]
```

