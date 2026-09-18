Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 1: Resilient 3-Tier Web Application

**Use Case:** Standard web app requiring separation of concerns: Presentation (Web), Logic (App), and Data (DB).

## Architecture Schematic

```
+----------------------+
|      End User        |
+----------------------+
         |
         v
+----------------------+\      +-------------------------+
|     GDC Gateway      |----->|   Web Tier (Nginx)      |
|    (Gateway API)     |      |   (3 Replicas)          |
+----------------------+\      +-------------------------+
                                         |
                                         v
                              +-------------------------+
                              | GKE Service (ClusterIP) |
                              |      (logic-svc)        |
                              +-------------------------+
                                         |
                                         v
+-------------------------+\      +-------------------------+
| App/Logic Tier (API)    |<---->| GDC Database Service    |
|   (2 Replicas)          |      | (PostgreSQL HA Cluster) |
+-------------------------+\      +-------------------------+
         ^
         |
         v
+-------------------------+
| GDC KMS                 |
+-------------------------+
```

### Target Cluster Type
The target cluster type on GDC fundamentally impacts how Load Balancing works:  
**Standard Clusters (Project-Scoped):** Provide Application Operators (AOs) full control over `Gateway` creation and LB provisioning. Because they are project-scoped, AOs can configure both Internal Load Balancers (ILBs) for intra-project communication and External Load Balancers (ELBs).    
**Shared Clusters (Org-Scoped):** Managed by Platform Administrators. While `Gateway` resources are supported, underlying routing is part of the managed multi-tenant fabric. 

The use of  of a Gateway API should default to targeting **Standard Clusters** on GDC to ensure AOs maintain control over the load balancer provisioning path.

## Design and Resilience Pattern

1.  **Web/Presentation Tier:**
    *   **GDC Platform Service:** Deployed as a containerized workload (e.g., Nginx, Apache) on a **GDC GKE Cluster**.
    *   **Resilience:** Achieved by running multiple replicas of the web server pods managed by a GKE Deployment.
    *   The **Kubernetes Gateway API** (`Gateway` and `HTTPRoute`) manages external traffic, providing robust routing and load balancing to the web tier service.

2.  **Application/Logic Tier:**
    *   **GDC Platform Service:** Deployed as a containerized application (e.g., Java Spring Boot, Python Flask, Go) on the same **GDC GKE Cluster**.
    *   **Resilience:** GKE Deployments manage multiple replicas of the application pods. Horizontal Pod Autoscaling (HPA) can be used to scale pods based on CPU/memory. Communication with the web tier and database tier is managed via GKE Services.
    *   **Sizing:** Recommended node pool machine type: `n2-standard-4-gdc`.
3.  **Data Tier:**
    *   **GDC Platform Service:** A stateful workload using the **GDC Database Service**. For this pattern, a high-availability **PostgreSQL** cluster is provisioned.
    *   **Resilience:** The GDC Database Service manages the cluster's replication (e.g., primary-standby). The [High availability configuration](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/db-configure-ha) allows manual failover to the standby replica.
4.  **Storage (Static Assets):**
    *   **GDC Platform Service:** Static assets (images, CSS, JS) are stored in a **GDC Storage** bucket (Object Storage).
    *   **Resilience:** GDC Object Storage provides built-in data durability and redundancy within the GDC instance.
5.  **Security:**
    *   **GDC Platform Service:** Application secrets (API keys, DB credentials) are stored and managed by the **GDC KMS**. The GDC Database Service integrates with KMS for encryption at rest.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The Web Tier (e.g., Nginx) and App Tier container images must be built, scanned, and pushed to the internal GDC registry (Harbor).
2.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
3.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Supports approx. 1,000+ concurrent users (depending on application logic complexity).

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Web Tier** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **App Tier** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-2-8` (Managed) | 2 | 8Gi | 50Gi | No |

**Scaling & Upgrades:**
*   **Storage:** Monitor Database storage usage. Resize the instance storage when usage exceeds 70%.
*   **Compute:** Use Horizontal Pod Autoscaling (HPA) for Web and App tiers. If CPU utilization consistently exceeds 80%, increase the `maxReplicas` in the HPA configuration.
*   **Database:** For higher concurrency (>2,000 users), upgrade the Managed Database instance to `db-custom-4-16` or higher to handle increased connection counts and query load.

**Sizing Rationale:**
These estimates are based on typical resource consumption for stateless web/application servers handling moderate concurrency. The database size allows for high availability overhead and initial dataset growth.

## Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL> -d p1-resilient-3-tier-webapp
```

## Required IAM Permissions

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Database Admin:** To provision the PostgreSQL HA cluster.
    *   `roles/db.cluster.creator`
*   **GKE Developer:** To deploy applications, services, and load balancers to the GKE cluster.
    *   `roles/gke.developer`

## Implementation

### Step 1: Provision Data Tier (HA Database)

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

gdcloud database clusters create tier3-db \
  --project=$PROJECT_ID \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=2 --memory=8Gi --storage-size=50Gi
```

**Option B: GitOps**

Sync the `manifests/gdc/db/tier3-db.yaml` file (already configured by the script) to your cluster.

### Step 2: Initialize Database Schema

The application requires a specific database schema to store todo items.

**For GDC Production (PostgreSQL HA):**
You must manually apply the schema to your GDC Database Service instance.

1.  Connect to your database instance using `psql`.
2.  Run the following SQL commands:

    ```sql
    CREATE TABLE IF NOT EXISTS todos (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        completed BOOLEAN NOT NULL
    );
    ```

### Step 3: Deploy Application Tier (Business Logic)

*Prerequisite: Database must be READY so the secret `tier3-db-credentials` exists.*

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/apps/app-tier.yaml
```

**Option B: GitOps**

Sync the `manifests/apps/app-tier.yaml` file to your cluster.

### Step 4: Deploy Web Tier & Gateway

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/apps/web-tier.yaml
kubectl apply -f manifests/apps/gateway.yaml
```

**Option B: GitOps**

Sync the `manifests/apps/web-tier.yaml` and `manifests/apps/gateway.yaml` files to your cluster.

## Testing



### Standard Testing
This pattern includes scripts to help validate the artifacts and verify a successful deployment. The scripts are located in the `test/` directory.

### Validation (Pre-deployment)

The `validate.sh` script performs a client-side dry run of all Kubernetes manifests to check for syntactical errors.

To run the validation:
```bash
cd test/
chmod +x validate.sh
./validate.sh
```

### Verification (Post-deployment)

The `verify.sh` script checks the status of the deployed GDC and GKE resources.

To run the verification:
```bash
cd test/
chmod +x verify.sh
### Local Testing

You can run the validation and verification scripts locally using the provided test runner, which mocks the GDC and Kubernetes CLI commands.

```bash
# Run from the root of the repository
bash tests/run-local.sh
```

This will run the configuration tests and the verification logic for all patterns (or you can modify the script to run only this pattern).

## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p1-resilient-3-tier-webapp
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p1-resilient-3-tier-webapp
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p1-resilient-3-tier-webapp-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p1-resilient-3-tier-webapp-gdc-images.tar` (The bundled container images)
    *   `p1-resilient-3-tier-webapp-BOM.txt` and `p1-resilient-3-tier-webapp-manifest.txt` (Integrity checksums)
    *   `p1-resilient-3-tier-webapp-README.md` (Standalone deployment instructions)

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
   ./scripts/unpack-for-gdc.sh p1-resilient-3-tier-webapp-gdc-images.tar harbor.gdc.local/library
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
   tar -xzf p1-resilient-3-tier-webapp-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

5. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.
