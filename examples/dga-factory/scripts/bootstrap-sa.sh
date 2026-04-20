#!/bin/bash
export SCRIPTS_DIR=$( readlink -e $(dirname $0))
source ${SCRIPTS_DIR:?}/config.sh

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

for role in \
  secret-admin \
  cluster-admin \
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