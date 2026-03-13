# gdc-project-network-policies

A Helm chart for managing Google Distributed Cloud Hosted (air-gapped) Project-level Network Policies. It templates Custom Resources like `ProjectNetworkPolicy` from the `networking.global.gdc.goog/v1` API group.

## Prerequisites

- Helm 3.0+
- Access to the Global API Cluster where GDCH policies are provisioned.

## Usage / Installation

Once `values.yaml` is configured or integrated into your multi-value YAML configs, run:

```bash
helm install my-policies ./gdc-project-network-policies -f my-values.yaml
```

## Configuration Parameters

The following table lists the configurable parameters of the chart and their default values.

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `projects[].name` | Name of the project/namespace the policy belongs to | `""` | **Yes** |
| `projects[].project-network-policies[].name` | Name of the ProjectNetworkPolicy resource | `""` | **Yes** if policies exist |
| `projects[].project-network-policies[].subject` | Target workloads subject block. | `{}` | No |
| `projects[].project-network-policies[].ingress` | Ingress filtering rules. | `[]` | No |
| `projects[].project-network-policies[].egress` | Egress filtering rules. | `[]` | No |

## Example Configuration (Optional)

This chart expects a top-level `projects` list in the `values.yaml`, with each project having an optional `project-network-policies` list attached.

```yaml
projectnetworkpolicies:
  - name: "allow-all-ingress-example"
    ingress:
      - {} # Empty object creates an allow-all rule
```

## Testing

This chart includes unit tests verifying the Go templating logic using the [helm-unittest](https://github.com/helm-unittest/helm-unittest) plugin. 

Testing the chart does not require a live Kubernetes cluster.

### Prerequisites for Testing
Ensure you have installed the `helm-unittest` plugin:
```bash
helm plugin install https://github.com/helm-unittest/helm-unittest.git
```
*(Note for air-gapped environments: You will need to download the release binary from GitHub and install it manually or ensure it is baked into your CI runner image).*

### Running Tests
To run the automated test suite locally:

```bash
helm unittest charts/gdc-project-network-policies
```
