#!/usr/bin/env python3
"""
Update all scenario JSON files to use 1-LV-rural3--2-no_sw network profiles.

Profile Mapping (from BDEW Network Selection Analysis):
- Node 1 (Local Authority): G4 load, no PV
- Node 2 (Fire Station): G6 load, PV4, Storage_PV4_H0-G
- Node 3 (Apartment): H0-L load, no PV
- Node 4 (Apartment): H0-L load, no PV
- Node 5 (Apartment HWB): H0-G load, no PV
- Node 6 (Household): H0-L load, PV3, Storage_PV3_H0-L
- Node 7 (Bank): G1 load, no PV
- Node 8 (Household): H0-L load, PV1, Storage_PV1_H0-L
- Node 9 (Household): H0-L load, no PV
"""

import json
import os
from pathlib import Path

# Base path
BASE = Path("/home/benjamin/data")

# Network prefix
NET = "1-LV-rural3--2-no_sw"

# Profile definitions for each node (from paper Table 1)
NODE_PROFILES = {
    1: {"name": "Local Authority", "load": "G4", "pv": None, "storage": None},
    2: {"name": "Fire Fighting Station", "load": "G6", "pv": "PV4", "storage": "Storage_PV4_H0-G"},
    3: {"name": "Apartment", "load": "H0-L", "pv": None, "storage": None},
    4: {"name": "Apartment", "load": "H0-L", "pv": None, "storage": None},
    5: {"name": "Apartment (Hot Water Boiler)", "load": "H0-G", "pv": None, "storage": None},
    6: {"name": "Household", "load": "H0-L", "pv": "PV3", "storage": "Storage_PV3_H0-L"},
    7: {"name": "Bank", "load": "G1", "pv": None, "storage": None},
    8: {"name": "Household", "load": "H0-L", "pv": "PV1", "storage": "Storage_PV1_H0-L"},
    9: {"name": "Household", "load": "H0-L", "pv": None, "storage": None},
}

def make_load_id(profile):
    return f"{NET} Load [{profile}]"

def make_res_id(profile):
    return f"{NET} SGen [{profile}]"

def make_storage_id(profile):
    return f"{NET} Storage [{profile}]"

def update_json(filepath, scenario_type):
    """
    Update a scenario JSON file.
    
    scenario_type: dict with keys:
      - has_rec: bool
      - has_battery: bool  
      - num_suppliers: 1 or 2
      - prosumer_nodes: list of node IDs that are prosumers
      - consumer_nodes: list of node IDs that are consumers
    """
    with open(filepath, 'r') as f:
        cfg = json.load(f)
    
    has_rec = scenario_type['has_rec']
    has_battery = scenario_type['has_battery']
    num_suppliers = scenario_type['num_suppliers']
    prosumer_nodes = scenario_type['prosumer_nodes']
    consumer_nodes = scenario_type['consumer_nodes']
    
    # Update prosumers
    new_prosumers = []
    for i, node_id in enumerate(prosumer_nodes, 1):
        p = NODE_PROFILES[node_id]
        prosumer = {
            "meter_id": f"prosumer_{i:03d}",
            "name": p["name"],
            "node_id": node_id,
            "supplier": {
                "supplier_id": "SUP_A" if num_suppliers == 1 or node_id <= 5 else "SUP_B",
                "balancing_group_id": "BG_A" if num_suppliers == 1 or node_id <= 5 else "BG_B"
            },
            "load": {
                "id": make_load_id(p["load"]),
                "csv_file": "data/load_actual.csv",
                "load_forecast_da_file": "data/load_forecast_da.csv",
                "load_forecast_id_file": "data/load_forecast_id.csv",
                "load_type": "residential" if p["load"].startswith("H") else "commercial",
                "profile": p["load"]
            },
            "res": {
                "id": make_res_id(p["pv"]),
                "csv_file": "data/res_actual.csv",
                "res_forecast_da_file": "data/res_forecast_da.csv",
                "res_forecast_id_file": "data/res_forecast_id.csv",
                "profile": p["pv"]
            }
        }
        if has_rec:
            prosumer["rec"] = "REC_01"
        if has_battery and p["storage"]:
            prosumer["storage"] = {
                "id": make_storage_id(p["storage"]),
                "csv_file": "data/storage_actual.csv",
                "profile": p["storage"]
            }
        new_prosumers.append(prosumer)
    
    # Update consumers
    new_consumers = []
    for i, node_id in enumerate(consumer_nodes, 1):
        p = NODE_PROFILES[node_id]
        consumer = {
            "meter_id": f"consumer_{i:03d}",
            "name": p["name"],
            "node_id": node_id,
            "supplier": {
                "supplier_id": "SUP_A" if num_suppliers == 1 or node_id <= 5 else "SUP_B",
                "balancing_group_id": "BG_A" if num_suppliers == 1 or node_id <= 5 else "BG_B"
            },
            "load": {
                "id": make_load_id(p["load"]),
                "csv_file": "data/load_actual.csv",
                "load_forecast_da_file": "data/load_forecast_da.csv",
                "load_forecast_id_file": "data/load_forecast_id.csv",
                "load_type": "residential" if p["load"].startswith("H") else "commercial",
                "profile": p["load"]
            }
        }
        if has_rec:
            consumer["rec"] = "REC_01"
        new_consumers.append(consumer)
    
    # Update config
    cfg['prosumers'] = new_prosumers
    cfg['consumers'] = new_consumers
    
    # Update RECs
    if has_rec:
        cfg['recs'] = [{
            "rec_id": "REC_01",
            "rec_name": "Renewable Energy Community 1",
            "settlement_method": "proportional"
        }]
    else:
        cfg['recs'] = []
    
    # Update suppliers
    if num_suppliers == 1:
        cfg['suppliers'] = [{
            "supplier_id": "SUP_A",
            "supplier_name": "Supplier A",
            "balancing_groups": [{"balancing_group_id": "BG_A", "balancing_group_name": "Balancing Group A"}],
            "retail_pricing": {"price": "retail_price"},
            "feedin_pricing": {"price": "feedin_price"}
        }]
    else:
        cfg['suppliers'] = [
            {
                "supplier_id": "SUP_A",
                "supplier_name": "Supplier A",
                "balancing_groups": [{"balancing_group_id": "BG_A", "balancing_group_name": "Balancing Group A"}],
                "retail_pricing": {"price": "retail_price"},
                "feedin_pricing": {"price": "feedin_price"}
            },
            {
                "supplier_id": "SUP_B",
                "supplier_name": "Supplier B",
                "balancing_groups": [{"balancing_group_id": "BG_B", "balancing_group_name": "Balancing Group B"}],
                "retail_pricing": {"price": "retail_price"},
                "feedin_pricing": {"price": "feedin_price"}
            }
        ]
    
    # Remove battery sections if not needed
    if not has_battery:
        cfg.pop('battery_storage', None)
        cfg.pop('battery_optimization', None)
    
    # Write back
    with open(filepath, 'w') as f:
        json.dump(cfg, f, indent=2)
    
    print(f"✓ Updated {filepath.name}")

