"""Registro y aplicación de glosas personalizadas (global / contexto)."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent   # motores/
REPO = ROOT.parent                               # raíz BIBLIA2027/
# Tras la reorganización: el registro de glosas y los backups viven en fuentes/.
GLOSAS_PATH = REPO / 'fuentes' / 'glosas_personales.json'
BACKUP_DIR = REPO / 'fuentes' / 'backups'


def atomic_write_json(path: Path, data: Any, *, indent=None, separators=None) -> None:
    """Escribe JSON de forma atómica (temp + os.replace) para no corromper el
    archivo si el proceso se interrumpe a mitad de escritura."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, separators=separators)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _backup_registry(path: Path) -> None:
    """Respaldo del registro: un .bak con la versión previa (anti-corrupción)
    y una copia diaria con fecha (historial acotado, una por día)."""
    if not path.exists():
        return
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        # Copia previa inmediata (rollback ante corrupción).
        shutil.copy2(path, path.with_suffix('.json.bak'))
        # Snapshot diario (se sobrescribe durante el mismo día -> acotado).
        day = datetime.now().strftime('%Y%m%d')
        daily = BACKUP_DIR / f'{path.stem}_{day}.json'
        if not daily.exists():
            shutil.copy2(path, daily)
    except OSError:
        pass


def normalize_strongs(raw: str | None) -> str:
    if not raw:
        return ''
    s = str(raw).strip().upper()
    m = re.match(r'^([HG])0*(\d+)', s)
    if m:
        return f'{m.group(1)}{m.group(2)}'
    return s


# ── Tetragrámaton (qere perpetuo) ───────────────────────────────────────────
# El Nombre divino (יהוה, Strong H3068) se vocaliza distinto según el qere que
# los masoretas insertaron, y eso define su LECTURA:
#   · hiriq  (ִ U+05B4)            → se lee "Elohim"  (junto a Adonai, p. ej. אֲדֹנָי יְהוִה)
#   · holam  (ֹ U+05B9 / ֺ U+05BA) → se lee "Adonai"  (apuntamiento pleno)
#   · solo qamats (sin holam/hiriq) → "Hashem" (apuntamiento defectivo, caso común)
# El emparejado del motor ignora vocales (consonants_only/clean_hebrew), así que
# SIN esta función todas las formas colapsarían a un único valor. Por eso el
# valor a escribir para H3068 se enruta SIEMPRE por la vocal del propio token.
_YHWH_HIRIQ = '\u05B4'
_YHWH_HOLAM = ('\u05B9', '\u05BA')


def tetragrammaton_es(he_form: str | None, default: str = 'Hashem') -> str:
    s = he_form or ''
    if _YHWH_HIRIQ in s:
        return "'Elohim"
    if any(h in s for h in _YHWH_HOLAM):
        return 'Adonai'
    return default or 'Hashem'


def load_registry(path: Path | None = None) -> dict[str, Any]:
    p = path or GLOSAS_PATH
    if not p.exists():
        return {'version': 1, 'updated': None, 'global': [], 'contexto': []}
    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('global', [])
    data.setdefault('contexto', [])
    return data


def save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or GLOSAS_PATH
    _backup_registry(p)
    data['updated'] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(p, data, indent=2)


def list_book_slugs(data_dir: Path | None = None) -> list[str]:
    d = data_dir or (REPO / 'data_master')
    return sorted(p.stem.replace('_final', '') for p in d.glob('*_final.json'))


def _read_es_from_hw(hw: dict, field: str, prefix_idx: int | None, combined: bool) -> str:
    if field == 'prefix_es':
        arr = hw.get('prefix_es') or []
        if prefix_idx is None or prefix_idx >= len(arr):
            return ''
        return str(arr[prefix_idx] or '').strip()
    es = str(hw.get('es') or '').strip()
    if combined and hw.get('prs_suffix'):
        suf = str((hw.get('prs_suffix') or {}).get('es') or '').strip()
        if suf and es:
            return f'{es} {suf}'.strip()
        return es or suf
    return es


