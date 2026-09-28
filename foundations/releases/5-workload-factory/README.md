# Stage 5: Workload Factory (`5-workload-factory`)

This stage deploys User Cluster application workloads for GDC Blueprint Patterns (`blueprints/patterns/*/chart`) after foundational projects (`1-project-factory`), Zonal managed databases/VMs/buckets (`2-resources`), and Kubernetes clusters (`3-clusters`) have been provisioned.

## Separation of Planes
- **Zonal Managed Infrastructure (`Stage 2: 2-resources`)**: Databases (`DBCluster`), Virtual Machines (`VirtualMachine`), and Object Storage (`Bucket`) required by a pattern are provisioned on the Zonal Management API (`kube_context_zonal`) via the core `charts/gdc-dbs`, `charts/gdc-vm`, and `charts/gdc-buckets` charts (`gdc.enabled: false` in Stage 5).
- **User Cluster Workloads (`Stage 5: 5-workload-factory`)**: Kubernetes `Deployment`, `StatefulSet`, `Service`, `Gateway`, `HTTPRoute`, `CronJob`, and `NetworkPolicy` resources are deployed to the target User/Standard Cluster (`kube_context_cluster`) with `apps.enabled: true`.

## Usage
```bash
# Template all Stage 5 pattern releases in dev environment
helmfile -e dev -l stage=5-workload-factory template

# Apply Stage 5 pattern releases
helmfile -e dev -l stage=5-workload-factory apply
```
