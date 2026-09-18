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

export SCRIPTS_DIR=$( readlink -e $(dirname $0))
source ${SCRIPTS_DIR:?}/config.sh

for role in \
  organization-iam-admin \
  project-creator \
  project-editor \
  user-cluster-admin \
  organization-billing-account-admin \
  organization-billing-account-user \
  organization-billing-manager \
; do \
    gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
    --member="serviceAccount:${IAC_PROJECT:?}:${IAC_SA:?}" \
    --role="$role";\
done

for role in \
  secret-admin \
  cluster-admin \
  standard-cluster-admin \
  namespace-admin \
  workload-viewer \
  cluster-developer \
  project-networkpolicy-admin \
  project-bucket-admin \
  project-bucket-object-admin \
; do \
  gdcloud projects add-iam-policy-binding $IAC_PROJECT \
  --member="serviceAccount:${IAC_PROJECT:?}:${IAC_SA:?}" \
  --role=$role;\
done