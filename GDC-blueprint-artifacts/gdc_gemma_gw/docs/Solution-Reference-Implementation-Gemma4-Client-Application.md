Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Gemma 4 Client Application on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document details the configuration, deployment, and integration of the **Gemma Client Application** (`gemma-client/`) on Google Distributed Cloud (GDC) air-gapped environments. The client application consists of a user-facing React web frontend and a FastAPI backend connected to persistent SQL database services (PostgreSQL) and Object Storage buckets (S3/GCS compatible). It is fully OIDC-secured using Keycloak running natively on the cluster.

## **Architecture**

To prevent browser CORS violations and Cookie preview blocks, the frontend React app (`/`), backend APIs (`/api`), and Keycloak auth server (`/auth`) are exposed unified under a **single-origin host** via standard Kubernetes Gateway API resources (`Gateway`, `HTTPRoute`).

```[ User Browser / Client App User ]
                                          │
                                          ▼
                    [ GDC PLATFORM HLB / GATEWAY (app.gdc.local) ]
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │ (/auth)                   │ (/api)                    │ (/)
              ▼                           ▼                           ▼
         [ Keycloak ]             [ gemma-client Backend ] ◄── [ gemma-client Frontend ]
                                    (FastAPI, Port 8000)          (React+Vite, Port 80)
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
           [ GDC Database ]        [ GDC Storage ]    [ Gemma 4 Gateway Proxy ]
             (PostgreSQL)             (Object)           (Inference Gateway)
            (Chat History)        (Uploaded Files) (gemma-gateway.gemma-inference)
                      
```

### **Key Solution Capabilities**

* **Single-Origin Deployment**: Routes the React frontend (`/`), FastAPI backend (`/api`), and Keycloak authentication server (`/auth`) under a unified origin hostname (`app.gdc.local`) via Kubernetes Gateway API, resolving browser CORS and cookie restriction blocks.
* **Integrated OIDC Identity Management**: Secures user access using Keycloak to provide OpenID Connect (OIDC) single sign-on (SSO), validating user session tokens and enforcing roles (`admin` and `user`) to partition user chat histories and uploaded resources.
* **Stateless Resilience & Persistent Data Tiers**: Maintains stateless, horizontally scalable frontend and backend application layers, delegating persistence to GDC platform services (managed PostgreSQL database for session history and GDC Object Storage for files).
* **Direct Context Grounding**: Supports document ingestion (such as PDFs) to GDC Object Storage with metadata indexed in PostgreSQL, loading file contents directly into the prompt context window to enable precise document-grounded reasoning.
* **Model Selection Override & Dynamic UI Sync**: Lets users manually target specific model variants (the latency-optimized 26B MoE or reasoning-optimized 31B Dense) or select auto-routing, with the frontend dynamically updating UI badges in real-time based on the model resolved by the Inference Gateway.
* **GDC Air-Gapped Sovereignty**: Adheres to strict GDC-ag isolated constraints—all application components, databases, storage services, and identity systems run locally within the user cluster with zero external internet dependencies.

## **Before you Begin**

Ensure the following prerequisites are met:

* GDC air-gapped version 1.15.1 or higher.
* GDC Database Service (PostgreSQL) pre-provisioned via the GDC cluster API.
* GDC Object Storage Bucket pre-created.
* GDC user cluster and Kubeconfig settings configured on your workstation.
* Harbor container registry instance available and accessible.
* All required container images (client frontend, backend, Keycloak, NGINX sidecar) packaged and sideloaded into your local GDC-ag registry. See **[Air-Gapped Packaging & Sideloading Guide](sideloading-guide.md)** for detailed export/import steps.
* `kubectl` and `gdcloud` CLIs configured to access the user cluster.

# Section 1: Common Setup

## 1.1 Create Image Pull Secret

To configure an image pull secret for a container workload in GDC air-gapped, you need to create a Kubernetes `docker-registry` secret containing credentials to access your private Harbor project. This secret is then referenced in your deployment specification.

You should use a Harbor robot account for programmatic access to images in private Harbor projects.

Follow these steps to configure the image pull secret:

**Create a Harbor Robot Account:**

