# Config Sync Setup

1. Obtain credentials for the substrate cluster where you will run Config Sync. For a simple test you can use microk8s. 
2. Deploy Config Sync using kubectl, following the [documentation](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-kubectl). Use  manifest file: [config-sync-manifest-gdc.yaml](config-sync-manifest-gdc.yaml)
    ```
    kubectl apply -f config-sync-manifest-gdc.yaml
    ```
3. Configure RepoSync CRD on substrate cluster and target clusters using manifest [reposync-crd.yaml](reposync-crd.yaml)

    ```
    kubectl apply -f config-sync-manifest-gdc.yaml
    ```
    **Note:**

    This one time action requires IO privileges to install CRD on global API cluster and management API clusters

4. Configure access secrets
    ```
    kubectl -n config-management-system create secret generic kubeconfigs \
    --from-file=global=[FILE NAME] \
    --from-file=zone1=[FILE NAME] 
    ```

    **Note:**
     Follow [documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#gdcloud) to create service account and obtain kubeconfig.

5. Configure GDC CA certificate

    kubectl -n config-management-system create secret generic certs \
    --from-file=[CA CERTIFICATE]

6. Configure synchronization on all clusters (substrate where Config Sync is running, Global API and each Management API).
    ```
    export GIT_REPO=...

    kubectl apply -f - << EOF
    # Global API
    apiVersion: v1
    kind: Namespace
    metadata:
    name: syncs
    ---
    apiVersion: configsync.gke.io/v1alpha1
    kind: RepoSync
    metadata:
    name: global
    namespace: syncs
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
    namespace: syncs
    spec:
    sourceFormat: unstructured
    git:
        repo: $GIT_REPO
        branch: main
        dir: zone1
        auth: none
    EOF
    ```