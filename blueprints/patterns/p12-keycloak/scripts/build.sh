#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# P12 strictly utilizes the official CNCF-compliant Keycloak OSS distribution via Quay.io
IMAGE_TAG="24.0.4"
SOURCE_IMAGE="quay.io/keycloak/keycloak:${IMAGE_TAG}"

if [ -z "$REGISTRY_HOST" ]; then
  echo "Error: REGISTRY_HOST is not set."
  exit 1
fi

TARGET_IMAGE="${REGISTRY_HOST}/keycloak/keycloak:${IMAGE_TAG}"

echo "Fetching official raw Keycloak container: ${SOURCE_IMAGE}..."
docker pull ${SOURCE_IMAGE}

echo "Mirroring to private GCP GCP Registry..."
docker tag ${SOURCE_IMAGE} ${TARGET_IMAGE}
docker push ${TARGET_IMAGE}

echo "Injecting authenticated registry string into static deployment manifest..."
sed -i.bak "s|REGISTRY_HOST_PLACEHOLDER|${REGISTRY_HOST}|g" p12-keycloak/manifests/apps/keycloak.yaml
rm -f p12-keycloak/manifests/apps/keycloak.yaml.bak

echo "Success! Image securely localized."
