# gdc-iac

A Helm chart for managing Infrastructure as Code (IaC) RoleBindings in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-iac ./gdc-iac -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `global.projects` | A list of projects to set namespaces for. | `[]` | No |
| `global.projects[].name` | Name of the project. | `""` | **Yes** if projects provided |
| `iac` | Configuration for the IaC RoleBinding. | `{}` | No |
| `iac.subject_name` | The name of the subject (e.g., user email). | `""` | **Yes** if iac configured |
| `iac.subject_kind` | The kind of the subject. | `"User"` | No |

## Example Configuration (Optional)

```yaml
global:
  projects:
    - name: "lotus-prj"
    - name: "snowflake-prj"
iac:
  subject_name: "fop-iac@example.com"
  subject_kind: "User"
```
