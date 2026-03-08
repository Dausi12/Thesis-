# SimBench Network Extraction Script

## Overview
The `extract_simbench_networks.py` script provides a complete interface to extract and manage all available SimBench networks dynamically.

## Features

### Main Functions

1. **`get_all_simbench_networks()`**
   - Returns all known SimBench network codes
   - Returns: `List[str]` of 24 networks
   - No network loading required

2. **`get_available_simbench_networks()`**
   - Tests each network by attempting to load it
   - Returns: Tuple of (available_networks, unavailable_networks)
   - Useful for detecting missing or corrupted networks

3. **`get_network_details(network_code: str)`**
   - Loads a specific network and extracts detailed information
   - Returns: Dictionary with buses, loads, sgens, lines, transformers, profiles
   - Example: `get_network_details("1-LV-rural2--0-sw")`

4. **`get_networks_by_type(network_type: str)`**
   - Filters networks by type: "LV" (Low Voltage), "MV" (Medium Voltage), "HV" (High Voltage)
   - Returns: Filtered list of network codes
   - Example: `get_networks_by_type("LV")` returns 14 LV networks

5. **`extract_network_metadata(network_code: str)`**
   - Parses network code to extract metadata
   - Returns: Dictionary with voltage_level, area_type, variant, switch_type
   - No network loading required

6. **`print_network_summary(networks: List[str])`**
   - Prints formatted summary of networks grouped by type
   - Optional parameter to filter specific networks

## Available Networks (24 Total)

### Low Voltage (LV): 14 networks
- 1-LV-rural1--0-sw, 1-LV-rural1--1-no_sw
- 1-LV-rural2--0-sw, 1-LV-rural2--1-no_sw
- 1-LV-rural3--0-sw, 1-LV-rural3--1-no_sw
- 1-LV-urban1--0-sw, 1-LV-urban1--1-no_sw
- 1-LV-urban2--0-sw, 1-LV-urban2--1-no_sw
- 1-LV-urban3--0-sw, 1-LV-urban3--1-no_sw
- 1-LV-urban6--0-sw, 1-LV-urban6--1-no_sw

### Medium Voltage (MV): 8 networks
- 1-MV-urban--0-sw, 1-MV-urban--1-no_sw
- 1-MV-rural--0-sw, 1-MV-rural--1-no_sw
- 2-MV-urban--0-sw, 2-MV-urban--1-no_sw
- 2-MV-rural--0-sw, 2-MV-rural--1-no_sw

### High Voltage (HV): 2 networks
- 3-LV_urban--0-sw, 3-LV_urban--1-no_sw

## Command Line Usage

```bash
# List all networks
python extract_simbench_networks.py all

# Check which networks are available
python extract_simbench_networks.py available

# Get summary of LV networks
python extract_simbench_networks.py lv

# Get summary of MV networks
python extract_simbench_networks.py mv

# Get detailed information for a specific network
python extract_simbench_networks.py details 1-LV-rural2--0-sw

# Default: print summary
python extract_simbench_networks.py
```

## Python Usage

```python
from extract_simbench_networks import (
    get_all_simbench_networks,
    get_network_details,
    get_networks_by_type
)

# Get all networks
all_nets = get_all_simbench_networks()
print(f"Total networks: {len(all_nets)}")

# Get details for a network
details = get_network_details("1-LV-rural2--0-sw")
print(f"Network has {details['loads']} loads and {details['sgens']} generators")
print(f"Load profiles: {details['load_profiles']}")

# Filter by type
lv_networks = get_networks_by_type("LV")
mv_networks = get_networks_by_type("MV")
```

## Network Code Format

Format: `{voltage_level}-{area_type}-{variant}--{switch_type}`

Examples:
- `1-LV-rural2--0-sw`: Low voltage, rural, variant 2, with switches
- `1-MV-urban--0-sw`: Medium voltage, urban, with switches
- `1-LV-rural1--1-no_sw`: Low voltage, rural, variant 1, without switches

## Example Output

### Get Network Details
```
Network: 1-LV-rural2--0-sw
  status: loaded
  buses: 97
  loads: 99
  sgens: 8
  lines: 95
  transformers: 1
  load_profiles: {'H0-A': 21, 'H0-B': 19, 'H0-C': 15, 'H0-G': 14, 'H0-L': 23, ...}
  pv_profiles: {'PV1': 1, 'PV3': 3, 'PV4': 2, 'PV7': 2}
  profile_types: 16
```

## Notes

- All network extraction is **dynamic** - no hardcoded data
- Networks are loaded on-demand from SimBench
- Supports error handling for missing or corrupted networks
- Profile information is extracted directly from network objects
- Compatible with SimBench v1.6.1 and pandapower v3.x
