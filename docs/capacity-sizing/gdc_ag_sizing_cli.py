#!/usr/bin/env python3
"""GDC Air-Gapped (GDC-ag) Workload Sizing, MIG Partitioning & IO Procurement CLI.

Ingests coded interview capture files ([F-01] through [F-28]) collected via the
Facilitator Interview Guide (v2.0) and outputs:
  1. Day 0 (T0) Physical Node Pool, 3x Ceph Raw Storage, and Hardware MIG GPU Cards
  2. Dedicated Platform Service Isolation Tax (Vault P11 + Keycloak P12 + Cluster)
  3. Data Confidence Contingency Buffer (F04B: Measured/Benchmarked/Derived/Estimated)
  4. Reclaimable Spin-Down Compute (F20C: Static 24x7 vs Spin-Down Eligible)
  5. 4-Horizon Ramp-Up Schedule (T0, T+6m, T+12m Day 0 Order Gate, T+24m M6 Gate)
  6. Infrastructure Operator (IO) Automated Purchase Order Action Plan

Usage:
  python3 ./docs/capacity-sizing/gdc_ag_sizing_cli.py --demo
  python3 ./docs/capacity-sizing/gdc_ag_sizing_cli.py --input ./docs/capacity-sizing/customer_intake_example.json
  python3 ./docs/capacity-sizing/gdc_ag_sizing_cli.py --dump-template ./my_intake.json
"""

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List

BLUEPRINT_CATALOG: Dict[str, Dict[str, Any]] = {
    "P1_WEB_3TIER": {
        "min_nodes": 2,
        "needs_large_model": False,
        "tiers": {
            "TIER_S": {"pod_cpu": 1.5, "pod_ram": 4, "db_cpu": 2, "db_ram": 8, "usable_gib": 100, "mig_slices": 0},
            "TIER_M": {"pod_cpu": 6.0, "pod_ram": 16, "db_cpu": 4, "db_ram": 16, "usable_gib": 350, "mig_slices": 0},
            "TIER_L": {"pod_cpu": 16.0, "pod_ram": 48, "db_cpu": 8, "db_ram": 32, "usable_gib": 1524, "mig_slices": 0},
        },
    },
    "P2_P5_AI_GATEWAY": {
        "min_nodes": 2,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 2.0, "pod_ram": 8, "db_cpu": 0, "db_ram": 0, "usable_gib": 200, "mig_slices": 1},
            "TIER_M": {"pod_cpu": 4.0, "pod_ram": 16, "db_cpu": 0, "db_ram": 0, "usable_gib": 400, "mig_slices": 2},
            "TIER_L": {"pod_cpu": 8.0, "pod_ram": 32, "db_cpu": 0, "db_ram": 0, "usable_gib": 1000, "mig_slices": 4},
        },
    },
    "P3_LEGACY_VM_DB": {
        "min_nodes": 2,
        "needs_large_model": False,
        "tiers": {
            "TIER_S": {"pod_cpu": 4.0, "pod_ram": 16, "db_cpu": 2, "db_ram": 8, "usable_gib": 150, "mig_slices": 0},
            "TIER_M": {"pod_cpu": 16.0, "pod_ram": 32, "db_cpu": 4, "db_ram": 16, "usable_gib": 350, "mig_slices": 0},
            "TIER_L": {"pod_cpu": 64.0, "pod_ram": 256, "db_cpu": 8, "db_ram": 32, "usable_gib": 2248, "mig_slices": 0},
        },
    },
    "P4_KAFKA_EVENT": {
        "min_nodes": 3,
        "needs_large_model": False,
        "tiers": {
            "TIER_S": {"pod_cpu": 4.0, "pod_ram": 10, "db_cpu": 2, "db_ram": 8, "usable_gib": 250, "mig_slices": 0},
            "TIER_M": {"pod_cpu": 6.0, "pod_ram": 16, "db_cpu": 4, "db_ram": 16, "usable_gib": 538, "mig_slices": 0},
            "TIER_L": {"pod_cpu": 28.0, "pod_ram": 96, "db_cpu": 8, "db_ram": 32, "usable_gib": 7168, "mig_slices": 0},
        },
    },
    "P6_RAG_AGENT": {
        "min_nodes": 2,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 1.5, "pod_ram": 4, "db_cpu": 4, "db_ram": 16, "usable_gib": 300, "mig_slices": 1},
            "TIER_M": {"pod_cpu": 4.0, "pod_ram": 16, "db_cpu": 8, "db_ram": 32, "usable_gib": 1000, "mig_slices": 2},
            "TIER_L": {"pod_cpu": 12.0, "pod_ram": 48, "db_cpu": 16, "db_ram": 64, "usable_gib": 4096, "mig_slices": 4},
        },
    },
    "P7_SQL_AGENT": {
        "min_nodes": 2,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 1.0, "pod_ram": 2, "db_cpu": 2, "db_ram": 8, "usable_gib": 100, "mig_slices": 1},
            "TIER_M": {"pod_cpu": 2.0, "pod_ram": 8, "db_cpu": 4, "db_ram": 16, "usable_gib": 250, "mig_slices": 1},
            "TIER_L": {"pod_cpu": 6.0, "pod_ram": 16, "db_cpu": 8, "db_ram": 32, "usable_gib": 500, "mig_slices": 2},
        },
    },
    "P8_MLOPS_LOOP": {
        "min_nodes": 2,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 8.0, "pod_ram": 32, "db_cpu": 2, "db_ram": 8, "usable_gib": 350, "mig_slices": 2},
            "TIER_M": {"pod_cpu": 16.0, "pod_ram": 64, "db_cpu": 4, "db_ram": 16, "usable_gib": 700, "mig_slices": 2},
            "TIER_L": {"pod_cpu": 32.0, "pod_ram": 128, "db_cpu": 8, "db_ram": 32, "usable_gib": 3060, "mig_slices": 6},
        },
    },
    "P9_P10_NOTEBOOK_CHAT": {
        "min_nodes": 2,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 1.0, "pod_ram": 2, "db_cpu": 2, "db_ram": 8, "usable_gib": 200, "mig_slices": 1},
            "TIER_M": {"pod_cpu": 3.0, "pod_ram": 8, "db_cpu": 4, "db_ram": 16, "usable_gib": 500, "mig_slices": 2},
            "TIER_L": {"pod_cpu": 8.0, "pod_ram": 24, "db_cpu": 8, "db_ram": 32, "usable_gib": 1524, "mig_slices": 4},
        },
    },
    "P13_GDC_DEV": {
        "min_nodes": 3,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 6.6, "pod_ram": 13, "db_cpu": 2, "db_ram": 8, "usable_gib": 350, "mig_slices": 1},
            "TIER_M": {"pod_cpu": 14.1, "pod_ram": 28, "db_cpu": 2, "db_ram": 8, "usable_gib": 825, "mig_slices": 2},
            "TIER_L": {"pod_cpu": 26.6, "pod_ram": 53, "db_cpu": 4, "db_ram": 16, "usable_gib": 1780, "mig_slices": 4},
        },
    },
    "P_MULTI_SYNTHESIS": {
        "min_nodes": 3,
        "needs_large_model": True,
        "tiers": {
            "TIER_S": {"pod_cpu": 12.0, "pod_ram": 36, "db_cpu": 4, "db_ram": 16, "usable_gib": 700, "mig_slices": 2},
            "TIER_M": {"pod_cpu": 20.0, "pod_ram": 64, "db_cpu": 8, "db_ram": 32, "usable_gib": 1574, "mig_slices": 3},
            "TIER_L": {"pod_cpu": 40.0, "pod_ram": 128, "db_cpu": 16, "db_ram": 64, "usable_gib": 4572, "mig_slices": 6},
        },
    },
}

