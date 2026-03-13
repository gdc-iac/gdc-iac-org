# gdc-standard-clusters-rbac

A Helm chart for managing RBAC (RoleBindings and ClusterRoleBindings) in standard clusters.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-rbac ./gdc-standard-clusters-rbac -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `roleBindings` | List of RoleBinding resources to apply to specific namespaces. | `[]` | No |
| `clusterRoleBindings` | List of ClusterRoleBinding resources to apply globally within the cluster. | `[]` | No |

## Example Configuration (Optional)

```yaml
roleBindings:
  - name: developer-binding
    namespace: app-namespace
    roleName: developer-role
    roleKind: Role
    subjects:
      - kind: User
        name: fop-alice@example.com
        apiGroup: rbac.authorization.k8s.io
```
