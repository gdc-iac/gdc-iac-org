# Stage 4: Notebooks (`4-notebooks`)

This stage provisions containerized Jupyter Workbench Notebook workspaces inside user clusters to enable interactive development and AI/ML modeling workloads.

---

## Operational Architecture

* **Target Control Plane Scope**: Zonal API Server (`gdc_context_zone`)
* **Target Namespace**: Project namespaces (e.g. `mellon-prj`)
* **Pre-requisites**: Stage `3-clusters` must be fully executed (the targeted user cluster must be operational).

---

## Deployments & Sub-Helmfiles

* **`notebooks.yaml.gotmpl`**: Provisions interactive Jupyter notebooks and associated Persistent Volume Claims inside project namespaces.
  * **Chart**: `gdc-notebooks`

---

## Execution Commands

Run the following commands from the repository root directory:

```bash
# Template validation
helmfile -e dev -l stage=4-notebooks template

# Apply/Deploy stage
helmfile -e dev -l stage=4-notebooks apply
```