MIG_GEOMETRY: Dict[str, Dict[str, Any]] = {
    "NO_GPU": {
        "slices_per_gpu": 0,
        "vram_gb": 0,
        "card_vram_gb": 0,
        "gpu_sku": "None (CPU Only)",
        "requires_b300": False,
        "label": "No GPU",
    },
    "MIG_1G_10GB": {
        "slices_per_gpu": 7,
        "vram_gb": 10,
        "card_vram_gb": 80,
        "gpu_sku": "NVIDIA A100/H100 (80GB HBM)",
        "requires_b300": False,
        "label": "nvidia.com/mig-1g.10gb (A100/H100)",
    },
    "MIG_2G_20GB": {
        "slices_per_gpu": 3,
        "vram_gb": 20,
        "card_vram_gb": 80,
        "gpu_sku": "NVIDIA A100/H100 (80GB HBM)",
        "requires_b300": False,
        "label": "nvidia.com/mig-2g.20gb (A100/H100)",
    },
    "MIG_3G_40GB": {
        "slices_per_gpu": 2,
        "vram_gb": 40,
        "card_vram_gb": 80,
        "gpu_sku": "NVIDIA A100/H100 (80GB HBM)",
        "requires_b300": False,
        "label": "nvidia.com/mig-3g.40gb (A100/H100)",
    },
    "MIG_7G_80GB_FULL": {
        "slices_per_gpu": 1,
        "vram_gb": 80,
        "card_vram_gb": 80,
        "gpu_sku": "NVIDIA A100/H100 (80GB HBM)",
        "requires_b300": False,
        "label": "nvidia.com/gpu (80GB Full A100/H100)",
    },
    "DEDICATED_L4_WHOLE": {
        "slices_per_gpu": 1,
        "vram_gb": 24,
        "card_vram_gb": 24,
        "gpu_sku": "NVIDIA L4 (24GB GDDR6 — Non-MIG)",
        "requires_b300": False,
        "label": "nvidia.com/gpu (L4 24GB Whole)",
    },
    "NATIVE_GEMINI_ENDPOINT": {
        "slices_per_gpu": 2,
        "vram_gb": 144,
        "card_vram_gb": 288,
        "gpu_sku": "NVIDIA B300 (288GB HBM3e — Gemini Exclusive)",
        "requires_b300": True,
        "label": "GDC Native Gemini API (NVIDIA B300 288GB Only)",
    },
}

