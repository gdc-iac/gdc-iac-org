Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# **Solution Reference Implementation - Pattern 13: Resilient GDC Developer Environment (gdc-dev) on GDC air-gapped**

> **Version:** 1.4

## **Overview**

This document provides step-by-step instructions for deploying and configuring **GDC Developer Environment (`gdc-dev`)** (inspired by the cloud IDE paradigms of Eclipse Theia Cloud) as a resilient, on-demand, containerized developer workspace platform for enterprise software development teams on Google Distributed Cloud (GDC) air-gapped environments. 

This architecture modernizes cloud developer workspace deployments specifically for GDC physical environments:
* **Dual Ingress & LoadBalancer Entry Points:** Modernizes ingress using **Kubernetes Gateway API (`gateway.networking.k8s.io/v1`)** with a GDC Platform `GatewayClass` (`gdc-dev-gateway`) alongside a dedicated, standalone **Platform LoadBalancer Service (`gdc-dev-loadbalancer`)** with internal VIP annotations (`networking.gke.io/load-balancer-type: "Internal"`) for direct network routing from enterprise developer workstations.
* **Enterprise SSO Identity:** Integrates with centralized **Keycloak (`p12-keycloak`)** for OpenID Connect (OIDC) single sign-on (SSO) authentication and role-based workspace authorization.
* **In-Pod Sovereign Agentic AI Platform (Phase 3):** Upgrades from a passive co-pilot to an autonomous in-pod ReAct agent engine equipped with OpenAI-compatible tool calling (`read_file`, `write_file`, `apply_diff`, `run_terminal_command`, `list_directory`), selective auto-approval security gates, interactive model switching, and automated terminal diagnostics.
* **Multi-Agent Swarm Specialization (Phase 4):** Extends the ReAct engine into a collaborative **3-Agent Developer Swarm** (📐 Architect, 💻 Coder, 🔍 Reviewer) with role-based tool isolation enforcing the Principle of Least Privilege.
* **Air-Gapped Developer Persistence:** Guarantees developer code, Git history, and workspace configurations are permanently retained on GDC block storage via dynamic PersistentVolumeClaims (`PVC`), allowing developers to disconnect at the end of the day and resume work seamlessly the next morning.
* **Platform PKI & Hardening:** Enforces automated TLS certificate lifecycle management via GDC `cert-manager` (`ClusterIssuer/gdc-ca-issuer`), persistent developer storage via `PersistentVolumeClaim` (PVCs), and strict multi-tenant network boundaries (`NetworkPolicy`).

---

## **Architecture Schematic**

```
+-----------------------------------------------------------------------------------------------+
|                                    GDC Air-Gapped Cluster                                     |
|                                                                                               |
|  +---------------------------+    +--------------------------------------------------------+  |
|  | Developer Workstation     |    | Ingress Entry Point: Gateway API / Platform LB         |  |
|  | (https://dev.gdc.local)   | -> | (gdc-dev-gateway / gdc-dev-loadbalancer: VIP 80/443)   |  |
|  +---------------------------+    +--------------------------------------------------------+  |
|                                                  |                         |                  |
|                                                  | /                       | /instances/*     |
|                                                  v                         v                  |
|                                      +-----------------------+   +-------------------------+  |
|                                      | Landing Page Service  |   | Dynamic Workspace Pods  |  |
|                                      | (gdc-dev-landing-page)|   | (gdc-dev-session)       |  |
|                                      +-----------------------+   +-------------------------+  |
|                                         |                         |       ^   |               |
|                                         v                         |       |   | /home/dev/    |
|                             +-----------------------+             |       |   | workspace/    |
|                             | GDC Dev Operator      | <-----------+       |   |               |
|                             +-----------------------+  (Spawns Pods)      |   v               |
|                                         |                                 | +--------------+  |
|                                         |                                 | | GDC PVC Disk |  |
|                                         |                                 | +--------------+  |
|                                         +---> [Keycloak OIDC SSO (p12-keycloak)]              |
|                                         +---> [Phase 3 Agentic Engine: ReAct + In-Pod Tools]  |
|                                         +---> [Sovereign Inference: gdc_gemma_gw (31B / 26B)] |
|                                         +---> [GDC Platform PKI (gdc-ca-issuer)]             |
+-----------------------------------------------------------------------------------------------+
```

---

## **Key Solution Capabilities**

* **On-Demand Web IDE Workspaces:** Provisions isolated, containerized `gdc-dev` development environments (inspired by cloud IDE paradigms like Eclipse Theia) accessible via standard web browsers without requiring local software installations.
* **Dual Ingress & LoadBalancer Entry Points:** Supports both modern **Kubernetes Gateway API (`gateway.networking.k8s.io/v1`)** and a direct, dedicated **Platform LoadBalancer Service (`gdc-dev-loadbalancer`)**, allocating an internal VIP (`networking.gke.io/load-balancer-type: "Internal"`) that allows developer web browsers and automated test harnesses to connect directly over the enterprise LAN without requiring `kubectl port-forward`.
* **Zero-Downtime Progressive Delivery:** Designed for 3-phase progressive delivery (`Phase 1: Baseline -> Phase 2: Keycloak OIDC -> Phase 3: PKI, Hardening & Agentic AI`). Upgrades across phases execute in-place (`~3s rollout`) by applying declarative `ConfigMap` and `Deployment` overlays without cluster teardown.
* **Centralized Keycloak SSO (`p12-keycloak`):** Seamlessly integrates with centralized enterprise identity pools. Supports edge OIDC termination (`Envoy/GDC Gateway OIDC filter`) where the Gateway verifies JWT claims and injects trusted user identity headers (`X-Forwarded-User`) directly to backend session controllers.
* **Persistent Workspace Memory:** Mounts GDC block/object storage (`standard-rwo` `PersistentVolumeClaim`) to `/home/dev/workspace` inside developer session pods so code, Git repositories, and IDE settings persist permanently across pod reboots and end-of-day idle hibernations.
* **In-Pod Agentic AI Engine (Phase 3):** Executes a sovereign ReAct agent directly inside the developer's session container. The agent autonomously reads workspace files, drafts surgical unified diffs, and inspects directory trees via strict OpenAI-compatible function schemas.
* **Selective Auto-Approval Guardrails:** Implements a strict Human-in-the-Loop (HITL) security policy: non-mutating actions (`read_file`, `list_directory`) run autonomously, while code mutations (`apply_diff`, `write_file`) and terminal commands pause to render interactive visual **Diff Approval Cards** requiring 1-click developer authorization.
* **Interactive Model Selector & Model Tiering:** Provides an in-IDE model dropdown supporting real-time toggling between `gemma4:31b (Reasoning)`, `gemma4:26b (Fast MoE)`, `Auto (Model Tiering)`, and available sovereign air-gapped Gemini endpoints (`gemini-2.0-pro`, `gemini-2.0-flash`).
* **Terminal Auto-Repair Hook:** Automatically inspects failing terminal commands, captures `stderr` and stack traces, and renders an immediate **`[ ⚡ Fix with Gemma Agent ]`** one-click diagnosis button.
* **Two-Tier Rollback Protection:** Supports 1-click in-editor code rollback (`[ ↩ Rollback Changes ]`) and declarative cluster platform rollback (`rollback-to-phase2.sh`).
* **Multi-Project Workspace Management & Filesystem Isolation:** Dynamically provisions and switches between independent project workspaces (`default-workspace`, custom projects) with isolated directories under `/tmp/dev-projects/<name>`, terminal prompt tracking (`dev@gdc-session:~/<project>$`), and template scaffolding.
* **Seamless OIDC Session Continuity:** Employs domain-scoped session cookies and auth query parameter propagation to ensure project switching requires zero re-authentication.
* **Full Agent Output Preservation:** Preserves complete architectural blueprints and code reviews without compression or tree-stripping via direct `💾 Save as File` export and `📋 Copy All` actions.
* **Customizable Developer UI Layout & Persistence:** Provides interactive draggable resizers with preset buttons for adjusting terminal dock height and AI panel width, persisted across sessions via browser `localStorage`.
* **Automated Platform PKI (`cert-manager`):** Disables upstream self-signed certificate generation (`tls.issuerCa.create=false`) and requests 90-day automated TLS certificates (`dev.gdc.local`) directly from GDC Platform `ClusterIssuer/gdc-ca-issuer`.
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

## **Section 1: Day 0 Air-Gap Asset Packaging, Sneakernet Transfer & Harbor Registry Setup**

> [!NOTE]
> This implementation guide details the production deployment procedures for **physical Google Distributed Cloud (GDC) air-gapped** environments.

In strictly isolated physical GDC air-gapped environments with no direct Internet connectivity, deployment assets must be built and packaged on an external connected workstation, transferred across the security perimeter via approved physical removable media (sneakernet), and loaded into the local in-cluster Harbor container registry before cluster deployment can commence.

### 1.1 Step 1: Package Assets on Connected Workstation (Outside the Air-Gap)

On your internet-connected build workstation where Git repositories and base OCI images can be accessed:

```bash
# 1. Build and export container images as a compressed offline tarball archive
# Builds gdc-dev-landing-page, gdc-dev-operator, and gdc-dev-workspace
./p13-gdc-dev/scripts/build.sh --with-workspace --save-tar ./dist/airgap-bundle

# 2. Stage self-contained production manifests, configs, and helper scripts
python3 scripts/stage_production_assets.py p13-gdc-dev
```

