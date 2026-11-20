Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 3: Legacy VM + Modern Database on GDC air-gapped**

> **Version:** 1.2

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Legacy VM + Modern Database** pattern on Google Distributed Cloud (GDC) air-gapped environments. This pattern demonstrates the lift-and-shift of legacy applications that cannot be containerized but need to connect to a high-performance, modern database service (PostgreSQL) running on the same GDC infrastructure.

## **Architecture**

The architecture features a virtual machine running on GDC VM Runtime, backed by GDC Block Storage, connecting to a managed PostgreSQL High-Availability database cluster.

```
                    [ GDC VM Runtime (Legacy App VM) ] ◄───► [ GDC Block Storage (Disk) ]
                                      │
                                      │ (Internal VPC Net)
                                      ▼
                           [ GDC Database Service ]
                            (PostgreSQL HA Cluster)
                                      ▲
                                      │ (Internal VPC Net)
                            [ GDC GKE Cluster ]
                            (Modern Microservices)
```

### **Key Solution Capabilities**

* **Infrastructure Lift-and-Shift**: Supports monolithic legacy binaries (Linux/Windows) that require a full OS environment.
* **Modern Database Integration**: Connects to the high-performance PostgreSQL database service.
* **Zonal Resilience**: PostgreSQL 15 is configured for `zonal_ha` (`spec.availability.enableHighAvailability: true`), providing hot standby replication with automatic failover (`enableAutoFailover: true`) by default in GDCag `v1.15.1+` plus operator-controlled switchovers.
* **Unified VPC Networking**: Connects the VM Runtime and database clusters securely through private VPC subnetting.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* GDC VM Runtime enabled and configured by Platform Administrators.
* A legacy VM boot image (e.g., Ubuntu 20.04 or RHEL 8) imported into GDC's VM images registry.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Network Admin**: `project-networkpolicy-admin` (to create subnets).
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL).
  * **Compute Admin**: `project-vm-admin` (to create and configure VMs).

---

## **Section 1: Common Setup**

### 1.1 VPC Network Configuration

Both the database cluster and the VM must reside in a common network namespace or have routed IP paths. Establish the subnetwork manually:

```shell
export PROJECT_ID="my-gdc-project"

# 1. Create the VPC network
gdcloud compute networks create vm-net --project=${PROJECT_ID} --subnet-mode=custom

# 2. Add custom subnetwork
gdcloud compute networks subnets create vm-subnet \
  --project=${PROJECT_ID} \
  --network=vm-net \
  --range=10.1.0.0/24 \
  --region=region-1
```

### 1.2 Resource Sizing & Capacity Planning

#### **Component Resource Allocation Breakdown**

| Component | Recommended GDC Instance Size | vCPU | RAM | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Legacy VM** | `n2-highcpu-8-gdc` | 8 | 8Gi | 100Gi Persistent Disk |
| **PostgreSQL HA** | `db-custom-4-16` | 4 | 16Gi | 100Gi DB Volume |

---

## **Section 2: Deploying the Data Tier (PostgreSQL HA)**

### 2.1 Provision PostgreSQL Cluster

Create the managed PostgreSQL 15 cluster (`postgresql.dbadmin.gdc.goog/v1`) on the Zonal Management Plane (`ZONE_KUBECONFIG`).

#### Option A: Manual (CLI)
```shell
export DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"

gdcloud database clusters create legacy-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_15 \
  --availability-type=zonal_ha \
  --admin-password="${DB_ADMIN_PASSWORD}" \
  --cpu=4 --memory=16Gi --storage-size=100Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/infra/legacy-infra.yaml` on `ZONE_KUBECONFIG`)
Apply the network, the `dbsadmin` password `Secret` (`db-pw-legacy-db`, key `legacy-db`), and the `DBCluster` resource against `ZONE_KUBECONFIG`:
```yaml
apiVersion: networking.gdc.goog/v1
kind: Network
metadata:
  name: vm-net
  namespace: my-gdc-project
---
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-legacy-db
  namespace: my-gdc-project
type: Opaque
data:
  legacy-db: "<base64-admin-password>"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: legacy-db
  namespace: my-gdc-project
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-legacy-db
    version: "15"
    resources:
      cpu: 4
      memory: 16Gi
      disks:
        - name: DataDisk
          size: 100Gi
```

