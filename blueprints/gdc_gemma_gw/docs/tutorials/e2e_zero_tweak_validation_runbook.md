Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Zero-Tweak E2E Validation Runbook & IO/AO Upgrade Verification Suite

> **Document ID:** `RUNBOOK-E2E-ZERO-TWEAK-AND-UPGRADE-SUITE`  
> **Companion Guides:**  
> - [AI-Enabled Blueprint E2E Test Guide (GCP Staging & Development)](./ai_enabled_e2e_gcp_staging_guide.md)  
> - [AI-Enabled Blueprint E2E Deployment & Verification Guide (GDC-ag Production IaC)](./ai_enabled_e2e_gdc_production_iac_guide.md)  
> - [GUI Functional Walkthrough & Live Demo Playbook](./gui_demo_walkthrough_and_prompts.md)  
> **Automated CLI Suites:**  
> - **GCP Staging (17 Checks):** `scripts/verify-e2e-gcp-staging.py`  
> - **GDC-ag Production IO/AO Upgrade Suite (20 Checks):** `scripts/verify-e2e-gdc-ag.py`

---

## 1. Overview: What Has Been Baked In for a "Zero-Tweak" Run

Every manual workaround or post-deployment patch encountered in prior sessions is now baked directly into the repository scripts, manifests, Helm charts, and guides so that running [ai_enabled_e2e_gcp_staging_guide.md](./ai_enabled_e2e_gcp_staging_guide.md) from top to bottom requires **zero manual tweaks**:

| Previously Encountered Issue | Baked-In Permanent Fix |
| :--- | :--- |
| **`git pull` blocked by modified manifests (`01-gateway-ollama.yaml`, `backend.yaml`)** | `git stash 2>/dev/null \|\| true` is included before `git pull origin main` in Steps 2.1 and 3. |
| **GKE GPU stockout vs. existing Artifact Registry in a different region** | Step 2.1 detects any running `gdc-gemma-cluster` (never deleting it) and exports `CLUSTER_ZONE` / `CLUSTER_REGION`; Step 2.2 independently configures or auto-detects `AR_REGION` and `REGISTRY_HOST`. |
| **`gcloud projects add-iam-policy-binding` failing on projects with IAM conditions** | Added `--condition=None` in both `deploy-e2e-solution.sh` and Step 3 of the guide. |
| **GCS Bucket `gs://gemma-client-files-${PROJECT_ID}` existence check & double `gs://gs://` prefix** | `deploy-e2e-solution.sh` and Step 3 check `gcloud storage buckets describe` and create the bucket if missing; `storage.py` and `workloads.yaml` normalize any `gs://` or `s3://` prefix. |
| **PostgreSQL `postgres-0` readiness race & multi-worker `uuid-ossp` initialization** | `deploy-e2e-solution.sh` waits for `pg_isready` before seeding `seed_readiness_db.sql`; `database.py` uses `gen_random_uuid()` and isolates each `CREATE TABLE IF NOT EXISTS` statement. |
| **Unchecking `Use provided sources` (`only_use_sources=false`) staying stuck in RAG refusal mode** | `chat.py` injects explicit general-chat instructions, marks uploaded files as optional reference context, and strips prior `"I cannot answer this based on the provided sources"` refusals from conversation history. |
| **`gemma-gateway` OIDC (`ENABLE_OIDC=true`) rejecting in-cluster `gemma-client` & `gdc-dev` calls** | `gateway/proxy/main.py` accepts verified upstream identity headers (`X-User-ID`, `X-Authenticated-User`, `X-Forwarded-User`) when `Authorization: Bearer gdc-no-auth-required` is sent, while strictly verifying real RS256 JWTs and rejecting unauthenticated calls with `401`. |
| **Python `< 3.12` `SyntaxError` on `\"` inside f-strings in `python3 -c '...'` blocks** | All `python3 -c` snippets across both guides extract dictionary/header values into local variables before formatting f-strings. |
| **Tab 3 (`Operational Readiness SQL`) `DROP TABLE` relying on LLM output** | `intel_services.py` enforces both pre-execution user-input DDL/DML detection (`has_destructive_sql_intent`) and post-generation `is_safe_sql` validation, deterministically returning `-- Rejected by Security Gate`. |

---

