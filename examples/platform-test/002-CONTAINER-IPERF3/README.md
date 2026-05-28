# 002-CONTAINER-IPERF3: Container to Container Network Performance Test

### TL;DR: GDC IaC Pipeline Automation

This directory contains a self-contained IaC (Infrastructure as Code) setup to satisfy the requirements of the **002-CONTAINER-IPERF3** test case, which automates secure container-to-container network performance and connectivity verification across GDC's logical and physical API planes using a **progressive, bottom-up staging stance**:

1. **Adhoc Sandbox ([setup-adhoc-env.sh](./setup-adhoc-env.sh)):** Validates OIDC/AIS identity synchronization loops interactively.
2. **Operator Scope ([setup-operator-sa.sh](./setup-operator-sa.sh)):** Performs out-of-band K8s-native bootstrapping directly on physical Admin/User Clusters for time-zero platform start-up.
3. **Tenant Scope ([setup-tenant-sa.sh](./setup-tenant-sa.sh)):** Provisions resources strictly within GDC-native customer tenant boundaries.

The orchestration is driven by `helmfile.yaml.gotmpl`, which dynamically routes cross-plane tokens and uses a namespaced `auth can-i` presync hook to securely handle asynchronous namespace and IAM replication delays without requiring cluster-wide administrative privileges.

---

## 1. Overview & Context

### Test Case Overview
- **ID:** 002-CONTAINER-IPERF3
- **Description:** Verify that authorized workloads can establish network connections and measure performance using iperf3 between containers inside the regional GDC project space.
- **Goal:** Automate the provisioning of the `iperf3-server` deployment/service, `iperf3-client` job, and project network policies in the `ioc-test-project-002` namespace, validating network isolation and network throughput.

### Mapping to 002-CONTAINER-IPERF3 Test Spec
- **PR-01 (RBAC):** Satisfied via `tenants.yaml` and `gdc-iam-role-bindings` chart.
- **PR-02 (Workloads):** Uses the standardized `networkstatic/iperf3:latest` image inside the tenant project namespace to run server and client pods.
- **Step 2-5 (Creation):** Automated via `gdc-iperf3` Helm chart with customizable ports (default `5201`), server Deployment, ClusterIP Service, and a single-run test Job.
- **Step 6 (Verification):** Automated check for Job `Completed` status and retrieval of performance throughput metrics.

### Assets
- **`tenants.yaml`**: The declarative desired-state manifest defining the tenant topology, target projects, regional cluster bindings, dynamic user IAM permissions, and iperf3 test workload parameters.
- **`helmfile.yaml.gotmpl`**: The core logical orchestration engine that dynamically parses `tenants.yaml` into ordered Helm releases. It implements multi-phase execution and incorporates the optimized namespaced `auth can-i` presync hook to poll regional cluster readiness safely without requiring cluster-wide Namespace privileges.
- **`tenant-bootstrap.yaml`**: The declarative Kubernetes manifest applied to the Global API Cluster to bootstrap the logical Service Accounts (`platform-bootstrap-sa`, `test-runner-sa`) and GDC-native IAM bindings.
- **`operator-bootstrap.yaml`**: The declarative Kubernetes manifest applied out-of-band directly to the regional Admin Cluster to provision local Service Accounts and local K8s `RoleBindings` scoped strictly to the `iac-root` namespace.
- **`setup-adhoc-env.sh`**: The interactive adhoc testing script that establishes certificate trust, guides the operator through double interactive OIDC logins (Platform Admin + IAC User) against GDC's AIS, and enforces a **30-second logical propagation wait** before executing Helm.
- **`setup-tenant-sa.sh`**: The automated script that deploys `tenant-bootstrap.yaml` to the Global API, extracts the resulting tokens, and generates the client-side **2-context** `.kubeconfig-sa` to authenticate headless tenant-scoped pipeline runs.
- **`setup-operator-sa.sh`**: The automated script that deploys `tenant-bootstrap.yaml` to the Global API and `operator-bootstrap.yaml` directly to the Admin Cluster out-of-band, extracts all 4 tokens, and constructs the **4-context** `.kubeconfig-sa` to authenticate headless operator-scoped bootstrap runs.

