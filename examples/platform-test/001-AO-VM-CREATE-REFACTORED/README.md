# 001-AO-VM-CREATE-REFACTORED

This test case demonstrates the creation of a Virtual Machine in GDC using a refactored, persona-based approach. It separates the responsibilities of the **Platform Admin (PA)** and the **Application Operator (AO)** to reduce the blast radius and clarify the resource lifecycle.

## Overview

- **Stage 1 (PA)**: The Platform Admin (using `ioc-test-pa`) creates the project, grants IAM roles to the AO, and binds the project to a user cluster.
- **Stage 2 (AO)**: The Application Operator (using `ioc-test-ao`) provisions the Virtual Machine within the pre-created project.

## Project-Namespace Isolation

In GDC, a **Project** is a logical container. When a Project is bound to a cluster, it automatically provisions a **Kubernetes Namespace** of the same name.
- **Isolation**: By using a unique `PROJECT_NAME` (e.g., `pt-001-vm-create`), all resources for this test (VMs, disks, etc.) are isolated within that specific namespace.
- **Cleanup**: Deleting the Project resource will automatically remove the corresponding namespace and all resources within it, ensuring a clean teardown.

## Prerequisites

1.  **Accounts**: `ioc-test-pa@example.com` and `ioc-test-ao@example.com` must be created in ADFS.
2.  **Permissions**:
    - `ioc-test-pa` must have Organization IAM Admin roles to create projects and assign bindings.
3.  **Environment Variables**:
    ```bash
    # Set the cluster contexts
    export GLOBAL_API_CONTEXT="your-global-api-context"
    export ADMIN_CLUSTER_CONTEXT="your-admin-cluster-context"

    # Set the target user cluster name
    # You can find this by running: kubectl --context ${ADMIN_CLUSTER_CONTEXT} get clusters.cluster.gdc.goog
    export USER_CLUSTER_NAME="your-user-cluster-name"

    # Set the project name (derived from this folder by default)
    export PROJECT_NAME=$(basename $(pwd))
    ```

## Stage 1: Platform Admin Setup (PA)

1.  **Login** as `ioc-test-pa`.
2.  **Navigate** to the setup directory:
    ```bash
    cd 01-PA-SETUP
    ```
3.  **Review** `tenants.yaml` to ensure the AO user and roles are correct.
4.  **Deploy**:
    ```bash
    helmfile sync
    ```

## Stage 2: Application Operator Resources (AO)

1.  **Login** as `ioc-test-ao`.
2.  **Navigate** to the resources directory:
    ```bash
    cd ../02-AO-RESOURCES
    ```
3.  **Review** `tenants.yaml` to customize the VM specification.
4.  **Deploy**:
    ```bash
    helmfile sync
    ```

## Stage 3: Verification (Manual)

1.  **CLI**: Verify the VM status:
    ```bash
    kubectl --context ${ADMIN_CLUSTER_CONTEXT} get vm -n ${PROJECT_NAME}
    ```
2.  **UI**: Navigate to the GDC Console and verify the VM is listed under the project.

## Stage 4: Teardown

1.  **AO**: Clear up VM resources:
    ```bash
    cd 02-AO-RESOURCES
    helmfile destroy
    ```
2.  **PA**: (Optional) Clear up the project and IAM bindings:
    ```bash
    cd ../01-PA-SETUP
    helmfile destroy
    ```
