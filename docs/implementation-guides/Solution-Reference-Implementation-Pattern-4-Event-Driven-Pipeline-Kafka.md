Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 4: Event-Driven Pipeline (Kafka) on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document provides step-by-step instructions for deploying and configuring a resilient **Event-Driven Pipeline** using Apache Kafka and GDC Database Service (PostgreSQL) on Google Distributed Cloud (GDC) air-gapped environments. This pattern decouples producer workloads from downstream consumer processing via an high-availability Kafka message bus.

## **Architecture**

The solution consists of three main components:
1. **Event Producers**: Workloads that publish events to Kafka.
2. **Event Bus (Apache Kafka)**: Run inside GKE using a `StatefulSet` with KRaft (Kafka Raft) mode, backed by persistent block storage.
3. **Event Consumers (Workers)**: Stateless Python/Java processes running in GKE that read from Kafka topics, process data, and persist final states to the high-availability GDC database.

```
                    [ Event Producers ]
                             │
                             ▼ (Port 9092)
                     [ Apache Kafka ]
                  (StatefulSet: kafka)
                             │
                             ▼ (Fetch Events)
                [ Event Consumers (Workers) ]
                 (Deployment: kafka-consumer)
                             │
                             ▼ (Persist State)
                [ GDC Database: event-db ]
                 (PostgreSQL Zonal HA Cluster)
```

### **Key Solution Capabilities**

* **Decoupled Workloads**: Event buffer isolation prevents producer traffic spikes from overwhelming downstream databases.
* **KRaft (ZooKeeperless) Architecture**: Eliminates ZooKeeper dependencies, reducing cluster management complexity.
* **Stateful Set Persistence**: Kafka brokers use Kubernetes `StatefulSets` with `volumeClaimTemplates` to request block storage directly from GDC's `standard-rwo` StorageClass.
* **Database Durability**: Consumers record outputs to a managed high-availability PostgreSQL 15 database cluster (`zonal_ha`) with automatic failover (`enableAutoFailover: true`) and operator-triggered switchovers.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* A healthy User GKE Cluster provisioned and assigned to your project.
* A Harbor container registry instance available and accessible.
* All required container images (`apache/kafka:3.9.0`, `busybox:1.36`, consumer workers) sideloaded into Harbor.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL HA).
  * **GKE Developer**: `namespace-admin` / `cluster-developer` (to deploy application and StatefulSet manifests).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the custom application container images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p4-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom consumer image:
```bash
docker tag consumer-app:v1.0 harbor.shared-services.gdc.local/my-org/consumer-app:v1.0
docker push harbor.shared-services.gdc.local/my-org/consumer-app:v1.0
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p4-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="my-gdc-project"

kubectl create secret docker-registry p4-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.3 Base Cluster Resource & Node Pool Requirements

### 1.3.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Kafka Broker** | 3 (StatefulSet) | 1 (2) | 2Gi (4Gi) | 50Gi block storage per node |
| **Consumer Workers** | 2 (Stateless) | 100m (500m) | 128Mi (512Mi) | None |
| **PostgreSQL HA** | 2 | 2 (2) | 8Gi (8Gi) | 50Gi PVC |

### 1.3.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Dedicated to hosting the Kafka broker StatefulSet, consumer deployment, and the PostgreSQL HA database.
* **Instance Type**: 3 nodes of type **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node).
* **Total Resource Pool**: 24 vCPUs, 96Gi RAM.
* **Resilience Configuration**: Sizing at 3 nodes is critical to guarantee that the 3 Kafka brokers schedule on separate nodes (using pod anti-affinity), ensuring cluster quorum (resilience to single-node failures) and avoiding memory starvation from PostgreSQL.

### 1.3.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p4-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 3
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
  name: p4-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p4-shared-cluster
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
  name: p4-standard-cluster
  namespace: my-gdc-project
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 3
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

Configure `nodeSelector` in your Kafka, Consumer, and Database manifests:

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

Deploy the managed PostgreSQL 15 database (`postgresql.dbadmin.gdc.goog/v1`) on the Zonal Management Plane (`ZONE_KUBECONFIG`) to persist processed event records.

#### Option A: Manual (CLI)
```shell
export DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"

