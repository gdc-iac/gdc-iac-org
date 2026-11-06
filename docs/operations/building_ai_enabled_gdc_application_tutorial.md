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

# Building an AI-Enabled Application on Your GDC-ag Cloud Workstation Environment

> [!IMPORTANT]
> **Purpose & Scope of This Tutorial**  
> This tutorial picks up **immediately after your GDC-ag development environment is set up** (following the [Greenfield GDC-ag Developer Guide](./greenfield_gdc_developer_guide.md)).  
> Its goal is twofold:
> 1. **Give you immediate end-to-end confidence** that your Cloud Workstation, GKE Stepping-Stone cluster, **Gemma 4 GPU Inference Gateway (`gemma-gateway`)**, **Keycloak OIDC (`p12-keycloak`)**, **PostgreSQL (`pgvector`)**, **Google Cloud Storage / S3 Object Storage**, and **Unified Gateway API (`Port 8081`)** work together seamlessly by deploying a **100% pre-canned, AI-enabled Sovereign Mission Intelligence Application**.
> 2. **Show how real-world engineering teams develop code** using standard desktop/laptop tooling (**Antigravity**, **Visual Studio Code**, **Cursor**, **PyCharm**) and transfer code to the Cloud Workstation / GKE staging environment—alongside the **GCP and Sovereign GDC developer tools** available directly inside the Cloud Workstation—before running automated tests and packaging for air-gapped `GDC-ag` production.
>
> **Language Assumption:** All pre-canned backend and test code in this tutorial uses **Python 3.12 (FastAPI)** and a single-page HTML5/JS frontend. Developers using Go, Java, Node.js, or Rust can follow the exact same architecture, OpenAI-compatible `/v1/chat/completions` contract, and promotion gates with language-appropriate adaptations.

---

## 1. Architecture of the Pre-Canned AI-Enabled Application

In this tutorial, you will deploy and test an **AI-Enabled Sovereign Mission & Intelligence Assistant** that combines every core building block of a production `GDC-ag` AI application:

```mermaid
flowchart TB
    subgraph DEV["Developer Authoring & Tooling"]
        LAPTOP["💻 Local Laptop / Desktop\n• Antigravity IDE\n• Visual Studio Code\n• Local Unit Tests & Mock Auth"]
        WS_TOOLS["☁️ Cloud Workstation Dev Tools\n• Browser Code-OSS IDE (Port 80)\n• GDC Dev + JupyterLab 4 (Port 8084)\n• Admin Telemetry Console (Port 8083)\n• Gemma 4 Control Plane (Port 8080)"]
    end

    subgraph GKE["GKE Stepping-Stone Cluster (Current Up-and-Running Environment)"]
        subgraph NS_APP["Application Namespace (${NAMESPACE}: mission-app)"]
            GW["🌐 Unified Gateway API (Port 8081)\ngdc-platform-gateway + HealthCheckPolicies\n• / -> frontend-svc:80\n• /api -> backend-svc:8000\n• /auth -> keycloak-svc:8080"]
            FE["🖥️ AI Mission Portal UI (frontend)\n• Keycloak OIDC PKCE Login\n• 1-Click Pre-Canned AI Scenarios\n• Live AI Gateway Telemetry Badge"]
            BE["⚙️ FastAPI AI Backend (backend)\n• RS256 JWKS Token Validation\n• RBAC: user (UNCLASSIFIED) vs admin (SECRET)\n• POST /api/analyze (AI Tactical Briefing)\n• GET /api/ai/status (Gateway Probe)"]
            KC["🔐 Keycloak OIDC (keycloak-svc:8080)\nRealm: gdc-app-realm (alice / charlie)"]
            PG[("🐘 PostgreSQL + pgvector\n(postgres-svc:5432)\nStores Records + AI Briefings")]
            GCS[("🪣 Google Cloud Storage (GKE)\n/ GDC-ag S3 Bucket (Prod)\nStores Uploaded Field Logs")]
        end

        subgraph NS_GEMMA["Shared GPU Inference Namespace (gemma-inference)"]
            GEMMA_GW["🧠 Gemma 4 Inference Gateway\nhttp://gemma-gateway.gemma-inference.svc.cluster.local/v1\n• Tier 1 Fast MoE: gemma4:26b\n• Tier 2 Deep Dense: gemma4:31b"]
        end
    end

    LAPTOP == "Git Push/Pull, Remote-SSH (Port 2222),\nor rsync/scp" ==> WS_TOOLS
    WS_TOOLS == "docker build/push + helm upgrade" ==> GW
    GW --> FE
    GW --> KC
    GW --> BE
    BE -- "1. Verify RS256 JWT (KubeDNS)" --> KC
    BE -- "2. Upload Telemetry Attachment" --> GCS
    BE -- "3. OpenAI /v1/chat/completions\n(X-Task-Complexity: tier1 | tier2)" --> GEMMA_GW
    BE -- "4. Persist Record + AI Briefing" --> PG
```

### What the Pre-Canned Application Does
1. **Keycloak OIDC PKCE Authentication & Role-Based Access Control (RBAC):**
   - Standard operators (**`alice` / `password`**, role: `user`) can submit `UNCLASSIFIED` field reports and request AI tactical summaries.
   - Mission administrators (**`charlie` / `password`**, role: `admin, user`) can submit `SECRET` intelligence logs and request deep multi-vector AI threat assessments.
2. **Sovereign AI Analysis via the Gemma 4 Gateway (`/api/analyze` & `/api/records`):**
   - Calls `http://gemma-gateway.gemma-inference.svc.cluster.local/v1/chat/completions` inside the cluster using the standard OpenAI Chat Completions payload.
   - Passes `X-Task-Complexity: tier1` (`gemma4:26b` MoE) for standard `UNCLASSIFIED` summaries and `X-Task-Complexity: tier2` (`gemma4:31b` Dense) for complex `SECRET` analytical queries.
   - Includes a **resilient sovereign fallback synthesizer** so that even if a developer tests on a CPU-only cluster (or while GPU nodes are scaling up), the endpoint still returns a structured tactical briefing and clearly reports `"ai_engine": "live-gemma-gateway"` vs. `"ai_engine": "sovereign-tactical-fallback"`.
3. **Cloud/Object Storage + PostgreSQL Audit Persistence:**
   - Any attached log or sensor file is uploaded to **Google Cloud Storage (`gs://...`)** via GKE Workload Identity (or `s3://...` on physical `GDC-ag` racks), and both the raw record and the AI-generated briefing are stored in **PostgreSQL (`mission_records`)**.

---

## 2. Developer Tooling & Code Transfer Workflows: Local Laptop IDE vs. Cloud Workstation GCP Tools

When developing applications for `GDC-ag`, you do **not** have to write all of your code inside a terminal window. You can author code on your **local developer laptop/desktop** using modern AI-assisted IDEs (**Antigravity**, **Visual Studio Code**, **Cursor**, **PyCharm**) and transfer it to your Cloud Workstation for staging tests, **or** use the **integrated GCP and Sovereign GDC tools** directly on the Cloud Workstation.

```mermaid
flowchart LR
    subgraph LOCAL["Option A: Local Laptop / Desktop Authoring"]
        L1["1. Edit in Antigravity or VS Code\n(Local Git Clone ~/Projects/my-app)"]
        L2["2. Fast Local Iteration\n• AUTH_MODE=mock\n• python3 -m unittest"]
    end

    subgraph TRANSFER["4 Ways to Transfer Code to Cloud Workstation"]
        T1["Method 1 (Recommended): Git Push / Pull\nLaptop git push -> Workstation git pull"]
        T2["Method 2: Live Remote-SSH IDE\ngcloud workstations start-tcp-tunnel :2222"]
        T3["Method 3: Instant rsync / scp\nSync uncommitted WIP files over Port 2222"]
        T4["Method 4: Direct Registry Push\ndocker push -> Workstation helm upgrade"]
    end

    subgraph WORKSTATION["Option B: Cloud Workstation & GCP/GDC Dev Tools"]
        W1["🌐 Workstation Browser IDE (Port 80)\nCode-OSS + Gemini Code Assist + Cloud Code"]
        W2["📓 GDC Dev + JupyterLab 4 (Port 8084)\nInteractive AI Prompt & pgvector Prototyping"]
        W3["🎛️ Gemma 4 Control Plane (Port 8080)\nLive Tier 1/Tier 2 Routing & GPU Telemetry"]
        W4["🧪 GKE Staging & Promotion Gates (Port 8081)\nLive Keycloak OIDC + Trivy + OPA + Air-Gap Tarball"]
    end

    L1 --> L2 --> TRANSFER --> WORKSTATION
```

---

### 2.1. Developing on a Local Laptop / Desktop (`Antigravity`, `Visual Studio Code`) & Transferring to the Cloud Workstation

Most developers prefer writing application code on their local laptop or desktop where their AI coding assistants (**Antigravity**, **VS Code**, **GitHub Copilot / Gemini Code Assist**) and local credentials are already configured.

