# -*- coding: utf-8 -*-
"""Motor unificado de transliteración de nombres en interlineal.

Escribe translit_academica, render_espanol y es (capa española) en cada token
NPROP o GENT.*. Respeta glosas personales (global/contexto) y nunca
translitera el Tetragrámaton.

Nombres partidos por maqaf (בֵּֽית־ + אֵל, …): reparte Beit- + el bajo cada eslabón.

Locativos -áh (מִצְרַיְמָה = מִצְרַיְמָ + sufijo ה): infiere Strong (H4714),
translitera la forma fusionada (Mitzráymah) aunque el dato no traiga Strong.

Gentilicios (מִצְרִים → Mitzrim, כְּנַעֲנִי → Kena'aní): misma capa española;
infiere H4713 para מצרים cuando morph=GENT.*.

Auditoría y limpieza
────────────────────
Antes de aplicar reporta:
  A) NPROP/GENT con glosa compuesta sospechosa (excluyendo maqaf legítimos).
  B) Tokens NPROP consecutivos con la MISMA glosa compuesta (patrón spider).
  C) Reglas ctx contra NPROP/GENT con after.es literal (rey/monte/valle…) o
     no-op (before == after).
  D) NPROP/GENT con glosa traducida (Pozo, Casa, Tierra…).

Con --limpiar-artefactos --apply, además:
  • Limpia `es` de tokens patrón B antes de transliterar.
  • Borra reglas ctx anómalas (C).

Uso:
    python motores/scripts/aplicar_translit_nombres.py --book genesis --chapter 14
    python motores/scripts/aplicar_translit_nombres.py --book genesis --chapter 14 --apply
    python motores/scripts/aplicar_translit_nombres.py --book genesis --apply --limpiar-artefactos
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'visor'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from translit_nombres import (  # noqa: E402
    es_nprop_o_gent,
    fused_he_form,
    has_leading_maqaf,
    has_trailing_maqaf,
    he_fusionado_hw,
    inferir_strongs_nprop,
    transliterar,
    transliterar_locativo_nprop,
    transliterar_maqaf_partes,
)
from hebrew_clean import is_meta_raw  # noqa: E402
from glosas_personales_utils import GLOSAS_PATH, REPO  # noqa: E402

DATA_DIR = REPO / 'data_master'
YHWH_CONS = frozenset({'יהוה', 'יהויה'})

# Glosa "literal" (no transliteración) — para detectar artefactos.
LITERAL_HINTS = frozenset({
    'rey', 'monte', 'valle', 'fuente', 'carnero', 'encina', 'salt',
    'ciudad', 'lugar', 'campo', 'puerta', 'casa', 'tienda', 'piedra',
    'cueva', 'pozo', 'altar', 'sangre', 'sembrar', 'semilla', 'cordero',
    'desierto', 'rio', 'río', 'mar', 'agua', 'aguas', 'tierra',
    'al norte', 'sur', 'oriente', 'occidente', 'norte', 'levante',
    'mi pueblo', 'sea atado', 'mi vigor',
})


def consk(s: str) -> str:
    return ''.join(c for c in (s or '') if 0x05D0 <= ord(c) <= 0x05EA)


def es_compuesta(es: str) -> bool:
    """True si la glosa es compuesta (varias palabras o con guion sin maqaf)."""
    if not es:
        return False
    s = es.strip()
    if not s:
        return False
    # Maqaf legítimo: 'Beit-', 'Malkí-', 'Rehobot-' (termina en guion sin más).
    if s.endswith('-') and ' ' not in s and s.count('-') == 1:
        return False
    if '-' in s and ' ' not in s and not s.startswith("'"):
        return True
    if ' ' in s and len(s.split()) >= 2:
        return True
    return False


def parece_literal(es: str) -> bool:
    """True si la glosa parece traducción literal en lugar de transliteración."""
    if not es:
        return False
    s = es.strip().lower()
    if not s:
        return False
    if s in LITERAL_HINTS:
        return True
    primera = s.split()[0]
    if primera in LITERAL_HINTS and len(s.split()) <= 3:
        return True
    return False


def load_protected(slug: str, ctx_omit: set[str] | None = None) -> tuple[set[str], set[tuple]]:
    """Reglas globales por Strong + contextuales por (ch,vs,pi,wi).

    `ctx_omit`: ids de reglas ctx a NO considerar protegidas (p. ej. cuando
    han sido marcadas como anómalas por la auditoría)."""
    reg = json.loads(GLOSAS_PATH.read_text(encoding='utf-8'))
    prot_strongs: set[str] = set()
    for r in reg.get('global', []):
        st = (r.get('match') or {}).get('strongs')
        if st:
            prot_strongs.add(st)
    prot_ctx: set[tuple] = set()
    omit = ctx_omit or set()
    for r in reg.get('contexto', []):
        if r.get('id') in omit:
            continue
        m = r.get('match') or {}
        if m.get('book') == slug:
            prot_ctx.add((
                m.get('chapter'), m.get('verse'),
                m.get('pairIdx'), m.get('hwIdx'),
            ))
    return prot_strongs, prot_ctx


def auditar_artefactos(
    d: dict,
    slug: str,
    chapter_filter,
) -> dict:
    """Detecta artefactos del spider (A/B/C/D) en el rango indicado.

    `chapter_filter(ch:int) -> bool`: filtra los capítulos a auditar.

    Devuelve:
      {
        'A': [(ch,vs,pi,wi,hf,es,morph)...],
        'B': [((ch,vs,pi,wi),(ch,vs,pi,wi),hf1,hf2,es)...],
        'C': [(rule_id,(ch,vs,pi,wi),hf,before,cur,after,reason)...],
        'D': [(ch,vs,pi,wi,hf,es,morph)...],
        'B_keys': set of token keys involved in B (for cleanup),
        'C_ids': set of rule ids to delete (in cleanup),
      }
    """
    reg = json.loads(GLOSAS_PATH.read_text(encoding='utf-8'))

    A_list = []
    B_list = []
    D_list = []
    B_keys: set[tuple] = set()
    nprop_index: dict[tuple, dict] = {}

    for v in d.get('verses', []):
        ch, vs = v['chapter'], v['verse']
        if not chapter_filter(ch):
            continue
        prev = None
        for pi, p in enumerate(v.get('pairs') or []):
            if p.get('kind') == 'gk_add':
                continue
            for wi, hw in enumerate(p.get('he_words') or []):
                m = (hw.get('he_morph') or '')
                if not (m == 'NPROP' or m.startswith('GENT.')):
                    prev = None
                    continue
                key = (ch, vs, pi, wi)
                nprop_index[key] = hw
                hf = hw.get('he_form') or ''
                es = (hw.get('es') or '').strip()
                if es_compuesta(es):
                    A_list.append((ch, vs, pi, wi, hf, es, m))
                if parece_literal(es):
                    D_list.append((ch, vs, pi, wi, hf, es, m))
                if prev is not None:
                    pk, phf, pes, _ = prev
                    if es and pes and es == pes and es_compuesta(es):
                        B_list.append((pk, key, phf, hf, es))
                        B_keys.add(pk)
                        B_keys.add(key)
                prev = (key, hf, es, m)

    C_list = []
    C_ids: set[str] = set()
    for r in reg.get('contexto', []) or []:
        m = r.get('match') or {}
        if m.get('book') != slug:
            continue
        if m.get('role') != 'stem':
            continue
        key = (m.get('chapter'), m.get('verse'), m.get('pairIdx'), m.get('hwIdx'))
        if key not in nprop_index:
            continue
        if not chapter_filter(m.get('chapter') or 0):
            continue
        before = ((r.get('before') or {}).get('es') or '').strip()
        after = ((r.get('after') or {}).get('es') or '').strip()
        cur = (nprop_index[key].get('es') or '').strip()
        reason = None
        # Anomalías: after es literal traducido, o regla no-op (before==after),
        # o after apunta a una glosa compuesta repetida (B).
        if parece_literal(after):
            reason = 'after literal'
        elif after and after == before:
            reason = 'no-op (before==after)'
        elif key in B_keys and after == cur and es_compuesta(after):
            reason = 'fija duplicado spider'
        if reason:
            C_list.append((r.get('id'), key, nprop_index[key].get('he_form'),
                           before, cur, after, reason))
            C_ids.add(r.get('id'))

    return {
        'A': A_list, 'B': B_list, 'C': C_list, 'D': D_list,
        'B_keys': B_keys, 'C_ids': C_ids,
    }


def limpiar_artefactos(
    d: dict,
    slug: str,
    audit: dict,
    apply: bool,
) -> tuple[int, int]:
    """Limpia artefactos B (vacía `es` para forzar re-transliteración) y C
    (borra reglas ctx anómalas). Solo escribe si apply=True.

    Retorna (tokens_b_limpiados, reglas_c_borradas).
    """
    n_b = 0
    n_c = 0
    if audit['B_keys']:
        for v in d.get('verses', []):
            ch, vs = v['chapter'], v['verse']
            for pi, p in enumerate(v.get('pairs') or []):
                for wi, hw in enumerate(p.get('he_words') or []):
                    if (ch, vs, pi, wi) in audit['B_keys']:
                        if apply:
                            hw['es'] = ''
                        n_b += 1
    if audit['C_ids'] and apply:
        reg = json.loads(GLOSAS_PATH.read_text(encoding='utf-8'))
        kept = [r for r in (reg.get('contexto') or [])
                if r.get('id') not in audit['C_ids']]
        n_c = len(reg.get('contexto') or []) - len(kept)
        reg['contexto'] = kept
        reg['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        GLOSAS_PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                               encoding='utf-8')
    elif audit['C_ids']:
        n_c = len(audit['C_ids'])
    return n_b, n_c


def chapter_in_scope(ch: int, args: argparse.Namespace) -> bool:
    if args.chapter is not None:
        return ch == args.chapter
    lo = args.from_chapter or 0
    hi = args.to_chapter or 9999
    return lo <= ch <= hi


def is_protected(
    ch: int, vs: int, pi: int, wi: int, hw: dict,
    prot_strongs: set[str], prot_ctx: set[tuple],
) -> bool:
    st = hw.get('strongs') or ''
    return st in prot_strongs or (ch, vs, pi, wi) in prot_ctx


def hw_wordable_seq(verse: dict) -> list[tuple[int, int, dict]]:
    """Secuencia de he_words no-meta en orden de lectura (como el visor)."""
    seq: list[tuple[int, int, dict]] = []
    for pi, pair in enumerate(verse.get('pairs') or []):
        if pair.get('kind') == 'gk_add':
            continue
        for wi, hw in enumerate(pair.get('he_words') or []):
            if is_meta_raw(hw.get('raw') or ''):
                continue
            seq.append((pi, wi, hw))
    return seq


def maqaf_nprop_groups(verse: dict) -> list[list[tuple[int, int, dict]]]:
    """Cadenas de ≥2 NPROP enlazados por maqaf (־) en el mismo verso."""
    seq = hw_wordable_seq(verse)
    groups: list[list[tuple[int, int, dict]]] = []
    i = 0
    while i < len(seq):
        _, _, hw = seq[i]
        if (hw.get('he_morph') or '') != 'NPROP':
            i += 1
            continue
        chain = [seq[i]]
        j = i
        while j < len(seq) - 1:
            _, _, hw0 = seq[j]
            _, _, hw1 = seq[j + 1]
            if (hw1.get('he_morph') or '') != 'NPROP':
                break
            he0 = hw0.get('he_form') or ''
            he1 = hw1.get('he_form') or ''
            if not (has_trailing_maqaf(he0) or has_leading_maqaf(he1)):
                break
            j += 1
            chain.append(seq[j])
        if len(chain) >= 2:
            groups.append(chain)
            i = j + 1
        else:
            i += 1
    return groups


def apply_translit_fields(
    hw: dict,
    esp: str,
    acad: str,
    *,
    write_es: bool,
) -> None:
    hw['translit_academica'] = acad
    hw['render_espanol'] = esp
    if write_es:
        hw['es'] = esp


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser(description='Aplicar transliteración de nombres propios')
    ap.add_argument('--book', default='genesis')
    ap.add_argument('--chapter', type=int, default=None)
    ap.add_argument('--from-chapter', type=int, default=None)
    ap.add_argument('--to-chapter', type=int, default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--limpiar-artefactos', action='store_true',
                    help='Limpia artefactos del spider (B/C) antes de transliterar.')
    ap.add_argument('--solo-auditoria', action='store_true',
                    help='Solo auditar, no transliterar.')
    args = ap.parse_args()

    dm = DATA_DIR / f'{args.book}_final.json'
    if not dm.exists():
        print(f'No existe {dm}', file=sys.stderr)
        return 1

    d = json.loads(dm.read_text(encoding='utf-8'))

    # ── Auditoría de artefactos ──────────────────────────────────────────────
    audit = auditar_artefactos(d, args.book, lambda ch: chapter_in_scope(ch, args))

    print('═══ AUDITORÍA DE ARTEFACTOS ═══')
    print(f"A) NPROP/GENT con glosa compuesta sospechosa: {len(audit['A'])}")
    for ch, vs, pi, wi, hf, es, morph in audit['A'][:40]:
        print(f"   {ch:>2}:{vs:<2} p{pi:>2}/w{wi}  {hf:<22} morph={morph:<14} es={es!r}")
    if len(audit['A']) > 40:
        print(f"   ... y {len(audit['A'])-40} más")

    print(f"\nB) Pares NPROP consecutivos con MISMA glosa compuesta: {len(audit['B'])}")
    for pk, k, phf, hf, es in audit['B']:
        ch, vs, _, _ = k
        print(f"   {ch:>2}:{vs:<2}  prev={phf!r} -> cur={hf!r}  es={es!r}")

    print(f"\nC) Reglas ctx anómalas contra NPROP/GENT: {len(audit['C'])}")
    for rid, key, hf, before, cur, after, reason in audit['C']:
        ch, vs, pi, wi = key
        print(f"   {rid}  {ch}:{vs} p{pi}/w{wi}  hf={hf!r}  "
              f"before={before!r} cur={cur!r} after={after!r}  [{reason}]")

    print(f"\nD) NPROP/GENT con glosa literal traducida: {len(audit['D'])}")
    for ch, vs, pi, wi, hf, es, morph in audit['D'][:30]:
        print(f"   {ch:>2}:{vs:<2} p{pi:>2}/w{wi}  {hf:<22} morph={morph:<14} es={es!r}")
    if len(audit['D']) > 30:
        print(f"   ... y {len(audit['D'])-30} más")

    if args.solo_auditoria:
        return 0

    # ── Limpieza de artefactos (opcional) ────────────────────────────────────
    cleaned_b, cleaned_c = 0, 0
    if args.limpiar_artefactos:
        cleaned_b, cleaned_c = limpiar_artefactos(d, args.book, audit, args.apply)
        print(f"\n═══ LIMPIEZA DE ARTEFACTOS ({'APPLY' if args.apply else 'DRY-RUN'}) ═══")
        print(f"  tokens B con `es` vaciado: {cleaned_b}")
        print(f"  reglas ctx C borradas: {cleaned_c}")

    # ── Cargar protecciones (excluyendo reglas C anómalas ya limpiadas) ─────
    ctx_omit = audit['C_ids'] if args.limpiar_artefactos else set()
    prot_strongs, prot_ctx = load_protected(args.book, ctx_omit=ctx_omit)
    print(f"\n═══ TRANSLITERACIÓN ({'APPLY' if args.apply else 'DRY-RUN'}) ═══")

    maqaf_done: set[tuple[int, int, int, int]] = set()  # (ch, vs, pi, wi)
    locative_done: set[tuple[int, int, int, int]] = set()
    targets: list[tuple[dict, str, str, str]] = []  # hw, gk, old_es, kind
    grp_esp: dict[str, Counter] = defaultdict(Counter)
    grp_acad: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    skipped_prot = skipped_nostrong = 0
    maqaf_groups = 0
    maqaf_tokens = 0
    locative_tokens = 0
    maqaf_report: list[str] = []
    locative_report: list[str] = []
    gent_tokens = 0
    nprop_tokens = 0

    for v in d['verses']:
        ch = v['chapter']
        if not chapter_in_scope(ch, args):
            continue
        vs = v['verse']

        for chain in maqaf_nprop_groups(v):
            he_forms = [hw.get('he_form') or '' for _, _, hw in chain]
            if consk(fused_he_form(he_forms)) in YHWH_CONS:
                continue
            if any(
                is_protected(ch, vs, pi, wi, hw, prot_strongs, prot_ctx)
                for pi, wi, hw in chain
            ):
                skipped_prot += len(chain)
                continue

            partes = transliterar_maqaf_partes(he_forms)
            if not any(p['espanol'] for p in partes):
                continue

            maqaf_groups += 1
            ref = f'{ch}:{vs}'
            parts_txt = ' + '.join(
                f"{hf!r}->{p['espanol']!r}" for hf, p in zip(he_forms, partes)
            )
            maqaf_report.append(f'  {ref}  {parts_txt}')

            for idx, ((pi, wi, hw), parte) in enumerate(zip(chain, partes)):
                esp = parte['espanol']
                acad = parte['academica']
                if not esp:
                    continue
                maqaf_done.add((ch, vs, pi, wi))
                maqaf_tokens += 1
                # Maqaf: cada eslabón lleva su glosa (Beit- | el), no solo el primero.
                if args.apply:
                    apply_translit_fields(hw, esp, acad, write_es=True)

        for pi, p in enumerate(v.get('pairs', [])):
            for wi, w in enumerate(p.get('he_words', [])):
                if (ch, vs, pi, wi) in maqaf_done or (ch, vs, pi, wi) in locative_done:
                    continue
                morph = w.get('he_morph') or ''
                if not es_nprop_o_gent(morph):
                    continue
                tr_loc = transliterar_locativo_nprop(w)
                if tr_loc:
                    if is_protected(ch, vs, pi, wi, w, prot_strongs, prot_ctx):
                        skipped_prot += 1
                        continue
                    esp = tr_loc['espanol']
                    acad = tr_loc['academica']
                    old_es = (w.get('es') or '').strip()
                    locative_done.add((ch, vs, pi, wi))
                    locative_tokens += 1
                    locative_report.append(
                        f'  {ch}:{vs}  {he_fusionado_hw(w)!r}  old[{old_es!r}]'
                        f'  ->  esp={esp!r}  acad={acad!r}'
                    )
                    if args.apply:
                        inferred = inferir_strongs_nprop(w)
                        if inferred and not (w.get('strongs') or '').strip():
                            w['strongs'] = inferred
                        apply_translit_fields(w, esp, acad, write_es=True)
                    continue

                hf = w.get('he_form') or ''
                st = (w.get('strongs') or '').strip()
                inferred = inferir_strongs_nprop(w)
                if inferred and (not st or (morph.startswith('GENT.') and st != inferred)):
                    st = inferred
                    if args.apply:
                        w['strongs'] = inferred
                cons = consk(hf)
                if not cons:
                    # Sin consonantes hebreas no hay nada que transliterar.
                    skipped_nostrong += 1
                    continue
                if cons in YHWH_CONS:
                    continue
                if is_protected(ch, vs, pi, wi, w, prot_strongs, prot_ctx):
                    skipped_prot += 1
                    continue
                tr = transliterar(hf)
                esp = tr['espanol']
                acad = tr['academica']
                if not esp:
                    skipped_nostrong += 1
                    continue
                # gk: SIEMPRE (Strong, consk) para evitar que dos formas hebreas
                # distintas que comparten Strong (p. ej. פַּדַּן y אֲרָם con H758
                # en "Paddan-Aram") se agrupen y se contaminen entre sí.
                gk = f'{st}|{cons}' if st else cons
                kind = 'GENT' if morph.startswith('GENT.') else 'NPROP'
                grp_esp[gk][esp] += 1
                grp_acad[gk][esp][acad] += 1
                targets.append((w, gk, (w.get('es') or '').strip(), kind))

    canon: dict[str, tuple[str, str]] = {}
    for gk, cnt in grp_esp.items():
        best = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[0][0]
        bestacad = sorted(grp_acad[gk][best].items(), key=lambda x: (-x[1], x[0]))[0][0]
        canon[gk] = (best, bestacad)

    mapping: dict[str, dict] = defaultdict(
        lambda: {'old': Counter(), 'esp': '', 'acad': '', 'n': 0, 'kind': ''}
    )
    changed = maqaf_tokens + locative_tokens
    for w, gk, old_es, kind in targets:
        esp, acad = canon[gk]
        rec = mapping[gk]
        rec['old'][old_es] += 1
        rec['esp'] = esp
        rec['acad'] = acad
        rec['n'] += 1
        rec['kind'] = kind
        if kind == 'GENT':
            gent_tokens += 1
        else:
            nprop_tokens += 1
        if args.apply:
            apply_translit_fields(w, esp, acad, write_es=True)
        changed += 1

    scope = f'cap. {args.chapter}' if args.chapter else f'caps {args.from_chapter or 1}–{args.to_chapter or "fin"}'
    print(f'· {args.book} · {scope}')
    print('tokens a transliterar:', changed)
    print('  NPROP:', nprop_tokens, '| GENT:', gent_tokens)
    print('  maqaf: grupos', maqaf_groups, '| tokens', maqaf_tokens)
    print('  locativo -áh: tokens', locative_tokens)
    print('omitidos por protegido:', skipped_prot, '| sin strong (constructo/frag):', skipped_nostrong)
    print('formas distintas (Strong):', len(mapping))
    if maqaf_report:
        print('\n── NPROP maqaf ──')
        for line in maqaf_report:
            print(line)
    if locative_report:
        print('\n── NPROP locativo (-áh) ──')
        for line in locative_report:
            print(line)
    if mapping:
        print('\n── NPROP / GENT con Strong ──')
        items = sorted(mapping.items(), key=lambda x: -x[1]['n'])
        for gk, rec in items:
            old = ', '.join(f'{k!r}x{n}' for k, n in rec['old'].most_common(2))
            tag = rec.get('kind') or '?'
            print(
                f"{gk!r:12} {tag:4} n={rec['n']:<3} old[{old}]"
                f"  ->  esp={rec['esp']!r}  acad={rec['acad']!r}"
            )

    if args.apply and changed:
        ts = time.strftime('%Y%m%d_%H%M%S')
        ch_tag = f'_ch{args.chapter}' if args.chapter else ''
        bak = dm.with_suffix(f'.json.bak_translit{ch_tag}_{ts}')
        shutil.copyfile(dm, bak)
        dm.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'\nsaved {dm.name}  backup {bak.name}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
