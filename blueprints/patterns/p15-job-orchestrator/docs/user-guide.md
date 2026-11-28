<!--
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 15 (`p15-job-orchestrator`): Operator User Guide

Running recurring batch processing, platform hygiene checks, and policy enforcement inside an air-gapped **Google Distributed Cloud Air-Gapped (`GDC-ag`)** enclave without managed cloud schedulers creates an operational split. Teams either rely on ad-hoc `CronJob` manifests that lack audit trails, backfills, and failover recovery, or they hand application teams cluster-wide privileges that break multi-tenant isolation.

**Pattern 15 (`p15-job-orchestrator`)** resolves that tension through a single governed control plane (`p15-job-manager`) split across two strictly isolated surfaces: the **Job Portal & OpenAPI REST API (`:8080`)** for day-to-day schedule operations, and the **PA Platform Admin Console (`:8081`)** for platform-wide governance and emergency controls. This guide walks **Application Operators (`AO`)** and **Platform Administrators (`PA`)** through every day-2 workflow, from creating a UTC-safe schedule to executing a Four-Eyes human-in-the-loop (`HITL`) approval, verifying signed air-gapped notifications, and diagnosing failures.

> **Target Platform:** Google Distributed Cloud Air-Gapped (`GDC-ag` `v1.16.2+`)  
> **Related Documentation:**
> - **Architecture & Stage 2–5 Deployment Runbook:** [`../README.md`](../README.md)
> - **Air-Gapped Notification & Incident Integration Guide:** [`./notification-integrations.md`](./notification-integrations.md)

---

## 1. Know Your Role & Operating Surface (`PA` vs. `AO`)

Pattern 15 applies a split-scope operating model: **Platform Administrators (`PA`)** govern *of the platform* (allowlists, quotas, templates, cross-namespace watchers, and emergency kill-switches), while **Application Operators (`AO`)** operate *on the platform* inside their assigned namespace.

| Surface & Port | Primary Audience | Authentication & Role Claim | What You Can Do |
| :--- | :--- | :--- | :--- |
| **Job Portal & REST API (`:8080`)**<br>`https://jobs.gdc.local` | `AO` & `PA` | Keycloak OIDC (`jobs_user_session` cookie or Bearer JWT): `ao-job-operator-<ns>`, `job-viewer-<ns>`, or `pa-job-admin` | Preview and register schedules, trigger immediate runs (`Run Now`), run UTC backfills, inspect runs and redacted logs, review HITL approvals, and register namespace notification sinks. |
| **PA Platform Admin Console (`:8081`)**<br>`https://admin.jobs.gdc.local` | `PA` Only | Keycloak OIDC (`jobs_admin_session` cookie or Bearer JWT): strictly `pa-job-admin` (`AO` roles receive `403 Forbidden`) | Inspect platform overview, manage `ALLOWED_NOTIFICATION_HOSTS` SSRF allowlist, configure namespace shard quotas, and toggle the **Global Emergency Pause-All Kill-Switch**. |
| **Prometheus Telemetry (`:9091`)**<br>`Service/p15-job-metrics` | Platform Observability | Internal cluster scrape by GDC `MonitoringTarget` | Exposes `/metrics` (`gdc_job_runs_total`, `gdc_job_watermark_lag_seconds`, `gdc_job_circuit_breaker_open`, and enforcement/self-heal counters). |

### Choosing Between Profile B (`k8s-native`) and Profile A (`argo`)
Your workflow in the portal and REST API is identical regardless of the active engine mode shown in the top header badge:
- **Profile B (`engine.mode: "k8s-native"` — Shared Cluster Default):** Compiles schedules into native Kubernetes `batch/v1` `CronJob` and `Job` objects with zero custom CRDs and zero `ClusterRole`s. Use this when operating in a multi-tenant Shared Cluster namespace.
- **Profile A (`engine.mode: "argo"` — Standard Cluster Default):** Compiles schedules into Argo `CronWorkflow` and `Workflow` DAGs referencing `ClusterWorkflowTemplate/gdc-standard-job-runner-v1`. Use this on a dedicated Standard Cluster when you need multi-step pipelines or dynamic shard fan-out (`maxShardsPerRun=50`).

---

## 2. Keycloak (`p12-keycloak`) Integration, Authentication (`AuthN`) & Authorisation (`AuthZ`)

Production deployments on GDC-ag **must** authenticate every human operator and CI pipeline against your internal **Keycloak (`p12-keycloak`)** identity provider using **OIDC Authorization Code + PKCE (`S256`)** and **RS256 JWKS verification** (`ALLOW_SIMULATED_OIDC="false"` is enforced by Rego policy and air-gap packaging gates).

### 2.1 Prerequisites, Network Policies & Internal CA Trust

Before wiring Keycloak, confirm three platform prerequisites:
1. **Keycloak Deployed (`p12-keycloak`):** Pattern 12 (`p12-keycloak`) is running with a valid internal TLS certificate issued by your GDC CA and backed by a managed HA PostgreSQL `DBCluster`.
2. **Explicit Network Egress:** Confirm that Stage 2 `ProjectNetworkPolicy` (`manifests/gdc/network/pnp-cross-project.yaml`, applied **after** `pnp-intra-project-egress.yaml`) and Stage 5 `NetworkPolicy/p15-allow-control-plane-and-workers` (`manifests/apps/network-policy.yaml`) allow TCP ports `80`/`443`/`8080` from the Pattern 15 namespace to the `p12-keycloak` namespace.
3. **Internal CA Bundle Mounted:** Mount your enclave root CA as `Secret/gdc-ca-bundle` at `/etc/gdc-certs/ca.crt` (`GDC_CA_BUNDLE="/etc/gdc-certs/ca.crt"`). `p15-job-manager` validates TLS certificates against this bundle whenever fetching JWKS keys over HTTPS.

### 2.2 Configuring Keycloak Realm, Dual OIDC Clients & Role Mappers

Create a dedicated realm **`gdc-jobs-realm`** in Keycloak with **two separate OIDC clients** so the `:8080` Portal and `:8081` PA Admin Console never share client credentials or redirect boundaries:

| Setting | Portal Client (`:8080`) | PA Admin Client (`:8081`) |
| :--- | :--- | :--- |
| **Client ID** | `p15-job-portal` | `p15-job-admin` |
| **Client Protocol / Access Type** | OpenID Connect (`public` with mandatory PKCE, or confidential behind OIDC gateway) | OpenID Connect (`public` with mandatory PKCE, or confidential behind OIDC gateway) |
| **Standard Flow & PKCE** | Enabled; **Proof Key for Code Exchange Code Challenge Method = `S256`** | Enabled; **Proof Key for Code Exchange Code Challenge Method = `S256`** |
| **Valid Redirect URIs** | `https://jobs.gdc.local/*` | `https://admin.jobs.gdc.local/*` |
| **Web Origins** | `https://jobs.gdc.local` | `https://admin.jobs.gdc.local` |
| **Token Signing Algorithm** | `RS256` *(strictly required — `HS256` and symmetric tokens are rejected)* | `RS256` |

**Mandatory Realm Roles & Protocol Mapper:**
1. Under **Realm Roles**, create the governance roles required by your tenants:
   - `pa-job-admin` (Platform Administrators — access to `:8080` across all namespaces and exclusive access to `:8081`).
   - `ao-job-operator-<namespace>` (for example, `ao-job-operator-platform-jobs` — read/write operator scoped strictly to that namespace on `:8080`).
   - `job-viewer-<namespace>` (for example, `job-viewer-platform-jobs` — read-only schedule, run, log, and finding viewer scoped strictly to that namespace on `:8080`).
2. Add a **Client Scope / Protocol Mapper** (`User Realm Role` or `Group Membership`) emitting assigned roles into `roles`, `realm_access.roles`, or `groups` inside the RS256 access/ID JWT, alongside standard `preferred_username` and `email` claims.

### 2.3 Wiring `p15-job-manager` to Keycloak (`ConfigMap` & Helm Values)

Configure the Keycloak issuer, in-cluster JWKS endpoint, dual client IDs, and hardened cookie settings in `ConfigMap/p15-job-manager-config` (or via Helm `--set` flags during Stage 5 deployment):

