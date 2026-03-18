# gdc-iam-roles

A Helm chart for managing IAM Roles in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-iam-roles ./gdc-iam-roles -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `projects` | List or map of projects. | `{}` | No |
| `projects.<name>` | Configuration for a specific project. | `{}` | No |
| `projects.<name>.name` | Name of the GDC project. | `""` | **Yes** if projects provided |
| `projects.<name>.namespace` | Namespace of the project (e.g., "platform"). | `""` | **Yes** if projects provided |

## Example Configuration (Optional)

```yaml
projects:
  project1:
    name: "project-x"
    namespace: "platform"
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
