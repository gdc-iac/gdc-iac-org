Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.


# A  Generic Guide to Moving Software Assets to Google Distributed Cloud (GDC)

This guide outlines the standard process for transferring software from an internet-connected development environment to a secure, air-gapped Google Distributed Cloud (GDC) environment.

The core principle in an air-gapped GDC environment is that your GKE user clusters have no access to the public internet. Every container image, Helm chart, and dependency must be made available from within the GDC network, typically from an internal **Harbor registry**.

The process involves preparing a self-contained "deployment bundle" on a connected machine, transferring it securely, and then publishing the assets to internal GDC services before deployment.

---

## Stage 1: Asset Collection & Preparation (On the Connected System)

On your development machine with internet access, you will gather all assets and, most importantly, re-configure them for the destination GDC environment.

### 1. Identify and Save All Container Images
*   Identify every Docker/OCI image your application uses, including third-party services (e.g., `postgres`, `redis`).
*   Save each image to a tarball using `docker save`.
  ```bash
  docker save my-app:1.2.3 -o my-app.tar
  docker save redis:latest -o redis.tar
  ```

### 2. Re-configure Kubernetes Manifests & Helm Charts
*   This is the most critical GDC-specific step in the preparation phase. You must edit all your Kubernetes manifests (`Deployment`, `StatefulSet`, `DaemonSet`, etc.) and Helm `values.yaml` files to point to your **future GDC Harbor registry**.
*   For example, change an image reference from this:
    ```yaml
    # Before
    image: "docker.io/library/redis:latest"
    ```
    To this, using your GDC Harbor registry's URL:
    ```yaml
    # After
    image: "harbor.gdc.local/my-project/redis:latest"
    ```
*   **Best Practice:** Automate this process with a script that replaces registry URLs across all your manifest files. This prevents manual errors and makes it easy to target different environments.

### 3. Gather Other Dependencies
*   If your application needs them, download all language-specific packages (e.g., Python wheels, npm packages) or system packages (e.g., `.rpm`, `.deb`). These will need to be hosted on an internal repository within GDC (like Nexus or Artifactory).

---

## Stage 2: Create a Transfer Bundle

Because of the architectural differences between raw Kubernetes vs. Helm charts, consolidating your GDC assets requires a **two-phase** build process to generate your transfer bundle:

### Phase 1: Internal Blueprints (`package-for-gdc.sh`)
**CRITICAL REQUIREMENT:** Before running the packager, you MUST ensure all Kubernetes manifests have been configured with your actual registry URLs so the script can locate and bundle the correct images from your local cache.
```bash
# From the root of the repository, replace placeholders with your actual project and registry
./configure-blueprints.sh -p $PROJECT_ID -n test-project -r $REGISTRY_HOST

First, package the blueprint's native K8s manifests, helper scripts, configuration parameters, and custom application images. Run the script from the root of this repository:

```bash
./scripts/package-for-gdc.sh p1-resilient-3-tier-webapp
```

This will create a `packages/p1-resilient-3-tier-webapp/` directory containing:
* `p1-resilient-3-tier-webapp-gdc-manifests.tar.gz`
* `p1-resilient-3-tier-webapp-gdc-images.tar`
* `configuration_parameters.txt` (recording your namespace, registry, etc.)
* `helper-scripts/` (containing `unpack-for-gdc.sh` and `configure-blueprints.sh`)

### Phase 2: External Dependencies (Helm Charts & Public Images)

If a pattern relies on heavy remote Helm charts (e.g., Ollama or Kafka), the `package-for-gdc.sh` script intentionally skips them because they are not hardcoded in your local `.yaml` files. You must package these external dependencies using the dedicated export script:

```bash
./scripts/export-external-dependencies.sh
```

This deposits the relevant artifacts directly into individual pattern output folders (e.g., `packages/p4-event-driven-kafka/external-dependencies/`).

*Note: Due to its massive size (15GB+), the `vLLM` model image is deliberately skipped by this automated script. If your architecture specifically requires it, you must mirror it manually:*
`./scripts/mirror_images.sh ./p5-hybrid-llm-gateway ./artifacts/vllm-images`

---

## Stage 3: The Secure Transfer

*   **Mandatory Pre-Transfer Check:** Before transferring, the operator MUST read the generated `*-BOM.txt` (Bill of Materials) file for the pattern. Verify that no critical container images are listed under `MISSING / FAILED`. If any are missing, resolve the error and repackage before proceeding!
*   Move the final transfer bundle (The output `.tar.gz`, `.tar`, `*-BOM.txt`, and `.txt` checksum files from Phase 1, plus the Helm `.tgz` and mirrored `.tar`s from Phase 2) into the GDC environment using your organization's approved secure transfer method (e.g., secure USB, dedicated transfer host).

---

## Stage 4: Unpack & Deploy (On the Air-Gapped GDC System)

Once the bundle is on a workstation within the GDC environment, you will unpack it and publish the assets to the internal GDC services.

### 1. Authenticate
*   Log in to your GDC environment using the `gdcloud` CLI.
*   Authenticate your Docker client with the GDC Harbor registry.
  ```bash
  # Example login command
  docker login harbor.gdc.local
  ```

### 2. Verify Transfer Integrity
*   First, use the checksum manifest to verify the integrity of the bundle.
  ```bash
  sha256sum -c p1-resilient-3-tier-webapp-manifest.txt
  ```

### 3. Load Images into Harbor
*   Use the native unpacking script provided in the blueprints. This script takes the pattern name (not the file name) as its argument. It will automatically extract your packaged Kubernetes manifests into a folder and use `docker load` to import the custom application images into your Workstation's local Docker daemon.
  ```bash
  # Automatically extracts manifests and runs 'docker load'
  ./scripts/unpack-for-gdc.sh p1-resilient-3-tier-webapp
  ```
  *(Note for P5 Hybrid LLM Gateway: Because the massive 5GB+ Gemma AI model is natively "baked" into a custom Docker image and captured by the Phase 1 packaging loop, this single `unpack-for-gdc.sh` command will perfectly extract and load those heavy AI weights into your daemon alongside the lightweight gateway app!)*

*   **Push to Harbor**: The `unpack-for-gdc.sh` script **does not automatically push** images. Because your workstation previously ran `./configure-blueprints.sh` to inject your Harbour URLs during Stage 1, the loaded images *should* already be tagged correctly for your GDC registry. You must now push them manually:
  ```bash
  docker push harbor.gdc.local/library/p1-backend:latest
  docker push harbor.gdc.local/library/p1-frontend:latest
  ```

*   **External Dependencies (Phase 2):** You must manually `docker load -i <file.tar>` any heavy external dependencies mirrored into the `artifacts/external-dependencies/images` folder, tag them for your Harbor registry, push them, and then use `helm install` to deploy the raw `.tgz` charts (like Ollama or Kafka).

### 4. Deploy to GKE
*   With all your custom blueprint images and heavy external helm dependencies now hosted in the GDC Harbor registry, you can finally deploy your resilient architecture.
*   Apply the re-configured Kubernetes manifests to your target GKE user cluster.
  ```bash
  kubectl apply -f ./p1-resilient-3-tier-webapp/manifests/apps/
  ```
*   Because the `configure-blueprints.sh` script previously injected the Harbor registry into the raw `.yaml`, the GKE cluster will successfully pull the images from within the air-gapped environment and start your application.
