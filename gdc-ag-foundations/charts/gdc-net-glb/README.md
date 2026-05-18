# GDC Global Load Balancer Helm Chart (`gdc-net-glb`)

This Helm chart automates the provisioning of **Global Internal** and **Global External** Load Balancers inside Google Distributed Cloud (GDC) Hosted air-gapped environments. It is built on top of GDC's official `networking.global.gdc.goog/v1` and `networking.gdc.goog/v1` KRM API groups.

---

## Architecture Overview

By deploying this chart, Helm compiles and creates the following KRM custom resources depending on your scheme:

* **`Backend`**: Identifies and groups the targeted workload endpoints (Pods or VMs).
* **`HealthCheck`** (Optional): Periodically validates VM workload health status (VM backends only).
* **`BackendService`**: Orchestrates backend refs, zones, and port translation mappings.
* **`ForwardingRule`**: Dynamically provisions either **`ForwardingRuleInternal`** or **`ForwardingRuleExternal`** to expose the Virtual IP (VIP).
* **`ProjectNetworkPolicy`** (Optional): Creates ingress firewall permissions (External Scheme only) to permit traffic from external client subnets (required due to Direct Server Return).

---

## Configuration Parameters

The following table lists the configurable parameters of the `gdc-net-glb` chart and their default values:

| Parameter | Description | Default | Required |
| :--- | :--- | :--- | :--- |
| `namespace` | Target namespace where resources are deployed | `""` | **Yes** |
| `name` | Unique identifier name of the load balancer | `""` | **Yes** |
| `loadBalancingScheme` | Schemes: `"INTERNAL"` or `"EXTERNAL"` | `"INTERNAL"` | **Yes** |
| `backend.clusterName` | Standard/shared cluster name (optional) | `""` | No |
| `backend.matchLabels.app` | Match label key/value selector targeting workloads | `""` | **Yes** |
| `healthCheck.enabled` | Enables TCP Health Checks (VM workloads only) | `false` | No |
| `healthCheck.port` | Port to perform health probes | `80` | No |
| `healthCheck.timeoutSec` | Probe timeout in seconds | `5` | No |
| `healthCheck.checkIntervalSec` | Probe interval in seconds | `5` | No |
| `healthCheck.healthyThreshold` | Consecutives successes to mark healthy | `2` | No |
| `healthCheck.unhealthyThreshold` | Consecutives failures to mark unhealthy | `2` | No |
| `backendService.zone` | Zonal location of targeted workloads | `""` | **Yes** |
| `backendService.port` | Port exposed by the BackendService | `80` | **Yes** |
| `backendService.protocol` | Network protocol: `"TCP"` or `"UDP"` | `"TCP"` | **Yes** |
| `backendService.targetPort` | Underlying port exposed by container workload | `80` | **Yes** |
| `forwardingRule.cidrName` | Subnet resource name to pull static VIP (optional) | `""` | No |
| `forwardingRule.port` | Exposed frontend L4 port on the VIP | `80` | **Yes** |
| `forwardingRule.protocol` | Exposed frontend L4 protocol | `"TCP"` | **Yes** |
| `pnp.enabled` | Deploys `ProjectNetworkPolicy` (EXTERNAL only) | `true` | No |
| `pnp.allowedCidr` | External client CIDR range allowed ingress traffic | `"0.0.0.0/0"` | No |

---

## Usage Examples

### 1. Deploying a Global Internal Load Balancer (ILB)

Use this configuration to expose workloads internally to other clusters within your GDC organization:

```yaml
# values-ilb.yaml
namespace: "my-project"
name: "internal-app-lb"
loadBalancingScheme: "INTERNAL"

backend:
  matchLabels:
    app: "frontend-app"

backendService:
  zone: "zone1"
  port: 80
  protocol: "TCP"
  targetPort: 8080

forwardingRule:
  port: 80
  protocol: "TCP"
```

### 2. Deploying a Global External Load Balancer (ELB)

Use this configuration to expose workloads to public or external client networks outside your GDC organization:

```yaml
# values-elb.yaml
namespace: "my-project"
name: "external-app-lb"
loadBalancingScheme: "EXTERNAL"

backend:
  matchLabels:
    app: "frontend-app"

backendService:
  zone: "zone1"
  port: 80
  protocol: "TCP"
  targetPort: 8080

forwardingRule:
  port: 80
  protocol: "TCP"

pnp:
  enabled: true
  allowedCidr: "192.168.10.0/24" # External client network range
```
