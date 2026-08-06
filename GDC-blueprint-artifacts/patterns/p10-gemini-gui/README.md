Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 10: Gemini GUI Chatbot

**Use Case:** A multi-user chatbot interface for Google's Gemini models in a GDC air-gapped environment. This pattern provides a direct wrapper around Gemini, allowing users to upload documents (Text, PDF, Images) and load them directly into the model's context window for grounded responses. It supports model selection, chat history persistence, and role-based access control (RBAC).

## Architecture Schematic

```
+----------------------+      +----------------------+      +----------------------+
|      Frontend        |----->|      Backend         |----->|   Gemini (Vertex AI) |
|   (React + Vite)     |      |     (FastAPI)        |      |  (Model Inference)   |
+----------------------+      +----------------------+      +----------------------+
           ^                             |
           |                             v
           |                  +----------------------+
           |                  | GDC Database Service |
           |                  |    (PostgreSQL HA)   |
           |                  |    (Chat History)    |
           |                  +----------------------+
           |                             |
           |                             v
           |                  +----------------------+
           |                  |    GDC Storage       |
           |                  |       (Object)       |
           |                  |   (Uploaded Files)   |
           |                  +----------------------+
```

## Design & Resilience Strategy

This pattern describes a modern, resilient, multi-user chatbot for a GDC-ag environment.

1.  **Direct Context Grounding:** Unlike RAG (Pattern 6), this pattern loads the full content of selected documents into the Gemini context window. This ensures higher accuracy for reasoning over specific documents but is limited by the model's context size.
2.  **Multi-User & RBAC:** Supports multiple users with isolated chat histories and personal file storage. Administrators can manage shared resources.
3.  **Stateless Compute:** The frontend and backend are stateless and scalable. State is persisted in **GDC Database Service (PostgreSQL HA)** and **GDC Storage (Object)**.
4.  **Model Flexibility:** Users can select different Gemini models (e.g., Flash, Pro) based on their needs (speed vs. reasoning depth).
5.  **Resilience:** All dependencies (Storage, PostgreSQL, Gemini) are managed, high-availability GDC platform services.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The React frontend image and FastAPI backend image must be built, scanned, and pushed to the internal GDC registry (Harbor).
2.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
3.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Supports approx. 100+ concurrent users (chat interface).

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Backend** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-2-8` (Managed) | 2 | 8Gi | 50Gi | No |

**Scaling & Upgrades:**
*   **Backend:** Use HPA to scale the backend service based on CPU/Memory usage.
*   **Database:** Monitor storage usage (chat history and file metadata). Resize if usage exceeds 70%. Upgrade to `db-custom-4-16` if concurrent user count doubles.
*   **Storage:** GDC Object Storage scales automatically. Ensure sufficient quota is available for uploaded files.

**Sizing Rationale:**
Backend sizing accounts for handling file uploads and managing WebSocket connections. Database sizing ensures performant retrieval of chat history and user metadata.

## Configuration

### Environment Variables

The following environment variables can be configured in `manifests/apps/backend.yaml`:

| Variable | Description | Default / GDC Example |
| :--- | :--- | :--- |
| `PROJECT_ID` | Your Google Cloud Project ID. | `your-project-id` |
| `INPUT_BUCKET` | GCS Bucket for uploaded files. | `gs://gemini-gui-files-${PROJECT_ID}` |
| `DATABASE_URL` | Connection string for PostgreSQL. | From Secret: `gemini-gui-db-credentials` |
| `GEMINI_ENDPOINT` | Endpoint for Gemini API. | **GCP:** `https://us-central1-aiplatform.googleapis.com/...` <br> **GDC:** `https://<GDC_ENDPOINT>/v1/...` |
| `GEMINI_MODEL` | Gemini Model ID. | `gemini-2.5-flash` |

### GUI Model Configuration

The Gemini models available in the GUI dropdown and the default selected model are hardcoded in the frontend React application. 

**Changing the Default Model**

To change the default model selected when the application loads, modify `src/frontend/src/App.jsx`:

1. Open `src/frontend/src/App.jsx`.
2. Locate the `selectedModel` state initialization (around line 13):
   ```javascript
   const [selectedModel, setSelectedModel] = useState('gemini-2.5-flash');
   ```
3. Change `'gemini-2.5-flash'` to the desired default model ID.

**Adding or Removing Model Selections in the Dropdown**

To change the list of available models in the dropdown, modify the `Header` component:

1. Open `src/frontend/src/components/Header.jsx`.
2. Locate the `models` array definition (around line 11):
   ```javascript
   const models = [
     { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
     { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
     { id: 'gemini-3.0-flash-preview', name: 'Gemini 3.0 Flash (Preview)' },
     { id: 'gemini-3.0-pro-preview', name: 'Gemini 3.0 Pro (Preview)' },
   ];
   ```
3. Add or remove objects from this array. The `id` must match the model ID expected by the backend and Gemini API, and the `name` is the display label in the dropdown.

### Gemini Endpoint Configuration

The backend service needs to know where to send requests for the Gemini API. This is controlled by the `GEMINI_ENDPOINT` environment variable in the backend deployment manifests.