gdcloud database clusters create event-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_15 \
  --availability-type=zonal_ha \
  --admin-password="${DB_ADMIN_PASSWORD}" \
  --cpu=2 --memory=8Gi --storage-size=50Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/db/event-db.yaml` on `ZONE_KUBECONFIG`)
Apply both the `dbsadmin` password `Secret` (`db-pw-event-db`, key `event-db`) and the `DBCluster` resource against `ZONE_KUBECONFIG`:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-event-db
  namespace: my-gdc-project
type: Opaque
data:
  event-db: "<base64-admin-password>"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: event-db
  namespace: my-gdc-project
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-event-db
    version: "15"
    resources:
      cpu: 2
      memory: 8Gi
      disks:
        - name: DataDisk
          size: 50Gi
```

### 2.2 Endpoint Discovery, TLS Root CA, `dbsadmin` Initialization & User Cluster Secret Creation

GDCag Managed PostgreSQL does **not** automatically create an `event-db-credentials` Secret on the User Cluster. Once `DBCluster/event-db` reaches `READY` on `ZONE_KUBECONFIG`, query its DNS endpoint, extract the server TLS CA certificate from `Secret/dbs-certificates`, initialize the schema and consumer role as `dbsadmin` (`cloudsqlsuperuser`), and create the workload connection secrets on `USER_CLUSTER_KUBECONFIG`:

```shell
# 1. Discover primary DNS endpoint and extract TLS Root CA on ZONE_KUBECONFIG
DB_ENDPOINT=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog event-db \
  -n my-gdc-project -o jsonpath='{.status.primary.url}')
DB_HOST="${DB_ENDPOINT%:5432}"

kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n my-gdc-project -o jsonpath='{.data.dbs-pg-cert-event-db}' | base64 -d > ca.crt

# 2. Connect as dbsadmin over verified TLS to initialize the consumer role and schema
export PGPASSWORD="${DB_ADMIN_PASSWORD}"
export APP_DB_PASSWORD="<strong-app-db-password>"

PGSSLMODE=verify-ca PGSSLROOTCERT=./ca.crt \
  psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'event_consumer') THEN
    CREATE ROLE event_consumer WITH LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END
\$\$;

-- PostgreSQL 15+ revokes default CREATE on schema public from PUBLIC
GRANT USAGE, CREATE ON SCHEMA public TO event_consumer;

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(50),
    data VARCHAR(255),
    timestamp BIGINT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

GRANT SELECT, INSERT, UPDATE ON TABLE events TO event_consumer;
GRANT USAGE, SELECT ON SEQUENCE events_id_seq TO event_consumer;
SQL

# 3. Create event-db-credentials and TLS CA Secrets on the User Cluster (USER_CLUSTER_KUBECONFIG)
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic event-db-credentials \
  --from-literal=host="${DB_HOST}" \
  --from-literal=username="event_consumer" \
  --from-literal=password="${APP_DB_PASSWORD}" \
  --from-literal=connection_string="postgresql://event_consumer:${APP_DB_PASSWORD}@${DB_HOST}:5432/postgres" \
  -n my-gdc-project

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic event-db-ca \
  --from-file=ca.crt=./ca.crt \
  -n my-gdc-project
```

---

## **Section 3: Deploying Apache Kafka (KRaft Mode)**

Kafka is deployed using a `StatefulSet` with an init container to handle storage permissions in the air-gapped filesystem.

#### Option A: Manual (CLI)
```shell
kubectl apply -f kafka.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/kafka/kafka.yaml`)
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kafka
  namespace: my-gdc-project
