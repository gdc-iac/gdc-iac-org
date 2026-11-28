<!--
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Example Custom Job Worker (`inventory-audit-report`)

This folder provides a minimal, runnable template showing how an **Application Operator (`AO`)** or platform team packages custom Python business logic onto Pattern 15's orchestrator-agnostic runner contract (`gdc-standard-job-runner-v1`), running identically across **Profile B (`k8s-native`)** and **Profile A (`argo`)**.

## How This Script Enters the Orchestrator

Pattern 15 never accepts raw script uploads or arbitrary `PodSpec` overrides on `:8080`. Your custom script enters the orchestrator strictly by **container image reference**:

```text
p15_jobs/runner.py  -->  Dockerfile (USER 65532:65532)  -->  Allowlisted Registry  -->  Portal (:8080)
(--mode contract)        ENTRYPOINT python3 -m               p15-example-inventory     Bind Pinned Worker Image
                         p15_jobs.runner                     -job:v1.0.0               + --mode inventory-audit-report
```

## Files

- [`p15_jobs/runner.py`](./p15_jobs/runner.py): Implements `--mode inventory-audit-report`, live Kubernetes `Service` discovery via the pod's attached ServiceAccount token (`p15-ao-worker-sa`, falling back cleanly to a local fixture outside a cluster), WAL-first Object Storage persistence (`DualModeStorageAdapter`), automatic secret scrubbing (`[REDACTED_TOKEN]`), and exit code `2` non-retryable configuration validation.
- [`Dockerfile`](./Dockerfile): Multi-stage, Pod Security `Restricted` (`USER 65532:65532`, read-only root filesystem) container packaging `p15_jobs/` and shared `example-app/common/`.
- [`requirements.txt`](./requirements.txt): Pinned Python dependencies (`0` `HIGH`/`CRITICAL` CVEs).

## Quick Local Smoke Test

Run directly from the repository root (`GDC-blueprints/`) to verify both the happy path (`exit 0` + `[REDACTED_TOKEN]`) and the non-retryable guardrail (`exit 2`):

```bash
# 1. Happy path -> writes redacted /tmp/job-out/result.json
PYTHONPATH=p15-job-orchestrator/examples/custom-job-inventory:p15-job-orchestrator/example-app \
  python3 -m p15_jobs.runner \
    --mode inventory-audit-report \
    --job-id ao-inventory-audit-15m \
    --run-id local-smoke-01 \
    --shard-key shard-00 \
    --output-file /tmp/job-out/result.json
grep -q '\[REDACTED_TOKEN\]' /tmp/job-out/result.json && echo "REDACTION_VERIFIED"

# 2. Invalid --mode -> exits immediately with code 2 (stops futile retries)
PYTHONPATH=p15-job-orchestrator/examples/custom-job-inventory:p15-job-orchestrator/example-app \
  python3 -m p15_jobs.runner \
    --mode invalid-mode \
    --job-id ao-inventory-audit-15m \
    --run-id local-smoke-02; echo "Exit code: $?"
```

## Build, Scan & Register

Build from the `p15-job-orchestrator/` root so `example-app/common` is copied into the image:

```bash
export REGISTRY_HOST="harbor.gdc.local/blueprint-images"

docker build --platform linux/amd64 \
  -f p15-job-orchestrator/examples/custom-job-inventory/Dockerfile \
  -t "${REGISTRY_HOST}/p15-example-inventory-job:v1.0.0" \
  p15-job-orchestrator

trivy image --severity HIGH,CRITICAL --ignore-unfixed \
  "${REGISTRY_HOST}/p15-example-inventory-job:v1.0.0"

docker push "${REGISTRY_HOST}/p15-example-inventory-job:v1.0.0"
```

## Full Walkthrough

- **Air-Gapped GDC-ag Production Walkthrough:** Section 4.1 of [`../../docs/user-guide.md`](../../docs/user-guide.md)
