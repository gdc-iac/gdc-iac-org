# Stage 1: Project Factory (`1-project-factory`)

The Project Factory dynamically processes tenant declarations to generate secure projects boundaries, provision dedicated service accounts, network policies, and IAM role bindings inside GDC Hosted.

---

## Operational Architecture

* **Target Control Plane Scope**: Global API Server (`gdc_context_global`)
* **Target Namespace**: `platform` (individual projects reside here)
* **Pre-requisites**: Stage `0-org-setup` must be fully executed and synced.

---

## Deployments & Sub-Helmfiles

All sub-helmfiles are executed sequentially to guarantee that projects are provisioned prior to dependent resources:

1. **`projects.yaml.gotmpl`**: Creates the core `Project` custom resources inside GDC Hosted.
   * **Chart**: `gdc-projects`
2. **`service-accounts.yaml.gotmpl`**: Provisions dedicated service accounts for tenant workloads.
   * **Chart**: `gdc-project-service-accounts`
3. **`iam.yaml.gotmpl`**: Establishes project `IAMRoleBinding` mappings linking developers and service accounts to predefined or custom IAM roles.
   * **Chart**: `gdc-iam-role-bindings`
4. **`project-network-policies.yaml.gotmpl`**: Provisions project-scoped traffic control policies.
   * **Chart**: `gdc-project-network-policies`

---

## Execution Commands

Run the following commands from the repository root directory:

```bash
# Template validation
helmfile -e dev -l stage=1-project-factory template

# Apply/Deploy stage
helmfile -e dev -l stage=1-project-factory apply
```

---

## Configuration & Defaulting

To streamline tenant configurations, this stage supports the **Tenant Admin Defaulting Pattern**. You can completely omit `subject_name` and `subject_kind` in project-scoped `iamrolebindings` under the tenant configurations, and they will automatically inherit the tenant's `admin_subject_name` and the kind `"User"`.

For more details, refer to the [Defaulting Patterns](../../README.md#defaulting-patterns-iacyaml--tenants-org-yaml) section in the root README.