This generates:
* `dist/airgap-bundle/gdc-dev-images.tar.gz`: Offline OCI container image bundle containing:
  * `gdc-dev-landing-page`: Web dashboard for workspace session management.
  * `gdc-dev-operator`: Kubernetes controller managing workspace lifecycle and scale-to-zero hibernation.
  * `gdc-dev-workspace`: Developer workspace session image pre-baked with enterprise CLI tools (`git`, `kubectl`, `helm`, `gdcloud`, rootless `podman`, and `buildah`) and in-pod ReAct AI agent tooling.
* `deploy-to-production/patterns/p13-gdc-dev/`: Complete, self-contained production deployment directory containing declarative Kubernetes Gateway API manifests, Helm charts, Keycloak OIDC configs, NetworkPolicies, and operational runbooks.

> [!TIP]
> **Customizing Developer Tooling & Language SDK Recipes:**  
> If your organization requires additional language runtimes (Golang, Java OpenJDK/Maven/Gradle, Node.js/TypeScript, OpenTofu, enterprise CA certificates) or slimmer base images to enforce least-privilege policies, customize the Dockerfile before running the offline build. See the dedicated guide:  
> 📖 [**Customizing Developer Workspace Images (gdc-dev)**](../customizing-developer-workspace-images.md) (or [workspace/README.md](../../p13-gdc-dev/example-app/workspace/README.md)).

---

### 1.2 Step 2: Sneakernet Transfer Across Air-Gap Boundary

Transfer the generated artifacts across the air-gap boundary to your physical GDC administrative workstation or jumpbox using your organization's approved secure data transfer process (e.g. encrypted physical media, unidirectional data diode, or jumpbox staging):

1. `dist/airgap-bundle/gdc-dev-images.tar.gz` $\rightarrow$ Target jumpbox (e.g., `~/transfer/gdc-dev-images.tar.gz`)
2. `deploy-to-production/patterns/p13-gdc-dev/` $\rightarrow$ Target jumpbox (e.g., `~/GDC-blueprints/deploy-to-production/patterns/p13-gdc-dev/`)

---

### 1.3 Step 3: Harbor Registry Authentication & Image Import (Inside Air-Gap)

Once the archive and manifests reside on the physical GDC jumpbox with network connectivity to the internal Harbor registry:

```bash
# 1. Set environment variables for target internal Harbor registry
export INSTANCE_URL="harbor.shared-services.gdc.local"
export ROBOT_NAME="robot\$p13-puller"  # Escape the $ character
export ROBOT_SECRET="your-robot-secret"
export REGISTRY_HOST="${INSTANCE_URL}/my-org"

# 2. Authenticate Docker daemon with Harbor
docker login ${INSTANCE_URL} --username ${ROBOT_NAME} --password ${ROBOT_SECRET}

# 3. Load container images into local Docker daemon from offline tarball
docker load -i gdc-dev-images.tar.gz

# 4. Tag and push images to internal Harbor registry
docker tag gdc-dev-landing-page:latest ${REGISTRY_HOST}/gdc-dev-landing-page:latest
docker tag gdc-dev-operator:latest ${REGISTRY_HOST}/gdc-dev-operator:latest
docker tag gdc-dev-workspace:latest ${REGISTRY_HOST}/gdc-dev-workspace:latest

docker push ${REGISTRY_HOST}/gdc-dev-landing-page:latest
docker push ${REGISTRY_HOST}/gdc-dev-operator:latest
docker push ${REGISTRY_HOST}/gdc-dev-workspace:latest

# 5. Create gdc-dev namespace and image pull secret in the GDC user cluster
kubectl create namespace gdc-dev --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret docker-registry harbor-image-pull-secret \
    --docker-server="${INSTANCE_URL}" \
    --docker-username="${ROBOT_NAME}" \
    --docker-password="${ROBOT_SECRET}" \
    --namespace="gdc-dev"
```

> [!NOTE]
> If your administrative workstation has direct access to build images and network connectivity to the internal Harbor registry, you can alternatively build and push directly without an offline tarball using:  
> `./p13-gdc-dev/scripts/build.sh --registry "${REGISTRY_HOST}" --with-workspace`

---

## **Section 2: Cluster Resource Sizing & Capacity Planning**

Before initiating production deployment, verify that the target GDC user cluster has sufficient compute, memory, and persistent storage headroom to support concurrent developer workspaces and control plane components.

### 2.1 Component Resource Allocation Breakdown

| Component | Replicas | CPU Request (Limit) | Memory Request (Limit) | Storage / PVC |
| :--- | :---: | :--- | :--- | :--- |
| **Landing Page** (`gdc-dev-landing-page`) | 2 | 100m (500m) | 128Mi (512Mi) | None (Stateless Web UI) |
| **Operator** (`gdc-dev-operator`) | 2 | 200m (1000m) | 256Mi (1024Mi) | None (Stateless Controller) |
| **Developer Session Pod** (`gdc-dev-workspace-session`) | 1 per active user | 500m (2000m) | 1Gi (4Gi) | 20Gi (`standard-rwo`) GDC Block Storage |
| **Keycloak SSO (`p12-keycloak`)** | 2 | 500m (1000m) | 1Gi (2Gi) | 50Gi HA DB Volume |
| **Sovereign Gemma Gateway (`gdc_gemma_gw`)** | 1–2 (GPU) | 4 (8) | 16Gi (32Gi) | 100Gi SAN Volume (Model Weights) |

### 2.2 Recommended Node Pool Configurations & Sizing Guidelines

* **Control Plane & Management Node Pool (`platform-pool`):**
  * Hosts the `gdc-dev-operator`, `gdc-dev-landing-page`, Keycloak OIDC authentication, Envoy Gateway API controllers, and Platform PKI `cert-manager`.
  * **Instance Type:** 2 nodes of type **`n2-standard-4-gdc`** (4 vCPUs, 16Gi RAM per node).
  * **Total Resource Pool:** 8 vCPUs, 32Gi RAM with multi-zone HA redundancy.

* **Developer Session Worker Node Pool (`dev-session-pool`):**
  * Dedicated to dynamic developer workspaces (`gdc-dev-workspace-session`) and unprivileged container builders (`podman`, `buildah`).
  * Sizing guidelines based on concurrent active developer tenancy:
    * **Small Team (10 Concurrent Developers):**
      * Compute Baseline: 10 pods $\times$ 500m CPU = 5 vCPUs request; 10 pods $\times$ 1Gi RAM = 10Gi RAM request.
      * Recommended: 2 nodes of type **`n2-standard-8-gdc`** (8 vCPUs, 32Gi RAM per node; total 16 vCPUs, 64Gi RAM). Provides ample headroom for compilation bursts, language servers, and rootless OCI builds.
    * **Medium Department (25 Concurrent Developers):**
      * Compute Baseline: 25 pods $\times$ 500m CPU = 12.5 vCPUs request; 25 pods $\times$ 1Gi RAM = 25Gi RAM request.
      * Recommended: 3 nodes of type **`n2-standard-8-gdc`** (24 vCPUs, 96Gi RAM) or 2 nodes of type **`n2-standard-16-gdc`** (32 vCPUs, 128Gi RAM).
    * **Large Engineering Organization (50 Concurrent Developers):**
      * Compute Baseline: 50 pods $\times$ 500m CPU = 25 vCPUs request; 50 pods $\times$ 1Gi RAM = 50Gi RAM request.
      * Recommended: 4 nodes of type **`n2-standard-16-gdc`** (64 vCPUs, 256Gi RAM).

* **Persistent Storage Capacity Planning:**
  * Backed by GDC Air-Gapped block storage (`standard-rwo`).
  * Each developer receives a dedicated **20Gi** PVC mounted at `/home/dev/workspace`.
  * Storage sizing formula: $\text{Total Storage} = \text{Registered Developers} \times 20\text{Gi} \times 1.25\text{ (Safety Headroom)}$.
    * 10 Developers: 250Gi GDC Block Storage.
    * 25 Developers: 625Gi GDC Block Storage.
    * 50 Developers: 1.25TiB GDC Block Storage.
  * **Scale-to-Zero Hibernation Efficiency:** When developers close their sessions or exceed idle timeouts (e.g. 30 minutes), the Operator hibernates the session pod to reclaim CPU and memory. The underlying block storage volume remains permanently preserved, allowing physical compute nodes to scale strictly with *active concurrent* developers rather than total registered user accounts.

### 2.3 Declaring the Cluster & Node Pools in GDC (Declarative Provisioning)

#### Option A: Using an Existing Shared Cluster or Creating a New One

**1. Create the Shared Cluster YAML (`shared-cluster.yaml`):**
```yaml
apiVersion: cluster.gdc.goog/v1
kind: Cluster
metadata:
  name: gdc-dev-cluster
  namespace: platform
spec:
  clusterNetwork:
    podCIDRSize: 21
    serviceCIDRSize: 23
  initialVersion:
    kubernetesVersion: 1.26.5-gke.2100
  nodePools:
  - name: platform-pool
    machineTypeName: n2-standard-4-gdc
    initialNodeCount: 2
  - name: dev-session-pool
    machineTypeName: n2-standard-8-gdc
    initialNodeCount: 2
    nodeConfig:
      labels:
        pool: cpu
```

