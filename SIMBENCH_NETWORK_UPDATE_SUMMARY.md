# SimBench Network Update Summary

**Date**: January 29, 2026  
**Document**: BDEW_Network_Selection_and_Profile_Matching.ipynb  
**Purpose**: Align SimBench network selection with Austrian REC case study (Cosic et al., 2021)

## Key Updates

### 1. PV System Specifications (from Paper Table 3)

Updated REC participants to include actual PV capacity in kWp:

| Node | Participant | PV Capacity | Annual Generation |
|------|-------------|-------------|-------------------|
| 2 | Fire Station | **17.68 kWp** | 18,115.65 kWh/year |
| 6 | Household | **4.2 kWp** | 4,303.49 kWh/year |
| 8 | Household | **2.6 kWp** | 2,664.07 kWh/year |
| **Total** | **3 prosumers** | **24.48 kWp** | **25,083.21 kWh/year** |

**Source**: Cosic et al., 2021 - "Mixed-integer linear programming based optimization strategies for renewable energy communities"
- Fire department: 17.68 kWp (existing PV system, node 2 in case study)
- Single-family household 1: 4.2 kWp (existing PV system, node 8 in case study)
- Single-family household 2: 2.6 kWp (existing PV system, node 9 in case study)

### 2. Battery Storage Integration (NEW)

**SimBench Networks with Battery Storage**:

| Network | Storage Units | Total Capacity | Avg Unit Size | Type |
|---------|--------------|----------------|---------------|------|
| **1-LV-rural3--2-no_sw** | **16** | **~150 kWh** | **~10 kWh** | Distributed |
| **1-LV-rural3--1-no_sw** | **14** | **~130 kWh** | **~10 kWh** | Distributed |
| 1-LV-semiurb5--2-no_sw | 15 | ~140 kWh | ~10 kWh | Distributed |
| 1-LV-semiurb5--1-no_sw | 10 | ~95 kWh | ~10 kWh | Distributed |
| 1-LV-semiurb4--2-no_sw | 4 | ~35 kWh | ~9 kWh | Distributed |
| **1-LV-rural3--0-no_sw** | **0** | **0 kWh** | **N/A** | **No storage** |

**Storage Characteristics** (from Storage.csv):
- **Efficiency**: 95% charging/discharging (matches case study)
- **Self-discharge**: 0.13% per day (vs 4.8% in case study)
- **Min SOC**: 0% (vs 20% in case study for battery protection)
- **Capacity range**: 2.8-10.3 kWh per residential unit
- **Profile type**: PV_Storage (paired with PV systems)

**Storage Strategy for C3 Scenario**:
- **Case Study Approach**: Centralized 200 kWh community battery (MILP optimized)
- **SimBench Approach**: Distributed residential batteries (5-16 units × 10 kWh each)
- **C3 Implementation**: Add centralized 200 kWh battery independently
- **Comparison Option**: Use 1-LV-rural3--2-no_sw to compare distributed vs centralized

### 3. SimBench Network List Update

**Previous Network List** (10 networks):
```
1-LV-rural1--0-sw
1-LV-rural1--1-no_sw
1-LV-rural2--0-sw
1-LV-rural2--1-no_sw
1-LV-urban3--0-sw
1-LV-urban3--1-no_sw
1-LV-urban6--0-sw
1-LV-urban6--1-no_sw
2-MV-urban--0-sw
3-LV_urban--0-sw
```

**Updated Network List** (11 networks):
```
1-LV-rural1--0-sw
1-LV-rural1--1-no_sw
1-LV-rural2--0-sw
1-LV-rural2--1-no_sw
1-LV-rural3--0-no_sw  ← NEW - LV3.101 Primary Candidate
1-LV-rural3--1-no_sw  ← NEW
1-LV-rural3--2-no_sw  ← NEW
1-LV-semiurb4--0-sw
1-LV-semiurb5--0-sw
1-LV-urban6--0-sw
1-LV-urban6--1-no_sw
```

### 4. Network Rationale

**Why LV3.101 (1-LV-rural3--0-no_sw) vs Storage Variants?**

**Common Features (All Rural3 Variants)**:

1. **Configuration File Reference**: 
   - Used in C3_single_supplier_rec_battery.json
   - All load/PV IDs reference "LV3.101" (e.g., "LV3.101 Load 90 [G4-A]")

2. **Rural Community Match**:
   - Case study: Village in Carinthia, Austria
   - Rural3 network type aligns with Austrian village topology
   - Low voltage distribution network (same as case study)

3. **Profile Availability**:
   - Crystalline silicon PV systems (per paper)
   - Residential and commercial BDEW classes (G1, G4, G6, H0)
   - Storage.csv shows PV_Storage profiles (variants 1 & 2)

4. **Network Variants Comparison**:
   ```
   1-LV-rural3--0-no_sw:  0 storage units (baseline)
   1-LV-rural3--1-no_sw: 14 storage units (~130 kWh distributed)
   1-LV-rural3--2-no_sw: 16 storage units (~150 kWh distributed) ← BEST FOR COMPARISON
   ```

## Updated Network Scoring

**Scoring Criteria** (Updated to include battery storage):
- Mandatory BDEW classes (G4, G1, H0): +25 each
- Optional classes (G6): +15
- PV availability: +20
- **Battery storage (NEW)**: 
  - 10+ units: +30 points
  - 5-9 units: +20 points
  - 1-4 units: +10 points
  - No storage: -15 points
