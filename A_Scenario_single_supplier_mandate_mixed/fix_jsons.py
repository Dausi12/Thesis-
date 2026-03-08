import json
import re

# Read the file
with open('A2_single_supplier_with_rec_mixed.json', 'r') as f:
    content = f.read()

# Replace all LV2.101 with LV3.101
content = content.replace('LV2.101', 'LV3.101')

# Replace specific load/gen mappings
replacements = {
    'Load 2 [G4]': 'Load 90 [G4-A]',
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

for old, new in replacements.items():
    content = content.replace(old, new)

# Write back
with open('A2_single_supplier_with_rec_mixed.json', 'w') as f:
    f.write(content)

print("✓ A2_single_supplier_with_rec_mixed.json updated")

# Also fix the remaining consumers in A1_single_supplier_no_rec_mixed.json
with open('A1_single_supplier_no_rec_mixed.json', 'r') as f:
    content = f.read()

# Check if already has some LV3.101 (from partial update)
if 'LV2.101' in content:
    content = content.replace('LV2.101', 'LV3.101')
    
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    with open('A1_single_supplier_no_rec_mixed.json', 'w') as f:
        f.write(content)
    
    print("✓ A1_single_supplier_no_rec_mixed.json completed")
else:
    print("✓ A1_single_supplier_no_rec_mixed.json already updated")
