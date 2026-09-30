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

# Standardized Container Image Mirroring for GDC Air-Gapped

This document describes how to provision a **GDC Managed Harbor** instance, configure authentication and cluster trust, and mirror container images from Kubernetes manifests or image lists into Harbor for **Google Distributed Cloud air-gapped (GDCag)** environments. Please also refer to [deploy-container-workloads](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/platform-application/deploy-container-workloads).

---

## 1. Managed Harbor Setup

### Setup Environment Variables
```bash
export PROJECT="iac-root"           # GDC project where the Harbor instance is deployed
export HARBOR_PROJECT="iac"         # Harbor project where images will be mirrored
export HARBOR_INSTANCE="harbor001"  # Harbor instance name
```

### Option A: Declarative Provisioning (Helm / Foundations IaC)
You can provision `HarborInstance` and `HarborInstanceProject` declaratively using [`charts/gdc-harbors`](../../charts/gdc-harbors/README.md) (or via Stage 2 of Foundations in [`foundations/releases/2-resources/harbor.yaml.gotmpl`](../../foundations/releases/2-resources/harbor.yaml.gotmpl)):

```yaml
harbors:
  - name: harbor001
    namespace: iac-root
    annotations:
      harborinstance.artifactregistry.gdc.goog/auth-audience: "gdchservices-admin"
    projects:
      - name: iac
        autoscan: "true"
        creatorkind: User
        creatorname: admin@example.com
```

### Option B: Imperative Provisioning (`gdcloud` CLI)
```bash
gdcloud harbor instances create ${HARBOR_INSTANCE:?} \
    --project=${PROJECT:?}

gdcloud harbor harbor-projects create ${HARBOR_PROJECT:?} \
    --project=${PROJECT:?} \
    --instance=${HARBOR_INSTANCE:?}
```

### Get Harbor Registry URL
```bash
gdcloud harbor instances describe ${HARBOR_INSTANCE:?} \
    --project=${PROJECT:?}
```
The output contains the Harbor URL, e.g.: `https://harbor001-iac-root.org-12345.zone1-a.gdch.test`.

```bash
export REGISTRY="harbor001-iac-root.org-12345.zone1-a.gdch.test"
```

---

## 2. Create Harbor Robot Account & Authenticate

