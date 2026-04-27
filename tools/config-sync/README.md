# Config Sync Setup
1. Go through the [bootstrap process](../../tools/bootstrap/README.md). 
2. [Optional] Download latest `config-sync-manifest.yaml` for your setup from [Config Sync releases](https://github.com/GoogleContainerTools/kpt-config-sync/releases).

- [v.1.23.3](https://github.com/GoogleContainerTools/config-sync/releases/download/v1.23.3/config-sync-manifest.yaml)
- [v.1.24.0-rc.4](https://github.com/GoogleContainerTools/config-sync/releases/download/v1.24.0-rc.4/config-sync-manifest.yaml)

3. Create harbor instance in the `iac-root` project:

```
. ../bootstrap/config.sh
gdcloud harbor instances create ${IAC_ROOT}-mhs \
  --project=${IAC_ROOT:?}
gdcloud harbor harbor-projects create ${IAC_ROOT} \
--project=${IAC_ROOT:?} \
--instance=${IAC_ROOT:?}-mhs
```
4. Use `pull_images.py` script to pull the images from GCR to the local machine

Example usage:

```bash
python3 pull_images.py --manifest patched-config-sync-manifest-v.1.23.3.yaml --out-dir /tmp/config-sync-images
```

5. Push the images to the harbor instance:

```bash
python3 push_images.py --manifest patched-config-sync-manifest-v.1.23.3.yaml --img-dir /tmp/config-sync-images --harbor-registry <HARBOR_REGISTRY>
```


3. Apply the patch to the manifest file:

```bash
# Run the script to apply the patch and create patched-config-sync-manifest.yaml
./apply_patch.sh v.1.23.3.patch config-sync-manifest-v.1.23.3.yaml
```

5. Deploy Config Sync using kubectl, following the [documentation](https://docs.cloud.google.com/kubernetes-engine/config-sync/docs/how-to/installing-kubectl). 
Use  manifest file: [config-sync-manifest-gdc.yaml](config-sync-manifest-gdc.yaml)
    ```
    kubectl apply -f config-sync-manifest-gdc.yaml
    ```
 
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
