import json

notebook_path = r"C:\Users\Hp\Desktop\data\C_Scenario_Battery_Optimization\C3_single_supplier_rec_battery_optimization.ipynb"

# Read the notebook
with open(notebook_path, 'r', encoding='utf-8') as f:
    notebook = json.load(f)

changes_made = []

# Iterate through cells
for idx, cell in enumerate(notebook['cells']):
    if cell['cell_type'] == 'markdown':
        source = ''.join(cell['source'])
        
        # Debug: check for our target strings
        if "Rationale for No DA Battery Optimization" in source:
            print(f"Found 'Rationale' in cell {idx}")
            print(f"Source preview: {source[:200]}")
        if "traditional day-ahead battery optimization" in source:
            print(f"Found 'traditional' in cell {idx}")
            print(f"Source preview: {source[:200]}")
        if "ID-only optimization" in source:
            print(f"Found 'ID-only' in cell {idx}")
            print(f"Source preview: {source[:200]}")
        
        # Fix 1: Replace "Rationale for No DA Battery Optimization" section
        if "**Rationale for No DA Battery Optimization:**" in source:
            old_section = """**Rationale for No DA Battery Optimization:**
- DA forecasts have higher error margins compared to ID forecasts
- Battery optimization with inaccurate forecasts leads to suboptimal schedules
- ID forecasts (refreshed hourly) provide superior input for battery decisions
- 1-hour-ahead optimization minimizes forecast-related balancing costs"""
            
            new_section = "The day-ahead market establishes the baseline trading position based on forecasted supply and demand. The supplier procures or sells energy one day in advance at the DA market price, setting up the foundation for subsequent intra-day adjustments."
            
            source = source.replace(old_section, new_section)
            cell['source'] = source.splitlines(True)
            changes_made.append("Replaced 'Rationale for No DA Battery Optimization' section with standard DA market description")
        
        # Fix 4: Replace "Unlike traditional day-ahead battery optimization"
        if "Unlike traditional day-ahead battery optimization, this scenario uses" in source:
            source = source.replace(
                "Unlike traditional day-ahead battery optimization, this scenario uses **hourly-refreshed intra-day forecasts only** to optimize",
                "This scenario uses **hourly-refreshed intra-day forecasts** to optimize"
            )
            source = source.replace(
                "This approach minimizes forecast errors and balancing costs by leveraging the superior accuracy of short-term ID forecasts.",
                "Battery optimization occurs exclusively in the intra-day market, leveraging the superior accuracy of short-term ID forecasts to minimize forecast errors and balancing costs."
            )
            cell['source'] = source.splitlines(True)
            changes_made.append("Rewrote 'Key Innovation' section to remove 'traditional day-ahead battery optimization'")
        
        # Fix 5: Replace "ID-only optimization" bullet point
        if "**ID-only optimization**: No DA battery optimization" in source:
            source = source.replace(
                "- **ID-only optimization**: No DA battery optimization (DA establishes baseline only)",
                "- **Intra-day battery optimization**: Batteries optimized in ID market with 1-hour-ahead forecasts"
            )
            cell['source'] = source.splitlines(True)
            changes_made.append("Replaced 'ID-only optimization' with 'Intra-day battery optimization'")
    
    elif cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        
        # Debug
        if 'ID forecasts only (no DA battery optimization)' in source:
            print(f"Found print statement in cell {idx}")
        
        # Fix 2 & 3: Fix print statements
        if 'ID forecasts only (no DA battery optimization)' in source:
            source = source.replace(
                'ID forecasts only (no DA battery optimization)',
                'ID forecasts for battery optimization'
            )
            cell['source'] = source.splitlines(True)
            changes_made.append("Updated print statement to remove '(no DA battery optimization)'")
        
        # Also fix any comments
        if '(no DA battery optimization)' in source:
            source = source.replace('(no DA battery optimization)', '')
            source = source.replace('ID-only', 'ID')
            cell['source'] = source.splitlines(True)
            changes_made.append("Removed '(no DA battery optimization)' from code comments")
        
        # Fix stored outputs
        if 'outputs' in cell:
            for output in cell['outputs']:
                if 'text' in output:
                    text = ''.join(output['text'])
                    if 'ID forecasts only (no DA battery optimization)' in text:
                        text = text.replace(
                            'ID forecasts only (no DA battery optimization)',
                            'ID forecasts for battery optimization'
                        )
                        output['text'] = text.splitlines(True)
                        changes_made.append("Updated cell output to remove '(no DA battery optimization)'")

# Write the modified notebook
with open(notebook_path, 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

print(f"✅ Successfully updated {notebook_path}")
print(f"\nChanges made ({len(changes_made)} updates):")
for i, change in enumerate(changes_made, 1):
    print(f"{i}. {change}")
