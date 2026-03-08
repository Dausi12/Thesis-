import simbench as sb
import pandas as pd

print("Searching SimBench networks for storage units...\n")
print("="*70)

nets = sb.collect_all_simbench_codes()
storage_nets = []

for i, code in enumerate(nets):
    try:
        net = sb.get_simbench_net(code)
        if hasattr(net, 'storage') and len(net.storage) > 0:
            storage_nets.append({
                'network_code': code,
                'num_storage': len(net.storage),
                'storage_details': net.storage.to_dict('records')
            })
            print(f"✓ {code}: {len(net.storage)} storage unit(s)")
    except Exception as e:
        pass

print("="*70)
print(f"\nTotal networks checked: {len(nets)}")
print(f"Networks with storage: {len(storage_nets)}\n")

if storage_nets:
    print("="*70)
    print("STORAGE NETWORKS FOUND:")
    print("="*70)
    for net_info in storage_nets:
        print(f"\nNetwork: {net_info['network_code']}")
        print(f"Storage Units: {net_info['num_storage']}")
        print("\nStorage Details:")
        df = pd.DataFrame(net_info['storage_details'])
        print(df.to_string())
        print("\n" + "-"*70)
else:
    print("No networks with storage units found in SimBench database.")