```yaml
# Excerpt from manifests/apps/configmaps.yaml (`p15-job-manager-config`)
ALLOW_SIMULATED_OIDC: "false"
COOKIE_SECURE: "true"
CORS_ALLOWED_ORIGINS: "https://jobs.gdc.local,https://admin.jobs.gdc.local"
OIDC_ISSUER: "https://keycloak.gdc.local/realms/gdc-jobs-realm"
OIDC_JWKS_URL: "http://keycloak.p12-keycloak.svc.cluster.local:80/realms/gdc-jobs-realm/protocol/openid-connect/certs"
OIDC_CLIENT_ID: "p15-job-portal"
OIDC_ADMIN_CLIENT_ID: "p15-job-admin"
GDC_CA_BUNDLE: "/etc/gdc-certs/ca.crt"
```

> **Rotate Session Signing Keys Before Production Cutover:** Replace the placeholder values in `Secret/p15-session-and-webhook-secrets` (`USER_COOKIE_SECRET`, `ADMIN_COOKIE_SECRET`, and `WEBHOOK_HMAC_SECRET`) with distinct 256-bit random secrets managed via Vault (`p11-vault`). Keeping `USER_COOKIE_SECRET != ADMIN_COOKIE_SECRET` cryptographically guarantees that a `:8080` Portal cookie can never verify on `:8081`.

### 2.4 Authentication (`AuthN`) Flows: CLI/CI vs. Browser Sessions

- **CLI & CI Automation (`Authorization: Bearer <JWT>`):** Obtain a short-lived RS256 token from Keycloak (`${OIDC_ISSUER}/protocol/openid-connect/token`) and attach it directly via `Authorization: Bearer ${OIDC_TOKEN}`. On every request, `p15-job-manager` verifies the `RS256` signature against cached JWKS keys (`OIDC_JWKS_URL`, refreshed every 5 minutes), validates `iss == OIDC_ISSUER` and `exp`, and derives the caller's `AuthPrincipal`. Bearer-authenticated API calls bypass browser CSRF checks while enforcing identical persona and namespace RBAC.
- **Browser Sessions (PKCE + Dual-Port Cookies + CSRF):**
  1. Call `GET /auth/oidc/login` on `:8080` (or `:8081`) to obtain the Keycloak `authorize_url` with an `S256` PKCE challenge bound to `p15-job-portal` (or `p15-job-admin`).
  2. After Keycloak returns the RS256 token (via your Gateway OIDC filter, frontend PKCE callback, or the Portal Sign-In box), exchange it at `POST /auth/oidc/session` (accepting either `Authorization: Bearer <RS256_JWT>` or JSON body `{"token": "<RS256_JWT>"}` behind authenticating reverse proxies) to mint a surface-bound `HttpOnly`, `Secure`, `SameSite=Lax` HMAC-signed cookie (`jobs_user_session` on `:8080`, `jobs_admin_session` on `:8081`) plus a session-scoped `csrf_token`. Inspect the active session via `GET /auth/me` and clear the surface cookie via `POST /auth/logout` (or the top-right **`Sign Out`** button).
  3. Every mutating cookie-authenticated call (`POST`, `PUT`, `PATCH`, `DELETE`) must carry `X-CSRF-Token` and originate from the same host or an entry in `CORS_ALLOWED_ORIGINS`.

### 2.5 Authorisation (`AuthZ`) Role Mapping & Verification

`p15-job-manager` maps Keycloak JWT role/group claims deterministically to persona and namespace boundaries (`p15_job_manager/security.py`):

| Keycloak Role / Group Claim | Persona | Authorised Namespaces | `:8080` Portal & REST API | `:8081` PA Admin Console |
| :--- | :--- | :--- | :--- | :--- |
| **`pa-job-admin`** | `PA` | `*` (all namespaces) | Full read/write; can register `PA` schedules & cast Four-Eyes peer approvals | **Full Access** (`overview`, `allowed-hosts`, `quotas`, `kill-switch`, `audit-export`) |
| **`ao-job-operator-<ns>`** *(or `ao-job-operator` for default ns)* | `AO` | `<ns>` only | Full schedule, run, backfill, log & sink read/write inside `<ns>` (`403` on other namespaces or `PA` schedules) | **`403 Forbidden`** |
| **`job-viewer-<ns>`** *(or `job-viewer` for default ns)* | `AO` (`read-only`) | `<ns>` only | `GET` schedules, runs, redacted logs & findings inside `<ns>` (`403` on all `POST`/`PUT`/`DELETE` mutations) | **`403 Forbidden`** |
| **No matching role claim** | *Rejected* | *None* | **`403 Forbidden`** (`Principal has no assigned GDC job roles`) | **`403 Forbidden`** |

**Verify Keycloak AuthN & AuthZ End-to-End:**

```bash
# 1. Confirm unauthenticated access is rejected (expect HTTP 401)
curl -sk -o /dev/null -w "%{http_code}\n" --cacert /etc/gdc/ca-bundle.crt \
  https://jobs.gdc.local/api/v1/schedules

# 2. Obtain a short-lived RS256 access token from Keycloak (e.g. AO operator account)
export AO_TOKEN="$(curl -s --cacert /etc/gdc/ca-bundle.crt \
  -X POST https://keycloak.gdc.local/realms/gdc-jobs-realm/protocol/openid-connect/token \
  -d 'grant_type=password' -d 'client_id=p15-job-portal' \
  -d "username=${AO_USER}" -d "password=${AO_PASS}" | jq -r '.access_token')"

# 3. Confirm AO token works on :8080 (expect 200) and is BLOCKED on :8081 (expect 403)
curl -s -o /dev/null -w "Portal (:8080): %{http_code}\n" --cacert /etc/gdc/ca-bundle.crt \
  -H "Authorization: Bearer ${AO_TOKEN}" https://jobs.gdc.local/api/v1/schedules
curl -s -o /dev/null -w "Admin  (:8081): %{http_code}\n" --cacert /etc/gdc/ca-bundle.crt \
  -H "Authorization: Bearer ${AO_TOKEN}" https://admin.jobs.gdc.local/admin/v1/overview

# 4. Exchange a verified RS256 token for a surface-bound browser session cookie + CSRF token
curl -s --cacert /etc/gdc/ca-bundle.crt -c /tmp/p15-session.cookies \
  -X POST https://jobs.gdc.local/auth/oidc/session \
  -H "Authorization: Bearer ${AO_TOKEN}" | jq '{authenticated, principal, persona, allowed_namespaces}'
```

---

## 3. Application Operator (`AO`) Day-2 Workflows (`:8080`)

### 3.1 Previewing & Registering a Schedule
Never guess how a cron expression behaves across Daylight Saving Time transitions or whether an interval violates namespace guardrails. Always preview first:

1. Open the **Job Portal (`:8080`)** and click **`+ Add New Job`** in the top-right bar (or open the **`Catalogue & Schedules`** tab).
2. Enter a unique **Job ID** (e.g., `ao-rollup-15m`), select **Persona** (`AO`), **Job Class** (`batch`, `monitor`, or `enforce`), and select a **Worker Mode** from the dropdown (`batch-watermarked-rollup`, `monitor-platform-hygiene`, `enforce-resource-policy`, `inventory-audit-report`, or `Custom mode...` — an inline helper shows the exact Python module backing each built-in mode).
3. Provide a 5-field cron expression (e.g., `*/15 * * * *`), an IANA timezone (`UTC` is strongly recommended for deterministic billing, ETL, and compliance rollups), and a **pinned Harbor image tag** from an allowlisted registry prefix.
4. Click **`1. Preview Next 5 Runs`** (`POST /api/v1/schedules/preview`). The portal displays the next five execution windows in both local time and canonical `UTC`, flagging DST spring-forward skips or autumn ambiguities in a warning banner.
5. Click **`2. Save & Register Job`** (`POST /api/v1/schedules`). The control plane persists the schedule in PostgreSQL (also supporting in-place pinned `worker_image` / `worker_mode` upgrades on re-registration), applies the compiled `CronWorkflow` or `CronJob` directly to the cluster when not GitOps-locked, and displays the compiled YAML.

**Hard Security Guardrails Enforced on Registration:**
- **No Mutable `:latest` Tags:** Images ending in `:latest` or omitting a tag/digest are rejected with `400 Bad Request`.
- **No Unapproved Registries or Arbitrary `PodSpec`s:** You cannot inject raw `podSpec`, `command`, `volumes`, `hostPath`, or privileged security contexts via `:8080`. All workers execute inside PA-approved templates (`gdc-standard-job-runner-v1`).
- **Minimum AO Frequency Guard:** AO schedules more frequent than `MIN_AO_CRON_INTERVAL_MINUTES` (default `5` minutes) are rejected to protect cluster API server and database capacity.

