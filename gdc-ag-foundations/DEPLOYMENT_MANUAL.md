# GDC Foundations: Step-by-Step IaC Deployment Manual

This operational playbook guides GDC Hosted administrators through manual execution, state verification, and rollback procedures for all 5 foundational stages.

---

## Pre-Flight Checklist
Before running any manual deployment commands:
1. Verify your local workstation is prepared as detailed in `WORKSTATION_ONBOARDING.md`.
2. Execute the validation script to ensure there are no syntax or schema violations:
   ```bash
   ./scripts/validate.sh dev
   ```
3. Ensure all required container images and Helm charts are mirrored to local registries as detailed in `AIRGAP_MIRRORING.md`.

---

## Stage Execution Runbook

```mermaid
graph TD
    S0[Stage 0-org-setup: Org Policies] --> S1[Stage 1-project-factory: Create Projects]
    S1 --> S2[Stage 2-resources: DBs, VMs, Storage]
    S2 --> S3[Stage 3-clusters: Compute Provisioning]
    S3 --> S4[Stage 4-notebooks: Workbench Setup]
```

---

### 🏁 Stage 0: Bootstrap & Organization Setup

Provisions root platform settings, billing configurations, organizational policies, and baseline operator role bindings.

```bash
# 1. Perform dry-run diff validation
helmfile -e dev -l stage=0-bootstrap diff
helmfile -e dev -l stage=0-org-setup diff

# 2. Apply the stage releases
helmfile -e dev -l stage=0-bootstrap apply
helmfile -e dev -l stage=0-org-setup apply
```

* **Verification**:
  * Verify that the target administrative namespace exists: `kubectl get ns iac-root`
  * Verify root OrgPolicy resources are active: `kubectl get orgpolicies -n platform`
* **Rollback Plan**:
  * Revert change and rollback using helmfile: `helmfile -e dev -l stage=0-org-setup rollback`

---

### 🏗️ Stage 1: Project Factory

Dynamically provisions target GDC Hosted tenant namespaces, maps project-level custom roles, establishes project service accounts, and applies cross-project networking isolation policies.

```bash
# 1. Perform dry-run diff validation
helmfile -e dev -l stage=1-project-factory diff

# 2. Apply the stage releases
helmfile -e dev -l stage=1-project-factory apply
```

* **Verification**:
  * Verify that tenant namespaces are active: `kubectl get projects -n platform` (checks custom resources) and `kubectl get ns` (checks physical namespaces).
  * Verify that service accounts are provisioned: `kubectl get sa -n mellons-prj`
* **Rollback Plan**:
  * In case of failures, execute: `helmfile -e dev -l stage=1-project-factory rollback`

---

### 💾 Stage 2: Zonal Application Resources

Deploys foundational customer services inside tenant projects: databases, virtual machine templates, storage buckets, and custom dashboards.

```bash
# 1. Perform dry-run diff validation
helmfile -e dev -l stage=2-resources diff

# 2. Apply the stage releases
helmfile -e dev -l stage=2-resources apply
```

* **Verification**:
  * Verify that object storage buckets are active: `kubectl get buckets -n mellons-prj`
  * Verify virtual machine instances: `kubectl get virtualmachines -n mellons-prj`
* **Rollback Plan**:
  * Execute rollback command: `helmfile -e dev -l stage=2-resources rollback`

---

### 🖥️ Stage 3: Compute Clusters (Standard & User Clusters)

Provisions dedicated Kubernetes workloads compute pools (Standard and User clusters) and configures ProjectBindings.

```bash
# 1. Perform dry-run diff validation
helmfile -e dev -l stage=3-clusters diff

# 2. Apply the stage releases
helmfile -e dev -l stage=3-clusters apply
```

* **Verification**:
  * Verify physical cluster creation progress: `kubectl get clusters -n platform`
  * Verify user project access bindings: `kubectl get projectbindings -n platform`
* **Rollback Plan**:
  * Execute rollback command: `helmfile -e dev -l stage=3-clusters rollback`

---

### 🧠 Stage 4: Jupyter Notebook Workbenches

Configures dedicated AI/ML workbench notebooks mapping GPUs, service accounts, environment variables, and custom dataset storage volumes inside tenant user namespaces.

```bash
# 1. Perform dry-run diff validation
helmfile -e dev -l stage=4-notebooks diff

# 2. Apply the stage releases
helmfile -e dev -l stage=4-notebooks apply
```

* **Verification**:
  * Verify that Notebook workbench custom resources exist: `kubectl get notebooks -n mellons-prj`
  * Verify that the workbench server pods are successfully scheduled and active.
* **Rollback Plan**:
  * Execute rollback command: `helmfile -e dev -l stage=4-notebooks rollback`

---

## Pipeline Rollback Strategy

If an entire pipeline run encounters errors and you must restore the environment to a previously known stable revision:
```bash
# Rollback all stages sequentially in reverse order
helmfile -e dev -l stage=4-notebooks rollback
helmfile -e dev -l stage=3-clusters rollback
helmfile -e dev -l stage=2-resources rollback
helmfile -e dev -l stage=1-project-factory rollback
helmfile -e dev -l stage=0-org-setup rollback
```
