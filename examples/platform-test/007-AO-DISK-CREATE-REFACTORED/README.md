# 007-AO-DISK-CREATE-REFACTORED

This test case demonstrates the creation of independent Virtual Machine Disks in GDC using a refactored, persona-based approach.

## Overview

- **Stage 1 (PA)**: The Platform Admin (using `ioc-test-pa`) creates the project, grants the `project-vm-admin` role to the AO, and binds the project to a user cluster.
- **Stage 2 (AO)**: The Application Operator (using `ioc-test-ao`) provisions the independent Virtual Machine Disks within the pre-created project.

## Project-Namespace Isolation

In GDC, a **Project** is a logical container. When a Project is bound to a cluster, it automatically provisions a **Kubernetes Namespace** of the same name.
- **Isolation**: By using a unique `PROJECT_NAME` (e.g., `pt-007-disk-create`), all resources for this test are isolated within that specific namespace.
- **Cleanup**: Deleting the Project resource will automatically remove the corresponding namespace and all resources within it.

## Prerequisites

1.  **Accounts**: `ioc-test-pa@test.local` and `ioc-test-ao@test.local` must be created in ADFS.
2.  **Environment Variables**:
    ```bash
    export GLOBAL_API_CONTEXT="your-global-api-context"
    export ADMIN_CLUSTER_CONTEXT="your-admin-cluster-context"
    export USER_CLUSTER_NAME="your-user-cluster-name"
    export PROJECT_NAME=$(basename $(pwd))
    ```

## Stage 1: Platform Admin Setup (PA)

1.  **Login** as `ioc-test-pa`.
2.  **Navigate** to `01-PA-SETUP` and **Deploy**:
    ```bash
    helmfile sync
    ```

## Stage 2: Application Operator Resources (AO)

1.  **Login** as `ioc-test-ao`.
2.  **Navigate** to `02-AO-RESOURCES` and **Deploy**:
    ```bash
    helmfile sync
    ```

## Stage 3: Verification (Manual)

1.  **CLI**: Verify the Virtual Machine Disks:
    ```bash
    kubectl --context ${ADMIN_CLUSTER_CONTEXT} get virtualmachinedisks.virtualmachine.gdc.goog -n ${PROJECT_NAME}
    ```

## Stage 4: Teardown

1.  **AO**: Clear up workload resources:
    ```bash
    cd 02-AO-RESOURCES
    helmfile destroy
    ```
2.  **PA**: (Optional) Clear up the project and IAM bindings:
    ```bash
    cd ../01-PA-SETUP
    helmfile destroy
    ```
