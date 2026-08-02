Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Pattern 8: Closed-Loop MLOps

**Use Case:** Automated model retraining upon drift detection in GDC-ag environments.

## Architecture Schematic

```
+----------------------+      +----------------------+
| Prometheus           |----->| Alertmanager         |
| (Drift Detection)    |      | (Webhook Trigger)    |
+----------------------+      +----------------------+
                                         |
                                         v
+----------------------+      +----------------------+
| CI/CD System         |----->| Training Script      |
| (e.g., GitLab CI)    |      | (e.g., train.py)     |
+----------------------+      +----------------------+
         |                             |
         | (Triggers Canary)           v
         v                    +----------------------+
+----------------------+      | GDC Storage (Object) |
| Argo Rollouts        |      | (New Model Version)  |
+----------------------+      +----------------------+
         |
         v
+----------------------+
| GKE Model Serving    |
| (Canary Deployment)  |
+----------------------+
```

**Sizing Recommendation:** For GKE node pools, use `n2-standard-4-gdc` for general purpose or `a3-highgpu-1g-gdc` for GPU-accelerated model serving.

## Design & Resilience Strategy

This pattern establishes a closed-loop MLOps process to automatically retrain and redeploy a machine learning model when its performance degrades in production.

1.  **Monitoring & Alerting:**
    *   **OSS Components:** A **Prometheus** stack is deployed to the GKE cluster to scrape performance metrics from the model serving endpoint.
    *   **Drift Detection:** An alert is configured in **Alertmanager** (part of the Prometheus stack) to fire when a key metric (e.g., prediction accuracy, latency, or data drift) crosses a predefined threshold.
    *   **Trigger:** Alertmanager is configured to send a webhook to an external system (the CI/CD platform) when the "ModelDrift" alert is firing.

2.  **Automated Retraining Pipeline:**
    *   **CI/CD System:** A platform like **GitLab CI** receives the webhook from Alertmanager, triggering a new pipeline job.
    *   **Retraining Job:** The pipeline executes a script that:
        1.  Pulls the latest training data (e.g., using DVC from GDC Storage).
        2.  Runs the model training process to create a new model version.
        3.  Pushes the new model artifacts back to a model registry or GDC Storage.

3.  **Automated Canary Deployment:**
    *   **OSS Component:** **Argo Rollouts** is used to manage the deployment of the model serving application on GKE.
    *   **Progressive Delivery:** The CI/CD pipeline, after the retraining job succeeds, triggers Argo Rollouts to start a canary deployment. It updates the model serving deployment to use the new model container image.
    *   **Analysis & Rollback:** Argo Rollouts gradually shifts traffic to the new version while querying Prometheus for performance metrics. If the new model performs well, it is fully rolled out. If it fails the analysis, Argo Rollouts automatically rolls back to the previous stable version.

## Day 0 Prerequisites (Air-Gap Transfer)

Before deploying this pattern to a GDC air-gapped environment, the following artifacts must be transferred:
1.  **Container Images:** The Prometheus and Argo Rollouts images, along with the model serving and training job images, must be pushed to the internal GDC registry (Harbor).
2.  **Helm Charts:** The `kube-prometheus-stack` and `argo-rollouts` Helm charts must be downloaded and transferred.
3.  **Configuration:** The Kubernetes manifests, CI/CD pipeline scripts, and any helper scripts must be packaged and transferred.
4.  **Transfer Process:** Use the provided `scripts/package-for-gdc.sh` to create the necessary transfer bundles (manifests, helper scripts, and tarballs into a dedicated `packages/` directory).

## Resource Requirements (T-Shirt Sizes)

**Estimated Capacity:** N/A (Batch/Pipeline). Supports 1 concurrent training job.

| Component | Recommended GDC Machine Type | vCPU | RAM | Storage (PVC) | GPU Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Model Serving** | `n2-standard-4-gdc` (or `a2-highgpu-1g`) | 4 | 16Gi | N/A | Optional |
| **Training Job** | `n2-standard-8-gdc` (or `a2-highgpu-1g`) | 8 | 32Gi | N/A | Optional |
| **MLOps Tools** | `n2-standard-4-gdc` | 4 | 16Gi | 50Gi (Prometheus) | No |

**Scaling & Upgrades:**
*   **Training:** If training times are too long (>4 hours), upgrade the training job node pool to use GPUs (`a2-highgpu-1g`) or distributed training (requires code changes).
*   **Serving:** Use HPA (or KEDA) to scale the serving pods based on request volume.
*   **Prometheus:** Monitor PVC usage for metrics storage. Resize if usage exceeds 70%.

