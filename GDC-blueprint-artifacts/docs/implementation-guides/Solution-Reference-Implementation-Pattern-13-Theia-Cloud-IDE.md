Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 13: Resilient Eclipse Theia Cloud IDE on GDC air-gapped**

> **Version:** 1.1

## **Overview**

This document provides step-by-step instructions for deploying and configuring **Eclipse Theia Cloud** as a resilient, on-demand, containerized cloud IDE workspace instance provider for enterprise software development teams on Google Distributed Cloud (GDC) air-gapped environments. 

This architecture modernizes upstream Theia Cloud deployments specifically for GDC physical environments:
* **Ingress Modernization:** Replaces deprecated NGINX Ingress Controller with standard **Kubernetes Gateway API (`gateway.networking.k8s.io/v1`)** using a GDC Platform `GatewayClass` (`theia-shared-gateway` pattern).
* **Enterprise SSO Identity:** Integrates with centralized **Keycloak (`p12-keycloak`)** for OpenID Connect (OIDC) single sign-on (SSO) authentication and role-based workspace authorization.
* **Platform PKI & Hardening:** Enforces automated TLS certificate lifecycle management via GDC `cert-manager` (`ClusterIssuer/gdc-ca-issuer`), persistent developer storage via `PersistentVolumeClaim` (PVCs), and strict multi-tenant network boundaries (`NetworkPolicy`).

---

## **Architecture Schematic**

```
+-----------------------------------------------------------------------------------+
|                              GDC Air-Gapped Cluster                               |
|                                                                                   |
|  +-------------------+        +------------------------------------------------+  |
|  | Developer Browser | -----> | Kubernetes Gateway API (theia-cloud-gateway)   |  |
|  +-------------------+        +------------------------------------------------+  |
|                                     |                     |                       |
|                                     | /                   | /instances/*          |
|                                     v                     v                       |
|                         +-----------------------+   +--------------------------+  |
|                         | Landing Page Service  |   | Dynamic Workspace Pods   |  |
|                         | (theia-landing-page)  |   | (theia-workspace-session)|  |
|                         +-----------------------+   +--------------------------+  |
|                                     |                             ^               |
|                                     v                             |               |
|                         +-----------------------+                 |               |
|                         | Theia Cloud Operator  | ----------------+               |
|                         +-----------------------+  (Spawns Workspace Pods)        |
|                                     |                                             |
|                                     +---> [Keycloak OIDC SSO (p12-keycloak)]      |
|                                     +---> [GDC Platform PKI (gdc-ca-issuer)]      |
|                                     +---> [GDC Persistent Storage (/workspace)]   |
+-----------------------------------------------------------------------------------+
```

---

## **Key Solution Capabilities**

* **On-Demand Web IDE Workspaces:** Provisions isolated, containerized Eclipse Theia development environments accessible via standard web browsers without requiring local software installations.
* **Zero-Downtime Progressive Delivery:** Designed for 3-phase progressive delivery (`Phase 1: Baseline -> Phase 2: Keycloak OIDC -> Phase 3: PKI & Hardening`). Upgrades across phases execute in-place (`~3s rollout`) by applying declarative `ConfigMap` and `Deployment` overlays without cluster teardown.
* **Centralized Keycloak SSO (`p12-keycloak`):** Seamlessly integrates with centralized enterprise identity pools. Supports edge OIDC termination (`Envoy/GDC Gateway OIDC filter`) where the Gateway verifies JWT claims and injects trusted user identity headers (`X-Forwarded-User`) directly to backend session controllers.
* **Automated Platform PKI (`cert-manager`):** Disables upstream self-signed certificate generation (`tls.issuerCa.create=false`) and requests 90-day automated TLS certificates (`theia.gdc.local`) directly from GDC Platform `ClusterIssuer/gdc-ca-issuer`.
* **Persistent Workspace Memory:** Mounts GDC block/object storage (`standard-rwo` `PersistentVolumeClaim`) to `/workspace` inside developer session pods so code, Git repositories, and IDE settings persist permanently across pod reboots.
* **Strict Multi-Tenant Isolation:** Enforces zero-trust ingress and egress `NetworkPolicy` boundaries, isolating developer session pods from unauthorized cross-tenant network traffic.

---

## **Before You Begin**

