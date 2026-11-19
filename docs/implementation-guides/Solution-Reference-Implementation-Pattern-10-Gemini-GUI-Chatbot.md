Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 10: Gemini GUI Chatbot on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Gemini GUI Chatbot** pattern on Google Distributed Cloud (GDC) air-gapped environments. This pattern provides a React-based frontend web interface and FastAPI backend serving as a wrapper around GDC's native platform-managed Gemini models. It allows users to upload documents (PDFs, images, text) directly into Gemini's large context window, managing chat histories and file metadata inside a managed database (PostgreSQL HA).

## **Architecture**

The architecture features a single-origin host routing strategy using Gateway API:
* **Frontend (React)**: Exposes the user interface and coordinates API requests.
* **Backend (FastAPI)**: Manages model context construction, document upload metadata, and talks to GDC's Vertex AI Gemini endpoint.
* **Database (PostgreSQL HA)**: Persists user settings, session contexts, and message histories.
* **Object Storage (GCS Bucket)**: Stores uploaded source files.

```
                    [ User Web Browser ]
                             │
                             ▼ (Port 80)
                     [ GDC platform Load Balancer ]
                             │
              ┌──────────────┴──────────────┐
              │ (/)                         │ (/api)
              ▼                             ▼
     [ frontend-svc ]               [ backend-svc ]
     (React Web App)                (FastAPI App)
                                            │
                     ┌──────────────────────┼──────────────────────┐
                     ▼                      ▼                      ▼
             [ GDC Vertex AI ]       [ GDC Database ]      [ GDC Storage ]
            (Gemini inference)       (PostgreSQL HA)     (Object Bucket)
```

### **Key Solution Capabilities**

* **Direct Context Upload Grounding**: Injects full document contents directly into the Gemini model's native context window for reasoning tasks.
* **Sovereign File Persistence**: Keeps uploaded user data localized to secure GDC Object Storage buckets.
* **Session Persistence**: Stores multi-turn chat sessions inside the GDC Database Service, ensuring state is not lost across container restarts.
* **Least-Privilege Storage Policy**: Restricts storage bucket modifications to a dedicated `ServiceAccount` and binds IAM permissions.

---

## **LLM Gateway Integration & Cross-Cluster Topology Guidance**

Pattern 10 is designed to consume either the native **GDC Gemini AI Gateway** or self-hosted **Gemma Inference Gateway** (`gdc_gemma_gw`).

