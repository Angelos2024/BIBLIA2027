"""
Genera un NUEVO PDF de la Lectura Samaritana via HTML + navegador Chromium headless.
Mismo motor de render que el visor/HTML original (misma herramienta), SIN modificar
el texto fuente ni la tipografia original (Frank Ruehl / SBL Hebrew).

Cambios solicitados respecto del PDF original:
  1. El numero de cada verso aparece a la DERECHA, al INICIO del verso (orden RTL).
  2. Tipografia mas legible (mayor tamano, interlineado y contraste) conservando la
     misma familia tipografica original del hebreo samaritano.
  3. Apartado de Derechos de Autor (registro mexicano INDAUTOR).

NO modifica el PDF original; escribe un archivo nuevo.
"""
import json, os, subprocess, sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Carpeta del propio script (portable)
BASE = os.path.dirname(os.path.abspath(__file__))
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']
NAMES_HE = {
    'genesis': 'בראשית', 'exodus': 'שמות', 'leviticus': 'ויקרא',
    'numbers': 'במדבר', 'deuteronomy': 'דברים'
}
NAMES_ES = {
    'genesis': 'Génesis', 'exodus': 'Éxodo', 'leviticus': 'Levítico',
    'numbers': 'Números', 'deuteronomy': 'Deuteronomio'
}

# ── Datos del registro de derechos de autor ──
REG_INDAUTOR = '03-2026-060601-14275006-14'
AUTOR = 'Ing. Miguel Ángel Roan Rodriguez'

# ── Deteccion del navegador Chromium (misma herramienta: motor headless) ──
BROWSER_CANDIDATES = [
    r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
    r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
]
BROWSER = next((p for p in BROWSER_CANDIDATES if os.path.exists(p)), None)

# ── Fuente original Frank Ruehl para embeber (garantiza render claro) ──
FRANK = r'C:\Windows\Fonts\frank.ttf'
frank_uri = FRANK.replace('\\', '/')
font_face = ''
if os.path.exists(FRANK):
    font_face = f'''
@font-face {{
  font-family: "FrankRuehlLocal";
  src: url("file:///{frank_uri}");
}}
'''
# La familia hebrea conserva la tipografia ORIGINAL; solo se anteponen alias locales
HEB_FAMILY = ('"FrankRuehlLocal", "SBL Hebrew", "Frank Ruehl CLM", '
              '"FrankRuehl", "David", "Noto Serif Hebrew", serif')

print("Construyendo HTML para impresión (v2: números a la derecha, fuente más legible)...")

html_parts = ['''<!DOCTYPE html>
<html lang="he" dir="ltr">
<head>
<meta charset="utf-8">
<title>Lectura Samaritana de la Toráh</title>
<style>
''' + font_face + '''
@page {
  size: A4;
  margin: 20mm 18mm 22mm 18mm;
}
body {
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 11.5pt;
  color: #241a10;
  line-height: 1.55;
}

/* Title page */
.title-page {
  page-break-after: always;
  text-align: center;
  padding-top: 110px;
  position: relative;
  min-height: 760px;
}
.title-he {
  font-family: ''' + HEB_FAMILY + ''';
  font-size: 42pt;
  color: #3c2314;
  direction: rtl;
  margin-bottom: 20px;
}
.title-es {
  font-size: 24pt;
  font-weight: bold;
  color: #3c2314;
  margin-bottom: 10px;
}
.subtitle {
  font-size: 13pt;
  color: #644b32;
  margin-bottom: 40px;
}
.title-line {
  width: 120px;
  border: none;
  border-top: 1.5px solid #b4966e;
  margin: 0 auto;
}
.author-block {
  position: absolute;
  bottom: 40px;
  left: 0;
  text-align: left;
  font-size: 10pt;
  color: #786450;
}
.author-block .date {
  font-style: italic;
  font-size: 9pt;
  color: #968270;
}

/* Copyright */
.copyright-page {
  page-break-after: always;
}
.copyright-page h1 {
  font-size: 18pt;
  color: #3c2314;
  margin-bottom: 4px;
}
.copyright-page hr {
  border: none;
  border-top: 1.5px solid #b4966e;
  margin-bottom: 16px;
}
.copyright-box {
  border: 1px solid #cbb38c;
  background: #faf6ef;
  border-radius: 6px;
  padding: 16px 18px;
  font-size: 10.5pt;
  line-height: 1.6;
  color: #2a1e14;
  text-align: justify;
}
.copyright-box .reg {
  font-weight: bold;
  color: #643c1e;
}
.copyright-box .small {
  font-size: 9.5pt;
  color: #6b5640;
}

/* Introduction */
.intro-page {
  page-break-after: always;
}
.intro-page h1 {
  font-size: 20pt;
  color: #3c2314;
  margin-bottom: 4px;
}
.intro-page hr {
  border: none;
  border-top: 1.5px solid #b4966e;
  margin-bottom: 16px;
}
.intro-page p {
  text-align: justify;
  margin-bottom: 8px;
}
.intro-page ol {
  padding-left: 20px;
}
.intro-page ol li {
  margin-bottom: 6px;
  text-align: justify;
}

/* Book pages */
.book-title {
  page-break-before: always;
  text-align: center;
  padding-top: 30px;
  margin-bottom: 10px;
}
.book-title .es {
  font-size: 22pt;
  font-weight: bold;
  color: #3c2314;
}
.book-title .he {
  font-family: ''' + HEB_FAMILY + ''';
  font-size: 30pt;
  color: #3c2314;
  direction: rtl;
}
.book-title hr {
  width: 140px;
  border: none;
  border-top: 1.5px solid #b4966e;
  margin: 12px auto 20px;
}

.chapter-head {
  font-size: 14pt;
  font-weight: bold;
  color: #643c1e;
  text-align: right;
  margin-top: 20px;
  margin-bottom: 8px;
}

/* Verso: hebreo samaritano mas grande y legible, conservando fuente original */
.verse {
  direction: rtl;
  text-align: right;
  font-family: ''' + HEB_FAMILY + ''';
  font-size: 22pt;
  line-height: 2.35;
  margin-bottom: 6px;
  color: #120d08;
  letter-spacing: 0.015em;
}
/* Numero de verso: a la DERECHA, al INICIO del verso */
.verse .vn {
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 11pt;
  font-weight: bold;
  color: #8c5a20;
  vertical-align: super;
  margin-left: 10px;
  direction: ltr;
  unicode-bidi: embed;
}

@media print {
  .no-break { page-break-inside: avoid; }
}
</style>
</head>
<body>
''']