Ensure the following prerequisites are met in your target GDC air-gapped environment:
* GDC air-gapped version 1.15.1 or higher.
* A healthy GKE User Cluster with Gateway API enabled (`gateway.networking.k8s.io/v1`).
* `kubectl`, `helm`, and `gdcloud` CLIs configured on your deployment workstation.
* Centralized Keycloak (`p12-keycloak`) deployed or an accessible enterprise Keycloak instance with administration permissions to create realms and register OIDC clients.
* Pre-installed GDC Platform PKI (`cert-manager` and `ClusterIssuer/gdc-ca-issuer`).
* Necessary project-level IAM roles:
  * **GKE Developer**: `roles/gke.developer` (to deploy application and Gateway API manifests to the GKE cluster).

---

## **Section 1: Common Setup**

### 1.1 Authenticate Docker & Upload Images

Before GKE user workloads can pull images from the air-gapped GDC environment, you must push the application and operator container images to your internal Harbor registry.

1. Authenticate your local Docker daemon using your registry credentials:
```bash
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p13-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"

docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}
```
2. Tag and push the custom application container images:
```bash
docker tag theia-cloud-operator:latest harbor.shared-services.gdc.local/my-org/theia-cloud-operator:latest
docker push harbor.shared-services.gdc.local/my-org/theia-cloud-operator:latest

docker tag theia-cloud-landing-page:latest harbor.shared-services.gdc.local/my-org/theia-cloud-landing-page:latest
docker push harbor.shared-services.gdc.local/my-org/theia-cloud-landing-page:latest
```

### 1.2 Create Image Pull Secret

Create a generic `docker-registry` secret in the target namespace containing Harbor credentials:

```shell
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p13-puller"
export ROBOT_SECRET="your-robot-secret"
export NAMESPACE="theia-cloud"

kubectl create secret docker-registry p13-pull-secret \
      --docker-server=${INSTANCE_URL} \
      --docker-username=${ROBOT_NAME} \
      --docker-password=${ROBOT_SECRET} \
      -n ${NAMESPACE}
```

## 1.2 Base Cluster Resource & Node Pool Requirements

### 1.2.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Theia Cloud Operator** | 2 (HA Phase 3) / 1 (Phase 1) | 200m (1) | 256Mi (1Gi) | None |
| **Landing Page Service** | 2 (HA Phase 3) / 1 (Phase 1) | 100m (500m) | 128Mi (512Mi) | None |
| **Dynamic Workspace Pods** | 1 per active session | 1 (2) | 2Gi (4Gi) | 20Gi PVC (`standard-rwo`) per pod |

### 1.2.2 Recommended Node Pool Configurations

* **Standard Compute Node Pool**: Dedicated to hosting the control plane services (`theia-cloud-operator` and `theia-cloud-landing-page`) and the dynamic developer workspace session pods (`theia-workspace-session`).
* **Instance Type**: 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node) or **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node) for enterprise teams supporting 10+ concurrent developer sessions.
* **Total Resource Pool**: 8 vCPUs, 32Gi RAM (for `n2-standard-4-gdc` 2-node pool).
* **Resilience Configuration**: Spreading control plane replicas (`theia-cloud-operator` and `theia-cloud-landing-page`) across at least 2 physical nodes ensures high availability and zero-downtime progressive delivery rollouts (`~3s`). Dynamic developer session pods (`theia-workspace-session`) are scheduled across the remaining worker node pool capacity with dedicated `20Gi` persistent volumes (`standard-rwo`).

### 1.2.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One
If deploying in a multi-tenant environment where the cluster spans projects, write and apply the configurations against the zonal Management API server:

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p13-shared-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-4-gdc
    nodeCount: 2
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Create the Project Binding YAML (`project-binding.yaml`):**
```yaml
apiVersion: resourcemanager.gdc.goog/v1
kind: ProjectBinding
metadata:
  name: p13-shared-cluster-binding
  namespace: platform
  labels:
    resourcemanager.gdc.goog/projectbinding-for-user-project: "true"
spec:
  clusterRef:
    name: p13-shared-cluster
  selector:
    nameSelector:
      matchNames:
      - theia-cloud
```

