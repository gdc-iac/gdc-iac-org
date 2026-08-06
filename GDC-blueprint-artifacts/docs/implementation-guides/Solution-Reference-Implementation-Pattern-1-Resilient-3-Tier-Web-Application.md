Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 1: Resilient 3-Tier Web Application on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Resilient 3-Tier Web Application** pattern on Google Distributed Cloud (GDC) air-gapped environments. This architectural blueprint demonstrates the standard separation of concerns—Presentation (Web), Logic (App), and Data (DB)—under high availability (HA) constraints with zero external internet dependencies.

## **Architecture**

The architecture splits responsibilities into three distinct tiers:
1. **Web Tier (Presentation)**: Replicated Nginx containers serving frontend assets and proxying API traffic.
2. **App Tier (Logic)**: Stateless API servers executing core business logic, decoupled and scaled horizontally.
3. **Data Tier (Persistence)**: A managed high-availability PostgreSQL database service with zonal replication and manual failover.

```
                    [ Downstream Client / User ]
                                 │
                                 ▼
                     [ GDC PLATFORM GATEWAY ]
                       (Gateway: web-gateway)
                                 │
                                 ▼
                       [ Web Tier: web-tier ] (Nginx)
                           (Port 8080 / 3 Replicas)
                                 │
                                 ▼
                      [ GKE Service: logic-svc ]
                                 │
                                 ▼
                     [ App Tier: logic-tier ] (API)
                           (Port 8080 / 2 Replicas)
                                 │
                                 ▼
                    [ GDC Database: tier3-db ]
                     (PostgreSQL Zonal HA Cluster)
```

### **Key Solution Capabilities**

* **Tiered Decoupling**: Separation of presentation, logic, and data limits blast radiuses and lets developers optimize and scale each layer independently.
* **Zonal High Availability**: The data tier uses GDC's native `ZONAL_HA` availability configuration, offering hot standby replication and manual failover.
* **Anti-Affinity Co-location rules**: Stateless application pods implement strict pod anti-affinity to ensure replicas run on separate physical hypervisors.
* **Gateway API exposure**: External routing is managed via standard Kubernetes Gateway API (`Gateway` and `HTTPRoute` resources) bound to a platform-configured `GatewayClass`.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* A healthy User GKE Cluster provisioned and assigned to your project.
* A Harbor container registry instance available and accessible.
* All required container images (web frontend, app backend, Postgres/system images) sideloaded into your local Harbor registry.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL HA).
  * **GKE Developer**: `roles/gke.developer` (to deploy application manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the application container images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p1-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom application images:
```bash
docker tag p1-frontend:latest harbor.shared-services.gdc.local/my-org/p1-frontend:latest
docker push harbor.shared-services.gdc.local/my-org/p1-frontend:latest

docker tag p1-backend:latest harbor.shared-services.gdc.local/my-org/p1-backend:latest
docker push harbor.shared-services.gdc.local/my-org/p1-backend:latest
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p1-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry p1-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.3 Base Cluster Resource & Node Pool Requirements

### 1.3.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Web Tier** | 3 | 50m (200m) | 64Mi (256Mi) | None |
| **App Tier** | 2 | 100m (500m) | 128Mi (512Mi) | None |
| **PostgreSQL HA** | 2 (1 Primary, 1 Standby) | 2 (2) | 8Gi (8Gi) | 50Gi PVC |

### 1.3.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Dedicated to hosting the stateless frontend, backend logic, and the high-availability database pods.
* **Instance Type**: 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node).
* **Total Resource Pool**: 8 vCPUs, 32Gi RAM.
* **Resilience Configuration**: Spreading workloads across at least 2 nodes ensures that Web and App tier replicas, along with database primary/standby pairs, can withstand a single-node failure without downtime.

### 1.3.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One
If deploying in a multi-tenant environment where the cluster spans projects, write and apply the configurations against the zonal Management API server:

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p1-shared-cluster
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
  name: p1-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p1-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - my-gdc-project
```

**3. Apply the Manifests using the Zonal Management Kubeconfig:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster (Single-Tenant/Self-Contained Workload)
For isolated workloads scoped directly to a single GDC project namespace:

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p1-standard-cluster
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

**2. Apply the Manifest using the Zonal Management Kubeconfig:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.3.4 Workload Pod Assignment & Scheduling Configuration

Configure `nodeSelector` in your deployment manifests to guarantee workloads land on the provisioned CPU nodes:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Deploying the Data Tier (PostgreSQL HA)**

### 2.1 Provision PostgreSQL DBCluster

Deploy the GDC managed database cluster configuration.

#### Option A: Manual (CLI)
```shell
gdcloud database clusters create tier3-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=2 --memory=8Gi --storage-size=50Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/db/tier3-db.yaml`)
```yaml
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: tier3-db
  namespace: my-gdc-project
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA
  resources:
     requests: { cpu: "2", memory: "8Gi" }
  storage: { size: "50G" }
```

