# 001-AO-VM-CREATE: Virtual Machine Provisioning (IaC Setup)

This directory contains a self-contained IaC (Infrastructure as Code) setup to satisfy the requirements of the **001-AO-VM-CREATE** test case.

## Test Case Overview
- **ID:** 001-AO-VM-CREATE
- **Description:** Verify that authorized users can provision virtual machines.
- **Goal:** Automate the provisioning of the `ioc-test-vm` in the `ioc-test-project-001` namespace, including networking and IAM.

## Assets
- `tenants.yaml`: Defines the desired state including the project, IAM roles, and VM configuration.
- `helmfile.yaml.gotmpl`: Orchestration engine to deploy the resources using Helm.

## RBAC & Authorization (PR-01)
To satisfy the prerequisites of **PR-01**, the following authorization structure is required and implemented:

### 1. Bootstrap Permissions (Pre-requisite)
The user executing the `helmfile sync` command must have the following roles at the **Organization** level:
- `project-creator`: Permission to create the `ioc-test-project-001`.
- `organization-iam-admin`: Permission to assign the project-level roles defined in `tenants.yaml`.

### 2. Automated Project-Level Roles
The `tenants.yaml` file automatically provisions these roles to the target user (`fop-iac@example.com`) within the `ioc-test-project-001` namespace:
- **`project-vm-admin`**: Grants full access to manage Virtual Machines and Disks.
- **`project-networkpolicy-admin`**: Grants permission to manage `ProjectNetworkPolicy` resources, which is essential for enabling SSH ingress.
- **`project-viewer`**: Grants read access to verify the state of all provisioned resources.

## Deployment Steps

1. **Initialize and Sync:**
   Run the following command to provision the project, IAM roles, and the VM:
   ```bash
   helmfile sync
   ```

2. **Verify Resource Creation:**
   Confirm that all resources have been created in the `ioc-test-project-001` namespace:
   ```bash
   # Verify the VM status
   kubectl get virtualmachine ioc-test-vm -n ioc-test-project-001

   # Verify the Boot Disk
   kubectl get virtualmachinedisk ioc-test-vm-boot-disk -n ioc-test-project-001

   # Verify the Network Policy (Inbound SSH)
   kubectl get projectnetworkpolicy ioc-test-vm-ingress -n ioc-test-project-001
   ```

## Traffic Verification (SSH Ingress)
The configuration includes `uiAccessEnabled: true` and `createProjectNetworkPolicy: true`. This satisfies the requirements for secure console access:

1. **Verify Ingress Policy:**
   Check that the `ProjectNetworkPolicy` allows traffic on port 22:
   ```bash
   kubectl describe projectnetworkpolicy ioc-test-vm-ingress -n ioc-test-project-001
   ```
2. **Console Verification:**
   In the GDC Console, navigate to **Virtual Machines > Instances**, select `ioc-test-vm`, and click the **SSH** button. The presence of the `ProjectNetworkPolicy` allows this traffic to pass successfully.

## Traffic & Metrics Verification
To verify that the VM is not only running but also accessible and generating metrics:

1. **Verify Network Connectivity (Traffic):**
   The IaC creates a `VirtualMachineExternalAccess` resource with an Ingress IP. You can verify that the SSH port is open and reachable:
   ```bash
   # Get the Ingress IP
   INGRESS_IP=$(kubectl get virtualmachineexternalaccess ioc-test-vm -n ioc-test-project-001 -o jsonpath='{.status.ingressIP}')
   
   # Test connectivity to the SSH port (22)
   nc -zv -w 5 $INGRESS_IP 22
   ```
   *Expected Result: `Connection to <IP> 22 port [tcp/ssh] succeeded!`*

2. **Retrieve Metrics (Resource Usage):**
   If the Metrics API is enabled in your cluster, you can view the real-time resource usage:
   ```bash
   # Note: This requires the metrics-server to be operational in the zone
   kubectl top pod -n ioc-test-project-001 --containers
   ```
   If `kubectl top` is unavailable (e.g., "Metrics API not available"), performance data can be viewed in the **GDC Console** under **Virtual Machines > Instances > ioc-test-vm > Monitoring**.

## Visual Verification
For manual verification and audit evidence (screenshots):

1. **Direct Console Link:**
   Navigate to the Virtual Machines instances page:
   [https://console.org-1.zone1.google.gdch.test/#/virtual-machines?project=ioc-test-project-001&zone=zone1](https://console.org-1.zone1.google.gdch.test/#/virtual-machines?project=ioc-test-project-001&zone=zone1)

2. **Screenshot Capture:**
   To capture the current state of the VM in the console for the test report:
   ```bash
   google-chrome --headless --disable-gpu --ignore-certificate-errors --screenshot=vm_verification.png --window-size=1280,1024 "https://console.org-1.zone1.google.gdch.test/#/virtual-machines?project=ioc-test-project-001&zone=zone1"
   ```
   *Note: If the session is not authenticated, the screenshot will capture the login screen. Manual steps are currently required to select the OIDC provider and the user from the dropdown menu. Scripting of this authentication flow is deferred for future automation.*

## Teardown
To remove all resources created for this test case:
```bash
helmfile destroy
```

## Mapping to 001-AO-VM-CREATE Test Spec
- **PR-01 (RBAC):** satisfy via `tenants.yaml` and `gdc-iam-role-bindings` chart.
- **PR-02 (Images):** Uses `ubuntu-24.04-v20260224-gdch` from the `vm-system` namespace.
- **Step 2-5 (Creation):** Automated via `gdc-vm` Helm chart with specific hardware requirements (`n3-standard-2-gdc`, `20Gi` disk).
- **Step 6 (Verification):** Automated check for `Running` state.
