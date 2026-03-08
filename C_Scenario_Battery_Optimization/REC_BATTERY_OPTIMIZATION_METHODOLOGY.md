# REC-Level Battery Optimization with Heterogeneous Distributed Storage

**Document Version:** 1.0  
**Date:** February 1, 2026  
**Scenario:** C3 - Single Supplier with REC and Distributed Battery Optimization  
**Network:** 1-LV-rural3--2-no_sw (9 nodes, 3 prosumers with PV+Storage)

---

## 1. Executive Summary

This document describes the Mixed-Integer Linear Programming (MILP) optimization model for coordinating **three heterogeneous battery storage systems** distributed across prosumer nodes in a Renewable Energy Community (REC). The optimizer operates at the REC level to minimize total community energy costs while respecting:

- Individual battery technical specifications (capacity, power, efficiency)
- Physical distribution of assets (batteries remain at prosumer locations)
- Energy balance constraints at both node and REC levels
- Grid interaction limits and market price signals

**Key Innovation:** Centralized REC-level optimization of heterogeneous distributed batteries (not a single centralized battery).

---

## 2. System Architecture

### 2.1 REC Composition

| Node | Participant Type | Load Profile | PV Profile | Storage Profile | Battery |
|------|-----------------|--------------|------------|-----------------|---------|
| 1    | Consumer        | G4           | -          | -               | No      |
| 2    | Prosumer        | G6           | PV4        | Storage_PV4_H0-G| **Yes** |
| 3    | Consumer        | H0-L         | -          | -               | No      |
| 4    | Consumer        | H0-L         | -          | -               | No      |
| 5    | Consumer        | H0-G         | -          | -               | No      |
| 6    | Prosumer        | H0-L         | PV3        | Storage_PV3_H0-L| **Yes** |
| 7    | Consumer        | G1           | -          | -               | No      |
| 8    | Prosumer        | H0-L         | PV1        | Storage_PV1_H0-L| **Yes** |
| 9    | Consumer        | H0-L         | -          | -               | No      |

**Total REC Capacity:**
- **Consumers:** 6 nodes (42,832 kWh/year)
- **Prosumers:** 3 nodes (21,069 kWh/year load, 25,083 kWh/year PV)
- **Net Annual Balance:** ~3,900 kWh surplus (REC is net exporter)

---

## 3. Heterogeneous Battery Specifications

### 3.1 Node 2: Fire Fighting Station (Commercial)

**Rationale:** Large commercial PV system (17.68 kWp) requires substantial storage for load shifting and grid arbitrage.

| Parameter | Value | Unit | Notes |
|-----------|-------|------|-------|
| **Capacity** | 40 | kWh | 2.3h at peak PV output |
| **Max Charge Power** | 20 | kW | 1.13× peak PV (17.68 kWp) |
| **Max Discharge Power** | 20 | kW | Can supply full load + export |
| **Charge Efficiency** | 95 | % | Commercial-grade Li-ion |
| **Discharge Efficiency** | 95 | % | Round-trip: 90.25% |
| **Self-Discharge Rate** | 0.1 | %/hour | 2.4% per day |
| **SOC Min** | 10 | % | Deep discharge capable |
| **SOC Max** | 100 | % | Full capacity utilization |
| **Initial SOC** | 50 | % | Starting condition |
| **Usable Capacity** | 36 | kWh | (100% - 10%) × 40 kWh |

**Strategic Role:** Primary grid arbitrage battery, handles bulk energy shifting, peak shaving for REC.

---

### 3.2 Node 6: Household (Medium Residential)

**Rationale:** Medium PV system (4.2 kWp) serving high residential load (14,094 kWh/year).

| Parameter | Value | Unit | Notes |
|-----------|-------|------|-------|
| **Capacity** | 10 | kWh | 2.4h at peak PV output |
| **Max Charge Power** | 5 | kW | 1.19× peak PV (4.2 kWp) |
| **Max Discharge Power** | 5 | kW | Standard residential inverter |
| **Charge Efficiency** | 92 | % | Mid-tier residential battery |
| **Discharge Efficiency** | 92 | % | Round-trip: 84.64% |
| **Self-Discharge Rate** | 0.2 | %/hour | 4.8% per day |
| **SOC Min** | 20 | % | Battery protection threshold |
| **SOC Max** | 100 | % | Full capacity utilization |
| **Initial SOC** | 50 | % | Starting condition |
| **Usable Capacity** | 8 | kWh | (100% - 20%) × 10 kWh |