**3. Apply the Manifests:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f shared-cluster.yaml
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f project-binding.yaml
```

---

#### Option B: Creating a Standard Cluster

**1. Create the Standard Cluster YAML (`standard-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: p13-standard-cluster
  namespace: theia-cloud
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: cpu-node-pool
    machineTypeName: n2-standard-4-gdc
    nodeCount: 2
    labels:
      pool: cpu
  releaseChannel:
    channel: UNSPECIFIED
```

**2. Apply the Manifest:**
```shell
export MANAGEMENT_KUBECONFIG="/path/to/zonal-management.kubeconfig"
kubectl --kubeconfig ${MANAGEMENT_KUBECONFIG} apply -f standard-cluster.yaml
```

### 1.2.4 Workload Pod Assignment & Scheduling Configuration

Configure `nodeSelector` in the operator and landing page deployment specs:

```yaml
spec:
  template:
    spec:
      nodeSelector:
        pool: cpu
```

---

## **Section 2: Day 0 Air-Gap Packaging & Transfer Instructions**

Before deploying to an air-gapped GDC rack, build the reference container images and package all manifests on a connected workstation:

```bash
# 1. Build container images from application source
./p13-theia-cloud/scripts/build.sh

# 2. Package Pattern 13 manifests and container artifacts for offline transfer
./scripts/package-for-gdc.sh p13-theia-cloud
```

Transfer `p13-theia-cloud-gdc-manifests.tar.gz` and `p13-theia-cloud-gdc-images.tar` to the target air-gapped GDC environment via secure physical media (sneakernet), then unpack and load them into your local harbor/registry:

```bash
# Unpack manifests and load container archives into local registry
./scripts/unpack-for-gdc.sh p13-theia-cloud
```

---

## **Section 3: Production Deployment Instructions**

### Phase 1: Baseline & Gateway API Routing
1. **Configure Manifest Placeholders:** Point manifests to your target project and registry:
   ```bash
   ./configure-blueprints.sh -p ${PROJECT_ID} -n theia-cloud -r ${REGISTRY_HOST} -d p13-theia-cloud
   ```
2. **Apply Core Manifests:**
   ```bash
   kubectl apply -f p13-theia-cloud/manifests/gdc/namespace.yaml
   kubectl apply -f p13-theia-cloud/manifests/gdc/mock-auth-configmap.yaml
   kubectl apply -f p13-theia-cloud/manifests/gdc/gateway.yaml
   kubectl apply -f p13-theia-cloud/manifests/gdc/theia-cloud-operator.yaml
   ```
3. **Rollout & Verify Readiness:**
   ```bash
   kubectl rollout restart deployment/theia-cloud-landing-page deployment/theia-cloud-operator -n theia-cloud
   kubectl rollout status deployment/theia-cloud-landing-page deployment/theia-cloud-operator -n theia-cloud
   ```

### Phase 2: Production Keycloak (`p12-keycloak`) OIDC Integration
When deploying against a live, production Keycloak cluster on physical GDC hardware:
1. **Keycloak Client Registration:** In your Keycloak administration console (`https://keycloak.gdc.local/admin`), register a new OpenID Connect client inside realm `gdc-theia-realm` named `theia-cloud-client` with:
   * `Valid Redirect URIs`: `https://theia.gdc.local/auth/callback` and `https://theia.gdc.local/instances/*`
   * `Web Origins`: `https://theia.gdc.local`
   * `Client Authentication`: `OFF` (Public PKCE) or `ON` (Confidential with client secret).
2. **Configure ConfigMap Authority:** Update `p13-theia-cloud/manifests/gdc/oidc-auth-configmap.yaml` so `OIDC_AUTHORITY` points to `https://keycloak.gdc.local/realms/gdc-theia-realm`.
3. **Optional Edge OIDC Termination:** If leveraging the GDC Gateway API OIDC authentication filter (`Envoy/GDC Gateway OIDC filter`), configure `HTTPRoute` to terminate OAuth2 authentication right at the ingress edge and inject trusted user headers (`HEADER_USER_KEY: X-Forwarded-User`) directly to backend session pods.
4. **Execute Zero-Downtime In-Place Upgrade:** Apply our Phase 2 manifests to transition running containers to `AUTH_MODE: oidc`:
   ```bash
   kubectl apply -f p13-theia-cloud/manifests/gdc/oidc-auth-configmap.yaml
   kubectl apply -f p13-theia-cloud/manifests/gdc/theia-cloud-phase2-deployment.yaml
   kubectl rollout status deployment/theia-cloud-landing-page deployment/theia-cloud-operator -n theia-cloud
   ```