# ── PORTADA ──
html_parts.append(f'''
<div class="title-page">
  <div class="title-he">תורת השמרונים</div>
  <div class="title-es">Lectura Samaritana de la Toráh</div>
  <div class="subtitle">Pentateuco Samaritano vocalizado en hebreo cuadrado</div>
  <hr class="title-line">
  <div class="author-block">
    {AUTOR}<br>
    <span class="date">{datetime.now().strftime("%B %Y")}</span>
  </div>
</div>
''')

# ── DERECHOS DE AUTOR ──
year = datetime.now().year
html_parts.append(f'''
<div class="copyright-page">
<h1>Derechos de Autor</h1>
<hr>
<div class="copyright-box">
<p>&copy; {year} {AUTOR}. Todos los derechos reservados.</p>

<p>La presente obra se encuentra protegida por la <strong>Ley Federal del Derecho de Autor</strong>
de los Estados Unidos Mexicanos, de manera enunciativa y no limitativa por sus
<strong>artículos 13, 162, 163 fracción I y 164 fracción I</strong>, así como por las demás
disposiciones legales aplicables en materia de derechos de autor y propiedad intelectual,
tanto nacionales como los tratados internacionales suscritos por México.</p>

<p>Obra inscrita en el Registro Público del Derecho de Autor del Instituto Nacional del Derecho
de Autor (INDAUTOR) bajo el número de registro:</p>

<p class="reg">Número de Registro INDAUTOR: {REG_INDAUTOR}</p>

<p class="small">Queda estrictamente prohibida la reproducción, distribución, comunicación pública,
transformación o cualquier otra forma de explotación, total o parcial, de esta obra por
cualquier medio o procedimiento, sin la autorización previa y por escrito del titular de los
derechos. Toda utilización deberá respetar el derecho moral de paternidad e integridad de la
obra reconocido a favor del autor.</p>
</div>
</div>
''')

