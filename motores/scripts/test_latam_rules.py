import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from es_latam_neutral import to_latam_neutral

# Buscar deformaciones en datos actuales
ROOT = Path(__file__).resolve().parent.parent
BAD = re.compile(
    r"\b(caeren|comeren|viveren|seran\b(?!\w)|estarán\b|moriran\b(?!\w)|"
    r"paen\b|atlan\b|\bman\b|\bren\b|\bden\b(?!\w)|virian\b|comeran\b(?!\w)|"
    r"haberan\b|tendran\b|podran\b|haran\b|diran\b|irenan\b)\b",
    re.I,
)

for name in ["genesis_final.json", "rv1960_genesis.json"]:
    p = ROOT / "data" / name
    if not p.exists():
        continue
    raw = p.read_text(encoding="utf-8")
    hits = BAD.findall(raw)
    print(f"{name}: {len(hits)} hits", hits[:20])

# Test comprehensive edge cases
cases = {
    "país": "país",
    "pais": "pais",
    "países": "países",
    "Dios": "Dios",
    "nos": "nos",
    "reyes": "reyes",
    "reis": "reis",
    "deis": "deis",  # or "den" if verb - ambiguous
    "mais": "mais",
    "atlas": "atlas",
    "caeréis": "caerán",
    "caereis": "caerán",
    "comeréis": "comerán",
    "comereis": "comerán",
    "moriréis": "morirán",
    "seréis": "serán",
    "sereis": "serán",
    "coméis": "comen",
    "comeis": "comen",
    "habláis": "hablan",
    "hablais": "hablan",
    "vivís": "viven",
    "confiáis": "confían",
    "confiais": "confían",
    "hablabais": "hablaban",
    "hablasteis": "hablaron",
    "fuisteis": "fueron",
    "estáis": "están",
    "estais": "están",
    "No comeréis": "No comerán",
    "moriréis todos": "morirán todos",
    "Vosotros moriréis": "Ustedes morirán",
    "escoger": "escoger",
    "coger": "coger",  # léxico moderno DESACTIVADO en corpus bíblico
    "equivalente": "equivalente",
    "historia": "historia",
    "gloria": "gloria",
    "paraíso": "paraíso",
    "paraiso": "paraiso",
    "análisis": "análisis",
    "Jehová": "Jehová",
    "id": "vayan",
    "Id": "Vayan",
    "validé": "validé",
    "salvador": "salvador",
    "leeréis": "leerán",
    "creeréis": "creerán",
    "veréis": "verán",
    "oiréis": "oirán",
    "caeréis en": "caerán en",
    "que deis": "que den",  # subjunctive - acceptable
    "os": "les",
    "Os lo dije": "se lo dije",
    "vuestro": "su",
    "vuestra casa es vuestra": "su casa es de ustedes",
}

fail = []
for inp, expected in cases.items():
    got = to_latam_neutral(inp)
    if got != expected:
        fail.append((inp, expected, got))

print(f"\nFAILURES: {len(fail)}/{len(cases)}")
for inp, exp, got in fail:
    print(f"  {inp!r}\n    expected: {exp!r}\n    got:      {got!r}")
