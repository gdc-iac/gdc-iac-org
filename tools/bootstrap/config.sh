export SCRIPTS_DIR=$( readlink -e $(dirname "${BASH_SOURCE[0]}"))
export KUBECONFIG_PATH=${SCRIPTS_DIR:?}/generated/kubeconfig
export SECRETS_DIR=${SCRIPTS_DIR:?}/generated/secrets

export ORG_NAME="gdc1"
export GDCH_DOMAIN="prestaging.gdclabs.com"
export GDCH_ZONE="us-east1-a"
export GDCH_CONSOLE="console.${ORG_NAME}.${GDCH_ZONE}.${GDCH_DOMAIN}"
export CLUSTER_NAME="user-vm-1"

export IAC_PROJECT="iac-root"
export IAC_SA="iac001-sa"

export GLOBAL_API_KUBECONFIG=${KUBECONFIG_PATH:?}/${IAC_PROJECT:?}-${IAC_SA:?}-global-api.kubeconfig
export ZONE_KUBECONFIG=${KUBECONFIG_PATH:?}/${IAC_PROJECT:?}-${IAC_SA:?}-${GDCH_ZONE:?}.kubeconfig
export USER_CLUSTER_KUBECONFIG=${KUBECONFIG_PATH:?}/${IAC_PROJECT:?}-${IAC_SA}-${GDCH_ZONE:?}-${CLUSTER_NAME:?}.kubeconfig