import os
import re

TESTING_BLOCK = """## CI/CD Pre-Deployment Testing

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
"""

charts_dir = "charts"
for chart_name in os.listdir(charts_dir):
    chart_path = os.path.join(charts_dir, chart_name)
    readme_file = os.path.join(chart_path, "README.md")
    
    if os.path.isdir(chart_path) and os.path.isfile(readme_file):
        with open(readme_file, "r") as f:
            content = f.read()
            
        # Remove old testing blocks if they exist
        content = re.sub(r'## Testing\n.*', '', content, flags=re.DOTALL)
        content = re.sub(r'## CI/CD Pre-Deployment Testing\n.*', '', content, flags=re.DOTALL)
        
        # Append the new standardized block
        content = content.strip() + "\n\n" + TESTING_BLOCK
        
        with open(readme_file, "w") as f:
            f.write(content)
        print(f"Updated README for {chart_name}")
