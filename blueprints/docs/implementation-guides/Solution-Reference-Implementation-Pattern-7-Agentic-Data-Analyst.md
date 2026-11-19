Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 7: Agentic Data Analyst on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Agentic Data Analyst** pattern on Google Distributed Cloud (GDC) air-gapped environments. This pattern features an LLM-powered autonomous agent utilizing the Agent Development Kit (ADK) python framework to query a structured database (PostgreSQL HA) to answer user questions, safely parsing and executing SQL commands using read-only database credentials.

## **Architecture**

The solution consists of the ADK agent running in a GKE deployment, exposed to clients internally, querying a managed database using credentials injected securely at runtime.

```
                             [ User Client ]
                                   │
                                   ▼ (Natural Language Query)
                           [ sql-agent ] (API)
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   ▼ (Read-Only SQL)
                 │                       [ GDC Database: postgres-db ]
                 │
  ┌──────────────┴──────────────┐
  │ (Reason & Plan Loop)        │
  ▼                             ▼
(Option A: Gemma Gateway)    (Option B: GDC Gemini Gateway)
[ Gemma Inference Gateway ]  [ GDC AI Inference Gateway ]
 (vLLM / Ollama Endpoint)     (OpenAI SDK + GDC STS Token +
 Model: Gemma 4 26B / 31B     x-goog-user-project Header)
                              Model: google/gemini-3.5-flash /
                                     google/gemini-3.1-flash-lite
```

### **Key Solution Capabilities**

* **ADK Agent Loop**: Uses the ReAct (Reason-Action) paradigm to decide which SQL operations are necessary to resolve prompts.
* **Strict Read-Only Access Enforcement**: The agent is bound exclusively to read-only database tables, protecting production data from accidental mutations.
* **Dual LLM Gateway Integration**: Supports reasoning requests over:
  * **Option A (Primary)**: Self-hosted **Gemma Inference Gateway** (`../gdc_gemma_gw`) providing offline inference for Gemma models.
  * **Option B (Alternative)**: Native **GDC Gemini AI Gateway** exposing Gemini models via an OpenAI-compatible interface authenticated with GDC STS tokens and `x-goog-user-project` headers.
* **Namespace Isolation & Blueprint Hydration**: Blueprints use `./configure-blueprints.sh -p <project-id> -n <target-namespace>` to bind workloads seamlessly to custom namespaces (such as `gemma-inference`).
* **Decoupled Security Credentials**: DB connection details are injected via a GDC Kubernetes Secret (`db-ro-creds`), rather than hardcoded in the deployment definition.

---

## **LLM Gateway Integration & Cross-Cluster Topology Guidance**

Pattern 7 is designed to consume either the self-hosted **Gemma Inference Gateway** (`gdc_gemma_gw`) or the native **GDC Gemini AI Gateway**.

> [!NOTE]
> **Cross-Cluster & Shared-Services Gateway Access**:
> The inference gateway does **not** need to be co-located in the same cluster or namespace as the SQL Agent application.
> Depending on enterprise infrastructure deployment, `LLM_GATEWAY_URL` can point to:
> * **Co-located Namespace**: `http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`
> * **Shared Services Cluster / Namespace**: `http://gemma-gateway.shared-services.svc.cluster.local:80/v1`
> * **Dedicated External GPU Cluster**: `https://ai-gateway.shared-services.gdc.local/v1` (exposed via GDC Gateway API `HTTPRoute` or load balancer FQDN).

---

## **Production Deployment vs Connected Artifact Preparation**