> [!NOTE]
> **Cross-Cluster & Shared-Services Gateway Access**:
> The inference gateway does **not** need to be co-located in the same cluster or namespace as the Chatbot application.
> Depending on enterprise infrastructure deployment, `LLM_GATEWAY_URL` or `GEMINI_ENDPOINT` can point to:
> * **Co-located Namespace**: `http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`
> * **Shared Services Cluster / Namespace**: `http://gemma-gateway.shared-services.svc.cluster.local:80/v1`
> * **Dedicated External GPU / Platform Cluster**: `https://ai-gateway.shared-services.gdc.local/v1` (exposed via GDC Gateway API `HTTPRoute` or load balancer FQDN).

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* GDC Vertex AI service enabled and healthy.
* A GDC Object Storage bucket (`gs://gemini-gui-files-<project_id>`) created.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL HA).
  * **Storage Admin**: `project-bucket-object-admin` (to assign bucket permissions).
  * **GKE Developer**: `namespace-admin` / `cluster-developer` (to deploy manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the custom chatbot container images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p10-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom chatbot images:
```bash
docker tag p10-frontend:latest harbor.shared-services.gdc.local/my-org/p10-frontend:latest
docker push harbor.shared-services.gdc.local/my-org/p10-frontend:latest

docker tag p10-backend:latest harbor.shared-services.gdc.local/my-org/p10-backend:latest
docker push harbor.shared-services.gdc.local/my-org/p10-backend:latest
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p10-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry client-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.3 Base Cluster Resource & Node Pool Requirements

### 1.3.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Frontend UI** | 1 | 100m (500m) | 128Mi (256Mi) | None |
| **Backend API** | 1 | 200m (1) | 256Mi (1Gi) | None |
| **PostgreSQL HA** | 2 | 2 (2) | 8Gi (8Gi) | 50Gi PVC |

### 1.3.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Hosts the frontend UI deployment, the backend API, and the PostgreSQL HA database.
* **Instance Type**: 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node).
* **Total Resource Pool**: 8 vCPUs, 32Gi RAM.
* **Resilience Configuration**: Running on at least 2 compute nodes ensures that database replicas are zone-separated and frontend/backend components can fail over seamlessly.

### 1.3.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p10-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-4-gdc
    nodeCount: 2
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Create the Project Binding YAML (`project-binding.yaml`):**
```yaml
apiVersion: resourcemanager.gdc.goog/v1
kind: ProjectBinding
metadata:
  name: p10-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p10-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - my-gdc-project
```

**3. Apply the Manifests:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p10-standard-cluster
  namespace: my-gdc-project
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-4-gdc
    nodeCount: 2
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Apply the Manifest:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.3.4 Workload Pod Assignment & Scheduling Configuration

Configure `nodeSelector` in the chatbot frontend, backend, and database manifests:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Database & Storage Configuration**

### 2.1 Provision Database Service

Deploy the managed PostgreSQL 15 database (`postgresql.dbadmin.gdc.goog/v1`) on the Zonal Management Plane (`ZONE_KUBECONFIG`).

#### Option A: Manual (CLI)
```shell
export DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"

gdcloud database clusters create gemini-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_15 \
  --availability-type=zonal_ha \
  --admin-password="${DB_ADMIN_PASSWORD}" \
  --cpu=2 --memory=8Gi --storage-size=50Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/db/postgres.yaml` on `ZONE_KUBECONFIG`)
Apply both the `dbsadmin` password `Secret` (`db-pw-gemini-db`, key `gemini-db`) and the `DBCluster` resource against `ZONE_KUBECONFIG`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-gemini-db
  namespace: my-gdc-project
type: Opaque
data:
  gemini-db: "<base64-admin-password>"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: gemini-db
  namespace: my-gdc-project
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-gemini-db
    version: "15"
    resources:
      cpu: 2
      memory: 8Gi
      disks:
        - name: DataDisk
          size: 50Gi
```

### 2.2 Endpoint Discovery, TLS Root CA & `dbsadmin` Schema Initialization

GDCag Managed PostgreSQL does **not** automatically create a `gemini-db-credentials` Secret on the User Cluster. Once `DBCluster/gemini-db` reaches `READY` on `ZONE_KUBECONFIG`, query its primary DNS endpoint, extract the server TLS CA certificate from `Secret/dbs-certificates`, and connect as `dbsadmin` (`cloudsqlsuperuser`) over verified TLS to enable `uuid-ossp`, create a dedicated `gemini_app` role, and initialize the chat tables:

```shell
# 1. Discover primary DNS endpoint and extract TLS Root CA on ZONE_KUBECONFIG
DB_ENDPOINT=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog gemini-db \
  -n my-gdc-project -o jsonpath='{.status.primary.url}')
DB_HOST="${DB_ENDPOINT%:5432}"

kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n my-gdc-project -o jsonpath='{.data.dbs-pg-cert-gemini-db}' | base64 -d > ca.crt

# 2. Connect as dbsadmin over verified TLS to initialize extensions, application role, and tables
export PGPASSWORD="${DB_ADMIN_PASSWORD}"
export APP_DB_PASSWORD="<strong-gemini-db-password>"

PGSSLMODE=verify-ca PGSSLROOTCERT=./ca.crt \
  psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d postgres <<SQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gemini_app') THEN
    CREATE ROLE gemini_app WITH LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END
\$\$;

CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE chats, messages, files TO gemini_app;
SQL
```

### 2.3 Create Workload Connection & TLS CA Secrets on User Cluster

Create `gemini-gui-db-credentials` and `gemini-db-ca` on the User Cluster (`USER_CLUSTER_KUBECONFIG`):
```shell
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic gemini-gui-db-credentials \
  --from-literal=connection_string="postgresql://gemini_app:${APP_DB_PASSWORD}@${DB_HOST}:5432/postgres" \
  --from-literal=host="${DB_HOST}" \
  --from-literal=username="gemini_app" \
  --from-literal=password="${APP_DB_PASSWORD}" \
  -n my-gdc-project

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic gemini-db-ca \
  --from-file=ca.crt=./ca.crt \
  -n my-gdc-project
```

### 2.4 Configure Storage Service Account

Create a `ServiceAccount` and bind GDC storage roles to enable the backend to access uploaded documents:

```yaml
# Apply on Global API (`GLOBAL_API_KUBECONFIG`):
apiVersion: resourcemanager.global.gdc.goog/v1
kind: ProjectServiceAccount
metadata:
  name: gemini-gui-sa
  namespace: my-gdc-project
---
apiVersion: iam.global.gdc.goog/v1
kind: IAMRoleBinding
metadata:
  name: gemini-gui-sa--project-bucket-object-admin
  namespace: my-gdc-project
  labels:
    iam.global.gdc.goog/iam-role-name: project-bucket-object-admin
spec:
  subjects:
    - kind: ServiceAccount
      name: gemini-gui-sa
      namespace: my-gdc-project
  roleRef:
    apiGroup: iam.global.gdc.goog/v1
    kind: IAMRole
    name: project-bucket-object-admin
```
Save as `iam-binding.yaml` and apply:
```shell
kubectl apply -f iam-binding.yaml -n my-gdc-project
```

---

## **Section 3: Deploying Frontend & Backend**

#### Option A: Manual (CLI)
```shell
kubectl apply -f backend.yaml -n my-gdc-project
kubectl apply -f frontend.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/apps/backend.yaml` & `frontend.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: my-gdc-project
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
      serviceAccountName: gemini-gui-sa
      containers:
      - name: backend
        image: harbor.shared-services.gdc.local/my-org/p10-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: PROJECT_ID
          value: "my-gdc-project"
        - name: INPUT_BUCKET
          value: "gs://gemini-gui-files-my-gdc-project"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: gemini-gui-db-credentials
              key: connection_string
        - name: REGION
          value: "us-central1"
        - name: GEMINI_MODEL
          value: "gemini-2.5-flash"
---
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
  namespace: my-gdc-project
spec:
  selector:
    app: backend
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: my-gdc-project
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
      containers:
      - name: frontend
        image: harbor.shared-services.gdc.local/my-org/p10-frontend:latest
        ports:
        - containerPort: 80
        env:
        - name: VITE_API_URL
          value: "/api"
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
  namespace: my-gdc-project
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
```

---

## **Section 4: Network Exposure (Gateway API)**

To expose the chatbot frontend and API backend unified under a single hostname (preventing CORS issues), deploy a GDC HTTPRoute mapping paths:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gemini-chatbot-route
  namespace: my-gdc-project
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: my-gdc-project
  hostnames:
  - "chatbot.gdc.local"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /api
    filters:
    - type: URLRewrite
      urlRewrite:
        path:
          type: ReplacePrefixMatch
          replacePrefix: /
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
```
Apply route manifest:
```shell
kubectl apply -f route.yaml -n my-gdc-project
```

---

## **Section 5: Validation**

### 5.1 Test API Ping & Backend Status

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute verification check directly inside the cluster against the internal `backend-svc` Service:

```bash
kubectl run p10-verify --rm -i --restart=Never -n my-gdc-project \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"harbor-creds"}]}}' \
  --image="${PROJECT_HARBOR}/iac/curl:8.12.1" --command -- sh -ec '
    sleep 2 && \
    curl -s http://backend-svc:8000/health && \
    echo "" && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 10 Gemini GUI API verified!" && \
    echo "✅ SUCCESS: Backend health check returned 200 OK" && \
    echo "===============================================" 
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 10 Gemini GUI API verified!
✅ SUCCESS: Backend health check returned 200 OK
===============================================
{"status": "healthy"}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: ClusterIP Curl Check
Query the backend API directly:
```shell
export BACKEND_IP=$(kubectl get service backend-svc -n my-gdc-project -o jsonpath='{.spec.clusterIP}')
curl http://${BACKEND_IP}:8000/health
# Expected output: {"status": "healthy"}
```

