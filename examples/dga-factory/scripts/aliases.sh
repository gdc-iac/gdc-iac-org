#!/bin/bash
export SCRIPTS_DIR=$( readlink -e $(dirname "${BASH_SOURCE[0]}"))
source ${SCRIPTS_DIR:?}/config.sh

alias kc='kubectl --kubeconfig=${USER_CLUSTER_KUBECONFIG:?}'
alias kz='kubectl --kubeconfig=${ZONE_KUBECONFIG:?}'
alias kg='kubectl --kubeconfig=${GLOBAL_API_KUBECONFIG:?}'
