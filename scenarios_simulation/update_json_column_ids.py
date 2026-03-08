#!/usr/bin/env python3
"""
Universal script to update ALL scenario JSON files with actual column IDs from generated data.
This ensures JSON configs match the column names in the CSV data files.
"""

import json
import os
import csv
from pathlib import Path

def get_column_names(data_dir: str):
    """Get actual column names from the generated CSV files."""
    columns = {}
    
    # Load columns - read only header
    with open(os.path.join(data_dir, 'load_actual.csv'), 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        columns['loads'] = [col for col in header if col != 'datetime']
    
    # RES columns
    with open(os.path.join(data_dir, 'res_actual.csv'), 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        columns['res'] = [col for col in header if col != 'datetime']
    
    # Storage columns
    with open(os.path.join(data_dir, 'storage_actual.csv'), 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        columns['storage'] = [col for col in header if col != 'datetime']
    
    return columns

def categorize_columns(columns: dict):
    """Categorize columns by profile type."""
    categorized = {
        'loads': {
            'residential': [],  # H0
            'commercial': [],   # G1, G2, G3, G4, G5, G6
        },
        'res': {
            'pv': [],  # PV1-PV7
        },
        'storage': []
    }
    
    for col in columns['loads']:
        profile = col.split('[')[-1].replace(']', '')
        if profile.startswith('H0'):
            categorized['loads']['residential'].append(col)
        elif profile.startswith('G'):
            categorized['loads']['commercial'].append(col)
    
    for col in columns['res']:
        categorized['res']['pv'].append(col)
    
    categorized['storage'] = columns['storage']
    
    return categorized

def update_json_config(json_path: str, columns: dict, categorized: dict):
    """Update a JSON config file with actual column IDs."""
    with open(json_path, 'r') as f:
        config = json.load(f)
    
    load_idx = 0
    res_idx = 0
    storage_idx = 0
    
    # Get total counts for distribution
    residential_loads = categorized['loads']['residential']
    commercial_loads = categorized['loads']['commercial']
    all_loads = columns['loads']
    all_res = columns['res']
    all_storage = columns['storage']
    
    # Update prosumers
    if 'prosumers' in config:
        for prosumer in config['prosumers']:
            # Assign load column
            if 'load' in prosumer:
                # Use residential or commercial based on load_type
                load_type = prosumer['load'].get('load_type', 'residential')
                if load_type == 'commercial' and commercial_loads:
                    col = commercial_loads[load_idx % len(commercial_loads)]
                else:
                    col = residential_loads[load_idx % len(residential_loads)] if residential_loads else all_loads[load_idx % len(all_loads)]
                
                prosumer['load']['id'] = col
                # Extract profile from column name
                profile = col.split('[')[-1].replace(']', '')
                prosumer['load']['profile'] = profile
                load_idx += 1
            
            # Assign RES column
            if 'res' in prosumer and all_res:
                col = all_res[res_idx % len(all_res)]
                prosumer['res']['id'] = col
                profile = col.split('[')[-1].replace(']', '')
                prosumer['res']['profile'] = profile
                res_idx += 1
            
            # Assign storage column if present
            if 'storage' in prosumer and all_storage:
                col = all_storage[storage_idx % len(all_storage)]
                prosumer['storage']['id'] = col
                storage_idx += 1
    
    # Update consumers
    if 'consumers' in config:
        for consumer in config['consumers']:
            if 'load' in consumer:
                load_type = consumer['load'].get('load_type', 'residential')
                if load_type == 'commercial' and commercial_loads:
                    col = commercial_loads[load_idx % len(commercial_loads)]
                else:
                    col = residential_loads[load_idx % len(residential_loads)] if residential_loads else all_loads[load_idx % len(all_loads)]
                
                consumer['load']['id'] = col
                profile = col.split('[')[-1].replace(']', '')
                consumer['load']['profile'] = profile
                load_idx += 1
    
    # Update battery_storage if present
    if 'battery_storage' in config:
        battery = config['battery_storage']
        # Check if it's a list or a single object
        if isinstance(battery, list):
            for bat in battery:
                if all_storage:
                    col = all_storage[storage_idx % len(all_storage)]
                    bat['id'] = col
                    storage_idx += 1
        elif isinstance(battery, dict):
            # Single battery object - just note it exists
            # C3 uses battery_id not an id from the storage columns
            storage_idx = 1
    
    # Save updated config
    with open(json_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    return load_idx, res_idx, storage_idx

def main():
    # Paths
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / 'data'
    
    print(f"Data directory: {data_dir}")
    print(f"Script directory: {script_dir}")
    
    # Get actual column names
    print("\n📊 Loading column names from CSV files...")
    columns = get_column_names(str(data_dir))
    print(f"   Loads: {len(columns['loads'])} columns")
    print(f"   RES: {len(columns['res'])} columns")
    print(f"   Storage: {len(columns['storage'])} columns")
    
    # Categorize columns
    categorized = categorize_columns(columns)
    print(f"\n   Residential loads: {len(categorized['loads']['residential'])}")
    print(f"   Commercial loads: {len(categorized['loads']['commercial'])}")
    print(f"   PV generators: {len(categorized['res']['pv'])}")
    
    # Find all JSON config files
    json_files = list(script_dir.glob('*.json'))
    print(f"\n📁 Found {len(json_files)} JSON config files")
    
    # Update each JSON file
    for json_file in sorted(json_files):
        print(f"\n   Updating: {json_file.name}")
        try:
            loads, res, storage = update_json_config(str(json_file), columns, categorized)
            print(f"      ✓ Updated {loads} loads, {res} RES, {storage} storage IDs")
        except Exception as e:
            print(f"      ✗ Error: {e}")
    
    print("\n✅ All JSON files updated with actual column IDs!")

if __name__ == '__main__':
    main()
