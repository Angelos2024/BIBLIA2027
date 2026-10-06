"""
PDF v3 de la Lectura Samaritana  (HTML + navegador Chromium headless).
AUTOCONTENIDO y NO DESTRUCTIVO: lee los JSON originales, no modifica nada,
y escribe un PDF nuevo. No toca el motor ni los PDF/visores previos.

Incluye, respecto del original:
  1. Numero de verso a la DERECHA, al INICIO de cada verso (RTL).
  2. Tipografia hebrea mas grande/legible (fuente original Frank Ruehl incrustada).
  3. Apartado de Derechos de Autor (registro INDAUTOR mexicano).
  4. NUEVO: linea de TRANSCRIPCION FONETICA bajo cada verso, con las guturales
     o laringeas (Alef, He, Het, Ayin) ENMUDECIDAS segun la lectura samaritana
     (reglas G1-G5, Ben-Hayyim). El hebreo cuadrado conserva las letras.

Salida: Lectura_Samaritana_Torah_MiguelAngelRoanRodriguez_v3.pdf
"""
import json, os, subprocess, sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']
NAMES_HE = {'genesis': 'בראשית', 'exodus': 'שמות', 'leviticus': 'ויקרא',
            'numbers': 'במדבר', 'deuteronomy': 'דברים'}
NAMES_ES = {'genesis': 'Génesis', 'exodus': 'Éxodo', 'leviticus': 'Levítico',
            'numbers': 'Números', 'deuteronomy': 'Deuteronomio'}

REG_INDAUTOR = '03-2026-060601-14275006-14'
AUTOR = 'Ing. Miguel Ángel Roan Rodriguez'

# ============================================================
#  TRANSCRIPCION FONETICA: UNICA fuente = motor_gutural_fonetico.py
# ============================================================
# Este generador NO define reglas de transcripcion propias. Toda la logica
# (guturales mudas G1-G5, cualidad vocalica, qamats qatan, doble linea
# academica/hispana) vive SOLO en motor_gutural_fonetico.py, para que no
# existan reglas duplicadas ni desincronizadas entre archivos.
try:
    import motor_gutural_fonetico as mgf
except Exception as _e:
    print(f"ERROR: no se pudo importar motor_gutural_fonetico.py ({_e}).")
    print("Es la UNICA fuente de transcripcion; debe estar en la misma carpeta.")
    sys.exit(3)


print("Transcripcion: motor_gutural_fonetico (doble linea academica + hispana).")


# ============================================================
#  Navegador headless + fuente original incrustada
# ============================================================
BROWSER_CANDIDATES = [
    r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
    r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]
BROWSER = next((p for p in BROWSER_CANDIDATES if os.path.exists(p)), None)

FRANK = r'C:\Windows\Fonts\frank.ttf'
font_face = ''
if os.path.exists(FRANK):
    font_face = f'@font-face {{ font-family:"FrankRuehlLocal"; src:url("file:///{FRANK.replace(chr(92),"/")}"); }}'
HEB_FAMILY = ('"FrankRuehlLocal", "SBL Hebrew", "Frank Ruehl CLM", '
              '"FrankRuehl", "David", "Noto Serif Hebrew", serif')

print("Construyendo HTML v3 (numeros a la derecha + fonetica gutural)...")

