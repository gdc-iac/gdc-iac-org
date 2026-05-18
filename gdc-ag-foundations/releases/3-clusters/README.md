# Stage 3: Clusters (`3-clusters`)

This stage provisions dedicated Kubernetes standard clusters inside GDC Hosted for deploying highly available, containerized tenant workloads.

---

## Operational Architecture

* **Target Control Plane Scope**: Zonal API Server (`gdc_context_zone`)
* **Target Namespace**: Dynamic: `platform` (for Standard Clusters) or specific tenant project namespaces (for User Clusters).
* **Pre-requisites**: Stage `1-project-factory` must be fully executed (tenant project contexts must exist).

---

## Deployments & Sub-Helmfiles

* **`clusters.yaml.gotmpl`**: Configures and deploys GDC Hosted clusters and registers matched project bindings.
  * **Chart**: `gdc-clusters` (local path: `charts/gdc-clusters`)
  * **Features Supported**:
    * **Standard Clusters**: Automatically provisioned inside the system administrative namespace (`platform`).
    * **User Clusters**: Provisioned dynamically inside designated tenant project namespaces (e.g., `namespace: mellons-prj`).
    * **Custom Load Balancing**: Support for custom IP allocation sizes via `loadBalancer` / `ingressServiceIPSize`.
    * **Automated Project Bindings**: Automatically constructs corresponding `ProjectBinding` resources inside the target namespace to grant tenant user projects administrative cluster access.

---

## Execution Commands

Run the following commands from the repository root directory:

```bash
# Template validation
helmfile -e dev -l stage=3-clusters template

# Apply/Deploy stage
helmfile -e dev -l stage=3-clusters apply
```
