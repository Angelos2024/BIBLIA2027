"""
Genera el VISOR/PDF del TEXTO SAMARITANO de Genesis (Pasos 1-5 integrados).
NO destructivo: lee mapeo_genesis/genesis_texto_samaritano.json, no modifica nada,
y escribe HTML + PDF nuevos.

Render por verso:
  - Linea cuadrada (RTL) con la lectura samaritana, con marca ADD+ ENCIMA de cada
    adicion samaritana (plus). Transposiciones (moved) visibles sin marca.
    Omisiones (omit) y reubicaciones-fantasma (moved_omit) OCULTAS.
  - Doble linea fonetica (esp / acad) via motor_gutural_fonetico, palabra por
    palabra, sobre el texto VISIBLE (incluye pluses vocalizados).

Salida: _print_genesis_samaritano.html  +  Genesis_Samaritano.pdf
"""
import json, os, subprocess, sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'mapeo_genesis', 'genesis_texto_samaritano.json')
VISIBLE = ('common', 'variant', 'plus', 'moved')

try:
    import motor_gutural_fonetico as mgf
except Exception as e:
    print(f"ERROR importando motor_gutural_fonetico: {e}"); sys.exit(3)

FRANK = r'C:\Windows\Fonts\frank.ttf'
font_face = ''
if os.path.exists(FRANK):
    font_face = f'@font-face {{ font-family:"FrankRuehlLocal"; src:url("file:///{FRANK.replace(chr(92),"/")}"); }}'
HEB_FAMILY = ('"FrankRuehlLocal","SBL Hebrew","Frank Ruehl CLM","FrankRuehl",'
              '"David","Noto Serif Hebrew",serif')

BROWSER_CANDIDATES = [
    r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
    r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]
BROWSER = next((p for p in BROWSER_CANDIDATES if os.path.exists(p)), None)


def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;')


