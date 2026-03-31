#!/bin/bash
export SCRIPTS_DIR=$( readlink -e $(dirname "${BASH_SOURCE[0]}"))
source ${SCRIPTS_DIR:?}/config.sh
set -e
export GLOBAL_TRUST_BUNDLE_FILE="${SECRETS_DIR:?}/certs/global-trust-bundle"
mkdir -p "$(dirname "${GLOBAL_TRUST_BUNDLE_FILE:?}")"

export WELL_KNOWN_URL=https://console.${ORG_NAME:?}.${GDCH_ZONE:?}.${GDCH_DOMAIN:?}/.well-known/certificate-authority
echo -n | curl ${WELL_KNOWN_URL:?} > ${GLOBAL_TRUST_BUNDLE_FILE:?}