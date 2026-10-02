# Image Mirroring 
This document describes how to mirror container images from Kubernetes manifests into a private container registry (such as **GDC Managed Harbor** or an organization-level Harbor instance) for **Google Distributed Cloud air-gapped (GDCag)** environments. Please also refer to [deploy-container-workloads](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/platform-application/deploy-container-workloads).

# Managed Harbor Setup
## Setup environment variables
```bash
export PROJECT="iac-root" #project where the Harbor will be deployed
export HARBOR_PROJECT="iac" #project in Harbor where the images will be mirrored
export HARBOR_INSTANCE="harbor001" #Harbor instance name
```
## Create harbor instance:
```bash
gdcloud harbor instances create ${HARBOR_INSTANCE:?} \
    --project=${PROJECT:?}

gdcloud harbor harbor-projects create ${HARBOR_PROJECT:?} \
    --project=${PROJECT:?} \
    --instance=${HARBOR_INSTANCE:?}
```

## Get harbor details:
```bash
gdcloud harbor instances describe ${HARBOR_INSTANCE:?} \
    --project=${PROJECT:?}
```
Output contains the harbor url, e.g.: https://harbor001-iac-root.org-12345.zone1-a.gdch.test

## Create Kubernetes image pull secret
Follow [create-image-pull-secret](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/platform-application/deploy-container-workloads#create-image-pull-secret) documentation to add a Harbor project robot account to serve as your service account.

- From the Harbor console, select your Harbor project.

- Click Robot Accounts.

- Select New Robot Account.

- Give your new robot account a name and define any additional settings.

- Click Add. The robot account name and secret are displayed on the success screen. Keep this screen open for reference in the next step. For more information, see [Harbor's documentation](https://goharbor.io/docs/2.8.0/working-with-projects/project-configuration/create-robot-accounts/#add-a-robot-account). 

- Login using robot account credentials:
```bash
docker login ${REGISTRY:?} 
... provide robot account name and password
```
**Note:**
 You can use Harbor CLI Secret to login, as in the example below:
 ```bash
docker login -u "${HARBOR_USER:?}" -p "${HARBOR_SECRET:?}" "${REGISTRY:?}"
```

# Mirror  images to Managed Harbor Registry
## Prerequisites

- **Python 3**
- **Docker CLI** installed, running, and authenticated against the target Harbor registry (`docker login`).
- **Network Access** from the workstation running the script to both the upstream source registries (to pull images) and the target Harbor registry (to push images).

## Usage

```bash
./mirror_images.py --manifest <manifest_path> --registry <registry_url>
```

### Arguments

| Argument | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--manifest` | No | `manifest.yaml` | Path to the Kubernetes manifest YAML file containing `image:` references. |
| `--registry` | Yes | — | Target registry URL including the Harbor project path (e.g., `harbor001-iac-root.org-12345.zone1-a.gdch.test/iac`). |

### Example: Mirroring Images to Harbor

1. **Set environment variables and authenticate with Harbor:**
   ```bash
   export REGISTRY="harbor001-iac-root.org-12345.zone1-a.gdch.test"
   export HARBOR_PROJECT="iac"
   export HARBOR_USER="<robot-account-or-user>"
   export HARBOR_SECRET="<harbor-cli-secret>"

   docker login -u "${HARBOR_USER:?}" -p "${HARBOR_SECRET:?}" "${REGISTRY:?}"
   ```

2. **Run `mirror_images.py` against your Kubernetes manifest:**
   ```bash
   ./mirror_images.py \
     --manifest "<path_to_manifest>" \
     --registry "${REGISTRY}/${HARBOR_PROJECT}"
   ```

# Use mirrored images
When using mirrored images, ensure that the target cluster has an image pull secret that can access the mirrored images. 

1. **Update the manifest to reference the mirrored images:**
   After pushing the images to Harbor, update the image prefixes in your deployment manifest so the cluster pulls from the private registry:
   ```bash
   sed -i -E "s@(image:[[:space:]]+).*/@\1${REGISTRY:?}/${HARBOR_PROJECT:?}/@g" "<path_to_manifest>"
   ```
2. **Create an image pull secret** in the target cluster's namespace to allow it to pull images from the mirrored registry, for example:
```bash
kubectl create secret docker-registry ${HARBOR_INSTANCE:?}-creds  \
    --from-file=.dockerconfigjson=${HOME}/.docker/config.json \
    -n <namespace>
```   
Make sure to update the manifest also to include:
```bash
  imagePullSecrets:
      - name: ${HARBOR_INSTANCE:?}-creds
```

## How It Works

1. **Manifest Parsing**: Reads the specified YAML file and extracts all unique image references matching `image: <name>:<tag>`.
2. **Pull**: Executes `docker pull <image>` for each discovered image.
3. **Re-tag**: Strips the upstream registry/repository path to keep the base image name and tag (`<image_base>:<tag>`), and runs `docker tag <image> <registry>/<image_base>:<tag>`.
4. **Push**: Executes `docker push <registry>/<image_base>:<tag>` to upload the image to the target registry.
5. **Verification**: Tracks pushed images and exits with code `1` if any image fails to mirror, listing the failed images.



# Troubleshooting

## Manual image push:
```
export IMAGE=...
export SOURCE_REGISTRY=...

docker pull ${SOURCE_REGISTRY:?}/${IMAGE:?}
docker tag ${SOURCE_REGISTRY:?}/${IMAGE:?} ${REGISTRY:?}/${HARBOR_PROJECT:?}/${IMAGE:?}
docker push ${REGISTRY:?}/${HARBOR_PROJECT:?}/${IMAGE:?}
```

## Authentication Issue
```
E0926 08:57:00.988701 3971516 get.go:37] cred helper failed: can not find harbor credential: failed to get audience of the Harbor instance registry harbor001-iac-root.org-12345.zone1-a.gdch.test: HarborInstance iac-root/harbor001 does not contain audience annotation
```
The error you are encountering occurs because the docker-credential-mhs credential helper relies on an annotation (harborinstance.artifactregistry.gdc.goog/auth-audience) on the HarborInstance resource to generate the correct tokens. As we saw in your earlier describe output, your harbor001 instance has empty annotations (annotations: `{}`), which causes the credential helper to fail.

To unblock your image push, a workaround is to bypass the mhs credential helper and use a Harbor CLI Secret to authenticate instead as in the example.
export HARBOR_USER="admin"
export HARBOR_SECRET="********"

To fix the annotation:
```bash
export HARBOR_AUDIENCE=[ORG ADMIN CLUSTER NAME] # gdchservices-admin
kubectl patch harborinstance harbor001 -n iac-root --type=merge -p '{"metadata": {"annotations": {"harborinstance.artifactregistry.gdc.goog/auth-audience": "${HARBOR_AUDIENCE}"}}}'
```

# TLS issue
In case there is an issue with trusting harbor registry, here is what needs to be done:
```
Failed to pull image "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/argocd:latest": failed to pull and unpack image "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/argocd:latest": failed to resolve reference "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/argocd:latest": failed to do request: Head "https://harbor001-iac-root.org-12345.zone1-a.gdch.test/v2/iac/argocd/manifests/latest": tls: failed to verify certificate: x509: certificate signed by unknown authority
```
Managed Harbor trust chain is:
- CN = GDC Managed ORG TLS CA
  - CN = harbor001-iac-root.org-12345.zone1-a.gdch.test

Export GDC Managed ORG TLS CA to "harbor-ca.crt" and follow instructions in online documentation to trust the registry.

Standard cluster config snippet:
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
```
This is however missing trust store for Managed Harbor. To add it, add the snpippet (requires IO priviledges):
```yaml
    - caCertSecretRef:
        name: trust-store-root-ext
        namespace: anthos-creds
      endpoint: https://harbor001-iac-root.org-12345.zone1-a.gdch.test/iac
```