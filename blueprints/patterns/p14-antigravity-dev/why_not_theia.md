Copyright 2026 Google. This software is provided as-is, without warranty or representation for any use or purpose. Your use of it is subject to your agreement with Google.

# Architectural Decision Record: Why Not Upstream Eclipse Theia?
## A Strategic Rationale for Streamlined, Air-Gap-Native Cloud IDEs & Integrated Notebooks on Google Distributed Cloud (`GDC-ag`)

> **Document Version:** 1.1  
> **Status:** Accepted / Active Architecture  
> **Target Environment:** Google Distributed Cloud Air-Gapped (`GDC-ag`) & Sovereign Kubernetes Clusters  
> **Target Pattern:** Pattern 14 (`p14-antigravity-dev` — Antigravity SDK & Integrated Notebooks Developer IDE Platform)

---

## 1. Executive Summary & Core Thesis

When designing a cloud-hosted developer workspace and MLOps notebook solution on Google Distributed Cloud Air-Gapped (`GDC-ag`), an initial consideration is **upstream Eclipse Theia**—the open-source TypeScript/Node.js IDE framework maintained by the Eclipse Foundation and TypeFox.

However, after architectural analysis, prototyping, and security evaluations in disconnected GDC environments, **upstream Eclipse Theia was rejected in favor of a streamlined, air-gap-native architecture**.

### Core Thesis:
> **Upstream Eclipse Theia is architected for internet-connected environments where dependency downloading, heavy webworker processes, and third-party extension ecosystems are cheap. In a sovereign, air-gapped GDC facility, these characteristics become operational liabilities ("The Air-Gap Tax").**
>
> **Pattern 14 delivers a purpose-built cloud IDE (`/ide/`), co-located JupyterLab 4 notebook surface (`/lab/`), and Antigravity SDK Tri-Backend AI Swarm that reduces memory consumption by ~95%, eliminates external npm build dependencies, builds hermetically in ~10 seconds, and provides native in-pod AI swarm and `.ipynb` v4 cell tools without requiring third-party plugins or operator sidecars.**

---

## 2. Architectural Decision Matrix

| Architectural Dimension | Upstream Eclipse Theia Cloud | Pattern 14 (`p14-antigravity-dev`) | Strategic Value for GDC Air-Gapped |
| :--- | :--- | :--- | :--- |
| **Runtime & Base Image** | Node.js, Yarn, Lerna, C++ `node-gyp` native builds | Python 3.11 stdlib, Debian Bookworm | **100% Hermetic:** Zero npm downloads; builds in ~10 seconds offline. |
| **Idle Memory Footprint** | 1.5 GB – 2.0 GB per session pod | **~50 MB per session pod** (`cpu-gateway`) | **~95% Savings:** 15–25 developer sessions per GDC node. |
| **AI Pair Programming** | Requires `@theia/ai` compilation or Open-VSX `.vsix` plugins | **Antigravity SDK Tri-Backend Swarm** (`LocalOpenAIAgentConfig.lightweight()`, `LiteRTAgentConfig`, `LocalAgentConfig`) | Out-of-the-box sovereign AI via `gemma-gateway` or on-device `.litertlm` with zero plugin configuration. |
| **Jupyter Notebooks (`.ipynb`)** | Requires separate JupyterHub control plane or heavy VS Code extensions | **Co-Located `/lab/` Drawer + Structured `.ipynb` v4 Tools + `%%agy_*` Magics** | Shares `/home/dev/workspace` PVC and OIDC session cookie with automatic `.ipynb.bak` rollback. |
| **Domain Skills (`SKILL.md`)** | Static plugin compilation required | **Hot-Reloadable `/opt/p14-antigravity/skills/*/SKILL.md`** | Platform teams update or add skills live without rebuilding containers. |
| **Security Guardrails** | External IDE settings or plugin-dependent | **PoLP Role Policies + `SAFE_ENV` Secret Scrubbing + `is_safe_verify_cmd`** | Enforces Human-in-the-Loop approval before code or cell mutation and scrubs OIDC/API secrets. |
| **Control Plane Complexity** | Custom CRDs (`TheiaCloudSession`) & Go Operator | Standard Gateway API `HTTPRoute` & K8s Deployments | Zero custom IDE CRDs to install, upgrade, or troubleshoot. |