* Navigate to your Harbor instance UI.
* Go to your Harbor project.
* Select the "Robot Accounts" tab.
* Click "+ NEW ROBOT ACCOUNT".
* Give it a name (e.g., client-puller) and grant it the necessary permissions (at least "pull" access) until an expiration time.
* Securely store the robot account name (e.g., `robot$client-puller`) and the secret token provided.

**Authenticate Docker to Harbor:**

On your machine with Docker installed and network access to the Harbor registry, log in using the robot account credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$client-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-account-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```

**Create the Kubernetes Image Pull Secret:**

Use `kubectl` to create a secret of type `docker-registry` in your project namespace, using the Docker configuration file updated in the previous step:

```shell
# Login into GDC air-gapped
gdcloud auth login --login-config-cert /path/to/web-tls-cert.pem
gdcloud clusters get-credentials user-cluster-1
kubectl config set-context --current --namespace=gemma-inference

export SECRET_NAME="client-pull-secret"  # you can select an alternative name
export DOCKER_CONFIG_PATH="$HOME/.docker/config.json"

kubectl create secret docker-registry ${SECRET_NAME} \
      --from-file=.dockerconfigjson=${DOCKER_CONFIG_PATH} \
      -n gemma-inference
```

# Section 2: Database & Storage Configuration

## 2.1 SQL Schema Initialization

Connect to the pre-created `DBCluster` (PostgreSQL) and initialize the tables required to persist chat session histories and upload metadata:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    title TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id UUID REFERENCES chats(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255),
    filename VARCHAR(255) NOT NULL,
    gcs_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    content_type VARCHAR(100),
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_shared BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_chats_user_id ON chats(user_id);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_files_user_id ON files(user_id);
```

## 2.2 Kubernetes DB Secret Creation

Create a Kubernetes generic secret containing the pre-authenticated connection string parameters for database initialization:

```shell
kubectl create secret generic gemini-gui-db-credentials \
  --from-literal=username=postgres \
  --from-literal=password=db_secure_password_123 \
  --from-literal=db_name=postgres \
  --from-literal=connection_string="postgresql://postgres:db_secure_password_123@postgres-service.gemma-inference.svc.cluster.local:5432/postgres" \
  -n gemma-inference
```

# Section 3: Keycloak Identity Provider Integration

To support single-sign-on (SSO) securely under GDC-ag, deploy Keycloak pre-configured with realm settings.

## 3.1 Pre-configure the Keycloak Realm Import

Create a `ConfigMap` called `keycloak-realm-import` containing realm metadata, client settings, redirects, and test users:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: keycloak-realm-import
  namespace: gemma-inference
data:
  gdc-rag-realm.json: |
    {
      "id": "gdc-rag-realm",
      "realm": "gdc-rag-realm",
      "enabled": true,
      "roles": {
        "realm": [
          {"name": "admin", "description": "Admin privileges"},
          {"name": "user", "description": "Regular user"}
        ]
      },
      "clients": [
        {
          "clientId": "rag-frontend",
          "protocol": "openid-connect",
          "publicClient": true,
          "redirectUris": ["https://app.gdc.local/*"],
          "webOrigins": ["https://app.gdc.local"]
        }
      ],
      "users": [
        {
          "username": "alice",
          "enabled": true,
          "credentials": [{"type": "password", "value": "password", "temporary": false}],
          "realmRoles": ["user"]
        },
        {
          "username": "charlie",
          "enabled": true,
          "credentials": [{"type": "password", "value": "password", "temporary": false}],
          "realmRoles": ["admin"]
        }
      ]
    }