**Strategic Role:** Evening residential peak support, local self-consumption optimization.

---

### 3.3 Node 8: Household (Small Residential)

**Rationale:** Small PV system (2.6 kWp) serving low residential load (1,804 kWh/year).

| Parameter | Value | Unit | Notes |
|-----------|-------|------|-------|
| **Capacity** | 6.5 | kWh | 2.5h at peak PV output |
| **Max Charge Power** | 3.25 | kW | 1.25× peak PV (2.6 kWp) |
| **Max Discharge Power** | 3.25 | kW | Basic residential inverter |
| **Charge Efficiency** | 90 | % | Entry-level battery |
| **Discharge Efficiency** | 90 | % | Round-trip: 81% |
| **Self-Discharge Rate** | 0.3 | %/hour | 7.2% per day |
| **SOC Min** | 20 | % | Battery protection threshold |
| **SOC Max** | 100 | % | Full capacity utilization |
| **Initial SOC** | 50 | % | Starting condition |
| **Usable Capacity** | 5.2 | kWh | (100% - 20%) × 6.5 kWh |

**Strategic Role:** Local self-consumption only, limited REC-level contribution due to low efficiency.

---

### 3.4 Aggregate Battery Fleet

| Metric | Total | Notes |
|--------|-------|-------|
| **Total Nominal Capacity** | 56.5 kWh | Sum of all three batteries |
| **Total Usable Capacity** | 49.2 kWh | Accounting for SOC limits |
| **Total Charge Power** | 28.25 kW | Sum of max charge rates |
| **Total Discharge Power** | 28.25 kW | Sum of max discharge rates |
| **Weighted Avg Efficiency** | 87.8% | Capacity-weighted round-trip |

---

## 4. Mathematical Model Formulation

### 4.1 Sets and Indices

- **N** = {1, 2, 3, 4, 5, 6, 7, 8, 9}: All REC nodes
- **B** = {2, 6, 8} ⊂ N: Nodes with batteries (prosumers)
- **C** = {1, 3, 4, 5, 7, 9} ⊂ N: Nodes without batteries (consumers)
- **T** = {0, 1, ..., 95}: Time intervals (15-min resolution, 24 hours)

### 4.2 Parameters

**Time Series Data:**
- **L<sub>i,t</sub>**: Load demand at node i, time t [kW]
- **PV<sub>i,t</sub>**: PV generation at node i, time t [kW] (i ∈ B only)
- **π<sub>t</sub><sup>DA</sup>**: Day-ahead market price at time t [€/kWh]
- **π<sub>t</sub><sup>FI</sup>**: Feed-in tariff at time t [€/kWh]

**Battery Specifications (for i ∈ B):**
- **E<sub>i</sub><sup>cap</sup>**: Battery capacity [kWh]
- **P<sub>i</sub><sup>ch,max</sup>**: Max charging power [kW]
- **P<sub>i</sub><sup>dch,max</sup>**: Max discharging power [kW]
- **η<sub>i</sub><sup>ch</sup>**: Charging efficiency [dimensionless]
- **η<sub>i</sub><sup>dch</sup>**: Discharging efficiency [dimensionless]
- **σ<sub>i</sub>**: Self-discharge rate [1/hour]
- **SOC<sub>i</sub><sup>min</sup>**: Minimum state of charge [% of E<sub>i</sub><sup>cap</sup>]
- **SOC<sub>i</sub><sup>max</sup>**: Maximum state of charge [% of E<sub>i</sub><sup>cap</sup>]
- **SOC<sub>i</sub><sup>init</sup>**: Initial state of charge [% of E<sub>i</sub><sup>cap</sup>]

**Economic Parameters:**
- **π<sup>grid</sup>**: Grid fee [€/kWh] = 0.02
- **Δt**: Time interval duration [hours] = 0.25 (15 minutes)

### 4.3 Decision Variables

**Power Flows (Continuous, ≥ 0):**
- **P<sub>i,t</sub><sup>grid,import</sup>**: Power imported from grid at node i, time t [kW]
- **P<sub>i,t</sub><sup>grid,export</sup>**: Power exported to grid at node i, time t [kW]
- **P<sub>i,t</sub><sup>rec,import</sup>**: Power imported from REC at node i, time t [kW]
- **P<sub>i,t</sub><sup>rec,export</sup>**: Power exported to REC at node i, time t [kW]

