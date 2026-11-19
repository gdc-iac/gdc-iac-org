Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 12: Identity and Access Management (Keycloak) on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document provides step-by-step instructions for deploying and configuring **Keycloak** as a resilient, centralized Identity Provider (IdP) on Google Distributed Cloud (GDC) air-gapped environments. This pattern demonstrates authentication, single sign-on (SSO), and role-based access control (RBAC) proxying for tenant applications, integrating with a GDC managed database cluster for persistent user metadata storage.

## **Architecture**

Keycloak runs as a GKE deployment, exposed to clients internally and externally (via Gateway API), and connects to a managed PostgreSQL cluster configured for zonal high availability.

```
                    [ External client browser ]
                                 │
                                 ▼ (Port 80)
                     [ GDC platform Load Balancer ]
                                 │
                                 ▼
                     [ keycloak Service ] (ClusterIP)
                                 │
                                 ▼
                     [ keycloak pods ] (Deployment)
                                 │
                                 ▼ (Port 5432)
                    [ GDC Database: keycloak-db ]
                     (PostgreSQL Zonal HA Cluster)
```

### **Key Solution Capabilities**

* **Centralized IdP**: Exposes OIDC (OpenID Connect) and SAML endpoints for client authentication across all project namespaces.
* **Persistent User Store**: Uses the GDC Database Service PostgreSQL 15 `zonal_ha` cluster (`spec.availability.enableHighAvailability: true`, `enableAutoFailover: true`), safeguarding user profile records and active session states across node failures.
* **Declarative Configuration Imports**: Facilitates auto-configuration of realms, clients, and test user databases during startup using Kubernetes ConfigMaps.
* **Proxy-Friendly exposure**: Configured to trust upstream header forwards (`KC_PROXY_HEADERS="xforwarded"`), enabling seamless integration behind hardware load balancers.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* A healthy GKE User Cluster.
* `kubectl`, `helm`, and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL HA).
  * **GKE Developer**: `namespace-admin` / `cluster-developer` (to deploy manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the Keycloak container image to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p12-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the Keycloak container image:
```bash
docker pull quay.io/keycloak/keycloak:24.0.4
docker tag quay.io/keycloak/keycloak:24.0.4 harbor.shared-services.gdc.local/keycloak/keycloak:24.0.4
docker push harbor.shared-services.gdc.local/keycloak/keycloak:24.0.4
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p12-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry client-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.2 Base Cluster Resource & Node Pool Requirements

### 1.2.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Keycloak App** | 1 | 500m (1) | 1Gi (2Gi) | None |
| **PostgreSQL HA** | 2 | 2 (2) | 8Gi (8Gi) | 100Gi PVC |

### 1.2.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Handles the Keycloak application container and the PostgreSQL HA replication instances.
* **Instance Type**: 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node).
* **Total Resource Pool**: 8 vCPUs, 32Gi RAM.
* **Resilience Configuration**: Spreading components across at least 2 nodes ensures zone-separated redundancy for PostgreSQL, guaranteeing identity services persist through single-node failures.

### 1.2.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p12-shared-cluster
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
  name: p12-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p12-shared-cluster
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
  name: p12-standard-cluster
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

### 1.2.4 Workload Pod Assignment & Scheduling Configuration

Configure `nodeSelector` in the Keycloak and database deployment specs:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Deploying the Database Tier (PostgreSQL HA)**

### 2.1 Provision PostgreSQL DBCluster

Create the managed PostgreSQL 15 database cluster (`postgresql.dbadmin.gdc.goog/v1`) on the Zonal Management Plane (`ZONE_KUBECONFIG`) for Keycloak.

#### Option A: Manual (CLI)
```shell
export DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"

gdcloud database clusters create keycloak-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_15 \
  --availability-type=zonal_ha \
  --admin-password="${DB_ADMIN_PASSWORD}" \
  --cpu=2 --memory=8Gi --storage-size=100Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/db/db-cluster.yaml` on `ZONE_KUBECONFIG`)
Apply both the `dbsadmin` password `Secret` (`db-pw-keycloak-db`, key `keycloak-db`) and the `DBCluster` resource against `ZONE_KUBECONFIG`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-keycloak-db
  namespace: my-gdc-project
type: Opaque
data:
  keycloak-db: "<base64-admin-password>"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: keycloak-db
  namespace: my-gdc-project
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-keycloak-db
    version: "15"
    resources:
      cpu: 2
      memory: 8Gi
      disks:
        - name: DataDisk
          size: 100Gi
```

### 2.2 Endpoint Discovery, TLS Root CA, `dbsadmin` Initialization & User Cluster Secret Creation

GDCag Managed PostgreSQL does **not** automatically create a `keycloak-db-credentials` Secret on the User Cluster. Once `DBCluster/keycloak-db` reaches `READY` on `ZONE_KUBECONFIG`, discover its primary DNS endpoint, extract the server TLS CA certificate from `Secret/dbs-certificates`, connect as `dbsadmin` (`cloudsqlsuperuser`) over verified TLS to run `CREATE DATABASE keycloak;` and provision a dedicated `keycloak` role, and then create the workload connection secrets on `USER_CLUSTER_KUBECONFIG`:

```shell
# 1. Discover primary DNS endpoint and extract TLS Root CA on ZONE_KUBECONFIG
DB_ENDPOINT=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog keycloak-db \
  -n my-gdc-project -o jsonpath='{.status.primary.url}')
DB_HOST="${DB_ENDPOINT%:5432}"

kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n my-gdc-project -o jsonpath='{.data.dbs-pg-cert-keycloak-db}' | base64 -d > ca.crt

# 2. Connect as dbsadmin over verified TLS to create the keycloak database and dedicated role
export PGPASSWORD="${DB_ADMIN_PASSWORD}"
export KEYCLOAK_DB_PASSWORD="<strong-keycloak-db-password>"

PGSSLMODE=verify-ca PGSSLROOTCERT=./ca.crt \
  psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d postgres \
  -c "CREATE DATABASE keycloak;"

PGSSLMODE=verify-ca PGSSLROOTCERT=./ca.crt \
  psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d keycloak <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak') THEN
    CREATE ROLE keycloak WITH LOGIN PASSWORD '${KEYCLOAK_DB_PASSWORD}';
  END IF;
END
\$\$;

GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak;
GRANT ALL ON SCHEMA public TO keycloak;
SQL

# 3. Create keycloak-db-credentials and TLS CA Secrets on the User Cluster (USER_CLUSTER_KUBECONFIG)
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic keycloak-db-credentials \
  --from-literal=host="${DB_HOST}" \
  --from-literal=jdbc_url="jdbc:postgresql://${DB_HOST}:5432/keycloak" \
  --from-literal=username="keycloak" \
  --from-literal=password="${KEYCLOAK_DB_PASSWORD}" \
  -n my-gdc-project

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic keycloak-db-ca \
  --from-file=ca.crt=./ca.crt \
  -n my-gdc-project
```

---

## **Section 3: Deploying Keycloak**

Deploy the Keycloak manifests on the User Cluster (`USER_CLUSTER_KUBECONFIG`), referencing the `keycloak-db-credentials` Secret created in Section 2.2 (or setting `KC_DB_URL`, `KC_DB_USERNAME`, and `KC_DB_PASSWORD` to `${DB_HOST}` and the `keycloak` role).

#### Option A: Manual (CLI)
```shell
kubectl apply -f keycloak.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/keycloak.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keycloak
  namespace: my-gdc-project
  labels:
    app: keycloak
spec:
  replicas: 1
  selector:
    matchLabels:
      app: keycloak
  template:
    metadata:
      labels:
        app: keycloak
    spec:
      containers:
      - name: keycloak
        image: harbor.shared-services.gdc.local/keycloak/keycloak:24.0.4
        args: ["start-dev"]
        env:
        - name: KC_DB
          value: "postgres"
        - name: KC_DB_URL
          value: "jdbc:postgresql://<DATABASE_HOST_IP>:5432/keycloak"
        - name: KC_DB_USERNAME
          value: "postgres"
        - name: KC_DB_PASSWORD
          value: "postgres_password"
        - name: KEYCLOAK_ADMIN
          value: "admin"
        - name: KEYCLOAK_ADMIN_PASSWORD
          value: "admin"
        - name: KC_METRICS_ENABLED
          value: "true"
        - name: KC_PROXY_HEADERS
          value: "xforwarded"
        - name: KC_HOSTNAME_STRICT
          value: "false"
        - name: KC_HEALTH_ENABLED
          value: "true"
        ports:
        - name: http
          containerPort: 8080
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 5
          failureThreshold: 10
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 90
          periodSeconds: 5
          failureThreshold: 10
---
apiVersion: v1
kind: Service
metadata:
  name: keycloak
  namespace: my-gdc-project
  labels:
    app: keycloak
spec:
  selector:
    app: keycloak
  ports:
  - name: http
    port: 80
    targetPort: 8080
```

---

## **Section 4: Validation**

### 4.1 Verify Keycloak Health & Readiness

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute an ephemeral verification check directly inside the cluster against the internal `keycloak` Service:

```bash
kubectl run p12-verify --rm -i --restart=Never -n my-gdc-project \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"harbor-creds"}]}}' \
  --image="${PROJECT_HARBOR}/iac/curl:8.12.1" --command -- sh -ec '
    sleep 2 && \
    curl -s -I http://keycloak/health/ready | head -n 5 && \
    echo "" && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 12 Keycloak IAM verified!" && \
    echo "✅ SUCCESS: Keycloak readiness endpoint reachable" && \
    echo "===============================================" 
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 12 Keycloak IAM verified!
✅ SUCCESS: Keycloak readiness endpoint reachable
===============================================
HTTP/1.1 200 OK
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: ClusterIP Readiness Check
Query the readiness status check via ClusterIP:
```shell
export KEYCLOAK_IP=$(kubectl get service keycloak -n my-gdc-project -o jsonpath='{.spec.clusterIP}')
curl -I http://${KEYCLOAK_IP}/health/ready
# Expected output: HTTP/1.1 200 OK
```

### 4.2 Test Admin UI Connection
Verify you can log in to the admin console:
1. Target `http://keycloak.my-gdc-project.svc.cluster.local` or route FQDN.
2. Authenticate using username `admin` / password `admin`.
3. Create a test realm (`gdc-realm`) and client configuration to verify storage persistence writes.

---

## **Section 5: Operations & Troubleshooting**

### 5.1 Database High Availability & Failover

In GDC air-gapped `v1.15.1+`, `DBCluster` resources configured with `spec.availability.enableHighAvailability: true` enable automatic failover (`enableAutoFailover: true`) by default upon primary instance failure. Operators can also trigger planned switchovers or manual failovers via the `gdcloud` CLI or the declarative `fleet.dbadmin.gdc.goog/v1` `Failover` custom resource.

#### Option A: Manual Switchover / Failover (CLI)
To trigger an operator-initiated failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover keycloak-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml` on `ZONE_KUBECONFIG`)
Apply a `Failover` custom resource to trigger a switchover or manual failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-keycloak-db
  namespace: my-gdc-project
spec:
  dbclusterRef: keycloak-db
```

### 5.2 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Keycloak crashes during DB migrations` | JDBC database URL contains invalid address, or database credentials are incorrect. | Verify hostname/IP coordinates inside `KC_DB_URL` env variable. |
| `Infinite redirect loop in browser` | Keycloak hostname settings require SSL validation but upstream TLS termination is active. | Verify `KC_PROXY_HEADERS` is configured to `xforwarded` and `KC_HOSTNAME_STRICT` is `false`. |
| `OOMKilled during startup` | Container memory limits are set too low. Keycloak requires at least 1Gi memory on GDC nodes. | Increase memory limits inside the container configuration to `2Gi`. |

---

## IaC Framework Integration (Helm & Helmfile)

This pattern includes a Helm wrapper chart (`chart/`) supporting dual-mode deployment:
1. **Standalone Mode (`manifests/`)**: Apply raw manifests directly using `kubectl apply -f manifests/`.
2. **Orchestrated Mode (`chart/` & `foundations/releases/5-workload-factory`)**: Deploy User Cluster workloads (`apps.enabled=true`, `gdc.enabled=false`) via Stage 5 of the `foundations/` Helmfile pipeline after Stage 2 (`2-resources`) provisions Zonal databases and VMs via `charts/gdc-dbs` and `charts/gdc-vm`.
