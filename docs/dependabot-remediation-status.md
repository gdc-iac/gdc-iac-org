# GitHub Dependabot Security Remediation Status (`gdc-iac-org`)

**Tracker URL:** `https://github.com/gdc-iac/gdc-iac-org/security/dependabot`  
**Remediation Branch:** `security/p0-cve-and-auth-remediation-2026-10`  
**Status Date:** `2026-10-09`  
**Overall Status:** ✅ **25 / 25 Dependabot Alerts Remediated & Verified on GKE GPU Cluster**

---

## 1. Executive Summary

All **25 active GitHub Dependabot alerts** tracked at `https://github.com/gdc-iac/gdc-iac-org/security/dependabot` were elevated to **P0** priority, remediated in the upstream blueprint repositories (`GDC-blueprints` and `gdc_gemma_gw`), validated end-to-end on a live GCP GKE GPU cluster (`2026-10-08` – `2026-10-09`), and propagated into `gdc-iac-org` on branch `security/p0-cve-and-auth-remediation-2026-10`.

In addition to closing the 25 directly reported Dependabot alerts across the 5 flagged manifests, all unpinned `requirements.txt`, `package.json`, and `Dockerfile` manifests across Patterns P1–P13 and `gdc_gemma_gw` were pinned to patched versions and upgraded to current base images (`python:3.11-slim`, `node:22-alpine`, `debian:trixie-slim`, `apache/kafka:3.9.0`) to prevent secondary Dependabot findings upon merge.

---

## 2. Alert-by-Alert Remediation Status (All 25 Dependabot Alerts)

| Alert ID | CVE / Advisory | Package | Ecosystem | Manifest Path in `gdc-iac-org` | Vulnerable Spec | Remediated Spec / Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **#27** | `CVE-2024-34064` | `jinja2` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `jinja2==3.1.3` | Upgraded to `jinja2==3.1.6` | ✅ Remediated (`2026-10-09`) |
| **#28** | `CVE-2024-53981` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#29** | `CVE-2024-56326` | `jinja2` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `jinja2==3.1.3` | Upgraded to `jinja2==3.1.6` | ✅ Remediated (`2026-10-09`) |
| **#30** | `CVE-2024-56201` | `jinja2` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `jinja2==3.1.3` | Upgraded to `jinja2==3.1.6` | ✅ Remediated (`2026-10-09`) |
| **#31** | `CVE-2025-27516` | `jinja2` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `jinja2==3.1.3` | Upgraded to `jinja2==3.1.6` | ✅ Remediated (`2026-10-09`) |
| **#32** | `CVE-2026-24486` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#33** | `CVE-2026-40347` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#34** | `CVE-2026-42561` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#35** | `CVE-2026-53537` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#36** | `CVE-2026-53538` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#37** | `CVE-2026-53540` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#38** | `CVE-2026-53539` | `python-multipart` | pip | `blueprints/gdc_gemma_gw/gateway/proxy/requirements.txt` | `python-multipart==0.0.9` | Removed unused `python-multipart` from proxy (`>=0.0.31` where used) | ✅ Remediated (`2026-10-09`) |
| **#39** | `CVE-2026-39365` | `vite` | npm | `blueprints/gdc_gemma_gw/gemma-client/src/frontend/package.json` | `"^5.2.0"` | Upgraded to `"vite": "^6.4.3"` (`node:22-alpine`) | ✅ Remediated (`2026-10-09`) |
| **#40** | `CVE-2026-53571` | `vite` | npm | `blueprints/gdc_gemma_gw/gemma-client/src/frontend/package.json` | `"^5.2.0"` | Upgraded to `"vite": "^6.4.3"` (`node:22-alpine`) | ✅ Remediated (`2026-10-09`) |
| **#41** | `CVE-2026-53632` | `vite` | npm | `blueprints/gdc_gemma_gw/gemma-client/src/frontend/package.json` | `"^5.2.0"` | Upgraded to `"vite": "^6.4.3"` (`node:22-alpine`) | ✅ Remediated (`2026-10-09`) |
| **#43** | `CVE-2024-1681` | `flask-cors` | pip | `blueprints/patterns/p1-resilient-3-tier-webapp/example-app/src/backend/requirements.txt` | `flask-cors==4.0.0` | Upgraded to `flask-cors==6.0.0` | ✅ Remediated (`2026-10-09`) |
| **#44** | `CVE-2024-6221` | `flask-cors` | pip | `blueprints/patterns/p1-resilient-3-tier-webapp/example-app/src/backend/requirements.txt` | `flask-cors==4.0.0` | Upgraded to `flask-cors==6.0.0` | ✅ Remediated (`2026-10-09`) |
| **#45** | `CVE-2024-6844` | `flask-cors` | pip | `blueprints/patterns/p1-resilient-3-tier-webapp/example-app/src/backend/requirements.txt` | `flask-cors==4.0.0` | Upgraded to `flask-cors==6.0.0` | ✅ Remediated (`2026-10-09`) |
| **#46** | `CVE-2024-6866` | `flask-cors` | pip | `blueprints/patterns/p1-resilient-3-tier-webapp/example-app/src/backend/requirements.txt` | `flask-cors==4.0.0` | Upgraded to `flask-cors==6.0.0` | ✅ Remediated (`2026-10-09`) |
| **#47** | `CVE-2024-6839` | `flask-cors` | pip | `blueprints/patterns/p1-resilient-3-tier-webapp/example-app/src/backend/requirements.txt` | `flask-cors==4.0.0` | Upgraded to `flask-cors==6.0.0` | ✅ Remediated (`2026-10-09`) |
| **#50** | `CVE-2026-39365` | `vite` | npm | `blueprints/patterns/p10-gemini-gui/src/frontend/package.json` | `"^5.2.0"` | Upgraded to `"vite": "^6.4.3"` (`node:22-alpine`) | ✅ Remediated (`2026-10-09`) |
| **#51** | `CVE-2026-53571` | `vite` | npm | `blueprints/patterns/p10-gemini-gui/src/frontend/package.json` | `"^5.2.0"` | Upgraded to `"vite": "^6.4.3"` (`node:22-alpine`) | ✅ Remediated (`2026-10-09`) |
| **#52** | `CVE-2026-53632` | `vite` | npm | `blueprints/patterns/p10-gemini-gui/src/frontend/package.json` | `"^5.2.0"` | Upgraded to `"vite": "^6.4.3"` (`node:22-alpine`) | ✅ Remediated (`2026-10-09`) |
| **#53** | `CVE-2026-10142` | `kafka-python` | pip | `blueprints/gdc_gemma_gw/glue-code/telemetry-consumer/requirements.txt` | `kafka-python==2.0.2` | Upgraded to `kafka-python==2.3.2` | ✅ Remediated (`2026-10-09`) |
| **#54** | `CVE-2026-10143` | `kafka-python` | pip | `blueprints/gdc_gemma_gw/glue-code/telemetry-consumer/requirements.txt` | `kafka-python==2.0.2` | Upgraded to `kafka-python==2.3.2` | ✅ Remediated (`2026-10-09`) |

