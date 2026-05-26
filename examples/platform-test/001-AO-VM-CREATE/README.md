# 001-AO-VM-CREATE: Virtual Machine Provisioning (IaC Setup)

This directory contains a self-contained, DRY-compliant IaC (Infrastructure as Code) setup to satisfy the requirements of Virtual Machine provisioning on Google Distributed Cloud (GDC).

## Test Case Overview
* **Goal:** Automate the provisioning of an Ubuntu-based VirtualMachine workload and an ingress project network policy inside the `ioc-test-project-001` namespace on an attached User Cluster.
* **Features covered:** Logical Project creation, dynamic VM-admin role bindings (`project-vm-admin`, `project-networkpolicy-admin`), regional SSH key management, and hypervisor-level scheduling.

> [!NOTE]
> **GDC Platform Architecture & Security Manual:**
> For details concerning GDC's split-plane cluster topology, Service Account least-privilege scopes, OIDC/AIS identity propagation loops, and permanent system role bindings, refer to the **[GDC Staging Platform setup README](../000-SETUP/README.md)**.

---

## Directory Structure & Assets
* **`tenants.yaml`**: Defines the desired state including the project, user cluster bindings, roles, VM size, image, SSH keys, and network ingress bindings.
* **`helmfile.yaml.gotmpl`**: Unified orchestrator driving multi-stage topological deployments across cluster control planes.
* **`setup-adhoc-env.sh`**: Interactive OIDC developer sandbox wrapper.
* **`setup-operator-sa.sh`**: Headless operator workflow wrapper.
* **`setup-customer-sa.sh`**: Headless customer-scoped pipeline workflow wrapper.

---

## Deployment Execution

### Method 1: OIDC Interactive (Developer Sandbox)
Use this flow to deploy manually from a workstation using OIDC credentials:
```bash
# 1. Bootstrap permissions, project namespace setup, and VM roles
VERSION=-v1 ./setup-adhoc-env.sh

# 2. Export the context of your user cluster (or auto-discover it)
export USER_CLUSTER_CONTEXT=$(kubectl config get-contexts -o name | grep "^user-vm-" | head -n 1)

# 3. Synchronize the IaC assets
VERSION=-v1 helmfile sync
```

### Method 2: Scoped Service Accounts (Headless Pipelines)
Use these flows to run automated pipelines in headless execution environments:

#### A. Operator-Scoped Run
```bash
./setup-operator-sa.sh
KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=vm sync
KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=vm sync
```

#### B. Customer-Scoped Run

1. **Generate Service Account Credentials:**
   ```bash
   ./setup-customer-sa.sh
   ```

   > [!WARNING]
   > **Logical to Physical Propagation Latency:**
   > GDC's background identity propagation engines require around **15 to 20 seconds** to replicate logical namespace and GDC-native IAM role permissions from the Global API down to regional clusters. Running Step 2 immediately will result in authorization failures.

   * **Query/Verify Role Propagation Status:**
     Before proceeding, confirm that the restricted runner SA permissions are fully synchronized:
     ```bash
     kubectl --kubeconfig=./.kubeconfig-sa --context=runner-context auth can-i get virtualmachines -n ioc-test-project-001-v1
     ```
     *Do not execute Step 2 until this check returns `yes`.*

2. **Deploy Project and VM Workloads:**
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile sync
   ```

---

## Verification & Validation

### 1. Validate Workload Status (CLI)
Confirm that the VM, virtual boot disks, and ingress network policy have been successfully provisioned:
```bash
# Automatically target the discovered User Cluster context
export USER_CLUSTER_CONTEXT=$(kubectl config get-contexts -o name | grep "^user-vm-" | head -n 1)

# Verify the VM status (should be Running)
kubectl get virtualmachine ioc-test-vm -n ioc-test-project-001-v1 --context $USER_CLUSTER_CONTEXT

# Verify the Boot Disk
kubectl get virtualmachinedisk ioc-test-vm-boot-disk -n ioc-test-project-001-v1 --context $USER_CLUSTER_CONTEXT

# Verify the Ingress Network Policy
kubectl get projectnetworkpolicy ioc-test-vm-ingress -n ioc-test-project-001-v1 --context $USER_CLUSTER_CONTEXT
```
*Expected Result: `ioc-test-vm` shows status `Running`, the boot disk is bound/active, and the network policy is applied.*

### 2. Validate Workload Status (GDC Console UI)
You can visually verify the running workloads inside the GDC Console UI:
* **GDC Console URL:** [https://console.org-1.zone1.google.gdch.test/#/virtualmachines?project=ioc-test-project-001-v1&zone=zone1](https://console.org-1.zone1.google.gdch.test/#/virtualmachines?project=ioc-test-project-001-v1&zone=zone1)

> [!IMPORTANT]
> **Tenant Security & Isolation Boundary:**
> * **Authorized Tenant User:** You must be signed into the console as the **IAC Tenant User (`iac@example.com`)** to view these VM workloads.
> * **Cluster/Platform Admin Forbidden:** If you are logged in as the **Platform Admin (`cluster-admin@example.com`)**, accessing this URL or namespace will return `Forbidden`. Cluster administrators have zero workload visibility inside customer tenant namespaces by design.

### 3. SSH Connectivity Verification
Test that GDC dynamically provisions external access to your VM:
```bash
# Resolve VM external IP
INGRESS_IP=$(kubectl get virtualmachineexternalaccess ioc-test-vm -n ioc-test-project-001-v1 --context $USER_CLUSTER_CONTEXT -o jsonpath='{.status.ingressIP}')

# Test connectivity to SSH port (22)
nc -zv -w 5 $INGRESS_IP 22
```
*Expected Result: Netcat reports successful connection connection on port 22.*

---

## Teardown

### A. Teardown Tenant Deployments
```bash
KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile destroy
kubectl --context bootstrap-context delete -f ../000-SETUP/base-customer-identity.yaml
rm -f .kubeconfig-sa
```

### B. Teardown Operator Deployments
```bash
# Destroy VM workloads
KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=vm destroy

# Destroy logical project
KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=vm destroy

# Clean up operator and tenant roles
kubectl --context bootstrap-global-context delete -f ../000-SETUP/base-customer-identity.yaml
kubectl --context bootstrap-admin-context delete -f ../000-SETUP/base-operator-identity.yaml
rm -f .kubeconfig-sa
```
