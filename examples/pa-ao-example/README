This directory contains an example structure for two repo types, "PA Repo" and "AO Repo"

# PA Repo
This is an example of a Platform Administrator repo which would have the following structure:

```text
pa-repo/
│
├── charts/ # This directory would contain all of the PA managed charts that would be used to deploy clusters, projects, etc
│
└── tenants/ This directory would contain all tenant configuration files, split into the core namespace and projects
    │
    ├── core/
    │   │
    │   ├── core-tenants.yaml  # Contains core namespace configuration for the Org level such as org policies, org network policies, billing, org level IAM etc.
    │   │
    │   └── helmfile.yaml.gotmpl
    │   
    └── projects/ # Each AO would have their own tenants directory containing their specific tenant configuration files for projects
        │
        └── example-ao-1
            │
            ├── ao1-tenants.yaml # Contains tenant configuration files for projects relating to AO1
            │
            └── helmfile.yaml.gotmpl
```

When new AO's are onboarded to the organisation, a new directory would be created under `tenants/projects/` for the new AO and a new `aoX-tenants.yaml` file would be created and added to the `helmfile.yaml.gotmpl`. This ensures that the core-tenants.yaml file does not have to contain all of the AO project config and is not modified during the onboarding of a new AO.

To further enforce principle of least privilage, the "core" tenant and "projects" tenants could be entirely separate Git repositories with separate access controls.

# AO Repo  
This is an example of an AO Repo for an AO called AO1 which has 3 projects called AO1 Project1, AO1 Project2 and AO1 Project3. Each project would have its own tenant configuration files and helmfile.yaml.gotmpl. This ensures that workloads within individual projects can be managed independantly of each other.

This repo would be entirely managed by the AO team, the PA team would only manage the clusters and deploy the projects with relevant IAM permissions for the AOs.

```text
ao-repo/
│
├── charts/ # This directory would contain all of the custom Helm charts that would be used to deploy AO specific workloads to AO controled projects
│
└── tenants/ This directory would contain all tenant configuration files for each of the AO managed projects
    │
    ├── ao1-project1/
    │   │
    │   ├── ao1-project1-tenants.yaml  # Contains AO1 Project1 tenant configuration files
    │   │
    │   └── helmfile.yaml.gotmpl
    │
    ├── ao1-project2/
    │   │
    │   ├── ao1-project2-tenants.yaml  # Contains AO1 Project2 tenant configuration files
    │   │
    │   └── helmfile.yaml.gotmpl
    │
    └── ao1-project3/
        │
        ├── ao1-project3-tenants.yaml  # Contains AO1 Project3 tenant configuration files
        │
        └── helmfile.yaml.gotmpl
```

