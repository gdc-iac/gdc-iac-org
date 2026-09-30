Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Unified Script Usage Guide

> **Version:** 1.1

This guide provides detailed instructions on how to use the repository's scripts to manage container images, test deployments, and validate configurations for all GDC Blueprint patterns.

## 1. Overview of Scripts

Container image mirroring and blueprint management scripts are organized across:
* **[`tools/mirror-images/`](../tools/mirror-images/README.md):** Standardized Python utility (`mirror_images.py`) and Managed Harbor setup guide for mirroring images from Kubernetes manifests or image lists (`--manifest`, `--images-file`, `--save-dir`, `--load-dir`, `--registry`).
* **`blueprints/common-scripts/`:** Blueprint packaging, unpacking, parameter configuration, and custom application image build/push helpers.
* **`scripts/`:** Repository-level OCI Helm chart air-gap bundle ingestion (`ingest-airgap-bundle.sh`), chart validation (`test-charts.sh`), and schema generation.

---

## 2. Image and Artifact Management (Air-Gap)

These scripts prepare custom and external dependencies for disconnected GDC environments. For GDC Managed Harbor provisioning (`gdcloud harbor`), Robot Account setup, `imagePullSecrets`, and Standard Cluster `registryMirrors` TLS trust, see **[tools/mirror-images/README.md](../tools/mirror-images/README.md)**.

### `tools/mirror-images/mirror_images.py` (Standardized Image Mirroring)
* **Direct Connected Bastion Usage:**
  ```bash
  ./tools/mirror-images/mirror_images.py --manifest <manifest.yaml> --registry <harbor-url>/<project>
  ./tools/mirror-images/mirror_images.py --images-file blueprints/common-scripts/bulk_external_images.txt --registry <harbor-url>/<project>
  ```
* **Two-Step Disconnected Air-Gap Usage:**
  ```bash
  # Step 1 (Low-Side): Pull and export compressed .tar.gz archives
  ./tools/mirror-images/mirror_images.py --images-file blueprints/common-scripts/bulk_external_images.txt --save-dir /tmp/offline-images

  # Step 2 (High-Side): Load archives and push to GDC Managed Harbor
  ./tools/mirror-images/mirror_images.py --load-dir /tmp/offline-images --registry <harbor-url>/<project>
  ```

### `blueprints/common-scripts/configure-blueprints.sh`
* **Usage:** `./blueprints/common-scripts/configure-blueprints.sh -p <project-id> -n <namespace> -r <registry-url>`
* **CRITICAL:** Run this script *before* `package-for-gdc.sh`. It injects your actual registry URLs into the raw manifests so the packager knows exactly where to find your locally built images.
* **⚠️ WARNING FOR VALIDATION TESTS:** If you omit the `-n` flag, the script will permanently override the `NAMESPACE` variable inside the repository's validation scripts (`verify.sh`) from `test-project` to `<project-id>`, failing any future local emulation tests. Always use `-n test-project` for simple air-gap staging!

### `blueprints/common-scripts/package-for-gdc.sh` & `unpack-for-gdc.sh`
Used to manage custom application images that you build.
* **`./blueprints/common-scripts/package-for-gdc.sh <pattern-directory>`:** Parses Kubernetes manifests, verifies required custom images exist locally, and packages them alongside manifests into a dedicated `packages/<pattern-name>` folder containing tarballs (`-gdc-manifests.tar.gz` and `-gdc-images.tar`), parameters, and helper scripts. Optionally accepts `--skip-vllm` flag.
* **`./blueprints/common-scripts/unpack-for-gdc.sh <pattern-name>`:** Bundled inside the package `helper-scripts/` directory. Run on the air-gapped machine to extract manifests and load images into the local Docker daemon.

### `blueprints/common-scripts/push-images.sh`
* **Usage:** `./blueprints/common-scripts/push-images.sh <registry-url-prefix> [--dry-run]`
* Used after unpacking to build/push custom blueprint application images (`p1-frontend`, `p1-backend`, etc.) to the internal GDC Harbor registry.

### `blueprints/common-scripts/mirror_images.sh` & `bulk_mirror_images.sh`
* **Usage:** `./blueprints/common-scripts/mirror_images.sh <PATTERN_DIRECTORY> <OUTPUT_DIRECTORY>`
* Pulls external public images (defined in a pattern's `external_images.txt` or `bulk_external_images.txt`) and archives them as `.tar` files. Supports exporting a `SKIP_IMAGES` regex to skip large images (e.g. `export SKIP_IMAGES="vllm"`).

### `scripts/ingest-airgap-bundle.sh`
* **Usage:** `./scripts/ingest-airgap-bundle.sh --registry <harbor-host> --project <project>`
* Verifies `SHA256SUMS` and pushes packaged OCI Helm charts (`*.tgz`) into GDC Harbor (see [foundations/AIRGAP_MIRRORING.md](../foundations/AIRGAP_MIRRORING.md)).

---

## 3. Emulation and GCP Deployment

These scripts help emulate the GDC environment on Google Cloud Platform (GCP) or locally.

### Infrastructure Setup
* **`create_cluster.sh`:** Creates a GKE Cluster for emulation testing, configuring necessary APIs, network, and IAM integrations.
* **`setup-gcp-resources.sh`:** Sets up GCP emulation resources like creating specific Cloud Storage buckets.
* **`configure-workload-identity.sh`:** Configures Workload Identity for a GKE cluster (binds Kubernetes Service Accounts to GCP Service Accounts).

### Deployment
* **`deploy-all-mocked.sh`:** Deploys all patterns to a local Kubernetes environment using mocked services (e.g., local Postgres StatefulSets instead of Cloud SQL).
* **`deploy-emulation-gcp.sh`:** Deploys all patterns using emulated GCP services configured specifically for the target project.
* **`deploy-gcp-mocked.sh <pattern-directory>`:** Deploys a specific, single pattern to GCP GKE using mocked services.
* **`deploy-p6.sh`:** Specific script to configure secrets and deploy Pattern 6 (Resilient RAG Agent) manifests.

---

## 4. Testing and Verification

Used to ensure manifests are valid and applications operate correctly.

* **`stage1-local-test.sh`:** Builds basic images locally and is mainly used as an early Stage 1 verification.
* **`validate-manifests.sh`:** Performs bulk manifest validation against an active Kubernetes cluster, catching syntax or configuration errors before deployment.
* **`verify-all-emulation.sh`:** Iterates through all deployed patterns in an emulation environment to ensure pods are running and services are bound.
* **`verify-functionality.sh`:** Executes functional smoke tests (e.g., `curl` endpoints) for deployed patterns to ensure actual business logic is operational.

---

## 5. Utilities

Helper scripts for configuration and clean-up.

* **`create-secrets.sh`:** Automates the creation of generic Kubernetes secrets (like DB passwords) into the required namespace.
* **`fix-manifests.sh <registry-url-prefix>`:** Updates image registry URLs inside pattern manifests (especially Pattern 6) to point to a specific repository.

---

## 6. Cleaning Up

Scripts to remove unneeded artifacts and infrastructure.

* **`cleanup-local-images.sh`:** Removes all local Docker images tagged with blueprint prefixes (e.g., `p1-`, `p2-`) to clear workspace disk space.
* **`cleanup-gcp.sh`:** Tears down GCP resources and buckets that were provisioned by the emulation and setup scripts.