---

## 3. Additional Manifests & Container CVEs Proactively Remediated in This Branch

To ensure zero follow-on Dependabot or container scanner findings when Dependabot re-scans the repository, the following sibling manifests and `Dockerfile` definitions in `gdc-iac-org` were also upgraded and verified:

| Manifest / Component in `gdc-iac-org` | Previous State | Remediated State (`2026-10-09`) | CVE / Risk Closed |
| :--- | :--- | :--- | :--- |
| `blueprints/gdc_gemma_gw/gemma-client/src/backend/requirements.txt` | Unpinned `fastapi`, `python-jose[cryptography]`, `python-multipart` | `fastapi==0.142.2`, `starlette==1.7.0`, `python-multipart==0.0.31`, `PyJWT[crypto]>=2.10.1` (removed `python-jose`) | `CVE-2026-85394` (`python-jose`), `CVE-2024-23342` (`ecdsa`), `CVE-2024-47874` / `CVE-2026-54283` (`starlette`) |
| `blueprints/patterns/p10-gemini-gui/src/backend/requirements.txt` | Unpinned `fastapi`, `python-jose[cryptography]`, `python-multipart` | `fastapi==0.142.2`, `starlette==1.7.0`, `python-multipart==0.0.31`, `PyJWT[crypto]>=2.10.1` (removed `python-jose`) | `CVE-2026-85394` (`python-jose`), `CVE-2024-23342` (`ecdsa`), `CVE-2024-47874` / `CVE-2026-54283` (`starlette`) |
| `blueprints/patterns/p6-resilient-rag-agent/example-app/frontend/package.json` | `"vite": "^7.2.4"`, `"axios": "^1.6.7"` | `"vite": "^7.3.5"`, `"axios": "^1.8.4"` on `node:22-alpine` | `CVE-2026-53571`, `CVE-2026-39365`, `CVE-2026-53632`, `CVE-2025-27152` |
| `blueprints/patterns/p6-resilient-rag-agent/example-app/query-service/Dockerfile` & `blueprints/patterns/p7-agentic-data-analyst/example-app/agent/Dockerfile` | Installed `google-adk==1.27.4` and unpinned `fastapi` / `flask` | Removed unused `google-adk`; pinned `fastapi==0.142.2`, `starlette==1.7.0`, `flask==3.1.3`, `cryptography==46.0.6` | `CVE-2026-4810` (`google-adk`), `CVE-2026-27205` (`flask`) |
| `blueprints/patterns/p4-event-driven-kafka/example-app/{consumer,producer}/requirements.txt` & `manifests/gdc/kafka/kafka.yaml` | Unpinned `kafka-python`, `psycopg2-binary`, and `apache/kafka:3.7.0` | Pinned `kafka-python==2.3.2`, `psycopg2-binary==2.9.10`, and `apache/kafka:3.9.0` | `CVE-2026-10142`, `CVE-2026-10143` |
| `blueprints/patterns/p3-legacy-vm-modern-db/...` | Unpinned `psycopg2-binary`, `python:3.9-slim` | Pinned `psycopg2-binary==2.9.10`, `python:3.11-slim` with `apt-get dist-upgrade -y` | EOL Python 3.9 base image CVEs |
| `blueprints/gdc_gemma_gw/samples/requirements.txt` | `openai>=1.13.3`, `pytest>=8.0.0`, `httpx>=0.27.0` | `openai>=1.68.2`, `pytest>=9.0.3`, `httpx>=0.28.1` | `CVE-2025-71176` (`pytest < 9.0.3`) |
| `blueprints/patterns/p13-gdc-dev/example-app/{landing-page,operator,workspace}/Dockerfile` | `debian:bookworm-slim`, `kubectl` v1.30.0, `helm` v3.15.2, `docker` 26.1.4 | Upgraded all 3 images to `debian:trixie-slim` with `apt-get dist-upgrade -y`, `pip install --break-system-packages --ignore-installed`, `kubectl` `v1.37.1`, `helm` `v3.22.0`, `docker` `29.8.2` | `CVE-2023-45853`, `CVE-2025-7458`, `CVE-2026-58016`, `CVE-2024-24790`, `CVE-2025-68121`, `CVE-2024-41110`, `CVE-2026-33186` |