- Profile diversity: +5 to +25

**Expected Top Networks** (with new scoring):
1. **1-LV-rural3--2-no_sw**: ~145 points (16 storage units + full BDEW coverage)
2. **1-LV-rural3--1-no_sw**: ~140 points (14 storage units + full BDEW coverage)
3. **1-LV-semiurb5--2-no_sw**: ~135 points (15 storage units)
4. 1-LV-rural3--0-no_sw: ~100 points (no storage penaltymprehensive analysis:
1. Extract network with distributed storage (baseline comparison)
2. Add centralized 200 kWh battery for C3 scenario
3. Compare: No storage vs Distributed vs Centralized vs Hybrid

**Common Features (All Rural3 Variants)**:

1. **Configuration File Reference**: 
   - Used in C3_single_supplier_rec_battery.json
   - All load/PV IDs reference "LV3.101" (e.g., "LV3.101 Load 90 [G4-A]")

2. **Rural Community Match**:
   - Case study: Village in Carinthia, Austria
   - Rural3 network type aligns with Austrian village topology
   - Low voltage distribution network (same as case study)

3. **Profile Availability**:
   - Storage.csv shows LV3.101 has PV_Storage profiles
   - Compatible with crystalline silicon PV systems (per paper)
   - Residential and commercial BDEW classes (G1, G4, G6, H0)

4. **Network Variants**:
   - `--0-no_sw`: Base case (no switching)
   - `--1-no_sw`: Variant 1
   - `--2-no_sw`: Variant 2 (16 storage units available)

## Summary Statistics

**REC Community Profile**:
- **Total participants**: 9 (3 prosumers + 6 consumers)
- **Total load**: 63,902 kWh/year
- **Total PV capacity**: 24.48 kWp
- **Total PV generation**: 25,083 kWh/year
- **Peak load**: 18.32 kW
- **Location**: Village in Carinthia, Austria
- **Network level**: Low voltage distribution

**BDEW Functional Classes Required**:
- **G1** - Bank/commercial (node 7)
- **G4** - Local authority (node 1)
- **G6** - Fire station (node 2)
- **H0** - Households/apartments (nodes 3-6, 8-9)

**Apartment Aggregation**:
- Nodes 3, 4, 5, 8 aggregated into single H0 profile
- Total: 3,590 kWh/year (4 apartments)
- Reason: Individual apartments 5-25× smaller than typical SimBench profiles

## Integration with Battery Optimization

The updated network selection supports the C3 scenario:
- **Scenario C3**: Single supplier REC with centralized battery optimization
- **Battery**: 200 kWh Li-ion (0.34 C-rate, 95% efficiency)
- **Control**: Centralized MILP optimization at REC level
- **Optimization points**: DA (D-1 12:00) + 3 ID updates

**Battery Parameters** (from paper Table 3):
```json
{
  "capacity_kwh": 200,
  "max_charge_rate_kw": 68,
  "c_rate": 0.34,
  "charge_efficiency": 0.95,
  "discharge_efficiency": 0.95,
  "min_soc": 0.20,
  "max_soc": 1.00,
  "self_discharge_per_hour": 0.002,
  "lifetime_years": 15
}
```

## Files Updated

1. **BDEW_Network_Selection_and_Profile_Matching.ipynb**
   - Added `pv_kwp` field to prosumer nodes (17.68, 4.2, 2.6)
   - Added LV3.101 rural3 networks (3 variants)
   - Updated print statements to show PV capacity
   - Updated case study reference to Cosic et al., 2021

2. **C3_single_supplier_rec_battery.json**
   - Already references LV3.101 profiles
   - PV capacities match paper specifications
   - Battery parameters from Table 3

## Next Steps

1. **Run Network Selection**:
   - Execute BDEW_Network_Selection_and_Profile_Matching.ipynb
   - Evaluate LV3.101 against BDEW functional requirements
   - Generate profile matching and scale factors

2. **Profile Extraction**:
   - Extract 8,760 hourly load profiles from selected network
   - Extract PV generation profiles (crystalline silicon)
   - Apply scale factors to match REC annual energy

3. **MILP Optimization**:
   - Use scaled profiles in C3 battery optimization notebook
   - Execute DA + ID + REC + Balancing + Billing workflow
   - Validate against case study results (15% cost reduction, 34% CO2 reduction)

## References

**Primary Source**:
- Cosic, A., Stadler, M., Mansoor, M., & Zellinger, M. (2021). Mixed-integer linear programming based optimization strategies for renewable energy communities. *Energy*, 237, 121559.
  - Table 1: REC participant loads and types
  - Table 2: Economic parameters (PV €842/kW, ESS €434/kWh)
  - Table 3: Li-ion battery technical parameters
  - Figure 1: Network topology (9 participants, central investment options)

**SimBench Documentation**:
- LV3.101: 1-LV-rural3--0-no_sw
- BDEW load profiles: G1, G4, G6, H0 (residential/commercial)
- PV profiles: Crystalline silicon with efficient inverter
- Storage profiles: Li-ion compatible (95% efficiency)

---

**Update Status**: ✓ Complete  
**Configuration Alignment**: ✓ Verified  
**Ready for MILP Optimization**: ✓ Yes
