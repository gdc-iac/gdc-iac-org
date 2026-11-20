# 004-CONTAINER-APACHE-POSTGRES: Container Web & Database Throughput Benchmark

### TL;DR: GDC IaC Pipeline Automation

This directory contains a self-contained IaC (Infrastructure as Code) setup to satisfy the requirements of the **004-CONTAINER-APACHE-POSTGRES** test case, which automates secure container-to-container web-database query execution and benchmarks throughput (requests per minute) across GDC's logical and physical API planes using a **progressive, bottom-up staging stance**:

1. **Adhoc Sandbox ([setup-adhoc-env.sh](setup-adhoc-env.sh)):** Validates OIDC/AIS identity synchronization loops interactively.
2. **Operator Scope ([setup-operator-sa.sh](setup-operator-sa.sh)):** Performs out-of-band K8s-native bootstrapping directly on physical Admin/User Clusters for time-zero platform start-up.
3. **Tenant Scope ([setup-tenant-sa.sh](setup-tenant-sa.sh)):** Provisions resources strictly within GDC-native customer tenant boundaries.

The orchestration is driven by `helmfile.yaml.gotmpl`, which dynamically routes cross-plane tokens and uses a namespaced `auth can-i` presync hook to securely handle asynchronous namespace and IAM replication delays without requiring cluster-wide administrative privileges.

---

## 1. Overview & Context

### Test Case Overview
- **ID:** 004-CONTAINER-APACHE-POSTGRES
- **Description:** Verify that containerized web server workloads can securely query PostgreSQL databases and run a load benchmark to measure performance (requests per minute) inside the GDC project space.
- **Goal:** Deploy a containerized database (`postgres-db`), a Python-based query server acting as the web server (`web-server`), and a benchmarking worker (`benchmark-client`) that executes `ab` (ApacheBench) load queries inside the `ioc-test-project-004` namespace.

### Mapping to 004-CONTAINER-APACHE-POSTGRES Test Spec
- **PR-01 (RBAC):** Satisfied via `tenants.yaml` and `gdc-iam-role-bindings` chart.
- **PR-02 (Workloads):** Uses standard `postgres:15-alpine` and `python:3.11-alpine` images inside the tenant project namespace to run database and query web server pods.
- **Step 2-5 (Creation):** Automated via custom `gdc-apache-postgres` Helm chart deploying Deployments, ClusterIP Services, ConfigMaps, a `ProjectNetworkPolicy` to allow web/db traffic, and a benchmarking Job.
- **Step 6 (Verification):** Automated check for Job completion and extracting requests per second / requests per minute throughput results.

### Assets
- **`tenants.yaml`**: The declarative desired-state manifest defining the tenant topology, target projects, regional cluster bindings, dynamic user IAM permissions, and benchmark workload parameters (e.g. requests count, concurrency limits).
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
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=apache-postgres sync
   ```

3. **Run Phase 2 - Provision Container Workloads (Restricted Runner SA Context):**
   Provision web deployments, databases, and benchmark jobs directly in the regional project workspace:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=apache-postgres sync
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
     kubectl --kubeconfig=./.kubeconfig-sa --context=runner-context auth can-i create deployments -n ioc-test-project-004-v1
     ```
     *Do not proceed to step 2 until this command returns `yes`.*

2. **Deploy the Project and Web+DB Workloads:**
   Run the `helmfile sync` using the generated `.kubeconfig-sa` file to provision both the GDC logical project environment and the regional workloads:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile sync
   ```

---

## 3. Verification & Throughput Analysis

### 1. Resource Creation Verification
Confirm that all resources have been created in the project namespace:
```bash
# Verify the Postgres Database deployment
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get deployments postgres-db -n ioc-test-project-004-v1

# Verify the Web Server deployment
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get deployments web-server -n ioc-test-project-004-v1

# Verify the Project Network Policy
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get projectnetworkpolicy allow-web-and-db-traffic -n ioc-test-project-004-v1

# Verify the Benchmark Job status
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get jobs benchmark-client -n ioc-test-project-004-v1
```

### 2. Extract Requests Per Minute Throughput Metrics
Query the benchmark-client container logs to view the ApacheBench benchmark report:
```bash
# Find the benchmark pod name
BENCH_POD=$(kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get pods -l job-name=benchmark-client -n ioc-test-project-004-v1 -o jsonpath='{.items[0].metadata.name}')

# View benchmark throughput logs
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context logs $BENCH_POD -n ioc-test-project-004-v1
```

A successful benchmark will output detailed ApacheBench stats. Focus on `Requests per second` to calculate **Requests Per Minute**:
```text
Server Software:        BaseHTTP/0.6
Server Hostname:        web-server
Server Port:            8080

Document Path:          /
Document Length:        39 bytes

Concurrency Level:      20
Time taken for tests:   1.215 seconds
Complete requests:      2000
Failed requests:        0
Total transferred:      338000 bytes
HTML transferred:       78000 bytes
Requests per second:    1646.09 [#/sec] (mean)
Time per request:       12.150 [ms] (mean)
Time per request:       0.608 [ms] (mean, across all concurrent requests)
Transfer rate:          271.65 [Kbytes/sec] received

Connection Times (ms)
              min  mean[+/-sd] median   max
Connect:        0    1   1.2      0      12
Processing:     2   11   4.1     11      35
Waiting:        1   10   4.0     10      34
Total:          3   12   4.0     12      36
```

**Calculating Requests Per Minute (RPM):**
$$\text{RPM} = \text{Requests per second} \times 60$$
$$\text{RPM} = 1646.09 \times 60 = 98,765.4 \text{ requests per minute}$$

This confirms rapid container-to-container communication with live Postgres query reconciliation under strict GDC limits.

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
# Teardown Web + DB workloads on the Admin Cluster
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=apache-postgres destroy

# Teardown project and platform bootstrap
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=apache-postgres destroy

# Delete the bootstrap service accounts and bindings
kubectl --context "$GLOBAL_API_CONTEXT" delete -f tenant-bootstrap.yaml
rm -f .kubeconfig-sa
```

---

## 5. Architecture & Security Design

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
            
            subgraph "Test Project Namespace"
                NP["ProjectNetworkPolicy<br/>(allow-web-and-db-traffic)"]
                DB["Postgres Database Pod<br/>(port 5432)"]
                WEB["Python Web Pod<br/>(port 8080)"]
                CLI["Benchmark Client Job<br/>(ApacheBench)"]
                
                CLI -->|1. Hit Web HTTP server| WEB
                WEB -->|2. Execute SELECT 1 query| DB
                NP -->|Enforces Ingress| WEB
                NP -->|Enforces Ingress| DB
            end
        end

        G_Res -->|Replicates Namespace & RBAC| AIS
        AIS -->|Secures Workspace| Test Project Namespace
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
