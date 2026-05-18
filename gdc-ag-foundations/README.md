# GDC AG Foundations

Infrastructure-as-Code implementation for automating operational configurations inside Google Distributed Cloud systems utilizing Helmfile pipelines orchestrations.

---

## Core Concepts

The system groups environment resources and setups into execution layers triggered sequentially:

- **`0-bootstrap/`**: Sets up root administrative namespace, base operations, and core landing zone operators.
- **`0-org-setup/`**: Sets up platform operations, organizations policies boundaries, accounts systems linkages, and foundational setups.
- **`1-project-factory/`**: Dynamically processes projects definitions generating IAM permissions roles bindings, and service accounts baseline setups.
- **`2-resources/`**: Coordinates deployment instances of application resources (observability dashboards, Harbor image registries, backup plans and repositories, VM instances, Database configurations, Buckets stores).
- **`3-clusters/`**: Instantiates and provisions standard Kubernetes clusters with baseline supporting services.
- **`4-notebooks/`**: Facilitates development or deployment of AI/ML workloads.

## Architecture Overview

```text
gdc-ag-foundations/
├── bases/                  <- Shared base configurations and variables
│   └── environments/       <- Environment definitions files
│       ├── dev/
│       │   ├── globals.yaml
│       │   ├── charts.yaml
│       │   ├── iac.yaml
│       │   ├── tenants-org-1.yaml
│       │   ├── tenants-org-2.yaml
│       │   └── overrides.yaml
│       ├── prd/
│       └── stg/
├── charts/                 <- Localized deployment modules definitions
│   └── gdc-dashboards/     <- Charts configurations structures
│       └── examples/       <- Default dashboard layout specifications
│   └── ...
└── releases/               <- Modular deployment groups scripts
    ├── 0-bootstrap/        <- Foundations bootstrap stage
    ├── 0-org-setup/        <- Organization policies setup stage
    ├── 1-project-factory/  <- Tenant project factory stage
    ├── 2-resources/        <- Application zonal resources stage
    ├── 3-clusters/         <- Standard/User clusters stage
    └── 4-notebooks/        <- AI/ML Jupyter notebooks stage
```

---

## Configuration Modular Separation

Monolithic setup values are structured into targeted files profiles executed sequentially:

1. **`globals.yaml`**: Shared context parameters (`gdc_context_global`, `gdc_context_zone`, `iac_sa`).
2. **`charts.yaml`**: Paths locations referencing workspace Helm packages directories.
3. **`iac.yaml`**: Static platform and project-level roles and IAM/RBAC rolebindings setup definitions.
4. **`tenants-org-*.yaml`**: Grouped properties profiles defining operational specifications of separate GDC tenants.
5. **`overrides.yaml`**: Local configuration manual overrides options. Properties set here supersede values loaded inside preceding configurations.

---

## Multi-Tenant Configuration Pattern

When assigning multiple static files (e.g. `tenants-org-1.yaml` and `tenants-org-2.yaml`) inside an environment, parameters are processed through a recursive merging behavior:

- **Independent Tenant Names (Safe)**: Distinct dictionary assignments (`org-1: ...` and `org-2: ...`) are deeply combined into the underlying `gdc_tenants:` evaluation object.
- **Overlapping Keys Constraint**: If both configuration sources define parameters referencing the identical customer tenant context ID, fields loaded lower in the values evaluation chain will override rather than append entries.

### Required Tenant Configuration Structure (`tenants-org-*.yaml`)

Every tenant file **MUST** wrap its properties under the environment key (`dev:`, `stg:`, or `prd:`) to match the Project Factory parser requirements:

```yaml
# bases/environments/<environment>/tenants-org-X.yaml
dev:
  gdc_tenants:
    org-X:
      global:
        org_policies:
          - name: "policy-name"
            spec: {}
        projects:
          - name: "project-name"
            iamrolebindings:
              - role: "project-iam-admin"
                subject_kind: "User"
                subject_name: "user@example.com"
            serviceaccounts:
              - name: "service-account-name"
                namespace: "project-name"
            resources:
              buckets:
                - name: "bucket-name"
                  description: "store description"
                  storage_class: "Standard"
                  location: "zone1"
```

