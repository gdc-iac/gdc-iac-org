# ArgoCD

This procedure outlines how to connect **ArgoCD** to a **GDC (Google Distributed Cloud) Air-gapped** environment. In GDC Air-gapped, you typically interact with three distinct API endpoints to manage the fleet, the infrastructure, and the workloads.

## Prerequisites
* **Network Reachability:** Your ArgoCD cluster must have a network route to the GDC API endpoints (Global, Management, and User Shared).
* **DNS:** Ensure the FQDNs of these APIs are resolvable from the ArgoCD pods or use static IP addresses.
* **Kubeconfigs:** Complete the IaC bootstrap procedure described in the [tools/bootstrap/README.md](./../bootstrap/README.md). This will provide you with the necessary credentials, including CA certificates and API tokens, for the Global, Management, and User Shared clusters.

### Select ArgoCD installation target
ArgoCD can be installed in one of the following environments:
- **External Cluster:** Using `microk8s` as an example.
- **User Standard Cluster:** Setup is similar to an external cluster, and is described in the [INSTALL_STANDARD_CLUSTER.md](INSTALL_STANDARD_CLUSTER.md). You can use Managed Harbor Service for image mirroring as described in [tools/mirror-images/README.md](../mirror-images/README.md).
- **User Shared Cluster:** Requires an Infrastructure Operator (IO) to install Custom Resource Definitions (CRDs). The CRD manifests are located in [manifests/crds](https://github.com/argoproj/argo-cd/blob/stable/manifests/crds) and are required by ArgoCD server and UI to manage deployment configuration. For installation on shared cluster, use [namespace-install.yaml](https://github.com/argoproj/argo-cd/blob/stable/manifests/namespace-install.yaml).

### Prepare ArgoCD manifests
Clone the latest ArgoCD manifests to your working directory, as they will be updated to point to the private registry.
```bash
# Clone the ArgoCD repository
git clone https://github.com/argoproj/argo-cd.git
cd argo-cd
```
Select the deployment option and corresponding [manifest](https://github.com/argoproj/argo-cd/blob/stable/manifests/).

### Prepare container images for air-gapped environment
Follow the instructions in [tools/mirror-images/README.md](../mirror-images/README.md) to mirror ArgoCD images into Managed Harbor.

## Installation procedures

### Install ArgoCD on Standard Cluster
You can use [install.yaml](https://github.com/argoproj/argo-cd/blob/stable/manifests/install.yaml), a standard Argo CD installation with cluster-admin access (see [INSTALL_STANDARD_CLUSTER.md](INSTALL_STANDARD_CLUSTER.md) for standard cluster specifics). For production environments, consider using [High Availability setup](https://github.com/argoproj/argo-cd/tree/stable/manifests#high-availability).

Update image names in the ArgoCD manifests to use the private registry:
```bash
sed -i -E "s@(image:[[:space:]]+).*/@\1${REGISTRY:?}/${HARBOR_PROJECT:?}/@g" install.yaml
```

Make sure to update the manifest also to include:
```yaml
  imagePullSecrets:
      - name: harbor001-creds
```

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f install.yaml --server-side
```
### Install ArgoCD on User Shared Cluster
Shared cluster is a special cluster type in GDC that is used for deploying workloads. It is managed by an Infrastructure Operator (IO). To install ArgoCD on a user shared cluster, the required CRDs need to be installed on the shared cluster first and this requires IO permissions. The CRD manifests are located in [manifests/crds](https://github.com/argoproj/argo-cd/blob/stable/manifests/crds) directory.

After the CRDs are installed, you can install ArgoCD on the shared cluster using [namespace-install.yaml](https://github.com/argoproj/argo-cd/blob/stable/manifests/namespace-install.yaml). For production environments, consider using [High Availability setup](https://github.com/argoproj/argo-cd/tree/stable/manifests#high-availability).

Update image names in the ArgoCD manifests to use the private registry:
```bash
sed -i -E "s@(image:[[:space:]]+).*/@\1${REGISTRY:?}/${HARBOR_PROJECT:?}/@g" namespace-install.yaml
```

Make sure to update the manifest also to include:
```yaml
  imagePullSecrets:
      - name: harbor001-creds
```
```bash
# Install ArgoCD
kubectl apply -n ${PROJECT:?} -f namespace-install.yaml
```

## Register GDC Clusters in ArgoCD
In an air-gapped environment, it is best to register clusters using **Kubernetes Secrets** in the namespace where ArgoCD is installed (usually `argocd`).

### 1. Add Global API Cluster
The Global API is used for fleet-wide resources (e.g., Projects, Namespaces across the fleet).
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gdc-global-api-secret
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: gdc-global
  server: https://<GDC_GLOBAL_API_ENDPOINT>
  config: |
    {
      "bearerToken": "<TOKEN_FROM_STEP_1>",
      "tlsClientConfig": {
        "insecure": false,
        "caData": "<CA_CERT_FROM_STEP_1>"
      }
    }
```

### 2. Add Management API Cluster
The Management API is used for infrastructure-level resources (e.g., cluster lifecycle, node pools).
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gdc-mgmt-api-secret
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: gdc-management
  server: https://<GDC_MGMT_API_ENDPOINT>
  config: |
    {
      "bearerToken": "<TOKEN_FROM_STEP_1>",
      "tlsClientConfig": {
        "insecure": false,
        "caData": "<CA_CERT_FROM_STEP_1>"
      }
    }
```

### 3. Add User Cluster API
This is where your actual applications (Deployments, Services) will run.
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gdc-user-shared-secret
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: gdc-user-shared
  server: https://<GDC_USER_SHARED_API_ENDPOINT>
  config: |
    {
      "bearerToken": "<TOKEN_FROM_STEP_1>",
      "tlsClientConfig": {
        "insecure": false,
        "caData": "<CA_CERT_FROM_STEP_1>"
      }
    }
```


## Configure Internal Source Repositories
Since GDC is **air-gapped**, ArgoCD cannot pull from the public internet.

1.  **Git Repository:** Add your internal Git (e.g., GitLab/Gitea) to ArgoCD via **Settings > Repositories**.
2.  **Container Registry:** Ensure all manifests in Git point to your **local GDC Registry** (Harbor). 

## Create a Test Application
Verify the connection by deploying a simple resource to the User Shared Cluster.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gdc-connectivity-test
  namespace: argocd
spec:
  project: default
  source:
    repoURL: 'https://<INTERNAL_GIT>/gdc-apps.git'
    targetRevision: HEAD
    path: 'test-app'
  destination:
    server: 'https://<GDC_USER_SHARED_API_ENDPOINT>' # Must match the secret "server" field
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## Summary of API Usage in GDC
| Endpoint | ArgoCD Use Case |
| :--- | :--- |
| **Global API** | Managing Global-level resources: Organization, Projects, and IAM-like structures. |
| **Management API** | Zone-level resources: Clusters, Buckets, Harbors, Backups, Network Policies, and infrastructure/cluster config. |
| **User Cluster API** | Deploying standard Kubernetes workloads (Apps). |

> **Note:** In air-gapped environments, pay close attention to **Certificates**. GDC uses a custom internal CA, so the `caData` field in the Cluster Secret is mandatory for ArgoCD to trust the connection.
