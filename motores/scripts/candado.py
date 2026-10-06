# -*- coding: utf-8 -*-
"""
Candado de capítulos terminados — seguridad a nivel de persistencia.

Regla única del proyecto: un capítulo CERRADO queda BLOQUEADO y NINGÚN proceso
(editor manual, globalización, motor de revisión, scripts nuevos o futuros)
puede modificar ningún campo suyo. Solo se cierra/abre con el botón del visor.

Dos capas de defensa:
  1) esta_bloqueado(libro, cap)  → todo escritor debe consultarlo y SALTAR.
  2) SELLOS + reasegurar()       → copia sellada del capítulo; reasegurar()
     restaura los capítulos sellados dentro de un `data` antes de guardarlo,
     de modo que aunque un proceso "olvide" consultar el candado, el capítulo
     sellado se restablece y no se persiste ningún cambio.

Config:  fuentes/candado_capitulos.json
Sellos:  fuentes/candado_sellos/<libro>.json   (chapter -> [verse objs sellados])
"""
import copy
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CFG = _REPO / 'fuentes' / 'candado_capitulos.json'
_SELLOS = _REPO / 'fuentes' / 'candado_sellos'


def _norm(libro):
    return (libro or '').lower().replace('_final.json', '').replace('.json', '').strip()


_CFG_CACHE = {'mtime': None, 'data': None}


def _load_cfg():
    """Config con caché por mtime (esta_bloqueado se llama por-verso en
    globalize/motores; sin caché reparsearíamos el JSON miles de veces)."""
    try:
        mt = _CFG.stat().st_mtime_ns
    except OSError:
        mt = None
    if _CFG_CACHE['data'] is not None and _CFG_CACHE['mtime'] == mt:
        return _CFG_CACHE['data']
    try:
        data = json.loads(_CFG.read_text(encoding='utf-8'))
    except Exception:
        data = {'version': 2, 'candados': {}}
    _CFG_CACHE['mtime'] = mt
    _CFG_CACHE['data'] = data
    return data


def _save_cfg(cfg):
    import datetime
    cfg['actualizado'] = datetime.date.today().isoformat()
    _CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        _CFG_CACHE['mtime'] = _CFG.stat().st_mtime_ns
    except OSError:
        _CFG_CACHE['mtime'] = None
    _CFG_CACHE['data'] = cfg


def capitulos_bloqueados(libro):
    """Conjunto (set[int]) de capítulos bloqueados de un libro."""
    c = _load_cfg().get('candados', {}).get(_norm(libro))
    if not c:
        return set()
    hasta = int(c.get('bloqueados_hasta', 0) or 0)
    base = set(range(1, hasta + 1)) if hasta else set()
    base |= {int(x) for x in c.get('bloqueados', [])}
    base -= {int(x) for x in c.get('desbloqueados', [])}
    return base


def esta_bloqueado(libro, capitulo):
    """True si (libro, capitulo) está cerrado y NO debe modificarse."""
    try:
        return int(capitulo) in capitulos_bloqueados(libro)
    except (TypeError, ValueError):
        return False


# ── Sellos ──────────────────────────────────────────────────────────────────

def _sello_path(libro):
    return _SELLOS / f'{_norm(libro)}.json'


def _load_sellos(libro):
    p = _sello_path(libro)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_sellos(libro, sellos):
    _SELLOS.mkdir(parents=True, exist_ok=True)
    _sello_path(libro).write_text(
        json.dumps(sellos, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8')


def sellar(libro, capitulo, data):
    """Guarda una copia sellada de todos los versos del capítulo dentro de `data`."""
    cap = int(capitulo)
    verses = [copy.deepcopy(v) for v in data.get('verses', []) if v.get('chapter') == cap]
    if not verses:
        return 0
    sellos = _load_sellos(libro)
    sellos[str(cap)] = verses
    _save_sellos(libro, sellos)
    return len(verses)


def quitar_sello(libro, capitulo):
    sellos = _load_sellos(libro)
    if str(int(capitulo)) in sellos:
        del sellos[str(int(capitulo))]
        _save_sellos(libro, sellos)


def reasegurar(libro, data):
    """Restaura en `data` (in-place) todos los capítulos sellados y bloqueados.

    Devuelve el nº de versos restaurados. Cualquier escritor por lotes debe
    llamar esto JUSTO antes de guardar para no persistir cambios en capítulos
    cerrados, aunque no haya consultado esta_bloqueado()."""
    sellos = _load_sellos(libro)
    if not sellos:
        return 0
    bloq = capitulos_bloqueados(libro)
    restaurados = 0
    verses = data.get('verses', [])
    for cap_str, sealed_verses in sellos.items():
        cap = int(cap_str)
        if cap not in bloq:
            continue
        sealed_by_v = {v.get('verse'): v for v in sealed_verses}
        for i, v in enumerate(verses):
            if v.get('chapter') == cap and v.get('verse') in sealed_by_v:
                if verses[i] != sealed_by_v[v.get('verse')]:
                    verses[i] = copy.deepcopy(sealed_by_v[v.get('verse')])
                    restaurados += 1
    return restaurados


# ── Cerrar / Abrir (usado por el servidor / botón) ──────────────────────────

def bloquear(libro, capitulo, data=None):
    """Cierra un capítulo: lo marca en config y (si se pasa `data`) lo sella."""
    slug = _norm(libro)
    cap = int(capitulo)
    cfg = _load_cfg()
    c = cfg.setdefault('candados', {}).setdefault(
        slug, {'bloqueados_hasta': 0, 'bloqueados': [], 'desbloqueados': []})
    c.setdefault('bloqueados', [])
    c.setdefault('desbloqueados', [])
    if cap in c['desbloqueados']:
        c['desbloqueados'].remove(cap)
    if cap not in c['bloqueados'] and cap > int(c.get('bloqueados_hasta', 0) or 0):
        c['bloqueados'].append(cap)
        c['bloqueados'].sort()
    _save_cfg(cfg)
    if data is not None:
        sellar(slug, cap, data)
    return True


def desbloquear(libro, capitulo):
    """Abre un capítulo: lo quita del candado y borra su sello."""
    slug = _norm(libro)
    cap = int(capitulo)
    cfg = _load_cfg()
    c = cfg.setdefault('candados', {}).setdefault(
        slug, {'bloqueados_hasta': 0, 'bloqueados': [], 'desbloqueados': []})
    c.setdefault('bloqueados', [])
    c.setdefault('desbloqueados', [])
    if cap in c['bloqueados']:
        c['bloqueados'].remove(cap)
    if cap <= int(c.get('bloqueados_hasta', 0) or 0) and cap not in c['desbloqueados']:
        c['desbloqueados'].append(cap)
        c['desbloqueados'].sort()
    _save_cfg(cfg)
    quitar_sello(slug, cap)
    return True


def resumen():
    out = []
    for lib in _load_cfg().get('candados', {}):
        caps = sorted(capitulos_bloqueados(lib))
        out.append(f"{lib}: {len(caps)} cerrados")
    return ' · '.join(out) if out else '(sin candados)'


if __name__ == '__main__':
    print('Candados:', resumen())
    for ch in (8, 21, 22):
        print(f'  genesis {ch}: {"CERRADO" if esta_bloqueado("genesis", ch) else "abierto"}')