**2. Apply Manifest via GDC Management API:**
```bash
kubectl apply -f shared-cluster.yaml
```

---


## **Section 3: Production Deployment Instructions**

### 3.1 Fast-Track: Direct Production Deployment (Hardened Phase 3 Sovereign Stack - Recommended)

For production deployments on GDC Air-Gapped, deploy the complete, hardened Phase 3 stack directly (Gateway API routing, Keycloak OIDC SSO, In-Pod ReAct Agentic AI, automated PKI TLS, and zero-trust NetworkPolicies):

#### Step 1: Set Target Registry Environment Variable
```bash
export REGISTRY_HOST="harbor.shared-services.gdc.local/my-org"
```

#### Step 2: Apply Namespace, Gateway API Routing & Platform LoadBalancer Entry Point
Deploy the dedicated namespace, modern Gateway API routing, and the standalone platform LoadBalancer service:
```bash
# 1. Create dedicated developer environment namespace
kubectl apply -f p13-gdc-dev/manifests/gdc/namespace.yaml

# 2. Deploy Gateway API routing (GatewayClass, Gateway, HTTPRoutes)
kubectl apply -f p13-gdc-dev/manifests/gdc/gateway.yaml

# 3. Deploy dedicated GDC Platform LoadBalancer Service entry point
kubectl apply -f p13-gdc-dev/manifests/gdc/loadbalancer.yaml
```

#### Step 3: Configure & Apply Keycloak OIDC Authentication
In your Keycloak administration console (`https://keycloak.gdc.local/admin`), register a new OpenID Connect client in realm `gdc-dev-realm` named `gdc-dev-client`:
* `Valid Redirect URIs`: `https://dev.gdc.local/auth/callback` and `https://dev.gdc.local/instances/*`
* `Web Origins`: `https://dev.gdc.local`
* `Client Authentication`: `OFF` (Public PKCE) or `ON` (Confidential with client secret)

Update `p13-gdc-dev/manifests/gdc/oidc-auth-configmap.yaml` with your Keycloak realm authority and apply:
```bash
kubectl apply -f p13-gdc-dev/manifests/gdc/oidc-auth-configmap.yaml
```

#### Step 4: Configure Sovereign Agentic AI Swarm & Deploy Control Plane

> [!NOTE]
> **Sovereign Inference Architecture (Primary vs. Alternative):**
> * **Primary / Default Configuration:** Uses the in-cluster sovereign **Gemma Gateway (`gdc_gemma_gw`)** running on local GDC GPU/TPU nodes with dual-model specialization (`gemma4:31b` for reasoning/review and `gemma4:26b` for rapid diff authoring).
> * **Alternative Configuration (Sovereign GDC Gemini):** If your air-gapped facility provides an internal sovereign Gemini service (e.g. `https://gemini.gdc.local/v1`), set `AI_PROVIDER: "gemini"`, `OPENAI_API_BASE_URL: "https://gemini.gdc.local/v1"`, and configure `AI_GEMINI_TIER1_MODEL` / `AI_GEMINI_TIER2_MODEL` in `gdc-dev-agent-configmap.yaml`.

Apply the in-pod agent configuration and Phase 3 deployment manifests:
```bash
# 1. Apply Phase 3 Agentic ConfigMap
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-agent-configmap.yaml

# 2. Apply Phase 3 Deployment Manifest
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-phase3-deployment.yaml

# 3. Update image references to target Harbor registry
kubectl set image deployment/gdc-dev-landing-page landing-page="${REGISTRY_HOST}/gdc-dev-landing-page:latest" -n gdc-dev
kubectl set image deployment/gdc-dev-operator operator="${REGISTRY_HOST}/gdc-dev-operator:latest" -n gdc-dev
```

#### Step 5: Enforce Platform PKI TLS & Zero-Trust Network Policies
```bash
# Apply automated TLS certificate referencing GDC ClusterIssuer/gdc-ca-issuer:
kubectl apply -f p13-gdc-dev/manifests/gdc/certificate.yaml

# Lock down multi-tenant ingress/egress boundaries:
kubectl apply -f p13-gdc-dev/manifests/gdc/network-policy.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/network-policy-ai.yaml
```

#### Step 6: Verify Rollout Status
```bash
kubectl rollout restart deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
kubectl rollout status deployment/gdc-dev-landing-page -n gdc-dev
kubectl rollout status deployment/gdc-dev-operator -n gdc-dev
```

#### Step 7: Retrieve Ingress LoadBalancer VIP & Confirm Service Readiness
Once the rollout completes, verify that the GDC platform load balancer controller has provisioned an internal VIP:
```bash
# Retrieve assigned LoadBalancer VIP from GDC platform pool:
export LB_IP=$(kubectl get svc gdc-dev-loadbalancer -n gdc-dev -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "=========================================================="
echo "✅ GDC Developer Environment LoadBalancer VIP: ${LB_IP}"
echo "=========================================================="

# Or if using Gateway API with Envoy Gateway:
export GATEWAY_IP=$(kubectl get gateway gdc-dev-gateway -n gdc-dev -o jsonpath='{.status.addresses[0].value}')
echo "✅ GDC Gateway VIP: ${GATEWAY_IP}"
```

---

### 3.2 Developer Ingress Entry Point, LoadBalancer VIP & DNS Configuration on GDC-ag

In physical GDC air-gapped environments, developer workstations and administrative jump hosts connect over the enterprise/campus network. Developers access their containerized workspaces through standard web browsers without requiring local CLI tools, cluster admin credentials, or `kubectl port-forward`.

#### 1. Ingress Architecture & Entry Point Options

Pattern 13 provides two complementary, production-tested ingress pathways:

* **Pathway A: Dedicated Platform LoadBalancer Service (`manifests/gdc/loadbalancer.yaml` - Standalone Entry Point):**
  Provisions a native Kubernetes Service of `type: LoadBalancer` with the GDC internal load balancer annotation (`networking.gke.io/load-balancer-type: "Internal"`). The GDC platform load balancer controller allocates a static ingress VIP from the cluster's ingress IP pool, routing external HTTP (80) and HTTPS (443) traffic directly to the high-availability `gdc-dev-landing-page` pods.
* **Pathway B: Kubernetes Gateway API (`manifests/gdc/gateway.yaml` - Recommended Modern Standard):**
  Uses the standard Kubernetes Gateway API (`gateway.networking.k8s.io/v1`) with `GatewayClass`, `Gateway`, and `HTTPRoute` resources annotated for internal platform load balancing (`networking.gke.io/load-balancer-type: "Internal"`). It exposes host-based routing for `dev.gdc.local` to split traffic between the Landing Page (`/`) and dynamic user session pods (`/instances/*`).

#### 2. Retrieving the Assigned Ingress VIP

Run the following command on your deployment terminal to obtain the allocated VIP:

```bash
# Obtain the LoadBalancer Service VIP:
export LB_IP=$(kubectl get svc gdc-dev-loadbalancer -n gdc-dev -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Alternatively, obtain the Gateway API VIP:
export GATEWAY_IP=$(kubectl get gateway gdc-dev-gateway -n gdc-dev -o jsonpath='{.status.addresses[0].value}')

# Set the active ingress IP:
export INGRESS_IP="${LB_IP:-$GATEWAY_IP}"
echo "Routable Ingress VIP: ${INGRESS_IP}"
```

#### 3. Enterprise DNS & Workstation Routing Setup

To enable developers to access the environment using standard domain names (`https://dev.gdc.local`):

* **Enterprise DNS (Corporate Active Directory / BIND / CoreDNS):**
  Network administrators add a forward `A` record in the enterprise DNS server resolving `dev.gdc.local` to `${INGRESS_IP}`:
  ```text
  dev.gdc.local.    IN    A    <INGRESS_IP>
  ```
* **Developer Workstation `/etc/hosts` Mapping (Air-Gapped Lab / Jump Host):**
  For testing or environments without direct administrative control over corporate DNS, add the mapping to the developer workstation's local hosts file:
  ```bash
  echo "${INGRESS_IP} dev.gdc.local" | sudo tee -a /etc/hosts
  ```

#### 4. Verifying External Ingress Health

Before directing developers to the portal, verify connectivity from an external workstation on the developer network:

```bash
# 1. Probe health endpoint directly via IP with Host header:
curl -k -H "Host: dev.gdc.local" http://${INGRESS_IP}/health
# Expected Output: {"status": "healthy", "service": "gdc-dev-landing-page"}

# 2. Probe health endpoint via configured DNS hostname:
curl -k https://dev.gdc.local/health
# Expected Output: {"status": "healthy", "service": "gdc-dev-landing-page"}
```

#### 5. Developer Access Workflow & Endpoints

Once DNS is configured, developers access the platform using two primary URL endpoints:

1. **Central Developer Workspace Landing Page (`https://dev.gdc.local/`):**
   * **Authentication:** Authenticates developers via Keycloak OIDC Single Sign-On (or Mock Auth in lab mode).
   * **Dashboard Features:** Displays the active workspace sessions, multi-project workspace manager, template generator (Telemetry, Microservice, Clean), and system health metrics.
