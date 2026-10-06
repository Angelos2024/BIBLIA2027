"""Servidor HTTP sin caché para el visor interlineal con edición de glosas ES."""
import http.server
import json
import socketserver
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Candado de capítulos cerrados (seguridad a nivel de persistencia).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'motores' / 'scripts'))
try:
    import candado
except Exception:  # pragma: no cover
    candado = None


def _cap_cerrado(book, chapter):
    return bool(candado and candado.esta_bloqueado(book, chapter))


def _refresh_estadistica_async():
    """Realimenta el modelo estadístico de estilo (en 2º plano, no bloquea)."""
    def _work():
        try:
            import construir_estadistica
            construir_estadistica.construir(incluir_abiertos=False, verbose=False)
        except Exception:
            pass
    threading.Thread(target=_work, daemon=True).start()

# Serializa las mutaciones (guardado/globalización) para que el servidor
# multihilo no entrelace escrituras ni caches de un mismo archivo.
_WRITE_LOCK = threading.RLock()

# Caché en memoria del libro en edición (clave: ruta -> (mtime_ns, data)).
# Evita re-parsear 13–27 MB en cada guardado; se invalida por mtime, de modo
# que cualquier escritura externa (motores) se detecta y se relee.
_BOOK_CACHE: dict[str, tuple] = {}


def load_book(path: Path) -> dict:
    """Carga el _final.json con caché por mtime (no re-parsea si no cambió)."""
    key = str(path)
    try:
        mt = path.stat().st_mtime_ns
    except OSError:
        mt = None
    cached = _BOOK_CACHE.get(key)
    if cached is not None and cached[0] == mt:
        return cached[1]
    data = json.loads(path.read_text(encoding='utf-8'))
    _BOOK_CACHE[key] = (mt, data)
    return data


def _remember_book(path: Path, data: dict) -> None:
    """Actualiza la caché tras escribir (para que el siguiente guardado no relea)."""
    try:
        mt = path.stat().st_mtime_ns
    except OSError:
        mt = None
    _BOOK_CACHE[str(path)] = (mt, data)

