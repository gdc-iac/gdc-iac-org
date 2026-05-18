# GDC Cloud NAT Gateway Helm Chart (`gdc-cloudnatgateway`)

This Helm chart automates the provisioning of **Cloud NAT Gateways** inside Google Distributed Cloud (GDC) Hosted air-gapped environments. It uses GDC's official `networking.gdc.goog/v1` API group to define gateway workloads.

---

## Configuration Parameters

The following table lists the configurable parameters of the `gdc-cloudnatgateway` chart and their default values:

| Parameter | Description | Default | Required |
| :--- | :--- | :--- | :--- |
| `namespace` | Target namespace where resources are deployed | `""` | **Yes** |
| `name` | Unique identifier name of the Cloud NAT Gateway | `""` | **Yes** |
| `workloadSelector.matchLabels.app` | Target workload match label to route through the NAT | `""` | **Yes** |
| `subnetRefs` | List of leaf subnets representing egress IPs allocated for NAT | `[]` | **Yes** |
| `connectionOptions.nonTCPTimeoutSeconds` | Timeout for non-TCP connections in seconds | `60` | No |
| `connectionOptions.tcpTimeoutSeconds` | Timeout for established TCP connections in seconds | `600` | No |
| `connectionOptions.tcpTeardownTimeoutSeconds` | Teardown timeout for TCP connections in seconds | `120` | No |
| `connectionOptions.tcpEstablishmentTimeoutSeconds` | Establishment timeout for TCP connections in seconds | `20` | No |

---

## Usage Example

```yaml
# values.yaml
namespace: "my-project"
name: "my-cloud-nat"
workloadSelector:
  matchLabels:
    app: "internal-workload"
subnetRefs:
  - "nat-ip-subnet-1"
  - "nat-ip-subnet-2"
```
