Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 14: GDC-ag Antigravity SDK & Integrated Notebooks Developer IDE Platform (`p14-antigravity-dev`)**

> **Version:** 1.3  
> **Specification ID:** `REQ-GDC-AG-DEV-PLATFORM-001`  
> **Target Environment:** Google Distributed Cloud Air-Gapped (`GDC-ag`)

---

## **1. Overview & GDC Air-Gapped Architecture**

Pattern 14 (`p14-antigravity-dev`) provides an air-gapped developer workspace and MLOps notebook platform for **Google Distributed Cloud Air-Gapped (`GDC-ag`)**. It unifies **Interactive Application & Infrastructure Engineering (`/ide/`)** and **Interactive MLOps & Data Science Notebooks (`/lab/`)** inside a single per-developer Kubernetes workspace pod, authenticated via **Keycloak OIDC (`p12-keycloak`)** and governed by a dedicated **Sovereign Admin & Telemetry Console** on an isolated listener port (`8081`).

```text
+---------------------------------------------------------------------------------------------------+
|                                   GDC Air-Gapped Cluster (GDC-ag)                                 |
|                                                                                                   |
|  [Developer Browser]                  [Keycloak OIDC IdP]                [Platform Admin Browser] |
|  https://dev.gdc.local     <---OIDC--- https://keycloak.gdc.local --OIDC--> https://admin.dev...  |
|  (dev_auth_user Cookie)      SSO/JWT   (p12-keycloak / keycloak-svc)  RBAC  (admin_auth_user)     |
|               |                        - Realm: gdc-dev-realm                          |          |
|               |                        - Realm: gdc-rag-realm                          |          |
|               +--------------------+              |              +---------------------+          |
|                                    |              | (OIDC /auth/callback & RS256 JWKS) |          |
|                                    v              v                                    v          |
|                +------------------------------------------------------------------+               |
|                |         Kubernetes Gateway API (gdc-dev-gateway / Envoy)         |               |
|                |         + OIDC Auth Config (X-Forwarded-User / Groups / RBAC)    |               |
|                +------------------------------------------------------------------+               |
|                          | (Port 8080: /ide/, /lab/)        | (Port 8081: /admin/)                |
|                          v                                  v                                     |
|  +---------------------------------------------------------------------------------------------+  |
|  |                     gdc-dev-landing-page / Workspace Session Pod                            |  |
|  |                                                                                             |  |
|  |  +-------------------------------------------+  +----------------------------------------+  |  |
|  |  | Unified Developer Surface (Port 8080)     |  | Sovereign Admin Console (Port 8081)    |  |  |
|  |  | - Keycloak OIDC SSO (/auth/callback)      |  | - OIDC RBAC Guard (gdc-admin/dev-admin)|  |  |
|  |  | - Code IDE (/ide/)                        |  | - 4-Up KPI Grid (Sessions, Latency)    |  |  |
|  |  | - Integrated JupyterLab 4 (/lab/)         |  | - Real-Time Cluster Broadcast Push     |  |  |
|  |  | - Antigravity Multi-Agent Swarm Dock      |  | - Dynamic AI Governance Policies       |  |  |
|  |  | - Integrated Bash Terminal                |  | - Model & Persona Distributions        |  |  |
|  |  +---------------------+---------------------+  | - Session Hibernate / Evict Table      |  |  |
|  |                        |                        | - Live Agentic Inference Audit Log     |  |  |
|  |                        v                        +----------------------------------------+  |  |
|  |  +---------------------------------------------------------------------------------------+  |  |
|  |  | Antigravity SDK Hybrid Orchestrator (gdc_agy_orchestrator.py + gdc_antigravity_magic) |  |  |
|  |  | - Configs: LocalOpenAIAgentConfig.lightweight() | LiteRTAgentConfig | LocalAgentConfig|  |  |
|  |  | - Skills : /opt/p14-antigravity/skills/*/SKILL.md (Hot-Reloadable)                    |  |  |
|  |  | - Tools  : read_file, apply_diff, write_file, notebook_*_cell, run_terminal_command   |  |  |
|  |  | - Guard  : SAFE_ENV Secret Scrubbing + PoLP Role Policies + .ipynb.bak Snapshots      |  |  |
|  |  +---------------------------------------------------------------------------------------+  |  |
|  +-----------------|--------------------------------------|-----------------------------|------+  |
|                    |                                      |                             |         |
|                    v (GDC Block & Shared PVCs)            v (OIDC Token & JWKS)         v (HTTPS) |
|     +-----------------------------+     +-------------------------------+   +------------------+  |
|     | /home/dev/workspace (RWO)   |     | keycloak-svc (p12-keycloak)   |   | gemma-gateway    |  |
|     | /workspace/shared   (RWX)   |     | - gdc-dev-realm (gdc-dev-cli) |<->| (gemma-inference)|  |
|     | notebooks/*.ipynb           |     | - gdc-rag-realm (AI GW OIDC)  |   | - gemma4:26b/31b |  |
|     +-----------------------------+     +-------------------------------+   +------------------+  |
+---------------------------------------------------------------------------------------------------+
```

