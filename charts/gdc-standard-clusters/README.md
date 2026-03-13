# gdc-standard-clusters

A Helm chart for deploying standard clusters in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-standard-clusters ./gdc-standard-clusters -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `standardClusters` | List or map of standard clusters to create. | `{}` | No |
| `standardClusters.<name>.name` | Name of the standard cluster. | `""` | **Yes** if cluster provided |
| `standardClusters.<name>.namespace` | Namespace for the standard cluster. | `""` | **Yes** if cluster provided |
| `standardClusters.<name>.podCIDRSize` | Pod CIDR block size. | `""` | No |
| `standardClusters.<name>.serviceCIDRSize` | Service CIDR block size. | `""` | No |
| `standardClusters.<name>.kubernetesVersion` | Kubernetes version of the cluster. | `""` | No |
| `standardClusters.<name>.nodePools` | Node pools configuration for the standard cluster. | `[]` | No |

## Example Configuration (Optional)

```yaml
standardClusters:
  cluster1:
    name: "smugabe-test-cluster"
    namespace: "platform"
    podCIDRSize: 21
    serviceCIDRSize: 23
    kubernetesVersion: "1.26.5-gke.2100"
    nodePools:
      - name: "pool-1"
        machineTypeName: "n2-standard-4"
        nodeCount: 3
```