### 2.2 Initialize Database Schema

Once the database cluster reports a status of `READY`, GDC automatically creates a secret named `tier3-db-credentials` containing access information. Initialize the schema using `psql`:

```sql
CREATE TABLE IF NOT EXISTS todos (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    completed BOOLEAN NOT NULL
);
```

---

## **Section 3: Deploying the App/Logic Tier**

The logic tier utilizes pod anti-affinity to ensure that application replicas do not land on the same physical host.

#### Option A: Manual (CLI)
```shell
kubectl apply -f app-tier.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/app-tier.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: logic-tier
  namespace: my-gdc-project
spec:
  replicas: 2
  selector:
    matchLabels:
      app: logic
  template:
    metadata:
      labels:
        app: logic
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values: ["logic"]
            topologyKey: "kubernetes.io/hostname"
      containers:
      - name: api-server
        image: harbor.shared-services.gdc.local/my-org/p1-backend:latest
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
        - name: DB_NAME
          value: "postgres"
        - name: DB_HOST
          valueFrom: { secretKeyRef: { name: tier3-db-credentials, key: host } }
        - name: DB_PASS
          valueFrom: { secretKeyRef: { name: tier3-db-credentials, key: password } }
        livenessProbe:
          tcpSocket:
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          tcpSocket:
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: logic-svc
  namespace: my-gdc-project
spec:
  type: ClusterIP
  selector:
    app: logic
  ports:
  - protocol: TCP
    port: 8080
    targetPort: 8080
```

---

## **Section 4: Deploying the Web Tier**

#### Option A: Manual (CLI)
```shell
kubectl apply -f web-tier.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/web-tier.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-tier
  namespace: my-gdc-project
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 101 # Nginx UID
        fsGroup: 101
      containers:
      - name: nginx
        image: harbor.shared-services.gdc.local/my-org/p1-frontend:latest
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop: ["ALL"]
        resources:
          requests:
            cpu: "50m"
            memory: "64Mi"
          limits:
            cpu: "200m"
            memory: "256Mi"
        env:
        - name: API_UPSTREAM
          value: "http://logic-svc.my-gdc-project.svc.cluster.local:8080"
        ports:
        - containerPort: 8080
          name: http
        livenessProbe:
          httpGet:
            path: /
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: web-lb
  namespace: my-gdc-project
spec:
  type: ClusterIP
  selector:
    app: web
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
```

---

## **Section 5: High-Performance Exposure (Gateway API)**

External users consume the application via standard Kubernetes Gateway API resources (`Gateway`, `HTTPRoute`) bound to a platform-configured `GatewayClass`.

### 5.1 Provision the Gateway & Route

Configure the `GatewayClass` (backed by an Envoy Proxy or GDC platform controller) along with the `Gateway` and `HTTPRoute` resources.

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: eg
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: web-gateway
  namespace: my-gdc-project
  annotations:
    networking.gke.io/load-balancer-type: "Internal"
