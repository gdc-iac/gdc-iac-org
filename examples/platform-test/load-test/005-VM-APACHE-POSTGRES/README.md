# 005-VM-APACHE-POSTGRES: Virtual Machine Web & Database Throughput Benchmark

### TL;DR: GDC IaC Pipeline Automation

This directory contains a self-contained IaC (Infrastructure as Code) setup to satisfy the requirements of the **005-VM-APACHE-POSTGRES** test case, which automates secure virtual-machine-to-virtual-machine web-database query execution and benchmarks throughput (requests per minute) across GDC's logical and physical API planes using a **progressive, bottom-up staging stance**:

1. **Adhoc Sandbox ([setup-adhoc-env.sh](setup-adhoc-env.sh)):** Validates OIDC/AIS identity synchronization loops interactively.
2. **Operator Scope ([setup-operator-sa.sh](setup-operator-sa.sh)):** Performs out-of-band K8s-native bootstrapping directly on physical Admin/User Clusters for time-zero platform start-up.
3. **Tenant Scope ([setup-tenant-sa.sh](setup-tenant-sa.sh)):** Provisions resources strictly within GDC-native customer tenant boundaries.

The orchestration is driven by `helmfile.yaml.gotmpl`, which dynamically routes cross-plane tokens and uses a namespaced `auth can-i` presync hook to securely handle asynchronous namespace and IAM replication delays without requiring cluster-wide administrative privileges.

---

## 1. Overview & Context

### Test Case Overview
- **ID:** 005-VM-APACHE-POSTGRES
- **Description:** Verify that virtual machine web servers can securely establish database connections to other virtual machines and benchmark transactional query throughput (requests per minute) inside the GDC project space.
- **Goal:** Deploy two virtual machines (`postgres-vm` and `apache-vm`) and a regional GDC `ProjectNetworkPolicy` to allow web and database port traffic, execute a query benchmarking test, and record requests per minute results.

### Mapping to 005-VM-APACHE-POSTGRES Test Spec
- **PR-01 (RBAC):** Satisfied via `tenants.yaml` and `gdc-iam-role-bindings` chart.
- **PR-02 (VM Images):** Uses `ubuntu-24.04-v20260224-gdch` from the `vm-system` namespace.
- **Step 2-5 (Creation):** Automated via GDC's production-native `gdc-vm` Helm chart to spin up two virtual machines, and `gdc-project-network-policies` to open port `5432` and `8080`.
- **Step 6 (Verification):** Automated check for VM `Running` states, SSH connectivity, installing database/server software inside the virtual machines, and triggering ApacheBench load runs.

### Assets
- **`tenants.yaml`**: The declarative desired-state manifest defining the tenant topology, target projects, regional cluster bindings, dynamic user IAM permissions, and virtual machines/network policy parameters.
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
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=vm sync
   ```

3. **Run Phase 2 - Provision VM Workloads (Restricted Runner SA Context):**
   Provision virtual machines directly in the regional project workspace:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=vm sync
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
     kubectl --kubeconfig=./.kubeconfig-sa --context=runner-context auth can-i get virtualmachines -n ioc-test-project-005-v1
     ```
     *Do not proceed to step 2 until this command returns `yes`.*

2. **Deploy the Project and VM Workloads:**
   Run the `helmfile sync` using the generated `.kubeconfig-sa` file to provision both the GDC logical project environment and the regional VM workloads:
   ```bash
   KUBECONFIG=./.kubeconfig-sa VERSION=-v1 GLOBAL_API_CONTEXT=bootstrap-context ADMIN_CLUSTER_CONTEXT=runner-context helmfile sync
   ```

---

## 3. Verification & Throughput Analysis

### 1. Resource Creation Verification
Confirm that all VM resources have been created in the project namespace:
```bash
# Verify the Database VM status
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get virtualmachine postgres-vm -n ioc-test-project-005-v1

# Verify the Web Server VM status
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get virtualmachine apache-vm -n ioc-test-project-005-v1

# Verify the general iperf3 Project Network Policy
kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get projectnetworkpolicy allow-web-db-traffic -n ioc-test-project-005-v1
```

### 2. Configure workloads and Run Benchmark
Because virtual machines boot with a clean Ubuntu base image, you can SSH in and configure them using standard scripts to measure transaction rates:

1. **Retrieve internal Virtual IPs:**
   ```bash
   # postgres-vm IP
   DB_IP=$(kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get virtualmachine postgres-vm -n ioc-test-project-005-v1 -o jsonpath='{.status.network.interfaces[0].ipAddresses[0]}' | cut -d/ -f1)
   
   # apache-vm IP
   WEB_IP=$(kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get virtualmachine apache-vm -n ioc-test-project-005-v1 -o jsonpath='{.status.network.interfaces[0].ipAddresses[0]}' | cut -d/ -f1)
   ```

