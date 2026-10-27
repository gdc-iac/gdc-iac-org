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

# Install system dependencies, Git, Xvfb (for headless LiteRT Vulkan GPU init), and POSIX utilities
RUN apt-get update && apt-get dist-upgrade -y && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    ca-certificates \
    jq \
    tar \
    gzip \
    procps \
    xvfb \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade core Python packaging tools and install pytest, JupyterLab 4, nbformat, and Antigravity SDK dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir pytest pytest-mock jupyterlab nbformat jupyter_client pydantic

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

# Install gdcloud CLI and any staged offline Python wheels (e.g. latest google_antigravity-*.whl)
COPY binaries/ /tmp/binaries/
RUN mkdir -p /opt/wheelhouse && \
    if ls /tmp/binaries/*.whl 1>/dev/null 2>&1; then \
        cp /tmp/binaries/*.whl /opt/wheelhouse/ && \
        pip install --no-cache-dir --no-index --find-links=/opt/wheelhouse /opt/wheelhouse/*.whl; \
    fi && \
    if [ -f /tmp/binaries/gdcloud-linux-amd64.tar.gz ]; then \
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
COPY app.py gdc_agy_orchestrator.py gdc_antigravity_magic.py /app/
COPY skills/ /opt/p14-antigravity/skills/

EXPOSE 8080 8081 8888

# Create non-root developer user 'dev' (UID 1000) and directories for configs, LiteRT cache, and workspace
RUN useradd -m -u 1000 dev && \
    mkdir -p /home/dev/.config /home/dev/.cache/litert /home/dev/workspace /opt/wheelhouse /opt/p14-antigravity/skills && \
    chown -R dev:dev /home/dev /opt/wheelhouse /opt/p14-antigravity

USER 1000
ENV HOME=/home/dev
ENV PATH=/usr/local/bin:/usr/bin:/bin:/opt/gdcloud/bin
ENV HELM_CONFIG_HOME=/home/dev/.config/helm
ENV HELM_CACHE_HOME=/home/dev/.cache/helm
ENV GDCLOUD_CONFIG_DIR=/home/dev/.config/gdcloud
ENV LITERT_CACHE_DIR=/home/dev/.cache/litert
ENV AGY_SKILLS_PATH=/opt/p14-antigravity/skills

RUN git config --global --add safe.directory '*' && \
    git config --global init.defaultBranch main && \
    git config --global user.name "GDC Developer" && \
    git config --global user.email "developer@gdc.local"

CMD ["python3", "/app/app.py"]
