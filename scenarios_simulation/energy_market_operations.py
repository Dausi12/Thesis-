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
    from energy_market_operations import EnergyMarketOperations

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
        self.battery_schedules: dict = {}   # {battery_id: schedule_df} for multi-battery scenarios

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
        self.has_battery = (
            'batteries' in self.config
            or 'battery_storage' in self.config
            or 'battery_optimization' in self.config
        )

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

        # Helper to find column with flexible matching
        def find_column(member_id: str, df_columns: list) -> str | None:
            """Find column by exact match first, then try trimmed match."""
            if member_id in df_columns:
                return member_id
            # Try trimmed comparison
            member_stripped = member_id.strip()
            for col in df_columns:
                if col.strip() == member_stripped:
                    return col
            return None

        # Consumer forecasts (load only)
        for consumer in cfg.get('consumers', []):
            load_def = consumer['load']
            member_id = load_def['id']

            da_file = root / load_def['load_forecast_da_file']
            da_df = pd.read_csv(da_file, index_col='datetime', parse_dates=['datetime'])
            col = find_column(member_id, da_df.columns.tolist())
            if col:
                load_forecast_da_df[member_id] = da_df[col]
            else:
                print(f"  ⚠ Load forecast DA: column '{member_id}' not found")

            id_file = root / load_def['load_forecast_id_file']
            id_df = pd.read_csv(id_file, index_col='datetime', parse_dates=['datetime'])
            col = find_column(member_id, id_df.columns.tolist())
            if col:
                load_forecast_id_df[member_id] = id_df[col]
            else:
                print(f"  ⚠ Load forecast ID: column '{member_id}' not found")

        # Prosumer forecasts (load + RES)
        for prosumer in cfg.get('prosumers', []):
            # Load forecast
            if 'load' in prosumer and prosumer['load']:
                load_def = prosumer['load']
                member_id = load_def['id']

                da_file = root / load_def['load_forecast_da_file']
                da_df = pd.read_csv(da_file, index_col='datetime', parse_dates=['datetime'])
                col = find_column(member_id, da_df.columns.tolist())
                if col:
                    load_forecast_da_df[member_id] = da_df[col]
                else:
                    print(f"  ⚠ Load forecast DA: column '{member_id}' not found")

                id_file = root / load_def['load_forecast_id_file']
                id_df = pd.read_csv(id_file, index_col='datetime', parse_dates=['datetime'])
                col = find_column(member_id, id_df.columns.tolist())
                if col:
                    load_forecast_id_df[member_id] = id_df[col]
                else:
                    print(f"  ⚠ Load forecast ID: column '{member_id}' not found")

            # RES forecast
            if 'res' in prosumer and prosumer['res']:
                res_def = prosumer['res']
                member_id = res_def['id']

                da_file = root / res_def['res_forecast_da_file']
                da_df = pd.read_csv(da_file, index_col='datetime', parse_dates=['datetime'])
                col = find_column(member_id, da_df.columns.tolist())
                if col:
                    res_forecast_da_df[member_id] = da_df[col]
                else:
                    print(f"  ⚠ RES forecast DA: column '{member_id}' not found")

                id_file = root / res_def['res_forecast_id_file']
                id_df = pd.read_csv(id_file, index_col='datetime', parse_dates=['datetime'])
                col = find_column(member_id, id_df.columns.tolist())
                if col:
                    res_forecast_id_df[member_id] = id_df[col]
                else:
                    print(f"  ⚠ RES forecast ID: column '{member_id}' not found")

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

    # ------------------------------------------------------------------ #
    #  Step (i) – Day-Ahead Market                                         #
    # ------------------------------------------------------------------ #

    def run_da_market(self):
        """
        Calculate day-ahead market commitments per balancing group.

        Reads:  config → prosumers/consumers → supplier/balancing_group mapping
                es_data → load_forecast_da, res_forecast_da, prices
        Writes: self.es_timeseries_df  (initial creation)
        
        If forecast data is empty, falls back to using actual data.
        """
        load_da = self.es_data['load_forecast_da']
        gen_da = self.es_data['res_forecast_da']
        prices = self.es_data['prices']
        
        # Fallback: use actual data if forecasts are empty
        if load_da.empty:
            print("  ⚠ Using load_actual as DA forecast fallback")
            load_da = self.es_data['load_actual']
        if gen_da.empty:
            print("  ⚠ Using res_actual as DA forecast fallback") 
            gen_da = self.es_data['res_actual']

        bg_agg = self._aggregate_by_bg(load_da, gen_da)

        rows = []
        for sid, bg_id, _ in self._iter_balancing_groups():
            agg = bg_agg[bg_id]
            net = agg['gen'] - agg['load']
            net_load = net.clip(upper=0).abs()   # purchase
            net_gen = net.clip(lower=0)           # sale
            da_price = prices['DA_price']

            for ts in load_da.index:
                rows.append({
                    'datetime': ts,
                    'supplier_id': sid,
                    'balancing_group_id': bg_id,
                    'da_net_load_forecast_mwh': net_load.loc[ts],
                    'da_net_gen_forecast_mwh': net_gen.loc[ts],
                    'da_price_eur_per_mwh': da_price.loc[ts],
                    'da_purchase_commitment_eur': net_load.loc[ts] * da_price.loc[ts],
                    'da_sale_commitment_eur': net_gen.loc[ts] * da_price.loc[ts],
                })

        self.es_timeseries_df = pd.DataFrame(rows)
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
        
        If forecast data is empty, falls back to using actual data.
        """
        load_id = self.es_data['load_forecast_id']
        gen_id = self.es_data['res_forecast_id']
        prices = self.es_data['prices']
        
        # Fallback: use actual data if forecasts are empty
        if load_id.empty:
            print("  ⚠ Using load_actual as ID forecast fallback")
            load_id = self.es_data['load_actual']
        if gen_id.empty:
            print("  ⚠ Using res_actual as ID forecast fallback")
            gen_id = self.es_data['res_actual']

        bg_agg = self._aggregate_by_bg(load_id, gen_id)

        id_rows = []
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

            # Adjustments
            load_adj = id_net_load - da_data['da_net_load_forecast_mwh']
            gen_adj = id_net_gen - da_data['da_net_gen_forecast_mwh']
            id_price = prices['ID_price']

            for ts in load_id.index:
                id_rows.append({
                    'datetime': ts,
                    'supplier_id': sid,
                    'balancing_group_id': bg_id,
                    'id_net_load_forecast_mwh': id_net_load.loc[ts],
                    'id_net_gen_forecast_mwh': id_net_gen.loc[ts],
                    'id_net_load_adjustment_mwh': load_adj.loc[ts],
                    'id_net_gen_adjustment_mwh': gen_adj.loc[ts],
                    'id_price_eur_per_mwh': id_price.loc[ts],
                    'id_purchase_adjustment_eur': load_adj.loc[ts] * id_price.loc[ts],
                    'id_sale_adjustment_eur': gen_adj.loc[ts] * id_price.loc[ts],
                    'closing_net_load_forecast_mwh':
                        da_data['da_net_load_forecast_mwh'].loc[ts] + load_adj.loc[ts],
                    'closing_net_gen_forecast_mwh':
                        da_data['da_net_gen_forecast_mwh'].loc[ts] + gen_adj.loc[ts],
                })

        id_df = pd.DataFrame(id_rows)
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
        Gurobi LGS-style MILP battery optimization with 24-hour rolling windows.

        Supports both single-battery ('battery_storage' dict) and multi-battery
        ('batteries' list) config formats.  Each battery is optimised independently
        using the same shared load/generation forecasts and prices.

        Results are stored in:
          self.battery_schedules   – dict {battery_id: DataFrame} per-battery
          self.battery_schedule_df – aggregated (first battery for backward compat)
        """
        if not self.has_battery:
            print("⚠ Battery optimization: skipped (no battery in config)")
            return self

        try:
            import gurobipy as gp
            from gurobipy import GRB
        except Exception:
            print("⚠ Battery optimization: gurobipy not available")
            return self

        cfg = self.config
        opt_cfg = cfg.get('battery_optimization', {})

        # ── Normalise battery list (support both old dict and new list format) ──
        raw = cfg.get('batteries', cfg.get('battery_storage', {}))
        battery_list = raw if isinstance(raw, list) else [raw]

        # Rolling-window parameters (shared across all batteries)
        delta_t       = opt_cfg.get('delta_t_hours', 0.25)
        block_hours   = opt_cfg.get('block_hours', 24)
        block_periods = max(1, int(round(block_hours / delta_t)))

        # Load and generation forecasts (kept separate for the LGS energy balance)
        load_forecast_id = self.es_data.get('load_forecast_id', pd.DataFrame())
        res_forecast_id  = self.es_data.get('res_forecast_id',  pd.DataFrame())
        prices           = self.es_data.get('prices', pd.DataFrame())

        if load_forecast_id.empty and res_forecast_id.empty:
            print("⚠ Battery optimization: no ID forecasts available")
            return self

        total_load = load_forecast_id.sum(axis=1) if not load_forecast_id.empty else pd.Series(dtype=float)
        total_gen  = res_forecast_id.sum(axis=1)  if not res_forecast_id.empty  else pd.Series(dtype=float)

        common_idx = total_load.index.intersection(prices.index)
        if not res_forecast_id.empty:
            common_idx = common_idx.intersection(total_gen.index)
        if len(common_idx) == 0:
            print("⚠ Battery optimization: no overlapping index between forecasts and prices")
            return self

        load_full   = total_load.reindex(common_idx).fillna(0.0)
        gen_full    = total_gen.reindex(common_idx).fillna(0.0)
        retail_full = prices.loc[common_idx, 'retail_price']
        feedin_full = prices.loc[common_idx, 'feedin_price']
        T_full      = len(common_idx)

        print(f"  Rolling-horizon LGS battery optimization: "
              f"{len(battery_list)} batter{'y' if len(battery_list)==1 else 'ies'}, "
              f"block {block_hours}h ({block_periods} periods), total {T_full} periods")

        # ── Per-battery optimisation loop ─────────────────────────────────────
        self.battery_schedules = {}
        first_schedule_df = None

        for battery_cfg in battery_list:
            batt_id   = battery_cfg.get('battery_id', 'BESS_01')
            batt_name = battery_cfg.get('battery_name', batt_id)
            tech = battery_cfg.get('technical_parameters', {})

            capacity_kwh     = tech.get('capacity_kwh', 200)
            max_charge_kw    = tech.get('max_charge_power_kw', 50)
            max_discharge_kw = tech.get('max_discharge_power_kw', 50)
            eta_charge       = tech.get('charging_efficiency', 0.95)
            eta_discharge    = tech.get('discharging_efficiency', 0.95)
            soc_min          = capacity_kwh * tech.get('soc_min_percent', 20)  / 100.0
            soc_max          = capacity_kwh * tech.get('soc_max_percent', 100) / 100.0
            initial_soc      = capacity_kwh * tech.get('initial_soc_percent', 50) / 100.0

            print(f"    [{batt_id}] {batt_name}: "
                  f"{capacity_kwh} kWh, ±{max_charge_kw}/{max_discharge_kw} kW, "
                  f"SOC [{soc_min:.0f}–{soc_max:.0f}] kWh")

            schedule_records  = []
            prev_terminal_soc = initial_soc

            for block_start in range(0, T_full, block_periods):
                block_end  = min(block_start + block_periods, T_full)
                idx_slice  = common_idx[block_start:block_end]
                T          = len(idx_slice)
                if T == 0:
                    break

                rng      = list(range(T))
                load_b   = load_full.iloc[block_start:block_end].values
                gen_b    = gen_full.iloc[block_start:block_end].values
                retail_b = retail_full.iloc[block_start:block_end].values
                feedin_b = feedin_full.iloc[block_start:block_end].values

                m = gp.Model(f"LGS_{batt_id}_block_{block_start}")
                m.Params.OutputFlag = 1 if opt_cfg.get('verbose', False) else 0
                m.Params.TimeLimit  = opt_cfg.get('time_limit_seconds', 60)

                x_ch  = m.addVars(rng, lb=0.0, ub=max_charge_kw,    name="x_ch")
                x_dis = m.addVars(rng, lb=0.0, ub=max_discharge_kw,  name="x_dis")
                SoC   = m.addVars(rng, lb=soc_min, ub=soc_max,        name="SoC")
                P_imp = m.addVars(rng, lb=0.0,                         name="P_imp")
                P_exp = m.addVars(rng, lb=0.0,                         name="P_exp")
                b_ch  = m.addVars(rng, vtype=GRB.BINARY,               name="b_ch")

                m.addConstrs((x_ch[t]  <= max_charge_kw    * b_ch[t]       for t in rng), name="no_sim_ch")
                m.addConstrs((x_dis[t] <= max_discharge_kw * (1 - b_ch[t]) for t in rng), name="no_sim_dis")

                for t in rng:
                    soc_prev = prev_terminal_soc if t == 0 else SoC[t - 1]
                    m.addConstr(SoC[t] == soc_prev
                                + eta_charge * x_ch[t] * delta_t
                                - (1.0 / eta_discharge) * x_dis[t] * delta_t,
                                name=f"soc_{t}")

                for t in rng:
                    net_demand = float(load_b[t]) - float(gen_b[t])
                    m.addConstr(P_imp[t] - P_exp[t] + x_dis[t] - x_ch[t] == net_demand,
                                name=f"meter_{t}")

                m.addConstr(SoC[T - 1] >= prev_terminal_soc, name="terminal_soc")

                obj = gp.quicksum(
                    (float(retail_b[t]) * P_imp[t] - float(feedin_b[t]) * P_exp[t]) * delta_t
                    for t in rng
                )
                m.setObjective(obj, GRB.MINIMIZE)

                try:
                    m.optimize()
                except gp.GurobiError as e:
                    print(f"⚠ GurobiError [{batt_id}] block {block_start}: {e}")
                    for t in rng:
                        net = float(load_b[t]) - float(gen_b[t])
                        schedule_records.append({'datetime': idx_slice[t], 'charge_kw': 0.0,
                                                 'discharge_kw': 0.0, 'soc_kwh': prev_terminal_soc,
                                                 'grid_import_kw': max(0.0, net), 'grid_export_kw': max(0.0, -net)})
                    continue

                if m.Status not in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL):
                    print(f"⚠ Solver status {m.Status} [{batt_id}] block {block_start}")
                    for t in rng:
                        net = float(load_b[t]) - float(gen_b[t])
                        schedule_records.append({'datetime': idx_slice[t], 'charge_kw': 0.0,
                                                 'discharge_kw': 0.0, 'soc_kwh': prev_terminal_soc,
                                                 'grid_import_kw': max(0.0, net), 'grid_export_kw': max(0.0, -net)})
                    continue

                for t in rng:
                    schedule_records.append({
                        'datetime':      idx_slice[t],
                        'charge_kw':     float(x_ch[t].X),
                        'discharge_kw':  float(x_dis[t].X),
                        'soc_kwh':       float(SoC[t].X),
                        'grid_import_kw': float(P_imp[t].X),
                        'grid_export_kw': float(P_exp[t].X),
                    })
                prev_terminal_soc = float(SoC[T - 1].X)

            # Store per-battery schedule
            schedule_df = (
                pd.DataFrame(schedule_records)
                .set_index('datetime')
                .pipe(lambda df: df[~df.index.duplicated(keep='first')])
                .sort_index()
            )
            self.battery_schedules[batt_id] = schedule_df
            if first_schedule_df is None:
                first_schedule_df = schedule_df

            total_ch  = schedule_df['charge_kw'].sum()    * delta_t / 1000
            total_dis = schedule_df['discharge_kw'].sum() * delta_t / 1000
            print(f"    ✓ [{batt_id}] charge={total_ch:.1f} MWh, discharge={total_dis:.1f} MWh")

        # ── Backward-compatible aggregate DataFrame ────────────────────────────
        # battery_schedule_df = element-wise sum of all per-battery schedules
        if self.battery_schedules:
            agg = pd.concat(list(self.battery_schedules.values())).groupby(level=0).sum()
            self.battery_schedule_df = agg.sort_index()
        if first_schedule_df is not None and not first_schedule_df.empty:
            initial_soc_first = list(self.battery_schedules.values())[0]['soc_kwh'].iloc[0]
        else:
            initial_soc_first = 100.0

        # Merge aggregated battery into es_timeseries_df
        schedule_df = self.battery_schedule_df
        df_left = self.es_timeseries_df.copy()
        if 'datetime' in df_left.columns:
            merged = df_left.merge(
                schedule_df[['charge_kw', 'discharge_kw', 'soc_kwh']],
                left_on='datetime', right_index=True, how='left'
            )
            merged['battery_charge_kw']    = merged['charge_kw'].fillna(0.0)
            merged['battery_discharge_kw'] = merged['discharge_kw'].fillna(0.0)
            merged['battery_soc_kwh']      = merged['soc_kwh'].fillna(initial_soc_first)
            merged.drop(columns=[c for c in ['charge_kw', 'discharge_kw', 'soc_kwh']
                                  if c in merged.columns], inplace=True)
            self.es_timeseries_df = merged
        else:
            self.es_timeseries_df['battery_charge_kw']    = 0.0
            self.es_timeseries_df['battery_discharge_kw'] = 0.0
            self.es_timeseries_df['battery_soc_kwh']      = initial_soc_first
            for dt, row in schedule_df.iterrows():
                if dt in self.es_timeseries_df.index:
                    self.es_timeseries_df.at[dt, 'battery_charge_kw']    = row['charge_kw']
                    self.es_timeseries_df.at[dt, 'battery_discharge_kw'] = row['discharge_kw']
                    self.es_timeseries_df.at[dt, 'battery_soc_kwh']      = row['soc_kwh']

        total_charge_mwh    = schedule_df['charge_kw'].sum()    * delta_t / 1000
        total_discharge_mwh = schedule_df['discharge_kw'].sum() * delta_t / 1000
        print(f"✓ Battery optimization: COMPLETE "
              f"({len(self.battery_schedules)} batter{'y' if len(self.battery_schedules)==1 else 'ies'}, "
              f"LGS rolling {block_hours}h, "
              f"total charge={total_charge_mwh:.1f} MWh, discharge={total_discharge_mwh:.1f} MWh)")
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

        # Compute original net_load per BG
        bg_agg_orig = self._aggregate_by_bg(load_actual_df, gen_actual_df)
        for sid, bg_id, _ in self._iter_balancing_groups():
            agg = bg_agg_orig[bg_id]
            bg_net_load = agg['load'] - agg['gen']
            mask = ((self.es_timeseries_df['supplier_id'] == sid) &
                    (self.es_timeseries_df['balancing_group_id'] == bg_id))
            for idx in self.es_timeseries_df[mask].index:
                ts = self.es_timeseries_df.at[idx, 'datetime']
                self.es_timeseries_df.at[idx, 'net_load'] = bg_net_load.loc[ts]

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
                for idx in self.es_timeseries_df[mask].index:
                    ts = self.es_timeseries_df.at[idx, 'datetime']
                    self.es_timeseries_df.at[idx, 'rec_id'] = rec_id
                    self.es_timeseries_df.at[idx, 'internal_shared_energy_mwh'] = shared_energy_bg.loc[ts]
                    self.es_timeseries_df.at[idx, 'corrected_net_load'] = corrected_net_load_series.loc[ts]

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

        bal_rows = []
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
            imb_price = prices['imbalance_price']
            settlement = imbalance * imb_price
            penalty = settlement.apply(lambda x: abs(x) if x < 0 else 0)
            reward = settlement.apply(lambda x: x if x > 0 else 0)

            for ts in load_df.index:
                bal_rows.append({
                    'datetime': ts,
                    'supplier_id': sid,
                    'balancing_group_id': bg_id,
                    'actual_load_mwh': agg['load'].loc[ts],
                    'actual_gen_mwh': agg['gen'].loc[ts],
                    'balancing_group_actual_mwh': bg_actual.loc[ts],
                    'balancing_group_forecast_mwh': bg_forecast.loc[ts],
                    'imbalance_mwh': imbalance.loc[ts],
                    'imbalance_price_eur_per_mwh': imb_price.loc[ts],
                    'imbalance_penalty': penalty.loc[ts],
                    'imbalance_reward': reward.loc[ts],
                })

        bal_df = pd.DataFrame(bal_rows)
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

    def plot_financials(self, figsize=(18, 6)):
        """Plot financial overview (revenue / cost / profit) per supplier."""
        df = self.es_monthly_analysis_df
        supplier_names = self._supplier_names()
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
            label = f"{sid} ({supplier_names[sid]})"
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
        supplier_ids = list(supplier_names.keys())
        n = len(supplier_ids)

        fig, axes = plt.subplots(n, 2, figsize=(figsize[0], figsize[1] * n))
        if n == 1:
            axes = axes.reshape(1, -1)

        for idx, sid in enumerate(supplier_ids):
            sd = df[df['supplier_id'] == sid].sort_values('datetime')
            if sd.empty:
                continue
            label = f"{sid} ({supplier_names[sid]})"
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
