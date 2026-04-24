# Config Sync Setup
1. Go through the [bootstrap process](../../tools/bootstrap/README.md). 
2. Make sure the required images are accessible from the cluster where you want to deploy config sync, e.g. from your local host for testing purposes. 

    Following config sync images are required:
    -   gcr.io/config-management-release/hydration-controller:v1.22.2
    -   gcr.io/config-management-release/reconciler:v1.22.2
    -   gcr.io/config-management-release/git-sync:v4.4.2-gke.3__linux_amd64
    -   gcr.io/config-management-release/gcenode-askpass-sidecar:v1.22.2
    -   gcr.io/config-management-release/oci-sync:v1.22.2
    -   gcr.io/config-management-release/helm-sync:v1.22.2
    -   gcr.io/config-management-release/otelcontribcol:v0.119.0-gke.2
    -   gcr.io/config-management-release/reconciler-manager:v1.22.2
    -   gcr.io/config-management-release/resource-group-controller:v1.22.2

    
2. Deploy Config Sync using kubectl, following the [documentation](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-kubectl). Use  manifest file: [config-sync-manifest-gdc.yaml](config-sync-manifest-gdc.yaml)
    ```
    kubectl apply -f config-sync-manifest-gdc.yaml
    ```
 

gdcloud harbor instances create ${shared_infra_project_name:?}-mhs \
  --project=${shared_infra_project_name:?}
gdcloud harbor harbor-projects create ${nb_project:?} \
--project=${shared_infra_project_name:?} \
--instance=${shared_infra_project_name:?}-mhs

Create scripts to migrate the images to the harbor instance and project.

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

    This action requires IO privileges. IO should use IaC to create these resources and ensure their persistence. 

4. Install config-sync:

   export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-global-api.kubeconfig

    kubectl apply -f - <<EOF
    apiVersion: networking.global.gdc.goog/v1
    kind: ProjectNetworkPolicy
    metadata:
    namespace: iac-root
    name: allow-inbound-traffic-from-to-mhs-service
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
            - iac-root
    EOF

   export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig

   kubectl -n iac-root apply -f config-sync-manifest-gdc.yaml

5. Configure access secrets to store [kubeconfig created during the bootstrap](../../README.md) in the user cluster (where config-sync is running):
    ```
    export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
    kubectl -n iac-root create secret generic kubeconfigs \
    --from-file=global=${CA_CERT_PATH}${IAC_PROJECT}_${IAC_SA}-global-api.kubeconfig \
    --from-file=${ZONE}=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}.kubeconfig \
    --from-file=${CLUSTER_NAME}=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
    ```

    **Note:**
     Follow [documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#gdcloud) to create service account and obtain kubeconfig.

6. Configure GDC CA certificate

    ```
    curl -k  https://${GDCH_CONSOLE}/.well-known/certificate-authority -o ${CA_CERT_PATH:?}cachain.crt
    export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
    kubectl -n iac-root create secret generic certs \
    --from-file=${CA_CERT_PATH:?}cachain.crt
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