### 2.2 Endpoint Discovery, TLS Root CA, `dbsadmin` Initialization & Secret Creation

GDCag Managed PostgreSQL does **not** automatically create a `<cluster-name>-credentials` Secret on the User Cluster. Once `DBCluster/legacy-db` reports `READY` on `ZONE_KUBECONFIG`, discover the primary endpoint, extract the server TLS CA certificate from `Secret/dbs-certificates`, initialize the schema and application role as `dbsadmin` (`cloudsqlsuperuser`), and create the User Cluster secrets (as well as distributing `ca.crt` and `DB_HOST` to the VM):

```shell
# 1. Query primary DNS endpoint and extract TLS Root CA on ZONE_KUBECONFIG
DB_ENDPOINT=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog legacy-db \
  -n my-gdc-project -o jsonpath='{.status.primary.url}')
DB_HOST="${DB_ENDPOINT%:5432}"

kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n my-gdc-project -o jsonpath='{.data.dbs-pg-cert-legacy-db}' | base64 -d > ca.crt

# 2. Connect as dbsadmin over verified TLS to initialize the application role and schema
export PGPASSWORD="${DB_ADMIN_PASSWORD}"
export APP_DB_PASSWORD="<strong-app-db-password>"

PGSSLMODE=verify-ca PGSSLROOTCERT=./ca.crt \
  psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'legacy_app') THEN
    CREATE ROLE legacy_app WITH LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END
\$\$;

-- PostgreSQL 15+ revokes default CREATE on schema public from PUBLIC
GRANT USAGE, CREATE ON SCHEMA public TO legacy_app;

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE orders TO legacy_app;
GRANT USAGE, SELECT ON SEQUENCE orders_id_seq TO legacy_app;
SQL

# 3. Create workload connection and TLS CA Secrets on the User Cluster (USER_CLUSTER_KUBECONFIG)
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic legacy-db-credentials \
  --from-literal=host="${DB_HOST}" \
  --from-literal=username="legacy_app" \
  --from-literal=password="${APP_DB_PASSWORD}" \
  --from-literal=database="postgres" \
  -n my-gdc-project

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" create secret generic legacy-db-ca \
  --from-file=ca.crt=./ca.crt \
  -n my-gdc-project
```

---

## **Section 3: Deploying the Legacy VM**

Provision the virtual machine on GDC's VM Runtime and bind it to the subnetwork.

#### Option A: Manual (CLI)
```shell
gdcloud compute instances create app-vm-01 \
  --project=my-gdc-project \
  --zone=zone-1 \
  --machine-type=n2-highcpu-8-gdc \
  --image-project=gradec-images --image-family=ubuntu-2004 \
  --subnet=vm-subnet
```

#### Option B: GitOps / IaC (`manifests/gdc/vm/app-vm.yaml`)
```yaml
apiVersion: virtualmachine.compute.gdc.goog/v1
kind: VirtualMachine
metadata:
  name: app-vm-01
  namespace: my-gdc-project
spec:
  compute:
    machineType: n2-highcpu-8-gdc
  storage:
    disks:
    - boot: true
      size: 10G
      source:
        image: projects/gradec-images/global/images/family/ubuntu-2004
  networkInterfaces:
  - subnetwork: vm-subnet
```

---

## **Section 4: Networking & Exposure**

Legacy VMs communicate with the database cluster via internal subnetwork IP addresses.

To authorize database access:
1. Fetch the primary instance IP address of the database:
   ```shell
   gdcloud database clusters describe legacy-db --project=my-gdc-project
   ```
2. Configure the connection parameters (Database host, credentials) directly in the legacy application configuration inside the VM.

---

## **Section 5: Validation**

### 5.1 Verify VM Status
Ensure the virtual machine is in `Running` state:
```shell
gdcloud compute instances describe app-vm-01 --project=my-gdc-project --zone=zone-1
```

### 5.2 Verify Connection from VM to Database