---

## Defaulting Patterns (`iac.yaml` & `tenants-org-*.yaml`)

To avoid repetitive declarations of `subject_name` and `subject_kind` inside configuration profiles, the system supports automated template defaulting across different stages:

### 1. Service Account Defaulting (`iac.yaml`)
* **Context**: Root bootstrap level bindings.
* **Dynamic Fallback**: When `subject_name` and `subject_kind` are omitted for a binding in `iac.yaml`, they default to:
  * **`subject_name`**: The environment-specific service account `iac_sa` defined in `globals.yaml` (e.g. `"system:serviceaccount:iac-root:iac001-sa"`).
  * **`subject_kind`**: `"serviceAccount"`.

### 2. Tenant Admin Defaulting (`tenants-org-*.yaml`)
* **Context**: Organization Setup (`0-org-setup`) and Project Factory (`1-project-factory`) stages.
* **Dynamic Fallback**: When `subject_name` and `subject_kind` are omitted for a global or project-level binding under `gdc_tenants`, they default to:
  * **`subject_name`**: The specific tenant's `admin_subject_name` parameter (e.g. `"fop-mellon@example.com"`).
  * **`subject_kind`**: `"User"`.

### Design Principles & Rationale (The "Why")

This defaulting architecture is built around core Helmfile and Kubernetes GitOps best practices:

* **Strict Separation of Concerns (Code/Values Separation)**:
  Configuration profiles (`iac.yaml`, `tenants-org-X.yaml`) are kept as **pure static YAML**. Keeping them free from complex inline templates makes them highly readable, auditable, and declarative, protecting operators from syntax errors or templating leaks during value definition.
* **Pipeline-Level Controller Defaulting**:
  Defaulting is resolved entirely inside the pipeline release files (`.gotmpl` templates). These files act like a Kubernetes controller, dynamically mapping lightweight user declarations into fully validated API resources at template generation time.
* **Robust JSON Serialization**:
  Instead of using error-prone white-space indentation helpers (e.g., `toYaml | indent`), the pipeline maps list fields down to child charts using standard JSON serialization (`toJson`). This completely eliminates whitespace syntax issues common in nested Helm charts.
* **Cross-Namespace Identity Compliance**:
  The templates explicitly inspect and preserve standard Kubernetes RBAC fields (such as `subject_namespace` inside `rbacrolebindings`). This ensures that complex, cross-namespace identity mappings work out-of-the-box without template truncation.

---

### Simplified Configuration Examples


#### Simplified `iac.yaml`:
```yaml
dev:
  iac:
    global:
      namespace: "platform"
      iamrolebindings: 
      - role: "bucket-admin"           # Automatically bound to globals.yaml iac_sa with kind "serviceAccount"
```

#### Simplified `tenants-org-1.yaml`:
```yaml
dev:
  gdc_tenants:
    org-1:
      global:
        admin_subject_name: "fop-mellon@example.com"
        projects:
          - name: "mellon-prj"
            iamrolebindings:
              - role: "project-iam-admin"  # Automatically bound to "fop-mellon@example.com" with kind "User"
```

### Explicit Override:
You can always override the default behavior for individual bindings by explicitly declaring the fields:
```yaml
            iamrolebindings: 
              - role: "project-iam-admin"
                subject_name: "other-operator@example.com"
                subject_kind: "User"
```

---

## Execution Standards

### Required Directory Execution Point
Given internal pathing specifications evaluated relative to `${PWD}`, execution operations **MUST** originate directly within project base folder `/gdc-ag-foundations`.

#### Examples Tasks Execution Commands

Template baseline environment deployment configurations all together:
```bash
helmfile -e dev template
```

Template baseline stage 0-org-setup deployment configuration:
```bash
helmfile -e dev -l stage=0-org-setup template
```

Validate isolated release files updates configurations:
```bash
helmfile -f releases/2-resources/dashboards.yaml.gotmpl -e dev template
```

---

## Operational Control Plane Routing & Isolation

To guarantee strict security boundary isolation in production GDC environments, the landing zone enforces dynamic, tenant-isolated Kubecontext routing.

