Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Gemma Client - Multi-User Chat Interface

**Use Case:** A multi-user chatbot interface for **Gemma 4** models in a GDC air-gapped environment. This pattern provides a direct wrapper around the **Gemma Inference Gateway**, allowing users to chat, upload documents, and ground reasoning tasks securely. It supports model selection, chat history persistence, and role-based access control (RBAC).

## Architecture Schematic

```
                             [ User Browser / Client App User ]
                                          │
                                          ▼
                    [ GDC PLATFORM HLB / GATEWAY (app.gdc.local) ]
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │ (/auth)                   │ (/api)                    │ (/)
              ▼                           ▼                           ▼
         [ Keycloak ]             [ gemma-client Backend ] ◄── [ gemma-client Frontend ]
                                    (FastAPI, Port 8000)          (React+Vite, Port 80)
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
           [ GDC Database ]        [ GDC Storage ]    [ Gemma 4 Gateway Proxy ]
             (PostgreSQL)             (Object)           (Inference Gateway)
            (Chat History)        (Uploaded Files) (gemma-gateway.gemma-inference)
```

## Design & Resilience Strategy

This pattern describes a modern, resilient, multi-user chatbot for a GDC-ag environment.

1.  **Direct Context Grounding:** Unlike RAG (Pattern 6), this pattern loads the full content of selected documents into the context window. This ensures higher accuracy for reasoning over specific documents but is limited by the model's context size.
2.  **Multi-User & RBAC:** Supports multiple users with isolated chat histories and personal file storage. Administrators can manage shared resources.
3.  **Stateless Compute & Resilience:** The frontend and backend are stateless, scalable, and resilient. Session data, chat histories, and uploads persist securely under managed GDC platform services (**GDC Database Service (PostgreSQL)** and **GDC Storage (Object)**).
4.  **Model Selection Override:** Users can manually lock their prompt queries to target a specific model variant (the efficient `26B MoE` or the high-capacity `31B Dense` variant) natively from the header select menu dropdown.
5.  **Smart Prompt Routing & Dynamic UI Sync:** By leaving the selector on **`Auto / Generic (gemma4)`**, queries route dynamically. The backend gateway parses query complexity (math, programming, logic) and redirects to the most appropriate GPU pod dynamically. The React frontend automatically intercepts the resolved serving model tag returned in the OpenAI response envelope, and **refreshes its header model badge dynamically in real-time** (flipping between **`MoE (26B)`** and **`Dense (31B)`**), giving users transparent feedback of the server's dynamic routing decisions.
    *   *Reference Details*: Proceed deeply into the master architectural guide: **[docs/model_routing_architecture.md](../docs/model_routing_architecture.md)**.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The React frontend image and FastAPI backend image must be built, scanned, and pushed to the internal GDC registry (Harbor).
2.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
3.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

The table below outlines the cluster resource requirements to support varying levels of concurrent user sessions on the chat client.

### 1. 100 Concurrent Users
| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Backend** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-2-8` (Managed) | 2 | 8Gi | 50Gi | No |

### 2. 500 Concurrent Users
| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend** | 2 x `n2-standard-4-gdc` | 8 | 32Gi | N/A | No |
| **Backend** | 2 x `n2-standard-4-gdc` | 8 | 32Gi | N/A | No |
| **Database** | `db-custom-4-16` (Managed) | 4 | 16Gi | 250Gi | No |

### 3. 1000 Concurrent Users
| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend** | 4 x `n2-standard-4-gdc` | 16 | 64Gi | N/A | No |
| **Backend** | 4 x `n2-standard-4-gdc` | 16 | 64Gi | N/A | No |
| **Database** | `db-custom-8-32` (Managed) | 8 | 32Gi | 500Gi | No |

**Sizing Rationale:**
Frontend and Backend sizing uses HPA for horizontal pod scaling to comfortably handle user queries and WebSocket connections. Database sizing supports history retrieval and user metadata without I/O starvation.

> [!TIP]
> **ARCHITECTURAL COMPLIANCE REPORT:**
> The entire client and database scaling sizing matrix has been physically audited, verified, and signed off under GDC-ag standard machine mappings! Proceed deeply into the master engineering report: **[docs/resource-sizing-validation.md](../docs/resource-sizing-validation.md)**.

## Configuration

### Environment Variables

The following environment variables can be configured in `manifests/apps/backend.yaml`:

| Variable | Description | Default / GDC Example |
| :--- | :--- | :--- |
| `PROJECT_ID` | Your Google Cloud Project ID. | `your-project-id` |
| `INPUT_BUCKET` | GCS Bucket for uploaded files. | `gs://gemma-client-files-${PROJECT_ID}` |
| `DATABASE_URL` | Connection string for PostgreSQL. | From Secret: `gemma-client-db-credentials` |
| `GATEWAY_URL` | Endpoint for Gemma Inference Gateway. | **GCP:** `http://gemma-gateway.gemma-inference.svc.cluster.local/v1` |
| `GEMMA_MODEL` | Gemma Model ID. | `gemma4:26b` |

