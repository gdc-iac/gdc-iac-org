# Gitea with Actions Runners on GDC Standard Cluster

This guide describes how to deploy **Gitea** along with **Gitea Actions Runners (`act_runner`)** on a **Google Distributed Cloud air-gapped (GDCag) Kubernetes Standard Cluster**. This is a simplified version of [Gitea installation guide](https://docs.gitea.com/category/installation/) limiting use of tools to those available in the GDC environment. E.g. use of `kubectl` and `kubectl apply` instead of Helm or custom manifests provided by the Gitea team. It assumes **Gitea is air-gapped** meaning it cannot reach the internet directly and all required container images need to be mirrored to a local Harbor registry. It also assumes use of [GDC Standard Cluster](https://cloud.google.com/distributed-cloud/hosted/docs/reference/api/rest/v1/projects.locations.clusters?hl=en_US).

In an air-gapped GDC environment, Gitea serves as an internal Git repository and CI/CD platform for GitOps tools (such as [ArgoCD](../argocd/README.md) and [Config Sync](../config-sync/README.md)) and infrastructure automation pipelines ([Helmfile](../helmfile/README.md) / [Helm CLI](../helm_cli/README.md)).


## Prerequisites

1. **GDC Bootstrap & Kubeconfigs**: Complete the initial bootstrap procedure in [`tools/bootstrap/README.md`](../bootstrap/README.md).
2. **Kubernetes Standard Cluster**: A running GDC Standard Cluster with `kubectl` context configured. If you need to create one, follow the cluster creation steps in [`tools/argocd/INSTALL_STANDARD_CLUSTER.md`](../argocd/INSTALL_STANDARD_CLUSTER.md).
   ```bash
   gdcloud clusters get-credentials <CLUSTER_NAME> \
       --standard \
       --project=iac-root
   ```
3. **Container Registry (Managed Harbor)**: A Harbor instance reachable from the Standard Cluster with TLS trust configured. See [`tools/argocd/INSTALL_HARBOR.md`](../argocd/INSTALL_HARBOR.md) for instructions on creating a Managed Harbor instance, configuring robot accounts, and setting up the cluster TLS trust store.

---

## 1. Prepare Environment Variables and Manifests

Set the environment variables for your GDC project, Harbor registry, and target Kubernetes namespace:

```bash
export PROJECT="iac-root"
export HARBOR_PROJECT="iac"
export REGISTRY="harbor001-iac-root.org-12345.zone1a.gdch.test"
export HARBOR_USER="<robot-account-or-admin>"
export HARBOR_SECRET="<harbor-cli-secret>"
export NAMESPACE="gitea"
```

### Step 1.1: Create Gitea Server Manifest (`gitea.yaml`)

```bash
cat <<EOF > gitea.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: gitea-data
  labels:
    app: gitea
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gitea
  labels:
    app: gitea
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gitea
  template:
    metadata:
      labels:
        app: gitea
    spec:
      imagePullSecrets:
        - name: harbor001-creds     # <-- Added your Harbor registry credentials
      containers:
        - name: gitea
          image: gitea/gitea:latest
          ports:
            - name: http
              containerPort: 3000   # Internal web panel port
              protocol: TCP
            - name: ssh
              containerPort: 22     # Internal built-in SSH push port
              protocol: TCP
          volumeMounts:
            - name: data
              mountPath: /data
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: gitea-data
---
apiVersion: v1
kind: Service
metadata:
  name: gitea
spec:
  type: ClusterIP
  selector:
    app: gitea
  ports:
    - name: http
      port: 80
      targetPort: 3000
    - name: ssh
      port: 22
      targetPort: 22
EOF
```

### Step 1.2: Create Gitea Actions Runner Manifest (`gitea-runner.yaml`)

This manifest defines `act_runner` with a Docker-in-Docker (`dind`) sidecar container so container-based workflow jobs can run inside the Kubernetes pod:

```bash
cat <<EOF > gitea-runner.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: gitea-runner-data
  labels:
    app: gitea-runner
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gitea-runner
  labels:
    app: gitea-runner
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: gitea-runner
  template:
    metadata:
      labels:
        app: gitea-runner
    spec:
      imagePullSecrets:
        - name: harbor001-creds
      containers:
        - name: runner
          image: gitea/act_runner:latest
          command: ["sh", "-c", "while ! nc -z localhost 2376 </dev/null; do echo 'Waiting for docker daemon...'; sleep 2; done; /sbin/tini -- run.sh"]
          env:
            - name: DOCKER_HOST
              value: tcp://localhost:2376
            - name: DOCKER_CERT_PATH
              value: /certs/client
            - name: DOCKER_TLS_VERIFY
              value: "1"
            - name: GITEA_INSTANCE_URL
              value: http://gitea.${NAMESPACE:?}.svc:80
            - name: GITEA_RUNNER_REGISTRATION_TOKEN
              valueFrom:
                secretKeyRef:
                  name: gitea-runner-secret
                  key: GITEA_RUNNER_REGISTRATION_TOKEN
            - name: GITEA_RUNNER_NAME
              value: k8s-standard-runner
            - name: CONFIG_FILE
              value: /config/config.yaml
          volumeMounts:
            - name: docker-certs
              mountPath: /certs
            - name: runner-data
              mountPath: /data
            - name: runner-config
              mountPath: /config
              readOnly: true
        - name: daemon
          image: library/docker:dind
          env:
            - name: DOCKER_TLS_CERTDIR
              value: /certs
          securityContext:
            privileged: true
          volumeMounts:
            - name: docker-certs
              mountPath: /certs
      volumes:
        - name: docker-certs
          emptyDir: {}
        - name: runner-data
          persistentVolumeClaim:
            claimName: gitea-runner-data
        - name: runner-config
          configMap:
            name: gitea-runner-config
EOF
```

> **Alternative (Rootless / Host-Mode Runner without DinD):**
> If your cluster security policies disallow `privileged: true` containers, omit the `daemon` (`library/docker:dind`) container and `DOCKER_*` environment variables, set `command: ["/sbin/tini", "--", "run.sh"]`, and configure `labels: ["self-hosted:host"]` in `gitea-runner-config` (Step 5.2). Jobs referencing `runs-on: self-hosted` will execute directly inside the `runner` container process space.

---

## 2. Mirror Container Images to Harbor

Because GDC Standard Clusters run in an air-gapped environment without internet access, mirror the required container images into your Harbor registry using [`../mirror-images/mirror_images.py`](../mirror-images/mirror_images.py) from a workstation with access to both upstream registries and Harbor:

```bash
# Authenticate with Harbor
docker login -u "${HARBOR_USER:?}" -p "${HARBOR_SECRET:?}" "${REGISTRY:?}"

# Mirror images from Gitea and Runner manifests to Harbor
../mirror-images/mirror_images.py \
  --manifest gitea.yaml \
  --registry "${REGISTRY:?}/${HARBOR_PROJECT:?}"

../mirror-images/mirror_images.py \
  --manifest gitea-runner.yaml \
  --registry "${REGISTRY:?}/${HARBOR_PROJECT:?}"
```

### Mirror Workflow Job Images / Manual Image Push

For workflow job images not referenced directly in the Pod `image:` fields (such as `gitea/runner-images:ubuntu-latest`) or for manual troubleshooting:

```bash
for IMAGE in \
  "gitea/runner-images:ubuntu-latest" \
  "ghcr.io/helmfile/helmfile:v1.2.1" \
  "bitnami/kubectl:latest" 
do
  IMAGE_BASE="${IMAGE##*/}"
  docker pull "${IMAGE:?}"
  docker tag "${IMAGE:?}" "${REGISTRY:?}/${HARBOR_PROJECT:?}/${IMAGE_BASE:?}"
  docker push "${REGISTRY:?}/${HARBOR_PROJECT:?}/${IMAGE_BASE:?}"
done
```

### Update Manifest Image References

Update the `image:` fields in `gitea.yaml` and `gitea-runner.yaml` to point to your Harbor registry:

```bash
sed -i -E "s@(image:[[:space:]]+).*/@\1${REGISTRY:?}/${HARBOR_PROJECT:?}/@g" gitea.yaml gitea-runner.yaml
```

---

## 3. Prepare Namespace and Image Pull Secret

Create the target namespace on the Standard Cluster and configure the `harbor001-creds` `docker-registry` secret so kubelet can pull images from your project-scoped Managed Harbor:

```bash
kubectl create namespace "${NAMESPACE:?}"

kubectl create secret docker-registry harbor001-creds \
    --from-file=.dockerconfigjson="${HOME:?}/.docker/config.json" \
    -n "${NAMESPACE:?}"
```

---

## 4. Deploy Gitea Server

Apply `gitea.yaml` to the Standard Cluster:

```bash
kubectl apply -n "${NAMESPACE:?}" -f gitea.yaml
kubectl rollout status deployment/gitea -n "${NAMESPACE:?}"
```

Verify that the PVC, Pod, and Service are ready:

```bash
kubectl get pvc,pods,svc -n "${NAMESPACE:?}" -l app=gitea
```

### Complete Initial Gitea Configuration

1. Forward the Gitea HTTP service port to your workstation:
   ```bash
   kubectl port-forward -n "${NAMESPACE:?}" svc/gitea 3000:80
   ```
2. Open `http://localhost:3000` in your browser and complete the initial installation wizard (select **SQLite3** for lightweight standalone setups or configure an external PostgreSQL database, and create an Administrator account).

   Alternatively, you can create the admin user via CLI once Gitea is initialized:
   ```bash
   kubectl exec -n "${NAMESPACE:?}" deploy/gitea -- \
     su -c "gitea admin user create --username gitea-admin --password '<STRONG_PASSWORD>' --email admin@example.com --admin" git
   ```

> **Note:** Gitea Actions is enabled by default in modern Gitea releases. If needed, verify that `/data/gitea/conf/app.ini` includes:
> ```ini
> [actions]
> ENABLED = true
> ```

---

## 5. Register and Deploy Gitea Actions Runners (`act_runner`)

Gitea Actions uses `act_runner` to execute CI/CD workflows.

### Step 5.1: Generate a Runner Registration Token

Obtain an instance-wide runner registration token from the running Gitea instance via the CLI or Web UI:

- **Option A — Via CLI:**
  ```bash
  export RUNNER_TOKEN=$(kubectl exec -n "${NAMESPACE:?}" deploy/gitea -- \
    su -c "gitea actions generate-runner-token" git | tr -d '\r')
  ```
- **Option B — Via Web UI:**
  Log in as Administrator, go to **Site Administration** -> **Actions** -> **Runners**, click **Create new Runner**, and copy the **Registration Token**.

Create a Kubernetes Secret in the `${NAMESPACE:?}` namespace with the token:

```bash
kubectl create secret generic gitea-runner-secret \
    --from-literal=GITEA_RUNNER_REGISTRATION_TOKEN="${RUNNER_TOKEN:?}" \
    -n "${NAMESPACE:?}"
```

### Step 5.2: Create Runner Configuration (`ConfigMap`)

In an air-gapped environment, `act_runner` must be configured to pull workflow job container images from your internal Harbor registry rather than Docker Hub.

Create the `gitea-runner-config` `ConfigMap` that maps the `ubuntu-latest` label to your mirrored image in Harbor (and `self-hosted` to `host` execution):

```bash
cat <<EOF | kubectl apply -n "${NAMESPACE:?}" -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: gitea-runner-config
  labels:
    app: gitea-runner
data:
  config.yaml: |
    log:
      level: info
    runner:
      file: .runner
      capacity: 2
      timeout: 3h
      insecure: true
      fetch_timeout: 5s
      fetch_interval: 2s
      labels:
        - "ubuntu-latest:docker://${REGISTRY:?}/${HARBOR_PROJECT:?}/runner-images:ubuntu-latest"
        - "helmfile:docker://${REGISTRY:?}/${HARBOR_PROJECT:?}/helmfile:v1.2.1"
        - "self-hosted:host"
    container:
      network: ""
      privileged: false
      valid_volumes: []
EOF
```

### Step 5.3: Configure Runner access secret
Configure access secrets to store [kubeconfigs created during the bootstrap](../bootstrap/README.md) in the user cluster (where runner is running):
```bash
kubectl -n ${NAMESPACE:?} create secret generic kubeconfig \
  --from-file=config=${MERGED_KUBECONFIG:?}
```

### Step 5.4: Deploy the Runner on the Standard Cluster

Apply `gitea-runner.yaml` (created in Step 1.2 and updated in Step 2):

```bash
kubectl apply -n "${NAMESPACE:?}" -f gitea-runner.yaml
kubectl rollout status deployment/gitea-runner -n "${NAMESPACE:?}"
```

---

## 6. Verify Runner Registration and Test CI Workflow

### Check Runner Logs and Status

```bash
kubectl logs -n "${NAMESPACE:?}" deploy/gitea-runner -c runner
```

You should see output indicating that the runner registered successfully and is polling for jobs:

```text
level=info msg="Runner registered successfully."
...
level=info msg="poller: waiting for tasks..."
```

In the Gitea Web UI (**Site Administration** -> **Actions** -> **Runners**), verify that `k8s-standard-runner` appears with status **Idle**.

### Run a Sample Workflow

Create `.gitea/workflows/verify.yaml` in any Gitea repository with Actions enabled:

```yaml
name: Verify GDC Standard Cluster Runner
on: [push]

jobs:
  smoke-test:
    runs-on: self-hosted
    steps:
      - name: Check Runner Environment
        run: |
          uname -a
          whoami
```
---

## 7. Prepare Gitea repository

Once Gitea and `act_runner` are operational, you can host and automate your GDC Landing Zone configuration by initializing a dedicated Git repository from [`../../foundations/`](../../foundations/README.md) (driven by [`../../foundations/helmfile.yaml`](../../foundations/helmfile.yaml)).

As detailed in [`foundations/README.md`](../../foundations/README.md), the foundations Helmfile pipeline orchestrates GDC resources across sequential execution stages:
- **Global Control Plane Stages (`0-bootstrap`, `0-org-setup`, `1-project-factory`)**: Manage root namespaces, organization policies, projects, IAM role bindings, and service accounts via `kube_context_global`.
- **Zonal & Workload Stages (`2-resources`, `3-clusters`, `4-notebooks`, `5-workload-factory`)**: Provision Harbor registries, VMs, buckets, databases, Standard/User Kubernetes clusters, notebooks, and blueprint workloads via `kube_context_zonal`.

### Step 7.1: Clone `foundations/` into a New Landing Zone Repository

Per the **Execution Standards** in [`foundations/README.md`](../../foundations/README.md#execution-standards), Helmfile resolves internal paths relative to `${PWD}`, so [`helmfile.yaml`](../../foundations/helmfile.yaml) must reside at the root of your repository.

1. Copy [`foundations/`](../../foundations/README.md) into a new standalone repository directory (for example, `landing.git`) and initialize Git:
   ```bash
   cp -r ../../foundations ./landing.git
   cd ./landing.git
   git init -b main
   ```

2. Review and tailor the modular environment configuration files under `bases/environments/<env>/` (e.g., `bases/environments/dev/`) as documented in [`foundations/README.md`](../../foundations/README.md#configuration-modular-separation):
   - **`globals.yaml`**: Set shared context parameters (`gdc_context_global`, `gdc_context_zone`, `gdc_release_namespace`, and `iac_sa`).
   - **`tenants-org-*.yaml`**: Define tenant organizations, explicit `kube_context_global` and `kube_context_zonal` contexts (required by the pipeline's pre-flight security assertions), projects, IAM/RBAC bindings, and zonal resources.
   - **`charts.yaml`**: Configure chart resolution mode (see [`foundations/DEPLOYMENT_MANUAL.md`](../../foundations/DEPLOYMENT_MANUAL.md) and [`foundations/AIRGAP_MIRRORING.md`](../../foundations/AIRGAP_MIRRORING.md)):
     - **OCI Registry Mode (Recommended for standalone repositories)**: Point chart paths and pinned versions to the Helm charts ingested into your air-gapped Harbor registry (e.g., `oci://${REGISTRY:?}/${HARBOR_PROJECT:?}/gdc-clusters`).
     - **Local Path Mode**: If retaining default relative paths (`../../../charts/gdc-*`), ensure `charts/` and `blueprints/` are accessible at the expected relative path or vendored into the repository.

3. Validate the repository locally before pushing:
   ```bash
   helmfile -e dev lint
   helmfile -e dev template >/dev/null
   ```

### Step 7.2: Push the Repository to Gitea

1. In the Gitea Web UI, create a target organization (e.g., `org-12345`) and an empty repository named `landing`.
2. Expose the Gitea service to your workstation via `kubectl port-forward`. You can push over either HTTP or SSH:
   - **Option A — Via SSH (matching `landing.git` example):**
     Ensure your SSH public key is added to your Gitea user profile (**Settings** -> **SSH / GPG Keys**), then forward container port `22`:
     ```bash
     kubectl port-forward -n "${NAMESPACE:?}" svc/gitea 2222:22
     ```
     Configure the remote and push:
     ```bash
     git remote add origin ssh://git@127.0.0.1:2222/org-12345/landing.git
     git add .
     git commit -m "Initialize GDC foundations landing zone"
     git push -u origin main
     ```
   - **Option B — Via HTTP:**
     Forward service port `80` to local port `3000`:
     ```bash
     kubectl port-forward -n "${NAMESPACE:?}" svc/gitea 3000:80
     ```
     Configure the remote and push:
     ```bash
     git remote add origin http://127.0.0.1:3000/org-12345/landing.git
     git add .
     git commit -m "Initialize GDC foundations landing zone"
     git push -u origin main
     ```

### Step 7.3: Prepare the Gitea Actions Workflow

Adapt the staged CI/CD automation strategy from [`foundations/README.md`](../../foundations/README.md#cicd-automation-strategy-staged-execution-samples) into a Gitea Actions workflow at `.gitea/workflows/foundations.yaml`.

Key design considerations for running the Foundations Helmfile pipeline on the air-gapped Gitea runner:
- **Runner Image (`runs-on: helmfile`)**: Uses the `helmfile` label mapped in Step 5.2 (`gitea-runner-config`) to the mirrored `ghcr.io/helmfile/helmfile:v1.2.1` image in Harbor.
- **Air-Gapped Git Checkout**: Uses native `git fetch` against the internal Kubernetes service endpoint (`http://gitea.gitea.svc:80`) with `GITEA_TOKEN` / `github.token` rather than external GitHub Actions (`actions/checkout`), avoiding internet dependencies.
- **Offline Validation & Manual Dispatch**: Automatically runs `helmfile lint` and `helmfile template` on every `push` and `pull_request` without requiring cluster credentials, while providing `workflow_dispatch` inputs (`environment`, `action`, `stage`) for `diff`, `sync`, `apply`, and reverse-ordered `rollback`.

1. Configure the following **Secrets** and **Variables** in your Gitea repository (**Settings** -> **Actions** -> **Secrets** / **Variables**):
   - `GDC_KUBECONFIG_B64` *(Secret, required for `diff`/`sync`/`apply`/`rollback`)*: Base64-encoded kubeconfig (`base64 -w0 ~/.kube/config`) containing the Global and Zonal API contexts referenced in `globals.yaml` and `tenants-org-*.yaml`.
   - `HARBOR_REGISTRY` *(Variable, optional)*: Internal Harbor hostname (e.g., `harbor001-iac-root.org-12345.zone1a.gdch.test`) when using OCI chart resolution in `charts.yaml`.
   - `HARBOR_USER` & `HARBOR_SECRET` *(Secrets, optional)*: Robot account credentials for `helm registry login`.
   - `SOPS_AGE_KEY` *(Secret, optional)*: Age private key if using `helm-secrets` / SOPS-encrypted environment files.

2. Create `.gitea/workflows/foundations.yaml` in your repository:

```yaml
name: GDC Air-Gapped Foundations Pipeline

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
  workflow_dispatch:
    inputs:
      environment:
        description: "Target GDC environment (dev, stg, prd)"
        required: true
        default: "dev"
        type: choice
        options:
          - dev
          - stg
          - prd
      action:
        description: "Helmfile operation to execute"
        required: true
        default: "validate"
        type: choice
        options:
          - validate
          - diff
          - sync
          - apply
          - rollback
      stage:
        description: "Target execution stage (or 'all' for full staged pipeline)"
        required: true
        default: "all"
        type: choice
        options:
          - all
          - 0-bootstrap
          - 0-org-setup
          - 1-project-factory
          - 2-resources
          - 3-clusters
          - 4-notebooks
          - 5-workload-factory

env:
  ENV: ${{ github.event.inputs.environment || 'dev' }}
  ACTION: ${{ github.event.inputs.action || 'validate' }}
  TARGET_STAGE: ${{ github.event.inputs.stage || 'all' }}
  # Internal Gitea service endpoint on the GDC Standard Cluster
  GITEA_INTERNAL_URL: "http://gitea.gitea.svc:80"
  HELM_WAIT: "true"

jobs:
  # ============================================================================
  # Job 1: Offline Static Validation (Lint & Template Rendering)
  # Runs on every push, PR, and manual dispatch without requiring cluster access
  # ============================================================================
  validate:
    name: "Validate Foundations (${{ github.event.inputs.environment || 'dev' }})"
    runs-on: helmfile
    steps:
      - name: Checkout Repository (Air-Gapped Native Git)
        env:
          GIT_TOKEN: ${{ secrets.GITEA_TOKEN || github.token }}
        run: |
          set -euo pipefail
          rm -rf ./* ./.[!.]* ./..?* 2>/dev/null || true
          git init .
          git remote add origin "${GITEA_INTERNAL_URL:?}/${GITHUB_REPOSITORY:?}.git"
          git -c http.extraHeader="Authorization: token ${GIT_TOKEN:?}" fetch --depth=1 origin "${GITHUB_SHA:?}"
          git checkout FETCH_HEAD

      - name: Authenticate with Local Harbor OCI Registry (Optional)
        if: env.HARBOR_REGISTRY != ''
        env:
          HARBOR_REGISTRY: ${{ vars.HARBOR_REGISTRY }}
          HARBOR_USER: ${{ secrets.HARBOR_USER }}
          HARBOR_SECRET: ${{ secrets.HARBOR_SECRET }}
        run: |
          if [ -n "${HARBOR_REGISTRY}" ] && [ -n "${HARBOR_USER}" ] && [ -n "${HARBOR_SECRET}" ]; then
            echo "${HARBOR_SECRET:?}" | helm registry login "${HARBOR_REGISTRY:?}" \
              --username "${HARBOR_USER:?}" \
              --password-stdin \
              --insecure
          fi

      - name: Verify Tooling Versions
        run: |
          helm version --short
          helmfile --version
          helm plugin list

      - name: Lint & Template Foundations
        run: |
          set -euo pipefail
          if [ "${TARGET_STAGE:?}" = "all" ]; then
            echo "Running full environment lint and template validation for ENV=${ENV:?}..."
            helmfile -e "${ENV:?}" lint
            helmfile -e "${ENV:?}" template >/dev/null
          else
            echo "Running stage-scoped lint and template validation for ENV=${ENV:?}, stage=${TARGET_STAGE:?}..."
            helmfile -e "${ENV:?}" -l "stage=${TARGET_STAGE:?}" lint
            helmfile -e "${ENV:?}" -l "stage=${TARGET_STAGE:?}" template >/dev/null
          fi
          echo "Validation succeeded for ENV=${ENV:?} (stage=${TARGET_STAGE:?})."

  # ============================================================================
  # Job 2: Dry-Run Plan (helmfile diff)
  # Requires GDC_KUBECONFIG_B64 secret containing Global and Zonal API contexts
  # ============================================================================
  plan:
    name: "Plan / Diff (${{ github.event.inputs.environment || 'dev' }})"
    needs: [validate]
    if: >-
      github.event.inputs.action == 'diff' ||
      github.event.inputs.action == 'apply' ||
      github.event.inputs.action == 'sync'
    runs-on: helmfile
    steps:
      - name: Checkout Repository (Air-Gapped Native Git)
        env:
          GIT_TOKEN: ${{ secrets.GITEA_TOKEN || github.token }}
        run: |
          set -euo pipefail
          rm -rf ./* ./.[!.]* ./..?* 2>/dev/null || true
          git init .
          git remote add origin "${GITEA_INTERNAL_URL:?}/${GITHUB_REPOSITORY:?}.git"
          git -c http.extraHeader="Authorization: token ${GIT_TOKEN:?}" fetch --depth=1 origin "${GITHUB_SHA:?}"
          git checkout FETCH_HEAD

      - name: Configure GDC Multi-Context Kubeconfig & SOPS
        env:
          GDC_KUBECONFIG_B64: ${{ secrets.GDC_KUBECONFIG_B64 }}
          SOPS_AGE_KEY: ${{ secrets.SOPS_AGE_KEY }}
          CLOUDSDK_API_ENDPOINT_OVERRIDES_KMS: ${{ vars.CLOUDSDK_API_ENDPOINT_OVERRIDES_KMS }}
        run: |
          set -euo pipefail
          if [ -z "${GDC_KUBECONFIG_B64}" ]; then
            echo "ERROR: Secret GDC_KUBECONFIG_B64 is required for cluster diff/apply operations."
            exit 1
          fi
          mkdir -p ~/.kube ~/.config/sops/age
          echo "${GDC_KUBECONFIG_B64:?}" | base64 -d > ~/.kube/config
          chmod 600 ~/.kube/config
          if [ -n "${SOPS_AGE_KEY}" ]; then
            echo "${SOPS_AGE_KEY:?}" > ~/.config/sops/age/keys.txt
            chmod 600 ~/.config/sops/age/keys.txt
          fi
          kubectl config get-contexts

      - name: Authenticate with Local Harbor OCI Registry (Optional)
        if: env.HARBOR_REGISTRY != ''
        env:
          HARBOR_REGISTRY: ${{ vars.HARBOR_REGISTRY }}
          HARBOR_USER: ${{ secrets.HARBOR_USER }}
          HARBOR_SECRET: ${{ secrets.HARBOR_SECRET }}
        run: |
          if [ -n "${HARBOR_REGISTRY}" ] && [ -n "${HARBOR_USER}" ] && [ -n "${HARBOR_SECRET}" ]; then
            echo "${HARBOR_SECRET:?}" | helm registry login "${HARBOR_REGISTRY:?}" \
              --username "${HARBOR_USER:?}" \
              --password-stdin \
              --insecure
          fi

      - name: Execute Helmfile Diff
        run: |
          set -euo pipefail
          if [ "${TARGET_STAGE:?}" = "all" ]; then
            helmfile -e "${ENV:?}" diff
          else
            helmfile -e "${ENV:?}" -l "stage=${TARGET_STAGE:?}" diff
          fi

  # ============================================================================
  # Job 3: Staged Deployment / Rollback Execution
  # Executes stages in strict dependency order against Global & Zonal APIs
  # ============================================================================
  deploy:
    name: "Execute ${{ github.event.inputs.action }} (${{ github.event.inputs.stage || 'all' }})"
    needs: [validate]
    if: >-
      github.event.inputs.action == 'sync' ||
      github.event.inputs.action == 'apply' ||
      github.event.inputs.action == 'rollback'
    runs-on: helmfile
    steps:
      - name: Checkout Repository (Air-Gapped Native Git)
        env:
          GIT_TOKEN: ${{ secrets.GITEA_TOKEN || github.token }}
        run: |
          set -euo pipefail
          rm -rf ./* ./.[!.]* ./..?* 2>/dev/null || true
          git init .
          git remote add origin "${GITEA_INTERNAL_URL:?}/${GITHUB_REPOSITORY:?}.git"
          git -c http.extraHeader="Authorization: token ${GIT_TOKEN:?}" fetch --depth=1 origin "${GITHUB_SHA:?}"
          git checkout FETCH_HEAD

      - name: Configure GDC Multi-Context Kubeconfig & SOPS
        env:
          GDC_KUBECONFIG_B64: ${{ secrets.GDC_KUBECONFIG_B64 }}
          SOPS_AGE_KEY: ${{ secrets.SOPS_AGE_KEY }}
          CLOUDSDK_API_ENDPOINT_OVERRIDES_KMS: ${{ vars.CLOUDSDK_API_ENDPOINT_OVERRIDES_KMS }}
        run: |
          set -euo pipefail
          if [ -z "${GDC_KUBECONFIG_B64}" ]; then
            echo "ERROR: Secret GDC_KUBECONFIG_B64 is required for cluster deployment operations."
            exit 1
          fi
          mkdir -p ~/.kube ~/.config/sops/age
          echo "${GDC_KUBECONFIG_B64:?}" | base64 -d > ~/.kube/config
          chmod 600 ~/.kube/config
          if [ -n "${SOPS_AGE_KEY}" ]; then
            echo "${SOPS_AGE_KEY:?}" > ~/.config/sops/age/keys.txt
            chmod 600 ~/.config/sops/age/keys.txt
          fi
          kubectl config get-contexts

      - name: Authenticate with Local Harbor OCI Registry (Optional)
        if: env.HARBOR_REGISTRY != ''
        env:
          HARBOR_REGISTRY: ${{ vars.HARBOR_REGISTRY }}
          HARBOR_USER: ${{ secrets.HARBOR_USER }}
          HARBOR_SECRET: ${{ secrets.HARBOR_SECRET }}
        run: |
          if [ -n "${HARBOR_REGISTRY}" ] && [ -n "${HARBOR_USER}" ] && [ -n "${HARBOR_SECRET}" ]; then
            echo "${HARBOR_SECRET:?}" | helm registry login "${HARBOR_REGISTRY:?}" \
              --username "${HARBOR_USER:?}" \
              --password-stdin \
              --insecure
          fi

      - name: Run Staged Helmfile Operation
        run: |
          set -euo pipefail

          if [ "${TARGET_STAGE:?}" != "all" ]; then
            echo "Executing 'helmfile -e ${ENV:?} -l stage=${TARGET_STAGE:?} ${ACTION:?}'..."
            helmfile -e "${ENV:?}" -l "stage=${TARGET_STAGE:?}" "${ACTION:?}"
            exit 0
          fi

          if [ "${ACTION:?}" = "rollback" ]; then
            # Rollback in reverse dependency order
            STAGES=(
              "5-workload-factory"
              "4-notebooks"
              "3-clusters"
              "2-resources"
              "1-project-factory"
              "0-org-setup"
              "0-bootstrap"
            )
          else
            # Forward deployment order (Global stages 0-1 -> Zonal stages 2-5)
            STAGES=(
              "0-bootstrap"
              "0-org-setup"
              "1-project-factory"
              "2-resources"
              "3-clusters"
              "4-notebooks"
              "5-workload-factory"
            )
          fi

          for STAGE in "${STAGES[@]}"; do
            echo "===================================================="
            echo " Executing Stage: ${STAGE:?} (Action: ${ACTION:?}, Env: ${ENV:?})"
            echo "===================================================="
            helmfile -e "${ENV:?}" -l "stage=${STAGE:?}" "${ACTION:?}"
          done
```

3. Commit and push the workflow to trigger validation on Gitea Actions:
   ```bash
   git add .gitea/workflows/foundations.yaml
   git commit -m "Add GDC Foundations Helmfile Gitea Actions workflow"
   git push origin main
   ```

---

## Troubleshooting

- **`x509: certificate signed by unknown authority` when pulling from Managed Harbor:**
  Standard clusters trust the organization-level Harbor by default, but require the Managed Harbor endpoint to be added to `registryMirrors` with `trust-store-root-ext`. Follow the **Trust Harbor Registry** section in [`tools/argocd/INSTALL_HARBOR.md`](../argocd/INSTALL_HARBOR.md).
- **`pull access denied ... authorization failed: no basic auth credentials`:**
  Ensure the `harbor001-creds` secret exists in the target namespace (`${NAMESPACE:?}`) and contains valid robot account credentials for your Harbor project.
- **DinD sidecar fails to pull job images from Managed Harbor (`x509: certificate signed by unknown authority`):**
  Mount the GDC root CA certificate (`harbor-ca.crt`) into the `daemon` (`docker:dind`) container at `/etc/docker/certs.d/${REGISTRY:?}/ca.crt` via a `ConfigMap` or `Secret` so the internal Docker daemon trusts your Harbor registry.