**Configuring the Endpoint**

To change or set the `GEMINI_ENDPOINT`, you must update the Kubernetes manifests for the backend deployment.

1. Open `manifests/apps/backend.yaml` (and/or `manifests/gdc/apps/backend.yaml` if deploying to GDC).
2. Locate the `env` section under the container definition.
3. Uncomment or add the `GEMINI_ENDPOINT` environment variable:
   ```yaml
   env:
   # ... other variables ...
   - name: GEMINI_ENDPOINT
     value: "us-central1-aiplatform.googleapis.com" # Or your GDC endpoint (e.g., https://<GDC_ENDPOINT>/v1/...)
   ```
   *Note: If testing against Vertex AI on GCP, use the appropriate regional endpoint. For a GDC air-gapped environment, use the provided local endpoint for the model.*

### Blueprint Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -n <YOUR_NAMESPACE> -r <YOUR_REGISTRY_URL> -d p10-gemini-gui
```

## Required IAM Permissions

This pattern requires permissions for both the **user** deploying the application and the **service account** the application runs as.

**1. User Permissions:**
To deploy the resources, your user account will need the following GDC IAM roles:

*   **IAM Admin:** To create a new service account (`gemini-gui-sa`) and grant it project-level roles.
    *   `roles/iam.serviceAccountAdmin`
    *   `roles/project.iamAdmin`
*   **GKE Developer:** To deploy the Deployment and ServiceAccount to the GKE cluster.
    *   `roles/gke.developer`

**2. Service Account Permissions:**
The `gemini-gui-sa` service account itself will be granted the following roles by the user during setup, which it uses at runtime to call other GDC services:

*   **Vertex AI User** (if using ADC for Gemini)
*   OR **API Key Access** (if using API Key secret)
*   **Storage Object Admin** (for accessing the GDC Storage bucket)

## Implementation

### Step 1: Configure IAM

You must explicitly grant your workloads permission to use GDC pre-trained APIs and Storage.

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

kubectl create sa gemini-gui-sa -n $PROJECT_ID
# Example for GDC Storage access (adjust role as needed for your specific GDC version)
gdcloud iam service-accounts add-iam-policy-binding gemini-gui-sa --project=$PROJECT_ID --role=roles/storage.objectAdmin
```

**Option B: GitOps**

Sync the `manifests/gdc/iam/` files (if available) to your cluster.

### Step 2: Deploy Database

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

# 1. Create Managed Database Cluster
gdcloud database clusters create gemini-db \
  --project=$PROJECT_ID --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA

# 2. Create Connection Secret
# Retrieve the IP address of your new DB instance and create the secret
# DB_HOST=$(gdcloud database clusters describe gemini-db --project=$PROJECT_ID --format="value(primaryInstance.ipAddress)")
# kubectl create secret generic gemini-gui-db-credentials \
#   --namespace=$PROJECT_ID \
#   --from-literal=connection_string="postgresql://postgres:password@$DB_HOST:5432/postgres"
```

**Option B: GitOps**

Sync the `manifests/gdc/db/postgres.yaml` file to your cluster.

### Step 3: Initialize Database Schema

The application requires a specific database schema to store chat history and file metadata.

**Schema Definition:**
The schema includes three tables: `chats`, `messages`, and `files`. It also requires the `uuid-ossp` extension. You can find the reference SQL definition in `manifests/gcp/postgres-configmap.yaml`.

**For GDC Production (PostgreSQL HA):**
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
kubectl delete pod -n <YOUR_NAMESPACE> -l app=backend
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
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p10-gemini-gui
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p10-gemini-gui
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p10-gemini-gui-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p10-gemini-gui-gdc-images.tar` (The bundled container images)
    *   `p10-gemini-gui-BOM.txt` and `p10-gemini-gui-manifest.txt` (Integrity checksums)
    *   `p10-gemini-gui-README.md` (Standalone deployment instructions)

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


1. **Authenticate Docker with Harbor:** Log in to your target GDC environment's Harbor registry:
   ```bash
   export REGISTRY_HOST="harbor.gdc.local"
   export ROBOT_NAME="robot\$puller"  # Escape the $ character
   export ROBOT_SECRET="your-robot-secret"

   docker login ${REGISTRY_HOST} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
   ```

2. **Load and Push Local Container Images:** Extrapolate the locally-built images into your secure internal registry:
   ```bash
   ./scripts/unpack-for-gdc.sh p10-gemini-gui-gdc-images.tar harbor.gdc.local/library
   ```

3. **Load and Push Global Container Images (If Applicable):** For blueprints bridging global components (e.g. Hashicorp Vault, external pipelines), manually load and tag the artifacts using standard Docker commands:
   ```bash
   docker load -i artifacts/external-dependencies/images/...
   docker tag ... harbor.gdc.local/library/...
   docker push ...
   ```

4. **Extract and Apply Kubernetes Manifests:** Extract the exact blueprints generated during the `-d` inject step and apply them to your cluster:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf p10-gemini-gui-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

5. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.
