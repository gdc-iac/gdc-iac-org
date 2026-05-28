# gdc-org-policies

A Helm chart for managing Organization Policies in Google Distributed Cloud (GDC) air-gapped environments.

## Overview

Organization policies (`GDCHRestrictedService` custom resources) provide centralized, programmatic control over your organization's resources using OPA Gatekeeper constraints. Unlike identity and access management (IAM) which focuses on *who* can access resources, organization policies focus on *what*, allowing administrators to define restrictions on specific GDC managed services.

This chart manages policies that restrict operations (e.g., `CREATE`, `UPDATE`, `DELETE`) on protected API groups, such as preventing uncontrolled Vertex AI Notebook creation or preventing deletion of authoritative Database backups.

For comprehensive details on official usage and schemas, refer to the [official GDC documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/platform/pa-user/org-policy).

## Prerequisites

- Helm 3+
- GDC admin cluster with the `constraints.gatekeeper.sh/v1beta1` API group

## Usage / Installation

```bash
helm install my-org-policies ./gdc-org-policies -f values.yaml
```

## Configuration Parameters

The core configuration property is `orgpolicies` within `values.yaml`. This acts as an array of Gatekeeper restricted service definitions.

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `orgpolicies` | A list of organization policies to create. | `[]` | **Yes** |
| `orgpolicies[].name` | Name of the `GDCHRestrictedService` constraint. | `""` | **Yes** |
| `orgpolicies[].apiGroup` | The GDC API group to target (e.g. `postgresql.dbadmin.gdc.goog`). | `""` | **Yes** |
| `orgpolicies[].kind` | The Kind of resource within the target API group. | `""` | **Yes** |
| `orgpolicies[].disabledOperations` | Array of REST operations to block (`CREATE`, `UPDATE`, `DELETE`, `*`). | `[]` | **Yes** |

### Example Usage

The following configuration demonstrates how to completely restrict the creation of Vertex AI Notebooks, and how to restrict the modification or deletion of existing Postgres Backup Plans.

```yaml
orgpolicies:
  - name: "restrict-vertex-notebook-creation"
    apiGroup: "aiplatform.gdc.goog"
    kind: "Notebook"
    disabledOperations:
      - "CREATE"
      
  - name: "protect-postgres-backups"
    apiGroup: "postgresql.dbadmin.gdc.goog"
    kind: "BackupPlan"
    disabledOperations:
      - "UPDATE"
      - "DELETE"
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