def _consonants_only(s: str | None) -> str:
    if not s:
        return ''
    t = re.sub(r'[\u0591-\u05BD\u05BF\u05C1-\u05C7\u05BE\u05C0\u05F3\u05F4]', '', str(s))
    t = re.sub(r'[\s\-\u05BE\u2013]+', '', t)
    return t.strip()


def context_token_matches(hw: dict, match: dict) -> bool:
    """Verifica que el token coincide con la identidad guardada en la regla."""
    if not hw:
        return False
    req_strong = normalize_strongs(match.get('strongs'))
    hw_strong = normalize_strongs(hw.get('strongs'))
    if req_strong and hw_strong and hw_strong != req_strong:
        return False
    req_he = _consonants_only(match.get('he_form') or '') if match.get('he_form') else ''
    if req_he:
        m_he = _consonants_only(hw.get('he_form') or hw.get('stem_unicode') or '')
        if m_he and req_he != m_he:
            return False
    return True


def relocate_context_token(verse_obj: dict, match: dict) -> dict | None:
    """Relocaliza el token cuando pairIdx quedó obsoleto tras reestructuración."""
    best: dict | None = None
    best_dist = float('inf')
    target_pi = match.get('pairIdx') or 0
    for pi, pair in enumerate(verse_obj.get('pairs') or []):
        if pair.get('kind') == 'gk_add':
            continue
        for hw in pair.get('he_words') or []:
            if not context_token_matches(hw, match):
                continue
            dist = abs(pi - target_pi)
            if dist < best_dist:
                best_dist = dist
                best = hw
    return best


def _write_es_to_hw(hw: dict, field: str, prefix_idx: int | None, combined: bool, value: str) -> None:
    if field == 'prefix_es':
        arr = hw.setdefault('prefix_es', [])
        while len(arr) <= (prefix_idx or 0):
            arr.append('')
        arr[prefix_idx or 0] = value
        return
    hw['es'] = value
    if combined and hw.get('prs_suffix'):
        hw['prs_suffix']['es'] = ''
    hw['es_source'] = 'glosa_personal'


def _prefix_meta(hw: dict, prefix_idx: int) -> dict[str, str]:
    labels = hw.get('prefix_labels') or []
    morphs = hw.get('prefix_morphs') or []
    forms = hw.get('prefix_forms') or []
    return {
        'prefix_morph': str(morphs[prefix_idx] if prefix_idx < len(morphs) else ''),
        'prefix_label': str(labels[prefix_idx] if prefix_idx < len(labels) else ''),
        'he_prefix': str(forms[prefix_idx] if prefix_idx < len(forms) else ''),
    }


def build_global_match(token_meta: dict[str, Any]) -> dict[str, Any]:
    role = token_meta.get('role') or 'stem'
    match: dict[str, Any] = {'role': role}
    if role == 'prefix':
        match['prefix_morph'] = token_meta.get('prefix_morph') or ''
        match['prefix_label'] = token_meta.get('prefix_label') or ''
        match['he_prefix'] = token_meta.get('he_prefix') or ''
    else:
        match['strongs'] = normalize_strongs(token_meta.get('strongs'))
        match['he_form'] = token_meta.get('he_form') or ''
        match['he_morph'] = token_meta.get('he_morph') or ''
    return match


def global_rule_key(match: dict[str, Any]) -> str:
    role = match.get('role') or 'stem'
    if role == 'prefix':
        return '|'.join([
            'prefix',
            match.get('prefix_morph') or '',
            match.get('prefix_label') or '',
            match.get('he_prefix') or '',
        ])
    return '|'.join([
        'stem',
        normalize_strongs(match.get('strongs')),
        match.get('he_morph') or '',
    ])


def context_rule_key(book: str, match: dict[str, Any]) -> str:
    return '|'.join([
        book,
        str(match.get('chapter')),
        str(match.get('verse')),
        str(match.get('pairIdx')),
        str(match.get('hwIdx')),
        match.get('field') or '',
        str(match.get('prefixIdx')),
        str(match.get('combined')),
    ])