Follow the [create-image-pull-secret](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/platform-application/deploy-container-workloads#create-image-pull-secret) documentation to add a Harbor project robot account to serve as your service account:

1. From the Harbor console, select your Harbor project (`${HARBOR_PROJECT}`).
2. Click **Robot Accounts** -> **New Robot Account**.
3. Give your new robot account a name and define permissions (Pull/Push).
4. Click **Add**. Copy the generated robot account name and secret. For more information, see [Harbor's documentation](https://goharbor.io/docs/2.8.0/working-with-projects/project-configuration/create-robot-accounts/#add-a-robot-account).
5. Authenticate Docker using the robot account credentials (or Harbor CLI Secret):
   ```bash
   export HARBOR_USER="<robot-account-or-user>"
   export HARBOR_SECRET="<robot-secret-or-cli-secret>"

   docker login -u "${HARBOR_USER:?}" -p "${HARBOR_SECRET:?}" "${REGISTRY:?}"
   ```

---

## 3. Mirror Images to Managed Harbor Registry

[`mirror_images.py`](mirror_images.py) supports two input formats (`--manifest` for Kubernetes YAML files or `--images-file` for plain-text image lists like `external_images.txt`) and two operational workflows:

### Arguments Reference

| Argument | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--manifest` | No | `manifest.yaml` | Path to a Kubernetes manifest YAML file containing `image:` references. |
| `--images-file` | No | `None` | Path to a plain-text file with one image reference per line (e.g., `blueprints/patterns/*/external_images.txt`). |
| `--registry` | Conditional | `None` | Target registry URL including the Harbor project path (e.g., `${REGISTRY}/${HARBOR_PROJECT}`). Required when pushing directly or with `--load-dir`. |
| `--save-dir` | No | `None` | Directory to export pulled images as `.tar.gz` archives for offline transfer across an air-gap boundary. |
| `--load-dir` | No | `None` | Directory containing exported `.tar.gz` / `.tar` archives to load, re-tag, and push on the air-gapped workstation. |

### Workflow A: Direct Mirroring (Connected Bastion)
Use this mode when the workstation running the script has network reachability to both upstream registries and the target Harbor registry:

```bash
# Mirror images from a Kubernetes YAML manifest (e.g. ArgoCD or Config Sync)
./mirror_images.py \
  --manifest "<path_to_manifest.yaml>" \
  --registry "${REGISTRY}/${HARBOR_PROJECT}"

# Or mirror images from a blueprint external_images.txt list
./mirror_images.py \
  --images-file "../../blueprints/common-scripts/bulk_external_images.txt" \
  --registry "${REGISTRY}/${HARBOR_PROJECT}"
```

### Workflow B: Two-Step Disconnected Air-Gap Transfer (Low-Side -> High-Side)
Use this mode when transferring images across a physical air-gap or data diode where no single machine can reach both the internet and GDC Managed Harbor:

1. **Step 1 — Low-Side (Internet-Connected Workstation):** Pull images and save compressed `.tar.gz` archives:
   ```bash
   ./mirror_images.py \
     --manifest "<path_to_manifest.yaml>" \
     --save-dir /tmp/mirrored-images
   ```
2. **Step 2 — Transfer `/tmp/mirrored-images` to the GDC Air-Gapped Workstation.**
3. **Step 3 — High-Side (Air-Gapped GDC Workstation):** Load archives from disk, re-tag, and push to Managed Harbor:
   ```bash
   docker login -u "${HARBOR_USER:?}" -p "${HARBOR_SECRET:?}" "${REGISTRY:?}"

   ./mirror_images.py \
     --load-dir /tmp/mirrored-images \
     --registry "${REGISTRY}/${HARBOR_PROJECT}"
   ```

---

## 4. Configure Workloads to Use Mirrored Images

When deploying workloads onto GDC Standard or Shared clusters, ensure the manifests reference the Harbor registry and include an `imagePullSecret`:

1. **Update the manifest to reference the mirrored images:**
   ```bash
   sed -i -E "s@(image:[[:space:]]+).*/@\1${REGISTRY:?}/${HARBOR_PROJECT:?}/@g" "<path_to_manifest>"
   ```
2. **Create a Kubernetes `docker-registry` pull secret** in the target workload namespace:
   ```bash
   kubectl create secret docker-registry ${HARBOR_INSTANCE:?}-creds \
       --from-file=.dockerconfigjson=${HOME}/.docker/config.json \
       -n <namespace>
   ```
3. **Reference `imagePullSecrets` in your Pod / Deployment spec:**
   ```yaml
   imagePullSecrets:
     - name: harbor001-creds
   ```

---

## 5. Troubleshooting

### Manual Image Push
```bash
export IMAGE="argocd:latest"
export SOURCE_REGISTRY="quay.io/argoproj"

docker pull "${SOURCE_REGISTRY:?}/${IMAGE:?}"
docker tag "${SOURCE_REGISTRY:?}/${IMAGE:?}" "${REGISTRY:?}/${HARBOR_PROJECT:?}/${IMAGE:?}"
docker push "${REGISTRY:?}/${HARBOR_PROJECT:?}/${IMAGE:?}"
```

### Authentication Issue (`docker-credential-mhs` Missing Audience Annotation)
If authenticating via `docker-credential-mhs` fails with:
```text
E0926 08:57:00.988701 3971516 get.go:37] cred helper failed: can not find harbor credential: failed to get audience of the Harbor instance registry harbor001-iac-root.org-12345.zone1-a.gdch.test: HarborInstance iac-root/harbor001 does not contain audience annotation
```
This occurs because `docker-credential-mhs` requires the `harborinstance.artifactregistry.gdc.goog/auth-audience` annotation on the `HarborInstance` resource.

* **Workaround 1:** Authenticate directly with `docker login` using a Robot Account or Harbor CLI secret as shown in Section 2.
* **Workaround 2:** Patch the `HarborInstance` resource with the audience annotation (or set `annotations` in `charts/gdc-harbors`):
  ```bash
  export HARBOR_AUDIENCE="<ORG_ADMIN_CLUSTER_NAME>" # e.g. gdchservices-admin
  kubectl patch harborinstance ${HARBOR_INSTANCE:?} -n ${PROJECT:?} --type=merge \
    -p "{\"metadata\": {\"annotations\": {\"harborinstance.artifactregistry.gdc.goog/auth-audience\": \"${HARBOR_AUDIENCE}\"}}}"
  ```

### TLS Certificate Verification Issue on Standard Clusters
If kubelet fails to pull from Managed Harbor with:
```text
Failed to pull image "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/argocd:latest": ... tls: failed to verify certificate: x509: certificate signed by unknown authority
```
Managed Harbor uses the certificate chain:
* `CN = GDC Managed ORG TLS CA` -> `CN = harbor001-iac-root.org-12345.zone1-a.gdch.test`

Standard clusters include `registryMirrors` trust entries for the org-level Harbor (`https://harbor.org-12345.zone1-a.gdch.test/v2/...`) by default, but require adding an entry for project-scoped Managed Harbor instances (requires IO privileges):

```yaml
    registryMirrors:
    - caCertSecretRef:
        name: trust-store-root-ext
        namespace: anthos-creds
      endpoint: https://harbor.org-12345.zone1-a.gdch.test/v2/library
    - caCertSecretRef:
        name: trust-store-root-ext
        namespace: anthos-creds
      endpoint: https://harbor.org-12345.zone1-a.gdch.test/v2/gpc-system-container-images
    - caCertSecretRef:
        name: trust-store-root-ext
        namespace: anthos-creds
      endpoint: https://harbor.org-12345.zone1-a.gdch.test/v2/
    # Add trust entry for project-scoped Managed Harbor instance:
    - caCertSecretRef:
        name: trust-store-root-ext
        namespace: anthos-creds
      endpoint: https://harbor001-iac-root.org-12345.zone1-a.gdch.test/iac
```