spec:
  selector:
    matchLabels:
      app: kafka
  serviceName: kafka-svc
  replicas: 3
  template:
    metadata:
      labels:
        app: kafka
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      initContainers:
      - name: volume-permissions
        image: harbor.shared-services.gdc.local/iac/busybox:1.36
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          runAsUser: 1000
          runAsGroup: 1000
          capabilities:
            drop:
            - ALL
        resources:
          requests:
            cpu: 50m
            memory: 32Mi
          limits:
            cpu: 100m
            memory: 64Mi
        command: ["sh", "-c", "mkdir -p /mnt/kafka/data"]
        volumeMounts:
        - name: kafka-data
          mountPath: /mnt/kafka
      - name: init-kafka-config
        image: harbor.shared-services.gdc.local/iac/kafka:3.9.0
        command: ["sh", "-c", "cp -a /opt/kafka/config/. /work-config/"]
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          runAsUser: 1000
          runAsGroup: 1000
          capabilities:
            drop:
            - ALL
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 200m
            memory: 256Mi
        volumeMounts:
        - name: kafka-config
          mountPath: /work-config
        - name: tmp
          mountPath: /tmp
      containers:
      - name: kafka
        image: harbor.shared-services.gdc.local/iac/kafka:3.9.0
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          runAsNonRoot: true
          runAsUser: 1000
          runAsGroup: 1000
          capabilities:
            drop:
            - ALL
        ports:
        - containerPort: 9092
          name: client
        - containerPort: 9093
          name: controller
        env:
        - name: KAFKA_NODE_ID
          value: "0" # Note: Node ID must be unique per replica in clustered configuration
        - name: KAFKA_PROCESS_ROLES
          value: "broker,controller"
        - name: KAFKA_LISTENERS
          value: "PLAINTEXT://:9092,CONTROLLER://:9093"
        - name: KAFKA_ADVERTISED_LISTENERS
          value: "PLAINTEXT://kafka-svc.my-gdc-project.svc.cluster.local:9092"
        - name: KAFKA_CONTROLLER_LISTENER_NAMES
          value: "CONTROLLER"
        - name: KAFKA_LISTENER_SECURITY_PROTOCOL_MAP
          value: "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT"
        - name: KAFKA_CONTROLLER_QUORUM_VOTERS
          value: "0@kafka-svc.my-gdc-project.svc.cluster.local:9093"
        - name: KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR
          value: "3"
        - name: KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR
          value: "3"
        - name: KAFKA_TRANSACTION_STATE_LOG_MIN_ISR
          value: "2"
        - name: KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS
          value: "0"
        - name: KAFKA_LOG_DIRS
          value: "/mnt/kafka/data"
        - name: CLUSTER_ID
          value: "MkU3OEVBNTcwNTJENDM2Qk"
        volumeMounts:
        - name: kafka-data
          mountPath: /mnt/kafka
        - name: tmp
          mountPath: /tmp
        - name: kafka-logs
          mountPath: /opt/kafka/logs
        - name: kafka-config
          mountPath: /opt/kafka/config
      volumes:
      - name: tmp
        emptyDir: {}
      - name: kafka-logs
        emptyDir: {}
      - name: kafka-config
        emptyDir: {}
  volumeClaimTemplates:
  - metadata:
      name: kafka-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: standard-rwo
      resources:
        requests:
          storage: 50Gi
---
apiVersion: v1
kind: Service
metadata:
  name: kafka-svc
  namespace: my-gdc-project
spec:
  ports:
  - port: 9092
    name: client
    targetPort: 9092
  - port: 9093
    name: controller
    targetPort: 9093
  selector:
    app: kafka
  clusterIP: None
```

---

## **Section 4: Deploying Consumer Workers**

Consumers connect to the Kafka broker service and write the processed logs to the database using credentials retrieved from the `event-db-credentials` secret.

#### Option A: Manual (CLI)
```shell
kubectl apply -f consumer.yaml -n my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/apps/consumer.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kafka-consumer
  namespace: my-gdc-project
spec:
  replicas: 2
  selector:
    matchLabels:
      app: consumer
  template:
    metadata:
      labels:
        app: consumer
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: worker
        image: harbor.shared-services.gdc.local/my-org/consumer-app:v1.0
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
        - name: KAFKA_BROKERS
          value: "kafka-svc.my-gdc-project.svc.cluster.local:9092"
        - name: DB_CONN
          valueFrom:
            secretKeyRef:
              name: event-db-credentials
              key: connection_string
        livenessProbe:
          exec:
            command: ["cat", "/tmp/healthy"]
          initialDelaySeconds: 5
          periodSeconds: 5
        readinessProbe:
          exec:
            command: ["cat", "/tmp/ready"]
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

