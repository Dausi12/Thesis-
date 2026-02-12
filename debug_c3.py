import json

notebook_path = r"C:\Users\Hp\Desktop\data\C_Scenario_Battery_Optimization\C3_single_supplier_rec_battery_optimization.ipynb"

# Read the notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

print(f"Total cells: {len(notebook['cells'])}\n")

# Check for the specific phrases
for idx, cell in enumerate(notebook['cells']):
    source = cell['source']
    
    # Join source lines
    if isinstance(source, list):
        source_text = ''.join(source)
    else:
        source_text = source
    
    # Check for our target phrases
    if "Rationale" in source_text and "DA Battery" in source_text:
        print(f"Cell {idx} ({cell['cell_type']}): Contains 'Rationale for No DA Battery Optimization'")
        print(f"Source (first 300 chars): {source_text[:300]}")
        print()
    
    if "traditional day-ahead" in source_text:
        print(f"Cell {idx} ({cell['cell_type']}): Contains 'traditional day-ahead'")
        print(f"Source (first 300 chars): {source_text[:300]}")
        print()
    
    if 'ID forecasts only' in source_text and 'no DA battery' in source_text:
        print(f"Cell {idx} ({cell['cell_type']}): Contains 'ID forecasts only (no DA battery optimization)'")
        print(f"Source (first 300 chars): {source_text[:300]}")
        print()
    
    if 'ID-only optimization' in source_text:
        print(f"Cell {idx} ({cell['cell_type']}): Contains 'ID-only optimization'") 
        print(f"Source (first 300 chars): {source_text[:300]}")
        print()
