"""
REC-Level Battery Optimization with Heterogeneous Distributed Storage
Mixed-Integer Linear Programming (MILP) Implementation using Pyomo

Based on the mathematical formulation in REC_BATTERY_OPTIMIZATION_METHODOLOGY.tex
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import json
import warnings

try:
    import pyomo.environ as pyo
    from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False
    raise ImportError("Pyomo is required for optimization. Install with: pip install pyomo")


class RECBatteryOptimizer:
    """
    REC-level battery optimization with heterogeneous distributed storage.
    
    Optimizes coordinated charging/discharging of 3 distributed batteries
    to minimize total community energy costs while respecting individual
    battery technical specifications and grid constraints.
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize REC battery optimizer.
        
        Parameters:
        -----------
        config_path : str, optional
            Path to JSON configuration file (C3_single_supplier_rec_battery.json)
        """
        self.config = None
        self.model = None
        self.results = None
        
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path: str):
        """Load configuration from JSON file."""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        print(f"✓ Loaded configuration from {config_path}")
    
    def optimize(
        self,
        load_profiles: Dict[int, np.ndarray],
        pv_profiles: Dict[int, np.ndarray],
        da_prices: np.ndarray,
        feedin_prices: np.ndarray,
        battery_specs: Dict[int, Dict[str, float]],
        time_intervals: int = 96,
        solver: str = 'glpk',
        solver_options: Dict = None,
        verbose: bool = True
    ) -> Tuple[Dict, float, pyo.ConcreteModel]:
        """
        Optimize REC battery schedules for 24-hour horizon.
        
        Parameters:
        -----------
        load_profiles : Dict[int, np.ndarray]
            Load demand for each node [kW]. Keys: node IDs (1-9), Values: 96-length arrays
        pv_profiles : Dict[int, np.ndarray]
            PV generation for prosumer nodes [kW]. Keys: {2, 6, 8}, Values: 96-length arrays
        da_prices : np.ndarray
            Day-ahead market prices [€/kWh]. Length: 96
        feedin_prices : np.ndarray
            Feed-in tariff prices [€/kWh]. Length: 96
        battery_specs : Dict[int, Dict[str, float]]
            Battery specifications for nodes {2, 6, 8}. Required keys:
            - 'capacity_kwh': Battery capacity [kWh]
            - 'max_charge_kw': Max charging power [kW]
            - 'max_discharge_kw': Max discharging power [kW]
            - 'charge_efficiency': Charging efficiency [0-1]
            - 'discharge_efficiency': Discharging efficiency [0-1]
            - 'self_discharge_rate': Self-discharge rate [1/hour]
            - 'soc_min': Minimum SOC [0-1]
            - 'soc_max': Maximum SOC [0-1]
            - 'initial_soc': Initial SOC [0-1]
        time_intervals : int
            Number of time intervals (default: 96 for 15-min resolution)
        solver : str
            Solver to use ('glpk', 'cbc', 'gurobi', 'cplex')
        solver_options : Dict, optional
            Solver-specific options
        verbose : bool
            Print optimization progress
        
        Returns:
        --------
        battery_schedules : Dict
            Optimized battery schedules with keys:
            - 'charge_power': Charging power per battery [kW]
            - 'discharge_power': Discharging power per battery [kW]
            - 'soc': State of charge per battery [kWh]
            - 'grid_import': Grid imports per node [kW]
            - 'grid_export': Grid exports per node [kW]
            - 'rec_import': REC imports per node [kW]
            - 'rec_export': REC exports per node [kW]
        total_cost : float
            Optimal objective value [€]
        model : pyo.ConcreteModel
            Solved Pyomo model for post-analysis
        """
        
        if verbose:
            print("=" * 70)
            print("REC BATTERY OPTIMIZATION - HETEROGENEOUS DISTRIBUTED STORAGE")
            print("=" * 70)
        
        # ========== SETS AND INDICES ==========
        all_nodes = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        battery_nodes = [2, 6, 8]
        consumer_nodes = [1, 3, 4, 5, 7, 9]
        timesteps = list(range(time_intervals))
        
        # ========== PARAMETERS ==========
        delta_t = 0.25  # 15 minutes in hours
        grid_fee = 0.02  # €/kWh
        big_M = 1000.0  # kW (sufficiently large constant)
        
        # Validate inputs
        assert len(da_prices) == time_intervals, "DA prices length mismatch"
        assert len(feedin_prices) == time_intervals, "Feed-in prices length mismatch"
        for node in all_nodes:
            assert node in load_profiles, f"Missing load profile for node {node}"
            assert len(load_profiles[node]) == time_intervals, f"Load profile length mismatch for node {node}"
        for node in battery_nodes:
            assert node in pv_profiles, f"Missing PV profile for battery node {node}"
            assert len(pv_profiles[node]) == time_intervals, f"PV profile length mismatch for node {node}"
            assert node in battery_specs, f"Missing battery specs for node {node}"
        
        if verbose:
            print(f"\n📊 Problem Size:")
            print(f"   Nodes: {len(all_nodes)} (Batteries: {len(battery_nodes)}, Consumers: {len(consumer_nodes)})")
            print(f"   Time intervals: {time_intervals}")
            print(f"   Time resolution: {delta_t * 60:.0f} minutes")
        
        # ========== CREATE PYOMO MODEL ==========
        model = pyo.ConcreteModel(name="REC_Battery_Optimization")
        
        # Sets
        model.NODES = pyo.Set(initialize=all_nodes)
        model.BATTERIES = pyo.Set(initialize=battery_nodes)
        model.CONSUMERS = pyo.Set(initialize=consumer_nodes)
        model.TIME = pyo.Set(initialize=timesteps)
        
        # Parameters
        model.L = pyo.Param(model.NODES, model.TIME, initialize={
            (i, t): load_profiles[i][t] for i in all_nodes for t in timesteps
        })
        
        model.PV = pyo.Param(model.BATTERIES, model.TIME, initialize={
            (i, t): pv_profiles[i][t] for i in battery_nodes for t in timesteps
        })
        
        model.pi_DA = pyo.Param(model.TIME, initialize={t: da_prices[t] for t in timesteps})
        model.pi_FI = pyo.Param(model.TIME, initialize={t: feedin_prices[t] for t in timesteps})
        model.pi_grid = pyo.Param(initialize=grid_fee)
        model.delta_t = pyo.Param(initialize=delta_t)
        model.M = pyo.Param(initialize=big_M)
        
        # Battery specifications
        model.E_cap = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['capacity_kwh'] for i in battery_nodes
        })
        model.P_ch_max = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['max_charge_kw'] for i in battery_nodes
        })
        model.P_dch_max = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['max_discharge_kw'] for i in battery_nodes
        })
        model.eta_ch = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['charge_efficiency'] for i in battery_nodes
        })
        model.eta_dch = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['discharge_efficiency'] for i in battery_nodes
        })
        model.sigma = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['self_discharge_rate'] for i in battery_nodes
        })
        model.SOC_min = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['soc_min'] for i in battery_nodes
        })
        model.SOC_max = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['soc_max'] for i in battery_nodes
        })
        model.SOC_init = pyo.Param(model.BATTERIES, initialize={
            i: battery_specs[i]['initial_soc'] for i in battery_nodes
        })
        
        # ========== DECISION VARIABLES ==========
        
        # Power flows (continuous, >= 0)
        model.P_grid_import = pyo.Var(model.NODES, model.TIME, domain=pyo.NonNegativeReals)
        model.P_grid_export = pyo.Var(model.NODES, model.TIME, domain=pyo.NonNegativeReals)
        model.P_rec_import = pyo.Var(model.NODES, model.TIME, domain=pyo.NonNegativeReals)
        model.P_rec_export = pyo.Var(model.NODES, model.TIME, domain=pyo.NonNegativeReals)
        
        # Battery variables (continuous, >= 0)
        model.P_ch = pyo.Var(model.BATTERIES, model.TIME, domain=pyo.NonNegativeReals)
        model.P_dch = pyo.Var(model.BATTERIES, model.TIME, domain=pyo.NonNegativeReals)
        model.E_SOC = pyo.Var(model.BATTERIES, model.TIME, domain=pyo.NonNegativeReals)
        
        # Binary variables
        model.b_ch = pyo.Var(model.BATTERIES, model.TIME, domain=pyo.Binary)
        model.b_grid = pyo.Var(model.NODES, model.TIME, domain=pyo.Binary)
        
        # ========== OBJECTIVE FUNCTION ==========
        
        def objective_rule(m):
            """Minimize total REC cost over 24 hours."""
            return sum(
                m.P_grid_import[i, t] * m.pi_DA[t] * m.delta_t  # Grid purchase cost
                + (m.P_grid_import[i, t] + m.P_grid_export[i, t]) * m.pi_grid * m.delta_t  # Grid fees
                - m.P_grid_export[i, t] * m.pi_FI[t] * m.delta_t  # Feed-in revenue
                for i in m.NODES for t in m.TIME
            )
        
        model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)
        
        # ========== CONSTRAINTS ==========
        
        # 4.5.1: Energy Balance - Consumers
        def energy_balance_consumers_rule(m, i, t):
            """Consumers have no local generation or storage."""
            return (m.L[i, t] == 
                    m.P_grid_import[i, t] + m.P_rec_import[i, t] 
                    - m.P_grid_export[i, t] - m.P_rec_export[i, t])
        
        model.energy_balance_consumers = pyo.Constraint(
            model.CONSUMERS, model.TIME, rule=energy_balance_consumers_rule
        )
        
        # 4.5.2: Energy Balance - Prosumers
        def energy_balance_prosumers_rule(m, i, t):
            """Prosumers have load, PV, and battery storage."""
            return (m.PV[i, t] + m.P_dch[i, t] + m.P_grid_import[i, t] + m.P_rec_import[i, t]
                    - m.L[i, t] - m.P_ch[i, t] - m.P_grid_export[i, t] - m.P_rec_export[i, t] == 0)
        
        model.energy_balance_prosumers = pyo.Constraint(
            model.BATTERIES, model.TIME, rule=energy_balance_prosumers_rule
        )
        
        # 4.5.3: REC Energy Balance (Community-Wide)
        def rec_energy_balance_rule(m, t):
            """Total REC exports must equal total REC imports."""
            return sum(m.P_rec_export[i, t] for i in m.NODES) == sum(m.P_rec_import[i, t] for i in m.NODES)
        
        model.rec_energy_balance = pyo.Constraint(model.TIME, rule=rec_energy_balance_rule)
        
        # 4.5.4: Battery State of Charge Dynamics
        def soc_initial_rule(m, i):
            """Initial SOC condition (t=0)."""
            return m.E_SOC[i, 0] == m.E_cap[i] * m.SOC_init[i]
        
        model.soc_initial = pyo.Constraint(model.BATTERIES, rule=soc_initial_rule)
        
        def soc_evolution_rule(m, i, t):
            """SOC evolution over time (t > 0)."""
            if t == 0:
                return pyo.Constraint.Skip
            return (m.E_SOC[i, t] == 
                    m.E_SOC[i, t-1] * (1 - m.sigma[i] * m.delta_t)  # Self-discharge loss
                    + m.P_ch[i, t-1] * m.eta_ch[i] * m.delta_t  # Charging gain
                    - m.P_dch[i, t-1] / m.eta_dch[i] * m.delta_t)  # Discharging loss
        
        model.soc_evolution = pyo.Constraint(model.BATTERIES, model.TIME, rule=soc_evolution_rule)
        
        # 4.5.5: Battery State of Charge Limits
        def soc_min_rule(m, i, t):
            """Minimum SOC constraint."""
            return m.E_SOC[i, t] >= m.E_cap[i] * m.SOC_min[i]
        
        def soc_max_rule(m, i, t):
            """Maximum SOC constraint."""
            return m.E_SOC[i, t] <= m.E_cap[i] * m.SOC_max[i]
        
        model.soc_min = pyo.Constraint(model.BATTERIES, model.TIME, rule=soc_min_rule)
        model.soc_max = pyo.Constraint(model.BATTERIES, model.TIME, rule=soc_max_rule)
        
        # 4.5.6: Battery Charging Power Limits
        def charge_power_limit_rule(m, i, t):
            """Maximum charging power constraint."""
            return m.P_ch[i, t] <= m.P_ch_max[i]
        
        model.charge_power_limit = pyo.Constraint(model.BATTERIES, model.TIME, rule=charge_power_limit_rule)
        
        # 4.5.7: Battery Discharging Power Limits
        def discharge_power_limit_rule(m, i, t):
            """Maximum discharging power constraint."""
            return m.P_dch[i, t] <= m.P_dch_max[i]
        
        model.discharge_power_limit = pyo.Constraint(model.BATTERIES, model.TIME, rule=discharge_power_limit_rule)
        
        # 4.5.8: No Simultaneous Charge/Discharge
        def no_simultaneous_ch_dch_1_rule(m, i, t):
            """Charging limited by binary variable."""
            return m.P_ch[i, t] <= m.P_ch_max[i] * m.b_ch[i, t]
        
        def no_simultaneous_ch_dch_2_rule(m, i, t):
            """Discharging limited by complement of binary variable."""
            return m.P_dch[i, t] <= m.P_dch_max[i] * (1 - m.b_ch[i, t])
        
        model.no_simultaneous_ch_dch_1 = pyo.Constraint(
            model.BATTERIES, model.TIME, rule=no_simultaneous_ch_dch_1_rule
        )
        model.no_simultaneous_ch_dch_2 = pyo.Constraint(
            model.BATTERIES, model.TIME, rule=no_simultaneous_ch_dch_2_rule
        )
        
        # 4.5.9: No Simultaneous Grid Import/Export
        def no_simultaneous_grid_1_rule(m, i, t):
            """Grid import limited by binary variable."""
            return m.P_grid_import[i, t] <= m.M * m.b_grid[i, t]
        
        def no_simultaneous_grid_2_rule(m, i, t):
            """Grid export limited by complement of binary variable."""
            return m.P_grid_export[i, t] <= m.M * (1 - m.b_grid[i, t])
        
        model.no_simultaneous_grid_1 = pyo.Constraint(
            model.NODES, model.TIME, rule=no_simultaneous_grid_1_rule
        )
        model.no_simultaneous_grid_2 = pyo.Constraint(
            model.NODES, model.TIME, rule=no_simultaneous_grid_2_rule
        )
        
        if verbose:
            print(f"\n🔧 Model Statistics:")
            print(f"   Variables: ~{len(all_nodes) * time_intervals * 4 + len(battery_nodes) * time_intervals * 3}")
            print(f"   Binary variables: ~{(len(battery_nodes) + len(all_nodes)) * time_intervals}")
            print(f"   Constraints: ~{len(all_nodes) * time_intervals * 3 + len(battery_nodes) * time_intervals * 6}")
        
        # ========== SOLVE ==========
        
        if verbose:
            print(f"\n⚙️  Solving with {solver.upper()}...")
        
        opt = SolverFactory(solver)
        
        if solver_options:
            for key, value in solver_options.items():
                opt.options[key] = value
        
        # Solve the model
        solver_results = opt.solve(model, tee=verbose)
        
        # Check solver status
        if solver_results.solver.status != SolverStatus.ok:
            raise RuntimeError(f"Solver status: {solver_results.solver.status}")
        
        if solver_results.solver.termination_condition != TerminationCondition.optimal:
            raise RuntimeError(f"Termination condition: {solver_results.solver.termination_condition}")
        
        # ========== EXTRACT RESULTS ==========
        
        total_cost = pyo.value(model.objective)
        
        battery_schedules = {
            'charge_power': pd.DataFrame({
                i: [pyo.value(model.P_ch[i, t]) for t in timesteps]
                for i in battery_nodes
            }),
            'discharge_power': pd.DataFrame({
                i: [pyo.value(model.P_dch[i, t]) for t in timesteps]
                for i in battery_nodes
            }),
            'soc': pd.DataFrame({
                i: [pyo.value(model.E_SOC[i, t]) for t in timesteps]
                for i in battery_nodes
            }),
            'grid_import': pd.DataFrame({
                i: [pyo.value(model.P_grid_import[i, t]) for t in timesteps]
                for i in all_nodes
            }),
            'grid_export': pd.DataFrame({
                i: [pyo.value(model.P_grid_export[i, t]) for t in timesteps]
                for i in all_nodes
            }),
            'rec_import': pd.DataFrame({
                i: [pyo.value(model.P_rec_import[i, t]) for t in timesteps]
                for i in all_nodes
            }),
            'rec_export': pd.DataFrame({
                i: [pyo.value(model.P_rec_export[i, t]) for t in timesteps]
                for i in all_nodes
            })
        }
        
        if verbose:
            print(f"\n✅ Optimization Complete!")
            print(f"   Status: {solver_results.solver.termination_condition}")
            print(f"   Total Cost: €{total_cost:.2f}")
            print(f"   Solve Time: {solver_results.solver.time:.2f} seconds")
            
            # Battery utilization summary
            print(f"\n🔋 Battery Utilization:")
            for i in battery_nodes:
                total_charged = sum(pyo.value(model.P_ch[i, t]) * delta_t for t in timesteps)
                total_discharged = sum(pyo.value(model.P_dch[i, t]) * delta_t for t in timesteps)
                cycles = total_discharged / battery_specs[i]['capacity_kwh']
                print(f"   Node {i}: {total_charged:.1f} kWh charged, {total_discharged:.1f} kWh discharged ({cycles:.2f} cycles)")
        
        self.model = model
        self.results = battery_schedules
        
        return battery_schedules, total_cost, model
    
    def save_results(self, output_path: str, include_model: bool = False):
        """
        Save optimization results to CSV files.
        
        Parameters:
        -----------
        output_path : str
            Base path for output files (without extension)
        include_model : bool
            Save full Pyomo model to file (large)
        """
        if self.results is None:
            raise ValueError("No results to save. Run optimize() first.")
        
        for key, df in self.results.items():
            filepath = f"{output_path}_{key}.csv"
            df.to_csv(filepath, index=True)
            print(f"✓ Saved {key} to {filepath}")
        
        if include_model and self.model is not None:
            model_path = f"{output_path}_model.txt"
            self.model.pprint(filename=model_path)
            print(f"✓ Saved model to {model_path}")


def create_battery_specs_from_config(config: Dict) -> Dict[int, Dict[str, float]]:
    """
    Create battery specifications dictionary from config JSON.
    
    Parameters:
    -----------
    config : Dict
        Configuration dictionary from C3_single_supplier_rec_battery.json
    
    Returns:
    --------
    battery_specs : Dict[int, Dict[str, float]]
        Battery specifications for nodes {2, 6, 8}
    """
    battery_specs = {}
    
    # Check if prosumers have individual batteries
    has_individual_batteries = False
    for prosumer in config.get('prosumers', []):
        battery = prosumer.get('battery_storage', {})
        if battery:
            has_individual_batteries = True
            break
    
    if has_individual_batteries:
        # Extract individual battery specs from prosumers
        for prosumer in config.get('prosumers', []):
            node_id = int(prosumer.get('node_id'))
            battery = prosumer.get('battery_storage', {})
            
            if not battery:
                continue
            
            battery_specs[node_id] = {
                'capacity_kwh': battery.get('capacity_kwh', 10.0),
                'max_charge_kw': battery.get('max_charge_power_kw', 5.0),
                'max_discharge_kw': battery.get('max_discharge_power_kw', 5.0),
                'charge_efficiency': battery.get('charge_efficiency', 0.92),
                'discharge_efficiency': battery.get('discharge_efficiency', 0.92),
                'self_discharge_rate': battery.get('self_discharge_rate_per_hour', 0.002),
                'soc_min': battery.get('min_soc', 0.20),
                'soc_max': battery.get('max_soc', 1.00),
                'initial_soc': battery.get('initial_soc', 0.50)
            }
    else:
        # Use hardcoded heterogeneous battery specs for 3 nodes (as per LaTeX formulation)
        # Based on Table 3 from REC_BATTERY_OPTIMIZATION_METHODOLOGY.tex
        battery_specs = {
            2: {  # Node 2 - Fire Fighting Station (Large battery)
                'capacity_kwh': 40.0,
                'max_charge_kw': 20.0,
                'max_discharge_kw': 20.0,
                'charge_efficiency': 0.95,
                'discharge_efficiency': 0.95,
                'self_discharge_rate': 0.001,  # 0.1% per hour
                'soc_min': 0.10,
                'soc_max': 1.00,
                'initial_soc': 0.50
            },
            6: {  # Node 6 - Household (Medium battery)
                'capacity_kwh': 10.0,
                'max_charge_kw': 5.0,
                'max_discharge_kw': 5.0,
                'charge_efficiency': 0.92,
                'discharge_efficiency': 0.92,
                'self_discharge_rate': 0.002,  # 0.2% per hour
                'soc_min': 0.20,
                'soc_max': 1.00,
                'initial_soc': 0.50
            },
            8: {  # Node 8 - Household (Small battery)
                'capacity_kwh': 6.5,
                'max_charge_kw': 3.25,
                'max_discharge_kw': 3.25,
                'charge_efficiency': 0.90,
                'discharge_efficiency': 0.90,
                'self_discharge_rate': 0.003,  # 0.3% per hour
                'soc_min': 0.20,
                'soc_max': 1.00,
                'initial_soc': 0.50
            }
        }
    
    return battery_specs


if __name__ == "__main__":
    print("REC Battery Optimization - Heterogeneous Distributed Storage")
    print("=" * 70)
    print("This module implements MILP optimization for REC-level battery coordination.")
    print("\nUsage:")
    print("  from rec_battery_optimization_heterogeneous import RECBatteryOptimizer")
    print("  optimizer = RECBatteryOptimizer(config_path='C3_single_supplier_rec_battery.json')")
    print("  results, cost, model = optimizer.optimize(load_profiles, pv_profiles, ...)")
