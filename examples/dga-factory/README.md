# DGA Factory Example

This example demonstrates how to automate the deployment of a structured landing zone for multiple teams and users in a Google Distributed Cloud Hosted (GDCH) environment using a "factory" approach.

It uses a combination of Python scripts and Helm charts to dynamically generate and apply configurations based on a simple YAML definition of teams and users.

## Architecture

The DGA Factory follows a 3-step pipeline:

1.  **Configuration**: Define teams, users, and administrators in `users.yaml`. Environment variables (kubeconfig paths, images, etc.) are configured in `scripts/config.sh`.
2.  **Generation**: Python scripts (`update-config.py`, `update-secrets.py`) read the configuration and render Jinja2 templates (`shared.yaml.j2`, `team-shared.yaml.j2`, `user.yaml.j2`, `secret.yaml.j2`) into specific YAML files for each team and user.
3.  **Deployment**: 
    *   `sync-config.py`: Uses the `helm_cli.py` wrapper to apply the generated configurations to the cluster.
    *   `sync-secrets.py`: Deploys rendered secrets to the user cluster.

### Directory Structure

```text
├── charts/
│   └── dga-user-config/       # Helm chart for user-specific Kubernetes resources
├── scripts/
│   ├── bootstrap-sa.sh       # Script to bootstrap IAM bindings for the IaC SA
│   ├── bootstrap.sh          # Script to bootstrap project-level IAM bindings
│   ├── config.sh             # Central environment variable configuration
│   ├── status.sh             # Script to verify the status of deployed resources
│   ├── sync-config.py        # Deploys generated configurations via helm_cli.py
│   ├── sync-secrets.py       # Deploys rendered secrets to the user cluster
│   ├── update-config.py      # Renders configuration templates
│   └── update-secrets.py     # Renders secret templates
├── secret.yaml.j2             # Template for user secrets
├── secrets/                   # Rendered user secrets (generated)
├── shared.yaml.j2             # Template for global shared services
├── team-shared.yaml.j2        # Template for team-shared resources
├── user.yaml.j2               # Template for user-specific resources
├── users/                     # Rendered configurations (generated)
└── users.yaml                 # Definition of teams and users
```

## Configuration

### 1. `users.yaml`

Define your teams and users here.

```yaml
data-ets:
  admin_user: "org-70033-user-HGY395"
  users:
    - org-70033-user-PUF587
    - org-70033-user-RND123
```

### 2. `scripts/config.sh`

Configure your environment variables, including:
-   `ORG_NAME`, `IAC_PROJECT`, `IAC_SA`
-   `GDCH_ZONE`, `GDCH_DOMAIN`
-   `CLUSTER_NAME`
-   Paths to various kubeconfigs (`GLOBAL_API_KUBECONFIG`, `ZONE_KUBECONFIG`, `USER_CLUSTER_KUBECONFIG`)
-   Images (`NB_JUPYTER_IMAGE`, `S3_PROXY_IMAGE`)

## Usage

### 1. Bootstrapping (Initial Setup)

Run the bootstrap scripts to set up the necessary IAM bindings for the IaC Service Account and projects.

```bash
./scripts/bootstrap-sa.sh
./scripts/bootstrap.sh
```

### 2. Generate Configurations and Secrets

Run the update scripts to render the YAML files from templates based on `users.yaml`.

```bash
./scripts/update-config.py
./scripts/update-secrets.py
```

This will populate the `users/` and `secrets/` directories.

### 3. Sync Configurations and Secrets

Apply the generated configurations and secrets to the GDC environment.

```bash
./scripts/sync-config.py
./scripts/sync-secrets.py
```

### 4. Verify Status

You can use the `status.sh` script (if implemented fully) or standard `kubectl` commands to verify the deployment.

```bash
./scripts/status.sh
```

## Customization

You can modify the Jinja2 templates (`*.yaml.j2`) to customize the resources generated for each team and user.
