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

# Multi-stage zero-dependency build for the GDCag KMS Auto-Unseal Bridge sidecar.
# Note: In completely disconnected GDCag environments without a mirrored golang builder,
# compile statically on a bastion (`CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o gdc-kms-bridge .`)
# and package over `<project-harbor>/iac/vault:1.15.0` or `scratch`.
FROM golang:1.27-alpine AS builder
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/gdc-kms-bridge .

FROM gcr.io/distroless/static-debian12:nonroot
ENV GODEBUG="tlsmlkem=0"
COPY --from=builder /out/gdc-kms-bridge /usr/local/bin/gdc-kms-bridge
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/gdc-kms-bridge"]
