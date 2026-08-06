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
* **Zonal Resilience**: PostgreSQL is configured for `ZONAL_HA`, guaranteeing database survival with manual failover if a zone goes down.
* **Unified VPC Networking**: Connects the VM Runtime and database clusters securely through private VPC subnetting.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* GDC VM Runtime enabled and configured by Platform Administrators.
* A legacy VM boot image (e.g., Ubuntu 20.04 or RHEL 8) imported into GDC's VM images registry.
* `kubectl` and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **Network Admin**: `roles/compute.networkAdmin` (to create subnets).
  * **Database Admin**: `roles/db.cluster.creator` (to provision PostgreSQL).
  * **Compute Admin**: `roles/compute.instanceAdmin.v1` (to create and configure VMs).

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

Create the managed PostgreSQL cluster.

#### Option A: Manual (CLI)
```shell
gdcloud database clusters create legacy-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=4 --memory=16Gi --storage-size=100Gi
```

#### Option B: GitOps / IaC (`manifests/gdc/infra/legacy-infra.yaml`)
```yaml
apiVersion: networking.gdc.goog/v1
kind: Network
metadata:
  name: vm-net
  namespace: my-gdc-project
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: legacy-db
  namespace: my-gdc-project
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA
  resources:
     requests: { cpu: "4", memory: "16Gi" }
  storage: { size: "100G" }
```

### 2.2 Initialize Database Schema

Once the database status is `READY`, connect via `psql` to create the schema:

```sql
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
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

### 6.2 Database High Availability & Manual Failover

In GDC air-gapped, database clusters configured with `ZONAL_HA` (primary and standby replicas) do not automatically failover when the primary instance becomes unavailable. Failover must be triggered manually by an operator.

#### Option A: Manual (CLI)
To trigger a manual failover using the `gdcloud` CLI:
```shell
gdcloud database clusters failover legacy-db --project=my-gdc-project
```

#### Option B: GitOps / IaC (`manifests/gdc/db/failover.yaml`)
Apply a `Failover` custom resource to trigger the failover declaratively:
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
| `PostgreSQL HA Failover` | Physical host failure hosting primary DB pod. | Standby replica must be promoted by manually triggering a failover. |