### **1.1 GDC-ag Endpoint & Port Matrix**

> [!NOTE]
> Identity values (`<developer-user>@<org-domain>`, `<platform-admin>@<org-domain>`, and `<gateway-admin-user>`) represent accounts provisioned in your organization's production **Keycloak (`p12-keycloak`)** realms (`ALLOW_SIMULATED_OIDC: "false"` in [`manifests/gdc/oidc-auth-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/oidc-auth-configmap.yaml)). See [Section 2.4 of `p14-antigravity-dev/README.md`](../../p14-antigravity-dev/README.md#24-configuring-keycloak-oidc-for-production-gdc-dev-realm--rbac-claims) and [`docs/operations/keycloak_integration_guide.md`](../operations/keycloak_integration_guide.md) for production Keycloak configuration.

| GDC-ag FQDN | Container Port | Target Service | Login Identity & Cookie Scope | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`https://dev.gdc.local`** | `8080` | `svc/gdc-dev-landing-page` (`gdc-dev`) | `<developer-user>@<org-domain>` (`dev_auth_user` HMAC cookie via Keycloak `gdc-dev-realm`) | **Pattern 14 Unified Developer IDE (`/ide/`) & Integrated JupyterLab 4 (`/lab/`)**: Code editor, `.ipynb` notebook drawer, `%%agy_*` cell magics, Multi-Agent AI Swarm dock, and integrated bash terminal. |
| **`https://admin.dev.gdc.local`** | `8081` | `svc/gdc-dev-landing-page` (`gdc-dev`) | `<platform-admin>@<org-domain>` (`admin_auth_user` HMAC cookie; `gdc-admin` / `dev-admin` role in `gdc-dev-realm`) | **Sovereign Admin & Telemetry Console**: Real-time AI Swarm invocation audit log, model/persona utilization bars, cluster broadcast banner, dynamic policy overrides, session hibernation/termination, and `GET /agy-config`. |
| **`https://keycloak.gdc.local`** | `8080` (`8443`) | `svc/keycloak-svc` (`platform` / `gemma-inference`) | `gdc-dev-realm` (`gdc-dev-client`) & `gdc-rag-realm` | **Keycloak OIDC Identity Provider (`p12-keycloak`)**: Issues RS256 OIDC JWTs, handles `/auth/callback` SSO redirects, and enforces RBAC group claims (`X-Forwarded-User` / `X-Forwarded-Groups`) for both `gdc-dev` and `gemma-gateway`. |
| **`https://ai-gateway.gdc.local`** | `443` (`8000`) | `svc/gemma-gateway` (`gemma-inference`) | `<gateway-admin-user>` (`admin` role via Keycloak `gdc-rag-realm`) | **Gemma 4 Inference Gateway Control Plane**: GPU/VRAM telemetry, temperature/model overrides, active session kill-switch, and user blocklist. |

---

## **2. Key Solution Capabilities**

