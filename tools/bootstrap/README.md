# Bootstrap

This directory contains the bootstrapping scripts used to set up an initial organization with an Infrastructure as Code (IaC) root project and an IaC Service Account. It assigns initial IAM roles to this SA and prepares the required kubeconfigs for orchestration tools like `helm_cli`, `helmfile`, or `argocd`.

## Prerequisites

1. Before executing, make sure you are logged in to Distributed Cloud with an account that has the `organization-iam-admin` role.
2. Configure your environment details:
   ```bash
   cp config.sh.sample config.sh
   ```
   Then open `config.sh` and set the relevant variables like `ORG_NAME`, `GDCH_DOMAIN`, `GDCH_ZONE`, and `CLUSTER_NAME`.

## Usage

### 1. Bootstrap the Service Account
Run the `bootstrap.sh` script to handle the creation of the IaC root project, the Service Account, generation of the key files, and the setup of its organization and project IAM bindings:

```bash
./bootstrap.sh
```

### 2. Setup Authentication Contexts
Run the `authenticate.sh` script to generate context tokens and construct the Kubeconfigs for interaction with the three main endpoints (Global, Zone, and User Clusters):

```bash
./authenticate.sh
```

The context kubeconfigs will be successfully populated under the `generated/kubeconfig` directory.

### 3. Handy Aliases
Source the `aliases.sh` script to setup fast shortcuts for `kubectl` across the different contexts:

```bash
source ./aliases.sh
```

- **`kg`**: Queries against the Global API
- **`kz`**: Queries against the Zone Management API
- **`kc`**: Queries against the User Shared Cluster API
