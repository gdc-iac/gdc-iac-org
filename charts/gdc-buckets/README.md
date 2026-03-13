# gdc-buckets

A Helm chart for managing storage buckets in Google Distributed Cloud Hosted environments.

## Prerequisites

- Helm 3.0+
- Access to the GDCH API cluster.

## Usage / Installation

```bash
helm install my-buckets ./gdc-buckets -f values.yaml
```

## Configuration Parameters

| Parameter | Description | Default | Required |
| --- | --- | --- | --- |
| `location` | The location/zone for the buckets. | `"zone1"` | No |
| `buckets` | A list of bucket configurations. | `[]` | No |
| `buckets[].name` | Name of the bucket. | `""` | **Yes** if buckets provided |
| `buckets[].namespace` | Namespace of the bucket. | `""` | **Yes** if buckets provided |
| `buckets[].description` | Description of the bucket. | `""` | No |
| `buckets[].storageClass` | Storage class for the bucket. | `"Standard"` | No |
| `buckets[].enableCorsPolicy` | Whether to enable CORS policy. | `"false"` | No |

## Example Configuration (Optional)

```yaml
location: "lux-central1-b"
buckets:
  - name: "lotus-bucket-1"
    namespace: "lotus-prj"
    description: "Primary storage for lotus app"
    storageClass: "Standard"
    enableCorsPolicy: "true"
```
