# Config Sync Setup
1. Go through the [bootstrap process](../../README.md)
1. Obtain credentials for the substrate cluster where you will run Config Sync. For a simple test you can use microk8s. 
2. Deploy Config Sync using kubectl, following the [documentation](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-kubectl). Use  manifest file: [config-sync-manifest-gdc.yaml](config-sync-manifest-gdc.yaml)
    ```
    kubectl apply -f config-sync-manifest-gdc.yaml
    ```
    **Note:**

    In order to deploy this manifest, following images are required:
    -   gcr.io/config-management-release/hydration-controller:v1.22.2
    -   gcr.io/config-management-release/reconciler:v1.22.2
    -   gcr.io/config-management-release/git-sync:v4.4.2-gke.3__linux_amd64
    -   gcr.io/config-management-release/gcenode-askpass-sidecar:v1.22.2
    -   gcr.io/config-management-release/oci-sync:v1.22.2
    -   gcr.io/config-management-release/helm-sync:v1.22.2
    -   gcr.io/config-management-release/otelcontribcol:v0.119.0-gke.2
    -   gcr.io/config-management-release/reconciler-manager:v1.22.2
    -   gcr.io/config-management-release/resource-group-controller:v1.22.2


gdcloud config set core/zone ""
gdcloud clusters get-credentials global-api
export shared_infra_project_name=data-ets-shared-infra
export nb_project=data-ets-001-001

for role in \
 harbor-instance-admin \
 harbor-project-creator \
 project-grafana-viewer \
 project-iam-admin \
 project-bucket-admin \
 project-bucket-object-admin \
 workload-viewer \
 backup-creator \
 project-networkpolicy-admin \
 project-vm-admin \
 project-vm-image-admin \
 custom-role-project-admin \
; do \
 gdcloud projects add-iam-policy-binding ${shared_infra_project_name:?} \
 --member="user:${IAC_USER:?}" \
 --role="$role";\
done


gdcloud harbor instances create ${shared_infra_project_name:?}-mhs \
  --project=${shared_infra_project_name:?}
gdcloud harbor harbor-projects create ${nb_project:?} \
--project=${shared_infra_project_name:?} \
--instance=${shared_infra_project_name:?}-mhs

Create scripts to migrate the images to the harbor instance and project.

cat <<'EOF' > /root/pull_save_images.sh
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
EOF

chmod +x /root/pull_save_images.sh
source /root/pull_save_images.sh


cat <<'EOF' > /root/push_2harbor_images.sh
#!/bin/bash

export IN_DIR="/mnt/c/temp/offline_packages/docker_images/"
export ORG_NAME="org-15357"
export ZONE="lux-central1-b"
export ROOT_ZONE="lux.clr"
export shared_infra_project_name="data-ets-shared-infra"
export nb_project="data-ets-001-001"
export HARBOR_PASSWORD="REDACTED"
export ARTIFACT_REGISTRY=https://${shared_infra_project_name}-mhs-${shared_infra_project_name}.${ORG_NAME}.${ZONE}.${ROOT_ZONE}
export USER="gdch-infra-operator-sdobrica-sa@opscenter.local"

echo "$HARBOR_PASSWORD" | docker login "$ARTIFACT_REGISTRY" -u "$USER" --password-stdin --tls-verify=false

export TARGET_HOST="${shared_infra_project_name}-mhs-${shared_infra_project_name}.${ORG_NAME}.${ZONE}.${ROOT_ZONE}"

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
    TARGET_IMAGE="${TARGET_HOST}/${nb_project}/${file_base}"

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
EOF

chmod +x /root/push_2harbor_images.sh
source /root/push_2harbor_images.sh


New Images list:

    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/resource-group-controller:v1.22.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/reconciler-manager:v1.22.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/otelcontribcol:v0.119.0-gke.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/helm-sync:v1.22.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/oci-sync:v1.22.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/gcenode-askpass-sidecar:v1.22.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/git-sync:v4.4.2-gke.3__linux_amd64
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/reconciler:v1.22.2
    -   data-ets-shared-infra-mhs-data-ets-shared-infra.org-15357.lux-central1-b.lux.clr/data-ets-001-001/hydration-controller:v1.22.2


Allow access to Harbor from other projects:

