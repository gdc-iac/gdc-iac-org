# 3-Tier Application Example (Helmfile)

This example demonstrates how to deploy a secure, 3-tier application architecture using Helmfile in Google Distributed Cloud air-gapped (GDCag).

It follows a **data-driven approach** separating the data (`tenants.yaml`) from the logic (`helmfile.yaml.gotmpl`).

---

## 🏗 Architecture

The example creates a typical 3-tier application structure with strict network isolation:

1.  **Projects**:
    *   `frontend-prj`: Hosts user-facing workloads.
    *   `applogic-prj`: Hosts business logic.
    *   `data-prj`: Hosts databases and sensitive data.
    *   `golden-images-prj`: Hosts the Harbor registry for secure images.

2.  **Network Isolation**:
    *   An **Organization Network Policy** blocks all external egress by default.
    *   **Project Network Policies** ensure that:
        *   `frontend-prj` can communicate with `applogic-prj`.
        *   `applogic-prj` can communicate with `data-prj`.
        *   `frontend-prj` **cannot** communicate directly with `data-prj`.

3.  **Identity & Access Control**:
    *   Dedicated Service Accounts are created for application tiers (`frontend-sa`, `applogic-sa`, `data-sa`) and for Harbor image building (`harbor-builder-sa`).
    *   Predefined `project-editor` role bindings are created for project-specific groups (e.g., `frontend-viewers@example.com`) to manage access.

---

## 🚀 Bootstrapping `iac-root`

To manage the state of these Helm releases, Helmfile requires a dedicated namespace to store its secrets. This example uses `iac-root` as the state namespace.

Because of the "chicken-and-egg" problem, this namespace must be created manually before running Helmfile.

### Prerequisites

You need to be logged in as a platform administrator or a user with rights to create projects.

### Step 1: Create the `iac-root` Project

Run the following command to create the project that will host the IaC state:

```bash
export IAC_PROJECT="iac-root"
gdcloud projects create $IAC_PROJECT
```

### Step 2: Grant Permissions to the IaC User

The user running Helmfile (e.g., `fop-iac@example.com`) requires specific permissions on the `iac-root` project to manage Helm state files, as well as organization-level permissions to create projects and manage resources.

Run the following commands to grant the required roles:

```bash
export ORG_NAME="org-1"
export IAC_PROJECT="iac-root"
export IAC_USER="fop-iac@example.com"

# 1. Grant IAC_USER required IAM permissions on `IAC_PROJECT` to manage Helm state:
gdcloud projects add-iam-policy-binding $IAC_PROJECT \
  --member=user:$IAC_USER \
  --role=secret-admin

# 2. Grant IAC_USER required Org roles to create and manage projects:
for role in \
  organization-iam-admin \
  project-creator \
  project-editor \
  user-cluster-admin \
  gdchrestrictedservice-policy-admin \
  org-network-policy-admin \
; do \
   gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
   --member="user:$IAC_USER" \
   --role="$role";\
done
```

---

## 🛠 How to Deploy

1.  Ensure you are in the example directory:
    ```bash
    cd examples/helmfile/3-tier-app
    ```

2.  **Run Prechecks** (Optional but recommended):
    Verify the configuration and view the execution order before deploying:
    ```bash
    helmfile lint
    helmfile list
    helmfile show-dag
    helmfile template
    ```

3.  Deploy the configuration. For the first run, it is recommended to use `sync` because `apply` attempts to calculate diffs against namespaces that do not exist yet:
    ```bash
    helmfile sync
    ```

4.  For subsequent updates once projects are created, you can use:
    ```bash
    helmfile apply
    ```