spec:
  gatewayClassName: eg
  listeners:
  - name: http
    protocol: HTTP
    port: 80
    allowedRoutes:
      namespaces:
        from: Same
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: web-route
  namespace: my-gdc-project
spec:
  parentRefs:
  - name: web-gateway
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: web-lb
      port: 80
```

Apply gateway manifests:
```shell
kubectl apply -f gateway-class.yaml
kubectl apply -f gateway.yaml -n my-gdc-project
```

---

## **Section 6: Network Isolation & Security**

To enforce a zero-trust model, deploy a `ProjectNetworkPolicy` to restrict direct access to the database and logic tiers, whitelisting ingress path traffic exclusively.

```yaml
apiVersion: networking.gdc.goog/v1
kind: ProjectNetworkPolicy
metadata:
  name: allow-logic-ingress
  namespace: my-gdc-project
spec:
  subject:
    subjectType: UserWorkload
  policyType: Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: web
    ports:
    - protocol: TCP
      port: 8080
```

---

## **Section 7: Validation**

### 7.1 Verify Resources
```shell
kubectl get pods,svc,gateway,httproute -n my-gdc-project
```

### 7.2 Run End-to-End Connectivity & Curl Test

#### Option A: Internal Cluster Verification (No Port-Forwarding Needed)
Execute an ephemeral verification pod directly inside the cluster against the internal application endpoints:

```bash
kubectl run p1-verify --rm -i --restart=Never -n my-gdc-project \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 1 Web Tier connectivity verified!" && \
    echo "✅ SUCCESS: Frontend reached via internal ClusterIP" && \
    echo "===============================================" && \
    wget -qO- http://web-lb/ | head -n 15 && \
    echo ""
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 1 Web Tier connectivity verified!
✅ SUCCESS: Frontend reached via internal ClusterIP
===============================================
<!DOCTYPE html>
<html>
<head>
    <title>GDC Todo App</title>
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: External Gateway LoadBalancer Verification
Determine the gateway's IP address and execute requests from the external network:
```shell
export GATEWAY_IP=$(kubectl get gateway web-gateway -n my-gdc-project -o jsonpath='{.status.addresses[0].value}')

# Add a Todo item
curl -X POST http://${GATEWAY_IP}/api/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Verify P1 Deployment", "completed": false}'

# List Todo items
curl http://${GATEWAY_IP}/api/todos
```

---

## **Section 8: Operations & Troubleshooting**

### 8.1 Scaling

**Horizontal Scaling**:
Scale the Web and App Deployments dynamically to match load:
```shell
kubectl scale deployment/web-tier --replicas=5 -n my-gdc-project
kubectl scale deployment/logic-tier --replicas=3 -n my-gdc-project
```

### 8.2 Database High Availability & Manual Failover

In GDC air-gapped, database clusters configured with `ZONAL_HA` (primary and standby replicas) do not automatically failover when the primary instance becomes unavailable. Failover must be triggered manually by an operator.

#### Option A: Manual (CLI)
To trigger a manual failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover tier3-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml`)
Apply a `Failover` custom resource to trigger the failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-tier3-db
  namespace: my-gdc-project
spec:
  dbclusterRef: tier3-db
```

### 8.3 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `DB connection timeout` | Network policies block App Tier pods from accessing the Database Service. | Verify the database ingress rules allow connections from the `app: logic` pods. |
| `503 Service Unavailable` | Gateway cannot reach the Nginx backend (Web Tier) or pods fail health probes. | Check pod logs via `kubectl logs -l app=web -n my-gdc-project` and verify readiness probes. |
| `ImagePullBackOff` | Secret `p1-pull-secret` missing, or Harbor registry is unreachable. | Confirm the secret is created in the correct namespace and Harbor robot credentials are active. |