**Battery Variables (i ∈ B only):**
- **P<sub>i,t</sub><sup>ch</sup>**: Charging power [kW] (Continuous, ≥ 0)
- **P<sub>i,t</sub><sup>dch</sup>**: Discharging power [kW] (Continuous, ≥ 0)
- **E<sub>i,t</sub><sup>SOC</sup>**: State of charge [kWh] (Continuous, ≥ 0)

**Binary Variables:**
- **b<sub>i,t</sub><sup>ch</sup>**: Battery charging indicator (1 = charging, 0 = not)
- **b<sub>i,t</sub><sup>grid</sup>**: Grid flow direction (1 = import, 0 = export)

---

### 4.4 Objective Function

**Minimize Total REC Cost over 24 hours:**

```
min Z = ∑[i∈N] ∑[t∈T] [
    P[i,t]^(grid,import) × π[t]^DA × Δt                          [Grid purchase cost]
    + (P[i,t]^(grid,import) + P[i,t]^(grid,export)) × π^grid × Δt   [Grid fees]
    - P[i,t]^(grid,export) × π[t]^FI × Δt                         [Feed-in revenue]
]
```

**Note:** Internal REC transactions (P<sup>rec,import</sup> and P<sup>rec,export</sup>) cancel out in total cost calculation since one member's export is another's import at the same price (€0.08/kWh).

---

### 4.5 Constraints

#### 4.5.1 Energy Balance - Consumers (i ∈ C)

```
L[i,t] = P[i,t]^(grid,import) + P[i,t]^(rec,import) 
         - P[i,t]^(grid,export) - P[i,t]^(rec,export)     ∀i ∈ C, ∀t ∈ T
```

Consumers have no local generation or storage, so load must equal net imports.

---

#### 4.5.2 Energy Balance - Prosumers (i ∈ B)

```
PV[i,t] + P[i,t]^dch + P[i,t]^(grid,import) + P[i,t]^(rec,import)
- L[i,t] - P[i,t]^ch - P[i,t]^(grid,export) - P[i,t]^(rec,export) = 0     ∀i ∈ B, ∀t ∈ T
```

Prosumers have **load consumption (L[i,t])**, **PV generation**, and **battery storage**. Energy balance: all sources (PV + battery discharge + imports) must equal all sinks (load + battery charge + exports).

---

#### 4.5.3 REC Energy Balance (Community-Wide)

```
∑[i∈N] P[i,t]^(rec,export) = ∑[i∈N] P[i,t]^(rec,import)     ∀t ∈ T
```

Total energy exported within REC must equal total energy imported (conservation of energy within community).

---

#### 4.5.4 Battery State of Charge Dynamics (i ∈ B)

**Initial Condition (t = 0):**
```
E[i,0]^SOC = E[i]^cap × SOC[i]^init     ∀i ∈ B
```

**Evolution (t > 0):**
```
E[i,t]^SOC = E[i,t-1]^SOC × (1 - σ[i] × Δt)                [Self-discharge loss]
             + P[i,t-1]^ch × η[i]^ch × Δt                  [Charging gain]
             - P[i,t-1]^dch / η[i]^dch × Δt                [Discharging loss]
                                                            ∀i ∈ B, ∀t ∈ T \ {0}
```

**Physical Interpretation:**
- Battery loses energy over time due to self-discharge (σ)
- Charging adds energy with efficiency loss (η<sup>ch</sup> < 1)
- Discharging removes more energy than delivered (1/η<sup>dch</sup> > 1)

---

#### 4.5.5 Battery State of Charge Limits (i ∈ B)

```
E[i]^cap × SOC[i]^min ≤ E[i,t]^SOC ≤ E[i]^cap × SOC[i]^max     ∀i ∈ B, ∀t ∈ T
```

**Node-Specific Limits:**
- Node 2: 4 kWh ≤ E[2,t]^SOC ≤ 40 kWh (10% - 100%)
- Node 6: 2 kWh ≤ E[6,t]^SOC ≤ 10 kWh (20% - 100%)
- Node 8: 1.3 kWh ≤ E[8,t]^SOC ≤ 6.5 kWh (20% - 100%)

---

#### 4.5.6 Battery Charging Power Limits (i ∈ B)