### 5.2 Validate Web Interface
Open a browser and target `https://chatbot.gdc.local` (ensure your DNS or `/etc/hosts` maps this hostname to GDC platform gateway load balancer IP).
1. Create a new chat session.
2. Ask: "Who are you?"
3. Upload a text file containing "Secret Code: GDC-ag-101" and select it.
4. Ask: "What is the secret code listed in my document?"
Verify the chatbot correctly grounds its reasoning using the uploaded text context.

---

## **Section 6: Operations & Troubleshooting**

### 6.1 Database High Availability & Failover

In GDC air-gapped `v1.15.1+`, `DBCluster` resources configured with `spec.availability.enableHighAvailability: true` enable automatic failover (`enableAutoFailover: true`) by default upon primary instance failure. Operators can also trigger planned switchovers or manual failovers via the `gdcloud` CLI or the declarative `fleet.dbadmin.gdc.goog/v1` `Failover` custom resource.

#### Option A: Manual Switchover / Failover (CLI)
To trigger an operator-initiated failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover gemini-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml` on `ZONE_KUBECONFIG`)
Apply a `Failover` custom resource to trigger a switchover or manual failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-gemini-db
  namespace: my-gdc-project
spec:
  dbclusterRef: gemini-db
```

### 6.2 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `File Upload fails` | ServiceAccount lacks permissions to write objects to the GCS Bucket. | Verify that the `IAMRoleBinding` (`iam.global.gdc.goog/v1`) binds `project-bucket-object-admin` to `gemini-gui-sa`. |
| `Chat history fails to save` | Database connection string in `gemini-gui-db-credentials` is misconfigured. | Verify database host address and secret string formatting. |
| `CORS errors in browser` | Browser tries to reach the API directly on port 8000 instead of route paths. | Verify HTTPRoute path rewrite rules are active and that frontend configuration uses `/api` base path. |

---

## IaC Framework Integration (Helm & Helmfile)

This pattern includes a Helm wrapper chart (`chart/`) supporting dual-mode deployment:
1. **Standalone Mode (`manifests/`)**: Apply raw manifests directly using `kubectl apply -f manifests/`.
2. **Orchestrated Mode (`chart/` & `foundations/releases/5-workload-factory`)**: Deploy User Cluster workloads (`apps.enabled=true`, `gdc.enabled=false`) via Stage 5 of the `foundations/` Helmfile pipeline after Stage 2 (`2-resources`) provisions Zonal databases and VMs via `charts/gdc-dbs` and `charts/gdc-vm`.
