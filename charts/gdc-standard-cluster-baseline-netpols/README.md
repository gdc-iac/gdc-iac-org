# gdc-standard-cluster-baseline-netpols

A Helm chart for applying baseline network policies to standard clusters in GDC.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-baseline-netpols ./gdc-standard-cluster-baseline-netpols -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `namespace` | The namespace where these baseline policies will be applied. | `"default"` | No |
| `defaultDeny.enabled` | Enable the default deny-all policy for the namespace. | `true` | No |
| `allowDns.enabled` | Enable explicit egress to kube-dns. | `true` | No |
| `allowAll.enabled` | Enable an overriding policy that allows all traffic. | `false` | No |

## Example Configuration (Optional)

```yaml
namespace: default
defaultDeny:
  enabled: true
allowDns:
  enabled: true
allowAll:
  enabled: false
```
