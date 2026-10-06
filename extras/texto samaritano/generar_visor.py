"""
Generador del visor HTML de la Lectura Samaritana
==================================================
Lee los 5 JSON (genesis..deuteronomy) y produce un único archivo
'visor_samaritano.html' autónomo (datos embebidos) que se abre con doble clic,
sin necesidad de servidor.

Por cada palabra se guarda: [lectura_vocalizada, codigo_fuente, glosa, consonantal].
Códigos de fuente:
  e = derivada del MT (exacta)     l = léxico (armonización SP)
  f = derivada del MT (difusa)     c = curada (reconstrucción)
  s = SP sin resolver (residual)   m = plus masorético (no está en el SP)
"""
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']
NAMES = {'genesis': 'Génesis', 'exodus': 'Éxodo', 'leviticus': 'Levítico',
         'numbers': 'Números', 'deuteronomy': 'Deuteronomio'}


def code(w):
    vs = w.get('vocal_source')
    if vs == 'curado':
        return 'c'
    if vs == 'lexicon':
        return 'l'
    m = w.get('match')
    return {'exact': 'e', 'fuzzy': 'f', 'mt_only': 'm', 'sp_only': 's'}.get(m, 'e')


data = {}
for b in ORDER:
    with open(os.path.join(BASE, f'{b}_lectura_samaritana.json'), encoding='utf-8') as f:
        src = json.load(f)
    chapters = {}
    for ch, chap in src['chapters'].items():
        verses = {}
        for vs, verse in chap.items():
            words = []
            for w in verse['words']:
                cw = code(w)
                cons = w.get('sp_cons') or w.get('mt', '')
                words.append([w['sam_reading'], cw, w.get('gloss', ''), cons])
            verses[vs] = {
                'w': words,
                'c': verse.get('sp_consonantal', ''),
                'm': verse.get('mt_vocalized', ''),
            }
        chapters[ch] = verses
    data[b] = {
        'name': NAMES[b],
        'stats': src.get('stats', {}),
        'chapters': chapters,
    }

payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

