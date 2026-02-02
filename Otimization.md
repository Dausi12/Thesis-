# Optimisation Model for Battery Scheduling in an Austrian Renewable Energy Community

## Statement on the Choice of Objective Function

The objective of minimising total interaction with the public grid,

$$
\min \sum_{t \in T} \left( P_t^{\text{import}} + P_t^{\text{export}} \right),
$$

is commonly applied in the renewable energy community literature as a proxy for maximising local self-consumption and reducing stress on the public distribution network. However, this formulation implicitly assumes non-negative electricity prices and equivalence between reduced grid interaction and economic optimality.

Under market-based electricity settlement with time-varying and potentially negative prices, as observed in current European wholesale markets and reflected in Austrian electricity pricing, minimising grid interaction may lead to suboptimal or economically inconsistent operating decisions. In particular, periods of negative electricity prices may incentivise deliberate grid imports in order to charge storage systems, which would be artificially suppressed by a grid-interaction-minimising objective.

For this reason, the optimisation model adopts a **cost-minimising formulation** that explicitly accounts for electricity procurement costs and feed-in revenues. This approach ensures economically rational battery operation under all price regimes while still allowing increased local self-consumption to emerge endogenously whenever it is economically advantageous.

---

## Final Thesis Summary Paragraph (Refined and Aligned)

The battery scheduling problem of the renewable energy community (*Erneuerbare-Energie-Gemeinschaft*, EEG) is formulated as a linear optimisation model. The objective is to minimise the total electricity procurement costs of the community, including revenues from electricity fed into the public grid. This cost-based formulation reflects market-oriented electricity pricing and remains valid under time-varying and negative price signals. The model respects power balance constraints at the community level, battery energy dynamics, and technical limits on storage and grid exchange, thereby enabling the economically optimal temporal shifting of locally generated photovoltaic electricity within the regulatory framework of the Austrian *Erneuerbaren-Ausbau-Gesetz*.

---

## 1. Purpose and Scope of the Optimisation Model

The purpose of the optimisation model is to determine the optimal operation of a battery storage system within a Renewable Energy Community (*Erneuerbare-Energie-Gemeinschaft*, EEG) under the Austrian regulatory framework defined by the *Erneuerbaren-Ausbau-Gesetz* (EAG).

The model supports the coordinated temporal shifting of locally generated photovoltaic (PV) electricity in order to reduce electricity procurement costs at the community level while respecting technical and regulatory constraints.

The optimisation is formulated at the aggregated community level and focuses on short-term operational decisions, assuming perfect foresight of demand, generation, and electricity prices within the planning horizon.

---

## 2. Sets and Indices

| Symbol | Description |
|--------|-------------|
| $t \in T$ | Time steps in the planning horizon (e.g. hourly or 15-minute resolution) |

---

## 3. Decision Variables

All decision variables are continuous and non-negative.

| Variable | Unit | Description |
|----------|------|-------------|
| $P_t^{\text{ch}}$ | kW | Battery charging power at time step $t$ |
| $P_t^{\text{dis}}$ | kW | Battery discharging power at time step $t$ |
| $\text{SoC}_t$ | kWh | State of charge of the battery at the end of time step $t$ |
| $P_t^{\text{import}}$ | kW | Power imported from the public grid |
| $P_t^{\text{export}}$ | kW | Power exported to the public grid |

---

## 4. Parameters

### 4.1 Technical and Operational Parameters

| Parameter | Unit | Description |
|-----------|------|-------------|
| $P_t^{\text{load}}$ | kW | Aggregated electricity demand of the REC |
| $P_t^{\text{PV}}$ | kW | Aggregated photovoltaic generation |
| $\eta_{\text{ch}}$ | – | Battery charging efficiency |
| $\eta_{\text{dis}}$ | – | Battery discharging efficiency |
| $\text{SoC}_{\min}$ | kWh | Minimum allowable battery state of charge |
| $\text{SoC}_{\max}$ | kWh | Maximum battery capacity |
| $P_{\text{ch,max}}$ | kW | Maximum charging power |
| $P_{\text{dis,max}}$ | kW | Maximum discharging power |
| $P_{\text{grid,max}}$ | kW | Grid connection limit |
| $\text{SoC}_0$ | kWh | Initial state of charge |
| $\Delta t$ | h | Time step duration |