PORT = 7080
ROOT = Path(__file__).resolve().parent          # carpeta visor/
REPO = ROOT.parent                              # raíz BIBLIA2027/
DATA_DIR = REPO / 'data_master'                 # *_final.json (interlineal)
FUENTES_DIR = REPO / 'fuentes'                  # glosas, diccionario, etc.
RV_DIR = REPO / 'data_master'                   # rv1960_<slug>.json (copia local)
GLOSAS_PATH = FUENTES_DIR / 'glosas_personales.json'
MARCAS_PATH = FUENTES_DIR / 'marcas_tokens.json'
REFUERZO_PATH = FUENTES_DIR / 'refuerzo_estilo.json'
_MARCA_COLORES = {'rojo', 'azul', 'verde'}
_MARCAS_EMPTY = {
    'version': 1,
    'actualizado': '',
    '_descripcion': (
        'Marcas de resaltado por token (visor: clic en hebreo base). '
        'rojo=transliterar · azul=globalizar término (preguntar antes) · '
        'verde=error para reforzar el motor. No toca data_master ni el candado.'
    ),
    'marcas': [],
}
ANGELOS_RV = Path(
    r'C:\Users\Angelos\Documents\GitHub\Local-consults\estudio\angelos\librosRV1960'
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Caché en memoria del registro de glosas (evita re-leer 2.8 MB por guardado).
_REG_CACHE: dict = {'mtime': None, 'data': None}


def load_registry() -> dict:
    try:
        mt = GLOSAS_PATH.stat().st_mtime_ns
    except OSError:
        mt = None
    if _REG_CACHE['data'] is not None and _REG_CACHE['mtime'] == mt:
        return _REG_CACHE['data']
    if not GLOSAS_PATH.exists():
        return {'version': 1, 'updated': '', 'global': [], 'contexto': []}
    try:
        reg = json.loads(GLOSAS_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'version': 1, 'updated': '', 'global': [], 'contexto': []}
    reg.setdefault('global', [])
    reg.setdefault('contexto', [])
    _REG_CACHE['mtime'] = mt
    _REG_CACHE['data'] = reg
    return reg


def save_registry(reg: dict):
    reg['updated'] = _now_iso()
    # Registro legible (indent) para facilitar lectura/edición manual; los datos
    # interlineales (_final.json) siguen guardándose compactos.
    atomic_write_json(GLOSAS_PATH, reg, indent=2)
    try:
        _REG_CACHE['mtime'] = GLOSAS_PATH.stat().st_mtime_ns
    except OSError:
        _REG_CACHE['mtime'] = None
    _REG_CACHE['data'] = reg


def upsert_context_rule(book: str, chapter: int, verse: int,
                        pair_idx: int, hw_idx: int, field: str,
                        prefix_idx: int, has_suffix: bool,
                        new_es: str, hw_snapshot: dict):
    """Inserta o actualiza una regla de contexto en glosas_personales.json.
    Esta regla pisará el valor cargado de _final.json al re-aplicarse en runtime,
    garantizando que las ediciones del usuario sean persistentes a través de
    recargas del libro."""
    reg = load_registry()
    ctx = reg['contexto']
    norm_pidx = prefix_idx if (field == 'prefix_es' and prefix_idx >= 0) else None
    role = 'prefix' if field == 'prefix_es' else 'stem'

    target = None
    for r in ctx:
        m = r.get('match') or {}
        if (m.get('book') == book and
                m.get('chapter') == chapter and
                m.get('verse') == verse and
                m.get('pairIdx') == pair_idx and
                m.get('hwIdx') == hw_idx and
                m.get('field') == field and
                m.get('prefixIdx') == norm_pidx):
            target = r
            break

    now = _now_iso()
    if target:
        target.setdefault('after', {})['es'] = new_es
        target['updated_at'] = now
        m = target.setdefault('match', {})
        m['combined'] = bool(has_suffix)
        m['strongs'] = hw_snapshot.get('strongs', '') or ''
        m['he_form'] = hw_snapshot.get('he_form', '') or ''
        m['role'] = role
    else:
        rid = f'ctx-{book}-{chapter}-{verse}-{pair_idx}-{hw_idx}'
        if role == 'prefix':
            rid += f'-pre{prefix_idx}'
        ctx.append({
            'id': rid,
            'scope': 'context',
            'match': {
                'book': book,
                'chapter': chapter,
                'verse': verse,
                'pairIdx': pair_idx,
                'hwIdx': hw_idx,
                'field': field,
                'prefixIdx': norm_pidx,
                'combined': bool(has_suffix),
                'strongs': hw_snapshot.get('strongs', '') or '',
                'he_form': hw_snapshot.get('he_form', '') or '',
                'prefix_morph': '',
                'prefix_label': '',
                'he_prefix': '',
                'role': role,
            },
            'before': {'es': str(hw_snapshot.get('es', '') or '')},
            'after': {'es': new_es},
            'created_at': now,
        })
    save_registry(reg)


def upsert_global_rule(strongs: str, new_es: str,
                       he_form: str = '', he_morph: str = '',
                       consonants: str = '', morph: str = '',
                       mode: str = 'lemma', book: str = ''):
    """Inserta o actualiza una regla global en glosas_personales.json.

    Dos capas independientes que NO colisionan:
      mode='lemma' → regla por SOLO Strong (todas las formas).
      mode='form'  → regla por Strong + forma CONSONÁNTICA + morfología (solo
                     esa flexión; separa homógrafos con morfología distinta).
    La identidad de la regla incluye `mode` y, en 'form', las `consonants` y la
    `morph`, de modo que pueden coexistir una regla de lema y varias reglas por
    forma para el mismo Strong."""
    reg = load_registry()
    glb = reg['global']
    target_strong = normalize_strongs(strongs)
    cons = consonants_only(he_form) if (mode == 'form' and not consonants) else consonants
    morph = morph or (he_morph if mode == 'form' else '')

    def same_identity(m):
        if m.get('role') != 'stem':
            return False
        if normalize_strongs(m.get('strongs', '')) != target_strong:
            return False
        # Una regla acotada a un libro es distinta de la global y de la de
        # otro libro: el `book` forma parte de la identidad.
        if (m.get('book', '') or '') != (book or ''):
            return False
        rmode = m.get('mode', 'lemma')
        if rmode != mode:
            return False
        if mode == 'form':
            return ((m.get('consonants', '') or '') == (cons or '') and
                    (m.get('morph', '') or '') == (morph or ''))
        return True

    target = None
    for r in glb:
        if same_identity(r.get('match') or {}):
            target = r
            break

    now = _now_iso()
    if target:
        target.setdefault('after', {})['es'] = new_es
        target['updated_at'] = now
        # Asegura metadatos de identidad actualizados
        m = target.setdefault('match', {})
        m['mode'] = mode
        if book:
            m['book'] = book
        if mode == 'form':
            m['consonants'] = cons or ''
            m['morph'] = morph or ''
    else:
        bprefix = f'{book}-' if book else ''
        if mode == 'form':
            mtag = (morph or 'x').replace('.', '').replace(' ', '')[:16]
            rid = f'g-{bprefix}form-{target_strong}-{cons or "x"}-{mtag}'
        else:
            rid = f'g-{bprefix}stem-{target_strong}'
            if he_morph:
                rid += f'-{he_morph}'
        match = {
            'role': 'stem',
            'strongs': target_strong,
            'he_form': he_form,
            'he_morph': he_morph,
            'mode': mode,
        }
        if book:
            match['book'] = book
        if mode == 'form':
            match['consonants'] = cons or ''
            match['morph'] = morph or ''
        glb.append({
            'id': rid,
            'scope': ('book' if book else 'global'),
            'match': match,
            'before': {'es': ''},
            'after': {'es': new_es},
            'created_at': now,
        })
    save_registry(reg)

os.chdir(ROOT)


def resolve_data_file(name: str):
    """Mapea un nombre pedido bajo /data/ a su ubicación real tras la
    reorganización de carpetas. Devuelve un Path o None."""
    if not name or '/' in name or '\\' in name or '..' in name:
        return None
    if name.endswith('_final.json'):
        return DATA_DIR / name
    if name.startswith('rv1960_') or name.startswith('traduccion_personal_'):
        return RV_DIR / name
    if name in ('glosas_personales.json', 'diccionario_hebreo.json',
                'candado_capitulos.json', 'marcas_tokens.json'):
        return FUENTES_DIR / name
    # Fallback: data_master primero, luego fuentes.
    for base in (DATA_DIR, FUENTES_DIR):
        cand = base / name
        if cand.exists():
            return cand
    return None


def atomic_write_json(path: Path, data, *, indent=None):
    """Escribe JSON de forma atómica: tmp + rename.

    Por defecto compacto (para los _final.json, que son enormes). Con `indent`
    escribe legible (lo usa el registro de glosas, pensado para lectura/edición
    humana).

    Serializa a bytes en memoria y escribe en un solo bloque: json.dump(data, f)
    escribe en muchos trozos pequeños y es ~5× más lento que serializar y hacer
    un único f.write() (medido: 995 ms vs 180 ms en un libro de 13 MB). La salida
    es idéntica byte a byte, así que NO altera el orden ni la estructura."""
    if indent:
        payload = json.dumps(data, ensure_ascii=False, indent=indent).encode('utf-8')
    else:
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix='.tmp.json', dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(payload)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def normalize_strongs(raw: str) -> str:
    if not raw:
        return ''
    s = raw.strip().upper()
    m = re.match(r'^([HG])0*(\d+)', s)
    return f'{m.group(1)}{m.group(2)}' if m else s


# Forma consonántica: elimina niqqud, cantilación, dagesh, maqaf y signos de
# puntuación, dejando solo consonantes. DEBE coincidir con
# TraduccionTokens.consonantsOnly del cliente para que el emparejamiento sea
# idéntico en servidor y navegador.
_CONS_RE1 = re.compile(r'[\u0591-\u05BD\u05BF\u05C1-\u05C7\u05BE\u05C0\u05F3\u05F4]')
_CONS_RE2 = re.compile(r'[\s\-\u05BE\u2013]+')


def consonants_only(s: str) -> str:
    if not s:
        return ''
    s = _CONS_RE1.sub('', s)
    s = _CONS_RE2.sub('', s)
    return s.strip()


# Tetragrámaton (qere perpetuo): la vocal define la lectura del Nombre divino.
#   hiriq (U+05B4) → 'Elohim ; holam (U+05B9/U+05BA) → Adonai ; resto → Hashem.
# El emparejado global ignora vocales, así que H3068 SIEMPRE se enruta por aquí.
_YHWH_HIRIQ = '\u05B4'
_YHWH_HOLAM = ('\u05B9', '\u05BA')


def tetragrammaton_es(he_form: str, default: str = 'Hashem') -> str:
    s = he_form or ''
    if _YHWH_HIRIQ in s:
        return "'Elohim"
    if any(h in s for h in _YHWH_HOLAM):
        return 'Adonai'
    return default or 'Hashem'


def token_matches(hw: dict, strong: str, consonants, morph=None) -> bool:
    """Identidad única para 'la misma palabra' en TODO el motor de globalización.

    - Exige coincidir el número Strong normalizado.
    - Si `consonants` no es None, exige además misma forma CONSONÁNTICA
      (ignora vocales/cantilación).
    - Si `morph` no es None, exige además misma MORFOLOGÍA (he_morph). Esto
      separa homógrafos del mismo Strong (p. ej. דַּעַת sustantivo vs infinitivo
      verbal), de modo que 'esta forma' no afecte otras formas distintas.
    El Strong vacío NUNCA coincide (no se puede globalizar sin identidad).
    """
    if not strong:
        return False
    if normalize_strongs(hw.get('strongs', '')) != strong:
        return False
    if consonants is not None:
        if consonants_only(hw.get('he_form', '') or '') != consonants:
            return False
    if morph is not None:
        if (hw.get('he_morph', '') or '') != morph:
            return False
    return True


# ── Índice por Strong (cacheado por mtime) ──────────────────────────────────
# Evita reescanear los 39 libros en cada acción y garantiza que el conteo, la
# búsqueda y el cambio usen EXACTAMENTE el mismo conjunto de ocurrencias.
_INDEX_CACHE = {'sig': None, 'data': None}


def _data_signature():
    sig = []
    for fp in sorted(DATA_DIR.glob('*_final.json')):
        try:
            sig.append((fp.name, fp.stat().st_mtime_ns, fp.stat().st_size))
        except OSError:
            pass
    return tuple(sig)


def build_strong_index():
    """dict: strong -> lista de ocurrencias (solo raíces/stems con Strong)."""
    sig = _data_signature()
    if _INDEX_CACHE['sig'] == sig and _INDEX_CACHE['data'] is not None:
        return _INDEX_CACHE['data']
    index = {}
    for fp in sorted(DATA_DIR.glob('*_final.json')):
        slug = fp.stem.replace('_final', '')
        try:
            data = json.loads(fp.read_text(encoding='utf-8'))
        except Exception:
            continue
        for v in data.get('verses', []):
            ch, vs = v.get('chapter'), v.get('verse')
            for pi, p in enumerate(v.get('pairs', [])):
                if p.get('kind') == 'gk_add':
                    continue
                for hi, hw in enumerate(p.get('he_words', [])):
                    st = normalize_strongs(hw.get('strongs', ''))
                    if not st:
                        continue
                    he = hw.get('he_form', '') or ''
                    index.setdefault(st, []).append({
                        'book': slug,
                        'chapter': ch,
                        'verse': vs,
                        'pairIdx': pi,
                        'hwIdx': hi,
                        'he_form': he,
                        'consonants': consonants_only(he),
                        'he_morph': hw.get('he_morph', '') or '',
                        'es': hw.get('es', '') or '',
                    })
    _INDEX_CACHE['sig'] = sig
    _INDEX_CACHE['data'] = index
    return index


def strong_aggregate(occs):
    """Agrega ocurrencias de un Strong en un resumen para mapeo/validación.

    Devuelve glosas distintas (equivalencias) con su conteo, formas y morfos.
    `glosses` se ordena por frecuencia descendente. Una glosa vacía cuenta como
    '∅' (sin glosa)."""
    glosses = {}
    forms = {}
    morphs = {}
    for o in occs:
        es = (o.get('es') or '').strip()
        key = es if es else '∅'
        glosses[key] = glosses.get(key, 0) + 1
        he = o.get('he_form') or ''
        if he:
            forms[he] = forms.get(he, 0) + 1
        mo = o.get('he_morph') or ''
        if mo:
            morphs[mo] = morphs.get(mo, 0) + 1
    gl_sorted = sorted(glosses.items(), key=lambda kv: (-kv[1], kv[0]))
    # equivalencias = glosas NO vacías distintas
    distinct_es = [g for g, _ in gl_sorted if g != '∅']
    # conteo exacto por forma flexionada = consonantes + morfología (capa
    # "esta forma"). Clave: "<consonantes>\u0001<morph>". Debe coincidir con el
    # cálculo del cliente.
    form_counts = {}
    for o in occs:
        c = consonants_only(o.get('he_form') or '')
        if not c:
            continue
        key = c + '\u0001' + (o.get('he_morph') or '')
        form_counts[key] = form_counts.get(key, 0) + 1
    return {
        'total': len(occs),
        'glosses': [{'es': g, 'count': c} for g, c in gl_sorted],
        'distinct_glosses': len(distinct_es),
        'multiple_equiv': len(distinct_es) > 1,
        'forms': sorted(forms.keys()),
        'consonant_forms': sorted({consonants_only(f) for f in forms}),
        'form_counts': form_counts,
        'morphs': sorted(morphs.keys()),
    }


def build_strong_map():
    """dict: strong -> resumen agregado (para listado/mapeo de Strongs)."""
    index = build_strong_index()
    return {st: strong_aggregate(occs) for st, occs in index.items()}


def strong_info(strongs: str, scope: str = 'all'):
    """Resumen agregado de un Strong (para validar antes de globalizar).
    scope='all' o 'book:<slug>' para acotar al libro actual."""
    target = normalize_strongs(strongs)
    if not target:
        return None
    index = build_strong_index()
    occs = index.get(target, [])
    if scope.startswith('book:'):
        slug = scope.split(':', 1)[1]
        occs = [o for o in occs if o.get('book') == slug]
    info = strong_aggregate(occs)
    info['strongs'] = target
    info['scope'] = scope
    return info


def _personal_path(book: str) -> Path:
    slug = (book or '').strip().lower().replace('_final.json', '').replace('.json', '')
    return DATA_DIR / f'traduccion_personal_{slug}.json'


def save_personal_verse(book: str, chapter: int, verse: int, new_text: str):
    """Corrige UNA línea de texto personal YA vigente.

    No crea versos nuevos, no toca huecos vacíos (ahí sigue el RV1960) y no
    mueve el resto del capítulo. El candado del interlineal no aplica: esta
    capa es el archivo traduccion_personal_<libro>.json.
    """
    text = str(new_text or '').strip()
    if not text:
        raise ValueError('La línea personal no puede quedar vacía.')
    path = _personal_path(book)
    if not path.exists():
        raise FileNotFoundError(f'{path.name} no existe')
    cap = int(chapter)
    vs = int(verse)
    if cap < 1 or vs < 1:
        raise ValueError(f'Versículo inválido: {cap}:{vs}')
    with _WRITE_LOCK:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError('traducción personal: formato inesperado')
        if cap > len(data):
            raise ValueError(f'No hay capítulo {cap} en el texto personal')
        chap = data[cap - 1]
        if not isinstance(chap, list):
            raise ValueError(f'Capítulo {cap}: formato inesperado')
        if vs > len(chap):
            raise ValueError(f'No hay verso {cap}:{vs} en el texto personal')
        prev = chap[vs - 1]
        if not isinstance(prev, str) or not prev.strip():
            raise PermissionError(
                f'{cap}:{vs} no tiene línea personal vigente (sigue el RV1960).')
        if prev == text:
            return 0
        chap[vs - 1] = text
        payload = json.dumps(data, ensure_ascii=False, indent=1)
        if not payload.endswith('\n'):
            payload += '\n'
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix='.tmp.json', dir=str(path.parent))
        try:
            with os.fdopen(tmp_fd, 'wb') as f:
                f.write(payload.encode('utf-8'))
            os.replace(tmp_path, str(path))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return 1


