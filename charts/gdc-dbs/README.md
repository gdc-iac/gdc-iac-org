# GDC Database Services Helm Chart (`gdc-dbs`)

This Helm chart deploys and manages Database Services on Google Distributed Cloud air-gapped (`GDCag`) Zonal Management API servers (`ZONE_KUBECONFIG`). It supports provisioning:

*   **PostgreSQL `DBCluster` & `BackupPlan`** (`postgresql.dbadmin.gdc.goog/v1`, PostgreSQL `15` on AlloyDB Omni runtime)
*   **Oracle `DBCluster`** (`oracle.dbadmin.gdc.goog/v1`)

## Prerequisites

1.  **Helm:** Helm version 3.x is installed.
2.  **Kubectl:** `kubectl` is configured against your GDCag Zonal Management API server (for example, `org-1-admin-zone1`).
3.  **Permissions:** Bind `IAMRole` `project-db-admin` and `secret-admin` in the target project namespace, and ensure `BackupRepository/dbs-backup-repository` exists on the Zonal Management API server before creating `DBCluster` or `BackupPlan` resources.
4.  **Project Namespace:** A project namespace must exist in your GDCag organization where the database will be deployed.

## Usage / Installation

1. Navigate to the chart directory:

```bash
cd charts/gdc-dbs
```

2. Generate Base64 Password:

```bash
export B64_PASSWORD=$(echo -n 'YourSecureP@ssw0rd' | base64 -w0)
```

3. Install a Zonal HA PostgreSQL 15 `DBCluster` with an Automated `BackupPlan`:

```bash
helm upgrade --install my-pg-release . \
  --namespace my-db-project \
  --set namespace=my-db-project \
  --set base64EncodedPassword="${B64_PASSWORD}" \
  --set postgresql.enabled=true \
  --set postgresql.clusterName=prod-pg \
  --set postgresql.backupPlan.enabled=true
```

4. Install an Oracle `DBCluster`:

```bash
helm upgrade --install my-ora-release . \
  --namespace my-db-project \
  --set namespace=my-db-project \
  --set base64EncodedPassword="${B64_PASSWORD}" \
  --set oracle.enabled=true \
  --set oracle.clusterName=prod-ora \
  --set oracle.cdbName=PRODORACDB \
  --set oracle.memory=16Gi
```

## Configuration Parameters

The chart is configured through `values.yaml` or `--set` / `-f` flags during `helm install` or `helm upgrade`.

| Parameter | Description | Default |
| :--- | :--- | :--- |
| `namespace` | Target GDC project namespace on the Zone Management API server. | `my-db-project` |
| `base64EncodedPassword` | Fallback Base64-encoded password for `dbsadmin` (used when engine-specific `base64EncodedPassword` is empty). | `""` |
| `postgresql.enabled` | Deploy a PostgreSQL `DBCluster` (`postgresql.dbadmin.gdc.goog/v1`). | `false` |
| `postgresql.clusterName` | Name of the PostgreSQL `DBCluster` resource. | `my-pg-cluster` |
| `postgresql.createSecret` | Render `Secret/db-pw-<clusterName>` (`false` when pre-created via SOPS or External Secrets). | `true` |
| `postgresql.base64EncodedPassword` | Base64-encoded password for `dbsadmin` (overrides top-level `base64EncodedPassword`). | `""` |
| `postgresql.secretName` | Optional custom `passwordRef.name` Secret (defaults to `db-pw-<clusterName>`). | `""` |
| `postgresql.version` | PostgreSQL major version (`"15"` supported on GDCag). | `"15"` |
| `postgresql.cpu` | Primary instance vCPU allocation (`>= 2` required on GDCag). | `2` |
| `postgresql.memory` | Primary instance memory allocation (`>= 8Gi` required on GDCag). | `8Gi` |
| `postgresql.dataDiskSize` | Primary `DataDisk` size. | `50Gi` |
| `postgresql.availability.enableHighAvailability` | Deploy Zonal HA standby replica. | `true` |
| `postgresql.availability.enableAutoFailover` | Enable automatic failover (`GDCag v1.15.1+`). | `true` |
| `postgresql.databaseFlags` | Optional key-value PostgreSQL runtime flags (`spec.primarySpec.databaseFlags`). | `{}` |
| `postgresql.backupPlan.enabled` | Deploy a `postgresql.dbadmin.gdc.goog/v1` `BackupPlan` targeting `clusterName`. | `false` |
| `postgresql.backupPlan.name` | Custom `BackupPlan` resource name (defaults to `<clusterName>-backup-plan`). | `""` |
| `postgresql.backupPlan.backupRetainDays` | Automated backup retention window in days (`1` to `90`). | `14` |
| `postgresql.backupPlan.paused` | Pause scheduled backup execution. | `false` |
| `postgresql.backupPlan.PITREnabled` | Enable log replication for Point-in-Time Recovery (`PITR`). | `false` |
| `postgresqlClusters` | Optional list of additional PostgreSQL `DBCluster` objects (each supporting all `postgresql.*` fields) to provision multiple clusters in one project release. | `[]` |
| `oracle.enabled` | Deploy an Oracle `DBCluster` (`oracle.dbadmin.gdc.goog/v1`). | `false` |
| `oracle.clusterName` | Name of the Oracle `DBCluster` resource. | `my-ora-cluster` |
| `oracle.createSecret` | Render `Secret/db-pw-<clusterName>`. | `true` |
| `oracle.base64EncodedPassword` | Base64-encoded password for the Oracle admin user (overrides top-level `base64EncodedPassword`). | `""` |
| `oracle.version` | Oracle version (for example, `"19"`). | `"19"` |
| `oracle.cpu` | CPU allocation for the primary instance. | `2` |
| `oracle.memory` | Memory allocation for the primary instance. | `8Gi` |
| `oracle.dataDiskSize` | Size of `DataDisk`. | `20Gi` |
| `oracle.logDiskSize` | Size of `LogDisk`. | `20Gi` |
| `oracle.cdbName` | Oracle Container Database (`CDB`) name. | `MYORACDB` |

