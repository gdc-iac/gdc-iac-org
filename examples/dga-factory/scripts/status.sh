#!/bin/bash

export SCRIPTS_DIR=$( readlink -e $(dirname $0))
source ${SCRIPTS_DIR:?}/config.sh

${HELM_CLI:?} list --namespace=${IAC_PROJECT:?} --kubeconfig=$GLOBAL_API_KUBECONFIG
${HELM_CLI:?} list --namespace=${IAC_PROJECT:?} --kubeconfig=$ZONE_KUBECONFIG
${HELM_CLI:?} list --namespace=${IAC_PROJECT:?} --kubeconfig=$USER_CLUSTER_KUBECONFIG