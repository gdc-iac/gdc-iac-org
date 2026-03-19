# gdc-clusters

A Helm chart for managing Google Distributed Cloud Hosted (air-gapped) User Clusters via the `baremetal.cluster.gke.io/v1` or `cluster.gdc.goog/v1` API.

## Prerequisites

- Helm 3.0+
- Access to the Global API Cluster where GDCH clusters are provisioned.

## Usage / Installation

Once `values.yaml` is configured or integrated into your multi-value YAML configs, run:

```bash
helm install my-clusters ./gdc-clusters -f my-values.yaml
```

It supports configuring the control plane nodes, initial kubernetes versions, VIPs for load balancing, and network CIDRs matching the `cluster.gdc.goog/v1` specs.

## Configuration Parameters

The following table lists the configurable parameters of the chart and their default values.

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `clusters[].name` | Name of the cluster | `""` | **Yes** |
| `clusters[].namespace` | Target namespace on the admin/global cluster | `""` | **Yes** |
| `clusters[].annotations` | Dictionary of metadata annotations. (e.g. `last-applied-configuration`) | `{}` | No |
| `clusters[].labels` | Dictionary of metadata labels. | `{}` | No |
| `clusters[].clusterNetwork.podCIDRSize` | Size of pod CIDRs | `21` | No |
| `clusters[].clusterNetwork.serviceCIDRSize` | Size of service CIDRs | `23` | No |
| `clusters[].initialVersion.kubernetesVersion` | Initial K8s version deployed (e.g. `1.30.12-gke.300`) | `""` | No |
| `clusters[].loadBalancer.ingressServiceIPSize` | Size of LoadBalancer IP block | `21` | No |
| `clusters[].nodePools[].name` | Name of the NodePool | `""` | **Yes** if nodePools present |
| `clusters[].nodePools[].machineTypeName` | Hardware Machine Type (e.g. `n3-standard-16-gdc`) | `""` | **Yes** if nodePools present |
| `clusters[].nodePools[].nodeCount` | Number of nodes in this pool | `1` | No |
| `clusters[].releaseChannel` | Release channel | `"UNSPECIFIED"` | No |
| `clusters[].projectBindings[]` | List of target project names (e.g. `agtest-project`) | `[]` | No |

## Example Configuration (Optional)

This chart expects a top-level `clusters` list in the `values.yaml` representing the individual GDCH user clusters to create.

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
