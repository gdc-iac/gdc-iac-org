Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 14 (`p14-antigravity-dev`): GDC-ag Antigravity SDK & Integrated Notebooks Developer IDE Platform

> **Specification ID:** `REQ-GDC-AG-DEV-PLATFORM-001` (v1.3)  
> **Target Environment:** Google Distributed Cloud Air-Gapped (`GDC-ag`)  
> **Baseline Preservation:** Leaves [`p13-gdc-dev`](../p13-gdc-dev/README.md) untouched as the interim zero-dependency pattern while introducing the **Google Antigravity SDK (`google-antigravity`) Tri-Backend Orchestrator**, **Modular GDC `SKILL.md` Bundles**, and **Co-Located Integrated JupyterLab 4 (`/lab/`)**.

---

## Table of Contents

1. [Overview & GDC Air-Gapped Architecture](#1-overview--gdc-air-gapped-architecture)
2. [Prerequisites: Sovereign Gemma 4 Inference Gateway (`gdc_gemma_gw`) & Keycloak OIDC (`p12-keycloak`)](#2-prerequisites-sovereign-gemma-4-inference-gateway-gdc_gemma_gw--keycloak-oidc-p12-keycloak)
3. [Resource Requirements (T-Shirt Sizes) & Compute Profiles (`GDC-ag`)](#3-resource-requirements-t-shirt-sizes--compute-profiles-gdc-ag)
4. [Antigravity SDK Tri-Backend Architecture & Verification](#4-antigravity-sdk-tri-backend-architecture--verification)
5. [Specialist Agent Personas & Principle of Least Privilege (PoLP)](#5-specialist-agent-personas--principle-of-least-privilege-polp)
6. [Modular GDC Skills (`SKILL.md`): Using Skills in the Code IDE & ClickOps Skill Creation](#6-modular-gdc-skills-skillmd-using-skills-in-the-code-ide--clickops-skill-creation)
7. [Integrated JupyterLab 4 (`/lab/`), `.ipynb` v4 Tools & IPython Magics](#7-integrated-jupyterlab-4-lab-ipynb-v4-tools--ipython-magics)
8. [Sovereign Admin & Telemetry Console (`https://admin.dev.gdc.local` / Port `8081`)](#8-sovereign-admin--telemetry-console-httpsadmindevgdclocal--port-8081)
9. [Air-Gapped Packaging, Transfer & Production GDC-ag Deployment](#9-air-gapped-packaging-transfer--production-gdc-ag-deployment)
10. [End-to-End GDC-ag Walkthrough & Verification](#10-end-to-end-gdc-ag-walkthrough--verification)
11. [Helm & IaC Orchestrated Deployment (`foundations/releases/5-workload-factory`)](#11-helm--iac-orchestrated-deployment-foundationsreleases5-workload-factory)

---

## 1. Overview & GDC Air-Gapped Architecture

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

### GDC-ag Endpoint & Port Matrix

> [!NOTE]
> Identity values such as `<developer-user>@<org-domain>`, `<platform-admin>@<org-domain>`, and `<gateway-admin-user>` are placeholders representing accounts provisioned in your organization's production **Keycloak (`p12-keycloak`)** realms. Lab/emulation test accounts (defined in `mock-auth-configmap.yaml` or staging realm imports) are disabled in production when `ALLOW_SIMULATED_OIDC: "false"`. See **[Section 2.4: Configuring Keycloak OIDC for Production](#24-configuring-keycloak-oidc-for-production-gdc-dev-realm--rbac-claims)** below for production setup instructions.

| GDC-ag FQDN | Container Port | Target Service | Login Identity & Cookie Scope | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`https://dev.gdc.local`** | `8080` | `svc/gdc-dev-landing-page` (`gdc-dev`) | `<developer-user>@<org-domain>` (`dev_auth_user` HMAC cookie via Keycloak `gdc-dev-realm`) | **Pattern 14 Unified Developer IDE (`/ide/`) & Integrated JupyterLab 4 (`/lab/`)**: Code editor, `.ipynb` notebook drawer, `%%agy_*` cell magics, Multi-Agent AI Swarm dock, and integrated bash terminal. |
| **`https://admin.dev.gdc.local`** | `8081` | `svc/gdc-dev-landing-page` (`gdc-dev`) | `<platform-admin>@<org-domain>` (`admin_auth_user` HMAC cookie; `gdc-admin` / `dev-admin` role in `gdc-dev-realm`) | **Sovereign Admin & Telemetry Console**: Real-time AI Swarm invocation audit log, model/persona utilization bars, cluster broadcast banner, dynamic policy overrides, session hibernation/termination, and `GET /agy-config`. |
| **`https://keycloak.gdc.local`** | `8080` (`8443`) | `svc/keycloak-svc` (`platform` / `gemma-inference`) | `gdc-dev-realm` (`gdc-dev-client`) & `gdc-rag-realm` | **Keycloak OIDC Identity Provider (`p12-keycloak`)**: Issues RS256 OIDC JWTs, handles `/auth/callback` SSO redirects, and enforces RBAC group claims (`X-Forwarded-User` / `X-Forwarded-Groups`) for both `gdc-dev` and `gemma-gateway`. |
| **`https://ai-gateway.gdc.local`** | `443` (`8000`) | `svc/gemma-gateway` (`gemma-inference`) | `<gateway-admin-user>` (`admin` role via Keycloak `gdc-rag-realm`) | **Gemma 4 Inference Gateway Control Plane**: GPU/VRAM telemetry, temperature/model overrides, active session kill-switch, and user blocklist. |

---

## 2. Prerequisites: Sovereign Gemma 4 Inference Gateway (`gdc_gemma_gw`) & Keycloak OIDC (`p12-keycloak`)

> [!IMPORTANT]
> **Mandatory AI Backend & Identity Prerequisites:**
> 1. **Sovereign AI Inference Backend (`gdc_gemma_gw` Default, or Pluggable Alternative Inference Gateways):**
>    - **Default Backend (`gdc_gemma_gw` in `gemma-inference`):** By default (`backend_mode: "gdc_gemma_gw"`), Pattern 14 routes Antigravity SDK `LocalOpenAIAgentConfig.lightweight()` requests across namespaces to `http://gemma-gateway.gemma-inference.svc.cluster.local/v1` (`gemma4:26b` Fast MoE and `gemma4:31b` Dense Reasoning).
>    - **Pluggable Alternative Inference Gateways:** Because the Antigravity SDK orchestrator ([`example-app/orchestrator/gdc_agy_orchestrator.py`](example-app/orchestrator/gdc_agy_orchestrator.py)) decouples agent tool execution from model serving via standard OpenAI `/v1/chat/completions` and LiteRT contracts, **alternative inference gateways can be swapped in declaratively** via [`manifests/gdc/gdc-dev-agent-configmap.yaml`](manifests/gdc/gdc-dev-agent-configmap.yaml) and [`manifests/gdc/gdc-antigravity-notebook-configmap.yaml`](manifests/gdc/gdc-antigravity-notebook-configmap.yaml) without rebuilding container images:
>      - **Sovereign GDC Air-Gapped Gemini AI Gateway (`gdc_gemini` / `LocalAgentConfig`):** Routes to the native Vertex AI / Gemini on GDC-ag Chat Completions endpoint (`https://gemini.gdc.local:443/v1/projects/<project>/locations/<location>/chat/completions`).
>      - **Custom OpenAI-Compatible `/v1` Inference Gateways (`LocalOpenAIAgentConfig`):** Routes to any organization-managed vLLM, Envoy AI Gateway, TGI, or Ollama `/v1` endpoint by updating `OPENAI_API_BASE_URL`.
>      - **Zero-Gateway On-Device LiteRT-LM (`litert_on_device` / `LiteRTAgentConfig`):** Runs quantized `.litertlm` weights directly inside GPU-enabled MLOps pods (`computeProfile: "gpu-litert-notebook"`).
>    - See **[Section 2.3: Swapping in Alternative Inference Gateways](#23-swapping-in-alternative-inference-gateways)**, **[Section 4.1: The Three Antigravity SDK Backend Configurations](#41-the-three-antigravity-sdk-backend-configurations)**, **[Pattern 13 Reference Implementation Guide — Section 5.3 (*Configuring Sovereign Inference Endpoints & Models*)](../docs/implementation-guides/Solution-Reference-Implementation-Pattern-13-GDC-Dev.md#3-configuring-sovereign-inference-endpoints--models-gemma-gateway-vs-gdc-gemini)**, and **[Architecture Patterns Definition (*Migration to Native GDC Gemini AI Gateway*)](../docs/architecture/patterns_def.md)** for full details.
> 2. **Keycloak OIDC Identity Provider (`p12-keycloak` / `keycloak-svc`):** Both the Inference Gateway Control Plane (`https://ai-gateway.gdc.local`) and Pattern 14's production OIDC boundary (`ALLOW_SIMULATED_OIDC: "false"` in [`manifests/gdc/oidc-auth-configmap.yaml`](manifests/gdc/oidc-auth-configmap.yaml)) require **Keycloak OIDC** to be deployed and configured:
>    - **`gdc-rag-realm`** (`https://keycloak.gdc.local/realms/gdc-rag-realm`): Authenticates Gemma Gateway administrators (`<gateway-admin-user>`) and analysts (`<developer-user>`). Note that in `gdc_gemma_gw`, running `./standalone/install-all.sh` alone does **not** deploy Keycloak—you must also deploy [`p12-keycloak`](../p12-keycloak/README.md) (Stage 5 `5-workload-factory` in GDC-ag production).
>    - **`gdc-dev-realm`** (`https://keycloak.gdc.local/realms/gdc-dev-realm`, client `gdc-dev-client`): Issues RS256 OIDC tokens and role claims (`gdc-admin`, `dev-admin`, `admin`) for `https://dev.gdc.local` (`:8080`) and `https://admin.dev.gdc.local` (`:8081`). See **[Section 2.4](#24-configuring-keycloak-oidc-for-production-gdc-dev-realm--rbac-claims)** below.

### 2.1. Verify the Gemma 4 Inference Gateway & Keycloak OIDC Are Running

```bash
kubectl get pods,svc -n gemma-inference
kubectl get pods,svc -n platform -l app.kubernetes.io/name=keycloak
```

**Expected Output (`gemma-inference`):**
```text
NAME                                 READY   STATUS    RESTARTS   AGE
pod/gemma-gateway-xxxxxxxxxx-xxxxx   1/1     Running   0          1h
pod/keycloak-xxxxxxxxxx-xxxxx        1/1     Running   0          1h
pod/vllm-26b-xxxxxxxxxx-xxxxx        1/1     Running   0          1h
pod/vllm-31b-xxxxxxxxxx-xxxxx        1/1     Running   0          1h

NAME                    TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
service/gemma-gateway   ClusterIP   10.96.xxx.xx   <none>        80/TCP     1h
service/keycloak-svc    ClusterIP   10.96.xxx.xx   <none>        8080/TCP   1h
```

### 2.2. Deploying the Gemma 4 Inference Gateway & Keycloak OIDC (If Not Already Deployed)

If `gemma-inference` or Keycloak (`p12-keycloak`) is not yet populated on your GDC-ag cluster:
1. Follow the **[AI-Enabled Blueprint E2E Deployment Guide (GDC-ag Production IaC)](../docs/tutorials/ai_enabled_e2e_gdc_production_iac_guide.md)** (Stages 2, 3, and 5) to deploy `p12-keycloak`, `vllm-26b`, `vllm-31b`, Envoy `InferencePool` (`gemma-envoy-pool`), and `gemma-gateway`.
2. Or deploy the standalone air-gapped gateway bundle from the `gdc_gemma_gw` blueprint (`INFERENCE_ENGINE=vllm ./scripts/unpack-for-gdc.sh`) along with [`p12-keycloak`](../p12-keycloak/README.md), and configure the `gdc-dev-realm` client (`OIDC_CLIENT_ID: "gdc-dev-client"`, redirect URI `https://dev.gdc.local/auth/callback`) as documented in [`docs/operations/keycloak_integration_guide.md`](../docs/operations/keycloak_integration_guide.md).
3. Verify cross-namespace DNS resolution from `gdc-dev` once Pattern 14 is deployed (`manifests/gdc/network-policy-ai.yaml` automatically whitelists egress from `gdc-dev` to `gemma-inference` on ports `80`, `443`, and `8080`).

### 2.3. Configuring & Swapping the AI Inference Gateway for Deployment

Pattern 14 does not hard-lock workspaces to a single inference appliance. Before deploying via `kubectl` or `helm`, update the **AI Inference ConfigMaps**, **Zero-Trust Egress NetworkPolicy**, or **Helm `values.yaml`** to point to your cluster's active AI Gateway (also cross-referenced in **[Section 4.1](#41-the-three-antigravity-sdk-backend-configurations)**, **[Pattern 14 Implementation Guide — Section 4](../docs/implementation-guides/Solution-Reference-Implementation-Pattern-14-Antigravity-Dev.md)**, **[Pattern 13 Implementation Guide — Section 5.3](../docs/implementation-guides/Solution-Reference-Implementation-Pattern-13-GDC-Dev.md#3-configuring-sovereign-inference-endpoints--models-gemma-gateway-vs-gdc-gemini)**, and **[`docs/architecture/patterns_def.md`](../docs/architecture/patterns_def.md)**):

#### Files to Update Before Deployment (`kubectl` vs. `helm`)

| Configuration Target | Standalone Manifests (`kubectl apply -f manifests/gdc/`) | Helm / Helmfile (`chart/values.yaml` or `--set`) | What to Update |
| :--- | :--- | :--- | :--- |
| **1. Agent & Swarm Gateway Endpoint** | [`manifests/gdc/gdc-dev-agent-configmap.yaml`](manifests/gdc/gdc-dev-agent-configmap.yaml) & [`manifests/gdc/ai-gateway-configmap.yaml`](manifests/gdc/ai-gateway-configmap.yaml) | `ai.backendMode`, `ai.provider`, `ai.openaiApiBaseUrl`, `ai.tier1Model`, `ai.coderModel`, `ai.defaultModel` | Set `AGY_BACKEND_MODE` (`gdc_gemma_gw`, `gdc_gemini`, or `litert_on_device`), `AI_PROVIDER` (`gemma` or `gemini`), `OPENAI_API_BASE_URL` (or `GDC_GEMINI_*`), and served model IDs. |
| **2. Antigravity SDK & Notebook Config** | [`manifests/gdc/gdc-antigravity-notebook-configmap.yaml`](manifests/gdc/gdc-antigravity-notebook-configmap.yaml) | `computeProfile`, `antigravity.gatewayTokenThreshold`, `antigravity.litertModelPath` | Keep `AGY_BACKEND_MODE` and `OPENAI_API_BASE_URL` aligned with `gdc-dev-agent-configmap.yaml`; set `COMPUTE_PROFILE` (`cpu-gateway` or `gpu-litert-notebook`). |
| **3. Zero-Trust Egress `NetworkPolicy`** | [`manifests/gdc/network-policy-ai.yaml`](manifests/gdc/network-policy-ai.yaml) (`gdc-dev-to-gemma-netpol`) | `ai.gatewayNamespace` | Because Pattern 14 enforces default-deny egress, if your inference gateway runs in a namespace other than `gemma-inference`, update `namespaceSelector.matchLabels["kubernetes.io/metadata.name"]` (or add an `ipBlock` rule for an external GDC appliance) and verify the target TCP port (`80`, `443`, `8000`, `8080`) is listed. |
| **4. Corporate Proxy Bypass (`NO_PROXY`)** | `NO_PROXY` in [`manifests/gdc/gdc-dev-agent-configmap.yaml`](manifests/gdc/gdc-dev-agent-configmap.yaml) | `ai.noProxy` | Include the gateway service's internal DNS suffix (e.g., `*.<gateway-namespace>.svc.cluster.local`) so workspace pods do not route internal inference traffic through an HTTP proxy. |

#### Gateway Configuration Pathways

1. **Pathway A (Default): In-Cluster Sovereign Gemma 4 Inference Gateway (`gdc_gemma_gw` / `LocalOpenAIAgentConfig.lightweight()`):**
   ```yaml
   # manifests/gdc/gdc-dev-agent-configmap.yaml & manifests/gdc/gdc-antigravity-notebook-configmap.yaml
   AGY_BACKEND_MODE: "gdc_gemma_gw"
   AI_PROVIDER: "gemma"
   OPENAI_API_BASE_URL: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
   AI_TIER1_MODEL: "gemma4:26b"
   AI_CODER_MODEL: "gemma4:31b"
   AI_DEFAULT_MODEL: "gemma4:31b"
   NO_PROXY: "*.gemma-inference.svc.cluster.local,*.gemma-inference,*.svc.cluster.local,localhost,127.0.0.1"
   ```
2. **Pathway B: Native GDC Air-Gapped Gemini AI Gateway (`gdc_gemini` / `LocalAgentConfig`):**
   Update [`manifests/gdc/gdc-dev-agent-configmap.yaml`](manifests/gdc/gdc-dev-agent-configmap.yaml) (or `ai.*` in [`chart/values.yaml`](chart/values.yaml)) to target the GDC-ag Vertex / Gemini Chat Completions API endpoint, and ensure [`manifests/gdc/network-policy-ai.yaml`](manifests/gdc/network-policy-ai.yaml) permits TCP port `443` egress to the Gemini gateway namespace or appliance CIDR:
   ```yaml
   # manifests/gdc/gdc-dev-agent-configmap.yaml
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
3. **Pathway C: Custom OpenAI-Compatible `/v1` Inference Gateway (vLLM, Envoy AI Gateway, TGI, or Ollama in a Custom Namespace):**
   - Update `OPENAI_API_BASE_URL` (e.g., `https://<custom-gateway-svc>.<custom-namespace>.svc.cluster.local/v1`), `AI_TIER1_MODEL`, `AI_CODER_MODEL`, `AI_DEFAULT_MODEL`, and `NO_PROXY` (`*.<custom-namespace>.svc.cluster.local,...`) in [`manifests/gdc/gdc-dev-agent-configmap.yaml`](manifests/gdc/gdc-dev-agent-configmap.yaml) and [`manifests/gdc/gdc-antigravity-notebook-configmap.yaml`](manifests/gdc/gdc-antigravity-notebook-configmap.yaml).
   - Update `kubernetes.io/metadata.name` in [`manifests/gdc/network-policy-ai.yaml`](manifests/gdc/network-policy-ai.yaml) (or `--set ai.gatewayNamespace=<custom-namespace>` in Helm) to match `<custom-namespace>`.
4. **Pathway D: Zero-Gateway On-Device LiteRT-LM (`litert_on_device` / `LiteRTAgentConfig`):**
   Set `AGY_BACKEND_MODE: "litert_on_device"`, `COMPUTE_PROFILE: "gpu-litert-notebook"`, and `LITERT_MODEL_PATH: "/opt/models/gemma4-26b/model.litertlm"` in [`manifests/gdc/gdc-antigravity-notebook-configmap.yaml`](manifests/gdc/gdc-antigravity-notebook-configmap.yaml) (or `--set computeProfile=gpu-litert-notebook --set ai.backendMode=litert_on_device` in Helm) to run inference directly on the workspace pod's GPU/CPU without an external gateway.

### 2.4. Configuring Keycloak OIDC for Production (`gdc-dev-realm` & RBAC Claims)

In a production GDC-ag deployment, simulated/testing accounts (`mock-auth-configmap.yaml`) are disabled (`ALLOW_SIMULATED_OIDC: "false"`). Configure your enterprise **Keycloak (`p12-keycloak`)** instance and [`manifests/gdc/oidc-auth-configmap.yaml`](manifests/gdc/oidc-auth-configmap.yaml) (or [`chart/values.yaml`](chart/values.yaml)) as follows (see [`docs/operations/keycloak_integration_guide.md`](../docs/operations/keycloak_integration_guide.md) and [`p12-keycloak/README.md`](../p12-keycloak/README.md) for full realm & Gateway API setup):

1. **Create the Realm & OIDC Client in Keycloak (`https://keycloak.gdc.local`):**
   - **Realm:** `gdc-dev-realm` (or your organization's existing realm).
   - **Client ID:** `gdc-dev-client` (`Client Protocol: openid-connect`, Authorization Code Flow + PKCE enabled).
   - **Valid Redirect URIs:** `https://dev.gdc.local/auth/callback` and `https://admin.dev.gdc.local/auth/callback`.
   - **Web Origins:** `https://dev.gdc.local` and `https://admin.dev.gdc.local`.
2. **Configure Realm Roles & User/Group Mappings:**
   - **Developer Accounts (`<developer-user>@<org-domain>`):** Provision standard users (or federate via LDAP/Active Directory) in `gdc-dev-realm`. Upon login at `https://dev.gdc.local`, the Gateway OIDC filter / callback validates the RS256 JWT and forwards the canonical identity via `X-Forwarded-User`, issuing a workspace-scoped `dev_auth_user` HMAC cookie on Port `8080`.
   - **Platform Administrator Accounts (`<platform-admin>@<org-domain>`):** Create realm roles `gdc-admin` or `dev-admin` (matching `ADMIN_ROLES` in `oidc-auth-configmap.yaml`) and assign them to authorized platform operators. Configure a Keycloak **User Realm Role / Group Membership Protocol Mapper** so role claims are emitted in the JWT and forwarded via `X-Forwarded-Groups`. Only users holding an `ADMIN_ROLES` claim are issued the isolated `admin_auth_user` cookie on Port `8081` (`https://admin.dev.gdc.local`).
   - **Inference Gateway Administrators (`<gateway-admin-user>`):** In `gdc-rag-realm`, assign the `admin` role to operators who manage `https://ai-gateway.gdc.local`.
3. **Update [`manifests/gdc/oidc-auth-configmap.yaml`](manifests/gdc/oidc-auth-configmap.yaml) (or `auth.*` in [`chart/values.yaml`](chart/values.yaml)):**
   ```yaml
   data:
     AUTH_MODE: "oidc"
     ALLOW_SIMULATED_OIDC: "false"
     HEADER_USER_KEY: "X-Forwarded-User"
     HEADER_ROLES_KEY: "X-Forwarded-Groups"
     ADMIN_ROLES: "gdc-admin,dev-admin,admin"
     OIDC_AUTHORITY: "https://keycloak.gdc.local/realms/gdc-dev-realm"
     OIDC_CLIENT_ID: "gdc-dev-client"
     OIDC_REDIRECT_URI: "https://dev.gdc.local/auth/callback"
     ADMIN_PORT: "8081"
     REDIRECT_ADMIN_PORT: "true"
   ```

### 2.5. Configuring the Kubernetes Gateway API Ingress (`gdc-dev-gateway`) & TLS for Deployment

To expose the Developer IDE (`https://dev.gdc.local`, Port `8080`) and Sovereign Admin Console (`https://admin.dev.gdc.local`, Port `8081`) through your cluster's Kubernetes Gateway API controller, update [`manifests/gdc/certificate.yaml`](manifests/gdc/certificate.yaml), [`manifests/gdc/gateway.yaml`](manifests/gdc/gateway.yaml), and [`manifests/gdc/network-policy.yaml`](manifests/gdc/network-policy.yaml) (or `gateway.*` in [`chart/values.yaml`](chart/values.yaml)):

1. **Provision the Production TLS Certificate ([`manifests/gdc/certificate.yaml`](manifests/gdc/certificate.yaml)):**
   - Update `dnsNames` (`dev.gdc.local`, `*.dev.gdc.local`) to match your organization's GDC-ag FQDNs.
   - Apply Option A (`pki.security.gdc.goog/v1` `CertificateRequest` against `gdc-root-ca`) or Option B (`cert-manager.io/v1` `Certificate` against `ClusterIssuer/gdc-ca-issuer`) to generate `Secret/gdc-dev-tls-secret` in namespace `gdc-dev`.
2. **Update GatewayClass, TLS Secret Reference & HTTPRoute Hostnames ([`manifests/gdc/gateway.yaml`](manifests/gdc/gateway.yaml) or `gateway.*` in [`chart/values.yaml`](chart/values.yaml)):**
   - **`spec.gatewayClassName`:** Set to your GDC-ag cluster's internal GatewayClass (default `gdc-dev-gateway-class` backed by `gateway.envoyproxy.io/gatewayclass-controller`), or update `HTTPRoute.spec.parentRefs` to attach routes to an existing shared platform gateway (`gdc-platform-gateway`).
   - **HTTPS Listener `certificateRefs`:** For production PKI, change `certificateRefs[0].name` on the Port `443` listener from `gdc-dev-selfsigned-cert-secret` to `gdc-dev-tls-secret` (`--set gateway.tlsSecretName=gdc-dev-tls-secret`).
   - **`HTTPRoute.spec.hostnames`:** Update `dev.gdc.local` (`gdc-dev-host-route` and `gdc-dev-session-route`) and `admin.dev.gdc.local` (`gdc-dev-admin-route`) to match your enterprise DNS names (`--set gateway.domain=<dev-fqdn> --set gateway.adminDomain=<admin-fqdn>`).
3. **Verify Ingress `NetworkPolicy` Controller Namespace ([`manifests/gdc/network-policy.yaml`](manifests/gdc/network-policy.yaml)):**
   - `gdc-dev-netpol` allows ingress on TCP ports `8080`, `8081`, and `3000` from `namespaceSelector.matchLabels["kubernetes.io/metadata.name"]: gdc-gateway-system`. If your Envoy / GDC Gateway controller pods run in a different namespace (e.g., `envoy-gateway-system` or `istio-system`), update that namespace label before applying `network-policy.yaml`.

---

## 3. Resource Requirements (T-Shirt Sizes) & Compute Profiles (`GDC-ag`)

### 3.1. Component-Level Resource Requirements

**Estimated Baseline Capacity:** Supports 15–25 concurrent zero-GPU developer IDE + Notebook sessions per standard CPU worker node when using `computeProfile: "cpu-gateway"`, with centralized GPU inference handled by `gdc_gemma_gw`.

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Control Plane (`gdc-dev-operator` & `gdc-dev-landing-page`)** | `n2-standard-4-gdc` | `4` | `16 GiB` | N/A | **No** |
| **Dynamic Workspace Pod — Profile A (`computeProfile: "cpu-gateway"`, Default)** | `n2-standard-8-gdc` (Shared Pool) | `2–4` (Per Pod) | `8–16 GiB` (Per Pod) | `20–50 GiB` (`standard-rwo`) + `100 GiB` (`standard-rwx` Shared Team Git) | **No** (Routes to shared `gdc_gemma_gw` with `40,960` compaction threshold) |
| **Dynamic Workspace Pod — Profile B (`computeProfile: "gpu-litert-notebook"`, MLOps)** | `g2-standard-12-gdc` or `a2-highgpu-1g` | `8–12` (Per Pod) | `32–48 GiB` (Per Pod) | `100 GiB` (`standard-rwo`) + `100 GiB` (`standard-rwx` Shared `.litertlm` Models) | **Yes** (`1x NVIDIA L4 24GB` or `A100` for CUDA kernels & `LiteRTAgentConfig` at `16,384` token cap) |
| **Sovereign LLM Serving Prerequisite (`gdc_gemma_gw` in `gemma-inference`)** | `g2-standard-24-gdc` or `a2-highgpu-2g` | `24` | `96 GiB` | `200 GiB` (`gdc-block-storage` / `standard-rwx`) | **Yes** (`2x NVIDIA L4` or `A100/H100` for concurrent `gemma4:26b` MoE + `gemma4:31b` Dense) |

### 3.2. Cluster T-Shirt Sizing Tiers (Small / Medium / Large)

| T-Shirt Tier | Concurrent Developers | CPU Worker Node Pool (`cpu-gateway`) | GPU Worker Node Pool (`gdc_gemma_gw` + `gpu-litert-notebook`) | Total vCPU | Total RAM | Total Block / Shared Storage (`PVC`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Small (Pilot / Lab)** | **10–15 Devs** (All `cpu-gateway`) | `2x n2-standard-8-gdc` (`16 vCPU`, `64 GiB RAM`) | `1x g2-standard-24-gdc` (`2x L4 GPU` for `gdc_gemma_gw`) | `40 vCPU` | `160 GiB` | `~500 GiB` (`standard-rwo` + `standard-rwx`) |
| **Medium (Departmental)** | **25–50 Devs** + **4 GPU Notebook Pods** | `4x n2-standard-16-gdc` (`64 vCPU`, `256 GiB RAM`) | `2x g2-standard-24-gdc` (`4x L4 GPU` across Gateway + Notebooks) | `112 vCPU` | `448 GiB` | `~1.5 TiB` (`standard-rwo` + `standard-rwx`) |
| **Large (Enterprise Enclave)** | **100+ Devs** + **16 GPU Notebook Pods** | `8x n2-standard-32-gdc` (`256 vCPU`, `1024 GiB RAM`) | `4x a2-highgpu-2g` or `g2-standard-48-gdc` (`8x–16x GPUs`) | `448 vCPU` | `1.8 TiB` | `~5.0 TiB` (`standard-rwo` + `standard-rwx`) |

### 3.3. Dual Storage Topology (`standard-rwo` + `standard-rwx`)
1. **Per-Developer Workspace Volume (`/home/dev/workspace`, `standard-rwo` / `gdc-block-storage`):**
   - Stores the developer's private repositories, unstaged edits, `.ipynb` v4 notebooks, and `.bak` / `.ipynb.bak` rollback snapshots.
   - Remains intact when the workspace pod is hibernated (`0 CPU / 0 Gi RAM`) and re-attaches when resumed.
2. **Shared Team Git Promotion & Model Artifact Volume (`/workspace/shared`, `standard-rwx`):**
   - Enables air-gapped bare Git repository promotion (`/workspace/shared/team-repo.git`) and pre-staged `.litertlm` quantized model sharing across developer pods without external internet access.

---

## 4. Antigravity SDK Tri-Backend Architecture & Verification

### 4.1. The Three Antigravity SDK Backend Configurations

Implemented in [`example-app/orchestrator/gdc_agy_orchestrator.py`](example-app/orchestrator/gdc_agy_orchestrator.py), Pattern 14 supports three air-gapped execution backends selectable per request (`backend_mode`) or via cluster configuration (`AGY_BACKEND_MODE`):

| Backend Mode (`backend_mode`) | Antigravity SDK Config Class | Default Model & Endpoint | Context Compaction & Optimization | Primary Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **`gdc_gemma_gw`** *(Default)* | `LocalOpenAIAgentConfig(...).lightweight()` | `gemma4:26b` (Coder/Reviewer/Swarm) & `gemma4:31b` (Architect) at `http://gemma-gateway.gemma-inference.svc.cluster.local/v1` | `.lightweight()` sets `AgentBehavior.MINIMAL`, `enable_subagents=False`, `enable_knowledge=False`, and `token_threshold=40960` | Zero-GPU developer workspace pods (`computeProfile: "cpu-gateway"`) sharing the central in-cluster Gemma 4 Gateway. |
| **`litert_on_device`** | `LiteRTAgentConfig(...).lightweight()` | `gemma4:26b-litert` loading pre-staged `/opt/models/gemma4-26b/model.litertlm` (`LiteRTBackend.GPU` or `CPU`) | Sets `download_if_missing=False`, `enable_speculative_decoding=True`, and lowers `token_threshold=16384` on GPU pods to prevent WebGPU 2D attention mask VRAM exhaustion | Dedicated GPU-enabled MLOps & notebook pods (`computeProfile: "gpu-litert-notebook"`). |
| **`gdc_gemini`** | `LocalAgentConfig(model="gemini-3.5-flash", ...)` | `gemini-3.5-flash` via GDC-ag Chat Completions API (`https://gemini.gdc.local:443/v1/projects/gdc-dev/locations/gdc-dev/chat/completions`) | Full `128,000`-token context window with STS Bearer auth (`ai-large-gemini-developer`), `reasoning_effort` control, and native structured output | Sovereign GDC-ag Gemini on GDC Air-Gapped Chat Completions API escalation for cross-blueprint architecture plans. |

### 4.2. How to Verify Antigravity SDK Configuration Live

#### 1. Visual Confirmation in the Unified Developer IDE (`https://dev.gdc.local`)
When signed into `https://dev.gdc.local/instances/default-workspace`, the **Pattern 14 Antigravity Surface Bar** directly above the editor displays:
- Left badge: **`🚀 Pattern 14: Antigravity SDK + Notebooks`**
- Surface switcher buttons: **`💻 Code IDE (/ide/)`**, **`📓 Integrated JupyterLab 4 (/lab/)`**, **`🧩 Antigravity Skills (4)`**, **`➕ + New SKILL.md`**, **`↩️ Rollback .ipynb Cell`**, and **`⚡ Fix Cell with Antigravity Agent`**.
- Right status readout: **`Profile: cpu-gateway | SDK: LocalOpenAIAgentConfig.lightweight() / LiteRTAgentConfig`**.
- Right-hand **AI Swarm** dock: **`🧩 Antigravity SKILL.md (Active in IDE)`** selector bar (`#p14-ide-skill-bar`) with **`🚀 Apply Skill`**, **`📄 Edit SKILL.md`**, and **`➕ + Skill`**.

#### 2. Query the `/agy-config` Introspection Endpoint (`https://admin.dev.gdc.local/agy-config`)
```bash
curl -sk https://admin.dev.gdc.local/agy-config | jq .
```

**Expected Output:**
```json
{
  "status": "ok",
  "pattern": "p14-antigravity-dev",
  "compute_profile": "cpu-gateway",
  "config_class": "LocalOpenAIAgentConfig",
  "model": "gemma4:26b",
  "behavior": "MINIMAL",
  "token_threshold": 40960,
  "skills": [
    {
      "name": "gdc-blueprint-adaptation",
      "description": "Adapts GDC-blueprints applications across manifests/gdc/ and chart/ with air-gapped Harbor registries and GDC CRDs.",
      "path": "/opt/p14-antigravity/skills/gdc-blueprint-adaptation/SKILL.md"
    },
    {
      "name": "gdc-e2e-iac-knitting",
      "description": "Knits multi-pattern GDC-blueprints solutions into the 5-stage gdc-iac-org GitOps hierarchy (0-bootstrap to 5-workload-factory).",
      "path": "/opt/p14-antigravity/skills/gdc-e2e-iac-knitting/SKILL.md"
    },
    {
      "name": "gdc-notebook-mlops",
      "description": "Structured Jupyter Notebook (.ipynb v4) cell inspection, editing, execution, magic commands, and KFP/Papermill pipeline export.",
      "path": "/opt/p14-antigravity/skills/gdc-notebook-mlops/SKILL.md"
    },
    {
      "name": "gdc-security-opa",
      "description": "Enforces GDC-ag Restricted Pod Security Standards (PSS), OIDC PKCE/JWKS isolation, zero-egress NetworkPolicies, and SAFE_ENV secret scrubbing.",
      "path": "/opt/p14-antigravity/skills/gdc-security-opa/SKILL.md"
    }
  ]
}
```

#### 3. Inspect Antigravity SDK Metadata & Structured Outputs on `/ai-chat`
Every `POST /instances/<session>/ai-chat` response returns:
- `agy_sdk_config`: Serialized Antigravity SDK `AgentConfig` (`config_class`, `model`, `behavior`, `token_threshold`, `skills_paths`, `allowed_tools`).
- `blueprint_plan`: Typed `BlueprintAdaptationPlan` structured output when invoking the Architect or Swarm persona.
- `total_usage`: Token usage breakdown (`input_tokens`, `output_tokens`, `thought_tokens`, `cached_tokens`, `total_tokens`).

```bash
curl -sk -X POST https://dev.gdc.local/instances/default-workspace/ai-chat \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-User: <developer-user>@<org-domain>" \
  -d '{
    "role": "architect",
    "prompt": "Adapt p14-antigravity-dev helm chart and add a notebook latency benchmark",
    "filename": "main.py",
    "backend_mode": "gdc_gemma_gw"
  }' | jq '{role, agent_name, agy_sdk_config, blueprint_plan, total_usage}'
```

---

## 5. Specialist Agent Personas & Principle of Least Privilege (PoLP)

Pattern 14 enforces role-based tool policies in [`build_polp_policies_for_role()`](example-app/orchestrator/gdc_agy_orchestrator.py) so no single persona can bypass workspace boundaries:

| Persona (`role`) | UI Dropdown Label | Default Model Tier | Allowed Tools (`allowed_tools`) | Denied / Guarded Tools & Security Controls |
| :--- | :--- | :--- | :--- | :--- |
| **`architect`** | `📐 Architect Agent (31b Dense - Design & ADRs)` | `gemma4:31b` (Tier 2 Reasoning) | `read_file`, `search_code`, `list_files`, `notebook_list_cells` | **Read-Only Confinement:** `apply_diff`, `write_file`, `notebook_edit_cell`, `notebook_run_cell`, and `run_terminal_command` are `DENY`. Produces typed `BlueprintAdaptationPlan` JSON + Markdown architecture spec. |
| **`coder`** (`builder`) | `💻 Coder Agent (26b MoE - Code & Diffs)` | `gemma4:26b` (Tier 1 Fast MoE) | `read_file`, `search_code`, `list_files`, `apply_diff`, `write_file`, `notebook_list_cells`, `notebook_get_cell_outputs`, `notebook_edit_cell` | **Selective Mutation Approval:** File and notebook cell mutations require Human-in-the-Loop (`ASK_USER`) approval card (`✓ Approve & Apply Diff`) in Selective mode, and automatically create `.bak` / `.ipynb.bak` rollback snapshots. `run_terminal_command` is `DENY`. |
| **`reviewer`** (`verifier`) | `🔍 Reviewer Agent (26b MoE - Security & QA)` | `gemma4:26b` (Tier 1 Fast MoE) | `read_file`, `search_code`, `list_files`, `notebook_list_cells`, `notebook_get_cell_outputs`, `notebook_run_cell`, `run_terminal_command` | **Predicate-Guarded Verification (`is_safe_verify_cmd`):** `run_terminal_command` only permits `pytest`, `python -m unittest`, `helm lint`, `verify.sh`, and `opa test`. Rejects shell chaining (`;`, `&&`, `\|`, `` ` ``, `$()`, `>`) and scrubs secrets via `build_safe_env()`. |
| **`swarm`** | `🐝 Multi-Agent Swarm (Auto Pipeline)` | `gemma4:31b` (Architect) -> `gemma4:26b` (Coder & Reviewer) | Sequential pipeline across all 3 specialist personas | Runs **Stage 1 (`📐 Architect`) -> Stage 2 (`💻 Coder`) -> Stage 3 (`🔍 Reviewer`)** in a single turn. If verification fails, triggers automatic retry (`max_retries=2`) and escalates from `26b` to `31b`. |

---

## 6. Modular GDC Skills (`SKILL.md`): Using Skills in the Code IDE & ClickOps Skill Creation

### 6.1. How Antigravity Skills Work in the Code IDE

Pattern 14 ships with four pre-installed GDC domain skills located in [`example-app/skills/`](example-app/skills/), baked into `/opt/p14-antigravity/skills/`, and **mirrored directly into your Code IDE workspace Explorer under `📁 skills/`**:

1. [`example-app/skills/gdc-blueprint-adaptation/SKILL.md`](example-app/skills/gdc-blueprint-adaptation/SKILL.md) (`skills/gdc-blueprint-adaptation/SKILL.md` in IDE) — Air-gapped Harbor registries, GDC StorageClasses (`standard-rwo`, `standard-rwx`), Gateway API `HTTPRoute`, and Helm chart parity.
2. [`example-app/skills/gdc-e2e-iac-knitting/SKILL.md`](example-app/skills/gdc-e2e-iac-knitting/SKILL.md) (`skills/gdc-e2e-iac-knitting/SKILL.md` in IDE) — 5-stage `gdc-iac-org` hierarchy (`0-bootstrap` to `5-workload-factory`).
3. [`example-app/skills/gdc-notebook-mlops/SKILL.md`](example-app/skills/gdc-notebook-mlops/SKILL.md) (`skills/gdc-notebook-mlops/SKILL.md` in IDE) — Structured `.ipynb` v4 cell tools, `%%agy_*` magics, `.ipynb.bak` rollback, and KFP/Papermill pipeline export.
4. [`example-app/skills/gdc-security-opa/SKILL.md`](example-app/skills/gdc-security-opa/SKILL.md) (`skills/gdc-security-opa/SKILL.md` in IDE) — Restricted Pod Security Standards (`PSS`), OIDC PKCE/JWKS isolation, zero-egress NetworkPolicies, and `SAFE_ENV` secret scrubbing.

**Zero-Restart Hot-Reload:**
[`get_installed_skills()`](example-app/orchestrator/gdc_agy_orchestrator.py) scans `/opt/p14-antigravity/skills`, `/tmp/p14-runtime-skills`, and `<workspace_dir>/skills/*/SKILL.md` dynamically on every request. Any edit saved to `skills/<name>/SKILL.md` in the Code IDE or any new `SKILL.md` created via the ClickOps Studio Drawer is picked up immediately on the next prompt without restarting the pod.

### 6.2. Using Skills in the Code IDE & Creating a New `SKILL.md` via ClickOps (`https://dev.gdc.local`)

1. **Select & Apply a Skill in the Code IDE's Right-Hand AI Swarm Dock:**
   - Directly above the **Agent Persona** dropdown in the right-hand **AI Swarm** dock sits the **`🧩 Antigravity SKILL.md (Active in IDE)`** bar (`#p14-ide-skill-bar`):
     - **Skill Dropdown (`#p14-active-skill-select`):** Select **`🔄 Auto-Match Skill from Prompt (All Skills)`** or pin a specific skill (`🧩 gdc-security-opa`, `🧩 gdc-blueprint-adaptation`, `🧩 gdc-e2e-iac-knitting`, `🧩 gdc-notebook-mlops`, or any custom ClickOps skill).
     - **`🚀 Apply Skill`:** Auto-populates and sends a skill-grounded prompt against the active file in the Code IDE, displaying a **`🧩 Antigravity Skill Active: <skill-name>`** compliance checklist banner at the top of the AI reply.
     - **`📄 Edit SKILL.md`:** Opens `skills/<skill-name>/SKILL.md` directly in the Code IDE editor (click **`👁️ Preview`** to render Markdown or **`💾 Save`** to hot-reload changes).
2. **ClickOps New Skill Creator (`➕ + New SKILL.md` & `🧩 Antigravity Skills` Studio Drawer):**
   - Click **`➕ + New SKILL.md`** (or **`🧩 Antigravity Skills (4)`**) in the top surface bar (or **`➕ + Skill`** in the AI Swarm dock) to open the **Antigravity Skills Manager & ClickOps `SKILL.md` Studio Drawer** (`#p14-skills-drawer`):
     - Pre-populated with a worked example (`gdc-gpu-cost-governance`, plus 1-click preset buttons **`⚡ Load Example: gdc-gpu-cost-governance`** and **`🔐 Load Example: gdc-airgap-telemetry-audit`**).
     - Click **`💾 Save & Register SKILL.md`** or **`📄 Save & Open SKILL.md in Code IDE Editor`** to create `skills/<name>/SKILL.md` in the Code IDE Explorer, register it in `/agy-config`, and activate it in the AI Swarm dropdown.
     - Each installed skill card also includes **`🚀 Apply in Code IDE (AI Swarm)`**, **`📄 Open & Edit SKILL.md in IDE`**, and **`🗑️ Delete`** (for custom ClickOps skills).

### 6.3. Required `SKILL.md` Format

Every skill resides in `skills/<skill-name>/SKILL.md` (and `/opt/p14-antigravity/skills/<skill-name>/SKILL.md`) and begins with YAML frontmatter defining `name` and `description`:

```markdown
---
name: gdc-custom-skill-name
description: Single-sentence summary of when and how the Antigravity agent should apply this skill.
---

# Skill Title & Rules

1. Concrete rule or checklist item #1.
2. Concrete rule or checklist item #2.
```

### 6.4. Method A: Create or List Skills via REST API (`/instances/<session>/skills`) or Pod CLI

```bash
# 1. Create a 5th skill ("gdc-gpu-cost-governance") via the Skills REST API
curl -sk -X POST https://dev.gdc.local/instances/default-workspace/skills \
  -H "Content-Type: application/json" \
  -H "X-Forwarded-User: <developer-user>@<org-domain>" \
  -d '{
    "action": "create_skill",
    "skill_name": "gdc-gpu-cost-governance",
    "description": "Enforces NVIDIA L4 GPU time-slicing quotas, idle notebook auto-hibernation, and LiteRT-LM 16k context window limits.",
    "instructions": "# GDC GPU Cost & Quota Governance Skill\n\n1. Require `computeProfile: \"cpu-gateway\"` for standard application engineering workspaces.\n2. Cap `gpu-litert-notebook` pods at `nvidia.com/gpu: 1` with `token_threshold: 16384`.\n3. Hibernate idle GPU sessions after 30 minutes of inactivity via the Sovereign Admin Console."
  }' | jq .

# 2. Verify the new skill appears on /agy-config
curl -sk https://admin.dev.gdc.local/agy-config | jq '.skills'
```

### 6.5. Method B: Declarative Kubernetes `ConfigMap` Volume Mount (GitOps / Cluster-Wide)

Mount a Kubernetes `ConfigMap` containing one or more custom `SKILL.md` files into `/opt/p14-antigravity/skills/<skill-name>/SKILL.md` across all workspace pods:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gdc-custom-skills-cm
  namespace: gdc-dev
data:
  SKILL.md: |
    ---
    name: gdc-gpu-cost-governance
    description: Enforces NVIDIA L4 GPU time-slicing quotas and idle notebook auto-hibernation.
    ---
    # GDC GPU Cost & Quota Governance
    1. Cap GPU pods at 16,384 context tokens.
```

### 6.6. Method C: Permanent Repository Addition & Harbor Image Build

```bash
# 1. Create or edit the skill in the canonical skills directory
mkdir -p p14-antigravity-dev/example-app/skills/gdc-gpu-cost-governance
vi p14-antigravity-dev/example-app/skills/gdc-gpu-cost-governance/SKILL.md

# 2. Sync into the self-contained Docker build contexts
cp -r p14-antigravity-dev/example-app/skills/* p14-antigravity-dev/example-app/landing-page/skills/
cp -r p14-antigravity-dev/example-app/skills/* p14-antigravity-dev/example-app/operator/skills/

# 3. Verify discovery via the Phase 5 test suite
python3 p14-antigravity-dev/test/test_phase5_antigravity_notebooks.py -v
```

---

## 7. Integrated JupyterLab 4 (`/lab/`), `.ipynb` v4 Tools & IPython Magics

### 7.1. Co-Located `/ide/` and `/lab/` Surface Architecture (`notebooks/gdc_blueprint_explorer.ipynb`)

Every workspace session provisions a starter `.ipynb` v4 notebook at `notebooks/gdc_blueprint_explorer.ipynb` on the shared `/home/dev/workspace` PVC rendered as 3 live, interactive cell cards (`Cell [0] (markdown)`, `Cell [1] (code)` with green `Out [1]:`, and `Cell [2] (code)` with red `Error [2]: ZeroDivisionError: division by zero`). Clicking **`📓 Integrated JupyterLab 4 (/lab/)`** in the top surface bar expands the **Integrated JupyterLab 4 Workspace Drawer** (`#p14-jupyterlab-drawer`) directly below the top bar, displaying:
- **Drawer Header Controls:** **`➕ + Code Cell`**, **`➕ + Markdown Cell`**, **`▶ Run All Cells`**, **`📖 Complete Notebook View`** (renders the entire `.ipynb` as a continuous formatted document), **`🗗 Split with IDE` / `🔲 Full-Screen Notebook`**, **`📄 Open .ipynb in IDE`** (syncs and opens `notebooks/gdc_blueprint_explorer.ipynb` in the Code IDE with **`👁️ Preview`**), **`⬇️ Download .ipynb`**, **`%%agy_architect → Cell [0]`**, **`%%agy_builder → Cell [1]`**, **`%%agy_verify → Cell [1]`**, and **`🔄 Refresh Cells`**.
- **Per-Cell ClickOps & Antigravity Controls (`Cell [i]`):** Every cell card (`Cell [0]`, `Cell [1]`, `Cell [2]`, `Cell [3]`, ...) includes its own **`▶ Run Cell [i]`** (which also expands inline `%%agy_*` magics written inside the cell), **`🤖 %%agy_builder`** (or **`📐 %%agy_architect`** on Markdown cells), **`🔍 %%agy_verify`**, **`⚡ Fix Cell [i]`** (when an error is present), **`✏️ Edit`** (inline `<textarea>` with **`▶ Save & Run Cell [i]`**, **`🤖 Synthesize with %%agy_builder`**, and **`💾 Save Cell [i]`**), **`➕ + Below`**, and **`🗑️ Delete`**.
- **Top Surface Bar Controls:** **`⚡ Fix Cell with Antigravity Agent`** (`%agy_fix` on `Cell [2]`) and **`↩️ Rollback .ipynb Cell`** (`.ipynb.bak` restore).

### 7.2. Structured `.ipynb` v4 Cell Tools (`/instances/<session>/notebooks`)

The orchestrator never uses raw text regexes on `.ipynb` JSON. Instead, it exposes eight structured cell operations backed by automatic `.ipynb.bak` snapshots:
- `list_cells` (`notebook_list_cells`): Returns cell indices, cell types (`markdown` / `code`), full source, `stdout`, `error_summary`, and complete `notebook_json`.
- `get_cell_outputs` (`notebook_get_cell_outputs`): Reads `stdout`, `stderr`, and traceback arrays for a specific cell index.
- `add_cell` (`notebook_add_cell`): Snapshots `<notebook>.ipynb.bak` and appends (`position=-1`) or inserts at `position` a new `code` (pre-populated with a worked `%%agy_builder` example) or `markdown` cell.
- `edit_cell` (`notebook_edit_cell`): Snapshots `<notebook>.ipynb.bak` and updates the target cell's `source` array while preserving `.ipynb` v4 schema integrity.
- `delete_cell` (`notebook_delete_cell`): Snapshots `<notebook>.ipynb.bak` and removes the cell at `cell_index` while preserving at least 1 cell in the notebook.
- `run_cell` (`notebook_run_cell`): Executes the target code cell (automatically expanding any inline `%%agy_*` magic) inside a scrubbed `SAFE_ENV` Python kernel (`REQ-SEC-010`) and appends the resulting output back into the `.ipynb` file.
- `run_all_cells` (`notebook_run_all_cells`): Sequentially executes all cells (`Cell [0]`..`Cell [N]`) top-to-bottom and returns updated cells plus complete `notebook_json`.
- `magic` (`%%agy_architect`, `%%agy_builder`, `%%agy_verify`, `%agy_fix`) & `rollback_cell` (`notebook_rollback_cell`): Executes Antigravity SDK cell magics in-place on `Cell [0]`, `Cell [1]`, `Cell [2]`, or any `target_cell_index`, or restores `notebooks/gdc_blueprint_explorer.ipynb` from its `.ipynb.bak` snapshot.

### 7.3. IPython Cell Magics ([`example-app/orchestrator/gdc_antigravity_magic.py`](example-app/orchestrator/gdc_antigravity_magic.py))

Loadable inside any Jupyter kernel via `%load_ext gdc_antigravity_magic` or triggered directly from the JupyterLab 4 drawer toolbar:
- **`%%agy_architect`:** Invokes the `31b` Architect persona across the active notebook and returns a structured `BlueprintAdaptationPlan` Markdown plan.
- **`%%agy_builder`:** Invokes the `26b` Builder/Coder persona to synthesize or patch cell code (gated by Human-in-the-Loop approval when `selective` policy is active).
- **`%%agy_verify`:** Invokes the `26b` Verifier/Reviewer persona (`CommandRegexPolicy`) to validate cell outputs in `SAFE_ENV`.
- **`%agy_fix` (`⚡ Fix Cell with Antigravity Agent`):** Diagnoses cell exceptions (such as `ZeroDivisionError`) and proposes a repaired cell block (`# Auto-Repaired by Antigravity Builder Agent`).

---

## 8. Sovereign Admin & Telemetry Console (`https://admin.dev.gdc.local` / Port `8081`)

Platform administrators access the **Sovereign Admin & Telemetry Console** on isolated Container Port `8081` (`https://admin.dev.gdc.local`), authenticated via `admin_auth_user` HMAC cookies (`<platform-admin>@<org-domain>` holding a `gdc-admin`, `dev-admin`, or `admin` role in Keycloak `gdc-dev-realm`) so administrative credentials never share cookie scope with developer workspaces on Port `8080`.

1. **Row 1 — 4-Up Executive KPI Grid:**
   - **Active Dev Sessions:** Count of `Running` workspaces vs. `Hibernated (0 CPU)` workspaces.
   - **AI Swarm Requests:** Cumulative AI prompts and estimated tokens generated across all workspaces.
   - **Avg Gateway Latency:** Rolling average latency (`ms`) to `gemma-gateway.gemma-inference.svc.cluster.local` plus active default model and temperature.
   - **Cluster Compute Quota:** Allocated vCPU cores (`N / 64`) and security posture (`PSS: Restricted | NetPol: Active`).
2. **Row 2 — Real-Time Cluster Broadcast & Dynamic AI Governance Controls:**
   - **📢 Cluster Broadcast Notification:** Push `Info (Blue)`, `Warning (Amber)`, or `Critical Maintenance (Red)` banners to all active developer IDEs within 5 seconds.
   - **⚙️ Dynamic AI Governance & Quota Policy:** Live cluster-wide overrides for **Default Swarm Model** (`gemma4:26b` vs `gemma4:31b`), **Temperature** (`0.0`–`0.7`), **Max Sessions / User** (`2`–`10`), and **Swarm Access Toggle** (`Enabled` vs `Kill-Switch: Disabled`).
3. **Row 3 — Model Tier & Agent Persona Utilization Breakdown:**
   - Progress bars tracking request share and average latency across `gemma4:26b` vs. `gemma4:31b` and across `📐 Architect`, `💻 Coder`, `🔍 Reviewer`, and `🐝 Full Swarm Pipeline`.
4. **Row 4 — Active Developer Workspaces & Lifecycle Controls Table:**
   - Per-workspace **`💤 Hibernate`** (scales compute to `0 CPU` while preserving PVC data), **`▶️ Resume`**, and **`🛑 Terminate`** controls.
5. **Row 5 — Live Agentic Inference Audit Log (Last 15 Invocations):**
   - Real-time table logging `Time (UTC)`, `Developer (OIDC)`, `Workspace`, `Persona / Agent`, `Model Routed`, `Latency`, `Est. Tokens`, and `Prompt Preview`.

---

## 9. Air-Gapped Packaging, Transfer & Production GDC-ag Deployment

### Step 1: Ensure Latest Antigravity SDK Is Staged & Package Offline Bundle (Connected Bastion)
Before packaging the air-gapped tarball on an internet-connected build bastion:

1. **Stage the Latest Antigravity SDK Wheel & Sovereign Binaries (Optional Drop-Ins):**
   - To bundle the latest compiled `google-antigravity` wheel into `/opt/wheelhouse` inside the container images, either set `FETCH_LATEST_AGY_WHEEL=true` or place `google_antigravity-*.whl` directly into `p14-antigravity-dev/example-app/landing-page/binaries/` and `p14-antigravity-dev/example-app/operator/binaries/`:
     ```bash
     # Download the latest google-antigravity wheel into binaries/ so Docker installs it into /opt/wheelhouse
     pip download --no-deps -d p14-antigravity-dev/example-app/landing-page/binaries google-antigravity
     cp -f p14-antigravity-dev/example-app/landing-page/binaries/google_antigravity-*.whl \
           p14-antigravity-dev/example-app/operator/binaries/
     ```
   - Place `gdcloud-linux-amd64.tar.gz` into `binaries/` if bundling the full sovereign `gdcloud` CLI.
2. **Build Images, Scan for Vulnerabilities, and Export the Air-Gap Bundle:**
   `package-for-gdc.sh` automatically synchronizes the canonical [`gdc_agy_orchestrator.py`](example-app/orchestrator/gdc_agy_orchestrator.py), [`gdc_antigravity_magic.py`](example-app/orchestrator/gdc_antigravity_magic.py), and [`example-app/skills/`](example-app/skills/) into the container build contexts, verifies that `manifests/gdc/` contains no non-production registry references, and exports the OCI image and manifest tarballs:
   ```bash
   # Build production images for harbor.gdc.local
   docker build -t harbor.gdc.local/blueprint-images/gdc-dev-landing-page:v1.0.0 p14-antigravity-dev/example-app/landing-page/
   docker build -t harbor.gdc.local/blueprint-images/gdc-dev-operator:v1.0.0 p14-antigravity-dev/example-app/operator/
   docker build -t harbor.gdc.local/blueprint-images/gdc-dev-workspace:v1.0.0 p14-antigravity-dev/example-app/workspace/

   # Run offline verification & container CVE vulnerability scan before packaging
   ./p14-antigravity-dev/test/verify.sh
   trivy image --severity HIGH,CRITICAL --ignore-unfixed harbor.gdc.local/blueprint-images/gdc-dev-landing-page:v1.0.0
   trivy image --severity HIGH,CRITICAL --ignore-unfixed harbor.gdc.local/blueprint-images/gdc-dev-operator:v1.0.0
   trivy image --severity HIGH,CRITICAL --ignore-unfixed harbor.gdc.local/blueprint-images/gdc-dev-workspace:v1.0.0

   # Export packages/p14-antigravity-dev/p14-antigravity-dev-gdc-{images.tar,manifests.tar.gz}
   ./p14-antigravity-dev/scripts/package-for-gdc.sh
   ```

### Step 2: Unpack & Push to Sovereign Harbor Registry inside GDC-ag Enclave
```bash
export TARGET_REGISTRY="harbor.gdc.local/blueprint-images"
export PROJECT_ID="gdc-dev"
./p14-antigravity-dev/scripts/unpack-for-gdc.sh
```

### Step 3: Configure Gateways, OIDC & Deploy Pattern 14 Manifests on GDC-ag
Before applying the manifests, verify you have updated your target **AI Inference Gateway** ([Section 2.3](#23-configuring--swapping-the-ai-inference-gateway-for-deployment)), **Keycloak OIDC realm** ([Section 2.4](#24-configuring-keycloak-oidc-for-production-gdc-dev-realm--rbac-claims)), and **Kubernetes Gateway API Ingress & TLS** ([Section 2.5](#25-configuring-the-kubernetes-gateway-api-ingress-gdc-dev-gateway--tls-for-deployment)):
```bash
kubectl apply -f p14-antigravity-dev/manifests/gdc/namespace.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/certificate.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gateway.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/loadbalancer.yaml
# Apply oidc-auth-configmap.yaml for production Keycloak OIDC (use mock-auth-configmap.yaml only in offline lab emulation)
kubectl apply -f p14-antigravity-dev/manifests/gdc/oidc-auth-configmap.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-dev-agent-configmap.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-antigravity-notebook-configmap.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-dev-operator.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/network-policy.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/network-policy-ai.yaml
kubectl apply -f p14-antigravity-dev/manifests/gdc/gdc-dev-phase3-deployment.yaml
```

---

## 10. End-to-End GDC-ag Walkthrough & Verification

### 10.1. Automated Offline & Live Validation Suites
```bash
# Run all 87 offline unit, security, OIDC, NetworkPolicy, Telemetry, Antigravity SDK & Notebook tests (8 suites)
./p14-antigravity-dev/test/verify.sh

# Run the live GDC-ag cluster smoke checks + 10-stage Multi-Agent Swarm + Phase 5 Antigravity/Notebook suite
python3 p14-antigravity-dev/scripts/test-agy-swarm.py \
  --admin-url https://admin.dev.gdc.local \
  --ide-url https://dev.gdc.local
```

### 10.2. Interactive Browser Walkthrough (`https://dev.gdc.local` & `https://admin.dev.gdc.local`)
1. **Authenticate via Keycloak OIDC (`https://dev.gdc.local`):**
   - Sign in with your Keycloak developer account (`<developer-user>@<org-domain>` in `gdc-dev-realm`) and launch `default-workspace`.
   - Verify the **Pattern 14 Antigravity Surface Bar** displays `Profile: cpu-gateway | SDK: LocalOpenAIAgentConfig.lightweight() / LiteRTAgentConfig`.
2. **Exercise ClickOps `SKILL.md` Creation, Code IDE Skill Application & the 4 Antigravity Agent Personas:**
   - **ClickOps `SKILL.md` Creation (`➕ + New SKILL.md`):** Click **`➕ + New SKILL.md`** in the top surface bar, review the pre-populated `gdc-gpu-cost-governance` skill form, and click **`📄 Save & Open SKILL.md in Code IDE Editor`** to sync `skills/gdc-gpu-cost-governance/SKILL.md` into the Code IDE Explorer and select it in the **`🧩 Antigravity SKILL.md (Active in IDE)`** bar.
   - **Apply Skill in Code IDE (`🚀 Apply Skill`):** In the right-hand AI Swarm dock, click **`🚀 Apply Skill`** to run the active `SKILL.md` against `main.py` and verify the **`🧩 Antigravity Skill Active`** compliance header in the reply.
   - **`📐 Architect Agent`:** Prompt *"Design a modular telemetry collector for GDC air-gapped workloads"* and click **`💾 Save as File`** (`architecture.md`).
   - **`💻 Coder Agent`:** Prompt *"Add a helper function is_prime(n) to main.py"*, review the unified diff card, and click **`✓ Approve & Apply Diff`**.
   - **`🔍 Reviewer Agent`:** Prompt *"Synthesize a pytest suite for is_prime(n) in test_main.py"*.
   - **`🐝 Multi-Agent Swarm`:** Create or switch to a clean project via **`+ New / Switch`** (e.g., `testing-swarm`), prompt *"Build and verify a token budget calculator module for GDC-ag"*, click **`⚡ Auto-Create All Swarm Files (3)`**, and inspect `rate_limiter_architecture.md` (clicking **`👁️ Preview`**), `main.py`, `rate_limiter.py` (clicking **`▶ Run Code`**), and `test_rate_limiter.py` (running `python3 -m unittest test_rate_limiter.py -v` in the terminal).
3. **Exercise Integrated JupyterLab 4 (`/lab/`), ClickOps Cell Controls, Complete Notebook View, `%%agy_*` Magics & `%agy_fix`:**
   - Click **`📓 Integrated JupyterLab 4 (/lab/)`** in the top surface bar to expand the drawer for **`notebooks/gdc_blueprint_explorer.ipynb`** directly beneath the top bar (`Cell [0] (markdown)`, `Cell [1] (code)` with green `Out [1]:`, and `Cell [2] (code)` with red `Error [2]: ZeroDivisionError`).
   - Click **`%%agy_architect → Cell [0]`**, **`%%agy_builder → Cell [1]`**, and **`%%agy_verify → Cell [1]`** in the drawer header to watch each target cell card highlight and update in-place inside `#p14-notebook-cells-container`.
   - Click **`⚡ Fix Cell with Antigravity Agent`** in the top surface bar to auto-diagnose and repair `Cell [2]` (`120 / 0` -> `120 / 1`, `Out [2]: Throughput QPS: 120.0`) via `%agy_fix`.
   - Use the ClickOps cell buttons (**`➕ + Code Cell`**, **`➕ + Markdown Cell`**, **`➕ + Below`**, **`✏️ Edit`** -> **`▶ Save & Run Cell [i]`**, and **`🗑️ Delete`**) to add, inline-edit, execute, and delete cells, click **`📖 Complete Notebook View`** / **`▶ Run All Cells`** / **`📄 Open .ipynb in IDE`** / **`⬇️ Download .ipynb`** to inspect the complete notebook, and click **`↩️ Rollback .ipynb Cell`** to restore `notebooks/gdc_blueprint_explorer.ipynb` from `.ipynb.bak`.
4. **Inspect Telemetry & Push Governance Policy (`https://admin.dev.gdc.local`):**
   - Sign in with a Keycloak platform administrator account (`<platform-admin>@<org-domain>` assigned the `gdc-admin` or `dev-admin` role in `gdc-dev-realm`) on `https://admin.dev.gdc.local`.
   - Inspect the **4-Up KPI Grid**, **Model & Persona Utilization Bars**, and **Live Agentic Inference Audit Log**.
   - Push a maintenance banner via **`📢 Cluster Broadcast Notification`** and verify it appears at the top of `https://dev.gdc.local` within 5 seconds.

---

## 11. Helm & IaC Orchestrated Deployment (`foundations/releases/5-workload-factory`)

In addition to standalone manifest application (`kubectl apply -f manifests/gdc/`), Pattern 14 provides a parameterized Helm chart in [`chart/`](./chart/) designed for the 5-stage `gdc-iac-org` GitOps hierarchy (`foundations/releases/5-workload-factory`).

### Option A: Orchestrated Deployment via Helmfile (`foundations/`)
Declare `p14-antigravity-dev` under your tenant project's `resources.patterns` list in `foundations/bases/environments/<env>/tenants-org-<N>.yaml`:

```yaml
resources:
  patterns:
    - name: "my-p14-antigravity-dev"
      pattern: "p14-antigravity-dev"
      namespace: "my-gdc-project"
      registry: "harbor.gdc.local/blueprint-images"
      deploy_gdc_resources: false
      deploy_apps: true
```

Then template or apply Stage 5 from `foundations/`:
```bash
cd foundations
helmfile -e dev -l stage=5-workload-factory template
helmfile -e dev -l stage=5-workload-factory apply
```

### Option B: Direct Helm CLI Deployment
```bash
# 1. Deploy default zero-GPU developer workspace (computeProfile=cpu-gateway) with gdc_gemma_gw
helm upgrade --install p14-antigravity-dev ./p14-antigravity-dev/chart \
  --namespace my-gdc-project \
  --set global.projectId=my-gdc-project \
  --set global.namespace=my-gdc-project \
  --set global.registry=harbor.gdc.local/blueprint-images \
  --set computeProfile=cpu-gateway \
  --set ai.backendMode=gdc_gemma_gw \
  --set ai.openaiApiBaseUrl=http://gemma-gateway.gemma-inference.svc.cluster.local/v1 \
  --set ai.gatewayNamespace=gemma-inference \
  --set gateway.domain=dev.gdc.local \
  --set gateway.adminDomain=admin.dev.gdc.local \
  --set gateway.tlsSecretName=gdc-dev-tls-secret

# 2. Deploy against an alternative OpenAI-compatible or GDC Gemini AI Gateway
helm upgrade --install p14-antigravity-dev ./p14-antigravity-dev/chart \
  --namespace my-gdc-project \
  --set global.projectId=my-gdc-project \
  --set global.namespace=my-gdc-project \
  --set global.registry=harbor.gdc.local/blueprint-images \
  --set computeProfile=cpu-gateway \
  --set ai.backendMode=gdc_gemini \
  --set ai.provider=gemini \
  --set ai.geminiBaseUrl=https://gemini.gdc.local:443/v1/projects/my-gdc-project/locations/us-central1 \
  --set ai.geminiEndpoint=https://gemini.gdc.local:443/v1/projects/my-gdc-project/locations/us-central1/chat/completions

# 3. Deploy GPU-enabled LiteRT-LM & CUDA Notebook profile (computeProfile=gpu-litert-notebook)
helm upgrade --install p14-antigravity-dev ./p14-antigravity-dev/chart \
  --namespace my-gdc-project \
  --set global.projectId=my-gdc-project \
  --set global.namespace=my-gdc-project \
  --set global.registry=harbor.gdc.local/blueprint-images \
  --set computeProfile=gpu-litert-notebook \
  --set ai.backendMode=litert_on_device
```