def save_single_gloss(book: str, chapter: int, verse: int,
                      pair_idx: int, hw_idx: int, new_es: str,
                      field: str = 'es', prefix_idx: int = -1,
                      has_suffix: bool = False):
    """Guarda una sola glosa ES en el archivo _final.json del libro.
    field='es'        → escribe en he_words[hw_idx]['es']       (stem)
    field='prefix_es' → escribe en he_words[hw_idx]['prefix_es'][prefix_idx]
    has_suffix=True   → además vacía prs_suffix.es para evitar duplicación
                        (el texto completo ya incluye el sufijo)
    """
    path = DATA_DIR / f'{book}_final.json'
    if not path.exists():
        raise FileNotFoundError(f'{path.name} no existe')
    if _cap_cerrado(book, chapter):
        raise PermissionError(
            f'Capítulo CERRADO ({book} {chapter}): está bajo candado y no se puede editar. '
            f'Ábrelo con el botón Cerrado→Cerrar si quieres modificarlo.')
    with _WRITE_LOCK:
        data = load_book(path)
        verse_obj = next(
            (v for v in data.get('verses', [])
             if v.get('chapter') == chapter and v.get('verse') == verse), None)
        if not verse_obj:
            raise ValueError(f'Versículo {chapter}:{verse} no encontrado')
        pairs = verse_obj.get('pairs') or []
        if pair_idx < 0 or pair_idx >= len(pairs):
            raise ValueError(f'Par inválido: {pair_idx}')
        he_words = pairs[pair_idx].get('he_words') or []
        if hw_idx < 0 or hw_idx >= len(he_words):
            raise ValueError(f'he_word inválido: {hw_idx}')

        hw = he_words[hw_idx]
        # Snapshot del valor previo antes de modificar (para registrar `before`)
        hw_snapshot = {
            'es': hw.get('es', ''),
            'strongs': hw.get('strongs', ''),
            'he_form': hw.get('he_form', ''),
        }
        if field == 'prefix_es' and prefix_idx >= 0:
            plist = list(hw.get('prefix_es') or [])
            pforms = hw.get('prefix_forms') or []
            # Auto-alinear: prefix_es puede venir más corto que prefix_forms
            # (p.ej. si una glosa se consolidó en la raíz y quedó prefix_es=[]).
            # Mientras el índice esté dentro de los prefijos hebreos reales, se
            # rellena con '' en vez de fallar en silencio.
            if prefix_idx >= len(plist):
                if prefix_idx < len(pforms):
                    plist.extend([''] * (prefix_idx + 1 - len(plist)))
                else:
                    raise ValueError(
                        f'prefix_idx {prefix_idx} fuera de rango '
                        f'(len_es={len(plist)}, len_forms={len(pforms)})')
            hw_snapshot['es'] = plist[prefix_idx]
            plist[prefix_idx] = new_es
            hw['prefix_es'] = plist
        else:
            hw['es'] = new_es
            if has_suffix and hw.get('prs_suffix'):
                hw['prs_suffix']['es'] = ''

        atomic_write_json(path, data)
        _remember_book(path, data)

        # Persistencia en el registry de glosas personales para que el patch
        # se re-aplique al recargar y sobreviva re-ejecuciones de motores que
        # reconstruyan _final.json desde fuentes.
        upsert_context_rule(
            book=book, chapter=chapter, verse=verse,
            pair_idx=pair_idx, hw_idx=hw_idx, field=field,
            prefix_idx=prefix_idx, has_suffix=has_suffix,
            new_es=new_es, hw_snapshot=hw_snapshot,
        )
    return 1


