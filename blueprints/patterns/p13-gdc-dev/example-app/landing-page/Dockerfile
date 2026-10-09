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

FROM python:3.11-slim

# Install system dependencies, Git, and utilities
RUN apt-get update && apt-get dist-upgrade -y && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    ca-certificates \
    jq \
    tar \
    gzip \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Upgrade core Python packaging tools (CVE-2026-1703, CVE-2026-24049) and pre-install pytest
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir pytest pytest-mock

# Install static kubectl binary (v1.37.1, Go >= 1.26.2) with SHA256 verification
ARG KUBECTL_VERSION="v1.37.1"
ARG KUBECTL_SHA256="65691ff77eb6fa44c908b77a1082c9f092c3b9733b5cefabec0d1104890e21a8"
RUN curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && echo "${KUBECTL_SHA256}  /usr/local/bin/kubectl" | sha256sum -c - \
    && chmod +x /usr/local/bin/kubectl

# Install static helm binary (v3.22.0, Go >= 1.26.2) with SHA256 verification
ARG HELM_VERSION="v3.22.0"
ARG HELM_SHA256="1e4ab49e429626cf6c6958d914248b78c9730803c2751b87627e171dc800e7bb"
RUN curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" -o /tmp/helm.tar.gz \
    && echo "${HELM_SHA256}  /tmp/helm.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/helm.tar.gz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && rm -rf /tmp/linux-amd64 /tmp/helm.tar.gz \
    && chmod +x /usr/local/bin/helm

# Install static docker CLI client (v29.8.2)
ARG DOCKER_VERSION="29.8.2"
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" -o /tmp/docker.tgz \
    && tar -xzf /tmp/docker.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /tmp/docker.tgz \
    && chmod +x /usr/local/bin/docker

# Install gdcloud CLI (GDC Air-Gapped archive support with emulation stub fallback)
COPY binaries/ /tmp/binaries/
RUN if [ -f /tmp/binaries/gdcloud-linux-amd64.tar.gz ]; then \
        mkdir -p /opt/gdcloud && \
        tar -xzf /tmp/binaries/gdcloud-linux-amd64.tar.gz -C /opt/gdcloud && \
        ln -s /opt/gdcloud/bin/gdcloud /usr/local/bin/gdcloud && \
        rm -rf /tmp/binaries; \
    else \
        printf '#!/bin/sh\n# Google Distributed Cloud (GDC) CLI Stub\nif [ "$1" = "version" ]; then echo "Google Distributed Cloud CLI (gdcloud) v1.15.1 [GDC Air-Gapped / Emulation]"; exit 0; fi\necho "gdcloud CLI (GDC Air-Gapped). To bundle full CLI, place gdcloud-linux-amd64.tar.gz in binaries/ before build."\n' > /usr/local/bin/gdcloud && \
        chmod +x /usr/local/bin/gdcloud && \
        rm -rf /tmp/binaries; \
    fi

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 8080

# Create developer user 'dev' (UID 1000) and directories for configs/caches
RUN useradd -m -u 1000 dev && \
    mkdir -p /home/dev/.config /home/dev/.cache /home/dev/workspace && \
    chown -R dev:dev /home/dev

# Configure environment variables for non-root execution
USER 1000
ENV HOME=/home/dev
ENV PATH=/usr/local/bin:/usr/bin:/bin:/opt/gdcloud/bin
ENV HELM_CONFIG_HOME=/home/dev/.config/helm
ENV HELM_CACHE_HOME=/home/dev/.cache/helm
ENV GDCLOUD_CONFIG_DIR=/home/dev/.config/gdcloud

# Configure Git defaults to prevent dubious ownership warnings on mounted PVCs
RUN git config --global --add safe.directory '*' && \
    git config --global init.defaultBranch main && \
    git config --global user.name "GDC Developer" && \
    git config --global user.email "developer@gdc.local"

CMD ["python3", "/app/app.py"]