html = ['''<!DOCTYPE html>
<html lang="he" dir="ltr"><head><meta charset="utf-8">
<title>Lectura Samaritana de la Toráh</title>
<style>
''' + font_face + '''
@page { size: A4; margin: 20mm 18mm 22mm 18mm; }
body { font-family:"Segoe UI",Arial,sans-serif; font-size:11.5pt; color:#241a10; line-height:1.55; }
.title-page { page-break-after:always; text-align:center; padding-top:110px; position:relative; min-height:760px; }
.title-he { font-family:''' + HEB_FAMILY + '''; font-size:42pt; color:#3c2314; direction:rtl; margin-bottom:20px; }
.title-es { font-size:24pt; font-weight:bold; color:#3c2314; margin-bottom:10px; }
.subtitle { font-size:13pt; color:#644b32; margin-bottom:40px; }
.title-line { width:120px; border:none; border-top:1.5px solid #b4966e; margin:0 auto; }
.author-block { position:absolute; bottom:40px; left:0; text-align:left; font-size:10pt; color:#786450; }
.author-block .date { font-style:italic; font-size:9pt; color:#968270; }
.copyright-page { page-break-after:always; }
.copyright-page h1 { font-size:18pt; color:#3c2314; margin-bottom:4px; }
.copyright-page hr { border:none; border-top:1.5px solid #b4966e; margin-bottom:16px; }
.copyright-box { border:1px solid #cbb38c; background:#faf6ef; border-radius:6px; padding:16px 18px;
                 font-size:10.5pt; line-height:1.6; color:#2a1e14; text-align:justify; }
.copyright-box .reg { font-weight:bold; color:#643c1e; }
.copyright-box .small { font-size:9.5pt; color:#6b5640; }
.intro-page { page-break-after:always; }
.intro-page h1 { font-size:20pt; color:#3c2314; margin-bottom:4px; }
.intro-page hr { border:none; border-top:1.5px solid #b4966e; margin-bottom:16px; }
.intro-page p { text-align:justify; margin-bottom:8px; }
.intro-page ol { padding-left:20px; }
.intro-page ol li { margin-bottom:6px; text-align:justify; }
.book-title { page-break-before:always; text-align:center; padding-top:30px; margin-bottom:10px; }
.book-title .es { font-size:22pt; font-weight:bold; color:#3c2314; }
.book-title .he { font-family:''' + HEB_FAMILY + '''; font-size:30pt; color:#3c2314; direction:rtl; }
.book-title hr { width:140px; border:none; border-top:1.5px solid #b4966e; margin:12px auto 20px; }
.chapter-head { font-size:14pt; font-weight:bold; color:#643c1e; text-align:right; margin-top:20px; margin-bottom:8px; }
.verse { direction:rtl; text-align:right; font-family:''' + HEB_FAMILY + ''';
         font-size:22pt; line-height:2.35; margin-bottom:1px; color:#120d08; letter-spacing:0.015em; }
.verse .vn { font-family:"Segoe UI",Arial,sans-serif; font-size:11pt; font-weight:bold; color:#8c5a20;
             vertical-align:super; margin-left:10px; direction:ltr; unicode-bidi:embed; }
.fon-h { direction:ltr; text-align:left; font-family:"Cambria","Segoe UI",serif;
         font-size:10.5pt; color:#5e4226; margin:0 0 1px 6px; line-height:1.35; }
.fon-a { direction:ltr; text-align:left; font-family:"Cambria","Segoe UI",serif; font-style:italic;
         font-size:10pt; color:#8a6a48; margin:0 0 9px 6px; line-height:1.35; }
.fon-h .lbl, .fon-a .lbl { font-size:7.5pt; font-weight:bold; color:#b08040;
         text-transform:uppercase; letter-spacing:0.05em; margin-right:6px; }
</style></head><body>
''']

# ── PORTADA ──
html.append(f'''
<div class="title-page">
  <div class="title-he">תורת השמרונים</div>
  <div class="title-es">Lectura Samaritana de la Toráh</div>
  <div class="subtitle">Pentateuco Samaritano vocalizado en hebreo cuadrado · con transcripción fonética</div>
  <hr class="title-line">
  <div class="author-block">{AUTOR}<br><span class="date">{datetime.now().strftime("%B %Y")}</span></div>
</div>
''')

# ── DERECHOS DE AUTOR ──
year = datetime.now().year
html.append(f'''
<div class="copyright-page">
<h1>Derechos de Autor</h1><hr>
<div class="copyright-box">
<p>&copy; {year} {AUTOR}. Todos los derechos reservados.</p>
<p>La presente obra se encuentra protegida por la <strong>Ley Federal del Derecho de Autor</strong>
de los Estados Unidos Mexicanos, de manera enunciativa y no limitativa por sus
<strong>artículos 13, 162, 163 fracción I y 164 fracción I</strong>, así como por las demás
disposiciones legales aplicables en materia de derechos de autor y propiedad intelectual,
nacionales e internacionales suscritas por México.</p>
<p>Obra inscrita en el Registro Público del Derecho de Autor del Instituto Nacional del Derecho
de Autor (INDAUTOR) bajo el número de registro:</p>
<p class="reg">Número de Registro INDAUTOR: {REG_INDAUTOR}</p>
<p class="small">Queda estrictamente prohibida la reproducción, distribución, comunicación pública,
transformación o cualquier otra forma de explotación, total o parcial, de esta obra por cualquier
medio o procedimiento, sin la autorización previa y por escrito del titular de los derechos. Toda
utilización deberá respetar el derecho moral de paternidad e integridad de la obra a favor del autor.</p>
</div></div>
''')

