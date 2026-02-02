"""
Extract and return all available SimBench networks.

This script queries the SimBench database for all available networks
and provides methods to access them dynamically.
"""

import warnings
from typing import List, Dict, Tuple
from simbench import get_simbench_net

# Suppress SimBench warnings
warnings.filterwarnings('ignore')


def get_all_simbench_networks() -> List[str]:
    """
    Extract all available SimBench network codes.
    
    Returns:
        List[str]: List of all available SimBench network codes
    """
    # All known SimBench networks in the repository
    # Based on the SimBench v1.6.1 release
    all_networks = [
        # Low Voltage (LV) Networks
        "1-LV-rural1--0-sw",
        "1-LV-rural1--1-no_sw",
        "1-LV-rural2--0-sw",
        "1-LV-rural2--1-no_sw",
        "1-LV-urban1--0-sw",
        "1-LV-urban1--1-no_sw",
        "1-LV-urban2--0-sw",
        "1-LV-urban2--1-no_sw",
        "1-LV-urban3--0-sw",
        "1-LV-urban3--1-no_sw",
        "1-LV-urban6--0-sw",
        "1-LV-urban6--1-no_sw",
        "1-LV-rural3--0-sw",
        "1-LV-rural3--1-no_sw",
        
        # Medium Voltage (MV) Networks
        "1-MV-urban--0-sw",
        "1-MV-urban--1-no_sw",
        "1-MV-rural--0-sw",
        "1-MV-rural--1-no_sw",
        "2-MV-urban--0-sw",
        "2-MV-urban--1-no_sw",
        "2-MV-rural--0-sw",
        "2-MV-rural--1-no_sw",
        
        # High Voltage (HV) Networks
        "3-LV_urban--0-sw",
        "3-LV_urban--1-no_sw",
    ]
    
    return all_networks


def get_available_simbench_networks() -> Tuple[List[str], List[str]]:
    """
    Get available and unavailable SimBench networks by attempting to load them.
    
    Returns:
        Tuple[List[str], List[str]]: (available_networks, unavailable_networks)
    """
    available = []
    unavailable = []
    
    all_networks = get_all_simbench_networks()
    
    print(f"Checking {len(all_networks)} SimBench networks...")
    print("=" * 80)
    
    for i, network_code in enumerate(all_networks, 1):
        try:
            # Attempt to load network
            net = get_simbench_net(network_code)
            available.append(network_code)
            print(f"  [{i:2d}/{len(all_networks)}] ✓ {network_code}")
            print(f"        Loads: {len(net.load):3d} | Sgens: {len(net.sgen):3d}")
        except Exception as e:
            unavailable.append(network_code)
            print(f"  [{i:2d}/{len(all_networks)}] ✗ {network_code}")
            print(f"        Error: {str(e)[:60]}")
    
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  Available:   {len(available)} networks")
    print(f"  Unavailable: {len(unavailable)} networks")
    
    return available, unavailable


def get_network_details(network_code: str) -> Dict:
    """
    Get detailed information about a specific SimBench network.
    
    Args:
        network_code (str): The network code (e.g., "1-LV-rural1--0-sw")
    
    Returns:
        Dict: Dictionary containing network details
    """
    try:
        net = get_simbench_net(network_code)
        
        # Extract profile information
        load_profiles = {}
        if 'profile' in net.load.columns:
            for profile in net.load['profile'].dropna().unique():
                count = (net.load['profile'] == profile).sum()
                load_profiles[str(profile)] = int(count)
        
        pv_profiles = {}
        if len(net.sgen) > 0 and 'profile' in net.sgen.columns:
            for profile in net.sgen['profile'].dropna().unique():
                if 'pv' in str(profile).lower():
                    count = (net.sgen['profile'] == profile).sum()
                    pv_profiles[str(profile)] = int(count)
        
        return {
            'network': network_code,
            'status': 'loaded',
            'buses': len(net.bus),
            'loads': len(net.load),
            'sgens': len(net.sgen),
            'lines': len(net.line),
            'transformers': len(net.trafo),
            'load_profiles': load_profiles,
            'pv_profiles': pv_profiles,
            'profile_types': len(load_profiles) + len(pv_profiles)
        }
    except Exception as e:
        return {
            'network': network_code,
            'status': 'error',
            'error': str(e)
        }