def globalize_by_strongs(strongs: str, new_es: str, scope: str = 'all',
                         mode: str = 'lemma', he_form: str = '',
                         he_morph: str = ''):
    """Cambia la glosa ES de tokens (raíces) según la capa elegida.

    mode='lemma' → TODAS las formas con ese Strong.
    mode='form'  → SOLO la misma forma flexionada: mismo Strong + mismas
                   consonantes (ignora vocales/cantilación) + misma morfología
                   (he_morph). No toca otras flexiones distintas del mismo Strong
                   ni homógrafos con morfología diferente.
    scope='all' → todos los libros; scope='book:genesis' → solo ese libro.
    Solo afecta RAÍCES (hw['es']); nunca prefijos ni sufijos sueltos. Al cambiar
    una raíz con sufijo pronominal, vacía prs_suffix.es para evitar duplicación.
    Retorna (total_cambiados, libros_afectados)."""
    target = normalize_strongs(strongs)
    if not target:
        raise ValueError('Strong vacío')

    consonants = consonants_only(he_form) if mode == 'form' else None
    morph = (he_morph or '') if mode == 'form' else None
    if mode == 'form' and not consonants:
        raise ValueError('Forma consonántica vacía para mode="form"')

    if scope.startswith('book:'):
        book_slug = scope.split(':', 1)[1]
        files = [DATA_DIR / f'{book_slug}_final.json']
    else:
        book_slug = ''
        files = sorted(DATA_DIR.glob('*_final.json'))

    total = 0
    books = []
    sample_he_form = he_form or ''
    sample_he_morph = he_morph or ''
    for fpath in files:
        if not fpath.exists():
            continue
        data = json.loads(fpath.read_text(encoding='utf-8'))
        slug_f = fpath.stem.replace('_final', '')
        changed = 0
        for v in data.get('verses', []):
            if _cap_cerrado(slug_f, v.get('chapter')):
                continue  # candado: no tocar capítulos cerrados
            for p in v.get('pairs', []):
                if p.get('kind') == 'gk_add':
                    continue
                for hw in p.get('he_words', []):
                    if token_matches(hw, target, consonants, morph):
                        if not sample_he_form:
                            sample_he_form = hw.get('he_form', '') or ''
                        if not sample_he_morph:
                            sample_he_morph = hw.get('he_morph', '') or ''
                        # Tetragrámaton: el valor se enruta por la vocal del token
                        # (Hashem/Adonai/'Elohim) y nunca se uniforma por Strong.
                        val = tetragrammaton_es(hw.get('he_form'), new_es) \
                            if target == 'H3068' else new_es
                        if hw.get('es', '') != val:
                            hw['es'] = val
                            if hw.get('prs_suffix'):
                                hw['prs_suffix']['es'] = ''
                            changed += 1
        if changed:
            if candado:
                candado.reasegurar(slug_f, data)  # blindaje: restaura sellados
            atomic_write_json(fpath, data)
            books.append(slug_f)
            total += changed

    # Registro global persistente: aún si el scope era un solo libro, la regla
    # se guarda globalmente para que cualquier carga futura aplique el cambio.
    # Se guarda con el MISMO predicado usado para cambiar (mode + consonantes en
    # 'form'), de modo que la re-aplicación coincida con el conjunto modificado.
    if total > 0:
        upsert_global_rule(
            strongs=target, new_es=new_es,
            he_form=sample_he_form, he_morph=sample_he_morph,
            consonants=(consonants or ''), morph=(morph if morph is not None else ''),
            mode=mode, book=book_slug,
        )
    return total, books


