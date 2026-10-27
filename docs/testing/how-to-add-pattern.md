Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# How to Add a New Pattern

This guide outlines the steps to add a new Resilient Architecture Pattern to the GDC Blueprints repository.

## 1. Create Pattern Directory
1.  Copy the `template-pattern` directory to a new directory named `p<N>-<pattern-name>`.
    ```bash
    cp -r template-pattern p9-new-pattern-name
    ```
2.  Update the `README.md` in your new directory:
    *   Set the Title to your pattern name.
    *   Fill in the **Use Case**, **Architecture Schematic**, and **Design Strategy**.
    *   Update the **Prerequisites** and **Deployment** sections with specific resource names.

## 2. Define Infrastructure (Manifests)
Populate the `manifests/` directory with your Kubernetes YAML files.
*   **Structure**: Organize subfolders by function if needed (e.g., `manifests/db/`, `manifests/apps/`).
*   **Namespace**: Ensure all resources use `namespace: test-project` (this is the convention for validation; deployment scripts patch it for GCP).
*   **Images**: Use placeholders for image registries (e.g., `image: test-registry.local/my-org/my-app:v1`).

## 3. Create Example Application
Create an `example-app` directory to house a reference implementation. This is crucial for validating that the architecture actually supports a workload.

**Required Structure:**
```text
p9-new-pattern-name/
├── example-app/
│   ├── src/                 # Application Source Code
│   ├── Dockerfile           # Multi-stage build (run as non-root)
│   ├── docker-compose.yaml  # (Optional) For local testing
│   └── README.md            # Usage instructions
```

## 4. Implement Testing Scripts

### 4.1. Validation
Update `test/validate.sh` to checks your manifests.
*   **Recommended**: Use the shared validation logic.
    ```bash
    #!/bin/bash
    # test/validate.sh
    source "$(dirname "$0")/../../tests/common/validate_manifests.sh"
    validate_manifests "$(dirname "$0")/../manifests"
    ```

### 4.2. Verification
Update `test/verify.sh` to verify your specific resources are healthy.
*   **Context**: This script runs *after* deployment.
*   **Logic**: Check for specific pods, services, or log messages.
*   **Mock Support**: Ensure it sources `tests/lib/mocks.sh` if running in mock mode.

## 5. Register in Global Scripts
To ensure your pattern is included in the unified test pipeline, update the following scripts in the root `scripts/` directory:

Note: if your pattern is based on deploying a solution which requires the example application to be an intrinsic and non optional part
of the blueprint do not include it in the global scripts. Use p9-notebooklm as a guide on how to incorporate 

### 5.1. `deploy-gcp-mocked.sh`
*   Add a case to the `Patch Image Names` section (approx line 100) to map your generic image names (e.g., `my-app:v1`) to the GCP Artifact Registry names.
*   Add any specific mock injection logic if your pattern relies on GDC-only CRDs (like Pattern 2 or 3).

### 5.2. `cleanup-gcp.sh`
*   Add your pattern directory name to the `ALL_PATTERNS` array.

### 5.3. `stage1-local-test.sh` (Optional)
*   Ensure the script iterates over your new directory (it typically wildcards `p*`, so this might be automatic, but verify).

## 6. Update Documentation
*   Add your pattern to the main table in `README.md` (root).
*   Update `docs/patterns_def.md` with the formal definition if applicable.

## 7. Submit PR
1.  Run the local test suite: `bash tests/run-local.sh`
2.  (Optional) Run GCP mock deployment: `./scripts/deploy-gcp-mocked.sh p9-new-pattern-name`
3.  Commit your changes.

## 8. Register in Testing Plan

### 8.1. Add to Verification Guide (Section 7)
Add a new entry in `docs/testing_plan.md` under **7. Pattern-Specific Verification Guide**. Provide the manual commands a user should run to verify your pattern is working (e.g., port-forwarding, curling an endpoint, checking logs).

Example:
```markdown
### Pattern 9: My New Pattern
*   **Deploy**: `./scripts/deploy-gcp-mocked.sh p9-new-pattern-name`
*   **Verify**:
    ```bash
    kubectl port-forward svc/my-service 8080:80
    curl http://localhost:8080/health
    ```
```

### 8.2. Add to Reference Table (Section 9)
Update `docs/testing_plan.md` to include your new pattern in the **Reference: Expected Pod Statuses** table.

**Why?**
This table serves as the "source of truth" for the `verify.sh` scripts and human operators. It defines what "healthy" looks like for your specific pattern in a mock environment.

*   **P9 | `your-app-pod-*` | ✅ Running**: If the pod should be active.
*   **P9 | `job-pod-*` | ✅ Completed**: If it's a batch job.
*   **P9 | `mock-pod-*` | ⚠️ CrashLoop**: If it's acceptable for a mock to fail (e.g., missing dependency) but still prove the infra is up.

Example:
```markdown
| **P9**    | `my-new-app-*`       | ✅ **Running**             | Main application. |
```

## 9. Gateway API Integration
If your pattern exposes an HTTP interface, use the Gateway API instead of traditional Ingress.
1. Copy the `gateway.yaml` from `p1-resilient-3-tier-webapp/manifests/apps/`.
2. Ensure you annotate the `Gateway` resource with `networking.gke.io/load-balancer-type: "Internal"` for GCP testing to avoid external IP quota issues.
3. Update the `HTTPRoute` to target your specific frontend service.
