# GDC Database Services Helm Chart (`gdc-dbs`)

This Helm chart deploys and manages Database Services on Google Distributed Cloud air-gapped (`GDCag`) Zonal Management API servers (`ZONE_KUBECONFIG`). It supports provisioning:

*   **PostgreSQL `DBCluster` & `BackupPlan`** (`postgresql.dbadmin.gdc.goog/v1`, PostgreSQL `15` on AlloyDB Omni runtime)
*   **Oracle `DBCluster` *(Deprecated on GDCag)*** (`oracle.dbadmin.gdc.goog/v1`, retained solely for legacy backward compatibility)

## Prerequisites

1.  **Helm:** Helm version 3.x is installed.
2.  **Kubectl:** `kubectl` is configured against your GDCag Zonal Management API server (for example, `org-1-admin-zone1`).
3.  **Permissions & Backup Repository:** Bind `IAMRole` `project-db-admin` (`iam.global.gdc.goog/v1`) and `secret-admin` in the target project namespace, and verify the cluster-scoped `BackupRepository` name via `kubectl get backuprepositories.backup.gdc.goog` on the Zonal Management API server before creating `DBCluster` or `BackupPlan` resources.
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

3. Install a Zonal HA PostgreSQL 15 `DBCluster` and Automated `BackupPlan`:

> [!NOTE]
> **Admission Ordering (`vbackupplan.postgresql.dbadmin.gdc.goog`):** On GDCag, an unpaused `BackupPlan` (`paused: false`) requires its target `DBCluster` to exist at admission time. Argo CD GitOps deploys both in a single sync via `argocd.argoproj.io/sync-wave: "1"`. When installing directly with the `helm` CLI (which sorts Custom Resources alphabetically and sends `BackupPlan` before `DBCluster`), either apply `DBCluster` first and enable `backupPlan` on `helm upgrade`, or pass `--set postgresql.backupPlan.paused=true` on initial install and unpause after creation. If your organization's `BackupRepository` is not named `dbs-backup-repository`, pass `--set postgresql.backupPlan.backupRepository=<repo-name>` to avoid `DBSE0062`.

```bash
# Step 3a: Provision Secret and PostgreSQL 15 DBCluster
helm upgrade --install my-pg-release . \
  --namespace my-db-project \
  --set namespace=my-db-project \
  --set base64EncodedPassword="${B64_PASSWORD}" \
  --set postgresql.enabled=true \
  --set postgresql.clusterName=prod-pg \
  --set-string postgresql.parameters.max_connections=200

# Step 3b: Enable automated BackupPlan once DBCluster exists
helm upgrade --install my-pg-release . \
  --namespace my-db-project \
  --reuse-values \
  --set postgresql.backupPlan.enabled=true \
  --set postgresql.backupPlan.backupRepository=org-1-backup-repository
```

4. *(Deprecated on GDCag)* Install a Legacy Oracle `DBCluster`:

