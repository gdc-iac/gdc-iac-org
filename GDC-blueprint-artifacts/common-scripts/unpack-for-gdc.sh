#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <pattern-name>"
  echo "Example: $0 p1-resilient-3-tier-webapp"
  exit 1
fi

PATTERN_NAME=$1

MANIFESTS_TAR="${PATTERN_NAME}-gdc-manifests.tar.gz"
IMAGES_TAR="${PATTERN_NAME}-gdc-images.tar"

if [ ! -f "$MANIFESTS_TAR" ]; then
  echo "Error: Manifests tarball $MANIFESTS_TAR not found."
  exit 1
fi

echo "Unpacking $PATTERN_NAME for GDC..."

# Extract manifests
echo "Extracting manifests..."
mkdir -p "$PATTERN_NAME"
tar -xzf "$MANIFESTS_TAR" -C "$PATTERN_NAME"
echo "Manifests extracted to $PATTERN_NAME/"

# Load images
if [ -f "$IMAGES_TAR" ]; then
  echo "📦 Reading container image payload: $IMAGES_TAR..."
  if docker load -i "$IMAGES_TAR"; then
    echo "✅ Successfully extracted and loaded all images into local Docker daemon."
    echo ""
    echo "⚠️  REMINDER: You must now manually push these loaded images to your GDC registry."
    echo "   Example: docker push harbor.gdc.local/library/my-image:latest"
  else
    echo "❌ FAILED: Error occurred while loading images from $IMAGES_TAR."
  fi
else
  echo "⚠️  No image payload found ($IMAGES_TAR). Skipping image load."
fi

echo "Unpacking complete!"
echo "You can now deploy the pattern using the manifests in $PATTERN_NAME/"
