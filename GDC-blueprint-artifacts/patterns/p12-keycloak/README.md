Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 12: Identity and Access Management (Keycloak)

**Use Case:** Centralized identity provider for applications running on GDC air-gapped environment, offering Single Sign-On (SSO), Role-Based Access Control (RBAC), and user federation.

## Architecture Schematic

```text
+----------------------+
| GKE Service          |
| (e.g. RAG Agent App) |
+----------------------+
           |
           | (OIDC / SAML)
           v
+----------------------+      (SQL / JDBC)      +----------------------+
| GKE Cluster          |----------------------->| GDC Database Service |
| (Keycloak IAM)       |                        | (PostgreSQL HA)      |
+----------------------+                        +----------------------+
```

## Design & Resilience Strategy

This pattern describes an enterprise-grade IAM solution for a GDC-ag environment, ensuring high availability and secure identity verification.

*   **Database Backend:** Uses the managed **GDC Database Service** to provision a highly available, replicated PostgreSQL database. This ensures resilient storage for users, realms, roles, and active session states against zonal failover. 
*   **Identity Service:** The Keycloak application runs as a horizontally scalable workload within a **GDC GKE Cluster**. Multiple replicas ensure the authentication service remains online during node maintenance or failure.
*   **Container Images:** All required container images (Keycloak and its database drivers) are mirrored to a local GDC Artifact Registry (`harbor.gdc.local`), adhering to the strict air-gapped constraints.
*   **Resilience:** Both the backend database (managed HA) and front-end identity gateway (GKE ReplicaSets) survive localized hardware degradation dynamically.
*   **Sizing:** Recommended node pool machine type for GKE workloads: `n2-standard-4-gdc`.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The official open-source Keycloak image (`quay.io/keycloak/keycloak:24.0.4`) must be pulled, scanned, and pushed to the internal GDC registry.
2.  **Configuration:** The declarative Kubernetes Deployment and Service manifests.
3.  **Transfer Process:** Use the provided pipeline scripts to package the native manifests and external dependencies into secure transit payloads.

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Supports 10,000+ active sessions with standard token rotation.

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Keycloak Agents** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-2-8` (Managed) | 2 | 8Gi | 100Gi | No |

**Scaling & Upgrades:**
*   **Database:** Session storage and persistent token states dictate database demands. If read/write thresholds exceed latency boundaries, upgrade to `db-custom-4-16`.
*   **Identity Service:** Utilize Horizontal Pod Autoscalers (HPA) to inflate the Keycloak pods linearly during authentication storms or mass credential rollover events.

## Configuration

### Blueprint Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -n <YOUR_TARGET_NAMESPACE> -r <YOUR_REGISTRY_URL> -d p12-keycloak
```

## Required IAM Permissions

To deploy the resources, your user account must hold the following GDC IAM roles:

*   **Database Admin:** To provision the PostgreSQL HA cluster.
    *   `roles/db.cluster.creator`
*   **GKE Developer:** To deploy the pure Kubernetes manifests and Application Pods to the target GKE cluster.
    *   `roles/gke.developer`

## Implementation

You can execute deployment using the automated GitOps cycle or manual execution approaches.

### Step 1: Deploy Database Backend
 
 **Option A: Manual (CLI)**
 
 ```bash
 export PROJECT_ID=<YOUR_PROJECT_ID>
 
 gdcloud database clusters create keycloak-db \
   --project=$PROJECT_ID --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA --cpu=2 --memory=8Gi --storage-size=100Gi
 ```
 
 **Option B: GitOps**
 
 Sync the `manifests/gdc/db/db-cluster.yaml` declarative configuration to your infrastructure repository.
 
### Step 2: Extract Database Secrets
Keycloak must connect securely to the database provisioned above to execute Schema migrations on startup.

```bash
# Wait for DB to be 'READY'. 
# This script specifically retrieves the managed connection string for Helm.
export DB_HOST=$(kubectl get secret keycloak-db-credentials -n my-gdc-project -o jsonpath='{.data.host}' | base64 -d)
export DB_PASSWORD=$(kubectl get secret keycloak-db-credentials -n my-gdc-project -o jsonpath='{.data.password}' | base64 -d)
```

### Step 3: Deploy Identity Application (Kubernetes Manifests)

The centralized Keycloak IAM Gateway is deployed utilizing pure, declarative Kubernetes manifests specifically aligned with GDC baseline constraints, avoiding any fragile 3rd-party vendor locking (e.g. Helm).

**Option A: Manual Execution**

```bash
# Ensure your active blueprint configuration has successfully injected the correct harbor domain
kubectl apply -f manifests/apps/keycloak.yaml -n my-gdc-project
```

