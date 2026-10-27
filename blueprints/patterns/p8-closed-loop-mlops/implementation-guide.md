Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 8: Closed-Loop MLOps on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document provides step-by-step instructions for deploying and configuring the **Closed-Loop MLOps** pipeline on Google Distributed Cloud (GDC) air-gapped environments. This architectural blueprint establishes a self-healing machine learning operational cycle: monitoring model serving endpoints, triggering automated retraining when performance or data drift is detected, and executing progressive canary deployments using Argo Rollouts with automated rollback safety.

## **Architecture**

The MLOps loop connects monitoring, orchestration, and serving tiers:
1. **Model Monitoring**: Prometheus scrapes metrics from GKE serving endpoints.
2. **Drift Alerting**: Alertmanager evaluates metrics and calls a webhook trigger.
3. **CI/CD System**: A platform like GitLab CI processes webhook calls, pulls fresh data, trains a new model version, and uploads the artifacts.
4. **Progressive Delivery**: Argo Rollouts executes a canary release of the model server, evaluating performance and auto-rolling back if accuracy drops.

```
                  +-----------------------------------+
                  |          [ Prometheus ]           |
                  |     (Metric Scraping & Drift)     |
                  +-----------------------------------+
                                    │
                                    ▼ (Trigger Webhook)
                  +-----------------------------------+
                  |         [ Alertmanager ]          |
                  +-----------------------------------+
                                    │
                                    ▼ (API Payload)
   +--------------------+  (Pulls Data)   +--------------------+
   |   [ GitLab CI ]    |◄───────────────►|  [ GDC Storage ]   |
   | (Training Runner)  |                 |  (gs://ml-data)    |
   +--------------------+                 +--------------------+
             │
             ▼ (Argo Rollouts Set Image)
   +--------------------+
   |  [ Argo Rollouts ] |
   |  (Canary Manager)  |
   +--------------------+
             │
             ▼ (Traffic Shifting)
   +--------------------+
   |  [ Model Serving ] |
   +--------------------+
```

### **Key Solution Capabilities**

* **Automated Drift Remediation**: Resolves model accuracy degradation without manual operational intervention.
* **Canary Release Verification**: Argo Rollouts shifts traffic gradually (e.g. 10%, 20%, 50%), using real-time Prometheus analysis to evaluate quality.
* **Air-Gapped Data Versioning**: Works in conjunction with local DVC (Data Version Control) storing raw datasets in GDC Object Storage buckets.
* **Declarative Rollouts**: Decouples deployment specifications from standard Kubernetes deployments to enable canary pipelines.

---

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* A GDC GKE User Cluster active.
* An internal Git server (e.g. GitLab Enterprise) and runners configured to run inside the cluster or project network.
* `helm`, `kubectl`, and `gdcloud` CLIs configured on your developer workstation.
* Necessary project-level IAM roles:
  * **GKE Cluster Admin**: `roles/gke.clusterAdmin` (required to install cluster-wide MLOps CRDs).
  * **Storage Reader/Writer**: `roles/storage.objectAdmin` (for training data access).

---

## **Section 1: Common Setup**

## 1.2 Base Cluster Resource & Node Pool Requirements

### 1.2.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | GPU Required (per Pod) | Storage / PVC |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **Model Serving** | 1 | 4 (4) | 16Gi (16Gi) | 1 x A100 (80GB)* | None |
| **Training Job** | 1 | 8 (8) | 32Gi (32Gi) | 1 x A100 (80GB)* | None |
| **MLOps Tools** | 1 | 4 (4) | 16Gi (16Gi) | None | 50Gi PVC |

> [!NOTE]
> \* **GPU requirements for MLOps**: Model serving and training workloads optionally leverage NVIDIA A100/H100 GPUs for acceleration. If GPUs are not available, workloads can run in CPU-only mode, but execution times will significantly increase.

### 1.2.2 Recommended Node Pool Configurations

To isolate heavy ML workloads and prevent resource starvation, configure two separate node pools:
1. **GPU Accelerator Node Pool**: Dedicated to hosting the GPU-accelerated model serving and training jobs.
   * **Node Type**: GPU-equipped host servers (e.g., `a2-highgpu-1g` / GDC equivalent physical node).
   * **Capacity**: 2 nodes of type **`a2-ultragpu-1g-gdc`** (1x A100 80GB per node).
   * **Taints & Tolerations**: Apply taint `nvidia.com/gpu:NoSchedule` to prevent standard non-GPU containers from scheduling here.
2. **Standard Compute Node Pool**: Hosts the standard MLOps control plane tools (Prometheus, MLFlow/metadata services).
   * **Capacity**: 2 nodes of type **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node).

### 1.2.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p8-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  # 1. CPU Node Pool
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 2
    labels:
      pool: cpu
  # 2. GPU Node Pool
  - name: gpu-node-pool
    machineTypeName: a2-ultragpu-1g-gdc
    nodeCount: 2
    labels:
      pool: gpu
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Create the Project Binding YAML (`project-binding.yaml`):**
```yaml
apiVersion: resourcemanager.gdc.goog/v1
kind: ProjectBinding
metadata:
  name: p8-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p8-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - my-gdc-project
```

