# ESS Parameters Mapping: Case Study to SimBench Storage Columns

## Column Mapping Table

| Case Study Parameter | Value | SimBench Column | SimBench Format | Notes |
|---------------------|-------|-----------------|-----------------|-------|
| **Charging Efficiency of ESS [%]** | 95 | `etaStore` | 0.95 | Stored as decimal (95% → 0.95) |
| **Discharging Efficiency of ESS [%]** | 95 | `etaStore` | 0.95 | Same column, round-trip efficiency |
| **Maximum Charge Rate [% per hour]** | 34 | `pMax` | Calculated from capacity | pMax = 0.34 × eStore (kW) |
| **Maximum Discharge Rate [% per hour]** | 34 | `pMin` | Calculated from capacity | pMin = -0.34 × eStore (kW) |
| **Minimum SOC of ESS [%]** | 20 | Not in SimBench | - | Must be implemented in optimization constraints |
| **Maximum SOC of ESS [%]** | 100 | Not in SimBench | - | Must be implemented in optimization constraints |
| **Self-Discharge Rate of ESS [% per hour]** | 0.2 | `sdStore` | 0.002 | Stored as decimal per hour (0.2% → 0.002) |

---

## SimBench Storage Column Definitions

### Columns in Storage.csv:

1. **`id`** - Storage unit identifier (e.g., "LV2.101 Storage 1")
2. **`node`** - Bus/node where storage is connected
3. **`type`** - Storage type (e.g., "PV_Storage", "Wind_Storage")
4. **`profile`** - Load profile identifier
5. **`pStor`** - Initial active power [MW/kW] (typically 0)
6. **`qStor`** - Initial reactive power [Mvar/kvar] (typically 0)
7. **`chargeLevel`** - Initial state of charge [MWh/kWh] (typically 0)
8. **`sR`** - Rated apparent power [MVA/kVA]
9. **`eStore`** - **Energy capacity [MWh/kWh]** ⚠️ Key parameter
10. **`etaStore`** - **Efficiency [-]** → Maps to charging/discharging efficiency
11. **`sdStore`** - **Self-discharge rate [per hour]** → Maps to self-discharge
12. **`pMin`** - **Minimum active power [MW/kW]** → Maps to max discharge rate (negative)
13. **`pMax`** - **Maximum active power [MW/kW]** → Maps to max charge rate (positive)
14. **`qMin`** - Minimum reactive power [Mvar/kvar]
15. **`qMax`** - Maximum reactive power [Mvar/kvar]
16. **`subnet`** - Subnet identifier
17. **`voltLvl`** - Voltage level

---

## Current SimBench Default Values

From the Storage.csv file, typical SimBench storage uses:
- **`etaStore`** = 0.95 (95% efficiency) ✓ Matches case study
- **`sdStore`** = 0.13 (13% per hour) ❌ Much higher than case study (0.2%)

---

## Detailed Parameter Mapping

### 1. Charging/Discharging Efficiency

**Case Study:** 95% each (charging and discharging)  
**SimBench Mapping:**
```
etaStore = 0.95
```

**Note:** SimBench uses a single efficiency value. For separate charging/discharging:
- Round-trip efficiency = η_charge × η_discharge = 0.95 × 0.95 = 0.9025
- If using single value: etaStore = 0.95 (assumes same for both directions)

### 2. Maximum Charge Rate (34% per hour)

**SimBench Mapping:**
```
pMax = 0.34 × eStore
```

**Example:**
- If `eStore = 100 kWh`, then `pMax = 34 kW`
- This means the battery can charge at max 34 kW (34% of 100 kWh capacity per hour)

### 3. Maximum Discharge Rate (34% per hour)

**SimBench Mapping:**
```
pMin = -0.34 × eStore
```

**Example:**
- If `eStore = 100 kWh`, then `pMin = -34 kW`
- Negative value indicates power flowing out (discharge)

### 4. Self-Discharge Rate (0.2% per hour)

**Case Study:** 0.2% per hour  
**SimBench Default:** 0.13 (13% per hour - much higher!)

**SimBench Mapping:**
```
sdStore = 0.002
```

**⚠️ Important:** The default SimBench value (0.13) is 65× higher than the case study value. This must be changed to 0.002 for realistic Li-ion battery modeling.

### 5. SOC Constraints (20-100%)

**SimBench:** No direct columns for SOC limits

**Implementation Required:**
These constraints must be implemented in the optimization model:

