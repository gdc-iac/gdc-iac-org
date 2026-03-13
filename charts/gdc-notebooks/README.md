# gdc-notebooks

A Helm chart for deploying and managing Notebooks in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-notebooks ./gdc-notebooks -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `namespace` | Default namespace for notebooks. | `""` | No |
| `notebooks` | List of notebook configurations. | `[]` | No |
| `notebooks[].name` | Name of the notebook. | `""` | **Yes** if notebook provided |
| `notebooks[].nb_project` | Project name for the notebook. | `""` | No |
| `notebooks[].nb_jupyter_image` | Jupyter image to use. | `""` | No |
| `notebooks[].user_cluster_name` | Name of the user cluster. | `""` | No |
| `notebooks[].sidecars` | List of sidecar containers. | `[]` | No |

## Example Configuration (Optional)

```yaml
notebooks:
  - name: my-notebook
    nb_project: project-name
    nb_jupyter_image: jupyter-image:1.0
    user_cluster_name: my-user-cluster
```