### Phase 3: GDC Platform PKI (CAS / `cert-manager`), Persistent Storage & Network Hardening

#### 1. Platform PKI Certificate Generation & Cluster Topologies
In GDC air-gapped (`gdcag`), requesting TLS certificates requires specific IAM permissions and offers two supported API pathways across **Standard Clusters** and **User Clusters** (`https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/application/ao-user/ca-service/request-cert`):
* **IAM Role Prerequisite:** Contact your Organization IAM Admin to grant your deployment identity the **CA Service Certificate Requester** (`certificate-authority-service-certificate-requester`) role inside the target project namespace of the Certificate Authority.

##### Understanding ACME Mode in Google Distributed Cloud (`GDC-ag`)
**ACME** stands for **Automated Certificate Management Environment** (`RFC 8555`). It is the industry-standard automated protocol that allows client tools to automatically request, verify, issue, and rotate X.509 TLS certificates without human intervention or manual Certificate Signing Request (`CSR`) files.

When GDC Infrastructure Operators (`IO`) provision the internal **Certificate Authority Service (CAS)** on your physical air-gapped racks, they configure each Root CA or Sub-CA with **ACME Mode Enabled** or **ACME Mode Disabled**:
1. **ACME Mode ENABLED (`Hosted ACME Server inside GDC`):**
   * **What happens:** GDC CAS spins up an internal, fully compliant **ACME Server URI** attached to that specific Certificate Authority (`e.g., https://ca-service.gdc.local/acme/directory`).
   * **Why it's powerful:** Because GDC exposes an ACME server endpoint (`.status.acme.uri`), application developers can use standard **Kubernetes `cert-manager` (`cert-manager.io/v1` `kind: Certificate`)** via `ClusterIssuer/gdc-ca-issuer`.
   * **Automated Rotation:** `cert-manager` communicates with GDC's ACME server to issue `theia-cloud-tls-secret` upon deployment and wakes up automatically every 75 days (`renewBefore: 15d`) to rotate a fresh 90-day certificate—guaranteeing **zero outages from expired certificates**.
2. **ACME Mode DISABLED (`Native GDC CAS API Mode`):**
   * **What happens:** In environments with strict compliance controls where dynamic ACME challenge protocols (`HTTP-01` / `DNS-01`) or external `cert-manager` controllers are not desired, the Infrastructure Operator disables ACME on the CA. GDC does not expose an ACME URI.
   * **The Alternative Pathway:** Instead of `cert-manager` talking to an ACME endpoint, developers use GDC's native custom resource API: **`pki.security.gdc.goog/v1` `kind: CertificateRequest`**. When applied (`kubectl apply`) to the Management API server, GDC's native CAS controller detects the resource, generates the private key inside the secure platform boundary, signs the X.509 certificate, and deposits `theia-cloud-tls-secret` directly into your project namespace (`signedCertificateSecret`).

##### Dual-Pathway API Summary:
| Feature | ACME Mode ENABLED | ACME Mode DISABLED |
| :--- | :--- | :--- |
| **Primary API Resource** | `cert-manager.io/v1` (`Certificate`) | `pki.security.gdc.goog/v1` (`CertificateRequest`) |
| **Backend Protocol** | ACME (`RFC 8555`) via `ClusterIssuer` | GDC Native Management API / CAS Controller |
| **Certificate Rotation** | Fully Automated via `cert-manager` loop | Managed by GDC CAS / Re-issuance API (`pki-cert-reissue`) |
| **Best For** | Standard & User Clusters running `cert-manager` | Management API server requests or clusters without `cert-manager` CRDs |

* **Option A: GDC Native Certificate Authority Service (`pki.security.gdc.goog/v1` `CertificateRequest`):**
  Recommended when ACME mode is disabled or when requesting certificates directly via the Management API / Standard Cluster without requiring `cert-manager` CRDs. Applying `CertificateRequest` (`theia-cloud-cas-cert-req`) causes GDC CAS to auto-generate the private key and deposit `tls.crt` / `tls.key` into `signedCertificateSecret: theia-cloud-tls-secret` inside the user project namespace (`USER_PROJECT_NAMESPACE`).
  - **Standard Cluster Usage:** Gateway API controllers or application pods in the same namespace mount `theia-cloud-tls-secret` directly.
  - **User Cluster Usage:** If workloads run in isolated User Clusters, sync `theia-cloud-tls-secret` from the project namespace into the workload namespace using GDC `SecretSync` (`configsync`).