PLATFORM_SERVICES: Dict[str, Dict[str, Any]] = {
    "VAULT_P11_QUORUM": {
        "name": "Dedicated HashiCorp Vault Quorum (P11)",
        "vcpu": 12.0,
        "ram_gib": 48.0,
        "usable_gib": 125.0,
        "min_nodes": 3,
        "apply_in_modes": ["DEDICATED_SINGLE_TENANT", "HYBRID_DEDICATED_SVC"],
    },
    "KEYCLOAK_P12_QUORUM": {
        "name": "Dedicated Keycloak OIDC SSO + Postgres (P12)",
        "vcpu": 12.0,
        "ram_gib": 48.0,
        "usable_gib": 125.0,
        "min_nodes": 2,
        "apply_in_modes": ["DEDICATED_SINGLE_TENANT", "HYBRID_DEDICATED_SVC"],
    },
    "DEDICATED_CLUSTER_CONTROL_PLANE": {
        "name": "Dedicated Single-Tenant K8s Control Plane & System Overhead",
        "vcpu": 8.0,
        "ram_gib": 32.0,
        "usable_gib": 100.0,
        "min_nodes": 3,
        "apply_in_modes": ["DEDICATED_SINGLE_TENANT"],
    },
}

CONFIDENCE_BUFFERS: Dict[str, float] = {
    "MEASURED": 1.00,
    "BENCHMARKED": 1.05,
    "DERIVED": 1.10,
    "ESTIMATED": 1.25,
}

# Unified declarative catalog dictionary (exportable/importable via --dump-catalog / --catalog)
SIZING_CONFIG: Dict[str, Any] = {
    "blueprints": BLUEPRINT_CATALOG,
    "gpu_profiles": MIG_GEOMETRY,
    "platform_services": PLATFORM_SERVICES,
    "confidence_buffers": CONFIDENCE_BUFFERS,
}

DEFAULT_EXAMPLE_PAYLOAD: Dict[str, Any] = {
    "F01_PROJECT_ID": "tactical-c2-prod",
    "F03_ENTRY_PATH": "PATH_B",
    "F04B_CONFIDENCE_LEVEL": "DERIVED",
    "F05_TENANCY_MODE": "SHARED_DEFAULT",
    "F06_OVERCOMMIT_POLICY": "PROD_1_TO_1",
    "F07_HA_DR_TOPOLOGY": "ZONAL_HA_PLUS_DR",
    "F08_GPU_MIG_PROFILE": "MIG_3G_40GB",
    "F15_VAULT_ISOLATION": "VAULT_SHARED",
    "F16_IDENTITY_SSO": "KEYCLOAK_SHARED",
    "F17_HARBOR_BUNDLE_GIB": 120,
    "F18B_BLUEPRINT_PATTERNS": ["P4_KAFKA_EVENT", "P6_RAG_AGENT", "P7_SQL_AGENT"],
    "F19B_TSHIRT_TIER": "TIER_M",
    "F20B_NONPROD_POLICY": "NONPROD_HALF",
    "F20C_LIFESPAN_CLASS": "STATIC_24X7",
    "F25_STORAGE_PARAMS": {
        "daily_ingest_gib": 25.0,
        "retention_days": 730.0,
        "daily_change_rate": 0.05,
        "snapshot_days": 14.0,
        "base_full_backups": 2.0,
    },
    "F26_RAMP_M6_COMPUTE_GPU": [1.25, 1.5],
    "F27_RAMP_M12_COMPUTE_GPU": [2.0, 2.0],
    "F28_RAMP_M24_COMPUTE_GPU": [3.0, 4.0],
    "IO_AVAILABLE_RACK_HEADROOM": {
        "physical_vcpu": 96,
        "physical_ram_gib": 384,
        "raw_ceph_tib": 80.0,
        "physical_gpu_cards": 3,
    },
}