def token_meta_from_patch(edit_path: dict, token_meta: dict | None) -> dict[str, Any]:
    meta = dict(token_meta or {})
    meta['field'] = edit_path.get('field')
    meta['prefixIdx'] = edit_path.get('prefixIdx')
    meta['combined'] = bool(edit_path.get('combined'))
    if edit_path.get('field') == 'prefix_es':
        meta['role'] = 'prefix'
    elif edit_path.get('field') == 'heb_omit_es':
        meta['role'] = 'heb_omit'
    else:
        meta['role'] = 'stem'
    return meta


def upsert_global_rule(
    registry: dict[str, Any],
    token_meta: dict[str, Any],
    before_es: str,
    after_es: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    match = build_global_match(token_meta)
    key = global_rule_key(match)
    rule = {
        'id': f'g-{key.replace("|", "-")}',
        'scope': 'global',
        'match': match,
        'before': {'es': before_es},
        'after': {'es': after_es},
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source': source,
    }
    rules = registry.setdefault('global', [])
    for i, existing in enumerate(rules):
        if global_rule_key(existing.get('match') or {}) == key:
            rule['id'] = existing.get('id') or rule['id']
            rule['created_at'] = existing.get('created_at') or rule['created_at']
            rules[i] = rule
            return rule
    rules.append(rule)
    return rule


def upsert_context_rule(
    registry: dict[str, Any],
    book: str,
    chapter: int,
    verse: int,
    edit_path: dict[str, Any],
    token_meta: dict[str, Any],
    before_es: str,
    after_es: str,
) -> dict[str, Any]:
    match = {
        'book': book,
        'chapter': chapter,
        'verse': verse,
        'pairIdx': edit_path.get('pairIdx'),
        'hwIdx': edit_path.get('hwIdx'),
        'field': edit_path.get('field'),
        'prefixIdx': edit_path.get('prefixIdx'),
        'combined': bool(edit_path.get('combined')),
        'strongs': normalize_strongs(token_meta.get('strongs')),
        'he_form': token_meta.get('he_form') or '',
        'prefix_morph': token_meta.get('prefix_morph') or '',
        'prefix_label': token_meta.get('prefix_label') or '',
        'he_prefix': token_meta.get('he_prefix') or '',
        'role': token_meta.get('role') or '',
    }
    key = context_rule_key(book, match)
    rule = {
        'id': f'ctx-{book}-{chapter}-{verse}-{edit_path.get("pairIdx")}-{edit_path.get("hwIdx")}',
        'scope': 'context',
        'match': match,
        'before': {'es': before_es},
        'after': {'es': after_es},
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    rules = registry.setdefault('contexto', [])
    for i, existing in enumerate(rules):
        if context_rule_key(existing.get('match', {}).get('book', ''), existing.get('match') or {}) == key:
            rule['id'] = existing.get('id') or rule['id']
            rules[i] = rule
            return rule
    rules.append(rule)
    return rule


def clean_hebrew(s: str | None) -> str:
    if not s:
        return ''
    import re, unicodedata
    t = unicodedata.normalize('NFC', str(s))
    t = re.sub(r'[\u0591-\u05AF\u05BD]', '', t)
    t = re.sub(r'[\u05BE\u05C0]', '', t)
    t = re.sub(r'[\u05C3-\u05C6]', '', t)
    t = re.sub(r'^[\s\-–־]+', '', t)
    t = re.sub(r'[\s\-–־]+$', '', t)
    return t.strip()


def stem_matches_global(rule: dict, hw: dict) -> bool:
    match = rule.get('match') or {}
    if match.get('role') != 'stem':
        return False
    rule_strong = normalize_strongs(match.get('strongs'))
    hw_strong = normalize_strongs(hw.get('strongs'))
    if rule_strong:
        if hw_strong != rule_strong:
            return False
    elif hw_strong and not (match.get('he_form') or '').strip():
        return False
    # NOTA: no exigimos he_morph. El meta del cliente arma he_morph como
    # (he_morph || stem_label); cuando he_morph del dato está vacío, ese
    # requisito hacía que la regla NO emparejara ni el token de origen y la
    # globalización no escribía nada (0 hits, sin error). El emparejado por
    # Strong + forma consonántica es suficiente y es lo esperado.
    req_morph = (match.get('he_morph') or '').strip()
    hw_morph = (hw.get('he_morph') or '').strip()
    if req_morph and hw_morph and req_morph not in hw_morph:
        return False
    req_form = (match.get('he_form') or '').strip()
    if req_form:
        hw_form = (hw.get('he_form') or hw.get('stem_unicode') or '').strip()
        if clean_hebrew(req_form) != clean_hebrew(hw_form):
            return False
    return True


def prefix_matches_global(rule: dict, hw: dict, prefix_idx: int) -> bool:
    match = rule.get('match') or {}
    if match.get('role') != 'prefix':
        return False
    meta = _prefix_meta(hw, prefix_idx)
    if match.get('prefix_morph') and match.get('prefix_morph') != meta['prefix_morph']:
        return False
    if match.get('prefix_label') and match.get('prefix_label') != meta['prefix_label']:
        return False
    if match.get('he_prefix') and match.get('he_prefix') != meta['he_prefix']:
        return False
    return True


def apply_global_rule_to_interlineal(interlineal: dict, rule: dict) -> int:
    match = rule.get('match') or {}
    after_es = (rule.get('after') or {}).get('es', '')
    hits = 0
    role = match.get('role')

    for verse in interlineal.get('verses', []):
        for pair in verse.get('pairs', []):
            if pair.get('kind') == 'gk_add':
                continue
            if role == 'heb_omit':
                continue
            for hw in pair.get('he_words', []):
                if role == 'stem' and stem_matches_global(rule, hw):
                    # Tetragrámaton: enruta por vocal (Hashem/Adonai/'Elohim) en
                    # vez de aplastar todas las formas a un único valor.
                    val = after_es
                    if normalize_strongs(match.get('strongs')) == 'H3068':
                        val = tetragrammaton_es(hw.get('he_form'), after_es)
                    if str(hw.get('es') or '').strip() != val:
                        hw['_es_original'] = hw.get('_es_original') or hw.get('es')
                        hw['es'] = val
                        if hw.get('prs_suffix'):
                            hw['prs_suffix']['es'] = ''
                        hw['es_source'] = 'glosa_global'
                        hits += 1
                elif role == 'prefix':
                    for i in range(len(hw.get('prefixes') or [])):
                        if prefix_matches_global(rule, hw, i):
                            arr = hw.setdefault('prefix_es', [])
                            while len(arr) <= i:
                                arr.append('')
                            if str(arr[i] or '').strip() != after_es:
                                arr[i] = after_es
                                hits += 1
    return hits


def apply_context_rule_to_interlineal(interlineal: dict, rule: dict) -> int:
    match = rule.get('match') or {}
    after_es = (rule.get('after') or {}).get('es', '')
    chapter = match.get('chapter')
    verse = match.get('verse')
    pair_idx = match.get('pairIdx')
    field = match.get('field')

    verse_obj = next(
        (v for v in interlineal.get('verses', [])
         if v.get('chapter') == chapter and v.get('verse') == verse),
        None,
    )
    if not verse_obj:
        return 0

    pairs = verse_obj.get('pairs') or []
    if pair_idx is None or pair_idx < 0 or pair_idx >= len(pairs):
        return 0

    if field == 'heb_omit_es':
        pair = pairs[pair_idx]
        if str(pair.get('es_gloss') or '').strip() != after_es:
            pair['es_gloss'] = after_es
            return 1
        return 0

    pair = pairs[pair_idx]
    he_words = pair.get('he_words') or []
    hw_idx = match.get('hwIdx')
    if hw_idx is None or hw_idx < 0 or hw_idx >= len(he_words):
        return 0

    hw = he_words[hw_idx]
    verifiable = bool(normalize_strongs(match.get('strongs')) or match.get('he_form'))
    if verifiable and not context_token_matches(hw, match):
        hw = relocate_context_token(verse_obj, match)
        if not hw:
            return 0
    cur = _read_es_from_hw(
        hw,
        field,
        match.get('prefixIdx'),
        bool(match.get('combined')),
    )
    if cur == after_es:
        return 0
    _write_es_to_hw(
        hw,
        field,
        match.get('prefixIdx'),
        bool(match.get('combined')),
        after_es,
    )
    return 1


def apply_all_global_rules(interlineal: dict, registry: dict) -> int:
    total = 0
    for rule in registry.get('global', []):
        total += apply_global_rule_to_interlineal(interlineal, rule)
    return total


def apply_registry_to_interlineal(interlineal: dict, book: str, registry: dict) -> int:
    hits = apply_all_global_rules(interlineal, registry)
    for rule in registry.get('contexto', []):
        match = rule.get('match') or {}
        if match.get('book') != book:
            continue
        hits += apply_context_rule_to_interlineal(interlineal, rule)
    return hits


def apply_direct_gloss_patch(interlineal: dict, chapter: int, verse: int, edit_path: dict, value: str) -> None:
    """Parche directo al JSON interlineal (misma lógica que servidor.apply_gloss_patch)."""
    verse_obj = next(
        (v for v in interlineal.get('verses', [])
         if v.get('chapter') == chapter and v.get('verse') == verse),
        None,
    )
    if not verse_obj:
        raise ValueError(f'Versículo no encontrado: {chapter}:{verse}')

    pair_idx = edit_path['pairIdx']
    pairs = verse_obj.get('pairs') or []
    if pair_idx < 0 or pair_idx >= len(pairs):
        raise ValueError(f'Par inválido: {pair_idx}')

    pair = pairs[pair_idx]
    field = edit_path.get('field')

    if field == 'heb_omit_es':
        pair['es_gloss'] = value
        return

    hw_idx = edit_path.get('hwIdx')
    he_words = pair.get('he_words') or []
    if hw_idx is None or hw_idx < 0 or hw_idx >= len(he_words):
        raise ValueError(f'he_word inválido: {hw_idx}')

    hw = he_words[hw_idx]
    _write_es_to_hw(
        hw,
        field,
        edit_path.get('prefixIdx'),
        bool(edit_path.get('combined')),
        value,
    )


def apply_gloss_choice(
    mode: str,
    book: str,
    chapter: int,
    verse: int,
    edit_path: dict[str, Any],
    token_meta: dict[str, Any],
    before_es: str,
    after_es: str,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    d = data_dir or (REPO / 'data_master')
    registry = load_registry()
    source = {
        'book': book,
        'ref': f'{chapter}:{verse}',
        'pairIdx': edit_path.get('pairIdx'),
        'hwIdx': edit_path.get('hwIdx'),
    }

    if mode == 'global':
        meta = token_meta_from_patch(edit_path, token_meta)
        if meta.get('role') == 'heb_omit':
            raise ValueError('Las omisiones hebreas no se pueden globalizar por Strong')
        if meta.get('role') == 'stem' and not normalize_strongs(meta.get('strongs')):
            raise ValueError('Sin número Strong: no se puede globalizar este token')
        rule = upsert_global_rule(registry, meta, before_es, after_es, source)

        # Conflicto global vs contexto: el registro se aplica global -> contexto,
        # así que una regla de contexto en ESTE mismo token revertiría la
        # globalización al recargar. Como el usuario acaba de globalizar desde
        # este token, su acción nueva manda: quitamos la regla de contexto de
        # esta posición exacta (las de otros versículos se conservan).
        origin_match = {
            'chapter': chapter,
            'verse': verse,
            'pairIdx': edit_path.get('pairIdx'),
            'hwIdx': edit_path.get('hwIdx'),
            'field': edit_path.get('field'),
            'prefixIdx': edit_path.get('prefixIdx'),
            'combined': bool(edit_path.get('combined')),
        }
        origin_key = context_rule_key(book, origin_match)
        registry['contexto'] = [
            r for r in registry.get('contexto', [])
            if context_rule_key(
                (r.get('match') or {}).get('book', ''), r.get('match') or {}
            ) != origin_key
        ]

        save_registry(registry)

        total_hits = 0
        books_touched = []
        for slug in list_book_slugs(d):
            path = d / f'{slug}_final.json'
            with open(path, 'r', encoding='utf-8') as f:
                interlineal = json.load(f)
            hits = apply_global_rule_to_interlineal(interlineal, rule)
            if hits:
                atomic_write_json(path, interlineal, separators=(',', ':'))
                total_hits += hits
                books_touched.append(slug)

        # Red de seguridad: si la regla global no emparejó NINGÚN token (ni el de
        # origen) escribimos directamente el token editado en su libro para que la
        # acción nunca falle en silencio.
        if total_hits == 0 and before_es != after_es and book:
            path = d / f'{book}_final.json'
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    interlineal = json.load(f)
                try:
                    apply_direct_gloss_patch(interlineal, chapter, verse, edit_path, after_es)
                    atomic_write_json(path, interlineal, separators=(',', ':'))
                    total_hits = 1
                    books_touched.append(book)
                except ValueError:
                    pass

        return {
            'rule': rule,
            'hits': total_hits,
            'books': books_touched,
        }

    if mode == 'context':
        rule = upsert_context_rule(
            registry, book, chapter, verse, edit_path, token_meta, before_es, after_es,
        )
        save_registry(registry)
        path = d / f'{book}_final.json'
        with open(path, 'r', encoding='utf-8') as f:
            interlineal = json.load(f)
        hits = apply_context_rule_to_interlineal(interlineal, rule)
        if hits == 0 and before_es != after_es:
            apply_direct_gloss_patch(interlineal, chapter, verse, edit_path, after_es)
            hits = 1
        atomic_write_json(path, interlineal, separators=(',', ':'))
        return {'rule': rule, 'hits': hits, 'books': [book]}

    raise ValueError(f'Modo inválido: {mode}')


def apply_gloss_bulk(
    book: str,
    items: list[dict[str, Any]],
    after_es: str,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Aplica un MISMO español a varias ocurrencias dentro de un libro.

    Usado por el flujo "Diccionario" (Globalizar = aplicar a todas las
    ocurrencias de esa palabra en el libro actual). Escribe el JSON del libro
    una sola vez (atómico) y registra una regla de contexto por ocurrencia
    para que las ediciones sobrevivan a una regeneración del libro.
    """
    if not book:
        raise ValueError('Falta book')
    d = data_dir or (REPO / 'data_master')
    path = d / f'{book}_final.json'
    if not path.exists():
        raise ValueError(f'Libro no encontrado: {book}')

    registry = load_registry()
    with open(path, 'r', encoding='utf-8') as f:
        interlineal = json.load(f)

    hits = 0
    for it in items or []:
        try:
            chapter = int(it['chapter'])
            verse = int(it['verse'])
        except (KeyError, TypeError, ValueError):
            continue
        edit_path = it.get('editPath') or {}
        token_meta = it.get('tokenMeta') or {}
        before_es = str(it.get('before', '')).strip()
        try:
            apply_direct_gloss_patch(interlineal, chapter, verse, edit_path, after_es)
        except ValueError:
            continue
        upsert_context_rule(
            registry, book, chapter, verse, edit_path, token_meta, before_es, after_es,
        )
        hits += 1

    atomic_write_json(path, interlineal, separators=(',', ':'))
    if hits:
        save_registry(registry)
    return {'hits': hits, 'book': book}
