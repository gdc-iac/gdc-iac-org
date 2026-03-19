# Google Distributed Cloud Infrastructure Automation

This repository provides a flexible toolkit for managing infrastructure as code (IaC) using predefined YAML configuration files and Helm charts for **Google Distributed Cloud air-gapped (GDCag)**.

## Terminology
- **GDCag**: Google Distributed Cloud air-gapped (formerly known as **GDCH**)

## Repository Structure

- `charts/`: The raw Helm charts that template the GDCag Custom Resources (e.g., Projects, VM, DB Clusters).
- `tools/`: Tooling and configuration files for deploying resources:
  - `helmfile/`: Declarative, data-driven orchestration using `helmfile`.
  - `helm_cli/`: Custom python wrapper script for processing configurations and deploying.
  - `config-sync/`: Examples for operators using GitOps.
- `examples/`: Sample configuration files (e.g., `tenants.yaml` or `org.yaml`) representing a desired state.
- `scripts/`: Helper utilities for testing charts and updating documentation.
- `policy/`: OPA/Rego policies for security and configuration validation.

---

## Architecture & Resource Orchestration

GDCag heavily relies on custom resources, which are typically created in alphabetical order by Helm (as described in [issue/1228](https://github.com/helm/helm/issues/1228)). For example, an `IAMRole` resource must be created before a `Project` resource. 

To overcome this constraint, this framework uses a **layered approach**, where configurations (like `org.yaml` or `tenants.yaml`) are shared across multiple, highly specialized charts. These charts are then deployed in a strict, predefined order:

1. Organization roles
2. User Clusters [scope: zone]
3. Projects
4. Buckets [scope: zone]
5. Project roles
6. Project Service Accounts
7. Role Bindings
8. Workloads (VMs, DBs, Harbors, Notebooks, Network Policies)

### Separating Infrastructure Provisioning from Access Management

When provisioning GDCag standard clusters, it is highly recommended to logically separate cluster provisioning from access management:
- **Infrastructure Provisioning (`gdc-standard-clusters`)**: Dedicated only to creating standard clusters. Cluster creation has a separate lifecycle and requires higher privileges.
- **Access Management (`gdc-standard-clusters-rbac`)**: Dedicated to managing Kubernetes RBAC (`RoleBindings`, `ClusterRoleBindings`) inside the provisioned clusters. This allows developers to be onboarded or offboarded securely without modifying the core cluster infrastructure.

---

## Deployment Strategies

The toolkit allows you to use different tools to template and synchronize these configurations based on your operational needs. The detailed setup workflows and prerequisites for each method are documented in their respective tool directories:

### Method 1: Infrastructure Automation via Helmfile (Recommended)
This method utilizes a **data-driven approach** linking `tenants.yaml` inputs through a logic engine (`helmfile.yaml`) to dynamically generate and sequence Helm releases based on the required dependency chain.

👉 **[View Helmfile Documentation & Setup Guide](tools/helmfile/README.md)**

### Method 2: Deployment via Custom Helm CLI wrapper
A custom Python wrapper script (`helm_cli.py`) designed for local or CI/CD usage. It streamlines the parsing of YAML configurations and loops through the charts imperatively, substituting the correct contexts and environments automatically.

👉 **[View Helm CLI Documentation & Setup Guide](tools/helm_cli/README.md)**

### Method 3: Config Sync (GitOps)
Continuous state synchronization using the Config Sync operator. It acts as an in-cluster reconciliation agent, applying changes made directly to this repository.

👉 **[View Config Sync Documentation & Setup Guide](tools/config-sync/README.md)**
### Grant IAC_USER required Org roles:
for role in \
  organization-iam-admin \
  organization-billing-account-admin \
  organization-billing-manager \
  project-creator \
  project-editor \
  user-cluster-admin \
  dr-backup-admin \
  organization-backup-admin \
  organization-cluster-backup-admin \
  system-cluster-backup-repository-admin \
  user-cluster-backup-admin \
; do \
   gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
   --member="user:$IAC_USER" \
   --role="$role";\
done

### Grant IAC_USER required IAM permissions on `IAC_PROJECT` :
for role in \
  secret-admin \
  backup-creator \
; do \
  gdcloud projects add-iam-policy-binding $IAC_PROJECT \
  --member=user:$IAC_USER \
  --role=$role;\
done
```

### 4. Deploying GDCH Resources `VirtualMachine`, `Bucket`, `DBCluster`

0. gdcloud auth login (as fop-iac@example.com)

`gdcloud auth login --login-config-cert=/tmp/org-1-web-tls-ca.cert`

1. Prechecks Helm Chart
```bash
cd helm-iac
helmfile lint
helmfile list
helmfile show-dag
```


2. Helmfile diff to show resources to deploy

```bash
helmfile diff
```

Note: this is like to fail because of a "Chicken and Egg" problem.  `helmfile diff` or even `helmfile apply` attempts to calculate diffs for all groups before it applies anything.
However, this is a fresh install and  the namespaces (e.g lotus-prj, snowflake-prj) does not exist yet.

2. Use `helmfile sync` for ``first run``.

Note: `helmfile sync` does not try to read the state first. It will simply execute the DAG in order ensuring the resources are deployed base on the order and dependency defined using the `needs` keyword.

4. Use `helmfile apply` for subsequent resources deployment once project and rolebindings exists.

```bash
helmfile apply
```

---

## Code Validation & Testing

All charts and configurations submitted to this repository should be validated against the included policies and test scripts to ensure compliance.

- **Chart Testing**: Scripts to template and validate charts are located in `scripts/test-charts.sh`.
- **Security Policies**: OPA/Gatekeeper validations (like `policy/security.rego`) exist to ensure that deployments adhere to the organization's security defaults.

---

## Reference

<details>
<summary><b>GDCag Resource Creation Sequences</b></summary>
<br>

**Zonal resource creation sequence:**
- `clusters.cluster.gdc.goog`: [only zonal mgmt]
- `OrganizationNetworkPolicy`: [only zonal mgmt]

**Global Resource creation sequence:**
- `projects` namespace: platform
- `customroles.iam.global.gdc.goog` namespace: platform
- `projectserviceaccounts.resourcemanager.global.gdc.goog` namespace: project
- `iamrolebindings.iam.global.gdc.goog` namespace: platform/project-name (both regular and custom)
- `projectnetworkpolicies.networking.global.gdc.goog` namespace: project
</details>

<details>
<summary><b>Global Resources API Endpoints</b></summary>
<br>

- `backendservicepolicies.networking.global.gdc.goog`
- `backendservices.networking.global.gdc.goog`
- `billingaccountbindings.billing.global.gdc.goog`
- `billingaccounts.billing.global.gdc.goog`
- `blockinvalidgdchrestrictedservice.constraints.global.gatekeeper.sh`
- `bucketinfos.object.global.private.gdc.goog`
- `bucketlocationconfigs.object.global.gdc.goog`
- `bucketlocations.object.global.gdc.goog`
- `buckets.object.global.gdc.goog`
- `clustermeshes.network.global.private.gdc.goog`
- `customroles.iam.global.gdc.goog`
- `datasources.monitoring.global.private.gdc.goog`
- `dnsregistrations.network.global.private.gdc.goog`
- `dnszones.network.global.private.gdc.goog`
- `etcdcarotations.etcd.mz.global.private.gdc.goog`
- `etcdclusterconfigoverrides.etcd.mz.global.private.gdc.goog`
- `etcdclusters.etcd.mz.global.private.gdc.goog`
- `etcdzones.etcd.mz.global.private.gdc.goog`
- `forwardingruleexternals.networking.global.gdc.goog`
- `forwardingruleinternals.networking.global.gdc.goog`
- `gdchallowedchars.constraints.global.gatekeeper.sh`
- `gdchallowedlength.constraints.global.gatekeeper.sh`
- `gdchallowednamespaces.constraints.global.gatekeeper.sh`
- `gdchreadonly.constraints.global.gatekeeper.sh`
- `gdchreservednames.constraints.global.gatekeeper.sh`
- `gdchreservedprefix.constraints.global.gatekeeper.sh`
- `gdchreservedsuffix.constraints.global.gatekeeper.sh`
- `gdchrestrictattribute.constraints.global.gatekeeper.sh`
- `gdchrestrictattributerange.constraints.global.gatekeeper.sh`
- `gdchrestrictbyattributes.constraints.global.gatekeeper.sh`
- `gdchrestrictedservice.constraints.global.gatekeeper.sh`
- `gdchrestrictfinalizerremoval.constraints.global.gatekeeper.sh`
- `gdchrestrictobjectstorageattributevalue.constraints.global.gatekeeper.sh`
- `gdchrestrictresource.constraints.global.gatekeeper.sh`
- `gdchsuffixednamespace.constraints.global.gatekeeper.sh`
- `gdchsystemclusterresource.constraints.global.gatekeeper.sh`
- `globaladdresspoolclaims.ipam.global.private.gdc.goog`
- `globaladdresspools.ipam.global.private.gdc.goog`
- `globalapizones.location.mz.global.private.gdc.goog`
- `globalresourceregistrations.apiregistry.global.private.gdc.goog`
- `globalrootkeys.kms.global.private.gdc.goog`
- `globalsecrets.core.global.private.gdc.goog`
- `healthchecks.networking.global.gdc.goog`
- `iamrolebindings.iam.global.gdc.goog`
- `iamroles.iam.global.gdc.goog`
- `identityproviderconfigs.iam.global.gdc.goog`
- `ioauthmethods.iam.global.private.gdc.goog`
- `kubeapiservers.lcm.global.private.gdc.goog`
- `manageddnszones.networking.global.gdc.goog`
- `mzaeadkeys.kms.global.gdc.goog`
- `orgbootstraps.bootstrap.mz.global.private.gdc.goog`
- `orgzones.bootstrap.mz.global.private.gdc.goog`
- `projectnetworkpolicies.networking.global.gdc.goog`
- `projects.resourcemanager.global.gdc.goog`
- `projectserviceaccounts.resourcemanager.global.gdc.goog`
- `releases.release.mz.global.private.gdc.goog`
- `resourcerecordsets.network.global.private.gdc.goog`
- `resourcerecordsets.networking.global.gdc.goog`
- `subnets.ipam.global.gdc.goog`
- `tokenrequests.bootstrap.mz.global.private.gdc.goog`
- `virtualmachineimages.virtualmachine.global.gdc.goog`
- `volumereplicationrelationships.storage.global.gdc.goog`
- `zonalrolebindings.iam.global.gdc.goog`
- `zonednsservers.network.global.private.gdc.goog`
- `zoneexclusions.location.mz.global.private.gdc.goog`
- `zones.location.mz.global.private.gdc.goog`
- `zoneselectionresults.location.mz.global.private.gdc.goog`
- `zoneselections.location.mz.global.private.gdc.goog`
</details>