### GUI Model Configuration

The Gemma models available in the GUI dropdown and the default selected model are hardcoded in the frontend React application. 

**Changing the Default Model**

To change the default model selected when the application loads, modify `src/frontend/src/App.jsx`:

1. Open `src/frontend/src/App.jsx`.
2. Locate the `selectedModel` state initialization (around line 13):
   ```javascript
   const [selectedModel, setSelectedModel] = useState('gemma4:26b');
   ```
3. Change `'gemma4:26b'` to the desired default model ID.

**Adding or Removing Model Selections in the Dropdown**

To change the list of available models in the dropdown, modify the `Header` component:

1. Open `src/frontend/src/components/Header.jsx`.
2. Locate the `models` array definition (around line 11):
   ```javascript
   const models = [
     { id: 'gemma4:26b', name: 'Gemma 4 26B A4B (MoE)' },
     { id: 'gemma4:31b', name: 'Gemma 4 31B (Dense)' }
   ];
   ```
3. Add or remove objects from this array. The `id` must match the model ID expected by the backend and Gemma Inference Gateway API, and the `name` is the display label in the dropdown.

### Gateway URL Configuration

The backend service needs to know where to send requests for the Gemma Inference Gateway. This is controlled by the `GATEWAY_URL` environment variable in the backend deployment manifests.

**Configuring the Endpoint**

To change or set the `GATEWAY_URL`, you must update the Kubernetes manifests for the backend deployment.

1. Open `manifests/apps/backend.yaml` (and/or `manifests/gdc/apps/backend.yaml` if deploying to GDC).
2. Locate the `env` section under the container definition.
3. Uncomment or add the `GATEWAY_URL` environment variable:
   ```yaml
   env:
   # ... other variables ...
   - name: GATEWAY_URL
     value: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
   ```

### Blueprint Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -n <YOUR_NAMESPACE> -r <YOUR_REGISTRY_URL> -d gemma-client
```

## Required IAM Permissions

This pattern requires permissions for both the **user** deploying the application and the **service account** the application runs as.

**1. User Permissions:**
To deploy the resources, your user account will need the following GDC IAM roles:

*   **IAM Admin:** To create a new service account (`gemma-client-sa`) and grant it project-level roles.
    *   `roles/iam.serviceAccountAdmin`
    *   `roles/project.iamAdmin`
*   **GKE Developer:** To deploy the Deployment and ServiceAccount to the GKE cluster.
    *   `roles/gke.developer`

**2. Service Account Permissions:**
The `gemma-client-sa` service account itself will be granted the following roles by the user during setup, which it uses at runtime to call other GDC services:

*   **Storage Object Admin** (for accessing the GDC Storage bucket)

## Implementation

### Step 1: Configure IAM

You must explicitly grant your workloads permission to use GDC Storage.

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

kubectl create sa gemma-client-sa -n $PROJECT_ID
# Example for GDC Storage access (adjust role as needed for your specific GDC version)
gdcloud iam service-accounts add-iam-policy-binding gemma-client-sa --project=$PROJECT_ID --role=roles/storage.objectAdmin
```

**Option B: GitOps**

Sync the `manifests/gdc/iam/` files (if available) to your cluster.

### Step 2: Deploy Database

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

# 1. Create Managed Database Cluster
gdcloud database clusters create gemma-client-db \
  --project=$PROJECT_ID --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA

# 2. Create Connection Secret
# Retrieve the IP address of your new DB instance and create the secret
# DB_HOST=$(gdcloud database clusters describe gemma-client-db --project=$PROJECT_ID --format="value(primaryInstance.ipAddress)")
# kubectl create secret generic gemma-client-db-credentials \
#   --namespace=$PROJECT_ID \
#   --from-literal=connection_string="postgresql://postgres:password@$DB_HOST:5432/postgres"
```

**Option B: GitOps**

Sync the `manifests/gdc/db/postgres.yaml` file to your cluster.

### Step 3: Initialize Database Schema

The application requires a specific database schema to store chat history and file metadata.

**Schema Definition:**
The schema includes three tables: `chats`, `messages`, and `files`. It also requires the `uuid-ossp` extension. You can find the reference SQL definition in `manifests/gcp/postgres-configmap.yaml`.

**For GDC Production (PostgreSQL):**
You must manually apply the schema to your GDC Database Service instance.

1.  Connect to your PostgreSQL instance using `psql`.
2.  Run the following SQL commands:

    ```sql
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    CREATE TABLE IF NOT EXISTS chats (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id VARCHAR(255) NOT NULL,
        title TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
        role VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS files (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id VARCHAR(255),
        filename VARCHAR(255) NOT NULL,
        gcs_path TEXT NOT NULL,
        file_size_bytes BIGINT,
        content_type VARCHAR(100),
        uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        is_shared BOOLEAN DEFAULT FALSE
    );

    CREATE INDEX idx_chats_user_id ON chats(user_id);
    CREATE INDEX idx_messages_chat_id ON messages(chat_id);
    CREATE INDEX idx_files_user_id ON files(user_id);
    ```

### Step 4: Deploy Application

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/gdc/apps/backend.yaml
kubectl apply -f manifests/gdc/apps/frontend.yaml
```

**Option B: GitOps**

Sync the `manifests/gdc/apps/` directory to your cluster using Config Sync or Argo CD.

## Testing

### Validation (Pre-deployment)

The `validate.sh` script performs a client-side dry run of all Kubernetes manifests to check for syntactical errors.

To run the validation:
```bash
cd test/
chmod +x validate.sh
./validate.sh
```

### Verification (Post-deployment)

The `verify.sh` script checks the status of the deployed GKE resources.

To run the verification:
```bash
cd test/
chmod +x verify.sh
./verify.sh
```

### Local Testing

You can run the validation and verification scripts locally using the provided test runner, which mocks the GDC and Kubernetes CLI commands.

```bash
# Run from the root of the repository
bash tests/run-local.sh
```

### 🔐 Secure Identity Staging: Keycloak OIDC Authentication
By default, the client quickstart deploys in a simplified "Mock Auth" mode, allowing dropdown persona selections. To secure dynamic user sessions and emulate GDC zero-trust, transition the client to OIDC via Keycloak.

We resolve the browser's sandboxed iframe cookies restrictions (the Workstation preview proxy returning `403 Forbidden` on session iframes) by establishing:
1. **Unified Port Ingress Proxy**: Exposing both Frontend (`/`), API endpoints (`/api/`), and Keycloak (`/auth/`) on a **single port (Port `8081`)** inside GKE, satisfying browser CORS.
2. **Automated Realm Import (GitOps Standard)**: Preloading and importing the realm config map on Keycloak startup, bypassing Master Admin UI console hangs.

Refer to the newly staged master blueprints and scripts to run the integration:
*   **[gcp-sandbox-keycloak-testing-strategy.md](../docs/gcp-sandbox-keycloak-testing-strategy.md)**: Dynamic sequence flows, GKE Staging (Nginx) vs. GDC-ag Production (Gateway API) structural matrix, and DNS optimizations.
*   **[configure-keycloak.sh](scripts/configure-keycloak.sh)**: Interactive configurator to dynamically discover your workstation preview subdomains, stage hydrated manifests, and bake frontend `.env` parameters.

## Troubleshooting

### Resetting the Environment

If you need to wipe all data and start fresh (e.g., to clear old chat history or reset the database), run the following commands:

```bash
# 1. Clear GCS Bucket (WARNING: Deletes all uploaded files)
# Ensure BUCKET_NAME is set
gcloud storage rm -r ${BUCKET_NAME}/**

# 2. Clear Database Tables (WARNING: Deletes all chat history and users)
# Connect to your GDC Database Service instance and run:
# TRUNCATE users, chats, messages, documents;

# 3. Restart Pods (to reset any in-memory state if applicable)
# kubectl delete pod -n <YOUR_NAMESPACE> -l app=backend
```

### Sandbox Staging Troubleshoot Gotchas

#### 1. Chromium Browser Cache Retention (The Chrome Hard Reload Trick)
Chromium browsers aggressively cache static Vite/React Javascript and CSS assets. If you rollout changes (like OIDC flags) but the UI does not update:
1. Open the preview tab targeting Port 8081.
2. Open Developer Tools by pressing **`F12`** (keep the panel open!).
3. **Right-Click** (or click and hold) on browser's circular **Reload (Refresh) button** next to the URL bar.
4. Click the third option: **"Empty Cache and Hard Reload"**!
*(This evicts the disk cache for the specific domain, forcing Chrome to pull the up-to-date static Javascript bundles).*

#### 2. GKE GPU Regional Stock Shortages & Registry Alignment
GKE regional pools can sometimes encounter dynamic hardware stock exhaustions (Nvidia L4 GPUs completely out-of-stock in your default zone e.g. `us-central1-a`). To bypass this, operators are forced to spin up cluster pools inside alternative GCP regions (e.g. `us-west4-b`).

**The Registry Synchronization Clash**: If you are forced to shift GKE cluster coordinates (e.g., from `us-central1` to `us-west4`), **you MUST update your Artifact Registry region coordinates symmetrically (`REGISTRY_HOST` variable)**!
If you fail to do this, your build script will push new dynamic containers to the central repository, but GKE will continue to pull from the old `us-west4` repository, running yesterday's stale baseline layers without OIDC flags!
*   **The Fix**: Symmetrically map all target regions inside your build environment before building:
    `export PROJECT_ID="grace-playground"`
    `export REGISTRY_HOST="us-west4-docker.pkg.dev/${PROJECT_ID}/gemma-repo"`
    `./gemma-client/scripts/build.sh -p $PROJECT_ID -r $REGISTRY_HOST`

#### 3. In-Memory Database Recycles (Table Not Found Errors)
H2 in-memory databases (`dev-mem` vendor) discard dynamic RAM schemas once active connection pools drop to `0` (which occurs during startup assemble completions), causing welcome pages queries to return `Table "USER_ENTITY" not found`.
*   **The Fix**: Force the GKE connection pool to keep at least one connection active permanently by setting:
    `KC_DB_POOL_MIN_SIZE=1`
    This preserves your tables across transient startup recycles and boot events.

#### 4. Command-Line Truncation Loops (Picocli Crashes on Startup)
Keycloak's container start wrapper `kc.sh` evaluates options using UNIX shell expansions and `eval`. Passing connection URLs containing semi-colons splits the execution stream, truncating the Java launch and crashing the container.
*   **The Fix**: Avoid using `KC_DB_URL` with semi-colons inside the YAML env array! Use `KC_DB_POOL_MIN_SIZE=1` to keep memory DBs alive instead, or pass H2 parameters under `KC_DB_URL_PROPERTIES`.
```

## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d gemma-client
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh gemma-client
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `gemma-client-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `gemma-client-gdc-images.tar` (The bundled container images)
    *   `gemma-client-BOM.txt` and `gemma-client-manifest.txt` (Integrity checksums)
    *   `gemma-client-README.md` (Standalone deployment instructions)

*(Note: Unlike the infrastructure-heavy patterns, this robust pattern does not strictly require complex 3rd-party external Helm charts or images dropped into the `artifacts/` pool via the dependencies script—it is cleanly self-contained in the 3 standard `.tar` / `.txt` files above).*

### 4. Unpack and Deploy
Once transferred to your secure GDC environment, you must unpack and deploy the assets logically:

> **Optional: Hot-Patching Manifests Offline**
> If you need to deploy this pattern to a *different* namespace, project ID, or registry host than the one you originally injected during the pre-packaging step, you do not need to resend the payload across the air-gap. You can dynamically hot-patch the extracted manifests locally:
> ```bash
> # Define your old (packaged) and new (target) variables
> OLD_PROJECT="<PACKAGED_PROJECT_ID>"
> NEW_PROJECT="<NEW_PROJECT_ID>"
> OLD_NAMESPACE="<PACKAGED_NAMESPACE>"
> NEW_NAMESPACE="<NEW_NAMESPACE>"
> OLD_REGISTRY="<PACKAGED_REGISTRY_HOST>"
> NEW_REGISTRY="<NEW_REGISTRY_HOST>"
> 
> # Recursively execute string replacement across all extracted YAML files
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_PROJECT}|${NEW_PROJECT}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_NAMESPACE}|${NEW_NAMESPACE}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_REGISTRY}|${NEW_REGISTRY}|g" {} +
> ```


1. **Load and Push Local Container Images:** Extrapolate the locally-built images into your secure internal registry:
   ```bash
   ./scripts/unpack-for-gdc.sh gemma-client-gdc-images.tar harbor.gdc.local/library
   ```

2. **Load and Push Global Container Images (If Applicable):** For blueprints bridging global components (e.g. Hashicorp Vault, external pipelines), manually load and tag the artifacts using standard Docker commands:
   ```bash
   docker load -i artifacts/external-dependencies/images/...
   docker tag ... harbor.gdc.local/library/...
   docker push ...
   ```

3. **Extract and Apply Kubernetes Manifests:** Extract the exact blueprints generated during the `-d` inject step and apply them to your cluster:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf gemma-client-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

4. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.
