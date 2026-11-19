Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Vault Integration Guide for GDC Air-Gapped Blueprints

> **Version:** 1.2  
> **Related Guides:** `docs/implementation-guides/Solution-Reference-Implementation-Pattern-11-Resilient-Secret-Management-Vault.md` and `docs/operations/gitlab_vault_kms_installation_guide.md` (Sections 7–8).

This guide explains how to transition active GDC air-gapped (`GDCag`) architectural blueprints (such as Pattern 1, Pattern 6, Pattern 7, Pattern 10, Pattern 13/14, and `gdc_gemma_gw`) from static Kubernetes `Secret`s or plaintext environment variables to centralized, dynamically leased secrets served by **HashiCorp Vault (`p11-vault`)** auto-unsealed via **GDCag KMS (`kms.gdc.goog/v1` `AEADKey`)**.

---

## Architecture Overview

* **Secret Manager**: HashiCorp Vault (`http://vault.vault.svc.cluster.local:8200`), deployed via Pattern 11 (`p11-vault`) with 3-node Raft HA storage (`standard-rwo`) and hardware-backed GDCag KMS auto-unseal (`gdc-kms-bridge`).
* **Workload Authentication (`auth/kubernetes`)**: Vault validates projected Kubernetes `ServiceAccount` JWTs (`/var/run/secrets/kubernetes.io/serviceaccount/token`) against the User Cluster's Kubernetes `TokenReview` API (`443/6443` TCP).
* **CI/CD Authentication (`auth/jwt`)**: GitLab CI pipelines authenticate without static tokens using short-lived RS256 OIDC `id_tokens` verified against GitLab's in-cluster JWKS endpoint (`/oauth/discovery/keys`).
* **Delivery Patterns**:
  1. **Pattern A — Vault Agent Sidecar Injector (`vault-k8s:1.7.2`)**: Zero application code changes; renders secrets into an in-memory `tmpfs` volume (`/vault/secrets/*`).
  2. **Pattern B — Zero-Dependency Direct HTTP Client (`urllib.request`)**: Single-container pods fetch and renew secrets directly over HTTP using Python's standard library without external PyPI packages (`hvac`/`requests`).

---

## 1. Vault Preparation on the User Cluster

Ensure Pattern 11 (`p11-vault`) is initialized and unsealed (`Sealed: false`), and that `manifests/security/network-policy.yaml` is applied so cross-namespace pods can reach `vault:8200/TCP` (`namespaceSelector: {}`).

### 1.1 Enable KVv2 & Kubernetes Authentication

```bash
export NAMESPACE="vault"
export VAULT_ROOT_TOKEN=$(jq -r '.root_token' /path/to/vault-init.json)

kubectl -n "${NAMESPACE}" exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  vault secrets enable -path=secret kv-v2 || true
  vault auth enable kubernetes || true
  vault write auth/kubernetes/config \
    kubernetes_host="https://${KUBERNETES_PORT_443_TCP_ADDR}:443"
'
```

### 1.2 Create Least-Privilege Policies & Seed Secrets

Create isolated KVv2 paths and read-only policies per blueprint:

```bash
kubectl -n "${NAMESPACE}" exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  # Pattern 1 (3-Tier Web Application)
  vault policy write p1-db-policy - <<EOF
path "secret/data/p1/database" { capabilities = ["read"] }
path "secret/metadata/p1/database" { capabilities = ["read", "list"] }
EOF
  vault kv put secret/p1/database \
    POSTGRES_USER="app_user" \
    POSTGRES_PASSWORD="<replace-with-strong-db-password>"

  # Pattern 6 (Resilient RAG Agent)
  vault policy write p6-rag-policy - <<EOF
path "secret/data/p6/datastores" { capabilities = ["read"] }
path "secret/metadata/p6/datastores" { capabilities = ["read", "list"] }
EOF
  vault kv put secret/p6/datastores \
    PG_PASS="<replace-with-rag-db-password>" \
    S3_SECRET_KEY="<replace-with-gdc-s3-secret>"

  # Gemma 4 Gateway / Pattern 10 Client Application
  vault policy write gemma-client-policy - <<EOF
path "secret/data/gemma/client" { capabilities = ["read"] }
path "secret/metadata/gemma/client" { capabilities = ["read", "list"] }
EOF
  vault kv put secret/gemma/client \
    DATABASE_URL="postgresql+asyncpg://gemma_user:<password>@gemini-db:5432/gemmadb"
'
```