```
0 ≤ P[i,t]^ch ≤ min(P[i]^(ch,max), E[i]^cap × 1.0)     ∀i ∈ B, ∀t ∈ T
```

**Node-Specific Limits:**
- Node 2: 0 ≤ P[2,t]^ch ≤ 20 kW
- Node 6: 0 ≤ P[6,t]^ch ≤ 5 kW
- Node 8: 0 ≤ P[8,t]^ch ≤ 3.25 kW

**Optional C-Rate Protection:** Additional constraint limits charging to 1C (capacity/hour) to protect battery health.

---

#### 4.5.7 Battery Discharging Power Limits (i ∈ B)

```
0 ≤ P[i,t]^dch ≤ min(P[i]^(dch,max), E[i]^cap × 1.0)     ∀i ∈ B, ∀t ∈ T
```

**Node-Specific Limits:**
- Node 2: 0 ≤ P[2,t]^dch ≤ 20 kW
- Node 6: 0 ≤ P[6,t]^dch ≤ 5 kW
- Node 8: 0 ≤ P[8,t]^dch ≤ 3.25 kW

---

#### 4.5.8 No Simultaneous Charge/Discharge (i ∈ B)

```
P[i,t]^ch ≤ P[i]^(ch,max) × b[i,t]^ch                      ∀i ∈ B, ∀t ∈ T
P[i,t]^dch ≤ P[i]^(dch,max) × (1 - b[i,t]^ch)              ∀i ∈ B, ∀t ∈ T
b[i,t]^ch ∈ {0, 1}                                          ∀i ∈ B, ∀t ∈ T
```

**Physical Interpretation:** Battery cannot charge and discharge simultaneously. Binary variable b<sub>i,t</sub><sup>ch</sup> enforces this logical constraint.

---

#### 4.5.9 No Simultaneous Grid Import/Export (i ∈ N)

```
P[i,t]^(grid,import) ≤ M × b[i,t]^grid                     ∀i ∈ N, ∀t ∈ T
P[i,t]^(grid,export) ≤ M × (1 - b[i,t]^grid)               ∀i ∈ N, ∀t ∈ T
b[i,t]^grid ∈ {0, 1}                                        ∀i ∈ N, ∀t ∈ T
```

**Physical Interpretation:** Node cannot import from and export to grid simultaneously. M is a sufficiently large constant (e.g., 1000 kW).

---

## 5. Optimization Strategy and Expected Behavior

### 5.1 Charging Priority (Morning/Midday)

When REC has PV surplus, the optimizer charges batteries in this order:

1. **Node 2 (40 kWh, 90.25% efficiency):**
   - Highest capacity → can absorb most surplus
   - Best efficiency → minimizes energy loss
   - Lowest SOC limit (10%) → more usable capacity
   - **Target fill time:** 2 hours at 20 kW = full charge

2. **Node 6 (10 kWh, 84.64% efficiency):**
   - Medium capacity → residential load matching
   - Good efficiency → acceptable losses
   - **Target fill time:** 2 hours at 5 kW = full charge

3. **Node 8 (6.5 kWh, 81% efficiency):**
   - Small capacity → limited absorption
   - Lower efficiency → use sparingly
   - **Target fill time:** 2 hours at 3.25 kW = full charge

**Rationale:** Fill largest and most efficient batteries first to maximize REC-level energy arbitrage opportunities.

---

### 5.2 Discharging Priority (Evening Peak)

When REC has load deficit (evening), the optimizer discharges batteries in this order:

1. **Node 8 (small, low efficiency):**
   - Discharge early → preserve Node 2 for bigger arbitrage
   - Limited capacity → won't sustain long discharge
   - **Target: Local self-consumption only**

2. **Node 6 (medium, good efficiency):**
   - Support residential evening peak (18:00-21:00)
   - Moderate capacity → 2-3 hours discharge at 5 kW
   - **Target: Residential load support**

3. **Node 2 (large, high efficiency):**
   - Reserve for highest-value discharge periods
   - Large capacity → 4+ hours discharge at 20 kW
   - **Target: Grid arbitrage, peak demand reduction**

**Rationale:** Preserve high-capacity, high-efficiency battery (Node 2) for maximum-value discharge opportunities (highest grid prices or peak demand charges).

---

### 5.3 Daily Cycle Example

**Typical Summer Day (High PV):**

