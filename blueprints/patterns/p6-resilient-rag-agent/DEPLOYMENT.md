Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Next Steps Plan: Pattern 6 (Gemini Adaptation) - Clean Start

**Objective:** Deploy and verify the `p6-resilient-rag-agent` with Gemini integration from first principles, ensuring all infrastructure and identity components are correctly configured on a fresh cluster.

## 1. Environment Preparation (First Principles)
*   **Cluster:** Create a fresh GKE cluster (Standard or Autopilot, as per GDC requirements).
*   **Workstation:** Ensure all commands are run from the **Repository Root** on your **Google Cloud Workstation**.
*   **Tools:** Ensure `gcloud`, `kubectl`, and `docker` are authenticated and available.
*   **Variables:** Define consistent environment variables at the start of the session:
    ```bash
    export PROJECT_ID="<your-project-id>"
    export REGION="us-central1"
    export CLUSTER_NAME="<your-cluster-name>"
    export NAMESPACE="test-project"
    export GSA_NAME="rag-sa"
    export KSA_NAME="rag-sa"
    export BUCKET_NAME="gs://raw-docs-${PROJECT_ID}"
    export EMBEDDING_MODEL="text-embedding-004"
    ```

## 2. Infrastructure & Identity Setup (Automated)
Run the configuration script to set up Workload Identity, Service Accounts, and IAM roles:

```bash
./scripts/configure-workload-identity.sh
```

**What this script does:**
1.  Creates the `${NAMESPACE}` (test-project).
2.  Creates the KSA (`rag-sa`).
3.  Creates the GSA (`rag-sa@${PROJECT_ID}.iam.gserviceaccount.com`).
4.  Grants `roles/storage.objectAdmin` and `roles/aiplatform.user` to the GSA.
5.  Binds the GSA to the KSA (Workload Identity).
6.  Annotates the KSA.

## 3. Storage Setup
1.  **Create Bucket:** Ensure the bucket `${BUCKET_NAME}` exists and is unique.
2.  **Upload Test Data:** Upload a sample file (`test.txt` or `sample.pdf`) to verify access.

## 4. Application Configuration
1.  **Secrets:**
    *   **Configure Blueprints:** Run the configuration script to set your Project ID and Namespace.
        > **IMPORTANT:** You MUST specify `-n test-project` for Pattern 6, otherwise the namespace will default to your Project ID, breaking the setup.
        ```bash
        ./configure-blueprints.sh -p ${PROJECT_ID} -n test-project -d p6-resilient-rag-agent
        ```
    *   **DB Credentials:** Run the secrets generation script:
        ```bash
        ./scripts/create-secrets.sh
        ```
    *   **Gemini API Key (Optional):** If you are using Workload Identity (recommended), this is **not required**. If you prefer to use an API Key:
        ```bash
        kubectl create secret generic gemini-secrets \
            --from-literal=api-key="YOUR_GEMINI_API_KEY" \
            --namespace=test-project
        ```
2.  **Manifest Update:** Ensure `ingest-job.yaml` references:
    *   The correct `serviceAccountName: rag-sa`.
    *   The correct `INPUT_BUCKET` value (`${BUCKET_NAME}`).
    *   The correct `EMBEDDING_MODEL` value (`${EMBEDDING_MODEL}`).
    *   The correct image tag (`imagePullPolicy: Always` is good for dev).

## 5. Deployment & Verification
1.  **Deploy Postgres:**
    *   Apply the Secret: (Handled by `./scripts/create-secrets.sh`)
    *   Apply the StatefulSet: `kubectl apply -f p6-resilient-rag-agent/manifests/gcp/statefulset-postgres.yaml`
    *   Wait for Postgres to be ready: `kubectl wait --for=condition=ready pod -l app=postgres -n test-project --timeout=60s`
2.  **Deploy Ingestion Job:** Apply `p6-resilient-rag-agent/manifests/apps/ingest-job.yaml`.
    *   **Note:** The ingestion application (`app.py`) automatically initializes the database (creates `vector` extension and `documents` table) upon startup. No manual SQL setup is required.
3.  **Monitor:**
    *   Check Pod status: `kubectl get pods -n test-project`.
    *   Check Logs: `kubectl logs -l job-name=manual-ingest-test -n test-project -f`.
    *   **Success Criteria:** Logs show "Using Native GCS...", "Processing...", and "Indexed...".
4.  **Deploy Query Service (Agentic RAG):**
    *   Apply the Deployment: `kubectl apply -f p6-resilient-rag-agent/manifests/apps/query-service.yaml`
    *   Apply the Service: (Included in the yaml)
    *   **Verification:**
        *   Port-forward: `kubectl port-forward service/query-service 8080:80 -n test-project`
        *   Test Query: `curl -X POST http://localhost:8080/query -H "Content-Type: application/json" -d '{"query": "What documents do you have?"}'`
        *   **Success Criteria:** Response includes `"thoughts"` array (Agentic reasoning) and `"answer"`.
        *   **Success Criteria:** Response includes `"thoughts"` array (Agentic reasoning) and `"answer"`.

## 7. GDC Production Deployment (Air-Gapped)

When deploying to the actual GDC environment, follow these adjustments:

1.  **Identity:**
    *   Do NOT use `./scripts/configure-workload-identity.sh` (this is for GCP).
    *   Use `gdcloud` to bind the Kubernetes Service Account (`rag-sa`) to the Project Service Account.
    *   Example: `gdcloud iam service-accounts add-iam-policy-binding ...` (See README.md).

2.  **Endpoints:**
    *   Update `GEMINI_ENDPOINT` in `manifests/apps/query-service.yaml` to point to your local GDC Vertex AI endpoint (e.g., `https://ai.gdc.example.com/v1/...`).
    *   Update `EMBEDDING_MODEL` if the model name differs (e.g., `text-embedding-gecko`).

3.  **Storage:**
    *   Ensure the `INPUT_BUCKET` exists in your GDC Object Storage.
    *   The application uses the S3-compatible protocol or GDC Storage Connector transparently.

4.  **Registry:**
    *   Push your Docker images (`rag-ingest`, `rag-query`) to the GDC Project Registry, not Google Artifact Registry.
    *   Update the `image:` fields in the manifests to point to the local registry.
## 6. Final Blueprint Verification
*   Run the full test suite for Pattern 6 to ensure no regressions.
*   Verify `app.py` logic handles both S3 (MinIO) and GCS paths correctly (hybrid support).

---
**Note for Co-Developer:**
*   **Do not auto-run `gcloud` commands.** Generate the exact commands for the user to copy-paste into their Workstation terminal.
*   **Wait for output.** After providing a command, explicitly wait for the user to paste the result before proceeding.
