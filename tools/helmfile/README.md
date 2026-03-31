# GDCag Infrastructure Automation (Helmfile)

This repository manages the deployment of **Google Distributed Cloud air-gapped  (GDCag)** resources using [Helmfile](https://github.com/helmfile/helmfile). 

It utilizes a **data-driven approach**:
1.  **`tenants.yaml`**: Defines the desired state (Tenants, Projects, IAM, VMs, Buckets, Databases).
2.  **`helmfile.yaml`**: The logic engine that dynamically generates Helm releases based on the data.
3.  **`charts/`**: Local Helm charts that template the GDCag Custom Resources.

---

## 🏗 Architecture

This setup orchestrates resources across two distinct Kubernetes contexts required by GDCag:

| Kubernetes Context | Resources Managed |
| :--- | :--- |
| **Global API Cluster** | `Project`, `IAMRoleBinding`, `ProjectServiceAccount` |
| **Org Admin Cluster** | `VirtualMachine`, `Bucket`, `DBCluster` (Postgres/Oracle/AlloyDB) |

![GDCag Helmfile Architecture Diagram](arch.png)

### State Management Strategy
* **Helm State (Secrets):** All Helm release secrets are stored in a centralized namespace called **`iac-root`**.
* **Resource Destination:** The actual resources are deployed into their respective Project Namespaces (e.g., `lambda-prj`, `snowflake-prj`).

### Dependency Chain
Helmfile enforces the following strict execution order to satisfy GDCH API requirements:
1.  **Project** (Creates the Namespace)
2.  **IAM Role Bindings** (Grants permissions to the IaC user & Tenant users)
3.  **Service Accounts** (Requires IAM permissions to be visible)
4.  **Workloads** (VMs, Buckets, DBs - deployed in parallel after the Project environment is ready)

---

## ✅ Prerequisites

### 0. Required Tools
* [Helm](https://helm.sh/docs/intro/install/) (v3.17.1+)
* [Helm diff](https://github.com/databus23/helm-diff) (v3.12.5+)
* [Helmfile](https://github.com/helmfile/helmfile) (v1.2.1+)
* `kubectl`

```bash
# install helm-diff
helm plugin install https://github.com/databus23/helm-diff --version v3.12.5

helm plugin list

# install helmfile
wget https://github.com/helmfile/helmfile/releases/download/v1.2.1/helmfile_1.2.1_linux_amd64.tar.gz
tar -zxvf helmfile_1.2.1_linux_amd64.tar.gz
mv helmfile /usr/local/bin/

echo 'source <(helmfile completion bash)' >> ~/.bashrc
source ~/.bashrc

helmfile version
```

### 2. Kubeconfig Contexts
The `helmfile.yaml.gotmpl` expects these specific context names:
* `global-api-gdch_console-org-1-zone1-google-gdch-test_global-api` - use for global resources deployment like projects, projectserviceaccounts.
* `org-1-admin-zone1-gdch_console-org-1-zone1-google-gdch-test_org-1-admin` - use for project specific or zonal resource deployment like VMs, buckets and DBs.

> **Tip:** To see your available cluster contexts:  `kubectl config get-contexts`

### 3. RBAC Bootstrapping (First Run Only)
The user running Helmfile (e.g., `fop-iac`) requires **Secret-Admin** and **IAM-Project-Admin** privileges on **iac-root** project to manage Helm state file.

Run these commands once to bootstrap permissions:

Firstly, make sure `fop-platform-admin@example.com` user has the roles `IAM Org Admin`, `Organization Grafana Viewer`, `Project Creator` assigned.

```bash
# Export environment variables 
export ORG_NAME="org-1"
export IAC_PROJECT="iac-root"
export IAC_USER="fop-iac@example.com"


### Create a project to host IaC resources
gdcloud auth login (as platform-admin)
gdcloud projects create $IAC_PROJECT

### Grant IAC_USER required Org roles:
for role in \
  organization-iam-admin \
  project-creator \
  project-editor \
  user-cluster-admin \
; do \
   gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
   --member="user:$IAC_USER" \
   --role="$role";\
done

### Grant IAC_USER required IAM permissions on `IAC_PROJECT` :
for role in \
  secret-admin \
; do \
  gdcloud projects add-iam-policy-binding $IAC_PROJECT \
  --member=user:$IAC_USER \
  --role=$role;\
done
```

### 4. Deploying GDCag Resources `VirtualMachine`, `Bucket`, `DBCluster`

0. gdcloud auth login (as fop-iac@example.com)

`gdcloud auth login --login-config-cert=/tmp/org-1-web-tls-ca.cert`

1. Prechecks Helm Chart
```bash
cd tools/helmfile
helmfile lint
helmfile list
helmfile show-dag
```


2. Helmfile diff to show resources to deploy

```bash
helmfile diff
```

Note: This is likely to fail because of the "Chicken and Egg" problem.  `helmfile diff` or even `helmfile apply` attempts to calculate diffs for all groups before it applies anything.
However, this is a fresh install and the namespaces (e.g lambda-prj, snowflake-prj) do not exist yet.

2. Use `helmfile sync` for ``first run``.

Note: `helmfile sync` does not try to read the state first. It will simply execute the Directed Acyclic Graph (DAG) in order ensuring the resources are deployed based on the order and dependency defined using the `needs` keyword.

4. Use `helmfile apply` for subsequent resources deployment once project and rolebindings exists.

```bash
helmfile apply
```
