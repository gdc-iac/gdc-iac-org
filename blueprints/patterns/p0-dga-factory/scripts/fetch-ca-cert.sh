#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

export SCRIPTS_DIR=$( readlink -e $(dirname "${BASH_SOURCE[0]}"))
source ${SCRIPTS_DIR:?}/config.sh
set -e
export GLOBAL_TRUST_BUNDLE_FILE="${SECRETS_DIR:?}/certs/global-trust-bundle"
mkdir -p "$(dirname "${GLOBAL_TRUST_BUNDLE_FILE:?}")"

export WELL_KNOWN_URL=https://console.${ORG_NAME:?}.${GDCH_ZONE:?}.${GDCH_DOMAIN:?}/.well-known/certificate-authority
echo -n | curl ${WELL_KNOWN_URL:?} > ${GLOBAL_TRUST_BUNDLE_FILE:?}