```bash
# Equivalent REST API schedule registration (using Keycloak OIDC Bearer JWT)
curl -s --cacert /etc/gdc/ca-bundle.crt \
  -X POST https://jobs.gdc.local/api/v1/schedules \
  -H "Authorization: Bearer ${OIDC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "ao-rollup-15m",
    "namespace": "platform-jobs",
    "persona": "AO",
    "job_class": "batch",
    "worker_mode": "batch-watermarked-rollup",
    "worker_image": "harbor.gdc.local/blueprint-images/p15-reference-worker:v1.0.4",
    "schedule_cron": "*/15 * * * *",
    "timezone": "UTC",
    "enforcement_mode": "audit"
  }'
```

### 3.2 Triggering Immediate Runs, Pausing/Resuming/Deleting Single Jobs & Running UTC Backfills
- **Immediate Trigger (`Run Now`):** Click **`Run Now`** next to any active schedule on the **Dashboard** or **`Catalogue & Schedules`** tab (or call `POST /api/v1/schedules/{job_id}/trigger`). The control plane dispatches a live Kubernetes `Job` (Profile B) or Argo `Workflow` (Profile A) and automatically reconciles its completion, redacted logs, and HITL findings every ~5 seconds. For sharded batch jobs, pass `{"shards": ["shard-00", "shard-01"]}` up to `MAX_SHARDS_PER_RUN` (default `50`).
- **Single-Job Pause, Resume & Delete:** Click **`Pause`** / **`Resume`** next to any individual job on the **Dashboard** or **`Catalogue & Schedules`** tab (or call `POST /api/v1/schedules/{job_id}/pause` and `.../resume`) to patch `spec.suspend` on that single schedule during maintenance without affecting other jobs. To remove an ad-hoc schedule cleanly from both PostgreSQL and Kubernetes (`?propagationPolicy=Background`), click red **`Delete`** in **`Catalogue & Schedules`** or call `DELETE /api/v1/schedules/{job_id}`.
- **Deterministic UTC Backfills:** When upstream data arrives late or a historical slice requires reprocessing, submit a UTC window range via `POST /api/v1/schedules/{job_id}/backfill`:
  ```bash
  curl -s --cacert /etc/gdc/ca-bundle.crt \
    -X POST https://jobs.gdc.local/api/v1/schedules/ao-rollup-15m/backfill \
    -H "Authorization: Bearer ${OIDC_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
      "window_start": "2026-11-26T08:00:00Z",
      "window_end": "2026-11-26T09:00:00Z",
      "step_seconds": 900
    }'
  ```
  Backfill runs slice `[window_start, window_end)` into idempotent `[start, end)` sub-windows and **never regress** the `(job_id, shard_key)` high-water mark stored in `platform_jobs.watermarks`.

### 3.3 Respecting the Anti-ClickOps GitOps Guard
By default, Pattern 15 operates in `GITOPS_MODE="direct-apply"` with automatic GitOps drift protection:
- **Ad-Hoc Schedules:** Schedules created directly via `:8080` can be paused, edited, or deleted through the UI/API.
- **GitOps-Managed Schedules:** Any schedule carrying **Argo CD** (`argocd.argoproj.io/tracking-id`) or **Flux** (`kustomize.toolkit.fluxcd.io/name`, `helm.toolkit.fluxcd.io/name`) annotations is automatically locked read-only in the control plane. Attempting to mutate it via UI/API blocks direct cluster writes and returns a ready-to-commit YAML snippet and GitLab Merge Request payload so changes go through Git review rather than creating silent cluster drift.

### 3.4 Inspecting Runs, Watermarks & Redacted Logs
Open the **`Run Explorer & Logs`** tab on `:8080` (or query `GET /api/v1/runs` and `GET /api/v1/schedules/{job_id}`):
- **Object Storage Artifact URI:** Every completed run records its archived bundle URI (`s3://p15-jobs-ledger/jobs/<ns>/<job>/<YYYY>/<MM>/<run>/result.json`).
- **Redacted Log Downloads:** Retrieve archived run logs via `GET /api/v1/runs/{run_id}/logs`. All logs pass through pre-archive secret redaction (`Bearer` tokens, `password=`, API keys, PEM blocks) and are served with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.
- **Standardised Exit Code Semantics:**
  - **`0` (`Succeeded`):** Completed cleanly; WAL archived and watermark advanced.
  - **`2` (`Non-Retryable Configuration Error`):** Halts retries immediately so bad parameters or missing schema fields do not burn cluster quota.
  - **Other Non-Zero Codes (`Transient Failure`):** Retried with exponential backoff up to `backoffLimit`; after `5` consecutive failures (`CONSECUTIVE_FAILURE_THRESHOLD`), the **Circuit Breaker** opens, suspends the schedule, and fires an `OnCircuitBreakerOpen` notification.

---

## 4. Onboarding Custom Jobs, Air-Gapped ImpEx, ServiceAccounts & Accessing Resources

Pattern 15 ships three customer-agnostic starter modes in `p15-reference-worker` (`batch-watermarked-rollup`, `monitor-platform-hygiene`, and `enforce-resource-policy`). To onboard your own domain workload (for example, database archival, sovereign compliance reporting, or AI dataset curation) so it runs identically across Shared and Standard clusters:

1. **Conform to the CLI Contract:** Accept `--mode`, `--job-id`, `--run-id`, `--window-start`, `--window-end`, `--shard-key`, and `--enforcement-mode`, and write a structured summary JSON to `/tmp/job-out/result.json`.
2. **Enforce Pod Security `Restricted`:** Build a multi-stage non-root container (`USER 65532:65532`) with a read-only root filesystem, writing ephemeral scratch files solely under `/tmp` or `/home/appuser`.
3. **Write WAL First to GDC Object Storage:** Persist redacted output artifacts to retention-locked GDC Object Storage (`https://objectstorage.gdc.goog` via S3 v4 with `AWS_CA_BUNDLE`) before updating relational tables so scheduled runs remain lossless across PostgreSQL failover windows.
4. **Return Accurate Exit Codes:** Exit `2` on deterministic configuration/validation failures and `1` on transient network or dependency errors.
5. **Pass Supply-Chain Gates Before Registration:** Scan the built image with Trivy (`0` `HIGH`/`CRITICAL` unmitigated CVEs, zero rogue `.pth` files), push with an immutable SemVer tag or SHA-256 digest to your internal Harbor repository, and register it under an allowlisted prefix approved by your `PA`.

### 4.1 End-to-End Code-to-Run Example: Writing, Uploading & Running a Custom Job (`ao-inventory-audit-15m`)

> **How Your Script Enters the Orchestrator (Zero Raw Code Upload Model):**
> In an air-gapped GDC-ag enclave, operators **never** upload raw `.py` files into the web UI or inject custom `PodSpec`s. Instead, your script enters the orchestrator strictly as an immutable, Trivy-scanned container image bound by reference:
> ```text
> [1. Python Script]         [2. Non-Root Container]             [3. Managed Harbor Registry]          [4. Orchestrator Portal (:8080)]
> p15_jobs/runner.py  --->   COPY p15_jobs ./p15_jobs     --->   docker push                           Register Pinned Worker Image +
> (--mode CLI contract)      ENTRYPOINT python3 -m p15_jobs      harbor.gdc.local/.../                 Worker Mode -> compiled into
>                            .runner (USER 65532:65532)          p15-example-inventory-job:v1.0.0      gdc-standard-job-runner-v1
> ```

Pattern 15 ships a complete, runnable custom worker template in [`examples/custom-job-inventory/`](../examples/custom-job-inventory/) implementing mode `inventory-audit-report`. This walkthrough takes you all the way from Python source code and hardened container packaging to Harbor registry upload, schedule registration, live Dashboard execution, and verified redacted output in GDC Object Storage.

#### Step 1: Project Layout & Custom Worker Source Code (`examples/custom-job-inventory/`)

Organise your custom job using the standard module layout expected by `gdc-standard-job-runner-v1` (`python3 -m p15_jobs.runner`):

```text
examples/custom-job-inventory/
├── Dockerfile              # Multi-stage, non-root (65532:65532), readOnlyRootFilesystem-safe
├── requirements.txt        # Pinned Python dependencies (0 HIGH/CRITICAL CVEs)
└── p15_jobs/
    ├── __init__.py
    └── runner.py           # CLI contract, WAL-first write, redaction & exit-code 2 guardrail
```