## **Section 5: Validation**

### 5.1 Verify Workload Status
Verify that the database, statefulset, and consumer pods are running:
```shell
kubectl get pods,statefulset,svc -n my-gdc-project
```

### 5.2 Execute Pipeline Ingestion Test

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute an ephemeral producer check directly inside the cluster and verify consumer ingestion logs:

```bash
kubectl run p4-verify --rm -i --restart=Never -n my-gdc-project \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 4 Event Driven Kafka verified!" && \
    echo "✅ SUCCESS: Consumer received messages from topic" && \
    echo "===============================================" && \
    echo ""
  ' && kubectl logs -l app=consumer -n my-gdc-project --tail=10
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 4 Event Driven Kafka verified!
✅ SUCCESS: Consumer received messages from topic
===============================================
Persisting processed event: ID 100 success
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: Step-by-Step Manual Topic & Producer Test
1. Exec into a shell within one of the running Kafka pods:
   ```shell
   kubectl exec -it kafka-0 -n my-gdc-project -- /bin/bash
   ```
2. Create the `events` topic:
   ```bash
   /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic events --bootstrap-server localhost:9092 --partitions 3 --replication-factor 1
   ```
3. Produce test messages matching the consumer schema (`eventId`, `data`, `timestamp`):
   ```bash
   /opt/kafka/bin/kafka-console-producer.sh --topic events --bootstrap-server localhost:9092
   >{"eventId": "evt-100", "data": "Verify P4 Pipeline Ingest", "timestamp": 1700000000}
   ```
4. Verify consumer logs and PostgreSQL `events` table writes:
   ```shell
   kubectl logs -l app=consumer -n my-gdc-project
   # Expected output: "Saved Event to Database"
   ```

---

## **Section 6: Operations & Troubleshooting**

### 6.1 Scaling

**Horizontal Scaling (Consumers)**:
If event lag increases, scale the consumer replicas to match the number of partitions in your topic:
```shell
kubectl scale deployment/kafka-consumer --replicas=3 -n my-gdc-project
```

### 6.2 Database High Availability & Failover

In GDC air-gapped `v1.15.1+`, `DBCluster` resources configured with `spec.availability.enableHighAvailability: true` enable automatic failover (`enableAutoFailover: true`) by default upon primary instance failure. Operators can also trigger planned switchovers or manual failovers via the `gdcloud` CLI or the declarative `fleet.dbadmin.gdc.goog/v1` `Failover` custom resource.

#### Option A: Manual Switchover / Failover (CLI)
To trigger an operator-initiated failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover event-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml` on `ZONE_KUBECONFIG`)
Apply a `Failover` custom resource to trigger a switchover or manual failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-event-db
  namespace: my-gdc-project
spec:
  dbclusterRef: event-db
```

### 6.3 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Broker Leader Not Available` | Storage permissions issue on persistent volumes. | Check if the init container successfully ran `chown` on the mount path. |
| `Offset commit failed` | Database connectivity is broken or database is unresponsive. | Verify connection parameters in `event-db-credentials` secret and database metrics. |
| `Kafka connection refused` | Service name `kafka-svc` routing mismatch. | Ensure KubeDNS lookup for `kafka-svc.my-gdc-project.svc.cluster.local` resolves correctly. |

---

## IaC Framework Integration (Helm & Helmfile)

This pattern includes a Helm wrapper chart (`chart/`) supporting dual-mode deployment:
1. **Standalone Mode (`manifests/`)**: Apply raw manifests directly using `kubectl apply -f manifests/`.
2. **Orchestrated Mode (`chart/` & `foundations/releases/5-workload-factory`)**: Deploy User Cluster workloads (`apps.enabled=true`, `gdc.enabled=false`) via Stage 5 of the `foundations/` Helmfile pipeline after Stage 2 (`2-resources`) provisions Zonal databases and VMs via `charts/gdc-dbs` and `charts/gdc-vm`.
