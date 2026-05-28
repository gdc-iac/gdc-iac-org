# gdc-standard-clusters

A Helm chart for deploying standard clusters in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-standard-clusters ./gdc-standard-clusters -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `standardClusters` | List or map of standard clusters to create. | `{}` | No |
| `standardClusters.<name>.name` | Name of the standard cluster. | `""` | **Yes** if cluster provided |
| `standardClusters.<name>.namespace` | Namespace for the standard cluster. | `""` | **Yes** if cluster provided |
| `standardClusters.<name>.podCIDRSize` | Pod CIDR block size. | `""` | No |
| `standardClusters.<name>.serviceCIDRSize` | Service CIDR block size. | `""` | No |
| `standardClusters.<name>.kubernetesVersion` | Kubernetes version of the cluster. | `""` | No |
| `standardClusters.<name>.nodePools` | Node pools configuration for the standard cluster. | `[]` | No |

## Example Configuration (Optional)

```yaml
standardClusters:
  cluster1:
    name: "smugabe-test-cluster"
    namespace: "platform"
    podCIDRSize: 21
    serviceCIDRSize: 23
    kubernetesVersion: "1.26.5-gke.2100"
    nodePools:
      - name: "pool-1"
        machineTypeName: "n2-standard-4"
        nodeCount: 3
```

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