**Custom Worker Implementation (`examples/custom-job-inventory/p15_jobs/runner.py`):**

```python
import argparse, hashlib, json, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from common.redaction import redact_payload
from common.storage import DualModeStorageAdapter, build_job_artifact_key

DEFAULT_RESULT_PATH = Path("/tmp/job-out/result.json")
SUPPORTED_MODES = ("inventory-audit-report",)

def run_inventory_audit_job(mode, job_id, run_id, window_start="", window_end="",
                            shard_key="all", sink_uri="", enforcement_mode="audit",
                            result_path=DEFAULT_RESULT_PATH):
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported custom worker --mode {mode!r}")

    t0 = time.monotonic()
    now = datetime.now(timezone.utc)
    w_end = window_end.strip() or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    w_start = window_start.strip() or (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ns = os.getenv("NAMESPACE", "platform-jobs")
    store = DualModeStorageAdapter(bucket_name=sink_uri or os.getenv("BUCKET_NAME", "p15-jobs-ledger"))

    # Domain workload: in-cluster, query live namespace Services via the attached ServiceAccount token;
    # fall back cleanly to a local fixture when running outside Kubernetes for unit/smoke tests.
    live_assets = discover_live_k8s_services(ns)
    data_source = "kubernetes-api" if live_assets is not None else "local-fixture"
    inventory_slice = live_assets or [
        {"asset_id": f"{shard_key}-svc-payments",  "owner_label": "team-core", "tls_days_left": 142},
        {"asset_id": f"{shard_key}-svc-reporting", "owner_label": "team-data", "tls_days_left": 89},
        {"asset_id": f"{shard_key}-svc-legacy",    "owner_label": "",          "tls_days_left": 12},
    ]
    violations, compliant = [], 0
    for item in inventory_slice:
        if not item["owner_label"] or item["tls_days_left"] < 30:
            violations.append({
                "target_kind": "Service", "target_namespace": ns, "target_name": item["asset_id"],
                "rule_id": "CUSTOM-INV-001", "severity": "high" if item["tls_days_left"] < 30 else "medium",
                "missing_owner_label": not item["owner_label"], "tls_days_left": item["tls_days_left"],
            })
        else:
            compliant += 1

    # 1. Persist WAL bundle to GDC Object Storage FIRST (survives DBCluster HA failover or maintenance)
    slug = f"{w_end.replace(':', '').replace('-', '')}-{hashlib.sha256(f'{w_start}..{w_end}'.encode()).hexdigest()[:16]}"
    wal_doc = {
        "idempotency_key": f"{job_id}:{shard_key}:{w_start}:{w_end}",
        "job_id": job_id, "run_id": run_id, "mode": mode, "namespace": ns, "shard_key": shard_key,
        "inventory_items_audited": len(inventory_slice), "compliant_count": compliant,
        "non_compliant_count": len(violations),
        # Deliberate synthetic header to verify pre-archive secret redaction -> [REDACTED_TOKEN]
        "diagnostic_trace": "checked endpoint with Authorization: Bearer synthetic-demo-token-do-not-persist",
    }
    wal_uri = store.put_json(f"wal/inventory/{job_id}/{shard_key}/{slug}.json", wal_doc, redact=True)

    # 2. Write redacted canonical result.json to Object Storage and /tmp/job-out/result.json
    sanitized = redact_payload({
        "job_id": job_id, "run_id": run_id, "mode": mode, "status": "Succeeded",
        "namespace": ns, "shard_key": shard_key, "enforcement_mode": enforcement_mode,
        "window_start": w_start, "window_end": w_end, "items_processed": len(inventory_slice),
        "violations": violations, "actions_taken": [], "watermark_end": w_end, "wal_uri": wal_uri,
        "metrics": {
            "inventory_items_audited": len(inventory_slice), "compliant_count": compliant,
            "non_compliant_count": len(violations),
            "compliance_pct": round((compliant / len(inventory_slice)) * 100.0, 2),
            "duration_ms": round((time.monotonic() - t0) * 1000.0, 2),
        },
        "notes": wal_doc["diagnostic_trace"],
    })
    obj_key = build_job_artifact_key(ns, job_id, run_id, "result.json", ts=now)
    sanitized["artifact_uri"] = store.put_json(obj_key, sanitized, redact=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(sanitized, sort_keys=True, indent=2), encoding="utf-8")
    return sanitized

def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    for flag in ("--mode", "--job-id", "--run-id"): p.add_argument(flag, required=True)
    for flag, default in (("--window-start", ""), ("--window-end", ""), ("--shard-key", "all"),
                          ("--sink-uri", ""), ("--enforcement-mode", "audit"),
                          ("--output-file", str(DEFAULT_RESULT_PATH))):
        p.add_argument(flag, default=default)
    try:
        a = p.parse_args(argv)
        res = run_inventory_audit_job(a.mode, a.job_id, a.run_id, a.window_start, a.window_end,
                                      a.shard_key, a.sink_uri, a.enforcement_mode, Path(a.output_file))
        print(json.dumps({"status": res["status"], "artifact_uri": res["artifact_uri"],
                          "wal_uri": res["wal_uri"], "metrics": res["metrics"]}))
        return 0
    except ValueError as exc:
        # Exit code 2 tells Argo / Kubernetes podFailurePolicy NOT to retry a bad config
        sys.stderr.write(f"Configuration error (non-retryable): {exc}\n")
        return 2
```

**Pinned Air-Gapped Dependencies (`examples/custom-job-inventory/requirements.txt`) & Hardened Non-Root `Dockerfile`:**

```text
boto3==1.37.1
cryptography==50.0.0
urllib3==2.8.0
```

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get dist-upgrade -y && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY examples/custom-job-inventory/requirements.txt ./
RUN pip install --no-cache-dir --upgrade "pip>=25.1" "setuptools>=78.1.1" "wheel>=0.45.1" && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get dist-upgrade -y && apt-get install -y --no-install-recommends ca-certificates && \
    (pip uninstall -y setuptools wheel || true) && \
    rm -rf /usr/local/lib/python3.11/ensurepip /usr/local/lib/python3.11/site-packages/pip* \
           /usr/local/lib/python3.11/site-packages/setuptools* /usr/local/lib/python3.11/site-packages/wheel* \
           /var/lib/apt/lists/* && \
    groupadd -g 65532 nonroot && useradd -u 65532 -g 65532 -d /home/appuser -m -s /usr/sbin/nologin nonroot

COPY --from=builder /install /usr/local
COPY example-app/common ./common
COPY examples/custom-job-inventory/p15_jobs ./p15_jobs

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app HOME=/home/appuser
RUN python3 -c "import boto3, cryptography, p15_jobs.runner; print('CUSTOM_WORKER_IMPORTS_OK')"
USER 65532:65532
ENTRYPOINT ["python3", "-m", "p15_jobs.runner"]
```

**Local Smoke Test (Verify Exit Code `0` Redaction & Exit Code `2` Guardrail):**

```bash
# 1. Verify happy path writes redacted result.json locally
PYTHONPATH=p15-job-orchestrator/examples/custom-job-inventory:p15-job-orchestrator/example-app \
  python3 -m p15_jobs.runner \
    --mode inventory-audit-report --job-id ao-inventory-audit-15m --run-id local-smoke-01 \
    --shard-key shard-00 --output-file /tmp/job-out/result.json
grep -q '\[REDACTED_TOKEN\]' /tmp/job-out/result.json && echo "REDACTION_VERIFIED"

# 2. Verify invalid --mode returns exit code 2 (stops futile pod retries)
PYTHONPATH=p15-job-orchestrator/examples/custom-job-inventory:p15-job-orchestrator/example-app \
  python3 -m p15_jobs.runner --mode invalid-mode --job-id ao-inventory-audit-15m --run-id local-smoke-02; echo "Exit code: $?"
```

#### Step 2: Build, Vulnerability-Scan & Upload to Air-Gapped Managed Harbor

Build from the `p15-job-orchestrator/` root so `example-app/common` is copied cleanly, verify zero `HIGH`/`CRITICAL` CVEs, and upload the immutable SemVer tag to your allowlisted Harbor repository:

```bash
docker build --platform linux/amd64 \
  -f p15-job-orchestrator/examples/custom-job-inventory/Dockerfile \
  -t harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0 \
  p15-job-orchestrator

# Mandatory supply-chain gate before uploading to Managed Harbor
trivy image --severity HIGH,CRITICAL --ignore-unfixed \
  harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0

# Push directly inside the enclave (or `docker save` -> high-side transfer -> `docker load` + push)
docker push harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0
```

#### Step 3: Register the Uploaded Job in the Portal (`:8080`) or REST API

1. In the **Job Portal (`:8080`)**, click **`+ Add New Job`** in the top-right bar.
2. Fill the labelled schedule fields:
   - **Job ID:** `ao-inventory-audit-15m`
   - **Persona:** `AO (Application Operator)` | **Job Class:** `batch`
   - **Worker Mode:** `inventory-audit-report`
   - **5-Field Cron Expression:** `*/15 * * * *` | **IANA Timezone:** `UTC` *(test `Europe/London` first with **`1. Preview Next 5 Runs`** to see DST warnings, then switch back to `UTC`)*
   - **Pinned Worker Image:** `harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0`
   - **Enforcement Ladder Mode:** `audit (default)`
3. Click **`2. Save & Register Job`**. Equivalent REST API call:
   ```bash
   curl -s --cacert /etc/gdc/ca-bundle.crt \
     -X POST https://jobs.gdc.local/api/v1/schedules \
     -H "Authorization: Bearer ${OIDC_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{
       "job_id": "ao-inventory-audit-15m",
       "namespace": "platform-jobs",
       "persona": "AO",
       "job_class": "batch",
       "worker_mode": "inventory-audit-report",
       "worker_image": "harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0",
       "schedule_cron": "*/15 * * * *",
       "timezone": "UTC",
       "enforcement_mode": "audit"
     }'
   ```
   `p15-job-manager` validates the Harbor prefix and pinned tag, persists the definition in PostgreSQL, and displays the compiled declarative manifest (Profile A `CronWorkflow` or Profile B `CronJob`) in `.reconcile.manifest_yaml`:
   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: CronWorkflow
   metadata:
     name: ao-inventory-audit-15m
     namespace: platform-jobs
   spec:
     schedule: "*/15 * * * *"
     timezone: UTC
     concurrencyPolicy: Forbid
     workflowSpec:
       serviceAccountName: p15-ao-worker-sa
       priorityClassName: p15-batch-low
       arguments:
         parameters:
           - name: worker_image
             value: harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0
           - name: mode
             value: inventory-audit-report
   ```

