import json
import glob

# Define replacement mappings
replacements = {
    'LV2.101': 'LV3.101',
    'LV6.201': 'LV3.101',  # In case any mixed references exist
    'Load 2 [G4]': 'Load 90 [G4-A]',
    'Load 1 [H0-A]': 'Load 90 [G4-A]',  # First prosumer load mapping
    'Load 6 [H0-A]': 'Load 31 [H0-A]',
    'Load 8 [H0-A]': 'Load 24 [H0-A]',
    'Load 1 [G3]': 'Load 46 [G6-A]',
    'Load 3 [H0-G]': 'Load 42 [H0-G]',
    'Load 4 [H0-C]': 'Load 1 [H0-C]',
    'Load 5 [H0-A]': 'Load 27 [H0-A]',
    'Load 7 [G1]': 'Load 97 [G1-C]',
    'Load 9 [H0-A]': 'Load 28 [H0-A]',
    'SGen 2 [PV4]': 'SGen 4 [PV4]',
    'SGen 6 [PV3]': 'SGen 1 [PV7]',
    'SGen 8 [PV1]': 'SGen 2 [PV3]'
}

# Process all JSON files
for json_file in glob.glob('*.json'):
    print(f"\nProcessing {json_file}...")
    
    with open(json_file, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Apply all replacements
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    if content != original_content:
        with open(json_file, 'w') as f:
            f.write(content)
        print(f"  ✓ Updated {json_file}")
    else:
        print(f"  - No changes needed for {json_file}")

print("\n" + "="*60)
print("All A_Scenario mixed JSON files updated!")
print("="*60)
