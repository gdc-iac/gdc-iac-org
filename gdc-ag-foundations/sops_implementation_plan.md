# SOPS & Helm-Secrets Integration Guide for GDC Air-Gapped Landing Zones

This document outlines the architecture and step-by-step implementation plan to integrate **Mozilla SOPS** (Secrets Operations) and **helm-secrets** into the GDC AG Foundations codebase. This guarantees that sensitive credentials (database passwords, VM SSH private keys, S3 backup credentials) are encrypted at rest in Git and decrypted dynamically on the fly during Helmfile orchestrations.

---

## Architecture Overview

In an air-gapped GDC Hosted environment, external cloud KMS providers (such as AWS KMS or GCP Cloud KMS) are usually inaccessible. To achieve robust secret management in these zones, we leverage **Age** (a simple, modern alternative to PGP) or **PGP keys** stored securely on the operator's bastion hosts or CI/CD runtimes.

```mermaid
graph TD
    Git[Git Repository: Encrypted secrets.yaml] -->|git pull| Bastion[Bastion Host / CI Runner]
    AgeKey[Age Private Key / PGP Private Key] -->|Decryption Key| Bastion
    Bastion -->|helmfile apply| Helmfile[Helmfile & helm-secrets]
    Helmfile -->|Dynamic Decryption| Plaintext[Plaintext Values in Memory]
    Plaintext -->|gdc-dbs / gdc-vms Chart| K8s[GDC Kubernetes Secrets]
```

---

## Step-by-Step Integration Plan

### Phase 1: Tooling Installation
To enable decryption on the runtimes, the following binaries must be present on bastions or CI/CD agents:

1. **Mozilla SOPS CLI**:
   ```bash
   curl -LO https://github.com/getsops/sops/releases/download/v3.8.1/sops-v3.8.1.linux.amd64
   sudo mv sops-v3.8.1.linux.amd64 /usr/local/bin/sops
   sudo chmod +x /usr/local/bin/sops
   ```
2. **Helm Secrets Plugin**:
   ```bash
   helm plugin install https://github.com/jkroepke/helm-secrets --version v4.6.0
   ```

---

### Phase 2: Declaring Secrets in Helmfile

We define a central environment-specific `secrets.yaml` that is automatically decrypted by `helm-secrets` when Helmfile runs.

#### 1. Update `bases/environments.yaml.gotmpl`:
We add a `secrets` section to the environment definition. Helmfile will decrypt these files using SOPS and merge the values:

```yaml
environments:
  dev:
    values:
      - bases/environments/dev/globals.yaml
      - bases/environments/dev/iac.yaml
      - bases/environments/dev/tenants-org-1.yaml
      - bases/environments/dev/tenants-org-2.yaml
    secrets:
      - bases/environments/dev/secrets.yaml   # <--- SOPS Encrypted File
```

---

### Phase 3: Database Secret Auto-Injection

By leveraging our template-level dynamic defaulting architecture, we can keep the tenant files (`tenants-org-2.yaml`) completely free of plain-text database passwords.

#### 1. Simplified Tenant Config (`tenants-org-2.yaml`):
```yaml
projects:
  - name: "team2-prj"
    resources:
      dbs:
        alloydbomni:
          enabled: true
          clusterName: lts-ado-cluster
          version: "15"
          cpu: 2
          memory: 4Gi
          dataDiskSize: 10Gi
          # base64EncodedPassword OMITTED entirely for security
```

#### 2. Create `bases/environments/dev/secrets.yaml` (Encrypted via SOPS):
```yaml
# This file is fully encrypted using SOPS.
# Decrypted representation:
dbs_org_2_team2_prj_password: "SuperSecureProductionPassword123!"
```

#### 3. Dynamic Injection in `releases/2-resources/dbs.yaml.gotmpl`:
The release template dynamically reads the decrypted secret value and injects the base64-encoded version on the fly:

