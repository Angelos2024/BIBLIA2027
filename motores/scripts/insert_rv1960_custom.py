"""Inserta texto corrido personalizado en data/rv1960_genesis.json (caps 1-6)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RV_PATH = ROOT / "data" / "rv1960_genesis.json"
SRC_PATH = Path(__file__).resolve().parent / "rv1960_custom_gen1-6.txt"


def parse_source(text: str) -> dict[int, dict[int, str]]:
    """Parsea bloques N/א y versos numerados N)."""
    chapters: dict[int, dict[int, str]] = {}

    def flush_verse(ch: int, vn: int, body: str) -> None:
        body = body.strip()
        if not body:
            return
        chapters.setdefault(ch, {})[vn] = body

    text_norm = re.sub(r"\r\n", "\n", text)
    ch_parts = re.split(r"(?=\d+/\s*[א-ת])", text_norm)
    for part in ch_parts:
        m = re.match(r"^(\d+)/\s*[א-ת]\s*\n?", part)
        if not m:
            continue
        ch = int(m.group(1))
        body = part[m.end():]
        matches = list(re.finditer(r"(?:^|\n)(\d+)\)", body))
        for idx, match in enumerate(matches):
            vn = int(match.group(1))
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
            verse_text = body[start:end].strip()
            verse_text = re.sub(r"\s+", " ", verse_text).strip()
            flush_verse(ch, vn, verse_text)

    return chapters


def main() -> None:
    if not SRC_PATH.exists():
        raise SystemExit(f"Falta archivo fuente: {SRC_PATH}")

    src = SRC_PATH.read_text(encoding="utf-8")
    parsed = parse_source(src)

    rv = json.loads(RV_PATH.read_text(encoding="utf-8"))
    report: list[str] = []

    for ch in sorted(parsed.keys()):
        if ch < 1 or ch > len(rv):
            report.append(f"WARN cap {ch} fuera de rango JSON ({len(rv)} caps)")
            continue
        cap_verses = rv[ch - 1]
        for vn, text in sorted(parsed[ch].items()):
            if vn < 1 or vn > len(cap_verses):
                report.append(f"WARN {ch}:{vn} fuera de rango ({len(cap_verses)} versos)")
                continue
            cap_verses[vn - 1] = text
            report.append(f"OK {ch}:{vn} ({len(text)} chars)")

    RV_PATH.write_text(
        json.dumps(rv, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    out = Path(__file__).resolve().parent / "insert_rv1960_report.txt"
    out.write_text("\n".join(report), encoding="utf-8")
    print(f"Capítulos actualizados: {sorted(parsed.keys())}")
    for ch in sorted(parsed.keys()):
        print(f"  Cap {ch}: {len(parsed[ch])} versos")
    print(f"Reporte: {out}")


if __name__ == "__main__":
    main()
