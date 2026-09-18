# Air-Gapped Image Mirroring & Chart Packaging Guide

Google Distributed Cloud (GDC) partitions operate in highly secured, physically isolated, air-gapped environments. 

Before executing this IaC foundations pipeline inside GDC, all referenced container images and Helm charts must be mirrored, imported, and hosted within your partition's local container registry.

---

## 1. Inventory of External Container Images

This toolkit utilizes several core base images. Ensure all of them are mirrored:

| Stage | Source Image | Target Local Image in GDC Registry |
| :--- | :--- | :--- |
| **Stage 4 (Notebooks)** | `gcr.io/private-cloud-staging/notebooks/deeplearning-platform-release/pytorch-gpu:m125_ext` | `<gdc-harbor-domain>/<project>/pytorch-gpu:m125_ext` |
| **Validation Tests** | `alpine:latest` (or `alpine:3.20`) | `<gdc-harbor-domain>/<project>/alpine:latest` |
| **Validation Tests** | `busybox:latest` | `<gdc-harbor-domain>/<project>/busybox:latest` |

---

## 2. Mirroring Container Images Using Skopeo (Recommended)

`skopeo` is a lightweight, open-source CLI tool that copies container images directly between registries (or into local tar files) without requiring a full Docker daemon installation.

### Step A: On an Internet-Connected Machine
1. Download and save the required images as local directory archives:
```bash
# Pull PyTorch Deep Learning GPU container
skopeo copy docker://gcr.io/private-cloud-staging/notebooks/deeplearning-platform-release/pytorch-gpu:m125_ext dir:./images/pytorch-gpu

# Pull Alpine test image
skopeo copy docker://docker.io/library/alpine:latest dir:./images/alpine
```

2. Compress the local images directory into a tarball to move onto your secure transport media (e.g. encrypted USB or diode interface):
```bash
tar -czf gdc-foundations-images.tar.gz ./images
```

### Step B: On your Air-Gapped Operator Workstation
1. Extract the compressed images:
```bash
tar -xzf gdc-foundations-images.tar.gz
```

2. Log in to your GDC Hosted local Harbor registry:
```bash
skopeo login --tls-verify=false -u <registry-user> -p <registry-password> <gdc-harbor-domain>
```

3. Synchronize the local image folders directly into your Harbor project namespace:
```bash
# Push PyTorch GPU Image
skopeo copy --dest-tls-verify=false dir:./images/pytorch-gpu docker://<gdc-harbor-domain>/<project>/pytorch-gpu:m125_ext

# Push Alpine Test Image
skopeo copy --dest-tls-verify=false dir:./images/alpine docker://<gdc-harbor-domain>/<project>/alpine:latest
```

---

## 3. Mirroring Helm Charts to Local OCI Registries

Standard GDC IaC pipelines require pushing local Helm charts to your regional OCI (Open Container Initiative) registry so they can be referenced dynamically in GitOps workflows.

To package and push the custom charts:
```bash
# 1. Log in your Helm CLI to the local OCI registry
helm registry login <gdc-harbor-domain> --username <username> --password <password>

# 2. Package and push each local chart
for chart_dir in charts/*; do
  if [ -d "$chart_dir" ]; then
    chart_name=$(basename "$chart_dir")
    echo "Packaging and pushing $chart_name..."
    
    # Package chart into a tarball
    helm package "$chart_dir" --destination ./packaged-charts
    
    # Push tarball to GDC Hosted OCI registry
    helm push "./packaged-charts/${chart_name}-*.tgz" oci://<gdc-harbor-domain>/charts
  fi
done
```
Once completed, update your [charts.yaml](file:///usr/local/google/home/andybubune/helm-iac/gdc-ag-foundations/bases/environments/dev/charts.yaml) to direct release values to point to `oci://<gdc-harbor-domain>/charts/`.