2. **Retrieve SSH Ingress IPs (if external access is configured):**
   ```bash
   # postgres-vm SSH Ingress IP
   DB_EXT=$(kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get virtualmachineexternalaccess postgres-vm -n ioc-test-project-005-v1 -o jsonpath='{.status.ingressIP}')
   
   # apache-vm SSH Ingress IP
   WEB_EXT=$(kubectl --kubeconfig=./.kubeconfig-sa --context=runner-admin-context get virtualmachineexternalaccess apache-vm -n ioc-test-project-005-v1 -o jsonpath='{.status.ingressIP}')
   ```

3. **Install & Initialize PostgreSQL on `postgres-vm`:**
   SSH into the database VM and install Postgres:
   ```bash
   ssh -i [YOUR_SSH_KEY] user@$DB_EXT "sudo apt-get update && sudo apt-get install -y postgresql && sudo systemctl start postgresql"
   ```
   Configure PostgreSQL to allow queries from the web server:
   ```bash
   ssh -i [YOUR_SSH_KEY] user@$DB_EXT "sudo -u postgres psql -c \"CREATE DATABASE testdb;\" && sudo -u postgres psql -c \"CREATE USER postgres WITH PASSWORD 'dbpassword123';\""
   ssh -i [YOUR_SSH_KEY] user@$DB_EXT "echo \"listen_addresses = '*'\" | sudo tee -a /etc/postgresql/*/main/postgresql.conf && echo \"host all all 0.0.0.0/0 md5\" | sudo tee -a /etc/postgresql/*/main/pg_hba.conf && sudo systemctl restart postgresql"
   ```

4. **Install and Run Web Query Server on `apache-vm`:**
   SSH into the Web VM, install python drivers, and launch the web server:
   ```bash
   ssh -i [YOUR_SSH_KEY] user@$WEB_EXT "sudo apt-get update && sudo apt-get install -y python3-pip && pip3 install pg8000 --break-system-packages"
   ```
   Deploy the live database query web server on the VM:
   ```bash
   ssh -i [YOUR_SSH_KEY] user@$WEB_EXT "cat << 'EOF' > server.py
   import http.server
   import pg8000.dbapi

   class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
       def do_GET(self):
           try:
               conn = pg8000.dbapi.connect(
                   database='testdb',
                   user='postgres',
                   password='dbpassword123',
                   host='$DB_IP',
                   port=5432
               )
               cursor = conn.cursor()
               cursor.execute('SELECT 1;')
               result = cursor.fetchone()
               cursor.close()
               conn.close()
               
               self.send_response(200)
               self.send_header('Content-type', 'text/html')
               self.end_headers()
               self.wfile.write(f'DB query successful! Result: {result[0]}'.encode('utf-8'))
           except Exception as e:
               self.send_response(500)
               self.send_header('Content-type', 'text/html')
               self.end_headers()
               self.wfile.write(f'DB query failed: {e}'.encode('utf-8'))

   print('Starting HTTP Server on port 8080...')
   http.server.HTTPServer(('0.0.0.0', 8080), SimpleHTTPRequestHandler).serve_forever()
   EOF"
   
   # Start the query server in the background
   ssh -i [YOUR_SSH_KEY] user@$WEB_EXT "nohup python3 server.py > server.log 2>&1 &"
   ```

5. **Execute Benchmark and Calculate Requests Per Minute:**
   On a client node (or directly on `apache-vm`), install ApacheBench and run a benchmark hitting the query web server:
   ```bash
   ssh -i [YOUR_SSH_KEY] user@$WEB_EXT "sudo apt-get install -y apache2-utils && ab -n 2000 -c 20 http://localhost:8080/"
   ```

   **Example output:**
   ```text
   Concurrency Level:      20
   Time taken for tests:   1.956 seconds
   Complete requests:      2000
   Failed requests:        0
   Requests per second:    1022.49 [#/sec] (mean)
   ```

   **Requests Per Minute (RPM) Calculation:**
   $$\text{RPM} = \text{Requests per second} \times 60$$
   $$\text{RPM} = 1022.49 \times 60 = 61,349.4 \text{ requests per minute}$$

This confirms fast, high-performance VM-to-VM network communications and virtualization layers querying database backends inside GDC.

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
# Teardown VM workloads on the Admin/User Cluster
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=runner-admin-context helmfile --selector tier=vm destroy

# Teardown project, platform bootstrap, and network policies
KUBECONFIG=./.kubeconfig-sa GLOBAL_API_CONTEXT=bootstrap-global-context ADMIN_CLUSTER_CONTEXT=bootstrap-admin-context helmfile --selector tier!=vm destroy

# Delete the bootstrap service accounts and bindings
kubectl --context "$GLOBAL_API_CONTEXT" delete -f tenant-bootstrap.yaml
rm -f .kubeconfig-sa
```
