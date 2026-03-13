# gdc-standard-cluster-external-traffic

A Helm chart for managing external traffic routing policies for standard clusters in GDC.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-external-traffic ./gdc-standard-cluster-external-traffic -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `namespace` | The namespace where these external traffic routing policies will be applied. | `"default"` | No |
| `loadBalancer.subjectLabelKey` | The label key used to match workloads receiving LB traffic. | `"app"` | No |
| `loadBalancer.subjectLabelValue` | The label value used to match workloads receiving LB traffic. | `"ingress-controller"` | No |
| `loadBalancer.ingress.enabled` | Enable Load Balancer ingress routing. | `true` | No |
| `loadBalancer.ingress.fromCidr` | The external LB IP or internal network that the LB is routing from. | `"10.0.0.0/8"` | No |
| `loadBalancer.ingress.port` | Ingress port for load balancer. | `443` | No |
| `loadBalancer.egress.enabled` | Enable Load Balancer egress routing. | `false` | No |
| `loadBalancer.egress.toCidr` | Egress CIDR destination. | `"10.0.0.0/8"` | No |
| `loadBalancer.egress.port` | Egress port. | `443` | No |
| `orgExternal.subjectLabelKey` | The label key used to match workloads allowed to talk to external endpoints. | `"app"` | No |
| `orgExternal.subjectLabelValue` | The label value used to match workloads. | `"external-gateway"` | No |
| `orgExternal.ingress.enabled` | Enable ORG external ingress routing. | `false` | No |
| `orgExternal.ingress.fromCidr` | Ingress limit CIDR for ORG external. | `"192.168.1.0/24"` | No |
| `orgExternal.ingress.port` | Ingress port. | `8443` | No |
| `orgExternal.egress.enabled` | Enable ORG external egress routing. | `true` | No |
| `orgExternal.egress.toCidr` | Egress CIDR destination. | `"192.168.1.0/24"` | No |
| `orgExternal.egress.port` | Egress port. | `8443` | No |

## Example Configuration (Optional)

```yaml
namespace: default
loadBalancer:
  subjectLabelKey: app
  subjectLabelValue: ingress-controller
  ingress:
    enabled: true
    fromCidr: "10.0.0.0/8"
    port: 443
```