**Sizing Rationale:**
Training jobs are batch processes that benefit from high core counts and memory to reduce execution time. Serving sizing balances cost with inference latency.

## Configuration

Before deploying, ensure you have configured the blueprints with your Project ID and Registry URL:

```bash
# Run from the root of the repository
./configure-blueprints.sh -p <YOUR_PROJECT_ID> -r <YOUR_REGISTRY_URL> -d p8-closed-loop-mlops
```

## Required IAM Permissions

This pattern involves cluster-wide tooling and a CI/CD pipeline, requiring distinct, high-privilege roles.

**1. User Permissions (for Toolchain Setup):**
To deploy cluster-wide tools like Prometheus and Argo Rollouts, your user account will need administrative permissions on the GKE cluster:

*   **GKE Cluster Admin:** To install Helm charts that create Custom Resource Definitions (CRDs) and manage resources across all namespaces.
    *   `roles/gke.clusterAdmin`

**2. CI/CD Pipeline Permissions:**
The service principal or service account used by your CI/CD system (e.g., GitLab) will need the following roles to execute the retraining pipeline:

*   **Storage Reader:** To pull the latest training data.
    *   `roles/storage.objectViewer`
*   **Storage Writer:** To push newly trained model artifacts.
    *   `roles/storage.objectCreator`
*   **GKE Developer:** To trigger the Argo Rollouts canary deployment by updating the image.
    *   `roles/gke.developer`

## Implementation

### Step 1: Deploy Toolchain

**Option A: Manual (Helm)**

```bash
export REGISTRY_HOST=<YOUR_REGISTRY_URL>

helm install prometheus oci://$REGISTRY_HOST/charts/kube-prometheus-stack -n monitoring --create-namespace
helm install argo-rollouts oci://$REGISTRY_HOST/charts/argo-rollouts -n argo-rollouts --create-namespace
```

**Option B: GitOps**

Deploying stateful, cluster-wide tools like Prometheus and Argo Rollouts via GitOps can be complex. For this pattern, the manual Helm-based installation is the recommended starting point.

### Step 2: Configure Pipeline Trigger

Add this job to your internal CI/CD system (e.g., GitLab CI) to close the loop. This job should be configured to run only when triggered by an API call, which would be initiated by the Alertmanager webhook.

*.gitlab-ci.yml snippet:*

```yaml
retrain_on_drift:
  stage: retrain
  # This job is triggered via API call from Prometheus Alertmanager
  only:
    variables:
      - $TRIGGER_SOURCE == "alertmanager"
  script:
    # 1. Pull data
    - dvc pull gs://ml-data/latest.dvc
    # 2. Retrain & Push artifacts
    - python train.py
    - gdcloud storage cp new_model.pb gs://models/vNext/
    # 3. Trigger Canary Deployment
    - kubectl argo rollouts set image model-serving container=harbor.gdc.local/model:vNext
```

## Testing


### Standard Testing
The `validate.sh` script checks for the existence of the CI/CD snippet file, as this pattern does not contain standard Kubernetes manifests for validation.

To run the validation:
```bash
cd test/
chmod +x validate.sh
./validate.sh
```

### Verification (Post-deployment)

The `verify.sh` script checks that the Helm releases for the MLOps toolchain (Prometheus, Argo Rollouts) were deployed successfully. This script should be run **after** you have deployed the toolchain.

To run the verification:
```bash
cd test/
chmod +x verify.sh
./verify.sh
```

### Local Testing

You can run the validation and verification scripts locally using the provided test runner, which mocks the GDC and Kubernetes CLI commands.

```bash
# Run from the root of the repository
bash tests/run-local.sh
```

This will run the configuration tests and the verification logic for all patterns.
## Packaging for GDC Air-Gapped Environments

To deploy this pattern to a GDC air-gapped environment, you must first package the required artifacts (manifests, scripts, and container images) into transferrable archives.

### 1. Configure the Blueprint (Pre-requisite)
**CRITICAL DESTINATION VARIABLES:** The variables below must point specifically to your **destination** GDC air-gapped environment. For instance, the `PROJECT_ID` must be the exact name of the project inside the disconnected GDC environment where this blueprint will run—**NOT** the project on your connected packaging workstation. The scripts physically hardcode these target IDs right into the yaml manifests before they are compressed.

