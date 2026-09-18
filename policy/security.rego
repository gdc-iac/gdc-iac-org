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

package main

deny[msg] {
  input.kind == "ProjectNetworkPolicy"
  some i, j, k
  input.spec.ingress[i].from[j].ipBlock.cidr == "0.0.0.0/0"
  msg = sprintf("ProjectNetworkPolicy '%s' allows ingress from 0.0.0.0/0, which is too permissive.", [input.metadata.name])
}

deny[msg] {
  input.kind == "ProjectNetworkPolicy"
  some i, j, k
  input.spec.egress[i].to[j].ipBlock.cidr == "0.0.0.0/0"
  msg = sprintf("ProjectNetworkPolicy '%s' allows egress to 0.0.0.0/0, which is too permissive.", [input.metadata.name])
}
