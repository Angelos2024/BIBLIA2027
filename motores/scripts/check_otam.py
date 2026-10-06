"""Inspecciona el estado de )T/M (אֹתָם) y similares en Génesis."""
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

JSON = Path(r"C:\Users\pik_y\Documents\TRADUCCION\data\genesis_final.json")
data = json.loads(JSON.read_text(encoding="utf-8"))

print("=== Estado actual de )T + sufijo PRS en Génesis ===\n")
print(f"{'Ref':<10} {'raw':<10} {'he_form':<12} {'es':<10} {'gr_word':<25} prs_suffix")
print("-" * 100)

count = {'total': 0, 'sin_es': 0, 'con_prs': 0, 'sin_prs': 0}
samples_by_pattern = {}

for v in data['verses']:
    ref = v.get('ref', '') or f"{v.get('chapter','')}:{v.get('verse','')}"
    for p in v.get('pairs', []):
        for hw in p.get('he_words', []):
            raw = hw.get('raw', '')
            if raw.startswith(')T/') and len(raw) <= 8:
                count['total'] += 1
                es = hw.get('es', '')
                gr = hw.get('gr_word', '')
                he = hw.get('he_form', '')
                prs = hw.get('prs_suffix')
                if not es: count['sin_es'] += 1
                if prs: count['con_prs'] += 1
                else:    count['sin_prs'] += 1
                pat = raw
                if pat not in samples_by_pattern:
                    samples_by_pattern[pat] = []
                if len(samples_by_pattern[pat]) < 3:
                    samples_by_pattern[pat].append({
                        'ref': ref, 'he': he, 'es': es, 'gr': gr,
                        'prs': prs
                    })

print("Resumen:")
print(f"  Total tokens )T/X: {count['total']}")
print(f"  Sin es:            {count['sin_es']}")
print(f"  Con prs_suffix:    {count['con_prs']}")
print(f"  Sin prs_suffix:    {count['sin_prs']}\n")

for pat in sorted(samples_by_pattern.keys()):
    print(f"\n--- Patrón {pat} ({len(samples_by_pattern[pat])} muestras) ---")
    for s in samples_by_pattern[pat]:
        prs_str = ""
        if s['prs']:
            prs_str = f"prs: he={s['prs'].get('he_form','')!r} es={s['prs'].get('es','')!r} gr={s['prs'].get('gr_word','')!r}"
        else:
            prs_str = "(sin prs)"
        print(f"  {s['ref']:<10}  he={s['he']!r:<14} es={s['es']!r:<10} gr={s['gr']!r:<25}  {prs_str}")
