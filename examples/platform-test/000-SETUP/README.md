# GDC Staging Platform Setup: Architecture & Security Design Manual

This directory contains the shared core platform setup templates, cryptographic TLS trust managers, and Service Account credential generation scripts for GDC staging and test execution pipelines.

---

## 1. GDC Multi-Plane Control Plane Topology

GDC architecture divides operations across separate API planes to isolate physical resources from logical configuration metadata.

```mermaid
graph TD
    subgraph "Tier 1: Global API Cluster (Logical)"
        G_CP[("Global API Control Plane")]
        G_Res["Logical resources:<br/>- Projects<br/>- Global IAM Policies<br/>- NetworkPolicies"]
        G_CP --- G_Res
    end

    subgraph "GDC Automated Propagation Layer"
        AIS["Ais Core Identity Propagation"]
    end

    subgraph "Tier 2: Admin Cluster (Physical Control)"
        A_CP[("Admin Cluster Control Plane")]
        A_Res["Physical resources:<br/>- ProjectBindings<br/>- Namespace Allocation<br/>- K8s RBAC Permissions"]
        A_CP --- A_Res
    end

    subgraph "Tier 3: User / Workload Cluster (Physical Execution)"
        U_CP[("User Cluster Control Plane")]
        U_Res["Workloads:<br/>- VirtualMachines<br/>- Persistent Disks<br/>- Regional IP Networks"]
        U_CP --- U_Res
    end

    G_Res -->|Replicates Namespace & IAM| AIS
    AIS -->|Secures Workspace| U_CP
    A_CP -->|Manages Nodes| U_CP
```

* **Central logical Plane:** Decouples customer identity and tenancy configurations from physical bare-metal. Creating a logical `Project` triggers asynchronous GDC propagation engines to provision a corresponding regional namespace and sync permissions (~15-20 seconds propagation delay).
* **Regional Compute Plane:** Manages localized hypervisors, node storage pools, and physical network leaf routing.

---

## 2. Non-Interactive Authentication Models

Automated CI/CD pipelines (e.g. runners in GitHub Actions, GitLab CI, or Jenkins) cannot execute interactive, browser-based OIDC sign-ins. To bypass human front-door logins, GDC pipelines authenticate via **Headless Service Accounts** with isolated API client credentials.

Because GDC clusters operate as completely separate API endpoints without a shared trust domain for local Kubernetes-native tokens, a standard Global API token is natively rejected by Admin/User clusters. To solve this, this repository implements two distinct operational execution scopes:

### Model A: Customer-Scoped Pathway (Standard Production Mode)
Operates 100% inside standard customer tenant boundaries, requiring zero raw platform-operator administrative authority.
* **Mechanism:** Service Accounts are created strictly on the Global API Cluster. Permissions are assigned through GDC-native logical `IAMRoleBindings`. The GDC AIS background Identity Engine securely replicates logical access down to regional namespaces.
* **Client Configuration:** A client-side 2-context `.kubeconfig-sa` mapping:
  - `bootstrap-context` (delegated customer setup)
  - `runner-context` (case workload runner)

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
            A_Res["Regional Workloads: VMs, NetPol"]
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


### Model B: Operator-Scoped Pathway (Time-Zero Bootstrap & Fallback Mode)
Designed for infrastructure platform operators to verify compute hypervisors during time-zero bring-up or diagnostic runs when global identity services (AIS) are degraded or bypassed.
* **Mechanism:** Service Accounts are deployed on the Global API and applied **directly and out-of-band** onto the physical Admin Cluster control plane using native Kubernetes `ClusterRoleBindings`.
* **Client Configuration:** A client-side 4-context `.kubeconfig-sa` mapping both Logical and Physical cluster contexts for both SAs.

This represents the low-level infrastructure bootstrap and diagnostic architecture. It is used out-of-band to verify local compute hypervisors and physical node connectivity. The client-side Kubeconfig maps **4 hybrid contexts** to bypass GDC's global propagation layer, establishing direct, K8s-native `RoleBindings` on the target Admin Cluster control plane.

```mermaid
graph TD
    subgraph "1. Logical Personas (Identity Layer)"
        SA_B["Platform Bootstrap SA<br/>(High Privilege)"]
        SA_R["Test Runner SA<br/>(Restricted)"]
    end

    subgraph "2. Kubeconfig Mapping (.kubeconfig-sa)"
        direction LR
        subgraph "Contexts"
            C1["bootstrap-global-context"]
            C2["bootstrap-admin-context"]
            C3["runner-global-context"]
            C4["runner-admin-context"]
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
            U_Res["Workloads: VMs, NetPol"]
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

---

## 3. Service Account Scoping & Least Privilege

To restrict the pipeline's security blast radius and satisfy security audit reviews, Service Account identities are separated by duty and scoped to prevent permission creep:

| Service Account | Naming Scope | Permission Level | Responsibilities |
| :--- | :--- | :--- | :--- |
| **`test-setup-sa`** | **Global Shared** | High Privilege | Provisions GDC logical projects, assigns project-level role bindings, and handles regional project bindings. |
| **`test-runner-${TEST_CASE_NO}-sa`** | **Case-Scoped** | Namespace Restricted | Scoped strictly to a single test case (e.g. `test-runner-001-sa` for VM workloads). Deploys regional assets (VirtualMachines, Subnets) inside its own project namespace. |

---

## 4. Role Bindings: System vs. Workload Scopes

Role bindings are strictly divided into two groups with distinct lifetimes and scopes:

### A. System-Level Role Bindings (Permanent System Roles)
* **Declared In:** `000-SETUP/base-customer-identity.yaml` & `000-SETUP/base-operator-identity.yaml`
* **Target:** System service accounts (`test-setup-sa` and `test-runner-${TEST_CASE_NO}-sa`).
* **Purpose:** Authorizes the IaC runner components to execute pipeline sync commands.
* **Lifecycle:** Permanent; persists across all runs.

### B. Workload-Level Role Bindings (Ephemeral User Roles)
* **Declared In:** Local test case `tenants.yaml` (e.g., `001-AO-VM-CREATE/tenants.yaml`)
* **Target:** End users and consumer personas (such as developer OIDC accounts like `fop-iac@example.com`).
* **Purpose:** Grants permissions to consume regional resources inside their dedicated projects.
* **Lifecycle:** Ephemeral; instantly deleted when the logical GDC `Project` is destroyed.
