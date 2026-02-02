# Data Generator

Single unified data generator for SimBench grid data and energy market prices.

## Overview

`data.py` generates all required data for energy balancing simulations:
- Load profiles (actual, day-ahead forecast, intraday forecast)
- RES profiles (actual, day-ahead forecast, intraday forecast)
- Storage profiles (actual, day-ahead forecast, intraday forecast)
- Market prices (day-ahead, intraday, imbalance, retail, feed-in)

## Key Features

✅ **Single Generator** - One script generates everything
✅ **Integrated ID Prices** - Intraday prices generated on-the-fly from day-ahead prices
✅ **Consistent Randomization** - All forecasts use same strategy (controlled random multipliers)
✅ **Reproducible** - Seed-based for consistent results
✅ **Configurable** - All parameters in `data_config.json`

## Quick Start

```bash
# Generate all data
python data.py --generate

# Use custom config
python data.py --generate --config my_config.json

# Override SimBench grid
python data.py --generate --simbench 1-LV-urban6--2-no_sw

# Use different seed
python data.py --generate --seed 123
```

## Configuration

Edit `data_config.json`:

```json
{
  "seed": 42,
  "simbench_code": "1-LV-rural2--1-no_sw",
  "da_price_file": "original/Day Ahead Preise_M15_2016.csv",
  "id_price_range": [0.9, 1.1],
  "imbalance_price_file": "original/imbalance_prices.csv",
  "retail_price_file": "original/retail_price.csv",
  "feedin_price_file": "original/feedin_price.csv",
  "start_time": "2016-01-01 00:00",
  "end_time": "2016-12-31 23:45",
  "output_dir": "."
}
```

### Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `seed` | Random seed for reproducibility | 42 |
| `simbench_code` | SimBench grid topology | `1-LV-rural2--1-no_sw` |
| `da_price_file` | Day-ahead price CSV | `original/Day Ahead Preise_M15_2016.csv` |
| `id_price_range` | ID/DA ratio range [min, max] | `[0.9, 1.1]` |
| `imbalance_price_file` | Imbalance price CSV | `original/imbalance_prices.csv` |
| `retail_price_file` | Fixed retail price CSV | `original/retail_price.csv` |
| `feedin_price_file` | Fixed feed-in price CSV | `original/feedin_price.csv` |
| `start_time` | Start timestamp | `2016-01-01 00:00` |
| `end_time` | End timestamp | `2016-12-31 23:45` |
| `output_dir` | Output directory | `.` (current) |

## Randomization Strategy

All forecasts use **controlled randomization** with uniform random multipliers:

| Forecast Type | Range | Purpose |
|--------------|-------|---------|
| Load DA | 0.8 - 1.2 | Wider uncertainty for day-ahead |
| Load ID | 0.9 - 1.1 | Tighter for intraday (closer to gate closure) |
| RES DA | 0.7 - 1.3 | Higher uncertainty (weather-dependent) |
| RES ID | 0.85 - 1.15 | Improved but still uncertain |
| **Price ID** | **0.9 - 1.1** | **Same strategy as Load ID** |

### Why This Approach?

1. **Consistent** - Same methodology across all forecasts
2. **Simple** - Easy to understand and maintain
3. **Realistic** - Captures forecast uncertainty
4. **Reproducible** - Seed-based for identical results
5. **Fast** - No ML model training required

## Output Files

Generated CSV files (35,136 rows each, 15-minute intervals):

### Load Profiles
- `load_actual.csv` - Actual load (103 units)
- `load_forecast_da.csv` - Day-ahead forecast
- `load_forecast_id.csv` - Intraday forecast

### RES Profiles
- `res_actual.csv` - Actual generation (9 units)
- `res_forecast_da.csv` - Day-ahead forecast
- `res_forecast_id.csv` - Intraday forecast

### Storage Profiles (if available)
- `storage_actual.csv` - Actual storage
- `storage_forecast_da.csv` - Day-ahead forecast
- `storage_forecast_id.csv` - Intraday forecast

### Prices
- `prices.csv` - Unified price data with columns:
  - `DA_price` - Day-ahead market price (€/MWh)
  - `ID_price` - Intraday market price (€/MWh) - **Generated**
  - `imbalance_price` - System imbalance price (€/MWh)
  - `retail_price` - Fixed retail price (€/MWh)
  - `feedin_price` - Fixed feed-in tariff (€/MWh)

## Intraday Price Generation

**Integrated into data.py** - No separate script needed!

```python
def generate_id_price_data(self, da_price_df, id_range=(0.9, 1.1)):
    """Generate ID prices from DA prices using randomization"""
    random_factors = np.random.uniform(id_range[0], id_range[1], size=len(da_price_df))
    id_prices = da_price_df['DA_price'] * random_factors
    return id_price_df
```

### ID Price Statistics
- Average ID/DA ratio: ~1.0
- Range: 0.90 - 1.10 (configurable)
- Method: Uniform random distribution
- Correlation with DA: Very high (by design)

## File Structure

```
data/
├── data.py                      # Main generator (run this!)
├── data_config.json             # Configuration
├── original/                    # Input data
│   ├── Day Ahead Preise_M15_2016.csv
│   ├── imbalance_prices.csv
│   ├── retail_price.csv
│   ├── feedin_price.csv
│   └── generate_intraday_prices.py  # (deprecated - kept for reference)
├── load_actual.csv             # Generated outputs
├── load_forecast_da.csv
├── load_forecast_id.csv
├── res_actual.csv
├── res_forecast_da.csv
├── res_forecast_id.csv
├── storage_actual.csv
├── storage_forecast_da.csv
├── storage_forecast_id.csv
└── prices.csv
```

## Dependencies

```bash
pip install pandas numpy simbench
```

## Notes

- All timestamps are **timezone-naive** for consistency
- DST transitions (2A/2B notation) are handled automatically
- Forward-fill is used for missing price data
- All prices in **€/MWh**
- All power values in **MW**
- Grid: SimBench `1-LV-rural2--1-no_sw` (103 loads, 9 RES units)

## Migration from Two Generators

**Old workflow:**
```bash
cd original
python generate_intraday_prices.py  # Generate ID prices
cd ..
python data.py --generate           # Generate everything else
```

**New workflow:**
```bash
python data.py --generate           # One command!
```

The `generate_intraday_prices.py` script in the `original/` folder is kept for reference but is no longer needed.

## Troubleshooting

**Issue:** Missing config file
```
Solution: Create data_config.json or specify --config path
```

**Issue:** SimBench not found
```
Solution: pip install simbench
```

**Issue:** Different results
```
Solution: Check seed value - same seed = same results
```

## Examples

### Change ID price volatility
```json
"id_price_range": [0.85, 1.15]  // More volatile
"id_price_range": [0.95, 1.05]  // Less volatile
```

### Different time range
```json
"start_time": "2016-01-01 00:00",
"end_time": "2016-01-31 23:45"    // January only
```

### Different grid topology
```bash
python data.py --generate --simbench 1-LV-urban6--2-no_sw
```