### 1.3 Bind Tenant Kubernetes ServiceAccounts to Vault Roles

```bash
kubectl -n "${NAMESPACE}" exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  vault write auth/kubernetes/role/p1-backend-role \
    bound_service_account_names="p1-backend-sa" \
    bound_service_account_namespaces="p1-webapp" \
    policies="p1-db-policy" \
    ttl="1h" max_ttl="24h"

  vault write auth/kubernetes/role/p6-rag-role \
    bound_service_account_names="rag-sa" \
    bound_service_account_namespaces="p6-rag" \
    policies="p6-rag-policy" \
    ttl="1h" max_ttl="24h"

  vault write auth/kubernetes/role/gemma-client-role \
    bound_service_account_names="gemma-client-sa" \
    bound_service_account_namespaces="gemma-inference" \
    policies="gemma-client-policy" \
    ttl="1h" max_ttl="24h"
'
```

---

## 2. Consuming Secrets in Blueprint Workloads

### Pattern A: Zero-Code Vault Agent Sidecar Injection

Ensure the application namespace has a `harbor-creds` pull secret attached to its `ServiceAccount` so the injected `vault-agent` container (`${PROJECT_HARBOR}/iac/vault:1.15.0`) pulls cleanly on GDCag:

```bash
kubectl -n p6-rag patch serviceaccount rag-sa \
  -p '{"imagePullSecrets": [{"name": "harbor-creds"}]}'
```

Annotate the `Deployment` pod template (for example, `p6-resilient-rag-agent/manifests/apps/query-service.yaml`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: query-service
  namespace: p6-rag
spec:
  template:
    metadata:
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "p6-rag-role"
        vault.hashicorp.com/agent-pre-populate-only: "false"
        vault.hashicorp.com/agent-inject-secret-api-config.env: "secret/data/p6/datastores"
        vault.hashicorp.com/agent-inject-template-api-config.env: |
          {{- with secret "secret/data/p6/datastores" -}}
          export DB_PASSWORD="{{ .Data.data.PG_PASS }}"
          export AWS_SECRET_ACCESS_KEY="{{ .Data.data.S3_SECRET_KEY }}"
          {{- end }}
    spec:
      serviceAccountName: rag-sa
      containers:
        - name: rag-api
          command: ["/bin/sh", "-ec"]
          args:
            - |
              . /vault/secrets/api-config.env
              exec uvicorn main:app --host 0.0.0.0 --port 8000
```

### Pattern B: Zero-Dependency Python `urllib.request` Client (No Sidecar)

For air-gapped Python microservices that prefer a `1/1` single-container pod without external SDK packages:

```python
import json
import os
import urllib.request

def fetch_vault_kv2(secret_path: str, role: str, vault_addr: str = "http://vault.vault.svc.cluster.local:8200") -> dict:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r", encoding="utf-8") as f:
        jwt = f.read().strip()
    login_req = urllib.request.Request(
        f"{vault_addr.rstrip('/')}/v1/auth/kubernetes/login",
        data=json.dumps({"role": role, "jwt": jwt}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login_req, timeout=10) as resp:
        client_token = json.loads(resp.read().decode("utf-8"))["auth"]["client_token"]

    kv_req = urllib.request.Request(
        f"{vault_addr.rstrip('/')}/v1/secret/data/{secret_path.lstrip('/')}",
        headers={"X-Vault-Token": client_token},
        method="GET",
    )
    with urllib.request.urlopen(kv_req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))["data"]["data"]
```

---

## 3. Production Security Posture on GDCag

1. **Strict Role Isolation**: Never share a Vault Kubernetes Auth role across patterns or namespaces (`p1-backend-role` cannot read `secret/data/p6/*`).
2. **In-Memory Secret Delivery (`tmpfs`)**: Vault Agent Injector mounts `/vault/secrets/` using `emptyDir.medium: Memory`, ensuring decrypted credentials never touch node persistent disks.
3. **Hardware-Backed Root of Trust**: Vault's master encryption key remains wrapped at rest by the Zonal GDCag KMS `AEADKey` (`namespaces/<project>/aeadKeys/vault-unseal-key`).
