
import json
from pathlib import Path
from agents.concentration_hedger import _compute_single_position_flags, _compute_sector_flags, _compute_correlation_pairs, _resolve_sector
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle

bundle_path = Path('bundles/composite_bundle_2026-04-13T203821Z_8402887a2204.json')
composite = load_composite_bundle(bundle_path)
market = load_bundle(Path(composite['market_bundle_path']))
positions = market['positions']
total_value = market['total_value']

print('--- Sector Resolution Check ---')
for ticker in ['GOOG', 'AMZN', 'QQQM', 'IGV', 'UNH']:
    pos = next(p for p in positions if p['ticker'] == ticker)
    print(f"{ticker} resolved to: {_resolve_sector(pos)}")

sector_flags = _compute_sector_flags(positions, total_value)
print('\n--- Sector Flags ---')
for f in sector_flags:
    print(f"{f['sector']}: {f['current_weight_pct']}% | {f['tickers_involved']}")

tech_flag = next((f for f in sector_flags if f['sector'] == 'Technology'), None)
print(f"\nT5.2 Tech > 30%: {tech_flag['current_weight_pct'] > 30 if tech_flag else False}")

print('\n--- Correlation Pairs (Running full compute) ---')
corr_pairs = _compute_correlation_pairs(positions, total_value, threshold=0.50)
print(f"Found {len(corr_pairs)} pairs.")
targets = [('AMZN', 'GOOG'), ('AMD', 'NVDA'), ('CRWD', 'PANW')]
found_targets = []
for p in corr_pairs:
    pair = tuple(sorted(p['tickers_involved']))
    for target in targets:
        if tuple(sorted(target)) == pair:
            print(f"Found target pair: {target} | Correlation: {p['correlation']:.2f}")
            found_targets.append(target)

print(f"\nT5.4 Found at least 2: {len(set(found_targets)) >= 2}")
