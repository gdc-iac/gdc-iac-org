Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 7: Agentic Data Analyst

**Use Case:** LLM Agent querying a SQL database securely. This agent acts as a data analyst, capable of querying structured databases to answer natural language questions (e.g., "How many units did we sell in the last quarter?").

## Architecture Schematic

```
+----------------------+
|      End User        |
+----------------------+
         |
         v
+----------------------+
| GKE Service          |
| (SQL Agent Service)  |
+----------------------+
         |
    +----+-----------------------+
    |                            |
    v                            v
+------------------------+   +------------------------+      +----------------------+
| Gemma Inference GW     |   | GDC AI Inference GW    |----->| GDC Database Service |
| (gdc_gemma_gw / vLLM)  |   | (Gemini 3.5/3.1 Flash) |      | (PostgreSQL HA)      |
+------------------------+   +------------------------+      +----------------------+
                                         ^
                                         |
                                         | (Read-Only Credentials)
                                         v
                              +----------------------+
                              | GDC KMS              |
                              +----------------------+
```

> [!NOTE]
> **LLM Provider Integration**: This pattern interfaces directly with either the **Gemma Inference Gateway** (`gdc_gemma_gw` / vLLM / Ollama) or **GDC Gemini AI Gateway**. Legacy proxy gateways (Pattern 5) are deprecated and no longer required.

## Design & Resilience Strategy

1.  **Agent Service:** A microservice deployed on a **GDC GKE Cluster**.
2.  **Logic (OSS):** The service runs the **Agent Development Kit (ADK)**, an OSS framework optimized for GDC. ADK implements the ReAct loop and uses **Model Context Protocol (MCP)** for tool integration (SQL toolkit) and **Agent2Agent (A2A)** for communication.
3.  **Target Database:** The agent is given secure, read-only access to a production or replica database, such as the **GDC Database Service (PostgreSQL HA)**.
4.  **Security:** The agent's database credentials are securely injected from **GDC KMS**.
5.  **Agent Logic (ReAct):**
    *   User asks a question.
    *   The agent service (ADK) calls the **Resilient Hybrid LLM Gateway (Archetype 5)** to *reason* and *plan* (e.g., "I need to write and execute a SQL query").
    *   The agent *acts* by using its SQL toolkit to execute the query against the **GDC Database Service**.
    *   It gets the raw data result (e.g., [5,482]).
    *   It calls the **Resilient Hybrid LLM Gateway** again to *reason* and synthesize the raw data into a natural language answer (e.g., "You sold 5,482 units in the last quarter.").
6.  **Resilience:** The agent service is stateless and replicated on GKE. The LLM brain (the Gateway) is resilient, and the target database is a managed, HA GDC service.

## Day 0 Prerequisites (Air-Gap Transfer)

As ADK, A2A, and MCP are open-source components, they must be ingested into the GDC-ag environment before use:
1.  **Source Code/Libraries:** Download the ADK, A2A, and MCP libraries from GitHub/PyPI.
2.  **Packaging:** Package them as Python wheels or container images.
3.  **Transfer:** Scan and transfer the artifacts to the internal GDC repositories (Harbor for images, internal PyPI for libraries) via the standard Day 0 supply chain process.

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Supports approx. 50 concurrent users (complex SQL queries).

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SQL Agent** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-2-8` (Managed) | 2 | 8Gi | 50Gi | No |

**Scaling & Upgrades:**
*   **Database:** Monitor query execution time. If slow, optimize indexes or upgrade the Managed Database instance to `db-custom-4-16`.
*   **Agent Service:** Use HPA to scale the agent pods.
*   **LLM Latency:** If response times are slow, check the LLM Gateway (Pattern 5) performance or switch to a faster model (e.g., Gemini Flash).

**Sizing Rationale:**
The SQL Agent is a lightweight API wrapper. Database sizing assumes a standard analytical workload; complex queries on large datasets would require vertical scaling.

## Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL> -d p7-agentic-data-analyst
```

## Required IAM Permissions

**1. User Permissions:**
To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **GKE Developer:** To deploy the agent's Deployment and Secret to the GKE cluster.
    *   `roles/gke.developer`

**2. Agent Runtime Permissions:**
The service account used by the `sql-agent` pods will need permissions to access the resources it queries. This includes:

*   **Database Access:** Read-only access to the target SQL database. This is handled via the Kubernetes secret in this pattern, but in a production scenario, you might grant the Kubernetes Service Account a GDC IAM role (e.g., via `gdcloud iam service-accounts add-iam-policy-binding`) for database access.
*   **LLM Gateway Access:** Network access to the LLM Gateway service (Pattern 5).

## Implementation

### Step 1: Deploy Database

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

# 1. Create Managed Database Cluster
gdcloud database clusters create postgres-db \
  --project=$PROJECT_ID --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA
```

**Option B: GitOps**

Sync the `manifests/gdc/db/postgres.yaml` file to your cluster.

### Step 2: Create Read-Only Credentials

*Security Note: Never give an LLM agent admin DB credentials.*

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

kubectl create secret generic db-ro-creds \
  --namespace=$PROJECT_ID \
  --from-literal=username=analyst_ro \
  --from-literal=password='<SECURE_PASSWORD>' \
  --from-literal=host='postgres-db'
```

**Option B: GitOps**

Sync the `manifests/gdc/security/db-secret.yaml` file to your cluster.

### Step 3: Initialize Database Schema

The agent requires a specific database schema and sample data to analyze.

**For GDC Production (PostgreSQL HA):**
You must manually apply the schema and seed data to your GDC Database Service instance.

1.  Connect to your database instance using `psql`.
2.  Run the following SQL commands:

    ```sql
    -- 1. Create Table
    CREATE TABLE IF NOT EXISTS sales (
        id SERIAL PRIMARY KEY,
        date DATE,
        amount DECIMAL
    );

    -- 2. Seed Data (if empty)
    INSERT INTO sales (date, amount) VALUES 
    ('2023-01-01', 100), ('2023-01-02', 150), ('2023-01-03', 200),
    ('2023-01-04', 130), ('2023-01-05', 170);
    ```

### Step 4: Deploy Agent

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/apps/sql-agent.yaml
```

**Option B: GitOps**

Sync the `manifests/apps/sql-agent.yaml` file to your cluster.

## Testing


### Standard Testing
This pattern includes scripts to help validate the artifacts and verify a successful deployment. The scripts are located in the `test/` directory.

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

This will run the configuration tests and the verification logic for all patterns.
## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p7-agentic-data-analyst
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p7-agentic-data-analyst
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p7-agentic-data-analyst-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p7-agentic-data-analyst-gdc-images.tar` (The bundled container images)
    *   `p7-agentic-data-analyst-BOM.txt` and `p7-agentic-data-analyst-manifest.txt` (Integrity checksums)
    *   `p7-agentic-data-analyst-README.md` (Standalone deployment instructions)

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
   ./scripts/unpack-for-gdc.sh p7-agentic-data-analyst-gdc-images.tar harbor.gdc.local/library
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
   tar -xzf p7-agentic-data-analyst-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

5. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.

---

## Advanced Configuration: Identity Management

By default, Pattern 7 utilizes a lightweight "Mock Auth" system intended strictly for feature validation and testing. The architecture itself is completely decoupled from any single Identity Provider (IdP). 

If you wish to advance this architecture to a state of production-readiness or require multi-tenant access control for "multiple users", you can seamlessly overlay Keycloak via standard OIDC.

For step-by-step instructions on integrating this pattern with the **P12-Keycloak** blueprint, please refer to the dedicated [Keycloak Integration Guide](../docs/keycloak_integration_guide.md).
