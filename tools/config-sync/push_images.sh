#!/bin/bash

export IN_DIR="/mnt/c/temp/offline_packages/docker_images/"
export ORG_NAME="org-15357"
export ZONE="lux-central1-b"
export ROOT_ZONE="lux.clr"
export shared_infra_project_name="data-ets-mhs"
export nb_project="data-ets-shared-infra"
export mhs_project="data-ets-mhs"
export HARBOR_PASSWORD="REDACTED"
export ARTIFACT_REGISTRY=https://${shared_infra_project_name}-${nb_project}.${ORG_NAME}.${ZONE}.${ROOT_ZONE}
export USER="gdch-infra-operator-sdobrica-sa@opscenter.local"

echo "$HARBOR_PASSWORD" | docker login "$ARTIFACT_REGISTRY" -u "$USER" --password-stdin --tls-verify=false

export TARGET_HOST="${shared_infra_project_name}-${nb_project}.${ORG_NAME}.${ZONE}.${ROOT_ZONE}"

images=(
    "gcr.io/config-management-release/hydration-controller:v1.22.2"
    "gcr.io/config-management-release/reconciler:v1.22.2"
    "gcr.io/config-management-release/git-sync:v4.4.2-gke.3__linux_amd64"
    "gcr.io/config-management-release/gcenode-askpass-sidecar:v1.22.2"
    "gcr.io/config-management-release/oci-sync:v1.22.2"
    "gcr.io/config-management-release/helm-sync:v1.22.2"
    "gcr.io/config-management-release/otelcontribcol:v0.119.0-gke.2"
    "gcr.io/config-management-release/reconciler-manager:v1.22.2"
    "gcr.io/config-management-release/resource-group-controller:v1.22.2"
)

for image in "${images[@]}"; do
    
    # Extract the filename variables
    file_base="${image##*/}"
    safe_filename="${file_base/:/_}"
    
    # Assemble the final destination path
    TARGET_IMAGE="${TARGET_HOST}/${mhs_project}/${file_base}"

    echo "========================================"
    echo "Processing: ${file_base}"
    
    # Load the tarball into the local daemon
    echo " -> Loading from: ${IN_DIR}${safe_filename}.tar.gz"
    gunzip < "${IN_DIR}${safe_filename}.tar.gz" | docker load
    
    # Tag the image for Harbor
    echo " -> Tagging as: ${TARGET_IMAGE}"
    docker tag "${image}" "${TARGET_IMAGE}"
    
    # Push to Harbor (Again, --tls-verify=false is a Podman-specific flag)
    echo " -> Pushing to Harbor..."
    docker push "${TARGET_IMAGE}" --tls-verify=false
    
done

echo "========================================"
echo "All images successfully loaded, tagged, and pushed to Harbor!"
