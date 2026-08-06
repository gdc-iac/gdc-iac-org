Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 4: Event-Driven Pipeline (Kafka)

**Use Case:** Decoupled microservices using a message bus for durability.

## Architecture Schematic

```
+-----------------+      +----------------------+      +-----------------+
| Event Producer  |----->| Kafka on GKE         |----->| Event Consumer  |
| (GKE/VM)        |      | (StatefulSet, 3 Rep) |      | (GKE Deployment)|
+-----------------+      +----------------------+      +-----------------+
                                   |                            |
                                   v                            v
                          +----------------------+      +----------------------+
                          | GDC Storage (Block)  |      | GDC Database Service |
                          | (Persistent Volumes) |      | (PostgreSQL HA)      |
                          +----------------------+      +----------------------+
```

## Design & Resilience Pattern

1.  **Event Bus (Message Queue):**
    *   **OSS Component:** GDC-ag does not have a native "Pub/Sub" style service, you would deploy a resilient message queue like **Kafka** onto a **GDC GKE Cluster**.
        *   Note Kafka is available as a managed service in the GDC-ag marketplace.
    *   **Resilience:** This is managed at the application layer. Kafka can be deployed in clustered configurations on GKE, using GKE stateful sets and persistent volumes (backed by **GDC Block Storage**) to ensure message durability and high availability.
2.  **Event Producers:**
    *   **GDC Platform Service:** Applications or services running on **GDC GKE Clusters** or **GDC VM Runtime** publish messages to the OSS event bus.
    *   **Resilience:** Handled by the application logic (e.g. retry mechanisms).
3.  **Event Consumers (Workers):**
    *   **GDC Platform Service:** Deployed as scalable, containerized applications on a **GDC GKE Cluster**.
    *   **Resilience:** These are typically stateless workers managed by a GKE Deployment. They consume messages from the queue. GKE's Horizontal Pod Autoscaler (HPA) can be configured (using custom metrics from the queue) to scale the number of workers based on the queue depth, ensuring timely processing.
4.  **Data Persistence:**
    *   **GDC Platform Service:** Workers persist their results to a **GDC Database Service** (PostgreSQL HA) or write artifacts to **GDC Storage (Object)**.
    *   **Resilience:** Provided by the managed GDC data services.

## Required IAM Permissions

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Database Admin:** To provision the PostgreSQL HA cluster for results.
    *   `roles/db.cluster.creator`
*   **GKE Admin/Developer:** To deploy the Kafka Helm chart (which includes StatefulSets and PersistentVolumeClaims) and the consumer application. A more privileged role like `roles/gke.admin` may be required for the initial Helm installation of stateful services.
    *   `roles/gke.admin` or `roles/gke.developer`

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The Kafka broker images, Zookeeper images, and the consumer application image must be built, scanned, and pushed to the internal GDC registry (Harbor).
2.  **Helm Charts:** The Kafka Helm chart must be downloaded and transferred.
3.  **Configuration:** The Kubernetes manifests and any helper scripts must be packaged and transferred.
4.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** High throughput. Supports 10,000+ messages/second (depending on message size).

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Kafka Cluster** | `n2-standard-4-gdc` (x3) | 4 | 16Gi | 100Gi (x3) | No |
| **Consumer** | `n2-standard-4-gdc` | 4 | 16Gi | N/A | No |
| **Database** | `db-custom-2-8` (Managed) | 2 | 8Gi | 50Gi | No |

**Scaling & Upgrades:**
*   **Kafka:** Monitor broker CPU and disk I/O. If consistently high, add more brokers to the cluster (e.g., scale from 3 to 5 nodes).
*   **Consumers:** Monitor consumer lag. If lag increases, scale up the number of consumer replicas using HPA.
*   **Database:** If write latency increases, upgrade the Managed Database instance to `db-custom-4-16` or higher.

**Sizing Rationale:**
Kafka brokers are memory-intensive (JVM heap + OS page cache). The suggested size ensures stability for high-throughput message processing and replication.

## Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL> -d p4-event-driven-kafka
```

## Required IAM Permissions

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Database Admin:** To provision the PostgreSQL HA cluster for results.
    *   `roles/db.cluster.creator`
*   **GKE Admin/Developer:** To deploy the Kafka Helm chart (which includes StatefulSets and PersistentVolumeClaims) and the consumer application. A more privileged role like `roles/gke.admin` may be required for the initial Helm installation of stateful services.
    *   `roles/gke.admin` or `roles/gke.developer`

## Implementation

### Step 1: Deploy Kafka & Persistence

**Option A: Manual (CLI/Helm)**

```bash
export PROJECT_ID=<YOUR_PROJECT_ID>
export REGISTRY_HOST=<YOUR_REGISTRY_URL>

# 1. Durable storage for final results
gdcloud database clusters create event-db \
  --project=$PROJECT_ID --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA

# 2. Kafka Cluster (KRaft StatefulSet)
# Execute the native, offline-friendly Kubernetes manifests
kubectl apply -f manifests/gdc/kafka/kafka.yaml
```

**Option B: GitOps**

Sync the `manifests/gdc/db/event-db.yaml` and `manifests/gdc/kafka/kafka.yaml` files to your cluster.

> **Note on Storage:** GDC Block Storage for Kafka is provisioned dynamically. The StatefulSet creates PersistentVolumeClaims (PVCs) requesting the `standard-rwo` StorageClass (default), which the GDC platform automatically fulfills with block storage volumes.

### Step 2: Initialize Database Schema

The consumer application requires a specific database schema to store processed orders.

**For GDC Production (PostgreSQL HA):**
You must manually apply the schema to your GDC Database Service instance.

1.  Connect to your database instance using `psql`.
2.  Run the following SQL commands:

    ```sql
    CREATE TABLE IF NOT EXISTS processed_orders (
        id SERIAL PRIMARY KEY,
        order_id INT,
        item TEXT,
        amount INT,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ```

### Step 3: Deploy Consumers

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/apps/consumer.yaml
```

**Option B: GitOps**

Sync the `manifests/apps/consumer.yaml` file to your cluster.

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

The `verify.sh` script checks the status of the deployed GDC and GKE resources.

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
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p4-event-driven-kafka
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p4-event-driven-kafka
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p4-event-driven-kafka-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p4-event-driven-kafka-gdc-images.tar` (The bundled local consumer app container images)
    *   `p4-event-driven-kafka-BOM.txt` and `p4-event-driven-kafka-manifest.txt` (Integrity checksums)
    *   `p4-event-driven-kafka-README.md` (Standalone deployment instructions)
*   **Global Dependencies (Generated in the `artifacts/` directory):**
    *   `artifacts/external-dependencies/images/docker.io_apache_kafka_3.7.0.tar` (The Kafka broker container)
    *   `artifacts/external-dependencies/images/busybox_latest.tar` (InitContainers for storage provisioning)
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

2. **Load and Push Consumer Images:** Extrapolate the locally-built consumer logic images:
   ```bash
   ./scripts/unpack-for-gdc.sh p4-event-driven-kafka-gdc-images.tar harbor.gdc.local/library
   ```

3. **Load and Push Kafka Weights:** The Kafka KRaft dependencies were mirrored autonomously and need to be loaded from the external images directory:
   ```bash
   docker load -i artifacts/external-dependencies/images/docker.io_apache_kafka_3.7.0.tar
   docker load -i artifacts/external-dependencies/images/busybox_latest.tar
   
   docker tag apache/kafka:3.7.0 harbor.gdc.local/library/apache/kafka:3.7.0
   docker tag busybox:latest harbor.gdc.local/library/busybox:latest
   
   docker push harbor.gdc.local/library/apache/kafka:3.7.0
   docker push harbor.gdc.local/library/busybox:latest
   ```

4. **Extract Kubernetes Manifests:** Extract the tailored blueprints:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf p4-event-driven-kafka-gdc-manifests.tar.gz -C ./gdc-manifests/
   ```

5. **Deploy Kafka Infrastructure:** Deploy the native, offline-friendly KRaft StatefulSet:
   ```bash
   kubectl apply -f ./gdc-manifests/manifests/gdc/kafka/kafka.yaml
   ```

6. **Apply Consumer Logic:**
   ```bash
   kubectl apply -f ./gdc-manifests/manifests/apps/consumer.yaml
   ```
