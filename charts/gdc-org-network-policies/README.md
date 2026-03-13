# gdc-org-network-policies

A Helm chart for creating Organization Network Policies in Google Distributed Cloud (GDC) air-gapped environments.

## Overview

Organization network policies (`OrganizationNetworkPolicy` custom resources) function at the organizational level to control access to specific GDC managed services. By default, many services are denied default access to ensure a strong security baseline. This chart allows Platform Administrators to explicitly declare which networks can access key management interfaces like the UI console, Vertex AI, object storage, etc.

For comprehensive details on official usage and schemas, refer to the [official GDC documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/platform/pa-user/org-network-policy).

## Prerequisites

- Helm 3+
- GDC admin cluster with the `networking.gdc.goog/v1` API group (Management API Server)

## Usage / Installation

```bash
helm install my-org-netpols ./gdc-org-network-policies -f values.yaml
```

## Configuration Parameters

The core configuration property is `orgnetworkpolicies` within `values.yaml`. This acts as an array of network policy definitions.

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `orgnetworkpolicies` | A list of organization network policies to create. | `[]` | **Yes** |
| `orgnetworkpolicies[].name` | Name of the OrganizationNetworkPolicy resource. | `""` | **Yes** |
| `orgnetworkpolicies[].subject` | Target workloads subject block. | `{}` | No |
| `orgnetworkpolicies[].ingress` | Ingress filtering rules. | `[]` | No |
| `orgnetworkpolicies[].egress` | Egress filtering rules. | `[]` | No |

### Example Usage

The following configuration allows traffic from the `10.251.0.0/24` subnet to access both the `ui-console` and `api-server` services.

```yaml
orgnetworkpolicies:
  - name: "allow-ui-and-api-access"
    subject:
      services:
        match_types:
        - "ui-console"
        - "api-server"
    ingress:
      - from:
        - ip_block:
            cidr: "10.251.0.0/24"
```

Common service names include:
- `all`: All services
- `ui-console`: GDC console
- `api-server`: gdcloud CLI
- `global-api-server`: Global API server
- `iam`: IAM
- `kms`: KMS
- `object-storage`: Object storage
- `system-artifact-registry`: SAR
- `ai`: Vertex AI
- `vmm`: Virtual Machine Management (VMM)