```bash
export PROJECT_ID="<YOUR_TARGET_PROJECT_ID>"
export NAMESPACE="<YOUR_TARGET_NAMESPACE>"
export REGISTRY_HOST="<YOUR_TARGET_REGISTRY_HOST>" # e.g. harbor.gdc.local/library

# Run from the root of the repository
./configure-blueprints.sh -p ${PROJECT_ID} -n ${NAMESPACE} -r ${REGISTRY_HOST} -d p8-closed-loop-mlops
```

### 2. Execute the Pipeline
Run the external dependencies script first (to fetch necessary Helm charts and global images), and then run the primary packaging script for this specific pattern:

```bash
# 1. Gather global external dependencies into the artifacts/ directory
./scripts/export-external-dependencies.sh

# 2. Package all localized manifests and containers for this pattern
./scripts/package-for-gdc.sh p8-closed-loop-mlops
```

### 3. Transfer Artifacts
Ensure you transfer **all** of the following exact items to your air-gapped environment using your secure mechanism (e.g., data diode or secure USB):

*   **Pattern-Specific Archives (Generated in the repository root):**
    *   `p8-closed-loop-mlops-gdc-manifests.tar.gz` (The localized k8s manifests)
    *   `p8-closed-loop-mlops-gdc-images.tar` (The bundled container images)
    *   `p8-closed-loop-mlops-BOM.txt` and `p8-closed-loop-mlops-manifest.txt` (Integrity checksums)
    *   `p8-closed-loop-mlops-README.md` (Standalone deployment instructions)

*(Note: Unlike the infrastructure-heavy patterns, this robust pattern does not strictly require complex 3rd-party external Helm charts or images dropped into the `artifacts/` pool via the dependencies script—it is cleanly self-contained in the 3 standard `.tar` / `.txt` files above).*
### 4. Unpack and Deploy
Once transferred to your secure GDC environment, you must unpack and deploy the assets logically:

> **Optional: Hot-Patching Manifests Offline**
> If you need to deploy this pattern to a *different* namespace, project ID, or registry host than the one you originally injected during the pre-packaging step, you do not need to resend the payload across the air-gap. You can dynamically hot-patch the extracted manifests locally:
> ```bash
> # Define your old (packaged) and new (target) variables
> OLD_PROJECT="<PACKAGED_PROJECT_ID>"
> NEW_PROJECT="<NEW_PROJECT_ID>"
> OLD_NAMESPACE="<PACKAGED_NAMESPACE>"
> NEW_NAMESPACE="<NEW_NAMESPACE>"
> OLD_REGISTRY="<PACKAGED_REGISTRY_HOST>"
> NEW_REGISTRY="<NEW_REGISTRY_HOST>"
> 
> # Recursively execute string replacement across all extracted YAML files
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_PROJECT}|${NEW_PROJECT}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_NAMESPACE}|${NEW_NAMESPACE}|g" {} +
> find ./gdc-manifests/ -type f -name "*.yaml" -exec sed -i "s|${OLD_REGISTRY}|${NEW_REGISTRY}|g" {} +
> ```


1. **Authenticate Docker with Harbor:** Log in to your target GDC environment's Harbor registry:
   ```bash
   export REGISTRY_HOST="harbor.gdc.local"
   export ROBOT_NAME="robot\$puller"  # Escape the $ character
   export ROBOT_SECRET="your-robot-secret"

   docker login ${REGISTRY_HOST} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
   ```

2. **Load and Push Local Container Images:** Extrapolate the locally-built images into your secure internal registry:
   ```bash
   ./scripts/unpack-for-gdc.sh p8-closed-loop-mlops-gdc-images.tar harbor.gdc.local/library
   ```

3. **Load and Push Global Container Images (If Applicable):** For blueprints bridging global components (e.g. Hashicorp Vault, external pipelines), manually load and tag the artifacts using standard Docker commands:
   ```bash
   docker load -i artifacts/external-dependencies/images/...
   docker tag ... harbor.gdc.local/library/...
   docker push ...
   ```

4. **Extract and Apply Kubernetes Manifests:** Extract the exact blueprints generated during the `-d` inject step and apply them to your cluster:
   ```bash
   mkdir -p ./gdc-manifests
   tar -xzf p8-closed-loop-mlops-gdc-manifests.tar.gz -C ./gdc-manifests/
   kubectl apply -f ./gdc-manifests/
   ```

5. **Deploy Helm Charts (If Applicable):** Unpack any required software suites from `artifacts/external-dependencies/charts/` using `--untar` and `helm install` them securely referencing your internal registry.