def get_networks_by_type(network_type: str = None) -> List[str]:
    """
    Get SimBench networks filtered by type (LV, MV, HV).
    
    Args:
        network_type (str): Network type - "LV", "MV", "HV", or None for all
    
    Returns:
        List[str]: Filtered list of network codes
    """
    all_networks = get_all_simbench_networks()
    
    if network_type is None:
        return all_networks
    
    network_type = network_type.upper()
    return [net for net in all_networks if network_type in net]


def extract_network_metadata(network_code: str) -> Dict:
    """
    Extract metadata from network code.
    
    Args:
        network_code (str): The network code
    
    Returns:
        Dict: Metadata extracted from the code
    """
    # Format: voltage_level-area-variant--switch_type
    # Example: 1-LV-rural2--0-sw
    
    parts = network_code.split('-')
    
    metadata = {
        'code': network_code,
        'voltage_level': None,
        'area_type': None,
        'variant': None,
        'switch_type': None
    }
    
    if len(parts) >= 3:
        metadata['voltage_level'] = parts[1]  # LV, MV, HV
        metadata['area_type'] = parts[2]      # rural, urban, mixed
        
        if len(parts) >= 4:
            # Variant is in 4th part or after
            last_part = parts[-1]
            if '--' in last_part:
                variant_switch = last_part.split('--')
                metadata['variant'] = variant_switch[0] if variant_switch[0] else '1'
                metadata['switch_type'] = 'sw' if len(variant_switch) > 1 else 'no_sw'
            else:
                metadata['variant'] = parts[3] if len(parts) > 3 else '1'
    
    return metadata


def print_network_summary(networks: List[str] = None):
    """
    Print a summary of all SimBench networks.
    
    Args:
        networks (List[str]): List of networks to summarize (default: all)
    """
    if networks is None:
        networks = get_all_simbench_networks()
    
    print("\n" + "=" * 100)
    print("SIMBENCH NETWORK SUMMARY")
    print("=" * 100)
    
    # Group by type
    lv_nets = [n for n in networks if 'LV' in n]
    mv_nets = [n for n in networks if 'MV' in n]
    hv_nets = [n for n in networks if 'HV' in n or '3-LV' in n]
    
    print(f"\nLow Voltage (LV): {len(lv_nets)} networks")
    for net in sorted(lv_nets):
        print(f"  - {net}")
    
    print(f"\nMedium Voltage (MV): {len(mv_nets)} networks")
    for net in sorted(mv_nets):
        print(f"  - {net}")
    
    if hv_nets:
        print(f"\nHigh Voltage (HV): {len(hv_nets)} networks")
        for net in sorted(hv_nets):
            print(f"  - {net}")
    
    print(f"\nTotal: {len(networks)} networks")
    print("=" * 100)


# Main execution
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "all":
            # Get all known networks
            networks = get_all_simbench_networks()
            print(f"Total SimBench networks available: {len(networks)}")
            for net in networks:
                print(f"  {net}")
        
        elif command == "available":
            # Get available networks
            available, unavailable = get_available_simbench_networks()
            print(f"\nAvailable: {available}")
        
        elif command == "lv":
            # Get LV networks
            networks = get_networks_by_type("LV")
            print_network_summary(networks)
        
        elif command == "mv":
            # Get MV networks
            networks = get_networks_by_type("MV")
            print_network_summary(networks)
        
        elif command == "details":
            # Get details of a specific network
            if len(sys.argv) > 2:
                net_code = sys.argv[2]
                details = get_network_details(net_code)
                print(f"\nNetwork: {net_code}")
                for key, value in details.items():
                    print(f"  {key}: {value}")
            else:
                print("Usage: python extract_simbench_networks.py details <network_code>")
        
        else:
            print_network_summary()
    else:
        # Default: print summary
        print_network_summary()