### 4.2 Economic Parameters

| Parameter | Unit | Description |
|-----------|------|-------------|
| $\lambda_t^{\text{imp}}$ | €/kWh | Electricity import price (may be negative) |
| $\lambda_t^{\text{exp}}$ | €/kWh | Feed-in remuneration for electricity exports |

---

## 5. Objective Function

### Cost-Minimising Objective (Recommended)

The objective is to minimise total electricity procurement costs of the renewable energy community, accounting for electricity imports from and exports to the public grid:

$$
\min \sum_{t \in T} \left( \lambda_t^{\text{imp}} \, P_t^{\text{import}} - \lambda_t^{\text{exp}} \, P_t^{\text{export}} \right) \Delta t
$$

This formulation:

- Reflects market-based electricity settlement under the EAG
- Explicitly allows for time-varying and negative electricity prices
- Incentivises economically optimal charging during periods of low or negative prices
- Avoids artificial restrictions on grid interaction

---

## 6. Model Constraints

### 6.1 Power Balance Constraint (Community Level)

For each time step, electricity demand must be satisfied by local generation, battery operation, and grid exchange:

$$
P_t^{\text{load}} = P_t^{\text{PV}} + P_t^{\text{import}} - P_t^{\text{export}} + P_t^{\text{dis}} - P_t^{\text{ch}} \quad \forall t \in T
$$

### 6.2 Battery State-of-Charge Dynamics

The evolution of the battery state of charge is governed by charging and discharging actions:

$$
\text{SoC}_{t+1} = \text{SoC}_t + \eta_{\text{ch}} \, P_t^{\text{ch}} \Delta t - \frac{1}{\eta_{\text{dis}}} \, P_t^{\text{dis}} \Delta t \quad \forall t \in T
$$

**Initial condition:**

$$
\text{SoC}_1 = \text{SoC}_0
$$

### 6.3 Battery Capacity Limits

$$
\text{SoC}_{\min} \leq \text{SoC}_t \leq \text{SoC}_{\max} \quad \forall t \in T
$$

### 6.4 Battery Power Limits

$$
0 \leq P_t^{\text{ch}} \leq P_{\text{ch,max}} \quad \forall t \in T
$$

$$
0 \leq P_t^{\text{dis}} \leq P_{\text{dis,max}} \quad \forall t \in T
$$

### 6.5 Grid Exchange Limits

$$
0 \leq P_t^{\text{import}} \leq P_{\text{grid,max}} \quad \forall t \in T
$$

$$
0 \leq P_t^{\text{export}} \leq P_{\text{grid,max}} \quad \forall t \in T
$$

### 6.6 Non-Negativity

$$
P_t^{\text{ch}}, \; P_t^{\text{dis}}, \; P_t^{\text{import}}, \; P_t^{\text{export}} \geq 0 \quad \forall t \in T
$$

---

## 7. Model Characteristics

| Aspect | Description |
|--------|-------------|
| **Problem class** | Linear Programming (LP) |
| **Convexity** | Convex |
| **Deterministic** | Yes |
| **Binary variables** | None |
| **Solvers** | CBC, HiGHS, Gurobi, CPLEX |

**Note:** Simultaneous charging and discharging or simultaneous grid import and export are not explicitly prohibited. However, due to efficiency losses and the cost-minimising objective, such behaviour is never optimal in the solution.

---

## 8. Regulatory Interpretation (Austria – EAG)

The optimisation reflects the operational reality of Austrian EEGs:

- Electricity is settled based on market-oriented price signals
- Feed-in remuneration and procurement costs are explicitly modelled
- No profit maximisation is imposed, consistent with the cooperative nature of EEGs
- Increased self-consumption arises endogenously whenever it is economically advantageous

---

## 9. Final Thesis Summary Sentence

The battery scheduling problem of the renewable energy community is formulated as a linear optimisation model that minimises total electricity procurement costs, including revenues from electricity exports, while respecting power balance constraints, battery energy dynamics, and technical limits. The formulation remains valid under time-varying and negative electricity prices and enables economically optimal temporal shifting of locally generated photovoltaic energy within the Austrian regulatory framework.