**Option B: GitOps**
Ensure ArgoCD or ConfigSync is tracking the `manifests/apps/` directory within your isolated infrastructure repository to continuously synchronize the deployment.

## Testing

### Validation (Pre-deployment)
Ensure all external image logic correctly resolved utilizing the validation logic.
```bash
bash tests/run-local.sh
```

### Verification (Post-deployment)

To validate the integration on your target GDC environment, you can verify connectivity directly:

1. **Access the Console:** Either utilizing the designated GDC platform Gateway Ingress URL or a secure internal port-forward:
   ```bash
   # Opens a secure socket tunnel on Port 8080 mapping to Keycloak service Port 80
   kubectl port-forward svc/keycloak 8080:80 -n my-gdc-project
   ```

> [!WARNING]
> **DEVELOPMENT STAGING GOTCHA: THE WORKSTATIONS PREVIEW ANOMALY**
> If you are validating this blueprint inside a **Google Cloud Workstation Web Preview** environment, you cannot access the Keycloak administration welcome panel. 
> 
> **Why?** Keycloak's React Admin UI initializes a dynamic session-checking iframe. To prevent clickjacking, this iframe is running under strict sandboxing. Modern secure browsers (Chrome 120+ / Brave) block sandboxed iframes from transmitting active session cookies (specifically, your Google account session cookie `forwardAuthCookie` required to access the private Workstation VM). The preview proxy rejects the anonymous request, returning a **`403 Forbidden`** and hanging the console loading spinner forever!
> 
> **The Production Solution (GitOps Auto-Import):** 
> To bypass this staging block completely and conform with physical GDC air-gapped disconnected racks standards, **do not manually click console UIs to configure realms!**
> Establish the **Automated Realm Import** method by pre-packaging your target security settings, OIDC clients, custom origins, and personas inside a GKE ConfigMap, and mount it to `/opt/keycloak/data/import/`. Keycloak will dynamically read and self-configure on start! Your React client applications bypass all framing checks by redirecting directly to the dynamic login page, which loads flawlessly!
> 
> In GDC physical rack production, components sit securely unified behind platform Hardware Load Balancers and Ingress Gateway HTTPRoutes FQDNs, completely resolving all cookie disjoints!

2. **Manual Verification (Physical GDC-ag Only):** Hit the `/auth/admin` path organically in your browser and enter the default system credentials provisioned in your manifest (e.g., `admin` / `admin`).  
3. **Advanced Integration Testing:** Once confirmed healthy, you can systematically overlay this Identity Provider atop other architectures (like Pattern 6). For step-by-step instructions on converting a Mock Auth application into a verified Keycloak OIDC citizen, proceed deeply into the **[P12 Keycloak Integration Guide](../docs/keycloak_integration_guide.md)**.

## Packaging for GDC Air-Gapped Environments

To deploy this Keycloak pattern directly to a GDC air-gapped environment securely, package the required artifacts into discrete transit payloads using the helper pipeline.

### 1. Execute the Pipeline
Run the external dependencies script first (to fetch necessary global Keycloak Open Source images outlined in `external_images.txt`), and then systematically package the blueprint:

```bash
# 1. Fetch Keycloak Remote Assets
./scripts/export-external-dependencies.sh

# 2. Package all localized configuration for P12
./scripts/package-for-gdc.sh p12-keycloak
```

### 2. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated within `packages/p12-keycloak/`):**
    *   `p12-keycloak-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p12-keycloak-BOM.txt` and `p12-keycloak-manifest.txt` (Integrity checksums)
    *   `p12-keycloak-README.md` (Standalone deployment instructions)
*   **Global Dependencies:**
    *   `packages/p12-keycloak/external-dependencies/images/quay_io_keycloak_keycloak_24_0_4.tar` (The open-source Red Hat identity container)

### 3. Unpack and Deploy (On GDC)

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

2. **Load and Push Keycloak Image:** Keycloak relies strictly on its native open-source container image. Load and push the artifact to your local registry:
   ```bash
   docker load -i packages/p12-keycloak/external-dependencies/images/quay_io_keycloak_keycloak_24_0_4.tar
   docker push harbor.gdc.local/library/keycloak/keycloak:24.0.4
   ```

3. **Extract API Manifests:** Extract the packaged blueprint configurations:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf packages/p12-keycloak/p12-keycloak-gdc-manifests.tar.gz -C ./gdc-manifests/
   ```

4. **Deploy Pure OSS Identity Gateway:**
   ```bash
   kubectl apply -f ./gdc-manifests/apps/keycloak.yaml
   ```
