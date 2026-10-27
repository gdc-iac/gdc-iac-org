# DGA Factory Example

This example demonstrates how to automate the deployment of a structured landing zone for multiple teams and users in a Google Distributed Cloud Hosted (GDCH) environment using a "factory" approach.

It uses a combination of Python scripts and Helm charts to dynamically generate and apply configurations based on a simple YAML definition of teams and users.

## Architecture

The DGA Factory follows a 3-step pipeline:

1.  **Configuration**: Define teams, users, their readiness status, and administrators in `users.yaml`. Environment variables (kubeconfig paths, parameters, network CIDRs, images, etc.) are configured in `scripts/config.sh`.
2.  **Generation**: Python scripts (`update-config.py`, `update-secrets.py`) read the configuration and individually render Jinja2 templates (`shared.yaml.j2`, `team-shared.yaml.j2`, `user.yaml.j2`, `secret.yaml.j2`) into specific YAML files for each team and user. Files will only be regenerated if modifications are present to save subsequent execution times based on hashes.
3.  **Deployment**: 
    *   `sync-config.py`: Uses the `helm_cli.py` wrapper to apply the generated environment and user configurations to the cluster. Skips deployments where the source rendered configuration has not been modified using a `last-sync` timestamp check.
    *   `sync-secrets.py`: Maps, retrieves and deploys the S3 user secrets to the user cluster. Also features execution skips for artifacts unchanged since the last sync.

### Directory Structure

```text
├── charts/
│   ├── dga-secret-sync/       # Helm chart for managing the syncing of S3 credentials from Secrets to PVCs
│   └── dga-user-config/       # Helm chart for user-specific Kubernetes resources
├── scripts/
│   ├── authenticate.sh       # Script to authenticate and set kubeconfig credentials
│   ├── bootstrap-sa.sh       # Script to bootstrap IAM bindings for the IaC SA
│   ├── cluster-uninstall.sh  # Uninstalls previously deployed config artifacts at the cluster level
│   ├── config.sh             # Central environment variable configuration
│   ├── global-uninstall.sh   # Uninstalls previously deployed config artifacts at the global level
│   ├── status.sh             # Script to verify the status of deployed cluster resources
│   ├── sync-config.py        # Deploys generated configurations via helm_cli.py
│   ├── sync-secrets.py       # Deploys rendered secrets to the user cluster
│   ├── update-config.py      # Renders configuration templates
│   ├── update-secrets.py     # Renders secret templates
│   └── zone-uninstall.sh     # Uninstalls previously deployed config artifacts at the zonal level
├── secret.yaml.j2             # Template for user S3 provisioning secrets
├── shared.yaml.j2             # Template for global shared services
├── team-shared.yaml.j2        # Template for team-shared resources
├── user.yaml.j2               # Template for user-specific resources
└── users.yaml                 # Definition of teams and users
```

_Note: When generation scripts execute, they create `generated/` directories automatically to hold outputs._

## Configuration

### 1. `users.yaml`

Define your teams, their administrators, their user membership, and if the user configurations are fully provisioned (`ready`) or disabled/`stopped` (`not-ready`).

```yaml
team-1:
  admin_user: "admin-email@example.com"
  users:
    - user1@example.com: ready
    - user2@example.com: not-ready
```

### 2. `scripts/config.sh`

Configure your environment variables, including:
-   **Core parameters:** `ORG_NAME`, `IAC_PROJECT`, `IAC_SA`, `GDCH_ZONE`, `GDCH_DOMAIN`
-   **Resource definitions:** `CLUSTER_NAME`
-   **Network setup:** `CLUSTER_POD_CIDR_SIZE`, `CLUSTER_SERVICE_CIDR_SIZE`, `CLUSTER_INGRESS_SERVICE_IP_SIZE`
-   **Infrastructure:** `CLUSTER_K8S_VERSION`, `CLUSTER_MACHINE_TYPE`, `CLUSTER_NODE_COUNT`, `CLUSTER_NODE_POOL_NAME`
-   **Authentication mapping:** `AIS_PREFIX`
-   **Tooling administration:** `HARBOR_ADMIN_EMAIL`, `CLOUD_BILLING_CONFIG_ACCOUNT_ID`
-   Paths to various auto-generated kubeconfigs and scripts in the setup directory topology.

## Usage

### 1. Bootstrapping (Initial Setup)

Run the bootstrap scripts to set up the necessary IAM bindings for the IaC Service Account and projects.

```bash
./scripts/bootstrap-sa.sh
```

### 2. Authentication

Before attempting to generate configurations that need kubernetes context, load the IaC service account credentials and set up kubeconfigs for global, zonal, and user APIs. Place your service account json key at `generated/secrets/iac001-sa.json`.

```bash
./scripts/authenticate.sh
```

### 3. Generate Configurations and Secrets

Run the update scripts to render the YAML files from templates based on `users.yaml` and logic inside the python scripts based on GDCH API calls checking provisioning statuses.

```bash
./scripts/update-config.py
./scripts/update-secrets.py
```

This will populate the `generated/output/` and `generated/secrets/` directories. Output generated code files will be checked against matching file hashes, resulting in new saves only if content has drifted.

### 4. Sync Configurations and Secrets

Apply the generated configurations and secrets to the GDC environment using the sync scripts.

```bash
./scripts/sync-config.py
./scripts/sync-secrets.py
```

These scripts are built identically to leverage timestamps for file comparison against `.last-sync` temporary files, completely skipping un-modified definitions.

### 5. Verify Status

You can use the `status.sh` script to display all Helm installations operating in all cluster topology API spaces via global, zonal or cluster definitions.

```bash
./scripts/status.sh
```

### 6. Uninstall Workloads

If necessary, you have access to three uninstallation shell scripts targeting all possible deployment spaces (`global-uninstall.sh`, `zone-uninstall.sh`, `cluster-uninstall.sh`) that use raw wildcard inputs (`$@`) passed directly to `helm uninstall`.

```bash
./scripts/global-uninstall.sh team-1-shared-infra
```

## Customization

You can dynamically manage GDCH integrations by adapting variables or conditional Jinja2 inclusions within files such as logic rendering `stopped: true` under `not-ready` workloads. Using `*.yaml.j2` overrides, you can generate customized Kubernetes resources generated per team or individual data-scientist workflow.
