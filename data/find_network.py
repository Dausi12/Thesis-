import simbench as sb
import pandas as pd

# Required profiles from JSON
required_loads = {
    'G6': 'prosumer_001 - Fire Fighting Station',
    'H0-A': 'prosumers 2,3 and consumers',
    'G4': 'consumer_001 - Local Authority',
    'H0-G': 'consumer_002 - Apartment Hot Water Boiler',
    'G1': 'consumer_005 - Commercial'
}

# Test networks
test_networks = [
    '1-LV-urban6--0-no_sw',
    '1-LV-urban6--1-no_sw',
    '1-LV-rural3--0-no_sw',
    '1-LV-rural3--1-no_sw',
    '1-LV-rural3--2-no_sw'
]

print("="*80)
print("SEARCHING FOR NETWORK WITH REQUIRED BDEW PROFILES")
print("="*80)
print("\nRequired profiles:", list(required_loads.keys()))
print()

for net_code in test_networks:
    print(f"\n{'='*80}")
    print(f"Testing: {net_code}")
    print(f"{'='*80}")
    
    try:
        net = sb.get_simbench_net(net_code)
        
        # Get load profiles
        load_profiles = {}
        if 'profile' in net.load.columns:
            for profile in net.load['profile'].unique():
                count = (net.load['profile'] == profile).sum()
                load_profiles[profile] = count
        
        print(f"Load profiles found ({len(load_profiles)} types):")
        for profile, count in sorted(load_profiles.items()):
            indicator = "✓" if profile in required_loads else " "
            print(f"  {indicator} {profile}: {count} loads")
        
        # Check which required profiles are present
        missing = [p for p in required_loads.keys() if p not in load_profiles]
        present = [p for p in required_loads.keys() if p in load_profiles]
        
        print(f"\nRequired profiles present: {len(present)}/{len(required_loads)}")
        if missing:
            print(f"Missing: {missing}")
        else:
            print("✓ ALL REQUIRED PROFILES FOUND!")
            print(f"\n{'='*80}")
            print(f"RECOMMENDED NETWORK: {net_code}")
            print(f"{'='*80}")
            
            # Show sample loads with required profiles
            print("\nSample loads with required profiles:")
            for profile in required_loads.keys():
                matching_loads = net.load[net.load['profile'] == profile]
                if len(matching_loads) > 0:
                    sample = matching_loads.head(3)['name'].tolist()
                    print(f"  {profile}: {sample[:3]}")
            
            break
            
    except Exception as e:
        print(f"Error loading network: {e}")

print("\n" + "="*80)
