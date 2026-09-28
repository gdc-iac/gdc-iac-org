Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **GDC-ag Resilient Architecture Blueprints \-md for artifact building**

## **Architectural Assumptions & Prerequisites**

These blueprints are "Day 2" application deployment patterns. They rely on a fully operational GDC environment where "Day 0" (initial supply chain) and "Day 1" (platform configuration) activities have been successfully completed by Platform Administrators.

Before attempting to use any of the blueprints verify that your environment meets the following core assumptions:

### **1\. Platform Readiness (Day 1 Complete)**

* **Operational GKE Clusters:** These patterns **do not** include instructions for creating Kubernetes clusters. It is assumed that healthy, conformant GKE User Clusters have already been provisioned and assigned to your project.  
* **Enabled Managed Services:** Platform services specifically the **Database Service** (PostgreSQL HA), **Vertex AI** (Training/Serving), and pre-trained APIs (OCR, Translation) must be available, enabled, and healthy at the platform level before they can be consumed by these patterns.

### **2\. Air-Gapped Supply Chain (Day 0 Complete)**

Because the environment has no internet access, these patterns assume all necessary dependencies have already been transported across the air-gap:

* **Mirrored Artifacts:** All container images (middleware like Kafka, application code), Helm charts, and VM boot images referenced in the patterns must exist in the organization's trusted internal registry (Harbor).  
* **Model Weights:** For AI patterns, base model artifacts (like Gemma or TensorFlow standard models) must already be scanned and available in GDC Object Storage.

### **3\. Physical Infrastructure Capabilities**

* **Hardware for High Availability:** Patterns utilizing availability-type: ZONAL\_HA assume the underlying GDC hardware is deployed across physically separated fault domains (e.g. separate racks with independent power). If deployed on single-rack hardware, these configurations will be accepted by the API but cannot provide true physical redundancy.  
* **Specialized Compute Quota:** AI/ML patterns assume your user project has been allocated sufficient quota for specialized hardware (e.g. NVIDIA GPUs) required for large language model inference.

### **4\. Developer prerequisites**

If you wish to implement any of these patterns, ensure the following is complete:

1.  **CLIs Installed:** Your workstation has gdcloud, kubectl, and docker installed.
2.  **Authentication:** You are authenticated to your GDC environment (gdcloud auth login) and you have [configured the Docker CLI to use your GDC identity](https://cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/platform-application/pa-ao-operations/configure-docker-authentication#sign-in-docker). Ensure Docker is configured to push to your organization's internal Harbor registry.
3.  You have the **appropriate IAM roles** granted to you for the services you need to grant permissions and developer roles to create resources in the target projects (e.g. my-gdc-project).
4.  **GDC Resources:** Your GDC project (my-gdc-project) and GKE user cluster and/or vanilla clusters are already created.
5.  **Local Files:** You have your application's container image (e.g. my-app-v1.2.0.tar) and its Kubernetes manifests (e.g deployment.yaml) on your workstation.
6.  **For IaC Only:** You have a local Git server and your GitOps tool (Config Sync or Argo CD) is installed on your user cluster, configured to watch your repository.
7.  Patterns that **use GKE** assume that you have a GKE cluster ready to use.

All patterns use the built-in Prometheus service for observability and monitoring.

Patterns include detailed implementation guidance using two methods:

1.  **Manual (CLI):** Interactive steps using gdcloud and kubectl for quick validation and learning.
2.  **IaC (GitOps):** Declarative manifests for production deployments managed by Config Sync or Argo CD.

### **5\. Platform Readiness Checks**

Before starting, verify your environment is ready by running these commands and that the expected results are returned

*   **Hardware Resilience:** Ensure you have multiple zones available for HA.
*   Bash

```
gdcloud compute zones list
# Verify at least 2 zones exist and are 'UP'
```

*   **Kubernetes Cluster:** Ensure you are targeted to your User Cluster.
*   Bash

```
kubectl get nodes
# Should return Ready nodes in your user cluster, NOT the admin cluster.
```

*   **Registry Access:** Ensure Docker can pull from your internal registry.
*   Bash

```
docker pull harbor.gdc.local/library/busybox:latest
# Must succeed without internet access.
```

### **6\. Required "Day 0" Artifacts**

You must have these artifacts mirrored to your internal harbor.gdc.local registry before deploying the patterns:

*   **Container Images:** library/nginx:latest, library/postgres:14, vertex/tf-serving:latest, bitnami/kafka:latest.
*   **Helm Charts:** kafka (Bitnami or Confluent), kube-prometheus-stack.
*   **VM Images:** A standard Linux base image (e.g., RHEL 8 or Ubuntu 20.04) must be imported into GDC VM images.

## 

## **One-Time GitOps Setup (Required for Option B)**

If you plan to use the **Option B (GitOps)** path for any pattern, your GitOps tool (Config Sync or Argo CD) must be configured to trust your internal Git repository.

### **Step 1: Establish Trust**

You need the root CA certificate that signed your internal GitLab/Gitea's SSL certificate. Save it locally as internal-ca.crt.

Bash

```

# 1. Create namespace if it doesn't exist
kubectl create ns my-gdc-project --dry-run=client -o yaml | kubectl apply -f -

# 2. Trust the internal Git provider's CA
kubectl create secret generic git-ssl-ca \
  --namespace=my-gdc-project \
  --from-file=ca.crt=./internal-ca.crt

# 3. Create Git read-only credentials
kubectl create secret generic git-creds \
  --namespace=my-gdc-project \
  --from-literal=username='git-reader' \
  --from-literal=token='<YOUR_READ_ONLY_TOKEN>'

```

### **Option A: Config Sync (RepoSync)**

Apply this manifest once to your cluster to start syncing from your infra repo.

```yaml
apiVersion: configsync.gke.io/v1beta1
kind: RepoSync
metadata:
  name: infra-sync
  namespace: my-gdc-project
spec:
  sourceType: git
  git:
    repo: "https://gitlab.gdc.local/my-org/gdc-blueprints.git"
    branch: "main"
    dir: "manifests/"
    auth: "token"
    secretRef:
      name: "git-creds"
    caCertSecretRef:
      name: "git-ssl-ca"
```

*Verify success:* `kubectl get reposync -n my-gdc-project` should show status SYNCED.

### **Option B: Argo CD**

If using Argo CD, you must register the repository and create an Application.

**1. Register Repository (with Credentials)**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: blueprint-repo-creds
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repository
stringData:
  type: git
  url: https://gitlab.gdc.local/my-org/gdc-blueprints.git
  username: git-reader
  password: <YOUR_READ_ONLY_TOKEN>
  # If using internal CA, you may need to add 'tlsClientCertData' or configure Argo CD to trust the CA.
  insecure: "true" 
```

**2. Create Application**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: gdc-blueprints
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://gitlab.gdc.local/my-org/gdc-blueprints.git
    targetRevision: HEAD
    path: manifests/
  destination:
    server: https://kubernetes.default.svc
    namespace: my-gdc-project
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

---

## **Pattern 1: Resilient 3-Tier Web Application**

Use Case: Standard web app requiring separation of concerns: Presentation (Web), Logic (App), and Data (DB)

## Networking & Ingress

### Kubernetes Gateway API (Recommended)
As Ingress Nginx is being retired, GDC blueprints are transitioning to the Kubernetes Gateway API.

**Gateway Resource**: Defines the entry point for traffic into the cluster.
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: my-gateway
spec:
  gatewayClassName: gdc-gateway
  listeners:
  - name: http
    protocol: HTTP
    port: 80
```

**HTTPRoute Resource**: Defines how traffic is routed from the Gateway to Services.
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-route
spec:
  parentRefs:
  - name: my-gateway
  rules:
  - matches:
    - path: { type: PathPrefix, value: / }
    backendRefs:
    - name: my-service
      port: 80
```

### LoadBalancer Service (Legacy)
**Design and Resilience Pattern:**

1. **Web/Presentation Tier:**  
   * **GDC Platform Service:** Deployed as a containerized workload (e.g., Nginx, Apache) on a **GDC GKE Cluster**.  
   * **Resilience:** Achieved by running multiple replicas of the web server pods managed by a GKE Deployment. A GKE Service (of type LoadBalancer) exposes the application within the GDC network, providing load balancing across the pods.  
2. **Application/Logic Tier:**  
   * **GDC Platform Service:** Deployed as a containerized application (e.g., Java Spring Boot, Python Flask, Go) on the same **GDC GKE Cluster**.  
   * **Resilience:** GKE Deployments manage multiple replicas of the application pods. Horizontal Pod Autoscaling (HPA) can be used (if GDC MHS provides the metrics) to scale pods based on CPU/memory. Communication with the web tier and database tier is managed via GKE Services.  
3. **Data Tier:**  
   * **GDC Platform Service:** A stateful workload using the **GDC Database Service**. For this pattern, a high-availability **PostgreSQL** cluster is provisioned.  
   * **Resilience:** The GDC Database Service manages the cluster's replication (e.g., primary-standby) . The [High availability configuration](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/db-configure-ha) allows manual failover to the standby replica  
4. **Storage (Static Assets):**  
   * **GDC Platform Service:** Static assets (images, CSS, JS) are stored in a **GDC Storage** bucket (Object Storage).  
   * **Resilience:** GDC Object Storage provides built-in data durability and redundancy within the GDC instance.  
5. **Security:**  
   * **GDC Platform Service:** Application secrets (API keys, DB credentials) are stored and managed by the **GDC KMS**. The GDC Database Service integrates with KMS for encryption at rest

Resilience: Database manual failover (Zonal HA); Web tier stateless scaling.

### **Required IAM Permissions**

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Database Admin:** To provision the PostgreSQL HA cluster.
    *   `roles/db.cluster.creator`
*   **GKE Developer:** To deploy applications, services, and load balancers to the GKE cluster.
    *   `roles/gke.developer`

### **Step 1: Provision Data Tier (HA Database)**

**Option A: Manual (CLI)**

Bash

```

gdcloud database clusters create tier3-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=2 --memory=8Gi --storage-size=50Gi

```

**Option B: GitOps** \-\> manifests/db/tier3-db.yaml

YAML

```

apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: tier3-db
  namespace: my-gdc-project
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA
  resources:
     requests: { cpu: "2", memory: "8Gi" }
  storage: { size: "50Gi" }

```

### **Step 2: Deploy Application Tier (Business Logic)**

Prerequisite: Database must be READY so the secret tier3-db-credentials exists.

This tier connects to the DB and exposes an internal API only.

**Option A: Manual (kubectl)**

1. Save YAML below to app-tier.yaml.  
2. Run: kubectl apply \-f app-tier.yaml

**Option B: GitOps** \-\> manifests/apps/app-tier.yaml

YAML

```

apiVersion: apps/v1
kind: Deployment
metadata:
  name: logic-tier
  namespace: my-gdc-project
spec:
  replicas: 2
  selector: { matchLabels: { app: logic } }
  template:
    metadata: { labels: { app: logic } }
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values: ["logic"]
            topologyKey: "kubernetes.io/hostname"
      containers:
      - name: api-server
        image: harbor.gdc.local/my-org/api-server:v1
        env:
        - name: DB_HOST
          valueFrom: { secretKeyRef: { name: tier3-db-credentials, key: host } }
        - name: DB_PASS
          valueFrom: { secretKeyRef: { name: tier3-db-credentials, key: password } }
---
apiVersion: v1
kind: Service
metadata:
  name: logic-svc
  namespace: my-gdc-project
spec:
  type: ClusterIP
  selector: { app: logic }
  ports: [ { protocol: TCP, port: 8080, targetPort: 8080 } ]

```

### **Step 3: Deploy Web Tier (Presentation)**

This tier handles user traffic and proxies requests to the internal Logic tier.

**Option A: Manual (kubectl)**

1. Save YAML below to web-tier.yaml.  
2. Run: kubectl apply \-f web-tier.yaml

**Option B: GitOps** \-\> manifests/apps/web-tier.yaml

YAML

```

apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-tier
  namespace: my-gdc-project
spec:
  replicas: 3
  selector: { matchLabels: { app: web } }
  template:
    metadata: { labels: { app: web } }
    spec:
      containers:
      - name: nginx
        image: harbor.gdc.local/library/nginx:latest
        env:
        # Points to the internal K8s DNS of the logic tier service
        - name: API_UPSTREAM
          value: "http://logic-svc.my-gdc-project.svc.cluster.local:8080"
---
apiVersion: v1
kind: Service
metadata:
  name: web-lb
  namespace: my-gdc-project
spec:
  type: LoadBalancer
  selector: { app: web }
  ports: [ { protocol: TCP, port: 80, targetPort: 80 } ]

```

## **Pattern 2: High-Availability ML/AI Inference**

Use Case: Serving ML models with guaranteed uptime even if a node fails.

**Design & Resilience Pattern:**

1. **Model Serving:**  
   * **GDC Platform Service:** Pre-trained models are deployed to **GDC Vertex AI**. Vertex AI handles the serving runtime, versioning, and scaling of the inference endpoints. Vertex AI Endpoint with minimum replica count \> 1  
   * **Resilience:** Vertex AI is a managed service designed for availability, managing the underlying compute and scaling to meet prediction request loads.  
2. **Model & Artifact Storage:**  
   * **GDC Platform Service:** Trained models (e.g., TensorFlow SavedModel, ONNX), datasets, and training artifacts are stored in **GDC Storage** (Object Storage).  
   * **Resilience:** GDC Object Storage provides built-in data durability and redundancy within the GDC instance.  
3. **Pre/Post-processing Services (Optional):**  
   * **GDC Platform Service:** If data requires transformation before being sent to Vertex AI (or after receiving a prediction), these lightweight logic components are deployed as microservices on a **GDC GKE Cluster**.  
   * **Resilience:** Managed as stateless, replicated Deployments on GKE.  
4. **Security:**  
   * **GDC Platform Service:** **GDC KMS** is used to encrypt model artifacts at rest in GDC Storage and to manage keys used by the Vertex AI service.

### **Required IAM Permissions**

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Storage Admin:** To create GDC Storage buckets and upload model artifacts.
    *   `roles/storage.objectAdmin`
*   **AI Developer:** To create, upload, and deploy models and endpoints on Vertex AI.
    *   `roles/ai.developer` (or a combination of `roles/ai.endpoint.creator`, `roles/ai.model.uploader`, and `roles/ai.endpoint.deployer`)

### **Step 1: Stage Model Artifacts**

**Option A: Manual (CLI)**

Bash

```

# 1. Create Bucket
gdcloud storage buckets create gs://ml-models --project=my-gdc-project
# 2. Upload Artifacts (assuming local folder ./my-model-v1 exists)
gdcloud storage cp -r ./my-model-v1/ gs://ml-models/v1/

```

**Option B: GitOps** \-\> manifests/storage/ml-bucket.yaml

YAML

```

apiVersion: object.gdc.goog/v1
kind: Bucket
metadata:
  name: ml-models
  namespace: my-gdc-project
spec:
  storageClass: standard

```

*(GitOps Note: After sync, you must still manually run the gdcloud storage cp command above.)*

### **Step 2: Deploy HA Endpoint**

**Option A: Manual (CLI)**

Bash

```

# 1. Create Endpoint
gdcloud ai endpoints create ha-endpoint --project=my-gdc-project
# 2. Upload Model (links artifacts to serving container)
gdcloud ai models upload my-model-v1 \
  --project=my-gdc-project \
  --artifact-uri=gs://ml-models/v1/ \
  --container-image-uri=harbor.gdc.local/vertex/tf-serving:latest
# 3. Deploy with HA (min-replica=2 is crucial)
gdcloud ai endpoints deploy-model ha-endpoint \
  --project=my-gdc-project \
  --model=my-model-v1 \
  --display-name=v1-ha \
  --min-replica-count=2 \
  --machine-type=n2-standard-4-gdc

```

**Option B: GitOps** \-\> manifests/ai/ha-endpoint.yaml

YAML

```

apiVersion: aiplatform.gdc.goog/v1
kind: Endpoint
metadata:
  name: ha-endpoint
  namespace: my-gdc-project
---
apiVersion: aiplatform.gdc.goog/v1
kind: Model
metadata:
  name: my-model-v1
  namespace: my-gdc-project
spec:
  artifactUri: gs://ml-models/v1/
  containerSpec:
    imageUri: harbor.gdc.local/vertex/tf-serving:latest
---
apiVersion: aiplatform.gdc.goog/v1
kind: DeployedModel
metadata:
  name: v1-ha-deployment
  namespace: my-gdc-project
spec:
  endpointRef: { name: ha-endpoint }
  modelRef: { name: my-model-v1 }
  dedicatedResources:
    minReplicaCount: 2 # Ensures HA
    machineSpec: { machineType: n2-standard-4-gdc }

```

---

## **Pattern 3: Legacy VM \+ Modern Database**

Use Case: Lift-and-shift legacy apps that can't be containerized but need a modern DB.

**Design & Resilience Pattern:**

1. **Legacy Application VM:**  
   * **GDC Platform Service:** The legacy application (e.g., a Windows Server-based application or a monolithic Linux binary) is deployed onto a virtual machine using the **GDC VM Runtime**.  
   * **Resilience:** The VM Runtime provides basic infrastructure-level availability. For application-level resilience, you would rely on traditional methods like in-guest clustering or load balancing between multiple VMs (if the app supports it).  
   * **GDC Platform Service:** A high-availability **PostgreSQL** cluster is provisioned using the **GDC Database Service**. This serves as the high-throughput, resilient database for both modern and legacy applications.  
   * **Resilience:** PostgreSQL is designed for high availability with zonal standby replicas, requiring a manual trigger for failover.  
3. **VM Data Storage:**  
   * **GDC Platform Service:** Virtual machine disks are provisioned using **GDC Storage (Block Storage)**. Shared filesystems for clustered VMs can use **GDC Storage (File Storage)**.  
   * **Resilience:** GDC Block and File Storage provide resilient, persistent storage for the GDC VMs.  
4. **Bridge to Modern Apps:**  
   * **GDC Platform Service:** Applications running on **GDC GKE Clusters** can securely access the PostgreSQL database and interact with the legacy VM application via standard GDC networking.

### **Required IAM Permissions**

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Network Admin:** To create VPC networks and subnets for the VM.
    *   `roles/compute.networkAdmin`
*   **Database Admin:** To provision the PostgreSQL HA cluster.
    *   `roles/db.cluster.creator`
*   **Compute Admin:** To create the virtual machine instance.
    *   `roles/compute.instanceAdmin.v1`

### **Step 1: Create Infrastructure**

**Option A: Manual (CLI)**

Bash

```

# Network for the VM
gdcloud compute networks create vm-net --project=my-gdc-project --subnet-mode=custom
gdcloud compute networks subnets create vm-subnet --network=vm-net --range=10.1.0.0/24 --region=region-1

# High Performance HA Database
gdcloud database clusters create legacy-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=4 --memory=16Gi --storage-size=100Gi

```

**Option B: GitOps** \-\> manifests/infra/legacy-infra.yaml

YAML

```

apiVersion: networking.gdc.goog/v1
kind: Network
metadata:
  name: vm-net
  namespace: my-gdc-project
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: legacy-db
  namespace: my-gdc-project
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA
  resources:
     requests: { cpu: "4", memory: "16Gi" }
  storage: { size: "100G" }

```

### **Step 2: Provision VM**

*Prerequisite: Run gdcloud compute images list to find your exact image name.*

**Option A: Manual (CLI)**

Bash

```

gdcloud compute instances create app-vm-01 \
  --project=my-gdc-project \
  --zone=zone-1 \
  --machine-type=n2-standard-8-gdc \
  --image-project=gradec-images --image-family=ubuntu-2004 \
  --subnet=vm-subnet

```

**Option B: GitOps** \-\> manifests/vm/app-vm.yaml

YAML

```

apiVersion: virtualmachine.compute.gdc.goog/v1
kind: VirtualMachine
metadata:
  name: app-vm-01
  namespace: my-gdc-project
spec:
  compute: { machineType: n2-standard-8-gdc }
  storage:
    disks:
    - boot: true
      # Update this source image path based on your 'gdcloud compute images list' output
      source: { image: projects/gradec-images/global/images/family/ubuntu-2004 }
  networkInterfaces: [ { subnetwork: vm-subnet } ]

```

---

## **Pattern 4: Event-Driven Pipeline (Kafka)**

Use Case: Decoupled microservices using a message bus for durability.

**Design & Resilience Pattern:**

1. **Event Bus (Message Queue):**  
   * **OSS Component:** GDC air-gapped does not have a native "Pub/Sub" style service, you would deploy a resilient message queue like **Kafka** onto a **GDC GKE Cluster**.  
     * Note Kafka is available as a  managed service in the GDC air-gapped marketplace  
   * **Resilience:** This is managed at the application layer. Kafka can be deployed in clustered configurations on GKE, using GKE stateful sets and persistent volumes (backed by **GDC Block Storage**) to ensure message durability and high availability.  
2. **Event Producers:**  
   * **GDC Platform Service:** Applications or services running on **GDC GKE Clusters** or **GDC VM Runtime** publish messages to the OSS event bus.  
   * **Resilience:** Handled by the application logic (e.g. retry mechanisms).  
3. **Event Consumers (Workers):**  
   * **GDC Platform Service:** Deployed as scalable, containerized applications on a **GDC GKE Cluster**.  
   * **Resilience:** These are typically stateless workers managed by a GKE Deployment. They consume messages from the queue. GKE's Horizontal Pod Autoscaler (HPA) can be configured (using custom metrics from the queue) to scale the number of workers based on the queue depth, ensuring timely processing.  
4. **Data Persistence:**  
   * **GDC Platform Service:** Workers persist their results to a **GDC Database Service** (PostgreSQL HA) or write artifacts to **GDC Storage (Object)**.  
   * **Resilience:** Provided by the managed GDC data services.

Resilience: Kafka StatefulSet (3 nodes); Consumers (stateless deployments).

### **Required IAM Permissions**

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **Database Admin:** To provision the PostgreSQL HA cluster for results.
    *   `roles/db.cluster.creator`
*   **GKE Admin/Developer:** To deploy the Kafka Helm chart (which includes StatefulSets and PersistentVolumeClaims) and the consumer application. A more privileged role like `roles/gke.admin` may be required for the initial Helm installation of stateful services.
    *   `roles/gke.admin` or `roles/gke.developer`

### **Step 1: Deploy Kafka & Persistence**

**Option A: Manual (CLI/Helm)**

Bash

```

# 1. Durable storage for final results
gdcloud database clusters create event-db \
  --project=my-gdc-project --database-version=POSTGRESQL_14 --availability-type=ZONAL_HA

# 2. Kafka Cluster (Helm)
# Ensure you point to your INTERNAL registry for the chart and images
helm install kafka oci://harbor.gdc.local/charts/kafka \
  --namespace my-gdc-project \
  --set replicaCount=3 \
  --set zookeeper.replicaCount=3 \
  --set persistence.enabled=true \
  --set image.registry=harbor.gdc.local \
  --set image.repository=bitnami/kafka

```

Option B: GitOps \-\> manifests/db/event-db.yaml

(Deploy DB via GitOps. Recommend deploying Kafka via Manual Helm above to avoid complex air-gapped Helm-controller setup).

YAML

```

apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: event-db
  namespace: my-gdc-project
spec:
  version: POSTGRESQL_14
  availabilityType: ZONAL_HA

```

### **Step 2: Deploy Consumers**

**Option A: Manual (kubectl)**

1. Save YAML below to consumer.yaml.  
2. Run kubectl apply \-f consumer.yaml.

**Option B: GitOps** \-\> manifests/apps/consumer.yaml

YAML

```

apiVersion: apps/v1
kind: Deployment
metadata:
  name: kafka-consumer
  namespace: my-gdc-project
spec:
  replicas: 2
  selector: { matchLabels: { app: consumer } }
  template:
    metadata: { labels: { app: consumer } }
    spec:
      containers:
      - name: worker
        image: harbor.gdc.local/my-org/consumer-app:v1.0
        env:
        # Assumes Helm created a service named 'kafka'
        - name: KAFKA_BROKERS
          value: "kafka.my-gdc-project.svc.cluster.local:9092"
        - name: DB_CONN
          valueFrom: { secretKeyRef: { name: event-db-credentials, key: connection_string } }

```

---

## **Pattern 5: Resilient Hybrid LLM Gateway [DEPRECATED]**

> [!CAUTION]
> **DEPRECATED PATTERN**: Pattern 5 (Resilient Hybrid LLM Gateway) is **deprecated** as of Blueprint Version 1.2. Applications (Patterns 6, 7, 9, 10) now natively interface directly with either the **Gemma Inference Gateway** (`gdc_gemma_gw` / vLLM / Ollama) or **GDC Gemini AI Gateway**. Dedicated proxy gateways (Pattern 5) are no longer required for multi-provider routing.

**Use Case:** Failover for GenAI apps if the primary platform model is unreachable.

**Design & Resilience Strategy:**

1. **The Gateway Service:** A new, lightweight microservice (e.g., in Python/Go) is deployed onto a **GDC GKE Cluster**. This service is deployed with multiple replicas for high availability and is exposed via a GKE Service (ClusterIP) to other applications within GDC.  
2. **Primary LLM (Gemini):** The GDC platform provides Gemini via the **GDC Vertex AI (Gemini API)**. This is a managed, resilient service endpoint.  
3. **Failover LLM (Gemma):** The open-source Gemma model is imported into the **GDC Vertex AI Model Registry** and deployed as a **GDC Vertex AI Endpoint**. This leverages the platform's managed, auto-scaling, and resilient custom model serving.  
4. **Resilient Failover Logic:**  
   * Agentic workloads (like Archetypes 6 & 7\) send their prompts to the *Gateway Service* endpoint, not directly to the LLMs.  
   * The Gateway's internal logic first attempts to call the **GDC Vertex AI (Gemini API)**.  
   * If this call fails (e.g., HTTP 5xx error, network timeout), the logic catches the exception, logs the error, and automatically retries the *exact same prompt* against the **GDC Vertex AI (Gemma Endpoint)**.  
   * This ensures that even if the primary Gemini service has a temporary issue, the agent's "brain" seamlessly fails over to the locally-hosted model, providing high availability for reasoning tasks

### **Required IAM Permissions**

To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **GKE Developer:** To deploy the gateway application, service, and configmap to the GKE cluster.
    *   `roles/gke.developer`
*   **AI Invoker:** The service account used by the gateway pods will need permission to call the Vertex AI endpoints. While not a user permission, it's a critical part of the setup.
    *   `roles/ai.invoker`

### **Step 1: Deploy Failover Model**

Use **Pattern 2** instructions to deploy the Gemma model to an Endpoint named gemma-failover.

### **Step 2: Deploy Gateway**

**Option A: Manual (kubectl)**

1. Save YAML below to gateway.yaml.  
2. Run kubectl apply \-f gateway.yaml.

**Option B: GitOps** \-\> manifests/apps/llm-gateway.yaml

YAML

```

apiVersion: v1
kind: ConfigMap
metadata:
  name: gateway-conf
  namespace: my-gdc-project
data:
  PRIMARY_URL: "https://vertex-ai.gdc.local/gemini"
  FAILOVER_URL: "http://gemma-failover.my-gdc-project.svc.cluster.local"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-gateway
  namespace: my-gdc-project
spec:
  replicas: 2
  selector: { matchLabels: { app: gateway } }
  template:
    metadata: { labels: { app: gateway } }
    spec:
      containers:
      - name: proxy
        image: harbor.gdc.local/my-org/llm-gateway:latest
        envFrom:
        - configMapRef: { name: gateway-conf }
---
apiVersion: v1
kind: Service
metadata:
  name: llm-gateway
  namespace: my-gdc-project
spec:
  selector: { app: gateway }
  ports: [ { port: 80, targetPort: 8080 } ]

```

---

## **Pattern 6: Resilient RAG Agent**

**Use Case:** Document processing pipeline using platform AI APIs. This is a modern approach to a RAG solution using an agentic pattern.

### **Design & Resilience Strategy**

This pattern describes a modern, resilient, agentic RAG solution for a Google Cloud air-gapped environment, designed to answer questions about a private document corpus.

> [!IMPORTANT]
> **Document Corpus Scope & Query Handling**:
> * **Document-Centric Design**: Pattern 6 is specifically built to answer questions grounded in the user's uploaded/indexed document corpus stored in PostgreSQL (`pgvector`).
> * **Not Optimized for Generic Queries**: This pattern is **not** an open-ended general chat agent. If a user asks generic or out-of-scope questions without uploading relevant documents (or before the ingestion job runs), the agent's semantic search will return zero matching context chunks and will trigger a fallback error: `"Sorry, I encountered an error processing your request."`

> [!NOTE]
> **LLM Gateway Dependency & Migration Path**:
> * **Primary Gateway (`gdc_gemma_gw`)**: By default, this pattern depends on the self-hosted **Gemma Inference Gateway** (`../gdc_gemma_gw`), listening on HTTP port 80 (`http://gemma-gateway.<namespace>.svc.cluster.local:80/v1`).
> * **Migration to Native GDC Gemini AI Gateway**: To migrate from Gemma Gateway to GDC Gemini AI Gateway or Vertex Gemini, set `LLM_PROVIDER="gemini"`, `LLM_GATEWAY_URL="https://ai-gateway.shared-services.gdc.local/v1"`, and `GEMINI_MODEL="google/gemini-3.5-flash"` in `manifests/apps/query-service.yaml` and `manifests/apps/ingest-job.yaml`.

* **Document Ingestion:** A GKE CronJob periodically scans a GDC Storage (Object) bucket. It coordinates a pre-processing pipeline:  
  1. **Source Triage:** Identifies file types.  
  2. **Speech-to-Text:** If audio (e.g., .mp3, .wav), it calls the **GDC Vertex Text-to-Speech service** (or a dedicated STT service) to transcribe it.  
  3. **Image-to-Text:** If an image or PDF, it calls the **GDC Vertex OCR service** to extract text.  
  4. **Translation:** If the extracted text is not in the target language, it calls the **GDC Vertex Translation service**.  
* **Embedding & Vector Storage:** The (now-processed) text is passed to the ingestion job's embedding service, which:  
  1. Converts text chunks to embeddings.  
  2. Stores embeddings in GDC Database Service (PostgreSQL with `pgvector`).  
* **Agent Service (Inference):** A GKE service using A2A, ADK, and MCP.  
* **Agent Logic (RAG):**  
  1. A user query is received.  
  2. The service calls its *own* embedding service to vectorize the *query*.  
  3. It queries PostgreSQL to retrieve relevant document chunks.  
  4. It combines the query and context into a new prompt.  
  5. It sends this prompt to the LLM Gateway—either the **Gemma Inference Gateway** (`../gdc_gemma_gw`) or **GDC Gemini AI Gateway**—for a synthesized answer.  
* **Resilience:** The agent and ingestion services are stateless (replicas on GKE). All dependencies (Storage, PostgreSQL, Gemma Gateway / GDC Gemini Gateway, and the OCR/Translation/T2S services) are managed, high-availability GDC platform components.

### **Required IAM Permissions**

This pattern requires permissions for both the **user** deploying the application and the **service account** the application runs as.

**1. User Permissions:**
To deploy the resources, your user account will need the following GDC IAM roles:

*   **IAM Admin:** To create a new service account (`rag-sa`) and grant it project-level roles.
    *   `roles/iam.serviceAccountAdmin`
    *   `roles/project.iamAdmin`
*   **GKE Developer:** To deploy the CronJob and ServiceAccount to the GKE cluster.
    *   `roles/gke.developer`

**2. Service Account Permissions:**
The `rag-sa` service account itself will be granted the following roles by the user during setup, which it uses at runtime to call other GDC services:

*   `roles/ai.ocr.developer`
*   `roles/ai.translation.developer`

### **Step 1: Configure IAM**

You must explicitly grant your workloads permission to use GDC pre-trained APIs.

**Option A: Manual (CLI)**

Bash

```

kubectl create sa rag-sa -n my-gdc-project
gdcloud iam service-accounts add-iam-policy-binding rag-sa --project=my-gdc-project --role=Role/ai-ocr-developer
gdcloud iam service-accounts add-iam-policy-binding rag-sa --project=my-gdc-project --role=Role/ai-translation-developer

```

**Option B: GitOps** \-\> manifests/iam/rag-permissions.yaml

YAML

```

apiVersion: v1
kind: ServiceAccount
metadata:
  name: rag-sa
  namespace: my-gdc-project
---
apiVersion: iam.gdc.goog/v1
kind: ProjectPolicy
metadata:
  name: rag-bindings
  namespace: my-gdc-project
spec:
  bindings:
  - role: Role/ai-ocr-developer
    members: [ serviceAccount:rag-sa ]
  - role: Role/ai-translation-developer
    members: [ serviceAccount:rag-sa ]

```

### **Step 2: Deploy Ingestion Job**

**Option A: Manual (kubectl)**

1. Save YAML below to ingest.yaml.  
2. Run kubectl apply \-f ingest.yaml.

**Option B: GitOps** \-\> manifests/apps/ingest-job.yaml

YAML

```

apiVersion: batch/v1
kind: CronJob
metadata:
  name: doc-ingest
  namespace: my-gdc-project
spec:
  schedule: "*/15 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: rag-sa  # Must match Step 1
          containers:
          - name: ingest
            image: harbor.gdc.local/my-org/rag-ingest:v1
            env:
            - name: INPUT_BUCKET
              value: "gs://raw-docs"
          restartPolicy: OnFailure

```

---

## **Pattern 7: Agentic Data Analyst**

**Use Case:** LLM Agent querying a SQL database securely. This agent acts as a data analyst, capable of querying structured databases to answer natural language questions (e.g., "How many units did we sell in the last quarter?").

**Design & Resilience Strategy:**

1. **Agent Service:** A microservice deployed on a **GDC GKE Cluster**.  
2. **Logic (OSS):** The service runs the **Agent Development Kit (ADK)**, an OSS framework optimized for GDC. ADK implements the ReAct loop and uses **Model Context Protocol (MCP)** for tool integration (SQL toolkit) and **Agent2Agent (A2A)** for communication.  
3. **Target Database:** The agent is given secure, read-only access to a production or replica database, such as the **GDC Database Service (PostgreSQL HA)**.  
4. **Security:** The agent's database credentials are securely injected from **GDC KMS**.  
5. **Agent Logic (ReAct):**  
   * User asks a question.    *   The agent service (ADK) calls the LLM backend—either the **Gemma Inference Gateway** (`../gdc_gemma_gw`) or **GDC Gemini AI Gateway**—to *reason* and *plan* (e.g., "I need to write and execute a SQL query").  
   * The agent *acts* by using its SQL toolkit to execute the query against the **GDC Database Service**.  
   * It gets the raw data result (e.g., \[5,482\]).    *   It calls the LLM Gateway again to *reason* and synthesize the raw data into a natural language answer (e.g., "You sold 5,482 units in the last quarter.").  
6. **Resilience:** The agent service is stateless and replicated on GKE. The LLM backend (Gemma Gateway or GDC Gemini Gateway) is resilient, and the target database is a managed, HA GDC service.

### **Day 0 Prerequisites (Air-Gap Transfer)**

As ADK, A2A, and MCP are open-source components, they must be ingested into the air-gapped environment before use:
1.  **Source Code/Libraries:** Download the ADK, A2A, and MCP libraries from GitHub/PyPI.
2.  **Packaging:** Package them as Python wheels or container images.
3.  **Transfer:** Scan and transfer the artifacts to the internal GDC repositories (Harbor for images, internal PyPI for libraries) via the standard Day 0 supply chain process.

### **Required IAM Permissions**

**1. User Permissions:**
To deploy the resources for this pattern, your user account will need the following GDC IAM roles granted in your target project:

*   **GKE Developer:** To deploy the agent's Deployment and Secret to the GKE cluster.
    *   `roles/gke.developer`

**2. Agent Runtime Permissions:**
The service account used by the `sql-agent` pods will need permissions to access the resources it queries. This includes:

*   **Database Access:** Read-only access to the target SQL database. This is handled via the Kubernetes secret in this pattern, but in a production scenario, you might grant the GKE service account an IAM role like `roles/db.viewer`.
*   **LLM Gateway Access:** Network access to the LLM Gateway service (Pattern 5).

### **Step 1: Create Read-Only Credentials**

*Security Note: Never give an LLM agent admin DB credentials.*

**Option A: Manual (CLI)**

Bash

```

kubectl create secret generic db-ro-creds \
  --namespace=my-gdc-project \
  --from-literal=username=analyst_ro \
  --from-literal=password='<SECURE_PASSWORD>'

```

**Option B: GitOps** \-\> manifests/security/db-secret.yaml

YAML

```

apiVersion: v1
kind: Secret
metadata:
  name: db-ro-creds
  namespace: my-gdc-project
type: Opaque
# Values must be base64 encoded: echo -n 'my-password' | base64
data:
  username: YW5hbHlzdF9ybw==
  password: U2VjdXJlUGFzc3dvcmQ=

```

### **Step 2: Deploy Agent**

**Option A: Manual (kubectl)**

1. Save YAML below to agent.yaml.  
2. Run kubectl apply \-f agent.yaml.

**Option B: GitOps** \-\> manifests/apps/sql-agent.yaml

YAML

```

apiVersion: apps/v1
kind: Deployment
metadata:
  name: sql-agent
  namespace: my-gdc-project
spec:
  replicas: 2
  selector: { matchLabels: { app: agent } }
  template:
    metadata: { labels: { app: agent } }
    spec:
      containers:
      - name: langchain
        image: harbor.gdc.local/my-org/sql-agent-adk:v1
        env:
        - name: DB_USER
          valueFrom: { secretKeyRef: { name: db-ro-creds, key: username } }
        - name: DB_PASS
          valueFrom: { secretKeyRef: { name: db-ro-creds, key: password } }

```

---

## **Pattern 8: Closed-Loop MLOps**

**Use Case:** Automated model retraining upon drift detection in air-gapped environments.

### **Design & Resilience Strategy**

This pattern establishes a closed-loop MLOps process to automatically retrain and redeploy a machine learning model when its performance degrades in production.

1.  **Monitoring & Alerting:**
    *   **OSS Components:** A **Prometheus** stack is deployed to the GKE cluster to scrape performance metrics from the model serving endpoint.
    *   **Drift Detection:** An alert is configured in **Alertmanager** (part of the Prometheus stack) to fire when a key metric (e.g., prediction accuracy, latency, or data drift) crosses a predefined threshold.
    *   **Trigger:** Alertmanager is configured to send a webhook to an external system (the CI/CD platform) when the "ModelDrift" alert is firing.

2.  **Automated Retraining Pipeline:**
    *   **CI/CD System:** A platform like **GitLab CI** receives the webhook from Alertmanager, triggering a new pipeline job.
    *   **Retraining Job:** The pipeline executes a script that:
        1.  Pulls the latest training data (e.g., using DVC from GDC Storage).
        2.  Runs the model training process to create a new model version.
        3.  Pushes the new model artifacts back to a model registry or GDC Storage.

3.  **Automated Canary Deployment:**
    *   **OSS Component:** **Argo Rollouts** is used to manage the deployment of the model serving application on GKE.
    *   **Progressive Delivery:** The CI/CD pipeline, after the retraining job succeeds, triggers Argo Rollouts to start a canary deployment. It updates the model serving deployment to use the new model container image.
    *   **Analysis & Rollback:** Argo Rollouts gradually shifts traffic to the new version while querying Prometheus for performance metrics. If the new model performs well, it is fully rolled out. If it fails the analysis, Argo Rollouts automatically rolls back to the previous stable version.

### **Required IAM Permissions**

This pattern involves cluster-wide tooling and a CI/CD pipeline, requiring distinct, high-privilege roles.

**1. User Permissions (for Toolchain Setup):**
To deploy cluster-wide tools like Prometheus and Argo Rollouts, your user account will need administrative permissions on the GKE cluster:

*   **GKE Cluster Admin:** To install Helm charts that create Custom Resource Definitions (CRDs) and manage resources across all namespaces.
    *   `roles/gke.clusterAdmin`

**2. CI/CD Pipeline Permissions:**
The service principal or service account used by your CI/CD system (e.g., GitLab) will need the following roles to execute the retraining pipeline:

*   **Storage Reader:** To pull the latest training data.
    *   `roles/storage.objectViewer`
*   **Storage Writer:** To push newly trained model artifacts.
    *   `roles/storage.objectCreator`
*   **GKE Developer:** To trigger the Argo Rollouts canary deployment by updating the image.
    *   `roles/gke.developer`

### **Step 1: Deploy Toolchain**

**Option A: Manual (Helm)**

Bash

```

helm install prometheus oci://harbor.gdc.local/charts/kube-prometheus-stack -n monitoring --create-namespace
helm install argo-rollouts oci://harbor.gdc.local/charts/argo-rollouts -n argo-rollouts --create-namespace

```

### **Step 2: Configure Pipeline Trigger**

Add this job to your internal CI/CD system (e.g., GitLab CI) to close the loop.

*.gitlab-ci.yml snippet:*

YAML

```

retrain_on_drift:
  stage: retrain
  # This job is triggered via API call from Prometheus Alertmanager
  only:
    variables:
      - $TRIGGER_SOURCE == "alertmanager"
  script:
    # 1. Pull data
    - dvc pull gs://ml-data/latest.dvc
    # 2. Retrain & Push artifacts
    - python train.py
    - gdcloud storage cp new_model.pb gs://models/vNext/
    # 3. Trigger Canary Deployment
    - kubectl argo rollouts set image model-serving container=harbor.gdc.local/model:vNext

```


---

## **Pattern 9: Sovereign Notebook (NotebookLM)**

**Use Case:** Deploying a secure, multi-user, RAG-enabled workspace similar to NotebookLM in an air-gapped environment.

### **Design & Resilience Strategy**

1.  **Application Tier:**
    *   **OSS Component:** "AnythingLLM" or "Open Notebook" is deployed as a scalable implementation on **GDC GKE Cluster**.
    *   **Resilience:** Multiple replicas managed by a Deployment.
2.  **Vector Database:**
    *   **GDC Platform Service:** A high-availability **GDC Database Service (PostgreSQL)** is used to store vector embeddings.
    *   **Resilience:** Zonal HA configuration handles failover.
3.  **Document Storage:**
    *   **GDC Platform Service:** Processed documents (PDFs, etc.) are stored in **GDC Storage (Object)**.
    *   **Resilience:** Built-in durability of GDC Object Storage.
4.  **Security & Sovereignty:**
    *   **Egress Control:** Kubernetes NetworkPolicies block all internet egress, ensuring data sovereignty.
    *   **Identity:** **ServiceIdentity** binds the application to GDC services securely.

### **Required IAM Permissions**

To deploy this pattern:

*   **Database Admin:** To create the sovereign DBCluster.
    *   `roles/db.cluster.creator`
*   **GKE Developer:** To deploy the application and NetworkPolicies.
    *   `roles/gke.developer`

### **Step 1: Deploy Sovereign Infra**

**Option A: Manual (kubectl)**

```bash
kubectl apply -f manifests/gdc/resources.yaml
kubectl apply -f manifests/gdc/iam-backup.yaml
```

**Option B: GitOps**

Commit `manifests/gdc/` to your repository.

### **Step 2: Deploy Application**

**Option A: Manual (Helm)**

```bash
helm upgrade --install notebook ./example-app/anythingllm -f example-app/anythingllm/values-gdc.yaml
```

**Option B: GitOps**

Use Argo CD to sync the application manifest or Helm chart.

---

## **Pattern 11: Resilient Secret Management with HashiCorp Vault**

Use Case: A centralized, high-availability, and secure enclave for managing secrets on GDC Air-Gapped leveraging Hardware KMS Auto-Unseal and Raft.

**Design & Resilience Strategy:**
1. **Dynamic Secret Store:** Vault is deployed inside the GDC environment instead of static K8s secrets.
2. **Auto-Unseal via Hardware KMS:** Uses GDC KMS to implement auto-unseal, removing the need for manual key entering during pod rotation.
3. **Availability:** Raft Consensus backed by PVC storage allows 3-pod highly available deployment.
4. **Integration Options:** Works elegantly via Sidecar Injection (Vault Agent Mutating Webhook) or External Secrets.

### **Required IAM Permissions**
*   **KMS Admin:** `roles/cloudkms.admin`

### **Step 1: Create Core GDC Infrastructure**

**Manual (gdcloud CLI)**

```bash
gdcloud kms key-rings create vault-ring --location=zone-1
gdcloud kms keys create vault-unseal-key --key-ring=vault-ring --purpose=encryption
gdcloud kms keys add-iam-policy-binding vault-unseal-key \
    --key-ring=vault-ring --location=zone-1 \
    --member="serviceAccount:my-gdc-project.svc.id.goog/my-gdc-project/vault-kms-sa" \
    --role="roles/cloudkms.encrypterDecrypter"
```

### **Step 2: Deploy Vault via Helm**

```bash
helm install vault hashicorp/vault -f manifests/helm/values.yaml
```

---

## **Pattern 12: Identity and Access Management (Keycloak)**

Use Case: Centralized authentication, SSO, and RBAC proxying for applications in an air-gapped GDC environment using Keycloak.

**Design & Resilience Strategy:**
1. **Identity Provider:** Keycloak is deployed as an HA cluster on a **GDC GKE Cluster**.
2. **Backend Persistence:** Uses the managed **GDC Database Service** (PostgreSQL HA) to store users, roles, and session states resiliently across zones.
3. **Decoupled Architecture:** Acts as a standalone identity service. Applications integrate with it dynamically via OIDC (e.g., via `react-oidc-context`). For instructions on integrating it with patterns like P6 and P7 without disrupting their core architecture, refer to `docs/keycloak_integration_guide.md`.

### **Required IAM Permissions**
*   **Database Admin:** `roles/db.cluster.creator`
*   **GKE Developer:** `roles/gke.developer`

### **Step 1: Create Database Backend**

```bash
gdcloud database clusters create keycloak-db \
  --project=my-gdc-project \
  --database-version=POSTGRESQL_14 \
  --availability-type=ZONAL_HA \
  --cpu=2 --memory=8Gi --storage-size=100Gi
```

### **Step 2: Deploy Keycloak via Helm**
*(Requires fetching DB connection details from the namespace secret first)*

```bash
helm upgrade --install keycloak oci://harbor.gdc.local/charts/keycloak \
  --namespace my-gdc-project \
  -f manifests/helm/values.yaml \
  --set externalDatabase.host=$DB_HOST \
  --set externalDatabase.password=$DB_PASSWORD
```

---

## **Pattern 13: Resilient GDC Developer Environment (gdc-dev)**

> **Version:** 1.5  
> **Status:** Production Reference Implementation  
> **Default Configuration:** Sovereign In-Pod Multi-Agent AI Swarm & Dual-Port Sovereign Admin Console Enabled by Default

Use Case: Provisioning dynamic, containerized cloud developer environment workspace instances on demand for software developers on GDC air-gapped infrastructure.

**Design & Resilience Strategy:**
1. **Ingress Modernization:** Standard **Kubernetes Gateway API (`gateway.networking.k8s.io/v1`)** using a GDC Platform `GatewayClass` (`gdc-dev-gateway` pattern) alongside a standalone GDC Platform LoadBalancer service.
2. **In-Pod Multi-Agent Swarm (Default by Design):** Full collaborative 3-agent developer swarm (📐 Architect, 💻 Coder, 🔍 Reviewer) with tool isolation and least privilege active out of the box.
3. **Dedicated Port Architecture (Port 8080 vs 8081):** Developer IDE sessions run on Port 8080 (`dev_auth_user`), while the Sovereign Admin & Telemetry Console runs on Port 8081 (`admin_auth_user`) with zero session collision.
4. **Enterprise SSO Identity & PKI:** Keycloak OIDC integration with role-based access control (RBAC) and automated TLS lifecycle management via GDC `cert-manager`.
5. **Air-Gapped Developer Persistence:** Developer repositories and workspace configurations permanently retained on GDC block storage PVCs across pod reboots and scale-to-zero idle hibernations.

### **Required IAM & RBAC Permissions**
* **GDC IAM Role:** `roles/container.developer` or `roles/gke.developer`
* **Kubernetes RBAC:** ServiceAccount `gdc-dev-operator-sa` with Role/ClusterRole granting operations on `pods`, `services`, `deployments`, `configmaps`, `secrets`, and `httproutes` (`gateway.networking.k8s.io`).

### **Deployment Command Sequence (Production / Default)**

```bash
# 1. Apply Core Infrastructure: Namespace, Gateway API, LoadBalancer, and Operator RBAC
kubectl apply -f p13-gdc-dev/manifests/gdc/namespace.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/gateway.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/loadbalancer.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-operator.yaml

# 2. Apply Configuration (Keycloak OIDC + In-Pod Multi-Agent AI Swarm) & Network Policies
kubectl apply -f p13-gdc-dev/manifests/gdc/oidc-auth-configmap.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-agent-configmap.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/network-policy-ai.yaml

# 3. Deploy Platform Services (Dual-Port Workspace & Sovereign Admin with AI Swarm Enabled by Default)
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-phase3-deployment.yaml
```