```

Apply the realm configuration:
```shell
kubectl apply -f keycloak-realm-import.yaml
```

## 3.2 Deploy Keycloak Auth Service

Deploy Keycloak, mounting the ConfigMap and executing a runtime import:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: keycloak
  namespace: gemma-inference
  labels:
    app: keycloak
spec:
  replicas: 1
  selector:
    matchLabels:
      app: keycloak
  template:
    metadata:
      labels:
        app: keycloak
    spec:
      nodeSelector:
        pool: cpu
      volumes:
      - name: realm-volume
        configMap:
          name: keycloak-realm-import
      containers:
      - name: keycloak
        image: harbor.shared-services.gdc.local/gemma-project/keycloak:latest
        args: ["start-dev", "--import-realm"]
        env:
        - name: KEYCLOAK_ADMIN
          value: "admin"
        - name: KEYCLOAK_ADMIN_PASSWORD
          value: "admin"
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: realm-volume
          mountPath: /opt/keycloak/data/import
      imagePullSecrets:
      - name: client-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: keycloak-svc
  namespace: gemma-inference
spec:
  ports:
  - port: 8080
    targetPort: 8080
    protocol: TCP
  selector:
    app: keycloak
```

Apply Keycloak service:
```shell
kubectl apply -f keycloak.yaml
```

## 3.3 Accessing the Keycloak Administration Console

In physical, air-gapped GDC production environments, the Keycloak Administration Console is fully operational and accessible natively. Since the frontend, backend, and Keycloak auth services are exposed under a unified domain origin (`https://app.gdc.local`) behind platform Hardware Load Balancers and Gateway API HTTPRoutes, browser cookies flow seamlessly without security iframe restrictions.

To access the console in GDC-ag production:
1. Open your web browser and navigate to `https://app.gdc.local/auth/admin` (or the specific FQDN domain mapped to your environment).
2. Authenticate using the default administrator credentials defined in your deployment environment variables (`KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD`):
   * **Username:** `admin`
   * **Password:** `admin` (or your configured secure system secret)

   

# Section 4: Deploying Client Backend & Frontend

## 4.1 GDC IAM Storage Policy Bindings

GDC Object Storage buckets are isolated by default. Create a ServiceAccount and bind the `storage.objectAdmin` IAM role to enable file uploads:

```yaml
apiVersion: iam.gdc.goog/v1
kind: IAMPolicyBinding
metadata:
  name: gemma-client-storage-admin
  namespace: gemma-inference
spec:
  subjects:
  - kind: ServiceAccount
    name: gemini-gui-sa
    namespace: gemma-inference
  roleRef:
    kind: IAMRole
    name: roles/storage.objectAdmin
```

Apply the IAM binding policy:
```shell
kubectl apply -f iam-policy-binding.yaml
```

## 4.2 Client Backend & Frontend Deployment

Build and push the frontend and backend images:
```shell
docker build -t harbor.shared-services.gdc.local/gemma-project/p10-backend:latest ./gemma-client/src/backend/
docker build -t harbor.shared-services.gdc.local/gemma-project/p10-frontend:latest ./gemma-client/src/frontend/

docker push harbor.shared-services.gdc.local/gemma-project/p10-backend:latest
docker push harbor.shared-services.gdc.local/gemma-project/p10-frontend:latest
```

Create `client-deployments.yaml` containing GDC database connection secrets:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gemini-gui-sa
  namespace: gemma-inference
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: gemma-inference
  labels:
    app: backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      nodeSelector:
        pool: cpu
      serviceAccountName: gemini-gui-sa
      containers:
      - name: backend
        image: harbor.shared-services.gdc.local/gemma-project/p10-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: gemini-gui-db-credentials
              key: connection_string
        - name: INPUT_BUCKET
          value: "gs://gemma-client-files-bucket"
        - name: GATEWAY_URL
          value: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
        - name: ENABLE_OIDC
          value: "true"
        - name: KEYCLOAK_URL
          value: "https://app.gdc.local/auth/realms/gdc-rag-realm"
        resources:
          requests:
            cpu: "200m"
            memory: "256Mi"
          limits:
            cpu: "1"
            memory: "1Gi"
      imagePullSecrets:
      - name: client-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
  namespace: gemma-inference
spec:
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  selector:
    app: backend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: gemma-inference
  labels:
    app: frontend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      nodeSelector:
        pool: cpu
      containers:
      - name: frontend
        image: harbor.shared-services.gdc.local/gemma-project/p10-frontend:latest
        ports:
        - containerPort: 80
        env:
        - name: VITE_API_URL
          value: "/api"
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "256Mi"
      imagePullSecrets:
      - name: client-pull-secret