#### Step 4: Trigger & Watch Live Execution on the Dashboard

Commit `.reconcile.manifest_yaml` to your GitOps repository (**Argo CD** or **Flux**) for recurring production execution, or click **`Run Now`** on the `ao-inventory-audit-15m` row (equivalent to `POST /api/v1/schedules/ao-inventory-audit-15m/trigger` with `{"shards": ["shard-00"]}`).

Clicking **`Run Now`** switches straight to the **Dashboard**, where you can monitor the workload in real time:
- **`Running Now`** increments to **`1`**, a blue animated **`● LIVE JOB RUNNING`** banner lights up with the Job ID, Run ID, and compiled engine reference (`Workflow/...` or `Job/...`), and Row #1 of **`Live Job Execution & Recent Runs`** displays a pulsing **`● Running`** status bar.
- Once the container exits `0`, the Dashboard updates in-place: the banner flips green (**`✓ LATEST JOB SUCCEEDED`**), Row #1 switches to **`✓ Succeeded`** with inline metrics (**`Audited: 3 • Compliant: 2 • Findings: 1 • 66.67% • exit=0`**) and the `s3://` artifact URI, and **`Latest Job Result (result.json)`** populates immediately on the Dashboard.

#### Step 5: Inspect Archived `result.json`, WAL & Redacted Logs

Click **`Inspect Output`** on the Dashboard row (or open **`Run Explorer & Logs`** / query `GET /api/v1/runs/{run_id}/logs`) to inspect the side-by-side structured result and archived redacted log. The resulting `result.json` stored at `s3://p15-jobs-ledger/jobs/platform-jobs/ao-inventory-audit-15m/<YYYY>/<MM>/<run_id>/result.json` confirms both the audit metrics and pre-archive secret scrubbing:

```json
{
  "job_id": "ao-inventory-audit-15m",
  "mode": "inventory-audit-report",
  "status": "Succeeded",
  "shard_key": "shard-00",
  "wal_uri": "s3://p15-jobs-ledger/wal/inventory/ao-inventory-audit-15m/shard-00/20261126T190000Z-a1b2c3d4e5f60718.json",
  "metrics": {
    "inventory_items_audited": 3,
    "compliant_count": 2,
    "non_compliant_count": 1,
    "compliance_pct": 66.67
  },
  "violations": [
    {
      "target_kind": "Service",
      "target_name": "shard-00-svc-legacy",
      "rule_id": "CUSTOM-INV-001",
      "severity": "high",
      "missing_owner_label": true,
      "tls_days_left": 12
    }
  ],
  "notes": "checked endpoint with Authorization: Bearer [REDACTED_TOKEN]"
}
```

---

### 4.2 Air-Gapped ImpEx (Import / Export) Guide: Crossing the Physical Air Gap

Inside a disconnected GDC-ag enclave, worker pods and cluster nodes have **zero internet egress** and can pull images solely from your internal **Managed Harbor (`harbor.gdc.local`)**. Moving either the full Pattern 15 platform or a Day-2 custom job container across the physical air-gap boundary follows a two-sided **ImpEx (Export $\rightarrow$ Verify & Scan $\rightarrow$ Physical/Diode Transfer $\rightarrow$ High-Side Import)** workflow.

#### A. Initial Platform Bundle ImpEx (`package-for-gdc.sh` $\rightarrow$ `unpack-for-gdc.sh`)

1. **Low-Side Export (Connected Build Workstation):**
   Run the Pattern 15 packaging script. It fails closed if any non-production registry or simulated OIDC flag exists in `manifests/gdc/` or `manifests/apps/`, bundles all manifests, Helm charts, and images, and writes a **SHA-256 Bill of Materials (`p15-job-orchestrator-BOM.txt`)**:
   ```bash
   # 1. Verify unit tests, OPA policies, Helm lint & Trivy fs before packaging
   ./p15-job-orchestrator/test/verify.sh

   # 2. Export production archives + SHA-256 BOM into packages/p15-job-orchestrator/
   ./p15-job-orchestrator/scripts/package-for-gdc.sh
   ls -lh packages/p15-job-orchestrator/
   ```
   Transfer `p15-job-orchestrator-gdc-manifests.tar.gz`, `p15-job-orchestrator-gdc-images.tar`, any `offline-images/*.tar*` third-party Argo archives listed in `external_images.txt`, `p15-job-orchestrator-BOM.txt`, and your Trivy scan reports across your approved air-gap transfer mechanism (encrypted media, clean-room staging station, or one-way data diode per site SOP).

2. **High-Side Import (Air-Gapped GDC-ag Bastion):**
   Verify archive integrity against the BOM before loading anything into Docker or Managed Harbor, then unpack and push:
   ```bash
   # 1. Verify SHA-256 integrity of every transferred tarball
   sha256sum -c packages/p15-job-orchestrator/p15-job-orchestrator-BOM.txt --ignore-missing

   # 2. Authenticate to internal GDC Managed Harbor
   docker login harbor.gdc.local

   # 3. Unpack production manifests (auto-strips non-GDC overlays) & push all images to Harbor
   ./p15-job-orchestrator/scripts/unpack-for-gdc.sh \
     --bundle-dir ./packages/p15-job-orchestrator \
     --output-dir ./p15-job-orchestrator-prod \
     --registry harbor.gdc.local/blueprint-images
   ```

#### B. Day-2 Custom Job Image ImpEx (Moving Your Own Job Scripts Across the Air Gap)

When an `AO` team builds a new custom job (or releases `v1.0.1` of `p15-example-inventory-job`) on a low-side build environment, package and import it as an immutable OCI tarball:

1. **Low-Side Build, Scan & Export:**
   ```bash
   export IMG="harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0"

   # 1. Build reproducible linux/amd64 non-root container
   docker build --platform linux/amd64 \
     -f p15-job-orchestrator/examples/custom-job-inventory/Dockerfile \
     -t "${IMG}" p15-job-orchestrator

   # 2. Mandatory supply-chain gate: 0 HIGH/CRITICAL CVEs + SBOM/report for high-side review
   trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "${IMG}"
   trivy image --format json -o p15-example-inventory-job-v1.0.0-trivy.json "${IMG}"

   # 3. Export compressed OCI tarball + SHA-256 checksum for ImpEx transfer
   docker save "${IMG}" | gzip > p15-example-inventory-job-v1.0.0.tar.gz
   sha256sum p15-example-inventory-job-v1.0.0.tar.gz > p15-example-inventory-job-v1.0.0.tar.gz.sha256
   ```
   Move `p15-example-inventory-job-v1.0.0.tar.gz`, `.sha256`, and `-trivy.json` through your ImpEx inspection gate into the high-side enclave.

