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

## CI/CD Pre-Deployment Testing

This repository enforces a strict, 4-step offline testing pipeline for all Helm charts to ensure GitOps best practices for our enterprise GDC landing zone. Tests are executed via the global `gdc-iac-org/scripts/test-charts.sh` script.

### The 4 Validation Layers

1.  **Input/Schema Validation:** Verifies that required values (like `namespace`) are provided and strongly typed using the native `values.schema.json`.
2.  **Logic Validation (`helm-unittest`):** Asserts that the Go templating logic correctly generates the intended YAML without needing a live cluster.
3.  **Structural Validation (`kubeconform`):** Verifies the rendered YAML conforms strictly to Kubernetes OpenAPI specifications. 
    > [!IMPORTANT]
    > `kubeconform` currently skips validation of the `ProjectNetworkPolicy` Custom Resource Definition. To achieve maximum offline safety, administrators should export the GDC CRD schemas and supply them to the test pipeline.
4.  **Security Policy Validation (`conftest` / OPA):** Asserts that the generated manifests comply with enterprise security mandates (e.g., denying `0.0.0.0/0` ingress rules), defined via Rego policies in the `policy/` directory.

### Prerequisites for Local Testing

If you are developing locally in an air-gapped environment, ensure the following binaries are downloaded and available in your `$PATH` (or injected into your CI runner image):

- `helm` (with the `helm-unittest` plugin installed)
- `kubeconform`
- `conftest`

### Running the Tests

To run the entire validation suite across all charts, execute the global test script from the repository root:

```bash
./scripts/test-charts.sh
```
