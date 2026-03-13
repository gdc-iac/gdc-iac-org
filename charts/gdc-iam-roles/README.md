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
