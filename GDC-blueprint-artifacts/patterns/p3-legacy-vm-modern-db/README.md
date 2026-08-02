Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 3: Legacy VM + Modern Database

**Use Case:** Lift-and-shift legacy apps that can't be containerized but need a modern DB.

## Architecture Schematic

```
+-------------------------+      +-------------------------+
| GDC VM Runtime          |<---->| GDC Storage (Block)     |
| (Legacy App VM)         |      | (VM Disk)               |
+-------------------------+      +-------------------------+
         |
         |
         v
+-------------------------+
| GDC Database Service    |
| (PostgreSQL HA)         |
+-------------------------+
         ^
         |
         |
+-------------------------+
| GDC GKE Cluster         |
| (Modern Apps)           |
+-------------------------+
```

## Design & Resilience Pattern

1.  **Legacy Application VM:**
    *   **GDC Platform Service:** The legacy application (e.g., a Windows Server-based application or a monolithic Linux binary) is deployed onto a virtual machine using the **GDC VM Runtime**.
    *   **Resilience:** The VM Runtime provides basic infrastructure-level availability. For application-level resilience, you would rely on traditional methods like in-guest clustering or load balancing between multiple VMs (if the app supports it).
2.  **High-Performance Database:**
    *   **GDC Platform Service:** A high-availability **PostgreSQL** cluster is provisioned using the **GDC Database Service**. This serves as the high-throughput, resilient database for both modern and legacy applications.
    *   **Resilience:** PostgreSQL is designed for high availability with zonal standby replicas, requiring a manual trigger for failover.
3.  **VM Data Storage:**
    *   **GDC Platform Service:** Virtual machine disks are provisioned using **GDC Storage (Block Storage)**. Shared filesystems for clustered VMs can use **GDC Storage (File Storage)**.
    *   **Resilience:** GDC Block and File Storage provide resilient, persistent storage for the GDC VMs.
4.  **Bridge to Modern Apps:**
    *   **GDC Platform Service:** Applications running on **GDC GKE Clusters** can securely access the PostgreSQL database and interact with the legacy VM application via standard GDC networking.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **VM Images:** The legacy application VM image (e.g., Ubuntu or Windows Server) must be imported into the GDC VM Runtime image repository.
2.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
3.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** Limited by the single VM instance size. Vertical scaling is required for growth.

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC/Disk) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Legacy VM** | `n2-highcpu-8-gdc` | 8 | 8Gi | 100Gi (Disk) | No |
| **Database** | `db-custom-4-16` (Managed) | 4 | 16Gi | 100Gi | No |

**Scaling & Upgrades:**
*   **Compute (VM):** Monitor CPU/RAM usage within the VM. If consistently high (>80%), stop the VM and resize to a larger machine type (e.g., `n2-standard-16-gdc`).
*   **Storage (Disk):** Monitor disk usage. Resize the Persistent Disk if usage exceeds 70%.
*   **Database:** Upgrade the Managed Database instance to `db-custom-8-32` for higher transaction throughput.

**Sizing Rationale:**
Based on common requirements for legacy monolithic applications (Windows/Linux) that cannot be easily containerized, requiring dedicated resources for the OS and application runtime.

## Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL> -d p3-legacy-vm-modern-db
```

## Required IAM Permissions

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Network Admin:** To create VPC networks and subnets for the VM.
    *   `roles/compute.networkAdmin`
*   **Database Admin:** To provision the PostgreSQL HA cluster.
    *   `roles/db.cluster.creator`
*   **Compute Admin:** To create the virtual machine instance.
    *   `roles/compute.instanceAdmin.v1`

## Implementation

### Step 1: Create Infrastructure

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

# Network for the VM
gdcloud compute networks create vm-net --project=$PROJECT_ID --subnet-mode=custom
gdcloud compute networks subnets create vm-subnet --network=vm-net --range=10.1.0.0/24 --region=region-1

# High Performance HA Database
gdcloud database clusters create legacy-db \
  --project=$PROJECT_ID \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=4 --memory=16Gi --storage-size=100Gi
```

**Option B: GitOps**

Sync the `manifests/gdc/infra/legacy-infra.yaml` file to your cluster.

### Step 2: Initialize Database Schema

The legacy application requires a specific database schema to store orders.

**For GDC Production (PostgreSQL):**
You must manually apply the schema to your GDC Database Service instance.

1.  Connect to your PostgreSQL instance using `psql`.
2.  Run the following SQL commands:

    ```sql
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        product_id INT NOT NULL,
        quantity INT NOT NULL,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ```

### Step 3: Provision VM

*Prerequisite: Run `gdcloud compute images list` to find your exact image name.*

**Option A: Manual (CLI)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>

gdcloud compute instances create app-vm-01 \
  --project=$PROJECT_ID \
  --zone=zone-1 \
  --machine-type=n2-highcpu-8-gdc \
  --image-project=gradec-images --image-family=ubuntu-2004 \
  --subnet=vm-subnet
```

**Option B: GitOps**

Sync the `manifests/gdc/vm/app-vm.yaml` file to your cluster.

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

The `verify.sh` script checks the status of the deployed GDC resources.

To run the verification:
```bash
cd test/
chmod +x verify.sh
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
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p3-legacy-vm-modern-db
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p3-legacy-vm-modern-db
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p3-legacy-vm-modern-db-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p3-legacy-vm-modern-db-gdc-images.tar` (The bundled container images)
    *   `p3-legacy-vm-modern-db-BOM.txt` and `p3-legacy-vm-modern-db-manifest.txt` (Integrity checksums)
    *   `p3-legacy-vm-modern-db-README.md` (Standalone deployment instructions)

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
   ./scripts/unpack-for-gdc.sh p3-legacy-vm-modern-db-gdc-images.tar harbor.gdc.local/library
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
   tar -xzf p3-legacy-vm-modern-db-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

5. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.