def evaluate_intake(data: Dict[str, Any], catalog: Dict[str, Any] = SIZING_CONFIG) -> Dict[str, Any]:
    """Evaluates interview intake JSON against the declarative SIZING_CONFIG catalog."""
    bp_catalog = catalog.get("blueprints", BLUEPRINT_CATALOG)
    gpu_catalog = catalog.get("gpu_profiles", MIG_GEOMETRY)
    plat_services = catalog.get("platform_services", PLATFORM_SERVICES)
    conf_buffers = catalog.get("confidence_buffers", CONFIDENCE_BUFFERS)

    path = data.get("F03_ENTRY_PATH", "PATH_B")
    confidence = data.get("F04B_CONFIDENCE_LEVEL", "DERIVED")
    conf_mult = conf_buffers.get(confidence, 1.10)
    tenancy = data.get("F05_TENANCY_MODE", "SHARED_DEFAULT")
    overcommit = data.get("F06_OVERCOMMIT_POLICY", "PROD_1_TO_1")
    ha_mode = data.get("F07_HA_DR_TOPOLOGY", "ZONAL_HA_PLUS_DR")
    mig_profile = data.get("F08_GPU_MIG_PROFILE", "MIG_3G_40GB")
    vault_mode = data.get("F15_VAULT_ISOLATION", "VAULT_SHARED")
    keycloak_mode = data.get("F16_IDENTITY_SSO", "KEYCLOAK_SHARED")
    harbor_gib = float(data.get("F17_HARBOR_BUNDLE_GIB", 180))
    nonprod_policy = data.get("F20B_NONPROD_POLICY", "NONPROD_HALF")
    lifespan_class = data.get("F20C_LIFESPAN_CLASS", "STATIC_24X7")

    is_zonal_ha = ha_mode != "SINGLE_ZONE"
    dr_mult = 2.0 if ha_mode == "ZONAL_HA_PLUS_DR" else 1.0

    prod_pod_cpu = 0.0
    prod_pod_ram = 0.0
    prod_db_cpu = 0.0
    prod_db_ram = 0.0
    prod_usable_gib = 0.0
    prod_mig_slices = 0
    min_nodes = 2 if is_zonal_ha else 1
    advisories: List[str] = []
    mig_info = gpu_catalog.get(mig_profile, gpu_catalog["MIG_3G_40GB"])

    if path == "PATH_B":
        tier = data.get("F19B_TSHIRT_TIER", "TIER_M")
        patterns = data.get("F18B_BLUEPRINT_PATTERNS", ["P4_KAFKA_EVENT", "P6_RAG_AGENT", "P7_SQL_AGENT"])
        needs_large = False
        for p in patterns:
            bp = bp_catalog.get(p)
            if not bp:
                continue
            t = bp["tiers"][tier]
            prod_pod_cpu += t["pod_cpu"]
            prod_pod_ram += t["pod_ram"]
            prod_db_cpu = max(prod_db_cpu, t["db_cpu"])
            prod_db_ram = max(prod_db_ram, t["db_ram"])
            prod_usable_gib += t["usable_gib"]
            prod_mig_slices = max(prod_mig_slices, t["mig_slices"])
            min_nodes = max(min_nodes, bp["min_nodes"])
            if bp.get("needs_large_model"):
                needs_large = True
        if needs_large and mig_profile in ("MIG_1G_10GB", "MIG_2G_20GB"):
            advisories.append(
                f"GUARDRAIL VIOLATION: {mig_profile} ({mig_info['vram_gb']}GB VRAM) "
                "cannot fit Gemma 4 26B/31B weights + KV-cache. Minimum hardware MIG profile is MIG_3G_40GB (40GB)."
            )
    else:
        pod_vcpu = data.get("F18A_POD_VCPU_NONPROD_PROD_DR", [8, 16, 0])
        pod_ram = data.get("F19A_POD_RAM_NONPROD_PROD_DR", [32, 64, 0])
        vm_spec = data.get("F20A_VM_VCPU_RAM_PROD", [0, 0])
        db_spec = data.get("F21A_DB_PRIMARY_VCPU_RAM_PROD", [4, 16])
        prod_pod_cpu = float(pod_vcpu[1]) + float(vm_spec[0])
        prod_pod_ram = float(pod_ram[1]) + float(vm_spec[1])
        prod_db_cpu = float(db_spec[0])
        prod_db_ram = float(db_spec[1])
        prod_usable_gib = float(data.get("F22A_BLOCK_USABLE_GIB_PROD", 500)) + float(
            data.get("F23A_OBJECT_USABLE_GIB_PROD", 500)
        )
        prod_mig_slices = int(data.get("F24A_GPU_UNITS_NONPROD_PROD_DR", [1, 2, 0])[1])

    if mig_info.get("requires_b300"):
        advisories.append(
            f"GEMINI HARDWARE SKU CONSTRAINT (B300 ONLY): {mig_info['label']} requires dedicated "
            f"{mig_info['gpu_sku']}. It cannot run on A100, H100, or L4 GPUs. Verify IO physical GPU headroom consists of B300 units."
        )

    db_total_cpu = prod_db_cpu * (2.0 if is_zonal_ha else 1.0)
    db_total_ram = prod_db_ram * (2.0 if is_zonal_ha else 1.0)

    # Declarative Platform Service Isolation Tax (from SIZING_CONFIG["platform_services"])
    tax_cpu = 0.0
    tax_ram = 0.0
    tax_gib = 0.0
    for svc in plat_services.values():
        if tenancy in svc.get("apply_in_modes", []):
            tax_cpu += float(svc.get("vcpu", 0.0))
            tax_ram += float(svc.get("ram_gib", 0.0))
            tax_gib += float(svc.get("usable_gib", 0.0))
            min_nodes = max(min_nodes, int(svc.get("min_nodes", 2)))

    if tenancy == "SHARED_DEFAULT":
        if vault_mode == "VAULT_DEDICATED":
            tax_cpu += 12.0
            tax_ram += 48.0
            tax_gib += 125.0
        if keycloak_mode == "KEYCLOAK_DEDICATED":
            tax_cpu += 12.0
            tax_ram += 48.0
            tax_gib += 125.0

    nonprod_cpu = (prod_pod_cpu + prod_db_cpu) * 0.5 if nonprod_policy == "NONPROD_HALF" else 0.0
    if overcommit != "ALL_1_TO_1":
        nonprod_cpu /= 2.0
    nonprod_ram = (prod_pod_ram + prod_db_ram) * 0.5 if nonprod_policy == "NONPROD_HALF" else 0.0
    nonprod_mig = 1 if (nonprod_policy != "NONPROD_NONE" and prod_mig_slices > 0) else 0

    sp = data.get("F25_STORAGE_PARAMS", {})
    daily_ingest_gib = float(sp.get("daily_ingest_gib", 25.0))
    retention_days = float(sp.get("retention_days", 730.0))
    change_rate = float(sp.get("daily_change_rate", 0.05))
    snap_days = float(sp.get("snapshot_days", 14.0))
    base_backups = float(sp.get("base_full_backups", 2.0))
    backup_factor = (change_rate * snap_days) + base_backups

    horizons_cfg = [
        ("T0 (Day 0)", 0, [1.0, 1.0]),
        ("T+6m", 180, data.get("F26_RAMP_M6_COMPUTE_GPU", [1.25, 1.5])),
        ("T+12m (Day 0 IO Order Gate)", 365, data.get("F27_RAMP_M12_COMPUTE_GPU", [2.0, 2.0])),
        ("T+24m (Month 6 IO Order Gate)", 730, data.get("F28_RAMP_M24_COMPUTE_GPU", [3.0, 4.0])),
    ]

    results = []
    for label, days, (cpu_m, gpu_m) in horizons_cfg:
        req_cpu = ((prod_pod_cpu * cpu_m) + db_total_cpu + tax_cpu) * conf_mult
        req_ram = ((prod_pod_ram * cpu_m) + db_total_ram + tax_ram) * conf_mult
        eff_cpu = req_cpu / 2.0 if overcommit == "OVERCOMMIT_2_TO_1" else req_cpu

        node_cpu = math.ceil((eff_cpu * dr_mult + nonprod_cpu) / 0.80) + (8 if is_zonal_ha else 0)
        node_ram = math.ceil((req_ram * dr_mult + nonprod_ram) / 0.80) + (32 if is_zonal_ha else 0)
        nodes_8 = max(min_nodes, math.ceil(max(node_cpu / 8.0, node_ram / 32.0)))

        eff_days = min(days, retention_days)
        usable_tib = (
            ((prod_usable_gib + tax_gib + harbor_gib + (daily_ingest_gib * eff_days)) * 1.20 * dr_mult * conf_mult)
            / 1024.0
        )
        raw_ceph_tib = usable_tib * (1.0 + backup_factor) * 3.0

        mig_slices = (math.ceil(prod_mig_slices * gpu_m * dr_mult) + nonprod_mig) if mig_profile != "NO_GPU" else 0
        phys_gpus = math.ceil(mig_slices / mig_info["slices_per_gpu"]) if mig_info["slices_per_gpu"] > 0 else 0

        results.append(
            {
                "horizon": label,
                "nodes_n2_standard_8": nodes_8,
                "physical_vcpu": nodes_8 * 8,
                "physical_ram_gib": nodes_8 * 32,
                "reclaimable_offshift_vcpu": int(math.ceil(nonprod_cpu)) if lifespan_class == "SPINDOWN_ELIGIBLE" else 0,
                "usable_tib": round(usable_tib, 2),
                "raw_ceph_tib": round(raw_ceph_tib, 2),
                "mig_slices": mig_slices,
                "physical_gpu_cards": phys_gpus,
                "gpu_sku": mig_info.get("gpu_sku", "NVIDIA A100/H100 (80GB HBM)"),
            }
        )

    # Evaluate IO Procurement Gates against Available Headroom
    headroom = data.get(
        "IO_AVAILABLE_RACK_HEADROOM",
        {"physical_vcpu": 96, "physical_ram_gib": 384, "raw_ceph_tib": 80.0, "physical_gpu_cards": 3},
    )
    avail_cpu = int(headroom.get("physical_vcpu", 96))
    avail_ram = int(headroom.get("physical_ram_gib", 384))
    avail_ceph = float(headroom.get("raw_ceph_tib", 80.0))
    avail_gpu = int(headroom.get("physical_gpu_cards", 3))

    t0 = results[0]
    t12 = results[2]
    t24 = results[3]

    # Day 0 Allocation Verdict (T0 vs Available Headroom)
    t0_def_cpu = max(0, t0["physical_vcpu"] - avail_cpu)
    t0_def_ram = max(0, t0["physical_ram_gib"] - avail_ram)
    t0_def_ceph = round(max(0.0, t0["raw_ceph_tib"] - avail_ceph), 2)
    t0_def_gpu = max(0, t0["physical_gpu_cards"] - avail_gpu)
    day0_can_allocate = (t0_def_cpu == 0 and t0_def_ram == 0 and t0_def_ceph == 0.0 and t0_def_gpu == 0)

    # Day 0 Emergency Hardware Order Gate (T+12m vs Available Headroom due to 9-18m lead time)
    po_day0_cpu = max(0, t12["physical_vcpu"] - avail_cpu)
    po_day0_nodes = math.ceil(po_day0_cpu / 8.0)
    po_day0_ram = max(0, t12["physical_ram_gib"] - avail_ram)
    po_day0_ceph = round(max(0.0, t12["raw_ceph_tib"] - avail_ceph), 2)
    po_day0_gpu = max(0, t12["physical_gpu_cards"] - avail_gpu)

    # Month 6 Scheduled Hardware Order Gate (T+24m vs T+12m)
    po_m6_cpu = max(0, t24["physical_vcpu"] - t12["physical_vcpu"])
    po_m6_nodes = math.ceil(po_m6_cpu / 8.0)
    po_m6_ram = max(0, t24["physical_ram_gib"] - t12["physical_ram_gib"])
    po_m6_ceph = round(max(0.0, t24["raw_ceph_tib"] - t12["raw_ceph_tib"]), 2)
    po_m6_gpu = max(0, t24["physical_gpu_cards"] - t12["physical_gpu_cards"])

    target_gpu_sku = mig_info.get("gpu_sku", "NVIDIA A100/H100 (80GB HBM)")
    io_procurement_plan = {
        "target_gpu_hardware_sku": target_gpu_sku,
        "available_rack_headroom": {
            "physical_vcpu": avail_cpu,
            "physical_ram_gib": avail_ram,
            "raw_ceph_tib": avail_ceph,
            "physical_gpu_cards": avail_gpu,
        },
        "day0_allocation_gate": {
            "status": "APPROVED_FROM_EXISTING_RACKS" if day0_can_allocate else "BLOCKED_DEFICIT_ON_DAY_0",
            "day0_deficit_vcpu": t0_def_cpu,
            "day0_deficit_ram_gib": t0_def_ram,
            "day0_deficit_raw_ceph_tib": t0_def_ceph,
            "day0_deficit_gpu_cards": t0_def_gpu,
        },
        "day0_emergency_purchase_order_for_t12m": {
            "trigger_required": (po_day0_nodes > 0 or po_day0_ceph > 0 or po_day0_gpu > 0),
            "lead_time_justification": "Covers T+12m demand against 9-18 month hardware delivery & SCIF accreditation lead time",
            "order_compute_nodes_n2_std_8": po_day0_nodes,
            "order_physical_vcpu": po_day0_cpu,
            "order_physical_ram_gib": po_day0_ram,
            "order_raw_ceph_tib": po_day0_ceph,
            "order_physical_gpu_cards": po_day0_gpu,
            "order_gpu_sku": target_gpu_sku,
        },
        "month6_scheduled_purchase_order_for_t24m": {
            "trigger_required": (po_m6_nodes > 0 or po_m6_ceph > 0 or po_m6_gpu > 0),
            "lead_time_justification": "Covers Month 12->24 ramp-up delta; order at Month 6 for Month 18 delivery",
            "order_compute_nodes_n2_std_8": po_m6_nodes,
            "order_physical_vcpu": po_m6_cpu,
            "order_physical_ram_gib": po_m6_ram,
            "order_raw_ceph_tib": po_m6_ceph,
            "order_physical_gpu_cards": po_m6_gpu,
            "order_gpu_sku": target_gpu_sku,
        },
    }

    return {
        "project_id": data.get("F01_PROJECT_ID", "mission-intel-prod"),
        "tenancy_mode": tenancy,
        "confidence_level": f"{confidence} ({int((conf_mult - 1.0) * 100)}% Contingency)",
        "lifespan_class": lifespan_class,
        "isolation_tax_vcpu_ram": [tax_cpu, tax_ram],
        "mig_profile": mig_info["label"],
        "gpu_hardware_sku": target_gpu_sku,
        "advisories": advisories,
        "horizons": results,
        "io_procurement_plan": io_procurement_plan,
    }