2. **Direct Workspace IDE Session (`https://dev.gdc.local/instances/<project_name>`):**
   * Example: `https://dev.gdc.local/instances/default-workspace` or `https://dev.gdc.local/instances/telemetry-service`
   * **Full Web IDE:** Loads the Monaco code editor, integrated in-pod terminal dock, and ReAct Multi-Agent Swarm panel.
   * **Storage Persistence:** All code, Git history, and project configuration files are written to `/home/dev/workspace` and permanently backed by non-volatile GDC block storage (`standard-rwo` PVC).
   * **Seamless Project Switching:** Developers switch between projects directly within the UI without re-authenticating.

---

### 3.3 Staging Lab Walkthrough: Progressive Phased Rollout (Optional)

If validating in a staging lab or migrating an existing environment incrementally, you can execute the zero-downtime 3-phase delivery pathway:

#### Phase 1: Baseline & Gateway API Routing (Mock Auth)
1. **Configure Manifest Placeholders:** Point manifests to your target project and registry:
   ```bash
   ./configure-blueprints.sh -n gdc-dev -r ${REGISTRY_HOST} -d p13-gdc-dev
   ```
2. **Apply Core Manifests & Ingress LoadBalancer:**
   ```bash
   kubectl apply -f p13-gdc-dev/manifests/gdc/namespace.yaml
   kubectl apply -f p13-gdc-dev/manifests/gdc/mock-auth-configmap.yaml
   kubectl apply -f p13-gdc-dev/manifests/gdc/gateway.yaml
   kubectl apply -f p13-gdc-dev/manifests/gdc/loadbalancer.yaml
   kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-operator.yaml
   ```
3. **Rollout & Verify Readiness:**
   ```bash
   kubectl rollout restart deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
   kubectl rollout status deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
   ```

#### Phase 2: Production Keycloak (`p12-keycloak`) OIDC Integration
When transitioning from mock authentication to enterprise Keycloak SSO:
1. **Configure ConfigMap Authority:** Update `p13-gdc-dev/manifests/gdc/oidc-auth-configmap.yaml` so `OIDC_AUTHORITY` points to `https://keycloak.gdc.local/realms/gdc-dev-realm`.
2. **Execute Zero-Downtime In-Place Upgrade:** Apply Phase 2 manifests to transition running containers to `AUTH_MODE: oidc`:
   ```bash
   kubectl apply -f p13-gdc-dev/manifests/gdc/oidc-auth-configmap.yaml
   kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-phase2-deployment.yaml
   kubectl rollout status deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
   ```

#### Phase 2 Optional: Sovereign AI Inference Gateway Integration (Gemma Gateway vs. Sovereign Gemini)
To connect developer sessions to sovereign AI inference running within the air-gapped environment:

* **Pathway A (Primary / Default): Sovereign Gemma Gateway (`gdc_gemma_gw`):**
  Connects to the in-cluster Gemma 4 Gateway running on local GDC GPU/TPU worker nodes:
  ```bash
  kubectl apply -f p13-gdc-dev/manifests/gdc/ai-gateway-configmap.yaml
  kubectl apply -f p13-gdc-dev/manifests/gdc/network-policy-ai.yaml
  kubectl rollout restart deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
  ```

* **Pathway B (Alternative): Sovereign GDC Air-Gapped Gemini Endpoint (`gemini.gdc.local`):**
  If utilizing an air-gapped internal sovereign Gemini appliance or endpoint:
  ```bash
  cat << 'EOF' | kubectl apply -n gdc-dev -f -
  apiVersion: v1
  kind: ConfigMap
  metadata:
    name: gdc-dev-ai-config
  data:
    AI_ENABLED: "true"
    AI_PROVIDER: "gemini"
    OPENAI_API_BASE_URL: "https://gemini.gdc.local/v1"
    AI_DEFAULT_MODEL: "gemini-2.0-flash"
    AI_CODER_MODEL: "gemini-2.0-pro"
  EOF
  kubectl rollout restart deployment/gdc-dev-landing-page -n gdc-dev
  ```

#### Phase 3: Upgrade to In-Pod Agentic AI & Multi-Tenant Hardening
To upgrade the running Phase 2 cluster to the full in-pod ReAct Agentic Swarm:
```bash
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-agent-configmap.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-phase3-deployment.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/certificate.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/network-policy.yaml
kubectl rollout restart deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
```

---

## **Section 4: Developer Workspace Allocation, Persistent Storage & Lifecycle on GDC-ag**

In enterprise air-gapped Google Distributed Cloud (GDC) environments, developer workspace allocation must balance self-service developer agility with strict regulatory compliance, multi-tenant isolation, and node capacity governance. This section details how workspaces are provisioned, assigned to authenticated identities, isolated at the filesystem and network layers, and governed throughout their operational lifecycle.

### 4.1 Developer Identity & Tenancy Mapping

Developer identity in GDC Dev is rooted in enterprise Single Sign-On (SSO) via Keycloak OIDC (Pattern 12) or federated enterprise identity providers (Active Directory, FreeIPA, Google Workspace).

1. **Authentication & Identity Flow:**
   * Developers authenticate against the sovereign Keycloak realm (`gdc-dev-realm`).
   * Upon successful authentication, the Gateway API / Ingress layer (Envoy Gateway or OAuth2-Proxy) validates the JSON Web Token (JWT) and injects standardized identity headers into the upstream request:
     * `X-User-ID`: The developer's canonical identifier (e.g. `alice@gdc.local` or `developer-alice`).
     * `X-Forwarded-User`: Downstream proxy username claim.
     * `X-Forwarded-Email`: Enterprise email address.
2. **Deterministic Workspace Identification:**
   * The Operator derives a deterministic, Kubernetes-safe workspace identifier from the authenticated user identity:
     ```bash
     # Sanitized user hash for Kubernetes resource naming:
     USER_HASH=$(echo -n "alice@gdc.local" | md5sum | cut -c1-8)
     # Resource name format:
     # workspace-pvc-<user-hash>  -> workspace-pvc-a1b2c3d4
     # gdc-dev-workspace-<user-hash> -> gdc-dev-workspace-a1b2c3d4
     ```
3. **Tenancy Models:**
   * **Multi-Tenant Shared Namespace (Default):** Workspaces reside in the `gdc-dev` namespace. Isolation is enforced via dedicated per-user PersistentVolumeClaims, non-root user namespaces (UID 1000 `dev`), Kubernetes `NetworkPolicy` enforcements, and individual `HTTPRoute` path boundaries (`/instances/<session-id>`).
   * **Dedicated Per-Team / Enclave Namespaces:** For projects with strict classification or compliance boundaries, the Operator or GitOps controller provisions dedicated namespaces (e.g. `gdc-dev-team-alpha`), each with dedicated `ResourceQuota`, `LimitRange`, and egress network policies.

---

### 4.2 Allocation Pathway A: Automated Just-In-Time (JIT) Dynamic Self-Service Allocation

In standard operations, developer workspaces are allocated dynamically on-demand when a developer logs into the portal:

```
+---------------------------------------------------------------------------------------------------+
|                        Automated JIT Developer Workspace Allocation Flow                         |
|                                                                                                   |
|  [Developer Browser]                                                                              |
|          |                                                                                        |
|          v                                                                                        |
|  [1. HTTPS Request -> https://dev.gdc.local]                                                      |
|          |                                                                                        |
|          v                                                                                        |
|  [2. Keycloak OIDC Gateway]                                                                       |
|     (Validates credentials -> injects X-User-ID: alice@gdc.local)                                 |
|          |                                                                                        |
|          v                                                                                        |
|  [3. GDC Dev Operator / Landing Page]                                                              |
|     |-- Check: Does PVC 'workspace-pvc-alice' exist?                                              |
|     |     NO  --> Call Kube API: Provision 20Gi standard-rwo GDC Block Storage PVC                |
|     |     YES --> Reuse existing PVC                                                              |
|     |                                                                                             |
|     |-- Check: Is session pod 'gdc-dev-workspace-alice' running?                                  |
|     |     NO  --> Spawn session pod attaching 'workspace-pvc-alice' to /home/dev/workspace        |
|     |     YES --> Route to existing container                                                     |
|     |                                                                                             |
|     |-- Configure HTTPRoute: /instances/alice -> gdc-dev-workspace-alice:8080                     |
|          |                                                                                        |
|          v                                                                                        |
|  [4. Browser Redirected to /instances/alice]                                                      |
|     (Developer IDE initialized with persistent storage, pre-baked CLI tooling, and AI dock)       |
+---------------------------------------------------------------------------------------------------+
```

#### Step-by-Step JIT Lifecycle:
1. **SSO Ingress:** The developer visits `https://dev.gdc.local` and completes Keycloak authentication.
2. **Operator Lookup:** The Operator intercepts the initial request, parses `X-User-ID`, and queries the cluster for existing resources matching `gdc.dev/user: alice`.
3. **Storage Claim Provisioning:** If the user is logging in for the first time, the Operator generates a 20Gi `PersistentVolumeClaim` backed by GDC block storage (`standard-rwo`).
4. **Session Container Provisioning:** The Operator spawns the developer workspace pod with pre-baked tooling (`gdcloud`, `kubectl`, `helm`, `git`, `podman`).
5. **Entrypoint Bootstrapping:** On initial volume mount, the container entrypoint verifies `/home/dev/workspace`. If empty, it executes `ensure_workspace_dir()` to bootstrap `main.py` and `README.md` with proper ownership (`dev:dev`, UID 1000).
6. **Dynamic Routing:** The Operator binds an `HTTPRoute` rule mapping `/instances/alice` to the newly provisioned session pod.