HTML = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lectura Samaritana de la Torá</title>
<style>
  :root{
    --bg:#f6f1e7; --panel:#fffaf0; --ink:#2b2118; --muted:#8a7a63;
    --line:#e3d8c3; --accent:#7c4a2d; --accent2:#a9763f;
    --e:#2b2118; --f:#1d6a64; --l:#1f5fa6; --c:#9b2d6b; --s:#c0392b; --m:#b08400;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{font-family:"Segoe UI",system-ui,Arial,sans-serif;background:var(--bg);color:var(--ink);}
  header{background:linear-gradient(180deg,#3a2517,#5b3a22);color:#f6e9d6;padding:14px 20px;box-shadow:0 2px 10px rgba(0,0,0,.25)}
  header h1{margin:0;font-size:20px;letter-spacing:.3px;font-weight:600}
  header .sub{font-size:12px;opacity:.8;margin-top:2px}
  .wrap{display:flex;gap:0;height:calc(100vh - 60px)}
  .side{width:230px;min-width:230px;background:var(--panel);border-right:1px solid var(--line);overflow-y:auto;padding:12px}
  .side h2{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin:14px 6px 6px}
  .bookbtn{display:block;width:100%;text-align:left;border:none;background:transparent;color:var(--ink);
    padding:9px 12px;border-radius:8px;cursor:pointer;font-size:15px;margin-bottom:2px}
  .bookbtn:hover{background:#f0e6d2}
  .bookbtn.active{background:var(--accent);color:#fff;font-weight:600}
  .chapgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-top:6px}
  .chapbtn{border:1px solid var(--line);background:#fff;border-radius:6px;padding:7px 0;cursor:pointer;font-size:13px;color:var(--ink)}
  .chapbtn:hover{border-color:var(--accent2);color:var(--accent)}
  .chapbtn.active{background:var(--accent2);color:#fff;border-color:var(--accent2);font-weight:600}
  .main{flex:1;overflow-y:auto;padding:22px 30px 80px}
  .toolbar{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin-bottom:18px;font-size:13px;color:var(--muted)}
  .toolbar label{display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none}
  .nav{display:flex;gap:8px;align-items:center}
  .nav button{border:1px solid var(--line);background:#fff;border-radius:7px;padding:6px 12px;cursor:pointer;font-size:13px}
  .nav button:hover{border-color:var(--accent2);color:var(--accent)}
  .title{font-size:26px;font-weight:700;color:var(--accent);margin:0 0 2px}
  .legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;margin:6px 0 18px;color:var(--muted)}
  .legend span{display:inline-flex;align-items:center;gap:5px}
  .dot{width:11px;height:11px;border-radius:50%;display:inline-block}
  .verse{padding:8px 4px;border-bottom:1px solid #efe7d6;line-height:2.3}
  .vnum{display:inline-block;min-width:30px;color:var(--accent2);font-weight:700;font-size:13px;
    vertical-align:middle;font-family:"Segoe UI",sans-serif;margin-left:6px}
  .heb{font-family:"SBL Hebrew","Taamey Frank CLM","Ezra SIL","Times New Roman",serif;
    direction:rtl;unicode-bidi:isolate;font-size:30px;line-height:2.1}
  .heb .wd{margin:0 .12em;white-space:nowrap}
  .alt{direction:rtl;unicode-bidi:isolate;font-family:"SBL Hebrew","Times New Roman",serif;
    font-size:19px;color:#9a8a70;margin-top:2px;display:none}
  .alt.show{display:block}
  .alt.cons{color:#8a7a63}
  .alt.mt{color:#9a7d5a}
  /* source colors (applied only when .colors active) */
  .colors .c-e{color:var(--e)} .colors .c-f{color:var(--f)} .colors .c-l{color:var(--l)}
  .colors .c-c{color:var(--c)} .colors .c-s{color:var(--s)} .colors .c-m{color:var(--m)}
  .c-m{display:none}
  .showmt .c-m{display:inline}
  .wd[data-g]:hover{outline:2px solid #d9c39a;border-radius:4px;cursor:help}
  #tip{position:fixed;pointer-events:none;background:#2b2118;color:#fdf6e8;padding:6px 9px;border-radius:7px;
    font-size:12.5px;font-family:"Segoe UI",sans-serif;max-width:260px;z-index:50;display:none;box-shadow:0 4px 14px rgba(0,0,0,.3)}
  #tip .gl{color:#f0d9a8}
  #tip .he{font-family:"SBL Hebrew",serif;direction:rtl;font-size:16px}
  .meta{font-size:12px;color:var(--muted);margin-bottom:10px}
  .jump{margin-right:auto;display:flex;gap:6px;align-items:center}
  .jump input{width:54px;border:1px solid var(--line);border-radius:6px;padding:5px 7px;font-size:13px}
</style>
</head>
<body>
<header>
  <h1>Lectura Samaritana de la Torá</h1>
  <div class="sub">Hebreo cuadrado vocalizado · reglas fonológicas samaritanas (Ben-Hayyim) · 116.209 palabras · <span id="buildts"></span></div>
</header>
<div class="wrap">
  <aside class="side">
    <h2>Libro</h2>
    <div id="books"></div>
    <h2>Capítulo</h2>
    <div id="chaps" class="chapgrid"></div>
  </aside>
  <main class="main">
    <div class="toolbar">
      <div class="nav">
        <button id="prev">‹ Anterior</button>
        <button id="next">Siguiente ›</button>
      </div>
      <div class="jump">
        <span>Ir a verso</span>
        <input id="jv" type="number" min="1" placeholder="#">
      </div>
      <label><input type="checkbox" id="cbColors" checked> Colorear por fuente</label>
      <label><input type="checkbox" id="cbCons"> Consonantal (SP)</label>
      <label><input type="checkbox" id="cbMt"> Masorético (MT)</label>
      <label><input type="checkbox" id="cbMtOnly"> Mostrar plus masorético</label>
    </div>
    <h2 class="title" id="title"></h2>
    <div class="meta" id="meta"></div>
    <div class="legend">
      <span><i class="dot" style="background:var(--e)"></i>derivada del MT</span>
      <span><i class="dot" style="background:var(--f)"></i>difusa (matres)</span>
      <span><i class="dot" style="background:var(--l)"></i>léxico (armonización)</span>
      <span><i class="dot" style="background:var(--c)"></i>curada (reconstrucción)</span>
      <span><i class="dot" style="background:var(--m)"></i>plus masorético</span>
    </div>
    <div id="text"></div>
  </main>
</div>
<div id="tip"></div>
<script id="data" type="application/json">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const ORDER = ['genesis','exodus','leviticus','numbers','deuteronomy'];
const SRCNAME = {e:'derivada del MT (exacta)',f:'derivada del MT (difusa)',l:'léxico (armonización SP)',
  c:'curada (reconstrucción)',s:'SP sin resolver',m:'plus masorético (no está en el SP)'};
let curBook='genesis', curChap='1';

const numKeys = o => Object.keys(o).sort((a,b)=>(+a)-(+b));

function renderBooks(){
  const c=document.getElementById('books'); c.innerHTML='';
  ORDER.forEach(b=>{
    const btn=document.createElement('button');
    btn.className='bookbtn'+(b===curBook?' active':'');
    btn.textContent=DATA[b].name;
    btn.onclick=()=>{curBook=b;curChap=numKeys(DATA[b].chapters)[0];renderBooks();renderChaps();renderText();};
    c.appendChild(btn);
  });
}
function renderChaps(){
  const c=document.getElementById('chaps'); c.innerHTML='';
  numKeys(DATA[curBook].chapters).forEach(ch=>{
    const btn=document.createElement('button');
    btn.className='chapbtn'+(ch===curChap?' active':'');
    btn.textContent=ch;
    btn.onclick=()=>{curChap=ch;renderChaps();renderText();window.scrollTo(0,0);
      document.querySelector('.main').scrollTop=0;};
    c.appendChild(btn);
  });
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

function renderText(){
  const bk=DATA[curBook], chap=bk.chapters[curChap];
  document.getElementById('title').textContent=bk.name+' '+curChap;
  const st=bk.stats||{};
  document.getElementById('meta').textContent=
    `${bk.name}: ${numKeys(bk.chapters).length} capítulos · ${st.words_total||'?'} palabras · ${numKeys(chap).length} versos en este capítulo`;
  const out=[];
  numKeys(chap).forEach(vs=>{
    const v=chap[vs];
    const words=v.w.map(w=>{
      const [r,cd,gl,cons]=w;
      const g = gl? ` data-g="${esc(gl)}" data-cd="${cd}" data-cn="${esc(cons||'')}"`:` data-cd="${cd}" data-cn="${esc(cons||'')}"`;
      return `<span class="wd c-${cd}"${g}>${esc(r)}</span>`;
    }).join(' ');
    let block=`<div class="verse" id="v${vs}"><span class="vnum">${vs}</span>`+
      `<span class="heb">${words}</span>`;
    block+=`<div class="alt cons">${esc(v.c||'')}</div>`;
    block+=`<div class="alt mt">${esc(v.m||'')}</div>`;
    block+=`</div>`;
    out.push(block);
  });
  document.getElementById('text').innerHTML=out.join('');
  applyToggles();
}

function applyToggles(){
  const t=document.getElementById('text');
  t.classList.toggle('colors',document.getElementById('cbColors').checked);
  t.classList.toggle('showmt',document.getElementById('cbMtOnly').checked);
  const cons=document.getElementById('cbCons').checked, mt=document.getElementById('cbMt').checked;
  document.querySelectorAll('.alt.cons').forEach(e=>e.classList.toggle('show',cons));
  document.querySelectorAll('.alt.mt').forEach(e=>e.classList.toggle('show',mt));
}

// navigation
function move(d){
  const chs=numKeys(DATA[curBook].chapters); let i=chs.indexOf(curChap)+d;
  if(i>=0&&i<chs.length){curChap=chs[i];}
  else{
    let bi=ORDER.indexOf(curBook)+d;
    if(bi>=0&&bi<ORDER.length){curBook=ORDER[bi];const c2=numKeys(DATA[curBook].chapters);curChap=d>0?c2[0]:c2[c2.length-1];renderBooks();}
  }
  renderChaps();renderText();document.querySelector('.main').scrollTop=0;
}
document.getElementById('prev').onclick=()=>move(-1);
document.getElementById('next').onclick=()=>move(1);
['cbColors','cbCons','cbMt','cbMtOnly'].forEach(id=>document.getElementById(id).onchange=applyToggles);
document.getElementById('jv').onchange=function(){
  const el=document.getElementById('v'+this.value);
  if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.style.background='#fbeecb';
    setTimeout(()=>el.style.background='',1400);}
};
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;
  if(e.key==='ArrowLeft')move(1); if(e.key==='ArrowRight')move(-1);});

// tooltip
const tip=document.getElementById('tip');
document.getElementById('text').addEventListener('mouseover',e=>{
  const w=e.target.closest('.wd'); if(!w)return;
  const g=w.getAttribute('data-g'), cd=w.getAttribute('data-cd'), cn=w.getAttribute('data-cn');
  tip.innerHTML=(cn?`<div class="he">${esc(cn)}</div>`:'')+
    (g?`<div class="gl">${esc(g)}</div>`:'')+
    `<div style="opacity:.7">${SRCNAME[cd]||''}</div>`;
  tip.style.display='block';
});
document.getElementById('text').addEventListener('mousemove',e=>{
  tip.style.left=Math.min(e.clientX+14,window.innerWidth-270)+'px';
  tip.style.top=(e.clientY+16)+'px';
});
document.getElementById('text').addEventListener('mouseout',()=>tip.style.display='none');

document.getElementById('buildts').textContent='Build: __TIMESTAMP__';
renderBooks();renderChaps();renderText();
</script>
</body>
</html>'''

from datetime import datetime
ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
html = HTML.replace('__PAYLOAD__', payload).replace('__TIMESTAMP__', ts)
out_path = os.path.join(BASE, 'visor_samaritano.html')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

size_mb = os.path.getsize(out_path) / (1024 * 1024)
print(f"Generado: {out_path}")
print(f"Tamaño: {size_mb:.2f} MB")
print(f"Libros: {len(data)}  ·  payload: {len(payload)/1024/1024:.2f} MB")
