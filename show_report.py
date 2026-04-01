import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(r'data\latest.json', encoding='utf-8') as f:
    d = json.load(f)

print('Generated:', d['generated_at'])
print('Analyzed:', d['total_analyzed'])
print('Tiers:', d['tier_summary'])
print()

tier_en = {'blue_ocean': '[BLUE OCEAN]', 'red_ocean_beatable': '[BEATABLE]', 'red_ocean_avoid': '[AVOID]'}
for p in d['top10']:
    label = tier_en.get(p['tier'], '?')
    print(f"#{p['rank']} Score:{p['total_score']}  {label}  ${p.get('price', 0):.2f}")
    print(f"  {p['title'][:60]}")
    print(f"  {p['opportunity_summary']}")
    print()