#### Step 1: Fast Local Prototyping on Your Laptop (`AUTH_MODE=mock`)
On your laptop, you do **not** need a local GPU, local Keycloak server, or local Kubernetes cluster to write and unit-test your application logic:
1. Open your project folder in **Antigravity** or **Visual Studio Code** on your laptop.
2. Develop your FastAPI routes and UI using `AUTH_MODE="mock"` (so requests with `-H "X-Mock-User: charlie" -H "X-Mock-Roles: admin,user"` work locally without Keycloak).
3. Run the unit and RBAC test suite locally in under 1 second:
   ```bash
   # On your local laptop / desktop terminal (inside Antigravity or VS Code):
   python3 -m unittest discover -s src/backend -p "test_*.py" -v
   ```

#### Step 2: Transfer Your Code to the Cloud Workstation / GKE Staging Environment (4 Methods)

Choose whichever transfer workflow best fits how you work:

| Transfer Method | Best For | How It Works |
| :--- | :--- | :--- |
| **Method 1: Git / GitHub Sync (`git push` $\rightarrow$ `git pull`) — *Recommended*** | Team development, traceable commits, and CI/CD hygiene | Push from **Antigravity / VS Code** on your laptop to your Git repository, then run `git pull` on the Cloud Workstation terminal to build and deploy to GKE. |
| **Method 2: Connect Desktop Antigravity / VS Code Directly to the Workstation via `Remote-SSH` (`Port 2222`)** | Zero-copy live editing on the Cloud Workstation using your local desktop IDE | Open a TCP tunnel from your laptop to the Cloud Workstation's SSH daemon (`Port 22`) and attach your local **Antigravity** or **VS Code** window directly to `~/GitHub/${APP_NAME}` on the remote workstation. |
| **Method 3: Fast Work-in-Progress File Sync (`rsync` / `scp` over TCP Tunnel)** | Testing uncommitted local edits on GKE in 1–2 seconds without cluttering Git history | Use `rsync` over the `gcloud workstations start-tcp-tunnel` port (`2222`) to mirror your laptop's working directory straight into `~/GitHub/${APP_NAME}` on the Cloud Workstation. |
| **Method 4: Local Container Build & Artifact Registry Push (`docker push`)** | Laptops with Docker installed and GCP IAM credentials | Build and push `${REGISTRY_HOST}/${APP_NAME}-backend:latest` directly from your laptop, then run `helm upgrade --install` on the Cloud Workstation. |

<details open>
<summary><b>Copy-Paste Commands for Methods 1, 2, and 3 (Laptop ↔ Cloud Workstation)</b></summary>

##### Method 1: Git / GitHub Workflow (`git push` on Laptop $\rightarrow$ `git pull` on Workstation)
```bash
# --- ON YOUR LOCAL LAPTOP (Antigravity / VS Code Terminal) ---
git add src/ chart/ manifests/ scripts/
git commit -m "feat: add Gemma 4 AI tactical briefing endpoint and UI"
git push origin main

# --- ON YOUR CLOUD WORKSTATION TERMINAL ---
cd ~/GitHub/${APP_NAME}
git pull --rebase origin main
```

##### Method 2: Connect Desktop Antigravity or VS Code Directly via `Remote-SSH`
1. On your **local laptop/desktop terminal**, start an authenticated SSH tunnel to your Cloud Workstation on local port `2222`:
   ```bash
   # Run on your LOCAL LAPTOP terminal:
   gcloud workstations start-tcp-tunnel \
     --project="<YOUR_PROJECT_ID>" \
     --region="<YOUR_WS_REGION>" \
     --cluster="<YOUR_WS_CLUSTER>" \
     --config="<YOUR_WS_CONFIG>" \
     "<YOUR_WORKSTATION_NAME>" 22 \
     --local-host-port=:2222
   ```
2. Add this host entry to `~/.ssh/config` on your **local laptop/desktop**:
   ```sshconfig
   Host gdc-cloud-workstation
       HostName 127.0.0.1
       Port 2222
       User user
       StrictHostKeyChecking no
       UserKnownHostsFile /dev/null
   ```
3. In **Antigravity** or **Visual Studio Code** on your laptop, open the Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) $\rightarrow$ **Remote-SSH: Connect to Host...** $\rightarrow$ select `gdc-cloud-workstation` $\rightarrow$ open folder `/home/user/GitHub/p15-sovereign-mission-app`. Every edit and terminal command you run in Antigravity/VS Code now executes live inside your Cloud Workstation!

##### Method 3: Instant `rsync` of Uncommitted Local Edits from Laptop to Cloud Workstation
With the `Port 2222` TCP tunnel from Method 2 running on your laptop, sync any local folder to your Cloud Workstation in one command:
```bash
# Run on your LOCAL LAPTOP terminal:
rsync -avz --exclude '.git' --exclude 'dist' \
  -e "ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
  ./ user@127.0.0.1:~/GitHub/p15-sovereign-mission-app/
```
</details>

---

### 2.2. Using the Available GCP & Sovereign GDC Developer Tools Directly from the Cloud Workstation

Once your code is on the Cloud Workstation (or if you prefer developing 100% in the cloud), your environment provides **five integrated GCP and GDC developer tools** that accelerate AI development and debugging prior to production packaging:

| Workstation Port / Tool | Service / Component | How Developers Use It During AI App Development |
| :--- | :--- | :--- |
| **Port `80` (Default Web URL)** | **Cloud Workstations Browser IDE (`Code-OSS`) + Gemini Code Assist + Cloud Code** | Full VS Code-compatible IDE in your browser with integrated bash terminals, Git graph, **Gemini Code Assist** (inline AI code completion & chat), and the **Cloud Code Kubernetes Explorer** for viewing live pod logs and editing YAML manifests. |
| **Port `8084` Web Preview** | **GDC Unified Developer IDE & Integrated JupyterLab 4 (`gdc-dev-landing-page` in namespace `gdc-dev`)** | **Interactive AI & RAG Prototyping Lab:** Click the **JupyterLab** tab inside Port `8084` to launch an in-cluster `Python 3 (ipykernel)` notebook. Because JupyterLab runs *inside* the GKE cluster, you can interactively test prompts against `http://gemma-gateway.gemma-inference.svc.cluster.local/v1/chat/completions` and query `postgres-svc.mission-app.svc.cluster.local:5432` before baking the final code into `src/backend/main.py`. |
| **Port `8080` Web Preview** | **Gemma 4 Inference Gateway Control Plane (`gemma-gateway` in namespace `gemma-inference`)** | **Live LLM Governance & Routing Inspector:** View real-time GPU VRAM utilization, test how the prompt classifier routes between **Tier 1 (`gemma4:26b` MoE)** and **Tier 2 (`gemma4:31b` Dense)**, tune global `temperature` / `top_p` parameters, and inspect or terminate active inference sessions. |
| **Port `8083` Web Preview** | **Sovereign Admin Telemetry Console (`gdc-dev-operator` in namespace `gdc-dev`)** | **Cluster & CRD Health Dashboard:** Inspect simulated GDC Custom Resources (`DBCluster`, `Bucket`), namespace resource quotas, and pod readiness across your cluster. |
| **Port `8081` Web Preview** | **Unified GDC Application Gateway API (`gdc-platform-gateway` in namespace `${NAMESPACE}`)** | **Production-Identical Staging Entrypoint:** Single-origin Envoy Gateway (`/` $\rightarrow$ frontend, `/api` $\rightarrow$ backend, `/auth` $\rightarrow$ Keycloak OIDC) where you test real browser PKCE logins and run automated integration tests before packaging. |

> [!TIP]
> **Quick Command to Ensure All Workstation Web Preview Tunnels (`8080`, `8081`, `8083`, `8084`) Are Running:**  
> At any time on your Cloud Workstation terminal, you can check and start all four Web Preview port-forwards with:
> ```bash
> source ~/GitHub/gdc-dev-env.sh
> curl -sf http://127.0.0.1:8080/health >/dev/null || (kubectl port-forward --address 0.0.0.0 -n gemma-inference svc/gemma-gateway 8080:80 >/dev/null 2>&1 &)
> curl -sf http://127.0.0.1:8083/ >/dev/null       || (kubectl port-forward --address 0.0.0.0 -n gdc-dev svc/gdc-dev-operator 8083:8083 >/dev/null 2>&1 &)
> curl -sf http://127.0.0.1:8084/ >/dev/null       || (kubectl port-forward --address 0.0.0.0 -n gdc-dev svc/gdc-dev-landing-page 8084:8080 >/dev/null 2>&1 &)
> curl -sf http://127.0.0.1:8081/api/health >/dev/null || (nohup bash -c "while true; do kubectl port-forward --address 0.0.0.0 -n ${NAMESPACE} svc/gdc-gateway-tunnel 8081:80 >> /tmp/pf-8081.log 2>&1; sleep 1; done" >/dev/null 2>&1 &)
> ```

---

## 3. Step 1: Verify Your Up-and-Running Environment & Shared Gemma 4 AI Gateway

Run this quick check on your **Cloud Workstation terminal** to load `~/GitHub/gdc-dev-env.sh` and confirm that your `mission-app` staging infrastructure (`postgres`, `keycloak`, `gdc-platform-gateway`) and the shared GPU `gemma-gateway` (`gemma-inference` namespace) are up and running:

```bash
source ~/GitHub/gdc-dev-env.sh
mkdir -p ~/GitHub/${APP_NAME}/{src/backend,src/frontend,manifests/gdc,manifests/apps,manifests/gcp,chart/templates/gdc,chart/templates/apps,chart/tests,scripts,dist}
cd ~/GitHub/${APP_NAME}

echo "=== 1. Checking Staging Services in Namespace: ${NAMESPACE} ==="
kubectl get pods,svc,gateway -n "${NAMESPACE}"

echo "=== 2. Checking Shared GPU Gemma 4 Inference Gateway (gemma-inference) ==="
kubectl get pods,svc -n gemma-inference

echo "=== 3. Probing Gemma 4 Gateway Over Internal Cluster DNS ==="
kubectl exec -n "${NAMESPACE}" deploy/postgres -- \
  sh -c "wget -qO- --timeout=5 http://gemma-gateway.gemma-inference.svc.cluster.local/health 2>/dev/null || echo '{\"status\":\"gateway_warming_or_cpu_mode\"}'"
echo ""
```

<details>
<summary><b>Starting from a Brand-New Namespace? (Click to expand only if <code>postgres</code>, <code>keycloak</code>, or <code>gdc-platform-gateway</code> are not yet running in <code>${NAMESPACE}</code>)</b></summary>

If you already completed the Greenfield Guide validation in `mission-app`, **skip this box**—your PostgreSQL database, GCS bucket, Keycloak OIDC server, and Gateway API (`Port 8081`) are already running! If you are running in a brand-new namespace where those services haven't been applied yet, apply the existing `manifests/gcp/*.yaml` files from the Greenfield Guide:
```bash
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/postgres-emulation.yaml -n "${NAMESPACE}"
kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/gcs-workload-identity.yaml -n "${NAMESPACE}"
kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/gateway-api-staging.yaml -n "${NAMESPACE}"
kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/keycloak-emulation.yaml -n "${NAMESPACE}"
kubectl rollout status deployment/postgres deployment/keycloak -n "${NAMESPACE}" --timeout=180s
```
</details>

---

## 4. Step 2: Create the Pre-Canned AI-Enabled Backend (`src/backend/`)

Now let's populate `src/backend/` with the **pre-canned AI-enabled FastAPI service**. Compared to the basic CRUD skeleton, this backend adds:
1. **`OPENAI_API_BASE_URL` (`http://gemma-gateway.gemma-inference.svc.cluster.local/v1`)**: Calls the in-cluster Gemma 4 Dedicated Inference Gateway (`gemma4:26b` Tier 1 MoE for `UNCLASSIFIED` tasks; `gemma4:31b` Tier 2 Dense for `SECRET` tasks) using Python's standard `urllib.request` / `requests` client.
2. **Resilient Sovereign AI Fallback (`call_sovereign_llm`)**: If `gemma-gateway` is actively serving GPU models, it returns the live Gemma 4 completion along with `X-Model-Used` and `X-Model-Tier`. If `gemma-gateway` is still warming up or running on a CPU-only test cluster without GPU nodes, it automatically synthesizes a deterministic tactical AI briefing so your end-to-end workflow and UI tests never hang or fail.
3. **`GET /ai/status` (`/api/ai/status` via Gateway)**: Probes `gemma-gateway` health, reports the active model routing configuration, storage backend (`gcp-gcs` vs `gdc-s3`), and database readiness.
4. **`POST /analyze` (`/api/analyze` via Gateway)**: Accepts a tactical prompt, classification (`UNCLASSIFIED` or `SECRET`), and optional file attachment (`UploadFile`), enforces Keycloak OIDC RBAC (`alice` is blocked with `403 Forbidden` from `SECRET` AI analysis; `charlie` is authorized), uploads any attachment to GCS/S3, invokes the Gemma 4 Gateway, persists the record + AI briefing to PostgreSQL (`mission_records`), and returns the structured AI intelligence card.

Copy and paste the following block on your **Cloud Workstation terminal**:

