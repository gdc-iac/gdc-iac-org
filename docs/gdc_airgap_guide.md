Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.


# A  Generic Guide to Moving Software Assets to Google Distributed Cloud (GDC)

This guide outlines the standard process for transferring software from an internet-connected development environment to a secure, air-gapped Google Distributed Cloud (GDC) environment.

The core principle in an air-gapped GDC environment is that your GKE user clusters have no access to the public internet. Every container image, Helm chart, and dependency must be made available from within the GDC network, typically from an internal **GDC Managed Harbor registry** (see [Standardized Image Mirroring & Managed Harbor Setup](../tools/mirror-images/README.md)).

The process involves preparing a self-contained "deployment bundle" on a connected machine, transferring it securely, and then publishing the assets to internal GDC services before deployment.

---

## Stage 1: Asset Collection & Preparation (On the Connected System)

On your development machine with internet access, you will gather all assets and, most importantly, re-configure them for the destination GDC environment.

### 1. Identify and Save All Container Images
*   Identify every Docker/OCI image your application uses, including third-party services (e.g., `postgres`, `redis`).
*   Use the standardized [`tools/mirror-images/mirror_images.py`](../tools/mirror-images/README.md) utility to pull and save images from a Kubernetes manifest or image list file into compressed `.tar.gz` archives:
  ```bash
  python3 ./tools/mirror-images/mirror_images.py \
    --manifest <path_to_manifest.yaml> \
    --save-dir ./offline-images
  ```

### 2. Re-configure Kubernetes Manifests & Helm Charts
*   This is the most critical GDC-specific step in the preparation phase. You must edit all your Kubernetes manifests (`Deployment`, `StatefulSet`, `DaemonSet`, etc.) and Helm `values.yaml` files to point to your **future GDC Managed Harbor registry**.
*   For example, change an image reference from this:
    ```yaml
    # Before
    image: "docker.io/library/redis:latest"
    ```
    To this, using your GDC Managed Harbor registry's URL:
    ```yaml
    # After
    image: "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/redis:latest"
    ```
*   **Best Practice:** Automate this process with `./blueprints/common-scripts/configure-blueprints.sh` (or `sed` as shown in [`tools/mirror-images/README.md`](../tools/mirror-images/README.md)) to replace registry URLs across all your manifest files.

### 3. Gather Other Dependencies
*   If your application needs them, download all language-specific packages (e.g., Python wheels, npm packages) or system packages (e.g., `.rpm`, `.deb`). These will need to be hosted on an internal repository within GDC (like Nexus or Artifactory).

---

## Stage 2: Create a Transfer Bundle

Because of the architectural differences between raw Kubernetes vs. Helm charts, consolidating your GDC assets requires a **two-phase** build process to generate your transfer bundle:

### Phase 1: Internal Blueprints (`package-for-gdc.sh`)
**CRITICAL REQUIREMENT:** Before running the packager, you MUST ensure all Kubernetes manifests have been configured with your actual registry URLs so the script can locate and bundle the correct images from your local cache.
```bash
# From the blueprints/ directory, replace placeholders with your actual project and registry
cd blueprints
./common-scripts/configure-blueprints.sh -p $PROJECT_ID -n test-project -r $REGISTRY_HOST
```

First, package the blueprint's native K8s manifests, helper scripts, configuration parameters, and custom application images:

```bash
./common-scripts/package-for-gdc.sh patterns/p1-resilient-3-tier-webapp
```

This will create a `packages/p1-resilient-3-tier-webapp/` directory containing:
* `p1-resilient-3-tier-webapp-gdc-manifests.tar.gz`
* `p1-resilient-3-tier-webapp-gdc-images.tar`
* `configuration_parameters.txt` (recording your namespace, registry, etc.)
* `helper-scripts/` (containing `unpack-for-gdc.sh` and `configure-blueprints.sh`)

### Phase 2: External Dependencies (Helm Charts & Public Images)