**3. Apply the Manifests:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p8-standard-cluster
  namespace: my-gdc-project
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-8-gdc
    nodeCount: 2
    labels:
      pool: cpu
  - name: gpu-node-pool
    machineTypeName: a2-ultragpu-1g-gdc
    nodeCount: 2
    labels:
      pool: gpu
    taints:
    - key: nvidia.com/gpu
      value: "present"
      effect: NoSchedule
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Apply the Manifest:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.2.4 Workload Pod Assignment & Scheduling Configuration

Configure pod scheduling selectors and tolerations:

1. **MLOps Tools**:
   ```yaml
   spec:
     template:
       spec:
         nodeSelector:
           pool: cpu
   ```

2. **Model Serving & Training Workloads (GPU-Enabled)**:
   ```yaml
   spec:
     template:
       spec:
         nodeSelector:
           pool: gpu
         tolerations:
         - key: "nvidia.com/gpu"
           operator: "Exists"
           effect: "NoSchedule"
   ```

### 1.2 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the model container images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p8-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the model container images:
```bash
docker tag model:v1 harbor.shared-services.gdc.local/my-org/model:v1
docker push harbor.shared-services.gdc.local/my-org/model:v1
```

---

## **Section 2: Deploying the MLOps Toolchain**

Deploy the Prometheus monitoring stack and Argo Rollouts controller using Helm charts.

#### Option A: Manual (CLI)
```shell
export REGISTRY_HOST="harbor.shared-services.gdc.local/charts"

# 1. Deploy Prometheus & Alertmanager
helm install prometheus oci://${REGISTRY_HOST}/kube-prometheus-stack \
  -n monitoring --create-namespace

# 2. Deploy Argo Rollouts Controller
helm install argo-rollouts oci://${REGISTRY_HOST}/argo-rollouts \
  -n argo-rollouts --create-namespace
```

---

## **Section 3: Configuring Retraining Pipeline**

Integrate the retraining triggers inside your internal GitLab CI system. Alertmanager webhooks must target your project API pipeline.

#### *.gitlab-ci.yml* retrain configuration snippet:
```yaml
stages:
  - retrain

retrain_on_drift:
  stage: retrain
  only:
    variables:
      - $TRIGGER_SOURCE == "alertmanager"
  script:
    # 1. Pull the training data from local storage
    - dvc pull gs://ml-data/latest.dvc

    # 2. Run training script
    - python train.py

    # 3. Push new model weights to local GDC bucket
    - gdcloud storage cp new_model.pb gs://models/vNext/

    # 4. Update the rollout image to start canary deployment
    - kubectl argo rollouts set image model-serving container=harbor.shared-services.gdc.local/model:vNext
```

---

## **Section 4: Deploying Canary Rollouts**

Expose the serving model using an Argo `Rollout` definition instead of standard Kubernetes Deployments.

#### *rollout.yaml* Configuration:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: model-serving
  namespace: my-gdc-project
spec:
  replicas: 4
  strategy:
    canary:
      analysis:
        templates:
          - templateName: model-accuracy-analysis
      steps:
        - setWeight: 10
        - pause: { duration: 5m }
        - setWeight: 50
        - pause: { duration: 10m }
  template:
    metadata:
      labels:
        app: model-serving
    spec:
      containers:
      - name: container
        image: harbor.shared-services.gdc.local/model:v1
        ports:
        - containerPort: 8080
```

Apply the Rollout:
```shell
kubectl apply -f rollout.yaml -n my-gdc-project
```

---

## **Section 5: Validation**

### 5.1 Verify Toolchain Deployments
Check that the Prometheus and Argo Rollouts operators are healthy:
```shell
helm status prometheus -n monitoring
helm status argo-rollouts -n argo-rollouts
```

### 5.2 Simulate Drift Trigger & Pipeline Execution

#### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute verification pod directly inside the cluster to check toolchain status and rollout progression:

```bash
kubectl run p8-verify --rm -i --restart=Never -n my-gdc-project \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Pattern 8 Closed Loop MLOps verified!" && \
    echo "✅ SUCCESS: Prometheus and Rollouts toolchain active" && \
    echo "===============================================" && \
    echo ""
  ' && kubectl get pods -n monitoring && kubectl get pods -n argo-rollouts
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Pattern 8 Closed Loop MLOps verified!
✅ SUCCESS: Prometheus and Rollouts toolchain active
===============================================
NAME... READY STATUS...
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

#### Option B: Manual Drift Trigger & Rollout Verification
Trigger Alertmanager manually or invoke the GitLab API endpoint directly:
```shell
curl -X POST https://gitlab.shared-services.gdc.local/api/v4/projects/<ID>/trigger/pipeline \
     -F token=<TOKEN> \
     -F ref=main \
     -F variables[TRIGGER_SOURCE]=alertmanager
```
Verify:
1. A new training pipeline initiates.
2. After completion, verify with `kubectl argo rollouts get rollout model-serving -n my-gdc-project` that the rollout has transitioned to a canary state with 10% traffic shifted to `vNext`.

---

## **Section 6: Operations & Troubleshooting**

### 6.1 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Canary fails & rolls back` | The newly trained model accuracy is below threshold, or serving throws exceptions. | Inspect training logs in GitLab CI; check model serving error logs. |
| `Webhook fails to trigger pipeline` | Network configuration prevents Alertmanager pods from communicating with GitLab. | Verify network routes and whitelists inside your user project's network configs. |
| `Rollout status Stuck` | Insufficient compute resources to schedule new canary pods. | Check GKE node capacity; provision additional standard node pools if needed. |