---
## 2. Execution Steps

### Option A: Adhoc / Sandbox Execution (Interactive OIDC)

For local sandbox validation and rapid design iterations, operators can use the full interactive workflow that directly integrates with the GDC AIS (Authentication & Identity Service). This method requires interactive OIDC logins and manual certificate trust establishment.

### Execution Steps

This flow is captured in the `setup-adhoc-env.sh` script and follows this sequence:

1. **Run the Adhoc Setup Script:**
   Execute the script to fetch certificates, perform the double login, and grant roles. You can pass a `VERSION` variable to avoid GDC Project ID reuse collisions:
   ```bash
   VERSION=-v2 ./setup-adhoc-env.sh
   ```
2. **The Script Flow Includes:**
   * **Certificate Fetching & Trust:** Fetches TLS certificates for the Console, AIS, and KMS endpoints and adds them to the local machine's trust store.
   * **Step 1: Platform Admin Login:** Prompts the operator to log in interactively as a highly privileged **Platform Admin** to perform organization-level bootstrapping.
   * **Project & IAM Bootstrap:** Creates the GDC `Project` and grants global roles (`platform-admin`, `project-creator`, `organization-iam-admin`, `user-cluster-admin`) to the target IaC user (`fop-iac@example.com`).
   * **Step 2: IAC User Login:** Prompts the operator to switch context by logging in again as the restricted **IAC User** to verify that the assigned roles have propagated via AIS.
   * **Execution:** Finally, runs `helmfile sync` using the active user context authorized by AIS.

---

### Option B: Executing the Operator-Scoped Pathway

For physical/local testing without Interactive OIDC, run as an operator with Service Accounts. Suitable also for execution on Adhoc Environments, Bare-Metal Bring-Up (T=0), and Physical Test Labs to ensure direct multi-plane routing and bypass OIDC/AIS propagation dependency entirely.

1. **Generate Service Account Credentials & 4-Context Kubeconfig:**
   Run the script using your active operator context to provision the Service Accounts and write their tokens into a local Kubeconfig file (`.kubeconfig-sa`):
   ```bash
   ./setup-operator-sa.sh
   ```

2. **Run Phase 1 - Project Infrastructure (Platform Admin SA Context):**
   Deploy the project logically on the Global API and bind the cluster on the Admin plane:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=iperf3 sync
   ```

3. **Run Phase 2 - Provision Container Workloads (Restricted Runner SA Context):**
   Provision iperf3 server deployments, client jobs, and project network policies directly in the regional project workspace:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=iperf3 sync
   ```

---
### Option C: Executing the Tenant-Scoped Pathway (Production & Staging)

Designed for Production GDC-AG tenant environments and automated GitOps pipelines.

#### 1. Execution Commands

1. **Generate Service Account Credentials:**
   Run the bootstrap script using your active platform context to provision the Service Accounts and write their tokens into a local Kubeconfig file (`.kubeconfig-sa`):
   ```bash
   ./setup-tenant-sa.sh
   ```

   > [!WARNING]
   > **Role & Namespace Propagation Delay:**
   > GDC's background identity propagation engines require around **15 to 20 seconds** to replicate namespaces, projects, and IAM role permissions down from the logical Global API to physical regional clusters. Running step 2 immediately may result in immediate authentication or authorization failures.
   
   * **Optional: Verify Role Propagation Status:**
     Before proceeding, run the following access check to confirm the restricted runner credentials have propagated and are active in the target project namespace:
     ```bash
     kubectl --kubeconfig=./.kubeconfig-sa --context=runner-context auth can-i create deployments -n ioc-test-project-002-v1
     ```
     *Do not proceed to step 2 until this command returns `yes`.*

