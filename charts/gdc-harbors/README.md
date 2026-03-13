# gdc-harbors

A Helm chart for managing Harbor instances in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-harbors ./gdc-harbors -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `harbors` | A list of Harbor instances to create. | `[]` | No |

## Example Configuration (Optional)

```yaml
harbors: []
```