#### Option A: GDC VM Runtime SSH Verification (Production Air-Gapped)
SSH into the legacy VM and verify that it can reach the database on port `5432`:
```shell
# Open SSH session
gdcloud compute ssh app-vm-01 --project=my-gdc-project --zone=zone-1

# Inside the VM, run verification check against the database ClusterIP
echo "Testing connection to PostgreSQL..." && \
nc -zv ${DB_HOST} 5432 && \
echo "===============================================" && \
echo "✅ PASS: Pattern 3 Legacy VM -> Modern DB verified!" && \
echo "✅ SUCCESS: Database port 5432 reachable from VM" && \
echo "==============================================="
```
**Expected Production Output:**
```text
Connection to 10.1.0.10 5432 port [tcp/postgresql] succeeded!
===============================================
✅ PASS: Pattern 3 Legacy VM -> Modern DB verified!
✅ SUCCESS: Database port 5432 reachable from VM
===============================================
```

#### Option B: Container Verification Check (Connected Workstation Sideloading)
If validating on a connected workstation prior to sideloading into GDC air-gapped:
```bash
kubectl run p3-verify --rm -i --restart=Never -n my-gdc-project \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 3 Legacy VM -> Modern DB verified!" && \
    echo "✅ SUCCESS: Database credentials and network reachable" && \
    echo "===============================================" && \
    echo ""
  ' && kubectl logs -l app=legacy-vm -n my-gdc-project --tail=10
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

---

## **Section 6: Operations & Troubleshooting**

### 6.1 Scaling

**VM Resizing (Vertical Scaling)**:
monolithic VMs must be stopped to resize compute parameters:
1. Stop the instance:
   ```shell
   gdcloud compute instances stop app-vm-01 --project=my-gdc-project --zone=zone-1
   ```
2. Update machine type:
   ```shell
   gdcloud compute instances set-machine-type app-vm-01 --machine-type=n2-standard-16-gdc --project=my-gdc-project --zone=zone-1
   ```
3. Restart the instance:
   ```shell
   gdcloud compute instances start app-vm-01 --project=my-gdc-project --zone=zone-1
   ```

### 6.2 Database High Availability & Failover

In GDC air-gapped `v1.15.1+`, `DBCluster` resources configured with `spec.availability.enableHighAvailability: true` enable automatic failover (`enableAutoFailover: true`) by default upon primary instance failure. Operators can also trigger planned switchovers or manual failovers via the `gdcloud` CLI or the declarative `fleet.dbadmin.gdc.goog/v1` `Failover` custom resource.

#### Option A: Manual Switchover / Failover (CLI)
To trigger an operator-initiated failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover legacy-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/infra/failover.yaml` on `ZONE_KUBECONFIG`)
Apply a `Failover` custom resource to trigger a switchover or manual failover declaratively:
```yaml
apiVersion: fleet.dbadmin.gdc.goog/v1
kind: Failover
metadata:
  name: trigger-failover-legacy-db
  namespace: my-gdc-project
spec:
  dbclusterRef: legacy-db
```

### 6.3 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `VM fails to schedule` | Zonal physical compute resource exhaustion. | Try creating the instance in a different GDC availability zone. |
| `DB Connection Refused` | Subnetwork route rules are misconfigured or VM is in a different VPC namespace. | Ensure the DB cluster and VM subnetwork reside in the same VPC or that VPC peering is active. |
| `PostgreSQL HA Planned Maintenance` | Planned host maintenance or primary switchover validation. | Automatic failover (`enableAutoFailover: true`) handles unplanned primary failures; trigger a planned switchover via `gdcloud database clusters failover` or `Failover` CR. |

---

## IaC Framework Integration (Helm & Helmfile)

This pattern includes a Helm wrapper chart (`chart/`) supporting dual-mode deployment:
1. **Standalone Mode (`manifests/`)**: Apply raw manifests directly using `kubectl apply -f manifests/`.
2. **Orchestrated Mode (`chart/` & `foundations/releases/5-workload-factory`)**: Deploy User Cluster workloads (`apps.enabled=true`, `gdc.enabled=false`) via Stage 5 of the `foundations/` Helmfile pipeline after Stage 2 (`2-resources`) provisions Zonal databases and VMs via `charts/gdc-dbs` and `charts/gdc-vm`.
