#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

export SCRIPTS_DIR=$( readlink -e $(dirname "${BASH_SOURCE[0]}"))
source ${SCRIPTS_DIR:?}/config.sh
set -e
mkdir -p ${KUBECONFIG_PATH:?}
mkdir -p ${SECRETS_DIR:?}

gdcloud auth activate-service-account --key-file=${SECRETS_DIR:?}/${IAC_SA:?}.json

rm -f ${GLOBAL_API_KUBECONFIG}
export KUBECONFIG=${GLOBAL_API_KUBECONFIG}
gdcloud config set core/zone ""
gdcloud clusters get-credentials global-api
IAC_TOKEN=$(gdcloud auth print-identity-token --zone ${GDCH_ZONE:?} --audiences=https://global-api.${ORG_NAME:?}.${GDCH_ZONE:?}.${GDCH_DOMAIN:?})
kubectl config set-credentials "${IAC_SA}" --token="${IAC_TOKEN}"
kubectl auth whoami || { echo "Failed to authenticate with global-api"; exit 1; }

rm -f ${ZONE_KUBECONFIG}
export KUBECONFIG=${ZONE_KUBECONFIG}
gdcloud config set core/zone ${GDCH_ZONE:?}
gdcloud clusters get-credentials ${ORG_NAME:?}-admin --zone ${GDCH_ZONE:?}
IAC_TOKEN=$(gdcloud auth print-identity-token --audiences=https://management-kube.apiserver.${ORG_NAME:?}.${GDCH_ZONE:?}.${GDCH_DOMAIN:?} --zone=${GDCH_ZONE:?})
kubectl config set-credentials "${IAC_SA}" --token="${IAC_TOKEN}"
kubectl auth whoami || { echo "Failed to authenticate with zone"; exit 1; }

rm -rf ${USER_CLUSTER_KUBECONFIG}
export KUBECONFIG=${USER_CLUSTER_KUBECONFIG}
gdcloud config set core/zone ${GDCH_ZONE:?}
gdcloud clusters get-credentials ${CLUSTER_NAME:?} --zone ${GDCH_ZONE:?}
IAC_TOKEN=$(gdcloud auth print-identity-token --audiences=https://${CLUSTER_NAME:?}-kube.apiserver.${ORG_NAME:?}.${GDCH_ZONE:?}.${GDCH_DOMAIN:?} --zone=${GDCH_ZONE:?})
kubectl config set-credentials "${IAC_SA}" --token="${IAC_TOKEN}"
kubectl auth whoami || { echo "Failed to authenticate with user cluster"; exit 1; }

