# Helm CLI Tool

`helm_cli.py` is a Python script designed to automate the execution of Helm commands based on a structured configuration file. It iterates through defined resource types and applies Helm charts located in the `../../charts/` directory.

## Prerequisites

- Python 3
- Helm installed and available in the system PATH.
- Python packages: `PyYAML`

## Usage

```bash
python3 helm_cli.py <config_file> [options]
```

### Arguments

- `config_file`: (Required) Path to the YAML configuration file containing the resource definitions.

### Options

- `-a`, `--action`: The Helm action to perform. Defaults to `template`. Common actions include `install`, `upgrade`, `lint`.
- `--dry-run`: If set, the script will parse the configuration and log the intended actions but will not execute the Helm commands.
- `-v`, `--verbose`: Enable verbose (debug) logging.

## Configuration

The tool expects a YAML configuration file that structures resources under specific API groups. The supported structure includes:

- `clusters`
- `projects`
    - `buckets`
- `iac`
    - `iac-role-bindings`
- `global`
    - `iam-roles`
    - `projects`
        - `iam-roles`
        - `iam-role-bindings`

## How it works

1.  **Parses Configuration**: Reads the provided YAML file.
2.  **Iterates Resources**: Traverses the configuration based on the defined `RESOURCE_TYPES` hierarchy.
3.  **Generates Values**: Constructs a temporary values YAML file for each resource found.
4.  **Executes Helm**: Calls the Helm CLI with the specified action (e.g., `helm template ...`) targeting the corresponding chart (e.g., `../../charts/gdc-<resource_type>`).