# Stage 2: Resources (`2-resources`)

This stage provisions regional workload infrastructure resources and zonal applications (Virtual Machines, Databases, Object Storage Buckets, Observability Dashboards, Harbor registries, and Backups) mapped to individual projects.

---

## Operational Architecture

* **Target Control Plane Scope**: Zonal API Server (`gdc_context_zone`)
* **Target Namespace**: Project namespaces (e.g. `mellon-prj`) or `platform`
* **Pre-requisites**: Stage `1-project-factory` must be fully executed and synced (projects must exist).

---

## Deployments & Sub-Helmfiles

1. **`vm.yaml.gotmpl`**: Provisions virtual machine instances.
   * **Chart**: `gdc-vm`
2. **`buckets.yaml.gotmpl`**: Provisions object storage buckets.
   * **Chart**: `gdc-buckets`
3. **`dbs.yaml.gotmpl`**: Provisions managed database clusters (PostgreSQL / Alloydb Omni).
   * **Chart**: `gdc-dbs`
4. **`dashboards.yaml.gotmpl`**: Configures observability dashboards.
   * **Chart**: `gdc-dashboards`
5. **`habor.yaml.gotmpl`**: Provisions dedicated Harbor image registry instances.
   * **Chart**: `gdc-harbors`
6. **`backup-repositories.yaml.gotmpl`**: Sets up zonal backup storage repositories.
   * **Chart**: `gdc-backup-repositories`
7. **`backups.yaml.gotmpl`**: Provisions automated virtual machine backup schedules.
   * **Chart**: `gdc-backup-plans`

---

## Execution Commands

Run the following commands from the repository root directory:

```bash
# Template validation
helmfile -e dev -l stage=2-resources template

# Apply/Deploy stage
helmfile -e dev -l stage=2-resources apply
```

---

## Dashboard Resolution & Sourcing Rules

This stage processes observability dashboards supporting multiple integration patterns configured inside `bases/environments/<environment>/tenants-org-*.yaml`:

- **Inline Template Payload**: Passing explicit JSON configurations models string snippets (`json_model`).
- **Reference Template File**: Fetching specific layouts files stored under examples paths (`json_model_file`).
- **Nested Subdirectory Models Reference**: Defining folders targets containing multiples dashboard configurations files sequentially expanded (`json_model_dir`).

### Defining dashboards at Resources level (Stage 2)

```yaml
gdc_tenants:
  org-1:
    global:
      projects:
        - name: "mellon-prj"
          resources:
            dashboards:
              # Example 1: Inline JSON
              - name: "inline-dashboard"
                json_model: '{"title": "Custom Metric Overview"}'
              
              # Example 2: File reference from examples directory
              - name: "spend-report-dashboard"
                json_model_file: "org-spend-dash.json"
              
              # Example 3: Scan directory containing JSON layout definitions
              - json_model_dir: "mydashboards"
```

### Automated scan of dashboards directories

Omitting the explicit dashboards array definitions instructs the module framework to scan for dashboard configuration files matching fallback paths:

```yaml
# Define local execution fallback parameters inside environment configuration files (charts.yaml)
gdc_dashboards_examples_path: "../../charts/gdc-dashboards/examples"
gdc_dashboards_env_path: "mydashboards"
```

