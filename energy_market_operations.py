"""
EnergyMarketOperations - Sequential Energy Market & Community Settlement Pipeline
==================================================================================

A config-driven class that models the end-to-end operation of an energy supplier
participating in wholesale markets (day-ahead, intra-day, balancing) while
managing retail settlement with prosumers, consumers, and renewable energy
communities (RECs).

Every step is driven entirely by the JSON config file:
  - Suppliers, balancing groups, prosumers, consumers: from config
  - CSV file paths & column IDs for load/gen/prices: from config
  - REC membership & settlement rules: from config
  - Battery specs (optional): from config

The simulation models a sequential market operation:

  Prerequisites (data loading):
      load_config()              - Parse JSON, detect features (REC, battery)
      load_data()                - Load CSVs using paths & column IDs from config

  Main Pipeline (6 sequential market steps):
      i.    run_da_market()           - Day-Ahead Market: initial positions from DA forecasts
      ii.   run_id_market()           - Intra-Day Market: adjustments using updated forecasts
      ii-b  run_battery_optimization() - Battery Optimization: MILP schedule using ID forecasts [if battery]
      iii.  run_rec_settlement()      - Energy Community Settlement: internal REC sharing
      iv.   run_balancing_market()    - Balancing Market: scheduled vs actual settlement
      v.    run_supplier_billing()    - Supplier Billing: final settlement with REC members

  Analysis & Reporting:
      aggregate_to_monthly()     - Monthly rollup by supplier/BG
      calculate_profit_loss()    - Revenue, cost, margin analysis
      plot_financials()          - Financial overview charts
      plot_imbalances()          - Balancing group position charts
      summary()                  - Print annual financial summary

Usage:
    from rec_pipeline import EnergyMarketOperations

    pipe = EnergyMarketOperations("A1_single_supplier_no_rec.json")
    pipe.run_all()          # runs all 5 market steps + aggregation + P/L
    pipe.plot_financials()
    pipe.summary()
"""

import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import warnings

try:
    import pyomo.environ as pyo
    from pyomo.opt import SolverFactory
    PYOMO_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False

warnings.filterwarnings('ignore')


