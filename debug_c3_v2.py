import json

notebook_path = r"C:\Users\Hp\Desktop\data\C_Scenario_Battery_Optimization\C3_single_supplier_rec_battery_optimization.ipynb"

# Read the notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

print(f"Total cells: {len(notebook['cells'])}\n")

# Check both source and outputs
for idx, cell in enumerate(notebook['cells']):
    source = cell['source']
    
    # Join source lines
    if isinstance(source, list):
        source_text = ''.join(source)
    else:
        source_text = source
    
    # Check source
    found_in_source = False
    if any(phrase in source_text for phrase in ["Rationale", "traditional day-ahead", "ID-only optimization", "no DA battery optimization"]):
        found_in_source = True
        print(f"===== Cell {idx} ({cell['cell_type']}) - FOUND IN SOURCE =====")
        for line in source_text.split('\n')[:10]:
            print(line)
        print()
    
    # Check outputs
    if 'outputs' in cell and cell['outputs']:
        for output_idx, output in enumerate(cell['outputs']):
            if 'text' in output:
                output_text = ''.join(output['text']) if isinstance(output['text'], list) else output['text']
                if any(phrase in output_text for phrase in ["no DA battery optimization", "ID forecasts only", "ID-only"]):
                    print(f"===== Cell {idx} Output {output_idx} - FOUND IN OUTPUT =====")
                    for line in output_text.split('\n')[:15]:
                        print(line)
                    print()

print("Done scanning all cells")
