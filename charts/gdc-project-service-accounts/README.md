# gdc-project-service-accounts

A Helm chart for managing Project Service Accounts in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-project-sa ./gdc-project-service-accounts -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `name` | The name of the project. | `""` | No |
| `projectserviceaccounts` | A list of service account names to create in the project. | `[]` | No |

## Example Configuration (Optional)

```yaml
name: "lotus-project"
projectserviceaccounts:
  - "lotus-frontend-sa"
  - "lotus-backend-sa"
```