---

### 4.3 Allocation Pathway B: Declarative Administrative Pre-Allocation (GitOps / CLI)

In highly secure air-gapped environments, platform administrators often pre-allocate dedicated developer workspaces ahead of team onboarding. This pathway enables administrators to assign custom compute profiles (e.g., GPU accelerators, heavy RAM allocations for machine learning, or custom base container images).

#### 1. Pre-Allocate the Developer PersistentVolumeClaim (`workspace-pvc-alice.yaml`):
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workspace-pvc-alice
  namespace: gdc-dev
  labels:
    app.kubernetes.io/name: gdc-dev
    app.kubernetes.io/component: workspace-storage
    gdc.dev/user: "alice"
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-rwo
  resources:
    requests:
      storage: 20Gi
```

#### 2. Declare the Developer Workspace Session Deployment (`workspace-session-alice.yaml`):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gdc-dev-workspace-alice
  namespace: gdc-dev
  labels:
    app.kubernetes.io/name: gdc-dev-workspace
    gdc.dev/user: "alice"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gdc-dev-workspace-alice
  template:
    metadata:
      labels:
        app: gdc-dev-workspace-alice
        gdc.dev/user: "alice"
    spec:
      serviceAccountName: gdc-dev-operator-sa
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        runAsNonRoot: true
      containers:
      - name: workspace
        image: harbor.shared-services.gdc.local/my-org/gdc-dev-workspace:latest # kpt-set: ${registry-host}/gdc-dev-workspace:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http-ide
        env:
        - name: DEV_USER_ID
          value: "alice@gdc.local"
        - name: DEV_WORKSPACE_ROOT
          value: "/home/dev/workspace"
        - name: DEV_PROJECTS_ROOT
          value: "/home/dev/workspace/projects"
        - name: AUTH_MODE
          value: "oidc"
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
        volumeMounts:
        - name: workspace-storage
          mountPath: /home/dev/workspace
      volumes:
      - name: workspace-storage
        persistentVolumeClaim:
          claimName: workspace-pvc-alice
```

#### 3. Declare the Developer Workspace Service & HTTPRoute (`workspace-routing-alice.yaml`):
```yaml
apiVersion: v1
kind: Service
metadata:
  name: gdc-dev-workspace-alice
  namespace: gdc-dev
  labels:
    app: gdc-dev-workspace-alice
spec:
  selector:
    app: gdc-dev-workspace-alice
  ports:
  - port: 8080
    targetPort: 8080
    name: http
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: gdc-dev-route-alice
  namespace: gdc-dev
  labels:
    gdc.dev/user: "alice"
spec:
  parentRefs:
  - name: gdc-dev-gateway
    namespace: gdc-dev
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /instances/alice
    backendRefs:
    - name: gdc-dev-workspace-alice
      port: 8080
```

#### 4. Applying the Pre-Allocation via Terminal:
```bash
# Apply storage, deployment, and routing in gdc-dev namespace
kubectl apply -f workspace-pvc-alice.yaml
kubectl apply -f workspace-session-alice.yaml
kubectl apply -f workspace-routing-alice.yaml

# Verify pod status and persistent volume binding
kubectl get pvc -l gdc.dev/user=alice -n gdc-dev
kubectl get pods -l gdc.dev/user=alice -n gdc-dev
kubectl get httproute gdc-dev-route-alice -n gdc-dev
```

---

### 4.4 Multi-Project Workspace Allocation within a Tenancy

Once a developer is allocated a workspace tenancy, they are not constrained to a single flat folder. `gdc-dev` provides built-in multi-project workspace isolation:

* **Primary Tenancy Anchor:**
  * `${DEV_WORKSPACE_ROOT}` is fixed to `/home/dev/workspace`, mounted directly to the developer's GDC block storage PVC.
* **Secondary Project Allocation:**
  * Developers can allocate secondary project folders directly from the IDE:
    * **Via Web UI:** Click **`⚙️ Projects`** -> **`➕ New`** tab -> Select a project template (`📐 Telemetry Service`, `🚀 Python Microservice`, or `🧹 Clean Workspace`) and enter a project name (e.g. `telemetry-service`).
    * **Via In-Pod API:**
      ```bash
      curl -X POST http://localhost:8080/projects/create \
        -H "Content-Type: application/json" \
        -d '{"name": "telemetry-service", "template": "telemetry"}'
      ```
* **Production GDC Persistence Structure:**
  * By configuring `DEV_PROJECTS_ROOT: "/home/dev/workspace/projects"`, all secondary projects are placed on the developer's persistent block storage volume (`/home/dev/workspace/projects/<name>`).
  * Secondary projects permanently survive overnight pod hibernations and container restarts.
* **Confinement & Tool Isolation:**
  * All file editing APIs (`/files/save`, `/files/delete`) and in-pod Agentic AI tools (`read_file`, `write_file`, `apply_diff`, `list_directory`) are sandboxed to the active project folder.
  * The terminal automatically adjusts its prompt (`dev@gdc-session:~/telemetry-service$`) to prevent accidental operations in adjacent codebases.

---

### 4.5 Resource Governance & Multi-Tenant Quotas (Noisy Neighbor Prevention)

To prevent individual developer compilations, container builds (`buildah`/`podman`), or AI workloads from starving cluster compute resources, platform operators enforce Kubernetes `ResourceQuota` and `LimitRange` controls:

#### 1. Developer Namespace ResourceQuota (`gdc-dev-resource-quota.yaml`):
```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: gdc-dev-tenancy-quota
  namespace: gdc-dev
spec:
  hard:
    requests.cpu: "32"
    requests.memory: 64Gi
    limits.cpu: "64"
    limits.memory: 128Gi
    requests.storage: 500Gi
    persistentvolumeclaims: "25"
    pods: "30"
```

#### 2. Default Container Limits (`gdc-dev-limit-range.yaml`):
```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: gdc-dev-container-limits
  namespace: gdc-dev
spec:
  limits:
  - type: Container
    default:
      cpu: 2000m
      memory: 4Gi
    defaultRequest:
      cpu: 500m
      memory: 1Gi
    max:
      cpu: 4000m
      memory: 8Gi
    min:
      cpu: 100m
      memory: 256Mi
```

---

### 4.6 Workspace Lifecycle, Idle Hibernation & Deprovisioning Runbooks

#### Lifecycle State Transitions:
```
+---------------+     User Login       +----------------+    Idle Timeout (30m)    +-------------------+
|  UNALLOCATED  | -------------------> | ACTIVE SESSION | -----------------------> | HIBERNATED POD    |
+---------------+                      +----------------+                          +-------------------+
                                               |                                             |
                                               | User Re-login                               | User Re-login
                                               +-------------------+                         |
                                                                   |                         |
                                                                   v                         v
                                                       +---------------------------------------+
                                                       | PVC Mounted -> 100% Code State Active |
                                                       +---------------------------------------+
                                                                   |
                                                                   | Developer Offboarded
                                                                   v
                                                       +---------------------------------------+
                                                       | ARCHIVED & RECLAIMED (Storage freed)  |
                                                       +---------------------------------------+
```

#### 1. Idle Hibernation (Scale-to-Zero):
* **Inactivity Detection:** When a developer disconnects or remains idle past the configured inactivity threshold (default: `30 minutes`), the GDC Dev Operator scales the workspace deployment replica to `0`.
* **Compute Reclamation:** CPU and RAM allocations are immediately returned to the GDC node pool, enabling high multi-tenant density.
* **Storage Protection:** The developer's underlying block storage PVC (`workspace-pvc-<user>`) remains bound and intact.

#### 2. Next-Day Resumption:
* When the developer logs back in, the Operator instantly spins the deployment back to `1` replica and re-attaches the existing PVC.
* All Git branches, uncommitted changes, installed packages, and project directories are restored in under **5 seconds**.

#### 3. Offboarding & Workspace Reclamation Procedure:
When a developer leaves the engineering organization or transitions off a project, execute this runbook to reclaim resources:

```bash
USER_ID="alice"

# Step 1: Optional - Archive workspace volume to GDC Object Storage / VolumeSnapshot
cat << EOF | kubectl apply -n gdc-dev -f -
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: workspace-snapshot-${USER_ID}-$(date +%F)
spec:
  volumeSnapshotClassName: gdc-snapshot-class
  source:
    persistentVolumeClaimName: workspace-pvc-${USER_ID}
EOF

# Step 2: Delete workspace session deployment and services
kubectl delete deployment gdc-dev-workspace-${USER_ID} -n gdc-dev
kubectl delete service gdc-dev-workspace-${USER_ID} -n gdc-dev
kubectl delete httproute gdc-dev-route-${USER_ID} -n gdc-dev

# Step 3: Reclaim persistent block storage volume
kubectl delete pvc workspace-pvc-${USER_ID} -n gdc-dev

# Step 4: Revoke developer access in Keycloak SSO realm
# (Remove developer from 'gdc-developers' group in Keycloak Admin Console or via Keycloak Admin API)
```

---