class EnergyMarketOperations:
    """
    Config-driven sequential energy market operations pipeline.

    All data loading, column mapping, and step sequencing is determined
    by the JSON configuration file.  No hardcoded column names or file paths.
    """

    # ------------------------------------------------------------------ #
    #  Construction & Config Loading                                       #
    # ------------------------------------------------------------------ #

    def __init__(self, config_path: str, scenario_name: str = None, data_root: str = None):
        """
        Parameters
        ----------
        config_path : str
            Path to the scenario JSON configuration file.
        scenario_name : str, optional
            Human-readable label (e.g. "A1", "B2_mixed").  If None, derived from filename.
        data_root : str, optional
            Root directory for resolving relative CSV paths in the config.
            If None, defaults to <config_dir>/..  (i.e. one level above the config).
        """
        self.config_path = Path(config_path).resolve()
        self.scenario_name = scenario_name or self.config_path.stem
        self.data_root = Path(data_root).resolve() if data_root else self.config_path.parent.parent

        # State populated by pipeline steps
        self.config: dict = {}
        self.es_data: dict = {}
        self.es_timeseries_df: pd.DataFrame = pd.DataFrame()
        self.customer_billing_df: pd.DataFrame = pd.DataFrame()
        self.es_monthly_df: pd.DataFrame = pd.DataFrame()
        self.es_monthly_analysis_df: pd.DataFrame = pd.DataFrame()
        self.corrected_load_df: pd.DataFrame = pd.DataFrame()
        self.corrected_gen_df: pd.DataFrame = pd.DataFrame()
        self.battery_schedule_df: pd.DataFrame = pd.DataFrame()

        # Feature flags – set by load_config()
        self.has_rec: bool = False
        self.has_battery: bool = False

    # ------------------------------------------------------------------ #
    #  Prerequisite – Load Configuration                                   #
    # ------------------------------------------------------------------ #

    def load_config(self):
        """Load JSON config and detect features (REC, battery)."""
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

        self.has_rec = len(self.config.get('recs', [])) > 0
        self.has_battery = 'battery_storage' in self.config or 'battery_optimization' in self.config

        cfg = self.config
        es = cfg.get('energy_system', {})
        print("=" * 80)
        print(f"  SCENARIO: {self.scenario_name}")
        print("=" * 80)
        print(f"  System  : {es.get('system_name', 'N/A')}")
        print(f"  Period  : {es.get('simulation_period', {}).get('start_date', '?')} → "
              f"{es.get('simulation_period', {}).get('end_date', '?')}")
        print(f"  Suppliers    : {len(cfg.get('suppliers', []))}")
        print(f"  Prosumers    : {len(cfg.get('prosumers', []))}")
        print(f"  Consumers    : {len(cfg.get('consumers', []))}")
        print(f"  RECs         : {len(cfg.get('recs', []))}  →  has_rec = {self.has_rec}")
        print(f"  Battery      : {self.has_battery}")
        print("=" * 80)
        return self

    # ------------------------------------------------------------------ #
    #  Prerequisite – Load Data (all paths & column IDs from config)        #
    # ------------------------------------------------------------------ #

    def load_data(self):
        """
        Load all CSV data files using paths and column IDs defined in the JSON config.

        Data loaded:
          - prices (DA, ID, imbalance, retail, feedin)
          - load_actual, res_actual
          - load_forecast_da, load_forecast_id  (per-member columns)
          - res_forecast_da, res_forecast_id    (per-member columns)
        """
        cfg = self.config
        root = self.data_root

        # --- Prices ---
        price_cfg = cfg['energy_market']['price_lists']
        prices_file = root / price_cfg['day_ahead_prices']['csv_file']
        prices_df = pd.read_csv(prices_file, parse_dates=['datetime'], index_col='datetime')
        print(f"✓ Prices loaded: {prices_df.shape}  from {prices_file.name}")

        # --- Actual metering ---
        # Resolve actual CSV paths from settlement_approach if present, else from member definitions
        settlement = cfg.get('settlement_approach', {}).get('metering', {})
        load_actual_file = settlement.get('load_actual')
        res_actual_file = settlement.get('res_actual')

        # Fallback: use first prosumer/consumer csv_file if settlement_approach not present
        if not load_actual_file:
            first_member = (cfg.get('consumers', []) + cfg.get('prosumers', []))[0]
            load_actual_file = first_member['load']['csv_file']
        if not res_actual_file:
            first_prosumer = cfg.get('prosumers', [{}])[0]
            res_actual_file = first_prosumer.get('res', {}).get('csv_file', load_actual_file)

        load_actual_df = pd.read_csv(root / load_actual_file, parse_dates=['datetime'], index_col='datetime')
        res_actual_df = pd.read_csv(root / res_actual_file, parse_dates=['datetime'], index_col='datetime')
        print(f"✓ Load actual : {load_actual_df.shape}")
        print(f"✓ RES actual  : {res_actual_df.shape}")

        # --- Build per-member forecast DataFrames from config ---
        load_forecast_da_df = pd.DataFrame()
        load_forecast_id_df = pd.DataFrame()
        res_forecast_da_df = pd.DataFrame()
        res_forecast_id_df = pd.DataFrame()

        # Consumer forecasts (load only)
        for consumer in cfg.get('consumers', []):
            load_def = consumer['load']
            member_id = load_def['id']

            da_file = root / load_def['load_forecast_da_file']
            da_df = pd.read_csv(da_file, index_col='datetime', parse_dates=['datetime'])
            if member_id in da_df.columns:
                load_forecast_da_df[member_id] = da_df[member_id]

            id_file = root / load_def['load_forecast_id_file']
            id_df = pd.read_csv(id_file, index_col='datetime', parse_dates=['datetime'])
            if member_id in id_df.columns:
                load_forecast_id_df[member_id] = id_df[member_id]

        # Prosumer forecasts (load + RES)
        for prosumer in cfg.get('prosumers', []):
            # Load forecast
            if 'load' in prosumer and prosumer['load']:
                load_def = prosumer['load']
                member_id = load_def['id']

                da_file = root / load_def['load_forecast_da_file']
                da_df = pd.read_csv(da_file, index_col='datetime', parse_dates=['datetime'])
                if member_id in da_df.columns:
                    load_forecast_da_df[member_id] = da_df[member_id]

                id_file = root / load_def['load_forecast_id_file']
                id_df = pd.read_csv(id_file, index_col='datetime', parse_dates=['datetime'])
                if member_id in id_df.columns:
                    load_forecast_id_df[member_id] = id_df[member_id]

            # RES forecast
            if 'res' in prosumer and prosumer['res']:
                res_def = prosumer['res']
                member_id = res_def['id']

                da_file = root / res_def['res_forecast_da_file']
                da_df = pd.read_csv(da_file, index_col='datetime', parse_dates=['datetime'])
                if member_id in da_df.columns:
                    res_forecast_da_df[member_id] = da_df[member_id]

                id_file = root / res_def['res_forecast_id_file']
                id_df = pd.read_csv(id_file, index_col='datetime', parse_dates=['datetime'])
                if member_id in id_df.columns:
                    res_forecast_id_df[member_id] = id_df[member_id]

        print(f"✓ Load forecast DA: {load_forecast_da_df.shape}")
        print(f"✓ RES  forecast DA: {res_forecast_da_df.shape}")
        print(f"✓ Load forecast ID: {load_forecast_id_df.shape}")
        print(f"✓ RES  forecast ID: {res_forecast_id_df.shape}")

        # --- Storage data (if battery scenario) ---
        storage_actual_df = pd.DataFrame()
        if self.has_battery:
            # Try to load storage actual data
            for prosumer in cfg.get('prosumers', []):
                if 'storage' in prosumer and prosumer['storage']:
                    storage_def = prosumer['storage']
                    storage_file = root / storage_def['csv_file']
                    if storage_file.exists():
                        storage_actual_df = pd.read_csv(
                            storage_file, parse_dates=['datetime'], index_col='datetime'
                        )
                        print(f"✓ Storage actual: {storage_actual_df.shape}")
                        break

        # Store everything
        self.es_data = {
            'prices': prices_df,
            'load_actual': load_actual_df,
            'res_actual': res_actual_df,
            'load_forecast_da': load_forecast_da_df,
            'res_forecast_da': res_forecast_da_df,
            'load_forecast_id': load_forecast_id_df,
            'res_forecast_id': res_forecast_id_df,
            'storage_actual': storage_actual_df,
        }
        return self

    # ------------------------------------------------------------------ #
    #  Helper: iterate over (supplier_id, bg_id) pairs from config         #
    # ------------------------------------------------------------------ #

    def _iter_balancing_groups(self):
        """Yield (supplier_id, bg_id, supplier_dict) for every BG in config."""
        for supplier in self.config['suppliers']:
            sid = supplier['supplier_id']
            for bg in supplier['balancing_groups']:
                yield sid, bg['balancing_group_id'], supplier

    def _aggregate_by_bg(self, load_df, gen_df):
        """
        Aggregate member-level load/gen DataFrames to BG level.

        Returns dict of  {bg_id: {'load': Series, 'gen': Series}}
        All column IDs come from the JSON config.
        """
        cfg = self.config
        result = {}

        for sid, bg_id, _ in self._iter_balancing_groups():
            bg_load = pd.Series(0.0, index=load_df.index)
            bg_gen = pd.Series(0.0, index=gen_df.index)

            # Prosumers
            for p in cfg.get('prosumers', []):
                if p['supplier']['supplier_id'] == sid and p['supplier']['balancing_group_id'] == bg_id:
                    if 'load' in p and p['load']:
                        lid = p['load']['id']
                        if lid in load_df.columns:
                            bg_load += load_df[lid]
                    if 'res' in p and p['res']:
                        gid = p['res']['id']
                        if gid in gen_df.columns:
                            bg_gen += gen_df[gid]

            # Consumers
            for c in cfg.get('consumers', []):
                if c['supplier']['supplier_id'] == sid and c['supplier']['balancing_group_id'] == bg_id:
                    lid = c['load']['id']
                    if lid in load_df.columns:
                        bg_load += load_df[lid]

            result[bg_id] = {'load': bg_load, 'gen': bg_gen, 'supplier_id': sid}

        return result

    def _correct_forecasts_for_rec_sharing(self, load_forecast_df, gen_forecast_df):
        """
        Apply anticipated REC sharing correction to forecast DataFrames.

        Mirrors run_rec_settlement() proportional sharing logic but uses
        forecast data instead of actuals.  For each REC, the anticipated
        shared energy is min(total_gen_forecast, total_load_forecast).
        Each member's forecast is proportionally reduced by their share.

        Returns corrected (load_forecast_df, gen_forecast_df) copies.
        """
        cfg = self.config
        corrected_load = load_forecast_df.copy()
        corrected_gen = gen_forecast_df.copy()

        for rec in cfg.get('recs', []):
            rec_id = rec['rec_id']

            # Gather member columns for this REC
            rec_load_cols = []
            rec_gen_cols = []

            for p in cfg.get('prosumers', []):
                if p.get('rec', '') == rec_id:
                    if 'res' in p and p['res'] and p['res']['id'] in gen_forecast_df.columns:
                        rec_gen_cols.append(p['res']['id'])
                    if 'load' in p and p['load'] and p['load']['id'] in load_forecast_df.columns:
                        rec_load_cols.append(p['load']['id'])

            for c in cfg.get('consumers', []):
                if c.get('rec', '') == rec_id:
                    lid = c['load']['id']
                    if lid in load_forecast_df.columns:
                        rec_load_cols.append(lid)

            if not rec_load_cols or not rec_gen_cols:
                continue

            # REC-level forecast totals
            gen_total = gen_forecast_df[rec_gen_cols].sum(axis=1)
            load_total = load_forecast_df[rec_load_cols].sum(axis=1)
            anticipated_shared = np.minimum(gen_total, load_total)

            # Proportional correction for load members
            for col in rec_load_cols:
                orig = load_forecast_df[col]
                frac = np.where(load_total > 0, orig / load_total, 0)
                corrected_load[col] = orig - frac * anticipated_shared

            # Proportional correction for gen members
            for col in rec_gen_cols:
                orig = gen_forecast_df[col]
                frac = np.where(gen_total > 0, orig / gen_total, 0)
                corrected_gen[col] = orig - frac * anticipated_shared

        return corrected_load, corrected_gen

    # ------------------------------------------------------------------ #
    #  Step (i) – Day-Ahead Market                                         #
    # ------------------------------------------------------------------ #

    def run_da_market(self):
        """
        Calculate day-ahead market commitments per balancing group.

        Reads:  config → prosumers/consumers → supplier/balancing_group mapping
                es_data → load_forecast_da, res_forecast_da, prices
        Writes: self.es_timeseries_df  (initial creation)
        """
        load_da = self.es_data['load_forecast_da']
        gen_da = self.es_data['res_forecast_da']
        prices = self.es_data['prices']

        # REC-aware forecasting: subtract anticipated REC sharing from forecasts
        rec_aware = self.config.get('settlement_approach', {}).get('rec_aware_forecasting', False)
        if rec_aware and self.has_rec:
            load_da, gen_da = self._correct_forecasts_for_rec_sharing(load_da, gen_da)
            print("  ✓ DA forecasts corrected for anticipated REC sharing")

        bg_agg = self._aggregate_by_bg(load_da, gen_da)
        da_price = prices['DA_price']

        frames = []
        for sid, bg_id, _ in self._iter_balancing_groups():
            agg = bg_agg[bg_id]
            net = agg['gen'] - agg['load']
            net_load = net.clip(upper=0).abs()
            net_gen = net.clip(lower=0)

            bg_df = pd.DataFrame({
                'datetime': load_da.index,
                'supplier_id': sid,
                'balancing_group_id': bg_id,
                'da_net_load_forecast_mwh': net_load.values,
                'da_net_gen_forecast_mwh': net_gen.values,
                'da_price_eur_per_mwh': da_price.values,
                'da_purchase_commitment_eur': (net_load * da_price).values,
                'da_sale_commitment_eur': (net_gen * da_price).values,
            })
            frames.append(bg_df)

        self.es_timeseries_df = pd.concat(frames, ignore_index=True)
        print(f"✓ DA market: {self.es_timeseries_df.shape}")
        return self

    # ------------------------------------------------------------------ #
    #  Step (ii) – Intra-Day Market                                        #
    # ------------------------------------------------------------------ #

    def run_id_market(self):
        """
        Calculate intra-day adjustments from DA commitments.

        Reads:  config, es_data → load_forecast_id, res_forecast_id, prices
        Writes: additional columns on self.es_timeseries_df
        """
        load_id = self.es_data['load_forecast_id']
        gen_id = self.es_data['res_forecast_id']
        prices = self.es_data['prices']

        # REC-aware forecasting: subtract anticipated REC sharing from forecasts
        rec_aware = self.config.get('settlement_approach', {}).get('rec_aware_forecasting', False)
        if rec_aware and self.has_rec:
            load_id, gen_id = self._correct_forecasts_for_rec_sharing(load_id, gen_id)
            print("  ✓ ID forecasts corrected for anticipated REC sharing")

        bg_agg = self._aggregate_by_bg(load_id, gen_id)

        id_price = prices['ID_price']

        id_frames = []
        for sid, bg_id, _ in self._iter_balancing_groups():
            agg = bg_agg[bg_id]

            # DA positions from es_timeseries_df
            da_data = self.es_timeseries_df[
                (self.es_timeseries_df['supplier_id'] == sid) &
                (self.es_timeseries_df['balancing_group_id'] == bg_id)
            ].set_index('datetime')

            # ID net position
            id_net = agg['gen'] - agg['load']
            id_net_load = id_net.clip(upper=0).abs()
            id_net_gen = id_net.clip(lower=0)

            # Adjustments (vectorized)
            da_nl = da_data['da_net_load_forecast_mwh']
            da_ng = da_data['da_net_gen_forecast_mwh']
            load_adj = id_net_load - da_nl
            gen_adj = id_net_gen - da_ng

            bg_df = pd.DataFrame({
                'datetime': load_id.index,
                'supplier_id': sid,
                'balancing_group_id': bg_id,
                'id_net_load_forecast_mwh': id_net_load.values,
                'id_net_gen_forecast_mwh': id_net_gen.values,
                'id_net_load_adjustment_mwh': load_adj.values,
                'id_net_gen_adjustment_mwh': gen_adj.values,
                'id_price_eur_per_mwh': id_price.values,
                'id_purchase_adjustment_eur': (load_adj * id_price).values,
                'id_sale_adjustment_eur': (gen_adj * id_price).values,
                'closing_net_load_forecast_mwh': (da_nl + load_adj).values,
                'closing_net_gen_forecast_mwh': (da_ng + gen_adj).values,
            })
            id_frames.append(bg_df)

        id_df = pd.concat(id_frames, ignore_index=True)
        merge_keys = ['datetime', 'supplier_id', 'balancing_group_id']
        drop_cols = [c for c in id_df.columns if c in self.es_timeseries_df.columns and c not in merge_keys]
        if drop_cols:
            id_df = id_df.drop(columns=drop_cols)

        self.es_timeseries_df = self.es_timeseries_df.merge(id_df, on=merge_keys, how='left')

        # Closing commitments
        self.es_timeseries_df['closing_purchase_commitment_eur'] = (
            self.es_timeseries_df['da_purchase_commitment_eur'] +
            self.es_timeseries_df['id_purchase_adjustment_eur']
        )
        self.es_timeseries_df['closing_sale_commitment_eur'] = (
            self.es_timeseries_df['da_sale_commitment_eur'] +
            self.es_timeseries_df['id_sale_adjustment_eur']
        )
        print(f"✓ ID market : {self.es_timeseries_df.shape}")
        return self

    # ------------------------------------------------------------------ #
    #  Step (ii-b) – Battery Optimization (optional, MILP on forecasts)    #
    # ------------------------------------------------------------------ #

    def run_battery_optimization(self):
        """
        Optimize battery charge/discharge schedule using MILP (Pyomo).

        Runs AFTER run_id_market() using ID forecasts for planning.
        Only runs when config has 'battery_storage' or 'battery_optimization'.

        Objective: Minimize total expected grid cost based on forecasted net load
            min Σ (grid_import[t] * retail_price[t] - grid_export[t] * feedin_price[t])

        Decision Variables:
            - charge[t]: Power charged to battery in period t (kW)
            - discharge[t]: Power discharged from battery in period t (kW)
            - soc[t]: State of charge at end of period t (kWh)
            - is_charging[t]: Binary variable for charge/discharge exclusion

        Constraints:
            - SOC bounds: soc_min <= soc[t] <= soc_max
            - Power limits: charge[t] <= P_max_charge, discharge[t] <= P_max_discharge
            - Energy balance: soc[t] = soc[t-1] + charge[t]*η_c*Δt - discharge[t]/η_d*Δt
            - No simultaneous charge/discharge (via binary)

        Reads:  config → battery_storage, battery_optimization
                es_data → load_forecast_id, res_forecast_id, prices (ID forecasts)
        Writes: self.battery_schedule_df (planned schedule)
                Updates es_timeseries_df with battery-adjusted forecasts
        """
        if not self.has_battery:
            print("✓ Battery optimization: SKIPPED (no battery in config)")
            return self

        if not PYOMO_AVAILABLE:
            print("⚠ Battery optimization: SKIPPED (pyomo not installed)")
            return self

        cfg = self.config
        battery_cfg = cfg.get('battery_storage', {})
        opt_cfg = cfg.get('battery_optimization', {})

        # Battery parameters
        capacity_kwh = battery_cfg.get('technical_parameters', {}).get('capacity_kwh', 200)
        max_charge_kw = battery_cfg.get('technical_parameters', {}).get('max_charge_power_kw', 50)
        max_discharge_kw = battery_cfg.get('technical_parameters', {}).get('max_discharge_power_kw', 50)
        eta_charge = battery_cfg.get('technical_parameters', {}).get('charging_efficiency', 0.95)
        eta_discharge = battery_cfg.get('technical_parameters', {}).get('discharging_efficiency', 0.95)
        soc_min_pct = battery_cfg.get('technical_parameters', {}).get('soc_min_percent', 20)
        soc_max_pct = battery_cfg.get('technical_parameters', {}).get('soc_max_percent', 100)
        initial_soc_pct = battery_cfg.get('technical_parameters', {}).get('initial_soc_percent', 50)

        soc_min = capacity_kwh * soc_min_pct / 100
        soc_max = capacity_kwh * soc_max_pct / 100
        initial_soc = capacity_kwh * initial_soc_pct / 100

        # Time parameters (assuming 15-min intervals = 0.25 hours)
        delta_t = 0.25  # hours

        # Use ID FORECASTS for battery planning (not actuals)
        load_forecast_id = self.es_data['load_forecast_id']
        res_forecast_id = self.es_data['res_forecast_id']
        prices = self.es_data['prices']

        # Aggregate forecasted load and generation
        total_load_forecast = load_forecast_id.sum(axis=1)
        total_gen_forecast = res_forecast_id.sum(axis=1)
        net_load_forecast = total_load_forecast - total_gen_forecast  # positive = import, negative = export

        # Align indices
        common_idx = net_load_forecast.index.intersection(prices.index)
        net_load_forecast = net_load_forecast.loc[common_idx]
        retail_price = prices.loc[common_idx, 'retail_price']
        feedin_price = prices.loc[common_idx, 'feedin_price']

        T = len(common_idx)
        time_periods = list(range(T))

        print(f"  Battery: {capacity_kwh} kWh, {max_charge_kw}/{max_discharge_kw} kW charge/discharge")
        print(f"  Optimizing over {T} time periods using ID forecasts...")

        # Build Pyomo model
        model = pyo.ConcreteModel(name="BatteryOptimization")

        # Sets
        model.T = pyo.Set(initialize=time_periods)

        # Parameters
        model.net_load_forecast = pyo.Param(model.T, initialize=dict(enumerate(net_load_forecast.values)))
        model.retail_price = pyo.Param(model.T, initialize=dict(enumerate(retail_price.values)))
        model.feedin_price = pyo.Param(model.T, initialize=dict(enumerate(feedin_price.values)))

        # Decision Variables
        model.charge = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, max_charge_kw))
        model.discharge = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(0, max_discharge_kw))
        model.soc = pyo.Var(model.T, domain=pyo.NonNegativeReals, bounds=(soc_min, soc_max))
        model.is_charging = pyo.Var(model.T, domain=pyo.Binary)

        # Auxiliary variables for grid interaction
        model.grid_import = pyo.Var(model.T, domain=pyo.NonNegativeReals)
        model.grid_export = pyo.Var(model.T, domain=pyo.NonNegativeReals)

        # Objective: Minimize expected total grid cost
        def objective_rule(m):
            return sum(
                m.grid_import[t] * m.retail_price[t] - m.grid_export[t] * m.feedin_price[t]
                for t in m.T
            )
        model.objective = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

        # Constraint: SOC dynamics
        def soc_balance_rule(m, t):
            if t == 0:
                return m.soc[t] == initial_soc + m.charge[t] * eta_charge * delta_t - m.discharge[t] / eta_discharge * delta_t
            else:
                return m.soc[t] == m.soc[t-1] + m.charge[t] * eta_charge * delta_t - m.discharge[t] / eta_discharge * delta_t
        model.soc_balance = pyo.Constraint(model.T, rule=soc_balance_rule)

        # Constraint: No simultaneous charge and discharge
        def no_simul_charge_rule(m, t):
            return m.charge[t] <= max_charge_kw * m.is_charging[t]
        model.no_simul_charge = pyo.Constraint(model.T, rule=no_simul_charge_rule)

        def no_simul_discharge_rule(m, t):
            return m.discharge[t] <= max_discharge_kw * (1 - m.is_charging[t])
        model.no_simul_discharge = pyo.Constraint(model.T, rule=no_simul_discharge_rule)

        # Constraint: Net load balance with battery
        # net_load_with_battery = net_load_forecast + charge - discharge
        # grid_import - grid_export = net_load_with_battery
        def net_balance_rule(m, t):
            net_load_with_battery = m.net_load_forecast[t] + m.charge[t] - m.discharge[t]
            return m.grid_import[t] - m.grid_export[t] == net_load_with_battery
        model.net_balance = pyo.Constraint(model.T, rule=net_balance_rule)

        # Solve
        solver_name = opt_cfg.get('solver', 'glpk')
        solver = SolverFactory(solver_name)

        if not solver.available():
            # Try CBC as fallback
            solver = SolverFactory('cbc')
            if not solver.available():
                print("⚠ Battery optimization: No MILP solver available (tried glpk, cbc)")
                return self

        print(f"  Solving with {solver_name}...")
        result = solver.solve(model, tee=False)

        if result.solver.termination_condition != pyo.TerminationCondition.optimal:
            print(f"⚠ Battery optimization: Solver did not find optimal solution ({result.solver.termination_condition})")
            return self

        # Extract results
        schedule_records = []
        for t in time_periods:
            schedule_records.append({
                'datetime': common_idx[t],
                'charge_kw': pyo.value(model.charge[t]),
                'discharge_kw': pyo.value(model.discharge[t]),
                'soc_kwh': pyo.value(model.soc[t]),
                'grid_import_kw': pyo.value(model.grid_import[t]),
                'grid_export_kw': pyo.value(model.grid_export[t]),
                'net_load_forecast_kw': net_load_forecast.iloc[t],
                'retail_price': retail_price.iloc[t],
                'feedin_price': feedin_price.iloc[t],
            })

        self.battery_schedule_df = pd.DataFrame(schedule_records)
        self.battery_schedule_df.set_index('datetime', inplace=True)

        # Calculate expected cost savings
        cost_without_battery = sum(
            max(0, net_load_forecast.iloc[t]) * retail_price.iloc[t] -
            max(0, -net_load_forecast.iloc[t]) * feedin_price.iloc[t]
            for t in time_periods
        )
        cost_with_battery = pyo.value(model.objective)
        savings = cost_without_battery - cost_with_battery

        # Update es_timeseries_df with battery-adjusted closing positions
        # Battery net effect: charge increases load, discharge reduces load
        battery_net_effect = self.battery_schedule_df['charge_kw'] - self.battery_schedule_df['discharge_kw']

        # Add battery columns to es_timeseries_df
        self.es_timeseries_df['battery_charge_kw'] = 0.0
        self.es_timeseries_df['battery_discharge_kw'] = 0.0
        self.es_timeseries_df['battery_soc_kwh'] = initial_soc

        for idx in self.es_timeseries_df.index:
            ts = self.es_timeseries_df.at[idx, 'datetime']
            if ts in self.battery_schedule_df.index:
                self.es_timeseries_df.at[idx, 'battery_charge_kw'] = self.battery_schedule_df.loc[ts, 'charge_kw']
                self.es_timeseries_df.at[idx, 'battery_discharge_kw'] = self.battery_schedule_df.loc[ts, 'discharge_kw']
                self.es_timeseries_df.at[idx, 'battery_soc_kwh'] = self.battery_schedule_df.loc[ts, 'soc_kwh']

        print(f"✓ Battery optimization: COMPLETE (using ID forecasts)")
        print(f"  Expected cost without battery: €{cost_without_battery:,.2f}")
        print(f"  Expected cost with battery   : €{cost_with_battery:,.2f}")
        print(f"  Expected savings             : €{savings:,.2f} ({100*savings/cost_without_battery:.1f}%)")
        print(f"  Total energy charged: {self.battery_schedule_df['charge_kw'].sum() * delta_t:.1f} kWh")
        print(f"  Total energy discharged: {self.battery_schedule_df['discharge_kw'].sum() * delta_t:.1f} kWh")

        # ── Apply battery effects to actual metered data ──────────────────
        # The battery physically operates behind the meter:
        #   Charging    → additional load at prosumer meters (draws power)
        #   Discharging → additional generation at prosumer meters (injects power)
        # Supplier forecasts remain UNCHANGED → structural imbalance deviation.
        # This models the REC cost-minimisation vs supplier imbalance paradox.
        prosumer_gen_cols = []
        prosumer_load_cols = []
        for p in cfg.get('prosumers', []):
            if 'res' in p and p['res']:
                gid = p['res']['id']
                if gid in self.es_data['res_actual'].columns:
                    prosumer_gen_cols.append(gid)
            if 'load' in p and p['load']:
                lid = p['load']['id']
                if lid in self.es_data['load_actual'].columns:
                    prosumer_load_cols.append(lid)

        if prosumer_gen_cols or prosumer_load_cols:
            gen_actual = self.es_data['res_actual']
            load_actual = self.es_data['load_actual']

            # Align battery schedule to actual data index
            batt_charge = self.battery_schedule_df['charge_kw'].reindex(
                gen_actual.index, fill_value=0.0)
            batt_discharge = self.battery_schedule_df['discharge_kw'].reindex(
                gen_actual.index, fill_value=0.0)

            # Distribute charge as additional load across prosumer nodes
            if prosumer_load_cols:
                total_load_pros = load_actual[prosumer_load_cols].sum(axis=1)
                load_shares = {}
                for col in prosumer_load_cols:
                    load_shares[col] = np.where(
                        total_load_pros > 0,
                        load_actual[col] / total_load_pros,
                        1.0 / len(prosumer_load_cols))
                for col in prosumer_load_cols:
                    load_actual[col] = load_actual[col] + batt_charge * load_shares[col]

            # Distribute discharge as additional generation across prosumer nodes
            if prosumer_gen_cols:
                total_gen_pros = gen_actual[prosumer_gen_cols].sum(axis=1)
                gen_shares = {}
                for col in prosumer_gen_cols:
                    gen_shares[col] = np.where(
                        total_gen_pros > 0,
                        gen_actual[col] / total_gen_pros,
                        1.0 / len(prosumer_gen_cols))
                for col in prosumer_gen_cols:
                    gen_actual[col] = gen_actual[col] + batt_discharge * gen_shares[col]

            print(f"  ✓ Battery effects applied to actual metered data")
            print(f"    (Supplier forecasts unchanged → structural imbalance deviation)")

        return self

    # ------------------------------------------------------------------ #
    #  Step (iii) – Energy Community Settlement (optional, config-driven)   #
    # ------------------------------------------------------------------ #

    def run_rec_settlement(self):
        """
        Calculate REC internal settlement and produce corrected meter readings.

        Only runs when config['recs'] is non-empty.

        Process per REC (from config):
          1. Identify members by checking prosumer/consumer 'rec' field
          2. Sum total generation & total load using column IDs from config
          3. shared_energy = min(total_gen, total_load)
          4. Proportionally reduce each member's meter by their share
          5. Store corrected_load_df and corrected_gen_df for downstream steps

        Reads:  config → recs, prosumers[].rec, consumers[].rec, load.id, res.id
                es_data → load_actual, res_actual
        Writes: self.corrected_load_df, self.corrected_gen_df
                additional columns on self.es_timeseries_df
        """
        if not self.has_rec:
            # No REC – corrected = original
            self.corrected_load_df = self.es_data['load_actual'].copy()
            self.corrected_gen_df = self.es_data['res_actual'].copy()
            print("✓ REC settlement: SKIPPED (no RECs in config)")
            return self

        cfg = self.config
        load_actual_df = self.es_data['load_actual']
        gen_actual_df = self.es_data['res_actual']

        # Build BG → REC mapping from member definitions
        bg_to_rec = {}
        for member in cfg.get('prosumers', []) + cfg.get('consumers', []):
            rec_id = member.get('rec', '')
            if rec_id:
                bg_to_rec[member['supplier']['balancing_group_id']] = rec_id

        # Initialize corrected DataFrames with original values
        corrected_load = load_actual_df.copy()
        corrected_gen = gen_actual_df.copy()

        # Initialize new columns
        self.es_timeseries_df['net_load'] = 0.0
        self.es_timeseries_df['rec_id'] = ''
        self.es_timeseries_df['internal_shared_energy_mwh'] = 0.0
        self.es_timeseries_df['corrected_net_load'] = 0.0

        # Compute original net_load per BG (vectorized)
        bg_agg_orig = self._aggregate_by_bg(load_actual_df, gen_actual_df)
        for sid, bg_id, _ in self._iter_balancing_groups():
            agg = bg_agg_orig[bg_id]
            bg_net_load = agg['load'] - agg['gen']
            mask = ((self.es_timeseries_df['supplier_id'] == sid) &
                    (self.es_timeseries_df['balancing_group_id'] == bg_id))
            ts_vals = self.es_timeseries_df.loc[mask, 'datetime']
            self.es_timeseries_df.loc[mask, 'net_load'] = bg_net_load.reindex(ts_vals).values

        # Process each REC defined in config
        for rec in cfg['recs']:
            rec_id = rec['rec_id']

            # Collect member column IDs for this REC
            rec_load_cols = []
            rec_gen_cols = []

            for p in cfg.get('prosumers', []):
                if p.get('rec', '') == rec_id:
                    if 'res' in p and p['res']:
                        gid = p['res']['id']
                        if gid in gen_actual_df.columns:
                            rec_gen_cols.append(gid)
                    if 'load' in p and p['load']:
                        lid = p['load']['id']
                        if lid in load_actual_df.columns:
                            rec_load_cols.append(lid)

            for c in cfg.get('consumers', []):
                if c.get('rec', '') == rec_id:
                    lid = c['load']['id']
                    if lid in load_actual_df.columns:
                        rec_load_cols.append(lid)

            # Vectorized REC totals
            gen_total = gen_actual_df[rec_gen_cols].sum(axis=1) if rec_gen_cols else pd.Series(0.0, index=gen_actual_df.index)
            load_total = load_actual_df[rec_load_cols].sum(axis=1) if rec_load_cols else pd.Series(0.0, index=load_actual_df.index)

            shared_energy = np.minimum(gen_total, load_total)

            # Proportional correction for load members
            for col in rec_load_cols:
                orig = load_actual_df[col]
                frac = np.where(load_total > 0, orig / load_total, 0)
                corrected_load[col] = orig - frac * shared_energy

            # Proportional correction for gen members
            for col in rec_gen_cols:
                orig = gen_actual_df[col]
                frac = np.where(gen_total > 0, orig / gen_total, 0)
                corrected_gen[col] = orig - frac * shared_energy

            # Update es_timeseries_df for BGs in this REC
            for sid, bg_id, _ in self._iter_balancing_groups():
                if bg_to_rec.get(bg_id, '') != rec_id:
                    continue

                # Gather member columns for this BG in this REC
                bg_load_cols = [lid for lid in rec_load_cols if lid in corrected_load.columns]
                bg_gen_cols = [gid for gid in rec_gen_cols if gid in corrected_gen.columns]

                # Filter to members in this specific BG
                bg_member_load = []
                bg_member_gen = []
                for p in cfg.get('prosumers', []):
                    if (p['supplier']['balancing_group_id'] == bg_id and p.get('rec', '') == rec_id):
                        if 'res' in p and p['res'] and p['res']['id'] in corrected_gen.columns:
                            bg_member_gen.append(p['res']['id'])
                        if 'load' in p and p['load'] and p['load']['id'] in corrected_load.columns:
                            bg_member_load.append(p['load']['id'])
                for c in cfg.get('consumers', []):
                    if (c['supplier']['balancing_group_id'] == bg_id and c.get('rec', '') == rec_id):
                        if c['load']['id'] in corrected_load.columns:
                            bg_member_load.append(c['load']['id'])

                orig_load_bg = load_actual_df[bg_member_load].sum(axis=1) if bg_member_load else pd.Series(0.0, index=load_actual_df.index)
                corr_load_bg = corrected_load[bg_member_load].sum(axis=1)  if bg_member_load else pd.Series(0.0, index=corrected_load.index)
                orig_gen_bg = gen_actual_df[bg_member_gen].sum(axis=1)     if bg_member_gen else pd.Series(0.0, index=gen_actual_df.index)
                corr_gen_bg = corrected_gen[bg_member_gen].sum(axis=1)     if bg_member_gen else pd.Series(0.0, index=corrected_gen.index)

                shared_load = orig_load_bg - corr_load_bg
                shared_gen = orig_gen_bg - corr_gen_bg
                shared_energy_bg = shared_load + shared_gen
                corrected_net_load_series = corr_load_bg - corr_gen_bg

                mask = ((self.es_timeseries_df['supplier_id'] == sid) &
                        (self.es_timeseries_df['balancing_group_id'] == bg_id))
                ts_vals = self.es_timeseries_df.loc[mask, 'datetime']
                self.es_timeseries_df.loc[mask, 'rec_id'] = rec_id
                self.es_timeseries_df.loc[mask, 'internal_shared_energy_mwh'] = shared_energy_bg.reindex(ts_vals).values
                self.es_timeseries_df.loc[mask, 'corrected_net_load'] = corrected_net_load_series.reindex(ts_vals).values

        self.corrected_load_df = corrected_load
        self.corrected_gen_df = corrected_gen
        print(f"✓ REC settlement: {len(cfg['recs'])} REC(s) processed")
        return self

    # ------------------------------------------------------------------ #
    #  Step (iv) – Balancing Market                                        #
    # ------------------------------------------------------------------ #

    def run_balancing_market(self):
        """
        Calculate balancing market positions and imbalance settlements.

        Uses corrected meter readings if REC settlement was applied,
        otherwise uses original actuals.  All column IDs from config.

        Reads:  config, corrected_load_df/corrected_gen_df (or load_actual/res_actual)
        Writes: additional columns on self.es_timeseries_df
        """
        # Use corrected meters if REC, else originals
        if self.has_rec and not self.corrected_load_df.empty:
            load_df = self.corrected_load_df
            gen_df = self.corrected_gen_df
        else:
            load_df = self.es_data['load_actual']
            gen_df = self.es_data['res_actual']

        prices = self.es_data['prices']
        bg_agg = self._aggregate_by_bg(load_df, gen_df)

        imb_price = prices['imbalance_price']

        bal_frames = []
        for sid, bg_id, _ in self._iter_balancing_groups():
            agg = bg_agg[bg_id]

            # ID closing position
            id_data = self.es_timeseries_df[
                (self.es_timeseries_df['supplier_id'] == sid) &
                (self.es_timeseries_df['balancing_group_id'] == bg_id)
            ].set_index('datetime')

            bg_actual = agg['load'] - agg['gen']
            bg_forecast = id_data['id_net_load_forecast_mwh'] - id_data['id_net_gen_forecast_mwh']
            imbalance = bg_actual - bg_forecast
            settlement = imbalance * imb_price
            penalty = settlement.clip(upper=0).abs()
            reward = settlement.clip(lower=0)

            bg_df = pd.DataFrame({
                'datetime': load_df.index,
                'supplier_id': sid,
                'balancing_group_id': bg_id,
                'actual_load_mwh': agg['load'].values,
                'actual_gen_mwh': agg['gen'].values,
                'balancing_group_actual_mwh': bg_actual.values,
                'balancing_group_forecast_mwh': bg_forecast.values,
                'imbalance_mwh': imbalance.values,
                'imbalance_price_eur_per_mwh': imb_price.values,
                'imbalance_penalty': penalty.values,
                'imbalance_reward': reward.values,
            })
            bal_frames.append(bg_df)

        bal_df = pd.concat(bal_frames, ignore_index=True)
        merge_keys = ['datetime', 'supplier_id', 'balancing_group_id']
        drop_cols = [c for c in bal_df.columns if c in self.es_timeseries_df.columns and c not in merge_keys]
        if drop_cols:
            bal_df = bal_df.drop(columns=drop_cols)

        self.es_timeseries_df = self.es_timeseries_df.merge(bal_df, on=merge_keys, how='left')
        print(f"✓ Balancing market: {self.es_timeseries_df.shape}")
        return self

    # ------------------------------------------------------------------ #
    #  Step (v) – Supplier Billing                                         #
    # ------------------------------------------------------------------ #

    def run_supplier_billing(self):
        """
        Final settlement between supplier and REC members (prosumers/consumers).

        Uses corrected meters if Energy Community Settlement was applied.
        Retail & feed-in price column names from supplier config.

        Reads:  config → prosumers, consumers, suppliers → retail_pricing, feedin_pricing
                es_data → prices
                corrected_load_df / corrected_gen_df (or originals)
        Writes: self.customer_billing_df
                merges retail aggregates into self.es_timeseries_df
        """
        cfg = self.config
        prices = self.es_data['prices']

        # Use corrected meters if REC, else originals
        if self.has_rec and not self.corrected_load_df.empty:
            load_df = self.corrected_load_df
            gen_df = self.corrected_gen_df
        else:
            load_df = self.es_data['load_actual']
            gen_df = self.es_data['res_actual']

        # Build supplier pricing lookup from config
        supplier_pricing = {}
        for sup in cfg['suppliers']:
            sid = sup['supplier_id']
            retail_col = sup['retail_pricing']['price']
            feedin_col = sup['feedin_pricing']['price']
            supplier_pricing[sid] = {
                'retail_price': prices[retail_col],
                'feedin_price': prices[feedin_col],
            }

        all_records = []

        # --- Prosumers ---
        for prosumer in cfg.get('prosumers', []):
            cid = prosumer['meter_id']
            sid = prosumer['supplier']['supplier_id']
            bg_id = prosumer['supplier']['balancing_group_id']
            sp = supplier_pricing[sid]

            # Generation from config column ID
            gen_id = prosumer['res']['id']
            actual_gen = gen_df[gen_id] if gen_id in gen_df.columns else pd.Series(0.0, index=gen_df.index)

            # Load from config column ID
            actual_load = pd.Series(0.0, index=gen_df.index)
            if 'load' in prosumer and prosumer['load']:
                load_id = prosumer['load']['id']
                if load_id in load_df.columns:
                    actual_load = load_df[load_id]

            net_load = actual_load - actual_gen
            grid_import = net_load.clip(lower=0)
            grid_export = (-net_load).clip(lower=0)

            sales_revenue = (grid_import * sp['retail_price']).abs()
            purchase_costs = (grid_export * sp['feedin_price']).abs()

            all_records.append(pd.DataFrame({
                'datetime': prices.index,
                'supplier_id': sid,
                'balancing_group_id': bg_id,
                'customer_id': cid,
                'customer_type': 'prosumer',
                'actual_load_mwh': actual_load.values,
                'actual_gen_mwh': actual_gen.values,
                'net_load_mwh': net_load.values,
                'retail_price_eur_per_mwh': sp['retail_price'].values,
                'feedin_price_eur_per_mwh': sp['feedin_price'].values,
                'sales_revenue_eur': sales_revenue.values,
                'purchase_costs_eur': purchase_costs.values,
            }))

        # --- Consumers ---
        for consumer in cfg.get('consumers', []):
            cid = consumer['meter_id']
            sid = consumer['supplier']['supplier_id']
            bg_id = consumer['supplier']['balancing_group_id']
            sp = supplier_pricing[sid]

            load_id = consumer['load']['id']
            actual_load = load_df[load_id] if load_id in load_df.columns else pd.Series(0.0, index=load_df.index)
            actual_gen = pd.Series(0.0, index=actual_load.index)

            sales_revenue = actual_load * sp['retail_price']
            purchase_costs = pd.Series(0.0, index=actual_load.index)

            all_records.append(pd.DataFrame({
                'datetime': prices.index,
                'supplier_id': sid,
                'balancing_group_id': bg_id,
                'customer_id': cid,
                'customer_type': 'consumer',
                'actual_load_mwh': actual_load.values,
                'actual_gen_mwh': actual_gen.values,
                'net_load_mwh': actual_load.values,
                'retail_price_eur_per_mwh': sp['retail_price'].values,
                'feedin_price_eur_per_mwh': sp['feedin_price'].values,
                'sales_revenue_eur': sales_revenue.values,
                'purchase_costs_eur': purchase_costs.values,
            }))

        self.customer_billing_df = pd.concat(all_records, ignore_index=True)

        # Merge retail aggregates into es_timeseries_df
        retail_bg = self.customer_billing_df.groupby(
            ['datetime', 'supplier_id', 'balancing_group_id']
        ).agg({
            'retail_price_eur_per_mwh': 'mean',
            'feedin_price_eur_per_mwh': 'mean',
            'sales_revenue_eur': 'sum',
            'purchase_costs_eur': 'sum',
        }).reset_index()

        # Drop existing retail columns to avoid _x/_y
        retail_cols_existing = [c for c in self.es_timeseries_df.columns
                                if c in ['retail_price_eur_per_mwh', 'feedin_price_eur_per_mwh',
                                         'sales_revenue_eur', 'purchase_costs_eur']]
        if retail_cols_existing:
            self.es_timeseries_df = self.es_timeseries_df.drop(columns=retail_cols_existing)

        self.es_timeseries_df = self.es_timeseries_df.merge(
            retail_bg,
            on=['datetime', 'supplier_id', 'balancing_group_id'],
            how='left'
        )
        print(f"✓ Customer billing: {self.customer_billing_df.shape}  "
              f"({self.customer_billing_df['customer_id'].nunique()} customers)")
        return self

    # ------------------------------------------------------------------ #
    #  Analysis – Monthly Aggregation                                      #
    # ------------------------------------------------------------------ #

    def aggregate_to_monthly(self):
        """Aggregate es_timeseries_df to monthly level by supplier/BG."""
        df = self.es_timeseries_df.copy()
        df['month_year'] = pd.to_datetime(df['datetime']).dt.strftime('%m-%Y')

        numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        agg_dict = {}
        for col in numeric:
            agg_dict[col] = 'mean' if 'price' in col.lower() else 'sum'

        self.es_monthly_df = (
            df.groupby(['month_year', 'supplier_id', 'balancing_group_id'])
              .agg(agg_dict)
              .reset_index()
              .rename(columns={'month_year': 'datetime'})
        )

        # Keep relevant columns
        keep = [
            'datetime', 'supplier_id', 'balancing_group_id',
            'da_net_load_forecast_mwh', 'da_net_gen_forecast_mwh',
            'da_purchase_commitment_eur', 'da_sale_commitment_eur',
            'id_net_load_adjustment_mwh', 'id_net_gen_adjustment_mwh', 'id_price_eur_per_mwh',
            'id_purchase_adjustment_eur', 'id_sale_adjustment_eur',
            'closing_purchase_commitment_eur', 'closing_sale_commitment_eur',
            'actual_load_mwh', 'actual_gen_mwh',
            'balancing_group_actual_mwh', 'balancing_group_forecast_mwh', 'imbalance_mwh',
            'imbalance_price_eur_per_mwh', 'imbalance_penalty', 'imbalance_reward',
            'retail_price_eur_per_mwh', 'feedin_price_eur_per_mwh',
            'sales_revenue_eur', 'purchase_costs_eur',
            'internal_shared_energy_mwh',
        ]
        keep = [c for c in keep if c in self.es_monthly_df.columns]
        self.es_monthly_df = self.es_monthly_df[keep]
        print(f"✓ Monthly aggregation: {self.es_monthly_df.shape}")
        return self

    # ------------------------------------------------------------------ #
    #  Analysis – Profit / Loss                                            #
    # ------------------------------------------------------------------ #

    def calculate_profit_loss(self):
        """Calculate supplier revenue, cost, and margin per month."""
        df = self.es_monthly_df.copy()

        # Revenue
        df['revenue_energy_market_sales_eur'] = df['closing_sale_commitment_eur']
        df['revenue_balancing_rewards_eur'] = df['imbalance_reward']
        df['revenue_retail_sales_eur'] = df['sales_revenue_eur']
        df['total_revenue_eur'] = (
            df['revenue_energy_market_sales_eur']
            + df['revenue_balancing_rewards_eur']
            + df['revenue_retail_sales_eur']
        )

        # Costs
        df['cost_energy_market_purchases_eur'] = df['closing_purchase_commitment_eur']
        df['cost_balancing_penalties_eur'] = df['imbalance_penalty']
        df['cost_retail_purchases_eur'] = df['purchase_costs_eur']
        df['total_costs_eur'] = (
            df['cost_energy_market_purchases_eur']
            + df['cost_balancing_penalties_eur']
            + df['cost_retail_purchases_eur']
        )

        df['profit_loss_eur'] = df['total_revenue_eur'] - df['total_costs_eur']

        self.es_monthly_analysis_df = df
        print(f"✓ Profit/loss calculated")
        return self

    # ------------------------------------------------------------------ #
    #  Reporting – Visualization                                           #
    # ------------------------------------------------------------------ #

    def _supplier_names(self):
        return {s['supplier_id']: s['supplier_name'] for s in self.config['suppliers']}

    def _supplier_bgs(self):
        """Return {supplier_id: [bg_id, ...]} mapping."""
        return {
            s['supplier_id']: [bg['balancing_group_id'] for bg in s['balancing_groups']]
            for s in self.config['suppliers']
        }

    def plot_financials(self, figsize=(18, 6)):
        """Plot financial overview (revenue / cost / profit) per supplier."""
        df = self.es_monthly_analysis_df
        supplier_names = self._supplier_names()
        supplier_bgs = self._supplier_bgs()
        supplier_ids = list(supplier_names.keys())
        n = len(supplier_ids)

        # Global limits
        fin_max = max(df['total_revenue_eur'].max(), df['total_costs_eur'].max(), df['profit_loss_eur'].max())
        fin_min = min(df['profit_loss_eur'].min(), 0)
        fin_lim = [fin_min * 1.1, fin_max * 1.1]

        fig, axes = plt.subplots(n, 2, figsize=(figsize[0], figsize[1] * n))
        if n == 1:
            axes = axes.reshape(1, -1)

        for idx, sid in enumerate(supplier_ids):
            sd = df[df['supplier_id'] == sid].sort_values('datetime')
            if sd.empty:
                continue
            bg_str = ', '.join(supplier_bgs.get(sid, []))
            label = f"{sid} / {bg_str} ({supplier_names[sid]})"
            x = range(len(sd))

            # Left: line chart
            ax = axes[idx, 0]
            ax.plot(x, sd['total_revenue_eur'], 'go-', lw=2.5, ms=8, label='Revenue')
            ax.plot(x, sd['total_costs_eur'], 'rs-', lw=2.5, ms=8, label='Costs')
            ax.plot(x, sd['profit_loss_eur'], 'b^--', lw=2.5, ms=8, label='Profit/Loss')
            ax.axhline(0, color='k', lw=0.5, alpha=0.3)
            ax.set_xticks(list(x))
            ax.set_xticklabels(sd['datetime'].values, rotation=45, ha='right')
            ax.set_title(f'{label} – Financial Overview ({self.scenario_name})', fontweight='bold')
            ax.set_ylabel('EUR')
            ax.legend()
            ax.grid(alpha=0.3)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'€{v:,.0f}'))
            ax.set_ylim(fin_lim)

            # Right: grouped bar (revenue components)
            ax2 = axes[idx, 1]
            bw = 0.25
            xp = np.arange(len(sd))
            for i, (col, lbl, clr) in enumerate([
                ('revenue_energy_market_sales_eur', 'Market Sales', '#27ae60'),
                ('revenue_balancing_rewards_eur', 'Balancing Rewards', '#f39c12'),
                ('revenue_retail_sales_eur', 'Retail Sales', '#3498db'),
            ]):
                ax2.bar(xp + (i - 1) * bw, sd[col].values, width=bw, label=lbl, color=clr, alpha=0.8)
            ax2.set_xticks(xp)
            ax2.set_xticklabels(sd['datetime'].values, rotation=45, ha='right')
            ax2.set_title(f'{label} – Revenue Components', fontweight='bold')
            ax2.set_ylabel('EUR')
            ax2.legend(fontsize=9)
            ax2.grid(alpha=0.3, axis='y')
            ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'€{v:,.0f}'))

        plt.tight_layout()
        plt.show()
        return self

    def plot_imbalances(self, figsize=(18, 6)):
        """Plot balancing group position & imbalance per supplier."""
        df = self.es_monthly_analysis_df
        supplier_names = self._supplier_names()
        supplier_bgs = self._supplier_bgs()
        supplier_ids = list(supplier_names.keys())
        n = len(supplier_ids)

        fig, axes = plt.subplots(n, 2, figsize=(figsize[0], figsize[1] * n))
        if n == 1:
            axes = axes.reshape(1, -1)

        for idx, sid in enumerate(supplier_ids):
            sd = df[df['supplier_id'] == sid].sort_values('datetime')
            if sd.empty:
                continue
            bg_str = ', '.join(supplier_bgs.get(sid, []))
            label = f"{sid} / {bg_str} ({supplier_names[sid]})"
            x = range(len(sd))

            # Left: BG actual vs forecast vs imbalance
            ax = axes[idx, 0]
            ax.plot(x, sd['balancing_group_actual_mwh'], 'ro-', lw=2.5, ms=8, alpha=0.9, label='BG Actual')
            ax.plot(x, sd['balancing_group_forecast_mwh'], 'gs-', lw=2.5, ms=8, alpha=0.6, label='BG Forecast')
            ax.plot(x, sd['imbalance_mwh'], 'b^--', lw=2.5, ms=8, alpha=0.9, label='Imbalance')
            ax.axhline(0, color='k', lw=1, alpha=0.7)
            ax.set_xticks(list(x))
            ax.set_xticklabels(sd['datetime'].values, rotation=45, ha='right')
            ax.set_title(f'{label} – BG Position & Imbalance ({self.scenario_name})', fontweight='bold')
            ax.set_ylabel('MWh')
            ax.legend()
            ax.grid(alpha=0.3)

            # Right: cost breakdown
            ax2 = axes[idx, 1]
            bw = 0.25
            xp = np.arange(len(sd))
            for i, (col, lbl, clr) in enumerate([
                ('cost_energy_market_purchases_eur', 'Market Purchases', '#e74c3c'),
                ('cost_balancing_penalties_eur', 'Balancing Penalties', '#8e44ad'),
                ('cost_retail_purchases_eur', 'Retail Purchases', '#e67e22'),
            ]):
                ax2.bar(xp + (i - 1) * bw, sd[col].values, width=bw, label=lbl, color=clr, alpha=0.8)
            ax2.set_xticks(xp)
            ax2.set_xticklabels(sd['datetime'].values, rotation=45, ha='right')
            ax2.set_title(f'{label} – Cost Components', fontweight='bold')
            ax2.set_ylabel('EUR')
            ax2.legend(fontsize=9)
            ax2.grid(alpha=0.3, axis='y')
            ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'€{v:,.0f}'))

        plt.tight_layout()
        plt.show()
        return self

    # ------------------------------------------------------------------ #
    #  Reporting – Summary                                                 #
    # ------------------------------------------------------------------ #

    def summary(self):
        """Print annual financial summary per supplier."""
        df = self.es_monthly_analysis_df
        supplier_names = self._supplier_names()

        print("\n" + "=" * 80)
        print(f"  ANNUAL FINANCIAL SUMMARY – {self.scenario_name.upper()}")
        print("=" * 80)

        for sid, sname in supplier_names.items():
            sd = df[df['supplier_id'] == sid]
            if sd.empty:
                continue

            print(f"\n  {sid} ({sname}):")
            print(f"\n    REVENUES:")
            print(f"      Energy Market Sales : €{sd['revenue_energy_market_sales_eur'].sum():>12,.2f}")
            print(f"      Balancing Rewards   : €{sd['revenue_balancing_rewards_eur'].sum():>12,.2f}")
            print(f"      Retail Sales        : €{sd['revenue_retail_sales_eur'].sum():>12,.2f}")
            print(f"      {'─' * 44}")
            print(f"      Total Revenue       : €{sd['total_revenue_eur'].sum():>12,.2f}")

            print(f"\n    COSTS:")
            print(f"      Market Purchases    : €{sd['cost_energy_market_purchases_eur'].sum():>12,.2f}")
            print(f"      Balancing Penalties  : €{sd['cost_balancing_penalties_eur'].sum():>12,.2f}")
            print(f"      Retail Purchases     : €{sd['cost_retail_purchases_eur'].sum():>12,.2f}")
            print(f"      {'─' * 44}")
            print(f"      Total Costs          : €{sd['total_costs_eur'].sum():>12,.2f}")

            print(f"\n    PROFIT/LOSS:")
            print(f"      Annual Total         : €{sd['profit_loss_eur'].sum():>12,.2f}")
            print(f"      Monthly Average      : €{sd['profit_loss_eur'].mean():>12,.2f}")

            if 'imbalance_mwh' in sd.columns:
                total_imb = sd['imbalance_mwh'].sum()
                pos = "SHORT" if total_imb > 0 else "LONG" if total_imb < 0 else "BALANCED"
                print(f"\n    IMBALANCE:")
                print(f"      System Position      : {pos}")
                print(f"      Total Imbalance      : {total_imb:>12,.2f} MWh")
                print(f"      BG Actual Position   : {sd['balancing_group_actual_mwh'].sum():>12,.2f} MWh")
                print(f"      BG Forecast Position : {sd['balancing_group_forecast_mwh'].sum():>12,.2f} MWh")

            if self.has_rec and 'internal_shared_energy_mwh' in sd.columns:
                print(f"\n    REC SHARING:")
                print(f"      Shared Energy        : {sd['internal_shared_energy_mwh'].sum():>12,.2f} MWh")

        print("\n" + "=" * 80)
        return self

    # ------------------------------------------------------------------ #
    #  Orchestrator                                                        #
    # ------------------------------------------------------------------ #

    # Backward-compatible method alias
    run_customer_billing = run_supplier_billing

    def run_all(self):
        """
        Execute the full sequential market pipeline:

          Prerequisites:  load_config → load_data
          (i)    Day-Ahead Market
          (ii)   Intra-Day Market
          (iii)  Energy Community Settlement  [skipped if no RECs]
          (iii-b) Battery Optimization        [skipped if no battery]
          (iv)   Balancing Market
          (v)    Supplier Billing
          Analysis: aggregate_to_monthly → calculate_profit_loss
        """
        print(f"\n{'━' * 80}")
        print(f"  Running full pipeline for: {self.scenario_name}")
        print(f"{'━' * 80}\n")

        # Prerequisites
        self.load_config()
        self.load_data()

        # Sequential market operations
        self.run_da_market()             # (i)    Day-Ahead Market
        self.run_id_market()             # (ii)   Intra-Day Market
        self.run_battery_optimization()  # (ii-b) Battery Optimization (uses forecasts)
        self.run_rec_settlement()        # (iii)  Energy Community Settlement
        self.run_balancing_market()      # (iv)   Balancing Market
        self.run_supplier_billing()      # (v)    Supplier Billing

        # Analysis & reporting
        self.aggregate_to_monthly()
        self.calculate_profit_loss()

        print(f"\n{'━' * 80}")
        print(f"  Pipeline complete: {self.scenario_name}")
        print(f"{'━' * 80}\n")
        return self


# Backward-compatible alias
RECPipeline = EnergyMarketOperations
