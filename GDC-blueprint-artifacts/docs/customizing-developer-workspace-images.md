# Customizing Developer Workspace Images (gdc-dev) on Google Distributed Cloud

> **Reference Guide for Pattern 13 (gdc-dev)**  
> **Source Dockerfile:** `p13-gdc-dev/example-app/workspace/Dockerfile`

---

## 1. Overview

In Google Distributed Cloud (GDC) air-gapped and emulation environments, software developers and autonomous AI agents (`Architect`, `Coder`, `Reviewer`) interact directly with containerized developer session pods (`gdc-dev-workspace`). 

To maximize developer productivity without requiring external workstation software, the default workspace image comes pre-baked with core cloud-native tools (`git`, `kubectl`, `helm`, `gdcloud`, rootless `podman`, and `buildah`).

This guide explains how to:
1. Understand the pre-baked tooling architecture and security model.
2. Add custom programming language SDKs, runtimes, and enterprise CA certificates.
3. Remove unneeded tools to slim image size and enforce least-privilege security policies.
4. Build, tag, and configure `gdc-dev` deployments to use your custom images.

---

## 2. Pre-Baked Default Tooling Matrix

| Tool | Version / Source | Primary Role | In-Pod Authentication & Security Model |
| :--- | :--- | :--- | :--- |
| **`git` & `git-lfs`** | Debian 12 Bookworm | In-pod source control, branch switching, surgical diff reversion | Configured with `safe.directory '*'` to eliminate PVC mount ownership errors |
| **`kubectl`** | v1.30.0 (Static binary) | Inspecting pods, deployments, services, querying logs, CRDs | In-cluster ServiceAccount token mount (`/var/run/secrets/kubernetes.io/serviceaccount/token`) |
| **`helm`** | v3.15.2 (Static binary) | Packaging, deploying, and managing Kubernetes application charts | Uses in-cluster ServiceAccount; OCI registry login to local GDC Harbor |
| **`gdcloud`** | v1.15.1 (GDC Air-Gap bundle) | Managing sovereign GDC infrastructure, VMs, storage, clusters | `GDCLOUD_CONFIG_DIR=/home/dev/.config/gdcloud`; Keycloak OIDC / SA key |
| **`docker` CLI** | v26.1.4 (Static client) | Standard command-line syntax for container operations | Client binary (used with remote BuildKit or aliased to Podman) |
| **`podman`** | Debian 12 Bookworm | Rootless, daemonless OCI container engine without Docker daemon | Configured with `subuid`/`subgid` user namespaces and `vfs` storage |
| **`buildah`** | Debian 12 Bookworm | Daemonless OCI container image builder for Kubernetes pods | Unprivileged OCI builder; builds and pushes directly to Harbor without Docker daemon |

> [!WARNING]
> **Kaniko Deprecation & Archival Notice:** Google Kaniko (`github.com/GoogleContainerTools/kaniko`) has been archived and placed in read-only status upstream. It is no longer supported or recommended for enterprise production. For secure, daemonless container building inside Kubernetes pods on GDC Air-Gapped, use **Rootless Podman (`podman`)** and **Buildah (`buildah`)**.

---

## 3. Reference Dockerfile (`p13-gdc-dev/example-app/workspace/Dockerfile`)