### 4.7 Verifying Persistent Volume Storage & Multi-User Isolation:
```bash
# 1. Provision a test developer workspace PVC using standard block storage
cat << 'EOF' | kubectl apply -n gdc-dev -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: gdc-dev-workspace-test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF

# 2. Spawn a temporary session writer pod to simulate developer file creation in /workspace
kubectl run pvc-writer --rm -i --restart=Never -n gdc-dev \
  --image=busybox:1.36 --overrides='
{
  "spec": {
    "containers": [
      {
        "name": "pvc-writer",
        "image": "busybox:1.36",
        "command": ["sh", "-c", "echo \"Persistent GDC volume check: user code preserved for next day\" > /workspace/main.py"],
        "volumeMounts": [{"name": "workspace-vol", "mountPath": "/workspace"}]
      }
    ],
    "volumes": [{"name": "workspace-vol", "persistentVolumeClaim": {"claimName": "gdc-dev-workspace-test-pvc"}}]
  }
}'

# 3. Spawn a fresh session reader pod attaching the exact same PVC and verify the file survived across pod deletion
kubectl run pvc-reader --rm -i --restart=Never -n gdc-dev \
  --image=busybox:1.36 --overrides='
{
  "spec": {
    "containers": [
      {
        "name": "pvc-reader",
        "image": "busybox:1.36",
        "command": ["sh", "-c", "sleep 2 && echo \"===============================================\" && echo \"✅ PASS: Persistent GDC volume check verified!\" && echo \"✅ SUCCESS: Data survived across pod deletion\" && echo \"===============================================\" && cat /workspace/main.py && echo \"\""],
        "volumeMounts": [{"name": "workspace-vol", "mountPath": "/workspace"}]
      }
    ],
    "volumes": [{"name": "workspace-vol", "persistentVolumeClaim": {"claimName": "gdc-dev-workspace-test-pvc"}}]
  }
}'

# 4. Clean up test PVC
kubectl delete pvc gdc-dev-workspace-test-pvc -n gdc-dev
```

---

## **Section 5: Production Verification & Testing**

### 1. Automated Structural Suite (TDD)
Execute the complete 43-test automated validation suite:
```bash
./p13-gdc-dev/test/verify.sh
```

**Verified Outputs (`44/44 PASS`):**
* **Phase 1 (8/8):** Gateway API spec (`HTTPRoute`), mock identity header checks (`X-User-ID`), standalone LoadBalancer Service (`loadbalancer.yaml`), and interactive execution (`POST /exec`).
* **Phase 2 (5/5):** Keycloak OIDC SSO manifests (`gdc-dev-phase2-deployment.yaml`, `oidc-auth-configmap.yaml`), unauthenticated/authenticated login portal transitions (`gdc-dev-realm`).
* **Phase 3 Hardening (4/4):** Platform PKI (`cert-manager.io/v1`), persistent PVC storage, multi-tenant NetworkPolicies.
* **Phase 3 Agentic AI (6/6):** Function calling tool schemas (`read_file`, `apply_diff`, `write_file`, `run_terminal_command`, `list_directory`), in-pod execution engine, selective auto-approval security gatekeeper, Phase 3 Helm values.
* **AI Integration (7/7):** Cross-namespace config structure, AI egress network policies, backwards-compatible UI rendering, Copy/Insert/Stop button contracts.
* **Phase 4 Multi-Agent Swarm (14/14):** Swarm ConfigMap & Helm declarations, `SWARM_PERSONAS` definitions (Architect, Coder, Reviewer, Swarm), least-privilege tool isolation, persona-based ReAct routing, in-IDE specialist selector UI, workspace disk persistence & project templates, and draggable terminal height & AI panel width resizers with `localStorage` persistence.

### 2. Demonstrating the Multi-Agent Swarm Experience in Action

Access the web IDE at `https://dev.gdc.local/instances/default-workspace` (or directly via the LoadBalancer VIP: `https://${INGRESS_IP}/instances/default-workspace`). The dock on the right displays the **`🤖 GDC Dev AI Swarm`** header with two side-by-side dropdown selectors.

1. **Swarm Specialist Persona Selector (`[ 🐝 Swarm ▼ ]`):**
   * Select **`🐝 Swarm (Collaborative)`**: The autonomous pipeline where the Architect plans, the Coder writes surgical diffs, and the Reviewer validates with unit tests.
   * Select **`📐 Architect Agent`**: Focused strictly on high-level architectural planning, system modularity, workspace AST exploration, and file scaffolding (tool permissions isolated to read-only queries: `read_file`, `list_directory`).
   * Select **`💻 Coder Agent`**: Dedicated to surgical code implementation, AST-aware unified diff authoring (`apply_diff`), and in-pod file editing (`write_file`).
   * Select **`🔍 Reviewer / QA Agent`**: Dedicated to test generation (`pytest`/`unittest`), security audits, and sandbox command verification (`run_terminal_command`).
2. **Interactive Model Selector & Auto-Tiering (`[ ⚡ 31b ▼ ]`):**
   * Choose between `⚡ 31b` (Reasoning default), `🚀 26b` (Fast MoE default), `🔄 Auto` (Dynamic Model Tiering), or configured sovereign GDC Gemini endpoints (`🌐 gemini-2.0-pro`, `⚡ gemini-2.0-flash`).
3. **Selective Auto-Approval & Surgical Diff Cards:**
   * Prompt the agent: *"Add a helper function to main.py that checks if an integer is prime, and call it in main()."*
   * The agent reads `main.py` autonomously, then pauses and displays an interactive **Diff Review Card** with `[✓ Approve & Execute]` and `[✕ Reject]`.
   * Click **`✓ Approve & Execute`** to update the editor. Click **`▶ Run Code`** to execute the updated script.
4. **1-Click Code Rollback:**
   * If you wish to undo the change, click the red **`[ ↩ Rollback Changes ]`** button on the agent's message. The prior file state is restored immediately in the editor.
5. **Terminal Auto-Repair Hook:**
   * Run a failing command in the terminal: `python3 -c "assert False, 'Enclave checksum verification failed'"`.
   * Click the orange **`[ ⚡ Fix with Gemma Agent ]`** button that appears under the trace to have the agent diagnose and repair the failure.
6. **Customizable Terminal Height & AI Output Width:**
   * **Terminal Height Adjustment:** Click and drag the horizontal splitter bar directly above the terminal dock up or down to adjust height smoothly, or use the quick preset buttons (`140px`, `220px`, `360px`, `500px`, or `⤢` to maximize). Double-clicking the splitter toggles between standard and expanded views.
   * **AI Panel Width Adjustment:** Click and drag the vertical splitter on the left edge of the AI output panel to customize width, or click preset buttons (`320`, `420`, `560`, or `⤢` to maximize).
   * **State Persistence:** Refresh the browser page (`F5`) or switch projects to confirm that your custom terminal height and AI panel width are retained automatically via browser `localStorage` (`gdc_dev_terminal_height` and `gdc_dev_ai_width`).

### 3. Configuring Sovereign Inference Endpoints & Models (Gemma Gateway vs. GDC Gemini)

Inference endpoints and model tags are managed declaratively via `gdc-dev-agent-config`. Organizations can choose between hosting local Gemma models or pointing to sovereign Gemini endpoints available in their GDC air-gapped rack:

#### Pathway A (Primary / Default): In-Cluster Sovereign Gemma Gateway (`gdc_gemma_gw`)
* **Role:** Best for self-contained environments with dedicated GPU/TPU nodes hosting in-cluster Gemma 4 models.
* **Endpoint:** `http://gemma-gateway.gemma-inference.svc.cluster.local/v1`
* **Dual-Model Tiering:**
  * `gemma4:31b`: Dense 31B reasoning model for deep architectural decomposition, complex debugging, and code reviews.
  * `gemma4:26b`: Fast MoE variant (~4B active params) for rapid code completions and surgical AST diff authoring.
* **Configuration (`gdc-dev-agent-configmap.yaml`):**
  ```yaml
  AI_PROVIDER: "gemma"
  OPENAI_API_BASE_URL: "http://gemma-gateway.gemma-inference.svc.cluster.local/v1"
  AI_TIER1_MODEL: "gemma4:26b"
  AI_CODER_MODEL: "gemma4:31b"
  AI_DEFAULT_MODEL: "gemma4:31b"
  ```

#### Pathway B (Alternative): Sovereign GDC Air-Gapped Gemini Endpoints (`gemini.gdc.local`)
* **Role:** Connects developer workspaces to a centralized sovereign Gemini service appliance or internal Gemini endpoint running within the air-gapped facility.
* **Endpoint:** `https://gemini.gdc.local/v1` (or your internal GDC Gemini proxy URL)
* **Model Versions:**
  * `AI_GEMINI_TIER1_MODEL`: Fast routine completion model (e.g. `gemini-2.0-flash`).
  * `AI_GEMINI_TIER2_MODEL`: Deep reasoning and planning model (e.g. `gemini-2.0-pro`).
* **Configuration (`gdc-dev-agent-configmap.yaml`):**
  ```yaml
  AI_PROVIDER: "gemini"
  OPENAI_API_BASE_URL: "https://gemini.gdc.local/v1"
  AI_GEMINI_TIER1_MODEL: "gemini-2.0-flash"
  AI_GEMINI_TIER2_MODEL: "gemini-2.0-pro"
  ```

Updating these keys in `gdc-dev-agent-configmap.yaml` dynamically adjusts the IDE dropdown selectors and backend routing payloads without requiring container image rebuilds.

