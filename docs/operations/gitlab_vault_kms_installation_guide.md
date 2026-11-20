Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# GitLab & HashiCorp Vault Installation Guide with GDCag KMS Auto-Unseal

> **Document ID:** `OPS-GUIDE-GITLAB-VAULT-KMS`  
> **Version:** 1.1  
> **Target Environment:** Google Distributed Cloud air-gapped (version validated: `v1.16.2`) - Organization `org-12345` (`zone1`)  
> **Target Project & Cluster:** Project `iac-root` / User Cluster `iac-root-2ad0c4dd` (`argocd-cluster`)  
> **Related Patterns & Charts:** [Pattern 11 (`p11-vault`)](../../blueprints/patterns/p11-vault/README.md), [`charts/gdc-dbs`](../../charts/gdc-dbs/README.md), and [SOPS & Helm-Secrets Integration](../../foundations/sops_implementation_plan.md)

---

## Table of Contents

<!-- TOC_START -->
* [1. Overview & Architecture](#1-overview--architecture)
  * [1.1 Architectural Highlights](#11-architectural-highlights)
  * [1.2 Architecture Diagram](#12-architecture-diagram)
  * [1.3 Target Environment Reference](#13-target-environment-reference)
* [2. Prerequisites & Official IAM Authentication](#2-prerequisites--official-iam-authentication)
  * [2.1 Workstation Binary Path & `kubectl` TLS Handshake Requirement](#21-workstation-binary-path--kubectl-tls-handshake-requirement)
  * [2.2 Configure `gdcloud` CLI & Activate Official IAM Service Account](#22-configure-gdcloud-cli--activate-official-iam-service-account)
  * [2.3 Generate Official IAM Kubeconfigs for Global, Zonal, and User Clusters](#23-generate-official-iam-kubeconfigs-for-global-zonal-and-user-clusters)
* [3. Air-Gap Harbor Registry & Image/Chart Prerequisites](#3-air-gap-harbor-registry--imagechart-prerequisites)
  * [3.1 Complete Inventory of Required Harbor Artifacts](#31-complete-inventory-of-required-harbor-artifacts)
  * [3.2 Provisioning Managed Harbor & Mirroring Images via `tools/mirror-images/`](#32-provisioning-managed-harbor--mirroring-images-via-toolsmirror-images)
  * [3.3 Extracting & Seeding the Cloud-Native GitLab Chart (`gitlab-8.11.7.tgz`)](#33-extracting--seeding-the-cloud-native-gitlab-chart-gitlab-8117tgz)
* [4. Step-by-Step GDCag KMS & Database IAM Provisioning](#4-step-by-step-gdcag-kms--database-iam-provisioning)
  * [4.1 Step 1: Create `ProjectServiceAccount`, Bind KMS & Database IAM Roles (`global-api.kubeconfig`) & Verify DBS Backup Repository](#41-step-1-create-projectserviceaccount-bind-kms--database-iam-roles-global-apikubeconfig--verify-dbs-backup-repository)
  * [4.2 Step 2: Provision the `AEADKey` on the Zone Management API (`zone-admin.kubeconfig`)](#42-step-2-provision-the-aeadkey-on-the-zone-management-api-zone-adminkubeconfig)
  * [4.3 Step 3: Verify `AEADKey` Readiness & Test Live Encryption/Decryption via `gdcloud kms`](#43-step-3-verify-aeadkey-readiness--test-live-encryptiondecryption-via-gdcloud-kms)
* [5. Step-by-Step HashiCorp Vault Installation & Automatic Unsealing via GDCag KMS](#5-step-by-step-hashicorp-vault-installation--automatic-unsealing-via-gdcag-kms)
  * [5.1 How the `gdc-kms-bridge` Sidecar Bridges Vault `seal "gcpckms"` to GDCag KMS](#51-how-the-gdc-kms-bridge-sidecar-bridges-vault-seal-gcpckms-to-gdcag-kms)
  * [5.2 Step 1: Create the `vault` Namespace & Secrets on the User Cluster](#52-step-1-create-the-vault-namespace--secrets-on-the-user-cluster)
  * [5.3 Step 2: Create the Vault Helm Values (`vault-values.yaml` - Option A: Integrated Raft Storage Default)](#53-step-2-create-the-vault-helm-values-vault-valuesyaml---option-a-integrated-raft-storage-default)
  * [5.4 Step 3: Deploy, Initialize & Verify Automatic Unsealing via GDCag KMS](#54-step-3-deploy-initialize--verify-automatic-unsealing-via-gdcag-kms)
  * [5.5 Step 4: Apply User Cluster Vault `NetworkPolicy` (`5432/TCP` Managed `DBCluster` Egress)](#55-step-4-apply-user-cluster-vault-networkpolicy-5432tcp-managed-dbcluster-egress)
  * [5.6 Alternative Architecture (Option B): Managed PostgreSQL `DBCluster` Storage Backend](#56-alternative-architecture-option-b-managed-postgresql-dbcluster-storage-backend)
* [6. Step-by-Step GitLab 17.11.7 Installation](#6-step-by-step-gitlab-17117-installation)
  * [6.1 Key Air-Gap & Managed Persistence Architecture](#61-key-air-gap--managed-persistence-architecture)
  * [6.2 Step 1: Provision Zonal Managed PostgreSQL 15 (`gitlab-db`) & `BackupPlan` (`ZONE_KUBECONFIG`)](#62-step-1-provision-zonal-managed-postgresql-15-gitlab-db--backupplan-zone_kubeconfig)
  * [6.3 Step 2: Bootstrap User Cluster Namespace, TLS CA, `NetworkPolicy` & `gitlabhq_production` Extensions (`USER_CLUSTER_KUBECONFIG`)](#63-step-2-bootstrap-user-cluster-namespace-tls-ca-networkpolicy--gitlabhq_production-extensions-user_cluster_kubeconfig)
  * [6.4 Step 3: Create GitLab 17.11.7 Helm Values (`gitlab-values.yaml`)](#64-step-3-create-gitlab-17117-helm-values-gitlab-valuesyaml)
  * [6.5 Step 4: Install GitLab 17.11.7 & Seed CI OIDC Signing Keys](#65-step-4-install-gitlab-17117--seed-ci-oidc-signing-keys)
  * [6.6 Step 5: Verify GitLab Pods, PVCs, Services, Ingress & API Endpoints](#66-step-5-verify-gitlab-pods-pvcs-services-ingress--api-endpoints)
* [7. GitLab & HashiCorp Vault Integration](#7-gitlab--hashicorp-vault-integration)
  * [7.1 Step 1: Enable KVv2 Secrets Engine, Write Secrets & Create Vault Policy](#71-step-1-enable-kvv2-secrets-engine-write-secrets--create-vault-policy)
  * [7.2 Step 2: Configure Vault JWT Authentication (`auth/jwt`) for GitLab CI Pipelines](#72-step-2-configure-vault-jwt-authentication-authjwt-for-gitlab-ci-pipelines)
  * [7.3 Step 3: Configure Vault Kubernetes Auth (`auth/kubernetes`) & Sidecar Injection](#73-step-3-configure-vault-kubernetes-auth-authkubernetes--sidecar-injection)
* [8. Consuming Vault Secrets in Applications & GitLab](#8-consuming-vault-secrets-in-applications--gitlab)
  * [8.1 Onboarding an Application Namespace & ServiceAccount in Vault](#81-onboarding-an-application-namespace--serviceaccount-in-vault)
  * [8.2 Pattern A: Zero-Code Consumption via Vault Agent Sidecar Injector](#82-pattern-a-zero-code-consumption-via-vault-agent-sidecar-injector)
  * [8.3 Pattern B: Direct In-Application Consumption via Vault HTTP API / SDK (No Sidecar)](#83-pattern-b-direct-in-application-consumption-via-vault-http-api--sdk-no-sidecar)
  * [8.4 Pattern C: Consuming Vault Secrets in GitLab CI/CD Pipelines](#84-pattern-c-consuming-vault-secrets-in-gitlab-cicd-pipelines)
  * [8.5 Pattern D: Dynamic PostgreSQL Credentials via Vault `database/` Secrets Engine](#85-pattern-d-dynamic-postgresql-credentials-via-vault-database-secrets-engine)
* [9. End-to-End Verification & Troubleshooting](#9-end-to-end-verification--troubleshooting)
  * [9.1 End-to-End Cross-Namespace & Managed `DBCluster` TLS Verification](#91-end-to-end-cross-namespace--managed-dbcluster-tls-verification)
  * [9.2 Troubleshooting Common Issues](#92-troubleshooting-common-issues)
<!-- TOC_END -->

---

## 1. Overview & Architecture

This operational guide provides end-to-end instructions for deploying **GitLab 17.11.7 (`gitlab-8.11.7`)** backed by **GDCag Managed PostgreSQL 15 (`postgresql.dbadmin.gdc.goog/v1` `DBCluster`)** and **HashiCorp Vault 1.15.0 (`vault-0.32.0`)** with **automatic cryptographic unsealing via Google Distributed Cloud air-gapped (GDCag) Key Management Service (KMS)** in organization `org-12345` (`zone1`), project `iac-root`.

### 1.1 Architectural Highlights

* **Official IAM Control-Plane & Data-Plane Access**: All operations across the Global API (`global-api`), Zone Management API (`org-12345-admin`), KMS Data Plane (`kms.org-12345.zone1.google.gdch.test`), and User Cluster (`iac-root-2ad0c4dd`) authenticate strictly via official `gdcloud` CLI workflows, `gdcloud-k8s-auth-plugin`, and project IAM Service Accounts (`iac001-sa` with `kms-*` and `project-db-admin` roles, plus `vault-kms-sa`).
* **Zonal HA Managed PostgreSQL (`DBCluster` + `BackupPlan`)**: GitLab's relational database tier runs on the GDCag Database Service (`postgresql.dbadmin.gdc.goog/v1` `DBCluster` `gitlab-db`, PostgreSQL `"15"`, `enableHighAvailability: true`, `enableAutoFailover: true`) with automated daily `BackupPlan` backups and verified TLS (`Secret/dbs-certificates`), eliminating single-pod database SPOFs on the User Cluster. HashiCorp Vault defaults to integrated Raft storage on `standard-rwo` (**Option A**) so no external database sits on the KMS auto-unseal critical path, while also supporting a Managed PostgreSQL `DBCluster` storage backend (**Option B**, `storage "postgresql"`) and short-lived application database leases via the **Database Secrets Engine (`database/`)**.
* **Hardware-Backed GDCag KMS Auto-Unseal**: HashiCorp Vault's master encryption key is wrapped by an `AES_256_GCM` symmetric `AEADKey` (`namespaces/iac-root/aeadKeys/vault-unseal-key`) hosted in the GDCag KMS enclave. A lightweight, zero-dependency Go native sidecar (`gdc-kms-bridge`) translates Vault's `seal "gcpckms"` gRPC calls (`/google.cloud.kms.v1.KeyManagementService/{Encrypt,Decrypt}`) into GDCag KMS gRPC operations (`/goog.gdc.kms.v1.CryptoOperationsService/{Encrypt,Decrypt}`) authenticated via GDC STS token exchange (`urn:k8s:params:oauth:token-type:serviceaccount`).
* **Air-Gapped Harbor Artifact Resolution**: All Helm charts and OCI container images are pulled exclusively from the partition's internal Harbor registries (`harbor.org-12345.zone1.google.gdch.test` and `harbor001-iac-root.org-12345.zone1.google.gdch.test`), reusing the mirrored `gitlab-toolbox-ee` image for pre-install PostgreSQL extension bootstrap with zero additional images.
* **Multi-Pattern Secret Delivery**:
  1. **GitLab CI OIDC / JWT Authentication (`auth/jwt`)**: Validates GitLab CI job ID tokens (`CI_JOB_JWT_V2` / `id_tokens`) against GitLab's in-cluster JWKS endpoint (`/oauth/discovery/keys`) with project-scoped claim enforcement (`bound_claims: {"project_id": "1"}`).
  2. **Kubernetes ServiceAccount Authentication (`auth/kubernetes`) & Vault Agent Sidecar Injector (`vault-k8s:1.7.2`)**: Authenticates workload pods via Kubernetes `TokenReview` and injects static KVv2 secrets (`secret/data/*`) or dynamic PostgreSQL leases (`database/creds/*`) into in-memory `tmpfs` volumes (`/vault/secrets/*`) or direct HTTP clients.

### 1.2 Architecture Diagram

```text
[ GDCag Partition: org-12345 (zone1) | Project: iac-root ]
========================================================================================================

  ┌──────────────────────────────────────┐          ┌────────────────────────────────────────────────┐
  │   Global API Server (global-api)     │          │   Zone Management API (org-12345-admin)        │
  │  https://global-api.org-12345...     │          │  https://management-kube.apiserver...          │
  │                                      │          │                                                │
  │  • ProjectServiceAccount: iac001-sa  │          │  • kms.gdc.goog/v1 AEADKey: vault-unseal-key   │
  │  • ProjectServiceAccount:            │          │    (Namespace: iac-root, Alg: AES_256_GCM)     │
  │    vault-kms-sa                      │          │  • postgresql.dbadmin.gdc.goog/v1 DBCluster:   │
  │  • IAMRoleBindings:                  │          │    gitlab-db (PG 15 Zonal HA + BackupPlan)     │
  │    kms-admin, kms-developer,         │          │    [+ optional vault-db for Vault Option B]    │
  │    kms-viewer, project-db-admin      │          │  • Secret/dbs-certificates (TLS Root CAs)      │
  └──────────────────┬───────────────────┘          │  • HarborInstance: harbor001                   │
                     │                              └───────┬───────────────────────────▲────────────┘
                     │ STS Token Exchange (ES256)           │                           │
                     ▼                                      ▼                           │
            ┌────────────────────────────────────────────────────────┐                  │
            │   GDCag KMS Data Plane & STS Endpoint                  │                  │
            │  • https://kms.org-12345.zone1...                      │                  │
            │    (/goog.gdc.kms.v1.CryptoOperationsService)          │                  │
            │  • https://service-accounts.org-12345...               │                  │
            └───────────────────────────────▲────────────────────────┘                  │
                                            │                                           │
                                 gRPC Encrypt / Decrypt                      5432/TCP Verified TLS
                                 (STS-Bearer Token)                          (gitlabhq_production &
                                            │                                 optional vault / app DB)
  ┌─────────────────────────────────────────┴───────────────────────────────────────────┴────────────┐
  │ User Cluster: iac-root-2ad0c4dd (CR: argocd-cluster | StorageClass: standard-rwo)                │
  │                                                                                                  │
  │  ┌─────────────────────────────────────────────┐  ┌───────────────────────────────────────────┐  │
  │  │ Namespace: vault                            │  │ Namespace: gitlab                         │  │
  │  │                                             │  │                                           │  │
  │  │  ┌───────────────────────────────────────┐  │  │  • gitlab-webservice-default (2/2)        │  │
  │  │  │ Pod: vault-0 (2/2 Running)            │  │  │    └─ JWKS: /oauth/discovery/keys         │  │
  │  │  │  ├─ Container: vault (v1.15.0)        │◄─┼──┼─────── JWT Auth (auth/jwt) ───────────────┤  │
  │  │  │  │   Option A: Raft (default)         │  │  │    └─ API: /api/v4/version (17.11.7-ee)   │  │
  │  │  │  │   Option B: PG DBCluster (5432/TCP)│  │  │  • gitlab-toolbox / sidekiq /             │  │
  │  │  │  │   seal "gcpckms" -> 127.0.0.1:443  │  │  │    gitlab-shell / kas                     │  │
  │  │  │  └─ Sidecar: gdc-kms-bridge (v1.0.0)  │  │  │  • gitaly & redis-master (standard-rwo)   │  │
  │  │  │      Translates gcpckms -> GDCag KMS  │  │  │  • Outbound 5432/TCP TLS -> gitlab-db     │  │
  │  │  └───────────────────────────────────────┘  │  │  • gitlab-nginx-ingress-controller        │  │
  │  │                                             │  │    (LoadBalancer IP: 10.136.68.48)        │  │
  │  │  ┌───────────────────────────────────────┐  │  │                                           │  │
  │  │  │ Pod: vault-agent-injector (1/1)       │◄─┼──┼─────── K8s Auth & Mutating Webhook ───────┘  │
  │  │  │  Mutating Webhook (vault-k8s:1.7.2)   │  │  │        (Injects /vault/secrets/*)            │
  │  │  └───────────────────────────────────────┘  │  └───────────────────────────────────────────┘  │
  │  └─────────────────────────────────────────────┘                                                 │
  └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Target Environment Reference

| Component / Parameter | Verified Value |
| :--- | :--- |
| **GDCag Version** | `1.16.2` |
| **Organization & Zone** | `org-12345` / `zone1` (`org-12345.zone1.google.gdch.test`) |
| **Console URL** | `https://console.org-12345.zone1.google.gdch.test` |
| **Tenant Project** | `iac-root` |
| **Global API Endpoint** | `https://global-api.org-12345.zone1.google.gdch.test` |
| **Zone Management API Endpoint** | `https://management-kube.apiserver.org-12345.zone1.google.gdch.test` |
| **User Cluster (`argocd-cluster`)** | `iac-root-2ad0c4dd` (`https://iac-root-2ad0c4dd-kube.apiserver.org-12345.zone1.google.gdch.test`) |
| **GDCag KMS Endpoint** | `https://kms.org-12345.zone1.google.gdch.test` |
| **GDCag STS Endpoint** | `https://service-accounts.org-12345.google.gdch.test/authenticate` |
| **System Harbor Registry** | `harbor.org-12345.zone1.google.gdch.test` |
| **Project Managed Harbor Registry** | `harbor001-iac-root.org-12345.zone1.google.gdch.test` |
| **Default Block StorageClass** | `standard-rwo` (`csi.kubevirt.io`, `ReadWriteOnce`, `allowVolumeExpansion: true`) |
| **GitLab Managed PostgreSQL (`DBCluster`)** | `gitlab-db` (`postgresql.dbadmin.gdc.goog/v1`, PostgreSQL `"15"`, Zonal HA + Auto-Failover, `4 CPU / 16Gi / 50Gi DataDisk` + daily `BackupPlan`; GitLab `17.11` supports PG `14–16`, whereas GitLab `18.0+` requires PG `16+`) |
| **Zonal DBS Backup Repository** | `BackupRepository/dbs-backup-repository` (Zone Management API, prerequisite for `BackupPlan`) |
| **GitLab FQDN & LoadBalancer IP** | `https://gitlab.org-12345.zone1.google.gdch.test` (`10.136.68.48`) |
| **Vault Internal Service URL** | `http://vault.vault.svc.cluster.local:8200` |

---

## 2. Prerequisites & Official IAM Authentication

> [!IMPORTANT]
> **STRICT IAM COMPLIANCE:** Authenticate using `gdcloud` CLI, `gdcloud-k8s-auth-plugin`, and project-scoped `ProjectServiceAccount` credentials (`iac001-sa` or user OIDC login) as implemented in `tools/bootstrap/authenticate.sh`. 

### 2.1 Workstation Binary Path & `kubectl` TLS Handshake Requirement

On operator workstations running newer system `kubectl` builds (e.g., `/usr/bin/kubectl` compiled with Go `1.27+` / `v1.32–1.37`), direct `kubectl` connections through the GDCag Envoy ingress gateway can stall during the TLS handshake because the Envoy listener requires standard ALPN negotiation (`h2, http/1.1`) and standard ECDHE curves (`X25519`, `P-256`) rather than oversized post-quantum `X25519MLKEM768` ClientHello frames.

Always prepend the `gdcloud`-bundled `kubectl` (`v1.30.2-gke.1100`, BoringCrypto) and `gdcloud-k8s-auth-plugin` directories to your `PATH`, and set `GODEBUG=tlsmlkem=0` when invoking newer Go-based CLIs such as `helm`:

```bash
# Set the root path of the Google Distributed Cloud Hosted CLI installation
export GDCLOUD_CLI_PATH="${GDCLOUD_CLI_PATH:-/google/gdcloud}"

# Extract the official gdcloud-bundled kubectl binary if not already in ~/bin
mkdir -p "${HOME}/bin"
tar -xzf "${GDCLOUD_CLI_PATH}/bin/component_bundles/kubectl_linux_amd64_1.23.5.tar.gz" \
  -C "${HOME}/bin" --strip-components=1 bin/kubectl

# Prepend official gdcloud CLI, gdcloud-bundled kubectl, and auth plugin to PATH
export PATH="${HOME}/bin:${GDCLOUD_CLI_PATH}/bin:${PATH}"
export GODEBUG=tlsmlkem=0

# Verify binary versions
kubectl version --client
gdcloud version
helm version --short
```

**Verified Output:**
```text
Client Version: v1.30.2-gke.1100
Kustomize Version: v5.0.4-0.20230601165947-6ce0bf390ce3
Google Distributed Cloud Hosted CLI 1.16.2
v3.19.0+g3a960fd
```

### 2.2 Configure `gdcloud` CLI & Activate Official IAM Service Account

Configure the `gdcloud` CLI for the `org-12345` (`zone1`) organization and activate the official IaC Service Account (`iac001-sa` in project `iac-root`), following the conventions in `tools/bootstrap/config.sh.sample` and `tools/bootstrap/authenticate.sh`:

```bash
export SCRIPTS_DIR=$(readlink -e ./tools/bootstrap)
export ORG_NAME="org-12345"
export GDCH_ZONE="zone1"
export GDCH_DOMAIN="google.gdch.test"
export IAC_PROJECT="iac-root"
export IAC_SA="iac001-sa"
export USER_CLUSTER="iac-root-2ad0c4dd"

export KUBECONFIG_PATH="${SCRIPTS_DIR:?}/generated/kubeconfig"
export SECRETS_DIR="${SCRIPTS_DIR:?}/generated/secrets"
export GLOBAL_API_KUBECONFIG="${KUBECONFIG_PATH}/${IAC_PROJECT}-${IAC_SA}-global-api.kubeconfig"
export ZONE_KUBECONFIG="${KUBECONFIG_PATH}/${IAC_PROJECT}-${IAC_SA}-${GDCH_ZONE}.kubeconfig"
export USER_CLUSTER_KUBECONFIG="${KUBECONFIG_PATH}/${IAC_PROJECT}-${IAC_SA}-${GDCH_ZONE}-${USER_CLUSTER}.kubeconfig"
mkdir -p "${KUBECONFIG_PATH}" "${SECRETS_DIR}"

# 1. Configure organization console URL, project, and zone
gdcloud config set core/organization_console_url "https://console.${ORG_NAME}.${GDCH_ZONE}.${GDCH_DOMAIN}"
gdcloud config set core/project "${IAC_PROJECT}"
gdcloud config set core/zone "${GDCH_ZONE}"

# 2. Activate the official IAM Service Account
gdcloud auth activate-service-account --key-file="${SECRETS_DIR:?}/${IAC_SA:?}.json"
```

### 2.3 Generate Official IAM Kubeconfigs for Global, Zonal, and User Clusters

Generate the three official IAM kubeconfigs using `gdcloud clusters get-credentials` and verify identity via `kubectl auth whoami`:

```bash
# 1. Global API Kubeconfig (IAMRoleBindings, ProjectServiceAccounts, Projects)
rm -f "${GLOBAL_API_KUBECONFIG}"
gdcloud config set core/zone ""
KUBECONFIG="${GLOBAL_API_KUBECONFIG}" gdcloud clusters get-credentials global-api
kubectl --kubeconfig="${GLOBAL_API_KUBECONFIG}" auth whoami

# 2. Zone Management API Kubeconfig (KMS AEADKeys, PostgreSQL DBClusters & BackupPlans, HarborInstances, Clusters)
rm -f "${ZONE_KUBECONFIG}"
gdcloud config set core/zone "${GDCH_ZONE}"
KUBECONFIG="${ZONE_KUBECONFIG}" gdcloud clusters get-credentials "${ORG_NAME}-admin" --zone "${GDCH_ZONE}"
kubectl --kubeconfig="${ZONE_KUBECONFIG}" auth whoami

# 3. User Cluster Kubeconfig (Vault & GitLab Workloads)
rm -f "${USER_CLUSTER_KUBECONFIG}"
KUBECONFIG="${USER_CLUSTER_KUBECONFIG}" gdcloud clusters get-credentials "${USER_CLUSTER}" --zone "${GDCH_ZONE}"
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" auth whoami

# Set the User Cluster as the default KUBECONFIG for workload operations
export KUBECONFIG="${USER_CLUSTER_KUBECONFIG}"
```

**Verified Output (`kubectl auth whoami` across all three planes):**
```text
ATTRIBUTE                                           VALUE
Username                                            system:serviceaccount:iac-root:iac001-sa
Groups                                              [system:authenticated]
Extra: authentication.kubernetes.io/credential-id   [JTI=...]
```

---

## 3. Air-Gap Harbor Registry & Image/Chart Prerequisites

Two Harbor registries serve artifacts in the `org-12345` (`zone1`) environment. For full details on Managed Harbor provisioning, robot account authentication, and automated image mirroring workflows, refer to [`tools/mirror-images/`](../../tools/mirror-images/) ([`tools/mirror-images/README.md`](../../tools/mirror-images/README.md) and [`tools/mirror-images/mirror_images.py`](../../tools/mirror-images/mirror_images.py)).

### 3.1 Complete Inventory of Required Harbor Artifacts

| Component | Artifact Type | Sample Harbor URI |
| :--- | :--- | :--- |
| **Vault Helm Chart** | OCI Helm Chart | `oci://harbor.org-12345.zone1.google.gdch.test/gpc-system-helm-packages/vault` (`0.32.0`) |
| **Vault OSS Server & Agent** | Container Image | `harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault:1.15.0` |
| **Vault K8s Mutating Webhook** | Container Image | `harbor.org-12345.zone1.google.gdch.test/library/hashicorp/vault-k8s:1.7.2` |
| **GDCag KMS Auto-Unseal Bridge** | Container Image | `harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/gdc-kms-bridge:1.0.0` |
| **GitLab 17.11.7 Helm Chart** | OCI Helm Chart | `oci://harbor001-iac-root.org-12345.zone1.google.gdch.test/charts/gitlab` (`8.11.7`) |
| **GitLab CNG 17.11.7 Suite** | Container Images | `harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-*-17-11-7:v1.16.2-iac-1800e51e18` (`webservice-ee`, `workhorse-ee`, `sidekiq-ee`, `gitaly`, `gitlab-shell`, `gitlab-kas`, `gitlab-toolbox-ee` *(also reused for `psql` DB bootstrap)*, `gitlab-exporter`, `certificates`, `kubectl`, `gitlab-base`, `cfssl-self-sign`) |
| **GitLab Ingress Controller** | Container Image | `harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-cloud-native-mirror-images-ingress-nginx-controller-17-11-7:v1.16.2-iac-1800e51e18` |
| **GitLab Redis 17.11.7** | Container Image | `harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-bitnamilegacy-redis-17-11-7:v1.16.2-iac-1800e51e18` |
| **GDCag Database Service Chart** | Local Helm Chart | [`./charts/gdc-dbs`](../../charts/gdc-dbs/README.md) (`v0.2.0` - optional Helm wrapper for Zonal `DBCluster` + `BackupPlan` CRDs) |
| **Self-Managed PostgreSQL 17** *(Optional Lab Fallback Only)* | Container Image | `harbor.org-12345.zone1.google.gdch.test/library/tenable/postgres:17` *(Not used in production Managed `DBCluster` deployments; retained only for the optional stepping-stone lab fallback in Section 6.3)* |

### 3.2 Provisioning Managed Harbor & Mirroring Images via [`tools/mirror-images/`](../../tools/mirror-images/)

Follow the workflow in [`tools/mirror-images/`](../../tools/mirror-images/) to provision the Project Managed Harbor registry (`harbor001-iac-root.org-12345.zone1.google.gdch.test`). Mirror Container Images with [`tools/mirror-images/mirror_images.py`](../../tools/mirror-images/mirror_images.py):
   `mirror_images.py` extracts `image:` references from a Kubernetes YAML manifest (`--manifest`) or a plain-text image list (`--images-file`), strips the upstream registry/repository path to `<image_base>:<tag>`, and pushes to `${PROJECT_HARBOR}/iac/<image_base>:<tag>`. It supports both **Direct Mirroring** and **Two-Step Disconnected Air-Gap Mirroring**:

   ```bash
   export WORK_DIR="/tmp/gitlab-vault-artifacts"
   mkdir -p "${WORK_DIR}"

   cat <<'EOF' > "${WORK_DIR}/external_images.txt"
   hashicorp/vault:1.15.0
   alpine:latest
   EOF

   # Option A: Direct Mirroring (from a bastion with access to both source registry and Managed Harbor)
   ./tools/mirror-images/mirror_images.py \
     --images-file "${WORK_DIR}/external_images.txt" \
     --registry "${PROJECT_HARBOR}/iac"

   # Option B: Two-Step Disconnected Air-Gap Mirroring (Low-Side Export -> High-Side Import)
   # Step B1 (Low-Side / Internet-Connected Workstation): Pull and save .tar.gz archives + images.index
   ./tools/mirror-images/mirror_images.py \
     --images-file "${WORK_DIR}/external_images.txt" \
     --save-dir "${WORK_DIR}/offline-images"

   # Step B2 (High-Side / Air-Gapped GDCag Workstation): Load .tar.gz archives, re-tag, and push to Harbor
   ./tools/mirror-images/mirror_images.py \
     --load-dir "${WORK_DIR}/offline-images" \
     --registry "${PROJECT_HARBOR}/iac"
   ```
   *(You can also pass `--manifest <rendered-manifest.yaml>` to `mirror_images.py` to automatically discover and mirror all `image:` references from a rendered Helm template or Kubernetes manifest.)*

### 3.3 Extracting & Seeding the Cloud-Native GitLab Chart (`gitlab-8.11.7.tgz`)

In GDCag, the upstream Cloud-Native GitLab Helm chart (`gitlab-8.11.7.tgz`, appVersion `v17.11.6` / CNG `17.11.7`) is embedded inside the mirrored `gitlab-operator` image in System Harbor. To extract it and publish it to Project Harbor (`harbor001-iac-root`):

```bash
export SYSTEM_HARBOR="harbor.org-12345.zone1.google.gdch.test"
export PROJECT_HARBOR="harbor001-iac-root.org-12345.zone1.google.gdch.test"
export WORK_DIR="/tmp/gitlab-vault-artifacts"
mkdir -p "${WORK_DIR}/charts"

# 1. Pull the Vault 0.32.0 Helm chart from System Harbor
GODEBUG=tlsmlkem=0 helm pull "oci://${SYSTEM_HARBOR}/gpc-system-helm-packages/vault" \
  --version 0.32.0 --untar -d "${WORK_DIR}/charts"

# 2. Extract gitlab-8.11.7.tgz from the mirrored GitLab Operator image and push to Project Harbor
CID=$(docker create "${SYSTEM_HARBOR}/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-cloud-native-gitlab-operator-17-11-7:v1.16.2-iac-1800e51e18")
docker cp "${CID}:/charts/gitlab-8.11.7.tgz" "${WORK_DIR}/charts/gitlab-8.11.7.tgz"
docker rm -v "${CID}"

GODEBUG=tlsmlkem=0 helm push "${WORK_DIR}/charts/gitlab-8.11.7.tgz" \
  "oci://${PROJECT_HARBOR}/charts" --insecure-skip-tls-verify
```

---

## 4. Step-by-Step GDCag KMS & Database IAM Provisioning

> [!IMPORTANT]
> **GDCag v1.16.2 KMS Architecture Note (`AEADKey` vs. `KeyRing`):**
> In GDCag there is **no `KeyRing` CustomResourceDefinition**, and `gdcloud kms` does not use `key-rings create`. Instead, symmetric encryption keys are provisioned declaratively as `AEADKey` (`kms.gdc.goog/v1`) resources directly inside the project namespace (`iac-root`) on the **Zone Management API** (`zone-admin.kubeconfig`).
> On the KMS data plane (`https://kms.org-12345.zone1.google.gdch.test`), keys are addressed by the camelCase resource path `namespaces/<project>/aeadKeys/<key-name>` (e.g., `namespaces/iac-root/aeadKeys/vault-unseal-key`). Using lowercase `aeadkeys` will fail with `InvalidArgument: does not match expected format namespaces/<namespace>/aeadKeys/<name>`.

### 4.1 Step 1: Create `ProjectServiceAccount`, Bind KMS & Database IAM Roles (`global-api.kubeconfig`) & Verify DBS Backup Repository

Grant `kms-admin`, `kms-developer`, `kms-viewer`, and **`project-db-admin`** (required to provision `postgresql.dbadmin.gdc.goog/v1` `DBCluster` and `BackupPlan` resources) in project `iac-root` to `iac001-sa`, create a dedicated `vault-kms-sa` `ProjectServiceAccount` with `kms-developer` and `kms-viewer` privileges for Vault auto-unseal, and verify that the Zonal Database Service `BackupRepository` (`dbs-backup-repository`) is ready:

```bash
# 1. Create KMS and Database Service IAMRoleBindings for iac001-sa on the Global API server
cat <<'EOF' | kubectl --kubeconfig="${GLOBAL_API_KUBECONFIG}" apply -f -
apiVersion: iam.global.gdc.goog/v1
kind: IAMRoleBinding
metadata:
  name: iac001-sa--kms-admin
  namespace: iac-root
  labels:
    iam.global.gdc.goog/iam-role-name: kms-admin
spec:
  roleRef:
    apiGroup: iam.global.gdc.goog/v1
    kind: IAMRole
    name: kms-admin
  subjects:
  - kind: ServiceAccount
    name: iac001-sa
    namespace: iac-root
---
apiVersion: iam.global.gdc.goog/v1
kind: IAMRoleBinding
metadata:
  name: iac001-sa--kms-developer
  namespace: iac-root
  labels:
    iam.global.gdc.goog/iam-role-name: kms-developer
spec:
  roleRef:
    apiGroup: iam.global.gdc.goog/v1
    kind: IAMRole
    name: kms-developer
  subjects:
  - kind: ServiceAccount
    name: iac001-sa
    namespace: iac-root
---
apiVersion: iam.global.gdc.goog/v1
kind: IAMRoleBinding
metadata:
  name: iac001-sa--kms-viewer
  namespace: iac-root
  labels:
    iam.global.gdc.goog/iam-role-name: kms-viewer
spec:
  roleRef:
    apiGroup: iam.global.gdc.goog/v1
    kind: IAMRole
    name: kms-viewer
  subjects:
  - kind: ServiceAccount
    name: iac001-sa
    namespace: iac-root
---
apiVersion: iam.global.gdc.goog/v1
kind: IAMRoleBinding
metadata:
  name: iac001-sa--project-db-admin
  namespace: iac-root
  labels:
    iam.global.gdc.goog/iam-role-name: project-db-admin
spec:
  roleRef:
    apiGroup: iam.global.gdc.goog/v1
    kind: IAMRole
    name: project-db-admin
  subjects:
  - kind: ServiceAccount
    name: iac001-sa
    namespace: iac-root
EOF

# 2. Pre-flight check: verify Zonal DBS BackupRepository is Ready before creating BackupPlans
kubectl --kubeconfig="${ZONE_KUBECONFIG}" get backuprepository dbs-backup-repository || \
  echo "WARNING: dbs-backup-repository not found on ZONE_KUBECONFIG; ask Infrastructure Operator to configure DBS backup storage before applying BackupPlan resources."

# 3. Create the dedicated vault-kms-sa ProjectServiceAccount and export its credentials JSON
gdcloud iam service-accounts create vault-kms-sa --project=iac-root || true

# Export the GDCH login CA bundle and create the service account JSON key
kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret -n gpc-system TrustStore-root-ext \
  -o jsonpath='{.data.ca\.crt}' | base64 -d > "${WORK_DIR}/gdc-login-ca.crt" 2>/dev/null || \
  cp /etc/ssl/certs/ca-certificates.crt "${WORK_DIR}/gdc-login-ca.crt"

gdcloud iam service-accounts keys create "${WORK_DIR}/vault-kms-sa.json" \
  --iam-account=vault-kms-sa \
  --project=iac-root \
  --ca-cert-path="${WORK_DIR}/gdc-login-ca.crt"

# 4. Bind kms-developer (Encrypt/Decrypt) and kms-viewer to vault-kms-sa
gdcloud projects add-iam-policy-binding iac-root \
  --role=roles/kms-developer \
  --member="serviceAccount:iac-root:vault-kms-sa"

gdcloud projects add-iam-policy-binding iac-root \
  --role=roles/kms-viewer \
  --member="serviceAccount:iac-root:vault-kms-sa"
```

### 4.2 Step 2: Provision the `AEADKey` on the Zone Management API (`zone-admin.kubeconfig`)

Apply the `AEADKey` resource in namespace `iac-root` on the Zone Management API server:

```bash
cat <<'EOF' | kubectl --kubeconfig="${ZONE_KUBECONFIG}" apply -f -
apiVersion: kms.gdc.goog/v1
kind: AEADKey
metadata:
  name: vault-unseal-key
  namespace: iac-root
spec:
  algorithm: AES_256_GCM
EOF
```

### 4.3 Step 3: Verify `AEADKey` Readiness & Test Live Encryption/Decryption via `gdcloud kms`

Verify that the `AEADKey` controller reconciles the key to `Ready=True` and test round-trip encryption and decryption through the GDCag KMS data plane:

```bash
# 1. Check AEADKey status on the Zone Management API
kubectl --kubeconfig="${ZONE_KUBECONFIG}" get aeadkey vault-unseal-key -n iac-root -o yaml

# 2. Test live encrypt/decrypt via gdcloud kms keys
gdcloud config set auth/login_config_cert_path "${WORK_DIR}/gdc-login-ca.crt"
echo -n "gdc-vault-kms-test" > "${WORK_DIR}/plain.txt"

gdcloud kms keys encrypt namespaces/iac-root/aeadKeys/vault-unseal-key \
  --plaintext-file="${WORK_DIR}/plain.txt" \
  --ciphertext-file="${WORK_DIR}/cipher.enc"

gdcloud kms keys decrypt namespaces/iac-root/aeadKeys/vault-unseal-key \
  --ciphertext-file="${WORK_DIR}/cipher.enc" \
  --plaintext-file="${WORK_DIR}/decrypted.txt"

cat "${WORK_DIR}/decrypted.txt" && echo ""
```

**Verified Output:**
```yaml
apiVersion: kms.gdc.goog/v1
kind: AEADKey
metadata:
  name: vault-unseal-key
  namespace: iac-root
spec:
  algorithm: AES_256_GCM
status:
  conditions:
  - lastTransitionTime: "2026-11-16T11:04:18Z"
    message: ""
    observedGeneration: 1
    reason: ReconcileSuccess
    status: "True"
    type: Ready
  encryptedKeyMaterial: eyJjaXBoZXJ0ZXh0Ijoi...
  rootKeyID: kms-system/kms-key-ctm-root/ctm/60d6e587f1524923a4e53b522680a69e6268425f429d49cc97c7eeb70a7ed822/0
```
```text
gdc-vault-kms-test
```

---

## 5. Step-by-Step HashiCorp Vault Installation & Automatic Unsealing via GDCag KMS

### 5.1 How the `gdc-kms-bridge` Sidecar Bridges Vault `seal "gcpckms"` to GDCag KMS

HashiCorp Vault's built-in `seal "gcpckms"` seal mechanism invokes Google Cloud KMS gRPC methods (`/google.cloud.kms.v1.KeyManagementService/{GetCryptoKey,Encrypt,Decrypt}` and `/google.iam.v1.IAMPolicy/TestIamPermissions`) against `cloudkms.googleapis.com:443` using standard OAuth2 credentials and resource names formatted as `projects/<project>/locations/<region>/keyRings/<ring>/cryptoKeys/<key>`.

On GDCag, the hardware-backed KMS endpoint (`https://kms.org-12345.zone1.google.gdch.test:443`) exposes `/goog.gdc.kms.v1.CryptoOperationsService/{Encrypt,Decrypt}`—which shares identical protobuf field numbers (`1 = name`, `2 = plaintext/ciphertext`, `3 = additional_authenticated_data`)—authenticated with a GDC `STS-Bearer` token exchanged from the `vault-kms-sa.json` ES256 key at `https://service-accounts.org-12345.google.gdch.test/authenticate`.

To provide seamless auto-unsealing without modifying the upstream Vault binary:
1. `gdc-kms-bridge` runs as a Kubernetes 1.32 native sidecar (`extraInitContainers` with `restartPolicy: Always`) inside `vault-0`, listening on `0.0.0.0:443` with `hostAliases` mapping `cloudkms.googleapis.com` and `oauth2.googleapis.com` to `127.0.0.1`.
2. On startup, `gdc-kms-bridge` writes a local CA bundle and OAuth2 credential stub to the shared `/vault/kms-bridge` memory volume before `vault` starts (enforced by a `tcpSocket: 443` `startupProbe`).
3. Whenever Vault initializes or restarts, `gdc-kms-bridge` exchanges `vault-kms-sa.json` for a GDC `STS-Bearer` token and translates Vault's `projects/iac-root/locations/zone1/keyRings/iac-root/cryptoKeys/vault-unseal-key` Encrypt/Decrypt calls into live GDCag KMS calls on `namespaces/iac-root/aeadKeys/vault-unseal-key`.

<details>
<summary><strong>Click to expand: <code>gdc-kms-bridge</code> Source (<code>main.go</code>) & <code>Dockerfile</code></strong></summary>

#### `Dockerfile`
```dockerfile
FROM harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault:1.15.0
USER root
COPY gdc-kms-bridge /usr/local/bin/gdc-kms-bridge
RUN chmod 0755 /usr/local/bin/gdc-kms-bridge
```

#### `main.go`
```go
package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type saKeyFile struct {
	Project      string `json:"project"`
	Name         string `json:"name"`
	PrivateKeyID string `json:"private_key_id"`
	PrivateKey   string `json:"private_key"`
	TokenURI     string `json:"token_uri"`
}

type bridgeServer struct {
	saPath      string
	kmsEndpoint string
	hc          *http.Client

	mu          sync.Mutex
	cachedToken string
	tokenExpiry time.Time
}

func (b *bridgeServer) getSTSToken() (string, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.cachedToken != "" && time.Now().Before(b.tokenExpiry) {
		return b.cachedToken, nil
	}
	raw, err := os.ReadFile(b.saPath)
	if err != nil {
		return "", fmt.Errorf("read SA key: %w", err)
	}
	var sa saKeyFile
	if err := json.Unmarshal(raw, &sa); err != nil {
		return "", fmt.Errorf("unmarshal SA key: %w", err)
	}
	block, _ := pem.Decode([]byte(sa.PrivateKey))
	if block == nil {
		return "", fmt.Errorf("failed to decode PEM private_key")
	}
	var ecKey *ecdsa.PrivateKey
	if k, err := x509.ParseECPrivateKey(block.Bytes); err == nil {
		ecKey = k
	} else if k2, err := x509.ParsePKCS8PrivateKey(block.Bytes); err == nil {
		ecKey = k2.(*ecdsa.PrivateKey)
	} else {
		return "", fmt.Errorf("parse EC private key failed: %w", err)
	}

	hdr, _ := json.Marshal(map[string]string{
		"alg": "ES256",
		"kid": sa.PrivateKeyID,
		"typ": "JWT",
	})
	now := time.Now().Unix()
	sub := fmt.Sprintf("system:serviceaccount:%s:%s", sa.Project, sa.Name)
	pay, _ := json.Marshal(map[string]any{
		"aud": sa.TokenURI,
		"exp": now + 3600,
		"iat": now,
		"iss": sub,
		"sub": sub,
	})
	b64 := base64.RawURLEncoding.EncodeToString
	signingInput := b64(hdr) + "." + b64(pay)
	digest := sha256.Sum256([]byte(signingInput))
	r, s, err := ecdsa.Sign(rand.Reader, ecKey, digest[:])
	if err != nil {
		return "", err
	}
	curveBytes := (elliptic.P256().Params().BitSize + 7) / 8
	sig := make([]byte, 2*curveBytes)
	r.FillBytes(sig[:curveBytes])
	s.FillBytes(sig[curveBytes:])
	jwt := signingInput + "." + b64(sig)

	reqBody, _ := json.Marshal(map[string]string{
		"audience":             b.kmsEndpoint,
		"grant_type":           "urn:ietf:params:oauth:token-type:token-exchange",
		"requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
		"subject_token":        jwt,
		"subject_token_type":   "urn:k8s:params:oauth:token-type:serviceaccount",
	})
	resp, err := b.hc.Post(sa.TokenURI, "application/json", bytes.NewReader(reqBody))
	if err != nil {
		return "", fmt.Errorf("STS POST: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 {
		return "", fmt.Errorf("STS status %d: %s", resp.StatusCode, string(body))
	}
	var out struct {
		AccessToken string `json:"access_token"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return "", fmt.Errorf("STS json: %w", err)
	}
	b.cachedToken = out.AccessToken
	b.tokenExpiry = time.Now().Add(45 * time.Minute)
	return b.cachedToken, nil
}

func appendVarint(b []byte, v uint64) []byte {
	for v >= 0x80 {
		b = append(b, byte(v)|0x80)
		v >>= 7
	}
	return append(b, byte(v))
}

func appendBytesField(b []byte, fieldNum int, data []byte) []byte {
	if len(data) == 0 {
		return b
	}
	b = appendVarint(b, uint64((fieldNum<<3)|2))
	b = appendVarint(b, uint64(len(data)))
	return append(b, data...)
}

func parseProtoFields(b []byte) (map[int][]byte, map[int][][]byte) {
	single := map[int][]byte{}
	multi := map[int][][]byte{}
	i := 0
	for i < len(b) {
		tag, n := binary.Uvarint(b[i:])
		if n <= 0 {
			break
		}
		i += n
		fnum := int(tag >> 3)
		wtype := int(tag & 7)
		switch wtype {
		case 2:
			l, n2 := binary.Uvarint(b[i:])
			if n2 <= 0 || i+n2+int(l) > len(b) {
				return single, multi
			}
			i += n2
			val := b[i : i+int(l)]
			single[fnum] = val
			multi[fnum] = append(multi[fnum], val)
			i += int(l)
		case 0:
			_, n2 := binary.Uvarint(b[i:])
			if n2 <= 0 {
				return single, multi
			}
			i += n2
		case 1:
			i += 8
		case 5:
			i += 4
		default:
			return single, multi
		}
	}
	return single, multi
}

func toGDCKeyName(gcpName string) string {
	if strings.HasPrefix(gcpName, "namespaces/") {
		return gcpName
	}
	parts := strings.Split(gcpName, "/")
	var kr, ck string
	for i := 0; i+1 < len(parts); i++ {
		if parts[i] == "keyRings" {
			kr = parts[i+1]
		}
		if parts[i] == "cryptoKeys" {
			ck = parts[i+1]
		}
	}
	if kr != "" && ck != "" {
		return fmt.Sprintf("namespaces/%s/aeadKeys/%s", kr, ck)
	}
	return "namespaces/iac-root/aeadKeys/vault-unseal-key"
}

func (b *bridgeServer) callGDCKMS(method string, reqProto []byte) ([]byte, error) {
	tok, err := b.getSTSToken()
	if err != nil {
		return nil, err
	}
	frame := make([]byte, 5+len(reqProto))
	frame[0] = 0
	binary.BigEndian.PutUint32(frame[1:5], uint32(len(reqProto)))
	copy(frame[5:], reqProto)

	req, err := http.NewRequest("POST", b.kmsEndpoint+method, bytes.NewReader(frame))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/grpc")
	req.Header.Set("Te", "trailers")
	req.Header.Set("Authorization", "Bearer "+tok)

	resp, err := b.hc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if gs := resp.Trailer.Get("Grpc-Status"); gs != "" && gs != "0" {
		return nil, fmt.Errorf("gdc kms grpc error %s: %s", gs, resp.Trailer.Get("Grpc-Message"))
	}
	if gs := resp.Header.Get("Grpc-Status"); gs != "" && gs != "0" {
		return nil, fmt.Errorf("gdc kms header error %s: %s", gs, resp.Header.Get("Grpc-Message"))
	}
	if len(body) < 5 {
		return nil, fmt.Errorf("short gdc kms response (%d bytes)", len(body))
	}
	msgLen := binary.BigEndian.Uint32(body[1:5])
	return body[5 : 5+msgLen], nil
}

func writeGRPCResponse(w http.ResponseWriter, respProto []byte) {
	w.Header().Set("Content-Type", "application/grpc")
	w.Header().Set("Trailer", "Grpc-Status, Grpc-Message")
	w.WriteHeader(http.StatusOK)
	frame := make([]byte, 5+len(respProto))
	frame[0] = 0
	binary.BigEndian.PutUint32(frame[1:5], uint32(len(respProto)))
	copy(frame[5:], respProto)
	_, _ = w.Write(frame)
	if fl, ok := w.(http.Flusher); ok {
		fl.Flush()
	}
	w.Header().Set("Grpc-Status", "0")
	w.Header().Set("Grpc-Message", "")
}

func writeGRPCError(w http.ResponseWriter, msg string) {
	log.Printf("ERROR: %s", msg)
	w.Header().Set("Content-Type", "application/grpc")
	w.Header().Set("Trailer", "Grpc-Status, Grpc-Message")
	w.WriteHeader(http.StatusOK)
	w.Header().Set("Grpc-Status", "13")
	w.Header().Set("Grpc-Message", msg)
}

func (b *bridgeServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/token" {
		tok, err := b.getSTSToken()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": tok,
			"token_type":   "Bearer",
			"expires_in":   3600,
		})
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil || len(body) < 5 {
		writeGRPCError(w, "invalid grpc request frame")
		return
	}
	msgLen := binary.BigEndian.Uint32(body[1:5])
	if int(5+msgLen) > len(body) {
		writeGRPCError(w, "truncated grpc frame")
		return
	}
	reqProto := body[5 : 5+msgLen]
	single, multi := parseProtoFields(reqProto)

	switch r.URL.Path {
	case "/google.cloud.kms.v1.KeyManagementService/GetCryptoKey":
		var out []byte
		out = appendBytesField(out, 1, single[1])
		writeGRPCResponse(w, out)

	case "/google.iam.v1.IAMPolicy/TestIamPermissions":
		var out []byte
		for _, perm := range multi[2] {
			out = appendBytesField(out, 1, perm)
		}
		writeGRPCResponse(w, out)

	case "/google.cloud.kms.v1.KeyManagementService/Encrypt":
		origName := string(single[1])
		gdcName := toGDCKeyName(origName)
		var gdcReq []byte
		gdcReq = appendBytesField(gdcReq, 1, []byte(gdcName))
		gdcReq = appendBytesField(gdcReq, 2, single[2])
		gdcReq = appendBytesField(gdcReq, 3, single[3])

		gdcResp, err := b.callGDCKMS("/goog.gdc.kms.v1.CryptoOperationsService/Encrypt", gdcReq)
		if err != nil {
			writeGRPCError(w, err.Error())
			return
		}
		respFields, _ := parseProtoFields(gdcResp)
		var out []byte
		out = appendBytesField(out, 1, []byte(origName))
		out = appendBytesField(out, 2, respFields[2])
		log.Printf("GDCag KMS Encrypt succeeded for %s -> %s (ciphertext=%d bytes)", origName, gdcName, len(respFields[2]))
		writeGRPCResponse(w, out)

	case "/google.cloud.kms.v1.KeyManagementService/Decrypt":
		origName := string(single[1])
		gdcName := toGDCKeyName(origName)
		var gdcReq []byte
		gdcReq = appendBytesField(gdcReq, 1, []byte(gdcName))
		gdcReq = appendBytesField(gdcReq, 2, single[2])
		gdcReq = appendBytesField(gdcReq, 3, single[3])

		gdcResp, err := b.callGDCKMS("/goog.gdc.kms.v1.CryptoOperationsService/Decrypt", gdcReq)
		if err != nil {
			writeGRPCError(w, err.Error())
			return
		}
		respFields, _ := parseProtoFields(gdcResp)
		var out []byte
		out = appendBytesField(out, 1, respFields[1])
		log.Printf("GDCag KMS Decrypt succeeded for %s -> %s (plaintext=%d bytes)", origName, gdcName, len(respFields[1]))
		writeGRPCResponse(w, out)

	default:
		log.Printf("Unhandled gRPC method: %s", r.URL.Path)
		writeGRPCResponse(w, nil)
	}
}

func setupTLSAndCreds(tlsDir string) (tls.Certificate, error) {
	if err := os.MkdirAll(tlsDir, 0755); err != nil {
		return tls.Certificate{}, err
	}
	certPath := filepath.Join(tlsDir, "server.crt")
	keyPath := filepath.Join(tlsDir, "server.key")
	if _, err := os.Stat(certPath); err == nil {
		if _, err2 := os.Stat(keyPath); err2 == nil {
			return tls.LoadX509KeyPair(certPath, keyPath)
		}
	}
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return tls.Certificate{}, err
	}
	tmpl := x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "cloudkms.googleapis.com"},
		NotBefore:             time.Now().Add(-1 * time.Hour),
		NotAfter:              time.Now().Add(10 * 365 * 24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment | x509.KeyUsageCertSign,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		IsCA:                  true,
		DNSNames:              []string{"cloudkms.googleapis.com", "oauth2.googleapis.com", "localhost"},
		IPAddresses:           []net.IP{net.ParseIP("127.0.0.1")},
	}
	der, err := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &priv.PublicKey, priv)
	if err != nil {
		return tls.Certificate{}, err
	}
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	privBytes, _ := x509.MarshalECPrivateKey(priv)
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: privBytes})

	if err := os.WriteFile(certPath, certPEM, 0644); err != nil {
		return tls.Certificate{}, err
	}
	if err := os.WriteFile(keyPath, keyPEM, 0600); err != nil {
		return tls.Certificate{}, err
	}

	var combined bytes.Buffer
	if sysCA, err := os.ReadFile("/etc/ssl/certs/ca-certificates.crt"); err == nil {
		combined.Write(sysCA)
		combined.WriteByte('\n')
	}
	combined.Write(certPEM)
	if err := os.WriteFile(filepath.Join(tlsDir, "ca-certificates.crt"), combined.Bytes(), 0644); err != nil {
		return tls.Certificate{}, err
	}

	credsJSON := `{
  "type": "authorized_user",
  "client_id": "vault-kms-sa",
  "client_secret": "gdc-kms",
  "refresh_token": "gdc-kms",
  "token_uri": "https://oauth2.googleapis.com/token"
}
`
	if err := os.WriteFile(filepath.Join(tlsDir, "gcp-credentials.json"), []byte(credsJSON), 0644); err != nil {
		return tls.Certificate{}, err
	}
	return tls.X509KeyPair(certPEM, keyPEM)
}

func main() {
	saPath := os.Getenv("GDC_SA_KEY_FILE")
	if saPath == "" {
		saPath = "/etc/vault/kms/vault-kms-sa.json"
	}
	kmsEndpoint := os.Getenv("GDC_KMS_ENDPOINT")
	if kmsEndpoint == "" {
		kmsEndpoint = "https://kms.org-12345.zone1.google.gdch.test"
	}
	tlsDir := os.Getenv("GDC_BRIDGE_SHARED_DIR")
	if tlsDir == "" {
		tlsDir = "/vault/kms-bridge"
	}
	listenAddr := os.Getenv("GDC_BRIDGE_LISTEN")
	if listenAddr == "" {
		listenAddr = "127.0.0.1:443"
	}

	cert, err := setupTLSAndCreds(tlsDir)
	if err != nil {
		log.Fatalf("setupTLSAndCreds: %v", err)
	}
	if os.Getenv("INIT_ONLY") == "true" {
		log.Printf("Initialized TLS & credentials in %s", tlsDir)
		return
	}

	tr := &http.Transport{
		ForceAttemptHTTP2: true,
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: true,
			CurvePreferences:   []tls.CurveID{tls.X25519, tls.CurveP256},
			NextProtos:         []string{"h2"},
		},
	}
	bs := &bridgeServer{
		saPath:      saPath,
		kmsEndpoint: kmsEndpoint,
		hc:          &http.Client{Transport: tr, Timeout: 15 * time.Second},
	}

	srv := &http.Server{
		Addr:    listenAddr,
		Handler: bs,
		TLSConfig: &tls.Config{
			Certificates: []tls.Certificate{cert},
			NextProtos:   []string{"h2", "http/1.1"},
		},
	}
	ln, err := net.Listen("tcp", listenAddr)
	if err != nil {
		log.Fatalf("listen %s: %v", listenAddr, err)
	}
	log.Printf("gdc-kms-bridge listening on %s -> %s", listenAddr, kmsEndpoint)
	log.Fatal(srv.Serve(tls.NewListener(ln, srv.TLSConfig)))
}
```

#### Build & Push Commands (if rebuilding from source)
```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o gdc-kms-bridge main.go
docker build -t harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/gdc-kms-bridge:1.0.0 .
docker push harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/gdc-kms-bridge:1.0.0
```
</details>

### 5.2 Step 1: Create the `vault` Namespace & Secrets on the User Cluster

Switch to the User Cluster kubeconfig (`iac-root-2ad0c4dd`) and create the `vault` namespace, the `gdc-kms-sa` secret containing `vault-kms-sa.json`, and the `harbor-creds` image pull secret:

```bash
export KUBECONFIG="${USER_CLUSTER_KUBECONFIG}"

# 1. Create namespace vault
kubectl create namespace vault --dry-run=client -o yaml | kubectl apply -f -

# 2. Create secret containing the GDCag KMS ProjectServiceAccount key
kubectl -n vault create secret generic gdc-kms-sa \
  --from-file=vault-kms-sa.json="${WORK_DIR}/vault-kms-sa.json" \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Create Harbor pull secret from ~/.docker/config.json
kubectl -n vault create secret generic harbor-creds \
  --from-file=.dockerconfigjson="${HOME}/.docker/config.json" \
  --type=kubernetes.io/dockerconfigjson \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 5.3 Step 2: Create the Vault Helm Values (`vault-values.yaml` - Option A: Integrated Raft Storage Default)

> [!TIP]
> **Option A (Recommended Default - Integrated Raft Storage on `standard-rwo`) vs. Option B (Managed PostgreSQL):**
> * **Why Option A is the Default**: Storing Vault's encrypted state on integrated Raft (`storageClass: "standard-rwo"`, `replicas: 1` for single-node validation or `replicas: 3` for multi-node HA) keeps Vault's startup and GDCag KMS auto-unseal path 100% self-contained on the User Cluster, with zero external database hop or bootstrap credential circularity. If your organization requires all stateful persistence on GDCag Managed PostgreSQL (`DBCluster`), use **Option B (`storage "postgresql"`)** in [Section 5.6](#56-alternative-architecture-option-b-managed-postgresql-dbcluster-storage-backend).
> * **`livenessProbe.path: "/v1/sys/health?standbyok=true&uninitok=true&sealedcode=204"`**: Prevents kubelet from restarting `vault-0` with HTTP `501 Not Initialized` prior to running `vault operator init`.

Create `${WORK_DIR}/vault-values.yaml`:

```yaml
global:
  enabled: true
  tlsDisable: true
  imagePullSecrets:
    - name: harbor-creds

injector:
  enabled: true
  affinity: ""
  image:
    repository: harbor.org-12345.zone1.google.gdch.test/library/hashicorp/vault-k8s
    tag: "1.7.2"
    pullPolicy: IfNotPresent
  agentImage:
    repository: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault
    tag: "1.15.0"
  resources:
    requests:
      memory: 128Mi
      cpu: 100m
    limits:
      memory: 256Mi
      cpu: 250m

server:
  enabled: true
  image:
    repository: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault
    tag: "1.15.0"
    pullPolicy: IfNotPresent
  updateStrategyType: "RollingUpdate"
  affinity: ""
  resources:
    requests:
      memory: 256Mi
      cpu: 250m
    limits:
      memory: 512Mi
      cpu: 500m

  readinessProbe:
    enabled: true
    path: "/v1/sys/health?standbyok=true&perfstandbyok=true"
  livenessProbe:
    enabled: true
    path: "/v1/sys/health?standbyok=true&uninitok=true&sealedcode=204"
    initialDelaySeconds: 60

  hostAliases:
    - ip: "127.0.0.1"
      hostnames:
        - "cloudkms.googleapis.com"
        - "oauth2.googleapis.com"

  extraEnvironmentVars:
    GOOGLE_REGION: "zone1"
    GOOGLE_PROJECT: "iac-root"
    GOOGLE_APPLICATION_CREDENTIALS: "/vault/kms-bridge/gcp-credentials.json"
    SSL_CERT_FILE: "/vault/kms-bridge/ca-certificates.crt"

  extraVolumes:
    - type: secret
      name: gdc-kms-sa

  volumes:
    - name: kms-bridge
      emptyDir: {}

  volumeMounts:
    - name: kms-bridge
      mountPath: /vault/kms-bridge
      readOnly: true

  extraInitContainers:
    - name: gdc-kms-bridge
      image: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/gdc-kms-bridge:1.0.0
      imagePullPolicy: IfNotPresent
      restartPolicy: Always
      command: ["/usr/local/bin/gdc-kms-bridge"]
      securityContext:
        runAsNonRoot: false
        runAsUser: 0
        capabilities:
          add: ["NET_BIND_SERVICE"]
      env:
        - name: GDC_SA_KEY_FILE
          value: "/vault/userconfig/gdc-kms-sa/vault-kms-sa.json"
        - name: GDC_KMS_ENDPOINT
          value: "https://kms.org-12345.zone1.google.gdch.test"
        - name: GDC_BRIDGE_SHARED_DIR
          value: "/vault/kms-bridge"
        - name: GDC_BRIDGE_LISTEN
          value: "0.0.0.0:443"
      startupProbe:
        tcpSocket:
          port: 443
        initialDelaySeconds: 1
        periodSeconds: 1
        failureThreshold: 15
      volumeMounts:
        - name: kms-bridge
          mountPath: /vault/kms-bridge
        - name: userconfig-gdc-kms-sa
          mountPath: /vault/userconfig/gdc-kms-sa
          readOnly: true

  dataStorage:
    enabled: true
    size: 10Gi
    mountPath: /vault/data
    storageClass: "standard-rwo"
    accessMode: ReadWriteOnce

  auditStorage:
    enabled: false

  standalone:
    enabled: false

  ha:
    enabled: true
    replicas: 1
    raft:
      enabled: true
      setNodeId: true
      config: |
        ui = true

        listener "tcp" {
          tls_disable = 1
          address = "[::]:8200"
          cluster_address = "[::]:8201"
        }

        storage "raft" {
          path = "/vault/data"
        }

        seal "gcpckms" {
          project     = "iac-root"
          region      = "zone1"
          key_ring    = "iac-root"
          crypto_key  = "vault-unseal-key"
        }

        service_registration "kubernetes" {}

ui:
  enabled: true
  serviceType: "ClusterIP"
```

### 5.4 Step 3: Deploy, Initialize & Verify Automatic Unsealing via GDCag KMS

Install the Vault Helm chart, initialize the Raft storage backend (`vault operator init`), and verify that Vault immediately auto-unseals via GDCag KMS without manual unseal key entry:

```bash
# 1. Install or upgrade HashiCorp Vault
GODEBUG=tlsmlkem=0 helm upgrade --install vault "${WORK_DIR}/charts/vault" \
  --namespace vault \
  -f "${WORK_DIR}/vault-values.yaml"

# 2. Wait for vault-0 containers to start
kubectl -n vault wait --for=condition=Initialized pod/vault-0 --timeout=120s

# 3. Initialize Vault (generates recovery keys and root token, and auto-unseals via GDCag KMS)
kubectl -n vault exec vault-0 -c vault -- vault operator init -format=json > "${WORK_DIR}/vault-init.json"

# 4. Verify Vault status and GDCag KMS bridge logs
kubectl -n vault exec vault-0 -c vault -- vault status
kubectl -n vault logs vault-0 -c gdc-kms-bridge
```

**Verified `vault status` Output (`Sealed: false`, `Recovery Seal Type: shamir`):**
```text
Key                      Value
---                      -----
Recovery Seal Type       shamir
Initialized              true
Sealed                   false
Total Recovery Shares    5
Threshold                3
Version                  1.15.0
Build Date               2023-09-22T16:53:10Z
Storage Type             raft
Cluster Name             vault-cluster-26f409a6
Cluster ID               7a4711f4-c0ed-4d5d-4dc9-84f6a53fb77b
HA Enabled               true
HA Cluster               https://vault-0.vault-internal:8201
HA Mode                  active
Active Since             2026-11-16T11:49:08.051173804Z
Raft Committed Index     58
Raft Applied Index       58
```

**Verified `gdc-kms-bridge` Auto-Unseal Logs (including live process restart test):**
```text
2026/11/16 11:48:16 gdc-kms-bridge listening on 0.0.0.0:443 -> https://kms.org-12345.zone1.google.gdch.test
2026/11/16 11:49:04 GDCag KMS Encrypt succeeded for projects/iac-root/locations/zone1/keyRings/iac-root/cryptoKeys/vault-unseal-key -> namespaces/iac-root/aeadKeys/vault-unseal-key (ciphertext=60 bytes)
2026/11/16 11:49:07 GDCag KMS Decrypt succeeded for projects/iac-root/locations/zone1/keyRings/iac-root/cryptoKeys/vault-unseal-key -> namespaces/iac-root/aeadKeys/vault-unseal-key (plaintext=32 bytes)
2026/11/16 11:52:19 GDCag KMS Decrypt succeeded for projects/iac-root/locations/zone1/keyRings/iac-root/cryptoKeys/vault-unseal-key -> namespaces/iac-root/aeadKeys/vault-unseal-key (plaintext=32 bytes)
```

### 5.5 Step 4: Apply User Cluster Vault `NetworkPolicy` (`5432/TCP` Managed `DBCluster` Egress)

Harden the `vault` namespace with a least-privilege Kubernetes `NetworkPolicy` (matching [`blueprints/patterns/p11-vault/manifests/security/network-policy.yaml`](../../blueprints/patterns/p11-vault/manifests/security/network-policy.yaml)) that restricts Raft peer traffic (`8201/TCP`) strictly to Vault pods, allows cross-namespace application pods to reach Vault API port `8200/TCP`, permits outbound KMS/STS/OIDC/Kubernetes `TokenReview` calls, and scopes outbound PostgreSQL `5432/TCP` egress to your Zonal `DBCluster` VIP/subnet CIDR (required for **Option B** in [Section 5.6](#56-alternative-architecture-option-b-managed-postgresql-dbcluster-storage-backend) and the **Dynamic Database Secrets Engine (`database/`)** in [Section 8.5](#85-pattern-d-dynamic-postgresql-credentials-via-vault-database-secrets-engine)):

```bash
# Set DBCLUSTER_SUBNET_CIDR to your GDCag Zonal Managed Database VIP/subnet CIDR (e.g., 10.200.0.0/16)
export DBCLUSTER_SUBNET_CIDR="${DBCLUSTER_SUBNET_CIDR:-10.200.0.0/16}"

cat <<EOF | kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vault-internal-policy
  namespace: vault
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: vault
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector: {}
      ports:
        - protocol: TCP
          port: 8200
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: vault
      ports:
        - protocol: TCP
          port: 8201
  egress:
    # 1. Cluster DNS resolution (kube-dns / CoreDNS)
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # 2. Vault Raft / HA peer communication
    - to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: vault
      ports:
        - protocol: TCP
          port: 8200
        - protocol: TCP
          port: 8201
    # 3. In-cluster OIDC JWKS discovery (GitLab / Keycloak)
    - to:
        - namespaceSelector: {}
      ports:
        - protocol: TCP
          port: 80
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 8080
    # 4. GDCag KMS Data Plane, STS Token Exchange & K8s API TokenReview
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 6443
    # 5. GDCag Managed PostgreSQL (DBCluster) egress for Option B storage or database/ engine
    - to:
        - ipBlock:
            cidr: ${DBCLUSTER_SUBNET_CIDR}
      ports:
        - protocol: TCP
          port: 5432
EOF
```
*(If deploying Vault via the [`p11-vault` Helm wrapper chart](../../blueprints/patterns/p11-vault/chart/values.yaml), set `vault.networkPolicy.allowPostgresEgress: true` and `vault.networkPolicy.postgresCidrs: ["<DBCLUSTER_SUBNET_CIDR>"]`.)*

### 5.6 Alternative Architecture (Option B): Managed PostgreSQL `DBCluster` Storage Backend

Use **Option B (`storage "postgresql"`)** when platform governance mandates storing all stateful control-plane data in GDCag Managed PostgreSQL (`postgresql.dbadmin.gdc.goog/v1` `DBCluster` + `BackupPlan`) rather than User Cluster `standard-rwo` PVCs.

> [!IMPORTANT]
> **Option B Design & Security Guardrails:**
> 1. **Bootstrap Secret Circularity (SOPS Pattern E)**: Because Vault requires `VAULT_PG_CONNECTION_URL` before unsealing, Vault cannot fetch its own storage backend credentials from Vault. Store the User Cluster `Secret/vault-pg-conn` encrypted at rest in Git using Mozilla SOPS (`helm-secrets`) as documented in the [SOPS & Helm-Secrets Integration Guide](../../foundations/sops_implementation_plan.md).
> 2. **Bypassing `gdc-kms-bridge` `SSL_CERT_FILE` Override**: `gdc-kms-bridge` sets `SSL_CERT_FILE="/vault/kms-bridge/ca-certificates.crt"` (`main.go` bundles system CAs plus the localhost KMS certificate, not Zonal `dbs-certificates`). Always mount `Secret/vault-db-ca` via `server.extraVolumes` and pass explicit `?sslmode=verify-full&sslrootcert=/vault/userconfig/vault-db-ca/ca.crt` in `VAULT_PG_CONNECTION_URL`.
> 3. **Mandatory `COLLATE "C"` & Upstream Chart Keys**: Vault does not auto-create PostgreSQL tables, and text columns in `vault_kv_store` and `vault_ha_locks` **must** use `COLLATE "C"` so byte-order prefix scans work reliably. In `vault-0.32.0`, set `server.dataStorage.enabled: false`, **`server.ha.raft.enabled: false`**, and move HCL to **`server.ha.config`** (leaving HCL under `server.ha.raft.config` is ignored when Raft is disabled).

#### Step B1: Provision Zonal `DBCluster/vault-db` & `BackupPlan` (`ZONE_KUBECONFIG`)

```bash
export VAULT_DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"
export VAULT_DB_ADMIN_B64=$(printf '%s' "${VAULT_DB_ADMIN_PASSWORD}" | base64 -w0)

# 1. Provision Secret/db-pw-vault-db (key MUST match DBCluster name 'vault-db') and DBCluster on ZONE_KUBECONFIG
cat <<EOF | kubectl --kubeconfig="${ZONE_KUBECONFIG}" apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-vault-db
  namespace: iac-root
type: Opaque
data:
  vault-db: "${VAULT_DB_ADMIN_B64}"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: vault-db
  namespace: iac-root
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-vault-db
    version: "15"
    resources:
      cpu: 2
      memory: 8Gi
      disks:
        - name: DataDisk
          size: 50Gi
EOF

# Optional: Attach automated daily BackupPlan if BackupRepository/dbs-backup-repository is Ready
if kubectl --kubeconfig="${ZONE_KUBECONFIG}" get backuprepository dbs-backup-repository >/dev/null 2>&1; then
  cat <<'EOF' | kubectl --kubeconfig="${ZONE_KUBECONFIG}" apply -f -
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: BackupPlan
metadata:
  name: vault-db-backup
  namespace: iac-root
spec:
  dbclusterRef: vault-db
  backupRetainDays: 14
  paused: false
  PITREnabled: false
EOF
fi

# 2. Wait for DBCluster/vault-db readiness, strip ':5432' from primary URL, and export TLS Root CA
kubectl --kubeconfig="${ZONE_KUBECONFIG}" wait --for=condition=Ready \
  dbcluster.postgresql.dbadmin.gdc.goog/vault-db -n iac-root --timeout=20m

VAULT_DB_URL=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog vault-db \
  -n iac-root -o jsonpath='{.status.primary.url}')
export VAULT_DB_HOST="${VAULT_DB_URL%:5432}"

kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n iac-root -o jsonpath='{.data.dbs-pg-cert-vault-db}' | base64 -d > "${WORK_DIR}/vault-db-ca.crt"
```

#### Step B2: Initialize `vault` Role, Database & `COLLATE "C"` Schema as `dbsadmin`

Connect to `vault-db` as `dbsadmin` (`cloudsqlsuperuser`) over verified TLS (for example, using `psql` from an operator bastion with Zonal DB routing or a short-lived User Cluster bootstrap job reusing `gitlab-toolbox-ee` as shown in [Section 6.3](#63-step-2-bootstrap-user-cluster-namespace-tls-ca-networkpolicy--gitlabhq_production-extensions-user_cluster_kubeconfig)):

```bash
export VAULT_DB_PASSWORD="<strong-vault-storage-password>"

# 1. Create dedicated 'vault' role, grant membership to dbsadmin (required for cloudsqlsuperuser OWNER assignment),
#    and create database 'vault' owned by 'vault'
PGPASSWORD="${VAULT_DB_ADMIN_PASSWORD}" PGSSLMODE=verify-full PGSSLROOTCERT="${WORK_DIR}/vault-db-ca.crt" \
  psql -h "${VAULT_DB_HOST}" -p 5432 -U dbsadmin -d postgres -v vault_pw="${VAULT_DB_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE vault WITH LOGIN PASSWORD %L', :'vault_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vault') \gexec
GRANT vault TO dbsadmin;
SELECT 'CREATE DATABASE vault OWNER vault'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vault') \gexec
SQL

# 2. Connect to '-d vault' to transfer PostgreSQL 15 public schema ownership and create Vault HA tables with COLLATE "C"
PGPASSWORD="${VAULT_DB_ADMIN_PASSWORD}" PGSSLMODE=verify-full PGSSLROOTCERT="${WORK_DIR}/vault-db-ca.crt" \
  psql -h "${VAULT_DB_HOST}" -p 5432 -U dbsadmin -d vault <<'SQL'
GRANT ALL ON SCHEMA public TO vault;
ALTER SCHEMA public OWNER TO vault;

CREATE TABLE IF NOT EXISTS vault_kv_store (
  parent_path TEXT COLLATE "C" NOT NULL,
  path        TEXT COLLATE "C",
  key         TEXT COLLATE "C",
  value       BYTEA,
  CONSTRAINT pkey PRIMARY KEY (path, key)
);

CREATE INDEX IF NOT EXISTS parent_path_idx ON vault_kv_store (parent_path);

CREATE TABLE IF NOT EXISTS vault_ha_locks (
  ha_key      TEXT COLLATE "C" NOT NULL,
  ha_identity TEXT COLLATE "C" NOT NULL,
  ha_value    TEXT COLLATE "C",
  valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
  CONSTRAINT ha_key PRIMARY KEY (ha_key)
);

ALTER TABLE vault_kv_store OWNER TO vault;
ALTER TABLE vault_ha_locks OWNER TO vault;
GRANT ALL PRIVILEGES ON TABLE vault_kv_store, vault_ha_locks TO vault;
SQL
```

#### Step B3: Create User Cluster TLS CA & Connection Secrets (`USER_CLUSTER_KUBECONFIG`)

```bash
# URL-encode special characters in VAULT_DB_PASSWORD before embedding in a PostgreSQL URI
VAULT_DB_PASSWORD_URLENC=$(python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["VAULT_DB_PASSWORD"], safe=""))')

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" -n vault create secret generic vault-db-ca \
  --from-file=ca.crt="${WORK_DIR}/vault-db-ca.crt" \
  --dry-run=client -o yaml | kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" apply -f -

# In GitOps workflows, encrypt this Secret manifest in Git with Mozilla SOPS (see foundations/sops_implementation_plan.md)
kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" -n vault create secret generic vault-pg-conn \
  --from-literal=connection_url="postgresql://vault:${VAULT_DB_PASSWORD_URLENC}@${VAULT_DB_HOST}:5432/vault?sslmode=verify-full&sslrootcert=/vault/userconfig/vault-db-ca/ca.crt" \
  --dry-run=client -o yaml | kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" apply -f -
```
*(Note: If connecting via a raw LoadBalancer IP or custom alias absent from the certificate's `subjectAltName`, replace `sslmode=verify-full` with `sslmode=verify-ca`.)*

#### Step B4: Deploy Vault with `vault-values-pg.yaml` (`ha.raft.enabled: false`)

Create `${WORK_DIR}/vault-values-pg.yaml` overriding the storage layer of `${WORK_DIR}/vault-values.yaml` (note that Vault's Go `postgresql` backend reads `VAULT_PG_CONNECTION_URL` natively from the environment - never place Consul Template `{{env ...}}` syntax inside Vault Server HCL):

```yaml
server:
  dataStorage:
    enabled: false

  extraEnvironmentVars:
    GOOGLE_REGION: "zone1"
    GOOGLE_PROJECT: "iac-root"
    GOOGLE_APPLICATION_CREDENTIALS: "/vault/kms-bridge/gcp-credentials.json"
    SSL_CERT_FILE: "/vault/kms-bridge/ca-certificates.crt"
    # Advertise individual pod IP for HA standby client redirects (POD_IP is injected by vault-0.32.0 StatefulSet)
    VAULT_API_ADDR: "http://$(POD_IP):8200"

  extraSecretEnvironmentVars:
    - envName: VAULT_PG_CONNECTION_URL
      secretName: vault-pg-conn
      secretKey: connection_url

  extraVolumes:
    - type: secret
      name: gdc-kms-sa
    - type: secret
      name: vault-db-ca

  ha:
    enabled: true
    replicas: 2
    raft:
      enabled: false
    config: |
      ui = true
      api_addr = "http://POD_IP:8200"

      listener "tcp" {
        tls_disable = 1
        address = "[::]:8200"
        cluster_address = "[::]:8201"
      }

      storage "postgresql" {
        table      = "vault_kv_store"
        ha_enabled = "true"
        ha_table   = "vault_ha_locks"
      }

      seal "gcpckms" {
        project     = "iac-root"
        region      = "zone1"
        key_ring    = "iac-root"
        crypto_key  = "vault-unseal-key"
      }

      service_registration "kubernetes" {}
```

Install with both files layered (`-f vault-values.yaml -f vault-values-pg.yaml`) and run `vault operator init` as in Section 5.4 (`vault status` will report `Storage Type: postgresql` and `HA Enabled: true`).

---

## 6. Step-by-Step GitLab 17.11.7 Installation

### 6.1 Key Air-Gap & Managed Persistence Architecture

1. **Explicit System Harbor Image Paths**: User cluster nodes (`vm-9eeae553`) do not have containerd mirror rules for `gcr.io/private-cloud-staging/*`. Every GitLab CNG image in `gitlab-values.yaml` must reference `harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/...:v1.16.2-iac-1800e51e18` with `imagePullSecrets: [{name: harbor-creds}]`.
2. **Zonal HA Managed PostgreSQL 15 (`DBCluster/gitlab-db` + `BackupPlan`)**: The upstream Bitnami PostgreSQL subchart in `gitlab-8.11.7` defaults to un-mirrored `docker.io/bitnami/postgresql:14.8.0` (`postgresql.install: false`). For production resilience on GDCag, provision a Zonal HA `postgresql.dbadmin.gdc.goog/v1` `DBCluster` (`gitlab-db`, `version: "15"`, `enableHighAvailability: true`, `enableAutoFailover: true`, `4 CPU / 16Gi / 50Gi DataDisk`) with an automated daily `BackupPlan` on `ZONE_KUBECONFIG`, and run a one-time pre-install bootstrap `Job` reusing `gitlab-toolbox-ee` (`/usr/bin/psql`) as `dbsadmin` (`cloudsqlsuperuser`) to create the `gitlab` role, `gitlabhq_production` database, and required `pg_trgm` and `btree_gist` extensions prior to `helm upgrade --install gitlab`.
   * *PostgreSQL Version Compatibility Note*: GitLab `17.11.7` officially supports PostgreSQL `14`, `15`, and `16`. Because GitLab `18.0+` raises the minimum PostgreSQL version to `16+` while GDCag `postgresql.dbadmin.gdc.goog/v1` currently provisions PostgreSQL `"15"`, keep GitLab pinned to the `17.11.x` release line until GDCag DBS adds PostgreSQL `16+`.
3. **Why Redis & Gitaly Remain on User Cluster `standard-rwo` PVCs**: GDCag Database Service manages relational PostgreSQL and Oracle engines only (there is no platform-managed Redis service on GDCag), and Gitaly persists raw Git packfiles over gRPC directly on low-latency POSIX block storage (`standard-rwo`). With `registry.enabled: false` and single-node `gitaly` (`praefect` disabled), only the single `gitlabhq_production` database is required (shared automatically by GitLab `17.11`'s `main` and `ci` logical Rails connections).

### 6.2 Step 1: Provision Zonal Managed PostgreSQL 15 (`gitlab-db`) & `BackupPlan` (`ZONE_KUBECONFIG`)

Provision `Secret/db-pw-gitlab-db` (whose `data` key **must** match the `DBCluster` `metadata.name`: `gitlab-db`), `DBCluster/gitlab-db`, and `BackupPlan/gitlab-db-backup` in namespace `iac-root` on the Zone Management API (`ZONE_KUBECONFIG`). You can apply raw KRM manifests (**Option A**) or install the repository's [`./charts/gdc-dbs`](../../charts/gdc-dbs/README.md) (`v0.2.0`) Helm chart (**Option B**):

```bash
export GITLAB_DB_ADMIN_PASSWORD="<strong-dbsadmin-password>"
export GITLAB_DB_ADMIN_B64=$(printf '%s' "${GITLAB_DB_ADMIN_PASSWORD}" | base64 -w0)

# Option A: Declarative KRM Manifests on ZONE_KUBECONFIG
cat <<EOF | kubectl --kubeconfig="${ZONE_KUBECONFIG}" apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: db-pw-gitlab-db
  namespace: iac-root
type: Opaque
data:
  gitlab-db: "${GITLAB_DB_ADMIN_B64}"
---
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: DBCluster
metadata:
  name: gitlab-db
  namespace: iac-root
spec:
  availability:
    enableHighAvailability: true
    enableAutoFailover: true
  primarySpec:
    adminUser:
      passwordRef:
        name: db-pw-gitlab-db
    version: "15"
    resources:
      cpu: 4
      memory: 16Gi
      disks:
        - name: DataDisk
          size: 50Gi
EOF

# Attach automated daily BackupPlan (requires BackupRepository/dbs-backup-repository verified in Section 4.1)
if kubectl --kubeconfig="${ZONE_KUBECONFIG}" get backuprepository dbs-backup-repository >/dev/null 2>&1; then
  cat <<'EOF' | kubectl --kubeconfig="${ZONE_KUBECONFIG}" apply -f -
apiVersion: postgresql.dbadmin.gdc.goog/v1
kind: BackupPlan
metadata:
  name: gitlab-db-backup
  namespace: iac-root
spec:
  dbclusterRef: gitlab-db
  backupRetainDays: 14
  paused: false
  PITREnabled: false
EOF
fi
```

*(**Option B - via [`./charts/gdc-dbs`](../../charts/gdc-dbs/README.md) `v0.2.0`**: Instead of applying the raw YAML above, run `GODEBUG=tlsmlkem=0 helm upgrade --install gitlab-db ./charts/gdc-dbs -n iac-root --kubeconfig="${ZONE_KUBECONFIG}" --set namespace=iac-root --set postgresql.enabled=true --set postgresql.clusterName=gitlab-db --set postgresql.base64EncodedPassword="${GITLAB_DB_ADMIN_B64}" --set postgresql.cpu=4 --set postgresql.memory=16Gi --set postgresql.dataDiskSize=50Gi --set postgresql.backupPlan.enabled=true --set postgresql.backupPlan.name=gitlab-db-backup`.)*

Wait for `DBCluster/gitlab-db` to reach `Ready=True` on `ZONE_KUBECONFIG`, strip `:5432` from `.status.primary.url`, and extract the Zonal server TLS Root CA from `Secret/dbs-certificates`:

```bash
kubectl --kubeconfig="${ZONE_KUBECONFIG}" wait --for=condition=Ready \
  dbcluster.postgresql.dbadmin.gdc.goog/gitlab-db -n iac-root --timeout=20m

# .status.primary.url includes ':5432' (e.g., gitlab-db-primary.iac-root...:5432); strip port for global.psql.host
DB_URL=$(kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog gitlab-db \
  -n iac-root -o jsonpath='{.status.primary.url}')
export DB_HOST="${DB_URL%:5432}"
echo "Resolved GitLab DB_HOST=${DB_HOST}"

# Extract the DBCluster server Root CA from ZONE_KUBECONFIG (not auto-projected to User Clusters)
kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n iac-root -o jsonpath='{.data.dbs-pg-cert-gitlab-db}' | base64 -d > "${WORK_DIR}/gitlab-db-ca.crt"

# Optional SAN pre-flight check (verifies leaf certificate DNS SAN matches ${DB_HOST} for PGSSLMODE=verify-full)
openssl s_client -starttls postgres -connect "${DB_HOST}:5432" \
  -CAfile "${WORK_DIR}/gitlab-db-ca.crt" </dev/null 2>/dev/null | openssl x509 -noout -ext subjectAltName || true
```

### 6.3 Step 2: Bootstrap User Cluster Namespace, TLS CA, `NetworkPolicy` & `gitlabhq_production` Extensions (`USER_CLUSTER_KUBECONFIG`)

Switch to the User Cluster (`USER_CLUSTER_KUBECONFIG`), create the `gitlab` namespace, Harbor pull secret, object-storage backup secret, GitLab application database password secret (`gitlab-postgres-secret`), and cross-plane TLS CA secret (`gitlab-db-ca` - the key **must** end in `.crt` so GitLab's `certificates` initContainer bundles it via `update-ca-certificates`):

```bash
export KUBECONFIG="${USER_CLUSTER_KUBECONFIG}"
export GITLAB_APP_DB_PASSWORD="<strong-gitlab-app-db-password>"

# 1. Create namespace, Harbor pull secret, S3 backup config, and GitLab DB credentials + TLS CA secrets
cat <<EOF > "${WORK_DIR}/gitlab-prereqs.yaml"
apiVersion: v1
kind: Namespace
metadata:
  name: gitlab
---
apiVersion: v1
kind: Secret
metadata:
  name: gitlab-postgres-secret
  namespace: gitlab
type: Opaque
stringData:
  postgresql-password: "${GITLAB_APP_DB_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: gitlab-storage
  namespace: gitlab
type: Opaque
stringData:
  config: |
    [default]
    access_key = gitlab-access-key
    secret_key = gitlab-secret-key
    bucket_location = us-east-1
    host_base = s3.org-12345.zone1.google.gdch.test
    host_bucket = s3.org-12345.zone1.google.gdch.test/%(bucket)
    use_https = True
  connection: |
    provider: AWS
    region: us-east-1
    aws_access_key_id: gitlab-access-key
    aws_secret_access_key: gitlab-secret-key
    endpoint: https://s3.org-12345.zone1.google.gdch.test
    path_style: true
EOF

kubectl apply -f "${WORK_DIR}/gitlab-prereqs.yaml"

# Secret key MUST end with '.crt' for GitLab global.certificates.customCAs (update-ca-certificates)
kubectl create secret generic gitlab-db-ca \
  --from-file=gitlab-db-ca.crt="${WORK_DIR}/gitlab-db-ca.crt" \
  -n gitlab --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic harbor-creds \
  --from-file=.dockerconfigjson="${HOME}/.docker/config.json" \
  --type=kubernetes.io/dockerconfigjson \
  -n gitlab --dry-run=client -o yaml | kubectl apply -f -

kubectl patch serviceaccount default -n gitlab \
  -p '{"imagePullSecrets": [{"name": "harbor-creds"}]}'
```

If your User Cluster enforces project-wide default-deny egress policies, permit outbound `5432/TCP` from the `gitlab` namespace to your Zonal `DBCluster` VIP/subnet CIDR (`DBCLUSTER_SUBNET_CIDR`, plus cluster DNS and intra-cluster traffic):

```bash
export DBCLUSTER_SUBNET_CIDR="${DBCLUSTER_SUBNET_CIDR:-10.200.0.0/16}"

cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: gitlab-postgres-egress
  namespace: gitlab
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - namespaceSelector: {}
    - to:
        - ipBlock:
            cidr: ${DBCLUSTER_SUBNET_CIDR}
      ports:
        - protocol: TCP
          port: 5432
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 6443
EOF
```

Next, run a pre-install `Job` (`gitlab-db-bootstrap`) reusing `/usr/bin/psql` inside the already-mirrored `gitlab-toolbox-ee-17-11-7` image to create the `gitlab` role, transfer PostgreSQL 15 `public` schema ownership (`GRANT gitlab TO dbsadmin` is mandatory before `dbsadmin` can assign `OWNER gitlab` under `cloudsqlsuperuser`), and install `pg_trgm` and `btree_gist` inside `gitlabhq_production` **before** running `helm upgrade --install gitlab`:

> [!WARNING]
> **Why `command: ["/bin/bash", "-ec"]` Is Mandatory on `gitlab-toolbox-ee`:**
> The upstream `gitlab-toolbox-ee` image sets `ENTRYPOINT ["/scripts/entrypoint.sh"]`, which attempts to render Ruby `.erb` templates from GitLab ConfigMaps/Secrets that do not exist prior to `helm upgrade --install gitlab`. Always override `command:` (not just `args:`) in the pre-install bootstrap `Job`, and delete the temporary `gitlab-dbsadmin-bootstrap` Secret immediately after completion.

```bash
# 1. Create a short-lived dbsadmin credential Secret strictly for the one-shot bootstrap Job
kubectl create secret generic gitlab-dbsadmin-bootstrap \
  --from-literal=dbsadmin-password="${GITLAB_DB_ADMIN_PASSWORD}" \
  -n gitlab --dry-run=client -o yaml | kubectl apply -f -

# 2. Run idempotent pre-install bootstrap Job over verified TLS
kubectl delete job gitlab-db-bootstrap -n gitlab --ignore-not-found
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: gitlab-db-bootstrap
  namespace: gitlab
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 300
  template:
    spec:
      restartPolicy: Never
      imagePullSecrets:
        - name: harbor-creds
      containers:
        - name: psql-bootstrap
          image: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-toolbox-ee-17-11-7:v1.16.2-iac-1800e51e18
          command: ["/bin/bash", "-ec"]
          args:
            - |
              echo "Bootstrapping role 'gitlab' and database 'gitlabhq_production' on ${DB_HOST}:5432..."
              psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d postgres -v gitlab_pw="\${GITLAB_APP_PASSWORD}" <<'SQL'
              SELECT format('CREATE ROLE gitlab WITH LOGIN PASSWORD %L', :'gitlab_pw')
              WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gitlab') \gexec
              ALTER ROLE gitlab WITH PASSWORD :'gitlab_pw';
              GRANT gitlab TO dbsadmin;
              SELECT 'CREATE DATABASE gitlabhq_production OWNER gitlab'
              WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gitlabhq_production') \gexec
              SQL

              echo "Installing required GitLab extensions and PG 15 schema grants in gitlabhq_production..."
              psql -h "${DB_HOST}" -p 5432 -U dbsadmin -d gitlabhq_production <<'SQL'
              CREATE EXTENSION IF NOT EXISTS pg_trgm;
              CREATE EXTENSION IF NOT EXISTS btree_gist;
              GRANT ALL PRIVILEGES ON DATABASE gitlabhq_production TO gitlab;
              GRANT ALL ON SCHEMA public TO gitlab;
              ALTER SCHEMA public OWNER TO gitlab;
              SQL
              echo "GitLab Managed PostgreSQL bootstrap complete."
          env:
            - name: PGPASSWORD
              valueFrom:
                secretKeyRef:
                  name: gitlab-dbsadmin-bootstrap
                  key: dbsadmin-password
            - name: GITLAB_APP_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: gitlab-postgres-secret
                  key: postgresql-password
            - name: PGSSLMODE
              value: "verify-full"
            - name: PGSSLROOTCERT
              value: "/etc/gitlab-db-ca/gitlab-db-ca.crt"
          volumeMounts:
            - name: gitlab-db-ca
              mountPath: /etc/gitlab-db-ca
              readOnly: true
      volumes:
        - name: gitlab-db-ca
          secret:
            secretName: gitlab-db-ca
EOF

kubectl wait --for=condition=complete job/gitlab-db-bootstrap -n gitlab --timeout=120s
kubectl logs job/gitlab-db-bootstrap -n gitlab

# 3. Remove temporary dbsadmin credentials from the User Cluster immediately after bootstrap
kubectl delete secret gitlab-dbsadmin-bootstrap -n gitlab
kubectl delete job gitlab-db-bootstrap -n gitlab
```

<details>
<summary><strong>Alternative (Dev / Lab Stepping-Stone Only): In-Cluster Self-Managed PostgreSQL (<code>tenable/postgres:17</code>)</strong></summary>

In disconnected development or lab environments where Zonal DBS quota or `BackupRepository/dbs-backup-repository` is not yet provisioned, you can deploy a single-replica self-managed PostgreSQL container (`harbor.org-12345.zone1.google.gdch.test/library/tenable/postgres:17`, no HA, manual backups) inside `-n gitlab` instead of Sections 6.2–6.3 above. When using this lab fallback, set `global.psql.host: gitlab-postgresql.gitlab.svc.cluster.local` and omit `global.certificates.customCAs` and `global.extraEnv` (`PGSSLMODE` / `PGSSLROOTCERT`) in `gitlab-values.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gitlab-postgresql-init
  namespace: gitlab
data:
  init-extensions.sql: |
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS btree_gist;
    CREATE EXTENSION IF NOT EXISTS plpgsql;
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: gitlab-postgresql-pvc
  namespace: gitlab
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-rwo
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gitlab-postgresql
  namespace: gitlab
  labels:
    app: gitlab-postgresql
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: gitlab-postgresql
  template:
    metadata:
      labels:
        app: gitlab-postgresql
    spec:
      containers:
        - name: postgresql
          image: harbor.org-12345.zone1.google.gdch.test/library/tenable/postgres:17
          ports:
            - containerPort: 5432
              name: tcp-postgresql
          env:
            - name: POSTGRES_USER
              value: "gitlab"
            - name: POSTGRES_DB
              value: "gitlabhq_production"
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: gitlab-postgres-secret
                  key: postgresql-password
            - name: PGDATA
              value: "/var/lib/postgresql/data/pgdata"
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 1000m
              memory: 1Gi
          readinessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - pg_isready -U gitlab -d gitlabhq_production -h 127.0.0.1
            initialDelaySeconds: 5
            periodSeconds: 5
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
            - name: init-scripts
              mountPath: /docker-entrypoint-initdb.d
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: gitlab-postgresql-pvc
        - name: init-scripts
          configMap:
            name: gitlab-postgresql-init
---
apiVersion: v1
kind: Service
metadata:
  name: gitlab-postgresql
  namespace: gitlab
  labels:
    app: gitlab-postgresql
spec:
  type: ClusterIP
  ports:
    - port: 5432
      targetPort: 5432
      protocol: TCP
      name: tcp-postgresql
  selector:
    app: gitlab-postgresql
```

</details>

### 6.4 Step 3: Create GitLab 17.11.7 Helm Values (`gitlab-values.yaml`)

> [!IMPORTANT]
> **Server-Only TLS Configuration (`customCAs` + `global.extraEnv` vs. `global.psql.ssl`):**
> * **Do NOT set `global.psql.ssl`**: In `gitlab-8.11.7`, `global.psql.ssl` enforces mutual TLS (mTLS) and requires `clientCertificate` and `clientKey` alongside `serverCA`, whereas GDCag Managed PostgreSQL (`DBCluster`) uses server TLS + password authentication.
> * **Pair `global.certificates.customCAs` with `PGSSLROOTCERT`**: `global.certificates.customCAs` mounts `Secret/gitlab-db-ca` (`gitlab-db-ca.crt`) and merges it into `/etc/ssl/certs/ca-certificates.crt` via the `certificates` initContainer. However, Debian's `libpq5` inside CNG `17.11.7` looks for `~/.postgresql/root.crt` unless **`PGSSLROOTCERT: "/etc/ssl/certs/ca-certificates.crt"`** is explicitly exported under `global.extraEnv`.
> * **`PGSSLMODE` Hostname Verification**: `PGSSLMODE: "verify-full"` validates both the CA signature and the `.status.primary.url` DNS `subjectAltName` (`${DB_HOST}`). If connecting via a raw LoadBalancer IP or split-horizon alias absent from the certificate SANs, set `PGSSLMODE: "verify-ca"`.

Create `${WORK_DIR}/gitlab-values.yaml` (substituting `${DB_HOST}` resolved in Section 6.2):

```yaml
global:
  edition: ee
  gitlabVersion: "17.11.7"
  image:
    pullSecrets:
      - name: harbor-creds
  hosts:
    domain: org-12345.zone1.google.gdch.test
    https: true
    gitlab:
      name: gitlab.org-12345.zone1.google.gdch.test
  ingress:
    configureCertmanager: false
    provider: nginx
    enabled: true
    tls:
      enabled: true
  minio:
    enabled: false
  psql:
    # Set to ${DB_HOST} from Section 6.2 (stripped of ':5432')
    host: "<DB_HOST_FROM_SECTION_6_2>"
    port: 5432
    username: gitlab
    database: gitlabhq_production
    password:
      useSecret: true
      secret: gitlab-postgres-secret
      key: postgresql-password
  certificates:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-certificates-17-11-7
      tag: v1.16.2-iac-1800e51e18
    customCAs:
      - secret: gitlab-db-ca
  extraEnv:
    PGSSLMODE: "verify-full"
    PGSSLROOTCERT: "/etc/ssl/certs/ca-certificates.crt"
  redis:
    auth:
      enabled: true
  gitaly:
    enabled: true
    persistence:
      storageClass: standard-rwo
      size: 10Gi
  kubectl:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-kubectl-17-11-7
      tag: v1.16.2-iac-1800e51e18
  gitlabBase:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-base-17-11-7
      tag: v1.16.2-iac-1800e51e18
  appConfig:
    gitlab_kas:
      enabled: false
    object_store:
      enabled: false
    lfs:
      enabled: false
    artifacts:
      enabled: false
    uploads:
      enabled: false
    packages:
      enabled: false
    externalDiffs:
      enabled: false
    terraformState:
      enabled: false
    ciSecureFiles:
      enabled: false
    dependencyProxy:
      enabled: false

upgradeCheck:
  enabled: false

certmanager:
  install: false

prometheus:
  install: false

postgresql:
  install: false

gitlab-runner:
  install: false

registry:
  enabled: false

nginx-ingress:
  imagePullSecrets:
    - name: harbor-creds
  enabled: true
  controller:
    replicaCount: 1
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-cloud-native-mirror-images-ingress-nginx-controller-17-11-7
      tag: v1.16.2-iac-1800e51e18
      digest: ""

redis:
  install: true
  global:
    imagePullSecrets:
      - harbor-creds
  architecture: standalone
  image:
    registry: harbor.org-12345.zone1.google.gdch.test
    repository: gpc-system-container-images/private-cloud-staging/gitlab-operator-bitnamilegacy-redis-17-11-7
    tag: v1.16.2-iac-1800e51e18
  master:
    persistence:
      storageClass: standard-rwo
      size: 5Gi
  metrics:
    enabled: false
    image:
      registry: harbor.org-12345.zone1.google.gdch.test
      repository: gpc-system-container-images/private-cloud-staging/gitlab-operator-bitnamilegacy-redis-exporter-17-11-7
      tag: v1.16.2-iac-1800e51e18

shared-secrets:
  enabled: true
  selfsign:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-gitlab-org-build-cng-cfssl-self-sign-17-11-7
      tag: v1.16.2-iac-1800e51e18

gitlab:
  gitaly:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitaly-17-11-7
      tag: v1.16.2-iac-1800e51e18
    persistence:
      storageClass: standard-rwo
      size: 10Gi
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
  gitlab-exporter:
    enabled: false
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-exporter-17-11-7
      tag: v1.16.2-iac-1800e51e18
  gitlab-shell:
    minReplicas: 1
    maxReplicas: 1
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-shell-17-11-7
      tag: v1.16.2-iac-1800e51e18
    resources:
      requests:
        cpu: 50m
        memory: 64Mi
  kas:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-kas-17-11-7
      tag: v1.16.2-iac-1800e51e18
  migrations:
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-toolbox-ee-17-11-7
      tag: v1.16.2-iac-1800e51e18
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
  sidekiq:
    minReplicas: 1
    maxReplicas: 1
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-sidekiq-ee-17-11-7
      tag: v1.16.2-iac-1800e51e18
    resources:
      requests:
        cpu: 200m
        memory: 1Gi
  toolbox:
    enabled: true
    replicas: 1
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-toolbox-ee-17-11-7
      tag: v1.16.2-iac-1800e51e18
    backups:
      objectStorage:
        config:
          secret: gitlab-storage
          key: config
    resources:
      requests:
        cpu: 50m
        memory: 128Mi
  webservice:
    minReplicas: 1
    maxReplicas: 1
    image:
      repository: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-webservice-ee-17-11-7
      tag: v1.16.2-iac-1800e51e18
    workhorse:
      image: harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/gitlab-operator-gitlab-org-build-cng-gitlab-workhorse-ee-17-11-7
      tag: v1.16.2-iac-1800e51e18
    resources:
      requests:
        cpu: 300m
        memory: 1536Mi
```

> [!NOTE]
> **Day-2 Disaster Recovery Scope (`BackupPlan` + Gitaly + `gitlab-rails-secret`):**
> `BackupPlan/gitlab-db-backup` on `ZONE_KUBECONFIG` backs up only the Managed PostgreSQL `gitlab-db` cluster. A complete GitLab disaster recovery posture requires three coordinated artifacts:
> 1. **Relational State (`gitlab-db`)**: Automated daily Zonal `BackupPlan` (`postgresql.dbadmin.gdc.goog/v1`).
> 2. **Git Repositories & Assets (`gitaly`)**: Periodic `kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- backup-utility --skip db` (uploading tarballs to `gitlab-storage` S3) or User Cluster PVC snapshots for `repo-data-gitlab-gitaly-0`.
> 3. **Application Encryption Keys (`gitlab-rails-secret`)**: Securely archive `kubectl get secret -n gitlab gitlab-rails-secret -o yaml` (encrypted via SOPS); without `db_key_base` and `otp_key_base`, encrypted columns inside a restored `gitlabhq_production` backup cannot be decrypted.

### 6.5 Step 4: Install GitLab 17.11.7 & Seed CI OIDC Signing Keys

Install the GitLab Helm chart (passing `--set global.psql.host="${DB_HOST}"` to inject the Zonal `DBCluster` primary hostname) and ensure the database is seeded and `ci_jwt_signing_key` is populated so GitLab exposes its OIDC discovery keys at `/oauth/discovery/keys`:

```bash
# 1. Install GitLab 17.11.7 from Project Harbor against Managed PostgreSQL (${DB_HOST})
GODEBUG=tlsmlkem=0 helm upgrade --install gitlab \
  "oci://harbor001-iac-root.org-12345.zone1.google.gdch.test/charts/gitlab" \
  --version 8.11.7 \
  -n gitlab \
  -f "${WORK_DIR}/gitlab-values.yaml" \
  --set global.psql.host="${DB_HOST}" \
  --insecure-skip-tls-verify \
  --timeout 10m

# 2. If gitlab-migrations restarted on first boot while waiting for Redis PVC attachment,
#    ensure root user seeding and ci_jwt_signing_key generation are completed:
ROOT_PASS=$(kubectl get secret -n gitlab gitlab-gitlab-initial-root-password -o jsonpath='{.data.password}' | base64 -d)
kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- \
  env GITLAB_ROOT_PASSWORD="${ROOT_PASS}" /srv/gitlab/bin/rake db:seed_fu

kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- /srv/gitlab/bin/rails runner '
  settings = ApplicationSetting.current_without_cache
  if settings.ci_jwt_signing_key.blank?
    settings.update_column(:ci_jwt_signing_key, OpenSSL::PKey::RSA.new(2048).to_pem)
  end
  puts "CI JWT Signing Key Present: #{settings.ci_jwt_signing_key.present?}"
'
```

### 6.6 Step 5: Verify GitLab Pods, PVCs, Services, Ingress & API Endpoints

```bash
kubectl get pods,pvc,svc,ingress -n gitlab -o wide
```

**Expected User Cluster Output (with PostgreSQL hosted externally on Zonal `DBCluster/gitlab-db`):**
```text
NAME                                                  READY   STATUS      RESTARTS        AGE   IP             NODE
pod/gitlab-gitaly-0                                   1/1     Running     0               14m   10.99.25.110   vm-9eeae553
pod/gitlab-gitlab-shell-854f75485b-stqmr              1/1     Running     0               14m   10.99.25.148   vm-9eeae553
pod/gitlab-kas-74c7f59c46-c6ftp                       1/1     Running     5 (11m ago)     14m   10.99.25.67    vm-9eeae553
pod/gitlab-kas-74c7f59c46-gwbh2                       1/1     Running     5 (12m ago)     14m   10.99.25.6     vm-9eeae553
pod/gitlab-migrations-8aa9b56-nnbd7                   0/1     Completed   3               14m   10.99.25.5     vm-9eeae553
pod/gitlab-nginx-ingress-controller-7d64c4c4f-q4snc   1/1     Running     0               14m   10.99.25.8     vm-9eeae553
pod/gitlab-redis-master-0                             1/1     Running     0               14m   10.99.25.97    vm-9eeae553
pod/gitlab-sidekiq-all-in-1-v2-d978886fc-swlxv        1/1     Running     1 (10m ago)     14m   10.99.25.245   vm-9eeae553
pod/gitlab-toolbox-76d9b44f57-rnpkm                   1/1     Running     0               14m   10.99.25.159   vm-9eeae553
pod/gitlab-webservice-default-689bd9d6cc-ljj49        2/2     Running     2 (8m51s ago)   14m   10.99.25.63    vm-9eeae553

NAME                                                     STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS
persistentvolumeclaim/redis-data-gitlab-redis-master-0   Bound    pvc-c03808aa-02b0-4b7e-be0a-d3279260496d   5Gi       RWO            standard-rwo
persistentvolumeclaim/repo-data-gitlab-gitaly-0          Bound    pvc-34a26467-562c-4f66-966e-a46e97f57916   10Gi      RWO            standard-rwo

NAME                                              TYPE           CLUSTER-IP     EXTERNAL-IP    PORT(S)
service/gitlab-nginx-ingress-controller           LoadBalancer   10.99.16.69    10.136.68.48   80:31591/TCP,443:32453/TCP,22:30503/TCP
service/gitlab-redis-master                       ClusterIP      10.99.16.163   <none>         6379/TCP
service/gitlab-webservice-default                 ClusterIP      10.99.17.192   <none>         8080/TCP,8181/TCP,8083/TCP

NAME                                                  CLASS          HOSTS                                     ADDRESS        PORTS
ingress.networking.k8s.io/gitlab-kas                  gitlab-nginx   kas.org-12345.zone1.google.gdch.test      10.136.68.48   80, 443
ingress.networking.k8s.io/gitlab-webservice-default   gitlab-nginx   gitlab.org-12345.zone1.google.gdch.test   10.136.68.48   80, 443
```

Verify GitLab HTTPS health, readiness, version API, and OIDC JWKS discovery endpoints inside the cluster (via `deploy/gitlab-toolbox` targeting the internal MetalLB VIP `10.136.68.48`, or from the workstation via `kubectl port-forward -n gitlab svc/gitlab-nginx-ingress-controller 8443:443`):

```bash
kubectl get secret -n gitlab gitlab-wildcard-tls-ca -o jsonpath='{.data.cfssl_ca}' | base64 -d > "${WORK_DIR}/gitlab-ca.pem"

kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- \
  curl -sk --resolve "gitlab.org-12345.zone1.google.gdch.test:443:10.136.68.48" \
  https://gitlab.org-12345.zone1.google.gdch.test/-/health

kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- \
  curl -sk --resolve "gitlab.org-12345.zone1.google.gdch.test:443:10.136.68.48" \
  https://gitlab.org-12345.zone1.google.gdch.test/-/readiness

ROOT_TOKEN=$(kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- /srv/gitlab/bin/rails runner '
  user = User.find_by_username("root")
  token = user.personal_access_tokens.create!(name: "verify-api", scopes: [:api], expires_at: 7.days.from_now)
  puts token.token
' | tail -n 1 | tr -d '\r')

kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- \
  curl -sk -H "PRIVATE-TOKEN: ${ROOT_TOKEN}" \
  --resolve "gitlab.org-12345.zone1.google.gdch.test:443:10.136.68.48" \
  https://gitlab.org-12345.zone1.google.gdch.test/api/v4/version

kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- \
  curl -sk --resolve "gitlab.org-12345.zone1.google.gdch.test:443:10.136.68.48" \
  https://gitlab.org-12345.zone1.google.gdch.test/oauth/discovery/keys
```

**Verified Endpoint Responses:**
```text
GitLab OK
{"status":"ok","master_check":[{"status":"ok"}]}
{"version":"17.11.7-ee","revision":"5f9db3887f3","kas":{"enabled":true,"externalUrl":"wss://kas.org-12345.zone1.google.gdch.test","version":"17.11.6"},"enterprise":true}
{"keys":[{"kty":"RSA","kid":"MGGp73ZkTHLaa4v5gx26MWAXlONNkYbsi8ghThxcv_k","e":"AQAB","n":"...","use":"sig","alg":"RS256"},{"kty":"RSA","kid":"jV8yd6Pqke5faAkhUW24euUHMIRimkdXhB84J6ue01I","e":"AQAB","n":"...","use":"sig","alg":"RS256"}]}
```

---

## 7. GitLab & HashiCorp Vault Integration

This section configures HashiCorp Vault to serve secrets to GitLab CI pipelines (via **JWT/OIDC Auth**) and GitLab Kubernetes workloads (via **Kubernetes Auth** and the **Vault Agent Sidecar Injector**).

### 7.1 Step 1: Enable KVv2 Secrets Engine, Write Secrets & Create Vault Policy

Execute the following commands inside `vault-0`:

```bash
export VAULT_ROOT_TOKEN=$(jq -r '.root_token' "${WORK_DIR}/vault-init.json")

kubectl -n vault exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  # 1. Enable KVv2 secrets engine at secret/
  vault secrets enable -path=secret kv-v2 || true

  # 2. Store GitLab CI and application secrets
  vault kv put secret/gitlab/ci-demo \
    DB_USER="gitlab_ci" \
    DB_PASS="GdcVaultKms2026!" \
    API_KEY="glpat-vault-kms-verified"

  vault kv put secret/gitlab/app \
    APP_ENV="production" \
    KMS_KEY="namespaces/iac-root/aeadKeys/vault-unseal-key"

  # 3. Create read-only policy for GitLab CI and workload pods
  vault policy write gitlab-ci-policy - <<EOF
path "secret/data/gitlab/*" {
  capabilities = ["read", "list"]
}
path "secret/metadata/gitlab/*" {
  capabilities = ["read", "list"]
}
EOF
'
```

### 7.2 Step 2: Configure Vault JWT Authentication (`auth/jwt`) for GitLab CI Pipelines

Configure Vault's `jwt` auth method to verify GitLab CI `id_tokens` against GitLab's internal Kubernetes Service JWKS URL (`http://gitlab-webservice-default.gitlab.svc.cluster.local:8080/oauth/discovery/keys`):

```bash
kubectl -n vault exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  # 1. Enable JWT auth method
  vault auth enable jwt || true

  # 2. Point JWKS URL to the internal GitLab webservice endpoint
  vault write auth/jwt/config \
    jwks_url="http://gitlab-webservice-default.gitlab.svc.cluster.local:8080/oauth/discovery/keys" \
    bound_issuer="https://gitlab.org-12345.zone1.google.gdch.test"

  # 3. Create a bound role for GitLab project ID 1 (root/vault-kms-demo)
  vault write auth/jwt/role/gitlab-ci-role \
    role_type="jwt" \
    policies="gitlab-ci-policy" \
    token_ttl="1h" \
    token_max_ttl="4h" \
    user_claim="user_login" \
    bound_audiences="https://vault.org-12345.zone1.google.gdch.test" \
    bound_claims_type="string" \
    bound_claims="{\"project_id\":\"1\"}"
'
```

#### Example `.gitlab-ci.yml` Job Consuming Vault Secrets via `id_tokens`

```yaml
stages:
  - verify-secrets

fetch_vault_secrets:
  stage: verify-secrets
  image: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault:1.15.0
  id_tokens:
    VAULT_ID_TOKEN:
      aud: https://vault.org-12345.zone1.google.gdch.test
  variables:
    VAULT_ADDR: "http://vault.vault.svc.cluster.local:8200"
  script:
    - export VAULT_TOKEN="$(vault write -field=token auth/jwt/login role=gitlab-ci-role jwt=$VAULT_ID_TOKEN)"
    - vault kv get secret/gitlab/ci-demo
```

### 7.3 Step 3: Configure Vault Kubernetes Auth (`auth/kubernetes`) & Sidecar Injection

Configure Vault's `kubernetes` auth method to allow workloads in the `gitlab` namespace to authenticate using their Kubernetes ServiceAccount JWTs, and deploy a pod annotated for the **Vault Agent Sidecar Injector (`vault-k8s:1.7.2`)**:

```bash
kubectl -n vault exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  # 1. Enable Kubernetes auth method
  vault auth enable kubernetes || true

  # 2. Configure Kubernetes API connection using in-cluster service account
  vault write auth/kubernetes/config \
    kubernetes_host="https://${KUBERNETES_PORT_443_TCP_ADDR}:443"

  # 3. Create role bound to GitLab namespace ServiceAccounts
  vault write auth/kubernetes/role/gitlab-role \
    bound_service_account_names="default,gitlab-vault-sa,gitlab-webservice,gitlab-sidekiq,gitlab-toolbox,vault" \
    bound_service_account_namespaces="gitlab,vault,default" \
    policies="gitlab-ci-policy" \
    ttl=1h
'
```

Deploy a workload pod in namespace `gitlab` (`gitlab-vault-agent-pod.yaml`) that uses Vault Agent Mutating Webhook annotations to inject `secret/data/gitlab/ci-demo` into `/vault/secrets/ci-demo`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gitlab-vault-agent-test
  namespace: gitlab
  labels:
    app: gitlab-vault-agent-test
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "gitlab-role"
    vault.hashicorp.com/agent-inject-secret-ci-demo: "secret/data/gitlab/ci-demo"
    vault.hashicorp.com/agent-inject-template-ci-demo: |
      {{- with secret "secret/data/gitlab/ci-demo" -}}
      export API_KEY="{{ .Data.data.API_KEY }}"
      export DB_USER="{{ .Data.data.DB_USER }}"
      export DB_PASS="{{ .Data.data.DB_PASS }}"
      {{- end }}
spec:
  serviceAccountName: default
  containers:
    - name: app
      image: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/alpine:latest
      command: ["sh", "-c", "sleep 3600"]
      resources:
        requests:
          cpu: 50m
          memory: 64Mi
```

```bash
kubectl apply -f "${WORK_DIR}/gitlab-vault-agent-pod.yaml"
kubectl wait --for=condition=Ready pod/gitlab-vault-agent-test -n gitlab --timeout=60s
kubectl get pod gitlab-vault-agent-test -n gitlab -o wide
kubectl exec -n gitlab gitlab-vault-agent-test -c app -- cat /vault/secrets/ci-demo
```

**Verified Vault Agent Sidecar Output (`2/2 Running`):**
```text
NAME                      READY   STATUS    RESTARTS   AGE   IP            NODE          NOMINATED NODE   READINESS GATES
gitlab-vault-agent-test   2/2     Running   0          31s   10.99.25.39   vm-9eeae553   <none>           <none>
export API_KEY="glpat-vault-kms-verified"
export DB_USER="gitlab_ci"
export DB_PASS="GdcVaultKms2026!"
```

---

## 8. Consuming Vault Secrets in Applications & GitLab

Once HashiCorp Vault is running and auto-unsealed via GDCag KMS, application workloads deployed on the User Cluster (`iac-root-2ad0c4dd`) and CI/CD pipelines running in GitLab can consume secrets directly from Vault using four production patterns:

* **Pattern A - Zero-Code Consumption via Vault Agent Sidecar Injector**: The `vault-agent-injector` mutating webhook injects an init/sidecar container that renders Vault secrets onto an in-memory `tmpfs` volume (`/vault/secrets/*`) as environment files or JSON/YAML configuration files.
* **Pattern B - Direct In-Application Consumption via Vault HTTP API / SDK (No Sidecar)**: The application authenticates directly to `http://vault.vault.svc.cluster.local:8200/v1/auth/kubernetes/login` using its mounted Kubernetes `ServiceAccount` JWT and fetches secrets over HTTP without sidecar containers or external library dependencies.
* **Pattern C - Consuming Vault Secrets in GitLab CI/CD Pipelines**: GitLab CI jobs authenticate via short-lived OIDC `id_tokens` (`auth/jwt`) using either GitLab Runner's native `secrets:` keyword or direct Vault CLI / HTTP API calls.
* **Pattern D - Dynamic Short-Lived PostgreSQL Credentials (`database/` Secrets Engine)**: Vault connects over verified TLS (`5432/TCP`) to a GDCag Managed PostgreSQL `DBCluster` (`postgresql.dbadmin.gdc.goog/v1`), dynamically minting per-pod PostgreSQL roles that expire and revoke automatically when the pod's lease ends.

### 8.1 Onboarding an Application Namespace & ServiceAccount in Vault

Before an application in a tenant namespace (for example, `my-app-ns`) can read secrets from Vault, provision its Kubernetes `ServiceAccount`, seed its secrets under a dedicated KVv2 path (`secret/apps/my-app/*`), and bind a least-privilege Vault Kubernetes Auth role:

```bash
# 1. Create the application namespace, dedicated ServiceAccount, and Harbor pull secret
kubectl create namespace my-app-ns --dry-run=client -o yaml | kubectl apply -f -
kubectl create serviceaccount my-app-sa -n my-app-ns --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic harbor-creds \
  --from-file=.dockerconfigjson="${HOME}/.docker/config.json" \
  --type=kubernetes.io/dockerconfigjson \
  -n my-app-ns --dry-run=client -o yaml | kubectl apply -f -

kubectl patch serviceaccount my-app-sa -n my-app-ns \
  -p '{"imagePullSecrets": [{"name": "harbor-creds"}]}'

# 2. Seed application secrets, create a least-privilege ACL policy, and bind a Kubernetes Auth role in Vault
export VAULT_ROOT_TOKEN=$(jq -r '.root_token' "${WORK_DIR}/vault-init.json")

kubectl -n vault exec -i vault-0 -c vault -- env VAULT_TOKEN="${VAULT_ROOT_TOKEN}" sh -c '
  # Write application secrets to KVv2 (mounted at secret/, pointing at the tenant Managed DBCluster host)
  vault kv put secret/apps/my-app/config \
    DB_HOST="my-app-db-primary.iac-root.dbs.org-12345.zone1.google.gdch.test" \
    DB_PORT="5432" \
    DB_USER="my_app_user" \
    DB_PASSWORD="AppVaultSecretPassword2026!" \
    API_SIGNING_KEY="gdc-kms-backed-hmac-key"

  # Create a read-only Vault policy scoped strictly to secret/data/apps/my-app/*
  vault policy write my-app-policy - <<EOF
path "secret/data/apps/my-app/*" {
  capabilities = ["read"]
}
path "secret/metadata/apps/my-app/*" {
  capabilities = ["read", "list"]
}
EOF

  # Bind Kubernetes ServiceAccount my-app-ns/my-app-sa to my-app-policy
  vault write auth/kubernetes/role/my-app-role \
    bound_service_account_names="my-app-sa" \
    bound_service_account_namespaces="my-app-ns" \
    policies="my-app-policy" \
    ttl="1h" \
    max_ttl="24h"
'
```

### 8.2 Pattern A: Zero-Code Consumption via Vault Agent Sidecar Injector

Use **Pattern A** when you want applications to consume Vault secrets as standard files or environment variables without writing any Vault API code in the application itself.

#### Architecture & Secret Delivery Flow (Pattern A)

```text
[ Pattern A: Zero-Code Secret Consumption via Vault Agent Sidecar Injector ]
====================================================================================================

  (1) Pod Creation (vault.hashicorp.com/agent-inject: "true", role: "my-app-role")
       │
       ▼
  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Mutating Admission Webhook: vault-agent-injector (Namespace: vault, Image: vault-k8s:1.7.2)  │
  │  • Intercepts Pod CREATE request and injects:                                                │
  │    - Init Container:    vault-agent-init (pre-populates secrets before app starts)           │
  │    - Sidecar Container: vault-agent      (renews lease & live-rotates secrets in background) │
  │    - In-Memory Volume:  emptyDir (medium: Memory) mounted at /vault/secrets                  │
  └──────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                 │ (2) Mutated Pod Scheduled
                                                 ▼
  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Application Pod: my-app-sidecar (Namespace: my-app-ns | ServiceAccount: my-app-sa)           │
  │                                                                                              │
  │  ┌────────────────────────────────────────┐        ┌──────────────────────────────────────┐  │
  │  │ Init / Sidecar: vault-agent (v1.15.0)  │        │ Shared In-Memory Volume (tmpfs)      │  │
  │  │  • Reads projected K8s SA JWT:         │        │ Mount: /vault/secrets                │  │
  │  │    /var/run/secrets/k8s.io/.../token   │        │                                      │  │
  │  │  • Evaluates Consul Templates          │───────►│  • /vault/secrets/config.env         │  │
  │  │  • Polls KVv2 & re-renders on rotation │ (5)    │    (export DB_HOST=..., DB_PASS=...) │  │
  │  │    (agent-pre-populate-only: "false")  │ Writes │  • /vault/secrets/config.json        │  │
  │  └───────────────────┬────────────────────┘        │    ({ "DB_HOST": "...", ... })       │  │
  │                      │                             └──────────────────┬───────────────────┘  │
  │                      │                                                │ (6) Sources .env &   │
  │                      │                                                ▼     reads .json      │
  │                      │                             ┌──────────────────────────────────────┐  │
  │                      │                             │ Application Container: app           │  │
  │                      │                             │  • Entrypoint: . /vault/secrets/     │  │
  │                      │                             │    config.env && exec <app-binary>   │  │
  │                      │                             │  • Zero Vault SDK / API code needed  │  │
  │                      │                             └──────────────────────────────────────┘  │
  └──────────────────────┼───────────────────────────────────────────────────────────────────────┘
                         │
                         │ (3) POST /v1/auth/kubernetes/login (role="my-app-role", jwt=<my-app-sa>)
                         │ (4) GET  /v1/secret/data/apps/my-app/config (X-Vault-Token: <client_token>)
                         ▼
  ┌────────────────────────────────────────────────────┐      ┌──────────────────────────────────┐
  │ HashiCorp Vault: vault-0 (Namespace: vault)        │ (3a) │ Kubernetes API Server            │
  │  http://vault.vault.svc.cluster.local:8200         │─────►│  POST /apis/authentication.k8s   │
  │  • Validates JWT via TokenReview & my-app-policy   │◄─────│       .io/v1/tokenreviews        │
  │  • Returns KVv2 secret (unsealed via GDCag KMS)    │      │  Verifies my-app-ns/my-app-sa    │
  └────────────────────────────────────────────────────┘      └──────────────────────────────────┘
```

#### How It Works
1. When a pod with `vault.hashicorp.com/agent-inject: "true"` is submitted, the `vault-agent-injector` mutating webhook injects a `vault-agent-init` init container (which authenticates via `auth/kubernetes` and renders secrets into `/vault/secrets/*` before the application container starts) and, by default, a `vault-agent` sidecar container.
2. When `vault.hashicorp.com/agent-pre-populate-only` is `"false"` (the default), the `vault-agent` sidecar remains running alongside the application, automatically renews its Vault token lease, polls KVv2 for secret updates, and re-renders `/vault/secrets/*` in place whenever a secret is rotated in Vault.

#### Key Vault Agent Injector Annotations

| Annotation | Example Value | Purpose |
| :--- | :--- | :--- |
| `vault.hashicorp.com/agent-inject` | `"true"` | Enables Vault Agent init/sidecar injection on the Pod. |
| `vault.hashicorp.com/role` | `"my-app-role"` | Vault Kubernetes Auth role used to authenticate the pod's `ServiceAccount`. |
| `vault.hashicorp.com/agent-pre-populate-only` | `"false"` | `"false"` keeps the sidecar running for live secret rotation; `"true"` injects only the init container (ideal for one-shot `Job`s). |
| `vault.hashicorp.com/agent-inject-secret-<file>` | `"secret/data/apps/my-app/config"` | Mounts the secret at `/vault/secrets/<file>`. |
| `vault.hashicorp.com/agent-inject-template-<file>` | Consul Template string | Formats `/vault/secrets/<file>` as `export KEY="VAL"`, JSON, YAML, or properties files. |
| `vault.hashicorp.com/agent-inject-command-<file>` | `"kill -HUP $(pidof myapp)"` | Optional command executed when `<file>` is re-rendered after a secret rotation (requires `shareProcessNamespace: true` if signaling the app process). |

#### Example `Deployment` Rendering Both Environment Exports and a JSON Config File

Create `${WORK_DIR}/my-app-sidecar-deployment.yaml` to render `/vault/secrets/config.env` (sourced as environment variables at container startup) and `/vault/secrets/config.json` (read directly by the application):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app-sidecar
  namespace: my-app-ns
  labels:
    app: my-app-sidecar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: my-app-sidecar
  template:
    metadata:
      labels:
        app: my-app-sidecar
      annotations:
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "my-app-role"
        vault.hashicorp.com/agent-pre-populate-only: "false"
        # 1. Render shell environment exports to /vault/secrets/config.env
        vault.hashicorp.com/agent-inject-secret-config.env: "secret/data/apps/my-app/config"
        vault.hashicorp.com/agent-inject-template-config.env: |
          {{- with secret "secret/data/apps/my-app/config" -}}
          export DB_HOST="{{ .Data.data.DB_HOST }}"
          export DB_PORT="{{ .Data.data.DB_PORT }}"
          export DB_USER="{{ .Data.data.DB_USER }}"
          export DB_PASSWORD="{{ .Data.data.DB_PASSWORD }}"
          export API_SIGNING_KEY="{{ .Data.data.API_SIGNING_KEY }}"
          {{- end }}
        # 2. Render structured JSON configuration to /vault/secrets/config.json
        vault.hashicorp.com/agent-inject-secret-config.json: "secret/data/apps/my-app/config"
        vault.hashicorp.com/agent-inject-template-config.json: |
          {{- with secret "secret/data/apps/my-app/config" -}}
          {{ .Data.data | toJSONPretty }}
          {{- end }}
    spec:
      serviceAccountName: my-app-sa
      containers:
        - name: app
          image: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/alpine:latest
          # Source /vault/secrets/config.env before launching the application binary
          command: ["/bin/sh", "-c"]
          args:
            - |
              set -a
              . /vault/secrets/config.env
              set +a
              echo "Loaded DB_USER=${DB_USER} for DB_HOST=${DB_HOST}:${DB_PORT}"
              cat /vault/secrets/config.json
              exec sleep 3600
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
```

### 8.3 Pattern B: Direct In-Application Consumption via Vault HTTP API / SDK (No Sidecar)

Use **Pattern B** when applications require direct programmatic access to Vault secrets on demand without running a sidecar container in the Pod.

#### Architecture & Secret Delivery Flow (Pattern B)

```text
[ Pattern B: Direct In-Application Consumption via Vault HTTP API / SDK (No Sidecar) ]
====================================================================================================

  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Single-Container Application Pod (Namespace: my-app-ns | ServiceAccount: my-app-sa)          │
  │                                                                                              │
  │  ┌────────────────────────────────────────┐        ┌──────────────────────────────────────┐  │
  │  │ Application Container: app (1/1)       │  (1)   │ Projected K8s ServiceAccount Volume  │  │
  │  │  (Python urllib.request / curl / Go)   │◄───────│  /var/run/secrets/kubernetes.io/     │  │
  │  │                                        │ Reads  │  serviceaccount/token                │  │
  │  │  • Caches client_token in memory       │  JWT   │  (Short-lived K8s ServiceAccount JWT)│  │
  │  │  • Fetches KVv2 secrets on demand      │        └──────────────────────────────────────┘  │
  │  │  • Renews lease before TTL expiry      │                                                  │
  │  └───────────┬───────────────────────┬────┘                                                  │
  └──────────────┼───────────────────────┼───────────────────────────────────────────────────────┘
                 │                       │
                 │ (2) POST /v1/auth/    │ (4) GET /v1/secret/data/apps/my-app/config
                 │     kubernetes/login  │     Header: X-Vault-Token: <client_token>
                 │     (role, jwt)       │ (5) POST /v1/auth/token/renew-self
                 │ (3) Returns           │     (Renews lease before 1h TTL expiry)
                 │     client_token      │
                 ▼                       ▼
  ┌────────────────────────────────────────────────────┐      ┌──────────────────────────────────┐
  │ HashiCorp Vault: vault-0 (Namespace: vault)        │ (2a) │ Kubernetes API Server            │
  │  http://vault.vault.svc.cluster.local:8200         │─────►│  POST /apis/authentication.k8s   │
  │  • Verifies SA JWT via K8s TokenReview API         │◄─────│       .io/v1/tokenreviews        │
  │  • Enforces ACL policy: my-app-policy              │      │  Confirms my-app-ns/my-app-sa    │
  │  • Serves secret/data/apps/my-app/config           │      └──────────────────────────────────┘
  └────────────────────────────────────────────────────┘
```

#### How Direct Kubernetes Auth Works Inside a Pod
1. Kubernetes automatically mounts a projected ServiceAccount token at `/var/run/secrets/kubernetes.io/serviceaccount/token` inside the container (as long as `automountServiceAccountToken` is not set to `false`).
2. The application sends `POST http://vault.vault.svc.cluster.local:8200/v1/auth/kubernetes/login` with body `{"role": "my-app-role", "jwt": "<serviceaccount-jwt>"}`.
3. Vault validates the JWT against the cluster's `TokenReview` API and returns `.auth.client_token` and `.auth.lease_duration`.
4. The application caches `client_token` in memory, sends `GET http://vault.vault.svc.cluster.local:8200/v1/secret/data/apps/my-app/config` with header `X-Vault-Token: <client_token>`, and renews the token before expiry via `POST /v1/auth/token/renew-self`.

#### Example 1: Zero-Dependency Python 3 Client (`urllib.request` Standard Library)

In air-gapped GDCag containers where external PyPI packages (`hvac`, `requests`) may not be installed, use Python's built-in `urllib.request` and `json` modules to authenticate, cache/renew the Vault token, and fetch KVv2 secrets:

```python
#!/usr/bin/env python3
"""Zero-dependency Vault Kubernetes Auth + KVv2 client for GDCag workloads."""

import json
import os
import time
import urllib.error
import urllib.request

VAULT_ADDR = os.getenv("VAULT_ADDR", "http://vault.vault.svc.cluster.local:8200")
VAULT_ROLE = os.getenv("VAULT_ROLE", "my-app-role")
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


class VaultK8sClient:
    def __init__(self, vault_addr: str = VAULT_ADDR, role: str = VAULT_ROLE):
        self.vault_addr = vault_addr.rstrip("/")
        self.role = role
        self._token: str = ""
        self._token_expiry: float = 0.0

    def _request(self, method: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
        url = f"{self.vault_addr}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Vault-Token"] = token
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_token(self) -> str:
        now = time.time()
        # Reuse cached token if at least 60 seconds of lease remain
        if self._token and now < (self._token_expiry - 60):
            return self._token

        # Attempt in-place token renewal first if we already hold a token
        if self._token:
            try:
                renewed = self._request("POST", "/v1/auth/token/renew-self", {}, token=self._token)
                ttl = int(renewed["auth"]["lease_duration"])
                self._token_expiry = time.time() + ttl
                return self._token
            except Exception:
                self._token = ""

        # Otherwise perform a fresh Kubernetes ServiceAccount JWT login
        with open(SA_TOKEN_PATH, "r", encoding="utf-8") as f:
            k8s_jwt = f.read().strip()

        login_resp = self._request(
            "POST",
            "/v1/auth/kubernetes/login",
            payload={"role": self.role, "jwt": k8s_jwt},
        )
        self._token = login_resp["auth"]["client_token"]
        ttl = int(login_resp["auth"]["lease_duration"])
        self._token_expiry = time.time() + ttl
        return self._token

    def read_kv2(self, mount: str, path: str) -> dict:
        token = self.get_token()
        resp = self._request("GET", f"/v1/{mount}/data/{path.lstrip('/')}", token=token)
        return resp["data"]["data"]


if __name__ == "__main__":
    client = VaultK8sClient()
    secrets = client.read_kv2(mount="secret", path="apps/my-app/config")
    print(f"Successfully fetched {len(secrets)} keys from Vault for DB_USER={secrets.get('DB_USER')}")
```

#### Example 2: Direct POSIX Shell (`curl` + `jq`) Entrypoint Wrapper (No Sidecar)

For container images that include `curl` and `jq`, the following entrypoint script exchanges the pod's ServiceAccount token at `/v1/auth/kubernetes/login`, exports every key from `secret/data/apps/my-app/config` into the process environment, and `exec`s the main application process:

```bash
#!/bin/sh
set -eu

VAULT_ADDR="${VAULT_ADDR:-http://vault.vault.svc.cluster.local:8200}"
VAULT_ROLE="${VAULT_ROLE:-my-app-role}"
SECRET_PATH="${SECRET_PATH:-secret/data/apps/my-app/config}"

# 1. Read projected Kubernetes ServiceAccount JWT
K8S_JWT=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)

# 2. Authenticate to Vault via auth/kubernetes/login
VAULT_TOKEN=$(curl -sfS --request POST \
  --data "{\"role\": \"${VAULT_ROLE}\", \"jwt\": \"${K8S_JWT}\"}" \
  "${VAULT_ADDR}/v1/auth/kubernetes/login" | jq -r '.auth.client_token')

# 3. Fetch KVv2 secret JSON and export each key=value into environment
SECRET_JSON=$(curl -sfS -H "X-Vault-Token: ${VAULT_TOKEN}" \
  "${VAULT_ADDR}/v1/${SECRET_PATH}")

eval "$(printf '%s' "${SECRET_JSON}" | jq -r '.data.data | to_entries[] | "export \(.key)=\(.value | @sh)"')"

# 4. Replace shell with the target application process
exec "$@"
```

### 8.4 Pattern C: Consuming Vault Secrets in GitLab CI/CD Pipelines

GitLab CI/CD jobs authenticate to Vault without static tokens by using per-job RS256 OIDC `id_tokens` verified by Vault's `auth/jwt` backend (configured in Section 7.2).

#### Architecture & Secret Delivery Flow (Pattern C)

```text
[ Pattern C: Consuming Vault Secrets in GitLab CI/CD Pipelines via OIDC id_tokens ]
====================================================================================================

  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
  │ GitLab Control Plane (Namespace: gitlab | https://gitlab.org-12345.zone1.google.gdch.test)   │
  │  • Mints per-job RS256 OIDC JWT (VAULT_ID_TOKEN) signed by ci_jwt_signing_key:               │
  │    - iss: "https://gitlab.org-12345.zone1.google.gdch.test"                                  │
  │    - aud: "https://vault.org-12345.zone1.google.gdch.test"                                   │
  │    - claims: {"project_id": "1", "user_login": "root", "ref": "main"}                        │
  │  • Publishes public signing keys at:                                                         │
  │    http://gitlab-webservice-default.gitlab.svc.cluster.local:8080/oauth/discovery/keys       │
  └─────────────────────────┬───────────────────────────────────────────────────▲────────────────┘
                            │ (1) Injects VAULT_ID_TOKEN into CI Job            │
                            ▼                                                   │ (2a) GET /oauth/
  ┌──────────────────────────────────────────────────────────┐                  │   discovery/keys
  │ GitLab Runner / CI Job Pod                               │                  │   (JWKS Public
  │                                                          │                  │    RSA Keys)
  │  • Method 1 (Native Runner `secrets:` keyword):          │                  │
  │    Runner exchanges $VAULT_ID_TOKEN before `script:` &   │                  │
  │    injects DB_USER, DB_PASS, API_KEY as env vars.        │                  │
  │  • Method 2 (Direct `script:` Vault CLI / HTTP API):     │                  │
  │    Job runs `vault write auth/jwt/login` or `curl` &     │                  │
  │    fetches `vault kv get secret/gitlab/ci-demo`.         │                  │
  └─────────────────────────┬────────────────────────────────┘                  │
                            │                                                   │
                            │ (2) POST /v1/auth/jwt/login                       │
                            │     {"role":"gitlab-ci-role","jwt":"<id_token>"}  │
                            │ (3) GET  /v1/secret/data/gitlab/ci-demo           │
                            │     Header: X-Vault-Token: <client_token>         │
                            ▼                                                   │
  ┌─────────────────────────────────────────────────────────────────────────────┴────────────────┐
  │ HashiCorp Vault: vault-0 (Namespace: vault | http://vault.vault.svc.cluster.local:8200)      │
  │  • Verifies RS256 JWT signature against GitLab JWKS endpoint (/oauth/discovery/keys)         │
  │  • Validates bound_issuer, bound_audiences, and bound_claims ({"project_id": "1"})           │
  │  • Issues token with gitlab-ci-policy and returns secret/data/gitlab/ci-demo                 │
  └──────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Method 1: Native GitLab Runner `secrets:` Keyword Integration

When using GitLab Runner (`16.0+`), declare `id_tokens:` alongside the `secrets:` keyword in `.gitlab-ci.yml`. GitLab Runner automatically exchanges `VAULT_ID_TOKEN` against `VAULT_SERVER_URL` before the job `script:` starts and injects each secret as an environment variable (`file: false`) or temporary file (`file: true`, default):

```yaml
stages:
  - build
  - deploy

variables:
  VAULT_SERVER_URL: "http://vault.vault.svc.cluster.local:8200"
  VAULT_AUTH_PATH: "jwt"
  VAULT_AUTH_ROLE: "gitlab-ci-role"

deploy_with_native_vault_secrets:
  stage: deploy
  image: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/alpine:latest
  id_tokens:
    VAULT_ID_TOKEN:
      aud: https://vault.org-12345.zone1.google.gdch.test
  secrets:
    DB_USER:
      vault: gitlab/ci-demo/DB_USER@secret
      token: $VAULT_ID_TOKEN
      file: false
    DB_PASS:
      vault: gitlab/ci-demo/DB_PASS@secret
      token: $VAULT_ID_TOKEN
      file: false
    API_KEY:
      vault: gitlab/ci-demo/API_KEY@secret
      token: $VAULT_ID_TOKEN
      file: false
  script:
    - echo "Authenticated via GitLab OIDC id_token for DB_USER=${DB_USER}"
```

#### Method 2: Direct HTTP API / Vault CLI Exchange in `script:` (Runner-Agnostic)

If your CI job requires fetching an entire KVv2 path at once or runs on a custom runner executor where you prefer explicit HTTP/CLI control, exchange `$VAULT_ID_TOKEN` directly via `curl` or `vault write` inside `script:`:

```yaml
deploy_with_vault_http_api:
  stage: deploy
  image: harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault:1.15.0
  id_tokens:
    VAULT_ID_TOKEN:
      aud: https://vault.org-12345.zone1.google.gdch.test
  variables:
    VAULT_ADDR: "http://vault.vault.svc.cluster.local:8200"
  script:
    # 1. Exchange GitLab OIDC id_token for a short-lived Vault client token
    - export VAULT_TOKEN="$(vault write -field=token auth/jwt/login role=gitlab-ci-role jwt=$VAULT_ID_TOKEN)"
    # 2. Export specific secrets or full KVv2 JSON for build/deploy commands
    - export DB_USER="$(vault kv get -field=DB_USER secret/gitlab/ci-demo)"
    - export DB_PASS="$(vault kv get -field=DB_PASS secret/gitlab/ci-demo)"
    - export API_KEY="$(vault kv get -field=API_KEY secret/gitlab/ci-demo)"
    - echo "Retrieved secrets for DB_USER=${DB_USER} from Vault KVv2"
```

### 8.5 Pattern D: Dynamic PostgreSQL Credentials via Vault `database/` Secrets Engine

To eliminate static long-lived database passwords altogether, configure HashiCorp Vault's **Database Secrets Engine (`database/`)** against a tenant GDCag Managed PostgreSQL `DBCluster` (for example, `my-app-db`, provisioned on `ZONE_KUBECONFIG` via [`./charts/gdc-dbs`](../../charts/gdc-dbs/README.md)). Vault creates unique, time-bounded PostgreSQL login roles (`v-k8s-my-app-...`) on demand and automatically revokes them upon lease expiration.

> [!IMPORTANT]
> **Three Prerequisites for Dynamic Credentials Against GDCag Managed PostgreSQL 15:**
> 1. **Outbound `5432/TCP` Egress**: Ensure `vault-internal-policy` in `-n vault` allows `5432/TCP` egress to the Zonal `DBCluster` CIDR ([Section 5.5](#55-step-4-apply-user-cluster-vault-networkpolicy-5432tcp-managed-dbcluster-egress)).
> 2. **Explicit `sslrootcert=` Mount in `vault-0`**: Because `gdc-kms-bridge` overrides `SSL_CERT_FILE="/vault/kms-bridge/ca-certificates.crt"`, copy `dbs-pg-cert-<dbcluster>` from `Secret/dbs-certificates` (`ZONE_KUBECONFIG`) into a Secret in `-n vault` (e.g., `vault-db-ca` mounted at `/vault/userconfig/vault-db-ca/ca.crt` via `server.extraVolumes`) and pass `?sslmode=verify-full&sslrootcert=/vault/userconfig/vault-db-ca/ca.crt` in `connection_url`.
> 3. **Pre-Created `NOLOGIN` Group Role (`app_rw`) & PG 15 `DROP OWNED BY` Revocation**: Do not place table-level `GRANT` statements directly inside Vault's `creation_statements` - on PostgreSQL 15, direct ACL dependencies block `DROP ROLE` when leases expire (`cannot be dropped because some objects depend on it`). Instead, grant schema/table privileges once to a `NOLOGIN` group role (`app_rw`), issue dynamic child roles with `IN ROLE app_rw`, and include `DROP OWNED BY "{{name}}";` in `revocation_statements`.

#### Step 1: Prepare `app_rw` Group Role & `vault_db_admin` Role on the Target `DBCluster`

After provisioning `DBCluster/my-app-db` on `ZONE_KUBECONFIG`, extracting `APP_DB_HOST="${APP_DB_URL%:5432}"`, and mounting `Secret/vault-db-ca` into `vault-0` (`server.extraVolumes: [{type: secret, name: vault-db-ca}]`), connect once as `dbsadmin` to create the `app_db` database, the `NOLOGIN` permission group role (`app_rw`), and a dedicated `vault_db_admin` role with `CREATEROLE`:

```bash
export APP_DB_ADMIN_PASSWORD="<dbsadmin-password-for-my-app-db>"
export VAULT_DB_ENGINE_PASSWORD="<initial-vault-db-admin-password>"

# 1. Extract CA from ZONE_KUBECONFIG and sync to -n vault on USER_CLUSTER_KUBECONFIG (mount via server.extraVolumes)
kubectl --kubeconfig="${ZONE_KUBECONFIG}" get secret dbs-certificates \
  -n iac-root -o jsonpath='{.data.dbs-pg-cert-my-app-db}' | base64 -d > "${WORK_DIR}/my-app-db-ca.crt"

kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" -n vault create secret generic vault-db-ca \
  --from-file=ca.crt="${WORK_DIR}/my-app-db-ca.crt" \
  --dry-run=client -o yaml | kubectl --kubeconfig="${USER_CLUSTER_KUBECONFIG}" apply -f -

# 2. Initialize 'app_db', NOLOGIN group role 'app_rw', and 'vault_db_admin' as dbsadmin
PGPASSWORD="${APP_DB_ADMIN_PASSWORD}" PGSSLMODE=verify-full PGSSLROOTCERT="${WORK_DIR}/my-app-db-ca.crt" \
  psql -h "${APP_DB_HOST}" -p 5432 -U dbsadmin -d postgres -v vault_adm_pw="${VAULT_DB_ENGINE_PASSWORD}" <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw NOLOGIN;
  END IF;
END $$;

SELECT format('CREATE ROLE vault_db_admin WITH LOGIN CREATEROLE PASSWORD %L', :'vault_adm_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vault_db_admin') \gexec

GRANT app_rw TO vault_db_admin WITH ADMIN OPTION;
GRANT app_rw TO dbsadmin;

SELECT 'CREATE DATABASE app_db OWNER app_rw'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'app_db') \gexec
SQL

PGPASSWORD="${APP_DB_ADMIN_PASSWORD}" PGSSLMODE=verify-full PGSSLROOTCERT="${WORK_DIR}/my-app-db-ca.crt" \
  psql -h "${APP_DB_HOST}" -p 5432 -U dbsadmin -d app_db <<'SQL'
GRANT CONNECT ON DATABASE app_db TO app_rw;
GRANT USAGE, CREATE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
SQL
```

#### Step 2: Configure Vault `database/` Engine, Rotate Root Password & Issue Dynamic Leases

```bash
export VAULT_ROOT_TOKEN=$(jq -r '.root_token' "${WORK_DIR}/vault-init.json")

kubectl -n vault exec -i vault-0 -c vault -- env \
  VAULT_TOKEN="${VAULT_ROOT_TOKEN}" \
  APP_DB_HOST="${APP_DB_HOST}" \
  VAULT_DB_ENGINE_PASSWORD="${VAULT_DB_ENGINE_PASSWORD}" sh -c '
  # 1. Enable the Database Secrets Engine
  vault secrets enable database || true

  # 2. Configure verified TLS connection to GDCag Managed PostgreSQL (explicit sslrootcert bypasses SSL_CERT_FILE)
  vault write database/config/my-app-postgres \
    plugin_name="postgresql-database-plugin" \
    allowed_roles="my-app-dynamic" \
    connection_url="postgresql://{{username}}:{{password}}@${APP_DB_HOST}:5432/app_db?sslmode=verify-full&sslrootcert=/vault/userconfig/vault-db-ca/ca.crt" \
    username="vault_db_admin" \
    password="${VAULT_DB_ENGINE_PASSWORD}"

  # 3. Immediately rotate vault_db_admin password so only Vault knows it
  vault write -force database/rotate-root/my-app-postgres

  # 4. Define dynamic role inheriting from app_rw with PG 15-safe revocation statements
  vault write database/roles/my-app-dynamic \
    db_name="my-app-postgres" \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL '\''{{expiration}}'\'' IN ROLE app_rw;" \
    revocation_statements="REASSIGN OWNED BY \"{{name}}\" TO app_rw; DROP OWNED BY \"{{name}}\"; DROP ROLE IF EXISTS \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"

  # 5. Grant read access on dynamic credentials to my-app-policy
  vault policy write my-app-policy - <<EOF
path "secret/data/apps/my-app/*" {
  capabilities = ["read"]
}
path "secret/metadata/apps/my-app/*" {
  capabilities = ["read", "list"]
}
path "database/creds/my-app-dynamic" {
  capabilities = ["read"]
}
EOF

  # 6. Test minting a short-lived PostgreSQL credential lease
  vault read database/creds/my-app-dynamic
'
```

Workloads using **Pattern A** (`vault-agent-injector`) can render dynamic credentials directly into `/vault/secrets/db.env` via `vault.hashicorp.com/agent-inject-secret-db.env: "database/creds/my-app-dynamic"` (`{{ .Data.username }}` / `{{ .Data.password }}`), with `vault-agent` automatically renewing the lease and rotating credentials prior to `max_ttl`.

---

## 9. End-to-End Verification & Troubleshooting

### 9.1 End-to-End Cross-Namespace & Managed `DBCluster` TLS Verification

First, verify Zonal `DBCluster` + `BackupPlan` health on `ZONE_KUBECONFIG` and confirm that GitLab's live ActiveRecord connection in `-n gitlab` is encrypted over TLS (`pg_stat_ssl`):

```bash
# 1. Verify Zonal DBCluster and BackupPlan status on ZONE_KUBECONFIG
kubectl --kubeconfig="${ZONE_KUBECONFIG}" get dbcluster.postgresql.dbadmin.gdc.goog,backupplan.postgresql.dbadmin.gdc.goog -n iac-root

# 2. Confirm GitLab Rails is connected to PostgreSQL 15 over verified TLS
kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- /srv/gitlab/bin/rails runner '
  row = ActiveRecord::Base.connection.select_one(
    "SELECT current_database() AS db, current_user AS usr, version() AS ver, ssl, tls.version AS tls_ver " \
    "FROM pg_stat_ssl tls WHERE tls.pid = pg_backend_pid()"
  )
  puts row.inspect
'
```

Next, run the cross-namespace verification commands from `gitlab-toolbox` in namespace `gitlab` to verify both **GitLab JWT Auth** and **Kubernetes ServiceAccount Auth** against Vault (`http://vault.vault.svc.cluster.local:8200`):

```bash
# 1. Mint a genuine RS256 GitLab CI JWT signed by GitLab's ci_jwt_signing_key and authenticate to Vault
GITLAB_CI_JWT=$(kubectl exec -n gitlab deploy/gitlab-toolbox -c toolbox -- /srv/gitlab/bin/rails runner '
  key = OpenSSL::PKey::RSA.new(ApplicationSetting.current.ci_jwt_signing_key)
  jwk = JWT::JWK.new(key)
  now = Time.now.to_i
  payload = {
    iss: "https://gitlab.org-12345.zone1.google.gdch.test",
    sub: "project_path:root/vault-kms-demo:ref_type:branch:ref:main",
    aud: "https://vault.org-12345.zone1.google.gdch.test",
    iat: now, nbf: now - 5, exp: now + 3600,
    project_id: "1", project_path: "root/vault-kms-demo",
    user_id: "1", user_login: "root", ref: "main"
  }
  puts JWT.encode(payload, key, "RS256", { kid: jwk.kid, typ: "JWT" })
' | tail -n 1 | tr -d '\r')

# 2. Mint a Kubernetes ServiceAccount token for gitlab/default (since gitlab-toolbox sets automountServiceAccountToken: false)
K8S_JWT=$(kubectl create token default -n gitlab)

# 3. Execute cross-namespace JWT Auth and Kubernetes Auth logins from gitlab-toolbox -> vault.vault.svc.cluster.local:8200
kubectl exec -i -n gitlab deploy/gitlab-toolbox -c toolbox -- bash -s "${GITLAB_CI_JWT}" "${K8S_JWT}" <<'EOF'
set -e
JWT_TOKEN="$1"
K8S_JWT="$2"
VAULT_ADDR="http://vault.vault.svc.cluster.local:8200"

echo "=== [Test 1] GitLab Pod -> Vault JWT Auth Login ==="
CLIENT_TOKEN=$(curl -sS --request POST \
  --data "{\"role\": \"gitlab-ci-role\", \"jwt\": \"${JWT_TOKEN}\"}" \
  "${VAULT_ADDR}/v1/auth/jwt/login" | jq -r '.auth.client_token')
curl -sS -H "X-Vault-Token: ${CLIENT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/gitlab/ci-demo" | jq '.data'

echo "=== [Test 2] GitLab Pod -> Vault Kubernetes ServiceAccount Auth Login ==="
K8S_CLIENT_TOKEN=$(curl -sS --request POST \
  --data "{\"role\": \"gitlab-role\", \"jwt\": \"${K8S_JWT}\"}" \
  "${VAULT_ADDR}/v1/auth/kubernetes/login" | jq -r '.auth.client_token')
curl -sS -H "X-Vault-Token: ${K8S_CLIENT_TOKEN}" \
  "${VAULT_ADDR}/v1/secret/data/gitlab/app" | jq '.data'
EOF
```

**Verified Live Output:**
```json
=== [Test 1] GitLab Pod -> Vault JWT Auth Login ===
{
  "data": {
    "API_KEY": "glpat-vault-kms-verified",
    "DB_PASS": "GdcVaultKms2026!",
    "DB_USER": "gitlab_ci"
  },
  "metadata": {
    "created_time": "2026-11-16T11:50:32.591281539Z",
    "custom_metadata": null,
    "deletion_time": "",
    "destroyed": false,
    "version": 1
  }
}
=== [Test 2] GitLab Pod -> Vault Kubernetes ServiceAccount Auth Login ===
{
  "data": {
    "APP_ENV": "production",
    "KMS_KEY": "namespaces/iac-root/aeadKeys/vault-unseal-key"
  },
  "metadata": {
    "created_time": "2026-11-16T11:50:32.997903442Z",
    "custom_metadata": null,
    "deletion_time": "",
    "destroyed": false,
    "version": 1
  }
}
```

### 9.2 Troubleshooting Common Issues

| Symptom / Error Message | Root Cause (`org-12345` / `zone1`) | Verified Remediation |
| :--- | :--- | :--- |
| `Unable to connect to the server: net/http: TLS handshake timeout` when running `kubectl` | Workstation `/usr/bin/kubectl` (`go1.27+`) sends oversized post-quantum `X25519MLKEM768` ClientHello / missing ALPN to the GDCag Envoy ingress gateway. | Prepend the `gdcloud`-bundled `kubectl` (`v1.30.2-gke.1100`) to `PATH` and export `GODEBUG=tlsmlkem=0` for `helm`. |
| `412 Precondition Failed: The image doesn't pass Cosign signature verification` | System Harbor `library` project enforces Cosign verification on newly pushed unsigned images. | Push custom or re-tagged images (`vault:1.15.0`, `gdc-kms-bridge:1.0.0`) to Project Harbor (`harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/...`) and attach `imagePullSecrets: [{name: harbor-creds}]`. |
| `Error initializing core: license check failed: no autoloaded license provided` in `vault-0` | Image `library/hashicorp/vault-enterprise:1.21.2-ent` requires an Enterprise license secret. | Use the OSS `harbor001-iac-root.org-12345.zone1.google.gdch.test/iac/vault:1.15.0` image in `server.image` and `injector.agentImage`. |
| `PersistentVolumeClaim is pending: storageclass.storage.k8s.io "standard" not found` | Blueprint default `storageClass: "standard"` does not exist on GDCag user clusters. | Set `storageClass: "standard-rwo"` in both Vault and GitLab Helm values. |
| `InvalidArgument: resource name ... does not match expected format namespaces/<namespace>/aeadKeys/<name>` | Using lowercase `aeadkeys` or GCP `projects/.../keyRings/...` path against GDCag KMS. | Use camelCase `namespaces/iac-root/aeadKeys/vault-unseal-key` in `gdcloud kms keys` and run `gdc-kms-bridge` for Vault's `seal "gcpckms"`. |
| `failed to pull and unpack image "gcr.io/private-cloud-staging/...": unexpected media type text/html` | User cluster containerd does not have mirror rules for `gcr.io/private-cloud-staging/*`. | Reference `harbor.org-12345.zone1.google.gdch.test/gpc-system-container-images/private-cloud-staging/...` explicitly in `gitlab-values.yaml`. |
| GitLab `/oauth/discovery/keys` returns `{"keys":[]}` | `ApplicationSetting.current.ci_jwt_signing_key` was not initialized during first-boot migration restart. | Run `/srv/gitlab/bin/rake db:seed_fu` and generate `ci_jwt_signing_key` via `rails runner` in `deploy/gitlab-toolbox` (see Section 6.5). |
| `dial tcp <db-vip>:5432: i/o timeout` from `gitlab` or `vault` pods | User Cluster `NetworkPolicy` (`vault-internal-policy` or `gitlab-postgres-egress`) blocks outbound `5432/TCP` to the Zonal `DBCluster` subnet. | Permit `5432/TCP` egress to `${DBCLUSTER_SUBNET_CIDR}` in `vault-internal-policy` (Section 5.5) and `gitlab-postgres-egress` (Section 6.3). |
| `PG::InsufficientPrivilege: ERROR: permission denied for extension "btree_gist"` or `permission denied for schema public` | Pre-install `gitlab-db-bootstrap` `Job` was skipped, extensions were created in `-d postgres` instead of `-d gitlabhq_production`, or `GRANT gitlab TO dbsadmin` + PG 15 `GRANT ALL ON SCHEMA public TO gitlab` was omitted. | Run `Job/gitlab-db-bootstrap` as `dbsadmin` against `-d gitlabhq_production` (Section 6.3) before `helm upgrade --install gitlab`. |
| `PG::ConnectionBad: root certificate file "/home/git/.postgresql/root.crt" does not exist` | `PGSSLMODE=verify-full` (or `verify-ca`) was set without `PGSSLROOTCERT`, or `Secret/gitlab-db-ca` key did not end in `.crt`. | Ensure `Secret/gitlab-db-ca` uses a `.crt` key (`gitlab-db-ca.crt`), set `global.certificates.customCAs: [{secret: gitlab-db-ca}]`, and set `PGSSLROOTCERT: "/etc/ssl/certs/ca-certificates.crt"` under `global.extraEnv` (Section 6.4). |
| `invalid port ":5432:5432"` or `could not translate host name "<host>:5432"` | `DBCluster` `.status.primary.url` includes `:5432` and was passed raw into `global.psql.host` or `psql -h`. | Strip the port suffix via `DB_HOST="${DB_URL%:5432}"` before passing to `global.psql.host` or `psql -h` (Section 6.2). |
| `DBCluster` stuck reconciling `adminUser.passwordRef` (`Secret/db-pw-<name>`) | `Secret` `data` key was named `password` instead of matching `DBCluster` `metadata.name`, or operator lacks `project-db-admin`. | Set `data.<dbcluster-name>` (e.g., `data.gitlab-db` in `Secret/db-pw-gitlab-db`) on `ZONE_KUBECONFIG` and bind `IAMRole` `project-db-admin` on `GLOBAL_API_KUBECONFIG` (Sections 4.1 & 6.2). |
| Vault `x509: certificate signed by unknown authority` when connecting to `DBCluster` (Option B or `database/`) | `gdc-kms-bridge` sets `SSL_CERT_FILE="/vault/kms-bridge/ca-certificates.crt"`, which excludes Zonal `Secret/dbs-certificates`. | Mount `Secret/vault-db-ca` via `server.extraVolumes` and pass explicit `?sslmode=verify-full&sslrootcert=/vault/userconfig/vault-db-ca/ca.crt` (or `sslmode=verify-ca` if connecting by raw IP; see Sections 5.6 & 8.5). |