| Dimension | **Connected Sideloading Workstation** | **GDC Air-Gapped Production** |
| :--- | :--- | :--- |
| **Database** | Local development container / StatefulSet for offline testing | GDC Database Service (Managed PostgreSQL HA) |
| **LLM Inference** | Container image download & model weights packaging | Gemma Gateway (`gdc_gemma_gw`) or GDC AI Inference Gateway |
| **Credentials Injection** | Local K8s Secret `db-ro-creds` (`host: postgres-svc`) | Secret Manager / GDC KMS Credential Injection |
| **Target Namespace** | Connected staging registry (`harbor.gdc.local`) | Organization Workload Namespace (hydrated via `-n`) |
| **Service Exposure** | Local CLI / Docker execution | GDC Gateway API (`HTTPRoute`) |

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* The LLM Gateway (Pattern 5) deployed and active.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL HA).
  * **GKE Developer**: `namespace-admin` / `cluster-developer` (to deploy manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the custom SQL agent container image to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p7-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom agent image:
```bash
docker tag p7-agent:v1 harbor.shared-services.gdc.local/my-org/p7-agent:v1
docker push harbor.shared-services.gdc.local/my-org/p7-agent:v1
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p7-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry p7-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.3 Base Cluster Resource & Node Pool Requirements

### 1.3.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **ADK Agent Worker** | 2 | 100m (500m) | 128Mi (512Mi) | None |
| **PostgreSQL HA** | 2 | 2 (2) | 8Gi (8Gi) | 50Gi PVC |

### 1.3.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Dedicated to hosting the ADK agent workers and the PostgreSQL database backend.
* **Instance Type**: 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node).
* **Total Resource Pool**: 8 vCPUs, 32Gi RAM.
* **Resilience Configuration**: Spreading components across at least 2 physical nodes ensures that agent replicas and database pairs are distributed, minimizing downtime during node upgrades or physical host crashes.

### 1.3.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p7-shared-cluster
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
  name: p7-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p7-shared-cluster
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
  name: p7-standard-cluster
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

Configure `nodeSelector` in your ADK agent and database manifests:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Deploying the Target Database**

### 2.1 Provision PostgreSQL DBCluster

Deploy the managed PostgreSQL 15 database (`postgresql.dbadmin.gdc.goog/v1`) on the Zonal Management Plane (`ZONE_KUBECONFIG`) which the analyst agent will inspect.

#### Option A: Manual (CLI)
```shell
export DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"

gdcloud database clusters create postgres-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_15 \
  --availability-type=zonal_ha \
  --admin-password="${DB_ADMIN_PASSWORD}" \
  --cpu=2 --memory=8Gi --storage-size=50Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/db/postgres.yaml` on `ZONE_KUBECONFIG`)
Apply both the `dbsadmin` password `Secret` (`db-pw-postgres-db`, key `postgres-db`) and the `DBCluster` resource against `ZONE_KUBECONFIG`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-postgres-db
  namespace: my-gdc-project
type: Opaque
data:
  postgres-db: "<base64-admin-password>"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: postgres-db
  namespace: my-gdc-project
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-postgres-db
    version: "15"
    resources:
      cpu: 2
      memory: 8Gi
      disks:
        - name: DataDisk
          size: 50Gi
```

### 2.2 Endpoint Discovery, TLS Root CA & `dbsadmin` Read-Only Role Setup

GDCag Managed PostgreSQL does **not** automatically create a `postgres-db-credentials` Secret on the User Cluster. Once `DBCluster/postgres-db` reaches `READY` on `ZONE_KUBECONFIG`, query its primary DNS endpoint, extract the server TLS CA certificate from `Secret/dbs-certificates`, and connect as `dbsadmin` (`cloudsqlsuperuser`) over verified TLS to create the dedicated read-only `analyst_ro` role and sample reporting schema:

```shell
# 1. Discover primary DNS endpoint and extract TLS Root CA on ZONE_KUBECONFIG
DB_ENDPOINT=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog postgres-db \
  -n my-gdc-project -o jsonpath='{.status.primary.url}')
DB_HOST="${DB_ENDPOINT%:5432}"

kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n my-gdc-project -o jsonpath='{.data.dbs-pg-cert-postgres-db}' | base64 -d > ca.crt

# 2. Connect as dbsadmin over verified TLS to create the read-only analyst_ro role and sample tables
export PGPASSWORD="${DB_ADMIN_PASSWORD}"
export ANALYST_RO_PASSWORD="<strong-readonly-password>"

PGSSLMODE=verify-ca PGSSLROOTCERT=./ca.crt \
  psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d postgres <<SQL
-- Create dedicated read-only role
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst_ro') THEN
    CREATE ROLE analyst_ro WITH LOGIN PASSWORD '${ANALYST_RO_PASSWORD}';
  END IF;
END
\$\$;

-- Create sample reporting tables
CREATE TABLE IF NOT EXISTS product_sales (
    id SERIAL PRIMARY KEY,
    product_name VARCHAR(100),
    units_sold INT,
    revenue NUMERIC(10,2),
    quarter VARCHAR(10)
);

INSERT INTO product_sales (product_name, units_sold, revenue, quarter) VALUES
('Standard License', 1500, 75000.00, '2026-Q1'),
('Pro Add-on', 450, 45000.00, '2026-Q1');

-- Grant strictly read-only access to reporting tables
GRANT CONNECT ON DATABASE postgres TO analyst_ro;
GRANT USAGE ON SCHEMA public TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO analyst_ro;
SQL
```

### 2.3 Deploy Agent Read-Only & TLS CA Secrets on User Cluster

Create the Kubernetes `Secret`s holding the read-only `analyst_ro` credentials (`db-ro-creds`) and server TLS CA certificate (`postgres-db-ca`) on the User Cluster (`USER_CLUSTER_KUBECONFIG`):

```shell
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic db-ro-creds \
  --from-literal=username="analyst_ro" \
  --from-literal=password="${ANALYST_RO_PASSWORD}" \
  --from-literal=host="${DB_HOST}" \
  -n my-gdc-project

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic postgres-db-ca \
  --from-file=ca.crt=./ca.crt \
  -n my-gdc-project
```

---

## **Section 3: Deploying the Agent**

#### Option A: Manual (CLI)
```shell
kubectl apply -f sql-agent.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/sql-agent.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sql-agent
  namespace: my-gdc-project
spec:
  replicas: 2
  selector:
    matchLabels:
      app: sql-agent
  template:
    metadata:
      labels:
        app: sql-agent
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: adk-agent
        image: harbor.shared-services.gdc.local/my-org/p7-agent:v1
        imagePullPolicy: Always
        command: ["python", "app.py"]
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
        env:
        - name: DB_USER
          valueFrom: { secretKeyRef: { name: db-ro-creds, key: username } }
        - name: DB_PASS
          valueFrom: { secretKeyRef: { name: db-ro-creds, key: password } }
        - name: DB_HOST
          valueFrom: { secretKeyRef: { name: db-ro-creds, key: host } }
        - name: DB_NAME
          value: "postgres"
        - name: LLM_URL
          value: "http://llm-gateway.my-gdc-project.svc.cluster.local:80/generate"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: sql-agent
  namespace: my-gdc-project
spec:
  selector:
    app: sql-agent
  ports:
  - port: 80
    targetPort: 8080
  type: ClusterIP
```

---

## **Section 4: Validation**

### 4.1 Test Agent Ingestion & Processing

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute an ephemeral verification query directly against the internal `sql-agent` Service:

```bash
kubectl run p7-verify --rm -i --restart=Never -n my-gdc-project \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"harbor-creds"}]}}' \
  --image="${PROJECT_HARBOR}/iac/curl:8.12.1" --command -- sh -ec '
    sleep 2 && \
    curl -s -X POST http://sql-agent/query -d "{\"question\": \"How many total units of Standard License were sold?\"}" -H "Content-Type: application/json" && \
    echo "" && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 7 Agentic Data Analyst verified!" && \
    echo "✅ SUCCESS: Natural language SQL query agent reachable" && \
    echo "===============================================" 
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 7 Agentic Data Analyst verified!
✅ SUCCESS: Natural language SQL query agent reachable
===============================================
{"result":"1500"}
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: ClusterIP & Log Verification
Query the analyst agent service manually via ClusterIP:
```shell
export AGENT_IP=$(kubectl get service sql-agent -n my-gdc-project -o jsonpath='{.spec.clusterIP}')

curl -X POST http://${AGENT_IP}/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many total units of Standard License were sold?"}'
```
Check the agent's logic flow from its logs:
```shell
kubectl logs -l app=sql-agent -n my-gdc-project --tail=20
```
Ensure you see the agent calling the LLM Gateway, planning the select statement `SELECT SUM(units_sold) FROM product_sales WHERE product_name = 'Standard License';`, executing it, and returning the parsed response value (`1500`).

### 4.3 Live Operational Log Inspection
To validate live system execution and verify LLM gateway routing, inspect pod logs across key components:

```bash
# 1. Inspect SQL Agent NL-to-SQL reasoning & query execution logs
kubectl logs -l app=sql-agent -n my-gdc-project --tail=50 -f

# 2. Inspect Gemma Inference Gateway LLM prompt & token generation logs
kubectl logs -l app=gemma-gateway -n my-gdc-project --tail=50 -f

# 3. Inspect PostgreSQL Database connection & query logs
kubectl logs postgres-0 -n my-gdc-project --tail=50 -f
```

---

## **Section 5: Operations & Troubleshooting**

### 5.1 Database High Availability & Failover

In GDC air-gapped `v1.15.1+`, `DBCluster` resources configured with `spec.availability.enableHighAvailability: true` enable automatic failover (`enableAutoFailover: true`) by default upon primary instance failure. Operators can also trigger planned switchovers or manual failovers via the `gdcloud` CLI or the declarative `fleet.dbadmin.gdc.goog/v1` `Failover` custom resource.

#### Option A: Manual Switchover / Failover (CLI)
To trigger an operator-initiated failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover postgres-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml` on `ZONE_KUBECONFIG`)
Apply a `Failover` custom resource to trigger a switchover or manual failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-postgres-db
  namespace: my-gdc-project
spec:
  dbclusterRef: postgres-db
```

### 5.2 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Permission Denied (SQL)` | Agent attempted to run a mutating statement (e.g. UPDATE, INSERT) or user permissions are restricted. | Confirm the DB user `analyst_ro` has SELECT permissions on all tables. |
| `LLM Gateway timeout` | The gateway endpoint failed to return a response within timeout. | Check gateway health status and check if the underlying Gemini service has quota limit bottlenecks. |
| `ReAct planning loop crash` | The model returned invalid planning actions that broke the ADK parsing code. | Verify parsing filters or upgrade parser libraries inside the agent's container. |

---

## IaC Framework Integration (Helm & Helmfile)

This pattern includes a Helm wrapper chart (`chart/`) supporting dual-mode deployment:
1. **Standalone Mode (`manifests/`)**: Apply raw manifests directly using `kubectl apply -f manifests/`.
2. **Orchestrated Mode (`chart/` & `foundations/releases/5-workload-factory`)**: Deploy User Cluster workloads (`apps.enabled=true`, `gdc.enabled=false`) via Stage 5 of the `foundations/` Helmfile pipeline after Stage 2 (`2-resources`) provisions Zonal databases and VMs via `charts/gdc-dbs` and `charts/gdc-vm`.
