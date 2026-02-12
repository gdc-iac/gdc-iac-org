# Helmfile Example for GDC IAC Helm

This directory provides an example of how to use `helmfile` to manage the deployment of Google Distributed Cloud (GDC) infrastructure components using the `gdc-iac-helm` charts.

Helmfile is a declarative specification for deploying Helm charts. It empowers you to manage your infrastructure as code, adopting GitOps principles. You can version control your entire cluster state, automate deployments, and manage environment-specific configurations from a single `helmfile.yaml` file. [4, 13]

## Prerequisites

Before you begin, ensure you have the following tools installed and configured:

*   Helm (v3.0.0 or later) [2]
*   Helmfile
*   `kubectl` configured to communicate with your GDC cluster.

## Directory Structure

```
.
├── helmfile.yaml
├── values
│   └── my-custom-values.yaml
└── README.md
```

*   **`helmfile.yaml`**: The core `helmfile` configuration. It defines the Helm repositories and the releases to be deployed.
*   **`values/`**: This directory holds custom values files. You can structure your values by environment (e.g., `dev`, `staging`, `prod`) or by component.
*   **`README.md`**: This file.

## Usage

The following commands demonstrate the basic workflow for using `helmfile`.

1.  **Add/Update Helm Repositories:**
    This command adds the repositories defined in your `helmfile.yaml` to your local Helm configuration.

    ```bash
    helmfile repos
    ```

2.  **Lint Charts (Optional):**
    It's a good practice to lint your charts to catch any formatting or template errors before deployment.

    ```bash
    helmfile lint
    ```

3.  **Preview Changes:**
    You can preview the changes that will be applied to your cluster. This will show a diff of the rendered templates against the live state.

    ```bash
    helmfile diff
    ```

4.  **Deploy or Update Releases:**
    The `apply` command deploys or updates the releases defined in `helmfile.yaml`. It only applies changes if there's a diff.

    ```bash
    helmfile apply
    ```
    Alternatively, `sync` is an alias for `apply`. [1]

    ```bash
    helmfile sync
    ```

5.  **Check Release Status:**
    To see the status of all the releases managed by the helmfile.

    ```bash
    helmfile status
    ```

6.  **Destroy Releases:**
    This command will uninstall all the releases defined in the `helmfile.yaml`. Use with caution.

    ```bash
    helmfile destroy
    ```

## Configuration

### helmfile.yaml

The `helmfile.yaml` is where you declare the desired state of your Helm releases. Here is a basic example:

```yaml
# helmfile.yaml

# Define the helm repositories to be used
repositories:
  - name: gdc-iac
    url: oci://your-gdc-iac-helm-repo

# Define the releases to be deployed
releases:
  - name: gdc-cluster-essentials
    namespace: kube-system
    chart: gdc-iac/gdc-cluster-essentials
    version: "1.0.0"
    # Apply custom values from a file
    values:
      - ./values/my-custom-values.yaml
```

### Managing Environments

Helmfile excels at managing multiple environments. You can use templating in your `helmfile.yaml` to switch between different value files or settings based on the target environment. [12, 13]

For more advanced configurations and best practices, refer to the official Helmfile documentation.