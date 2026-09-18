#!/bin/bash

export SCRIPTS_DIR=$( readlink -e $(dirname $0))
source ${SCRIPTS_DIR:?}/config.sh

helm uninstall --namespace=${IAC_PROJECT:?} --kubeconfig=$USER_CLUSTER_KUBECONFIG $@