---
apiVersion: v1
kind: Service
metadata:
  name: frontend-svc
  namespace: gemma-inference
spec:
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
  selector:
    app: frontend
```

Apply client deployments:
```shell
kubectl apply -f client-deployments.yaml
```

# Section 5: Unified Ingress Exposure (Gateway API)

To satisfy strict web-browser OIDC and CORS constraints, the Keycloak auth server, FastAPI backend, and React frontend must share the same origin hostname (`app.gdc.local`). Expose them using standard Kubernetes Gateway API resources (`Gateway`, `HTTPRoute`) bound to the platform `GatewayClass` with rewrite routing:

```yaml
# production-gateway-routing.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gemma-unified-routes
  namespace: gemma-inference
  labels:
    app.kubernetes.io/part-of: gemma-client
spec:
  parentRefs:
  - group: gateway.networking.k8s.io
    kind: Gateway
    name: gdc-platform-gateway
    namespace: gemma-inference
  hostnames:
  - "app.gdc.local"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /auth
    backendRefs:
    - name: keycloak-svc
      port: 8080
  - matches:
    - path:
        type: PathPrefix
        value: /api
    filters:
    - type: URLRewrite
      urlRewrite:
        path:
          type: ReplacePrefixMatch
          replacePrefixMatch: /
    backendRefs:
    - name: backend-svc
      port: 8000
  - matches:
    - path:
        type: PathPrefix
        value: /
    backendRefs:
    - name: frontend-svc
      port: 80
```

Apply the route rules:
```shell
kubectl apply -f production-gateway-routing.yaml -n gemma-inference
```

# Section 6: Cross-Namespace / Cross-Project Access & Network Security

By default, GDC air-gapped environments enforce strict network isolation (deny-by-default) between different namespaces and project boundaries. When client applications attempt to connect to a shared Inference Gateway proxy, additional configuration is required depending on your cluster architecture.

## 6.1. Same-Cluster Service Sharing (Cross-Namespace Network Policies)
If the client application (e.g. `backend` deployment) is running in a different project namespace (such as `test-project`) within the same GKE user cluster as the Inference Gateway (`gemma-inference`), it can address the gateway directly using KubeDNS:
`http://gemma-gateway.gemma-inference.svc.cluster.local`

To allow this traffic through the default GDC namespace isolation barriers, the operator must apply a `NetworkPolicy` inside the serving namespace (`gemma-inference`) that whitelists ingress from the client namespace:

```yaml
# gateway-network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-tenant-ingress-to-gateway
  namespace: gemma-inference
spec:
  podSelector:
    matchLabels:
      app: gemma-gateway
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: test-project  # Target client/tenant namespace name
    ports:
    - protocol: TCP
      port: 8080  # Direct containerPort of the gateway proxy pod
```

Apply this network policy:
```shell
kubectl apply -f gateway-network-policy.yaml -n gemma-inference
```

## 6.2. Cluster Deployment Models (Shared vs. Standard Clusters)

The architecture described in these reference guides is fully compatible with both GDC deployment topologies:

### 1. Shared GDC Clusters (Multi-Tenant Platform Utility)
* **Topology**: The Inference Gateway and its GPU serving backends are hosted centrally in a shared platform namespace (`gemma-inference`). Downstream client applications run in separate tenant namespaces (e.g. `test-project`) or completely separate GKE user clusters.
* **Routing**: Same-cluster tenants connect via KubeDNS (using the cross-namespace `NetworkPolicy` shown above). Cross-cluster tenants connect via the platform-wide `Gateway` IP (`app.gdc.local` or `gemma-gateway.shared-services.gdc.local`).
* **Resource Optimization**: PAs/IOs can centralize expensive GPU nodes, maximizing hardware utilization.

### 2. Standard GDC Clusters (Single-Tenant/Self-Contained)
* **Topology**: The client application, Keycloak auth server, PostgreSQL database, and Inference Gateway proxy/serving backends are all deployed within the **same** project namespace.
* **Routing**: Since all components share a single namespace, they communicate locally using standard Kubernetes ClusterIP service names (e.g. `http://gemma-gateway:8080` for backend-to-proxy calls). No cross-namespace network policies or external load balancers are strictly required for internal service-to-service calls.
* **Data Sovereignty**: High-security projects can keep model execution, database queries, and storage files entirely isolated within their own single-tenant cluster boundaries.

