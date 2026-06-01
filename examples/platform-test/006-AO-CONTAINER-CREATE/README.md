# 006-AO-CONTAINER-CREATE: Deploy Containerized Services (IaC Setup)

This directory contains a self-contained, DRY-compliant IaC (Infrastructure as Code) setup to satisfy the requirements of stateless containerized workload deployments on Google Distributed Cloud (GDC).

## Test Case Overview
* **Goal:** Automate the provisioning of an NGINX deployment and service in the `test-project-006` namespace on an attached User Cluster.
* **Features covered:** Logical Project creation, Dynamic namespace RBAC provisioning (`namespace-admin`), topological User Cluster bindings, and stateless workload scheduling.

---

## Directory Structure & Assets
* **`tenants.yaml`**: Defines the desired state including the project, user cluster bindings, namespace-scoped roles, and NGINX container workload parameters.
* **`helmfile.yaml.gotmpl`**: Unified orchestrator driving multi-stage topological deployments across cluster control planes.
* **`auth-extension.yaml`**: Empty configuration (all required roles are standard namespace admin profiles).
* **`setup-adhoc-env.sh`**: Interactive OIDC OIDC developer sandbox wrapper.
* **`setup-operator-sa.sh`**: Headless operator workflow wrapper.
* **`setup-customer-sa.sh`**: Headless customer-scoped pipeline workflow wrapper.

---

## Deployment Execution

### Method 1: OIDC Interactive (Developer Sandbox)
Use this flow to deploy manually from a workstation using OIDC credentials:
```bash
# 1. Bootstrap permissions, project namespace setup, and extension roles
./setup-adhoc-env.sh

# 2. Export the context of your user cluster
export USER_CLUSTER_CONTEXT="my-user-cluster-context"

# 3. Synchronize the IaC assets
helmfile sync
```

### Method 2: Scoped Service Accounts (Headless Pipelines)
Use these flows to run automated pipelines in headless execution environments:

```bash
# A. Operator-Scoped Run
./setup-operator-sa.sh
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-admin-context USER_CLUSTER_CONTEXT=my-user-cluster-context helmfile sync

# B. Customer-Scoped Run
./setup-customer-sa.sh
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-admin-context USER_CLUSTER_CONTEXT=my-user-cluster-context helmfile sync
```

---

## Verification & Validation

### 1. Validate Workload Status (CLI)
Confirm that the deployment and service have been created and pods are running on the User Cluster:
```bash
# Automatically target the discovered User Cluster context
export USER_CLUSTER_CONTEXT=$(kubectl config get-contexts -o name | grep "^user-vm-" | head -n 1)

kubectl get deployments,pods,svc -n test-project-006-v1 --context $USER_CLUSTER_CONTEXT
```
*Expected Result: `nginx-deployment` shows `1/1` ready, and the NGINX pod status is `Running`.*

### 2. Validate Workload Status (GDC Console UI)
You can visually verify the running workloads inside the GDC Console UI:
* **GDC Console URL:** [https://console.org-1.zone1.google.gdch.test/#/workloads?project=test-project-006-v1&zone=zone1](https://console.org-1.zone1.google.gdch.test/#/workloads?project=test-project-006-v1&zone=zone1)

> [!IMPORTANT]
> **Tenant Security & Isolation Boundary:**
> * **Authorized Tenant User:** You must be signed into the console as the **IAC Tenant User (`iac@example.com`)** to view these resources.
> * **Cluster/Platform Admin Forbidden:** If you are logged in as the **Platform Admin (`cluster-admin@example.com`)**, accessing this URL or namespace will return `Forbidden`. Cluster administrators have zero workload visibility inside customer tenant namespaces by design.

### 3. Dynamic Orchestration & Scaling Check
Verify that GDC dynamically scales the container replicas:
```bash
# Scale the deployment
kubectl scale deployment nginx-deployment --replicas=3 -n test-project-006-v1 --context $USER_CLUSTER_CONTEXT

# Verify scaling
kubectl get pods -l app=nginx-deployment -n test-project-006-v1 --context $USER_CLUSTER_CONTEXT
```
*Expected Result: Three active NGINX pods are scheduled and running successfully.*

---

## Teardown
To remove all provisioned resources:
```bash
USER_CLUSTER_CONTEXT=$USER_CLUSTER_CONTEXT helmfile destroy
```
