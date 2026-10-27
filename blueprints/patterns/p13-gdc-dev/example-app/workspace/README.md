# GDC Developer Environment (gdc-dev) Workspace Session Image

This directory contains the production reference `Dockerfile` for packaging custom, enterprise-ready developer session images on Google Distributed Cloud (GDC) Air-Gapped and GCP Emulation environments.

---

## 1. Pre-Baked Default Tooling Matrix

| Tool | Version / Source | Purpose | Permissions / Auth Model |
| :--- | :--- | :--- | :--- |
| **`git` & `git-lfs`** | Debian 12 Bookworm | In-pod source control, branch switching, surgical diff reversion | Configured with `safe.directory '*'` for mounted PVCs |
| **`kubectl`** | v1.30.0 (Static binary) | Inspecting pods, deployments, services, checking logs | Zero-config in-cluster ServiceAccount token mount (`gdc-dev-workspace-sa`) |
| **`helm`** | v3.15.2 (Static binary) | Packaging, deploying, and managing Kubernetes application charts | Uses in-cluster ServiceAccount; OCI registry login to local Harbor |
| **`gdcloud`** | v1.15.1 (GDC Air-Gap bundle) | Managing sovereign GDC infrastructure, VMs, storage, clusters | `GDCLOUD_CONFIG_DIR=/home/dev/.config/gdcloud`; Keycloak OIDC / SA key |
| **`docker` CLI** | v26.1.4 (Static client) | Standard command-line syntax for container operations | Client binary (used with remote BuildKit or aliased to Podman) |
| **`podman`** | Debian 12 Bookworm | Rootless, daemonless OCI container engine without Docker daemon | Configured with `subuid`/`subgid` user namespaces and `vfs` storage |
| **`buildah`** | Debian 12 Bookworm | Daemonless OCI container image builder for Kubernetes pods | Unprivileged OCI builder; builds and pushes directly to Harbor without Docker daemon |

> **Note on Deprecated Tooling (Kaniko):** Google Kaniko (`github.com/GoogleContainerTools/kaniko`) is now archived and read-only upstream. It is no longer supported or recommended. For secure, daemonless container building inside Kubernetes pods on GDC Air-Gapped, use **Rootless Podman (`podman`)** and **Buildah (`buildah`)**.

---

## 2. How to Customize the Workspace Dockerfile

The reference `Dockerfile` is architected into 6 modular sections with clear extension points:

### 2.1 Adding Your Team's Custom Tooling & Runtimes

Add your custom packages or SDKs to **Section 4: Custom Developer SDKs & Language Runtimes**:

#### Recipe A: Adding Golang Development Tools
```dockerfile
# Add to Section 4:
RUN apt-get update && apt-get install -y --no-install-recommends \
    golang-go \
    && rm -rf /var/lib/apt/lists/*
ENV GOPATH=/home/dev/go
ENV PATH=$PATH:/home/dev/go/bin
RUN mkdir -p /home/dev/go && chown -R dev:dev /home/dev/go
```

#### Recipe B: Adding Java (OpenJDK 17/21), Maven & Gradle
```dockerfile
# Add to Section 4:
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk \
    maven \
    gradle \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=$PATH:$JAVA_HOME/bin
```

#### Recipe C: Adding Node.js, TypeScript & Package Managers (yarn, pnpm)
```dockerfile
# Add to Section 4:
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && npm install -g typescript yarn pnpm \
    && rm -rf /var/lib/apt/lists/*
```

#### Recipe D: Adding Internal Corporate / GDC CA Certificates
In air-gapped environments where internal endpoints (Keycloak, Harbor, GitLab) use a private PKI root CA:
```dockerfile
# Add to Section 4:
COPY certs/gdc-internal-ca.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates
```

#### Recipe E: Adding Infrastructure & DevOps Tools (Terraform / OpenTofu)
```dockerfile
# Add to Section 4:
ARG TOFU_VERSION="1.7.2"
RUN curl -fsSL "https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_linux_amd64.tar.gz" | tar -xz -C /tmp \
    && mv /tmp/tofu /usr/local/bin/tofu \
    && chmod +x /usr/local/bin/tofu
```

---

### 2.2 Removing Default Tooling (Image Slimming & Hardening)

If corporate security policies restrict in-pod container building or if application developers do not require cluster administration utilities, you can easily remove default components to reduce image size and attack surface:

