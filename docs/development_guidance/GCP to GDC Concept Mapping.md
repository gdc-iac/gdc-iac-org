Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

## Concept Mapping

In our development environment (GKE Emulation), we aim for speed and simplicity. In production (GDC), we aim for reliability, compliance, and managed operations. 

| Component | Dev / GKE on GCP Emulation  | Prod / GDC Air-Gapped (Target) | Why the difference? |
| :---- | :---- | :---- | :---- |
| **Database Engine** | **Generic PostgreSQL Container** (StatefulSet) | **PostgreSQL HA** (Managed DB Cluster) | **Emulation:** Fast, free, lightweight.  \*\*GDC:\*\* HA, Backup, Security, Compliance (Reference: \[GDC DB Create Cluster\](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/db-create-cluster\#api)). |
| **Provisioning** | `helm install` (Native K8s manifests) | `kubectl apply -f` (GDC Custom Resources) | GDC uses specific CRDs (Custom Resource Definitions) like `DBCluster` to provision managed databases. |
| **Management** | Manual (DIY) | Fully Managed | GDC handles backups and updates; failover is triggered manually by the operator. |
| **Connection** | `postgres-mcp-db-0.postgres-mcp-db` (K8s DNS) | Service Endpoint / IP | Both expose a standard PostgreSQL connection string. The code *only* sees the connection string. |
| **Authentication** | Kubernetes Secret (Env Vars) | Kubernetes Secret (Env Vars) or Workload Identity | Identical mechanism. The application reads `DB_HOST`, `DB_USER`, etc., from env vars populated by K8s secrets. |
| **Kubernetes API** | Single API Server (GKE cluster) | Multiple API Servers - Management, Cluster, Zonal, Global | GDC has a number of API endpoints for managing different contexts, including clusters, zonal / global resources and the overall management platform. |
| **Networking** | Wide range of load balancers, ingress, Gateway options | Gateway API | GDC leverages the latest Kubernetes approach to migrate from Ingress to Gateway API |
| **PKI** | ManagedCertificates, internet hosted ACME certificate services (e.g. LetsEncrypt) | GDC Certificate Authority with ACME | GDC uses specific CRDs to operate PKI within the air-gapped environment |


## Migration Steps: From Emulation to GDC

### 0\. Functional Changes / Checks
* Review Ingress / Gateway configuration and adapt for the Gateway API as required.
* Review certificate objects and update for GDC Certificate Authority CRDs
* Split ``helm`` charts as required for different GDC API Servers - e.g. resources configured via the Management API vs Cluster API.

To move this workload to a real GDC Air-Gapped environment, you would perform the following infrastructure swap:

### 1\. Provision the GDC Managed Database

Instead of running our `statefulset.yaml`, you would apply a GDC-specific manifest to creating a database cluster:

**File:** `infrastructure/gdc/db-cluster.yaml` (Example)

```yaml
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: agent-db-cluster
  namespace: agent-framework
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA
  resources:
     requests: { cpu: "2", memory: "4Gi" }
  storage: { size: "50G" }
```

*Ref: [Create a DB Cluster (GDC Docs)](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/db-create-cluster#api)*

### 2\. Update the Helm Values

You would then update the `values.yaml` for the **Postgres MCP Server chart** to point to this new managed instance instead of the local headless service.

**File:** `infrastructure/helm/postgres_mcp/values.yaml`

```yaml
# OLD: Hosting our own DB
# postgres:
#   image: postgres:15-alpine
#   ...

# NEW: Connecting to GDC Managed DB
externalDatabase:
  host: "agent-db-cluster-rw-lb.agent-framework.svc.cluster.local" # Internal LB DNS provided by GDC
  port: 5432
  database: "postgres"
  # Credentials would still be mounted via Secret
```

## Appendix A: Deploy a GKE Cluster on GCP for emulation 
```bash
#!/bin/bash
set -e

# Configuration
CLUSTER_NAME="${CLUSTER_NAME:-gdc-emulation-cluster}"
REGION="${REGION:-us-central1}"
PROJECT_ID=$(gcloud config get-value project)
NETWORK="default"
SUBNET="default"

echo "Creating GKE Cluster: ${CLUSTER_NAME} in ${REGION}..."

# Enable necessary APIs
gcloud services enable container.googleapis.com \
    artifactregistry.googleapis.com \
    cloudresourcemanager.googleapis.com \
    iamcredentials.googleapis.com

# Create the cluster
# We enable Workload Identity for secure access to GCP resources (simulating GDC identity).
# We enable Config Connector to manage GCP resources via K8s manifests.

if gcloud container clusters describe "${CLUSTER_NAME}" --region "${REGION}" >/dev/null 2>&1; then
    echo "Cluster ${CLUSTER_NAME} already exists. Skipping creation."
else
    gcloud container clusters create "${CLUSTER_NAME}" \
        --region "${REGION}" \
        --project "${PROJECT_ID}" \
        --release-channel "regular" \
        --network "${NETWORK}" \
        --subnetwork "${SUBNET}" \
        --workload-pool "${PROJECT_ID}.svc.id.goog" \
        --machine-type "e2-standard-4" \
        --addons ConfigConnector \
        --enable-ip-alias \
        --num-nodes 1
fi

# Get credentials
gcloud container clusters get-credentials "${CLUSTER_NAME}" --region "${REGION}"

# Configure Config Connector
# This binds the K8s service account to the Google Service Account (GSA) with owner permissions 
# to allow creating resources in the project. 
# NOTE: In a strictly least-privileged env, use a custom role.
echo "Configuring Config Connector..."

# Create a GSA for Config Connector
KCC_SA="kcc-sa"
if ! gcloud iam service-accounts describe "${KCC_SA}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${KCC_SA}" --display-name "Config Connector Service Account"
fi

# Bind GSA to project Owner (for demo purposes)
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${KCC_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role "roles/owner" \
    --condition=None

# Annotate the ConfigConnectorContext
# Note: Newer GKE versions with Config Connector addon use a simplified setup, 
# but we follow the standard KCC setup steps for completeness if addon isn't auto-configuring everything.
# The addon usually handles the Operator, but we need to configure where it writes.

cat <<EOF | kubectl apply -f -
apiVersion: core.cnrm.cloud.google.com/v1beta1
kind: ConfigConnector
metadata:
  name: configconnector.core.cnrm.cloud.google.com
spec:
  mode: cluster
  googleServiceAccount: "${KCC_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
EOF

# Grant the KCC controller permission to impersonate the GSA
gcloud iam service-accounts add-iam-policy-binding "${KCC_SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --member "serviceAccount:${PROJECT_ID}.svc.id.goog[cnrm-system/cnrm-controller-manager]" \
    --role "roles/iam.workloadIdentityUser"

echo "Cluster setup complete. Config Connector enabled."
```
