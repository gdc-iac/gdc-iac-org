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

# ==============================================================================
# GDC Developer Environment (gdc-dev) Session Image for GDC Air-Gapped
#
# CUSTOMIZATION GUIDE:
# 1. TO ADD CUSTOM SDKS: Add package names or RUN commands to Section 4 below.
# 2. TO SLIM IMAGE / REMOVE TOOLS: Comment out Section 2 (K8s/cloud) or Section 3 (Podman/Buildah).
# ==============================================================================

FROM debian:bookworm-slim

LABEL maintainer="GDC Blueprint Authors"
LABEL description="GDC Developer Environment (gdc-dev) session image pre-baked with enterprise tooling for GDC Air-Gapped."

ARG KUBECTL_VERSION="v1.30.0"
ARG HELM_VERSION="v3.15.2"
ARG DOCKER_CLI_VERSION="26.1.4"

# ------------------------------------------------------------------------------
# SECTION 1: Base Operating System, Git, and Core Utilities (MANDATORY)
# ------------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    git-lfs \
    jq \
    tar \
    gzip \
    unzip \
    procps \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# SECTION 2: Kubernetes & Sovereign Cloud Infrastructure Tools (CUSTOMIZABLE)
# [NOTE: Comment out this entire section if application developers do not manage clusters]
# ------------------------------------------------------------------------------
# 2.1 Install static kubectl binary (in-cluster SA auth)
RUN (curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl) \
    || echo "Notice: kubectl download fallback for offline builds"

# 2.2 Install static Helm binary
RUN (curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" | tar -xz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && rm -rf /tmp/linux-amd64 \
    && chmod +x /usr/local/bin/helm) \
    || echo "Notice: helm download fallback for offline builds"

# 2.3 Install static Docker CLI client (used with remote BuildKit or Podman alias)
RUN (curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" | tar -xz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker \
    && chmod +x /usr/local/bin/docker) \
    || echo "Notice: docker CLI download fallback for offline builds"

# 2.4 Install gdcloud CLI (GDC Air-Gapped archive support with emulation stub fallback)
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

# ------------------------------------------------------------------------------
# SECTION 3: Daemonless Container Engines (Podman & Buildah) (OPTIONAL)
# [NOTE: Comment out this section to save ~400MB if in-pod container builds are disallowed]
# ------------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    podman \
    buildah \
    fuse-overlayfs \
    uidmap \
    && rm -rf /var/lib/apt/lists/*

# Configure Rootless Podman/Buildah storage driver (vfs fallback inside unprivileged Kubernetes containers)
RUN mkdir -p /etc/containers && \
    printf '[storage]\ndriver = "vfs"\nrunroot = "/home/dev/.local/share/containers/storage"\ngraphroot = "/home/dev/.local/share/containers/storage"\n' > /etc/containers/storage.conf

# ------------------------------------------------------------------------------
# SECTION 4: Custom Developer SDKs & Language Runtimes (EXTENSION HOOK)
# [Add your team's specific languages, build tools, and CLIs below]
# ------------------------------------------------------------------------------
# Example A: Golang Toolchain
# RUN apt-get update && apt-get install -y --no-install-recommends golang-go && rm -rf /var/lib/apt/lists/*
# ENV GOPATH=/home/dev/go
# ENV PATH=$PATH:/home/dev/go/bin

# Example B: Java OpenJDK & Maven
# RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk maven gradle && rm -rf /var/lib/apt/lists/*
# ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Example C: Node.js & TypeScript Tooling
# RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && npm install -g typescript yarn pnpm && rm -rf /var/lib/apt/lists/*

# Example D: Internal Corporate CA Certificates (Air-Gapped Trust Store)
# COPY certs/corporate-internal-ca.crt /usr/local/share/ca-certificates/
# RUN update-ca-certificates

# ------------------------------------------------------------------------------
# SECTION 5: Non-Root Developer User 'dev' (UID 1000) & SubUIDs (MANDATORY)
# ------------------------------------------------------------------------------
RUN useradd -m -u 1000 -s /bin/bash dev && \
    echo "dev:100000:65536" >> /etc/subuid && \
    echo "dev:100000:65536" >> /etc/subgid && \
    mkdir -p /home/dev/.config /home/dev/.cache /home/dev/workspace /home/dev/.local/share/containers/storage && \
    chown -R dev:dev /home/dev

# ------------------------------------------------------------------------------
# SECTION 6: User Context, Environment Variables, and Shell Aliases
# ------------------------------------------------------------------------------
USER 1000
WORKDIR /home/dev/workspace

ENV HOME=/home/dev
ENV USER=dev
ENV PATH=/usr/local/bin:/usr/bin:/bin:/opt/gdcloud/bin
ENV HELM_CONFIG_HOME=/home/dev/.config/helm
ENV HELM_CACHE_HOME=/home/dev/.cache/helm
ENV GDCLOUD_CONFIG_DIR=/home/dev/.config/gdcloud

# Configure Git defaults to prevent dubious ownership warnings on mounted PVCs
RUN git config --global --add safe.directory '*' && \
    git config --global init.defaultBranch main && \
    git config --global user.name "GDC Developer" && \
    git config --global user.email "developer@gdc.local"

# Convenience aliases for seamless terminal workflows
RUN echo 'alias docker="podman"' >> /home/dev/.bashrc && \
    echo 'alias k="kubectl"' >> /home/dev/.bashrc && \
    echo 'alias h="helm"' >> /home/dev/.bashrc && \
    echo 'alias gdc="gdcloud"' >> /home/dev/.bashrc

EXPOSE 3000
CMD ["bash"]