def render_word(w):
    """Palabra cuadrada; si es plus -> con etiqueta ADD+ encima."""
    txt = esc(w['text'])
    if w['type'] == 'plus':
        return (f'<span class="w add"><span class="lab">ADD+</span>'
                f'<span class="t">{txt}</span></span>')
    return txt


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    n_add = n_omit = 0

    css = font_face + '''
@page { size:A4; margin:18mm 16mm 20mm 16mm; }
body{font-family:"Segoe UI",Arial,sans-serif;font-size:11.5pt;color:#241a10;}
.title-page{text-align:center;padding-top:120px;page-break-after:always;}
.title-he{font-family:''' + HEB_FAMILY + ''';font-size:40pt;color:#3c2314;direction:rtl;}
.title-es{font-size:24pt;font-weight:bold;color:#3c2314;margin-top:12px;}
.subtitle{font-size:13pt;color:#644b32;margin-top:8px;}
.legend{margin:18px auto;max-width:520px;font-size:10.5pt;color:#4a3venir;background:#faf6ef;
        border:1px solid #cbb38c;border-radius:6px;padding:12px 16px;text-align:left;}
.legend b.add{background:#b3261e;color:#fff;border-radius:3px;padding:0 4px;font-size:9pt;}
.chapter-head{font-size:14pt;font-weight:bold;color:#643c1e;text-align:right;
              margin:18px 0 6px;page-break-after:avoid;}
.verse{direction:rtl;text-align:right;font-family:''' + HEB_FAMILY + ''';font-size:22pt;
       line-height:2.6;margin-bottom:1px;color:#120d08;letter-spacing:.015em;}
.verse .vn{font-family:"Segoe UI",Arial,sans-serif;font-size:11pt;font-weight:bold;
           color:#8c5a20;vertical-align:super;margin-left:10px;direction:ltr;unicode-bidi:embed;}
.w{display:inline-flex;flex-direction:column;align-items:center;vertical-align:bottom;margin:0 2px;}
.w .lab{font-size:7.5pt;color:#fff;background:#b3261e;border-radius:3px;padding:0 3px;
        line-height:1.3;direction:ltr;font-family:sans-serif;margin-bottom:-2px;}
.fon-h{direction:ltr;text-align:left;font-family:"Cambria",serif;font-size:10.5pt;
       color:#5e4226;margin:0 0 1px 6px;line-height:1.35;}
.fon-a{direction:ltr;text-align:left;font-family:"Cambria",serif;font-style:italic;
       font-size:10pt;color:#8a6a48;margin:0 0 9px 6px;line-height:1.35;}
.fon-h .lbl,.fon-a .lbl{font-size:7.5pt;font-weight:bold;color:#b08040;
       text-transform:uppercase;letter-spacing:.05em;margin-right:6px;}
'''.replace('#4a3venir', '#4a3a28')

    html = [f'''<!DOCTYPE html><html lang="es" dir="ltr"><head><meta charset="utf-8">
<title>Genesis Samaritano</title><style>{css}</style></head><body>
<div class="title-page">
  <div class="title-he">בראשית · תורת השמרונים</div>
  <div class="title-es">Génesis — Texto Samaritano</div>
  <div class="subtitle">Pentateuco Samaritano vocalizado · adiciones, variantes y omisiones respecto al MT</div>
  <div class="legend">
    Las <b class="add">ADD+</b> marcan <b>adiciones</b> que el texto samaritano tiene y el masorético no.
    Las <b>variantes</b> y <b>transposiciones</b> se integran en su lugar samaritano.
    Las <b>omisiones</b> (palabras del MT ausentes en el SP) se ocultan aquí y quedan
    registradas en el compendio <i>genesis_omisiones</i>. Bajo cada verso: transcripción
    fonética <b>esp</b> (hispana) y <b>acad</b> (académica, Ben-Hayyim).
  </div>
</div>''']

    for ch in sorted(data['chapters'], key=int):
        html.append(f'<div class="chapter-head">פרק {ch} · Capítulo {ch}</div>')
        for vs in sorted(data['chapters'][ch], key=int):
            words = data['chapters'][ch][vs]['words']
            vis = [w for w in words if w['type'] in VISIBLE and w.get('text')]
            n_add += sum(1 for w in vis if w['type'] == 'plus')
            n_omit += sum(1 for w in words if w['type'] == 'omit')

            line = ' '.join(render_word(w) for w in vis)
            fh = ' '.join(mgf.translit_hisp_word(w['text'], w.get('mt', '')) for w in vis)
            fa = ' '.join(mgf.translit_acad_word(w['text']) for w in vis)

            html.append(f'<div class="verse"><span class="vn">{vs}</span> {line}</div>')
            html.append(f'<div class="fon-h"><span class="lbl">esp</span>{esc(fh)}</div>')
            html.append(f'<div class="fon-a"><span class="lbl">acad</span>{esc(fa)}</div>')

    html.append('</body></html>')

    html_path = os.path.join(BASE, '_print_genesis_samaritano.html')
    open(html_path, 'w', encoding='utf-8').write(''.join(html))
    print(f'HTML: {html_path} ({os.path.getsize(html_path)/1048576:.2f} MB)')
    print(f'ADD+ renderizados: {n_add} | omisiones ocultas: {n_omit}')

    pdf_path = os.path.join(BASE, 'Genesis_Samaritano.pdf')
    if not BROWSER:
        print('No se encontró navegador; abre el HTML e imprime a PDF manualmente.')
        return
    print(f'Convirtiendo a PDF con: {BROWSER}')
    cmd = [BROWSER, '--headless', '--disable-gpu', '--no-sandbox',
           '--run-all-compositor-stages-before-draw',
           '--print-to-pdf=' + pdf_path, '--print-to-pdf-no-header', html_path]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        print('STDERR:', res.stderr[-800:]); sys.exit(1)
    print(f'PDF generado: {pdf_path}  ({os.path.getsize(pdf_path)/1048576:.2f} MB)')
    print('DONE')


if __name__ == '__main__':
    main()