```bash
source ~/GitHub/gdc-dev-env.sh
cd ~/GitHub/${APP_NAME}

# 1. Backend Python Dependencies (CVE-Clean Pinning)
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/backend/requirements.txt
fastapi>=0.135.0
uvicorn[standard]>=0.34.0
PyJWT[crypto]>=2.10.1
cryptography>=44.0.1
requests>=2.32.4
urllib3>=2.5.0
psycopg2-binary>=2.9.10
google-cloud-storage>=2.19.0
boto3>=1.36.0
python-multipart>=0.0.22
EOF

# 2. Pre-Canned AI-Enabled FastAPI Service (src/backend/main.py)
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/backend/main.py
import os
import time
import boto3
import jwt
import psycopg2
import requests
from botocore.client import Config
from google.cloud import storage as gcs_storage
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

app = FastAPI(title="GDC-ag Sovereign AI Mission & Intelligence API")

# ---------------------------------------------------------------------------
# 1. Dual-Mode Authentication: Live Keycloak OIDC RS256 JWKS (Default) +
#    Optional AUTH_MODE="mock" for Local Laptop Prototyping (Antigravity/VS Code)
# ---------------------------------------------------------------------------
AUTH_MODE = os.getenv("AUTH_MODE", "keycloak").lower()
KEYCLOAK_INTERNAL_URL = os.getenv(
    "KEYCLOAK_URL",
    "http://keycloak-svc:8080/auth/realms/gdc-app-realm",
)
bearer_scheme = HTTPBearer(auto_error=False)
jwks_client = PyJWKClient(f"{KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/certs")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    x_mock_user: str | None = Header(default=None, alias="X-Mock-User"),
    x_mock_roles: str | None = Header(default=None, alias="X-Mock-Roles"),
) -> dict:
    # Local laptop prototyping mode (ONLY active when AUTH_MODE="mock" and no Bearer token sent)
    if AUTH_MODE == "mock" and not credentials:
        username = x_mock_user or "alice"
        roles = [r.strip() for r in (x_mock_roles or "user").split(",") if r.strip()]
        return {"username": username, "roles": roles, "auth_source": "mock"}

    token = credentials.credentials if isinstance(credentials, HTTPAuthorizationCredentials) else (
        credentials if isinstance(credentials, str) else None
    )
    if not token:
        raise HTTPException(status_code=401, detail="Missing OIDC Bearer token")

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        username = payload.get("preferred_username") or payload.get("sub")
        roles = payload.get("roles") or payload.get("realm_access", {}).get("roles", [])
        if not username:
            raise HTTPException(status_code=401, detail="Invalid OIDC token claims")
        return {"username": username, "roles": roles}
    except (PyJWTError, Exception) as exc:
        raise HTTPException(status_code=401, detail=f"OIDC JWT validation failed: {exc}")


# ---------------------------------------------------------------------------
# 2. Database (PostgreSQL + pgvector) & Dual-Mode Storage (GCS <-> GDC-ag S3)
# ---------------------------------------------------------------------------
DB_CONN = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres-svc:5432/postgres")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "").strip()
S3_REGION = os.getenv("S3_REGION", "zone1").strip()
BUCKET_NAME = (
    os.getenv("BUCKET_NAME", "p15-sovereign-mission-app-bucket")
    .removeprefix("s3://")
    .removeprefix("gs://")
)

# ---------------------------------------------------------------------------
# 3. Sovereign AI Inference Configuration (Gemma 4 Gateway in gemma-inference)
# ---------------------------------------------------------------------------
OPENAI_API_BASE_URL = os.getenv(
    "OPENAI_API_BASE_URL",
    "http://gemma-gateway.gemma-inference.svc.cluster.local/v1",
).rstrip("/")
AI_GATEWAY_ROOT_URL = OPENAI_API_BASE_URL.removesuffix("/v1")
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "45.0"))

s3_client = None
gcs_client = None

if S3_ENDPOINT:
    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY") or None,
        config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10),
        region_name=S3_REGION,
    )
else:
    try:
        gcs_client = gcs_storage.Client()
    except Exception as exc:
        print(f"Warning: Could not initialize GCS client: {exc}")


def upload_object_bytes(object_key: str, content: bytes, content_type: str) -> str:
    if s3_client:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=object_key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
        )
        return f"s3://{BUCKET_NAME}/{object_key}"
    if gcs_client:
        bucket = gcs_client.bucket(BUCKET_NAME)
        blob = bucket.blob(object_key)
        blob.upload_from_string(content, content_type=content_type, timeout=10)
        return f"gs://{BUCKET_NAME}/{object_key}"
    raise HTTPException(status_code=500, detail="No object storage client initialized")


def call_sovereign_llm(
    prompt: str,
    classification: str,
    username: str,
    attachment_excerpt: str = "",
) -> dict:
    """
    Calls the in-cluster Gemma 4 Dedicated Inference Gateway (/v1/chat/completions).
    Routes UNCLASSIFIED queries to Tier 1 (gemma4:26b MoE) and SECRET queries to
    Tier 2 (gemma4:31b Dense). Automatically provides a deterministic sovereign
    tactical synthesis fallback if GPU pods are scaled down or warming up.
    """
    complexity_tier = "tier2" if classification == "SECRET" else "tier1"
    requested_model = "gemma4:31b" if classification == "SECRET" else "gemma4:26b"
    context_block = (
        f"\n\n[Attached Field Telemetry Excerpt]:\n{attachment_excerpt[:1500]}"
        if attachment_excerpt
        else ""
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a sovereign GDC Air-Gapped Mission Intelligence AI Assistant. "
                "Provide a concise, structured 3-bullet tactical assessment covering: "
                "(1) Operational Summary, (2) Risk/Anomaly Assessment, and (3) Recommended Action."
            ),
        },
        {
            "role": "user",
            "content": f"[{classification} REQUEST by {username}] {prompt}{context_block}",
        },
    ]

    start_ts = time.monotonic()
    try:
        resp = requests.post(
            f"{OPENAI_API_BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "X-Authenticated-User": username,
                "X-Task-Complexity": complexity_tier,
            },
            json={
                "model": requested_model,
                "messages": messages,
                "max_tokens": 256,
                "temperature": 0.2,
                "stream": False,
            },
            timeout=AI_TIMEOUT_SECONDS,
        )
        latency_ms = int((time.monotonic() - start_ts) * 1000)
        if resp.status_code == 200:
            body = resp.json()
            ai_text = (
                body.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if ai_text:
                model_used = resp.headers.get("X-Model-Used") or body.get("model") or requested_model
                model_tier = resp.headers.get("X-Model-Tier") or ("Dense" if "31b" in model_used else "MoE")
                return {
                    "ai_briefing": ai_text,
                    "ai_engine": "live-gemma-gateway",
                    "model_used": model_used,
                    "model_tier": model_tier,
                    "latency_ms": latency_ms,
                }
    except Exception as exc:
        print(f"Info: Gemma Gateway call fell back to deterministic synthesizer: {exc}")

    latency_ms = int((time.monotonic() - start_ts) * 1000)
    fallback_briefing = (
        f"• [Operational Summary ({classification})]: Analyzed input from operator '{username}' "
        f"({prompt[:120]})."
        + (f" Ingested {len(attachment_excerpt)} bytes of attached telemetry." if attachment_excerpt else "")
        + "\n• [Risk/Anomaly Assessment]: Sovereign air-gap boundary integrity verified; "
        "telemetry patterns match baseline sector thresholds."
        "\n• [Recommended Action]: Continue automated monitoring and archive artifact in sovereign storage."
    )
    return {
        "ai_briefing": fallback_briefing,
        "ai_engine": "sovereign-tactical-fallback",
        "model_used": f"{requested_model} (fallback)",
        "model_tier": "Dense" if classification == "SECRET" else "MoE",
        "latency_ms": latency_ms,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "mission-backend",
        "storage_mode": "gdc-s3" if s3_client else "gcp-gcs",
        "ai_gateway_url": OPENAI_API_BASE_URL,
    }


@app.get("/ai/status")
def ai_status():
    """Probes the in-cluster Gemma 4 Inference Gateway and reports environment readiness."""
    gw_reachable = False
    gw_status_code = None
    try:
        r = requests.get(f"{AI_GATEWAY_ROOT_URL}/health", timeout=3.0)
        gw_status_code = r.status_code
        gw_reachable = r.status_code < 500
    except Exception:
        gw_reachable = False

    return {
        "status": "ready",
        "ai_gateway_url": OPENAI_API_BASE_URL,
        "ai_gateway_reachable": gw_reachable,
        "ai_gateway_http_status": gw_status_code,
        "tier1_model": "gemma4:26b (MoE - UNCLASSIFIED)",
        "tier2_model": "gemma4:31b (Dense - SECRET)",
        "storage_mode": "gdc-s3" if s3_client else "gcp-gcs",
        "bucket_name": BUCKET_NAME,
    }


@app.get("/records")
def list_records(user: dict = Depends(get_current_user)):
    with psycopg2.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, author, classification, summary, s3_object_key, created_at "
                "FROM mission_records ORDER BY id DESC LIMIT 50;"
            )
            rows = cur.fetchall()
    return {
        "authenticated_user": user["username"],
        "roles": user["roles"],
        "records": [
            {
                "id": r[0],
                "author": r[1],
                "classification": r[2],
                "summary": r[3],
                "s3_object_key": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ],
    }


@app.post("/records")
async def create_record(
    classification: str = Form("UNCLASSIFIED"),
    summary: str = Form(...),
    attachment: UploadFile = File(None),
    user: dict = Depends(get_current_user),
):
    if classification == "SECRET" and "admin" not in user["roles"]:
        raise HTTPException(status_code=403, detail="Only 'admin' role (e.g. charlie) can file SECRET records")

    storage_uri = None
    if attachment and attachment.filename:
        safe_name = os.path.basename(attachment.filename)
        object_key = f"{user['username']}/{safe_name}"
        content = await attachment.read()
        storage_uri = upload_object_bytes(object_key, content, attachment.content_type)

    with psycopg2.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO mission_records (author, classification, summary, s3_object_key) "
                "VALUES (%s, %s, %s, %s) RETURNING id;",
                (user["username"], classification, summary, storage_uri),
            )
            record_id = cur.fetchone()[0]
        conn.commit()

    return {"status": "created", "id": record_id, "author": user["username"], "s3_object_key": storage_uri}


@app.post("/analyze")
async def analyze_mission_intelligence(
    classification: str = Form("UNCLASSIFIED"),
    prompt: str = Form(...),
    attachment: UploadFile = File(None),
    user: dict = Depends(get_current_user),
):
    """
    AI-Enabled Sovereign Mission Endpoint:
    1. Enforces Keycloak OIDC RS256 authentication & RBAC (SECRET requires 'admin' role).
    2. Uploads any attached telemetry/log file to GCS (GKE Workload Identity) or S3 (GDC-ag).
    3. Invokes Gemma 4 Inference Gateway (/v1/chat/completions) with automatic complexity routing.
    4. Persists the prompt + AI-generated tactical briefing to PostgreSQL (mission_records).
    """
    if classification == "SECRET" and "admin" not in user["roles"]:
        raise HTTPException(
            status_code=403,
            detail="Only 'admin' role (e.g. charlie) can run SECRET AI threat assessments",
        )

    storage_uri = None
    attachment_excerpt = ""
    if attachment and attachment.filename:
        safe_name = os.path.basename(attachment.filename)
        object_key = f"{user['username']}/ai-{safe_name}"
        content = await attachment.read()
        attachment_excerpt = content.decode("utf-8", errors="replace")
        storage_uri = upload_object_bytes(object_key, content, attachment.content_type)

    ai_result = call_sovereign_llm(
        prompt=prompt,
        classification=classification,
        username=user["username"],
        attachment_excerpt=attachment_excerpt,
    )

    combined_summary = f"[AI-BRIEFING | {ai_result['model_used']}] Prompt: {prompt} || Assessment: {ai_result['ai_briefing']}"

    with psycopg2.connect(DB_CONN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO mission_records (author, classification, summary, s3_object_key) "
                "VALUES (%s, %s, %s, %s) RETURNING id;",
                (user["username"], classification, combined_summary, storage_uri),
            )
            record_id = cur.fetchone()[0]
        conn.commit()

    return {
        "status": "analyzed",
        "id": record_id,
        "author": user["username"],
        "classification": classification,
        "prompt": prompt,
        "ai_briefing": ai_result["ai_briefing"],
        "ai_engine": ai_result["ai_engine"],
        "model_used": ai_result["model_used"],
        "model_tier": ai_result["model_tier"],
        "latency_ms": ai_result["latency_ms"],
        "s3_object_key": storage_uri,
    }
EOF

# 3. Rootless Backend Dockerfile (USER 1000:1000)
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/* && \
    groupadd -g 1000 appuser && useradd -u 1000 -g 1000 -m -s /bin/sh appuser
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt
COPY main.py .
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
```

---

## 5. Step 3: Create the Pre-Canned AI Mission Assistant Frontend (`src/frontend/`)

Next, populate `src/frontend/` with the **AI-Enabled Sovereign Mission & Intelligence Portal**. It includes:
- **Live Environment & AI Gateway Status Bar**: Calls `/api/ai/status` to show your connected `gemma-gateway` endpoint, Tier 1 (`gemma4:26b` MoE) and Tier 2 (`gemma4:31b` Dense) models, and active storage backend (`gcp-gcs` vs `gdc-s3`).
- **1-Click Pre-Canned AI Scenarios**: Three instant preset buttons (*Perimeter Sensor Anomaly*, *SECRET Multi-Vector Threat Correlation*, and *Supply-Chain Readiness Digest*) that automatically populate realistic mission prompts and attach a sample telemetry file (`sector9-telemetry.log`) in memory so you can test the entire AI + GCS + PostgreSQL + Keycloak RBAC pipeline with a single click!

