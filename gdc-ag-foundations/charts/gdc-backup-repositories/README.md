# gdc-backup-repositories

A Helm chart for creating `ClusterBackupRepository`, `BackupRepository`, and `HarborInstanceBackupRepository` resources in Google Distributed Cloud Hosted (GDCH).

## Overview

This chart simplifies the process of configuring and adding S3-compatible backup repositories in GDCH. These repositories are used by the Backup and Restore APIs to schedule and store backups for clusters, virtual machines, and harbor instances.

## Configuration

The chart accepts configuration across three distinct lists in `./values.yaml`:

- `cluster` (Global cluster backups)
- `vm` (Virtual machine backups)
- `harbor` (Harbor instance backups)

### `cluster` & `vm`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | **Required** | The name of the `ClusterBackupRepository` or `BackupRepository` resource. |
| `namespace` | string | **Required** | The namespace for the repository. Usually the project namespace. |
| `secretReference.name` | string | **Required** | The name of the Secret that contains the S3 credentials within the namespace. |
| `secretReference.namespace` | string | _Repository namespace_ | (Optional) The namespace where the secret exists. Defaults to `namespace`. |
| `endpoint` | string | **Required** | The FQDN for the storage system. |
| `type` | string | `"S3"` | The type of the repository. Only `"S3"` is currently supported by GDCH. |
| `s3Options.bucket` | string | **Required** | The fully qualified name (FQDN) of the bucket. |
| `s3Options.region` | string | **Required** | The storage region where the bucket resides. |
| `s3Options.forcePathStyle` | boolean | `false` | Set to `true` to force path-style URLs for objects. |
| `importPolicy` | string | `"ReadWrite"` | Set to `"ReadWrite"` or `"ReadOnly"`. |

### `harbor`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | **Required** | The name of the `HarborInstanceBackupRepository` resource. |
| `namespace` | string | **Required** | The namespace for the repository. **Must share the same namespace** as the Harbor instance being backed up. |
| `secretReference.name` | string | **Required** | The name of the Secret that contains the S3 credentials within the namespace. |
| `secretReference.namespace` | string | _Repository namespace_ | (Optional) The namespace where the secret exists. Defaults to `namespace`. |
| `endpoint` | string | **Required** | The FQDN for the storage system. |
| `bucket` | string | **Required** | The bucket name found in the status of the GDC bucket custom resource. |
| `region` | string | **Required** | The storage region where the bucket resides. |
| `description` | string | `""` | Optional text description of the backup repository. |

## Example `values.yaml`

```yaml
cluster:
  - name: "my-dr-repository"
    namespace: "my-project-ns"
    secretReference:
      name: "s3-credentials-secret"
    endpoint: "https://objectstorage.google.gdch.test"
    type: "S3"
    s3Options:
      bucket: "my-bucket.fqdn"
      region: "us-east1"
      forcePathStyle: true
    importPolicy: "ReadWrite"

vm:
  - name: "my-vm-backup"
    namespace: "my-project-ns"
    secretReference:
      name: "s3-credentials-secret"
    endpoint: "https://objectstorage.google.gdch.test"
    type: "S3"
    s3Options:
      bucket: "my-vm-bucket.fqdn"
      region: "us-east1"
      forcePathStyle: true

harbor:
  - name: "my-harbor-backup"
    namespace: "my-harbor-namespace"
    secretReference:
      name: "harbor-s3-secret"
    endpoint: "https://objectstorage.google.gdch.test"
    region: "us-east1"
    bucket: "my-harbor-bucket"
    description: "Daily harbor backup repository"
```