### 1. Tenant-Scoped Context Definition
Monolithic fallback contexts inside merged environment variables are strictly prohibited. Every tenant organization **MUST** explicitly declare its isolated Global and Zonal Kubecontexts under its respective properties file:

```yaml
# bases/environments/dev/tenants-org-1.yaml
dev:
  gdc_tenants:
    org-1:
      global:
        kube_context_global: "global-api-context-for-org-1"
        kube_context_zonal: "zonal-api-context-for-org-1"
```

### 2. Pre-Flight Security Assertions (Compile-Time Fail-Safe)
To prevent any accidental cross-tenant contamination or leaky context routing fallback to administrative clusters:
* Each dynamic stage (`0-org-setup`, `1-project-factory`, `2-resources`, `3-clusters`, `4-notebooks`) contains a top-level **Pre-Flight Security Loop**.
* The pipeline inspects the environment data and triggers a compile-time `fail` assertion if *any* active tenant lacks explicit `kube_context_global` or `kube_context_zonal` declarations:
  ```text
  ❌ SECURITY BREACH PREVENTED: Tenant 'org-X' does not have an explicitly defined 'kube_context_global' context!
  ```

### 3. Stage Boundaries
* **Global Stages (Stages 0 & 1)**: Target the tenant-isolated global control plane API (`kube_context_global`) to coordinate platform policies, project boundaries, and IAM bindings.
* **Zonal / Resource Stages (Stages 2, 3 & 4)**: Target the tenant-isolated zonal infrastructure API (`kube_context_zonal`) to coordinate application instances, databases, registries, user clusters, and notebooks.

---

## GDC IAM Security & Admission Webhooks

Google Distributed Cloud enforces strict privilege escalation checks via validating admission webhooks (e.g., **`customroles.iam.global.gdc.goog`**). 

When defining or updating **`CustomRole`** resources (in `globalRules` or `zonalRules`), **the identity executing the deployment must natively possess the permissions being granted**. If your active deployment account lacks the specified API groups or verbs, the webhook will block the deployment with:
```text
admission webhook "customroles.iam.global.gdc.goog" denied the request: error while validating rules: authorization for custom role rules failed
```
**Recommendation**: Execute pipeline deployments using an Organization Admin identity or scope your CustomRole templates to exactly match the privilege boundaries of your deploying Service Account.

---

## CI/CD Automation Strategy (Staged Execution Samples)

Deploy orchestrated stages configurations sequentially via this GitLab Pipeline Job sample (`.gitlab-ci.yml`):

```yaml
stages:
  - validate
  - plan
  - deploy-org
  - deploy-projects
  - deploy-resources
  - deploy-clusters
  - deploy-notebooks

default:
  image: ghcr.io/helmfile/helmfile:v1.2.1
  before_script:
    - cd gdc-ag-foundations

.helmfile_plan:
  stage: plan
  script:
    - helmfile -e $ENV -l stage=$STAGE diff

.helmfile_deploy:
  script:
    - helmfile -e $ENV -l stage=$STAGE apply

validate:
  stage: validate
  script:
    - helmfile -e dev lint
    - helmfile -e dev template

# Stage 0
plan:0-org:
  extends: .helmfile_plan
  variables:
    ENV: dev
    STAGE: 0-org-setup

deploy:0-org:
  stage: deploy-org
  extends: .helmfile_deploy
  variables:
    ENV: dev
    STAGE: 0-org-setup
  when: manual

# Downstream jobs (1-project-factory, 2-resources, etc) follow this sequence
```

---

## Operational Playbooks & Self-Deployment Manuals

For comprehensive onboarding, container mirroring, and manual step-by-step stage execution runbooks, refer to the dedicated guides below:

* **[Onboarding Workstation Guide](WORKSTATION_ONBOARDING.md)**: Local workstation preparation, tool requirements, and GDC context configurations.
* **[Air-Gapped Mirroring Manual](AIRGAP_MIRRORING.md)**: Mirroring external container images and Helm charts into isolated regional Harbor registries.
* **[Step-by-Step Deployment Guide](DEPLOYMENT_MANUAL.md)**: Step-by-step instructions for manual stage triggers, pre-flight testing, and pipeline rollbacks.

