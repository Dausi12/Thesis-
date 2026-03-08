import json
import glob
import os

# Define the consistent mapping from B1_multiple_supplier_no_rec.json
replacements = {
    'LV6.201': 'LV3.101',
    'LV2.101': 'LV3.101',
    
    # Prosumers (load + generation)
    'Load 5 [G6]': 'Load 46 [G6-A]',
    'Load 15 [H0-A]': 'Load 31 [H0-A]',
    'Load 6 [H0-A]': 'Load 24 [H0-A]',
    'SGen 4 [PV5]': 'SGen 4 [PV4]',
    'SGen 8 [PV2]': 'SGen 1 [PV7]',
    'SGen 5 [PV8]': 'SGen 2 [PV3]',
    
    # Consumers (load only)
    'Load 7 [G4]': 'Load 90 [G4-A]',
    'Load 19 [H0-G]': 'Load 42 [H0-G]',
    'Load 3 [H0-A]': 'Load 27 [H0-A]',
    'Load 8 [H0-A]': 'Load 28 [H0-A]',
    'Load 11 [G1]': 'Load 97 [G1-C]',
    'Load 9 [H0-A]': 'Load 35 [H0-A]'
}

# Process both B_Scenario directories
directories = [
    'c:/Users/Hp/Desktop/data/B_Scenarion_Forecasting',
    'c:/Users/Hp/Desktop/data/B_Scenarion_Forecasting_mixed'
]

total_updated = 0
total_files = 0

for directory in directories:
    if not os.path.exists(directory):
        print(f"Directory not found: {directory}")
        continue
    
    print(f"\n{'='*70}")
    print(f"Processing: {os.path.basename(directory)}")
    print(f"{'='*70}")
    
    json_files = glob.glob(os.path.join(directory, '*.json'))
    
    for json_file in json_files:
        total_files += 1
        filename = os.path.basename(json_file)
        
        # Skip if already processed (B1_multiple_supplier_no_rec.json)
        if filename == 'B1_multiple_supplier_no_rec.json':
            print(f"  ⊙ {filename} - Already updated")
            continue
        
        with open(json_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply all replacements
        for old, new in replacements.items():
            content = content.replace(old, new)
        
        if content != original_content:
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  ✓ {filename} - Updated")
            total_updated += 1
        else:
            print(f"  - {filename} - No changes needed")

print(f"\n{'='*70}")
print(f"Summary: Updated {total_updated} of {total_files} JSON files")
print(f"{'='*70}")
