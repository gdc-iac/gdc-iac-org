# gdc-project-network-policies

A Helm chart for managing Google Distributed Cloud Hosted (air-gapped) Project-level Network Policies. It templates Custom Resources like `ProjectNetworkPolicy` from the `networking.global.gdc.goog/v1` API group.

## Requirements

- Helm 3.0+
- Access to the Global API Cluster where GDCH policies are provisioned.

## Usage

This chart expects a top-level `projects` list in the `values.yaml`, with each project having an optional `project-network-policies` list attached.

## Configuration Parameters

The following table lists the configurable parameters of the chart and their default values.

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `projects[].name` | Name of the project/namespace the policy belongs to | `""` | **Yes** |
| `projects[].project-network-policies[].name` | Name of the ProjectNetworkPolicy resource | `""` | **Yes** if policies exist |
| `projects[].project-network-policies[].subject` | Target workloads subject block. | `{}` | No |
| `projects[].project-network-policies[].ingress` | Ingress filtering rules. | `[]` | No |
| `projects[].project-network-policies[].egress` | Egress filtering rules. | `[]` | No |

## Applying the Chart

Once `values.yaml` is configured or integrated into your multi-value YAML configs, run:

```bash
helm install my-policies ./charts/gdc-project-network-policies -f my-values.yaml
```