### 4. Phase 4 Architecture: Multi-Agent Swarm Specialization
The platform organizes development workflows across a **3-Agent Collaborative Swarm**:
* **Architect Agent:** Decomposes user goals into structural blueprints, verifies file hierarchy, and specifies interfaces without modifying code.
* **Coder Agent:** Implements features via minimal, AST-aligned unified diffs (`apply_diff`) gated by human confirmation.
* **Reviewer / QA Agent:** Synthesizes test fixtures and executes them inside the terminal container sandbox (`run_terminal_command`), verifying zero regressions.
* **Principle of Least Privilege (PoLP):** Tool capabilities are strictly sandboxed per persona, preventing non-reviewer agents from running shell commands and non-coder agents from mutating files.

### 5. Multi-Project Workspace Management & Directory Isolation Architecture (GDC-ag Production Target)

In enterprise air-gapped environments on Google Distributed Cloud (GDC), developer teams rarely work on a single codebase. A typical developer tenancy requires maintaining multiple microservices, client libraries, infrastructure manifests, and integration test suites simultaneously. The GDC Developer Environment (`gdc-dev`) enforces strict physical and operational **Multi-Project Workspace Management and Directory Isolation**:

#### Directory Isolation Model & Mapping (`get_workspace_dir`)
`gdc-dev` segregates projects into independent file hierarchies resolved dynamically at runtime:
* **Primary / Default Workspace (`default-workspace`):**
  * Environment variable: `DEV_WORKSPACE_ROOT` (defaults to `/home/dev/workspace`).
  * Storage backend: Directly mounted to the developer's dedicated PersistentVolumeClaim (`workspace-pvc-<user-hash>`), backed by `gdc-block-storage` or `standard-rwo`.
