# GDCH Database Services Helm Chart (gdch-dbs)

This Helm chart deploys and manages Database Services within a Google Distributed Cloud Hosted (GDCH) environment. It supports provisioning:

*   PostgreSQL DBClusters
*   Oracle DBClusters

## Prerequisites

1.  **Helm:** Helm version 3.x is installed.
2.  **Kubectl:** Kubectl is installed and configured to communicate with your GDCH Organization Management API server (e.g., `org-1-admin-zone1`).
3.  **Permissions:** You need sufficient permissions in the target project namespace to create Secrets and `DBCluster` resources (e.g., `project-db-admin` role or equivalent).
4.  **Project Namespace:** A project namespace must exist in your GDCH organization where the database will be deployed.

## Usage / Installation

1. Navigate to the chart directory:

```bash
cd gdc-dbs
```

2. Generate Base64 Password:

```bash
export B64_PASSWORD=$(echo -n 'YourSecureP@ssw0rd' | base64)
```

3. Install PostgreSQL Example:

```bash
helm install my-pg-release . \
  --namespace my-db-project \
  --set base64EncodedPassword=$B64_PASSWORD \
  --set postgresql.enabled=true
```

## Configuration Parameters

The chart is configured through the `values.yaml` file or by using `--set` flags during `helm install` or `helm upgrade`.

**Key Parameters:**

| Parameter                               | Description                                                                                                | Default                      |
| :-------------------------------------- | :--------------------------------------------------------------------------------------------------------- | :--------------------------- |
| `namespace`                             | The target project namespace for deployment.                                                               | `my-db-project`              |
| `alloydbomni.enabled`                   | Set to `true` to deploy an AlloyDB Omni DBCluster.                                  		       | `false`                      |
| `alloydbomni.clusterName`               | Name of the AlloyDB Omni DBCluster resource.                                      			       | `my-alloydb-cluster`         |
| `alloydbomni.base64EncodedPassword`     | **Required if alloydbomni.enabled=true.** Base64 encoded password for the admin user. 		       | `""`                         |
| `alloydbomni.version`                   | AlloyDB Omni version (e.g., "15").                                                			       | `"15"`                       |
| `alloydbomni.cpu`                       | CPU allocation for the primary instance.                                          			       | `4`                          |
| `alloydbomni.memory`                    | Memory allocation for the primary instance.                                       			       | `16Gi`                       |
| `alloydbomni.dataDiskSize`              | Size of the data disk.                                                            			       | `50Gi`                       |
| `alloydbomni.parameters`                | Optional. Key-value pairs for database parameters.                                			       | `{}`                         |
| `oracle.enabled`                        | Set to `true` to deploy an Oracle DBCluster. Only one database type can be enabled at a time.              | `false`                      |
| `oracle.clusterName`                    | Name of the Oracle DBCluster resource.                                                                     | `my-ora-cluster`             |
| `oracle.base64EncodedPassword`          | **Required if oracle.enabled=true.** Base64 encoded password for the Oracle admin user.                    | `""`                         |
| `oracle.version`                        | Oracle version (e.g., "19"). Check your GDCH documentation for supported versions.                         | `"19"`                       |
| `oracle.cpu`                            | CPU allocation for the primary instance.                                                                   | `2`                          |
| `oracle.memory`                         | Memory allocation for the primary instance.                                                                | `8Gi`                        |
| `oracle.dataDiskSize`                   | Size of the data disk.                                                                                     | `20Gi`                       |
| `oracle.logDiskSize`                    | Size of the log disk.                                                                                      | `20Gi`                       |
| `oracle.cdbName`                        | Oracle Container Database (CDB) name.                                                                      | `MYORACDB`                   |
| `postgresql.enabled`                    | Set to `true` to deploy a PostgreSQL DBCluster. Only one database type can be enabled at a time.           | `false`                      |
| `postgresql.clusterName`                | Name of the PostgreSQL DBCluster resource.                                                                 | `my-pg-cluster`              |
| `postgresql.base64EncodedPassword`      | **Required if postgresql.enabled=true.** Base64 encoded password for the PG admin user.                    | `""`                         |
| `postgresql.version`                    | PostgreSQL version (e.g., "14"). Check your GDCH documentation for supported versions.                     | `"14"`                       |
| `postgresql.cpu`                        | CPU allocation for the primary instance.                                                                   | `2`                          |
| `postgresql.memory`                     | Memory allocation for the primary instance.                                                                | `4Gi`                        |
| `postgresql.dataDiskSize`               | Size of the data disk.                                                                                     | `10Gi`                       |

