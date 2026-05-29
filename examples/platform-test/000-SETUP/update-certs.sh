#!/usr/bin/env bash
# update-certs.sh: Shared certificate trust utility
# Fetches GDC Root CA certificate and registers it in system and browser trust stores.

set -e

ORG_NAME=${ORG_NAME:-"org-1"}
ZONE_NAME=${ZONE_NAME:-"zone1"}
HOST_SUFFIX=${HOST_SUFFIX:-"google.gdch.test"}

CONSOLE_HOST=${CONSOLE_HOST:-"console.${ORG_NAME}.${ZONE_NAME}.${HOST_SUFFIX}"}

CERT_DIR="./.certs"
mkdir -p "$CERT_DIR"

echo "================================================="
echo "🔐 GDC Complete CA Trust Chain Manager"
echo "================================================="

echo "📡 Extracting GDC Root CA Certificate from ${CONSOLE_HOST}..."
# Fetch certificate chain and extract the last certificate block (GDC Root CA)
openssl s_client -showcerts -connect "${CONSOLE_HOST}:443" </dev/null 2>/dev/null | awk '
  /BEGIN CERTIFICATE/ { cert=""; in_cert=1 }
  in_cert { cert = cert $0 "\n" }
  /END CERTIFICATE/ { in_cert=0 }
  END { print cert }
' > "${CERT_DIR}/gdc-root-ca.crt"

if [ ! -s "${CERT_DIR}/gdc-root-ca.crt" ] || ! grep -q "BEGIN CERTIFICATE" "${CERT_DIR}/gdc-root-ca.crt"; then
    echo "❌ Error: Failed to extract a valid GDC Root CA certificate."
    exit 1
fi

echo "🛡️  Adding GDC Root CA to local system trust store (requires sudo)..."
sudo cp "${CERT_DIR}/gdc-root-ca.crt" /usr/local/share/ca-certificates/gdc-root-ca.crt
sudo update-ca-certificates
echo "✅ System trust store updated successfully!"

# 4. local browser trust database auto-injection (NSS / Chrome)
echo ""
if command -v certutil >/dev/null 2>&1; then
    echo "🦊 Found certutil. Registering GDC Root CA in local browser trust database (NSS)..."
    mkdir -p "$HOME/.pki/nssdb"
    
    # Import GDC Root CA as a trusted Certificate Authority (-t "C,,")
    certutil -d sql:"$HOME/.pki/nssdb" -A -t "C,," -n "GDC Root CA" -i "${CERT_DIR}/gdc-root-ca.crt"
    echo "✅ Browser trust database updated successfully!"
else
    echo "ℹ️  certutil (libnss3-tools) not found. Browser TLS security warnings will need to be bypassed manually."
    echo "👉 To automate browser trust, please install it: sudo apt install libnss3-tools"
fi
