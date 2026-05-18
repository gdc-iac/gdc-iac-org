# GDC Managed DNS Helm Chart (`gdc-dns`)

This Helm chart automates the provisioning of **Managed DNS Zones** and **Resource Record Sets** inside Google Distributed Cloud (GDC) Hosted air-gapped environments. It uses GDC's official `networking.global.gdc.goog/v1` API group to define DNS resources.

---

## Configuration Parameters

The following table lists the configurable parameters of the `gdc-dns` chart and their default values:

| Parameter | Description | Default | Required |
| :--- | :--- | :--- | :--- |
| `namespace` | Target namespace where resources are deployed | `""` | **Yes** |
| `zone.name` | Unique identifier name of the Managed DNS Zone | `""` | **Yes** |
| `zone.dnsName` | The domain name for the DNS zone (must end with dot) | `""` | **Yes** |
| `zone.description` | Human readable description of the zone | `""` | No |
| `zone.visibility` | Visibility: `"private"` or `"public"` | `"private"` | **Yes** |
| `records` | Array list of resource record sets to map in the zone | `[]` | No |
| `records[].name` | Fully qualified domain name (FQDN) of the record | `""` | **Yes** |
| `records[].type` | Record L4 type: `"A"`, `"CNAME"`, `"TXT"`, etc. | `""` | **Yes** |
| `records[].ttlSeconds` | Time to live (TTL) in seconds for caching | `300` | No |
| `records[].rrData` | Array list of target IPs or hostnames for the record | `[]` | **Yes** |

---

## Usage Example

```yaml
# values.yaml
namespace: "my-project"
zone:
  name: "my-private-dns"
  dnsName: "example.goog."
  description: "Tenant Project Private Domain Name System"
  visibility: "private"

records:
  - name: "api.example.goog."
    type: "A"
    ttlSeconds: 600
    rrData:
      - "10.200.32.59"
  - name: "web.example.goog."
    type: "CNAME"
    rrData:
      - "api.example.goog."
```
