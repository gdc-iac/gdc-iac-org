# Stage 0: Organization Setup (`0-org-setup`)

This stage establishes the overall platform operations boundary, global billing integrations, administrative custom IAM roles, and central organizational policies.

---

## Operational Architecture

* **Target Control Plane Scope**: Global API Server (`gdc_context_global`)
* **Target Namespace**: `platform` (scoped organizations/roles) or `gpc-system` (organizational policies)
* **Pre-requisites**: Stage `0-bootstrap` must be fully executed and synced.

---

## Deployments & Sub-Helmfiles

1. **`org-policies.yaml.gotmpl`**: Manages Gatekeeper constraints and organization-wide security boundaries.
   * **Chart**: `gdc-org-policies`
2. **`org-network-plocies.yaml.gotmpl`**: Manages central network topologies and global traffic blocks.
   * **Chart**: `gdc-org-network-policies`
3. **`billing.yaml.gotmpl`**: Provisions global billing accounts and pricing structures.
   * **Chart**: `gdc-billing`
4. **`iam-roles.yaml.gotmpl`**: Provisions organizational and project-scoped `CustomRole` resources.
   * **Chart**: `gdc-iam-roles`
5. **`rbac-role-bindings.yaml.gotmpl`**: Establishes standard Kubernetes `RoleBinding` mappings for administrative operators.
   * **Chart**: `gdc-rbac-role-bindings`

---

## Execution Commands

Run the following commands from the repository root directory to template or apply this stage:

```bash
# Template validation
helmfile -e dev -l stage=0-org-setup template

# Apply/Deploy stage
helmfile -e dev -l stage=0-org-setup apply
```

---

## Configuration & Defaulting

To streamline tenant configurations, this stage supports the **Tenant Admin Defaulting Pattern**. You can completely omit `subject_name` and `subject_kind` in `rbacrolebindings` and `iamrolebindings` under the tenant configurations, and they will automatically inherit the tenant's `admin_subject_name` and the kind `"User"`.

For more details, refer to the [Defaulting Patterns](../../README.md#defaulting-patterns-iacyaml--tenants-org-yaml) section in the root README.
