# gdc-billing

A Helm chart for managing billing configurations in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-billing ./gdc-billing -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `billing` | Billing configuration object. | `{}` | No |

## Example Configuration (Optional)

```yaml
billing: {}
```
