# ArgoCD

This procedure outlines how to connect **ArgoCD** to a **GDC (Google Distributed Cloud) Air-gapped** environment. In GDC Air-gapped, you typically interact with three distinct API endpoints to manage the fleet, the infrastructure, and the workloads.

## Prerequisites
* **Network Reachability:** Your ArgoCD cluster must have a network route to the GDC API endpoints (Global, Management, and User Shared).
* **DNS:** Ensure the FQDNs of these APIs are resolvable from the ArgoCD pods or use static IP addresses.
* **Kubeconfigs:** Complete the IaC bootstrap procedure described in the [tools/bootstrap/README.md](./../bootstrap/README.md). This will provide you with the necessary credentials, including CA certificates and API tokens, for the Global, Management, and User Shared clusters.


## Install ArgoCD
ArgoCD can be installed in one of the following environments:
- **External Cluster:** Using `microk8s` as an example.
- **User Standard Cluster:** Setup is similar to an external cluster.
- **User Shared Cluster:** Requires an Infrastructure Operator (IO) to install Custom Resource Definitions (CRDs).

### Install ArgoCD on External or Standard Cluster

This process follows the regular installation path for ArgoCD—there are no special modifications required.

Make sure that the container images required by ArgoCD are accessible from the cluster where you are installing ArgoCD.

```bash
# Clone the ArgoCD repository
git clone https://github.com/argoproj/argo-cd.git
cd argo-cd

# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f manifests/install.yaml
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
