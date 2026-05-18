# gdc-project-network-policies

A Helm chart for managing Google Distributed Cloud Hosted (air-gapped) Project-level Network Policies. It templates Custom Resources like `ProjectNetworkPolicy` from the `networking.global.gdc.goog/v1` API group.

## Prerequisites

- Helm 3.0+
- Access to the Global API Cluster where GDCH policies are provisioned.

## Usage / Installation

Once `values.yaml` is configured or integrated into your multi-value YAML configs, run:

```bash
helm install my-policies ./gdc-project-network-policies -f my-values.yaml
```

## Configuration Parameters

The following table lists the configurable parameters of the chart and their default values.

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `projects[].name` | Name of the project/namespace the policy belongs to | `""` | **Yes** |
| `projects[].project-network-policies[].name` | Name of the ProjectNetworkPolicy resource | `""` | **Yes** if policies exist |
| `projects[].project-network-policies[].subject` | Target workloads subject block. | `{}` | No |
| `projects[].project-network-policies[].ingress` | Ingress filtering rules. | `[]` | No |
| `projects[].project-network-policies[].egress` | Egress filtering rules. | `[]` | No |

## Example Configuration (Optional)

This chart expects a top-level `projects` list in the `values.yaml`, with each project having an optional `project-network-policies` list attached.

```yaml
projectnetworkpolicies:
  - name: "allow-all-ingress-example"
    ingress:
      - {} # Empty object creates an allow-all rule
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