```bash
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/frontend/index.html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>GDC-ag Sovereign AI Mission & Intelligence Portal</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; max-width: 980px; margin: 1.5rem auto; padding: 0 1rem; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    button { background: #2563eb; color: white; border: none; padding: 0.6rem 1.1rem; border-radius: 6px; cursor: pointer; font-weight: 600; margin-right: 0.4rem; margin-bottom: 0.4rem; }
    button.preset { background: #334155; font-size: 0.85rem; padding: 0.45rem 0.8rem; }
    button.preset:hover { background: #475569; }
    button.ai-btn { background: #7c3aed; }
    button.ai-btn:hover { background: #6d28d9; }
    input, select, textarea { width: 100%; box-sizing: border-box; padding: 0.55rem; margin: 0.35rem 0 0.8rem; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; }
    .badge { background: #059669; padding: 0.25rem 0.65rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; display: inline-block; margin-left: 0.4rem; }
    .badge.purple { background: #7c3aed; }
    .badge.amber { background: #d97706; }
    pre { background: #090d16; border: 1px solid #334155; border-radius: 6px; padding: 0.9rem; overflow-x: auto; white-space: pre-wrap; font-size: 0.85rem; color: #e2e8f0; }
    .status-bar { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; font-size: 0.85rem; color: #cbd5e1; }
  </style>
</head>
<body>
  <h1>🧠🛡️ GDC-ag Sovereign AI Mission & Intelligence Portal</h1>

  <div class="card">
    <div id="env-status" class="status-bar">Checking Gemma 4 AI Gateway & Storage environment status...</div>
  </div>

  <div id="auth-box" class="card">Loading Keycloak OIDC boundary...</div>

  <div id="app-box" style="display:none;">
    <div class="card" style="border-color: #7c3aed;">
      <h3>🤖 Sovereign AI Tactical Briefing Generator (Gemma 4 Gateway + GCS/S3 + PostgreSQL)</h3>
      <p style="font-size:0.9rem; color:#94a3b8; margin-top:0;">
        Click a <b>Pre-Canned Scenario</b> below (which also attaches a synthetic sensor log for GCS/S3 upload) or enter your own query:
      </p>
      <div>
        <button type="button" class="preset" onclick="loadPreset(1)">⚡ Scenario 1: Perimeter Sensor Anomaly (UNCLASSIFIED / Tier 1 MoE)</button>
        <button type="button" class="preset" onclick="loadPreset(2)">🔒 Scenario 2: Multi-Vector Threat Correlation (SECRET / Tier 2 Dense - Admin Only)</button>
        <button type="button" class="preset" onclick="loadPreset(3)">📦 Scenario 3: Air-Gap Convoy Logistics Readiness (UNCLASSIFIED / Tier 1 MoE)</button>
      </div>
      <form id="ai-form" style="margin-top: 0.8rem;">
        <label>Security Classification (<code>SECRET</code> routes to Tier 2 Dense <code>gemma4:31b</code> & requires <code>admin</code> role / <code>charlie</code>):</label>
        <select id="ai-classification" name="classification">
          <option value="UNCLASSIFIED">UNCLASSIFIED (Allowed for alice & charlie -> Tier 1 gemma4:26b MoE)</option>
          <option value="SECRET">SECRET (Requires admin role / charlie -> Tier 2 gemma4:31b Dense)</option>
        </select>
        <label>Tactical Prompt for Gemma 4 Inference Gateway:</label>
        <textarea id="ai-prompt" name="prompt" rows="3" required placeholder="Select a preset scenario above or type a tactical intelligence question..."></textarea>
        <label>Optional Telemetry / Field Log Attachment (Uploaded to GCS on GKE / S3 on GDC-ag & injected into AI prompt context):</label>
        <input id="ai-attachment" type="file" name="attachment" />
        <div id="preset-file-indicator" style="font-size:0.8rem; color:#38bdf8; margin-bottom:0.6rem;"></div>
        <button type="submit" class="ai-btn">🧠 Generate Sovereign AI Briefing & Persist</button>
      </form>
      <div id="ai-result-card" style="display:none; margin-top:1rem;">
        <h4>Latest AI Tactical Assessment</h4>
        <div id="ai-meta" style="margin-bottom:0.5rem;"></div>
        <pre id="ai-output"></pre>
      </div>
    </div>

    <div class="card">
      <h3>📜 Persisted Mission & AI Briefing Audit Log (PostgreSQL + GCS/S3 Object URIs)</h3>
      <pre id="records-out">Loading...</pre>
    </div>
  </div>

  <script>
    const REALM_URL = `${window.location.origin}/auth/realms/gdc-app-realm/protocol/openid-connect`;
    const CLIENT_ID = "mission-frontend";
    let syntheticAttachmentBlob = null;
    let syntheticAttachmentName = "";

    const PRESETS = {
      1: {
        classification: "UNCLASSIFIED",
        prompt: "Analyze Sector 4 perimeter acoustic and thermal sensor readings from 02:00-04:00Z and recommend immediate patrol posture.",
        filename: "sector4-perimeter-sensors.log",
        content: "TIMESTAMP=2026-11-06T02:14:00Z SENSOR=ACOUSTIC-S4-09 DBA=78.4 ANOMALY=TRANSIENT_VEHICLE_SIGNATURE\nTIMESTAMP=2026-11-06T02:15:12Z SENSOR=THERMAL-S4-02 DELTA_C=+11.2 BEARING=245_DEG\nSTATUS=PERIMETER_FENCE_INTACT"
      },
      2: {
        classification: "SECRET",
        prompt: "Correlate encrypted RF burst detections in Grid 9B with satellite uplink latency spikes and provide a classified counter-electronic-warfare action plan.",
        filename: "grid9b-rf-spectrum-classified.log",
        content: "CLASSIFICATION=SECRET//NOFORN\nRF_BAND=14.25GHz HOP_RATE=1200_HOPS_SEC SNR_DB=19.8\nUPLINK_JITTER_MS=412 PACKET_LOSS_PCT=4.7\nSIGNATURE_MATCH=PROBABILISTIC_JAMMING_NODE_ALPHA"
      },
      3: {
        classification: "UNCLASSIFIED",
        prompt: "Summarize forward operating depot battery reserve levels, diesel generator runtime hours, and medical resupply priority for the next 72 hours.",
        filename: "depot-logistics-status.txt",
        content: "DEPOT=FOB-SIERRA\nBATTERY_BANK_SOC_PCT=84%\nDIESEL_RESERVE_LITERS=14200 EST_RUNTIME_HOURS=168\nMEDICAL_TRAUMA_KITS_REMAINING=42 REPLENISHMENT_THRESHOLD=50"
      }
    };

    function loadPreset(id) {
      const p = PRESETS[id];
      document.getElementById("ai-classification").value = p.classification;
      document.getElementById("ai-prompt").value = p.prompt;
      syntheticAttachmentBlob = new Blob([p.content], { type: "text/plain" });
      syntheticAttachmentName = p.filename;
      document.getElementById("preset-file-indicator").textContent =
        `📎 Pre-canned telemetry file queued for upload: ${p.filename} (${p.content.length} bytes)`;
    }

    async function loadEnvStatus() {
      try {
        const r = await fetch("/api/ai/status");
        const s = await r.json();
        const gwBadge = s.ai_gateway_reachable
          ? `<span class="badge purple">Gemma 4 Gateway: CONNECTED</span>`
          : `<span class="badge amber">Gemma 4 Gateway: FALLBACK MODE</span>`;
        document.getElementById("env-status").innerHTML =
          `<b>Environment Readiness:</b> ${gwBadge} ` +
          `<span class="badge">Storage: ${s.storage_mode.toUpperCase()} (${s.bucket_name})</span> ` +
          `<span style="color:#94a3b8;">Endpoint: <code>${s.ai_gateway_url}</code></span>`;
      } catch (e) {
        document.getElementById("env-status").textContent = "Backend status check pending...";
      }
    }

    async function sha256Base64Url(str) {
      const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
      return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    }

    async function login() {
      const verifier = Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, "0")).join("");
      sessionStorage.setItem("pkce_verifier", verifier);
      const challenge = await sha256Base64Url(verifier);
      const redirectUri = encodeURIComponent(window.location.origin + "/");
      window.location.href = `${REALM_URL}/auth?client_id=${CLIENT_ID}&redirect_uri=${redirectUri}&response_type=code&scope=openid%20profile&code_challenge=${challenge}&code_challenge_method=S256`;
    }

    function logout() {
      sessionStorage.removeItem("oidc_token");
      window.location.reload();
    }

    async function init() {
      await loadEnvStatus();
      const params = new URLSearchParams(window.location.search);
      if (params.has("code")) {
        const verifier = sessionStorage.getItem("pkce_verifier");
        const body = new URLSearchParams({
          grant_type: "authorization_code",
          client_id: CLIENT_ID,
          code: params.get("code"),
          redirect_uri: window.location.origin + "/",
          code_verifier: verifier,
        });
        const r = await fetch(`${REALM_URL}/token`, { method: "POST", body });
        const data = await r.json();
        if (data.access_token) sessionStorage.setItem("oidc_token", data.access_token);
        window.history.replaceState({}, document.title, "/");
      }

      const token = sessionStorage.getItem("oidc_token");
      if (!token) {
        document.getElementById("auth-box").innerHTML =
          `<button onclick="login()">🔑 Sign In with Keycloak OIDC (alice = user | charlie = admin)</button>`;
        return;
      }
      const payloadB64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const claims = JSON.parse(atob(payloadB64));
      document.getElementById("auth-box").innerHTML =
        `Authenticated via Keycloak OIDC as <b>${claims.preferred_username}</b> ` +
        `<span class="badge">Roles: ${(claims.roles || []).join(", ")}</span> ` +
        `<button class="preset" style="float:right;" onclick="logout()">Sign Out</button>`;
      document.getElementById("app-box").style.display = "block";
      loadPreset(1);
      await loadRecords(token);

      document.getElementById("ai-form").onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData();
        fd.append("classification", document.getElementById("ai-classification").value);
        fd.append("prompt", document.getElementById("ai-prompt").value);
        const fileInput = document.getElementById("ai-attachment");
        if (fileInput.files.length > 0) {
          fd.append("attachment", fileInput.files[0]);
        } else if (syntheticAttachmentBlob) {
          fd.append("attachment", syntheticAttachmentBlob, syntheticAttachmentName);
        }

        const outCard = document.getElementById("ai-result-card");
        const outPre = document.getElementById("ai-output");
        const outMeta = document.getElementById("ai-meta");
        outCard.style.display = "block";
        outPre.textContent = "⏳ Calling Gemma 4 Inference Gateway & persisting to GCS/PostgreSQL...";

        const res = await fetch("/api/analyze", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        });
        const text = await res.text();
        let data = {};
        try { data = JSON.parse(text); } catch (_) {}

        if (!res.ok) {
          outMeta.innerHTML = `<span class="badge amber">HTTP ${res.status} Blocked by Zero-Trust RBAC</span>`;
          outPre.textContent = data.detail || text;
        } else {
          outMeta.innerHTML =
            `<span class="badge purple">Engine: ${data.ai_engine}</span>` +
            `<span class="badge">Model: ${data.model_used} (${data.model_tier})</span>` +
            `<span class="badge">Latency: ${data.latency_ms} ms</span>` +
            (data.s3_object_key ? `<span class="badge">Artifact: ${data.s3_object_key}</span>` : "");
          outPre.textContent = data.ai_briefing;
        }
        await loadRecords(token);
      };
    }

    async function loadRecords(token) {
      const res = await fetch("/api/records", { headers: { Authorization: `Bearer ${token}` } });
      document.getElementById("records-out").textContent = JSON.stringify(await res.json(), null, 2);
    }
    init();
  </script>
</body>
</html>
EOF

cat << 'EOF' > ~/GitHub/${APP_NAME}/src/frontend/Dockerfile
FROM nginxinc/nginx-unprivileged:1.27-alpine
USER root
RUN apk upgrade --no-cache
COPY index.html /usr/share/nginx/html/index.html
USER 101:101
EXPOSE 8080
EOF
```

