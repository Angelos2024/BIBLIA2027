/**
 * Lógica compartida de tokens hebreo → español.
 * Usada por index.html y diccionario-editor.html sobre data/<slug>_final.json
 */
(function (global) {
  'use strict';

  const ES_PROCLITICS = new Set([
    'lo', 'la', 'los', 'las', 'le', 'les', 'me', 'te', 'nos', 'os', 'se',
    'su', 'mi', 'tu', 'sus', 'mis', 'tus',
    'nuestro', 'nuestra', 'nuestros', 'nuestras',
    'vuestro', 'vuestra', 'vuestros', 'vuestras'
  ]);

  const ES_TONICS = new Set([
    'él', 'ella', 'ellos', 'ellas', 'yo', 'tú', 'usted',
    'nosotros', 'nosotras', 'vosotros', 'vosotras', 'ustedes'
  ]);

  function cleanHebrew(s) {
    if (!s) return '';
    return String(s)
      .replace(/[\u0591-\u05AF]/g, '')
      .replace(/[\u05BE\u05C0]/g, '')
      .replace(/[\u05C3-\u05C6]/g, '')
      .replace(/^[\s\-–־]+/, '')
      .replace(/[\s\-–־]+$/, '')
      .trim();
  }

  // Forma consonántica: elimina TODO niqqud, cantilación y signos para emparejar
  // con el diccionario (que viene sin puntuación). Debe coincidir con
  // build_diccionario_hebreo.clean_consonants.
  function consonantsOnly(s) {
    if (!s) return '';
    return String(s)
      .replace(/[\u0591-\u05BD\u05BF\u05C1-\u05C7\u05BE\u05C0\u05F3\u05F4]/g, '')
      .replace(/[\s\-־–]+/g, '')
      .trim();
  }

  // Forma VOCALIZADA: mantiene las vocales (niqqud) y los puntos sin/shin para
  // distinguir homógrafos con mismas consonantes pero distintas vocales
  // (p. ej. אֹון vs אָוֶן). Quita solo cantilación, dagesh, meteg, rafe y signos
  // de puntuación. Debe coincidir con build_diccionario_hebreo.vowel_key.
  function vowelKey(s) {
    if (!s) return '';
    return String(s)
      .replace(/[\u0591-\u05AF]/g, '')                          // cantilación (te'amim)
      .replace(/[\u05BC\u05BD\u05BE\u05BF\u05C0\u05C3-\u05C6\u05F3\u05F4]/g, '') // dagesh, meteg, maqaf, rafe, paseq, sof pasuq, geresh
      .replace(/[\s\-־–]+/g, '')
      .trim();
  }

  // Clave FONÉMICA: normaliza las matres lectionis (vav/yod que solo escriben
  // una vocal) fusionándolas con su vocal, preservando la calidad vocálica.
  // Sirve para emparejar ortografía PLENA vs DEFECTIVA del MISMO lema
  // (אוֹתוֹת == אֹתוֹת) sin colisionar palabras de vocales distintas
  // (אוֹדֶנּוּ != אֲדֹנִי). Debe coincidir con _audit_diccionario.phon_key.
  function phonKey(s) {
    if (!s) return '';
    let t = String(s)
      .replace(/[\u0591-\u05AF\u05BD\u05BF\u05C0\u05C3-\u05C6\u05F3\u05F4\u05BE]/g, ''); // cantilación, meteg, maqaf, etc (mantiene niqqud y dagesh)
    t = t
      .replace(/\u05D5\u05B9/g, '\u05B9')   // holam male (וֹ) -> holam
      .replace(/\u05B9\u05D5/g, '\u05B9')   // holam + vav (orden alterno) -> holam
      .replace(/\u05D5\u05BC/g, '\u05BB')   // shureq (וּ) -> qibbuts
      .replace(/\u05B4\u05D9/g, '\u05B4')   // hiriq male (ִי) -> hiriq
      .replace(/\u05B5\u05D9/g, '\u05B5')   // tsere male (ֵי) -> tsere
      .replace(/\u05B6\u05D9/g, '\u05B6')   // segol male (ֶי) -> segol
      .replace(/\u05BC/g, '');              // dagesh restante
    return t.replace(/[\s\-־–]+/g, '').trim();
  }

  // Tetragrámaton (qere perpetuo): la vocal define la lectura del Nombre divino.
  //   hiriq (U+05B4) → 'Elohim ; holam (U+05B9/U+05BA) → Adonai ; resto → Hashem.
  // El emparejado global de H3068 es por lema/consonantes (ignora vocales), así
  // que SIN esto todas las formas se mostrarían con un único valor (Hashem).
  function tetragrammatonEs(heForm, fallback) {
    const s = heForm || '';
    if (s.indexOf('\u05B4') !== -1) return "'Elohim";
    if (s.indexOf('\u05B9') !== -1 || s.indexOf('\u05BA') !== -1) return 'Adonai';
    return fallback || 'Hashem';
  }

  function combineEsWithSuffix(stemEs, sufEs) {
    if (!sufEs) return stemEs || '';
    if (!stemEs) return sufEs;
    const sLow = sufEs.toLowerCase().trim();
    const stemLow = stemEs.toLowerCase().trim();
    if (stemLow === sLow) return stemEs;
    const stemTokens = stemLow.split(/\s+/);
    if (stemTokens.includes(sLow)) return stemEs;
    if (sLow.includes(' ') && stemLow.includes(sLow)) return stemEs;
    if (ES_PROCLITICS.has(sLow)) return `${sufEs} ${stemEs}`;
    if (ES_TONICS.has(sLow)) return `${stemEs} ${sufEs}`;
    if (sLow.startsWith('a ')) return `${stemEs} ${sufEs}`;
    return `${stemEs} ${sufEs}`;
  }

  function buildElements(pair) {
    const elements = [];
    const grTextFull = (pair.gr_unicode || '').trim();
    const grMorphAll = pair.morph_summary || '';

    let hasIndividualGr = false;
    for (const hw of (pair.he_words || [])) {
      if (hw.gr_word) { hasIndividualGr = true; break; }
      if ((hw.prefix_gr || []).some(g => g)) { hasIndividualGr = true; break; }
    }

    // prefix_forms marca el número real de prefijos (ver nota en index.html).
    let totalElems = 0;
    for (const hw of (pair.he_words || [])) {
      totalElems += (hw.prefix_forms || []).length + 1;
    }

    let elemIdx = 0;
    for (const hw of (pair.he_words || [])) {
      const prefixForms = hw.prefix_forms || [];
      const prefixMorphs = hw.prefix_morphs || [];
      const prefixEs = hw.prefix_es || [];
      const prefixGr = hw.prefix_gr || [];

      for (let i = 0; i < prefixForms.length; i++) {
        const isLast = (elemIdx === totalElems - 1);
        const rawMorph = prefixMorphs[i] || '';
        const plusIdx = rawMorph.indexOf('+RBS');
        const hasCombinedSuf = plusIdx !== -1;
        const stemMorph = hasCombinedSuf ? rawMorph.slice(0, plusIdx) : rawMorph;
        const sufMorph = hasCombinedSuf ? rawMorph.slice(plusIdx + 1) : '';

        elements.push({
          type: 'prefix',
          form: prefixForms[i] || '',
          morph: stemMorph,
          es: prefixEs[i] || '',
          esSource: hw.es_source || '',
          prefixLabel: (hw.prefix_labels || [])[i] || '',
          hePrefix: prefixForms[i] || '',
          prsSuffix: hasCombinedSuf ? { he_form: '', he_morph: sufMorph, es: _sufMorphToEs(sufMorph), gr_word: '' } : null
        });
        elemIdx++;
      }

      const isLast = (elemIdx === totalElems - 1);
      elements.push({
        type: 'stem',
        form: hw.he_form || hw.stem_unicode || hw.full_unicode || '·',
        morph: hw.he_morph || hw.stem_label || '',
        es: hw.es || '',
        esSource: hw.es_source || '',
        strongs: hw.strongs || '',
        heForm: hw.he_form || '',
        grWord: hasIndividualGr ? (hw.gr_word || '') : (isLast ? grTextFull : ''),
        grMorph: isLast && !hasIndividualGr ? grMorphAll : '',
        prsSuffix: hw.prs_suffix || null
      });
      elemIdx++;
    }
    return elements;
  }

  const _SUFFIX_ES = {
    RBSM3: 'su', RBSF3: 'su', RBPM3: 'su', RBPF3: 'su', RBPC3: 'su',
    RBSM2: 'tu', RBSF2: 'tu', RBPM2: 'vuestro', RBPF2: 'vuestro',
    RBSM1: 'mi', RBSC1: 'mi', RBSF1: 'mi',
    RBPM1: 'nuestro', RBPC1: 'nuestro'
  };

  function _sufMorphToEs(morph) {
    return _SUFFIX_ES[morph] || '';
  }

  function displayToken(el) {
    if (String(el.esSource || '').toLowerCase() === 'patch_meta' && !String(el.es || '').trim()) {
      return { he: '', es: '' };
    }
    let displayForm = el.form;
    let displayEs = el.es;

    if (el.prsSuffix) {
      const sf = el.prsSuffix;
      const heStem = cleanHebrew(el.form) || '';
      const heSuf = cleanHebrew(sf.he_form) || '';
      displayForm = heSuf ? heStem + heSuf : heStem;
      displayEs = combineEsWithSuffix(el.es, sf.es);
    }

    return {
      he: cleanHebrew(displayForm),
      es: String(displayEs || '').trim()
    };
  }

  function tokensForPair(pair) {
    if (pair.kind === 'gk_add') return [];
    if (pair.kind === 'heb_omit') {
      const he = cleanHebrew(pair.he_unicode || '');
      return he ? [{ he, es: '' }] : [];
    }

    const elements = buildElements(pair);
    const out = [];
    for (const el of elements) {
      const row = displayToken(el);
      const emptyForm = !row.he || row.he === '·' || row.he === '.';
      if (emptyForm && !row.es) continue;
      out.push(row);
    }
    return out;
  }

  function tokensForVerse(verse) {
    const rows = [];
    for (const pair of (verse.pairs || [])) {
      rows.push(...tokensForPair(pair));
    }
    return rows;
  }

  function endsWithMaqaf(heForm) {
    if (!heForm) return false;
    return /[\u05BE\-־]$/.test(String(heForm));
  }

  function startsWithMaqaf(heForm) {
    if (!heForm) return false;
    return /^[\u05BE\-־]/.test(String(heForm));
  }

  function displayElement(el, pairIdx, hwIdx, prefixIdx) {
    if (String(el.esSource || '').toLowerCase() === 'patch_meta' && !String(el.es || '').trim()) {
      return null;
    }
    let displayForm = el.form;
    let displayEs = el.es;
    let combined = false;

    if (el.prsSuffix) {
      const sf = el.prsSuffix;
      const heStem = cleanHebrew(el.form) || '';
      const heSuf = cleanHebrew(sf.he_form) || '';
      displayForm = heSuf ? heStem + heSuf : heStem;
      displayEs = combineEsWithSuffix(el.es, sf.es);
      combined = true;
    }

    const probeForm = cleanHebrew(displayForm);
    const probeEs = String(displayEs || '').trim();
    const emptyForm = !probeForm || probeForm === '·' || probeForm === '.';
    if (emptyForm && !probeEs) return null;

    let editPath;
    if (combined) {
      editPath = { pairIdx, hwIdx, field: 'es', combined: true };
    } else if (el.type === 'prefix') {
      editPath = { pairIdx, hwIdx, field: 'prefix_es', prefixIdx };
    } else {
      editPath = { pairIdx, hwIdx, field: 'es', combined: false };
    }

    return {
      he: probeForm,
      es: probeEs,
      isPrefix: el.type === 'prefix',
      editPath,
      tokenMeta: buildTokenMeta(el, combined)
    };
  }

  function buildTokenMeta(el, combined) {
    if (el.type === 'prefix') {
      return {
        role: 'prefix',
        prefix_morph: el.morph || '',
        prefix_label: el.prefixLabel || '',
        he_prefix: el.hePrefix || el.form || ''
      };
    }
    return {
      role: 'stem',
      strongs: el.strongs || '',
      he_form: el.heForm || el.form || '',
      he_morph: el.morph || '',
      combined: !!combined
    };
  }

  function applyGlossEdit(verse, editPath, value) {
    if (!verse || !editPath) return false;
    const pair = verse.pairs?.[editPath.pairIdx];
    if (!pair) return false;

    const text = String(value ?? '').trim();

    if (editPath.field === 'heb_omit_es') {
      pair.es_gloss = text;
      return true;
    }

    const hw = pair.he_words?.[editPath.hwIdx];
    if (!hw) return false;

    if (editPath.field === 'prefix_es') {
      if (!Array.isArray(hw.prefix_es)) hw.prefix_es = [];
      hw.prefix_es[editPath.prefixIdx] = text;
      return true;
    }

    hw.es = text;
    if (editPath.combined && hw.prs_suffix) {
      hw.prs_suffix.es = '';
    }
    return true;
  }

  function normalizeStrongs(raw) {
    if (!raw) return '';
    const s = String(raw).trim().toUpperCase();
    const m = s.match(/^([HG])0*(\d+)/);
    return m ? `${m[1]}${m[2]}` : s;
  }

  function normalizeEditPath(path) {
    if (!path) return {};
    return {
      pairIdx: path.pairIdx,
      hwIdx: path.hwIdx ?? null,
      field: path.field || '',
      prefixIdx: path.prefixIdx ?? null,
      combined: !!path.combined
    };
  }

  function editPathEqual(a, b) {
    const x = normalizeEditPath(a);
    const y = normalizeEditPath(b);
    return JSON.stringify(x) === JSON.stringify(y);
  }

  function matchesWordQuery(unitMeta, queryMeta) {
    const q = queryMeta || {};
    const m = unitMeta || {};
    if (q.role === 'prefix' || m.role === 'prefix') {
      if (m.role !== 'prefix') return false;
      if (q.prefix_label && q.prefix_label !== m.prefix_label) return false;
      if (q.prefix_morph && q.prefix_morph !== m.prefix_morph) return false;
      if (q.he_prefix && q.he_prefix !== m.he_prefix) return false;
      return !!(q.prefix_label || q.prefix_morph || q.he_prefix);
    }
    if (q.role === 'heb_omit') {
      return m.role === 'heb_omit' && (!q.he_form || q.he_form === m.he_form);
    }
    if (m.role !== 'stem') return false;
    if (normalizeStrongs(m.strongs) !== normalizeStrongs(q.strongs)) return false;
    if (q.he_form) {
      const qHe = cleanHebrew(q.he_form);
      const mHe = cleanHebrew(m.he_form || '');
      if (qHe && mHe && qHe !== mHe) return false;
    }
    return true;
  }

  function isHideOshbDupHw(hw) {
    return (
      String(hw.es_source || '').toLowerCase() === 'patch_meta' &&
      !String(hw.es || '').trim() &&
      !(hw.prefix_es || []).some(x => String(x || '').trim()) &&
      !String((hw.prs_suffix || {}).es || '').trim()
    );
  }

  function collectVerseEditorUnits(verse) {
    const out = [];
    for (let pairIdx = 0; pairIdx < (verse.pairs || []).length; pairIdx++) {
      const pair = verse.pairs[pairIdx];
      if (pair.kind === 'gk_add') continue;

      if (pair.kind === 'heb_omit') {
        const he = cleanHebrew(pair.he_unicode || '');
        if (!he) continue;
        out.push({
          unit: {
            he,
            es: String(pair.es_gloss || '').trim(),
            isPrefix: false,
            editPath: { pairIdx, field: 'heb_omit_es' },
            tokenMeta: { role: 'heb_omit', he_form: he }
          }
        });
        continue;
      }

      const elements = buildElements(pair);
      let elIdx = 0;
      for (let hwIdx = 0; hwIdx < (pair.he_words || []).length; hwIdx++) {
        const hw = pair.he_words[hwIdx];
        const numElems = (hw.prefix_forms || []).length + 1;
        if (isHideOshbDupHw(hw)) {
          elIdx += numElems;
          continue;
        }
        const hwElems = elements.slice(elIdx, elIdx + numElems);
        elIdx += numElems;

        let prefixIdx = 0;
        for (const el of hwElems) {
          const pIdx = el.type === 'prefix' ? prefixIdx++ : null;
          const unit = displayElement(el, pairIdx, hwIdx, pIdx);
          if (unit) out.push({ unit });
        }
      }
    }
    return out;
  }

  function findMatchingOccurrences(interlinealData, queryMeta) {
    const out = [];
    for (const verse of (interlinealData?.verses || [])) {
      for (const row of collectVerseEditorUnits(verse)) {
        const unit = row.unit;
        if (!matchesWordQuery(unit.tokenMeta, queryMeta)) continue;
        out.push({
          chapter: verse.chapter,
          verse: verse.verse,
          editPath: unit.editPath,
          tokenMeta: unit.tokenMeta,
          es: unit.es,
          he: unit.he
        });
      }
    }
    out.sort((a, b) => (a.chapter - b.chapter) || (a.verse - b.verse));
    return out;
  }

  // Candidatos por forma CONSONÁNTICA entre los stems del libro (amplio).
  // Usado por el flujo "Diccionario" como primer filtro; la desambiguación fina
  // (por vocales / Strong) la hace el cliente sobre estos candidatos. Cada occ
  // incluye tokenMeta (con he_form y strongs) para poder afinar después.
  function findOccurrencesByForm(interlinealData, forma) {
    const target = consonantsOnly(forma);
    const out = [];
    if (!target) return out;
    // Respaldo plene/defectivo: si NO hay match consonántico exacto en este
    // libro, se aceptan formas con la misma clave fonémica (matres lectionis
    // normalizadas). Solo se usa cuando el match exacto da 0, así no altera
    // el comportamiento de las palabras que ya emparejan.
    const phonTarget = phonKey(forma);
    const fallback = [];
    for (const verse of (interlinealData?.verses || [])) {
      for (const row of collectVerseEditorUnits(verse)) {
        const unit = row.unit;
        const meta = unit.tokenMeta || {};
        if (meta.role !== 'stem') continue;
        const heForm = meta.he_form || unit.he || '';
        const form = consonantsOnly(heForm);
        if (!form) continue;
        if (form === target) {
          out.push({
            chapter: verse.chapter,
            verse: verse.verse,
            editPath: unit.editPath,
            tokenMeta: unit.tokenMeta,
            es: unit.es,
            he: unit.he
          });
        } else if (phonTarget && phonKey(heForm) === phonTarget) {
          fallback.push({
            chapter: verse.chapter,
            verse: verse.verse,
            editPath: unit.editPath,
            tokenMeta: unit.tokenMeta,
            es: unit.es,
            he: unit.he
          });
        }
      }
    }
    const result = out.length ? out : fallback;
    result.sort((a, b) => (a.chapter - b.chapter) || (a.verse - b.verse));
    return result;
  }

  function buildEditorTokenHtml(unit, escHtml, options) {
    const opts = options || {};
    const prefixCls = unit.isPrefix ? ' tok-elem-prefix' : '';
    const pathAttr = escHtml(JSON.stringify(unit.editPath));
    const metaAttr = escHtml(JSON.stringify(unit.tokenMeta || {}));
    const heHtml = unit.he
      ? escHtml(unit.he)
      : '<span style="opacity:.18">—</span>';
    const glossHtml = escHtml(unit.es || '');
    const isTarget = opts.highlightEditPath
      && editPathEqual(unit.editPath, opts.highlightEditPath);
    const useClick = !!opts.clickToEdit && (!opts.editableOnlyTarget || isTarget);
    const editable = !useClick && (opts.editableOnlyTarget ? isTarget : (opts.editable !== false));
    const targetCls = isTarget ? ' is-context-target' : '';
    const readOnlyCls = (!useClick && !editable) ? ' is-readonly' : '';
    const glossBody = glossHtml || '—';

    let glossEl;
    if (useClick) {
      glossEl = `<button type="button" class="admin-morph-segment-gloss gloss-clickable${targetCls}"
               data-original="${glossHtml}"
               title="Clic para editar">${glossBody}</button>`;
    } else if (editable) {
      glossEl = `<div class="admin-morph-segment-gloss is-editable${targetCls}"
               contenteditable="true" spellcheck="true"
               data-original="${glossHtml}">${glossBody}</div>`;
    } else {
      glossEl = `<div class="admin-morph-segment-gloss${readOnlyCls}${targetCls}"
               data-original="${glossHtml}">${glossBody}</div>`;
    }

    return `
      <div class="admin-morph-token${prefixCls}${targetCls}"
           data-edit-path="${pathAttr}"
           data-token-meta="${metaAttr}"
           data-he="${escHtml(unit.he || '')}">
        <div class="admin-morph-segment">
          <div class="admin-morph-segment-hebrew">${heHtml}</div>
          ${glossEl}
        </div>
      </div>`;
  }

  function buildVerseEditorStrip(verse, escHtml, options) {
    const opts = options || {};
    const seq = [];

    for (let pairIdx = 0; pairIdx < (verse.pairs || []).length; pairIdx++) {
      const pair = verse.pairs[pairIdx];
      if (pair.kind === 'gk_add') continue;

      if (pair.kind === 'heb_omit') {
        const he = cleanHebrew(pair.he_unicode || '');
        if (!he) continue;
        const unit = {
          he,
          es: String(pair.es_gloss || '').trim(),
          isPrefix: false,
          editPath: { pairIdx, field: 'heb_omit_es' },
          tokenMeta: { role: 'heb_omit', he_form: he }
        };
        seq.push({
          html: buildEditorTokenHtml(unit, escHtml, opts),
          heForm: '',
          isWordable: false,
          _maqafGroupId: null
        });
        continue;
      }

      const elements = buildElements(pair);
      let elIdx = 0;

      for (let hwIdx = 0; hwIdx < (pair.he_words || []).length; hwIdx++) {
        const hw = pair.he_words[hwIdx];
        const numElems = (hw.prefix_forms || []).length + 1;
        if (isHideOshbDupHw(hw)) {
          elIdx += numElems;
          continue;
        }
        const hwElems = elements.slice(elIdx, elIdx + numElems);
        elIdx += numElems;

        let prefixIdx = 0;
        const units = [];
        for (const el of hwElems) {
          const pIdx = el.type === 'prefix' ? prefixIdx++ : null;
          const unit = displayElement(el, pairIdx, hwIdx, pIdx);
          if (unit) units.push(unit);
        }
        if (!units.length) continue;

        const html = units.map(u => buildEditorTokenHtml(u, escHtml, opts)).join('');
        seq.push({
          html,
          heForm: hw.he_form || '',
          isWordable: true,
          _maqafGroupId: null
        });
      }
    }

    let groupCounter = 0;
    for (let k = 0; k < seq.length; k++) {
      if (!seq[k].isWordable) continue;
      if (k + 1 >= seq.length) continue;
      if (!seq[k + 1].isWordable) continue;
      const trailing = endsWithMaqaf(seq[k].heForm);
      const leadingNext = startsWithMaqaf(seq[k + 1].heForm);
      if (!trailing && !leadingNext) continue;
      let gid = seq[k]._maqafGroupId;
      if (!gid) {
        groupCounter++;
        gid = `m_${groupCounter}`;
        seq[k]._maqafGroupId = gid;
      }
      seq[k + 1]._maqafGroupId = gid;
    }

    let out = '';
    let i = 0;
    while (i < seq.length) {
      const gid = seq[i]._maqafGroupId;
      if (gid) {
        let inner = '';
        while (i < seq.length && seq[i]._maqafGroupId === gid) {
          inner += seq[i].html;
          i++;
        }
        out += `<div class="maqaf-group">${inner}</div>`;
      } else {
        out += seq[i].html;
        i++;
      }
    }
    return out;
  }

  function buildRvEditorRow(chapter, verse, text, escHtml, options) {
    const opts = options || {};
    const safe = escHtml(text || '');
    const editable = opts.editable !== false;
    return `
      <div class="tok-translate-area" data-rv-ref="${chapter}:${verse}">
        <span class="tok-translate-label">RV1960</span>
        <span class="tok-translate-text${editable ? ' is-editable' : ''}"
              ${editable ? 'contenteditable="true" spellcheck="true"' : ''}
              data-chapter="${chapter}"
              data-verse="${verse}"
              data-original="${safe}">${safe || '—'}</span>
        <span class="tok-translate-source">Reina Valera 1960</span>
      </div>`;
  }

  // Verifica que un token (he_word) corresponda a la identidad guardada en la
  // regla de contexto (strongs y/o he_form). Sirve para evitar aplicar la regla
  // al token equivocado cuando los índices del verso se han desplazado.
  function contextTokenMatches(hw, match) {
    if (!hw) return false;
    const reqStrong = normalizeStrongs(match.strongs);
    const hwStrong = normalizeStrongs(hw.strongs);
    if (reqStrong && hwStrong && hwStrong !== reqStrong) return false;
    const reqHe = match.he_form ? consonantsOnly(match.he_form) : '';
    if (reqHe) {
      const mHe = consonantsOnly(hw.he_form || hw.stem_unicode || '');
      if (mHe && reqHe !== mHe) return false;
    }
    return true;
  }

  // Busca en el verso el token que coincide con la identidad de la regla,
  // eligiendo el más cercano al pairIdx original (tolera desplazamientos de
  // índices tras reestructuraciones de prefijos/maqaf).
  function relocateContextToken(verseObj, match) {
    let best = null;
    let bestDist = Infinity;
    const pairs = verseObj.pairs || [];
    for (let pi = 0; pi < pairs.length; pi++) {
      const p = pairs[pi];
      if (p.kind === 'gk_add') continue;
      const words = p.he_words || [];
      for (let hi = 0; hi < words.length; hi++) {
        if (!contextTokenMatches(words[hi], match)) continue;
        const dist = Math.abs(pi - (match.pairIdx ?? 0));
        if (dist < bestDist) { bestDist = dist; best = words[hi]; }
      }
    }
    return best;
  }

  function applyContextRuleToInterlineal(interlineal, rule, isLocked) {
    const match = rule.match || {};
    const afterEs = String((rule.after || {}).es ?? '').trim();
    const chapter = match.chapter;
    const verse = match.verse;
    const pairIdx = match.pairIdx;
    const field = match.field;

    // Candado: capítulo cerrado = congelado; se muestra tal cual el disco.
    if (isLocked && isLocked(chapter)) return 0;

    const verseObj = (interlineal?.verses || []).find(v => v.chapter === chapter && v.verse === verse);
    if (!verseObj) return 0;

    if (field === 'heb_omit_es') {
      const pair = verseObj.pairs[pairIdx];
      if (String(pair?.es_gloss || '').trim() === afterEs) return 0;
      pair.es_gloss = afterEs;
      return 1;
    }

    const pair = verseObj.pairs[pairIdx];
    let hw = pair?.he_words?.[match.hwIdx];

    // La regla guarda strongs/he_form: si el token en la posición registrada no
    // coincide (los índices se desplazaron), relocalizamos al token correcto y,
    // si no existe, NO aplicamos para no corromper un token ajeno.
    const verifiable = !!(normalizeStrongs(match.strongs) || match.he_form);
    if (verifiable && !contextTokenMatches(hw, match)) {
      hw = relocateContextToken(verseObj, match);
      if (!hw) return 0;
    }
    if (!hw) return 0;

    const cur = readEsFromHw(hw, field, match.prefixIdx, !!match.combined);
    if (cur === afterEs) return 0;

    writeEsToHw(hw, field, match.prefixIdx, !!match.combined, afterEs);
    return 1;
  }

  function readEsFromHw(hw, field, prefixIdx, combined) {
    if (field === 'prefix_es') {
      const arr = hw.prefix_es || [];
      if (prefixIdx == null || prefixIdx >= arr.length) return '';
      return String(arr[prefixIdx] || '').trim();
    }
    let es = String(hw.es || '').trim();
    if (combined && hw.prs_suffix) {
      const suf = String(hw.prs_suffix.es || '').trim();
      if (suf && es) return `${es} ${suf}`.trim();
      return es || suf;
    }
    return es;
  }

  function writeEsToHw(hw, field, prefixIdx, combined, value) {
    if (field === 'prefix_es') {
      if (!Array.isArray(hw.prefix_es)) hw.prefix_es = [];
      while (hw.prefix_es.length <= (prefixIdx || 0)) hw.prefix_es.push('');
      hw.prefix_es[prefixIdx || 0] = value;
      return;
    }
    hw.es = value;
    if (combined && hw.prs_suffix) hw.prs_suffix.es = '';
    hw.es_source = 'glosa_personal';
  }

  function prefixMeta(hw, prefixIdx) {
    const labels = hw.prefix_labels || [];
    const morphs = hw.prefix_morphs || [];
    const forms = hw.prefix_forms || [];
    return {
      prefix_morph: String(morphs[prefixIdx] ?? ''),
      prefix_label: String(labels[prefixIdx] ?? ''),
      he_prefix: String(forms[prefixIdx] ?? '')
    };
  }

  function stemMatchesGlobal(rule, hw) {
    // Dos capas (deben coincidir EXACTAMENTE con el predicado del servidor):
    //   mode='lemma' → solo Strong (todas las formas).
    //   mode='form'  → Strong + misma forma CONSONÁNTICA (solo esa flexión).
    const match = rule.match || {};
    if (match.role !== 'stem') return false;
    const reqStrong = normalizeStrongs(match.strongs);
    if (!reqStrong) return false;
    if (normalizeStrongs(hw.strongs) !== reqStrong) return false;
    if ((match.mode || 'lemma') === 'form') {
      const reqCons = match.consonants
        || consonantsOnly(match.he_form || '');
      if (!reqCons) return false;
      if (consonantsOnly(hw.he_form || hw.stem_unicode || '') !== reqCons) return false;
      // misma morfología → separa homógrafos del mismo Strong (p. ej.
      // sustantivo vs infinitivo verbal con consonantes idénticas).
      const reqMorph = (match.morph != null) ? String(match.morph) : null;
      if (reqMorph !== null) {
        return String(hw.he_morph || '') === reqMorph;
      }
      return true;
    }
    return true;
  }

  function prefixMatchesGlobal(rule, hw, prefixIdx) {
    const match = rule.match || {};
    if (match.role !== 'prefix') return false;
    const meta = prefixMeta(hw, prefixIdx);
    if (match.prefix_morph && match.prefix_morph !== meta.prefix_morph) return false;
    if (match.prefix_label && match.prefix_label !== meta.prefix_label) return false;
    if (match.he_prefix && match.he_prefix !== meta.he_prefix) return false;
    return true;
  }

  function applyGlobalRuleToInterlineal(interlineal, rule, isLocked) {
    const match = rule.match || {};
    const afterEs = String((rule.after || {}).es ?? '').trim();
    const role = match.role;
    let hits = 0;

    for (const verse of (interlineal?.verses || [])) {
      // Candado: no reaplicar reglas globales sobre capítulos cerrados; se
      // muestran EXACTAMENTE como quedaron sellados en disco.
      if (isLocked && isLocked(verse.chapter)) continue;
      for (const pair of (verse.pairs || [])) {
        if (pair.kind === 'gk_add' || role === 'heb_omit') continue;
        for (const hw of (pair.he_words || [])) {
          if (role === 'stem' && stemMatchesGlobal(rule, hw)) {
            // Tetragrámaton: enruta por la vocal del propio token en vez de
            // uniformar todas las formas (Hashem/Adonai/'Elohim).
            const val = (normalizeStrongs(match.strongs) === 'H3068')
              ? tetragrammatonEs(hw.he_form || hw.stem_unicode || '', afterEs)
              : afterEs;
            if (String(hw.es || '').trim() !== val) {
              hw._es_original = hw._es_original || hw.es;
              hw.es = val;
              if (hw.prs_suffix) hw.prs_suffix.es = '';
              hw.es_source = 'glosa_global';
              hits += 1;
            }
          } else if (role === 'prefix') {
            for (let i = 0; i < (hw.prefix_forms || []).length; i++) {
              if (!prefixMatchesGlobal(rule, hw, i)) continue;
              if (!Array.isArray(hw.prefix_es)) hw.prefix_es = [];
              while (hw.prefix_es.length <= i) hw.prefix_es.push('');
              if (String(hw.prefix_es[i] || '').trim() !== afterEs) {
                hw.prefix_es[i] = afterEs;
                hits += 1;
              }
            }
          }
        }
      }
    }
    return hits;
  }

  // Construye el predicado isLocked(chapter) a partir de la config de candado
  // (mismo criterio que motores/scripts/candado.py).
  function buildIsLocked(candadoCfg, book) {
    const c = ((candadoCfg || {}).candados || {})[book];
    if (!c) return null;
    const hasta = parseInt(c.bloqueados_hasta || 0, 10) || 0;
    const bloq = new Set((c.bloqueados || []).map(Number));
    const desb = new Set((c.desbloqueados || []).map(Number));
    return function (ch) {
      const n = Number(ch);
      if (desb.has(n)) return false;
      return (hasta && n <= hasta) || bloq.has(n);
    };
  }

  function applyRegistryToInterlineal(interlineal, book, registry, candadoCfg) {
    if (!interlineal || !registry) return 0;
    let hits = 0;
    const isLocked = buildIsLocked(candadoCfg, book);
    // Las reglas por FORMA (mode='form') son más específicas que las de lema:
    // se aplican DESPUÉS para que prevalezcan sobre el lema en esa flexión.
    const globalRules = (registry.global || []).slice().sort((a, b) => {
      const am = ((a.match || {}).mode === 'form') ? 1 : 0;
      const bm = ((b.match || {}).mode === 'form') ? 1 : 0;
      return am - bm;
    });
    for (const rule of globalRules) {
      // Reglas acotadas a un libro (match.book) solo se aplican a ese libro;
      // las reglas sin book son globales (todos los libros).
      const rb = (rule.match || {}).book;
      if (rb && rb !== book) continue;
      hits += applyGlobalRuleToInterlineal(interlineal, rule, isLocked);
    }
    for (const rule of (registry.contexto || [])) {
      const match = rule.match || {};
      if (match.book !== book) continue;
      hits += applyContextRuleToInterlineal(interlineal, rule, isLocked);
    }
    return hits;
  }

  global.TraduccionTokens = {
    cleanHebrew,
    consonantsOnly,
    vowelKey,
    phonKey,
    findOccurrencesByForm,
    combineEsWithSuffix,
    buildElements,
    tokensForPair,
    tokensForVerse,
    endsWithMaqaf,
    displayElement,
    applyGlossEdit,
    buildVerseEditorStrip,
    buildRvEditorRow,
    buildTokenMeta,
    normalizeStrongs,
    normalizeEditPath,
    editPathEqual,
    matchesWordQuery,
    collectVerseEditorUnits,
    findMatchingOccurrences,
    applyRegistryToInterlineal
  };
})(typeof window !== 'undefined' ? window : globalThis);
