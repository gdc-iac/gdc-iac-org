#!/bin/bash

# Configure gdcloud configuration
## Variables for Org Admin Cluster
export ORG=org-15357
export DOMAIN=lux.clr
export ZONE=lux-central1-b
export CONFIG="${ORG}-${ZONE}"


echo "Config Name: ${CONFIG}"

if [[ "$ORG" == "root" ]]; then
export CONSOLE_URL="https://infra-console.${ZONE:?}.${DOMAIN:?}"
else
export CONSOLE_URL="https://console.${ORG}.${ZONE:?}.${DOMAIN:?}"
fi

echo "Console URL: ${CONSOLE_URL}"

export KUBECONFIG=/root/${CONFIG:?}.yaml
echo "Kubeconfig file: ${KUBECONFIG}"

### Install GDC Organization Console Certificate
echo -n | openssl s_client -showcerts -connect ${CONSOLE_URL#https://}:443 2>/dev/null | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > /usr/share/pki/ca-trust-source/anchors/${CONFIG:?}.crt
echo "Certificate is exported to: /usr/share/pki/ca-trust-source/anchors/${CONFIG:?}.crt"
update-ca-trust

### Install gdcloud components
gdcloud components install gdcloud-k8s-auth-plugin

### Set Configuration Parameters
gdcloud config configurations create ${CONFIG:?} 2>/dev/null
gdcloud config configurations activate ${CONFIG:?}
gdcloud config set core/organization_console_url ${CONSOLE_URL:?}
gdcloud config set core/zone ${ZONE}

### Check existing configurations
gdcloud config configurations list

### Login
gdcloud auth login