## 2. Tomorrow's Zero-Tweak Execution Sequence (GCP Staging Validation)

Run the following sequence on your **Cloud Workstation** (`~/GitHub/gdc_gemma_gw`) to validate the entire GCP Staging guide from a clean workload state with zero manual tweaks.

### Phase 1: Pull Latest Code & Run Non-Destructive Workload Reset (~1 min)

```bash
cd ~/GitHub/gdc_gemma_gw
git stash 2>/dev/null || true
git pull origin main

# Clean up existing Kubernetes workloads/namespaces while PRESERVING your GKE cluster,
# GPU nodes, Artifact Registry images, and GCS bucket (or pass --empty-bucket to wipe bucket objects):
./scripts/cleanup-e2e-gcp.sh --empty-bucket
```

### Phase 2: Execute Steps 1–5 of `ai_enabled_e2e_gcp_staging_guide.md` (~8–10 mins on warm cluster)

Follow Sections **2 through 6.1** of [ai_enabled_e2e_gcp_staging_guide.md](./ai_enabled_e2e_gcp_staging_guide.md) verbatim:
1. **Section 2.1 (Step 1A)**: Detects your running `gdc-gemma-cluster`, configures `kubectl` credentials, verifies `client-pool`, `REGIONAL_MANAGED_PROXY` subnet, and `allow-gateway-internal` firewall rule.
2. **Section 2.2 (Step 1B)**: Exports `AR_REGION`, `AR_REPO_NAME`, and `REGISTRY_HOST` (use Option A if known, or Option B to auto-detect).
3. **Section 3 (Step 2)**: Deploys `ollama-26b`, `ollama-31b`, and `gemma-gateway` (`./standalone/install-all.sh`) and sets the Gateway OIDC & `InferencePool` environment variables.
4. **Section 4 (Step 3)**: Verifies/creates `gs://gemma-client-files-${PROJECT_ID}` with Workload Identity (`--condition=None`), deploys `postgres-0` and `keycloak`, runs `INGRESS_MODE=nginx ./scripts/deploy-e2e-solution.sh`, and enables `gdc-platform-gateway` + `gdc-gateway-tunnel` (`Port 8081`).
5. **Section 5 (Step 4)**: Deploys `p13-gdc-dev` (`gdc-dev-landing-page` and `gdc-dev-operator`) in `gdc-dev`.
6. **Section 6.1 (Step 5A)**: Starts the 5 background `kubectl port-forward` loops (`8080`–`8084`) and confirms `HTTP 200` on all 5 ports.

### Phase 3: Run the Standalone 17-Check Automated CLI Verification Suite (~1–2 mins)

Once Ports `8080`–`8084` report `HTTP 200`, execute the standalone verification script:

```bash
cd ~/GitHub/gdc_gemma_gw
chmod +x scripts/verify-e2e-gcp-staging.py

./scripts/verify-e2e-gcp-staging.py --json-report /tmp/gcp-staging-e2e-report.json
```

**Expected Output (`17/17 PASS`):**

