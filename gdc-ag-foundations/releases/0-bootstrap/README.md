# Stage 0: Bootstrap (`0-bootstrap`)

This stage initializes the foundational landing zone operators, systems, and resources required to enable subsequent automated tenant deployment pipelines.

---

## Operational Architecture

* **Target Control Plane Scope**: Global API Server (`gdc_context_global`)
* **Target Namespace**: `iac-root` (or parameterized via `gdc_release_namespace`)
* **Pre-requisites**: Initial GDC cluster bootstrap completed with administrative access.

> [!IMPORTANT]
> This stage **MUST** be run by the **Platform Admin** (or a user with full cluster-wide administrative access), as it sets up root namespaces, base CustomResources, and landing zone operators that require highest-level privileges. Subsequent project and resource stages are designed to be executed by standard or restricted tenant operators.

---

## Deployments & Sub-Helmfiles

The bootstrap stage consists of the following sub-helmfiles:

* **`customroles.yaml.gotmpl`**: Configures environment-specific custom IAM roles at the organization and project scope.
  * **Chart**: `gdc-iam-roles` (local path: `charts/gdc-iam-roles`)
* **`iam-rolebindings.yaml.gotmpl`**: Maps global and project-level GDC Hosted Predefined and Custom IAM roles to identities.
  * **Chart**: `gdc-iam-role-bindings` (local path: `charts/gdc-iam-role-bindings`)
* **`rbacrolebindings.yaml.gotmpl`**: Configures standard Kubernetes RoleBindings and ClusterRoleBindings for root operations.
  * **Chart**: `gdc-rbac-role-bindings` (local path: `charts/gdc-rbac-role-bindings`)

---

## Execution Commands

Run the following command from the repository root directory to validate and deploy the bootstrap stage:

```bash
# Template validation
helmfile -e dev -l stage=0-bootstrap template

# Apply/Deploy stage
helmfile -e dev -l stage=0-bootstrap apply
```
