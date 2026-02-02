# Shared Energy Storage System (ESS) Parameters
## Austrian Energy Community Case Study

**Source:** Mixed-integer linear programming based optimization strategies for renewable energy communities  
**Battery Technology:** Lithium-ion based ESS

---

## 1. Efficiency Parameters

| Parameter | Value | Unit | Description |
|-----------|-------|------|-------------|
| Charging Efficiency | 95 | % | Energy efficiency during charging |
| Discharging Efficiency | 95 | % | Energy efficiency during discharging |
| Round-trip Efficiency | 90.25 | % | Combined efficiency (0.95 × 0.95) |
| Self-discharge Rate | 0.2 | % per hour | Energy losses when idle |

---

## 2. Power Constraints

| Parameter | Value | Unit | Description |
|-----------|-------|------|-------------|
| Maximum Charge Rate | 34 | % per hour | Max charging power relative to capacity |
| Maximum Discharge Rate | 34 | % per hour | Max discharging power relative to capacity |

**Note:** For a battery with capacity C (kWh), the maximum power is:
- Max Charge Power = 0.34 × C (kW)
- Max Discharge Power = 0.34 × C (kW)

---

## 3. State of Charge (SOC) Constraints

| Parameter | Value | Unit | Description |
|-----------|-------|------|-------------|
| Minimum SOC | 20 | % | Lower operating limit |
| Maximum SOC | 100 | % | Upper operating limit (full capacity) |
| Operating Range | 20-100 | % | Operational window |

**Rationale:** Operating in the 20-100% SOC range minimizes battery degradation and prolongs the usage of stored renewable energy. According to research, this strategy can increase the battery lifetime (number of charge cycles) by **50%**.

---

## 4. Lifetime and Degradation

| Parameter | Value | Unit | Description |
|-----------|-------|------|-------------|
| Base Warranty | 10 | years | Manufacturer warranty at 100% DoD |
| Extended Lifetime | 15 | years | Expected with 20-100% SOC operation |
| Lifetime Extension | 50 | % | Increase in charge cycles |

---

## 5. Economic Parameters

| Parameter | Value | Unit | Description |
|-----------|-------|------|-------------|
| Interest Rate | 2 | % | For annuity rate calculation |

---

## 6. System Integration

### Community Context:
- **Members:** 9 community participants
- **Location:** Municipality in Austria
- **Sharing Model:** Shared ESS across entire community
- **Renewable Source:** Distributed photovoltaic (PV) systems

### Operational Strategy:
- **Optimization Method:** Mixed-Integer Linear Programming (MILP)
- **Objective:** Minimize total energy costs and CO2 emissions
- **Energy Sharing:** Enable surplus renewable energy sharing among members
- **Scheduling:** Optimal hourly charging/discharging based on:
  - PV generation forecasts
  - Load demands
  - Electricity tariffs
  - Grid feed-in prices

### Expected Benefits (from case study):
- **Cost Reduction:** 15% total energy cost reduction
- **Emission Reduction:** 34% total CO2 emissions reduction
- **Individual Benefits:** Each community participant benefits both economically and ecologically

---

## 7. Technical Constraints for Optimization

### Charging/Discharging Limits:
```
P_charge(t) ≤ 0.34 × E_capacity
P_discharge(t) ≤ 0.34 × E_capacity
```

### SOC Evolution:
```
SOC(t+1) = SOC(t) + (η_charge × P_charge(t) - P_discharge(t)/η_discharge - α × E_capacity) × Δt
```
Where:
- η_charge = 0.95 (charging efficiency)
- η_discharge = 0.95 (discharging efficiency)
- α = 0.002 per hour (self-discharge rate)
- Δt = time step (typically 1 hour or 15 minutes)

### SOC Bounds:
```
0.20 × E_capacity ≤ SOC(t) ≤ 1.00 × E_capacity
```

---

## 8. References

1. **[39]** Manufacturer specifications for Li-ion battery warranty and depth of discharge
2. **[40]** Study on SOC range impact on battery lifetime and charge cycles  
3. **[41]** Technical parameters for typical Li-ion ESS

---

## Notes for Implementation:

1. **Capacity Selection:** The actual energy capacity (kWh) should be determined through optimization based on:
   - Community total load profile
   - PV generation capacity
   - Economic feasibility (CAPEX vs. energy cost savings)

2. **Power Rating:** The power rating (kW) is constrained by the 34% per hour charge/discharge rate:
   - For example, a 100 kWh battery can charge/discharge at max 34 kW

3. **Operating Strategy:** 
   - Charge during high PV generation and low loads
   - Discharge during low/no PV generation and high loads
   - Participate in energy arbitrage if time-of-use tariffs apply

4. **Degradation Model:** The 15-year lifetime assumes:
   - Operation within 20-100% SOC range
   - Proper thermal management
   - Typical residential/community usage patterns