# ── INTRODUCCION ──
html.append('''
<div class="intro-page">
<h1>Introducción</h1><hr>
<p>El presente documento contiene la vocalización completa del Pentateuco Samaritano (SP)
en hebreo cuadrado con niqqud (signos vocálicos), acompañada de una transcripción fonética
que refleja el enmudecimiento de las consonantes guturales o laríngeas (Álef, He, Jet y Ayin),
rasgo característico de la lectura oral samaritana según Ben-Hayyim.</p>
<p>La comunidad samaritana, que hoy cuenta con apenas 800 miembros divididos entre Holon
y el Monte Gerizim, preserva una tradición oral de lectura de la Toráh que difiere
sustancialmente de la pronunciación masorética (tiberiana). El texto en hebreo cuadrado conserva
todas las consonantes y su vocalización (incluidas las guturales o laríngeas Álef א, He ה, Jet ח y
Ayin ע). La línea fonética, en cursiva bajo cada verso, indica cómo se leería en voz alta: en la
tradición samaritana esas guturales se debilitan o enmudecen, y las vocales adyacentes tienden a
fundirse o alargarse.</p>
<p>Bajo cada verso se ofrecen <strong>dos líneas de transcripción</strong>:</p>
<ol>
<li><strong>esp</strong> (hispana): pensada para la lectura fluida en español, sin signos especiales
(p. ej. <em>ba rashit bara aluim</em>).</li>
<li><strong>acad</strong> (académica): refleja con mayor precisión la realidad fonética de Nablus,
distinguiendo la <em>å</em> (qamats velar) y marcando las vocales largas <em>ā ē ī ō ū</em> cuando
provienen de contracción o de <em>mater lectionis</em> (p. ej. <em>bå råšīt bårå aluēim</em>).
No se marca la longitud meramente posicional, que depende del sistema de acento (pendiente de
incorporar). No se usa el signo schwa, pues la tradición samaritana carece de ese fonema.</li>
</ol>
<p>La vocalización se generó con un motor de reglas fonológicas (Motor Samaritano v6) que transfiere
la vocalización masorética del corpus ETCBC/BHSA al esqueleto consonántico samaritano (dt-ucph/sp)
y aplica reglas documentadas por Ben-Hayyim. La capa fonética añade reglas de debilitamiento gutural
(G1-G5). Las transcripciones son reconstrucciones eruditas, revisables contra las fuentes impresas
(Tsedaka / Ben-Hayyim).</p>
</div>
''')

# ── TEXTO ──
for b in ORDER:
    # Prefiere el JSON con reglas /e/ (we-qatal, *ay) si existe; si no, el original.
    src_e = os.path.join(BASE, f'{b}_lectura_samaritana_e.json')
    src = src_e if os.path.exists(src_e) else os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(src, encoding='utf-8') as f:
        data = json.load(f)
    print(f'{NAMES_ES[b]}: {len(data["chapters"])} capítulos  [fuente: {os.path.basename(src)}]')
    html.append(f'''
<div class="book-title"><div class="es">{NAMES_ES[b]}</div>
<div class="he">{NAMES_HE[b]}</div><hr></div>
''')
    for ch in sorted(data['chapters'].keys(), key=int):
        chap = data['chapters'][ch]
        html.append(f'<div class="chapter-head">Capítulo {ch}</div>\n')
        for vs in sorted(chap.keys(), key=int):
            sam = chap[vs]['sam_reading']
            # El hebreo cuadrado conserva la vocalizacion (incluidas las guturales).
            # El enmudecimiento gutural se refleja SOLO en la transliteracion.
            safe = sam.replace('&', '&amp;').replace('<', '&lt;')
            words = chap[vs].get('words', [])
            if words:
                # Palabra por palabra para que la Regla 1 (patron hataf) use w['mt'].
                fh = ' '.join(mgf.translit_hisp_word(w.get('sam_reading', ''), w.get('mt', ''))
                              for w in words if w.get('sam_reading'))
                fa = ' '.join(mgf.translit_acad_word(w.get('sam_reading', ''))
                              for w in words if w.get('sam_reading'))
            else:
                fh = mgf.translit_hisp_verse(sam)
                fa = mgf.translit_acad_verse(sam)
            fh = fh.replace('&', '&amp;').replace('<', '&lt;')
            fa = fa.replace('&', '&amp;').replace('<', '&lt;')
            html.append(f'<div class="verse"><span class="vn">{vs}</span> {safe}</div>\n')
            html.append(f'<div class="fon-h"><span class="lbl">esp</span>{fh}</div>\n')
            html.append(f'<div class="fon-a"><span class="lbl">acad</span>{fa}</div>\n')

html.append('</body></html>')

html_path = os.path.join(BASE, '_print_torah_v3.html')
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(''.join(html))
print(f'HTML: {html_path} ({os.path.getsize(html_path)/1048576:.2f} MB)')

pdf_path = os.path.join(BASE, 'Lectura_Samaritana_Torah_MiguelAngelRoanRodriguez_v3.pdf')
if not BROWSER:
    print('ERROR: no se encontró Brave/Chrome/Edge. El HTML quedó generado; ábrelo e imprime a PDF.')
    sys.exit(2)

print(f'Convirtiendo a PDF con: {BROWSER}')
cmd = [BROWSER, '--headless', '--disable-gpu', '--no-sandbox',
       '--run-all-compositor-stages-before-draw',
       '--print-to-pdf=' + pdf_path, '--print-to-pdf-no-header', html_path]
res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
if res.returncode != 0:
    print('STDERR:', res.stderr); print('STDOUT:', res.stdout); sys.exit(1)
print(f'\nPDF v3 generado: {pdf_path}')
print(f'Tamaño: {os.path.getsize(pdf_path)/1048576:.2f} MB\n¡Listo!')
