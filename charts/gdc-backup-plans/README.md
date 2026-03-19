# gdc-backup-plans

A Helm chart for creating `BackupPlan` Custom Resources on Google Distributed Cloud Hosted (GDCH).

## Overview

This chart simplifies the scheduling and deployment of backup plans for your GDCH clusters and applications. It supports four different types of backups, each mapping to an array in `values.yaml`:

- `application`: For application-level `BackupPlan`s
- `cluster`: For `ClusterBackupPlan`s
- `harbor`: For `HarborInstanceBackupPlan`s 
- `vm`: For Virtual Machine backups (renders both `VirtualMachineBackupPlanTemplate` and `VirtualMachineBackupPlan`)

## Configuration

### `application`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | **Required** | The name of the `BackupPlan` resource. |
| `namespace` | string | **Required** | The namespace for the `BackupPlan`. Usually the project namespace. |
| `clusterName` | string | **Required** | The name of the cluster targeted by the backup plan. |
| `backupRepository` | string | **Required** | The name of the `BackupRepository` or `ClusterBackupRepository` used to store backups. |
| `backupScope` | object | `{ allNamespaces: true }` | The scope of the backup. Defaults to cluster-wide `allNamespaces: true`. |
| `includeSecrets` | boolean | `false` | Whether to backup secrets. |
| `includeVolumeData` | boolean | `false` | Whether to perform volume snapshots and backup PV data. |
| `cronSchedule` | string | **Required** | A valid cron expression denoting the backup schedule. |
| `retentionPolicy.backupDeleteLockDays` | integer | `0` | Lock period for backups in days where they cannot be deleted. |
| `retentionPolicy.backupRetainDays` | integer | `0` | Minimum retention period for backups in days. |

### `cluster`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | **Required** | The name of the `ClusterBackupPlan`. |
| `namespace` | string | **Required** | The namespace for the plan. |
| `targetCluster.targetClusterType` | string | **Required** | Typically `UserCluster` or `ManagementAPI`. |
| `targetCluster.targetClusterName.name` | string | **Required** | Name of the cluster to backup. |
| `cronSchedule` | string | **Required** | A valid cron expression denoting the backup schedule. |
| `clusterBackupRepositoryName` | string | **Required** | Target cluster backup repository. |
| `backupScope` | object | `{ allNamespaces: true }` | Scope of the backup. |

### `harbor`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | **Required** | The name of the `HarborInstanceBackupPlan`. |
| `namespace` | string | **Required** | The namespace where the harbor instance resides. |
| `harborInstance` | string | **Required** | The name of the harbor instance to backup. |
| `backupRepository` | string | **Required** | The harbor backup repository. |
| `cronSchedule` | string | **Required** | Cron schedule expression. |

### `vm`

Note: One entry generates both a `VirtualMachineBackupPlanTemplate` (suffixed with `-template`) and a `VirtualMachineBackupPlan`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | **Required** | The name of the `VirtualMachineBackupPlan`. |
| `namespace` | string | **Required** | The namespace containing the VMs. |
| `backupRepository` | string | **Required** | The VM backup repository target. |
| `volumeStrategy` | string | **Required** | `ProvisionerSpecific` or `LocalSnapshotOnly`. |
| `backupScope` | object | `{}` | e.g. `vmResourceLabelSelector` or explicit lists. |
| `cronSchedule` | string | **Required** | Cron schedule expression. |

## Example `values.yaml`

```yaml
application:
  - name: "majduk-backup-plan"
    namespace: "data-ets-shared-infra"
    clusterName: "stress-test"
    backupRepository: "billing-cluster-backup-repository"
    cronSchedule: "35 20 * * *"

cluster:
  - name: my-cluster-backup-plan
    namespace: project-namespace
    targetCluster:
      targetClusterType: UserCluster
      targetClusterName:
        kind: "Cluster"
        name: "my-user-cluster"
    cronSchedule: "0 2 * * *"
    clusterBackupRepositoryName: my-cluster-repo

harbor:
  - name: my-harbor-backup-plan
    namespace: harbor-namespace
    harborInstance: my-harbor-instance
    backupRepository: my-harbor-repo
    cronSchedule: "0 3 * * *"

vm:
  - name: my-vm-backup-plan
    namespace: project-namespace
    backupRepository: my-vm-repo
    cronSchedule: "0 1 * * *"
    volumeStrategy: ProvisionerSpecific
    backupScope:
      vmResourceLabelSelector:
        backup: daily
```