# Scenario definitions
# Prosumer nodes: 2, 6, 8 (have PV)
# Consumer nodes: 1, 3, 4, 5, 7, 9 (no PV)

SCENARIOS = {
    # A scenarios: single supplier
    "A_Scenario_single_supplier_mandate/A1_single_supplier_no_rec.json": {
        "has_rec": False, "has_battery": False, "num_suppliers": 1,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "A_Scenario_single_supplier_mandate/A2_single_supplier_with_rec.json": {
        "has_rec": True, "has_battery": False, "num_suppliers": 1,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "A_Scenario_single_supplier_mandate_mixed/A1_single_supplier_no_rec_mixed.json": {
        "has_rec": False, "has_battery": False, "num_suppliers": 1,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "A_Scenario_single_supplier_mandate_mixed/A2_single_supplier_with_rec_mixed.json": {
        "has_rec": True, "has_battery": False, "num_suppliers": 1,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    # B scenarios: multiple suppliers
    "B_Scenarion_Forecasting/B1_multiple_supplier_no_rec.json": {
        "has_rec": False, "has_battery": False, "num_suppliers": 2,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "B_Scenarion_Forecasting/B2_multiple_supplier_with_rec.json": {
        "has_rec": True, "has_battery": False, "num_suppliers": 2,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "B_Scenarion_Forecasting/B2_multiple_supplier_with_rec_forecasts.json": {
        "has_rec": True, "has_battery": False, "num_suppliers": 2,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "B_Scenarion_Forecasting_mixed/B1_multiple_supplier_no_rec_mixed.json": {
        "has_rec": False, "has_battery": False, "num_suppliers": 2,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "B_Scenarion_Forecasting_mixed/B2_multiple_supplier_with_rec_mixed.json": {
        "has_rec": True, "has_battery": False, "num_suppliers": 2,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    "B_Scenarion_Forecasting_mixed/B2_multiple_supplier_with_rec_forecasts_mixed.json": {
        "has_rec": True, "has_battery": False, "num_suppliers": 2,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
    # C scenario: with battery
    "C_Scenario_Battery_Optimization/C3_single_supplier_rec_battery.json": {
        "has_rec": True, "has_battery": True, "num_suppliers": 1,
        "prosumer_nodes": [2, 6, 8], "consumer_nodes": [1, 3, 4, 5, 7, 9]
    },
}

if __name__ == "__main__":
    print("=" * 60)
    print("UPDATING ALL SCENARIO JSON FILES")
    print("Network: 1-LV-rural3--2-no_sw")
    print("=" * 60)
    
    for rel_path, scenario_type in SCENARIOS.items():
        filepath = BASE / rel_path
        if filepath.exists():
            update_json(filepath, scenario_type)
        else:
            print(f"⚠ Not found: {rel_path}")
    
    print("\n" + "=" * 60)
    print("✓ All scenario JSON files updated")
    print("=" * 60)
