#!/bin/bash

# Configure gdcloud configuration
## Variables for Org Admin Cluster
export ORG=org-70033
export DOMAIN=lux.clr
export ZONE=lux-central1-a
export CONFIG="${ORG}-${ZONE}"


echo "Config Name: ${CONFIG}"

if [[ "$ORG" == "root" ]]; then
export CONSOLE_URL="https://infra-console.${ZONE:?}.${DOMAIN:?}"
else
export CONSOLE_URL="https://console.${ORG}.${ZONE:?}.${DOMAIN:?}"
fi

echo "Console URL: ${CONSOLE_URL}"

export KUBECONFIG=~/${CONFIG:?}.yaml
echo "Kubeconfig file: ${KUBECONFIG}"

### Install GDC Organization Console Certificate
echo -n | openssl s_client -showcerts -connect artifact-server-gateway.${ORG}.${ZONE}.${DOMAIN}:443 | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' | sudo tee /usr/local/share/ca-certificates/${ORG}-web-tls-artifact.crt > /dev/null

#  Update the trust store
sudo update-ca-certificates

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