> [!WARNING]
> **Deprecation Notice:** Oracle Database Service (`oracle.dbadmin.gdc.goog/v1`) is deprecated on GDC air-gapped (`GDCag`). The `oracle.*` values and template remain solely for backward compatibility; use Managed PostgreSQL 15 (`postgresql.*`) for all new deployments.

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
| `postgresql.secretName` | Optional custom `passwordRef.name` Secret (defaults to `db-pw-<clusterName>`, which is required by the GDCag `vdbcluster` admission webhook). | `""` |
| `postgresql.version` | PostgreSQL major version (`"15"` supported on GDCag). | `"15"` |
| `postgresql.cpu` | Primary instance vCPU allocation (`>= 2` required on GDCag). | `2` |
| `postgresql.memory` | Primary instance memory allocation (`>= 8Gi` required on GDCag). | `8Gi` |
| `postgresql.dataDiskSize` | Primary `DataDisk` size. | `50Gi` |
| `postgresql.availability.enableHighAvailability` | Deploy a same-zone RaaS HA standby replica (`GDCag v1.16.2+`, `dbcluster.dbadmin.goog/raasEnabled: "true"`). HA is PostgreSQL-only (unsupported on Oracle) and opt-in at the GDCag API (`false` / `zonal` by default); this chart enables it by default. | `true` |
| `postgresql.availability.enableAutoFailover` | Enable automatic failover for unplanned primary failures on `GDCag v1.16.2+` (active only when `enableHighAvailability: true`). Triggers after 3 consecutive 30s health-check failures (`~90s` detection latency; typically `~2+ minutes` total end-to-end RTO as the standby is promoted and traffic reroutes). Planned maintenance and manual switchovers (`gdcloud database clusters failover` / `fleet.dbadmin.gdc.goog/v1` `Failover`) are separate, active client connections drop in all cases, and legacy pre-`v1.15.1` HA clusters must disable HA, wait for `HAReady` to clear, and re-enable HA to migrate to RaaS. See [Configure high availability](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/application/ao-user/db-configure-ha#about-high-availability). | `true` |
| `postgresql.isDeleted` | Mark `spec.isDeleted: true` prior to deleting or uninstalling a PostgreSQL `DBCluster` (`vdbcluster` deletion protection). | `false` |
| `postgresql.parameters` | Optional key-value PostgreSQL engine parameters (`spec.primarySpec.parameters`, for example `max_connections: "200"`). | `{}` |
| `postgresql.backupPlan.enabled` | Deploy a `postgresql.dbadmin.gdc.goog/v1` `BackupPlan` targeting `clusterName`. | `false` |
| `postgresql.backupPlan.name` | Custom `BackupPlan` resource name (defaults to `<clusterName>-backup-plan`). | `""` |
| `postgresql.backupPlan.backupRepository` | Optional `BackupRepository` name injected as `metadata.annotations["fleet.dbadmin.goog/backup-repository"]` (required when the cluster repository is not named `dbs-backup-repository`). | `""` |
| `postgresql.backupPlan.annotations` | Optional extra annotations merged onto `BackupPlan` (`argocd.argoproj.io/sync-wave: "1"` is set by default). | `{}` |
| `postgresql.backupPlan.backupRetainDays` | Automated backup retention window in days (`1` to `90`). | `14` |
| `postgresql.backupPlan.paused` | Pause scheduled backup execution. | `false` |
| `postgresql.backupPlan.PITREnabled` | Enable log replication for Point-in-Time Recovery (`PITR`). | `false` |
| `postgresqlClusters` | Optional list of additional PostgreSQL `DBCluster` objects (each supporting all `postgresql.*` fields) to provision multiple clusters in one project release. | `[]` |
| `oracle.enabled` | *(Deprecated on GDCag)* Deploy an Oracle `DBCluster` (`oracle.dbadmin.gdc.goog/v1`). | `false` |
| `oracle.clusterName` | *(Deprecated)* Name of the Oracle `DBCluster` resource. | `my-ora-cluster` |
| `oracle.createSecret` | *(Deprecated)* Render `Secret/db-pw-<clusterName>`. | `true` |
| `oracle.base64EncodedPassword` | *(Deprecated)* Base64-encoded password for the Oracle admin user (overrides top-level `base64EncodedPassword`). | `""` |
| `oracle.version` | *(Deprecated)* Oracle version (for example, `"19"`). | `"19"` |
| `oracle.cpu` | *(Deprecated)* CPU allocation for the primary instance. | `2` |
| `oracle.memory` | *(Deprecated)* Memory allocation for the primary instance. | `8Gi` |
| `oracle.dataDiskSize` | *(Deprecated)* Size of `DataDisk`. | `20Gi` |
| `oracle.logDiskSize` | *(Deprecated)* Size of `LogDisk`. | `20Gi` |
| `oracle.cdbName` | *(Deprecated)* Oracle Container Database (`CDB`) name. | `MYORACDB` |

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

Monitor `DBCluster` and `BackupPlan` readiness on the Zonal Management API server (note that GDCag `DBCluster` readiness is reported via `.status.phase=DBClusterReady` rather than a `Ready` status condition):

```bash
kubectl get dbcluster.postgresql.dbadmin.gdc.goog,backupplan.postgresql.dbadmin.gdc.goog -n <namespace>
kubectl wait --for=jsonpath='{.status.phase}'=DBClusterReady dbcluster.postgresql.dbadmin.gdc.goog/<clusterName> -n <namespace> --timeout=20m
kubectl get dbcluster.oracle.dbadmin.gdc.goog -n <namespace> <oracle.clusterName> -w
```

Once `.status.phase` reaches `DBClusterReady`, retrieve the database endpoint (`{.status.primary.url}`, stripping `:5432` when an application expects a bare hostname) and extract the server TLS CA certificate (`dbs-pg-cert-<clusterName>`) from `Secret/dbs-certificates` in the project namespace.

## Uninstallation

GDCag enforces deletion protection on PostgreSQL `DBCluster` resources (`vdbcluster.postgresql.dbadmin.gdc.goog` denies `DELETE` while `spec.isDeleted` is `false`). Set `isDeleted=true` first, then uninstall the Helm release:

```bash
helm upgrade <release-name> . --namespace <namespace> --reuse-values --set postgresql.isDeleted=true
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