* **Isolated Named Projects (`<project_name>`):**
  * Environment variable: `DEV_PROJECTS_ROOT` (defaults to `/tmp/dev-projects`).
  * Target path: `${DEV_PROJECTS_ROOT}/<project_name>` (e.g. `/tmp/dev-projects/telemetry-service`).
  * **Target GDC-ag Persistent Volume Mapping:** In physical GDC production racks, to ensure secondary projects are preserved permanently across overnight scale-to-zero pod hibernations, platform operators configure `DEV_PROJECTS_ROOT` inside the `gdc-dev-agent-config` ConfigMap or container deployment:
    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: gdc-dev-agent-config
      namespace: gdc-dev
    data:
      DEV_WORKSPACE_ROOT: "/home/dev/workspace"
      DEV_PROJECTS_ROOT: "/home/dev/workspace/projects"  # Anchored on persistent GDC block storage PVC
    ```
    Alternatively, an in-pod symlink (`/tmp/dev-projects -> /home/dev/workspace/projects`) ensures that container-level `/tmp/dev-projects/<name>` operations are transparently persisted directly into the developer's persistent block storage volume.

#### Security & Confinement Guarantees
* **Filesystem Sandboxing:** All file read, write, and delete operations (`/files/save`, `/files/delete`) are strictly resolved relative to `get_workspace_dir(session_id)`. Path traversal sequences (`../`) are stripped and sanitized, eliminating cross-project contamination or unauthorized access.
* **Agentic Tool Isolation:** In-pod AI agent tools (`read_file`, `write_file`, `apply_diff`, `list_directory`) pass `workspace_dir=get_workspace_dir(session_id)` to each tool handler. An AI agent working on `telemetry-service` has zero visibility into or access to files in `default-workspace` or other projects.
* **Dynamic Terminal Prompt Synchronization:** The integrated terminal automatically synchronizes its prompt with the active project root:
  ```bash
  # Active project: default-workspace
  dev@gdc-session:~/default-workspace$
  
  # Active project: telemetry-service
  dev@gdc-session:~/telemetry-service$
  ```
  This provides immediate visual confirmation of the shell working directory before developers or QA agents execute terminal commands (`run_terminal_command`).

#### Enterprise Project Lifecycles & SSO Continuity
* **Project Creation (`POST /projects/create`):** Scaffolds new projects from templates (`telemetry`, `microservice`, or `clean`) under `${DEV_PROJECTS_ROOT}/<project_name>`.
* **Zero Re-Authentication Project Switching:** When navigating between project endpoints (`/instances/<project_name>`), the platform preserves the domain-scoped session cookie (`dev_auth_user`) and URL query parameter (`?oidc_login=success`). Developers switch between multiple projects seamlessly without encountering repetitive Keycloak login prompts.
* **Clean Project Purging (`POST /projects/delete`):** Recursively deletes the specified project directory (`shutil.rmtree`) from disk without impacting any other project or the primary workspace, and safely falls back to `default-workspace`.

### 6. Multi-Agent Swarm Validation: Automated & Interactive CLI Testing (`test-swarm.py`)

A specialized CLI test harness validates all 10 validation stages: 4 personas, tool isolation boundaries, rollback integrity, multi-project workspace isolation, full output preservation, pre-baked tooling, and OIDC session continuity directly against the cluster ingress entry point (without requiring `kubectl port-forward`):

```bash
# 1. Obtain the assigned LoadBalancer IP or Gateway VIP:
export INGRESS_IP=$(kubectl get svc gdc-dev-loadbalancer -n gdc-dev -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
export GDC_DEV_ENDPOINT="https://${INGRESS_IP}/instances/default-workspace/ai-chat"

# 2. Run automated test directly against the LoadBalancer entry point:
./p13-gdc-dev/scripts/test-swarm.py --endpoint "${GDC_DEV_ENDPOINT}" --host-header dev.gdc.local

# Or run directly via enterprise DNS once dev.gdc.local is configured:
./p13-gdc-dev/scripts/test-swarm.py --endpoint "https://dev.gdc.local/instances/default-workspace/ai-chat"

# 3. Run interactive step-by-step walkthrough (pauses between each test stage):
./p13-gdc-dev/scripts/test-swarm.py --endpoint "${GDC_DEV_ENDPOINT}" --host-header dev.gdc.local --interactive

# 4. Test with dense 31B reasoning model (extended timeout up to 300s):
./p13-gdc-dev/scripts/test-swarm.py --endpoint "${GDC_DEV_ENDPOINT}" --host-header dev.gdc.local --model gemma4:31b --timeout 300

# 5. Run offline in-memory verification (bypasses cluster network entirely):
./p13-gdc-dev/scripts/test-swarm.py --local

# (Optional Emulation Fallback): If testing in an isolated staging emulator without a physical LoadBalancer controller:
# kubectl port-forward svc/gdc-dev-landing-page 8080:8080 -n gdc-dev
# ./p13-gdc-dev/scripts/test-swarm.py --endpoint "http://localhost:8080/instances/default-workspace/ai-chat"
```

### 7. End-to-End GUI Walkthrough & Test Prompts

To test and demonstrate the Multi-Agent Swarm directly in the web browser interface, open **`https://dev.gdc.local/instances/default-workspace`** (or `https://${INGRESS_IP}/instances/default-workspace` with `/etc/hosts` mapped to `dev.gdc.local`):

> [!TIP]
> **Model Selection:** In the AI dock header on the right, select **`[ ⚡ 31b (Reasoning) ]`** for deep architectural planning and reasoning, or **`[ 🚀 26b (Fast MoE) ]`** for rapid completions.

#### Step 1: 📐 Architect Agent — System Planning & Read-Only Confinement
* **Dropdown Selection:** Role = `[ 📐 Architect (Planning) ]` | Model = `[ 🚀 26b (Fast MoE) ]`
* **Prompt to Enter:**
  ```text
  Design a modular telemetry and health-check service for GDC air-gapped workloads. Specify the file hierarchy, data contracts, and integration points with Kubernetes liveness probes.
  ```
* **Expected UI Result:**
  * Displays `[ 📐 Architect Agent ]` badge in blue.
  * Generates an architectural design breakdown and API schema.
  * Strictly restricted to read-only tools (`read_file`, `list_directory`). Does not mutate files or execute shell commands.
  * **Full Output Preservation (`💾 Save as File` / `📋 Copy All`):**
    * Click **`💾 Save as File`** on the response card to write the full, unstripped architectural specification directly to `architecture.md` on the workspace disk. Run `ls` and `cat architecture.md` in the terminal to verify.
    * Click **`📋 Copy All`** to copy the complete raw markdown output to the clipboard.

#### Step 2: 💻 Coder Agent — Surgical Diffs & Selective Auto-Approval Handshake
* **Dropdown Selection:** Role = `[ 💻 Coder (Implementation) ]` | Model = `[ 🚀 26b (Fast MoE) ]`
* **Pre-condition:** Open `main.py` in the workspace editor with baseline code (`def main(): print('Hello GDC')`).
* **Prompt to Enter:**
  ```text
  Add a helper function is_prime(n) to main.py and call it in main() to print all prime numbers up to 20.
  ```
* **Expected UI Result:**
  * Displays `[ 💻 Coder Agent ]` badge in green.
  * Autonomously reads `main.py` via `read_file`.
  * Renders an interactive **Diff Approval Card** with colorized changes, target file `main.py`, and action buttons: **`[ ✓ Approve & Execute ]`** and **`[ ✕ Reject ]`**.
  * Clicking **`[ ✓ Approve & Execute ]`** immediately updates the live code in the editor.
  * Clicking **`▶ Run Code`** executes the updated script in the integrated terminal.

#### Step 3: 🔍 Reviewer / QA Agent — Automated Test Suite Synthesis
* **Dropdown Selection:** Role = `[ 🔍 Reviewer (QA & Tests) ]` | Model = `[ 🚀 26b (Fast MoE) ]`
* **Prompt to Enter:**
  ```text
  Synthesize a comprehensive pytest test suite for is_prime(n) in test_main.py covering edge cases: 0, 1, negative numbers, small primes (2, 3), and non-primes (4, 9, 15).
  ```
* **Expected UI Result:**
  * Displays `[ 🔍 Reviewer Agent ]` badge in yellow/gold.
  * Synthesizes `test_main.py` with parametrized assertions.
  * Possesses sandbox execution permissions (`run_terminal_command`) for running test suites, without direct code mutation permissions.

#### Step 4: 🐝 Multi-Agent Swarm Mode — Autonomous 3-Stage Pipeline
* **Dropdown Selection:** Role = `[ 🐝 Swarm (Collaborative) ]` | Model = `[ 🚀 26b (Fast MoE) ]`
* **Prompt to Enter:**
  ```text
  Build a sovereign key-value cache with TTL expiration in cache.py and verify it with a unit test.
  ```
* **Expected UI Result:**
  * Displays `[ 🐝 Multi-Agent Swarm ]` badge in purple.
  * Coordinates the 3-stage lifecycle: Architect designs architecture -> Coder generates implementation and diff card -> Reviewer generates test suite.

#### Step 5: ↩️ 1-Click Code Rollback
* **Action:**
  * Beneath the Coder agent's completed message in the AI dock, click the red button: **`[ ↩ Rollback Changes ]`**.
* **Expected UI Result:**
  * The active editor immediately restores `main.py` bit-for-bit to its exact pre-mutation state.
  * A confirmation toast confirms: *"Rollback successful: restored baseline state."*

#### Step 6: ⚡ Terminal Auto-Repair ("Fix with Gemma Agent")
* **Action:**
  * In the integrated terminal at the bottom of the workspace, run:
    ```bash
    python3 -c "assert False, 'Enclave checksum verification failed'"
    ```
  * Click the orange **`[ ⚡ Fix with Gemma Agent ]`** action pill that appears beneath the error.
* **Expected UI Result:**
  * Passes terminal stack trace to the Gemma agent, diagnosing the root cause and suggesting a fix.

#### Step 7: 📁 Workspace File Management & Disk Persistence
* **Save to Disk & Terminal Sync (`Ctrl+S` / `💾 Save`):**
  * Click **`[ + File ]`** in the file explorer and create `architecture.md`.
  * Paste notes or code into the editor and press `Ctrl+S` (or click `💾 Save`).
  * In the terminal, run `ls` and `cat architecture.md` — files saved in the GUI are stored directly on the persistent volume disk and are immediately accessible.
* **Refresh Files from Disk (`[ 🔄 ]`):**
  * In the terminal, create files via shell or test suites (e.g., `touch config.json`).
  * Click the **`[ 🔄 ]`** refresh button on the explorer toolbar to sync new files into the GUI instantly.
* **Delete File (`[ 🗑️ ]`):**
  * Hover over any file in the explorer and click the red **`[ 🗑️ ]`** trash icon to delete it from disk with confirmation.

#### Step 8: 🔄 Multi-Project Management & Dynamic Workspace Switching
* **Header Project Dropdown (`#header-project-select`):**
  * Switch between projects (`default-workspace`, custom projects) directly via the top navigation dropdown.
  * Notice the integrated terminal prompt tracks active project context: `dev@gdc-session:~/<project-name>$`.
* **Open Project Manager (`⚙️ Projects` / `📁`):**
  * Click **`⚙️ Projects`** next to the dropdown to manage projects across 3 tabs:
    * **`🔄 Switch`**: Lists all projects discovered on disk, file counts, and direct switch/delete actions.
    * **`➕ New`**: Provisions an isolated project (e.g., `telemetry-service`) from templates (Telemetry, Microservice, or Empty).
    * **`🧹 Reset`**: Wipes the current project's workspace back to template defaults without affecting other projects.
* **Workspace Isolation:**
  * Files for each project are strictly isolated under `/tmp/dev-projects/<project-name>`.
  * Run `ls` in the terminal to verify clean directory isolation.
* **Project Deletion:**
  * In the `🔄 Switch` tab, click **`🗑️ Delete`** next to any custom project to completely purge its directory and files from disk.

#### Step 9: 🔐 Enterprise OIDC Session Continuity Across Project Switches
* **Zero Re-Authentication:**
  * When logged in via Keycloak OIDC as `oidc-developer@gdc.local`, switching projects via the dropdown or modal preserves authentication state via the domain-scoped session cookie (`dev_auth_user`) and URL query parameter (`?oidc_login=success`).
  * Developers can switch between multiple projects seamlessly without being redirected back to login.
* **Explicit Session Termination:**
  * Click **`Exit Session`** in the header to clear session cookies (`Max-Age=0`) and return to the SSO login portal.

---

## **Section 6: Operations, Performance & Rollback Runbooks**

### Sovereign Inference Performance & Sizing on GDC Hardware

> [!NOTE]
> **Production GDC Air-Gapped Platforms:** On physical GDC-ag hardware equipped with GPU/TPU accelerator pools and **vLLM PagedAttention** serving via `gdc_gemma_gw`, reasoning completions execute with low latency (<10 seconds).
> The platform configures `AI_REQUEST_TIMEOUT: "300"` (5 minutes) across `gdc-dev-agent-config` to match `gdc_gemma_gw`'s `GATEWAY_TIMEOUT=300.0`, preventing premature client disconnections during complex multi-step reasoning traces.

### Rollback Runbooks & Procedures

#### Procedure A: Workspace Code Rollback
If an agent-modified file needs to be reverted:
1. **1-Click UI Rollback:** Click **`[ ↩ Rollback Changes ]`** on the agent's message in the AI dock.
2. **Terminal Rollback:** Execute `git checkout <filename>` or `git restore <filename>` in the integrated terminal.

#### Procedure B: Platform Deployment Rollback (`Phase 3 -> Phase 2`)
To revert the cluster infrastructure from Phase 3 Agentic mode back to Phase 2 Passive AI Co-Pilot:

```bash
# Automated rollback script
./p13-gdc-dev/scripts/rollback-to-phase2.sh
```

**Manual Rollback Steps:**
```bash
REGISTRY_HOST=${REGISTRY_HOST:-"harbor.shared-services.gdc.local/my-org"}

# 1. Restore Phase 2 ConfigMap and Deployment
kubectl apply -f p13-gdc-dev/manifests/gdc/ai-gateway-configmap.yaml
kubectl apply -f p13-gdc-dev/manifests/gdc/gdc-dev-phase2-deployment.yaml

# 2. Reset deployment images
kubectl set image deployment/gdc-dev-landing-page landing-page="${REGISTRY_HOST}/gdc-dev-landing-page:latest" -n gdc-dev
kubectl set image deployment/gdc-dev-operator operator="${REGISTRY_HOST}/gdc-dev-operator:latest" -n gdc-dev

# 3. Rollout restart
kubectl rollout restart deployment/gdc-dev-landing-page deployment/gdc-dev-operator -n gdc-dev
kubectl rollout status deployment/gdc-dev-landing-page -n gdc-dev
```

---

### Troubleshooting Common Failures

| Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| `Gateway API HTTPRoute reports PROGRAMMED: False` | The target `Gateway` resource (`gdc-dev-gateway`) is not programmed or the specified `gatewayClassName` (`gdc-dev-gateway-class`) does not exist on the GKE cluster. | Verify that GDC Gateway API CRDs are installed and check `kubectl get gateway -n gdc-dev -o yaml`. |
| `Browser gets stuck in OIDC redirect loop or returns 401 Unauthorized` | Keycloak client redirect URIs do not match the Gateway host (`https://dev.gdc.local/auth/callback`), or the Gateway API OIDC filter is not injecting the `X-Forwarded-User` header. | Confirm `OIDC_AUTHORITY` in `oidc-auth-configmap.yaml` and verify that `Valid Redirect URIs` in Keycloak include `https://dev.gdc.local/*`. |
| `AI Assistant dock returns Gateway communication error: timed out` | Cross-namespace egress is blocked by NetworkPolicy or the LLM is warming up in VRAM. | Verify `gdc-dev-to-gemma-netpol` egress rules allow TCP port 80/8080 to `gemma-inference` and check `kubectl logs -n gemma-inference deployment/gemma-gateway`. |
| `Workspace session pod stuck in Pending state with PVC binding failure` | The `standard-rwo` StorageClass is not available on the cluster or the developer namespace `ResourceQuota` has exceeded its `requests.storage` limit. | Check `kubectl describe pvc -l app=gdc-dev-workspace-session -n gdc-dev` and verify GDC block/object storage capacity. |
| `Rollout exceeded progress deadline (0 out of 1 new replicas updated)` | Deployment was stuck due to non-existent ServiceAccount or image pull error, locking the controller. | Clear the frozen controller state via `kubectl delete deployment gdc-dev-landing-page -n gdc-dev` and re-apply the Phase 3 manifest. |