| Time | REC Net Position | Node 2 Battery | Node 6 Battery | Node 8 Battery | Grid Interaction |
|------|------------------|----------------|----------------|----------------|------------------|
| 00:00-06:00 | Deficit (consumers only) | Idle (preserve) | Idle | Idle | Import (~15 kW) |
| 06:00-09:00 | Small surplus (PV starts) | **Charging** (0→20 kW) | **Charging** (0→5 kW) | **Charging** (0→3 kW) | Minimal |
| 09:00-12:00 | Large surplus (peak PV) | **Charging** (full by 11:00) | **Charging** (full by 11:00) | **Charging** (full by 11:00) | Export surplus |
| 12:00-15:00 | Max surplus | Idle (full) | Idle (full) | Idle (full) | Export (~25 kW) |
| 15:00-17:00 | Declining surplus | Idle | Idle | Idle | Minimal |
| 17:00-19:00 | Deficit (no PV, high load) | Idle (reserve) | **Discharging** (5 kW) | **Discharging** (3 kW) | Import (~7 kW) |
| 19:00-21:00 | High deficit (peak demand) | **Discharging** (20 kW) | **Discharging** (5 kW) | Empty | Import (~10 kW) |
| 21:00-24:00 | Moderate deficit | **Discharging** (10 kW) | Empty | Empty | Import (~5 kW) |

**Key Metrics:**
- Total Battery Charged: ~56 kWh (accounting for efficiency losses)
- Total Battery Discharged: ~50 kWh delivered to loads
- Round-trip Energy Loss: ~6 kWh (10-15% depending on battery mix)
- Peak Grid Import Reduction: ~25 kW (batteries discharge during peak)
- Peak Grid Export Reduction: ~15 kW (batteries charge during surplus)

---

## 6. Expected Outcomes

**Baseline (No Batteries):**
- Total daily cost: ~€X (grid purchases - feed-in revenue)
- Peak grid import: ~40 kW
- Peak grid export: ~30 kW

**With Optimized Batteries:**
- Total daily cost: ~€Y (expect 15-25% reduction)
- Peak grid import: ~20 kW (50% reduction via discharge)
- Peak grid export: ~20 kW (33% reduction via charge)
- Self-consumption ratio: +20-30% (PV → battery → load)

---

## 7. Limitations and Assumptions

### 7.1 Model Assumptions

1. **Perfect Foresight:** Model assumes perfect day-ahead forecasts (unrealistic)
   - **Mitigation:** Re-optimize with updated forecasts at intraday stage

2. **Linear Efficiency:** Battery efficiency constant regardless of SOC or power level
   - **Reality:** Efficiency varies with temperature, SOC, and C-rate
   - **Impact:** ±2-5% energy throughput error

3. **No Battery Degradation:** Model doesn't account for capacity fade over time
   - **Reality:** Capacity decreases ~2% per year (500-1000 cycles)
   - **Mitigation:** Reduce E<sup>cap</sup> by 2% annually in multi-year simulations

4. **No Network Constraints:** Assumes unlimited power transfer within REC
   - **Reality:** Distribution lines have thermal limits
   - **Mitigation:** Add line capacity constraints if critical

5. **Single Price Signal:** Uses day-ahead prices only
   - **Reality:** Intraday prices, imbalance prices also relevant
   - **Enhancement:** Multi-stage stochastic optimization

---

---

## 8. References

### 8.1 Technical Standards

1. **IEC 61850:** Communication networks for substations (battery control protocols)
2. **IEEE 1547:** Interconnection of distributed energy resources
3. **VDE-AR-N 4110:** Technical requirements for DER grid connection (Germany)

### 8.2 Academic Literature

1. Peng, W., et al. (2018). "Optimizing rooftop photovoltaic distributed generation with battery storage for peer-to-peer energy trading." *Applied Energy*, 228, 2567-2580.
2. Mixed-integer linear programming for battery energy storage systems (various sources)
3. BDEW standard load profiles documentation (Germany)

### 8.3 Software Tools

1. **Pyomo:** Python optimization modeling language
2. **GLPK:** GNU Linear Programming Kit (open-source solver)
3. **SimBench:** Benchmark datasets for power system analysis

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-01 | REC Optimization Team | Initial release |

**Approval:**
- Technical Review: ✓ Pending
- Economic Analysis: ✓ Pending
- Regulatory Compliance: ✓ Pending

**Next Review Date:** 2026-05-01

---

**END OF DOCUMENT**
