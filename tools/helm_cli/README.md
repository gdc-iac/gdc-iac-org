# Helm CLI Tool

`helm_cli.py` is a Python wrapper script for the Helm CLI. It serves two primary purposes:

1.  **Automated Deployments**: It automates running Helm commands (`upgrade`, `install`, etc.) for multiple resources defined in a structured YAML configuration file.
2.  **Direct Passthrough**: It can act as a simple passthrough to the `helm` command for actions that don't require a configuration file (e.g., `helm list`).

The script iterates through defined resource types and applies Helm charts located in the `../../charts/` directory.

## Prerequisites

- Python 3
- Helm installed and available in the system PATH.
- Python packages: `PyYAML`
- Bootstrapping of the GDC environment described in the global [README.md](./../../README.md)

## Usage

The script's command-line interface is designed to be similar to `helm` itself.

```bash
python3 helm_cli.py <action> [config_file] [helm_flags]
```

### Manual Example
1. Assuming you have bootstrapped the GDC environment, set the following environment variables (example):
    ```bash
    export ORG_NAME="gdchservices"
    export IAC_PROJECT="iac-root"
    export IAC_USER="fop-iac001@example.com"
    export IAC_SA="iac001-sa"
    export GDCH_DOMAIN="google.gdch.test"
    export GDCH_ZONE="us-east67-b"
    export GDCH_CONSOLE="console.${ORG_NAME}.${GDCH_ZONE}.${GDCH_DOMAIN}"
    ```
2. Log in as user $IAC_USER:
    ```bash
    gdcloud auth login (as $IAC_USER)"
    ```

4. Global configuration:
    ```bash
    gdcloud clusters get-credentials global-api
    python3 helm_cli.py list \
        --namespace=${IAC_PROJECT:?}
    ```
    ```bash
    gdcloud clusters get-credentials global-api
    python3 helm_cli.py template ../../examples/multi-value-org/example-infra.yaml \
        --namespace=${IAC_PROJECT:?} \
        --api=iac,global
    ```
    ```bash
    gdcloud clusters get-credentials global-api
    python3 helm_cli.py upgrade ../../examples/multi-value-org/example-infra.yaml \
        --namespace=${IAC_PROJECT:?} \
        --api=iac,global
    ```

3. Zonal configuration (for each zone):
    ```bash
    gdcloud clusters get-credentials ${ORG_NAME:?}-admin --zone ${GDCH_ZONE:?}
    python3 helm_cli.py list \
        --api=${GDCH_ZONE:?} \
        --namespace=${IAC_PROJECT:?}
    ```

    ```bash
    gdcloud clusters get-credentials ${ORG_NAME:?}-admin --zone ${GDCH_ZONE:?}
    python3 helm_cli.py template ../../examples/multi-value-org/example-infra.yaml \
        --namespace=${IAC_PROJECT:?} \
        --api=iac,${GDCH_ZONE:?}
    ```

### Arguments

- `<action>`: (Required) The Helm action to perform (e.g., `template`, `install`, `upgrade`, `lint`, `list`, etc.).
- `[config_file]`: (Optional) Path to the YAML configuration file containing the resource definitions. If omitted, the action is executed globally without trying to iterate on nested objects.
- `[helm_flags]`: (Optional) Any additional arguments or flags supported by the raw Helm CLI (e.g., `--set key=value`, `--namespace mynamespace`). These arguments are directly passed through to `helm`.

### Options

- `--api`: (Optional) Comma-separated list of APIs to process from the configuration file. If omitted, all APIs are processed.
- `--api-kubeconfig`: (Optional) Comma-separated list of kubeconfigs to use for API processing. It must match the number of specified APIs if `--api` is used and specify kubeconfig for each API. If not specified, the script will use the default kubeconfig for each API.
- `--dry-run`: If set, the script will parse the configuration and log the intended actions but will not execute the specific Helm commands that modify the state.
- `-v`, `--verbose`: Enable verbose (debug) logging output.

## Configuration

The tool expects a YAML configuration file that structures resources under specific API groups. A comprehensive example can be found at `examples/multi-value-org/example-infra.yaml`.

The supported structure maps specific list keys directly to their respective underlying charts:
```yaml
iac: # Mapped to: charts/gdc-iac
- role: "project-iam-admin"
  subject_kind: "User"
  subject_name: "fop-iac001@example.com"
global:
    iam-roles # Mapped to: charts/gdc-iam-roles
    projects: # Mapped to: charts/gdc-projects
      - iam-roles # Mapped to: charts/gdc-iam-roles
      - iam-role-bindings # Mapped to: charts/gdc-iam-role-bindings
      - project-network-policies # Mapped to: charts/gdc-project-network-policies
<zone1>:
    clusters: # Mapped to: charts/gdc-clusters
    projects: # Mapped to: charts/gdc-projects
      - buckets # Mapped to: charts/gdc-buckets
      - iam-role-bindings # Mapped to: charts/gdc-iam-role-bindings
      - project-network-policies # Mapped to: charts/gdc-project-network-policies
      - notebooks # Mapped to: charts/gdc-notebooks
      - harbors # Mapped to: charts/gdc-harbors
<zone2>:
    clusters: # Mapped to: charts/gdc-clusters
    projects: # Mapped to: charts/gdc-projects
      - buckets # Mapped to: charts/gdc-buckets
      - iam-role-bindings # Mapped to: charts/gdc-iam-role-bindings
      - project-network-policies # Mapped to: charts/gdc-project-network-policies
      - notebooks # Mapped to: charts/gdc-notebooks
      - harbors # Mapped to: charts/gdc-harbors
```
## How it works

1.  **Parses Configuration**: Reads the provided YAML file.
2.  **Iterates Resources**: Traverses the configuration based on the defined `RESOURCE_TYPES` hierarchy.
3.  **Generates Values**: Constructs a temporary values YAML file for each resource found.
4.  **Executes Helm**: Calls the Helm CLI with the specified action (e.g., `helm template ...`) targeting the corresponding chart (e.g., `../../charts/gdc-<resource_type>`).

## Running Tests

Unit tests are provided using the standard Python `unittest` framework in `test_helm_cli.py`. You can run the tests using any of the following commands from the `tools/helm_cli` directory:

1. **Direct execution:**
```bash
python3 test_helm_cli.py
```

2. **Using the `unittest` module explicitly:**
```bash
python3 -m unittest test_helm_cli.py
```

3. **Running `unittest` with verbose logging:**
```bash
python3 -m unittest -v test_helm_cli.py
```