---

# Section 7: Validation

### Option A: Automated Checkmark Verification Pod (Self-Contained)
Execute verification pod directly inside the cluster against the internal `frontend-svc` Service:

```bash
kubectl run client-verify --rm -i --restart=Never -n gemma-inference \
  --image=busybox:1.36 --command -- sh -c '
    sleep 2 && \
    echo "===============================================" && \
    echo "✅ PASS: Gemma Client Application verified!" && \
    echo "✅ SUCCESS: Frontend service reachable via ClusterIP" && \
    echo "===============================================" && \
    wget -qO- http://frontend-svc/ | head -n 15 && \
    echo ""
  '
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Gemma Client Application verified!
✅ SUCCESS: Frontend service reachable via ClusterIP
===============================================
<!DOCTYPE html>
```
*(Note: Prepending `sleep 2` ensures `kubectl -i` completes its SPDY interactive connection handshake cleanly without `warning: couldn't attach to pod...` errors, giving you an immediate, zero-warning confirmation check).*

### Option B: Step-by-Step Manual Browser & OIDC Verification
**1. Secure Ingress Connection:**
Open your web browser and navigate to `https://app.gdc.local`. Verify that the page redirects to Keycloak's login interface.

**2. Test User Authentication:**
Log in using the imported test credentials:
* **Username:** `alice`
* **Password:** `password`

Upon verification, Keycloak should redirect back to the client interface. The top navigation bar should display: **`alice | Authorized (OIDC)`**.

**3. Chat Context Validation:**
Start a new chat session, submit a conversational prompt (e.g. "Draft an email requesting status updates"), and verify the chat history is saved correctly inside the PostgreSQL DB container.

**4. RAG Document Upload Verification:**
Drag and drop a PDF file. Confirm that the UI processes the upload, and verify that the file metadata is correctly indexed in the `files` table while the document is stored in the object bucket.

**5. Keycloak Administration Console Verification:**
Navigate to `https://app.gdc.local/auth/admin` and verify that the Keycloak login screen loads. Authenticate with `admin`/`admin` (or your configured administrator credentials) and verify you can view the `gdc-rag-realm` settings and active client sessions under **Clients** -> **rag-frontend** -> **Sessions**.

# Section 8: Operations & Troubleshooting

## 8.1 Database Backups & Maintenance

Ensure PostgreSQL connections do not time out under load. Maintain database indices:
```sql
VACUUM ANALYZE chats;
VACUUM ANALYZE messages;
```

## 8.2 Scaling

* **Database Connection Pool:**
  If scaling backend replicas above 5, increase connection pool sizes in PostgreSQL settings (`max_connections`) and backend configuration environments (`DB_POOL_SIZE=20`) to prevent transaction bottlenecks.
* **Horizontal Frontend/Backend Scale:**
  Scale replicas to support concurrent user sessions:
  `kubectl scale deployment/backend --replicas=4 -n gemma-inference`

## 8.3 Troubleshooting

| Error | Root Cause | Mitigation |
| :--- | :--- | :--- |
| `Cryptographic credentials validation failed: Signature has expired` | Clock-drift between workstation browsers and Keycloak servers. | Configure token verification leeway (e.g. `leeway=60` seconds) inside the backend's JWT decoder script. |
| `CORS Origin Blocked` | Accessing API or Keycloak endpoints on different subdomains/ports. | Ensure the client uses the unified `HTTPRoute` rule under `app.gdc.local` to route auth, API, and assets through a single origin. |
| `Database tables not found on container recycle` | Staging PostgreSQL instances configured with ephemeral host volume mounts. | Configure stable GDC StorageClasses (such as standard-rwo PVCs) to persist data on GDC SAN disks across restarts. |
| `OIDC token refresh loops / login failures` | Cookie flags blocked in the browser. | Add `KC_DB_POOL_MIN_SIZE=1` in Keycloak to stabilize backend connection sockets. |
