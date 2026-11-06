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

# Greenfield Developer Guide: Building, Testing & Promoting GDC-ag Solutions from Scratch Using Only `gdc-iac-org`

> **Document ID:** `GUIDE-GDC-GREENFIELD-CLOUD-WORKSTATION-TO-PRODUCTION`  
> **Target Audience:** Independent Application & Solution Developers building **customer-specific applications from scratch in their own Git repository** (`~/GitHub/my-gdc-solution`)  
> **Development Language Assumption:** Assumes **Python** (`FastAPI`) for application development; other languages (Go, Java, Node.js/TypeScript, C#, Rust) will require adaptations where needed  
> **External Repository Dependency:** Public [`gdc-iac/gdc-iac-org`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints) repository **only** (consumed strictly as a read-only reference blueprint library, OPA security policy baseline, and landing zone foundation)  
> **Allowed Developer Toolchain:** `docker`, `helm` (`helmfile`), and `kubectl` for day-to-day build/deploy/test — with **deliberate `gcloud` exceptions** for enabling/configuring **Google Artifact Registry (`-docker.pkg.dev`)**, provisioning **actual Google Cloud Storage (`gs://...`)** + GKE Workload Identity, and optional self-service GKE cluster creation  
> **Mandatory Security Baseline:** Every application **must** integrate with **Keycloak OIDC (`p12-keycloak`)** as a minimum requirement  
> **Companion AI Tutorial:** Once your environment is set up using this guide, see [Building an AI-Enabled Application on Your GDC-ag Cloud Workstation Environment](./building_ai_enabled_gdc_application_tutorial.md) for a pre-canned AI application walkthrough, local desktop IDE (`Antigravity` / `VS Code`) code transfer workflows, and Cloud Workstation GCP/GDC developer tools.

---

## 1. Overview & Architecture for Greenfield Developers

This guide provides a self-contained blueprint for developers building new customer-specific applications targeted at **Google Distributed Cloud Air-Gapped (`GDC-ag`)** from scratch in their own Git repository, using a **Google Cloud Workstation** connected to a **GKE Stepping-Stone cluster** (with or without GPUs) and referencing **only** the public [`gdc-iac/gdc-iac-org`](https://github.com/gdc-iac/gdc-iac-org) repository.

> [!NOTE]
> **Application Language Assumption (`Python`):**  
> This guide assumes **Python** (`FastAPI`) will be the development language used to create applications—including the reference Keycloak OIDC RS256 JWT validation middleware, PostgreSQL (`psycopg2`) client, and Dual-Mode Google Cloud Storage / S3 (`google-cloud-storage` + `boto3`) adapter in **Section 5**. Developers building applications in other languages (such as Go, Java, Node.js/TypeScript, C#, or Rust) can use the same containerization, Helm chart, Keycloak OIDC, PostgreSQL, Object Storage, and Gateway API contracts, but will need to make language-specific adaptations where needed (such as OIDC/JWKS libraries, database drivers, GCS/S3 SDKs, and rootless base container images).

### 1.1. Why This Guide Includes Inline GCP Emulation Manifests, Artifact Registry & Actual Cloud Storage (`GCS`)

Because the public [`gdc-iac/gdc-iac-org/tree/main/blueprints`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints) repository operates strictly as a reusable production reference library, it intentionally excludes GCP-specific emulation manifests (`manifests/gcp/`), and **customer-specific applications are never pushed into `gdc-iac-org`**. When starting from scratch in your own customer repository (`~/GitHub/my-gdc-solution`), you maintain two layers inside your own repo:
1. **A local `manifests/gcp/` + Artifact Registry + Cloud Storage staging layer** so you can push and pull container images via **Google Artifact Registry (`-docker.pkg.dev`)**, emulate GDC Managed PostgreSQL (`DBCluster`), GDC Hardware Load Balancers (`Gateway API`), and **Keycloak OIDC (`p12-keycloak`)** via **`kubectl`** and **`helm`**, and use **actual Google Cloud Storage (`gs://...`)** with **GKE Workload Identity** for object storage (aligning with the `p6-resilient-rag-agent` pattern in [`gdc-iac-org/blueprints/patterns/`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints/patterns)).
2. **A production `manifests/apps/`, `manifests/gdc/`, and `chart/` structure inside your own repository** that aligns with the architectural and security standards of [`gdc-iac-org/blueprints`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints) (`policy/security.rego`, `values.schema.json`, and Stage 2 vs. Stage 5 separation) so your customer application can be packaged into a standalone air-gap bundle (`dist/${APP_NAME}-gdc-airgap-bundle.tar.gz`) and deployed into your customer's `GDC-ag` environment.

> [!IMPORTANT]
> **The GDC-ag Toolchain Rule (`docker`, `helm`, `kubectl`) & The Artifact Registry / Cloud Storage Exceptions:**  
> On physical `GDC-ag` racks, the public-cloud `gcloud` CLI does not exist—Application Developers and Application Operators (**AOs**) deploy and manage workloads exclusively via **`docker`**, **`helm`** (`helmfile`), and **`kubectl`**.  
> 
> To mirror `GDC-ag` as closely as possible on your Cloud Workstation:
> - **All application builds, database emulation, Keycloak OIDC, Gateway API load balancing, and LLM deployments** use strictly **`docker`**, **`helm`**, and **`kubectl`**.
> - **Deliberate Exception 1 — Google Artifact Registry (`Section 2.2`):** To push images from your Cloud Workstation (`docker push`) and pull them onto your GKE cluster nodes (`imagePull`), the **Artifact Registry API (`artifactregistry.googleapis.com`)** and a Docker repository (`${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}`) must be enabled, authenticated (`gcloud auth configure-docker`), and granted GKE node pull permissions (`roles/artifactregistry.reader`). On `GDC-ag`, this maps directly to **GDC Managed Harbor (`harbor.infra.gdc.local`)** via `{{ .Values.global.registry }}`.
> - **Deliberate Exception 2 — Actual GCP Cloud Storage (`gs://...`, `Section 3.2`):** Because GCP Cloud Storage buckets and GKE Workload Identity IAM bindings cannot be created via plain `kubectl` (without Config Connector), **Section 3.2** uses `gcloud storage` and `gcloud iam` once to provision a real GCS bucket (`gs://${APP_NAME}-files-${PROJECT_ID}`) and bind it to your Kubernetes `ServiceAccount` (`iam.gke.io/gcp-service-account`). Your Python backend uses a **Dual-Mode Storage Adapter (`google-cloud-storage` + `boto3`)** that talks to real **Google Cloud Storage** on GKE and automatically switches to **GDC S3 Object Storage (`https://objectstorage.gdc.goog`)** on `GDC-ag` with **zero code changes**!

```mermaid
flowchart LR
    subgraph REPOS["Cloud Workstation ~/GitHub Workspace"]
        OWN["Your Customer Repo:\n~/GitHub/my-gdc-solution\n(manifests/gcp, apps, gdc + chart/)"]
        PUB["Read-Only Reference Repo:\n~/GitHub/gdc-iac-org\n(blueprints/, policy/, foundations/)"]
    end

    subgraph AR["Google Artifact Registry"]
        REG["${AR_REGION}-docker.pkg.dev/\n${PROJECT_ID}/${AR_REPO_NAME}\n(docker push & GKE node imagePull)"]
    end

    subgraph GKE["GKE Stepping-Stone Cluster + GCP Cloud Storage"]
        GW["Gateway API (gke-l7-rilb)\n+ gdc-gateway-tunnel (socat)"]
        KC["Keycloak OIDC (p12-keycloak)\n+ ConfigMap Realm Import"]
        PG["Emulated PostgreSQL + pgvector\n(StatefulSet + Secret Contract)"]
        GCS["Actual GCP Cloud Storage (gs://)\n+ GKE Workload Identity\n(Dual-Mode GCS <-> S3 Adapter)"]
        LLM["Optional GPU LLM Serving\n(gdc_gemma_gw [Recommended]\nor p5-hybrid-llm-gateway)"]
        APP["Your Customer Application\n(Frontend SPA + FastAPI Backend)"]
    end

    subgraph PROD["Customer GDC-ag Promotion (In Your Own Repo)"]
        VAL["1. Trivy Scan & 4-Layer\nValidation (policy/security.rego)"]
        STG["2. Package dist/ Air-Gap Bundle\n(Stripping manifests/gcp/)"]
        HF["3. Ingest into Customer Harbor &\nDeploy on GDC-ag (Stage 2 -> Stage 5)"]
    end

    OWN -- "docker build & push" --> REG
    REG -- "imagePull" --> GKE
    OWN -- "helm & kubectl" --> GKE
    PUB -. "Read-only reference: p12-keycloak,\ngdc_gemma_gw / p5 & security.rego" .-> GKE
    GW --> KC
    GW --> APP
    APP --> PG
    APP --> GCS
    APP --> LLM
    GKE ==> PROD
    VAL --> STG --> HF
```

### 1.2. Emulation-to-Production Contract Matrix

By adhering to the contracts below, your application code (`src/`) runs **unchanged** in both your Cloud Workstation GKE cluster and physical `GDC-ag` production:

| Platform Capability | Cloud Workstation + GKE Staging (`manifests/gcp/`) | `GDC-ag` Production (`gdc-iac-org` Stage 2 & Stage 5) | Zero-Code-Change Contract |
| :--- | :--- | :--- | :--- |
| **Developer Toolchain** | **`docker`**, **`helm`**, **`kubectl`** *(plus one-time `gcloud` for Artifact Registry, GCS bucket / Workload Identity, or optional cluster setup)* | **`docker`**, **`helm`** / **`helmfile`**, **`kubectl`** | Zero `gcloud` calls inside application containers, Helm charts, or runtime scripts. |
| **OCI Container Registry (Push & Pull)** | **Google Artifact Registry** (`${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}`) — Workstation pushes via `docker push`; GKE nodes pull via `roles/artifactregistry.reader` | **GDC Managed Harbor OCI Registry** (`harbor.infra.gdc.local/gdc-iac`) — Populated via `ingest-airgap-bundle.sh` & `mirror_images.py` | Parameterized `{{ .Values.global.registry }}` in Helm `values.yaml` (or `./configure-blueprints.sh -r ${REGISTRY_HOST}`). |
| **Compute (CPU & GPU)** | GKE CPU nodes (`app=client`) + optional GPU nodes (`nvidia.com/gpu`) | GDC User Cluster CPU nodes + `gpu-moe` / `gpu-dense` H100 pools | Standard K8s `resources.limits["nvidia.com/gpu"]` and parameterized `nodeSelector`. |
| **Authentication (Mandatory)** | In-cluster **Keycloak OIDC** (`quay.io/keycloak/keycloak:24.0.4`) with `ConfigMap` Realm Import | **HA Keycloak OIDC (`p12-keycloak`)** federated with Enterprise AD/LDAP & PKI | Frontend uses OIDC Auth Code + PKCE (`S256`); Backend verifies RS256 JWTs via internal KubeDNS (`http://keycloak-svc:8080/auth/.../certs`). |
| **PostgreSQL + `pgvector`** | In-cluster **`pgvector/pgvector:pg16` `StatefulSet`** | Zonal Managed **`DBCluster` CRD** (`postgresql.dbadmin.gdc.goog/v1`, `ZONAL_HA`) | Both expose `Secret/<app>-db-credentials` (`connection_string`, `username`, `password`, `db_name`). |
| **Object Storage (RAG / Files)** | **Actual Google Cloud Storage (`gs://<app>-files-${PROJECT_ID}`)** via **GKE Workload Identity** (`iam.gke.io/gcp-service-account`) | Zonal Managed **`Bucket` CRD** (`buckets.object.gdc.goog/v1` at `https://objectstorage.gdc.goog`) | **Dual-Mode Storage Adapter (`google-cloud-storage` + `boto3`):** Uses native GCS via Workload Identity when `S3_ENDPOINT` is empty on GKE, and automatically uses `boto3` S3 v4 when `S3_ENDPOINT="https://objectstorage.gdc.goog"` is set on `GDC-ag`. |
| **Load Balancing & Routing** | **Kubernetes Gateway API** (`Gateway/gdc-platform-gateway`, `HTTPRoute`) + `gdc-gateway-tunnel` (`socat` L4 bridge) | **Kubernetes Gateway API** (`gateway.networking.k8s.io/v1` on GDC Hardware Load Balancers) | Single-origin `HTTPRoute` mapping `/auth` $\rightarrow$ Keycloak, `/api` $\rightarrow$ Backend, and `/` $\rightarrow$ Frontend. |

---

## 2. Step 1: Clone `gdc-iac-org`, Configure Artifact Registry & Scaffold Your Solution Repository

Open your **Google Cloud Workstation** terminal. All repositories live under `~/GitHub`.

### 2.1. Clone the Public `gdc-iac-org` Repository & Initialize Your Repo

```bash
mkdir -p ~/GitHub && cd ~/GitHub

# 1. Clone (or sync) the public gdc-iac-org blueprint & foundations library
if [ -d ~/GitHub/gdc-iac-org/.git ]; then
  git -C ~/GitHub/gdc-iac-org branch "backup-local-main-$(date +%s)" 2>/dev/null || true
  git -C ~/GitHub/gdc-iac-org fetch origin main
  git -C ~/GitHub/gdc-iac-org checkout main
  git -C ~/GitHub/gdc-iac-org reset --hard origin/main
else
  git clone https://github.com/gdc-iac/gdc-iac-org.git ~/GitHub/gdc-iac-org
fi

# 2. Create and initialize your own solution repository from scratch
export APP_NAME="p15-sovereign-mission-app"
mkdir -p ~/GitHub/${APP_NAME}/{src/backend,src/frontend,manifests/{apps,gdc,gcp},chart/{templates/{apps,gdc},tests},scripts}
cd ~/GitHub/${APP_NAME}
git init
```

### 2.2. Enable, Create & Authenticate Google Artifact Registry (For Pushing & Pulling Container Images)

Before building and deploying containers, **Google Artifact Registry (`artifactregistry.googleapis.com`)** must be enabled and available in your GCP project, your Cloud Workstation `docker` daemon must be authenticated to push images (`docker push`), and your GKE cluster nodes must have IAM permissions (`roles/artifactregistry.reader`) to pull images (`imagePull`):

```bash
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "${PROJECT_ID:-gdc-tenant-project}")
export AR_REGION="${AR_REGION:-us-east4}"
export AR_REPO_NAME="${AR_REPO_NAME:-blueprint-images}"
export REGISTRY_HOST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}"

# 1. Enable the Artifact Registry API in your GCP project
gcloud services enable artifactregistry.googleapis.com --project="${PROJECT_ID}"

# 2. Create the Docker-format Artifact Registry repository if it does not already exist
gcloud artifacts repositories describe "${AR_REPO_NAME}" \
  --location="${AR_REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${AR_REPO_NAME}" \
  --repository-format=docker \
  --location="${AR_REGION}" \
  --description="GDC-ag Stepping-Stone Container Registry" \
  --project="${PROJECT_ID}"

# 3. Configure Docker on your Cloud Workstation to authenticate with Artifact Registry (for docker push/pull)
gcloud auth configure-docker "${AR_REGION}-docker.pkg.dev" --quiet

# 4. Ensure GKE cluster nodes have IAM permission to pull images from Artifact Registry (prevents ImagePullBackOff)
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
gcloud artifacts repositories add-iam-policy-binding "${AR_REPO_NAME}" \
  --location="${AR_REGION}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader" --quiet >/dev/null

# 5. Save your Developer Environment Config (~/GitHub/gdc-dev-env.sh)
cat <<EOF > ~/GitHub/gdc-dev-env.sh
# ============================================================================
# Greenfield GDC-ag Developer Environment Variables
# ============================================================================
export APP_NAME="${APP_NAME:-p15-sovereign-mission-app}"
export PROJECT_ID="${PROJECT_ID}"
export NAMESPACE="${NAMESPACE:-mission-app}"
export AR_REGION="${AR_REGION}"
export AR_REPO_NAME="${AR_REPO_NAME}"
export REGISTRY_HOST="${AR_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}"

echo "=================================================================="
echo "Kube Context      : \$(kubectl config current-context 2>/dev/null || echo 'not-set')"
echo "Solution Repo     : ~/GitHub/\${APP_NAME}"
echo "Namespace         : \${NAMESPACE}"
echo "Artifact Registry : \${REGISTRY_HOST}"
echo "=================================================================="
EOF

source ~/GitHub/gdc-dev-env.sh
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
```

> [!TIP]
> **Sharing One GKE Cluster Across a Team of Developers?**  
> Multiple developers (each on their own Cloud Workstation) can safely share a **single GKE Stepping-Stone cluster** and Artifact Registry. Prefix `NAMESPACE` and `APP_NAME` with your developer identifier before running Step 2.2 (for example, `export DEV_ID="alice"`, `export NAMESPACE="dev-${DEV_ID}"`, and `export APP_NAME="${DEV_ID}-mission-app"`—or have your Platform Administrator pre-configure this automatically via [Appendix A.6](#a6-option-onboarding-a-team-of-developers-sharing-one-gke-cluster)). See **[Section 2.5](#25-dedicated-cluster-vs-shared-team-gke-cluster-key-workflow-differences)** below for all operational differences—including **`kubectl port-forward`**, **Gateway API VIPs**, **image tagging**, and **shared GPU usage**.

### 2.3. Inspect Cluster Hardware Profile (`CPU-Only` vs. `GPU-Enabled`) via `kubectl`

```bash
# Check node pools and allocatable NVIDIA GPUs using pure kubectl
kubectl get nodes -o custom-columns="NODE:.metadata.name,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,GPU_TYPE:.metadata.labels.cloud\.google\.com/gke-accelerator,GPUS:.status.allocatable.nvidia\.com/gpu"
```

- **CPU-Only GKE Cluster (`0` GPUs):** Supports all web, API, PostgreSQL `pgvector`, Google Cloud Storage (`gs://`), Kafka, Vault, and Keycloak OIDC workloads.
- **GPU-Enabled GKE Cluster (`nvidia-l4` or `nvidia-tesla-a100`):** Also supports deploying local LLM inference—choosing between the **Gemma 4 Dedicated Inference Gateway (`gdc_gemma_gw`, Recommended)** or the legacy **Pattern 5 Hybrid LLM Gateway (`p5-hybrid-llm-gateway`)** from `~/GitHub/gdc-iac-org/blueprints/` (decision criteria and commands in **Section 3.4** below).

### 2.4. Alternative: Provision Your Own GKE Cluster & Artifact Registry (If Permitted by GCP IAM)

If a Platform Administrator has **not** pre-provisioned a GKE cluster for your project—and your GCP account has IAM permissions to create GKE clusters, VPC subnets, and Artifact Registry repositories (`roles/container.admin`, `roles/artifactregistry.admin`, `roles/compute.networkAdmin`)—you can provision your own CPU-only or GPU-enabled GKE Stepping-Stone cluster directly from your Cloud Workstation terminal:

<details>
<summary><b>Option A: Create Your Own CPU-Only GKE Stepping-Stone Cluster + Artifact Registry</b></summary>

```bash
export PROJECT_ID=$(gcloud config get-value project)
export CLUSTER_NAME="${CLUSTER_NAME:-gdc-stepping-stone}"
export REGION="${REGION:-us-east4}"
export ZONE="${ZONE:-us-east4-a}"
export AR_REPO_NAME="${AR_REPO_NAME:-blueprint-images}"

# 1. Enable required GCP APIs & create Artifact Registry Docker repository
gcloud services enable container.googleapis.com artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com iamcredentials.googleapis.com --project="${PROJECT_ID}"

gcloud artifacts repositories describe "${AR_REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${AR_REPO_NAME}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}"

# 2. Create CPU-Only GKE cluster with Workload Identity, Dataplane V2, and Gateway API enabled
if ! gcloud container clusters describe "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud container clusters create "${CLUSTER_NAME}" \
    --project "${PROJECT_ID}" \
    --zone "${ZONE}" \
    --release-channel "regular" \
    --enable-dataplane-v2 \
    --gateway-api=standard \
    --workload-pool "${PROJECT_ID}.svc.id.goog" \
    --machine-type "e2-standard-4" \
    --num-nodes 2 \
    --disk-size=100 \
    --node-labels="app=client"
fi

# 3. Create Regional Managed Proxy subnet & firewall rule required for GKE Gateway API (gke-l7-rilb)
if [ -z "$(gcloud compute networks subnets list --filter="region:${REGION} AND purpose:REGIONAL_MANAGED_PROXY" --format="value(name)" --project="${PROJECT_ID}")" ]; then
  gcloud compute networks subnets create "gke-gateway-proxy-${REGION}" \
    --purpose=REGIONAL_MANAGED_PROXY \
    --role=ACTIVE \
    --region="${REGION}" \
    --network=default \
    --range=172.16.2.0/23 \
    --project="${PROJECT_ID}"
fi

gcloud compute firewall-rules create allow-gateway-internal \
  --network=default --direction=INGRESS --priority=1000 --action=ALLOW \
  --rules=tcp:80,tcp:443,tcp:8000,tcp:8080,tcp:8081 \
  --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
  --project="${PROJECT_ID}" 2>/dev/null || true

# 4. Bind kubectl & Docker credentials and re-source ~/GitHub/gdc-dev-env.sh
gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}"
source ~/GitHub/gdc-dev-env.sh
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
```
</details>

<details>
<summary><b>Option B: Create Your Own GPU-Enabled GKE Cluster (with Automatic Multi-Region Stockout Fallback)</b></summary>

Because GPU capacity (`nvidia-l4`, `nvidia-tesla-a100`, `nvidia-rtx-6000`) can experience regional stockouts on GCP, this script automatically searches across `("us-east4" "us-west4" "europe-west4" "asia-southeast1" "us-central1")` until it finds available GPU capacity, then adds a standard CPU `client-pool` and Gateway API proxy subnet:

```bash
export PROJECT_ID=$(gcloud config get-value project)
export CLUSTER_NAME="${CLUSTER_NAME:-gdc-gpu-stepping-stone}"
export AR_REPO_NAME="${AR_REPO_NAME:-blueprint-images}"

gcloud services enable container.googleapis.com artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com iamcredentials.googleapis.com --project="${PROJECT_ID}"

GPU_CONFIGS=(
  "nvidia-l4:g2-standard-24:2"
  "nvidia-tesla-a100:a2-highgpu-1g:1"
  "nvidia-rtx-6000:g4-standard-24:1"
)
REGIONS=("us-east4" "us-west4" "europe-west4" "asia-southeast1" "us-central1")

EXISTING_ZONE=$(gcloud container clusters list --project "${PROJECT_ID}" \
  --filter="name=${CLUSTER_NAME} AND status=RUNNING" --format="value(location)" 2>/dev/null | head -n 1)

if [ -n "${EXISTING_ZONE}" ]; then
  export ZONE="${EXISTING_ZONE}"
  export REGION="${EXISTING_ZONE%-*}"
  echo "✅ Existing running GPU cluster detected in ${ZONE}"
else
  for REGION_CANDIDATE in "${REGIONS[@]}"; do
    for ZONE_CANDIDATE in $(gcloud compute zones list --project "${PROJECT_ID}" --filter="region:${REGION_CANDIDATE}" --format="value(name)"); do
      for CONFIG in "${GPU_CONFIGS[@]}"; do
        GPU_TYPE=$(echo "${CONFIG}" | cut -d: -f1)
        MACHINE=$(echo "${CONFIG}" | cut -d: -f2)
        COUNT=$(echo "${CONFIG}" | cut -d: -f3)
        echo "Trying ${ZONE_CANDIDATE} for ${MACHINE} (${COUNT}x ${GPU_TYPE})..."
        if gcloud container clusters create "${CLUSTER_NAME}" \
          --project "${PROJECT_ID}" --zone "${ZONE_CANDIDATE}" --release-channel "regular" \
          --machine-type "${MACHINE}" --accelerator "type=${GPU_TYPE},count=${COUNT},gpu-driver-version=LATEST" \
          --num-nodes 1 --enable-dataplane-v2 --gateway-api=standard \
          --workload-pool "${PROJECT_ID}.svc.id.goog" --disk-size=300 \
          --node-labels="app=vllm-26b" --quiet 2>/tmp/gke-err.log; then
          export ZONE="${ZONE_CANDIDATE}"
          export REGION="${ZONE_CANDIDATE%-*}"
          echo "✅ Provisioned GPU cluster in ${ZONE} (${MACHINE} with ${COUNT}x ${GPU_TYPE})"
          break 3
        else
          gcloud container clusters delete "${CLUSTER_NAME}" --zone "${ZONE_CANDIDATE}" --project "${PROJECT_ID}" --quiet >/dev/null 2>&1 || true
        fi
      done
    done
  done
fi

gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}"

# Add standard CPU node pool (client-pool) and Gateway API proxy-only subnet
gcloud container node-pools describe client-pool --cluster "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud container node-pools create client-pool --cluster "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}" \
  --machine-type "e2-standard-4" --num-nodes 2 --node-labels="app=client" --quiet

if [ -z "$(gcloud compute networks subnets list --filter="region:${REGION} AND purpose:REGIONAL_MANAGED_PROXY" --format="value(name)" --project="${PROJECT_ID}")" ]; then
  gcloud compute networks subnets create "gke-gateway-proxy-${REGION}" \
    --purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE --region="${REGION}" \
    --network=default --range=172.16.2.0/23 --project="${PROJECT_ID}" || true
fi

gcloud compute firewall-rules create allow-gateway-internal \
  --network=default --direction=INGRESS --priority=1000 --action=ALLOW \
  --rules=tcp:80,tcp:443,tcp:8000,tcp:8080,tcp:8081 \
  --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
  --project="${PROJECT_ID}" 2>/dev/null || true

gcloud artifacts repositories describe "${AR_REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${AR_REPO_NAME}" --repository-format=docker --location="${REGION}" --project="${PROJECT_ID}"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}"
source ~/GitHub/gdc-dev-env.sh
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
```
</details>

### 2.5. Dedicated Cluster vs. Shared Team GKE Cluster: Key Workflow Differences

When a team of developers shares **one GKE Stepping-Stone cluster** (with each developer working from their own dedicated Cloud Workstation instance, such as `ws-alice` and `ws-bob`), day-to-day workflows differ from a single-developer dedicated cluster in several important ways:

| Workflow Area | Dedicated GKE Cluster (Single Developer) | Shared Team GKE Cluster (Multiple Developers) |
| :--- | :--- | :--- |
| **Kubernetes Namespace & Helm Release** | Generic namespace (`NAMESPACE="mission-app"`) and release name (`p15-sovereign-mission-app`). | **Mandatory per-developer namespace** (`NAMESPACE="dev-alice"`, `NAMESPACE="dev-bob"`). Always pass `-n "${NAMESPACE}"` to every `kubectl` and `helm` command (or bind your kubeconfig context default namespace via `kubectl config set-context --current --namespace="${NAMESPACE}"`). |
| **`kubectl port-forward` & Web Previews** | Local workstation ports (`8081`, `8080`) map to the only copy of each service on the cluster. | **Same local port (`8081`) works simultaneously across different Cloud Workstations** (`ws-alice` vs. `ws-bob`), because `port-forward` binds `127.0.0.1:8081` **inside your own workstation VM** and tunnels via the K8s API server to `svc/gdc-gateway-tunnel` **inside `-n dev-alice` vs. `-n dev-bob`**. See detailed port-forwarding rules below. |
| **Container Registry Image Tags (`docker push`)** | Pushing `${REGISTRY_HOST}/${APP_NAME}-backend:latest` is safe because only one developer pushes `:latest`. | **Prefix `APP_NAME` (`export APP_NAME="${DEV_ID}-mission-app"`) or set `--set apps.imageTag="${DEV_ID}-dev"`** so `bob` pushing `:latest` into the shared `blueprint-images` Artifact Registry never overwrites `alice`'s container image! |
| **Gateway API (`gdc-platform-gateway`)** | One `Gateway` (`gke-l7-rilb`) in `mission-app`. | **Small teams ($\le 8$ devs):** Each developer deploys their own per-namespace `Gateway` + `gdc-gateway-tunnel` inside `dev-<dev_id>`, giving each developer an isolated ILB VIP so root-path `/` + `/auth` + `/api` routing works without hostname conflicts.<br>**Larger teams ($> 8$ devs):** Watch VPC Internal Forwarding Rule quotas; if sharing a single central `Gateway`, each developer's `HTTPRoute` **must** specify a distinct `hostnames: ["${DEV_ID}.app.gdc.local"]` filter so `/` routes do not collide. |
| **GPU & LLM Inference (`nvidia.com/gpu`)** | Developer deploys `gdc_gemma_gw` or `vLLM` directly whenever needed. | **Never deploy duplicate GPU LLM pods in `dev-<dev_id>`**—GPUs are whole-device scheduled and duplicate pods will hang in `Pending (Insufficient nvidia.com/gpu)`. Consume the **single shared gateway** in `gemma-inference` via `http://gemma-gateway.gemma-inference.svc.cluster.local/v1`. |
| **In-Namespace vs. Cross-Namespace KubeDNS** | Short service names (`postgres-svc`, `keycloak-svc`) or FQDNs work interchangeably. | Short names (`http://keycloak-svc:8080/...`, `postgres-svc:5432`) resolve automatically to **your own `dev-<dev_id>` namespace** via pod DNS search domains, keeping your DB and Keycloak isolated from teammates, while shared services use full FQDNs (`*.gemma-inference.svc.cluster.local`). |
| **Cluster-Scoped K8s Objects (`ClusterRole`, CRDs)** | Static names (e.g., `ClusterRole/app-operator-role`) do not collide. | **Avoid `ClusterRole` / `ClusterRoleBinding` in app charts**—use namespace-scoped `Role` and `RoleBinding` instead. Unprefixed cluster-scoped resources fail Helm ownership checks when a second developer installs the same chart in another namespace. |
| **GCS Buckets & Workload Identity** | Bound to `[mission-app/p15-sovereign-mission-app-sa]`. | Workload Identity IAM bindings match the **exact `[NAMESPACE/KSA_NAME]` tuple** (`${PROJECT_ID}.svc.id.goog[dev-alice/alice-mission-app-sa]`). Each developer must use their own bucket and KSA binding. |
| **Teardown & Cleanup** | `kubectl delete namespace mission-app` is safe. | **Never delete shared namespaces (`gemma-inference`, `gdc-dev`) or PA-managed namespaces (`dev-alice`, which holds your `ResourceQuota` and RBAC `RoleBinding`)!** Clean up via `helm uninstall "${APP_NAME}" -n "${NAMESPACE}"` and `kubectl delete -f manifests/gcp/ -n "${NAMESPACE}"`. |

> [!IMPORTANT]
> **Three Golden Rules for `kubectl port-forward` on a Shared Team Cluster:**
> 1. **Always Specify `-n "${NAMESPACE}"` (`-n dev-<dev_id>`):** Each Cloud Workstation VM (`ws-alice`, `ws-bob`) has its own isolated localhost network stack and unique Web Preview URL (`https://8081-ws-alice-...` vs. `https://8081-ws-bob-...`). Two developers can both bind local Port `8081` at the exact same time without any port conflict—**provided** Alice runs `kubectl port-forward -n dev-alice svc/gdc-gateway-tunnel 8081:80` and Bob runs `kubectl port-forward -n dev-bob svc/gdc-gateway-tunnel 8081:80`.
> 2. **Shared Services (`Port 8080` `gemma-gateway`) Are Read-Safe, Write-Shared:** Multiple developers can simultaneously port-forward the shared GPU gateway (`kubectl port-forward -n gemma-inference svc/gemma-gateway 8080:80`) to view live GPU VRAM and routing telemetry. However, **treat shared admin controls as team-wide**: toggling model overrides, temperature, or the session kill-switch on Port `8080` mutates the live `gemma-gateway` state for every developer on the cluster!
> 3. **Use Targeted Port Cleanup (Never Blanket `pkill`):** If you have multiple port-forwards open on your workstation (e.g., `8080` for `gemma-gateway` and `8081` for your app), kill only the specific port tunnel (`pkill -f "port-forward.*8081:80" || true`) rather than `pkill -f "kubectl port-forward"`, and assign distinct local ports (`8081`, `8082`, `8085`) if previewing multiple namespaces from the **same** workstation.

---

## 3. Step 2: Configure GCP Backing Services (`PostgreSQL`, Actual `Cloud Storage` + Workload Identity, and `Gateway API`)

Because `manifests/gcp/` is only used on your GKE Stepping-Stone cluster (and is automatically stripped when promoting to `gdc-iac-org/blueprints`), populate `~/GitHub/${APP_NAME}/manifests/gcp/` as follows.

### 3.1. Emulate GDC Managed PostgreSQL + `pgvector` (`manifests/gcp/postgres-emulation.yaml`)

On `GDC-ag`, the Zonal `DBCluster` CRD (`postgresql.dbadmin.gdc.goog/v1`) provisions HA PostgreSQL and populates a Kubernetes `Secret` containing `connection_string`, `username`, `password`, and `db_name`. Create the identical `Secret` and a `pgvector/pgvector:pg16` `StatefulSet`:

```bash
# 1. Create the Database Credentials Secret Contract
kubectl create secret generic "${APP_NAME}-db-credentials" \
  --from-literal=username=postgres \
  --from-literal=password=password \
  --from-literal=db_name=postgres \
  --from-literal=connection_string="postgresql://postgres:password@postgres-svc.${NAMESPACE}.svc.cluster.local:5432/postgres" \
  -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# 2. Write and apply manifests/gcp/postgres-emulation.yaml
cat <<EOF > ~/GitHub/${APP_NAME}/manifests/gcp/postgres-emulation.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-init-script
data:
  init.sql: |
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE IF NOT EXISTS mission_records (
      id SERIAL PRIMARY KEY,
      author VARCHAR(128) NOT NULL,
      classification VARCHAR(64) NOT NULL,
      summary TEXT NOT NULL,
      s3_object_key TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres-svc
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: pgvector/pgvector:pg16
        ports:
        - containerPort: 5432
          name: postgres
        env:
        - name: POSTGRES_DB
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-db-credentials
              key: db_name
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-db-credentials
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-db-credentials
              key: password
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
        - name: init-script
          mountPath: /docker-entrypoint-initdb.d
      volumes:
      - name: init-script
        configMap:
          name: postgres-init-script
  volumeClaimTemplates:
  - metadata:
      name: postgres-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 5Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-svc
spec:
  clusterIP: None
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
EOF

kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/postgres-emulation.yaml -n "${NAMESPACE}"
kubectl rollout status statefulset/postgres -n "${NAMESPACE}" --timeout=120s
```

---

### 3.2. Configure Actual Google Cloud Storage (`gs://...`) & GKE Workload Identity

> [!NOTE]
> **Why We Use Actual GCP Cloud Storage (`gs://`) Here (The Deliberate `gcloud` Exception):**  
> Aligning with the `p6-resilient-rag-agent` blueprint in [`gdc-iac-org/blueprints/patterns/p6-resilient-rag-agent`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints/patterns/p6-resilient-rag-agent), we use **actual Google Cloud Storage (`GCS`)** on GCP rather than Config Connector CRDs. Because GCS buckets and IAM Workload Identity bindings live in the GCP control plane, we run `gcloud storage` and `gcloud iam` once below (if not already provisioned by your Platform Administrator in [Appendix A](#appendix-a-one-time-platform-administrator-cluster--workstation-bootstrap-out-of-band)) to bind a real `gs://${APP_NAME}-files-${PROJECT_ID}` bucket to a Kubernetes `ServiceAccount` (`${APP_NAME}-sa`).  
> 
> In **Section 5.1**, your Python backend uses a **Dual-Mode Storage Adapter (`google-cloud-storage` + `boto3`)**:
> - **On GKE (`S3_ENDPOINT=""`):** Automatically uses `google.cloud.storage.Client()` authenticated via GKE Workload Identity against `gs://${APP_NAME}-files-${PROJECT_ID}`.
> - **On Physical `GDC-ag` (`S3_ENDPOINT="https://objectstorage.gdc.goog"`):** Automatically switches to `boto3.client("s3")` (`s3v4`) against your Zonal `Bucket` (`buckets.object.gdc.goog/v1`) with **zero code changes**!

```bash
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "${PROJECT_ID}")
export REGION="${REGION:-us-east4}"
export BUCKET_NAME="${APP_NAME}-files-${PROJECT_ID}"
export GSA_NAME="${APP_NAME}-sa"
export KSA_NAME="${APP_NAME}-sa"
export GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# 1. Create the actual Google Cloud Storage (GCS) bucket
gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud storage buckets create "gs://${BUCKET_NAME}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --uniform-bucket-level-access

# 2. Create the Google Service Account (GSA) and grant Storage Object Admin on the bucket
gcloud iam service-accounts describe "${GSA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud iam service-accounts create "${GSA_NAME}" \
  --display-name="GDC App GCS Workload Identity SA" \
  --project="${PROJECT_ID}"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${GSA_EMAIL}" \
  --role="roles/storage.objectAdmin" --quiet >/dev/null

# 3. Bind GKE Workload Identity between the GSA and the Kubernetes ServiceAccount (KSA)
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]" --quiet >/dev/null

# 4. Save and apply the annotated Kubernetes ServiceAccount + Storage Secret Contract
cat <<EOF > ~/GitHub/${APP_NAME}/manifests/gcp/gcs-workload-identity.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ${KSA_NAME}
  annotations:
    iam.gke.io/gcp-service-account: "${GSA_EMAIL}"
EOF
kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/gcs-workload-identity.yaml -n "${NAMESPACE}"

# 5. Create the Object Storage Secret Contract
#    - On GKE: S3_ENDPOINT is empty ("") so the Dual-Mode adapter uses native GCS via Workload Identity
#    - On GDC-ag: S3_ENDPOINT is "https://objectstorage.gdc.goog" with S3 credentials from the Zonal Bucket
kubectl create secret generic "${APP_NAME}-s3-credentials" \
  --from-literal=AWS_ACCESS_KEY_ID="" \
  --from-literal=AWS_SECRET_ACCESS_KEY="" \
  --from-literal=S3_ENDPOINT="" \
  --from-literal=S3_REGION="${REGION}" \
  --from-literal=BUCKET_NAME="gs://${BUCKET_NAME}" \
  -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
```

<details>
<summary><b>Optional Fallback: In-Cluster S3-Compatible MinIO (If Running Without GCS IAM Permissions)</b></summary>

If you are testing in a restricted Kubernetes namespace where you cannot create GCS buckets or IAM Workload Identity bindings, you can instead deploy an in-cluster S3-compatible MinIO pod using pure `kubectl` by setting `S3_ENDPOINT="http://minio-svc.${NAMESPACE}.svc.cluster.local:9000"` in `Secret/${APP_NAME}-s3-credentials`.
</details>

---

### 3.3. Emulate GDC Load Balancing (`Gateway API` + `gdc-gateway-tunnel` L4 Bridge)

Physical `GDC-ag` racks use the **Kubernetes Gateway API** (`gateway.networking.k8s.io/v1`). Because Cloud Workstations run in a peered tenant VPC that cannot route directly to GKE Regional Internal Load Balancer VIPs (`gke-l7-rilb`), we deploy `Gateway/gdc-platform-gateway` alongside an in-cluster `alpine/socat` L4 bridge (`svc/gdc-gateway-tunnel`):

```bash
cat <<EOF > ~/GitHub/${APP_NAME}/manifests/gcp/gateway-api-staging.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: gdc-platform-gateway
spec:
  gatewayClassName: gke-l7-rilb
  listeners:
  - name: http
    protocol: HTTP
    port: 80
    allowedRoutes:
      namespaces:
        from: Same
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gdc-gateway-tunnel
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gdc-gateway-tunnel
  template:
    metadata:
      labels:
        app: gdc-gateway-tunnel
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
      - name: socat-bridge
        image: alpine/socat:1.8.0.0
        args:
        - "TCP-LISTEN:8080,fork,reuseaddr"
        - "TCP:\$(GATEWAY_VIP):80"
        env:
        - name: GATEWAY_VIP
          value: "127.0.0.1"
        ports:
        - containerPort: 8080
          name: http
        resources:
          requests:
            cpu: "25m"
            memory: "32Mi"
          limits:
            cpu: "100m"
            memory: "64Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: gdc-gateway-tunnel
spec:
  selector:
    app: gdc-gateway-tunnel
  ports:
  - name: http
    port: 80
    targetPort: 8080
---
apiVersion: networking.gke.io/v1
kind: HealthCheckPolicy
metadata:
  name: keycloak-healthcheck
spec:
  default:
    checkIntervalSec: 5
    timeoutSec: 5
    healthyThreshold: 1
    unhealthyThreshold: 3
    config:
      type: HTTP
      httpHealthCheck:
        port: 8080
        requestPath: /auth/realms/gdc-app-realm
  targetRef:
    group: ""
    kind: Service
    name: keycloak-svc
---
apiVersion: networking.gke.io/v1
kind: HealthCheckPolicy
metadata:
  name: backend-healthcheck
spec:
  default:
    checkIntervalSec: 5
    timeoutSec: 5
    healthyThreshold: 1
    unhealthyThreshold: 3
    config:
      type: HTTP
      httpHealthCheck:
        port: 8000
        requestPath: /health
  targetRef:
    group: ""
    kind: Service
    name: backend-svc
---
apiVersion: networking.gke.io/v1
kind: HealthCheckPolicy
metadata:
  name: frontend-healthcheck
spec:
  default:
    checkIntervalSec: 5
    timeoutSec: 5
    healthyThreshold: 1
    unhealthyThreshold: 3
    config:
      type: HTTP
      httpHealthCheck:
        port: 8080
        requestPath: /
  targetRef:
    group: ""
    kind: Service
    name: frontend-svc
EOF

kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/gateway-api-staging.yaml -n "${NAMESPACE}"
```

---

### 3.4. (Optional — GPU Clusters) Architectural Decision: Gemma 4 Gateway (`gdc_gemma_gw`) vs. Pattern 5 Hybrid LLM Gateway (`p5-hybrid-llm-gateway`)

If your GKE cluster includes NVIDIA GPUs (`nvidia-l4`, `a100`, or `h100`) and your application requires AI/LLM inference, the public `~/GitHub/gdc-iac-org/blueprints/` library contains **two distinct LLM gateway architectures**.

> [!IMPORTANT]
> **Mutually Exclusive Choice — Deploy One Gateway Architecture, Not Both:**  
> Do **not** deploy both `gdc_gemma_gw` and `p5-hybrid-llm-gateway` for the same solution—they compete for finite GPU VRAM (`nvidia.com/gpu`) and solve different architectural problems. Review the comparison table below to choose the right gateway before deploying:

| Decision Dimension | **Option A: Gemma 4 Dedicated Inference Gateway (`blueprints/gdc_gemma_gw`) — RECOMMENDED** | **Option B: Pattern 5 Hybrid LLM Gateway (`blueprints/patterns/p5-hybrid-llm-gateway`) — LEGACY / SPECIFIC FAILOVER** |
| :--- | :--- | :--- |
| **Status in `gdc-iac-org`** | **Active & Canonical Default** for greenfield sovereign AI workloads | **Deprecated as of Blueprint v1.2** for general multi-provider routing; retained for managed-Gemini failover or minimal single-GPU PoCs |
| **Primary Routing Architecture** | **Dedicated Sovereign Open-Weights Gateway (`svc/gemma-gateway`):** Exposes an OpenAI-compatible `/v1/chat/completions` API with an intelligent prompt-complexity classifier routing between **Tier 1 (`gemma4:26b` MoE)** for fast chat/RAG and **Tier 2 (`gemma4:31b` Dense)** for complex reasoning, math, and code. | **Primary-to-Local Failover Proxy (`svc/llm-gateway`):** Routes prompts first to the platform-managed **GDC Native Gemini API** (NVIDIA B300 hardware) and automatically retries against a single local `Ollama` / `vLLM` model (`gemma:7b` / `TinyLlama`) **only** on HTTP `5xx` or network timeout. |
| **Governance & Control Plane** | Built-in **Keycloak OIDC Admin Control Plane (`Port 8080`)**, live GPU/VRAM telemetry, per-user token rate limiting, session kill-switch, parameter overrides, and optional Envoy `InferencePool` (`epp`). | Stateless HTTP proxy (`ConfigMap/gateway-conf`) with health checks (`/health`); no admin UI, prompt classifier, or per-user governance plane. |
| **Multi-Developer GPU Sharing** | Deployed **once** in shared namespace `gemma-inference` and consumed by all developer namespaces via `http://gemma-gateway.gemma-inference.svc.cluster.local/v1`. | Deployed inside a single application namespace (`${NAMESPACE}`); `charts/vllm` is useful when a single developer wants a quick 1-GPU OpenAI pod (`TinyLlama-1.1B`) without baking `26B`/`31B` weights. |
| **When to Choose** | **Choose Option A** for almost all greenfield GenAI, RAG (`p6`), Agentic SQL (`p7`), Chat, or Multi-Agent (`p14`) applications targeting sovereign GPU inference on `GDC-ag` or shared team GPU clusters. | **Choose Option B only** if your customer's `GDC-ag` rack provides the managed **GDC Gemini API** and requires automatic local-GPU fallback during Gemini maintenance, **or** if you only have a small single-GPU test node and want a minimal standalone `vLLM` endpoint. |

<details open>
<summary><b>Option A (Recommended Default): Deploy Gemma 4 Dedicated Inference Gateway (<code>blueprints/gdc_gemma_gw</code>)</b></summary>

Deploy `gdc_gemma_gw` once into the shared `gemma-inference` namespace so your application (and any teammates sharing the cluster) can call `http://gemma-gateway.gemma-inference.svc.cluster.local/v1/chat/completions` using standard OpenAI-compatible HTTP/Python clients:

```bash
# If your Artifact Registry does not already contain pre-baked gemma-proxy & ollama-gemma-26b/31b images,
# build and push them once from ~/GitHub/gdc-iac-org/blueprints/gdc_gemma_gw:
#   (cd ~/GitHub/gdc-iac-org/blueprints/gdc_gemma_gw && REGISTRY_HOST="${REGISTRY_HOST}" ./scripts/build-and-push.sh)

# Deploy the Gemma 4 Gateway + GPU serving pods into shared namespace 'gemma-inference'
(
  cd ~/GitHub/gdc-iac-org/blueprints/gdc_gemma_gw/standalone
  export REGISTRY_HOST="${GEMMA_REGISTRY:-${REGISTRY_HOST}}"
  export INFERENCE_ENGINE="ollama"   # Set "vllm" when using blueprints/vllm-gke on A100/H100 GPUs
  export OLLAMA_MODEL_VARIANT="26b"
  chmod +x install-all.sh
  ./install-all.sh
)

kubectl rollout status deployment/gemma-gateway -n gemma-inference --timeout=180s
# Your application backend in ${NAMESPACE} connects via internal KubeDNS:
#   OPENAI_API_BASE_URL="http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
```
</details>

<details>
<summary><b>Option B (Lightweight Single-GPU PoC or Legacy Gemini Failover): Deploy <code>p5-hybrid-llm-gateway</code> / <code>charts/vllm</code></b></summary>

Use this option **only** if you are testing a primary-Gemini-to-local-GPU failover topology or spinning up a lightweight single-model `vLLM` server (`TinyLlama-1.1B` / `Gemma-2B`) inside `${NAMESPACE}` without deploying `gdc_gemma_gw`:

```bash
# 1. Deploy the standalone vLLM OpenAI-compatible GPU serving chart
helm upgrade --install vllm-engine ~/GitHub/gdc-iac-org/blueprints/patterns/p5-hybrid-llm-gateway/charts/vllm \
  --namespace "${NAMESPACE}" \
  --set model.name="TinyLlama/TinyLlama-1.1B-Chat-v1.0" \
  --set resources.limits."nvidia\.com/gpu"=1

# 2. (Optional — Only if testing legacy Primary Gemini -> Local Failover proxy)
helm upgrade --install p5-hybrid-llm-gateway ~/GitHub/gdc-iac-org/blueprints/patterns/p5-hybrid-llm-gateway/chart \
  --namespace "${NAMESPACE}" \
  --set global.projectId="${PROJECT_ID}" \
  --set global.namespace="${NAMESPACE}" \
  --set global.registry="${REGISTRY_HOST}" \
  --set gdc.enabled=false \
  --set apps.enabled=true
```
</details>

---

## 4. Step 3: Mandatory Keycloak OIDC Availability & Integration (`p12-keycloak`)

**Every GDC-ag application must integrate with Keycloak OIDC (`p12-keycloak`) as a minimum baseline, and a live Keycloak instance must be running and available in your GKE Stepping-Stone cluster so you can test authentic OIDC handshakes, RS256 JWKS token validation, and Role-Based Access Control (RBAC) against whatever application you are developing.**

> [!IMPORTANT]
> **Why Keycloak Must Be Available in Your Development Environment:**  
> Even if you develop and test your application's core functional features first (such as database queries, RAG pipelines, LLM prompts, or file uploads) using local/mock authentication, **you cannot promote an application to `GDC-ag` without end-to-end verification against a live Keycloak OIDC Identity Provider**. Having `keycloak` (`svc/keycloak-svc:8080`) running in your namespace and exposed at `/auth` on your Gateway API (`Port 8081`) ensures you can:
> 1. Test real browser OIDC Authorization Code + PKCE (`S256`) redirects under the same single-origin Gateway API (`/` + `/auth` + `/api`) used on physical `GDC-ag` racks.
> 2. Verify that your backend cryptographically validates RS256 signatures against live JWKS endpoints (`http://keycloak-svc:8080/auth/realms/<realm>/protocol/openid-connect/certs`) over internal KubeDNS.
> 3. Run automated integration tests (`401 Unauthorized` on missing/forged tokens, `403 Forbidden` on insufficient roles, `200 OK` on authorized roles) before packaging your air-gap release bundle.

> [!CAUTION]
> **Why Automated Realm Import (`ConfigMap`) Is Required on Cloud Workstations:**  
> Keycloak's interactive Admin UI uses a sandboxed iframe (`login-status-iframe.html`) that strips the Cloud Workstation authentication cookie (`forwardAuthCookie`), resulting in `403 Forbidden`. **Never manually click the Keycloak Admin UI to configure realms!** Always import your realm (`gdc-app-realm`), client (`mission-frontend`), roles (`admin`, `user`), and test users (`alice`, `charlie`) declaratively via a Kubernetes `ConfigMap` mounted at `/opt/keycloak/data/import` with `--import-realm` and `KC_DB_POOL_MIN_SIZE="1"`.

### 4.1. Deploy Pre-Configured Keycloak OIDC (`manifests/gcp/keycloak-emulation.yaml`)

```bash
cat << 'EOF' > ~/GitHub/${APP_NAME}/manifests/gcp/keycloak-emulation.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: keycloak-realm-import
data:
  gdc-app-realm.json: |
    {
      "realm": "gdc-app-realm",
      "enabled": true,
      "sslRequired": "none",
      "roles": {
        "realm": [
          { "name": "user", "description": "Standard GDC Operator" },
          { "name": "admin", "description": "GDC Mission Administrator" }
        ]
      },
      "users": [
        {
          "username": "alice",
          "enabled": true,
          "emailVerified": true,
          "firstName": "Alice",
          "lastName": "Analyst",
          "email": "alice@gdc.local",
          "requiredActions": [],
          "credentials": [{ "type": "password", "value": "password", "temporary": false }],
          "realmRoles": ["user"]
        },
        {
          "username": "charlie",
          "enabled": true,
          "emailVerified": true,
          "firstName": "Charlie",
          "lastName": "Commander",
          "email": "charlie@gdc.local",
          "requiredActions": [],
          "credentials": [{ "type": "password", "value": "password", "temporary": false }],
          "realmRoles": ["admin", "user"]
        }
      ],
      "clients": [
        {
          "clientId": "mission-frontend",
          "enabled": true,
          "publicClient": true,
          "standardFlowEnabled": true,
          "directAccessGrantsEnabled": true,
          "redirectUris": ["*"],
          "webOrigins": ["*"],
          "attributes": { "pkce.code.challenge.method": "S256" },
          "protocolMappers": [
            {
              "name": "realm-roles-mapper",
              "protocol": "openid-connect",
              "protocolMapper": "oidc-usermodel-realm-role-mapper",
              "consentRequired": false,
              "config": {
                "multivalued": "true",
                "userinfo.token.claim": "true",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "claim.name": "roles",
                "jsonType.label": "String"
              }
            }
          ]
        }
      ]
    }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keycloak
  labels:
    app: keycloak
spec:
  replicas: 1
  selector:
    matchLabels:
      app: keycloak
  template:
    metadata:
      labels:
        app: keycloak
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: keycloak
        image: quay.io/keycloak/keycloak:24.0.4
        args: ["start-dev", "--http-relative-path=/auth", "--import-realm"]
        env:
        - name: KEYCLOAK_ADMIN
          value: "admin"
        - name: KEYCLOAK_ADMIN_PASSWORD
          value: "password"
        - name: KC_PROXY
          value: "edge"
        - name: KC_HTTP_ENABLED
          value: "true"
        - name: KC_DB
          value: "dev-mem"
        - name: KC_DB_POOL_MIN_SIZE
          value: "1"
        - name: KC_HEALTH_ENABLED
          value: "true"
        - name: KC_HOSTNAME_STRICT
          value: "false"
        ports:
        - name: http
          containerPort: 8080
        readinessProbe:
          httpGet:
            path: /auth/realms/gdc-app-realm
            port: 8080
          initialDelaySeconds: 20
          periodSeconds: 5
        resources:
          requests:
            cpu: "200m"
            memory: "512Mi"
          limits:
            cpu: "1000m"
            memory: "1Gi"
        volumeMounts:
        - name: realm-import-volume
          mountPath: /opt/keycloak/data/import
      volumes:
      - name: realm-import-volume
        configMap:
          name: keycloak-realm-import
---
apiVersion: v1
kind: Service
metadata:
  name: keycloak-svc
spec:
  selector:
    app: keycloak
  ports:
  - name: http
    port: 8080
    targetPort: 8080
EOF

kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/keycloak-emulation.yaml -n "${NAMESPACE}"
kubectl rollout status deployment/keycloak -n "${NAMESPACE}" --timeout=180s
```

### 4.2. Verify Keycloak Is Available & Customize Realm Roles/Clients for Your Application

Before (or while) developing your application, verify that `keycloak-svc` is running and serving OIDC discovery metadata and RS256 JWKS keys inside `${NAMESPACE}`:

```bash
# Verify Keycloak pod & service are Ready in your namespace
kubectl get pods,svc -n "${NAMESPACE}" -l app=keycloak

# Verify Keycloak OIDC Discovery endpoint inside the cluster
kubectl exec -n "${NAMESPACE}" deploy/keycloak -- \
  curl -sf http://127.0.0.1:8080/auth/realms/gdc-app-realm/.well-known/openid-configuration | head -c 300 && echo ""
```

**Customizing `keycloak-realm-import` for Your Own Application:**
When adapting `manifests/gcp/keycloak-emulation.yaml` to match the specific roles or client IDs of the application you are building:
1. **Custom Roles (`roles.realm`):** Add any domain-specific roles your application enforces (for example, `analyst`, `auditor`, `operator`, `approver`, `admin`).
2. **Test Users (`users`):** Always populate `firstName`, `lastName`, `email`, `"emailVerified": true`, and `"requiredActions": []` on every imported user. Keycloak 24+ enforces `UserProfile` validation by default and will reject token grants with `Account is not fully set up` if those fields are omitted.
3. **Role Claim Mapper (`protocolMappers`):** Keep the `oidc-usermodel-realm-role-mapper` (`"claim.name": "roles"`) on your OIDC client so user roles are injected directly into `payload["roles"]` in both the ID token and Access token.
4. **Reloading Changes:** Because Keycloak uses `KC_DB="dev-mem"`, editing `manifests/gcp/keycloak-emulation.yaml` and running:
   ```bash
   kubectl apply -f ~/GitHub/${APP_NAME}/manifests/gcp/keycloak-emulation.yaml -n "${NAMESPACE}"
   kubectl rollout restart deployment/keycloak -n "${NAMESPACE}"
   kubectl rollout status deployment/keycloak -n "${NAMESPACE}" --timeout=180s
   ```
   cleanly re-imports your updated realm, roles, and users in ~30 seconds.

---

## 5. Step 4: Write Your GDC-Compliant Application Code & Dockerfiles (`src/`)

Below is a complete, production-hardened reference implementation (`src/backend/` and `src/frontend/`) that integrates:
1. **Keycloak OIDC RS256 JWT validation** over internal KubeDNS (`http://keycloak-svc:8080/auth/realms/gdc-app-realm/protocol/openid-connect/certs`) with `admin` / `user` RBAC.
2. **PostgreSQL (`pgvector`) persistence** via `Secret/${APP_NAME}-db-credentials`.
3. **Dual-Mode Object Storage (`google-cloud-storage` + `boto3`)** aligning with [`gdc-iac-org/blueprints/patterns/p6-resilient-rag-agent`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints/patterns/p6-resilient-rag-agent): uses **actual Google Cloud Storage (`gs://...`)** via GKE Workload Identity when `S3_ENDPOINT` is empty on GCP, and automatically switches to **GDC-ag Native Object Storage (`https://objectstorage.gdc.goog`)** via `boto3` (`s3v4`) on `GDC-ag` production.
4. **Rootless, non-privileged container execution** (`USER 1000`) compliant with `gdc-iac-org/policy/security.rego`.

### 5.1. Backend FastAPI Service (`src/backend/main.py`, `requirements.txt`, `Dockerfile`)

```bash
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

cat << 'EOF' > ~/GitHub/${APP_NAME}/src/backend/main.py
import os
import boto3
import jwt
import psycopg2
from botocore.client import Config
from google.cloud import storage as gcs_storage
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

app = FastAPI(title="GDC-ag Sovereign Mission API")

# 1. Keycloak OIDC Configuration (Always verify RS256 JWKS over internal KubeDNS!)
OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="token")
KEYCLOAK_INTERNAL_URL = os.getenv(
    "KEYCLOAK_URL",
    "http://keycloak-svc:8080/auth/realms/gdc-app-realm",
)
jwks_client = PyJWKClient(f"{KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/certs")

async def get_current_user(token: str = Depends(OAUTH2_SCHEME)) -> dict:
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

# 2. Database & Dual-Mode Object Storage Clients (GCS on GKE Workload Identity <-> S3 on GDC-ag)
DB_CONN = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres-svc:5432/postgres")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "").strip()
S3_REGION = os.getenv("S3_REGION", "zone1").strip()
BUCKET_NAME = os.getenv("BUCKET_NAME", "p15-sovereign-mission-app-bucket").removeprefix("s3://").removeprefix("gs://")

s3_client = None
gcs_client = None

if S3_ENDPOINT:
    # Physical GDC-ag Production (or optional in-cluster S3 MinIO fallback)
    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY") or None,
        config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10),
        region_name=S3_REGION,
    )
else:
    # GCP Stepping-Stone Cluster: Actual Google Cloud Storage via GKE Workload Identity
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

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "mission-backend",
        "storage_mode": "gdc-s3" if s3_client else "gcp-gcs",
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
EOF

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

### 5.2. Frontend Single-Page App with Keycloak OIDC PKCE (`src/frontend/`)

```bash
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/frontend/index.html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>GDC-ag Sovereign Mission Portal</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; max-width: 880px; margin: 2rem auto; padding: 0 1rem; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.25rem; margin-bottom: 1rem; }
    button { background: #2563eb; color: white; border: none; padding: 0.6rem 1.1rem; border-radius: 6px; cursor: pointer; font-weight: 600; }
    input, select, textarea { width: 100%; padding: 0.5rem; margin: 0.4rem 0 0.8rem; border-radius: 4px; border: 1px solid #475569; background: #0f172a; color: white; }
    .badge { background: #059669; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.8rem; }
  </style>
</head>
<body>
  <h1>🛡️ GDC-ag Sovereign Mission Portal</h1>
  <div id="auth-box" class="card">Loading Keycloak OIDC boundary...</div>
  <div id="app-box" style="display:none;">
    <div class="card">
      <h3>Submit Mission Record (PostgreSQL + Cloud/Object Storage)</h3>
      <form id="record-form">
        <label>Classification (SECRET requires 'admin' role / charlie):</label>
        <select name="classification"><option value="UNCLASSIFIED">UNCLASSIFIED</option><option value="SECRET">SECRET</option></select>
        <label>Mission Summary:</label>
        <textarea name="summary" rows="2" required placeholder="Enter tactical observation..."></textarea>
        <label>Attach File (Uploaded to GCS on GKE / S3 Bucket on GDC-ag):</label>
        <input type="file" name="attachment" />
        <button type="submit">Save Record</button>
      </form>
    </div>
    <div class="card">
      <h3>Mission Records</h3>
      <pre id="records-out">Loading...</pre>
    </div>
  </div>
  <script>
    const REALM_URL = `${window.location.origin}/auth/realms/gdc-app-realm/protocol/openid-connect`;
    const CLIENT_ID = "mission-frontend";

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

    async function init() {
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
        document.getElementById("auth-box").innerHTML = `<button onclick="login()">🔑 Sign In with Keycloak OIDC (alice or charlie)</button>`;
        return;
      }
      const claims = JSON.parse(atob(token.split(".")[1]));
      document.getElementById("auth-box").innerHTML = `Authenticated via Keycloak OIDC as <b>${claims.preferred_username}</b> <span class="badge">Roles: ${(claims.roles || []).join(", ")}</span>`;
      document.getElementById("app-box").style.display = "block";
      await loadRecords(token);

      document.getElementById("record-form").onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const res = await fetch("/api/records", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
        alert(await res.text());
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

### 5.3. How to Integrate Keycloak OIDC Into Your Application After Developing Core Functional Features

When building a new customer application (such as a RAG assistant, an agentic Text-to-SQL service, a telemetry dashboard, or a workflow API), developers typically follow a **Two-Phase Development Workflow**:
- **Phase 1 (Functional Development First):** Build and verify your core business logic, database schema, GCS/S3 storage, and LLM calls first using a lightweight **Mock Auth mode (`AUTH_MODE=mock`)** so you can iterate rapidly with `curl`, `pytest`, or a UI persona switcher without browser login redirects.
- **Phase 2 (Keycloak OIDC Integration & Hardening):** Once your functional endpoints and UI work as expected, switch to **Live Keycloak OIDC mode (`AUTH_MODE=keycloak`)** against the `keycloak` service running in your GKE namespace (`svc/keycloak-svc:8080`)—**without rewriting any of your functional route handlers!**

```mermaid
flowchart LR
    subgraph PHASE1["Phase 1: Functional Development (AUTH_MODE=mock)"]
        F1["1. Build DB, Storage, LLM &\nUI Functional Endpoints"]
        F2["2. Test with X-Mock-User /\nX-Mock-Roles Headers & pytest"]
    end

    subgraph PHASE2["Phase 2: Keycloak OIDC Integration (AUTH_MODE=keycloak)"]
        K1["3. Align Realm Roles & Users\nin keycloak-emulation.yaml"]
        K2["4. Switch Backend to RS256 JWKS\n(http://keycloak-svc:8080/auth/...)"]
        K3["5. Wire Frontend OIDC PKCE\n(Vanilla JS or React AuthProvider)"]
        K4["6. Run Unit (pytest) & Live\nKeycloak Integration Tests"]
    end

    F1 --> F2 ==> K1 --> K2 --> K3 --> K4
```

#### Step A: Use a Dual-Mode `auth.py` Dependency So Functional Code Never Changes
By isolating authentication in a small helper module (`src/backend/auth.py` or inside `main.py`) that returns a normalized `{"username": str, "roles": list[str]}` dictionary, your functional endpoints (`@app.get(...)`, `@app.post(...)`) stay **100% identical** between Phase 1 (`AUTH_MODE=mock`) and Phase 2 (`AUTH_MODE=keycloak`):

```python
import os
import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

# Set AUTH_MODE="mock" ONLY during early local functional prototyping.
# Production and GKE Staging MUST use AUTH_MODE="keycloak" (the default).
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
    # Phase 1: Functional development mode (ONLY when explicitly enabled via AUTH_MODE=mock)
    if AUTH_MODE == "mock" and not credentials:
        username = x_mock_user or "alice"
        roles = [r.strip() for r in (x_mock_roles or "user").split(",") if r.strip()]
        return {"username": username, "roles": roles, "auth_source": "mock"}

    # Phase 2: Mandatory Keycloak OIDC RS256 JWKS Verification
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing OIDC Bearer token")

    token = credentials.credentials
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
        return {"username": username, "roles": roles, "auth_source": "keycloak-jwt"}
    except (PyJWTError, Exception) as exc:
        raise HTTPException(status_code=401, detail=f"OIDC JWT validation failed: {exc}")

def require_roles(*required_roles: str):
    """Reusable RBAC guard for protecting privileged functional endpoints."""
    async def _role_checker(user: dict = Depends(get_current_user)) -> dict:
        if not any(role in user["roles"] for role in required_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles {list(required_roles)}; user '{user['username']}' has {user['roles']}",
            )
        return user
    return _role_checker
```

#### Step B: Replicate Your Mock Personas & Roles in `ConfigMap/keycloak-realm-import`
When you finish functional testing and are ready to switch to Keycloak OIDC:
1. List every role your functional code checks (e.g., `user`, `admin`, `analyst`, `auditor`) and add them under `roles.realm` in `manifests/gcp/keycloak-emulation.yaml`.
2. Add corresponding test users under `users` in `manifests/gcp/keycloak-emulation.yaml` with `"enabled": true`, `"emailVerified": true`, `"firstName"`, `"lastName"`, `"email"`, and `"requiredActions": []`.
3. Re-apply `manifests/gcp/keycloak-emulation.yaml` and restart Keycloak (`kubectl rollout restart deployment/keycloak -n "${NAMESPACE}"`).

#### Step C: Replace Frontend Mock Persona Selectors with OIDC PKCE (`Vanilla JS` or `React`)
- **If using a Vanilla JS / HTML frontend:** Use the Web Crypto `S256` PKCE flow shown in **Section 5.2** above (`window.location.origin + "/auth/realms/gdc-app-realm/protocol/openid-connect/auth"`), store the resulting `access_token` in `sessionStorage`, and pass `headers: { Authorization: \`Bearer \${token}\` }` on every `fetch("/api/...")` call.
- **If using a compiled React / Vite frontend (like `p6-resilient-rag-agent` or `gemma-client`):** Install `react-oidc-context` and `oidc-client-ts` (`npm install react-oidc-context oidc-client-ts`) and replace your mock `UserContext.jsx` with a `KeycloakBridge` provider that reads `window.location.origin + "/auth/realms/gdc-app-realm"`:
  ```jsx
  import React, { createContext, useContext } from "react";
  import { AuthProvider, useAuth } from "react-oidc-context";

  const UserContext = createContext(null);
  export const useUser = () => useContext(UserContext);

  const oidcConfig = {
    authority: `${window.location.origin}/auth/realms/gdc-app-realm`,
    client_id: "mission-frontend",
    redirect_uri: window.location.origin + "/",
    onSigninCallback: () => window.history.replaceState({}, document.title, window.location.pathname),
  };

  function KeycloakBridge({ children }) {
    const auth = useAuth();
    if (auth.isLoading) return <div>Loading Keycloak OIDC boundary...</div>;
    if (!auth.isAuthenticated) {
      return <button onClick={() => auth.signinRedirect()}>Sign In with Keycloak OIDC</button>;
    }
    const profile = auth.user?.profile || {};
    const roles = profile.roles || profile.realm_access?.roles || [];
    const user = {
      username: profile.preferred_username,
      roles,
      token: auth.user?.access_token,
    };
    return <UserContext.Provider value={{ user, logout: () => auth.removeUser() }}>{children}</UserContext.Provider>;
  }

  export function AppUserProvider({ children }) {
    return (
      <AuthProvider {...oidcConfig}>
        <KeycloakBridge>{children}</KeycloakBridge>
      </AuthProvider>
    );
  }
  ```

#### Step D: Verify the 4-Point Keycloak Integration Checklist
Before deploying, confirm these 4 wiring points between your app, Keycloak, and the Gateway API:
1. **Internal KubeDNS for Backend JWKS Verification:** `KEYCLOAK_URL` in `Deployment/backend` points to `http://keycloak-svc:8080/auth/realms/gdc-app-realm` (never the external workstation preview URL or public load balancer hostname).
2. **Single-Origin Browser Authority:** The frontend uses `${window.location.origin}/auth/realms/gdc-app-realm` so `/`, `/api`, and `/auth` share the exact same origin and port (`Port 8081` on Cloud Workstation; `https://app.gdc.local` on `GDC-ag`).
3. **Gateway API `/auth` Route Header Injection:** `HTTPRoute` sets `X-Forwarded-Proto: https` on `/auth` and `Deployment/keycloak` sets `KC_PROXY="edge"`, `KC_HTTP_ENABLED="true"`, and `KC_HOSTNAME_STRICT="false"`.
4. **GKE `HealthCheckPolicy` on `keycloak-svc`:** `HealthCheckPolicy/keycloak-healthcheck` probes `port: 8080` at `requestPath: /auth/realms/gdc-app-realm` (or `/auth/realms/master`) so GKE's `gke-l7-rilb` Load Balancer marks the Keycloak NEG healthy (`HTTP 200`) rather than failing on `GET /` (`302 Found` $\rightarrow$ `no healthy upstream`).

---

### 5.4. Automated Unit, Functional & Keycloak RBAC Tests (`src/backend/test_main.py`)

Always include an automated unit test suite (`src/backend/test_main.py`) in your repository using Python's built-in `unittest.IsolatedAsyncioTestCase`. Testing route handlers and `get_current_user` directly with `unittest.IsolatedAsyncioTestCase` requires **zero extra third-party test client packages** (such as `httpx`/`httpx2`), keeping your production container image attack surface minimal while verifying **both** your core functional endpoints (with database and storage calls mocked for fast offline execution) **and** your Keycloak OIDC authentication and RBAC enforcement (`401 Unauthorized` on forged/invalid JWTs, valid RS256 claim extraction, `403 Forbidden` when a standard `user` attempts an `admin`-only operation, and `200 OK` when authorized):

```bash
cat << 'EOF' > ~/GitHub/${APP_NAME}/src/backend/test_main.py
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
import main


class TestMissionBackendUnitAndRBAC(unittest.IsolatedAsyncioTestCase):
    def test_01_health_endpoint_is_public(self):
        """Health check endpoint must remain unauthenticated for GKE HealthCheckPolicy probes."""
        body = main.health()
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["service"], "mission-backend")

    async def test_02_forged_or_invalid_jwt_rejected_401(self):
        """Zero-Trust baseline: passing a forged/invalid Bearer JWT to get_current_user must raise 401."""
        with self.assertRaises(HTTPException) as ctx:
            await main.get_current_user(token="forged.invalid.jwt")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("main.jwt.decode")
    @patch("main.jwks_client.get_signing_key_from_jwt")
    async def test_03_valid_keycloak_rs256_jwt_extracts_user_and_roles(self, mock_jwks, mock_decode):
        """Keycloak OIDC claim mapping: valid RS256 token maps preferred_username and roles."""
        mock_key = MagicMock()
        mock_key.key = "public-rs256-key"
        mock_jwks.return_value = mock_key
        mock_decode.return_value = {"preferred_username": "alice", "roles": ["user"]}

        user = await main.get_current_user(token="valid.rs256.jwt")
        self.assertEqual(user, {"username": "alice", "roles": ["user"]})

    @patch("main.psycopg2.connect")
    async def test_04_authenticated_user_can_list_and_create_unclassified_record(self, mock_connect):
        """Functional + RBAC test: 'alice' (role: user) can list and file UNCLASSIFIED records."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            (1, "alice", "UNCLASSIFIED", "Routine patrol check", None, None)
        ]
        mock_cur.fetchone.return_value = [1]
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_connect.return_value = mock_conn

        alice = {"username": "alice", "roles": ["user"]}
        listed = main.list_records(user=alice)
        self.assertEqual(listed["authenticated_user"], "alice")
        self.assertEqual(len(listed["records"]), 1)

        created = await main.create_record(
            classification="UNCLASSIFIED",
            summary="Routine patrol check",
            attachment=None,
            user=alice,
        )
        self.assertEqual(created["status"], "created")
        self.assertEqual(created["author"], "alice")

    async def test_05_standard_user_blocked_from_secret_record_403(self):
        """RBAC enforcement: 'alice' (role: user) must be blocked with 403 when filing SECRET records."""
        alice = {"username": "alice", "roles": ["user"]}
        with self.assertRaises(HTTPException) as ctx:
            await main.create_record(
                classification="SECRET",
                summary="Attempted unauthorized SECRET post",
                attachment=None,
                user=alice,
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("admin", ctx.exception.detail)

    @patch("main.upload_object_bytes", return_value="gs://test-bucket/charlie/intel.txt")
    @patch("main.psycopg2.connect")
    async def test_06_admin_user_allowed_secret_record_with_attachment_200(self, mock_connect, mock_upload):
        """RBAC + Storage test: 'charlie' (role: admin) can file SECRET records with file attachments."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = [42]
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_connect.return_value = mock_conn

        mock_file = MagicMock()
        mock_file.filename = "intel.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=b"classified payload")

        charlie = {"username": "charlie", "roles": ["admin", "user"]}
        created = await main.create_record(
            classification="SECRET",
            summary="Verified sector 9 telemetry",
            attachment=mock_file,
            user=charlie,
        )
        self.assertEqual(created["id"], 42)
        self.assertEqual(created["s3_object_key"], "gs://test-bucket/charlie/intel.txt")
        mock_upload.assert_called_once_with("charlie/intel.txt", b"classified payload", "text/plain")


if __name__ == "__main__":
    unittest.main()
EOF
```

You can execute this unit test suite at any time during development using `docker` (with zero host Python dependencies or extra container packages required):

```bash
cd ~/GitHub/${APP_NAME}
docker build -t "${REGISTRY_HOST}/${APP_NAME}-backend:latest" src/backend
docker run --rm -v "$HOME/GitHub/${APP_NAME}/src/backend/test_main.py:/app/test_main.py:ro" \
  --entrypoint python3 "${REGISTRY_HOST}/${APP_NAME}-backend:latest" \
  -m unittest discover -s /app -p "test_*.py" -v
```

---

## 6. Step 5: Create the `gdc-iac-org`-Compliant Manifests & Helm Wrapper Chart (`manifests/` & `chart/`)

To align with [`https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints`](https://github.com/gdc-iac/gdc-iac-org/tree/main/blueprints), every blueprint must provide:
1. **`external_images.txt`**: Audited third-party images for air-gap mirroring.
2. **`manifests/gdc/`**: Zonal GDC Custom Resources (`DBCluster` and `Bucket`).
3. **`manifests/apps/`**: User Cluster Kubernetes workloads (`Deployment`, `Service`, `HTTPRoute`).
4. **`chart/`**: A standardized Helm wrapper chart (`values.yaml`, `values.schema.json`, `templates/`, and `tests/pattern_test.yaml`) that passes all 4 layers of `~/GitHub/gdc-iac-org/scripts/test-charts.sh` (including OPA Rego security policies in `policy/security.rego`).

### 6.1. Populate `external_images.txt`, `manifests/gdc/`, and `manifests/apps/`

```bash
# 1. Audited 3P images list
cat << 'EOF' > ~/GitHub/${APP_NAME}/external_images.txt
# 3P Container Dependencies for Air-Gapped GDC-ag Mirroring
quay.io/keycloak/keycloak:24.0.4
EOF

# 2. Production Zonal GDC Custom Resources (manifests/gdc/resources.yaml)
cat <<EOF > ~/GitHub/${APP_NAME}/manifests/gdc/resources.yaml
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: ${APP_NAME}-db
  namespace: ${NAMESPACE}
spec:
  version: POSTGRESQL_15
  availabilityType: ZONAL_HA
  resources:
    requests:
      cpu: "2"
      memory: 8Gi
  storage:
    size: 50G
---
apiVersion: object.gdc.goog/v1
kind: Bucket
metadata:
  name: ${APP_NAME}-bucket
  namespace: ${NAMESPACE}
spec:
  description: "Sovereign Mission Attachment Storage"
  storageClass: Standard
EOF

# 3. Production User Cluster Workloads & Unified Gateway API HTTPRoute (manifests/apps/workloads.yaml)
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
```

### 6.2. Create the Standardized Stage 5 Helm Wrapper Chart (`chart/`)

In `gdc-iac-org`, Stage 2 (`2-resources`) provisions Zonal `DBCluster` and `Bucket` CRDs on the Zone Admin API server, while Stage 5 (`5-workload-factory`) deploys your Helm chart to the User Cluster with `gdc.enabled: false` and `apps.enabled: true`. Create the complete Helm chart in `~/GitHub/${APP_NAME}/chart/`:

```bash
cat <<EOF > ~/GitHub/${APP_NAME}/chart/Chart.yaml
apiVersion: v2
name: ${APP_NAME}
description: GDC-ag Sovereign Mission Application Blueprint
type: application
version: 0.1.0
appVersion: "1.0.0"
EOF

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

# Stage 2 provisions Zonal CRDs, so gdc.enabled defaults to false for Stage 5 User Cluster deployment
gdc:
  enabled: false

apps:
  enabled: true
  imageTag: "latest"
  serviceAccountName: "${APP_NAME}-sa"
  keycloakUrl: "http://keycloak-svc:8080/auth/realms/gdc-app-realm"
  # Defaults to GDC-ag Native Object Storage for production; set s3Endpoint="" on GKE to use native GCS via Workload Identity
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
        "s3Endpoint": { "type": "string" },
        "bucketName": { "type": "string" }
      }
    }
  }
}
EOF

cat <<EOF > ~/GitHub/${APP_NAME}/chart/templates/_helpers.tpl
{{- define "${APP_NAME}.namespace" -}}
{{- default .Values.global.namespace .Values.namespace -}}
{{- end -}}

{{- define "${APP_NAME}.registry" -}}
{{- default .Values.global.registry .Values.registry -}}
{{- end -}}
EOF

cat <<EOF > ~/GitHub/${APP_NAME}/chart/templates/gdc/resources.yaml
{{- if .Values.gdc.enabled }}
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: ${APP_NAME}-db
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  version: POSTGRESQL_15
  availabilityType: ZONAL_HA
  resources:
    requests:
      cpu: "2"
      memory: 8Gi
  storage:
    size: 50G
---
apiVersion: object.gdc.goog/v1
kind: Bucket
metadata:
  name: {{ .Values.apps.bucketName }}
  namespace: {{ include "${APP_NAME}.namespace" . }}
spec:
  description: "Sovereign Mission Attachment Storage"
  storageClass: Standard
{{- end }}
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

cat <<EOF > ~/GitHub/${APP_NAME}/chart/tests/pattern_test.yaml
suite: test ${APP_NAME} wrapper chart
templates:
  - templates/apps/workloads.yaml
  - templates/gdc/resources.yaml
tests:
  - it: should render User Cluster workloads and skip GDC CRDs by default
    asserts:
      - hasDocuments:
          count: 5
        template: templates/apps/workloads.yaml
      - hasDocuments:
          count: 0
        template: templates/gdc/resources.yaml
  - it: should render GDC DBCluster and Bucket CRDs when gdc.enabled is true
    set:
      gdc.enabled: true
    asserts:
      - hasDocuments:
          count: 2
        template: templates/gdc/resources.yaml
EOF
```

---

## 7. Step 6: Build, Deploy & Test on Your Cloud Workstation (`docker`, `helm`, `kubectl` Only)

Now build your images, deploy the chart to your GKE Stepping-Stone cluster (using native Google Cloud Storage via Workload Identity by passing `apps.s3Endpoint=""`), wire the Gateway API L4 tunnel, and verify end-to-end using strictly `docker`, `helm`, and `kubectl`:

```bash
cd ~/GitHub/${APP_NAME}

# 1. Build and push container images using docker
docker build -t "${REGISTRY_HOST}/${APP_NAME}-backend:latest" src/backend
docker push "${REGISTRY_HOST}/${APP_NAME}-backend:latest"

docker build -t "${REGISTRY_HOST}/${APP_NAME}-frontend:latest" src/frontend
docker push "${REGISTRY_HOST}/${APP_NAME}-frontend:latest"

# 2. Deploy your application via the Stage 5 Helm Wrapper Chart
#    (Passing apps.s3Endpoint="" activates native Google Cloud Storage via GKE Workload Identity)
helm upgrade --install "${APP_NAME}" ./chart \
  --namespace "${NAMESPACE}" \
  --set global.projectId="${PROJECT_ID}" \
  --set global.namespace="${NAMESPACE}" \
  --set global.registry="${REGISTRY_HOST}" \
  --set gdc.enabled=false \
  --set apps.enabled=true \
  --set apps.serviceAccountName="${APP_NAME}-sa" \
  --set apps.s3Endpoint="" \
  --set apps.bucketName="${APP_NAME}-files-${PROJECT_ID}"

kubectl rollout status deployment/backend deployment/frontend -n "${NAMESPACE}" --timeout=120s

# 3. Wait for GKE Gateway API VIP allocation and bind the L4 TCP Tunnel (gdc-gateway-tunnel)
until [ -n "$(kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)" ]; do
  echo "Waiting for gdc-platform-gateway VIP..."
  sleep 5
done
export GATEWAY_VIP=$(kubectl get gateway gdc-platform-gateway -n "${NAMESPACE}" -o jsonpath='{.status.addresses[0].value}')
kubectl set env deployment/gdc-gateway-tunnel GATEWAY_VIP="${GATEWAY_VIP}" -n "${NAMESPACE}"
kubectl rollout status deployment/gdc-gateway-tunnel -n "${NAMESPACE}" --timeout=60s

# 4. Port-forward the Unified Gateway API Tunnel on Port 8081 (scoped to ${NAMESPACE} and port 8081)
pkill -f "while true.*8081" || true
pkill -f "port-forward.*8081" || true
sleep 1
nohup bash -c "while true; do kubectl port-forward --address 0.0.0.0 -n ${NAMESPACE} svc/gdc-gateway-tunnel 8081:80 >> /tmp/pf-8081.log 2>&1; sleep 1; done" >/dev/null 2>&1 &

# 5. Wait for GKE Gateway API (gke-l7-rilb) Envoy URL map & all 3 NEG HealthCheckPolicies (/, /auth, /api) to return HTTP 200
#    (While NEG health checks warm up, gke-l7-rilb returns 'fault filter abort' or 'no healthy upstream' for ~30-60s)
for i in {1..36}; do
  CODE_FE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/ 2>/dev/null || echo "000")
  CODE_KC=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/auth/realms/gdc-app-realm 2>/dev/null || echo "000")
  CODE_BE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/api/health 2>/dev/null || echo "000")
  if [ "${CODE_FE}" = "200" ] && [ "${CODE_KC}" = "200" ] && [ "${CODE_BE}" = "200" ]; then
    echo "✅ Port 8081 Gateway API is LIVE across all 3 routes (/=${CODE_FE}, /auth=${CODE_KC}, /api/health=${CODE_BE})!"
    break
  fi
  echo "  [${i}/36] Waiting for gke-l7-rilb HTTPRoute & NEG health checks (/=${CODE_FE}, /auth=${CODE_KC}, /api/health=${CODE_BE})..."
  sleep 5
done
```

### Verify End-to-End (CLI & Browser)
1. **CLI Zero-Trust & OIDC Verification (No Browser Required):**
   ```bash
   # A. Confirm unauthenticated API call is rejected with HTTP 401
   curl -i -s http://127.0.0.1:8081/api/records | head -n 1
   # Expected: HTTP/1.1 401 Unauthorized

   # B. Acquire a signed RS256 JWT from Keycloak via Gateway API (/auth) as 'charlie' (admin)
   TOKEN=$(curl -s -X POST "http://127.0.0.1:8081/auth/realms/gdc-app-realm/protocol/openid-connect/token" \
     -d "client_id=mission-frontend" \
     -d "grant_type=password" \
     -d "username=charlie" \
     -d "password=password" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

   # C. Post a SECRET mission record with an uploaded file to Google Cloud Storage via Gateway API (/api)
   echo "Tactical telemetry log payload" > /tmp/sample-log.txt
   curl -s -X POST "http://127.0.0.1:8081/api/records" \
     -H "Authorization: Bearer ${TOKEN}" \
     -F "classification=SECRET" \
     -F "summary=Sector 9 perimeter sensor verified" \
     -F "attachment=@/tmp/sample-log.txt"

   # D. Read back records from PostgreSQL (confirming gs://... URI persisted)
   curl -s "http://127.0.0.1:8081/api/records" -H "Authorization: Bearer ${TOKEN}" | python3 -m json.tool
   ```
2. **Interactive Browser Verification:**
   Open your Cloud Workstation Port `8081` Web Preview (`https://8081-w-...cloudworkstations.dev`), click **Sign In with Keycloak OIDC**, and log in as **`alice` / `password`** (`user` role) or **`charlie` / `password`** (`admin` role).

### 7.2. Automated Live Keycloak OIDC & End-to-End Integration Test Suite (`scripts/test-keycloak-integration.py`)

Create and run `~/GitHub/${APP_NAME}/scripts/test-keycloak-integration.py` (using only Python 3 standard library modules) to automatically verify all **7 live Keycloak OIDC, RBAC, PostgreSQL, and Cloud/Object Storage integration invariants** against your deployed application on Port `8081`:

```bash
cat << 'EOF' > ~/GitHub/${APP_NAME}/scripts/test-keycloak-integration.py
#!/usr/bin/env python3
"""
Automated Live Keycloak OIDC & Application Integration Test Suite (7 Checks).
Validates:
  [KC-01] Keycloak OIDC Discovery & RS256 JWKS endpoint availability via Gateway API (/auth)
  [KC-02] Application Backend Health endpoint reachability via Gateway API (/api/health)
  [KC-03] Zero-Trust Unauthenticated Rejection (HTTP 401 when Bearer token is missing)
  [KC-04] Zero-Trust Forged/Tampered Token Rejection (HTTP 401 on invalid RS256 JWT)
  [KC-05] Keycloak OIDC Token Issuance & Role Claim Mapper for 'alice' (role: 'user')
  [KC-06] Least-Privilege RBAC: 'alice' blocked from SECRET (HTTP 403), allowed on UNCLASSIFIED (HTTP 200)
  [KC-07] Privileged Admin RBAC + Storage/DB Persistence: 'charlie' (role: 'admin') posts SECRET + attachment (HTTP 200)
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
REALM = os.getenv("KEYCLOAK_REALM", "gdc-app-realm")
CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "mission-frontend")

def http_request(url: str, method: str = "GET", headers: dict | None = None, data: bytes | None = None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")

def decode_jwt_claims(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))

def get_keycloak_token(username: str, password: str) -> str:
    token_url = f"{BASE_URL}/auth/realms/{REALM}/protocol/openid-connect/token"
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "password",
        "username": username,
        "password": password,
    }).encode("utf-8")
    status, text = http_request(
        token_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=body,
    )
    if status != 200:
        raise RuntimeError(f"Keycloak token grant failed for {username} (HTTP {status}): {text}")
    return json.loads(text)["access_token"]

def build_multipart(fields: dict[str, str], file_field: tuple[str, str, bytes] | None = None) -> tuple[str, bytes]:
    boundary = f"----GDCBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for k, v in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    if file_field:
        field_name, filename, content = file_field
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: text/plain\r\n\r\n".encode()
        )
        lines.append(content + b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    return f"multipart/form-data; boundary={boundary}", b"".join(lines)

def main() -> int:
    passed = 0
    total = 7
    print("================================================================================")
    print(f"🔐 KEYCLOAK OIDC & APPLICATION INTEGRATION TEST SUITE ({BASE_URL})")
    print("================================================================================")

    # [KC-01] OIDC Discovery & JWKS
    disc_status, disc_body = http_request(f"{BASE_URL}/auth/realms/{REALM}/.well-known/openid-configuration")
    jwks_status, jwks_body = http_request(f"{BASE_URL}/auth/realms/{REALM}/protocol/openid-connect/certs")
    assert disc_status == 200 and jwks_status == 200 and "keys" in json.loads(jwks_body), \
        f"KC-01 failed: disc={disc_status}, jwks={jwks_status}"
    print("[KC-01] Keycloak OIDC Discovery & RS256 JWKS Reachable (/auth) ......... [PASS]")
    passed += 1

    # [KC-02] Backend Health
    h_status, h_body = http_request(f"{BASE_URL}/api/health")
    assert h_status == 200 and json.loads(h_body).get("status") == "healthy", f"KC-02 failed: {h_status} {h_body}"
    print("[KC-02] Application Backend Health Endpoint Reachable (/api/health) .... [PASS]")
    passed += 1

    # [KC-03] Unauthenticated 401
    u_status, _ = http_request(f"{BASE_URL}/api/records")
    assert u_status == 401, f"KC-03 failed: expected 401, got {u_status}"
    print("[KC-03] Zero-Trust Unauthenticated Request Rejected (HTTP 401) ......... [PASS]")
    passed += 1

    # [KC-04] Forged JWT 401
    f_status, _ = http_request(
        f"{BASE_URL}/api/records",
        headers={"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.e30.invalidsignature"},
    )
    assert f_status == 401, f"KC-04 failed: expected 401, got {f_status}"
    print("[KC-04] Forged / Tampered Bearer Token Rejected (HTTP 401) ............. [PASS]")
    passed += 1

    # [KC-05] Alice token issuance & role claim verification
    alice_token = get_keycloak_token("alice", "password")
    alice_claims = decode_jwt_claims(alice_token)
    alice_roles = alice_claims.get("roles") or alice_claims.get("realm_access", {}).get("roles", [])
    assert alice_claims.get("preferred_username") == "alice" and "user" in alice_roles, \
        f"KC-05 failed: claims={alice_claims}"
    print("[KC-05] Keycloak RS256 Token Issued & 'user' Role Mapped for 'alice' ... [PASS]")
    passed += 1

    # [KC-06] Alice RBAC: blocked from SECRET (403), allowed on UNCLASSIFIED (200)
    ctype, body = build_multipart({"classification": "SECRET", "summary": "Unauthorized secret test"})
    s_status, _ = http_request(
        f"{BASE_URL}/api/records",
        method="POST",
        headers={"Authorization": f"Bearer {alice_token}", "Content-Type": ctype},
        data=body,
    )
    ctype_ok, body_ok = build_multipart({"classification": "UNCLASSIFIED", "summary": "Alice routine report"})
    ok_status, _ = http_request(
        f"{BASE_URL}/api/records",
        method="POST",
        headers={"Authorization": f"Bearer {alice_token}", "Content-Type": ctype_ok},
        data=body_ok,
    )
    assert s_status == 403 and ok_status == 200, f"KC-06 failed: SECRET={s_status}, UNCLASSIFIED={ok_status}"
    print("[KC-06] Least-Privilege RBAC ('alice': SECRET->403, UNCLASSIFIED->200) . [PASS]")
    passed += 1

    # [KC-07] Charlie RBAC: allowed on SECRET + file upload + DB readback
    charlie_token = get_keycloak_token("charlie", "password")
    ctype_c, body_c = build_multipart(
        {"classification": "SECRET", "summary": "Charlie verified sector 9 sensor"},
        file_field=("attachment", "sensor-log.txt", b"Sector 9 tactical sensor log payload"),
    )
    c_status, c_text = http_request(
        f"{BASE_URL}/api/records",
        method="POST",
        headers={"Authorization": f"Bearer {charlie_token}", "Content-Type": ctype_c},
        data=body_c,
    )
    assert c_status == 200, f"KC-07 POST failed: {c_status} {c_text}"
    created = json.loads(c_text)
    assert created.get("s3_object_key", "").startswith(("gs://", "s3://")), f"KC-07 storage key missing: {created}"

    r_status, r_text = http_request(
        f"{BASE_URL}/api/records",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert r_status == 200 and len(json.loads(r_text).get("records", [])) >= 1, f"KC-07 GET failed: {r_status}"
    print(f"[KC-07] Admin RBAC + Storage/DB Persistence ('charlie' -> {created['s3_object_key']}) [PASS]")
    passed += 1

    print("================================================================================")
    print(f"✅ ALL KEYCLOAK OIDC & APPLICATION INTEGRATION TESTS PASSED ({passed}/{total})")
    print("================================================================================")
    return 0

if __name__ == "__main__":
    sys.exit(main())
EOF

chmod +x ~/GitHub/${APP_NAME}/scripts/test-keycloak-integration.py
~/GitHub/${APP_NAME}/scripts/test-keycloak-integration.py
```

---

## 8. Step 7: Validate, Package & Promote Your Customer Application Using `gdc-iac-org` Principles

Because you are building a **customer-specific application**, your source code, manifests, and Helm chart **remain in your own Git repository (`~/GitHub/${APP_NAME}`)**—you do **not** push customer code into the public `gdc-iac-org` repository. Instead, you validate your repository against the `gdc-iac-org` architectural and OPA security policies (`~/GitHub/gdc-iac-org/policy/security.rego`), package a self-contained air-gap bundle (`dist/${APP_NAME}-gdc-airgap-bundle.tar.gz`) inside your own repository (stripping `manifests/gcp/`), and deploy it into your customer's `GDC-ag` environment.

### 8.1. Gate 1: Run Trivy Vulnerability & Misconfiguration Scans (`HIGH,CRITICAL`)

Before packaging your customer release bundle, scan your built images and repository filesystem using `docker`:

```bash
# 1. Scan built container images for HIGH and CRITICAL CVEs
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOME/.cache/trivy:/root/.cache/" aquasec/trivy:latest image \
  --severity HIGH,CRITICAL --ignore-unfixed "${REGISTRY_HOST}/${APP_NAME}-backend:latest"

docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOME/.cache/trivy:/root/.cache/" aquasec/trivy:latest image \
  --severity HIGH,CRITICAL --ignore-unfixed "${REGISTRY_HOST}/${APP_NAME}-frontend:latest"

# 2. Scan production Dockerfiles, source code, and Helm/K8s manifests for secrets, CVEs, and KSV-* misconfigurations
#    (Skipping manifests/gcp/ and dist/, since manifests/gcp/ is local emulation only and stripped from the bundle)
docker run --rm -v "$HOME/GitHub/${APP_NAME}:/workspace:ro" \
  -v "$HOME/.cache/trivy:/root/.cache/" aquasec/trivy:latest fs \
  --scanners vuln,secret,misconfig --severity HIGH,CRITICAL \
  --skip-dirs /workspace/manifests/gcp --skip-dirs /workspace/dist /workspace
```

### 8.2. Gate 2: Run the 4-Layer Offline Chart Validation Suite Directly on Your Repository

Validate `~/GitHub/${APP_NAME}/chart` directly inside your own repository against all four `gdc-iac-org` quality and security gates (referencing `~/GitHub/gdc-iac-org/policy/security.rego` read-only):

```bash
cd ~/GitHub/${APP_NAME}
mkdir -p ~/.local/bin && export PATH="$HOME/.local/bin:$PATH"

# Ensure helm-unittest, kubeconform, and conftest are installed in ~/.local/bin
helm plugin list 2>/dev/null | grep -q unittest || helm plugin install https://github.com/helm-unittest/helm-unittest.git --verify=false || true
if ! command -v kubeconform >/dev/null 2>&1; then
  curl -fsSL https://github.com/yannh/kubeconform/releases/latest/download/kubeconform-linux-amd64.tar.gz | tar -xz -C ~/.local/bin kubeconform
fi
if ! command -v conftest >/dev/null 2>&1; then
  CONFTEST_VER="0.56.0"
  curl -fsSL "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VER}/conftest_${CONFTEST_VER}_Linux_x86_64.tar.gz" | tar -xz -C ~/.local/bin conftest
fi

# Layer 1: Helm Lint & JSON Schema Validation (values.schema.json)
helm lint ./chart

# Layer 2: Helm Template Logic Unit Tests (tests/pattern_test.yaml)
helm unittest ./chart

# Layer 3: OpenAPI Structural Validation (kubeconform) for both Stage 5 (apps) and Stage 2 (gdc)
helm template "${APP_NAME}" ./chart --set gdc.enabled=false --set apps.enabled=true \
  | kubeconform -strict -ignore-missing-schemas -skip DBCluster,Bucket,Gateway,HTTPRoute -summary

helm template "${APP_NAME}" ./chart --set gdc.enabled=true --set apps.enabled=true \
  | kubeconform -strict -ignore-missing-schemas -skip DBCluster,Bucket,Gateway,HTTPRoute -summary

# Layer 4: OPA Rego Security Policy Validation (using gdc-iac-org/policy/security.rego read-only)
helm template "${APP_NAME}" ./chart --set gdc.enabled=false --set apps.enabled=true \
  | conftest test - --policy ~/GitHub/gdc-iac-org/policy/security.rego
```

### 8.3. Gate 3: Build a Self-Contained Air-Gap Release Bundle (`dist/`) in Your Own Repository

Create and run a packaging script (`scripts/package-airgap-release.sh`) inside `~/GitHub/${APP_NAME}` that:
1. Stages only production-ready assets (`manifests/apps/`, `manifests/gdc/`, `chart/`, `external_images.txt`, `README.md`) into `dist/${APP_NAME}/` while **stripping all GCP emulation files (`manifests/gcp/`)**.
2. Packages your Helm chart (`helm package ./chart`) into a versioned `.tgz` archive.
3. Saves your application images and third-party images (`external_images.txt`) into portable OCI image tarballs (`dist/${APP_NAME}/images/`) using `docker save`.
4. Generates a cryptographic **SHA-256 Bill of Materials (`BOM.txt`)** and compresses the release archive (`dist/${APP_NAME}-gdc-airgap-bundle.tar.gz`) for transfer across the customer's air gap:

```bash
cat << 'EOF' > ~/GitHub/${APP_NAME}/scripts/package-airgap-release.sh
#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="$(basename "${REPO_ROOT}")"
DIST_DIR="${REPO_ROOT}/dist/${APP_NAME}"
BUNDLE_TAR="${REPO_ROOT}/dist/${APP_NAME}-gdc-airgap-bundle.tar.gz"

echo "📦 Staging production GDC-ag bundle for ${APP_NAME} (stripping manifests/gcp/)..."
rm -rf "${DIST_DIR}" "${BUNDLE_TAR}"
mkdir -p "${DIST_DIR}/manifests" "${DIST_DIR}/charts" "${DIST_DIR}/images"

# 1. Copy ONLY production manifests (apps/ and gdc/) and Helm chart — NEVER copy manifests/gcp/
cp -r "${REPO_ROOT}/manifests/apps" "${DIST_DIR}/manifests/apps"
cp -r "${REPO_ROOT}/manifests/gdc"  "${DIST_DIR}/manifests/gdc"
cp -r "${REPO_ROOT}/chart"          "${DIST_DIR}/chart"
cp "${REPO_ROOT}/external_images.txt" "${DIST_DIR}/external_images.txt"
[ -f "${REPO_ROOT}/README.md" ] && cp "${REPO_ROOT}/README.md" "${DIST_DIR}/README.md"

# 2. Package the Stage 5 Helm Wrapper Chart into a versioned OCI .tgz archive
helm package "${REPO_ROOT}/chart" --destination "${DIST_DIR}/charts"

# 3. Export application container images using docker save
for COMPONENT in backend frontend; do
  IMG="${REGISTRY_HOST}/${APP_NAME}-${COMPONENT}:latest"
  TAR_FILE="${DIST_DIR}/images/${APP_NAME}-${COMPONENT}.tar"
  echo "  -> Saving ${IMG} to ${TAR_FILE}..."
  docker save -o "${TAR_FILE}" "${IMG}"
done

# 4. Generate cryptographic SHA-256 Bill of Materials (BOM.txt)
(
  cd "${DIST_DIR}"
  find . -type f ! -name "BOM.txt" -print0 | sort -z | xargs -0 sha256sum > BOM.txt
)

# 5. Create the final air-gap transfer tarball
tar -czf "${BUNDLE_TAR}" -C "${REPO_ROOT}/dist" "${APP_NAME}"
sha256sum "${BUNDLE_TAR}" > "${BUNDLE_TAR}.sha256"

echo "=================================================================="
echo "✅ Air-Gap Bundle Created : ${BUNDLE_TAR}"
echo "✅ SHA-256 Checksum       : $(cat "${BUNDLE_TAR}.sha256")"
echo "=================================================================="
EOF

chmod +x ~/GitHub/${APP_NAME}/scripts/package-airgap-release.sh
~/GitHub/${APP_NAME}/scripts/package-airgap-release.sh
```

### 8.4. Gate 4: Ingest & Deploy Your Customer Bundle on Physical `GDC-ag` (`docker`, `helm`, `kubectl`)

After transferring `${APP_NAME}-gdc-airgap-bundle.tar.gz` across the air gap to the customer's high-side **GDC-ag Operator Workstation**, the Application Operator (**AO**) verifies the SHA-256 checksum, pushes the images and Helm chart into the customer's **GDC Managed Harbor** registry (`harbor.infra.gdc.local/customer-apps`), and deploys the application across the **Zone Admin Context** (Stage 2) and **User Cluster Context** (Stage 5):

```bash
# ============================================================================
# High-Side GDC-ag Operator Workstation (Strictly docker, helm, and kubectl)
# ============================================================================
export APP_NAME="p15-sovereign-mission-app"
export HARBOR_REGISTRY="harbor.infra.gdc.local/customer-apps"
export NAMESPACE="mission-app"

# 1. Verify cryptographic integrity and extract the customer release bundle
sha256sum -c "${APP_NAME}-gdc-airgap-bundle.tar.gz.sha256"
tar -xzf "${APP_NAME}-gdc-airgap-bundle.tar.gz"
cd "${APP_NAME}" && sha256sum -c BOM.txt

# 2. Load container images and push to the customer's GDC Managed Harbor registry
docker login harbor.infra.gdc.local
helm registry login harbor.infra.gdc.local

for TAR_FILE in images/*.tar; do
  LOADED_IMG=$(docker load -i "${TAR_FILE}" | awk '/Loaded image:/ {print $3}')
  IMG_BASENAME="${LOADED_IMG##*/}"
  docker tag "${LOADED_IMG}" "${HARBOR_REGISTRY}/${IMG_BASENAME}"
  docker push "${HARBOR_REGISTRY}/${IMG_BASENAME}"
done

# Push the packaged Helm chart to Harbor OCI
helm push charts/${APP_NAME}-*.tgz "oci://${HARBOR_REGISTRY}/charts"

# 3. Stage 2 (Zone Admin API Context): Provision Zonal HA PostgreSQL DBCluster & Object Bucket
#    (Or declare them in your customer's downstream foundations/ tenant YAML)
kubectl --context="${ZONE_ADMIN_CONTEXT}" apply -f manifests/gdc/resources.yaml -n "${NAMESPACE}"

# 4. Stage 5 (User Cluster Context): Deploy the Application Workloads via Helm
helm --kube-context="${USER_CLUSTER_CONTEXT}" upgrade --install "${APP_NAME}" \
  "oci://${HARBOR_REGISTRY}/charts/${APP_NAME}" \
  --namespace "${NAMESPACE}" --create-namespace \
  --set global.projectId="${NAMESPACE}" \
  --set global.namespace="${NAMESPACE}" \
  --set global.registry="${HARBOR_REGISTRY}" \
  --set gdc.enabled=false \
  --set apps.enabled=true \
  --set apps.keycloakUrl="http://keycloak-svc:8080/auth/realms/gdc-app-realm" \
  --set apps.s3Endpoint="https://objectstorage.gdc.goog" \
  --set apps.bucketName="${APP_NAME}-bucket"
```

<details>
<summary><b>Optional: Orchestrating Your Customer Chart via a Downstream Customer <code>foundations/</code> Environment</b></summary>

If your customer uses the `gdc-iac-org/foundations/` Helmfile landing zone in their own downstream environment repository, they reference your chart directly from their Harbor OCI registry (or your customer Git repository) inside their `tenant-1.yaml`—without modifying the upstream `gdc-iac-org` repository:

```yaml
# Customer's downstream foundations environment (tenant-1.yaml)
prd:
  gdc_tenants:
    tenant-1:
      projects:
        - name: "mission-app"
          resources:
            # Stage 2 (2-resources): Provisioned on Zone Admin API Context
            buckets:
              - name: "p15-sovereign-mission-app-bucket"
                description: "Sovereign Mission Attachment Storage"
                storage_class: "Standard"
                location: "zone1"
            dbs:
              - name: "p15-sovereign-mission-app-db"
                engine: "PostgreSQL"
                version: "15"
                highAvailability: true
                storageSize: "50Gi"
                extensions: ["vector"]
            # Stage 5 (5-workload-factory): Deployed on User Cluster Context from Customer Harbor OCI
            patterns:
              - name: "keycloak-sso"
                pattern: "p12-keycloak"
                namespace: "mission-app"
                registry: "harbor.infra.gdc.local/gdc-iac"
                deploy_gdc_resources: false
                deploy_apps: true
              - name: "sovereign-mission-app"
                pattern: "p15-sovereign-mission-app"
                chart_path: "oci://harbor.infra.gdc.local/customer-apps/charts/p15-sovereign-mission-app"
                namespace: "mission-app"
                registry: "harbor.infra.gdc.local/customer-apps"
                deploy_gdc_resources: false
                deploy_apps: true
                values:
                  apps:
                    keycloakUrl: "http://keycloak-svc:8080/auth/realms/gdc-app-realm"
                    s3Endpoint: "https://objectstorage.gdc.goog"
                    bucketName: "p15-sovereign-mission-app-bucket"
```
</details>

---

## Appendix A: Complete Platform Administrator Guide — Provisioning & Bootstrapping the Cloud Workstation + GKE Environment

This section provides the complete, step-by-step instructions for a **Platform Administrator (PA)** to set up a Google Cloud Workstation and GKE Stepping-Stone environment from scratch so that Application Developers opening their Cloud Workstation in the browser have a pre-configured `~/.kube/config`, `~/.docker/config.json`, `helm`, `helmfile`, `kubectl`, and Google Cloud Storage (`gs://`) Workload Identity bucket ready to use.

### A.1. How Google Cloud Workstations Bootstrapping Works

Google Cloud Workstations uses a 3-tier resource hierarchy:
1. **Workstation Cluster (`gcloud workstations clusters`)**: The regional control plane and VPC gateway inside your GCP project.
2. **Workstation Configuration (`gcloud workstations configs`)**: A template defining the VM machine type (`e2-standard-8`), the container image (`code-oss`), a **Persistent Disk (`100 GB` mounted at `/home`)**, and the **VM Service Account (`gdc-workstation-dev-sa`)**.
3. **Workstation Instance (`gcloud workstations`)**: The individual developer's dedicated workstation VM.

#### How the Developer's Environment Is Automatically Bootstrapped
- **Persistent `/home/user` Directory:** Cloud Workstations mounts a dedicated Persistent Disk at `/home` (`/home/user`). Any files written to `/home/user/.kube/config`, `/home/user/.docker/config.json`, `/home/user/.local/bin`, and `/home/user/.bashrc` **persist across workstation restarts**.
- **Two Supported Bootstrap Methods for Platform Administrators:**
  - **Method 1 (Stock Predefined Image + One-Time Remote Bootstrap via `gcloud workstations ssh` — Fastest for Single Workstations):** The PA uses Google's predefined `code-oss` image, starts the workstation, and executes a one-time bootstrap script over `gcloud workstations ssh` that populates `/home/user/.kube/config`, `/home/user/.docker/config.json`, `helm`, `helmfile`, `kubeconform`, and `conftest` on the persistent disk.
  - **Method 2 (Custom Workstation Container Image with `/etc/workstation-startup.d/` — Best for Multi-Developer Teams):** Cloud Workstations automatically executes any script inside `/etc/workstation-startup.d/` whenever a workstation container boots. By building a thin custom image on top of `code-oss` containing `/etc/workstation-startup.d/110_gdc_bootstrap.sh`, every workstation spun up from the Workstation Configuration automatically configures `kubectl`, `docker`, and `helm` on boot with zero manual intervention.

---

### A.2. Step 1: Enable GCP APIs & Create the Workstation IAM Service Account (`gdc-workstation-dev-sa`)

Run these commands from **Google Cloud Shell** or an admin workstation with `Owner` / `Editor` + `Project IAM Admin` permissions:

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION="${REGION:-us-east4}"
export ZONE="${ZONE:-us-east4-a}"
export CLUSTER_NAME="${CLUSTER_NAME:-gdc-stepping-stone}"
export AR_REPO_NAME="${AR_REPO_NAME:-blueprint-images}"
export WS_CLUSTER_NAME="${WS_CLUSTER_NAME:-gdc-dev-ws-cluster}"
export WS_CONFIG_NAME="${WS_CONFIG_NAME:-gdc-dev-ws-config}"
export WS_INSTANCE_NAME="${WS_INSTANCE_NAME:-gdc-dev-ws-01}"
export WS_SA_NAME="gdc-workstation-dev-sa"
export WS_SA_EMAIL="${WS_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export DEVELOPER_EMAIL="${DEVELOPER_EMAIL:-developer@example.com}" # Replace with developer's Google identity

# 1. Enable required GCP APIs (GKE, Cloud Workstations, Artifact Registry, Cloud Storage, IAM)
gcloud services enable \
  container.googleapis.com \
  workstations.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iamcredentials.googleapis.com \
  --project="${PROJECT_ID}"

# 2. Create the dedicated Service Account attached to the Cloud Workstation VM
gcloud iam service-accounts describe "${WS_SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud iam service-accounts create "${WS_SA_NAME}" \
  --display-name="GDC Developer Cloud Workstation SA" \
  --project="${PROJECT_ID}"

# 3. Grant least-privilege roles so the workstation can access GKE, push to Artifact Registry, and use GCS
for ROLE in \
  "roles/container.developer" \
  "roles/artifactregistry.writer" \
  "roles/storage.objectAdmin" \
  "roles/logging.logWriter" \
  "roles/monitoring.metricWriter"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${WS_SA_EMAIL}" \
    --role="${ROLE}" \
    --condition=None --quiet >/dev/null
done
```

---

### A.3. Step 2: Provision the GKE Stepping-Stone Cluster, Artifact Registry & GCS Workload Identity

```bash
export ENABLE_GPUS="${ENABLE_GPUS:-false}" # Set "true" for 2x NVIDIA L4 GPU cluster
export APP_NAME="${APP_NAME:-p15-sovereign-mission-app}"
export NAMESPACE="${NAMESPACE:-mission-app}"
export BUCKET_NAME="${APP_NAME}-files-${PROJECT_ID}"
export APP_GSA_NAME="${APP_NAME}-sa"
export APP_GSA_EMAIL="${APP_GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# 1. Create the Artifact Registry Docker repository
gcloud artifacts repositories describe "${AR_REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud artifacts repositories create "${AR_REPO_NAME}" \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}"

# 2. Create the GKE Cluster (with Workload Identity, Dataplane V2, and Standard Gateway API)
if ! gcloud container clusters describe "${CLUSTER_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  if [ "${ENABLE_GPUS}" = "true" ]; then
    gcloud container clusters create "${CLUSTER_NAME}" \
      --project "${PROJECT_ID}" --zone "${ZONE}" --release-channel "regular" \
      --enable-dataplane-v2 --gateway-api=standard --workload-pool "${PROJECT_ID}.svc.id.goog" \
      --machine-type "g2-standard-24" --accelerator "type=nvidia-l4,count=2,gpu-driver-version=LATEST" \
      --num-nodes 1 --disk-size=300 --node-labels="app=vllm-26b"
    gcloud container node-pools create client-pool \
      --cluster "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}" \
      --machine-type "e2-standard-4" --num-nodes 2 --node-labels="app=client" --quiet
  else
    gcloud container clusters create "${CLUSTER_NAME}" \
      --project "${PROJECT_ID}" --zone "${ZONE}" --release-channel "regular" \
      --enable-dataplane-v2 --gateway-api=standard --workload-pool "${PROJECT_ID}.svc.id.goog" \
      --machine-type "e2-standard-4" --num-nodes 2 --disk-size=100 --node-labels="app=client"
  fi
fi

# 3. Create Regional Managed Proxy subnet & firewall rule required by GKE Gateway API (gke-l7-rilb)
if [ -z "$(gcloud compute networks subnets list --filter="region:${REGION} AND purpose:REGIONAL_MANAGED_PROXY" --format="value(name)" --project="${PROJECT_ID}")" ]; then
  gcloud compute networks subnets create "gke-gateway-proxy-${REGION}" \
    --purpose=REGIONAL_MANAGED_PROXY --role=ACTIVE --region="${REGION}" \
    --network=default --range=172.16.2.0/23 --project="${PROJECT_ID}"
fi

gcloud compute firewall-rules create allow-gateway-internal \
  --network=default --direction=INGRESS --priority=1000 --action=ALLOW \
  --rules=tcp:80,tcp:443,tcp:8000,tcp:8080,tcp:8081 \
  --source-ranges=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,35.191.0.0/16,130.211.0.0/22 \
  --project="${PROJECT_ID}" 2>/dev/null || true

# 4. Pre-provision the Google Cloud Storage bucket & GKE Workload Identity binding for the developer
gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud storage buckets create "gs://${BUCKET_NAME}" \
  --project="${PROJECT_ID}" --location="${REGION}" --uniform-bucket-level-access

gcloud iam service-accounts describe "${APP_GSA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
gcloud iam service-accounts create "${APP_GSA_NAME}" \
  --display-name="GDC App GCS Workload Identity SA" --project="${PROJECT_ID}"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${APP_GSA_EMAIL}" --role="roles/storage.objectAdmin" --quiet >/dev/null

gcloud iam service-accounts add-iam-policy-binding "${APP_GSA_EMAIL}" \
  --project="${PROJECT_ID}" --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${APP_GSA_NAME}]" --quiet >/dev/null
```

---

### A.4. Step 3: Create the Cloud Workstation Cluster, Configuration & Developer Instance

```bash
# 1. Create the Cloud Workstation Cluster (~10-15 minutes on first creation)
if ! gcloud workstations clusters describe "${WS_CLUSTER_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud workstations clusters create "${WS_CLUSTER_NAME}" \
    --region="${REGION}" \
    --network="projects/${PROJECT_ID}/global/networks/default" \
    --subnetwork="projects/${PROJECT_ID}/regions/${REGION}/subnetworks/default" \
    --project="${PROJECT_ID}"
fi

# 2. Create the Workstation Configuration (e2-standard-8, 100GB persistent /home disk, attached WS_SA_EMAIL)
if ! gcloud workstations configs describe "${WS_CONFIG_NAME}" \
  --cluster="${WS_CLUSTER_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud workstations configs create "${WS_CONFIG_NAME}" \
    --cluster="${WS_CLUSTER_NAME}" \
    --region="${REGION}" \
    --machine-type="e2-standard-8" \
    --pd-disk-size=100 \
    --pd-disk-type="pd-balanced" \
    --service-account="${WS_SA_EMAIL}" \
    --container-predefined-image="code-oss" \
    --project="${PROJECT_ID}"
fi

# 3. Create the Developer's Workstation Instance and grant IAM access to the Developer
if ! gcloud workstations describe "${WS_INSTANCE_NAME}" \
  --cluster="${WS_CLUSTER_NAME}" --config="${WS_CONFIG_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud workstations create "${WS_INSTANCE_NAME}" \
    --cluster="${WS_CLUSTER_NAME}" \
    --config="${WS_CONFIG_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"
fi

gcloud workstations add-iam-policy-binding "${WS_INSTANCE_NAME}" \
  --cluster="${WS_CLUSTER_NAME}" \
  --config="${WS_CONFIG_NAME}" \
  --region="${REGION}" \
  --member="user:${DEVELOPER_EMAIL}" \
  --role="roles/workstations.user" \
  --project="${PROJECT_ID}"
```

---

### A.5. Step 4: Bootstrap the Developer's Cloud Workstation Environment (`~/.kube/config`, `~/.docker/config.json`, `helm`, `helmfile`)

Choose **Method 1** (one-time remote bootstrap over `gcloud workstations ssh` into the persistent `/home/user` disk) or **Method 2** (custom workstation container image with `/etc/workstation-startup.d/110_gdc_bootstrap.sh` for automated fleet bootstrapping).

#### Method 1: One-Time Remote Bootstrap into Persistent `/home/user` (No Custom Image Required)

```bash
# 1. Start the developer's workstation
gcloud workstations start "${WS_INSTANCE_NAME}" \
  --cluster="${WS_CLUSTER_NAME}" \
  --config="${WS_CONFIG_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}"

# 2. Push the one-time bootstrap script over gcloud workstations ssh into /home/user
gcloud workstations ssh "${WS_INSTANCE_NAME}" \
  --cluster="${WS_CLUSTER_NAME}" \
  --config="${WS_CONFIG_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --command="bash -s" <<EOF
set -euo pipefail
mkdir -p ~/.local/bin ~/GitHub

# A. Install GKE auth plugin (if not pre-installed) and populate ~/.kube/config
gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}"

# B. Populate ~/.docker/config.json for Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# C. Install helm, helm-unittest, kubeconform, and conftest into persistent ~/.local/bin
export PATH="\$HOME/.local/bin:\$PATH"
if ! command -v helm >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | USE_SUDO=false HELM_INSTALL_DIR="\$HOME/.local/bin" bash
fi
helm plugin list 2>/dev/null | grep -q unittest || helm plugin install https://github.com/helm-unittest/helm-unittest.git --verify=false || true
if ! command -v kubeconform >/dev/null 2>&1; then
  curl -fsSL https://github.com/yannh/kubeconform/releases/latest/download/kubeconform-linux-amd64.tar.gz | tar -xz -C "\$HOME/.local/bin" kubeconform
fi
if ! command -v conftest >/dev/null 2>&1; then
  curl -fsSL https://github.com/open-policy-agent/conftest/releases/download/v0.56.0/conftest_0.56.0_Linux_x86_64.tar.gz | tar -xz -C "\$HOME/.local/bin" conftest
fi

# D. Persist environment variables in ~/.bashrc so every terminal opens pre-configured
grep -q "GDC_WORKSTATION_BOOTSTRAPPED" ~/.bashrc || cat << 'BRC' >> ~/.bashrc
# GDC_WORKSTATION_BOOTSTRAPPED
export PATH="\$HOME/.local/bin:\$PATH"
export PROJECT_ID="${PROJECT_ID}"
export REGION="${REGION}"
export ZONE="${ZONE}"
export NAMESPACE="${NAMESPACE}"
export REGISTRY_HOST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}"
BRC

echo "✅ Developer Cloud Workstation persistent /home/user environment bootstrapped!"
EOF
```

<details>
<summary><b>Method 2 (Recommended for Teams): Custom Workstation Image with <code>/etc/workstation-startup.d/110_gdc_bootstrap.sh</code></b></summary>

If you are onboarding a team of developers and want **every new workstation** created from `${WS_CONFIG_NAME}` to automatically configure `~/.kube/config`, `~/.docker/config.json`, `helm`, `kubeconform`, `conftest`, and per-developer namespace defaults on startup without running `gcloud workstations ssh`, build a thin custom workstation image containing `/etc/workstation-startup.d/110_gdc_bootstrap.sh`:

```bash
mkdir -p /tmp/gdc-ws-image && cd /tmp/gdc-ws-image

cat << 'EOF' > 110_gdc_bootstrap.sh
#!/bin/bash
# Executed automatically by Cloud Workstations on container startup.
# Supports both single-developer and multi-developer shared-GKE-cluster teams:
# if workstation is named 'ws-alice', DEV_ID resolves to 'alice' and NAMESPACE to 'dev-alice'.
su - user -c '
  export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
  export REGION="'"${REGION}"'"
  export ZONE="'"${ZONE}"'"
  export CLUSTER_NAME="'"${CLUSTER_NAME}"'"
  export AR_REPO_NAME="'"${AR_REPO_NAME}"'"
  DEV_ID=$(hostname | sed "s/^ws-//")
  export NAMESPACE="dev-${DEV_ID}"

  if [ -n "${PROJECT_ID}" ]; then
    gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}" 2>/dev/null || true
    kubectl config set-context --current --namespace="${NAMESPACE}" 2>/dev/null || true
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet 2>/dev/null || true
  fi
'
EOF

cat << 'EOF' > Dockerfile
FROM us-central1-docker.pkg.dev/cloud-workstations-images/predefined/code-oss:latest
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    curl -fsSL https://github.com/yannh/kubeconform/releases/latest/download/kubeconform-linux-amd64.tar.gz | tar -xz -C /usr/local/bin kubeconform && \
    curl -fsSL https://github.com/open-policy-agent/conftest/releases/download/v0.56.0/conftest_0.56.0_Linux_x86_64.tar.gz | tar -xz -C /usr/local/bin conftest
COPY 110_gdc_bootstrap.sh /etc/workstation-startup.d/110_gdc_bootstrap.sh
RUN chmod +x /etc/workstation-startup.d/110_gdc_bootstrap.sh
EOF

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}/gdc-workstation-ide:latest" .
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}/gdc-workstation-ide:latest"

# Update the Workstation Configuration to use the custom image
gcloud workstations configs update "${WS_CONFIG_NAME}" \
  --cluster="${WS_CLUSTER_NAME}" \
  --region="${REGION}" \
  --container-custom-image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}/gdc-workstation-ide:latest" \
  --project="${PROJECT_ID}"
```
</details>

---

### A.6. Option: Onboarding a Team of Developers Sharing One GKE Cluster

A team of developers (each with their own dedicated Cloud Workstation instance, e.g., `ws-alice`, `ws-bob`, `ws-charlie`) can **share a single GKE Stepping-Stone cluster** (`${CLUSTER_NAME}`). Sharing one GKE cluster is strongly recommended for teams because it amortizes control-plane and scarce **NVIDIA GPU (`nvidia-l4` / `a100`)** capacity across the entire team while closely mirroring multi-tenant User Clusters on physical `GDC-ag` (see **[Section 2.5](#25-dedicated-cluster-vs-shared-team-gke-cluster-key-workflow-differences)** for how developer day-to-day commands, `kubectl port-forward`, and Gateway API VIPs behave on a shared cluster).

#### Multi-Developer Shared GKE Cluster Design Rules

1. **Shared Cluster-Wide Services (Deployed Once by the PA):**
   - **One GKE Cluster (`${CLUSTER_NAME}`):** Sized with an autoscaled CPU `client-pool` (e.g., `--enable-autoscaling --min-nodes=2 --max-nodes=8` of `e2-standard-8`) plus a shared GPU pool (if using AI).
   - **One Shared GPU LLM Gateway (`gemma-inference`):** Deploy `gdc_gemma_gw` **once** in namespace `gemma-inference` (**Section 3.4, Option A**). Every developer's app calls `http://gemma-gateway.gemma-inference.svc.cluster.local/v1`—preventing multiple developers from exhausting GPU scheduling quota.
   - **One Shared Artifact Registry (`blueprint-images`):** Developers prefix `APP_NAME` with their developer ID (e.g., `alice-mission-app`, `bob-mission-app`) so pushing `:latest` never overwrites a teammate's container image.
   - **VPC Internal Load Balancer Quota Awareness:** Each per-namespace `Gateway` (`gke-l7-rilb`) consumes one GCP Regional Internal Forwarding Rule; for larger teams ($> 8$ developers), either request an Internal Forwarding Rule quota increase or deploy a single shared `Gateway` with per-developer `HTTPRoute` `hostnames` (**Section 2.5**).
2. **Per-Developer Tenant Isolation (`dev-<developer_id>`):**
   - **Dedicated Cloud Workstation (`ws-<dev_id>`):** Gives each developer an isolated persistent `/home` disk, Docker daemon, and local `kubectl port-forward` / Web Preview port space (`8081`).
   - **Dedicated Kubernetes Namespace (`dev-<dev_id>`) + `ResourceQuota` + Namespace RBAC (`RoleBinding`):** Prevents noisy-neighbor CPU/memory starvation, keeps each developer's `postgres`, `keycloak`, `gdc-gateway-tunnel`, and Helm releases isolated, and optionally restricts developer write permissions strictly to their own `dev-<dev_id>` namespace.
   - **Dedicated GCS Bucket & Workload Identity Binding:** Scopes `roles/iam.workloadIdentityUser` strictly to `serviceAccount:${PROJECT_ID}.svc.id.goog[dev-<dev_id>/<dev_id>-mission-app-sa]`.

#### Platform Administrator Team Onboarding Script (One Shared GKE Cluster, Multiple Developers)

After provisioning the single shared GKE cluster (**Step A.3**) and Workstation Configuration (**Step A.4** / **Step A.5 Method 2**), run this loop to onboard each developer onto the shared cluster:

```bash
# Scale the shared GKE CPU client-pool with autoscaling for multi-developer concurrency
gcloud container clusters update "${CLUSTER_NAME}" \
  --zone="${ZONE}" --project="${PROJECT_ID}" \
  --node-pool="default-pool" --enable-autoscaling --min-nodes=2 --max-nodes=8 2>/dev/null || true

gcloud container clusters get-credentials "${CLUSTER_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}"

# List of developers to onboard: "<dev_id>:<google_email>"
TEAM_MEMBERS=(
  "alice:alice@example.com"
  "bob:bob@example.com"
  "charlie:charlie@example.com"
)

for ENTRY in "${TEAM_MEMBERS[@]}"; do
  DEV_ID="${ENTRY%%:*}"
  DEV_EMAIL="${ENTRY#*:}"
  DEV_WS="ws-${DEV_ID}"
  DEV_NS="dev-${DEV_ID}"
  DEV_APP="${DEV_ID}-mission-app"
  DEV_BUCKET="${DEV_APP}-files-${PROJECT_ID}"
  DEV_GSA="${DEV_APP}-sa"
  DEV_GSA_EMAIL="${DEV_GSA}@${PROJECT_ID}.iam.gserviceaccount.com"

  echo "=== Onboarding developer '${DEV_ID}' (${DEV_EMAIL}) onto shared cluster ${CLUSTER_NAME} ==="

  # 1. Create isolated Kubernetes Namespace + ResourceQuota + Namespace-Scoped RBAC RoleBinding
  kubectl create namespace "${DEV_NS}" --dry-run=client -o yaml | kubectl apply -f -
  cat <<EOF | kubectl apply -n "${DEV_NS}" -f -
apiVersion: v1
kind: ResourceQuota
metadata:
  name: dev-namespace-quota
spec:
  hard:
    requests.cpu: "6"
    requests.memory: 16Gi
    limits.cpu: "12"
    limits.memory: 24Gi
    persistentvolumeclaims: "5"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: dev-${DEV_ID}-namespace-edit
subjects:
- kind: User
  name: "${DEV_EMAIL}"
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: edit
  apiGroup: rbac.authorization.k8s.io
EOF

  # 2. Provision per-developer GCS bucket & GKE Workload Identity binding scoped to ${DEV_NS}
  gcloud storage buckets describe "gs://${DEV_BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${DEV_BUCKET}" \
    --project="${PROJECT_ID}" --location="${REGION}" --uniform-bucket-level-access

  gcloud iam service-accounts describe "${DEV_GSA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "${DEV_GSA}" \
    --display-name="GDC Dev (${DEV_ID}) GCS Workload Identity SA" --project="${PROJECT_ID}"

  gcloud storage buckets add-iam-policy-binding "gs://${DEV_BUCKET}" \
    --member="serviceAccount:${DEV_GSA_EMAIL}" --role="roles/storage.objectAdmin" --quiet >/dev/null

  gcloud iam service-accounts add-iam-policy-binding "${DEV_GSA_EMAIL}" \
    --project="${PROJECT_ID}" --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${DEV_NS}/${DEV_GSA}]" --quiet >/dev/null

  # 3. Create the developer's dedicated Cloud Workstation instance (ws-<dev_id>) and grant access
  if ! gcloud workstations describe "${DEV_WS}" \
    --cluster="${WS_CLUSTER_NAME}" --config="${WS_CONFIG_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud workstations create "${DEV_WS}" \
      --cluster="${WS_CLUSTER_NAME}" --config="${WS_CONFIG_NAME}" --region="${REGION}" --project="${PROJECT_ID}"
  fi

  gcloud workstations add-iam-policy-binding "${DEV_WS}" \
    --cluster="${WS_CLUSTER_NAME}" --config="${WS_CONFIG_NAME}" --region="${REGION}" \
    --member="user:${DEV_EMAIL}" --role="roles/workstations.user" --project="${PROJECT_ID}" --quiet >/dev/null

  echo "✅ Ready: Workstation '${DEV_WS}' -> Shared Cluster '${CLUSTER_NAME}' (Namespace: '${DEV_NS}', Bucket: 'gs://${DEV_BUCKET}')"
done
```