```text
========================================================================================
🚀 AI-ENABLED BLUEPRINT E2E UPGRADE & FUNCTIONAL VERIFICATION (GCP STAGING)
   Port 8080 (Gateway Control Plane) : http://127.0.0.1:8080
   Port 8081 (Gateway API Client)    : http://127.0.0.1:8081
   Port 8082 (NGINX Ingress Client)  : http://127.0.0.1:8082
   Port 8083 (gdc-dev Admin Console) : http://127.0.0.1:8083
   Port 8084 (gdc-dev Developer IDE) : http://127.0.0.1:8084
========================================================================================
[TEST-01] [IO] Kubernetes Pods & Namespace Readiness ... [PASS]
[TEST-02] [AO] Port 8080 Admin Control Plane Auth Guardrail ... [PASS]
[TEST-03] [AO] Port 8080 Keycloak OIDC SSO Login (/login/oidc) ... [PASS]
[TEST-04] [AO] Port 8080 Gateway Live Telemetry (/api/metrics) ... [PASS]
[TEST-05] [AO] Port 8080 Tier 1 (26B MoE) Auto-Routing ... [PASS]
[TEST-06] [AO] Port 8080 Tier 2 (31B Dense) + System Role Flattener ... [PASS]
[TEST-07] [AO] Port 8080 Admin Parameter Hot-Swap (/admin/config) ... [PASS]
[TEST-08] [AO] Port 8080 Session Oversight & Blocklist Enforcement ... [PASS]
[TEST-09] [AO] Port 8081 (Gateway API) & Port 8082 (Ingress) Parity ... [PASS]
[TEST-10] [AO] Port 8081 Tab 1: Multi-Domain Kafka Sensor Telemetry ... [PASS]
[TEST-11] [AO] Port 8081 Tab 2: All-Source SITREP RAG Synthesis ... [PASS]
[TEST-12] [AO] Port 8081 Tab 3: Agentic Text-to-SQL Readiness Audit ... [PASS]
[TEST-13] [AO] Port 8081 Tab 3: SQL Security Gate (DROP TABLE Rejection) ... [PASS]
[TEST-14] [AO] Port 8081 Gemma Client: Document Upload & Storage Readback ... [PASS]
[TEST-15] [AO] Port 8081 Gemma Client: Source-Grounded RAG -> General Chat Toggle ... [PASS]
[TEST-16] [AO] Port 8083 gdc-dev Admin Telemetry & Broadcast Banner ... [PASS]
[TEST-17] [AO] Port 8084 gdc-dev AI Swarm & Port 8080 Session Audit ... [PASS]
========================================================================================
📊 SUMMARY: ALL TESTS PASSED | PASS: 17/17 | FAIL: 0/17 | SKIP: 0/17
========================================================================================
```

### Phase 4: Interactive GUI Walkthrough & Demo Validation

Follow the companion [GUI Functional Walkthrough & Live Demo Playbook](./gui_demo_walkthrough_and_prompts.md) across Ports `8080`–`8084`.

### Phase 5: Execute Step 6 (`Ollama` $\rightarrow$ `vLLM` $\rightarrow$ `Ollama` Live Engine Flip) & Re-Run CLI Suite

Follow **Section 7 (Step 6)** of [ai_enabled_e2e_gcp_staging_guide.md](./ai_enabled_e2e_gcp_staging_guide.md):
1. Flip to `vLLM` (**Phase 6A**) and run `./scripts/verify-e2e-gcp-staging.py` to confirm all 17 checks pass on `vLLM` as well.
2. Flip back to `Ollama` (**Phase 6C**) and confirm `framework == "ollama"` is restored.

---

## 3. GDC-ag Production IO / AO Pre- & Post-Upgrade Verification Routine (`scripts/verify-e2e-gdc-ag.py`)

For **Infrastructure Operators (IOs)** and **Application Operators (AOs)** operating Google Distributed Cloud Air-Gapped (**GDC-ag**), `scripts/verify-e2e-gdc-ag.py` provides a zero-dependency (Python 3 stdlib only) upgrade gate that can be executed **before** and **after** GDC platform upgrades, Helmfile stage rollouts, or model weight updates.

### 3.1. What `verify-e2e-gdc-ag.py` Validates (`TEST-01` – `TEST-20`)