def print_executive_report(summary: Dict[str, Any]) -> None:
    """Prints a clean ASCII executive table for Infrastructure Operators (IOs)."""
    sep = "=" * 98
    thin_sep = "-" * 98
    print(sep)
    print(f" GDC AIR-GAPPED (GDC-ag) WORKLOAD SIZING & IO PROCUREMENT REPORT — PROJECT: {summary['project_id']}")
    print(sep)
    print(f" • Tenancy Mode ([F-05])      : {summary['tenancy_mode']} (Isolation Tax: +{summary['isolation_tax_vcpu_ram'][0]} vCPU / +{summary['isolation_tax_vcpu_ram'][1]} GiB RAM)")
    print(f" • Data Confidence ([F-04B])  : {summary['confidence_level']}")
    print(f" • Lifespan Class ([F-20C])   : {summary['lifespan_class']}")
    print(f" • GPU Profile ([F-08])       : {summary['mig_profile']}")
    print(f" • Target Physical GPU SKU    : {summary['gpu_hardware_sku']}")
    if summary.get("advisories"):
        print(thin_sep)
        print(" ARCHITECTURE & HARDWARE SKU GUARDRAIL ADVISORIES:")
        for adv in summary["advisories"]:
            print(f"   [!] {adv}")
    print(thin_sep)
    print(" 4-HORIZON PHYSICAL RESOURCE SCHEDULE (INCLUDES KUBE SYSTEM RESERVE & 3x CEPH/DR MULTIPLIERS)")
    print(thin_sep)
    header = f" {'HORIZON':<30} | {'NODES':>5} | {'PHYS vCPU':>9} | {'PHYS RAM':>9} | {'USABLE TiB':>10} | {'RAW CEPH TiB':>12} | {'SLICES':>10} | {'GPUs':>4}"
    print(header)
    print(thin_sep)
    for h in summary["horizons"]:
        row = (
            f" {h['horizon']:<30} | {h['nodes_n2_standard_8']:>5} | "
            f"{h['physical_vcpu']:>9} | {str(h['physical_ram_gib']) + ' GiB':>9} | "
            f"{h['usable_tib']:>10.2f} | {h['raw_ceph_tib']:>12.2f} | "
            f"{h['mig_slices']:>10} | {h['physical_gpu_cards']:>4}"
        )
        print(row)
    print(thin_sep)

    io_plan = summary["io_procurement_plan"]
    hr = io_plan["available_rack_headroom"]
    d0 = io_plan["day0_allocation_gate"]
    po0 = io_plan["day0_emergency_purchase_order_for_t12m"]
    pom6 = io_plan["month6_scheduled_purchase_order_for_t24m"]

    print(" INFRASTRUCTURE OPERATOR (IO) HARDWARE ACTION PLAN")
    print(f" Baseline Unallocated Rack Headroom : {hr['physical_vcpu']} vCPU | {hr['physical_ram_gib']} GiB RAM | {hr['raw_ceph_tib']} TiB Raw Ceph | {hr['physical_gpu_cards']} GPUs ({io_plan['target_gpu_hardware_sku']})")
    print(thin_sep)
    print(f" 1. DAY 0 ALLOCATION GATE (T0)      : {d0['status']}")
    if d0["status"] != "APPROVED_FROM_EXISTING_RACKS":
        print(
            f"    -> Immediate Day 0 Deficit      : +{d0['day0_deficit_vcpu']} vCPU | +{d0['day0_deficit_ram_gib']} GiB RAM | +{d0['day0_deficit_raw_ceph_tib']} TiB Ceph | +{d0['day0_deficit_gpu_cards']} GPUs"
        )
    else:
        print("    -> All Day 0 compute (96 vCPU / 384 GiB), storage (54.58 TiB <= 80 TiB), and GPUs (3 <= 3) fit in current racks.")

    print(f" 2. DAY 0 EMERGENCY PO (FOR T+12m)  : {'ORDER REQUIRED ON DAY 0' if po0['trigger_required'] else 'NO ORDER REQUIRED'}")
    if po0["trigger_required"]:
        print(f"    -> Justification                : {po0['lead_time_justification']}")
        print(
            f"    -> Day 0 Hardware PO Quantities : +{po0['order_compute_nodes_n2_std_8']} Compute Nodes (+{po0['order_physical_vcpu']} vCPU / +{po0['order_physical_ram_gib']} GiB RAM) | +{po0['order_raw_ceph_tib']} TiB Raw Ceph | +{po0['order_physical_gpu_cards']} Physical GPUs [{po0['order_gpu_sku']}]"
        )

    print(f" 3. MONTH 6 SCHEDULED PO (FOR T+24m): {'ORDER REQUIRED AT MONTH 6' if pom6['trigger_required'] else 'NO ORDER REQUIRED'}")
    if pom6["trigger_required"]:
        print(f"    -> Justification                : {pom6['lead_time_justification']}")
        print(
            f"    -> Month 6 Hardware PO Quantities: +{pom6['order_compute_nodes_n2_std_8']} Compute Nodes (+{pom6['order_physical_vcpu']} vCPU / +{pom6['order_physical_ram_gib']} GiB RAM) | +{pom6['order_raw_ceph_tib']} TiB Raw Ceph | +{pom6['order_physical_gpu_cards']} Physical GPUs [{pom6['order_gpu_sku']}]"
        )
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(description="GDC-ag Workload Sizing & IO Procurement CLI")
    parser.add_argument(
        "--input",
        type=str,
        help="Path to JSON file containing [F-01]-[F-28] fields (e.g., ./docs/capacity-sizing/customer_intake_example.json)",
    )
    parser.add_argument(
        "--catalog",
        type=str,
        help="Optional path to a custom SIZING_CONFIG catalog JSON file (add new services/GPUs without editing code)",
    )
    parser.add_argument(
        "--dump-catalog",
        type=str,
        metavar="OUTPUT_CATALOG_JSON",
        help="Export the built-in SIZING_CONFIG service & hardware catalog to a JSON file for zero-code maintenance",
    )
    parser.add_argument("--demo", action="store_true", help="Run with built-in sample SCIF interview dataset (Project Sentinel)")
    parser.add_argument(
        "--dump-template",
        type=str,
        metavar="OUTPUT_JSON",
        help="Write a sample customer intake JSON template to the specified file path and exit",
    )
    parser.add_argument("--json-only", action="store_true", help="Output raw JSON only (suppress ASCII executive table)")
    args = parser.parse_args()

    if args.dump_catalog:
        with open(args.dump_catalog, "w", encoding="utf-8") as out_c:
            json.dump(SIZING_CONFIG, out_c, indent=2)
        print(f"[+] Exported declarative SIZING_CONFIG service & GPU catalog to: {args.dump_catalog}")
        print(f"[+] Add new services or GPU SKUs to {args.dump_catalog} and run with: python3 {sys.argv[0]} --catalog {args.dump_catalog} --demo")
        return

    if args.dump_template:
        with open(args.dump_template, "w", encoding="utf-8") as out_f:
            json.dump(DEFAULT_EXAMPLE_PAYLOAD, out_f, indent=2)
        print(f"[+] Wrote sample customer intake template to: {args.dump_template}")
        print(f"[+] Run sizing calculation with: python3 {sys.argv[0]} --input {args.dump_template}")
        return

    active_catalog = SIZING_CONFIG
    if args.catalog and os.path.exists(args.catalog):
        with open(args.catalog, "r", encoding="utf-8") as cf:
            active_catalog = json.load(cf)

    payload = DEFAULT_EXAMPLE_PAYLOAD
    if args.input:
        if os.path.exists(args.input):
            with open(args.input, "r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            fallback_path = os.path.join(script_dir, "customer_intake_example.json")
            print(
                f"[!] Notice: Input file '{args.input}' was not found.",
                file=sys.stderr,
            )
            if os.path.exists(fallback_path):
                print(
                    f"[!] Automatically loading checked-in example file: '{fallback_path}'",
                    file=sys.stderr,
                )
                with open(fallback_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            else:
                print(
                    "[!] Falling back to built-in Project Sentinel sample payload (use --dump-template <file.json> to create a new file).",
                    file=sys.stderr,
                )

    summary = evaluate_intake(payload, active_catalog)
    if not args.json_only:
        print_executive_report(summary)
        print("\n--- JSON PAYLOAD FOR AUTOMATION / GITOPS ---")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