2. **Deploy the Project and iperf3 Workloads:**
   Run the `helmfile sync` using the generated `.kubeconfig-sa` file to provision both the GDC logical project environment and the regional container workloads:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile sync
   ```

---

## 3. Verification Steps

### 1. Resource Creation Verification
Confirm that all resources have been created in the project namespace (on the User/Admin Cluster):
```bash
# Verify the iperf3 Server Deployment status
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get deployments iperf3-server -n ioc-test-project-002-v1

# Verify the iperf3 Server Service
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get svc iperf3-server -n ioc-test-project-002-v1

# Verify the Network Policy
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get projectnetworkpolicy iperf3-server-ingress -n ioc-test-project-002-v1

# Verify the Client Job execution status (should have Succeeded = 1)
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get jobs iperf3-client -n ioc-test-project-002-v1
```

### 2. Network Performance and Throughput Verification
Extract the results from the client job's pod logs to view actual measured network throughput:
```bash
# Find the iperf3 client pod name
CLIENT_POD=$(kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get pods -l job-name=iperf3-client -n ioc-test-project-002-v1 -o jsonpath='{.items[0].metadata.name}')

# View the iperf3 performance output logs
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context logs $CLIENT_POD -n ioc-test-project-002-v1
```

A successful run should display standard iperf3 client transmission logs concluding with a summary of the network performance, similar to:
```text
[ ID] Interval           Transfer     Bitrate         Retr
[  5]   0.00-10.00  sec  11.5 GBytes  9.88 Gbits/sec    0             sender
[  5]   0.00-10.04  sec  11.5 GBytes  9.84 Gbits/sec                  receiver
```

---

## 4. Teardown

To remove all resources created for this test case:

### A. Teardown Tenant-Scoped Deployments
```bash
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile destroy
kubectl --context "$GLOBAL_API_CONTEXT" delete -f tenant-bootstrap.yaml
rm -f .kubeconfig-sa
```

### B. Teardown Operator-Scoped Deployments
```bash
# Teardown iperf3 workloads on the Admin/User Cluster
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=iperf3 destroy

# Teardown project and platform bootstrap
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=iperf3 destroy

# Delete the bootstrap service accounts and bindings
kubectl --context "$GLOBAL_API_CONTEXT" delete -f tenant-bootstrap.yaml
rm -f .kubeconfig-sa
```

---

## 5. Architecture & Security Design

### Pathway A: Standard GDC-Native Tenant-Scoped Architecture (Primary / Staging)

This represents the standard production-aligned architecture. The client-side Kubeconfig contains **2 contexts** mapped strictly to GDC's Global logical API. Workload security, namespace creation, and target cluster role assignments are governed 100% by GDC-native logical IAM policies, which GDC's background propagation services replicate to the physical layers.

```mermaid
graph TD
    subgraph "1. Logical Personas (Identity Layer)"
        SA_B["Platform Bootstrap SA<br/>(High Privilege)"]
        SA_R["Test Runner SA<br/>(Restricted)"]
    end

    subgraph "2. Kubeconfig Mapping (.kubeconfig-sa)"
        direction LR
        subgraph "Contexts"
            C1["bootstrap-context"]
            C2["runner-context"]
        end
        subgraph "Users (Tokens)"
            U1["global-token-A"]
            U2["global-token-B"]
        end
        C1 --> U1
        C2 --> U2
    end

    SA_B -->|Generates| U1
    SA_R -->|Generates| U2

    subgraph "3. GDC Platform Topology"
        subgraph "Global API Cluster (Logical Control)"
            G_CP[("Global API Control Plane")]
            G_Res["Logical: Projects, IAM Roles"]
            G_CP --- G_Res
        end

        subgraph "GDC Automated Propagation Layer"
            AIS["Ais Core Identity Propagation"]
        end

        subgraph "Admin/User Cluster (Physical Execution)"
            A_CP[("Admin Cluster Control Plane")]
            A_Res["Regional Workloads: iperf3 server Pods, client Jobs, NetPol"]
            A_CP --- A_Res
        end

        G_Res -->|Replicates Namespace & RBAC| AIS
        AIS -->|Secures Workspace| A_Res
    end

    U1 -->|Authenticates| G_CP
    U2 -->|Authenticates| G_CP

    classDef persona fill:#fff2cc,stroke:#d6b656,stroke-width:2px;
    classDef kube fill:#f1f3f4,stroke:#5f6368,stroke-width:2px;
    classDef global fill:#e8f0fe,stroke:#1a73e8,stroke-width:2px;
    classDef admin fill:#e6fffa,stroke:#00bfa5,stroke-width:2px;

    class SA_B,SA_R persona;
    class C1,C2,U1,U2 kube;
    class G_CP,G_Res global;
    class A_CP,A_Res admin;
