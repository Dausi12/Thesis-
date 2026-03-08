"""
Data Generator for SimBench Grid Data
=======================================
Generates consistent, reproducible randomized copies from SimBench profiles and local price data
for uniform supplier comparison.

Features:
- Converts SimBench normalized profiles to absolute MW values using nominal powers
- Generates Day-Ahead (DA) and Intraday (ID) forecasts with controlled randomization
- All timestamps are timezone-naive for consistency
- Supports load, renewable energy (RES), and storage profiles
"""

import pandas as pd
import numpy as np
import json
import os
import argparse
import sys
import warnings
import glob
from typing import Dict, Tuple, Optional

# Try to import simbench (only needed for generating new data)
try:
    import simbench as sb  # type: ignore
    SIMBENCH_AVAILABLE = True
except ImportError as e:
    print(f"Warning: simbench not available: {e}")
    print("Note: simbench is only needed for generating new data")
    SIMBENCH_AVAILABLE = False
    sb = None

# Suppress warnings
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=FutureWarning)

class Data:
    """
    Generates consistent, reproducible randomized copies from SimBench and local price data.
    
    This class handles:
    1. Loading SimBench grid profiles (load, RES, storage)
    2. Converting normalized profiles to absolute MW values
    3. Generating Day-Ahead (DA) and Intraday (ID) forecasts
    4. Processing local price data
    5. Resampling all data to 15-minute intervals
    6. Filtering to specific time ranges
    
    All timestamps are kept timezone-naive for consistency across datasets.
    
    Attributes:
        seed (int): Random seed for reproducibility
    """
    
    # Randomization ranges for different forecast types
    # Calibrated to empirical accuracy benchmarks (Okur et al., 2019):
    #   Load DA:  2–5% MAPE industry standard → ±5%  + deterministic 10 % upward bias
    #   Load ID:  <2% MAPE at 1–4 h ahead     → ±2%  (no bias — closer to gate closure)
    #   RES  DA:  25–40% RMSE at 24 h ahead   → ±35%
    #   RES  ID:  5–20% RMSE at 1–2 h ahead   → ±20% (residual cloud-cover uncertainty)
    #
    # Load DA upward bias rationale:
    #   Retailers/grid operators systematically over-forecast day-ahead load to avoid
    #   a short position (under-procurement).  The asymmetric cost structure of the
    #   Austrian APCS balancing mechanism penalises short positions more heavily than
    #   long positions, creating a rational incentive to bid slightly above the best
    #   point estimate.  The 10 % factor is consistent with empirical over-procurement
    #   margins reported in European intraday market studies (Pape et al., 2016;
    #   Garnier & Madlener, 2015).  Load ID forecasts carry no bias because by intraday
    #   gate closure the supplier has metered data and corrects back toward actuals.
    LOAD_DA_RANGE = (0.95, 1.05)    # Day-ahead load forecast: ±5% random noise
    LOAD_ID_RANGE = (0.98, 1.02)    # Intraday load forecast : ±2% random noise (no bias)
    RES_DA_RANGE  = (0.65, 1.35)    # Day-ahead RES forecast : ±35%
    RES_ID_RANGE  = (0.80, 1.20)    # Intraday RES forecast  : ±20%
    
    # Fixed price files will be loaded from CSV
    
    def __init__(self, seed: int = 42, simbench_code: Optional[str] = None, config_file: Optional[str] = None):
        """
        Initialize Data with a fixed seed for reproducibility.
        Deletes existing generated CSV files before initialization.
        
        Args:
            seed: Random seed for numpy random number generator
            simbench_code: Optional SimBench grid code to override config file setting
            config_file: Optional path to config file. If not provided, searches current directory
        """
        # Delete existing generated CSV files
        self._cleanup_existing_files()
        
        np.random.seed(seed)
        self.seed = seed
        self.simbench_code = simbench_code
        self.config_file = config_file or self._find_config_file()
    
    @staticmethod
    def _find_config_file() -> str:
        """
        Find config file in current directory or common locations.
        
        Returns:
            Path to config file
        
        Raises:
            FileNotFoundError: If no config file is found
        """
        # List of possible config file names to search for
        possible_names = [
            'data_config.json',
            'config.json',
            'randomizer_config.json'
        ]
        
        # Search in current directory
        for name in possible_names:
            if os.path.exists(name):
                print(f"Found config file: {name}")
                return name
        
        # If not found, return default and let it fail later with clear error
        return 'data_config.json'
    
    @staticmethod
    def _cleanup_existing_files():
        """
        Delete existing generated CSV files before creating new ones.
        Removes load, RES, storage, price, and time index files.
        """
        print("🗑️ Cleaning up existing generated files...")
        csv_patterns = [
            'load_*.csv',
            'res_*.csv', 
            'storage_*.csv',
            'prices.csv',
            'time_index.csv'
        ]
        
        deleted_count = 0
        for pattern in csv_patterns:
            for file in glob.glob(pattern):
                try:
                    os.remove(file)
                    deleted_count += 1
                    print(f"  Deleted: {file}")
                except Exception as e:
                    print(f"  Warning: Failed to delete {file}: {e}")
        
        if deleted_count > 0:
            print(f"✓ Deleted {deleted_count} files\n")
        else:
            print("✓ No existing files to delete\n")
    
    # ========================================================================
    # SIMBENCH DATA LOADING
    # ========================================================================
    
    def load_simbench_data(self, sb_code: str = '1-EHVHVMVLV-mixed-all-2-sw') -> Tuple[pd.DataFrame, pd.DataFrame, Optional[pd.DataFrame]]:
        """
        Load load, RES, and storage profiles from SimBench and convert to absolute MW.
        
        Args:
            sb_code: SimBench grid code (e.g., '1-EHVHVMVLV-mixed-all-2-sw')
        
        Returns:
            Tuple of (load_df, renewables_df, storage_df)
            storage_df is None if no storage exists in the model
        
        Raises:
            RuntimeError: If simbench is not available
        """
        if not SIMBENCH_AVAILABLE:
            raise RuntimeError(
                "simbench is required for loading new data. "
                "Please install: pip install simbench"
            )
        
        print(f"Loading Load + RES + Storage from SimBench '{sb_code}'...")
        
        # Fetch profiles from SimBench (converts to absolute MW)
        result = self.get_profiles(sb_code)
        if len(result) == 3:
            load_df, renewables_df, storage_df = result
        else:
            load_df, renewables_df = result
            storage_df = None
        
        # Parse time columns to naive datetime
        load_df = self._parse_time_column(load_df, 'load')
        renewables_df = self._parse_time_column(renewables_df, 'renewables')
        if storage_df is not None:
            storage_df = self._parse_time_column(storage_df, 'storage')
        
        # Print summary
        print(f"\nSimBench '{sb_code}' loaded and converted to absolute MW:")
        print(f"   Loads:   {len(load_df)} rows | {len(load_df.columns)-1} columns")
        print(f"   RES:     {len(renewables_df)} rows | {len(renewables_df.columns)-1} columns")
        if storage_df is not None:
            print(f"   Storage: {len(storage_df)} rows | {len(storage_df.columns)-1} columns")
        
        return load_df, renewables_df, storage_df
    
    def _parse_time_column(self, df: pd.DataFrame, df_type: str) -> pd.DataFrame:
        """
        Auto-detect and parse time column to timezone-naive datetime.
        
        Args:
            df: DataFrame with time column
            df_type: Type descriptor for logging (e.g., 'load', 'renewables')
        
        Returns:
            DataFrame with parsed 'time' column
        
        Raises:
            ValueError: If no time column found or parsing fails
        """
        # Check if DataFrame is empty
        if df.empty:
            print(f"   {df_type} DataFrame is empty, skipping time parsing")
            return df
        
        # Find time column (usually first column named 'time')
        time_col = df.columns[0] if df.columns[0] == 'time' else None
        
        if time_col is None:
            raise ValueError(f"No 'time' column found in {df_type}")
        
        # Show sample for debugging
        sample_time = df[time_col].iloc[0]
        print(f"   {df_type} sample time: '{sample_time}'")
        
        # Try multiple datetime formats
        formats_to_try = [
            '%d.%m.%Y %H:%M',           # 13.01.2016 00:00
            '%Y-%m-%dT%H:%M:%S.%f',     # 2016-06-27T00:00:00.000000000
            '%m/%d/%Y %H:%M',           # 01/13/2016 00:00
            'ISO8601'                    # Auto ISO parsing
        ]
        
        for fmt in formats_to_try:
            try:
                if fmt == 'ISO8601':
                    df['time'] = pd.to_datetime(df[time_col], utc=False).dt.tz_localize(None)
                else:
                    df['time'] = pd.to_datetime(df[time_col], format=fmt).dt.tz_localize(None)
                print(f"   {df_type} time parsed with format: {fmt}")
                break
            except:
                continue
        else:
            # Last resort: mixed format with day-first
            df['time'] = pd.to_datetime(df[time_col], format='mixed', dayfirst=True).dt.tz_localize(None)
            print(f"   {df_type} time parsed with: mixed format")
        
        print(f"   {df_type}: {len(df.columns)-1} columns (absolute MW)")
        return df
    
    @staticmethod
    def get_profiles(sb_code: str) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[pd.DataFrame]]:
        """
        Fetch load, renewable, and storage profiles from SimBench and convert to absolute MW.
        
        This method:
        1. Loads normalized profiles from SimBench
        2. Matches profiles with their nominal powers from the grid model
        3. Converts normalized values to absolute MW
        
        Args:
            sb_code: SimBench grid code
        
        Returns:
            Tuple of (load_df, res_df, storage_df) in absolute MW
            storage_df is None if no storage exists
        
        Raises:
            RuntimeError: If SimBench data cannot be fetched
        """
        if not SIMBENCH_AVAILABLE:
            raise RuntimeError(
                "simbench is required for fetching profiles. "
                "Please install: pip install simbench"
            )
        
        try:
            net = sb.get_simbench_net(sb_code)
            
            # Get normalized profiles
            load_profiles = pd.DataFrame(net.profiles['load'])
            res_profiles = pd.DataFrame(net.profiles['renewables'])
            
            print(f"Raw Load columns ({len(load_profiles.columns)}): {len(load_profiles.columns)}")
            print(f"Raw Renewables columns ({len(res_profiles.columns)}): {len(res_profiles.columns)}")
            
            # Check for storage profiles
            storage_profiles = None
            if 'storage' in net.profiles:
                storage_profiles = pd.DataFrame(net.profiles['storage'])
                print(f"Raw Storage columns ({len(storage_profiles.columns)}): {len(storage_profiles.columns)}")
            else:
                print("No storage profiles found in SimBench model")
            
            # === LOAD CONVERSION ===
            print("\nConverting normalized profiles to absolute MW...")
            # Each load unit operates independently with its own nominal power
            # Create individual columns for each load unit with profile name included
            load_df = load_profiles[['time']].copy()
            
            for idx, load_unit in net.load.iterrows():
                profile_name = load_unit['profile']
                unit_name = load_unit['name']
                p_mw = load_unit['p_mw']
                
                profile_col = f"{profile_name}_pload"
                if profile_col in load_profiles.columns:
                    # Create column with format: "unit_name [profile_name]"
                    column_name = f"{unit_name} [{profile_name}]"
                    load_df[column_name] = load_profiles[profile_col] * p_mw
            
            matched_load = len(net.load)
            print(f"  Load units: {matched_load} individual units converted to MW")
            
            # === RES CONVERSION ===
            # Each RES generator operates independently with its own nominal power
            # Create individual columns for each RES unit with profile name included
            res_df = res_profiles[['time']].copy()
            
            for idx, res_unit in net.sgen.iterrows():
                if 'profile' in net.sgen.columns:
                    profile_name = res_unit['profile']
                else:
                    profile_name = res_unit['name']
                
                unit_name = res_unit['name']
                p_mw = res_unit['p_mw']
                
                if profile_name in res_profiles.columns:
                    # Create column with format: "unit_name [profile_name]"
                    column_name = f"{unit_name} [{profile_name}]"
                    res_df[column_name] = res_profiles[profile_name] * p_mw
            
            matched_res = len(net.sgen)
            print(f"  RES units: {matched_res} individual generators converted to MW")
            
            # === STORAGE CONVERSION ===
            storage_df = None
            if storage_profiles is not None:
                # Each storage unit operates independently with its own nominal power
                # Create individual columns for each storage unit with profile name included
                storage_df = storage_profiles[['time']].copy()
                
                for idx, storage_unit in net.storage.iterrows():
                    if 'profile' in net.storage.columns:
                        profile_name = storage_unit['profile']
                    else:
                        profile_name = storage_unit['name']
                    
                    unit_name = storage_unit['name']
                    p_mw = storage_unit['p_mw']
                    
                    if profile_name in storage_profiles.columns:
                        # Create column with format: "unit_name [profile_name]"
                        column_name = f"{unit_name} [{profile_name}]"
                        storage_df[column_name] = storage_profiles[profile_name] * p_mw
                
                matched_storage = len(net.storage)
                print(f"  Storage units: {matched_storage} individual units converted to MW")
            
            print(f"✓ Profiles converted to absolute MW values")
            
            if storage_df is not None:
                return load_df, res_df, storage_df
            return load_df, res_df, None
            
        except Exception as e:
            print(f"Failed to fetch SimBench '{sb_code}': {e}", file=sys.stderr)
            raise RuntimeError(f"Failed to fetch SimBench data: {e}")
    
    # ========================================================================
    # PRICE DATA LOADING
    # ========================================================================
    
    def load_da_price_data(self, price_file: str) -> pd.DataFrame:
        """
        Load Day-Ahead price data with auto-detection of time format.
        
        Args:
            price_file: Path to CSV file containing DA price data
        
        Returns:
            DataFrame with 'datetime' index and 'DA_price' column (timezone-naive)
        
        Raises:
            FileNotFoundError: If price file doesn't exist
            ValueError: If required columns are missing or datetime parsing fails
        """
        print("Loading Day-Ahead price data...")
        
        # Check file existence
        if not os.path.exists(price_file):
            similar_files = glob.glob("energy-charts_*.csv")
            error_msg = f"Price file not found: {price_file}"
            if similar_files:
                error_msg += f"\n💡 Found similar files: {similar_files}"
                error_msg += f"\n   Update 'price_file' in config file to use one of these."
            raise FileNotFoundError(error_msg)
        
        # Load CSV
        price_df = pd.read_csv(price_file, encoding='utf-8-sig')
        print(f"Price file loaded: {len(price_df)} rows")
        print(f"   Available columns: {price_df.columns.tolist()}")
        
        # Find date and price columns (flexible column names)
        date_col = self._find_column(price_df, ['date', 'time', 'datetime'])
        price_col = self._find_column(price_df, ['price', 'spot', 'auction'])
        
        if date_col is None or price_col is None:
            raise ValueError(
                f"Could not find required columns. "
                f"Available: {price_df.columns.tolist()}"
            )
        
        print(f"   Using date column: '{date_col}' | price column: '{price_col}'")
        
        # Select and rename columns
        price_df = price_df[[date_col, price_col]].copy()
        price_df.columns = ['datetime', 'DA_price']
        
        # Handle DST transitions (2A/2B notation) BEFORE parsing
        price_df['datetime'] = price_df['datetime'].astype(str)
        price_df['datetime'] = price_df['datetime'].str.replace('2A:', '02:', regex=False)
        price_df['datetime'] = price_df['datetime'].str.replace('2B:', '03:', regex=False)
        
        # Parse datetime with auto-detection
        price_df['datetime'] = self._parse_datetime(price_df['datetime'])
        
        # Clean and sort
        price_df.set_index('datetime', inplace=True)
        price_df = price_df[~price_df.index.duplicated(keep='first')].sort_index()
        
        print(f"Day-Ahead Price loaded: {len(price_df)} rows")
        print(f"   📈 Range: {price_df['DA_price'].min():.1f} - {price_df['DA_price'].max():.1f} €/MWh")
        
        return price_df
    
    def generate_id_price_data(self, da_price_df: pd.DataFrame, id_range=None) -> pd.DataFrame:
        """
        Generate Intraday price data from Day-Ahead prices using tiered randomization.

        Applies scaling factors differentiated by time-to-delivery, reflecting the
        empirical convergence of intraday prices toward day-ahead prices as delivery
        approaches (Okur et al., 2019; Meinecke et al., 2020):

          - Hours  0–5  (4–6 h ahead): ±15% — maximum intraday price volatility
          - Hours  6–17 (2–4 h ahead): ±5%  — price discovery narrows
          - Hours 18–23 (1–2 h ahead): ±2%  — prices converge to day-ahead

        A flat fallback is supported for backward compatibility by passing a
        (min, max) tuple directly.

        Args:
            da_price_df: DataFrame with 'DA_price' column and datetime index
            id_range: Scaling configuration. Either:
                      - None (default): use literature-calibrated tiered ranges
                      - dict with keys 'tier_4h_6h', 'tier_2h_4h', 'tier_1h_2h',
                        each mapping to a [min, max] list or (min, max) tuple
                      - (min, max) tuple/list for flat single-range randomization

        Returns:
            DataFrame with 'ID_price' column and datetime index (timezone-naive)
        """
        # Literature-calibrated default tiers (Okur et al., 2019)
        DEFAULT_TIERS = {
            'tier_4h_6h': (0.85, 1.15),   # hours  0– 5: farthest from delivery
            'tier_2h_4h': (0.95, 1.05),   # hours  6–17: mid intraday window
            'tier_1h_2h': (0.98, 1.02),   # hours 18–23: closest to delivery
        }

        print("Generating Intraday prices from Day-Ahead prices (tiered scaling)...")

        id_prices = da_price_df['DA_price'].copy().astype(float)

        if id_range is None or isinstance(id_range, dict):
            # --- Tiered approach ---
            tiers = DEFAULT_TIERS.copy()
            if isinstance(id_range, dict):
                for key, val in id_range.items():
                    tiers[key] = tuple(val) if isinstance(val, list) else val

            hours = da_price_df.index.hour
            tier_map = [
                ((hours >= 0)  & (hours < 6),  'tier_4h_6h'),
                ((hours >= 6)  & (hours < 18), 'tier_2h_4h'),
                ((hours >= 18),                'tier_1h_2h'),
            ]
            for mask, tier_key in tier_map:
                lo, hi = tiers.get(tier_key, DEFAULT_TIERS[tier_key])
                n = int(mask.sum())
                if n > 0:
                    factors = np.random.uniform(lo, hi, size=n)
                    id_prices.values[mask] = da_price_df['DA_price'].values[mask] * factors

            t46 = tiers.get('tier_4h_6h', DEFAULT_TIERS['tier_4h_6h'])
            t24 = tiers.get('tier_2h_4h', DEFAULT_TIERS['tier_2h_4h'])
            t12 = tiers.get('tier_1h_2h', DEFAULT_TIERS['tier_1h_2h'])
            print(f"   Tiered scaling applied:")
            print(f"     Hours  0– 5 (4–6 h ahead): [{t46[0]:.2f}, {t46[1]:.2f}]")
            print(f"     Hours  6–17 (2–4 h ahead): [{t24[0]:.2f}, {t24[1]:.2f}]")
            print(f"     Hours 18–23 (1–2 h ahead): [{t12[0]:.2f}, {t12[1]:.2f}]")
        else:
            # --- Flat fallback (backward-compatible) ---
            lo, hi = tuple(id_range) if isinstance(id_range, list) else id_range
            factors = np.random.uniform(lo, hi, size=len(da_price_df))
            id_prices = da_price_df['DA_price'] * factors
            print(f"   Flat range: [{lo:.2f}, {hi:.2f}]")

        id_price_df = pd.DataFrame({'ID_price': id_prices.round(2)}, index=da_price_df.index)

        print(f"Intraday Price generated: {len(id_price_df)} rows")
        print(f"   📈 Range: {id_price_df['ID_price'].min():.1f} - {id_price_df['ID_price'].max():.1f} €/MWh")
        print(f"   Average ID/DA ratio: {(id_price_df['ID_price'] / da_price_df['DA_price']).mean():.4f}")

        return id_price_df
    
    @staticmethod
    def load_fixed_price(price_file: str, price_name: str) -> float:
        """
        Load fixed price from single-value CSV file.
        
        Args:
            price_file: Path to CSV file containing fixed price
            price_name: Name of the price (for logging)
        
        Returns:
            Fixed price value as float
        
        Raises:
            FileNotFoundError: If price file doesn't exist
            ValueError: If price value cannot be read
        """
        print(f"Loading {price_name}...")
        
        if not os.path.exists(price_file):
            raise FileNotFoundError(f"{price_name} file not found: {price_file}")
        
        # Load CSV
        price_df = pd.read_csv(price_file)
        
        # Get the price value (should be single row, single column or two columns with header)
        if len(price_df) != 1:
            raise ValueError(f"{price_name} file must contain exactly one data row")
        
        # Get the price value from first data column
        price_value = float(price_df.iloc[0, 0] if len(price_df.columns) == 1 else price_df.iloc[0, 1])
        
        print(f"   {price_name}: €{price_value:.2f}/MWh")
        
        return price_value
    
    def load_imbalance_price_data(self, price_file: str) -> pd.DataFrame:
        """
        Load imbalance price data with DST handling.
        
        The sign of the imbalance price indicates the system position:
        - Negative: Supply > Demand (generation penalized, consumption rewarded)
        - Positive: Supply < Demand (generation rewarded, consumption penalized)
        
        Args:
            price_file: Path to CSV file containing imbalance price data
        
        Returns:
            DataFrame with 'datetime' index and 'imbalance_price' column (timezone-naive)
        
        Raises:
            FileNotFoundError: If price file doesn't exist
            ValueError: If required columns are missing or datetime parsing fails
        """
        print("Loading Imbalance price data...")
        
        if not os.path.exists(price_file):
            raise FileNotFoundError(f"Imbalance price file not found: {price_file}")
        
        # Load CSV
        price_df = pd.read_csv(price_file, encoding='utf-8-sig')
        print(f"Imbalance price file loaded: {len(price_df)} rows")
        print(f"   Available columns: {price_df.columns.tolist()}")  
        
        # Find date and price columns
        date_col = self._find_column(price_df, ['date', 'time', 'datetime', 'from'])
        price_col = self._find_column(price_df, ['imbalance', 'price', 'final'])
        
        if date_col is None or price_col is None:
            raise ValueError(
                f"Could not find required columns. "
                f"Available: {price_df.columns.tolist()}"
            )
        
        print(f"   Using date column: '{date_col}' | price column: '{price_col}'")
        
        # Select and rename columns
        price_df = price_df[[date_col, price_col]].copy()
        price_df.columns = ['datetime', 'imbalance_price']
        
        # Parse datetime (handle DST notation if present)
        price_df['datetime'] = price_df['datetime'].astype(str)
        price_df['datetime'] = price_df['datetime'].str.replace('2A:', '02:', regex=False)
        price_df['datetime'] = price_df['datetime'].str.replace('2B:', '03:', regex=False)
        price_df['datetime'] = pd.to_datetime(price_df['datetime'], format='mixed')
        
        # Clean and sort
        price_df.set_index('datetime', inplace=True)
        price_df = price_df[~price_df.index.duplicated(keep='first')].sort_index()
        
        print(f"Imbalance Price loaded: {len(price_df)} rows")
        print(f"   📈 Range: {price_df['imbalance_price'].min():.1f} - {price_df['imbalance_price'].max():.1f} €/MWh")
        
        return price_df
    
    @staticmethod
    def _find_column(df: pd.DataFrame, keywords: list) -> Optional[str]:
        """Find column name containing any of the keywords (case-insensitive)."""
        for col in df.columns:
            if any(kw in col.lower() for kw in keywords):
                return col
        return None
    
    @staticmethod
    def _parse_datetime(datetime_series: pd.Series) -> pd.Series:
        """Parse datetime series with auto-detection, returning timezone-naive result."""
        sample_time = datetime_series.iloc[0]
        print(f"   Sample time: '{sample_time}'")
        
        # Try pandas auto-detection first (most flexible)
        try:
            result = pd.to_datetime(datetime_series, format='mixed')
            # Remove timezone if present
            if hasattr(result.dt, 'tz') and result.dt.tz is not None:
                result = result.dt.tz_localize(None)
            print(f"   Time parsed with format: mixed (auto-detect)")
            return result
        except Exception as e:
            print(f"   Mixed format failed: {e}")
        
        # Try specific formats
        formats_to_try = [
            '%Y-%m-%dT%H:%M:%z',      # 2016-01-01T00:00+02:00
            '%m/%d/%Y %H:%M',         # 06/27/2016 00:00 or 1/1/2016 0:00
            '%d.%m.%Y %H:%M',         # 27.06.2016 00:00
        ]
        
        for fmt in formats_to_try:
            try:
                result = pd.to_datetime(datetime_series, format=fmt)
                # Remove timezone if present
                if hasattr(result.dt, 'tz') and result.dt.tz is not None:
                    result = result.dt.tz_localize(None)
                print(f"   Time parsed with format: {fmt}")
                return result
            except:
                continue
        
        raise ValueError(f"Could not parse datetime format: '{sample_time}'")
    
    # ========================================================================
    # DATA RESAMPLING
    # ========================================================================
    
    def resample_to_15min(self, load_df: pd.DataFrame, res_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Resample load and RES data to 15-minute intervals.
        
        Args:
            load_df: Load DataFrame with 'time' column
            res_df: RES DataFrame with 'time' column
        
        Returns:
            Tuple of (load_15min, res_15min) with 'datetime' column
        """
        load_df.set_index('time', inplace=True)
        res_df.set_index('time', inplace=True)
        
        load_15min = load_df.resample('15T').mean().reset_index()
        res_15min = res_df.resample('15T').mean().reset_index()
        
        load_15min.rename(columns={'time': 'datetime'}, inplace=True)
        res_15min.rename(columns={'time': 'datetime'}, inplace=True)
        
        return load_15min, res_15min
    
    # ========================================================================
    # FORECAST GENERATION (DAY-AHEAD AND INTRADAY)
    # ========================================================================
    
    def randomize_load_da(self, load_df: pd.DataFrame, 
                          randomization_range: Optional[Tuple[float, float]] = None) -> pd.DataFrame:
        """
        Generate Day-Ahead load forecasts with controlled randomization and a
        deterministic 10 % upward bias applied on top of the random noise.

        The bias models the rational over-commitment behaviour of electricity
        retailers under the Austrian APCS single-price balancing mechanism:
        a short position (under-procurement) is penalised more heavily than a
        long position, so suppliers deliberately submit day-ahead bids that are
        slightly above their best point estimate.  The 10 % factor reflects
        empirical over-procurement margins in European markets (Pape et al.,
        2016; Garnier & Madlener, 2015).

        Load ID forecasts (randomize_load_updated) carry NO bias because by
        intraday gate closure the supplier has corrected metered data and
        can submit a forecast much closer to the anticipated actual.

        Args:
            load_df: Actual load DataFrame
            randomization_range: Optional (min, max) multipliers.
                                 Defaults to LOAD_DA_RANGE = (0.95, 1.05).

        Returns:
            DataFrame with randomized load forecasts (random noise ±5% × 1.10 upward bias)
        """
        if randomization_range is None:
            randomization_range = self.LOAD_DA_RANGE
        
        da_load = load_df.copy()
        load_cols = [col for col in da_load.columns if col != 'datetime']
        
        for col in load_cols:
            random_factors = np.random.uniform(*randomization_range, size=len(da_load))
            da_load[col] = (da_load[col] * random_factors * 1.1).round(6)  # 10% upward bias
        
        return da_load
    
    def randomize_load_updated(self, load_df: pd.DataFrame,
                               randomization_range: Optional[Tuple[float, float]] = None) -> pd.DataFrame:
        """
        Generate Intraday load forecasts (improved forecasts with tighter range).
        
        Args:
            load_df: Actual load DataFrame
            randomization_range: Optional (min, max) multipliers. Defaults to LOAD_ID_RANGE
        
        Returns:
            DataFrame with improved load forecasts
        """
        if randomization_range is None:
            randomization_range = self.LOAD_ID_RANGE
        
        updated_load = load_df.copy()
        load_cols = [col for col in updated_load.columns if col != 'datetime']
        
        for col in load_cols:
            random_factors = np.random.uniform(*randomization_range, size=len(updated_load))
            updated_load[col] = (updated_load[col] * random_factors).round(6)
        
        return updated_load
    
    def randomize_res_da(self, res_df: pd.DataFrame,
                         randomization_range: Optional[Tuple[float, float]] = None) -> pd.DataFrame:
        """
        Generate Day-Ahead RES forecasts with controlled randomization.
        
        Args:
            res_df: Actual RES DataFrame
            randomization_range: Optional (min, max) multipliers. Defaults to RES_DA_RANGE
        
        Returns:
            DataFrame with randomized RES forecasts
        """
        if randomization_range is None:
            randomization_range = self.RES_DA_RANGE
        
        da_res = res_df.copy()
        res_cols = [col for col in da_res.columns if col != 'datetime']
        
        for col in res_cols:
            if any(col.startswith(t) for t in ['PV', 'WP', 'BM', 'Hydro']):
                random_factors = np.random.uniform(*randomization_range, size=len(da_res))
                da_res[col] = (da_res[col] * random_factors).round(6)
        
        return da_res
    
    def randomize_res_updated(self, res_df: pd.DataFrame,
                             randomization_range: Optional[Tuple[float, float]] = None) -> pd.DataFrame:
        """
        Generate Intraday RES forecasts (improved forecasts with tighter range).
        
        Args:
            res_df: Actual RES DataFrame
            randomization_range: Optional (min, max) multipliers. Defaults to RES_ID_RANGE
        
        Returns:
            DataFrame with improved RES forecasts
        """
        if randomization_range is None:
            randomization_range = self.RES_ID_RANGE
        
        updated_res = res_df.copy()
        res_cols = [col for col in updated_res.columns if col != 'datetime']
        
        for col in res_cols:
            random_factors = np.random.uniform(*randomization_range, size=len(updated_res))
            updated_res[col] = (updated_res[col] * random_factors).round(6)
        
        return updated_res


    # ========================================================================
    # PRICE COMBINATION
    # ========================================================================
    
    def combine_prices(self, da_df: pd.DataFrame, id_df: pd.DataFrame, 
                      imbalance_df: pd.DataFrame, retail_price: float, feedin_price: float) -> pd.DataFrame:
        """
        Combine DA, ID, and imbalance prices with fixed retail and feed-in prices.
        
        Creates unified price DataFrame with:
        - DA_price: Day-Ahead market price (€/MWh)
        - ID_price: Intraday market price (€/MWh)
        - imbalance_price: System imbalance price (€/MWh)
          * Negative: Supply > Demand (generation penalized, consumption rewarded)
          * Positive: Supply < Demand (generation rewarded, consumption penalized)
        - retail_price: Fixed retail electricity price (€/MWh)
        - feedin_price: Fixed feed-in tariff for prosumer exports (€/MWh)
        
        Args:
            da_df: DataFrame with 'DA_price' column
            id_df: DataFrame with 'ID_price' column
            imbalance_df: DataFrame with 'imbalance_price' column
            retail_price: Fixed retail price in €/MWh
            feedin_price: Fixed feed-in price in €/MWh
        
        Returns:
            DataFrame with all price types, indexed by datetime
        """
        print("\nCombining all prices...")
        
        # Merge all price data on datetime index
        prices = da_df[['DA_price']].copy()
        prices = prices.join(id_df[['ID_price']], how='outer')
        prices = prices.join(imbalance_df[['imbalance_price']], how='outer')
        
        # Add fixed retail and feed-in prices
        prices['retail_price'] = retail_price
        prices['feedin_price'] = feedin_price
        
        # Forward fill missing values and drop any remaining NaN rows
        prices = prices.fillna(method='ffill').dropna()
        
        # Round all prices to 2 decimal places
        for col in prices.columns:
            prices[col] = prices[col].round(2)
        
        print(f"Combined prices: {len(prices)} rows")
        print(f"   DA_price range: {prices['DA_price'].min():.2f} - {prices['DA_price'].max():.2f} €/MWh")
        print(f"   ID_price range: {prices['ID_price'].min():.2f} - {prices['ID_price'].max():.2f} €/MWh")
        print(f"   Imbalance range: {prices['imbalance_price'].min():.2f} - {prices['imbalance_price'].max():.2f} €/MWh")
        print(f"   Retail (fixed): {retail_price:.2f} €/MWh")
        print(f"   Feed-in (fixed): {feedin_price:.2f} €/MWh")
        
        return prices.reset_index()
    
    # ========================================================================
    # TIME FILTERING
    # ========================================================================
    
    def filter_time_range(self, dfs: Dict[str, pd.DataFrame], 
                         start_time: str, end_time: str) -> Tuple[Dict[str, pd.DataFrame], pd.DatetimeIndex]:
        """
        Filter all DataFrames to the same time range with 15-minute intervals.
        
        All timestamps are converted to timezone-naive before filtering.
        Missing timestamps are forward-filled and remaining gaps filled with zeros.
        
        Args:
            dfs: Dictionary of DataFrames to filter (must have 'datetime' column)
            start_time: Start time string (e.g., '2016-01-01')
            end_time: End time string (e.g., '2016-12-31')
        
        Returns:
            Tuple of (filtered_dfs, time_range)
        """
        # Create naive time range
        start = pd.to_datetime(start_time).tz_localize(None)
        end = pd.to_datetime(end_time).tz_localize(None)
        time_range = pd.date_range(start=start, end=end, freq='15T')
        
        filtered_dfs = {}
        for name, df in dfs.items():
            # Ensure datetime column is timezone-naive
            df = df.copy()
            df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
            
            # Filter and reindex
            df_filtered = df[(df['datetime'] >= start) & (df['datetime'] <= end)].copy()
            df_filtered = (df_filtered.set_index('datetime')
                          .reindex(time_range)
                          .ffill()
                          .fillna(0)
                          .reset_index())
            df_filtered.rename(columns={'index': 'datetime'}, inplace=True)
            filtered_dfs[name] = df_filtered
        
        print(f"Filtered to {len(time_range)} 15-minute intervals: {start} to {end} (NAIVE)")
        return filtered_dfs, time_range
    
    # ========================================================================
    # MAIN GENERATION FUNCTION
    # ========================================================================
    
    def generate_consistent_copies(self) -> Tuple[Dict[str, pd.DataFrame], pd.DatetimeIndex]:
        """
        Main function: Generate ALL consistent copies from SimBench + local prices.
        
        Process:
        1. Load configuration
        2. Load SimBench data (load, RES, storage)
        3. Load local price data
        4. Resample all to 15-minute intervals
        5. Generate Day-Ahead (DA) forecasts
        6. Generate Intraday (ID) forecasts
        7. Generate price variants
        8. Filter to specified time range
        9. Save all to CSV files
        
        Returns:
            Tuple of (filtered_dfs, time_range)
        """
        # Load configuration
        with open(self.config_file, 'r') as f:
            config = json.load(f)
        
        # Use instance simbench_code if provided, otherwise use config file value
        if self.simbench_code is not None:
            sb_code = self.simbench_code
            print(f"Using SimBench code from instance: '{sb_code}'")
        else:
            sb_code = config.get('simbench_code', '1-EHVHVMVLV-mixed-all-2-sw')
            print(f"Using SimBench code from config: '{sb_code}'")
        
        # Price file paths
        da_price_file = config.get('da_price_file', 'original/Day Ahead Preise_M15_2016.csv')
        imbalance_price_file = config.get('imbalance_price_file', 'original/imbalance_prices.csv')
        retail_price_file = config.get('retail_price_file', 'original/retail_price.csv')
        feedin_price_file = config.get('feedin_price_file', 'original/feedin_price.csv')
        
        # ID price generation range: tiered dict (default) or flat tuple
        id_price_range = config.get('id_price_range', None)
        if isinstance(id_price_range, list):
            # Flat fallback: [min, max] list → tuple
            id_price_range = tuple(id_price_range)
        elif isinstance(id_price_range, dict):
            # Tiered: convert any list values to tuples
            id_price_range = {k: tuple(v) if isinstance(v, list) else v
                              for k, v in id_price_range.items()}
        # None → generate_id_price_data uses literature-calibrated defaults
        
        start_time = config['start_time']
        end_time = config['end_time']
        output_dir = config.get('output_dir', '.')
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n{'='*80}")
        print(f"GENERATING CONSISTENT DATA SEQUENCE")
        print(f"{'='*80}")
        
        # === STEP 1: Load SimBench data ===
        load_orig, res_orig, storage_orig = self.load_simbench_data(sb_code)
        
        # === STEP 2: Load all price data ===
        print("\n" + "="*80)
        print("LOADING PRICE DATA")
        print("="*80)
        da_price = self.load_da_price_data(da_price_file)
        id_price = self.generate_id_price_data(da_price, id_price_range)
        imbalance_price = self.load_imbalance_price_data(imbalance_price_file)
        retail_price = self.load_fixed_price(retail_price_file, "Retail Price")
        feedin_price = self.load_fixed_price(feedin_price_file, "Feed-in Price")
        
        # === STEP 3: Resample to 15-minute intervals ===
        print("\nResampling to 15-minute intervals...")
        load_15min, res_15min = self.resample_to_15min(load_orig, res_orig)
        
        if storage_orig is not None:
            # Convert 'time' column to datetime before resampling
            storage_orig['time'] = pd.to_datetime(storage_orig['time'])
            storage_orig.set_index('time', inplace=True)
            storage_15min = storage_orig.resample('15T').mean().reset_index()
            storage_15min.rename(columns={'time': 'datetime'}, inplace=True)
        else:
            storage_15min = None
        
        # === STEP 4: Generate Day-Ahead forecasts ===
        print("Generating Day-Ahead forecasts...")
        load_da = self.randomize_load_da(load_15min)
        res_da = self.randomize_res_da(res_15min)
        
        # === STEP 5: Generate Intraday forecasts ===
        print("Generating Intraday forecasts...")
        load_id = self.randomize_load_updated(load_15min)
        res_id = self.randomize_res_updated(res_15min)
        
        # === STEP 6: Combine all prices ===
        prices_all = self.combine_prices(da_price, id_price, imbalance_price, retail_price, feedin_price)
        
        # === STEP 7: Combine all datasets ===
        dfs = {
            'load_actual': load_15min,
            'load_forecast_da': load_da,
            'load_forecast_id': load_id,
            'res_actual': res_15min,
            'res_forecast_da': res_da,
            'res_forecast_id': res_id,
            'prices': prices_all
        }
        
        # Add storage if available
        if storage_15min is not None:
            print("Generating storage forecasts...")
            storage_da = self.randomize_res_da(storage_15min)
            storage_id = self.randomize_res_updated(storage_15min)
            dfs['storage_actual'] = storage_15min
            dfs['storage_forecast_da'] = storage_da
            dfs['storage_forecast_id'] = storage_id
        
        # === STEP 8: Filter to time range ===
        print("\nFiltering to specified time range...")
        filtered_dfs, time_range = self.filter_time_range(dfs, start_time, end_time)
        
        # === STEP 9: Save to CSV ===
        print("\nSaving CSV files...")
        for name, df in filtered_dfs.items():
            filename = f"{name}.csv"
            filepath = os.path.join(output_dir, filename)
            df.to_csv(filepath, index=False)
            print(f"   💾 Saved: {filename} ({len(df)} rows)")
        
        # Print summary
        print(f"\n{'='*80}")
        print(f"🎉 COMPLETE DATA SEQUENCE GENERATED!")
        print(f"{'='*80}")
        print(f"   📊 SimBench: '{sb_code}'")
        print(f"   💰 DA Price: '{da_price_file}'")
        if isinstance(id_price_range, dict):
            range_str = ", ".join(f"{k}: [{v[0]:.2f}-{v[1]:.2f}]" for k, v in id_price_range.items())
            print(f"   💰 ID Price: Generated from DA (tiered: {range_str})")
        elif id_price_range is not None:
            print(f"   💰 ID Price: Generated from DA (range: {id_price_range[0]:.2f}-{id_price_range[1]:.2f})")
        else:
            print(f"   💰 ID Price: Generated from DA (default literature-calibrated ranges)")
        print(f"   💰 Imbalance: '{imbalance_price_file}'")
        print(f"   💰 Retail: Fixed price from '{retail_price_file}'")
        print(f"   💰 Feed-in: Fixed price from '{feedin_price_file}'")
        print(f"   🌱 Seed: {self.seed}")
        print(f"   ⏰ Intervals: {len(time_range)} × 15-min")
        print(f"   📁 Output: '{output_dir}/'")
        
        num_datasets = 7 if storage_15min is None else 10
        datasets_desc = "Load + RES"
        if storage_15min is not None:
            datasets_desc += " + Storage"
        datasets_desc += " (Actual + DA + ID) + Prices"
        
        print(f"   📈 Datasets: {num_datasets} CSV files ({datasets_desc})")
        print(f"   ⏰ ALL TIMES NAIVE (NO TIMEZONE)")
        print(f"{'='*80}\n")
        
        return filtered_dfs, time_range
    
    # ========================================================================
    # DATA LOADING (STATIC METHOD)
    # ========================================================================
    
    @staticmethod
    def load_generated_data(output_dir: str) -> Dict[str, pd.DataFrame]:
        """
        Load pre-generated consistent copies from directory.
        
        Args:
            output_dir: Directory containing generated CSV files
        
        Returns:
            Dictionary of DataFrames with timezone-naive timestamps
        """
        files = {
            'load_actual': 'load_actual.csv',
            'load_forecast_da': 'load_forecast_da.csv',
            'load_forecast_id': 'load_forecast_id.csv',
            'res_actual': 'res_actual.csv',
            'res_forecast_da': 'res_forecast_da.csv',
            'res_forecast_id': 'res_forecast_id.csv',
            'prices': 'prices.csv',
            'storage_actual': 'storage_actual.csv',
            'storage_forecast_da': 'storage_forecast_da.csv',
            'storage_forecast_id': 'storage_forecast_id.csv'
        }
        
        data = {}
        for key, filename in files.items():
            filepath = os.path.join(output_dir, filename)
            if os.path.exists(filepath):
                df = pd.read_csv(filepath, parse_dates=['datetime'])
                # Ensure timezone-naive
                df['datetime'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
                data[key] = df
                print(f"✓ Loaded: {filename} ({len(df)} rows)")
            else:
                if key not in ['storage_actual', 'storage_forecast_da', 'storage_forecast_id']:
                    print(f"⚠ Missing: {filepath}")
        
        print(f"\nLoaded {len(data)} datasets from: {output_dir}")
        return data


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Command-line interface for Data."""
    parser = argparse.ArgumentParser(
        description="Generate consistent SimBench data with forecasts and prices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate new data using config file
  python data.py --generate
  
  # Generate with custom config
  python data.py --generate --config my_config.json
  
  # Generate with specific SimBench code (overrides config)
  python data.py --generate --simbench 1-LV-urban6--2-no_sw
  
  # Load existing generated data
  python data.py --load ./output
        """
    )
    
    parser.add_argument('--config', 
                       default='data_config.json',
                       help='Configuration file path (default: data_config.json)')
    parser.add_argument('--generate', 
                       action='store_true',
                       help='Generate new data')
    parser.add_argument('--load', 
                       metavar='DIR',
                       help='Load existing data from directory')
    parser.add_argument('--seed',
                       type=int,
                       default=42,
                       help='Random seed for reproducibility (default: 42)')
    parser.add_argument('--simbench',
                       type=str,
                       metavar='CODE',
                       help='SimBench grid code to override config file (e.g., 1-LV-urban6--2-no_sw)')
    
    args = parser.parse_args()
    
    if args.generate:
        print(f"Generating data with seed: {args.seed}")
        data_generator = Data(seed=args.seed, simbench_code=args.simbench, config_file=args.config)
        data_generator.generate_consistent_copies()
        print("\n✅ Generation complete!")
    
    elif args.load:
        print(f"Loading data from: {args.load}")
        data = Data.load_generated_data(args.load)
        print(f"\n✅ Loaded {len(data)} datasets")
        
        # Show basic statistics
        for name, df in data.items():
            print(f"\n{name}:")
            print(f"  Shape: {df.shape}")
            print(f"  Columns: {df.columns.tolist()[:5]}...")
    
    else:
        parser.print_help()
        print("\nError: Please specify --generate or --load")
        sys.exit(1)

if __name__ == "__main__":
    main()