def count_strongs_occurrences(strongs: str):
    """Cuenta tokens con ese Strong (vía índice; idéntico al conjunto que
    globaliza). Devuelve (total, n_libros)."""
    target = normalize_strongs(strongs)
    if not target:
        return 0, 0
    occs = build_strong_index().get(target, [])
    n_books = len({o['book'] for o in occs})
    return len(occs), n_books


def _verse_context_tokens(verse, target_pi, target_hi):
    """Construye la lista ordenada de tokens (he + es) del verso para mostrar
    contexto. El token OBJETIVO se separa en prefijo(s) / raíz / sufijo para que
    el resaltado marque EXACTAMENTE la glosa editable (la raíz = hw['es']) y no
    se desborde sobre el artículo u otras partes."""
    toks = []
    for pi, p in enumerate(verse.get('pairs', [])):
        if p.get('kind') == 'gk_add':
            continue
        for hi, hw in enumerate(p.get('he_words', [])):
            is_target = (pi == target_pi and hi == target_hi)
            pref_forms = hw.get('prefix_forms') or []
            pref_es = [g for g in (hw.get('prefix_es') or []) if g]
            suf = hw.get('prs_suffix') or {}

            if is_target:
                # prefijo(s) → sin resaltar
                if pref_es:
                    toks.append({
                        'he': ''.join(pref_forms),
                        'es': ' '.join(pref_es),
                        'target': False,
                    })
                # raíz → resaltada (coincide con el campo editable)
                toks.append({
                    'he': hw.get('he_form') or '',
                    'es': hw.get('es', '') or '',
                    'target': True,
                })
                # sufijo pronominal → sin resaltar
                if suf.get('es'):
                    toks.append({
                        'he': suf.get('he_form') or '',
                        'es': suf['es'],
                        'target': False,
                    })
            else:
                he = ''.join(pref_forms) + (hw.get('he_form') or '')
                if suf.get('he_form'):
                    he += suf['he_form']
                es_parts = list(pref_es)
                if hw.get('es'):
                    es_parts.append(hw['es'])
                if suf.get('es'):
                    es_parts.append(suf['es'])
                toks.append({
                    'he': he,
                    'es': ' '.join(es_parts),
                    'target': False,
                })
    return toks