---

## 6. Step 4: Update the Helm Chart (`chart/`) & Production Manifests (`manifests/`) with AI Gateway Wiring

Update `manifests/apps/workloads.yaml`, `chart/values.yaml`, `chart/values.schema.json`, and `chart/templates/apps/workloads.yaml` so `OPENAI_API_BASE_URL` (`http://gemma-gateway.gemma-inference.svc.cluster.local/v1`) is declaratively injected into your backend container:

```bash
source ~/GitHub/gdc-dev-env.sh
cd ~/GitHub/${APP_NAME}

# 1. Production User Cluster Workloads (manifests/apps/workloads.yaml)
cat <<EOF > ~/GitHub/${APP_NAME}/manifests/apps/workloads.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      serviceAccountName: ${APP_NAME}-sa
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: backend
        image: ${REGISTRY_HOST}/${APP_NAME}-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-db-credentials
              key: connection_string
        - name: KEYCLOAK_URL
          value: "http://keycloak-svc:8080/auth/realms/gdc-app-realm"
        - name: OPENAI_API_BASE_URL
          value: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
        envFrom:
        - secretRef:
            name: ${APP_NAME}-s3-credentials
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        volumeMounts:
        - name: tmp-dir
          mountPath: /tmp
        resources:
          requests:
            cpu: "100m"
            memory: "256Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
      volumes:
      - name: tmp-dir
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
  namespace: ${NAMESPACE}
spec:
  selector:
    app: backend
  ports:
  - port: 8000
    targetPort: 8000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 101
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: frontend
        image: ${REGISTRY_HOST}/${APP_NAME}-frontend:latest
        ports:
        - containerPort: 8080
        securityContext:
          runAsNonRoot: true
          runAsUser: 101
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        volumeMounts:
        - name: tmp-dir
          mountPath: /tmp
        - name: nginx-cache
          mountPath: /var/cache/nginx
        - name: nginx-run
          mountPath: /var/run
        resources:
          requests:
            cpu: "50m"
            memory: "64Mi"
          limits:
            cpu: "200m"
            memory: "128Mi"
      volumes:
      - name: tmp-dir
        emptyDir: {}
      - name: nginx-cache
        emptyDir: {}
      - name: nginx-run
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
  namespace: ${NAMESPACE}
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: ${APP_NAME}-unified-routes
  namespace: ${NAMESPACE}
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: ${NAMESPACE}
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /auth
    filters:
    - type: RequestHeaderModifier
      requestHeaderModifier:
        set:
        - name: X-Forwarded-Proto
          value: https
    backendRefs:
    - name: keycloak-svc
      port: 8080
  - matches:
    - path:
        type: PathPrefix
        value: /api
    filters:
    - type: URLRewrite
      urlRewrite:
        path:
          type: ReplacePrefixMatch
          replacePrefixMatch: /
    backendRefs:
    - name: backend-svc
      port: 8000
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: frontend-svc
      port: 80
EOF

# 2. Update Helm Chart values.yaml, values.schema.json, and templates/apps/workloads.yaml
cat <<EOF > ~/GitHub/${APP_NAME}/chart/values.yaml
global:
  projectId: "test-project"
  namespace: "mission-app"
  registry: "harbor.gdc.local/blueprint-images"
  imagePullSecrets: []
  commonLabels: {}
  commonAnnotations: {}

namespace: ""
registry: ""

gdc:
  enabled: false

apps:
  enabled: true
  imageTag: "latest"
  serviceAccountName: "${APP_NAME}-sa"
  keycloakUrl: "http://keycloak-svc:8080/auth/realms/gdc-app-realm"
  openaiApiBaseUrl: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
  s3Endpoint: "https://objectstorage.gdc.goog"
  bucketName: "${APP_NAME}-bucket"
EOF

cat << 'EOF' > ~/GitHub/${APP_NAME}/chart/values.schema.json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "global": {
      "type": "object",
      "properties": {
        "projectId": { "type": "string" },
        "namespace": { "type": "string" },
        "registry": { "type": "string" }
      }
    },
    "gdc": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean" }
      }
    },
    "apps": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean" },
        "imageTag": { "type": "string" },
        "serviceAccountName": { "type": "string" },
        "keycloakUrl": { "type": "string" },
        "openaiApiBaseUrl": { "type": "string" },
        "s3Endpoint": { "type": "string" },
        "bucketName": { "type": "string" }
      }
    }
  }
}
EOF

cat <<EOF > ~/GitHub/${APP_NAME}/chart/templates/apps/workloads.yaml
{{- if .Values.apps.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      serviceAccountName: {{ .Values.apps.serviceAccountName | default "${APP_NAME}-sa" }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: backend
        image: "{{ include "${APP_NAME}.registry" . }}/${APP_NAME}-backend:{{ .Values.apps.imageTag }}"
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-db-credentials
              key: connection_string
        - name: KEYCLOAK_URL
          value: {{ .Values.apps.keycloakUrl | quote }}
        - name: OPENAI_API_BASE_URL
          value: {{ .Values.apps.openaiApiBaseUrl | default "http://gemma-gateway.gemma-inference.svc.cluster.local/v1" | quote }}
        - name: S3_ENDPOINT
          value: {{ .Values.apps.s3Endpoint | quote }}
        - name: BUCKET_NAME
          value: {{ .Values.apps.bucketName | quote }}
        envFrom:
        - secretRef:
            name: ${APP_NAME}-s3-credentials
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        volumeMounts:
        - name: tmp-dir
          mountPath: /tmp
        resources:
          requests:
            cpu: "100m"
            memory: "256Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
      volumes:
      - name: tmp-dir
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  selector:
    app: backend
  ports:
  - port: 8000
    targetPort: 8000
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 101
        seccompProfile:
          type: RuntimeDefault
      containers:
      - name: frontend
        image: "{{ include "${APP_NAME}.registry" . }}/${APP_NAME}-frontend:{{ .Values.apps.imageTag }}"
        ports:
        - containerPort: 8080
        securityContext:
          runAsNonRoot: true
          runAsUser: 101
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
        volumeMounts:
        - name: tmp-dir
          mountPath: /tmp
        - name: nginx-cache
          mountPath: /var/cache/nginx
        - name: nginx-run
          mountPath: /var/run
        resources:
          requests:
            cpu: "50m"
            memory: "64Mi"
          limits:
            cpu: "200m"
            memory: "128Mi"
      volumes:
      - name: tmp-dir
        emptyDir: {}
      - name: nginx-cache
        emptyDir: {}
      - name: nginx-run
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 8080
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: ${APP_NAME}-unified-routes
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: {{ include "${APP_NAME}.namespace" . }}
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /auth
    filters:
    - type: RequestHeaderModifier
      requestHeaderModifier:
        set:
        - name: X-Forwarded-Proto
          value: https
    backendRefs:
    - name: keycloak-svc
      port: 8080
  - matches:
    - path:
        type: PathPrefix
        value: /api
    filters:
    - type: URLRewrite
      urlRewrite:
        path:
          type: ReplacePrefixMatch
          replacePrefixMatch: /
    backendRefs:
    - name: backend-svc
      port: 8000
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: frontend-svc
      port: 80
{{- end }}
EOF
```

---

## 7. Step 5: Build, Push & Deploy the AI-Enabled Application to Your Running GKE Environment

Now build and push the updated AI-enabled container images to `blueprint-images` (`us-central1`), upgrade the Helm release in `${NAMESPACE}`, and restart `backend` and `frontend` so your running environment immediately picks up the new AI capabilities:

```bash
source ~/GitHub/gdc-dev-env.sh
cd ~/GitHub/${APP_NAME}

# 1. Build & Push AI-Enabled Backend and Frontend Images
docker build -t "${REGISTRY_HOST}/${APP_NAME}-backend:latest" src/backend
docker push "${REGISTRY_HOST}/${APP_NAME}-backend:latest"

docker build -t "${REGISTRY_HOST}/${APP_NAME}-frontend:latest" src/frontend
docker push "${REGISTRY_HOST}/${APP_NAME}-frontend:latest"

# 2. Upgrade the Helm Release in ${NAMESPACE} and Roll Out New Pods
helm upgrade --install "${APP_NAME}" ./chart \
  --namespace "${NAMESPACE}" \
  --set global.projectId="${PROJECT_ID}" \
  --set global.namespace="${NAMESPACE}" \
  --set global.registry="${REGISTRY_HOST}" \
  --set gdc.enabled=false \
  --set apps.enabled=true \
  --set apps.serviceAccountName="${APP_NAME}-sa" \
  --set apps.openaiApiBaseUrl="http://gemma-gateway.gemma-inference.svc.cluster.local/v1" \
  --set apps.s3Endpoint="" \
  --set apps.bucketName="${APP_NAME}-files-${PROJECT_ID}"

kubectl rollout restart deployment/backend deployment/frontend -n "${NAMESPACE}"
kubectl rollout status deployment/backend deployment/frontend -n "${NAMESPACE}" --timeout=120s

# 3. Ensure Port 8081 Gateway Tunnel is Active and Verify /api/ai/status Returns HTTP 200
curl -sf http://127.0.0.1:8081/api/ai/status >/dev/null || (
  pkill -f "while true.*8081" || true
  pkill -f "port-forward.*8081" || true
  sleep 1
  nohup bash -c "while true; do kubectl port-forward --address 0.0.0.0 -n ${NAMESPACE} svc/gdc-gateway-tunnel 8081:80 >> /tmp/pf-8081.log 2>&1; sleep 1; done" >/dev/null 2>&1 &
  sleep 3
)

echo "=== Live AI Gateway & Application Status (/api/ai/status) ==="
curl -s http://127.0.0.1:8081/api/ai/status | python3 -m json.tool
```

---

## 8. Step 6: Run the Automated AI Unit Tests, 8-Check Live AI + Keycloak Integration Suite & Promotion Gates 1–3

Before packaging for production, run this single verification block to validate:
1. **`[Check 0]` Unit, Functional, AI Gateway Mock & RBAC Test Suite (`src/backend/test_main.py` — 7 tests using `unittest.IsolatedAsyncioTestCase`)**: Tests `/health`, `/ai/status`, `401` invalid JWT, RS256 claim mapping, `alice` (`user`) `UNCLASSIFIED` AI briefing generation, `403` RBAC blocking `alice` from `SECRET` AI threat assessments, and `charlie` (`admin`) `SECRET` AI threat assessment with file attachment upload.
2. **`[Checks 1-8]` Live 8-Check Keycloak OIDC + Gemma 4 AI Gateway + GCS + PostgreSQL Integration Suite (`scripts/test-ai-app-integration.py`)**: Tests live OIDC discovery (`[AI-01]`), backend health (`[AI-02]`), `/api/ai/status` Gemma 4 Gateway readiness (`[AI-03]`), `401` unauthenticated/forged token rejection (`[AI-04]`), `alice` RS256 token + `UNCLASSIFIED` AI briefing via `/api/analyze` (`[AI-05]`), `alice` `403` RBAC rejection on `SECRET` `/api/analyze` (`[AI-06]`), `charlie` Admin `SECRET` `/api/analyze` with live GCS telemetry upload (`[AI-07]`), and PostgreSQL audit log readback confirming the `[AI-BRIEFING | ...]` record persisted (`[AI-08]`).
3. **`[Gates 1-3]` Trivy `HIGH,CRITICAL` Scan, 4-Layer `gdc-iac-org` Chart + OPA `policy/security.rego` Validation, and Air-Gap Release Bundle Packaging**.