* **Antigravity SDK Tri-Backend Orchestration (`gdc_agy_orchestrator.py`):**
  * **`gdc_gemma_gw` *(Default)*:** `LocalOpenAIAgentConfig.lightweight()` (`AgentBehavior.MINIMAL`, `enable_subagents=False`, `enable_knowledge=False`, `token_threshold=40960`) routing to `http://gemma-gateway.gemma-inference.svc.cluster.local/v1` (`gemma4:26b` Fast MoE and `gemma4:31b` Dense Reasoning).
  * **`litert_on_device`:** `LiteRTAgentConfig.lightweight()` (`download_if_missing=False`, `enable_speculative_decoding=True`, `token_threshold=16384`) for GPU-enabled MLOps pods loading pre-staged `/opt/models/gemma4-26b/model.litertlm`.
  * **`gdc_gemini`:** `LocalAgentConfig(model="gemini-3.5-flash", ...)` (`128,000`-token window with STS Bearer auth) for GDC Air-Gapped Chat Completions API escalation.
* **4 Specialist Personas & Principle of Least Privilege (PoLP):**
  * **`📐 Architect Agent` (`gemma4:31b`):** Read-only confinement producing typed `BlueprintAdaptationPlan` JSON and Markdown architecture specifications.
  * **`💻 Coder Agent` (`gemma4:26b`):** Selective Human-in-the-Loop (`ASK_USER`) mutation approval with automatic `.bak` and `.ipynb.bak` rollback snapshots.
  * **`🔍 Reviewer Agent` (`gemma4:26b`):** Predicate-guarded verification (`is_safe_verify_cmd`) with `SAFE_ENV` secret scrubbing (`KEYCLOAK_CLIENT_SECRET`, `GDC_GEMINI_API_KEY`, `ADMIN_COOKIE_SECRET` stripped).
  * **`🐝 Multi-Agent Swarm (Auto Pipeline)`:** Sequential 3-stage handoff (`📐 Architect` $\rightarrow$ `💻 Coder` $\rightarrow$ `🔍 Reviewer`) with 1-click **`⚡ Auto-Create All Swarm Files (3)`** artifact extraction.
* **Modular Hot-Reloadable GDC Skills (`SKILL.md`):**
  * Ships with 4 pre-installed GDC domain skills (`gdc-blueprint-adaptation`, `gdc-e2e-iac-knitting`, `gdc-notebook-mlops`, `gdc-security-opa`) mirrored into the Code IDE `📁 skills/` Explorer tree, plus a ClickOps `SKILL.md` Studio Drawer (`➕ + New SKILL.md`) that hot-reloads skills without pod restarts.
* **Co-Located Integrated JupyterLab 4 (`/lab/`), `.ipynb` v4 Tools & IPython Magics:**
  * Structured `.ipynb` v4 cell tools (`list_cells`, `get_cell_outputs`, `add_cell`, `edit_cell`, `delete_cell`, `run_cell`, `run_all_cells`, `rollback_cell`) and IPython cell magics (`%%agy_architect`, `%%agy_builder`, `%%agy_verify`, `%agy_fix`) sharing the developer's `/home/dev/workspace` PVC and OIDC session cookie.
* **Dual-Port Sovereign Admin & Telemetry Console (`Port 8081`):**
  * Isolated administrative port (`admin_auth_user` HMAC cookie) providing a 4-Up Executive KPI Grid, real-time Cluster Broadcast Notification push, dynamic AI governance policy controls, model/persona utilization bars, session hibernation/termination, and a Live Agentic Inference Audit Log.

---

## **3. Resource Requirements (T-Shirt Sizes) & Compute Profiles (`GDC-ag`)**

### **3.1 Component-Level Resource Requirements**

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Control Plane (`gdc-dev-operator` & `gdc-dev-landing-page`)** | `n2-standard-4-gdc` | `4` | `16 GiB` | N/A | **No** |
| **Dynamic Workspace Pod — Profile A (`computeProfile: "cpu-gateway"`, Default)** | `n2-standard-8-gdc` (Shared Pool) | `2–4` (Per Pod) | `8–16 GiB` (Per Pod) | `20–50 GiB` (`standard-rwo`) + `100 GiB` (`standard-rwx` Shared Team Git) | **No** (Routes to shared `gdc_gemma_gw` with `40,960` compaction threshold) |
| **Dynamic Workspace Pod — Profile B (`computeProfile: "gpu-litert-notebook"`, MLOps)** | `g2-standard-12-gdc` or `a2-highgpu-1g` | `8–12` (Per Pod) | `32–48 GiB` (Per Pod) | `100 GiB` (`standard-rwo`) + `100 GiB` (`standard-rwx` Shared `.litertlm` Models) | **Yes** (`1x NVIDIA L4 24GB` or `A100` for CUDA kernels & `LiteRTAgentConfig` at `16,384` token cap) |
| **Sovereign LLM Serving Prerequisite (`gdc_gemma_gw` in `gemma-inference`)** | `g2-standard-24-gdc` or `a2-highgpu-2g` | `24` | `96 GiB` | `200 GiB` (`gdc-block-storage` / `standard-rwx`) | **Yes** (`2x NVIDIA L4` or `A100/H100` for concurrent `gemma4:26b` MoE + `gemma4:31b` Dense) |

