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

gdcloud harbor instances create ${shared_infra_project_name:?}-mhs \
  --project=${shared_infra_project_name:?}
 gdcloud harbor harbor-projects create ${nb_project:?} \
    --project=${shared_infra_project_name:?} \
    --instance=${shared_infra_project_name:?}-mhs


3. Create RepoSync CRD on substrate cluster and target clusters using manifest [reposync-crd.yaml](reposync-crd.yaml)

    - Global API
    ```
    kubectl apply -f reposync-crd.yaml
    ```
    - Each Zone Management API
    ```
    kubectl apply -f reposync-crd.yaml
    ```

    **Note:**

    This one time action requires IO privileges to create CRD on global API cluster and management API clusters. IO should use IaC to create this resources and ensure it's persistence.  

3. Create IAM and RBAC roles that allow managing RepoSync objects. Use the provided manifests [sync-admin-iam-role.yaml](sync-admin-iam-role.yaml) and [sync-admin-iam.yaml](sync-admin-role.yaml):

    - Global API IAMRole
    ```
    kubectl apply -f sync-admin-iam-role.yaml
    ```
    - Each Zone Management API RBAC
    ```
    kubectl apply -f sync-admin-role.yaml
    ```
    **Note:**

    This one time action requires IO privileges. IO should use IaC to create these resources and ensure their persistence. 

4. Configure access secrets to store [kubeconfig created during the bootstrap](../../README.md):
    ```
    kubectl -n config-management-system create secret generic kubeconfigs \
    --from-file=global=${IAC_PROJECT}_${IAC_SA}-global-api.kubeconfig \
    --from-file=zone1=${IAC_PROJECT}_${IAC_SA}-zone1.kubeconfig
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