# ── INTRODUCCION ──
html_parts.append('''
<div class="intro-page">
<h1>Introducción</h1>
<hr>

<p>El presente documento contiene la vocalización completa del Pentateuco Samaritano (SP)
en hebreo cuadrado con niqqud (signos vocálicos). Constituye, hasta donde sabemos,
el primer corpus digital que representa la pronunciación samaritana tradicional de la
Toráh en un formato procesable por computadora.</p>

<p>La comunidad samaritana, que hoy cuenta con apenas 800 miembros divididos entre Holon
y el Monte Gerizim, preserva una tradición oral de lectura de la Toráh que difiere
sustancialmente de la pronunciación masorética (tiberiana) conocida por la mayoría de
los estudiosos del hebreo bíblico. Hasta ahora, la única referencia escrita para esta
pronunciación eran los textos impresos de Benyamim Tsedaka y la gramática monumental
de Ze'ev Ben-Hayyim, ambos inaccesibles al procesamiento digital.</p>

<p>El desafío técnico central radicaba en que no existe ningún corpus digital con la
vocalización samaritana. Los intentos de aplicar OCR a los textos impresos de Tsedaka
fracasaron sistemáticamente (Tesseract, ABBYY y modelos especializados), debido a que
los diacríticos vocálicos samaritanos son diminutos y no están soportados por ningún
motor de reconocimiento óptico de caracteres existente.</p>

<p>La solución implementada consiste en un motor de reglas fonológicas (Motor Samaritano v6)
que toma como entrada la vocalización masorética del corpus ETCBC/BHSA y la transforma
mediante las reglas fonológicas documentadas por Ben-Hayyim para la tradición oral samaritana.
El texto consonantal de referencia proviene del corpus digital dt-ucph/sp del Pentateuco
Samaritano.</p>

<p>El proceso de producción involucró los siguientes pasos:</p>

<ol>
<li>Alineamiento del texto consonantal SP con el texto masorético mediante el algoritmo
de Needleman-Wunsch, tolerando variaciones en matres lectionis.</li>
<li>Transferencia de la vocalización masorética al esqueleto consonantal samaritano para
las palabras con emparejamiento exacto o difuso (94.6%).</li>
<li>Aplicación de 13 reglas fonológicas samaritanas: conversión del cholam a qubuts/qamats,
eliminación de sheva, transformación de hataf a vocal plena, ajuste del plural masculino
(-im a -em), entre otras.</li>
<li>Resolución léxica de 4,890 palabras exclusivas del SP mediante armonización con formas
vocalizadas encontradas en otros contextos del corpus.</li>
<li>Curación manual de 63 formas únicas del SP sin paralelo masorético, incluyendo el
emblemático Monte Gerizim.</li>
<li>Correcciones editoriales de post-procesamiento: erradicación global del sin-dot
(la tradición samaritana no distingue shin de sin), aplicación de dagesh protector en
Bet/Kaf/Pe, normalización de participios activos Qal con qamats, ajuste del plural
femenino -ot a -at, y corrección de la partícula negativa a /la/.</li>
</ol>

<p>El resultado es un corpus de 116,208 palabras con cobertura de vocalización del 100%
y calidad fonológica del 100% (medida como ausencia de residuos masoréticos detectables
por las reglas del motor). El emparejamiento MT-SP alcanzó el 94.6% (89.4% exacto +
5.2% difuso).</p>

<p>Es importante señalar que la calidad reportada representa consistencia interna con las
reglas fonológicas implementadas, no una validación contra el "gold standard" de la
pronunciación samaritana oral. Tal validación requeriría acceso digital a los textos
impresos de Tsedaka o a grabaciones fonéticas sistematizadas de la lectura litúrgica
samaritana, recursos que al momento de esta publicación no están disponibles en formato
procesable.</p>

<p>Este corpus se ofrece como herramienta de investigación para lingüistas, biblistas y
estudiosos de las tradiciones textuales del Pentateuco. Los datos están disponibles
también en formato JSON para facilitar su procesamiento computacional.</p>
</div>
''')

# ── TEXTO POR LIBRO ──
for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    name_es = NAMES_ES[b]
    name_he = NAMES_HE[b]
    print(f'{name_es}: {len(data["chapters"])} capítulos...')

    html_parts.append(f'''
<div class="book-title">
  <div class="es">{name_es}</div>
  <div class="he">{name_he}</div>
  <hr>
</div>
''')

    for ch in sorted(data['chapters'].keys(), key=int):
        chap = data['chapters'][ch]
        html_parts.append(f'<div class="chapter-head">Capítulo {ch}</div>\n')

        for vs in sorted(chap.keys(), key=int):
            sam = chap[vs]['sam_reading']
            safe = sam.replace('&', '&amp;').replace('<', '&lt;')
            # Numero al INICIO (derecha en RTL)
            html_parts.append(
                f'<div class="verse"><span class="vn">{vs}</span> {safe}</div>\n'
            )

html_parts.append('</body></html>')

html_path = os.path.join(BASE, '_print_torah_v2.html')
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(''.join(html_parts))

html_size = os.path.getsize(html_path) / (1024 * 1024)
print(f'HTML generado: {html_path} ({html_size:.2f} MB)')

# ── CONVERTIR A PDF CON NAVEGADOR HEADLESS ──
pdf_path = os.path.join(
    BASE, 'Lectura_Samaritana_Torah_MiguelAngelRoanRodriguez_v2.pdf')

if not BROWSER:
    print('ERROR: No se encontró Brave/Chrome/Edge para la conversión a PDF.')
    print('El HTML quedó generado; instala un navegador Chromium o ábrelo e imprime a PDF.')
    sys.exit(2)

print(f'Convirtiendo a PDF con: {BROWSER}')

cmd = [
    BROWSER,
    '--headless',
    '--disable-gpu',
    '--no-sandbox',
    '--run-all-compositor-stages-before-draw',
    '--print-to-pdf=' + pdf_path,
    '--print-to-pdf-no-header',
    html_path
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
if result.returncode != 0:
    print(f'STDERR: {result.stderr}')
    print(f'STDOUT: {result.stdout}')
    sys.exit(1)

pdf_size = os.path.getsize(pdf_path) / (1024 * 1024)
print(f'\nPDF generado: {pdf_path}')
print(f'Tamaño: {pdf_size:.2f} MB')
print('¡Listo!')