**Important: Password Management**

Never store plain text passwords in the `values.yaml` file. The `base64EncodedPassword` value **must** be provided securely during installation using the `--set` flag.

To generate a base64 encoded password:

```bash
echo -n 'YourSecureP@ssw0rd' | base64

## Example Configuration (Optional)

To customize further (PostgreSQL):

```bash
helm install my-pg-release . \
  --namespace my-db-project \
  --set base64EncodedPassword=$B64_PASSWORD \
  --set postgresql.enabled=true \
  --set postgresql.clusterName=prod-pg \
  --set postgresql.memory=8Gi \
  --set postgresql.dataDiskSize=100Gi
```
helm install my-pg-release . \
  --namespace my-db-project \
  --set base64EncodedPassword=$B64_PASSWORD \
  --set postgresql.enabled=true \
  --set postgresql.clusterName=prod-pg \
  --set postgresql.memory=8Gi \
  --set postgresql.dataDiskSize=100Gi

```

4. Install Oracle Example:

```
helm install my-ora-release . \
  --namespace my-db-project \
  --set base64EncodedPassword=$B64_PASSWORD \
  --set oracle.enabled=true

```

To customize further:

```
helm install my-ora-release . \
  --namespace my-db-project \
  --set base64EncodedPassword=$B64_PASSWORD \
  --set oracle.enabled=true \
  --set oracle.clusterName=prod-ora \
  --set oracle.cdbName=PRODORACDB \
  --set oracle.memory=16Gi

``` 

## Checking Deployment Status

Use kubectl to monitor the status of the `DBCluster` resource:

- PostgreSQL:

```
kubectl get dbcluster.postgresql.dbadmin.gdc.goog -n <namespace> <postgresql.clusterName> -w
```

- Oracle:

```
kubectl get dbcluster.oracle.dbadmin.gdc.goog -n <namespace> <oracle.clusterName> -w
```

Wait for the `Status` field to show `Ready`.

## Uninstallation
To uninstall/delete the Helm release:

```
helm uninstall <release-name> --namespace <namespace>
```

Example:

```
helm uninstall my-pg-release --namespace my-db-project
```

This will remove the `DBCluster` and associated `Secret` created by the chart.

## Accessing the Database
Refer to the GDCH Database Services documentation for details on how to connect to your provisioned database instance. The service endpoints and connection details can typically be found in the status of the `DBCluster` resource.

## CI/CD Pre-Deployment Testing

This repository enforces a strict, 4-step offline testing pipeline for all Helm charts to ensure GitOps best practices for our enterprise GDC landing zone. Tests are executed via the global `gdc-iac-org/scripts/test-charts.sh` script.

### The 4 Validation Layers

1.  **Input/Schema Validation:** Verifies that required values (like `namespace`) are provided and strongly typed using the native `values.schema.json`.
2.  **Logic Validation (`helm-unittest`):** Asserts that the Go templating logic correctly generates the intended YAML without needing a live cluster.
3.  **Structural Validation (`kubeconform`):** Verifies the rendered YAML conforms strictly to Kubernetes OpenAPI specifications. 
    > [!IMPORTANT]
    > `kubeconform` currently skips validation of the `ProjectNetworkPolicy` Custom Resource Definition. To achieve maximum offline safety, administrators should export the GDC CRD schemas and supply them to the test pipeline.
4.  **Security Policy Validation (`conftest` / OPA):** Asserts that the generated manifests comply with enterprise security mandates (e.g., denying `0.0.0.0/0` ingress rules), defined via Rego policies in the `policy/` directory.

### Prerequisites for Local Testing

If you are developing locally in an air-gapped environment, ensure the following binaries are downloaded and available in your `$PATH` (or injected into your CI runner image):

- `helm` (with the `helm-unittest` plugin installed)
- `kubeconform`
- `conftest`

### Running the Tests

To run the entire validation suite across all charts, execute the global test script from the repository root:

```bash
./scripts/test-charts.sh
```