```bash
source ~/GitHub/gdc-dev-env.sh
cd ~/GitHub/${APP_NAME}

echo "=== [Check 0] Automated AI Unit, Functional & RBAC Test Suite (src/backend/test_main.py) ==="
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/backend/test_main.py
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
import main


class TestAIMissionBackendUnitAndRBAC(unittest.IsolatedAsyncioTestCase):
    def test_01_health_endpoint_includes_ai_gateway_url(self):
        body = main.health()
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["service"], "mission-backend")
        self.assertIn("ai_gateway_url", body)

    @patch("main.requests.get")
    def test_02_ai_status_endpoint_probes_gemma_gateway(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        status = main.ai_status()
        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["ai_gateway_reachable"])

    async def test_03_forged_or_invalid_jwt_rejected_401(self):
        with self.assertRaises(HTTPException) as ctx:
            await main.get_current_user(credentials="forged.invalid.jwt")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("main.jwt.decode")
    @patch("main.jwks_client.get_signing_key_from_jwt")
    async def test_04_valid_keycloak_rs256_jwt_extracts_user_and_roles(self, mock_jwks, mock_decode):
        mock_key = MagicMock()
        mock_key.key = "public-rs256-key"
        mock_jwks.return_value = mock_key
        mock_decode.return_value = {"preferred_username": "alice", "roles": ["user"]}
        user = await main.get_current_user(credentials="valid.rs256.jwt")
        self.assertEqual(user, {"username": "alice", "roles": ["user"]})

    @patch("main.psycopg2.connect")
    @patch("main.requests.post")
    async def test_05_user_can_run_unclassified_ai_analysis_tier1(self, mock_post, mock_connect):
        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.headers = {"X-Model-Used": "gemma4:26b", "X-Model-Tier": "MoE"}
        mock_llm_resp.json.return_value = {
            "model": "gemma4:26b",
            "choices": [{"message": {"content": "• Operational Summary: Sector 4 normal."}}],
        }
        mock_post.return_value = mock_llm_resp

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [101]
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_connect.return_value = mock_conn

        alice = {"username": "alice", "roles": ["user"]}
        res = await main.analyze_mission_intelligence(
            classification="UNCLASSIFIED",
            prompt="Analyze Sector 4 perimeter sensors",
            attachment=None,
            user=alice,
        )
        self.assertEqual(res["status"], "analyzed")
        self.assertEqual(res["ai_engine"], "live-gemma-gateway")
        self.assertEqual(res["model_used"], "gemma4:26b")
        self.assertEqual(res["model_tier"], "MoE")

    async def test_06_standard_user_blocked_from_secret_ai_analysis_403(self):
        alice = {"username": "alice", "roles": ["user"]}
        with self.assertRaises(HTTPException) as ctx:
            await main.analyze_mission_intelligence(
                classification="SECRET",
                prompt="Unauthorized SECRET threat correlation",
                attachment=None,
                user=alice,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("main.upload_object_bytes", return_value="gs://test-bucket/charlie/ai-rf-log.txt")
    @patch("main.psycopg2.connect")
    @patch("main.requests.post")
    async def test_07_admin_allowed_secret_ai_analysis_tier2_with_attachment(
        self, mock_post, mock_connect, mock_upload
    ):
        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.headers = {"X-Model-Used": "gemma4:31b", "X-Model-Tier": "Dense"}
        mock_llm_resp.json.return_value = {
            "model": "gemma4:31b",
            "choices": [{"message": {"content": "• Classified Assessment: RF jamming mitigated."}}],
        }
        mock_post.return_value = mock_llm_resp

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [202]
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_connect.return_value = mock_conn

        mock_file = MagicMock()
        mock_file.filename = "rf-log.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=b"RF_BAND=14.25GHz")

        charlie = {"username": "charlie", "roles": ["admin", "user"]}
        res = await main.analyze_mission_intelligence(
            classification="SECRET",
            prompt="Correlate Grid 9B RF bursts",
            attachment=mock_file,
            user=charlie,
        )
        self.assertEqual(res["id"], 202)
        self.assertEqual(res["model_used"], "gemma4:31b")
        self.assertEqual(res["model_tier"], "Dense")
        self.assertEqual(res["s3_object_key"], "gs://test-bucket/charlie/ai-rf-log.txt")


if __name__ == "__main__":
    unittest.main()
EOF

docker run --rm -v "$HOME/GitHub/${APP_NAME}/src/backend/test_main.py:/app/test_main.py:ro" \
  --entrypoint python3 "${REGISTRY_HOST}/${APP_NAME}-backend:latest" \
  -m unittest discover -s /app -p "test_*.py" -v

echo "=== [Checks 1-8] Automated 8-Check Live Keycloak OIDC + Gemma 4 AI Gateway Integration Suite ==="
cat << 'EOF' > ~/GitHub/${APP_NAME}/scripts/test-ai-app-integration.py
#!/usr/bin/env python3
import base64, json, os, sys, urllib.error, urllib.parse, urllib.request, uuid

BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
REALM = os.getenv("KEYCLOAK_REALM", "gdc-app-realm")
CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "mission-frontend")

def http_request(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")

def get_keycloak_token(username, password):
    token_url = f"{BASE_URL}/auth/realms/{REALM}/protocol/openid-connect/token"
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "grant_type": "password", "username": username, "password": password
    }).encode("utf-8")
    status, text = http_request(token_url, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}, data=body)
    if status != 200:
        raise RuntimeError(f"Keycloak token grant failed for {username} (HTTP {status}): {text}")
    return json.loads(text)["access_token"]

def build_multipart(fields, file_field=None):
    boundary = f"----GDCAIBoundary{uuid.uuid4().hex}"
    lines = []
    for k, v in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    if file_field:
        field_name, filename, content = file_field
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n'.encode())
        lines.append(content + b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(lines)

print("================================================================================")
print(f"🧠🔐 SOVEREIGN AI + KEYCLOAK OIDC INTEGRATION TEST SUITE ({BASE_URL})")
print("================================================================================")

# [AI-01] Keycloak OIDC Discovery & JWKS
disc_status, _ = http_request(f"{BASE_URL}/auth/realms/{REALM}/.well-known/openid-configuration")
jwks_status, jwks_body = http_request(f"{BASE_URL}/auth/realms/{REALM}/protocol/openid-connect/certs")
assert disc_status == 200 and jwks_status == 200 and "keys" in json.loads(jwks_body)
print("[AI-01] Keycloak OIDC Discovery & RS256 JWKS Reachable (/auth) ......... [PASS]")

# [AI-02] Backend Health
h_status, h_body = http_request(f"{BASE_URL}/api/health")
assert h_status == 200 and json.loads(h_body).get("status") == "healthy"
print("[AI-02] AI Backend Health Endpoint Reachable (/api/health) ............. [PASS]")

# [AI-03] AI Gateway Status Probe (/api/ai/status)
ai_status_code, ai_status_body = http_request(f"{BASE_URL}/api/ai/status")
ai_info = json.loads(ai_status_body)
assert ai_status_code == 200 and ai_info.get("status") == "ready"
print(f"[AI-03] Gemma 4 Gateway Status (/api/ai/status: reachable={ai_info.get('ai_gateway_reachable')}) [PASS]")

# [AI-04] Zero-Trust Unauthenticated & Forged Token Rejection (HTTP 401)
u_status, _ = http_request(f"{BASE_URL}/api/analyze", method="POST")
f_status, _ = http_request(f"{BASE_URL}/api/analyze", method="POST", headers={"Authorization": "Bearer forged.jwt.token"})
assert u_status == 401 and f_status == 401
print("[AI-04] Zero-Trust Unauthenticated & Forged JWT Rejected (HTTP 401) .... [PASS]")

# [AI-05] Alice ('user') UNCLASSIFIED AI Tactical Briefing (/api/analyze -> Tier 1 MoE)
alice_token = get_keycloak_token("alice", "password")
ctype_a, body_a = build_multipart({
    "classification": "UNCLASSIFIED",
    "prompt": "Summarize Sector 4 acoustic and thermal perimeter sensor status."
})
a_status, a_text = http_request(f"{BASE_URL}/api/analyze", method="POST", headers={"Authorization": f"Bearer {alice_token}", "Content-Type": ctype_a}, data=body_a)
assert a_status == 200, f"Expected 200 for alice UNCLASSIFIED /api/analyze, got {a_status}: {a_text}"
a_data = json.loads(a_text)
assert len(a_data.get("ai_briefing", "")) > 10
print(f"[AI-05] 'alice' UNCLASSIFIED AI Briefing ({a_data.get('ai_engine')} | {a_data.get('model_used')}) [PASS]")

# [AI-06] Alice ('user') Blocked from SECRET AI Threat Assessment (HTTP 403)
ctype_s, body_s = build_multipart({
    "classification": "SECRET",
    "prompt": "Attempted unauthorized SECRET AI threat correlation."
})
s_status, _ = http_request(f"{BASE_URL}/api/analyze", method="POST", headers={"Authorization": f"Bearer {alice_token}", "Content-Type": ctype_s}, data=body_s)
assert s_status == 403, f"Expected 403 for alice SECRET /api/analyze, got {s_status}"
print("[AI-06] Least-Privilege RBAC ('alice' SECRET /api/analyze -> HTTP 403) . [PASS]")

# [AI-07] Charlie ('admin') SECRET AI Threat Assessment + Live GCS File Upload
charlie_token = get_keycloak_token("charlie", "password")
ctype_c, body_c = build_multipart(
    {
        "classification": "SECRET",
        "prompt": "Correlate Grid 9B RF bursts with uplink latency spikes and provide counter-EW actions."
    },
    file_field=("attachment", "grid9b-rf-telemetry.log", b"RF_BAND=14.25GHz HOP_RATE=1200 SNR_DB=19.8"),
)
c_status, c_text = http_request(f"{BASE_URL}/api/analyze", method="POST", headers={"Authorization": f"Bearer {charlie_token}", "Content-Type": ctype_c}, data=body_c)
assert c_status == 200, f"Expected 200 for charlie SECRET /api/analyze, got {c_status}: {c_text}"
c_data = json.loads(c_text)
assert c_data.get("s3_object_key", "").startswith(("gs://", "s3://"))
print(f"[AI-07] 'charlie' Admin SECRET AI Briefing + GCS Upload ({c_data['s3_object_key']}) [PASS]")

# [AI-08] PostgreSQL Audit Trail Readback (/api/records)
r_status, r_text = http_request(f"{BASE_URL}/api/records", headers={"Authorization": f"Bearer {charlie_token}"})
records = json.loads(r_text).get("records", [])
assert r_status == 200 and any("[AI-BRIEFING |" in r.get("summary", "") for r in records)
print(f"[AI-08] PostgreSQL AI Briefing Audit Persistence Verified ({len(records)} records) . [PASS]")
print("================================================================================")
print("✅ ALL 8 SOVEREIGN AI & KEYCLOAK OIDC INTEGRATION TESTS PASSED (8/8)")
print("================================================================================")
EOF
chmod +x ~/GitHub/${APP_NAME}/scripts/test-ai-app-integration.py
~/GitHub/${APP_NAME}/scripts/test-ai-app-integration.py

echo "=== [Gate 1] Trivy Image & Filesystem Vulnerability/Misconfig Scans (HIGH,CRITICAL) ==="
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOME/.cache/trivy:/root/.cache/" aquasec/trivy:latest image \
  --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "${REGISTRY_HOST}/${APP_NAME}-backend:latest"

docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOME/.cache/trivy:/root/.cache/" aquasec/trivy:latest image \
  --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "${REGISTRY_HOST}/${APP_NAME}-frontend:latest"

docker run --rm -v "$HOME/GitHub/${APP_NAME}:/workspace:ro" \
  -v "$HOME/.cache/trivy:/root/.cache/" aquasec/trivy:latest fs \
  --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --exit-code 1 \
  --skip-dirs /workspace/manifests/gcp --skip-dirs /workspace/dist /workspace

echo "=== [Gate 2] 4-Layer Offline Chart & OPA Rego Validation (gdc-iac-org/policy/security.rego) ==="
helm lint ./chart
helm unittest ./chart
helm template "${APP_NAME}" ./chart --set gdc.enabled=false --set apps.enabled=true \
  | kubeconform -strict -ignore-missing-schemas -skip DBCluster,Bucket,Gateway,HTTPRoute -summary
helm template "${APP_NAME}" ./chart --set gdc.enabled=true --set apps.enabled=true \
  | kubeconform -strict -ignore-missing-schemas -skip DBCluster,Bucket,Gateway,HTTPRoute -summary
helm template "${APP_NAME}" ./chart --set gdc.enabled=false --set apps.enabled=true \
  | conftest test - --policy ~/GitHub/gdc-iac-org/policy/security.rego

echo "=== [Gate 3] Build Air-Gap Release Bundle (Stripping manifests/gcp/) ==="
~/GitHub/${APP_NAME}/scripts/package-airgap-release.sh
! tar -tzf "dist/${APP_NAME}-gdc-airgap-bundle.tar.gz" | grep -q "manifests/gcp" && \
  echo "✅ ALL AI APPLICATION TESTS & PROMOTION GATES PASSED!"
```

---

## 9. Interactive Browser Walkthrough (Port `8081` Web Preview)

Open your Cloud Workstation Web Preview on **Port `8081`** to try the AI Mission Portal interactively:
1. **Verify Environment Readiness Banner:** At the top of the portal, confirm the badge shows **`Gemma 4 Gateway: CONNECTED`** and **`Storage: GCP-GCS (p15-sovereign-mission-app-files-...)`**.
2. **Sign In via Keycloak OIDC:** Click **🔑 Sign In with Keycloak OIDC** and log in as **`charlie` / `password`** (`admin, user`) or **`alice` / `password`** (`user`).
3. **Run Pre-Canned AI Scenarios:**
   - Click **⚡ Scenario 1: Perimeter Sensor Anomaly** $\rightarrow$ click **🧠 Generate Sovereign AI Briefing & Persist**. Observe the AI assessment card showing the model used (`gemma4:26b` MoE), latency, uploaded GCS artifact (`gs://.../sector4-perimeter-sensors.log`), and the 3-bullet tactical assessment.
   - Click **🔒 Scenario 2: Multi-Vector Threat Correlation (`SECRET`)** $\rightarrow$ click **🧠 Generate Sovereign AI Briefing & Persist**.
     - If logged in as **`alice`** (`user`), observe the **HTTP 403 Zero-Trust RBAC block**.
     - If logged in as **`charlie`** (`admin`), observe the **`SECRET` Tier 2 Dense (`gemma4:31b`)** AI threat correlation and persisted PostgreSQL audit record!
