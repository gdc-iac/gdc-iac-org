# 008-PA-DB-CREATE-REFACTORED

This test case demonstrates the creation of a Database Cluster in GDC using a refactored, persona-based approach.

## Overview

- **Stage 1 (PA)**: The Platform Admin (using `ioc-test-pa`) performs two critical tasks:
    1.  **Infrastructure Setup**: Provisions the `BackupRepository` and required S3 secret (mandatory for GDC databases).
    2.  **Project Setup**: Creates the project, grants the `project-db-admin` role to the AO, and binds the project to a user cluster.
- **Stage 2 (AO)**: The Application Operator (using `ioc-test-ao`) provisions the Postgres Database Cluster within the pre-created project.

## Project-Namespace Isolation

In GDC, a **Project** is a logical container. When a Project is bound to a cluster, it automatically provisions a **Kubernetes Namespace** of the same name.
- **Isolation**: By using a unique `PROJECT_NAME` (e.g., `pt-008-db-create`), all resources for this test (DB Cluster, Secrets, Disks) are isolated within that specific namespace.
- **Cleanup**: Deleting the Project resource will automatically remove the corresponding namespace and all resources within it.

## Prerequisites

1.  **Accounts**: `ioc-test-pa@test.local` and `ioc-test-ao@test.local` must be created in ADFS.
2.  **Permissions**:
    - `ioc-test-pa` must have Organization IAM Admin and Cluster Admin roles.
3.  **Environment Variables**:
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

1.  **CLI**: Verify the Database Cluster:
    ```bash
    kubectl --context ${ADMIN_CLUSTER_CONTEXT} get dbclusters.postgresql.dbadmin.gdc.goog -n ${PROJECT_NAME}
    ```

## Stage 4: Teardown

1.  **AO**: Clear up database resources:
    ```bash
    cd 02-AO-RESOURCES
    helmfile destroy
    ```
2.  **PA**: (Optional) Clear up the project, IAM bindings, and backup infrastructure:
    ```bash
    cd ../01-PA-SETUP
    helmfile destroy
    ```
