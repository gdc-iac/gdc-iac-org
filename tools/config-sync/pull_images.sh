#!/bin/bash

export OUT_DIR="/mnt/c/temp/offline_packages/docker_images/"

mkdir -p "${OUT_DIR}"

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
    
    # Extract just the filename and format it safely
    file_base="${image##*/}"
    safe_filename="${file_base/:/_}"
    
    # Print a status message so you know what the script is currently doing
    echo "Processing: ${image}"
    echo " -> Saving to: ${OUT_DIR}${safe_filename}.tar.gz"

    # Pull the image
    docker image pull "${image}"
    
    # Save and compress the image
    docker save "${image}" | gzip > "${OUT_DIR}${safe_filename}.tar.gz"
    
    echo " -> Done."
    echo "----------------------------------------"

done

echo "All images have been downloaded and saved successfully!"