def find_occurrences(strongs: str, scope: str = 'all', limit: int = 800):
    """Devuelve todas las ocurrencias del Strong con su contexto de verso.
    Cada item: {book, chapter, verse, pairIdx, hwIdx, es, he_form, he_morph,
    tokens:[{he,es,target}]}. scope='all' o 'book:<slug>'."""
    target = normalize_strongs(strongs)
    if not target:
        return [], 0

    if scope.startswith('book:'):
        slug = scope.split(':', 1)[1]
        files = [DATA_DIR / f'{slug}_final.json']
    else:
        files = sorted(DATA_DIR.glob('*_final.json'))

    occ = []
    total = 0
    for fpath in files:
        if not fpath.exists():
            continue
        slug = fpath.stem.replace('_final', '')
        try:
            data = json.loads(fpath.read_text(encoding='utf-8'))
        except Exception:
            continue
        for v in data.get('verses', []):
            ch = v.get('chapter')
            vs = v.get('verse')
            for pi, p in enumerate(v.get('pairs', [])):
                if p.get('kind') == 'gk_add':
                    continue
                for hi, hw in enumerate(p.get('he_words', [])):
                    if normalize_strongs(hw.get('strongs', '')) != target:
                        continue
                    total += 1
                    if len(occ) >= limit:
                        continue
                    occ.append({
                        'book': slug,
                        'chapter': ch,
                        'verse': vs,
                        'pairIdx': pi,
                        'hwIdx': hi,
                        'es': hw.get('es', '') or '',
                        'he_form': hw.get('he_form', '') or '',
                        'he_morph': hw.get('he_morph', '') or '',
                        'tokens': _verse_context_tokens(v, pi, hi),
                    })
    return occ, total


def _marca_key(m: dict) -> tuple:
    pidx = m.get('prefixIdx')
    try:
        pidx_n = int(pidx) if pidx is not None and pidx != '' else -1
    except (TypeError, ValueError):
        pidx_n = -1
    return (
        str(m.get('book') or ''),
        int(m.get('chapter') or 0),
        int(m.get('verse') or 0),
        int(m.get('pairIdx') or 0),
        int(m.get('hwIdx') or 0),
        pidx_n,
    )