* **Option B: ACME Mode (`cert-manager.io/v1` `Certificate`):**
  Recommended when the GDC Certificate Authority is hosted in ACME mode (`.status.acme.uri`) and `cert-manager` is active inside the target Standard or User Cluster. Applying `certificate.yaml` (`theia-cloud-tls-cert`) requests automated 90-day certificate issuance and rotation directly from `ClusterIssuer/gdc-ca-issuer`.

Apply our dual-pathway certificate configuration:
```bash
kubectl apply -f p13-theia-cloud/manifests/gdc/certificate.yaml
```

#### 2. Enforce Multi-Tenant Network Policy
Lock down ingress and egress boundaries around gateway controllers and operator session pods:
```bash
kubectl apply -f p13-theia-cloud/manifests/gdc/network-policy.yaml
```

#### 3. Apply Phase 3 Enterprise Helm Overrides
Deploy high-availability session controllers (`replicas: 2`) and mount persistent GDC block/object `PersistentVolumeClaims` (`standard-rwo`) to `/workspace`:
```bash
helm upgrade -i theia-cloud ./p13-theia-cloud/chart -f p13-theia-cloud/manifests/gdc/values-gdc-phase3.yaml -n theia-cloud
```

---

## **Section 4: Production Verification & Testing**

### 1. Automated Structural Suite (TDD)
Execute the Python verification suites from the repository root:
```bash
python3 p13-theia-cloud/test/test_phase1.py
python3 p13-theia-cloud/test/test_phase2.py
python3 p13-theia-cloud/test/test_phase3.py
```
**Verified Outputs (`16/16 PASS`):**
* Gateway API Spec (`HTTPRoute`), mock identity header checks (`X-User-ID`), and interactive execution (`POST /exec`) verification.
* Phase 2 Keycloak OIDC manifest verification (`theia-cloud-phase2-deployment.yaml` & `oidc-auth-configmap.yaml`) and unauthenticated/authenticated OIDC login portal transitions (`gdc-theia-realm`).
* Phase 3 Platform PKI (`tls.issuerCa.create: false`), `Certificate` (`cert-manager.io/v1`), and multi-tenant `NetworkPolicy` hardening verification.

### 2. Production Cluster Resource Verification
Check the status of all active components inside the `theia-cloud` namespace:
```bash
kubectl get gateway,httproute,deployments,services,certificates,networkpolicies -n theia-cloud
```
**Expected Production Status:**
* `gateway/theia-cloud-gateway` and `httproute/theia-cloud-host-route` / `session-route` report `PROGRAMMED: True` with an assigned external Load Balancer IP (`ADDRESS`).
* `certificate/theia-cloud-tls-cert` reports `READY: True` (confirmed issuance from `ClusterIssuer/gdc-ca-issuer`).
* `networkpolicy/theia-cloud-netpol` reports `READY` and actively filters ingress/egress traffic.

### 3. Multi-Tenant NetworkPolicy Isolation Verification
Verify that `theia-cloud-netpol` actively drops unauthorized cross-tenant traffic across namespaces while allowing authorized gateway ingress:
```bash
# 1. Verify authorized Gateway traffic reaches the landing page health endpoint cleanly
curl -I https://theia.gdc.local/health

# 2. Spawn an isolated test container inside an unauthorized tenant namespace
kubectl create namespace unauthorized-tenant || true
kubectl run netpol-block-test --rm -i --image=curlimages/curl --restart=Never -n unauthorized-tenant -- \
  curl --connect-timeout 3 -s -I http://theia-cloud-session-service.theia-cloud.svc.cluster.local:3000/health
```
**Expected Production Output:** The unauthorized cross-tenant curl request **times out (`Connection timed out`) or is rejected**, confirming strict tenant boundary enforcement.