gdcloud config set core/zone ""
gdcloud clusters get-credentials global-api
kubectl apply -f - <<EOF
apiVersion: networking.global.gdc.goog/v1
kind: ProjectNetworkPolicy
metadata:
  namespace: ${shared_infra_project_name:?}
  name: allow-inbound-traffic-from-${nb_project:?}-to-mhs-service
spec:
  subject:
    subjectType: ManagedService
    managedServices:
      matchTypes:
      - 'mhs'
  ingress:
  - from:
    - projectSelector:
        projects:
          matchNames:
          - ${nb_project:?}
EOF


3. Create RepoSync CRD on substrate cluster and target clusters using manifest [reposync-crd.yaml](reposync-crd.yaml)

    - Global API
    ```
    k-site2-org-15357-global-admin-api apply -f reposync-crd.yaml
    ```
    - Each Zone Management API
    ```
    k-site2-org-15357-admin-zone-management apply -f reposync-crd.yaml
    ```

    **Note:**

    This one time action requires IO privileges to create CRD on global API cluster and management API clusters. IO should use IaC to create this resources and ensure it's persistence.  

3. Create IAM and RBAC roles that allow managing RepoSync objects. Use the provided manifests [sync-admin-iam-role.yaml](sync-admin-iam-role.yaml) and [sync-admin-iam.yaml](sync-admin-role.yaml):

    - Global API IAMRole
    ```
    k-site2-org-15357-global-admin-api apply -f sync-admin-iam-role.yaml
    ```
    - Each Zone Management API RBAC
    ```
    k-site2-org-15357-admin-zone-management apply -f sync-admin-role.yaml
    ```
    **Note:**

    This one time action requires IO privileges. IO should use IaC to create these resources and ensure their persistence. 

4. Configure access secrets to store [kubeconfig created during the bootstrap](../../README.md) in the user cluster (where config-sync is running):
    ```
    export KUBECONFIG=${CLUSTER_NAME}=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
    kubectl -n config-management-system create secret generic kubeconfigs \
    --from-file=global=${CA_CERT_PATH}${IAC_PROJECT}_${IAC_SA}-global-api.kubeconfig \
    --from-file=${ZONE}=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}.kubeconfig \
    --from-file=${CLUSTER_NAME}=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
    ```

    **Note:**
     Follow [documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#gdcloud) to create service account and obtain kubeconfig.

5. Configure GDC CA certificate

    ```
    curl -k  https://${GDCH_CONSOLE}/.well-known/certificate-authority -o cachain.crt
    kubectl -n config-management-system create secret generic certs \
    --from-file=cachain.crt
    ```

6. Create objects for synchronisation state tracking:
    - Global API
    ```
    export GIT_REPO=...

    kubectl apply -f - << EOF
    apiVersion: configsync.gke.io/v1alpha1
    kind: RepoSync
    metadata:
    name: global
    namespace: ${IAC_PROJECT}
    spec:
    sourceFormat: unstructured
    git:
        repo: $GIT_REPO
        branch: main
        dir: global
        auth: none
    EOF
    ```
    - Each Zone Management API
    ```
    export GIT_REPO=...

    kubectl apply -f - << EOF
    # Management API for each zone
    apiVersion: configsync.gke.io/v1alpha1
    kind: RepoSync
    metadata:
    name: zone1
    namespace: ${IAC_PROJECT}
    spec:
    sourceFormat: unstructured
    git:
        repo: $GIT_REPO
        branch: main
        dir: zone1
        auth: none
    EOF
    ```
7. Enable synchronisation - create RepoSyncs on the cluster where Config Sync is running:
    - Global API
    ```
    export GIT_REPO=...

    kubectl apply -f - << EOF
    apiVersion: v1
    kind: Namespace
    metadata:
    name: ${IAC_PROJECT}
    ---
    apiVersion: configsync.gke.io/v1alpha1
    kind: RepoSync
    metadata:
    name: global
    namespace: ${IAC_PROJECT}
    spec:
    sourceFormat: unstructured
    git:
        repo: $GIT_REPO
        branch: main
        dir: global
        auth: none
    ---
    # Management API for each zone
    apiVersion: configsync.gke.io/v1alpha1
    kind: RepoSync
    metadata:
    name: zone1
    namespace: ${IAC_PROJECT}
    spec:
    sourceFormat: unstructured
    git:
        repo: $GIT_REPO
        branch: main
        dir: zone1
        auth: none
    EOF
    ```
