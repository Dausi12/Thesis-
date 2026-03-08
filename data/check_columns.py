import pandas as pd

df_load = pd.read_csv('load_forecast_da.csv')
df_res = pd.read_csv('res_forecast_da.csv')

loads = ['3', '5', '6', '7', '8', '11', '15', '19']

print('LOAD COLUMNS:')
for l in loads:
    matching = [c for c in df_load.columns if f'Load {l} ' in c]
    print(f'  Load {l}: {matching}')

print('\nRES COLUMNS:')
res_cols = [c for c in df_res.columns if 'SGen' in c]
for i, col in enumerate(res_cols, 1):
    print(f'  {i}. {col}')