```yaml
releases:
  {{- range $tenantName, $tenantConfig := $envData.gdc_tenants }}
    {{- range $project := $tenantConfig.global.projects }}
      {{- if and $project.resources (hasKey $project.resources "dbs") }}
        {{- $dbs := $project.resources.dbs }}
        {{- if and (hasKey $dbs "alloydbomni") (not (hasKey $dbs.alloydbomni "base64EncodedPassword")) }}
          {{- $secretKey := printf "dbs_%s_%s_password" (replace "-" "_" $tenantName) (replace "-" "_" $project.name) }}
          {{- $password := $vals | get $secretKey "default-fallback-password" }}
          {{- $_ := set $dbs.alloydbomni "base64EncodedPassword" ($password | b64enc) }}
        {{- end }}
      - name: {{ $project.name }}-dbs
        chart: {{ $vals | get "gdc_dbs_chart_path" "../../charts/gdc-dbs" }}
        inherit:
          - template: db-template
        values:
          - {{ $dbs | toJson }}
          - namespace: {{ $project.name }}
      {{- end }}
    {{- end }}
  {{- end }}
```

---

### Phase 4: VM SSH Key & Backup Credentials Auto-Injection

This same dynamic injection pattern applies cleanly to sensitive VM credentials:

#### 1. Secure SSH Keys for VM Provisioning:
Instead of committing public/private SSH key blocks inside plain-text config files, we define them in `secrets.yaml`:
```yaml
vms_org_1_mellon_prj_ssh_key: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ..."
```

#### 2. Secure VM Backup S3 Credentials:
For S3 backup access, we dynamically generate a Kubernetes secret from the decrypted SOPS configuration inside `releases/2-resources/backup-repositories.yaml.gotmpl`:
```yaml
# Decrypted secrets.yaml
backup_s3_access_key: "AKIAIOSFODNN7EXAMPLE"
backup_s3_secret_key: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

Inside `backup-repositories.yaml.gotmpl`, these are securely mapped into the standard `secretReference`:
```yaml
        values:
          - s3_credentials:
              access_key: {{ $vals.backup_s3_access_key | quote }}
              secret_key: {{ $vals.backup_s3_secret_key | quote }}
```

---

## Advantages of this Implementation Plan
1. **Zero Secret Leakage**: No plaintext passwords or SSH keys are ever committed to Git.
2. **Clean Tenant Configs**: Configuration values files remain lightweight and declarative.
3. **Standardized Conventions**: Passwords and keys are mapped cleanly using predictable conventions (e.g., `<resource>_<tenant>_<project>_key`).
4. **Seamless Integration**: Relies on the official `helm-secrets` plugin and native Helmfile decryption mechanisms.

---

## Leveraging Native GDCag KMS

We can absolutely leverage GDC Hosted's native Key Management Service (KMS) to drive SOPS encryption/decryption natively inside your partition, eliminating the need to distribute and rotate local `Age` or `PGP` keys on production runners and operator bastions.

### 1. SOPS Key Specification
Because GDCag exposes APIs fully compatible with standard Google Cloud KMS, keys are declared in `.sops.yaml` using standard `gcp-kms` URI schemes pointing to your GDC local project and key ring:
```yaml
# .sops.yaml
creation_rules:
  - path_regex: bases/environments/.*secrets\.yaml$
    gcp_kms: gcp-kms://projects/<gdc-project-id>/locations/<gdc-region>/keyRings/<gdc-key-ring>/cryptoKeys/<gdc-key-name>
```

### 2. Redirecting SOPS to GDCag Private KMS Endpoints
By default, the Google Cloud client libraries compiled into SOPS target the public Google Cloud KMS API (`kms.googleapis.com`). 
To direct SOPS to resolve keys against GDCag's internal, private KMS endpoints inside the air-gapped boundary, export the standard SDK endpoint override environment variable on the bastion/runner before running Helmfile:

```bash
export CLOUDSDK_API_ENDPOINT_OVERRIDES_KMS="https://kms.<region>.<zone>.gdc.goog/v1/"
```

### 3. Transparent etcd Secrets Encryption (At-Rest Protection)
It is important to note that GDCag automatically protects resources inside `etcd` via standard **KMS Envelope Encryption**. 
Any credentials or passwords resolved by our templates and mapped into Kubernetes `Secret` manifests are automatically encrypted at rest by GDCag's internal KMS/HSM layer without requiring manual operator intervention.
