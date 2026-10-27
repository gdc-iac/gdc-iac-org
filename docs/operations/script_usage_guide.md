Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Unified Script Usage Guide

> **Version:** 1.1

This guide provides detailed instructions on how to use the repository's scripts to manage container images, test deployments, and validate configurations for all GDC Blueprint patterns.

## 1. Overview of Scripts

The `scripts/` directory contains tools grouped into four main functional areas:

1. **Image and Artifact Management (Air-Gap):** Packaging, unpacking, mirroring, and pushing images for GDC deployments.
2. **Emulation and GCP Deployment:** Setting up infrastructure, workload identity, and deploying patterns to local or GCP-emulated clusters.
3. **Testing and Verification:** Validating manifests, running smoke tests, and verifying deployments.
4. **Utilities:** Managing secrets, fixing manifests, and cleaning up resources.

---

## 2. Image and Artifact Management (Air-Gap)

These scripts prepare custom and external dependencies for disconnected GDC environments and publish them to **GDC Managed Harbor** (`gdcloud harbor instances create` / `harbor-projects create`).

### `scripts/stage_production_assets.py` (3-Step Production Staging & `gdc-iac-org` Replication)
Packages 100% self-contained, GDC-ag production-only assets into `deploy-to-production/` while automatically stripping GCP-only staging manifests (`manifests/gcp/`), scripts (`verify-e2e-gcp-staging.py`, `cleanup-e2e-gcp.sh`), and GCP-only tutorials (`quickstart_on_GCP.md`, `ai_enabled_e2e_gcp_staging_guide.md`, `gcp-sandbox-keycloak-testing-strategy.md`, `testing_strategy_gcp_stepping_stone.md`).

* **Single Pattern Re-Staging:**
  ```bash
  python3 scripts/stage_production_assets.py p6-resilient-rag-agent --skip-images
  ```
* **Full 3-Step Replication Pipeline (`gdc_gemma_gw` $\rightarrow$ `GDC-blueprints` $\rightarrow$ `gdc-iac-org`):**
  ```bash
  # Step 1: Stage production assets in gdc_gemma_gw (use ~/GitHub/... on Cloud Workstation or ~/src/... on Cloudtop)
  cd ~/GitHub/gdc_gemma_gw
  python3 scripts/stage_production_assets.py all --skip-images

  # Step 2: Stage all patterns + sync external gdc_gemma_gw in GDC-blueprints
  cd ~/GitHub/GDC-blueprints
  python3 scripts/stage_production_assets.py all --skip-images --sync-external-gemma-gw

  # Step 3: Replicate strictly production-only assets into gdc-iac-org/blueprints/
  rsync -av --delete --exclude='README.md' \
    ~/GitHub/GDC-blueprints/deploy-to-production/ \
    ~/GitHub/gdc-iac-org/blueprints/
  ```

### `scripts/mirror_images.py` (Standardized Image Mirroring)
* **Direct Connected Bastion Usage:**
  ```bash
  ./scripts/mirror_images.py --manifest <manifest.yaml> --registry <harbor-url>/<project>
  ./scripts/mirror_images.py --images-file deploy-to-production/bulk_external_images.txt --registry <harbor-url>/<project>
  ```
* **Two-Step Disconnected Air-Gap Usage:**
  ```bash
  # Step 1 (Low-Side): Pull and export compressed .tar.gz archives
  ./scripts/mirror_images.py --images-file deploy-to-production/bulk_external_images.txt --save-dir /tmp/offline-images

  # Step 2 (High-Side): Load archives and push to GDC Managed Harbor
  ./scripts/mirror_images.py --load-dir /tmp/offline-images --registry <harbor-url>/<project>
  ```

### `configure-blueprints.sh`
* **Usage:** `./configure-blueprints.sh -p <project-id> -n <namespace> -r <registry-url>`
* **CRITICAL:** Run this script *before* `package-for-gdc.sh`. It injects your actual registry URLs into the raw manifests so the packager knows exactly where to find your locally built images.
* **⚠️ WARNING FOR VALIDATION TESTS:** If you omit the `-n` flag, the script will permanently override the `NAMESPACE` variable inside the repository's validation scripts (`verify.sh`) from `test-project` to `<project-id>`, failing any future local emulation tests. Always use `-n test-project` for simple air-gap staging!

### `package-for-gdc.sh` & `unpack-for-gdc.sh`
Used to manage custom application images that you build.
* **`package-for-gdc.sh <pattern-directory>`:** Parses Kubernetes manifests, verifies required custom images exist locally, and packages them alongside manifests into a dedicated `packages/<pattern-name>` folder containing tarballs (`-gdc-manifests.tar.gz` and `-gdc-images.tar`), parameters, and helper scripts. Optionally accepts `--skip-vllm` flag.
* **`unpack-for-gdc.sh <pattern-name>`:** Bundled inside the package `helper-scripts/` directory. Run on the air-gapped machine to extract manifests and load images into the local Docker daemon.

### `push-images.sh`
* **Usage:** `./scripts/push-images.sh <registry-url-prefix> [--dry-run]`
* Used after unpacking to push the loaded application images to the internal GDC Managed Harbor registry.

### `mirror_images.sh`
* **Usage:** `./scripts/mirror_images.sh <PATTERN_DIRECTORY> <OUTPUT_DIRECTORY>`
* Pulls external public images (defined in a pattern's `external_images.txt`) and archives them as `.tar` files while preserving pinned version tags. Supports exporting a `SKIP_IMAGES` regex to skip large images (e.g. `export SKIP_IMAGES="vllm"`).

### `bulk_mirror_images.sh`
* Underlying bulk image mirror script. Called by `export-external-dependencies.sh` to grab all referenced public Docker images across the repository, saving them into their respective `packages/<pattern-name>/external-dependencies/images` folders.

### `export-external-dependencies.sh`
* **Usage:** `./scripts/export-external-dependencies.sh`
* Consolidates external dependency gathering. Automatically pulls needed Helm charts and runs `bulk_mirror_images.sh` to grab all public images for all patterns, placing them directly into pattern-specific `packages/<pattern>/external-dependencies` folders. Note: Massive images like `vLLM` are explicitly hard-skipped by this script.

### `bulk-package-all.sh`
* **Usage:** `./scripts/bulk-package-all.sh`
* High-level automation script that iterates through all recognized blueprint patterns. It invokes dependency exports, and runs the individual `package-for-gdc.sh` script to cleanly package all blueprints into the `packages/` directory at once.

### Managing Helm Charts
Some patterns (P4, P5, P8) require external Helm charts. The `export-external-dependencies.sh` script automates downloading their `.tgz` archives. 
Once transferred to an air-gapped environment, install using:
```bash
helm install my-release ./<CHART_NAME>-<VERSION>.tgz
```

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
