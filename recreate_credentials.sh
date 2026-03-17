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

rm -rf "${CA_CERT_PATH}${IAC_SA:?}.json"
gdcloud iam service-accounts keys create "${CA_CERT_PATH}${IAC_SA:?}.json" \
--project="$IAC_PROJECT" \
--iam-account="$IAC_SA"

sed -i "s|https://service-accounts.${ORG_NAME:?}.lux.clr/authenticate|https://service-accounts.${ORG_NAME:?}.${ZONE:?}.lux.clr/authenticate|" "${CA_CERT_PATH}${IAC_SA}.json"
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