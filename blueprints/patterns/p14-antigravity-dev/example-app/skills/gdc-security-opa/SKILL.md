---
name: gdc-security-opa
description: Enforces GDC-ag Restricted Pod Security Standards (PSS), OIDC PKCE/JWKS isolation, zero-egress NetworkPolicies, and SAFE_ENV secret scrubbing.
---

# GDC Security & OPA Compliance Skill (`gdc-security-opa`)

Use this skill when auditing or authoring Kubernetes manifests, Helm charts, and Python services for GDC-ag compliance.

## 1. Restricted Pod Security Standards (PSS)

Every `Deployment`, `StatefulSet`, and workspace `Pod` MUST enforce:
- Pod-level `securityContext`: `runAsNonRoot: true`, `runAsUser: 1000`, `runAsGroup: 1000`, `fsGroup: 1000`, `seccompProfile: { type: RuntimeDefault }`.
- Container-level `securityContext`: `allowPrivilegeEscalation: false`, `capabilities: { drop: ["ALL"] }`.

## 2. OIDC Authentication & Dual-Port Surface Separation

- **Port `8080` (Developer IDE `/ide/` & Integrated JupyterLab `/lab/`)**: Uses `dev_auth_user` / `dev_auth_sig` HMAC-signed cookies validated against `p12-keycloak` (`gdc-dev-realm`) with PKCE (`S256`).
- **Port `8081` (Sovereign Admin & Telemetry Console)**: Uses `admin_auth_user` / `admin_auth_sig` HMAC-signed cookies and requires the `gdc-admin` / `admin` role.
- **Production Enforcement**: `AUTH_MODE: "oidc"` and `ALLOW_SIMULATED_OIDC: "false"` MUST be set in production manifests so simulated query parameters (`?simulated=admin`) return `403 Forbidden`.

## 3. Subprocess & Kernel Secret Scrubbing (`SAFE_ENV`)

Before running any shell command (`run_command` / `subprocess.run`) or Jupyter Notebook cell (`notebook_run_cell`), scrub sensitive platform environment variables (`KEYCLOAK_CLIENT_SECRET`, `OIDC_CLIENT_SECRET`, `GDC_GEMINI_API_KEY`, `GITLAB_PAT`, `COOKIE_SIGNING_SECRET`, `ADMIN_COOKIE_SECRET`).