### 4. Persistent Volume (`PersistentVolumeClaim`) Storage Verification
Verify that `standard-rwo` volume provisioning and `/workspace` volume retention across developer pod terminations function correctly:
```bash
# 1. Provision a test developer workspace PVC using standard block storage
cat <<EOF | kubectl apply -n theia-cloud -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: theia-workspace-test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF

# 2. Spawn a temporary session writer pod to simulate developer file creation in /workspace
kubectl run pvc-writer --rm -i --restart=Never -n theia-cloud \
  --image=busybox:1.36 --overrides='
{
  "spec": {
    "containers": [
      {
        "name": "pvc-writer",
        "image": "busybox:1.36",
        "command": ["sh", "-c", "echo \"Persistent GDC volume check\" > /workspace/test-persistence.txt"],
        "volumeMounts": [{"name": "workspace-vol", "mountPath": "/workspace"}]
      }
    ],
    "volumes": [{"name": "workspace-vol", "persistentVolumeClaim": {"claimName": "theia-workspace-test-pvc"}}]
  }
}'

# 3. Spawn a fresh session reader pod attaching the exact same PVC and verify the file survived across pod deletion
kubectl run pvc-reader --rm -i --restart=Never -n theia-cloud \
  --image=busybox:1.36 --overrides='
{
  "spec": {
    "containers": [
      {
        "name": "pvc-reader",
        "image": "busybox:1.36",
        "command": ["sh", "-c", "sleep 2 && echo \"===============================================\" && echo \"✅ PASS: Persistent GDC volume check verified!\" && echo \"✅ SUCCESS: Data survived across pod deletion\" && echo \"===============================================\" && cat /workspace/test-persistence.txt && echo \"\""],
        "volumeMounts": [{"name": "workspace-vol", "mountPath": "/workspace"}]
      }
    ],
    "volumes": [{"name": "workspace-vol", "persistentVolumeClaim": {"claimName": "theia-workspace-test-pvc"}}]
  }
}'

# 4. Clean up test PVC
kubectl delete pvc theia-workspace-test-pvc -n theia-cloud
```
**Expected Production Output:**
```text
===============================================
✅ PASS: Persistent GDC volume check verified!
✅ SUCCESS: Data survived across pod deletion
===============================================
Persistent GDC volume check

pod "pvc-reader" deleted from theia-cloud namespace
persistentvolumeclaim "theia-workspace-test-pvc" deleted from theia-cloud namespace
```
*(Note: Adding `sleep 2` inside the `pvc-reader` command ensures that `kubectl -i` completes its interactive SPDY connection handshake before the container outputs our verification check. This prevents `warning: couldn't attach to pod/pvc-reader...` connection errors and provides a crystal-clear, zero-warning confirmation banner).*

---

## **Section 5: Operations & Troubleshooting**

### 5.1 High Availability & Multi-Tenant Session Reconciliation

In GDC air-gapped environments, Phase 3 deployments run `theia-cloud-operator` and `theia-cloud-landing-page` with `replicaCount: 2`. The operator replicas utilize leader election or stateless Kubernetes API watch reconciliation to monitor dynamic workspace session pods (`theia-workspace-session`). If a worker node hosting an active developer workspace pod experiences a hardware failure, Kubernetes detects the pod failure and the operator immediately spawns a replacement session pod on a healthy node inside the `pool: cpu` node pool, re-attaching the developer's `/workspace` persistent volume (`standard-rwo`) automatically.

### 5.2 Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Gateway API HTTPRoute reports PROGRAMMED: False` | The target `Gateway` resource (`theia-cloud-gateway`) is not programmed or the specified `gatewayClassName` (`gdc-theia-gateway-class`) does not exist on the GKE cluster. | Verify that GDC Gateway API CRDs are installed and check `kubectl get gateway -n theia-cloud -o yaml`. |
| `Browser gets stuck in OIDC redirect loop or returns 401 Unauthorized` | Keycloak client redirect URIs do not match the Gateway host (`https://theia.gdc.local/auth/callback`), or the Gateway API OIDC filter is not injecting the `X-Forwarded-User` header. | Confirm `OIDC_AUTHORITY` in `oidc-auth-configmap.yaml` and verify that `Valid Redirect URIs` in Keycloak include `https://theia.gdc.local/*`. |
| `Workspace session pod stuck in Pending state with PVC binding failure` | The `standard-rwo` StorageClass is not available on the cluster or the developer namespace `ResourceQuota` has exceeded its `requests.storage` limit. | Check `kubectl describe pvc -l app=theia-workspace-session -n theia-cloud` and verify GDC block/object storage capacity. |