### **3.2 Cluster T-Shirt Sizing Tiers (Small / Medium / Large)**

| T-Shirt Tier | Concurrent Developers | CPU Worker Node Pool (`cpu-gateway`) | GPU Worker Node Pool (`gdc_gemma_gw` + `gpu-litert-notebook`) | Total vCPU | Total RAM | Total Block / Shared Storage (`PVC`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Small (Pilot / Lab)** | **10–15 Devs** (All `cpu-gateway`) | `2x n2-standard-8-gdc` (`16 vCPU`, `64 GiB RAM`) | `1x g2-standard-24-gdc` (`2x L4 GPU` for `gdc_gemma_gw`) | `40 vCPU` | `160 GiB` | `~500 GiB` (`standard-rwo` + `standard-rwx`) |
| **Medium (Departmental)** | **25–50 Devs** + **4 GPU Notebook Pods** | `4x n2-standard-16-gdc` (`64 vCPU`, `256 GiB RAM`) | `2x g2-standard-24-gdc` (`4x L4 GPU` across Gateway + Notebooks) | `112 vCPU` | `448 GiB` | `~1.5 TiB` (`standard-rwo` + `standard-rwx`) |
| **Large (Enterprise Enclave)** | **100+ Devs** + **16 GPU Notebook Pods** | `8x n2-standard-32-gdc` (`256 vCPU`, `1024 GiB RAM`) | `4x a2-highgpu-2g` or `g2-standard-48-gdc` (`8x–16x GPUs`) | `448 vCPU` | `1.8 TiB` | `~5.0 TiB` (`standard-rwo` + `standard-rwx`) |

---

## **4. Pre-Deployment Configuration: AI Inference Gateway, Ingress Gateway & Keycloak OIDC**

Before deploying Pattern 14 via Helm (`chart/`) or standalone manifests (`manifests/gdc/`), update the following configuration artifacts so the appropriate **AI Inference Gateway**, **Kubernetes Gateway API Ingress (`gdc-dev-gateway`)**, and **Keycloak OIDC (`p12-keycloak`)** endpoints are wired for your target GDC-ag cluster.

### **4.1 Summary of Files & Helm Parameters to Update for Deployment**

| Subsystem | Standalone Manifests (`p14-antigravity-dev/manifests/gdc/`) | Helm Chart (`p14-antigravity-dev/chart/values.yaml` or `--set`) | Required Updates for Your Target Cluster |
| :--- | :--- | :--- | :--- |
| **1. AI Inference Gateway & Model Tiering** | [`gdc-dev-agent-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/gdc-dev-agent-configmap.yaml), [`gdc-antigravity-notebook-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/gdc-antigravity-notebook-configmap.yaml), [`ai-gateway-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/ai-gateway-configmap.yaml) | `ai.backendMode`, `ai.provider`, `ai.openaiApiBaseUrl`, `ai.tier1Model`, `ai.coderModel`, `ai.defaultModel`, `ai.noProxy`, `computeProfile` | Set `AGY_BACKEND_MODE` (`gdc_gemma_gw`, `gdc_gemini`, or `litert_on_device`), `AI_PROVIDER` (`gemma` or `gemini`), `OPENAI_API_BASE_URL` (or `GDC_GEMINI_*`), served model IDs, and `NO_PROXY`. |
| **2. Zero-Trust AI Egress `NetworkPolicy`** | [`network-policy-ai.yaml`](../../p14-antigravity-dev/manifests/gdc/network-policy-ai.yaml) (`gdc-dev-to-gemma-netpol`) | `ai.gatewayNamespace` | Update `namespaceSelector.matchLabels["kubernetes.io/metadata.name"]` from `gemma-inference` to your inference gateway's namespace (or add an `ipBlock` rule if routing to an external GDC-ag Gemini appliance) and verify the target TCP port (`80`, `443`, `8000`, `8080`) is permitted. |
| **3. Kubernetes Gateway API Ingress & TLS** | [`certificate.yaml`](../../p14-antigravity-dev/manifests/gdc/certificate.yaml), [`gateway.yaml`](../../p14-antigravity-dev/manifests/gdc/gateway.yaml), [`network-policy.yaml`](../../p14-antigravity-dev/manifests/gdc/network-policy.yaml) | `gateway.className`, `gateway.name`, `gateway.domain`, `gateway.adminDomain`, `gateway.tlsSecretName`, `gateway.clusterIssuer` | Set `dnsNames` & `HTTPRoute.spec.hostnames` (`dev.gdc.local`, `admin.dev.gdc.local`), bind `certificateRefs` on Port `443` to `gdc-dev-tls-secret`, verify `gatewayClassName`, and ensure `gdc-dev-netpol` matches your Gateway controller namespace (`gdc-gateway-system`). |
| **4. Production Keycloak OIDC & RBAC** | [`oidc-auth-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/oidc-auth-configmap.yaml) | `auth.mode`, `auth.allowSimulatedOidc`, `auth.oidcAuthority`, `auth.oidcClientId`, `auth.oidcRedirectUri` | Set `ALLOW_SIMULATED_OIDC: "false"`, `OIDC_AUTHORITY` (`https://keycloak.gdc.local/realms/gdc-dev-realm`), `OIDC_CLIENT_ID` (`gdc-dev-client`), `OIDC_REDIRECT_URI` (`https://dev.gdc.local/auth/callback`), and `ADMIN_ROLES` (`gdc-admin,dev-admin,admin`). |

### **4.2 Configuring the AI Inference Gateway (`gdc_gemma_gw`, GDC Gemini, Custom `/v1`, or On-Device LiteRT-LM)**

1. **Pathway A (Default): In-Cluster Sovereign Gemma 4 Inference Gateway (`gdc_gemma_gw` / `LocalOpenAIAgentConfig.lightweight()`):**
   - Prerequisite: Deploy `gdc_gemma_gw` (`vllm-26b`, `vllm-31b`, `gemma-envoy-pool`, and `gemma-gateway`) in namespace `gemma-inference` per the [AI-Enabled Blueprint E2E Deployment Guide](../tutorials/ai_enabled_e2e_gdc_production_iac_guide.md).
   - Configuration in [`gdc-dev-agent-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/gdc-dev-agent-configmap.yaml) and [`gdc-antigravity-notebook-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/gdc-antigravity-notebook-configmap.yaml):
     ```yaml
     AGY_BACKEND_MODE: "gdc_gemma_gw"
     AI_PROVIDER: "gemma"
     OPENAI_API_BASE_URL: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
     AI_TIER1_MODEL: "gemma4:26b"
     AI_CODER_MODEL: "gemma4:31b"
     AI_DEFAULT_MODEL: "gemma4:31b"
     NO_PROXY: "*.gemma-inference.svc.cluster.local,*.gemma-inference,*.svc.cluster.local,localhost,127.0.0.1"
     ```
2. **Pathway B: Native GDC Air-Gapped Gemini AI Gateway (`gdc_gemini` / `LocalAgentConfig`):**
   - Update [`gdc-dev-agent-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/gdc-dev-agent-configmap.yaml) (or `ai.*` in `chart/values.yaml`) to point to the GDC-ag Vertex / Gemini Chat Completions API endpoint and permit TCP port `443` egress in [`network-policy-ai.yaml`](../../p14-antigravity-dev/manifests/gdc/network-policy-ai.yaml):
     ```yaml
     AGY_BACKEND_MODE: "gdc_gemini"
     AI_PROVIDER: "gemini"
     GOOGLE_CLOUD_PROJECT: "<project-id>"
     GOOGLE_CLOUD_LOCATION: "<location>"
     GDC_GEMINI_BASE_URL: "https://gemini.gdc.local:443/v1/projects/<project-id>/locations/<location>"
     GDC_GEMINI_ENDPOINT: "https://gemini.gdc.local:443/v1/projects/<project-id>/locations/<location>/chat/completions"
     AI_GEMINI_MODEL: "gemini-3.5-flash"
     AI_GEMINI_TIER1_MODEL: "gemini-2.0-flash"
     AI_GEMINI_TIER2_MODEL: "gemini-2.0-pro"
     ```
3. **Pathway C: Custom OpenAI-Compatible `/v1` Gateway (vLLM, Envoy AI Gateway, TGI, or Ollama in a Custom Namespace):**
   - Set `AGY_BACKEND_MODE: "gdc_gemma_gw"`, `OPENAI_API_BASE_URL: "https://<gateway-svc>.<custom-namespace>.svc.cluster.local/v1"`, `AI_TIER1_MODEL`, `AI_CODER_MODEL`, `AI_DEFAULT_MODEL`, and `NO_PROXY: "*.<custom-namespace>.svc.cluster.local,*.svc.cluster.local,localhost,127.0.0.1"`.
   - Update `kubernetes.io/metadata.name` in [`network-policy-ai.yaml`](../../p14-antigravity-dev/manifests/gdc/network-policy-ai.yaml) (or `--set ai.gatewayNamespace=<custom-namespace>` in Helm) to allow egress from `gdc-dev` to `<custom-namespace>`.
4. **Pathway D: Zero-Gateway On-Device LiteRT-LM (`litert_on_device` / `LiteRTAgentConfig`):**
   - Set `AGY_BACKEND_MODE: "litert_on_device"`, `COMPUTE_PROFILE: "gpu-litert-notebook"`, and `LITERT_MODEL_PATH: "/opt/models/gemma4-26b/model.litertlm"` in [`gdc-antigravity-notebook-configmap.yaml`](../../p14-antigravity-dev/manifests/gdc/gdc-antigravity-notebook-configmap.yaml) (or `--set computeProfile=gpu-litert-notebook --set ai.backendMode=litert_on_device` in Helm).

### **4.3 Configuring the Kubernetes Gateway API Ingress (`gdc-dev-gateway`) & TLS**

1. **Issue the TLS Certificate ([`certificate.yaml`](../../p14-antigravity-dev/manifests/gdc/certificate.yaml)):** Update `dnsNames` (`dev.gdc.local`, `*.dev.gdc.local`) and apply Option A (`pki.security.gdc.goog/v1` `CertificateRequest`) or Option B (`cert-manager.io/v1` `Certificate` with `ClusterIssuer/gdc-ca-issuer`) to create `Secret/gdc-dev-tls-secret`.
2. **Update `Gateway` & `HTTPRoute` ([`gateway.yaml`](../../p14-antigravity-dev/manifests/gdc/gateway.yaml)):**
   - Set `spec.gatewayClassName` to match your GDC-ag GatewayClass (or point `HTTPRoute.spec.parentRefs` to an existing shared `gdc-platform-gateway`).
   - Update `certificateRefs[0].name` on the Port `443` listener to `gdc-dev-tls-secret` (`--set gateway.tlsSecretName=gdc-dev-tls-secret`).
   - Update `hostnames` on `gdc-dev-host-route`, `gdc-dev-session-route`, and `gdc-dev-admin-route` (`--set gateway.domain=<dev-fqdn> --set gateway.adminDomain=<admin-fqdn>`).

---

## **5. Air-Gapped Packaging, Harbor Mirroring & Production GDC-ag Deployment**

### **5.1 Step 1: Build Images, Scan for CVEs & Package Air-Gap Bundle (Connected Bastion)**

```bash
# 1. Build production images for harbor.gdc.local
docker build -t harbor.gdc.local/blueprint-images/gdc-dev-landing-page:v1.0.0 p14-antigravity-dev/example-app/landing-page/
docker build -t harbor.gdc.local/blueprint-images/gdc-dev-operator:v1.0.0 p14-antigravity-dev/example-app/operator/
docker build -t harbor.gdc.local/blueprint-images/gdc-dev-workspace:v1.0.0 p14-antigravity-dev/example-app/workspace/

# 2. Run 87-test offline verification suite & Trivy CVE scan
./p14-antigravity-dev/test/verify.sh
trivy image --severity HIGH,CRITICAL --ignore-unfixed harbor.gdc.local/blueprint-images/gdc-dev-landing-page:v1.0.0
trivy image --severity HIGH,CRITICAL --ignore-unfixed harbor.gdc.local/blueprint-images/gdc-dev-operator:v1.0.0
trivy image --severity HIGH,CRITICAL --ignore-unfixed harbor.gdc.local/blueprint-images/gdc-dev-workspace:v1.0.0

# 3. Export offline bundle & stage into deploy-to-production/
./p14-antigravity-dev/scripts/package-for-gdc.sh
python3 scripts/stage_production_assets.py p14-antigravity-dev
```

### **5.2 Step 2: Unpack & Push to Sovereign Harbor Registry inside GDC-ag Enclave**

```bash
export TARGET_REGISTRY="harbor.gdc.local/blueprint-images"
export PROJECT_ID="gdc-dev"
./p14-antigravity-dev/scripts/unpack-for-gdc.sh
```

### **5.3 Step 3: Deploy Pattern 14 via Helm (`foundations/releases/5-workload-factory`) or `kubectl`**

#### **Option A: Helm / Helmfile Deployment (Recommended)**
```bash
# 1. Deploy zero-GPU developer workspace profile (computeProfile=cpu-gateway) with gdc_gemma_gw
helm upgrade --install p14-antigravity-dev ./p14-antigravity-dev/chart \
  --namespace gdc-dev \
  --create-namespace \
  --set global.projectId=gdc-dev \
  --set global.namespace=gdc-dev \
  --set global.registry=harbor.gdc.local/blueprint-images \
  --set computeProfile=cpu-gateway \
  --set ai.backendMode=gdc_gemma_gw \
  --set ai.openaiApiBaseUrl=http://gemma-gateway.gemma-inference.svc.cluster.local/v1 \
  --set ai.gatewayNamespace=gemma-inference \
  --set gateway.domain=dev.gdc.local \
  --set gateway.adminDomain=admin.dev.gdc.local \
  --set gateway.tlsSecretName=gdc-dev-tls-secret

# 2. Or deploy against the Native GDC Gemini AI Gateway (ai.backendMode=gdc_gemini)
helm upgrade --install p14-antigravity-dev ./p14-antigravity-dev/chart \
  --namespace gdc-dev \
  --create-namespace \
  --set global.projectId=gdc-dev \
  --set global.namespace=gdc-dev \
  --set global.registry=harbor.gdc.local/blueprint-images \
  --set computeProfile=cpu-gateway \
  --set ai.backendMode=gdc_gemini \
  --set ai.provider=gemini \
  --set ai.geminiBaseUrl=https://gemini.gdc.local:443/v1/projects/gdc-dev/locations/us-central1 \
  --set ai.geminiEndpoint=https://gemini.gdc.local:443/v1/projects/gdc-dev/locations/us-central1/chat/completions
```

#### **Option B: Direct Manifest Deployment (`kubectl`)**
```bash
kubectl apply -f p14-antigravity-dev/manifests/gdc/namespace.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/certificate.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gateway.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/loadbalancer.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/oidc-auth-configmap.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-dev-agent-configmap.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-antigravity-notebook-configmap.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-dev-operator.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/network-policy.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/network-policy-ai.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-dev-phase3-deployment.yaml
```

---

## **6. Post-Deployment Verification**

```bash
# 1. Verify Antigravity SDK configuration and installed SKILL.md bundles
curl -sk https://admin.dev.gdc.local/agy-config | jq .

# 2. Run the live GDC-ag cluster smoke checks + 10-stage Multi-Agent Swarm + Phase 5 Notebook suite
python3 p14-antigravity-dev/scripts/test-agy-swarm.py \
  --admin-url https://admin.dev.gdc.local \
  --ide-url https://dev.gdc.local
```