```python
# Minimum SOC constraint
SOC(t) >= 0.20 × eStore  # 20% of capacity

# Maximum SOC constraint  
SOC(t) <= 1.00 × eStore  # 100% of capacity
```

**Alternative:** Use `chargeLevel` bounds in optimization:
```
chargeLevel_min = 0.20 × eStore
chargeLevel_max = 1.00 × eStore
```

---

## Example Storage Entry for Case Study

For a 100 kWh shared ESS in the Austrian energy community:

```csv
id;node;type;profile;pStor;qStor;chargeLevel;sR;eStore;etaStore;sdStore;pMin;pMax;qMin;qMax;subnet;voltLvl
LV2.101 Storage 1;LV2.101 Bus 1;Community_ESS;shared_ess;0;0;20;100;100;0.95;0.002;-34;34;0;0;LV2;5
```

### Column-by-Column Explanation:
- `id`: "LV2.101 Storage 1" - Storage identifier
- `node`: "LV2.101 Bus 1" - Connected to main bus
- `type`: "Community_ESS" - Shared community storage
- `profile`: "shared_ess" - Custom profile
- `pStor`: 0 - Initial power (start idle)
- `qStor`: 0 - No reactive power
- `chargeLevel`: 20 kWh - Initial charge at 20% (minimum SOC)
- `sR`: 100 kVA - Rated power (matches capacity for 1C rate base)
- `eStore`: **100 kWh** - Energy capacity
- `etaStore`: **0.95** - 95% efficiency
- `sdStore`: **0.002** - 0.2% per hour self-discharge
- `pMin`: **-34 kW** - Max discharge (34% of 100 kWh)
- `pMax`: **34 kW** - Max charge (34% of 100 kWh)
- `qMin`: 0 - No reactive power limits
- `qMax`: 0 - No reactive power limits
- `subnet`: "LV2" - Low voltage network
- `voltLvl`: 5 - Voltage level code

---

## Implementation Checklist

When implementing the case study ESS parameters in SimBench:

- [ ] Set `etaStore = 0.95` (95% efficiency)
- [ ] Set `sdStore = 0.002` (0.2% per hour, NOT 0.13!)
- [ ] Calculate `pMax = 0.34 × eStore` (34% charge rate)
- [ ] Calculate `pMin = -0.34 × eStore` (34% discharge rate)
- [ ] Add SOC constraints in optimization: `0.20 × eStore ≤ SOC(t) ≤ 1.00 × eStore`
- [ ] Set `chargeLevel = 0.20 × eStore` as initial state (start at minimum SOC)
- [ ] Verify `sR ≥ max(|pMin|, |pMax|)` for power rating

---

## Key Differences: SimBench Defaults vs Case Study

| Parameter | SimBench Default | Case Study | Action Required |
|-----------|------------------|------------|-----------------|
| Efficiency | 0.95 (95%) | 0.95 (95%) | ✓ No change needed |
| Self-discharge | 0.13 (13%/h) | 0.002 (0.2%/h) | ❌ **Must change!** |
| Max Charge Rate | Varies | 34%/h | ✓ Calculate from capacity |
| Max Discharge Rate | Varies | 34%/h | ✓ Calculate from capacity |
| Min SOC | Not defined | 20% | ⚠️ Add constraint |
| Max SOC | Not defined | 100% | ⚠️ Add constraint |

---

## Notes for Data Generation

When using the `data.py` script to generate storage profiles:

1. **Update Storage Parameters:**
   ```python
   # In data.py or configuration
   storage_params = {
       'etaStore': 0.95,      # 95% efficiency
       'sdStore': 0.002,      # 0.2% per hour self-discharge
       'pMax': 0.34,          # 34% charge rate coefficient
       'pMin': -0.34,         # 34% discharge rate coefficient
       'soc_min': 0.20,       # 20% minimum SOC
       'soc_max': 1.00        # 100% maximum SOC
   }
   ```

2. **SOC Evolution Equation:**
   ```python
   SOC(t+1) = SOC(t) * (1 - sdStore * dt) + (eta * P_charge(t) - P_discharge(t) / eta) * dt
   ```
   Where:
   - `dt` = time step (typically 1 hour or 0.25 hour for 15-min resolution)
   - `eta` = etaStore = 0.95
   - `sdStore` = 0.002 per hour

3. **Power Constraints:**
   ```python
   -0.34 * eStore <= P_storage(t) <= 0.34 * eStore
   ```

4. **SOC Constraints:**
   ```python
   0.20 * eStore <= SOC(t) <= 1.00 * eStore
   ```
