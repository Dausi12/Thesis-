"""
SimBench Profile Classes Extractor
===================================
This script extracts all load and RES (Renewable Energy Sources) profile classes
from SimBench networks.

Profile Types:
- BDEW Load Profiles: H0, G0-G6, L0-L2 (residential, commercial, agricultural)
- PV Profiles: PV1-PV8 (photovoltaic by power class)
- Wind Profiles: WP1-WP12
- Biomass Profiles: BM1-BM5
- Hydro Profiles: Hydro1-Hydro3
- Heat Pump/Storage Profiles: HS, HLS, APLS, etc.
"""

import simbench as sb
import pandas as pd
from collections import defaultdict
import re


def get_all_load_profile_classes(net=None):
    """
    Extract all unique load profile classes from SimBench.
    
    Returns:
        dict: Dictionary with profile base classes and their variants
    """
    if net is None:
        # Load a complete network to get all profiles
        net = sb.get_simbench_net("1-complete_data-mixed-all-0-sw")
    
    # Get load profiles from the profiles dataframe
    if "profiles" in net and "load" in net["profiles"]:
        load_profile_columns = list(net["profiles"]["load"].columns)
    else:
        load_profile_columns = []
    
    # Get unique profiles assigned to loads
    if "load" in net and "profile" in net.load.columns:
        assigned_profiles = net.load["profile"].unique().tolist()
    else:
        assigned_profiles = []
    
    # Parse profile names to extract base classes
    bdew_profiles = defaultdict(list)
    other_profiles = defaultdict(list)
    
    all_profiles = set(load_profile_columns) | set(assigned_profiles)
    
    for profile in all_profiles:
        if profile is None:
            continue
        profile = str(profile)
        
        # BDEW Standard Load Profiles (H0, G0-G6, L0-L2)
        if profile.startswith(('H0', 'G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'L0', 'L1', 'L2')):
            # Extract base class (e.g., H0, G1, L2)
            match = re.match(r'^([HGL]\d)', profile)
            if match:
                base_class = match.group(1)
                bdew_profiles[base_class].append(profile)
        
        # Heat pump and storage profiles
        elif profile.startswith(('HS', 'HLS', 'APLS', 'BL-', 'WB-')):
            base = profile.split('-')[0].split('_')[0]
            other_profiles[base].append(profile)
        
        # Aggregated load profiles (lv_, mv_, hv_)
        elif profile.startswith(('lv_', 'mv_', 'hv_')):
            prefix = profile.split('_')[0] + '_' + profile.split('_')[1]
            other_profiles["Aggregated"].append(profile)
        
        # Air/Soil heat pump profiles
        elif profile.startswith(('Air_', 'Soil_')):
            other_profiles["HeatPump"].append(profile)
        
        else:
            other_profiles["Other"].append(profile)
    
    return {
        "bdew_load_profiles": dict(bdew_profiles),
        "other_load_profiles": dict(other_profiles)
    }


def get_all_res_profile_classes(net=None):
    """
    Extract all unique RES (Renewable Energy Sources) profile classes from SimBench.
    
    Returns:
        dict: Dictionary with RES profile categories and their variants
    """
    if net is None:
        # Load a complete network to get all profiles
        net = sb.get_simbench_net("1-complete_data-mixed-all-0-sw")
    
    # Get RES profiles from the profiles dataframe
    if "profiles" in net and "renewables" in net["profiles"]:
        res_profile_columns = list(net["profiles"]["renewables"].columns)
    else:
        res_profile_columns = []
    
    # Get unique profiles assigned to sgens
    if "sgen" in net and "profile" in net.sgen.columns:
        assigned_profiles = net.sgen["profile"].unique().tolist()
    else:
        assigned_profiles = []
    
    # Parse profile names to extract categories
    pv_profiles = []
    wind_profiles = []
    biomass_profiles = []
    hydro_profiles = []
    aggregated_profiles = []
    other_profiles = []
    
    all_profiles = set(res_profile_columns) | set(assigned_profiles)
    
    for profile in all_profiles:
        if profile is None:
            continue
        profile = str(profile)
        
        # PV (Photovoltaic) profiles
        if profile.startswith('PV'):
            pv_profiles.append(profile)
        
        # Wind Power profiles
        elif profile.startswith('WP'):
            wind_profiles.append(profile)
        
        # Biomass profiles
        elif profile.startswith('BM'):
            biomass_profiles.append(profile)
        
        # Hydro profiles
        elif profile.startswith('Hydro'):
            hydro_profiles.append(profile)
        
        # Aggregated RES profiles (lv_, mv_, hv_)
        elif profile.startswith(('lv_', 'mv_', 'hv_')):
            aggregated_profiles.append(profile)
        
        else:
            other_profiles.append(profile)
    
    return {
        "pv_profiles": sorted(pv_profiles),
        "wind_profiles": sorted(wind_profiles),
        "biomass_profiles": sorted(biomass_profiles),
        "hydro_profiles": sorted(hydro_profiles),
        "aggregated_res_profiles": sorted(aggregated_profiles),
        "other_res_profiles": sorted(other_profiles)
    }


def get_bdew_profile_descriptions():
    """
    Get BDEW standard load profile descriptions.
    
    Returns:
        dict: BDEW profile classes with descriptions
    """
    return {
        "H0": {
            "name": "Household",
            "description": "Residential household load profile",
            "typical_use": "Private households, apartments"
        },
        "G0": {
            "name": "Commercial General",
            "description": "General commercial load profile",
            "typical_use": "General commercial operations"
        },
        "G1": {
            "name": "Commercial (Weekday 8-18)",
            "description": "Commercial with operation mainly during weekday daytime",
            "typical_use": "Offices, administrative buildings"
        },
        "G2": {
            "name": "Commercial (Evening)",
            "description": "Commercial with evening peak",
            "typical_use": "Restaurants, evening entertainment"
        },
        "G3": {
            "name": "Commercial (Continuous)",
            "description": "Commercial with continuous operation",
            "typical_use": "24h operations, hotels"
        },
        "G4": {
            "name": "Commercial (Shop/Retail)",
            "description": "Commercial shop and retail operations",
            "typical_use": "Retail stores, shopping centers"
        },
        "G5": {
            "name": "Commercial (Bakery)",
            "description": "Commercial bakery profile with early morning peak",
            "typical_use": "Bakeries, early-start commercial"
        },
        "G6": {
            "name": "Commercial (Weekend)",
            "description": "Commercial with weekend operation emphasis",
            "typical_use": "Weekend-focused businesses"
        },
        "L0": {
            "name": "Agricultural General",
            "description": "General agricultural load profile",
            "typical_use": "General farms"
        },
        "L1": {
            "name": "Agricultural (Dairy)",
            "description": "Agricultural with dairy farming emphasis",
            "typical_use": "Dairy farms"
        },
        "L2": {
            "name": "Agricultural (Other)",
            "description": "Other agricultural operations",
            "typical_use": "Non-dairy farms, livestock"
        }
    }


def get_pv_profile_descriptions():
    """
    Get PV (Photovoltaic) profile descriptions based on power class.
    
    Returns:
        dict: PV profile classes with descriptions
    """
    return {
        "PV1": {
            "power_range": "1-3 kWp",
            "description": "Small residential PV systems",
            "typical_use": "Single-family homes"
        },
        "PV2": {
            "power_range": "3-5 kWp",
            "description": "Medium residential PV systems",
            "typical_use": "Larger homes"
        },
        "PV3": {
            "power_range": "5-10 kWp",
            "description": "Large residential/small commercial PV",
            "typical_use": "Large homes, small businesses"
        },
        "PV4": {
            "power_range": "10-20 kWp",
            "description": "Commercial PV systems",
            "typical_use": "Commercial rooftops"
        },
        "PV5": {
            "power_range": "20-50 kWp",
            "description": "Medium commercial/industrial PV",
            "typical_use": "Industrial buildings"
        },
        "PV6": {
            "power_range": "50-100 kWp",
            "description": "Large commercial PV",
            "typical_use": "Large commercial/industrial"
        },
        "PV7": {
            "power_range": "100-500 kWp",
            "description": "Large industrial/ground-mounted PV",
            "typical_use": "Industrial parks, ground-mounted"
        },
        "PV8": {
            "power_range": ">500 kWp",
            "description": "Utility-scale PV",
            "typical_use": "Solar farms, utility installations"
        }
    }


def print_all_profiles():
    """
    Print all extracted profile classes in a formatted way.
    """
    print("=" * 80)
    print("SimBench Profile Classes Extraction")
    print("=" * 80)
    
    # Load network once
    print("\nLoading SimBench network...")
    net = sb.get_simbench_net("1-complete_data-mixed-all-0-sw")
    
    # Extract load profiles
    print("\n" + "-" * 40)
    print("LOAD PROFILE CLASSES")
    print("-" * 40)
    
    load_profiles = get_all_load_profile_classes(net)
    bdew_descriptions = get_bdew_profile_descriptions()
    
    print("\n>>> BDEW Standard Load Profiles:")
    for base_class in sorted(load_profiles["bdew_load_profiles"].keys()):
        variants = load_profiles["bdew_load_profiles"][base_class]
        desc = bdew_descriptions.get(base_class, {})
        name = desc.get("name", "Unknown")
        description = desc.get("description", "")
        print(f"\n  {base_class}: {name}")
        print(f"      Description: {description}")
        print(f"      Variants ({len(variants)}): {', '.join(sorted(variants)[:5])}" + 
              ("..." if len(variants) > 5 else ""))
    
    print("\n>>> Other Load Profile Categories:")
    for category, profiles in load_profiles["other_load_profiles"].items():
        unique_profiles = sorted(set(profiles))
        print(f"\n  {category}: {len(unique_profiles)} profiles")
        print(f"      Examples: {', '.join(unique_profiles[:5])}" + 
              ("..." if len(unique_profiles) > 5 else ""))
    
    # Extract RES profiles
    print("\n" + "-" * 40)
    print("RES (RENEWABLE) PROFILE CLASSES")
    print("-" * 40)
    
    res_profiles = get_all_res_profile_classes(net)
    pv_descriptions = get_pv_profile_descriptions()
    
    print("\n>>> Photovoltaic (PV) Profiles:")
    for pv in sorted(res_profiles["pv_profiles"]):
        desc = pv_descriptions.get(pv, {})
        power_range = desc.get("power_range", "Unknown")
        description = desc.get("description", "")
        print(f"  {pv}: {power_range} - {description}")
    
    print("\n>>> Wind Power (WP) Profiles:")
    print(f"  {', '.join(res_profiles['wind_profiles'])}")
    
    print("\n>>> Biomass (BM) Profiles:")
    print(f"  {', '.join(res_profiles['biomass_profiles'])}")
    
    print("\n>>> Hydro Profiles:")
    print(f"  {', '.join(res_profiles['hydro_profiles'])}")
    
    print("\n>>> Aggregated RES Profiles:")
    print(f"  {', '.join(res_profiles['aggregated_res_profiles'])}")
    
    print("\n" + "=" * 80)
    print("Summary:")
    print(f"  - BDEW Load Profile Classes: {len(load_profiles['bdew_load_profiles'])}")
    print(f"  - PV Profiles: {len(res_profiles['pv_profiles'])}")
    print(f"  - Wind Profiles: {len(res_profiles['wind_profiles'])}")
    print(f"  - Biomass Profiles: {len(res_profiles['biomass_profiles'])}")
    print(f"  - Hydro Profiles: {len(res_profiles['hydro_profiles'])}")
    print("=" * 80)


def get_profiles_dataframe():
    """
    Get all profile information as pandas DataFrames.
    
    Returns:
        tuple: (load_profiles_df, res_profiles_df)
    """
    net = sb.get_simbench_net("1-complete_data-mixed-all-0-sw")
    
    # BDEW Load Profiles DataFrame
    bdew_desc = get_bdew_profile_descriptions()
    load_data = []
    for code, info in bdew_desc.items():
        load_data.append({
            "Profile Code": code,
            "Name": info["name"],
            "Description": info["description"],
            "Typical Use": info["typical_use"]
        })
    load_df = pd.DataFrame(load_data)
    
    # PV/RES Profiles DataFrame  
    pv_desc = get_pv_profile_descriptions()
    res_data = []
    for code, info in pv_desc.items():
        res_data.append({
            "Profile Code": code,
            "Power Range": info["power_range"],
            "Description": info["description"],
            "Typical Use": info["typical_use"]
        })
    res_df = pd.DataFrame(res_data)
    
    return load_df, res_df


if __name__ == "__main__":
    print_all_profiles()
    
    # Optional: Get as DataFrames
    # load_df, res_df = get_profiles_dataframe()
    # print(load_df)
    # print(res_df)
