# gdc-iam-role-bindings

A Helm chart for managing IAM RoleBindings in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-iam-role-bindings ./gdc-iam-role-bindings -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `namespace` | Target namespace for the RoleBindings. | `""` | No |
| `iamrolebindings` | List of IAM RoleBindings to create. | `[]` | No |
| `iamrolebindings[].role` | The name of the role to bind. | `""` | **Yes** if bindings provided |
| `iamrolebindings[].subject_kind` | The kind of subject (e.g., User, Group, ServiceAccount). | `""` | **Yes** if bindings provided |
| `iamrolebindings[].subject_name` | The name of the subject. | `""` | **Yes** if bindings provided |

## Example Configuration (Optional)

```yaml
namespace: "my-namespace"
iamrolebindings:
  - role: "project-admin"
    subject_kind: "User"
    subject_name: "alice@example.com"
```
