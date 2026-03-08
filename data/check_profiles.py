import pandas as pd
import json

# Check generated data
try:
    df_load = pd.read_csv('load_forecast_da.csv')
    df_res = pd.read_csv('res_forecast_da.csv')
    
    print("="*80)
    print("GENERATED DATA ANALYSIS - LV3.101 Network")
    print("="*80)
    
    # Extract profile types
    load_profiles = {}
    for col in df_load.columns:
        if '[' in col and ']' in col:
            profile = col.split('[')[1].rstrip(']')
            load_profiles[profile] = load_profiles.get(profile, 0) + 1
    
    print(f"\nLoad Profiles ({len(load_profiles)} types, {len(df_load.columns)-1} total):")
    for profile in sorted(load_profiles.keys()):
        count = load_profiles[profile]
        print(f"  {profile}: {count}")
    
    # Check for required profiles
    required = ['G6-A', 'G4-A', 'G1-C', 'H0-A', 'H0-G']
    print(f"\nRequired profiles check:")
    for req in required:
        status = "✓" if req in load_profiles else "✗"
        count = load_profiles.get(req, 0)
        print(f"  {status} {req}: {count} loads")
    
    # Find specific loads with required profiles
    print(f"\nSample loads with commercial profiles:")
    for profile in ['G6-A', 'G4-A', 'G1-C']:
        matching = [c for c in df_load.columns if f'[{profile}]' in c]
        if matching:
            print(f"  {profile}: {matching[:3]}")
    
    # RES profiles
    res_profiles = [c for c in df_res.columns if 'SGen' in c]
    print(f"\nRES Generators: {len(res_profiles)}")
    print(f"  Sample: {res_profiles[:5]}")
    
    print("\n" + "="*80)
    
except FileNotFoundError as e:
    print(f"Data files not ready yet: {e}")
except Exception as e:
    print(f"Error: {e}")