2. **High-Side Verification, Load & Harbor Push:**
   ```bash
   # 1. Verify checksum after ImpEx transfer
   sha256sum -c p15-example-inventory-job-v1.0.0.tar.gz.sha256

   # 2. Load into high-side Docker daemon (or use `skopeo copy docker-archive:... docker://...`)
   docker load -i p15-example-inventory-job-v1.0.0.tar.gz

   # 3. Push immutable tag into allowlisted Managed Harbor project
   docker login harbor.gdc.local
   docker push harbor.gdc.local/blueprint-images/p15-example-inventory-job:v1.0.0
   ```
   Once pushed, verify the image tag appears in Managed Harbor (and optionally record its `@sha256:...` digest) before registering it in the `:8080` Job Portal.

---

### 4.3 How Jobs Get a ServiceAccount Attached (`RBAC` & Stage 2 IAM)

To prevent privilege escalation, **`p15-job-manager` strictly forbids callers from passing `serviceAccountName` in `:8080` API requests** (`400 Bad Request`, `REQ-SEC-005`). An `AO` can never attach `p15-job-manager-sa` or an elevated platform identity to a worker pod. Instead, Kubernetes ServiceAccounts are attached deterministically by the control plane or via PA-approved GitOps templates:

#### 1. Default Automatic ServiceAccount Attachment

When you register a job against the default `gdc-standard-job-runner-v1` template, `DualProfileEngineCompiler` automatically binds one of two least-privilege worker ServiceAccounts defined in `manifests/apps/rbac.yaml`:

| Engine Profile & Persona | Attached Kubernetes `ServiceAccount` | Bound RBAC (`manifests/apps/rbac.yaml`) | Permitted & Denied Access |
| :--- | :--- | :--- | :--- |
| **Profile B (`k8s-native`) — `AO` or `PA`**<br>**Profile A (`argo`) — `AO`** | **`p15-ao-worker-sa`** | Namespace-scoped `Role/p15-ao-worker-role` | **Allowed:** `get/list/watch` on `pods`, `services`, `events`, `resourcequotas`, `limitranges`, `deployments`, `statefulsets`, `jobs`, `cronjobs` inside the job's own namespace (plus `workflowtaskresults` create/patch).<br>**Denied:** Zero `Secret` reads, zero `ConfigMap` API reads, zero `pods/exec`, zero writes to workloads, zero cross-namespace access. |
| **Profile A (`argo`) — `PA`** | **`p15-pa-watcher-sa`** | Metadata-only `ClusterRole/p15-pa-metadata-watcher-role` | **Allowed:** Cluster-wide `get/list/watch` on `namespaces`, `nodes`, `pods`, `services`, `deployments`, `statefulsets`, `daemonsets`, `jobs`, `cronjobs`, `workflows`, `pvcs`, `resourcequotas`.<br>**Denied:** Zero `Secret` reads, zero `ConfigMap` reads, zero `pods/exec`, zero cluster mutations. |
| **Stage 2 GDC Object Storage (`Bucket`)** | **`ProjectServiceAccount/p15-jobs-sa`** *(GDC Global API)* | `IAMRoleBinding` $\rightarrow$ `project-bucket-object-admin` (`manifests/gdc/iam/permissions.yaml`) | Grants object read/write on the 400-day retention-locked `p15-jobs-ledger` bucket; its S3 HMAC keys are projected into `Secret/p15-s3-credentials` and injected into workers via `envFrom`. |

#### 2. Attaching a Dedicated Least-Privilege ServiceAccount to a Custom Tenant Job

When a custom workload requires permissions beyond `p15-ao-worker-sa` (for example, reading a dedicated application `Secret`, watching a tenant CRD, or authenticating to a separate Stage 2 `ProjectServiceAccount`), follow this **PA-governed onboarding pattern**:

1. **Declare the Dedicated `ServiceAccount` & Narrow `Role` in Your Namespace (GitOps):**
   Scope `Secret` or `ConfigMap` reads strictly with `resourceNames:` — never grant wildcard `secrets` access:
   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: ao-billing-worker-sa
     namespace: platform-jobs
   automountServiceAccountToken: true
   ---
   apiVersion: rbac.authorization.k8s.io/v1
   kind: Role
   metadata:
     name: ao-billing-worker-role
     namespace: platform-jobs
   rules:
     - apiGroups: [""]
       resources: ["services", "configmaps"]
       verbs: ["get", "list"]
     - apiGroups: [""]
       resources: ["secrets"]
       resourceNames: ["billing-db-credentials"] # Scoped to one named Secret only
       verbs: ["get"]
   ---
   apiVersion: rbac.authorization.k8s.io/v1
   kind: RoleBinding
   metadata:
     name: ao-billing-worker-rb
     namespace: platform-jobs
   roleRef:
     apiGroup: rbac.authorization.k8s.io
     kind: Role
     name: ao-billing-worker-role
   subjects:
     - kind: ServiceAccount
       name: ao-billing-worker-sa
       namespace: platform-jobs
   ```
2. **Bind the `ServiceAccount` via an Approved Template (Profile A) or GitOps Manifest (Profile B):**
   - **Profile A (`argo`):** Have your `PA` review and deploy a dedicated `WorkflowTemplate` (or `ClusterWorkflowTemplate`) setting `spec.serviceAccountName: ao-billing-worker-sa` and mounting only the required `Secret`/`ConfigMap`, then append that template name to `APPROVED_TEMPLATES` in `ConfigMap/p15-job-manager-config`. The `AO` then registers jobs with `"template_name": "ao-billing-runner-v1"`.
   - **Profile B (`k8s-native`):** Commit a GitOps-managed `CronJob` carrying **Argo CD** (`argocd.argoproj.io/tracking-id`) or **Flux** (`kustomize.toolkit.fluxcd.io/name`) annotations with `spec.jobTemplate.spec.template.spec.serviceAccountName: ao-billing-worker-sa`. Pattern 15 tracks and observes the schedule in read-only GitOps-protected mode.
3. **Pair Identity with Network Reachability:** Attaching a `ServiceAccount` grants *API/IAM authorisation*, not network egress. If the job must reach a database, internal API, or cross-project service, ensure both Stage 5 `NetworkPolicy` (`manifests/apps/network-policy.yaml`) and Stage 2 `ProjectNetworkPolicy` (`manifests/gdc/network/pnp-cross-project.yaml`) explicitly allow the destination port/project.

---

### 4.4 Examples: How a Custom Job Accesses Cluster & GDC Resources

Every worker runs with `readOnlyRootFilesystem: true`, `USER 65532:65532`, `/tmp` as scratch storage, and the enclave CA mounted at `/etc/gdc-certs/ca.crt`. Use the four patterns below inside your `p15_jobs/runner.py` to access cluster and GDC-ag managed resources safely:

#### Pattern 1: Reading Kubernetes API Resources via the Attached `ServiceAccount` Token

Because `p15-ao-worker-sa` sets `automountServiceAccountToken: true`, Kubernetes mounts a short-lived bound JWT at `/var/run/secrets/kubernetes.io/serviceaccount/token` and the cluster CA at `.../ca.crt`. The runnable example in [`examples/custom-job-inventory/p15_jobs/runner.py`](../examples/custom-job-inventory/p15_jobs/runner.py) uses this exact stdlib snippet (zero extra dependencies) to list and audit live `Service` resources in its namespace:

```python
import json, os, ssl, urllib.request
from pathlib import Path

def list_namespace_services(namespace: str) -> list[dict]:
    token = Path("/var/run/secrets/kubernetes.io/serviceaccount/token").read_text().strip()
    ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    url = f"https://{host}:{port}/api/v1/namespaces/{namespace}/services"

    ctx = ssl.create_default_context(cafile=ca_path)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items", [])
```

#### Pattern 2: Reading & Writing GDC Object Storage (`s3://` Bucket)

Workers inherit `S3_ENDPOINT="https://objectstorage.gdc.goog"`, `BUCKET_NAME`, `AWS_CA_BUNDLE="/etc/gdc-certs/ca.crt"`, and `Secret/p15-s3-credentials` (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) via `envFrom`. Always use the shared `DualModeStorageAdapter` so S3 v4 signing, TLS verification against the GDC CA, and automatic secret redaction happen consistently:

```python
from common.storage import DualModeStorageAdapter

store = DualModeStorageAdapter()  # Reads S3_ENDPOINT, BUCKET_NAME & AWS_CA_BUNDLE from env
input_keys = store.list_keys("inputs/platform-jobs/2026/11/")
raw_batch = store.get_text(input_keys[0])

# Persist redacted WAL & summary artifacts
wal_uri = store.put_json("wal/my-job/shard-00/slice-01.json", {"rows": 420}, redact=True)
```

#### Pattern 3: Querying GDC Managed PostgreSQL (`DBCluster`) with TLS `verify-ca`

When a job processes records in a GDC managed `DBCluster`, project `Secret/p15-db-credentials` (or your tenant DB secret) via `envFrom` and mount `Secret/dbs-certificates` at `/etc/db-tls/ca.crt`. Always strip any trailing `:5432` from `DBCluster` `.status.primary.url` and enforce `sslmode="verify-ca"` plus bounded timeouts:

```python
import os, psycopg2

raw_host = os.environ["DB_HOST"]
host, _, port_str = raw_host.partition(":")
conn = psycopg2.connect(
    host=host,
    port=int(port_str or os.getenv("DB_PORT", "5432")),
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    sslmode="verify-ca",
    sslrootcert=os.getenv("DB_SSLROOTCERT", "/etc/db-tls/ca.crt"),
    connect_timeout=5,
    options="-c statement_timeout=30000",
)
with conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM tenant_records WHERE updated_at >= %s;", (window_start,))
    row_count = cur.fetchone()[0]
```

#### Pattern 4: Calling Internal Enclave Services & Reading ConfigMaps / Scoped Secrets

- **Internal HTTPS Services:** Verify server certificates against `/etc/gdc-certs/ca.crt` (`ssl.create_default_context(cafile=os.getenv("GDC_CA_BUNDLE", "/etc/gdc-certs/ca.crt"))` or `httpx.Client(verify=os.getenv("GDC_CA_BUNDLE"), trust_env=False)`) and verify the destination namespace/port is permitted in `NetworkPolicy` and Stage 2 `ProjectNetworkPolicy`.
- **Non-Sensitive Parameters (`ConfigMap`):** Inject job configuration via `envFrom: [{configMapRef: {name: my-job-config}}]` inside your PA-approved `WorkflowTemplate` or GitOps `CronJob` and read via `os.getenv(...)`.
- **Tenant Credentials (`Secret` / Vault `p11-vault`):** Mount secrets read-only at `/etc/job-secrets/` (or via Vault Agent Injector annotations) rather than embedding credentials in CLI arguments or schedule parameters, and pass all diagnostic logs through `redact_secrets()` before writing to stdout or Object Storage.

---

## 5. Platform Administrator (`PA`) Governance & Bounded Self-Healing

### 5.1 Operating the 3-Tier Enforcement Ladder (`audit` -> `hitl-approval` -> `auto-remediate`)
Autonomous remediation without guardrails turns minor configuration drift into platform-wide outages. Always progress workloads deliberately through the three enforcement tiers:

1. **`audit` *(Mandatory Default)*:** Evaluates rules and records findings in `platform_jobs.enforcement_findings` without modifying any Kubernetes resource. Use `audit` for at least one full business cycle to verify rule precision before requesting mutations.
2. **`hitl-approval` *(Four-Eyes + Cryptographic TOCTOU)*:** Archives a pre-action JSON snapshot of the target object to Object Storage, computes `SHA-256(planned_patch + target_resourceVersion)`, and parks the finding in **`Enforcement & HITL Queue`** (`status: pending_approval`).
   - **Four-Eyes Rule (`REQUIRE_FOUR_EYES_APPROVAL="true"`):** The operator who triggered or owns the finding cannot self-approve it (`403 Forbidden`). A second distinct `PA` identity must review the SHA-256 digest and submit the decision (`POST /api/v1/approvals/{finding_id}/decide`).
   - **TOCTOU Protection (`409 Conflict`):** Before applying the approved patch, `p15-job-manager` re-verifies the target resource's live `resourceVersion`. If another operator or GitOps controller modified the target while approval was pending, the patch aborts safely with `409 Conflict` rather than overwriting newer state. Re-run the audit to generate a fresh plan.
   - **1-Click Snapshot Rollback:** If an approved patch causes unexpected impact, call `POST /api/v1/approvals/{finding_id}/rollback` to restore the pre-action Object Storage snapshot immediately.
3. **`auto-remediate` *(Strictly Bounded Opt-In)*:** Permitted only for low-risk, idempotent housekeeping (such as applying missing cost/owner labels or cleaning up expired sandbox resources). Every run enforces:
   - **Blast-Radius Cap (`maxActionsPerRun`, default `5`):** Excess findings are automatically escalated to `pending_approval` instead of executed.
   - **Per-Resource Cooldown (`cooldownSeconds`, default `3600s`):** Prevents rapid repeated patching of the same target.
   - **GitOps Tug-of-War Circuit Breaker:** If a remediated target reverts within `< 1` hour (indicating Argo CD or Flux is fighting the enforcer), the control plane immediately downgrades the schedule back to `audit` and opens its circuit breaker.

### 5.2 PA Platform Admin Console (`:8081`) Governance
Log into `https://admin.jobs.gdc.local` (`:8081`) with a `pa-job-admin` account to manage enclave-wide controls:
- **Platform Governance Overview (`GET /admin/v1/overview`):** Audits active `engine_mode`, `gitops_mode`, `emergency_pause_all` status, allowlisted registries, and allowlisted notification hosts.
- **SSRF Host Allowlist (`PUT /admin/v1/allowed-hosts`):** Explicitly allowlists internal FQDNs (for example, internal SMTP relays, enterprise chat webhooks, or ITSM bridges) before any `AO` can register a sink pointing to them. Private/link-local/loopback IP literals and DNS rebinding targets are blocked unconditionally.
- **Global Emergency Pause-All Kill-Switch (`POST /admin/v1/kill-switch`):** Immediately halts all new job triggers across every namespace during security incidents, storage pressure, or appliance maintenance. Click **`Toggle Emergency Pause-All`** on `:8081` or call:
  ```bash
  # Engage emergency pause-all (blocks all new :8080 triggers with HTTP 400)
  curl -s --cacert /etc/gdc/ca-bundle.crt \
    -X POST https://admin.jobs.gdc.local/admin/v1/kill-switch \
    -H "Authorization: Bearer ${PA_OIDC_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"paused": true}'
  ```

---

## 6. Configuring Air-Gapped Notifications & Auditing the Outbox

Because GDC-ag has no internet egress to SaaS paging services, notifications follow a **Dual-Path Air-Gapped Delivery Model** (detailed end-to-end in [`docs/notification-integrations.md`](./notification-integrations.md)):
- **Path A (Infrastructure & SLA Alerts):** Prometheus metrics scraped from `Service/p15-job-metrics` (`:9091`) evaluate against `MonitoringRule`s and route via GDC `ObservabilityPipeline` and Alertmanager `alertmanager.yml`.
- **Path B (Rich Job-Lifecycle Events):** `p15-job-manager` writes lifecycle events (`OnFailure`, `OnRecovery`, `OnSLAExceeded`, `OnApprovalRequired`, `OnCircuitBreakerOpen`) into a PostgreSQL **Transactional Outbox** (`platform_jobs.notification_outbox`), dispatched by the `Lease`-elected leader replica with exponential backoff and **HMAC-SHA256 signing** (`X-P15-Signature-256`).