### Password Management

Never commit plaintext passwords to `values.yaml`. Supply `base64EncodedPassword` via SOPS-encrypted environment files (`foundations/sops_implementation_plan.md`) or `--set` at deployment time:

```bash
echo -n 'YourSecureP@ssw0rd' | base64 -w0
```

### Multi-Cluster Example (`postgresqlClusters`)

To provision multiple PostgreSQL `DBCluster`s inside a single GDC project release (for example, `gitlab-db` and `vault-db` in `iac-root`):

```yaml
namespace: iac-root
postgresqlClusters:
  - clusterName: gitlab-db
    createSecret: false # Pre-created via SOPS / kubectl
    cpu: 4
    memory: 16Gi
    dataDiskSize: 50Gi
    backupPlan:
      enabled: true
      backupRetainDays: 14
  - clusterName: vault-db
    createSecret: false
    cpu: 2
    memory: 8Gi
    dataDiskSize: 50Gi
    backupPlan:
      enabled: true
      backupRetainDays: 30
```

## Checking Deployment Status

Monitor `DBCluster` and `BackupPlan` readiness on the Zonal Management API server:

```bash
kubectl get dbcluster.postgresql.dbadmin.gdc.goog,backupplan.postgresql.dbadmin.gdc.goog -n <namespace>
kubectl get dbcluster.oracle.dbadmin.gdc.goog -n <namespace> <oracle.clusterName> -w
```

Once `Ready`, retrieve the database endpoint (`{.status.primary.url}`, stripping `:5432` when an application expects a bare hostname) and extract the server TLS CA certificate (`dbs-pg-cert-<clusterName>`) from `Secret/dbs-certificates` in the project namespace.

## Uninstallation

```bash
helm uninstall <release-name> --namespace <namespace>
```

## CI/CD Pre-Deployment Testing

Tests are executed via `./scripts/test-charts.sh` from the repository root:

1.  **Input/Schema Validation (`helm lint`):** Validates `values.yaml` against `values.schema.json`.
2.  **Logic Validation (`helm-unittest`):** Executes `tests/dbs_test.yaml` across PostgreSQL, `BackupPlan`, `createSecret`, `postgresqlClusters`, and Oracle configurations.
3.  **Structural Validation (`kubeconform`):** Verifies Kubernetes OpenAPI specifications (`DBCluster` and `BackupPlan` CRDs are skipped in offline mode unless GDC CRD schemas are supplied).
4.  **Security Policy Validation (`conftest` / OPA):** Evaluates any configured Rego policies.

```bash
./scripts/test-charts.sh
```