```

---

### Pathway B: Operator-Scoped Bootstrapping & Diagnostics Architecture (Secondary / Fallback)

This represents the low-level infrastructure bootstrap and diagnostic architecture. It is used out-of-band to verify local container virtualization and network policy connectivity. The client-side Kubeconfig maps **4 hybrid contexts** to bypass GDC's global propagation layer, establishing direct, K8s-native `RoleBindings` on the target Admin Cluster control plane.

```mermaid
graph TD
    subgraph "1. Logical Personas (Identity Layer)"
        SA_B["Platform Bootstrap SA<br/>(High Privilege)"]
        SA_R["Test Runner SA<br/>(Restricted)"]
    end

    subgraph "2. Kubeconfig Mapping (.kubeconfig-sa)"
        direction LR
        subgraph "Contexts"
            C1["bootstrap-global"]
            C2["bootstrap-admin"]
            C3["runner-global"]
            C4["runner-admin"]
        end
        subgraph "Users (Tokens)"
            U1["global-token-A"]
            U2["admin-token-B"]
            U3["global-token-C"]
            U4["admin-token-D"]
        end
        C1 --> U1
        C2 --> U2
        C3 --> U3
        C4 --> U4
    end

    SA_B -->|Generates| U1
    SA_B -->|Generates| U2
    SA_R -->|Generates| U3
    SA_R -->|Generates| U4

    subgraph "3. GDC Multi-Cluster Physical Topology"
        subgraph "Tier 1: Global API Cluster"
            G_CP[("Global API Control Plane")]
            G_Res["Logical: Projects, IAM Roles"]
            G_CP --- G_Res
        end

        subgraph "Tier 2: Admin Cluster"
            A_CP[("Admin Cluster Control Plane")]
            A_Res["Infra: ProjectBindings, K8s RBAC"]
            A_CP --- A_Res
        end

        subgraph "Tier 3: User / Workload Cluster"
            U_CP[("User Cluster Control Plane")]
            U_Res["Workloads: iperf3 server Deployment, client Job, NetPol"]
            U_CP --- U_Res
        end
        
        A_CP -->|Manages| U_CP
    end

    U1 -->|Authenticates| G_CP
    U3 -->|Authenticates| G_CP
    U2 -->|Authenticates| A_CP
    U4 -->|Authenticates| U_CP
    
    classDef persona fill:#fff2cc,stroke:#d6b656,stroke-width:2px;
    classDef kube fill:#f1f3f4,stroke:#5f6368,stroke-width:2px;
    classDef global fill:#e8f0fe,stroke:#1a73e8,stroke-width:2px;
    classDef admin fill:#fce8e6,stroke:#d93025,stroke-width:2px;
    classDef user fill:#e6fffa,stroke:#00bfa5,stroke-width:2px;

    class SA_B,SA_R persona;
    class C1,C2,C3,C4,U1,U2,U3,U4 kube;
    class G_CP,G_Res global;
    class A_CP,A_Res admin;
    class U_CP,U_Res user;
```