def load_marcas() -> dict:
    if not MARCAS_PATH.exists():
        return {
            'version': 1,
            'actualizado': '',
            '_descripcion': _MARCAS_EMPTY['_descripcion'],
            'marcas': [],
        }
    try:
        data = json.loads(MARCAS_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {
            'version': 1,
            'actualizado': '',
            '_descripcion': _MARCAS_EMPTY['_descripcion'],
            'marcas': [],
        }
    if not isinstance(data, dict):
        return {
            'version': 1,
            'actualizado': '',
            '_descripcion': _MARCAS_EMPTY['_descripcion'],
            'marcas': [],
        }
    data.setdefault('marcas', [])
    if not isinstance(data['marcas'], list):
        data['marcas'] = []
    return data


def save_marcas(data: dict) -> None:
    data['actualizado'] = _now_iso()
    data['version'] = int(data.get('version') or 1)
    atomic_write_json(MARCAS_PATH, data, indent=2)


_HE_CONS = re.compile(r'[\u05D0-\u05EA]')
_NIQ_HE = re.compile(r'[\u0591-\u05C7]')


def _esqueleto_he(s: str) -> str:
    s = _NIQ_HE.sub('', s or '')
    return ''.join(_HE_CONS.findall(s))


def load_refuerzo() -> dict:
    empty = {
        'version': 1,
        'actualizado': '',
        '_descripcion': (
            'Refuerzo de estilo desde marcas VERDES. El hebreo identifica el token; '
            'el motor aprende el español es_antes → es_despues.'
        ),
        'entradas': [],
    }
    if not REFUERZO_PATH.exists():
        return empty
    try:
        data = json.loads(REFUERZO_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    data.setdefault('entradas', [])
    if not isinstance(data['entradas'], list):
        data['entradas'] = []
    return data


def save_refuerzo(data: dict) -> None:
    data['actualizado'] = _now_iso()
    data['version'] = int(data.get('version') or 1)
    atomic_write_json(REFUERZO_PATH, data, indent=2)
    try:
        import estilo_usuario
        estilo_usuario._refuerzo = None
    except Exception:
        pass


def upsert_refuerzo_verde(payload: dict) -> None:
    """Anota tu español (antes→después) para que el motor REFUERZO lo auto-aplique."""
    despues = str(payload.get('es_despues') or payload.get('es') or '').strip()
    if not despues:
        return
    he = str(payload.get('he') or '')
    try:
        prefix_idx = int(payload['prefixIdx']) if payload.get('prefixIdx') not in (None, '') else -1
    except (TypeError, ValueError):
        prefix_idx = -1
    rec = {
        'book': str(payload.get('book') or ''),
        'chapter': int(payload.get('chapter') or 0),
        'verse': int(payload.get('verse') or 0),
        'pairIdx': int(payload.get('pairIdx') or 0),
        'hwIdx': int(payload.get('hwIdx') or 0),
        'prefixIdx': prefix_idx,
        'he': he,
        'esqueleto': _esqueleto_he(he),
        'strongs': str(payload.get('strongs') or ''),
        'morph': str(payload.get('morph') or ''),
        'es_antes': str(payload.get('es_antes') or '').strip(),
        'es_despues': despues,
        'at': _now_iso(),
    }
    key = _marca_key(rec)
    with _WRITE_LOCK:
        data = load_refuerzo()
        entradas = []
        for e in data.get('entradas') or []:
            if _marca_key(e) == key:
                if not rec['es_antes']:
                    rec['es_antes'] = str(e.get('es_antes') or '').strip()
                continue
            entradas.append(e)
        entradas.append(rec)
        data['entradas'] = entradas
        save_refuerzo(data)


def upsert_marca(payload: dict) -> dict:
    """Crea/actualiza/borra una marca de un token-stem. color vacío = borrar."""
    book = str(payload.get('book') or '').strip()
    chapter = int(payload['chapter'])
    verse = int(payload['verse'])
    pair_idx = int(payload['pairIdx'])
    hw_idx = int(payload['hwIdx'])
    try:
        prefix_idx = int(payload['prefixIdx']) if payload.get('prefixIdx') not in (None, '') else -1
    except (TypeError, ValueError):
        prefix_idx = -1
    color = str(payload.get('color') or '').strip().lower()
    if color and color not in _MARCA_COLORES:
        raise ValueError(f'color no válido: {color}')
    if not book:
        raise ValueError('falta book')

    rec = {
        'book': book,
        'chapter': chapter,
        'verse': verse,
        'pairIdx': pair_idx,
        'hwIdx': hw_idx,
        'prefixIdx': prefix_idx,
        'role': 'prefix' if prefix_idx >= 0 else 'stem',
        'color': color,
        'he': str(payload.get('he') or ''),
        'es': str(payload.get('es') or ''),
        'strongs': str(payload.get('strongs') or ''),
        'morph': str(payload.get('morph') or ''),
        'at': _now_iso(),
    }
    key = _marca_key(rec)
    with _WRITE_LOCK:
        data = load_marcas()
        marcas = [m for m in data.get('marcas') or [] if _marca_key(m) != key]
        if color:
            marcas.append(rec)
        data['marcas'] = marcas
        save_marcas(data)
        if color == 'verde':
            upsert_refuerzo_verde({**rec, **payload})
    return {'ok': True, 'color': color or None, 'total': len(marcas)}


def _normalize_marca(m: dict, default_book: str = '') -> dict | None:
    if not isinstance(m, dict):
        return None
    color = str(m.get('color') or '').strip().lower()
    if color not in _MARCA_COLORES:
        return None
    book = str(m.get('book') or default_book).strip()
    if not book:
        return None
    try:
        rec = {
            'book': book,
            'chapter': int(m['chapter']),
            'verse': int(m['verse']),
            'pairIdx': int(m['pairIdx']),
            'hwIdx': int(m['hwIdx']),
            'prefixIdx': int(m['prefixIdx']) if m.get('prefixIdx') not in (None, '') else -1,
            'role': str(m.get('role') or ('prefix' if int(m.get('prefixIdx') or -1) >= 0 else 'stem')),
            'color': color,
            'he': str(m.get('he') or ''),
            'es': str(m.get('es') or ''),
            'strongs': str(m.get('strongs') or ''),
            'morph': str(m.get('morph') or ''),
            'at': str(m.get('at') or _now_iso()),
        }
    except (KeyError, TypeError, ValueError):
        return None
    return rec


def sync_marcas_list(incoming: list) -> dict:
    """Sustituye el archivo de marcas con la lista del visor (cierre de pestaña)."""
    cleaned, seen = [], set()
    for raw in incoming or []:
        rec = _normalize_marca(raw)
        if not rec:
            continue
        k = _marca_key(rec)
        if k in seen:
            continue
        seen.add(k)
        cleaned.append(rec)
    with _WRITE_LOCK:
        data = load_marcas()
        data['marcas'] = cleaned
        save_marcas(data)
    for rec in cleaned:
        if rec.get('color') == 'verde':
            upsert_refuerzo_verde(rec)
    return {'ok': True, 'total': len(cleaned)}


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/health':
            self._json_response(200, {'ok': True, 'server': 'traduccion'})
            return
        if parsed.path == '/api/marcas':
            self._handle_get_marcas(parsed)
            return
        if self.path.startswith('/data/'):
            self._serve_data(self.path)
            return
        return super().do_GET()

    def _serve_data(self, path: str):
        clean = path.split('?', 1)[0][len('/data/'):]
        target = resolve_data_file(clean)
        if target and target.exists():
            try:
                body = target.read_bytes()
            except OSError:
                self.send_error(500, 'No se pudo leer el archivo')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # RV1960: si no hay copia local, recuperarla desde la fuente angelos
        # y materializarla en data_master/ para futuras cargas.
        if clean.startswith('rv1960_'):
            src = ANGELOS_RV / clean[len('rv1960_'):]   # rv1960_genesis.json -> genesis.json
            if src.exists():
                try:
                    body = src.read_bytes()
                except OSError:
                    self.send_error(500, 'No se pudo leer la fuente RV1960')
                    return
                try:
                    (RV_DIR / clean).write_bytes(body)   # copia local (idempotente)
                except OSError:
                    pass
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # Sin fuente disponible: degradar a vacío para no romper el visor.
            self._json_response(200, [])
            return
        self.send_error(404, f'No encontrado: {clean}')

    def do_POST(self):
        if self.path == '/api/save-gloss':
            self._handle_save_gloss()
            return
        if self.path == '/api/save-personal':
            self._handle_save_personal()
            return
        if self.path == '/api/globalize':
            self._handle_globalize()
            return
        if self.path == '/api/count-strongs':
            self._handle_count_strongs()
            return
        if self.path == '/api/occurrences':
            self._handle_occurrences()
            return
        if self.path == '/api/strong-info':
            self._handle_strong_info()
            return
        if self.path == '/api/lock-state':
            self._handle_lock_state()
            return
        if self.path == '/api/toggle-lock':
            self._handle_toggle_lock()
            return
        if self.path == '/api/run-motor':
            self._handle_run_motor()
            return
        if self.path == '/api/marcas':
            self._handle_post_marcas()
            return
        if self.path == '/api/marcas-sync':
            self._handle_sync_marcas()
            return
        self.send_error(404, 'Endpoint no encontrado')

    def _read_json_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _handle_save_gloss(self):
        try:
            body = self._read_json_body()
            n = save_single_gloss(
                book=str(body['book']).strip(),
                chapter=int(body['chapter']),
                verse=int(body['verse']),
                pair_idx=int(body['pairIdx']),
                hw_idx=int(body['hwIdx']),
                new_es=str(body.get('es', '')).strip(),
                field=str(body.get('field', 'es')).strip(),
                prefix_idx=int(body.get('prefixIdx', -1)),
                has_suffix=bool(body.get('hasSuffix', False)),
            )
            self._json_response(200, {'ok': True, 'changed': n})
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_save_personal(self):
        try:
            body = self._read_json_body()
            n = save_personal_verse(
                book=str(body['book']).strip(),
                chapter=int(body['chapter']),
                verse=int(body['verse']),
                new_text=str(body.get('text', '')),
            )
            self._json_response(200, {'ok': True, 'changed': n})
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_globalize(self):
        try:
            body = self._read_json_body()
            total, books = globalize_by_strongs(
                strongs=str(body['strongs']).strip(),
                new_es=str(body.get('es', '')).strip(),
                scope=str(body.get('scope', 'all')).strip(),
                mode=str(body.get('mode', 'lemma')).strip() or 'lemma',
                he_form=str(body.get('he_form', '')),
                he_morph=str(body.get('he_morph', '')),
            )
            self._json_response(200, {
                'ok': True, 'changed': total, 'books': books
            })
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_count_strongs(self):
        try:
            body = self._read_json_body()
            total, n_books = count_strongs_occurrences(
                str(body['strongs']).strip()
            )
            self._json_response(200, {
                'ok': True, 'total': total, 'books': n_books
            })
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_occurrences(self):
        try:
            body = self._read_json_body()
            occ, total = find_occurrences(
                strongs=str(body['strongs']).strip(),
                scope=str(body.get('scope', 'all')).strip(),
            )
            self._json_response(200, {
                'ok': True,
                'total': total,
                'returned': len(occ),
                'occurrences': occ,
            })
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_strong_info(self):
        try:
            body = self._read_json_body()
            info = strong_info(
                str(body['strongs']).strip(),
                scope=str(body.get('scope', 'all')).strip() or 'all',
            )
            if info is None:
                self._json_response(200, {'ok': True, 'info': None})
            else:
                self._json_response(200, {'ok': True, 'info': info})
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_lock_state(self):
        try:
            body = self._read_json_body()
            book = str(body['book']).strip()
            chapter = int(body['chapter'])
            locked = _cap_cerrado(book, chapter)
            self._json_response(200, {'ok': True, 'locked': locked})
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_toggle_lock(self):
        """Cierra/abre un capítulo. Al cerrar, sella su estado actual."""
        if candado is None:
            self._json_response(500, {'ok': False, 'error': 'candado no disponible'})
            return
        try:
            body = self._read_json_body()
            book = str(body['book']).strip()
            chapter = int(body['chapter'])
            with _WRITE_LOCK:
                if candado.esta_bloqueado(book, chapter):
                    candado.desbloquear(book, chapter)
                    locked = False
                else:
                    path = DATA_DIR / f'{book}_final.json'
                    data = load_book(path) if path.exists() else {'verses': []}
                    candado.bloquear(book, chapter, data)
                    locked = True
            if locked:
                _refresh_estadistica_async()  # alimentar el modelo con lo cerrado
            self._json_response(200, {'ok': True, 'locked': locked})
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_run_motor(self):
        """Corre el motor de español (revisar_es.py) sobre un capítulo.

        body: {book, chapter, apply}. apply=False → solo INFORME (dry-run).
        Nunca aplica sobre capítulos CERRADOS (candado): degrada a informe."""
        try:
            body = self._read_json_body()
            book = str(body['book']).strip()
            chapter = int(body['chapter'])
            apply = bool(body.get('apply', False))
            if _cap_cerrado(book, chapter):
                self._json_response(200, {
                    'ok': True, 'locked': True, 'applied': 0,
                    'output': (f'Capitulo {book} {chapter} esta CERRADO (candado): '
                               'el motor NO se ejecuta aqui. Reabrelo si quieres correrlo.')})
                return
            script = str(REPO / 'motores' / 'scripts' / 'revisar_es.py')
            cmd = [sys.executable, script, '--book', book,
                   '--chapter', str(chapter)]
            if apply:
                cmd.append('--apply')
            with _WRITE_LOCK:
                proc = subprocess.run(
                    cmd, cwd=str(REPO), capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=600)
            out = (proc.stdout or '')
            if proc.stderr:
                out += '\n[stderr]\n' + proc.stderr
            applied = 0
            m = re.search(r'APLICADOS[^:]*:\s*(\d+)', out)
            if m:
                applied = int(m.group(1))
            if apply and applied:
                # invalida caché para que el visor relea el archivo modificado
                _BOOK_CACHE.pop(str(DATA_DIR / f'{book}_final.json'), None)
                _refresh_estadistica_async()
            self._json_response(200, {
                'ok': proc.returncode == 0, 'applied': applied, 'output': out})
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_get_marcas(self, parsed):
        qs = parse_qs(parsed.query)
        book = (qs.get('book') or [''])[0].strip()
        data = load_marcas()
        marcas = data.get('marcas') or []
        if book:
            marcas = [m for m in marcas if str(m.get('book') or '') == book]
        self._json_response(200, {'ok': True, 'marcas': marcas})

    def _handle_post_marcas(self):
        try:
            body = self._read_json_body()
            result = upsert_marca(body)
            self._json_response(200, result)
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _handle_sync_marcas(self):
        try:
            body = self._read_json_body()
            incoming = body if isinstance(body, list) else body.get('marcas')
            result = sync_marcas_list(incoming if isinstance(incoming, list) else [])
            self._json_response(200, result)
        except Exception as exc:
            self._json_response(400, {'ok': False, 'error': str(exc)})

    def _json_response(self, status: int, payload: dict):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

class _ThreadingServer(socketserver.ThreadingTCPServer):
    # Servidor multihilo: evita que una petición lenta/colgada bloquee al resto
    # (el navegador mantiene conexiones keep-alive abiertas).
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    with _ThreadingServer(('', PORT), Handler) as httpd:
        print(f'Servidor sin caché (multihilo) en http://localhost:{PORT}')
        httpd.serve_forever()