### Registering & Verifying a Namespace Sink
1. Confirm your `PA` has added the destination FQDN to `ALLOWED_NOTIFICATION_HOSTS` on `:8081`.
2. Open the **`Notifications & Outbox`** tab on `:8080`, enter a **Sink Name**, select the vendor-neutral **Sink Type** (`generic-webhook`, `smtp-relay`, `chat-webhook`, `itsm-webhook` — where ServiceNow is one illustrative ITSM example, not a mandatory dependency — or `portal-feed`), and enter the internal `https://` target URL.
3. Click **`1. Register Sink`** (`POST /api/v1/notifications/sinks`). Sink definitions persist across all HA `p15-job-manager` replicas in `platform_jobs.notification_sinks` (storing only `*_env` references, never raw secrets), and webhook sinks automatically default to `WEBHOOK_HMAC_SECRET` from `Secret/p15-session-and-webhook-secrets` when no explicit `hmac_secret_env` is passed.
4. Click **`2. Send Test Notification`** (`POST /api/v1/notifications/sinks/{name}/test`) and confirm the green banner reports `HTTP 200` signed delivery and a **`delivered`** `OnSinkTest` row appears immediately in the **Transactional Notification Outbox Ledger** (`GET /api/v1/notifications/outbox`). If the downstream endpoint rejects or fails delivery (e.g., `HTTP 401` HMAC mismatch or connection failure), the control plane returns `HTTP 502` with the diagnostic detail.
5. **Noise Suppression:** Identical `(job_id, event_type, error_signature)` alerts within `DEDUP_WINDOW_SECONDS` (`900s` / 15 minutes) are collapsed (`status: deduplicated`), and non-critical alerts respect `QUIET_HOURS_UTC` (`status: suppressed_quiet_hours`). Permanently failing sinks transition to `dead_letter` after retry exhaustion and increment `gdc_job_notification_dead_letter_total`.

---

## 7. Failover Behaviour & Troubleshooting Reference

### 7.1 What Happens During a PostgreSQL `DBCluster` Failover or Maintenance Window?
On GDC-ag `v1.16.2+` (using the RaaS HA implementation, `dbcluster.dbadmin.goog/raasEnabled: "true"`), a PostgreSQL `DBCluster` with **high availability explicitly enabled** (`spec.availability.enableHighAvailability: true` / `--availability-type=zonal_ha`, which defaults to `false`/`zonal`) has **automatic failover enabled by default** (`spec.availability.enableAutoFailover: true`; see [Configure high availability](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/application/ao-user/db-configure-ha#about-high-availability)). Automatic failover **triggers** after 3 consecutive health check failures on the primary instance spaced 30 seconds apart (`~90s` detection), followed by taking the primary offline, promoting the same-zone standby replica, and rerouting application traffic (total end-to-end RTO is typically `~2+ minutes`, not `~90s`). Existing legacy HA clusters upgraded from pre-`1.15.1` must disable and re-enable HA to migrate to RaaS, and operators can also trigger a manual switchover at any time (`gdcloud database clusters failover` or `fleet.dbadmin.gdc.goog/v1` `Failover`). During an unplanned automatic failover or a planned maintenance window, active client connections are dropped and applications must reconnect cleanly:
- **Scheduled Jobs Keep Running:** Both Argo `CronWorkflow`s and Profile B `CronJob`s trigger from Kubernetes `etcd`, independent of PostgreSQL.
- **Zero Lost Slices:** Workers persist their redacted `result.json` and WAL bundle to 400-day retention-locked Object Storage first.
- **Automatic Catch-Up:** `p15-job-manager` marks `/readyz` `503` while the primary is unreachable, recycles stale TCP sockets within `< 15s` via `SELECT 1` `pool_pre_ping` + TCP keepalives once the new primary is promoted, and replays unindexed WAL bundles idempotently (`ON CONFLICT DO UPDATE`).

### 7.2 Quick Troubleshooting Table

| Symptom / HTTP Status | Likely Root Cause | Resolution |
| :--- | :--- | :--- |
| **`400 Bad Request` on `POST /api/v1/schedules`** | Image uses `:latest`, registry prefix is not in `ALLOWED_REGISTRY_PREFIXES`, raw `podSpec` was supplied, cron interval is `< 5m` for an `AO`, or Global Emergency Kill-Switch is active. | Pin an immutable SemVer tag/digest from an approved Harbor prefix, use template `gdc-standard-job-runner-v1`, check interval >= `5m`, or ask `PA` to inspect `/admin/v1/overview`. |
| **`400 Bad Request` on `POST /api/v1/notifications/sinks`** | Destination host is not in PA `ALLOWED_NOTIFICATION_HOSTS`, uses plaintext `http://` in production, or resolves to a blocked loopback/link-local/RFC1918 metadata IP (`SSRF` guard). | Ask `PA` to allowlist the internal FQDN on `:8081` (`PUT /admin/v1/allowed-hosts`) and use `https://` with internal CA trust. |
| **`401` / `403` on `:8081` Admin Console** | Signed in with an `AO` role (`ao-job-operator-*`) or presenting a `:8080` `jobs_user_session` cookie. | Authenticate directly on `:8081` with a `pa-job-admin` Keycloak identity (`jobs_admin_session`). |
| **`403 Forbidden` on HITL Approval** | Four-Eyes dual control blocked self-approval (`approver == requester`). | Have a second distinct `PA` operator review the patch SHA-256 and approve the finding. |
| **`409 Conflict` on HITL Approval (or GitOps Read-Only Export on Schedule Edit)** | Either the target KRM object's `resourceVersion` changed since planning (`TOCTOU` conflict), or the schedule carries Argo CD / Flux GitOps management annotations. | For `TOCTOU`, re-run the enforcement audit to generate a fresh plan against the current `resourceVersion`. For GitOps-managed schedules, commit the exported YAML change via GitLab Merge Request. |
| **Schedule State Shows `Circuit-Open`** | Job hit `5` consecutive transient failures or triggered the GitOps tug-of-war detector (`< 1h` target revert). | Inspect archived logs via `GET /api/v1/runs/{run_id}/logs`, resolve the underlying failure or GitOps conflict, then reset/resume the schedule. |
| **Run Failed Immediately After 1 Attempt (`exitCode: 2`)** | Worker exited with code `2` (non-retryable configuration or parameter validation failure). | Fix the schedule parameters or worker config before triggering a manual retry. |
| **`502 Bad Gateway` on `POST .../sinks/{name}/test`** | Downstream webhook/SMTP/ITSM receiver returned an HTTP error (such as `HTTP 401 (invalid_hmac_signature)`), failed TLS verification, or refused connection. | Align `WEBHOOK_HMAC_SECRET` in `Secret/p15-session-and-webhook-secrets` with the receiver, check `GDC_CA_BUNDLE` trust, and verify NetworkPolicy egress. |
| **Outbox Item Stuck in `dead_letter`** | Downstream webhook/SMTP/ITSM endpoint returned persistent errors or failed TLS verification after retry budget expired. | Verify internal CA bundle (`GDC_CA_BUNDLE`), endpoint availability, and `X-P15-Signature-256` secret alignment, then re-test with `POST /api/v1/notifications/sinks/{name}/test`. |

---

## 8. API Quick-Reference Summary

| Port | Method & Endpoint | Purpose |
| :--- | :--- | :--- |
| `:8080` | `GET /healthz`, `GET /readyz`, `GET /metrics`, `GET /openapi.json` | Liveness, PostgreSQL readiness, Prometheus exposition, and OpenAPI 3.1 schema. |
| `:8080` / `:8081` | `GET /auth/oidc/login`, `POST /auth/oidc/session`, `GET /auth/me`, `POST /auth/logout` | Initiate Keycloak PKCE (`S256`) login, exchange a verified RS256 JWT (Bearer header or JSON body) for a surface-bound `HttpOnly` cookie + CSRF token, inspect active session, or sign out. |
| `:8080` | `POST /api/v1/schedules/preview` | Preview next 5 UTC/local fire times and DST warnings. |
| `:8080` | `GET`, `POST /api/v1/schedules` / `GET`, `DELETE /api/v1/schedules/{job_id}` | List, register/update, inspect (with watermark), or delete schedules. |
| `:8080` | `POST /api/v1/schedules/{job_id}/{pause,resume,trigger,backfill}` | Operational schedule lifecycle and UTC window backfills. |
| `:8080` | `GET /api/v1/runs` / `GET /api/v1/runs/{run_id}/logs` | Browse run history and download redacted Object Storage logs. |
| `:8080` | `GET /api/v1/findings` / `POST /api/v1/approvals/{finding_id}/{decide,rollback}` | Inspect findings, submit Four-Eyes HITL approvals, and run 1-click snapshot rollbacks. |
| `:8080` | `POST /api/v1/notifications/sinks` / `POST .../sinks/{name}/test` / `GET .../outbox` | Register sinks, dispatch signed test notifications, and inspect the transactional outbox ledger. |
| `:8081` | `GET /admin/v1/overview`, `PUT /admin/v1/allowed-hosts`, `POST /admin/v1/kill-switch` | PA-only governance overview, SSRF allowlist management, and Global Emergency Pause-All Kill-Switch. |
