#!/bin/bash

# Export variables

export ORG_NAME="org-15357"
export IAC_PROJECT="iac-root"
export user_project_name="d2-ets-user-1"
export IAC_USER="gdch-infra-operator-fop-iac001@opscenter.local"
export IAC_SA="iac001-sa"
export ZONE="lux-central1-b"
export ROOT_ZONE="lux.clr"
export GDCH_CONSOLE="console.${ORG_NAME}.${ZONE}.${ROOT_ZONE}"
export CA_CERT_PATH="/mnt/c/temp/DGA/cert/"
export CLUSTER_NAME="clstr-20260224"
export shared_infra_project_name=data-ets-shared-infra

# 1. Grant IaC Bootstrap User required Org roles:

# Connect with and account with organization-iam-admin permissions

for role in \
organization-iam-admin \
project-creator \
project-editor \
user-cluster-admin \
; do \
    gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="user:${IAC_USER:?}" \
    --role="$role";\
done

# 2. Create a project to host IaC resources

gdcloud projects create $IAC_PROJECT
gdcloud projects create $shared_infra_project_name

# 3. Grant IaC Bootstrap User required `$IAC_PROJECT` roles:

for role in \
secret-admin \
project-iam-admin \
; do \
gdcloud projects add-iam-policy-binding $IAC_PROJECT \
--member=user:$IAC_USER \
--role=$role;\
done

# 4. Follow [documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#gdcloud) to create service account:

gdcloud iam service-accounts create "$IAC_SA" --project "$IAC_PROJECT"

# 5. Assign the permissions required by the service account:
# - organization:

for role in \
organization-iam-admin \
project-creator \
project-editor \
user-cluster-admin \
organization-billing-account-admin \
organization-billing-account-user \
organization-billing-manager \
; do \
    gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="serviceAccount:${IAC_PROJECT:?}:${IAC_SA:?}" \
    --role="$role";\
done

# - project:

for role in \
secret-admin \
standard-cluster-admin \
namespace-admin \
workload-viewer \
cluster-developer \
project-networkpolicy-admin \
project-bucket-admin \
project-bucket-object-admin \
; do \
gdcloud projects add-iam-policy-binding $IAC_PROJECT \
--member="serviceAccount:${IAC_PROJECT:?}:${IAC_SA:?}" \
--role=$role;\
done

for role in \
project-bucket-admin \
project-iam-admin \
harbor-instance-admin \
project-networkpolicy-admin \
; do \
gdcloud projects add-iam-policy-binding $shared_infra_project_name \
--member="serviceAccount:${IAC_PROJECT:?}:${IAC_SA:?}" \
--role=$role;\
done

for role in \
project-bucket-admin \
project-iam-admin \
workbench-notebooks-admin \
; do \
gdcloud projects add-iam-policy-binding $user_project_name \
--member="serviceAccount:${IAC_PROJECT:?}:${IAC_SA:?}" \
--role=$role;\
done

# 6. Obtain the Service Account [credentials](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#create-and-add-key-pairs):

rm -rf "${CA_CERT_PATH}${IAC_SA:?}.json"
gdcloud iam service-accounts keys create "${CA_CERT_PATH}${IAC_SA:?}.json" \
--project="$IAC_PROJECT" \
--iam-account="$IAC_SA"
sed -i 's|https://service-accounts.org-15357.lux.clr/authenticate|https://service-accounts.org-15357.lux-central1-b.lux.clr/authenticate|' "${CA_CERT_PATH}${IAC_SA}.json"

# 7. Generate kubeconfig files (https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#generate-kubeconfig):

# Activate  service account key
gdcloud auth activate-service-account --key-file=${CA_CERT_PATH:?}${IAC_SA:?}.json
# Generate Global API KUBECONFIG file
rm -rf ${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-global-api.kubeconfig
export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-global-api.kubeconfig
gdcloud config set core/zone ""
gdcloud clusters get-credentials global-api
IAC_TOKEN=$(gdcloud auth print-identity-token --audiences=https://global-api.${ORG_NAME:?}.${ZONE:?}.${ROOT_ZONE:?})
kubectl config set-credentials "${IAC_SA}" --token="${IAC_TOKEN}"
kubectl config set-context --current --user="${IAC_SA}"
# Generate Zonal API KUBECONFIG file
rm -rf ${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}.kubeconfig
export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}.kubeconfig
gdcloud config set core/zone ${ZONE:?}
gdcloud clusters get-credentials ${ORG_NAME:?}-admin --zone ${ZONE:?}
IAC_TOKEN=$(gdcloud auth print-identity-token --audiences=https://management-kube.apiserver.${ORG_NAME:?}.${ZONE:?}.${ROOT_ZONE:?} --zone=${ZONE:?})
kubectl config set-credentials "${IAC_SA}" --token="${IAC_TOKEN}"
kubectl config set-context --current --user="${IAC_SA}"
# Generate User cluster API KUBECONFIG file
rm -rf ${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
export KUBECONFIG=${CA_CERT_PATH:?}${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}-${CLUSTER_NAME:?}.kubeconfig
gdcloud config set core/zone ${ZONE:?}
gdcloud clusters get-credentials ${CLUSTER_NAME:?} --zone ${ZONE:?}
IAC_TOKEN=$(gdcloud auth print-identity-token --audiences=https://${CLUSTER_NAME:?}-kube.apiserver.${ORG_NAME:?}.${ZONE:?}.${ROOT_ZONE:?} --zone=${ZONE:?})
kubectl config set-credentials "${IAC_SA}" --token="${IAC_TOKEN}"
kubectl config set-context --current --user="${IAC_SA}"

export HELM_NAMESPACE=$IAC_PROJECT