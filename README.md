# Setup

Helm is using the default kubeconfig path. Setup to use the same 
export KUBECONFIG=~/workspaces/amg1/adhoc-tools/kubeconfigs/global-api-iac-kubeconfig

# Grant roles to IaC User

for role in \
$(gdcloud iam roles list | grep admin)\
organization-grafana-viewer \
; do \
 gdcloud organizations add-iam-policy-binding org-1 \
 --member="user:fop-iac-tool@example.com" \
 --role="$role";\
done

# Configure kubeconfig
gdcloud auth login

export KUBECONFIG=~/workspaces/amg1/adhoc-tools/kubeconfigs/org-1-mgmt-kubeconfig

# Deploy Project
helm install iacproj1 ./gdc-project -f projects.yaml

# Update Project
helm upgrade --debug iacproj1 ./gdc-project -f projects.yaml


# Debug

for role in \
$(gdcloud iam roles list | grep admin)\
project-grafana-viewer \
; do \
 gdcloud projects add-iam-policy-binding iacproj3 \
 --member="user:fop-platform-admin@example.com" \
 --role="$role";\
done