#### Scenario 1: Disabling In-Pod Container Engines (Saves ~400MB)
If container builds are executed exclusively in external CI/CD pipelines (e.g. Tekton, Argo):
1. **Comment out or delete Section 3** (`podman`, `buildah`, `fuse-overlayfs`, `uidmap`).
2. **Remove static Docker client** from Section 2.3.
3. **Remove subuid/subgid mapping** from Section 5:
   ```dockerfile
   # Remove these lines:
   # echo "dev:100000:65536" >> /etc/subuid && \
   # echo "dev:100000:65536" >> /etc/subgid && \
   ```
4. **Remove Docker alias** from Section 6 (`alias docker="podman"`).

#### Scenario 2: Stripping Cluster Infrastructure CLIs (`helm`, `gdcloud`, `kubectl`)
For pure frontend or business logic developer workspaces that must not have cluster or cloud management capabilities:
1. **Comment out Section 2.1 (`kubectl`)**, **Section 2.2 (`helm`)**, and **Section 2.4 (`gdcloud`)**.
2. **Remove aliases** from Section 6 (`alias k="kubectl"`, `alias h="helm"`, `alias gdc="gdcloud"`).
3. **Remove environment variables** (`HELM_CONFIG_HOME`, `GDCLOUD_CONFIG_DIR`).

---

## 3. Security & Permission Invariants (Must Preserve)

When customizing the Dockerfile, ensure the following critical security invariants are preserved:

1. **Keep Non-Root User UID 1000:** Always end the build with `USER 1000`. GDC Dev pods run under Pod Security Standards (PSS) that reject root containers.
2. **Preserve Safe Git Directory:** Keep `git config --global --add safe.directory '*'` to prevent Git `dubious ownership` errors when PersistentVolumeClaims (PVCs) are mounted to `/home/dev/workspace`.
3. **Ensure Permissions on `$HOME`:** Any directory created under `/home/dev` (such as `.m2`, `.cache`, `.config`, `go`) must be owned by `dev:dev` (`chown -R dev:dev /home/dev`).

---

## 4. Building, Tagging & Deploying Your Custom Image

### 4.1 Build and Push

```bash
# Build the custom workspace image using build.sh:
./p13-gdc-dev/scripts/build.sh --with-workspace --tag v1.0.0

# Or build manually using Docker / Podman:
docker build -t harbor.shared-services.gdc.local/my-org/gdc-dev-workspace:v1.0.0 p13-gdc-dev/example-app/workspace
docker push harbor.shared-services.gdc.local/my-org/gdc-dev-workspace:v1.0.0
```

### 4.2 Configuring GDC Dev to Use Your Custom Image

In your Helm values (`values-gdc-phase3.yaml`) or deployment manifests, configure the session pod template to target your custom image:

```yaml
session:
  image:
    repository: "harbor.shared-services.gdc.local/my-org/gdc-dev-workspace"
    tag: "v1.0.0"
    pullPolicy: IfNotPresent
```

---

## 5. Architectural Philosophy: Why Upstream Eclipse Theia is Not Needed

A common question when provisioning developer workspaces is whether to include upstream Eclipse Theia (Node.js `@theia/*` runtime). While `gdc-dev` is inspired by the cloud IDE paradigms pioneered by Eclipse Theia Cloud, in air-gapped Google Distributed Cloud (GDC-ag) environments, **upstream Theia is deliberately omitted** for the following architectural reasons:

1. **Zero-Baggage Hermetic Builds:** Upstream Theia pulls hundreds of transitives from npmjs.org, requiring dedicated air-gap npm mirrors, complex `node-gyp` compilations, and frequent rebuild failures. This workspace image builds hermetically in seconds using standard Linux packages.
2. **Minimal Resource Footprint (~50MB vs 1.5GB):** An upstream Theia session idles at 1.5GB–2.0GB of RAM due to Node.js, Monaco workers, and Language Server Protocol (LSP) daemons. This streamlined session consumes ~50MB, allowing **10x to 20x higher developer density** per GDC compute node.
3. **Drastically Reduced Attack Surface:** Stripping out hundreds of third-party JavaScript dependencies eliminates constant CVE scanner alerts and vulnerability patching in high-compliance sovereign racks.
4. **Native Sovereign AI Tool Calling:** Autonomous agent workflows (read/write files, apply AST/unified diffs, run terminal commands, inspect directories) execute directly against the workspace filesystem via in-pod ReAct hooks without requiring third-party VS Code or Open-VSX plugins.