To mirror external public images referenced by the blueprint patterns (defined in `external_images.txt` / `bulk_external_images.txt`), use either the standardized [`tools/mirror-images/mirror_images.py`](../tools/mirror-images/README.md) script or the blueprint mirror scripts under `blueprints/common-scripts/`:

```bash
# Standardized Python mirror tool (supports both --save-dir and direct --registry push):
python3 ../tools/mirror-images/mirror_images.py \
  --images-file ./common-scripts/bulk_external_images.txt \
  --save-dir ./packages/external-images

# Or pattern-specific bash mirror script:
./common-scripts/mirror_images.sh ./patterns/p5-hybrid-llm-gateway ./artifacts/vllm-images
```

---

## Stage 3: The Secure Transfer

*   **Mandatory Pre-Transfer Check:** Before transferring, the operator MUST read the generated `*-BOM.txt` (Bill of Materials) file for the pattern. Verify that no critical container images are listed under `MISSING / FAILED`. If any are missing, resolve the error and repackage before proceeding!
*   Move the final transfer bundle (The output `.tar.gz`, `.tar`, `*-BOM.txt`, and `.txt` checksum files from Phase 1, plus the Helm `.tgz` and mirrored image archives from Phase 2) into the GDC environment using your organization's approved secure transfer method (e.g., secure USB, dedicated transfer host).

---

## Stage 4: Unpack & Deploy (On the Air-Gapped GDC System)

Once the bundle is on a workstation within the GDC environment, you will unpack it and publish the assets to the internal GDC services.

### 1. Provision & Authenticate with GDC Managed Harbor
*   Follow **[tools/mirror-images/README.md](../tools/mirror-images/README.md)** to:
    1. Create a GDC Managed Harbor instance (`gdcloud harbor instances create`) or provision it declaratively via `charts/gdc-harbors`.
    2. Create a Harbor Robot Account and authenticate your Docker client:
       ```bash
       docker login -u "${HARBOR_USER:?}" -p "${HARBOR_SECRET:?}" "${REGISTRY:?}"
       ```
    3. Create the Kubernetes `imagePullSecret` in your target cluster namespace and (for Standard Clusters) configure `registryMirrors` TLS trust (`trust-store-root-ext`).

### 2. Verify Transfer Integrity
*   First, use the checksum manifest to verify the integrity of the bundle.
  ```bash
  sha256sum -c p1-resilient-3-tier-webapp-manifest.txt
  ```

### 3. Load Images into Harbor
*   Use the native unpacking script provided in `blueprints/common-scripts/`. This script takes the pattern name as its argument, extracts your packaged Kubernetes manifests, and runs `docker load` to import custom application images into your Workstation's local Docker daemon:
  ```bash
  ./common-scripts/unpack-for-gdc.sh p1-resilient-3-tier-webapp
  ```
*   **Push Custom Images to Harbor**: Because `./common-scripts/configure-blueprints.sh` injected your Harbor URLs during Stage 1, the loaded images are already tagged for your GDC registry:
  ```bash
  ./common-scripts/push-images.sh "${REGISTRY:?}/${HARBOR_PROJECT:?}"
  ```
*   **Load & Push External Dependencies (Phase 2):** Use `tools/mirror-images/mirror_images.py` to load and push all offline 3P image archives in one step:
  ```bash
  python3 ../tools/mirror-images/mirror_images.py \
    --load-dir ./packages/external-images \
    --registry "${REGISTRY:?}/${HARBOR_PROJECT:?}"
  ```

### 4. Deploy to GKE
*   With all custom blueprint images and external dependencies hosted in the GDC Managed Harbor registry, apply the Kubernetes manifests (or deploy via Foundations Stage 3 `patterns.yaml.gotmpl`):
  ```bash
  kubectl apply -f ./patterns/p1-resilient-3-tier-webapp/manifests/apps/
  ```
*   Because the `configure-blueprints.sh` script previously injected the Harbor registry into the raw `.yaml`, the GKE cluster will successfully pull the images from within the air-gapped environment and start your application.