| Test ID | Persona | Feature / Subsystem | Success Criteria (`[PASS]`) |
| :--- | :--- | :--- | :--- |
| **`TEST-01`** | **IO** | **Tenant Namespace & Workload Pod Health** | All pods in `gemma-inference` and `gdc-dev` are `Running` (or `Succeeded`) with zero crash loops. |
| **`TEST-02`** | **IO** | **GPU Serving Engine Pods (`vLLM` / `Ollama`)** | Active GPU serving pods (`vllm-26b`, `vllm-31b`, or `ollama-*`) are `Running`. |
| **`TEST-03`** | **IO** | **Gateway API Inference Extension CRDs** | Verifies `InferencePool` CRD instances (`gemma-26b-pool`, `gemma-31b-pool`) when installed (`[SKIP]` if direct routing is used). |
| **`TEST-04`** | **IO** | **Gateway API Routes & DB Credentials Secret** | Confirms `Gateway`/`HTTPRoute` resources and `secret/gemma-client-db-credentials` exist. |
| **`TEST-05`** | **AO** | **Gateway Unauthenticated Zero-Trust Guardrail** | Unauthenticated `GET /admin/sessions` and `POST /v1/chat/completions` return `HTTP 401`. |
| **`TEST-06`** | **AO** | **Keycloak OIDC Authentication (`/login/oidc`)** | Exchanges Keycloak credentials (`charlie`), sets `HttpOnly` session cookies, and acquires RS256 JWT. |
| **`TEST-07`** | **AO** | **Gateway Live Telemetry & Engine Health (`/api/metrics`)** | Returns `status: "online"`, active `framework` (`vllm`/`ollama`), `model`, and GPU/VRAM metrics. |
| **`TEST-08`** | **AO** | **Tier 1 (`26B MoE`) Complexity Auto-Routing** | Simple prompt with `model="gemma4"` routes to `gemma4:26b` (`X-Model-Tier: tier1-moe-26b`). |
| **`TEST-09`** | **AO** | **Tier 2 (`31B Dense`) Routing + System-Role Flattener** | System-role + code prompt flattens cleanly and routes to `gemma4:31b` (`X-Model-Tier: tier2-dense-31b`). |
| **`TEST-10`** | **AO** | **Admin Parameter Override Hot-Swap (`/admin/config`)** | Updates `temperature=0.4` via `POST /admin/config` and restores `temperature=0.7`. |
| **`TEST-11`** | **AO** | **Session Oversight & User Blocklist Enforcement** | Blocks a test user via `/admin/block`, verifies presence in `/admin/sessions`, and unblocks via `/admin/unblock`. |
| **`TEST-12`** | **AO** | **Gateway API (`intel.gdc.local`) & Ingress (`intel-ingress.gdc.local`) Parity** | Both traffic exposure paths return `HTTP 200` on `/`, `/api/health`, and `/api/models`. |
| **`TEST-13`** | **AO** | **Intel Console Tab 1: Multi-Domain Kafka Telemetry** | Simulates and retrieves multi-domain sensor events (`LAND`, `AIR`, `SEA`, `SPACE`, `CYBER`). |
| **`TEST-14`** | **AO** | **Intel Console Tab 2: All-Source SITREP RAG Synthesis** | Returns grounded synthesis and `[SITREP-...]` citations from `intelligence_reports`. |
| **`TEST-15`** | **AO** | **Intel Console Tab 3: Agentic Text-to-SQL Readiness Audit** | Translates natural-language question into read-only `SELECT` SQL, returns rows from `military_units`, and summarizes. |
| **`TEST-16`** | **AO** | **Intel Console Tab 3: SQL Security Gate (`DROP TABLE` Rejection)** | Rejects `DROP TABLE military_units;` with `generated_sql: "-- Rejected by Security Gate"`. |
| **`TEST-17`** | **AO** | **Gemma Client: Object Storage Upload & Readback** | Uploads synthetic directive (`VANGUARD-OMEGA-749`) to `s3://gemma-rag-bucket` / `gs://...` and verifies readback. |
| **`TEST-18`** | **AO** | **Gemma Client: Strict RAG $\rightarrow$ General Chat Toggle** | Turn 1 (`only_use_sources: true`) extracts `VANGUARD-OMEGA-749`; Turn 2 (`only_use_sources: false`, same chat) answers `"Paris"` cleanly. |
| **`TEST-19`** | **AO** | **`gdc-dev` Sovereign Admin Telemetry & Broadcast Banner** | Verifies `/admin/telemetry/json` and confirms broadcast banner propagates from Admin Console to Developer IDE. |
| **`TEST-20`** | **AO** | **`gdc-dev` Multi-Agent Swarm & Gateway Session Audit** | Executes `coder` agent prompt on Developer IDE and verifies active user sessions on the Gateway Control Plane. |

### 3.2. Running `verify-e2e-gdc-ag.py` During GDC-ag Maintenance & Upgrades

```bash
cd ~/GitHub/gdc-iac-org

# 1. Infrastructure Operator (IO) Pre-/Post-Upgrade Check Only:
./scripts/verify-e2e-gdc-ag.py --persona io

# 2. Full IO + AO Suite against GDC-ag Production FQDNs (with internal PKI CA bundle or --insecure):
./scripts/verify-e2e-gdc-ag.py --insecure --json-report /tmp/gdc-upgrade-report.json

# 3. Full IO + AO Suite via Operator Workstation Port-Forwards (Ports 8080-8084):
./scripts/verify-e2e-gdc-ag.py --port-forward --json-report /tmp/gdc-upgrade-report.json
```
