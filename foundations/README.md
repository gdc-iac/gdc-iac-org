# GDC AG Foundations

Infrastructure-as-Code implementation for automating operational configurations inside [Google Distributed Cloud air gapped Organization](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/resources/resource-hierarchy#organization) utilizing Helmfile pipelines orchestrations. The organization is the top-level resource in the GDC resource hierarchy and defines a security boundary that encloses infrastructure resources to be administered together by this code.

---

## Core Concepts

The system groups environment resources and setups into execution layers triggered sequentially:

- **`0-bootstrap/`**: Sets up root administrative namespace, base operations, and core landing zone operators.
- **`0-org-setup/`**: Sets up platform operations, organization policies boundaries, accounts systems linkages, and foundational setups.
- **`1-project-factory/`**: Dynamically processes projects definitions generating IAM permissions roles bindings, and service accounts baseline setups.
- **`2-resources/`**: Coordinates deployment instances of application resources (observability dashboards, Harbor image registries, backup plans and repositories, VM instances, Database configurations, Buckets stores).
- **`3-clusters/`**: Instantiates and provisions standard Kubernetes clusters with baseline supporting services.
- **`4-notebooks/`**: Facilitates development or deployment of AI/ML workloads.
- **`5-workload-factory/`**: Orchestrates User Cluster application workloads for GDC Blueprint Patterns (`blueprints/patterns/*/chart`) while relying on Stage 2 (`2-resources`) for Zonal managed databases, VMs, and buckets.

## Operational Playbooks & Guides
- 📖 **[Deployment Manual](DEPLOYMENT_MANUAL.md)**: Step-by-step execution, RBAC bootstrapping, verification, and rollback runbook.
- 📦 **[Air-Gap Mirroring & Ingestion Guide](AIRGAP_MIRRORING.md)**: Downloading releases, SHA256/Cosign verification, and turnkey Harbor ingestion with `./scripts/ingest-airgap-bundle.sh`.
- 💻 **[Workstation Onboarding](WORKSTATION_ONBOARDING.md)**: Tooling installation, Helm plugins, and environment setup.

---

## Architecture Overview

```text
gdc-iac-org/
├── charts/                     <- 30+ canonical Helm charts for GDC Custom Resources
├── foundations/
│   ├── bases/                  <- Shared base configurations and variables
│   │   └── environments/       <- Environments (dev, stg, prd) definitions files
│   │       ├── dev/            <- dev environment definition
│   │       │   ├── global/           <- `dev` environment global API resources
│   │       │   │   ├── iac.yaml      <- IaC role bindings and service accounts
│   │       │   │   └── tenant-1.yaml <- Organization global resources definitions
│   │       │   ├── zone1/            <- `dev` zonal GDC resources (in example, GDC Zone 1)
│   │       │   │   └── tenant-1.yaml <- Organization resource specifications
│   │       │   ├── zone2/            <- `dev` zonal GDC resources (in example, GDC Zone 2)
│   │       │   │   ...
│   │       │   │   ...
│   │       │   ├── charts.yaml       <- Dual-mode chart paths & version overrides
│   │       │   ├── contexts.yaml     <- Global and zonal API contexts
│   │       │   ├── globals.yaml      <- Environment parameters
│   │       │   └── overrides.yaml    <- Manual configuration overrides 
│   │       ├── stg/                <- `stg` environment definition
│   │       │   ...
│   │       └── prd/                <- `prd` environment definition
│   │           ...
│   └── releases/               <- Modular Helmfile execution stages
│       ├── 0-bootstrap/        <- Foundations bootstrap stage
│       ├── 0-org-setup/        <- Organization policies setup stage
│       ├── 1-project-factory/  <- Tenant project factory stage
│       ├── 2-resources/        <- Application zonal resources stage
│       ├── 3-clusters/         <- Standard/User clusters stage
│       ├── 4-notebooks/        <- AI/ML Jupyter notebooks stage
│       └── 5-workload-factory/         <- GDC Blueprint Patterns workload stage
└── scripts/
    └── ingest-airgap-bundle.sh <- Turnkey air-gap bundle ingestion & Harbor sync utility
```

---

## Environment Configuration

Each environment (e.g. dev, stg, prd) represents a set of GDC resources belonging to a specific GDC ag Organization and is defined by a set of configuration files.

1. Environment settings files.
	- **`context.yaml`**: Cluster context `gdc_context_global` for global API access and dictionary of zonal GDC API contexts.
	- **`globals.yaml`**: Shared global environment parameters.
	- **`charts.yaml`**: Dual-mode chart paths & version overrides.
	- **`overrides.yaml`**: Local configuration manual overrides. Properties set here supersede values loaded inside preceding configurations.

2. Global API resources definitions: 
	- **`iac.yaml`**: Static platform and project-level roles for the IaC system.
	- **`tenant-*.yaml`**: Global Organizational resources (projects, roles, etc) grouped by tenant profiles.

3. One or more zone resources definitions:
	- **`tenant-*.yaml`**: Zonal resources (clusters, Harbors, etc.) for that specific zone, grouped by tenant profiles.

The key role of environment component is providing [workload separation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/resources/workload-separation). There are two patterns possible that depend on a level oif isolation required:
- single organization with [separate projects per software development environment](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/resources/access-boundaries#design-projects-for-isolation) with [recommendation to design separate Kubernetes clusters per software development environment](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/resources/workload-separation#design-clusters-for-workload-isolation)
- [separate organizations](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/resources/access-boundaries#define-orgs-for-isolation). Each organization within a GDC zone provides physical isolation for compute infrastructure, and logical isolation for networking, storage, and other services. Users in one organization have no access to resources in another organization unless explicitly granted access. Network connectivity from one organization to another is not allowed by default, unless explicitly configured to allow data transfer out from one organization and data transfer in to another.

## Organization Configuration Pattern

The environment allows specifying multiple tenants per organization via assigning multiple static files (e.g. `tenant-1.yaml` and `tenant-2.yaml`) inside an environment. This separation is useful for large organizations with multiple teams or departments sharing the same GDC organization for resource consumption optimization. The default assumption is that there is one tenant per organization - `tenant-1`.

Parameters are processed through a recursive merging behavior:

- **Independent Tenant Names (Safe)**: Distinct dictionary assignments (`tenant-1: ...` and `tenant-2: ...`) are deeply combined into the underlying `gdc_tenants:` evaluation object.

### Required Tenant Configuration Structure (`tenant-*.yaml`)

Every tenant file **MUST** wrap its properties under the environment key (`dev:`, `stg:`, or `prd:`) to match the Project Factory parser requirements:

```yaml
# bases/environments/<environment>/tenant-X.yaml
dev:
  gdc_tenants:
    tenant-X:
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

## Defaulting Patterns (`iac.yaml` & `tenant-*.yaml`)

To avoid repetitive declarations of `subject_name` and `subject_kind` inside configuration profiles, the system supports automated template defaulting across different stages:

### 1. Service Account Defaulting (`iac.yaml`)
* **Context**: Root bootstrap level bindings.
* **Dynamic Fallback**: When `subject_name` and `subject_kind` are omitted for a binding in `iac.yaml`, they default to:
  * **`subject_name`**: The environment-specific service account `iac_sa` defined in `globals.yaml` (e.g. `"system:serviceaccount:iac-root:iac001-sa"`).
  * **`subject_kind`**: `"serviceAccount"`.

### 2. Tenant Admin Defaulting (`tenant-*.yaml`)
* **Context**: Organization Setup (`0-org-setup`) and Project Factory (`1-project-factory`) stages.
* **Dynamic Fallback**: When `subject_name` and `subject_kind` are omitted for a global or project-level binding under `gdc_tenants`, they default to:
  * **`subject_name`**: The specific tenant's `admin_subject_name` parameter (e.g. `"fop-mellon@example.com"`).
  * **`subject_kind`**: `"User"`.

### Design Principles & Rationale (The "Why")

This defaulting architecture is built around core Helmfile and Kubernetes GitOps best practices:
* **Strict Organization Separation**: 
  The environment allows specifying multiple tenants per organization via assigning multiple static files (e.g. `tenant-1.yaml` and `tenant-2.yaml`) inside an environment however single environment can only belong to a single organization.
* **Strict Separation of Concerns (Code/Values Separation)**:
  Configuration profiles (`iac.yaml`, `tenant-X.yaml`) are kept as **pure static YAML**. Keeping them free from complex inline templates makes them highly readable, auditable, and declarative, protecting operators from syntax errors or templating leaks during value definition.
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

#### Simplified `tenants-1.yaml`:
```yaml
dev:
  gdc_tenants:
    tenant-1:
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

Monolithic fallback contexts inside merged environment variables are strictly prohibited. Every environment **MUST** explicitly declare its isolated Global and Zonal Kubecontexts under its respective `globals.yaml` file.
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

