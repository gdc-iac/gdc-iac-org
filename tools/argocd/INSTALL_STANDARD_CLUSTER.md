# Setup environment variables
```bash
export PROJECT="iac-root"
export HARBOR_PROJECT="iac"
export HARBOR_INSTANCE="harbor001"
```
You can create a Managed Harbor instance (see [INSTALL_HARBOR.md](../mirror-images/INSTALL_HARBOR.md) or use org-level harbor. 
```bash
export REGISTRY="harbor.org-12345.zone1-a.gdch.test"
export HARBOR_USER="admin"
export HARBOR_SECRET="KCXioUXR4zPVyY3N"
```
Note, that to use org-level harbor, the images needs to be signed to avoid an error:
```bash
│   Warning  Failed     9s    kubelet            Failed to pull image "harbor.org-12345.zone1-a.gdch.test/iac/argocd:latest": failed to pull a │
│ nd unpack image "harbor.org-12345.zone1-a.gdch.test/iac/argocd:latest": failed to copy: httpReadSeeker: failed open: unexpected status code  │
│ https://harbor.org-12345.zone1-a.gdch.test/v2/iac/argocd/manifests/sha256:fe3b76b7ee4acc292c3f6c7cc1afbf9d252d71f8842740921a5dad67bac6ef20:  │
│ 412 Precondition Failed - Server message: unknown: The image doesn't pass Cosign signature verification with err [no matching signatures:                  │
│ ].
```


# Login using Harbor CLI Secret
```bash
docker login -u "${HARBOR_USER}" -p "${HARBOR_SECRET}" "${REGISTRY}"
```
# Mirror ArgoCD images to harbor
```bash
../mirror-images/mirror_images.py \
  --manifest argo-cd/manifests/install.yaml \
  --registry ${REGISTRY}/${HARBOR_PROJECT}
```

## Manual image push:
```
docker pull quay.io/argoproj/argocd:latest
docker tag quay.io/argoproj/argocd:latest ${REGISTRY}/${HARBOR_PROJECT}/argocd:latest
docker push ${REGISTRY}/${HARBOR_PROJECT}/argocd:latest
```

# Set Org Admin cluster context
```bash
kubectl config set-context org-12345-admin-zone1-a-gdch_console-org-12345-zone1-a-google-gdch-test_org-12345-admin
```

```
kubectl auth whoami
ATTRIBUTE                        VALUE
Username                         system:serviceaccount:iac-root:iac001-sa
Groups                           [system:authenticated]
Extra: __AIS_token_issuer_zone   [zone1-a]
```
# Prepare cluster definition
```
export K8S_VERSION=$( kubectl get userclustermetadata.upgrade.private.gdc.goog -o=custom-columns=K8S-VERSION:.spec.kubernetesVersion | sort -n | tail -n1 )
#export MACHINE_TYPE=$( kubectl get virtualmachinetypes.virtualmachine.gdc.goog -n vm-system --no-headers | #awk '$2 == "true" && $1 ~ /-standard-/ {print $1}' | sort -V | head -n 1 )
export MACHINE_TYPE=n3-standard-8-gdc
```
# Create Argo CD cluster 
```bash
cat <<EOF > argocd-cluster.yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: argocd-cluster
  namespace: iac-root
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: "${K8S_VERSION}"
  nodePools:
  - name: default-node-pool
    machineTypeName: "${MACHINE_TYPE}"
    nodeCount: 1
  releaseChannel:
    channel: UNSPECIFIED
EOF
#  Apply the configuration
kubectl apply -f argocd-cluster.yaml
# Monitor progress
kubectl get cluster -niac-root --watch
```
Example output:
```
NAME             STATE         K8S VERSION
argocd-cluster   Reconciling   1.32.13-gke.100
....
argocd-cluster   Running   1.32.13-gke.100
```

# Get Argo CD cluster credentials
```bash
gdcloud clusters get-credentials argocd-cluster \
    --standard \
    --project=iac-root
```
Example cluster context is `iac-root-2ad0c4dd-zone1-a-gdch_console-org-12345-zone1-a-google-gdch-test_iac-root-2ad0c4dd`

# Configure TLS trust.
Sdandard cluster by default trusts org-level harbor. If using managed harbor, follow instructions in [INSTALL_HARBOR.md](../mirror-images/INSTALL_HARBOR.md) to configure trust store.

# Configure Image Pull credentials for project-scoped harbor
In GDC air-gapped, the local project-scoped Harbor registries require credentials to authorize image pulls. In case you see errors like:
```
│   Warning  Failed     17s (x2 over 31s)  kubelet            Failed to pull image "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/alpine": f │
│ ailed to pull and unpack image "harbor001-iac-root.org-12345.zone1-a.gdch.test/iac/alpine:latest": failed to resolve reference "harbor001-iac-r │
│ oot.org-12345.zone1-a.gdch.test/iac/alpine:latest": pull access denied, repository does not exist or may require authorization: authorization f │
│ ailed: no basic auth credentials 
```

You need to configure robot account and obtain pull credentials for the project-scoped harbor as shown in [INSTALL_HARBOR.md](../mirror-images/INSTALL_HARBOR.md). Create a docker-registry secret in ArgoCD namespace (default is argocd):
```bash
kubectl create secret docker-registry harbor001-creds  \
    --from-file=.dockerconfigjson=${HOME}/.docker/config.json \
    -n argocd
```

