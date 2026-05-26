#!/usr/bin/env bash
# update-certs.sh: Shared certificate trust utility
# Fetches and registers Console, AIS, and KMS endpoints TLS certificates.

set -e

ORG_NAME=${ORG_NAME:-"org-1"}
ZONE_NAME=${ZONE_NAME:-"east1"}
HOST_SUFFIX=${HOST_SUFFIX:-"google.gdch.test"}

CONSOLE_HOST=${CONSOLE_HOST:-"console.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}
AIS_HOST=${AIS_HOST:-"ais-core.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}
KMS_HOST=${KMS_HOST:-"kms.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}

CERT_DIR="./.certs"
mkdir -p "$CERT_DIR"

echo "================================================="
echo "🔐 GDC Certificate Trust Chain Manager"
echo "================================================="

echo "Fetching Console Certificate from ${CONSOLE_HOST}..."
openssl s_client -showcerts -connect "${CONSOLE_HOST}:443" </dev/null 2>/dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-console.crt"

echo "Fetching AIS Certificate from ${AIS_HOST}..."
openssl s_client -showcerts -connect "${AIS_HOST}:443" </dev/null 2>/dev/null | openssl x509 -outform PEM > "${CERT_DIR}/ais-core.crt"

echo "Fetching KMS Certificate from ${KMS_HOST}..."
openssl s_client -showcerts -connect "${KMS_HOST}:443" </dev/null 2>/dev/null | openssl x509 -outform PEM > "${CERT_DIR}/gdc-kms.crt"

echo "Adding certificates to local trust store (requires sudo)..."
sudo cp "${CERT_DIR}"/* /usr/local/share/ca-certificates/
sudo update-ca-certificates
echo "✅ Certificate trust store updated successfully!"

# 4. local browser trust database auto-injection (NSS / Chrome)
echo ""
if command -v certutil >/dev/null 2>&1; then
    echo "🦊 Found certutil. Registering certificates in local browser trust database (NSS)..."
    mkdir -p "$HOME/.pki/nssdb"
    
    certutil -d sql:"$HOME/.pki/nssdb" -A -t "P,," -n "GDC Console CA" -i "${CERT_DIR}/gdc-console.crt"
    certutil -d sql:"$HOME/.pki/nssdb" -A -t "P,," -n "GDC AIS CA" -i "${CERT_DIR}/ais-core.crt"
    certutil -d sql:"$HOME/.pki/nssdb" -A -t "P,," -n "GDC KMS CA" -i "${CERT_DIR}/gdc-kms.crt"
    echo "✅ Browser trust database updated successfully!"
else
    echo "ℹ️  certutil (libnss3-tools) not found. Browser TLS security warnings will need to be bypassed manually."
    echo "👉 To automate browser trust, please install it: sudo apt install libnss3-tools"
fi