```dockerfile
# GDC Developer Workspace Session Image for GDC Air-Gapped
# Includes: git, kubectl, helm, gdcloud, docker CLI, podman & buildah (rootless)
FROM debian:bookworm-slim

ARG KUBECTL_VERSION="v1.30.0"
ARG HELM_VERSION="v3.15.2"
ARG DOCKER_CLI_VERSION="26.1.4"

# 1. Base OS dependencies, Git, runtimes, and daemonless container builders (Podman & Buildah)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git git-lfs jq tar gzip unzip procps \
    python3 python3-pip python3-venv podman buildah fuse-overlayfs uidmap \
    && rm -rf /var/lib/apt/lists/*

# 2. Static kubectl binary
RUN (curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl) || true

# 3. Static Helm binary
RUN (curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" | tar -xz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && rm -rf /tmp/linux-amd64 \
    && chmod +x /usr/local/bin/helm) || true

# 4. Static Docker CLI client
RUN (curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" | tar -xz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker \
    && chmod +x /usr/local/bin/docker) || true

# 5. gdcloud CLI (GDC air-gapped bundle with emulation stub fallback)
COPY binaries/ /tmp/binaries/
RUN if [ -f /tmp/binaries/gdcloud-linux-amd64.tar.gz ]; then \
        mkdir -p /opt/gdcloud && \
        tar -xzf /tmp/binaries/gdcloud-linux-amd64.tar.gz -C /opt/gdcloud && \
        ln -s /opt/gdcloud/bin/gdcloud /usr/local/bin/gdcloud && \
        rm -rf /tmp/binaries; \
    else \
        printf "#!/bin/sh\nif [ \"\$1\" = \"version\" ]; then echo \"Google Distributed Cloud CLI (gdcloud) v1.15.1 [GDC Air-Gapped / Emulation]\"; exit 0; fi\necho \"gdcloud CLI (GDC Air-Gapped). Drop gdcloud-linux-amd64.tar.gz into binaries/ for full CLI.\"\n" > /usr/local/bin/gdcloud && \
        chmod +x /usr/local/bin/gdcloud && \
        rm -rf /tmp/binaries; \
    fi

# 6. Non-root developer user dev (UID 1000) & SubUIDs for Rootless Podman/Buildah
RUN useradd -m -u 1000 -s /bin/bash dev && \
    echo "dev:100000:65536" >> /etc/subuid && \
    echo "dev:100000:65536" >> /etc/subgid && \
    mkdir -p /home/dev/.config /home/dev/.cache /home/dev/workspace /home/dev/.local/share/containers/storage && \
    chown -R dev:dev /home/dev

# 7. Podman & Buildah rootless storage configuration
RUN mkdir -p /etc/containers && \
    printf "[storage]\ndriver = \"vfs\"\nrunroot = \"/home/dev/.local/share/containers/storage\"\ngraphroot = \"/home/dev/.local/share/containers/storage\"\n" > /etc/containers/storage.conf

# 8. Environment variables & Git safety config
USER 1000
WORKDIR /home/dev/workspace

ENV HOME=/home/dev
ENV PATH=/usr/local/bin:/usr/bin:/bin:/opt/gdcloud/bin
ENV HELM_CONFIG_HOME=/home/dev/.config/helm
ENV HELM_CACHE_HOME=/home/dev/.cache/helm
ENV GDCLOUD_CONFIG_DIR=/home/dev/.config/gdcloud

RUN git config --global --add safe.directory "*" && \
    git config --global init.defaultBranch main && \
    echo 'alias docker="podman"' >> /home/dev/.bashrc && \
    echo 'alias k="kubectl"' >> /home/dev/.bashrc

EXPOSE 3000
CMD ["bash"]
```

---

## 4. Customizing Workspace Images: Adding Languages & SDKs

The reference Dockerfile contains designated extension sections. To add enterprise toolchains, insert recipes into **Section 4: Custom Developer SDKs & Language Runtimes**:

### Recipe A: Golang Toolchain (Go 1.22+)
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    golang-go \
    && rm -rf /var/lib/apt/lists/*
ENV GOPATH=/home/dev/go
ENV PATH=$PATH:/home/dev/go/bin
RUN mkdir -p /home/dev/go && chown -R dev:dev /home/dev/go
```

### Recipe B: Java OpenJDK (17/21), Maven & Gradle
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk \
    maven \
    gradle \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=$PATH:$JAVA_HOME/bin
```

### Recipe C: Node.js, TypeScript, and Package Managers (pnpm, yarn)
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && npm install -g typescript yarn pnpm \
    && rm -rf /var/lib/apt/lists/*
```

### Recipe D: Corporate / Internal GDC Root CA Certificates
In GDC Air-Gapped environments, internal services (Keycloak SSO, Harbor OCI registry, GitLab/Gitea) use a private corporate PKI. Inject your internal CA certificate into the system trust store:
```dockerfile
COPY certs/gdc-internal-ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates
```

### Recipe E: Infrastructure & GitOps Tools (OpenTofu / Terraform)
```dockerfile
ARG TOFU_VERSION="1.7.2"
RUN curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_amd64.tar.gz" | tar -xz -C /tmp \
    && mv /tmp/tofu /usr/local/bin/tofu \
    && chmod +x /usr/local/bin/tofu
```

---

## 5. Removing Default Tooling (Image Slimming & Least Privilege)

Platform operators can reduce image footprint and enforce the Principle of Least Privilege by removing unnecessary tools:

### Scenario 1: Removing Container Engines (`podman`, `buildah`, `docker` CLI) — Saves ~400MB
If enterprise policy mandates that container images may only be built via centralized CI/CD pipelines (Tekton, Argo Workflows) and not inside interactive developer pods:
1. **Comment out Section 3** in `workspace/Dockerfile`:
   ```dockerfile
   # RUN apt-get update && apt-get install -y --no-install-recommends \
   #     podman buildah fuse-overlayfs uidmap && rm -rf /var/lib/apt/lists/*
   ```
2. **Remove Section 2.3** (`docker` CLI static client).
3. **Remove subuid/subgid user namespace mappings** in Section 5:
   ```dockerfile
   # echo "dev:100000:65536" >> /etc/subuid && \
   # echo "dev:100000:65536" >> /etc/subgid && \
   ```
4. **Remove Docker alias** in Section 6 (`alias docker="podman"`).

### Scenario 2: Removing Cluster Management CLIs (`helm`, `gdcloud`, `kubectl`)
For application developers who do not deploy infrastructure and should not have cluster mutation privileges:
1. **Comment out Section 2.1 (`kubectl`)**, **Section 2.2 (`helm`)**, and **Section 2.4 (`gdcloud`)**.
2. **Remove aliases** in Section 6 (`alias k="kubectl"`, `alias h="helm"`, `alias gdc="gdcloud"`).
3. **Remove environment variables** (`HELM_CONFIG_HOME`, `GDCLOUD_CONFIG_DIR`).

---

## 6. Security & Permission Invariants (Must Preserve)

When customizing developer workspace session images, always preserve these 3 security invariants:

1. **Non-Root Execution (`USER 1000`):** Always run as user `dev` (UID 1000). `gdc-dev` pods enforce Kubernetes Pod Security Standards (PSS) that reject root containers (`runAsNonRoot: true`).
2. **PersistentVolume Safe Git Directory:** Maintain `git config --global --add safe.directory '*'` to eliminate ownership mismatch errors when mounting developer PVCs backed by GDC block storage.
3. **Directory Ownership in `$HOME`:** Any custom SDK directory created under `/home/dev` (e.g. `.m2`, `.cache`, `go`) must be owned by `dev:dev` (`chown -R dev:dev /home/dev`).

---

## 7. Building, Tagging & Configuring gdc-dev to Use Custom Images

### 7.1 Build and Push Custom Image
```bash
# Using build script:
./p13-gdc-dev/scripts/build.sh --with-workspace --tag v1.0.0

# Or build manually using Docker:
docker build -t harbor.shared-services.gdc.local/my-org/gdc-dev-workspace-custom:v1.0.0 p13-gdc-dev/example-app/workspace
docker push harbor.shared-services.gdc.local/my-org/gdc-dev-workspace-custom:v1.0.0
```

### 7.2 Configure Deployment to Use Custom Image
Update `values-gdc-phase3.yaml` or workspace session deployment templates:
```yaml
session:
  image:
    repository: "harbor.shared-services.gdc.local/my-org/gdc-dev-workspace-custom"
    tag: "v1.0.0"
    pullPolicy: IfNotPresent
```
